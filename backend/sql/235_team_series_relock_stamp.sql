-- 235: team_series.relocked_at — when the DC-resume family resolver last
-- re-locked this series onto a fresh assembly (bug 245, review r2 HIGH 1).
--
-- Why it exists: the resume clears the dead room, so a DEFERRED disconnect
-- report that still NAMES that room is rejected by the room fence — but an
-- old-client report carries NO room at all, and the server cannot tell a
-- delayed pre-resume report from a live one. This stamp is the server-owned
-- discriminator: report-dc ignores ROOMLESS reports arriving within the
-- post-relock window (a report about the resumed sitting's own play names
-- the new room; only a stale pre-resume report is roomless in that window).
--
-- DEPLOY ORDER: apply BEFORE the API deploy that reads it. The reader is
-- savepointed (#235 learning) so a reversed order degrades to "fence
-- inactive" rather than 500ing DC reports, but migration-first is the
-- correct order.
--
-- Idempotent statement-by-statement (#243: the wrapper's || retry re-runs
-- the whole file).

BEGIN;

ALTER TABLE team_series
    ADD COLUMN IF NOT EXISTS relocked_at timestamptz;

COMMIT;
