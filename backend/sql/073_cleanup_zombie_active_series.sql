-- 073_cleanup_zombie_active_series.sql
-- One-shot cleanup. Before today's RankedSeries-model fix (added
-- tournament_id / is_tournament / is_private columns), start_tournament
-- raised on every cron tick and many ranked_series rows from queue
-- preflights, private rooms, and previous tournament attempts ended up
-- stuck in status='active' forever — never advanced, never invalidated,
-- never completed. They don't surface in /api/v1/series/active because
-- of the 2-hour created_at filter, but they pollute the table and
-- inflate the count of "live" series for any historical query that
-- doesn't time-bound.
--
-- This migration marks any active series older than 4 hours as
-- 'abandoned' so the active count reflects reality. The cutoff is
-- generous — even a long BO3 with multiple disconnect-pause windows
-- is well under 2 hours, so 4h is a clear "no human is still in this"
-- threshold.

UPDATE ranked_series
   SET status = 'abandoned',
       invalidated_at = NOW(),
       invalidation_reason = 'zombie_pre_v1.26.5_cleanup'
 WHERE status = 'active'
   AND created_at < NOW() - INTERVAL '4 hours';
