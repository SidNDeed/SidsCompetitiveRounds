"""A1 identity-first formation primitives (rejoin batch, 2026-09-17).

Covers the primitives themselves; the per-site wiring has its own tests. The
helpers are EXECUTED against a fake session that records every statement, in
the style of test_queue_pair_writers.py -- a test that reads the source instead
of running it cannot fail for the reason we care about (#441).

Acceptance items from ai-collab/rejoin/A1-BRIEF.md covered here:

  item 2  every ordering oracle is exercised with a planted misordered trace
          AND with a source mutation, so a green result means the oracle can
          actually go red.
  item 3  the strict lease reader propagates; the three lease policies are
          told apart by their reason strings, not merely by "something
          refused".
  item 4  the REAL advisory-lock bind sequence is captured and asserted,
          including duplicate collapse. Note what is deliberately NOT tested:
          r1 asked for a steam-id pair that sorts differently lexically than
          numerically, and no such pair exists -- canonical SteamID64s are
          fixed-width 17-digit ASCII decimals, so the two orders coincide.
          The bind-sequence assertion replaces it, and the short-id case below
          is what actually separates _ffa_sort_key from bare sorted().
"""

import asyncio
import re

import pytest

import main


# --- fake session -----------------------------------------------------------

class _Result:
    def __init__(self, rows=()):
        self._rows = [dict(r) for r in rows]

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        if not self._rows:
            return None
        return list(self._rows[0].values())[0]


class _Savepoint:
    """begin_nested() for the fake. __aexit__ never swallows -- whether a
    failure is survivable is the CALLER's decision, and telling the two lease
    readers apart is the entire point of this file."""

    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        self.session.savepoints += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeSession:
    def __init__(self, leases=None, fail_lease_read=False):
        self.statements = []
        self.params = []
        self.commits = 0
        self.rollbacks = 0
        self.savepoints = 0
        # player_id -> {"mode": str, "group_id": obj} for LIVE leases only.
        self.leases = dict(leases or {})
        self.fail_lease_read = fail_lease_read

    def begin_nested(self):
        return _Savepoint(self)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.statements.append(sql)
        self.params.append(dict(params or {}))
        if "FROM queue_leases" in sql:
            if self.fail_lease_read:
                raise RuntimeError("queue_leases does not exist")
            assert "expires_at > clock_timestamp()" in sql, (
                "expiry is evaluated at READ time; a reader that drops the "
                "predicate reports dead leases as live and refuses live players"
            )
            held = self.leases.get(params["pid"])
            return _Result([held] if held else [])
        return _Result([])

    # -- what the oracles read --

    def identity_binds(self):
        """The steam ids actually bound to an identity advisory lock, in the
        order the statements were issued."""
        out = []
        for sql, prm in zip(self.statements, self.params):
            if "pg_advisory_xact_lock(hashtext(" in sql and "sid" in prm:
                out.append(prm["sid"])
        return out

    def lock_trace(self):
        """('parent', table) / ('queue', pid) in issue order."""
        out = []
        for sql, prm in zip(self.statements, self.params):
            m = re.match(r"SELECT 1 FROM (\w+) WHERE id = :pid FOR UPDATE", sql)
            if m:
                out.append(("parent", m.group(1), prm["pid"]))
                continue
            m = re.match(r"SELECT 1 FROM (\w+) WHERE player_id = :pid FOR UPDATE", sql)
            if m:
                out.append(("queue", m.group(1), prm["pid"]))
        return out


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


# --- the oracle, used by the real tests AND by the negative controls ---------

def assert_canonical_identity_order(binds, expected_sids):
    """The one oracle for item 4. Raises AssertionError on any violation."""
    assert binds == sorted(set(expected_sids), key=main._ffa_sort_key), (
        f"identity binds {binds!r} are not the canonical order of "
        f"{sorted(set(expected_sids), key=main._ffa_sort_key)!r}"
    )
    assert len(binds) == len(set(binds)), f"duplicate identity binds: {binds!r}"


# --- item 4: the real bind sequence ----------------------------------------

SIDS = ["76561198040410653", "76561198709950406", "76561198041616199"]


def test_identity_binds_are_canonically_ordered_regardless_of_input_order():
    for order in ([0, 1, 2], [2, 1, 0], [1, 2, 0]):
        db = FakeSession()
        given = [SIDS[i] for i in order]
        returned = run(main._identity_lock_many(db, given))
        binds = db.identity_binds()
        assert_canonical_identity_order(binds, given)
        assert returned == binds, (
            "the returned order must BE the bind order -- a test that trusts "
            "the return value while the loop binds something else is decoration"
        )


def test_identity_binds_collapse_duplicates_and_drop_empties():
    db = FakeSession()
    given = [SIDS[0], SIDS[1], SIDS[0], None, "", SIDS[1]]
    returned = run(main._identity_lock_many(db, given))
    assert returned == sorted({SIDS[0], SIDS[1]}, key=main._ffa_sort_key)
    assert db.identity_binds() == returned
    assert len(db.identity_binds()) == 2, (
        "a duplicate sid must be bound ONCE; binding it twice is harmless for "
        "correctness but means the roster the caller thinks it gated is not "
        "the roster it gated"
    )


def test_identity_lock_uses_the_lattice_key_not_a_private_one():
    """The whole guarantee rests on this lock serializing against the EXISTING
    lattice members. A different key expression would serialize against
    nothing and every test above would still pass."""
    db = FakeSession()
    run(main._identity_lock_many(db, [SIDS[0]]))
    # Not statements[0]: the barrier arms its lock_timeout first. Selected
    # by content so this keeps testing the KEY rather than an offset that
    # any future preamble silently redefines.
    sql = next(s for s in db.statements if "pg_advisory_xact_lock" in s)
    assert "pg_advisory_xact_lock(hashtext(" in sql, sql
    assert "_shared" not in sql, (
        "formation takes the EXCLUSIVE identity lock; the shared form would "
        "let two formations hold the same identity simultaneously"
    )
    gate_src = main.inspect.getsource(main._enrollment_identity_gate) \
        if hasattr(main, "inspect") else None
    if gate_src is None:
        import inspect as _i
        gate_src = _i.getsource(main._enrollment_identity_gate)
    assert "pg_advisory_xact_lock(hashtext(" in gate_src, (
        "the enrollment gate no longer takes this lock in this form -- the two "
        "have drifted apart and formation is serializing against nothing"
    )


def test_short_ids_order_by_length_then_ordinal_not_bare_lexical():
    """This is the case that actually distinguishes _ffa_sort_key from
    sorted(). On canonical 17-digit ids the two agree, so a test built only
    from real steam ids cannot tell which key is in use."""
    db = FakeSession()
    returned = run(main._identity_lock_many(db, ["10", "9"]))
    assert returned == ["9", "10"], returned
    assert sorted(["10", "9"]) == ["10", "9"], (
        "premise check: bare lexical really does disagree here"
    )


# --- item 2: the oracle can go red ------------------------------------------

def test_planted_misordered_trace_is_rejected_by_the_oracle():
    with pytest.raises(AssertionError):
        assert_canonical_identity_order(list(reversed(sorted(SIDS))), SIDS)


def test_planted_duplicate_trace_is_rejected_by_the_oracle():
    dup = sorted(SIDS, key=main._ffa_sort_key)
    with pytest.raises(AssertionError):
        assert_canonical_identity_order(dup + dup[:1], SIDS)


def test_source_mutation_reversing_the_key_is_caught(monkeypatch):
    """Negative control against the SOURCE, not just against a trace.

    The key is REVERSED rather than collapsed to a constant. A constant key
    looks like the more natural mutation, but sorted() is stable, so the binds
    would come out in set-iteration order -- which is hash-randomized for
    strings and coincides with the canonical order often enough that the
    control passes by luck. A control that is green on some runs and red on
    others is worse than no control at all, because the green runs are the
    ones you believe.
    """
    monkeypatch.setattr(
        main, "_ffa_sort_key",
        lambda s: (-len(s or ""), tuple(-ord(c) for c in (s or ""))))
    db = FakeSession()
    given = [SIDS[2], SIDS[0], SIDS[1]]
    run(main._identity_lock_many(db, given))
    monkeypatch.undo()
    binds = db.identity_binds()
    assert binds == list(reversed(sorted(set(given), key=main._ffa_sort_key))), (
        "premise check: the mutated key really did reverse the order"
    )
    with pytest.raises(AssertionError):
        assert_canonical_identity_order(binds, given)


# --- _lock_snapshot_rows ----------------------------------------------------

P1 = "aaaaaaaa-0000-0000-0000-000000000001"
P2 = "bbbbbbbb-0000-0000-0000-000000000002"
LOBBY = "cccccccc-0000-0000-0000-000000000003"


