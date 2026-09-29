"""The session report route against a REAL PostgreSQL (board rows 30a, 30d).

One test per selector - series, match, session, sitting (all four anchor
kinds) and lobby - over one seeded world: a ranked 1v1 series and a casual
1v1 sitting of the same pair, a 2v2 series, a 1v2 series and a three-game FFA
lobby, plus the decoys each selector must leave out (a later sitting, another
pair, another lobby, a game the caller sat out). test_session_report.py pins
the statements' predicates on a scripted session; this file proves the
statements RUN against the production schema and return the sets those
predicates promise.

THE SCHEMA is rebuilt from the repository in three steps: the ORM's shape
of the tables 001_schema.sql creates (production's early tables came from the
ORM before 001 documented them - 001's own matches table lacks columns no
later migration adds - and test_the_schema_replay_is_named checks that every
one of them is an ORM table); then every later numbered migration in order, so
a table a migration CREATES carries that migration's SQL defaults and checks
(an ORM-first build gave shop_items a created_at with no default, which failed
216 and silently took ffa_match_players.end_stats with it); then the ORM's
remaining tables, the early tables' foreign keys to tables a migration created
(players references shop_items, which 021 creates - those keys are held back
from the first step and added here, once each), and one retry pass over the
files that failed. An ORM column still missing at the end is reported as a
failure of its own ("orm-columns"). The files
that still fail are data seeds, cosmetic releases and backfills that need rows
this world does not have (36 of them at this lane's base: cosmetic releases,
translation seeds, grants and backfills); the replay test prints each with its
error. Column census against production (sql-readonly, 2026-09-28, the 18
tables the report reads, compared by name, type, nullability and length): 528
columns identical, four production gained after this lane's base
(players.pc_trades_*, team_series.dc_fallback_*) and two this lane's base adds
that production has not applied yet (players.mail_discord_relay,
team_series.first_game_nonce), with varchar/text and double/real differences
on four matches/ranked_series columns the report does not read
(invalidation_reason, p1/p2_freeze_total_sec). The ORM's early tables have no SQL default on a column a
later migration added with one (the ORM already made it), so _ins applies the
ORM's scalar default the way an ORM insert does.

The lab is the `public` schema of a database of its own, as in production:
migrations post-check information_schema both ways - 167 counts its new
ffa_match_players columns in EVERY schema (a second copy of the table anywhere
in the database fails it), 216 counts its end_stats columns in schema 'public'
only (a lab in any other schema fails it) - so the lab refuses to build while
any other schema holds tables, and every file that does not apply is kept with
its error for the replay test to print. The build costs one btree fsync per
index, which on a busy seat is minutes, so it is done ONCE per migration set:
public.sr_lab_ready records the hash of the migration files and models.py it
was built from, and a build of any other hash (or an interrupted one, which
has no mark) is dropped with the schema and rebuilt.
Every run seeds its own players (fresh steam ids)
and games (fresh uuids), and every report statement is scoped by the caller's
player id and the selector's key, so an earlier run's rows are never in a
later run's sets. Drop the database to clean up.

RUNNING IT
    SESSION_REPORT_TEST_PG_DSN=postgresql+asyncpg://postgres@127.0.0.1:55432/scratch_sr_report
    python -m pytest backend/tests/test_session_report_pg.py -q
The DSN must name a database on this machine called scratch*/test*.
SESSION_REPORT_TESTS_REQUIRED=1 makes "no DSN" a failure instead of a skip.
SESSION_REPORT_ENVELOPE_DUMP=<dir> writes every envelope a test reads to
<dir>/<nnn>_<test>__<selector>.json (nnn = the call's order in the run) in
the wire form FastAPI sends (compact, UTF-8):
the client harness's parse cases (tools/client-rules-harness,
SessionReportRulesSelfTest.cs) are envelopes captured this way, so the client
parser is executed against what this route actually produces.
"""
import asyncio
import hashlib
import itertools
import json
import os
import random
import re
import urllib.parse as _urlparse
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

import main
import models

try:
    import asyncpg
except ImportError:                                    # pragma: no cover
    asyncpg = None

DSN_VAR = "SESSION_REPORT_TEST_PG_DSN"
_RAW_DSN = (os.environ.get(DSN_VAR) or "").strip()
REQUIRED = os.environ.get("SESSION_REPORT_TESTS_REQUIRED") == "1"

if REQUIRED and not _RAW_DSN:
    raise RuntimeError(
        "SESSION_REPORT_TESTS_REQUIRED=1 but %s is unset -- refusing to report a "
        "green run for tests that would not run. Check the variable NAME." % DSN_VAR)


def _refuse_unless_throwaway(dsn):
    """These tests create and drop whole schemas: the DSN must name a
    disposable database on this machine before anything runs."""
    parsed = _urlparse.urlsplit(dsn)
    try:
        host = (parsed.hostname or "").lower()
    except ValueError:
        host = "?"
    if host not in ("", "localhost", "127.0.0.1", "::1"):
        raise RuntimeError("%s points at host %r; these tests run against a database "
                           "on this machine only." % (DSN_VAR, host))
    name = (parsed.path or "").lstrip("/").split("?")[0].strip().lower()
    if not (name.startswith("scratch") or name.startswith("test")):
        raise RuntimeError("%s names database %r; these tests run only against a "
                           "database named scratch*/test*." % (DSN_VAR, name))


if _RAW_DSN:
    _refuse_unless_throwaway(_RAW_DSN)

PLAIN_DSN = _RAW_DSN.replace("postgresql+asyncpg://", "postgresql://")
ASYNC_DSN = PLAIN_DSN.replace("postgresql://", "postgresql+asyncpg://", 1)

pytestmark = pytest.mark.skipif(
    not _RAW_DSN or asyncpg is None,
    reason="%s unset (or asyncpg missing): the live session report checks" % DSN_VAR)

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"
UTC = timezone.utc
T0 = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)

# -- the world ----------------------------------------------------------------

