"""
Pydantic schemas for API request and response validation.
These define the JSON shape of data going in and out of the API.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ── Match Submission ───────────────────────────────────────────

class CardPick(BaseModel):
    """A single card picked during a match. `rolled` is FFA-only (pushed out
    by the rolling 5-card cap; rendered red in the Recent panel) — additive
    default so 1v1/2v2/1v2 payloads are untouched."""
    card_name: str = Field(..., max_length=64, examples=["Buckshot"])
    card_rarity: str | None = Field(None, max_length=16, examples=["Common"])
    pick_order: int = Field(..., ge=1, examples=[1])
    round_number: int = Field(..., ge=1, examples=[1])
    rolled: bool = False


class CardOfferEntry(BaseModel):
    """A single card the local player was offered during a pick phase.
    round_number capped (records-v2 r2 finding 3): a real game stays well
    under 50 rounds; an unbounded value was one leg of a 14 MB report ->
    78 MB public board response amplification."""
    card_name: str = Field(..., max_length=64)
    round_number: int = Field(..., ge=1, le=50)
    was_picked: bool = False


# End-of-game BUILD STATS wire format (migration 216). One fixed-shape string
# per player, numbers only — the client renders the labels from its own
# localised catalogue, so nothing user-authored ever crosses this field:
#
#   1|hp|maxhp|dmg|aspd|reload|ammo|bullets|bursts|bounces|bspd|slow|knock|
#    spread|lifesteal|blockcd|blocks|regen|movespd|jump|jumps|size
#
# 22 pipe-separated fields; field 0 is the literal format version "1"; fields
# 1..21 are each a decimal (optionally negative, <= 3 decimal places) or "-"
# for unavailable. Structural max is 274 chars — the bound below is slack, and
# the ANCHORED regex in main.py (_clean_end_stats / _END_STATS_RE) is the real
# authority: anything that does not match is stored as NULL rather than
# failing the report. ADVISORY — outside every frozen HMAC canonical
# (1v1 7-field, 1v2 10-field, 2v2 11-field, FFA "ffa:"-tagged); none of those
# strings change for this field (hard rule #5).
END_STATS_MAX_LEN = 300


class PlayerMatchData(BaseModel):
    """Data about one player in a match report."""
    steam_id: str = Field(..., max_length=20, examples=["76561198012345678"])
    display_name: str = Field(..., max_length=64, examples=["PlayerOne"])
    cards: list[CardPick] = Field(default_factory=list, max_length=200)
    # max_length (r2 finding 3): honest clients send <= ~30 offers (prod
    # max); 1024 is 34x headroom, and only a forged report can exceed it —
    # rejecting the whole forged report is fine, an honest one never trips.
    card_offers: list[CardOfferEntry] = Field(default_factory=list, max_length=1024)
    # r3 finding 1: the picks array was the LAST unbounded list on the
    # report — 80k entries fit under the body cap and each one persisted.
    # Honest ceiling is ~30 picks; 200 is generous headroom.
    # Optional: absent from every client that predates the feature, and those
    # reports must still record normally. NULL is "not recorded", never a build
    # of zeroes (#257). Shared by 1v1, 2v2 and 1v2 — the slot this object sits
    # in already carries the seat, so no viewer-orientation mapping is needed.
    end_stats: str | None = Field(None, max_length=END_STATS_MAX_LEN)


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
    # Per-second diagnostic evidence for that detector. Timeline entries are
    # "elapsedSecond:keyRate:clickRate" and contain suspect windows only.
    local_macro_peak_kps: int | None = Field(None, ge=0, le=32767)
    local_macro_peak_cps: int | None = Field(None, ge=0, le=32767)
    local_macro_peak_eps: int | None = Field(None, ge=0, le=32767)
    local_macro_timeline: str | None = Field(None, max_length=1024)
    # The elected reporter receives the other player's compact evidence via
    # cr_gstats so macros on either side can be diagnosed.
    opp_macro_suspect_seconds: int | None = Field(None, ge=0, le=86400)
    opp_macro_peak_kps: int | None = Field(None, ge=0, le=32767)
    opp_macro_peak_cps: int | None = Field(None, ge=0, le=32767)
    opp_macro_peak_eps: int | None = Field(None, ge=0, le=32767)
    opp_macro_timeline: str | None = Field(None, max_length=1024)
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
    # July 21 — FPS/lag exploit telemetry (advisory anti-cheat, NOT in HMAC).
    # local_* = reporter's own counters; opp_* = sniffed off the opponent's
    # extended cr_gstats Photon prop. Old clients omit all of these → None →
    # NULL columns → heuristics skip. Timelines are comma-separated ints
    # ("142,138,61,..."), truncated client-side; le bounds keep a crafted
    # value from overflowing the SMALLINT columns and 500'ing the submit.
    local_fps_timeline: str | None = Field(None, max_length=512)
    opp_fps_timeline: str | None = Field(None, max_length=512)
    local_freeze_count: int | None = Field(None, ge=0, le=30000)
    local_freeze_focused_count: int | None = Field(None, ge=0, le=30000)
    local_freeze_total_sec: float | None = Field(None, ge=0, le=86400)
    local_ping_avg: int | None = Field(None, ge=0, le=30000)
    local_ping_max: int | None = Field(None, ge=0, le=30000)
    local_recv_gap_count: int | None = Field(None, ge=0, le=30000)
    # le bound: stored in an INTEGER column — an unbounded crafted value would
    # otherwise 500 the whole submit at the DB. 1h in ms covers any real gap.
    local_recv_gap_max_ms: int | None = Field(None, ge=0, le=3600000)
    # The reporter's observation of the OPPONENT's heartbeat gaps — stored on
    # the opponent's side of the match row.
    opp_hb_gap_count: int | None = Field(None, ge=0, le=30000)
    opp_freeze_count: int | None = Field(None, ge=0, le=30000)
    opp_freeze_focused_count: int | None = Field(None, ge=0, le=30000)
    opp_recv_gap_count: int | None = Field(None, ge=0, le=30000)
    # July 22 item 3 — latency timelines (own 3s GetPing samples; opponent's
    # via cr_gstats field 12) + reporter-computed opponent average.
    local_ping_timeline: str | None = Field(None, max_length=512)
    opp_ping_timeline: str | None = Field(None, max_length=512)
    opp_ping_avg: int | None = Field(None, ge=0, le=30000)
    # July 22 — cumulative Hit%/Block% timelines ("fired:hit,..." /
    # "dmgTaken:blocksSucc,...", 3s cadence) + per-point timestamps
    # ("12,47,89" seconds since match start, one per point_timeline entry).
    local_hit_timeline: str | None = Field(None, max_length=1024)
    opp_hit_timeline: str | None = Field(None, max_length=1024)
    local_block_timeline: str | None = Field(None, max_length=1024)
    opp_block_timeline: str | None = Field(None, max_length=1024)
    point_times: str | None = Field(None, max_length=512)
    # Aug 6 items 1+4 — expanded combat telemetry. All advisory, outside the
    # frozen 7-field HMAC. Damage timelines are cumulative ints (local = 5s
    # buckets, opp = ~3s cr_gstats samples). Deaths are the reporter's LOCAL
    # observations of both seats (every client simulates every death).
    # -1 is the client's "never observed" sentinel for the OPPONENT fields:
    # an older (18-field cr_gstats) peer sends no expanded telemetry, and
    # persisting its reset ZEROES alongside a real match duration would
    # permanently depress that player's DPS average with data nobody measured
    # (#257 — NULL and 0 are different facts). ge=-1 lets the sentinel through
    # validation; submit_match maps any negative to NULL before storing.
    local_damage_dealt: int | None = Field(None, ge=-1, le=100_000_000)
    opp_damage_dealt: int | None = Field(None, ge=-1, le=100_000_000)
    local_max_single_hit: int | None = Field(None, ge=-1, le=10_000_000)
    opp_max_single_hit: int | None = Field(None, ge=-1, le=10_000_000)
    local_max_health: int | None = Field(None, ge=-1, le=100_000_000)
    opp_max_health: int | None = Field(None, ge=-1, le=100_000_000)
    local_best_bounce_kill: int | None = Field(None, ge=-1, le=100_000)
    opp_best_bounce_kill: int | None = Field(None, ge=-1, le=100_000)
    local_damage_timeline: str | None = Field(None, max_length=1024)
    opp_damage_timeline: str | None = Field(None, max_length=1024)
    local_deaths: int | None = Field(None, ge=0, le=1000)
    local_deaths_boundary: int | None = Field(None, ge=0, le=1000)
    local_deaths_own_bullet: int | None = Field(None, ge=0, le=1000)
    opp_deaths: int | None = Field(None, ge=0, le=1000)
    opp_deaths_boundary: int | None = Field(None, ge=0, le=1000)
    opp_deaths_own_bullet: int | None = Field(None, ge=0, le=1000)


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
    # July 22 (migration 144): display name + the opt-in that gates showing it
    # to other players on the leaderboard detail panel.
    discord_display_name: str | None = None
    show_discord: bool = False
    # Spectator opt-out (migration 194) — Settings-tab toggle state.
    allow_spectators: bool = True
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
    # Appear-offline toggle: true when this player is hidden from the Home tab's
    # online/recently-online lists. Renders the Settings-tab toggle state.
    appear_offline: bool = False
    # Multi-equip map colors (v1.23+). The client cycles through this ordered list with
    # Left Shift in-game. Empty list → no equipped map colors → ArtHandler.NextArt falls
    # through to ROUNDS' vanilla random rotation. active_color_sku above is kept for
    # backward compat — reflects the first entry of this list when present.
    active_color_skus: list[str] = Field(default_factory=list)
    # Stackable nametag rich-text styles by sku, e.g. ["nametag_bold","nametag_italic"].
    active_nametag_skus: list[str] = Field(default_factory=list)
    last_match: datetime | None
    recent_rating_history: list[dict] = Field(default_factory=list)
    # Aug 7 — the same series for FFA (ffa_match_players.rating_after joined to
    # ffa_matches.created_at, ranked games only, ghost rows excluded, oldest ->
    # newest, same cap as the 1v1 list). The two lists do NOT share a key set:
    # a 1v1 entry is {rating, rd, date}, an FFA entry is {rating, recorded_at,
    # date} — no rd (FFA has no rating_history row to take one from), and the
    # timestamp is emitted under BOTH spellings on purpose, because the frozen
    # contract names it 'recorded_at' while the 1v1 client parser this one was
    # copied from reads 'date'. That duplication is what actually lets the
    # Compare graph read both series through one code path.
    ffa_rating_history: list[dict] = Field(default_factory=list)
    top_cards: list[dict] = Field(default_factory=list)
    level: int = 0
    total_xp: int = 0
    xp_into_level: int = 0
    xp_for_next_level: int = 0
    best_ranked_streak: int = 0
    best_casual_streak: int = 0
    # July 20 item 5: labeled game/series ranked streaks. best_ranked_streak
    # keeps its historical per-SERIES value (old clients + Compare graph bind
    # to it); current_* are SIGNED (negative = loss streak).
    best_ranked_game_streak: int = 0
    current_ranked_game_streak: int = 0
    best_ranked_series_streak: int = 0
    current_ranked_series_streak: int = 0
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
    # 1v2 + FFA headline stats inline (bug #130: My Stats -> Record covered only
    # 1v1/2v2). All FLAT SCALARS on purpose — the mod parses this payload with
    # JsonUtility, which silently fails on nested arrays but picks up scalar
    # additions with zero parser changes (learnings #25 / #73).
    # 1v2 is per GAME and split by seat, matching what the 1v2 tab shows.
    ovt_solo_wins: int = 0
    ovt_solo_losses: int = 0
    ovt_duo_wins: int = 0
    ovt_duo_losses: int = 0
    # FFA: win rate is derivable from wins/games; the rest are the three
    # averages Sid asked for. avg_damage stays 0 until enough games carry the
    # new damage_dealt telemetry.
    ffa_games: int = 0
    ffa_wins: int = 0
    ffa_top3: int = 0
    ffa_avg_placement: float = 0.0
    ffa_avg_kills: float = 0.0
    ffa_avg_damage: float = 0.0
    # How many of this player's FFA games actually carry damage telemetry.
    # 0 = "no data yet", which is how the client tells that apart from a
    # legitimate ffa_avg_damage of 0.0 (a real game where they dealt none).
    ffa_damage_games: int = 0
    # Most recently observed mod version for this player (X-Mod-Version
    # header on their last mod-only request). null for non-mod players.
    mod_version: str | None = None
    # LFP Discord-ping cooldown (July 21): seconds until this player may fire
    # the next /lfp-ping. 0 = available now. Flat int — the mod's
    # JsonUtility parse picks it up with zero parser changes (learning #73).
    lfp_seconds_left: int = 0
    # Server-computed head-to-head against the optional ?viewer_steam_id
    # query param. All zero when viewer is unset or matches steam_id.
    h2h_ranked_wins: int = 0
    h2h_ranked_losses: int = 0
    h2h_casual_wins: int = 0
    h2h_casual_losses: int = 0
    h2h_series_wins: int = 0
    h2h_series_losses: int = 0
    # Aug 6 item 1 — Compare-tab scalar additions (migration 191). All FLAT
    # scalars so the client's JsonUtility parse picks them up with zero parser
    # changes (learnings #25 / #73). Defaults are the zero-data shape — a fresh
    # account (or the deploy-order window before migration 191) renders these
    # as "no data", never 500s.
    # ── "Rage Quit %" — RE-ORIENTED Aug 12 (item 12) ──────────────────────
    # It now measures HOW OFTEN THIS PLAYER'S QUICKPLAY OPPONENTS QUIT ON
    # THEM, which is what it was always meant to be. It used to measure how
    # often the player abandoned their OWN casual games — a shame stat about
    # the leaver, which is not what the name promises and not what anyone
    # wanted to read on their own profile. The NAME is unchanged (owner
    # decision); the number and every description are not.
    #
    #   numerator   = casual_dc_events where THIS player is the REPORTER
    #                 (i.e. they were the one left behind)
    #   denominator = their recorded casual 1v1 matches
    #                 + their reporter-side DC events whose own game produced
    #                   no match row
    #
    # The denominator is a UNION, not a sum: a leave at 4-0 is BOTH a recorded
    # casual match AND a DC event, and counting it twice halves the rate.
    # The two tables identify a room DIFFERENTLY (raw Photon name vs the
    # suffixed report id), so the union is computed by prefix + report ordering
    # in get_player_stats — that note is the authority, not this summary.
    #
    # This works against completely unmodded opponents — the casual DC branch
    # has no has-mod gate and resolves the leaver from ROUNDS' own vanilla
    # `u_id` player property, so a vanilla quickplay peer is fully attributable.
    casual_rage_quit_pct: float = 0.0
    # The percentage's OWN numerator: opponents who quit on this player.
    # Paired with casual_rage_quit_pct on every surface, so it must move with
    # it — a client rendering "3% (n/N)" needs n to be this number.
    casual_dc_count: int = 0
    # Same value under an unambiguous name. New clients should bind here;
    # casual_dc_count is kept in step for clients that predate the re-orientation.
    casual_opponent_dc_count: int = 0
    # The OLD number, preserved and renamed: casual games THIS player
    # abandoned (players.casual_dc_count). Neither the column nor its data was
    # touched — only what the headline percentage is computed from.
    casual_own_dc_count: int = 0
    casual_matches: int = 0
    # Damage-per-second over matches that CARRY damage telemetry (#257 —
    # pre-telemetry rows are excluded from both numerator and denominator).
    ranked_dps: float = 0.0
    ffa_dps: float = 0.0
    # Death breakdown, both-seat side-mapped sums over non-invalidated 1v1s.
    # self_death_pct = (boundary + own_bullet) / total deaths recorded.
    self_death_pct: float = 0.0
    deaths_total: int = 0
    deaths_boundary: int = 0
    deaths_own_bullet: int = 0
    # Career records (players.record_*). None = never recorded, not zero.
    record_max_single_hit: int | None = None
    record_max_health: int | None = None
    record_bounce_kill: int | None = None
    # Opponent variety over COMPLETED (non-invalidated) ranked series:
    # distinct opponents / total series.
    ranked_unique_opponents: int = 0
    ranked_total_series: int = 0
    ranked_uniqueness_pct: float = 0.0
    # ── Aug 12 item 2 — multi-mode ratings + numeric standings ────────────
    # All FLAT scalars, so the mod's JsonUtility parse picks them up with zero
    # parser changes (#25 / #73).
    #
    # Every standing is COMPETITION-STYLE (1 + how many eligible players are
    # strictly ahead) computed with the SAME eligibility filter and ordering
    # its board actually uses AS CALLED (#153) — not the endpoint's parameter
    # defaults — so the number agrees with the row the player sees. Two players
    # on identical values share a standing; the board's own ROW_NUMBER breaks
    # such a tie arbitrarily, so the shared number is the honest one.
    #
    # standing = 0 means NOT ON THAT BOARD (no games, below the entry floor, or
    # a deleted row) — it is never a real position. *_standing_population is
    # that board's total eligible population, i.e. the "of N" half of "#7 of N".
    standing: int = 0
    standing_population: int = 0
    # 2v2. team_rating / team_completed_series already existed above.
    team_rating_deviation: float = 0.0
    team_peak_rating: float = 0.0
    team_standing: int = 0
    team_standing_population: int = 0
    # FFA. peak_rating IS maintained server-side (GREATEST on every rated
    # game) but was returned by no endpoint until now.
    ffa_rating: float = 0.0
    ffa_rating_deviation: float = 0.0
    ffa_peak_rating: float = 0.0
    ffa_standing: int = 0
    ffa_standing_population: int = 0
    # 1v2 has NO RATING — glicko_ratings_1v2's rating columns are never
    # written by anything, so there is no rating, RD or peak to return and one
    # must not be invented. The 1v2 record is W/L only (ovt_solo_wins /
    # ovt_solo_losses / ovt_duo_wins / ovt_duo_losses above); the standing
    # below is that board's own ordering — games played, then win rate — over
    # the COMBINED role, which is the role the board opens on.
    ovt_standing: int = 0
    ovt_standing_population: int = 0

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
    # Aug 31 (Compare > Cards metrics): 5-0 match wins carrying the card, and
    # builds that stacked >= 2 copies of it. Defaults keep a stale replica's
    # rows parseable (#422 — new response fields, absent until it rebuilds).
    sweeps_with_card: int = 0
    stacked_builds: int = 0

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
    # July 21 — per-match FPS timelines (comma-separated ints, viewer-relative
    # like the other per-side columns). None on rows predating migration 136
    # or when the side's client didn't report one. Drives the history FPS
    # hover graph.
    player_fps_timeline: str | None = None
    opp_fps_timeline: str | None = None
    # July 22 item 3 — viewer-relative latency.
    player_ping_avg: int = 0
    opponent_ping_avg: int = 0
    player_ping_timeline: str | None = None
    opp_ping_timeline: str | None = None
    # July 22 — viewer-relative cumulative Hit%/Block% timelines
    # ("fired:hit,..." / "dmgTaken:blocksSucc,...") + per-point timestamps in
    # seconds since match start (no orientation — who scored is derived by
    # diffing point_timeline pairs). Drive the new history hover graphs.
    player_hit_timeline: str | None = None
    opp_hit_timeline: str | None = None
    player_block_timeline: str | None = None
    opp_block_timeline: str | None = None
    point_times: str | None = None
    # Bug batch item 4 — total game length in seconds (0 = unknown/legacy row).
    duration_seconds: int = 0
    # Aug 6 item 1 (migration 191) — viewer-relative damage + death telemetry.
    # None on every row recorded before the expanded-telemetry clients (#257:
    # "not recorded", never zero). damage_timeline is a cumulative-int CSV.
    player_damage_dealt: int | None = None
    opp_damage_dealt: int | None = None
    player_damage_timeline: str | None = None
    opp_damage_timeline: str | None = None
    player_deaths: int | None = None
    player_deaths_boundary: int | None = None
    player_deaths_own_bullet: int | None = None
    opp_deaths: int | None = None
    opp_deaths_boundary: int | None = None
    opp_deaths_own_bullet: int | None = None
    # Migration 216 — each side's END-OF-GAME BUILD (the 21 hold-Tab stats),
    # viewer-relative like the columns above. Format documented at
    # PlayerMatchData.end_stats. None on every pre-216 row and on any row whose
    # reporter predates the field: the client must render "no data", never a
    # build of zeroes (#257).
    player_end_stats: str | None = None
    opp_end_stats: str | None = None

    model_config = {"from_attributes": True}


class HealthResponse(BaseModel):
    """API health check response."""
    status: str = "ok"
    version: str = "1.0.0"
    database: str = "connected"
    # Which ROLE answered. Before this, /health was byte-identical on the
    # primary and on the read standby -- same status, same version, same
    # database -- so nothing on the network could tell a box that SKIPS writes
    # from one that performs them, and the only way to find out was to exec
    # into the container. A failover lever pointed at that signal would happily
    # move all traffic onto the replica with every probe still green.
    #
    # That is the same defect shape as the boot banner it complements: an
    # absence cannot distinguish "read replica" from "old build that predates
    # the flag". This field makes the role a POSITIVE signal at runtime, the
    # banner does it at boot, and neither relies on the absence of anything.
    #
    # Deliberately on the UNAUTHENTICATED health path rather than an admin
    # route: the consumer is monitoring and failover, which must be able to ask
    # this without holding a credential, and the disclosure is a topology fact
    # about a box that is not individually reachable from the internet (the
    # edge fronts both). Health endpoints that hide operational truth to save a
    # byte of disclosure are how the wrong box gets promoted.
    replica: bool = False


# ── Queue ─────────────────────────────────────────────────────

class QueueJoinRequest(BaseModel):
    """Request to join the ranked queue."""
    steam_id: str = Field(..., max_length=20)
    display_name: str | None = Field(None, max_length=64)
    region: str | None = Field(None, max_length=8)
    # Aug 15 item 5: Photon's cached best-region ("home") — distinct from
    # `region` (the live CloudRegion snapshot, which region-churn/offline
    # states make wrong or empty). Optional so pre-1.38.7 clients keep
    # working; the room-region pick prefers two AGREEING home regions.
    home_region: str | None = Field(None, max_length=8)
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
    # Bug 200 (Aug 11): the resumed BO3 tally, carried alongside series_id.
    # Setting ActiveRankedSeriesId from series_id closes the
    # IsNullOrEmpty(ActiveRankedSeriesId) gate on both /series/preflight
    # arming sites, and the preflight "exists" branch is the only other place
    # the client can learn a resumed score — so a series resumed through the
    # queue rendered 0-0 on the in-match HUD. Field names and perspective
    # semantics MIRROR that preflight response exactly, so the client adopts
    # with one shared helper instead of a divergent second copy (#330).
    # Old clients ignore these; a new client against an old server sees None
    # and behaves exactly as before. Safe in both skew directions.
    p1_steam_id: str | None = None
    p2_steam_id: str | None = None
    p1_wins: int = 0
    p2_wins: int = 0


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
    # Gold paid on unlock (v1.32). Server truth from _achievement_gold(),
    # which reads ACHIEVEMENT_GOLD_OVERRIDES: values run from the 100 default
    # through the 300/500 tiers to 1000 for the slayers. The six FFA keys sit
    # on those same tiers (two at 100, two at 300, two at 500; priced
    # 2026-08-07) after shipping unpaid for one day — the second time this
    # comment has needed correcting, so read the table, not a restatement.
    #
    # The default below stays 100 only for OLD servers that omit the field;
    # a modern response always carries the real number.
    gold: int = 100

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
    # Sync signups must state which offered start slots they can make (>= 1);
    # recorded as the player's time votes in the same transaction. Ignored
    # for async tournaments and by unsignup (which shares this schema).
    slot_ts: list[datetime] = []


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
    # Aug 17 bracket-clarity batch: identity for the signups list + bracket
    # cells. rating = cached_elo_at_lock once seeded (stable, matches the
    # seeds), live glicko before lock. Title resolves through
    # _display_title_sync (#111) with the podium maps wired (round-2 f15),
    # so dynamic skus — rank AND podium — render their live form.
    rating: int | None = None
    title: str | None = None
    title_color: str | None = None


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
    # Prizes scale with confirmed player count (July 17 round 2): live count
    # while voting, locked snapshot afterward. Flat ints — the mod's manual
    # parser reads scalars.
    prize_players: int = 0
    prize_gold_1: int = 0
    prize_gold_2: int = 0
    prize_gold_3: int = 0
    prize_xp_1: int = 0
    prize_xp_2: int = 0
    prize_xp_3: int = 0
    signups: list[TournamentSignupEntry]
    matches: list[TournamentMatchEntry]
    my_signup_id: UUID | None
    my_votes: list[datetime]
    my_force_vote_at: datetime | None
    my_ready: bool
    my_penalty_pct: float
    my_discord_linked: bool
    time_slot_options: list[datetime]
    # Tallies are public during voting (mandatory-vote coordination).
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


class TeamPlayerTelemetry(BaseModel):
    """Per-player 2v2 telemetry (July 22, migration 142). Advisory — NOT in
    the HMAC. The reporter's own slot comes from its counters; the other three
    slots from each peer's cr_gstats Photon prop. Bounds mirror MatchReport's
    so a crafted value can't overflow a column and 500 the submit."""
    fps_timeline: str | None = Field(None, max_length=512)
    ping_timeline: str | None = Field(None, max_length=512)
    ping_avg: int | None = Field(None, ge=0, le=30000)
    hit_timeline: str | None = Field(None, max_length=1024)
    block_timeline: str | None = Field(None, max_length=1024)
    # Aug 7 — cumulative damage-dealt CSV, matching the column migration 201
    # adds to team_match_telemetry. None from clients that predate it; NULL is
    # "not recorded", which is a different fact from a real zero (#257).
    damage_dealt_timeline: str | None = Field(None, max_length=1024)
    bullets_fired: int | None = Field(None, ge=0, le=1000000)
    bullets_hit: int | None = Field(None, ge=0, le=1000000)
    blocks_activated: int | None = Field(None, ge=0, le=1000000)
    blocks_successful: int | None = Field(None, ge=0, le=1000000)
    keys_pressed: int | None = Field(None, ge=0, le=10000000)
    active_seconds: float | None = Field(None, ge=0, le=86400)


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
    # July 22 — per-slot telemetry blobs (timelines + hit/block counters).
    # None from old clients; slots whose peer data never reached the reporter
    # are None individually.
    t1a_telemetry: TeamPlayerTelemetry | None = None
    t1b_telemetry: TeamPlayerTelemetry | None = None
    t2a_telemetry: TeamPlayerTelemetry | None = None
    t2b_telemetry: TeamPlayerTelemetry | None = None


