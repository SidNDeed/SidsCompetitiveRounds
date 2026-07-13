-- 120_1v2_schema.sql
-- 1v2 mode foundation (1 solo vs a duo). Parallel to the 1v1 and 2v2 paths —
-- separate queue/series/match tables — so neither existing mode is touched.
--
-- Launch is UNSCORED (Sid, July 13 answer #2): no ratings applied yet, but the
-- match tables record the FULL replay surface (per-slot rounds/points/cards/fps,
-- cached ratings at time, timestamps) so a retroactive Glicko replay can turn
-- ranked on later with zero data loss — same recovery pattern as learning #76.
-- The rating table + cached_* columns exist now so that replay has somewhere to
-- write and the queue can snapshot ratings from day one.
--
-- Scoring maps to the existing two-team client model: solo = team 1, duo =
-- team 2. So GM_ArmsRace's p1/p2 rounds carry straight through; only the
-- SERVER stores three player slots (solo, duo_a, duo_b).
--
-- Report HMAC canonical (10 fields, ':' separated), NEW format — the 1v1
-- 7-field and 2v2 11-field formats are untouched (hard rule #5):
--   solo:duo_a:duo_b:solo_rounds:duo_rounds:is_ranked:reporter:room_id:winner_side:series_id

-- ── Per-player 1v2 Glicko-2 rating (unused until ranked launches) ──
CREATE TABLE IF NOT EXISTS glicko_ratings_1v2 (
    player_id UUID PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
    -- Solo and duo performances rate into ONE 1v2 pool at launch; if asymmetric
    -- rating proves necessary later, split into _solo/_duo columns then (the
    -- match rows record which side each player was on, so a split replay works).
    rating DOUBLE PRECISION NOT NULL DEFAULT 1500.0,
    rating_deviation DOUBLE PRECISION NOT NULL DEFAULT 350.0,
    volatility DOUBLE PRECISION NOT NULL DEFAULT 0.06,
    peak_rating DOUBLE PRECISION,
    games_in_period INTEGER NOT NULL DEFAULT 0,
    completed_series INTEGER NOT NULL DEFAULT 0,
    -- Split game counts for later asymmetric analysis / leaderboard columns.
    solo_games INTEGER NOT NULL DEFAULT 0,
    duo_games INTEGER NOT NULL DEFAULT 0,
    last_calculated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Queue (manual/consent lobby; 3-row threshold to lock) ─────────
-- 'manual' queue type only at launch: joining the lobby IS consent, so it
-- SKIPS the Elo band entirely (learning #127) — friends of mixed rating lock
-- immediately. preferred_side lets a player ask for solo vs duo; the lock
-- resolves 1 solo + 2 duo from preferences, else fills by join order.
CREATE TABLE IF NOT EXISTS ovt_queue (
    player_id UUID PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
    steam_id VARCHAR(20) NOT NULL,
    display_name VARCHAR(64) NOT NULL,
    rating DOUBLE PRECISION NOT NULL DEFAULT 1500.0,
    rating_deviation DOUBLE PRECISION NOT NULL DEFAULT 350.0,
    completed_series INTEGER NOT NULL DEFAULT 0,
    fallback_rating DOUBLE PRECISION NOT NULL DEFAULT 1500.0,
    region VARCHAR(8),
    queue_type VARCHAR(16) NOT NULL DEFAULT 'manual',
    -- 0 = no preference, 1 = wants solo, 2 = wants duo.
    preferred_side SMALLINT NOT NULL DEFAULT 0,
    status VARCHAR(16) NOT NULL DEFAULT 'searching',
    series_id UUID,
    -- 1 = solo side, 2 = duo side (assigned at lock).
    side_assigned SMALLINT,
    -- Solo extra INITIAL card pick toggle (Sid #1). Any lobby member may set it;
    -- lock takes the OR across the lobby and stamps it on the series.
    solo_extra_pick BOOLEAN NOT NULL DEFAULT FALSE,
    room_name VARCHAR(64),
    room_region VARCHAR(8),
    ready BOOLEAN NOT NULL DEFAULT FALSE,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    matched_at TIMESTAMPTZ,
    last_polled TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ovt_queue_status ON ovt_queue (status, joined_at);
CREATE INDEX IF NOT EXISTS idx_ovt_queue_series ON ovt_queue (series_id) WHERE series_id IS NOT NULL;

-- ── Series (BO3; solo vs duo) ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS ovt_series (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    solo_id  UUID NOT NULL REFERENCES players(id),
    duo_a_id UUID NOT NULL REFERENCES players(id),
    duo_b_id UUID NOT NULL REFERENCES players(id),
    solo_series_wins SMALLINT NOT NULL DEFAULT 0,
    duo_series_wins  SMALLINT NOT NULL DEFAULT 0,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    winner_side SMALLINT,                    -- 1 = solo, 2 = duo
    -- Per-player Elo deltas (written only once ranked launches; NULL meanwhile).
    solo_rating_change  DOUBLE PRECISION,
    duo_a_rating_change DOUBLE PRECISION,
    duo_b_rating_change DOUBLE PRECISION,
    is_ranked BOOLEAN NOT NULL DEFAULT FALSE,  -- FALSE at launch (unscored)
    solo_extra_pick BOOLEAN NOT NULL DEFAULT FALSE,
    photon_room_id VARCHAR(64),
    region VARCHAR(8),
    -- DC handling (mirrors team_series).
    dc_grace_until TIMESTAMPTZ,
    dc_side_remaining SMALLINT,
    dc_player_id UUID REFERENCES players(id),
    -- Economy accumulators (per slot) so the F5 panel can show +g/+xp per player.
    solo_gold_earned  INTEGER NOT NULL DEFAULT 0,
    duo_a_gold_earned INTEGER NOT NULL DEFAULT 0,
    duo_b_gold_earned INTEGER NOT NULL DEFAULT 0,
    solo_xp_earned  INTEGER NOT NULL DEFAULT 0,
    duo_a_xp_earned INTEGER NOT NULL DEFAULT 0,
    duo_b_xp_earned INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    invalidated_at TIMESTAMPTZ,
    invalidation_reason VARCHAR(64),
    spawn_confirmations SMALLINT NOT NULL DEFAULT 0,
    spawn_confirmed_by JSONB NOT NULL DEFAULT '[]'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_ovt_series_status ON ovt_series (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ovt_series_solo  ON ovt_series (solo_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ovt_series_duo_a ON ovt_series (duo_a_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ovt_series_duo_b ON ovt_series (duo_b_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ovt_series_dc_grace ON ovt_series (dc_grace_until) WHERE dc_grace_until IS NOT NULL;

-- ── Matches (individual games within a series) ────────────────────
CREATE TABLE IF NOT EXISTS ovt_matches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    series_id UUID REFERENCES ovt_series(id) ON DELETE SET NULL,
    solo_id  UUID NOT NULL REFERENCES players(id),
    duo_a_id UUID NOT NULL REFERENCES players(id),
    duo_b_id UUID NOT NULL REFERENCES players(id),
    solo_rounds_won SMALLINT NOT NULL,
    duo_rounds_won  SMALLINT NOT NULL,
    solo_points_total SMALLINT NOT NULL DEFAULT 0,
    duo_points_total  SMALLINT NOT NULL DEFAULT 0,
    winner_side SMALLINT NOT NULL,             -- 1 solo, 2 duo
    -- Cached ratings at report time (the retroactive-ranked replay reads these).
    solo_rating_at  DOUBLE PRECISION,
    duo_a_rating_at DOUBLE PRECISION,
    duo_b_rating_at DOUBLE PRECISION,
    solo_fps_avg  SMALLINT,
    duo_a_fps_avg SMALLINT,
    duo_b_fps_avg SMALLINT,
    duration_seconds INTEGER,
    photon_room_id VARCHAR(64),
    game_version VARCHAR(32),
    region VARCHAR(8),
    hmac_signature VARCHAR(128),
    reported_by UUID REFERENCES players(id),
    is_ranked BOOLEAN NOT NULL DEFAULT FALSE,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    invalidated_at TIMESTAMPTZ,
    invalidation_reason VARCHAR(64),
    dc_player_id UUID REFERENCES players(id),
    dc_at TIMESTAMPTZ,
    -- Dedup guard: one game per (room, three players) — room ids are per-game
    -- suffixed on the client, so a replay of an already-recorded game no-ops.
    UNIQUE (photon_room_id, solo_id, duo_a_id, duo_b_id)
);
CREATE INDEX IF NOT EXISTS idx_ovt_matches_series ON ovt_matches (series_id, ended_at DESC);
CREATE INDEX IF NOT EXISTS idx_ovt_matches_ended  ON ovt_matches (ended_at DESC);
CREATE INDEX IF NOT EXISTS idx_ovt_matches_solo   ON ovt_matches (solo_id, ended_at DESC);
CREATE INDEX IF NOT EXISTS idx_ovt_matches_duo_a  ON ovt_matches (duo_a_id, ended_at DESC);
CREATE INDEX IF NOT EXISTS idx_ovt_matches_duo_b  ON ovt_matches (duo_b_id, ended_at DESC);

-- ── Per-game card picks (replay surface) ──────────────────────────
CREATE TABLE IF NOT EXISTS ovt_match_cards (
    id BIGSERIAL PRIMARY KEY,
    match_id UUID NOT NULL REFERENCES ovt_matches(id) ON DELETE CASCADE,
    player_id UUID NOT NULL REFERENCES players(id),
    card_name VARCHAR(64) NOT NULL,
    pick_order SMALLINT NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_ovt_match_cards_match ON ovt_match_cards (match_id);
