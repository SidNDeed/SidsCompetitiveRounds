-- 097_backfill_rating_history.sql
--
-- Backfill missing rating_history rows so the leaderboard graph shows every
-- ranked series, not just the ones completed after the inline-insert was
-- added in v1.26.8.
--
-- Current state (2026-05-30): 48 missing rows across 12 players. Sid has
-- 96 completed series but only 85 rating_history rows — gap from April 11-13,
-- the first batch of ranked series ever played, predating the inline rating
-- snapshot. The weekly cron only catches active players, so dormant gaps
-- stay forever.
--
-- Method: for each player, walk their completed ranked series in chronological
-- order and compute cumulative rating from 1500 + cumulative deltas. Insert
-- a rating_history row at each series' completed_at IF none already exists
-- within a 30s window. Verified for Sid: 1500 + sum(deltas) = 2136.6 vs actual
-- 2136.4 (drift from rounding) — deltas reconstruct rating accurately.
--
-- RD and volatility are not stored on ranked_series, so we use defaults (RD=100,
-- volatility=0.06). These are reasonable for historic entries that the graph
-- only reads `rating` from anyway.

WITH series_with_deltas AS (
    SELECT
        rs.id AS series_id,
        rs.completed_at,
        p.id AS pid,
        CASE
            WHEN rs.player1_id = p.id THEN COALESCE(rs.p1_rating_change, 0)
            ELSE COALESCE(rs.p2_rating_change, 0)
        END AS rating_change
    FROM ranked_series rs
    JOIN players p ON p.id IN (rs.player1_id, rs.player2_id)
    WHERE rs.completed_at IS NOT NULL
),
cumulative AS (
    SELECT
        series_id,
        completed_at,
        pid,
        1500.0 + SUM(rating_change) OVER (
            PARTITION BY pid ORDER BY completed_at
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS rating_after
    FROM series_with_deltas
)
INSERT INTO rating_history (player_id, rating, rating_deviation, volatility, period_end)
SELECT
    c.pid,
    c.rating_after,
    100.0,
    0.06,
    c.completed_at
FROM cumulative c
WHERE NOT EXISTS (
    SELECT 1 FROM rating_history rh
    WHERE rh.player_id = c.pid
      AND ABS(EXTRACT(EPOCH FROM (rh.period_end - c.completed_at))) < 30
);
