-- 111_per_game_stats.sql  (v1.30, Sid item 4)
--
-- Per-game combat stats for BOTH players + the scoring timeline, on matches.
-- The reporter's side comes from their own counters; the opponent's side from
-- the cr_gstats Photon prop each client publishes every ~3s during a match.
-- Mapped to p1/p2 at submit time (same pattern as p1_fps_avg/p2_fps_avg).
-- All NULL on rows predating this migration — the client omits the stats line
-- for those rows instead of rendering fake zeros.

ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_bullets_fired INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_bullets_hit INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_blocks_activated INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_blocks_successful INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_keys_pressed INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_active_seconds DOUBLE PRECISION;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_bullets_fired INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_bullets_hit INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_blocks_activated INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_blocks_successful INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_keys_pressed INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_active_seconds DOUBLE PRECISION;

-- Cumulative scoring timeline "p1Total:p2Total,..." (total = rounds*2 + points),
-- capped at 64 events client-side. Drives the score-hover line graph.
ALTER TABLE matches ADD COLUMN IF NOT EXISTS point_timeline VARCHAR(512);