class TeamMatchResponse(BaseModel):
    match_id: UUID
    series_id: UUID
    series_status: str  # "active" or "completed"
    series_score: str   # "1-0" / "2-0" / "2-1" — from the reporter's team perspective
    winner_team: int
    rebalance_assignments: dict[str, int] | None = None  # ALWAYS None today (proposal-only server; dormant until the client-side swap ships)
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
    # Aug 12 item 2: peak was only reachable through /team/team-stats.
    # Falls back to the current rating when the stored peak is NULL.
    peak_rating: int = 0
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


# ── 1v2 (solo vs duo) ────────────────────────────────────────────────
class OvtMatchReport(BaseModel):
    """
    Submitted by the lowest-Steam-ID participant after a 1v2 game ends.
    HMAC canonical (10 fields, ':' separated) — NEW format, distinct from the
    1v1 (7) and 2v2 (11) formats which must never change (hard rule #5):
      solo:duo_a:duo_b:solo_rounds:duo_rounds:is_ranked:reporter:room_id:winner_side:series_id
    """
    series_id: str
    solo: PlayerMatchData
    duo_a: PlayerMatchData
    duo_b: PlayerMatchData
    solo_rounds_won: int = Field(..., ge=0, le=10)
    duo_rounds_won: int = Field(..., ge=0, le=10)
    solo_points_total: int = Field(0, ge=0)
    duo_points_total: int = Field(0, ge=0)
    winner_side: int = Field(..., ge=1, le=2)  # 1 = solo, 2 = duo
    photon_room_id: str | None = Field(None, max_length=64)
    game_version: str | None = Field(None, max_length=32)
    region: str | None = Field(None, max_length=8)
    match_duration: int | None = Field(None, ge=0)
    started_at: datetime | None = None
    hmac_signature: str | None = Field(None, max_length=128)
    is_ranked: bool = False  # unscored at launch
    reported_by_steam_id: str = Field(..., max_length=20)
    solo_fps: int | None = Field(None, ge=0, le=10000)
    duo_a_fps: int | None = Field(None, ge=0, le=10000)
    duo_b_fps: int | None = Field(None, ge=0, le=10000)
    # Aug 7 — per-seat cumulative damage-dealt CSVs, matching the columns
    # migration 201 adds to ovt_matches. 1v2 has no telemetry table, so these
    # hang off the match row beside the fps averages rather than mirroring the
    # 2v2 per-slot blob. Advisory: outside the frozen 10-field HMAC canonical.
    # None from clients that predate them; NULL is "not recorded", never a real
    # zero (#257).
    solo_damage_timeline: str | None = Field(None, max_length=1024)
    duo_a_damage_timeline: str | None = Field(None, max_length=1024)
    duo_b_damage_timeline: str | None = Field(None, max_length=1024)


