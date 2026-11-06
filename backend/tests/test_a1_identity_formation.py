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


def _txn_end(node, b):
    """'commit' or 'rollback' when `node` is the statement `await db.commit()`
    or `await db.rollback()`, else None; `db` read through `b`, the walked
    function's closed_walk.Bindings, as its own parameter bound once
    (ruling REHEARSAL-FOUR-R5, fix 1)."""
    call = (node.value.value if isinstance(node, _ast.Expr)
            and isinstance(node.value, _ast.Await) else None)
    if (isinstance(call, _ast.Call) and not call.args and not call.keywords
            and isinstance(call.func, _ast.Attribute)
            and b.spelled_once(call.func.value, "db", ("param",))
            and call.func.attr in ("commit", "rollback")):
        return call.func.attr
    return None


def _handler_bindings(tree, scope):
    """closed_walk.Bindings of the one definition `tree` (a parsed handler
    source) holds: the one resolver every spelling the a1 walk reads goes
    through (ruling REHEARSAL-FOUR-R5, fix 1); refused for a source that is
    not exactly one definition."""
    if not (len(tree.body) == 1 and isinstance(
            tree.body[0], (_ast.FunctionDef, _ast.AsyncFunctionDef))):
        raise Unclassified((0, "a walked source that is not one definition"))
    return _cw.Bindings(scope, tree.body[0],
                        grammar=_policy(scope).grammar)


def _binding_problems(b, line=0):
    """(line, why) for a session `db` that is not the walked function's own
    parameter bound once. Round 7 (ruling REHEARSAL-FOUR-R6 (1)(c)) deleted
    the loop that proved each name the walk reads as the module's unbound:
    the grammar's binding rule refuses every binding of a meaningful
    spelling (grammar_shapes_a1.A1_MEANINGFUL holds them) before the walk."""
    out = []
    if not b.is_param("db"):
        out.append((line, "the session db is not the walked function's own "
                          "parameter, bound once"))
    return out


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
import identity_binder as _a1_ib  # noqa: E402


class _A1OwnSource:
    """Round 11 (ruling FOUR-R10-A2, FIX-R11-ID; the class of finding
    closed_walk:1125): the a1 walks' one source reader. inspect.getsource
    and inspect.getsourcelines unwrap __wrapped__ and return ANOTHER body
    than the one that runs; here a function's source is the source of its
    OWN code object, and the function must be the definition its module's
    source makes (identity_binder.trusted_function: no wrapper layer, no
    closure, its code equal to a fresh compile). Every other attribute is
    the inspect module's."""

    def __getattr__(self, name):
        return getattr(_a1_real_inspect, name)

    @staticmethod
    def _own(obj):
        if isinstance(obj, _a1_real_inspect.types.FunctionType):
            if not _a1_ib.trusted_function(obj):
                raise Unclassified((0, f"{obj.__code__.co_name}: not the "
                                       "definition its module's source "
                                       "makes"))
            return obj.__code__
        return obj

    def getsource(self, obj):
        return _a1_real_inspect.getsource(self._own(obj))

    def getsourcelines(self, obj):
        return _a1_real_inspect.getsourcelines(self._own(obj))


_a1_real_inspect = _inspect
_inspect = _A1OwnSource()
import grammar_shapes_a1 as _gs  # noqa: E402
import ro_covered as _ro  # noqa: E402
import match_hold as _a1_match_hold  # noqa: E402
# The frozen providers of the pure tables (round 10, ruling REHEARSAL-R9-A1
# (D)), bound by these static imports.
import builtins as _a1_builtins  # noqa: E402
import datetime as _a1_datetime  # noqa: E402
import json as _a1_json  # noqa: E402
import random as _a1_random  # noqa: E402
import time as _a1_time  # noqa: E402
import uuid as _a1_uuid  # noqa: E402
from fastapi import HTTPException as _a1_HTTPException  # noqa: E402
import models as _a1_models  # noqa: E402
import schemas as _a1_schemas  # noqa: E402
# The planted sample helpers below (_sample_read and its siblings) call
# `text`; round 9 left the name unbound in this module and the walk accepted
# the spelling. It is SQLAlchemy's, through ro_covered's own import.
from ro_covered import text  # noqa: E402
import match_report_window as _a1_mrw  # noqa: E402
import tournaments as _a1_tournaments  # noqa: E402

# The frozen callee table (round 8, ruling REHEARSAL-FOUR-R7-A1, M4):
# grammar_shapes_a1.A1_CALLEES names each form and its frozen span; the
# functions are bound HERE, by this file's static imports, and the two are
# asserted to agree (test_r8_the_callee_table_is_the_frozen_one). The walks
# import nothing and look up no attribute by a name read from a tree.
_A1_CALLEES = {
    "from tournaments import _region_candidate_volumes":
        _a1_tournaments._region_candidate_volumes,
    "_match_hold._hold_latch": _a1_match_hold._hold_latch,
    "_mrw_mod().series_fresh": _a1_mrw.series_fresh,
    "_mrw_mod().series_holds": _a1_mrw.series_holds,
}


# The default-deny grammar of the a1 walks (ruling REHEARSAL-FOUR-R6
# (1)(b)): every span the walks below visit (a handler, the resolver, the
# family pick, the relock helper, every helper body def_effects descends
# into, a builder's or a module accessor's body) is admitted by it BEFORE
# any walker reasoning: every node's shape in the frozen whitelist
# (grammar_shapes_a1.A1_SHAPES, generated once from the real spans at
# a30d37f6 by RF/r7/ga1/gen_shapes.py), every meaningful store and every
# transaction end at a frozen anchor (round 8, M3), every callee outside a
# module's own namespace through the frozen callee table (M4), every
# constructor-pure class in a complete frozen definition scope (M5). A
# refusal names the file, the line and the shape or anchor.
def _a1_grammar():
    return _cw.Grammar(_gs.A1_SHAPES, _gs.A1_MEANINGFUL, _gs.A1_BINDINGS,
                       _A1_CALLEES, _gs.A1_NAMEDTUPLES)


_A1_GRAMMAR = _a1_grammar()


def _admit_source(d, scope, src):
    """Admit the parsed definition `d` of source `src` under the grammar of
    the a1 policy over `scope`: positioned at its real file and line when
    `src` is exactly the source of the scope's same-named function, else as
    planted."""
    scope = main if scope is None else scope
    fn = getattr(scope, getattr(d, "name", ""), None)
    where = ("<planted>", 0)
    if _inspect.isfunction(fn):
        try:
            if _inspect.getsource(fn) == src:
                where = _cw.source_of(fn)
        except (OSError, TypeError):
            pass
    _policy(scope).grammar.admit(d, *where)


def _admit_handler(tree, scope, src):
    """Admit the one definition a parsed handler source holds; refused
    (Unclassified) for anything else, or by the grammar."""
    if not (len(tree.body) == 1 and isinstance(
            tree.body[0], (_ast.FunctionDef, _ast.AsyncFunctionDef))):
        raise Unclassified((0, "a walked source that is not one definition"))
    _admit_source(tree.body[0], scope, src)


# The frozen lookup table (round 8, ruling REHEARSAL-FOUR-R7-A1 M1, revised
# by R-A; closed_walk.Bindings.execute_kind): a position (file, line, end
# line) answers 'read' when it is in ro_covered.COVERED and green under the
# read-only role, 'lock' when it is in ro_covered.WRITERS; every other
# execute, a covered position the role did not reach and a position in no
# table included, is 'write'. The static S analysis is retired.
_A1_TABLE = _ro.lookup_table()
_A1_READS = frozenset(p for p, k in _A1_TABLE.items() if k == "read")

# Plain calls a step may make that touch no session: builtins and the clock,
# id and log functions the spans use. Round 10 (ruling REHEARSAL-R9-A1 (D);
# finding closed_walk:859): each spelling maps to its frozen provider, one
# object per component of the spelling, bound HERE by this file's own static
# imports; closed_walk.Bindings.listed admits a call only when the walked
# scope's binding of the spelling IS that provider, so a module binding
# `int = writer` refuses every `int(...)` the walk meets.
# grammar_providers.PROVIDERS names each provider by (module, qualified
# name), and test_r10_pure_providers_are_the_frozen_ones asserts they agree.
# `text` is SQLAlchemy's, read through ro_covered's own import of it (this
# file's import forms are frozen by the DSN census); StakeRefundRefused is
# main's own class, bound here by its static import and pinned by the test
# to main's one top-level class statement of that name.
_PURE_CALLS = {
    "GoldTransaction": (_a1_models.GoldTransaction,),
    "HTTPException": (_a1_HTTPException,),
    "QueuePollResponse": (_a1_schemas.QueuePollResponse,),
    "StakeRefundRefused": (main.StakeRefundRefused,),
    "TeamQueuePollResponse": (_a1_schemas.TeamQueuePollResponse,),
    "ValueError": (_a1_builtins.ValueError,),
    "_json.loads": (_a1_json, _a1_json.loads),
    "all": (_a1_builtins.all,), "any": (_a1_builtins.any,),
    "bool": (_a1_builtins.bool,),
    "datetime.now": (_a1_datetime.datetime, _a1_datetime.datetime.now),
    "dict": (_a1_builtins.dict,), "enumerate": (_a1_builtins.enumerate,),
    "float": (_a1_builtins.float,), "int": (_a1_builtins.int,),
    "isinstance": (_a1_builtins.isinstance,), "len": (_a1_builtins.len,),
    "list": (_a1_builtins.list,), "min": (_a1_builtins.min,),
    "next": (_a1_builtins.next,), "print": (_a1_builtins.print,),
    "random.choice": (_a1_random, _a1_random.choice),
    "round": (_a1_builtins.round,), "set": (_a1_builtins.set,),
    "sorted": (_a1_builtins.sorted,), "str": (_a1_builtins.str,),
    "text": (_ro.text,),
    "time.monotonic": (_a1_time, _a1_time.monotonic),
    "time.time": (_a1_time, _a1_time.time),
    "type": (_a1_builtins.type,),
    "uuid.UUID": (_a1_uuid, _a1_uuid.UUID),
    "uuid.uuid4": (_a1_uuid, _a1_uuid.uuid4),
    "uuid_mod.uuid4": (_a1_uuid, _a1_uuid.uuid4)}
# Methods a step may call on a local value (rows, lists, dicts, strings).
_PURE_METHODS = frozenset({"add", "all", "append", "extend", "fetchall",
    "first", "get", "intersection", "items", "join", "lower", "lstrip",
    "mappings", "one", "replace", "scalar", "scalar_one", "scalars", "sort",
    "strip", "timestamp", "update", "values"})
# Awaited library calls a helper may make that touch no session (round 10:
# with their frozen providers, as _PURE_CALLS).
_PURE_AWAITS = {"asyncio.sleep": (asyncio, asyncio.sleep)}


def _policy(scope=None):
    """The a1 walk's policy over `scope` (main by default). One policy per
    scope, so its helper cache and met-shape counter persist."""
    scope = main if scope is None else scope
    key = id(scope)
    if key not in _POLICIES:
        _POLICIES[key] = _cw.Policy(scope, _PURE_CALLS, _PURE_METHODS,
                                    _PURE_AWAITS, _A1_TABLE)
        _POLICIES[key].grammar = _A1_GRAMMAR
    return _POLICIES[key]


_POLICIES = {}


@pytest.fixture
def structural_only(monkeypatch):
    """The a1 walks' STRUCTURAL rules alone, for the controls of rounds 1 to
    5 (ruling REHEARSAL-FOUR-R6 (1)(b) keeps the structural exit logic, over
    grammar-admitted spans). Those controls plant small synthetic handlers
    and helpers; none is a real span, so the frozen grammar refuses each at
    its first shape (its root's body set) before any structural rule could
    speak. Here the grammar RECORDS instead, so each older program still
    reaches the rule it was written for. Every finding of rounds 1 to 6 this
    child owns is ALSO a round-7 control under the frozen grammar
    (test_r7_a1_findings_are_refused_under_the_frozen_grammar). The
    recording grammar keeps the frozen callee table (round 8, M4): it is
    the only route to a callee outside a module's own namespace."""
    import sys as _sys
    me = _sys.modules[__name__]
    none = frozenset()
    g = _cw.Grammar(none, none, none, _A1_CALLEES, record=True)
    monkeypatch.setattr(me, "_A1_GRAMMAR", g)
    monkeypatch.setattr(me, "_POLICIES", {})


def _is_db_call(call, attr):
    return _cw.is_db_call(call, attr)


def _helper_effects(fn, scope=None):
    """closed_walk.helper_effects under the a1 policy."""
    return _cw.helper_effects(fn, _policy(scope))


def expr_effects(node, scope=None, opaque=frozenset(), bindings=None):
    """closed_walk.expr_effects under the a1 policy: the (shape, effect) list
    of evaluating `node` under `bindings`, the handler's Bindings; raises
    Unclassified naming the construct and its line."""
    return _cw.expr_effects(node, _policy(scope), opaque=opaque,
                            bindings=bindings)


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


def _calls_named(node, name, b):
    """Whether `node` holds a call of the plain name `name`, the module's
    (read through `b`, the walked function's Bindings)."""
    return any(isinstance(n, _ast.Call) and b.spelled(n.func, name)
               for n in _ast.walk(node))


def _calls_supplied(node, d, b):
    """Round 11: whether `node` holds a call of definition `d`, a helper
    the caller supplies and reads separately (the family pick), read
    through `b` (Bindings.supplied, as the walk's opaque branch reads it):
    a planted pick is no definition of the module's."""
    return any(isinstance(n, _ast.Call) and b.supplied(n.func, d)
               for n in _ast.walk(node))


def _is_team_answer(node, status, b):
    """Whether `node` is `return TeamQueuePollResponse(status=<status>, ...)`,
    the answer class the module's (read through `b`)."""
    value = getattr(node, "value", None)
    return (isinstance(node, _ast.Return) and isinstance(value, _ast.Call)
            and b.spelled(value.func, "TeamQueuePollResponse")
            and any(k.arg == "status" and isinstance(k.value, _ast.Constant)
                    and k.value.value == status for k in value.keywords))


