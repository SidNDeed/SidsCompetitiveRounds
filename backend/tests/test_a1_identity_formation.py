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
import textwrap as _textwrap
import collections as _collections
import importlib as _importlib

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


def _txn_end(node):
    """'commit' or 'rollback' when `node` is the statement `await db.commit()`
    or `await db.rollback()`, else None."""
    call = (node.value.value if isinstance(node, _ast.Expr)
            and isinstance(node.value, _ast.Await) else None)
    if (isinstance(call, _ast.Call) and not call.args and not call.keywords
            and isinstance(call.func, _ast.Attribute)
            and isinstance(call.func.value, _ast.Name)
            and call.func.value.id == "db"
            and call.func.attr in ("commit", "rollback")):
        return call.func.attr
    return None


def _awaits(node):
    return any(isinstance(n, _ast.Await) for n in _ast.walk(node))


def _ends_inside(node):
    """Whether `node` names a transaction end in any spelling. The walk
    places only the plain statements `await db.commit()` and
    `await db.rollback()` on a path, so any other `.commit` or `.rollback` in
    its span is one it cannot place, and is reported rather than skipped."""
    return any(isinstance(n, _ast.Attribute) and n.attr in ("commit", "rollback")
               for n in _ast.walk(node))


def _outer_jumps(node):
    """The `continue` and `break` statements inside `node` that leave it for a
    loop around it. A loop's own body captures its jumps; its `else:` does
    not, so a `continue` there restarts the formation loop (rehearsal-four
    round 1, finding 2). A nested def, lambda or class is a scope no jump
    leaves."""
    out = []

    def visit(n, captured):
        if isinstance(n, (_ast.Continue, _ast.Break)):
            if not captured:
                out.append(n)
        elif isinstance(n, (_ast.For, _ast.AsyncFor, _ast.While)):
            for c in n.body:
                visit(c, True)
            for c in n.orelse:
                visit(c, captured)
        elif not isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef,
                                _ast.Lambda, _ast.ClassDef)):
            for c in _ast.iter_child_nodes(n):
                visit(c, captured)

    visit(node, False)
    return out


# The exit walk is CLOSED (rehearsal-four round 2, ruling REHEARSAL-FOUR-R2):
# every statement it meets in a walked span is classified into a NAMED shape,
# and a construct it cannot classify fails the test naming the construct and
# its line. Round 1's walk listed bad shapes (a commit before the rollback, a
# write after it) and let every construct it did not name through: a barrier
# and a commit under `if True:`, a helper that commits, `SELECT lo_create(0)`
# read as a plain SELECT. The allow-lists below are positive: a name is on a
# list because the walk met it in main's real spans and it reads, locks or
# writes rows without ending the transaction.

from closed_walk import Unclassified  # noqa: E402
import closed_walk as _cw  # noqa: E402


# The allow-lists are positive and named; the classification itself is
# closed_walk's (rehearsal-four round 3, ruling REHEARSAL-FOUR-R3: one shared
# default-deny visitor, every concrete ast class in its NODE_TABLE, SQL
# classified from migration_table_ddl's lexer tokens). Each list holds only
# what main's real spans met, verified by count (round 3: every entry with a
# count of zero was removed).
#
# Functions a reading statement may call: each reads, computes or casts and
# writes nothing. Anything else in a SELECT (lo_create, nextval, setval,
# pg_advisory_*, a user function) is unclassified.
_SQL_READ_FUNCS = frozenset({"abs", "any", "cast", "clock_timestamp",
    "coalesce", "count", "current_setting", "exists", "extract",
    "hashtextextended", "in", "least", "make_interval", "max", "now", "nullif",
    "string_to_array", "unnest", "values"})
# Functions that take a transaction-scoped lock or change a transaction-local
# setting and nothing else (`set_config(<name>, <value>, true)`,
# `pg_advisory_xact_lock(<key>)`, released at the transaction's end): such a
# statement is read as 'lock', never as a plain read.
_SQL_SETTING_FUNCS = frozenset({"pg_advisory_xact_lock", "set_config"})
# Functions a writing statement may call besides the reading ones.
_SQL_WRITE_FUNCS = frozenset()
# Words followed by "(" that are SQL syntax, not function calls.
_SQL_SYNTAX = frozenset({"and", "conflict", "from", "materialized", "not",
    "where"})
_SQL_LISTS = _cw.SqlLists(_SQL_READ_FUNCS, _SQL_SETTING_FUNCS, _SQL_WRITE_FUNCS,
                          _SQL_SYNTAX)

# Plain calls a step may make that touch no session: builtins and the clock,
# id and log functions the spans use.
_PURE_CALLS = frozenset({"GoldTransaction", "HTTPException",
    "QueuePollResponse", "StakeRefundRefused", "TeamQueuePollResponse",
    "ValueError", "_json.loads", "all", "any", "bool", "datetime.now", "dict",
    "enumerate", "float", "int", "isinstance", "len", "list", "min", "next",
    "print", "random.choice", "round", "set", "sorted", "str", "text",
    "time.monotonic", "time.time", "type", "uuid.UUID", "uuid.uuid4",
    "uuid_mod.uuid4"})
# Methods a step may call on a local value (rows, lists, dicts, strings).
_PURE_METHODS = frozenset({"add", "all", "append", "extend", "fetchall",
    "first", "get", "intersection", "items", "join", "lower", "lstrip",
    "mappings", "one", "replace", "scalar", "scalar_one", "scalars", "sort",
    "strip", "timestamp", "update", "values"})
# Awaited library calls a helper may make that touch no session.
_PURE_AWAITS = frozenset({"asyncio.sleep"})


def _policy(scope=None):
    """The a1 walk's policy over `scope` (main by default). One policy per
    scope, so its helper cache and met-shape counter persist."""
    scope = main if scope is None else scope
    key = id(scope)
    if key not in _POLICIES:
        _POLICIES[key] = _cw.Policy(scope, _PURE_CALLS, _PURE_METHODS,
                                    _PURE_AWAITS, _SQL_LISTS)
    return _POLICIES[key]


_POLICIES = {}


def _sql_kind(sql):
    """'read', 'lock' or 'write' (closed_walk.sql_kind under the a1 lists)."""
    return _cw.sql_kind(sql, _SQL_LISTS)


def _local_sql(tree, scope):
    return _cw.local_sql(tree, scope)


def _is_db_call(call, attr):
    return _cw.is_db_call(call, attr)


def _execute_kind(call, scope, local_sql=None, guarded=frozenset()):
    return _cw.execute_kind(call, scope, _SQL_LISTS, local_sql, guarded)


def _helper_effects(fn, scope=None):
    """closed_walk.helper_effects under the a1 policy."""
    return _cw.helper_effects(fn, _policy(scope))


def expr_effects(node, scope=None, local_sql=None):
    """closed_walk.expr_effects under the a1 policy: the (shape, effect) list
    of evaluating `node`; raises Unclassified naming the construct and its
    line."""
    return _cw.expr_effects(node, _policy(scope), local_sql)


def _plain_read(call):
    """Whether `call` is `db.execute(text(<sql>), ...)` whose SQL _sql_kind
    reads as 'read': one SELECT or WITH statement, no lock, no write, every
    function on the read allow-list."""
    if not _is_db_call(call, "execute"):
        return False
    try:
        return _execute_kind(call, main) == "read"
    except Unclassified:
        return False


def _only_plain_reads(node):
    """Every await in `node` is a plain read (_plain_read). That is what a
    gather site may run after its rollback: the rediscovery
    _ffa_queue_poll_inner makes there ("The rollback above is what makes the
    rediscovery legal"), and the searching counts its no-match exits answer
    with. It takes no lock and writes nothing, so the next attempt's barrier
    still runs with no row held."""
    return all(_plain_read(n.value) for n in _ast.walk(node)
               if isinstance(n, _ast.Await))


def _block_holding(tree, node):
    """The statement list that holds `node`, and its index there."""
    for parent in _ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(parent, field, None)
            if isinstance(block, list):
                for i, st in enumerate(block):
                    if st is node:
                        return block, i
    return None, None


TEAM_RESOLVER = "_team_resolve_live_family"


def _calls_named(node, name):
    """Whether `node` holds a call of the plain name `name`."""
    return any(isinstance(n, _ast.Call) and isinstance(n.func, _ast.Name)
               and n.func.id == name for n in _ast.walk(node))


def _is_team_answer(node, status):
    """Whether `node` is `return TeamQueuePollResponse(status=<status>, ...)`."""
    value = getattr(node, "value", None)
    return (isinstance(node, _ast.Return) and isinstance(value, _ast.Call)
            and isinstance(value.func, _ast.Name)
            and value.func.id == "TeamQueuePollResponse"
            and any(k.arg == "status" and isinstance(k.value, _ast.Constant)
                    and k.value.value == status for k in value.keywords))


def _resolver_dispatch(stmts, i):
    """The team resolver's outcome dispatch at stmts[i:i + 3], exactly as
    team_queue_poll states it, as (the 'relocked' return, the 'defer'
    branch); None for any other shape:

        <o>, <r> = await _team_resolve_live_family(...)
        if <o> == "relocked":
            return <r>
        if <o> == "defer":
            await db.commit()
            return TeamQueuePollResponse(status="searching", ...)

    What follows it is the 'fresh' outcome. The resolver's docstring:
    "Returns ('relocked', TeamQueuePollResponse) / ('fresh', None) /
    ('defer', None)"."""
    if i + 3 > len(stmts):
        return None
    st, rel, dfr = stmts[i:i + 3]
    target = (st.targets[0] if isinstance(st, _ast.Assign)
              and len(st.targets) == 1 else None)
    call = getattr(getattr(st, "value", None), "value", None)
    if not (isinstance(target, _ast.Tuple) and len(target.elts) == 2
            and all(isinstance(e, _ast.Name) for e in target.elts)
            and isinstance(st.value, _ast.Await)
            and isinstance(call, _ast.Call)
            and isinstance(call.func, _ast.Name)
            and call.func.id == TEAM_RESOLVER):
        return None
    outcome, answer = (e.id for e in target.elts)

    def branch(node, word, size):
        test = getattr(node, "test", None)
        return (isinstance(node, _ast.If) and not node.orelse
                and len(node.body) == size
                and isinstance(test, _ast.Compare)
                and isinstance(test.left, _ast.Name)
                and test.left.id == outcome and len(test.ops) == 1
                and isinstance(test.ops[0], _ast.Eq)
                and isinstance(test.comparators[0], _ast.Constant)
                and test.comparators[0].value == word)

    ret = rel.body[0] if branch(rel, "relocked", 1) else None
    if not (isinstance(ret, _ast.Return) and isinstance(ret.value, _ast.Name)
            and ret.value.id == answer):
        return None
    if not (branch(dfr, "defer", 2) and _txn_end(dfr.body[0]) == "commit"
            and _is_team_answer(dfr.body[1], "searching")):
        return None
    return ret, dfr


