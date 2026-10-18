-- 387_ffa_rating_restore_2f60481d.sql
-- Restores the rating delta of one FFA seat whose game falls under the
-- 2026-10-18 early-leave ruling: a seat that left before two full points
-- were scored is not rated for that game. Data only; no code change.
--
-- TARGET: ffa_matches.id 2f60481d-ea6c-40e4-bda2-0ed47af8e990, the
-- ffa_match_players row of player fbb3d29d-b637-43c0-9787-357c2753e28c
-- (placement 4 of 4, left_early, voluntary, not absent, 1 game point at
-- leave). The FFA rating lives in glicko_ratings_ffa.rating
-- (glicko_ratings is the 1v1 table, not this one).
--
-- MEASURED PRE-IMAGE, pinned below as literals (primary, read-only
-- wrapper, read at 06:43Z, 07:22Z and 08:00Z 2026-10-18, identical text):
--   glicko_ratings_ffa  rating 2024.405412230633, peak_rating
--                       2087.094158271577, updated_at
--                       2026-10-18 04:59:48.803927+00
--   ffa_match_players   rating_before 2087.094158271577, rating_after
--                       2024.3941582715768, rating_change -62.7
--   no later rated FFA row for the seat; no ffa_queue row.
--
-- WHAT IS WRITTEN (two rows, nothing else), every value a verified literal:
--   1. glicko_ratings_ffa: rating = 2087.094158271577 (the pinned match
--      rating_before), peak_rating = GREATEST(peak, that value) (a no-op:
--      the peak is pinned at the same value), updated_at = NOW().
--   2. the match row: rating_after = 2087.094158271577, rating_change = 0.
-- Rating deviation, volatility, games_played, wins, top3, placement_sum,
-- last_calculated, XP and gold are NOT touched.
--
-- DEVIATION FROM THE DELTA RULE (learning 326), stated: the rating write is
-- an absolute literal, not rating + delta. The stored rating_change is
-- rounded to 0.1 (main.py submit_ffa_match) while the rating row holds the
-- unrounded result, so no stored delta is exact. Under the identity
-- advisory lock, the row locks and the bit-exact pre-image guard below,
-- the literal equals pre-image + applied delta exactly, so the absolute
-- write and the delta write are the same value. There is no fallback.
--
-- EVERY DECISION IS TOTAL: booleans are tested with IS TRUE / IS FALSE,
-- values with IS NOT DISTINCT FROM, so a NULL in any operand refuses. The
-- state must be EXACTLY the measured pre-image (apply) or EXACTLY this
-- file's post-image (no-op); anything else RAISEs. Each UPDATE runs inside
-- the DO block, re-asserts the pinned values in its WHERE, and must touch
-- exactly one row (GET DIAGNOSTICS), or the transaction aborts.
--
-- `psql -f` does not wrap a file in a transaction, so this file does.

BEGIN;

DO $$
DECLARE
    k            bigint;
    r            record;
    -- pinned measured literals
    pre_rating   CONSTANT double precision := CAST(2024.405412230633  AS double precision);
    pre_peak     CONSTANT double precision := CAST(2087.094158271577  AS double precision);
    pre_stamp    CONSTANT timestamptz      := TIMESTAMPTZ '2026-10-18 04:59:48.803927+00';
    m_before     CONSTANT double precision := CAST(2087.094158271577  AS double precision);
    m_after      CONSTANT double precision := CAST(2024.3941582715768 AS double precision);
    m_change     CONSTANT double precision := CAST(-62.7              AS double precision);
    is_pre       boolean;
    is_post      boolean;
