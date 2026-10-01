"""Live PostgreSQL for the connect-failure lane (DESIGN V11): one case schema
per case, built as the ladder suite builds its own.

The build (test_title_ladder_hooks_live._build, reused step for step): the
DDL of every numbered migration is replayed, the ORM makes the tables no
migration makes, the mapped tables are widened, and the DDL is replayed again;
then 331 runs whole. Two differences, both on purpose:

  - 355_ffa_assembly.sql is held out of both replays and run WHOLE at the end,
    inside its own BEGIN/COMMIT, so every case runs the migration this lane
    ships as its FIRST apply. A case that builds with with_355=False applies
    it itself (the migration's own dry run and re-run).
  - the case schema is sealed only after the case's own DDL, so the census
    proves that nothing the build or the case ran reached outside it.

CF_TEST_PG_DSN names the lane database (postgresql+asyncpg://...);
CF_TEST_PG_OPTOUT=1 waives the live cases deliberately. Unset and not
waived, every live case FAILS, because a skipped live case reports exit 0
for coverage that did not run.
"""

import contextlib
import glob
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import pytest  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

import ladder_pg_harness as harness  # noqa: E402
import models  # noqa: E402
import test_title_ladder_hooks_live as lh  # noqa: E402

try:
    import asyncpg as _asyncpg
except ImportError:                                    # pragma: no cover
    _asyncpg = None

DSN_VAR = "CF_TEST_PG_DSN"
OPTOUT_VAR = "CF_TEST_PG_OPTOUT"
# CF_PG_POOL=0: every case builds a fresh schema and drops it (cf_pool's
# docstring says what the pool does instead).
POOL = os.environ.get("CF_PG_POOL", "1") != "0"
DSN = (os.environ.get(DSN_VAR) or "").replace("postgresql+asyncpg://", "postgresql://")
OPTOUT = os.environ.get(OPTOUT_VAR) == "1"

SQL_DIR = os.path.normpath(os.path.join(HERE, "..", "sql"))
M331 = lh.MIGRATION
M355 = os.path.join(SQL_DIR, "355_ffa_assembly.sql")
HELD_OUT = frozenset({os.path.basename(M331), os.path.basename(M355)})


def require_live_pg():
    """Fail, not skip (module docstring)."""
    if DSN and _asyncpg is not None:
        return
    if OPTOUT:
        pytest.skip("%s is unset and %s=1: the connect-failure live coverage is "
                    "deliberately waived." % (DSN_VAR, OPTOUT_VAR))
    if _asyncpg is None:
        pytest.fail("asyncpg is not installed, so no connect-failure route ran "
                    "against a real server. Install it, or set %s=1." % OPTOUT_VAR)
    pytest.fail("%s is unset, so no connect-failure route ran against migration "
                "355's tables. Point it at a throwaway database, or set %s=1 to "
                "waive the coverage deliberately." % (DSN_VAR, OPTOUT_VAR))


def ddl_statements():
    """The replayed DDL of every numbered migration outside HELD_OUT, split and
    selected exactly as the ladder suite selects its own."""
    out = []
    for path in sorted(glob.glob(os.path.join(SQL_DIR, "*.sql"))):
        name = os.path.basename(path)
        if not re.match(r"^\d{3}_", name) or name in HELD_OUT:
            continue
        for s in lh._split_sql(io.open(path, encoding="utf-8").read()):
            head = s.lstrip()
            if re.search(r"\bpg_temp\.", s):
                continue
            if lh._DDL_HEAD.match(head) or (re.match(r"^DO\b", head, re.I)
                                            and lh._DO_DDL.search(head)):
                s = re.sub(r"\buuid_generate_v4\(\)", "gen_random_uuid()", s)
                s = re.sub(r"\s+CONCURRENTLY\b", "", s, flags=re.I)
                out.append((name, s))
    return out


def read_355():
    return io.open(M355, encoding="utf-8").read()


