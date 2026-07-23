"""
SQLAlchemy ORM models for Competitive ROUNDS.
These map directly to the tables created by 001_schema.sql.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Double, FetchedValue, Float, ForeignKey, Index, Integer,
    SmallInteger, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Player(Base):
    __tablename__ = "players"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    steam_id = Column(String(20), nullable=False, unique=True, index=True)
    display_name = Column(String(64), nullable=False)
    ranked_enabled = Column(Boolean, nullable=False, default=False)
    total_xp = Column(Integer, nullable=False, default=0)
    ranked_dc_count = Column(Integer, nullable=False, default=0)
    discord_id = Column(String(20), nullable=True, unique=True, index=True)
    # The unique @handle (user.name). Pre-migration-144 rows held DISPLAY
    # names here; the bot re-resolves and overwrites on startup.
    discord_username = Column(String(64), nullable=True)
    # July 22 (migration 144): the global/server display name, shown on the
    # leaderboard player detail, Search-Ranked beacon, and /mystats when
    # show_discord is true. v1.34.1 (migration 146): flipped to OPT-OUT —
    # default TRUE; a player hides via the Settings toggle.
    discord_display_name = Column(String(64), nullable=True)
    show_discord = Column(Boolean, nullable=False, default=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    gold_earned = Column(Integer, nullable=False, default=0)
    team_gold_earned = Column(Integer, nullable=False, default=0)
    team_xp_earned = Column(Integer, nullable=False, default=0)
    gold_spent = Column(Integer, nullable=False, default=0)
    # Hide-gold utility (migration 098): when true, the leaderboard masks this
    # player's gold from everyone. Unlocked by purchasing sku 'util_hide_gold',
    # toggled via /hide-gold. The player still sees their own real balance.
    hide_gold = Column(Boolean, nullable=False, default=False)
    # Appear-offline privacy toggle (migration 126): when true, the player is
    # excluded from the Home tab's online / recently-online lists. The
    # anonymous online COUNT still includes them (it carries no identity).
    appear_offline = Column(Boolean, nullable=False, default=False)
    # Lifetime gun accuracy + block success counters (migration 038).
    # Accumulated from each submitted non-invalidated match's local_* fields on the reporter.
    bullets_fired = Column(BigInteger, nullable=False, default=0)
    bullets_hit = Column(BigInteger, nullable=False, default=0)
    blocks_activated = Column(BigInteger, nullable=False, default=0)
    blocks_successful = Column(BigInteger, nullable=False, default=0)
    # Lifetime input-rate counters (migration 102, v1.29 Compare tab).
    # Accumulated from the reporter's per-match local_keys_pressed /
    # local_active_seconds — same one-sided pattern as bullets_fired.
    keys_pressed_total = Column(BigInteger, nullable=False, default=0)
    active_seconds_total = Column(Double, nullable=False, default=0)
    # Win-streak achievement counters (migration 112, v1.30 item 2). Updated on
    # every valid match submit; both start counting from the 112 deploy.
    consecutive_sweeps = Column(Integer, nullable=False, default=0)
    casual_win_streak = Column(Integer, nullable=False, default=0)
    active_title_id = Column(BigInteger, ForeignKey("shop_items.id", ondelete="SET NULL"), nullable=True)
    active_trail_id = Column(BigInteger, ForeignKey("shop_items.id", ondelete="SET NULL"), nullable=True)
    active_color_id = Column(BigInteger, ForeignKey("shop_items.id", ondelete="SET NULL"), nullable=True)
    # Player BODY color (kind=player_color), overrides the default team-based
    # orange/blue. Single-equip; sync via Photon cr_pbody_color custom prop.
    active_player_color_id = Column(BigInteger, ForeignKey("shop_items.id", ondelete="SET NULL"), nullable=True)
    # Cursor color (kind=cursor_color, migration 098): recolors the in-menu mouse
    # cursor. Single-equip, local-only render. preview_color drives the tint.
    active_cursor_color_id = Column(BigInteger, ForeignKey("shop_items.id", ondelete="SET NULL"), nullable=True)
    # Player effect (kind=player_effect, migration 098): in-match particle aura on
    # the body. Single-equip; cross-visible via Photon cr_effect_sku.
    active_player_effect_id = Column(BigInteger, ForeignKey("shop_items.id", ondelete="SET NULL"), nullable=True)
    # kind='color' items are multi-equip (v1.23+): player cycles between equipped colors
    # with Left Shift in-game. active_color_id above is the single-value legacy column,
    # kept for backward compat — reflects active_color_ids[0] when populated.
    active_color_ids = Column(ARRAY(BigInteger), nullable=False, default=list)
    # kind='nametag' items are stackable, unlike the single-active cosmetics above.
    nametag_style_ids = Column(ARRAY(BigInteger), nullable=False, default=list)
    first_seen = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    last_seen = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    # Set by _mark_mod_seen on the first call from a mod-only endpoint.
    # NULL = passive opponent record (auto-created via get_or_create_player
    # when their match was reported by someone else).
    mod_seen_at = Column(DateTime(timezone=True), nullable=True)
    # Most recently observed mod version (X-Mod-Version request header,
    # stamped by _mark_mod_seen on mod-only endpoints). Used by the
    # leaderboard player-detail view so testers can tell at a glance
    # whether a player is running a build that has a given fix.
    mod_version = Column(String(16), nullable=True)

    glicko = relationship("GlickoRating", back_populates="player", uselist=False)
    rating_history = relationship("RatingHistory", back_populates="player")


class GlickoRating(Base):
    __tablename__ = "glicko_ratings"

    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    rating = Column(Double, nullable=False, default=1500.0)
    rating_deviation = Column(Double, nullable=False, default=350.0)
    volatility = Column(Double, nullable=False, default=0.06)
    peak_rating = Column(Double, nullable=True)
    games_in_period = Column(Integer, nullable=False, default=0)
    last_calculated = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    player = relationship("Player", back_populates="glicko")


class RatingHistory(Base):
    __tablename__ = "rating_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    rating = Column(Double, nullable=False)
    rating_deviation = Column(Double, nullable=False)
    volatility = Column(Double, nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    player = relationship("Player", back_populates="rating_history")

    __table_args__ = (
        Index("idx_rating_history_player", "player_id", period_end.desc()),
    )


class Match(Base):
    __tablename__ = "matches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player1_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    player2_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    p1_rounds_won = Column(SmallInteger, nullable=False)
    p2_rounds_won = Column(SmallInteger, nullable=False)
    p1_points_total = Column(SmallInteger, nullable=False, default=0)
    p2_points_total = Column(SmallInteger, nullable=False, default=0)
    winner_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=True)
    match_duration = Column(Integer, nullable=True)
    photon_room_id = Column(String(64), nullable=True)
    game_version = Column(String(32), nullable=True)
    region = Column(String(8), nullable=True)
    hmac_signature = Column(String(128), nullable=True)
    reported_by = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=True)
    is_ranked = Column(Boolean, nullable=False, default=False)
    series_id = Column(UUID(as_uuid=True), ForeignKey("ranked_series.id"), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)

    # XP earned per player
    p1_xp_gained = Column(Integer, default=0)
    p2_xp_gained = Column(Integer, default=0)
    ended_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Anti-cheat (v1.21.0). duration_seconds replaces match_duration as the canonical name in
    # new code; the older column is preserved so historical rows aren't disturbed.
    duration_seconds = Column(Integer, nullable=True)
    local_bullets_fired = Column(Integer, nullable=True)
    local_blocks_raised = Column(Integer, nullable=True)
    # Reporter's per-match input-rate metrics (migration 102, v1.29).
    local_keys_pressed = Column(Integer, nullable=True)
    local_active_seconds = Column(Double, nullable=True)
    # #50 macro detector (migration 106): 1s windows with superhuman key rates.
    local_macro_suspect_seconds = Column(Integer, nullable=True)
    invalidated_at = Column(DateTime(timezone=True), nullable=True)
    invalidation_reason = Column(String(64), nullable=True)
    p1_fps_avg = Column(SmallInteger, nullable=True)
    p2_fps_avg = Column(SmallInteger, nullable=True)
    # Per-game combat stats, BOTH sides (migration 111, v1.30 item 4). Reporter
    # side comes from their own counters; the other side from the opponent's
    # cr_gstats Photon prop snapshot. Mapped to p1/p2 at submit (FPS pattern).
    p1_bullets_fired = Column(Integer, nullable=True)
    p1_bullets_hit = Column(Integer, nullable=True)
    p1_blocks_activated = Column(Integer, nullable=True)
    p1_blocks_successful = Column(Integer, nullable=True)
    p1_keys_pressed = Column(Integer, nullable=True)
    p1_active_seconds = Column(Double, nullable=True)
    p2_bullets_fired = Column(Integer, nullable=True)
    p2_bullets_hit = Column(Integer, nullable=True)
    p2_blocks_activated = Column(Integer, nullable=True)
    p2_blocks_successful = Column(Integer, nullable=True)
    p2_keys_pressed = Column(Integer, nullable=True)
    p2_active_seconds = Column(Double, nullable=True)
    # Cumulative scoring timeline "p1Total:p2Total,..." (total = rounds*2+points)
    # in match-row p1/p2 orientation — drives the history score-hover graph.
    point_timeline = Column(String(512), nullable=True)
    # Analysis-era filter (migration 136): the reporter client's X-Mod-Version
    # at submit time. Cannot be backfilled — required to slice per-match
    # hit/block stats by counting-semantics era after the July 21 fix.
    reporter_mod_version = Column(String(16), nullable=True)
    # FPS/lag telemetry (migration 136, advisory anti-cheat). Reporter side
    # from their own counters; opponent side from the extended cr_gstats
    # Photon prop. Asymmetries: ping + freeze_total_sec exist only for the
    # reporter side; hb_gap is the OTHER seat's observation of this side's
    # heartbeat. All NULL on old-client reports and pre-migration rows.
    p1_fps_timeline = Column(String(512), nullable=True)
    p2_fps_timeline = Column(String(512), nullable=True)
    p1_freeze_count = Column(SmallInteger, nullable=True)
    p2_freeze_count = Column(SmallInteger, nullable=True)
    p1_freeze_focused_count = Column(SmallInteger, nullable=True)
    p2_freeze_focused_count = Column(SmallInteger, nullable=True)
    p1_freeze_total_sec = Column(Float, nullable=True)
    p2_freeze_total_sec = Column(Float, nullable=True)
    p1_recv_gap_count = Column(SmallInteger, nullable=True)
    p2_recv_gap_count = Column(SmallInteger, nullable=True)
    # Longest single socket-silence gap in ms (reporter side only — cr_gstats
    # carries no opponent max). Integer, NOT SmallInteger: a 45s NIC cut is
    # 45000 ms, over SMALLINT's 32767 max.
    p1_recv_gap_max_ms = Column(Integer, nullable=True)
    p2_recv_gap_max_ms = Column(Integer, nullable=True)
    # July 22 item 3 — per-side latency timelines (comma ints, 3s cadence).
    p1_ping_timeline = Column(String(512), nullable=True)
    p2_ping_timeline = Column(String(512), nullable=True)
    p1_hb_gap_count = Column(SmallInteger, nullable=True)
    p2_hb_gap_count = Column(SmallInteger, nullable=True)
    p1_ping_avg = Column(SmallInteger, nullable=True)
    p2_ping_avg = Column(SmallInteger, nullable=True)
    p1_ping_max = Column(SmallInteger, nullable=True)
    p2_ping_max = Column(SmallInteger, nullable=True)
    # July 22 (migration 141) — cumulative hit/block timelines, 3s cadence:
    # hit = "fired:hit,...", block = "dmgTaken:blocksSucc,...". point_times =
    # seconds-since-start per point_timeline entry (no p1/p2 orientation).
    p1_hit_timeline = Column(String(1024), nullable=True)
    p2_hit_timeline = Column(String(1024), nullable=True)
    p1_block_timeline = Column(String(1024), nullable=True)
    p2_block_timeline = Column(String(1024), nullable=True)
    point_times = Column(String(512), nullable=True)

    player1 = relationship("Player", foreign_keys=[player1_id])
    player2 = relationship("Player", foreign_keys=[player2_id])
    winner = relationship("Player", foreign_keys=[winner_id])
    cards = relationship("MatchCard", back_populates="match", cascade="all, delete-orphan")
    series = relationship("RankedSeries", back_populates="matches")

    __table_args__ = (
        UniqueConstraint("photon_room_id", "player1_id", "player2_id", name="unique_match"),
        Index("idx_matches_player1", "player1_id", ended_at.desc()),
        Index("idx_matches_player2", "player2_id", ended_at.desc()),
        Index("idx_matches_ended", ended_at.desc()),
    )


class RankedSeries(Base):
    __tablename__ = "ranked_series"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player1_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    player2_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    p1_series_wins = Column(SmallInteger, nullable=False, default=0)
    p2_series_wins = Column(SmallInteger, nullable=False, default=0)
    status = Column(String(16), nullable=False, default="active")
    winner_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=True)
    p1_rating_change = Column(Double, nullable=True)
    p2_rating_change = Column(Double, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True), nullable=True)
    invalidated_at = Column(DateTime(timezone=True), nullable=True)
    invalidation_reason = Column(String(64), nullable=True)
    # v1.22 — live point counts for game 1 of the series (zeros after first match completes,
    # since this only matters for the bet-cutoff window). Bets reject when sum >= 2.
    live_p1_points = Column(Integer, nullable=False, default=0)
    live_p2_points = Column(Integer, nullable=False, default=0)
    # Tournament linkage. Set when start_tournament creates the series row
    # for a bracket match. The DB schema has had these columns since the
    # tournament feature shipped, but the model was never updated to
    # declare them — every start_tournament call errored with "'tournament_id'
    # is an invalid keyword argument for RankedSeries", silently stranding
    # tournaments in status='locked' (caught by Sid's testing 2026-04-30).
    tournament_id = Column(UUID(as_uuid=True), ForeignKey("tournaments.id", ondelete="SET NULL"), nullable=True)
    is_tournament = Column(Boolean, nullable=False, default=False)
    # Private rooms (set by /series/preflight when room name doesn't start
    # with "ranked_") — bets are locked, not surfaced on Live Ranked Games.
    is_private = Column(Boolean, nullable=False, default=False)

    player1 = relationship("Player", foreign_keys=[player1_id])
    player2 = relationship("Player", foreign_keys=[player2_id])
    series_winner = relationship("Player", foreign_keys=[winner_id])
    matches = relationship("Match", back_populates="series", order_by="Match.ended_at")


class MatchCard(Base):
    __tablename__ = "match_cards"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id = Column(UUID(as_uuid=True), ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    card_name = Column(String(64), nullable=False)
    card_rarity = Column(String(16), nullable=True)
    pick_order = Column(SmallInteger, nullable=False)
    round_number = Column(SmallInteger, nullable=False)

    match = relationship("Match", back_populates="cards")


class CardOffer(Base):
    __tablename__ = "card_offers"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    match_id = Column(UUID(as_uuid=True), ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    round_number = Column(Integer, nullable=False)
    card_name = Column(String(64), nullable=False)
    was_picked = Column(Boolean, nullable=False, default=False)


class GoldTransaction(Base):
    __tablename__ = "gold_transactions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Integer, nullable=False)
    reason = Column(String(64), nullable=False)
    reference_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class ShopItem(Base):
    __tablename__ = "shop_items"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    sku = Column(String(64), unique=True, nullable=False)
    kind = Column(String(16), nullable=False)
    name = Column(String(128), nullable=False)
    description = Column(String(256), nullable=True)
    price = Column(Integer, nullable=False)
    rarity = Column(String(16), nullable=False, default="common")
    rotation_pool = Column(String(32), nullable=True)
    preview_color = Column(String(16), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    # Artist controls (v1.30, migration 109): community-made cosmetics carry
    # their creator's steam id; the artist can then set price/stock, gift
    # copies, and block buyers via the /artist endpoints. NULL = house item.
    artist_steam_id = Column(String(20), nullable=True)
    # Max copies in circulation (purchases + gifts). NULL = unlimited.
    stock_limit = Column(Integer, nullable=True)
    # When the item actually became buyable (stamped on the first stock open
    # from the born-out-of-stock -1 state; migration 131). NULL = never
    # gated — readers COALESCE to created_at.
    released_at = Column(DateTime(timezone=True), nullable=True)


class PlayerItem(Base):
    __tablename__ = "player_items"

    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    item_id = Column(BigInteger, ForeignKey("shop_items.id", ondelete="CASCADE"), primary_key=True)
    purchased_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    purchase_price = Column(Integer, nullable=False)


class Bet(Base):
    __tablename__ = "bets"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    series_id = Column(UUID(as_uuid=True), ForeignKey("ranked_series.id", ondelete="CASCADE"), nullable=False)
    bet_on_player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    amount = Column(Integer, nullable=False)
    odds_multiplier = Column(Double, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    settled_at = Column(DateTime(timezone=True), nullable=True)
    payout = Column(Integer, nullable=True)

    __table_args__ = (UniqueConstraint("player_id", "series_id", name="uq_bet_player_series"),)


class RankRoleColor(Base):
    """Discord rank-role colors, synced by the bot (migration 102, v1.29).
    Keyed by the CLEAN tier name ("Master V", not "Master V 2270-2329").
    Drives rank display colors in the leaderboard + the 'Current Rank' title;
    hardcoded fallback palette applies while a name is missing here."""
    __tablename__ = "rank_role_colors"

    name = Column(String(48), primary_key=True)
    color_hex = Column(String(16), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class BoosterGrant(Base):
    """Monthly Discord-booster gold grants (migration 102, v1.29). One row per
    booster per calendar month — the unique constraint is the idempotency key,
    so the bot's daily sweep can re-post the same grant without double-paying."""
    __tablename__ = "booster_grants"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    discord_id = Column(String(20), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    month = Column(String(7), nullable=False)  # "2026-07"
    amount = Column(Integer, nullable=False)
    granted_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("discord_id", "month", name="uq_booster_grant_month"),)


