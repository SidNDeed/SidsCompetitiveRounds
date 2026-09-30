"""FFA-TROPHIES, board row 28: the ranked-FFA shutout tiers count the players
who FINISHED the game, and migration 363 takes back the four awards that fail
that count.

THE RULE (Sid, 2026-09-28: the same rule for everyone). Clean House, Party
Crasher and Hostile Takeover -- ffa_shutout_3 / _4 / _5, nested, winner only --
are tiered on _ffa_finishing_count: the MINIMUM of the server's account (the
seated members minus the departures recorded on the lobby row the report
locked) and the report's account (seats marked neither left_early nor absent).
Until this batch the tier read len(members), the sitting's seated roster,
which keeps every seat that has left: the 2026-09-08 sitting -- five seated,
three recorded as departed, two finishing -- paid all three tiers.

What the groups below pin:

  * the rule as a pure function, no database;
  * the endpoint itself, awaited against a harness in ONE named schema:
      - the 2026-09-08 sitting replayed grants no tier (count 2);
      - the same sitting with the departed seats reported present still
        counts 2: the report's flags can lower the count, never raise it;
      - a genuine five-player 5-0 grants all three (the control proving a
        grant is reachable through this harness at all);
      - a departure recorded AFTER a report leaves that game's grants alone,
        and the next game counts it (4: two tiers, not three);
      - a lobby row carrying no departed_ids grants no tier;
      - the old roster count, patched back in, pays the replayed sitting all
        three tiers (the in-suite mutation control: the first test's "no
        tier" is not vacuous);
  * the ordering the rule rests on: a departure write waits for the report's
    lobby lock, and every departed_ids writer updates that row;
  * migration 363, applied from its own file: the four revoked with exact
    deltas, a second run changes nothing (value + xmin), a partial state and a
    short balance are refused with nothing changed, a database without the
    holders is left alone, and a revoked key pays again when it is re-earned.

Live checks read FFA_TROPHIES_TEST_PG_DSN and FAIL without it;
FFA_TROPHIES_TEST_PG_OPTOUT=1 is the explicit way to run this file without a
PostgreSQL (#438). Before it drops or creates anything, the harness refuses a
database whose name does not carry the lane marker, a database holding any
relation that is not one of its own fixtures, and a fixture table holding a
row that is not one of its own.
"""

import ast
import asyncio
import inspect
import io
import os
import pathlib
import re
import sys
import textwrap
import tokenize
import uuid
from datetime import datetime, timezone

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

import main  # noqa: E402
import schemas  # noqa: E402

SQL_DIR = pathlib.Path(__file__).resolve().parents[1] / "sql"
MIGRATION = SQL_DIR / "363_revoke_ffa_shutouts_below_finishing_count.sql"

# Five seats, in seat order. Synthetic 17-digit ids outside the SteamID64
# range, so no row here can be mistaken for a real account.
SEATS = ("90000000000028001", "90000000000028002", "90000000000028003",
         "90000000000028004", "90000000000028005")
A, B, C, D, E = SEATS
PIDS = {s: uuid.UUID("00000000-0000-4000-8000-0000000280%02d" % (i + 1))
        for i, s in enumerate(SEATS)}
OUTSIDER = uuid.UUID("00000000-0000-4000-8000-000000028999")
LOBBY = uuid.UUID("00000000-0000-4000-8000-000000028100")
ROOM = "ffatrophies_s1"
T0 = datetime(2026, 9, 8, 21, 0, 0, tzinfo=timezone.utc)
SHUTOUT_KEYS = ("ffa_shutout_3", "ffa_shutout_4", "ffa_shutout_5")

# The migration fixture's own players: the two target holders (their ids come
# from the migration file itself), a holder of a SOUND award, and a bystander.
SOUND = uuid.UUID("00000000-0000-4000-8000-000000028203")
BYSTANDER = uuid.UUID("00000000-0000-4000-8000-000000028204")
MIG_STEAMS = ("90000000000028101", "90000000000028102", "90000000000028103",
              "90000000000028104")
SYNTHETIC_STEAMS = frozenset(SEATS) | frozenset(MIG_STEAMS)


def run(coro):
    return asyncio.run(coro)


# -- live PostgreSQL gate ------------------------------------------------------

DSN = os.environ.get("FFA_TROPHIES_TEST_PG_DSN")


def _optout(raw) -> bool:
    """Only an affirmative word opts out; "0", "false" or an unknown value do
    not, so the live checks then FAIL and name the DSN (#438)."""
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


OPTOUT = _optout(os.environ.get("FFA_TROPHIES_TEST_PG_OPTOUT"))


def require_pg():
    if DSN:
        return DSN
    if OPTOUT:
        pytest.skip("FFA_TROPHIES_TEST_PG_OPTOUT is set -- live-PostgreSQL checks "
                    "deliberately not run in this invocation")
    pytest.fail(
        "FFA_TROPHIES_TEST_PG_DSN is not set, so the report endpoint's shutout "
        "tier, the lobby lock ordering and migration 363 were never executed. Set "
        "FFA_TROPHIES_TEST_PG_DSN=postgresql+asyncpg://... to run them, or "
        "FFA_TROPHIES_TEST_PG_OPTOUT=1 to say out loud that this run skips them.")


@pytest.mark.parametrize("raw,opts_out", [
    ("1", True), ("true", True), (" yes ", True), ("on", True),
    ("0", False), ("false", False), ("", False), (None, False), ("maybe", False),
])
def test_only_an_affirmative_opt_out_turns_the_live_checks_into_skips(raw, opts_out):
    assert _optout(raw) is opts_out


def test_the_live_checks_cannot_be_skipped_by_a_missing_dsn_alone():
    assert "pytest.fail(" in inspect.getsource(require_pg)
    mod = sys.modules[__name__]
    for name in dir(mod):
        fn = getattr(mod, name)
        if callable(fn) and name.startswith("test_pg_"):
            marks = {m.name for m in getattr(fn, "pytestmark", [])}
            assert "skipif" not in marks and "skip" not in marks, name
    saved_dsn, saved_opt = globals()["DSN"], globals()["OPTOUT"]
    globals()["DSN"], globals()["OPTOUT"] = None, False
    try:
        with pytest.raises(BaseException) as ex:
            require_pg()
        assert "Failed" in type(ex.value).__name__
        assert "FFA_TROPHIES_TEST_PG_DSN" in str(ex.value)
        globals()["OPTOUT"] = True
        with pytest.raises(BaseException) as sk:
            require_pg()
        assert "Skipped" in type(sk.value).__name__
    finally:
        globals()["DSN"], globals()["OPTOUT"] = saved_dsn, saved_opt


# -- scoreboards -----------------------------------------------------------------
# Every board lists the five seats in seat order, so an entry's slot is its
# member index -- which is what the endpoint's slot binding compares.

