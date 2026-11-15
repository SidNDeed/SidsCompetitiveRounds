"""Bug report 463, live half: get_player_stats run against PostgreSQL.

test_casual_current_streak.py runs the handler's casual statement on SQLite
and reads the handler's source; this file calls the real handler,
main.get_player_stats, on real players and matches rows and asserts the
answer's current_casual_streak and best_casual_streak. So the value the
handler RETURNS is checked, on the production column types (TIMESTAMPTZ
end and creation times, UUID ids).

The schema is the connect-failure lane's full replayed build (cf_pg.case),
the build test_music_refund_413.py's account-deletion case uses for a handler
that reads most tables. CF_TEST_PG_DSN names the database; unset and not
waived (CF_TEST_PG_OPTOUT=1), every case FAILS (cf_pg.require_live_pg).

    CF_TEST_PG_DSN="postgresql+asyncpg://postgres@127.0.0.1:55432/cftest" \\
        python -m pytest backend/tests/test_casual_current_streak_pg.py

Rows are inserted in an order of the case's choosing (each case says which),
never chronologically by accident, so the walk's order comes from its
ORDER BY. The two tie cases pin the complete order: equal end times are
decided by created_at, then by id, exactly in reverse of the match history's
order (get_player_matches: ended_at DESC, created_at DESC, id DESC).
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import main  # noqa: E402
import cf_pg  # noqa: E402

# Synthetic steam ids (the 7656119000000xxxx form test_title_ladder_hooks_live
# uses): no real account.
ME = "76561190000046301"
OPP = "76561190000046302"
THIRD = "76561190000046303"
BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)

# Two fixed ids for the id tie-break: as uuid values LOW sorts before HIGH.
LOW_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
HIGH_ID = uuid.UUID("ffffffff-ffff-ffff-ffff-fffffffffffe")


def _m(winner, *, at, created=None, ranked=False, invalidated=False,
       players=(ME, OPP), mid=None):
    """One matches row: `winner` is a steam id; `at`/`created` are minutes
    after BASE (created defaults to at)."""
    return {"winner": winner, "at": at, "created": at if created is None else created,
            "ranked": ranked, "invalidated": invalidated, "players": players,
            "id": mid or uuid.uuid4()}


def _w(at, **kw):
    return _m(ME, at=at, **kw)


def _l(at, **kw):
    return _m(OPP, at=at, **kw)


async def _answer_async(rows):
    """Plant the players and `rows` (in list order) into a fresh case schema,
    then return (current_casual_streak, best_casual_streak) from
    main.get_player_stats(ME)."""
    async with cf_pg.case("streak463") as (c, sm):
        ids = {}
        async with sm() as db:
            for steam in (ME, OPP, THIRD):
                ids[steam] = (await main.get_or_create_player(db, steam, "Streak " + steam[-2:])).id
            await db.commit()
        for r in rows:
            p1, p2 = (ids[s] for s in r["players"])
            await c.conn.execute(
                "INSERT INTO matches (id, player1_id, player2_id, winner_id,"
                " p1_rounds_won, p2_rounds_won, p1_points_total, p2_points_total,"
                " is_ranked, invalidated_at, ended_at, created_at)"
                " VALUES ($1, $2, $3, $4, 3, 1, 0, 0, $5, $6, $7, $8)",
                r["id"], p1, p2, ids[r["winner"]], r["ranked"],
                BASE + timedelta(days=30) if r["invalidated"] else None,
                BASE + timedelta(minutes=r["at"]),
                BASE + timedelta(minutes=r["created"]))
        async with sm() as db:
            got = await main.get_player_stats(steam_id=ME, viewer_steam_id=None, db=db)
        return got.current_casual_streak, got.best_casual_streak


def _answer(rows):
    cf_pg.require_live_pg()
    return asyncio.run(_answer_async(rows))


async def _ranked_streak_async(series):
    """Plant the players and `series` (in list order) as completed
    ranked_series rows, then return main.get_ranked_streak(db, ME). Each
    entry: (winner steam id, completed minute, created minute)."""
    async with cf_pg.case("streak463rs") as (c, sm):
        ids = {}
        async with sm() as db:
            for steam in (ME, OPP):
                ids[steam] = (await main.get_or_create_player(db, steam, "Streak " + steam[-2:])).id
            await db.commit()
        for winner, completed, created in series:
            await c.conn.execute(
                "INSERT INTO ranked_series (id, player1_id, player2_id, status, winner_id,"
                " created_at, completed_at) VALUES ($1, $2, $3, 'completed', $4, $5, $6)",
                uuid.uuid4(), ids[ME], ids[OPP], ids[winner],
                BASE + timedelta(minutes=created), BASE + timedelta(minutes=completed))
        async with sm() as db:
            return await main.get_ranked_streak(db, ME)


def test_pg_ranked_streak_equal_completion_times_are_decided_by_created_at():
    """get_ranked_streak: A (a win) and B (a loss) completed at the same
    instant; A was created first, so B is the latest series by the full
    order (completed_at, created_at, id, all DESC): the streak is -1. B's
    row is inserted before A's."""
    cf_pg.require_live_pg()
    b = (OPP, 10, 2)
    a = (ME, 10, 1)
    assert asyncio.run(_ranked_streak_async([b, a])) == -1


def test_pg_w_w_l_gives_current_minus_1_and_best_2():
    # inserted newest first
    assert _answer([_l(3), _w(2), _w(1)]) == (-1, 2)


def test_pg_l_w_w_w_gives_3_and_3():
    # inserted out of order: 3, 1, 4, 2
    assert _answer([_w(3), _l(1), _w(4), _w(2)]) == (3, 3)


def test_pg_no_casual_match_gives_0_and_0():
    """The player has no match at all; two other players' casual games exist."""
    others = [_m(OPP, at=1, players=(OPP, THIRD)), _m(THIRD, at=2, players=(THIRD, OPP))]
    assert _answer(others) == (0, 0)


def test_pg_an_invalidated_match_and_a_ranked_match_are_skipped():
    """W W, an invalidated casual loss, a valid ranked loss, W: both losses
    are skipped, so the casual run is unbroken (3, 3); counted, either one
    would give (1, 2)."""
    rows = [_w(5), _l(3, invalidated=True), _w(1), _l(4, ranked=True), _w(2)]
    assert _answer(rows) == (3, 3)


def test_pg_equal_end_times_are_decided_by_created_at():
    """A (a win) and B (a loss) end at the same instant; A was created first,
    so B is the later match by the full order: the answer is -1. B's row is
    inserted before A's."""
    a = _w(10, created=1)
    b = _l(10, created=2)
    assert _answer([b, a]) == (-1, 1)


def test_pg_equal_end_and_created_times_are_decided_by_id():
    """X (a win, id HIGH_ID) and Y (a loss, id LOW_ID) share ended_at AND
    created_at. ORDER BY ... m.id ASC walks Y then X, so X is the later
    match: the answer is +1 (the history, id DESC, lists X first). X's row
    is inserted before Y's."""
    x = _w(10, created=5, mid=HIGH_ID)
    y = _l(10, created=5, mid=LOW_ID)
    assert _answer([x, y]) == (1, 1)