class OvtMatchResponse(BaseModel):
    match_id: UUID
    series_id: UUID
    series_status: str          # "active" | "completed"
    series_score: str           # solo-duo, from the reporter's own side perspective
    winner_side: int
    message: str = "1v2 match recorded"
    # Bug #129: the REPORTER's own reward for this game, so the client has
    # something to show. 1v2 paid xp+gold from day one but no surface ever
    # rendered it, which is why it read as "1v2 doesn't provide XP/gold".
    # Mirrors FfaMatchResponse / MatchResponse. Zero on an idempotent replay —
    # a re-report pays nothing, so it must not claim to.
    xp_gained: int = 0
    gold_gained: int = 0
    xp_bonuses: list[str] = Field(default_factory=list)


class Ovt1v2LeaderboardEntry(BaseModel):
    rank: int
    steam_id: str
    display_name: str
    games_played: int
    wins: int
    losses: int
    win_rate: float
    solo_games: int
    duo_games: int
    # July 22: W/L split by role — games played as solo vs as duo half.
    solo_wins: int = 0
    solo_losses: int = 0
    duo_wins: int = 0
    duo_losses: int = 0
    level: int = 0
    title: str | None = None
    title_color: str | None = None
    last_played: str | None = None


class Ovt1v2LeaderboardResponse(BaseModel):
    entries: list[Ovt1v2LeaderboardEntry]
    total_players: int
    last_updated: datetime
    is_ranked: bool = False  # tells the client to show "unranked" labeling


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


