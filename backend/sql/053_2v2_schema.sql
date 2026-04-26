-- 053_2v2_schema.sql
-- 2v2 ranked mode foundation. Lives in parallel with the 1v1 path — separate
-- queue/series/match tables, separate Glicko ratings — so 1v1 stays untouched.
--
-- Match-submit HMAC canonical (11 fields, sorted): see schemas.py / verify_team_hmac.

-- ── Per-player 2v2 Glicko-2 rating ──────────────────────────────
CREATE TABLE IF NOT EXISTS glicko_ratings_2v2 (
    player_id UUID PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
    rating DOUBLE PRECISION NOT NULL DEFAULT 1500.0,
    rating_deviation DOUBLE PRECISION NOT NULL DEFAULT 350.0,
    volatility DOUBLE PRECISION NOT NULL DEFAULT 0.06,
    peak_rating DOUBLE PRECISION,
    games_in_period INTEGER NOT NULL DEFAULT 0,
    -- Series count drives the "use 2v2 elo vs fall back to 1v1" gate in the
    -- team balancer (>= 10 completed series → trust the 2v2 rating).
    completed_series INTEGER NOT NULL DEFAULT 0,
    last_calculated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Queue (4-row threshold to lock a match) ─────────────────────
CREATE TABLE IF NOT EXISTS team_queue (
    player_id UUID PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
    steam_id VARCHAR(20) NOT NULL,
    display_name VARCHAR(64) NOT NULL,
    -- Snapshot at queue-join (so Elo windows don't drift mid-search).
    rating DOUBLE PRECISION NOT NULL DEFAULT 1500.0,
    rating_deviation DOUBLE PRECISION NOT NULL DEFAULT 350.0,
    -- 2v2-specific completion count for the "fallback to 1v1 elo" rule.
    completed_series INTEGER NOT NULL DEFAULT 0,
    -- 1v1 rating, used by the balancer when the player has < 10 completed 2v2 series.
    fallback_rating DOUBLE PRECISION NOT NULL DEFAULT 1500.0,
    region VARCHAR(8),
    status VARCHAR(16) NOT NULL DEFAULT 'searching',
    -- Filled at lock time. NULL while still searching.
    series_id UUID,
    -- Team assignment (1 or 2) computed by the min-|Δ| balancer at lock time.
    team_assigned SMALLINT,
    room_name VARCHAR(64),
    room_region VARCHAR(8),
    ready BOOLEAN NOT NULL DEFAULT FALSE,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    matched_at TIMESTAMPTZ,
    last_polled TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_team_queue_status ON team_queue (status, joined_at);
CREATE INDEX IF NOT EXISTS idx_team_queue_series ON team_queue (series_id) WHERE series_id IS NOT NULL;

-- ── Series (BO3 of team_matches) ───────────────────────────────
CREATE TABLE IF NOT EXISTS team_series (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Team 1 = (t1a, t1b); Team 2 = (t2a, t2b). Slot order is balancer-assigned;
    -- an auto-rebalance after the first BO3 may rewrite these for series #2 etc.
    t1a_id UUID NOT NULL REFERENCES players(id),
    t1b_id UUID NOT NULL REFERENCES players(id),
    t2a_id UUID NOT NULL REFERENCES players(id),
    t2b_id UUID NOT NULL REFERENCES players(id),
    t1_series_wins SMALLINT NOT NULL DEFAULT 0,
    t2_series_wins SMALLINT NOT NULL DEFAULT 0,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    winner_team SMALLINT, -- 1 or 2
    -- Per-player Elo deltas. Storage order matches the t1a/t1b/t2a/t2b columns.
    t1a_rating_change DOUBLE PRECISION,
    t1b_rating_change DOUBLE PRECISION,
    t2a_rating_change DOUBLE PRECISION,
    t2b_rating_change DOUBLE PRECISION,
    photon_room_id VARCHAR(64),
    region VARCHAR(8),
    -- Auto-balance trigger: set by /team/rebalance after a sweep series.
    rebalance_count SMALLINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    invalidated_at TIMESTAMPTZ,
    invalidation_reason VARCHAR(64)
);
CREATE INDEX IF NOT EXISTS idx_team_series_status ON team_series (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_team_series_t1a ON team_series (t1a_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_team_series_t1b ON team_series (t1b_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_team_series_t2a ON team_series (t2a_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_team_series_t2b ON team_series (t2b_id, created_at DESC);

-- ── Match (one BO5/BO11 game inside a BO3 series) ──────────────
CREATE TABLE IF NOT EXISTS team_matches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    series_id UUID REFERENCES team_series(id) ON DELETE SET NULL,
    t1a_id UUID NOT NULL REFERENCES players(id),
    t1b_id UUID NOT NULL REFERENCES players(id),
    t2a_id UUID NOT NULL REFERENCES players(id),
    t2b_id UUID NOT NULL REFERENCES players(id),
    t1_rounds_won SMALLINT NOT NULL,
    t2_rounds_won SMALLINT NOT NULL,
    t1_points_total SMALLINT NOT NULL DEFAULT 0,
    t2_points_total SMALLINT NOT NULL DEFAULT 0,
    winner_team SMALLINT NOT NULL, -- 1 or 2
    -- Per-player FPS averages (display only).
    t1a_fps_avg SMALLINT,
    t1b_fps_avg SMALLINT,
    t2a_fps_avg SMALLINT,
    t2b_fps_avg SMALLINT,
    duration_seconds INTEGER,
    photon_room_id VARCHAR(64),
    game_version VARCHAR(32),
    region VARCHAR(8),
    hmac_signature VARCHAR(128),
    reported_by UUID REFERENCES players(id),
    is_ranked BOOLEAN NOT NULL DEFAULT TRUE,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    invalidated_at TIMESTAMPTZ,
    invalidation_reason VARCHAR(64),
    UNIQUE (photon_room_id, t1a_id, t1b_id, t2a_id, t2b_id)
);
CREATE INDEX IF NOT EXISTS idx_team_matches_series ON team_matches (series_id, ended_at DESC);
CREATE INDEX IF NOT EXISTS idx_team_matches_ended ON team_matches (ended_at DESC);
CREATE INDEX IF NOT EXISTS idx_team_matches_t1a ON team_matches (t1a_id, ended_at DESC);
CREATE INDEX IF NOT EXISTS idx_team_matches_t1b ON team_matches (t1b_id, ended_at DESC);
CREATE INDEX IF NOT EXISTS idx_team_matches_t2a ON team_matches (t2a_id, ended_at DESC);
CREATE INDEX IF NOT EXISTS idx_team_matches_t2b ON team_matches (t2b_id, ended_at DESC);

-- ── Card picks per (match_id, player_id) ───────────────────────
CREATE TABLE IF NOT EXISTS team_match_cards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    match_id UUID NOT NULL REFERENCES team_matches(id) ON DELETE CASCADE,
    player_id UUID NOT NULL REFERENCES players(id),
    card_name VARCHAR(64) NOT NULL,
    card_rarity VARCHAR(16),
    pick_order SMALLINT NOT NULL,
    round_number SMALLINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_team_match_cards_match ON team_match_cards (match_id);
CREATE INDEX IF NOT EXISTS idx_team_match_cards_player ON team_match_cards (player_id);
