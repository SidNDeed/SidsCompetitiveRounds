"""2v2 disconnect settlement: the lead-forfeit rule reads a per-game record the
server writes during play, never the DC report's own point snapshot
(v1.41.0 beta review, round 2, finding 1), and names the game by its identity,
never by when a post arrived (the same review, round 1 of the hotfix).

team_series_report_dc completes a series to the team that stayed only when
that team was already a game up AND the abandoned game saw real play (two
points). The second half used to be the report's query-string snapshot, so two
honest survivors holding different snapshots of one game got different
settlements depending on which report took the series lock first. It is now
team_series_games (migrations 348, 351, 352 and 354), written by the team
live-points POST: one row per game, named by the series, its recorded games
plus one and the sitting's room, holding which seat posted which pair, which
of those posts named their game, and which carried the physical game's token.
A crossing needs a pair of two points from a seat of each team, and after the
first game of the original sitting only the posts that named their game
count: the production client can deliver a previous game's posts after that
game's report, and they name no game (hotfix round 2). Of those, only the
posts that carried the token of the physical game the DC report names are
read, and only when no other token was filed under the game and the token is
on no other game of the series: a game's report can land after the next
physical game has started, and both games then name the same number (beta
round 4 review, F25). No time is read (main.py, the comment above
_team_game_identity). Since beta round 8 (F31) a token is read only when it
is counted from the series' physical game 1 on record (migration 359's
first_game_nonce), and since round 9 (M2) a later game's nonce is derived
from the whole of it and the token's own ordinal and epoch. Since round 11
nothing issues or names a physical game 1 (M1, route (a)): no statement of
the API writes first_game_nonce, so every series is tokenless and every
leave goes to an admin. The lab writes an origin directly (LAB_FIRST) to
exercise the readers of one.

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

What runs as written: POST /team/series/{id}/live-points,
POST /team/series/{id}/report-dc, including the synthetic forfeit row, and
the lobby resolve's read of a team seat (round 11). What is replaced: for
the lobby resolve, the Steam session check (the `resolving` fixture); for
all of them, the transport seat verdict (always "unbound", so no attestation row
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
import re
import textwrap
import types
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
# Applied after 352 when present: which physical game (beta round 5, F25).
MIGRATION_354 = os.path.join(SQL_DIR, "354_team_series_games_game_token.sql")
# Applied after 354 when present: the series' physical game 1 (beta round 8,
# F31; written by no statement of the API since round 11).
MIGRATION_359 = os.path.join(SQL_DIR, "359_team_series_first_game_nonce.sql")

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


# -- the physical game's token (beta round 5, F25) ------------------------------
#
# The room's host publishes a token for every physical game and every seat
# carries that one value. In the lab a physical game is, by default, the game
# number a post names in its sitting, and _tok is its token: every post naming
# that game carries it, and a DC report carries the one of the game in
# progress. A test models two physical games that share a game number (F25) by
# giving each its own token explicitly, and an old client by token=None.

_AUTO = object()

# Round 8, finding F31: a DC report's token is read only when it is counted
# from the series' physical game 1 on record (main._team_game_first_game_refusal,
# migration 359's first_game_nonce). Since round 11 no statement of the API
# writes one (route (a): nothing issues or names a physical game 1), so the
# lab writes LAB_FIRST directly on every lab series unless a test says
# otherwise: the tests of the token's readers from before round 11 read what
# they read before, and the round-11 tests below model the product, where no
# series has one. Since round 9 (finding M2) game 1's token carries the
# origin itself and every later game's nonce is derived from the whole of it
# and the token's own ordinal and epoch (main._team_game_chain_nonce; _chain
# below, computed apart from it).
LAB_FIRST = "5eed1ab00f1e2d3c"


def _sitting(room):
    """The sitting a room names: the suffix grammar the server accepts
    (_team_game_same_sitting) makes ROOM + "_1" the sitting of ROOM."""
    for base in (ROOM_NEXT, ROOM):
        if room == base or room.startswith(base + "_"):
            return base
    return room


def _wire(nonce, game, epoch=None):
    """A token as a post or a DC report sends it (round 6, finding F27):
    'nonce:ordinal:epoch', naming game `game`; the epoch is the game's own
    number unless given."""
    return "%s:%d:%d" % (nonce, game, game if epoch is None else epoch)


def _nonce(token):
    """The part of a token the record keeps (migration 354's game_token)."""
    return token.split(":", 1)[0]


def _chain(issued, ordinal, epoch):
    """Round 9, finding M2: the nonce physical game `ordinal`'s token carries
    when it is published with `epoch`, counted from the issued nonce
    `issued`, computed here apart from main._team_game_chain_nonce: `issued`
    itself for game 1, else the first 16 hex digits of HMAC-SHA256 keyed by
    the 16 ASCII digits of `issued` over 'team-game-chain:{ordinal}:{epoch}'."""
    if ordinal == 1:
        return issued
    message = ("team-game-chain:%d:%d" % (ordinal, epoch)).encode("ascii")
    return hmac.new(issued.encode("ascii"), message, hashlib.sha256).hexdigest()[:16]


def _cwire(issued, game, epoch=None):
    """A token counted from `issued` (round 9, M2) naming game `game` with
    `epoch` (the game's own number unless given): its nonce is _chain's."""
    epoch = game if epoch is None else epoch
    return _wire(_chain(issued, game, epoch), game, epoch)


def _tok(sid, game, room):
    """The lab's token for game `game` of the sitting of `room`, naming that
    game, counted from the series' issued physical game 1 (LAB_FIRST). Its
    epoch is drawn from the series, the game and the sitting, so each
    sitting's token of a later game differs (round 9, M2: the nonce is
    derived from the epoch)."""
    epoch = 1 + int(hashlib.sha256(("%s:%s:%s" % (sid, game, _sitting(room))).encode())
                    .hexdigest()[:7], 16)
    return _cwire(LAB_FIRST, game, epoch)


def _token_sig(series_id, reporter, t1, t2, game, room, token):
    msg = f"team-live-points-token:{series_id}:{reporter}:{t1}:{t2}:{game}:{room}:{token}"
    return hmac.new(SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()


def _dc_token_sig(reporter, series_id, dc_player, token):
    msg = f"team-dc-token:{reporter}:{series_id}:{dc_player}:{token}"
    return hmac.new(SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()


def _takes(fn, name):
    """Whether `fn` has a parameter `name`: a tree from before the token has
    none, and is then called exactly as before."""
    return name in inspect.signature(fn).parameters


class _Lab:
    """One throwaway schema holding the tables the two endpoints touch.
    `with_identity=False` stops after migration 348 (the API-before-351
    deploy order), `with_attested_seats=False` after 351 (the API-before-352
    one), `with_game_token=False` after 352 (the API-before-354 one),
    `with_first_game=False` after 354 (the API-before-359 one)."""

    def __init__(self, with_games_table=True, with_identity=True,
                 with_attested_seats=True, with_game_token=True, with_first_game=True):
        self.schema = "teamdc_" + uuid.uuid4().hex[:12]
        self.with_games_table = with_games_table
        self.with_identity = with_identity
        self.with_attested_seats = with_attested_seats
        self.with_game_token = with_game_token
        self.with_first_game = with_first_game
        self.first_game_applied = False
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
                        if self.with_game_token and os.path.exists(MIGRATION_354):
                            await conn.execute(_read(MIGRATION_354))
                            if self.with_first_game and os.path.exists(MIGRATION_359):
                                await conn.execute(_read(MIGRATION_359))
                                self.first_game_applied = True
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

    async def series(self, *, t1_wins=1, t2_wins=0, game_recorded_secs_ago=600,
                     same_four_as=None, granted=True):
        """Four fresh players (or, with same_four_as, the same four in the same
        slots as an earlier series) and an active series in room ROOM. A game
        already recorded gets its team_matches row dated
        `game_recorded_secs_ago` seconds back. The record rule reads no time;
        the date is what the window this rule replaced measured from. Once
        migration 359 is applied the lab writes the series' physical game 1,
        LAB_FIRST, directly (round 8, F31; no statement of the API writes one
        since round 11), unless `granted` is false: a product series."""
        if same_four_as is not None:
            steams, pids = same_four_as["steams"], same_four_as["pids"]
        else:
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
        if granted and self.first_game_applied:
            await self.sql("UPDATE team_series SET first_game_nonce = :n WHERE id = :sid",
                           {"sid": sid, "n": LAB_FIRST})
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

    async def first_game(self, ser):
        """The series' first_game_nonce (migration 359)."""
        return (await self.sql("SELECT first_game_nonce FROM team_series WHERE id = :sid",
                               {"sid": ser["sid"]}))[0]["first_game_nonce"]

    async def post(self, ser, seat, t1, t2, *, game=None, room=None, token=_AUTO,
                   token_sig=_AUTO):
        """One team live-points post from seat `seat` (0..3), through the real
        endpoint. With `game`/`room` it is an attested post; without them the
        call is exactly the legacy one, with no extra argument, which is also
        what lets the two review scenarios run against a tree from before the
        fix. An attested post carries the physical game's token: by default
        the lab's (_tok), None for a client that sends none, or the one given;
        `token_sig` replaces its signature."""
        reporter = ser["steams"][seat]
        extra = {}
        if game is not None or room is not None:
            extra = {"game_number": game, "photon_room_id": room}
        if token is _AUTO:
            token = _tok(ser["sid"], game, room) if game is not None and room else None
        if token is not None and _takes(main.update_team_live_points, "game_token"):
            extra["game_token"] = token
            extra["token_sig"] = (
                _token_sig(str(ser["sid"]), reporter, t1, t2, game, room, token)
                if token_sig is _AUTO else token_sig)
        async with self.sm() as db:
            return await main.update_team_live_points(
                series_id=str(ser["sid"]), request=None, t1_points=t1, t2_points=t2,
                reporter_steam_id=reporter,
                sig=_live_sig(str(ser["sid"]), reporter, t1, t2, game, room),
                db=db, **extra)

    async def current_token(self, ser):
        """The lab's token of the game in progress: the series' recorded
        games plus one, in the stored sitting (None while no room is stored)."""
        row = (await self.sql(
            "SELECT t1_series_wins + t2_series_wins AS n, photon_room_id AS room"
            "  FROM team_series WHERE id = :sid", {"sid": ser["sid"]}))[0]
        return _tok(ser["sid"], row["n"] + 1, row["room"]) if row["room"] else None

    async def report_dc(self, ser, *, reporter_seat, dc_seat, t1_total, t2_total,
                        room=ROOM, token=_AUTO, token_sig=_AUTO):
        """A DC report through the real endpoint. It names the token of the
        physical game its reporter is in: by default the lab's token of the
        game in progress, None for a client that sends none, or the one
        given; `token_sig` replaces its signature."""
        reporter = ser["steams"][reporter_seat]
        dc = ser["steams"][dc_seat]
        if token is _AUTO:
            token = await self.current_token(ser)
        extra = {}
        if token is not None and _takes(main.team_series_report_dc, "game_token"):
            extra = {"game_token": token,
                     "token_sig": (_dc_token_sig(reporter, str(ser["sid"]), dc, token)
                                   if token_sig is _AUTO else token_sig)}
        async with self.sm() as db:
            return await main.team_series_report_dc(
                series_id=str(ser["sid"]), reporter_steam_id=reporter,
                dc_player_steam_id=dc, t1_points_total=t1_total,
                t2_points_total=t2_total, photon_room_id=room,
                hmac_sig=_dc_sig(reporter, str(ser["sid"]), dc), db=db, **extra)

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

    async def crossed(self, ser, token=_AUTO):
        """The record rule's verdict for the game in progress, asked the way
        the DC report asks it: under the series row lock, from the row that
        lock pins, for the token a report would name (by default the lab's
        token of the game in progress). Nothing is written."""
        from sqlalchemy import text
        async with self.sm() as db:
            row = (await db.execute(text(
                "SELECT id, status, t1a_id, t1b_id, t2a_id, t2b_id,"
                "       t1_series_wins, t2_series_wins, photon_room_id"
                "  FROM team_series WHERE id = :sid FOR NO KEY UPDATE"),
                {"sid": ser["sid"]})).mappings().first()
            if token is _AUTO:
                token = (_tok(ser["sid"], row["t1_series_wins"] + row["t2_series_wins"] + 1,
                              row["photon_room_id"]) if row["photon_room_id"] else None)
            # Round 6: the DC route hands the reader the token as it verified
            # it, (nonce, ordinal, epoch).
            parse = getattr(main, "_team_game_wire_token", None)
            if parse is not None and token is not None:
                token = parse(token)
            extra = {"token": token} if _takes(main._team_game_crossed_two, "token") else {}
            verdict = await main._team_game_crossed_two(db, ser["sid"], row, None, **extra)
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


async def _two_reports(lab, ser, first, second, room=ROOM, token=_AUTO):
    a = await lab.report_dc(ser, reporter_seat=0, dc_seat=2, room=room, token=token, **first)
    b = await lab.report_dc(ser, reporter_seat=1, dc_seat=2, room=room, token=token, **second)
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


@needs_pg
def test_the_same_four_can_lead_forfeit_twice(wired):
    """team_matches is UNIQUE on (photon_room_id, t1a_id, t1b_id, t2a_id,
    t2b_id), and the lead-forfeit writes a synthetic row. Its room is per
    series, so the same four players in the same slots can lead-forfeit a
    second series. This also runs the INSERT itself: built in the statement,
    the room gave :sid two types and the INSERT could not be prepared.

    Each abandoned game shows 1-1 from a seat of EACH team, each post naming
    game 2: the record's proof of play since hotfix round 2 (one team's
    seats prove nothing, and after the first game of a sitting only a post
    naming its game counts). Before that round's picks this test proved play
    with two team-1 seats' legacy posts (beta round 4, step 0)."""
    async def go():
        async with _Lab() as lab:
            first = await lab.series()
            again = await lab.series(same_four_as=first)
            for ser in (first, again):
                await lab.post(ser, 0, 1, 1, game=2, room=ROOM)
                await lab.post(ser, 2, 1, 1, game=2, room=ROOM)
                await _two_reports(lab, ser, HIGH, HIGH)
            rooms = await lab.sql(
                "SELECT series_id, photon_room_id FROM team_matches"
                " WHERE dc_player_id IS NOT NULL ORDER BY created_at")
            return (await lab.settlement(first), await lab.settlement(again),
                    {r["series_id"]: r["photon_room_id"] for r in rooms}, first, again)

    s1, s2, rooms, first, again = _run(go())
    assert s1 == ("completed", 1, None, None, 1), s1
    assert s2 == ("completed", 1, None, None, 1), s2
    assert rooms == {first["sid"]: "dc_leadforfeit:%s" % first["sid"],
                     again["sid"]: "dc_leadforfeit:%s" % again["sid"]}, rooms


@needs_pg
@pytest.mark.parametrize("played", [True, False], ids=["game-crossed-two", "game-did-not"])
def test_every_survivor_reporting_settles_the_series_once(wired, played):
    """Round 2 finding 2: a seat that cannot read the teams now reports the
    disconnect itself, so all three survivors can report one leave. The
    server's F6 gate refuses the leaver's teammate (400, nothing written), the
    first report from the team that stayed settles the series, and the second
    finds it settled. One settlement, one forfeit row at most. A played game
    shows 1-1 from a seat of EACH team, each post naming game 2, the record's
    proof of play since hotfix round 2 (beta round 4, step 0: it was two
    team-1 seats' legacy posts before)."""
    async def go():
        async with _Lab() as lab:
            ser = await lab.series()
            if played:
                await lab.post(ser, 0, 1, 1, game=2, room=ROOM)
                await lab.post(ser, 2, 1, 1, game=2, room=ROOM)
            with pytest.raises(HTTPException) as refused:
                await lab.report_dc(ser, reporter_seat=3, dc_seat=2, **HIGH)
            after_refusal = await lab.settlement(ser)
            first = await lab.report_dc(ser, reporter_seat=1, dc_seat=2, **HIGH)
            second = await lab.report_dc(ser, reporter_seat=0, dc_seat=2, **LOW)
            return refused.value, after_refusal, first, second, await lab.settlement(ser)

    refused, after_refusal, first, second, settled = _run(go())
    assert refused.status_code == 400, refused
    assert after_refusal == ("active", None, None, None, 0), after_refusal
    assert first.get("ignored") is not True, first
    assert second.get("ignored") is True, second
    if played:
        assert settled == ("completed", 1, None, None, 1), settled
        assert len(wired) == 1, wired
    else:
        assert settled == ("dc_incomplete", None, 1, "dc_manual_pending", 0), settled
        assert wired == [], wired


# -- the game is identified, never timed (hotfix round 1) ---------------------
#
# The two scenarios the review raised against the 90-second window, each RED
# on the tree before this round (8af7fb3) and GREEN after, each with a
# mutation control and an inert twin on the same path.

async def _post_all(lab, ser, *pairs, seats=(0, 1, 2, 3), game=None, room=None, token=_AUTO):
    """Every seat in `seats` posts each pair in turn: the four clients' own
    re-sends of one game's running score, naming `game` and `room` when
    given, and carrying `token` (the lab's own for that game by default)."""
    for t1, t2 in pairs:
        for seat in seats:
            await lab.post(ser, seat, t1, t2, game=game, room=room, token=token)


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


_ALL_BITS = (1 << 36) - 1


def _token_layer_off(monkeypatch):
    """Every bit of a record reads as posted with the report's token: the
    token rule (main._team_game_token_seats, rounds 5 and 6) removed. The controls
    below that mutate one of the earlier rules switch it off as well. Each
    scenario they run is kept out twice since round 5: its stale posts name
    no game or another one, and they carry no token or another game's. With
    the token rule in place a mutant of the earlier rule alone changes
    nothing there, so a control that leaves it on could no longer watch its
    test fail. The token rule has its own controls (beta round 5, below)."""
    monkeypatch.setattr(main, "_team_game_token_seats",
                        lambda rec, token, ordinal: (_ALL_BITS, None))


def _wrap_the_evidence(monkeypatch, mutant=None):
    """Replace main._team_game_evidence by a wrapper that records each call's
    shape and returns `mutant(shape, cur, attested)` when given, else the real
    answer (the inert twin). With `mutant` the token rule is switched off too
    (_token_layer_off)."""
    real = main._team_game_evidence
    calls = []

    def wrapped(shape, cur_seats, attested_seats):
        calls.append(shape)
        if mutant is not None:
            return mutant(shape, cur_seats, attested_seats)
        return real(shape, cur_seats, attested_seats)

    monkeypatch.setattr(main, "_team_game_evidence", wrapped)
    if mutant is not None:
        _token_layer_off(monkeypatch)
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


def _sitting_rule_off(monkeypatch):
    """Round 7 (F29): no game token is read outside the series' original
    sitting (main._team_game_sitting_refusal). The relocked-sitting tests
    below also run with that rule switched off, so the record rule beneath
    it keeps tests that can watch it decide."""
    monkeypatch.setattr(main, "_team_game_sitting_refusal", lambda rec: None)


@needs_pg
@pytest.mark.parametrize("sitting_rule", [True, False], ids=["sitting-rule", "sitting-rule-off"])
@pytest.mark.parametrize("now, named, played", [(((1, 0), (1, 1)), True, True),
                                                (((2, 1),), False, False)],
                         ids=["own-crossing", "leftover"])
def test_the_game_after_a_relocked_sittings_first_reads_its_own_record(
        wired, monkeypatch, sitting_rule, now, named, played):
    """The game after a relocked sitting's first is named by the new
    sitting's room and its own number. Posts naming exactly that, a 1-1 from
    every seat, prove it; a pair the replayed game 1 went on to (2-1),
    naming no game, proves nothing. Since round 7 (F29) a relocked series
    reads no game token, so with the sitting rule both go to an admin; with
    the rule off the record rule decides."""
    if not sitting_rule:
        _sitting_rule_off(monkeypatch)

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
    completes = played and not sitting_rule
    assert settled[:2] == (("completed", 1) if completes else ("dc_incomplete", None)), settled


@needs_pg
@pytest.mark.parametrize("sitting_rule", [True, False], ids=["sitting-rule", "sitting-rule-off"])
@pytest.mark.parametrize("attested", [True, False], ids=["attested", "legacy"])
def test_an_attested_post_settles_the_first_game_of_a_relocked_sitting(
        wired, monkeypatch, sitting_rule, attested):
    """The first game of a relocked sitting takes no legacy proof: the dead
    sitting's posts can land in its record carrying anything. A post naming
    its game and sitting is filed only when it is exactly that game, so a 1-1
    named so by a seat of each team proves the game crossed. The same posts
    without the names settle nothing. Since round 7 (F29) a relocked series
    reads no game token, so with the sitting rule neither settles; with the
    rule off the record rule decides."""
    if not sitting_rule:
        _sitting_rule_off(monkeypatch)

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
    completes = attested and not sitting_rule
    assert settled[:2] == (("completed", 1) if completes else ("dc_incomplete", None)), settled


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


@needs_pg
def test_migration_352_runs_twice_over_a_351_table(wired):
    """352 over a 351 table that already holds a row: the row keeps its bits
    and reads attested_seats 0 (whatever it held counts as unnamed),
    attested_max_sum is gone, the new column is bounded, and a second run of
    352 changes nothing -- nor does 351 run again and then 352."""
    async def state(conn):
        cols = [r["column_name"] for r in await conn.fetch(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = current_schema() AND table_name = 'team_series_games'"
            " ORDER BY ordinal_position")]
        cons = [(r["conname"], r["def"]) for r in await conn.fetch(
            "SELECT conname, pg_get_constraintdef(oid) AS def FROM pg_constraint"
            " WHERE conrelid = 'team_series_games'::regclass ORDER BY conname")]
        rows = [tuple(r) for r in await conn.fetch(
            "SELECT series_id, game_ordinal, sitting_room, pair_seats, attested_seats"
            "  FROM team_series_games ORDER BY game_ordinal, sitting_room")]
        return cols, cons, rows

    async def go():
        async with _Lab(with_attested_seats=False) as lab:
            ser = await lab.series()
            conn = await asyncpg.connect(PLAIN_DSN)
            try:
                await conn.execute('SET search_path TO "%s"' % lab.schema)
                await conn.execute(
                    "INSERT INTO team_series_games (series_id, game_ordinal,"
                    " sitting_room, pair_seats, attested_max_sum)"
                    " VALUES ($1, 2, $2, $3, 2)", ser["sid"], ROOM, _bit(1, 1, 0))
                await conn.execute(_read(MIGRATION_352))
                first = await state(conn)
                await conn.execute(_read(MIGRATION_352))
                again = await state(conn)
                await conn.execute(_read(MIGRATION_351))
                await conn.execute(_read(MIGRATION_352))
                after_351 = await state(conn)
                refused = []
                for bad in ("attested_seats = 68719476736", "attested_seats = -1"):
                    try:
                        await conn.execute("UPDATE team_series_games SET %s" % bad)
                    except asyncpg.CheckViolationError:
                        refused.append(bad)
                return ser["sid"], first, again, after_351, refused
            finally:
                await conn.close()

    sid, first, again, after_351, refused = _run(go())
    cols, cons, rows = first
    assert "attested_max_sum" not in cols and "attested_seats" in cols, cols
    assert rows == [(sid, 2, ROOM, _bit(1, 1, 0), 0)], rows
    assert again == first and after_351 == first, (first, again, after_351)
    assert len(refused) == 2, refused


@needs_pg
@pytest.mark.parametrize("with_352", [False, True], ids=["before-352", "after-352"])
def test_before_migration_352_nothing_fails_and_nothing_auto_completes(wired, with_352):
    """The deploy-order claim in 352's header: this API against a database
    with 351 but not 352 records nothing and reads nothing, fails no request,
    and the DC report settles as dc_incomplete on a game a seat of each team
    posted 1-1 in, naming it. The twin, the same posts once 352 is applied,
    records the game and completes the series."""
    async def go():
        async with _Lab(with_attested_seats=with_352) as lab:
            ser = await lab.series()
            posted = [await lab.post(ser, seat, 1, 1, game=2, room=ROOM)
                      for seat in (0, 2)]
            await _two_reports(lab, ser, LOW, LOW)
            rows = (await lab.sql("SELECT count(*) AS n FROM team_series_games"))[0]["n"]
            return posted, rows, await lab.settlement(ser)

    posted, rows, settled = _run(go())
    assert [p["status"] for p in posted] == ["ok", "ok"], posted
    assert rows == (1 if with_352 else 0), rows
    assert settled[:2] == (("completed", 1) if with_352 else ("dc_incomplete", None)), settled


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


# -- beta round 3, finding 2: the reporter gate reads no client team ----------
#
# The client election now makes the two lowest ids among the survivors report
# whatever any advertised t_id says (DcReporterElection.ShouldReport), so the
# leaver's own teammate can be among the reporters. That is safe only because
# the F6 gate decides both teams from the series row: which slot the leaver's
# resolved player id and the reporter's resolved player id sit in. These pin
# that the gate still does, unchanged, and that it refuses the teammate
# wherever its report lands.

_SERIES_SLOTS = {"t1a_id", "t1b_id", "t2a_id", "t2b_id"}


def _team_read_issues(src):
    """Everything in team_series_report_dc's source that would let a team come
    from the request instead of the series row. Empty = the gate is intact."""
    fn = ast.parse(textwrap.dedent(src)).body[0]
    issues = []
    params = [a.arg for a in fn.args.args + fn.args.kwonlyargs]
    # "team" as a word of the name: reporter_steam_id is not a team.
    issues += ["team parameter %r" % p for p in params
               if re.search(r"(^|_)teams?(_|$)", p.lower())]
    for target, pid in (("dc_team", "dc_pid"), ("rep_team", "rep_pid")):
        assigns = [n for n in ast.walk(fn) if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == target for t in n.targets)]
        if len(assigns) != 1:
            issues.append("%s assigned %d times" % (target, len(assigns)))
            continue
        value = assigns[0].value
        names = {n.id for n in ast.walk(value) if isinstance(n, ast.Name)}
        if names != {pid, "s"}:
            issues.append("%s reads %s" % (target, sorted(names)))
        keys = {n.slice.value for n in ast.walk(value)
                if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant)}
        if keys != _SERIES_SLOTS:
            issues.append("%s reads series keys %s" % (target, sorted(keys)))
    for who in ("dc_player_steam_id", "reporter_steam_id"):
        n = ast.unparse(fn).count("Player.steam_id == %s" % who)
        if n != 1:
            issues.append("player id resolved from %s %d times" % (who, n))
    gates = [n for n in ast.walk(fn) if isinstance(n, ast.If)
             and ast.unparse(n.test) == "rep_team is None or rep_team == dc_team"]
    if len(gates) != 1 or not ast.unparse(gates[0].body[0]).startswith("raise HTTPException(400"):
        issues.append("F6 gate found %d times" % len(gates))
    return issues


def test_the_reporter_gate_reads_both_teams_from_the_series_row():
    """No team value from the request reaches the gate: dc_team and rep_team
    are each assigned once, from the locked series row's four slots and the
    player id resolved from the request's Steam id, and the endpoint takes no
    team parameter. Round 3 did not touch this; the test pins that it did not
    need to."""
    assert _team_read_issues(inspect.getsource(main.team_series_report_dc)) == []


@pytest.mark.parametrize("mutant", ["team-from-a-parameter", "gate-compares-a-constant",
                                    "reporter-team-from-the-leaver"])
def test_the_team_read_check_can_fail(mutant):
    """The check above, run on mutated copies of the real source: each mutant
    is flagged. The unmodified source is the test above."""
    src = textwrap.dedent(inspect.getsource(main.team_series_report_dc))
    swaps = {
        "team-from-a-parameter": [
            ("    photon_room_id: str = Query(None),\n",
             "    photon_room_id: str = Query(None),\n    dc_team_claimed: int = Query(0),\n"),
            ("    dc_team = 1 if dc_pid in", "    dc_team = dc_team_claimed or 1 if dc_pid in")],
        "gate-compares-a-constant": [
            ("if rep_team is None or rep_team == dc_team:", "if rep_team is None or rep_team == 3:")],
        "reporter-team-from-the-leaver": [
            ("rep_team = 1 if rep_pid in (s[\"t1a_id\"]", "rep_team = 1 if dc_pid in (s[\"t1a_id\"]")],
    }
    for old, new in swaps[mutant]:
        assert src.count(old) == 1, (mutant, old)
        src = src.replace(old, new)
    assert _team_read_issues(src), mutant


@needs_pg
@pytest.mark.parametrize("order", [(3, 0, 1), (0, 3, 1), (0, 1, 3)],
                         ids=["teammate-first", "teammate-second", "teammate-last"])
def test_the_leavers_teammate_is_refused_wherever_its_report_lands(wired, order):
    """The floor can put the leaver's teammate (seat 3 when seat 2 leaves)
    among the reporters, first, second or last. While the series is open its
    report is the F6 gate's 400; once the series is settled it is a no-op like
    any late report. Either way it writes nothing, it never settles the
    series, and the first report from the team that stayed settles it once.
    The game shows 1-1 from a seat of EACH team, each post naming game 2,
    the record's proof of play since hotfix round 2 (beta round 4, step 0:
    it was two team-1 seats' legacy posts before)."""
    async def go():
        async with _Lab() as lab:
            ser = await lab.series()
            await lab.post(ser, 0, 1, 1, game=2, room=ROOM)
            await lab.post(ser, 2, 1, 1, game=2, room=ROOM)
            seen = []
            for seat in order:
                before = await lab.settlement(ser)
                try:
                    res = await lab.report_dc(ser, reporter_seat=seat, dc_seat=2, **HIGH)
                    what = "ignored" if res.get("ignored") is True else "settled"
                except HTTPException as ex:
                    what = "refused %d: %s" % (ex.status_code, ex.detail)
                seen.append((seat, what, before, await lab.settlement(ser)))
            return seen, await lab.settlement(ser)

    seen, settled = _run(go())
    open_ = ("active", None, None, None, 0)
    done = ("completed", 1, None, None, 1)
    teammate = [s for s in seen if s[0] == 3]
    assert len(teammate) == 1, seen
    _, what, before, after = teammate[0]
    if order[0] == 3:
        assert what == "refused 400: reporter must be a member of the non-DC team", seen
        assert before == after == open_, seen
    else:
        assert what == "ignored", seen
        assert before == after == done, seen
    stayed = [s for s in seen if s[0] != 3]
    assert [s[1] for s in stayed] == ["settled", "ignored"], seen
    assert settled == done, settled
    assert len(wired) == 1, wired


# -- what the production client can prove, from both teams (hotfix round 2) ---
#
# Review round 1 of the hotfix. Finding 1: the production client dispatches a
# post at every change of its pair and at every 20-second refresh, never
# withdraws one in flight, and names no game in it (TAG v1.40.3,
# plugin/ApiClient.cs:2602-2666), so a previous game's posts, first-round
# pairs included, can be processed after that game's report, and are filed
# under the next game. Finding 2: one attested post proved a crossing by
# itself. Scenario (c): two seats of one team proved a crossing under the
# legacy rule alone. Each scenario is RED on f67b22a and GREEN after, with a
# mutation control on its own path and a twin.

async def _stale_first_round_posts(lab):
    """Scenario (a), in review finding 1's own shape: game 1 goes 1-0, 1-1,
    2-1, 2-2, but two seats of different teams (1 and 2) still have their 1-1
    in flight when game 1 is reported. Those two are processed now, filed
    under game 2, and game 2 itself has reached 1-0 when seat 2 leaves."""
    ser = await lab.series(t1_wins=0, t2_wins=0)
    await _post_all(lab, ser, (1, 0))
    await _post_all(lab, ser, (1, 1), seats=(0, 3))        # 1 and 2 still in flight
    await _post_all(lab, ser, (2, 1), (2, 2))
    await lab.win_game(ser, winner=1)
    await _post_all(lab, ser, (1, 1), seats=(1, 2))        # game 1's, landing late
    await _post_all(lab, ser, (1, 0))                      # game 2's own
    await _two_reports(lab, ser, LOW, LOW)
    return await lab.settlement(ser)


@needs_pg
def test_a_previous_games_first_round_posts_landing_late_settle_nothing(wired):
    """Scenario (a). Game 2's record holds a 1-1 from a seat of each team, and
    game 2 never passed 1-0. Round 1's rule read the two 1-1 bits as game 2's
    own first round (a 1-1 exists only in a first round, and it excused one
    seat) and settled a forfeit. They are game 1's, and the production client
    can deliver them this late. After the first game of a sitting only a post
    that names its game says which game its pair describes."""
    async def go():
        async with _Lab() as lab:
            return await _stale_first_round_posts(lab)

    settled = _run(go())
    assert settled == ("dc_incomplete", None, 1, "dc_manual_pending", 0), settled
    assert wired == [], wired


@needs_pg
@pytest.mark.parametrize("mutant", ["legacy-read-in-every-game", "pass-through"])
def test_the_stale_first_round_test_can_fail(wired, monkeypatch, mutant):
    """Control for scenario (a), on its own path: a rule that reads a legacy
    post as belonging to the game it was filed under, in every game (round
    1's attribution by arrival, the two-team rule kept), completes the same
    series, so the test above would fail; the inert twin wraps the real
    evidence rule, is reached once, and changes nothing."""
    calls = _wrap_the_evidence(monkeypatch, (lambda shape, cur, att: cur | att)
                               if mutant == "legacy-read-in-every-game" else None)

    async def go():
        async with _Lab() as lab:
            return await _stale_first_round_posts(lab)

    settled = _run(go())
    assert calls == ["second"], calls
    if mutant == "legacy-read-in-every-game":
        assert settled == ("completed", 1, None, None, 1), settled
    else:
        assert settled == ("dc_incomplete", None, 1, "dc_manual_pending", 0), settled


async def _one_team_attests(lab, other_team_seat=None):
    """Scenario (b): team 1 won game 1. In game 2 seat 0 (team 1) posts 2-0
    naming game 2 and its room, and nothing else is filed for game 2. With
    `other_team_seat`, a seat of team 2 posts the same pair, also naming the
    game: attested, because after the first game of a sitting only a post
    that names its game is read. Seat 2 leaves."""
    ser = await lab.series()
    await lab.post(ser, 0, 2, 0, game=2, room=ROOM)
    if other_team_seat is not None:
        await lab.post(ser, other_team_seat, 2, 0, game=2, room=ROOM)
    await _two_reports(lab, ser, LOW, LOW)
    return await lab.settlement(ser)


@needs_pg
@pytest.mark.parametrize("other_team_seat, played", [(None, False), (3, True)],
                         ids=["leader-alone", "each-team"])
def test_an_attested_crossing_needs_a_seat_of_each_team(wired, other_team_seat, played):
    """Scenario (b), review finding 2, and its twin. A post naming its game
    gives its pair an identity and nothing more: one seat of the team already
    up a game, attesting two points alone, proves nothing (dc_incomplete). The
    same post, with a seat of the other team attesting a pair of two points
    for the same game, proves the crossing (completed)."""
    async def go():
        async with _Lab() as lab:
            return await _one_team_attests(lab, other_team_seat)

    settled = _run(go())
    if played:
        assert settled == ("completed", 1, None, None, 1), settled
    else:
        assert settled == ("dc_incomplete", None, 1, "dc_manual_pending", 0), settled


@needs_pg
@pytest.mark.parametrize("mutant", ["one-seat-suffices", "pass-through"])
def test_the_attested_crossing_test_can_fail(wired, monkeypatch, mutant):
    """Control for scenario (b), on its own path: with the two-team rule put
    back to "any one seat's pair of two points proves it" (round 1's reading
    of an attested post), the leader-alone series completes, so the test
    above would fail, while the each-team twin completes either way; the
    inert twin wraps the real rule, is reached once per series, and changes
    nothing."""
    real = main._team_game_both_teams_reached_two
    calls = []

    def wrapped(seats):
        calls.append(seats)
        if mutant == "one-seat-suffices":
            return bool(seats & _TWO_OR_MORE)
        return real(seats)

    monkeypatch.setattr(main, "_team_game_both_teams_reached_two", wrapped)

    async def go():
        async with _Lab() as lab:
            return await _one_team_attests(lab), await _one_team_attests(lab, 3)

    alone, each = _run(go())
    assert len(calls) == 2, calls
    assert each == ("completed", 1, None, None, 1), each
    if mutant == "one-seat-suffices":
        assert alone == ("completed", 1, None, None, 1), alone
    else:
        assert alone == ("dc_incomplete", None, 1, "dc_manual_pending", 0), alone


async def _one_team_two_seats(lab, *, game_one, other_team_seat=None):
    """Scenario (c): two seats of team 1 (0 and 1) each post 1-1, and nothing
    comes from team 2 unless `other_team_seat` posts the same pair.
    game_one=True: game 1 of a fresh series (shape "first"), legacy posts --
    the one game legacy evidence was read in until beta round 5; a legacy
    post carries no physical-game token, so since then it proves nothing
    there either. game_one=False: game 2 of a series team 1 leads, every post
    naming game 2. Returns the record rule's verdict for the game in
    progress, then the settlement after seat 2 leaves."""
    ser = await lab.series(t1_wins=0 if game_one else 1, t2_wins=0)
    named = {} if game_one else {"game": 2, "room": ROOM}
    seats = (0, 1) + ((other_team_seat,) if other_team_seat is not None else ())
    for seat in seats:
        await lab.post(ser, seat, 1, 1, **named)
    verdict = await lab.crossed(ser)
    await _two_reports(lab, ser, LOW, LOW)
    return verdict, await lab.settlement(ser)


@needs_pg
@pytest.mark.parametrize("game_one", [True, False], ids=["game-1-legacy", "game-2-attested"])
@pytest.mark.parametrize("other_team_seat", [None, 2], ids=["one-team", "each-team"])
def test_two_seats_of_one_team_prove_no_crossing(wired, game_one, other_team_seat):
    """Scenario (c) and its twin. Two seats of the SAME team posting a pair of
    two points prove nothing: a seat count is not a team count, and one
    team's evidence alone is what ruling 2 refuses. A third post, from a seat
    of the other team, proves it. In game 1 the verdict is the record rule's
    own answer: the DC report never asks about game 1, because no team is a
    game up yet, so it settles dc_incomplete either way, on f67b22a and
    after. Game 1's legacy posts proved the crossing from a seat of each team
    until beta round 5; they carry no physical-game token (F25), so since
    then they prove nothing, whatever the teams. In game 2 the same rule
    settles the series."""
    async def go():
        async with _Lab() as lab:
            return await _one_team_two_seats(lab, game_one=game_one,
                                             other_team_seat=other_team_seat)

    verdict, settled = _run(go())
    played = other_team_seat is not None
    assert verdict is (played and not game_one), (verdict, settled)
    if played and not game_one:
        assert settled == ("completed", 1, None, None, 1), settled
    else:
        assert settled == ("dc_incomplete", None, 1, "dc_manual_pending", 0), settled


def _two_seats_suffice(seats):
    """Round 1's legacy reading as a seat count: any two seats with a pair of
    two points prove a crossing (one irregular seat excused), whatever their
    teams."""
    return sum(1 for k in range(4)
               if any(seats & _bit(a, b, k)
                      for a in range(3) for b in range(3) if a + b >= 2)) >= 2


@needs_pg
@pytest.mark.parametrize("mutant", ["two-seats-suffice", "two-seats-suffice-token-layer-off",
                                    "pass-through"])
def test_the_one_team_test_can_fail(wired, monkeypatch, mutant):
    """Control for scenario (c), on its own path: with the two-team rule put
    back to a seat count, the game-2 one-team record reads as crossed and
    game 2's settlement flips, so the test above would fail. Game 1's legacy
    record flips too once the round-5 token rule is also switched off
    (_token_layer_off); with the token rule in place its posts carry no
    token, so it stays unread under the seat count alone. The same mutant
    leaves scenario (b)'s lone attester unsettled (one seat is not two), so
    (b) and (c) pin different rules. The inert twin wraps the real rule and
    changes nothing."""
    real = main._team_game_both_teams_reached_two
    monkeypatch.setattr(main, "_team_game_both_teams_reached_two",
                        real if mutant == "pass-through" else _two_seats_suffice)
    if mutant == "two-seats-suffice-token-layer-off":
        _token_layer_off(monkeypatch)

    async def go():
        async with _Lab() as lab:
            return (await _one_team_two_seats(lab, game_one=True),
                    await _one_team_two_seats(lab, game_one=False),
                    await _one_team_attests(lab))

    game_one, game_two, lone = _run(go())
    flipped = mutant != "pass-through"
    assert game_one == (mutant == "two-seats-suffice-token-layer-off",
                        ("dc_incomplete", None, 1, "dc_manual_pending", 0)), game_one
    assert game_two == (flipped, ("completed", 1, None, None, 1) if flipped
                        else ("dc_incomplete", None, 1, "dc_manual_pending", 0)), game_two
    assert lone == ("dc_incomplete", None, 1, "dc_manual_pending", 0), lone


# -- round 4 of the beta lane: the client names its game ----------------------
#
# The v1.41.0 beta review, round 3, finding 1: the client sent no game number
# and no room, so after the first game of a sitting no post counted (every
# lead-forfeit settled as dc_incomplete), and a previous game's posts landing
# late were kept out only because nothing counted. Round 4's client
# (plugin/TeamGameNumber.cs, and PostTeamLivePoints in plugin/ApiClient.cs)
# names, on every 2v2 post it can, the game frozen at that game's start and
# the room it is played in. These tests pin what the server does with such
# posts. The server code is the hotfix's; this round changes only the
# endpoint's docstring, which now says a client sends the names.

def _wrap_the_filing(monkeypatch, mutant=False):
    """Replace main._record_team_game_points by a wrapper that records each
    call and, with `mutant`, files an attested post under the game in
    progress whatever game or sitting it names: the check that makes a
    post's identity its own, removed (and the token rule switched off,
    _token_layer_off). Without `mutant` it passes every call through
    unchanged (the inert twin)."""
    real = main._record_team_game_points
    calls = []

    async def wrapped(db, series_id, t1_points, t2_points, game, seat, attested=None,
                      token=None):
        calls.append(attested)
        if mutant and attested is not None:
            attested = game
        return await real(db, series_id, t1_points, t2_points, game, seat, attested,
                          token=token)

    monkeypatch.setattr(main, "_record_team_game_points", wrapped)
    if mutant:
        _token_layer_off(monkeypatch)
    return calls


def _masks(row):
    return None if row is None else (row["pair_seats"], row["attested_seats"])


async def _a_one_one_naming(lab, named):
    """Game 2 is in progress in ROOM (team 1 won game 1). A seat of each team
    (0 and 2) posts 1-1 naming `named` = (game, room); seat 2 leaves. Returns
    every record of games 1-3 in both rooms, and the settlement."""
    ser = await lab.series()
    for seat in (0, 2):
        await lab.post(ser, seat, 1, 1, game=named[0], room=named[1])
    rows = {}
    for ordinal in (1, 2, 3):
        for room in (ROOM, ROOM_NEXT):
            rows[(ordinal, room)] = _masks(await lab.game_row(ser, ordinal, room))
    await _two_reports(lab, ser, LOW, LOW)
    return rows, await lab.settlement(ser)


@needs_pg
@pytest.mark.parametrize("named, filed", [
    ((1, ROOM), False),
    ((2, ROOM), True),
    ((3, ROOM), False),
    ((2, ROOM_NEXT), False),
], ids=["the-game-before", "the-game-in-progress", "the-game-after", "another-sitting"])
def test_an_attested_post_is_filed_only_under_exactly_the_game_it_names(wired, named, filed):
    """Round 4, 2.4. Only a post naming the game in progress, in the stored
    sitting, is filed (in both masks) and proves the crossing. One naming the
    game before (a late post), the game after (a number ahead of the
    server's) or another sitting leaves no record anywhere and settles
    nothing."""
    async def go():
        async with _Lab() as lab:
            return await _a_one_one_naming(lab, named)

    rows, settled = _run(go())
    both = _bit(1, 1, 0) | _bit(1, 1, 2)
    expected = {key: None for key in rows}
    if filed:
        expected[(2, ROOM)] = (both, both)
    assert rows == expected, rows
    assert settled == (("completed", 1, None, None, 1) if filed
                       else ("dc_incomplete", None, 1, "dc_manual_pending", 0)), settled


@needs_pg
@pytest.mark.parametrize("mutant", ["files-whatever-it-names", "pass-through"])
def test_the_exact_game_test_can_fail(wired, monkeypatch, mutant):
    """Control for the test above, on its own path: with the named game and
    sitting ignored, a 1-1 naming the game AFTER the one in progress is filed
    under game 2 and completes the series, so the test above would fail. The
    inert twin wraps the real filing, is reached by both posts, and changes
    nothing."""
    calls = _wrap_the_filing(monkeypatch, mutant == "files-whatever-it-names")

    async def go():
        async with _Lab() as lab:
            return await _a_one_one_naming(lab, (3, ROOM))

    rows, settled = _run(go())
    assert calls == [(3, ROOM), (3, ROOM)], calls
    both = _bit(1, 1, 0) | _bit(1, 1, 2)
    if mutant == "files-whatever-it-names":
        assert rows[(2, ROOM)] == (both, both), rows
        assert settled == ("completed", 1, None, None, 1), settled
    else:
        assert all(v is None for v in rows.values()), rows
        assert settled == ("dc_incomplete", None, 1, "dc_manual_pending", 0), settled


async def _consecutive_sweeps(lab, scenario):
    """Review round 3's own failing shape (its test_team_series_report_dc.py:867,
    'same-sweep-before', and the ambiguity proof at :1259): game 1 goes 1-0,
    2-0, 2-1, 2-2 from every seat and team 1 wins it; game 2 opens the same
    way, team 1 sweeping round 1. Seat 2 leaves.
      game-2-swept         every post names its game; game 2 reaches 2-0.
      game-2-swept-legacy  the same posts without the names: round 3's pin.
      game-1-resends-late  game 2 reaches only 1-0, and game 1's 1-0 and 2-0,
                           naming game 1, land after game 1's report: the
                           records round 3 proved identical, bit for bit, to
                           game-2-swept when no post names its game."""
    named = scenario != "game-2-swept-legacy"
    one = {"game": 1, "room": ROOM} if named else {}
    two = {"game": 2, "room": ROOM} if named else {}
    ser = await lab.series(t1_wins=0, t2_wins=0)
    await _post_all(lab, ser, (1, 0), (2, 0), (2, 1), (2, 2), **one)
    await lab.win_game(ser, winner=1)
    if scenario == "game-1-resends-late":
        await _post_all(lab, ser, (1, 0), (2, 0), **one)
        await _post_all(lab, ser, (1, 0), **two)
    else:
        await _post_all(lab, ser, (1, 0), (2, 0), **two)
    await _two_reports(lab, ser, LOW, LOW)
    return await lab.settlement(ser)


@needs_pg
@pytest.mark.parametrize("scenario, played", [
    ("game-2-swept", True),
    ("game-2-swept-legacy", False),
    ("game-1-resends-late", False),
])
def test_consecutive_same_team_sweeps_are_told_apart_once_posts_name_their_game(
        wired, scenario, played):
    """Round 4, 2.4, in round 3's exact failing shape. With every post naming
    its game, a real game 2 that swept round 1 after game 1 had also passed
    2-0 settles as the forfeit it is, and a game 2 that reached only 1-0,
    with game 1's own 2-0 landing late, settles the conservative way. Without
    the names the first still settles as dc_incomplete, as round 3 pinned:
    the pair is what tells them apart."""
    async def go():
        async with _Lab() as lab:
            return await _consecutive_sweeps(lab, scenario)

    settled = _run(go())
    assert settled == (("completed", 1, None, None, 1) if played
                       else ("dc_incomplete", None, 1, "dc_manual_pending", 0)), settled


@needs_pg
@pytest.mark.parametrize("mutant", ["files-whatever-it-names", "evidence-disabled", "pass-through"])
def test_the_consecutive_sweeps_test_can_fail(wired, monkeypatch, mutant):
    """Control for the test above, on its own path. With the named game
    ignored, game 1's late 2-0 re-sends are filed under game 2 and complete
    the series; with no post counted as evidence, the real sweep settles as
    dc_incomplete. Either way the test above would fail. The inert twin wraps
    the real filing and changes nothing."""
    calls = _wrap_the_filing(monkeypatch, mutant == "files-whatever-it-names")
    if mutant == "evidence-disabled":
        _wrap_the_evidence(monkeypatch, lambda shape, cur, att: 0)

    async def go():
        async with _Lab() as lab:
            return (await _consecutive_sweeps(lab, "game-2-swept"),
                    await _consecutive_sweeps(lab, "game-1-resends-late"))

    swept, resent = _run(go())
    assert len(calls) == (16 + 8) + (16 + 8 + 4), len(calls)
    completed = ("completed", 1, None, None, 1)
    incomplete = ("dc_incomplete", None, 1, "dc_manual_pending", 0)
    assert swept == (incomplete if mutant == "evidence-disabled" else completed), swept
    assert resent == (completed if mutant == "files-whatever-it-names" else incomplete), resent


async def _prior_game_one_ones(lab, order, game_two_crossed):
    """Review round 3, finding 1's order case. Game 1 goes 1-0 from every
    seat, naming game 1, and two seats of different teams (1 and 2) post a
    1-1 naming game 1 that is still in flight while the game goes on to be
    reported (team 1 wins it). Game 2 reaches 1-0 from every seat, naming
    game 2, and with `game_two_crossed` also 1-1 from seats 0 and 3. Seat 2
    leaves. `order` is when the two game-1 posts are processed:
      before-its-report    while game 1 is in progress;
      after-its-report     after game 1's report, before the DC reports;
      after-the-dc-report  after the DC reports have settled the series.
    Returns the settlement, game 1's and game 2's records when it was
    decided, what the two posts got, and the records once they are
    processed."""
    ser = await lab.series(t1_wins=0, t2_wins=0)
    await _post_all(lab, ser, (1, 0), game=1, room=ROOM)
    got = []

    async def the_two():
        for seat in (1, 2):
            try:
                got.append((await lab.post(ser, seat, 1, 1, game=1, room=ROOM))["status"])
            except HTTPException as ex:
                got.append(ex.status_code)

    if order == "before-its-report":
        await the_two()
    await lab.win_game(ser, winner=1)
    if order == "after-its-report":
        await the_two()
    await _post_all(lab, ser, (1, 0), game=2, room=ROOM)
    if game_two_crossed:
        await _post_all(lab, ser, (1, 1), seats=(0, 3), game=2, room=ROOM)
    await _two_reports(lab, ser, LOW, LOW)
    settled = await lab.settlement(ser)
    decided = (_masks(await lab.game_row(ser, 1)), _masks(await lab.game_row(ser, 2)))
    if order == "after-the-dc-report":
        await the_two()
    final = (_masks(await lab.game_row(ser, 1)), _masks(await lab.game_row(ser, 2)))
    return settled, decided, got, final


_ORDERS = ["before-its-report", "after-its-report", "after-the-dc-report"]


@needs_pg
@pytest.mark.parametrize("game_two_crossed", [False, True], ids=["game-2-below-two", "game-2-crossed"])
def test_a_previous_games_named_posts_settle_the_same_whenever_they_land(wired, game_two_crossed):
    """Round 4, 2.5. Two game-1 posts, a 1-1 from a seat of each team, name
    game 1. Wherever they land -- before game 1's report, after it, or after
    the DC report that settles game 2 -- game 2 settles on game 2's own posts
    alone, and the same way: the identity a post is filed by is the one it
    carries, never the game in progress when it is processed. Landing before
    the report they are game 1's own and are filed there; after it they name
    a game that is no longer in progress and are filed nowhere (accepted:
    live points are still raised); after the DC report the series is no
    longer active and they are refused (409). Game 2's record never holds
    them."""
    async def go():
        results = {}
        for order in _ORDERS:
            async with _Lab() as lab:
                results[order] = await _prior_game_one_ones(lab, order, game_two_crossed)
        return results

    results = _run(go())
    expect = (("completed", 1, None, None, 1) if game_two_crossed
              else ("dc_incomplete", None, 1, "dc_manual_pending", 0))
    all_ten = sum(_bit(1, 0, k) for k in range(4))
    game_two = all_ten | ((_bit(1, 1, 0) | _bit(1, 1, 3)) if game_two_crossed else 0)
    late = _bit(1, 1, 1) | _bit(1, 1, 2)
    for order, (settled, decided, got, final) in results.items():
        assert settled == expect, (order, settled)
        game_one = all_ten | (late if order == "before-its-report" else 0)
        assert decided == ((game_one, game_one), (game_two, game_two)), (order, decided)
        assert final == decided, (order, final)
        assert got == ([409, 409] if order == "after-the-dc-report" else ["ok", "ok"]), (order, got)


@needs_pg
@pytest.mark.parametrize("mutant", ["files-whatever-it-names", "pass-through"])
def test_the_order_test_can_fail(wired, monkeypatch, mutant):
    """Control for the test above, on its own path: with the named game
    ignored, the two game-1 posts landing after game 1's report are filed
    under game 2, prove a crossing game 2 never reached, and complete the
    series, while the same posts landing before the report leave it
    dc_incomplete: the settlement depends on the order again, so the test
    above would fail. The inert twin wraps the real filing and changes
    nothing."""
    _wrap_the_filing(monkeypatch, mutant == "files-whatever-it-names")

    async def go():
        results = {}
        for order in ("before-its-report", "after-its-report"):
            async with _Lab() as lab:
                results[order] = (await _prior_game_one_ones(lab, order, False))[0]
        return results

    results = _run(go())
    incomplete = ("dc_incomplete", None, 1, "dc_manual_pending", 0)
    assert results["before-its-report"] == incomplete, results
    assert results["after-its-report"] == (("completed", 1, None, None, 1)
                                           if mutant == "files-whatever-it-names" else incomplete), results


_PLUGIN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                           "plugin")