def _team_formation_loops(fn_src, tree):
    """team_queue_poll's two formation loops, resume then fresh, read as the
    poll spends them: ONE attempt budget (_attempt_budgets: one opening, one
    counter) across exactly two `while <counter> > 0:` loops, each spending
    it as its first statement, with the counter stored nowhere else but its
    opening and the fresh phase's floor of one attempt (`<counter> =
    max(<counter>, 1)`), and every _identity_lock_many call in the poll one
    of the loops' barriers, one statement in each loop's body, so no
    formation is left outside the walk. Returns (loops, None), or ([],
    (line, why)) for any other shape."""
    openings, counters, _whiles = _attempt_budgets(fn_src)
    if len(openings) != 1 or len(counters) != 1:
        return [], (0, f"{len(openings)} attempt budget openings over "
                       f"{sorted(counters)}; the team form spends one")
    (counter,) = counters
    loops = sorted((n for n in _ast.walk(tree) if isinstance(n, _ast.While)
                    and any(isinstance(x, _ast.Name) and x.id == counter
                            for x in _ast.walk(n.test))),
                   key=lambda n: n.lineno)
    if len(loops) != 2:
        return [], (0, f"{len(loops)} loops over the attempt budget; the "
                       "team form has two")
    stores = set()
    for n in loops:
        if not (_ast.unparse(n.test) == f"{counter} > 0"
                and _ast.unparse(n.body[0]) == f"{counter} -= 1"):
            return [], (n.lineno, "a loop over the attempt budget that is not "
                                  f"`while {counter} > 0:` spending it first")
        stores.add(id(n.body[0].target))
    # The opening and the fresh phase's floor are stores of the budget only
    # OUTSIDE both loops: a floor inside a loop refills the budget on every
    # attempt (rehearsal-four round 2, finding 4: `_form_left =
    # max(_form_left, 1)` after the decrement passed and made the drift
    # retries unbounded).
    inside = {id(x) for lp in loops for x in _ast.walk(lp)}
    for n in _ast.walk(tree):
        if id(n) in inside:
            continue
        if (isinstance(n, _ast.Assign) and len(n.targets) == 1
                and isinstance(n.targets[0], _ast.Name)
                and n.targets[0].id == counter
                and _ast.unparse(n.value) in ("FORMATION_MAX_ATTEMPTS",
                                              f"max({counter}, 1)")):
            stores.add(id(n.targets[0]))
    for n in _ast.walk(tree):
        if (isinstance(n, _ast.Name) and n.id == counter
                and isinstance(n.ctx, _ast.Store) and id(n) not in stores):
            return [], (n.lineno, "an assignment to the attempt budget this "
                                  "walk does not read")
    barriers = [n for n in _ast.walk(tree) if isinstance(n, _ast.Call)
                and isinstance(n.func, _ast.Name)
                and n.func.id == "_identity_lock_many"]
    held = [st for n in loops for st in n.body if any(
        c is b for c in _ast.walk(st) for b in barriers)]
    if len(barriers) != 2 or len(held) != 2 or any(
            sum(st in held for st in n.body) != 1 for n in loops):
        return [], (0, f"{len(barriers)} identity barriers; the team form "
                       "reads one in each of its two loops and none elsewhere")
    return loops, None


