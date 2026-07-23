-- 141_hit_block_timelines.sql — July 22 (My Stats Hit%/Block% hover graphs)
--
-- ============================================================================
-- !! DEPLOY ORDER: apply BEFORE the API deploy that ships the new Match ORM
-- !! columns — the ORM passes every column explicitly on every INSERT (and
-- !! the history query SELECTs these), so code-before-migration 500s EVERY
-- !! match submit (UndefinedColumn). ADD COLUMN IF NOT EXISTS is harmless
-- !! under the old code, so migrations-first is strictly safe:
-- !! /migrate 141 first, THEN /deploy-backend, then a POST smoke test.
-- ============================================================================
--
-- Cumulative in-game timelines sampled every ~3s by the client, both sides:
--   *_hit_timeline   = "fired:hit,fired:hit,..."      (shots placed vs landed)
--   *_block_timeline = "dmgTaken:blocksSucc,..."      (damage taken vs blocks)
-- point_times = "12,47,89" — seconds since match start, one entry per
-- point_timeline entry (who scored is derived by diffing point_timeline).
-- Reporter side from own counters; opponent side sniffed from the extended
-- cr_gstats Photon prop (13-field era). NULL on old rows / old-client peers.

ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_hit_timeline VARCHAR(1024);
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_hit_timeline VARCHAR(1024);
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_block_timeline VARCHAR(1024);
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_block_timeline VARCHAR(1024);
ALTER TABLE matches ADD COLUMN IF NOT EXISTS point_times VARCHAR(512);
