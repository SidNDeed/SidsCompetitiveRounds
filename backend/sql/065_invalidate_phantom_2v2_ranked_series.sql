-- v1.25.19 cleanup: phantom 1v1 ranked_series rows created from inside 2v2
-- (cr_ff) rooms by GameStateWatcher's series-preflight branch. The 2v2 flow
-- already has its own team_series row; the 1v1 preflight pollutes the live
-- bets panel and 1v1 stats.
--
-- A 2v2 phantom shows up as: an *active* 1v1 ranked_series with
--   - non-null live_p1_points/live_p2_points
--   - no completed matches linked (zero p1_series_wins / p2_series_wins)
--   - both players are in the team_queue / team_series cohort
-- The pattern is "active series with live points but no completed matches"
-- — that combo only happens when the preflight created the row but the
-- 2v2 match-report path took over and never wrote completed 1v1 matches.
--
-- Mark these as invalidated so they vanish from /series/active and from
-- recent-1v1 history. The associated bets (if any) need separate handling
-- — for now, none of these phantoms have bets placed on them yet.

UPDATE ranked_series
   SET status = 'cancelled',
       invalidated_at = NOW(),
       invalidation_reason = 'phantom_from_2v2_room'
 WHERE status = 'active'
   AND p1_series_wins = 0
   AND p2_series_wins = 0
   AND completed_at IS NULL
   AND id NOT IN (
       -- Don't touch real 1v1 series that just haven't completed game 1 yet.
       -- A 1v1 series in flight will have a corresponding *match* row even
       -- if no series-wins are tallied (matches roll up to series on game
       -- end). If matches.series_id references this row, it's a real series.
       SELECT DISTINCT series_id FROM matches WHERE series_id IS NOT NULL
   )
   AND created_at < NOW() - INTERVAL '5 minutes';
