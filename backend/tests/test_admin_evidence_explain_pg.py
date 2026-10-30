"""Admin evidence report, phase 1a item 1: the order indexes, measured by plan.

Migration 377 adds four indexes on `matches` (design 7.1), each ending in the
`id` its ordering breaks ties on. Their whole purpose is a property of the
PLAN, so this module reads plans: every report read is run under
`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` against seeded fixtures (design 2.9)
and each gate requires (the acceptance as restated by the integrator's pass 2
ruling 3; the lane notes carry it as a deviation from the certified wording)

  * no sequential or bitmap scan anywhere;
  * exactly one index scan or index-only scan per branch, each under its own
    branch Limit, whose Index Cond carries at least one seat equality (the
    series equality for the series read) and, where the read has one, the
    `(ended_at, id)` time bound with its trailing `id`; either seat order
    index or the pair index satisfies it;
  * no Sort or Incremental Sort between that scan and its branch Limit;
  * rows read by that scan (actual rows plus rows removed by a filter or
    recheck) at or under the read's ceiling, so a seat index with a Filter
    passes only while its rows read stay under the ceiling;
  * a merge above the two branches over at most twice the branch limit;
  * the same ids, in the same order, as a reference query with no LIMIT under
    the index (so a fast plan returning the wrong rows is red too).

STATISTICS are part of the fixture: after the load every loaded table gets
`VACUUM (ANALYZE)` (outside any open transaction), so the planner reads the
statistics and visibility a maintained production table has; the
`default_statistics_target` in force is printed. The migration's statistics
object on the seat pair (`stx_matches_pair`, kind mcv; integrator pass 3
ruling 5) is built by that analysis too, and the fixture gate requires its
most-common-values list. No planner setting (no
enable_* and no cost setting) appears anywhere in this module: a gate that
forces its plan cannot fail. `plan_cache_mode` only selects WHICH plan is read
(the generic one a statement cache reuses), never its shape.

Every gate runs on the custom plan (planned with the bound values) and on
the generic plan (PREPARE, EXECUTE under force_generic_plan), the one a
connection's statement cache settles on after its first executions.

FIXTURES (design 2.9): a 10,000-game distractor player; a rare pair with 3
games per orientation beside it; a short series among 10,000 unrelated
series; the series bound (10, 11 and 10,000 games); equal timestamps (10,000
pair games and 10,000 player games sharing one `ended_at`, a baseline before a
game at that timestamp, and a series sharing one).

THE STATEMENTS. Item 1a-4 builds the routes; until then the read statements
are held here in the routes' `:name` bind form with typed casts, and 1a-4
binds this module to the route module's own statements. The population
rebuild's sort-key gate is item 1a-3's.

SCRATCH CYCLE. The migration is applied to a throwaway schema, the four
indexes are read back from `pg_indexes` and the statistics object from
`pg_statistic_ext`, the file is applied again and must leave every index and the
statistics object with its OID and definition unchanged; a same-named index
or statistics object with another definition must abort the file; over a
loaded table the file's own `ANALYZE` must leave the object's
most-common-values list built.

RUNNING IT. `ADMIN_EVIDENCE_TEST_PG_DSN` names a PostgreSQL database whose
name carries `admin_evidence` (the module creates and drops its own schemas
there). Unset, the module FAILS rather than skips; an affirmative
`ADMIN_EVIDENCE_TEST_PG_OPTOUT` turns that into named skips.
"""

import asyncio
import json
import os
import pathlib
import re
import uuid
from urllib.parse import urlsplit

import pytest

try:
    import asyncpg
except ImportError:                                    # pragma: no cover
    asyncpg = None

SQL_DIR = pathlib.Path(__file__).resolve().parents[1] / "sql"
MIGRATION = SQL_DIR / "377_admin_evidence_indexes.sql"

DSN = (os.environ.get("ADMIN_EVIDENCE_TEST_PG_DSN") or "").replace(
    "postgresql+asyncpg://", "postgresql://")
OPTOUT = str(os.environ.get("ADMIN_EVIDENCE_TEST_PG_OPTOUT") or "").strip().lower() in {
    "1", "true", "yes", "on"}

# CONTRACT_BOUNDS values these reads are sized by (design 2.8, 2.9). Item
# 1a-2 moves them into the route module and this module then reads them there.
SERIES_GAMES_MAX = 10
BASELINE_SCAN = 500
GAMES_MAX = 30

FOUR = {
    "idx_matches_pair": "btree (player1_id, player2_id, ended_at DESC, id DESC)",
    "idx_matches_p1_order": "btree (player1_id, ended_at DESC, id DESC)",
    "idx_matches_p2_order": "btree (player2_id, ended_at DESC, id DESC)",
    "idx_matches_series": "btree (series_id, ended_at, id) WHERE (series_id IS NOT NULL)",
}