def _seat(steam, rounds=0, points=0, kills=0, left=False, absent=False, gp=None):
    return {"steam": steam, "rounds": rounds, "points": points, "kills": kills,
            "left": left, "absent": absent, "gp": gp}


def _won(steam):
    """Five converted points and nobody else converted one: a 5-0."""
    return _seat(steam, rounds=5, points=10, kills=6)


def _finished(steam, points):
    """Played to the end, converted nothing (leftover half points only)."""
    return _seat(steam, points=points, kills=1)


def _departed(steam):
    """A seat that left: left_early AND absent, zero signed tallies -- the
    shape the 2026-09-08 report carried for its three departed seats."""
    return _seat(steam, left=True, absent=True)


def _called_present(steam):
    """The same departed seat with both unsigned flags cleared."""
    return _seat(steam)


SEPT8 = (_won(A), _finished(B, 4), _departed(C), _departed(D), _departed(E))
SEPT8_CALLED_PRESENT = (_won(A), _finished(B, 4), _called_present(C),
                        _called_present(D), _called_present(E))
FIVE_FINISH = (_won(A), _finished(B, 4), _finished(C, 3), _finished(D, 2),
               _finished(E, 1))
NEXT_GAME_E_GONE = (_finished(A, 4), _won(B), _finished(C, 3), _finished(D, 2),
                    _departed(E))


def _report(board, winner, game):
    assert tuple(s["steam"] for s in board) == SEATS, "a board must list the seats in seat order"
    return schemas.FfaMatchReport(
        lobby_id=str(LOBBY), photon_room_id="%s_r%d" % (ROOM, game),
        winner_steam_id=winner, reported_by_steam_id=winner, is_ranked=True,
        players=[schemas.FfaPlayerEntry(
            steam_id=s["steam"], slot=i, rounds_won=s["rounds"],
            points_total=s["points"], kills=s["kills"], left_early=s["left"],
            absent=s["absent"], game_points_at_leave=s["gp"])
            for i, s in enumerate(board)])


# -- the rule, as a pure function --------------------------------------------------

@pytest.mark.parametrize("departed,board,expected", [
    # the 2026-09-08 sitting: five seated, three recorded departed, two attested
    ((C, D, E), SEPT8, (2, 2, 2)),
    # the same sitting with the departed seats reported present
    ((C, D, E), SEPT8_CALLED_PRESENT, (2, 2, 5)),
    # a genuine five-player game
    ((), FIVE_FINISH, (5, 5, 5)),
    # the report says three left that the server never recorded: the lower
    # account decides, which is the report's
    ((), SEPT8, (2, 5, 2)),
    # the server recorded one departure the report does not show
    ((E,), FIVE_FINISH, (4, 4, 5)),
], ids=["sept8", "sept8-called-present", "five-finish", "report-lower",
        "server-lower"])
def test_the_count_is_the_minimum_of_the_server_and_the_report(departed, board, expected):
    members = {PIDS[s] for s in SEATS}
    got = main._ffa_finishing_count(members, [PIDS[s] for s in departed],
                                    _report(board, A, 1))
    assert got == expected


def test_a_departure_outside_the_roster_and_a_repeated_one_move_nothing_extra():
    members = {PIDS[s] for s in SEATS}
    report = _report(FIVE_FINISH, A, 1)
    assert main._ffa_finishing_count(members, [OUTSIDER], report) == (5, 5, 5)
    assert main._ffa_finishing_count(members, [PIDS[E], PIDS[E]], report) == (4, 4, 5)
    assert main._ffa_finishing_count(members, None, report) == (5, 5, 5)


def test_the_count_is_never_above_either_account_or_the_old_roster_count():
    """Every combination of recorded departures and reported leavers over five
    seats. The expected server and report numbers are counted here from the
    masks, not read back from the function."""
    members = [PIDS[s] for s in SEATS]
    for dmask in range(32):
        departed = [PIDS[s] for i, s in enumerate(SEATS) if dmask >> i & 1]
        for lmask in range(32):
            board = tuple(
                _departed(s) if lmask >> i & 1 else (_won(s) if i == 0 else _finished(s, 1))
                for i, s in enumerate(SEATS))
            count, server, attested = main._ffa_finishing_count(
                set(members), departed, _report(board, A, 1))
            assert server == 5 - bin(dmask).count("1"), (dmask, lmask)
            assert attested == 5 - bin(lmask).count("1"), (dmask, lmask)
            assert count == min(server, attested), (dmask, lmask)
            assert count <= len(members), (dmask, lmask)


# -- the endpoint reads it, and nothing else ----------------------------------------

def _without_comments(src):
    """The source with every comment token removed, so a comment that NAMES the
    old roster count is not mistaken for code that reads it."""
    toks = [t for t in tokenize.generate_tokens(io.StringIO(textwrap.dedent(src)).readline)
            if t.type != tokenize.COMMENT]
    return tokenize.untokenize(toks)


def test_the_tier_reads_the_finishing_count_and_nothing_else():
    """Occurrences are counted inside submit_ffa_match, never file-wide (#284):
    the one assignment of `_n_played` comes from _ffa_finishing_count, its one
    comparison is the tier loop's, and no other function in the module reads
    it. Comments are stripped first; the old count is named in one."""
    raw = inspect.getsource(main.submit_ffa_match)
    src = _without_comments(raw)
    assert "seated roster" in raw and "seated roster" not in src, "the comments were not stripped"
    start = src.index("_ach_players = sorted(")
    end = src.index('"ffa_shutout_5")', start)
    block = src[start:end]
    assert block.count("_ffa_finishing_count(") == 1
    assert src.count("_ffa_finishing_count(") == 1
    for roster_read in ("len(members)", "len(member_set)", "cardinality(member_ids)"):
        assert roster_read not in block, roster_read
    assigns = re.findall(r"^\s*(_n_played\b[^=\n]*)=(?!=)", src, re.M)
    assert assigns == ["_n_played, _n_server, _n_attested "], assigns
    assert re.findall(r"_n_played\s*>=\s*(\w+)", src) == ["_need"]
    module_src = pathlib.Path(main.__file__).read_text(encoding="utf-8")
    assert module_src.count("_n_played") == raw.count("_n_played") == 3
    for need, key in ((3, "ffa_shutout_3"), (4, "ffa_shutout_4"), (5, "ffa_shutout_5")):
        assert '(%d, "%s")' % (need, key) in src, key


