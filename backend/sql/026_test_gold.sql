-- 026_test_gold.sql
-- One-off test grant of 50,000 gold to Sid (steam_id 76561198040410653) so he
-- can actually afford to buy the high-tier titles/trails for end-to-end QA.
-- Logged as a normal transaction so the ledger still balances against gold_earned.

WITH sid AS (
    SELECT id FROM players WHERE steam_id = '76561198040410653'
)
INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
SELECT id, 50000, 'test_grant', 'qa'
FROM sid;

UPDATE players
SET gold_earned = gold_earned + 50000
WHERE steam_id = '76561198040410653';