def test_snapshot_locks_parents_before_queue_rows():
    db = FakeSession()
    run(main._lock_snapshot_rows(
        db, "ffa_queue",
        parents=[("ffa_lobbies", LOBBY)],
        player_ids=[P2, P1],
    ))
    trace = db.lock_trace()
    kinds = [t[0] for t in trace]
    assert kinds == ["parent", "queue", "queue"], trace
    assert trace[0][1] == "ffa_lobbies"
    assert [t[2] for t in trace[1:]] == sorted([P1, P2], key=str), (
        "queue rows must be taken in the same global UUID order every caller "
        "uses, or two formations holding different identity subsets still ABBA"
    )


def test_snapshot_never_commits_or_rolls_back():
    """The single most important property. A commit here releases every
    transaction-scoped advisory lock the caller just took."""
    db = FakeSession()
    run(main._lock_snapshot_rows(
        db, "team_queue", parents=[("team_series", LOBBY)], player_ids=[P1]))
    assert db.commits == 0, "a commit here hands the formation back to the race"
    assert db.rollbacks == 0, "rollback is the CALLER's decision, not this helper's"


def test_snapshot_refuses_unknown_tables():
    db = FakeSession()
    with pytest.raises(ValueError):
        run(main._lock_snapshot_rows(db, "players", player_ids=[P1]))
    with pytest.raises(ValueError):
        run(main._lock_snapshot_rows(
            db, "team_queue", parents=[("players", LOBBY)], player_ids=[P1]))


def test_snapshot_parent_allowlist_is_derived_from_the_group_maps():
    for t in main._QUEUE_GROUP_SERIES_TABLES.values():
        assert t in main._QUEUE_PARENT_LOCK_TABLES, t
    for t in main._QUEUE_GROUP_LOBBY_TABLES.values():
        assert t in main._QUEUE_PARENT_LOCK_TABLES, t
    assert "ranked_series" in main._QUEUE_PARENT_LOCK_TABLES


def test_snapshot_with_no_parents_locks_only_queue_rows():
    db = FakeSession()
    run(main._lock_snapshot_rows(db, "ranked_queue", player_ids=[P1, P2]))
    assert [t[0] for t in db.lock_trace()] == ["queue", "queue"]


# --- item 3: the strict lease reader and the three policies -----------------

def test_strict_reader_propagates_where_the_soft_one_swallows():
    """Both readers, same failing session, opposite outcomes. This is the
    #412 polarity split stated as an executable fact."""
    soft = FakeSession(fail_lease_read=True)
    assert run(main._lease_live_mode(soft, P1)) is None, (
        "_lease_live_mode must stay fail-soft -- its callers depend on it"
    )
    strict = FakeSession(fail_lease_read=True)
    with pytest.raises(RuntimeError):
        run(main._lease_live_claim_strict(strict, P1))


def test_strict_reader_returns_mode_and_group():
    db = FakeSession(leases={P1: {"mode": "ffa", "group_id": LOBBY}})
    claim = run(main._lease_live_claim_strict(db, P1))
    assert (claim["mode"], claim["group_id"]) == ("ffa", LOBBY)
    assert run(main._lease_live_claim_strict(db, P2)) is None


MEMBERS = [("76561198040410653", P1), ("76561198709950406", P2)]


def test_fresh_roster_refuses_any_live_lease():
    db = FakeSession(leases={P2: {"mode": "team", "group_id": LOBBY}})
    conflict = run(main._formation_lease_conflict(db, MEMBERS))
    assert conflict == ("76561198709950406", "lease_held_elsewhere")


def test_fresh_roster_admits_a_wholly_unleased_roster():
    db = FakeSession()
    assert run(main._formation_lease_conflict(db, MEMBERS)) is None


def test_hosted_start_accepts_its_own_exact_predecessor():
    """The HIGH that a blanket 'reject any live lease' would have shipped:
    hosted seats already hold a same-mode lobby lease BY DESIGN, so this is
    the case that decides whether every healthy Start keeps working."""
    db = FakeSession(leases={
        P1: {"mode": "ffa", "group_id": LOBBY},
        P2: {"mode": "ffa", "group_id": LOBBY},
    })
    assert run(main._formation_lease_conflict(
        db, MEMBERS, allow=("ffa", LOBBY))) is None


def test_hosted_start_refuses_a_different_lobby():
    other = "dddddddd-0000-0000-0000-000000000004"
    db = FakeSession(leases={P2: {"mode": "ffa", "group_id": other}})
    assert run(main._formation_lease_conflict(
        db, MEMBERS, allow=("ffa", LOBBY))) == ("76561198709950406",
                                                "lease_held_elsewhere")


def test_hosted_start_refuses_the_same_lobby_id_in_another_mode():
    db = FakeSession(leases={P2: {"mode": "team", "group_id": LOBBY}})
    assert run(main._formation_lease_conflict(
        db, MEMBERS, allow=("ffa", LOBBY))) == ("76561198709950406",
                                                "lease_held_elsewhere")


def test_hosted_start_still_admits_a_seat_with_no_lease():
    db = FakeSession(leases={P1: {"mode": "ffa", "group_id": LOBBY}})
    assert run(main._formation_lease_conflict(
        db, MEMBERS, allow=("ffa", LOBBY))) is None


def test_require_refuses_an_expired_predecessor():
    """queue_ready's policy. An absent lease means the pair is already gone;
    proceeding resurrects it and makes it cross-mode eligible again."""
    db = FakeSession(leases={P1: {"mode": "ranked", "group_id": None}})
    assert run(main._formation_lease_conflict(
        db, MEMBERS, allow=("ranked", None), require=True)) == (
            "76561198709950406", "lease_expired")


def test_require_admits_the_exact_live_predecessor_for_every_member():
    db = FakeSession(leases={
        P1: {"mode": "ranked", "group_id": None},
        P2: {"mode": "ranked", "group_id": None},
    })
    assert run(main._formation_lease_conflict(
        db, MEMBERS, allow=("ranked", None), require=True)) is None


def test_the_three_policies_are_distinguishable_by_reason():
    """A guard that returns one undifferentiated refusal cannot be shown to
    implement three different policies (#430: one boolean must not mean two
    things)."""
    expired = FakeSession()
    assert run(main._formation_lease_conflict(
        expired, MEMBERS[:1], allow=("ranked", None), require=True))[1] == "lease_expired"
    elsewhere = FakeSession(leases={P1: {"mode": "team", "group_id": LOBBY}})
    assert run(main._formation_lease_conflict(
        elsewhere, MEMBERS[:1]))[1] == "lease_held_elsewhere"


def test_members_with_no_player_id_are_skipped_not_refused():
    db = FakeSession()
    assert run(main._formation_lease_conflict(
        db, [("76561198040410653", None)])) is None
    assert not any("queue_leases" in s for s in db.statements)


# --- item 1: the phase order, per wired site ------------------------------

import ast as _ast
import io as _io
import inspect as _inspect
import functools as _functools
from sqlalchemy.exc import DBAPIError as _DBAPIError
import re as _re

_IDENTITY = _re.compile(r"_identity_lock_many\(|_ranked_identity_phase\(")
_ROWLOCK = _re.compile(r"_lock_snapshot_rows\(|_lock_queue_rows_ordered\(")
_ENDTXN = _re.compile(r"await db\.(commit|rollback)\(\)")

# Sites wired so far. The remaining ones from A1-BRIEF.md are added here as
# they land, and this list is the record of which are done.
# _lobby_start_common is listed rather than team_lobby_start/ovt_lobby_start:
# the two routes share it, and it is where the locking actually happens, so
# checking the routes would pass trivially and prove nothing.
# v1.41.0 merge pass 4 (c): main's connect-failure landing runs the FFA poll's
# body as _ffa_queue_poll_inner (ffa_queue_poll wraps it and gathers nothing),
# so every FFA gather site below names the body.
WIRED_SITES = ["queue_poll", "queue_ready", "_lobby_start_common",
               "ffa_lobby_start", "team_queue_poll", "ovt_queue_poll",
               "_ffa_queue_poll_inner"]

# The gather paths. A FRESH automatic roster, so the gate must be called with
# no `allow` at all -- the exact mirror of HOSTED_STARTS, and the same one-word
# edit in the other direction: an `allow` here would admit precisely the
# double booking A1 exists to refuse.
# queue_poll LEFT this list in A1 r2: it now carries a second gate, at room
# issuance, with a different policy. A handler with two policies belongs in a
# test that pins both -- see test_ranked_poll_gates_its_two_branches_
# differently -- not in one that counts to one.
FRESH_ROSTER_SITES = ["ovt_queue_poll", "_ffa_queue_poll_inner"]

# The two hosted-Start paths and the `allow` expression each must pass.
HOSTED_STARTS = {
    "_lobby_start_common": 'allow=(cfg["lease"], lobby_id)',
    "ffa_lobby_start": 'allow=("ffa", lobby_id)',
}


