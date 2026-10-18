-- rollback_387_ffa_rating_restore_2f60481d.sql
-- Reverses migration 387 (the rating restore of one FFA seat under the
-- 2026-10-18 early-leave ruling). Run ONLY to undo 387; data only.
--
-- LITERALS: the measured pre-image, read on the primary through the
-- read-only wrapper at 06:43Z, 07:22Z and 08:00Z 2026-10-18 (identical
-- text every time):
--   glicko_ratings_ffa.rating        2024.405412230633
--   glicko_ratings_ffa.peak_rating   2087.094158271577
--   glicko_ratings_ffa.updated_at    2026-10-18 04:59:48.803927+00
--   match row rating_before          2087.094158271577
--   match row rating_after           2024.3941582715768
--   match row rating_change          -62.7
-- Every value written is one of those literals, never computed.
-- peak_rating is not written: 387 refuses unless the peak is the measured
-- value, its GREATEST therefore cannot move it, and this file refuses
-- unless the peak still reads that value.
--
-- EVERY DECISION IS TOTAL (IS TRUE / IS FALSE / IS NOT DISTINCT FROM; a NULL
-- in any operand refuses). The state must be EXACTLY 387's post-image
-- (apply) or EXACTLY the measured pre-image (no-op); anything else RAISEs.
-- Each UPDATE runs inside the DO block, re-asserts the pinned values in
-- its WHERE, and must touch exactly one row, or the transaction aborts.

BEGIN;

DO $$
DECLARE
    k            bigint;
    r            record;
    pre_rating   CONSTANT double precision := CAST(2024.405412230633  AS double precision);
    pre_peak     CONSTANT double precision := CAST(2087.094158271577  AS double precision);
    pre_stamp    CONSTANT timestamptz      := TIMESTAMPTZ '2026-10-18 04:59:48.803927+00';
    m_before     CONSTANT double precision := CAST(2087.094158271577  AS double precision);
    m_after      CONSTANT double precision := CAST(2024.3941582715768 AS double precision);
    m_change     CONSTANT double precision := CAST(-62.7              AS double precision);
    is_pre       boolean;
    is_post      boolean;
BEGIN
    -- Locks, in the global order identity -> rows: the identity key every
    -- FFA ENROLLMENT writer takes through its gate (main.py
    -- _enrollment_identity_gate 15763-15780, called from 50925-50993,
    -- 52881-52953, 52971-53012), resolved from the players row.
    PERFORM pg_advisory_xact_lock(hashtext(CAST(p.steam_id AS text)))
       FROM players p
      WHERE p.id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
        AND p.steam_id IS NOT NULL;
    GET DIAGNOSTICS k = ROW_COUNT;
    IF k IS DISTINCT FROM 1::bigint THEN
        RAISE EXCEPTION 'rollback 387: identity lock not taken (players rows %)', k;
    END IF;
    PERFORM 1 FROM glicko_ratings_ffa
      WHERE player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
        FOR NO KEY UPDATE;
    PERFORM 1 FROM ffa_match_players
      WHERE match_id  = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
        AND player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
        FOR NO KEY UPDATE;

    SELECT fmp.rating_before, fmp.rating_after, fmp.rating_change,
           g.rating AS rating_now, g.peak_rating AS peak_now, g.updated_at AS stamp_now,
           EXISTS (SELECT 1
                     FROM ffa_match_players f2
                     JOIN ffa_matches m2 ON m2.id = f2.match_id
                    WHERE f2.player_id = fmp.player_id
                      AND f2.match_id <> fmp.match_id
                      AND f2.rating_change IS NOT NULL
                      AND m2.ended_at > m.ended_at) AS later_rated,
           EXISTS (SELECT 1 FROM ffa_queue q
                    WHERE q.player_id = fmp.player_id) AS queued
      INTO STRICT r
      FROM ffa_match_players fmp
      JOIN ffa_matches m        ON m.id = fmp.match_id
      JOIN glicko_ratings_ffa g ON g.player_id = fmp.player_id
     WHERE fmp.match_id  = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
       AND fmp.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c';

    -- Guards common to apply AND no-op.
    IF r.queued IS NOT FALSE THEN
        RAISE EXCEPTION 'rollback 387: the seat has an ffa_queue row; retry when the seat is not queued';
    END IF;
    IF r.later_rated IS NOT FALSE THEN
        RAISE EXCEPTION 'rollback 387: a later rated FFA row exists; the pre-image literals no longer apply';
    END IF;
    IF r.rating_before IS DISTINCT FROM m_before THEN
        RAISE EXCEPTION 'rollback 387: match rating_before % is not the measured %', r.rating_before, m_before;
    END IF;
    IF r.peak_now IS DISTINCT FROM pre_peak THEN
        RAISE EXCEPTION 'rollback 387: peak % is not the measured %', r.peak_now, pre_peak;
    END IF;

    is_post := (r.rating_now    IS NOT DISTINCT FROM m_before)
           AND (r.rating_after  IS NOT DISTINCT FROM m_before)
           AND (r.rating_change IS NOT DISTINCT FROM CAST(0 AS double precision));
    is_pre  := (r.rating_now    IS NOT DISTINCT FROM pre_rating)
           AND (r.stamp_now     IS NOT DISTINCT FROM pre_stamp)
           AND (r.rating_after  IS NOT DISTINCT FROM m_after)
           AND (r.rating_change IS NOT DISTINCT FROM m_change);

    IF is_pre IS TRUE THEN
        RAISE NOTICE 'rollback 387: rows already read the measured pre-image -- no-op';
        RETURN;
    END IF;
    IF is_post IS NOT TRUE THEN
        RAISE EXCEPTION 'rollback 387: state is neither the 387 post-image nor the measured pre-image (rating %, after %, change %)',
            r.rating_now, r.rating_after, r.rating_change;
    END IF;

    RAISE NOTICE 'rollback 387: rating % -> %, updated_at % -> %',
        r.rating_now, pre_rating, r.stamp_now, pre_stamp;

    UPDATE glicko_ratings_ffa g
       SET rating     = pre_rating,
           updated_at = pre_stamp
     WHERE g.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
       AND g.rating      IS NOT DISTINCT FROM m_before
       AND g.peak_rating IS NOT DISTINCT FROM pre_peak;
    GET DIAGNOSTICS k = ROW_COUNT;
    IF k IS DISTINCT FROM 1::bigint THEN
        RAISE EXCEPTION 'rollback 387: rating row update touched % rows, expected 1', k;
    END IF;

    UPDATE ffa_match_players fmp
       SET rating_after  = m_after,
           rating_change = m_change
     WHERE fmp.match_id  = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
       AND fmp.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
       AND fmp.rating_before IS NOT DISTINCT FROM m_before
       AND fmp.rating_after  IS NOT DISTINCT FROM m_before
       AND fmp.rating_change IS NOT DISTINCT FROM CAST(0 AS double precision);
    GET DIAGNOSTICS k = ROW_COUNT;
    IF k IS DISTINCT FROM 1::bigint THEN
        RAISE EXCEPTION 'rollback 387: match row update touched % rows, expected 1', k;
    END IF;
END $$;

SELECT g.rating, g.peak_rating, g.updated_at
  FROM glicko_ratings_ffa g
 WHERE g.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c';

SELECT fmp.rating_before, fmp.rating_after, fmp.rating_change
  FROM ffa_match_players fmp
 WHERE fmp.match_id  = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
   AND fmp.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c';

COMMIT;
