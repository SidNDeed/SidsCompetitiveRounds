"""POST /api/v1/matches/macro-evidence answers the same whatever flag rows
the caller has (the Codex SMALL-ABC-R1 and R2 HIGHs on the small docket's
item c).

Required behaviour: for a valid POST the response status, body and wait are
identical whatever the caller's flag state on that match -- none, pending,
confirmed, dismissed, pending under the legacy reporter_steam key, a flag
naming the opponent, or a flag row another transaction holds locked -- and on
a retry of the same evidence. The flag state may change only what is written
to flagged_matches, and that happens AFTER the response, in the background
task the route schedules (main._macro_evidence_attach): the request path
reads no flag row at all, so no flag row can make it wait, fail or answer
differently. Round 1 unified the answer but left the flag reads and a FOR
UPDATE on the caller's flag row on the request path; a held row then made the
flagged request wait (and with a lock_timeout, fail) while the unflagged one
answered at once.

Live PostgreSQL. players, matches and flagged_matches are built from the
models (columns and types, no foreign keys) in one throwaway schema for the
module; one match between two synthetic players is seeded once; every case
starts with no flag row, files its own, and POSTs the same signed evidence
through the route function itself (main.submit_macro_evidence) on a session
whose search_path is that schema, then runs the background tasks the route
added, as Starlette does once the response has been handed over for
transmission. The signature is the real HMAC over the route's canonical
under a test secret; the Steam session check, which runs before anything
here and reads no flag, is a no-op.

The background attach itself (Codex SMALL-ABC-R3/R4): two attaches for one
match and reporter -- of one fingerprint, or of two -- the second entering
while the first holds the (match, reporter) advisory lock, end with exactly
one row; every database error but a certainly permanent one (class 22, 23,
42, or a programming error) is retried through the ladder (a deadlock, a
failover's 57P01, a connection refused arriving as InterfaceError), a
permanent one goes to the fallback at once, and the fallback itself is
retried.

Mutation controls (#391): the shipped route with the attach run on the
request path and its outcome answered (the pre-fix shape), the attach
without its fingerprint lock, and the round-2 ladder that retried only
55P03 must each turn their check red; inert twins stay green.

MACRO_EVIDENCE_TEST_PG_DSN names a throwaway database (postgresql:// or the
postgresql+asyncpg:// form); unset, every executed case FAILS rather than
skips (#342), and MACRO_EVIDENCE_TEST_PG_OPTOUT=1 makes that a named skip.
"""

import ast
import asyncio
import datetime as dt
import hashlib
import hmac
import inspect
import json
import os
import sys
import textwrap
import time
import uuid
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "api"))
sys.path.insert(0, str(HERE))

import main  # noqa: E402
import models  # noqa: E402
from test_admin_evidence_cells_pg import _required_defaults  # noqa: E402

try:
    import asyncpg  # noqa: F401
except ImportError:                                    # pragma: no cover
    asyncpg = None

DSN_VAR = "MACRO_EVIDENCE_TEST_PG_DSN"
OPTOUT_VAR = "MACRO_EVIDENCE_TEST_PG_OPTOUT"
_RAW = os.environ.get(DSN_VAR) or ""
PLAIN_DSN = _RAW.replace("postgresql+asyncpg://", "postgresql://")
ASYNC_DSN = PLAIN_DSN.replace("postgresql://", "postgresql+asyncpg://", 1)
OPTOUT = str(os.environ.get(OPTOUT_VAR) or "").strip().lower() in {"1", "true", "yes", "on"}

TABLES = (models.Player.__table__, models.Match.__table__, models.FlaggedMatch.__table__)
PLAYER_REQUIRED = _required_defaults(models.Player.__table__)
MATCH_REQUIRED = _required_defaults(models.Match.__table__)
FLAG_REQUIRED = _required_defaults(models.FlaggedMatch.__table__)

UTC = dt.timezone.utc
SECRET = "macro-evidence-test-secret"
LOCK_TIMEOUT_S = 1.0          # the request sessions' lock_timeout in the held-row cases

# Test-only identities: digit strings of the route's accepted shape that are
# no Steam account's id.
P1, P2 = "10000000000000001", "10000000000000002"
ROOM = "macro-flag-room"
P1_ROUNDS, P2_ROUNDS, DURATION = 3, 1, 300
TIMELINE = "12:30:40,15:31:41"

# case -> the flag rows filed on the match first: (attribution key, subject,
# reviewed as). The reporter is P1 throughout.
CASES = {
    "none": [],
    "pending": [("suspect_steam", P1, None)],
    "confirmed": [("suspect_steam", P1, "confirmed_cheat")],
    "dismissed": [("suspect_steam", P1, "false_positive")],
    "legacy key": [("reporter_steam", P1, None)],
    "opponent pending": [("suspect_steam", P2, None)],
}
# What each case must still RECORD differently once the background task has
# run: the reporter's suspected_macro rows on the match, and whether the
# newest one supersedes a reviewed flag. A pending flag is merged into; a
# reviewed one is kept and a new row supersedes it; otherwise a new row.
RECORDED = {
    "none": (1, False),
    "pending": (1, False),
    "confirmed": (2, True),
    "dismissed": (2, True),
    "legacy key": (1, False),
    "opponent pending": (1, False),
}