BEGIN
    -- 0. Locks, in the global order identity -> rows. The identity key is
    --    the one every FFA ENROLLMENT writer takes through its gate
    --    (main.py _enrollment_identity_gate 15763-15780, called from the
    --    enrollment paths at 50925-50993, 52881-52953, 52971-53012):
    --    pg_advisory_xact_lock(hashtext(steam id)), resolved here from the
    --    players row so no identifier is written down.
    PERFORM pg_advisory_xact_lock(hashtext(CAST(p.steam_id AS text)))
       FROM players p
      WHERE p.id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
        AND p.steam_id IS NOT NULL;
    GET DIAGNOSTICS k = ROW_COUNT;
    IF k IS DISTINCT FROM 1::bigint THEN
        RAISE EXCEPTION '387: identity lock not taken (players rows %)', k;
    END IF;
    PERFORM 1 FROM glicko_ratings_ffa
      WHERE player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
        FOR NO KEY UPDATE;
    PERFORM 1 FROM ffa_match_players
      WHERE match_id  = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
        AND player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
        FOR NO KEY UPDATE;

    -- 1. Read the state under the locks (exactly one joined row, or raise).
    SELECT fmp.rating_before, fmp.rating_after, fmp.rating_change,
           fmp.left_early, fmp.absent, fmp.left_early_involuntary,
           fmp.game_points_at_leave,
           m.is_ranked, m.invalidated_at,
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

    -- 2. Guards common to apply AND no-op.
    IF r.queued IS NOT FALSE THEN
        RAISE EXCEPTION '387: the seat has an ffa_queue row; retry when the seat is not queued';
    END IF;
    IF r.later_rated IS NOT FALSE THEN
        RAISE EXCEPTION '387: a later rated FFA row exists for the seat; this file does not apply';
    END IF;
    IF NOT ((r.left_early IS TRUE)
            AND (r.absent IS FALSE)
            AND (r.left_early_involuntary IS FALSE)
            AND ((r.game_points_at_leave < 2) IS TRUE)
            AND (r.is_ranked IS TRUE)
            AND (r.invalidated_at IS NULL)) THEN
        RAISE EXCEPTION '387: the match row is not eligible under the ruling (left_early %, absent %, involuntary %, points %, ranked %, invalidated %)',
            r.left_early, r.absent, r.left_early_involuntary, r.game_points_at_leave,
            r.is_ranked, r.invalidated_at;
    END IF;
    IF r.rating_before IS DISTINCT FROM m_before THEN
        RAISE EXCEPTION '387: match rating_before % is not the measured %', r.rating_before, m_before;
    END IF;
    IF r.peak_now IS DISTINCT FROM pre_peak THEN
        RAISE EXCEPTION '387: peak % is not the measured %', r.peak_now, pre_peak;
    END IF;

    -- 3. Classify: exactly the pre-image, exactly the post-image, or refuse.
    is_pre  := (r.rating_now    IS NOT DISTINCT FROM pre_rating)
           AND (r.stamp_now     IS NOT DISTINCT FROM pre_stamp)
           AND (r.rating_after  IS NOT DISTINCT FROM m_after)
           AND (r.rating_change IS NOT DISTINCT FROM m_change);
    is_post := (r.rating_now    IS NOT DISTINCT FROM m_before)
           AND (r.rating_after  IS NOT DISTINCT FROM m_before)
           AND (r.rating_change IS NOT DISTINCT FROM CAST(0 AS double precision));

    IF is_post IS TRUE THEN
        RAISE NOTICE '387: already applied (rating %, match row zeroed, peak %) -- no-op',
            r.rating_now, r.peak_now;
        RETURN;
    END IF;
    IF is_pre IS NOT TRUE THEN
        RAISE EXCEPTION '387: state is neither the measured pre-image nor the 387 post-image (rating %, updated_at %, after %, change %)',
            r.rating_now, r.stamp_now, r.rating_after, r.rating_change;
    END IF;

    RAISE NOTICE '387: rating_now=% pre_image=% snapshot_delta=% applied_delta=% -> %',
        r.rating_now, pre_rating, m_before - m_after, m_before - r.rating_now, m_before;

    -- 4. The rating row.
    UPDATE glicko_ratings_ffa g
       SET rating      = m_before,
           peak_rating = GREATEST(g.peak_rating, m_before),
           updated_at  = NOW()
     WHERE g.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
       AND g.rating      IS NOT DISTINCT FROM pre_rating
       AND g.peak_rating IS NOT DISTINCT FROM pre_peak
       AND g.updated_at  IS NOT DISTINCT FROM pre_stamp;
    GET DIAGNOSTICS k = ROW_COUNT;
    IF k IS DISTINCT FROM 1::bigint THEN
        RAISE EXCEPTION '387: rating row update touched % rows, expected 1', k;
    END IF;

    -- 5. The match row: unrated for this game.
    UPDATE ffa_match_players fmp
       SET rating_after  = m_before,
           rating_change = CAST(0 AS double precision)
     WHERE fmp.match_id  = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
       AND fmp.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
       AND fmp.rating_before IS NOT DISTINCT FROM m_before
       AND fmp.rating_after  IS NOT DISTINCT FROM m_after
       AND fmp.rating_change IS NOT DISTINCT FROM m_change;
    GET DIAGNOSTICS k = ROW_COUNT;
    IF k IS DISTINCT FROM 1::bigint THEN
        RAISE EXCEPTION '387: match row update touched % rows, expected 1', k;
    END IF;
END $$;

-- Verification, printed before COMMIT lands.
SELECT g.rating, g.peak_rating, g.rating_deviation, g.volatility, g.games_played, g.updated_at
  FROM glicko_ratings_ffa g
 WHERE g.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c';

SELECT fmp.rating_before, fmp.rating_after, fmp.rating_change
  FROM ffa_match_players fmp
 WHERE fmp.match_id  = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
   AND fmp.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c';

COMMIT;
