-- rollback_391_dc_events_leave_anchor.sql
-- Roll back migration 391 only after the api code that writes
-- dc_events.leave_anchor_at has been rolled back. NOT a release-train
-- migration. Explicit transaction (learning #340).
-- DEPLOY ORDER: THE API FIRST (roll back the writer), then this file.

BEGIN;
SET LOCAL lock_timeout = '5s';

ALTER TABLE dc_events
    DROP COLUMN IF EXISTS leave_anchor_at;

COMMIT;