def test_every_departed_ids_writer_updates_the_lobby_row_the_report_locks():
    """The server account is "departures recorded before this report" only
    because every writer of departed_ids is an UPDATE of the ffa_lobbies row,
    which waits for the report's FOR NO KEY UPDATE on that row. A writer of
    any other shape would break that, so the writers are counted from the
    module's own string constants: three today, and a fourth has to be looked
    at before this count moves."""
    tree = ast.parse(pathlib.Path(main.__file__).read_text(encoding="utf-8"))
    writers = [n.value for n in ast.walk(tree)
               if isinstance(n, ast.Constant) and isinstance(n.value, str)
               and re.search(r"\bdeparted_ids\s*=(?!=)", n.value)]
    assert writers, "no departed_ids writer found: the pattern no longer reads the source"
    offenders = [w.strip()[:120] for w in writers
                 if not re.match(r"\s*UPDATE\s+ffa_lobbies\b", w)]
    assert not offenders, offenders
    assert len(writers) == 3, [w.strip()[:120] for w in writers]
    assert "FOR NO KEY UPDATE" in main._FFA_LOBBY_LOCK_SQL
    assert "FROM ffa_lobbies" in main._FFA_LOBBY_LOCK_SQL


# -- the harness: ONE named schema, refusals before anything destructive ------------

HARNESS_SCHEMA = "ffa_trophies_harness"
LANE_MARKER = re.compile(r"(?:^|_)ffa_trophies(?:_|$)")
# Dependency order: each table is dropped before the tables it references.
HARNESS_TABLES = ("player_achievements", "gold_transactions", "glicko_ratings_ffa",
                  "match_report_quarantine", "ffa_match_players", "ffa_matches",
                  "ffa_lobbies", "players")
HARNESS_DROP = ["DROP TABLE IF EXISTS %s.%s RESTRICT" % (HARNESS_SCHEMA, t)
                for t in HARNESS_TABLES]

# The columns the report path reads and writes, at the types their migrations
# declare (154/155/156/159/167/169/177/206/216/233/324/327, 009+011 for
# player_achievements), in the shape test_ffa_game_number_anchor.py's settling
# fixture already proves the endpoint settles against -- plus departed_ids
# (159) and player_achievements, the two things this lane's rule reads and
# writes. ffa_match_players keeps 154's NULLABLE rating columns: an unrated
# (departed) seat is written with no rating change, and the anchor fixture's
# narrowed NOT NULL copy refuses that row -- its reports never carry one.
# Cards, offers, packs and wagers are not built: each sits in its own
# savepoint in the endpoint, so a missing table costs that feature and not the
# report.
_DDL = """
CREATE TABLE @S@.players (
    id UUID PRIMARY KEY,
    steam_id TEXT NOT NULL UNIQUE,
    display_name VARCHAR(64) NOT NULL DEFAULT 'Player',
    total_xp INTEGER NOT NULL DEFAULT 0,
    ffa_xp_earned INTEGER NOT NULL DEFAULT 0,
    gold_earned INTEGER NOT NULL DEFAULT 0,
    gold_spent INTEGER NOT NULL DEFAULT 0,
    ffa_gold_earned INTEGER NOT NULL DEFAULT 0,
    active_player_color_id BIGINT
)
;;
CREATE TABLE @S@.ffa_lobbies (
    id UUID PRIMARY KEY,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    player_count SMALLINT NOT NULL DEFAULT 3,
    member_ids UUID[] NOT NULL DEFAULT '{}',
    games_played INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    departure_causes JSONB NOT NULL DEFAULT '{}'::jsonb,
    departed_ids UUID[] NOT NULL DEFAULT '{}'
)
;;
CREATE TABLE @S@.ffa_matches (
    id UUID PRIMARY KEY,
    lobby_id UUID,
    photon_room_id VARCHAR(64) NOT NULL,
    player_count SMALLINT NOT NULL DEFAULT 3,
    winner_id UUID REFERENCES @S@.players(id),
    ended_at TIMESTAMPTZ NOT NULL,
    invalidated_at TIMESTAMPTZ,
    game_number SMALLINT,
    score_target_frozen SMALLINT,
    score_target_played SMALLINT,
    duration_seconds INTEGER,
    game_version VARCHAR(32),
    region VARCHAR(8),
    hmac_signature VARCHAR(160),
    reported_by UUID,
    is_ranked BOOLEAN NOT NULL DEFAULT TRUE,
    started_at TIMESTAMPTZ,
    timeline TEXT,
    battles_total INTEGER,
    paid_battles REAL,
    elapsed_seconds INTEGER,
    CONSTRAINT uq_ffa_match_room UNIQUE (photon_room_id)
)
;;
CREATE TABLE @S@.ffa_match_players (
    match_id UUID NOT NULL REFERENCES @S@.ffa_matches(id) ON DELETE CASCADE,
    player_id UUID NOT NULL REFERENCES @S@.players(id) ON DELETE CASCADE,
    slot SMALLINT,
    rounds_won SMALLINT NOT NULL DEFAULT 0,
    points_total SMALLINT NOT NULL DEFAULT 0,
    placement SMALLINT NOT NULL,
    left_early BOOLEAN NOT NULL DEFAULT FALSE,
    rating_before DOUBLE PRECISION,
    rating_after DOUBLE PRECISION,
    rating_change DOUBLE PRECISION,
    xp_gained INTEGER NOT NULL DEFAULT 0,
    gold_gained INTEGER NOT NULL DEFAULT 0,
    kills INTEGER NOT NULL DEFAULT 0,
    absent BOOLEAN NOT NULL DEFAULT false,
    fps_avg SMALLINT,
    ping_avg SMALLINT,
    bullets_fired INTEGER,
    bullets_hit INTEGER,
    blocks_activated INTEGER,
    blocks_successful INTEGER,
    keys_pressed INTEGER,
    active_seconds REAL,
    fps_timeline VARCHAR(512),
    ping_timeline VARCHAR(512),
    hit_timeline VARCHAR(1024),
    block_timeline VARCHAR(1024),
    damage_dealt INTEGER,
    damage_dealt_timeline VARCHAR(1024),
    kill_timeline VARCHAR(512),
    end_stats TEXT,
    game_points_at_leave SMALLINT,
    color_name VARCHAR(40),
    color_hex VARCHAR(9),
    left_early_involuntary BOOLEAN NOT NULL DEFAULT false,
    PRIMARY KEY (match_id, player_id)
)
;;
CREATE TABLE @S@.match_report_quarantine (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mode VARCHAR(8) NOT NULL,
    reason VARCHAR(64) NOT NULL,
    http_status SMALLINT NOT NULL,
    group_id UUID,
    photon_room_id VARCHAR(64),
    reporter_id UUID REFERENCES @S@.players(id) ON DELETE SET NULL,
    player_ids UUID[] NOT NULL DEFAULT '{}',
    payload JSONB NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    reviewed_by UUID REFERENCES @S@.players(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    review_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
;;
CREATE UNIQUE INDEX uq_quarantine_room
    ON @S@.match_report_quarantine (mode, photon_room_id)
    WHERE photon_room_id IS NOT NULL
;;
CREATE TABLE @S@.glicko_ratings_ffa (
    player_id UUID PRIMARY KEY REFERENCES @S@.players(id) ON DELETE CASCADE,
    rating DOUBLE PRECISION NOT NULL DEFAULT 1500,
    rating_deviation DOUBLE PRECISION NOT NULL DEFAULT 350,
    volatility DOUBLE PRECISION NOT NULL DEFAULT 0.06,
    peak_rating DOUBLE PRECISION NOT NULL DEFAULT 1500,
    games_played INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    top3 INTEGER NOT NULL DEFAULT 0,
    placement_sum INTEGER NOT NULL DEFAULT 0,
    last_calculated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
;;
CREATE TABLE @S@.gold_transactions (
    id BIGSERIAL PRIMARY KEY,
    player_id UUID NOT NULL REFERENCES @S@.players(id) ON DELETE CASCADE,
    amount INTEGER NOT NULL,
    reason VARCHAR(64) NOT NULL,
    reference_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
;;
CREATE TABLE @S@.player_achievements (
    id SERIAL PRIMARY KEY,
    player_id UUID NOT NULL REFERENCES @S@.players(id) ON DELETE CASCADE,
    achievement_key VARCHAR(64) NOT NULL,
    unlocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    match_id UUID,
    UNIQUE (player_id, achievement_key)
)
"""
HARNESS_DDL = [s.strip().replace("@S@", HARNESS_SCHEMA) for s in _DDL.split(";;") if s.strip()]

