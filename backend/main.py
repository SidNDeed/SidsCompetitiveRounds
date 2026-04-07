"""
Competitive ROUNDS API Server
FastAPI backend for match tracking, Glicko-2 ratings, and leaderboards.
"""

import hashlib
import hmac
import math
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import case, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from glicko2 import calculate_new_rating
from models import GlickoRating, Match, MatchCard, Player, RankedSeries, RatingHistory, RankedQueue, QueueBlock
from schemas import (
    CardStatEntry,
    HealthResponse,
    LeaderboardEntry,
    LeaderboardResponse,
    MatchHistoryEntry,
    MatchReport,
    MatchResponse,
    PlayerStatsResponse,
    QueueJoinRequest,
    QueueDeclineRequest,
    QueuePollResponse,
)

# ── Config from environment ────────────────────────────────────

MATCH_HMAC_SECRET = os.getenv("MATCH_HMAC_SECRET", "")
GLICKO2_TAU = float(os.getenv("GLICKO2_TAU", "0.5"))
GLICKO2_DEFAULT_RATING = float(os.getenv("GLICKO2_DEFAULT_RATING", "1500"))
GLICKO2_DEFAULT_RD = float(os.getenv("GLICKO2_DEFAULT_RD", "350"))
GLICKO2_DEFAULT_VOLATILITY = float(os.getenv("GLICKO2_DEFAULT_VOLATILITY", "0.06"))
GLICKO2_PERIOD_HOURS = int(os.getenv("GLICKO2_PERIOD_HOURS", "168"))


# ── Application setup ──────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    print("Competitive ROUNDS API starting up")
    yield
    print("Competitive ROUNDS API shutting down")


