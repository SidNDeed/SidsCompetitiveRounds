"""
Competitive ROUNDS API Server
FastAPI backend for match tracking, Glicko-2 ratings, and leaderboards.
"""

import asyncio
import hashlib
import hmac
import math
import os
import random
import string
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import uuid
from uuid import UUID

import json as _json
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import case, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from glicko2 import calculate_new_rating
from models import Bet, CardOffer, GlickoRating, GoldTransaction, Match, MatchCard, Player, PlayerItem, RankedSeries, RatingHistory, RankedQueue, QueueBlock, PlayerBlock, LinkCode, PlayerAchievement, ShopItem
from schemas import (
    AchievementUnlockRequest,
    AchievementListResponse,
    AchievementEntry,
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
    task = asyncio.create_task(queue_cleanup_loop())
    yield
    task.cancel()
    print("Competitive ROUNDS API shutting down")


async def queue_cleanup_loop():
    """Delete stale queue entries every 60 seconds."""
    import asyncio as _aio
    from database import async_session
    while True:
        try:
            await _aio.sleep(60)
            async with async_session() as db:
                result = await db.execute(
                    text("""DELETE FROM ranked_queue 
                        WHERE last_polled < NOW() - INTERVAL '30 seconds'
                           OR joined_at < NOW() - INTERVAL '30 minutes'
                        RETURNING steam_id, display_name""")
                )
                rows = result.fetchall()
                if rows:
                    names = [r[1] for r in rows]
                    print(f"[QUEUE-CLEANUP] Expired {len(rows)} stale entries: {', '.join(names)}")
                await db.commit()
        except Exception as e:
            print(f"[QUEUE-CLEANUP] Error: {e}")


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


# ── Version gate ───────────────────────────────────────────────
# Clients send X-Mod-Version on every request. If the version is below
# MIN_MOD_VERSION, the request is rejected with 426 so the mod can prompt
# the user to update before showing any data.
#
# Initial deploy grandfathers requests with no header (older clients in the
# wild). Once adoption of the header is universal, set REQUIRE_MOD_VERSION
# to True to lock out anyone who removes it.

MIN_MOD_VERSION = "1.20.0"
REQUIRE_MOD_VERSION = True  # Missing-header clients are pre-1.18.7 and should be locked out.

# Endpoints that bypass the gate (mod uses these to discover the required version).
# Use a frozenset of exact paths — startswith on a tuple containing "/" would match everything.
_VERSION_GATE_BYPASS = frozenset({
    "/api/v1/mod-version",
    "/api/v1/health",
    "/api/v1/healthz",
    "/api/v1/chat/post",      # internal bot relay; authenticated by X-Internal-Key instead
    "/api/v1/chat/recent",    # bot uses this for scrollback on WS reconnect too
})


def _parse_version(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except Exception:
        return (0,)


@app.middleware("http")
async def version_gate(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/v1/") or path in _VERSION_GATE_BYPASS:
        return await call_next(request)
    sent = request.headers.get("X-Mod-Version")
    if sent is None:
        if REQUIRE_MOD_VERSION:
            return JSONResponse(
                status_code=426,
                content={"error": "outdated", "required": MIN_MOD_VERSION, "current": None},
            )
        return await call_next(request)
    if _parse_version(sent) < _parse_version(MIN_MOD_VERSION):
        return JSONResponse(
            status_code=426,
            content={"error": "outdated", "required": MIN_MOD_VERSION, "current": sent},
        )
    return await call_next(request)


# ── Helpers ────────────────────────────────────────────────────

def _hash_steam_id(steam_id: str) -> str:
    """Server-salted one-way hash. Used to identify previously-purged Steam IDs
    without storing the Steam ID itself."""
    return hashlib.sha256(f"{MATCH_HMAC_SECRET}:{steam_id}".encode()).hexdigest()


async def _is_steam_id_purged(db: AsyncSession, steam_id: str) -> bool:
    if not MATCH_HMAC_SECRET:
        return False
    h = _hash_steam_id(steam_id)
    row = await db.execute(text("SELECT 1 FROM deleted_steam_ids WHERE steam_id_hash = :h"), {"h": h})
    return row.scalar() is not None


async def get_or_create_player(db: AsyncSession, steam_id: str, display_name: str) -> Player:
    """
    Find an existing player by Steam ID or create a new one.
    Also creates their initial Glicko-2 rating row.

    If the Steam ID was previously purged via /players/{steam_id}/data, the
    player is re-created as a permanent [Deleted User] tombstone. Their
    matches continue to process so opponents' stats stay consistent, but the
    deleted player never earns a rating, never shows on leaderboards, and
    can never reclaim their identity.
    """
    result = await db.execute(select(Player).where(Player.steam_id == steam_id))
    player = result.scalar_one_or_none()

    if player:
        # Don't resurrect a tombstoned row.
        if player.deleted_at is None:
            player.display_name = display_name
            player.last_seen = datetime.now(timezone.utc)
        return player

    # Was this Steam ID permanently deleted in a previous session?
    purged = await _is_steam_id_purged(db, steam_id)

    player = Player(
        steam_id=steam_id,
        display_name="[Deleted User]" if purged else display_name,
        ranked_enabled=False,
        deleted_at=datetime.now(timezone.utc) if purged else None,
    )
    db.add(player)
    await db.flush()  # Get the player.id

    # Tombstoned players still get a Glicko row so FK constraints hold, but
    # it's scoped out of the recalc by the deleted_at filter.
    glicko = GlickoRating(
        player_id=player.id,
        rating=GLICKO2_DEFAULT_RATING,
        rating_deviation=GLICKO2_DEFAULT_RD,
        volatility=GLICKO2_DEFAULT_VOLATILITY,
    )
    db.add(glicko)

    if purged:
        print(f"[PRIVACY] Re-registration blocked: steam_id={steam_id} was previously purged — tombstoned")
    return player


def verify_hmac(report: MatchReport) -> bool:
    """
    Verify the HMAC signature on a match report.
    Returns True if HMAC is disabled (no secret set) or if signature is valid.
    """
    if not MATCH_HMAC_SECRET:
        return True  # HMAC not configured yet (Phase 4)
    if not report.hmac_signature:
        print(f"[HMAC] No signature provided")
        return False

    # Build the message to sign (deterministic field order)
    message = (
        f"{report.player1.steam_id}:{report.player2.steam_id}:"
        f"{report.p1_rounds_won}:{report.p2_rounds_won}:"
        f"{str(report.is_ranked).lower()}:{report.reported_by_steam_id}:"
        f"{report.photon_room_id or ''}"
    )
    expected = hmac.new(
        MATCH_HMAC_SECRET.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()

    match = hmac.compare_digest(report.hmac_signature, expected)
    if not match:
        print(f"[HMAC] Signature mismatch for room {report.photon_room_id}")
    return match


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


LATEST_MOD_VERSION = "1.20.0"

@app.get("/api/v1/mod-version", tags=["System"])
async def get_mod_version():
    """Returns the latest recommended mod version and the gating floor."""
    return {"version": LATEST_MOD_VERSION, "min_version": MIN_MOD_VERSION}


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

    # Record per-player offered cards (pass-tracking). Only the local mod has
    # this for itself; opponent's offers may or may not be present.
    for player_obj, side in ((p1, report.player1), (p2, report.player2)):
        for offer in side.card_offers:
            db.add(CardOffer(
                match_id=match.id,
                player_id=player_obj.id,
                round_number=offer.round_number,
                card_name=offer.card_name,
                was_picked=offer.was_picked,
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

    # Convert XP milestones to gold BEFORE persisting — 100 XP = 1 gold.
    # Only the crossings matter (so we don't double-pay if a player re-reports).
    old_xp_p1 = p1.total_xp or 0
    old_xp_p2 = p2.total_xp or 0
    p1.total_xp = old_xp_p1 + p1_xp
    p2.total_xp = old_xp_p2 + p2_xp

    gold_p1 = (p1.total_xp // 100) - (old_xp_p1 // 100)
    gold_p2 = (p2.total_xp // 100) - (old_xp_p2 // 100)
    if gold_p1 > 0:
        p1.gold_earned = (p1.gold_earned or 0) + gold_p1
        db.add(GoldTransaction(player_id=p1.id, amount=gold_p1, reason="xp", reference_id=str(match.id)))
    if gold_p2 > 0:
        p2.gold_earned = (p2.gold_earned or 0) + gold_p2
        db.add(GoldTransaction(player_id=p2.id, amount=gold_p2, reason="xp", reference_id=str(match.id)))

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

            # +5 gold to the series winner, +1 extra if it was a 2-0 sweep.
            series_winner = p1 if series.p1_series_wins >= 2 else p2
            bonus = 5
            if series.p1_series_wins == 0 or series.p2_series_wins == 0:
                bonus += 1
            series_winner.gold_earned = (series_winner.gold_earned or 0) + bonus
            db.add(GoldTransaction(
                player_id=series_winner.id, amount=bonus,
                reason="series_win", reference_id=str(series.id),
            ))

            # Settle all pending bets on this series.
            await _settle_series_bets(db, series)
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
                # Must map match-report p1/p2 to the series' player1/player2
                # (match report order can differ from series order)
                rc_match_p1 = round(new_r1 - g1.rating, 1)
                rc_match_p2 = round(new_r2 - g2.rating, 1)
                if p1.id == series.player1_id:
                    series.p1_rating_change = rc_match_p1
                    series.p2_rating_change = rc_match_p2
                else:
                    series.p1_rating_change = rc_match_p2
                    series.p2_rating_change = rc_match_p1

                # Apply updates
                now = datetime.now(timezone.utc)
                g1.rating = new_r1
                g1.rating_deviation = new_rd1
                g1.volatility = new_vol1
                g1.peak_rating = max(g1.peak_rating or new_r1, new_r1)
                g1.updated_at = now
                g2.rating = new_r2
                g2.rating_deviation = new_rd2
                g2.volatility = new_vol2
                g2.peak_rating = max(g2.peak_rating or new_r2, new_r2)
                g2.updated_at = now

                # Save rating history snapshots (powers the Elo-over-time graph)
                for pid, r, rd, vol in [
                    (p1.id, new_r1, new_rd1, new_vol1),
                    (p2.id, new_r2, new_rd2, new_vol2),
                ]:
                    db.add(RatingHistory(
                        player_id=pid,
                        rating=r,
                        rating_deviation=rd,
                        volatility=vol,
                        period_end=now,
                    ))

            await db.commit()
        except Exception as ex:
            print(f"Series Glicko update error: {ex}")

        # ── Auto-grant Regicide achievement ──
        # If someone beat Sid (the mod creator) in a ranked series, unlock "regicide"
        SID_STEAM_ID = "76561198040410653"
        try:
            winner_steam = (await db.execute(
                select(Player.steam_id).where(Player.id == series.winner_id)
            )).scalar_one_or_none()
            loser_id = series.player2_id if series.winner_id == series.player1_id else series.player1_id
            loser_steam = (await db.execute(
                select(Player.steam_id).where(Player.id == loser_id)
            )).scalar_one_or_none()
            if loser_steam == SID_STEAM_ID and winner_steam and winner_steam != SID_STEAM_ID:
                # Winner beat Sid — check if they already have it
                existing = (await db.execute(
                    select(PlayerAchievement).where(
                        PlayerAchievement.player_id == series.winner_id,
                        PlayerAchievement.achievement_key == "regicide",
                    )
                )).scalar_one_or_none()
                if not existing:
                    ach = PlayerAchievement(
                        player_id=series.winner_id,
                        achievement_key="regicide",
                    )
                    db.add(ach)
                    # Match the /achievements/unlock gold grant (25 gold).
                    winner_row = (await db.execute(select(Player).where(Player.id == series.winner_id))).scalar_one_or_none()
                    if winner_row is not None:
                        winner_row.gold_earned = (winner_row.gold_earned or 0) + 25
                        db.add(GoldTransaction(
                            player_id=series.winner_id, amount=25,
                            reason="achievement", reference_id="regicide",
                        ))
                    await db.commit()
                    print(f"[ACH] Regicide auto-granted to {winner_steam} for beating Sid in ranked series (+25 gold)")
        except Exception as ex:
            print(f"Regicide auto-grant error: {ex}")

    # Compile gold breakdown for the reporter so the notification can show
    # "+3 gold [XP]  [Series win +5]  [Sweep +1]" type details.
    reporter_is_p1 = (report.reported_by_steam_id == report.player1.steam_id)
    reporter_gold_from_xp = gold_p1 if reporter_is_p1 else gold_p2
    reporter_gold_total = reporter_gold_from_xp
    reporter_gold_bonuses = []
    if reporter_gold_from_xp > 0:
        reporter_gold_bonuses.append(f"XP +{reporter_gold_from_xp}")
    # Series-win gold only goes to the series winner; check if reporter == winner.
    if series_completed:
        reporter_player_id = p1.id if reporter_is_p1 else p2.id
        if series.winner_id == reporter_player_id:
            reporter_gold_total += 5
            reporter_gold_bonuses.append("Series win +5")
            if series.p1_series_wins == 0 or series.p2_series_wins == 0:
                reporter_gold_total += 1
                reporter_gold_bonuses.append("Sweep +1")

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
        gold_gained=reporter_gold_total,
        gold_bonuses=reporter_gold_bonuses,
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
            COALESCE(p.total_xp, 0) AS total_xp,
            COALESCE(p.gold_earned, 0) - COALESCE(p.gold_spent, 0) AS gold,
            si.name          AS title,
            si.preview_color AS title_color
        FROM glicko_ratings gr
        JOIN players p ON p.id = gr.player_id
        LEFT JOIN combined c ON c.player_id = p.id
        LEFT JOIN shop_items si ON si.id = p.active_title_id
        WHERE COALESCE(c.total, 0) >= :min_matches
          AND p.deleted_at IS NULL
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
            gold=int(row["gold"] or 0),
            title=row["title"],
            title_color=row["title_color"],
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
        WHERE COALESCE(c.total, 0) >= :min_matches
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

    # Top cards by pick count, with pass-rate from card_offers (additive — old
    # matches without offer rows just yield times_offered=0, pass_rate=0).
    cards_query = text("""
        WITH offers AS (
            SELECT card_name,
                   COUNT(*) AS times_offered,
                   ROUND(
                       (1.0 - SUM(CASE WHEN was_picked THEN 1 ELSE 0 END)::numeric
                            / NULLIF(COUNT(*), 0)),
                       4
                   ) AS pass_rate
            FROM card_offers
            WHERE player_id = :pid
            GROUP BY card_name
        )
        SELECT
            mc.card_name,
            COUNT(*) AS times_picked,
            SUM(CASE WHEN m.winner_id = :pid THEN 1 ELSE 0 END) AS wins_with,
            ROUND(
                SUM(CASE WHEN m.winner_id = :pid THEN 1 ELSE 0 END)::numeric
                / NULLIF(COUNT(*), 0), 4
            ) AS win_rate,
            COALESCE(o.times_offered, 0) AS times_offered,
            COALESCE(o.pass_rate, 0)     AS pass_rate
        FROM match_cards mc
        JOIN matches m ON m.id = mc.match_id
        LEFT JOIN offers o ON o.card_name = mc.card_name
        WHERE mc.player_id = :pid
        GROUP BY mc.card_name, o.times_offered, o.pass_rate
        ORDER BY times_picked DESC
        LIMIT 10
    """)
    cards = (await db.execute(cards_query, {"pid": player.id})).mappings().all()
    top_cards = [
        {"card_name": c["card_name"], "times_picked": c["times_picked"],
         "wins_with": c["wins_with"], "win_rate": float(c["win_rate"] or 0),
         "times_offered": c["times_offered"], "pass_rate": float(c["pass_rate"] or 0)}
        for c in cards
    ]

    player_total_xp = player.total_xp or 0
    player_level, xp_into_level, xp_needed_for_next = level_from_xp(player_total_xp)

    # Compute best win streaks
    # Ranked: count per SERIES completion, not per individual match
    ranked_streak_query = text("""
        SELECT rs.winner_id
        FROM ranked_series rs
        WHERE rs.status = 'completed'
          AND (rs.player1_id = :pid OR rs.player2_id = :pid)
        ORDER BY rs.completed_at ASC
    """)
    ranked_streak_rows = (await db.execute(ranked_streak_query, {"pid": player.id})).mappings().all()
    best_ranked_streak = 0
    cur_ranked_streak = 0
    for sr in ranked_streak_rows:
        if sr["winner_id"] == player.id:
            cur_ranked_streak += 1
            best_ranked_streak = max(best_ranked_streak, cur_ranked_streak)
        else:
            cur_ranked_streak = 0

    # Casual: count per individual match (no series)
    casual_streak_query = text("""
        SELECT m.winner_id
        FROM matches m
        WHERE (m.player1_id = :pid OR m.player2_id = :pid)
          AND m.is_ranked = false
        ORDER BY m.ended_at ASC
    """)
    casual_streak_rows = (await db.execute(casual_streak_query, {"pid": player.id})).mappings().all()
    best_casual_streak = 0
    cur_casual_streak = 0
    for sr in casual_streak_rows:
        if sr["winner_id"] == player.id:
            cur_casual_streak += 1
            best_casual_streak = max(best_casual_streak, cur_casual_streak)
        else:
            cur_casual_streak = 0

    # Active cosmetic lookups (title + trail)
    active_title_name: str | None = None
    active_title_color: str | None = None
    active_trail_sku: str | None = None
    active_trail_color: str | None = None
    active_trail_price: int = 0
    for cosmetic_id, is_title in ((player.active_title_id, True), (player.active_trail_id, False)):
        if cosmetic_id is None:
            continue
        row = (await db.execute(
            select(ShopItem.name, ShopItem.sku, ShopItem.preview_color, ShopItem.price).where(ShopItem.id == cosmetic_id)
        )).first()
        if row is None:
            continue
        if is_title:
            active_title_name, active_title_color = row[0], row[2]
        else:
            active_trail_sku, active_trail_color, active_trail_price = row[1], row[2], row[3] or 0

    # Casual W/L (individual casual matches only)
    casual_wl_query = text("""
        SELECT
            SUM(CASE WHEN m.winner_id = :pid THEN 1 ELSE 0 END) AS casual_wins,
            SUM(CASE WHEN m.winner_id IS NOT NULL AND m.winner_id != :pid THEN 1 ELSE 0 END) AS casual_losses
        FROM matches m
        WHERE (m.player1_id = :pid OR m.player2_id = :pid)
          AND m.is_ranked = false
    """)
    casual_wl = (await db.execute(casual_wl_query, {"pid": player.id})).mappings().first()
    casual_wins = casual_wl["casual_wins"] or 0 if casual_wl else 0
    casual_losses = casual_wl["casual_losses"] or 0 if casual_wl else 0

    # Sweep counts (5-0 wins given and taken)
    sweep_query = text("""
        SELECT
            SUM(CASE
                WHEN m.winner_id = :pid
                    AND CASE WHEN m.player1_id = :pid THEN m.p2_rounds_won ELSE m.p1_rounds_won END = 0
                THEN 1 ELSE 0 END) AS sweeps_given,
            SUM(CASE
                WHEN m.winner_id IS NOT NULL AND m.winner_id != :pid
                    AND CASE WHEN m.player1_id = :pid THEN m.p1_rounds_won ELSE m.p2_rounds_won END = 0
                THEN 1 ELSE 0 END) AS sweeps_taken
        FROM matches m
        WHERE m.player1_id = :pid OR m.player2_id = :pid
    """)
    sweep_data = (await db.execute(sweep_query, {"pid": player.id})).mappings().first()
    sweeps_given = sweep_data["sweeps_given"] or 0 if sweep_data else 0
    sweeps_taken = sweep_data["sweeps_taken"] or 0 if sweep_data else 0

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

    # Recent form (last 20 completed ranked SERIES, newest first — aligns with Elo changes)
    form_query = text("""
        SELECT
            CASE WHEN rs.winner_id = :pid THEN 'W' ELSE 'L' END AS result,
            CASE
                WHEN rs.player1_id = :pid THEN p2.display_name
                ELSE p1.display_name
            END AS opponent_name,
            CASE
                WHEN rs.player1_id = :pid THEN rs.p1_series_wins || '-' || rs.p2_series_wins
                ELSE rs.p2_series_wins || '-' || rs.p1_series_wins
            END AS score,
            rs.completed_at AS ended_at
        FROM ranked_series rs
        JOIN players p1 ON p1.id = rs.player1_id
        JOIN players p2 ON p2.id = rs.player2_id
        WHERE rs.status = 'completed'
          AND (rs.player1_id = :pid OR rs.player2_id = :pid)
        ORDER BY rs.completed_at DESC
        LIMIT 20
    """)
    form_rows = (await db.execute(form_query, {"pid": player.id})).mappings().all()
    recent_form = [
        {"result": r["result"], "ranked": True,
         "opponent": r["opponent_name"],
         "score": r["score"],
         "date": r["ended_at"].isoformat() if r["ended_at"] else ""}
        for r in form_rows
    ]

    return PlayerStatsResponse(
        steam_id=player.steam_id,
        display_name=player.display_name,
        rating=round(glicko.rating, 1) if glicko else GLICKO2_DEFAULT_RATING,
        rating_deviation=round(glicko.rating_deviation, 1) if glicko else GLICKO2_DEFAULT_RD,
        volatility=round(glicko.volatility, 4) if glicko else GLICKO2_DEFAULT_VOLATILITY,
        peak_rating=round(glicko.peak_rating, 1) if glicko and glicko.peak_rating else GLICKO2_DEFAULT_RATING,
        total_matches=total,
        wins=wins,
        losses=losses,
        win_rate=round(wins / total, 4) if total > 0 else 0.0,
        ranked_enabled=player.ranked_enabled,
        discord_id=player.discord_id,
        discord_username=player.discord_username,
        gold_earned=player.gold_earned or 0,
        gold_spent=player.gold_spent or 0,
        active_title=active_title_name,
        active_title_color=active_title_color,
        active_trail_sku=active_trail_sku,
        active_trail_color=active_trail_color,
        active_trail_price=active_trail_price,
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
        casual_wins=casual_wins,
        casual_losses=casual_losses,
        sweeps_given=sweeps_given,
        sweeps_taken=sweeps_taken,
        ranked_dc_count=player.ranked_dc_count or 0,
        recent_form=recent_form,
    )


# ── Routes: Match History ──────────────────────────────────────

@app.get("/api/v1/players/{steam_id}/matches", response_model=list[MatchHistoryEntry], tags=["Players"])
async def get_player_matches(
    steam_id: str,
    limit: int = Query(100, ge=1, le=2000),
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
            CASE WHEN m.player1_id = :pid THEN m.p1_points_total ELSE m.p2_points_total END AS player_points,
            CASE WHEN m.player1_id = :pid THEN m.p2_points_total ELSE m.p1_points_total END AS opp_points,
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
                 ELSE m.p2_xp_gained END AS xp_gained,
            -- Gold earned ON this match (xp crossings), and series bonus if applicable.
            COALESCE((
                SELECT SUM(gt.amount) FROM gold_transactions gt
                WHERE gt.player_id = :pid AND gt.reason = 'xp' AND gt.reference_id = m.id::text
            ), 0) AS gold_gained,
            COALESCE((
                SELECT SUM(gt.amount) FROM gold_transactions gt
                WHERE gt.player_id = :pid AND gt.reason = 'series_win' AND gt.reference_id = m.series_id::text
                  AND m.series_id IS NOT NULL
            ), 0) AS series_gold_gained
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
            player_points=row["player_points"] or 0,
            opponent_points=row["opp_points"] or 0,
            won=(row["winner_id"] == player.id),
            ended_at=row["ended_at"],
            is_ranked=row["is_ranked"] if "is_ranked" in row.keys() else False,
            cards_picked=cards,
            opponent_cards_picked=opp_cards,
            series_id=series_id_str,
            series_score=series_score_str,
            series_rating_change=series_rc,
            xp_gained=row["xp_gained"] or 0,
            gold_gained=row["gold_gained"] or 0,
            series_gold_gained=row["series_gold_gained"] or 0,
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

    # Pass-rate aggregation. Filtered to the same player when requested so the
    # number reflects "how often THIS player passes on this card." Without a
    # player filter we pool across everyone — community-wide pass rate.
    offer_player_filter = ""
    if steam_id:
        offer_player_filter = "WHERE player_id = (SELECT id FROM players WHERE steam_id = :steam_id)"

    query = text(f"""
        WITH offers AS (
            SELECT card_name,
                   COUNT(*) AS times_offered,
                   ROUND(
                       (1.0 - SUM(CASE WHEN was_picked THEN 1 ELSE 0 END)::numeric
                            / NULLIF(COUNT(*), 0)),
                       4
                   ) AS pass_rate
            FROM card_offers
            {offer_player_filter}
            GROUP BY card_name
        )
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
            ) AS win_rate,
            COALESCE(o.times_offered, 0) AS times_offered,
            COALESCE(o.pass_rate, 0)     AS pass_rate
        FROM match_cards mc
        JOIN matches m ON m.id = mc.match_id
        LEFT JOIN offers o ON o.card_name = mc.card_name
        WHERE 1=1 {player_filter} {ranked_filter}
        GROUP BY mc.card_name, mc.card_rarity, o.times_offered, o.pass_rate
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
            times_offered=r["times_offered"],
            pass_rate=float(r["pass_rate"] or 0),
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

    # Get all live players with ratings. Tombstoned (anonymized) players keep
    # their Glicko row for FK integrity but are skipped by the recalc.
    result = await db.execute(
        select(GlickoRating)
        .join(Player, Player.id == GlickoRating.player_id)
        .where(Player.deleted_at.is_(None))
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
        glicko.peak_rating = max(glicko.peak_rating or new_rating, new_rating)
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
    """Toggle a player's ranked mode on or off. Auto-registers if needed."""
    result = await db.execute(select(Player).where(Player.steam_id == steam_id))
    player = result.scalar_one_or_none()

    if not player:
        # Auto-register on first toggle (startup sync)
        player = await get_or_create_player(db, steam_id, steam_id)

    player.ranked_enabled = enabled
    await db.commit()

    return {"steam_id": steam_id, "ranked_enabled": enabled}


# ── Routes: Ranked Queue ──────────────────────────────────────

QUEUE_EXPIRE_MINUTES = 30
QUEUE_BLOCK_MINUTES = 5
READY_TIMEOUT_SECONDS = 30


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
    # Get or create the player (auto-register on first queue join)
    name = req.display_name or req.steam_id
    player = await get_or_create_player(db, req.steam_id, name)

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
        room_region=None,
        ready=False,
        joined_at=datetime.now(timezone.utc),
        matched_at=None,
        last_polled=datetime.now(timezone.utc),
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
            "room_region": None,
            "ready": False,
            "joined_at": datetime.now(timezone.utc),
            "matched_at": None,
            "last_polled": datetime.now(timezone.utc),
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


@app.get("/api/v1/queue/count", tags=["Queue"])
async def queue_count(db: AsyncSession = Depends(get_db)):
    """Lightweight endpoint: returns number of players searching in the ranked queue."""
    result = await db.execute(
        text("SELECT COUNT(*) FROM ranked_queue WHERE status = 'searching'")
    )
    searching = result.scalar() or 0
    result2 = await db.execute(
        text("SELECT COUNT(*) FROM ranked_queue")
    )
    total = result2.scalar() or 0
    return {"searching": searching, "total": total}


@app.get("/api/v1/queue/recent-joins", tags=["Queue"])
async def queue_recent_joins(seconds: int = Query(20), db: AsyncSession = Depends(get_db)):
    """Return players who joined the queue within the last N seconds."""
    result = await db.execute(
        text("""
            SELECT rq.display_name, rq.steam_id, rq.rating, rq.joined_at
            FROM ranked_queue rq
            WHERE rq.status = 'searching'
              AND rq.joined_at > NOW() - INTERVAL '1 second' * :secs
            ORDER BY rq.joined_at DESC
        """), {"secs": seconds}
    )
    rows = result.mappings().all()
    return {"joins": [
        {"display_name": r["display_name"], "steam_id": r["steam_id"],
         "rating": round(r["rating"]), "joined_at": r["joined_at"].isoformat()}
        for r in rows
    ]}


@app.get("/api/v1/queue/poll/{steam_id}", response_model=QueuePollResponse, tags=["Queue"])
async def queue_poll(steam_id: str, db: AsyncSession = Depends(get_db)):
    """
    Poll queue status. Handles searching, matching, mutual ready-up, and timeouts.
    Uses SELECT FOR UPDATE SKIP LOCKED for race-safe matching.
    Elo range: ±100 / ±200@30s / ±400@60s / ±800@120s.
    Ready timeout: 30s — if both players don't ready up, match is canceled.
    """
    import uuid as uuid_mod

    # Clean up expired blocks opportunistically
    await db.execute(text("DELETE FROM queue_blocks WHERE expires_at < now()"))

    # Find our queue entry (lock it)
    result = await db.execute(
        text("""
            SELECT rq.player_id, rq.steam_id, rq.display_name, rq.rating,
                   rq.rating_deviation, rq.status, rq.matched_with,
                   rq.room_name, rq.room_region, rq.region, rq.ready,
                   rq.joined_at, rq.matched_at
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
    my_pid = entry["player_id"]

    # Heartbeat — update last_polled so cleanup knows we're alive
    await db.execute(
        text("UPDATE ranked_queue SET last_polled = NOW() WHERE player_id = :pid"),
        {"pid": my_pid},
    )

    # Check for expiry (only applies to searching state)
    if entry["status"] == "searching" and wait_seconds > QUEUE_EXPIRE_MINUTES * 60:
        await db.execute(
            text("DELETE FROM ranked_queue WHERE player_id = :pid"),
            {"pid": my_pid},
        )
        await db.commit()
        return QueuePollResponse(status="expired", wait_time=wait_seconds)

    # ── MATCHED state: handle ready-up and room joining ──
    if entry["status"] == "matched" and entry["matched_with"]:
        # Get opponent info (lock their row too for atomic updates)
        opp_result = await db.execute(
            text("""
                SELECT player_id, steam_id, display_name, rating, ready, room_name, region
                FROM ranked_queue WHERE player_id = :oid
                FOR UPDATE
            """),
            {"oid": entry["matched_with"]},
        )
        opp = opp_result.mappings().first()

        if not opp:
            # Opponent left queue entirely — go back to searching
            await db.execute(
                text("""
                    UPDATE ranked_queue
                    SET status = 'searching', matched_with = NULL,
                        room_name = NULL, room_region = NULL, ready = false, matched_at = NULL
                    WHERE player_id = :pid
                """),
                {"pid": my_pid},
            )
            await db.commit()
            return QueuePollResponse(status="searching", wait_time=wait_seconds)

        my_ready = entry["ready"]
        opp_ready = opp["ready"]
        room_name = entry["room_name"]

        # Check ready timeout
        if entry["matched_at"]:
            match_age = int((now - entry["matched_at"]).total_seconds())
            if match_age > READY_TIMEOUT_SECONDS and not (my_ready and opp_ready):
                # Timeout — cancel match, both back to searching
                for pid in [my_pid, opp["player_id"]]:
                    await db.execute(
                        text("""
                            UPDATE ranked_queue
                            SET status = 'searching', matched_with = NULL,
                                room_name = NULL, room_region = NULL, ready = false, matched_at = NULL
                            WHERE player_id = :pid
                        """),
                        {"pid": pid},
                    )
                await db.commit()
                return QueuePollResponse(status="searching", wait_time=wait_seconds)

        # Both ready — generate room if not already done
        if my_ready and opp_ready:
            if not room_name:
                room_name = f"ranked_{uuid_mod.uuid4().hex[:12]}"
                # Pick region: use our region (first poller), fallback to opponent's, fallback to "us"
                chosen_region = entry["region"] or opp["region"] or "us"
                for pid in [my_pid, opp["player_id"]]:
                    await db.execute(
                        text("UPDATE ranked_queue SET room_name = :room, room_region = :region WHERE player_id = :pid"),
                        {"room": room_name, "region": chosen_region, "pid": pid},
                    )
            await db.commit()
            return QueuePollResponse(
                status="ready_join",
                wait_time=wait_seconds,
                opponent_steam_id=opp["steam_id"],
                opponent_name=opp["display_name"],
                opponent_rating=opp["rating"],
                opponent_ready=True,
                room_name=room_name,
                photon_region=entry["room_region"] or entry["region"] or "us",
            )

        # Room already set (by /ready endpoint) but we see it on poll
        if room_name:
            await db.commit()
            return QueuePollResponse(
                status="ready_join",
                wait_time=wait_seconds,
                opponent_steam_id=opp["steam_id"],
                opponent_name=opp["display_name"],
                opponent_rating=opp["rating"],
                opponent_ready=opp_ready,
                room_name=room_name,
                photon_region=entry["room_region"] or entry["region"] or "us",
            )

        # Waiting for ready-up
        await db.commit()
        return QueuePollResponse(
            status="matched",
            wait_time=wait_seconds,
            opponent_steam_id=opp["steam_id"],
            opponent_name=opp["display_name"],
            opponent_rating=opp["rating"],
            opponent_ready=opp_ready,
        )

    # ── SEARCHING state: try to find a match ──
    elo_range = compute_elo_range(wait_seconds)
    my_rating = entry["rating"]
    min_rating = my_rating - elo_range
    max_rating = my_rating + elo_range

    # Find best candidate (SKIP LOCKED prevents race conditions)
    # Bilateral range check: OUR range must include them AND THEIR range must include us
    candidate = await db.execute(
        text("""
            SELECT player_id, steam_id, display_name, rating
            FROM ranked_queue
            WHERE status = 'searching'
              AND player_id != :pid
              AND rating BETWEEN :rmin AND :rmax
              AND :my_rating BETWEEN
                  rating - (CASE
                      WHEN EXTRACT(EPOCH FROM (now() - joined_at)) >= 120 THEN 800
                      WHEN EXTRACT(EPOCH FROM (now() - joined_at)) >= 60 THEN 400
                      WHEN EXTRACT(EPOCH FROM (now() - joined_at)) >= 30 THEN 200
                      ELSE 100
                  END)
                  AND
                  rating + (CASE
                      WHEN EXTRACT(EPOCH FROM (now() - joined_at)) >= 120 THEN 800
                      WHEN EXTRACT(EPOCH FROM (now() - joined_at)) >= 60 THEN 400
                      WHEN EXTRACT(EPOCH FROM (now() - joined_at)) >= 30 THEN 200
                      ELSE 100
                  END)
              AND player_id NOT IN (
                  SELECT blocked_id FROM queue_blocks
                  WHERE blocker_id = :pid AND expires_at > now()
              )
              AND player_id NOT IN (
                  SELECT blocker_id FROM queue_blocks
                  WHERE blocked_id = :pid AND expires_at > now()
              )
              AND player_id NOT IN (
                  SELECT blocked_id FROM player_blocks WHERE blocker_id = :pid
              )
              AND player_id NOT IN (
                  SELECT blocker_id FROM player_blocks WHERE blocked_id = :pid
              )
            ORDER BY ABS(rating - :my_rating)
            LIMIT 1
            FOR UPDATE SKIP LOCKED
        """),
        {"pid": my_pid, "rmin": min_rating, "rmax": max_rating, "my_rating": my_rating},
    )
    opp = candidate.mappings().first()

    if opp:
        # Match found — set both to matched, NO room yet (wait for both to ready up)
        matched_at = datetime.now(timezone.utc)
        for pid, opp_id in [(my_pid, opp["player_id"]), (opp["player_id"], my_pid)]:
            await db.execute(
                text("""
                    UPDATE ranked_queue
                    SET status = 'matched', matched_with = :opp_id,
                        room_name = NULL, room_region = NULL, ready = false, matched_at = :mat
                    WHERE player_id = :pid
                """),
                {"opp_id": opp_id, "mat": matched_at, "pid": pid},
            )
        await db.commit()

        return QueuePollResponse(
            status="matched",
            wait_time=wait_seconds,
            opponent_steam_id=opp["steam_id"],
            opponent_name=opp["display_name"],
            opponent_rating=opp["rating"],
            opponent_ready=False,
        )

    # No match yet
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


@app.post("/api/v1/queue/ready", tags=["Queue"])
async def queue_ready(steam_id: str = Query(...), db: AsyncSession = Depends(get_db)):
    """
    Mark player as ready for their matched game.
    If opponent is also ready, generates a room immediately.
    """
    import uuid as uuid_mod

    result = await db.execute(select(Player).where(Player.steam_id == steam_id))
    player = result.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Lock our queue entry
    entry_result = await db.execute(
        text("""
            SELECT player_id, status, matched_with, room_name, room_region, region, ready
            FROM ranked_queue WHERE player_id = :pid
            FOR UPDATE
        """),
        {"pid": player.id},
    )
    entry = entry_result.mappings().first()

    if not entry or entry["status"] != "matched":
        await db.commit()
        return {"status": "not_matched", "message": "Not currently in a matched state"}

    # Set ourselves as ready
    await db.execute(
        text("UPDATE ranked_queue SET ready = true WHERE player_id = :pid"),
        {"pid": player.id},
    )

    # Check if opponent is also ready
    opp_result = await db.execute(
        text("""
            SELECT player_id, ready, room_name, region
            FROM ranked_queue WHERE player_id = :oid
            FOR UPDATE
        """),
        {"oid": entry["matched_with"]},
    )
    opp = opp_result.mappings().first()

    if opp and opp["ready"]:
        # Both ready — generate room if not already done
        room_name = entry["room_name"] or opp["room_name"]
        if not room_name:
            room_name = f"ranked_{uuid_mod.uuid4().hex[:12]}"
            chosen_region = entry["region"] or (opp["region"] if opp else None) or "us"
            for pid in [player.id, opp["player_id"]]:
                await db.execute(
                    text("UPDATE ranked_queue SET room_name = :room, room_region = :region WHERE player_id = :pid"),
                    {"room": room_name, "region": chosen_region, "pid": pid},
                )
        else:
            chosen_region = entry["room_region"] or entry["region"] or "us"
        await db.commit()
        return {"status": "both_ready", "room_name": room_name, "photon_region": chosen_region}

    await db.commit()
    return {"status": "waiting", "message": "Waiting for opponent to ready up"}


@app.post("/api/v1/queue/decline", tags=["Queue"])
async def queue_decline(req: QueueDeclineRequest, db: AsyncSession = Depends(get_db)):
    """
    Decline a matched opponent. Blocks re-matching for 5 minutes.
    Both players are reset to searching (stay in queue).
    """
    p1_result = await db.execute(select(Player).where(Player.steam_id == req.steam_id))
    p1 = p1_result.scalar_one_or_none()
    p2_result = await db.execute(select(Player).where(Player.steam_id == req.opponent_steam_id))
    p2 = p2_result.scalar_one_or_none()

    if not p1 or not p2:
        raise HTTPException(status_code=404, detail="Player not found")

    expires = datetime.now(timezone.utc) + timedelta(minutes=QUEUE_BLOCK_MINUTES)

    # Insert bidirectional blocks
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

    # Reset BOTH players back to searching (stay in queue, find other opponents)
    for pid in [p1.id, p2.id]:
        await db.execute(
            text("""
                UPDATE ranked_queue
                SET status = 'searching', matched_with = NULL,
                    room_name = NULL, room_region = NULL, ready = false, matched_at = NULL
                WHERE player_id = :pid
            """),
            {"pid": pid},
        )

    await db.commit()
    return {"status": "declined", "message": f"Declined match. Blocked for {QUEUE_BLOCK_MINUTES} minutes."}


# ── Player Blocks (permanent, from leaderboard) ─────────────

@app.post("/api/v1/players/block", tags=["Players"])
async def block_player(
    steam_id: str = Query(...),
    target_steam_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Permanently block a player from ranked matchmaking against you."""
    p1 = (await db.execute(select(Player).where(Player.steam_id == steam_id))).scalar_one_or_none()
    p2 = (await db.execute(select(Player).where(Player.steam_id == target_steam_id))).scalar_one_or_none()
    if not p1 or not p2:
        raise HTTPException(status_code=404, detail="Player not found")
    await db.execute(
        text("""
            INSERT INTO player_blocks (blocker_id, blocked_id)
            VALUES (:b, :bl)
            ON CONFLICT DO NOTHING
        """),
        {"b": p1.id, "bl": p2.id},
    )
    await db.commit()
    return {"status": "blocked", "message": f"Blocked {target_steam_id} from ranked matchmaking"}


@app.post("/api/v1/players/unblock", tags=["Players"])
async def unblock_player(
    steam_id: str = Query(...),
    target_steam_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Remove a permanent ranked matchmaking block."""
    p1 = (await db.execute(select(Player).where(Player.steam_id == steam_id))).scalar_one_or_none()
    p2 = (await db.execute(select(Player).where(Player.steam_id == target_steam_id))).scalar_one_or_none()
    if not p1 or not p2:
        raise HTTPException(status_code=404, detail="Player not found")
    await db.execute(
        text("DELETE FROM player_blocks WHERE blocker_id = :b AND blocked_id = :bl"),
        {"b": p1.id, "bl": p2.id},
    )
    await db.commit()
    return {"status": "unblocked", "message": f"Unblocked {target_steam_id}"}


@app.get("/api/v1/players/blocks/{steam_id}", tags=["Players"])
async def get_player_blocks(steam_id: str, db: AsyncSession = Depends(get_db)):
    """Get list of steam IDs this player has blocked from ranked matchmaking."""
    p = (await db.execute(select(Player).where(Player.steam_id == steam_id))).scalar_one_or_none()
    if not p:
        return {"blocked_steam_ids": []}
    result = await db.execute(
        text("""
            SELECT p.steam_id FROM player_blocks pb
            JOIN players p ON pb.blocked_id = p.id
            WHERE pb.blocker_id = :pid
        """),
        {"pid": p.id},
    )
    return {"blocked_steam_ids": [r[0] for r in result.fetchall()]}


# ── Routes: Disconnect Reporting ─────────────────────────────────

@app.post("/api/v1/report-disconnect", tags=["Players"])
async def report_disconnect(
    reporter_steam_id: str = Query(...),
    disconnected_steam_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Report that a player disconnected during a ranked match.
    Called by the remaining player's client when the opponent leaves mid-match.
    Only counts if the match was ranked and enough gameplay occurred.
    The client enforces eligibility (ranked, >=2 total points, neither has >=4 rounds).
    """
    # Validate both players exist
    reporter = (await db.execute(select(Player).where(Player.steam_id == reporter_steam_id))).scalar_one_or_none()
    disconnected = (await db.execute(select(Player).where(Player.steam_id == disconnected_steam_id))).scalar_one_or_none()

    if not reporter or not disconnected:
        raise HTTPException(status_code=404, detail="Player not found")

    if reporter.id == disconnected.id:
        raise HTTPException(status_code=400, detail="Cannot report yourself")

    # Increment the disconnected player's DC count
    disconnected.ranked_dc_count = (disconnected.ranked_dc_count or 0) + 1
    await db.commit()

    print(f"[DC] {reporter_steam_id} reported disconnect by {disconnected_steam_id} (total: {disconnected.ranked_dc_count})")
    return {
        "status": "recorded",
        "disconnected_steam_id": disconnected_steam_id,
        "ranked_dc_count": disconnected.ranked_dc_count,
    }


# ── Routes: Discord Linking ──────────────────────────────────────

@app.post("/api/v1/players/link-code", tags=["Discord"])
async def generate_link_code(steam_id: str = Query(...), db: AsyncSession = Depends(get_db)):
    """
    Generate a 6-character verification code for Discord linking.
    Code expires after 10 minutes.
    """
    result = await db.execute(select(Player).where(Player.steam_id == steam_id))
    player = result.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Delete any existing codes for this player
    await db.execute(text("DELETE FROM link_codes WHERE player_id = :pid"), {"pid": player.id})

    # Generate a 6-char uppercase alphanumeric code
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    expires = datetime.now(timezone.utc) + timedelta(minutes=10)

    db.add(LinkCode(player_id=player.id, code=code, expires_at=expires))
    await db.commit()

    return {"code": code, "expires_in": 600}


@app.post("/api/v1/players/link-discord", tags=["Discord"])
async def link_discord(
    code: str = Query(...),
    discord_id: str = Query(...),
    discord_username: str | None = Query(None, max_length=64),
    db: AsyncSession = Depends(get_db),
):
    """
    Link a Discord account to a Steam account via verification code.
    Called by the Discord bot after !link CODE.
    """
    # Clean up expired codes
    await db.execute(text("DELETE FROM link_codes WHERE expires_at < now()"))

    # Find the code
    result = await db.execute(
        select(LinkCode).where(LinkCode.code == code.upper())
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Invalid or expired code")

    # Check if discord_id is already linked to another player
    existing = await db.execute(
        select(Player).where(Player.discord_id == discord_id)
    )
    existing_player = existing.scalar_one_or_none()
    if existing_player and existing_player.id != link.player_id:
        # Unlink old player
        existing_player.discord_id = None

    # Link the discord account
    player_result = await db.execute(select(Player).where(Player.id == link.player_id))
    player = player_result.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    player.discord_id = discord_id
    if discord_username:
        player.discord_username = discord_username

    # Delete the used code
    await db.execute(text("DELETE FROM link_codes WHERE player_id = :pid"), {"pid": player.id})
    await db.commit()

    return {
        "status": "linked",
        "steam_id": player.steam_id,
        "display_name": player.display_name,
        "discord_id": discord_id,
        "discord_username": player.discord_username,
    }


@app.get("/api/v1/admin/missing-discord-usernames", tags=["Discord"])
async def missing_discord_usernames(
    x_internal_key: str | None = Header(None, alias="X-Internal-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Internal — used by the bot's startup backfill. Returns Discord IDs that
    are linked but haven't cached a username yet."""
    expected = os.getenv("API_SECRET_KEY", "")
    if not expected or x_internal_key != expected:
        raise HTTPException(status_code=403, detail="Invalid internal key")
    rows = (await db.execute(text(
        "SELECT discord_id FROM players "
        "WHERE discord_id IS NOT NULL AND discord_username IS NULL AND deleted_at IS NULL "
        "LIMIT 500"
    ))).mappings().all()
    return {"discord_ids": [r["discord_id"] for r in rows]}


@app.post("/api/v1/admin/set-discord-username", tags=["Discord"])
async def set_discord_username(
    payload: dict,
    x_internal_key: str | None = Header(None, alias="X-Internal-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Internal — bot writes resolved Discord usernames here."""
    expected = os.getenv("API_SECRET_KEY", "")
    if not expected or x_internal_key != expected:
        raise HTTPException(status_code=403, detail="Invalid internal key")
    discord_id = str(payload.get("discord_id", "")).strip()
    username = str(payload.get("discord_username", "")).strip()[:64]
    if not discord_id or not username:
        return {"status": "skipped"}
    await db.execute(
        text("UPDATE players SET discord_username = :u WHERE discord_id = :did AND discord_username IS NULL"),
        {"u": username, "did": discord_id},
    )
    await db.commit()
    return {"status": "ok"}


@app.get("/api/v1/players/by-discord/{discord_id}", tags=["Discord"])
async def get_player_by_discord(discord_id: str, db: AsyncSession = Depends(get_db)):
    """Look up a player by their linked Discord ID."""
    result = await db.execute(select(Player).where(Player.discord_id == discord_id))
    player = result.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="No player linked to this Discord account")

    rating_result = await db.execute(
        select(GlickoRating).where(GlickoRating.player_id == player.id)
    )
    glicko = rating_result.scalar_one_or_none()

    return {
        "steam_id": player.steam_id,
        "display_name": player.display_name,
        "discord_id": discord_id,
        "rating": round(glicko.rating, 1) if glicko else GLICKO2_DEFAULT_RATING,
        "peak_rating": round(glicko.peak_rating, 1) if glicko and glicko.peak_rating else GLICKO2_DEFAULT_RATING,
        "level": level_from_xp(player.total_xp or 0)[0],
    }


@app.get("/api/v1/series/recent", tags=["Discord"])
async def get_recent_series(
    minutes: int = Query(2, ge=1, le=43200),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """
    Get recently completed ranked series.
    Used by Discord bot (small minutes) and in-game leaderboard (large minutes + limit).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    query = text("""
        SELECT
            rs.id::text AS series_id,
            rs.status,
            rs.p1_series_wins,
            rs.p2_series_wins,
            rs.p1_rating_change,
            rs.p2_rating_change,
            rs.completed_at,
            p1.steam_id AS p1_steam_id,
            p1.display_name AS p1_name,
            p1.discord_id AS p1_discord_id,
            p2.steam_id AS p2_steam_id,
            p2.display_name AS p2_name,
            p2.discord_id AS p2_discord_id,
            g1.rating AS p1_rating,
            g1.peak_rating AS p1_peak,
            g2.rating AS p2_rating,
            g2.peak_rating AS p2_peak,
            pw.steam_id AS winner_steam_id,
            pw.display_name AS winner_name
        FROM ranked_series rs
        JOIN players p1 ON p1.id = rs.player1_id
        JOIN players p2 ON p2.id = rs.player2_id
        LEFT JOIN glicko_ratings g1 ON g1.player_id = rs.player1_id
        LEFT JOIN glicko_ratings g2 ON g2.player_id = rs.player2_id
        LEFT JOIN players pw ON pw.id = rs.winner_id
        WHERE rs.status = 'completed'
          AND rs.completed_at >= :cutoff
        ORDER BY rs.completed_at DESC
        LIMIT :limit
    """)
    rows = (await db.execute(query, {"cutoff": cutoff, "limit": limit})).mappings().all()

    # Compute streaks for each player
    async def get_ranked_streak(steam_id):
        """Get current ranked win/loss streak."""
        p = (await db.execute(select(Player).where(Player.steam_id == steam_id))).scalar_one_or_none()
        if not p:
            return 0
        streak_q = text("""
            SELECT rs.winner_id
            FROM ranked_series rs
            WHERE rs.status = 'completed'
              AND (rs.player1_id = :pid OR rs.player2_id = :pid)
            ORDER BY rs.completed_at DESC
            LIMIT 20
        """)
        streak_rows = (await db.execute(streak_q, {"pid": p.id})).mappings().all()
        if not streak_rows:
            return 0
        first_won = (streak_rows[0]["winner_id"] == p.id)
        count = 0
        for sr in streak_rows:
            if (sr["winner_id"] == p.id) == first_won:
                count += 1
            else:
                break
        return count if first_won else -count

    series_list = []
    for row in rows:
        p1_streak = await get_ranked_streak(row["p1_steam_id"])
        p2_streak = await get_ranked_streak(row["p2_steam_id"])

        series_list.append({
            "series_id": row["series_id"],
            "p1_name": row["p1_name"],
            "p1_steam_id": row["p1_steam_id"],
            "p1_discord_id": row["p1_discord_id"],
            "p1_rating": round(row["p1_rating"] or 1500, 1),
            "p1_rating_change": row["p1_rating_change"] or 0,
            "p1_streak": p1_streak,
            "p2_name": row["p2_name"],
            "p2_steam_id": row["p2_steam_id"],
            "p2_discord_id": row["p2_discord_id"],
            "p2_rating": round(row["p2_rating"] or 1500, 1),
            "p2_rating_change": row["p2_rating_change"] or 0,
            "p2_streak": p2_streak,
            "p1_series_wins": row["p1_series_wins"],
            "p2_series_wins": row["p2_series_wins"],
            "winner_name": row["winner_name"],
            "winner_steam_id": row["winner_steam_id"],
            "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
        })

    return {"series": series_list}


# ── Chat bridge (in-game ↔ Discord) ──────────────────────────
# Minimal groundwork: in-memory fanout. Mods connect via WebSocket;
# Discord bot POSTs Discord messages to /chat/post which broadcasts
# to every WS client. Bot also holds one WS connection so in-game
# messages reach the Discord channel.
#
# TODO (hardening, not in scope yet): per-connection rate limiting,
# HMAC on the send path, chat_messages persistence for scrollback.

class _ChatManager:
    def __init__(self):
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.add(ws)

    def disconnect(self, ws: WebSocket):
        self._connections.discard(ws)

    async def broadcast(self, message: dict, exclude: WebSocket | None = None):
        payload = _json.dumps(message)
        dead = []
        for ws in list(self._connections):
            if ws is exclude:
                continue
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)

    @property
    def count(self) -> int:
        return len(self._connections)


chat_manager = _ChatManager()


async def _persist_chat(db_session_factory, entry: dict):
    """Insert one chat row. Swallows failures — chat durability is nice-to-have, never critical path."""
    from database import async_session
    try:
        async with async_session() as db:
            await db.execute(
                text(
                    "INSERT INTO chat_messages (source, steam_id, discord_id, display_name, message) "
                    "VALUES (:source, :steam_id, :discord_id, :display_name, :message)"
                ),
                {
                    "source": entry.get("source", "ingame"),
                    "steam_id": entry.get("steam_id"),
                    "discord_id": entry.get("discord_id"),
                    "display_name": entry.get("display_name", "")[:64],
                    "message": entry.get("message", "")[:500],
                },
            )
            await db.commit()
    except Exception as e:
        print(f"[CHAT] persist failed: {e}")


async def _lookup_chat_meta(*, steam_id: str | None = None, discord_id: str | None = None) -> dict:
    """Look up Glicko rating + active title (for the 'Name [Title] (rating)' render).
    Returns {'rating': int|None, 'title': str|None, 'title_color': str|None}."""
    from database import async_session
    try:
        async with async_session() as db:
            col = None
            val = None
            if steam_id:
                col, val = "steam_id", steam_id
            elif discord_id:
                col, val = "discord_id", discord_id
            else:
                return {"rating": None, "title": None, "title_color": None}
            r = await db.execute(text(
                f"SELECT gr.rating, si.name AS title, si.preview_color AS title_color "
                f"FROM glicko_ratings gr "
                f"JOIN players p ON p.id = gr.player_id "
                f"LEFT JOIN shop_items si ON si.id = p.active_title_id "
                f"WHERE p.{col} = :v AND p.deleted_at IS NULL"
            ), {"v": val})
            row = r.mappings().first()
            if row is None:
                return {"rating": None, "title": None, "title_color": None}
            return {
                "rating": int(round(row["rating"])) if row["rating"] is not None else None,
                "title": row["title"],
                "title_color": row["title_color"],
            }
    except Exception as e:
        print(f"[CHAT] meta lookup failed: {e}")
        return {"rating": None, "title": None, "title_color": None}


@app.websocket("/api/v1/ws/chat")
async def ws_chat(ws: WebSocket):
    """Mod <-> server chat channel. Messages are broadcast fan-out style."""
    sent = ws.headers.get("x-mod-version")
    if sent and _parse_version(sent) < _parse_version(MIN_MOD_VERSION):
        await ws.close(code=1008, reason="outdated")
        return
    await chat_manager.connect(ws)
    print(f"[CHAT] subscriber connected (total={chat_manager.count})")
    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = _json.loads(raw)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            # App-level keepalive — silently ignore, don't broadcast.
            if data.get("type") == "ping":
                continue
            message = str(data.get("message", ""))[:500].strip()
            steam_id = str(data.get("steam_id", ""))[:20]
            display_name = str(data.get("display_name", ""))[:64]
            if not message or not steam_id:
                continue
            meta = await _lookup_chat_meta(steam_id=steam_id)
            out = {
                "source": "ingame",
                "steam_id": steam_id,
                "display_name": display_name,
                "rating": meta["rating"],
                "title": meta["title"],
                "title_color": meta["title_color"],
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            print(f"[CHAT] <- ingame {display_name}({meta['rating']}): {message[:80]}")
            # Exclude the sender so they don't double-render (local echo on the client covers it).
            await chat_manager.broadcast(out, exclude=ws)
            await _persist_chat(None, out)
    except WebSocketDisconnect:
        print(f"[CHAT] subscriber disconnected")
        chat_manager.disconnect(ws)
    except Exception as e:
        print(f"[CHAT] WS error: {e}")
        chat_manager.disconnect(ws)


@app.post("/api/v1/chat/post", tags=["Chat"])
async def post_chat_from_discord(
    payload: dict,
    x_internal_key: str | None = Header(None, alias="X-Internal-Key"),
):
    """Bot -> server relay. Auth: same API_SECRET_KEY used for the Glicko admin route."""
    expected = os.getenv("API_SECRET_KEY", "")
    if not expected or x_internal_key != expected:
        raise HTTPException(status_code=403, detail="Invalid internal key")
    message = str(payload.get("message", ""))[:500].strip()
    if not message:
        return {"status": "empty"}
    discord_id = str(payload.get("discord_id", ""))[:20] or None
    meta = await _lookup_chat_meta(discord_id=discord_id) if discord_id else {"rating": None, "title": None, "title_color": None}
    out = {
        "source": "discord",
        "discord_id": discord_id,
        "display_name": str(payload.get("display_name", "Discord"))[:64],
        "rating": meta["rating"],
        "title": meta["title"],
        "title_color": meta["title_color"],
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    print(f"[CHAT] <- discord {out['display_name']}({meta['rating']}): {message[:80]} (subs={chat_manager.count})")
    await chat_manager.broadcast(out)
    await _persist_chat(None, out)
    return {"status": "posted", "subscribers": chat_manager.count}


@app.get("/api/v1/chat/recent", tags=["Chat"])
async def get_recent_chat(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Scrollback for clients just connecting. Returns most-recent first, newest-last
    so the client can append directly to its display log."""
    # Join to current rating + active title so scrollback shows them too.
    rows = (await db.execute(
        text(
            "SELECT cm.source, cm.steam_id, cm.discord_id, cm.display_name, cm.message, cm.created_at, "
            "       ROUND(gr.rating)::int AS rating, si.name AS title, si.preview_color AS title_color "
            "FROM chat_messages cm "
            "LEFT JOIN players p ON "
            "   (cm.steam_id IS NOT NULL AND p.steam_id = cm.steam_id) OR "
            "   (cm.steam_id IS NULL AND cm.discord_id IS NOT NULL AND p.discord_id = cm.discord_id) "
            "LEFT JOIN glicko_ratings gr ON gr.player_id = p.id AND p.deleted_at IS NULL "
            "LEFT JOIN shop_items si ON si.id = p.active_title_id "
            "ORDER BY cm.created_at DESC LIMIT :limit"
        ),
        {"limit": limit},
    )).mappings().all()
    entries = list(reversed([
        {
            "source": r["source"],
            "steam_id": r["steam_id"],
            "discord_id": r["discord_id"],
            "display_name": r["display_name"],
            "rating": r["rating"],
            "title": r["title"],
            "title_color": r["title_color"],
            "message": r["message"],
            "timestamp": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]))
    return {"messages": entries}


# ── Betting helpers ──────────────────────────────────────────
# Elo expectancy. At |ΔR| ≥ 800 the favorite's P → ≈0.99, so the payout
# multiplier floors at 1/0.99 ≈ 1.01x — practically nothing for betting the
# obvious winner (matches the requested design).
def _elo_expectancy(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def _odds_multiplier(bet_on_rating: float, opponent_rating: float) -> float:
    p = _elo_expectancy(bet_on_rating, opponent_rating)
    if p <= 0.0:
        return 3.0
    # Cap the payout multiplier at 3x so no single bet can pay more than triple
    # your stake. Underdog bets on very-large Elo gaps still max out at 3x.
    # Favorite bets floor at 1.01x (barely-profitable) — matches the intent of
    # "shouldn't give anyone any gold for betting on an 800+ favorite."
    mult = 1.0 / p
    return max(1.01, min(mult, 3.0))


async def _settle_series_bets(db: AsyncSession, series: RankedSeries):
    """Called when a series transitions to status='completed'. Pays winning
    bets from the implicit house pool."""
    rows = (await db.execute(
        select(Bet).where(Bet.series_id == series.id, Bet.settled_at.is_(None))
    )).scalars().all()
    if not rows:
        return
    now = datetime.now(timezone.utc)
    for bet in rows:
        if bet.bet_on_player_id == series.winner_id:
            payout = int(round(bet.amount * bet.odds_multiplier))
            bet.payout = payout
            # Credit to bettor — payout INCLUDES stake return.
            bettor = (await db.execute(select(Player).where(Player.id == bet.player_id))).scalar_one_or_none()
            if bettor is not None:
                bettor.gold_earned = (bettor.gold_earned or 0) + payout
                db.add(GoldTransaction(
                    player_id=bettor.id, amount=payout,
                    reason="bet_win", reference_id=str(series.id),
                ))
        else:
            bet.payout = 0  # lost
        bet.settled_at = now
    print(f"[BETS] Settled {len(rows)} bets on series {series.id}")


# ── Routes: Shop ─────────────────────────────────────────────

@app.get("/api/v1/shop/items", tags=["Shop"])
async def list_shop_items(steam_id: str | None = Query(None), db: AsyncSession = Depends(get_db)):
    """Always-available items + (future) today's rotation pick. If steam_id is
    provided, annotates each item with 'owned' so the UI can hide Buy buttons
    for already-owned items."""
    rows = (await db.execute(
        select(ShopItem).where(ShopItem.rotation_pool.is_(None)).order_by(ShopItem.price)
    )).scalars().all()

    owned_ids: set[int] = set()
    if steam_id:
        p = (await db.execute(select(Player).where(Player.steam_id == steam_id))).scalar_one_or_none()
        if p is not None:
            owned_ids = {
                r for (r,) in (await db.execute(
                    select(PlayerItem.item_id).where(PlayerItem.player_id == p.id)
                )).all()
            }

    return {
        "items": [
            {
                "id": r.id,
                "sku": r.sku,
                "kind": r.kind,
                "name": r.name,
                "description": r.description,
                "price": r.price,
                "rarity": r.rarity,
                "preview_color": r.preview_color,
                "owned": r.id in owned_ids,
            }
            for r in rows
        ]
    }


@app.get("/api/v1/players/{steam_id}/inventory", tags=["Shop"])
async def get_inventory(steam_id: str, db: AsyncSession = Depends(get_db)):
    """Titles + trails the player has purchased."""
    p = (await db.execute(select(Player).where(Player.steam_id == steam_id))).scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="Player not found")
    rows = (await db.execute(
        select(ShopItem, PlayerItem)
        .join(PlayerItem, PlayerItem.item_id == ShopItem.id)
        .where(PlayerItem.player_id == p.id)
        .order_by(PlayerItem.purchased_at.desc())
    )).all()
    return {
        "active_title_id": p.active_title_id,
        "items": [
            {
                "id": item.id,
                "sku": item.sku,
                "kind": item.kind,
                "name": item.name,
                "rarity": item.rarity,
                "preview_color": item.preview_color,
                "purchased_at": pi.purchased_at.isoformat() if pi.purchased_at else None,
                "purchase_price": pi.purchase_price,
            }
            for (item, pi) in rows
        ],
    }


@app.post("/api/v1/shop/purchase", tags=["Shop"])
async def purchase_item(
    steam_id: str = Query(...),
    sku: str = Query(...),
    sig: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Buy an item. HMAC signs 'buy:{steam_id}:{sku}'. Server rejects if:
    already-owned, not enough gold, or item doesn't exist."""
    if not MATCH_HMAC_SECRET:
        raise HTTPException(status_code=503, detail="HMAC not configured")
    expected = hmac.new(
        MATCH_HMAC_SECRET.encode(), f"buy:{steam_id}:{sku}".encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=403, detail="Invalid signature")

    player = (await db.execute(select(Player).where(Player.steam_id == steam_id))).scalar_one_or_none()
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    if player.deleted_at is not None:
        raise HTTPException(status_code=410, detail="Account deleted")

    item = (await db.execute(select(ShopItem).where(ShopItem.sku == sku))).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    already = (await db.execute(
        select(PlayerItem).where(PlayerItem.player_id == player.id, PlayerItem.item_id == item.id)
    )).scalar_one_or_none()
    if already is not None:
        return {"status": "already_owned", "sku": sku}

    balance = (player.gold_earned or 0) - (player.gold_spent or 0)
    if balance < item.price:
        raise HTTPException(status_code=402, detail=f"Insufficient gold: have {balance}, need {item.price}")

    player.gold_spent = (player.gold_spent or 0) + item.price
    db.add(PlayerItem(player_id=player.id, item_id=item.id, purchase_price=item.price))
    db.add(GoldTransaction(
        player_id=player.id, amount=-item.price,
        reason="purchase", reference_id=sku,
    ))
    await db.commit()

    return {
        "status": "purchased",
        "sku": sku,
        "price": item.price,
        "new_balance": balance - item.price,
    }


@app.post("/api/v1/players/{steam_id}/active-title", tags=["Shop"])
async def set_active_title(
    steam_id: str,
    item_id: int | None = Query(None, description="Shop item ID, or null to clear"),
    sig: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    return await _set_active_cosmetic(db, steam_id, "title", "title", item_id, sig)


@app.post("/api/v1/players/{steam_id}/active-trail", tags=["Shop"])
async def set_active_trail(
    steam_id: str,
    item_id: int | None = Query(None, description="Shop item ID, or null to clear"),
    sig: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    return await _set_active_cosmetic(db, steam_id, "trail", "trail", item_id, sig)


async def _set_active_cosmetic(db: AsyncSession, steam_id: str, kind: str, prefix: str, item_id: int | None, sig: str):
    """Shared set-active logic for titles and trails."""
    if not MATCH_HMAC_SECRET:
        raise HTTPException(status_code=503, detail="HMAC not configured")
    expected = hmac.new(
        MATCH_HMAC_SECRET.encode(),
        f"{prefix}:{steam_id}:{item_id or 0}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=403, detail="Invalid signature")

    player = (await db.execute(select(Player).where(Player.steam_id == steam_id))).scalar_one_or_none()
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    attr = "active_title_id" if kind == "title" else "active_trail_id"
    if item_id is None:
        setattr(player, attr, None)
        await db.commit()
        return {"status": "cleared"}

    item = (await db.execute(select(ShopItem).where(ShopItem.id == item_id))).scalar_one_or_none()
    if item is None or item.kind != kind:
        raise HTTPException(status_code=400, detail=f"Not a valid {kind}")
    owned = (await db.execute(
        select(PlayerItem).where(PlayerItem.player_id == player.id, PlayerItem.item_id == item_id)
    )).scalar_one_or_none()
    if owned is None:
        raise HTTPException(status_code=403, detail="Item not owned")

    setattr(player, attr, item_id)
    await db.commit()
    return {"status": "set", "item_id": item_id, "name": item.name}


# ── Routes: Betting + Live series ────────────────────────────

@app.get("/api/v1/series/active", tags=["Series"])
async def get_active_series(db: AsyncSession = Depends(get_db)):
    """Live (in-progress) ranked series — for the bet UI."""
    rows = (await db.execute(text("""
        SELECT
            rs.id::text                AS series_id,
            rs.player1_id              AS p1_id,
            rs.player2_id              AS p2_id,
            p1.steam_id                AS p1_steam_id,
            p1.display_name            AS p1_name,
            p2.steam_id                AS p2_steam_id,
            p2.display_name            AS p2_name,
            ROUND(gr1.rating)::int     AS p1_rating,
            ROUND(gr2.rating)::int     AS p2_rating,
            rs.p1_series_wins, rs.p2_series_wins,
            rs.created_at
        FROM ranked_series rs
        JOIN players p1        ON p1.id = rs.player1_id
        JOIN players p2        ON p2.id = rs.player2_id
        LEFT JOIN glicko_ratings gr1 ON gr1.player_id = rs.player1_id
        LEFT JOIN glicko_ratings gr2 ON gr2.player_id = rs.player2_id
        WHERE rs.status = 'active'
          AND rs.created_at > NOW() - INTERVAL '2 hours'
        ORDER BY rs.created_at DESC
        LIMIT 20
    """))).mappings().all()

    series = []
    for r in rows:
        p1_rating = r["p1_rating"] or 1500
        p2_rating = r["p2_rating"] or 1500
        series.append({
            "series_id": r["series_id"],
            "p1_steam_id": r["p1_steam_id"],
            "p1_name": r["p1_name"],
            "p1_rating": p1_rating,
            "p1_wins": r["p1_series_wins"],
            "p1_odds": round(_odds_multiplier(p1_rating, p2_rating), 2),
            "p2_steam_id": r["p2_steam_id"],
            "p2_name": r["p2_name"],
            "p2_rating": p2_rating,
            "p2_wins": r["p2_series_wins"],
            "p2_odds": round(_odds_multiplier(p2_rating, p1_rating), 2),
            "started_at": r["created_at"].isoformat() if r["created_at"] else None,
        })
    return {"series": series}


@app.post("/api/v1/bets", tags=["Betting"])
async def place_bet(
    steam_id: str = Query(...),
    series_id: str = Query(...),
    bet_on_steam_id: str = Query(..., description="Which player's Steam ID to bet on"),
    amount: int = Query(..., ge=1, le=100000),
    sig: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Place a bet. HMAC signs 'bet:{steam_id}:{series_id}:{bet_on_steam_id}:{amount}'."""
    if not MATCH_HMAC_SECRET:
        raise HTTPException(status_code=503, detail="HMAC not configured")
    expected = hmac.new(
        MATCH_HMAC_SECRET.encode(),
        f"bet:{steam_id}:{series_id}:{bet_on_steam_id}:{amount}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=403, detail="Invalid signature")

    bettor = (await db.execute(select(Player).where(Player.steam_id == steam_id))).scalar_one_or_none()
    if bettor is None:
        raise HTTPException(status_code=404, detail="Player not found")

    try:
        sid = UUID(series_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid series_id")
    series = (await db.execute(select(RankedSeries).where(RankedSeries.id == sid))).scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Series not found")
    if series.status != "active":
        raise HTTPException(status_code=409, detail="Series is not active")
    if series.p1_series_wins >= 2 or series.p2_series_wins >= 2:
        raise HTTPException(status_code=409, detail="Series already effectively concluded")

    # Bettor can't be a participant — obvious integrity issue.
    if bettor.id in (series.player1_id, series.player2_id):
        raise HTTPException(status_code=409, detail="Cannot bet on your own match")

    bet_on = (await db.execute(select(Player).where(Player.steam_id == bet_on_steam_id))).scalar_one_or_none()
    if bet_on is None or bet_on.id not in (series.player1_id, series.player2_id):
        raise HTTPException(status_code=400, detail="bet_on_steam_id is not in this series")

    # One bet per series per player.
    existing = (await db.execute(
        select(Bet).where(Bet.player_id == bettor.id, Bet.series_id == sid)
    )).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Already bet on this series")

    # Insufficient gold?
    balance = (bettor.gold_earned or 0) - (bettor.gold_spent or 0)
    if balance < amount:
        raise HTTPException(status_code=402, detail=f"Insufficient gold: have {balance}, need {amount}")

    # Snapshot current ratings for odds.
    ratings = (await db.execute(text(
        "SELECT player_id, rating FROM glicko_ratings "
        "WHERE player_id = :p1 OR player_id = :p2"
    ), {"p1": series.player1_id, "p2": series.player2_id})).mappings().all()
    rmap = {r["player_id"]: float(r["rating"] or 1500) for r in ratings}
    bet_on_r = rmap.get(bet_on.id, 1500.0)
    other_id = series.player2_id if bet_on.id == series.player1_id else series.player1_id
    other_r = rmap.get(other_id, 1500.0)
    mult = _odds_multiplier(bet_on_r, other_r)

    # Stake: debit now, credit payout at settlement.
    bettor.gold_spent = (bettor.gold_spent or 0) + amount
    db.add(GoldTransaction(
        player_id=bettor.id, amount=-amount,
        reason="bet_stake", reference_id=series_id,
    ))
    db.add(Bet(
        player_id=bettor.id,
        series_id=sid,
        bet_on_player_id=bet_on.id,
        amount=amount,
        odds_multiplier=mult,
    ))
    await db.commit()
    return {
        "status": "placed",
        "amount": amount,
        "odds_multiplier": round(mult, 2),
        "potential_payout": int(round(amount * mult)),
    }


@app.get("/api/v1/players/{steam_id}/bets", tags=["Betting"])
async def get_player_bets(
    steam_id: str,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Player's recent bets — both pending and settled."""
    rows = (await db.execute(text("""
        SELECT
            b.id, b.amount, b.odds_multiplier, b.created_at, b.settled_at, b.payout,
            bo.steam_id      AS bet_on_steam_id,
            bo.display_name  AS bet_on_name,
            rs.status        AS series_status,
            rs.winner_id     AS series_winner_id,
            rs.p1_series_wins, rs.p2_series_wins
        FROM bets b
        JOIN players p        ON p.id = b.player_id
        JOIN players bo       ON bo.id = b.bet_on_player_id
        JOIN ranked_series rs ON rs.id = b.series_id
        WHERE p.steam_id = :sid
        ORDER BY b.created_at DESC
        LIMIT :limit
    """), {"sid": steam_id, "limit": limit})).mappings().all()
    return {
        "bets": [
            {
                "id": r["id"],
                "amount": r["amount"],
                "odds_multiplier": round(r["odds_multiplier"], 2),
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "settled_at": r["settled_at"].isoformat() if r["settled_at"] else None,
                "payout": r["payout"],
                "bet_on_steam_id": r["bet_on_steam_id"],
                "bet_on_name": r["bet_on_name"],
                "series_status": r["series_status"],
                "series_score": f"{r['p1_series_wins']}-{r['p2_series_wins']}",
            }
            for r in rows
        ]
    }


# ── Routes: Privacy ──────────────────────────────────────────

@app.delete("/api/v1/players/{steam_id}/data", tags=["Privacy"])
async def delete_player_data(steam_id: str, sig: str = Query(...), db: AsyncSession = Depends(get_db)):
    """
    Anonymize a player's identity. Irreversible.

    Match records, card picks, Elo history, and opponent records are kept
    intact — deleting them would rewrite W/L counts and retroactively change
    other players' ratings on the next Glicko recalc. Instead:

      - steam_id → deleted_<short-uuid>
      - display_name → "[Deleted User]"
      - discord_id, discord_username → NULL
      - ranked_enabled → false (drops from matchmaking immediately)
      - deleted_at stamped so the row is hidden from leaderboards
      - personal-only rows (achievements, link codes, queue entries, blocks) deleted

    Requires an HMAC signature over "delete:{steam_id}" using the mod secret.
    """
    if not MATCH_HMAC_SECRET:
        raise HTTPException(status_code=503, detail="HMAC not configured")

    expected = hmac.new(
        MATCH_HMAC_SECRET.encode(),
        f"delete:{steam_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=403, detail="Invalid signature")

    player = (await db.execute(select(Player).where(Player.steam_id == steam_id))).scalar_one_or_none()
    if player is None:
        return {"status": "not_found", "steam_id": steam_id}
    if player.deleted_at is not None:
        return {"status": "already_deleted", "steam_id": steam_id}

    pid = player.id

    # Drop purely personal rows — no cross-player impact.
    await db.execute(text("DELETE FROM player_achievements WHERE player_id = :pid"), {"pid": pid})
    await db.execute(text("DELETE FROM link_codes WHERE player_id = :pid"), {"pid": pid})
    await db.execute(text("DELETE FROM ranked_queue WHERE player_id = :pid OR matched_with = :pid"), {"pid": pid})
    await db.execute(text("DELETE FROM queue_blocks WHERE blocker_id = :pid OR blocked_id = :pid"), {"pid": pid})
    await db.execute(text("DELETE FROM player_blocks WHERE blocker_id = :pid OR blocked_id = :pid"), {"pid": pid})

    # Anonymize the player row. Keep rating_history / glicko / matches untouched
    # so Glicko recalcs and opponent histories stay consistent.
    short = uuid.uuid4().hex[:8]
    player.steam_id = f"deleted_{short}"
    player.display_name = "[Deleted User]"
    player.discord_id = None
    player.discord_username = None
    player.ranked_enabled = False
    player.deleted_at = datetime.now(timezone.utc)

    # Record hash so a later match report from the same Steam ID can't
    # spoof a fresh account.
    if MATCH_HMAC_SECRET:
        await db.execute(
            text("INSERT INTO deleted_steam_ids (steam_id_hash) VALUES (:h) ON CONFLICT DO NOTHING"),
            {"h": _hash_steam_id(steam_id)},
        )

    await db.commit()
    print(f"[PRIVACY] Anonymized steam_id={steam_id} (placeholder={player.steam_id})")

    return {"status": "anonymized", "steam_id": steam_id, "placeholder": player.steam_id}


# ── Routes: Achievements ─────────────────────────────────────

# Master achievement definitions — single source of truth
ACHIEVEMENT_DEFS = {
    "untouchable":          {"name": "Untouchable",         "desc": "Win a game without taking any damage"},
    "silent_assassin":      {"name": "Silent Assassin",     "desc": "5-0 someone with Sneaky"},
    "total_mayhem":         {"name": "Total Mayhem",        "desc": "5-0 someone with Mayhem"},
    "fragile_perfection":   {"name": "Fragile Perfection",  "desc": "5-0 someone with Glass Cannon"},
    "no_escape":            {"name": "No Escape",           "desc": "5-0 someone with Chase"},
    "rise_from_the_ashes":  {"name": "Rise from the Ashes", "desc": "Win 5-0 with Phoenix without losing a life"},
    "the_comeback_kid":     {"name": "The Comeback Kid",    "desc": "Win after being down 0-4"},
    "stacked_deck":         {"name": "Stacked Deck",        "desc": "Get 5 copies of one card in a game"},
    "regicide":             {"name": "Regicide",            "desc": "Win against Sid in a ranked series"},
    "pacifist":             {"name": "Pacifist",            "desc": "Win a game without firing a single shot"},
    "immovable_object":     {"name": "Immovable Object",    "desc": "Win a game without moving or jumping"},
}


@app.get("/api/v1/achievements/definitions", tags=["Achievements"])
async def get_achievement_definitions():
    """Return the master list of all achievements."""
    return {"achievements": ACHIEVEMENT_DEFS}


@app.get("/api/v1/achievements/{steam_id}", tags=["Achievements"])
async def get_player_achievements(steam_id: str, db: AsyncSession = Depends(get_db)):
    """Get all achievements for a player, merged with definitions."""
    player = await db.execute(select(Player).where(Player.steam_id == steam_id))
    player = player.scalar_one_or_none()
    if not player:
        # Return all locked if player not found
        entries = [
            AchievementEntry(achievement_key=k, unlocked=False)
            for k in ACHIEVEMENT_DEFS
        ]
        return AchievementListResponse(steam_id=steam_id, achievements=entries)

    result = await db.execute(
        select(PlayerAchievement).where(PlayerAchievement.player_id == player.id)
    )
    unlocked = {a.achievement_key: a.unlocked_at for a in result.scalars().all()}

    entries = []
    for key in ACHIEVEMENT_DEFS:
        entries.append(AchievementEntry(
            achievement_key=key,
            unlocked=key in unlocked,
            unlocked_at=unlocked.get(key),
        ))
    return AchievementListResponse(steam_id=steam_id, achievements=entries)


@app.post("/api/v1/achievements/unlock", tags=["Achievements"])
async def unlock_achievement(req: AchievementUnlockRequest, db: AsyncSession = Depends(get_db)):
    """Unlock an achievement for a player. Idempotent — re-unlocking is a no-op."""
    if req.achievement_key not in ACHIEVEMENT_DEFS:
        raise HTTPException(status_code=400, detail=f"Unknown achievement: {req.achievement_key}")

    player = await db.execute(select(Player).where(Player.steam_id == req.steam_id))
    player = player.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Check if already unlocked
    existing = await db.execute(
        select(PlayerAchievement).where(
            PlayerAchievement.player_id == player.id,
            PlayerAchievement.achievement_key == req.achievement_key,
        )
    )
    if existing.scalar_one_or_none():
        return {"status": "already_unlocked", "achievement_key": req.achievement_key}

    # Resolve optional match_id
    match_id_val = None
    if req.match_id:
        try:
            from uuid import UUID as _UUID
            mid = _UUID(req.match_id)
            match_row = await db.execute(select(Match.id).where(Match.id == mid))
            m = match_row.scalar_one_or_none()
            if m:
                match_id_val = m
        except Exception:
            pass

    ach = PlayerAchievement(
        player_id=player.id,
        achievement_key=req.achievement_key,
        match_id=match_id_val,
    )
    db.add(ach)

    # 25 gold per achievement — uniform for now; rarity-scaled pricing can come
    # with the shop rollout.
    ACHIEVEMENT_GOLD = 25
    player.gold_earned = (player.gold_earned or 0) + ACHIEVEMENT_GOLD
    db.add(GoldTransaction(
        player_id=player.id,
        amount=ACHIEVEMENT_GOLD,
        reason="achievement",
        reference_id=req.achievement_key,
    ))

    await db.commit()

    name = ACHIEVEMENT_DEFS[req.achievement_key]["name"]
    return {"status": "unlocked", "achievement_key": req.achievement_key, "name": name, "gold_awarded": ACHIEVEMENT_GOLD}