def _require_live_pg():
    if PLAIN_DSN and asyncpg is not None:
        return
    if OPTOUT:
        pytest.skip("%s is unset and %s=1: the macro-evidence answers were deliberately "
                    "not read from PostgreSQL" % (DSN_VAR, OPTOUT_VAR))
    pytest.fail("%s is unset (or asyncpg is missing), so the macro-evidence route was "
                "never executed; point it at a throwaway database, or set %s=1 to "
                "waive the coverage deliberately" % (DSN_VAR, OPTOUT_VAR))


def _sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _payload():
    """One valid signed evidence body from P1, its canonical built the way the
    route builds it (with the shared-token marker)."""
    started = (dt.datetime.now(UTC) - dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = {
        "reporter_steam_id": P1, "p1_steam_id": P1, "p2_steam_id": P2,
        "photon_room_id": ROOM, "match_started_at": started,
        "duration_seconds": DURATION, "shared_game_token": True,
        "p1_rounds_won": P1_ROUNDS, "p2_rounds_won": P2_ROUNDS,
        "macro_suspect_seconds": 20, "peak_keys_per_second": 31,
        "peak_clicks_per_second": 12, "peak_events_per_second": 43,
        "suspect_windows": TIMELINE,
    }
    canonical = (
        "macro-evidence:%s:%s:%s:%s:%s:%d:1:%d:%d:%d:%d:%d:%d:%s"
        % (P1, P1, P2, _sha(ROOM), _sha(started), DURATION, P1_ROUNDS, P2_ROUNDS,
           20, 31, 12, 43, _sha(TIMELINE)))
    body["hmac_signature"] = hmac.new(SECRET.encode(), canonical.encode(),
                                      hashlib.sha256).hexdigest()
    return body


# -- the route's shape and its variants -------------------------------------------

def _route_def():
    src = textwrap.dedent(inspect.getsource(main.submit_macro_evidence))
    fn = ast.parse(src).body[0]
    assert isinstance(fn, ast.AsyncFunctionDef) and fn.name == "submit_macro_evidence"
    return fn


def _answer_returns(fn):
    """The route's own returns in source order (a nested helper's returns are
    not the route's answer)."""
    out, todo = [], list(fn.body)
    while todo:
        node = todo.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(node, ast.Return):
            out.append(node)
        todo.extend(ast.iter_child_nodes(node))
    return sorted(out, key=lambda n: n.lineno)


def variant(answer_expr):
    """The shipped route with its one answer swapped for `answer_expr`;
    nothing else differs."""
    fn = _route_def()
    fn.decorator_list = []
    rets = _answer_returns(fn)
    assert len(rets) == 1, len(rets)
    rets[0].value = ast.parse(answer_expr, mode="eval").body
    ast.fix_missing_locations(fn)
    ns = dict(vars(main))
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "<macro evidence variant>", "exec"), ns)
    return ns["submit_macro_evidence"]


VARIANTS = {
    # the pre-fix shape: the flag-dependent attach on the request path, its
    # outcome in the answer
    "attach on the request path": lambda: variant(
        '{"status": await _macro_evidence_attach_once(db, evidence, True), '
        '"match_id": str(match.id)}'),
    "inert twin": lambda: variant("dict(_macro_evidence_answer(match.id))"),
}


# -- the rig ---------------------------------------------------------------------

