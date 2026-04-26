-- 055_grant_sid_gold.sql
-- Top-up grant of 50,000 gold to Sid (76561198040410653) so the new
-- player_color shop tier (3000-8000g) is testable without grinding XP.
-- Logged as a transaction so the gold ledger reconciles against gold_earned.

WITH sid AS (
    SELECT id FROM players WHERE steam_id = '76561198040410653'
)
INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
SELECT id, 50000, 'test_grant', 'qa_pcolor'
FROM sid;

UPDATE players
SET gold_earned = gold_earned + 50000
WHERE steam_id = '76561198040410653';
