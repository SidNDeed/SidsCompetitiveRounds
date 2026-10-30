"""POST /api/v1/matches/macro-evidence answers the same whatever flag rows
the caller has (the Codex SMALL-ABC-R1 HIGH on the small docket's item c).

Required behaviour: for a valid POST the response status and body are
identical whatever the caller's flag state on that match -- none, pending,
confirmed, dismissed, pending under the legacy reporter_steam key, or a flag
naming the opponent -- and on a retry of the same evidence. The flag state may
change only what is written to flagged_matches (and so what the admin surfaces
show). The route used to answer `evidence_upgraded` when it merged into an
unreviewed flag, `recorded` when it opened a new one and `already_recorded` on
a retry, each with the flag row's id.

Live PostgreSQL. players, matches and flagged_matches are built from the
models (columns and types, no foreign keys) in one throwaway schema for the
module; one match between two synthetic players is seeded once; every case
starts with no flag row, files its own, and POSTs the same signed evidence
twice through the route function itself (main.submit_macro_evidence) on a
session whose search_path is that schema. The signature is the real HMAC
over the route's canonical under a test secret; the Steam session check, which
runs before any flag read and reads none, is replaced by a no-op.

Mutation controls (#391): the shipped function with the old answers put back
(compiled from the shipped source, only the answer expressions replaced) must
turn the check red, and an inert twin of the same edit must keep it green.

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
# What each case must still RECORD differently: the reporter's suspected_macro
# rows on the match after the POST, and whether the newest one supersedes a
# reviewed flag. A pending flag is merged into; a reviewed one is kept and a
# new row supersedes it; otherwise a new row is opened.
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


# -- the variants ---------------------------------------------------------------

# The answers the route gave before the fix, in source order of its four
# returns: the two lost-response retries, the merge into a pending flag, and
# the new flag.
OLD_ANSWERS = (
    '{"status": "already_recorded", "match_id": str(prior_attach["match_id"]), '
    '"flag_id": str(prior_attach["id"])}',
    '{"status": "already_recorded", "match_id": str(prior_attach["match_id"]), '
    '"flag_id": str(prior_attach["id"])}',
    '{"status": "evidence_upgraded", "match_id": str(match.id), "flag_id": str(flag.id)}',
    '{"status": "recorded", "match_id": str(match.id), "flag_id": str(flag.id)}',
)


def _route_def():
    src = textwrap.dedent(inspect.getsource(main.submit_macro_evidence))
    fn = ast.parse(src).body[0]
    assert isinstance(fn, ast.AsyncFunctionDef) and fn.name == "submit_macro_evidence"
    return fn


def _answer_returns(fn):
    """The route's own returns in source order (a nested helper's returns,
    such as the merge's _keep_stronger, are not the route's answer)."""
    out, todo = [], list(fn.body)
    while todo:
        node = todo.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(node, ast.Return):
            out.append(node)
        todo.extend(ast.iter_child_nodes(node))
    return sorted(out, key=lambda n: n.lineno)


def variant(replace):
    """The shipped route with the answer of each return index in `replace`
    swapped for the given expression text; nothing else differs."""
    fn = _route_def()
    fn.decorator_list = []
    rets = _answer_returns(fn)
    for i, expr in replace.items():
        rets[i].value = ast.parse(expr, mode="eval").body
    ast.fix_missing_locations(fn)
    ns = dict(vars(main))
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "<macro evidence variant>", "exec"), ns)
    return ns["submit_macro_evidence"]


VARIANTS = {
    "old merge answer": lambda: variant({2: OLD_ANSWERS[2]}),
    "every old answer": lambda: variant(dict(enumerate(OLD_ANSWERS))),
    "inert twin": lambda: variant({2: "dict(_macro_evidence_answer(match.id))"}),
}


# -- the rig ---------------------------------------------------------------------

class Rig:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.schema = "macro_flags_%s" % uuid.uuid4().hex[:10]
        self.match_id = uuid.uuid4()
        self.engine = self.conn = self.sessions = None

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

    async def down(self):
        from sqlalchemy import text
        try:
            if self.sessions is not None:
                await self.sessions.dispose()
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

    async def post(self, fn, body):
        """The route's public answer as (status code, body)."""
        from fastapi import HTTPException
        from sqlalchemy.ext.asyncio import AsyncSession
        # expire_on_commit=False as database.async_session (get_db) has it
        async with AsyncSession(self.sessions, expire_on_commit=False) as db:
            try:
                got = await fn(request=None, payload=dict(body), db=db)
            except HTTPException as ex:
                return (ex.status_code, {"detail": ex.detail})
        return (200, got)

    async def recorded(self):
        """The reporter's suspected_macro rows on the match after the POSTs:
        how many, and whether the newest supersedes a reviewed flag."""
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
    return seeded


def _answers(rig, fn):
    """Per case: the answers to the evidence POSTed twice (a first delivery
    and its retry), and what was recorded."""
    body = _payload()
    out = {}
    for case in CASES:
        rig.run(rig.file_case(case))
        first = rig.run(rig.post(fn, body))
        retry = rig.run(rig.post(fn, body))
        out[case] = (first, retry, rig.run(rig.recorded()))
    return out


def test_the_route_answers_through_one_helper():
    """Every return of the route is the one answer helper, so a new branch
    cannot grow its own answer without this failing."""
    rets = _answer_returns(_route_def())
    assert len(rets) == 4, len(rets)
    for r in rets:
        assert (isinstance(r.value, ast.Call) and isinstance(r.value.func, ast.Name)
                and r.value.func.id == "_macro_evidence_answer"), ast.unparse(r)


def test_every_flag_state_gets_the_same_answer(rig):
    got = _answers(rig, main.submit_macro_evidence)
    expected = (200, {"status": "recorded", "match_id": str(rig.match_id)})
    for case, (first, retry, _rec) in got.items():
        assert first == expected, (case, first)
        assert retry == expected, (case, retry)
    # ...while the flag state still decides what is recorded, so the cases
    # did reach the merge, the supersede and the new-row paths
    assert {case: rec for case, (_f, _r, rec) in got.items()} == RECORDED


@pytest.mark.parametrize("name", list(VARIANTS))
def test_the_old_answers_turn_the_check_red_and_the_inert_twin_does_not(rig, name):
    got = _answers(rig, VARIANTS[name]())
    answers = {(case, n): a for case, (f, r, _rec) in got.items()
               for n, a in (("first", f), ("retry", r))}
    distinct = {json.dumps(a, sort_keys=True) for a in answers.values()}
    assert {case: rec for case, (_f, _r, rec) in got.items()} == RECORDED, name
    if name == "inert twin":
        assert len(distinct) == 1, (name, distinct)
        return
    assert len(distinct) > 1, (name, distinct)
    # the old merge answer alone names the pending flag state
    statuses = {case: a[1]["status"] for (case, n), a in answers.items() if n == "first"}
    assert statuses["pending"] == "evidence_upgraded", statuses
    assert statuses["legacy key"] == "evidence_upgraded", statuses
    assert statuses["none"] in {"recorded", "already_recorded"}, statuses