# ── FFA (free-for-all, 3-10 players) ─────────────────────────────────
class FfaPlayerEntry(BaseModel):
    """One participant in an FFA match report. Rounds/points are that player's
    own tallies from the mod's FFA score engine; cards/telemetry mirror the
    2v2 per-slot surface so stat parity holds from day one."""
    steam_id: str = Field(..., max_length=20)
    display_name: str = Field("Player", max_length=64)
    slot: int = Field(0, ge=0, le=15)
    rounds_won: int = Field(0, ge=0, le=20)
    points_total: int = Field(0, ge=0, le=200)
    # Placement tie-break (rounds, then points, then kills) — but ONLY when
    # the report verified under the v2 canonical, which SIGNS kills, AND the
    # lobby's frozen kills_tiebreak capability flag is set (see main.py
    # _verify_ffa_hmac + submit_ffa_match). 0 from pre-kills clients.
    # 2000 is deliberate SATURATION, part of the ordering RULE, not a bound
    # believed to exceed the ceiling (full-wipe battles advance no point, so
    # raw kills are structurally unbounded — Codex Aug-3 r2 find 3): the
    # client compares AND signs min(kills, 2000), so above the bound kills
    # compare equal on every surface by definition.
    kills: int = Field(0, ge=0, le=2000)
    # Damage dealt + cumulative kill/damage timelines (bugs #127 / #130).
    # Also OUTSIDE the frozen ffa: HMAC canonical (#213) — advisory telemetry,
    # bounded so a crafted value can't overflow a column and 500 the submit.
    # None (not 0) is the default ON PURPOSE: it is the ONLY way to tell a
    # pre-v1.35.3 client that never sends the field from a player who genuinely
    # dealt no damage. A `0` default would make both arrive as 0, and either the
    # avg-damage aggregate counts phantom zeros or it discards real ones (#257).
    damage_dealt: int | None = Field(None, ge=0, le=10000000)
    kill_timeline: str | None = Field(None, max_length=512)
    damage_dealt_timeline: str | None = Field(None, max_length=1024)
    left_early: bool = False
    # True = left in an EARLIER game of the sitting (roster ghost: holds the
    # slot for the frozen-roster check, never rated/rewarded). False +
    # left_early = left DURING this game — still rated, so leaving at zero
    # score can't dodge the loss.
    absent: bool = False
    # Total points the WHOLE FIELD had scored at the moment this player left —
    # set only on left_early entries, by a client that was still in the room.
    # Under FFA_LEAVE_GRACE_POINTS the server does not rate them (the 2026-08-20
    # early-leave grace). None = not reported: a pre-v1.39 client, a present
    # player, or a carried roster ghost — all of which keep pre-grace behaviour.
    # Also OUTSIDE the frozen ffa: HMAC canonical, like `absent` and
    # `damage_dealt`; submit_ffa_match refutes the claim against the signed
    # tally. Bounded so a crafted value cannot overflow the SMALLINT column.
    game_points_at_leave: int | None = Field(None, ge=0, le=32000)
    fps: int | None = Field(None, ge=0, le=10000)
    # Generous hard bounds (reject only absurd bodies — the quarantine path
    # persists full payloads, so unbounded lists are a storage-inflation
    # primitive; Codex v1.36 find 6/9). The honest structural max at 10
    # players / first-to-10 is ~90 picks and ~450 offers; the award loops
    # truncate at 128/512.
    cards: list[CardPick] = Field(default_factory=list, max_length=256)
    # Per-draw offered candidates (§10 of the config-lobby spec: FFA reported
    # no offers at all, so every candidate-count question was answered from
    # 1v1-extrapolated data — this is the pre/post baseline). Outside the
    # frozen ffa: HMAC canonical; absent from pre-v1.36 clients. Only the
    # REPORTER can know every seat's offers under the same-card rule; in
    # private-roll games each client only knows its own, so entries here are
    # best-effort and bounded.
    card_offers: list[CardOfferEntry] = Field(default_factory=list, max_length=1024)
    telemetry: TeamPlayerTelemetry | None = None
    # End-of-game build stats (migration 216) — see PlayerMatchData.end_stats
    # for the format. FFA does not use PlayerMatchData, so the field is
    # declared here too. Outside the frozen "ffa:"-tagged HMAC canonical.
    end_stats: str | None = Field(None, max_length=END_STATS_MAX_LEN)


