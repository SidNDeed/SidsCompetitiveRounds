"""2v2 disconnect settlement: the lead-forfeit rule reads a per-game record the
server writes during play, never the DC report's own point snapshot
(v1.41.0 beta review, round 2, finding 1), and names the game by its identity,
never by when a post arrived (the same review, round 1 of the hotfix).

team_series_report_dc completes a series to the team that stayed only when
that team was already a game up AND the abandoned game saw real play (two
points). The second half used to be the report's query-string snapshot, so two
honest survivors holding different snapshots of one game got different
settlements depending on which report took the series lock first. It is now
team_series_games (migrations 348, 351 and 352), written by the team
live-points POST: one row per game, named by the series, its recorded games
plus one and the sitting's room, holding which seat posted which pair, and
which of those posts named their game. A crossing needs a pair of two points
from a seat of each team, and after the first game of the original sitting
only the posts that named their game count: the production client can deliver
a previous game's posts after that game's report, and they name no game
(hotfix round 2). No time is read (main.py, the comment above
_team_game_identity).

STRUCTURAL (always runs, no database): the condition that opens the
lead-forfeit branch asks the per-game record and compares no snapshot.

LIVE (TEAM_DC_TEST_PG_DSN). Row locks, upserts and the record's bit
arithmetic are PostgreSQL behaviour, so these run the real endpoints against a
real server:

    TEAM_DC_TEST_PG_DSN="postgresql+asyncpg://postgres@127.0.0.1:55432/scratch_teamdc" \\
        python -m pytest backend/tests/test_team_series_report_dc.py -q

Every live test builds its own throwaway SCHEMA and drops it afterwards, and
the DSN must name a local database called scratch*/test*. Set
TEAM_DC_TESTS_REQUIRED=1 to make "no DSN" a failure instead of a skip.

What runs as written: POST /team/series/{id}/live-points and
POST /team/series/{id}/report-dc, including the synthetic forfeit row. What is
replaced: the transport seat verdict (always "unbound", so no attestation row
is written) and _complete_team_series_with_ratings (a stub that marks the
series completed and counts its calls). The ratings helper is shared by every
2v2 settlement path and is not what these tests are about.
"""
import ast
import asyncio
import hashlib
import hmac
import inspect
import os
import textwrap
import urllib.parse as _urlparse
import uuid

import pytest
from fastapi import HTTPException

import main
import models

try:
    import asyncpg
except ImportError:                                    # pragma: no cover
    asyncpg = None

DSN_VAR = "TEAM_DC_TEST_PG_DSN"
_RAW_DSN = (os.environ.get(DSN_VAR) or "").strip()
REQUIRED = os.environ.get("TEAM_DC_TESTS_REQUIRED") == "1"

if REQUIRED and not _RAW_DSN:
    raise RuntimeError(
        "TEAM_DC_TESTS_REQUIRED=1 but %s is unset -- refusing to report a green "
        "run for tests that would not run. Check the variable NAME." % DSN_VAR)


def _refuse_unless_throwaway(dsn):
    """These tests create and drop whole schemas. The DSN must name itself
    disposable, on this machine, before anything runs."""
    parsed = _urlparse.urlsplit(dsn)
    try:
        host = (parsed.hostname or "").lower()
    except ValueError:
        host = "?"
    if host not in ("", "localhost", "127.0.0.1", "::1"):
        raise RuntimeError(
            "%s points at host %r. These tests run against a database on this "
            "machine only." % (DSN_VAR, host))
    name = (parsed.path or "").lstrip("/").split("?")[0].strip().lower()
    if not (name.startswith("scratch") or name.startswith("test")):
        raise RuntimeError(
            "%s names database %r; these tests run only against a database "
            "named scratch*/test*." % (DSN_VAR, name))


if _RAW_DSN:
    _refuse_unless_throwaway(_RAW_DSN)

PLAIN_DSN = _RAW_DSN.replace("postgresql+asyncpg://", "postgresql://")
ASYNC_DSN = PLAIN_DSN.replace("postgresql://", "postgresql+asyncpg://", 1)

needs_pg = pytest.mark.skipif(
    not _RAW_DSN or asyncpg is None,
    reason="%s unset (or asyncpg missing); live 2v2 DC settlement check" % DSN_VAR)

SQL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sql")
MIGRATION_348 = os.path.join(SQL_DIR, "348_team_series_games.sql")
# Applied after 348 when present. A tree from before it has no such file, so
# the file also runs, unchanged, against that older tree.
MIGRATION_351 = os.path.join(SQL_DIR, "351_team_series_games_identity.sql")
# Applied after 351 when present: which seat named which game.
MIGRATION_352 = os.path.join(SQL_DIR, "352_team_series_games_attested_seats.sql")

SECRET = "teamdc-test-secret"
ROOM = "teamdc_room"
# The room a relock's next sitting is issued. Like a real one it is not the
# old room with a suffix, so neither room passes for the other.
ROOM_NEXT = "teamdc_next"

# Deliberately outside the real SteamID64 space.
_SID_BASE = 90000000000700000


def _bit(t1, t2, seat):
    """The record's bit for seat `seat` (0..3 = t1a, t1b, t2a, t2b) posting the
    pair t1-t2, each side capped at 2: bit 4 * (3 * t1 + t2) + seat."""
    return 1 << (4 * (3 * min(t1, 2) + min(t2, 2)) + seat)


# -- structural ---------------------------------------------------------------

def _lead_forfeit_if():
    """The `if` whose body writes the synthetic lead-forfeit team_matches row."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(main.team_series_report_dc)))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        body_src = "\n".join(ast.unparse(b) for b in node.body)
        if "INSERT INTO team_matches" in body_src and "dc_leadforfeit" in body_src:
            found.append(node)
    assert len(found) == 1, "expected exactly one lead-forfeit branch, found %d" % len(found)
    return found[0]


def test_the_lead_forfeit_condition_asks_the_per_game_record():
    cond = _lead_forfeit_if().test
    calls = [n.func.id for n in ast.walk(cond)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    assert "_team_game_crossed_two" in calls, ast.unparse(cond)


def test_the_lead_forfeit_condition_compares_no_snapshot():
    """The report's t1/t2_points_total may be LOGGED (they are passed to the
    helper for that), but no comparison in the condition may read them."""
    cond = _lead_forfeit_if().test
    snapshot = {"total_points", "t1_points_total", "t2_points_total"}
    for node in ast.walk(cond):
        if isinstance(node, ast.Compare):
            names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            assert not (names & snapshot), (
                "the lead-forfeit condition compares the report's snapshot: "
                + ast.unparse(node))


def test_the_structural_checks_can_fail():
    """Negative control for the two checks above, on the same code path: the
    pre-fix condition must be flagged by both."""
    pre_fix = ast.parse("(other_team_existing_wins or 0) >= 1 and total_points >= 2",
                        mode="eval").body
    calls = [n.func.id for n in ast.walk(pre_fix)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    assert "_team_game_crossed_two" not in calls
    compared = set()
    for node in ast.walk(pre_fix):
        if isinstance(node, ast.Compare):
            compared |= {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    assert "total_points" in compared


def test_the_live_points_post_raises_the_per_game_record():
    src = inspect.getsource(main.update_team_live_points)
    assert src.count("_record_team_game_points(") == 1, src


# -- live ---------------------------------------------------------------------

_PREREQ = """
ALTER TABLE team_series
    ADD COLUMN IF NOT EXISTS dc_grace_until TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS dc_team_remaining SMALLINT,
    ADD COLUMN IF NOT EXISTS dc_player_id UUID,
    ADD COLUMN IF NOT EXISTS room_issued_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS live_t1_points INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS live_t2_points INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS relocked_at TIMESTAMPTZ;