class Rig:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.schema = "macro_flags_%s" % uuid.uuid4().hex[:10]
        self.match_id = uuid.uuid4()
        self.engine = self.conn = self.sessions = self.timed = None

    def run(self, coro):
        return self.loop.run_until_complete(coro)

    async def up(self):
        from sqlalchemy import text
        from sqlalchemy.dialects import postgresql
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.schema import CreateTable
        self.engine = create_async_engine(ASYNC_DSN)
        self.conn = await self.engine.connect()
        await self.conn.execute(text('CREATE SCHEMA "%s"' % self.schema))
        await self.conn.execute(text('SET search_path TO "%s"' % self.schema))
        dialect = postgresql.dialect()
        for table in TABLES:
            await self.conn.execute(text(str(
                CreateTable(table, include_foreign_key_constraints=[]).compile(dialect=dialect))))
        ids = {P1: uuid.uuid4(), P2: uuid.uuid4()}
        await self._insert("players", [
            dict(PLAYER_REQUIRED, id=ids[s], steam_id=s, display_name="Macro %s" % s[-1])
            for s in (P1, P2)])
        ended = dt.datetime.now(UTC) - dt.timedelta(minutes=55)
        await self._insert("matches", [dict(
            MATCH_REQUIRED, id=self.match_id, player1_id=ids[P1], player2_id=ids[P2],
            p1_rounds_won=P1_ROUNDS, p2_rounds_won=P2_ROUNDS, photon_room_id=ROOM,
            is_ranked=True, ended_at=ended, created_at=ended, duration_seconds=DURATION)])
        await self.conn.commit()
        self.sessions = create_async_engine(
            ASYNC_DSN, connect_args={"server_settings": {"search_path": self.schema}})
        # The held-row cases' request sessions: a lock wait ends in an error.
        self.timed = create_async_engine(
            ASYNC_DSN, connect_args={"server_settings": {
                "search_path": self.schema,
                "lock_timeout": "%dms" % int(LOCK_TIMEOUT_S * 1000)}})

    async def down(self):
        from sqlalchemy import text
        try:
            for eng in (self.sessions, self.timed):
                if eng is not None:
                    await eng.dispose()
            if self.conn is not None:
                await self.conn.rollback()
                await self.conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % self.schema))
                await self.conn.commit()
        finally:
            if self.conn is not None:
                await self.conn.close()
            if self.engine is not None:
                await self.engine.dispose()

    async def _insert(self, table, rows):
        from sqlalchemy import text
        names = sorted(rows[0])
        assert all(sorted(r) == names for r in rows), table
        vals = ", ".join("CAST(:%s AS jsonb)" % n if n == "flag_details" else ":%s" % n
                         for n in names)
        await self.conn.execute(text("INSERT INTO %s (%s) VALUES (%s)"
                                     % (table, ", ".join(names), vals)), rows)

    async def file_case(self, case):
        """No flag rows but the case's own; returns their ids."""
        from sqlalchemy import text
        await self.conn.rollback()
        await self.conn.execute(text("DELETE FROM flagged_matches"))
        t0 = dt.datetime.now(UTC) - dt.timedelta(minutes=50)
        rows = []
        for i, (key, subject, action) in enumerate(CASES[case]):
            rows.append(dict(
                FLAG_REQUIRED, id=uuid.uuid4(), match_id=self.match_id,
                player_steam_ids=[P1, P2], flag_reason="suspected_macro",
                flag_details=json.dumps({key: subject, "macro_suspect_seconds": 15,
                                         "evidence_source": "peer snapshot"}),
                created_at=t0 + dt.timedelta(seconds=i),
                reviewed_at=(t0 + dt.timedelta(minutes=5)) if action else None,
                review_action=action))
        if rows:
            await self._insert("flagged_matches", rows)
        await self.conn.commit()
        return [r["id"] for r in rows]

    async def post(self, fn, body, engine=None):
        """The route's public answer as (status code, body), the seconds it
        took, and the background tasks it scheduled (not yet run). A route
        without a background_tasks parameter (the pre-fix one) is called
        without it; an unhandled exception is the 500 the app would send."""
        from fastapi import BackgroundTasks, HTTPException
        from sqlalchemy.ext.asyncio import AsyncSession
        tasks = BackgroundTasks()
        kwargs = dict(request=None, payload=dict(body))
        if "background_tasks" in inspect.signature(fn).parameters:
            kwargs["background_tasks"] = tasks
        started = time.monotonic()
        # expire_on_commit=False as database.async_session (get_db) has it
        async with AsyncSession(engine or self.sessions, expire_on_commit=False) as db:
            try:
                got = (200, await fn(db=db, **kwargs))
            except HTTPException as ex:
                got = (ex.status_code, {"detail": ex.detail})
            except Exception as ex:
                got = (500, {"unhandled": type(ex).__name__})
        return got, time.monotonic() - started, tasks

    async def flag_rows(self):
        """Every flag row as {id: details}."""
        from sqlalchemy import text
        await self.conn.rollback()
        rows = (await self.conn.execute(text(
            "SELECT id, flag_details FROM flagged_matches"))).all()
        await self.conn.rollback()
        return {r[0]: r[1] for r in rows}

    async def recorded(self):
        """The reporter's suspected_macro rows on the match: how many, and
        whether the newest supersedes a reviewed flag."""
        from sqlalchemy import text
        await self.conn.rollback()
        rows = (await self.conn.execute(text(
            "SELECT flag_details FROM flagged_matches "
            " WHERE match_id = :m AND flag_reason = 'suspected_macro' "
            "   AND COALESCE(flag_details->>'suspect_steam', "
            "                flag_details->>'reporter_steam') = :s "
            " ORDER BY created_at"), {"m": self.match_id, "s": P1})).scalars().all()
        await self.conn.rollback()
        return len(rows), bool(rows) and "supersedes_reviewed_flag_id" in rows[-1]

    async def hold(self, flag_ids):
        """Another transaction holding these flag rows FOR UPDATE; returns
        the connection (roll it back to release)."""
        from sqlalchemy import text
        conn = await self.engine.connect()
        await conn.execute(text('SET search_path TO "%s"' % self.schema))
        got = (await conn.execute(text(
            "SELECT id FROM flagged_matches WHERE id = ANY(:ids) FOR UPDATE"),
            {"ids": list(flag_ids)})).all()
        assert len(got) == len(flag_ids), got
        return conn


@pytest.fixture(scope="module")
def seeded():
    _require_live_pg()
    r = Rig()
    try:
        r.run(r.up())
        yield r
    finally:
        try:
            r.run(r.down())
        finally:
            r.loop.close()