def _resolver_dispatch(stmts, i, b):
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
    ('defer', None)".

    Names read through `b`, the handler's Bindings: the resolver the
    module's, <o> and <r> two locals each bound exactly once (ruling
    REHEARSAL-FOUR-R5, fix 1), so `<o>, <o> = ...` is refused."""
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
            and b.spelled(call.func, TEAM_RESOLVER)):
        return None
    outcome, answer = target.elts

    def branch(node, word, size):
        test = getattr(node, "test", None)
        return (isinstance(node, _ast.If) and not node.orelse
                and len(node.body) == size
                and isinstance(test, _ast.Compare)
                and b.same(test.left, outcome, ("local",))
                and len(test.ops) == 1
                and isinstance(test.ops[0], _ast.Eq)
                and isinstance(test.comparators[0], _ast.Constant)
                and test.comparators[0].value == word)

    ret = rel.body[0] if branch(rel, "relocked", 1) else None
    if not (isinstance(ret, _ast.Return)
            and b.same(ret.value, answer, ("local",))):
        return None
    if not (branch(dfr, "defer", 2) and _txn_end(dfr.body[0], b) == "commit"
            and _is_team_answer(dfr.body[1], "searching", b)):
        return None
    return ret, dfr


def _team_formation_loops(fn_src, tree, b):
    """team_queue_poll's two formation loops, resume then fresh, read as the
    poll spends them: ONE attempt budget (_attempt_budgets: one opening, one
    counter) across exactly two `while <counter> > 0:` loops, each spending
    it as its first statement, with the counter stored nowhere else but its
    opening and the fresh phase's floor of one attempt (`<counter> =
    max(<counter>, 1)`), and every _identity_lock_many call in the poll one
    of the loops' barriers, one statement in each loop's body, so no
    formation is left outside the walk. Returns (loops, None), or ([],
    (line, why)) for any other shape.

    The budget is the one name the walk reads with every binding
    (`b.every_binding`, ruling REHEARSAL-FOUR-R5 fix 1): each of its
    bindings is a local the walk accounts for by node, never by spelling;
    every other name it reads goes through `b` as the module's."""
    try:
        return _team_formation_loops_read(fn_src, tree, b)
    except Unclassified as e:
        return [], e.args[0]


def _team_formation_loops_read(fn_src, tree, b):
    openings, counters, _whiles = _attempt_budgets(fn_src)
    if len(openings) != 1 or len(counters) != 1:
        return [], (0, f"{len(openings)} attempt budget openings over "
                       f"{sorted(counters)}; the team form spends one")
    (counter,) = counters
    bindings = {id(x) for x in b.every_binding(counter, ("local",))}
    loops = sorted((n for n in _ast.walk(tree) if isinstance(n, _ast.While)
                    and b.reads(n.test, counter)),
                   key=lambda n: n.lineno)
    if len(loops) != 2:
        return [], (0, f"{len(loops)} loops over the attempt budget; the "
                       "team form has two")
    stores = set()
    for n in loops:
        if not (b.text(n.test) == f"{counter} > 0"
                and b.text(n.body[0]) == f"{counter} -= 1"):
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
                and id(n.targets[0]) in bindings
                and b.text(n.value) in ("FORMATION_MAX_ATTEMPTS",
                                        f"max({counter}, 1)")):
            stores.add(id(n.targets[0]))
    for n in _ast.walk(tree):
        if id(n) in bindings and id(n) not in stores:
            return [], (n.lineno, "an assignment to the attempt budget this "
                                  "walk does not read")
    barriers = [n for n in _ast.walk(tree) if isinstance(n, _ast.Call)
                and b.spelled(n.func, "_identity_lock_many")]
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
    # Ruling REHEARSAL-FOUR-R5, fix 1: every spelling below is read through
    # the handler's one resolver, and every name the walk reads as the
    # module's is first proved unbound by the handler.
    try:
        _admit_handler(tree, scope, fn_src)
        b = _handler_bindings(tree, scope)
    except Unclassified as e:
        return [], 0, 0, (set(), set()), [e.args[0]]
    bad = _binding_problems(b)
    if bad:
        return [], 0, 0, (set(), set()), bad
    if team:
        loops, why = _team_formation_loops(fn_src, tree, b)
        if why is not None:
            return [], 0, 0, (set(), set()), [why]
        loop = loops[1] if form == "team-fresh" else loops[0]
    else:
        try:
            loops = [n for n in _ast.walk(tree) if isinstance(n, _ast.For)
                     and b.spelled_once(n.target, "_form_attempt", ("local",))]
        except Unclassified as e:
            return [], 0, 0, (set(), set()), [e.args[0]]
        if len(loops) != 1:
            return [], 0, 0, (set(), set()), [(0, f"{len(loops)} formation loops")]
        loop = loops[0]
    barrier = [i for i, st in enumerate(loop.body) if any(
        isinstance(c, _ast.Call) and b.spelled(c.func, "_identity_lock_many")
        for c in _ast.walk(st))]
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
            and b.spelled(bcall.func, "_identity_lock_many")):
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
                if b.session_value(a):
                    # the session only as the barrier's own same-named
                    # parameter (ruling REHEARSAL-FOUR-R5, fix 1)
                    b.session_root_ok(a, bst.lineno)
                    b.session_argument(bcall, a, b.callee(bcall.func),
                                       bst.lineno)
                    continue
                if any(sh != "call" for sh, _e in expr_effects(
                        a, scope, bindings=b)):
                    problems.append((bst.lineno, "the barrier's arguments await"))
        except Unclassified as e:
            problems.append((e.args[0][0] or bst.lineno, e.args[0][1]))
        shapes["barrier"] += 1

    def ended(state):
        return ", ".join(kind for kind, _ln in state) or None

    def effects_of(node, line, opaque=frozenset()):
        # An unclassified construct is reported where it stands; if it
        # awaits, it also counts as an await on the path, so a path that
        # ended the transaction still reports it. Its names resolve through
        # the handler's bindings (finding a1:665).
        try:
            return expr_effects(node, scope, opaque, bindings=b)
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
            elif (_txn_end(st, b) is not None
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
                not b.spelled(c.func, "len")
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
                                     else st, TEAM_RESOLVER, b):
                try:
                    shape = _resolver_dispatch(stmts, i, b)
                except Unclassified as e:
                    problems.append((e.args[0][0] or st.lineno, e.args[0][1]))
                    continue
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
                # The resolver call itself through the shared visitor, its
                # body opaque here (read by _relock_outcome_problems): an
                # unpacked argument is refused there, never collected into a
                # tuple of values (finding a1:1119).
                eff = [e for e in effects_of(st.value, st.lineno,
                                             frozenset({TEAM_RESOLVER}))
                       if e != (f"helper:{TEAM_RESOLVER}", "opaque")]
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
            kind = _txn_end(st, b)
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
                        if _txn_end(st, b) is None and _awaits(st))
    if gather or form == "team-fresh":
        block, at = _block_holding(tree, loop)
        after = block[at + 1:]
        acquire = [i for i, st in enumerate(after) if any(
            isinstance(c, _ast.Call) and b.spelled(c.func, "_lease_acquire_many")
            for c in _ast.walk(st))]
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
                 if _txn_end(n, b) == "rollback"}
    return exits, n_body, n_loop, (rollbacks, passed), problems


def _is_matched_answer(node, b):
    value = getattr(node, "value", None)
    return (isinstance(node, _ast.Return) and isinstance(value, _ast.Call)
            and b.spelled(value.func, "QueuePollResponse")
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
        b = (_handler_bindings(_ast.parse(fn_src),
                               main if scope is None else scope)
             if commits else None)
        success = [n for n in commits if _is_matched_answer(n, b)]
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

    def __binder_address__(self, name):
        """Round 11 (FIX-R11-ID): where each name this scope answers is
        defined, for the identity binder: (module, qualified name)."""
        if name in self._reads:
            return (__name__, "_sample_read")
        if name in ("settle", "write"):
            return (__name__, "_sample_write")
        if name == "sync_state":
            return (__name__, "_sample_commits")
        if name == "stale":
            return (__name__, "_sample_stale")
        return ("main", name)


_SAMPLE = _SampleScope()


def test_the_formation_exit_oracle_can_fail(structural_only):
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
    _admit_handler(tree, None, fn_src)
    # the constant read through the handler's resolver as the module's
    # (ruling REHEARSAL-FOUR-R5, fix 1)
    # round 11 (FIX-R11-ID): resolved in main, the module whose handlers
    # these are; a walk with no scope bound its names by spelling alone
    b = _handler_bindings(tree, main)
    openings, counters, loops = [], set(), []
    for node in _ast.walk(tree):
        if isinstance(node, _ast.For) and b.reads(
                node.iter, "FORMATION_MAX_ATTEMPTS"):
            openings.append(_ast.unparse(node.iter))
        elif isinstance(node, _ast.Assign) and b.spelled(
                node.value, "FORMATION_MAX_ATTEMPTS"):
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
    for d, s in zip((resolve, pick, relock),
                    (resolve_src, pick_src, relock_src)):
        try:
            _admit_source(d, scope, s)
        except Unclassified as e:
            return [f"{d.name}: {e.args[0][1]} (line {e.args[0][0]})"]
    # Ruling REHEARSAL-FOUR-R5, fix 1: each body's spellings are read
    # through its own resolver, the module names proved unbound first.
    grammar = _policy(scope).grammar
    rb = _cw.Bindings(main if scope is None else scope, resolve,
                      grammar=grammar)
    lb = _cw.Bindings(main if scope is None else scope, relock,
                      grammar=grammar)
    bad = ([f"{resolve.name}: {why} (line {ln})" for ln, why in
            _binding_problems(rb)]
           + [f"{relock.name}: {why} (line {ln})" for ln, why in
              _binding_problems(lb)])
    if bad:
        return bad
    out = [f"{fn.name} ends the transaction itself"
           for fn in (resolve, pick) if _ends_inside(fn)]
    # Both bodies are walked by the shared closed walk (round 3, finding
    # a1:2481: an awaited helper that commits, inserted into the real
    # resolver, passed this read). The relock helper's own body is read
    # below; at its one call only its arguments are classified.
    # Round 11 (F10): the two opaque helpers' receiver conditions are read
    # from their bodies FIRST and declared on the policy, so the resolver's
    # walk discharges each at the helper's call (closed_walk's opaque
    # branch); the pick is walked before the resolver for the same reason.
    pol = _policy(scope)
    declared = pol.__dict__.setdefault("opaque_receivers", {})
    rbody = [st for st in relock.body if not (
        isinstance(st, _ast.Expr) and isinstance(st.value, _ast.Constant))]
    rcommit = [st for st in rbody if _txn_end(st, lb) == "commit"]
    rroll = [x for x in _ast.walk(relock) if _txn_end(x, lb) == "rollback"]
    if len(rcommit) == 1 and len(rroll) == 1:
        try:
            reff = _cw.def_effects(relock, main if scope is None else scope,
                                   pol, relock.name, receivers=True,
                                   ends=frozenset({id(rcommit[0].value),
                                                   id(rroll[0].value)}))
        except Unclassified:
            pass                            # reported by the read below
        else:
            declared[id(relock)] = (relock, frozenset(
                e for e in reff if e.startswith("receiver:")))
    for fn in (pick, resolve):
        try:
            eff = _cw.def_effects(fn, main if scope is None else scope,
                                  pol, fn.name, receivers=fn is pick,
                                  opaque={relock.name: relock, pick.name: pick})
        except Unclassified as e:
            out.append(f"{fn.name}: {e.args[0][1]} (line {e.args[0][0]})")
            continue
        if fn is pick:
            declared[id(pick)] = (pick, frozenset(
                e for e in eff if e.startswith("receiver:")))
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
              and _calls_supplied(st.value, pick, rb)}
    for nm in sorted(picked):
        try:
            rb.spelled_once(_ast.Name(id=nm, ctx=_ast.Load()), nm, ("local",))
        except Unclassified as e:
            return out + [f"{resolve.name}: {e.args[0][1]}"]
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
                  or rb.spelled_in(first, picked, ("local",)) is not None):
            out.append(f"{resolve.name} line {st.lineno}: an answer this read "
                       "does not place")
    relocks = [n for n in _ast.walk(resolve) if isinstance(n, _ast.Call)
               and rb.supplied(n.func, relock)]
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
        try:
            same = (isinstance(prev, _ast.Assign) and len(prev.targets) == 1
                    and rb.same(prev.targets[0], name, ("local",)))
        except Unclassified as e:
            out.append(f"{resolve.name}: {e.args[0][1]}")
            same = False
        if not (same and isinstance(prev.value, _ast.Await)
                and isinstance(call, _ast.Call)
                and rb.supplied(call.func, relock)):
            out.append(f"{resolve.name}'s 'relocked' answer is not "
                       f"{relock.name}'s, bound in the statement before it")
    body = [st for st in relock.body if not (
        isinstance(st, _ast.Expr) and isinstance(st.value, _ast.Constant))]
    spellings = [n for n in _ast.walk(relock) if isinstance(n, _ast.Attribute)
                 and n.attr in ("commit", "rollback")]
    commits = [i for i, st in enumerate(body) if _txn_end(st, lb) == "commit"]
    rollbacks = [n for n in _ast.walk(relock) if _txn_end(n, lb) == "rollback"]
    returns = [n for n in _ast.walk(relock) if isinstance(n, _ast.Return)]
    if len(spellings) != 2 or len(commits) != 1 or len(rollbacks) != 1:
        out.append(f"{relock.name}: not one commit in its body and one "
                   "rollback, each a statement")
    else:
        tail = body[commits[0] + 1:]
        if not (tail and len(returns) == 1 and returns[0] is tail[-1]
                and _is_team_answer(tail[-1], "matched", lb)
                and not any(_awaits(st) for st in tail)):
            out.append(f"{relock.name}: its commit is not its last await "
                       "before its one return, the matched answer")
        block, at = _block_holding(relock, rollbacks[0])
        if not (block and at + 1 < len(block)
                and isinstance(block[at + 1], _ast.Raise)):
            out.append(f"{relock.name}: its rollback is not followed by a "
                       "raise")
        # Its body through the shared visitor (finding a1:2095: it was
        # opaque at its call and read here only by structure): every
        # construct classified, and the one commit and the one rollback read
        # above are the only transaction ends it takes (a savepoint block
        # ends none). Its writes are the relock itself (the series and its
        # rows re-formed).
        try:
            eff = _cw.def_effects(relock, main if scope is None else scope,
                                  _policy(scope), relock.name, receivers=True,
                                  ends=frozenset({id(body[commits[0]].value),
                                                  id(rollbacks[0].value)}))
        except Unclassified as e:
            out.append(f"{relock.name}: {e.args[0][1]} (line {e.args[0][0]})")
        else:
            # its receiver conditions: discharged at its call in the
            # resolver's walk above (declared before that walk)
            other = sorted(e for e in eff - {
                "read", "lock", "write", "await", "commit",
                "rollback-then-raise", "savepoint"}
                if not (e.startswith("receiver:") and declared.get(
                    id(relock), (None,))[0] is relock))
            if other:
                out.append(f"{relock.name} takes {', '.join(other)}")
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
                '    n = 0',
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
        # the rollback. Round 8 (M1): no SQL text is read; the planted
        # execute stands at no frozen read position, so the lookup makes it
        # a write and allowed() (after a gather rollback only plain reads
        # and plain calls) refuses it
        ("gather", "awaits after rollback", gather(
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


def test_the_closed_walk_refuses_round_2s_programs(structural_only):
    """Rehearsal-four round 2 (ruling REHEARSAL-FOUR-R2): the exit walk is
    closed. Every statement in a walked span is classified into a named
    shape (expr_effects, _helper_effects, the frozen execute lookup) or
    the walk fails
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


def test_the_gather_exit_oracle_can_fail(structural_only):
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
              '    n = 0',
              "    return n",
              'await db.execute(text("INSERT INTO s VALUES (1)"))']
             + acquire)
    assert bad_of(gather(drift + win, after)) == []
    # round 8 (M1): the planted rediscovery stands at no frozen read
    # position, so it is a write after the drift rollback (allowed())
    assert bad_of(gather(rediscover + win, after)) == [
        "line 8: awaits after rollback"]

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
    # round 9 (G3): the callee read through the handler's resolver
    # round 11 (FIX-R11-ID): resolved in main, the module whose handlers
    # these are; a walk with no scope bound its names by spelling alone
    b = _handler_bindings(tree, main)
    lease = "_formation_lease_conflict"
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
            hit = b.spelled(node.func, lease)
            if isinstance(node.func, _ast.Attribute) and node.func.attr == lease:
                hit = True
            if self.depth and hit is True:
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
            if a <= ln and ln <= b and (best is None or a > best[0]):
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
    # P under the grammar (ruling REHEARSAL-FOUR-R6 (1)(b)): the decision's
    # body is admitted by the a1 grammar, then walked whole by the shared
    # visitor as a plain function, and takes no effect.
    assert _cw.plain_effects(main._ffa_gather_decide, _policy()) == frozenset()


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
    tree = _ast.parse(_textwrap.dedent(_inspect.getsource(
        getattr(main, function_name))))
    # round 9 (G3): the callee read through the handler's resolver
    # round 11 (FIX-R11-ID): resolved in main, the module whose handlers
    # these are; a walk with no scope bound its names by spelling alone
    b = _handler_bindings(tree, main)
    return [node for node in _ast.walk(tree)
            if isinstance(node, _ast.Call) and b.spelled(node.func, callee)]


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
    _a1_ib.register_source(mod, _R3_HELPER_SRC, mod.__file__)
    exec(compile(_R3_HELPER_SRC, mod.__file__, "exec"), mod.__dict__)
    mod.sync_state = _sample_commits

    class Scope:
        def __getattr__(self, name):
            return getattr(mod, name) if hasattr(mod, name) else getattr(_SAMPLE, name)

        def __binder_address__(self, name):
            # round 11 (FIX-R11-ID): the binder's address of each name
            if name == "sync_state":
                return (__name__, "_sample_commits")
            if hasattr(mod, name):
                return (mod.__name__, name)
            return _SAMPLE.__binder_address__(name)

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


def test_the_shared_visitor_refuses_round_3s_programs(structural_only):
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


def test_the_resolver_walk_reads_an_awaited_committing_helper(structural_only):
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


# --- ruling REHEARSAL-FOUR-R4 item 1: the acceptance bound ----------------

# The names of the bound, spelled by joining so this test's own source is not
# a reference it then counts.
_ACC = "".join(["Accep", "ted"])
_TOKEN = "".join(["_ACCEPT", "_TOKEN"])
_SEEN = "".join(["_walked", "_nodes"])


def acceptance_sites(sources):
    """Every place in `sources` ({module name: source text}) that can bring
    an acceptance outcome into being, by AST: a reference, in any spelling,
    to closed_walk's acceptance class or its token (a bare name in
    closed_walk, a name imported from it under any alias, an attribute of
    the closed_walk module under any alias, or a string constant naming
    one, as a getattr would), and any reference to the visitor's record of
    walked nodes outside closed_walk. Each site is (module, the qualified
    name of the function holding it, what it references, line). The class
    definition itself is not a site."""
    out = []
    for mod, text in sources.items():
        tree = _ast.parse(text)
        own = mod == "closed_walk"
        names = {_ACC: _ACC, _TOKEN: _TOKEN} if own else {}
        modules = set()
        for n in _ast.walk(tree):
            if isinstance(n, _ast.ImportFrom) and n.module == "closed_walk":
                for a in n.names:
                    if a.name in (_ACC, _TOKEN, "*"):
                        names[a.asname or a.name] = a.name
            elif isinstance(n, _ast.Import):
                for a in n.names:
                    if a.name == "closed_walk":
                        modules.add(a.asname or a.name)

        def visit(node, where):
            for c in _ast.iter_child_nodes(node):
                inner = where
                if isinstance(c, (_ast.FunctionDef, _ast.AsyncFunctionDef,
                                  _ast.ClassDef)):
                    inner = f"{where}.{c.name}" if where else c.name
                    if own and isinstance(c, _ast.ClassDef) and c.name == _ACC:
                        # the definition: its own token check is a site
                        visit(c, inner)
                        continue
                ref = None
                if (own and not where and isinstance(c, _ast.Name)
                        and c.id == _TOKEN and isinstance(c.ctx, _ast.Store)):
                    pass        # the token's one module-level definition
                elif isinstance(c, _ast.Name) and c.id in names:
                    ref = names[c.id]
                elif (isinstance(c, _ast.Attribute) and c.attr in (_ACC, _TOKEN)
                      and isinstance(c.value, _ast.Name) and c.value.id in modules):
                    ref = c.attr
                elif isinstance(c, _ast.Attribute) and c.attr == _SEEN and not own:
                    ref = _SEEN
                elif (isinstance(c, _ast.Constant) and isinstance(c.value, str)
                      and c.value in (_ACC, _TOKEN, _SEEN)):
                    ref = f"the string {c.value!r}"
                if ref is not None:
                    out.append((mod, where, ref, getattr(c, "lineno", 0)))
                visit(c, inner)

        visit(tree, "")
    return out


def _lane_sources():
    """Every Python module of the backend's api and tests directories."""
    import pathlib
    here = pathlib.Path(__file__).resolve().parent
    out = {}
    for d in (here, here.parent / "api"):
        for p in sorted(d.glob("*.py")):
            out[p.stem] = p.read_text(encoding="utf-8")
    return out


def test_closed_walk_acceptance_bound():
    """Ruling REHEARSAL-FOUR-R4 item 1. An acceptance outcome of the closed
    walk (closed_walk's acceptance class) is constructed in exactly one
    function, Visitor.accept, which walks the expression (or the helper
    body) and refuses any expression inside it that the walk did not
    classify; every other module can only pass one on or refuse. Every
    reference to the class or its token, in any spelling, across the api
    and tests modules is enumerated by AST and must be exactly: the token
    check in the class's own constructor, and the one construction in
    Visitor.accept. A negative control plants a construction in the gate
    file's source and in a1's and must be found."""
    sources = _lane_sources()
    sites = sorted(acceptance_sites(sources))
    expected = [("closed_walk", f"{_ACC}.__init__", _TOKEN),
                ("closed_walk", "Visitor.accept", _ACC),
                ("closed_walk", "Visitor.accept", _TOKEN)]
    assert [(m, w, r) for m, w, r, _ln in sites] == sorted(expected), sites
    # The runtime check behind it: a construction outside accept refuses.
    with pytest.raises(TypeError):
        getattr(_cw, _ACC)(object(), _ast.Constant(1), ())
    # Negative controls: one construction planted per spelling.
    planted = {
        "test_match_hold_admission_gate_pg":
            f"\ndef _x(node):\n    return _cw.{_ACC}(_cw.{_TOKEN}, node, [])\n",
        "test_a1_identity_formation":
            f"\nfrom closed_walk import {_ACC} as A\nA(None, None, ())\n",
        "test_mail": f"\nimport closed_walk\ngetattr(closed_walk, '{_ACC}')\n",
        "migration_table_ddl": "\ndef _y(v):\n    v." + _SEEN + ".add(1)\n",
    }
    for mod, extra in planted.items():
        # sites are found module by module: the planted module alone
        got = acceptance_sites({mod: sources[mod] + extra})
        assert len(got) > sum(m == mod for m, *_r in sites), (mod, got)


# --- ruling REHEARSAL-FOUR-R4 item 2: class B and closed_walk:712 controls --

_R4_CW_SRC = "\n".join([
    "from sqlalchemy import text",
    "Q = 'SELECT 1'",
    "T = 'SELECT 1 {c}'",
    "ALLOWED = ('t', 'u')",
    "def builder():",
    "    Q = 'UPDATE t SET x = 1'",
    "    return Q",
    "async def builder_masked(db):",
    "    await db.execute(text(builder()), {})",
    "async def template_masked(db):",
    "    T = 'UPDATE t SET x = 1 {c}'",
    "    sql = T.format(c='')",
    "    await db.execute(text(sql), {})",
    "def plain_add(db, row):",
    "    db.add(row)",
    "def plain_ok(row):",
    "    return len(row)",
    "async def shadow_session_method(db, row):",
    "    str = db.add",
    "    str(row)",
    "async def shadow_by_parameter(db, str):",
    "    str(1)",
    "async def shadow_module_function(db, row):",
    "    plain_ok = plain_add",
    "    plain_ok(db, row)",
    "async def local_sql_masked(db):",
    "    Q = 'UPDATE t SET x = 1'",
    "    await db.execute(text(Q), {})",
    "async def guard_then_rebind(db, name):",
    "    if name not in ALLOWED:",
    "        raise ValueError(name)",
    "    name = 'lo_create(0)'",
    "    await db.execute(text(f'SELECT 1 FROM {name}'), {})",
    "async def guard_in_loop(db, pairs):",
    "    for name, pid in pairs:",
    "        if name not in ALLOWED:",
    "            raise ValueError(name)",
    "        await db.execute(text(f'SELECT 1 FROM {name} WHERE id = :p'), {'p': pid})",
    "async def guard_after_use(db, name):",
    "    await db.execute(text(f'SELECT 1 FROM {name}'), {})",
    "    if name not in ALLOWED:",
    "        raise ValueError(name)",
    "async def plain_helper_writes(db, row):",
    "    plain_add(db, row)",
    "async def plain_helper_reads_nothing(db, row):",
    "    return plain_ok(row)",
    "async def annotation_writes(db, row):",
    "    def inner(x: db.add(row)):",
    "        return x",
    "    inner(1)",
    "async def inner_ends(db):",
    "    try:",
    "        await db.execute(text('SELECT 1'), {})",
    "    except Exception:",
    "        await db.rollback()",
    "        raise",
    "async def outer_catches(db):",
    "    try:",
    "        await inner_ends(db)",
    "    except Exception:",
    "        pass",
    "async def nested_handler_caught(db):",
    "    try:",
    "        try:",
    "            await db.execute(text('SELECT 1'), {})",
    "        except Exception:",
    "            await db.rollback()",
    "            raise",
    "    except Exception:",
    "        pass",
    "async def outer_propagates(db):",
    "    await inner_ends(db)",
    ""])


def _r4_cw_scope():
    import linecache as _linecache
    import sys as _sys
    import types as _types
    mod = _types.ModuleType("r4_cw_controls")
    mod.__file__ = "<r4_cw_controls>"
    _linecache.cache[mod.__file__] = (len(_R4_CW_SRC), None,
                                      _R4_CW_SRC.splitlines(True), mod.__file__)
    _sys.modules[mod.__name__] = mod
    _a1_ib.register_source(mod, _R4_CW_SRC, mod.__file__)
    exec(compile(_R4_CW_SRC, mod.__file__, "exec"), mod.__dict__)
    return mod


# (helper, what the walk must give: a refusal sentence, or the effects)
_R4_CW_CONTROLS = [
    ("shadow_session_method", "a session attribute outside a call of it"),
    ("shadow_by_parameter", "a name the function binds"),
    ("shadow_module_function", "a name the function binds"),
    ("local_sql_masked", {"write"}),
    ("plain_helper_writes", "a plain call of plain_add, which takes write"),
    ("plain_helper_reads_nothing", set()),
    ("annotation_writes", {"write"}),
    # the 322 class swept (grep getattr(scope, ...)): a SQL builder's return
    # and a SQL template read through their own function's bindings
    # the builder's own local is never the module's: since ruling
    # REHEARSAL-FOUR-R5 fix 3 a builder of no parameters is called (its
    # whole domain) and its true text classified, a write
    ("builder_masked", {"write"}),
    # finding closed_walk:825 (class C): a rollback-then-raise propagates to
    # the helper that awaits it, and none is caught inside the walked helper
    ("outer_catches", "awaited inside a try that catches"),
    ("nested_handler_caught", "ends the transaction (.rollback)"),
    # round 8 (M1): a planted read is no frozen read position, a write
    ("outer_propagates", {"write", "await", "rollback-then-raise"}),
    ("inner_ends", {"write", "rollback-then-raise"}),
]


@pytest.mark.parametrize("helper,want", _R4_CW_CONTROLS,
                         ids=[c[0] for c in _R4_CW_CONTROLS])
def test_r4_closed_walk_names_resolve_through_the_function(helper, want):
    """Ruling REHEARSAL-FOUR-R4 item 2, findings closed_walk:699 (a callee
    name the function binds is not the module's, and a session attribute is
    reached only as a callee), :322 (a local SQL binding before the module
    constant), :345 (a guard proves a name only over the statements it
    dominates, up to a store of the name), :712 (a plain callee's body is
    walked), :1036 (a local function's annotations are walked) and :825 (a
    rollback-then-raise propagates to its caller, and is never caught
    inside the walked helper). Each
    program is read by the shared visitor under a1's policy; the refusals
    name their reason, and the two kept shapes (a guard inside a loop, a
    plain callee that touches nothing) still read."""
    scope = _r4_cw_scope()
    fn = getattr(scope, helper)
    # .format added for the template program, so it reaches the SQL read
    policy = _cw.Policy(scope, _PURE_CALLS, _PURE_METHODS | {"format"},
                        _PURE_AWAITS, _A1_TABLE)
    if isinstance(want, str):
        with pytest.raises(Unclassified) as e:
            _cw.helper_effects(fn, policy)
        assert want in e.value.args[0][1], e.value.args[0]
    else:
        got = set(_cw.helper_effects(fn, policy))
        assert got == want, got


# --- rehearsal-four round 5 (ruling REHEARSAL-FOUR-R5) -----------------------

# The reviewer's programs for round 5's closed_walk findings, read by the
# shared visitor under a1's policy (fix 0: each executed red at f2b21fbd,
# where every one of them was accepted).
_R5_CW_SRC = "\n".join([
    "from sqlalchemy import text",
    "Q = 'SELECT 1'",
    "SAFE = ('x',)",
    "SAFE_F = ('lo_create',)",
    "SAFE_LIST = ['x']",
    "_T = {'a': 't_a', 'b': 't_b'}",
    "def bad(db, row):",
    "    db.add(row)",
    "def plain_session_add(session, row):",
    "    session.add(row)",
    "def builder(mode):",
    "    if mode == 'evil':",
    "        return 'UPDATE t SET x = 1'",
    "    base = 'SELECT * FROM '",
    "    return base + _T[mode]",
    "def builder_two(mode):",
    "    if mode == 'evil':",
    "        return 'UPDATE t SET x = 1'",
    "    return 'SELECT 1'",
    "def builder_ok(mode):",
    "    return f'SELECT * FROM {_T[mode]}'",
    "class Evil(tuple):",
    "    _fields = ()",
    "    def __new__(cls, db, row):",
    "        db.add(row)",
    "        return tuple.__new__(cls, ())",
    # closed_walk:897, a local function rebound to a writing helper
    "async def local_def_rebound(db, row):",
    "    def inner(x, y):",
    "        return x",
    "    inner = bad",
    "    inner(db, row)",
    # closed_walk:1235, an imported name reassigned
    "async def import_rebound(db, row):",
    "    from builtins import str",
    "    str = bad",
    "    str(db, row)",
    # closed_walk:1005, the session through an alias and a plain parameter
    "async def session_alias(db, row):",
    "    s = db",
    "    s.add(row)",
    "async def session_to_plain(db, row):",
    "    plain_session_add(db, row)",
    # closed_walk:759, a tuple marker on a class whose __new__ writes
    "async def tuple_marker(db, row):",
    "    Evil(db, row)",
    # closed_walk:1217, an exception-suppressing finally (each kind)
    "async def finally_returns(db):",
    "    try:",
    "        await db.execute(text('SELECT 1'), {})",
    "    except Exception:",
    "        await db.rollback()",
    "        raise",
    "    finally:",
    "        return None",
    "async def finally_breaks(db):",
    "    for _i in (1,):",
    "        try:",
    "            await db.execute(text('SELECT 1'), {})",
    "        except Exception:",
    "            await db.rollback()",
    "            raise",
    "        finally:",
    "            break",
    "async def finally_continues(db):",
    "    for _i in (1,):",
    "        try:",
    "            await db.execute(text('SELECT 1'), {})",
    "        except Exception:",
    "            await db.rollback()",
    "            raise",
    "        finally:",
    "            continue",
    # closed_walk:501, a guard's name rebound in its else, its collection mutated
    "async def guard_else_rebinds(db, name):",
    "    if name not in SAFE:",
    "        raise ValueError(name)",
    "    else:",
    "        name = 'lo_create(0)'",
    "    return (await db.execute(text(f'SELECT {name}'), {})).scalar()",
    "async def guard_collection_mutated(db, name):",
    "    SAFE_LIST.append('lo_create(0)')",
    "    if name not in SAFE_LIST:",
    "        raise ValueError(name)",
    "    return (await db.execute(text(f'SELECT {name}'), {})).scalar()",
    # closed_walk:501's two routes, one control each: a module list as a
    # guard collection (never a proof, mutated or not), and a module table
    # updated in place before its item is read as a formatted SQL value
    "async def guard_mutable_list(db, name):",
    "    if name not in SAFE_LIST:",
    "        raise ValueError(name)",
    "    return (await db.execute(text(f'SELECT {name}'), {})).scalar()",
    "async def table_mutated(db, mode):",
    "    _T.update(a='t_a; UPDATE t SET x = 1')",
    "    return (await db.execute(text(f'SELECT * FROM {_T[mode]}'), {})).scalar()",
    "async def table_kept(db, mode):",
    "    return (await db.execute(text(f'SELECT * FROM {_T[mode]}'), {})).scalar()",
    # closed_walk:326, a guarded name in a function position
    "async def guarded_function_name(db, name):",
    "    if name not in SAFE_F:",
    "        raise ValueError(name)",
    "    return (await db.execute(text(f'SELECT {name}(0)'), {})).scalar()",
    # closed_walk:441, a builder whose unsampled branch writes
    "async def builder_union(db):",
    "    return (await db.execute(text(builder_two('a')), {})).scalar()",
    "async def builder_sampled(db):",
    "    return (await db.execute(text(builder('evil')), {})).scalar()",
    # the kept forms
    "async def guard_kept(db, name):",
    "    if name not in SAFE:",
    "        raise ValueError(name)",
    "    return (await db.execute(text(f'SELECT {name}'), {})).scalar()",
    "async def builder_kept(db):",
    "    return (await db.execute(text(builder_ok('a')), {})).scalar()",
    "async def local_def_kept(db, row):",
    "    def inner(x):",
    "        return x",
    "    inner(row)",
    "async def finally_kept(db):",
    "    try:",
    "        await db.execute(text('SELECT 1'), {})",
    "    finally:",
    "        pass",
    ""])


def _r5_cw_scope():
    import linecache as _linecache
    import sys as _sys
    import types as _types
    mod = _types.ModuleType("r5_cw_controls")
    mod.__file__ = "<r5_cw_controls>"
    _linecache.cache[mod.__file__] = (len(_R5_CW_SRC), None,
                                      _R5_CW_SRC.splitlines(True), mod.__file__)
    _sys.modules[mod.__name__] = mod
    _a1_ib.register_source(mod, _R5_CW_SRC, mod.__file__)
    exec(compile(_R5_CW_SRC, mod.__file__, "exec"), mod.__dict__)
    return mod


# (helper, what the walk must give: a refusal sentence, or the effects)
_R5_CW_CONTROLS = [
    ("local_def_rebound", "a name bound more than once: inner"),
    ("import_rebound", "a name bound more than once: str"),
    ("session_alias", "the session as a value"),
    ("session_to_plain", "the session as a value"),
    ("tuple_marker", "a call this walk does not classify: Evil"),
    ("finally_returns", "a return inside a finally"),
    ("finally_breaks", "a break inside a finally"),
    ("finally_continues", "a continue inside a finally"),
    ("builder_union", {"write"}),
    ("local_def_kept", set()),
    ("finally_kept", {"write"}),  # round 8 (M1): a planted read is a write
]


@pytest.mark.parametrize("helper,want", _R5_CW_CONTROLS,
                         ids=[c[0] for c in _R5_CW_CONTROLS])
def test_r5_closed_walk_round_5s_programs(helper, want):
    """Ruling REHEARSAL-FOUR-R5, fix 0: round 5's closed_walk findings :897
    (a local function rebound), :1235 (an imported name reassigned), :1005
    (the session through an alias or a plain parameter), :759 (a tuple
    marker granted constructor purity), :1217 (a finally that swallows a
    rollback-then-raise: return, break, continue), :501 (a guard's name
    rebound in its else, its collection mutated), :326 (a formatted name in
    a SQL function position) and :441 (a builder classified by sampling),
    each refused for its own reason, beside the kept forms."""
    scope = _r5_cw_scope()
    fn = getattr(scope, helper)
    policy = _cw.Policy(scope, _PURE_CALLS, _PURE_METHODS, _PURE_AWAITS,
                        _A1_TABLE)
    if isinstance(want, str):
        with pytest.raises(Unclassified) as e:
            _cw.helper_effects(fn, policy)
        assert want in e.value.args[0][1], e.value.args[0]
    else:
        got = set(_cw.helper_effects(fn, policy))
        assert got == want, got


class _R5Scope(_SampleScope):
    """_SampleScope with a module SQL constant the planted handler masks."""
    Q = "SELECT 1"


# The resolution-site census (ruling REHEARSAL-FOUR-R5, fix 1, a BOUND): in
# each function span of the three walkers, the sites that decide what a
# walked identifier denotes (resolution_sites.sites) all lie inside class
# closed_walk.Bindings, the one resolver. One span is exempt, by name and
# with its count pinned, so a new site in it fails as well:
_CENSUS_EXEMPT = {
    # acceptance_sites counts every spelling of the R4 token as a reference
    # (a superset): it decides no name's binding, and over-counts only.
    ("test_a1_identity_formation", "acceptance_sites.visit"): 4,
    # closed_walk._anchored_node (round 8, M3) asks whether a STORED Name's
    # spelling is a meaningful one: the grammar's own rule over the frozen
    # A1_MEANINGFUL, deciding no name's binding.
    ("closed_walk", "_anchored_node"): 1,
    # formation_loop_exits.decide (round 9, G3: every comparison operator
    # counts) evaluates a test only when every name it reads is a local the
    # path bound to a literal (`names <= set(env) | {"len"}`); a name outside
    # env leaves the test undecided (None), the walk's refusing direction,
    # and the check decides no binding the walk reads as the module's.
    ("test_a1_identity_formation", "formation_loop_exits.decide"): 1,
}
# One bypassing site per walker, each put where the census must count it:
# (module, the exact text replaced, its replacement, the span it lands in).
_CENSUS_MUTANTS = [
    ("closed_walk",
     '''            fn = self._check(n, self.b.callee, n.func)
            if fn is None or _inspect.iscoroutinefunction(fn):''',
     '''            fn = self._check(n, self.b.callee, n.func)
            fn = getattr(self.p.scope, n.func.id, None) or fn
            if fn is None or _inspect.iscoroutinefunction(fn):''',
     "Visitor.call"),
    # (escaped quotes, so this literal is not itself the text replaced)
    ("test_a1_identity_formation",
     "            and b.spelled_once(call.func.value, \"db\", (\"param\",))",
     "            and call.func.value.id == \"db\"",
     "_txn_end"),
    ("test_match_hold_admission_gate_pg",
     '''        if isinstance(n, ast.Call) and w.b.named(n.func, (stop,)) is not None:''',
     '''        if isinstance(n, ast.Call) and n.func.id == stop:''',
     "_calls"),
]


def _census_problems(sources):
    """(span, sites) for every walker span whose resolution sites do not all
    go through the resolver (resolution_sites.census; round 9, G2: a call
    is the resolver's only on the frozen receiver its span admits), the
    exempt spans held to their pinned counts; empty when the bound holds.
    The census's own forms and the receiver chain are checked by the tests
    (_r9_form_problems: this span is walker code, held to the frozen
    walker grammar, so it gains no call the grammar does not hold)."""
    import resolution_sites as _rs
    methods = _rs.resolver_methods(_ast.parse(sources["closed_walk"]))
    out = []
    for mod, text in sorted(sources.items()):
        for (q, _ln), (n, through, sites) in _rs.census(
                _ast.parse(text), methods).items():
            pinned = _CENSUS_EXEMPT.get((mod, q))
            if (n - through) != (pinned or 0):
                out.append((f"{mod}:{q}", sites))
    return out


def test_r5_every_resolution_site_goes_through_the_resolver():
    """Ruling REHEARSAL-FOUR-R5, fix 1: one resolver, exactly one binding per
    name or refuse. Within each function span of closed_walk and of the a1
    and gate walkers (never file-wide, #432), the resolution sites counted
    equal the sites that go through the resolver, class Bindings; the
    exempt span holds exactly its pinned count. Each mutant adds one
    bypassing site and must be counted, in the span it lands in."""
    import pathlib
    here = pathlib.Path(__file__).resolve().parent
    sources = {m: (here / f"{m}.py").read_text(encoding="utf-8") for m in (
        "closed_walk", "test_a1_identity_formation",
        "test_match_hold_admission_gate_pg")}
    assert _census_problems(sources) == []
    import resolution_sites as _rs
    for mod, text in sorted(sources.items()):
        assert _rs.form_problems(_ast.parse(text)) == [], mod
    methods = _rs.resolver_methods(_ast.parse(sources["closed_walk"]))
    for (q, _ln) in _rs.census(_ast.parse(sources["test_a1_identity_formation"]),
                               methods):
        if q.startswith("acceptance_sites"):
            break
    else:
        raise AssertionError("the exempt span is gone; drop its exemption")
    for mod, old, new, span in _CENSUS_MUTANTS:
        assert sources[mod].count(old) == 1, (mod, span)
        mutated = dict(sources, **{mod: sources[mod].replace(old, new)})
        got = _census_problems(mutated)
        assert [s for s, _sites in got] == [f"{mod}:{span}"], (span, got)


# --- round 7: the default-deny grammar of the a1 walks ---------------------
# Ruling REHEARSAL-FOUR-R6 (1)(b), arms E, P, B2-callee: every span the a1
# walks visit is admitted by _A1_GRAMMAR before any walker reasoning.

_REAL_TEAM_RELOCK = ("_team_resolve_live_family", "_team_lock_family_pick",
                     "_team_relock_existing_series")


def _a1_real_walks():
    """Every walk the a1 arms make over the REAL spans, in one place: the
    completeness test and the one-time generator (RF/r7/ga1/gen_shapes.py)
    both call this. [(walk, problems)]; every problems list is empty when
    the grammar admits every span and the walks' structural rules hold."""
    src = {n: _inspect.getsource(getattr(main, n)) for n in (
        "queue_poll", "ovt_queue_poll", "_ffa_queue_poll_inner",
        "team_queue_poll") + _REAL_TEAM_RELOCK}
    out = [("queue_poll return", formation_exit_violations(src["queue_poll"]))]
    for site in ("ovt_queue_poll", "_ffa_queue_poll_inner"):
        out.append((f"{site} gather",
                    formation_exit_violations(src[site], "gather")))
    for site in ("ovt_queue_poll", "_ffa_queue_poll_inner", "team_queue_poll"):
        try:
            openings, _c, _l = _attempt_budgets(src[site])
            out.append((f"{site} budget", [] if len(openings) == 1
                        else [f"{len(openings)} budget openings"]))
        except Unclassified as e:
            out.append((f"{site} budget", [e.args[0]]))
    out.append(("team_queue_poll team",
                formation_exit_violations(src["team_queue_poll"], "team")))
    out.append(("relock", _relock_outcome_problems(
        *(src[n] for n in _REAL_TEAM_RELOCK))))
    # P: the FFA gather decision, walked whole as a plain function
    try:
        eff = _cw.plain_effects(main._ffa_gather_decide, _policy())
        out.append(("_ffa_gather_decide plain", sorted(eff)))
    except Unclassified as e:
        out.append(("_ffa_gather_decide plain", [e.args[0]]))
    return out


def _span_def(filename, line, name):
    """Definition `name` at `line` of tests/../api/`filename`, read from the
    file itself (the completeness test's independent reading)."""
    import pathlib
    path = pathlib.Path(__file__).resolve().parent.parent / "api" / filename
    tree = _SPAN_TREES.get(filename)
    if tree is None:
        tree = _SPAN_TREES[filename] = _ast.parse(path.read_text(encoding="utf-8"))
    hits = [n for n in _ast.walk(tree) if isinstance(
        n, (_ast.FunctionDef, _ast.AsyncFunctionDef)) and n.name == name
        and n.lineno == line]
    assert len(hits) == 1, (filename, line, name, len(hits))
    return hits[0]


_SPAN_TREES = {}


def test_r7_the_grammar_checks_every_walked_node_and_refuses_none(monkeypatch):
    """Completeness (ruling REHEARSAL-FOUR-R6 (1)(b)): with a fresh grammar
    and fresh policies, every real walk of the a1 arms runs; the refusal
    list is EMPTY; the spans the grammar admitted are exactly the frozen
    A1_SPANS; and the nodes it checked, span by span and in total, equal
    the nodes of those spans counted independently from the source files."""
    import sys as _sys
    me = _sys.modules[__name__]
    g = _a1_grammar()
    monkeypatch.setattr(me, "_A1_GRAMMAR", g)
    monkeypatch.setattr(me, "_POLICIES", {})
    walks = _a1_real_walks()
    assert [(w, p) for w, p in walks if p] == [], walks
    want = {(f, ln, name): n for f, ln, name, n in _gs.A1_SPANS}
    assert set(g.admitted) == set(want), (
        sorted(set(g.admitted) ^ set(want)))
    import shape_grammar as _sg
    imports = set()
    for key, n in want.items():
        d = _span_def(*key)
        assert g.admitted[key] == n == len(_sg.visit(d)), (key, n)
        imports |= {imp for _ln, imp in _cw.local_imports(d)}
    assert sum(g.admitted.values()) == sum(want.values()) == _gs.A1_NODES
    # the local imports the shape rule admits, as (module, name, asname)
    assert imports == set(_gs.A1_IMPORTS), sorted(imports, key=repr)


# --- round 7: every owned finding of rounds 1 to 6, a control ------------
# Each reviewer's program is planted INTO THE REAL SPAN it was about (the
# real handler's source, or a real helper the real handler awaits, copied
# into a module over main's namespace with the program inserted), walked by
# the same a1 walk under the FROZEN grammar, and refused: by the grammar
# (the sentence names the shape), by the binding rule, by the P rule, or by
# the walk's structural exit rule (its sentence). The sentence each is
# refused with is pinned (R7_A1_WANT). Round 8 (ruling REHEARSAL-FOUR-R7-A1,
# M3, M5): no control is refused by a walk's sentence over an admitted
# shape any more; each is refused by a shape, an anchor (named by its
# innermost shape) or the definition scope (named by its shape).

def _r7_scope(tag, sources=()):
    """A planted module r7_<tag>: main's namespace, then each of `sources`
    (a real helper's source with a program inserted, or a class the program
    defines) executed over it, so the real call site reaches the copy."""
    import linecache
    import sys as _sys
    import types as _types
    mod = _types.ModuleType(f"r7_{tag}")
    mod.__file__ = f"<r7_{tag}>"
    text = "\n\n".join(sources) + "\n"
    linecache.cache[mod.__file__] = (len(text), None, text.splitlines(True),
                                     mod.__file__)
    mod.__dict__.update({k: v for k, v in vars(main).items()
                         if not k.startswith("__")})
    _sys.modules[mod.__name__] = mod
    _a1_ib.register_source(mod, text, mod.__file__)
    exec(compile(text, mod.__file__, "exec"), mod.__dict__)
    return mod


def _r7_put(src, anchor, new, replace=False):
    """`src` with `new` inserted before the one occurrence of `anchor` (or
    replacing it)."""
    assert src.count(anchor) == 1, (anchor, src.count(anchor))
    return src.replace(anchor, new if replace else new + anchor)


_R7_H = "_formation_lease_conflict"
_R7_H_AT = "    # One set, so `allow` and `allow_any` cannot disagree."
_R7_Q_DRIFT = ("            await db.rollback()\n            opp = None\n"
               "            continue\n")
_R7_Q_BARRIER = ('        await _identity_lock_many(db, [steam_id, '
                 'cand["steam_id"]])\n')
_R7_O_DRIFT = ("            await db.rollback()\n            lobby = None\n"
               "            continue\n")
_R7_T_DRIFT = ("            await db.rollback()\n            others = []\n"
               "            break\n        if len(still) != 3:\n")
_R7_T_SPEND = "\n    while _form_left > 0:\n        _form_left -= 1\n"
_R7_T_RESOLVE = ("            outcome, resp = await _team_resolve_live_family(\n"
                 "                db, original_pids, my_pid, steam_id, my_qtype, "
                 "req1, req2)\n")


def _r7_src(name):
    return _textwrap.dedent(_inspect.getsource(getattr(main, name)))


# Round 9 (G2, G3): queue_poll's admission refusal (main.py:20552), its
# success commit (:20554) and the lease acquire both stand under.
_R9_Q_ADMISSION = ("            await db.rollback()\n"
                   "            raise HTTPException(status_code=503, "
                   "detail=\"admission_contended\")\n")
_R9_Q_SUCCESS = "        await db.commit()\n\n        return QueuePollResponse(\n"
_R9_Q_ACQUIRE = ("        if (await _lease_acquire_many(\n"
                 "                db, [my_pid, opp[\"player_id\"]], \"ranked\",\n")


def _r7_helper(tag, lines, classes=()):
    """The real handler queue_poll over a scope whose _R7_H, the real
    helper it awaits in its formation loop, carries `lines` (statements at
    the helper's top level) before its first statement after the
    docstring; `classes` are module statements the program defines."""
    h = _r7_put(_r7_src(_R7_H), _R7_H_AT,
                "".join("    " + ln + "\n" for ln in lines))
    return ("return", _r7_src("queue_poll"),
            _r7_scope(tag, tuple(classes) + (h,)))


def _r7_programs():
    """[(finding, form, handler source or relock sources, scope)]: each
    owned finding's program in its real span (rounds 1 to 6; the census
    findings resolution_sites:132 and :145 are test_r7_census_*)."""
    q, o, t = _r7_src("queue_poll"), _r7_src("ovt_queue_poll"), _r7_src(
        "team_queue_poll")
    rel = [_r7_src(n) for n in _REAL_TEAM_RELOCK]
    plain = _r7_scope("plain")
    # round 9, G3: the success commit removed (the first of two edits of one
    # control, bound here so the case list holds no nested edit)
    q_no_success = _r7_put(q, _R9_Q_SUCCESS, _R9_Q_SUCCESS.replace(
        "        await db.commit()\n", ""), replace=True)
    # main's own committing helper, called with a name the span binds (its
    # call shape is the grammar's; its body commits)
    commit = "await _report_commit(db, {})"

    def relock(k):
        tree = _ast.parse(rel[k])
        tree.body[0].body.insert(1, _ast.parse(commit.format(
            ("four_pids", "four_pids", "srow")[k])).body[0])
        out = list(rel)
        out[k] = _ast.unparse(tree)
        return out

    return [
        ("r1 a1:567 a commit before the drift rollback", "return",
         _r7_put(q, _R7_Q_DRIFT, "            await db.commit()\n"), plain),
        ("r1 a1:593 a nested loop's else: continue", "return",
         _r7_put(q, _R7_Q_DRIFT, "            for _never in ():\n"
                 "                pass\n            else:\n"
                 "                continue\n", replace=True), plain),
        ("r1 a1:1172 the OVT drift rollback deleted", "gather",
         _r7_put(o, _R7_O_DRIFT, "            lobby = None\n"
                 "            continue\n", replace=True), plain),
        ("r2 a1:918 the barrier and a commit under if True", "return",
         _r7_put(q, _R7_Q_BARRIER, "        if True:\n    " + _R7_Q_BARRIER
                 + "            await db.commit()\n", replace=True), plain),
        ("r2 a1:910 a committing helper before the drift rollback", "return",
         _r7_put(q, _R7_Q_DRIFT, "            " + commit.format("opp") + "\n"),
         plain),
        ("r2 a1:961 the team drift keeps the rolled-back roster", "team",
         _r7_put(t, _R7_T_DRIFT, _R7_T_DRIFT.replace(
             "others = []", "others = still"), replace=True), plain),
        ("r2 a1:718 the budget refilled inside the loop", "team",
         _r7_put(t, _R7_T_SPEND, _R7_T_SPEND
                 + "        _form_left = max(_form_left, 1)\n", replace=True),
         plain),
        ("r3 a1:1397 a commit in the barrier's keyword", "return",
         _r7_put(q, _R7_Q_BARRIER, _R7_Q_BARRIER.replace(
             "]])", "]], timeout_ms=(await db.commit()))"), replace=True),
         plain),
        ("r3 a1:914 a helper holding a match",
         *_r7_helper("match", ["match members:", "    case _:",
                               "        pass"])),
        ("r3 a1:914 a helper holding a lambda",
         *_r7_helper("lambda", ["f = (lambda: db.add(members))", "f()"])),
        ("r3 a1:914 a helper holding a walrus",
         *_r7_helper("walrus", ["if (w := db.add(members)):", "    pass"])),
        ("r3 a1:2481 a committing helper in the real resolver", "relock",
         relock(0), plain),
        ("r4 cw:699 a builtin rebound to a session method",
         *_r7_helper("rebound", ["str = db.add", "str(members)"])),
        ("r4 cw:699 (binding route) a builtin rebound",
         *_r7_helper("rebound2", ["str = members", "str(members)"])),
        ("r4 cw:1036 a writing local-function annotation",
         *_r7_helper("annot", ["def inner(x: db.add(members)):",
                               "    return x"])),
        ("r4 cw:825 a helper catches a rollback-then-raise",
         *_r7_helper("catches", ["try:", "    " + commit.format("members"),
                                 "except Exception:", "    pass"])),
        ("r4 a1:1119 the resolver called with *[...]", "team",
         _r7_put(t, _R7_T_RESOLVE, _R7_T_RESOLVE.replace(
             "db, original_pids,", "*[db, original_pids],"), replace=True),
         plain),
        ("r4 a1:1119 the resolver called with **{}", "team",
         _r7_put(t, _R7_T_RESOLVE, _R7_T_RESOLVE.replace(
             "req2)", "req2, **{})"), replace=True), plain),
        ("r4 a1:2095 a committing helper in the real relock", "relock",
         relock(2), plain),
        ("r5 cw:897 a local function rebound to a writer",
         *_r7_helper("inner", ["def inner():", "    return None",
                               "inner = _report_commit", "inner()"])),
        ("r5 cw:1235 an imported builtin rebound",
         *_r7_helper("import", ["from builtins import str", "str = members",
                                "str(db, members)"])),
        ("r5 cw:759 a tuple subclass with a _fields marker",
         *_r7_helper("marker", ["Marked(members)"], classes=(
             "class Marked(tuple):\n    _fields = ()\n\n"
             "    def __new__(cls, *a):\n        return tuple.__new__(cls, a)\n",))),
        ("r5 cw:1217 a finally that returns",
         *_r7_helper("finally", ["try:", "    pass", "finally:",
                                 "    return None"])),
        ("r6 cw:406 the gate imported from another module",
         *_r7_helper("gate", ["from evil_gate import _lease_admission_gate",
                              "await _lease_admission_gate(db, members)"])),
        ("r6 cw:406 (binding route) the gate rebound",
         *_r7_helper("gate2", ["_lease_admission_gate = members"])),
        ("r6 cw:670 a copied namedtuple __new__ under a writing metaclass",
         *_r7_helper("meta", ["Evil(members)"], classes=(
             "import collections\n_Nt = collections.namedtuple('_Nt', 'a')\n\n\n"
             "class Meta(type):\n    def __call__(cls, *a):\n"
             "        return None\n\n\n"
             "class Evil(tuple, metaclass=Meta):\n    __new__ = _Nt.__new__\n",))),
        # round 9 (ruling REHEARSAL-R8-A1, G2): the reviewer's live mutant, a
        # commit in place of the admission refusal's rollback (main.py:20552)
        ("r8 grammar_shapes_a1:2106 a commit in place of the admission "
         "refusal's rollback", "return",
         _r7_put(q, _R9_Q_ADMISSION, _R9_Q_ADMISSION.replace(
             "rollback()", "commit()"), replace=True), plain),
        # round 9, G3: the position rule, one control per node class
        ("r9 G3 the success commit moved above the lease acquire", "return",
         _r7_put(q_no_success, _R9_Q_ACQUIRE, "        await db.commit()\n",
                 replace=False), plain),
        ("r9 G3 the drift rollback moved below its continue", "return",
         _r7_put(q, _R7_Q_DRIFT, "            opp = None\n            continue\n"
                 "            await db.rollback()\n", replace=True), plain),
        ("r9 G3 a refusal's detail changed", "return",
         _r7_put(q, _R9_Q_ADMISSION, _R9_Q_ADMISSION.replace(
             "admission_contended", "queue_contended"), replace=True), plain),
    ]


def _r7_outcome(form, prog, scope):
    """The problems the a1 walk gives the program, as sentences."""
    if form == "relock":
        return _relock_outcome_problems(*prog, scope=scope)
    return formation_exit_violations(prog, form, scope=scope)


# finding -> (the rule that refuses it, the text its first problem carries,
# the construct shapes the grammar must refuse in the program's spans).
# shape: "a shape outside the grammar ... <shape>"; anchored: "the anchored
# rule ... binds <spelling> (<how>) at <shape>" or "... a transaction end,
# <attr>, at <shape>" (round 8, M3: round 7's three exit controls and its
# two binding controls); scope: "<class>: a shape outside the definition
# scope at <file>:<line>: <shape>" (round 8, M5: round 7's two P controls).
_GRAMMAR = "a shape outside the grammar at "
R7_A1_WANT = {
    "r1 a1:567 a commit before the drift rollback":
        ("anchored", "a transaction end, commit, at "
                     "Await.value>Call(func=Attribute,args=[],keywords=[])", ()),
    "r1 a1:593 a nested loop's else: continue":
        ("shape", "For.body>If(test=BoolOp,body=[For],orelse=[])",
         ("For.orelse>Continue()",)),
    "r1 a1:1172 the OVT drift rollback deleted":
        ("shape", "For.body>If(test=Compare,body=[Assign|Continue],orelse=[])",
         ()),
    "r2 a1:918 the barrier and a commit under if True":
        ("shape", "For.body>If(test=Constant,body=[Expr],orelse=[])",
         ("If.test>Constant(value=bool)",)),
    "r2 a1:910 a committing helper before the drift rollback":
        ("shape", "<root>>AsyncFunctionDef(name=str,args=arguments,"
                  "body=[Expr|If],decorator_list=[]", ()),
    "r2 a1:961 the team drift keeps the rolled-back roster":
        ("anchored", "binds others (store) at Assign.targets>Name(", ()),
    "r2 a1:718 the budget refilled inside the loop":
        ("anchored", "binds _form_left (store) at Assign.targets>Name(", ()),
    "r3 a1:1397 a commit in the barrier's keyword":
        ("shape", "Call.keywords>keyword(arg='timeout_ms',value=Await)", ()),
    "r3 a1:914 a helper holding a match":
        ("shape", "body=[Assign|Expr|For|If|Match|Return]",
         ("AsyncFunctionDef.body>Match(",)),
    "r3 a1:914 a helper holding a lambda":
        ("shape", "AsyncFunctionDef.body>Assign(targets=[Name],value=Lambda,",
         ("Assign.value>Lambda(",)),
    "r3 a1:914 a helper holding a walrus":
        ("shape", "AsyncFunctionDef.body>If(test=NamedExpr,", ("If.test>NamedExpr(",)),
    "r3 a1:2481 a committing helper in the real resolver":
        ("shape", "<root>>AsyncFunctionDef(name=str,args=arguments,"
                  "body=[Expr|If],decorator_list=[]", ()),
    "r4 cw:699 a builtin rebound to a session method":
        ("shape", "AsyncFunctionDef.body>Assign(targets=[Name],value=Attribute,",
         ("Assign.value>Attribute(value=Name,attr='add',ctx=Load)",)),
    "r4 cw:699 (binding route) a builtin rebound":
        ("anchored", "binds str (store) at Assign.targets>Name(", ()),
    "r4 cw:1036 a writing local-function annotation":
        ("shape", "body=[Assign|Expr|For|FunctionDef|If|Return]",
         ("arg.annotation>Call(",)),
    "r4 cw:825 a helper catches a rollback-then-raise":
        ("shape", "AsyncFunctionDef.body>Try(body=[Expr],handlers=[ExceptHandler]",
         ()),
    "r4 a1:1119 the resolver called with *[...]":
        ("shape", "Await.value>Call(func=Name,args=[Name|Starred],keywords=[])",
         ("Call.args>Starred(",)),
    "r4 a1:1119 the resolver called with **{}":
        ("shape", "Call.keywords>keyword(arg=None,value=Dict)", ()),
    "r4 a1:2095 a committing helper in the real relock":
        ("shape", "<root>>AsyncFunctionDef(name=str,args=arguments,"
                  "body=[Expr|If],decorator_list=[]", ()),
    "r5 cw:897 a local function rebound to a writer":
        # the nested def's own shape is a real one (main nests functions);
        # the root's statement set and the bare call of the rebound name
        # are not
        ("shape", "body=[Assign|Expr|For|FunctionDef|If|Return]",
         ("Expr.value>Call(func=Name,args=[],keywords=[])",)),
    "r5 cw:1235 an imported builtin rebound":
        ("shape", "body=[Assign|Expr|For|If|ImportFrom|Return]",
         ("ImportFrom(module='builtins'",)),
    "r5 cw:759 a tuple subclass with a _fields marker":
        ("scope", "Marked: a shape outside the definition scope at "
                  "<r7_marker>:", ()),
    "r5 cw:1217 a finally that returns":
        ("shape", "finalbody=[Return]", ("Try.finalbody>Return(",)),
    "r6 cw:406 the gate imported from another module":
        ("shape", "body=[Assign|Expr|For|If|ImportFrom|Return]",
         ("ImportFrom(module='evil_gate'",)),
    "r6 cw:406 (binding route) the gate rebound":
        ("anchored", "binds _lease_admission_gate (store) at "
                     "Assign.targets>Name(", ()),
    "r6 cw:670 a copied namedtuple __new__ under a writing metaclass":
        ("scope", "Evil: a shape outside the definition scope at "
                  "<r7_meta>:", ()),
    # round 9 (G2): the committing-refusal anchor is gone, so the commit is
    # refused by its anchor, the reviewer's program itself
    "r8 grammar_shapes_a1:2106 a commit in place of the admission refusal's rollback":
        ("anchored", "a transaction end, commit, at "
                     "Await.value>Call(func=Attribute,args=[],keywords=[])", ()),
    # round 9 (G3): the position rule
    "r9 G3 the success commit moved above the lease acquire":
        ("anchored", "a transaction end, commit, outside its frozen position, "
                     "in queue_poll at", ()),
    "r9 G3 the drift rollback moved below its continue":
        ("anchored", "outside its frozen position, ", ()),
    "r9 G3 a refusal's detail changed":
        ("anchored", "a constant outside its frozen position, "
                     "keyword.value>Constant(value=str)#'queue_contended', "
                     "in queue_poll at", ()),
}
_R7_MARK = {"shape": _GRAMMAR, "anchored": "the anchored rule at ",
            "scope": "a shape outside the definition scope at "}


def _r7_program_refusals(form, prog, scope):
    """Every shape the frozen grammar refuses in the program's own spans:
    its handler (or the three relock bodies) and every definition its
    planted module holds."""
    import shape_grammar as _sg
    srcs = list(prog) if form == "relock" else [prog]
    path = getattr(scope, "__file__", "")
    if path.startswith("<r7_"):
        import linecache
        srcs.append("".join(linecache.cache[path][2]))
    out = set()
    for s in srcs:
        for d in _ast.parse(_textwrap.dedent(s)).body:
            if isinstance(d, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                out |= {sh for _f, _l, sh in _sg.refusals(d, _gs.A1_SHAPES, "")}
    return out


def test_r7_every_owned_finding_has_its_control():
    """The programs and R7_A1_WANT name the same findings."""
    progs = _r7_programs()
    assert {f for f, *_ in progs} == set(R7_A1_WANT), (
        sorted({f for f, *_ in progs} ^ set(R7_A1_WANT)))


@pytest.mark.parametrize("finding", sorted(R7_A1_WANT))
def test_r7_a1_findings_are_refused_under_the_frozen_grammar(finding, monkeypatch):
    """Ruling REHEARSAL-FOUR-R6 (3): every finding of rounds 1 to 6 this
    child owns is a control under the new mechanism. Each reviewer's
    program, planted into the real span it was about, is walked by the a1
    walk under the FROZEN grammar and refused, its FIRST problem carrying
    the rule and the text R7_A1_WANT pins; where a construct sits inside a
    container shape, the construct's own shape is among the grammar's
    refusals of the program too. The real spans the programs were planted
    in are admitted and pass (test_r7_the_grammar_checks_...).

    Round 9 (G2, G3): the position rule (closed_walk.positions) refuses a
    planted program that shifts a frozen position, often first. So every
    program is refused BY SHAPE under the full frozen grammar (its first
    problem carries one of the three marks), AND the rule each earlier
    round's row pins still refuses it on its own: rows before round 9 are
    checked under the frozen grammar less the position marker; the round-9
    rows (the reviewer's commit in place of rollback, the position
    controls) under the full grammar."""
    import sys as _sys
    me = _sys.modules[__name__]
    for f, form, prog, scope in _r7_programs():
        if f != finding:
            continue
        rule, text, constructs = R7_A1_WANT[finding]
        got = _r7_outcome(form, prog, scope)
        # round 8: every control is refused BY SHAPE (a shape, an anchor's
        # shape, a definition-scope shape), never by a walk's sentence
        assert got and any(m in got[0] for m in _R7_MARK.values()), (
            finding, got[:2])
        if not finding.startswith(("r8 grammar_shapes_a1:2106", "r9 ")):
            monkeypatch.setattr(me, "_A1_GRAMMAR", _cw.Grammar(
                _gs.A1_SHAPES, _gs.A1_MEANINGFUL,
                _gs.A1_BINDINGS - {_cw.POSITIONED, _cw.ORDERED}, _A1_CALLEES,
                _gs.A1_NAMEDTUPLES))
            monkeypatch.setattr(me, "_POLICIES", {})
            got = _r7_outcome(form, prog, scope)
        assert got and _R7_MARK[rule] in got[0] and text in got[0], (
            finding, got[:2])
        refused = _r7_program_refusals(form, prog, scope)
        for c in constructs:
            assert any(c in s for s in refused), (finding, c, sorted(refused))


@pytest.mark.parametrize("m", ["closed_walk", "test_a1_identity_formation",
                               "test_match_hold_admission_gate_pg"])
def test_r7_census_walker_code_is_in_its_grammar(m):
    """The census is default-deny (ruling REHEARSAL-FOUR-R6 (1)(b)), FILE
    BY FILE (round 8, M8): every node of every walker span of the file is
    in WALKER_SHAPES (ga1's round-7 freeze, 51d4faf2, less three removed
    shapes: test_r8_the_walker_grammar_is_the_round_7_freeze_less_three),
    the frozen set names no annotated assignment, and the nodes the census
    checks in the file equal the nodes of its outermost walker definitions
    counted independently here (ast.walk). A refusal lists the file's
    shapes outside, with lines. Round 8: red for the gate file only, whose
    walker code is child gg's to conform (RF/r8/ga1/GATE-WALKER-OUTSIDE.txt)."""
    import pathlib
    import resolution_sites as _rs
    here = pathlib.Path(__file__).resolve().parent
    assert not [s for s in _gs.WALKER_SHAPES if ">AnnAssign(" in s]
    tree = _ast.parse((here / f"{m}.py").read_text(encoding="utf-8"))
    defs = []
    for c in tree.body:
        if isinstance(c, _ast.ClassDef):
            defs += [d for d in c.body if isinstance(
                d, (_ast.FunctionDef, _ast.AsyncFunctionDef))]
        elif (isinstance(c, (_ast.FunctionDef, _ast.AsyncFunctionDef))
              and not c.name.startswith("test_")):
            defs.append(c)
    independent = sum(sum(1 for _n in _ast.walk(d)) for d in defs)
    assert _rs.walker_nodes(tree) == independent, (m, independent)
    outside = _rs.grammar_refusals(tree, _gs.WALKER_SHAPES, m)
    assert outside == [], (m, len(outside), [f"{f}:{ln} {sh}"
                                             for f, ln, sh in outside])


def test_r8_the_walker_grammar_is_the_round_7_freeze_less_three():
    """The boundary (round 8, ruling REHEARSAL-FOUR-R7-A1, M8): WALKER_SHAPES
    is ga1's round-7 freeze (51d4faf2), never regenerated from the code it
    bounds, less the three shapes M4 and M7 removed; pinned by its size and
    the digest of its sorted members, so any shape added fails. Round 11
    (ruling FOUR-R11-A1 (2), GROUP 2): the hand re-freeze block
    R11_ID_WALKER_SHAPES is pinned the same way, by its own size and digest,
    and WALKER_SHAPES is exactly the two, disjoint."""
    import hashlib
    removed = {"Call.func>Attribute(value=Name,attr='import_module',ctx=Load)",
               "Call.func>Attribute(value=Name,attr='module_accessor',ctx=Load)",
               "Call.func>Attribute(value=Name,attr='named',ctx=Load)"}
    r7, r11 = _gs.R7_LESS_THREE_WALKER_SHAPES, _gs.R11_ID_WALKER_SHAPES
    assert not removed & _gs.WALKER_SHAPES
    assert len(r7) == 2850, len(r7)
    digest = hashlib.sha256("\n".join(sorted(r7)).encode(
        "utf-8")).hexdigest()
    assert digest == ("073ed1959c7a09552e6d372d62988636"
                      "c8c77e90fe0d1157f57e276279648822"), digest
    # re-frozen once more for rules W, P and K (ruling FOUR-R11-A4): 364
    # shapes (75e1c16e) -> 608, three of the 364 no longer in the code;
    # -> 621 with the recorder's driver-UUID reading and type names (run 3)
    # -> 645 with FOUR-R11-A9's table amendment, counts and operation test
    # -> 693 with rule T (FOUR-R11-A5, A14 (1)): 40 shapes of rule T's
    # code and 8 of the order key at the group picker's call (FOUR-R11-A10
    # (C)), which the 645 block did not hold
    # (history and each shape's line: NOTES r11 rules, "walker shapes";
    # NOTES r11 t, "Walker shapes")
    assert len(r11) == 693, len(r11)
    digest = hashlib.sha256("\n".join(sorted(r11)).encode(
        "utf-8")).hexdigest()
    assert digest == ("cbd4c6575fd282b3b2f9a23f1de49970"
                      "7b255d8bf9cc99b11ca6b2e9bb407fba"), digest
    assert not (r7 & r11) and _gs.WALKER_SHAPES == r7 | r11


# The census findings of rounds 6 and 7: (finding, the program added to
# closed_walk outside class Bindings, whether the census must count it in
# the probe's span, the shape the walker grammar must refuse or None).
_R7_CENSUS_CONTROLS = [
    ("r6 resolution_sites:132 a decision inside a resolver call's argument",
     "def _r7_probe(b, n):\n    return b.named(n, ('db',) if n.id == 'db' "
     "else ())\n", True, None),
    ("r6 resolution_sites:145 an annotated alias",
     "def _r7_probe(node):\n    name: str = node.id\n    return name == 'db'\n",
     None, "FunctionDef.body>AnnAssign("),
    # round 8, M7: the report's own example; `b.named` on a plain name is
    # no resolver call (the one form is `<name>.b.<method>(...)`), and its
    # shape is no longer in the walker grammar
    ("r7 grammar_shapes_a1:3101 a resolver answer outside the resolver form",
     "def _r7_probe(b, n):\n    return b.named(n.id) == 'db'\n", True,
     "Call.func>Attribute(value=Name,attr='named',ctx=Load)"),
    # round 8, M4: the import and accessor routes' calls are no longer in
    # the walker grammar
    ("r7 closed_walk:755 a callee imported by a name read from the tree",
     "def _r7_probe(n):\n    return _importlib.import_module(n.module)\n",
     None, "Call.func>Attribute(value=Name,attr='import_module',ctx=Load)"),
    ("r7 closed_walk:755 a callee through the accessor route",
     "def _r7_probe(b, fn):\n    return b.module_accessor(fn)\n", None,
     "Call.func>Attribute(value=Name,attr='module_accessor',ctx=Load)"),
    # round 9 (ruling REHEARSAL-R8-A1, G2; finding resolution_sites:65): the
    # report's own example, `b.b` an ordinary object; its receiver is not
    # closed_walk's frozen one (`self` in a Visitor method), so the call is
    # an ordinary expression and the comparison is a site
    ("r8 resolution_sites:65 the resolver form on an ordinary receiver",
     "def _r7_probe(b, n):\n    return b.b.named(n.id) == 'db'\n", True, None),
    # `self.b` in a class that is not Visitor
    ("r9 G2 the resolver form on another class's self",
     "class _R9Probe:\n    def _r7_probe(self, n):\n"
     "        return self.b.named(n.id) == 'db'\n", "_R9Probe._r7_probe", None),
    # `self` rebound inside a Visitor method's span is no longer the receiver
    ("r9 G2 the receiver rebound in a Visitor method",
     None, "Visitor._r9_probe", None),
    # round 9, G3: the census's own forms
    ("r9 G3 a decision inside a lambda",
     "def _r7_probe(n):\n    return (lambda: n.id == 'db')()\n", True, None),
    ("r9 G3 hasattr with a walked identifier",
     "def _r7_probe(o, n):\n    return hasattr(o, n.id)\n", True, None),
    ("r9 G3 getattr with unpacked arguments",
     "def _r7_probe(o, a):\n    return getattr(*a)\n", True, None),
    ("r9 G3 the site spelling aliased",
     "def _r7_probe(o, n):\n    g = getattr\n    return g(o, n.id)\n",
     "form", None),
    ("r9 G3 the site method read as a value",
     "def _r7_probe(t, n):\n    g = t.get\n    return g(n.id)\n", "form", None),
    ("r9 G3 a second store to .b",
     "def _r7_probe(v, x):\n    v.b = x\n", "form", None),
]
# The Visitor method the receiver-rebinding control adds (G2): `self` bound
# a second time, so the span admits no receiver and the call is counted.
_R9_REBOUND = ("    def _r9_probe(self, n):\n        self = n\n"
               "        return self.b.named(n.id) == 'db'\n")


def test_r7_census_controls_are_refused():
    """Round 6's and round 7's census findings, each refused: a decision
    inside a resolver call's argument is a site outside the resolver (the
    arguments are no longer pruned); an annotated alias is a shape outside
    the walker grammar (AnnAssign); a resolver method on a plain name is a
    site (round 8, M7: only `<name>.b.<method>(...)` is the resolver's) and
    a shape outside; the import and accessor routes' calls are shapes
    outside (M4)."""
    import pathlib
    import resolution_sites as _rs
    here = pathlib.Path(__file__).resolve().parent
    base = {m: (here / f"{m}.py").read_text(encoding="utf-8") for m in (
        "closed_walk", "test_a1_identity_formation",
        "test_match_hold_admission_gate_pg")}
    assert _census_problems(base) == []
    assert not [m for m in base if _rs.form_problems(_ast.parse(base[m]))]
    for finding, prog, counted, shape in _R7_CENSUS_CONTROLS:
        if prog is None:
            # the rebinding control lands inside class Visitor (G2)
            head = "class Visitor:"
            assert base["closed_walk"].count(head) == 1, finding
            at = base["closed_walk"].index("    def __init__(self, policy,")
            text = base["closed_walk"][:at] + _R9_REBOUND + "\n" + base[
                "closed_walk"][at:]
            assert text.count(_R9_REBOUND) == 1, finding
            mutated = dict(base, closed_walk=text)
        else:
            mutated = dict(base, closed_walk=base["closed_walk"] + "\n\n" + prog)
        census = [s for s, _sites in _census_problems(mutated)] + [
            f"{m}:form" for m in sorted(mutated)
            if _rs.form_problems(_ast.parse(mutated[m]))]
        grammar = [sh for _f, _l, sh in _rs.grammar_refusals(
            _ast.parse(mutated["closed_walk"]), _gs.WALKER_SHAPES,
            "closed_walk") if _l > len(base["closed_walk"].splitlines())]
        assert counted or shape, finding
        if counted is True:
            assert census == ["closed_walk:_r7_probe"], (finding, census)
        elif counted:
            assert census == [f"closed_walk:{counted}"], (finding, census)
        if shape:
            assert any(s.startswith(shape) for s in grammar), (finding, grammar)


def test_r9_the_gate_receiver_chain_is_checked():
    """Round 9 (ruling REHEARSAL-R8-A1, G2): the gate walks' receiver `w` is
    the resolver's only through the chain resolution_sites.receiver_problems
    checks. Controls: a call passing an ordinary object as `w`, a gate
    function taking `w` handed on as a value, and a second store to `.b`,
    each refused; the real file holds the chain."""
    import pathlib
    import resolution_sites as _rs
    here = pathlib.Path(__file__).resolve().parent
    mod = "test_match_hold_admission_gate_pg"
    text = (here / f"{mod}.py").read_text(encoding="utf-8")
    assert _rs.receiver_problems(_ast.parse(text)) == []
    for prog, want in (
            ("def _r9_probe(n):\n    return _resolve(n, n.func)\n",
             "a call of _resolve passes n as `w`"),
            ("def _r9_probe(n):\n    return list(map(_resolve, [n]))\n",
             "_resolve, which takes `w`, is named other than as a callee"),
            ("def _r9_probe(n):\n    n.b = n\n",
             "the stores to `.b` are not exactly _Walk.__init__'s")):
        got = [why for _ln, why in _rs.receiver_problems(
            _ast.parse(text + "\n\n" + prog))]
        assert any(want in g for g in got), (prog, got)


# --- round 8: the callee table and the definition scope ---------------------
# Ruling REHEARSAL-FOUR-R7-A1, M4 and M5 (rule (1)(c)): a callee outside the
# walked function's own module namespace is admitted only through a frozen
# form (grammar_shapes_a1.A1_CALLEES, bound by _A1_CALLEES); a class is
# constructor-pure only inside a complete frozen definition scope
# (grammar_shapes_a1.A1_NAMEDTUPLES, every spelled shape of region_pick.py).


def test_r9_queue_poll_refusals_roll_back():
    """Production conformation (round 9, ruling REHEARSAL-R8-A1, G2; finding
    grammar_shapes_a1:2106). queue_poll's two committing refusals, the
    pair-inversion give-up (main.py:20059) and the formation loop's
    status re-read (:20446), each `await db.commit()` then `raise
    HTTPException(503, "queue_contended")`, now roll back: their
    transactions hold only reads and locks since the last end (the
    discovery and identity locks of the inversion loop; the loop's own
    re-read after the preflight commit or the previous attempt's
    rollback), so both ends release the same locks and keep the same rows.
    Every `raise` in queue_poll whose block ends a transaction first ends
    it by a rollback; the two conformed sites are among them; and the
    committing-refusal anchors are gone from the frozen anchors, which are
    the round-8 set less exactly those two (69, pinned by digest), the
    position rule's 2322 positions pinned beside them."""
    import hashlib
    tree = _ast.parse(_textwrap.dedent(_inspect.getsource(main.queue_poll)))
    off = main.queue_poll.__code__.co_firstlineno - 1
    ends = []
    for blk in _ast.walk(tree):
        for field in ("body", "orelse"):
            stmts = getattr(blk, field, None)
            if not isinstance(stmts, list):
                continue
            for a, b in zip(stmts, stmts[1:]):
                call = getattr(getattr(a, "value", None), "value", None)
                if (isinstance(b, _ast.Raise) and isinstance(a, _ast.Expr)
                        and isinstance(call, _ast.Call)
                        and isinstance(call.func, _ast.Attribute)
                        and call.func.attr in ("commit", "rollback")):
                    ends.append((a.lineno + off, call.func.attr))
    assert ends and all(e == "rollback" for _ln, e in ends), ends
    lines = {ln for ln, _e in ends}
    src = _inspect.getsource(main.queue_poll).splitlines()
    for want in ('pair kept changing under lock acquisition',
                 'Same precedent, and same status, as the pair-inversion'):
        at = next(i for i, s in enumerate(src) if want in s)
        nxt = next(i for i in range(at, len(src))
                   if src[i].strip() in ("await db.rollback()", "await db.commit()"))
        assert src[nxt].strip() == "await db.rollback()", (want, src[nxt])
        assert nxt + off + 1 in lines, (want, nxt + off + 1, sorted(lines))
    pos = _gs.A1_POSITIONS
    anchors = frozenset(b for b in _gs.A1_BINDINGS
                        if b not in pos and b != _cw.POSITIONED
                        and b not in _gs.A1_ORDERS and b != _cw.ORDERED)
    for lit, size, want in ((anchors, 69, "419ade3900e75191"),
                            (pos, 2322, "f9f0a2e4dbae2cd3")):
        digest = hashlib.sha256(repr(sorted(lit, key=repr)).encode(
            "utf-8")).hexdigest()[:16]
        assert (len(lit), digest) == (size, want), (len(lit), digest)
    assert _cw.POSITIONED in _gs.A1_BINDINGS
    raise_chains = [k for k in anchors if len(k) == 3 and k[0] == "commit"
                    and any("body=[Expr|Raise]" in c for c in k[2])]
    assert raise_chains == [], raise_chains


def test_r9_statement_order_is_bound():
    """The ORDER rule (round 9, W30b at the merge; the gr child's question
    2). The position rule binds every anchored node and every constant to
    its place, but a permutation of consecutive statements none of which
    holds a position kept every position. Now every statement of every a1
    span stands at its frozen order key (grammar_shapes_a1.A1_ORDERS, pinned
    here by size and digest). The class sweep: in every span, every
    adjacent pair of statements of one list, neither holding a position
    and with different headers, is swapped in a copy of the real
    definition; with the order marker the swap is refused by the order
    rule naming the moved statement's path, and with the marker off (the
    round-8 grammar plus positions) it is refused by nothing: each pair
    was free and is now bound. A header control: the two arguments of
    _team_resolve_live_family's quartet lock swapped (same shapes, no
    position), refused by the order rule alone. The real spans are
    admitted with the marker on."""
    import copy
    import hashlib
    import shape_grammar as _sg
    orders = sorted(_gs.A1_ORDERS)
    digest = hashlib.sha256(repr(orders).encode("utf-8")).hexdigest()[:16]
    assert (len(orders), digest) == (1537, "f6e1af03c9867031"), (len(orders), digest)
    assert _cw.ORDERED in _gs.A1_BINDINGS
    assert _gs.A1_ORDERS <= _gs.A1_BINDINGS
    on = _gs.A1_BINDINGS
    off = _gs.A1_BINDINGS - {_cw.ORDERED}
    mean = _gs.A1_MEANINGFUL

    def refusals(d, allowed):
        own = "binds %s (def)" % d.name
        return [why for _f, _ln, why in _cw.anchored_refusals(d, mean, allowed, "<r9>")
                if why != own]

    swapped = 0
    for f, ln, name, _n in _gs.A1_SPANS:
        d = copy.deepcopy(_span_def(f, ln, name))
        assert refusals(d, on) == [], (name, refusals(d, on)[:2])
        held = [p[3] for p in _gs.A1_POSITIONS if p[2] == name]
        paths = {}
        for n, p, fld in _sg.visit(d):
            if p is not None:
                paths[id(n)] = tuple(_cw._index_path(paths, n, p, fld))
        lists = []
        for n, _p, _f in _sg.visit(d):
            for _fld, v in _ast.iter_fields(n):
                if isinstance(v, list) and len(v) > 1 and all(
                        isinstance(s, _ast.stmt) for s in v):
                    lists.append(v)
        for v in lists:
            free = [not any(q[:len(paths[id(s)])] == paths[id(s)] for q in held)
                    for s in v]
            for i in range(len(v) - 1):
                if not (free[i] and free[i + 1]):
                    continue
                if _sg.header(v[i]) == _sg.header(v[i + 1]):
                    continue
                path = paths[id(v[i])]
                v[i], v[i + 1] = v[i + 1], v[i]
                got_on, got_off = refusals(d, on), refusals(d, off)
                v[i], v[i + 1] = v[i + 1], v[i]
                assert got_off == [], (name, path, got_off[:2])
                assert any("outside its frozen order" in w and f"at {path}" in w
                           for w in got_on), (name, path, got_on[:2])
                assert all("outside its frozen order" in w for w in got_on), (
                    name, path, got_on[:3])
                swapped += 1
    assert swapped == 57, swapped
    d = copy.deepcopy(_span_def(*next(
        (f, ln, name) for f, ln, name, _n in _gs.A1_SPANS
        if name == "_team_resolve_live_family")))
    (call,) = [n for n in _ast.walk(d) if isinstance(n, _ast.Call)
               and _ast.unparse(n) == "_team_quartet_lock(db, four_pids)"]
    call.args = [call.args[1], call.args[0]]
    assert refusals(d, off) == []
    got = refusals(d, on)
    assert got and all("outside its frozen order" in w for w in got), got[:3]


def test_r8_the_callee_table_is_the_frozen_one():
    """_A1_CALLEES names exactly the frozen forms, and each function this
    file's static imports bind stands at the form's frozen span, one of
    A1_SPANS."""
    want = {form: (f, ln, name) for form, f, ln, name in _gs.A1_CALLEES}
    assert set(_A1_CALLEES) == set(want), sorted(set(_A1_CALLEES) ^ set(want))
    spans = {(f, ln, name) for f, ln, name, _n in _gs.A1_SPANS}
    for form, fn in _A1_CALLEES.items():
        f, off = _cw.source_of(fn)
        d = _ast.parse(_textwrap.dedent(_inspect.getsource(fn))).body[0]
        got = (f, off + d.lineno, d.name)
        assert got == want[form] and got in spans, (form, got, want[form])


@pytest.mark.parametrize("form", sorted(f for f, *_ in _gs.A1_CALLEES))
def test_r8_a_callee_outside_the_table_is_refused(monkeypatch, form):
    """Each route the real walks take outside a module's namespace (a local
    `from ... import`, a module attribute, an accessor's attribute) reaches
    its callee ONLY through the frozen table: with the form's entry
    dropped, the real walks refuse at that call. With the full table they
    refuse nothing (test_r7_the_grammar_checks_every_walked_node_...)."""
    import sys as _sys
    me = _sys.modules[__name__]
    table = {k: v for k, v in _A1_CALLEES.items() if k != form}
    monkeypatch.setattr(me, "_A1_GRAMMAR", _cw.Grammar(
        _gs.A1_SHAPES, _gs.A1_MEANINGFUL, _gs.A1_BINDINGS, table,
        _gs.A1_NAMEDTUPLES))
    monkeypatch.setattr(me, "_POLICIES", {})
    got = [(w, p) for w, p in _a1_real_walks() if p]
    name = [n for _form, _f, _ln, n in _gs.A1_CALLEES if _form == form][0]
    assert got and any(name in str(x) for _w, p in got for x in p), (form, got)


_R8_WRITER = "\n\ndef _r8_writer(cls, *a):\n    raise SystemExit(a)\n"
_R8_SCOPE_CONTROLS = [
    # the report's own example (closed_walk:815): a store appended
    ("m5 closed_walk:815 a store to _Cand.__new__ appended", "append",
     _R8_WRITER + "\n\n_Cand.__new__ = staticmethod(_r8_writer)\n",
     "_Seat: a shape outside the definition scope at <r8_store>:"),
    ("m5 a setattr of _Cand appended", "append",
     _R8_WRITER + "\n\nsetattr(_Cand, '__new__', staticmethod(_r8_writer))\n",
     "_Seat: a shape outside the definition scope at <r8_setattr>:"),
    ("m5 the store inside the walked function", "inside",
     _R8_WRITER, "a shape outside the grammar at "),
    ("m5 a store to _Seat's field appended", "append",
     "\n\n_Seat._fields = ()\n",
     "_Seat: a shape outside the definition scope at <r8_fields>:"),
]


@pytest.mark.parametrize("scope_row", [c[0] for c in _R8_SCOPE_CONTROLS])
def test_r8_the_definition_scope_refuses_a_store_by_shape(scope_row):
    """M5: a copy of region_pick.py with a store to its constructor-pure
    class appended (or inside the walked function) is refused BY SHAPE when
    the real function _pick is walked over the copy; the unchanged copy
    (the negative control) is walked without a refusal."""
    import linecache
    import sys as _sys
    import types as _types
    import region_pick as _rp
    tag = {"m5 closed_walk:815 a store to _Cand.__new__ appended": "store",
           "m5 a setattr of _Cand appended": "setattr",
           "m5 the store inside the walked function": "inside",
           "m5 a store to _Seat's field appended": "fields"}

    def planted(name, extra, inside=False):
        src = _inspect.getsource(_rp)
        if inside:
            at = "def _pick(members,"
            assert src.count(at) == 1
            head, tail = src.split(at)
            first = tail.index("\n") + 1
            src = (head + at + tail[:first]
                   + "    _Cand.__new__ = staticmethod(_r8_writer)\n"
                   + tail[first:])
        text = src + extra
        mod = _types.ModuleType(f"r8_{name}")
        mod.__file__ = f"<r8_{name}>"
        linecache.cache[mod.__file__] = (len(text), None,
                                         text.splitlines(True), mod.__file__)
        _sys.modules[mod.__name__] = mod
        _a1_ib.register_source(mod, text, mod.__file__)
        exec(compile(text, mod.__file__, "exec"), mod.__dict__)
        return mod

    plain = planted("unchanged", "")
    _cw.plain_effects(plain._pick, _policy(plain))       # negative control
    for f, where, extra, text in _R8_SCOPE_CONTROLS:
        if f != scope_row:
            continue
        mod = planted(tag[f], extra, inside=(where == "inside"))
        with pytest.raises(Unclassified) as e:
            _cw.plain_effects(mod._pick, _policy(mod))
        assert text in str(e.value.args[0]), (f, e.value.args[0])


def test_r8_frozen_callee_picks_one_name_of_a_frozen_statement():
    """M4, the import route: a local import's form is its statement's text;
    a statement importing several names maps each BOUND name to its
    function. Only a frozen statement resolves, and of it only a name the
    table maps; a statement of one name maps to its function directly."""
    import types as _types

    def fa():
        return None

    def fb():
        return None

    g = _types.SimpleNamespace(imports={
        "from m import a, b as c": {"a": fa, "c": fb},
        "from m import a": fa})
    two = _ast.parse("from m import a, b as c").body[0]
    one = _ast.parse("from m import a").body[0]
    other = _ast.parse("from m import a, d").body[0]
    assert _cw._frozen_callee(g, two, "a") is fa
    assert _cw._frozen_callee(g, two, "c") is fb
    assert _cw._frozen_callee(g, two, "b") is None
    assert _cw._frozen_callee(g, one, "a") is fa
    assert _cw._frozen_callee(g, other, "a") is None
    assert _cw._frozen_callee(None, one, "a") is None


# --- round 8, M1: the static S analysis retired; a frozen execute lookup ----
# Ruling REHEARSAL-FOUR-R7-A1 M1 and W30b's rulings (a) and (b): an execute
# is 'read' only at a ro_covered.COVERED position whose OUTCOME is 'ok';
# WRITERS (main.py:16839 and :51703 included: grammar/lookup writers, not
# role-bound), the covered positions the role did not reach, and every
# position in neither table are 'write'.

_SR_RETIRED = ("SqlLists", "_SQL_END_WORDS", "_SQL_OTHER_COMMANDS", "_DML",
               "SQL_COMBINATIONS", "sql_texts", "_formatted", "guards",
               "local_sql", "builder_texts", "_builder_domain_texts",
               "_combine", "sql_tokens", "sql_kind", "sql_text",
               "guarded_names", "_lex_tokens", "_lex_views", "_LexError",
               "migration_table_ddl")


def test_r8_sr_the_lookup_reads_only_the_covered_ok_positions():
    """The lookup, position by position (ruling R-A): every COVERED
    position whose OUTCOME is green reads; every WRITERS position locks
    (main.py:16839 and :51703 named: 'ok' under the role, so the walk's lock
    rule alone bounds them); every other COVERED position (the reads the
    role did not reach) and a real execute in no table is a write; the key
    holds the file (a WRITERS line under another file's name is a write)."""
    def _sr_modules():
        import match_hold as _mh
        import match_report_window as _mrw
        import tournaments as _t
        return {"main.py": main, "match_hold.py": _mh,
                "match_report_window.py": _mrw, "tournaments.py": _t}


    def _sr_placed(entry):
        """(the walked definition's Bindings, the execute call node) standing
        at ro_covered `entry`'s position, read from the real span's source."""
        _w, f, ln, end, span = entry
        mod = _sr_modules()[f]
        d = _ast.parse(_textwrap.dedent(_inspect.getsource(getattr(mod, span)))).body[0]
        b = _cw.Bindings(mod, d)
        hits = [c for c in _ast.walk(d) if _cw._is_execute(c)
                and _cw._position(b, c) == (f, ln, end)]
        assert len(hits) == 1, (entry, len(hits))
        return b, hits[0]

    ok = {e[1:4] for e in _ro.COVERED if _ro.green(_ro.OUTCOME[e])}
    assert _A1_READS == ok, sorted(_A1_READS ^ ok)
    locks = {e[1:4] for e in _ro.WRITERS}
    assert len(locks) == 14 and {k for p, k in _A1_TABLE.items() if p in locks} == {"lock"}
    assert set(_A1_TABLE) == ok | locks
    for e in _ro.COVERED + _ro.WRITERS:
        b, c = _sr_placed(e)
        want = "read" if e[1:4] in ok else "lock" if e[1:4] in locks else "write"
        assert b.execute_kind(c, _A1_TABLE) == want, (e, want)
    for ln in (16839, 51703):
        e = [w for w in _ro.WRITERS if w[1] == "main.py" and w[2] == ln][0]
        b, c = _sr_placed(e)
        assert b.execute_kind(c, _A1_TABLE) == "lock", e
        # the key holds the file: the same line and end under another file
        assert b.execute_kind(c, {("tournaments.py",) + e[2:4]: "lock"}) == "write", e
        assert b.execute_kind(c, {e[1:4]: "lock"}) == "lock", e
    known = {e[1:4] for e in _ro.COVERED + _ro.WRITERS}
    d = _ast.parse(_textwrap.dedent(_inspect.getsource(main.queue_poll))).body[0]
    b = _cw.Bindings(main, d)
    other = [c for c in _ast.walk(d) if _cw._is_execute(c)
             and _cw._position(b, c) is not None
             and _cw._position(b, c) not in known]
    assert other, "queue_poll has no execute in neither table"
    assert {b.execute_kind(c, _A1_TABLE) for c in other} == {"write"}
    # a planted copy of a covered 'ok' call cannot be placed: a write
    e = [x for x in _ro.COVERED if _ro.OUTCOME[x] == "ok"][0]
    _b, c = _sr_placed(e)
    planted = _cw.Bindings(main, _ast.parse(
        "async def _sr_planted(db):\n    await " + _ast.unparse(c) + "\n").body[0])
    call = [x for x in _ast.walk(planted.where) if _cw._is_execute(x)][0]
    assert _cw._position(planted, call) is None
    assert planted.execute_kind(call, _A1_TABLE) == "write"


def test_r8_sr_every_walked_execute_is_classified_by_the_lookup(monkeypatch):
    """Every execute the real a1 walks visit is classified by the frozen
    lookup and by nothing else: each recorded kind is the table's answer
    for its position (_A1_TABLE, 'write' when absent); the walks visit a
    read, a lock and a write; and closed_walk holds no S symbol (each retired name occurs in
    its source 0 times)."""
    import pathlib
    import sys as _sys
    me = _sys.modules[__name__]
    monkeypatch.setattr(me, "_A1_GRAMMAR", _a1_grammar())
    monkeypatch.setattr(me, "_POLICIES", {})
    seen = []
    orig = _cw.Bindings.execute_kind

    def spy(self, call, reads):
        got = orig(self, call, reads)
        seen.append((_cw._position(self, call), got, reads is _A1_TABLE))
        return got

    monkeypatch.setattr(_cw.Bindings, "execute_kind", spy)
    _a1_real_walks()
    assert seen and all(t for _p, _k, t in seen), seen[:3]
    wrong = [x for x in seen if x[1] != _A1_TABLE.get(x[0], "write")]
    assert wrong == [], wrong
    kinds = {k for _p, k, _t in seen}
    assert kinds == {"read", "lock", "write"}, kinds
    text = (pathlib.Path(__file__).resolve().parent / "closed_walk.py"
            ).read_text(encoding="utf-8")
    left = {n: len(_re.findall(r"\b" + _re.escape(n) + r"\b", text))
            for n in _SR_RETIRED}
    assert all(v == 0 for v in left.values()), {k: v for k, v in left.items() if v}
    for n in _SR_RETIRED:
        assert not hasattr(_cw, n) and not hasattr(_cw.Bindings, n), n


# --- round 10 (ruling REHEARSAL-R9-A1): identity, never presence ----------
# Child gr's findings 8 (C, resolution_sites:202), 9 (C, resolution_sites:431)
# and 10 (D, closed_walk:859). Each negative is the report's own case,
# refused here; the side control (RF/r10/gr/neg_side.py) runs the same case
# on the 0b317394 harness and records that it was admitted there.

# The Visitor method each receiver negative adds: the report's own form.
_R10_PROBE_METHOD = ("    def _r10_probe(self, n):\n"
                     "        return self.b.named(n.id) == 'db'\n")
_R10_POLICY_FOR_BINDINGS = (
    "        self.b = (bindings if bindings is not None",
    "        self.b = (policy if bindings is not None")


def test_r10_n_resolution_sites_202_policy_selected_for_bindings():
    """Finding 8 (resolution_sites:202), the report's case: selecting
    `policy` instead of `bindings` in Visitor.__init__ and adding
    `self.b.named(n.id) == 'db'` in a Visitor method. Round 9 admitted it:
    the unused alternative's `Bindings(...)` call satisfied the presence
    check and the method's comparison counted no site. Now the store is
    refused by IDENTITY: its complete statement is not the frozen one
    (resolution_sites.RECEIVER_STORES), and the parameter the chosen
    alternative names reaches no frozen source (receiver_sources)."""
    import pathlib
    import resolution_sites as _rs
    here = pathlib.Path(__file__).resolve().parent
    base = {m: (here / f"{m}.py").read_text(encoding="utf-8") for m in (
        "closed_walk", "test_a1_identity_formation",
        "test_match_hold_admission_gate_pg")}
    old, new = _R10_POLICY_FOR_BINDINGS
    text = base["closed_walk"]
    assert text.count(old) == 1
    text = text.replace(old, new)
    at = text.index("    def __init__(self, policy,")
    text = text[:at] + _R10_PROBE_METHOD + "\n" + text[at:]
    assert text.count(_R10_PROBE_METHOD) == 1
    tree = _ast.parse(text)
    got = [why for _ln, why in _rs.form_problems(tree)]
    assert "Visitor.__init__'s store to `.b` is not its frozen statement" in got, got
    trees = {m: _ast.parse(t) for m, t in dict(base, closed_walk=text).items()}
    chain = _rs.receiver_source_problems(trees)
    assert any("is no frozen source" in g for g in chain), chain
    # the real files hold the frozen statement and chain
    real = {m: _ast.parse(t) for m, t in base.items()}
    assert all(_rs.form_problems(t) == [] for t in real.values())
    assert _rs.receiver_source_problems(real) == []


def test_r10_receiver_store_and_sources_are_frozen():
    """Round 10 (C), the receiver bound by identity, one control per route:
    the store's complete statement (pinned digests); each alternative's
    source (a resolver construction only through the module's one class
    statement, or `<X>.Bindings` through the one `import closed_walk as X`;
    a second binding of either refuses although the statement is
    unchanged); and the parameter's value chain across the three census
    modules (a caller handing on another value, a new caller, the class
    named other than as a callee), each refused, the real chain frozen."""
    import hashlib
    import pathlib
    import resolution_sites as _rs
    here = pathlib.Path(__file__).resolve().parent
    base = {m: (here / f"{m}.py").read_text(encoding="utf-8") for m in (
        "closed_walk", "test_a1_identity_formation",
        "test_match_hold_admission_gate_pg")}
    assert _rs.RECEIVER_STORES == {"Visitor": "deb50a21d5de8fad",
                                   "_Walk": "36214a5241768ebf"}
    rows = sorted(repr(x) for x in _rs.RECEIVER_SOURCES)
    assert (len(rows), hashlib.sha256("\n".join(rows).encode("utf-8"))
            .hexdigest()[:16]) == (10, "3cdfac8bc1d0f4ed"), rows
    real = {m: _ast.parse(t) for m, t in base.items()}
    assert _rs.receiver_source_problems(real) == []
    # the alternative-source route: the statement unchanged, its provider
    # binding doubled
    for mod, prog, want in (
            ("closed_walk", "\n\nBindings = dict\n",
             "the receiver's value alternative `Bindings("),
            ("test_match_hold_admission_gate_pg", "\n\n_cw = types\n",
             "the receiver's value alternative `_cw.Bindings("),
            # the sweep of the class: the receiver class itself, bound once
            # by its class statement
            ("closed_walk", "\n\nVisitor = dict\n",
             "the receiver class Visitor is not bound once"),
            ("test_match_hold_admission_gate_pg", "\n\n_Walk = dict\n",
             "the receiver class _Walk is not bound once")):
        got = [why for _ln, why in _rs.form_problems(_ast.parse(base[mod] + prog))]
        assert any(g.startswith(want) for g in got), (mod, got)
    # the store route: the complete statement changed while each of its
    # alternatives is still a frozen source (only the pinned digest
    # refuses it)
    for mod, old, new, cls in (
            ("closed_walk", "        self.b = (bindings if bindings is not None",
             "        self.b = (bindings if bindings is None", "Visitor"),
            ("test_match_hold_admission_gate_pg",
             "                              else stmts, session=self.policy.session,",
             "                              else stmts, session=None,", "_Walk")):
        assert base[mod].count(old) == 1, (mod, old)
        tree = _ast.parse(base[mod].replace(old, new))
        got = [why for _ln, why in _rs.form_problems(tree)]
        assert (f"{cls}.__init__'s store to `.b` is not its frozen statement"
                in got), (mod, got)
        trees = dict(real, **{mod: tree})
        assert _rs.receiver_source_problems(trees) == [], (mod, new)
    # the chain route
    for mod, old, new, want in (
            ("closed_walk", "bindings=bindings).accept(node).effects)",
             "bindings=policy).accept(node).effects)", "is no frozen source"),
            ("test_a1_identity_formation",
             "            return expr_effects(node, scope, opaque, " "bindings=b)",
             "            return expr_effects(node, scope, opaque, " "bindings=scope)",
             None),
            ("test_match_hold_admission_gate_pg",
             "    v = _cw.Visitor(w.policy, permitted=ends, bindings=w.b)",
             "    v = _cw.Visitor(w.policy, permitted=ends, bindings=w.policy)",
             "is no frozen source"),
            ("closed_walk", None,
             "\n\ndef _r10_probe(p):\n    return Visitor(p, bindings=p)\n",
             "an unfrozen source"),
            ("closed_walk", None, "\n\n_R10V = Visitor\n",
             "Visitor is named other than as a callee")):
        if old is None:
            text = base[mod] + new
        else:
            assert base[mod].count(old) == 1, (mod, old)
            text = base[mod].replace(old, new)
        trees = dict(real, **{mod: _ast.parse(text)})
        got = _rs.receiver_source_problems(trees)
        assert got and (want is None or any(want in g for g in got)), (
            mod, new, got)