# Every relation outside the system schemas, with the table an index or a
# column-owned sequence belongs to. Temporary schemas are other sessions'
# (or this session's ON COMMIT DROP table) and are not this harness's to judge.
CENSUS_SQL = """
SELECT n.nspname AS schema, c.relname AS name, c.relkind::text AS kind,
       COALESCE(ti.relname, ts.relname) AS owner_table,
       COALESCE(tni.nspname, tns.nspname) AS owner_schema
  FROM pg_catalog.pg_class c
  JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
  LEFT JOIN pg_catalog.pg_index i ON i.indexrelid = c.oid
  LEFT JOIN pg_catalog.pg_class ti ON ti.oid = i.indrelid
  LEFT JOIN pg_catalog.pg_namespace tni ON tni.oid = ti.relnamespace
  LEFT JOIN pg_catalog.pg_depend d
         ON c.relkind = 'S' AND d.classid = 'pg_catalog.pg_class'::regclass
        AND d.objid = c.oid AND d.refclassid = 'pg_catalog.pg_class'::regclass
        AND d.deptype IN ('a', 'i')
  LEFT JOIN pg_catalog.pg_class ts ON ts.oid = d.refobjid
  LEFT JOIN pg_catalog.pg_namespace tns ON tns.oid = ts.relnamespace
 WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
   AND n.nspname !~ '^pg_(toast_)?temp_[0-9]+$'
 ORDER BY 1, 2
"""


def _raw_dsn():
    dsn = require_pg()
    for prefix in ("postgresql+asyncpg://", "postgresql://"):
        if dsn.startswith(prefix):
            return "postgresql://" + dsn[len(prefix):]
    raise RuntimeError("FFA_TROPHIES_TEST_PG_DSN is not a postgresql URL")


def _foreign(rows):
    """Every census row that is not one of this harness's fixtures, by name:
    a harness table in HARNESS_SCHEMA, or an index / column-owned sequence of
    one. Never by a count."""
    out = []
    for r in rows:
        own = r["schema"] == HARNESS_SCHEMA and (
            (r["kind"] == "r" and r["name"] in HARNESS_TABLES)
            or (r["kind"] in ("i", "S") and r["owner_schema"] == HARNESS_SCHEMA
                and r["owner_table"] in HARNESS_TABLES))
        if not own:
            out.append("%s.%s (relkind %s)" % (r["schema"], r["name"], r["kind"]))
    return out


async def _refuse_unless_lane_database(conn):
    """The three refusals, on an UNBOUND connection, before any DROP or CREATE
    is sent: the database's name carries the lane marker; every relation in
    it is one of this harness's fixtures; and a fixture players table holds
    only this harness's synthetic seats. Returns the database name."""
    name = await conn.fetchval("SELECT pg_catalog.current_database()")
    if not LANE_MARKER.search(name or ""):
        raise RuntimeError(
            "refusing: FFA_TROPHIES_TEST_PG_DSN points at database %r, whose name "
            "does not carry the ffa_trophies lane marker; this harness drops and "
            "recreates tables" % (name,))
    foreign = _foreign(await conn.fetch(CENSUS_SQL))
    if foreign:
        raise RuntimeError(
            "refusing: database %r holds relations that are not this harness's "
            "fixtures: %s" % (name, ", ".join(foreign)))
    if await conn.fetchval("SELECT pg_catalog.to_regclass($1) IS NOT NULL",
                           HARNESS_SCHEMA + ".players"):
        strangers = await conn.fetch(
            "SELECT steam_id FROM " + HARNESS_SCHEMA + ".players"
            " WHERE NOT (steam_id = ANY($1::text[]))", sorted(SYNTHETIC_STEAMS))
        if strangers:
            raise RuntimeError(
                "refusing: %s.players in database %r holds rows that are not this "
                "harness's seats (%d)" % (HARNESS_SCHEMA, name, len(strangers)))
    return name


async def _fresh_harness():
    conn = await asyncpg.connect(_raw_dsn())
    try:
        await _refuse_unless_lane_database(conn)
        await conn.execute("CREATE SCHEMA IF NOT EXISTS " + HARNESS_SCHEMA)
        for stmt in HARNESS_DROP:
            await conn.execute(stmt)
        for stmt in HARNESS_DDL:
            await conn.execute(stmt)
    finally:
        await conn.close()


async def _bound_raw():
    """A raw connection whose search path is the harness schema alone, proved
    by reading it back rather than assumed from the setting."""
    conn = await asyncpg.connect(_raw_dsn(), server_settings={"search_path": HARNESS_SCHEMA})
    got = list(await conn.fetchval("SELECT pg_catalog.current_schemas(false)"))
    if got != [HARNESS_SCHEMA]:
        await conn.close()
        raise RuntimeError("the search path did not bind to %s: %r" % (HARNESS_SCHEMA, got))
    return conn


def _engine():
    return create_async_engine(
        require_pg(), connect_args={"server_settings": {"search_path": HARNESS_SCHEMA}})


class _FakeCensusConn:
    """Just enough of a connection for the refusals, with no database."""

    def __init__(self, name="scr_ffa_trophies", census=(), strangers=(), players=False):
        self.name, self.census, self.strangers, self.players = name, census, strangers, players

    async def fetchval(self, sql, *args):
        if "current_database()" in sql:
            return self.name
        if "to_regclass" in sql:
            return self.players
        raise AssertionError(sql)

    async def fetch(self, sql, *args):
        if "pg_catalog.pg_class" in sql:
            return list(self.census)
        if "steam_id" in sql:
            return [{"steam_id": s} for s in self.strangers]
        raise AssertionError(sql)