class FfaMatchReport(BaseModel):
    """
    Submitted by the lowest-Steam-ID participant after an FFA game ends.
    HMAC canonical — variable-length format, domain-separated by the "ffa"
    literal so it can never collide with the frozen 7/10/11-field formats:
      ffa:{lobby_id}:{room}:{reporter}:{is_ranked}:{winner_steam}:{n}
        then, per player sorted by numeric steam id:
          v2 (v1.36.0+): :{steam}:{rounds}:{points}:{kills}
          v1 (legacy):   :{steam}:{rounds}:{points}
    The server accepts BOTH for one release (main.py _verify_ffa_hmac); the
    kills tie-break applies only to v2-verified reports.
    """
    lobby_id: str
    players: list[FfaPlayerEntry] = Field(..., min_length=2, max_length=10)
    winner_steam_id: str = Field(..., max_length=20)
    photon_room_id: str | None = Field(None, max_length=64)
    game_version: str | None = Field(None, max_length=32)
    region: str | None = Field(None, max_length=8)
    match_duration: int | None = Field(None, ge=0)
    started_at: datetime | None = None
    hmac_signature: str | None = Field(None, max_length=160)
    is_ranked: bool = True
    reported_by_steam_id: str = Field(..., max_length=20)
    # Compact half-point event list "slot[R][G],slot,..." from the reporter's
    # engine (score-progression hover graph). Outside the frozen HMAC
    # canonical; absent from pre-timeline clients.
    timeline: str | None = Field(None, max_length=2000)


