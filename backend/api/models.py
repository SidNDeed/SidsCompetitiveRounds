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
    team_gold_earned = Column(Integer, nullable=False, default=0)
    team_xp_earned = Column(Integer, nullable=False, default=0)
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
    # Player BODY color (kind=player_color), overrides the default team-based
    # orange/blue. Single-equip; sync via Photon cr_pbody_color custom prop.
    active_player_color_id = Column(BigInteger, ForeignKey("shop_items.id", ondelete="SET NULL"), nullable=True)
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
    invalidated_at = Column(DateTime(timezone=True), nullable=True)
    invalidation_reason = Column(String(64), nullable=True)
    p1_fps_avg = Column(SmallInteger, nullable=True)
    p2_fps_avg = Column(SmallInteger, nullable=True)

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
