"""
SQLAlchemy ORM models for Competitive ROUNDS.
These map directly to the tables created by 001_schema.sql.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Double, ForeignKey, Index, Integer,
    SmallInteger, String, UniqueConstraint,
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
    discord_username = Column(String(64), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    gold_earned = Column(Integer, nullable=False, default=0)
    gold_spent = Column(Integer, nullable=False, default=0)
    # Lifetime gun accuracy + block success counters (migration 038).
    # Accumulated from each submitted non-invalidated match's local_* fields on the reporter.
    bullets_fired = Column(BigInteger, nullable=False, default=0)
    bullets_hit = Column(BigInteger, nullable=False, default=0)
    blocks_activated = Column(BigInteger, nullable=False, default=0)
    blocks_successful = Column(BigInteger, nullable=False, default=0)
    active_title_id = Column(BigInteger, ForeignKey("shop_items.id", ondelete="SET NULL"), nullable=True)
    active_trail_id = Column(BigInteger, ForeignKey("shop_items.id", ondelete="SET NULL"), nullable=True)
    active_color_id = Column(BigInteger, ForeignKey("shop_items.id", ondelete="SET NULL"), nullable=True)
    # kind='color' items are multi-equip (v1.23+): player cycles between equipped colors
    # with Left Shift in-game. active_color_id above is the single-value legacy column,
    # kept for backward compat — reflects active_color_ids[0] when populated.
    active_color_ids = Column(ARRAY(BigInteger), nullable=False, default=list)
    # kind='nametag' items are stackable, unlike the single-active cosmetics above.
    nametag_style_ids = Column(ARRAY(BigInteger), nullable=False, default=list)
    first_seen = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    last_seen = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

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
    invalidated_at = Column(DateTime(timezone=True), nullable=True)
    invalidation_reason = Column(String(64), nullable=True)

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
