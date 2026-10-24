-- 388_ffa_rating_restore_2f60481d.sql
-- Restores, in DELTA form, the rating that one FFA game moved for a seat that
-- left before two full points were scored: under the 2026-10-18 early-leave
-- ruling such a seat is not rated for that game. Data only; no code change.
-- Migration 387 restored the same game to an exact pre-image; the seat
-- played on before it ran, so 387 refuses by its own later-row guard and
-- stays on main unapplied. This file carries the correction instead.
--
-- TARGET: ffa_matches.id 2f60481d-ea6c-40e4-bda2-0ed47af8e990, the
-- ffa_match_players row of player fbb3d29d-b637-43c0-9787-357c2753e28c
-- (placement 4, left_early, voluntary, not absent, 1 game point at leave).
-- The FFA rating lives in glicko_ratings_ffa.rating.
--
-- MEASURED PRE-IMAGE (primary, read-only wrapper, 13:40Z 2026-10-19,
-- identical to the integrator reads of 13:08Z and 13:1xZ):
--   glicko_ratings_ffa  rating 2047.068334188351, peak_rating
--                       2087.094158271577, updated_at
--                       2026-10-19 06:03:20.051746+00, games_played 129
--   voided match row    rating_before 2087.094158271577, rating_after
--                       2024.3941582715768, rating_change -62.7;
--                       left_early true, left_early_involuntary false,
--                       absent false, game_points_at_leave 1, points_total 1,
--                       rounds_won 0; match ranked, not invalidated,
--                       ended_at 2026-10-18 04:59:48.93124+00
--   later rows          seven, every one a rated full game; the earliest is
--                       match 6e8c2f1c-e6df-46e9-bce9-3e31cc5fec7d, ended_at
--                       2026-10-19 04:30:37.00626+00, rating_before
--                       2024.405412230633 (the rating the voided game left)
--   no ffa_queue row for the seat; no active lobby names the seat.
--
-- RULING (integrator ruling 388): rating = rating + D, where
--   D = 2087.094158271577 - 2024.405412230633, both operands pinned
--   literals subtracted in double precision (62.6887460409439): the exact
--   amount the voided game moved the rating row. The match row's -62.7 is
--   rounded to 0.1 (main.py 58747) and is not used.
--
-- WHAT IS WRITTEN (two rows, nothing else):
--   1. glicko_ratings_ffa: rating = rating + D, peak_rating =
--      GREATEST(peak_rating, rating + D), updated_at = NOW().
--   2. the match row: rating_after = 2087.094158271577 (its rating_before),
--      rating_change = 0.
-- Rating deviation, volatility, games_played, wins, top3, placement_sum,
-- last_calculated, XP and gold are NOT touched.
--
-- WHAT IS PINNED: every value of the match row above, its match ended_at,
-- the peak (apply only), and the proof that D is the applied delta: the
-- earliest rated row of the seat after the voided match is 6e8c2f1c, ended
-- at the measured time, with rating_before 2024.405412230633, and no other
-- rated row of the seat ended in that interval. The rating VALUE and its
-- updated_at are NOT pinned: the seat keeps playing, and rating + D under
-- the row lock is right on whatever rating the row then holds.
--
-- IDEMPOTENCY: the match row is the marker. The measured pre-image applies;
-- zeroed (rating_after = rating_before, rating_change = 0) is a no-op with a
-- NOTICE; any other state RAISEs.
--
-- LIVE MATCH, read from backend/api/main.py at 3823ee96: submit_ffa_match
-- (58066-58067) locks the lobby row first (58132-58140), takes a report only
-- while ffa_lobbies.status is 'active' (58212-58251) and only when the
-- report covers exactly the frozen roster ffa_lobbies.member_ids
-- (58252-58268); it rates when the lobby is ranked (58197-58207, 58708).
-- An ffa_matches row is written only when a game is reported (ended_at is
-- bound from clock_timestamp() at 58606 into the insert at 58615-58638; the
-- column is NOT NULL, 154_ffa_schema.sql:87), so no ffa_matches column marks
-- a game in play. The seat is in a live FFA match when an ffa_lobbies row
-- with status 'active' holds it in member_ids (154_ffa_schema.sql:22, 26),
-- ranked or not; this file refuses then. The refusal lifts when that lobby
-- leaves status 'active': the lobby janitor closes an active lobby once no
-- game has ended in it for an idle window scaled by lobby size and score
-- target, and honours a live-game veto only until a ceiling of 3 h from
-- lobby creation scaled by the score target (main.py 5185-5248). Nothing in
-- this file has to change for the refusal to lift.
--
-- LOCKS, identity before rows: the identity advisory lock every FFA
-- ENROLLMENT writer takes through main.py _enrollment_identity_gate
-- (15763-15780; taken at 50926 in ffa_queue_join, and at 52978 in
-- ffa_lobby_create and 53012 in ffa_lobby_join before their shared
-- enrollment body _ffa_lobby_enroll_caller, 52872-52968), resolved here
-- from the players row so no identifier is written down; then the rating
-- row and the match row FOR NO KEY UPDATE. The rating writer,
-- submit_ffa_match, locks the rating row FOR UPDATE before it reads it
-- (58709-58717; one transaction, committed once at 59297) and writes an
-- absolute value (58749-58763); the two locks conflict, so the two never
-- interleave: whichever takes the rating row first commits before the other
-- reads it, and rating + D lands on the rating the row holds at that moment.
--
-- EVERY DECISION IS TOTAL: booleans are tested with IS TRUE / IS FALSE /
-- IS NOT FALSE, values with IS NOT DISTINCT FROM, so a NULL in any operand
-- refuses. Each UPDATE runs inside the DO block, re-asserts its predicate in
-- its WHERE, and must touch exactly one row (GET DIAGNOSTICS), or the
-- transaction aborts.
--
-- `psql -f` does not wrap a file in a transaction, so this file does.

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
    -- pinned measured literals
    m_before      CONSTANT double precision := CAST(2087.094158271577  AS double precision);
    m_after       CONSTANT double precision := CAST(2024.3941582715768 AS double precision);
    m_change      CONSTANT double precision := CAST(-62.7              AS double precision);
    m_ended       CONSTANT timestamptz      := TIMESTAMPTZ '2026-10-18 04:59:48.93124+00';
    pre_peak      CONSTANT double precision := CAST(2087.094158271577  AS double precision);
    first_match   CONSTANT uuid             := CAST('6e8c2f1c-e6df-46e9-bce9-3e31cc5fec7d' AS uuid);
    first_ended   CONSTANT timestamptz      := TIMESTAMPTZ '2026-10-19 04:30:37.00626+00';
    first_before  CONSTANT double precision := CAST(2024.405412230633  AS double precision);
    -- the applied delta: two pinned doubles, subtracted in double precision
    d             CONSTANT double precision := CAST(2087.094158271577  AS double precision)
                                             - CAST(2024.405412230633  AS double precision);
