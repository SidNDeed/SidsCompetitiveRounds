-- 136_fps_lag_telemetry.sql — July 21 (advisory anti-cheat)
--
-- ============================================================================
-- !! DEPLOY ORDER: this migration MUST be applied BEFORE the API deploy that
-- !! ships the new Match ORM columns — the ORM passes every column below
-- !! explicitly on every INSERT (and the history query SELECTs the
-- !! timelines), so code-before-migration 500s EVERY match submit and
-- !! /players/{id}/matches for ALL clients (UndefinedColumn). ADD COLUMN IF
-- !! NOT EXISTS is harmless under the currently-running old code, so
-- !! migrations-first is strictly safe: /migrate 136 first, THEN
-- !! /deploy-backend, then a POST smoke test on /api/v1/matches.
-- ============================================================================
--
-- Per-match FPS/lag telemetry, BOTH sides (mirrors 111_per_game_stats.sql).
-- Reporter side comes from their own counters; opponent side from the
-- extended cr_gstats Photon prop. Asymmetries: ping + freeze_total_sec exist
-- only for the reporter side (NULL on the other); hb_gap counts are the
-- OTHER seat's observation of this side's heartbeat gaps. All NULL on rows
-- predating this migration and on old-client reports — the flag heuristics
-- and the history hover graph skip NULLs.

ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_fps_timeline VARCHAR(512);
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_fps_timeline VARCHAR(512);
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_freeze_count SMALLINT;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_freeze_count SMALLINT;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_freeze_focused_count SMALLINT;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_freeze_focused_count SMALLINT;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_freeze_total_sec REAL;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_freeze_total_sec REAL;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_recv_gap_count SMALLINT;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_recv_gap_count SMALLINT;
-- Longest single socket-silence gap in ms (reporter side only). INTEGER, not
-- SMALLINT — a 45s NIC cut is 45000 ms, over SMALLINT's 32767 max.
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_recv_gap_max_ms INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_recv_gap_max_ms INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_hb_gap_count SMALLINT;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_hb_gap_count SMALLINT;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_ping_avg SMALLINT;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_ping_avg SMALLINT;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_ping_max SMALLINT;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_ping_max SMALLINT;

-- Analysis-era filter: the reporter client's X-Mod-Version at submit time.
-- Cannot be backfilled — required to slice per-match hit/block stats by
-- counting-semantics era after the July 21 fix (see migration 135).
ALTER TABLE matches ADD COLUMN IF NOT EXISTS reporter_mod_version VARCHAR(16);