def require_pg():
    if DSN and asyncpg is not None:
        name = urlsplit(DSN).path.lstrip("/")
        if "admin_evidence" not in name:
            pytest.fail("ADMIN_EVIDENCE_TEST_PG_DSN points at database %r; this "
                        "module creates and drops schemas there, so it runs only "
                        "in a database whose name carries 'admin_evidence'" % name)
        return DSN
    if OPTOUT:
        pytest.skip("ADMIN_EVIDENCE_TEST_PG_OPTOUT is set: the order-index plan "
                    "gates were deliberately not run in this invocation")
    pytest.fail("ADMIN_EVIDENCE_TEST_PG_DSN is not set (or asyncpg is missing), so "
                "no plan gate ran; point it at a throwaway database, or set "
                "ADMIN_EVIDENCE_TEST_PG_OPTOUT=1 to waive the coverage by name")


# ── Statements, in the routes' bind form ────────────────────────────────────

R1_CODE = """
SELECT m.id FROM matches m
 WHERE LEFT(REPLACE(m.id::text, '-', ''), 12) = CAST(:code AS text)
 LIMIT 2"""

R2_SERIES = """
SELECT m.id, m.ended_at FROM matches m
 WHERE m.series_id = CAST(:sid AS uuid)
 ORDER BY m.ended_at, m.id
 LIMIT CAST(:lim AS integer)"""

R3_PAIR = """
SELECT u.id, u.ended_at FROM (
  (SELECT m.id, m.ended_at FROM matches m
    WHERE m.player1_id = CAST(:a AS uuid) AND m.player2_id = CAST(:b AS uuid)
    ORDER BY m.ended_at DESC, m.id DESC LIMIT CAST(:games AS integer))
  UNION ALL
  (SELECT m.id, m.ended_at FROM matches m
    WHERE m.player1_id = CAST(:b AS uuid) AND m.player2_id = CAST(:a AS uuid)
    ORDER BY m.ended_at DESC, m.id DESC LIMIT CAST(:games AS integer))
) u
 ORDER BY u.ended_at DESC, u.id DESC
 LIMIT CAST(:games AS integer)"""

R4_PLAYER = """
SELECT u.id, u.ended_at FROM (
  (SELECT m.id, m.ended_at FROM matches m
    WHERE m.player1_id = CAST(:s AS uuid)
    ORDER BY m.ended_at DESC, m.id DESC LIMIT CAST(:games AS integer))
  UNION ALL
  (SELECT m.id, m.ended_at FROM matches m
    WHERE m.player2_id = CAST(:s AS uuid)
    ORDER BY m.ended_at DESC, m.id DESC LIMIT CAST(:games AS integer))
) u
 ORDER BY u.ended_at DESC, u.id DESC
 LIMIT CAST(:games AS integer)"""

SEAT_BASELINE = """
SELECT u.id, u.ended_at FROM (
  (SELECT m.id, m.ended_at FROM matches m
    WHERE m.player1_id = CAST(:s AS uuid) AND m.invalidated_at IS NULL
      AND (m.ended_at, m.id) < (CAST(:g_ended AS timestamptz), CAST(:g_id AS uuid))
    ORDER BY m.ended_at DESC, m.id DESC LIMIT CAST(:scan AS integer))
  UNION ALL
  (SELECT m.id, m.ended_at FROM matches m
    WHERE m.player2_id = CAST(:s AS uuid) AND m.invalidated_at IS NULL
      AND (m.ended_at, m.id) < (CAST(:g_ended AS timestamptz), CAST(:g_id AS uuid))
    ORDER BY m.ended_at DESC, m.id DESC LIMIT CAST(:scan AS integer))
) u
 ORDER BY u.ended_at DESC, u.id DESC
 LIMIT CAST(:scan AS integer)"""

PAIR_BASELINE = """
SELECT u.id, u.ended_at FROM (
  (SELECT m.id, m.ended_at FROM matches m
    WHERE m.player1_id = CAST(:a AS uuid) AND m.player2_id = CAST(:b AS uuid)
      AND m.invalidated_at IS NULL
      AND (m.ended_at, m.id) < (CAST(:g_ended AS timestamptz), CAST(:g_id AS uuid))
    ORDER BY m.ended_at DESC, m.id DESC LIMIT CAST(:scan AS integer))
  UNION ALL
  (SELECT m.id, m.ended_at FROM matches m
    WHERE m.player1_id = CAST(:b AS uuid) AND m.player2_id = CAST(:a AS uuid)
      AND m.invalidated_at IS NULL
      AND (m.ended_at, m.id) < (CAST(:g_ended AS timestamptz), CAST(:g_id AS uuid))
    ORDER BY m.ended_at DESC, m.id DESC LIMIT CAST(:scan AS integer))
) u
 ORDER BY u.ended_at DESC, u.id DESC
 LIMIT CAST(:scan AS integer)"""

# Reference reads: the same predicate and order with no per-branch LIMIT and
# no index to lean on (the planner's choice is irrelevant to the answer).
REF_SERIES = """
SELECT m.id FROM matches m WHERE m.series_id = CAST(:sid AS uuid)
 ORDER BY m.ended_at, m.id"""
REF_PAIR = """
SELECT m.id FROM matches m
 WHERE (m.player1_id = CAST(:a AS uuid) AND m.player2_id = CAST(:b AS uuid))
    OR (m.player1_id = CAST(:b AS uuid) AND m.player2_id = CAST(:a AS uuid))
 ORDER BY m.ended_at DESC, m.id DESC"""
