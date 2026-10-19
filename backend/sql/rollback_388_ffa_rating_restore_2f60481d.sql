-- rollback_388_ffa_rating_restore_2f60481d.sql
-- Reverses migration 388 (the delta-form rating restore of one FFA seat
-- under the 2026-10-18 early-leave ruling) in its IMMEDIATE WINDOW only.
-- Data only.
--
-- VALID ONLY WHEN (integrator ruling 388, item 6):
--   * the match row is zeroed (388's post-image: rating_after =
--     rating_before = 2087.094158271577, rating_change = 0);
--   * no rated row of the seat ended after the rating row's updated_at (388
--     stamps it with NOW(); a rated game stamps the row with its own
--     transaction's NOW() and records an ended_at read later in that same
--     transaction, main.py 58606 and 58760, committed once at 59297, so a
--     game rated after 388 shows as a row that ended after the stamp), so
--     the rating still holds what 388 wrote;
--   * peak_rating IS NOT DISTINCT FROM GREATEST(2087.094158271577, rating),
--     the shape 388 leaves.
-- Outside that window this file refuses; a later correction is a new file.
-- A game whose report read its clock after 388 began but committed before
-- 388 took the rating row also reads as ended after the stamp, so the
-- rollback refuses there although the rating holds what 388 wrote: the
-- conservative side.
--
-- WRITES (two rows, nothing else):
--   1. glicko_ratings_ffa: rating = rating - D (the same pinned D as 388:
--      2087.094158271577 - 2024.405412230633 in double precision),
--      peak_rating = 2087.094158271577 (the measured peak 388 required
--      before it wrote), updated_at = NOW().
--   2. the match row: rating_after = 2024.3941582715768, rating_change =
--      -62.7 (the measured pre-image literals).
-- EXACTNESS: rating - D gives back the pre-388 rating bit-exactly when
-- (x + D) - D equals x in double precision; it does for the measured
-- x = 2047.068334188351, and for any x of at least D it is within one unit
-- in the last place of x. updated_at does not return to its pre-388 value
-- (that value is not pinned; the ruling writes NOW()).
--
-- NO-OP: the match row in the measured pre-image (388 never applied, or
-- already rolled back) -> NOTICE, no write. Any other state RAISEs.
--
-- The guards 388 runs before any decision run here too: no ffa_queue row,
-- no active lobby naming the seat (the live-match predicate read in the 388
-- header), the match row eligibility and ended_at pinned, rating_before
-- pinned, and the first rated row after the voided match pinned.
--
-- LOCKS, identity before rows: the identity advisory lock every FFA
-- ENROLLMENT writer takes through main.py _enrollment_identity_gate
-- (15763-15780; taken at 50926 in ffa_queue_join, and at 52978 in
-- ffa_lobby_create and 53012 in ffa_lobby_join before their shared
-- enrollment body _ffa_lobby_enroll_caller, 52872-52968), resolved from
-- the players row; then the rating row and the match row FOR NO KEY
-- UPDATE.
--
-- EVERY DECISION IS TOTAL (IS TRUE / IS FALSE / IS NOT FALSE / IS NOT
-- DISTINCT FROM; a NULL in any operand refuses). Each UPDATE runs inside the
-- DO block, re-asserts its predicate in its WHERE, and must touch exactly
-- one row, or the transaction aborts.

BEGIN;

DO $$
DECLARE
    k             bigint;
    r             record;
    f_match       uuid;
    f_ended       timestamptz;
    f_before      double precision;
    n_window      bigint;
    new_rating    double precision;
    new_peak      double precision;
    is_pre        boolean;
    is_post       boolean;
    m_before      CONSTANT double precision := CAST(2087.094158271577  AS double precision);
    m_after       CONSTANT double precision := CAST(2024.3941582715768 AS double precision);
    m_change      CONSTANT double precision := CAST(-62.7              AS double precision);
    m_ended       CONSTANT timestamptz      := TIMESTAMPTZ '2026-10-18 04:59:48.93124+00';
    pre_peak      CONSTANT double precision := CAST(2087.094158271577  AS double precision);
    first_match   CONSTANT uuid             := CAST('6e8c2f1c-e6df-46e9-bce9-3e31cc5fec7d' AS uuid);
    first_ended   CONSTANT timestamptz      := TIMESTAMPTZ '2026-10-19 04:30:37.00626+00';
    first_before  CONSTANT double precision := CAST(2024.405412230633  AS double precision);
    d             CONSTANT double precision := CAST(2087.094158271577  AS double precision)
                                             - CAST(2024.405412230633  AS double precision);
