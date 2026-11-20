"""A voided series stays out of the streak, live half: get_ranked_streak and
the 2v2 walk of get_player_team_stats run against PostgreSQL.

get_ranked_streak feeds the three streak achievements (on_fire, unstoppable,
immortal at 25/50/100) and the p1_streak/p2_streak of GET /api/v1/series/recent;
get_player_team_stats' current_streak is the 2v2 streak. Before this lane both
walks filtered by status only, and a reversed 1v1 series KEEPS status
'completed' (admin_reverse_series sets invalidated_at only), so a voided
series counted. Each case below plants one voided row in the house form
(status 'completed', invalidated_at set) and asks for the streak:

  - a voided win inside a run of wins: the streak is one shorter;
  - a voided loss between wins: the streak is not cut;
  - a voided newest row: the streak is read from the row before it.

The schema is the connect-failure lane's full replayed build (cf_pg.case).
CF_TEST_PG_DSN names the database; unset and not waived (CF_TEST_PG_OPTOUT=1),
every case FAILS (cf_pg.require_live_pg). Steam ids are synthetic (the
7656119000000xxxx form); no real account.
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import pytest  # noqa: E402

import main  # noqa: E402
import cf_pg  # noqa: E402

ME = "76561190000047701"
OPP = "76561190000047702"
THIRD = "76561190000047703"
FOURTH = "76561190000047704"
BASE = datetime(2026, 2, 1, tzinfo=timezone.utc)

# (won by ME, minute, voided). Each case lists its rows oldest first and
# plants them newest first, so the order comes from the walk's ORDER BY.
CASES = {
    # L W W(voided) W: counted, the run is 3; left out, 2.
    "voided_win_inside_a_run": ([(False, 1, False), (True, 2, False), (True, 3, True),
                                 (True, 4, False)], 2),
    # W L(voided) W: counted, the run is 1; left out, 2.
    "voided_loss_between_wins": ([(True, 1, False), (False, 2, True), (True, 3, False)], 2),
    # W W L(voided, newest): counted, -1; left out, 2.
    "voided_newest_row": ([(True, 1, False), (True, 2, False), (False, 3, True)], 2),
}


async def _ranked_streak_async(rows):
    async with cf_pg.case("voidstreakrs") as (c, sm):
        ids = {}
        async with sm() as db:
            for steam in (ME, OPP):
                ids[steam] = (await main.get_or_create_player(db, steam, "Void " + steam[-2:])).id
            await db.commit()
        for won, minute, voided in reversed(rows):
            p1_wins, p2_wins = (2, 0) if won else (0, 2)
            # ranked_series is made by the ORM, whose Python-side defaults are
            # not column defaults: every NOT NULL column is planted.
            await c.conn.execute(
                "INSERT INTO ranked_series (id, player1_id, player2_id, status, winner_id,"
                " p1_series_wins, p2_series_wins, live_p1_points, live_p2_points,"
                " is_tournament, is_private, created_at, completed_at, invalidated_at)"
                " VALUES ($1, $2, $3, 'completed', $4, $5, $6, 0, 0, false, false, $7, $7, $8)",
                uuid.uuid4(), ids[ME], ids[OPP], ids[ME] if won else ids[OPP], p1_wins, p2_wins,
                BASE + timedelta(minutes=minute),
                BASE + timedelta(days=30) if voided else None)
        async with sm() as db:
            return await main.get_ranked_streak(db, ME)


async def _team_streak_async(rows):
    async with cf_pg.case("voidstreakts") as (c, sm):
        ids = {}
        async with sm() as db:
            for steam in (ME, OPP, THIRD, FOURTH):
                ids[steam] = (await main.get_or_create_player(db, steam, "Void " + steam[-2:])).id
            await db.commit()
        for won, minute, voided in reversed(rows):
            await c.conn.execute(
                "INSERT INTO team_series (id, t1a_id, t1b_id, t2a_id, t2b_id, status,"
                " winner_team, created_at, completed_at, invalidated_at)"
                " VALUES ($1, $2, $3, $4, $5, 'completed', $6, $7, $7, $8)",
                uuid.uuid4(), ids[ME], ids[OPP], ids[THIRD], ids[FOURTH], 1 if won else 2,
                BASE + timedelta(minutes=minute),
                BASE + timedelta(days=30) if voided else None)
        async with sm() as db:
            got = await main.get_player_team_stats(steam_id=ME, db=db)
        return got.current_streak


@pytest.mark.parametrize("case", sorted(CASES))
def test_pg_ranked_streak_leaves_a_voided_series_out(case):
    cf_pg.require_live_pg()
    rows, want = CASES[case]
    assert asyncio.run(_ranked_streak_async(rows)) == want


@pytest.mark.parametrize("case", sorted(CASES))
def test_pg_team_streak_leaves_a_voided_series_out(case):
    cf_pg.require_live_pg()
    rows, want = CASES[case]
    assert asyncio.run(_team_streak_async(rows)) == want


def test_pg_ranked_streak_without_voided_rows_is_unchanged():
    """The control: the same shape with nothing voided reads as it always did."""
    cf_pg.require_live_pg()
    rows = [(False, 1, False), (True, 2, False), (True, 3, False), (True, 4, False)]
    assert asyncio.run(_ranked_streak_async(rows)) == 3