@pytest.fixture()
def rig(seeded, monkeypatch):
    async def _session_ok(request, steam_id, db):
        return None
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    monkeypatch.setattr(main, "_check_steam_session", _session_ok)
    # raising=False: the pre-fix main has no such name, and the red run
    # against it must fail on behaviour, not here
    monkeypatch.setattr(main, "_MACRO_ATTACH_DELAYS", (0.05, 0.05), raising=False)
    return seeded


def _answers(rig, fn):
    """Per case: the answers to the evidence POSTed twice (a first delivery,
    its background effect, then its retry and that one's effect), and what
    was recorded."""
    body = _payload()
    out = {}
    for case in CASES:
        rig.run(rig.file_case(case))
        first, _s, tasks = rig.run(rig.post(fn, body))
        rig.run(tasks())
        retry, _s, tasks = rig.run(rig.post(fn, body))
        rig.run(tasks())
        out[case] = (first, retry, rig.run(rig.recorded()))
    return out


EXPECTED_STATUS = 200


def _expected(rig):
    return (EXPECTED_STATUS, {"status": "recorded", "match_id": str(rig.match_id)})


# -- the route's shape -------------------------------------------------------------

def test_the_route_answers_through_one_helper_and_reads_no_flag_row():
    """One return, the answer helper; the route names no flag table, model or
    attach step except as the background task it schedules."""
    fn = _route_def()
    rets = _answer_returns(fn)
    assert len(rets) == 1, len(rets)
    r = rets[0].value
    assert (isinstance(r, ast.Call) and isinstance(r.func, ast.Name)
            and r.func.id == "_macro_evidence_answer"), ast.unparse(rets[0])
    sql = [n.value for n in ast.walk(fn) if isinstance(n, ast.Constant)
           and isinstance(n.value, str) and "flagged_matches" in n.value.lower()]
    doc = ast.get_docstring(fn) or ""
    assert [s for s in sql if s != doc] == [], sql
    names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
    assert not names & {"FlaggedMatch", "_macro_evidence_attach_once"}, names
    awaited = [ast.unparse(n.value) for n in ast.walk(fn) if isinstance(n, ast.Await)]
    assert not [a for a in awaited if "attach" in a], awaited
    adds = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and n.func.attr == "add_task"]
    assert len(adds) == 1 and ast.unparse(adds[0].args[0]) == "_macro_evidence_attach"


# -- every flag state, one answer ----------------------------------------------------

def test_every_flag_state_gets_the_same_answer(rig):
    got = _answers(rig, main.submit_macro_evidence)
    for case, (first, retry, _rec) in got.items():
        assert first == _expected(rig), (case, first)
        assert retry == _expected(rig), (case, retry)
    # ...while the flag state still decides what is recorded (by the
    # background task), so the cases did reach the merge, the supersede and
    # the new-row paths
    assert {case: rec for case, (_f, _r, rec) in got.items()} == RECORDED


# -- a held flag row: the Codex SMALL-ABC-R2 scenario ------------------------------

def _held_row_answers(rig, fn):
    """POST unflagged, then flagged with the caller's pending flag row held
    FOR UPDATE by another transaction, both on sessions with a lock_timeout.
    Returns the two answers and waits, the flag rows straight after each
    response (before any background task ran), and the held flag's id, with
    the hold still in place for the caller to release."""
    body = _payload()
    rig.run(rig.file_case("none"))
    unflagged, waited_u, tasks_u = rig.run(rig.post(fn, body, rig.timed))
    rows_after_unflagged = rig.run(rig.flag_rows())
    [pending] = rig.run(rig.file_case("pending"))
    holder = rig.run(rig.hold([pending]))
    flagged, waited_f, tasks_f = rig.run(rig.post(fn, body, rig.timed))
    rows_after_flagged = rig.run(rig.flag_rows())
    return dict(unflagged=unflagged, flagged=flagged, waited=(waited_u, waited_f),
                rows=(rows_after_unflagged, rows_after_flagged),
                tasks=(tasks_u, tasks_f), pending=pending, holder=holder)


def _release(rig, holder):
    rig.run(holder.rollback())
    rig.run(holder.close())


def test_a_held_flag_row_changes_neither_the_answer_nor_the_wait(rig):
    got = _held_row_answers(rig, main.submit_macro_evidence)
    try:
        assert got["flagged"] == got["unflagged"] == _expected(rig), (
            got["flagged"], got["unflagged"])
        # no request waited on the held row (the lock_timeout is 1 s)
        assert max(got["waited"]) < LOCK_TIMEOUT_S, got["waited"]
        # the responses came before any flag-dependent effect: nothing was
        # written for the unflagged POST, and the held pending row is untouched
        assert got["rows"][0] == {}, got["rows"][0]
        assert list(got["rows"][1]) == [got["pending"]]
        assert "evidence_fingerprint" not in got["rows"][1][got["pending"]]
    finally:
        _release(rig, got["holder"])


