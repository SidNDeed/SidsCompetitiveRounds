"""Live PostgreSQL for the seat-evidence lane (contract V2, migration 368).

One case schema per case, built the way the connect-failure lane builds its
own (cf_pg.build, step for step: replay every numbered migration's DDL, the
ORM makes the tables no migration makes, widen, replay again, 331 and 355
whole), with two differences, both on purpose:

  - 368_seat_evidence.sql is held out of both replays, and the ORM does NOT
    create its nine tables, so 368 runs WHOLE, as its first apply, on a schema
    that has never held them -- and then runs whole a SECOND time (the
    re-run rule) before any case work;
  - the schema is sealed after both applies, so the census proves that
    nothing the build or 368 ran reached outside it.

SEAT_EVIDENCE_TEST_PG_DSN names the lane database (postgresql+asyncpg://...);
SEAT_EVIDENCE_TEST_PG_OPTOUT=1 waives the live cases deliberately. Unset and
not waived, every live case FAILS: a skipped live case reports exit 0 for
coverage that did not run.
"""

import contextlib
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import pytest  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

import cf_pg  # noqa: E402
import ladder_pg_harness as harness  # noqa: E402
import models  # noqa: E402
import test_title_ladder_hooks_live as lh  # noqa: E402

try:
    import asyncpg as _asyncpg
except ImportError:                                    # pragma: no cover
    _asyncpg = None

DSN_VAR = "SEAT_EVIDENCE_TEST_PG_DSN"
OPTOUT_VAR = "SEAT_EVIDENCE_TEST_PG_OPTOUT"
DSN = (os.environ.get(DSN_VAR) or "").replace("postgresql+asyncpg://", "postgresql://")
OPTOUT = os.environ.get(OPTOUT_VAR) == "1"

M368_NAME = "368_seat_evidence.sql"
M368 = os.path.join(cf_pg.SQL_DIR, M368_NAME)
M370_NAME = "370_card_evidence.sql"
SEV_TABLES = frozenset({"seat_evidence", "seat_evidence_games", "seat_evidence_findings",
                        "mod_release_digests", "client_compat_events",
                        "review_sitting_dirty", "review_cursor", "review_seen",
                        "seat_evidence_seeded_keys"})


def require_live_pg():
    """Fail, not skip (module docstring)."""
    if DSN and _asyncpg is not None:
        return
    if OPTOUT:
        pytest.skip("%s is unset and %s=1: the seat-evidence live coverage is "
                    "deliberately waived." % (DSN_VAR, OPTOUT_VAR))
    if _asyncpg is None:
        pytest.fail("asyncpg is not installed, so no seat-evidence case ran against "
                    "a real server. Install it, or set %s=1." % OPTOUT_VAR)
    pytest.fail("%s is unset, so no seat-evidence case ran against migration 368. "
                "Point it at a throwaway database, or set %s=1 to waive the "
                "coverage deliberately." % (DSN_VAR, OPTOUT_VAR))


def read_368():
    return io.open(M368, encoding="utf-8").read()


def ddl_statements():
    """cf_pg's replay set with 368 held out as well, and 370 with it: 370
    changes 368's findings table (its evidence domain), so it cannot replay
    before 368 has run. The card evidence build applies 370 itself, after."""
    saved = cf_pg.HELD_OUT
    cf_pg.HELD_OUT = frozenset(saved | {M368_NAME, M370_NAME})
    try:
        return cf_pg.ddl_statements()
    finally:
        cf_pg.HELD_OUT = saved


async def snapshot(conn):
    """Every row 368 can write, as text, for the second-run comparison."""
    out = {}
    out["runtime_settings"] = await conn.fetch(
        "SELECT key, value, updated_at::text FROM runtime_settings ORDER BY key")
    for t in sorted(SEV_TABLES):
        out[t] = await conn.fetch("SELECT * FROM %s ORDER BY 1" % t)
    out["seat_evidence_seeded_keys"] = await conn.fetch(
        "SELECT key FROM seat_evidence_seeded_keys ORDER BY key")
    out["constraints"] = await conn.fetch(
        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE connamespace = current_schema()::regnamespace ORDER BY conname")
    out["indexes"] = await conn.fetch(
        "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = current_schema() "
        "ORDER BY indexname")
    return {k: [tuple(r) for r in v] for k, v in out.items()}


async def _widen(conn, schema):
    """lh._widen over every mapped table EXCEPT 368's (which do not exist yet:
    368 makes them, and widening would have to create them first)."""
    from sqlalchemy.dialects import postgresql
    dialect = postgresql.dialect()
    for table in models.Base.metadata.sorted_tables:
        if table.name in SEV_TABLES:
            continue
        have = {r["column_name"] for r in await conn.fetch(
            "SELECT column_name FROM information_schema.columns "
            " WHERE table_schema = $1 AND table_name = $2", schema, table.name)}
        for col in table.columns:
            if col.name not in have:
                await conn.execute('ALTER TABLE %s."%s" ADD COLUMN "%s" %s' % (
                    harness.quoted(schema), table.name, col.name,
                    col.type.compile(dialect=dialect)))


async def build(case, dsn):
    """Into case.schema: the cf_pg build without 368 and without its tables,
    then 368 whole, twice. Returns (snapshot after the first apply, after the
    second)."""
    conn, schema = case.conn, case.schema
    statements = ddl_statements()
    await lh._replay(conn, statements)
    engine = harness.bound_engine(dsn, schema)
    tables = [t for name, t in models.Base.metadata.tables.items() if name not in SEV_TABLES]
    try:
        async with engine.begin() as c:
            await c.run_sync(lambda sc: models.Base.metadata.create_all(sc, tables=tables))
    finally:
        await engine.dispose()
    await _widen(conn, schema)
    second = await lh._replay(conn, statements)
    unexpected = [f for f in second
                  if f[1] not in lh._ALREADY and (f[0], f[1]) not in lh.REPLAY_KNOWN]
    assert not unexpected, unexpected[:5]
    await conn.execute(io.open(cf_pg.M331, encoding="utf-8").read())
    await cf_pg.apply_355(conn)
    present = await conn.fetchval(
        "SELECT count(*) FROM pg_tables WHERE schemaname = current_schema() "
        "AND tablename = ANY($1::text[])", sorted(SEV_TABLES))
    assert present == 0, "a seat-evidence table existed before 368's first apply"
    await conn.execute(read_368())
    first = await snapshot(conn)
    await conn.execute(read_368())
    again = await snapshot(conn)
    return first, again


@contextlib.asynccontextmanager
async def case(prefix="sev"):
    """A built, sealed case schema; yields (case, sessionmaker, (first, again))."""
    async with harness.CaseSchema(DSN, prefix) as c:
        snaps = await build(c, DSN)
        await c.seal()
        engine = harness.bound_engine(DSN, c.schema)
        try:
            yield c, async_sessionmaker(engine, expire_on_commit=False), snaps
        finally:
            await engine.dispose()