# fresh identities every run (the lab schema is kept between runs, see above)
STEAM = {k: "7656119%010d" % random.randrange(10 ** 10) for k in ("A", "B", "C", "D", "E", "Z")}
assert len(set(STEAM.values())) == len(STEAM)
NAME = {"A": "Alpha", "B": "Bravo", "C": "Charlie", "D": "Delta", "E": "Echo", "Z": "Zulu"}
PID = {k: str(uuid.uuid4()) for k in STEAM}
ID = {k: str(uuid.uuid4()) for k in (
    "RS1", "R1", "R2", "R3",                  # ranked 1v1 series A-B
    "S1", "K1", "K2", "K3", "KC", "KL",       # casual 1v1: session S1, a third game, A-C, a later sitting
    "TS1", "TM1", "TM2",                      # 2v2 series (A, C) v (B, D)
    "OS1", "OM1", "OM2",                      # 1v2 series: A solo v B + C
    "L1", "L2", "F1", "F2", "F3", "F4", "F5", "F6", "F7")}   # FFA lobbies and games


def _minutes(m):
    return T0 + timedelta(minutes=m)


def _v1_timeline(rounds, step=6.0):
    """[(winner 'a'|'b', loser_scored_first bool), ...] -> (point_timeline,
    point_times, points a, points b): the recorder's cumulative
    `rounds*2 + points` per event (GameStateWatcher.cs), a point at every
    `step` seconds."""
    ra = rb = pa = pb = 0
    tl, times, t = [], [], 0.0
    won = {"a": 0, "b": 0}

    def event(side):
        nonlocal ra, rb, pa, pb, t
        t += step
        won[side] += 1
        if side == "a":
            pa += 1
            if pa == 2:
                ra, pa, pb = ra + 1, 0, 0
        else:
            pb += 1
            if pb == 2:
                rb, pa, pb = rb + 1, 0, 0
        tl.append("%d:%d" % (ra * 2 + pa, rb * 2 + pb))
        times.append("%g" % t)

    for winner, loser_first in rounds:
        loser = "b" if winner == "a" else "a"
        if loser_first:
            event(loser)
        event(winner)
        event(winner)
    return ",".join(tl), ",".join(times), won["a"], won["b"]


# A beats B 5-3, B beats A 5-2, A beats B 5-4 (the ranked series); two casual games.
V1_GAMES = {
    "R1": ("A", "B", 0, [("a", False), ("b", True), ("a", True), ("a", False), ("b", False),
                         ("b", True), ("a", False), ("a", True)], "RS1", None, True),
    "R2": ("B", "A", 12, [("a", False), ("a", True), ("b", False), ("a", False), ("a", True),
                          ("b", True), ("a", False)], "RS1", None, True),
    "R3": ("A", "B", 24, [("b", False), ("a", True), ("b", False), ("a", False), ("b", True),
                          ("a", False), ("b", False), ("a", True), ("a", False)], "RS1", None, True),
    "K1": ("A", "B", 40, [("a", False)] * 5, None, "S1", False),
    "K2": ("B", "A", 50, [("b", False)] * 3 + [("a", False)] * 5, None, "S1", False),
    "K3": ("A", "B", 60, [("a", True)] * 5, None, None, False),
    "KC": ("A", "C", 45, [("a", False)] * 5, None, "S1", False),    # a different pair, same uuid
    "KL": ("A", "B", 60 * 7, [("a", False)] * 5, None, None, False),  # A's NEXT sitting
}

# FFA: lobby L1 (score target 3, recorded settings) hosts F1, F2, F3 inside A's
# sitting; C plays F1 only (an absent row in F2), D joins at F2, E at F3. F4
# is L1 again in A's next sitting, F5 another lobby, F6 an L1 game A sat out
# after the sitting's last game, F7 one A sat out INSIDE the sitting's span -
# only the per-game participant predicate keeps F7 out, never the span.
FFA_GAMES = {
    "F1": ("L1", 100, "0,0R,1,1R,0,2,0R,0,0R",
           [("A", 0, 1, 3), ("B", 1, 2, 1), ("C", 2, 3, 0)], []),
    "F2": ("L1", 110, "1,1R,0,0R,1,1R,3,1,1R",
           [("B", 1, 1, 3), ("A", 0, 2, 1), ("D", 3, 3, 0)], ["C"]),
    "F3": ("L1", 120, "4,0,0R,1,4,1R,0,0R,0,1,0R",
           [("A", 0, 1, 3), ("B", 1, 2, 1), ("D", 3, 3, 0), ("E", 4, 4, 0)], []),
    "F4": ("L1", 60 * 7 + 20, "0,0R,0,0R,0,0R", [("A", 0, 1, 3), ("B", 1, 2, 0)], []),
    "F5": ("L2", 115, "0,0R,0,0R,0,0R", [("A", 0, 1, 3), ("Z", 1, 2, 0)], []),
    "F6": ("L1", 130, "1,1R,1,1R,1,1R", [("B", 1, 1, 3), ("D", 3, 2, 0)], ["A"]),
    "F7": ("L1", 116, "1,1R,1,1R,1,1R", [("B", 1, 1, 3), ("D", 3, 2, 0)], ["A"]),
}
# game numbers inside each lobby (ffa_matches.game_number, 1..999, migration 327)
FFA_GAME_NO = {"F1": 1, "F2": 2, "F3": 3, "F6": 4, "F4": 5, "F7": 6, "F5": 1}
FFA_RATING = {"F1": {"A": (1500.0, 1512.0), "B": (1500.0, 1495.0), "C": (1500.0, 1490.0)},
              "F2": {"A": (1512.0, 1508.0), "B": (1495.0, 1507.0), "D": (1500.0, 1491.0)},
              "F3": {"A": (1508.0, 1519.5), "B": (1507.0, 1503.0), "D": (1491.0, 1486.0),
                     "E": (1500.0, 1492.0)}}


# -- the schema ---------------------------------------------------------------