# Finding 9's case, as the report states it: `name is not 'db' is not None`.
_R10_CHAINED = ("def _r7_probe(n):\n    name = n.id\n"
                "    if name is not 'db' is not None:\n        return 1\n"
                "    return 0\n")


def test_r10_n_resolution_sites_431_chained_is_not_none():
    """Finding 9 (resolution_sites:431), the report's case: `name is not 'db'
    is not None` with `name` bound from `n.id`. Round 9 admitted it: the
    chain matched the admitted one-comparison shape (a Compare's lists are
    sets of classes) and the None exemption suppressed the whole chain, so
    the spelling decision counted nothing. Now it is refused both ways: the
    chain is a form problem (comparison arity), and the census counts the
    span's spelling decision (the exemption covers one comparison with a
    single None comparator only)."""
    import pathlib
    import warnings
    import resolution_sites as _rs
    here = pathlib.Path(__file__).resolve().parent
    base = {m: (here / f"{m}.py").read_text(encoding="utf-8") for m in (
        "closed_walk", "test_a1_identity_formation",
        "test_match_hold_admission_gate_pg")}
    mutated = dict(base, closed_walk=base["closed_walk"] + "\n\n" + _R10_CHAINED)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        tree = _ast.parse(mutated["closed_walk"])
        census = [s for s, _sites in _census_problems(mutated)]
    assert census == ["closed_walk:_r7_probe"], census
    form = [why for _ln, why in _rs.form_problems(tree)]
    assert "a chained comparison of 2 operators" in form, form