def formation_loop_exits(fn_src, form="return", shapes=None, scope=None):
    """Every exit of the handler's one `for _form_attempt` loop taken after
    the loop body's identity barrier, path by path, with the transaction ends
    its path passed, in order. The loop's `else:` (attempts exhausted) is
    walked as a path of its own.

    form "return" (queue_poll): the success exit commits and returns inside
    the loop, and nothing may await on a path after it ended the transaction.
    form "gather" (ovt_queue_poll, _ffa_queue_poll_inner): the success exit
    is a `break` that carries the open transaction, barrier held, to the
    formation writes after the loop, so the statements after the loop are
    walked from that state through the one that holds the _lease_acquire_many
    call; and since a gather site rediscovers after its rollback, a plain
    read (_only_plain_reads) may follow a rollback there. Nothing may await
    after a commit in any form.

    forms "team-resume" and "team-fresh" (the two phases of team_queue_poll,
    which spend ONE attempt budget across two `while` loops, found by
    _team_formation_loops; rehearsal-four round 1, item T): each phase's
    loop is walked like the gather form's, from its own barrier, with no
    read allowed after a rollback, and with the team resolver's outcome
    dispatch read where it stands (_resolver_dispatch): 'relocked' is an
    exit whose transaction end is the resolver's relock commit (read there
    by _relock_outcome_problems), 'defer' an exit that commits once and
    answers searching, and 'fresh' carries on with the transaction open. A
    resolver call in any other shape is refused. The resume phase's success
    exit is its 'fresh' break: the statements after its loop are walked from
    it and must fall through to fresh formation after exactly one commit,
    awaiting nothing else, so a rollback-ended break that reaches the same
    commit publishes nothing of the attempt it rolled back. The fresh
    phase's statements after its loop are walked like the gather form's,
    through the one that holds the _lease_acquire_many call.

    Returns (exits, n_body, n_loop, (rollbacks, passed), problems):
      exits      [(line, kind, end, node)]: kind continue, break, raise or
                 return, or in the team forms the resolver's outcomes
                 relocked (end 'relock') and defer; end the transaction
                 ends the path passed, in order
                 ('rollback', 'commit', 'commit, rollback', ...), or None.
                 exits[:n_body] are the loop body's, exits[n_body:n_loop] the
                 else's, exits[n_loop:] the gather form's after the loop;
      rollbacks  (the line of every `await db.rollback()` in the walked span,
                 the lines of the rollbacks that ended an exit's path);
      problems   [(line, why)]: a second transaction end on one path (finding
                 1 of rehearsal-four round 1: a commit before the rollback
                 must not hide behind it); a statement that awaits after its
                 path ended the transaction (the barrier went with it),
                 except a gather site's plain read after its rollback; a
                 branch that ends the transaction and falls through; a
                 `continue` or `break` for the formation loop inside a nested
                 construct (finding 2: a nested loop's `else: continue`), and
                 any other end or exit inside a construct this walk does not
                 model, or a transaction end in a spelling it does not read;
                 an attempt that runs off the loop body without a rollback;
                 a gather formation that passes its lease acquisition after a
                 transaction end, or has none.
    Lines are handler-relative.
    """
    tree = _ast.parse(fn_src)
    scope = main if scope is None else scope
    team = form in ("team-resume", "team-fresh")
    if team:
        loops, why = _team_formation_loops(fn_src, tree)
        if why is not None:
            return [], 0, 0, (set(), set()), [why]
        loop = loops[1] if form == "team-fresh" else loops[0]
    else:
        loops = [n for n in _ast.walk(tree) if isinstance(n, _ast.For)
                 and isinstance(n.target, _ast.Name)
                 and n.target.id == "_form_attempt"]
        if len(loops) != 1:
            return [], 0, 0, (set(), set()), [(0, f"{len(loops)} formation loops")]
        loop = loops[0]
    barrier = [i for i, st in enumerate(loop.body) if any(
        isinstance(c, _ast.Call) and isinstance(c.func, _ast.Name)
        and c.func.id == "_identity_lock_many" for c in _ast.walk(st))]
    if not barrier:
        return [], 0, 0, (set(), set()), [(loop.lineno, "no identity barrier")]
    gather = form == "gather"
    exits, problems, passed, breaks = [], [], set(), []
    shapes = _collections.Counter() if shapes is None else shapes
    # post: walking the statements after the loop from a rollback-ended
    # break (round 2, finding 3), where a further rollback after reads only
    # is harmless and the break's bindings decide the conditions they can.
    mode = {"post": False}

    # The barrier is ONE named shape: the plain statement
    # `await _identity_lock_many(<pure arguments>)` (round 2, finding 1: a
    # barrier and a commit under `if True:` made the whole `if` the barrier
    # statement, and the walk started after it).
    bst = loop.body[barrier[0]]
    bcall = (bst.value.value if isinstance(bst, _ast.Expr)
             and isinstance(bst.value, _ast.Await) else None)
    if not (len(barrier) == 1 and isinstance(bcall, _ast.Call)
            and isinstance(bcall.func, _ast.Name)
            and bcall.func.id == "_identity_lock_many"):
        problems.append((bst.lineno, "the identity barrier is not the plain "
                         "statement `await _identity_lock_many(...)`"))
    else:
        # Every argument kind of the barrier call is classified: positional,
        # keyword, and unpacked ones are refused (round 3, finding a1:1397:
        # `timeout_ms=(await db.commit())` passed when only the positional
        # arguments were read).
        try:
            for kind, a in _cw.call_arguments(bcall):
                if kind in ("star", "double-star"):
                    raise Unclassified((bst.lineno, "the barrier has unpacked "
                                                    "arguments"))
                if any(sh != "call" for sh, _e in expr_effects(a, scope)):
                    problems.append((bst.lineno, "the barrier's arguments await"))
        except Unclassified as e:
            problems.append((e.args[0][0] or bst.lineno, e.args[0][1]))
        shapes["barrier"] += 1

    def ended(state):
        return ", ".join(kind for kind, _ln in state) or None

    local_sql = _local_sql(tree, scope)

    def effects_of(node, line):
        # An unclassified construct is reported where it stands; if it
        # awaits, it also counts as an await on the path, so a path that
        # ended the transaction still reports it.
        try:
            return expr_effects(node, scope, local_sql)
        except Unclassified as e:
            problems.append((e.args[0][0] or line, e.args[0][1]))
            return [("unclassified", "await")] if _awaits(node) else []

    def allowed(eff, state):
        """Whether effects `eff` may run on a path that passed `state`:
        anything classified while the transaction is open; after a rollback
        at a gather site (or after the loop, from a rollback-ended break)
        only plain reads and plain calls; after any other end, nothing that
        awaits."""
        if not state:
            return True
        if all(k == "rollback" for k, _ln in state) and (
                (gather and len(state) == 1) or mode["post"]):
            return all(sh == "call" or (sh, e) == ("sql", "read")
                       for sh, e in eff)
        return all(sh == "call" for sh, _e in eff)

    def record(prefix, eff):
        if any(sh == "unclassified" for sh, _e in eff):
            return
        kinds = sorted({(s.split(":")[0], e) for s, e in eff if s != "call"})
        shapes[prefix + (": " + ", ".join(f"{s} {e}" for s, e in kinds)
                         if kinds else ": pure")] += 1

    def target_ok(tg, line):
        if isinstance(tg, _ast.Name):
            return [tg.id]
        if isinstance(tg, (_ast.Tuple, _ast.List)) and all(
                isinstance(e, _ast.Name) for e in tg.elts):
            return [e.id for e in tg.elts]
        if isinstance(tg, _ast.Subscript) and isinstance(tg.value, _ast.Name):
            eff = effects_of(tg.slice, line)
            if eff and any(sh != "call" for sh, _e in eff):
                problems.append((line, "an assignment target that awaits"))
            return []
        problems.append((line, "an assignment target this walk does not "
                         f"classify: {_ast.unparse(tg)}"))
        return []

    def simple(st, state, env):
        """A simple statement: an assignment to locals, an expression, or
        pass. Returns the bindings after it."""
        names = []
        if isinstance(st, (_ast.Assign, _ast.AnnAssign, _ast.AugAssign)):
            tgs = st.targets if isinstance(st, _ast.Assign) else [st.target]
            for tg in tgs:
                names += target_ok(tg, st.lineno)
            eff = effects_of(st.value, st.lineno) if st.value is not None else []
            prefix = "assignment"
        elif isinstance(st, _ast.Expr):
            eff = effects_of(st.value, st.lineno)
            prefix = "expression"
        elif isinstance(st, _ast.Pass):
            eff, prefix = [], "pass"
        else:
            problems.append((st.lineno, "a statement this walk does not "
                             f"classify: {type(st).__name__}"))
            return {}
        if eff is None:
            return {}
        record(prefix, eff)
        if not allowed(eff, state):
            problems.append((st.lineno, f"awaits after {ended(state)}"))
        env = dict(env)
        # A store is any binding of the name, including a mutating method
        # on it (round 3, ruling item b: `others.extend(still)` after the
        # drift's `others = []` kept the rolled-back roster).
        for nm in set(names) | _cw.stores(st):
            env.pop(nm, None)
        if (isinstance(st, _ast.Assign) and len(st.targets) == 1
                and isinstance(st.targets[0], _ast.Name)):
            try:
                env[st.targets[0].id] = _ast.literal_eval(st.value)
            except (ValueError, TypeError, SyntaxError):
                pass
        return env

    def assigned(stmts):
        return set().union(*[_cw.stores(s) for s in stmts]) if stmts else set()

    def nested(stmts, state):
        """The body of a loop nested in the span: simple statements, ifs,
        nested loops and the jumps the nested loop captures; no transaction
        end and no exit."""
        for st in stmts:
            if isinstance(st, (_ast.Continue, _ast.Break)):
                shapes["nested loop jump"] += 1
            elif isinstance(st, _ast.If):
                eff = effects_of(st.test, st.lineno)
                if eff is not None:
                    record("nested if test", eff)
                    if not allowed(eff, state):
                        problems.append((st.lineno, f"awaits after {ended(state)}"))
                nested(st.body, state)
                nested(st.orelse, state)
            elif isinstance(st, _ast.For) and not st.orelse:
                loop_head(st, state)
                nested(st.body, state)
            elif (_txn_end(st) is not None
                  or isinstance(st, (_ast.Return, _ast.Raise))):
                problems.append((st.lineno, "an end or an exit inside a nested "
                                 "loop"))
            else:
                simple(st, state, {})

    def loop_head(st, state):
        target_ok(st.target, st.lineno)
        eff = effects_of(st.iter, st.lineno)
        if eff is not None:
            record("nested for", eff)
            if not allowed(eff, state):
                problems.append((st.lineno, f"awaits after {ended(state)}"))

    def decide(test, env):
        """True or False when the bindings `env` decide `test` (names bound
        to literals, `len`, comparisons and boolean operators only), else
        None."""
        if not mode["post"]:
            return None
        names = {n.id for n in _ast.walk(test) if isinstance(n, _ast.Name)}
        calls = [n for n in _ast.walk(test) if isinstance(n, _ast.Call)]
        if not names or not names <= set(env) | {"len"} or any(
                not (isinstance(c.func, _ast.Name) and c.func.id == "len")
                for c in calls) or any(
                not isinstance(n, (_ast.Compare, _ast.BoolOp, _ast.UnaryOp,
                                   _ast.Call, _ast.Name, _ast.Constant,
                                   _ast.Load, _ast.cmpop, _ast.boolop,
                                   _ast.unaryop)) for n in _ast.walk(test)):
            return None
        try:
            return bool(eval(compile(_ast.Expression(test), "<test>", "eval"),
                             {"__builtins__": {}, "len": len}, dict(env)))
        except Exception:
            return None

    def walk(stmts, state, env):
        # `state`: the transaction ends this path passed, in order, as
        # (kind, line); `env`: the locals the path bound to literals.
        # Returns (state, env) of the path that falls off `stmts`; None when
        # every path through them exits.
        skip = 0
        for i, st in enumerate(stmts):
            if skip:
                skip -= 1
                continue
            if team and _calls_named(st.test if isinstance(st, _ast.If)
                                     else st, TEAM_RESOLVER):
                shape = _resolver_dispatch(stmts, i)
                if shape is None:
                    problems.append((st.lineno, "a resolver call this walk "
                                     "does not read"))
                    continue
                # The resolver's outcomes as the dispatch states them:
                # 'relocked' returns the answer of the resolver's own
                # relock, whose commit ends that path (read there by
                # _relock_outcome_problems); 'defer' commits the resolver's
                # bookkeeping and answers searching; 'fresh' carries on
                # below, the transaction still open.
                ret, dfr = shape
                eff = effects_of(_ast.Tuple(elts=list(st.value.value.args)
                                            + [k.value for k in
                                               st.value.value.keywords],
                                            ctx=_ast.Load()), st.lineno)
                shapes["resolver dispatch"] += 1
                if state:
                    problems.append((st.lineno, f"awaits after {ended(state)}"))
                exits.append((ret.lineno, "relocked",
                              ended(state + (("relock", ret.lineno),)), ret))
                if state:
                    problems.append((dfr.body[0].lineno,
                                     f"commit after {ended(state)}"))
                d_eff = effects_of(dfr.body[1].value, dfr.body[1].lineno)
                if d_eff and any(sh != "call" for sh, _e in d_eff):
                    problems.append((dfr.body[1].lineno, "the defer answer awaits"))
                exits.append((dfr.body[1].lineno, "defer",
                              ended(state + (("commit", dfr.body[0].lineno),)),
                              dfr.body[1]))
                env = {k: v for k, v in env.items()
                       if k not in assigned([st])}
                skip = 2
                continue
            kind = _txn_end(st)
            if kind is not None:
                harmless = (mode["post"] and kind == "rollback"
                            and all(k == "rollback" for k, _ln in state))
                if state and not harmless:
                    problems.append((st.lineno, f"{kind} after {ended(state)}"))
                shapes[f"transaction end: {kind}"] += 1
                state = state + ((kind, st.lineno),)
                continue
            if isinstance(st, (_ast.Continue, _ast.Break, _ast.Raise,
                               _ast.Return)):
                parts = [x for x in (getattr(st, "exc", None),
                                     getattr(st, "cause", None),
                                     getattr(st, "value", None)) if x is not None]
                eff = effects_of(_ast.Tuple(elts=parts, ctx=_ast.Load()),
                                 st.lineno) if parts else []
                if eff is not None:
                    record(f"exit {type(st).__name__.lower()}", eff)
                    if not allowed(eff, state):
                        problems.append((st.lineno, f"awaits after {ended(state)}"))
                end = ended(state)
                exits.append((st.lineno, type(st).__name__.lower(), end, st))
                if isinstance(st, _ast.Break):
                    breaks.append((state, env, st.lineno))
                if end == "rollback":
                    passed.add(state[-1][1])
                return None
            if isinstance(st, _ast.If):
                eff = effects_of(st.test, st.lineno)
                if eff is not None:
                    record("if test", eff)
                    if not allowed(eff, state):
                        problems.append((st.lineno, f"awaits after {ended(state)}"))
                taken = decide(st.test, env)
                live = [r for r in ((walk(st.body, state, env) if taken
                                     is not False else None),
                                    (walk(st.orelse, state, env) if taken
                                     is not True else None))
                        if r is not None]
                if not live:
                    return None
                if any(r[0] != state for r in live):
                    problems.append((st.lineno, "a branch ends the "
                                     "transaction and falls through"))
                state = live[0][0]
                env = {k: v for k, v in live[0][1].items()
                       if all(k in r[1] and r[1][k] == v for r in live)}
                continue
            if isinstance(st, _ast.For):
                # A loop nested in the span: its body is classified, it may
                # capture its own jumps, and it holds no transaction end and
                # no exit. Its `else:` is not a shape this walk classifies
                # (round 1, finding 2: a nested loop's `else: continue`).
                if st.orelse or _outer_jumps(st):
                    problems.append((st.lineno, "a continue or break for the "
                                     "formation loop inside a nested construct"))
                loop_head(st, state)
                nested(st.body, state)
                env = {k: v for k, v in env.items()
                       if k not in assigned([st])}
                continue
            if isinstance(st, (_ast.Assign, _ast.AnnAssign, _ast.AugAssign,
                               _ast.Expr, _ast.Pass)):
                env = simple(st, state, env)
                continue
            problems.append((st.lineno, "a statement this walk does not "
                             f"classify: {type(st).__name__}"))
            if _outer_jumps(st):
                problems.append((st.lineno, "a continue or break for the "
                                 "formation loop inside a nested construct"))
        return state, env

    def walk_off(stmts):
        r = walk(stmts, (), {})
        return None if r is None else r[0]

    off = walk_off(loop.body[barrier[0] + 1:])
    if off is not None:
        if ended(off) == "rollback":          # an implicit continue
            exits.append((loop.body[-1].lineno, "continue", "rollback", None))
            passed.add(off[-1][1])
        else:
            problems.append((loop.body[-1].lineno, "the attempt runs off the "
                             f"loop body after {ended(off) or 'no transaction end'}"))
    n_body = len(exits)
    body_breaks = list(breaks)
    if not loop.orelse:
        problems.append((loop.lineno, "no exhausted-attempts exit"))
    elif walk_off(loop.orelse) is not None:
        problems.append((loop.orelse[0].lineno,
                         "the exhausted-attempts path does not exit"))
    n_loop = len(exits)
    span = loop.body[barrier[0] + 1:] + loop.orelse
    if form == "team-resume":
        # "Falling through to fresh formation COMMITS rather than rolls back:
        # the resolver may have superseded zero-game husks on its way to
        # 'fresh', and that bookkeeping is real work." A rollback-ended
        # break reaches the same commit, so nothing on the way may await.
        block, at = _block_holding(tree, loop)
        after = block[at + 1:]
        span = span + after
        out = walk_off(after)
        if out is None or [kind for kind, _ln in out] != ["commit"]:
            problems.append((loop.lineno, "the resume does not fall through "
                             "to fresh formation after exactly one commit"))
        problems.extend((st.lineno, "awaits between the resume loop and its "
                         "fall-through commit") for st in after
                        if _txn_end(st) is None and _awaits(st))
    if gather or form == "team-fresh":
        block, at = _block_holding(tree, loop)
        after = block[at + 1:]
        acquire = [i for i, st in enumerate(after) if any(
            isinstance(c, _ast.Call) and isinstance(c.func, _ast.Name)
            and c.func.id == "_lease_acquire_many" for c in _ast.walk(st))]
        if not acquire:
            problems.append((loop.lineno, "no _lease_acquire_many after the "
                             "formation loop"))
        else:
            post = after[:acquire[0] + 1]
            span = span + post
            out = walk_off(post)
            if out is None:
                problems.append((post[-1].lineno, "no path after the loop "
                                 "reaches the formation writes"))
            elif out:
                problems.append((post[-1].lineno, "the formation passes its "
                                 f"lease acquisition after {ended(out)}"))
            # Round 2, finding 3: every rollback-ended break of the loop body
            # is walked into the statements after the loop with its own
            # state and bindings, so a break that rolled back and then
            # reaches the formation writes (`others = still` for
            # `others = []`) is refused there, not lost at the loop's end.
            # The break's bindings start from the literals bound before the
            # loop (`ordered = None`, `_formed = False`) for names the loop
            # body stores only right before a top-level `break` (the success
            # exit, after which no attempt follows), then the break's own
            # path's bindings.
            pre_env = {}
            for st in block[:at]:
                if isinstance(st, (_ast.Assign, _ast.AugAssign, _ast.AnnAssign)):
                    for nm in assigned([st]):
                        pre_env.pop(nm, None)
                    if (isinstance(st, _ast.Assign) and len(st.targets) == 1
                            and isinstance(st.targets[0], _ast.Name)):
                        try:
                            pre_env[st.targets[0].id] = _ast.literal_eval(st.value)
                        except (ValueError, TypeError, SyntaxError):
                            pass
                else:
                    for nm in assigned([st]):
                        pre_env.pop(nm, None)
            exit_only = {id(s) for k, s in enumerate(loop.body[:-1])
                         if isinstance(loop.body[k + 1], _ast.Break)}
            for s in loop.body + loop.orelse:
                if id(s) not in exit_only:
                    for nm in _cw.stores(s):
                        pre_env.pop(nm, None)
            for b_state, b_env, b_line in body_breaks:
                if not b_state:
                    continue
                mode["post"] = True
                keep = (list(exits), set(passed))
                r = walk(post, b_state, {**pre_env, **b_env})
                exits[:], kept = keep[0], keep[1]
                passed.clear()
                passed.update(kept)
                mode["post"] = False
                if r is not None:
                    problems.append((b_line, f"the break after {ended(b_state)} "
                                     "reaches the lease acquisition"))
    rollbacks = {n.lineno for st in span for n in _ast.walk(st)
                 if _txn_end(n) == "rollback"}
    return exits, n_body, n_loop, (rollbacks, passed), problems


