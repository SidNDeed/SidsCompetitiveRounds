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
-- WHAT IS WRITTEN, in this order (the delta is frozen before anything is
-- zeroed, and every write is a delta on the row, never an absolute value):
--   1. glicko_ratings_ffa.rating += delta; peak_rating = GREATEST(peak, new).
--   2. the match row: rating_after = rating_before, rating_change = 0.
-- Rating deviation, volatility, games_played, wins, top3, placement_sum,
-- XP and gold are NOT touched (see the landing note for each).
--
-- THE DELTA. submit_ffa_match stores the UNROUNDED new rating on
-- glicko_ratings_ffa but snapshots rating_change = round(new - old, 1) and
-- rating_after = rating_before + that rounded change. So the match row's
-- (rating_before - rating_after) is the applied delta only to within 0.05;
-- measured 2026-10-18 06:43Z it is 62.700000000000045 against an applied
-- 62.6887460409439. Using the snapshot would leave the seat 0.0113 ABOVE
-- its pre-game rating and lift its peak above any rating it ever held.
-- Rule, read from the rows at run time (never a literal):
--   * if the seat has NO later rated FFA row and its rating still sits
--     within 0.05 of this game's rating_after (i.e. this game was the last
--     write to the rating row), delta = rating_before - current rating:
--     the exact applied delta;
--   * otherwise delta = rating_before - rating_after from the match row
--     (exact to within the 0.05 rounding of the snapshot).
-- Expected on the measured pre-image: exact branch, delta
-- 62.6887460409439, rating 2024.405412230633 -> 2087.094158271577,
-- peak unchanged at 2087.094158271577.
--
-- IDEMPOTENT: the selection requires the match row to still carry
-- rating_change <> 0, and step 2 zeroes it in the same transaction, so a
-- second run selects nothing and writes nothing.
--
-- `psql -f` does not wrap a file in a transaction, so this file does.

BEGIN;

-- ── 0. Serialise against a concurrent FFA settlement for this seat (it
--      takes FOR UPDATE on the same rating row) and against a second run.
SELECT 1 FROM glicko_ratings_ffa
 WHERE player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
   FOR NO KEY UPDATE;
SELECT 1 FROM ffa_match_players
 WHERE match_id  = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
   AND player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
   FOR NO KEY UPDATE;

-- ── 1. Freeze the delta before anything mutates. ──────────────────────────
CREATE TEMP TABLE _ffa_restore_2f60481d ON COMMIT DROP AS
SELECT fmp.match_id,
       fmp.player_id,
       fmp.rating_before,
       fmp.rating_after,
       g.rating AS rating_now,
       (NOT EXISTS (SELECT 1
                      FROM ffa_match_players f2
                      JOIN ffa_matches m2 ON m2.id = f2.match_id
                     WHERE f2.player_id = fmp.player_id
                       AND f2.match_id <> fmp.match_id
                       AND f2.rating_change IS NOT NULL
                       AND m2.ended_at > m.ended_at)
        AND abs(g.rating - fmp.rating_after) <= 0.05) AS exact_branch
  FROM ffa_match_players fmp
  JOIN ffa_matches m        ON m.id = fmp.match_id
  JOIN glicko_ratings_ffa g ON g.player_id = fmp.player_id
 WHERE fmp.match_id  = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
   AND fmp.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
   AND fmp.left_early
   AND NOT fmp.absent
   AND NOT fmp.left_early_involuntary
   AND fmp.game_points_at_leave < 2
   AND fmp.rating_change IS NOT NULL
   AND fmp.rating_change <> 0
   AND fmp.rating_after IS NOT NULL
   AND m.is_ranked
   AND m.invalidated_at IS NULL;

ALTER TABLE _ffa_restore_2f60481d ADD COLUMN delta DOUBLE PRECISION;
UPDATE _ffa_restore_2f60481d
   SET delta = CASE WHEN exact_branch THEN rating_before - rating_now
                    ELSE rating_before - rating_after END;

-- Sanity bound: at most one row (primary key), a positive delta (the game
-- cost the seat rating), and the delta within the snapshot's 0.05 rounding.
DO $$
DECLARE
    n  integer;
    r  record;
BEGIN
    SELECT COUNT(*) INTO n FROM _ffa_restore_2f60481d;
    IF n = 0 THEN
        RAISE NOTICE '387: nothing to restore (match row already zeroed or not eligible) -- no-op';
        RETURN;
    END IF;
    IF n <> 1 THEN
        RAISE EXCEPTION '387: expected 1 row to restore, found %', n;
    END IF;
    SELECT * INTO r FROM _ffa_restore_2f60481d;
    IF NOT (r.delta > 0) THEN
        RAISE EXCEPTION '387: delta % is not positive', r.delta;
    END IF;
    IF abs(r.delta - (r.rating_before - r.rating_after)) > 0.05 THEN
        RAISE EXCEPTION '387: delta % is not within 0.05 of the snapshot delta %',
            r.delta, r.rating_before - r.rating_after;
    END IF;
    RAISE NOTICE '387: exact_branch=% delta=% rating % -> %',
        r.exact_branch, r.delta, r.rating_now, r.rating_now + r.delta;
END $$;

-- ── 2. The rating row: a delta, and the peak only ever raised. ───────────
UPDATE glicko_ratings_ffa g
   SET rating      = g.rating + f.delta,
       peak_rating = GREATEST(g.peak_rating, g.rating + f.delta),
       updated_at  = NOW()
  FROM _ffa_restore_2f60481d f
 WHERE g.player_id = f.player_id;

-- ── 3. The match row: unrated for this game (the guard for a re-run). ────
UPDATE ffa_match_players fmp
   SET rating_after  = fmp.rating_before,
       rating_change = 0
  FROM _ffa_restore_2f60481d f
 WHERE fmp.match_id  = f.match_id
   AND fmp.player_id = f.player_id
   AND fmp.rating_change <> 0;

-- ── 4. Verification, printed before COMMIT lands. ────────────────────────
SELECT g.rating, g.peak_rating, g.rating_deviation, g.volatility, g.games_played
  FROM glicko_ratings_ffa g
 WHERE g.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c';

SELECT fmp.rating_before, fmp.rating_after, fmp.rating_change
  FROM ffa_match_players fmp
 WHERE fmp.match_id  = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
   AND fmp.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c';

-- Must return 0.
SELECT COUNT(*) AS should_be_zero
  FROM ffa_match_players fmp
 WHERE fmp.match_id  = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
   AND fmp.player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
   AND fmp.rating_change <> 0;

COMMIT;