def test_r10_comparison_arity_and_none_exemption():
    """Round 10 (C), one control per route of finding 9's fix. The arity
    route: a chained comparison with no walked identifier in it is still a
    form problem, and a two-operand one is not. The exemption route: a
    single `<key> is None` / `is not None` is exempt; `None is <key>` (None
    on the left) and `<key> is None is None` (two comparisons) are counted,
    each read alone (no form route involved for the first)."""
    import resolution_sites as _rs
    import warnings
    for prog, form in (
            ("def _r7_probe(a, b, c):\n    return a < b < c\n", True),
            ("def _r7_probe(a, b):\n    return a < b\n", False)):
        got = [w for _l, w in _rs.form_problems(_ast.parse(prog), False)]
        assert (("a chained comparison of 2 operators" in got) is form), (prog, got)
    for cmp, counted in (("name is None", False), ("name is not None", False),
                         ("None is name", True), ("name is None is None", True),
                         ("name == None", True)):
        prog = f"def f(n):\n    name = n.id\n    return {cmp}\n"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            fn = _ast.parse(prog).body[0]
        got = [k for k, _ln in _rs.sites(fn)]
        assert (got == ["spelling"]) is counted, (cmp, got)


def test_r10_n_closed_walk_859_int_rebound_by_the_module(monkeypatch):
    """Finding 10 (closed_walk:859), the report's case: a module binding
    `int = writer` in main, where writer changes observable state before
    returning builtins.int, under the unchanged `_ffa_gather_decide`.
    Round 9 kept its purity claim (the frozen span admitted, no effect
    reported): `int` was accepted by its spelling. Now the walk refuses:
    the scope's binding of `int` is not its frozen provider
    (closed_walk.Bindings.listed, the a1 table bound to builtins.int)."""
    import builtins
    marks = []

    def writer(x=0, *rest):
        marks.append(x)
        return builtins.int(x, *rest)
    fresh = _cw.Policy(main, _PURE_CALLS, _PURE_METHODS, _PURE_AWAITS, _A1_TABLE)
    fresh.grammar = _A1_GRAMMAR
    assert _cw.plain_effects(main._ffa_gather_decide, fresh) == frozenset()
    monkeypatch.setattr(main, "int", writer, raising=False)
    main._ffa_gather_decide(main.FFA_MIN_PLAYERS, 0.0, 0.0)
    assert marks, "the planted writer changed no state"
    again = _cw.Policy(main, _PURE_CALLS, _PURE_METHODS, _PURE_AWAITS, _A1_TABLE)
    again.grammar = _A1_GRAMMAR
    with pytest.raises(Unclassified) as e:
        _cw.plain_effects(main._ffa_gather_decide, again)
    assert "a call of int, whose int is not its frozen provider" in e.value.args[0][1], e.value.args