class FfaMatchResponse(BaseModel):
    match_id: UUID
    lobby_id: UUID
    placement: int              # the REPORTER's own placement (1 = won)
    player_count: int
    rating_changes: dict[str, float] = Field(default_factory=dict)  # steam_id -> delta
    xp_gained: int = 0          # reporter's own
    gold_gained: int = 0        # reporter's own
    message: str = "FFA match recorded"


class FfaLeaderboardEntry(BaseModel):
    rank: int
    steam_id: str
    display_name: str
    rating: int
    rd: int
    # Aug 12 item 2: glicko_ratings_ffa.peak_rating has been maintained on
    # every rated game since FFA shipped but was returned by no endpoint.
    # Defaults to the entry's current rating server-side when the stored peak
    # is NULL, so it is never lower than what the row already shows.
    peak_rating: int = 0
    games_played: int
    wins: int                   # 1st places
    top3: int
    avg_placement: float        # over recorded games
    win_rate: float             # fraction 0-1 (matches 1v1/2v2 convention)
    level: int = 0
    title: str | None = None
    title_color: str | None = None
    ffa_gold_earned: int = 0
    ffa_xp_earned: int = 0


class FfaLeaderboardResponse(BaseModel):
    entries: list[FfaLeaderboardEntry]
    total_players: int
    last_updated: datetime
    is_ranked: bool = True


