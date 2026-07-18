-- 133_twins_achievement_backfill.sql — July 17 round 3 (Sid item 3)
--
-- Retroactive backfill for the new "twins" achievement: any historical game
-- where both players finished with the exact same 5-card multiset
-- (duplicate copies counted). Mirrors _grant_achievement_inline exactly
-- (player_achievements row + 100g gold_transactions + gold_earned bump,
-- paid only for NEW rows) — same pattern as 113_achievement_backfill.sql.
-- Card names normalize like _norm_card: UPPER + strip non-alphanumerics
-- (display vs GameObject spellings, learning #19). Idempotent via
-- ON CONFLICT (player_id, achievement_key) DO NOTHING.

BEGIN;

WITH per_player AS (
    -- One row per (match, player, normalized card): pick counts.
    SELECT mc.match_id,
           mc.player_id,
           UPPER(REGEXP_REPLACE(mc.card_name, '[^a-zA-Z0-9]', '', 'g')) AS norm,
           COUNT(*) AS n
    FROM match_cards mc
    WHERE COALESCE(mc.card_name, '') <> ''
    GROUP BY mc.match_id, mc.player_id, norm
),
per_side AS (
    -- One row per (match, player): total picks + a canonical build signature.
    SELECT match_id, player_id,
           SUM(n) AS total,
           STRING_AGG(norm || 'x' || n, '|' ORDER BY norm) AS build_sig
    FROM per_player
    GROUP BY match_id, player_id
),
twin_matches AS (
    -- Matches with exactly two 5-card sides sharing one build signature.
    SELECT match_id
    FROM per_side
    WHERE total = 5
    GROUP BY match_id
    HAVING COUNT(*) = 2 AND COUNT(DISTINCT build_sig) = 1
),
twin_players AS (
    SELECT DISTINCT ps.player_id
    FROM per_side ps
    JOIN twin_matches tm ON tm.match_id = ps.match_id
),
granted AS (
    INSERT INTO player_achievements (player_id, achievement_key)
    SELECT player_id, 'twins' FROM twin_players
    ON CONFLICT (player_id, achievement_key) DO NOTHING
    RETURNING player_id
),
paid AS (
    INSERT INTO gold_transactions (player_id, amount, reason, reference_id, created_at)
    SELECT player_id, 100, 'achievement', 'twins', NOW() FROM granted
    RETURNING player_id
)
UPDATE players p
SET gold_earned = COALESCE(p.gold_earned, 0) + 100
WHERE p.id IN (SELECT player_id FROM paid);

-- Sanity output: who has it now.
SELECT p.display_name, pa.unlocked_at
FROM player_achievements pa
JOIN players p ON p.id = pa.player_id
WHERE pa.achievement_key = 'twins'
ORDER BY pa.unlocked_at;

COMMIT;