class RankedQueue(Base):
    __tablename__ = "ranked_queue"

    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    steam_id = Column(String(20), nullable=False)
    display_name = Column(String(64), nullable=False)
    rating = Column(Double, nullable=False, default=1500)
    rating_deviation = Column(Double, nullable=False, default=350)
    region = Column(String(8), nullable=True)
    ranked_only = Column(Boolean, nullable=False, default=False)
    status = Column(String(16), nullable=False, default="searching")
    matched_with = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=True)
    room_name = Column(String(64), nullable=True)
    room_region = Column(String(8), nullable=True)
    ready = Column(Boolean, nullable=False, default=False)
    joined_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    matched_at = Column(DateTime(timezone=True), nullable=True)
    last_polled = Column(DateTime(timezone=True), nullable=True, default=lambda: datetime.now(timezone.utc))


class QueueBlock(Base):
    __tablename__ = "queue_blocks"

    blocker_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    blocked_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class PlayerBlock(Base):
    __tablename__ = "player_blocks"

    blocker_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    blocked_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class LinkCode(Base):
    __tablename__ = "link_codes"

    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    code = Column(String(6), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class SteamSession(Base):
    """Opaque session tokens issued by POST /api/v1/auth/steam after Steam
    Web-API ticket verification (migration 137). DB-backed so sessions
    survive `docker compose up -d --build` redeploys — an in-memory store
    would 401-storm every client after each deploy once enforcement is on.
    Only sha256(token) is stored, never the raw token."""
    __tablename__ = "steam_sessions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    steam_id = Column(String(20), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)
    verified = Column(Boolean, nullable=False, default=False)
    issued_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=False)


