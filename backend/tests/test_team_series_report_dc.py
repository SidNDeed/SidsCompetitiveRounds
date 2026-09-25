"""2v2 disconnect settlement: the lead-forfeit rule reads a per-game record the
server writes during play, never the DC report's own point snapshot
(v1.41.0 beta review, round 2, finding 1), and names the game by its identity,
never by when a post arrived (the same review, round 1 of the hotfix).

team_series_report_dc completes a series to the team that stayed only when
that team was already a game up AND the abandoned game saw real play (two
points). The second half used to be the report's query-string snapshot, so two
honest survivors holding different snapshots of one game got different
settlements depending on which report took the series lock first. It is now
team_series_games (migrations 348 and 351), written by the team live-points
POST: one row per game, named by the series, its recorded games plus one and
the sitting's room, holding which seat posted which pair. The DC report asks
whether any history in which the game did not reach two points could have
produced that record. No time is read (main.py, the comment above
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


def _live_sig(series_id, reporter, t1, t2):
    return hmac.new(SECRET.encode(),
                    f"team-live-points:{series_id}:{reporter}:{t1}:{t2}".encode(),
                    hashlib.sha256).hexdigest()


def _dc_sig(reporter, series_id, dc_player):
    return hmac.new(SECRET.encode(), f"{reporter}:{series_id}:{dc_player}:dc".encode(),
                    hashlib.sha256).hexdigest()


class _Lab:
    """One throwaway schema holding the tables the two endpoints touch.
    `with_identity=False` stops after migration 348 (the API-before-351
    deploy order)."""

    def __init__(self, with_games_table=True, with_identity=True):
        self.schema = "teamdc_" + uuid.uuid4().hex[:12]
        self.with_games_table = with_games_table
        self.with_identity = with_identity
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

    async def post(self, ser, seat, t1, t2):
        """One team live-points post from seat `seat` (0..3), through the real
        endpoint."""
        reporter = ser["steams"][seat]
        async with self.sm() as db:
            return await main.update_team_live_points(
                series_id=str(ser["sid"]), request=None, t1_points=t1, t2_points=t2,
                reporter_steam_id=reporter,
                sig=_live_sig(str(ser["sid"]), reporter, t1, t2), db=db)

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
        rows = await self.sql(
            "SELECT game_ordinal, sitting_room, pair_seats, attested_max_sum"
            "  FROM team_series_games"
            " WHERE series_id = :sid AND game_ordinal = :o AND sitting_room = :r",
            {"sid": ser["sid"], "o": ordinal, "r": room})
        return rows[0] if rows else None


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

    The played game shows 1-1 from TWO seats. A 1-1 from one seat alone could
    be the previous game's irregular seat (a relaunched or late-starting
    client) and proves nothing; two seats cannot both be."""
    async def go():
        async with _Lab() as lab:
            outcomes = {}
            for order in ("high-first", "low-first"):
                ser = await lab.series()
                await lab.post(ser, 0, 1, 0)
                if played:
                    await lab.post(ser, 0, 1, 1)
                    await lab.post(ser, 1, 1, 1)
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
    report. On the second, two seats also post game 2's genuine first-round
    1-1 straight away, with no wait for any window: that series completes,
    while the stale post alone settles nothing."""
    async def go():
        async with _Lab() as lab:
            stale = await lab.series(game_recorded_secs_ago=0)
            await lab.post(stale, 1, 2, 1)
            fresh = await lab.series(game_recorded_secs_ago=0)
            await lab.post(fresh, 1, 2, 1)
            await lab.post(fresh, 0, 1, 1)
            await lab.post(fresh, 2, 1, 1)
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
    own room. The dead sitting's posts that land after that are filed under
    the new sitting's first game, where nothing bounds what they carry, so
    even two seats' 1-1 there settles nothing. The control series, identical
    but never relocked, completes."""
    async def go():
        async with _Lab() as lab:
            relocked = await lab.series()
            await lab.post(relocked, 0, 1, 1)                  # the dead sitting
            await lab.relock(relocked, ROOM_NEXT)
            await lab.post(relocked, 0, 1, 1)                  # its re-sends, landing late
            await lab.post(relocked, 1, 1, 1)
            control = await lab.series()
            await lab.post(control, 0, 1, 1)
            await lab.post(control, 1, 1, 1)
            await _two_reports(lab, relocked, HIGH, HIGH, room=ROOM_NEXT)
            await _two_reports(lab, control, LOW, LOW)
            return (await lab.settlement(relocked), await lab.settlement(control),
                    await lab.game_row(relocked, 2), await lab.game_row(relocked, 2, ROOM_NEXT))

    relocked, control, dead_row, next_row = _run(go())
    assert relocked[0] == "dc_incomplete", relocked
    assert control[:2] == ("completed", 1), control
    assert dead_row["pair_seats"] == _bit(1, 1, 0), dead_row
    assert next_row["pair_seats"] == _bit(1, 1, 0) | _bit(1, 1, 1), next_row


@needs_pg
def test_a_post_below_two_never_clears_a_crossing(wired):
    """Bits are only OR-ed: later posts below two points (a relaunched seat's
    lower view, a seat still at 0-0) add their own bits, clear none, and the
    record still proves the crossing."""
    async def go():
        async with _Lab() as lab:
            ser = await lab.series()
            await lab.post(ser, 0, 1, 1)
            await lab.post(ser, 1, 1, 1)
            before = await lab.game_row(ser, 2)
            await lab.post(ser, 3, 1, 0)
            await lab.post(ser, 2, 0, 0)
            after = await lab.game_row(ser, 2)
            return before, after

    before, after = _run(go())
    assert before["pair_seats"] == _bit(1, 1, 0) | _bit(1, 1, 1), before
    assert after["pair_seats"] == (before["pair_seats"] | _bit(1, 0, 3)
                                   | _bit(0, 0, 2)), after
    assert after["attested_max_sum"] == 0, after
    assert not main._team_game_unplayed_fits("second", after["pair_seats"], 0)


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
