-- 067_grant_lopidav_gold.sql
-- One-shot 20,000g grant to lopidav (76561198041616199), per Sid's request.

WITH lopi AS (
    SELECT id FROM players WHERE steam_id = '76561198041616199'
)
INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
SELECT id, 20000, 'admin_grant', 'lopidav_20k'
FROM lopi;

UPDATE players
SET gold_earned = gold_earned + 20000
WHERE steam_id = '76561198041616199';
