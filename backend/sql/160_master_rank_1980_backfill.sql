-- 160: July 28 rank reorganization — Master achievement threshold moves
--      2030 -> 1980 (new Master I floor). Backfill the achievement + its
--      500g unlock reward (master_rank's ACHIEVEMENT_GOLD_OVERRIDES tier,
--      set by migration 138 — NOT the uniform 100g) for everyone whose PEAK
--      1v1/2v2 rating already clears the new bar (same "reach" semantics +
--      peak source as migration 113's rating backfill).
-- Idempotent: ON CONFLICT DO NOTHING; gold is paid only for rows actually
-- inserted by THIS run.

BEGIN;

CREATE TEMP TABLE _master_new (player_id UUID) ON COMMIT DROP;

WITH peaks AS (
    SELECT COALESCE(gr.player_id, g2.player_id) AS player_id,
           GREATEST(COALESCE(gr.peak_rating, 0), COALESCE(g2.peak_rating, 0)) AS peak
    FROM glicko_ratings gr
    FULL OUTER JOIN glicko_ratings_2v2 g2 ON g2.player_id = gr.player_id
),
ins AS (
    INSERT INTO player_achievements (player_id, achievement_key, unlocked_at)
    SELECT p.player_id, 'master_rank', NOW()
    FROM peaks p
    JOIN players pl ON pl.id = p.player_id
    WHERE p.peak >= 1980.0
    ON CONFLICT (player_id, achievement_key) DO NOTHING
    RETURNING player_id
)
INSERT INTO _master_new SELECT player_id FROM ins;

INSERT INTO gold_transactions (player_id, amount, reason, reference_id, created_at)
SELECT player_id, 500, 'achievement', 'master_rank', NOW() FROM _master_new;

UPDATE players p
SET gold_earned = COALESCE(p.gold_earned, 0) + 500
FROM _master_new n
WHERE p.id = n.player_id;

COMMIT;