def test_r10_provider_identity_routes(monkeypatch):
    """Round 10 (D), one control per route of the provider rule, each
    admitted unchanged and refused when its provider is replaced: a dotted
    spelling's root (main's `_json` replaced), its attribute (`json.loads`
    itself replaced), an awaited listed call (main's `asyncio` replaced),
    the builtins route (main's `__builtins__` replaced by a mapping that
    holds a writer), and a root the function binds by its frozen local
    import (`import uuid as uuid_mod`; the same import of another module
    refuses)."""
    import builtins
    import types

    def writer(*a, **k):
        return None

    # round 11 (FIX-R11-ID): the one policy, its tables built BEFORE any
    # provider is rebound below (a provider rebound before a table is built
    # refuses the table itself: test_r11_n_a1_5655_json_loads_wrapper_
    # before_the_table); the routes rebind after it, listed()'s case
    policy = _cw.Policy(main, _PURE_CALLS, _PURE_METHODS, _PURE_AWAITS,
                        _A1_TABLE)
    policy.grammar = _A1_GRAMMAR

    def effects(src, fn_src=None):
        d = _ast.parse(fn_src or "def f(x):\n    pass\n").body[0]
        b = _cw.Bindings(main, d, grammar=_A1_GRAMMAR)
        node = _ast.parse(src, mode="eval").body
        try:
            return _cw.expr_effects(node, policy, bindings=b)
        except Unclassified as exc:
            return exc.args[0][1]
    ok = [("call", "pure")]
    assert effects("_json.loads(x)") == ok
    assert effects("int(x)") == ok
    imp = "def f(x):\n    import uuid as uuid_mod\n    return uuid_mod.uuid4()\n"
    assert effects("uuid_mod.uuid4()", imp) == ok
    bad = "def f(x):\n    import json as uuid_mod\n    return uuid_mod.uuid4()\n"
    assert effects("uuid_mod.uuid4()", bad) == (
        "a call of uuid_mod.uuid4, whose uuid_mod is not its frozen provider")
    with monkeypatch.context() as m:
        m.setattr(main, "_json", types.SimpleNamespace(loads=_a1_json.loads))
        assert effects("_json.loads(x)") == (
            "a call of _json.loads, whose _json is not its frozen provider")
    with monkeypatch.context() as m:
        m.setattr(_a1_json, "loads", writer)
        assert effects("_json.loads(x)") == (
            "a call of _json.loads, whose loads is not its frozen provider")
    with monkeypatch.context() as m:
        m.setattr(main, "__builtins__", {"int": writer}, raising=False)
        assert effects("int(x)") == (
            "a call of int, whose int is not its frozen provider")
    with monkeypatch.context() as m:
        m.setattr(main, "__builtins__", builtins)
        assert effects("int(x)") == ok
    policy = _cw.Policy(main, _PURE_CALLS, _PURE_METHODS, _PURE_AWAITS, _A1_TABLE)
    policy.grammar = _A1_GRAMMAR
    d = _ast.parse("async def f(x):\n    await asyncio.sleep(0)\n").body[0]
    node = d.body[0].value
    b = _cw.Bindings(main, d, grammar=_A1_GRAMMAR)
    assert _cw.expr_effects(node, policy, bindings=b) == ok
    with monkeypatch.context() as m:
        m.setattr(main, "asyncio", types.SimpleNamespace(sleep=asyncio.sleep))
        with pytest.raises(Unclassified) as e:
            _cw.expr_effects(node, policy, bindings=b)
        assert "whose asyncio is not its frozen provider" in e.value.args[0][1]


