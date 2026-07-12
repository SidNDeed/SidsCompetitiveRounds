"""
Pydantic schemas for API request and response validation.
These define the JSON shape of data going in and out of the API.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


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
    # Anti-cheat advisory signals. Reporter's per-match input counts. NOT in HMAC —
    # these can be spoofed but provide a useful weak signal alongside duration + card count.
    local_shots_fired: int | None = Field(None, ge=0)
    local_blocks_raised: int | None = Field(None, ge=0)
    # Gun-accuracy + block-success counters (v1.23). Feed into reporter's lifetime totals so
    # Hit %/Block % can be shown on leaderboards. Also NOT in HMAC (advisory).
    local_bullets_fired: int | None = Field(None, ge=0)
    local_bullets_hit: int | None = Field(None, ge=0)
    local_blocks_activated: int | None = Field(None, ge=0)
    local_blocks_successful: int | None = Field(None, ge=0)
    # Per-match average FPS. local_avg_fps = reporter's, opponent_avg_fps = sniffed
    # off the opponent's Photon `cr_fps` custom property (only present when the
    # opponent also has the mod). Display-only; never feeds Glicko or anti-cheat.
    local_avg_fps: int | None = Field(None, ge=0, le=10000)
    opponent_avg_fps: int | None = Field(None, ge=0, le=10000)
    # Input-rate metrics (v1.29, Compare tab "avg keystrokes/sec"). Reporter's
    # per-match counts, gathered only during active combat (alive + in round).
    # Advisory / display-only, NOT in HMAC.
    local_keys_pressed: int | None = Field(None, ge=0)
    local_active_seconds: float | None = Field(None, ge=0, le=86400)
    # #50 macro detector: count of 1-second windows whose gameplay-key event
    # rate was superhuman on the reporter's client. Advisory, NOT in HMAC.
    local_macro_suspect_seconds: int | None = Field(None, ge=0, le=86400)
    # v1.30 item 4 — opponent's per-game combat stats (their cr_gstats Photon
    # prop snapshot) + the cumulative scoring timeline for the history hover
    # graph. All advisory; not in HMAC.
    opp_bullets_fired: int | None = Field(None, ge=0)
    opp_bullets_hit: int | None = Field(None, ge=0)
    opp_blocks_activated: int | None = Field(None, ge=0)
    opp_blocks_successful: int | None = Field(None, ge=0)
    opp_keys_pressed: int | None = Field(None, ge=0)
    opp_active_seconds: float | None = Field(None, ge=0, le=86400)
    point_timeline: str | None = Field(None, max_length=512)


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
    # Lifetime gun accuracy + block success counters (v1.23).
    bullets_fired: int = 0
    bullets_hit: int = 0
    blocks_activated: int = 0
    blocks_successful: int = 0
    active_title: str | None = None
    active_title_color: str | None = None
    # Raw sku of the equipped title (the display name above is REWRITTEN for the
    # dynamic 'Current Rank' title, so name equality can't identify equip state).
    active_title_sku: str | None = None
    active_trail_sku: str | None = None
    active_trail_color: str | None = None
    active_trail_price: int = 0
    active_color_sku: str | None = None
    # Player body color (kind=player_color) — overrides default team color.
    active_player_color_sku: str | None = None
    active_player_color_hex: str | None = None
    active_player_color_name: str | None = None
    # Cursor color (kind=cursor_color) — recolors the in-menu mouse cursor.
    active_cursor_color_sku: str | None = None
    active_cursor_color_hex: str | None = None
    # Player effect (kind=player_effect) — in-match particle aura, synced via Photon.
    active_player_effect_sku: str | None = None
    # Hide-gold utility: true when this player has the toggle on (gold masked on
    # the leaderboard). The client uses this to render the Other-tab toggle state.
    hide_gold: bool = False
    # Multi-equip map colors (v1.23+). The client cycles through this ordered list with
    # Left Shift in-game. Empty list → no equipped map colors → ArtHandler.NextArt falls
    # through to ROUNDS' vanilla random rotation. active_color_sku above is kept for
    # backward compat — reflects the first entry of this list when present.
    active_color_skus: list[str] = Field(default_factory=list)
    # Stackable nametag rich-text styles by sku, e.g. ["nametag_bold","nametag_italic"].
    active_nametag_skus: list[str] = Field(default_factory=list)
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
    # Compare-tab metrics (v1.28).
    avg_fps: int = 0
    avg_cards_per_game: float = 0.0
    worst_cards: list[dict] = Field(default_factory=list)
    achievements_unlocked: int = 0
    region_breakdown: list[dict] = Field(default_factory=list)  # [{region, matches}]
    # Compare-tab metrics (v1.29): input rate, game length, betting record,
    # and the player's rank tier (also drives the "Current Rank" title).
    avg_keys_per_sec: float = 0.0
    avg_keys_per_game: int = 0
    avg_game_seconds: int = 0
    bets_won: int = 0
    bets_lost: int = 0
    bet_gold_net: int = 0
    rank_name: str = ""
    rank_color: str = ""
    # 2v2 headline stats inline (saves the Compare tab a second endpoint).
    team_rating: float = 0.0
    team_completed_series: int = 0
    # Most recently observed mod version for this player (X-Mod-Version
    # header on their last mod-only request). null for non-mod players.
    mod_version: str | None = None
    # Server-computed head-to-head against the optional ?viewer_steam_id
    # query param. All zero when viewer is unset or matches steam_id.
    h2h_ranked_wins: int = 0
    h2h_ranked_losses: int = 0
    h2h_casual_wins: int = 0
    h2h_casual_losses: int = 0
    h2h_series_wins: int = 0
    h2h_series_losses: int = 0

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
    # Rank tier (v1.29) — mirrors the Discord rank roles (name without the
    # rating range) + the role's color as synced from Discord.
    rank_name: str = ""
    rank_color: str = ""

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
    opponent_title: str | None = None
    opponent_title_color: str | None = None
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
    # Per-match avg FPS. None when the reporting client predates v1.25 or the opponent
    # didn't have the mod. Display-only.
    player_fps_avg: int | None = None
    opponent_fps_avg: int | None = None
    # v1.30 item 4 — per-game combat stats, viewer-relative (server maps the
    # p1/p2 columns by who's asking). None on rows predating migration 111.
    player_bullets_fired: int | None = None
    player_bullets_hit: int | None = None
    player_blocks_activated: int | None = None
    player_blocks_successful: int | None = None
    player_keys_pressed: int | None = None
    player_active_seconds: float | None = None
    opp_bullets_fired: int | None = None
    opp_bullets_hit: int | None = None
    opp_blocks_activated: int | None = None
    opp_blocks_successful: int | None = None
    opp_keys_pressed: int | None = None
    opp_active_seconds: float | None = None
    # Cumulative scoring timeline "myTotal:oppTotal,..." — already flipped to
    # the viewer's perspective server-side.
    point_timeline: str | None = None
    # Bug batch item 4 — total game length in seconds (0 = unknown/legacy row).
    duration_seconds: int = 0

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
    # Pre-created ranked_series id (ready_join only) — lets the poll-path client
    # set ActiveRankedSeriesId just like the /queue/ready both_ready path, so
    # live-points reporting + bet locking work for poll-discovered matches too.
    series_id: str | None = None


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
    hmac_signature: str | None = None  # 'achievement:{steam_id}:{key}' — gates the gold payout (F1)


class AchievementEntry(BaseModel):
    """One achievement for a player."""
    achievement_key: str
    unlocked_at: datetime | None = None
    unlocked: bool = False
    # Server-side display name from ACHIEVEMENT_DEFS. The Compare tab reads this
    # to label its grid; without it the client prettifies the raw key and renamed
    # achievements regress to their key name ("regicide" -> "Regicide", bug #44).
    name: str | None = None
    # Steam-style global unlock rate: percent of all (non-deleted) players who
    # have this achievement. Cached server-side ~5 min; 0.0 when unknown.
    global_pct: float = 0.0

    model_config = {"from_attributes": True}


class AchievementListResponse(BaseModel):
    """All achievements for a player."""
    steam_id: str
    achievements: list[AchievementEntry]


# ── Bug reports (v1.26.7) ─────────────────────────────────────

class BugReportRequest(BaseModel):
    """In-game bug report submission. log_text is optional plain-text — server
    gzips it before persisting to disk.

    IMPORTANT: oversized fields are TRUNCATED, never rejected. A hard Pydantic
    max_length makes FastAPI return 422 Unprocessable Entity before the handler
    runs, so a player with a verbose log (a 2v2 session with diagnostic spam can
    blow past 12MB) couldn't file a bug at all — the exact failure SpicyPeppersauce
    hit. We accept whatever they send and clamp it, keeping the TAIL of the log
    (most recent events matter most for debugging) and the head of text fields."""
    steam_id: str = Field(..., max_length=64)
    display_name: str | None = Field(None, max_length=200)
    mod_version: str | None = Field(None, max_length=64)
    game_version: str | None = Field(None, max_length=64)
    severity: str = Field("medium", max_length=64)   # low | medium | high | crash
    category: str = Field("other", max_length=64)    # ui | gameplay | network | other
    description: str = Field(..., min_length=1)       # no upper cap here — clamped in validator
    repro_steps: str | None = None
    log_text: str | None = None  # no Pydantic cap — clamped to the tail in the validator below

    @field_validator("steam_id", "display_name", "mod_version", "game_version",
                     "severity", "category", mode="before")
    @classmethod
    def _clamp_short(cls, v):
        # Clamp short string fields to a safe length instead of letting an
        # over-length value trip max_length → 422. Generous ceilings (the Field
        # max_length above is the real DB-safe bound; this just prevents a hard
        # reject if a client somehow sends more).
        if isinstance(v, str) and len(v) > 64:
            return v[:64]
        return v

    @field_validator("description", "repro_steps", mode="before")
    @classmethod
    def _clamp_text(cls, v):
        # Keep the HEAD of free-text fields (the user's own words come first).
        if isinstance(v, str) and len(v) > 8000:
            return v[:8000]
        return v

    @field_validator("log_text", mode="before")
    @classmethod
    def _clamp_log(cls, v):
        # Keep the TAIL of the log — the most recent events are what matter for a
        # bug report. 12MB pre-gzip ceiling (matches the prior intent) but as a
        # truncation, not a 422-triggering hard cap.
        if isinstance(v, str) and len(v) > 12_000_000:
            return v[-12_000_000:]
        return v


class BugReportSummary(BaseModel):
    """Listed in /api/v1/bug-reports for admin triage."""
    id: str
    bug_number: int
    created_at: datetime
    steam_id: str | None
    display_name: str | None
    mod_version: str | None
    severity: str
    category: str
    status: str
    description: str
    has_log: bool
    log_bytes: int | None


class BugReportEventEntry(BaseModel):
    """One row in a bug report's activity timeline."""
    id: str
    actor_steam_id: str | None = None
    actor_name: str
    event_type: str
    old_status: str | None = None
    new_status: str | None = None
    comment: str | None = None
    created_at: datetime