def phase_order_violations(src):
    """Walk a handler's source in order and return every row lock that is not
    covered by an identity acquisition taken since the last commit/rollback.

    This is a SOURCE-order walk, not an execution trace, and that limit is
    worth stating: it is meaningful for these handlers because each is a
    linear sequence of guarded blocks, and the one construct that revisits a
    lock -- the poll's pair-inversion loop -- commits before re-locking, so the
    walk sees the same clear/re-acquire the runtime does. What it CAN catch is
    the mistake that matters: a row lock reachable with no identity acquired
    since the transaction last ended.
    """
    events = []
    for m in _IDENTITY.finditer(src):
        events.append((m.start(), "identity"))
    for m in _ROWLOCK.finditer(src):
        events.append((m.start(), "rowlock"))
    for m in _ENDTXN.finditer(src):
        events.append((m.start(), "endtxn"))
    events.sort()

    held = False
    bad = []
    for pos, kind in events:
        if kind == "identity":
            held = True
        elif kind == "endtxn":
            held = False
        elif kind == "rowlock" and not held:
            bad.append(src[:pos].count("\n") + 1)
    return bad


@pytest.mark.parametrize("site", WIRED_SITES)
def test_every_row_lock_is_behind_an_identity_acquisition(site):
    src = _inspect.getsource(getattr(main, site))
    bad = phase_order_violations(src)
    assert bad == [], (
        f"{site}: row lock(s) at handler-relative line(s) {bad} are reachable "
        f"with no identity held since the last commit/rollback. A row taken "
        f"before its identity is the ABBA this change removes."
    )


def test_the_poll_reacquires_after_the_inversion_loop_commit():
    """The specific trap: the pair-inversion loop commits deliberately to
    release a mis-ordered row set, which also releases the advisory locks.
    Re-locking there without re-taking identities would leave the barrier
    behind."""
    src = _inspect.getsource(main.queue_poll)
    assert src.count("_ranked_identity_phase(") == 2, (
        "expected exactly two identity acquisitions in the poll: one before "
        "the first row lock, one after the inversion loop's commit"
    )


def test_the_formation_loop_is_bounded_and_rolls_back_rather_than_commits():
    src = _inspect.getsource(main.queue_poll)
    assert "for _form_attempt in range(1, FORMATION_MAX_ATTEMPTS + 1):" in src
    assert 'raise HTTPException(status_code=503, detail="queue_contended")' in src
    # every drift/conflict exit inside the loop rolls back; a commit there
    # would publish a half-formation and release the barrier
    loop = src[src.index("for _form_attempt"):src.index("    # No match yet")]
    assert loop.count("await db.rollback()") == 3, (
        "the two in-loop drift/conflict exits and the exhausted-attempts exit "
        "must all roll back"
    )


@pytest.mark.parametrize("site,allow_expr", sorted(HOSTED_STARTS.items()))
def test_hosted_start_passes_allow_and_never_a_bare_gate(site, allow_expr):
    """The single highest-consequence parameter in A1. Hosted seats hold a
    same-mode lobby lease by design, so a gate called WITHOUT `allow` — or with
    allow=None — refuses every healthy 2v2, 1v2 and FFA Start in the game.
    That is an outage, not a race, and it is a one-word edit away at all
    times."""
    src = _inspect.getsource(getattr(main, site))
    assert "_formation_lease_conflict(" in src, (
        f"{site} lost its lease gate entirely"
    )
    assert allow_expr in src, (
        f"{site} must allow its OWN (mode, lobby) predecessor; a bare gate "
        f"here refuses every healthy Start"
    )
    assert "require=True" not in src, (
        f"{site} must still admit a seat with no lease -- requiring one would "
        f"refuse a lobby whose members' leases lapsed while it filled"
    )
    # and it runs on the pruned roster, after the count decides
    gate = src.index("_formation_lease_conflict(")
    assert src.index("banned") < gate, f"{site}: gate must follow the banned prune"


@pytest.mark.parametrize("site,live_reader", [
    ("_lobby_start_common", "_lobby_live_members("),
    ("ffa_lobby_start", "_ffa_live_lobby_members("),
])
def test_lobby_start_gates_the_full_footprint_not_just_live_members(site, live_reader):
    """Codex HIGH: the row lock and the prune touch EVERY physical row
    pointing at the lobby, while the live-member readers filter by status and
    freshness. Gating only the live members leaves rows this transaction
    writes outside the barrier."""
    src = _inspect.getsource(getattr(main, site))
    disc = src.index("_identity_lock_many(")
    live = src.index(live_reader)
    assert disc < live, (
        f"{site}: the barrier must be taken from the raw roster discovery, "
        f"BEFORE the filtered live-member read"
    )
    assert "WHERE series_id = :lid" in src[:disc], (
        f"{site}: the identity phase must be fed by an unfiltered roster read"
    )


@pytest.mark.parametrize("site", sorted(HOSTED_STARTS))
def test_hosted_start_no_longer_uses_the_committing_group_helper(site):
    """Option (a)'s exact failure: that helper commits on a missing row and on
    a failed membership re-check, and a commit releases every advisory lock the
    barrier just took."""
    src = _inspect.getsource(getattr(main, site))
    assert "_lock_queue_group_for_player(" not in src, (
        f"{site} is back on the committing group helper; the barrier it takes "
        f"would be released inside that call"
    )


def test_phase_order_oracle_rejects_a_planted_violation():
    """Negative control for the oracle itself."""
    planted = (
        "async def f(db):\n"
        "    await db.commit()\n"
        "    await _lock_snapshot_rows(db, 't', player_ids=[1])\n"
        "    await _identity_lock_many(db, ['x'])\n"
    )
    assert phase_order_violations(planted) != []


def test_phase_order_oracle_accepts_the_correct_shape():
    ok = (
        "async def f(db):\n"
        "    await db.commit()\n"
        "    await _identity_lock_many(db, ['x'])\n"
        "    await _lock_snapshot_rows(db, 't', player_ids=[1])\n"
    )
    assert phase_order_violations(ok) == []


def test_phase_order_oracle_notices_a_commit_between_identity_and_rows():
    """The exact failure mode of option (a): a helper that commits between the
    barrier and the row locks releases the barrier."""
    leaky = (
        "async def f(db):\n"
        "    await _identity_lock_many(db, ['x'])\n"
        "    await db.commit()\n"
        "    await _lock_snapshot_rows(db, 't', player_ids=[1])\n"
    )
    assert phase_order_violations(leaky) != []


def _gate_calls(src):
    """Every _formation_lease_conflict(...) call in `src`, returned whole.

    Paren-matched rather than regex'd: team_queue_poll has TWO gates with
    different policies, and a substring test over the whole handler would let
    the sticky branch's `allow` vouch for the fresh branch (#432 -- a flag
    names a line, the defect is a class).
    """
    out = []
    marker = "_formation_lease_conflict("
    i = src.find(marker)
    while i != -1:
        j = i + len(marker)
        depth = 1
        while depth:
            if src[j] == "(":
                depth += 1
            elif src[j] == ")":
                depth -= 1
            j += 1
        out.append(src[i:j])
        i = src.find(marker, j)
    return out


def test_gate_call_splitter_separates_two_calls():
    """Negative control for the splitter: a handler carrying one gate WITH
    allow and one without must not read as either."""
    NL = chr(10)
    planted = NL.join([
        "await _formation_lease_conflict(db, a, allow=(1, 2))",
        "await _formation_lease_conflict(db, b)",
    ])
    calls = _gate_calls(planted)
    assert len(calls) == 2
    assert "allow=" in calls[0] and "allow=" not in calls[1]


@pytest.mark.parametrize("site", FRESH_ROSTER_SITES)
def test_fresh_roster_gate_carries_no_allow(site):
    calls = _gate_calls(_inspect.getsource(getattr(main, site)))
    assert len(calls) == 1, (site, len(calls))
    assert "allow=" not in calls[0], (
        f"{site} forms a fresh roster -- any live lease on any seat is the "
        f"double lock, so there is no predecessor to allow")
    assert "require=" not in calls[0], (
        f"{site} must not REQUIRE a lease either: a fresh roster has none")