def test_the_background_effect_runs_after_the_response(rig):
    """The control that the move is not a deletion: once the row is free the
    flagged POST's background task merges the evidence into the caller's
    pending flag (the flag row updated after the response)."""
    got = _held_row_answers(rig, main.submit_macro_evidence)
    _release(rig, got["holder"])
    assert rig.run(got["tasks"][1]()) is None
    rows = rig.run(rig.flag_rows())
    assert list(rows) == [got["pending"]], rows
    merged = rows[got["pending"]]
    assert merged.get("evidence_fingerprint") and merged.get("suspect_steam") == P1, merged
    assert merged.get("macro_suspect_seconds") == 20, merged


def test_a_row_held_through_every_attempt_still_records_the_evidence(rig):
    """NOWAIT never queues: a row held through every attempt ends in the
    evidence recorded as its own new flag (marked with 55P03), the held row
    untouched."""
    got = _held_row_answers(rig, main.submit_macro_evidence)
    try:
        started = time.monotonic()
        rig.run(got["tasks"][1]())
        took = time.monotonic() - started
        rows = rig.run(rig.flag_rows())
    finally:
        _release(rig, got["holder"])
    assert took < LOCK_TIMEOUT_S, took
    new = [d for i, d in rows.items() if i != got["pending"]]
    assert len(new) == 1 and new[0].get("attach_lock_unavailable") is True, rows
    assert new[0].get("attach_fallback_sqlstate") == "55P03", new[0]
    assert "evidence_fingerprint" not in rows[got["pending"]]


# -- mutation controls ---------------------------------------------------------------

@pytest.mark.parametrize("name", list(VARIANTS))
def test_the_request_path_attach_turns_the_checks_red_and_the_inert_twin_does_not(rig, name):
    fn = VARIANTS[name]()
    got = _answers(rig, fn)
    answers = {(case, n): a for case, (f, r, _rec) in got.items()
               for n, a in (("first", f), ("retry", r))}
    distinct = {json.dumps(a, sort_keys=True) for a in answers.values()}
    assert {case: rec for case, (_f, _r, rec) in got.items()} == RECORDED, name
    held = _held_row_answers(rig, fn)
    _release(rig, held["holder"])
    if name == "inert twin":
        assert len(distinct) == 1, (name, distinct)
        assert held["flagged"] == held["unflagged"], held
        return
    assert len(distinct) > 1, (name, distinct)
    statuses = {case: a[1]["status"] for (case, n), a in answers.items() if n == "first"}
    assert statuses["pending"] == "evidence_upgraded", statuses
    # the request-path attach meets the held row: a refusal the unflagged
    # request never sees
    assert held["flagged"] != held["unflagged"], held


# -- the background attach: one row per fingerprint (R3 H2) ------------------------

def _function_variant(name, edit):
    """main.<name> compiled from its shipped source after `edit(fn_node)`;
    nothing else differs."""
    src = textwrap.dedent(inspect.getsource(getattr(main, name)))
    fn = ast.parse(src).body[0]
    fn.decorator_list = []
    edit(fn)
    ast.fix_missing_locations(fn)
    ns = dict(vars(main))
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "<%s variant>" % name, "exec"), ns)
    return ns[name]


def _lock_statements(fn):
    return [s for s in fn.body if isinstance(s, ast.Expr) and isinstance(s.value, ast.Await)
            and isinstance(s.value.value, ast.Call)
            and getattr(s.value.value.func, "id", None) == "_macro_evidence_merge_lock"]


def _without_the_lock(fn):
    [stmt] = _lock_statements(fn)
    fn.body[fn.body.index(stmt)] = ast.Pass()


def _lock_taken_twice(fn):
    [stmt] = _lock_statements(fn)
    i = fn.body.index(stmt)
    fn.body[i:i + 1] = [stmt, ast.parse(ast.unparse(stmt)).body[0]]


ATTACH_ONCE_VARIANTS = {
    "shipped": lambda: main._macro_evidence_attach_once,
    "without the merge lock": lambda: _function_variant(
        "_macro_evidence_attach_once", _without_the_lock),
    "inert twin (lock taken twice)": lambda: _function_variant(
        "_macro_evidence_attach_once", _lock_taken_twice),
}


def _evidence(rig):
    """The evidence dict the route hands its background task, captured from
    a real POST (the task itself is not run)."""
    rig.run(rig.file_case("none"))
    answer, _s, tasks = rig.run(rig.post(main.submit_macro_evidence, _payload()))
    assert answer == _expected(rig), answer
    [task] = tasks.tasks
    assert task.func is main._macro_evidence_attach
    return task.args[1]


async def _advisory_waiters(rig) -> int:
    """Sessions of the test database waiting for an advisory lock now."""
    from sqlalchemy import text as _text
    async with rig.sessions.connect() as c:
        return (await c.execute(_text(
            "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
            "AND NOT granted AND database = "
            "(SELECT oid FROM pg_database WHERE datname = current_database())"
        ))).scalar_one()


