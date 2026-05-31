-- 088_fix_team_sweep_criteria.sql
--
-- v1.26.7 shipped the Tag Team Sweep achievement against the wrong criterion
-- — it fired on a 2-0 series win when it was supposed to fire on a 5-0 game
-- (round shutout) within a single 2v2 match. v1.26.8 server fix moves the
-- detection per-match against rounds_won == 5/0; this migration revokes the
-- grants that don't satisfy the new criterion and refunds the 100g bonus
-- (each grant came with ACHIEVEMENT_GOLD = 100).
--
-- Players who happen to ALSO have a real 5-0 game stay credited — they
-- meet both criteria so re-revoke would be churn.

BEGIN;

-- Identify holders of team_sweep who don't have a real 5-0 game win.
CREATE TEMP TABLE _bad_team_sweep AS
SELECT pa.id   AS achievement_id,
       pa.player_id
  FROM player_achievements pa
 WHERE pa.achievement_key = 'team_sweep'
   AND NOT EXISTS (
       SELECT 1 FROM team_matches tm
        WHERE (
              (tm.t1_rounds_won = 5 AND tm.t2_rounds_won = 0 AND pa.player_id IN (tm.t1a_id, tm.t1b_id))
           OR (tm.t2_rounds_won = 5 AND tm.t1_rounds_won = 0 AND pa.player_id IN (tm.t2a_id, tm.t2b_id))
       )
   );

-- Refund the 100g per affected player.
UPDATE players p
   SET gold_earned = GREATEST(0, COALESCE(p.gold_earned, 0) - 100)
  FROM _bad_team_sweep b
 WHERE p.id = b.player_id;

-- Record the reversal as a negative gold_transactions row so the audit trail
-- is symmetric.
INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
SELECT player_id, -100, 'achievement_revoked', 'team_sweep'
  FROM _bad_team_sweep;

-- Drop the achievement rows themselves.
DELETE FROM player_achievements
 WHERE id IN (SELECT achievement_id FROM _bad_team_sweep);

-- Report counts so the migration log shows the impact.
DO $$
DECLARE n INT;
BEGIN
    SELECT COUNT(*) INTO n FROM _bad_team_sweep;
    RAISE NOTICE 'fix_team_sweep_criteria: revoked % incorrect grants', n;
END $$;

DROP TABLE _bad_team_sweep;

COMMIT;