def _migration_files():
    files = [p for p in SQL_DIR.iterdir() if re.match(r"^\d{3}_.*\.sql$", p.name)]
    return sorted(files, key=lambda p: (int(p.name[:3]), p.name))


_BUILD_VERSION = "public; orm 001-tables (held-back fks), 002+, orm rest, fks, one retry pass, errors kept, v5"
LAB_SCHEMA = "public"

_FK_DEFS_SQL = """
    SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c
      JOIN pg_class r ON r.oid = c.conrelid
     WHERE c.contype = 'f' AND r.relname = $1 AND r.relnamespace = to_regnamespace(current_schema())
"""


def _fk_target(fkc):
    return fkc.elements[0].target_fullname.rsplit(".", 1)[0]


def _fk_signature(fkc):
    return "FOREIGN KEY (%s) REFERENCES %s(" % (
        ", ".join(e.parent.name for e in fkc.elements), _fk_target(fkc))

_STRAY_SQL = """
    SELECT DISTINCT table_schema FROM information_schema.tables
     WHERE table_schema NOT IN ('pg_catalog', 'information_schema') AND table_schema <> $1
"""


def _build_hash():
    h = hashlib.sha1(_BUILD_VERSION.encode())
    for p in _migration_files():
        h.update(p.name.encode())
        h.update(p.read_bytes())
    h.update(Path(models.__file__).read_bytes())
    return h.hexdigest()[:12]


