"""Live PostgreSQL for the identity-clock lane (migration 372).

The seat-evidence build (seat_evidence_pg.build: cf_pg's replay, the ORM's
own tables, widen, replay again, 331 and 355 whole, 368 whole twice) with 372
held out of both replays as well, so 372 runs WHOLE as its first apply on a
schema that has never held its tables. It then runs whole a SECOND time (the
re-run rule), is ROLLED BACK (its tables and the switches it seeded gone, no
other row moved), and is applied a THIRD time from that state; then findings
are planted on both sides of the "identity " namespace, the rollback runs
again and must remove exactly the identity rows, and 372 is applied a fourth
time, before the schema is sealed and any case work starts.

The DSN is seat-evidence's (SEAT_EVIDENCE_TEST_PG_DSN), with its opt-out:
this lane is a reader of the same throwaway database.
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

M372_NAME = "372_identity_clock_evidence.sql"
M372 = os.path.join(cf_pg.SQL_DIR, M372_NAME)
R372 = os.path.join(cf_pg.SQL_DIR, "rollback_372_identity_clock_evidence.sql")
ICE_TABLES = ("game_file_digests", "identity_clock_evidence", "identity_clock_games",
              "identity_clock_seeded_keys")
ICE_SWITCHES = ("identity_clock_evidence_accept", "identity_clock_evidence_purge",
                "identity_clock_evidence_worker")

require_live_pg = sp.require_live_pg


def read_372():
    return io.open(M372, encoding="utf-8").read()


def read_rollback():
    return io.open(R372, encoding="utf-8").read()


async def present(conn):
    return await conn.fetchval(
        "SELECT count(*) FROM pg_tables WHERE schemaname = current_schema() "
        "AND tablename = ANY($1::text[])", list(ICE_TABLES))


async def snapshot(conn):
    """Every row and object 372 can write, as text, for the run comparisons.
    Tables 372 has not made (yet, or any more) read as None."""
    out = {"runtime_settings": await conn.fetch(
        "SELECT key, value, updated_at::text FROM runtime_settings ORDER BY key")}
    have = {r["tablename"] for r in await conn.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname = current_schema()")}
    for t in ICE_TABLES:
        out[t] = (await conn.fetch("SELECT * FROM %s ORDER BY 1" % t)
                  if t in have and t != "identity_clock_seeded_keys"
                  else (await conn.fetch("SELECT key FROM %s ORDER BY 1" % t) if t in have
                        else None))
    out["findings"] = await conn.fetch(
        "SELECT id, dedup_key FROM seat_evidence_findings ORDER BY id")
    out["constraints"] = await conn.fetch(
        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE connamespace = current_schema()::regnamespace ORDER BY conname")
    out["indexes"] = await conn.fetch(
        "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = current_schema() "
        "ORDER BY indexname")
    return {k: (None if v is None else [tuple(r) for r in v]) for k, v in out.items()}


# (scope, dedup key, rule id) planted around the namespace cycle. Seat keys
# are legal seat_evidence stable keys (seat_evidence._KEY_CHARS, no space)
# followed by the two pair ids; identity keys are built by ice_dedup_key.
_LO, _HI = "00000000-0000-0000-0000-00000000000a", "00000000-0000-0000-0000-00000000000b"
PLANTED_SEAT = (
    ("game", "identity|X|%s|%s" % (_LO, _HI), "r0000a001"),
    ("game", "identityX|%s|%s" % (_LO, _HI), "r0000a001"),
    ("game", "identity_|%s|%s" % (_LO, _HI), "r0000a001"),
    ("sitting", "identity|X|%s|%s" % (_LO, _HI), "r0000a001"),
    ("game", "combat X|%s|%s" % (_LO, _HI), "r0000a001"),
)
PLANTED_IDENTITY = (
    ("game", "identity X|%s|%s" % (_LO, _HI), "r0000a001"),
    ("game", "identity ranked_k|%s|%s" % (_LO, _HI), "r0000e001"),
)
PLANTED = PLANTED_SEAT + PLANTED_IDENTITY


async def build(case, dsn):
    """The seat-evidence build with 372 held out, then 372 whole twice, the
    rollback, 372 once more, and the planted namespace cycle. Returns the
    snapshots by name."""
    saved = cf_pg.HELD_OUT
    cf_pg.HELD_OUT = frozenset(saved | {M372_NAME})
    try:
        await sp.build(case, dsn)
    finally:
        cf_pg.HELD_OUT = saved
    conn = case.conn
    assert await present(conn) == 0, "an identity-clock table existed before 372's first apply"
    before = await snapshot(conn)
    await conn.execute(read_372())
    first = await snapshot(conn)
    await conn.execute(read_372())
    again = await snapshot(conn)
    await conn.execute(read_rollback())
    rolled = await snapshot(conn)
    await conn.execute(read_372())
    third = await snapshot(conn)
    for scope, dedup, rule in PLANTED:
        await conn.execute(
            "INSERT INTO seat_evidence_findings (scope, dedup_key, rule_id, rules_rev) "
            "VALUES ($1, $2, $3, 'r0000plant')", scope, dedup, rule)
    planted = await snapshot(conn)
    await conn.execute(read_rollback())
    planted_rolled = await snapshot(conn)
    await conn.execute(read_372())
    fourth = await snapshot(conn)
    await conn.execute("DELETE FROM seat_evidence_findings WHERE rules_rev = 'r0000plant'")
    return {"before": before, "first": first, "again": again, "rolled": rolled, "third": third,
            "planted": planted, "planted_rolled": planted_rolled, "fourth": fourth}


@contextlib.asynccontextmanager
async def case(prefix="ice"):
    """A built, sealed case schema; yields (case, sessionmaker, snapshots)."""
    async with harness.CaseSchema(sp.DSN, prefix) as c:
        snaps = await build(c, sp.DSN)
        await c.seal()
        engine = harness.bound_engine(sp.DSN, c.schema)
        try:
            yield c, async_sessionmaker(engine, expire_on_commit=False), snaps
        finally:
            await engine.dispose()
