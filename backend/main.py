"""
Competitive ROUNDS API Server
FastAPI backend for match tracking, Glicko-2 ratings, and leaderboards.
"""

import hashlib
import hmac
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
from models import GlickoRating, Match, MatchCard, Player, RatingHistory
from schemas import (
    CardStatEntry,
    HealthResponse,
    LeaderboardEntry,
    LeaderboardResponse,
    MatchHistoryEntry,
    MatchReport,
    MatchResponse,
    PlayerStatsResponse,
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

    await db.commit()

    return MatchResponse(
        match_id=match.id,
        winner_steam_id=winner.steam_id,
        message="Match recorded successfully",
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

    # Count matches per player (as both p1 and p2)
    match_counts = (
        select(
            func.coalesce(
                case(
                    (Match.player1_id == Player.id, Match.player1_id),
                    else_=Match.player2_id,
                ),
                Player.id,
            ).label("pid"),
        )
        .select_from(Player)
        .outerjoin(Match, or_(Match.player1_id == Player.id, Match.player2_id == Player.id))
        .group_by(Player.id)
    )

    # Main query using the leaderboard view
    query = text("""
        SELECT
            ROW_NUMBER() OVER (ORDER BY gr.rating DESC) AS rank,
            p.steam_id,
            p.display_name,
            ROUND(gr.rating::numeric, 0) AS rating,
            ROUND(gr.rating_deviation::numeric, 0) AS rd,
            COALESCE(stats.total, 0) AS total_matches,
            COALESCE(stats.wins, 0) AS wins,
            COALESCE(stats.losses, 0) AS losses,
            CASE WHEN COALESCE(stats.total, 0) > 0
                 THEN ROUND(COALESCE(stats.wins, 0)::numeric / stats.total, 4)
                 ELSE 0 END AS win_rate
        FROM glicko_ratings gr
        JOIN players p ON p.id = gr.player_id
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN m.winner_id = p.id THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN m.winner_id IS NOT NULL AND m.winner_id != p.id THEN 1 ELSE 0 END) AS losses
            FROM matches m
            WHERE m.player1_id = p.id OR m.player2_id = p.id
        ) stats ON true
        WHERE COALESCE(stats.total, 0) >= :min_matches
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
        )
        for row in rows
    ]

    # Total players who qualify
    count_query = text("""
        SELECT COUNT(*) FROM glicko_ratings gr
        JOIN players p ON p.id = gr.player_id
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS total
            FROM matches m WHERE m.player1_id = p.id OR m.player2_id = p.id
        ) stats ON true
        WHERE COALESCE(stats.total, 0) >= :min_matches AND gr.rating_deviation < 200
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
            CASE WHEN m.player1_id = :pid THEN p2.display_name ELSE p1.display_name END AS opp_name
        FROM matches m
        JOIN players p1 ON p1.id = m.player1_id
        JOIN players p2 ON p2.id = m.player2_id
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
        ))

    return entries


# ── Routes: Card Stats ─────────────────────────────────────────

@app.get("/api/v1/cards", response_model=list[CardStatEntry], tags=["Cards"])
async def get_card_stats(
    sort_by: str = Query("times_picked", enum=["times_picked", "win_rate", "card_name"]),
    order: str = Query("desc", enum=["asc", "desc"]),
    limit: int = Query(50, ge=1, le=200),
    min_picks: int = Query(5, ge=0, description="Minimum times picked to appear"),
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated card statistics across all matches."""

    # Query directly rather than relying on the materialized view,
    # so results are always fresh.
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
        GROUP BY mc.card_name, mc.card_rarity
        HAVING COUNT(*) >= :min_picks
        ORDER BY {sort_by} {"DESC" if order == "desc" else "ASC"}
        LIMIT :limit
    """)

    rows = (await db.execute(query, {"min_picks": min_picks, "limit": limit})).mappings().all()

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
