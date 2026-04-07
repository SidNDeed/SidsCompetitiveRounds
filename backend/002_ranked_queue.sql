-- ============================================================
-- Competitive ROUNDS — Ranked Queue Migration
-- ============================================================
-- Run manually:
--   docker compose exec db psql -U comp_rounds -d competitive_rounds -f /docker-entrypoint-initdb.d/002_ranked_queue.sql
-- ============================================================

-- ── Ranked Queue ────────────────────────────────────────────
-- One row per player currently in the matchmaking queue.
-- Rows are upserted on join, deleted on leave/match completion.
CREATE TABLE IF NOT EXISTS ranked_queue (
    player_id       UUID PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
    steam_id        VARCHAR(20) NOT NULL,
    display_name    VARCHAR(64) NOT NULL,
    rating          DOUBLE PRECISION NOT NULL DEFAULT 1500,
    rating_deviation DOUBLE PRECISION NOT NULL DEFAULT 350,
    region          VARCHAR(8),
    ranked_only     BOOLEAN NOT NULL DEFAULT false,
    status          VARCHAR(16) NOT NULL DEFAULT 'searching',   -- searching, matched, expired
    matched_with    UUID REFERENCES players(id),                -- opponent player_id when matched
    room_name       VARCHAR(64),                                -- Photon room name to join
    joined_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    matched_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_queue_status ON ranked_queue (status);
CREATE INDEX IF NOT EXISTS idx_queue_rating ON ranked_queue (rating);

-- Also fix the ranked_enabled default for new players (from server bug fix)
ALTER TABLE players ALTER COLUMN ranked_enabled SET DEFAULT false;