ALTER TABLE team_matches
    ADD COLUMN IF NOT EXISTS dc_player_id UUID,
    ADD COLUMN IF NOT EXISTS dc_at TIMESTAMPTZ;
"""

# The ORM's defaults are Python-side, and these tests insert with raw SQL, so
# every NOT NULL column without a database default gets one.
_FILL_DEFAULTS = """
DO $fill$
DECLARE r RECORD;
BEGIN
  FOR r IN SELECT table_name AS t, column_name AS c, data_type AS d
             FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND is_nullable = 'NO' AND column_default IS NULL
  LOOP
    EXECUTE format('ALTER TABLE %I ALTER COLUMN %I SET DEFAULT %s', r.t, r.c,
      CASE WHEN r.d LIKE 'timestamp%' THEN 'NOW()'
           WHEN r.d = 'boolean' THEN 'FALSE'
           WHEN r.d IN ('integer','bigint','smallint','numeric','double precision','real') THEN '0'
           WHEN r.d = 'uuid' THEN 'gen_random_uuid()'
           WHEN r.d = 'jsonb' THEN quote_literal('[]')
           WHEN r.d = 'ARRAY' THEN quote_literal('{}')
           ELSE quote_literal('') END);
  END LOOP;
END $fill$;
"""


def _run(coro):
    return asyncio.run(coro)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _live_sig(series_id, reporter, t1, t2, game=None, room=None):
    """The legacy canonical, or the attested one when the post names its game."""
    if game is None and room is None:
        msg = f"team-live-points:{series_id}:{reporter}:{t1}:{t2}"
    else:
        msg = f"team-live-points-game:{series_id}:{reporter}:{t1}:{t2}:{game}:{room}"
    return hmac.new(SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()


def _dc_sig(reporter, series_id, dc_player):
    return hmac.new(SECRET.encode(), f"{reporter}:{series_id}:{dc_player}:dc".encode(),
                    hashlib.sha256).hexdigest()


class _Lab:
    """One throwaway schema holding the tables the two endpoints touch.
    `with_identity=False` stops after migration 348 (the API-before-351
    deploy order), `with_attested_seats=False` after 351 (the API-before-352
    one)."""

    def __init__(self, with_games_table=True, with_identity=True,
                 with_attested_seats=True):
        self.schema = "teamdc_" + uuid.uuid4().hex[:12]
        self.with_games_table = with_games_table
        self.with_identity = with_identity
        self.with_attested_seats = with_attested_seats
        self.engine = None
        self.sm = None
        self._n = 0

    async def __aenter__(self):
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool
        conn = await asyncpg.connect(PLAIN_DSN)
        try:
            await conn.execute('CREATE SCHEMA "%s"' % self.schema)
        finally:
            await conn.close()
        self.engine = create_async_engine(
            ASYNC_DSN, poolclass=NullPool,
            connect_args={"server_settings": {"search_path": self.schema}})
        self.sm = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as c:
            await c.run_sync(models.Base.metadata.create_all,
                             tables=[models.ShopItem.__table__, models.Player.__table__,
                                     models.TeamSeries.__table__, models.TeamMatch.__table__])
        conn = await asyncpg.connect(PLAIN_DSN)
        try:
            await conn.execute('SET search_path TO "%s"' % self.schema)
            await conn.execute(_PREREQ)
            await conn.execute(_FILL_DEFAULTS)
            if self.with_games_table:
                await conn.execute(_read(MIGRATION_348))
                if self.with_identity and os.path.exists(MIGRATION_351):
                    await conn.execute(_read(MIGRATION_351))
                    if self.with_attested_seats and os.path.exists(MIGRATION_352):
                        await conn.execute(_read(MIGRATION_352))
        finally:
            await conn.close()
        return self

    async def __aexit__(self, *exc):
        if self.engine is not None:
            await self.engine.dispose()
        conn = await asyncpg.connect(PLAIN_DSN)
        try:
            await conn.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % self.schema)
        finally:
            await conn.close()

    async def sql(self, stmt, params=None):
        from sqlalchemy import text
        async with self.sm() as db:
            res = await db.execute(text(stmt), params or {})
            rows = res.mappings().all() if res.returns_rows else None
            await db.commit()
            return rows

    async def series(self, *, t1_wins=1, t2_wins=0, game_recorded_secs_ago=600):
        """Four fresh players and an active series in room ROOM. A game
        already recorded gets its team_matches row dated
        `game_recorded_secs_ago` seconds back. The record rule reads no time;
        the date is what the window this rule replaced measured from."""
        self._n += 1
        base = _SID_BASE + self._n * 10
        steams = [str(base + i) for i in range(1, 5)]
        pids = [uuid.uuid4() for _ in range(4)]
        for pid, steam in zip(pids, steams):
            await self.sql("INSERT INTO players (id, steam_id, display_name)"
                           " VALUES (:i, :s, :d)",
                           {"i": pid, "s": steam, "d": "tdc" + steam[-4:]})
        sid = uuid.uuid4()
        await self.sql(
            "INSERT INTO team_series (id, t1a_id, t1b_id, t2a_id, t2b_id,"
            " t1_series_wins, t2_series_wins, status, photon_room_id, created_at)"
            " VALUES (:id, :a, :b, :c, :d, :w1, :w2, 'active', :room,"
            "         NOW() - INTERVAL '30 minutes')",
            {"id": sid, "a": pids[0], "b": pids[1], "c": pids[2], "d": pids[3],
             "w1": t1_wins, "w2": t2_wins, "room": ROOM})
        for g in range(t1_wins + t2_wins):
            await self.record_game(sid, pids, winner=1 if g < t1_wins else 2,
                                   secs_ago=game_recorded_secs_ago, n=g + 1)
        return {"sid": sid, "pids": pids, "steams": steams}

    async def record_game(self, sid, pids, *, winner, secs_ago, n):
        await self.sql(
            "INSERT INTO team_matches (series_id, t1a_id, t1b_id, t2a_id, t2b_id,"
            " t1_rounds_won, t2_rounds_won, winner_team, photon_room_id,"
            " ended_at, created_at)"
            " VALUES (:sid, :a, :b, :c, :d, :r1, :r2, :w, :room,"
            "         NOW() - make_interval(secs => CAST(:ago AS integer)),"
            "         NOW() - make_interval(secs => CAST(:ago AS integer)))",
            {"sid": sid, "a": pids[0], "b": pids[1], "c": pids[2], "d": pids[3],
             "r1": 5 if winner == 1 else 2, "r2": 2 if winner == 1 else 5,
             "w": winner, "room": "%s_g%d_%s" % (ROOM, n, str(sid)[:8]),
             "ago": int(secs_ago)})

    async def relock(self, ser, new_room):
        """A relock as production does it: the room is cleared and relocked_at
        stamped, then the next sitting is issued its own room."""
        await self.sql("UPDATE team_series SET photon_room_id = NULL,"
                       " room_issued_at = NULL, relocked_at = clock_timestamp()"
                       " WHERE id = :sid", {"sid": ser["sid"]})
        await self.sql("UPDATE team_series SET photon_room_id = :r,"
                       " room_issued_at = NOW() WHERE id = :sid",
                       {"sid": ser["sid"], "r": new_room})

    async def win_game(self, ser, *, winner, secs_ago=600):
        """The game in progress is reported: the series counts it and its
        team_matches row is written, as the match report does."""
        col = "t1_series_wins" if winner == 1 else "t2_series_wins"
        await self.sql("UPDATE team_series SET %s = %s + 1 WHERE id = :sid" % (col, col),
                       {"sid": ser["sid"]})
        n = (await self.sql(
            "SELECT t1_series_wins + t2_series_wins AS n FROM team_series"
            " WHERE id = :sid", {"sid": ser["sid"]}))[0]["n"]
        await self.record_game(ser["sid"], ser["pids"], winner=winner,
                               secs_ago=secs_ago, n=n)

    async def post(self, ser, seat, t1, t2, *, game=None, room=None):
        """One team live-points post from seat `seat` (0..3), through the real
        endpoint. With `game`/`room` it is an attested post; without them the
        call is exactly the legacy one, with no extra argument, which is also
        what lets the two review scenarios run against a tree from before the
        fix."""
        reporter = ser["steams"][seat]
        extra = {}
        if game is not None or room is not None:
            extra = {"game_number": game, "photon_room_id": room}
        async with self.sm() as db:
            return await main.update_team_live_points(
                series_id=str(ser["sid"]), request=None, t1_points=t1, t2_points=t2,
                reporter_steam_id=reporter,
                sig=_live_sig(str(ser["sid"]), reporter, t1, t2, game, room),
                db=db, **extra)

    async def report_dc(self, ser, *, reporter_seat, dc_seat, t1_total, t2_total,
                        room=ROOM):
        reporter = ser["steams"][reporter_seat]
        dc = ser["steams"][dc_seat]
        async with self.sm() as db:
            return await main.team_series_report_dc(
                series_id=str(ser["sid"]), reporter_steam_id=reporter,
                dc_player_steam_id=dc, t1_points_total=t1_total,
                t2_points_total=t2_total, photon_room_id=room,
                hmac_sig=_dc_sig(reporter, str(ser["sid"]), dc), db=db)

    async def settlement(self, ser):
        row = (await self.sql(
            "SELECT status, winner_team, dc_team_remaining, invalidation_reason"
            "  FROM team_series WHERE id = :sid", {"sid": ser["sid"]}))[0]
        forfeits = (await self.sql(
            "SELECT count(*) AS n FROM team_matches"
            " WHERE series_id = :sid AND dc_player_id IS NOT NULL",
            {"sid": ser["sid"]}))[0]["n"]
        return (row["status"], row["winner_team"], row["dc_team_remaining"],
                row["invalidation_reason"], forfeits)

    async def game_row(self, ser, ordinal, room=ROOM):
        """The record of game `ordinal` in sitting `room`, every column (they
        differ before and after migration 352), or None."""
        rows = await self.sql(
            "SELECT *"
            "  FROM team_series_games"
            " WHERE series_id = :sid AND game_ordinal = :o AND sitting_room = :r",
            {"sid": ser["sid"], "o": ordinal, "r": room})
        return rows[0] if rows else None

    async def crossed(self, ser):
        """The record rule's verdict for the game in progress, asked the way
        the DC report asks it: under the series row lock, from the row that
        lock pins. Nothing is written."""
        from sqlalchemy import text
        async with self.sm() as db:
            row = (await db.execute(text(
                "SELECT id, status, t1a_id, t1b_id, t2a_id, t2b_id,"
                "       t1_series_wins, t2_series_wins, photon_room_id"
                "  FROM team_series WHERE id = :sid FOR NO KEY UPDATE"),
                {"sid": ser["sid"]})).mappings().first()
            verdict = await main._team_game_crossed_two(db, ser["sid"], row, None)
            await db.rollback()
            return verdict


@pytest.fixture
def wired(monkeypatch):
    """The two stand-ins named in the module docstring, plus the shared secret."""
    completions = []

    async def _unbound(request, steam_id, db):
        return main.SEAT_UNBOUND

    async def _complete(db, series_uuid, winner_team, reason, dc_pid=None):
        from sqlalchemy import text
        await db.execute(text(
            "UPDATE team_series SET status = 'completed', winner_team = :w,"
            " completed_at = NOW() WHERE id = :sid"),
            {"w": winner_team, "sid": series_uuid})
        completions.append((str(series_uuid), winner_team, reason))
        return {}

    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    monkeypatch.setattr(main, "_seat_gate_for_live_points", _unbound)
    monkeypatch.setattr(main, "_complete_team_series_with_ratings", _complete)
    return completions


# Seats: 0,1 = team 1 (already a game up), 2,3 = team 2. Seat 2 leaves.
# The two survivors who report hold different snapshots of the abandoned game
# that straddle the two-point line: 1-1 (two points) and 1-0 (one point).
HIGH = dict(t1_total=1, t2_total=1)
LOW = dict(t1_total=1, t2_total=0)


async def _two_reports(lab, ser, first, second, room=ROOM):
    a = await lab.report_dc(ser, reporter_seat=0, dc_seat=2, room=room, **first)
    b = await lab.report_dc(ser, reporter_seat=1, dc_seat=2, room=room, **second)
    return a, b


@needs_pg
@pytest.mark.parametrize("played", [True, False], ids=["game-crossed-two", "game-did-not"])
def test_the_settlement_is_the_same_whichever_survivor_reports_first(wired, played):
    """The brief's proof. Two equivalent series, the SAME abandoned game
    observed by the live-points channel, two honest survivor snapshots on
    either side of the two-point line, submitted high-first on one series and
    low-first on the other. Before the fix, order decided: high-first completed
    the series with ratings, low-first sent it to dc_incomplete.

    The played game shows 1-1 from a seat of EACH team, each post naming game
    2: one team's seats alone prove nothing, and after the first game of a
    sitting a post that names no game may be the previous game's (hotfix
    round 2)."""
    async def go():
        async with _Lab() as lab:
            outcomes = {}
            for order in ("high-first", "low-first"):
                ser = await lab.series()
                await lab.post(ser, 0, 1, 0)
                if played:
                    await lab.post(ser, 0, 1, 1, game=2, room=ROOM)
                    await lab.post(ser, 2, 1, 1, game=2, room=ROOM)
                first, second = (HIGH, LOW) if order == "high-first" else (LOW, HIGH)
                a, b = await _two_reports(lab, ser, first, second)
                assert b.get("ignored") is True, b    # the second finds it settled
                outcomes[order] = await lab.settlement(ser)
            return outcomes

    outcomes = _run(go())
    assert outcomes["high-first"] == outcomes["low-first"], outcomes
    if played:
        assert outcomes["high-first"] == ("completed", 1, None, None, 1), outcomes
        assert [c[1:] for c in wired] == [(1, "dc_leadforfeit")] * 2, wired
    else:
        assert outcomes["high-first"] == (
            "dc_incomplete", None, 1, "dc_manual_pending", 0), outcomes
        assert wired == [], wired


@needs_pg
def test_the_record_is_per_game_not_the_series_latch(wired):
    """Game 1 crossed two points, then was recorded; nobody has scored in game
    2 when a player leaves. The series-wide live columns still say two points
    (they are the bet cutoff's latch); game 2's record says nothing, and game 2
    is what the rule asks about."""
    async def go():
        async with _Lab() as lab:
            ser = await lab.series(t1_wins=0, t2_wins=0)
            await lab.post(ser, 0, 1, 1)                       # game 1, two points
            await lab.sql("UPDATE team_series SET t1_series_wins = 1 WHERE id = :sid",
                          {"sid": ser["sid"]})
            await lab.record_game(ser["sid"], ser["pids"], winner=1, secs_ago=600, n=1)
            latch = (await lab.sql(
                "SELECT live_t1_points + live_t2_points AS s FROM team_series"
                " WHERE id = :sid", {"sid": ser["sid"]}))[0]["s"]
            g1, g2 = await lab.game_row(ser, 1), await lab.game_row(ser, 2)
            await _two_reports(lab, ser, HIGH, LOW)
            return latch, g1, g2, await lab.settlement(ser)

    latch, g1, g2, settled = _run(go())
    assert latch >= 2
    assert g1 is not None and g1["pair_seats"] == _bit(1, 1, 0), g1
    assert g2 is None, g2
    assert settled[0] == "dc_incomplete", settled


@needs_pg
def test_a_previous_games_post_recorded_after_its_report_does_not_count(wired):
    """A post that left a client during game 1 and landed just after game 1's
    report is filed under game 2 (the server's count has moved on). It carries
    game 1's points: a pair game 1 could have left behind, so it proves
    nothing about game 2, however soon or late after the report it lands."""
    async def go():
        async with _Lab() as lab:
            ser = await lab.series(game_recorded_secs_ago=0)   # report just landed
            await lab.post(ser, 1, 2, 1)                       # game 1's last pair
            row = await lab.game_row(ser, 2)
            await _two_reports(lab, ser, HIGH, HIGH)
            return row, await lab.settlement(ser)

    row, settled = _run(go())
    assert row is not None and row["pair_seats"] == _bit(2, 1, 1), row  # filed under game 2
    assert settled[0] == "dc_incomplete", settled
    assert wired == []


@needs_pg
def test_a_crossing_counts_by_its_pairs_not_by_its_distance_from_the_report(wired):
    """No window. The same stale post on two series, both just after game 1's
    report. On the second, a seat of each team also posts game 2's genuine
    first-round 1-1 straight away, naming game 2, with no wait for any
    window: that series completes, while the stale post alone settles
    nothing."""
    async def go():
        async with _Lab() as lab:
            stale = await lab.series(game_recorded_secs_ago=0)
            await lab.post(stale, 1, 2, 1)
            fresh = await lab.series(game_recorded_secs_ago=0)
            await lab.post(fresh, 1, 2, 1)
            await lab.post(fresh, 0, 1, 1, game=2, room=ROOM)
            await lab.post(fresh, 2, 1, 1, game=2, room=ROOM)
            await _two_reports(lab, stale, LOW, LOW)
            await _two_reports(lab, fresh, LOW, LOW)
            return await lab.settlement(stale), await lab.settlement(fresh)

    stale, fresh = _run(go())
    assert stale[0] == "dc_incomplete", stale
    assert fresh[:2] == ("completed", 1), fresh


@needs_pg
def test_a_relock_opens_the_game_again(wired):
    """A resume replays the same game number in a new sitting: the relock
    clears the room and stamps relocked_at, and the next sitting is issued its
    own room. The dead sitting's game crossed, a seat of each team naming it,
    and that record stays the dead sitting's. Its re-sends landing after the
    relock settle nothing: those naming the dead sitting are filed nowhere,
    and those naming no game are filed under the new sitting's first game,
    where nothing bounds what they carry and only named posts count. The
    control series, identical but never relocked, completes."""
    async def go():
        async with _Lab() as lab:
            relocked = await lab.series()
            for seat in (0, 2):                                # the dead sitting
                await lab.post(relocked, seat, 1, 1, game=2, room=ROOM)
            await lab.relock(relocked, ROOM_NEXT)
            for seat in (0, 2):                                # its re-sends, landing late
                await lab.post(relocked, seat, 1, 1, game=2, room=ROOM)
                await lab.post(relocked, seat, 1, 1)
            control = await lab.series()
            for seat in (0, 2):
                await lab.post(control, seat, 1, 1, game=2, room=ROOM)
            await _two_reports(lab, relocked, HIGH, HIGH, room=ROOM_NEXT)
            await _two_reports(lab, control, LOW, LOW)
            return (await lab.settlement(relocked), await lab.settlement(control),
                    await lab.game_row(relocked, 2), await lab.game_row(relocked, 2, ROOM_NEXT))

    relocked, control, dead_row, next_row = _run(go())
    assert relocked[0] == "dc_incomplete", relocked
    assert control[:2] == ("completed", 1), control
    both = _bit(1, 1, 0) | _bit(1, 1, 2)
    assert (dead_row["pair_seats"], dead_row["attested_seats"]) == (both, both), dead_row
    assert (next_row["pair_seats"], next_row["attested_seats"]) == (both, 0), next_row


@needs_pg
def test_a_post_below_two_never_clears_a_crossing(wired):
    """Bits are only OR-ed: later posts below two points (a relaunched seat's
    lower view, a seat still at 0-0, naming the game or not) add their own
    bits, clear none, and the record still proves the crossing, asked the way
    the DC report asks it."""
    async def go():
        async with _Lab() as lab:
            ser = await lab.series()
            await lab.post(ser, 0, 1, 1, game=2, room=ROOM)
            await lab.post(ser, 2, 1, 1, game=2, room=ROOM)
            before = await lab.game_row(ser, 2)
            await lab.post(ser, 3, 1, 0)
            await lab.post(ser, 1, 0, 0, game=2, room=ROOM)
            after = await lab.game_row(ser, 2)
            return before, after, await lab.crossed(ser)

    before, after, crossed = _run(go())
    both = _bit(1, 1, 0) | _bit(1, 1, 2)
    assert (before["pair_seats"], before["attested_seats"]) == (both, both), before
    assert after["pair_seats"] == both | _bit(1, 0, 3) | _bit(0, 0, 1), after
    assert after["attested_seats"] == both | _bit(0, 0, 1), after
    assert crossed is True


@needs_pg
def test_without_the_table_nothing_fails_and_nothing_auto_completes(wired):
    """The deploy-order claim in migration 348's header: API before migration
    costs no request. The live-points POST still answers, and the DC report
    settles as dc_incomplete."""
    async def go():
        async with _Lab(with_games_table=False) as lab:
            ser = await lab.series()
            posted = await lab.post(ser, 0, 1, 1)
            await _two_reports(lab, ser, HIGH, HIGH)
            return posted, await lab.settlement(ser)

    posted, settled = _run(go())
    assert posted["status"] == "ok", posted
    assert settled[0] == "dc_incomplete", settled


@needs_pg
def test_migration_348_runs_twice(wired):
    async def go():
        async with _Lab() as lab:
            conn = await asyncpg.connect(PLAIN_DSN)
            try:
                await conn.execute('SET search_path TO "%s"' % lab.schema)
                await conn.execute(_read(MIGRATION_348))       # the second run
                return await conn.fetchval(
                    "SELECT count(*) FROM pg_class c JOIN pg_namespace n"
                    "  ON n.oid = c.relnamespace"
                    " WHERE n.nspname = $1 AND c.relname = 'team_series_games'",
                    lab.schema)
            finally:
                await conn.close()

    assert _run(go()) == 1


@needs_pg
def test_a_reporter_on_the_leaving_team_is_still_refused(wired):
    """The F6 gate ahead of the settlement is untouched by this change: a
    report filed from the team that left is a 400, and settles nothing."""
    async def go():
        async with _Lab() as lab:
            ser = await lab.series()
            await lab.post(ser, 0, 1, 1)
            with pytest.raises(HTTPException) as ex:
                await lab.report_dc(ser, reporter_seat=3, dc_seat=2, **HIGH)
            return ex.value, await lab.settlement(ser)

    err, settled = _run(go())
    assert err.status_code == 400 and "non-DC team" in str(err.detail), err
    assert settled[0] == "active", settled


# -- the game is identified, never timed (hotfix round 1) ---------------------
#
# The two scenarios the review raised against the 90-second window, each RED
# on the tree before this round (8af7fb3) and GREEN after, each with a
# mutation control and an inert twin on the same path.

async def _post_all(lab, ser, *pairs, seats=(0, 1, 2, 3), game=None, room=None):
    """Every seat in `seats` posts each pair in turn: the four clients' own
    re-sends of one game's running score, naming `game` and `room` when
    given."""
    for t1, t2 in pairs:
        for seat in seats:
            await lab.post(ser, seat, t1, t2, game=game, room=room)


async def _early_crossing(lab):
    """Scenario (a): game 1 has just been reported, game 2's first round goes
    1-0 then 1-1 straight away with all four seats posting, each post naming
    game 2, then seat 2 leaves."""
    ser = await lab.series(game_recorded_secs_ago=0)
    await _post_all(lab, ser, (1, 0), (1, 1), game=2, room=ROOM)
    await _two_reports(lab, ser, LOW, LOW)
    return await lab.settlement(ser)


async def _late_stale_posts(lab):
    """Scenario (b): game 1 is played through to 2-2 with all four seats
    posting and is reported, its report dated ten minutes back. Game 1's last
    re-sends are processed only now, filed under game 2, and game 2 itself has
    reached 1-0 when seat 2 leaves."""
    ser = await lab.series(t1_wins=0, t2_wins=0)
    await _post_all(lab, ser, (1, 0), (1, 1), (2, 1), (2, 2))
    await lab.win_game(ser, winner=1, secs_ago=600)
    await _post_all(lab, ser, (2, 2), (2, 1))              # game 1's, landing late
    await _post_all(lab, ser, (1, 0))                      # game 2's own
    await _two_reports(lab, ser, LOW, LOW)
    return await lab.settlement(ser)


def _wrap_the_evidence(monkeypatch, mutant=None):
    """Replace main._team_game_evidence by a wrapper that records each call's
    shape and returns `mutant(shape, cur, attested)` when given, else the real
    answer (the inert twin)."""
    real = main._team_game_evidence
    calls = []

    def wrapped(shape, cur_seats, attested_seats):
        calls.append(shape)
        if mutant is not None:
            return mutant(shape, cur_seats, attested_seats)
        return real(shape, cur_seats, attested_seats)

    monkeypatch.setattr(main, "_team_game_evidence", wrapped)
    return calls


@needs_pg
def test_a_crossing_early_in_a_later_game_settles(wired):
    """Review finding 1, scenario (a): a genuine crossing moments after the
    previous game's report. The window discarded it as too close to the
    game's opening; the record proves it, from a seat of each team, each post
    naming its game."""
    async def go():
        async with _Lab() as lab:
            return await _early_crossing(lab)

    settled = _run(go())
    assert settled == ("completed", 1, None, None, 1), settled
    assert [c[1:] for c in wired] == [(1, "dc_leadforfeit")], wired


@needs_pg
@pytest.mark.parametrize("mutant", ["evidence-disabled", "pass-through"])
def test_the_early_crossing_test_can_fail(wired, monkeypatch, mutant):
    """Control for the test above, on its own path: with no post counted as
    evidence the same series settles as dc_incomplete, so the test above
    would fail; the inert twin wraps the real rule, is reached, and changes
    nothing."""
    calls = _wrap_the_evidence(monkeypatch, (lambda shape, cur, att: 0)
                               if mutant == "evidence-disabled" else None)

    async def go():
        async with _Lab() as lab:
            return await _early_crossing(lab)

    settled = _run(go())
    assert calls == ["second"], calls
    if mutant == "evidence-disabled":
        assert settled == ("dc_incomplete", None, 1, "dc_manual_pending", 0), settled
    else:
        assert settled == ("completed", 1, None, None, 1), settled


@needs_pg
def test_a_previous_games_post_never_settles_the_next_game_at_any_delay(wired):
    """Review finding 1, scenario (b): a previous game's posts processed long
    after that game's report. The window counted them as game 2's crossing;
    none of them names a game, so none counts in game 2, whatever the delay,
    and game 2 itself never reached two points."""
    async def go():
        async with _Lab() as lab:
            return await _late_stale_posts(lab)

    settled = _run(go())
    assert settled == ("dc_incomplete", None, 1, "dc_manual_pending", 0), settled
    assert wired == [], wired


_TWO_OR_MORE = sum(0xF << (4 * (3 * a + b))
                   for a in range(3) for b in range(3) if a + b >= 2)


@needs_pg
@pytest.mark.parametrize("mutant", ["any-two-points-count", "pass-through"])
def test_the_stale_post_test_can_fail(wired, monkeypatch, mutant):
    """Control for the test above, on its own path: a rule that counts every
    pair in the game's record, named or not, wherever it came from (the
    two-team rule kept), completes the same series, so the test above would
    fail; the inert twin wraps the real rule, is reached, and changes
    nothing."""
    calls = _wrap_the_evidence(monkeypatch, (lambda shape, cur, att: cur | att)
                               if mutant == "any-two-points-count" else None)

    async def go():
        async with _Lab() as lab:
            return await _late_stale_posts(lab)

    settled = _run(go())
    assert calls == ["second"], calls
    if mutant == "any-two-points-count":
        assert settled == ("completed", 1, None, None, 1), settled
    else:
        assert settled == ("dc_incomplete", None, 1, "dc_manual_pending", 0), settled


@needs_pg
@pytest.mark.parametrize("before, now", [
    (((0, 1), (1, 1), (1, 2), (2, 2)), ((1, 0), (2, 0))),
    (((1, 0), (2, 0), (2, 1), (2, 2)), ((1, 0), (2, 0))),
    (((1, 0), (2, 0), (2, 1), (2, 2)), ((0, 1), (0, 2))),
], ids=["split-before", "same-sweep-before", "other-team-sweeps"])
def test_after_game_one_legacy_first_round_sweeps_settle_nothing(wired, before, now):
    """Round 1 read a first-round sweep (2-0 from every seat) in game 2 as
    proof whenever game 1's record showed game 1 never went through that
    pair. That rested on every seat's game-1 posts being processed before
    game 1's report, which the production client does not guarantee: it
    never withdraws a post once sent. After the first game of a sitting a
    post that names no game proves nothing, whatever the record around it
    shows, so each of these settles the conservative way."""
    async def go():
        async with _Lab() as lab:
            ser = await lab.series(t1_wins=0, t2_wins=0)
            await _post_all(lab, ser, *before)
            await lab.win_game(ser, winner=1)
            await _post_all(lab, ser, *now)
            await _two_reports(lab, ser, LOW, LOW)
            return await lab.settlement(ser)

    settled = _run(go())
    assert settled == ("dc_incomplete", None, 1, "dc_manual_pending", 0), settled


@needs_pg
@pytest.mark.parametrize("named, played", [(False, False), (True, True)],
                         ids=["legacy", "attested"])
def test_after_game_one_a_one_one_counts_only_when_it_names_its_game(wired, named, played):
    """Game 2's first round goes 1-1 and a seat of each team posts it. A 1-1
    exists only in a first round, but the production client can deliver game
    1's own first-round 1-1 after game 1's report (review finding 1), and a
    post that names no game cannot say which game's it is: the legacy posts
    settle nothing. The same posts naming game 2 settle the series."""
    async def go():
        async with _Lab() as lab:
            ser = await lab.series()
            for seat in (0, 2):
                if named:
                    await lab.post(ser, seat, 1, 1, game=2, room=ROOM)
                else:
                    await lab.post(ser, seat, 1, 1)
            await _two_reports(lab, ser, HIGH, HIGH)
            return await lab.settlement(ser)

    settled = _run(go())
    assert settled[:2] == (("completed", 1) if played else ("dc_incomplete", None)), settled


@needs_pg
@pytest.mark.parametrize("now, named, played", [(((1, 0), (1, 1)), True, True),
                                                (((2, 1),), False, False)],
                         ids=["own-crossing", "leftover"])
def test_the_game_after_a_relocked_sittings_first_reads_its_own_record(
        wired, now, named, played):
    """The game after a relocked sitting's first is named by the new
    sitting's room and its own number. Posts naming exactly that, a 1-1 from
    every seat, prove it; a pair the replayed game 1 went on to (2-1),
    naming no game, proves nothing."""
    async def go():
        async with _Lab() as lab:
            ser = await lab.series(t1_wins=0, t2_wins=0)
            await lab.post(ser, 0, 1, 0)                       # the dead sitting
            await lab.relock(ser, ROOM_NEXT)
            await _post_all(lab, ser, (1, 0), (1, 1), (2, 1), (2, 2))   # game 1 again
            await lab.win_game(ser, winner=1)
            await _post_all(lab, ser, *now,
                            **({"game": 2, "room": ROOM_NEXT} if named else {}))
            await _two_reports(lab, ser, LOW, LOW, room=ROOM_NEXT)
            return await lab.settlement(ser)

    settled = _run(go())
    assert settled[:2] == (("completed", 1) if played else ("dc_incomplete", None)), settled


@needs_pg
@pytest.mark.parametrize("attested", [True, False], ids=["attested", "legacy"])
def test_an_attested_post_settles_the_first_game_of_a_relocked_sitting(wired, attested):
    """The first game of a relocked sitting takes no legacy proof: the dead
    sitting's posts can land in its record carrying anything. A post naming
    its game and sitting is filed only when it is exactly that game, so a 1-1
    named so by a seat of each team proves the game crossed. The same posts
    without the names settle nothing."""
    async def go():
        async with _Lab() as lab:
            ser = await lab.series()
            await lab.relock(ser, ROOM_NEXT)
            for seat in (0, 2):
                if attested:
                    await lab.post(ser, seat, 1, 1, game=2, room=ROOM_NEXT)
                else:
                    await lab.post(ser, seat, 1, 1)
            row = await lab.game_row(ser, 2, ROOM_NEXT)
            await _two_reports(lab, ser, LOW, LOW, room=ROOM_NEXT)
            return row, await lab.settlement(ser)

    row, settled = _run(go())
    assert row["pair_seats"] == _bit(1, 1, 0) | _bit(1, 1, 2), row
    assert row["attested_seats"] == (row["pair_seats"] if attested else 0), row
    assert settled[:2] == (("completed", 1) if attested else ("dc_incomplete", None)), settled


@needs_pg
def test_an_attested_post_for_another_game_or_sitting_is_not_filed(wired):
    """An attested post is filed only under exactly the game and sitting it
    names: game 1's post processed during game 2, and a post naming another
    room, are accepted and leave no trace in any record. A room carrying a
    suffix after the stored one (the report-room grammar team_series_report_dc
    also accepts) is the same sitting: with a seat of the other team naming
    the same game, the record proves the crossing."""
    async def go():
        async with _Lab() as lab:
            ser = await lab.series()                           # game 2, in ROOM
            prev_game = await lab.post(ser, 0, 2, 1, game=1, room=ROOM)
            other_room = await lab.post(ser, 1, 1, 1, game=2, room=ROOM_NEXT)
            untouched = (await lab.game_row(ser, 1), await lab.game_row(ser, 2),
                         await lab.game_row(ser, 2, ROOM_NEXT))
            await lab.post(ser, 1, 1, 1, game=2, room=ROOM + "_1")
            await lab.post(ser, 2, 1, 1, game=2, room=ROOM)
            filed = await lab.game_row(ser, 2)
            await _two_reports(lab, ser, LOW, LOW)
            return prev_game, other_room, untouched, filed, await lab.settlement(ser)

    prev_game, other_room, untouched, filed, settled = _run(go())
    assert prev_game["status"] == "ok" and other_room["status"] == "ok"
    assert untouched == (None, None, None), untouched
    both = _bit(1, 1, 1) | _bit(1, 1, 2)
    assert filed["pair_seats"] == both and filed["attested_seats"] == both, filed
    assert settled[:2] == ("completed", 1), settled


@pytest.mark.parametrize("fields, signed_as, status", [
    ({"game_number": 2, "photon_room_id": None}, "legacy", 400),
    ({"game_number": None, "photon_room_id": ROOM}, "legacy", 400),
    ({"game_number": 2, "photon_room_id": "  "}, "legacy", 400),
    ({"game_number": 2, "photon_room_id": ROOM}, "legacy", 403),
    ({}, "attested", 403),
], ids=["game-only", "room-only", "blank-room", "legacy-signature", "fields-missing"])
def test_a_half_or_missigned_attestation_is_refused(monkeypatch, fields, signed_as, status):
    """Both fields or neither, and the signature covers what was sent: a
    legacy signature does not carry the two fields, and an attested one does
    not stand in for a legacy post. Refused before the database is touched."""
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    sid, reporter = str(uuid.uuid4()), str(_SID_BASE + 9)
    sig = (_live_sig(sid, reporter, 1, 1) if signed_as == "legacy"
           else _live_sig(sid, reporter, 1, 1, 2, ROOM))
    with pytest.raises(HTTPException) as ex:
        _run(main.update_team_live_points(
            series_id=sid, request=None, t1_points=1, t2_points=1,
            reporter_steam_id=reporter, sig=sig, db=None, **fields))
    assert ex.value.status_code == status, ex.value.detail


@needs_pg
def test_migration_351_runs_twice_over_a_348_table(wired):
    """351 over a 348 table that already holds a row: the row survives, keyed
    by sitting '' (which the rule never reads), the window's columns are
    gone, the new columns are bounded, and a second run of 351, then of 348,
    changes nothing."""
    async def state(conn):
        cols = [r["column_name"] for r in await conn.fetch(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = current_schema() AND table_name = 'team_series_games'"
            " ORDER BY ordinal_position")]
        cons = [(r["conname"], r["def"]) for r in await conn.fetch(
            "SELECT conname, pg_get_constraintdef(oid) AS def FROM pg_constraint"
            " WHERE conrelid = 'team_series_games'::regclass ORDER BY conname")]
        rows = [tuple(r) for r in await conn.fetch(
            "SELECT series_id, game_ordinal, sitting_room, pair_seats, attested_max_sum"
            "  FROM team_series_games ORDER BY game_ordinal, sitting_room")]
        return cols, cons, rows

    async def go():
        async with _Lab(with_identity=False) as lab:
            ser = await lab.series()
            conn = await asyncpg.connect(PLAIN_DSN)
            try:
                await conn.execute('SET search_path TO "%s"' % lab.schema)
                await conn.execute(
                    "INSERT INTO team_series_games (series_id, game_ordinal,"
                    " max_points_sum, crossed_at) VALUES ($1, 2, 3, NOW())", ser["sid"])
                await conn.execute(_read(MIGRATION_351))
                first = await state(conn)
                await conn.execute(_read(MIGRATION_351))
                await conn.execute(_read(MIGRATION_348))
                second = await state(conn)
                refused = []
                for bad in ("pair_seats = 68719476736", "pair_seats = -1",
                            "attested_max_sum = 5"):
                    try:
                        await conn.execute("UPDATE team_series_games SET %s" % bad)
                    except asyncpg.CheckViolationError:
                        refused.append(bad)
                return ser["sid"], first, second, refused
            finally:
                await conn.close()

    sid, first, second, refused = _run(go())
    cols, cons, rows = first
    assert "crossed_at" not in cols and "max_points_sum" not in cols, cols
    assert {"sitting_room", "pair_seats", "attested_max_sum"} <= set(cols), cols
    assert [c for c in cons if c[1].startswith("PRIMARY KEY")] == [
        ("team_series_games_sitting_pkey",
         "PRIMARY KEY (series_id, game_ordinal, sitting_room)")], cons
    assert rows == [(sid, 2, "", 0, 0)], rows
    assert second == first
    assert len(refused) == 3, refused


@needs_pg
def test_before_migration_351_nothing_fails_and_nothing_auto_completes(wired):
    """The deploy-order claim in 351's header: this API against a database
    with 348 but not 351 records nothing and reads nothing, fails no request,
    and the DC report settles as dc_incomplete even on a game a seat of each
    team posted 1-1 in, naming it, which settles the series once every
    migration is in."""
    async def go():
        async with _Lab(with_identity=False) as lab:
            ser = await lab.series()
            posted = [await lab.post(ser, seat, 1, 1, game=2, room=ROOM)
                      for seat in (0, 2)]
            await _two_reports(lab, ser, LOW, LOW)
            rows = (await lab.sql("SELECT count(*) AS n FROM team_series_games"))[0]["n"]
            return posted, rows, await lab.settlement(ser)

    posted, rows, settled = _run(go())
    assert [p["status"] for p in posted] == ["ok", "ok"], posted
    assert rows == 0, rows
    assert settled[0] == "dc_incomplete", settled


# -- the rule against an independent model of what a record can hold ---------
#
# The live tests above pin individual histories. These enumerate them, in
# pairs and seats rather than masks, under the delivery assumption the
# production client supports (main.py, the comment above
# _team_game_identity): none. A post that names no game may be filed in any
# later game's record, from any seat, carrying any pair. A post naming its
# game is filed only under that game, and an honest seat names only its own
# view of it: the true score, or a lower one (a relaunched client counts
# from 0-0). One seat per game may post anything at all.

_PAIRS = [(a, b) for a in range(3) for b in range(3)]
_SHAPES = ("first", "second", "later", "after-relock", "unclean")


def _seat_bits(seat, pairs):
    m = 0
    for t1, t2 in pairs:
        m |= _bit(t1, t2, seat)
    return m


def _all_seats(pairs, seats=(0, 1, 2, 3)):
    m = 0
    for seat in seats:
        m |= _seat_bits(seat, pairs)
    return m


def _at_most(p, q):
    return p[0] <= q[0] and p[1] <= q[1]


def _verdict(shape, legacy, attested):
    """main's rule on a record whose posts named no game (`legacy`) and named
    this one (`attested`); pair_seats holds both, as the writer sets it."""
    evidence = main._team_game_evidence(shape, legacy | attested, attested)
    return main._team_game_both_teams_reached_two(evidence)


def _uncrossed_records(shape):
    """The fullest records a game that never reached two points can leave,
    for each side that scored its first point and each seat allowed to post
    anything (or none). Outside "first", legacy bits from every seat at every
    pair: nothing bounds a previous game's late posts. In "first" nothing was
    posted before the game, so the legacy posts are the seats' views too."""
    anything = set(_PAIRS)
    for first_side in (1, 2):
        top = (1, 0) if first_side == 1 else (0, 1)
        honest = {p for p in _PAIRS if _at_most(p, top)}
        for odd in (None, 0, 1, 2, 3):
            views = 0
            for seat in range(4):
                views |= _seat_bits(seat, anything if seat == odd else honest)
            legacy = views if shape == "first" else _all_seats(anything)
            yield first_side, odd, legacy, views


def _model_counterexamples(stop_at_first=False):
    """Records of a game that never reached two points that main's rule
    would settle as played."""
    found = []
    for shape in _SHAPES:
        for first_side, odd, legacy, attested in _uncrossed_records(shape):
            if _verdict(shape, legacy, attested):
                found.append((shape, first_side, odd))
                if stop_at_first:
                    return found
    return found


def test_the_record_rule_is_sound_without_a_delivery_bound():
    """Exhaustively: whichever side scored first, whichever seat posts
    anything, and -- after the first game of the original sitting -- every
    legacy post any seat could have left in flight, a game that never reached
    two points is never settled as played. The rule reads no delivery order
    and no time."""
    assert len(list(_uncrossed_records("second"))) == 10
    assert _model_counterexamples() == []


@pytest.mark.parametrize("mutant", ["one-seat-suffices", "legacy-in-every-game",
                                    "pass-through"])
def test_the_soundness_check_can_fail(monkeypatch, mutant):
    """Control for the test above: a rule that takes one seat's pair of two
    points as proof, or reads a post naming no game in every game (round 1's
    attribution by arrival, the two-team rule kept), is caught; the inert
    twin sets the real functions and finds nothing."""
    if mutant == "one-seat-suffices":
        monkeypatch.setattr(main, "_team_game_both_teams_reached_two",
                            lambda seats: bool(seats & _TWO_OR_MORE))
    elif mutant == "legacy-in-every-game":
        monkeypatch.setattr(main, "_team_game_evidence",
                            lambda shape, cur, att: cur | att)
    else:
        monkeypatch.setattr(main, "_team_game_both_teams_reached_two",
                            main._team_game_both_teams_reached_two)
        monkeypatch.setattr(main, "_team_game_evidence", main._team_game_evidence)
    found = _model_counterexamples(stop_at_first=mutant != "pass-through")
    assert bool(found) == (mutant != "pass-through"), found[:3]


def test_both_teams_named_posts_prove_a_crossing_in_every_shape():
    """What a record CAN prove: a first-round 1-1 from a seat of each team,
    naming its game, in every shape; the same posts naming no game only in
    the first game of the original sitting; two seats of one team nowhere,
    named or not."""
    each_team = _all_seats([(1, 0), (1, 1)], seats=(0, 2))
    one_team = _all_seats([(1, 0), (1, 1)], seats=(0, 1))
    for shape in _SHAPES:
        assert _verdict(shape, 0, each_team), shape
        assert _verdict(shape, each_team, 0) == (shape == "first"), shape
        assert not _verdict(shape, one_team, one_team), shape


def test_the_ambiguous_case_is_identical_bit_for_bit():
    """Why a post that names no game cannot count after game 1. Game 1 began
    with team 1 sweeping round 1 and went on; game 2 begins the same way.
    Game 2's legacy record when it really swept round 1, and its record when
    it only reached 1-0 and every 2-0 in it is game 1's re-send landing late,
    are the same bits, so the rule must give the conservative answer. The
    same posts naming game 2 remove the case."""
    crossed = _all_seats([(0, 0), (1, 0), (2, 0)])
    stayed_below = _all_seats([(0, 0), (1, 0)]) | _all_seats([(2, 0)])
    assert crossed == stayed_below
    for shape in ("second", "later"):
        assert not _verdict(shape, crossed, 0), shape
        assert _verdict(shape, 0, crossed), shape


def test_the_shape_names_what_can_reach_a_record():
    shape = main._team_game_shape
    assert [shape(True, n, 1) for n in (1, 2, 3)] == ["first", "second", "later"]
    assert shape(False, 2, None) == "unclean"          # nothing on record here yet
    assert shape(False, 2, 2) == "unclean"             # the sitting's first game
    assert shape(False, 3, 2) == "after-relock"
    assert shape(False, 3, 1) == "later"