def test_ranked_poll_gates_its_two_branches_differently():
    """A1 r2. queue_poll carries two gates now and they cannot share one
    policy, exactly as team_queue_poll's two branches cannot.

    DISCOVERY forms a fresh pair, so no seat may hold ANY live lease. r2
    briefly admitted a group-less (ranked, None) one here and that was wrong:
    queue_join takes no lease, so (ranked, None) means MATCHED-pre-room and is
    stale once the pair dissolves. The dissolution releases it instead, which
    also unblocks the 2v2/1v2/FFA formations that were refusing the same seat
    for the rest of the 210-second remainder.

    ROOM ISSUANCE is the opposite shape: the pair is already committed to
    itself, and its own history is two-valued -- (ranked, None) on the pass
    that issues the room, (ranked, series.id) on every replay of that branch.
    Both are its own predecessor; anything else is the double booking."""
    calls = _gate_calls(_inspect.getsource(main.queue_poll))
    assert len(calls) == 2, len(calls)
    # Picked by CONTENT, not position. The matched branch is written above the
    # searching branch, so textual order is the reverse of flow order and a
    # positional unpack reads as the wrong policy for each -- silently, and in
    # the direction that would call the strict gate lax.
    flat = ["".join(c.split()) for c in calls]
    _disc = [c for c in flat if "cand[" in c]
    _iss = [c for c in flat if "series.id" in c]
    assert len(_disc) == 1 and len(_iss) == 1, flat
    discovery, issuance = _disc[0], _iss[0]

    assert "allow" not in discovery, (
        "discovery forms a fresh pair -- it supersedes no predecessor; a "
        "stale one is released at the dissolution, not admitted here")
    assert "require=" not in discovery, (
        "a fresh pair has no lease to REQUIRE")

    assert issuance.count('(("ranked",None),("ranked",series.id))') == 1, issuance
    assert "require=" not in issuance, (
        "today the polling lease has usually lapsed by issuance; requiring "
        "it would refuse the match it is meant to fence")

def test_team_poll_gates_its_three_branches_differently():
    """Codex HIGH: team must choose sticky-resume vs fresh formation during
    unlocked discovery, and the branches cannot share one lease policy.

    STICKY resume: the four legitimately still hold the lease of a series in
    THIS QUARTET'S live family -- that is what makes the path a resume -- and
    require stays off, because a lease that lapsed during a long disconnect is
    the case a resume exists to recover. The admissible set is the family and
    not the trigger row (r1 :38443); see the single-sourcing test below.
    FRESH formation: a fresh four must hold nothing at all.
    ACTIVATION (r2, review HIGH :38186): issuing the 2v2 room commits the four
    to a live game, and it is the one team branch that REQUIRES the predecessor.
    The room is issued within TEAM_READY_TIMEOUT_SECONDS of a match that leased
    for LEASE_TTL_ASSEMBLY, and nothing renews it on the matched path, so all
    four share one expiry and every healthy case still holds it.

    Picked by CONTENT, not position: activation is written ABOVE discovery in
    the handler, so a positional unpack reads each policy as another branch's."""
    calls = _gate_calls(_inspect.getsource(main.team_queue_poll))
    assert len(calls) == 3, len(calls)
    sticky = [c for c in calls if "_fam_ids" in c]
    activation = [c for c in calls if "all_4" in c]
    fresh = [c for c in calls if c not in sticky + activation]
    assert len(sticky) == 1 and len(activation) == 1 and len(fresh) == 1, calls
    sticky, activation, fresh = sticky[0], activation[0], fresh[0]

    assert 'allow_any=[("team", _f) for _f in _fam_ids]' in (
        " ".join(sticky.split())), sticky
    assert "allow=" not in sticky, (
        "the admissible set is the whole live family, not the one row the "
        "unlocked trigger read happened to name")
    assert "require=True" not in sticky, (
        "a resume must still admit a seat whose lease lapsed during the DC")

    assert "allow" not in fresh, fresh
    assert "require" not in fresh, fresh

    assert 'allow=("team", me["series_id"])' in " ".join(activation.split()), activation
    assert "require=True" in activation, (
        "activation is the branch that must REQUIRE the live predecessor")

def test_the_sticky_resume_and_its_authority_read_one_family_predicate():
    """r1 :38443. The sticky gate's admissible set and the authority that
    picks the series to resume must enumerate the SAME live family.

    dc_row comes from the unlocked trigger read at the top of the handler,
    which takes the NEWEST row under a narrower predicate (dc_paused inside its
    grace, or dc_incomplete flagged dc_manual_pending). _team_lock_family_pick
    ranks the whole family by played progress and can name a different row —
    and it is that row the four already hold, because
    _team_relock_existing_series is what leased them. Allowing only the trigger
    row therefore refused legitimate resumes, saying "committed elsewhere"
    about the series the handler was resuming them onto.

    Single-sourced rather than merely equal today: two hand-copied predicates
    are how a pre-check and its authority drift apart, so the check is that
    the text exists exactly once and both readers name it."""
    fam_sql = main._TEAM_LIVE_FAMILY_IDS_SQL
    assert "FROM team_series ts" in fam_sql
    assert "status IN ('active', 'dc_paused', 'dc_incomplete')" in fam_sql
    whole = _io.open(_inspect.getsourcefile(main),
                     encoding="utf-8", newline="").read()
    assert whole.count("SELECT ts.id FROM team_series ts") == 1, (
        "the family predicate has been hand-copied somewhere; the gate "
        "and its authority must read one text")
    for site in ("team_queue_poll", "_team_lock_family_pick"):
        assert "_TEAM_LIVE_FAMILY_IDS_SQL" in _inspect.getsource(
            getattr(main, site)), site


def test_a_committed_peer_ends_the_resume_instead_of_rediscovering():
    """r1 :38448. A live lease held by one of the four is COMMITTED state
    — _lease_live_claim_strict reads committed rows — so re-running the
    unlocked consent read inside one poll cannot change the answer. `continue`
    therefore spent the whole budget on a fixed conflict and returned 503
    queue_contended about a seat that is not contended at all, merely playing
    elsewhere. The honest disposition is to stop resuming and let fresh
    formation run, which is what the caller's own commitment already did.

    The FRESH branch's refusal is asserted to still rediscover, in the same
    test: a fresh candidate scan genuinely can turn up different people, so the
    two dispositions are different on purpose and neither may be flattened
    into the other by someone tidying them up."""
    tree = _ast.parse(_inspect.getsource(main.team_queue_poll))
    blocks = [n for n in _ast.walk(tree)
              if isinstance(n, _ast.If)
              and _ast.unparse(n.test) == "_lease_bad is not None"]
    assert len(blocks) == 2, len(blocks)
    sticky = [b for b in blocks
              if "resume unavailable" in _ast.unparse(b)]
    assert len(sticky) == 1, [_ast.unparse(b)[:80] for b in blocks]
    fresh = [b for b in blocks if b is not sticky[0]]

    assert isinstance(sticky[0].body[-1], _ast.Break), _ast.unparse(sticky[0])
    assert not any(isinstance(n, _ast.Continue)
                   for n in _ast.walk(sticky[0])), (
        "a committed peer is a fixed answer inside one poll; "
        "rediscovering it burns the budget into a false 503")
    assert any(isinstance(n, _ast.Continue)
               for n in _ast.walk(fresh[0])), (
        "a fresh candidate scan CAN turn up different people on "
        "rediscovery, so its peer refusal is the one that retries")


# How many times each handler EXECUTES its predicate. Two is discovery plus
# revalidation; the FFA gather runs a third, its post-drift rediscovery, which
# re-elects the decider because the decider is a property of the roster.
@pytest.mark.parametrize("site,const,runs", [
    ("queue_poll", "_RANKED_CANDIDATE_SQL", 2),
    ("ovt_queue_poll", "_OVT_CANDIDATE_SQL", 2),
    ("_ffa_queue_poll_inner", "_FFA_CANDIDATE_SQL", 3),
])
def test_gather_predicates_are_one_statement_run_more_than_once(site, const, runs):
    src = _inspect.getsource(getattr(main, site))
    # count EXECUTIONS, not mentions -- the comments name the constant too
    assert src.count("text(" + const + ")") == runs, (
        f"{site} must run {const} exactly {runs} times; a revalidation that is "
        f"not the same test the discovery made proves nothing (#330)")
    sql = getattr(main, const)
    assert "FOR UPDATE" not in sql and "SKIP LOCKED" not in sql, (
        f"{const} still locks while it discovers -- that takes rows whose "
        f"identities the caller does not hold")
    assert ":only" in sql


def test_team_predicate_is_one_template_built_once():
    src = _inspect.getsource(main.team_queue_poll)
    assert src.count("_TEAM_CANDIDATE_SQL_TMPL.format(") == 1
    # Built once, then RUN twice: discovery and revalidation. Count
    # EXECUTIONS and the single binding, never total mentions -- the
    # comments name it too, which is the trap the gather-predicate test
    # above already carries in its own body.
    assert src.count("_cand_sql = ") == 1, src.count("_cand_sql = ")
    assert src.count("text(_cand_sql)") == 2, src.count("text(_cand_sql)")
    assert src.count("_TEAM_RESUME_CONSENT_SQL") == 2
    for name in ("_TEAM_CANDIDATE_SQL_TMPL", "_TEAM_RESUME_CONSENT_SQL"):
        sql = getattr(main, name)
        assert "FOR UPDATE" not in sql and "SKIP LOCKED" not in sql, name
        assert ":only" in sql, name