def test_r10_pure_providers_are_the_frozen_ones():
    """Round 10 (D): every pure table the a1 walks and closed_walk's plain
    bodies read maps exactly round 9's spellings (grammar_providers
    .FAMILIES) to providers whose descriptions are the frozen ones
    (grammar_providers.PROVIDERS: per component, a module's name, else the
    object's module and qualified name), so a provider rebound before the
    tables were built fails here; the policies the walks build hold these
    tables; StakeRefundRefused, main's own class, is bound by main's one
    top-level statement of that name, its class statement."""
    import types
    import grammar_providers as _gp
    tables = {"closed_walk.PLAIN_BODY_CALLS": _cw.PLAIN_BODY_CALLS,
              "a1._PURE_CALLS": _PURE_CALLS, "a1._PURE_AWAITS": _PURE_AWAITS}
    for fam, table in tables.items():
        assert set(table) == set(_gp.FAMILIES[fam]), fam
        for spelling, objs in table.items():
            # round 11 (FIX-R11-ID, finding a1:5655): each provider IS the
            # definition its frozen description addresses (identity_binder
            # .trusted), never the object's writable __module__/__qualname__
            desc = _gp.PROVIDERS[spelling]
            assert len(objs) == len(desc), (fam, spelling)
            for o, (m, q) in zip(objs, desc):
                assert _a1_ib.trusted(o, m, q) is True, (fam, spelling, m, q)
    p = _policy()
    assert p.pure_calls == _PURE_CALLS and p.pure_awaits == _PURE_AWAITS
    sub = _cw.Policy(main, {}, (), {}, {})
    assert sub.pure_calls == {} and sub.pure_awaits == {}
    st = _cw._one_top_binding(_main_tree(), "StakeRefundRefused")
    assert isinstance(st, _ast.ClassDef) and st.name == "StakeRefundRefused"


