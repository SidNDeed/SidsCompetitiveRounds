-- 084_retroactive_grant_master_and_team_sweep.sql
--
-- Retroactive grant of the two v1.26.7 achievements to players who already
-- met the criteria before the detection code shipped:
--   master_rank — current rating >= 2000 in either 1v1 OR 2v2 Glicko
--   team_sweep  — won at least one completed 2v2 series 2-0
--
-- Idempotent via the (player_id, achievement_key) UNIQUE constraint.
-- Awards ACHIEVEMENT_GOLD (100g) per grant, mirroring the inline grant path.

BEGIN;

-- ── master_rank ─────────────────────────────────────────────
WITH eligible AS (
    SELECT p.id AS player_id, p.steam_id
      FROM players p
      LEFT JOIN glicko_ratings    g1 ON g1.player_id = p.id
      LEFT JOIN glicko_ratings_2v2 g2 ON g2.player_id = p.id
     WHERE COALESCE(g1.rating, 0) >= 2000 OR COALESCE(g2.rating, 0) >= 2000
),
inserted AS (
    INSERT INTO player_achievements (player_id, achievement_key)
    SELECT player_id, 'master_rank' FROM eligible
    ON CONFLICT (player_id, achievement_key) DO NOTHING
    RETURNING player_id
)
INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
SELECT player_id, 100, 'achievement', 'master_rank' FROM inserted;

UPDATE players p
   SET gold_earned = COALESCE(p.gold_earned, 0) + 100
  FROM player_achievements pa
 WHERE pa.player_id = p.id
   AND pa.achievement_key = 'master_rank'
   AND pa.unlocked_at >= NOW() - INTERVAL '1 minute';

-- ── team_sweep ──────────────────────────────────────────────
-- Every winning slot of a 2-0 team_series qualifies (both winners on the
-- winning team). DISTINCT to dedupe players who swept multiple times.
WITH eligible AS (
    SELECT DISTINCT p.id AS player_id
      FROM team_series ts
      JOIN players p ON p.id IN (
            CASE WHEN ts.winner_team = 1 THEN ts.t1a_id ELSE ts.t2a_id END,
            CASE WHEN ts.winner_team = 1 THEN ts.t1b_id ELSE ts.t2b_id END
      )
     WHERE ts.status = 'completed'
       AND ((ts.t1_series_wins = 2 AND ts.t2_series_wins = 0)
         OR (ts.t2_series_wins = 2 AND ts.t1_series_wins = 0))
),
inserted AS (
    INSERT INTO player_achievements (player_id, achievement_key)
    SELECT player_id, 'team_sweep' FROM eligible
    ON CONFLICT (player_id, achievement_key) DO NOTHING
    RETURNING player_id
)
INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
SELECT player_id, 100, 'achievement', 'team_sweep' FROM inserted;

UPDATE players p
   SET gold_earned = COALESCE(p.gold_earned, 0) + 100
  FROM player_achievements pa
 WHERE pa.player_id = p.id
   AND pa.achievement_key = 'team_sweep'
   AND pa.unlocked_at >= NOW() - INTERVAL '1 minute';

COMMIT;
