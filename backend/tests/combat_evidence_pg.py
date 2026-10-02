"""Live PostgreSQL for the combat-evidence lane (combat contract one, migration 369).

The seat-evidence build (seat_evidence_pg.build: cf_pg's replay, the ORM's
own tables, widen, replay again, 331 and 355 whole, 368 whole twice) with
369 held out of both replays as well, so 369 runs WHOLE as its first apply
on a schema that has never held its tables. It then runs whole a SECOND
time (the re-run rule), is ROLLED BACK (its tables and switches gone, no
other row moved), and is applied a THIRD time from that state, before the
schema is sealed and any case work starts.

The DSN is seat-evidence's (SEAT_EVIDENCE_TEST_PG_DSN), with its opt-out:
the combat lane is a reader of the same throwaway database.
"""

import contextlib
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

import cf_pg  # noqa: E402
import ladder_pg_harness as harness  # noqa: E402
import seat_evidence_pg as sp  # noqa: E402

M369_NAME = "369_combat_evidence.sql"
M369 = os.path.join(cf_pg.SQL_DIR, M369_NAME)
R369 = os.path.join(cf_pg.SQL_DIR, "rollback_369_combat_evidence.sql")
CEV_TABLES = ("combat_contrib", "combat_evidence", "combat_games", "combat_player_daily")
CEV_SWITCHES = ("combat_evidence_accept", "combat_evidence_purge", "combat_evidence_worker")

require_live_pg = sp.require_live_pg


def read_369():
    return io.open(M369, encoding="utf-8").read()


def read_rollback():
    return io.open(R369, encoding="utf-8").read()


async def present(conn):
    return await conn.fetchval(
        "SELECT count(*) FROM pg_tables WHERE schemaname = current_schema() "
        "AND tablename = ANY($1::text[])", list(CEV_TABLES))


async def snapshot(conn):
    """Every row and object 369 can write, as text, for the run comparisons.
    Tables 369 has not made (yet, or any more) read as None."""
    out = {"runtime_settings": await conn.fetch(
        "SELECT key, value, updated_at::text FROM runtime_settings ORDER BY key")}
    have = {r["tablename"] for r in await conn.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname = current_schema()")}
    for t in CEV_TABLES:
        out[t] = await conn.fetch("SELECT * FROM %s ORDER BY 1" % t) if t in have else None
    out["findings"] = await conn.fetch(
        "SELECT id, dedup_key FROM seat_evidence_findings ORDER BY id")
    out["constraints"] = await conn.fetch(
        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE connamespace = current_schema()::regnamespace ORDER BY conname")
    out["indexes"] = await conn.fetch(
        "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = current_schema() "
        "ORDER BY indexname")
    return {k: (None if v is None else [tuple(r) for r in v]) for k, v in out.items()}


async def build(case, dsn):
    """The seat-evidence build with 369 held out, then 369 whole twice, the
    rollback, and 369 whole once more. Returns the four snapshots
    (before 369, first apply, second apply, after rollback, third apply)."""
    saved = cf_pg.HELD_OUT
    cf_pg.HELD_OUT = frozenset(saved | {M369_NAME})
    try:
        await sp.build(case, dsn)
    finally:
        cf_pg.HELD_OUT = saved
    conn = case.conn
    assert await present(conn) == 0, "a combat-evidence table existed before 369's first apply"
    before = await snapshot(conn)
    await conn.execute(read_369())
    first = await snapshot(conn)
    await conn.execute(read_369())
    again = await snapshot(conn)
    await conn.execute(read_rollback())
    rolled = await snapshot(conn)
    await conn.execute(read_369())
    third = await snapshot(conn)
    return {"before": before, "first": first, "again": again, "rolled": rolled, "third": third}


@contextlib.asynccontextmanager
async def case(prefix="cev"):
    """A built, sealed case schema; yields (case, sessionmaker, snapshots)."""
    async with harness.CaseSchema(sp.DSN, prefix) as c:
        snaps = await build(c, sp.DSN)
        await c.seal()
        engine = harness.bound_engine(sp.DSN, c.schema)
        try:
            yield c, async_sessionmaker(engine, expire_on_commit=False), snaps
        finally:
            await engine.dispose()