async def _two_attaches(rig, attach_once, ev, ev2=None, may_lock=False):
    """Attach #1 (of `ev`) takes the merge lock, finds nothing, inserts and
    then pauses AT its COMMIT; only then does attach #2 (of `ev2`, default
    the same evidence) start; #1 commits once #2 has finished or is seen
    waiting for an advisory lock (pg_locks, capped at 5 s). Event-gated, not
    sleep-timed, so #2's wait is never longer than #1's COMMIT however slow
    the seat is (a fixed-sleep version let a loaded run outlast the 2 s
    attempt lock_timeout). With may_lock False both are fallback attaches
    (every NOWAIT attempt exhausted, the Codex SMALL-ABC-R3 scenario); with
    True both are first attempts (R4: two fingerprints for one match).
    Returns both outcomes."""
    from sqlalchemy.ext.asyncio import AsyncSession
    gate = asyncio.Event()
    at_commit = asyncio.Event()

    class Paused(AsyncSession):
        async def commit(self):
            at_commit.set()
            await gate.wait()
            await super().commit()

    # the fallback's SQLSTATE argument only where the function takes one, so
    # the red run against the round-2 attach fails on rows, not on arity
    marker = ("55P03",) if (not may_lock and
                            len(inspect.signature(attach_once).parameters) > 3) else ()

    async def one(cls, evidence):
        async with cls(rig.sessions, expire_on_commit=False) as db:
            return await attach_once(db, evidence, may_lock, *marker)

    first = asyncio.ensure_future(one(Paused, ev))
    paused = asyncio.ensure_future(at_commit.wait())
    await asyncio.wait({first, paused}, timeout=30,
                       return_when=asyncio.FIRST_COMPLETED)
    paused.cancel()
    assert at_commit.is_set() and not first.done(), (
        first.result() if first.done() else "attach #1 never reached its COMMIT")
    second = asyncio.ensure_future(one(AsyncSession, ev2 or ev))
    for _ in range(100):
        if second.done() or await _advisory_waiters(rig):
            break
        await asyncio.sleep(0.05)
    gate.set()
    return await asyncio.gather(first, second)


@pytest.mark.parametrize("name", list(ATTACH_ONCE_VARIANTS))
def test_two_attaches_of_one_fingerprint_make_one_row(rig, name):
    ev = _evidence(rig)
    rig.run(rig.file_case("none"))
    outcomes = rig.run(_two_attaches(rig, ATTACH_ONCE_VARIANTS[name](), ev))
    rows = rig.run(rig.flag_rows())
    if name == "without the merge lock":
        assert len(rows) == 2 and sorted(outcomes) == ["recorded", "recorded"], (outcomes, rows)
        return
    assert sorted(outcomes) == ["already_recorded", "recorded"], outcomes
    assert len(rows) == 1, rows


def _second_fingerprint(ev):
    """The same match and reporter, different evidence: another fingerprint
    and a stronger suspect-seconds count."""
    other = ev["fingerprint"][::-1]
    assert other != ev["fingerprint"]
    return dict(ev, fingerprint=other,
                details=dict(ev["details"], evidence_fingerprint=other,
                             macro_suspect_seconds=25))


@pytest.mark.parametrize("name", list(ATTACH_ONCE_VARIANTS))
def test_two_fingerprints_for_one_match_merge_into_one_row(rig, name):
    """The Codex SMALL-ABC-R4 scenario: two first attempts with DIFFERENT
    fingerprints for one match and reporter. Under the (match, reporter)
    lock the second waits, then finds the first's unreviewed row and merges
    into it (the stronger count kept); without the lock both see no flag
    and insert."""
    ev = _evidence(rig)
    ev2 = _second_fingerprint(ev)
    rig.run(rig.file_case("none"))
    outcomes = rig.run(_two_attaches(rig, ATTACH_ONCE_VARIANTS[name](), ev, ev2, True))
    rows = list(rig.run(rig.flag_rows()).values())
    if name == "without the merge lock":
        assert len(rows) == 2 and sorted(outcomes) == ["recorded", "recorded"], (outcomes, rows)
        return
    assert sorted(outcomes) == ["evidence_upgraded", "recorded"], outcomes
    assert len(rows) == 1, rows
    assert rows[0]["evidence_fingerprint"] == ev2["fingerprint"], rows[0]
    assert rows[0]["macro_suspect_seconds"] == 25, rows[0]


def test_the_merge_lock_comes_before_every_read_and_write():
    """The lock is the attempt's first statement after its docstring, ahead
    of the dedupe read and the insert, on both the NOWAIT and the fallback
    path (one statement, no branch around it)."""
    src = textwrap.dedent(inspect.getsource(main._macro_evidence_attach_once))
    fn = ast.parse(src).body[0]
    body = [s for s in fn.body if not (isinstance(s, ast.Expr)
                                       and isinstance(s.value, ast.Constant))]
    [lock] = _lock_statements(fn)
    assert body.index(lock) == 1, [ast.unparse(s)[:60] for s in body[:3]]  # after `fingerprint = ...`
    first_read = min(n.lineno for n in ast.walk(fn) if isinstance(n, ast.Call)
                     and getattr(n.func, "id", None) == "attached_already")
    first_add = min(n.lineno for n in ast.walk(fn) if isinstance(n, ast.Call)
                    and getattr(n.func, "attr", None) == "add")
    assert lock.lineno < first_read < first_add