def _row(schema, name, kind, owner_table=None, owner_schema=None):
    return {"schema": schema, "name": name, "kind": kind,
            "owner_table": owner_table, "owner_schema": owner_schema}


def test_the_harness_refuses_before_anything_destructive():
    """Each refusal, run against a stand-in connection, with a clean control."""
    own = [_row(HARNESS_SCHEMA, "players", "r"),
           _row(HARNESS_SCHEMA, "players_pkey", "i", "players", HARNESS_SCHEMA),
           _row(HARNESS_SCHEMA, "gold_transactions_id_seq", "S", "gold_transactions",
                HARNESS_SCHEMA)]
    assert run(_refuse_unless_lane_database(_FakeCensusConn(census=own))) == "scr_ffa_trophies"
    assert run(_refuse_unless_lane_database(_FakeCensusConn(name="ffa_trophies_lane"))) == "ffa_trophies_lane"
    cases = [
        (_FakeCensusConn(name="scr_competitive_rounds"), "lane marker"),
        (_FakeCensusConn(name="notffa_trophiesx"), "lane marker"),
        (_FakeCensusConn(census=own + [_row("public", "players", "r")]), "public.players"),
        (_FakeCensusConn(census=[_row(HARNESS_SCHEMA, "shop_items", "r")]), "shop_items"),
        (_FakeCensusConn(census=[_row(HARNESS_SCHEMA, "players_steam_idx", "i", "players",
                                      "public")]), "players_steam_idx"),
        (_FakeCensusConn(players=True, strangers=["76561198000000000"]), "not this harness's seats"),
    ]
    for conn, why in cases:
        with pytest.raises(RuntimeError) as ex:
            run(_refuse_unless_lane_database(conn))
        assert why in str(ex.value), (why, str(ex.value))


def test_every_harness_statement_names_its_schema():
    for stmt in HARNESS_DROP + HARNESS_DDL:
        named = re.findall(r"\b(?:TABLE(?: IF EXISTS)?|REFERENCES|ON(?!\s+(?:DELETE|UPDATE)\b))"
                           r"\s+([A-Za-z_][\w.]*)\s*[\s(]", stmt)
        assert named, stmt[:80]
        for obj in named:
            assert obj.startswith(HARNESS_SCHEMA + "."), (obj, stmt[:80])
    assert all(s.endswith(" RESTRICT") for s in HARNESS_DROP)
    assert "CASCADE" not in " ".join(HARNESS_DROP)


# -- the endpoint, awaited --------------------------------------------------------

class _NoHeaders:
    @staticmethod
    def get(_name, _default=None):
        return None


class _FakeRequest:
    """Only what _check_steam_session reads; the session check itself is
    replaced below, as test_ffa_game_number_anchor.py does, so the result does
    not depend on which auth variables this machine has set (#438)."""
    headers = _NoHeaders()
    client = None
    url = "http://test/api/v1/ffa/matches"


async def _call_endpoint(sm, report):
    """Await the production endpoint with a real session. The signature check
    takes the module's own "no secret configured" path and the session check
    is replaced: neither is what these tests are about."""
    saved_secret = main.MATCH_HMAC_SECRET
    saved_session = main._check_steam_session

    async def _no_session_check(request, steam_id, db):
        return None

    main.MATCH_HMAC_SECRET = ""
    main._check_steam_session = _no_session_check
    try:
        async with sm() as db:
            return await main.submit_ffa_match(report, _FakeRequest(), db)
    finally:
        main.MATCH_HMAC_SECRET = saved_secret
        main._check_steam_session = saved_session


async def _seat_the_sitting(sm, departed, drop_departed_column):
    async with sm() as db:
        for i, s in enumerate(SEATS):
            await db.execute(text(
                "INSERT INTO players (id, steam_id, display_name) VALUES (:i, :s, :n)"),
                {"i": PIDS[s], "s": s, "n": "lane-seat-%d" % (i + 1)})
        await db.execute(text(
            "INSERT INTO ffa_lobbies (id, status, player_count, member_ids,"
            "                         departed_ids, games_played, created_at)"
            " VALUES (:i, 'active', :n, CAST(:m AS uuid[]), CAST(:d AS uuid[]), 0,"
            "         CAST(:t AS TIMESTAMPTZ))"),
            {"i": LOBBY, "n": len(SEATS), "m": [str(PIDS[s]) for s in SEATS],
             "d": [str(PIDS[s]) for s in departed], "t": T0})
        if drop_departed_column:
            await db.execute(text("ALTER TABLE ffa_lobbies DROP COLUMN departed_ids"))
        await db.commit()


# The same statement shape as the departure writers in ffa_queue_leave.
DEPARTURE_APPEND = (
    "UPDATE ffa_lobbies"
    "   SET departed_ids = (SELECT ARRAY(SELECT DISTINCT e FROM"
    "                        unnest(departed_ids || CAST(:pid AS uuid)) e))"
    " WHERE id = :lid AND status = 'active'")


async def _record_departure(sm, steam):
    async with sm() as db:
        n = (await db.execute(text(DEPARTURE_APPEND),
                              {"pid": PIDS[steam], "lid": LOBBY})).rowcount
        await db.commit()
    assert n == 1, n


async def _snapshot(sm):
    async with sm() as db:
        awards = [tuple(r) for r in (await db.execute(text(
            "SELECT p.steam_id, a.achievement_key FROM player_achievements a"
            "  JOIN players p ON p.id = a.player_id"
            " WHERE a.achievement_key = ANY(CAST(:k AS text[])) ORDER BY 1, 2"),
            {"k": list(SHUTOUT_KEYS)})).all()]
        paid = [tuple(r) for r in (await db.execute(text(
            "SELECT p.steam_id, g.reference_id, g.amount FROM gold_transactions g"
            "  JOIN players p ON p.id = g.player_id"
            " WHERE g.reason = 'achievement' AND g.reference_id = ANY(CAST(:k AS text[]))"
            " ORDER BY 1, 2"), {"k": list(SHUTOUT_KEYS)})).all()]
        settled = int((await db.execute(text(
            "SELECT COUNT(*) FROM ffa_matches WHERE lobby_id = :l"), {"l": LOBBY})).scalar())
    return {"awards": awards, "paid": paid, "settled": settled}