def _is_matched_answer(node):
    value = getattr(node, "value", None)
    return (isinstance(node, _ast.Return) and isinstance(value, _ast.Call)
            and isinstance(value.func, _ast.Name)
            and value.func.id == "QueuePollResponse"
            and any(k.arg == "status" and isinstance(k.value, _ast.Constant)
                    and k.value.value == "matched" for k in value.keywords))


def _raises_detail(node, detail):
    """Whether `node` is `raise HTTPException(..., detail=<detail>)`."""
    exc = getattr(node, "exc", None)
    return isinstance(node, _ast.Raise) and any(
        k.arg == "detail" and isinstance(k.value, _ast.Constant)
        and k.value.value == detail for k in getattr(exc, "keywords", ()))


def formation_exit_violations(fn_src, form="return", scope=None):
    """The A1 rule over every exit formation_loop_exits derives, as sentences
    (empty when the handler keeps it): each exit after the barrier has
    rolled back, once, with no other transaction end on its path, except ONE
    success exit -- form "return": the exit that commits once and returns
    the matched answer; form "gather": the loop's `break` that ends nothing
    and carries the barrier to the formation writes -- and every rollback in
    the walked span lies on some exit's path, so the rollbacks are counted
    against the exits rather than against a number.

    Form "team" is team_queue_poll's two phases, "team-resume" and
    "team-fresh", each held to the gather form's rule, with the team
    resolver's two other designed outcomes accepted where the walk read
    them: 'relocked' (ended by the resolver's relock commit) and 'defer'
    (one commit, then the searching answer)."""
    if form == "team":
        return (formation_exit_violations(fn_src, "team-resume", scope)
                + formation_exit_violations(fn_src, "team-fresh", scope))
    exits, n_body, _n_loop, (rollbacks, passed), problems = (
        formation_loop_exits(fn_src, form, scope=scope))
    out = [f"line {ln}: {why}" for ln, why in problems]
    if form in ("gather", "team-resume", "team-fresh"):
        success = [n for _ln, k, e, n in exits[:n_body]
                   if k == "break" and e is None]
        if len(success) != 1:
            out.append(f"{len(success)} success exits (a break that ends "
                       f"nothing); the {form} form has exactly one")
            success = []
    else:
        commits = [n for _ln, _k, e, n in exits if e == "commit"]
        success = [n for n in commits if _is_matched_answer(n)]
        if len(commits) != 1:
            success = []
    for ln, kind, end, node in exits:
        if end == "rollback" or (success and node is success[0]):
            continue
        if (kind, end) in (("relocked", "relock"), ("defer", "commit")):
            continue                    # the resolver's, read by the walk
        out.append(f"line {ln}: {kind} after {end or 'no transaction end'}")
    if rollbacks != passed:
        out.append("rollback(s) on no exit path at line(s) "
                   f"{sorted(rollbacks - passed)}")
    return out


def test_the_formation_loop_is_bounded_and_rolls_back_rather_than_commits():
    """A1-BRIEF.md, 'Drift restarts are bounded': at most three attempts,
    every drift does rollback(), never commit(), and after the third,
    rollback and 503 queue_contended; acceptance item 1: no commit until
    success.

    Derived per exit since rehearsal round 7 (D5). The test counted
    `await db.rollback()` == 3 between the loop header and "# No match yet",
    a list of the exits A1 r2 had. The RJ server half added one when it met
    A1 (merge 137366c2, on main by 1eb1aac6): the admission gate inside
    _lease_acquire_many refuses, and the loser rolls back its whole
    transaction (RJ Stage 2 fix 1 H3) before its 503 admission_contended. That
    exit keeps this rule, and the count went red on it; on the same code the
    count reads 3 again, and passes, when that exit's rollback becomes a
    commit or the drift exit loses its rollback -- a number correlated with
    the rule, not the rule (#732). So each exit is derived and held to the
    rule, and the rollbacks are counted against the exits. Rehearsal-four
    round 1: a path keeps every transaction end it passes, so a commit
    placed before the drift exit's rollback is refused (finding 1), and a
    `continue` that leaves a nested loop's `else:` for the formation loop is
    refused as a shape the walk does not follow (finding 2)."""
    src = _inspect.getsource(main.queue_poll)
    assert "for _form_attempt in range(1, FORMATION_MAX_ATTEMPTS + 1):" in src
    assert 'raise HTTPException(status_code=503, detail="queue_contended")' in src
    bad = formation_exit_violations(src)
    assert bad == [], (
        "queue_poll's formation loop leaves its transaction other than by a "
        "rollback or the one success commit:\n  " + "\n  ".join(bad))
    exits, n_body, n_loop, (rollbacks, passed), _problems = (
        formation_loop_exits(src))
    # Not vacuous: the drift restart and the exhausted-attempts exit the
    # design names are among the derived exits, each after a rollback; the
    # one commit is the success return; every rollback is an exit's.
    kinds = [(k, e) for _ln, k, e, _n in exits]
    assert n_loop == len(exits), kinds
    assert ("continue", "rollback") in kinds[:n_body], kinds
    assert kinds[n_body:] == [("raise", "rollback")], kinds
    assert _raises_detail(exits[n_body][3], "queue_contended"), (
        _ast.unparse(exits[n_body][3]))
    assert [k for k, e in kinds if e == "commit"] == ["return"], kinds
    assert rollbacks and rollbacks == passed, (
        sorted(rollbacks), sorted(passed))


async def _sample_read(db):
    """A planted handler's invented helper that reads (the can-fail tests'
    scope, _SampleScope)."""
    return (await db.execute(text("SELECT 1"))).scalar()


async def _sample_write(db):
    """A planted handler's invented helper that writes."""
    await db.execute(text("UPDATE sample SET x = 1"))


async def _sample_commits(db):
    """A planted handler's invented helper that commits (round 2, finding 2:
    a helper committing before the drift rollback)."""
    await db.execute(text("UPDATE sample SET x = 1"))
    await db.commit()


def _sample_stale(row):
    """A planted handler's invented plain predicate (no session)."""
    return row is None


class _SampleScope:
    """The scope the can-fail tests' planted handlers resolve in: each
    invented helper reads, writes or commits as named here; every other name
    is main's."""
    _reads = {"discover", "drifted", "pending", "won_early", "consent",
              "leased", "early", "mine", "none", "other", "recheck"}

    def __getattr__(self, name):
        if name in self._reads:
            return _sample_read
        if name in ("settle", "write"):
            return _sample_write
        if name == "sync_state":
            return _sample_commits
        if name == "stale":
            return _sample_stale
        return getattr(main, name)


_SAMPLE = _SampleScope()


def test_the_formation_exit_oracle_can_fail():
    """Negative control (#391): one planted loop per way the rule can break,
    beside the shapes that keep it, each refused for its own reason."""
    NL = chr(10)

    def handler(body, orelse=("await db.rollback()",
                              'raise HTTPException(status_code=503, '
                              'detail="queue_contended")')):
        return NL.join(
            ["async def queue_poll(db):",
             "    for _form_attempt in range(1, FORMATION_MAX_ATTEMPTS + 1):",
             "        cand = await discover(db)",
             "        await _identity_lock_many(db, [cand])"]
            + ["        " + ln for ln in body]
            + ["    else:"] + ["        " + ln for ln in orelse])

    refuse = ["if (await _lease_acquire_many(db, [cand])) is False:",
              "    await db.rollback()",
              '    raise HTTPException(status_code=503, '
              'detail="admission_contended")']
    win = ["await db.commit()", 'return QueuePollResponse(status="matched")']
    drift = ["if await drifted(db):", "    await db.rollback()", "    continue"]
    assert formation_exit_violations(handler(drift + refuse + win), scope=_SAMPLE) == []
    # A nested loop's own break and continue stay inside it.
    own_jumps = ["for r in cand:", "    if r is None:", "        break",
                 "    if r:", "        continue"]
    assert formation_exit_violations(
        handler(own_jumps + drift + refuse + win), scope=_SAMPLE) == []

    planted = [
        # a drift exit that commits: publishes the half-formation
        ("continue after commit", handler(
            ["if await drifted(db):", "    await db.commit()", "    continue"]
            + refuse + win)),
        # finding 1: a commit placed immediately before the drift exit's
        # rollback; the rollback after it ends an empty transaction
        ("rollback after commit", handler(
            ["if await drifted(db):", "    await db.commit()",
             "    await db.rollback()", "    continue"] + refuse + win)),
        ("continue after commit, rollback", handler(
            ["if await drifted(db):", "    await db.commit()",
             "    await db.rollback()", "    continue"] + refuse + win)),
        # finding 2: the drift exit leaves through a nested loop's else,
        # with no rollback
        ("a continue or break for the formation loop inside a nested "
         "construct", handler(
             ["if await drifted(db):", "    for _never in ():",
              "        pass", "    else:", "        continue"]
             + refuse + win)),
        # the same through a while's else, and through a try
        ("a continue or break for the formation loop inside a nested "
         "construct", handler(
             ["while await pending(db):", "    await settle(db)",
              "else:", "    break"] + drift + refuse + win)),
        ("a continue or break for the formation loop inside a nested "
         "construct", handler(
             ["try:", "    if await drifted(db):", "        continue",
              "finally:", "    pass"] + refuse + win)),
        # a transaction end in a spelling the walk does not read
        ("a transaction end in a spelling this walk does not read",
         handler(["_ = await db.commit()"] + drift + refuse + win)),
        # a refusal that leaves with nothing ended: the writes stay pending
        ("raise after no transaction end", handler(
            drift + [refuse[0], refuse[2]] + win)),
        # a rollback that falls through into more work, barrier gone
        ("awaits after rollback", handler(
            ["if await drifted(db):", "    await db.rollback()",
             "await db.execute(write)"] + win)),
        ("rollback(s) on no exit path", handler(
            ["if await drifted(db):", "    await db.rollback()",
             "await db.execute(write)"] + win)),
        # a commit before success, with work after it
        ("awaits after commit", handler(["await db.commit()"] + drift + win)),
        # an exhausted-attempts exit with no rollback
        ("raise after no transaction end", handler(
            drift + win, orelse=['raise HTTPException(status_code=503, '
                                 'detail="queue_contended")'])),
        # two success commits
        ("return after commit", handler(
            ["if await won_early(db):", "    await db.commit()",
             '    return QueuePollResponse(status="matched")'] + drift + win)),
    ]
    for why, src in planted:
        bad = formation_exit_violations(src, scope=_SAMPLE)
        assert any(why in b for b in bad), (why, bad)


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
    """A1-BRIEF.md, 'Drift restarts are bounded': every drift does
    rollback(), never commit(); after the third, rollback and 503
    queue_contended. A commit inside the formation loop would publish a
    half-formation AND release the barrier -- option (a)'s failure, reached
    from inside the retry instead of from a helper.

    Derived per exit since rehearsal-four round 1 (finding 6). The test
    counted `await db.rollback()` >= 3 between the loop header and the lease
    acquisition, a slice that also holds the no-match exits' rollbacks, so
    with ovt_queue_poll's drift rollback deleted it read 4 and passed. Now
    the gather form of the exit walk holds each exit to the rule: every exit
    after the barrier rolls back, with no other transaction end on its path;
    the one success `break` ends nothing and carries the barrier through the
    formation writes to the lease acquisition, every exit on that way rolls
    back, and nothing ends the transaction before the acquisition. A gather
    site rediscovers after its rollback (_ffa_queue_poll_inner: "The
    rollback above is what makes the rediscovery legal"), so a plain read
    may follow a rollback there, and nothing else may."""
    src = _inspect.getsource(getattr(main, site))
    bad = formation_exit_violations(src, "gather")
    assert bad == [], (
        f"{site}'s formation leaves its transaction other than by a rollback "
        "or carries it past a transaction end:\n  " + "\n  ".join(bad))
    exits, n_body, n_loop, (rollbacks, passed), _problems = (
        formation_loop_exits(src, "gather"))
    kinds = [(k, e) for _ln, k, e, _n in exits]
    # Not vacuous: a drift restart after a rollback, the one success break,
    # the exhausted-attempts raise after a rollback, and exits after the loop
    # that end with the acquisition's own refusal, each after a rollback; and
    # every rollback in the span is an exit's.
    assert ("continue", "rollback") in kinds[:n_body], kinds
    assert kinds[:n_body].count(("break", None)) == 1, kinds
    assert kinds[n_body:n_loop] == [("raise", "rollback")], kinds
    assert _raises_detail(exits[n_body][3], "queue_contended"), (
        _ast.unparse(exits[n_body][3]))
    assert kinds[n_loop:] and kinds[-1] == ("raise", "rollback"), kinds
    assert _raises_detail(exits[-1][3], "admission_contended"), (
        _ast.unparse(exits[-1][3]))
    assert rollbacks and rollbacks == passed, (
        sorted(rollbacks), sorted(passed))


