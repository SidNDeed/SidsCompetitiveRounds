-- 154_ffa_schema.sql — FFA (free-for-all, 3-10 players) mode schema.
-- RANKED from day one: pairwise Glicko-2 applied inline per match (an FFA
-- match is a complete unit — there is no series/BO3 layer; the "lobby" row
-- groups rematches in the same room for the queue lifecycle only).
--
-- Deploy order: apply this migration BEFORE deploying the API build that
-- serves the /api/v1/ffa/* endpoints (they reference every table below).
--
-- Conventions carried over (hard-won):
--   * ffa_queue.series_id column name is REQUIRED by the shared group-lock
--     helper (_lock_queue_group_for_player selects `series_id` by name); it
--     holds an ffa_lobbies.id.
--   * Cancel status spelling is 'canceled' (one L) — the ovt convention
--     (migration 145). Do not introduce 'cancelled' here.
--   * photon_room_id on ffa_matches is NOT NULL + UNIQUE: it is the replay
--     guard, and a nullable dedup column is no dedup at all (learning #147).
--     Room ids are per-game suffixed client-side ({room}_{token}_r{N}).

-- ── Lobby: the queue-lock grouping entity (rematches share one lobby) ──────
CREATE TABLE IF NOT EXISTS ffa_lobbies (
    id                  UUID PRIMARY KEY,
    status              VARCHAR(16) NOT NULL DEFAULT 'active',  -- active|completed|canceled
    photon_room_id      VARCHAR(64),
    region              VARCHAR(8),
    player_count        SMALLINT NOT NULL DEFAULT 0,
    member_ids          UUID[] NOT NULL DEFAULT '{}',  -- lock-time roster; report validation
                                                       -- (queue rows get pruned, this doesn't)
    games_played        INTEGER  NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    invalidated_at      TIMESTAMPTZ,
    invalidation_reason VARCHAR(64)
);
CREATE INDEX IF NOT EXISTS idx_ffa_lobbies_status ON ffa_lobbies (status, created_at DESC);

-- ── Queue (consent-at-join: no Elo band, no ready step — learning #127) ────
CREATE TABLE IF NOT EXISTS ffa_queue (
    player_id        UUID PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
    steam_id         VARCHAR(32) NOT NULL,
    display_name     VARCHAR(64),
    rating           DOUBLE PRECISION NOT NULL DEFAULT 1500,
    rating_deviation DOUBLE PRECISION NOT NULL DEFAULT 350,
    games_played     INTEGER NOT NULL DEFAULT 0,
    fallback_rating  DOUBLE PRECISION NOT NULL DEFAULT 1500,   -- 1v1 elo display hint
    region           VARCHAR(8),
    status           VARCHAR(16) NOT NULL DEFAULT 'searching', -- searching|ready_join
    series_id        UUID,          -- ffa_lobbies.id (name is the lock-helper contract)
    slot             SMALLINT,      -- 0..N-1, steam-ordinal order at lock time
    room_name        VARCHAR(64),
    room_region      VARCHAR(8),
    joined_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    matched_at       TIMESTAMPTZ,
    last_polled      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ffa_queue_status ON ffa_queue (status, joined_at);
CREATE INDEX IF NOT EXISTS idx_ffa_queue_lobby  ON ffa_queue (series_id) WHERE series_id IS NOT NULL;

-- ── Ratings (live from day one, unlike the 1v2 count-only table) ───────────
CREATE TABLE IF NOT EXISTS glicko_ratings_ffa (
    player_id        UUID PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
    rating           DOUBLE PRECISION NOT NULL DEFAULT 1500,
    rating_deviation DOUBLE PRECISION NOT NULL DEFAULT 350,
    volatility       DOUBLE PRECISION NOT NULL DEFAULT 0.06,
    peak_rating      DOUBLE PRECISION NOT NULL DEFAULT 1500,
    games_played     INTEGER NOT NULL DEFAULT 0,
    wins             INTEGER NOT NULL DEFAULT 0,   -- 1st places
    top3             INTEGER NOT NULL DEFAULT 0,   -- placements 1-3
    placement_sum    INTEGER NOT NULL DEFAULT 0,   -- avg placement = sum/games
    last_calculated  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Matches (one row per game; participants in the child table) ────────────
CREATE TABLE IF NOT EXISTS ffa_matches (
    id                  UUID PRIMARY KEY,
    lobby_id            UUID REFERENCES ffa_lobbies(id) ON DELETE SET NULL,
    photon_room_id      VARCHAR(64) NOT NULL,
    player_count        SMALLINT NOT NULL,
    winner_id           UUID REFERENCES players(id) ON DELETE SET NULL,
    duration_seconds    INTEGER,
    game_version        VARCHAR(32),
    region              VARCHAR(8),
    hmac_signature      VARCHAR(160),
    reported_by         UUID REFERENCES players(id) ON DELETE SET NULL,
    is_ranked           BOOLEAN NOT NULL DEFAULT TRUE,
    started_at          TIMESTAMPTZ,
    ended_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    invalidated_at      TIMESTAMPTZ,
    invalidation_reason VARCHAR(64),
    CONSTRAINT uq_ffa_match_room UNIQUE (photon_room_id)
);
CREATE INDEX IF NOT EXISTS idx_ffa_matches_lobby   ON ffa_matches (lobby_id);
CREATE INDEX IF NOT EXISTS idx_ffa_matches_created ON ffa_matches (created_at DESC);

-- ── Per-player match rows (full 1v1/2v2 stat parity — TeamPlayerTelemetry) ─
CREATE TABLE IF NOT EXISTS ffa_match_players (
    match_id          UUID NOT NULL REFERENCES ffa_matches(id) ON DELETE CASCADE,
    player_id         UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    slot              SMALLINT,
    rounds_won        SMALLINT NOT NULL DEFAULT 0,
    points_total      SMALLINT NOT NULL DEFAULT 0,
    placement         SMALLINT NOT NULL,           -- 1 = winner; ties share (dense)
    left_early        BOOLEAN NOT NULL DEFAULT FALSE,
    rating_before     DOUBLE PRECISION,
    rating_after      DOUBLE PRECISION,
    rating_change     DOUBLE PRECISION,
    xp_gained         INTEGER NOT NULL DEFAULT 0,
    gold_gained       INTEGER NOT NULL DEFAULT 0,
    fps_avg           SMALLINT,
    ping_avg          SMALLINT,
    bullets_fired     INTEGER,
    bullets_hit       INTEGER,
    blocks_activated  INTEGER,
    blocks_successful INTEGER,
    keys_pressed      INTEGER,
    active_seconds    REAL,
    fps_timeline      VARCHAR(512),
    ping_timeline     VARCHAR(512),
    hit_timeline      VARCHAR(1024),
    block_timeline    VARCHAR(1024),
    PRIMARY KEY (match_id, player_id)
);
CREATE INDEX IF NOT EXISTS idx_ffa_match_players_player ON ffa_match_players (player_id, match_id);

-- ── Cards (rarity + round included — the 1v2 table's omission was a gap) ───
CREATE TABLE IF NOT EXISTS ffa_match_cards (
    id           BIGSERIAL PRIMARY KEY,
    match_id     UUID NOT NULL REFERENCES ffa_matches(id) ON DELETE CASCADE,
    player_id    UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    card_name    VARCHAR(64) NOT NULL,
    card_rarity  VARCHAR(16),
    pick_order   SMALLINT NOT NULL DEFAULT 0,
    round_number SMALLINT
);
CREATE INDEX IF NOT EXISTS idx_ffa_match_cards_match ON ffa_match_cards (match_id);

-- ── Per-mode economy slice on players (learning #69 pattern) ───────────────
ALTER TABLE players ADD COLUMN IF NOT EXISTS ffa_gold_earned INTEGER NOT NULL DEFAULT 0;
ALTER TABLE players ADD COLUMN IF NOT EXISTS ffa_xp_earned   INTEGER NOT NULL DEFAULT 0;