def test_r10_sweep_sites_are_counted():
    """Round 10 (E), child gr's sweep of the class: every hit of the three
    operations (a receiver trusted by a test, a comparison-shape admission
    or constant-keyed exemption, a callee accepted by name) over the files
    the child owns is listed with its disposition in the round-10 notes;
    the counts per (operation, file) are frozen in grammar_sweep_r10.COUNTS,
    so a new site fails here until it is listed and judged."""
    import pathlib
    import grammar_sweep_r10 as _gsw
    here = pathlib.Path(__file__).resolve().parent
    _hits, counts = _gsw.sweep(str(here))
    assert counts == _gsw.COUNTS, sorted(
        set(counts.items()) ^ set(_gsw.COUNTS.items()))


# --- round 11 (ruling FOUR-R10-A2, FIX-R11-ID; ruling FOUR-R11-A1) ---------
# Identity is the evidence and spelling only a filter: one negative per
# round-10 finding of the class (F8 closed_walk:1949, F9 closed_walk:1125,
# F10 closed_walk:1775, F11 a1:5655; F7 gate:842 is in the gate file), each
# with its positive control in the same test.


def _r11_policy(scope=None, grammar=True):
    p = _cw.Policy(main if scope is None else scope, _PURE_CALLS,
                   _PURE_METHODS, _PURE_AWAITS, _A1_TABLE)
    p.grammar = _A1_GRAMMAR if grammar else None
    return p