def _tables_001_creates():
    text = _migration_files()[0].read_text(encoding="utf-8")
    return sorted(set(m.group(1).lower() for m in re.finditer(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)", text, re.I)))


async def _ensure_schema():
    """The kept lab for this migration set, rebuilt when its mark is absent
    (never built, or an interrupted build) or names another hash. Returns
    (schema, {file: error} for the files that did not apply)."""
    schema, build = LAB_SCHEMA, _build_hash()
    conn = await asyncpg.connect(PLAIN_DSN)
    try:
        stray = sorted(r[0] for r in await conn.fetch(_STRAY_SQL, schema))
        assert not stray, (
            "the report lab needs a database of its own: schema(s) %s hold tables, and "
            "migrations that post-check information_schema fail beside a second copy of "
            "their table - drop those schemas' tables first" % stray)
        if await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", schema + ".sr_lab_ready"):
            rows = await conn.fetch('SELECT build, name, error FROM "%s".sr_lab_ready' % schema)
            if rows and all(r["build"] == build for r in rows):
                return schema, {r["name"]: r["error"] for r in rows if r["name"] is not None}
    finally:
        await conn.close()
    failed = await _build_schema(schema)
    conn = await asyncpg.connect(PLAIN_DSN)
    try:
        # the mark: one row naming no file (the build is complete) plus one
        # row per file that did not apply, every row carrying the build hash
        await conn.execute('CREATE TABLE "%s".sr_lab_ready (build text NOT NULL, name text, error text)' % schema)
        await conn.executemany('INSERT INTO "%s".sr_lab_ready (build, name, error) VALUES ($1, $2, $3)' % schema,
                               [(build, None, None)] + [(build, n, e) for n, e in sorted(failed.items())])
    finally:
        await conn.close()
    return schema, failed


async def _build_schema(schema):
    """The ORM's shape of 001's tables, every migration after 001, the
    ORM's remaining tables, one retry pass. Returns {file name: its error}
    for the files that still fail."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool
    files = _migration_files()
    conn = await asyncpg.connect(PLAIN_DSN)
    try:
        await conn.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % schema)
        await conn.execute('CREATE SCHEMA "%s"' % schema)
    finally:
        await conn.close()
    from sqlalchemy.schema import CreateIndex, CreateTable
    md = models.Base.metadata
    early_names = set(_tables_001_creates()) & set(md.tables)
    early = [t for t in md.sorted_tables if t.name in early_names]
    held_back = []

    def _early_ddl(sc):
        for t in early:
            inline = []
            for fkc in t.foreign_key_constraints:
                (inline if _fk_target(fkc) in early_names else held_back).append(fkc)
            sc.execute(CreateTable(t, include_foreign_key_constraints=inline))
            for ix in t.indexes:
                sc.execute(CreateIndex(ix))

    async def _orm(fn):
        engine = create_async_engine(ASYNC_DSN, poolclass=NullPool,
                                     connect_args={"server_settings": {"search_path": schema}})
        try:
            async with engine.begin() as c:
                await c.run_sync(fn)
        finally:
            await engine.dispose()

    await _orm(_early_ddl)
    conn = await asyncpg.connect(PLAIN_DSN, server_settings={"search_path": schema})
    try:
        failed = {}
        for path in files[1:]:
            err = await _run_file(conn, path)
            if err is not None:
                failed[path] = err
        await _orm(md.create_all)    # the ORM tables no migration created (checkfirst)
        extra = {}
        for fkc in held_back:
            have = [r[0] for r in await conn.fetch(_FK_DEFS_SQL, fkc.table.name)]
            if any(d.startswith(_fk_signature(fkc)) for d in have):
                continue
            ddl = "ALTER TABLE %s ADD %s" % (fkc.table.name, _fk_signature(fkc)[:-1] + "(%s)" % ", ".join(
                e.column.name if e.column is not None else e.target_fullname.rsplit(".", 1)[1]
                for e in fkc.elements))
            if fkc.ondelete:
                ddl += " ON DELETE " + fkc.ondelete
            try:
                await conn.execute(ddl)
            except Exception as exc:
                extra["orm-fk:%s.%s" % (fkc.table.name, fkc.elements[0].parent.name)] = str(exc).splitlines()[0][:300]
        for path in list(failed):
            err = await _run_file(conn, path)
            if err is None:
                del failed[path]
            else:
                failed[path] = err
        missing = []
        for t in md.sorted_tables:
            got = {r[0] for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = $1", t.name)}
            missing += ["%s.%s" % (t.name, c.name) for c in t.columns if c.name not in got]
        if missing:
            extra["orm-columns"] = ", ".join(missing)[:300]
        out = {p.name: e for p, e in failed.items()}
        out.update(extra)
        return out
    finally:
        await conn.close()


async def _run_file(conn, path):
    """None when the file applied, else the first line of its error."""
    try:
        await conn.execute(path.read_text(encoding="utf-8"))
        return None
    except Exception as exc:
        try:
            await conn.execute("ROLLBACK")
        except Exception:
            pass
        return ("%s: %s" % (type(exc).__name__, exc)).splitlines()[0][:300]


_REQUIRED_COLS = """
    SELECT c.column_name, c.data_type, c.udt_name, c.character_maximum_length
      FROM information_schema.columns c
     WHERE c.table_schema = current_schema() AND c.table_name = $1
       AND c.is_nullable = 'NO' AND c.column_default IS NULL
       AND c.is_identity = 'NO' AND c.is_generated = 'NEVER'
"""


async def _ins(conn, table, **vals):
    """INSERT one row; every NOT NULL column without a SQL default that the
    seed does not name gets the ORM's scalar default when the model declares
    one (what an ORM insert sends), else a filler of its type (unique text,
    zero, false, T0)."""
    orm = models.Base.metadata.tables.get(table)
    for r in await conn.fetch(_REQUIRED_COLS, table):
        col = r["column_name"]
        if col in vals:
            continue
        ocol = orm.columns.get(col) if orm is not None else None
        odef = getattr(ocol, "default", None)
        if odef is not None and getattr(odef, "is_scalar", False):
            vals[col] = odef.arg
            continue
        dt, udt = r["data_type"], r["udt_name"]
        if dt == "uuid":
            vals[col] = uuid.uuid4()
        elif dt in ("text", "character varying", "character"):
            filler = "f" + uuid.uuid4().hex[:15]
            vals[col] = filler[: r["character_maximum_length"]] if r["character_maximum_length"] else filler
        elif dt in ("integer", "smallint", "bigint", "numeric", "real", "double precision"):
            vals[col] = 0
        elif dt == "boolean":
            vals[col] = False
        elif dt.startswith("timestamp"):
            vals[col] = T0
        elif dt == "date":
            vals[col] = T0.date()
        elif dt in ("json", "jsonb"):
            vals[col] = "{}"
        elif dt == "ARRAY":
            vals[col] = []
        else:
            raise AssertionError("no filler for %s.%s (%s/%s)" % (table, col, dt, udt))
    cols = list(vals)
    types = {r["column_name"]: r["data_type"] for r in await conn.fetch(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = $1", table)}
    missing = [c for c in cols if c not in types]
    assert not missing, "%s has no column(s) %s" % (table, missing)
    args = []
    for c in cols:
        v = vals[c]
        if types[c] == "uuid" and isinstance(v, str):
            v = uuid.UUID(v)
        elif types[c] == "ARRAY" and isinstance(v, list):
            v = [uuid.UUID(x) if isinstance(x, str) and len(x) == 36 else x for x in v]
        args.append(v)
    sql = 'INSERT INTO "%s" (%s) VALUES (%s)' % (
        table, ", ".join('"%s"' % c for c in cols), ", ".join("$%d" % (i + 1) for i in range(len(cols))))
    await conn.execute(sql, *args)


async def _seed(schema):
    conn = await asyncpg.connect(PLAIN_DSN, server_settings={"search_path": schema})
    try:
        for k in STEAM:
            await _ins(conn, "players", id=PID[k], steam_id=STEAM[k], display_name=NAME[k])
        # ranked 1v1 series A-B (player order B, A: the series row's own order)
        await _ins(conn, "ranked_series", id=ID["RS1"], player1_id=PID["B"], player2_id=PID["A"],
                   status="completed", completed_at=_minutes(36), created_at=_minutes(0),
                   p1_rating_change=-11.5, p2_rating_change=11.5)
        await _ins(conn, "rating_history", player_id=PID["A"], rating=1611.5,
                   series_id=ID["RS1"], period_end=_minutes(36))
        await _ins(conn, "rating_history", player_id=PID["B"], rating=1488.5,
                   series_id=ID["RS1"], period_end=_minutes(36))
        for key, (p1, p2, minute, rounds, series, session, ranked) in V1_GAMES.items():
            tl, times, pa, pb = _v1_timeline(rounds)
            ra = sum(1 for w, _ in rounds if w == "a")
            rb = len(rounds) - ra
            dur = int(float(times.split(",")[-1])) + 4
            start = _minutes(minute)
            await _ins(conn, "matches", id=ID[key], is_ranked=ranked,
                       series_id=ID[series] if series else None,
                       session_uuid=ID[session] if session else None,
                       started_at=start, ended_at=start + timedelta(seconds=dur), created_at=start,
                       duration_seconds=dur, player1_id=PID[p1], player2_id=PID[p2],
                       winner_id=PID[p1] if ra > rb else PID[p2],
                       p1_rounds_won=ra, p2_rounds_won=rb, p1_points_total=pa, p2_points_total=pb,
                       point_timeline=tl, point_times=times,
                       p1_damage_timeline="0,150,300,420", p2_damage_timeline="0,90,200,260",
                       p1_hit_timeline="10:4,20:9,30:15", p2_hit_timeline="12:3,24:8,36:10",
                       p1_block_timeline="2:1,4:3,6:4", p2_block_timeline="1:0,2:1,3:1",
                       p1_bullets_fired=30, p1_bullets_hit=15, p1_blocks_activated=6,
                       p1_blocks_successful=4, p1_damage_dealt=420, p1_deaths=rb * 2,
                       p2_bullets_fired=36, p2_bullets_hit=10, p2_blocks_activated=3,
                       p2_blocks_successful=1, p2_damage_dealt=260, p2_deaths=ra * 2,
                       p1_xp_gained=40 + ra, p2_xp_gained=30 + rb)
            await _ins(conn, "gold_transactions", player_id=PID[p1], amount=2, reason="xp",
                       reference_id=ID[key], created_at=start)
        await _ins(conn, "match_cards", match_id=ID["R1"], player_id=PID["A"], card_name="BombsAway",
                   pick_order=1, round_number=1)
        await _ins(conn, "match_cards", match_id=ID["R1"], player_id=PID["B"], card_name="Leach",
                   pick_order=1, round_number=1)
        await _ins(conn, "gold_transactions", player_id=PID["A"], amount=25, reason="series_win",
                   reference_id=ID["RS1"], created_at=_minutes(36))
        await _ins(conn, "gold_transactions", player_id=PID["B"], amount=5, reason="series_loss",
                   reference_id=ID["RS1"], created_at=_minutes(36))

        # 2v2 series: (A, C) v (B, D)
        await _ins(conn, "team_series", id=ID["TS1"], t1a_id=PID["A"], t1b_id=PID["C"],
                   t2a_id=PID["B"], t2b_id=PID["D"], status="completed", completed_at=_minutes(80),
                   created_at=_minutes(66), t1a_rating_change=9.0, t1b_rating_change=9.0,
                   t2a_rating_change=-9.0, t2b_rating_change=-9.0,
                   t1a_xp_earned=120, t1b_xp_earned=110, t2a_xp_earned=90, t2b_xp_earned=95)
        for key, minute, r1, r2 in (("TM1", 66, 5, 3), ("TM2", 73, 5, 2)):
            start = _minutes(minute)
            await _ins(conn, "team_matches", id=ID[key], series_id=ID["TS1"], started_at=start,
                       ended_at=start + timedelta(seconds=300), duration_seconds=300,
                       t1a_id=PID["A"], t1b_id=PID["C"], t2a_id=PID["B"], t2b_id=PID["D"],
                       t1_rounds_won=r1, t2_rounds_won=r2, t1_points_total=r1 * 2,
                       t2_points_total=r2 * 2, winner_team=1)
            await _ins(conn, "team_match_telemetry", match_id=ID[key], player_id=PID["A"],
                       fps_timeline="60,61", hit_timeline="5:2,10:6", damage_dealt_timeline="0,300",
                       bullets_fired=10, bullets_hit=6, keys_pressed=80, active_seconds=200.0)
            await _ins(conn, "gold_transactions", player_id=PID["A"], amount=1, reason="team_xp",
                       reference_id=ID[key], created_at=start)

        # 1v2 series: A solo v B + C
        await _ins(conn, "ovt_series", id=ID["OS1"], solo_id=PID["A"], duo_a_id=PID["B"],
                   duo_b_id=PID["C"], status="completed", completed_at=_minutes(95),
                   created_at=_minutes(82), solo_rating_change=6.0, duo_a_rating_change=-3.0,
                   duo_b_rating_change=-3.0, solo_gold_earned=3, duo_a_gold_earned=1,
                   duo_b_gold_earned=1, solo_xp_earned=70, duo_a_xp_earned=50, duo_b_xp_earned=55)
        for key, minute, rs, rd in (("OM1", 82, 5, 4), ("OM2", 88, 3, 5)):
            start = _minutes(minute)
            await _ins(conn, "ovt_matches", id=ID[key], series_id=ID["OS1"], solo_id=PID["A"],
                       duo_a_id=PID["B"], duo_b_id=PID["C"], solo_rounds_won=rs, duo_rounds_won=rd,
                       solo_points_total=rs * 2, duo_points_total=rd * 2,
                       winner_side=1 if rs > rd else 2, duration_seconds=240, started_at=start,
                       ended_at=start + timedelta(seconds=240), created_at=start,
                       solo_damage_timeline="0,200,380")

        # FFA lobbies and games
        for lob, target in (("L1", 3), ("L2", 3)):
            await _ins(conn, "ffa_lobbies", id=ID[lob], status="completed",
                       member_ids=[PID[k] for k in ("A", "B", "C", "D", "E")],
                       score_target=target, card_cap=5, initial_picks=1, card_candidates=5,
                       same_card_rule=False, sudden_death=False, settings_known=True,
                       created_at=_minutes(99))
        for key, (lob, minute, timeline, rows, absent) in FFA_GAMES.items():
            start = _minutes(minute)
            await _ins(conn, "ffa_matches", id=ID[key], lobby_id=ID[lob], player_count=len(rows),
                       game_number=FFA_GAME_NO[key],
                       winner_id=PID[[r for r in rows if r[2] == 1][0][0]], duration_seconds=200,
                       started_at=start, ended_at=start + timedelta(seconds=200), created_at=start,
                       timeline=timeline)
            for who, slot, placement, rounds in rows:
                rb_ra = FFA_RATING.get(key, {}).get(who)
                await _ins(conn, "ffa_match_players", match_id=ID[key], player_id=PID[who],
                           slot=slot, placement=placement, rounds_won=rounds, points_total=rounds * 2,
                           rating_before=rb_ra[0] if rb_ra else None,
                           rating_after=rb_ra[1] if rb_ra else None,
                           rating_change=(rb_ra[1] - rb_ra[0]) if rb_ra else None,
                           xp_gained=20 + rounds, gold_gained=3 if placement == 1 else 1,
                           absent=False, kills=rounds, damage_dealt=100 * (rounds + 1),
                           kill_timeline="0,%d" % rounds)
                await _ins(conn, "ffa_match_cards", match_id=ID[key], player_id=PID[who],
                           card_name="Card%s%d" % (who, slot), pick_order=1, round_number=1,
                           rolled=False)
                await _ins(conn, "gold_transactions", player_id=PID[who],
                           amount=3 if placement == 1 else 1,
                           reason="ffa_placement" if placement == 1 else "ffa_xp",
                           reference_id=ID[key], created_at=start)
            for who in absent:
                await _ins(conn, "ffa_match_players", match_id=ID[key], player_id=PID[who],
                           slot=9, placement=9, rounds_won=0, points_total=0, absent=True)
    finally:
        await conn.close()


_LAB = {}


@pytest.fixture(scope="module", autouse=True)
def lab():
    if not _RAW_DSN or asyncpg is None:
        yield None
        return

    async def _up():
        schema, failed = await _ensure_schema()
        await _seed(schema)
        return schema, failed

    _LAB["schema"], _LAB["failed"] = asyncio.run(_up())
    yield _LAB


@pytest.fixture(autouse=True)
def session_ok(monkeypatch):
    async def _ok(request, steam_id, db):
        return steam_id in STEAM.values()
    monkeypatch.setattr(main, "_strict_steam_session_ok", _ok)


_DUMP_SEQ = itertools.count()


def _report(who, **sel):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    async def _go():
        engine = create_async_engine(ASYNC_DSN, poolclass=NullPool,
                                     connect_args={"server_settings": {"search_path": _LAB["schema"]}})
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                return await main.get_set_report(request=None, steam_id=STEAM.get(who, who), db=db, **sel)
        finally:
            await engine.dispose()
    env = asyncio.run(_go())
    dump = os.environ.get("SESSION_REPORT_ENVELOPE_DUMP", "")
    if dump:
        test = os.environ.get("PYTEST_CURRENT_TEST", "unnamed").split("::")[-1].split(" ")[0]
        name = "%03d_%s__%s.json" % (next(_DUMP_SEQ), test, "_".join(sorted(sel)))
        with open(os.path.join(dump, name), "w", encoding="utf-8", newline="") as fh:
            fh.write(json.dumps(env, separators=(",", ":"), ensure_ascii=False, default=str))
    return env


def _refused(who, **sel):
    with pytest.raises(HTTPException) as ei:
        _report(who, **sel)
    return ei.value.status_code, ei.value.detail


def _games(env):
    return [g["match_id"] for g in env["games"]]


def _ids(*keys):
    return [ID[k] for k in keys]


# -- the tests ----------------------------------------------------------------

def test_the_schema_replay_is_named(lab):
    """Not an assertion about the report: the files the replay could not apply
    to an empty world, printed so a reader of the log sees the schema's
    provenance. The report's own tables are asserted present."""
    print("schema replay: %d file(s) did not apply to an empty world:" % len(_LAB["failed"]))
    for name in sorted(_LAB["failed"]):
        print("  %s -- %s" % (name, _LAB["failed"][name]))
    orm = set(models.Base.metadata.tables)
    made_by_001 = _tables_001_creates()
    assert made_by_001, "the 001 table census found nothing: the census is broken"
    assert set(made_by_001) <= orm, (
        "001_schema.sql creates a table the ORM does not define - the replay builds 001's "
        "tables from the ORM's shape: %s" % sorted(set(made_by_001) - orm))
    for f in ("120_1v2_schema.sql", "142_team_match_telemetry.sql", "154_ffa_schema.sql",
              "156_ffa_recent_panel.sql", "167_ffa_damage_kill_telemetry.sql",
              "176_ffa_lobby_config.sql", "216_end_stats_and_mode_podium_titles.sql",
              "298_matches_session_uuid.sql", "299_rating_history_series_id.sql",
              "306_room_rules.sql"):
        assert (SQL_DIR / f).exists(), "a migration the report depends on was renamed: " + f
        assert f not in _LAB["failed"], "a migration the report depends on did not apply: " + f


def test_series_selector(lab):
    env = _report("A", series=ID["RS1"])
    assert env["kind"] == "ranked" and _games(env) == _ids("R1", "R2", "R3")
    assert [p["id"] for p in env["players"]] == [STEAM["B"], STEAM["A"]]
    assert env["set_summary"]["rating"][STEAM["A"]] == {"before": 1600.0, "after": 1611.5, "delta": 11.5}
    assert env["set_summary"]["gold"] == {STEAM["A"]: 25, STEAM["B"]: 5}
    g1 = env["games"][0]
    assert g1["scores"] == {STEAM["A"]: 5, STEAM["B"]: 3}
    assert [p["card"] for p in g1["picks"]] == ["BombsAway", "Leach"]


def test_match_selector(lab):
    env = _report("A", match=ID["R2"])
    assert _games(env) == _ids("R2") and env["kind"] == "ranked"
    env = _report("A", match=ID["F2"])
    assert _games(env) == _ids("F2") and env["kind"] == "ffa"
    assert _refused("A", match=ID["F6"]) == (404, "not_found"), "a game A sat out"


def test_session_selector(lab):
    env = _report("A", session=ID["S1"])
    assert env["kind"] == "casual" and _games(env) == _ids("K1", "K2")
    assert env["games_omitted"] == 1, "the A-C game under the same uuid is left out and counted"


def test_sitting_on_a_1v1_game(lab):
    env = _report("A", sitting=ID["K2"])
    assert _games(env) == _ids("R1", "R2", "R3", "K1", "K2", "K3"), \
        "the pair's games inside A's sitting: not A-C, not the next sitting"
    assert env["kind"] == "casual"
    assert _games(_report("A", sitting=ID["KL"])) == _ids("KL"), "the next sitting is its own set"


def test_sitting_on_a_2v2_game_is_its_series(lab):
    env = _report("A", sitting=ID["TM2"])
    assert env["kind"] == "team" and _games(env) == _ids("TM1", "TM2")
    assert env == _report("A", series=ID["TS1"])
    assert env["set_summary"]["rating"][STEAM["C"]] == {"before": None, "after": None, "delta": 9.0}
    assert _refused("E", sitting=ID["TM1"]) == (404, "not_found")


def test_sitting_on_a_1v2_game_is_its_series(lab):
    env = _report("B", sitting=ID["OM1"])
    assert env["kind"] == "ovt" and _games(env) == _ids("OM1", "OM2")
    assert env == _report("B", series=ID["OS1"])
    assert {p["id"]: p["team"] for p in env["players"]} == {STEAM["A"]: 1, STEAM["B"]: 2, STEAM["C"]: 2}


def test_lobby_selector_is_every_game_of_the_lobby_sitting(lab):
    env = _report("A", lobby=ID["F2"])
    assert env["kind"] == "ffa"
    assert _games(env) == _ids("F1", "F2", "F3"), \
        "L1's games in A's sitting: not F4 (next sitting), F5 (other lobby), F6/F7 (A sat out)"
    assert env["games_omitted"] == 0 and env["truncated"] is False
    # the union roster: the newest game's players in placement order, then the
    # older games' newcomers
    assert [p["id"] for p in env["players"]] == [STEAM[k] for k in ("A", "B", "D", "E", "C")]
    by = {g["match_id"]: g for g in env["games"]}
    assert set(by[ID["F1"]]["scores"]) == {STEAM[k] for k in ("A", "B", "C")}
    assert set(by[ID["F2"]]["scores"]) == {STEAM[k] for k in ("A", "B", "D")}, \
        "C was absent from F2: no key, never a zero"
    assert set(by[ID["F3"]]["scores"]) == {STEAM[k] for k in ("A", "B", "D", "E")}
    assert by[ID["F1"]]["settings"]["score_target"] == 3
    assert sorted(p["card"] for p in by[ID["F3"]]["picks"]) == ["CardA0", "CardB1", "CardD3", "CardE4"]
    rating = env["set_summary"]["rating"]
    assert rating[STEAM["A"]] == {"before": 1500.0, "after": 1519.5, "delta": 19.5}
    assert rating[STEAM["C"]] == {"before": 1500.0, "after": 1490.0, "delta": -10.0}
    assert env["set_summary"]["gold"][STEAM["A"]] == 3 + 1 + 3
    # every game of the set anchors the same set; `sitting` on an FFA game is it
    assert env == _report("A", lobby=ID["F1"]) == _report("A", lobby=ID["F3"])
    assert env == _report("A", sitting=ID["F2"])


def test_lobby_selector_refusals_and_edges(lab):
    assert _games(_report("A", lobby=ID["F4"])) == _ids("F4"), "the next sitting's lobby game alone"
    assert _games(_report("C", lobby=ID["F1"])) == _ids("F1"), "C played F1 only"
    assert _refused("C", lobby=ID["F2"]) == (404, "not_found"), "C's absent row is not a game C played"
    assert _refused("A", lobby=ID["F6"]) == (404, "not_found")
    assert _refused("A", lobby=ID["F7"]) == (404, "not_found"), "sat out inside A's sitting"
    assert _refused("A", sitting=ID["F7"]) == (404, "not_found")
    assert _refused("Z", lobby=ID["F2"]) == (404, "not_found")
    assert _refused("A", lobby=str(uuid.uuid4())) == (404, "not_found")

def test_each_game_and_the_set_carry_what_was_earned(lab):
    """Board row 30d on the real schema: each game's own ledger gold and XP
    record, and the set totals, per mode."""
    env = _report("A", series=ID["RS1"])
    ss = env["set_summary"]
    exp_gold, exp_xp = {STEAM["A"]: 25, STEAM["B"]: 5}, {}
    for g in env["games"]:
        key = next(k for k in V1_GAMES if ID[k] == g["match_id"])
        p1, p2, _minute, rounds = V1_GAMES[key][:4]
        ra = sum(1 for w, _ in rounds if w == "a")
        rb = len(rounds) - ra
        assert g["gold"] == {STEAM[p1]: 2}, key
        assert g["xp"] == {STEAM[p1]: 40 + ra, STEAM[p2]: 30 + rb}, key
        exp_gold[STEAM[p1]] += 2
        for who, v in ((p1, 40 + ra), (p2, 30 + rb)):
            exp_xp[STEAM[who]] = exp_xp.get(STEAM[who], 0) + v
    assert ss["gold"] == {STEAM["A"]: 25, STEAM["B"]: 5}, "the award alone"
    assert ss["gold_total"] == exp_gold and ss["xp_total"] == exp_xp

    env = _report("A", series=ID["TS1"])
    assert [g["gold"] for g in env["games"]] == [{STEAM["A"]: 1}, {STEAM["A"]: 1}]
    assert all(g["xp"] == {} for g in env["games"]), "2v2 keeps no per-game XP record"
    assert env["set_summary"]["xp_total"] == {STEAM["A"]: 120, STEAM["C"]: 110,
                                               STEAM["B"]: 90, STEAM["D"]: 95}

    env = _report("A", series=ID["OS1"])
    assert env["set_summary"]["gold_total"] == {STEAM["A"]: 3, STEAM["B"]: 1, STEAM["C"]: 1}
    assert env["set_summary"]["xp_total"] == {STEAM["A"]: 70, STEAM["B"]: 50, STEAM["C"]: 55}

    env = _report("A", lobby=ID["F2"])
    tot_g, tot_x = {}, {}
    for g in env["games"]:
        key = next(k for k in FFA_GAMES if ID[k] == g["match_id"])
        rows = FFA_GAMES[key][3]
        want_g = {STEAM[w]: (3 if pl == 1 else 1) for w, _s, pl, _r in rows}
        want_x = {STEAM[w]: 20 + r for w, _s, _pl, r in rows}
        assert g["gold"] == want_g and g["xp"] == want_x, key
        for d, src in ((tot_g, want_g), (tot_x, want_x)):
            for k, v in src.items():
                d[k] = d.get(k, 0) + v
    assert env["set_summary"]["gold_total"] == env["set_summary"]["gold"] == tot_g
    assert env["set_summary"]["xp_total"] == tot_x


async def _watch(game_key, holder, roster_keys):
    """Round 2 M4: a spectate game around `game_key`'s end (from 5 min before
    it to 1 min after) whose roster is `roster_keys`' steam ids, and a revoked
    lease of `holder` on it - what the broadcast seat's grant leaves behind."""
    conn = await asyncpg.connect(PLAIN_DSN, server_settings={"search_path": _LAB["schema"]})
    try:
        end = await conn.fetchval("""
            SELECT ended_at FROM matches WHERE id = $1
            UNION ALL SELECT ended_at FROM team_matches WHERE id = $1
            UNION ALL SELECT ended_at FROM ovt_matches WHERE id = $1
            UNION ALL SELECT ended_at FROM ffa_matches WHERE id = $1""", uuid.UUID(ID[game_key]))
        assert end is not None, game_key
        wid = uuid.uuid4()
        await _ins(conn, "spectate_games", id=wid, mode="1v1", room_name="w" + wid.hex[:12],
                   roster=",".join(sorted(STEAM[k] for k in roster_keys)),
                   started_at=end - timedelta(minutes=5), ended_at=end + timedelta(minutes=1))
        await _ins(conn, "spectate_leases", game_id=wid, spectator_steam_id=holder,
                   token_hash=uuid.uuid4().hex, join_expires_at=end, heartbeat_expires_at=end,
                   revoked_at=end + timedelta(minutes=1))
        return wid
    finally:
        await conn.close()


def test_the_broadcast_account_is_served_the_set_as_its_viewer(lab, monkeypatch):
    """Board row 30g, against the real statements: the broadcast account names
    a player and is served exactly that player's envelope for each kind the
    broadcaster reports (a 1v1 sitting, a 2v2 series, an FFA lobby) - for a
    game it WATCHED (round 2 M4: a lease of that account on a spectate game
    whose roster names the viewer and whose span holds the game's end)."""
    bcast = next(iter(main.SPECTATE_BROADCAST_STEAM_IDS))

    async def _ok(request, steam_id, db):
        return steam_id in STEAM.values() or steam_id == bcast
    monkeypatch.setattr(main, "_strict_steam_session_ok", _ok)
    for key, roster in (("K2", "AB"), ("TM2", "ABCD"), ("F2", "ABD")):
        asyncio.run(_watch(key, bcast, roster))
    for sel in ({"sitting": ID["K2"]}, {"sitting": ID["TM2"]}, {"sitting": ID["F2"]}):
        assert _report(bcast, viewer=STEAM["A"], **sel) == _report("A", **sel), sel
    assert _refused(bcast, sitting=ID["K2"]) == (404, "not_found"), "no viewer: it played nothing"
    assert _refused(bcast, viewer=STEAM["C"], lobby=ID["F2"]) == (404, "not_found"), "C sat F2 out"
    assert _refused("B", viewer=STEAM["A"], sitting=ID["K2"]) == (403, "broadcast_only")


def test_a_viewer_read_is_bound_to_a_game_the_broadcast_seat_watched(lab, monkeypatch):
    """Round 2 M4 on the real statements: outside a watched game the viewer
    read is the ordinary 404; control: the viewer's own request for the same
    set is served, and a watched game makes the same request succeed."""
    bcast = next(iter(main.SPECTATE_BROADCAST_STEAM_IDS))

    async def _ok(request, steam_id, db):
        return steam_id in STEAM.values() or steam_id == bcast
    monkeypatch.setattr(main, "_strict_steam_session_ok", _ok)
    # KL is A's next sitting (minute 420): nothing the broadcast seat watched
    assert _refused(bcast, viewer=STEAM["A"], sitting=ID["KL"]) == (404, "not_found")
    assert _games(_report("A", sitting=ID["KL"])), "control: A's own request is served"
    # a spectate game over KL whose lease is ANOTHER account's
    asyncio.run(_watch("KL", STEAM["Z"], "AB"))
    assert _refused(bcast, viewer=STEAM["A"], sitting=ID["KL"]) == (404, "not_found")
    # the broadcast seat's lease on a game whose roster does not name the viewer
    asyncio.run(_watch("KL", bcast, "BZ"))
    assert _refused(bcast, viewer=STEAM["A"], sitting=ID["KL"]) == (404, "not_found")
    # a series key is not a game id
    assert _refused(bcast, viewer=STEAM["A"], series=ID["RS1"]) == (404, "not_found")
    # now the seat watched KL with A in the roster: served, the viewer's own envelope
    asyncio.run(_watch("KL", bcast, "AB"))
    assert _report(bcast, viewer=STEAM["A"], sitting=ID["KL"]) == _report("A", sitting=ID["KL"])


# -- /health `session_report` against the lab database ---------------------------

def test_the_health_word_reads_what_the_labs_database_has(lab):
    """/health `session_report` on the lab database: 1 with every column the
    report's statements name; 0 with one of them renamed (the ledger's
    `reason`, which only the gold statement names), after which the session
    still answers and the rename is gone; and 1 with a column no statement
    names renamed instead (the control: the ledger's `created_at`)."""
    from sqlalchemy import text as _text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    for s in main._SESSION_REPORT_STATEMENTS:
        assert "gt.created_at" not in s, "the control column must be one no statement names"
    assert any("gt.reason" in s for s in main._SESSION_REPORT_STATEMENTS)
    has_column = ("SELECT count(*) FROM information_schema.columns"
                  " WHERE table_schema = current_schema() AND table_name = 'gold_transactions'"
                  " AND column_name = :c")

    async def _go():
        engine = create_async_engine(ASYNC_DSN, poolclass=NullPool,
                                     connect_args={"server_settings": {"search_path": _LAB["schema"]}})
        out = {}
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                out["intact"] = await main._session_report_probe(db)
                for column in ("reason", "created_at"):
                    await db.execute(_text("ALTER TABLE gold_transactions RENAME COLUMN %s TO %s_gone"
                                           % (column, column)))
                    out[column + "_renamed"] = (await db.execute(_text(has_column),
                                                                 {"c": column + "_gone"})).scalar()
                    out[column] = await main._session_report_probe(db)
                    await db.rollback()   # undoes the control's rename; the probe undid the other
                    out[column + "_back"] = (await db.execute(_text(has_column), {"c": column})).scalar()
                    await db.rollback()
        finally:
            await engine.dispose()
        return out

    got = asyncio.run(_go())
    assert got == {"intact": 1,
                   "reason_renamed": 1, "reason": 0, "reason_back": 1,
                   "created_at_renamed": 1, "created_at": 1, "created_at_back": 1}, got
