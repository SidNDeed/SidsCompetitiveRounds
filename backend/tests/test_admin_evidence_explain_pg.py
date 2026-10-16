"""Admin evidence report, phase 1a item 1: the order indexes, measured by plan.

Migration 377 adds four indexes on `matches` (design 7.1), each ending in the
`id` its ordering breaks ties on. Their whole purpose is a property of the
PLAN, so this module reads plans: every report read is run under
`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` against seeded fixtures (design 2.9)
and each gate requires

  * the named index, and no sequential or bitmap scan anywhere;
  * no Sort or Incremental Sort between an index scan and its branch Limit;
  * a merge above the two branches over at most twice the branch limit;
  * rows touched (actual rows plus rows removed by a filter or recheck) within
    the read's ceiling;
  * the same ids, in the same order, as a reference query with no LIMIT under
    the index (so a fast plan returning the wrong rows is red too).

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
indexes are read back from `pg_indexes`, the file is applied again and must
leave every index OID and definition unchanged; a same-named index with
another definition must abort the file.

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
    await conn.execute("ANALYZE matches; ANALYZE ranked_series;")
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
        raise AssertionError("%s\nPLAN:\n%s" % (ex, _compact(plan))) from None


def _gate_checks(plan, *, indexes, branch_limit, branches):
    """The design 2.9 gate over one plan; returns lines for the step log."""
    nodes = list(_walk(plan))
    kinds = [n["Node Type"] for n, _ in nodes]
    assert "Seq Scan" not in kinds, "sequential scan in the plan: %r" % kinds
    assert not [k for k in kinds if k.startswith("Bitmap")], (
        "bitmap scan in the plan (order lost): %r" % kinds)
    scans = [(n, p) for n, p in nodes if n["Node Type"] in INDEX_SCANS]
    used = sorted(n["Index Name"] for n, _ in scans)
    assert used == sorted(indexes), "indexes used %r, required %r" % (used, sorted(indexes))
    assert len(scans) == branches, "%d index scans for %d branches" % (len(scans), branches)
    lines = []
    for node, path in scans:
        between = []
        for anc in reversed(path):
            if anc["Node Type"] == "Limit":
                break
            between.append(anc["Node Type"])
        else:
            raise AssertionError("index scan %s has no Limit above it"
                                 % node["Index Name"])
        assert not [k for k in between if k in SORTS], (
            "%s: %r between the index scan and its Limit"
            % (node["Index Name"], between))
        touched = _touched(node)
        assert touched <= branch_limit, (
            "%s touched %d rows, ceiling %d" % (node["Index Name"], touched, branch_limit))
        lines.append("%s touched=%d ceiling=%d between=%r shared_hit=%s read=%s"
                     % (node["Index Name"], touched, branch_limit, between,
                        node.get("Shared Hit Blocks"), node.get("Shared Read Blocks")))
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
    lines = _gate(plan, indexes=["idx_matches_series"], branch_limit=lim, branches=1)
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
    lines = _gate(plan, indexes=["idx_matches_pair", "idx_matches_pair"],
                  branch_limit=games, branches=2)
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
    lines = _gate(plan, indexes=["idx_matches_p1_order", "idx_matches_p2_order"],
                  branch_limit=games, branches=2)
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
    lines = _gate(plan, indexes=["idx_matches_p1_order", "idx_matches_p2_order"],
                  branch_limit=scan, branches=2)
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
    lines = _gate(plan, indexes=["idx_matches_pair", "idx_matches_pair"],
                  branch_limit=scan, branches=2)
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


async def _cycle(prepare=""):
    conn = await asyncpg.connect(DSN)
    schema = "ae_cycle_%s" % uuid.uuid4().hex[:10]
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
            return None, None, "%s: %s" % (type(ex).__name__, ex)
        pg_indexes = await conn.fetch(
            "SELECT indexname, indexdef FROM pg_indexes "
            " WHERE schemaname = current_schema() AND tablename = 'matches'"
            "   AND indexname = ANY($1::text[]) ORDER BY 1", list(FOUR))
        first = await _indexes(conn)
        await conn.execute(sql)
        second = await _indexes(conn)
        return [tuple(r) for r in pg_indexes], (first, second), None
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
        listed, (first, second), err = loop.run_until_complete(_cycle())
    finally:
        loop.close()
    assert err is None, err
    assert [name for name, _ in listed] == sorted(FOUR), listed
    for name, want in FOUR.items():
        assert first[name][1] == want, (name, first[name][1])
    assert second == first, "a re-apply changed an index OID or definition"
    print("GATE scratch cycle")
    for name, indexdef in listed:
        print("  pg_indexes %s: %s" % (name, indexdef))
    print("  re-apply: %d index OIDs and definitions unchanged" % len(second))


def test_a_same_named_index_with_another_definition_aborts_the_file():
    """The guard alone would accept any relation of the name; the post-check
    refuses one whose definition differs, naming it."""
    require_pg()
    loop = asyncio.new_event_loop()
    try:
        _listed, _states, err = loop.run_until_complete(_cycle(
            "CREATE INDEX idx_matches_p1_order ON matches (player1_id, ended_at DESC);"))
    finally:
        loop.close()
    assert err is not None and "idx_matches_p1_order" in err, err
    print("GATE same-named index refused: %s" % err.splitlines()[0])
