"""
SQLAlchemy ORM models for Competitive ROUNDS.
These map directly to the tables created by 001_schema.sql.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Double, ForeignKey, Index, Integer,
    SmallInteger, String, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Player(Base):
    __tablename__ = "players"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    steam_id = Column(String(20), nullable=False, unique=True, index=True)
    display_name = Column(String(64), nullable=False)
    ranked_enabled = Column(Boolean, nullable=False, default=True)
    total_xp = Column(Integer, nullable=False, default=0)
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
    joined_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    matched_at = Column(DateTime(timezone=True), nullable=True)


class QueueBlock(Base):
    __tablename__ = "queue_blocks"

    blocker_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    blocked_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
