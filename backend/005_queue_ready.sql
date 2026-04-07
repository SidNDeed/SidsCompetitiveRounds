-- ============================================================
-- Competitive ROUNDS — Queue Ready-Up Migration
-- ============================================================
-- Run manually:
--   docker compose exec db psql -U comp_rounds -d competitive_rounds -f /docker-entrypoint-initdb.d/005_queue_ready.sql
-- ============================================================

ALTER TABLE ranked_queue ADD COLUMN IF NOT EXISTS ready BOOLEAN NOT NULL DEFAULT false;
