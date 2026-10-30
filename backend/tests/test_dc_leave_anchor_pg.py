"""The disconnect report's leave anchor (migration 391), executed.

POST /api/v1/report-disconnect inserts one dc_events row per (series, leaver).
created_at is when the report was ACCEPTED, which the client's outbox can put
long after the leave; leave_anchor_at carries the leave by the rule the hold
logic anchors a dropped seat on, the last server evidence of that seat's
presence. In 1v1 that evidence is the LEAVER's own verified live-points stamp
in the series (series_progress, surface 'ranked'), else the series' last
recorded activity (ranked_series.last_activity_at), else nothing.

The statement executed here is the handler's own: the one `text()` call in
main._report_disconnect_once whose SQL starts "INSERT INTO dc_events", read
out of the function's source by the AST, so this module runs the shipped
statement and not a copy of it. It is bound the way the route binds it,
through SQLAlchemy and asyncpg. The tables: dc_events from migration 101's
own file with migration 391's own file applied over it, and series_progress
and ranked_series with the columns the statement reads (migrations 295 and
215), no foreign keys. The wiring (the route issues this insert with these
binds) is test_report_disconnect_durability.py's.

Cases, each in a throwaway schema:
  verified   the leaver's 'ranked' stamp is the anchor; the reporter's later
             stamp and the leaver's stamp on another surface are not
  fallback   no leaver stamp: the series' last activity is the anchor
  replay     a second insert after both stamps moved loses the conflict and
             moves nothing
  neither    no stamp at all: the row is still inserted, the anchor NULL

Mutation controls (#391): each mutant of the shipped text must turn at least
one case red, and an inert twin of the first mutant's site must keep them all
green.

DC_ANCHOR_TEST_PG_DSN names a throwaway database (postgresql:// or the
postgresql+asyncpg:// form); unset, the module FAILS rather than skips (#342),
and DC_ANCHOR_TEST_PG_OPTOUT=1 makes that a named skip.
"""

import ast
import asyncio
import datetime as dt
import inspect
import os
import re
import sys
import textwrap
import uuid
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "api"))

import main  # noqa: E402

try:
    import asyncpg
except ImportError:                                    # pragma: no cover
    asyncpg = None

SQL_DIR = HERE.parent / "sql"
DSN_VAR = "DC_ANCHOR_TEST_PG_DSN"
OPTOUT_VAR = "DC_ANCHOR_TEST_PG_OPTOUT"
_RAW = os.environ.get(DSN_VAR) or ""
PLAIN_DSN = _RAW.replace("postgresql+asyncpg://", "postgresql://")
ASYNC_DSN = PLAIN_DSN.replace("postgresql://", "postgresql+asyncpg://", 1)
OPTOUT = str(os.environ.get(OPTOUT_VAR) or "").strip().lower() in {"1", "true", "yes", "on"}

UTC = dt.timezone.utc
T_SERIES = dt.datetime(2026, 10, 1, 12, 0, 0, tzinfo=UTC)
T_LEAVER = T_SERIES + dt.timedelta(seconds=40)
T_REPORTER = T_SERIES + dt.timedelta(seconds=95)
T_OTHER_SURFACE = T_SERIES + dt.timedelta(seconds=300)
T_MOVED = T_SERIES + dt.timedelta(seconds=600)

_DDL = """
    CREATE TABLE ranked_series (
        id                UUID PRIMARY KEY,
        created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
        last_activity_at  TIMESTAMPTZ);
    CREATE TABLE series_progress (
        surface         TEXT        NOT NULL,
        subject_id      UUID        NOT NULL,
        player_id       UUID        NOT NULL,
        first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
        last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
        observed_points INTEGER     NOT NULL DEFAULT 0,
        CONSTRAINT pk_series_progress PRIMARY KEY (surface, subject_id, player_id));
"""


@pytest.fixture(autouse=True)
def _require_live_pg():
    if PLAIN_DSN and asyncpg is not None:
        return
    if OPTOUT:
        pytest.skip("%s is unset and %s=1: the leave anchor was deliberately not "
                    "executed against PostgreSQL" % (DSN_VAR, OPTOUT_VAR))
    pytest.fail("%s is unset (or asyncpg is missing), so the dc_events insert was "
                "never executed; point it at a throwaway database, or set %s=1 to "
                "waive the coverage deliberately" % (DSN_VAR, OPTOUT_VAR))


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def shipped_insert() -> str:
    """The handler's dc_events INSERT, exactly as it is written."""
    src = textwrap.dedent(inspect.getsource(main._report_disconnect_once))
    found = [n.args[0].value for n in ast.walk(ast.parse(src))
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "text" and n.args
             and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)
             and n.args[0].value.startswith("INSERT INTO dc_events")]
    assert len(found) == 1, "expected one dc_events INSERT in the handler, found %d" % len(found)
    return found[0]


def _mutate(sql: str, old: str, new: str) -> str:
    assert sql.count(old) == 1, "the mutation site %r is not unique in the shipped insert" % old
    return sql.replace(old, new)