class PlayerAchievement(Base):
    __tablename__ = "player_achievements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    achievement_key = Column(String(64), nullable=False)
    unlocked_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    match_id = Column(UUID(as_uuid=True), ForeignKey("matches.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (
        UniqueConstraint("player_id", "achievement_key", name="uq_player_achievement"),
        Index("idx_pa_player", "player_id"),
        Index("idx_pa_key", "achievement_key"),
    )


class BugReport(Base):
    """In-game bug reports submitted from the F5 menu (v1.26.7)."""
    __tablename__ = "bug_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Auto-assigned by DB sequence (migration 086); FetchedValue tells the
    # ORM not to send the column in the INSERT (so the DEFAULT fires) and to
    # re-read it after the insert so report.bug_number is populated.
    bug_number = Column(BigInteger, nullable=False, unique=True,
                        server_default=FetchedValue(), server_onupdate=FetchedValue())
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    steam_id = Column(String(32), nullable=True)
    display_name = Column(String(64), nullable=True)
    mod_version = Column(String(32), nullable=True)
    game_version = Column(String(32), nullable=True)
    severity = Column(String(16), nullable=False, default="medium")
    category = Column(String(16), nullable=False, default="other")
    description = Column(Text, nullable=False)
    repro_steps = Column(Text, nullable=True)
    log_filename = Column(String(96), nullable=True)
    log_bytes = Column(Integer, nullable=True)
    status = Column(String(16), nullable=False, default="open")
    triage_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class BugReportEvent(Base):
    """Activity log entry for a bug report — status change or comment."""
    __tablename__ = "bug_report_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bug_report_id = Column(UUID(as_uuid=True), ForeignKey("bug_reports.id", ondelete="CASCADE"), nullable=False)
    actor_steam_id = Column(String(32), nullable=True)
    actor_name = Column(String(96), nullable=False)
    event_type = Column(String(24), nullable=False)  # comment | status_change | created
    old_status = Column(String(16), nullable=True)
    new_status = Column(String(16), nullable=True)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


# ── Anti-cheat & admin (v1.21.0) ──────────────────────────────

class FlaggedMatch(Base):
    """Append-only audit log of suspicious matches. Multiple flags may attach to one match."""
    __tablename__ = "flagged_matches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id = Column(UUID(as_uuid=True), ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    series_id = Column(UUID(as_uuid=True), ForeignKey("ranked_series.id", ondelete="SET NULL"), nullable=True)
    player_steam_ids = Column(ARRAY(String), nullable=False)
    flag_reason = Column(String(64), nullable=False)
    flag_details = Column(JSONB, nullable=True)
    auto_invalidated = Column(Boolean, nullable=False, default=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by_steam_id = Column(String(20), nullable=True)
    review_action = Column(String(32), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class AdminUser(Base):
    """Whitelist of Steam IDs allowed to call /admin/* endpoints."""
    __tablename__ = "admin_users"

    steam_id = Column(String(20), primary_key=True)
    granted_by_steam_id = Column(String(20), nullable=True)
    granted_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    notes = Column(String(256), nullable=True)


class PlayerBan(Base):
    """Append-only ban log; player is currently banned if latest row has unbanned_at IS NULL."""
    __tablename__ = "player_bans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    steam_id = Column(String(20), nullable=False)
    reason = Column(String(256), nullable=False)
    banned_by_steam_id = Column(String(20), ForeignKey("admin_users.steam_id"), nullable=False)
    banned_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    unbanned_at = Column(DateTime(timezone=True), nullable=True)
    unbanned_by_steam_id = Column(String(20), nullable=True)


class AdminAction(Base):
    """Audit log for everything admins do — bans, achievement grants, series reversals."""
    __tablename__ = "admin_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_steam_id = Column(String(20), ForeignKey("admin_users.steam_id"), nullable=False)
    action = Column(String(32), nullable=False)
    target_steam_id = Column(String(20), nullable=True)
    target_match_id = Column(UUID(as_uuid=True), nullable=True)
    target_series_id = Column(UUID(as_uuid=True), nullable=True)
    details = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


# ── Tournaments (migration 047) ──────────────────────────────────────────

class Tournament(Base):
    __tablename__ = "tournaments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind = Column(String(8), nullable=False, default="sync")
    status = Column(String(16), nullable=False, default="voting")
    format = Column(String(24), nullable=False, default="single_elim_bo3")
    default_start_ts = Column(DateTime(timezone=True), nullable=False)
    scheduled_start_ts = Column(DateTime(timezone=True), nullable=True)
    voting_closes_at = Column(DateTime(timezone=True), nullable=True)
    lock_at = Column(DateTime(timezone=True), nullable=False)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    min_players = Column(SmallInteger, nullable=False, default=8)
    max_players = Column(SmallInteger, nullable=False, default=16)
    prize_tier = Column(String(8), nullable=True)
    # Confirmed player count snapshotted at lock (migration 132): prizes now
    # scale with this via _prize_amounts; prize_tier kept for legacy readers.
    prize_player_count = Column(SmallInteger, nullable=True)
    winner_signup_id = Column(UUID(as_uuid=True), nullable=True)
    runner_up_signup_id = Column(UUID(as_uuid=True), nullable=True)
    third_place_signup_id = Column(UUID(as_uuid=True), nullable=True)
    photon_region = Column(String(16), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_by = Column(String(16), nullable=False, default="cron")


class TournamentSignup(Base):
    __tablename__ = "tournament_signups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tournament_id = Column(UUID(as_uuid=True), ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    signed_up_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    is_speculative = Column(Boolean, nullable=False, default=False)
    penalty_at_signup = Column(Double, nullable=False, default=0)
    seed = Column(SmallInteger, nullable=True)
    cached_elo_at_lock = Column(Double, nullable=True)
    ready_at = Column(DateTime(timezone=True), nullable=True)
    forfeited = Column(Boolean, nullable=False, default=False)
    placed_rank = Column(SmallInteger, nullable=True)
    region_at_signup = Column(String(16), nullable=True)

    __table_args__ = (UniqueConstraint("tournament_id", "player_id"),)


class TournamentMatch(Base):
    __tablename__ = "tournament_matches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tournament_id = Column(UUID(as_uuid=True), ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False)
    round = Column(SmallInteger, nullable=False)
    bracket_side = Column(String(4), nullable=False, default="W")
    slot_idx = Column(SmallInteger, nullable=False)
    p1_signup_id = Column(UUID(as_uuid=True), ForeignKey("tournament_signups.id", ondelete="SET NULL"), nullable=True)
    p2_signup_id = Column(UUID(as_uuid=True), ForeignKey("tournament_signups.id", ondelete="SET NULL"), nullable=True)
    prereq_match_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False, default=list)
    prereq_roles = Column(ARRAY(String), nullable=False, default=list)
    is_bye = Column(Boolean, nullable=False, default=False)
    status = Column(String(16), nullable=False, default="pending")
    deadline_at = Column(DateTime(timezone=True), nullable=True)
    series_id = Column(UUID(as_uuid=True), ForeignKey("ranked_series.id", ondelete="SET NULL"), nullable=True)
    winner_signup_id = Column(UUID(as_uuid=True), ForeignKey("tournament_signups.id", ondelete="SET NULL"), nullable=True)
    ready_deadline_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    # Between-rounds break (migration 132): sync rounds 2+ sit in
    # status='scheduled' until this time, then flip to 'ready'. Both players
    # in early_ok_signup_ids = skip the break immediately.
    scheduled_ready_at = Column(DateTime(timezone=True), nullable=True)
    early_ok_signup_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False, default=list)
    # Server-issued Photon room name (e.g., "sct-a1b2c3d4e5f6"). Set when
    # the match transitions to 'ready' so both clients receive the same
    # canonical name from the API rather than deriving it locally.
    # Migration 072 added the column; older rows pre-existing the
    # migration may have NULL (server falls back to deriving from id
    # at activation time for those, kept for compat).
    photon_room_name = Column(String(64), nullable=True)

    __table_args__ = (UniqueConstraint("tournament_id", "round", "bracket_side", "slot_idx"),)


class TournamentTimeVote(Base):
    __tablename__ = "tournament_time_votes"

    tournament_id = Column(UUID(as_uuid=True), ForeignKey("tournaments.id", ondelete="CASCADE"), primary_key=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    slot_ts = Column(DateTime(timezone=True), primary_key=True)
    voted_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class TournamentForceVote(Base):
    __tablename__ = "tournament_force_votes"

    tournament_id = Column(UUID(as_uuid=True), ForeignKey("tournaments.id", ondelete="CASCADE"), primary_key=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    voted_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class PlayerTournamentPenalty(Base):
    __tablename__ = "player_tournament_penalty"

    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    cached_penalty_pct = Column(Double, nullable=False, default=0)
    signups_90d = Column(SmallInteger, nullable=False, default=0)
    missed_90d = Column(SmallInteger, nullable=False, default=0)
    no_show_last_at = Column(DateTime(timezone=True), nullable=True)
    latest_signup_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


# ── 2v2 ranked (separate path from 1v1; see migration 053) ────────────

class GlickoRating2v2(Base):
    __tablename__ = "glicko_ratings_2v2"

    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    rating = Column(Double, nullable=False, default=1500.0)
    rating_deviation = Column(Double, nullable=False, default=350.0)
    volatility = Column(Double, nullable=False, default=0.06)
    peak_rating = Column(Double, nullable=True)
    games_in_period = Column(Integer, nullable=False, default=0)
    completed_series = Column(Integer, nullable=False, default=0)
    last_calculated = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class TeamQueue(Base):
    __tablename__ = "team_queue"

    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    steam_id = Column(String(20), nullable=False)
    display_name = Column(String(64), nullable=False)
    rating = Column(Double, nullable=False, default=1500.0)
    rating_deviation = Column(Double, nullable=False, default=350.0)
    completed_series = Column(Integer, nullable=False, default=0)
    fallback_rating = Column(Double, nullable=False, default=1500.0)
    region = Column(String(8), nullable=True)
    status = Column(String(16), nullable=False, default="searching")
    series_id = Column(UUID(as_uuid=True), nullable=True)
    team_assigned = Column(SmallInteger, nullable=True)
    room_name = Column(String(64), nullable=True)
    room_region = Column(String(8), nullable=True)
    ready = Column(Boolean, nullable=False, default=False)
    joined_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    matched_at = Column(DateTime(timezone=True), nullable=True)
    last_polled = Column(DateTime(timezone=True), nullable=True, default=lambda: datetime.now(timezone.utc))
    queue_type = Column(String(8), nullable=False, default="auto")


class TeamSeries(Base):
    __tablename__ = "team_series"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    t1a_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    t1b_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    t2a_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    t2b_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    t1_series_wins = Column(SmallInteger, nullable=False, default=0)
    t2_series_wins = Column(SmallInteger, nullable=False, default=0)
    status = Column(String(16), nullable=False, default="active")
    winner_team = Column(SmallInteger, nullable=True)
    t1a_rating_change = Column(Double, nullable=True)
    t1b_rating_change = Column(Double, nullable=True)
    t2a_rating_change = Column(Double, nullable=True)
    t2b_rating_change = Column(Double, nullable=True)
    photon_room_id = Column(String(64), nullable=True)
    region = Column(String(8), nullable=True)
    rebalance_count = Column(SmallInteger, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True), nullable=True)
    invalidated_at = Column(DateTime(timezone=True), nullable=True)
    invalidation_reason = Column(String(64), nullable=True)
    spawn_confirmations = Column(SmallInteger, nullable=False, default=0)
    spawn_confirmed_by = Column(JSONB, nullable=False, default=list)


class TeamMatch(Base):
    __tablename__ = "team_matches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    series_id = Column(UUID(as_uuid=True), ForeignKey("team_series.id"), nullable=True)
    t1a_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    t1b_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    t2a_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    t2b_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    t1_rounds_won = Column(SmallInteger, nullable=False)
    t2_rounds_won = Column(SmallInteger, nullable=False)
    t1_points_total = Column(SmallInteger, nullable=False, default=0)
    t2_points_total = Column(SmallInteger, nullable=False, default=0)
    winner_team = Column(SmallInteger, nullable=False)
    t1a_fps_avg = Column(SmallInteger, nullable=True)
    t1b_fps_avg = Column(SmallInteger, nullable=True)
    t2a_fps_avg = Column(SmallInteger, nullable=True)
    t2b_fps_avg = Column(SmallInteger, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    photon_room_id = Column(String(64), nullable=True)
    game_version = Column(String(32), nullable=True)
    region = Column(String(8), nullable=True)
    hmac_signature = Column(String(128), nullable=True)
    reported_by = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=True)
    is_ranked = Column(Boolean, nullable=False, default=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    invalidated_at = Column(DateTime(timezone=True), nullable=True)
    invalidation_reason = Column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("photon_room_id", "t1a_id", "t1b_id", "t2a_id", "t2b_id", name="uq_team_match"),
    )


class TeamMatchCard(Base):
    __tablename__ = "team_match_cards"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id = Column(UUID(as_uuid=True), ForeignKey("team_matches.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    card_name = Column(String(64), nullable=False)
    card_rarity = Column(String(16), nullable=True)
    pick_order = Column(SmallInteger, nullable=False)
    round_number = Column(SmallInteger, nullable=False)


class TeamMatchTelemetry(Base):
    """Per-player 2v2 telemetry (migration 142) — one row per (match, player),
    written by submit_team_match from the reporter's harvest of everyone's
    cr_gstats props. Rows exist only for players whose data reached the
    reporter; old-client peers have no row."""
    __tablename__ = "team_match_telemetry"

    match_id = Column(UUID(as_uuid=True), ForeignKey("team_matches.id", ondelete="CASCADE"), primary_key=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), primary_key=True)
    fps_timeline = Column(String(512), nullable=True)
    ping_timeline = Column(String(512), nullable=True)
    ping_avg = Column(SmallInteger, nullable=True)
    hit_timeline = Column(String(1024), nullable=True)
    block_timeline = Column(String(1024), nullable=True)
    bullets_fired = Column(Integer, nullable=True)
    bullets_hit = Column(Integer, nullable=True)
    blocks_activated = Column(Integer, nullable=True)
    blocks_successful = Column(Integer, nullable=True)
    keys_pressed = Column(Integer, nullable=True)
    active_seconds = Column(Double, nullable=True)


class ArtistUser(Base):
    """Community artists (v1.30, migration 109). Mirrors admin_users: presence
    of a row grants the /artist endpoints + the in-game Artist tab. Artists
    control only items whose shop_items.artist_steam_id matches their row."""
    __tablename__ = "artist_users"

    steam_id = Column(Text, primary_key=True)
    display_name = Column(Text, nullable=True)
    granted_by_steam_id = Column(Text, nullable=True)
    granted_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    notes = Column(Text, nullable=True)


class ArtistItemBlock(Base):
    """Per-artist purchase blocklist (v1.30). A blocked player cannot BUY any
    of the artist's items; explicit gifts from the artist still work."""
    __tablename__ = "artist_item_blocks"

    artist_steam_id = Column(Text, ForeignKey("artist_users.steam_id", ondelete="CASCADE"), primary_key=True)
    blocked_steam_id = Column(String(20), primary_key=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class ArtistAction(Base):
    """Audit log for artist mutations (set-price / set-stock / gift / block),
    mirroring admin_actions."""
    __tablename__ = "artist_actions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    artist_steam_id = Column(Text, nullable=False)
    action = Column(Text, nullable=False)
    target = Column(Text, nullable=True)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class PendingChannelPost(Base):
    """Bot announce queue (v1.30). Rows are inserted by migrations (or future
    admin tooling); the Discord bot polls /internal/channel-posts/pending and
    acks posted_at after each successful send (learning #105 ack pattern)."""
    __tablename__ = "pending_channel_posts"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    channel_id = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    posted_at = Column(DateTime(timezone=True), nullable=True)


class TournamentNotice(Base):
    """Durable tournament DM queue (v1.32, migration 124). One row per
    (tournament, player, notice_type) — e.g. the 'availability_check' DM
    queued by tournament_tick 24-96h before a viable tournament starts.
    The bot polls GET /internal/tournament-notices?unnotified=true and acks
    notified_at after the DM lands (learning #105 ack pattern)."""
    __tablename__ = "tournament_notices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tournament_id = Column(UUID(as_uuid=True), ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    notice_type = Column(String(32), nullable=False)
    payload = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    notified_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("tournament_id", "player_id", "notice_type"),)