async def _play(games, departed=(), between=None, drop_departed_column=False):
    """Seat the five, then deliver each (board, winner) as game 1, 2, ... of the
    sitting through the real endpoint. `between` maps a game number to a step
    run after that game settles. Returns the search path the endpoint's
    sessions were bound to and a labelled snapshot after every step."""
    await _fresh_harness()
    engine = _engine()
    sm = async_sessionmaker(engine, expire_on_commit=False)
    out = {"snaps": []}
    try:
        async with sm() as db:
            out["search_path"] = list((await db.execute(text(
                "SELECT pg_catalog.current_schemas(false)"))).scalar())
        await _seat_the_sitting(sm, departed, drop_departed_column)
        for game, (board, winner) in enumerate(games, start=1):
            await _call_endpoint(sm, _report(board, winner, game))
            out["snaps"].append(("game %d" % game, await _snapshot(sm)))
            if between and game in between:
                label = await between[game](sm)
                out["snaps"].append((label, await _snapshot(sm)))
        return out
    finally:
        await engine.dispose()


_TIER_LINE = re.compile(
    r"\[FFA-ACH\] shutout tier count (\d+) in room (\S+): server (\d+) of (\d+) "
    r"seated not recorded departed before this report, reporter (\d+) attests "
    r"(\d+) present")


def _tier_lines(log):
    return [(int(m.group(1)), m.group(2), int(m.group(3)), int(m.group(4)),
             m.group(5), int(m.group(6))) for m in _TIER_LINE.finditer(log)]


def _read_log(capsys):
    """The endpoint's printed evidence. The decisive lines are printed again so
    a `-rA` report carries them beside the verdict, and a failed achievement
    evaluation -- which the endpoint catches, and which would make every
    "no tier" assertion pass for the wrong reason -- fails the test here."""
    log = capsys.readouterr().out
    for line in log.splitlines():
        if line.startswith("[FFA-ACH]") or line.startswith("[ACHIEVEMENT]"):
            print("DECISIVE " + line)
    assert "achievement evaluation failed" not in log, log[-2000:]
    return log


def _room(game):
    return "%s_r%d" % (ROOM, game)


def _shutouts(steam, keys):
    return [(steam, k) for k in keys]


def _payments(steam, keys):
    return [(steam, k, main._achievement_gold(k)) for k in keys]


def test_pg_the_sept8_sitting_replayed_grants_no_tier(capsys):
    """Five seated, three recorded as departed before the report, the report
    attesting the same two finishers: count 2, no tier."""
    require_pg()
    out = run(_play([(SEPT8, A)], departed=(C, D, E)))
    log = _read_log(capsys)
    assert out["search_path"] == [HARNESS_SCHEMA]
    snap = out["snaps"][-1][1]
    assert snap["settled"] == 1, "the report did not settle, so no tier was evaluated"
    assert _tier_lines(log) == [(2, _room(1), 2, 5, A, 2)]
    assert snap["awards"] == [] and snap["paid"] == []


def test_pg_the_departed_seats_reported_present_still_count_two(capsys):
    """The same sitting with both unsigned flags cleared on the three departed
    seats. The report's account says five; the server's recorded departures
    say two; the count is two and no tier is granted."""
    require_pg()
    out = run(_play([(SEPT8_CALLED_PRESENT, A)], departed=(C, D, E)))
    log = _read_log(capsys)
    snap = out["snaps"][-1][1]
    assert snap["settled"] == 1
    assert _tier_lines(log) == [(2, _room(1), 2, 5, A, 5)]
    assert snap["awards"] == [] and snap["paid"] == []


def test_pg_a_genuine_five_player_shutout_grants_all_three(capsys):
    """Control: five seated, none departed, all five finishing. The count is
    five and the winner holds all three tiers, each paid once at its price."""
    require_pg()
    out = run(_play([(FIVE_FINISH, A)]))
    log = _read_log(capsys)
    snap = out["snaps"][-1][1]
    assert snap["settled"] == 1
    assert _tier_lines(log) == [(5, _room(1), 5, 5, A, 5)]
    assert snap["awards"] == _shutouts(A, SHUTOUT_KEYS)
    assert snap["paid"] == _payments(A, SHUTOUT_KEYS)


def test_pg_a_departure_after_the_report_moves_only_the_next_game(capsys):
    """Game 1 settles with all five finishing; seat E's departure is recorded
    after it; game 2 is won 5-0 by seat B with E gone. Game 1's three tiers
    stay exactly as granted, and game 2 counts four: Clean House and Party
    Crasher, not Hostile Takeover. Under the roster count game 2 would have
    paid all three."""
    require_pg()

    async def depart_e(sm):
        await _record_departure(sm, E)
        return "E departs"

    out = run(_play([(FIVE_FINISH, A), (NEXT_GAME_E_GONE, B)], between={1: depart_e}))
    log = _read_log(capsys)
    labels = [label for label, _snap in out["snaps"]]
    assert labels == ["game 1", "E departs", "game 2"], labels
    game1, departed, game2 = (snap for _label, snap in out["snaps"])
    assert _tier_lines(log) == [(5, _room(1), 5, 5, A, 5), (4, _room(2), 4, 5, B, 4)]
    assert game1["awards"] == _shutouts(A, SHUTOUT_KEYS)
    assert departed == game1, "recording a departure changed an earlier game's grants"
    assert game2["settled"] == 2
    assert game2["awards"] == sorted(_shutouts(A, SHUTOUT_KEYS)
                                     + _shutouts(B, SHUTOUT_KEYS[:2]))
    assert game2["paid"] == sorted(_payments(A, SHUTOUT_KEYS)
                                   + _payments(B, SHUTOUT_KEYS[:2]))


def test_pg_a_lobby_row_without_departed_ids_grants_no_tier(capsys):
    """A row that cannot say who departed vouches for nobody: the server's
    account is zero and no tier is granted, even for five finishers."""
    require_pg()
    out = run(_play([(FIVE_FINISH, A)], drop_departed_column=True))
    log = _read_log(capsys)
    snap = out["snaps"][-1][1]
    assert snap["settled"] == 1
    assert _tier_lines(log) == [(0, _room(1), 0, 5, A, 5)]
    assert snap["awards"] == [] and snap["paid"] == []


def test_pg_the_old_roster_count_pays_the_replayed_sitting_all_three_tiers(capsys, monkeypatch):
    """The in-suite mutation control for the first test: with the count
    patched back to the seated roster -- what `_n_played = len(members)`
    computed -- the same replay pays all three tiers. So the first test's
    "no tier" is the rule's doing, not the harness's."""
    require_pg()

    def roster_count(member_ids, departed_ids, report):
        seated = len(set(member_ids or ()))
        return seated, seated, seated

    monkeypatch.setattr(main, "_ffa_finishing_count", roster_count)
    out = run(_play([(SEPT8, A)], departed=(C, D, E)))
    log = _read_log(capsys)
    snap = out["snaps"][-1][1]
    assert snap["settled"] == 1
    assert _tier_lines(log) == [(5, _room(1), 5, 5, A, 5)]
    assert snap["awards"] == _shutouts(A, SHUTOUT_KEYS)
    assert snap["paid"] == _payments(A, SHUTOUT_KEYS)


