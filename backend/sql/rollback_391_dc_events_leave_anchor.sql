-- rollback_391_dc_events_leave_anchor.sql
-- Roll back migration 391 only after the api code that writes
-- dc_events.leave_anchor_at has been rolled back. NOT a release-train
-- migration. Explicit transaction (learning #340).
-- DEPLOY ORDER: THE API FIRST (roll back the writer), then this file.
-- lock_timeout bounds the wait for the lock, statement_timeout the DROP,
-- idle_in_transaction_session_timeout how long a runner stopped before
-- COMMIT can keep the table locked; one statement between them and COMMIT.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '30s';

ALTER TABLE dc_events
    DROP COLUMN IF EXISTS leave_anchor_at;

COMMIT;