def _r11_planted(tag, text):
    """A module r11_<tag> holding main's names, then `text` executed over
    it; its text registered with the identity binder first (GROUP 1)."""
    import linecache
    import sys as _sys
    import types as _types
    mod = _types.ModuleType(f"r11_{tag}")
    mod.__file__ = f"<r11_{tag}>"
    linecache.cache[mod.__file__] = (len(text), None, text.splitlines(True),
                                     mod.__file__)
    mod.__dict__.update({k: v for k, v in vars(main).items()
                         if not k.startswith("__")})
    _sys.modules[mod.__name__] = mod
    _a1_ib.register_source(mod, text, mod.__file__)
    exec(compile(text, mod.__file__, "exec"), mod.__dict__)
    return mod


def test_r11_n_closed_walk_1949_int_rebound_after_the_cache_is_warm(monkeypatch):
    """F8: the SAME policy, its cache warm with _ffa_gather_decide's empty
    effects, then `main.int = writer` (a writer that changes state): the
    cache hit is revalidated by the binder's Deps and dropped, and the walk
    refuses. Round 10 returned the cached empty effects."""
    import builtins
    marks = []

    def writer(x=0, *rest):
        marks.append(x)
        return builtins.int(x, *rest)
    p = _r11_policy()
    assert _cw.plain_effects(main._ffa_gather_decide, p) == frozenset()
    assert _cw.plain_effects(main._ffa_gather_decide, p) == frozenset()
    monkeypatch.setattr(main, "int", writer, raising=False)
    main._ffa_gather_decide(main.FFA_MIN_PLAYERS, 0.0, 0.0)
    assert marks, "the planted writer changed no state"
    with pytest.raises(Unclassified) as e:
        _cw.plain_effects(main._ffa_gather_decide, p)
    assert "int" in e.value.args[0][1], e.value.args


def test_r11_n_closed_walk_1125_a_wraps_wrapper_over_the_callee(monkeypatch):
    """F9: `_ffa_gather_decide` replaced by a functools.wraps wrapper whose
    own body changes state: the callee route reads the ACTUAL callable and
    refuses it (a __wrapped__ layer), and the a1 source reader refuses to
    read the wrapped body in its place. Unchanged, both admit."""
    marks = []
    orig = main._ffa_gather_decide

    @_functools.wraps(orig)
    def wrapper(*a, **k):
        marks.append(a)
        return orig(*a, **k)
    d = _ast.parse("def f(n, a, b):\n    return _ffa_gather_decide(n, a, b)\n").body[0]
    node = d.body[0].value
    b = _cw.Bindings(main, d, grammar=_A1_GRAMMAR)
    assert _cw.expr_effects(node, _r11_policy(), bindings=b) == [("call", "pure")]
    assert "def _ffa_gather_decide" in _inspect.getsource(main._ffa_gather_decide)
    monkeypatch.setattr(main, "_ffa_gather_decide", wrapper)
    main._ffa_gather_decide(main.FFA_MIN_PLAYERS, 0.0, 0.0)
    assert marks, "the wrapper changed no state"
    b = _cw.Bindings(main, d, grammar=_A1_GRAMMAR)
    with pytest.raises(Unclassified) as e:
        _cw.expr_effects(node, _r11_policy(), bindings=b)
    assert "_ffa_gather_decide" in e.value.args[0][1], e.value.args
    with pytest.raises(Unclassified):
        _inspect.getsource(main._ffa_gather_decide)


_R11_F10_SRC = '''class WriterDict(dict):
    def get(self, k, d=None):
        R11_MARKS.append(k)
        return dict.get(self, k, d)


R11_MARKS = []


def planted_writer_dict():
    return _rules_normalize(WriterDict(ff=True))


def planted_attribute(obj):
    return _rules_normalize(obj.payload)


HOLDER = WriterDict(ff=True)


def planted_attribute_site():
    return planted_attribute(HOLDER)


def planted_parameter(rules):
    return _rules_normalize(rules)


def planted_literal():
    return _rules_normalize({"ff": True, "src": "lobby"})


def planted_json(text):
    return _rules_normalize(_json.loads(text))


def planted_unproven():
    return _rules_normalize(type("x"))
'''


def test_r11_n_closed_walk_1775_a_receiver_proven_by_provenance():
    """F10 (ruling FOUR-R11-A1 (3)): _rules_normalize's purity rests on
    `raw.get`, a method of its parameter: its verdict is CONDITIONAL
    ("receiver:raw:row"), discharged at each call site by the argument's
    provenance. A display and a json.loads result discharge it (GREEN); a
    parameter carries it to the caller; an attribute of an unproven value
    and the report's WriterDict refuse. WriterDict's .get is not the frozen
    dict.get (the binder), and running the report's call changes state."""
    mod = _r11_planted("f10", _R11_F10_SRC)
    eff = _cw.plain_effects(main._rules_normalize, _r11_policy(grammar=False))
    assert eff == frozenset({"receiver:raw:row"}), eff
    assert _cw.plain_effects(mod.planted_literal,
                             _r11_policy(mod, grammar=False)) == frozenset()
    assert _cw.plain_effects(mod.planted_json,
                             _r11_policy(mod, grammar=False)) == frozenset()
    assert _cw.plain_effects(mod.planted_parameter, _r11_policy(
        mod, grammar=False)) == frozenset({"receiver:rules:row"})
    # a value READ from the parameter: the parameter must be builtin whole
    assert _cw.plain_effects(mod.planted_attribute, _r11_policy(
        mod, grammar=False)) == frozenset({"receiver:obj:deep"})
    for fn in (mod.planted_attribute_site, mod.planted_writer_dict):
        with pytest.raises(Unclassified) as e:
            _cw.plain_effects(fn, _r11_policy(mod, grammar=False))
        assert "cannot prove builtin" in e.value.args[0][1] or (
            "does not classify" in e.value.args[0][1]) or (
            "is not the definition it names" in e.value.args[0][1]), e.value.args
    # a span walked on its own: no walked call site discharges its parameter
    d = _ast.parse("def f(x):\n    return _rules_normalize(x)\n").body[0]
    b = _cw.Bindings(main, d, grammar=None)
    with pytest.raises(Unclassified) as e:
        _cw.expr_effects(d.body[0].value, _r11_policy(grammar=False), bindings=b)
    assert "which no walked call site discharges" in e.value.args[0][1], e.value.args
    # the discharge route's own refusal: a listed provider the walk admits,
    # whose result's provenance it cannot prove builtin
    with pytest.raises(Unclassified) as e:
        _cw.plain_effects(mod.planted_unproven, _r11_policy(mod, grammar=False))
    assert ("a receiver of its row methods, is type('x'), which the walk "
            "cannot prove builtin") in e.value.args[0][1], e.value.args
    # the method branch's span-level refusal: a parameter's method walked on
    # its own, with no def_effects walk to carry the condition
    d = _ast.parse("def f(x):\n    return x.get('ff')\n").body[0]
    b = _cw.Bindings(main, d, grammar=None)
    with pytest.raises(Unclassified) as e:
        _cw.expr_effects(d.body[0].value, _r11_policy(grammar=False), bindings=b)
    assert "a receiver no walked call site discharges" in e.value.args[0][1], (
        e.value.args)
    assert _a1_ib.trusted(mod.WriterDict.get, "builtins", "dict.get") is False
    assert _a1_ib.trusted(dict.get, "builtins", "dict.get") is True
    mod.planted_writer_dict()
    assert mod.R11_MARKS, "the report's call changed no state"


_R11_F10_MORE_SRC = '''def planted_scoped(rules, obj):
    seen = [rules for rules in obj.items]
    return _rules_normalize(rules), seen
'''


def test_r11_f10_unions_scalar_results_and_nested_scopes():
    """F10, round 11 run 12's classes, each route with its own control:
    (1) a name bound to a session row in one binding and to a parameter in
    another is the union of both, judged per alternative: a builtin method
    on it refuses (the row alternative), a row method carries the
    parameter's condition; (2) `.scalars()` yields column values, builtin;
    (3) a comprehension's own target is not the function's parameter of
    the same spelling (Python's scoping)."""
    def walk(src):
        d = _ast.parse(src).body[0]
        return _cw.def_effects(d, main, _r11_policy(grammar=False), d.name,
                               receivers=True)
    head = ("async def f(db, p):\n"
            "    row = (await db.execute(text('SELECT 1'))).mappings().first()\n"
            "    v = p if p else row\n")
    with pytest.raises(Unclassified) as e:
        walk(head + "    return v.lower()\n")
    assert "a method call v.lower whose receiver the walk cannot prove builtin" in (
        e.value.args[0][1]), e.value.args
    assert "receiver:p:row" in walk(head + "    return v.get('k')\n")
    got = walk("async def g(db):\n"
               "    vals = (await db.execute(text('SELECT 1'))).scalars().all()\n"
               "    return [x.lower() for x in vals]\n")
    assert not any(x.startswith("receiver:") for x in got), got
    mod = _r11_planted("f10more", _R11_F10_MORE_SRC)
    assert _cw.plain_effects(mod.planted_scoped, _r11_policy(
        mod, grammar=False)) == frozenset({"receiver:rules:row"})


def test_r11_supplied_helper_bound_by_the_function():
    """Round 11 (probe 4): a helper the caller supplies and reads
    separately (the family pick of _relock_outcome_problems) is read at its
    calls as that definition (Bindings.supplied), never through the
    module's binding of a planted name; a function that binds the name
    itself refuses, since its call is then not the supplied helper."""
    pick = _ast.parse("async def pick(db):\n    return ('fresh', None)\n").body[0]
    ok = _ast.parse("async def r(db):\n    x = await pick(db)\n").body[0]
    bad = _ast.parse("async def r(db, other):\n    pick = other\n"
                     "    x = await pick(db)\n").body[0]
    b = _cw.Bindings(main, ok, grammar=None)
    assert _calls_supplied(ok.body[0].value, pick, b)
    b = _cw.Bindings(main, bad, grammar=None)
    with pytest.raises(Unclassified) as e:
        _calls_supplied(bad.body[1].value, pick, b)
    assert "a supplied helper the walk reads separately, is bound by the " in (
        e.value.args[0][1]), e.value.args


def test_r11_f10_operator_over_a_container():
    """Round 11 (run 17, _operated): an operator over exact containers is a
    container of the same elements (`[row] + [row]`; a display of builtin
    values alone is builtin whole, probe 8), and an identity test is a
    bool; an element's row method is then admitted, its builtin method
    refused. An operator over a session result stays unproven."""
    def walk(src):
        d = _ast.parse(src).body[0]
        return _cw.def_effects(d, main, _r11_policy(grammar=False), d.name,
                               receivers=True)
    head = ("async def g(db):\n"
            "    row = (await db.execute(text('SELECT 1'))).mappings().first()\n"
            "    xs = [row] + [row]\n"
            "    same = xs is None\n")
    got = walk(head + "    return xs[0].get('k'), same\n")
    assert not any(x.startswith("receiver:") for x in got), got
    with pytest.raises(Unclassified):
        walk(head + "    return xs[0].lower()\n")
    with pytest.raises(Unclassified):
        walk("async def g(db):\n"
             "    rows = (await db.execute(text('SELECT 1'))).mappings().all()\n"
             "    xs = rows + ['b']\n"
             "    return [x.lower() for x in xs]\n")


def test_r11_nested_def_through_the_resolver():
    """Round 11 (run 20): a nested definition's call is read through the
    resolver (Bindings.nested_def): its one binding, a `def` that binds in
    a scope the call sees; a def bound inside another nested scope, or a
    name bound twice, is unproven (None)."""
    def at(src):
        d = _ast.parse(src).body[0]
        call = d.body[-1].value
        return _cw.Bindings(main, d, grammar=None).nested_def(call.func, call), d
    got, d = at("def f(db):\n    def state():\n        return 1\n"
                "    return state()\n")
    assert got is d.body[0], got
    got, _d = at("def f(db):\n    def g():\n        def state():\n"
                 "            return 1\n        return 0\n    return state()\n")
    assert got is None, got
    got, _d = at("def f(db, k):\n    def state():\n        return 1\n"
                 "    state = k\n    return state()\n")
    assert got is None, got


def test_r11_binder_deps_hold_nested_reads():
    """FIX-R11-ID, round 11 run 11: a Deps holds what a nested recording
    read and what a carried cache hit read, by reference: rebinding a name
    only the nested walk read drops the enclosing entry too."""
    import types as _types
    ns = _types.SimpleNamespace(x=1, y=2)
    with _a1_ib.recording() as outer:
        with _a1_ib.recording() as inner:
            _a1_ib.observe(ns, "x", ns.x)
    assert inner.valid() and outer.valid()
    ns.x = 3
    assert not inner.valid() and not outer.valid()
    with _a1_ib.recording() as cached:
        _a1_ib.observe(ns, "y", ns.y)
    with _a1_ib.recording() as user:
        _a1_ib.carry(cached)
    assert user.valid()
    ns.y = 4
    assert not user.valid()


def test_r11_n_a1_5655_json_loads_wrapper_before_the_table(monkeypatch):
    """F11: `json.loads` replaced by a functools.wraps wrapper (which copies
    __module__, __qualname__ and __name__) BEFORE a provider table is
    built: the table refuses at construction (closed_walk.Providers, by
    identity_binder.trusted), and the provider assertion refuses it.
    Unchanged, the same construction is admitted."""
    marks = []
    orig = _a1_json.loads

    @_functools.wraps(orig)
    def loads(*a, **k):
        marks.append(a)
        return orig(*a, **k)
    built = _cw.Providers({"_json.loads": (_a1_json, _a1_json.loads)})
    assert built["_json.loads"][1] is orig
    monkeypatch.setattr(_a1_json, "loads", loads)
    assert (loads.__module__, loads.__qualname__) == ("json", "loads")
    _a1_json.loads("1")
    assert marks, "the wrapper changed no state"
    with pytest.raises(Unclassified) as e:
        _cw.Providers({"_json.loads": (_a1_json, _a1_json.loads)})
    assert "not the definition json.loads" in e.value.args[0][1], e.value.args
    assert _a1_ib.trusted(_a1_json.loads, "json", "loads") is False


def test_r11_binder_registration_closes_at_freeze():
    """GROUP 1 (ruling FOUR-R11-A1 (2)): a registered module's definitions
    are proven by code equality against a fresh compile of the registered
    text; a re-registration refuses, a registration after the module's
    first proof refuses, and a definition the text does not make is not
    trusted."""
    import types as _types
    text = "def f(x):\n    return x\n"
    mod = _r11_planted("reg", text)
    assert _a1_ib.trusted_function(mod.f) is True
    with pytest.raises(_a1_ib.RegistrationRefused):
        _a1_ib.register_source(mod, text, mod.__file__)
    import sys as _sys
    other = _types.ModuleType("r11_other")
    other.__file__ = "<r11_other>"
    _sys.modules[other.__name__] = other
    exec(compile("def f(x):\n    return x\n", other.__file__, "exec"),
         other.__dict__)
    assert _a1_ib.trusted_function(other.f) is False      # never registered
    late = _types.ModuleType("r11_late")
    late.__file__ = "<r11_late>"
    _sys.modules[late.__name__] = late
    _a1_ib.register_source(late, "def g():\n    return 1\n", late.__file__)
    exec(compile("def g():\n    return 2\n", late.__file__, "exec"),
         late.__dict__)
    assert _a1_ib.trusted_function(late.g) is False       # another text
    with pytest.raises(_a1_ib.RegistrationRefused):
        _a1_ib.register_source(late, "def g():\n    return 2\n", late.__file__)
    with pytest.raises(_a1_ib.RegistrationRefused):
        _a1_ib.register_source(main, "x = 1\n", main.__file__)


# ---------------------------------------------------------------------------
# Rulings FOUR-R11-A8 and FOUR-R11-A11 (2): the open recorder over this
# module. One freeze before its first id and one thaw after its last, on
# ro_census.OpenRecorder frozen at production's own URL
# (database.DATABASE_URL, in the form asyncpg resolves). No id of this module
# reaches an open (the census in test_r11_rec_pg), so the thaw requires the
# recorder active, zero connections built and zero opens recorded: an open,
# if one ever appears, fails the run. The control (test_r11_rec_pg) plants an
# open inside a window frozen by r11_open_window.a1_freeze and is refused by
# r11_open_window.a1_window_refusal with the recorder's own message. The
# fixture is defined in r11_open_window (every non-test function of this
# module is walker code its walker grammar must admit) and is this module's
# by this import.

from r11_open_window import _a1_open_window  # noqa: E402,F401
