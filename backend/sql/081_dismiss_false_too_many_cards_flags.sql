-- 081_dismiss_false_too_many_cards_flags.sql
-- All five existing 'too_many_cards' flags are false positives. ROUNDS
-- arms-race rules: BOTH players auto-pick a card pre-match, then only
-- the loser picks after each round. The legitimate maximum picks for a
-- player is `rounds_lost + 1`. Audit confirmed every flagged match's
-- 6-pick player exactly matches that formula:
--   33971dd5: nite_shades lost 5 -> 6 picks
--   6317d191: Drewgames15 lost 5 -> 6 picks
--   7b5ab430: Aniimoo lost 5 -> 6 picks
--   85dbb6b7: Capitan Rex lost 5 -> 6 picks
--   8bd4a480: 'c' lost 5 -> 6 picks
-- Companion app fix bumps ANTICHEAT_MAX_CARDS_PER_PLAYER 5 -> 7 and
-- demotes the flag to advisory-only. This migration cleans up the
-- existing false flags + reverses the auto-invalidations.

-- 1. Mark all five too_many_cards flags reviewed as false_positive.
UPDATE flagged_matches
   SET reviewed_at = NOW(),
       reviewed_by_steam_id = '76561198040410653',
       review_action = 'false_positive'
 WHERE flag_reason = 'too_many_cards'
   AND reviewed_at IS NULL;

-- 2. Reverse the auto-invalidation on the matches themselves so they
--    re-appear in players' history + leaderboards. Only matches whose
--    sole invalidation reason was 'too_many_cards' get cleared; matches
--    flagged for additional reasons keep the other reasons intact.
UPDATE matches
   SET invalidated_at = NULL,
       invalidation_reason = NULL
 WHERE id IN (
     SELECT match_id FROM flagged_matches
      WHERE flag_reason = 'too_many_cards'
   )
   AND invalidation_reason = 'too_many_cards';

-- 3. The matches table doesn't have rating_change rolled back the same
--    way team_series does, but gold/xp reversals were inserted as
--    GoldTransaction rows with reason='reversal'. Re-reverse those by
--    inserting offset rows so player balances re-credit the original
--    values. Only matches that 'too_many_cards' alone invalidated.
WITH affected_matches AS (
    SELECT match_id FROM flagged_matches WHERE flag_reason = 'too_many_cards'
),
reversal_txns AS (
    SELECT player_id, amount, reference_id
      FROM gold_transactions
     WHERE reason = 'reversal'
       AND reference_id IN (SELECT match_id::text FROM affected_matches)
)
INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
SELECT player_id, -amount, 'reversal_undo', reference_id
  FROM reversal_txns;

-- 4. Re-credit gold_earned on players for the un-reversed amounts.
WITH affected_matches AS (
    SELECT match_id FROM flagged_matches WHERE flag_reason = 'too_many_cards'
),
reversal_sums AS (
    SELECT player_id, SUM(-amount) AS to_recredit
      FROM gold_transactions
     WHERE reason = 'reversal'
       AND reference_id IN (SELECT match_id::text FROM affected_matches)
     GROUP BY player_id
)
UPDATE players p
   SET gold_earned = COALESCE(gold_earned, 0) + rs.to_recredit
  FROM reversal_sums rs
 WHERE rs.player_id = p.id;

-- 5. Restore total_xp using the matches.p1_xp_gained / p2_xp_gained
--    fields (the reversal had subtracted these). Match each player on
--    each affected match by p1/p2 slot.
WITH affected AS (
    SELECT m.id, m.player1_id, m.player2_id, m.p1_xp_gained, m.p2_xp_gained
      FROM matches m
      JOIN flagged_matches fm ON fm.match_id = m.id
     WHERE fm.flag_reason = 'too_many_cards'
)
UPDATE players p
   SET total_xp = COALESCE(total_xp, 0) + COALESCE(a.xp_to_restore, 0)
  FROM (
      SELECT player1_id AS pid, p1_xp_gained AS xp_to_restore FROM affected
      UNION ALL
      SELECT player2_id, p2_xp_gained FROM affected
  ) a
 WHERE a.pid = p.id AND a.xp_to_restore IS NOT NULL AND a.xp_to_restore > 0;
