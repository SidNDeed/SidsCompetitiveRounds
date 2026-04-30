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
from pydantic import BaseModel
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import and_, case, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from glicko2 import calculate_new_rating
from models import AdminUser, AdminAction, Bet, CardOffer, FlaggedMatch, GlickoRating, GoldTransaction, Match, MatchCard, Player, PlayerBan, PlayerItem, RankedSeries, RatingHistory, RankedQueue, QueueBlock, PlayerBlock, LinkCode, PlayerAchievement, ShopItem, GlickoRating2v2, TeamQueue, TeamSeries, TeamMatch, TeamMatchCard
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
    TeamQueueJoinRequest,
    TeamQueueMember,
    TeamQueuePollResponse,
    TeamMatchReport,
    TeamMatchResponse,
    TeamStatsResponse,
    Team2v2LeaderboardEntry,
    Team2v2LeaderboardResponse,
    TeamMatchHistoryEntry,
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
    task_t2 = asyncio.create_task(team_queue_cleanup_loop())
    from tournaments import tournament_tick
    task_t = asyncio.create_task(tournament_tick())
    yield
    task.cancel()
    task_t.cancel()
    task_t2.cancel()
    print("Competitive ROUNDS API shutting down")


async def team_queue_cleanup_loop():
    """Delete stale 2v2 queue rows. Mirrors queue_cleanup_loop with one extra
    safety net: when a 'matched' or 'ready' row goes stale we also cancel the
    series and boot the other 3 back to searching, since the queue cascade in
    /team/queue/leave only fires on explicit user action."""
    import asyncio as _aio
    from database import async_session
    while True:
        try:
            await _aio.sleep(60)
            async with async_session() as db:
                # Cancel any series whose queue rows have all gone stale (no poll in 30s).
                # This handles the case where a client crashed mid-lock without /leave.
                stale_series = await db.execute(
                    text("""
                        SELECT DISTINCT series_id FROM team_queue
                        WHERE series_id IS NOT NULL
                          AND last_polled < NOW() - INTERVAL '60 seconds'
                    """)
                )
                for srow in stale_series.fetchall():
                    sid = srow[0]
                    await db.execute(
                        text("""UPDATE team_series
                               SET status='cancelled', invalidated_at=NOW(),
                                   invalidation_reason='stale_queue_rows'
                               WHERE id=:sid AND status='active'"""),
                        {"sid": sid},
                    )
                # Stale-poll cleanup
                stale_q = await db.execute(
                    text("""DELETE FROM team_queue
                        WHERE last_polled < NOW() - INTERVAL '30 seconds'
                          AND joined_at >= NOW() - INTERVAL '30 minutes'
                        RETURNING steam_id, display_name, status, series_id""")
                )
                stale_rows = stale_q.fetchall()
                # Absolute-timeout cleanup (joined > 30 min ago, never matched)
                timeout_q = await db.execute(
                    text("""DELETE FROM team_queue
                        WHERE joined_at < NOW() - INTERVAL '30 minutes'
                        RETURNING steam_id, display_name, status, series_id""")
                )
                timeout_rows = timeout_q.fetchall()
                for r in stale_rows:
                    sid_part = f", series_id={r[3]}" if r[3] else ""
                    print(f"[TEAM-QUEUE-CLEANUP] Stale poll: {r[1]} status={r[2]}{sid_part}")
                for r in timeout_rows:
                    sid_part = f", series_id={r[3]}" if r[3] else ""
                    print(f"[TEAM-QUEUE-CLEANUP] Absolute timeout: {r[1]} status={r[2]}{sid_part}")
                await db.commit()
        except Exception as e:
            print(f"[TEAM-QUEUE-CLEANUP] Error: {e}")


async def queue_cleanup_loop():
    """Delete stale queue entries every 60 seconds.
    Logs enough detail to diagnose matchmaking reports like lopi+NotNic where
    one player's log showed repeated 'Match canceled' with no apparent cause —
    the cancel reason (stale poll vs absolute timeout) tells us whether it was
    a network hiccup or the player actually went idle."""
    import asyncio as _aio
    from database import async_session
    while True:
        try:
            await _aio.sleep(60)
            async with async_session() as db:
                # Separate the two cleanup reasons so we can attribute each one.
                stale_result = await db.execute(
                    text("""DELETE FROM ranked_queue
                        WHERE last_polled < NOW() - INTERVAL '30 seconds'
                          AND joined_at >= NOW() - INTERVAL '30 minutes'
                        RETURNING steam_id, display_name, status, matched_with""")
                )
                stale_rows = stale_result.fetchall()
                timeout_result = await db.execute(
                    text("""DELETE FROM ranked_queue
                        WHERE joined_at < NOW() - INTERVAL '30 minutes'
                        RETURNING steam_id, display_name, status, matched_with""")
                )
                timeout_rows = timeout_result.fetchall()
                for r in stale_rows:
                    partner = f", matched_with={r[3]}" if r[3] else ""
                    print(f"[QUEUE-CLEANUP] Stale poll (>30s no poll): {r[1]} status={r[2]}{partner}")
                for r in timeout_rows:
                    partner = f", matched_with={r[3]}" if r[3] else ""
                    print(f"[QUEUE-CLEANUP] Absolute timeout (>30min in queue): {r[1]} status={r[2]}{partner}")
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

# Tournament endpoints (router module).
from tournaments import router as tournaments_router
app.include_router(tournaments_router)


# ── Version gate ───────────────────────────────────────────────
# Clients send X-Mod-Version on every request. If the version is below
# MIN_MOD_VERSION, the request is rejected with 426 so the mod can prompt
# the user to update before showing any data.
#
# Initial deploy grandfathers requests with no header (older clients in the
# wild). Once adoption of the header is universal, set REQUIRE_MOD_VERSION
# to True to lock out anyone who removes it.

MIN_MOD_VERSION = "1.22.0"
REQUIRE_MOD_VERSION = True  # Missing-header clients are pre-1.18.7 and should be locked out.

# Endpoints that bypass the gate (mod uses these to discover the required version).
# Use a frozenset of exact paths — startswith on a tuple containing "/" would match everything.
_VERSION_GATE_BYPASS = frozenset({
    "/api/v1/mod-version",
    "/api/v1/health",
    "/api/v1/healthz",
    "/api/v1/chat/post",      # internal bot relay; authenticated by X-Internal-Key instead
    "/api/v1/chat/recent",    # bot uses this for scrollback on WS reconnect too
    "/api/v1/admin/maintenance/status",  # public-readable so even pre-version-check clients can probe
})