def _relock_outcome_problems(resolve_src, pick_src, relock_src, scope=None):
    """The team forms accept the resolver's 'relocked' answer as an exit
    whose transaction end is not in the poll, so that end is read where it
    is rather than assumed. The resolver (`resolve_src`) answers
    ("relocked", r) in exactly one place, with r bound in the statement
    before it to the answer of the relock helper (`relock_src`), whose one
    commit is its last await, right before its one return, the matched
    answer, and whose one rollback is followed by a raise; the resolver
    calls that helper only there. Every other
    answer of the resolver is a constant 'defer' or 'fresh', or the first
    answer of the family pick (`pick_src`), which answers only 'fresh',
    'defer' or 'picked'; neither the resolver nor the pick ends the
    transaction, so on 'fresh' and 'defer' the poll is what ends it. Returns
    problems as sentences, empty when the shape holds."""
    resolve, pick, relock = (_ast.parse(s).body[0]
                             for s in (resolve_src, pick_src, relock_src))
    out = [f"{fn.name} ends the transaction itself"
           for fn in (resolve, pick) if _ends_inside(fn)]
    # Both bodies are walked by the shared closed walk (round 3, finding
    # a1:2481: an awaited helper that commits, inserted into the real
    # resolver, passed this read). The relock helper's own body is read
    # below; at its one call only its arguments are classified.
    for fn in (resolve, pick):
        try:
            eff = _cw.def_effects(fn, main if scope is None else scope,
                                  _policy(scope), fn.name,
                                  opaque={relock.name, pick.name})
        except Unclassified as e:
            out.append(f"{fn.name}: {e.args[0][1]} (line {e.args[0][0]})")
            continue
        if eff & {"rollback-then-raise", "savepoint"}:
            out.append(f"{fn.name} ends the transaction itself")
    for st in _ast.walk(pick):
        value = getattr(st, "value", None)
        if isinstance(st, _ast.Return) and not (
                isinstance(value, _ast.Tuple) and len(value.elts) == 2
                and isinstance(value.elts[0], _ast.Constant)
                and value.elts[0].value in ("fresh", "defer", "picked")):
            out.append(f"{pick.name} line {st.lineno}: an answer this read "
                       "does not place")
    picked = {st.targets[0].elts[0].id for st in _ast.walk(resolve)
              if isinstance(st, _ast.Assign) and len(st.targets) == 1
              and isinstance(st.targets[0], _ast.Tuple)
              and isinstance(st.targets[0].elts[0], _ast.Name)
              and isinstance(st.value, _ast.Await)
              and _calls_named(st.value, pick.name)}
    relocked = []
    for st in _ast.walk(resolve):
        if not isinstance(st, _ast.Return):
            continue
        value = st.value
        first = (value.elts[0] if isinstance(value, _ast.Tuple)
                 and len(value.elts) == 2 else None)
        if isinstance(first, _ast.Constant) and first.value == "relocked":
            relocked.append(st)
        elif not ((isinstance(first, _ast.Constant)
                   and first.value in ("defer", "fresh"))
                  or (isinstance(first, _ast.Name) and first.id in picked)):
            out.append(f"{resolve.name} line {st.lineno}: an answer this read "
                       "does not place")
    relocks = [n for n in _ast.walk(resolve) if isinstance(n, _ast.Call)
               and isinstance(n.func, _ast.Name) and n.func.id == relock.name]
    if len(relocks) != 1:
        out.append(f"{resolve.name} calls {relock.name} {len(relocks)} "
                   "times; the read takes the one its 'relocked' answer "
                   "carries")
    if len(relocked) != 1:
        out.append(f"{resolve.name} answers 'relocked' in {len(relocked)} "
                   "places; the read takes one")
    else:
        ret = relocked[0]
        block, at = _block_holding(resolve, ret)
        prev = block[at - 1] if block and at else None
        name = ret.value.elts[1]
        call = getattr(getattr(prev, "value", None), "value", None)
        if not (isinstance(name, _ast.Name) and isinstance(prev, _ast.Assign)
                and len(prev.targets) == 1
                and isinstance(prev.targets[0], _ast.Name)
                and prev.targets[0].id == name.id
                and isinstance(prev.value, _ast.Await)
                and isinstance(call, _ast.Call)
                and isinstance(call.func, _ast.Name)
                and call.func.id == relock.name):
            out.append(f"{resolve.name}'s 'relocked' answer is not "
                       f"{relock.name}'s, bound in the statement before it")
    body = [st for st in relock.body if not (
        isinstance(st, _ast.Expr) and isinstance(st.value, _ast.Constant))]
    spellings = [n for n in _ast.walk(relock) if isinstance(n, _ast.Attribute)
                 and n.attr in ("commit", "rollback")]
    commits = [i for i, st in enumerate(body) if _txn_end(st) == "commit"]
    rollbacks = [n for n in _ast.walk(relock) if _txn_end(n) == "rollback"]
    returns = [n for n in _ast.walk(relock) if isinstance(n, _ast.Return)]
    if len(spellings) != 2 or len(commits) != 1 or len(rollbacks) != 1:
        out.append(f"{relock.name}: not one commit in its body and one "
                   "rollback, each a statement")
    else:
        tail = body[commits[0] + 1:]
        if not (tail and len(returns) == 1 and returns[0] is tail[-1]
                and _is_team_answer(tail[-1], "matched")
                and not any(_awaits(st) for st in tail)):
            out.append(f"{relock.name}: its commit is not its last await "
                       "before its one return, the matched answer")
        block, at = _block_holding(relock, rollbacks[0])
        if not (block and at + 1 < len(block)
                and isinstance(block[at + 1], _ast.Raise)):
            out.append(f"{relock.name}: its rollback is not followed by a "
                       "raise")
    return out


def test_team_formation_exits_roll_back_and_never_commit():
    """A1-BRIEF.md, 'Drift restarts are bounded', for team_queue_poll: every
    drift does rollback(), never commit(); after the budget is spent,
    rollback and 503 queue_contended.

    Per exit since rehearsal-four round 1 (item T). Its drift exits (at
    73a158b2, :49958 rollback then break, and :49962 rollback then continue)
    had no per-exit check: the walk read only `for _form_attempt` loops, and
    the budget test reads only the bound. The team form reads the poll's
    own shape (formation_loop_exits): two `while` loops spending one budget,
    each walked from its identity barrier; every exit after a barrier rolls
    back once with no other end on its path, except the designed outcomes:
    the resolver's 'relocked' and 'defer', the resume loop's 'fresh' break,
    which falls through to fresh formation after one commit, and the fresh
    loop's one success break, which carries the barrier through the
    resolver's outcomes and the formation writes to the lease acquisition.
    A shape the walk does not read is refused, never skipped."""
    src = _inspect.getsource(main.team_queue_poll)
    bad = formation_exit_violations(src, "team")
    assert bad == [], (
        "team_queue_poll's formation leaves its transaction other than by a "
        "rollback or a designed outcome:\n  " + "\n  ".join(bad))
    phases = {}
    for phase in ("team-resume", "team-fresh"):
        exits, n_body, n_loop, (rollbacks, passed), _problems = (
            formation_loop_exits(src, phase))
        kinds = [(k, e) for _ln, k, e, _n in exits]
        phases[phase] = (kinds[:n_body], kinds[n_body:n_loop], kinds[n_loop:])
        assert rollbacks and rollbacks == passed, (
            phase, sorted(rollbacks), sorted(passed))
    # Not vacuous. The resume: the consent re-read's restart and the
    # committed peer's break, each after a rollback; the resolver's three
    # outcomes; the exhausted-attempts raise after a rollback.
    body, spent, _after = phases["team-resume"]
    assert ("continue", "rollback") in body and ("break", "rollback") in body, body
    assert ("relocked", "relock") in body and ("defer", "commit") in body, body
    assert body.count(("break", None)) == 1, body
    assert spent == [("raise", "rollback")], spent
    # The fresh phase: the predicate drift's break and the roster drift's
    # restart, each after a rollback, and its one success break; after the
    # loop, the no-match answer after a rollback, the resolver's outcomes,
    # and the acquisition's refusal after a rollback.
    body, spent, after = phases["team-fresh"]
    assert ("break", "rollback") in body and ("continue", "rollback") in body, body
    assert body.count(("break", None)) == 1, body
    assert spent == [("raise", "rollback")], spent
    assert ("return", "rollback") in after, after
    assert ("relocked", "relock") in after and ("defer", "commit") in after, after
    assert after and after[-1] == ("raise", "rollback"), after
    problems = _relock_outcome_problems(*(
        _inspect.getsource(getattr(main, name)) for name in (
            "_team_resolve_live_family", "_team_lock_family_pick",
            "_team_relock_existing_series")))
    assert problems == [], problems