# -- the background attach: the retry ladder by SQLSTATE class (R3 H3) -------------

# The round-2 ladder, verbatim but for its name, with the single-code check it
# used: the mutant the class fix must beat.
OLD_LADDER = """
def _is_lock_not_available(ex) -> bool:
    seen, todo = set(), [ex]
    while todo:
        e = todo.pop()
        if e is None or id(e) in seen:
            continue
        seen.add(id(e))
        if (getattr(e, "sqlstate", None) == "55P03"
                or getattr(e, "pgcode", None) == "55P03"
                or type(e).__name__ == "LockNotAvailableError"):
            return True
        todo.extend((getattr(e, "orig", None), e.__cause__, e.__context__))
    return False


async def _macro_evidence_attach(session_factory, ev: dict) -> str:
    tag = str(ev.get("fingerprint", ""))[:12]
    attempts = len(_MACRO_ATTACH_DELAYS) + 1
    for attempt in range(attempts + 1):
        may_lock = attempt < attempts
        try:
            async with session_factory() as db:
                outcome = await _macro_evidence_attach_once(db, ev, may_lock)
            print(f"[MACRO-EVIDENCE] {tag} {outcome} (attempt {attempt + 1})")
            return outcome
        except Exception as ex:
            if not (may_lock and _is_lock_not_available(ex)):
                print(f"[MACRO-EVIDENCE] {tag} NOT RECORDED: {type(ex).__name__}: {ex}")
                return "failed"
        if attempt < len(_MACRO_ATTACH_DELAYS):
            await asyncio.sleep(_MACRO_ATTACH_DELAYS[attempt])
    return "failed"
"""


def _old_ladder():
    ns = dict(vars(main))
    exec(compile(OLD_LADDER, "<round-2 ladder>", "exec"), ns)
    return ns["_macro_evidence_attach"]


# The round-3 ladder (5e2cb737), verbatim but for its names: retried only an
# allow-list of SQLSTATEs, sent everything else to a fallback that was tried
# once. The mutant the inverted ladder must beat.
ROUND_3_LADDER = """
_R3_TRANSIENT_STATES = {"40P01", "40001", "55P03", "57014"}
_R3_TRANSIENT_CLASSES = {"08", "53"}


def _r3_is_transient(ex) -> bool:
    state = _attach_error_sqlstate(ex)
    if state is not None:
        return state in _R3_TRANSIENT_STATES or state[:2] in _R3_TRANSIENT_CLASSES
    return isinstance(ex, (ConnectionError, TimeoutError, OSError))


async def _macro_evidence_attach(session_factory, ev: dict) -> str:
    tag = str(ev.get("fingerprint", ""))[:12]
    last_state = None
    for attempt in range(len(_MACRO_ATTACH_DELAYS) + 1):
        try:
            async with session_factory() as db:
                outcome = await _macro_evidence_attach_once(db, ev, True)
            return outcome
        except Exception as ex:
            last_state = _attach_error_sqlstate(ex)
            if not _r3_is_transient(ex):
                break
        if attempt < len(_MACRO_ATTACH_DELAYS):
            await asyncio.sleep(_MACRO_ATTACH_DELAYS[attempt])
    try:
        async with session_factory() as db:
            outcome = await _macro_evidence_attach_once(db, ev, False, last_state)
        return outcome
    except Exception as ex:
        print(f"[MACRO-EVIDENCE] {tag} NOT RECORDED: {type(ex).__name__}: {ex}")
        return "failed"
"""


def _round_3_ladder():
    ns = dict(vars(main))
    exec(compile(ROUND_3_LADDER, "<round-3 ladder>", "exec"), ns)
    return ns["_macro_evidence_attach"]


class _Wrap(ast.NodeTransformer):
    def visit_Call(self, node):
        self.generic_visit(node)
        if getattr(node.func, "id", None) == "_attach_error_is_permanent":
            return ast.Call(func=ast.Name("bool", ast.Load()), args=[node], keywords=[])
        return node


def _ladder_inert_twin():
    return _function_variant("_macro_evidence_attach", lambda fn: _Wrap().visit(fn))


def _raising(nowait_n, make_error, calls, fallback_n=0, make_fallback_error=None):
    """main._macro_evidence_attach_once, except that its first `nowait_n`
    NOWAIT attempts raise make_error() and its first `fallback_n` fallback
    attempts raise make_fallback_error() (as the driver would)."""
    real = main._macro_evidence_attach_once

    async def wrapped(db, ev, may_lock, *rest):
        calls.append(may_lock)
        if may_lock and calls.count(True) <= nowait_n:
            raise make_error()
        if not may_lock and calls.count(False) <= fallback_n:
            raise make_fallback_error()
        return await real(db, ev, may_lock, *rest)
    return wrapped


def _deadlock():
    return asyncpg.exceptions.DeadlockDetectedError("deadlock detected")


def _undefined_column():
    return asyncpg.exceptions.UndefinedColumnError("column does not exist")


def _admin_shutdown():
    return asyncpg.exceptions.AdminShutdownError("terminating connection due to administrator command")