@pytest.mark.parametrize("const", ["_OVT_CANDIDATE_SQL", "_FFA_CANDIDATE_SQL",
                                   "_TEAM_CANDIDATE_SQL_TMPL"])
def test_fresh_predicates_exclude_an_already_committed_seat(const):
    """The gate alone would head-of-line block: one leased row at the front of
    the queue would fail every formation attempt until its lease lapsed, and
    the whole pool behind it would sit there. Excluding it at DISCOVERY keeps
    the pool moving and leaves the gate to catch only a claim made after."""
    sql = getattr(main, const)
    assert "FROM queue_leases ql" in sql, const
    assert "ql.expires_at > clock_timestamp()" in sql, const


def test_the_resume_predicate_is_deliberately_not_lease_filtered():
    """The four resuming a DC'd series still hold that series' lease -- that is
    what makes it a resume. Filtering them out at discovery would refuse every
    healthy resume; the sticky `allow` is what handles them instead."""
    assert "queue_leases" not in main._TEAM_RESUME_CONSENT_SQL


def test_ffa_rediscovery_re_elects_the_decider():
    """The decider is a property of the ROSTER (the ovt review HIGH: a lower-ID
    4th player who elects itself over a lobby it is not in locks a room for
    the other three and strands itself in it). The post-drift rediscovery
    therefore has to re-run the election, not reuse the old winner.

    Counted rather than grepped for presence: three uses is the election, the
    re-election and the slot ordering, so dropping any one of them fails here
    instead of passing on the other two (#432)."""
    src = _inspect.getsource(main._ffa_queue_poll_inner)
    assert src.count("_ffa_sort_key") == 3, src.count("_ffa_sort_key")


def _attempt_budgets(fn_src):
    """(budget openings, counter names, while-loops) in one handler's source.

    A budget is OPENED either by a `for` over range(1, FORMATION_MAX_ATTEMPTS
    + 1) or by binding a name straight from the constant. Structure rather
    than text, because what is being measured is how many INDEPENDENT budgets
    one poll gets, and the defect was two `for` loops that each read
    perfectly well on their own line."""
    tree = _ast.parse(fn_src)
    openings, counters, loops = [], set(), []
    for node in _ast.walk(tree):
        if isinstance(node, _ast.For) and (
                "FORMATION_MAX_ATTEMPTS" in _ast.unparse(node.iter)):
            openings.append(_ast.unparse(node.iter))
        elif isinstance(node, _ast.Assign) and (
                _ast.unparse(node.value) == "FORMATION_MAX_ATTEMPTS"):
            for t in node.targets:
                if isinstance(t, _ast.Name):
                    openings.append(_ast.unparse(node))
                    counters.add(t.id)
        elif isinstance(node, _ast.While):
            loops.append(node)
    return openings, counters, loops


@pytest.mark.parametrize("site", ["ovt_queue_poll", "_ffa_queue_poll_inner",
                                  "team_queue_poll"])
def test_gather_loops_are_bounded_and_end_in_a_refusal(site):
    """Bounded on purpose: identity locks stabilise only the identities
    already discovered, so a rediscovery can always turn up a new contender
    and an unbounded loop is a real possibility, not a theoretical one.

    ONE budget per poll (r1 :38500). team_queue_poll opened a SECOND
    range(1, FORMATION_MAX_ATTEMPTS + 1) for its fresh phase after the sticky
    phase had spent the first, so one poll could take and release the
    identity+snapshot lock set six times — twice the bound the constant
    names, doubled at exactly the moment the bound exists for. Counting the
    openings is what catches that; each loop read correctly in isolation.

    A `while` that spends a shared counter is bounded only if its body
    decrements that counter, and only if the decrement is the FIRST statement
    — a `continue` above it would never terminate. Checked structurally,
    because a grep for the word `while` cannot tell those two apart."""
    src = _inspect.getsource(getattr(main, site))
    openings, counters, loops = _attempt_budgets(src)
    assert len(openings) == 1, (site, openings)
    for node in loops:
        test_src = _ast.unparse(node.test)
        if not any(c in test_src for c in counters):
            continue                    # not a formation loop
        assert (isinstance(node.test, _ast.Compare)
                and isinstance(node.test.left, _ast.Name)), (site, test_src)
        first = node.body[0]
        assert (isinstance(first, _ast.AugAssign)
                and isinstance(first.op, _ast.Sub)
                and isinstance(first.target, _ast.Name)
                and first.target.id == node.test.left.id), (
            f"{site}: `while {test_src}` must spend its budget as its first "
            f"statement, or a `continue` above the decrement never ends")
    assert 'raise HTTPException(status_code=503, detail="queue_contended")' in src, site


@pytest.mark.parametrize("site", ["ovt_queue_poll", "_ffa_queue_poll_inner"])
def test_gather_drift_rolls_back_and_never_commits(site):
    """A commit inside the formation loop would publish a half-formation AND
    release the barrier -- option (a)'s failure, reached from inside the retry
    instead of from a helper."""
    src = _inspect.getsource(getattr(main, site))
    loop = src[src.index("for _form_attempt"):]
    loop = loop[:loop.index("await _lease_acquire_many(")]
    assert "await db.commit()" not in loop, (
        f"{site}: the formation loop commits somewhere between the barrier and "
        f"the lease acquisition")
    assert loop.count("await db.rollback()") >= 3, (
        f"{site}: the drift exit, the lease-conflict exit and the exhausted "
        f"-attempts exit must all roll back")


def _gate_calls_inside_a_swallowing_scope(src):
    """Handler-relative lines where a _formation_lease_conflict call sits
    inside a `try:` or an `async with db.begin_nested():`.

    An AST walk rather than a text search, because the thing being looked for
    is CONTAINMENT, and indentation-by-substring gets that wrong on exactly the
    nested cases that matter.
    """
    tree = _ast.parse(src)
    bad = []

    class V(_ast.NodeVisitor):
        def __init__(self):
            self.depth = 0

        def _guarded(self, node):
            self.depth += 1
            self.generic_visit(node)
            self.depth -= 1

        def visit_Try(self, node):
            self._guarded(node)

        def visit_AsyncWith(self, node):
            if "begin_nested" in _ast.dump(node):
                self._guarded(node)
            else:
                self.generic_visit(node)

        def visit_Call(self, node):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name == "_formation_lease_conflict" and self.depth:
                bad.append(node.lineno)
            self.generic_visit(node)

    V().visit(tree)
    return bad


def test_the_swallowing_scope_detector_can_fail():
    """Negative control for the detector, both directions."""
    NL = chr(10)
    planted = NL.join([
        "async def f(db):",
        "    try:",
        "        await _formation_lease_conflict(db, [])",
        "    except Exception:",
        "        pass",
    ])
    assert _gate_calls_inside_a_swallowing_scope(planted) != []
    ok = NL.join([
        "async def f(db):",
        "    await _formation_lease_conflict(db, [])",
    ])
    assert _gate_calls_inside_a_swallowing_scope(ok) == []


@pytest.mark.parametrize("site", WIRED_SITES)
def test_the_lease_gate_is_never_wrapped_in_a_swallowing_scope(site):
    """Acceptance item 3, the source half. A strict reader is only strict if
    nothing catches it: _lease_live_claim_strict has no savepoint and no catch
    ON PURPOSE, and wrapping the gate at the CALL site puts the #412 polarity
    error straight back. It is also precisely the edit someone reaches for to
    'fix' a 500 coming out of a lease read."""
    bad = _gate_calls_inside_a_swallowing_scope(
        _inspect.getsource(getattr(main, site)))
    assert bad == [], (
        f"{site}: the lease gate at handler-relative line(s) {bad} is inside a "
        f"try/except or a savepoint, so a lease-read fault would be swallowed "
        f"and the formation would commit anyway")


# ── Round 2: the commitment-point set is DERIVED, never enumerated ──────────
#
# Round 1 of the review returned five HIGHs that were all the same mistake: A1
# gated eight sites hand-listed from the brief, and there are more places that
# commit a player to a game than that list knew about (the ranked both-ready
# republish, queue_ready's stamped-room replay, team's all_ready activation,
# and both series continuations). Adding five names to WIRED_SITES would repeat
# the error rather than fix it, so the set is derived from the code instead.
#
# The invariant that derives it, and the whole of A1 in one sentence: a
# transaction may not acquire a formation lease without having proved, in that
# same transaction, that no conflicting live claim exists. `_lease_acquire` /
# `_lease_acquire_many` IS the commitment -- every call site of either is a
# commitment point by definition, whether or not anyone remembered to list it.
#
# The walk is interprocedural because the code is: team_lobby_start and
# ovt_lobby_start acquire in their OWN bodies (:44861, :44990) while the gate
# that covers them lives in _lobby_start_common, which they call. A per-function
# pass calls those two ungated and is simply wrong, which is the kind of
# false positive that gets a test deleted rather than fixed.

