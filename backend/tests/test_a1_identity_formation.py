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
    sql = db.statements[0]
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
import inspect as _inspect
import re as _re

_IDENTITY = _re.compile(r"_identity_lock_many\(|_ranked_identity_phase\(")
_ROWLOCK = _re.compile(r"_lock_snapshot_rows\(|_lock_queue_rows_ordered\(")
_ENDTXN = _re.compile(r"await db\.(commit|rollback)\(\)")

# Sites wired so far. The remaining ones from A1-BRIEF.md are added here as
# they land, and this list is the record of which are done.
# _lobby_start_common is listed rather than team_lobby_start/ovt_lobby_start:
# the two routes share it, and it is where the locking actually happens, so
# checking the routes would pass trivially and prove nothing.
WIRED_SITES = ["queue_poll", "queue_ready", "_lobby_start_common",
               "ffa_lobby_start", "team_queue_poll", "ovt_queue_poll",
               "ffa_queue_poll"]

# The gather paths. A FRESH automatic roster, so the gate must be called with
# no `allow` at all -- the exact mirror of HOSTED_STARTS, and the same one-word
# edit in the other direction: an `allow` here would admit precisely the
# double booking A1 exists to refuse.
FRESH_ROSTER_SITES = ["queue_poll", "ovt_queue_poll", "ffa_queue_poll"]

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


def test_team_poll_gates_its_two_branches_differently():
    """Codex HIGH: team must choose sticky-resume vs fresh formation during
    unlocked discovery, and the two branches cannot share one lease policy.
    The resuming four legitimately still hold THAT series' lease -- it is what
    makes the path a resume; a fresh four must hold nothing at all."""
    calls = _gate_calls(_inspect.getsource(main.team_queue_poll))
    assert len(calls) == 2, len(calls)
    sticky, fresh = calls
    assert 'allow=("team", dc_row["id"])' in sticky, sticky
    assert "allow=" not in fresh, fresh
    assert "require=True" not in sticky, (
        "a resume must still admit a seat whose lease lapsed during the DC")


# How many times each handler EXECUTES its predicate. Two is discovery plus
# revalidation; the FFA gather runs a third, its post-drift rediscovery, which
# re-elects the decider because the decider is a property of the roster.
@pytest.mark.parametrize("site,const,runs", [
    ("queue_poll", "_RANKED_CANDIDATE_SQL", 2),
    ("ovt_queue_poll", "_OVT_CANDIDATE_SQL", 2),
    ("ffa_queue_poll", "_FFA_CANDIDATE_SQL", 3),
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
    # built once, then used for discovery and for revalidation
    assert src.count("_cand_sql") == 3, src.count("_cand_sql")
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
    src = _inspect.getsource(main.ffa_queue_poll)
    assert src.count("_ffa_sort_key") == 3, src.count("_ffa_sort_key")


@pytest.mark.parametrize("site,loop_var", [
    ("ovt_queue_poll", "_form_attempt"),
    ("ffa_queue_poll", "_form_attempt"),
    ("team_queue_poll", "_form_attempt"),
])
def test_gather_loops_are_bounded_and_end_in_a_refusal(site, loop_var):
    """Bounded on purpose: identity locks stabilise only the identities
    already discovered, so a rediscovery can always turn up a new contender
    and an unbounded loop is a real possibility, not a theoretical one."""
    src = _inspect.getsource(getattr(main, site))
    assert f"for {loop_var} in range(1, FORMATION_MAX_ATTEMPTS + 1):" in src, site
    assert 'raise HTTPException(status_code=503, detail="queue_contended")' in src, site


@pytest.mark.parametrize("site", ["ovt_queue_poll", "ffa_queue_poll"])
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