class BugReportStatusRequest(BaseModel):
    """Admin POST body for /api/v1/bug-reports/{id}/status."""
    admin_steam_id: str
    hmac_signature: str | None = None
    new_status: str  # open | triaged | resolved | wontfix | dupe
    comment: str | None = None


class BugReportCommentRequest(BaseModel):
    """Admin POST body for /api/v1/bug-reports/{id}/comment."""
    admin_steam_id: str
    hmac_signature: str | None = None
    comment: str


class BugReportInternalCommentRequest(BaseModel):
    """Internal-only POST body (no HMAC, gated to localhost) used by the
    assistant to leave notes on triage. actor_name is free-form."""
    actor_name: str
    comment: str


class BugReportUserCommentRequest(BaseModel):
    """Bot-only POST body: a reporter replies to their OWN ticket via a Discord
    DM. Local-network gated (only the in-cluster bot can call it); ownership is
    verified server-side by matching discord_id to the report's reporter."""
    discord_id: str
    comment: str


# ── Tournaments (Phase 1: sync single-elim BO3) ────────────────

class TournamentSignupRequest(BaseModel):
    steam_id: str
    display_name: str | None = None
    region: str | None = None  # Photon region the client is currently on


class TournamentTimeVoteRequest(BaseModel):
    steam_id: str
    slot_ts: list[datetime]  # replaces player's entire vote set