_ACQUIRE = _re.compile(r"await\s+_lease_acquire(_many)?\(")
_GATE = _re.compile(r"await\s+_formation_lease_conflict\(")

# Acquisitions that are deliberately NOT formations, with the reason. An entry
# here is a claim that has to be argued, not a way to quiet the oracle; the
# test asserts every name still exists, so a stale exemption fails loudly
# instead of silently widening.
_NOT_A_FORMATION = {
    "_lease_acquire": "the primitive itself",
    "_lease_acquire_many": "the primitive itself",
}


_CALL_NAME = _re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")


# Memoised: main.py cannot change mid-run, and this suite ALREADY depends
# on that (#676 -- a mid-run edit makes inspect.getsource return another
# function's body and the failures look real), so the cache makes an
# assumption the file already relies on explicit rather than adding a new
# one. Without it every caller re-parses a 3 MB, 57k-line file from disk.
@_functools.lru_cache(maxsize=None)
def _main_tree():
    return _ast.parse(_io.open(_inspect.getsourcefile(main),
                               encoding="utf-8", newline="").read())


@_functools.lru_cache(maxsize=None)
def _function_spans():
    """{name: (first line, last line)} for every def in main.py."""
    out = {}
    for node in _ast.walk(_main_tree()):
        if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            out.setdefault(node.name, (node.lineno, node.end_lineno))
    return out


def _body_lines(name, spans, lines):
    a, b = spans[name]
    return [(i + 1, lines[i]) for i in range(a, min(b, len(lines)))
            if not lines[i].lstrip().startswith("#")]


@_functools.lru_cache(maxsize=None)
def commitment_points():
    """(acquirers, gaters) over main.py, gaters closed under calls.

    A function GATES if it calls _formation_lease_conflict itself, or calls
    another function in main.py that gates. The closure is a fixpoint so the
    depth of the indirection does not matter; today it is one level.
    """
    src = _io.open(_inspect.getsourcefile(main), encoding="utf-8",
                   newline="").read()
    lines = src.split("\n")
    spans = _function_spans()
    acquirers, gaters, calls = {}, set(), {}
    for name in spans:
        body = _body_lines(name, spans, lines)
        for n, ln in body:
            if _ACQUIRE.search(ln):
                acquirers.setdefault(name, []).append(n)
            if _GATE.search(ln):
                gaters.add(name)
        # Was: for every span, scan the body once per OTHER span. At 966
        # spans that is ~933k regex searches, each one re-joining the body
        # string inside the comprehension -- minutes per call. One findall
        # of 'identifier followed by (' intersected with the span names
        # asks the same question once, and every name the old pattern could
        # match is an identifier this one captures.
        body_src = "\n".join(l for _n, l in body)
        calls[name] = {m for m in _CALL_NAME.findall(body_src)
                       if m != name and m in spans}
    grew = True
    while grew:
        grew = False
        for name, callees in calls.items():
            if name not in gaters and (callees & gaters):
                gaters.add(name)
                grew = True
    return acquirers, gaters, spans


def test_the_commitment_oracle_can_fail():
    """Negative control (#391). A derivation that cannot come back non-empty
    proves nothing, so plant an acquirer that nothing gates and require the
    oracle to name it."""
    acquirers, gaters, _spans = commitment_points()
    assert acquirers, "no _lease_acquire call sites found -- the regex is stale"
    planted = dict(acquirers, _planted_ungated_acquirer=[0])
    ungated = [n for n in planted
               if n not in gaters and n not in _NOT_A_FORMATION]
    assert "_planted_ungated_acquirer" in ungated


def test_every_exemption_still_names_a_real_function():
    """A stale exemption is how an oracle stops measuring: the function gets
    renamed, the entry keeps excusing a name nothing uses, and the real site
    walks in behind it."""
    spans = _function_spans()
    for name in _NOT_A_FORMATION:
        assert name in spans, (name, "exempted but no longer exists")


# A function may also be gated by its CALLER rather than by itself or a
# callee -- the closure above only runs callee -> caller, so it cannot see
# that shape. Each entry is a CLAIM ('this acquirer's only caller in main.py
# gates before calling it'), and the test below is its proof: it re-derives
# the caller set from the source and fails the moment a second caller
# appears, which is exactly when the delegation stops being true.
_GATED_BY_SOLE_CALLER = {
    "_team_relock_existing_series": "_team_resolve_live_family",
}

# The same claim for an acquirer with MORE than one caller (v1.41.0 merge pass
# 4 (c)): main's connect-failure rework moved the FFA lock's lease acquisition
# into _ffa_lock_roster, which the hosted Start and the assembly's REFORM both
# call. The proof below re-derives the caller set, requires it to be exactly
# the claimed one, and requires each caller to run a gate BEFORE its first call.
_GATED_BY_EVERY_CALLER = {
    "_ffa_lock_roster": frozenset({"ffa_lobby_start", "_asm_reform"}),
}


def _callers_of(name, spans, lines):
    """Every function in main.py whose body calls `name`."""
    pat = _re.compile(r"\b" + _re.escape(name) + r"\s*\(")
    out = set()
    for other in spans:
        if other == name:
            continue
        if any(pat.search(l) for _n, l in _body_lines(other, spans, lines)):
            out.add(other)
    return out


def test_every_sole_caller_delegation_is_still_sole_and_still_gates():
    """The proof behind _GATED_BY_SOLE_CALLER. Two things have to hold:
    the named caller is the ONLY caller in main.py, and it gates. Either one
    failing means an acquisition runs with nothing in front of it, which is
    the whole defect this batch exists to remove."""
    _acquirers, gaters, spans = commitment_points()
    src = _io.open(_inspect.getsourcefile(main), encoding="utf-8",
                   newline="").read()
    lines = src.split(chr(10))
    for name, claimed in _GATED_BY_SOLE_CALLER.items():
        assert name in spans, (
            name, "delegation claimed but the function is gone")
        callers = _callers_of(name, spans, lines)
        assert callers == {claimed}, (
            name, "claims one gating caller; main.py has", callers)
        assert claimed in gaters, (
            claimed, "is the claimed gate but does not gate")


def test_every_caller_delegation_names_every_caller_and_each_gates_first():
    """The proof behind _GATED_BY_EVERY_CALLER (v1.41.0 merge pass 4 (c)).
    The derived caller set must equal the claim (a new caller fails here
    until it is argued in), and in each caller the first gate line must come
    before the first call, or the acquisition runs on an unproved roster."""
    _acquirers, _gaters, spans = commitment_points()
    src = _io.open(_inspect.getsourcefile(main), encoding="utf-8",
                   newline="").read()
    lines = src.split(chr(10))
    for name, claimed in _GATED_BY_EVERY_CALLER.items():
        assert name in spans, (
            name, "delegation claimed but the function is gone")
        callers = _callers_of(name, spans, lines)
        assert callers == set(claimed), (
            name, "claims these gating callers; main.py has", callers)
        pat = _re.compile(r"\b" + _re.escape(name) + r"\s*\(")
        for caller in sorted(claimed):
            body = _body_lines(caller, spans, lines)
            gates = [n for n, ln in body if _GATE.search(ln)]
            calls = [n for n, ln in body if pat.search(ln)]
            assert gates and calls and min(gates) < min(calls), (
                caller, "must gate before it calls", name, gates, calls)


def test_every_lease_acquisition_is_gated_in_its_own_transaction():
    """THE round-2 acceptance test, and the one that defines the batch's scope.

    Every _lease_acquire* call site must sit in a transaction that has already
    proved no conflicting live claim. Derived, not listed -- see the block
    comment above for why the list was the bug.
    """
    acquirers, gaters, spans = commitment_points()
    ungated = sorted(n for n in acquirers
                     if n not in gaters and n not in _NOT_A_FORMATION
                     and n not in _GATED_BY_SOLE_CALLER
                     and n not in _GATED_BY_EVERY_CALLER)
    assert not ungated, (
        "these acquire a formation lease with nothing proving the seat is "
        "free:\n" + "\n".join(
            f"  {n} (acquires at {acquirers[n]}, def line {spans[n][0]})"
            for n in ungated))


def test_a_gate_precedes_the_acquisition_it_covers():
    """Gating somewhere in the function is not enough -- the proof has to come
    BEFORE the commitment. queue_ready is the reason this is its own test: its
    gate and its reacquisition both sit inside `if not room_name:`, so a replay
    that already has a stamped room reaches neither (round-1 HIGH, :16902)."""
    src = _io.open(_inspect.getsourcefile(main), encoding="utf-8",
                   newline="").read()
    lines = src.split("\n")
    acquirers, _gaters, spans = commitment_points()
    late = []
    for name in acquirers:
        if name in _NOT_A_FORMATION:
            continue
        body = _body_lines(name, spans, lines)
        gates = [n for n, ln in body if _GATE.search(ln)]
        if not gates:
            continue          # covered by the derived test above
        first_acq = min(acquirers[name])
        if min(gates) > first_acq:
            late.append((name, min(gates), first_acq))
    assert not late, (
        "the gate runs AFTER the lease it is supposed to authorise:\n"
        + "\n".join(f"  {n}: gate@{g}, acquire@{a}" for n, g, a in late))