def test_pg_a_departure_recorded_while_a_report_holds_the_lobby_waits_for_it():
    """The server account is read off the lobby row _ffa_lock_lobby_slot locks.
    While that lock is held, a departure write of the writers' shape cannot
    land (it times out on the lock); once the report's transaction ends, it
    lands. So the departures a report reads are exactly those recorded before
    it."""
    require_pg()

    async def go():
        await _fresh_harness()
        engine = _engine()
        sm = async_sessionmaker(engine, expire_on_commit=False)
        try:
            await _seat_the_sitting(sm, (), False)
            blocked = None
            async with sm() as holder:
                row, _expected = await main._ffa_lock_lobby_slot(holder, LOBBY)
                seen = sorted(str(x) for x in (row["departed_ids"] or []))
                async with sm() as writer:
                    await writer.execute(text("SET LOCAL lock_timeout = '400ms'"))
                    try:
                        await writer.execute(text(DEPARTURE_APPEND),
                                             {"pid": PIDS[E], "lid": LOBBY})
                    except Exception as ex:          # noqa: BLE001 - the class is the point
                        blocked = ex
                    await writer.rollback()
                await holder.commit()
            await _record_departure(sm, E)
            async with sm() as db:
                after = sorted(str(x) for x in (await db.execute(text(
                    "SELECT departed_ids FROM ffa_lobbies WHERE id = :l"),
                    {"l": LOBBY})).scalar())
            return seen, blocked, after
        finally:
            await engine.dispose()

    seen, blocked, after = run(go())
    assert seen == []
    assert blocked is not None, "a departure write landed while the report held the lobby row"
    assert "lock timeout" in str(blocked), str(blocked)
    assert after == [str(PIDS[E])]


# -- migration 363 ------------------------------------------------------------------

_TARGET = re.compile(
    r"\((\d+), CAST\('([0-9a-f-]{36})' AS uuid\), '(ffa_shutout_[345])', (\d+), "
    r"CAST\((\d+) AS bigint\)\)")


def _targets():
    found = _TARGET.findall(MIGRATION.read_text(encoding="utf-8"))
    return [(int(pa), uuid.UUID(pid), key, int(gold), int(led))
            for pa, pid, key, gold, led in found]


def test_363_pins_exactly_the_four_awards_the_census_found():
    """Checked against the brief's list, which was drawn up from the census
    before the file was written: awards 414, 567, 568 and 569, their keys,
    the gold each paid and the ledger row that paid it."""
    t = _targets()
    assert [(pa, key, gold) for pa, _pid, key, gold, _led in t] == [
        (414, "ffa_shutout_4", 300), (567, "ffa_shutout_3", 100),
        (568, "ffa_shutout_4", 300), (569, "ffa_shutout_5", 500)]
    assert [led for *_rest, led in t] == [25287, 35699, 35700, 35701]
    holders = {pa: pid for pa, pid, *_rest in t}
    assert holders[567] == holders[568] == holders[569] != holders[414]


