-- 140_ping_timelines.sql  (July 22)
--
-- Item 3: per-side latency timelines for the history "Ping:" tag + hover
-- chart (own = 3s GetPing samples; opponent's via cr_gstats field 12).
--
-- MUST be applied BEFORE the API deploy that ships the matching Match ORM
-- columns — code-before-migration 500s every match submit (same rule as 136).
-- Additive-safe; idempotent.

ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_ping_timeline VARCHAR(512);
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_ping_timeline VARCHAR(512);