# ── Compare-tab stat boards (Aug 6 item 1) ────────────────────────────
# All of these use PARALLEL ARRAYS instead of nested objects on purpose:
# the client parses flat arrays natively and JsonUtility silently fails on
# nested arrays (learning #25).

class RecordsBoardResponse(BaseModel):
    """Mini-leaderboard of per-game records (match-derived, Aug 17). Still
    parallel arrays (#25). The original three arrays keep their exact
    meaning so pre-Aug-17 clients parse unchanged; everything below them is
    additive enrichment: the game's date, the holder's resolved title +
    rating, their cards that game ('|'-joined), and the opponent. cards2 /
    ratings2 are populated only by the match-scoped game-length boards
    (both participants shown)."""
    board: str
    display_names: list[str] = Field(default_factory=list)
    steam_ids: list[str] = Field(default_factory=list)
    values: list[int] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    titles: list[str] = Field(default_factory=list)
    title_colors: list[str] = Field(default_factory=list)
    ratings: list[int] = Field(default_factory=list)
    cards: list[str] = Field(default_factory=list)
    names2: list[str] = Field(default_factory=list)
    steam_ids2: list[str] = Field(default_factory=list)
    cards2: list[str] = Field(default_factory=list)
    ratings2: list[int] = Field(default_factory=list)
    # Aug 18: the source match per row, so the admin record-removal control
    # can name exactly which (board, match, seat) to exclude.
    match_ids: list[str] = Field(default_factory=list)
    # Aug 18 (Sid: "show game duration, score"): per-row game details.
    # scores are preformatted holder-first with the half-point convention
    # (mirrors the client's FmtHalfScore residue rule — see _rec_half_score).
    durations: list[int] = Field(default_factory=list)
    scores: list[str] = Field(default_factory=list)


class CardTopPickersResponse(BaseModel):
    """Who picks one card the most, with their win rate holding it."""
    card_name: str
    display_names: list[str] = Field(default_factory=list)
    steam_ids: list[str] = Field(default_factory=list)
    picks: list[int] = Field(default_factory=list)
    win_rates: list[float] = Field(default_factory=list)  # 0..1 per entry


class CardPickersSummaryResponse(BaseModel):
    """Top pickers for EVERY card, flattened as 'card|name|picks|winrate'
    pipe-CSV strings (the client parses pipe strings natively; pipes are
    stripped from display names before assembly — names are adversarial
    input, #156)."""
    entries: list[str] = Field(default_factory=list)


class CardLeadersSummaryResponse(BaseModel):
    """Per-card top players by 5-0 sweeps and by match wins, flattened as
    'card|name|count' pipe-CSV strings (same #25/#156 rationale as
    CardPickersSummaryResponse). Rows arrive grouped by card in rank order."""
    sweepers: list[str] = Field(default_factory=list)
    winners: list[str] = Field(default_factory=list)