BEGIN
    -- Locks, in the global order identity -> rows.
    PERFORM pg_advisory_xact_lock(hashtext(CAST(p.steam_id AS text)))
       FROM players p
      WHERE p.id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
        AND p.steam_id IS NOT NULL;
    GET DIAGNOSTICS k = ROW_COUNT;
    IF k IS DISTINCT FROM 1::bigint THEN
        RAISE EXCEPTION 'rollback 388: identity lock not taken (players rows %)', k;
    END IF;
    PERFORM 1 FROM glicko_ratings_ffa
      WHERE player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
        FOR NO KEY UPDATE;
    GET DIAGNOSTICS k = ROW_COUNT;
    IF k IS DISTINCT FROM 1::bigint THEN
        RAISE EXCEPTION 'rollback 388: rating row lock took % rows, expected 1', k;
    END IF;
    PERFORM 1 FROM ffa_match_players
      WHERE match_id  = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
        AND player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
        FOR NO KEY UPDATE;
    GET DIAGNOSTICS k = ROW_COUNT;
    IF k IS DISTINCT FROM 1::bigint THEN
        RAISE EXCEPTION 'rollback 388: match row lock took % rows, expected 1', k;
    END IF;

    SELECT fmp.rating_before, fmp.rating_after, fmp.rating_change,
           fmp.left_early, fmp.left_early_involuntary, fmp.absent,
           fmp.game_points_at_leave, fmp.points_total, fmp.rounds_won,
           m.is_ranked, m.invalidated_at, m.ended_at,
           g.rating AS rating_now, g.peak_rating AS peak_now, g.updated_at AS stamp_now,
           EXISTS (SELECT 1 FROM ffa_queue q
                    WHERE q.player_id = fmp.player_id) AS queued,
           EXISTS (SELECT 1 FROM ffa_lobbies l
                    WHERE l.status IS NOT DISTINCT FROM 'active'
                      AND (fmp.player_id = ANY (l.member_ids)) IS NOT FALSE) AS in_live_match,
           EXISTS (SELECT 1
                     FROM ffa_match_players f2
                     JOIN ffa_matches m2 ON m2.id = f2.match_id
                    WHERE f2.player_id = fmp.player_id
                      AND f2.match_id <> fmp.match_id
                      AND f2.rating_change IS NOT NULL
                      AND (m2.ended_at > g.updated_at) IS NOT FALSE) AS rated_after_stamp
      INTO STRICT r
      FROM ffa_match_players fmp
      JOIN ffa_matches m        ON m.id = fmp.match_id
      JOIN glicko_ratings_ffa g ON g.player_id = fmp.player_id
     WHERE fmp.match_id  = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
       AND fmp.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c';

    SELECT f2.match_id, m2.ended_at, f2.rating_before
      INTO f_match, f_ended, f_before
      FROM ffa_match_players f2
      JOIN ffa_matches m2 ON m2.id = f2.match_id
     WHERE f2.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
       AND f2.match_id <> '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
       AND f2.rating_change IS NOT NULL
       AND m2.ended_at > m_ended
     ORDER BY m2.ended_at, f2.match_id
     LIMIT 1;
    SELECT COUNT(*) INTO n_window
      FROM ffa_match_players f2
      JOIN ffa_matches m2 ON m2.id = f2.match_id
     WHERE f2.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
       AND f2.match_id <> '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
       AND f2.rating_change IS NOT NULL
       AND ((m2.ended_at >= m_ended) AND (m2.ended_at <= first_ended)) IS NOT FALSE;

    -- Guards for every path, apply and no-op alike.
    IF r.queued IS NOT FALSE THEN
        RAISE EXCEPTION 'rollback 388: the seat has an ffa_queue row; retry when the seat is not queued';
    END IF;
    IF r.in_live_match IS NOT FALSE THEN
        RAISE EXCEPTION 'rollback 388: an active FFA lobby names the seat (a live match); retry when it has closed';
    END IF;
    IF NOT ((r.left_early             IS NOT DISTINCT FROM TRUE)
            AND (r.left_early_involuntary IS NOT DISTINCT FROM FALSE)
            AND (r.absent                 IS NOT DISTINCT FROM FALSE)
            AND (r.game_points_at_leave   IS NOT DISTINCT FROM CAST(1 AS smallint))
            AND (r.points_total           IS NOT DISTINCT FROM CAST(1 AS smallint))
            AND (r.rounds_won             IS NOT DISTINCT FROM CAST(0 AS smallint))
            AND (r.is_ranked IS TRUE)
            AND (r.invalidated_at IS NULL)
            AND (r.ended_at IS NOT DISTINCT FROM m_ended)) THEN
        RAISE EXCEPTION 'rollback 388: the match row is not the measured eligible row (left_early %, involuntary %, absent %, points at leave %, points_total %, rounds_won %, ranked %, invalidated %, ended %)',
            r.left_early, r.left_early_involuntary, r.absent, r.game_points_at_leave,
            r.points_total, r.rounds_won, r.is_ranked, r.invalidated_at, r.ended_at;
    END IF;
    IF r.rating_before IS DISTINCT FROM m_before THEN
        RAISE EXCEPTION 'rollback 388: match rating_before % is not the measured %', r.rating_before, m_before;
    END IF;
    IF NOT ((f_match  IS NOT DISTINCT FROM first_match)
            AND (f_ended  IS NOT DISTINCT FROM first_ended)
            AND (f_before IS NOT DISTINCT FROM first_before)
            AND (n_window IS NOT DISTINCT FROM 1::bigint)) THEN
        RAISE EXCEPTION 'rollback 388: the first rated row after the voided match is not the measured one (match %, ended %, rating_before %, rated rows in the interval %)',
            f_match, f_ended, f_before, n_window;
    END IF;

    is_post := (r.rating_after  IS NOT DISTINCT FROM m_before)
           AND (r.rating_change IS NOT DISTINCT FROM CAST(0 AS double precision));
    is_pre  := (r.rating_after  IS NOT DISTINCT FROM m_after)
           AND (r.rating_change IS NOT DISTINCT FROM m_change);

    IF is_pre IS TRUE THEN
        IF NOT ((r.rating_now IS NOT NULL)
                AND ((r.peak_now >= pre_peak) IS TRUE)
                AND ((r.peak_now >= r.rating_now) IS TRUE)) THEN
            RAISE EXCEPTION 'rollback 388: the match row reads the pre-image but the rating row has an impossible shape (rating %, peak %)',
                r.rating_now, r.peak_now;
        END IF;
        RAISE NOTICE 'rollback 388: the match row reads the measured pre-image -- no-op';
        RETURN;
    END IF;
    IF is_post IS NOT TRUE THEN
        RAISE EXCEPTION 'rollback 388: the match row is neither zeroed nor the measured pre-image (rating_after %, rating_change %)',
            r.rating_after, r.rating_change;
    END IF;

    -- The immediate window.
    IF r.rated_after_stamp IS NOT FALSE THEN
        RAISE EXCEPTION 'rollback 388: a rated row of the seat ended after the rating row stamp %; outside the rollback window, a later correction is a new file',
            r.stamp_now;
    END IF;
    IF NOT ((r.rating_now IS NOT NULL)
            AND (r.peak_now IS NOT DISTINCT FROM GREATEST(pre_peak, r.rating_now))) THEN
        RAISE EXCEPTION 'rollback 388: peak % is not GREATEST(%, rating %), not the 388 post-image',
            r.peak_now, pre_peak, r.rating_now;
    END IF;

    UPDATE glicko_ratings_ffa g
       SET rating      = g.rating - d,
           peak_rating = pre_peak,
           updated_at  = NOW()
     WHERE g.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
       AND g.rating      IS NOT DISTINCT FROM r.rating_now
       AND g.peak_rating IS NOT DISTINCT FROM GREATEST(pre_peak, r.rating_now)
       AND g.updated_at  IS NOT DISTINCT FROM r.stamp_now
    RETURNING g.rating, g.peak_rating INTO new_rating, new_peak;
    GET DIAGNOSTICS k = ROW_COUNT;
    IF k IS DISTINCT FROM 1::bigint THEN
        RAISE EXCEPTION 'rollback 388: rating row update touched % rows, expected 1', k;
    END IF;

    UPDATE ffa_match_players fmp
       SET rating_after  = m_after,
           rating_change = m_change
     WHERE fmp.match_id  = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
       AND fmp.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
       AND fmp.rating_before IS NOT DISTINCT FROM m_before
       AND fmp.rating_after  IS NOT DISTINCT FROM m_before
       AND fmp.rating_change IS NOT DISTINCT FROM CAST(0 AS double precision)
       AND fmp.left_early             IS NOT DISTINCT FROM TRUE
       AND fmp.left_early_involuntary IS NOT DISTINCT FROM FALSE
       AND fmp.absent                 IS NOT DISTINCT FROM FALSE
       AND fmp.game_points_at_leave   IS NOT DISTINCT FROM CAST(1 AS smallint)
       AND fmp.points_total           IS NOT DISTINCT FROM CAST(1 AS smallint)
       AND fmp.rounds_won             IS NOT DISTINCT FROM CAST(0 AS smallint);
    GET DIAGNOSTICS k = ROW_COUNT;
    IF k IS DISTINCT FROM 1::bigint THEN
        RAISE EXCEPTION 'rollback 388: match row update touched % rows, expected 1', k;
    END IF;

    RAISE NOTICE 'rollback 388: rating before %, D %, rating after %, peak after %',
        r.rating_now, d, new_rating, new_peak;
END $$;

SELECT g.rating, g.peak_rating, g.updated_at
  FROM glicko_ratings_ffa g
 WHERE g.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c';

SELECT fmp.rating_before, fmp.rating_after, fmp.rating_change
  FROM ffa_match_players fmp
 WHERE fmp.match_id  = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
   AND fmp.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c';

COMMIT;
