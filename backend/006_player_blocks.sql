-- ============================================================
-- Competitive ROUNDS — Player Blocks Migration
-- ============================================================
-- Run manually:
--   docker compose exec db psql -U comp_rounds -d competitive_rounds -c "CREATE TABLE IF NOT EXISTS player_blocks (blocker_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE, blocked_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY (blocker_id, blocked_id));"
-- ============================================================

CREATE TABLE IF NOT EXISTS player_blocks (
    blocker_id  UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    blocked_id  UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (blocker_id, blocked_id)
);