# ── Round 2: a reset to 'searching' must release the lease that fenced it ───
#
# Review r1 found this at three sites and it is one class: a dissolution puts
# survivors back to `status='searching'` and leaves their (mode, group) lease
# in queue_leases. Before A1 that was inert -- nothing consulted leases when a
# roster formed. A1's discovery-side lease exclusion is what made it bite: a
# survivor reset to 'searching' while still holding a lease is invisible to
# every matcher until the TTL lapses or the janitor sweeps, so a correctness
# fix introduced a stall. The fix belongs in the same transaction as the reset,
# and this test is what keeps it there.
#
# Derived over the file rather than listed, for the same reason the commitment
# oracle is: the three sites review r1 happened to name are not the definition.

_RESET = _re.compile(r"SET status\s*=\s*'searching'")
_RELEASE = _re.compile(r"queue_leases|_lease_release")


# Resets that must NOT release anything, with the reason each is safe. These
# are husk clearances: each is guarded by `_lease_live_mode(...) is None`, i.e.
# it only runs once the lease has ALREADY expired, so there is nothing to
# release and a DELETE would be noise. The test proves the guard is really
# there rather than taking the name on trust.
_RESET_NO_LEASE = {
    "ovt_queue_join": "husk clearance, guarded by an already-expired lease",
    "ffa_queue_join": "husk clearance, guarded by an already-expired lease",
    "_lobby_enroll_caller": "husk clearance, guarded by an already-expired lease",
    "_ffa_lobby_enroll_caller": "husk clearance, guarded by an already-expired lease",
    # The two ranked reset helpers were briefly exempted here on the theory
    # that their lease had to survive. It does not: queue_join takes no lease,
    # so (ranked, NULL) means MATCHED-pre-room and is stale the moment the
    # pair dissolves. They release now and are held to the rule like the rest.
    # Widening the pattern to the spaced `SET status = ` spelling is what made
    # them visible at all.
    "_evict_other_queue_searching": (
        "1v1 eviction sweep: ranked_queue rows carry no group lease to fence"),
    "delete_player_data": (
        "the account is being erased; its queue_leases rows go with it"),
}


# A reset and the release of the lease it fenced must sit in ONE transaction.
# That is the invariant, so it is what gets measured: the enclosing function,
# bounded by the nearest commit or rollback on either side. The first version
# used a +/- 20 line window, which is only a proxy for it -- and a proxy that
# broke the moment a release grew a comment above it, while still counting a
# release on the far side of a commit.
_TXN_BOUNDARY = _re.compile(r"await db\.(commit|rollback)\(\)")


def _owner_index():
    """line number -> (innermost enclosing function, its first line, its last)."""
    spans = []
    for node in _ast.walk(_main_tree()):
        if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            spans.append((node.lineno, node.end_lineno, node.name))
    spans.sort()

    def owner(ln):
        best = None
        for a, b, name in spans:
            if a <= ln <= b and (best is None or a > best[0]):
                best = (a, b, name)
        return (best[2], best[0], best[1]) if best else ("<module>", 1, 1)
    return owner


def _same_txn_span(lines, i, lo_fn, hi_fn):
    """[lo, hi) indices around i covering its transaction within the function.

    lo_fn/hi_fn are 1-based inclusive function bounds; i is a 0-based index."""
    lo, hi = lo_fn - 1, min(hi_fn, len(lines))
    for j in range(i - 1, lo - 1, -1):
        if _TXN_BOUNDARY.search(lines[j]):
            lo = j + 1
            break
    for j in range(i + 1, hi):
        if _TXN_BOUNDARY.search(lines[j]):
            hi = j
            break
    return lo, hi


def _docstring_lines():
    """Every line number that falls inside a function docstring.

    _dissolve_group_rows' own docstring says it is the one authority and
    that no other site may write its own reset -- prose ABOUT the pattern,
    which the first version of this oracle counted as an INSTANCE of it and
    reported as a missing lease release. Same blindness the phase sweep had;
    same fix, taken from ast rather than guessed from indentation.
    """
    out = set()
    for node in _ast.walk(_main_tree()):
        if not isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            continue
        first = node.body[0]
        if (isinstance(first, _ast.Expr)
                and isinstance(first.value, _ast.Constant)
                and isinstance(first.value.value, str)):
            out.update(range(first.lineno, first.end_lineno + 1))
    return out


def reset_sites():
    """[(line, function, released_nearby)] for every reset to 'searching'."""
    src = _io.open(_inspect.getsourcefile(main), encoding="utf-8",
                   newline="").read()
    lines = src.split("\n")
    owner = _owner_index()
    docs = _docstring_lines()
    out = []
    for i, l in enumerate(lines):
        if not _RESET.search(l) or l.lstrip().startswith("#"):
            continue
        if (i + 1) in docs:
            continue
        fn, lo_fn, hi_fn = owner(i + 1)
        lo, hi = _same_txn_span(lines, i, lo_fn, hi_fn)
        released = any(_RELEASE.search(lines[j])
                       and not lines[j].lstrip().startswith("#")
                       and (j + 1) not in docs
                       for j in range(lo, hi))
        out.append((i + 1, fn, released))
    return out


def test_the_reset_oracle_can_fail():
    """Negative control: the derivation must actually find resets, and must
    report one that has no release near it."""
    sites = reset_sites()
    assert len(sites) >= 5, sites
    planted = sites + [(10 ** 9, "_planted_reset_with_no_release", False)]
    missing = [(ln, fn) for ln, fn, rel in planted
               if not rel and fn not in _RESET_NO_LEASE]
    assert (10 ** 9, "_planted_reset_with_no_release") in missing


def test_every_reset_exemption_is_a_real_husk_guard():
    """An exemption is a claim. Three of these say the reset only runs once the
    lease has already expired -- so the guard has to be visible in the source,
    or the entry is just a way of quieting the oracle."""
    spans = _function_spans()
    for name, why in _RESET_NO_LEASE.items():
        assert name in spans, (name, "exempted but no longer exists")
        if "husk" not in why:
            continue
        body = _inspect.getsource(getattr(main, name))
        assert "_lease_live_mode" in body, (
            name, "claimed to be husk clearance but takes no lease reading")


def test_every_dissolution_releases_the_lease_that_fenced_it():
    """A reset to 'searching' and the release of its lease belong to the same
    transaction. Anything that resets without releasing leaves a seat that
    looks free and cannot be formed."""
    missing = [(ln, fn) for ln, fn, released in reset_sites()
               if not released and fn not in _RESET_NO_LEASE]
    assert not missing, (
        "these reset a seat to 'searching' without releasing its lease:\n"
        + "\n".join(f"  {fn} at line {ln}" for ln, fn in missing))


# ── Round 2 part 4: the caller row, the ready clock, FFA's gather, the wait ──


def test_the_team_formation_writes_from_the_locked_caller_row():
    """r1 :38522. The preflight transaction COMMITS before formation begins,
    which releases the caller's own row lock — and the formation then wrote
    the caller's SIDE (preferred_team) and BALANCE (rating and friends) out of
    that pre-commit copy. A player who changed their team preference while the
    poll was acquiring identities was placed on the side they had just left,
    and it stuck, because team_assigned is what the series is scored under.

    Re-reading `status, queue_type` is not re-checking the predicate (#208).
    The whole row is re-read, through ONE column list, and the formation is
    made to use it — a re-read the writer does not then read from is
    decoration.

    The two drift dispositions are pinned separately. Predicate drift STOPS
    (rediscovery would re-run binds built above the loop, which is the :38448
    shape); candidate drift RETRIES. A test that still passed if those were
    collapsed into one would not be testing the thing."""
    whole = _io.open(_inspect.getsourcefile(main),
                     encoding="utf-8", newline="").read()
    assert "SELECT status, queue_type FROM team_queue" not in whole, (
        "the two-column re-read is back")
    cols = main._TEAM_CALLER_ROW_COLS
    for c in ("tq.rating", "tq.preferred_team", "tq.manual_pick_enabled",
              "tq.completed_series", "tq.queue_type", "tq.status"):
        assert c in cols, c
    assert whole.count("tq.preferred_team, tq.manual_pick_enabled") == 1, (
        "the caller's column list has been hand-copied a second time")

    src = _inspect.getsource(main.team_queue_poll)
    assert src.count("_TEAM_CALLER_ROW_COLS") == 2, (
        src.count("_TEAM_CALLER_ROW_COLS"))
    tail = src[src.index("me = _mine"):][:400]
    assert "_team_balance_rating(" in tail, tail[:200]
    assert 'me["rating"]' in tail, tail[:200]

    tree = _ast.parse(src)
    drift = [n for n in _ast.walk(tree) if isinstance(n, _ast.If)
             and "my_r" in _ast.unparse(n.test)]
    assert len(drift) == 1, len(drift)
    assert any(isinstance(n, _ast.Break) for n in drift[0].body), (
        "caller drift must stop, not rediscover with the stale binds")
    assert not any(isinstance(n, _ast.Continue)
                   for n in _ast.walk(drift[0]))
    cand = [n for n in _ast.walk(tree) if isinstance(n, _ast.If)
            and _ast.unparse(n.test) == "len(still) != 3"]
    assert len(cand) == 1, len(cand)
    assert any(isinstance(n, _ast.Continue) for n in cand[0].body), (
        "candidate drift is real contention and must retry")


