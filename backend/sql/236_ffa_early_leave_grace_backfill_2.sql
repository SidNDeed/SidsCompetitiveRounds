-- 236_ffa_early_leave_grace_backfill_2.sql
-- Second pass of migration 234, same rule, new window. The live grace
-- (migration 233 + main.py's game_points_at_leave path) is still INERT in
-- production because no shipped client release contains the sender
-- (fc2f684 is not in v1.39.0) — so games played AFTER 234's cutoff can
-- still charge Elo to a player who left before anything was decided.
-- Sid asked for the latest games to be fixed manually (2026-08-21).
--
-- METHOD: migration 234 verbatim — read its header for the full proxy
-- rationale (entirely-empty stat line incl. damage_dealt on a left_early
-- row), the deliberate asymmetries (stayers untouched, XP/gold untouched),
-- and the accuracy notes (exact for players with no later rated FFA,
-- approximate otherwise; RD/volatility left alone). Only the time window
-- differs: [234's cutoff, this file's authoring moment).
--
-- ── EXPECTED EFFECT (verified against production 2026-08-22) ─────────────
-- Exactly ONE game qualifies: 668dd4aa-89ba-48e1-8989-3c9693b2220a
-- (2026-08-21 21:27 UTC, 9 players, room ffa_7f95a764cd13_211312_r2) —
-- three leavers tied 7th with identical all-zero lines, the "game broke at
-- the start" signature 234's header describes. Expect 3 rows / 3 players /
-- net_rating_removed = -55.3:
--   Archnith  1618.1 -> 1629.2  (+11.1)  3 later rated games: approximate
--   Sid       1993.4 -> 2042.1  (+48.7)  3 later rated games: approximate
--   Nic       1318.6 -> 1314.1  ( -4.5)  no later rated FFA: exact
-- Nic is this pass's Xgamergoodman (see 234's header): Glicko paid him for
-- placing 7th of 9 in a field rated above him, in a game nobody can be
-- rated on. The rule cuts both ways.
-- Peaks: all three reversed ratings sit below current peaks — step 4 is
-- expected to be a no-op, kept for fidelity with 234.
--
-- STANDING CAVEAT: until a client release ships the game_points_at_leave
-- sender, any ranked FFA game played after this file's upper bound can
-- re-create identical rows. This same mirror (bump both bounds) is safe to
-- run once more for that residual window — the NOT absent guard keeps
-- every run idempotent.

BEGIN;

-- ── 1. Freeze the affected set before anything mutates it. ────────────────
CREATE TEMP TABLE _ffa_grace_fix2 ON COMMIT DROP AS
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
     -- 234 covered everything before its cutoff; this pass covers the gap
     -- from that cutoff to this file's authoring moment.
   AND m.ended_at >= TIMESTAMPTZ '2026-08-21 00:00:00+00'
   AND m.ended_at <  TIMESTAMPTZ '2026-08-22 04:30:00+00';

-- Expect 3 rows / 3 players / -55.3. A wildly different count means the
-- selection drifted — read it before letting the rest of the file run.
SELECT COUNT(*) AS rows_to_fix,
       COUNT(DISTINCT player_id) AS players_affected,
       ROUND(SUM(rating_change)::numeric, 1) AS net_rating_removed
  FROM _ffa_grace_fix2;

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
          FROM _ffa_grace_fix2
         GROUP BY player_id) agg
 WHERE g.player_id = agg.player_id;

-- ── 3. Mark the rows unrated (mirrors submit_ffa_match's graced write:
--      absent set, rating_after / rating_change NULL, rating_before kept,
--      game_points_at_leave stays NULL = honestly "not reported"). ────────
UPDATE ffa_match_players fmp
   SET absent        = TRUE,
       rating_after  = NULL,
       rating_change = NULL
  FROM _ffa_grace_fix2 f
 WHERE fmp.match_id  = f.match_id
   AND fmp.player_id = f.player_id;

-- ── 4. Peak: recompute from the rows that are still rated. ────────────────
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
 WHERE g.player_id IN (SELECT player_id FROM _ffa_grace_fix2);

-- ── 5. Verification — read this before COMMIT lands. ──────────────────────
SELECT p.display_name,
       ROUND(g.rating::numeric, 1)      AS new_rating,
       ROUND(g.peak_rating::numeric, 1) AS new_peak,
       g.games_played
  FROM glicko_ratings_ffa g
  JOIN players p ON p.id = g.player_id
 WHERE g.player_id IN (SELECT player_id FROM _ffa_grace_fix2)
 ORDER BY p.display_name;

-- Must return 0: nothing may still be selectable by the rule in-window.
SELECT COUNT(*) AS should_be_zero
  FROM ffa_match_players fmp
  JOIN ffa_matches m ON m.id = fmp.match_id
 WHERE fmp.left_early AND NOT fmp.absent
   AND fmp.rating_change IS NOT NULL
   AND fmp.rounds_won = 0 AND fmp.points_total = 0
   AND fmp.kills = 0 AND COALESCE(fmp.damage_dealt, 0) = 0
   AND m.is_ranked AND m.invalidated_at IS NULL
   AND m.ended_at >= TIMESTAMPTZ '2026-08-21 00:00:00+00'
   AND m.ended_at <  TIMESTAMPTZ '2026-08-22 04:30:00+00';

COMMIT;
