-- ============================================================
-- Competitive ROUNDS — Queue Blocks Migration
-- ============================================================
-- Run manually:
--   docker compose exec db psql -U comp_rounds -d competitive_rounds -f /docker-entrypoint-initdb.d/004_queue_blocks.sql
-- ============================================================

-- ── Queue Blocks ────────────────────────────────────────────
-- Tracks declined opponents. Players cannot be re-matched with
-- a declined opponent until the block expires (5 minutes).
CREATE TABLE IF NOT EXISTS queue_blocks (
    blocker_id      UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    blocked_id      UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    expires_at      TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (blocker_id, blocked_id)
);

CREATE INDEX IF NOT EXISTS idx_queue_blocks_expires ON queue_blocks (expires_at);