class TournamentForceVoteRequest(BaseModel):
    steam_id: str


class TournamentReadyRequest(BaseModel):
    steam_id: str


class TournamentSignupEntry(BaseModel):
    signup_id: UUID
    steam_id: str
    display_name: str
    signed_up_at: datetime
    is_speculative: bool
    seed: int | None
    penalty_at_signup: float
    ready: bool
    forfeited: bool
    placed_rank: int | None
    progress_label: str | None = None  # "WB R2" / "LB R3" / "eliminated R2" / "CHAMPION" etc.


class TournamentMatchEntry(BaseModel):
    match_id: UUID
    round: int
    bracket_side: str
    slot_idx: int
    p1_signup_id: UUID | None
    p2_signup_id: UUID | None
    p1_display_name: str | None
    p2_display_name: str | None
    prereq_match_ids: list[UUID]
    is_bye: bool
    status: str
    series_id: UUID | None
    winner_signup_id: UUID | None
    p1_series_wins: int | None
    p2_series_wins: int | None
    ready_deadline_at: datetime | None
    deadline_at: datetime | None = None
    started_at: datetime | None
    ended_at: datetime | None
    photon_room_name: str | None = None


class TournamentTimeSlotTally(BaseModel):
    slot_ts: datetime
    votes: int


class TournamentCurrentResponse(BaseModel):
    tournament_id: UUID | None
    status: str | None
    kind: str | None
    default_start_ts: datetime | None
    scheduled_start_ts: datetime | None
    lock_at: datetime | None
    voting_closes_at: datetime | None
    started_at: datetime | None
    ended_at: datetime | None
    min_players: int
    max_players: int
    signups: list[TournamentSignupEntry]
    matches: list[TournamentMatchEntry]
    my_signup_id: UUID | None
    my_votes: list[datetime]
    my_force_vote_at: datetime | None
    my_ready: bool
    my_penalty_pct: float
    my_discord_linked: bool
    time_slot_options: list[datetime]
    # Tallies only filled when caller has voted; otherwise empty.
    time_slot_tallies: list[TournamentTimeSlotTally]
    force_vote_count: int
    photon_region: str | None = None


