-- 089_cleanup_duplicate_tournaments.sql
--
-- A long-standing race in tournament_tick's _ensure_next_tournament has been
-- producing duplicate (kind, status='voting') rows when two ticks land at
-- the same instant — most likely during container recreate where the old
-- and new API instances briefly overlap. Two duplicate sync rows have been
-- sitting since 2026-04-25; the new async cadence change just produced a
-- new async pair on first cron tick.
--
-- This migration:
--   1) Cancels the duplicate with zero signups (keeping the one with users).
--   2) Adds a partial unique index so future double-inserts hit a constraint
--      violation and bubble up via the supervised wrapper instead of
--      silently producing twin tournaments.

BEGIN;

-- Cancel the duplicate sync tournament (the one with no signups).
UPDATE tournaments
   SET status = 'cancelled',
       ended_at = COALESCE(ended_at, NOW())
 WHERE id = 'b1a1fc48-26b0-4ee8-918c-c4280237fb5f'
   AND status = 'voting'
   AND NOT EXISTS (SELECT 1 FROM tournament_signups WHERE tournament_id = 'b1a1fc48-26b0-4ee8-918c-c4280237fb5f');

-- Cancel the duplicate async tournament (later-created of the freshly-spawned pair).
UPDATE tournaments
   SET status = 'cancelled',
       ended_at = COALESCE(ended_at, NOW())
 WHERE id = '9ad5fecc-14b7-46a8-a19a-44b2ec0f41db'
   AND status = 'voting'
   AND NOT EXISTS (SELECT 1 FROM tournament_signups WHERE tournament_id = '9ad5fecc-14b7-46a8-a19a-44b2ec0f41db');

-- Partial unique index: at most one tournament per kind in any pre-completion
-- status. Stops the race at the DB layer so the cron's INSERT will hit
-- IntegrityError instead of silently double-creating.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_tournaments_active_per_kind
    ON tournaments(kind)
 WHERE status IN ('voting', 'locked', 'running');

COMMIT;
