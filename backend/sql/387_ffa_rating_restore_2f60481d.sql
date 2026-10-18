-- 387_ffa_rating_restore_2f60481d.sql
-- Restores the rating delta of one FFA seat whose game falls under the
-- 2026-10-18 early-leave ruling: a seat that left before two full points
-- were scored is not rated for that game. Data only; no code change.
--
-- TARGET: ffa_matches.id 2f60481d-ea6c-40e4-bda2-0ed47af8e990, the
-- ffa_match_players row of player fbb3d29d-b637-43c0-9787-357c2753e28c
-- (placement 4 of 4, left_early, voluntary, not absent, 1 game point at
-- leave, rating_change -62.7). The FFA rating lives in
-- glicko_ratings_ffa.rating (glicko_ratings is the 1v1 table, not this one).
--
-- MEASURED PRE-IMAGE (primary, read-only wrapper, 06:43Z and again 07:22Z
-- 2026-10-18, identical text): rating 2024.405412230633, peak_rating
-- 2087.094158271577, updated_at 2026-10-18 04:59:48.803927+00; match row
-- rating_before 2087.094158271577, rating_after 2024.3941582715768,
-- rating_change -62.7; no later rated FFA row; no ffa_queue row.
--
-- WHAT IS WRITTEN (two rows, nothing else):
--   1. glicko_ratings_ffa: rating = rating_before (2087.094158271577),
--      peak_rating = GREATEST(peak, rating_before) (a no-op: the guard pins
--      the peak at that value), updated_at = NOW().
--   2. the match row: rating_after = rating_before, rating_change = 0.
-- Rating deviation, volatility, games_played, wins, top3, placement_sum,
-- last_calculated, XP and gold are NOT touched.
--
-- DEVIATION FROM THE DELTA RULE (learning 326), stated: the rating write is
-- the absolute value rating_before, not rating + delta. The stored
-- rating_change is rounded to 0.1 (main.py submit_ffa_match) while the
-- rating row holds the unrounded result, so no stored delta is exact. This
-- file therefore REFUSES unless the rating row is bit-exactly the measured
-- pre-image and no later rated game exists; under that guard, the identity
-- advisory lock and the row lock, rating_before equals pre-image + the
-- applied delta exactly, so the absolute write and the delta write are the
-- same value. There is no fallback path.
--
-- REFUSALS (RAISE EXCEPTION before any write; the transaction rolls back):
-- target rows missing; seat in ffa_queue (the queue row snapshots the
-- rating: retry the landing when the seat is not queued); match row not
-- eligible under the ruling; a later rated FFA row exists; rating or peak
-- differs from the measured pre-image.
-- IDEMPOTENT: if the rows are already in this file's post-image the file
-- writes nothing and prints a NOTICE.
--
-- `psql -f` does not wrap a file in a transaction, so this file does.

BEGIN;

-- ── 0. Locks, in the global order identity -> rows. The identity key is
--      the one every FFA queue/lobby writer takes (main.py
--      _enrollment_identity_gate: pg_advisory_xact_lock(hashtext(steam id))),
--      resolved here from the players row so no identifier is written down.
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

-- ── 1. Freeze the state under the locks. ─────────────────────────────────
CREATE TEMP TABLE _ffa_restore_2f60481d ON COMMIT DROP AS
SELECT fmp.match_id,
       fmp.player_id,
       fmp.rating_before,
       fmp.rating_after,
       fmp.rating_change,
       g.rating      AS rating_now,
       g.peak_rating AS peak_now,
       (fmp.left_early
        AND NOT fmp.absent
        AND NOT fmp.left_early_involuntary
        AND fmp.game_points_at_leave < 2
        AND fmp.rating_change IS NOT NULL
        AND fmp.rating_change <> 0
        AND fmp.rating_after IS NOT NULL
        AND m.is_ranked
        AND m.invalidated_at IS NULL)                         AS eligible,
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

-- ── 2. Decide: no-op, apply, or refuse. Nothing is written above here. ──
DO $$
DECLARE
    n  integer;
    r  record;
    pre_rating CONSTANT double precision := CAST(2024.405412230633 AS double precision);
    pre_peak   CONSTANT double precision := CAST(2087.094158271577 AS double precision);
BEGIN
    SELECT COUNT(*) INTO n FROM _ffa_restore_2f60481d;
    IF n <> 1 THEN
        RAISE EXCEPTION '387: expected the match row and the rating row (1 joined row), found %', n;
    END IF;
    SELECT * INTO r FROM _ffa_restore_2f60481d;

    IF r.rating_change = 0 AND r.rating_after = r.rating_before
       AND r.rating_now = r.rating_before THEN
        RAISE NOTICE '387: already applied (rating %, match row zeroed) -- no-op', r.rating_now;
        RETURN;
    END IF;

    IF NOT r.identity_locked THEN
        RAISE EXCEPTION '387: players row missing, identity lock not taken';
    END IF;
    IF r.queued THEN
        RAISE EXCEPTION '387: the seat has an ffa_queue row; retry when the seat is not queued';
    END IF;
    IF NOT r.eligible THEN
        RAISE EXCEPTION '387: the match row is not eligible under the ruling (change %, after %)',
            r.rating_change, r.rating_after;
    END IF;
    IF r.later_rated THEN
        RAISE EXCEPTION '387: a later rated FFA row exists for the seat; this file does not apply';
    END IF;
    IF r.rating_now <> pre_rating THEN
        RAISE EXCEPTION '387: rating % is not the measured pre-image %', r.rating_now, pre_rating;
    END IF;
    IF r.peak_now <> pre_peak THEN
        RAISE EXCEPTION '387: peak % is not the measured pre-image %', r.peak_now, pre_peak;
    END IF;

    RAISE NOTICE '387: rating_now=% pre_image=% snapshot_delta=% applied_delta=% -> %',
        r.rating_now, pre_rating, r.rating_before - r.rating_after,
        r.rating_before - r.rating_now, r.rating_before;
    UPDATE _ffa_restore_2f60481d SET apply = TRUE;
END $$;

-- ── 3. The rating row (re-asserts the pre-image in the WHERE). ───────────
UPDATE glicko_ratings_ffa g
   SET rating      = f.rating_before,
       peak_rating = GREATEST(g.peak_rating, f.rating_before),
       updated_at  = NOW()
  FROM _ffa_restore_2f60481d f
 WHERE f.apply
   AND g.player_id = f.player_id
   AND g.rating    = CAST(2024.405412230633 AS double precision);

-- ── 4. The match row: unrated for this game. ─────────────────────────────
UPDATE ffa_match_players fmp
   SET rating_after  = fmp.rating_before,
       rating_change = 0
  FROM _ffa_restore_2f60481d f
 WHERE f.apply
   AND fmp.match_id  = f.match_id
   AND fmp.player_id = f.player_id
   AND fmp.rating_change <> 0;

-- ── 5. Verification, printed before COMMIT lands. ────────────────────────
SELECT g.rating, g.peak_rating, g.rating_deviation, g.volatility, g.games_played, g.updated_at
  FROM glicko_ratings_ffa g
 WHERE g.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c';

SELECT fmp.rating_before, fmp.rating_after, fmp.rating_change
  FROM ffa_match_players fmp
 WHERE fmp.match_id  = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
   AND fmp.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c';

COMMIT;
