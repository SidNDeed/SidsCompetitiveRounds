"""
Pydantic schemas for API request and response validation.
These define the JSON shape of data going in and out of the API.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ── Match Submission ───────────────────────────────────────────

class CardPick(BaseModel):
    """A single card picked during a match."""
    card_name: str = Field(..., max_length=64, examples=["Buckshot"])
    card_rarity: str | None = Field(None, max_length=16, examples=["Common"])
    pick_order: int = Field(..., ge=1, examples=[1])
    round_number: int = Field(..., ge=1, examples=[1])


class CardOfferEntry(BaseModel):
    """A single card the local player was offered during a pick phase."""
    card_name: str = Field(..., max_length=64)
    round_number: int = Field(..., ge=1)
    was_picked: bool = False


class PlayerMatchData(BaseModel):
    """Data about one player in a match report."""
    steam_id: str = Field(..., max_length=20, examples=["76561198012345678"])
    display_name: str = Field(..., max_length=64, examples=["PlayerOne"])
    cards: list[CardPick] = Field(default_factory=list)
    card_offers: list[CardOfferEntry] = Field(default_factory=list)


class MatchReport(BaseModel):
    """
    The payload the BepInEx mod sends when a match ends.
    The host player's mod submits this.
    """
    player1: PlayerMatchData
    player2: PlayerMatchData
    p1_rounds_won: int = Field(..., ge=0, le=10, examples=[3])
    p2_rounds_won: int = Field(..., ge=0, le=10, examples=[1])
    p1_points_total: int = Field(0, ge=0, examples=[15])
    p2_points_total: int = Field(0, ge=0, examples=[8])
    photon_room_id: str | None = Field(None, max_length=64)
    game_version: str | None = Field(None, max_length=32, examples=["v1.1.2.a75ee335a"])
    region: str | None = Field(None, max_length=8, examples=["us"])
    match_duration: int | None = Field(None, ge=0, description="Duration in seconds")
    started_at: datetime | None = None
    hmac_signature: str | None = Field(None, max_length=128)
    is_ranked: bool = Field(False, description="Whether both players had ranked enabled")
    reported_by_steam_id: str = Field(..., max_length=20)


# ── Responses ──────────────────────────────────────────────────

class MatchResponse(BaseModel):
    """Response after successfully submitting a match."""
    match_id: UUID
    winner_steam_id: str | None
    p1_new_rating: float | None = None
    p2_new_rating: float | None = None
    message: str = "Match recorded"
    xp_gained: int = 0
    xp_bonuses: list[str] = Field(default_factory=list)
    total_xp: int = 0
    level: int = 0
    series_status: str = "none"  # "none", "active", "completed"
    series_score: str = ""       # e.g. "1-0", "2-1"
    gold_gained: int = 0
    gold_bonuses: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class PlayerStatsResponse(BaseModel):
    """Full stats for a single player."""
    steam_id: str
    display_name: str
    rating: float
    rating_deviation: float
    volatility: float
    peak_rating: float = 1500.0
    total_matches: int
    wins: int
    losses: int
    win_rate: float
    ranked_enabled: bool
    discord_id: str | None = None
    discord_username: str | None = None
    gold_earned: int = 0
    gold_spent: int = 0
    active_title: str | None = None
    active_title_color: str | None = None
    active_trail_sku: str | None = None
    active_trail_color: str | None = None
    active_trail_price: int = 0
    last_match: datetime | None
    recent_rating_history: list[dict] = Field(default_factory=list)
    top_cards: list[dict] = Field(default_factory=list)
    level: int = 0
    total_xp: int = 0
    xp_into_level: int = 0
    xp_for_next_level: int = 0
    best_ranked_streak: int = 0
    best_casual_streak: int = 0
    ranked_series_wins: int = 0
    ranked_series_losses: int = 0
    casual_wins: int = 0
    casual_losses: int = 0
    sweeps_given: int = 0
    sweeps_taken: int = 0
    ranked_dc_count: int = 0
    recent_form: list[dict] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class LeaderboardEntry(BaseModel):
    """One row on the leaderboard."""
    rank: int
    steam_id: str
    display_name: str
    rating: int
    rd: int
    total_matches: int
    wins: int
    losses: int
    win_rate: float
    level: int = 0
    gold: int = 0
    title: str | None = None
    title_color: str | None = None

    model_config = {"from_attributes": True}


class LeaderboardResponse(BaseModel):
    """Full leaderboard response."""
    entries: list[LeaderboardEntry]
    total_players: int
    last_updated: datetime


class CardStatEntry(BaseModel):
    """Stats for a single card."""
    card_name: str
    card_rarity: str | None
    times_picked: int
    matches_appeared: int
    unique_players: int
    wins_with_card: int
    win_rate: float
    times_offered: int = 0
    pass_rate: float = 0.0  # Fraction of offerings rejected (0..1). Only meaningful when times_offered > 0.

    model_config = {"from_attributes": True}


class MatchHistoryEntry(BaseModel):
    """One match in a player's history."""
    match_id: UUID
    opponent_steam_id: str
    opponent_name: str
    player_rounds_won: int
    opponent_rounds_won: int
    player_points: int = 0
    opponent_points: int = 0
    won: bool
    is_ranked: bool = False
    ended_at: datetime
    cards_picked: list[CardPick] = Field(default_factory=list)
    opponent_cards_picked: list[CardPick] = Field(default_factory=list)
    series_id: str | None = None
    series_score: str | None = None
    series_rating_change: float | None = None
    xp_gained: int = 0
    gold_gained: int = 0
    series_gold_gained: int = 0

    model_config = {"from_attributes": True}


class HealthResponse(BaseModel):
    """API health check response."""
    status: str = "ok"
    version: str = "1.0.0"
    database: str = "connected"


# ── Queue ─────────────────────────────────────────────────────

class QueueJoinRequest(BaseModel):
    """Request to join the ranked queue."""
    steam_id: str = Field(..., max_length=20)
    display_name: str | None = Field(None, max_length=64)
    region: str | None = Field(None, max_length=8)
    ranked_only: bool = False


class QueuePollResponse(BaseModel):
    """Response from polling the queue."""
    status: str  # searching, matched, ready_join, not_in_queue, expired
    wait_time: int = 0
    queue_size: int = 0
    elo_range: int = 0
    opponent_steam_id: str | None = None
    opponent_name: str | None = None
    opponent_rating: float | None = None
    opponent_ready: bool = False
    room_name: str | None = None
    photon_region: str | None = None


class QueueDeclineRequest(BaseModel):
    """Request to decline a matched opponent."""
    steam_id: str = Field(..., max_length=20)
    opponent_steam_id: str = Field(..., max_length=20)


# ── Achievements ──────────────────────────────────────────────

class AchievementUnlockRequest(BaseModel):
    """Request to unlock an achievement."""
    steam_id: str = Field(..., max_length=20)
    achievement_key: str = Field(..., max_length=64)
    match_id: str | None = None  # optional match reference


class AchievementEntry(BaseModel):
    """One achievement for a player."""
    achievement_key: str
    unlocked_at: datetime | None = None
    unlocked: bool = False

    model_config = {"from_attributes": True}


class AchievementListResponse(BaseModel):
    """All achievements for a player."""
    steam_id: str
    achievements: list[AchievementEntry]
