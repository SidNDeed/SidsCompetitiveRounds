-- 091_backfill_level_rewards.sql
--
-- v1.26.8 introduces level rewards: 100g per 5 levels through 50, then
-- 500g per 5 levels 55-100. Awarded on level-up going forward via the
-- post-XP-grant block in submit_match + submit_team_match. This migration
-- backfills the equivalent grant for players who already passed those
-- milestones, with a single audit row per player.
--
-- The level→XP formula in the API (xp_for_level/total_xp_for_level) is
-- expressed in Python; here we replicate it as a SQL CTE. The numbers
-- match xp_for_level(n) = 100 * (n+9) — confirmed by reading the Python
-- helper at backend/api/main.py.

BEGIN;

-- Players' current cumulative total_xp → level. xp_for_level(n) = 100*(n+9).
-- cumulative_xp(L) = 100 * sum_{n=1..L}(n+9) = 100 * (L*(L+1)/2 + 9*L) = 100*L*(L+19)/2 = 50*L*(L+19).
-- Solve for max L where 50*L*(L+19) <= total_xp -> use floor; capped at 100.
CREATE TEMP TABLE _player_level AS
SELECT p.id AS player_id,
       LEAST(100, GREATEST(0, FLOOR(
           (-19 + SQRT(361.0 + 4.0 * (p.total_xp::float / 50.0))) / 2.0
       )::int)) AS cur_level
  FROM players p
 WHERE COALESCE(p.total_xp, 0) >= 0;

-- For each player, total level-reward gold owed = sum over multiples of 5.
-- Bands 5..50: 100g each (10 bands × 100g = 1000g if at level 50).
-- Bands 55..100: 500g each (10 bands × 500g = 5000g if at level 100).
CREATE TEMP TABLE _backfill AS
SELECT player_id,
       cur_level,
       -- under-50 bands count
       LEAST(10, GREATEST(0, cur_level / 5)) * 100
       -- over-50 bands count
       + GREATEST(0, (LEAST(100, cur_level) - 50) / 5) * 500 AS owed_gold
  FROM _player_level;

-- Subtract what they already have (e.g. from any prior level_reward grants,
-- though none exist yet pre-091).
CREATE TEMP TABLE _existing AS
SELECT player_id, COALESCE(SUM(amount), 0) AS already_paid
  FROM gold_transactions
 WHERE reason = 'level_reward'
 GROUP BY player_id;

CREATE TEMP TABLE _to_grant AS
SELECT b.player_id,
       b.cur_level,
       b.owed_gold - COALESCE(e.already_paid, 0) AS delta
  FROM _backfill b
  LEFT JOIN _existing e ON e.player_id = b.player_id
 WHERE b.owed_gold - COALESCE(e.already_paid, 0) > 0;

-- Credit the players.
UPDATE players p
   SET gold_earned = COALESCE(p.gold_earned, 0) + g.delta
  FROM _to_grant g
 WHERE p.id = g.player_id;

-- Single audit row per backfilled player, reference_id labels the migration.
INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
SELECT player_id, delta, 'level_reward', 'backfill_091'
  FROM _to_grant;

DO $$
DECLARE n INT;
        total INT;
BEGIN
    SELECT COUNT(*), COALESCE(SUM(delta), 0) INTO n, total FROM _to_grant;
    RAISE NOTICE 'backfill_level_rewards: granted to % players (% gold total)', n, total;
END $$;

DROP TABLE _to_grant;
DROP TABLE _existing;
DROP TABLE _backfill;
DROP TABLE _player_level;

COMMIT;
