-- 234_ffa_early_leave_grace_backfill.sql
-- Retroactive half of the FFA early-leave grace (migration 233 / Sid,
-- 2026-08-20): un-rate the games players were charged Elo for after leaving
-- before anything had been decided.
--
-- ── WHY THIS IS A PROXY, SAID OUT LOUD ──────────────────────────────────────
-- The live rule tests the field's point total AT THE MOMENT OF THE LEAVE, a
-- number only a client in the room can know and one nothing recorded before
-- migration 233. It cannot be recovered: ffa_matches.timeline is an ordered log
-- of WHO scored, with no clock and no leave events, and no server-side table
-- timestamps a departure.
--
-- So this migration selects on the evidence that does survive — an ENTIRELY
-- EMPTY stat line on a left_early row:
--     rounds_won = 0 AND points_total = 0 AND kills = 0 AND damage_dealt = 0
-- A player who was really in the fight leaves a trace in at least one of those
-- four; damage_dealt in particular is computed locally for every seat from
-- vanilla's damage RPCs, so it is present even for someone who never scored.
-- Zero on all four is a seat that produced nothing at all.
--
-- This is deliberately STRICTER than the live rule, which refuses a grace only
-- on the signed placement inputs (rounds / points / kills) and never on damage
-- — someone who fought through the opening round-let and left at one field
-- point has earned the grace even though they dealt damage. Retroactively we
-- have no leave time, so the bar is raised to compensate.
--
-- It is a proxy, not the rule: it would also catch someone who idled a whole
-- game and left at the end. Nine of the ten rows sit in games where TWO OR
-- THREE players left with identical empty lines in the same game — the
-- signature of a game that broke at the start, which is exactly the case the
-- 2v2 dc_incomplete rule was written to protect ("a game can break and need a
-- restart, and we never auto-penalize for that").
--
-- ── WHAT IT DOES AND DOESN'T TOUCH ─────────────────────────────────────────
-- DOES:   reverses the affected rating_change on the live glicko_ratings_ffa
--         row, decrements games_played / placement_sum (and top3 / wins, which
--         are zero here — every affected placement is 4th or worse), marks the
--         match row absent so it drops out of the rating graph and the profile
--         aggregates, and recomputes peak_rating from the surviving rated rows
--         so nobody keeps a peak they only reached through a voided game.
--
-- DOESN'T: touch the players who STAYED. Under the live rule their opponent set
--         would have excluded the leaver and their own deltas would differ
--         slightly. Re-rating them means re-rating the match, and re-rating the
--         match means replaying 161 matches under today's constants, which
--         would move ratings for people who have nothing to do with this bug.
--         The asymmetry is deliberate: this only ever REMOVES a penalty the
--         leaver should not have paid, never claws back what anyone else won.
--
-- DOESN'T: touch XP or gold. Those were paid out, banked, and in some cases
--         spent. A live graced row records 0/0; these rows keep what was
--         actually paid, because the gold_transactions ledger is the source of
--         truth for the economy and rewriting one side of it to match a rule
--         that did not exist at the time would be the bigger lie.
--
-- ── ACCURACY ───────────────────────────────────────────────────────────────
-- Reversing the delta is EXACT for a player who has played no rated FFA since
-- (SpineOfGlass, Sewer_Gremlin, pskittle100, Sid). For the rest the later games
-- were rated from a polluted starting point, and Glicko's RD/volatility path is
-- not linear, so their corrected rating is an approximation good to a few
-- points. RD and volatility are deliberately left alone: they encode
-- uncertainty about the player, they are bounded, and inventing values for them
-- would be less honest than leaving the ones the real match history produced.
--
-- Historical rating_before / rating_after on LATER matches are also left as
-- they were. They are a record of what the ladder actually showed at the time.
--
-- ── EXPECTED EFFECT (verified against production 2026-08-20) ───────────────
--   SpineOfGlass   1375.0 -> 1555.5   (+180.5)   no later rated FFA: exact
--   skypie2654     1544.5 -> 1663.8   (+119.3)   4 later games: approximate
--   Sewer_Gremlin  1348.8 -> 1462.0   (+113.2)   no later rated FFA: exact
--   Sid            1985.4 -> 2049.3   ( +63.9)   no later rated FFA: exact
--   pskittle100    1423.3 -> 1474.5   ( +51.2)   no later rated FFA: exact
--   Archnith       1564.6 -> 1603.8   ( +39.2)   26 later games: approximate
--   Nic            1299.3 -> 1325.7   ( +26.4)   two rows; 39/17 later games
--   New_eden84     1213.2 -> 1236.1   ( +22.9)   4 later games: approximate
--   Xgamergoodman  1301.5 -> 1231.7   ( -69.8)   4 later games: approximate
--
-- Xgamergoodman is the one player this COSTS. They left an 2026-08-18 game with
-- an empty line and Glicko still paid them +69.8, because placing 5th of 6 in a
-- field rated far above them beats expectation. The rule has to cut both ways:
-- a game nobody can be rated on is not a game you get to keep the points from.
--
-- Peak movement, dry-run against production: none of the nine peaks change
-- except pskittle100's, which rises 1474.4 -> 1474.5 because the reversal puts
-- them a hair above their old high-water mark. Xgamergoodman keeps a peak of
-- 1301.5 even though their rating drops to 1231.7 — that peak was set by a
-- LATER game, which the step-4 recompute (correctly) still counts. That later
-- game was itself rated from the polluted starting point, which is the
-- approximation this file already declares above, not a separate error.
--
-- Idempotent: the selection requires NOT absent, and step 3 sets absent. A
-- second run finds nothing.

BEGIN;

-- ── 1. Freeze the affected set before anything mutates it. ────────────────
CREATE TEMP TABLE _ffa_grace_fix ON COMMIT DROP AS
SELECT fmp.match_id,
       fmp.player_id,
       fmp.rating_change,
       fmp.placement
  FROM ffa_match_players fmp
  JOIN ffa_matches m ON m.id = fmp.match_id
 WHERE fmp.left_early
   AND NOT fmp.absent
   AND fmp.rating_change IS NOT NULL
   AND fmp.rounds_won   = 0
   AND fmp.points_total = 0
   AND fmp.kills        = 0
   AND COALESCE(fmp.damage_dealt, 0) = 0
   AND m.is_ranked
   AND m.invalidated_at IS NULL
     -- Pre-fix games only. From migration 233 on, the server decides this
     -- live from game_points_at_leave and no row should ever qualify again.
   AND m.ended_at < TIMESTAMPTZ '2026-08-21 00:00:00+00';

-- Expect 10 rows / 9 players. A wildly different count means the selection
-- drifted — read it before letting the rest of the file run.
SELECT COUNT(*) AS rows_to_fix,
       COUNT(DISTINCT player_id) AS players_affected,
       ROUND(SUM(rating_change)::numeric, 1) AS net_rating_removed
  FROM _ffa_grace_fix;

-- ── 2. Reverse the rating and the counters. ───────────────────────────────
UPDATE glicko_ratings_ffa g
   SET rating        = g.rating - agg.delta,
       games_played  = GREATEST(0, g.games_played  - agg.n),
       placement_sum = GREATEST(0, g.placement_sum - agg.place_sum),
       top3          = GREATEST(0, g.top3 - agg.n_top3),
       wins          = GREATEST(0, g.wins - agg.n_wins),
       updated_at    = NOW()
  FROM (SELECT player_id,
               SUM(rating_change)                      AS delta,
               COUNT(*)                                AS n,
               SUM(placement)                          AS place_sum,
               COUNT(*) FILTER (WHERE placement <= 3)  AS n_top3,
               COUNT(*) FILTER (WHERE placement  = 1)  AS n_wins
          FROM _ffa_grace_fix
         GROUP BY player_id) agg
 WHERE g.player_id = agg.player_id;

-- ── 3. Mark the rows unrated. Mirrors exactly what submit_ffa_match now
--      writes for a graced leaver: absent set, rating_after / rating_change
--      NULL, rating_before kept (it is what they carried into the game).
--      game_points_at_leave stays NULL — it was never reported, and NULL is
--      the honest value for "not reported" (see migration 233).
UPDATE ffa_match_players fmp
   SET absent        = TRUE,
       rating_after  = NULL,
       rating_change = NULL
  FROM _ffa_grace_fix f
 WHERE fmp.match_id  = f.match_id
   AND fmp.player_id = f.player_id;

-- ── 4. Peak: recompute from the rows that are still rated, never raising it
--      above what the player actually reached. COALESCE covers a player whose
--      only rated row was the voided one.
UPDATE glicko_ratings_ffa g
   SET peak_rating = GREATEST(
         g.rating,
         COALESCE((SELECT MAX(f2.rating_after)
                     FROM ffa_match_players f2
                     JOIN ffa_matches m2 ON m2.id = f2.match_id
                    WHERE f2.player_id = g.player_id
                      AND NOT f2.absent
                      AND f2.rating_after IS NOT NULL
                      AND m2.invalidated_at IS NULL), g.rating))
 WHERE g.player_id IN (SELECT player_id FROM _ffa_grace_fix);

-- ── 5. Verification — read this before COMMIT lands. ──────────────────────
SELECT p.display_name,
       ROUND(g.rating::numeric, 1)      AS new_rating,
       ROUND(g.peak_rating::numeric, 1) AS new_peak,
       g.games_played
  FROM glicko_ratings_ffa g
  JOIN players p ON p.id = g.player_id
 WHERE g.player_id IN (SELECT player_id FROM _ffa_grace_fix)
 ORDER BY p.display_name;

-- Must return 0: nothing may still be selectable by the rule.
SELECT COUNT(*) AS should_be_zero
  FROM ffa_match_players fmp
  JOIN ffa_matches m ON m.id = fmp.match_id
 WHERE fmp.left_early AND NOT fmp.absent
   AND fmp.rating_change IS NOT NULL
   AND fmp.rounds_won = 0 AND fmp.points_total = 0
   AND fmp.kills = 0 AND COALESCE(fmp.damage_dealt, 0) = 0
   AND m.is_ranked AND m.invalidated_at IS NULL
   AND m.ended_at < TIMESTAMPTZ '2026-08-21 00:00:00+00';

COMMIT;