def _cs_const(src, name):
    m = re.search(r'internal const string %s\s*=\s*"([^"]*)";' % name, src)
    assert m, name
    return m.group(1)


def test_the_clients_named_canonical_is_the_one_the_server_checks(monkeypatch):
    """Round 4, 2.3: the client signs 'team-live-points-game:...' exactly as
    update_team_live_points builds it. plugin/TeamGameNumber.cs pins one
    example, PinExpected for its PinSeries, PinReporter and PinRoom with t1 2,
    t2 1 and game 3 (its sentinel checks that AttestedCanonical builds it). A
    signature over it passes the server's own check for those inputs -- the
    call then stops at the database, None here -- and a signature over the
    same string with the two sides swapped does not. The two query
    parameters the client appends are the endpoint's own, in its order, and
    PostTeamLivePoints builds its URL and both signatures from these helpers."""
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    src = _read(os.path.join(_PLUGIN_DIR, "TeamGameNumber.cs"))
    series, reporter, room, expected = (_cs_const(src, n) for n in
                                        ("PinSeries", "PinReporter", "PinRoom", "PinExpected"))

    def call(message):
        sig = hmac.new(SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
        return _run(main.update_team_live_points(
            series_id=series, request=None, t1_points=2, t2_points=1,
            reporter_steam_id=reporter, sig=sig, game_number=3, photon_room_id=room, db=None))

    with pytest.raises(AttributeError):          # past the signature; db is None
        call(expected)
    swapped = expected.replace(":2:1:3:", ":1:2:3:")
    assert swapped != expected
    with pytest.raises(HTTPException) as ex:
        call(swapped)
    assert ex.value.status_code == 403, ex.value.detail

    pair = re.search(r"internal static string QueryPair\(.*?\{(.*?)\n        \}", src, re.S)
    assert pair, "QueryPair"
    names = re.findall(r'"&(\w+)="', pair.group(1))
    params = list(inspect.signature(main.update_team_live_points).parameters)
    assert names == ["game_number", "photon_room_id"], names
    assert [p for p in params if p in names] == names, params

    api = _read(os.path.join(_PLUGIN_DIR, "ApiClient.cs"))
    start = api.index("public static void PostTeamLivePoints(")
    body = api[start:api.index("\n        }\n", start)]
    for helper in ("TeamGameNumber.Sendable(", "TeamGameNumber.LegacyCanonical(",
                   "TeamGameNumber.QueryPair(", "TeamGameNumber.AttestedCanonical("):
        assert body.count(helper) == 1, helper
    assert "team-live-points" not in body, "a canonical built outside TeamGameNumber"


# -- F25: the physical game's token (beta review round 4, F25; round 5) ---------
#
# The reviewer's scenario: team 1 leads 1-0; physical game 2 crosses two points
# for both teams and team 2 wins it, but its report is still on its way (the
# reporter's client queued it); physical game 3 starts while the server still
# counts one recorded game, so game 3's seats name game 2 again; a team-2
# player leaves at 0-0. Before round 5, with the queued result landing after
# the DC reports, they read game 2's crossing as game 3's and completed the
# series for team 1. A post that names its game now also carries the physical
# game's token when its client holds one (the room's host publishes one per
# game), and so does the DC report; a lead-forfeit is read only from posts
# that carried the report's token (main._team_game_token_seats). Each test
# below has its control: a mutation of exactly the rule it relies on, and an
# inert twin.

# Since round 8 (F31) every one of these is counted from the lab series'
# physical game 1 (LAB_FIRST, which the lab writes), and since round 9 (M2)
# each one's nonce is derived from the whole of it and the token's own
# ordinal and epoch (_cwire).
T2 = _cwire(LAB_FIRST, 2)        # physical game 2's token, naming game 2
T3 = _cwire(LAB_FIRST, 3)        # physical game 3's token, naming game 3
TX = _cwire(LAB_FIRST, 1)        # physical game 1's token, naming game 1
# Physical game 3's token as a host whose own count names game 2 publishes
# it (one that joined after game 2 started and anchored its count on the
# recorded games): another physical game's token naming the same game, with
# physical game 3's epoch.
T3_AS_2 = _cwire(LAB_FIRST, 2, 3)
ZERO = dict(t1_total=0, t2_total=0)
INCOMPLETE = ("dc_incomplete", None, 1, "dc_manual_pending", 0)
COMPLETED = ("completed", 1, None, None, 1)
_GAME_TWO_BITS = sum(_bit(1, 0, k) | _bit(1, 1, k) for k in range(4))

_ORD_FILTER = "FILTER (WHERE g.game_ordinal = CAST(:ord AS integer))"
_CONFLICT_SET = "OR COALESCE(EXCLUDED.game_token <> team_series_games.game_token, FALSE)"
_ELSEWHERE = "AND t.game_token = CAST(:tok AS text)"


def _mutate_sql(monkeypatch, name, anchor, replacement, count=1):
    sql = getattr(main, name)
    assert sql.count(anchor) == count, (name, anchor, sql.count(anchor))
    monkeypatch.setattr(main, name, sql.replace(anchor, replacement))


def _apply_f25_mutant(monkeypatch, mutant):
    """The F25 controls, joined by '+':
      token-layer-off           every bit of a record reads as posted with
                                the report's token (_token_layer_off);
      whole-sitting-read        the game in progress is read from every
                                record of its sitting (the ordinal filter
                                taken out of the five aggregates), the read
                                the per-game record replaced;
      no-conflict-flag          a post carrying another token no longer
                                marks the record as holding two games;
      a-tokenless-post-poisons  a post carrying no token does;
      token-elsewhere-unread    the report's token is never found on
                                another record of the series;
      pass-through              nothing changes (the inert twin)."""
    for part in mutant.split("+"):
        if part == "token-layer-off":
            _token_layer_off(monkeypatch)
        elif part == "whole-sitting-read":
            _mutate_sql(monkeypatch, "_TEAM_GAME_CROSSED_SQL", _ORD_FILTER,
                        "FILTER (WHERE TRUE)", count=5)
        elif part == "no-conflict-flag":
            _mutate_sql(monkeypatch, "_TEAM_GAME_POINTS_UPSERT_SQL", _CONFLICT_SET, "OR FALSE")
        elif part == "a-tokenless-post-poisons":
            _mutate_sql(monkeypatch, "_TEAM_GAME_POINTS_UPSERT_SQL", _CONFLICT_SET,
                        _CONFLICT_SET.replace("FALSE)", "TRUE)"))
        elif part == "token-elsewhere-unread":
            _mutate_sql(monkeypatch, "_TEAM_GAME_CROSSED_SQL", _ELSEWHERE, "AND FALSE")
        else:
            assert part == "pass-through", part


async def _f25(lab, order, game_three=None):
    """The reviewer's scenario. Team 1 leads 1-0. Physical game 2: every seat
    posts 1-0 and then 1-1, naming game 2 and carrying game 2's token; team 2
    wins it and its report is still on its way. Physical game 3 starts while
    the server counts one recorded game, so its seats name game 2 as well and
    carry game 3's token: with `game_three` (a pair) every seat posts it
    before the disconnect, without it none has posted. Seat 2 (team 2)
    leaves, and seats 0 and 1 report it naming game 3's token. `order` is
    when game 2's queued result lands: "result-first", before the DC reports,
    or "result-later", after them (the settlement is decided by then). Returns
    the settlement and game 2's record."""
    ser = await lab.series(t1_wins=1, t2_wins=0)
    await _post_all(lab, ser, (1, 0), (1, 1), game=2, room=ROOM, token=T2)
    if game_three is not None:
        await _post_all(lab, ser, game_three, game=2, room=ROOM, token=T3)
    if order == "result-first":
        await lab.win_game(ser, winner=2)
    snap = dict(t1_total=game_three[0], t2_total=game_three[1]) if game_three else ZERO
    await _two_reports(lab, ser, snap, snap, token=T3)
    return await lab.settlement(ser), await lab.game_row(ser, 2)


_F25_ORDERS = ["result-first", "result-later"]


@needs_pg
@pytest.mark.parametrize("game_three", [None, (0, 0), (1, 0)],
                         ids=["game-3-no-post", "game-3-posted-0-0", "game-3-posted-1-0"])
@pytest.mark.parametrize("order", _F25_ORDERS)
def test_the_reviewers_scenario_settles_nothing_from_game_two(wired, order, game_three):
    """F25, both ways: game 2's queued result landing before the DC reports and
    after them. Neither settles and no series is completed. With the result
    first the reports read game 3's own record, which holds nothing: game 3's
    posts named game 2 and were filed in its record. With it later they read
    game 2's record, whose token is not the reports' (since round 6 the
    reports' token is refused first: it names game 3, and game 2 is being
    settled). Game 2's record keeps game 2's token and only game 2's posts
    in its token bits; game 3's posts, filed there too, mark it as holding
    two physical games (since round 6 because their token names game 3, not
    the game they name)."""
    async def go():
        async with _Lab() as lab:
            return await _f25(lab, order, game_three)

    settled, record = _run(go())
    assert settled == INCOMPLETE, settled
    assert wired == [], wired
    assert (record["game_token"], record["token_seats"], record["token_conflict"]) == (
        _nonce(T2), _GAME_TWO_BITS, game_three is not None), record


@needs_pg
@pytest.mark.parametrize("mutant", ["token-layer-off", "whole-sitting-read",
                                    "whole-sitting-read+token-layer-off", "pass-through"])
def test_the_reviewers_scenario_test_can_fail(wired, monkeypatch, mutant):
    """Controls for the test above (#391), game 3 without a post. With the
    token rule off, the result-later order reads game 2's crossing as game
    3's and completes the series for team 1: the defect as reported. The
    result-first order is decided by the game's number before any token is
    read (the reports read game 3's empty record), so the token rule off
    leaves it incomplete; it completes only when the record is also read
    without its game (every record of the sitting). That read alone, with the
    token rule on, completes neither order: the token rule holds both by
    itself. The inert twin changes nothing."""
    _apply_f25_mutant(monkeypatch, mutant)

    async def go():
        results = {}
        for order in _F25_ORDERS:
            async with _Lab() as lab:
                results[order] = (await _f25(lab, order))[0]
        return results

    later = COMPLETED if "token-layer-off" in mutant else INCOMPLETE
    first = COMPLETED if mutant == "whole-sitting-read+token-layer-off" else INCOMPLETE
    assert _run(go()) == {"result-first": first, "result-later": later}


# ---- Round 6, finding F27: the token's game --------------------------------
# The token names the ordinal of the physical game it was published for,
# 'nonce:ordinal:epoch', all three signed. A seat takes it only for the game
# its own count and its posts both name (plugin/TeamGameNumber.cs); a post
# whose token names another game than the one it names marks the record as
# holding another physical game; a DC report's token is read only when it
# names the game being settled (main._team_game_token_seats).

_F27 = ["ahead-reporter-tokenless", "ahead-reporter-adopts", "level"]


async def _f27(lab, case):
    """The F27 reviewer's scenario. Team 1 leads 1-0 and game 2's result is
    still on its way. The host (seat 0, team 1) and an opposite-team
    contributor (seat 3) are a game behind: in game 2 they post 1-0 and 1-1
    naming game 2 and carrying T2, the token the host published at its game-2
    start, which names game 2. Seat 1 (team 1) is already in game 3, where
    seat 2 (team 2) leaves at 0-0, and seat 1 reports the leave. `case`:
      ahead-reporter-tokenless  what seat 1 sends as a round-6 client: its own
                                count names game 3 and T2 names game 2, so it
                                took no token (TeamGameNumber.cs, F27-REVIEWER)
                                and its report names none;
      ahead-reporter-adopts     the defect as reported: seat 1 took T2 as its
                                game 3's token (the round-5 adoption) and its
                                report names it;
      level                     the positive control: seat 1 is in game 2 as
                                well, posts the same pairs carrying T2 and
                                reports the leave at 1-1 naming it.
    Returns the settlement and game 2's record."""
    ser = await lab.series(t1_wins=1, t2_wins=0)
    seats = (0, 1, 3) if case == "level" else (0, 3)
    await _post_all(lab, ser, (1, 0), (1, 1), seats=seats, game=2, room=ROOM, token=T2)
    snap = HIGH if case == "level" else ZERO
    await lab.report_dc(ser, reporter_seat=1, dc_seat=2,
                        token=None if case == "ahead-reporter-tokenless" else T2, **snap)
    return await lab.settlement(ser), await lab.game_row(ser, 2)


@needs_pg
def test_the_f27_reviewers_scenario_is_ineligible(wired):
    """F27 (round 6): the reporter already in game 3 is tokenless, so its 0-0
    report names no token and the series goes to an admin (dc_incomplete):
    nothing is completed and no result, rating or gold moves. Game 2's record
    keeps T2's nonce, the two lagging seats' token bits and no conflict: the
    record is sound, and it is the reporter's own game that is not game 2."""
    async def go():
        async with _Lab() as lab:
            return await _f27(lab, "ahead-reporter-tokenless")

    settled, record = _run(go())
    assert settled == INCOMPLETE, settled
    assert wired == [], wired
    bits = sum(_bit(1, 0, k) | _bit(1, 1, k) for k in (0, 3))
    assert (record["game_token"], record["token_seats"], record["token_conflict"]) == (
        _nonce(T2), bits, False), record


@needs_pg
@pytest.mark.parametrize("mutant", ["ahead-reporter-adopts", "token-layer-off", "level",
                                    "pass-through"])
def test_the_f27_reviewers_scenario_test_can_fail(wired, monkeypatch, mutant):
    """Controls (#391). With the ahead reporter taking T2 for its game 3 (the
    defect as reported) the server reads game 2's crossing and completes the
    series for team 1: the server alone cannot tell that report from a
    genuine game-2 leave, which is why the ahead seat must be tokenless (the
    harness's F27 mutants restore that adoption and fail). With the token
    rule off the tokenless report completes it too. With every seat in game
    2 (level) the same posts and a report naming T2 complete it: the rule
    withholds only the divergent case. The inert twin changes nothing."""
    if mutant == "token-layer-off":
        _token_layer_off(monkeypatch)
    case = mutant if mutant in _F27 else "ahead-reporter-tokenless"

    async def go():
        async with _Lab() as lab:
            return (await _f27(lab, case))[0]

    assert _run(go()) == (INCOMPLETE if mutant == "pass-through" else COMPLETED)
    assert len(wired) == (0 if mutant == "pass-through" else 1), wired


# F29 (round 7): a seat's physical game is never taken from the recorded
# games. The reviewer's scenario: the series stands 1-1 and physical game 3's
# result (team 1's win) is still on its way, so the server counts two
# recorded games and settles game 3 while physical game 4 is played. Round
# 6's seats that joined, rejoined or changed rooms before game 4 anchored
# their count on the recorded games and named game 4 "game 3"; round 7's
# name no game until a host's publish grounds them (plugin/TeamGameNumber.cs),
# and the server reads a token only in the series' original sitting
# (main._team_game_sitting_refusal) and only when it names the game being
# settled.
T4 = _cwire(LAB_FIRST, 4)          # physical game 4's token, naming game 4
# Physical game 4's token as a round-6 host re-anchored on the two recorded
# games published it: it names game 3.
T4_AS_3 = _cwire(LAB_FIRST, 3, 4)
INCOMPLETE2 = ("dc_incomplete", None, 2, "dc_manual_pending", 0)
COMPLETED2 = ("completed", 2, None, None, 1)
_F29 = ["tokenless", "host-ordinal", "count-anchored", "in-step"]


async def _f29(lab, case, sitting="original"):
    """The F29 reviewer's scenario, as the server sees it. The series stands
    1-1 (in-step: 2-1, game 3's result recorded before game 4). In physical
    game 4 every seat posts 1-0 and then 1-1 naming the game the server has
    in progress (the posts' own number is the recorded games plus one) and
    carrying the token `case` gives; seat 0 (team 1) leaves and seat 2 (team
    2) reports it at 1-1 naming the same token. With `sitting` "relocked"
    the series moved to ROOM_NEXT before game 4 (the room change), and the
    posts and the report name that room; "moved" is the same room change
    without a relock stamp (the stamp is savepointed, and skipped before
    migration 235: #235), after seat 0 had filed a 1-0 of game 3 in ROOM, so
    the series has a game on record in another room. `case`:
      tokenless       round 7's seats: each one that joined, rejoined or
                      changed rooms before game 4 holds no physical game, so
                      none carries a token and the report names none;
      host-ordinal    a host that kept its physical game published T4, which
                      names game 4, and every seat carries it;
      count-anchored  round 6's seats (the defect as reported): anchored on
                      the recorded games, they carry T4_AS_3;
      in-step         the control: game 3 recorded in step, T4 carried.
    Returns the settlement and the record the posts were filed under."""
    ser = await lab.series(t1_wins=2 if case == "in-step" else 1, t2_wins=1)
    room = ROOM
    game = 4 if case == "in-step" else 3
    if sitting == "relocked":
        await lab.relock(ser, ROOM_NEXT)
        room = ROOM_NEXT
    elif sitting == "moved":
        await lab.post(ser, 0, 1, 0, game=game, room=ROOM, token=None)
        await lab.sql("UPDATE team_series SET photon_room_id = :r WHERE id = :sid",
                      {"sid": ser["sid"], "r": ROOM_NEXT})
        room = ROOM_NEXT
    token = {"tokenless": None, "host-ordinal": T4, "count-anchored": T4_AS_3,
             "in-step": T4}[case]
    await _post_all(lab, ser, (1, 0), (1, 1), game=game, room=room, token=token)
    await lab.report_dc(ser, reporter_seat=2, dc_seat=0, room=room, token=token, **HIGH)
    return await lab.settlement(ser), await lab.game_row(ser, game, room)


@needs_pg
@pytest.mark.parametrize("case, sitting", [("tokenless", "original"), ("host-ordinal", "original"),
                                           ("tokenless", "relocked"), ("count-anchored", "relocked"),
                                           ("count-anchored", "moved")],
                         ids=["rejoin-tokenless", "rejoin-host-ordinal",
                              "room-change-tokenless", "room-change-count-anchored",
                              "room-moved-count-anchored"])
def test_the_f29_reviewers_scenario_is_ineligible(wired, case, sitting):
    """F29 (round 7): with game 3's result still on its way the series goes
    to an admin (dc_incomplete) whatever game 4's seats carry: nothing is
    completed and no result, rating or gold moves. Round 7's seats are
    tokenless after a join, a rejoin or a room change. A host that kept its
    physical game names game 4, which is not the game being settled (game
    3): the token's number and the server's have different origins, and its
    posts, filed under game 3, mark that record as holding another game.
    After a room change even round 6's count-anchored token is not read: the
    series is outside its original sitting, by its relock stamp or, when the
    stamp is missing, by its game on record in another room."""
    async def go():
        async with _Lab() as lab:
            return await _f29(lab, case, sitting)

    settled, record = _run(go())
    assert settled == INCOMPLETE2, settled
    assert wired == [], wired
    want = {"tokenless": (None, 0, False), "host-ordinal": (None, 0, True),
            "count-anchored": (_nonce(T4_AS_3), _GAME_TWO_BITS, False)}[case]
    assert (record["game_token"], record["token_seats"], record["token_conflict"]) == want, record


@needs_pg
@pytest.mark.parametrize("mutant", ["count-anchored", "count-anchored-sitting-rule-off",
                                    "count-anchored-moved-sitting-rule-off",
                                    "token-layer-off", "in-step", "pass-through"])
def test_the_f29_reviewers_scenario_test_can_fail(wired, monkeypatch, mutant):
    """Controls (#391). With round 6's count-anchored seats (the count
    anchor restored: the defect as reported) game 4 crosses under a token
    naming game 3 and the server completes the series for team 2 before game
    3's result lands: the server alone cannot tell that from a genuine game-3
    leave, which is why the seats must be tokenless (the harness's F29
    mutants restore the anchor and fail). After a room change, with or
    without its relock stamp, the same seats complete it once the sitting
    rule is off. With the token rule off the
    tokenless report completes it too. With game 3 recorded in step, T4 and
    the same posts complete it: the rules withhold only the game with a
    result on its way. The inert twin changes nothing."""
    sitting = {"count-anchored-sitting-rule-off": "relocked",
               "count-anchored-moved-sitting-rule-off": "moved"}.get(mutant, "original")
    if sitting != "original":
        _sitting_rule_off(monkeypatch)
    if mutant == "token-layer-off":
        _token_layer_off(monkeypatch)
    case = mutant if mutant in _F29 else ("count-anchored" if sitting != "original" else "tokenless")

    async def go():
        async with _Lab() as lab:
            return (await _f29(lab, case, sitting))[0]

    assert _run(go()) == (INCOMPLETE2 if mutant == "pass-through" else COMPLETED2)
    assert len(wired) == (0 if mutant == "pass-through" else 1), wired


async def _report_naming(lab, game):
    """Team 1 leads 1-0 and game 2 crosses: every seat posts 1-0 and 1-1
    naming game 2 and carrying a token with epoch 2 that names game 2, its
    nonce the one derived for game `game` (T2 itself for game 2). Seat 2
    leaves; seats 0 and 1 report it naming the token that nonce was derived
    for, which names game `game`, signed as it is sent. Since round 9 (M2) a
    token's nonce is derived for its own ordinal, so a report token carrying
    T2's nonce but naming another game is refused before its ordinal is
    compared (main._team_game_first_game_refusal); this one passes that
    check, and the comparison of its ordinal with the game being settled
    alone refuses it."""
    ser = await lab.series(t1_wins=1, t2_wins=0)
    posted = _wire(_chain(LAB_FIRST, game, 2), 2, 2)
    await _post_all(lab, ser, (1, 0), (1, 1), game=2, room=ROOM, token=posted)
    await _two_reports(lab, ser, LOW, LOW, token=_cwire(LAB_FIRST, game, 2))
    return await lab.settlement(ser)


@needs_pg
@pytest.mark.parametrize("game", [3, 1, 2], ids=["names-game-3", "names-game-1", "names-game-2"])
def test_a_report_token_naming_another_game_reads_nothing(wired, game):
    """F27, the server's own check (round 6): a settlement for game 2 reads
    only a token that names game 2. A report whose signed token carries the
    record's own nonce but names game 3 or game 1 reads no bit of game 2's
    record, and the series goes to an admin; the twin naming game 2 (T2
    itself) completes it."""
    async def go():
        async with _Lab() as lab:
            return await _report_naming(lab, game)

    assert _run(go()) == (COMPLETED if game == 2 else INCOMPLETE)


@needs_pg
@pytest.mark.parametrize("mutant", ["ordinal-unread", "pass-through"])
def test_the_report_token_game_test_can_fail(wired, monkeypatch, mutant):
    """Control: with the report's ordinal never compared to the game being
    settled, the report naming game 3 reads game 2's crossing and completes
    the series; the inert twin changes nothing."""
    if mutant == "ordinal-unread":
        real = main._team_game_token_seats
        monkeypatch.setattr(main, "_team_game_token_seats",
                            lambda rec, token, ordinal: real(
                                rec, token, ordinal if token is None else token[1]))

    async def go():
        async with _Lab() as lab:
            return await _report_naming(lab, 3)

    assert _run(go()) == (COMPLETED if mutant == "ordinal-unread" else INCOMPLETE)


_FOREIGN_AT = ["foreign-first", "foreign-last"]


async def _foreign_post(lab, at):
    """Team 1 leads 1-0 and game 2 crosses: seats 0 and 3 post 1-0 and 1-1
    naming game 2 and carrying T2. Seat 1 posts 1-1 naming game 2 and
    carrying T3, signed, which names game 3: before the others
    ("foreign-first", its post opens the record) or after them. Seat 2
    leaves; seat 0 reports it naming T2. Returns the settlement and game 2's
    record."""
    ser = await lab.series(t1_wins=1, t2_wins=0)
    if at == "foreign-first":
        await lab.post(ser, 1, 1, 1, game=2, room=ROOM, token=T3)
    await _post_all(lab, ser, (1, 0), (1, 1), seats=(0, 3), game=2, room=ROOM, token=T2)
    if at == "foreign-last":
        await lab.post(ser, 1, 1, 1, game=2, room=ROOM, token=T3)
    await lab.report_dc(ser, reporter_seat=0, dc_seat=2, token=T2, **LOW)
    return await lab.settlement(ser), await lab.game_row(ser, 2)


@needs_pg
@pytest.mark.parametrize("at", _FOREIGN_AT)
def test_a_post_whose_token_names_another_game_marks_the_record(wired, at):
    """F27 (round 6): a post whose verified token names another game than the
    one it names is another physical game's post, not another token of this
    game. It is filed (as attested) with no token and no token bit, and it
    marks the record as holding another physical game, whether it opens the
    record or comes last; the report naming the record's own token then
    reads nothing."""
    async def go():
        async with _Lab() as lab:
            return await _foreign_post(lab, at)

    settled, record = _run(go())
    assert settled == INCOMPLETE, settled
    assert wired == [], wired
    bits = sum(_bit(1, 0, k) | _bit(1, 1, k) for k in (0, 3))
    assert (record["game_token"], record["token_seats"], record["token_conflict"]) == (
        _nonce(T2), bits, True), record
    assert record["attested_seats"] & _bit(1, 1, 1), record


_FOREIGN_SET = "OR EXCLUDED.token_conflict"
_FOREIGN_VALUE = "CAST(:foreign AS boolean)"


@needs_pg
@pytest.mark.parametrize("mutant", ["foreign-unmarked", "pass-through"])
def test_the_foreign_post_test_can_fail(wired, monkeypatch, mutant):
    """Control: with a post whose token names another game no longer marking
    the record (on its insert and on its update), game 2's crossing is read
    and the series completes, in both orders; the inert twin changes
    nothing."""
    if mutant == "foreign-unmarked":
        _mutate_sql(monkeypatch, "_TEAM_GAME_POINTS_UPSERT_SQL", _FOREIGN_SET, "OR FALSE")
        _mutate_sql(monkeypatch, "_TEAM_GAME_POINTS_UPSERT_SQL", _FOREIGN_VALUE,
                    "(" + _FOREIGN_VALUE + " AND FALSE)")

    async def go():
        results = {}
        for at in _FOREIGN_AT:
            async with _Lab() as lab:
                results[at] = (await _foreign_post(lab, at))[0]
        return results

    want = COMPLETED if mutant == "foreign-unmarked" else INCOMPLETE
    assert _run(go()) == {at: want for at in _FOREIGN_AT}


_PAIRLESS = ["result-first", "result-later", "same-game"]


async def _f25_pairless(lab, situation):
    """Old clients in game 2: every seat posts 1-0 and 1-1 without the pair (so
    without a token), each filed under game 2 as the game in progress when it
    is processed. `situation`:
      result-first, result-later  the reviewer's scenario: game 3 has no post
                                  when seat 2 leaves, and seats 0 and 1
                                  report it naming game 3's token, game 2's
                                  queued result landing before the reports or
                                  after them;
      same-game                   seat 2 leaves in game 2 itself and seats 0
                                  and 1, old clients too, report it with no
                                  token: a crossing that did happen."""
    ser = await lab.series(t1_wins=1, t2_wins=0)
    await _post_all(lab, ser, (1, 0), (1, 1))
    if situation == "result-first":
        await lab.win_game(ser, winner=2)
    if situation == "same-game":
        await _two_reports(lab, ser, HIGH, HIGH, token=None)
    else:
        await _two_reports(lab, ser, ZERO, ZERO, token=T3)
    return await lab.settlement(ser)


@needs_pg
@pytest.mark.parametrize("situation", _PAIRLESS)
def test_pairless_posts_withhold_the_settlement_and_move_nothing(wired, situation):
    """F25's pairless case (O1, unchanged): posts without the pair name no game
    and carry no token, so no crossing is read from them: not the reviewer's
    scenario in either order, and not a crossing that did happen. Each goes to
    an admin (dc_incomplete) and no series is completed, so no result, rating
    or gold moves."""
    async def go():
        async with _Lab() as lab:
            return await _f25_pairless(lab, situation)

    assert _run(go()) == INCOMPLETE
    assert wired == [], wired


@needs_pg
@pytest.mark.parametrize("mutant", ["legacy-counted-token-layer-off",
                                    "whole-sitting-read+legacy-counted-token-layer-off",
                                    "pass-through"])
def test_the_pairless_test_can_fail(wired, monkeypatch, mutant):
    """Control: with posts without the pair counted in every game and the
    token rule off, game 2's pairless crossing completes the series in the
    result-later order and in the same game; the result-first order reads
    game 3's empty record, and completes only when the record is also read
    without its game. The inert twin changes nothing."""
    counted = "legacy-counted" in mutant
    _wrap_the_evidence(monkeypatch, (lambda shape, cur, att: cur) if counted else None)
    if "whole-sitting-read" in mutant:
        _apply_f25_mutant(monkeypatch, "whole-sitting-read")

    async def go():
        results = {}
        for situation in _PAIRLESS:
            async with _Lab() as lab:
                results[situation] = await _f25_pairless(lab, situation)
        return results

    whole = "whole-sitting-read" in mutant
    assert _run(go()) == {"result-first": COMPLETED if whole else INCOMPLETE,
                          "result-later": COMPLETED if counted else INCOMPLETE,
                          "same-game": COMPLETED if counted else INCOMPLETE}


_MIXED = ["all-new", "old-team-2", "host-never-published", "old-reporters"]


async def _mixed(lab, case):
    """Team 1 leads 1-0 and game 2 crosses: every seat posts 1-0 and 1-1
    naming game 2. Then seat 2 leaves and seats 0 and 1 report it. `case`:
      all-new               every post and both reports carry game 2's token;
      old-team-2            team 2's seats run an old client: their posts
                            carry no token (team 1's do);
      host-never-published  no seat holds a token (an old host, or a publish
                            that never reached the room): no post and no
                            report carries one;
      old-reporters         every post carries it, the reports carry none."""
    ser = await lab.series(t1_wins=1, t2_wins=0)
    tok = _tok(ser["sid"], 2, ROOM)
    for pair in ((1, 0), (1, 1)):
        for seat in range(4):
            bare = case == "host-never-published" or (case == "old-team-2" and seat >= 2)
            await lab.post(ser, seat, *pair, game=2, room=ROOM, token=None if bare else tok)
    await _two_reports(lab, ser, LOW, LOW,
                       token=None if case in ("host-never-published", "old-reporters") else tok)
    return await lab.settlement(ser)


@needs_pg
@pytest.mark.parametrize("case", _MIXED)
def test_a_side_without_the_token_leaves_the_game_ineligible(wired, case):
    """F25's mixed-client case. The same crossing settles only when every side
    the rule reads carries the game's token: a two-point post of each team
    and the report. A side without it is never presumed to match the side
    that has it: the series goes to an admin (dc_incomplete)."""
    async def go():
        async with _Lab() as lab:
            return await _mixed(lab, case)

    assert _run(go()) == (COMPLETED if case == "all-new" else INCOMPLETE)
    assert len(wired) == (1 if case == "all-new" else 0), wired


@needs_pg
@pytest.mark.parametrize("mutant", ["token-layer-off", "pass-through"])
def test_the_mixed_client_test_can_fail(wired, monkeypatch, mutant):
    """Control: with the token rule off, each mixed case completes the series
    on a crossing one side never carried the game's token for; the inert twin
    changes nothing."""
    _apply_f25_mutant(monkeypatch, mutant)

    async def go():
        results = {}
        for case in _MIXED[1:]:
            async with _Lab() as lab:
                results[case] = await _mixed(lab, case)
        return results

    want = COMPLETED if mutant == "token-layer-off" else INCOMPLETE
    assert _run(go()) == {case: want for case in _MIXED[1:]}


_REPORT_AT = ["in-the-window", "after-the-token"]


async def _propagation(lab, report_at):
    """F25's propagation window. Team 1 leads 1-0. In game 2 team 1's seats
    post 1-0 and 1-1 carrying game 2's token; team 2's seats post the same
    before their clients hold any token for the game (none carried). The
    record rule is asked for game 2's token at that moment. With
    "after-the-token" team 2's seats then post 1-1 again, now carrying it (a
    client posts again when the token arrives), and the rule is asked again.
    Seat 2 leaves; seats 0 and 1 report it naming game 2's token: inside the
    window, or after the token arrived."""
    ser = await lab.series(t1_wins=1, t2_wins=0)
    tok = _tok(ser["sid"], 2, ROOM)
    await _post_all(lab, ser, (1, 0), (1, 1), seats=(0, 1), game=2, room=ROOM, token=tok)
    await _post_all(lab, ser, (1, 0), (1, 1), seats=(2, 3), game=2, room=ROOM, token=None)
    window = await lab.crossed(ser, token=tok)
    if report_at == "after-the-token":
        await _post_all(lab, ser, (1, 1), seats=(2, 3), game=2, room=ROOM, token=tok)
    now = await lab.crossed(ser, token=tok)
    await _two_reports(lab, ser, LOW, LOW, token=tok)
    return (window, now, await lab.settlement(ser)), await lab.game_row(ser, 2), tok


@needs_pg
@pytest.mark.parametrize("report_at", _REPORT_AT)
def test_a_crossing_before_the_token_arrives_counts_once_it_does(wired, report_at):
    """The window is ineligible while it lasts: a DC report inside it settles
    as dc_incomplete. A post without the token poisons nothing: once team 2's
    seats post the pair again carrying it, the same game is eligible and the
    report completes the series. The record's token bits hold the posts that
    carried the token and nothing else."""
    async def go():
        async with _Lab() as lab:
            return await _propagation(lab, report_at)

    verdicts, record, tok = _run(go())
    team_one = _bit(1, 0, 0) | _bit(1, 1, 0) | _bit(1, 0, 1) | _bit(1, 1, 1)
    if report_at == "in-the-window":
        assert verdicts == (False, False, INCOMPLETE), verdicts
        carried = team_one
    else:
        assert verdicts == (False, True, COMPLETED), verdicts
        carried = team_one | _bit(1, 1, 2) | _bit(1, 1, 3)
    assert (record["game_token"], record["token_seats"], record["token_conflict"]) == (
        _nonce(tok), carried, False), record


@needs_pg
@pytest.mark.parametrize("mutant", ["token-layer-off", "a-tokenless-post-poisons", "pass-through"])
def test_the_propagation_test_can_fail(wired, monkeypatch, mutant):
    """Controls: with the token rule off the window is already eligible and a
    report inside it completes the series; with a post without the token
    marking the record as two games, the game stays ineligible once the
    token arrives and that report goes to an admin. The inert twin changes
    nothing."""
    _apply_f25_mutant(monkeypatch, mutant)

    async def go():
        results = {}
        for report_at in _REPORT_AT:
            async with _Lab() as lab:
                results[report_at] = (await _propagation(lab, report_at))[0]
        return results

    want = {"token-layer-off": {"in-the-window": (True, True, COMPLETED),
                                "after-the-token": (True, True, COMPLETED)},
            "a-tokenless-post-poisons": {"in-the-window": (False, False, INCOMPLETE),
                                         "after-the-token": (False, False, INCOMPLETE)},
            "pass-through": {"in-the-window": (False, False, INCOMPLETE),
                             "after-the-token": (False, True, COMPLETED)}}[mutant]
    assert _run(go()) == want


async def _lagging_reporter(lab):
    """Game 2 crosses under its token (every seat 1-0 and 1-1 naming game 2,
    carrying T2) and its report is still on its way. Game 3's seats post 1-0,
    naming game 2 again and carrying game 3's token, which names game 2 as
    well (T3_AS_2; a token naming game 3 is the next test's case): filed in
    game 2's record. Seat 2 leaves; seats 0 and 1 report it naming game 2's
    token (a client that still holds it)."""
    ser = await lab.series(t1_wins=1, t2_wins=0)
    await _post_all(lab, ser, (1, 0), (1, 1), game=2, room=ROOM, token=T2)
    await _post_all(lab, ser, (1, 0), game=2, room=ROOM, token=T3_AS_2)
    await _two_reports(lab, ser, ZERO, ZERO, token=T2)
    return await lab.settlement(ser), await lab.game_row(ser, 2)


@needs_pg
def test_a_record_holding_two_physical_games_proves_nothing(wired):
    """The record keeps the first token filed under it; a post carrying another
    sets none of its token bits and marks the record as holding two physical
    games, and then no report reads a crossing from it, not even one naming
    the record's own token."""
    async def go():
        async with _Lab() as lab:
            return await _lagging_reporter(lab)

    settled, record = _run(go())
    assert settled == INCOMPLETE, settled
    assert wired == [], wired
    assert (record["game_token"], record["token_seats"], record["token_conflict"]) == (
        _nonce(T2), _GAME_TWO_BITS, True), record


@needs_pg
@pytest.mark.parametrize("mutant", ["no-conflict-flag", "pass-through"])
def test_the_two_games_test_can_fail(wired, monkeypatch, mutant):
    """Control: with a post carrying another token no longer marking the
    record, the report naming game 2's token reads game 2's crossing and
    completes the series; the inert twin changes nothing."""
    _apply_f25_mutant(monkeypatch, mutant)

    async def go():
        async with _Lab() as lab:
            return await _lagging_reporter(lab)

    settled, record = _run(go())
    assert (settled, record["token_conflict"]) == (
        (COMPLETED, False) if mutant == "no-conflict-flag" else (INCOMPLETE, True)), (
        settled, record)


_REUSE = ["nonce-reused", "token-kept", "token-fresh"]


async def _reused(lab, reuse):
    """Team 1 wins game 1 after every seat posted 1-0 and 1-1 naming it and
    carrying TX. Game 2 crosses the same way, carrying, by `reuse`: a nonce
    game 1's record holds too ("nonce-reused"); TX itself, a token kept past
    its own physical game ("token-kept"; since round 6 it names game 1); or
    game 2's own ("token-fresh"). Seat 2 leaves and seats 0 and 1 report it
    naming the token game 2's posts carried. Since round 9 (M2) TX's nonce
    signed as game 2's is not the nonce derived for game 2 and is refused
    before any record is read, so for "nonce-reused" game 1's posts carry
    game 2's own nonce, named as game 1, and game 2's carry T2: the same
    nonce on two records, which only the read of the report's token on
    another record refuses."""
    ser = await lab.series(t1_wins=0, t2_wins=0)
    first = _wire(_nonce(T2), 1) if reuse == "nonce-reused" else TX
    await _post_all(lab, ser, (1, 0), (1, 1), game=1, room=ROOM, token=first)
    await lab.win_game(ser, winner=1)
    tok = {"nonce-reused": T2, "token-kept": TX, "token-fresh": T2}[reuse]
    await _post_all(lab, ser, (1, 0), (1, 1), game=2, room=ROOM, token=tok)
    await _two_reports(lab, ser, LOW, LOW, token=tok)
    return await lab.settlement(ser)


@needs_pg
@pytest.mark.parametrize("reuse", _REUSE)
def test_a_token_on_another_game_of_the_series_proves_nothing(wired, reuse):
    """A token whose nonce is also on another game's record names no one
    physical game: the report naming it settles nothing. A token kept past
    its own game names that game (round 6), so game 2's posts carrying it
    mark game 2's record and the report naming it reads nothing. The twin
    with game 2's own token completes the series."""
    async def go():
        async with _Lab() as lab:
            return await _reused(lab, reuse)

    assert _run(go()) == (COMPLETED if reuse == "token-fresh" else INCOMPLETE)


@needs_pg
@pytest.mark.parametrize("mutant", ["token-elsewhere-unread", "pass-through"])
def test_the_reused_token_test_can_fail(wired, monkeypatch, mutant):
    """Control: with the report's token never found on another record, the
    reused token completes the series; the inert twin changes nothing."""
    _apply_f25_mutant(monkeypatch, mutant)

    async def go():
        async with _Lab() as lab:
            return await _reused(lab, "nonce-reused")

    assert _run(go()) == (COMPLETED if mutant == "token-elsewhere-unread" else INCOMPLETE)


@needs_pg
def test_migration_354_runs_twice_over_a_352_table(wired):
    """354 over a 352 table that already holds a row: the row keeps its bits
    and reads no token, token_seats 0 and no conflict; a row written as the
    API from before 354 writes one (naming only the older columns) gets the
    same defaults; the three new columns are bounded; and a second run of 354
    changes nothing -- nor does 352 run again and then 354."""
    async def state(conn):
        cols = [r["column_name"] for r in await conn.fetch(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = current_schema() AND table_name = 'team_series_games'"
            " ORDER BY ordinal_position")]
        cons = [(r["conname"], r["def"]) for r in await conn.fetch(
            "SELECT conname, pg_get_constraintdef(oid) AS def FROM pg_constraint"
            " WHERE conrelid = 'team_series_games'::regclass ORDER BY conname")]
        rows = [tuple(r) for r in await conn.fetch(
            "SELECT game_ordinal, sitting_room, pair_seats, attested_seats, game_token,"
            "       token_seats, token_conflict"
            "  FROM team_series_games ORDER BY game_ordinal, sitting_room")]
        return cols, cons, rows

    async def go():
        async with _Lab(with_game_token=False) as lab:
            ser = await lab.series()
            conn = await asyncpg.connect(PLAIN_DSN)
            try:
                await conn.execute('SET search_path TO "%s"' % lab.schema)
                insert_old = ("INSERT INTO team_series_games (series_id, game_ordinal,"
                              " sitting_room, pair_seats, attested_seats)"
                              " VALUES ($1, $2, $3, $4, $4)")
                await conn.execute(insert_old, ser["sid"], 2, ROOM, _bit(1, 1, 0))
                await conn.execute(_read(MIGRATION_354))
                await conn.execute(insert_old, ser["sid"], 3, ROOM, _bit(1, 1, 2))
                first = await state(conn)
                await conn.execute(_read(MIGRATION_354))
                again = await state(conn)
                await conn.execute(_read(MIGRATION_352))
                await conn.execute(_read(MIGRATION_354))
                after_352 = await state(conn)
                refused = []
                for bad in ("game_token = 'A2A2A2A2A2A2A2A2'", "game_token = 'a2'",
                            "token_seats = 68719476736", "token_seats = -1",
                            "token_seats = NULL", "token_conflict = NULL"):
                    try:
                        await conn.execute("UPDATE team_series_games SET %s"
                                           " WHERE game_ordinal = 2" % bad)
                    except (asyncpg.CheckViolationError, asyncpg.NotNullViolationError):
                        refused.append(bad)
                await conn.execute("UPDATE team_series_games SET game_token = $1"
                                   " WHERE game_ordinal = 2", _nonce(T2))
                kept = await conn.fetchval("SELECT game_token FROM team_series_games"
                                           " WHERE game_ordinal = 2")
                return first, again, after_352, refused, kept
            finally:
                await conn.close()

    first, again, after_352, refused, kept = _run(go())
    cols, _cons, rows = first
    assert cols[-3:] == ["game_token", "token_seats", "token_conflict"], cols
    assert rows == [(2, ROOM, _bit(1, 1, 0), _bit(1, 1, 0), None, 0, False),
                    (3, ROOM, _bit(1, 1, 2), _bit(1, 1, 2), None, 0, False)], rows
    assert again == first and after_352 == first, (first, again, after_352)
    assert len(refused) == 6, refused
    assert kept == _nonce(T2), kept


@needs_pg
@pytest.mark.parametrize("with_354", [False, True], ids=["before-354", "after-354"])
def test_before_migration_354_nothing_fails_and_nothing_auto_completes(wired, with_354):
    """The deploy-order claim in 354's header: this API against a database
    with 352 but not 354 records nothing (its upsert names the new columns
    and the savepoint takes the refusal) and reads nothing, fails no request,
    and the DC report settles as dc_incomplete on a game a seat of each team
    posted 1-1 in, naming it and carrying its token. The twin, the same posts
    once 354 is applied, records the game and completes the series."""
    async def go():
        async with _Lab(with_game_token=with_354) as lab:
            ser = await lab.series()
            posted = [await lab.post(ser, seat, 1, 1, game=2, room=ROOM) for seat in (0, 2)]
            await _two_reports(lab, ser, LOW, LOW)
            rows = (await lab.sql("SELECT count(*) AS n FROM team_series_games"))[0]["n"]
            return posted, rows, await lab.settlement(ser)

    posted, rows, settled = _run(go())
    assert [p["status"] for p in posted] == ["ok", "ok"], posted
    assert rows == (1 if with_354 else 0), rows
    assert settled == (COMPLETED if with_354 else INCOMPLETE), settled


_DROPS = ["bad-signature", "not-hex", "no-signature", "no-pair",
          "ordinal-altered", "epoch-altered", "ordinal-stripped"]


async def _dropped_token_post(lab, case):
    """One post from seat 0, 1-1, carrying a token the route cannot verify:
    signed with a wrong MAC, not 16 lowercase hex digits (signed), sent
    without token_sig, or on a post that names no game (signed over the
    token canonical with no game); round 6, finding F27: its ordinal or its
    epoch altered after it was signed, or its nonce alone (signed as it is
    sent, the round-5 shape)."""
    ser = await lab.series()
    kw = dict(game=2, room=ROOM, token=T2)
    signed_t2 = _token_sig(str(ser["sid"]), ser["steams"][0], 1, 1, 2, ROOM, T2)
    if case == "bad-signature":
        kw["token_sig"] = "0" * 64
    elif case == "not-hex":
        kw["token"] = T2.upper()
    elif case == "no-signature":
        kw["token_sig"] = None
    elif case == "no-pair":
        kw = dict(token=T2)
    elif case == "ordinal-altered":
        kw.update(token=_wire(_nonce(T2), 3, 2), token_sig=signed_t2)
    elif case == "epoch-altered":
        kw.update(token=_wire(_nonce(T2), 2, 9), token_sig=signed_t2)
    elif case == "ordinal-stripped":
        kw["token"] = _nonce(T2)
    answer = await lab.post(ser, 0, 1, 1, **kw)
    return answer, await lab.game_row(ser, 2)


@needs_pg
@pytest.mark.parametrize("case", _DROPS)
def test_a_post_token_the_route_cannot_verify_is_dropped_never_refused(wired, case):
    """A token that does not verify costs the post nothing but the token: the
    post is answered and filed (as attested when it names its game), and the
    record holds no token and no token bits."""
    async def go():
        async with _Lab() as lab:
            return await _dropped_token_post(lab, case)

    answer, record = _run(go())
    assert answer["status"] == "ok", answer
    assert (record["pair_seats"], record["attested_seats"], record["game_token"],
            record["token_seats"], record["token_conflict"]) == (
        _bit(1, 1, 0), 0 if case == "no-pair" else _bit(1, 1, 0), None, 0, False), record


@needs_pg
@pytest.mark.parametrize("mutant", ["token-unverified", "pass-through"])
def test_the_dropped_post_token_test_can_fail(wired, monkeypatch, mutant):
    """Control: with the route taking any token it is sent, the badly signed
    token is kept on the record, and so is the one whose epoch was altered
    after it was signed; the inert twin changes nothing."""
    if mutant == "token-unverified":
        monkeypatch.setattr(main, "_team_game_post_token",
                            lambda sid, rep, t1, t2, game, room, token, sig:
                            main._team_game_wire_token(token))

    async def go():
        records = {}
        for case in ("bad-signature", "epoch-altered"):
            async with _Lab() as lab:
                records[case] = (await _dropped_token_post(lab, case))[1]["game_token"]
        return records

    kept = _nonce(T2) if mutant == "token-unverified" else None
    assert _run(go()) == {"bad-signature": kept, "epoch-altered": kept}


async def _f28(lab, report):
    """The F28 reviewer's scenario. Team 1 leads 1-0 and game 2 crosses under
    T2 (every seat posts 1-0 and 1-1 naming game 2, carrying it) while its
    result is still on its way. Seat 0 (team 1) misses game 2's end and game
    3's start; seat 2 leaves game 3 at 0-0, and seat 0's OnPlayerLeftRoom
    builds its report before its next poll. `report` is the token that report
    names: None, a round-6 or a round-7 client's (round 6: its read-time
    check finds no reading that still shows game 2; round 7: the game's own
    game over already ended the token on seat 0: TeamGameNumber.cs,
    F28-REVIEWER), or T2, the round-5 client's."""
    ser = await lab.series(t1_wins=1, t2_wins=0)
    await _post_all(lab, ser, (1, 0), (1, 1), game=2, room=ROOM, token=T2)
    await lab.report_dc(ser, reporter_seat=0, dc_seat=2, token=report, **ZERO)
    return await lab.settlement(ser)


@needs_pg
def test_the_f28_reviewers_report_carries_no_token_and_settles_nothing(wired):
    """F28, the server's half (brief 3.3: no new server behavior): the fixed
    client's report in the reviewer's scenario names no token, and the
    server gives it what it gives every tokenless report: dc_incomplete,
    nothing completed, no result, rating or gold moved."""
    async def go():
        async with _Lab() as lab:
            return await _f28(lab, None)

    assert _run(go()) == INCOMPLETE
    assert wired == [], wired


@needs_pg
@pytest.mark.parametrize("mutant", ["round-5-client", "token-layer-off", "pass-through"])
def test_the_f28_report_test_can_fail(wired, monkeypatch, mutant):
    """Controls: the round-5 client's report, naming the token it kept past
    game 2, completes game 3's 0-0 leave from game 2's crossing (the defect
    as reported: the server cannot tell it from a genuine game-2 leave, so
    the fix is the client's); with the token rule off, the tokenless report
    completes it too; the inert twin changes nothing."""
    if mutant == "token-layer-off":
        _token_layer_off(monkeypatch)

    async def go():
        async with _Lab() as lab:
            return await _f28(lab, T2 if mutant == "round-5-client" else None)

    assert _run(go()) == (INCOMPLETE if mutant == "pass-through" else COMPLETED)
    assert len(wired) == (0 if mutant == "pass-through" else 1), wired


async def _f30(lab, report):
    """The F30 reviewer's scenario, round 6's residual shape. Team 1 leads
    1-0 and game 2 crosses under T2 (every seat posts 1-0 and 1-1 naming
    game 2, carrying it) while its result is still on its way. Seat 0 (team
    1) sees nothing of game 2's end or game 3's start (no game over, no game
    start, no poll tick), and the host publishes nothing, so the room still
    holds T2. Seat 2 leaves in game 3 after team 1 won its first round, and
    seat 0's report reads a score that follows its last reading inside one
    game; its snapshot is its watcher's last poll (game 2's one point each),
    which the route stores and logs but never settles on. `report` is the
    token that report names: None, the round-7 client's (the game's own game
    over and game 3's start ended the token on seat 0: TeamGameNumber.cs,
    F30-REVIEWER), or T2, the round-6 client's (its time bridge carried T2
    across the boundary)."""
    ser = await lab.series(t1_wins=1, t2_wins=0)
    await _post_all(lab, ser, (1, 0), (1, 1), game=2, room=ROOM, token=T2)
    await lab.report_dc(ser, reporter_seat=0, dc_seat=2, token=report, t1_total=1, t2_total=1)
    return await lab.settlement(ser)


@needs_pg
def test_the_f30_residual_report_carries_no_token_and_settles_nothing(wired):
    """F30, the server's half (brief 3.2: no new server behavior): in round
    6's residual shape the fixed client's report names no token, and the
    server gives it what it gives every tokenless report: dc_incomplete,
    nothing completed, no result, rating or gold moved."""
    async def go():
        async with _Lab() as lab:
            return await _f30(lab, None)

    assert _run(go()) == INCOMPLETE
    assert wired == [], wired


@needs_pg
@pytest.mark.parametrize("mutant", ["round-6-client", "token-layer-off", "pass-through"])
def test_the_f30_residual_test_can_fail(wired, monkeypatch, mutant):
    """Controls: the round-6 client's report, naming the token its time
    bridge carried past game 2's end, completes game 3's leave from game 2's
    crossing (the server cannot tell it from a genuine game-2 leave, so the
    fix is the client's); with the token rule off, the tokenless report
    completes it too; the inert twin changes nothing."""
    if mutant == "token-layer-off":
        _token_layer_off(monkeypatch)

    async def go():
        async with _Lab() as lab:
            return await _f30(lab, T2 if mutant == "round-6-client" else None)

    assert _run(go()) == (INCOMPLETE if mutant == "pass-through" else COMPLETED)
    assert len(wired) == (0 if mutant == "pass-through" else 1), wired


async def _dropped_token_report(lab, case):
    """Team 1 leads 1-0 and game 2 crosses, every post carrying game 2's
    token. Seat 2 leaves and seats 0 and 1 report it naming game 2's token,
    signed ("signed"), signed with a wrong MAC, or without token_sig; round
    6, finding F27: with its ordinal or its epoch altered after it was
    signed, or its nonce alone (signed as it is sent, the round-5 shape)."""
    ser = await lab.series(t1_wins=1, t2_wins=0)
    await _post_all(lab, ser, (1, 0), (1, 1), game=2, room=ROOM)
    tok = _tok(ser["sid"], 2, ROOM)
    for seat in (0, 1):
        kw = {}
        signed = _dc_token_sig(ser["steams"][seat], str(ser["sid"]), ser["steams"][2], tok)
        if case == "bad-signature":
            kw["token_sig"] = "0" * 64
        elif case == "no-signature":
            kw["token_sig"] = None
        elif case == "ordinal-altered":
            kw = dict(token=_wire(_nonce(tok), 3, 2), token_sig=signed)
        elif case == "epoch-altered":
            kw = dict(token=_wire(_nonce(tok), 2, 9), token_sig=signed)
        elif case == "ordinal-stripped":
            kw = dict(token=_nonce(tok))
        await lab.report_dc(ser, reporter_seat=seat, dc_seat=2, **LOW, **kw)
    return await lab.settlement(ser)


@needs_pg
@pytest.mark.parametrize("case", ["signed", "bad-signature", "no-signature",
                                  "ordinal-altered", "epoch-altered", "ordinal-stripped"])
def test_a_dc_token_the_route_cannot_verify_names_no_game(wired, case):
    """A DC report whose token does not verify names no token, and its game is
    not eligible: the series goes to an admin. The same report signed right
    completes it. Since round 6 the token's ordinal and epoch are signed
    with it, and a token without them is not a token."""
    async def go():
        async with _Lab() as lab:
            return await _dropped_token_report(lab, case)

    assert _run(go()) == (COMPLETED if case == "signed" else INCOMPLETE)


@needs_pg
@pytest.mark.parametrize("mutant", ["token-unverified", "chain-unread", "token-unverified-chain-unread",
                                    "pass-through"])
def test_the_dropped_dc_token_test_can_fail(wired, monkeypatch, mutant):
    """Control: with the DC route taking any token it is sent, the badly
    signed report completes the series. Since round 9 (M2) the report whose
    epoch was altered after it was signed is refused twice over: by its
    signature, and by the chain, since a later game's nonce is derived from
    the origin over its ordinal AND its epoch, so the altered token no
    longer carries the nonce derived for the epoch it names. Each refusal
    alone keeps it out: with the route taking any token it stays incomplete
    (the chain refuses it); with the chain unread (every token's nonce taken
    as the one derived for its ordinal and epoch, the rest of the read
    kept) it stays incomplete (the signature refuses it); with both off it
    completes. The inert twin changes nothing."""
    unverified = mutant in ("token-unverified", "token-unverified-chain-unread")
    unchained = mutant in ("chain-unread", "token-unverified-chain-unread")
    if unverified:
        monkeypatch.setattr(main, "_team_dc_game_token",
                            lambda sid, rep, dc, token, sig: main._team_game_wire_token(token))
    if unchained:
        real_read = main._team_game_first_game_refusal

        def chain_unread(rec, token):
            issued = rec["first_game_nonce"]
            if main._team_game_token_valid(issued):
                token = ((main._team_game_chain_nonce(issued, token[1], token[2]),)
                         + tuple(token[1:]))
            return real_read(rec, token)

        monkeypatch.setattr(main, "_team_game_first_game_refusal", chain_unread)

    async def go():
        results = {}
        for case in ("bad-signature", "epoch-altered"):
            async with _Lab() as lab:
                results[case] = await _dropped_token_report(lab, case)
        return results

    assert _run(go()) == {"bad-signature": COMPLETED if unverified else INCOMPLETE,
                          "epoch-altered": COMPLETED if unverified and unchained else INCOMPLETE}


def test_the_clients_token_canonicals_are_the_ones_the_server_checks(monkeypatch):
    """Round 5, F25: the client signs 'team-live-points-token:...' and
    'team-dc-token:...' exactly as the server's token checks build them.
    plugin/TeamGameNumber.cs pins PinTokenExpected (PinSeries, PinReporter,
    t1 2, t2 1, game 3, PinRoom, PinToken) and PinDcTokenExpected
    (PinReporter, PinSeries, PinDcPlayer, PinToken); its sentinel checks that
    TokenCanonical and DcTokenCanonical build them. A signature over each is
    accepted by the server's own check for those inputs, and one over the
    same string with two fields swapped, or over the token in upper case, is
    not. The two query parameters the client appends are both endpoints'
    own, in their order; PostTeamLivePoints and ReportTeamSeriesDc build them
    from these helpers only. PostTeamLivePoints' one caller passes the token;
    ReportTeamSeriesDc reads its own, once, for a prompt report only (v1.41.0
    merge pass 1, follow-up 5: see the pin at the end of this test).
    Round 6, finding F27: PinToken is 'nonce:ordinal:epoch', both canonicals
    end with the whole token, and the token with its ordinal or its epoch
    altered after signing, or sent as its nonce alone, is not accepted. The
    report's token is read as the report is built (F28): TeamTokenForReport
    passes this seat's reading of the score to TokenFor, and (round 7, F30)
    whether the game's lifecycle hooks are attached, where round 6 passed a
    clock."""
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    src = _read(os.path.join(_PLUGIN_DIR, "TeamGameNumber.cs"))
    series, reporter, room, token, dc_player, post_pin, dc_pin = (_cs_const(src, n) for n in (
        "PinSeries", "PinReporter", "PinRoom", "PinToken", "PinDcPlayer", "PinTokenExpected",
        "PinDcTokenExpected"))

    def mac(message):
        return hmac.new(SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()

    parsed = main._team_game_wire_token(token)
    assert parsed == ("0123456789abcdef", 3, 7), parsed
    assert main._team_game_post_token(series, reporter, 2, 1, 3, room, token,
                                      mac(post_pin)) == parsed
    swapped = post_pin.replace(":2:1:3:", ":1:2:3:")
    assert swapped != post_pin
    assert main._team_game_post_token(series, reporter, 2, 1, 3, room, token, mac(swapped)) is None
    upper = token.upper()
    assert upper != token
    assert main._team_game_post_token(series, reporter, 2, 1, 3, room, upper,
                                      mac(post_pin.replace(token, upper))) is None
    assert main._team_dc_game_token(series, reporter, dc_player, token, mac(dc_pin)) == parsed
    other = "team-dc-token:%s:%s:%s:%s" % (dc_player, series, reporter, token)
    assert other != dc_pin
    assert main._team_dc_game_token(series, reporter, dc_player, token, mac(other)) is None
    assert main._team_dc_game_token(series, reporter, dc_player, upper,
                                    mac(dc_pin.replace(token, upper))) is None
    assert post_pin.endswith(":" + token) and dc_pin.endswith(":" + token), (post_pin, dc_pin)
    for altered in (token.replace(":3:7", ":4:7"), token.replace(":3:7", ":3:8")):
        assert altered != token
        assert main._team_game_post_token(series, reporter, 2, 1, 3, room, altered,
                                          mac(post_pin)) is None, altered
        assert main._team_dc_game_token(series, reporter, dc_player, altered,
                                        mac(dc_pin)) is None, altered
    nonce = token.split(":", 1)[0]
    assert main._team_game_post_token(series, reporter, 2, 1, 3, room, nonce,
                                      mac(post_pin.replace(token, nonce))) is None
    assert main._team_dc_game_token(series, reporter, dc_player, nonce,
                                    mac(dc_pin.replace(token, nonce))) is None

    query = re.search(r"internal static string QueryToken\(.*?\{(.*?)\n        \}", src, re.S)
    assert query, "QueryToken"
    names = re.findall(r'"&(\w+)="', query.group(1))
    assert names == ["game_token", "token_sig"], names
    for endpoint in (main.update_team_live_points, main.team_series_report_dc):
        params = list(inspect.signature(endpoint).parameters)
        assert [p for p in params if p in names] == names, (endpoint.__name__, params)

    api = _read(os.path.join(_PLUGIN_DIR, "ApiClient.cs"))
    for head, canonical, literal in (
            ("public static void PostTeamLivePoints(", "TeamGameNumber.TokenCanonical(",
             "team-live-points-token"),
            ("public static void ReportTeamSeriesDc(", "TeamGameNumber.DcTokenCanonical(",
             "team-dc-token")):
        start = api.index(head)
        body = api[start:api.index("\n        }\n", start)]
        for helper in ("TeamGameNumber.TokenValid(", "TeamGameNumber.QueryToken(", canonical):
            assert body.count(helper) == 1, (head, helper)
        assert literal not in body, (head, "a canonical built outside TeamGameNumber")
    watcher = _read(os.path.join(_PLUGIN_DIR, "GameStateWatcher.cs"))
    start = watcher.index("private static void MaybeSendLivePoints(")
    body = watcher[start:watcher.index("\n        }\n", start)]
    assert body.count("TeamGameNumber.Live.TokenFor(") == 1, "MaybeSendLivePoints"
    assert "teamGame, teamRoom, teamToken);" in body, "MaybeSendLivePoints"
    assert "ReadLiveScore(), TeamGameLifecycle.HooksLive);" in body, "MaybeSendLivePoints"
    start = watcher.index("internal static string TeamTokenForReport(")
    body = watcher[start:watcher.index("\n        }\n", start)]
    assert body.count("TeamGameNumber.Live.TokenFor(") == 1, "TeamTokenForReport"
    assert "ReadLiveScore()," in body and "TeamGameLifecycle.HooksLive, out why);" in body, "TeamTokenForReport"
    # WHERE THE REPORT'S TOKEN IS READ (v1.41.0 merge pass 1, follow-up 5).
    # This lane read it in Plugin.cs and passed it to the one ReportTeamSeriesDc
    # call. The 886bed8 client half made ReportTeamSeriesDc the one place a DC
    # report is composed (a prompt report and the watch's fallback both go
    # through it) and pins that Plugin.cs call WITHOUT a token argument, so the
    # merged tree reads the token inside ReportTeamSeriesDc, for a prompt report
    # only. The pin moved with it; the guarantee did not: the token the report
    # signs into DcTokenCanonical is the one TeamTokenForReport returns, read
    # once, and a fallback carries none.
    plugin = _read(os.path.join(_PLUGIN_DIR, "Plugin.cs"))
    assert plugin.count("ApiClient.ReportTeamSeriesDc(") == 1
    assert ("ApiClient.ReportTeamSeriesDc(seriesId, myId, dcSteamId, t1Points, t2Points,\n"
            "                                             observedRoom, false);" in plugin)
    assert "TeamTokenForReport(" not in plugin, "Plugin.cs reads the report's token again"
    assert "dcToken" not in plugin, "Plugin.cs passes a token to ReportTeamSeriesDc again"
    start = api.index("public static void ReportTeamSeriesDc(")
    body = api[start:api.index("\n        }\n", start)]
    assert body.count("TeamTokenForReport(") == 1, "ReportTeamSeriesDc: one token read"
    read = body.index("gameToken = GameStateWatcher.TeamTokenForReport(seriesId, out tokenWhy)")
    gate = body.rfind("if (!fallback)", 0, read)
    assert gate > body.rfind('string gameToken = "";', 0, read) >= 0, "the read is prompt-only"
    assert body.index("reporterSteamId, seriesId, dcPlayerSteamId, gameToken)") > read, (
        "the canonical signs the token read here")


# ---- Round 11, finding M1: nothing issues or names a physical game 1 --------
#
# Round 7 let the room's creator name a series' physical game 1 from a read
# of the series showing nothing on record. The round-7 report's sequence
# (F31): the creator played the series' first game with every live-points
# post failing, its result waiting in the reporter's outbox, restarted, and
# named the NEXT game physical game 1; every seat took that chain, and once
# the queued result landed a leave could be settled under the wrong physical
# game. Rounds 8 to 10 had the server issue physical game 1 to the series'
# reporter (a route and its rules, the queue poll's record of every hand-out
# of the room, a match report's void and the DC report's session read), and
# each round's rules left a process of the reporter's account they could not
# see (round 10's review: a second process of the account that never polled
# the queue). Round 11 deleted all of it: no route issues one and no
# statement writes first_game_nonce (route (a)). Every series is then what a
# continuation series already was in round 10: tokenless, its leaves settled
# by an admin (dc_incomplete). The client half is plugin/TeamGameNumber.cs's
# sentinel. The tests below model the product with granted=False (no origin
# on record); a test that lets the lab write LAB_FIRST says why.

F31_ROOT = "b0b1b2b3b4b5b6b7"                   # the chain the restarted creator drew
F31_B = _cwire(F31_ROOT, 1)                     # physical game 2, named game 1 from absence
F31_C = _cwire(F31_ROOT, 2)                     # physical game 3: that chain's game 2

# What rounds 8 to 10 added to main.py to issue physical game 1 and bind it to
# one process: round 11 deleted every one of them.
_ISSUANCE = ("team_series_first_game", "_team_room_handed_out", "_team_first_game_void",
             "_team_first_game_session_hash", "_team_series_member_steams",
             "_team_first_game_schema_absent", "_team_first_game_bound_refusal",
             "_TEAM_FIRST_GAME_ISSUE_SQL", "_TEAM_FIRST_GAME_READ_SQL",
             "_TEAM_FIRST_GAME_VOID_SQL", "_TEAM_ROOM_HANDOUT_BIND_SQL")

# Round 10's issue statement, verbatim (main.py at 9ec3331): the control's
# writer.
_ROUND_10_ISSUE = (
    '_TEAM_FIRST_GAME_ISSUE_SQL = (\n'
    '    "UPDATE team_series SET first_game_nonce = CAST(:nonce AS text)"\n'
    '    " WHERE id = :sid AND first_game_nonce IS NULL"\n'
    '    "   AND first_game_session = CAST(:th AS text)"\n'
    '    " RETURNING first_game_nonce")\n')

_API_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api")
_WRITES = re.compile(r"\b(UPDATE|INSERT|SET|ALTER|COPY|DELETE|MERGE)\b", re.IGNORECASE)


def _first_game_statements(source):
    """What in the module `source` (a Python module's text) names
    first_game_nonce, sorted by line, as (line, text, writes): every string
    constant that names it but a docstring and a row key (the index of a
    subscript: a read is not a statement, and a write is found as an
    assignment, below), with whether it holds a verb that
    writes (adjacent literals are one constant, the parser joins them, so a
    statement written across lines is read whole; each piece of an f-string
    is a constant of its own), and every assignment whose target is an
    attribute or a subscript named first_game_nonce (an ORM or a row write),
    as (line, None, True)."""
    tree = ast.parse(source)
    not_statements = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                not_statements.add(id(body[0].value))
        if isinstance(node, ast.Subscript):
            not_statements.add(id(node.slice))
    found = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in not_statements and "first_game_nonce" in node.value):
            found.append((node.lineno, node.value, bool(_WRITES.search(node.value))))
        elif isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                if ((isinstance(target, ast.Attribute) and target.attr == "first_game_nonce")
                        or (isinstance(target, ast.Subscript)
                            and isinstance(target.slice, ast.Constant)
                            and target.slice.value == "first_game_nonce")):
                    found.append((node.lineno, None, True))
    return sorted(found, key=lambda f: f[0])


def test_nothing_issues_or_names_a_first_game():
    """M1 (round 11, route (a)): the API has no route that issues a series'
    physical game 1 and nothing that writes first_game_nonce, so the column
    is NULL on every series and every DC report's token is refused
    (main._team_game_first_game_refusal). Of every module in backend/api,
    main.py alone names the column, in exactly one statement,
    _TEAM_GAME_CROSSED_SQL, which reads it, and no assignment names it (the
    refusal reads the row's key, which is not a statement). None
    of what rounds 8 to 10 added to issue it and bind it to one process is
    left, and no path of the app ends in /first-game."""
    paths = [getattr(r, "path", "") for r in main.app.routes]
    assert paths and not [p for p in paths if p.endswith("/first-game")], paths
    assert [n for n in _ISSUANCE if hasattr(main, n)] == []
    named = {}
    for fn in sorted(os.listdir(_API_DIR)):
        if fn.endswith(".py"):
            found = _first_game_statements(_read(os.path.join(_API_DIR, fn)))
            if found:
                named[fn] = found
    assert list(named) == ["main.py"], sorted(named)
    assert [(text, writes) for _line, text, writes in named["main.py"]] == [
        (main._TEAM_GAME_CROSSED_SQL, False)], named["main.py"]


def test_the_no_writer_test_can_fail():
    """Control (#391) for the test above, on main.py's own text: round 10's
    issue statement put back is found, as a writer; so is an ORM-style or a
    row assignment of the column. The inert twins, a comment and a docstring
    that name the column beside a verb and a read of the row's key, are not
    statements, and the reader
    finds exactly what it found in the file."""
    source = _read(os.path.join(_API_DIR, "main.py"))
    base = _first_game_statements(source)
    assert [(t, w) for _l, t, w in base] == [(main._TEAM_GAME_CROSSED_SQL, False)], base
    issued = _first_game_statements(source + "\n" + _ROUND_10_ISSUE)
    assert [w for _l, _t, w in issued] == [False, True], issued
    assert "UPDATE team_series SET first_game_nonce" in issued[1][1], issued
    for line in ("series.first_game_nonce = nonce\n", 'row["first_game_nonce"] = nonce\n'):
        found = _first_game_statements(source + "\n" + line)
        assert [(t, w) for _l, t, w in found] == [(main._TEAM_GAME_CROSSED_SQL, False),
                                                  (None, True)], (line, found)
    inert = _first_game_statements(
        source + "\n# UPDATE team_series SET first_game_nonce = x\n"
        "def _inert():\n    \"\"\"UPDATE team_series SET first_game_nonce.\"\"\"\n"
        "    return rec[\"first_game_nonce\"]\n")
    assert inert == base, inert


_D1 = ["game-1", "game-2"]
_D1_TOKENS = ["none", "own-chain", "origin-chain"]


async def _d1(lab, game, tokens):
    """R11-D1, what a tokenless series costs, as the DC report settles it. The
    series stands 0-0 for game-1 and 1-0 to team 1 for game-2, in ROOM. In
    the game in progress every seat posts 1-0 and 1-1 naming it; seat 2
    (team 2) leaves and seats 0 and 1 report it at 1-1. `tokens` is what the
    posts and the reports carry:
      none          no token: what every current client carries, since no
                    seat holds an origin (the product since round 11);
      own-chain     a chain a client named from its own reading (F31_ROOT),
                    as a round-7 client's host publishes one;
      origin-chain  the chain counted from the series' physical game 1, which
                    the lab writes first (LAB_FIRST): what round 10 read in a
                    series it had issued one to. No product statement writes
                    one now.
    Returns the settlement."""
    ser = await lab.series(t1_wins=0 if game == "game-1" else 1, t2_wins=0,
                           granted=tokens == "origin-chain")
    ordinal = 1 if game == "game-1" else 2
    token = {"none": None, "own-chain": _cwire(F31_ROOT, ordinal),
             "origin-chain": _cwire(LAB_FIRST, ordinal)}[tokens]
    await _post_all(lab, ser, (1, 0), (1, 1), game=ordinal, room=ROOM, token=token)
    await _two_reports(lab, ser, HIGH, HIGH, token=token)
    return await lab.settlement(ser)


async def _f31(lab):
    """The F31 sequence under route (a), as the server sees it. The series
    stands 0-0 in ROOM with no physical game 1 on record (none is issued).
    Physical game 1 is played with no live-points post reaching the server;
    team 1 wins it and its result waits in an outbox. The creator restarts
    and names the next game physical game 1 from absence: physical game 2's
    seats post 1-0 naming game 1 (the recorded games plus one) and carrying
    that chain's game 1 (F31_B). Game 1's result lands. Physical game 3:
    every seat posts 1-0 and 1-1 naming game 2 and carrying that chain's game
    2 (F31_C) while game 2's result is still on its way; seat 2 (team 2)
    leaves and seats 0 and 1 report it naming the same token. Returns the
    settlement, the series' first_game_nonce and game 2's record."""
    ser = await lab.series(t1_wins=0, t2_wins=0, granted=False)
    await _post_all(lab, ser, (1, 0), game=1, room=ROOM, token=F31_B)
    await lab.win_game(ser, winner=1)
    await _post_all(lab, ser, (1, 0), (1, 1), game=2, room=ROOM, token=F31_C)
    await _two_reports(lab, ser, HIGH, HIGH, token=F31_C)
    return await lab.settlement(ser), await lab.first_game(ser), await lab.game_row(ser, 2)


@needs_pg
@pytest.mark.parametrize("tokens", _D1_TOKENS)
@pytest.mark.parametrize("game", _D1)
def test_a_tokenless_series_settles_every_leave_as_dc_incomplete(wired, game, tokens):
    """R11-D1: with no physical game 1 on record, which is every series since
    round 11, a leave in any game settles as dc_incomplete for an admin, with
    no result, rating or gold moved, whatever the posts and the reports
    carry: no token, or a chain a client named on its own. A leave in
    physical game 1 settled so in round 10 as well: no team is a game up
    there. The outcome route (a) removes is the other one: the lead-forfeit
    of a later game read from the chain counted from an issued game 1
    (origin-chain), which completes the series for team 1 here only because
    the lab writes that origin."""
    async def go():
        async with _Lab() as lab:
            return await _d1(lab, game, tokens)

    want = COMPLETED if (game, tokens) == ("game-2", "origin-chain") else INCOMPLETE
    assert _run(go()) == want
    assert len(wired) == (1 if want == COMPLETED else 0), wired


@needs_pg
def test_the_f31_sequence_settles_nothing(wired):
    """F31 (round 8) under route (a): the restarted creator, no live-points
    post of the first game reaching the server, and the queued result. The
    series goes to an admin (dc_incomplete): nothing is completed and no
    result, rating or gold moves, and the series has no physical game 1 on
    record. Every post of physical game 3 is on game 2's record with its
    token, so the refusal is the first-game rule's alone."""
    async def go():
        async with _Lab() as lab:
            return await _f31(lab)

    settled, first, record = _run(go())
    assert settled == INCOMPLETE, settled
    assert wired == [], wired
    assert first is None, first
    assert (record["game_token"], record["token_seats"], record["token_conflict"]) == (
        _nonce(F31_C), _GAME_TWO_BITS, False), record


@needs_pg
@pytest.mark.parametrize("mutant", ["absence-chain-read", "chain-unread", "pass-through"])
def test_the_tokenless_tests_can_fail(wired, monkeypatch, mutant):
    """Controls (#391) for the two tests above, every case under each mutant.
    absence-chain-read is round 7's server: a token is read whatever its
    origin (main._team_game_first_game_refusal answers None). The chain a
    client named on its own then completes game 2 for team 1, in _d1 and in
    the F31 sequence, and both tests turn red; a leave in game 1 and a
    tokenless game stay dc_incomplete. chain-unread takes every token's nonce
    as the one derived from the origin on record for its ordinal and epoch:
    with no origin on record that changes nothing, which shows the refusal
    of the product's series is the missing origin's, not the chain's. The
    inert twin changes nothing."""
    if mutant == "absence-chain-read":
        monkeypatch.setattr(main, "_team_game_first_game_refusal", lambda rec, token: None)
    elif mutant == "chain-unread":
        real = main._team_game_first_game_refusal

        def unchained(rec, token):
            issued = rec["first_game_nonce"]
            if main._team_game_token_valid(issued):
                token = ((main._team_game_chain_nonce(issued, token[1], token[2]),)
                         + tuple(token[1:]))
            return real(rec, token)

        monkeypatch.setattr(main, "_team_game_first_game_refusal", unchained)

    async def go():
        results = {}
        for game in _D1:
            for tokens in _D1_TOKENS:
                async with _Lab() as lab:
                    results[(game, tokens)] = await _d1(lab, game, tokens)
        async with _Lab() as lab:
            results["f31"] = (await _f31(lab))[0]
        return results

    completes = {("game-2", "origin-chain")}
    if mutant == "absence-chain-read":
        completes |= {("game-2", "own-chain"), "f31"}
    want = {(g, t): (COMPLETED if (g, t) in completes else INCOMPLETE)
            for g in _D1 for t in _D1_TOKENS}
    want["f31"] = COMPLETED if "f31" in completes else INCOMPLETE
    assert _run(go()) == want
    assert len(wired) == len(completes), wired


@pytest.fixture
def resolving(wired, monkeypatch):
    """`wired`, plus the lobby resolve's Steam session check stubbed (it reads
    steam_sessions, which the lab does not build)."""
    async def _checked(request, steam_id, db):
        return None

    monkeypatch.setattr(main, "_check_steam_session", _checked)
    return wired


@needs_pg
def test_the_team_lobby_resolve_carries_the_room_again(resolving):
    """M1 (round 11): round 10's lobby resolve withheld a started 2v2 seat's
    room, so that the queue poll, which recorded every hand-out of it, was
    the only route that named it (R10-D4). That record was deleted with the
    issue it served, so the resolve reports the seat's row verbatim again, as
    it did before round 10: its status, series, team, room and region, with
    the room's rules."""
    async def go():
        async with _Lab() as lab:
            ser = await lab.series(t1_wins=0, t2_wins=0, granted=False)
            async with lab.engine.begin() as c:
                await c.run_sync(models.Base.metadata.create_all,
                                 tables=[models.TeamQueue.__table__])
            await lab.sql(
                "INSERT INTO team_queue (player_id, steam_id, display_name, rating,"
                " rating_deviation, completed_series, fallback_rating, status, series_id,"
                " team_assigned, room_name, room_region, ready, joined_at, queue_type,"
                " seen_settings_version)"
                " VALUES (:p, :s, 'tdc', 1500, 350, 0, 1500, 'ready_join', :sid, 1,"
                "         'team_0123456789ab', 'eu', true, NOW(), 'manual', 0)",
                {"p": ser["pids"][0], "s": ser["steams"][0], "sid": ser["sid"]})
            request = types.SimpleNamespace(state=types.SimpleNamespace(scr_session_verified=True),
                                            headers={})
            async with lab.sm() as db:
                return ser, await main._lobby_resolve_impl("team", ser["steams"][0], request, db)

    ser, out = _run(go())
    assert {k: out.get(k) for k in ("status", "series_id", "room_name", "room_region",
                                    "team_assigned")} == {
        "status": "ready_join", "series_id": str(ser["sid"]), "room_name": "team_0123456789ab",
        "room_region": "eu", "team_assigned": 1}, out
    assert "rules" in out and "rules_prop" in out, out


@needs_pg
def test_migration_359_runs_twice_over_a_354_table(wired):
    """359 over a 354 series table that already holds a series: the series
    reads no physical game 1 (NULL); a second run, and 354 and then 359
    again, change nothing; the column takes 16 lowercase hex digits and
    refuses anything else, 'void' included (round 11: nothing voids)."""
    async def state(conn):
        cols = [r["column_name"] for r in await conn.fetch(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = current_schema() AND table_name = 'team_series'"
            " ORDER BY ordinal_position")]
        cons = sorted(r["def"] for r in await conn.fetch(
            "SELECT pg_get_constraintdef(oid) AS def FROM pg_constraint"
            " WHERE conrelid = 'team_series'::regclass AND contype = 'c'"))
        rows = [tuple(r) for r in await conn.fetch(
            "SELECT id, first_game_nonce FROM team_series ORDER BY id")]
        return cols, cons, rows

    async def go():
        async with _Lab(with_first_game=False) as lab:
            ser = await lab.series(t1_wins=0, t2_wins=0)
            conn = await asyncpg.connect(PLAIN_DSN)
            try:
                await conn.execute('SET search_path TO "%s"' % lab.schema)
                await conn.execute(_read(MIGRATION_359))
                first = await state(conn)
                await conn.execute(_read(MIGRATION_359))
                again = await state(conn)
                await conn.execute(_read(MIGRATION_354))
                await conn.execute(_read(MIGRATION_359))
                after_354 = await state(conn)
                refused = []
                for bad in ("NOT-A-NONCE", "0123456789ABCDEF", "0123456789abcde",
                            "0123456789abcdef0", "void", "VOID", "voided", " void", ""):
                    try:
                        await conn.execute("UPDATE team_series SET first_game_nonce = $1"
                                           " WHERE id = $2", bad, ser["sid"])
                    except asyncpg.CheckViolationError:
                        refused.append(bad)
                await conn.execute("UPDATE team_series SET first_game_nonce = $1"
                                   " WHERE id = $2", LAB_FIRST, ser["sid"])
                kept = await conn.fetchval(
                    "SELECT first_game_nonce FROM team_series WHERE id = $1", ser["sid"])
                return ser, first, again, after_354, refused, kept
            finally:
                await conn.close()

    ser, first, again, after_354, refused, kept = _run(go())
    cols, _cons, rows = first
    assert cols[-1] == "first_game_nonce", cols
    assert rows == [(ser["sid"], None)], rows
    assert again == first and after_354 == first, (first, again, after_354)
    assert len(refused) == 9, refused
    assert kept == LAB_FIRST, kept


@needs_pg
@pytest.mark.parametrize("with_359", [False, True], ids=["before-359", "after-359"])
def test_before_migration_359_nothing_fails_and_nothing_auto_completes(wired, with_359):
    """The deploy-order claim in 359's header: this API against a database
    with 354 but not 359 fails no request. Every post is recorded, and the
    DC report settles as dc_incomplete on a game a seat of each team posted
    1-1 in, naming it and carrying the lab's token (the record's read names
    the missing column inside its savepoint). The twin, once 359 is applied
    and the lab has written the series' physical game 1, completes."""
    async def go():
        async with _Lab(with_first_game=with_359) as lab:
            ser = await lab.series(t1_wins=0, t2_wins=0)
            await lab.win_game(ser, winner=1)
            posted = [await lab.post(ser, seat, 1, 1, game=2, room=ROOM) for seat in (0, 2)]
            await _two_reports(lab, ser, LOW, LOW)
            rows = (await lab.sql("SELECT count(*) AS n FROM team_series_games"
                                  " WHERE series_id = :sid", {"sid": ser["sid"]}))[0]["n"]
            return posted, rows, await lab.settlement(ser)

    posted, rows, settled = _run(go())
    assert [p["status"] for p in posted] == ["ok", "ok"], posted
    assert rows == 1, rows
    assert settled == (COMPLETED if with_359 else INCOMPLETE), settled


# ---- Round 9, finding M2: the chain bound to the whole origin -------------
#
# Round 8 bound a DC report's token to physical game 1 by the origin's first
# 8 digits (a later game's host drew its nonce as those 8 digits and 8 fresh
# ones, and the server read a token whose first 8 digits matched): 32 bits,
# so a chain from another origin that shared them was read. Since round 9
# game 1's token carries the whole origin, every later game's nonce is
# derived from it and the token's own ordinal and epoch
# (main._team_game_chain_nonce; plugin/TeamGameNumber.cs, ChainNonce), and it
# is compared at all 16 digits. A round-8 client's host token is unreadable.
# Since round 11 no product series has an origin on record; the lab writes
# LAB_FIRST so that the reader still has one to compare against.

_M2 = ["derived", "prefix-only-token"]


def _flip8(nonce):
    """A 16-digit nonce that matches `nonce` in exactly its first 8 digits:
    each of its last 8 moved by 8 (mod 16)."""
    return nonce[:8] + "".join("%x" % ((int(c, 16) + 8) % 16) for c in nonce[8:16])


async def _m2(lab, case):
    """The M2 sequence, in a fresh room. The series stands 0-0 with the lab's
    physical game 1 on record (LAB_FIRST). Game 1's posts carry it, and team
    1 wins it. Physical game 2: every seat posts 1-0 and 1-1 naming game 2
    and carrying game 2's token, its nonce derived from the whole origin,
    except for prefix-only-token, whose nonce shares only the origin's first
    8 digits (a round-8 host's); seat 2 (team 2) leaves and seats 0 and 1
    report it naming the same token. Returns the settlement."""
    ser = await lab.series(t1_wins=0, t2_wins=0)
    await _post_all(lab, ser, (1, 0), (1, 1), (2, 1), game=1, room=ROOM, token=_wire(LAB_FIRST, 1))
    await lab.win_game(ser, winner=1)
    two = _wire(_flip8(LAB_FIRST), 2) if case == "prefix-only-token" else _cwire(LAB_FIRST, 2)
    assert (_nonce(two) == _chain(LAB_FIRST, 2, 2)) == (case != "prefix-only-token"), two
    await _post_all(lab, ser, (1, 0), (1, 1), game=2, room=ROOM, token=two)
    await _two_reports(lab, ser, HIGH, HIGH, token=two)
    return await lab.settlement(ser)


@needs_pg
@pytest.mark.parametrize("case", _M2)
def test_a_chain_matching_only_the_first_eight_digits_is_unreadable(wired, case):
    """M2 (round 9): a game-2 token whose nonce shares only the first 8 hex
    digits of the origin on record is not read: the leave goes to an admin
    (dc_incomplete) and no result, rating or gold moves. The twin, its
    game-2 nonce derived from the whole origin, completes the series for
    team 1, the team a game up."""
    async def go():
        async with _Lab() as lab:
            return await _m2(lab, case)

    assert _run(go()) == {"derived": COMPLETED, "prefix-only-token": INCOMPLETE}[case]
    assert len(wired) == (1 if case == "derived" else 0), wired


@needs_pg
@pytest.mark.parametrize("mutant", ["round-8-read", "pass-through"])
def test_the_eight_digit_chain_test_can_fail(wired, monkeypatch, mutant):
    """M2's negative control (#391), both cases under each mutant. With round
    8's comparison of a token's first 8 digits restored (a token whose first
    8 digits are the origin's is handed on as the nonce derived for its
    ordinal and epoch), the game-2 token that matches only those digits is
    read and completes the series for team 1: the test above turns red. The
    derived twin completes under both, and the inert twin changes nothing."""
    if mutant == "round-8-read":
        real_read = main._team_game_first_game_refusal

        def round_8_read(rec, token):
            issued = rec["first_game_nonce"]
            if main._team_game_token_valid(issued) and token[0][:8] == issued[:8]:
                token = ((main._team_game_chain_nonce(issued, token[1], token[2]),)
                         + tuple(token[1:]))
            return real_read(rec, token)

        monkeypatch.setattr(main, "_team_game_first_game_refusal", round_8_read)

    async def go():
        results = {}
        for case in _M2:
            async with _Lab() as lab:
                results[case] = await _m2(lab, case)
        return results

    reads = mutant == "round-8-read"
    want = {"derived": COMPLETED, "prefix-only-token": COMPLETED if reads else INCOMPLETE}
    assert _run(go()) == want
    assert len(wired) == sum(1 for w in want.values() if w == COMPLETED), wired


def _cs_number(src, name):
    m = re.search(r'internal const (?:int|long) %s\s*=\s*(\d+);' % name, src)
    assert m, name
    return int(m.group(1))


def test_the_clients_chain_derivation_is_the_one_the_server_checks():
    """M2: plugin/TeamGameNumber.cs derives a later game's nonce exactly as
    main._team_game_chain_nonce does. Its message prefix is the server's,
    and its pin vector (PinChainRoot, PinChainOrdinal, PinChainEpoch and
    PinChainExpected; its sentinel checks that ChainNonce builds it) is what
    the server's derivation gives, and what the one computed here apart from
    both (_chain) gives. Game 1's nonce is the origin. The derivation moves
    with the ordinal, with the epoch and with the last 8 digits of the
    origin: a root that shares only its first 8 digits derives another
    nonce."""
    src = _read(os.path.join(_PLUGIN_DIR, "TeamGameNumber.cs"))
    root, expected = _cs_const(src, "PinChainRoot"), _cs_const(src, "PinChainExpected")
    ordinal, epoch = _cs_number(src, "PinChainOrdinal"), _cs_number(src, "PinChainEpoch")
    assert _cs_const(src, "ChainPrefix") == main._TEAM_GAME_CHAIN_PREFIX == "team-game-chain:"
    assert (root, ordinal, epoch, expected) == ("0123456789abcdef", 2, 7, "4f9833dd5e56800d")
    assert main._team_game_chain_nonce(root, ordinal, epoch) == expected
    assert _chain(root, ordinal, epoch) == expected
    assert main._team_game_chain_nonce(root, 1, epoch) == root
    derived = {main._team_game_chain_nonce(root, ordinal, epoch + 1),
               main._team_game_chain_nonce(root, ordinal + 1, epoch),
               main._team_game_chain_nonce(_flip8(root), ordinal, epoch), expected}
    assert len(derived) == 4, derived
    assert all(re.fullmatch(r"[0-9a-f]{16}", d) for d in derived), derived


def test_no_eight_digit_comparison_is_left_on_the_server():
    """M2: the read of a DC report's token against the origin's chain
    compares no slice of the nonce: it compares the whole of it
    (hmac.compare_digest) with the nonce derived from the origin."""
    src = inspect.getsource(main._team_game_first_game_refusal)
    assert "[:8]" not in src and "compare_digest" in src
    assert src.count("_team_game_chain_nonce(issued, token[1], token[2])") == 1