class RankedFriendsResponse(BaseModel):
    """Most-played ranked opponents (completed series count), pie source."""
    display_names: list[str] = Field(default_factory=list)
    steam_ids: list[str] = Field(default_factory=list)
    series_counts: list[int] = Field(default_factory=list)


class GoldSourcesResponse(BaseModel):
    """Where a player's positive gold came from, bucketed. Only buckets
    with a nonzero total appear; sorted by amount desc."""
    buckets: list[str] = Field(default_factory=list)
    amounts: list[int] = Field(default_factory=list)


class NemesisResponse(BaseModel):
    """Opponents with the best win rate against a set of target players."""
    display_names: list[str] = Field(default_factory=list)
    steam_ids: list[str] = Field(default_factory=list)
    wins: list[int] = Field(default_factory=list)
    games: list[int] = Field(default_factory=list)
    win_rates: list[float] = Field(default_factory=list)  # 0..1 per entry
    # Aug 7 — which of the REQUESTED targets actually faced this opponent,
    # index-aligned with the arrays above (element i is entry i's subset).
    # Nested rather than a comma-joined string because the entries are numeric
    # steam ids only: no user-authored text can appear inside, so the client may
    # slice this with a plain depth counter (the string-aware matcher of #156 is
    # only required where display names can carry brackets).
    faced_by: list[list[str]] = Field(default_factory=list)


class PlayerNemesisEntry(BaseModel):
    """One opponent on a single player's personal nemesis list. Counts are
    ranked 1v1 SERIES, not individual games."""
    steam_id: str
    display_name: str
    series_played: int
    series_lost: int
    loss_rate: float  # 0..1 — series_lost / series_played


class PlayerNemesisPlayer(BaseModel):
    """One of the requested players, with their own nemeses attached."""
    steam_id: str
    display_name: str
    nemeses: list[PlayerNemesisEntry] = Field(default_factory=list)


class PlayerNemesisResponse(BaseModel):
    """Per-player nemesis lists (Aug 7). NESTED, unlike the parallel-array
    boards above: the answer is grouped BY player, and flattening it would need
    a second index array for the client to regroup from. The client parses it by
    hand either way — JsonUtility silently fails on nested arrays (#25) — and
    display_name is user-authored, so that slicing must use the string-aware
    bracket matcher (#156).

    Semantic difference from NemesisResponse worth stating where it is easy to
    miss: co-selected targets are deliberately NOT excluded here. "Who beats me
    most" is a per-player question, and dropping a rival because they happen to
    also be selected would answer a different one."""
    players: list[PlayerNemesisPlayer] = Field(default_factory=list)


class BuildTypeResponse(BaseModel):
    """Ranked card picks classified into build-type buckets (weighted:
    a card touching N buckets adds 1 to each). Display-only taxonomy."""
    buckets: list[str] = Field(default_factory=list)
    counts: list[int] = Field(default_factory=list)
    total_picks: int = 0


class SimilarPlayersResponse(BaseModel):
    """Most similar players by profile vector (hit%, block%, ranked DPS,
    keys/sec, build-type shares). Scores are 0-100 display values."""
    display_names: list[str] = Field(default_factory=list)
    steam_ids: list[str] = Field(default_factory=list)
    similarity_scores: list[float] = Field(default_factory=list)


# ── Spectator mode (Aug 6 item 13, design §6) ─────────────────────────────

class SpectateAttestBody(BaseModel):
    """Fighter-side room attestation. Strict-session; POST body so the room
    credential never reaches access-log URLs (design §6.3)."""
    steam_id: str = Field(min_length=1, max_length=32)
    mode: str = Field(min_length=3, max_length=8)
    source_ref: str = Field(default="", max_length=64)
    room_name: str = Field(min_length=1, max_length=64)
    region: str = Field(default="", max_length=16)
    actor_number: int = Field(default=-1, ge=-1, le=255)
    fighter_target: int = Field(ge=2, le=10)
    room_capacity: int = Field(default=0, ge=0, le=32)
    spectator_protocol: int = Field(default=1, ge=1, le=100)
    phase: str = Field(default="", max_length=16)
    # Sorted comma-joined fighter steam ids — must be byte-identical across
    # all attesters (design §6.3).
    roster: str = Field(default="", max_length=400)


class SpectateCloseBody(BaseModel):
    """Fighter-side 'I have left this room'. Strict-session, and the caller
    must be in the room's roster — a stranger cannot close someone's game.

    Retracting your OWN attestation is always truthful, so this can only ever
    remove the caller from the live set; the row itself is ended only once no
    OTHER fighter is still attesting. That keeps an FFA leaver (whose exit does
    not end the game, #222) from closing a match the survivors are still
    playing, while a 1v1 pair walking away ends theirs immediately."""
    steam_id: str = Field(min_length=1, max_length=32)
    room_name: str = Field(min_length=1, max_length=64)


class SpectateGrantBody(BaseModel):
    steam_id: str = Field(min_length=1, max_length=32)
    game_id: str = Field(min_length=1, max_length=64)
    client_protocol: int = Field(default=1, ge=1, le=100)


class SpectateLeaseBody(BaseModel):
    """Heartbeat / leave — identifies the lease by id; identity comes from
    the strict session, never the body."""
    steam_id: str = Field(min_length=1, max_length=32)
    lease_id: str = Field(min_length=1, max_length=64)


class SpectateValidateEntry(BaseModel):
    actor_number: int = Field(ge=0, le=255)
    steam_id: str = Field(default="", max_length=32)


class SpectateValidateBody(BaseModel):
    """Master-fighter validation of claimed spectator actors (design §6.6)."""
    steam_id: str = Field(min_length=1, max_length=32)
    room_name: str = Field(min_length=1, max_length=64)
    spectators: list[SpectateValidateEntry] = Field(default_factory=list, max_length=8)


class AllowSpectatorsBody(BaseModel):
    steam_id: str = Field(min_length=1, max_length=32)
    allow: bool
