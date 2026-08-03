-- 182: normalize blank ban reasons (Codex wave-2 rounds 16-17).
--
-- The schema accepted reason='' / whitespace and the old endpoint persisted
-- them; truthiness-based existence checks then read such rows as "not
-- banned". The code now checks row EXISTENCE everywhere; this backfill makes
-- the display value honest. Whitespace coverage is the FULL POSIX class
-- (round-17 find 5: btrim's default strips spaces only — a reason of '\t'
-- survived it). Rerun-safe; the runbook re-runs it AFTER the new API is
-- live, so a blank written by the old writer inside the deploy window is
-- caught too.
UPDATE player_bans SET reason = 'violation'
 WHERE reason IS NULL OR reason !~ '[^[:space:]]';
DO $$ BEGIN RAISE NOTICE 'migration 182 OK: blank ban reasons normalized'; END $$;