async def apply_355(conn):
    """Run 355 whole on `conn` (its own BEGIN/COMMIT). The connection must not
    be inside a transaction."""
    await conn.execute(read_355())


async def _replay_refused(conn, statements):
    """Run each statement on its own; return the (file, statement) pairs the
    server refused, in order."""
    refused = []
    for name, s in statements:
        try:
            await conn.execute(s)
        except _asyncpg.PostgresError:
            refused.append((name, s))
    return refused


async def build(case, *, with_355=True, dsn=None, faithful=False):
    """Into case.schema, on case.conn: replay, ORM, widen, replay, 331, and
    355 when asked. Not sealed: the caller seals after its own DDL.

    faithful=True replays every statement ONCE where it can run: the second
    pass re-runs only the statements the first pass refused (the ones that
    alter tables only the ORM makes). The default second pass re-runs them
    all, which re-adds a column a later migration renamed away (208's
    live_top_points after 209's rename) -- harmless to a handler, wrong for
    a check that reads the table's column list."""
    conn, schema = case.conn, case.schema
    statements = ddl_statements()
    refused = (await _replay_refused(conn, statements) if faithful
               else await lh._replay(conn, statements))
    engine = harness.bound_engine(dsn or DSN, schema)
    try:
        async with engine.begin() as c:
            await c.run_sync(models.Base.metadata.create_all)
    finally:
        await engine.dispose()
    await lh._widen(conn, schema)
    if faithful:
        for _ in range(3):
            if not refused:
                break
            refused = await _replay_refused(conn, refused)
    else:
        second = await lh._replay(conn, statements)
        unexpected = [f for f in second
                      if f[1] not in lh._ALREADY and (f[0], f[1]) not in lh.REPLAY_KNOWN]
        assert not unexpected, (
            "the second DDL pass failed on statements outside REPLAY_KNOWN: %r"
            % unexpected[:5])
    await conn.execute(io.open(M331, encoding="utf-8").read())
    if with_355:
        await apply_355(conn)


@contextlib.asynccontextmanager
async def case(prefix="cf", *, with_355=True, dsn=None, faithful=False):
    """A built case schema; yields (case, sessionmaker). The case seals its
    schema through `await c.seal()` before the first handler call when it
    runs DDL of its own; otherwise the context seals it on entry. `dsn`
    names another database on the same server (fresh_database). A case
    with 355 applied and no dsn of its own comes from cf_pool when POOL is
    on; a case that applies 355 itself always builds its own schema."""
    if POOL and with_355 and dsn is None:
        import cf_pool
        async with cf_pool.checkout(faithful=faithful) as got:
            yield got
        return
    async with harness.CaseSchema(dsn or DSN, prefix) as c:
        await build(c, with_355=with_355, dsn=dsn, faithful=faithful)
        if with_355:
            await c.seal()
        engine = harness.bound_engine(dsn or DSN, c.schema)
        try:
            yield c, async_sessionmaker(engine, expire_on_commit=False)
        finally:
            await engine.dispose()


@contextlib.asynccontextmanager
async def fresh_database(prefix="cfdb"):
    """A throwaway database on the lane's server, dropped on exit; yields its
    DSN. For a check that must see exactly one ffa_lobbies in
    information_schema: migration 209's rename guard reads
    information_schema.columns without a schema, so in the shared lane
    database it sees every other case schema's ffa_lobbies, skips the
    rename, and leaves 208's live_top_points beside live_total_points -- a
    column no deployed database has."""
    name = "%s_%d_%s" % (prefix, os.getpid(), os.urandom(4).hex())
    admin = await _asyncpg.connect(DSN)
    try:
        await admin.execute('CREATE DATABASE "%s"' % name)
    finally:
        await admin.close()
    try:
        yield DSN.rsplit("/", 1)[0] + "/" + name
    finally:
        admin = await _asyncpg.connect(DSN)
        try:
            await admin.execute('DROP DATABASE IF EXISTS "%s" WITH (FORCE)' % name)
        finally:
            await admin.close()


