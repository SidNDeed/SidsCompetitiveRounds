"""Live PostgreSQL for the card draw evidence lane (migration 370).

The seat-evidence build (seat_evidence_pg.build: every numbered migration's
DDL replayed, the ORM's own tables, 368 whole twice) with 370 held out of the
replay as well, so 370 then runs WHOLE, as its first apply, on a schema that
has never held its tables, and a SECOND time before any case work. The schema
is sealed after both applies.

CARD_EVIDENCE_TEST_PG_DSN names the lane database (postgresql+asyncpg://...),
falling back to SEAT_EVIDENCE_TEST_PG_DSN; CARD_EVIDENCE_TEST_PG_OPTOUT=1
waives the live cases deliberately. Unset and not waived, every live case
FAILS: a skipped live case reports exit 0 for coverage that did not run.
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
import seat_evidence_pg as sp  # noqa: E402

DSN_VAR = "CARD_EVIDENCE_TEST_PG_DSN"
OPTOUT_VAR = "CARD_EVIDENCE_TEST_PG_OPTOUT"
DSN = (os.environ.get(DSN_VAR) or os.environ.get(sp.DSN_VAR) or "").replace(
    "postgresql+asyncpg://", "postgresql://")
OPTOUT = os.environ.get(OPTOUT_VAR) == "1"

M370_NAME = "370_card_evidence.sql"
M370 = os.path.join(cf_pg.SQL_DIR, M370_NAME)
CARD_TABLES = frozenset({"card_evidence", "card_pool_registry", "card_games", "card_hand_outside",
                         "card_phase_outside", "card_contrib", "card_player_daily",
                         "card_evidence_seeded_keys"})


def require_live_pg():
    """Fail, not skip (module docstring)."""
    if DSN and sp._asyncpg is not None:
        return
    if OPTOUT:
        pytest.skip("%s is unset and %s=1: the card evidence live coverage is "
                    "deliberately waived." % (DSN_VAR, OPTOUT_VAR))
    pytest.fail("%s (or %s) is unset, so no card evidence case ran against migration 370. "
                "Point it at a throwaway database, or set %s=1 to waive the coverage "
                "deliberately." % (DSN_VAR, sp.DSN_VAR, OPTOUT_VAR))


def read_370():
    return io.open(M370, encoding="utf-8").read()


async def snapshot(conn):
    """Every row and object 370 can write, as text, for the second-run comparison."""
    out = {"runtime_settings": await conn.fetch(
        "SELECT key, value FROM runtime_settings WHERE key LIKE 'card%' ORDER BY key")}
    for t in sorted(CARD_TABLES):
        out[t] = await conn.fetch("SELECT * FROM %s ORDER BY 1" % t)
    out["constraints"] = await conn.fetch(
        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE connamespace = current_schema()::regnamespace AND conrelid::regclass::text LIKE 'card%' "
        "ORDER BY conname")
    out["indexes"] = await conn.fetch(
        "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = current_schema() "
        "AND tablename LIKE 'card%' ORDER BY indexname")
    return {k: [tuple(r) for r in v] for k, v in out.items()}


async def build(case, dsn):
    """The seat build with 370 held out, then 370 whole, twice."""
    saved = cf_pg.HELD_OUT
    cf_pg.HELD_OUT = frozenset(saved | {M370_NAME})
    try:
        await sp.build(case, dsn)
    finally:
        cf_pg.HELD_OUT = saved
    conn = case.conn
    present = await conn.fetchval(
        "SELECT count(*) FROM pg_tables WHERE schemaname = current_schema() "
        "AND tablename = ANY($1::text[])", sorted(CARD_TABLES))
    assert present == 0, "a card table existed before 370's first apply"
    await conn.execute(read_370())
    first = await snapshot(conn)
    await conn.execute(read_370())
    again = await snapshot(conn)
    return first, again


@contextlib.asynccontextmanager
async def case(prefix="card"):
    """A built, sealed case schema; yields (case, sessionmaker, (first, again))."""
    async with harness.CaseSchema(DSN, prefix) as c:
        snaps = await build(c, DSN)
        await c.seal()
        engine = harness.bound_engine(DSN, c.schema)
        try:
            yield c, async_sessionmaker(engine, expire_on_commit=False), snaps
        finally:
            await engine.dispose()