async def _case(stmt: str, case: str) -> dict:
    """Seed one case in a fresh schema, execute `stmt` the way the route
    binds it, and return what the table then holds."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    schema = "dcanchor_%s" % uuid.uuid4().hex[:10]
    sid, leaver, reporter = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    raw = await asyncpg.connect(PLAIN_DSN)
    engine = create_async_engine(ASYNC_DSN)
    try:
        await raw.execute('CREATE SCHEMA "%s"' % schema)
        await raw.execute('SET search_path TO "%s"' % schema)
        await raw.execute((SQL_DIR / "101_dc_events_dedup.sql").read_text(encoding="utf-8"))
        await raw.execute((SQL_DIR / "391_dc_events_leave_anchor.sql").read_text(encoding="utf-8"))
        await raw.execute(_DDL)
        await raw.execute("INSERT INTO ranked_series (id, last_activity_at) VALUES ($1, $2)",
                          sid, None if case == "neither" else T_SERIES)
        if case in ("verified", "replay"):
            await raw.execute(
                "INSERT INTO series_progress (surface, subject_id, player_id, last_seen_at)"
                " VALUES ('ranked', $1, $2, $3)", sid, leaver, T_LEAVER)
            await raw.execute(
                "INSERT INTO series_progress (surface, subject_id, player_id, last_seen_at)"
                " VALUES ('team', $1, $2, $3)", sid, leaver, T_OTHER_SURFACE)
        if case != "neither":
            await raw.execute(
                "INSERT INTO series_progress (surface, subject_id, player_id, last_seen_at)"
                " VALUES ('ranked', $1, $2, $3)", sid, reporter, T_REPORTER)

        binds = {"sid": sid, "dp": leaver, "rp": reporter}
        returned = []
        async with engine.connect() as conn:
            await conn.exec_driver_sql('SET search_path TO "%s"' % schema)
            returned.append((await conn.execute(text(stmt), binds)).first() is not None)
            await conn.commit()
            if case == "replay":
                await raw.execute("UPDATE series_progress SET last_seen_at = $1", T_MOVED)
                await raw.execute("UPDATE ranked_series SET last_activity_at = $1", T_MOVED)
                returned.append((await conn.execute(text(stmt), binds)).first() is not None)
                await conn.commit()
        rows = await raw.fetch(
            "SELECT series_id, disconnected_player_id, reporter_player_id, leave_anchor_at"
            "  FROM dc_events")
        return {"returned": returned, "rows": [dict(r) for r in rows],
                "sid": sid, "leaver": leaver, "reporter": reporter}
    finally:
        try:
            await raw.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % schema)
        finally:
            await raw.close()
            await engine.dispose()


EXPECTED = {"verified": T_LEAVER, "fallback": T_SERIES, "replay": T_LEAVER, "neither": None}


def _failures(case: str, got: dict) -> list:
    out = []
    rows = got["rows"]
    if len(rows) != 1:
        return ["%s: %d dc_events rows, expected 1" % (case, len(rows))]
    row = rows[0]
    if (row["series_id"], row["disconnected_player_id"], row["reporter_player_id"]) != (
            got["sid"], got["leaver"], got["reporter"]):
        out.append("%s: the row names the wrong series or players" % case)
    if row["leave_anchor_at"] != EXPECTED[case]:
        out.append("%s: leave_anchor_at %r, expected %r" % (case, row["leave_anchor_at"], EXPECTED[case]))
    want_returned = [True, False] if case == "replay" else [True]
    if got["returned"] != want_returned:
        out.append("%s: RETURNING answered %r, expected %r" % (case, got["returned"], want_returned))
    return out


def _all_failures(stmt: str) -> list:
    """Every case's failures; a statement that raises fails that case (a
    mutant can break the statement rather than change its value)."""
    out = []
    for case in EXPECTED:
        try:
            got = _run(_case(stmt, case))
        except Exception as ex:
            out.append("%s: raised %s: %s" % (case, type(ex).__name__, str(ex)[:120]))
            continue
        out.extend(_failures(case, got))
    return out


def test_the_shipped_insert_binds_only_what_the_route_binds():
    names = set(re.findall(r"(?<!:):([a-z_]+)", shipped_insert()))
    assert names == {"sid", "dp", "rp"}, names


@pytest.mark.parametrize("case", sorted(EXPECTED))
def test_the_shipped_insert_writes_the_leave_anchor(case):
    got = _run(_case(shipped_insert(), case))
    assert not _failures(case, got), _failures(case, got)


MUTANTS = {
    # the anchor read from the REPORTER's presence instead of the leaver's
    "reporter-presence": ("sp.player_id = CAST(:dp AS uuid)", "sp.player_id = CAST(:rp AS uuid)"),
    # the leaver's own stamp ignored: the series' activity always wins
    "series-activity-only": ("sp.surface = 'ranked'", "sp.surface = 'none'"),
    # any surface's stamp accepted
    "any-surface": ("sp.surface = 'ranked'", "sp.surface IS NOT NULL"),
    # a replay re-stamps the anchor
    "replay-moves": ("ON CONFLICT DO NOTHING",
                     "ON CONFLICT (series_id, disconnected_player_id)"
                     " DO UPDATE SET leave_anchor_at = EXCLUDED.leave_anchor_at"),
    # the acceptance time written as the leave
    "acceptance-time": ("COALESCE((SELECT", "COALESCE(now(), (SELECT"),
}


@pytest.mark.parametrize("name", sorted(MUTANTS))
def test_each_mutant_turns_a_case_red(name):
    old, new = MUTANTS[name]
    mutant = _mutate(shipped_insert(), old, new)
    assert _all_failures(mutant), "mutant %r passed every case: the cases cannot see it" % name


def test_the_inert_twin_of_a_mutation_site_stays_green():
    old = "sp.player_id = CAST(:dp AS uuid)"
    twin = _mutate(shipped_insert(), old, old + " AND TRUE")
    assert not _all_failures(twin), _all_failures(twin)