def test_363_is_one_explicit_transaction_that_changes_no_schema():
    sql = MIGRATION.read_text(encoding="utf-8")
    body = "\n".join(ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))
    assert body.strip().startswith("BEGIN;"), "the file does not open its own transaction (#340)"
    assert body.strip().endswith("COMMIT;")
    assert body.count("BEGIN;") == 1 and body.count("COMMIT;") == 1
    for pattern in (r"\bDROP\s+(?:TABLE|INDEX|SCHEMA|COLUMN|CONSTRAINT|TRIGGER|FUNCTION|VIEW|SEQUENCE)\b",
                    r"\bALTER\s+TABLE\b", r"\bTRUNCATE\b",
                    r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\b", r"\bCREATE\s+TABLE\b"):
        assert not re.search(pattern, body, re.I), pattern
    assert re.search(r"^--\s*DEPLOY ORDER:\s*THIS FILE FIRST", sql, re.M)
    assert [p.name for p in SQL_DIR.glob("363_*.sql")] == [MIGRATION.name]


FINGERPRINT_SQL = "SELECT " + " || ' ' || ".join(
    "coalesce((SELECT md5(string_agg(x.r::text || '|' || x.xmin::text, ','"
    " ORDER BY x.r::text)) FROM (SELECT t AS r, t.xmin FROM %s t) x), 'empty')" % tbl
    for tbl in ("players", "gold_transactions", "player_achievements"))


async def _seed_363(conn, holders=True):
    """The census state of the four targets (ids, keys, amounts and ledger rows
    read from the migration file), a sound award that must survive, an
    unrelated award and payment of a target holder, and a bystander."""
    t = _targets()
    holder_of = {pa: pid for pa, pid, *_rest in t}
    first, second = holder_of[414], holder_of[567]
    people = [(SOUND, MIG_STEAMS[2], 800), (BYSTANDER, MIG_STEAMS[3], 700)]
    awards = [(411, SOUND, "ffa_shutout_3")]
    ledger = [(30000, SOUND, 100, "achievement", "ffa_shutout_3"),
              (36001, BYSTANDER, 40, "ffa_game", None)]
    if holders:
        people += [(first, MIG_STEAMS[0], 5000), (second, MIG_STEAMS[1], 4000)]
        awards += [(pa, pid, key) for pa, pid, key, _gold, _led in t]
        awards += [(600, second, "ffa_kills_50")]
        ledger += [(led, pid, gold, "achievement", key) for _pa, pid, key, gold, led in t]
        ledger += [(36000, second, 250, "achievement", "ffa_kills_50")]
    for pid, steam, gold in people:
        await conn.execute(
            "INSERT INTO players (id, steam_id, display_name, gold_earned)"
            " VALUES ($1, $2, $3, $4)", pid, steam, "lane-" + steam[-3:], gold)
    for aid, pid, key in awards:
        await conn.execute(
            "INSERT INTO player_achievements (id, player_id, achievement_key)"
            " VALUES ($1, $2, $3)", aid, pid, key)
    for gid, pid, amount, reason, ref in ledger:
        await conn.execute(
            "INSERT INTO gold_transactions (id, player_id, amount, reason, reference_id)"
            " VALUES ($1, $2, $3, $4, $5)", gid, pid, amount, reason, ref)
    await conn.execute("SELECT setval(pg_get_serial_sequence('player_achievements', 'id'), 1000)")
    await conn.execute("SELECT setval(pg_get_serial_sequence('gold_transactions', 'id'), 40000)")
    return first, second


async def _apply_363(conn):
    """The file, as one simple-protocol script -- the way `psql < file` sends
    it: its own BEGIN/COMMIT, the preflight SELECT, the DO block. Returns the
    error it raised (after rolling the failed transaction back) and its
    notices."""
    notices = []

    def listener(_conn, message):
        notices.append(message.message)

    conn.add_log_listener(listener)
    error = None
    try:
        await conn.execute(MIGRATION.read_text(encoding="utf-8"))
    except asyncpg.PostgresError as ex:
        error = ex
        await conn.execute("ROLLBACK")
    finally:
        await asyncio.sleep(0.05)
        conn.remove_log_listener(listener)
    return error, notices


async def _mig_state(conn):
    awards = [r["id"] for r in await conn.fetch("SELECT id FROM player_achievements ORDER BY id")]
    clawbacks = sorted((r["player_id"], r["reference_id"], r["amount"]) for r in await conn.fetch(
        "SELECT player_id, reference_id, amount FROM gold_transactions"
        " WHERE reason = 'achievement_revoked'"))
    balances = {r["id"]: r["gold_earned"] for r in await conn.fetch(
        "SELECT id, gold_earned FROM players")}
    return {"awards": awards, "clawbacks": clawbacks, "balances": balances}


def _in_harness(body):
    """A fresh harness and a bound raw connection for `body(conn)`."""
    async def go():
        await _fresh_harness()
        conn = await _bound_raw()
        try:
            return await body(conn)
        finally:
            await conn.close()
    return run(go())


def test_pg_363_revokes_the_four_and_a_second_run_changes_nothing():
    require_pg()

    async def body(conn):
        first, second = await _seed_363(conn)
        before = await conn.fetchval(FINGERPRINT_SQL)
        err1, notices1 = await _apply_363(conn)
        state1, fp1 = await _mig_state(conn), await conn.fetchval(FINGERPRINT_SQL)
        err2, notices2 = await _apply_363(conn)
        state2, fp2 = await _mig_state(conn), await conn.fetchval(FINGERPRINT_SQL)
        return first, second, before, err1, notices1, state1, fp1, err2, notices2, state2, fp2

    (first, second, before, err1, notices1, state1, fp1,
     err2, notices2, state2, fp2) = _in_harness(body)
    assert err1 is None, err1
    assert any("revoked awards 414, 567, 568, 569; 1200 gold taken back from 2 player(s)"
               in n for n in notices1), notices1
    assert state1["awards"] == [411, 600]
    assert state1["clawbacks"] == sorted([
        (first, "ffa_shutout_4", -300), (second, "ffa_shutout_3", -100),
        (second, "ffa_shutout_4", -300), (second, "ffa_shutout_5", -500)])
    assert state1["balances"] == {first: 4700, second: 3100, SOUND: 800, BYSTANDER: 700}
    assert fp1 != before
    # The second run: classified done, returns before its write half.
    assert err2 is None, err2
    assert any("already applied" in n for n in notices2), notices2
    assert state2 == state1
    assert fp2 == fp1, "a second run of 363 changed a row (value or xmin)"


def test_pg_363_refuses_a_partial_state_and_changes_nothing():
    require_pg()

    async def body(conn):
        await _seed_363(conn)
        await conn.execute("DELETE FROM player_achievements WHERE id = 568")
        before = await conn.fetchval(FINGERPRINT_SQL)
        err, _notices = await _apply_363(conn)
        return err, before, await conn.fetchval(FINGERPRINT_SQL)

    err, before, after = _in_harness(body)
    assert err is not None, "a partial state was applied"
    assert "not all pending" in str(err) and "568=other" in str(err), str(err)
    assert after == before


def test_pg_363_refuses_a_balance_below_the_amount_and_changes_nothing():
    """#326: the GREATEST(0, ...) floor must never be what decides the amount,
    so a holder whose gold_earned is below the gold owed is refused."""
    require_pg()

    async def body(conn):
        _first, second = await _seed_363(conn)
        await conn.execute("UPDATE players SET gold_earned = 800 WHERE id = $1", second)
        before = await conn.fetchval(FINGERPRINT_SQL)
        err, _notices = await _apply_363(conn)
        return err, before, await conn.fetchval(FINGERPRINT_SQL)

    err, before, after = _in_harness(body)
    assert err is not None, "a short balance was clamped instead of refused"
    assert "gold_earned below the amount taken" in str(err), str(err)
    assert after == before


def test_pg_363_leaves_a_database_without_the_holders_alone():
    """The shape of a harness that applies every later migration (the trading
    test's m53): none of the four holders exists, so nothing is written."""
    require_pg()

    async def body(conn):
        await _seed_363(conn, holders=False)
        before = await conn.fetchval(FINGERPRINT_SQL)
        err, notices = await _apply_363(conn)
        return err, notices, before, await conn.fetchval(FINGERPRINT_SQL)

    err, notices, before, after = _in_harness(body)
    assert err is None, err
    assert any("not the production database" in n for n in notices), notices
    assert after == before


def test_pg_a_revoked_key_pays_again_when_it_is_re_earned():
    """After 363 each revoked key has paid 1 / clawed 1, so
    _achievement_payment_eligible owes it again and a legitimate re-earn is
    paid at the current price. Control: a key paid once and never clawed back
    is not owed again, and re-granting it is a no-op."""
    require_pg()

    async def go():
        await _fresh_harness()
        conn = await _bound_raw()
        try:
            _first, second = await _seed_363(conn)
            err, _notices = await _apply_363(conn)
        finally:
            await conn.close()
        engine = _engine()
        sm = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sm() as db:
                eligible = {k: await main._achievement_payment_eligible(db, second, k)
                            for k in SHUTOUT_KEYS}
                sound_eligible = await main._achievement_payment_eligible(
                    db, SOUND, "ffa_shutout_3")
                granted = await main._grant_achievement_inline(db, second, "ffa_shutout_3")
                regranted_sound = await main._grant_achievement_inline(
                    db, SOUND, "ffa_shutout_3")
                await db.commit()
            async with sm() as db:
                ledger = [tuple(r) for r in (await db.execute(text(
                    "SELECT amount, reason FROM gold_transactions"
                    " WHERE player_id = :p AND reference_id = 'ffa_shutout_3' ORDER BY id"),
                    {"p": second})).all()]
                gold = int((await db.execute(text(
                    "SELECT gold_earned FROM players WHERE id = :p"), {"p": second})).scalar())
                sound_ledger = int((await db.execute(text(
                    "SELECT COUNT(*) FROM gold_transactions WHERE player_id = :p"),
                    {"p": SOUND})).scalar())
            return err, eligible, sound_eligible, granted, regranted_sound, ledger, gold, sound_ledger
        finally:
            await engine.dispose()

    (err, eligible, sound_eligible, granted, regranted_sound,
     ledger, gold, sound_ledger) = run(go())
    price = main._achievement_gold("ffa_shutout_3")
    assert err is None, err
    assert eligible == {k: True for k in SHUTOUT_KEYS}
    assert sound_eligible is False
    assert granted is True and regranted_sound is False
    assert ledger == [(100, "achievement"), (-100, "achievement_revoked"), (price, "achievement")]
    assert gold == 3100 + price
    assert sound_ledger == 1