REF_PLAYER = """
SELECT m.id FROM matches m
 WHERE m.player1_id = CAST(:s AS uuid) OR m.player2_id = CAST(:s AS uuid)
 ORDER BY m.ended_at DESC, m.id DESC"""

_BIND = re.compile(r"(?<![:\w]):([a-z_][a-z0-9_]*)")


def _positional(sql, params):
    """`:name` binds to asyncpg's `$n`, one number per distinct name (the
    form SQLAlchemy's text() gives the routes)."""
    order = []

    def sub(m):
        name = m.group(1)
        if name not in order:
            order.append(name)
        return "$%d" % (order.index(name) + 1)

    text = _BIND.sub(sub, sql)
    missing = [n for n in order if n not in params]
    assert not missing, "unbound names %r" % missing
    return text, [params[n] for n in order]


# ── Fixture database ───────────────────────────────────────────────────────

T0 = "2026-01-01T00:00:00Z"
TE = "2026-03-01T00:00:00Z"

PREREQ = """
CREATE TABLE ranked_series (id UUID PRIMARY KEY);
CREATE TABLE matches (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player1_id      UUID NOT NULL,
    player2_id      UUID NOT NULL,
    series_id       UUID REFERENCES ranked_series(id),
    is_ranked       BOOLEAN NOT NULL DEFAULT FALSE,
    invalidated_at  TIMESTAMPTZ,
    ended_at        TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE INDEX idx_matches_player1 ON matches (player1_id, ended_at DESC);
CREATE INDEX idx_matches_player2 ON matches (player2_id, ended_at DESC);
CREATE INDEX idx_matches_ended ON matches (ended_at DESC);
CREATE INDEX idx_matches_shortcode ON matches (LEFT(REPLACE(id::text, '-', ''), 12));
"""


class Seeded:
    pass


def _ids(n):
    return [uuid.uuid4() for _ in range(n)]


async def _seed(conn):
    s = Seeded()
    s.D, s.R, s.X, s.Y, s.X2, s.Y2, s.P, s.Q, s.E = _ids(9)
    s.S3, s.S10, s.S11, s.S10000, s.SE = _ids(5)
    await conn.executemany("INSERT INTO ranked_series (id) VALUES ($1)",
                           [(x,) for x in (s.S3, s.S10, s.S11, s.S10000, s.SE)])
    # Distractor: 10,000 games, alternating seats, one minute apart.
    await conn.execute("""
        INSERT INTO matches (player1_id, player2_id, ended_at)
        SELECT CASE WHEN i % 2 = 0 THEN $1::uuid ELSE gen_random_uuid() END,
               CASE WHEN i % 2 = 0 THEN gen_random_uuid() ELSE $1::uuid END,
               $2::timestamptz + make_interval(mins => i)
          FROM generate_series(1, 10000) AS i""", s.D, _ts(T0))
    # Rare pair D-R: three games per orientation, spread inside D's range.
    await conn.execute("""
        INSERT INTO matches (player1_id, player2_id, ended_at)
        SELECT CASE WHEN i <= 3 THEN $1::uuid ELSE $2::uuid END,
               CASE WHEN i <= 3 THEN $2::uuid ELSE $1::uuid END,
               $3::timestamptz + make_interval(mins => i * 1000, secs => 30)
          FROM generate_series(1, 6) AS i""", s.D, s.R, _ts(T0))
    # 10,000 unrelated one-game series, then the short series S3.
    await conn.execute("""
        WITH ser AS (
            INSERT INTO ranked_series (id)
            SELECT gen_random_uuid() FROM generate_series(1, 10000)
            RETURNING id)
        INSERT INTO matches (player1_id, player2_id, series_id, ended_at)
        SELECT gen_random_uuid(), gen_random_uuid(), ser.id,
               $1::timestamptz + make_interval(secs => (random() * 1000000)::int)
          FROM ser""", _ts(T0))
    for sid, count, same in ((s.S3, 3, False), (s.S10, 10, False),
                             (s.S11, 11, False), (s.S10000, 10000, False),
                             (s.SE, 10000, True)):
        await conn.execute("""
            INSERT INTO matches (player1_id, player2_id, series_id, ended_at)
            SELECT $1::uuid, $2::uuid, $3::uuid,
                   CASE WHEN $5 THEN $6::timestamptz
                        ELSE $6::timestamptz + make_interval(mins => i) END
              FROM generate_series(1, $4::int) AS i""",
                           s.X2, s.Y2, sid, count, same, _ts(T0))
    # Equal timestamps: 10,000 P-Q games and 10,000 E games at one ended_at.
    await conn.execute("""
        INSERT INTO matches (player1_id, player2_id, ended_at)
        SELECT CASE WHEN i % 2 = 0 THEN $1::uuid ELSE $2::uuid END,
               CASE WHEN i % 2 = 0 THEN $2::uuid ELSE $1::uuid END,
               $3::timestamptz
          FROM generate_series(1, 10000) AS i""", s.P, s.Q, _ts(TE))
    await conn.execute("""
        INSERT INTO matches (player1_id, player2_id, ended_at)
        SELECT CASE WHEN i % 2 = 0 THEN $1::uuid ELSE gen_random_uuid() END,
               CASE WHEN i % 2 = 0 THEN gen_random_uuid() ELSE $1::uuid END,
               $2::timestamptz
          FROM generate_series(1, 10000) AS i""", s.E, _ts(TE))
    # Statistics are part of the fixture (integrator pass 2 ruling 1): each
    # loaded table is vacuumed and analysed, one statement per call so no
    # VACUUM runs inside an implicit transaction block.
    s.loaded = ("matches", "ranked_series")
    for table in s.loaded:
        await conn.execute("VACUUM (ANALYZE) %s" % table)
    # The visibility map is this seed's postcondition (the gate reads
    # relallvisible == relpages). With autovacuum off on both tables, only
    # another backend's snapshot can hold a page back; exactly one re-run
    # covers a transient one, and the gate still asserts.
    for table in s.loaded:
        row = await conn.fetchrow("""
            SELECT c.relpages, c.relallvisible
              FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = current_schema() AND c.relname = $1""", table)
        if row["relallvisible"] != row["relpages"]:
            await asyncio.sleep(1.0)
            await conn.execute("VACUUM (ANALYZE) %s" % table)
    s.stats_target = await conn.fetchval("SHOW default_statistics_target")
    return s