def _parse_version(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except Exception:
        return (0,)


# Maintenance mode — set to True via /admin/maintenance/start. While True, all non-bypass
# requests get a 503 with Retry-After:30. Internal callers (X-Internal-Key) still go through
# so the deploy script + bot can finish work. Reset to False on container start (it's just a
# module global), so a fresh container after a redeploy is automatically NOT in maintenance.
_in_maintenance: bool = False
_MAINT_BYPASS = frozenset({
    "/api/v1/mod-version",
    "/api/v1/health",
    "/api/v1/healthz",
    "/api/v1/admin/maintenance/start",
    "/api/v1/admin/maintenance/stop",
    "/api/v1/admin/maintenance/status",
})


@app.middleware("http")
async def maintenance_gate(request: Request, call_next):
    if _in_maintenance:
        path = request.url.path
        # Always allow the bypass set + internal callers + maintenance control endpoints.
        internal_key = request.headers.get("X-Internal-Key")
        is_internal = internal_key and internal_key == os.getenv("API_SECRET_KEY", "")
        if path not in _MAINT_BYPASS and not is_internal:
            return JSONResponse(
                status_code=503,
                content={"error": "maintenance", "retry_after": 30},
                headers={"Retry-After": "30"},
            )
    return await call_next(request)


@app.middleware("http")
async def version_gate(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/v1/") or path in _VERSION_GATE_BYPASS:
        return await call_next(request)
    # Internal callers (Discord bot) authenticate via X-Internal-Key and bypass the version gate.
    # Bot doesn't have a "mod version" — locking it out broke leaderboard posting + flag relay.
    internal_key = request.headers.get("X-Internal-Key")
    if internal_key and internal_key == os.getenv("API_SECRET_KEY", ""):
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
    # Beta title is NOT auto-granted here anymore — every player row in the
    # DB triggers this path including casual opponents auto-created from
    # match reports. _mark_mod_seen() in mod-only endpoints handles the
    # Beta grant for actual mod users.
    return player


async def _mark_mod_seen(db: AsyncSession, player: Player) -> None:
    """Stamp `mod_seen_at` and auto-grant the Beta title. Called from mod-only
    endpoints (queue join, toggle-ranked, achievements unlock, match-report
    reporter) so the Beta title only lands on confirmed mod users — not on
    casual opponents auto-created by get_or_create_player."""
    if player is None or player.deleted_at is not None:
        return
    try:
        if player.mod_seen_at is None:
            player.mod_seen_at = datetime.now(timezone.utc)
        beta_id = (await db.execute(
            text("SELECT id FROM shop_items WHERE sku = 'title_beta' LIMIT 1")
        )).scalar()
        if beta_id is None:
            return
        await db.execute(
            text("INSERT INTO player_items (player_id, item_id, purchase_price) "
                 "VALUES (:pid, :iid, 0) "
                 "ON CONFLICT (player_id, item_id) DO NOTHING"),
            {"pid": player.id, "iid": beta_id},
        )
        if player.active_title_id is None:
            player.active_title_id = beta_id
    except Exception as ex:
        print(f"[BETA] mark_mod_seen failed for {player.steam_id}: {ex}")


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
    Ranked: 1.5x multiplier (bumped from 1.2x — ranked should feel meaningfully more rewarding)
    Beat top-5 player: +150 flat bonus
    """
    base_xp = 250
    bonuses = []
    multiplier = 1.0

    if won:
        multiplier *= 1.5
        bonuses.append("Win x1.5")

    if is_ranked:
        multiplier *= 1.5
        bonuses.append("Ranked x1.5")

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


LATEST_MOD_VERSION = "1.26.0"

@app.get("/api/v1/mod-version", tags=["System"])
async def get_mod_version():
    """Returns the latest recommended mod version and the gating floor."""
    return {"version": LATEST_MOD_VERSION, "min_version": MIN_MOD_VERSION}


# ── Internal endpoints (used by the Discord bot) ───────────────

@app.get("/api/v1/internal/recent-flags", tags=["Internal"])
async def get_recent_flags(
    since_id: str | None = Query(None, description="Last flag ID the bot has already posted"),
    limit: int = Query(50, ge=1, le=200),
    x_internal_key: str | None = Header(None, alias="X-Internal-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Bot-only feed for the #scr-admin channel poller. Returns newly-created
    flagged_matches rows with enough match context to render a one-line embed."""
    expected = os.getenv("API_SECRET_KEY", "")
    if not expected or x_internal_key != expected:
        raise HTTPException(status_code=403, detail="Invalid internal key")

    # Pull flag rows with the underlying match's relevant fields. Order by created_at ASC
    # so the bot can post in chronological order. since_id filtering uses created_at lookup
    # because UUIDs aren't sortable as time but the (id, created_at) pair is unique.
    if since_id:
        cutoff_q = await db.execute(
            text("SELECT created_at FROM flagged_matches WHERE id = :id"),
            {"id": since_id},
        )
        cutoff_row = cutoff_q.first()
        cutoff = cutoff_row[0] if cutoff_row else None
    else:
        cutoff = None

    if cutoff is not None:
        rows = (await db.execute(text(
            "SELECT fm.id, fm.match_id, fm.flag_reason, fm.flag_details, fm.auto_invalidated, "
            "       fm.player_steam_ids, fm.created_at, "
            "       m.is_ranked, m.duration_seconds, m.match_duration, "
            "       p1.display_name AS p1_name, p2.display_name AS p2_name "
            "FROM flagged_matches fm "
            "JOIN matches m ON m.id = fm.match_id "
            "JOIN players p1 ON p1.id = m.player1_id "
            "JOIN players p2 ON p2.id = m.player2_id "
            "WHERE fm.created_at > :cutoff "
            "ORDER BY fm.created_at ASC LIMIT :limit"
        ), {"cutoff": cutoff, "limit": limit})).mappings().all()
    else:
        rows = (await db.execute(text(
            "SELECT fm.id, fm.match_id, fm.flag_reason, fm.flag_details, fm.auto_invalidated, "
            "       fm.player_steam_ids, fm.created_at, "
            "       m.is_ranked, m.duration_seconds, m.match_duration, "
            "       p1.display_name AS p1_name, p2.display_name AS p2_name "
            "FROM flagged_matches fm "
            "JOIN matches m ON m.id = fm.match_id "
            "JOIN players p1 ON p1.id = m.player1_id "
            "JOIN players p2 ON p2.id = m.player2_id "
            "ORDER BY fm.created_at ASC LIMIT :limit"
        ), {"limit": limit})).mappings().all()

    return {
        "flags": [
            {
                "id": str(r["id"]),
                "match_id": str(r["match_id"]),
                "flag_reason": r["flag_reason"],
                "flag_details": r["flag_details"],
                "auto_invalidated": r["auto_invalidated"],
                "player_steam_ids": r["player_steam_ids"],
                "p1_name": r["p1_name"],
                "p2_name": r["p2_name"],
                "is_ranked": r["is_ranked"],
                "duration_seconds": r["duration_seconds"] or r["match_duration"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]
    }


# ── Anti-cheat detection ───────────────────────────────────────
#
# Three checks run on every match submission:
#   1. >5 cards picked by either player    → vanilla impossible, auto-invalidate
#   2. Sub-60s pattern between same pair   → 2+ in a 2hr window for ranked, 3+ for casual.
#                                            Auto-invalidates this match AND retroactively the prior ones.
#   3. Reporter sat idle (0 shots, 0 blocks, duration > 30s)
#                                          → flag only (we only see reporter's inputs; opponent could be
#                                            the cheater instead, so manual review).
#
# Pattern detection definition of "session": matches between same Steam ID pair within last 2h.
# Confirmed with Sid: false positives "should never happen" because two-player ROUNDS games
# legitimately take 2+ minutes per game.

ANTICHEAT_SHORT_DURATION_SEC = 60
ANTICHEAT_PATTERN_WINDOW_HOURS = 2
ANTICHEAT_MAX_CARDS_PER_PLAYER = 5
# Duration floor for the AFK check. Combined with cards_picked=0 AND shots=0
# AND blocks=0, this catches real AFK (never-at-keyboard) without firing on
# legitimate-but-inputless play like Pacifist, Melee, Echo+Decay, or
# trap-and-run builds. Dropped from 300s since cards_picked=0 is the strong
# signal now; duration just filters out match-abort races.
ANTICHEAT_INACTIVE_MIN_DURATION_SEC = 120


async def _reverse_match_gold_xp(db: AsyncSession, m: Match) -> None:
    """Add offsetting gold/XP rows for an invalidated match. Called on retro-invalidation."""
    txns = (await db.execute(
        select(GoldTransaction).where(
            GoldTransaction.reference_id == str(m.id),
            GoldTransaction.reason.in_(["xp", "series_win"]),
        )
    )).scalars().all()
    for tx in txns:
        db.add(GoldTransaction(
            player_id=tx.player_id, amount=-tx.amount,
            reason="reversal", reference_id=str(m.id),
        ))
        player = (await db.execute(select(Player).where(Player.id == tx.player_id))).scalar_one_or_none()
        if player is not None:
            player.gold_earned = max(0, (player.gold_earned or 0) - tx.amount)
    # Roll back XP. p1_xp_gained / p2_xp_gained were stored at insert time.
    p1_obj = (await db.execute(select(Player).where(Player.id == m.player1_id))).scalar_one_or_none()
    p2_obj = (await db.execute(select(Player).where(Player.id == m.player2_id))).scalar_one_or_none()
    if p1_obj is not None and m.p1_xp_gained:
        p1_obj.total_xp = max(0, (p1_obj.total_xp or 0) - m.p1_xp_gained)
    if p2_obj is not None and m.p2_xp_gained:
        p2_obj.total_xp = max(0, (p2_obj.total_xp or 0) - m.p2_xp_gained)


async def _check_anti_cheat(
    db: AsyncSession, match: Match, report: MatchReport, p1: Player, p2: Player,
) -> dict:
    """Returns {'flags': [(reason, details, auto_invalidate), ...], 'invalidate': bool}."""
    flags = []
    invalidate = False

    # 1. Too many cards (vanilla cap is 5 picks per player per BO5 game).
    p1_cards = len(report.player1.cards or [])
    p2_cards = len(report.player2.cards or [])
    if p1_cards > ANTICHEAT_MAX_CARDS_PER_PLAYER or p2_cards > ANTICHEAT_MAX_CARDS_PER_PLAYER:
        flags.append((
            "too_many_cards",
            {
                "p1_cards": p1_cards, "p2_cards": p2_cards,
                "p1_steam": p1.steam_id, "p2_steam": p2.steam_id,
                "max_allowed": ANTICHEAT_MAX_CARDS_PER_PLAYER,
            },
            True,
        ))
        invalidate = True

    # 2. Sub-60s pattern. Must use COALESCE since older matches only have match_duration set.
    duration = report.match_duration if report.match_duration is not None else 999999
    if duration < ANTICHEAT_SHORT_DURATION_SEC:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=ANTICHEAT_PATTERN_WINDOW_HOURS)
        prior_rows = (await db.execute(
            select(Match).where(
                Match.id != match.id,
                Match.is_ranked == report.is_ranked,
                Match.invalidated_at.is_(None),
                Match.ended_at >= cutoff,
                func.coalesce(Match.duration_seconds, Match.match_duration) < ANTICHEAT_SHORT_DURATION_SEC,
                or_(
                    and_(Match.player1_id == p1.id, Match.player2_id == p2.id),
                    and_(Match.player1_id == p2.id, Match.player2_id == p1.id),
                ),
            )
        )).scalars().all()
        # Ranked needs 2 total (1 prior + current); casual needs 3 (2 prior + current).
        prior_threshold = 1 if report.is_ranked else 2
        if len(prior_rows) >= prior_threshold:
            flags.append((
                "short_duration_pattern",
                {
                    "duration_seconds": duration,
                    "prior_match_ids": [str(m.id) for m in prior_rows],
                    "p1_steam": p1.steam_id, "p2_steam": p2.steam_id,
                    "is_ranked": report.is_ranked,
                    "window_hours": ANTICHEAT_PATTERN_WINDOW_HOURS,
                },
                True,
            ))
            invalidate = True
            # Retro-invalidate every prior sub-60s match in the window. They each
            # get their own flag row (so the admin tab shows them all) and their
            # gold/xp gets reversed via _reverse_match_gold_xp.
            for prior in prior_rows:
                if prior.invalidated_at is not None:
                    continue
                prior.invalidated_at = datetime.now(timezone.utc)
                prior.invalidation_reason = "short_duration_pattern_retro"
                db.add(FlaggedMatch(
                    match_id=prior.id,
                    series_id=prior.series_id,
                    player_steam_ids=[p1.steam_id, p2.steam_id],
                    flag_reason="short_duration_pattern",
                    flag_details={
                        "retroactive": True,
                        "triggered_by_match": str(match.id),
                        "duration_seconds": prior.duration_seconds or prior.match_duration,
                    },
                    auto_invalidated=True,
                ))
                # Cascade: if the prior match's series exists and isn't already invalid,
                # mark the series invalidated too. Glicko reversal is left to admin manual reverse.
                if prior.series_id is not None:
                    s = (await db.execute(select(RankedSeries).where(RankedSeries.id == prior.series_id))).scalar_one_or_none()
                    if s is not None and s.invalidated_at is None:
                        s.invalidated_at = datetime.now(timezone.utc)
                        s.invalidation_reason = "short_duration_pattern_retro"
                await _reverse_match_gold_xp(db, prior)

    # 3. Inactive reporter (advisory — flag only, no auto-invalidate).
    # Real AFK = player was never at the keyboard. Shots/blocks = 0 alone is
    # NOT sufficient — Pacifist, Melee, Empower+body, Echo+Decay, and trap-
    # and-run builds legitimately finish matches with zero bullets fired. Add
    # the reporter's cards_picked count to the criteria: you can't pick a
    # card without clicking at the keyboard, so any card pick proves
    # presence. First audit of flagged_matches (see /flag 74af9629..) showed
    # every historical "inactive_player" flag had 1-5 cards picked by the
    # reporter, meaning every one was a false positive.
    shots = report.local_shots_fired
    blocks = report.local_blocks_raised
    # Reporter's cards live under their PlayerMatchData sub-object (player1
    # or player2 depending on who reported). Look up by steam_id match.
    reporter_cards = 0
    if report.reported_by_steam_id == report.player1.steam_id:
        reporter_cards = len(report.player1.cards or [])
    elif report.reported_by_steam_id == report.player2.steam_id:
        reporter_cards = len(report.player2.cards or [])
    if (shots is not None and blocks is not None
            and shots == 0 and blocks == 0
            and reporter_cards == 0
            and report.match_duration is not None
            and report.match_duration > ANTICHEAT_INACTIVE_MIN_DURATION_SEC):
        flags.append((
            "inactive_player",
            {
                "reporter_steam": report.reported_by_steam_id,
                "duration_seconds": report.match_duration,
                "shots": 0, "blocks": 0, "cards_picked": 0,
            },
            False,
        ))

    return {"flags": flags, "invalidate": invalidate}


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

    # Reject offline / practice matches. ROUNDS' offline mode puts the photon room name as
    # "offline room" (with a space) — a buggy client would otherwise submit those with the
    # cached online-opponent's steam_id attached, producing phantom matches the real
    # opponent never played. Client-side block was added in the same pass but this server
    # check is defense in depth.
    if report.photon_room_id and "offline" in report.photon_room_id.lower():
        raise HTTPException(status_code=400, detail="Offline matches are not recorded")

    # Get or create both players
    p1 = await get_or_create_player(db, report.player1.steam_id, report.player1.display_name)
    p2 = await get_or_create_player(db, report.player2.steam_id, report.player2.display_name)

    # Determine winner
    winner = p1 if report.p1_rounds_won > report.p2_rounds_won else p2

    # Find the reporting player
    reporter = p1 if report.reported_by_steam_id == report.player1.steam_id else p2
    # Reporter clearly has the mod installed — stamp them and grant Beta.
    await _mark_mod_seen(db, reporter)

    # Create match record. duration_seconds mirrors match_duration so anti-cheat
    # queries can use the canonical column going forward; both populated for safety.
    # local_bullets_fired / local_blocks_raised come from the reporter's mod and
    # are advisory (not in HMAC). Reused field naming despite client→server casing.
    # FPS comes in as (local_avg_fps, opponent_avg_fps) on the reporter's side. Map onto
    # (p1_fps_avg, p2_fps_avg) by who the reporter actually was. Zero or missing → NULL
    # so the row stays unambiguous (no "0 fps" false-positives).
    reporter_is_p1 = reporter.id == p1.id
    _local_fps = report.local_avg_fps if (report.local_avg_fps or 0) > 0 else None
    _opp_fps = report.opponent_avg_fps if (report.opponent_avg_fps or 0) > 0 else None
    p1_fps = _local_fps if reporter_is_p1 else _opp_fps
    p2_fps = _opp_fps if reporter_is_p1 else _local_fps

    match = Match(
        player1_id=p1.id,
        player2_id=p2.id,
        p1_rounds_won=report.p1_rounds_won,
        p2_rounds_won=report.p2_rounds_won,
        p1_points_total=report.p1_points_total,
        p2_points_total=report.p2_points_total,
        winner_id=winner.id,
        match_duration=report.match_duration,
        duration_seconds=report.match_duration,
        local_bullets_fired=report.local_shots_fired,
        local_blocks_raised=report.local_blocks_raised,
        photon_room_id=report.photon_room_id,
        game_version=report.game_version,
        region=report.region,
        hmac_signature=report.hmac_signature,
        reported_by=reporter.id,
        is_ranked=report.is_ranked,
        started_at=report.started_at,
        p1_fps_avg=p1_fps,
        p2_fps_avg=p2_fps,
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

    # ── Anti-cheat ────────────────────────────────────────────
    # Run BEFORE any XP / gold / Glicko / series logic so an invalidated match
    # short-circuits all rewards. Advisory flags (e.g. inactive_player) are
    # recorded but don't short-circuit.
    ac = await _check_anti_cheat(db, match, report, p1, p2)
    if ac["invalidate"]:
        match.invalidated_at = datetime.now(timezone.utc)
        match.invalidation_reason = ",".join(r for r, _, ai in ac["flags"] if ai)
    for reason, details, auto_inv in ac["flags"]:
        db.add(FlaggedMatch(
            match_id=match.id,
            series_id=None,                      # set on retro-flags, not on the live one (no series yet)
            player_steam_ids=[p1.steam_id, p2.steam_id],
            flag_reason=reason,
            flag_details=details,
            auto_invalidated=auto_inv,
        ))
    if ac["invalidate"]:
        await db.commit()
        return MatchResponse(
            match_id=match.id,
            winner_steam_id=winner.steam_id,
            message=f"Match flagged: {match.invalidation_reason}",
            xp_gained=0, xp_bonuses=[], total_xp=reporter.total_xp or 0,
            level=level_from_xp(reporter.total_xp or 0)[0],
            series_status="invalidated", series_score="",
            gold_gained=0, gold_bonuses=[],
        )

    # Increment games_in_period for both players
    for pid in [p1.id, p2.id]:
        result = await db.execute(select(GlickoRating).where(GlickoRating.player_id == pid))
        glicko = result.scalar_one_or_none()
        if glicko:
            glicko.games_in_period += 1
            glicko.updated_at = datetime.now(timezone.utc)

    # Aggregate the reporter's hit/block counters into their lifetime totals (v1.23).
    # Only the reporter has these numbers — the higher Steam ID's client never sees match
    # completion — so Hit % / Block % are one-sided totals accumulated from whichever side
    # happened to report each match. Incoming fields are Optional and default to 0.
    if report.local_bullets_fired:
        reporter.bullets_fired = (reporter.bullets_fired or 0) + report.local_bullets_fired
    if report.local_bullets_hit:
        reporter.bullets_hit = (reporter.bullets_hit or 0) + report.local_bullets_hit
    if report.local_blocks_activated:
        reporter.blocks_activated = (reporter.blocks_activated or 0) + report.local_blocks_activated
    if report.local_blocks_successful:
        reporter.blocks_successful = (reporter.blocks_successful or 0) + report.local_blocks_successful

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
        # Find active series between these two players (order-independent).
        # Use the MOST RECENTLY CREATED active series so a player in multiple
        # tournaments against the same opponent doesn't crash the handler with
        # MultipleResultsFound. Tournament series are inserted when a match
        # becomes ready, so "newest active series" = "current match context."
        series_query = (
            select(RankedSeries)
            .where(
                RankedSeries.status == "active",
                or_(
                    (RankedSeries.player1_id == p1.id) & (RankedSeries.player2_id == p2.id),
                    (RankedSeries.player1_id == p2.id) & (RankedSeries.player2_id == p1.id),
                )
            )
            .order_by(RankedSeries.created_at.desc())
            .limit(1)
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

            # +10 gold to the series winner, +2 extra if it was a 2-0 sweep.
            # (Doubled from the 5/+1 payout in v1.22 to give ranked more teeth.)
            series_winner = p1 if series.p1_series_wins >= 2 else p2
            bonus = 10
            if series.p1_series_wins == 0 or series.p2_series_wins == 0:
                bonus += 2
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

        # Tournament bracket advancement. Noop for non-tournament series.
        try:
            if series.is_tournament:
                from tournaments import advance_tournament_match
                await advance_tournament_match(db, series.id)
                await db.commit()
        except Exception as ex:
            print(f"[TOURNAMENT] advance_tournament_match error: {ex}")

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

    # Active cosmetic lookups (title + trail + map color)
    active_title_name: str | None = None
    active_title_color: str | None = None
    active_trail_sku: str | None = None
    active_trail_color: str | None = None
    active_trail_price: int = 0
    active_color_sku: str | None = None
    active_color_skus: list[str] = []
    active_player_color_sku: str | None = None
    active_player_color_hex: str | None = None
    active_player_color_name: str | None = None
    for cosmetic_id, kind in ((player.active_title_id, "title"),
                               (player.active_trail_id, "trail"),
                               (player.active_color_id, "color"),
                               (player.active_player_color_id, "player_color")):
        if cosmetic_id is None:
            continue
        row = (await db.execute(
            select(ShopItem.name, ShopItem.sku, ShopItem.preview_color, ShopItem.price).where(ShopItem.id == cosmetic_id)
        )).first()
        if row is None:
            continue
        if kind == "title":
            active_title_name, active_title_color = row[0], row[2]
        elif kind == "trail":
            active_trail_sku, active_trail_color, active_trail_price = row[1], row[2], row[3] or 0
        elif kind == "color":
            active_color_sku = row[1]  # kept for backward compat — "first equipped color"
        else:  # player_color
            active_player_color_name = row[0]
            active_player_color_sku = row[1]
            active_player_color_hex = row[2]

    # Multi-equip colors: resolve the full active_color_ids list to skus so the client
    # can cycle between them with Left Shift in-game.
    color_id_list = player.active_color_ids or []
    if color_id_list:
        color_rows = (await db.execute(
            select(ShopItem.id, ShopItem.sku).where(ShopItem.id.in_(color_id_list), ShopItem.kind == "color")
        )).all()
        # Preserve the user's equipped order — the array is the source of truth.
        id_to_sku = {r[0]: r[1] for r in color_rows}
        active_color_skus = [id_to_sku[cid] for cid in color_id_list if cid in id_to_sku]
        # Ensure active_color_sku (the legacy single-value field) points at the first entry.
        if not active_color_sku and active_color_skus:
            active_color_sku = active_color_skus[0]

    # Active nametag styles (stackable). Returned as sku strings so the client can map
    # sku → rich-text tag without another lookup.
    active_nametag_skus: list[str] = []
    nametag_ids = player.nametag_style_ids or []
    if nametag_ids:
        nt_rows = (await db.execute(
            select(ShopItem.sku).where(ShopItem.id.in_(nametag_ids), ShopItem.kind == "nametag")
        )).all()
        active_nametag_skus = [r[0] for r in nt_rows]

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
        bullets_fired=player.bullets_fired or 0,
        bullets_hit=player.bullets_hit or 0,
        blocks_activated=player.blocks_activated or 0,
        blocks_successful=player.blocks_successful or 0,
        active_title=active_title_name,
        active_title_color=active_title_color,
        active_trail_sku=active_trail_sku,
        active_trail_color=active_trail_color,
        active_trail_price=active_trail_price,
        active_color_sku=active_color_sku,
        active_color_skus=active_color_skus,
        active_player_color_sku=active_player_color_sku,
        active_player_color_hex=active_player_color_hex,
        active_player_color_name=active_player_color_name,
        active_nametag_skus=active_nametag_skus,
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
            -- Opponent's CURRENT active title (view-time, not match-time snapshot — cheaper and good enough).
            CASE WHEN m.player1_id = :pid THEN si2.name        ELSE si1.name        END AS opp_title,
            CASE WHEN m.player1_id = :pid THEN si2.preview_color ELSE si1.preview_color END AS opp_title_color,
            m.series_id::text AS series_id,
            rs.status AS series_status,
            rs.p1_series_wins AS s_p1w,
            rs.p2_series_wins AS s_p2w,
            rs.player1_id AS s_p1id,
            CASE WHEN rs.player1_id = :pid THEN rs.p1_rating_change
                 ELSE rs.p2_rating_change END AS series_rating_change,
            CASE WHEN m.player1_id = :pid THEN m.p1_xp_gained
                 ELSE m.p2_xp_gained END AS xp_gained,
            CASE WHEN m.player1_id = :pid THEN m.p1_fps_avg ELSE m.p2_fps_avg END AS player_fps_avg,
            CASE WHEN m.player1_id = :pid THEN m.p2_fps_avg ELSE m.p1_fps_avg END AS opponent_fps_avg,
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
        LEFT JOIN shop_items si1 ON si1.id = p1.active_title_id
        LEFT JOIN shop_items si2 ON si2.id = p2.active_title_id
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
            opponent_title=row["opp_title"],
            opponent_title_color=row["opp_title_color"],
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
            player_fps_avg=row["player_fps_avg"],
            opponent_fps_avg=row["opponent_fps_avg"],
        ))

    return entries


# ── Routes: Card Stats ─────────────────────────────────────────

@app.get("/api/v1/players/{steam_id}/card-tiers", tags=["Cards"])
async def get_player_card_tiers(
    steam_id: str,
    filter: str = Query("ranked"),
    db: AsyncSession = Depends(get_db),
):
    """Per-player tier-list assignments for the Card Stats panel. Returns a
    map {card_name: tier} for the requested filter ('casual'|'ranked'|'all').
    Empty dict if the player has no rankings yet for this filter."""
    f = filter.lower()
    if f not in ("casual", "ranked", "all"):
        raise HTTPException(400, "filter must be casual|ranked|all")
    rows = (await db.execute(
        text("""
            SELECT pct.card_name, pct.tier
              FROM player_card_tiers pct
              JOIN players p ON p.id = pct.player_id
             WHERE p.steam_id = :sid AND pct.filter = :f
        """), {"sid": steam_id, "f": f}
    )).mappings().all()
    return {"filter": f, "tiers": {r["card_name"]: r["tier"] for r in rows}}


@app.post("/api/v1/players/{steam_id}/card-tiers", tags=["Cards"])
async def set_player_card_tier(
    steam_id: str,
    card_name: str = Query(..., max_length=64),
    filter: str = Query(...),
    tier: str = Query(""),  # empty = clear
    sig: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Set or clear a single (card, filter) tier for the caller. HMAC over
    'card-tier:{steam}:{card}:{filter}:{tier}' so a malicious client can't
    overwrite someone else's tier list."""
    if not MATCH_HMAC_SECRET:
        raise HTTPException(503, "HMAC not configured")
    expected = hmac.new(
        MATCH_HMAC_SECRET.encode(),
        f"card-tier:{steam_id}:{card_name}:{filter}:{tier}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(403, "Invalid signature")

    f = filter.lower()
    if f not in ("casual", "ranked", "all"):
        raise HTTPException(400, "filter must be casual|ranked|all")
    t = tier.upper().strip()
    if t and t not in ("S", "A", "B", "C", "D", "E", "F"):
        raise HTTPException(400, "tier must be S/A/B/C/D/E/F or empty")

    pid = (await db.execute(
        select(Player.id).where(Player.steam_id == steam_id)
    )).scalar_one_or_none()
    if pid is None:
        raise HTTPException(404, "Player not found")

    if not t:
        # Empty tier = clear the assignment.
        await db.execute(
            text("DELETE FROM player_card_tiers WHERE player_id=:pid AND card_name=:c AND filter=:f"),
            {"pid": pid, "c": card_name, "f": f},
        )
    else:
        await db.execute(
            text("""
                INSERT INTO player_card_tiers (player_id, card_name, filter, tier)
                VALUES (:pid, :c, :f, :t)
                ON CONFLICT (player_id, card_name, filter)
                DO UPDATE SET tier = EXCLUDED.tier, assigned_at = NOW()
            """),
            {"pid": pid, "c": card_name, "f": f, "t": t},
        )
    await db.commit()
    return {"status": "ok", "card_name": card_name, "filter": f, "tier": t or None}


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
    await _mark_mod_seen(db, player)
    await db.commit()

    return {"steam_id": steam_id, "ranked_enabled": enabled}


# ── Routes: Ranked Queue ──────────────────────────────────────

QUEUE_EXPIRE_MINUTES = 30
QUEUE_BLOCK_MINUTES = 5
# Window for both players to click Ready Up after being matched. Was 30s but
# lopi/NotNic reported "both readied, match canceled" — both alt-tabbed into
# ROUNDS, found the F5 menu, clicked Ready, and one of them consistently
# tripped the timeout. 90s gives real humans enough slack for Discord-to-game
# context switching. Additionally, /queue/ready resets matched_at on the
# first-to-ready so the slower player gets a fresh window, not leftover time.
READY_TIMEOUT_SECONDS = 90


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
    # Banned players can't queue. Let them load the leaderboard so they see the status.
    await _check_ban_or_raise(db, req.steam_id)
    # Get or create the player (auto-register on first queue join)
    name = req.display_name or req.steam_id
    player = await get_or_create_player(db, req.steam_id, name)
    await _mark_mod_seen(db, player)

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
                print(f"[QUEUE-CANCEL] {steam_id} vs opp={opp['steam_id']} "
                      f"timed out at match_age={match_age}s "
                      f"my_ready={my_ready} opp_ready={opp_ready}")
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
        print(f"[QUEUE-READY] {steam_id} NOT_MATCHED — entry={'none' if not entry else entry['status']}")
        await db.commit()
        return {"status": "not_matched", "message": "Not currently in a matched state"}

    # Set ourselves as ready.
    await db.execute(
        text("UPDATE ranked_queue SET ready = true WHERE player_id = :pid"),
        {"pid": player.id},
    )

    # Check if opponent is also ready (must FOR UPDATE-lock their row before
    # the matched_at reset below so polls don't see a half-state).
    opp_result = await db.execute(
        text("""
            SELECT player_id, ready, room_name, region
            FROM ranked_queue WHERE player_id = :oid
            FOR UPDATE
        """),
        {"oid": entry["matched_with"]},
    )
    opp = opp_result.mappings().first()

    # Refresh matched_at on BOTH rows so the opponent's ready timeout window
    # resets from NOW. Their normal 90s starts the moment anyone clicks Ready,
    # not whatever is left from the original pairing. Fixes the "both readied
    # but match canceled" race where the slower player clicked Ready at T=85s
    # and their partner's poll timed out at T=90s from the OLD matched_at.
    await db.execute(
        text("UPDATE ranked_queue SET matched_at = NOW() WHERE player_id = ANY(:pids)"),
        {"pids": [player.id, entry["matched_with"]]},
    )

    print(f"[QUEUE-READY] {steam_id} ready=true, opp={entry['matched_with']} opp_ready="
          f"{opp['ready'] if opp else 'opp_row_missing'}")

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

        # Pre-create the ranked_series row so /series/active returns it BEFORE game 1
        # ends. submit_match's existing find-or-create logic will reuse it whether the
        # match report's p1/p2 ordering matches our ordering or not. Skip if a row
        # already exists (e.g., re-ready after a brief disconnect).
        existing_series = (await db.execute(
            select(RankedSeries).where(
                RankedSeries.status == "active",
                or_(
                    and_(RankedSeries.player1_id == player.id, RankedSeries.player2_id == opp["player_id"]),
                    and_(RankedSeries.player1_id == opp["player_id"], RankedSeries.player2_id == player.id),
                ),
            )
        )).scalar_one_or_none()
        if existing_series is None:
            existing_series = RankedSeries(
                player1_id=player.id,
                player2_id=opp["player_id"],
                p1_series_wins=0, p2_series_wins=0,
                live_p1_points=0, live_p2_points=0,
                status="active",
            )
            db.add(existing_series)
            await db.flush()  # get the new series_id

        await db.commit()
        return {
            "status": "both_ready",
            "room_name": room_name,
            "photon_region": chosen_region,
            "series_id": str(existing_series.id),
        }

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


@app.get("/api/v1/series/recent", tags=["Discord", "Series"])
async def get_recent_series(
    minutes: int = Query(2, ge=1, le=43200),
    limit: int = Query(20, ge=1, le=200),
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

    # Pull all settled bets for the series in this page in one go (avoids N+1). Joined to
    # bettor + bet-on names so the client can render rows like "AsteRiA bet 500g on Sid → +505g".
    series_ids = [row["series_id"] for row in rows]
    bets_by_series: dict[str, list] = {}
    if series_ids:
        bet_rows = (await db.execute(text(
            "SELECT b.series_id::text AS series_id, b.amount, b.payout, b.odds_multiplier, "
            "       b.settled_at, "
            "       bp.display_name AS bettor_name, bp.steam_id AS bettor_steam_id, "
            "       bo.display_name AS bet_on_name, bo.steam_id AS bet_on_steam_id "
            "FROM bets b "
            "JOIN players bp ON bp.id = b.player_id "
            "JOIN players bo ON bo.id = b.bet_on_player_id "
            "WHERE b.series_id::text = ANY(:ids) "
            "ORDER BY b.settled_at DESC NULLS LAST, b.created_at DESC"
        ), {"ids": series_ids})).mappings().all()
        for br in bet_rows:
            bets_by_series.setdefault(br["series_id"], []).append({
                "bettor_name": br["bettor_name"],
                "bettor_steam_id": br["bettor_steam_id"],
                "amount": br["amount"],
                "payout": br["payout"],
                "odds_multiplier": round(br["odds_multiplier"] or 1.0, 2),
                "bet_on_name": br["bet_on_name"],
                "bet_on_steam_id": br["bet_on_steam_id"],
                "won": (br["payout"] or 0) > br["amount"],
            })

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
            "bets": bets_by_series.get(row["series_id"], []),
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
            # Banned players can't chat. Silently drop — telling them they're banned would
            # encourage griefing on alts. The mod's queue-join 409 is the primary signal.
            if await _is_banned_via_session(steam_id):
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
    # Look up the linked Steam ID and refuse the relay if that player is banned.
    # Without this, a banned player can still chat from Discord (since the WS path
    # is the in-game-only block point). Silent drop matches the WS behavior.
    if discord_id:
        try:
            from database import async_session
            async with async_session() as _bdb:
                row = (await _bdb.execute(
                    text("SELECT steam_id FROM players WHERE discord_id = :d AND deleted_at IS NULL"),
                    {"d": discord_id},
                )).first()
            if row and row[0] and await _is_banned_via_session(row[0]):
                print(f"[CHAT] dropped banned discord chatter discord_id={discord_id} steam={row[0]}")
                return {"status": "banned"}
        except Exception as e:
            print(f"[CHAT] ban-check failed for discord {discord_id}: {e}")
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
# Glicko expectancy — factors in BOTH players' rating deviation (RD) so a
# fresh expert with default RD=350 can't be exploited via "betting against
# the high-rated newbie." When either player has high RD, the rating gap is
# dampened by g(RD) → odds compress toward 50/50.
#
# Formulas (Glicko-2 / Glicko-1 unified):
#   q = ln(10) / 400
#   g(RD) = 1 / sqrt(1 + 3 * q^2 * RD^2 / pi^2)
#   E(a beats b) = 1 / (1 + 10^( g(combined_RD) * (R_b - R_a) / 400 ))
#   combined_RD = sqrt(RD_a^2 + RD_b^2)

import math as _math
_GLICKO_Q = _math.log(10.0) / 400.0


def _glicko_g(rd: float) -> float:
    return 1.0 / _math.sqrt(1.0 + 3.0 * _GLICKO_Q * _GLICKO_Q * rd * rd / (_math.pi * _math.pi))


def _glicko_expectancy(rating_a: float, rd_a: float, rating_b: float, rd_b: float) -> float:
    combined_rd = _math.sqrt(rd_a * rd_a + rd_b * rd_b)
    g = _glicko_g(combined_rd)
    return 1.0 / (1.0 + 10.0 ** (g * (rating_b - rating_a) / 400.0))


def _elo_expectancy(rating_a: float, rating_b: float) -> float:
    """Pure-Elo expectancy. Kept for backward compat with code paths that don't have RD on hand."""
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def _odds_multiplier(bet_on_rating: float, opponent_rating: float,
                      bet_on_rd: float = 80.0, opponent_rd: float = 80.0) -> float:
    """1/p with a 1.01x floor and a dynamic cap. RD-aware in two ways:
       (a) Expectancy uses Glicko g(RD) — high-RD players compress the rating gap
           toward 50/50 since their "true" skill is uncertain.
       (b) The payout CAP scales DOWN as the maximum RD on either side rises, so
           a fresh smurf can't be exploited even at small Elo gaps. With either
           player at default RD=350, the cap drops to 1.0x (no profit possible).
       Defaults to RD=80 (well-established player) for callers without RD."""
    p = _glicko_expectancy(bet_on_rating, bet_on_rd, opponent_rating, opponent_rd)
    if p <= 0.0:
        p = 1e-6  # fall through to the cap branch below
    mult = 1.0 / p

    # Dynamic cap based on the higher RD on either side. Linear ramp from 3x at
    # RD≤100 (well-established) to 1.0x at RD≥300 (new account or high uncertainty).
    max_rd = max(bet_on_rd or 80.0, opponent_rd or 80.0)
    if max_rd <= 100.0:
        cap = 3.0
    elif max_rd >= 300.0:
        cap = 1.0
    else:
        cap = 3.0 - 2.0 * (max_rd - 100.0) / 200.0   # linear: 100→3.0, 300→1.0

    return max(1.01, min(mult, cap))


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


@app.post("/api/v1/players/{steam_id}/active-color", tags=["Shop"])
async def set_active_color(
    steam_id: str,
    item_id: int | None = Query(None, description="Shop item ID, or null to clear"),
    sig: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Legacy single-active-color endpoint (v1.22 and older clients). New clients should
    use /color-toggle instead. Kept so older installs don't break — writes both the single
    active_color_id column AND replaces active_color_ids with a single-element list."""
    result = await _set_active_cosmetic(db, steam_id, "color", "color", item_id, sig)
    # Mirror into the multi-equip array so the two fields stay in sync.
    player = (await db.execute(select(Player).where(Player.steam_id == steam_id))).scalar_one_or_none()
    if player is not None:
        player.active_color_ids = [item_id] if item_id else []
        await db.commit()
    return result


@app.post("/api/v1/players/{steam_id}/active-player-color", tags=["Shop"])
async def set_active_player_color(
    steam_id: str,
    item_id: int | None = Query(None, description="Shop item ID, or null to clear"),
    sig: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Equip / unequip a player body color (kind='player_color'). Single-equip:
    setting a new color displaces the previous one. Pass item_id=null to clear."""
    return await _set_active_cosmetic(db, steam_id, "player_color", "player_color", item_id, sig)


@app.post("/api/v1/players/{steam_id}/color-toggle", tags=["Shop"])
async def toggle_color(
    steam_id: str,
    item_id: int = Query(..., description="Map color shop item ID to toggle on/off"),
    sig: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Toggle a map color (kind='color') in the player's active_color_ids list. Multi-
    equip — several colors can be on at once, and the client cycles between them with
    Left Shift in-game. Requires ownership (or that the item has been purchased)."""
    if not MATCH_HMAC_SECRET:
        raise HTTPException(status_code=503, detail="HMAC not configured")
    expected = hmac.new(
        MATCH_HMAC_SECRET.encode(),
        f"color:{steam_id}:{item_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=403, detail="Invalid signature")

    player = (await db.execute(select(Player).where(Player.steam_id == steam_id))).scalar_one_or_none()
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    item = (await db.execute(select(ShopItem).where(ShopItem.id == item_id))).scalar_one_or_none()
    if item is None or item.kind != "color":
        raise HTTPException(status_code=400, detail="Not a valid map color")

    owned = (await db.execute(
        select(PlayerItem).where(PlayerItem.player_id == player.id, PlayerItem.item_id == item_id)
    )).scalar_one_or_none()
    if owned is None:
        raise HTTPException(status_code=403, detail="Item not owned")

    current = list(player.active_color_ids or [])
    if item_id in current:
        current.remove(item_id)
        action = "removed"
    else:
        current.append(item_id)
        action = "added"
    # Reassign a fresh list so SQLAlchemy flags the ARRAY column as dirty.
    player.active_color_ids = current
    # Keep the legacy single-value column pointing at the first equipped color so any
    # code path still reading active_color_id returns a sensible value.
    player.active_color_id = current[0] if current else None
    await db.commit()
    return {"status": action, "item_id": item_id, "active_ids": current}


@app.post("/api/v1/players/{steam_id}/nametag-toggle", tags=["Shop"])
async def toggle_nametag_style(
    steam_id: str,
    item_id: int = Query(..., description="Nametag shop item ID to toggle on/off"),
    sig: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Toggle a single nametag style (kind='nametag') in the player's active set.
    Stackable — multiple styles can be on at once. Requires ownership."""
    if not MATCH_HMAC_SECRET:
        raise HTTPException(status_code=503, detail="HMAC not configured")
    expected = hmac.new(
        MATCH_HMAC_SECRET.encode(),
        f"nametag:{steam_id}:{item_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=403, detail="Invalid signature")

    player = (await db.execute(select(Player).where(Player.steam_id == steam_id))).scalar_one_or_none()
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    item = (await db.execute(select(ShopItem).where(ShopItem.id == item_id))).scalar_one_or_none()
    if item is None or item.kind != "nametag":
        raise HTTPException(status_code=400, detail="Not a valid nametag style")

    owned = (await db.execute(
        select(PlayerItem).where(PlayerItem.player_id == player.id, PlayerItem.item_id == item_id)
    )).scalar_one_or_none()
    if owned is None:
        raise HTTPException(status_code=403, detail="Item not owned")

    current = list(player.nametag_style_ids or [])
    if item_id in current:
        current.remove(item_id)
        action = "removed"
    else:
        # Subgroup enforcement: nametag SKUs prefixed nametag_color_ / nametag_glow_ /
        # nametag_font_ are single-active within their subgroup. The bare bold/italic/
        # underline/strike SKUs carry no prefix and stay stackable alongside everything.
        subgroup = _nametag_subgroup(item.sku)
        if subgroup is not None:
            # Look up every currently-active nametag item whose sku matches this subgroup
            # and remove them before adding the new one. Single query to resolve ids → skus.
            if current:
                sibling_rows = (await db.execute(
                    select(ShopItem.id, ShopItem.sku).where(ShopItem.id.in_(current))
                )).all()
                for sid, ssku in sibling_rows:
                    if _nametag_subgroup(ssku) == subgroup and sid in current:
                        current.remove(sid)
        current.append(item_id)
        action = "added"
    # Reassign a fresh list so SQLAlchemy flags ARRAY column as dirty.
    player.nametag_style_ids = current
    await db.commit()
    return {"status": action, "item_id": item_id, "active_ids": current}


def _nametag_subgroup(sku: str) -> str | None:
    """Return the subgroup name for a nametag SKU, or None if it's stackable (bold/italic/etc).
    Subgroups are single-active: adding an item from one replaces any existing one.

    Note: "font" (caps/smallcaps/spaced transforms, inline rich text) and "typeface"
    (Impact/Papyrus/Comic/Courier/Script OS-font swaps, local-only render) are deliberately
    separate subgroups so a player can stack e.g. Impact typeface + ALL CAPS simultaneously."""
    if not sku:
        return None
    # Neon items occupy the same single-active slot as plain colors — equipping
    # one displaces any plain `nametag_color_*` (and vice versa). The glow side
    # of a neon rides along automatically, so neon does NOT collide with the
    # separate `nametag_glow_*` subgroup.
    if sku.startswith("nametag_neon_"):
        return "nametag_color"
    for prefix in (
        "nametag_color_",
        "nametag_glow_",
        "nametag_font_",
        "nametag_typeface_",
        "nametag_size_",
    ):
        if sku.startswith(prefix):
            return prefix.rstrip("_")
    return None


async def _set_active_cosmetic(db: AsyncSession, steam_id: str, kind: str, prefix: str, item_id: int | None, sig: str):
    """Shared set-active logic for titles, trails, and colors."""
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

    attr = ("active_title_id" if kind == "title"
            else "active_trail_id" if kind == "trail"
            else "active_color_id" if kind == "color"
            else "active_player_color_id")
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

async def _prune_stale_series(db: AsyncSession) -> int:
    """Mark series abandoned when no match has been reported within 30 min of creation,
    and refund any pending bets on those series. Returns the number of series pruned.
    Called lazily at the start of /series/active so we don't need a separate scheduler."""
    cutoff_min = 30
    stale_rows = (await db.execute(text(
        "SELECT rs.id FROM ranked_series rs "
        "WHERE rs.status = 'active' "
        "  AND rs.created_at < NOW() - (:cutoff_min || ' minutes')::interval "
        "  AND NOT EXISTS (SELECT 1 FROM matches m WHERE m.series_id = rs.id) "
        "LIMIT 50"
    ), {"cutoff_min": str(cutoff_min)})).all()
    if not stale_rows:
        return 0
    pruned = 0
    for (sid,) in stale_rows:
        # Refund bets on this series. Stake was charged via gold_spent at place-time;
        # back it out and add a 'refund_abandoned' gold_transactions entry per bet.
        bets = (await db.execute(
            select(Bet).where(Bet.series_id == sid, Bet.settled_at.is_(None))
        )).scalars().all()
        for b in bets:
            player = (await db.execute(select(Player).where(Player.id == b.player_id))).scalar_one_or_none()
            if player is not None:
                player.gold_spent = max(0, (player.gold_spent or 0) - b.amount)
            db.add(GoldTransaction(
                player_id=b.player_id, amount=b.amount,
                reason="refund_abandoned", reference_id=str(sid),
            ))
            b.settled_at = datetime.now(timezone.utc)
            b.payout = b.amount  # full stake returned
        # Mark the series itself abandoned for the audit trail.
        await db.execute(text(
            "UPDATE ranked_series SET status = 'abandoned', "
            "  invalidated_at = NOW(), invalidation_reason = 'no_match_reported' "
            "WHERE id = :sid"
        ), {"sid": sid})
        pruned += 1
        print(f"[SERIES] abandoned stale series {sid} — refunded {len(bets)} bet(s)")
    if pruned:
        await db.commit()
    return pruned


@app.get("/api/v1/series/active", tags=["Series"])
async def get_active_series(db: AsyncSession = Depends(get_db)):
    """Live (in-progress) ranked series — for the bet UI."""
    # Lazy cleanup: any series older than 30min with zero matches reported gets marked
    # abandoned and bets refunded. Cheap (indexed on status + created_at) and runs only
    # when this endpoint is queried, which is exactly when bettors are looking.
    try:
        await _prune_stale_series(db)
    except Exception as e:
        print(f"[SERIES] prune error: {e}")
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
            gr1.rating_deviation       AS p1_rd,
            gr2.rating_deviation       AS p2_rd,
            rs.p1_series_wins, rs.p2_series_wins,
            rs.live_p1_points, rs.live_p2_points,
            rs.created_at,
            rs.is_private
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
        p1_rd = float(r["p1_rd"] or 350)
        p2_rd = float(r["p2_rd"] or 350)
        live_p1 = r["live_p1_points"] or 0
        live_p2 = r["live_p2_points"] or 0
        # Bets lock when:
        #   - 2+ points scored in game 1 (mystery preserved)
        #   - any game 1 result is in (series_wins > 0)
        #   - both odds offer no profit (both sides ≤1.10x — happens when either player has
        #     RD ≥ 280 → cap clamps low, no point letting players burn gold)
        p1_odds = round(_odds_multiplier(p1_rating, p2_rating, p1_rd, p2_rd), 2)
        p2_odds = round(_odds_multiplier(p2_rating, p1_rating, p2_rd, p1_rd), 2)
        no_profit = max(p1_odds, p2_odds) < 1.10
        score_locked = (live_p1 + live_p2) >= 2 or r["p1_series_wins"] > 0 or r["p2_series_wins"] > 0
        is_private = bool(r["is_private"])
        # Private rooms surface in /series/active right at game start with no
        # usable pre-game betting window, so we lock bets immediately and the
        # client renders a PRIVATE tag instead of bettable odds.
        bets_locked = no_profit or score_locked or is_private
        if is_private:
            lock_reason = "private_room"
        elif score_locked:
            lock_reason = "game_in_progress"
        elif no_profit:
            lock_reason = "no_meaningful_odds"
        else:
            lock_reason = None
        series.append({
            "series_id": r["series_id"],
            "p1_steam_id": r["p1_steam_id"],
            "p1_name": r["p1_name"],
            "p1_rating": p1_rating,
            "p1_rd": round(p1_rd, 1),
            "p1_wins": r["p1_series_wins"],
            "p1_odds": p1_odds,
            "p2_steam_id": r["p2_steam_id"],
            "p2_name": r["p2_name"],
            "p2_rating": p2_rating,
            "p2_rd": round(p2_rd, 1),
            "p2_wins": r["p2_series_wins"],
            "p2_odds": p2_odds,
            "live_p1_points": live_p1,
            "live_p2_points": live_p2,
            "bets_locked": bets_locked,
            "lock_reason": lock_reason,
            "is_private": is_private,
            "started_at": r["created_at"].isoformat() if r["created_at"] else None,
        })
    return {"series": series}


@app.get("/api/v1/team/series/active", tags=["Team Matches"])
async def get_active_team_series(db: AsyncSession = Depends(get_db)):
    """Live (in-progress) 2v2 team series — for the bet UI's 4-player panel."""
    rows = (await db.execute(text("""
        SELECT
            ts.id::text                AS series_id,
            ts.t1a_id, ts.t1b_id, ts.t2a_id, ts.t2b_id,
            p1a.steam_id  AS t1a_steam, p1a.display_name AS t1a_name,
            p1b.steam_id  AS t1b_steam, p1b.display_name AS t1b_name,
            p2a.steam_id  AS t2a_steam, p2a.display_name AS t2a_name,
            p2b.steam_id  AS t2b_steam, p2b.display_name AS t2b_name,
            ts.t1_series_wins, ts.t2_series_wins,
            ts.created_at, ts.dc_grace_until,
            -- Team-aggregated 2v2 ratings (avg of the 2 members), 1v1 fallback for low-confidence.
            (SELECT AVG(CASE WHEN g2.completed_series >= :trust THEN g2.rating ELSE g1.rating END)
               FROM glicko_ratings_2v2 g2
               JOIN glicko_ratings g1 ON g1.player_id = g2.player_id
              WHERE g2.player_id IN (ts.t1a_id, ts.t1b_id))         AS t1_avg_rating,
            (SELECT AVG(CASE WHEN g2.completed_series >= :trust THEN g2.rating ELSE g1.rating END)
               FROM glicko_ratings_2v2 g2
               JOIN glicko_ratings g1 ON g1.player_id = g2.player_id
              WHERE g2.player_id IN (ts.t2a_id, ts.t2b_id))         AS t2_avg_rating,
            (SELECT AVG(g2.rating_deviation)
               FROM glicko_ratings_2v2 g2
              WHERE g2.player_id IN (ts.t1a_id, ts.t1b_id))         AS t1_avg_rd,
            (SELECT AVG(g2.rating_deviation)
               FROM glicko_ratings_2v2 g2
              WHERE g2.player_id IN (ts.t2a_id, ts.t2b_id))         AS t2_avg_rd
        FROM team_series ts
        JOIN players p1a ON p1a.id = ts.t1a_id
        JOIN players p1b ON p1b.id = ts.t1b_id
        JOIN players p2a ON p2a.id = ts.t2a_id
        JOIN players p2b ON p2b.id = ts.t2b_id
        WHERE ts.status IN ('active', 'dc_paused')
          AND ts.created_at > NOW() - INTERVAL '2 hours'
        ORDER BY ts.created_at DESC
        LIMIT 20
    """), {"trust": TEAM_TRUST_2V2_RATING_AFTER})).mappings().all()

    series = []
    for r in rows:
        t1_r = float(r["t1_avg_rating"] or 1500.0)
        t2_r = float(r["t2_avg_rating"] or 1500.0)
        t1_rd = float(r["t1_avg_rd"] or 350.0)
        t2_rd = float(r["t2_avg_rd"] or 350.0)
        t1_odds = round(_odds_multiplier(t1_r, t2_r, t1_rd, t2_rd), 2)
        t2_odds = round(_odds_multiplier(t2_r, t1_r, t2_rd, t1_rd), 2)
        no_profit = max(t1_odds, t2_odds) < 1.10
        # Lock when series has any games done (t1_series_wins > 0 OR t2 > 0)
        # — the "is the favorite holding up" mystery has been resolved.
        score_locked = (r["t1_series_wins"] or 0) > 0 or (r["t2_series_wins"] or 0) > 0
        bets_locked = no_profit or score_locked
        lock_reason = "game_in_progress" if score_locked else ("no_meaningful_odds" if no_profit else None)
        series.append({
            "series_id": r["series_id"],
            "t1a_steam": r["t1a_steam"], "t1a_name": r["t1a_name"],
            "t1b_steam": r["t1b_steam"], "t1b_name": r["t1b_name"],
            "t2a_steam": r["t2a_steam"], "t2a_name": r["t2a_name"],
            "t2b_steam": r["t2b_steam"], "t2b_name": r["t2b_name"],
            "t1_rating": int(round(t1_r)), "t2_rating": int(round(t2_r)),
            "t1_wins": r["t1_series_wins"] or 0,
            "t2_wins": r["t2_series_wins"] or 0,
            "t1_odds": t1_odds, "t2_odds": t2_odds,
            "bets_locked": bets_locked,
            "lock_reason": lock_reason,
            "started_at": r["created_at"].isoformat() if r["created_at"] else None,
            "dc_grace_until": r["dc_grace_until"].isoformat() if r["dc_grace_until"] else None,
        })
    return {"series": series}


@app.post("/api/v1/series/preflight", tags=["Series"])
async def series_preflight(
    p1_steam_id: str = Query(...),
    p2_steam_id: str = Query(...),
    sig: str = Query(...),
    p1_name: str | None = Query(None, max_length=64),
    p2_name: str | None = Query(None, max_length=64),
    db: AsyncSession = Depends(get_db),
):
    """Pre-create a ranked_series for two players who are about to play a
    ranked match in a private room. Idempotent — if an active series for the
    pair already exists, returns its id. Used to surface non-queue ranked
    matches in /series/active immediately rather than only after the first
    match completes (the prior visibility gap that left private-room games
    invisible until ~5 minutes in).

    HMAC signs 'preflight:{lower}:{higher}' where the two steam IDs are sorted
    so either player can compute it without knowing who's p1/p2 server-side.
    Server returns the series_id which the client then uses for live-points
    reports during game 1."""
    if not MATCH_HMAC_SECRET:
        raise HTTPException(status_code=503, detail="HMAC not configured")
    if p1_steam_id == p2_steam_id:
        raise HTTPException(status_code=400, detail="Players must be distinct")
    a, b = sorted([p1_steam_id, p2_steam_id])
    expected = hmac.new(
        MATCH_HMAC_SECRET.encode(),
        f"preflight:{a}:{b}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=403, detail="Invalid signature")

    # Use the caller-provided NickNames so first-time-seen players don't
    # render as their bare Steam ID in /series/active until their next
    # /stats refresh. Falls back to the steam_id if the client didn't pass
    # a name (older mod build).
    p1 = await get_or_create_player(db, p1_steam_id, p1_name or p1_steam_id)
    p2 = await get_or_create_player(db, p2_steam_id, p2_name or p2_steam_id)
    # Both players reached preflight via their own mod's GameStateWatcher,
    # so both are confirmed mod users.
    await _mark_mod_seen(db, p1)
    await _mark_mod_seen(db, p2)
    if not p1.ranked_enabled or not p2.ranked_enabled:
        # Don't create series for casual matches. Client should re-call after
        # both have toggled ranked on.
        await db.commit()
        return {"status": "skipped", "reason": "one_or_both_not_ranked"}

    # Idempotent: reuse existing active series between this pair.
    existing = (await db.execute(
        select(RankedSeries).where(
            RankedSeries.status == "active",
            or_(
                and_(RankedSeries.player1_id == p1.id, RankedSeries.player2_id == p2.id),
                and_(RankedSeries.player1_id == p2.id, RankedSeries.player2_id == p1.id),
            ),
        )
    )).scalar_one_or_none()
    if existing is not None:
        await db.commit()
        return {"status": "exists", "series_id": str(existing.id)}

    series = RankedSeries(
        player1_id=p1.id, player2_id=p2.id,
        p1_series_wins=0, p2_series_wins=0,
        live_p1_points=0, live_p2_points=0,
        status="active",
    )
    db.add(series)
    await db.flush()
    # Mark as private-room so Live Ranked Games can render it with the
    # "PRIVATE — no bets" tag (preflight surfaces these right at game
    # start with no usable betting window).
    await db.execute(
        text("UPDATE ranked_series SET is_private = TRUE WHERE id = :sid"),
        {"sid": series.id},
    )
    await db.commit()
    print(f"[SERIES-PREFLIGHT] created series {series.id} for {p1_steam_id} vs {p2_steam_id} (private room)")
    return {"status": "created", "series_id": str(series.id)}


@app.post("/api/v1/series/{series_id}/live-points", tags=["Series"])
async def update_live_points(
    series_id: str,
    p1_points: int = Query(..., ge=0, le=10),
    p2_points: int = Query(..., ge=0, le=10),
    reporter_steam_id: str = Query(...),
    sig: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Reporter posts current game-1 point counts so betting can lock when sum >= 2.
    HMAC signs 'live-points:{series_id}:{reporter_steam_id}:{p1_points}:{p2_points}'."""
    if not MATCH_HMAC_SECRET:
        raise HTTPException(status_code=503, detail="HMAC not configured")
    expected = hmac.new(
        MATCH_HMAC_SECRET.encode(),
        f"live-points:{series_id}:{reporter_steam_id}:{p1_points}:{p2_points}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        sid = UUID(series_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid series_id")

    series = (await db.execute(select(RankedSeries).where(RankedSeries.id == sid))).scalar_one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Series not found")

    # Reporter must be a participant — only the two players in the match should report.
    reporter = (await db.execute(select(Player).where(Player.steam_id == reporter_steam_id))).scalar_one_or_none()
    if reporter is None or reporter.id not in (series.player1_id, series.player2_id):
        raise HTTPException(status_code=403, detail="Reporter is not in this series")

    # Map reporter's p1/p2 perspective to series' p1/p2 ordering.
    if reporter.id == series.player1_id:
        new_p1, new_p2 = p1_points, p2_points
    else:
        new_p1, new_p2 = p2_points, p1_points

    # Monotonic: only ever increase. Prevents a stale or out-of-order report from
    # un-locking betting after the cutoff has been hit.
    series.live_p1_points = max(series.live_p1_points or 0, new_p1)
    series.live_p2_points = max(series.live_p2_points or 0, new_p2)
    await db.commit()
    return {
        "status": "ok",
        "live_p1_points": series.live_p1_points,
        "live_p2_points": series.live_p2_points,
        "bets_locked": (series.live_p1_points + series.live_p2_points) >= 2,
    }


@app.post("/api/v1/discord-bets", tags=["Betting"])
async def place_discord_bet(
    discord_user_id: str = Query(..., max_length=32),
    series_id: str = Query(...),
    bet_on_steam_id: str = Query(..., description="Which player's Steam ID to bet on"),
    amount: int = Query(..., ge=1, le=100000),
    db: AsyncSession = Depends(get_db),
    x_internal_key: str | None = Header(None, alias="X-Internal-Key"),
):
    """Bot-side bet placement. Authenticated via X-Internal-Key. Resolves the
    Discord user to a linked player and places a bet on their behalf using
    the same validation pipeline as the in-game /bets endpoint (banned check,
    odds floor, lock checks, gold balance, idempotent one-bet-per-series)."""
    expected = os.getenv("API_SECRET_KEY", "")
    if not expected or x_internal_key != expected:
        raise HTTPException(403, "Internal endpoint")
    bettor = (await db.execute(
        select(Player).where(Player.discord_id == discord_user_id)
    )).scalar_one_or_none()
    if bettor is None:
        raise HTTPException(404, "Discord account not linked to any player. Use !link from in-game first.")
    # Reuse the in-game /bets validation by re-signing internally — keeps
    # the bet-placement code path single-sourced.
    sig = hmac.new(
        MATCH_HMAC_SECRET.encode(),
        f"bet:{bettor.steam_id}:{series_id}:{bet_on_steam_id}:{amount}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return await place_bet(
        steam_id=bettor.steam_id, series_id=series_id,
        bet_on_steam_id=bet_on_steam_id, amount=amount, sig=sig, db=db,
    )


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

    # Banned players can't bet (alongside queue + chat).
    await _check_ban_or_raise(db, steam_id)

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
    # Bet cutoff: once 2 points are scored in game 1, betting locks. Preserves the
    # "is the favorite actually going to win" mystery and prevents free-money bets
    # placed mid-game once an outcome is obvious. Game 1 ending (any p?_series_wins
    # > 0) also locks via the wins check above.
    if (series.live_p1_points or 0) + (series.live_p2_points or 0) >= 2:
        raise HTTPException(status_code=409, detail="Bets locked — game 1 has progressed past 2 points")

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

    # Snapshot current ratings + RD for odds. RD-aware so a fresh expert (default RD 350)
    # can't be exploited via bet-against — odds compress toward 50/50 until they play more.
    ratings = (await db.execute(text(
        "SELECT player_id, rating, rating_deviation FROM glicko_ratings "
        "WHERE player_id = :p1 OR player_id = :p2"
    ), {"p1": series.player1_id, "p2": series.player2_id})).mappings().all()
    rmap = {r["player_id"]: (float(r["rating"] or 1500), float(r["rating_deviation"] or 350)) for r in ratings}
    bet_on_r, bet_on_rd = rmap.get(bet_on.id, (1500.0, 350.0))
    other_id = series.player2_id if bet_on.id == series.player1_id else series.player1_id
    other_r, other_rd = rmap.get(other_id, (1500.0, 350.0))
    mult = _odds_multiplier(bet_on_r, other_r, bet_on_rd, other_rd)
    # Defense-in-depth: refuse bets that have no meaningful upside. The /series/active
    # response already hides the wager buttons in this case but a malicious client could
    # still POST directly. 1.10x = 10% profit minimum.
    if mult < 1.10:
        raise HTTPException(status_code=409,
            detail="Bets restricted — odds offer no meaningful profit (player rating still uncertain)")

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


@app.post("/api/v1/team-bets", tags=["Betting"])
async def place_team_bet(
    steam_id: str = Query(...),
    team_series_id: str = Query(...),
    bet_on_team: int = Query(..., ge=1, le=2),
    amount: int = Query(..., ge=1, le=100000),
    sig: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Place a bet on a 2v2 team_series. HMAC over
    `team-bet:{steam_id}:{team_series_id}:{bet_on_team}:{amount}`.
    Mirrors `place_bet` for 1v1 — same odds-uncertainty floor (>=1.10x),
    same one-bet-per-series-per-player rule, same gold debit-now /
    credit-on-settle flow."""
    if not MATCH_HMAC_SECRET:
        raise HTTPException(status_code=503, detail="HMAC not configured")
    expected = hmac.new(
        MATCH_HMAC_SECRET.encode(),
        f"team-bet:{steam_id}:{team_series_id}:{bet_on_team}:{amount}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=403, detail="Invalid signature")

    await _check_ban_or_raise(db, steam_id)
    bettor = (await db.execute(select(Player).where(Player.steam_id == steam_id))).scalar_one_or_none()
    if bettor is None:
        raise HTTPException(status_code=404, detail="Player not found")

    try:
        sid = UUID(team_series_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid team_series_id")
    series = (await db.execute(text("""
        SELECT id, status, t1a_id, t1b_id, t2a_id, t2b_id, t1_series_wins, t2_series_wins
          FROM team_series WHERE id = :sid
    """), {"sid": sid})).mappings().first()
    if series is None:
        raise HTTPException(status_code=404, detail="Team series not found")
    if series["status"] != "active":
        raise HTTPException(status_code=409, detail=f"Series is {series['status']}")
    if (series["t1_series_wins"] or 0) >= 2 or (series["t2_series_wins"] or 0) >= 2:
        raise HTTPException(status_code=409, detail="Series already effectively concluded")

    # Bettor can't be a participant.
    if bettor.id in (series["t1a_id"], series["t1b_id"], series["t2a_id"], series["t2b_id"]):
        raise HTTPException(status_code=409, detail="Cannot bet on your own match")

    # One bet per series per player.
    existing = (await db.execute(text("""
        SELECT 1 FROM team_bets WHERE player_id = :pid AND team_series_id = :sid
    """), {"pid": bettor.id, "sid": sid})).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Already bet on this series")

    balance = (bettor.gold_earned or 0) - (bettor.gold_spent or 0)
    if balance < amount:
        raise HTTPException(status_code=402, detail=f"Insufficient gold: have {balance}, need {amount}")

    # Compute team-aggregated odds. Each team's "rating" for odds is the
    # average of its 2 members' 2v2 ratings (RD-weighted falls back to 1v1
    # via _team_balance_rating for low-confidence accounts).
    pair_ids = [series["t1a_id"], series["t1b_id"], series["t2a_id"], series["t2b_id"]]
    g_rows = (await db.execute(text("""
        SELECT g2.player_id, g2.rating, g2.rating_deviation, g2.completed_series,
               g.rating AS rating_1v1
          FROM glicko_ratings_2v2 g2
          JOIN glicko_ratings g ON g.player_id = g2.player_id
         WHERE g2.player_id = ANY(:pids)
    """), {"pids": pair_ids})).mappings().all()
    rmap = {r["player_id"]: r for r in g_rows}

    def team_balance(pid):
        r = rmap.get(pid)
        if r is None:
            return 1500.0, 350.0
        cs = int(r["completed_series"] or 0)
        rd = float(r["rating_deviation"] or 350.0)
        rating = float(r["rating"] if cs >= TEAM_TRUST_2V2_RATING_AFTER else (r["rating_1v1"] or 1500.0))
        return rating, rd

    t1_ratings = [team_balance(series["t1a_id"]), team_balance(series["t1b_id"])]
    t2_ratings = [team_balance(series["t2a_id"]), team_balance(series["t2b_id"])]
    t1_avg = sum(r[0] for r in t1_ratings) / 2
    t2_avg = sum(r[0] for r in t2_ratings) / 2
    t1_rd_avg = sum(r[1] for r in t1_ratings) / 2
    t2_rd_avg = sum(r[1] for r in t2_ratings) / 2

    if bet_on_team == 1:
        mult = _odds_multiplier(t1_avg, t2_avg, t1_rd_avg, t2_rd_avg)
    else:
        mult = _odds_multiplier(t2_avg, t1_avg, t2_rd_avg, t1_rd_avg)
    if mult < 1.10:
        raise HTTPException(status_code=409,
            detail="Bets restricted — odds offer no meaningful profit (low team rating confidence)")

    bettor.gold_spent = (bettor.gold_spent or 0) + amount
    db.add(GoldTransaction(
        player_id=bettor.id, amount=-amount,
        reason="team_bet_stake", reference_id=team_series_id,
    ))
    await db.execute(text("""
        INSERT INTO team_bets (player_id, team_series_id, bet_on_team, amount, odds_multiplier)
        VALUES (:pid, :sid, :tm, :amt, :mult)
    """), {"pid": bettor.id, "sid": sid, "tm": bet_on_team, "amt": amount, "mult": mult})
    await db.commit()
    return {
        "status": "placed",
        "amount": amount,
        "bet_on_team": bet_on_team,
        "odds_multiplier": round(mult, 2),
        "potential_payout": int(amount * mult),
    }


@app.get("/api/v1/players/{steam_id}/team-bets", tags=["Betting"])
async def get_player_team_bets(
    steam_id: str,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Player's recent 2v2 bets."""
    rows = (await db.execute(text("""
        SELECT
            b.id, b.amount, b.odds_multiplier, b.created_at, b.settled_at,
            b.payout, b.bet_on_team,
            b.team_series_id::text AS series_id,
            ts.status AS series_status,
            ts.winner_team AS series_winner_team,
            ts.t1_series_wins, ts.t2_series_wins
        FROM team_bets b
        JOIN players p ON p.id = b.player_id
        JOIN team_series ts ON ts.id = b.team_series_id
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
                "series_id": r["series_id"],
                "bet_on_team": r["bet_on_team"],
                "series_status": r["series_status"],
                "series_winner_team": r["series_winner_team"],
                "series_score": f"{r['t1_series_wins']}-{r['t2_series_wins']}",
            }
            for r in rows
        ]
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
            b.series_id::text AS series_id,
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
                "series_id": r["series_id"],
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
# Module-level so admin_grant_achievement (defined later) can reference it without
# falling back to a NameError. unlock_achievement uses the same value. Bumped 25→100 in
# v1.22.6 — achievements are rare events and 25g felt token; 100g actually buys something.
ACHIEVEMENT_GOLD = 100

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
    await _mark_mod_seen(db, player)

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
    # with the shop rollout. ACHIEVEMENT_GOLD is now module-level so admin_grant_achievement
    # can reuse the same constant without a NameError.
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


# ── Routes: Admin ────────────────────────────────────────────
#
# Auth: every mutating admin endpoint requires
#   admin_steam_id  — must be in admin_users
#   hmac_signature  — HMAC-SHA256 over `admin:{admin_steam_id}:{action}:{target}` using MATCH_HMAC_SECRET
# Banning is enforced at queue join, /chat/post, and /bets POST via _check_ban_or_raise.

def _admin_canonical(admin_steam_id: str, action: str, target: str = "") -> str:
    return f"admin:{admin_steam_id}:{action}:{target or ''}"


def _verify_admin_hmac(admin_steam_id: str, action: str, target: str, signature):
    if not MATCH_HMAC_SECRET:
        return True
    if not signature:
        return False
    expected = hmac.new(
        MATCH_HMAC_SECRET.encode(),
        _admin_canonical(admin_steam_id, action, target).encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature, expected)


async def _is_admin(db: AsyncSession, steam_id: str) -> bool:
    if not steam_id:
        return False
    r = await db.execute(select(AdminUser).where(AdminUser.steam_id == steam_id))
    return r.scalar_one_or_none() is not None


async def _require_admin(db: AsyncSession, admin_steam_id: str, action: str, target: str, signature) -> None:
    if not await _is_admin(db, admin_steam_id):
        raise HTTPException(403, "Not an admin")
    if not _verify_admin_hmac(admin_steam_id, action, target, signature):
        raise HTTPException(403, "Bad admin signature")


async def _is_banned(db: AsyncSession, steam_id: str):
    if not steam_id:
        return None
    r = await db.execute(text(
        "SELECT reason FROM player_bans WHERE steam_id = :sid AND unbanned_at IS NULL "
        "ORDER BY banned_at DESC LIMIT 1"
    ), {"sid": steam_id})
    row = r.first()
    return row[0] if row else None


async def _check_ban_or_raise(db: AsyncSession, steam_id: str) -> None:
    reason = await _is_banned(db, steam_id)
    if reason:
        raise HTTPException(status_code=409, detail=f"Banned: {reason}")


async def _is_banned_via_session(steam_id: str) -> bool:
    """Standalone version for code paths that don't have a Depends-injected session
    (e.g., the chat WebSocket handler). Opens its own short-lived session."""
    from database import async_session
    if not steam_id:
        return False
    try:
        async with async_session() as db:
            return (await _is_banned(db, steam_id)) is not None
    except Exception as e:
        print(f"[BAN] check error: {e}")
        return False


@app.get("/api/v1/admin/check-status", tags=["Admin"])
async def admin_check_status(steam_id: str = Query(...), db: AsyncSession = Depends(get_db)):
    return {"is_admin": await _is_admin(db, steam_id)}


@app.get("/api/v1/admin/flagged-matches", tags=["Admin"])
async def admin_list_flagged(
    admin_steam_id: str = Query(...),
    hmac_signature: str = Query(None),
    include_reviewed: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    await _require_admin(db, admin_steam_id, "list_flagged", "", hmac_signature)
    where = "" if include_reviewed else "WHERE fm.reviewed_at IS NULL"
    rows = (await db.execute(text(
        "SELECT fm.id, fm.match_id, fm.series_id, fm.flag_reason, fm.flag_details, fm.auto_invalidated, "
        "       fm.player_steam_ids, fm.reviewed_at, fm.review_action, fm.created_at, "
        "       m.is_ranked, m.invalidated_at, m.invalidation_reason, "
        "       COALESCE(m.duration_seconds, m.match_duration) AS duration, "
        "       p1.display_name AS p1_name, p2.display_name AS p2_name "
        "FROM flagged_matches fm "
        "JOIN matches m ON m.id = fm.match_id "
        "JOIN players p1 ON p1.id = m.player1_id "
        "JOIN players p2 ON p2.id = m.player2_id "
        + where + " "
        "ORDER BY fm.created_at DESC LIMIT :lim OFFSET :off"
    ), {"lim": limit, "off": offset})).mappings().all()
    return {"flags": [
        {
            "id": str(r["id"]),
            "match_id": str(r["match_id"]),
            "series_id": str(r["series_id"]) if r["series_id"] else None,
            "flag_reason": r["flag_reason"],
            "flag_details": r["flag_details"],
            "auto_invalidated": r["auto_invalidated"],
            "match_invalidated": r["invalidated_at"] is not None,
            "match_invalidation_reason": r["invalidation_reason"],
            "player_steam_ids": r["player_steam_ids"],
            "p1_name": r["p1_name"],
            "p2_name": r["p2_name"],
            "is_ranked": r["is_ranked"],
            "duration_seconds": r["duration"],
            "reviewed_at": r["reviewed_at"].isoformat() if r["reviewed_at"] else None,
            "review_action": r["review_action"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        } for r in rows
    ]}


@app.get("/api/v1/admin/banned-users", tags=["Admin"])
async def admin_list_bans(
    admin_steam_id: str = Query(...),
    hmac_signature: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    await _require_admin(db, admin_steam_id, "list_bans", "", hmac_signature)
    rows = (await db.execute(text(
        "SELECT pb.id, pb.steam_id, pb.reason, pb.banned_by_steam_id, pb.banned_at, "
        "       pb.unbanned_at, p.display_name "
        "FROM player_bans pb "
        "LEFT JOIN players p ON p.steam_id = pb.steam_id "
        "WHERE pb.unbanned_at IS NULL "
        "ORDER BY pb.banned_at DESC"
    ))).mappings().all()
    return {"bans": [
        {
            "id": str(r["id"]),
            "steam_id": r["steam_id"],
            "display_name": r["display_name"],
            "reason": r["reason"],
            "banned_by_steam_id": r["banned_by_steam_id"],
            "banned_at": r["banned_at"].isoformat() if r["banned_at"] else None,
        } for r in rows
    ]}


class _AdminBanReq(BaseModel):
    admin_steam_id: str
    target_steam_id: str
    reason: str = "violation"
    hmac_signature: str | None = None


@app.post("/api/v1/admin/ban", tags=["Admin"])
async def admin_ban(req: _AdminBanReq, db: AsyncSession = Depends(get_db)):
    await _require_admin(db, req.admin_steam_id, "ban", req.target_steam_id, req.hmac_signature)
    existing = await _is_banned(db, req.target_steam_id)
    if existing:
        return {"status": "already_banned", "reason": existing}
    db.add(PlayerBan(steam_id=req.target_steam_id, reason=req.reason[:256], banned_by_steam_id=req.admin_steam_id))
    db.add(AdminAction(
        admin_steam_id=req.admin_steam_id, action="ban", target_steam_id=req.target_steam_id,
        details={"reason": req.reason},
    ))
    await db.commit()
    return {"status": "banned", "steam_id": req.target_steam_id, "reason": req.reason}


class _AdminUnbanReq(BaseModel):
    admin_steam_id: str
    target_steam_id: str
    hmac_signature: str | None = None


@app.post("/api/v1/admin/unban", tags=["Admin"])
async def admin_unban(req: _AdminUnbanReq, db: AsyncSession = Depends(get_db)):
    await _require_admin(db, req.admin_steam_id, "unban", req.target_steam_id, req.hmac_signature)
    res = await db.execute(text(
        "UPDATE player_bans SET unbanned_at = NOW(), unbanned_by_steam_id = :admin "
        "WHERE steam_id = :sid AND unbanned_at IS NULL"
    ), {"admin": req.admin_steam_id, "sid": req.target_steam_id})
    db.add(AdminAction(
        admin_steam_id=req.admin_steam_id, action="unban", target_steam_id=req.target_steam_id,
        details={"rows": res.rowcount},
    ))
    await db.commit()
    return {"status": "unbanned", "steam_id": req.target_steam_id, "rows": res.rowcount}


class _AdminGrantAchReq(BaseModel):
    admin_steam_id: str
    target_steam_id: str
    achievement_key: str
    hmac_signature: str | None = None


@app.post("/api/v1/admin/grant-achievement", tags=["Admin"])
async def admin_grant_achievement(req: _AdminGrantAchReq, db: AsyncSession = Depends(get_db)):
    await _require_admin(db, req.admin_steam_id, "grant_achievement", req.target_steam_id, req.hmac_signature)
    if req.achievement_key not in ACHIEVEMENT_DEFS:
        raise HTTPException(400, f"Unknown achievement: {req.achievement_key}")
    target = (await db.execute(select(Player).where(Player.steam_id == req.target_steam_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(404, "Target player not found")
    existing = (await db.execute(
        select(PlayerAchievement).where(
            PlayerAchievement.player_id == target.id,
            PlayerAchievement.achievement_key == req.achievement_key,
        )
    )).scalar_one_or_none()
    if existing is not None:
        return {"status": "already_unlocked"}
    db.add(PlayerAchievement(player_id=target.id, achievement_key=req.achievement_key))
    target.gold_earned = (target.gold_earned or 0) + ACHIEVEMENT_GOLD
    db.add(GoldTransaction(
        player_id=target.id, amount=ACHIEVEMENT_GOLD,
        reason="achievement", reference_id=req.achievement_key,
    ))
    db.add(AdminAction(
        admin_steam_id=req.admin_steam_id, action="grant_achievement",
        target_steam_id=req.target_steam_id,
        details={"achievement_key": req.achievement_key, "gold_awarded": ACHIEVEMENT_GOLD},
    ))
    await db.commit()
    return {"status": "granted", "achievement_key": req.achievement_key, "gold_awarded": ACHIEVEMENT_GOLD}


class _AdminReverseSeriesReq(BaseModel):
    admin_steam_id: str
    series_id: str
    reason: str = "admin_reverse"
    hmac_signature: str | None = None


@app.post("/api/v1/admin/reverse-series", tags=["Admin"])
async def admin_reverse_series(req: _AdminReverseSeriesReq, db: AsyncSession = Depends(get_db)):
    await _require_admin(db, req.admin_steam_id, "reverse_series", req.series_id, req.hmac_signature)
    series = (await db.execute(select(RankedSeries).where(RankedSeries.id == req.series_id))).scalar_one_or_none()
    if series is None:
        raise HTTPException(404, "Series not found")
    if series.invalidated_at is not None:
        return {"status": "already_invalidated"}

    for pid, rc in [(series.player1_id, series.p1_rating_change),
                    (series.player2_id, series.p2_rating_change)]:
        if rc is None:
            continue
        g = (await db.execute(select(GlickoRating).where(GlickoRating.player_id == pid))).scalar_one_or_none()
        if g is not None:
            g.rating = float(g.rating) - float(rc)
            g.updated_at = datetime.now(timezone.utc)

    txns = (await db.execute(
        select(GoldTransaction).where(
            GoldTransaction.reason == "series_win",
            GoldTransaction.reference_id == str(series.id),
        )
    )).scalars().all()
    for tx in txns:
        db.add(GoldTransaction(
            player_id=tx.player_id, amount=-tx.amount,
            reason="reversal", reference_id=str(series.id),
        ))
        player = (await db.execute(select(Player).where(Player.id == tx.player_id))).scalar_one_or_none()
        if player is not None:
            player.gold_earned = max(0, (player.gold_earned or 0) - tx.amount)

    matches_in_series = (await db.execute(select(Match).where(Match.series_id == series.id))).scalars().all()
    for m in matches_in_series:
        if m.invalidated_at is not None:
            continue
        m.invalidated_at = datetime.now(timezone.utc)
        m.invalidation_reason = "admin_reverse"
        await _reverse_match_gold_xp(db, m)

    series.invalidated_at = datetime.now(timezone.utc)
    series.invalidation_reason = req.reason[:64]

    db.add(AdminAction(
        admin_steam_id=req.admin_steam_id, action="reverse_series",
        target_series_id=series.id,
        details={"reason": req.reason, "matches_reversed": len(matches_in_series)},
    ))
    await db.commit()
    return {"status": "reversed", "series_id": req.series_id, "matches_reversed": len(matches_in_series)}


class _AdminReviewFlagReq(BaseModel):
    admin_steam_id: str
    flag_id: str
    review_action: str
    hmac_signature: str | None = None


@app.post("/api/v1/admin/review-flag", tags=["Admin"])
async def admin_review_flag(req: _AdminReviewFlagReq, db: AsyncSession = Depends(get_db)):
    await _require_admin(db, req.admin_steam_id, "review_flag", req.flag_id, req.hmac_signature)
    if req.review_action not in ("confirmed_cheat", "false_positive"):
        raise HTTPException(400, "review_action must be 'confirmed_cheat' or 'false_positive'")
    fm = (await db.execute(select(FlaggedMatch).where(FlaggedMatch.id == req.flag_id))).scalar_one_or_none()
    if fm is None:
        raise HTTPException(404, "Flag not found")
    fm.reviewed_at = datetime.now(timezone.utc)
    fm.reviewed_by_steam_id = req.admin_steam_id
    fm.review_action = req.review_action
    if req.review_action == "false_positive" and fm.auto_invalidated:
        m = (await db.execute(select(Match).where(Match.id == fm.match_id))).scalar_one_or_none()
        if m is not None and m.invalidated_at is not None:
            m.invalidated_at = None
            m.invalidation_reason = None
    db.add(AdminAction(
        admin_steam_id=req.admin_steam_id, action="flag_review",
        target_match_id=fm.match_id,
        details={"flag_id": req.flag_id, "review_action": req.review_action},
    ))
    await db.commit()
    return {"status": "reviewed", "flag_id": req.flag_id, "review_action": req.review_action}


# ── Maintenance mode endpoints ───────────────────────────────────
# Called by the deploy script to enter maintenance ~30s before docker-compose recreate,
# so clients see clean 503 + Retry-After:30 instead of connection-refused. Authed via
# X-Internal-Key — same secret the bot uses for /chat/post.

@app.post("/api/v1/admin/maintenance/start", tags=["Admin"])
async def maintenance_start(
    x_internal_key: str | None = Header(None, alias="X-Internal-Key"),
    broadcast: bool = Query(True, description="Also post a chat-bridge notice to the in-game/Discord chat"),
):
    """Flip the API into maintenance mode. Non-bypass, non-internal requests now 503."""
    expected = os.getenv("API_SECRET_KEY", "")
    if not expected or x_internal_key != expected:
        raise HTTPException(status_code=403, detail="Invalid internal key")
    global _in_maintenance
    _in_maintenance = True
    print("[MAINT] Entered maintenance mode — non-bypass requests will 503 with Retry-After:30")
    if broadcast:
        # Use the existing chat broadcast pipeline so both in-game players and Discord see the
        # notice. The chat WS subscribers will receive immediately; the bot relays to Discord.
        try:
            now = datetime.now(timezone.utc).isoformat()
            await chat_manager.broadcast({
                # source="ingame" so the bot's existing ingame→Discord forwarder picks this up.
                # source="system" would be filtered out and never reach #scr-discussion.
                "source": "ingame",
                "steam_id": "_server",
                "display_name": "[server]",
                "message": "Server restarting in ~30 seconds — match reports + bets will resume automatically.",
                "rating": None,
                "title": None,
                "title_color": None,
                "timestamp": now,
            })
        except Exception as e:
            print(f"[MAINT] broadcast failed: {e}")
    return {"status": "maintenance_on"}


@app.post("/api/v1/admin/maintenance/stop", tags=["Admin"])
async def maintenance_stop(
    x_internal_key: str | None = Header(None, alias="X-Internal-Key"),
):
    """Manually clear maintenance mode without restarting (rarely needed — fresh containers
    boot with _in_maintenance=False)."""
    expected = os.getenv("API_SECRET_KEY", "")
    if not expected or x_internal_key != expected:
        raise HTTPException(status_code=403, detail="Invalid internal key")
    global _in_maintenance
    _in_maintenance = False
    print("[MAINT] Maintenance mode cleared manually")
    return {"status": "maintenance_off"}


@app.get("/api/v1/admin/maintenance/status", tags=["Admin"])
async def maintenance_status():
    """Public-readable — clients can poll this if they want to confirm the API is back."""
    return {"in_maintenance": _in_maintenance}


# ════════════════════════════════════════════════════════════════════
# 2v2 RANKED (Phase 1 — Backend foundation)
# ════════════════════════════════════════════════════════════════════
# Parallel path to 1v1 ranked. Reuses Glicko-2 helper but separate ratings,
# separate queue, separate matches. See migration 053_2v2_schema.sql.

# Tunables. Wider ranges than 1v1 because the team-balancer absorbs some
# imbalance — 4-player matches don't need as tight a per-player Elo window.
TEAM_QUEUE_EXPIRE_MINUTES = 30
TEAM_READY_TIMEOUT_SECONDS = 120  # +30s vs 1v1 — 4 players coordinating is slower
# Min completed 2v2 series before we trust the 2v2 rating; below that the balancer
# falls back to 1v1 rating for that player (lesson: new accounts shouldn't drag a
# matchmaking decision around with a 1500-default 2v2 rating that means nothing).
TEAM_TRUST_2V2_RATING_AFTER = 10
# 2v2 elo is also trusted earlier than the series count if the player's RD has
# already converged below this threshold — Glicko-2 RD shrinks fast for active
# players, so once it hits ~100 the rating estimate is meaningful even if the
# player only has a few completed series. Without this, two high-elo veterans
# (one with 20 series, one with 4) couldn't get matched as opponents because
# the matchmaker would fall back to the new account's 1v1 elo for balancing.
TEAM_TRUST_2V2_RD_BELOW = 110.0

# 2v2 economy. Per-match XP base + win multiplier targets ~600 XP loss /
# ~900 XP win at base; per-series gold bonus on top.
TEAM_MATCH_XP_BASE       = 600
TEAM_MATCH_WIN_MULT      = 1.5  # 600 → 900 on win
TEAM_SERIES_WIN_GOLD     = 50
TEAM_SERIES_LOSS_GOLD    = 25
# Mid-series auto-balance trigger. Fires after a match in an auto-balanced
# series whose total point margin >= this threshold (e.g., 5-2 = margin 3).
# Lower → swap more often (every close-ish game), higher → swap only on
# blowouts. Tester request: "make sure colors/spawns/etc get properly
# swapped" — server emits rebalance_assignments and the client follows.
AUTO_BALANCE_SWAP_MARGIN = 3


def _verify_team_hmac(report: TeamMatchReport) -> bool:
    """11-field canonical: t1a:t1b:t2a:t2b:t1r:t2r:is_ranked:reporter:room_id:winner_team:series_id"""
    if not MATCH_HMAC_SECRET:
        return True
    if not report.hmac_signature:
        print(f"[TEAM-HMAC] No signature provided")
        return False
    msg = (
        f"{report.t1a.steam_id}:{report.t1b.steam_id}:"
        f"{report.t2a.steam_id}:{report.t2b.steam_id}:"
        f"{report.t1_rounds_won}:{report.t2_rounds_won}:"
        f"{str(report.is_ranked).lower()}:{report.reported_by_steam_id}:"
        f"{report.photon_room_id or ''}:{report.winner_team}:{report.series_id}"
    )
    expected = hmac.new(MATCH_HMAC_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()
    ok = hmac.compare_digest(report.hmac_signature, expected)
    if not ok:
        print(f"[TEAM-HMAC] mismatch. canonical='{msg}'")
    return ok


def _balance_teams(players: list[dict]) -> tuple[list[str], list[str]]:
    """Pick the partition (AB-CD / AC-BD / AD-BC) with the smallest |Δ-Elo|.
    `players` is a list of 4 dicts with keys: player_id, balance_rating.
    Returns (team1_ids, team2_ids) in original order — the caller assigns
    team_assigned=1/2 by membership."""
    assert len(players) == 4
    p = players  # alias
    partitions = [
        ([p[0], p[1]], [p[2], p[3]]),
        ([p[0], p[2]], [p[1], p[3]]),
        ([p[0], p[3]], [p[1], p[2]]),
    ]
    def diff(team1, team2):
        s1 = sum(x["balance_rating"] for x in team1)
        s2 = sum(x["balance_rating"] for x in team2)
        return abs(s1 - s2)
    best = min(partitions, key=lambda part: diff(part[0], part[1]))
    return ([x["player_id"] for x in best[0]], [x["player_id"] for x in best[1]])


def _team_balance_rating(rating: float, completed_series: int, fallback_rating: float, rd: float = 350.0) -> float:
    """Use 2v2 rating once a player has either:
       - enough completed series (TEAM_TRUST_2V2_RATING_AFTER), OR
       - converged RD (rd <= TEAM_TRUST_2V2_RD_BELOW)
    Otherwise fall back to their 1v1 rating. RD path catches active players
    whose 2v2 rating is meaningful even before they hit the series threshold."""
    if completed_series >= TEAM_TRUST_2V2_RATING_AFTER:
        return rating
    if rd is not None and rd <= TEAM_TRUST_2V2_RD_BELOW:
        return rating
    return fallback_rating


@app.post("/api/v1/team/queue/join", tags=["Team Queue"])
async def team_queue_join(req: TeamQueueJoinRequest, db: AsyncSession = Depends(get_db)):
    """Upsert player into team_queue. Snapshots their 2v2 + 1v1 ratings so the
    balancer at lock-time uses queue-join values (not drifted live ratings)."""
    await _check_ban_or_raise(db, req.steam_id)
    name = req.display_name or req.steam_id
    player = await get_or_create_player(db, req.steam_id, name)
    await _mark_mod_seen(db, player)

    # Snapshot 2v2 rating (default if no row yet)
    g2_r = await db.execute(select(GlickoRating2v2).where(GlickoRating2v2.player_id == player.id))
    g2 = g2_r.scalar_one_or_none()
    rating_2v2 = g2.rating if g2 else GLICKO2_DEFAULT_RATING
    rd_2v2 = g2.rating_deviation if g2 else GLICKO2_DEFAULT_RD
    completed = g2.completed_series if g2 else 0

    # Snapshot 1v1 rating for the balancer fallback
    g1_r = await db.execute(select(GlickoRating).where(GlickoRating.player_id == player.id))
    g1 = g1_r.scalar_one_or_none()
    fallback_rating = g1.rating if g1 else GLICKO2_DEFAULT_RATING

    qtype = (req.queue_type or "auto").lower()
    if qtype not in ("auto", "manual"):
        qtype = "auto"

    # Switching queue type clears any stale preferred_team — manual queue starts
    # fresh with no team claimed; auto queue ignores preferred_team entirely.
    stmt = pg_insert(TeamQueue).values(
        player_id=player.id,
        steam_id=req.steam_id,
        display_name=player.display_name,
        rating=rating_2v2,
        rating_deviation=rd_2v2,
        completed_series=completed,
        fallback_rating=fallback_rating,
        region=req.region,
        status="searching",
        series_id=None,
        team_assigned=None,
        room_name=None,
        room_region=None,
        ready=False,
        joined_at=datetime.now(timezone.utc),
        matched_at=None,
        last_polled=datetime.now(timezone.utc),
        queue_type=qtype,
    ).on_conflict_do_update(
        index_elements=[TeamQueue.player_id],
        set_={
            "status": "searching",
            "rating": rating_2v2,
            "rating_deviation": rd_2v2,
            "completed_series": completed,
            "fallback_rating": fallback_rating,
            "region": req.region,
            "series_id": None,
            "team_assigned": None,
            "room_name": None,
            "room_region": None,
            "ready": False,
            "joined_at": datetime.now(timezone.utc),
            "matched_at": None,
            "last_polled": datetime.now(timezone.utc),
            "queue_type": qtype,
            "preferred_team": None,
            "manual_pick_enabled": (qtype == "manual"),
        },
    )
    await db.execute(stmt)
    await db.commit()
    return {"status": "searching", "queue_type": qtype, "message": f"Joined 2v2 {qtype} queue"}


@app.post("/api/v1/team/queue/leave", tags=["Team Queue"])
async def team_queue_leave(steam_id: str = Query(...), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Player).where(Player.steam_id == steam_id))
    player = result.scalar_one_or_none()
    if player:
        # If player is in a locked match (status='matched'), tearing down their row
        # alone would strand the other 3. Cascade: cancel the whole series and
        # release the other 3 back to searching, rather than leave them locked
        # against a ghost teammate.
        row = await db.execute(
            text("SELECT series_id, status FROM team_queue WHERE player_id = :pid"),
            {"pid": player.id},
        )
        r = row.mappings().first()
        if r and r["series_id"] and r["status"] in ("matched", "ready"):
            await db.execute(
                text("""
                    UPDATE team_queue
                    SET status='searching', series_id=NULL, team_assigned=NULL,
                        room_name=NULL, room_region=NULL, ready=false,
                        matched_at=NULL, joined_at=NOW()
                    WHERE series_id = :sid AND player_id != :pid
                """),
                {"sid": r["series_id"], "pid": player.id},
            )
            # Mark the series invalidated so the post-lock /matches submit can't
            # accidentally write to it after a no-show.
            await db.execute(
                text("""
                    UPDATE team_series
                    SET status='cancelled', invalidated_at=NOW(),
                        invalidation_reason='pre_match_leaver'
                    WHERE id = :sid AND status='active'
                """),
                {"sid": r["series_id"]},
            )
        await db.execute(
            text("DELETE FROM team_queue WHERE player_id = :pid"),
            {"pid": player.id},
        )
        await db.commit()
    return {"status": "left"}


@app.get("/api/v1/team/queue/count", tags=["Team Queue"])
async def team_queue_count(db: AsyncSession = Depends(get_db)):
    """Lightweight: live queue size for the F5 tab "X searching" banner."""
    result = await db.execute(text("SELECT COUNT(*) FROM team_queue WHERE status = 'searching'"))
    searching = result.scalar() or 0
    return {"searching": searching}


@app.get("/api/v1/team/queue/list", tags=["Team Queue"])
async def team_queue_list(db: AsyncSession = Depends(get_db)):
    """Snapshot of every player currently in the 2v2 queue. Powers the
    "who else is queueing" panels on the F5 2v2 tab. Returns the unified
    `queuers` list (legacy) PLUS split `auto` / `manual` buckets so the
    client can render two side-by-side panels without re-filtering."""
    result = await db.execute(
        text("""
            SELECT tq.steam_id, tq.display_name, tq.rating, tq.rating_deviation, tq.completed_series,
                   tq.fallback_rating, tq.region, tq.joined_at, tq.status,
                   tq.team_assigned, tq.series_id,
                   tq.manual_pick_enabled, tq.preferred_team, tq.queue_type
            FROM team_queue tq
            WHERE tq.status IN ('searching', 'matched', 'ready')
            ORDER BY tq.joined_at ASC
        """),
    )
    rows = result.mappings().all()
    out: list[dict] = []
    auto_bucket: list[dict] = []
    manual_bucket: list[dict] = []
    for r in rows:
        cs = int(r["completed_series"] or 0)
        rd = float(r["rating_deviation"] or 350.0)
        # Same trust rule the matchmaker uses — series count OR converged RD.
        using_fb = (cs < TEAM_TRUST_2V2_RATING_AFTER) and (rd > TEAM_TRUST_2V2_RD_BELOW)
        fb = float(r["fallback_rating"] or 0)
        balance = int(round(fb)) if using_fb else int(round(r["rating"]))
        qt = (r["queue_type"] or "auto").lower()
        entry = {
            "steam_id": r["steam_id"],
            "display_name": r["display_name"],
            "rating": int(round(r["rating"] or 0)),
            "balance_rating": balance,
            "using_fallback_rating": using_fb,
            "completed_series": cs,
            "region": r["region"],
            "status": r["status"],
            "team_assigned": r["team_assigned"],
            "series_id": str(r["series_id"]) if r["series_id"] else None,
            "joined_at": r["joined_at"].isoformat() if r["joined_at"] else None,
            "wait_seconds": int((datetime.now(timezone.utc) - r["joined_at"]).total_seconds()) if r["joined_at"] else 0,
            "manual_pick_enabled": bool(r["manual_pick_enabled"]),
            "preferred_team": r["preferred_team"],
            "queue_type": qt,
        }
        out.append(entry)
        (manual_bucket if qt == "manual" else auto_bucket).append(entry)
    return {
        "queuers": out,
        "count": len(out),
        "auto": auto_bucket,
        "manual": manual_bucket,
        "auto_count": len(auto_bucket),
        "manual_count": len(manual_bucket),
    }


@app.get("/api/v1/team/queue/recent-joins", tags=["Team Queue"])
async def team_queue_recent_joins(seconds: int = Query(20), db: AsyncSession = Depends(get_db)):
    """Players who joined the 2v2 queue in the last N seconds. Drives the Discord
    beacon `🎯 NAME searching for 2v2!` post — auto queue only. Custom-lobby
    (manual) queuers are intentionally excluded so #ranked-looking-for-people
    only beacons random-matchmaking joins."""
    result = await db.execute(
        text("""
            SELECT tq.display_name, tq.steam_id, tq.rating, tq.joined_at
            FROM team_queue tq
            WHERE tq.status = 'searching'
              AND tq.queue_type = 'auto'
              AND tq.joined_at > NOW() - INTERVAL '1 second' * :secs
            ORDER BY tq.joined_at DESC
        """), {"secs": seconds},
    )
    rows = result.mappings().all()
    cnt_q = await db.execute(text("SELECT COUNT(*) FROM team_queue WHERE status='searching' AND queue_type='auto'"))
    cnt = cnt_q.scalar() or 0
    return {
        "joins": [
            {"display_name": r["display_name"], "steam_id": r["steam_id"],
             "rating": round(r["rating"]), "joined_at": r["joined_at"].isoformat()}
            for r in rows
        ],
        "queue_size": cnt,
    }


@app.get("/api/v1/team/queue/poll/{steam_id}", response_model=TeamQueuePollResponse, tags=["Team Queue"])
async def team_queue_poll(steam_id: str, db: AsyncSession = Depends(get_db)):
    """Polled by all 4 participants. Drives the searching → matched → ready_join state machine.
    At lock time, runs the balancer to assign teams. Identical safety pattern to 1v1:
    SELECT FOR UPDATE SKIP LOCKED on the candidate set, atomic update of all 4 rows."""
    import uuid as uuid_mod

    # Find caller's queue row (locked).
    me_q = await db.execute(
        text("""
            SELECT tq.player_id, tq.steam_id, tq.display_name, tq.rating, tq.rating_deviation,
                   tq.completed_series, tq.fallback_rating, tq.region, tq.status, tq.series_id,
                   tq.team_assigned, tq.room_name, tq.room_region, tq.ready,
                   tq.joined_at, tq.matched_at, tq.queue_type
            FROM team_queue tq
            JOIN players p ON tq.player_id = p.id
            WHERE p.steam_id = :sid
            FOR UPDATE OF tq
        """),
        {"sid": steam_id},
    )
    me = me_q.mappings().first()
    if not me:
        await db.commit()
        return TeamQueuePollResponse(status="not_in_queue")

    now = datetime.now(timezone.utc)
    wait_seconds = int((now - me["joined_at"]).total_seconds())
    my_pid = me["player_id"]

    # Heartbeat
    await db.execute(
        text("UPDATE team_queue SET last_polled = NOW() WHERE player_id = :pid"),
        {"pid": my_pid},
    )

    # Searching expiry
    if me["status"] == "searching" and wait_seconds > TEAM_QUEUE_EXPIRE_MINUTES * 60:
        await db.execute(text("DELETE FROM team_queue WHERE player_id = :pid"), {"pid": my_pid})
        await db.commit()
        return TeamQueuePollResponse(status="expired")

    # ── MATCHED / READY state ────────────────────────────────
    if me["status"] in ("matched", "ready") and me["series_id"]:
        # Pull the other 3 in this series
        peers_q = await db.execute(
            text("""
                SELECT player_id, steam_id, display_name, rating, region, ready, team_assigned
                FROM team_queue
                WHERE series_id = :sid AND player_id != :pid
            """),
            {"sid": me["series_id"], "pid": my_pid},
        )
        peers = list(peers_q.mappings().all())
        if len(peers) < 3:
            # Someone left — cascade was handled in /leave; we degrade back to searching here.
            await db.execute(
                text("""UPDATE team_queue
                       SET status='searching', series_id=NULL, team_assigned=NULL,
                           room_name=NULL, room_region=NULL, ready=false,
                           matched_at=NULL, joined_at=NOW()
                       WHERE player_id = :pid"""),
                {"pid": my_pid},
            )
            await db.commit()
            return TeamQueuePollResponse(status="searching")

        my_team = me["team_assigned"]
        teammates = [p for p in peers if p["team_assigned"] == my_team]
        opponents = [p for p in peers if p["team_assigned"] != my_team]
        all_4 = peers + [me]
        all_ready = all(p["ready"] for p in all_4)

        # Ready timeout
        if me["matched_at"]:
            match_age = int((now - me["matched_at"]).total_seconds())
            if match_age > TEAM_READY_TIMEOUT_SECONDS and not all_ready:
                # Cancel the series — boot all 4 back to searching.
                ids = [p["player_id"] for p in all_4]
                await db.execute(
                    text("""UPDATE team_queue
                           SET status='searching', series_id=NULL, team_assigned=NULL,
                               room_name=NULL, room_region=NULL, ready=false,
                               matched_at=NULL, joined_at=NOW()
                           WHERE player_id = ANY(:ids)"""),
                    {"ids": ids},
                )
                await db.execute(
                    text("UPDATE team_series SET status='cancelled', invalidated_at=NOW(), invalidation_reason='ready_timeout' WHERE id = :sid"),
                    {"sid": me["series_id"]},
                )
                await db.commit()
                return TeamQueuePollResponse(status="searching")

        # Build response payload
        def to_member(row):
            cs = int(row.get("completed_series") or 0)
            rd = float(row.get("rating_deviation") or 350.0)
            using_fb = (cs < TEAM_TRUST_2V2_RATING_AFTER) and (rd > TEAM_TRUST_2V2_RD_BELOW)
            fb = float(row.get("fallback_rating") or 0)
            balance = int(round(fb)) if using_fb else int(round(row["rating"]))
            return TeamQueueMember(
                steam_id=row["steam_id"],
                display_name=row["display_name"],
                rating=int(round(row["rating"])),
                region=row["region"],
                team_assigned=row["team_assigned"],
                using_fallback_rating=using_fb,
                balance_rating=balance,
                completed_series=cs,
            )
        teammates_pl = [to_member(r) for r in teammates]
        opponents_pl = [to_member(r) for r in opponents]

        if all_ready:
            # Generate room if not yet set (any one of the 4 can establish it).
            if not me["room_name"]:
                room_name = f"team_{uuid_mod.uuid4().hex[:12]}"
                # Pick region by mode of the 4 region values; fallback to 'us'.
                regions = [p["region"] for p in all_4 if p["region"]]
                if regions:
                    chosen_region = max(set(regions), key=regions.count)
                else:
                    chosen_region = "us"
                await db.execute(
                    text("""UPDATE team_queue
                           SET room_name = :rn, room_region = :rr
                           WHERE series_id = :sid"""),
                    {"rn": room_name, "rr": chosen_region, "sid": me["series_id"]},
                )
                await db.execute(
                    text("UPDATE team_series SET photon_room_id = :rn, region = :rr WHERE id = :sid"),
                    {"rn": room_name, "rr": chosen_region, "sid": me["series_id"]},
                )
                # Re-read so the response reflects the new room name.
                me_re = await db.execute(
                    text("SELECT room_name, room_region FROM team_queue WHERE player_id = :pid"),
                    {"pid": my_pid},
                )
                rr = me_re.mappings().first()
                room_out = rr["room_name"]
                region_out = rr["room_region"]
            else:
                room_out = me["room_name"]
                region_out = me["room_region"]

            await db.commit()
            return TeamQueuePollResponse(
                status="ready_join",
                series_id=str(me["series_id"]),
                team_assigned=my_team,
                teammates=teammates_pl,
                opponents=opponents_pl,
                room_name=room_out,
                room_region=region_out,
                match_age_seconds=int((now - me["matched_at"]).total_seconds()) if me["matched_at"] else 0,
            )

        # Matched but not all-ready
        await db.commit()
        return TeamQueuePollResponse(
            status="matched",
            series_id=str(me["series_id"]),
            team_assigned=my_team,
            teammates=teammates_pl,
            opponents=opponents_pl,
            match_age_seconds=int((now - me["matched_at"]).total_seconds()) if me["matched_at"] else 0,
        )

    # ── SEARCHING ── try to lock 4 mutually-acceptable players
    elo_range = compute_elo_range(wait_seconds)
    my_balance = _team_balance_rating(me["rating"], me["completed_series"], me["fallback_rating"], me["rating_deviation"])

    # Find 3 other compatible players. Bilateral Elo overlap, no mutual blocks.
    # Use the SAME elo_range as the caller's tier — wider tier callers find each
    # other faster but a 60s-old caller can't lock with a brand-new 100-Elo-band caller.
    my_qtype = (me.get("queue_type") or "auto").lower()
    cands = await db.execute(
        text("""
            SELECT tq.player_id, tq.steam_id, tq.display_name, tq.rating, tq.rating_deviation,
                   tq.completed_series, tq.fallback_rating, tq.region, tq.joined_at,
                   tq.manual_pick_enabled, tq.preferred_team, tq.queue_type
            FROM team_queue tq
            WHERE tq.status = 'searching'
              AND tq.player_id != :pid
              AND tq.queue_type = :qt
              AND ABS(tq.rating - :my_r) <= :range
              AND tq.player_id NOT IN (
                  SELECT blocked_id FROM player_blocks WHERE blocker_id = :pid
                  UNION SELECT blocker_id FROM player_blocks WHERE blocked_id = :pid
                  UNION SELECT blocked_id FROM queue_blocks WHERE blocker_id = :pid AND expires_at > now()
                  UNION SELECT blocker_id FROM queue_blocks WHERE blocked_id = :pid AND expires_at > now()
              )
            ORDER BY ABS(tq.rating - :my_r), tq.joined_at
            LIMIT 3
            FOR UPDATE SKIP LOCKED
        """),
        {"pid": my_pid, "my_r": me["rating"], "range": elo_range, "qt": my_qtype},
    )
    others = list(cands.mappings().all())

    # ── Sticky-team requeue resume ──────────────────────────────────
    # If this caller belongs to a `dc_paused` series whose grace deadline
    # hasn't expired, and the other 3 original players are ALSO in queue,
    # resume the existing series with the SAME teams instead of creating
    # a fresh one. Falls through to the normal balancer path otherwise.
    dc_resume_series = await db.execute(
        text("""
            SELECT id, t1a_id, t1b_id, t2a_id, t2b_id, dc_grace_until
              FROM team_series
             WHERE status = 'dc_paused'
               AND dc_grace_until > NOW()
               AND :pid IN (t1a_id, t1b_id, t2a_id, t2b_id)
             ORDER BY dc_grace_until DESC
             LIMIT 1
        """),
        {"pid": my_pid},
    )
    dc_row = dc_resume_series.mappings().first()
    if dc_row is not None:
        original_pids = [dc_row["t1a_id"], dc_row["t1b_id"], dc_row["t2a_id"], dc_row["t2b_id"]]
        # Are the OTHER 3 original players currently in queue (any status)?
        rs = await db.execute(
            text("""
                SELECT player_id, steam_id, display_name, rating, region
                  FROM team_queue
                 WHERE player_id = ANY(:pids)
                   AND status IN ('searching', 'matched', 'ready')
                   AND player_id != :me
                FOR UPDATE SKIP LOCKED
            """),
            {"pids": original_pids, "me": my_pid},
        )
        present = list(rs.mappings().all())
        if len(present) == 3:
            # All 4 originals are here. Re-lock them with the EXISTING series.
            print(f"[TEAM-QUEUE-LOCK] sticky-team resume: series={dc_row['id']} caller={steam_id}")
            # Map original team to t1/t2 — keep the original assignments so the
            # balancer-time slot order remains canonical for HMAC matching.
            t1a, t1b = dc_row["t1a_id"], dc_row["t1b_id"]
            t2a, t2b = dc_row["t2a_id"], dc_row["t2b_id"]
            for pid in [my_pid] + [p["player_id"] for p in present]:
                t = 1 if pid in (t1a, t1b) else 2
                await db.execute(
                    text("""
                        UPDATE team_queue
                           SET status = 'matched',
                               series_id = :sid,
                               team_assigned = :t,
                               matched_at = NOW()
                         WHERE player_id = :pid
                    """),
                    {"sid": dc_row["id"], "t": t, "pid": pid},
                )
            # Flip the series back to active and clear DC fields so the next
            # match plays through normally.
            await db.execute(
                text("""
                    UPDATE team_series
                       SET status = 'active',
                           dc_grace_until = NULL,
                           dc_team_remaining = NULL,
                           dc_player_id = NULL
                     WHERE id = :sid
                """),
                {"sid": dc_row["id"]},
            )
            await db.commit()
            # The poll responder reads the queue rows again on its next pass —
            # return matched here so the caller sees the resume and surfaces
            # the ready-up button.
            my_team = 1 if my_pid in (t1a, t1b) else 2
            return TeamQueuePollResponse(
                status="matched",
                series_id=str(dc_row["id"]),
                team_assigned=my_team,
                teammates=[],   # filled by next poll tick from the queue rows
                opponents=[],
                match_age_seconds=0,
            )

    if len(others) < 3:
        # Not enough — count searching, return.
        cnt_q = await db.execute(text("SELECT COUNT(*) FROM team_queue WHERE status='searching'"))
        cnt = cnt_q.scalar() or 0
        # Diagnostic: when the searching queue has >= 4 players but our lock
        # only finds < 3 candidates from THIS poller's perspective, something
        # filter-side is rejecting them (Elo band too tight, mutual block, or
        # SKIP LOCKED on a concurrent poll). This log is the primary signal
        # for "queue is full but match isn't locking".
        if cnt >= 4:
            print(f"[TEAM-QUEUE-LOCK] caller={steam_id} q_size={cnt} found_others={len(others)} elo_range={elo_range} my_rating={me['rating']:.0f}")
        await db.commit()
        return TeamQueuePollResponse(status="searching", queue_count=cnt, elo_range=elo_range)

    # 4 candidates total (caller + others). Run balancer (or honor manual picks).
    print(f"[TEAM-QUEUE-LOCK] caller={steam_id} locking 4-player series with {[o['steam_id'] for o in others]}")
    pool = [
        {"player_id": me["player_id"], "balance_rating": my_balance,
         "rating": me["rating"], "rd": me["rating_deviation"],
         "steam_id": me["steam_id"],
         "manual_pick_enabled": bool(me.get("manual_pick_enabled")),
         "preferred_team": me.get("preferred_team")},
    ]
    for o in others:
        pool.append({
            "player_id": o["player_id"],
            "balance_rating": _team_balance_rating(o["rating"], o["completed_series"], o["fallback_rating"], o["rating_deviation"]),
            "rating": o["rating"],
            "rd": o["rating_deviation"],
            "steam_id": o["steam_id"],
            "manual_pick_enabled": bool(o.get("manual_pick_enabled")),
            "preferred_team": o.get("preferred_team"),
        })

    # Manual queue: honor each player's preferred_team (queue membership IS the
    # opt-in). Players without a preference fill remaining slots. Auto queue:
    # always run the elo balancer regardless of any stale preferred_team.
    was_auto_balanced = True
    if my_qtype == "manual":
        team1_ids, team2_ids, unassigned = [], [], []
        for p in pool:
            pt = p["preferred_team"]
            if pt == 1 and len(team1_ids) < 2:
                team1_ids.append(p["player_id"])
            elif pt == 2 and len(team2_ids) < 2:
                team2_ids.append(p["player_id"])
            else:
                unassigned.append(p["player_id"])
        for pid in unassigned:
            if len(team1_ids) < 2:
                team1_ids.append(pid)
            elif len(team2_ids) < 2:
                team2_ids.append(pid)
        was_auto_balanced = False
        print(f"[TEAM-QUEUE-LOCK] manual-pick honored: t1={team1_ids} t2={team2_ids}")
    else:
        team1_ids, team2_ids = _balance_teams(pool)

    # Within each team, canonicalize the t-a / t-b slot order by sorting on
    # steam_id. The client reconstructs the same canonical order without any
    # extra metadata, so its 11-field HMAC byte-matches what the server
    # rebuilds at /team/matches submit time. Without this canonicalization
    # the balancer's arbitrary partition order would break HMAC verification.
    pid_to_steam = {p["player_id"]: p["steam_id"] for p in pool}
    team1_ids_sorted = sorted(team1_ids, key=lambda pid: pid_to_steam[pid])
    team2_ids_sorted = sorted(team2_ids, key=lambda pid: pid_to_steam[pid])

    # Create the team_series row.
    series_id = uuid_mod.uuid4()
    await db.execute(
        text("""
            INSERT INTO team_series (id, t1a_id, t1b_id, t2a_id, t2b_id,
                                     status, was_auto_balanced, created_at)
            VALUES (:sid, :t1a, :t1b, :t2a, :t2b, 'active', :wab, NOW())
        """),
        {
            "sid": series_id,
            "t1a": team1_ids_sorted[0], "t1b": team1_ids_sorted[1],
            "t2a": team2_ids_sorted[0], "t2b": team2_ids_sorted[1],
            "wab": was_auto_balanced,
        },
    )
    team1_ids = team1_ids_sorted
    team2_ids = team2_ids_sorted

    # Auto-clear permanent player_blocks within each team. If A blocked B from
    # 1v1 ranked but they ended up paired as teammates by the balancer, the
    # block would otherwise persist into 1v1 (annoying after a friendly 2v2).
    # Mirror of the tournament-lock behavior — clearing only WITHIN-team pairs.
    all_pairs = []
    for team in (team1_ids, team2_ids):
        all_pairs.extend([(team[0], team[1]), (team[1], team[0])])
    if all_pairs:
        # Use CAST(...) instead of `:bind::type` — asyncpg's parameter parser
        # can't distinguish PG's `::` cast operator from a bind-parameter prefix
        # when they're adjacent (`:b1::uuid[]` was throwing PostgresSyntaxError
        # on every lock attempt, silently rolling back the whole 4-player lock
        # transaction so no series ever materialized).
        await db.execute(
            text("""
                DELETE FROM player_blocks
                WHERE (blocker_id, blocked_id) IN (
                    SELECT UNNEST(CAST(:b1 AS uuid[])), UNNEST(CAST(:b2 AS uuid[]))
                )
            """),
            {"b1": [p[0] for p in all_pairs], "b2": [p[1] for p in all_pairs]},
        )
    # Update all 4 queue rows in one statement using arrays.
    matched_at = datetime.now(timezone.utc)
    await db.execute(
        text("""
            UPDATE team_queue
            SET status='matched',
                series_id=:sid,
                team_assigned = CASE WHEN player_id = ANY(:t1) THEN 1 ELSE 2 END,
                matched_at = :mat,
                ready = false,
                room_name = NULL, room_region = NULL
            WHERE player_id = ANY(:all4)
        """),
        {
            "sid": series_id,
            "t1": team1_ids,
            "mat": matched_at,
            "all4": team1_ids + team2_ids,
        },
    )
    await db.commit()

    # Reload our row to figure out our team.
    me_re = await db.execute(
        text("""SELECT team_assigned, matched_at FROM team_queue WHERE player_id = :pid"""),
        {"pid": my_pid},
    )
    me_row = me_re.mappings().first()
    my_team = me_row["team_assigned"]

    # Build initial matched response.
    peers_q = await db.execute(
        text("""SELECT player_id, steam_id, display_name, rating, region, team_assigned
               FROM team_queue WHERE series_id = :sid AND player_id != :pid"""),
        {"sid": series_id, "pid": my_pid},
    )
    peers = list(peers_q.mappings().all())
    teammates_pl = [
        TeamQueueMember(steam_id=p["steam_id"], display_name=p["display_name"],
                        rating=int(round(p["rating"])), region=p["region"], team_assigned=p["team_assigned"])
        for p in peers if p["team_assigned"] == my_team
    ]
    opponents_pl = [
        TeamQueueMember(steam_id=p["steam_id"], display_name=p["display_name"],
                        rating=int(round(p["rating"])), region=p["region"], team_assigned=p["team_assigned"])
        for p in peers if p["team_assigned"] != my_team
    ]

    return TeamQueuePollResponse(
        status="matched",
        series_id=str(series_id),
        team_assigned=my_team,
        teammates=teammates_pl,
        opponents=opponents_pl,
        match_age_seconds=0,
    )


@app.post("/api/v1/team/queue/manual-pick-toggle", tags=["Team Queue"])
async def team_queue_manual_pick_toggle(
    steam_id: str = Query(...),
    enabled: bool = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Flip the per-queuer manual_pick_enabled flag. The matchmaker respects
    `preferred_team` only when at least 3 queuers have the flag enabled
    (otherwise it auto-balances by elo). When disabling, the queuer's
    preferred_team is cleared."""
    pid = (await db.execute(select(Player.id).where(Player.steam_id == steam_id))).scalar_one_or_none()
    if pid is None:
        raise HTTPException(404, "Player not found")
    if enabled:
        await db.execute(
            text("UPDATE team_queue SET manual_pick_enabled = TRUE WHERE player_id = :pid"),
            {"pid": pid},
        )
    else:
        await db.execute(
            text("UPDATE team_queue SET manual_pick_enabled = FALSE, preferred_team = NULL WHERE player_id = :pid"),
            {"pid": pid},
        )
    await db.commit()
    return {"status": "ok", "enabled": enabled}


@app.post("/api/v1/team/queue/preferred-team", tags=["Team Queue"])
async def team_queue_preferred_team(
    steam_id: str = Query(...),
    team: int = Query(..., ge=1, le=2),
    db: AsyncSession = Depends(get_db),
):
    """Claim Team 1 or Team 2. Only honored when the queuer is in the manual
    (pick-teams) queue. Auto-queue calls are no-ops because the matchmaker
    ignores preferred_team for that queue."""
    pid = (await db.execute(select(Player.id).where(Player.steam_id == steam_id))).scalar_one_or_none()
    if pid is None:
        raise HTTPException(404, "Player not found")
    await db.execute(
        text("""
            UPDATE team_queue
               SET preferred_team = :team
             WHERE player_id = :pid AND queue_type = 'manual'
        """),
        {"pid": pid, "team": team},
    )
    await db.commit()
    return {"status": "ok", "preferred_team": team}


@app.post("/api/v1/team/queue/ready", tags=["Team Queue"])
async def team_queue_ready(steam_id: str = Query(...), db: AsyncSession = Depends(get_db)):
    """Mark caller ready. Resets matched_at on all 4 rows so the timeout window
    refreshes for whoever is the slowest of the four. (Lesson 51 from 1v1.)"""
    result = await db.execute(select(Player).where(Player.steam_id == steam_id))
    player = result.scalar_one_or_none()
    if not player:
        return {"status": "error", "message": "Unknown player"}
    me_q = await db.execute(
        text("SELECT series_id, status FROM team_queue WHERE player_id = :pid"),
        {"pid": player.id},
    )
    me = me_q.mappings().first()
    if not me or not me["series_id"] or me["status"] not in ("matched", "ready"):
        return {"status": "error", "message": "Not in a matched 2v2 series"}
    await db.execute(
        text("""UPDATE team_queue
               SET ready = (player_id = :pid OR ready),
                   matched_at = NOW(),
                   status = 'ready'
               WHERE series_id = :sid"""),
        {"pid": player.id, "sid": me["series_id"]},
    )
    await db.commit()
    # Log how many of the 4 are now ready so the lobby state is observable
    # without firing a separate poll log per player.
    cnt_q = await db.execute(
        text("SELECT COUNT(*) FROM team_queue WHERE series_id = :sid AND ready = true"),
        {"sid": me["series_id"]},
    )
    ready_cnt = cnt_q.scalar() or 0
    print(f"[TEAM-READY] {steam_id} ready ({ready_cnt}/4) in series {me['series_id']}")
    return {"status": "ok", "ready_count": ready_cnt}


# ─────────────────────────────────────────────────────────────────────────
# Match-assembly tracking (added v1.25.11). Each client posts spawn-confirm
# when its auto-spawn override successfully creates the local Player. Server
# bumps spawn_confirmations + records the player_id (idempotent). When state
# is polled and the series has been active >15s with <4 confirmations, the
# server cancels the series with reason='assembly_timeout' so all 4 clients
# can bail to menu instead of sitting on the ready screen for 30s.
# ─────────────────────────────────────────────────────────────────────────

_ASSEMBLY_DEADLINE_SECONDS = 15


def _verify_spawn_confirm_hmac(steam_id: str, series_id: str, signature: str) -> bool:
    """HMAC for spawn-confirm = sha256(secret, "{steam_id}:{series_id}:spawn")."""
    if not MATCH_HMAC_SECRET:
        return True  # dev mode without secret
    expected = hmac.new(
        MATCH_HMAC_SECRET.encode(),
        f"{steam_id}:{series_id}:spawn".encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")


@app.post("/api/v1/team/series/{series_id}/spawn-confirm", tags=["Team Matches"])
async def team_series_spawn_confirm(
    series_id: str,
    steam_id: str = Query(...),
    hmac_sig: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Client posts this when its 2v2 auto-spawn override successfully creates
    the local Player. Idempotent per (series, player) — safe to retry."""
    if not _verify_spawn_confirm_hmac(steam_id, series_id, hmac_sig):
        raise HTTPException(403, "Invalid spawn-confirm signature")
    try:
        sid_uuid = UUID(series_id)
    except (ValueError, TypeError):
        raise HTTPException(400, "Invalid series_id")
    # Resolve player to UUID for the idempotency record.
    p_row = await db.execute(select(Player.id).where(Player.steam_id == steam_id))
    pid = p_row.scalar_one_or_none()
    if pid is None:
        raise HTTPException(404, "Unknown player")

    # Idempotent atomic update: only increment if this player hasn't already
    # been recorded. asyncpg + jsonb @> for membership.
    # asyncpg's parameter parser collides with PostgreSQL's `::` cast operator
    # (learning #46 — same bug we hit with `:b1::uuid[]`). Use CAST(...) form.
    res = await db.execute(
        text("""
            UPDATE team_series
               SET spawn_confirmations = spawn_confirmations + 1,
                   spawn_confirmed_by = spawn_confirmed_by || to_jsonb(CAST(:pid AS text))
             WHERE id = :sid
               AND status = 'active'
               AND NOT (spawn_confirmed_by @> to_jsonb(CAST(:pid AS text)))
            RETURNING spawn_confirmations
        """),
        {"sid": sid_uuid, "pid": str(pid)},
    )
    new_count = res.scalar_one_or_none()
    await db.commit()
    if new_count is None:
        # Either series not active, or player already confirmed. Read current
        # value to return — useful for clients to see "already done".
        row = await db.execute(
            text("SELECT spawn_confirmations, status FROM team_series WHERE id = :sid"),
            {"sid": sid_uuid},
        )
        cur = row.first()
        if cur is None:
            raise HTTPException(404, "Series not found")
        return {"confirmations": int(cur[0] or 0), "status": cur[1], "already_recorded": True}
    return {"confirmations": int(new_count), "status": "active", "already_recorded": False}


@app.get("/api/v1/team/series/{series_id}/state", tags=["Team Matches"])
async def team_series_state(series_id: str, db: AsyncSession = Depends(get_db)):
    """Per-series assembly + lifecycle state. Polled by clients during the
    first ~20 seconds after ready_join. If the series has been active for
    longer than the assembly deadline (15s) and fewer than 4 players have
    posted spawn-confirm, transitions to status='canceled' with reason
    'assembly_timeout' so all 4 clients can bail back to menu."""
    try:
        sid_uuid = UUID(series_id)
    except (ValueError, TypeError):
        raise HTTPException(400, "Invalid series_id")

    row = await db.execute(
        text("""
            SELECT id, status, created_at, spawn_confirmations,
                   invalidation_reason, completed_at,
                   dc_grace_until, dc_team_remaining, dc_player_id,
                   t1_series_wins, t2_series_wins
              FROM team_series
             WHERE id = :sid
        """),
        {"sid": sid_uuid},
    )
    r = row.first()
    if r is None:
        raise HTTPException(404, "Series not found")

    s_status = r[1]
    s_created = r[2]
    s_confirms = int(r[3] or 0)
    s_reason = r[4]
    s_dc_grace_until = r[6]
    s_dc_team = r[7]
    s_dc_player = r[8]

    age_seconds = (datetime.now(timezone.utc) - s_created).total_seconds()

    # Auto-cancel if the assembly deadline has passed and we still don't have 4.
    if (
        s_status == "active"
        and s_confirms < 4
        and age_seconds > _ASSEMBLY_DEADLINE_SECONDS
    ):
        await db.execute(
            text("""
                UPDATE team_series
                   SET status = 'canceled',
                       invalidated_at = NOW(),
                       invalidation_reason = 'assembly_timeout'
                 WHERE id = :sid AND status = 'active'
            """),
            {"sid": sid_uuid},
        )
        await db.commit()
        return {
            "status": "canceled",
            "reason": "assembly_timeout",
            "confirmations": s_confirms,
            "expected": 4,
            "age_seconds": int(age_seconds),
            "deadline_seconds": _ASSEMBLY_DEADLINE_SECONDS,
        }

    # 5-min sticky-team requeue grace window: if the deadline has passed and
    # the series is still flagged dc_paused, resolve it. The non-DC team takes
    # the series win by forfeit (their 2 members were ready to keep going).
    dc_grace_seconds_remaining = 0
    if s_dc_grace_until is not None:
        dc_grace_seconds_remaining = max(0, int((s_dc_grace_until - datetime.now(timezone.utc)).total_seconds()))
        if dc_grace_seconds_remaining == 0 and s_status == "dc_paused":
            # Grace expired without the original 4 re-queueing. Forfeit-win
            # to whichever team was still around.
            await db.execute(
                text("""
                    UPDATE team_series
                       SET status = 'completed',
                           winner_team = COALESCE(:wt, winner_team),
                           completed_at = NOW(),
                           invalidation_reason = 'dc_forfeit'
                     WHERE id = :sid AND status = 'dc_paused'
                """),
                {"sid": sid_uuid, "wt": s_dc_team},
            )
            await db.commit()
            return {
                "status": "completed",
                "reason": "dc_forfeit",
                "winner_team": s_dc_team,
                "confirmations": s_confirms,
                "expected": 4,
                "age_seconds": int(age_seconds),
                "deadline_seconds": _ASSEMBLY_DEADLINE_SECONDS,
                "dc_grace_seconds_remaining": 0,
            }

    return {
        "status": s_status,
        "reason": s_reason,
        "confirmations": s_confirms,
        "expected": 4,
        "age_seconds": int(age_seconds),
        "deadline_seconds": _ASSEMBLY_DEADLINE_SECONDS,
        "dc_grace_seconds_remaining": dc_grace_seconds_remaining,
        "dc_team_remaining": s_dc_team,
        "dc_player_id": str(s_dc_player) if s_dc_player else None,
        "t1_series_wins": int(r[9] or 0),
        "t2_series_wins": int(r[10] or 0),
    }


_DC_GRACE_SECONDS = 300  # 5-minute sticky-team requeue window


def _verify_team_dc_hmac(steam_id: str, series_id: str, dc_player_steam_id: str, signature: str) -> bool:
    """HMAC for team-DC reports: sha256(secret, "{reporter}:{series}:{dc_player}:dc")."""
    if not MATCH_HMAC_SECRET:
        return True
    expected = hmac.new(
        MATCH_HMAC_SECRET.encode(),
        f"{steam_id}:{series_id}:{dc_player_steam_id}:dc".encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")


@app.post("/api/v1/team/series/{series_id}/report-dc", tags=["Team Matches"])
async def team_series_report_dc(
    series_id: str,
    reporter_steam_id: str = Query(...),
    dc_player_steam_id: str = Query(...),
    t1_points_total: int = Query(0, ge=0),
    t2_points_total: int = Query(0, ge=0),
    hmac_sig: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Mid-series disconnect report. The 2v2 DC rule: if the abandoned match
    had >=2 total points scored across both teams, award the match win to the
    non-DC team (different from 1v1 which usually cancels). Series stays
    active but flips to status='dc_paused' for 5 minutes — if the same 4
    re-queue within that window the matchmaker resumes the existing series;
    otherwise the team that was still around takes the series by forfeit
    (handled by the state-poll endpoint when the deadline expires)."""
    if not _verify_team_dc_hmac(reporter_steam_id, series_id, dc_player_steam_id, hmac_sig):
        raise HTTPException(403, "Invalid DC report signature")
    try:
        sid_uuid = UUID(series_id)
    except (ValueError, TypeError):
        raise HTTPException(400, "Invalid series_id")

    # Resolve players.
    pid_row = await db.execute(select(Player.id).where(Player.steam_id == dc_player_steam_id))
    dc_pid = pid_row.scalar_one_or_none()
    if dc_pid is None:
        raise HTTPException(404, "DC'd player unknown")

    s_row = await db.execute(
        text("""
            SELECT id, status, t1a_id, t1b_id, t2a_id, t2b_id,
                   t1_series_wins, t2_series_wins
              FROM team_series WHERE id = :sid
        """),
        {"sid": sid_uuid},
    )
    s = s_row.mappings().first()
    if s is None:
        raise HTTPException(404, "Series not found")
    if s["status"] not in ("active", "dc_paused"):
        return {"status": s["status"], "ignored": True}

    # Determine which team the DC'd player was on.
    dc_team = 1 if dc_pid in (s["t1a_id"], s["t1b_id"]) else 2 if dc_pid in (s["t2a_id"], s["t2b_id"]) else None
    if dc_team is None:
        raise HTTPException(400, "DC'd player isn't part of this series")
    other_team = 2 if dc_team == 1 else 1
    total_points = (t1_points_total or 0) + (t2_points_total or 0)

    # Award the match if any meaningful play happened (>= 2 total points).
    # Below that we treat it as a clean restart — no match recorded.
    if total_points >= 2:
        # Synthetic team_match row reflecting the forfeit.
        new_t1_wins = (s["t1_series_wins"] or 0) + (1 if other_team == 1 else 0)
        new_t2_wins = (s["t2_series_wins"] or 0) + (1 if other_team == 2 else 0)
        await db.execute(
            text("""
                INSERT INTO team_matches
                    (series_id, t1a_id, t1b_id, t2a_id, t2b_id,
                     t1_rounds_won, t2_rounds_won, t1_points_total, t2_points_total,
                     winner_team, dc_player_id, dc_at, ended_at, photon_room_id)
                VALUES
                    (:sid, :t1a, :t1b, :t2a, :t2b,
                     0, 0, :t1p, :t2p,
                     :wt, :dpid, NOW(), NOW(), 'dc_forfeit')
            """),
            {
                "sid": sid_uuid, "t1a": s["t1a_id"], "t1b": s["t1b_id"],
                "t2a": s["t2a_id"], "t2b": s["t2b_id"],
                "t1p": t1_points_total or 0, "t2p": t2_points_total or 0,
                "wt": other_team, "dpid": dc_pid,
            },
        )
        await db.execute(
            text("""
                UPDATE team_series
                   SET t1_series_wins = :t1w, t2_series_wins = :t2w
                 WHERE id = :sid
            """),
            {"sid": sid_uuid, "t1w": new_t1_wins, "t2w": new_t2_wins},
        )
        # If the series is now decided (someone has 2 wins in a BO3),
        # complete it directly. Otherwise drop into the 5-min grace window.
        if new_t1_wins >= 2 or new_t2_wins >= 2:
            await db.execute(
                text("""
                    UPDATE team_series
                       SET status = 'completed',
                           winner_team = :wt,
                           completed_at = NOW(),
                           invalidation_reason = 'dc_decided',
                           dc_player_id = :dpid
                     WHERE id = :sid
                """),
                {"sid": sid_uuid, "wt": other_team, "dpid": dc_pid},
            )
            await db.commit()
            return {"status": "completed", "winner_team": other_team, "reason": "dc_decided"}

    # Series isn't decided — start the sticky-team requeue grace.
    deadline = datetime.now(timezone.utc) + timedelta(seconds=_DC_GRACE_SECONDS)
    await db.execute(
        text("""
            UPDATE team_series
               SET status = 'dc_paused',
                   dc_grace_until = :gd,
                   dc_team_remaining = :ot,
                   dc_player_id = :dpid
             WHERE id = :sid
        """),
        {"sid": sid_uuid, "gd": deadline, "ot": other_team, "dpid": dc_pid},
    )
    await db.commit()
    return {
        "status": "dc_paused",
        "dc_team_remaining": other_team,
        "dc_grace_seconds_remaining": _DC_GRACE_SECONDS,
        "deadline": deadline.isoformat(),
    }


@app.post("/api/v1/team/matches", response_model=TeamMatchResponse, tags=["Team Matches"])
async def submit_team_match(report: TeamMatchReport, db: AsyncSession = Depends(get_db)):
    """Submitted by the lowest-Steam-ID participant after a 2v2 game ends.
    HMAC verifies the canonical 11-field message. On series completion, applies
    Glicko-2 update to all 4 players (each player has 2 opponents = the other team)."""
    if not _verify_team_hmac(report):
        raise HTTPException(403, "Invalid team match signature")
    try:
        series_uuid = UUID(report.series_id)
    except (ValueError, TypeError):
        raise HTTPException(400, "Invalid series_id format")
    # Sanity validations.
    steams = {report.t1a.steam_id, report.t1b.steam_id, report.t2a.steam_id, report.t2b.steam_id}
    if len(steams) != 4:
        raise HTTPException(400, "All four players must be distinct")
    if report.t1_rounds_won == report.t2_rounds_won:
        raise HTTPException(400, "Match must have a winner")
    if report.t1_rounds_won > 5 or report.t2_rounds_won > 5:
        raise HTTPException(400, "Invalid round count")
    expected_winner = 1 if report.t1_rounds_won > report.t2_rounds_won else 2
    if expected_winner != report.winner_team:
        raise HTTPException(400, "winner_team disagrees with rounds")
    if report.photon_room_id and "offline" in report.photon_room_id.lower():
        raise HTTPException(400, "Offline matches are not recorded")

    # Resolve players.
    p_t1a = await get_or_create_player(db, report.t1a.steam_id, report.t1a.display_name)
    p_t1b = await get_or_create_player(db, report.t1b.steam_id, report.t1b.display_name)
    p_t2a = await get_or_create_player(db, report.t2a.steam_id, report.t2a.display_name)
    p_t2b = await get_or_create_player(db, report.t2b.steam_id, report.t2b.display_name)

    # Series must exist and be active. Lock to prevent advance races.
    s_q = await db.execute(
        text("""SELECT * FROM team_series WHERE id = :sid FOR UPDATE"""),
        {"sid": series_uuid},
    )
    series = s_q.mappings().first()
    if not series:
        raise HTTPException(404, "team_series not found")
    if series["status"] != "active":
        raise HTTPException(400, f"team_series is {series['status']}")

    # Reporter
    by_steam = {report.t1a.steam_id: p_t1a, report.t1b.steam_id: p_t1b,
                report.t2a.steam_id: p_t2a, report.t2b.steam_id: p_t2b}
    reporter = by_steam.get(report.reported_by_steam_id)
    if not reporter:
        raise HTTPException(400, "Reporter must be one of the four participants")
    # 2v2 reporter clearly has the mod installed.
    await _mark_mod_seen(db, reporter)

    # First-match-of-series team_series slot alignment. The server's balancer
    # assigned team1/team2 at lock time, but the client's t1a/t1b/t2a/t2b
    # labels in the match report come from ROUNDS' in-game teamID — those
    # don't have to align. Re-stamp team_series.t1a_id/t1b_id/t2a_id/t2b_id
    # to mirror the report's grouping ONLY on the first match (so winner_team
    # increments + per-slot rating_change persistence stay consistent across
    # all 3 BO3 matches). Once any match is recorded, the slot mapping is
    # frozen and subsequent matches just have to use the same grouping.
    is_first_match = (series["t1_series_wins"] or 0) == 0 and (series["t2_series_wins"] or 0) == 0
    if is_first_match:
        client_t1_set = frozenset([p_t1a.id, p_t1b.id])
        server_t1_set = frozenset([series["t1a_id"], series["t1b_id"]])
        if client_t1_set != server_t1_set:
            await db.execute(
                text("""UPDATE team_series
                       SET t1a_id=:t1a, t1b_id=:t1b, t2a_id=:t2a, t2b_id=:t2b
                       WHERE id = :sid"""),
                {"sid": series_uuid,
                 "t1a": p_t1a.id, "t1b": p_t1b.id,
                 "t2a": p_t2a.id, "t2b": p_t2b.id},
            )
            # Re-read for downstream slot lookups.
            s_q2 = await db.execute(
                text("SELECT * FROM team_series WHERE id = :sid"), {"sid": series_uuid},
            )
            series = s_q2.mappings().first()
            print(f"[TEAM-MATCH] series {series_uuid} slots realigned to client grouping")

    # Insert team_matches row. is_ranked is server-authoritative for 2v2 since
    # the team_series row was created by /queue/poll's lock — by definition
    # all 4 players queued through ranked matchmaking. The client's matchIsRanked
    # heuristic is computed from the FIRST resolved peer's flags, which can
    # legitimately drop to false in 4-player rooms (only one peer is the "primary
    # opponent" the resolver picks). Forcing true here keeps the leaderboard +
    # series Glicko-update path aligned with the queue-was-ranked invariant.
    new_match = TeamMatch(
        series_id=series_uuid,
        t1a_id=p_t1a.id, t1b_id=p_t1b.id, t2a_id=p_t2a.id, t2b_id=p_t2b.id,
        t1_rounds_won=report.t1_rounds_won,
        t2_rounds_won=report.t2_rounds_won,
        t1_points_total=report.t1_points_total,
        t2_points_total=report.t2_points_total,
        winner_team=report.winner_team,
        t1a_fps_avg=(report.t1a_fps if (report.t1a_fps or 0) > 0 else None),
        t1b_fps_avg=(report.t1b_fps if (report.t1b_fps or 0) > 0 else None),
        t2a_fps_avg=(report.t2a_fps if (report.t2a_fps or 0) > 0 else None),
        t2b_fps_avg=(report.t2b_fps if (report.t2b_fps or 0) > 0 else None),
        duration_seconds=report.match_duration,
        photon_room_id=report.photon_room_id,
        game_version=report.game_version,
        region=report.region,
        hmac_signature=report.hmac_signature,
        reported_by=reporter.id,
        is_ranked=True,
        started_at=report.started_at,
    )
    db.add(new_match)
    await db.flush()

    # Card picks (4 lists)
    for player_obj, side in (
        (p_t1a, report.t1a), (p_t1b, report.t1b),
        (p_t2a, report.t2a), (p_t2b, report.t2b),
    ):
        for card in side.cards:
            db.add(TeamMatchCard(
                match_id=new_match.id,
                player_id=player_obj.id,
                card_name=card.card_name,
                card_rarity=card.card_rarity,
                pick_order=card.pick_order,
                round_number=card.round_number,
            ))

    # Per-match XP awards. Higher base than 1v1 so wins land in user's
    # ~800-900 band and losses near ~600. 100xp=1g auto-conversion still
    # applies (mirrors the 1v1 path) so a clean win also drops a few gold.
    # Per-series accumulator (tax slot positions in team_series so the F5 UI
    # can render +Ng/+Nxp beside each player's name in their own series).
    series_xp_by_pid: dict = {}
    series_gold_by_pid: dict = {}
    try:
        team_match_winner = report.winner_team
        for p in (p_t1a, p_t1b, p_t2a, p_t2b):
            p_team = 1 if p.id in (p_t1a.id, p_t1b.id) else 2
            won_match = (p_team == team_match_winner)
            xp = TEAM_MATCH_XP_BASE
            if won_match:
                xp = int(xp * TEAM_MATCH_WIN_MULT)
            old_xp_q = await db.execute(text("SELECT total_xp FROM players WHERE id = :pid"), {"pid": p.id})
            old_xp = old_xp_q.scalar() or 0
            new_xp = old_xp + xp
            await db.execute(
                text("UPDATE players SET total_xp = :new, "
                     "team_xp_earned = COALESCE(team_xp_earned,0) + :delta WHERE id = :pid"),
                {"new": new_xp, "delta": xp, "pid": p.id},
            )
            series_xp_by_pid[p.id] = series_xp_by_pid.get(p.id, 0) + xp
            # 100 XP = 1 gold conversion (mirrors submit_match logic).
            gold_delta = (new_xp // 100) - (old_xp // 100)
            if gold_delta > 0:
                await db.execute(
                    text("UPDATE players SET gold_earned = COALESCE(gold_earned,0) + :g, "
                         "team_gold_earned = COALESCE(team_gold_earned,0) + :g WHERE id = :pid"),
                    {"g": gold_delta, "pid": p.id},
                )
                db.add(GoldTransaction(
                    player_id=p.id, amount=gold_delta,
                    reason="team_xp", reference_id=str(new_match.id),
                ))
                series_gold_by_pid[p.id] = series_gold_by_pid.get(p.id, 0) + gold_delta
    except Exception as xpex:
        print(f"[TEAM-ECON] per-match XP failed for match {new_match.id}: {xpex}")

    # Roll the per-match awards into the team_series row's per-slot accumulators.
    try:
        slot_pid = {
            "t1a": series["t1a_id"], "t1b": series["t1b_id"],
            "t2a": series["t2a_id"], "t2b": series["t2b_id"],
        }
        await db.execute(text(
            "UPDATE team_series SET "
            "t1a_xp_earned = COALESCE(t1a_xp_earned,0) + :t1a_xp, "
            "t1b_xp_earned = COALESCE(t1b_xp_earned,0) + :t1b_xp, "
            "t2a_xp_earned = COALESCE(t2a_xp_earned,0) + :t2a_xp, "
            "t2b_xp_earned = COALESCE(t2b_xp_earned,0) + :t2b_xp, "
            "t1a_gold_earned = COALESCE(t1a_gold_earned,0) + :t1a_g, "
            "t1b_gold_earned = COALESCE(t1b_gold_earned,0) + :t1b_g, "
            "t2a_gold_earned = COALESCE(t2a_gold_earned,0) + :t2a_g, "
            "t2b_gold_earned = COALESCE(t2b_gold_earned,0) + :t2b_g "
            "WHERE id = :sid"
        ), {
            "sid": series_uuid,
            "t1a_xp": series_xp_by_pid.get(slot_pid["t1a"], 0),
            "t1b_xp": series_xp_by_pid.get(slot_pid["t1b"], 0),
            "t2a_xp": series_xp_by_pid.get(slot_pid["t2a"], 0),
            "t2b_xp": series_xp_by_pid.get(slot_pid["t2b"], 0),
            "t1a_g":  series_gold_by_pid.get(slot_pid["t1a"], 0),
            "t1b_g":  series_gold_by_pid.get(slot_pid["t1b"], 0),
            "t2a_g":  series_gold_by_pid.get(slot_pid["t2a"], 0),
            "t2b_g":  series_gold_by_pid.get(slot_pid["t2b"], 0),
        })
    except Exception as agex:
        print(f"[TEAM-ECON] per-series accumulator update failed: {agex}")

    # Advance series counters.
    if report.winner_team == 1:
        new_t1w = (series["t1_series_wins"] or 0) + 1
        new_t2w = series["t2_series_wins"] or 0
    else:
        new_t1w = series["t1_series_wins"] or 0
        new_t2w = (series["t2_series_wins"] or 0) + 1

    series_completed = new_t1w >= 2 or new_t2w >= 2
    series_status = "completed" if series_completed else "active"
    winner_team = (1 if new_t1w > new_t2w else 2) if series_completed else None

    rebalance_assignments: dict[str, int] | None = None
    new_ratings: dict[str, float] = {}

    if series_completed:
        await db.execute(
            text("""UPDATE team_series
                   SET t1_series_wins = :t1, t2_series_wins = :t2,
                       status = 'completed', winner_team = :w, completed_at = NOW()
                   WHERE id = :sid"""),
            {"t1": new_t1w, "t2": new_t2w, "w": winner_team, "sid": report.series_id},
        )
        # Settle 2v2 bets. Winning bets pay amount × odds; losing bets close
        # with payout=0. Mirrors the 1v1 bet settlement that runs on
        # ranked_series completion (in submit_match elsewhere).
        try:
            unsettled = (await db.execute(text("""
                SELECT b.id, b.player_id, b.amount, b.odds_multiplier, b.bet_on_team
                  FROM team_bets b
                 WHERE b.team_series_id = :sid AND b.settled_at IS NULL
            """), {"sid": series_uuid})).mappings().all()
            for b in unsettled:
                won = (b["bet_on_team"] == winner_team)
                payout = int(round(b["amount"] * b["odds_multiplier"])) if won else 0
                await db.execute(text("""
                    UPDATE team_bets
                       SET settled_at = NOW(), payout = :p
                     WHERE id = :id
                """), {"p": payout, "id": b["id"]})
                if payout > 0:
                    # Credit the bettor's gold.
                    await db.execute(text("""
                        UPDATE players
                           SET gold_earned = COALESCE(gold_earned, 0) + :p
                         WHERE id = :pid
                    """), {"p": payout, "pid": b["player_id"]})
                    db.add(GoldTransaction(
                        player_id=b["player_id"], amount=payout,
                        reason="team_bet_payout", reference_id=str(series_uuid),
                    ))
        except Exception as bex:
            # Don't let bet settlement failures block the team-match write.
            print(f"[TEAM-BET-SETTLE] error settling for series {series_uuid}: {bex}")
        # Apply Glicko-2 updates. Each player's "rating period" = this series.
        # Their two opponents are the two players on the other team.
        team1_ps = [p_t1a, p_t1b]
        team2_ps = [p_t2a, p_t2b]
        team1_won = (winner_team == 1)
        # Snapshot current ratings before any update.
        gids = [p_t1a.id, p_t1b.id, p_t2a.id, p_t2b.id]
        gres = await db.execute(
            text("SELECT player_id, rating, rating_deviation, volatility, peak_rating, completed_series "
                 "FROM glicko_ratings_2v2 WHERE player_id = ANY(:ids) FOR UPDATE"),
            {"ids": gids},
        )
        existing = {r["player_id"]: dict(r) for r in gres.mappings().all()}
        # Default rows for first-timers.
        for pid in gids:
            if pid not in existing:
                existing[pid] = {
                    "player_id": pid,
                    "rating": GLICKO2_DEFAULT_RATING,
                    "rating_deviation": GLICKO2_DEFAULT_RD,
                    "volatility": GLICKO2_DEFAULT_VOLATILITY,
                    "peak_rating": GLICKO2_DEFAULT_RATING,
                    "completed_series": 0,
                    "_new": True,
                }
        # Compute new ratings using PRE-update opponent values.
        def update_player(p, opps_pre, won: bool):
            opps = [(o["rating"], o["rating_deviation"], 1.0 if won else 0.0) for o in opps_pre]
            return calculate_new_rating(
                p["rating"], p["rating_deviation"], p["volatility"], opps, GLICKO2_TAU,
            )
        # Snapshot inputs first so each player's update sees the pre-update opp values.
        inputs = {pid: existing[pid] for pid in gids}
        results: dict[str, tuple[float, float, float]] = {}
        for p in team1_ps:
            results[p.id] = update_player(
                inputs[p.id],
                [inputs[p_t2a.id], inputs[p_t2b.id]],
                team1_won,
            )
        for p in team2_ps:
            results[p.id] = update_player(
                inputs[p.id],
                [inputs[p_t1a.id], inputs[p_t1b.id]],
                not team1_won,
            )
        # Persist.
        for pid, (new_r, new_rd, new_vol) in results.items():
            existing_pre = inputs[pid]
            new_peak = max(existing_pre.get("peak_rating") or new_r, new_r)
            if existing_pre.get("_new"):
                db.add(GlickoRating2v2(
                    player_id=pid,
                    rating=new_r,
                    rating_deviation=new_rd,
                    volatility=new_vol,
                    peak_rating=new_peak,
                    games_in_period=0,
                    completed_series=1,
                    last_calculated=datetime.now(timezone.utc),
                ))
            else:
                await db.execute(
                    text("""UPDATE glicko_ratings_2v2
                           SET rating=:r, rating_deviation=:rd, volatility=:v,
                               peak_rating=GREATEST(COALESCE(peak_rating,:r), :r),
                               completed_series = completed_series + 1,
                               last_calculated=NOW(), updated_at=NOW()
                           WHERE player_id=:pid"""),
                    {"r": new_r, "rd": new_rd, "v": new_vol, "pid": pid},
                )
            new_ratings[str(pid)] = round(new_r, 1)
        # Persist the per-player series Elo deltas in the team_series slot that
        # holds each player's player_id — NOT in the slot whose label happens to
        # match the report's t1a/t1b/t2a/t2b naming. The two can disagree
        # because the balancer assigns server-team1/team2 at lock time but
        # ROUNDS' in-game teamID (which the client uses to label t1a/t1b/t2a/t2b
        # in the report) is independent of that. Joining by player_id keeps the
        # team-matches history endpoint reading the correct rating_change for
        # each player no matter how the labels happen to align this game.
        delta_by_pid = {pid: round(results[pid][0] - inputs[pid]["rating"], 1) for pid in gids}
        slot_to_pid = {
            "t1a": series["t1a_id"], "t1b": series["t1b_id"],
            "t2a": series["t2a_id"], "t2b": series["t2b_id"],
        }
        await db.execute(
            text("""UPDATE team_series SET
                       t1a_rating_change = :t1a_d, t1b_rating_change = :t1b_d,
                       t2a_rating_change = :t2a_d, t2b_rating_change = :t2b_d
                   WHERE id = :sid"""),
            {
                "sid": series_uuid,
                "t1a_d": delta_by_pid[slot_to_pid["t1a"]],
                "t1b_d": delta_by_pid[slot_to_pid["t1b"]],
                "t2a_d": delta_by_pid[slot_to_pid["t2a"]],
                "t2b_d": delta_by_pid[slot_to_pid["t2b"]],
            },
        )

        # Series-completion gold: +50g winner, +25g loser. Also folded into
        # the team_series per-slot gold accumulator so the F5 panel can
        # render "+Ng / +Nxp" beside each player.
        bonus_by_pid = {}
        try:
            for p in (p_t1a, p_t1b, p_t2a, p_t2b):
                player_team = 1 if p.id in (p_t1a.id, p_t1b.id) else 2
                won_series = (player_team == winner_team)
                bonus = TEAM_SERIES_WIN_GOLD if won_series else TEAM_SERIES_LOSS_GOLD
                await db.execute(
                    text("UPDATE players SET gold_earned = COALESCE(gold_earned,0) + :g, "
                         "team_gold_earned = COALESCE(team_gold_earned,0) + :g WHERE id = :pid"),
                    {"g": bonus, "pid": p.id},
                )
                db.add(GoldTransaction(
                    player_id=p.id, amount=bonus,
                    reason=("team_series_win" if won_series else "team_series_loss"),
                    reference_id=str(series_uuid),
                ))
                bonus_by_pid[p.id] = bonus
            slot_pid = {
                "t1a": series["t1a_id"], "t1b": series["t1b_id"],
                "t2a": series["t2a_id"], "t2b": series["t2b_id"],
            }
            await db.execute(text(
                "UPDATE team_series SET "
                "t1a_gold_earned = COALESCE(t1a_gold_earned,0) + :t1a_g, "
                "t1b_gold_earned = COALESCE(t1b_gold_earned,0) + :t1b_g, "
                "t2a_gold_earned = COALESCE(t2a_gold_earned,0) + :t2a_g, "
                "t2b_gold_earned = COALESCE(t2b_gold_earned,0) + :t2b_g "
                "WHERE id = :sid"
            ), {
                "sid": series_uuid,
                "t1a_g": bonus_by_pid.get(slot_pid["t1a"], 0),
                "t1b_g": bonus_by_pid.get(slot_pid["t1b"], 0),
                "t2a_g": bonus_by_pid.get(slot_pid["t2a"], 0),
                "t2b_g": bonus_by_pid.get(slot_pid["t2b"], 0),
            })
        except Exception as gex:
            print(f"[TEAM-ECON] series-bonus gold failed for {series_uuid}: {gex}")

        # Free the queue rows so all 4 can re-queue.
        await db.execute(
            text("DELETE FROM team_queue WHERE series_id = :sid"),
            {"sid": series_uuid},
        )
    else:
        # Mid-series advance.
        await db.execute(
            text("""UPDATE team_series SET t1_series_wins = :t1, t2_series_wins = :t2 WHERE id = :sid"""),
            {"t1": new_t1w, "t2": new_t2w, "sid": report.series_id},
        )

        # ── Auto-balance between matches in an auto-balanced series ──
        # When the previous match was lopsided (point margin >= AUTO_BALANCE_SWAP_MARGIN)
        # AND the series was originally auto-balanced (not a manual pick lobby),
        # swap the weakest winner with the strongest loser so the next match
        # plays with reshuffled teams. The rebalance only applies to the NEXT
        # match — the client gets a `rebalance_assignments` payload on the
        # response and updates each player's TeamID before round 1 starts.
        try:
            was_auto = bool(series["was_auto_balanced"]) if "was_auto_balanced" in series else True
            margin = abs(int(report.t1_points_total or 0) - int(report.t2_points_total or 0))
            if was_auto and margin >= AUTO_BALANCE_SWAP_MARGIN:
                # Pull each player's current effective rating (2v2 if trusted, else 1v1 fallback).
                pids = [p_t1a.id, p_t1b.id, p_t2a.id, p_t2b.id]
                rate_q = await db.execute(
                    text("""
                        SELECT p.id AS pid,
                               COALESCE(g2.rating, 1500.0) AS r2,
                               COALESCE(g2.rating_deviation, 350.0) AS rd2,
                               COALESCE(g2.completed_series, 0) AS cs,
                               COALESCE(g1.rating, 1500.0) AS r1
                          FROM players p
                          LEFT JOIN glicko_ratings_2v2 g2 ON g2.player_id = p.id
                          LEFT JOIN glicko_ratings    g1 ON g1.player_id = p.id
                         WHERE p.id = ANY(:ids)
                    """),
                    {"ids": pids},
                )
                rate_by_pid = {r["pid"]: _team_balance_rating(
                    float(r["r2"]), int(r["cs"]), float(r["r1"]), float(r["rd2"])
                ) for r in rate_q.mappings().all()}

                winner_team_match = report.winner_team
                if winner_team_match == 1:
                    winners = [(p_t1a.id, rate_by_pid.get(p_t1a.id, 1500.0)),
                               (p_t1b.id, rate_by_pid.get(p_t1b.id, 1500.0))]
                    losers  = [(p_t2a.id, rate_by_pid.get(p_t2a.id, 1500.0)),
                               (p_t2b.id, rate_by_pid.get(p_t2b.id, 1500.0))]
                else:
                    winners = [(p_t2a.id, rate_by_pid.get(p_t2a.id, 1500.0)),
                               (p_t2b.id, rate_by_pid.get(p_t2b.id, 1500.0))]
                    losers  = [(p_t1a.id, rate_by_pid.get(p_t1a.id, 1500.0)),
                               (p_t1b.id, rate_by_pid.get(p_t1b.id, 1500.0))]
                # Weakest winner + strongest loser swap.
                weakest_winner = min(winners, key=lambda t: t[1])[0]
                strongest_loser = max(losers, key=lambda t: t[1])[0]

                # Build the new (post-swap) team rosters.
                t1_ids = [p_t1a.id, p_t1b.id]
                t2_ids = [p_t2a.id, p_t2b.id]
                new_t1 = [pid for pid in t1_ids if pid != weakest_winner and pid != strongest_loser]
                new_t2 = [pid for pid in t2_ids if pid != weakest_winner and pid != strongest_loser]
                if winner_team_match == 1:
                    # weakest_winner was on t1, strongest_loser was on t2 → swap them.
                    new_t1.append(strongest_loser); new_t2.append(weakest_winner)
                else:
                    new_t2.append(strongest_loser); new_t1.append(weakest_winner)

                # Canonicalize within-team order by steam_id (matches lock-time sort).
                pid_to_steam = {
                    p_t1a.id: p_t1a.steam_id, p_t1b.id: p_t1b.steam_id,
                    p_t2a.id: p_t2a.steam_id, p_t2b.id: p_t2b.steam_id,
                }
                new_t1.sort(key=lambda pid: pid_to_steam[pid])
                new_t2.sort(key=lambda pid: pid_to_steam[pid])

                # Persist new slot order on team_series.
                await db.execute(
                    text("""UPDATE team_series
                              SET t1a_id = :t1a, t1b_id = :t1b,
                                  t2a_id = :t2a, t2b_id = :t2b,
                                  rebalance_count = COALESCE(rebalance_count, 0) + 1
                            WHERE id = :sid"""),
                    {"t1a": new_t1[0], "t1b": new_t1[1],
                     "t2a": new_t2[0], "t2b": new_t2[1],
                     "sid": series_uuid},
                )
                # Update queue rows so /poll reflects the new team_assigned.
                await db.execute(
                    text("""UPDATE team_queue
                              SET team_assigned = CASE
                                                    WHEN player_id = ANY(:t1) THEN 1
                                                    ELSE 2
                                                  END
                            WHERE series_id = :sid"""),
                    {"t1": new_t1, "sid": series_uuid},
                )

                # Build rebalance_assignments keyed by Steam ID (the client
                # uses the Steam ID it knows for each peer to look up the new
                # team and update its local Player.TeamID + spawn / body color).
                steam_to_pid = {v: k for k, v in pid_to_steam.items()}
                rebalance_assignments = {}
                for pid in new_t1:
                    rebalance_assignments[pid_to_steam[pid]] = 1
                for pid in new_t2:
                    rebalance_assignments[pid_to_steam[pid]] = 2
                print(f"[TEAM-REBALANCE] series={series_uuid} margin={margin} swapped: "
                      f"weakest_winner={pid_to_steam[weakest_winner]} ↔ strongest_loser={pid_to_steam[strongest_loser]}")
        except Exception as rex:
            print(f"[TEAM-REBALANCE] error: {rex}")

    await db.commit()

    # Build response: series_score from the reporter's team perspective.
    reporter_team = 1 if reporter.id in (p_t1a.id, p_t1b.id) else 2
    if reporter_team == 1:
        score_str = f"{new_t1w}-{new_t2w}"
    else:
        score_str = f"{new_t2w}-{new_t1w}"

    return TeamMatchResponse(
        match_id=new_match.id,
        series_id=series_uuid,
        series_status=series_status,
        series_score=score_str,
        winner_team=(winner_team or report.winner_team),
        rebalance_assignments=rebalance_assignments,
        new_t1a_rating=new_ratings.get(str(p_t1a.id)),
        new_t1b_rating=new_ratings.get(str(p_t1b.id)),
        new_t2a_rating=new_ratings.get(str(p_t2a.id)),
        new_t2b_rating=new_ratings.get(str(p_t2b.id)),
    )


@app.get("/api/v1/team/players/{steam_id}/team-stats", response_model=TeamStatsResponse, tags=["Team Matches"])
async def get_player_team_stats(steam_id: str, db: AsyncSession = Depends(get_db)):
    """Per-player 2v2 stats — drives the My Stats tab 2v2 row + 2v2 leaderboard
    detail panel. Includes current series-level streak (positive=W streak,
    negative=L streak) by walking completed series in time order."""
    result = await db.execute(select(Player).where(Player.steam_id == steam_id))
    player = result.scalar_one_or_none()
    if not player:
        raise HTTPException(404, "Player not found")
    g_q = await db.execute(select(GlickoRating2v2).where(GlickoRating2v2.player_id == player.id))
    g = g_q.scalar_one_or_none()
    rating = g.rating if g else GLICKO2_DEFAULT_RATING
    rd = g.rating_deviation if g else GLICKO2_DEFAULT_RD
    peak = g.peak_rating if (g and g.peak_rating) else rating
    completed_series = g.completed_series if g else 0

    # Series wins/losses — UNION across all 4 slots.
    sw_q = await db.execute(
        text("""
            SELECT
                SUM(CASE WHEN s.winner_team = 1 AND :pid IN (s.t1a_id, s.t1b_id) THEN 1
                         WHEN s.winner_team = 2 AND :pid IN (s.t2a_id, s.t2b_id) THEN 1
                         ELSE 0 END) AS wins,
                SUM(CASE WHEN s.winner_team = 1 AND :pid IN (s.t2a_id, s.t2b_id) THEN 1
                         WHEN s.winner_team = 2 AND :pid IN (s.t1a_id, s.t1b_id) THEN 1
                         ELSE 0 END) AS losses
            FROM team_series s
            WHERE s.status = 'completed'
              AND :pid IN (s.t1a_id, s.t1b_id, s.t2a_id, s.t2b_id)
        """),
        {"pid": player.id},
    )
    sw_row = sw_q.mappings().first()
    series_wins = int(sw_row["wins"] or 0)
    series_losses = int(sw_row["losses"] or 0)

    # Match wins/losses inside team_matches.
    mw_q = await db.execute(
        text("""
            SELECT
                SUM(CASE WHEN m.winner_team = 1 AND :pid IN (m.t1a_id, m.t1b_id) THEN 1
                         WHEN m.winner_team = 2 AND :pid IN (m.t2a_id, m.t2b_id) THEN 1
                         ELSE 0 END) AS wins,
                SUM(CASE WHEN m.winner_team = 1 AND :pid IN (m.t2a_id, m.t2b_id) THEN 1
                         WHEN m.winner_team = 2 AND :pid IN (m.t1a_id, m.t1b_id) THEN 1
                         ELSE 0 END) AS losses
            FROM team_matches m
            WHERE m.invalidated_at IS NULL
              AND :pid IN (m.t1a_id, m.t1b_id, m.t2a_id, m.t2b_id)
        """),
        {"pid": player.id},
    )
    mw_row = mw_q.mappings().first()
    match_wins = int(mw_row["wins"] or 0)
    match_losses = int(mw_row["losses"] or 0)

    # Series streak — walk completed series newest first, count consecutive same-result.
    streak_q = await db.execute(
        text("""
            SELECT s.winner_team,
                   CASE WHEN :pid IN (s.t1a_id, s.t1b_id) THEN 1 ELSE 2 END AS my_team
            FROM team_series s
            WHERE s.status = 'completed'
              AND :pid IN (s.t1a_id, s.t1b_id, s.t2a_id, s.t2b_id)
            ORDER BY s.completed_at DESC
            LIMIT 50
        """),
        {"pid": player.id},
    )
    rows = streak_q.mappings().all()
    streak = 0
    last_was_win = None
    for r in rows:
        won = (r["winner_team"] == r["my_team"])
        if last_was_win is None:
            last_was_win = won
            streak = 1 if won else -1
        elif won == last_was_win:
            streak = streak + 1 if won else streak - 1
        else:
            break

    total_series = series_wins + series_losses
    return TeamStatsResponse(
        steam_id=steam_id,
        display_name=player.display_name,
        rating=round(rating, 1),
        rating_deviation=round(rd, 1),
        peak_rating=round(peak, 1),
        completed_series=completed_series,
        series_wins=series_wins,
        series_losses=series_losses,
        series_win_rate=round(series_wins / total_series, 4) if total_series > 0 else 0.0,
        match_wins=match_wins,
        match_losses=match_losses,
        current_streak=streak,
    )


@app.get("/api/v1/team/players/{steam_id}/team-matches", response_model=list[TeamMatchHistoryEntry], tags=["Team Matches"])
async def get_player_team_matches(
    steam_id: str,
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Recent 2v2 matches played by a given player. Used by the F5 2v2 tab
    history list. Renders the 4 names + win/loss + series score + per-player
    cards + FPS averages."""
    result = await db.execute(select(Player).where(Player.steam_id == steam_id))
    player = result.scalar_one_or_none()
    if not player:
        raise HTTPException(404, "Player not found")

    q = text("""
        SELECT
            tm.id AS match_id, tm.ended_at, tm.winner_team, tm.series_id,
            tm.t1_rounds_won, tm.t2_rounds_won,
            tm.t1_points_total, tm.t2_points_total,
            tm.t1a_id, tm.t1b_id, tm.t2a_id, tm.t2b_id,
            tm.t1a_fps_avg, tm.t1b_fps_avg, tm.t2a_fps_avg, tm.t2b_fps_avg,
            p1a.steam_id AS t1a_sid, p1a.display_name AS t1a_name,
            p1b.steam_id AS t1b_sid, p1b.display_name AS t1b_name,
            p2a.steam_id AS t2a_sid, p2a.display_name AS t2a_name,
            p2b.steam_id AS t2b_sid, p2b.display_name AS t2b_name,
            ts.t1_series_wins, ts.t2_series_wins, ts.winner_team AS series_winner_team,
            ts.t1a_id AS s_t1a, ts.t1b_id AS s_t1b,
            CASE
                WHEN :pid IN (ts.t1a_id, ts.t1b_id) THEN
                    CASE WHEN ts.t1a_id = :pid THEN ts.t1a_rating_change ELSE ts.t1b_rating_change END
                ELSE
                    CASE WHEN ts.t2a_id = :pid THEN ts.t2a_rating_change ELSE ts.t2b_rating_change END
            END AS rating_change
        FROM team_matches tm
        JOIN players p1a ON p1a.id = tm.t1a_id
        JOIN players p1b ON p1b.id = tm.t1b_id
        JOIN players p2a ON p2a.id = tm.t2a_id
        JOIN players p2b ON p2b.id = tm.t2b_id
        LEFT JOIN team_series ts ON ts.id = tm.series_id
        WHERE :pid IN (tm.t1a_id, tm.t1b_id, tm.t2a_id, tm.t2b_id)
          AND tm.invalidated_at IS NULL
        ORDER BY tm.ended_at DESC
        LIMIT :lim
    """)
    rows = (await db.execute(q, {"pid": player.id, "lim": limit})).mappings().all()

    entries: list[TeamMatchHistoryEntry] = []
    for r in rows:
        my_team = 1 if player.id in (r["t1a_id"], r["t1b_id"]) else 2
        won = (r["winner_team"] == my_team)
        # Card picks per (match_id, player_id)
        cards_q = await db.execute(
            text("""SELECT player_id, card_name, card_rarity, pick_order, round_number
                   FROM team_match_cards
                   WHERE match_id = :mid
                   ORDER BY player_id, round_number, pick_order"""),
            {"mid": r["match_id"]},
        )
        cards_by_player: dict[str, list] = {}
        for c in cards_q.mappings().all():
            pid_str = str(c["player_id"])
            cards_by_player.setdefault(pid_str, []).append({
                "card_name": c["card_name"], "card_rarity": c["card_rarity"],
                "pick_order": c["pick_order"], "round_number": c["round_number"],
            })
        # Re-key by Steam ID for the response (client doesn't know UUIDs).
        pid_to_sid = {
            str(r["t1a_id"]): r["t1a_sid"], str(r["t1b_id"]): r["t1b_sid"],
            str(r["t2a_id"]): r["t2a_sid"], str(r["t2b_id"]): r["t2b_sid"],
        }
        cards_by_steam: dict[str, list] = {}
        for pid_str, lst in cards_by_player.items():
            sid_for = pid_to_sid.get(pid_str)
            if sid_for:
                cards_by_steam[sid_for] = lst

        fps_by_steam: dict[str, int] = {}
        if r["t1a_fps_avg"]: fps_by_steam[r["t1a_sid"]] = int(r["t1a_fps_avg"])
        if r["t1b_fps_avg"]: fps_by_steam[r["t1b_sid"]] = int(r["t1b_fps_avg"])
        if r["t2a_fps_avg"]: fps_by_steam[r["t2a_sid"]] = int(r["t2a_fps_avg"])
        if r["t2b_fps_avg"]: fps_by_steam[r["t2b_sid"]] = int(r["t2b_fps_avg"])

        # Series score from caller's team perspective.
        series_score = None
        if r["series_id"] is not None and r["t1_series_wins"] is not None:
            t1w, t2w = r["t1_series_wins"] or 0, r["t2_series_wins"] or 0
            # Determine which team the caller was on FOR THIS SERIES (the series
            # uses balancer-time assignments; team_assigned in the match row may
            # have been rebalanced — we don't rebalance yet so they're identical
            # but keeping the logic explicit so future Phase 3 changes don't break it).
            in_series_team1 = player.id in (r["s_t1a"], r["s_t1b"])
            if in_series_team1:
                series_score = f"{t1w}-{t2w}"
            else:
                series_score = f"{t2w}-{t1w}"

        rating_change = None
        if r["rating_change"] is not None:
            rating_change = float(r["rating_change"])

        entries.append(TeamMatchHistoryEntry(
            match_id=r["match_id"],
            series_id=str(r["series_id"]) if r["series_id"] else "",
            ended_at=r["ended_at"],
            won=won,
            my_team=my_team,
            t1a_steam_id=r["t1a_sid"], t1a_name=r["t1a_name"],
            t1b_steam_id=r["t1b_sid"], t1b_name=r["t1b_name"],
            t2a_steam_id=r["t2a_sid"], t2a_name=r["t2a_name"],
            t2b_steam_id=r["t2b_sid"], t2b_name=r["t2b_name"],
            t1_rounds_won=r["t1_rounds_won"],
            t2_rounds_won=r["t2_rounds_won"],
            t1_points_total=r["t1_points_total"] or 0,
            t2_points_total=r["t2_points_total"] or 0,
            cards_by_player=cards_by_steam,
            series_score=series_score,
            series_rating_change=rating_change,
            fps_by_player=fps_by_steam,
        ))
    return entries


@app.get("/api/v1/team/series/recent", tags=["Team Matches"])
async def team_series_recent(minutes: int = Query(5, ge=1, le=60), db: AsyncSession = Depends(get_db)):
    """Series completed in the last N minutes — drives the Discord 2v2 announcement.
    Returns names + ratings + Elo changes per player so the bot can render the embed
    without further fetches."""
    q = text("""
        SELECT
            s.id AS series_id,
            s.completed_at,
            s.t1_series_wins, s.t2_series_wins, s.winner_team,
            s.t1a_rating_change, s.t1b_rating_change, s.t2a_rating_change, s.t2b_rating_change,
            p1a.steam_id AS t1a_sid, p1a.display_name AS t1a_name, p1a.discord_id AS t1a_did,
            p1b.steam_id AS t1b_sid, p1b.display_name AS t1b_name, p1b.discord_id AS t1b_did,
            p2a.steam_id AS t2a_sid, p2a.display_name AS t2a_name, p2a.discord_id AS t2a_did,
            p2b.steam_id AS t2b_sid, p2b.display_name AS t2b_name, p2b.discord_id AS t2b_did,
            g1a.rating AS t1a_rating, g1b.rating AS t1b_rating,
            g2a.rating AS t2a_rating, g2b.rating AS t2b_rating
        FROM team_series s
        JOIN players p1a ON p1a.id = s.t1a_id
        JOIN players p1b ON p1b.id = s.t1b_id
        JOIN players p2a ON p2a.id = s.t2a_id
        JOIN players p2b ON p2b.id = s.t2b_id
        LEFT JOIN glicko_ratings_2v2 g1a ON g1a.player_id = s.t1a_id
        LEFT JOIN glicko_ratings_2v2 g1b ON g1b.player_id = s.t1b_id
        LEFT JOIN glicko_ratings_2v2 g2a ON g2a.player_id = s.t2a_id
        LEFT JOIN glicko_ratings_2v2 g2b ON g2b.player_id = s.t2b_id
        WHERE s.status = 'completed'
          AND s.completed_at > NOW() - INTERVAL '1 minute' * :mins
        ORDER BY s.completed_at DESC
    """)
    rows = (await db.execute(q, {"mins": minutes})).mappings().all()
    return {"series": [
        {
            "series_id": str(r["series_id"]),
            "completed_at": r["completed_at"].isoformat() if r["completed_at"] else None,
            "winner_team": r["winner_team"],
            "t1_series_wins": r["t1_series_wins"], "t2_series_wins": r["t2_series_wins"],
            "t1a": {"steam_id": r["t1a_sid"], "name": r["t1a_name"], "discord_id": r["t1a_did"],
                    "rating": float(r["t1a_rating"]) if r["t1a_rating"] is not None else 1500.0,
                    "rating_change": float(r["t1a_rating_change"] or 0)},
            "t1b": {"steam_id": r["t1b_sid"], "name": r["t1b_name"], "discord_id": r["t1b_did"],
                    "rating": float(r["t1b_rating"]) if r["t1b_rating"] is not None else 1500.0,
                    "rating_change": float(r["t1b_rating_change"] or 0)},
            "t2a": {"steam_id": r["t2a_sid"], "name": r["t2a_name"], "discord_id": r["t2a_did"],
                    "rating": float(r["t2a_rating"]) if r["t2a_rating"] is not None else 1500.0,
                    "rating_change": float(r["t2a_rating_change"] or 0)},
            "t2b": {"steam_id": r["t2b_sid"], "name": r["t2b_name"], "discord_id": r["t2b_did"],
                    "rating": float(r["t2b_rating"]) if r["t2b_rating"] is not None else 1500.0,
                    "rating_change": float(r["t2b_rating_change"] or 0)},
        }
        for r in rows
    ]}


@app.get("/api/v1/team/all-series-paged", tags=["Team Matches"])
async def team_all_series_paged(
    page: int = Query(0, ge=0),
    page_size: int = Query(3, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Paginated feed of every completed 2v2 series. Drives the F5 'Recent 2v2
    Series' panel. Each series includes per-slot ratings + rating deltas +
    titles + per-slot gold/XP earned in this series, plus the matches array
    with per-player card picks. Replaces the per-player /team-matches feed
    so non-participants can also browse the global series history."""
    total_q = await db.execute(text("SELECT COUNT(*) FROM team_series WHERE status='completed'"))
    total = total_q.scalar() or 0

    series_q = text("""
        SELECT s.id AS series_id, s.completed_at, s.created_at,
               s.t1_series_wins, s.t2_series_wins, s.winner_team,
               s.t1a_id, s.t1b_id, s.t2a_id, s.t2b_id,
               s.t1a_rating_change, s.t1b_rating_change, s.t2a_rating_change, s.t2b_rating_change,
               s.t1a_gold_earned, s.t1b_gold_earned, s.t2a_gold_earned, s.t2b_gold_earned,
               s.t1a_xp_earned,   s.t1b_xp_earned,   s.t2a_xp_earned,   s.t2b_xp_earned,
               p1a.steam_id AS t1a_sid, p1a.display_name AS t1a_name, ti1a.name AS t1a_title, ti1a.preview_color AS t1a_title_color,
               p1b.steam_id AS t1b_sid, p1b.display_name AS t1b_name, ti1b.name AS t1b_title, ti1b.preview_color AS t1b_title_color,
               p2a.steam_id AS t2a_sid, p2a.display_name AS t2a_name, ti2a.name AS t2a_title, ti2a.preview_color AS t2a_title_color,
               p2b.steam_id AS t2b_sid, p2b.display_name AS t2b_name, ti2b.name AS t2b_title, ti2b.preview_color AS t2b_title_color,
               g1a.rating AS t1a_rating, g1b.rating AS t1b_rating,
               g2a.rating AS t2a_rating, g2b.rating AS t2b_rating
          FROM team_series s
          JOIN players p1a ON p1a.id = s.t1a_id
          JOIN players p1b ON p1b.id = s.t1b_id
          JOIN players p2a ON p2a.id = s.t2a_id
          JOIN players p2b ON p2b.id = s.t2b_id
          LEFT JOIN shop_items ti1a ON ti1a.id = p1a.active_title_id
          LEFT JOIN shop_items ti1b ON ti1b.id = p1b.active_title_id
          LEFT JOIN shop_items ti2a ON ti2a.id = p2a.active_title_id
          LEFT JOIN shop_items ti2b ON ti2b.id = p2b.active_title_id
          LEFT JOIN glicko_ratings_2v2 g1a ON g1a.player_id = s.t1a_id
          LEFT JOIN glicko_ratings_2v2 g1b ON g1b.player_id = s.t1b_id
          LEFT JOIN glicko_ratings_2v2 g2a ON g2a.player_id = s.t2a_id
          LEFT JOIN glicko_ratings_2v2 g2b ON g2b.player_id = s.t2b_id
         WHERE s.status = 'completed'
         ORDER BY s.completed_at DESC
         LIMIT :lim OFFSET :off
    """)
    rows = (await db.execute(series_q, {"lim": page_size, "off": page * page_size})).mappings().all()

    out_series = []
    for r in rows:
        # Per-series matches.
        m_q = text("""
            SELECT id AS match_id, ended_at, t1_rounds_won, t2_rounds_won,
                   t1_points_total, t2_points_total
              FROM team_matches
             WHERE series_id = :sid AND invalidated_at IS NULL
             ORDER BY ended_at ASC
        """)
        m_rows = (await db.execute(m_q, {"sid": r["series_id"]})).mappings().all()
        matches = []
        # Per-(match, player) cards lookup.
        match_ids = [m["match_id"] for m in m_rows]
        cards_by_match: dict = {}
        if match_ids:
            c_q = text("""
                SELECT match_id, player_id, card_name, pick_order, round_number
                  FROM team_match_cards
                 WHERE match_id = ANY(:mids)
                 ORDER BY match_id, player_id, round_number, pick_order
            """)
            c_rows = (await db.execute(c_q, {"mids": match_ids})).mappings().all()
            pid_to_sid = {
                str(r["t1a_id"]): r["t1a_sid"], str(r["t1b_id"]): r["t1b_sid"],
                str(r["t2a_id"]): r["t2a_sid"], str(r["t2b_id"]): r["t2b_sid"],
            }
            for c in c_rows:
                mid_key = str(c["match_id"])
                sid_for = pid_to_sid.get(str(c["player_id"]))
                if not sid_for: continue
                cards_by_match.setdefault(mid_key, {}).setdefault(sid_for, []).append(c["card_name"])
        for m in m_rows:
            matches.append({
                "match_id": str(m["match_id"]),
                "ended_at": m["ended_at"].isoformat() if m["ended_at"] else None,
                "t1_rounds_won": m["t1_rounds_won"], "t2_rounds_won": m["t2_rounds_won"],
                "t1_points_total": m["t1_points_total"] or 0, "t2_points_total": m["t2_points_total"] or 0,
                "cards_by_player": cards_by_match.get(str(m["match_id"]), {}),
            })

        def slot(prefix):
            return {
                "steam_id": r[f"{prefix}_sid"], "name": r[f"{prefix}_name"],
                "title": r[f"{prefix}_title"], "title_color": r[f"{prefix}_title_color"],
                "rating": float(r[f"{prefix}_rating"]) if r[f"{prefix}_rating"] is not None else 1500.0,
                "rating_change": float(r[f"{prefix}_rating_change"] or 0),
                "gold_earned": int(r[f"{prefix}_gold_earned"] or 0),
                "xp_earned":   int(r[f"{prefix}_xp_earned"] or 0),
            }
        out_series.append({
            "series_id": str(r["series_id"]),
            "completed_at": r["completed_at"].isoformat() if r["completed_at"] else None,
            "winner_team": r["winner_team"],
            "t1_series_wins": r["t1_series_wins"], "t2_series_wins": r["t2_series_wins"],
            "t1a": slot("t1a"), "t1b": slot("t1b"),
            "t2a": slot("t2a"), "t2b": slot("t2b"),
            "matches": matches,
        })

    return {
        "series": out_series,
        "page": page, "page_size": page_size, "total": total,
        "total_pages": (total + page_size - 1) // page_size if total else 0,
    }


@app.get("/api/v1/team/leaderboard", response_model=Team2v2LeaderboardResponse, tags=["Team Matches"])
async def team_leaderboard(
    limit: int = Query(200, ge=1, le=500),
    min_series: int = Query(1, ge=0),
    sort_by: str = Query("rating"),
    db: AsyncSession = Depends(get_db),
):
    """Top players by 2v2 Glicko rating. Includes title, avg teammate elo,
    total 2v2 gold + XP earned. sort_by accepts: rating, wins, win_rate,
    avg_teammate_elo, team_gold_earned, team_xp_earned."""
    sort_map = {
        "rating": "g2.rating DESC",
        "wins": "wins DESC",
        "win_rate": "win_rate DESC",
        "avg_teammate_elo": "avg_teammate_elo DESC",
        "team_gold_earned": "team_gold_earned DESC",
        "team_xp_earned": "team_xp_earned DESC",
    }
    order_clause = sort_map.get(sort_by, "g2.rating DESC")

    # avg_teammate_elo: pull the OTHER member's 2v2 rating across all completed
    # series this player was in (or 1v1 fallback if their teammate is provisional),
    # then average. Self-reference filtered so own rating doesn't pollute.
    q = text(f"""
        WITH series_stats AS (
            SELECT player_id, SUM(won) AS wins, SUM(lost) AS losses, COUNT(*) AS total
            FROM (
                SELECT t1a_id AS player_id,
                       CASE WHEN winner_team = 1 THEN 1 ELSE 0 END AS won,
                       CASE WHEN winner_team = 2 THEN 1 ELSE 0 END AS lost
                FROM team_series WHERE status='completed'
                UNION ALL
                SELECT t1b_id, CASE WHEN winner_team = 1 THEN 1 ELSE 0 END,
                       CASE WHEN winner_team = 2 THEN 1 ELSE 0 END
                FROM team_series WHERE status='completed'
                UNION ALL
                SELECT t2a_id, CASE WHEN winner_team = 2 THEN 1 ELSE 0 END,
                       CASE WHEN winner_team = 1 THEN 1 ELSE 0 END
                FROM team_series WHERE status='completed'
                UNION ALL
                SELECT t2b_id, CASE WHEN winner_team = 2 THEN 1 ELSE 0 END,
                       CASE WHEN winner_team = 1 THEN 1 ELSE 0 END
                FROM team_series WHERE status='completed'
            ) sub
            GROUP BY player_id
        ),
        teammate_pairs AS (
            SELECT t1a_id AS player_id, t1b_id AS teammate_id
              FROM team_series WHERE status='completed'
            UNION ALL
            SELECT t1b_id, t1a_id FROM team_series WHERE status='completed'
            UNION ALL
            SELECT t2a_id, t2b_id FROM team_series WHERE status='completed'
            UNION ALL
            SELECT t2b_id, t2a_id FROM team_series WHERE status='completed'
        ),
        teammate_elo AS (
            SELECT tp.player_id, ROUND(AVG(COALESCE(g2t.rating, gt1.rating, 1500))::numeric, 0) AS avg_teammate_elo
              FROM teammate_pairs tp
              LEFT JOIN glicko_ratings_2v2 g2t ON g2t.player_id = tp.teammate_id AND g2t.completed_series >= 5
              LEFT JOIN glicko_ratings    gt1 ON gt1.player_id = tp.teammate_id
             GROUP BY tp.player_id
        )
        SELECT
            p.steam_id,
            p.display_name,
            ROUND(g2.rating::numeric, 0) AS rating,
            ROUND(g2.rating_deviation::numeric, 0) AS rd,
            g2.completed_series,
            COALESCE(ss.wins, 0) AS wins,
            COALESCE(ss.losses, 0) AS losses,
            CASE WHEN COALESCE(ss.total, 0) > 0
                 THEN ROUND(COALESCE(ss.wins, 0)::numeric / ss.total, 4)
                 ELSE 0 END AS win_rate,
            COALESCE(p.total_xp, 0) AS total_xp,
            COALESCE(p.team_gold_earned, 0) AS team_gold_earned,
            COALESCE(p.team_xp_earned,   0) AS team_xp_earned,
            COALESCE(te.avg_teammate_elo, 0) AS avg_teammate_elo,
            si.name AS title,
            si.preview_color AS title_color
        FROM glicko_ratings_2v2 g2
        JOIN players p ON p.id = g2.player_id
        LEFT JOIN series_stats ss ON ss.player_id = p.id
        LEFT JOIN teammate_elo te  ON te.player_id = p.id
        LEFT JOIN shop_items si    ON si.id = p.active_title_id
        WHERE g2.completed_series >= :min_series
          AND p.deleted_at IS NULL
        ORDER BY {order_clause}
        LIMIT :limit
    """)
    rows = (await db.execute(q, {"min_series": min_series, "limit": limit})).mappings().all()
    entries = []
    for idx, r in enumerate(rows, start=1):
        entries.append(Team2v2LeaderboardEntry(
            rank=idx,
            steam_id=r["steam_id"],
            display_name=r["display_name"],
            rating=int(r["rating"]),
            rd=int(r["rd"]),
            completed_series=r["completed_series"],
            series_wins=r["wins"],
            series_losses=r["losses"],
            win_rate=float(r["win_rate"]),
            level=level_from_xp(r["total_xp"])[0],
            title=r["title"],
            title_color=r["title_color"],
            avg_teammate_elo=int(r["avg_teammate_elo"] or 0),
            team_gold_earned=int(r["team_gold_earned"] or 0),
            team_xp_earned=int(r["team_xp_earned"] or 0),
        ))
    cnt = (await db.execute(
        text("SELECT COUNT(*) FROM glicko_ratings_2v2 WHERE completed_series >= :m"),
        {"m": min_series},
    )).scalar() or 0
    return Team2v2LeaderboardResponse(entries=entries, total_players=cnt, last_updated=datetime.now(timezone.utc))