def _round2_a1_programs():
    """Rehearsal-four round 2's programs for findings 1 to 5, and the generic
    controls, as (form, the sentence the closed walk must give, source): each
    passed round 2's walk (tools: r2_old_vs_new.py) and each must fail this
    one. Templates as in the can-fail tests above; invented helpers resolve
    in _SampleScope."""
    NL = chr(10)
    spent = ["await db.rollback()",
             'raise HTTPException(status_code=503, detail="queue_contended")']

    def queue(body, barrier=("await _identity_lock_many(db, [cand])",)):
        return NL.join(
            ["async def queue_poll(db):",
             "    for _form_attempt in range(1, FORMATION_MAX_ATTEMPTS + 1):",
             "        cand = await discover(db)"]
            + ["        " + ln for ln in barrier]
            + ["        " + ln for ln in body]
            + ["    else:"] + ["        " + ln for ln in spent])

    def gather(body, after):
        return NL.join(
            ["async def ovt_queue_poll(db):", "    _formed = False",
             "    for _form_attempt in range(1, FORMATION_MAX_ATTEMPTS + 1):",
             "        rows = await discover(db)",
             "        await _identity_lock_many(db, rows)"]
            + ["        " + ln for ln in body]
            + ["    else:"] + ["        " + ln for ln in spent]
            + ["    " + ln for ln in after])

    def team(fresh, after, barrier=("await _identity_lock_many(db, cands)",),
             spend=("_form_left -= 1",)):
        resume = ["still = await consent(db)",
                  "if len(still) != len(present):", "    await db.rollback()",
                  "    continue",
                  "if await leased(db):", "    await db.rollback()", "    break",
                  "outcome, resp = await _team_resolve_live_family(db, present)",
                  'if outcome == "relocked":', "    return resp",
                  'if outcome == "defer":', "    await db.commit()",
                  '    return TeamQueuePollResponse(status="searching")',
                  "break"]
        return NL.join(
            ["async def team_queue_poll(db):",
             "    _form_left = FORMATION_MAX_ATTEMPTS",
             "    if dc_row is not None:",
             "        while _form_left > 0:",
             "            _form_left -= 1",
             "            present = await consent(db)",
             "            if len(present) < 3:",
             "                break",
             "            await _identity_lock_many(db, present)"]
            + ["            " + ln for ln in resume]
            + ["        else:"] + ["            " + ln for ln in spent]
            + ["        await db.commit()",
               "    others = None",
               "    _form_left = max(_form_left, 1)",
               "    while _form_left > 0:"]
            + ["        " + ln for ln in spend]
            + ["        cands = await discover(db)",
               "        if len(cands) < 3:",
               "            others = cands",
               "            break"]
            + ["        " + ln for ln in barrier]
            + ["        " + ln for ln in fresh]
            + ["    else:"] + ["        " + ln for ln in spent]
            + ["    " + ln for ln in after])

    drift = ["if await drifted(db):", "    await db.rollback()", "    continue"]
    refuse = ["if (await _lease_acquire_many(db, [cand])) is False:",
              "    await db.rollback()",
              'raise HTTPException(status_code=503, detail="admission_contended")']
    refuse[2] = "    " + refuse[2]
    win = ["await db.commit()", 'return QueuePollResponse(status="matched")']
    g_win = ["_formed = True", "break"]
    acquire = ["if (await _lease_acquire_many(db, rows)) is False:",
               "    await db.rollback()",
               '    raise HTTPException(status_code=503, '
               'detail="admission_contended")']
    g_after = (["if not _formed:", "    await db.rollback()",
                '    n = (await db.execute(text("SELECT COUNT(*) FROM q"))).scalar()',
                "    return n",
                'await db.execute(text("INSERT INTO s VALUES (1)"))'] + acquire)
    head = ["_mine = await mine(db)", "still = await recheck(db)"]
    pred = ["if stale(_mine):", "    await db.rollback()", "    others = []",
            "    break"]
    size = ["if len(still) != 3:", "    await db.rollback()", "    continue"]
    t_after = (["if len(others) < 3:", "    await db.rollback()",
                '    return TeamQueuePollResponse(status="searching")',
                'await db.execute(text("INSERT INTO s VALUES (1)"))']
               + [ln.replace("rows", "others") for ln in acquire])
    good = [
        ("return", queue(drift + refuse + win)),
        ("gather", gather(drift + g_win, g_after)),
        ("team", team(head + pred + size + ["others = still", "break"], t_after)),
    ]
    bad = [
        # finding 1 (a1:918): the barrier and a commit under `if True:`
        ("return", "the identity barrier is not the plain statement",
         queue(drift + refuse + win, barrier=(
             "if True:", "    await _identity_lock_many(db, [cand])",
             "    await db.commit()"))),
        ("team", "the identity barrier is not the plain statement",
         team(head + pred + size + ["others = still", "break"], t_after,
              barrier=("if True:", "    await _identity_lock_many(db, cands)",
                       "    await db.commit()"))),
        # finding 2 (a1:910): a helper that commits before the drift rollback
        ("return", "ends the transaction", queue(
            ["if await drifted(db):", "    await sync_state(db)",
             "    await db.rollback()", "    continue"] + refuse + win)),
        ("gather", "ends the transaction", gather(
            ["if await drifted(db):", "    await sync_state(db)",
             "    await db.rollback()", "    continue"] + g_win, g_after)),
        ("team", "ends the transaction", team(
            head + ["if stale(_mine):", "    await sync_state(db)",
                    "    await db.rollback()", "    others = []", "    break"]
            + size + ["others = still", "break"], t_after)),
        # finding 3 (a1:961): the drift break keeps the roster it rolled back
        ("team", "reaches the lease acquisition", team(
            head + ["if stale(_mine):", "    await db.rollback()",
                    "    others = still", "    break"]
            + size + ["others = still", "break"], t_after)),
        # finding 4 (a1:718): the budget refilled inside the loop
        ("team", "an assignment to the attempt budget this walk does not read",
         team(head + pred + size + ["others = still", "break"], t_after,
              spend=("_form_left -= 1", "_form_left = max(_form_left, 1)"))),
        # finding 5 (a1:590): a function that writes, inside a SELECT after
        # the rollback
        ("gather", "a SQL function off the read allow-list: lo_create", gather(
            ["if await drifted(db):", "    await db.rollback()",
             '    rows = (await db.execute(text("SELECT lo_create(0)"))).all()',
             "    if not rows:", "        break", "    continue"] + g_win,
            g_after)),
        # generic: constructs the walk has never met
        ("return", "a call of a computed callee", queue(
            ["(lambda: None)()"] + drift + refuse + win)),
        ("return", "a statement this walk does not classify: Match", queue(
            ["match cand:", "    case _:", "        pass"]
            + drift + refuse + win)),
        ("return", "a NamedExpr this walk does not classify", queue(
            ["if (hit := await drifted(db)):", "    await db.rollback()",
             "    continue"] + refuse + win)),
    ]
    return good, bad


def test_the_closed_walk_refuses_round_2s_programs():
    """Rehearsal-four round 2 (ruling REHEARSAL-FOUR-R2): the exit walk is
    closed. Every statement in a walked span is classified into a named
    shape (expr_effects, _helper_effects, _sql_kind) or the walk fails
    naming it. Each of the reviewer's programs for findings 1 to 5, and one
    construct of each kind the walk has never met (a lambda call, a match
    statement, an assignment expression), is refused for its own reason,
    beside the same templates kept whole, which pass."""
    good, bad = _round2_a1_programs()
    for form, src in good:
        assert formation_exit_violations(src, form, scope=_SAMPLE) == [], (
            form, formation_exit_violations(src, form, scope=_SAMPLE))
    for form, why, src in bad:
        got = formation_exit_violations(src, form, scope=_SAMPLE)
        assert any(why in b for b in got), (form, why, got)