app = FastAPI(
    title="Competitive ROUNDS API",
    description="Backend for ranked matchmaking, Glicko-2 ratings, and card stats in ROUNDS.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production if adding a web dashboard
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ────────────────────────────────────────────────────

async def get_or_create_player(db: AsyncSession, steam_id: str, display_name: str) -> Player:
    """
    Find an existing player by Steam ID or create a new one.
    Also creates their initial Glicko-2 rating row.
    """
    result = await db.execute(select(Player).where(Player.steam_id == steam_id))
    player = result.scalar_one_or_none()

    if player:
        player.display_name = display_name
        player.last_seen = datetime.now(timezone.utc)
        return player

    # New player
    player = Player(steam_id=steam_id, display_name=display_name)
    db.add(player)
    await db.flush()  # Get the player.id

    # Create initial rating
    glicko = GlickoRating(
        player_id=player.id,
        rating=GLICKO2_DEFAULT_RATING,
        rating_deviation=GLICKO2_DEFAULT_RD,
        volatility=GLICKO2_DEFAULT_VOLATILITY,
    )
    db.add(glicko)
    return player


def verify_hmac(report: MatchReport) -> bool:
    """
    Verify the HMAC signature on a match report.
    Returns True if HMAC is disabled (no secret set) or if signature is valid.
    """
    if not MATCH_HMAC_SECRET:
        return True  # HMAC not configured yet (Phase 4)
    if not report.hmac_signature:
        return False

    # Build the message to sign (deterministic field order)
    message = (
        f"{report.player1.steam_id}:{report.player2.steam_id}:"
        f"{report.p1_rounds_won}:{report.p2_rounds_won}:"
        f"{report.photon_room_id or ''}"
    )
    expected = hmac.new(
        MATCH_HMAC_SECRET.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(report.hmac_signature, expected)


# ── XP System ──────────────────────────────────────────────────

def xp_for_level(level: int) -> int:
    """XP required to go from level-1 to level. J-curve scaling."""
    if level <= 0:
        return 0
    return int(100 * math.pow(level, 1.5))


def total_xp_for_level(level: int) -> int:
    """Total cumulative XP needed to reach a given level."""
    return sum(xp_for_level(n) for n in range(1, level + 1))


def level_from_xp(total_xp: int) -> tuple[int, int, int]:
    """
    Given total XP, return (level, xp_into_current_level, xp_needed_for_next_level).
    Max level is 100.
    """
    level = 0
    remaining = total_xp
    for n in range(1, 101):
        needed = xp_for_level(n)
        if remaining < needed:
            return level, remaining, needed
        remaining -= needed
        level = n
    return 100, 0, 0  # Max level


async def calculate_match_xp(
    won: bool,
    is_ranked: bool,
    winner_rounds: int,
    loser_rounds: int,
    opponent_id,
    db: AsyncSession,
) -> tuple[int, list[str]]:
    """
    Calculate XP earned for a match. Returns (xp_amount, list_of_bonus_descriptions).

    Base: 250 XP per finished game
    Win: 1.5x multiplier
    Sweep (5-0): +100 flat bonus
    Ranked: 1.2x multiplier
    Beat top-5 player: +150 flat bonus
    """
    base_xp = 250
    bonuses = []
    multiplier = 1.0

    if won:
        multiplier *= 1.5
        bonuses.append("Win x1.5")

    if is_ranked:
        multiplier *= 1.2
        bonuses.append("Ranked x1.2")

    xp = int(base_xp * multiplier)

    # Sweep bonus
    if won and loser_rounds == 0:
        xp += 100
        bonuses.append("Sweep +100")

    # Top-5 bonus (check if opponent is in top 5 by rating)
    if won and opponent_id:
        try:
            top5_query = text("""
                SELECT player_id FROM glicko_ratings
                WHERE rating_deviation < 200
                ORDER BY rating DESC LIMIT 5
            """)
            top5 = (await db.execute(top5_query)).scalars().all()
            if opponent_id in top5:
                xp += 150
                bonuses.append("Top 5 opponent +150")
        except Exception:
            pass

    return xp, bonuses


# ── Routes: Health ─────────────────────────────────────────────

@app.get("/api/v1/health", response_model=HealthResponse, tags=["System"])
async def health_check(db: AsyncSession = Depends(get_db)):
    """Check if the API and database are operational."""
    try:
        await db.execute(text("SELECT 1"))
        return HealthResponse(status="ok", database="connected")
    except Exception:
        return HealthResponse(status="degraded", database="disconnected")


# ── Routes: Match Submission ───────────────────────────────────

@app.post("/api/v1/matches", response_model=MatchResponse, tags=["Matches"])
async def submit_match(report: MatchReport, db: AsyncSession = Depends(get_db)):
    """
    Submit a completed match result.
    Called by the BepInEx mod on the host player's client.
    """
    # Validate HMAC if configured
    if not verify_hmac(report):
        raise HTTPException(status_code=403, detail="Invalid match signature")

    # Validate: players can't be the same person
    if report.player1.steam_id == report.player2.steam_id:
        raise HTTPException(status_code=400, detail="Players cannot be the same")

    # Validate: someone must have won (ROUNDS doesn't draw)
    if report.p1_rounds_won == report.p2_rounds_won:
        raise HTTPException(status_code=400, detail="Match must have a winner")

    # Validate: round counts are reasonable for ROUNDS
    if report.p1_rounds_won > 5 or report.p2_rounds_won > 5:
        raise HTTPException(status_code=400, detail="Invalid round count")

    # Get or create both players
    p1 = await get_or_create_player(db, report.player1.steam_id, report.player1.display_name)
    p2 = await get_or_create_player(db, report.player2.steam_id, report.player2.display_name)

    # Determine winner
    winner = p1 if report.p1_rounds_won > report.p2_rounds_won else p2

    # Find the reporting player
    reporter = p1 if report.reported_by_steam_id == report.player1.steam_id else p2

    # Create match record
    match = Match(
        player1_id=p1.id,
        player2_id=p2.id,
        p1_rounds_won=report.p1_rounds_won,
        p2_rounds_won=report.p2_rounds_won,
        p1_points_total=report.p1_points_total,
        p2_points_total=report.p2_points_total,
        winner_id=winner.id,
        match_duration=report.match_duration,
        photon_room_id=report.photon_room_id,
        game_version=report.game_version,
        region=report.region,
        hmac_signature=report.hmac_signature,
        reported_by=reporter.id,
        is_ranked=report.is_ranked,
        started_at=report.started_at,
    )
    db.add(match)
    await db.flush()  # Get match.id

    # Record card picks for player 1
    for card in report.player1.cards:
        db.add(MatchCard(
            match_id=match.id,
            player_id=p1.id,
            card_name=card.card_name,
            card_rarity=card.card_rarity,
            pick_order=card.pick_order,
            round_number=card.round_number,
        ))

    # Record card picks for player 2
    for card in report.player2.cards:
        db.add(MatchCard(
            match_id=match.id,
            player_id=p2.id,
            card_name=card.card_name,
            card_rarity=card.card_rarity,
            pick_order=card.pick_order,
            round_number=card.round_number,
        ))

    # Increment games_in_period for both players
    for pid in [p1.id, p2.id]:
        result = await db.execute(select(GlickoRating).where(GlickoRating.player_id == pid))
        glicko = result.scalar_one_or_none()
        if glicko:
            glicko.games_in_period += 1
            glicko.updated_at = datetime.now(timezone.utc)

    # Award XP to both players
    winner_rounds = max(report.p1_rounds_won, report.p2_rounds_won)
    loser_rounds = min(report.p1_rounds_won, report.p2_rounds_won)
    loser = p2 if winner == p1 else p1

    p1_won = (winner == p1)
    p1_xp, p1_bonuses = await calculate_match_xp(
        won=p1_won, is_ranked=report.is_ranked,
        winner_rounds=winner_rounds, loser_rounds=loser_rounds,
        opponent_id=p2.id, db=db,
    )
    p2_xp, p2_bonuses = await calculate_match_xp(
        won=(not p1_won), is_ranked=report.is_ranked,
        winner_rounds=winner_rounds, loser_rounds=loser_rounds,
        opponent_id=p1.id, db=db,
    )

    p1.total_xp = (p1.total_xp or 0) + p1_xp
    p2.total_xp = (p2.total_xp or 0) + p2_xp

    # Store XP earned per player on the match record
    match.p1_xp_gained = p1_xp
    match.p2_xp_gained = p2_xp

    # Determine reporter's XP for the response
    if report.reported_by_steam_id == report.player1.steam_id:
        reporter_xp = p1_xp
        reporter_bonuses = p1_bonuses
        reporter_total_xp = p1.total_xp
    else:
        reporter_xp = p2_xp
        reporter_bonuses = p2_bonuses
        reporter_total_xp = p2.total_xp

    reporter_level, reporter_xp_into, reporter_xp_needed = level_from_xp(reporter_total_xp)

    # ── Best of 3 Series Logic (ranked only) ──────────────────
    series_status = "none"
    series_score = ""
    series_completed = False

    if report.is_ranked:
        # Find active series between these two players (order-independent)
        series_query = (
            select(RankedSeries)
            .where(
                RankedSeries.status == "active",
                or_(
                    (RankedSeries.player1_id == p1.id) & (RankedSeries.player2_id == p2.id),
                    (RankedSeries.player1_id == p2.id) & (RankedSeries.player2_id == p1.id),
                )
            )
        )
        series_result = await db.execute(series_query)
        series = series_result.scalar_one_or_none()

        if not series:
            # Create new series — p1/p2 order matches first match's order
            series = RankedSeries(
                player1_id=p1.id,
                player2_id=p2.id,
            )
            db.add(series)
            await db.flush()

        # Link match to series
        match.series_id = series.id

        # Increment series wins for the match winner
        if winner.id == series.player1_id:
            series.p1_series_wins += 1
        else:
            series.p2_series_wins += 1

        series_score = f"{series.p1_series_wins}-{series.p2_series_wins}"

        # Check if series is complete (first to 2)
        if series.p1_series_wins >= 2 or series.p2_series_wins >= 2:
            series.status = "completed"
            series.winner_id = series.player1_id if series.p1_series_wins >= 2 else series.player2_id
            series.completed_at = datetime.now(timezone.utc)
            series_status = "completed"
            series_completed = True
        else:
            series_status = "active"

    await db.commit()

    # Trigger Glicko recalculation only when a series completes
    # (for non-ranked matches, Glicko is not affected)
    if series_completed:
        # Inline recalculation for the two series players
        try:
            # Read both ratings BEFORE any updates (avoids ordering bug)
            g1_r = await db.execute(select(GlickoRating).where(GlickoRating.player_id == p1.id))
            g1 = g1_r.scalar_one_or_none()
            g2_r = await db.execute(select(GlickoRating).where(GlickoRating.player_id == p2.id))
            g2 = g2_r.scalar_one_or_none()

            if g1 and g2:
                p1_won_series = (series.winner_id == p1.id)

                # Calculate both new ratings using pre-update opponent values
                new_r1, new_rd1, new_vol1 = calculate_new_rating(
                    g1.rating, g1.rating_deviation, g1.volatility,
                    [(g2.rating, g2.rating_deviation, 1.0 if p1_won_series else 0.0)],
                    GLICKO2_TAU,
                )
                new_r2, new_rd2, new_vol2 = calculate_new_rating(
                    g2.rating, g2.rating_deviation, g2.volatility,
                    [(g1.rating, g1.rating_deviation, 0.0 if p1_won_series else 1.0)],
                    GLICKO2_TAU,
                )

                # Store rating changes on the series for UI display
                series.p1_rating_change = round(new_r1 - g1.rating, 1)
                series.p2_rating_change = round(new_r2 - g2.rating, 1)

                # Apply updates
                now = datetime.now(timezone.utc)
                g1.rating = new_r1
                g1.rating_deviation = new_rd1
                g1.volatility = new_vol1
                g1.updated_at = now
                g2.rating = new_r2
                g2.rating_deviation = new_rd2
                g2.volatility = new_vol2
                g2.updated_at = now

            await db.commit()
        except Exception as ex:
            print(f"Series Glicko update error: {ex}")

    return MatchResponse(
        match_id=match.id,
        winner_steam_id=winner.steam_id,
        message="Match recorded successfully",
        xp_gained=reporter_xp,
        xp_bonuses=reporter_bonuses,
        total_xp=reporter_total_xp,
        level=reporter_level,
        series_status=series_status,
        series_score=series_score,
    )


# ── Routes: Leaderboard ───────────────────────────────────────

@app.get("/api/v1/leaderboard", response_model=LeaderboardResponse, tags=["Leaderboard"])
async def get_leaderboard(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    min_matches: int = Query(5, ge=0, description="Minimum matches to appear"),
    db: AsyncSession = Depends(get_db),
):
    """Get the ranked leaderboard sorted by Glicko-2 rating."""

    # Leaderboard counts: completed series W/L + legacy individual ranked matches
    query = text("""
        WITH series_stats AS (
            SELECT
                sub.player_id,
                SUM(sub.won) AS wins,
                SUM(sub.lost) AS losses,
                COUNT(*) AS total
            FROM (
                SELECT rs.player1_id AS player_id,
                       CASE WHEN rs.winner_id = rs.player1_id THEN 1 ELSE 0 END AS won,
                       CASE WHEN rs.winner_id != rs.player1_id THEN 1 ELSE 0 END AS lost
                FROM ranked_series rs WHERE rs.status = 'completed'
                UNION ALL
                SELECT rs.player2_id AS player_id,
                       CASE WHEN rs.winner_id = rs.player2_id THEN 1 ELSE 0 END AS won,
                       CASE WHEN rs.winner_id != rs.player2_id THEN 1 ELSE 0 END AS lost
                FROM ranked_series rs WHERE rs.status = 'completed'
            ) sub
            GROUP BY sub.player_id
        ),
        legacy_stats AS (
            SELECT
                p.id AS player_id,
                COALESCE(SUM(CASE WHEN m.winner_id = p.id THEN 1 ELSE 0 END), 0) AS wins,
                COALESCE(SUM(CASE WHEN m.winner_id IS NOT NULL AND m.winner_id != p.id THEN 1 ELSE 0 END), 0) AS losses,
                COUNT(m.id) AS total
            FROM players p
            LEFT JOIN matches m ON (m.player1_id = p.id OR m.player2_id = p.id)
                AND m.is_ranked = true AND m.series_id IS NULL
            GROUP BY p.id
        ),
        combined AS (
            SELECT
                p.id AS player_id,
                COALESCE(ss.wins, 0) + COALESCE(ls.wins, 0) AS wins,
                COALESCE(ss.losses, 0) + COALESCE(ls.losses, 0) AS losses,
                COALESCE(ss.total, 0) + COALESCE(ls.total, 0) AS total
            FROM players p
            LEFT JOIN series_stats ss ON ss.player_id = p.id
            LEFT JOIN legacy_stats ls ON ls.player_id = p.id
        )
        SELECT
            ROW_NUMBER() OVER (ORDER BY gr.rating DESC) AS rank,
            p.steam_id,
            p.display_name,
            ROUND(gr.rating::numeric, 0) AS rating,
            ROUND(gr.rating_deviation::numeric, 0) AS rd,
            COALESCE(c.total, 0) AS total_matches,
            COALESCE(c.wins, 0) AS wins,
            COALESCE(c.losses, 0) AS losses,
            CASE WHEN COALESCE(c.total, 0) > 0
                 THEN ROUND(COALESCE(c.wins, 0)::numeric / c.total, 4)
                 ELSE 0 END AS win_rate,
            COALESCE(p.total_xp, 0) AS total_xp
        FROM glicko_ratings gr
        JOIN players p ON p.id = gr.player_id
        LEFT JOIN combined c ON c.player_id = p.id
        WHERE COALESCE(c.total, 0) >= :min_matches
          AND gr.rating_deviation < 200
        ORDER BY gr.rating DESC
        LIMIT :limit OFFSET :offset
    """)

    result = await db.execute(query, {"min_matches": min_matches, "limit": limit, "offset": offset})
    rows = result.mappings().all()

    entries = [
        LeaderboardEntry(
            rank=row["rank"] + offset,
            steam_id=row["steam_id"],
            display_name=row["display_name"],
            rating=int(row["rating"]),
            rd=int(row["rd"]),
            total_matches=row["total_matches"],
            wins=row["wins"],
            losses=row["losses"],
            win_rate=float(row["win_rate"]),
            level=level_from_xp(row["total_xp"])[0],
        )
        for row in rows
    ]

    # Total players who qualify
    count_query = text("""
        WITH series_stats AS (
            SELECT sub.player_id, COUNT(*) AS total
            FROM (
                SELECT rs.player1_id AS player_id FROM ranked_series rs WHERE rs.status = 'completed'
                UNION ALL
                SELECT rs.player2_id AS player_id FROM ranked_series rs WHERE rs.status = 'completed'
            ) sub GROUP BY sub.player_id
        ),
        legacy_stats AS (
            SELECT p.id AS player_id, COUNT(m.id) AS total
            FROM players p
            LEFT JOIN matches m ON (m.player1_id = p.id OR m.player2_id = p.id)
                AND m.is_ranked = true AND m.series_id IS NULL
            GROUP BY p.id
        ),
        combined AS (
            SELECT p.id AS player_id,
                   COALESCE(ss.total, 0) + COALESCE(ls.total, 0) AS total
            FROM players p
            LEFT JOIN series_stats ss ON ss.player_id = p.id
            LEFT JOIN legacy_stats ls ON ls.player_id = p.id
        )
        SELECT COUNT(*) FROM glicko_ratings gr
        JOIN players p ON p.id = gr.player_id
        LEFT JOIN combined c ON c.player_id = p.id
        WHERE COALESCE(c.total, 0) >= :min_matches AND gr.rating_deviation < 200
    """)
    total = (await db.execute(count_query, {"min_matches": min_matches})).scalar() or 0

    return LeaderboardResponse(
        entries=entries,
        total_players=total,
        last_updated=datetime.now(timezone.utc),
    )


# ── Routes: Player Stats ──────────────────────────────────────

@app.get("/api/v1/players/{steam_id}", response_model=PlayerStatsResponse, tags=["Players"])
async def get_player_stats(steam_id: str, db: AsyncSession = Depends(get_db)):
    """Get full stats for a player by Steam ID."""

    result = await db.execute(
        select(Player).where(Player.steam_id == steam_id)
    )
    player = result.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Get rating
    rating_result = await db.execute(
        select(GlickoRating).where(GlickoRating.player_id == player.id)
    )
    glicko = rating_result.scalar_one_or_none()

    # Get W/L stats
    stats_query = text("""
        SELECT
            COUNT(*) AS total_matches,
            SUM(CASE WHEN m.winner_id = :pid THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN m.winner_id IS NOT NULL AND m.winner_id != :pid THEN 1 ELSE 0 END) AS losses,
            MAX(m.ended_at) AS last_match
        FROM matches m
        WHERE m.player1_id = :pid OR m.player2_id = :pid
    """)
    stats = (await db.execute(stats_query, {"pid": player.id})).mappings().first()

    total = stats["total_matches"] or 0
    wins = stats["wins"] or 0
    losses = stats["losses"] or 0

    # Recent rating history (last 20 snapshots)
    history_result = await db.execute(
        select(RatingHistory)
        .where(RatingHistory.player_id == player.id)
        .order_by(RatingHistory.period_end.desc())
        .limit(20)
    )
    history = [
        {"rating": round(h.rating), "rd": round(h.rating_deviation), "date": h.period_end.isoformat()}
        for h in history_result.scalars().all()
    ]

    # Top cards by pick count
    cards_query = text("""
        SELECT
            mc.card_name,
            COUNT(*) AS times_picked,
            SUM(CASE WHEN m.winner_id = :pid THEN 1 ELSE 0 END) AS wins_with,
            ROUND(
                SUM(CASE WHEN m.winner_id = :pid THEN 1 ELSE 0 END)::numeric
                / NULLIF(COUNT(*), 0), 4
            ) AS win_rate
        FROM match_cards mc
        JOIN matches m ON m.id = mc.match_id
        WHERE mc.player_id = :pid
        GROUP BY mc.card_name
        ORDER BY times_picked DESC
        LIMIT 10
    """)
    cards = (await db.execute(cards_query, {"pid": player.id})).mappings().all()
    top_cards = [
        {"card_name": c["card_name"], "times_picked": c["times_picked"],
         "wins_with": c["wins_with"], "win_rate": float(c["win_rate"] or 0)}
        for c in cards
    ]

    player_total_xp = player.total_xp or 0
    player_level, xp_into_level, xp_needed_for_next = level_from_xp(player_total_xp)

    # Compute best win streaks (ranked and casual)
    streak_query = text("""
        SELECT m.winner_id, m.is_ranked
        FROM matches m
        WHERE m.player1_id = :pid OR m.player2_id = :pid
        ORDER BY m.ended_at ASC
    """)
    streak_rows = (await db.execute(streak_query, {"pid": player.id})).mappings().all()

    best_ranked_streak = 0
    best_casual_streak = 0
    cur_ranked_streak = 0
    cur_casual_streak = 0
    for sr in streak_rows:
        won = (sr["winner_id"] == player.id)
        if sr["is_ranked"]:
            cur_ranked_streak = cur_ranked_streak + 1 if won else 0
            best_ranked_streak = max(best_ranked_streak, cur_ranked_streak)
        else:
            cur_casual_streak = cur_casual_streak + 1 if won else 0
            best_casual_streak = max(best_casual_streak, cur_casual_streak)

    # Compute series-aware ranked W/L (completed series + legacy individual ranked matches)
    ranked_wl_query = text("""
        WITH series_wl AS (
            SELECT
                SUM(CASE WHEN rs.winner_id = :pid THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN rs.winner_id IS NOT NULL AND rs.winner_id != :pid THEN 1 ELSE 0 END) AS losses
            FROM ranked_series rs
            WHERE rs.status = 'completed'
              AND (rs.player1_id = :pid OR rs.player2_id = :pid)
        ),
        legacy_wl AS (
            SELECT
                SUM(CASE WHEN m.winner_id = :pid THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN m.winner_id IS NOT NULL AND m.winner_id != :pid THEN 1 ELSE 0 END) AS losses
            FROM matches m
            WHERE (m.player1_id = :pid OR m.player2_id = :pid)
              AND m.is_ranked = true
              AND m.series_id IS NULL
        )
        SELECT
            COALESCE(s.wins, 0) + COALESCE(l.wins, 0) AS ranked_wins,
            COALESCE(s.losses, 0) + COALESCE(l.losses, 0) AS ranked_losses
        FROM series_wl s, legacy_wl l
    """)
    ranked_wl = (await db.execute(ranked_wl_query, {"pid": player.id})).mappings().first()
    ranked_series_wins = ranked_wl["ranked_wins"] if ranked_wl else 0
    ranked_series_losses = ranked_wl["ranked_losses"] if ranked_wl else 0

    return PlayerStatsResponse(
        steam_id=player.steam_id,
        display_name=player.display_name,
        rating=round(glicko.rating, 1) if glicko else GLICKO2_DEFAULT_RATING,
        rating_deviation=round(glicko.rating_deviation, 1) if glicko else GLICKO2_DEFAULT_RD,
        volatility=round(glicko.volatility, 4) if glicko else GLICKO2_DEFAULT_VOLATILITY,
        total_matches=total,
        wins=wins,
        losses=losses,
        win_rate=round(wins / total, 4) if total > 0 else 0.0,
        ranked_enabled=player.ranked_enabled,
        last_match=stats["last_match"],
        recent_rating_history=history,
        top_cards=top_cards,
        level=player_level,
        total_xp=player_total_xp,
        xp_into_level=xp_into_level,
        xp_for_next_level=xp_needed_for_next,
        best_ranked_streak=best_ranked_streak,
        best_casual_streak=best_casual_streak,
        ranked_series_wins=ranked_series_wins,
        ranked_series_losses=ranked_series_losses,
    )


# ── Routes: Match History ──────────────────────────────────────

@app.get("/api/v1/players/{steam_id}/matches", response_model=list[MatchHistoryEntry], tags=["Players"])
async def get_player_matches(
    steam_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Get a player's match history."""

    result = await db.execute(select(Player).where(Player.steam_id == steam_id))
    player = result.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    query = text("""
        SELECT
            m.id AS match_id,
            m.ended_at,
            m.winner_id,
            m.is_ranked,
            CASE WHEN m.player1_id = :pid THEN m.p1_rounds_won ELSE m.p2_rounds_won END AS player_rounds,
            CASE WHEN m.player1_id = :pid THEN m.p2_rounds_won ELSE m.p1_rounds_won END AS opp_rounds,
            CASE WHEN m.player1_id = :pid THEN p2.steam_id ELSE p1.steam_id END AS opp_steam_id,
            CASE WHEN m.player1_id = :pid THEN p2.display_name ELSE p1.display_name END AS opp_name,
            CASE WHEN m.player1_id = :pid THEN m.player2_id ELSE m.player1_id END AS opp_id,
            m.series_id::text AS series_id,
            rs.status AS series_status,
            rs.p1_series_wins AS s_p1w,
            rs.p2_series_wins AS s_p2w,
            rs.player1_id AS s_p1id,
            CASE WHEN rs.player1_id = :pid THEN rs.p1_rating_change
                 ELSE rs.p2_rating_change END AS series_rating_change,
            CASE WHEN m.player1_id = :pid THEN m.p1_xp_gained
                 ELSE m.p2_xp_gained END AS xp_gained
        FROM matches m
        JOIN players p1 ON p1.id = m.player1_id
        JOIN players p2 ON p2.id = m.player2_id
        LEFT JOIN ranked_series rs ON rs.id = m.series_id
        WHERE m.player1_id = :pid OR m.player2_id = :pid
        ORDER BY m.ended_at DESC
        LIMIT :limit OFFSET :offset
    """)
    rows = (await db.execute(query, {"pid": player.id, "limit": limit, "offset": offset})).mappings().all()

    entries = []
    for row in rows:
        # Get cards for this player in this match
        cards_result = await db.execute(
            select(MatchCard)
            .where(MatchCard.match_id == row["match_id"], MatchCard.player_id == player.id)
            .order_by(MatchCard.round_number, MatchCard.pick_order)
        )
        cards = [
            {"card_name": c.card_name, "card_rarity": c.card_rarity,
             "pick_order": c.pick_order, "round_number": c.round_number}
            for c in cards_result.scalars().all()
        ]

        # Get opponent's cards in this match
        opp_cards_result = await db.execute(
            select(MatchCard)
            .where(MatchCard.match_id == row["match_id"], MatchCard.player_id == row["opp_id"])
            .order_by(MatchCard.round_number, MatchCard.pick_order)
        )
        opp_cards = [
            {"card_name": c.card_name, "card_rarity": c.card_rarity,
             "pick_order": c.pick_order, "round_number": c.round_number}
            for c in opp_cards_result.scalars().all()
        ]

        # Compute series score from the requesting player's perspective
        series_id_str = row["series_id"] if "series_id" in row.keys() else None
        series_score_str = None
        series_rc = None
        if series_id_str:
            s_p1w = row["s_p1w"] or 0
            s_p2w = row["s_p2w"] or 0
            s_p1id = row["s_p1id"]
            # Show score as "my_wins - their_wins"
            if s_p1id == player.id:
                series_score_str = f"{s_p1w}-{s_p2w}"
            else:
                series_score_str = f"{s_p2w}-{s_p1w}"
            series_rc = float(row["series_rating_change"]) if row["series_rating_change"] is not None else None

        entries.append(MatchHistoryEntry(
            match_id=row["match_id"],
            opponent_steam_id=row["opp_steam_id"],
            opponent_name=row["opp_name"],
            player_rounds_won=row["player_rounds"],
            opponent_rounds_won=row["opp_rounds"],
            won=(row["winner_id"] == player.id),
            ended_at=row["ended_at"],
            is_ranked=row["is_ranked"] if "is_ranked" in row.keys() else False,
            cards_picked=cards,
            opponent_cards_picked=opp_cards,
            series_id=series_id_str,
            series_score=series_score_str,
            series_rating_change=series_rc,
            xp_gained=row["xp_gained"] or 0,
        ))

    return entries


# ── Routes: Card Stats ─────────────────────────────────────────

@app.get("/api/v1/cards", response_model=list[CardStatEntry], tags=["Cards"])
async def get_card_stats(
    sort_by: str = Query("times_picked", enum=["times_picked", "win_rate", "card_name"]),
    order: str = Query("desc", enum=["asc", "desc"]),
    limit: int = Query(50, ge=1, le=200),
    min_picks: int = Query(5, ge=0, description="Minimum times picked to appear"),
    steam_id: str | None = Query(None, description="Filter to a specific player's cards"),
    is_ranked: str | None = Query(None, description="Filter by ranked (true) or casual (false)"),
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated card statistics. Optionally filter to a single player and/or ranked/casual."""

    # Build WHERE clause for optional filters
    player_filter = ""
    ranked_filter = ""
    params = {"min_picks": min_picks, "limit": limit}

    if steam_id:
        player_filter = "AND mc.player_id = (SELECT id FROM players WHERE steam_id = :steam_id)"
        params["steam_id"] = steam_id

    if is_ranked == "true":
        ranked_filter = "AND m.is_ranked = true"
    elif is_ranked == "false":
        ranked_filter = "AND m.is_ranked = false"

    query = text(f"""
        SELECT
            mc.card_name,
            mc.card_rarity,
            COUNT(*) AS times_picked,
            COUNT(DISTINCT mc.match_id) AS matches_appeared,
            COUNT(DISTINCT mc.player_id) AS unique_players,
            SUM(CASE WHEN m.winner_id = mc.player_id THEN 1 ELSE 0 END) AS wins_with_card,
            ROUND(
                SUM(CASE WHEN m.winner_id = mc.player_id THEN 1 ELSE 0 END)::numeric
                / NULLIF(COUNT(*), 0), 4
            ) AS win_rate
        FROM match_cards mc
        JOIN matches m ON m.id = mc.match_id
        WHERE 1=1 {player_filter} {ranked_filter}
        GROUP BY mc.card_name, mc.card_rarity
        HAVING COUNT(*) >= :min_picks
        ORDER BY {sort_by} {"DESC" if order == "desc" else "ASC"}
        LIMIT :limit
    """)

    rows = (await db.execute(query, params)).mappings().all()

    return [
        CardStatEntry(
            card_name=r["card_name"],
            card_rarity=r["card_rarity"],
            times_picked=r["times_picked"],
            matches_appeared=r["matches_appeared"],
            unique_players=r["unique_players"],
            wins_with_card=r["wins_with_card"],
            win_rate=float(r["win_rate"] or 0),
        )
        for r in rows
    ]


# ── Routes: Glicko-2 Recalculation ────────────────────────────

@app.post("/api/v1/glicko/recalculate", tags=["System"])
async def recalculate_ratings(
    api_key: str = Query(..., description="API secret key for admin operations"),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger a Glicko-2 rating period recalculation.
    Processes all matches since the last calculation for each player.

    This should be called periodically (e.g. weekly via cron).
    Requires the API_SECRET_KEY for authentication.
    """
    expected_key = os.getenv("API_SECRET_KEY", "")
    if not expected_key or api_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    now = datetime.now(timezone.utc)
    updated_count = 0

    # Get all players with ratings
    result = await db.execute(
        select(GlickoRating).join(Player, Player.id == GlickoRating.player_id)
    )
    all_ratings = result.scalars().all()

    for glicko in all_ratings:
        pid = glicko.player_id

        # Get all matches this player played since last calculation
        matches_query = text("""
            SELECT
                m.id,
                m.winner_id,
                CASE WHEN m.player1_id = :pid THEN m.player2_id ELSE m.player1_id END AS opponent_id
            FROM matches m
            WHERE (m.player1_id = :pid OR m.player2_id = :pid)
              AND m.ended_at > :since
            ORDER BY m.ended_at
        """)
        matches = (await db.execute(matches_query, {
            "pid": pid, "since": glicko.last_calculated,
        })).mappings().all()

        # Build opponent list for Glicko-2
        opponents = []
        for m in matches:
            opp_rating_result = await db.execute(
                select(GlickoRating).where(GlickoRating.player_id == m["opponent_id"])
            )
            opp_glicko = opp_rating_result.scalar_one_or_none()
            if not opp_glicko:
                continue

            score = 1.0 if m["winner_id"] == pid else 0.0
            opponents.append((opp_glicko.rating, opp_glicko.rating_deviation, score))

        # Calculate new rating (handles 0 games too, just RD increases)
        new_rating, new_rd, new_vol = calculate_new_rating(
            rating=glicko.rating,
            rd=glicko.rating_deviation,
            volatility=glicko.volatility,
            opponents=opponents,
            tau=GLICKO2_TAU,
        )

        # Save history snapshot before updating
        db.add(RatingHistory(
            player_id=pid,
            rating=glicko.rating,
            rating_deviation=glicko.rating_deviation,
            volatility=glicko.volatility,
            period_end=now,
        ))

        # Update current rating
        glicko.rating = new_rating
        glicko.rating_deviation = new_rd
        glicko.volatility = new_vol
        glicko.games_in_period = 0
        glicko.last_calculated = now
        glicko.updated_at = now
        updated_count += 1

    # Refresh the card_stats materialized view
    await db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY card_stats"))

    await db.commit()

    return {
        "status": "ok",
        "players_updated": updated_count,
        "period_end": now.isoformat(),
    }


# ── Routes: Mod Handshake ─────────────────────────────────────

@app.get("/api/v1/mod/check/{steam_id}", tags=["Mod"])
async def check_player_registered(steam_id: str, db: AsyncSession = Depends(get_db)):
    """
    Quick check used by the BepInEx mod to see if a Steam ID
    is a registered competitive player with ranked mode enabled.
    Called during the Photon room handshake.
    """
    result = await db.execute(select(Player).where(Player.steam_id == steam_id))
    player = result.scalar_one_or_none()

    if not player:
        return {"registered": False, "ranked": False}

    return {
        "registered": True,
        "ranked": player.ranked_enabled,
        "display_name": player.display_name,
    }


@app.post("/api/v1/mod/toggle-ranked/{steam_id}", tags=["Mod"])
async def toggle_ranked(steam_id: str, enabled: bool = Query(...), db: AsyncSession = Depends(get_db)):
    """Toggle a player's ranked mode on or off."""
    result = await db.execute(select(Player).where(Player.steam_id == steam_id))
    player = result.scalar_one_or_none()

    if not player:
        raise HTTPException(status_code=404, detail="Player not found. Play a match first to register.")

    player.ranked_enabled = enabled
    await db.commit()

    return {"steam_id": steam_id, "ranked_enabled": enabled}


# ── Routes: Ranked Queue ──────────────────────────────────────

QUEUE_EXPIRE_MINUTES = 30
QUEUE_BLOCK_MINUTES = 5


def compute_elo_range(wait_seconds: int) -> int:
    """Stepped elo range expansion based on wait time."""
    if wait_seconds >= 120:
        return 800
    elif wait_seconds >= 60:
        return 400
    elif wait_seconds >= 30:
        return 200
    else:
        return 100


@app.post("/api/v1/queue/join", tags=["Queue"])
async def queue_join(req: QueueJoinRequest, db: AsyncSession = Depends(get_db)):
    """
    Join the ranked matchmaking queue.
    Upserts the player into ranked_queue with status='searching'.
    """
    # Find the player
    result = await db.execute(select(Player).where(Player.steam_id == req.steam_id))
    player = result.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found. Play a match first.")

    # Get their current rating
    rating_result = await db.execute(
        select(GlickoRating).where(GlickoRating.player_id == player.id)
    )
    glicko = rating_result.scalar_one_or_none()
    cur_rating = glicko.rating if glicko else GLICKO2_DEFAULT_RATING
    cur_rd = glicko.rating_deviation if glicko else GLICKO2_DEFAULT_RD

    # Upsert into queue
    stmt = pg_insert(RankedQueue).values(
        player_id=player.id,
        steam_id=req.steam_id,
        display_name=player.display_name,
        rating=cur_rating,
        rating_deviation=cur_rd,
        region=req.region,
        ranked_only=req.ranked_only,
        status="searching",
        matched_with=None,
        room_name=None,
        joined_at=datetime.now(timezone.utc),
        matched_at=None,
    ).on_conflict_do_update(
        index_elements=[RankedQueue.player_id],
        set_={
            "status": "searching",
            "rating": cur_rating,
            "rating_deviation": cur_rd,
            "region": req.region,
            "ranked_only": req.ranked_only,
            "matched_with": None,
            "room_name": None,
            "joined_at": datetime.now(timezone.utc),
            "matched_at": None,
        },
    )
    await db.execute(stmt)
    await db.commit()

    return {"status": "searching", "message": "Joined ranked queue"}


@app.post("/api/v1/queue/leave", tags=["Queue"])
async def queue_leave(steam_id: str = Query(...), db: AsyncSession = Depends(get_db)):
    """Leave the ranked queue."""
    result = await db.execute(select(Player).where(Player.steam_id == steam_id))
    player = result.scalar_one_or_none()
    if player:
        await db.execute(
            text("DELETE FROM ranked_queue WHERE player_id = :pid"),
            {"pid": player.id},
        )
        await db.commit()

    return {"status": "left", "message": "Left ranked queue"}


@app.get("/api/v1/queue/poll/{steam_id}", response_model=QueuePollResponse, tags=["Queue"])
async def queue_poll(steam_id: str, db: AsyncSession = Depends(get_db)):
    """
    Poll queue status. If searching, attempts to find a match.
    Uses SELECT FOR UPDATE SKIP LOCKED to prevent race conditions
    where both players' polls match each other simultaneously.
    Elo range expands in steps: ±100 / ±200@30s / ±400@60s / ±800@120s.
    """
    import uuid as uuid_mod

    # Clean up expired blocks opportunistically
    await db.execute(
        text("DELETE FROM queue_blocks WHERE expires_at < now()")
    )

    # Find our queue entry (lock it so no concurrent poll can match us)
    result = await db.execute(
        text("""
            SELECT rq.player_id, rq.steam_id, rq.display_name, rq.rating,
                   rq.rating_deviation, rq.status, rq.matched_with,
                   rq.room_name, rq.joined_at, rq.matched_at
            FROM ranked_queue rq
            JOIN players p ON rq.player_id = p.id
            WHERE p.steam_id = :sid
            FOR UPDATE OF rq
        """),
        {"sid": steam_id},
    )
    entry = result.mappings().first()

    if not entry:
        await db.commit()
        return QueuePollResponse(status="not_in_queue")

    now = datetime.now(timezone.utc)
    wait_seconds = int((now - entry["joined_at"]).total_seconds())

    # Check for expiry
    if wait_seconds > QUEUE_EXPIRE_MINUTES * 60:
        await db.execute(
            text("DELETE FROM ranked_queue WHERE player_id = :pid"),
            {"pid": entry["player_id"]},
        )
        await db.commit()
        return QueuePollResponse(status="expired", wait_time=wait_seconds)

    # Already matched — return match info
    if entry["status"] == "matched" and entry["room_name"]:
        opp_result = await db.execute(
            text("""
                SELECT steam_id, display_name, rating
                FROM ranked_queue WHERE player_id = :oid
            """),
            {"oid": entry["matched_with"]},
        )
        opp = opp_result.mappings().first()
        await db.commit()
        return QueuePollResponse(
            status="matched",
            wait_time=wait_seconds,
            opponent_steam_id=opp["steam_id"] if opp else "",
            opponent_name=opp["display_name"] if opp else "",
            opponent_rating=opp["rating"] if opp else 0,
            room_name=entry["room_name"],
        )

    # Still searching — try to find a match
    elo_range = compute_elo_range(wait_seconds)
    my_pid = entry["player_id"]
    my_rating = entry["rating"]
    min_rating = my_rating - elo_range
    max_rating = my_rating + elo_range

    # Find best candidate with row lock (SKIP LOCKED prevents two polls
    # from grabbing the same opponent simultaneously)
    candidate = await db.execute(
        text("""
            SELECT player_id, steam_id, display_name, rating
            FROM ranked_queue
            WHERE status = 'searching'
              AND player_id != :pid
              AND rating BETWEEN :rmin AND :rmax
              AND player_id NOT IN (
                  SELECT blocked_id FROM queue_blocks
                  WHERE blocker_id = :pid AND expires_at > now()
              )
              AND player_id NOT IN (
                  SELECT blocker_id FROM queue_blocks
                  WHERE blocked_id = :pid AND expires_at > now()
              )
            ORDER BY ABS(rating - :my_rating)
            LIMIT 1
            FOR UPDATE SKIP LOCKED
        """),
        {
            "pid": my_pid,
            "rmin": min_rating,
            "rmax": max_rating,
            "my_rating": my_rating,
        },
    )
    opp = candidate.mappings().first()

    if opp:
        # Match found — update both entries atomically
        room_name = f"ranked_{uuid_mod.uuid4().hex[:12]}"
        matched_at = datetime.now(timezone.utc)

        await db.execute(
            text("""
                UPDATE ranked_queue
                SET status = 'matched', matched_with = :opp_id,
                    room_name = :room, matched_at = :mat
                WHERE player_id = :pid
            """),
            {"opp_id": opp["player_id"], "room": room_name, "mat": matched_at, "pid": my_pid},
        )
        await db.execute(
            text("""
                UPDATE ranked_queue
                SET status = 'matched', matched_with = :my_id,
                    room_name = :room, matched_at = :mat
                WHERE player_id = :opp_id
            """),
            {"my_id": my_pid, "room": room_name, "mat": matched_at, "opp_id": opp["player_id"]},
        )
        await db.commit()

        return QueuePollResponse(
            status="matched",
            wait_time=wait_seconds,
            opponent_steam_id=opp["steam_id"],
            opponent_name=opp["display_name"],
            opponent_rating=opp["rating"],
            room_name=room_name,
        )

    # No match yet — return search status
    count_result = await db.execute(
        text("SELECT COUNT(*) FROM ranked_queue WHERE status = 'searching'")
    )
    queue_size = count_result.scalar() or 0
    await db.commit()

    return QueuePollResponse(
        status="searching",
        wait_time=wait_seconds,
        queue_size=queue_size,
        elo_range=elo_range,
    )


@app.post("/api/v1/queue/decline", tags=["Queue"])
async def queue_decline(req: QueueDeclineRequest, db: AsyncSession = Depends(get_db)):
    """
    Decline a matched opponent. Removes both from queue and
    blocks re-matching for 5 minutes (bidirectional).
    """
    # Resolve both player IDs
    p1_result = await db.execute(select(Player).where(Player.steam_id == req.steam_id))
    p1 = p1_result.scalar_one_or_none()
    p2_result = await db.execute(select(Player).where(Player.steam_id == req.opponent_steam_id))
    p2 = p2_result.scalar_one_or_none()

    if not p1 or not p2:
        raise HTTPException(status_code=404, detail="Player not found")

    expires = datetime.now(timezone.utc) + timedelta(minutes=QUEUE_BLOCK_MINUTES)

    # Insert block (bidirectional — both directions)
    for blocker, blocked in [(p1.id, p2.id), (p2.id, p1.id)]:
        await db.execute(
            text("""
                INSERT INTO queue_blocks (blocker_id, blocked_id, expires_at)
                VALUES (:b, :bl, :ex)
                ON CONFLICT (blocker_id, blocked_id)
                DO UPDATE SET expires_at = :ex
            """),
            {"b": blocker, "bl": blocked, "ex": expires},
        )

    # Remove the declining player from queue
    await db.execute(
        text("DELETE FROM ranked_queue WHERE player_id = :pid"),
        {"pid": p1.id},
    )

    # Reset the opponent back to searching (so they can find someone else)
    await db.execute(
        text("""
            UPDATE ranked_queue
            SET status = 'searching', matched_with = NULL,
                room_name = NULL, matched_at = NULL
            WHERE player_id = :pid AND status = 'matched'
        """),
        {"pid": p2.id},
    )

    await db.commit()
    return {"status": "declined", "message": f"Declined match. Blocked for {QUEUE_BLOCK_MINUTES} minutes."}