def _ts(text):
    import datetime as _dt
    return _dt.datetime.fromisoformat(text.replace("Z", "+00:00"))


class _Db:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.conn = None
        self.schema = "ae_explain_%s" % uuid.uuid4().hex[:10]

    def run(self, coro):
        return self.loop.run_until_complete(coro)


@pytest.fixture(scope="module")
def db():
    require_pg()
    d = _Db()

    async def up():
        d.conn = await asyncpg.connect(DSN)
        await d.conn.execute('CREATE SCHEMA "%s"' % d.schema)
        await d.conn.execute('SET search_path TO "%s"' % d.schema)
        await d.conn.execute(PREREQ)
        await d.conn.execute(MIGRATION.read_text(encoding="utf-8"))
        # The fixture owns its tables' statistics (ruling 1 below): no
        # autovacuum worker may ANALYZE a loaded table mid-load or hold a
        # snapshot while the fixture's VACUUM sets the visibility map (suite
        # seat 2, 2026-10-30: 113 of 742 matches pages all-visible after the
        # fixture's VACUUM, the rest held back by an autovacuum ANALYZE the
        # 60,030-row load had triggered).
        for table in ("matches", "ranked_series"):
            await d.conn.execute("ALTER TABLE %s SET (autovacuum_enabled = false)" % table)
        d.seed = await _seed(d.conn)

    async def down():
        try:
            await d.conn.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % d.schema)
        finally:
            await d.conn.close()

    try:
        d.run(up())
        yield d
    finally:
        if d.conn is not None:
            d.run(down())
        d.loop.close()


# ── Plan reading ───────────────────────────────────────────────────────────

SORTS = ("Sort", "Incremental Sort")
INDEX_SCANS = ("Index Scan", "Index Only Scan")


def _walk(node, path=()):
    yield node, path
    for child in node.get("Plans", []):
        yield from _walk(child, path + (node,))


def _touched(node):
    loops = node.get("Actual Loops", 1) or 1
    return loops * (node.get("Actual Rows", 0)
                    + node.get("Rows Removed by Filter", 0)
                    + node.get("Rows Removed by Index Recheck", 0))