def test_the_gather_exit_oracle_can_fail():
    """Negative control (#391) for the gather form: one planted handler per
    way the rule can break, beside the shapes that keep it, each refused for
    its own reason."""
    NL = chr(10)

    def gather(body, after, orelse=("await db.rollback()",
                                    'raise HTTPException(status_code=503, '
                                    'detail="queue_contended")')):
        return NL.join(
            ["async def ovt_queue_poll(db):",
             "    _formed = False",
             "    for _form_attempt in range(1, FORMATION_MAX_ATTEMPTS + 1):",
             "        rows = await discover(db)",
             "        await _identity_lock_many(db, rows)"]
            + ["        " + ln for ln in body]
            + ["    else:"] + ["        " + ln for ln in orelse]
            + ["    " + ln for ln in after])

    def bad_of(src):
        return formation_exit_violations(src, "gather", scope=_SAMPLE)

    drift = ["if await drifted(db):", "    await db.rollback()", "    continue"]
    rediscover = ["if await drifted(db):", "    await db.rollback()",
                  '    rows = (await db.execute(text("SELECT id FROM q"))).all()',
                  "    if not rows:", "        break", "    continue"]
    win = ["_formed = True", "break"]
    acquire = ["if (await _lease_acquire_many(db, rows)) is False:",
               "    await db.rollback()",
               '    raise HTTPException(status_code=503, '
               'detail="admission_contended")']
    after = (["if not _formed:", "    await db.rollback()",
              '    n = (await db.execute(text("SELECT COUNT(*) FROM q"))).scalar()',
              "    return n",
              'await db.execute(text("INSERT INTO s VALUES (1)"))']
             + acquire)
    assert bad_of(gather(drift + win, after)) == []
    assert bad_of(gather(rediscover + win, after)) == []

    planted = [
        # finding 6: the drift rollback deleted
        ("continue after no transaction end", gather(
            ["if await drifted(db):", "    continue"] + win, after)),
        # a commit placed before the drift rollback
        ("rollback after commit", gather(
            ["if await drifted(db):", "    await db.commit()",
             "    await db.rollback()", "    continue"] + win, after)),
        # a write, a locking read, or a lock after the drift rollback
        ("awaits after rollback", gather(
            ["if await drifted(db):", "    await db.rollback()",
             '    await db.execute(text("UPDATE q SET x = 1"))',
             "    continue"] + win, after)),
        ("awaits after rollback", gather(
            ["if await drifted(db):", "    await db.rollback()",
             '    await db.execute(text("SELECT id FROM q FOR UPDATE"))',
             "    continue"] + win, after)),
        ("awaits after rollback", gather(
            ["if await drifted(db):", "    await db.rollback()",
             "    await _identity_lock_many(db, rows)", "    continue"]
            + win, after)),
        # the drift exit through a nested loop's else
        ("a continue or break for the formation loop inside a nested "
         "construct", gather(
             ["if await drifted(db):", "    for _never in ():",
              "        pass", "    else:", "        continue"] + win, after)),
        # two success breaks, and none
        ("2 success exits", gather(
            ["if await early(db):", "    _formed = True", "    break"]
            + drift + win, after)),
        ("0 success exits", gather(
            drift + ["await db.rollback()", "_formed = True", "break"],
            after)),
        # an exhausted-attempts exit with no rollback
        ("raise after no transaction end", gather(
            drift + win, after, orelse=[
                'raise HTTPException(status_code=503, '
                'detail="queue_contended")'])),
        # after the loop: a no-match exit with no rollback, a commit before
        # the acquisition, an acquisition refusal that commits, and none
        ("return after no transaction end", gather(
            drift + win, ["if not _formed:", "    return 0"] + acquire)),
        ("awaits after commit", gather(
            drift + win, ["await db.commit()"] + after)),
        ("raise after commit", gather(
            drift + win, after[:-2] + ["    await db.commit()",
                                       after[-1]])),
        ("no _lease_acquire_many after the formation loop", gather(
            drift + win, ["return 1"])),
    ]
    for why, src in planted:
        bad = bad_of(src)
        assert any(why in b for b in bad), (why, bad)

    # A team-shaped sample (rehearsal-four round 1, item T): two `while`
    # loops spending one budget, the resolver's outcomes dispatched in the
    # resume loop and after the fresh one, beside one planted handler per
    # way the team form breaks, each refused for its own reason.
    def team(resume, fresh, after, fall=("await db.commit()",),
             spent=("await db.rollback()", 'raise HTTPException('
                    'status_code=503, detail="queue_contended")'),
             floor="_form_left = max(_form_left, 1)"):
        return NL.join(
            ["async def team_queue_poll(db):",
             "    _form_left = FORMATION_MAX_ATTEMPTS",
             "    if dc_row is not None:",
             "        while _form_left > 0:",
             "            _form_left -= 1",
             "            present = await consent(db)",
             "            if len(present) < 3:",
             "                break",
             "            await _identity_lock_many(db, present)"]
            + ["            " + ln for ln in resume]
            + ["        else:"] + ["            " + ln for ln in spent]
            + ["        " + ln for ln in fall]
            + ["    others = None",
               "    " + floor,
               "    while _form_left > 0:",
               "        _form_left -= 1",
               "        cands = await discover(db)",
               "        if len(cands) < 3:",
               "            others = cands",
               "            break",
               "        await _identity_lock_many(db, cands)"]
            + ["        " + ln for ln in fresh]
            + ["    else:"] + ["        " + ln for ln in spent]
            + ["    " + ln for ln in after])

    def team_bad(src):
        return formation_exit_violations(src, "team", scope=_SAMPLE)

    consent = ["still = await consent(db)",
               "if len(still) != len(present):", "    await db.rollback()",
               "    continue"]
    peer = ["if await leased(db):", "    await db.rollback()", "    break"]
    relocked = ['if outcome == "relocked":', "    return resp"]
    defer = ['if outcome == "defer":', "    await db.commit()",
             '    return TeamQueuePollResponse(status="searching")']
    resolve = "outcome, resp = await _team_resolve_live_family(db, present)"
    resume = consent + peer + [resolve] + relocked + defer + ["break"]
    pred = ["if stale(_mine):", "    await db.rollback()", "    others = []",
            "    break"]
    size = ["if len(still) != 3:", "    await db.rollback()", "    continue"]
    head = ["_mine = await mine(db)", "still = await recheck(db)"]
    fresh = head + pred + size + ["others = still", "break"]
    team_after = (["if len(others) < 3:", "    await db.rollback()",
                   '    return TeamQueuePollResponse(status="searching")',
                   "fam, fam_resp = await _team_resolve_live_family(db, others)",
                   'if fam == "relocked":', "    return fam_resp",
                   'if fam == "defer":', "    await db.commit()",
                   '    return TeamQueuePollResponse(status="searching")',
                   'await db.execute(text("INSERT INTO s VALUES (1)"))']
                  + acquire)
    assert team_bad(team(resume, fresh, team_after)) == []

    team_planted = [
        # item T's mutants: the predicate drift's rollback deleted (t1), the
        # roster drift's rollback deleted (t2), a commit placed before it (t3)
        ("2 success exits", team(resume, head + [
            "if stale(_mine):", "    others = []", "    break"]
            + size + ["others = still", "break"], team_after)),
        ("continue after no transaction end", team(resume, head + pred + [
            "if len(still) != 3:", "    continue", "others = still",
            "break"], team_after)),
        ("rollback after commit", team(resume, head + pred + [
            "if len(still) != 3:", "    await db.commit()",
            "    await db.rollback()", "    continue", "others = still",
            "break"], team_after)),
        # the resume loop's drift restart and committed-peer break without
        # their rollbacks, and its exhausted-attempts exit without one
        ("continue after no transaction end", team(
            ["still = await consent(db)", "if len(still) != len(present):",
             "    continue"] + peer + [resolve] + relocked + defer + ["break"],
            fresh, team_after)),
        ("2 success exits", team(
            consent + ["if await leased(db):", "    break", resolve]
            + relocked + defer + ["break"], fresh, team_after)),
        ("raise after no transaction end", team(resume, fresh, team_after,
            spent=('raise HTTPException(status_code=503, '
                   'detail="queue_contended")',))),
        # the fall-through without its commit, and with work before it
        ("the resume does not fall through to fresh formation after exactly "
         "one commit", team(resume, fresh, team_after, fall=("pass",))),
        ("awaits between the resume loop and its fall-through commit", team(
            resume, fresh, team_after,
            fall=("await write(db)", "await db.commit()"))),
        # outcomes the walk does not read: a relocked answer that commits
        # again, a defer that rolls back, an answer left unread
        ("a resolver call this walk does not read", team(
            consent + peer + [resolve, 'if outcome == "relocked":',
                              "    await db.commit()", "    return resp"]
            + defer + ["break"], fresh, team_after)),
        ("a resolver call this walk does not read", team(
            consent + peer + [resolve] + relocked
            + ['if outcome == "defer":', "    await db.rollback()",
               '    return TeamQueuePollResponse(status="searching")', "break"],
            fresh, team_after)),
        ("a resolver call this walk does not read", team(resume, fresh, [
            "await _team_resolve_live_family(db, others)"] + team_after)),
        # the budget: a second opening, a store the walk does not read, a
        # third loop over it
        ("attempt budget openings", team(resume, fresh, team_after,
                                         floor="_form_left = FORMATION_MAX_ATTEMPTS")),
        ("an assignment to the attempt budget this walk does not read", team(
            resume, fresh, team_after, floor="_form_left = 3")),
        ("3 loops over the attempt budget", team(resume, fresh, [
            "while _form_left > 0:", "    _form_left -= 1"] + team_after)),
        # a barrier outside the two loops: a formation the walk would not read
        ("3 identity barriers", team(resume, fresh, [
            "await _identity_lock_many(db, others)"] + team_after)),
    ]
    for why, src in team_planted:
        bad = team_bad(src)
        assert any(why in b for b in bad), (why, bad)

    # The 'relocked' end, read in the resolver (_relock_outcome_problems).
    resolve_src = NL.join([
        "async def resolve(db):",
        "    outcome, row = await pick(db)",
        '    if outcome != "picked":',
        "        return (outcome, None)",
        "    if await leased(db):",
        '        return ("defer", None)',
        "    resp = await relock(db, row)",
        '    return ("relocked", resp)'])
    pick_src = NL.join([
        "async def pick(db):",
        "    if await none(db):",
        '        return ("fresh", None)',
        '    await db.execute(text("UPDATE team_series SET status = 1"))',
        '    return ("picked", 1)'])
    relock_src = NL.join([
        "async def relock(db, row):",
        "    if (await _lease_acquire_many(db, row)) is False:",
        "        await db.rollback()",
        '        raise HTTPException(status_code=503, detail="admission_contended")',
        '    await db.execute(text("UPDATE team_queue SET status = 1"))',
        "    await db.commit()",
        "    team = 1",
        '    return TeamQueuePollResponse(status="matched")'])
    assert _relock_outcome_problems(resolve_src, pick_src, relock_src,
                                    _SAMPLE) == []
    relock_planted = [
        ("answers 'relocked' in 0 places", resolve_src.replace(
            '("relocked", resp)', '("defer", resp)'), pick_src, relock_src),
        ("answer is not relock's", resolve_src.replace(
            "resp = await relock(db, row)", "resp = await other(db, row)"),
         pick_src, relock_src),
        # the relock's commit taken on the way to another answer
        ("calls relock 2 times", resolve_src.replace(
            "    if await leased(db):", "    await relock(db, row)" + NL
            + "    if await leased(db):"), pick_src, relock_src),
        ("an answer this read does not place", resolve_src.replace(
            '("defer", None)', '(state, None)'), pick_src, relock_src),
        ("pick ends the transaction itself", resolve_src, pick_src.replace(
            '    return ("picked", 1)', '    await db.commit()' + NL
            + '    return ("picked", 1)'), relock_src),
        ("pick line 5: an answer this read does not place", resolve_src,
         pick_src.replace('("picked", 1)', '("relocked", 1)'), relock_src),
        ("its commit is not its last await", resolve_src, pick_src,
         relock_src.replace("    team = 1", "    await write(db)")),
        ("not one commit in its body and one rollback", resolve_src,
         pick_src, relock_src.replace("    await db.commit()" + NL, "")),
        ("its rollback is not followed by a raise", resolve_src, pick_src,
         relock_src.replace('        raise HTTPException(status_code=503, '
                            'detail="admission_contended")',
                            "        return None")),
    ]
    for why, *srcs in relock_planted:
        got = _relock_outcome_problems(*srcs, scope=_SAMPLE)
        assert any(why in p for p in got), (why, got)


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
# What proves a seat free. _formation_lease_conflict is A1 r2's proof.
# _lease_admission_gate is RJ Stage 2 fix 1 H3's (e73ac345, on main by
# 1eb1aac6): "one per-player transaction gate ... followed by a post-gate
# recheck of live hold, queue and lease, the loser rolling back its whole
# transaction" (ai-collab/integrity-1001/CODEX-RJ-STAGE2-SERVER-FIX1-AUTHOR-
# BRIEF.md, H3). Under the players row locks it refuses every live lease the
# keys it is given do not admit -- for the FFA readmission claim the one key
# (ffa, its lobby), the check _formation_lease_conflict makes with that key
# as `allow` -- and every committed queue row and open match hold outside
# them. NX0c (203fe9e3) put that claim behind it directly, and
# test_match_hold_admission_gate_pg's CENSUS records the form for _rdm_claim
# (the gate, its refusal, then _lease_acquire with _gate_held=True). Knowing
# only the A1 proof, this oracle named _rdm_claim ungated (rehearsal round 7,
# D5).
_GATE = _re.compile(
    r"await\s+(?:_formation_lease_conflict|_lease_admission_gate)\(")

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

    A function GATES if it calls _formation_lease_conflict or
    _lease_admission_gate itself, or calls another function in main.py that
    gates. The closure is a fixpoint so the depth of the indirection does not
    matter; today it is one level. The two primitives never gate here,
    although each runs _lease_admission_gate by default: their refusal is a
    False return, and only the CALLER can roll its roster writes back (H3's
    shared form), so their own gate proves nothing for a caller, and counting
    it would make every caller of _lease_acquire_many a gater by closure.
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
            if _GATE.search(ln) and name not in _NOT_A_FORMATION:
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
    # The primitives' default gate is no proof for their callers (see
    # commitment_points); if it counted, the closure would excuse every
    # caller of _lease_acquire_many.
    assert not gaters & set(_NOT_A_FORMATION), sorted(gaters & set(_NOT_A_FORMATION))


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


# --- merged fix 1b: rated-FFA proximity admission -------------------------

def _fix1b_calls(function_name, callee):
    tree = _ast.parse(_inspect.getsource(getattr(main, function_name)))
    return [node for node in _ast.walk(tree)
            if isinstance(node, _ast.Call)
            and getattr(node.func, "id", None) == callee]


def test_fix1b_r1_floor_is_independent_inert_and_complete():
    assert main.FFA_PROXIMITY_VICTIM_MIN_VERSION == main.MIN_MOD_VERSION == "1.38.7"
    floor = main.MIN_MOD_VERSION
    assert main._ffa_roster_clears_proximity_floor([floor, "v" + floor, "V" + floor], 3)
    assert not main._ffa_roster_clears_proximity_floor([floor, "1.38.6", floor], 3)
    assert not main._ffa_roster_clears_proximity_floor([floor, floor], 3)
    helper = _ast.parse(_inspect.getsource(main._ffa_roster_clears_proximity_floor))
    assert not any(isinstance(node, _ast.Await) for node in _ast.walk(helper))


def test_fix1b_r1_hosted_lock_freezes_the_queue_floor_once():
    calls = _fix1b_calls("_ffa_lock_roster", "_ffa_roster_clears_proximity_floor")
    assert len(calls) == 1
    assert _ast.unparse(calls[0]) == \
        "_ffa_roster_clears_proximity_floor(_kt_vals, len(ordered))"
    src = " ".join(_inspect.getsource(main._ffa_lock_roster).split())
    assert "is_ranked=COALESCE(is_ranked, TRUE) AND CAST(:proximity_capable AS boolean)" in src
    assert "RETURNING is_ranked" in src
    assert '"proximity_capable": _ranked_floor_ok' in src
    assert src.index("_ffa_roster_clears_proximity_floor") < src.index("SET status='active'")
    assert src.index("RETURNING is_ranked") < src.index("_bind_lobby_bets")


def test_fix1b_r1_automatic_lock_freezes_the_queue_floor_once():
    calls = _fix1b_calls("_ffa_queue_poll_inner", "_ffa_roster_clears_proximity_floor")
    assert len(calls) == 1
    assert _ast.unparse(calls[0]) == \
        "_ffa_roster_clears_proximity_floor(_kt_vals, len(ordered))"
    src = " ".join(_inspect.getsource(main._ffa_queue_poll_inner).split())
    assert "kills_tiebreak, is_ranked, assembly_v1" in src
    assert ":proximity_capable, FALSE, FALSE" in src
    assert '"proximity_capable": _proximity_capable' in src
    assert src.index("_ffa_roster_clears_proximity_floor") < src.index("INSERT INTO ffa_lobbies")


