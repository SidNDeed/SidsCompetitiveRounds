-- 057_grant_stan_gold.sql
-- Compensation grant of 500g to Stan (76561198983423367). Stan unlocked
-- achievements before the per-achievement gold reward was patched up to 100g,
-- so his historical unlocks paid less than the current rate. 500g makes him
-- whole vs. the current schedule.

WITH stan AS (
    SELECT id FROM players WHERE steam_id = '76561198983423367'
)
INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
SELECT id, 500, 'achievement_backpay', 'pre_100g_unlocks'
FROM stan;

UPDATE players
SET gold_earned = gold_earned + 500
WHERE steam_id = '76561198983423367';