BEGIN
    -- 0. Locks, in the global order identity -> rows.
    PERFORM pg_advisory_xact_lock(hashtext(CAST(p.steam_id AS text)))
       FROM players p
      WHERE p.id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
        AND p.steam_id IS NOT NULL;
    GET DIAGNOSTICS k = ROW_COUNT;
    IF k IS DISTINCT FROM 1::bigint THEN
        RAISE EXCEPTION '388: identity lock not taken (players rows %)', k;
    END IF;
    PERFORM 1 FROM glicko_ratings_ffa
      WHERE player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
        FOR NO KEY UPDATE;
    GET DIAGNOSTICS k = ROW_COUNT;
    IF k IS DISTINCT FROM 1::bigint THEN
        RAISE EXCEPTION '388: rating row lock took % rows, expected 1', k;
    END IF;
    PERFORM 1 FROM ffa_match_players
      WHERE match_id  = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
        AND player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
        FOR NO KEY UPDATE;
    GET DIAGNOSTICS k = ROW_COUNT;
    IF k IS DISTINCT FROM 1::bigint THEN
        RAISE EXCEPTION '388: match row lock took % rows, expected 1', k;
    END IF;

    -- 1. Read the state under the locks (exactly one joined row, or raise).
    SELECT fmp.rating_before, fmp.rating_after, fmp.rating_change,
           fmp.left_early, fmp.left_early_involuntary, fmp.absent,
           fmp.game_points_at_leave, fmp.points_total, fmp.rounds_won,
           m.is_ranked, m.invalidated_at, m.ended_at,
           g.rating AS rating_now, g.peak_rating AS peak_now, g.updated_at AS stamp_now,
           EXISTS (SELECT 1 FROM ffa_queue q
                    WHERE q.player_id = fmp.player_id) AS queued,
           EXISTS (SELECT 1 FROM ffa_lobbies l
                    WHERE l.status IS NOT DISTINCT FROM 'active'
                      AND (fmp.player_id = ANY (l.member_ids)) IS NOT FALSE) AS in_live_match
      INTO STRICT r
      FROM ffa_match_players fmp
      JOIN ffa_matches m        ON m.id = fmp.match_id
      JOIN glicko_ratings_ffa g ON g.player_id = fmp.player_id
     WHERE fmp.match_id  = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
       AND fmp.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c';

    -- The earliest rated row of the seat after the voided match (NULLs when none).
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
    -- Rated rows of the seat, other than the voided one, that ended from the
    -- voided match up to the first later row: exactly that row, or the
    -- history is not the measured one (a tie at either end counts).
    SELECT COUNT(*) INTO n_window
      FROM ffa_match_players f2
      JOIN ffa_matches m2 ON m2.id = f2.match_id
     WHERE f2.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
       AND f2.match_id <> '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
       AND f2.rating_change IS NOT NULL
       AND ((m2.ended_at >= m_ended) AND (m2.ended_at <= first_ended)) IS NOT FALSE;

    -- 2. Guards for every path, apply and no-op alike.
    IF r.queued IS NOT FALSE THEN
        RAISE EXCEPTION '388: the seat has an ffa_queue row; retry when the seat is not queued';
    END IF;
    IF r.in_live_match IS NOT FALSE THEN
        RAISE EXCEPTION '388: an active FFA lobby names the seat (a live match); retry when it has closed';
    END IF;
    IF NOT ((r.left_early             IS NOT DISTINCT FROM TRUE)
            AND (r.left_early_involuntary IS NOT DISTINCT FROM FALSE)
            AND (r.absent                 IS NOT DISTINCT FROM FALSE)
            AND (r.game_points_at_leave   IS NOT DISTINCT FROM CAST(1 AS smallint))
            AND (r.points_total           IS NOT DISTINCT FROM CAST(1 AS smallint))
            AND (r.rounds_won             IS NOT DISTINCT FROM CAST(0 AS smallint))
            AND ((r.game_points_at_leave < 2) IS TRUE)
            AND (r.is_ranked IS TRUE)
            AND (r.invalidated_at IS NULL)
            AND (r.ended_at IS NOT DISTINCT FROM m_ended)) THEN
        RAISE EXCEPTION '388: the match row is not the measured eligible row (left_early %, involuntary %, absent %, points at leave %, points_total %, rounds_won %, ranked %, invalidated %, ended %)',
            r.left_early, r.left_early_involuntary, r.absent, r.game_points_at_leave,
            r.points_total, r.rounds_won, r.is_ranked, r.invalidated_at, r.ended_at;
    END IF;
    IF r.rating_before IS DISTINCT FROM m_before THEN
        RAISE EXCEPTION '388: match rating_before % is not the measured %', r.rating_before, m_before;
    END IF;
    IF NOT ((f_match  IS NOT DISTINCT FROM first_match)
            AND (f_ended  IS NOT DISTINCT FROM first_ended)
            AND (f_before IS NOT DISTINCT FROM first_before)
            AND (n_window IS NOT DISTINCT FROM 1::bigint)) THEN
        RAISE EXCEPTION '388: the first rated row after the voided match is not the measured one (match %, ended %, rating_before %, rated rows in the interval %)',
            f_match, f_ended, f_before, n_window;
    END IF;

    -- 3. Classify by the match row: the measured pre-image, zeroed, or refuse.
    is_pre  := (r.rating_after  IS NOT DISTINCT FROM m_after)
           AND (r.rating_change IS NOT DISTINCT FROM m_change);
    is_post := (r.rating_after  IS NOT DISTINCT FROM m_before)
           AND (r.rating_change IS NOT DISTINCT FROM CAST(0 AS double precision));

    IF is_post IS TRUE THEN
        -- The rating row must still have the shape every writer leaves:
        -- nothing lowers a peak, and the peak is never below the rating.
        IF NOT ((r.rating_now IS NOT NULL)
                AND ((r.peak_now >= pre_peak) IS TRUE)
                AND ((r.peak_now >= r.rating_now) IS TRUE)) THEN
            RAISE EXCEPTION '388: the match row is zeroed but the rating row is not a 388 post-image (rating %, peak %)',
                r.rating_now, r.peak_now;
        END IF;
        RAISE NOTICE '388: already applied (match row zeroed; rating %, peak %) -- no-op',
            r.rating_now, r.peak_now;
        RETURN;
    END IF;
    IF is_pre IS NOT TRUE THEN
        RAISE EXCEPTION '388: the match row is neither the measured pre-image nor zeroed (rating_after %, rating_change %)',
            r.rating_after, r.rating_change;
    END IF;

    -- 4. Apply. The peak must still read the measured value (a moved peak:
    --    refuse, re-measure, re-draft).
    IF NOT ((r.rating_now IS NOT NULL)
            AND (r.peak_now IS NOT DISTINCT FROM pre_peak)) THEN
        RAISE EXCEPTION '388: peak % is not the measured % (rating %); re-measure',
            r.peak_now, pre_peak, r.rating_now;
    END IF;

    UPDATE glicko_ratings_ffa g
       SET rating      = g.rating + d,
           peak_rating = GREATEST(g.peak_rating, g.rating + d),
           updated_at  = NOW()
     WHERE g.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
       AND g.rating      IS NOT DISTINCT FROM r.rating_now
       AND g.peak_rating IS NOT DISTINCT FROM pre_peak
       AND g.updated_at  IS NOT DISTINCT FROM r.stamp_now
    RETURNING g.rating, g.peak_rating INTO new_rating, new_peak;
    GET DIAGNOSTICS k = ROW_COUNT;
    IF k IS DISTINCT FROM 1::bigint THEN
        RAISE EXCEPTION '388: rating row update touched % rows, expected 1', k;
    END IF;

    UPDATE ffa_match_players fmp
       SET rating_after  = m_before,
           rating_change = CAST(0 AS double precision)
     WHERE fmp.match_id  = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
       AND fmp.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
       AND fmp.rating_before IS NOT DISTINCT FROM m_before
       AND fmp.rating_after  IS NOT DISTINCT FROM m_after
       AND fmp.rating_change IS NOT DISTINCT FROM m_change
       AND fmp.left_early             IS NOT DISTINCT FROM TRUE
       AND fmp.left_early_involuntary IS NOT DISTINCT FROM FALSE
       AND fmp.absent                 IS NOT DISTINCT FROM FALSE
       AND fmp.game_points_at_leave   IS NOT DISTINCT FROM CAST(1 AS smallint)
       AND fmp.points_total           IS NOT DISTINCT FROM CAST(1 AS smallint)
       AND fmp.rounds_won             IS NOT DISTINCT FROM CAST(0 AS smallint);
    GET DIAGNOSTICS k = ROW_COUNT;
    IF k IS DISTINCT FROM 1::bigint THEN
        RAISE EXCEPTION '388: match row update touched % rows, expected 1', k;
    END IF;

    RAISE NOTICE '388: rating before %, D %, rating after %, peak after %',
        r.rating_now, d, new_rating, new_peak;
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