def _literal(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return "'%s'" % str(value).replace("'", "''")


_PREPARED = [0]


async def _explain(conn, sql, params, mode="custom"):
    """The plan, measured. `custom`: planned with the bound values (what an
    EXPLAIN of a bound statement shows). `generic`: PREPARE, then EXECUTE
    under plan_cache_mode=force_generic_plan -- the plan a long-lived
    connection's statement cache reuses after its first executions, which
    is what production runs most of the time."""
    text, args = _positional(sql, params)
    if mode == "custom":
        raw = await conn.fetchval("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + text, *args)
    else:
        _PREPARED[0] += 1
        name = "ae_generic_%d" % _PREPARED[0]
        await conn.execute("PREPARE %s AS %s" % (name, text))
        try:
            await conn.execute("SET plan_cache_mode = force_generic_plan")
            raw = await conn.fetchval(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) EXECUTE %s(%s)"
                % (name, ", ".join(_literal(a) for a in args)))
        finally:
            await conn.execute("RESET plan_cache_mode")
            await conn.execute("DEALLOCATE %s" % name)
    doc = json.loads(raw) if isinstance(raw, str) else raw
    return doc[0]["Plan"]


MODES = ["custom", "generic"]


async def _rows(conn, sql, params):
    text, args = _positional(sql, params)
    return [r["id"] for r in await conn.fetch(text, *args)]


def _compact(plan):
    out = []
    for node, path in _walk(plan):
        bits = ["  " * len(path) + node["Node Type"]]
        for k in ("Index Name", "Index Cond", "Filter", "Sort Key", "Actual Rows",
                  "Rows Removed by Filter"):
            if k in node:
                bits.append("%s=%s" % (k, node[k]))
        out.append(" ".join(str(b) for b in bits))
    return "\n".join(out)


def _gate(plan, **kw):
    try:
        return _gate_checks(plan, **kw)
    except AssertionError as ex:
        # A failing case prints its whole EXPLAIN (ANALYZE, BUFFERS) plan into
        # the step log (integrator pass 2 ruling 4), after the compact form.
        raise AssertionError("%s\nPLAN:\n%s\nFULL PLAN (EXPLAIN ANALYZE, BUFFERS):\n%s"
                             % (ex, _compact(plan), json.dumps(plan, indent=1))) from None


SEAT_EQUALITY = re.compile(r"\((?:player1_id|player2_id) = ")
SERIES_EQUALITY = re.compile(r"\(series_id = ")
TIME_BOUND = re.compile(r"ROW\(ended_at, id\) < ROW\(")


def _gate_checks(plan, *, branch_limit, branches, equality=SEAT_EQUALITY,
                 time_bound=False):
    """The design 2.9 gate over one plan, in the acceptance restated by the
    integrator's pass 2 ruling 3 (a property, not an index name); returns
    lines for the step log."""
    nodes = list(_walk(plan))
    kinds = [n["Node Type"] for n, _ in nodes]
    assert "Seq Scan" not in kinds, "sequential scan in the plan: %r" % kinds
    assert not [k for k in kinds if k.startswith("Bitmap")], (
        "bitmap scan in the plan (order lost): %r" % kinds)
    scans = [(n, p) for n, p in nodes if n["Node Type"] in INDEX_SCANS]
    assert len(scans) == branches, "%d index scans for %d branches" % (len(scans), branches)
    lines = []
    branch_limits = set()
    for node, path in scans:
        name = node["Index Name"]
        cond = node.get("Index Cond", "")
        assert equality.search(cond), (
            "%s: the Index Cond %r carries no %s" % (
                name, cond, "seat equality" if equality is SEAT_EQUALITY
                else "series equality"))
        if time_bound:
            assert TIME_BOUND.search(cond), (
                "%s: the Index Cond %r does not carry the (ended_at, id) time bound"
                % (name, cond))
        between = []
        for anc in reversed(path):
            if anc["Node Type"] == "Limit":
                branch_limits.add(id(anc))
                break
            between.append(anc["Node Type"])
        else:
            raise AssertionError("index scan %s has no Limit above it" % name)
        assert not [k for k in between if k in SORTS], (
            "%s: %r between the index scan and its Limit" % (name, between))
        touched = _touched(node)
        assert touched <= branch_limit, (
            "%s read %d rows, ceiling %d" % (name, touched, branch_limit))
        lines.append("%s %s est=%s read=%d (filter removed %d) ceiling=%d between=%r "
                     "shared_hit=%s shared_read=%s"
                     % (node["Node Type"], name, node.get("Plan Rows"), touched,
                        node.get("Rows Removed by Filter", 0), branch_limit, between,
                        node.get("Shared Hit Blocks"), node.get("Shared Read Blocks")))
    assert len(branch_limits) == branches, (
        "%d index scans share %d branch Limits; one scan per branch is required"
        % (len(scans), len(branch_limits)))
    if branches == 2:
        appends = [n for n, _ in nodes if n["Node Type"] in ("Append", "Merge Append")]
        assert len(appends) == 1, kinds
        merged = sum(c.get("Actual Rows", 0) for c in appends[0].get("Plans", []))
        assert merged <= 2 * branch_limit, (
            "merge over %d rows, bound %d" % (merged, 2 * branch_limit))
        lines.append("merge input=%d bound=%d" % (merged, 2 * branch_limit))
    lines.append("execution_ms=%s" % plan.get("Actual Total Time"))
    return lines


def _say(name, lines):
    print("GATE %s" % name)
    for line in lines:
        print("  " + line)


# ── The gates ──────────────────────────────────────────────────────────────

def test_fixture_statistics_are_those_of_a_maintained_table(db):
    """Ruling 1: every loaded table carries fresh statistics and a set
    visibility map before any plan is read: reltuples equals the row count
    (a VACUUM sets it exactly), every heap page is all-visible, and pg_stats
    holds the seat, time and series columns."""
    lines = ["default_statistics_target=%s" % db.seed.stats_target]
    for table in db.seed.loaded:
        row = db.run(db.conn.fetchrow("""
            SELECT c.reltuples::bigint AS reltuples, c.relpages, c.relallvisible
              FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = current_schema() AND c.relname = $1""", table))
        count = db.run(db.conn.fetchval("SELECT count(*) FROM %s" % table))
        assert row["reltuples"] == count, (table, row["reltuples"], count)
        assert row["relpages"] > 0 and row["relallvisible"] == row["relpages"], (
            table, dict(row))
        lines.append("%s rows=%d reltuples=%d relpages=%d relallvisible=%d"
                     % (table, count, row["reltuples"], row["relpages"],
                        row["relallvisible"]))
    stats = db.run(db.conn.fetch("""
        SELECT attname FROM pg_stats
         WHERE schemaname = current_schema() AND tablename = 'matches'"""))
    have = {r["attname"] for r in stats}
    for col in ("player1_id", "player2_id", "ended_at", "series_id", "id"):
        assert col in have, (col, sorted(have))
    lines.append("pg_stats matches columns: %s" % ", ".join(sorted(have)))
    # Ruling 5: the seat-pair statistics object exists and the fixture's
    # analysis built its most-common-values list.
    ext = db.run(db.conn.fetchrow("""
        SELECT kinds::text AS kinds, attnames::text AS attnames,
               cardinality(most_common_vals) AS items
          FROM pg_stats_ext
         WHERE statistics_schemaname = current_schema()
           AND statistics_name = 'stx_matches_pair'"""))
    assert ext is not None, "no pg_stats_ext row for stx_matches_pair"
    assert ext["kinds"] == "{m}", dict(ext)
    assert ext["attnames"] == "{player1_id,player2_id}", dict(ext)
    assert ext["items"] and ext["items"] > 0, dict(ext)
    lines.append("pg_stats_ext stx_matches_pair kinds=%s attnames=%s mcv_items=%d"
                 % (ext["kinds"], ext["attnames"], ext["items"]))
    _say("fixture statistics", lines)


@pytest.mark.parametrize("mode", MODES)
def test_r1_short_code_reads_the_shortcode_index(db, mode):
    s = db.seed
    gid = db.run(db.conn.fetchval(
        "SELECT id FROM matches WHERE player1_id = $1 AND player2_id = $2 LIMIT 1",
        s.D, s.R))
    code = gid.hex[:12]
    plan = db.run(_explain(db.conn, R1_CODE, {"code": code}, mode))
    nodes = [n for n, _ in _walk(plan)]
    scans = [n for n in nodes if n["Node Type"] in INDEX_SCANS + ("Bitmap Index Scan",)]
    assert [n["Index Name"] for n in scans] == ["idx_matches_shortcode"], nodes
    assert plan["Node Type"] == "Limit" and plan["Actual Rows"] <= 2
    assert db.run(_rows(db.conn, R1_CODE, {"code": code})) == [gid]
    _say("r1 code %s" % mode, ["rows=%d" % plan["Actual Rows"]])


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("which,count", [("S3", 3), ("S10", 10), ("S11", 11),
                                         ("S10000", 10000), ("SE", 10000)])
def test_r2_series_is_a_limit_directly_over_the_series_index(db, which, count, mode):
    """Series bound: 10 games render, 11 and 10,000 are too_large; the latter
    is a Limit directly over the index scan touching at most 11 index rows.
    SE shares one ended_at across its 10,000 games (equal timestamps)."""
    sid = getattr(db.seed, which)
    lim = SERIES_GAMES_MAX + 1
    params = {"sid": sid, "lim": lim}
    plan = db.run(_explain(db.conn, R2_SERIES, params, mode))
    assert plan["Node Type"] == "Limit", _compact(plan)
    child = plan["Plans"][0]
    assert child["Node Type"] in INDEX_SCANS, (
        "the series Limit sits over %r, not directly over the index scan\nPLAN:\n%s"
        % (child["Node Type"], _compact(plan)))
    lines = _gate(plan, branch_limit=lim, branches=1, equality=SERIES_EQUALITY)
    got = db.run(_rows(db.conn, R2_SERIES, params))
    want = db.run(_rows(db.conn, REF_SERIES, {"sid": sid}))[:lim]
    assert got == want
    assert len(got) == min(count, lim)
    too_large = len(got) > SERIES_GAMES_MAX
    assert too_large == (count > SERIES_GAMES_MAX)
    _say("r2 series %s %s" % (which, mode),
         lines + ["rows=%d too_large=%s" % (len(got), too_large)])


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("pair,games", [("DR", 3), ("DR", 10), ("PQ", 3), ("PQ", 30)])
def test_r3_pair_reads_both_orientations_over_the_pair_index(db, pair, games, mode):
    """Rare pair beside a 10,000-game distractor (DR), and 10,000 pair games
    sharing one ended_at (PQ)."""
    s = db.seed
    a, b = (s.D, s.R) if pair == "DR" else (s.P, s.Q)
    params = {"a": a, "b": b, "games": games}
    plan = db.run(_explain(db.conn, R3_PAIR, params, mode))
    lines = _gate(plan, branch_limit=games, branches=2)
    got = db.run(_rows(db.conn, R3_PAIR, params))
    assert got == db.run(_rows(db.conn, REF_PAIR, {"a": a, "b": b}))[:games]
    _say("r3 pair %s games=%d %s" % (pair, games, mode), lines)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("who,games", [("D", 10), ("D", 30), ("E", 3), ("E", 30)])
def test_r4_player_reads_both_seats_over_the_seat_order_indexes(db, who, games, mode):
    """The 10,000-game distractor (D), and 10,000 games sharing one ended_at (E)."""
    subject = getattr(db.seed, who)
    params = {"s": subject, "games": games}
    plan = db.run(_explain(db.conn, R4_PLAYER, params, mode))
    lines = _gate(plan, branch_limit=games, branches=2)
    got = db.run(_rows(db.conn, R4_PLAYER, params))
    assert got == db.run(_rows(db.conn, REF_PLAYER, {"s": subject}))[:games]
    _say("r4 player %s games=%d %s" % (who, games, mode), lines)


def _game_in_middle(db, sql, args):
    return db.run(db.conn.fetchrow(sql, *args))


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("who", ["D", "E"])
def test_seat_baseline_reads_scan_plus_one_before_the_game(db, who, mode):
    """Per seat subject, BASELINE_SCAN+1 eligible games before G over the seat
    order indexes; E's G shares its ended_at with 9,999 other E games."""
    subject = getattr(db.seed, who)
    g = _game_in_middle(db, """
        SELECT id, ended_at FROM matches
         WHERE player1_id = $1 OR player2_id = $1
         ORDER BY ended_at DESC, id DESC OFFSET 4000 LIMIT 1""", (subject,))
    scan = BASELINE_SCAN + 1
    params = {"s": subject, "g_ended": g["ended_at"], "g_id": g["id"], "scan": scan}
    plan = db.run(_explain(db.conn, SEAT_BASELINE, params, mode))
    lines = _gate(plan, branch_limit=scan, branches=2, time_bound=True)
    got = db.run(_rows(db.conn, SEAT_BASELINE, params))
    ref = db.run(db.conn.fetch("""
        SELECT id FROM matches
         WHERE (player1_id = $1 OR player2_id = $1) AND invalidated_at IS NULL
           AND (ended_at, id) < ($2, $3)
         ORDER BY ended_at DESC, id DESC LIMIT $4""",
                               subject, g["ended_at"], g["id"], scan))
    assert got == [r["id"] for r in ref]
    assert len(got) == scan
    _say("seat baseline %s %s" % (who, mode), lines)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("pair", ["DR", "PQ"])
def test_pair_global_baseline_reads_both_orientations_before_the_game(db, pair, mode):
    """Pair-global baseline over the pair index: the rare pair (3 games per
    orientation) and the equal-timestamp pair (G at the shared ended_at)."""
    s = db.seed
    a, b = (s.D, s.R) if pair == "DR" else (s.P, s.Q)
    g = _game_in_middle(db, """
        SELECT id, ended_at FROM matches
         WHERE (player1_id = $1 AND player2_id = $2) OR (player1_id = $2 AND player2_id = $1)
         ORDER BY ended_at DESC, id DESC OFFSET 1 LIMIT 1""", (a, b))
    scan = BASELINE_SCAN + 1
    params = {"a": a, "b": b, "g_ended": g["ended_at"], "g_id": g["id"], "scan": scan}
    plan = db.run(_explain(db.conn, PAIR_BASELINE, params, mode))
    lines = _gate(plan, branch_limit=scan, branches=2, time_bound=True)
    got = db.run(_rows(db.conn, PAIR_BASELINE, params))
    ref = db.run(db.conn.fetch("""
        SELECT id FROM matches
         WHERE ((player1_id = $1 AND player2_id = $2) OR (player1_id = $2 AND player2_id = $1))
           AND invalidated_at IS NULL AND (ended_at, id) < ($3, $4)
         ORDER BY ended_at DESC, id DESC LIMIT $5""",
                               a, b, g["ended_at"], g["id"], scan))
    assert got == [r["id"] for r in ref]
    assert len(got) == (4 if pair == "DR" else scan)
    _say("pair baseline %s %s" % (pair, mode), lines)


# ── Scratch cycle ──────────────────────────────────────────────────────────

async def _indexes(conn):
    rows = await conn.fetch("""
        SELECT ci.relname AS name, ci.oid::text AS oid,
               substr(pg_get_indexdef(i.indexrelid),
                      strpos(pg_get_indexdef(i.indexrelid), ' USING ') + 7) AS def
          FROM pg_index i
          JOIN pg_class ci ON ci.oid = i.indexrelid
          JOIN pg_namespace n ON n.oid = ci.relnamespace
         WHERE n.nspname = current_schema() AND ci.relname LIKE 'idx_matches_%'
         ORDER BY 1""")
    return {r["name"]: (r["oid"], r["def"]) for r in rows}


STATS = ("stx_matches_pair", "{m}", "{player1_id,player2_id}")


async def _statistics(conn):
    """The seat-pair statistics object from the catalog, with its OID:
    (oid, name, kinds, attnames, mcv items or None). The items come from
    `pg_stats_ext`, which lists an object only once an analysis of a
    non-empty table has built it."""
    row = await conn.fetchrow("""
        SELECT s.oid::text AS oid, s.stxname::text AS name, s.stxkind::text AS kinds,
               (SELECT array_agg(a.attname::text ORDER BY k.ord)
                  FROM unnest(s.stxkeys::int2[]) WITH ORDINALITY AS k(attnum, ord)
                  JOIN pg_attribute a ON a.attrelid = s.stxrelid AND a.attnum = k.attnum
               )::text AS attnames,
               cardinality(e.most_common_vals) AS items
          FROM pg_statistic_ext s
          JOIN pg_namespace n ON n.oid = s.stxnamespace
          LEFT JOIN pg_stats_ext e
                 ON e.statistics_schemaname = n.nspname AND e.statistics_name = s.stxname
         WHERE n.nspname = current_schema() AND s.stxname = 'stx_matches_pair'""")
    return None if row is None else tuple(row)


async def _cycle(prepare=""):
    conn = await asyncpg.connect(DSN)
    schema = "ae_cycle_%s" % uuid.uuid4().hex[:10]
    out = {"err": None}
    try:
        await conn.execute('CREATE SCHEMA "%s"' % schema)
        await conn.execute('SET search_path TO "%s"' % schema)
        await conn.execute(PREREQ)
        if prepare:
            await conn.execute(prepare)
        sql = MIGRATION.read_text(encoding="utf-8")
        try:
            await conn.execute(sql)
        except Exception as ex:
            out["err"] = "%s: %s" % (type(ex).__name__, ex)
            return out
        pg_indexes = await conn.fetch(
            "SELECT indexname, indexdef FROM pg_indexes "
            " WHERE schemaname = current_schema() AND tablename = 'matches'"
            "   AND indexname = ANY($1::text[]) ORDER BY 1", list(FOUR))
        out["listed"] = [tuple(r) for r in pg_indexes]
        out["first"] = await _indexes(conn)
        out["stats_first"] = await _statistics(conn)
        await conn.execute(sql)
        out["second"] = await _indexes(conn)
        out["stats_second"] = await _statistics(conn)
        return out
    finally:
        try:
            await conn.execute("ROLLBACK")
        except Exception:
            pass
        await conn.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % schema)
        await conn.close()


