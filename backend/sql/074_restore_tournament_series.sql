-- 074_restore_tournament_series.sql
-- _prune_stale_series swept the active async tournament's WB R1 series
-- rows on 2026-05-01 because they were >30min old with no matches
-- reported (the players hadn't met up yet — async tournaments have a
-- 7-day match deadline). The prune query has been updated to exclude
-- is_tournament=TRUE rows; this migration restores the rows that were
-- already swept before the fix.

UPDATE ranked_series
   SET status = 'active',
       invalidated_at = NULL,
       invalidation_reason = NULL
 WHERE is_tournament = TRUE
   AND status = 'abandoned'
   AND invalidation_reason = 'no_match_reported';
