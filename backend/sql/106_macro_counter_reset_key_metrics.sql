-- 106_macro_counter_reset_key_metrics.sql
--
-- Bug #50 (Compare tab KPS/KPG "not registering"): the client sampled Unity's
-- per-frame *Down input APIs from the 10 Hz poll, catching ~3% of key events —
-- a 294s game recorded 7.7 active seconds and 31 keys. v1.29.1 moves sampling
-- to a per-frame tick and restricts counted keys to gameplay inputs
-- (WASD/arrows/space/L+R click), plus a macro-suspicion counter.
--
-- 1) New advisory column for the macro counter.
-- 2) Zero the lifetime keys/active-seconds accumulators AND the per-match
--    input columns: every historical value was collected by the broken 10 Hz
--    sampler. Mixing them with per-frame data would poison the lifetime
--    averages (old data undercounts keys ~10-30x), and avg_keys_per_game
--    averages the per-match column directly. Clean slate on both.

BEGIN;

ALTER TABLE matches ADD COLUMN IF NOT EXISTS local_macro_suspect_seconds INTEGER;

UPDATE players SET keys_pressed_total = 0, active_seconds_total = 0
WHERE keys_pressed_total > 0 OR active_seconds_total > 0;

-- Per-match rows: NULL means "no data" to every consumer (avg_keys_per_game
-- filters local_keys_pressed > 0), which is exactly right for pre-fix rows.
UPDATE matches SET local_keys_pressed = NULL, local_active_seconds = NULL
WHERE local_keys_pressed IS NOT NULL OR local_active_seconds IS NOT NULL;

COMMIT;