def test_scratch_cycle_apply_read_back_reapply_no_change():
    require_pg()
    loop = asyncio.new_event_loop()
    try:
        out = loop.run_until_complete(_cycle())
    finally:
        loop.close()
    assert out["err"] is None, out["err"]
    listed, first, second = out["listed"], out["first"], out["second"]
    assert [name for name, _ in listed] == sorted(FOUR), listed
    for name, want in FOUR.items():
        assert first[name][1] == want, (name, first[name][1])
    assert second == first, "a re-apply changed an index OID or definition"
    stats_first, stats_second = out["stats_first"], out["stats_second"]
    assert stats_first is not None, "the file left no statistics object stx_matches_pair"
    assert stats_first[1:4] == STATS, stats_first
    assert stats_second == stats_first, (
        "a re-apply changed the statistics object", stats_first, stats_second)
    print("GATE scratch cycle")
    for name, indexdef in listed:
        print("  pg_indexes %s: %s" % (name, indexdef))
    print("  pg_stats_ext %s kinds=%s attnames=%s" % stats_first[1:4])
    print("  re-apply: %d index OIDs and definitions and the statistics object "
          "OID %s unchanged" % (len(second), stats_second[0]))


def test_a_same_named_index_with_another_definition_aborts_the_file():
    """The guard alone would accept any relation of the name; the post-check
    refuses one whose definition differs, naming it."""
    require_pg()
    loop = asyncio.new_event_loop()
    try:
        err = loop.run_until_complete(_cycle(
            "CREATE INDEX idx_matches_p1_order ON matches (player1_id, ended_at DESC);"))["err"]
    finally:
        loop.close()
    assert err is not None and "idx_matches_p1_order" in err, err
    print("GATE same-named index refused: %s" % err.splitlines()[0])