class TournamentHistoryEntry(BaseModel):
    tournament_id: UUID
    kind: str
    format: str
    ended_at: datetime | None
    prize_tier: str | None
    winner_display_name: str | None
    runner_up_display_name: str | None
    third_place_display_name: str | None
    signup_count: int


class TournamentPenaltyResponse(BaseModel):
    steam_id: str
    cached_penalty_pct: float
    signups_90d: int
    missed_90d: int
    no_show_last_at: datetime | None


# ── 2v2 Ranked ────────────────────────────────────────────────

class TeamQueueJoinRequest(BaseModel):
    steam_id: str = Field(..., max_length=20)
    display_name: str | None = Field(None, max_length=64)
    region: str | None = Field(None, max_length=8)
    queue_type: str | None = Field(None, max_length=8)  # 'auto' (default) or 'manual'


class TeamQueueMember(BaseModel):
    """One occupant of the queue or a locked match. Surface for the F5 tab."""
    steam_id: str
    display_name: str
    rating: int
    region: str | None = None
    team_assigned: int | None = None  # 1, 2, or null while still searching
    # Balancer transparency — surfaced so the F5 tab can show the user
    # whether the matchmaker used 2v2 elo or fell back to 1v1 elo.
    using_fallback_rating: bool = False
    balance_rating: int = 0           # the rating the balancer actually used
    completed_series: int = 0         # 2v2 series count at queue join time
    ready: bool = False               # per-slot ready flag for the lock-in prompt


class TeamQueuePollResponse(BaseModel):
    """
    Polled by all four would-be participants; the response shape is union-flat.
    Status semantics match the 1v1 queue:
      searching        — still pooling, queue_count = N/4
      matched          — locked, balancer ran, ready-up window open
      ready_join       — both teams readied, room name + region populated
      not_in_queue     — never joined or removed/expired
      expired          — timed out before lock
    """
    status: str
    queue_count: int = 0  # 0..4
    elo_range: int = 0
    series_id: str | None = None
    team_assigned: int | None = None
    teammates: list[TeamQueueMember] = Field(default_factory=list)
    opponents: list[TeamQueueMember] = Field(default_factory=list)
    room_name: str | None = None
    room_region: str | None = None
    match_age_seconds: int = 0
    my_ready: bool = False  # the polling player's own ready flag


