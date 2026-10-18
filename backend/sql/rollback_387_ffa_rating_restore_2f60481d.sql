-- rollback_387_ffa_rating_restore_2f60481d.sql
-- Reverses migration 387 (the rating-delta restore of one FFA seat under
-- the 2026-10-18 early-leave ruling). Run ONLY to undo 387; data only.
--
-- LITERALS, measured on the primary 2026-10-18 06:43Z and valid for 387's
-- EXACT branch (its NOTICE prints exact_branch=t delta=62.6887460409439):
--   delta applied by 387          62.6887460409439
--   match row rating_after        2024.3941582715768
--   match row rating_change       -62.7
-- If 387's landing output printed exact_branch=f or any other delta, this
-- file is WRONG as written: replace the delta literal with the printed one
-- before running. The DO block below refuses the common mismatch.
--
-- Peak: 387's GREATEST was a no-op on the measured pre-image (the peak
-- already equalled the restored rating), so the peak is not written here.
--
-- IDEMPOTENT: the selection requires the match row to still read
-- rating_change = 0 AND rating_after = rating_before (387's post-image);
-- step 3 puts the original values back, so a second run selects nothing.

BEGIN;

SELECT 1 FROM glicko_ratings_ffa
 WHERE player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
   FOR NO KEY UPDATE;
SELECT 1 FROM ffa_match_players
 WHERE match_id  = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
   AND player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
   FOR NO KEY UPDATE;

CREATE TEMP TABLE _ffa_rollback_387 ON COMMIT DROP AS
SELECT fmp.match_id,
       fmp.player_id,
       fmp.rating_before,
       g.rating AS rating_now,
       EXISTS (SELECT 1
                 FROM ffa_match_players f2
                 JOIN ffa_matches m2 ON m2.id = f2.match_id
                WHERE f2.player_id = fmp.player_id
                  AND f2.match_id <> fmp.match_id
                  AND f2.rating_change IS NOT NULL
                  AND m2.ended_at > m.ended_at) AS later_rated
  FROM ffa_match_players fmp
  JOIN ffa_matches m        ON m.id = fmp.match_id
  JOIN glicko_ratings_ffa g ON g.player_id = fmp.player_id
 WHERE fmp.match_id  = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
   AND fmp.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
   AND fmp.rating_change = 0
   AND fmp.rating_after = fmp.rating_before;

-- With no later rated game, 387's exact branch left the rating EXACTLY at
-- rating_before; anything else means the literal is not the applied delta.
DO $$
DECLARE
    n integer;
    r record;
BEGIN
    SELECT COUNT(*) INTO n FROM _ffa_rollback_387;
    IF n = 0 THEN
        RAISE NOTICE 'rollback 387: match row is not in 387 post-image -- no-op';
        RETURN;
    END IF;
    SELECT * INTO r FROM _ffa_rollback_387;
    IF NOT r.later_rated AND r.rating_now <> r.rating_before THEN
        RAISE EXCEPTION 'rollback 387: rating % is not the restored value %; the delta literal does not match what 387 applied',
            r.rating_now, r.rating_before;
    END IF;
    RAISE NOTICE 'rollback 387: later_rated=% rating % -> %',
        r.later_rated, r.rating_now, r.rating_now - 62.6887460409439;
END $$;

UPDATE glicko_ratings_ffa g
   SET rating     = g.rating - 62.6887460409439,
       updated_at = NOW()
  FROM _ffa_rollback_387 f
 WHERE g.player_id = f.player_id;

UPDATE ffa_match_players fmp
   SET rating_after  = 2024.3941582715768,
       rating_change = -62.7
  FROM _ffa_rollback_387 f
 WHERE fmp.match_id  = f.match_id
   AND fmp.player_id = f.player_id
   AND fmp.rating_change = 0;

SELECT g.rating, g.peak_rating
  FROM glicko_ratings_ffa g
 WHERE g.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c';

SELECT fmp.rating_before, fmp.rating_after, fmp.rating_change
  FROM ffa_match_players fmp
 WHERE fmp.match_id  = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
   AND fmp.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c';

COMMIT;