def test_a_repeat_ready_moves_nobody_s_timeout_clock():
    """r1 :38859, and the 1v1 twin the finding did not name.

    matched_at IS the ready-timeout clock. Both endpoints refreshed it on every
    call, so a client re-posting ready — a retry loop, a stuck button, a
    player pressing it again — pushed the window out for everyone else
    indefinitely, and the sitting could never time out. Only a ready that
    CHANGES something may move a clock."""
    src = _inspect.getsource(main.queue_ready)
    tree = _ast.parse(src)
    guards = [n for n in _ast.walk(tree) if isinstance(n, _ast.If)
              and _ast.unparse(n.test) == "not entry['ready']"]
    assert len(guards) == 1, len(guards)
    assert _ast.unparse(guards[0]).count("matched_at = NOW()") == 2, (
        "both the caller's refresh and the partner's belong under the guard")
    assert src.count("matched_at = NOW()") == 2, (
        "a matched_at refresh escaped the guard")

    tsrc = _inspect.getsource(main.team_queue_ready)
    assert "matched_at = NOW()" not in tsrc, (
        "the unconditional four-row refresh is back")
    assert "CAST(:fresh AS boolean)" in tsrc
    assert '"fresh": not _was_ready' in tsrc
    # read, not derived from `status`: status is the SITTING's state and flips
    # to 'ready' for all four on the first ready, so it can never answer
    # whether THIS caller was already ready.
    assert "SELECT ready FROM team_queue WHERE player_id = :pid" in tsrc


def test_the_ffa_gather_decision_is_pure_and_asked_twice():
    """r1 :46810 / :46869. A FULL pool releases the gather immediately,
    waiting for nothing. If that roster shrank under the identity barrier, the
    rediscovery re-checked only the MINIMUM — so a lobby released because it
    was full could be locked with three seats, while the window that governs a
    three-seat start had not opened. The players were told it was full.

    The decision is asked again of the rediscovered roster, which is only safe
    because it touches none of the window's module state: re-stamping that is
    what the old comment was protecting against, and it is a different thing
    from re-asking the question.

    EXECUTED (#441): the releases are pinned by calling the function, not by
    reading it."""
    assert main.FFA_MIN_PLAYERS < main.FFA_MAX_PLAYERS
    src = _inspect.getsource(main._ffa_queue_poll_inner)
    # Structure, not a substring count. Two asks can both APPEAR while
    # only one can run: `x = (a, b) or f(...)` short-circuits on a truthy
    # tuple and never asks again, and a count of "_ffa_gather_decide("
    # reads that as compliant (#441). Require each call to BE the value
    # assigned, which is the only form that cannot be skipped.
    import ast as _ast, textwrap as _tw
    _fn = _ast.parse(_tw.dedent(src)).body[0]
    _asks = [n for n in _ast.walk(_fn) if isinstance(n, _ast.Call)
             and getattr(n.func, "id", None) == "_ffa_gather_decide"]
    assert len(_asks) == 2, len(_asks)
    _assigned = [n.value for n in _ast.walk(_fn)
                 if isinstance(n, _ast.Assign)]
    for _c in _asks:
        assert any(_c is _d for _d in _assigned), (
            "a gather ask that is not the assigned value can be short-"
            "circuited away while still reading as present")
    dsrc = _inspect.getsource(main._ffa_gather_decide)
    for name in ("_ffa_gather_started_mono", "_ffa_gather_last_join_mono",
                 "_ffa_gather_pool_seen_mono", "global"):
        assert name not in dsrc, (name, "the decision touches window state")

    go, left = main._ffa_gather_decide(main.FFA_MAX_PLAYERS, 0.0, 0.0)
    assert go and left == 0
    go, left = main._ffa_gather_decide(main.FFA_MIN_PLAYERS, 0.0, 0.0)
    assert not go and left > 0, (go, left)
    assert main._ffa_gather_decide(
        main.FFA_MIN_PLAYERS, main.FFA_GATHER_CAP_SECONDS, 0.0)[0]
    assert main._ffa_gather_decide(
        main.FFA_MIN_PLAYERS, main.FFA_GATHER_SECONDS,
        main.FFA_GATHER_EXTEND_SECONDS)[0]
    assert not main._ffa_gather_decide(
        main.FFA_MIN_PLAYERS, main.FFA_GATHER_SECONDS, 0.0)[0], (
        "the base window alone does not release; the quiet period must "
        "have run too")
    for w in (0.0, 5.0, float(main.FFA_GATHER_SECONDS) - 1):
        go, left = main._ffa_gather_decide(main.FFA_MIN_PLAYERS, w, 0.0)
        assert not go and 0 <= left <= main.FFA_GATHER_CAP_SECONDS, (w, left)

    assert '"gather_seconds_left": _left' in src, (
        "the failed-attempt return still reports a hardcoded window")


class _LockTimeoutSession(FakeSession):
    """A session whose Nth advisory lock raises a chosen SQLSTATE."""

    def __init__(self, fail_on=1, sqlstate="55P03"):
        super().__init__()
        self.fail_on = fail_on
        self.sqlstate = sqlstate
        self._lock_calls = 0

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        if "pg_advisory_xact_lock" in sql:
            self._lock_calls += 1
            if self._lock_calls == self.fail_on:
                orig = type("_orig", (Exception,),
                            {"sqlstate": self.sqlstate})()
                raise _DBAPIError("SELECT pg_advisory_xact_lock(...)", {},
                                  orig)
        return await super().execute(statement, params)


def test_the_identity_barrier_bounds_its_wait_and_answers_contended():
    """Self-review finding 2. pg_advisory_xact_lock waits forever by
    default. A poll blocked behind a stuck holder keeps an api worker and a
    database connection until that holder dies; the pool runs out before
    anything else does, and the symptom is a silent queue rather than one slow
    request. Bounding the retry COUNT does nothing about it — a poll stuck on
    its first acquire never reaches its second attempt.

    The bound is BRACKETED, and that is the half worth asserting. SET
    LOCAL lasts to the end of the transaction, so an arm with no disarm
    puts a 55P03 under every later row lock with nothing to answer it and
    turns a retryable contention into a 500. Extent is the property: armed
    before the first acquire, disarmed after the last, and on the refusal
    path not disarmed at all — the rollback reverts it.

    Carries its own negative control: a DIFFERENT SQLSTATE must propagate
    untouched."""
    db = FakeSession()
    run(main._identity_lock_many(db, SIDS))
    assert "SET LOCAL lock_timeout" in db.statements[0], db.statements[:2]
    assert str(main.FORMATION_LOCK_TIMEOUT_MS) in db.statements[0]
    # the timeout is set BEFORE the first lock, or it governs nothing.
    first_lock = next(i for i, s in enumerate(db.statements)
                      if "pg_advisory_xact_lock" in s)
    assert first_lock > 0
    # ...and disarmed immediately after the last one, or it governs more
    # than the handler above it covers.
    last_lock = max(i for i, s in enumerate(db.statements)
                    if "pg_advisory_xact_lock" in s)
    dis = [i for i, s in enumerate(db.statements)
           if "lock_timeout = DEFAULT" in s]
    assert dis == [last_lock + 1], (db.statements, dis, last_lock)

    db = _LockTimeoutSession()
    with pytest.raises(main.HTTPException) as exc:
        run(main._identity_lock_many(db, SIDS))
    assert exc.value.status_code == 503
    assert exc.value.detail == "queue_contended"
    assert db.rollbacks == 1, (
        "the locks already taken are released now, not at session close")
    assert not any("DEFAULT" in st for st in db.statements), (
        "the refusal path rolls back, and SET LOCAL reverts with it")

    db = _LockTimeoutSession(sqlstate="40001")
    with pytest.raises(_DBAPIError):
        run(main._identity_lock_many(db, SIDS))
