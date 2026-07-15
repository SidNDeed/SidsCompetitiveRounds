-- 123_slayer_gold_and_podium_title.sql
--
-- v1.32, part 1: the slayer achievements (Sid Slayer / Stan Slayer) now pay
-- 1000g instead of the uniform 100g (ACHIEVEMENT_GOLD_OVERRIDES in main.py).
-- Top up every EXISTING earner to the full 1000g — one row per earned slayer
-- achievement, so a player who earned both gets two topup rows. The delta is
-- 1000 minus whatever their original unlock actually paid, because the prod
-- ledger is uneven (verified July 14): of 7 earners, 3 have an original
-- 'achievement' payout row (25g pre-v1.22.6 or 100g) and 4 have NONE — the
-- migration-102 backfill inserted their achievement rows without paying gold.
-- A flat +900 would have left them at 900/925/1000 unevenly; the delta lands
-- everyone at exactly 1000 per slayer achievement, matching future earners.
-- Idempotency: the topup ledger rows use reference_id '<key>_topup' (distinct
-- from the original '<key>' payout rows), guarded by NOT EXISTS on
-- (player_id, reason='achievement', reference_id='<key>_topup'), and deltas
-- <= 0 are dropped — re-running is a no-op, and a future earner already paid
-- 1000 inline can never be topped up. Pattern follows
-- 113_achievement_backfill.sql.
--
-- v1.32, part 2: seed the dynamic 'Podium' title (sku title_podium) — held by
-- the current top 3 of the ranked leaderboard. rotation_pool='achievement'
-- keeps it out of the public shop listing AND blocks the purchase endpoint
-- (the 403 gate keys on that value); the API auto-grants ownership when a
-- player enters the podium and resolves the display text/color at render
-- time (1st/2nd/3rd Place, hidden while off the podium).

BEGIN;

-- ── Part 1: slayer gold top-up (to 1000g per earned slayer achievement) ────

CREATE TEMP TABLE _slayer_topup ON COMMIT DROP AS
SELECT pa.player_id,
       pa.achievement_key AS key,
       1000 - COALESCE((
           SELECT SUM(gt0.amount) FROM gold_transactions gt0
           WHERE gt0.player_id = pa.player_id
             AND gt0.reason = 'achievement'
             AND gt0.reference_id = pa.achievement_key
       ), 0) AS delta
FROM player_achievements pa
WHERE pa.achievement_key IN ('regicide', 'stan_slayer')
  AND NOT EXISTS (
      SELECT 1 FROM gold_transactions gt
      WHERE gt.player_id = pa.player_id
        AND gt.reason = 'achievement'
        AND gt.reference_id = pa.achievement_key || '_topup'
  );

-- Already at (or above) the new rate — nothing to pay.
DELETE FROM _slayer_topup WHERE delta <= 0;

INSERT INTO gold_transactions (player_id, amount, reason, reference_id, created_at)
SELECT player_id, delta, 'achievement', key || '_topup', NOW()
FROM _slayer_topup;

UPDATE players p
SET gold_earned = COALESCE(p.gold_earned, 0) + s.total
FROM (SELECT player_id, SUM(delta) AS total FROM _slayer_topup GROUP BY 1) s
WHERE p.id = s.player_id;

-- ── Part 2: dynamic 'Podium' title seed ─────────────────────────────────────

INSERT INTO shop_items (sku, kind, name, description, price, rarity, rotation_pool, preview_color)
SELECT 'title_podium', 'title', 'Podium',
       'Held by the top 3 on the ranked leaderboard',
       0, 'legendary', 'achievement', '#FFD700'
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'title_podium');

-- ── Summary (visible in /migrate output) ────────────────────────────────────

SELECT key, COUNT(*) AS earners_topped_up, SUM(delta) AS gold_paid
FROM _slayer_topup
GROUP BY 1
ORDER BY 1;

SELECT sku, kind, name, price, rarity, rotation_pool
FROM shop_items WHERE sku = 'title_podium';

COMMIT;