def test_a_same_named_statistics_object_of_another_kind_aborts_the_file():
    """Ruling 5 kind mcv only: the guard alone would accept any statistics
    object of the name; the post-check refuses one of another kind."""
    require_pg()
    loop = asyncio.new_event_loop()
    try:
        err = loop.run_until_complete(_cycle(
            "CREATE STATISTICS stx_matches_pair (dependencies) "
            "ON player1_id, player2_id FROM matches;"))["err"]
    finally:
        loop.close()
    assert err is not None and "stx_matches_pair" in err, err
    print("GATE same-named statistics object refused: %s" % err.splitlines()[0])


def test_the_file_analyses_matches_after_creating_the_statistics_object():
    """Ruling 5: the file's own ANALYZE, inside its BEGIN and COMMIT, builds
    the object's most-common-values list on a loaded table, so production
    plans read the corrected estimate from the landing on, not from the next
    automatic analysis. Loaded here: 400 games, a quarter of them one pair."""
    require_pg()
    loop = asyncio.new_event_loop()
    try:
        out = loop.run_until_complete(_cycle("""
            INSERT INTO matches (player1_id, player2_id, ended_at)
            SELECT CASE WHEN i % 4 = 0 THEN '00000000-0000-4000-8000-00000000000a'::uuid
                        ELSE gen_random_uuid() END,
                   CASE WHEN i % 4 = 0 THEN '00000000-0000-4000-8000-00000000000b'::uuid
                        ELSE gen_random_uuid() END,
                   TIMESTAMPTZ '2026-01-01T00:00:00Z' + make_interval(mins => i)
              FROM generate_series(1, 400) AS i;"""))
    finally:
        loop.close()
    assert out["err"] is None, out["err"]
    stats = out["stats_first"]
    assert stats is not None and stats[1:4] == STATS, stats
    assert stats[4] and stats[4] > 0, (
        "the statistics object has no most-common-values list after the file "
        "ran over a loaded table: the file's ANALYZE did not build it", stats)
    print("GATE the file's ANALYZE built stx_matches_pair: mcv_items=%d" % stats[4])