def _unique_violation():
    return asyncpg.exceptions.UniqueViolationError("duplicate key value")


def _connection_refused():
    import sqlalchemy.exc
    return sqlalchemy.exc.InterfaceError("connect", None, ConnectionRefusedError("connection refused"))


# case -> (failing NOWAIT attempts, their error, failing fallback attempts,
#          their error, NOWAIT attempts made, fallback attempts made,
#          (SQLSTATE, error name) on the fallback row or None for no fallback)
LADDER_CASES = {
    "deadlock once": (1, _deadlock, 0, None, 2, 0, None),
    "deadlock every attempt": (99, _deadlock, 0, None, 3, 1, ("40P01", "DeadlockDetectedError")),
    "42703 at once": (1, _undefined_column, 0, None, 1, 1, ("42703", "UndefinedColumnError")),
    "57P01 once": (1, _admin_shutdown, 0, None, 2, 0, None),
    "connection refused once": (1, _connection_refused, 0, None, 2, 0, None),
    "23505 at once": (1, _unique_violation, 0, None, 1, 1, ("23505", "UniqueViolationError")),
    "fallback retried": (99, _admin_shutdown, 1, _connection_refused, 3, 2,
                         ("57P01", "AdminShutdownError")),
}
# the 3 = the fixture's two delays + 1


def _run_ladder(rig, monkeypatch, case, attach):
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    nowait_n, err, fallback_n, fallback_err = LADDER_CASES[case][:4]
    ev = _evidence(rig)
    rig.run(rig.file_case("none"))
    calls = []
    monkeypatch.setattr(main, "_macro_evidence_attach_once",
                        _raising(nowait_n, err, calls, fallback_n, fallback_err))
    factory = async_sessionmaker(rig.sessions, class_=AsyncSession, expire_on_commit=False)
    outcome = rig.run(attach()(factory, ev))
    return ev, outcome, calls, list(rig.run(rig.flag_rows()).values())


@pytest.mark.parametrize("ladder", ["shipped", "inert twin"])
@pytest.mark.parametrize("case", list(LADDER_CASES))
def test_the_ladder_retries_every_database_error_but_a_permanent_one(
        rig, monkeypatch, case, ladder):
    attach = (lambda: main._macro_evidence_attach) if ladder == "shipped" else _ladder_inert_twin
    ev, outcome, calls, rows = _run_ladder(rig, monkeypatch, case, attach)
    *_, nowait_made, fallback_made, fallback = LADDER_CASES[case]
    assert outcome == "recorded", (case, outcome, calls)
    assert (calls.count(True), calls.count(False)) == (nowait_made, fallback_made), (case, calls)
    assert len(rows) == 1 and rows[0].get("evidence_fingerprint") == ev["fingerprint"], rows
    if fallback is None:
        assert "attach_fallback_sqlstate" not in rows[0], rows[0]
    else:
        got = (rows[0].get("attach_fallback_sqlstate"), rows[0].get("attach_fallback_error"))
        assert got == fallback, (case, got)
    assert ("attach_lock_unavailable" in rows[0]) is False, rows[0]


@pytest.mark.parametrize("case", list(LADDER_CASES))
def test_the_round_2_single_code_ladder_loses_the_evidence(rig, monkeypatch, case):
    _ev, outcome, calls, rows = _run_ladder(rig, monkeypatch, case, _old_ladder)
    assert outcome == "failed" and rows == [], (case, outcome, rows)


@pytest.mark.parametrize("case", ["57P01 once", "connection refused once", "fallback retried"])
def test_the_round_3_allow_list_ladder_misfiles_or_loses_a_failover(rig, monkeypatch, case):
    """The R4 HIGH: a failover's errors skipped the delays and went to a
    fallback tried once."""
    ev, outcome, calls, rows = _run_ladder(rig, monkeypatch, case, _round_3_ladder)
    if case == "fallback retried":
        assert outcome == "failed" and rows == [], (outcome, rows)
    else:
        # no retry: one NOWAIT attempt, straight into the fallback
        assert calls == [True, False], calls
        assert len(rows) == 1 and "attach_fallback_sqlstate" in rows[0], rows


def test_the_permanent_classes_are_the_documented_ones():
    import sqlalchemy.exc
    for state in ("22P02", "23505", "23503", "42703", "42P01"):
        err = type("E", (Exception,), {"sqlstate": state})()
        assert main._attach_error_is_permanent(err), state
    for state in ("40P01", "40001", "55P03", "57014", "57P01", "57P03", "25006",
                  "08006", "53300", "XX000"):
        err = type("E", (Exception,), {"sqlstate": state})()
        assert not main._attach_error_is_permanent(err), state
    assert not main._attach_error_is_permanent(_connection_refused())
    assert not main._attach_error_is_permanent(ConnectionResetError())
    assert not main._attach_error_is_permanent(
        sqlalchemy.exc.OperationalError("select 1", None, Exception("server closed")))
    # a programming error on our side is permanent
    assert main._attach_error_is_permanent(KeyError("match_id"))
    assert main._attach_error_is_permanent(TypeError("bad call"))