# The standing invariants (evidence V11:2985-3007), each a count that must be
# 0. The g3 row is the pre-production form (the table exists until the
# production-enabling release drops it).
STANDING_INVARIANTS = (
    ("started_canceled",
     "SELECT count(*) FROM ffa_lobbies WHERE start_granted_at IS NOT NULL "
     "AND status = 'canceled'"),
    ("short_bettable",
     "SELECT count(*) FROM ffa_lobbies WHERE short_started_at IS NOT NULL "
     "AND NOT bets_disabled"),
    ("reform_rows_left",
     "SELECT count(*) FROM ffa_queue q JOIN ffa_lobbies l ON l.id = q.series_id "
     "WHERE l.reformed_from IS NOT NULL AND l.status = 'active' AND l.games_played = 0"),
    ("late_unbound",
     "SELECT count(*) FROM ffa_assembly_seats WHERE verdict = 'admitted_late' "
     "AND (actor_nr IS NULL OR actor_region IS NULL)"),
    ("started_unbacked",
     "SELECT count(*) FROM ffa_assembly_seats s JOIN ffa_lobbies l ON l.id = s.lobby_id "
     "WHERE s.started_at IS NOT NULL AND (l.start_granted_at IS NULL OR NOT "
     "(s.start_roster OR s.late_admitted_at IS NOT NULL))"),
    ("late_body_order",
     "SELECT count(*) FROM ffa_assembly_seats WHERE late_body_game < late_game "
     "OR (late_body_game IS NOT NULL AND late_admitted_at IS NULL)"),
    ("late_without_epoch",
     "SELECT count(*) FROM ffa_assembly_seats s WHERE s.verdict = 'admitted_late' "
     "AND NOT EXISTS (SELECT 1 FROM ffa_kept_epochs e WHERE e.lobby_id = s.lobby_id "
     "AND e.slot = s.slot AND e.actor_nr = s.actor_nr)"),
    ("g3_over_72h",
     "SELECT count(*) FROM ffa_g3_seats WHERE expires_at > now() + interval '72 hours'"),
    ("gone_unstarted",
     "SELECT count(*) FROM ffa_assembly_seats s JOIN ffa_lobbies l ON l.id = s.lobby_id "
     "WHERE s.gone_game IS NOT NULL AND l.start_granted_at IS NULL"),
    ("gone_path_vocab",
     "SELECT count(*) FROM ffa_assembly_seats WHERE gone_path IS NOT NULL "
     "AND gone_path NOT IN ('leave', 'witness')"),
    ("left_after_grant",
     "SELECT count(*) FROM ffa_assembly_seats s JOIN ffa_lobbies l ON l.id = s.lobby_id "
     "WHERE s.verdict = 'left' AND l.start_granted_at IS NOT NULL "
     "AND s.verdict_at > l.start_granted_at "
     "AND (s.start_roster OR s.late_admitted_at IS NOT NULL)"),
    ("gone_leave_without_leave",
     "SELECT count(*) FROM ffa_assembly_seats WHERE gone_path = 'leave' AND left_at IS NULL"),
    ("release_pair",
     "SELECT count(*) FROM ffa_assembly_seats WHERE (released_at IS NULL) <> "
     "(release_why IS NULL) OR release_why NOT IN ('fence_expired', 'join_timeout')"),
)


# reform_rows_left holds "once every such lobby's seats have left" (evidence
# V11:2988): a test that re-forms a lobby and keeps its carried seats queued
# in L' checks it only after they leave, so a caller may skip it by name.
async def standing_invariants(conn, skip=()):
    """{name: count} for every standing invariant not in `skip`; each must
    be 0."""
    return {name: await conn.fetchval(sql) for name, sql in STANDING_INVARIANTS
            if name not in skip}