def test_fix1b_r1_locked_payload_names_only_an_unranked_refusal():
    src = _inspect.getsource(main._ffa_poll_locked_payload)
    assert '"lobby_ranked": _lobby_ranked' in src
    assert '**({"ranked_refusal": "unranked"} if not _lobby_ranked else {})' in src


def test_fix1b_r2_reform_copy_ands_rating_and_gates_the_wager_move():
    lock_src = _inspect.getsource(main._ffa_lock_roster)
    assert "_ranked_floor_ok = _proximity_capable" in lock_src
    assert "if reform_of is None else True" not in lock_src

    src = _inspect.getsource(main._asm_reform)
    tree = _ast.parse(src)
    gates = [node for node in _ast.walk(tree) if isinstance(node, _ast.If)
             and _ast.unparse(node.test) == "_locked_ranked"]
    assert len(gates) == 1
    rated = _ast.unparse(_ast.Module(body=gates[0].body, type_ignores=[]))
    unrated = _ast.unparse(_ast.Module(body=gates[0].orelse, type_ignores=[]))
    move = "UPDATE ffa_bets SET lobby_id = :new WHERE lobby_id = :old AND settled_at IS NULL"
    assert move in " ".join(rated.split())
    assert move not in " ".join(unrated.split())
    assert "_refund_ffa_lobby_bets(ctx.db, old, 'lobby_casual')" in unrated
    assert "refund_all_reason='lobby_casual'" in unrated
    assert "ctx.refund_flush = True" in unrated
    assert "_refund_ffa_game_bets_strict" not in src
    assert src.count("UPDATE ffa_bets SET lobby_id = :new") == 1
    assert main._ASM_REFORM_CLASSES["COPY_AND"] == \
        ("is_ranked", "kills_tiebreak", "sudden_death")


def test_fix1b_r3_locked_rejoin_rechecks_under_locks_before_any_write():
    src = _inspect.getsource(main.ffa_queue_join)
    compact = " ".join(src.split())
    assert src.count("_current_mod_version.get()") == 1
    assert '"mv": _join_mv' in src
    calls = _fix1b_calls("ffa_queue_join", "_ffa_roster_clears_proximity_floor")
    assert len(calls) == 1
    assert _ast.unparse(calls[0]) == \
        "_ffa_roster_clears_proximity_floor([_join_mv], 1)"

    identity = src.index("_enrollment_identity_gate")
    lobby_lock = src.index("FROM ffa_lobbies")
    queue_lock = src.index("FROM ffa_queue", lobby_lock)
    guard = src.index("_ffa_roster_clears_proximity_floor")
    husk = src.index("_lease_live_mode")
    upsert = src.index("INSERT INTO ffa_queue")
    assert identity < lobby_lock < queue_lock < guard < husk < upsert
    assert compact.count("FOR NO KEY UPDATE") == 2
    assert '_locked_queue["status"] == "ready_join"' in src
    assert '_locked_queue["series_id"] != _locked_hint["series_id"]' in src
    assert '_locked_lobby["status"] == "active"' in src
    refusal = "You're locked into another FFA game — finish or leave it first"
    assert src.count(refusal) == 2
    assert refusal in _inspect.getsource(main._ffa_lobby_enroll_caller)


def test_fix1b_r4_null_stays_below_every_floor_consumer():
    assert not main._ffa_roster_clears_proximity_floor([None], 1)
    assert not main._ffa_roster_clears_proximity_floor([""], 1)
    assert not main._ffa_roster_clears_proximity_floor(["not-a-version"], 1)
    expected = {
        "_ffa_lock_roster": "_ffa_roster_clears_proximity_floor(_kt_vals, len(ordered))",
        "_ffa_queue_poll_inner": "_ffa_roster_clears_proximity_floor(_kt_vals, len(ordered))",
        "ffa_queue_join": "_ffa_roster_clears_proximity_floor([_join_mv], 1)",
    }
    for function_name, expression in expected.items():
        calls = _fix1b_calls(function_name, "_ffa_roster_clears_proximity_floor")
        assert len(calls) == 1, function_name
        assert _ast.unparse(calls[0]) == expression, function_name


def test_the_node_table_names_every_concrete_ast_class():
    """Ruling REHEARSAL-FOUR-R3 (a): every concrete node class of the running
    interpreter's ast module is in closed_walk.NODE_TABLE with a rule, so no
    construct is accepted by omission; a class a newer interpreter adds
    fails here until it is given a rule."""
    assert _cw.table_gaps() == [], _cw.table_gaps()
    assert set(_cw.NODE_TABLE.values()) <= {
        "leaf", "children", "call", "await", "lambda", "comp", "stmt", "refuse"}


_R3_HELPER_SRC = chr(10).join([
    "async def finish(db):",
    "    await db.commit()",
    "async def cbhelper(db, callback=None):",
    "    if callback is not None:",
    "        await callback(db)",
    "async def defaulthelper(db, callback=finish):",
    "    await callback(db)",
    "async def matchhelper(db):",
    "    match 1:",
    "        case _:",
    "            pass",
    "async def lambdahelper(db):",
    "    (lambda: None)()",
    "async def walrushelper(db):",
    "    if (hit := 1):",
    "        pass",
    "async def yieldhelper(db):",
    "    yield 1",
    "async def defaultspelling(db, end=None):",
    "    x = db.commit",
    "async def comphelper(db):",
    "    return [await db.commit() for _ in [1]]",
    "async def committing(db):",
    "    await sync_state(db)",
    ""])


def _r3_scope():
    """A scope whose helpers are _R3_HELPER_SRC's, then _SAMPLE's."""
    import linecache as _linecache
    import types as _types
    mod = _types.ModuleType("r3_helpers")
    mod.__file__ = "<r3_helpers>"
    _linecache.cache[mod.__file__] = (len(_R3_HELPER_SRC), None,
                                      _R3_HELPER_SRC.splitlines(True), mod.__file__)
    import sys as _sys
    _sys.modules[mod.__name__] = mod
    exec(compile(_R3_HELPER_SRC, mod.__file__, "exec"), mod.__dict__)
    mod.sync_state = _sample_commits

    class Scope:
        def __getattr__(self, name):
            return getattr(mod, name) if hasattr(mod, name) else getattr(_SAMPLE, name)

    return Scope()


def _round3_a1_programs():
    """Rehearsal-four round 3's programs (the reviewer's a1 findings and the
    sitting's three probes) and one program per argument kind and per
    mutating method, as (form, a sentence the shared visitor must give,
    source): each must be refused. Templates are round 2's good programs."""
    NL = chr(10)
    good, _bad = _round2_a1_programs()
    q, g, t = good[0][1], good[1][1], good[2][1]
    drift_line = "        if await drifted(db):"
    assert q.count(drift_line) == 1 and g.count(drift_line) == 1

    def before_drift(src, line):
        return src.replace(drift_line, "        " + line + NL + drift_line)

    barrier = "        await _identity_lock_many(db, [cand])"
    assert q.count(barrier) == 1
    sql = '"SELECT COUNT(*) FROM q"'
    assert g.count(sql) == 1
    drop = "            others = []" + NL + "            break"
    assert t.count(drop) == 1
    out = [
        # a1:1397: every argument kind of the barrier call
        ("return", "a transaction end in a spelling", q.replace(
            barrier, "        await _identity_lock_many(db, [cand], "
                     "timeout_ms=(await db.commit()))")),
        ("return", "the barrier has unpacked arguments", q.replace(
            barrier, "        await _identity_lock_many(db, *[[cand]])")),
        ("return", "the barrier has unpacked arguments", q.replace(
            barrier, "        await _identity_lock_many(db, [cand], **{})")),
        # a1:914: helper bodies are closed
        ("return", "a Match this walk does not classify",
         before_drift(q, "await matchhelper(db)")),
        ("return", "a call of a computed callee",
         before_drift(q, "await lambdahelper(db)")),
        ("return", "a NamedExpr this walk does not classify",
         before_drift(q, "await walrushelper(db)")),
        ("return", "an awaited call this walk does not classify: yieldhelper",
         before_drift(q, "await yieldhelper(db)")),
        ("return", "a transaction word in a spelling",
         before_drift(q, "await defaultspelling(db)")),
        ("return", "ends the transaction (.commit)",
         before_drift(q, "await comphelper(db)")),
        ("return", "ends the transaction (.commit)",
         before_drift(q, "await committing(db)")),
        # probe P3: a callback through ** or a parameter default
        ("return", "a call of cbhelper with unpacked arguments",
         before_drift(q, "await cbhelper(db, **{'callback': finish})")),
        ("return", "a call of cbhelper with unpacked arguments",
         before_drift(q, "await cbhelper(*[db])")),
        ("return", "has a default the walk does not classify",
         before_drift(q, "await defaulthelper(db)")),
        # argument kinds in a step: a lambda's default, a comprehension
        ("return", "a transaction end in a spelling this walk does not read",
         before_drift(q, "f = (lambda x=(await db.commit()): x)")),
        ("return", "a transaction end in a spelling this walk does not read",
         before_drift(q, "xs = [await db.commit() for _ in [1]]")),
        # a1:672 and probe P2: SQL after the gather rollback, lexer-first
        ("gather", "a SQL function off the read allow-list: lo_create",
         g.replace(sql, repr('SELECT "lo_create"(0)'))),
        ("gather", "a SQL function off the read allow-list: lo_create",
         g.replace(sql, repr("SELECT '/*' || lo_create(0)::text || '*/'"))),
        ("gather", "awaits after rollback",
         g.replace(sql, repr("SELECT 1 INTO tmp_probe"))),
        ("gather", "awaits after rollback",
         g.replace(sql, repr("CREATE TEMP TABLE p AS SELECT 1"))),
    ]
    # probe P1 and ruling item (b): a mutating method on a carried name
    for m in ("append(still)", "extend(still)", "update(still)", "clear()",
              "pop()", "setdefault(1, still)", "insert(0, still)"):
        out.append(("team", "reaches the lease acquisition", t.replace(
            drop, "            others = []" + NL + "            others." + m + NL
            + "            break")))
    for op in ("+=", "|="):
        out.append(("team", "reaches the lease acquisition", t.replace(
            drop, "            others = []" + NL + f"            others {op} still"
            + NL + "            break")))
    return out


def test_the_shared_visitor_refuses_round_3s_programs():
    """Rehearsal-four round 3 (ruling REHEARSAL-FOUR-R3): the reviewer's a1
    programs and the sitting's probes, one program per argument kind and one
    per mutating method, each refused by the shared visitor for its own
    reason; round 2's good templates still pass."""
    scope = _r3_scope()
    good, _bad = _round2_a1_programs()
    for form, src in good:
        assert formation_exit_violations(src, form, scope=scope) == [], form
    for form, why, src in _round3_a1_programs():
        got = formation_exit_violations(src, form, scope=scope)
        assert any(why in b for b in got), (form, why, got)


def test_the_resolver_walk_reads_an_awaited_committing_helper():
    """Round 3, finding a1:2481: an awaited helper that commits, inserted
    into the real resolver and into the real family pick, is refused."""
    names = ("_team_resolve_live_family", "_team_lock_family_pick",
             "_team_relock_existing_series")
    srcs = [_inspect.getsource(getattr(main, n)) for n in names]
    assert _relock_outcome_problems(*srcs) == []
    for k in (0, 1):
        tree = _ast.parse(_textwrap.dedent(srcs[k]))
        fn = tree.body[0]
        fn.body.insert(1, _ast.parse("await sync_state(db)").body[0])
        mutated = list(srcs)
        mutated[k] = _ast.unparse(tree)
        got = _relock_outcome_problems(*mutated, scope=_SAMPLE)
        assert any("ends the transaction" in g for g in got), (names[k], got)
