-- 138_achievement_gold_tiers.sql — July 21
--
-- Backfill top-up for the new achievement gold tiers (1000/500/300; see
-- ACHIEVEMENT_GOLD_OVERRIDES in main.py). Clone of migration 123's shape,
-- with a distinct '_tier_topup' reference suffix so re-running this and any
-- future re-tier stay independent of 123's slayer '_topup' rows.
--
-- Delta-based: each earner is paid target minus everything already paid for
-- the key (counting reference_id IN (key, key||'_tier_topup')), so a partial
-- re-run can never double-pay and an earner with NO ledger row (mig-102-era
-- grant) gets the full amount. Slayers (regicide/stan_slayer) are excluded —
-- unchanged at 1000, already topped up by 123. Idempotent via the NOT EXISTS
-- guard + delta <= 0 delete.

BEGIN;
CREATE TEMP TABLE _tier_topup ON COMMIT DROP AS
SELECT pa.player_id, pa.achievement_key AS key, t.amt
       - COALESCE((SELECT SUM(gt0.amount) FROM gold_transactions gt0
                   WHERE gt0.player_id = pa.player_id AND gt0.reason = 'achievement'
                     AND gt0.reference_id IN (pa.achievement_key, pa.achievement_key || '_tier_topup')), 0) AS delta
FROM player_achievements pa
JOIN (VALUES ('master_rank',500),('team_sweep',500),('rise_from_the_ashes',500),
             ('casual_conqueror',500),('twins',500),('immortal',500),
             ('stacked_deck',300),('flawless',300),('silent_drill',300),
             ('deep_end',300),('casual_century',300),('unstoppable',300),
             ('grand_master',1000),('touch_grass',1000)) AS t(key, amt)
  ON t.key = pa.achievement_key
WHERE NOT EXISTS (SELECT 1 FROM gold_transactions gt
                  WHERE gt.player_id = pa.player_id AND gt.reason = 'achievement'
                    AND gt.reference_id = pa.achievement_key || '_tier_topup');
DELETE FROM _tier_topup WHERE delta <= 0;
INSERT INTO gold_transactions (player_id, amount, reason, reference_id, created_at)
SELECT player_id, delta, 'achievement', key || '_tier_topup', NOW() FROM _tier_topup;
UPDATE players p SET gold_earned = COALESCE(p.gold_earned,0) + s.total
FROM (SELECT player_id, SUM(delta) AS total FROM _tier_topup GROUP BY 1) s WHERE p.id = s.player_id;
SELECT key, COUNT(*) AS earners_topped_up, SUM(delta) AS gold_paid FROM _tier_topup GROUP BY 1 ORDER BY 1;
COMMIT;
