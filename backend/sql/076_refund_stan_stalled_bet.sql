-- 076_refund_stan_stalled_bet.sql
-- Refund Stan's 2000g bet on series 4e320959-c255-4794-a76b-3d47b8c94271
-- (Sundavar vs ImaMageBro, May 3rd). One match was played (5-2 in
-- ImaMageBro's favor) and then the players never finished the BO3 —
-- series sat at status='active', score 0-1, last match 4 days ago.
-- _prune_stale_series didn't catch it because that path only handles
-- "0 matches reported in 30 min"; this case is "1+ matches reported,
-- then stalled". Also sweeps the other 5 stuck series we found globally
-- in the same audit. The /series/active endpoint logic is updated
-- separately so future stalled series get auto-pruned + auto-refunded.

-- 1. Refund Stan's bet (settle with payout = stake, decrement gold_spent,
--    insert gold_transaction record).
WITH stan AS (
    SELECT id FROM players WHERE steam_id = '76561198983423367'
)
UPDATE players
   SET gold_spent = GREATEST(0, gold_spent - 2000)
 WHERE id = (SELECT id FROM stan);

INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
SELECT p.id, 2000, 'refund_abandoned', '4e320959-c255-4794-a76b-3d47b8c94271'
  FROM players p WHERE p.steam_id = '76561198983423367';

UPDATE bets
   SET settled_at = NOW(),
       payout = amount
 WHERE id = 23
   AND settled_at IS NULL;

-- 2. Mark the stalled series abandoned for the audit trail. The same
--    invalidation_reason is used by the prune path being updated
--    separately so historical reads stay consistent.
UPDATE ranked_series
   SET status = 'abandoned',
       invalidated_at = NOW(),
       invalidation_reason = 'series_stalled_post_match'
 WHERE status = 'active'
   AND is_tournament = FALSE
   AND id IN (
       '6a9cdf4d-8a59-43d6-8ea9-4b732cee9f8f',
       '6566d3e9-c3b5-43ba-add9-7f52bf789d9b',
       '4e320959-c255-4794-a76b-3d47b8c94271',
       'ccf9bf67-2b49-41a3-8ad0-17863bca54ab',
       '3fea0459-de24-49c4-bd4c-099109becb0c',
       '15cbee0b-dff9-4c5e-9be4-cd75691c7d34'
   );
