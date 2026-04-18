-- ============================================================
-- Competitive ROUNDS — Room Region Migration
-- ============================================================
-- Run manually:
--   docker compose exec db psql -U comp_rounds -d competitive_rounds -f /docker-entrypoint-initdb.d/007_room_region.sql
-- ============================================================

ALTER TABLE ranked_queue ADD COLUMN IF NOT EXISTS room_region VARCHAR(8);