class TeamMatchReport(BaseModel):
    """
    Submitted by the lowest-Steam-ID participant after a 2v2 game ends.
    HMAC canonical (11 fields, ':' separated):
      t1a:t1b:t2a:t2b:t1_rounds:t2_rounds:is_ranked:reporter:room_id:winner_team:series_id
    """
    series_id: str
    t1a: PlayerMatchData
    t1b: PlayerMatchData
    t2a: PlayerMatchData
    t2b: PlayerMatchData
    t1_rounds_won: int = Field(..., ge=0, le=10)
    t2_rounds_won: int = Field(..., ge=0, le=10)
    t1_points_total: int = Field(0, ge=0)
    t2_points_total: int = Field(0, ge=0)
    winner_team: int = Field(..., ge=1, le=2)
    photon_room_id: str | None = Field(None, max_length=64)
    game_version: str | None = Field(None, max_length=32)
    region: str | None = Field(None, max_length=8)
    match_duration: int | None = Field(None, ge=0)
    started_at: datetime | None = None
    hmac_signature: str | None = Field(None, max_length=128)
    is_ranked: bool = True
    reported_by_steam_id: str = Field(..., max_length=20)
    # Per-player FPS averages from each participant's mod (0/None = no data).
    t1a_fps: int | None = Field(None, ge=0, le=10000)
    t1b_fps: int | None = Field(None, ge=0, le=10000)
    t2a_fps: int | None = Field(None, ge=0, le=10000)
    t2b_fps: int | None = Field(None, ge=0, le=10000)


class TeamMatchResponse(BaseModel):
    match_id: UUID
    series_id: UUID
    series_status: str  # "active" or "completed"
    series_score: str   # "1-0" / "2-0" / "2-1" — from the reporter's team perspective
    winner_team: int
    rebalance_assignments: dict[str, int] | None = None  # filled if a rebalance triggered
    new_t1a_rating: float | None = None
    new_t1b_rating: float | None = None
    new_t2a_rating: float | None = None
    new_t2b_rating: float | None = None
    message: str = "Team match recorded"


class Team2v2LeaderboardEntry(BaseModel):
    rank: int
    steam_id: str
    display_name: str
    rating: int
    rd: int
    completed_series: int
    series_wins: int
    series_losses: int
    win_rate: float
    level: int = 0
    title: str | None = None
    title_color: str | None = None
    avg_teammate_elo: int = 0
    team_gold_earned: int = 0
    team_xp_earned: int = 0


class Team2v2LeaderboardResponse(BaseModel):
    entries: list[Team2v2LeaderboardEntry]
    total_players: int
    last_updated: datetime


class TeamStatsResponse(BaseModel):
    """Per-player 2v2 stats. Surfaced on the My Stats tab beside the 1v1 figures."""
    steam_id: str
    display_name: str
    rating: float
    rating_deviation: float
    peak_rating: float
    completed_series: int
    series_wins: int
    series_losses: int
    series_win_rate: float
    match_wins: int    # individual game wins inside completed/active series
    match_losses: int
    current_streak: int  # +N for win streak, -N for loss streak (counts series, not games)


class TeamMatchHistoryEntry(BaseModel):
    match_id: UUID
    series_id: str
    ended_at: datetime
    won: bool
    my_team: int
    t1a_steam_id: str
    t1a_name: str
    t1b_steam_id: str
    t1b_name: str
    t2a_steam_id: str
    t2a_name: str
    t2b_steam_id: str
    t2b_name: str
    t1_rounds_won: int
    t2_rounds_won: int
    t1_points_total: int = 0
    t2_points_total: int = 0
    cards_by_player: dict[str, list[CardPick]] = Field(default_factory=dict)  # keyed by steam_id
    series_score: str | None = None
    series_rating_change: float | None = None
    fps_by_player: dict[str, int] = Field(default_factory=dict)  # keyed by steam_id, 0 = missing


