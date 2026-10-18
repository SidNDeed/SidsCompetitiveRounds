-- rollback_387_ffa_rating_restore_2f60481d.sql
-- Reverses migration 387 (the rating restore of one FFA seat under the
-- 2026-10-18 early-leave ruling). Run ONLY to undo 387; data only.
--
-- LITERALS: the measured pre-image, read on the primary through the
-- read-only wrapper at 06:43Z and re-read at 07:22Z 2026-10-18 (identical
-- text both times):
--   glicko_ratings_ffa.rating        2024.405412230633
--   glicko_ratings_ffa.updated_at    2026-10-18 04:59:48.803927+00
--   match row rating_after           2024.3941582715768
--   match row rating_change          -62.7
-- Every value is written as that literal, never computed by subtraction.
-- peak_rating is not written: 387 refuses unless the peak is the measured
-- 2087.094158271577, so its GREATEST cannot have moved it, and this file
-- refuses unless the peak still reads that value.
--
-- REFUSALS (RAISE EXCEPTION before any write): target rows missing; seat
-- in ffa_queue (retry when not queued); a later rated FFA row exists; the
-- rows are not in 387's canonical post-image (match row rating_change 0
-- and rating_after = rating_before; rating = rating_before exactly; peak
-- at the measured value).
-- IDEMPOTENT: if both rows already read the measured pre-image exactly,
-- the file writes nothing and prints a NOTICE.

BEGIN;

SELECT pg_advisory_xact_lock(hashtext(CAST(p.steam_id AS text)))
  FROM players p
 WHERE p.id = 'fbb3d29d-b637-43c0-9787-357c2753e28c';
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
       fmp.rating_after,
       fmp.rating_change,
       g.rating      AS rating_now,
       g.peak_rating AS peak_now,
       g.updated_at  AS stamp_now,
       EXISTS (SELECT 1
                 FROM ffa_match_players f2
                 JOIN ffa_matches m2 ON m2.id = f2.match_id
                WHERE f2.player_id = fmp.player_id
                  AND f2.match_id <> fmp.match_id
                  AND f2.rating_change IS NOT NULL
                  AND m2.ended_at > m.ended_at)               AS later_rated,
       EXISTS (SELECT 1 FROM ffa_queue q
                WHERE q.player_id = fmp.player_id)            AS queued,
       EXISTS (SELECT 1 FROM players p
                WHERE p.id = fmp.player_id)                   AS identity_locked,
       FALSE                                                  AS apply
  FROM ffa_match_players fmp
  JOIN ffa_matches m        ON m.id = fmp.match_id
  JOIN glicko_ratings_ffa g ON g.player_id = fmp.player_id
 WHERE fmp.match_id  = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
   AND fmp.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c';

DO $$
DECLARE
    n integer;
    r record;
    pre_rating CONSTANT double precision := CAST(2024.405412230633 AS double precision);
    pre_after  CONSTANT double precision := CAST(2024.3941582715768 AS double precision);
    pre_change CONSTANT double precision := CAST(-62.7 AS double precision);
    pre_peak   CONSTANT double precision := CAST(2087.094158271577 AS double precision);
    pre_stamp  CONSTANT timestamptz      := TIMESTAMPTZ '2026-10-18 04:59:48.803927+00';
BEGIN
    SELECT COUNT(*) INTO n FROM _ffa_rollback_387;
    IF n <> 1 THEN
        RAISE EXCEPTION 'rollback 387: expected 1 joined row, found %', n;
    END IF;
    SELECT * INTO r FROM _ffa_rollback_387;

    IF r.rating_now = pre_rating AND r.stamp_now = pre_stamp
       AND r.rating_after = pre_after AND r.rating_change = pre_change THEN
        RAISE NOTICE 'rollback 387: rows already read the measured pre-image -- no-op';
        RETURN;
    END IF;

    IF NOT r.identity_locked THEN
        RAISE EXCEPTION 'rollback 387: players row missing, identity lock not taken';
    END IF;
    IF r.queued THEN
        RAISE EXCEPTION 'rollback 387: the seat has an ffa_queue row; retry when the seat is not queued';
    END IF;
    IF r.later_rated THEN
        RAISE EXCEPTION 'rollback 387: a later rated FFA row exists; the pre-image literal no longer applies';
    END IF;
    IF NOT (r.rating_change = 0 AND r.rating_after = r.rating_before) THEN
        RAISE EXCEPTION 'rollback 387: match row is not in 387 post-image (change %, after %)',
            r.rating_change, r.rating_after;
    END IF;
    IF r.rating_now <> r.rating_before THEN
        RAISE EXCEPTION 'rollback 387: rating % is not the 387 post-image %', r.rating_now, r.rating_before;
    END IF;
    IF r.peak_now <> pre_peak THEN
        RAISE EXCEPTION 'rollback 387: peak % is not the measured %', r.peak_now, pre_peak;
    END IF;

    RAISE NOTICE 'rollback 387: rating % -> %, updated_at % -> %',
        r.rating_now, pre_rating, r.stamp_now, pre_stamp;
    UPDATE _ffa_rollback_387 SET apply = TRUE;
END $$;

UPDATE glicko_ratings_ffa g
   SET rating     = CAST(2024.405412230633 AS double precision),
       updated_at = TIMESTAMPTZ '2026-10-18 04:59:48.803927+00'
  FROM _ffa_rollback_387 f
 WHERE f.apply
   AND g.player_id = f.player_id
   AND g.rating    = f.rating_before;

UPDATE ffa_match_players fmp
   SET rating_after  = CAST(2024.3941582715768 AS double precision),
       rating_change = CAST(-62.7 AS double precision)
  FROM _ffa_rollback_387 f
 WHERE f.apply
   AND fmp.match_id  = f.match_id
   AND fmp.player_id = f.player_id
   AND fmp.rating_change = 0;

SELECT g.rating, g.peak_rating, g.updated_at
  FROM glicko_ratings_ffa g
 WHERE g.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c';

SELECT fmp.rating_before, fmp.rating_after, fmp.rating_change
  FROM ffa_match_players fmp
 WHERE fmp.match_id  = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
   AND fmp.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c';

COMMIT;
