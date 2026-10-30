-- rollback_391_dc_events_leave_anchor.sql
-- Roll back migration 391 only after the api code that writes
-- dc_events.leave_anchor_at has been rolled back. NOT a release-train
-- migration. Explicit transaction (learning #340).
-- DEPLOY ORDER: THE API FIRST (roll back the writer), then this file.
-- lock_timeout bounds the wait for the lock, statement_timeout the DROP,
-- idle_in_transaction_session_timeout how long a runner stopped before
-- COMMIT can keep the table locked; one statement between them and COMMIT.
-- The hold bound is statement plus idle (separate budgets; PostgreSQL 16 has
-- no transaction_timeout): 25 s + 5 s = 30 s.
-- THE COMMIT. PostgreSQL disables the statement timer before it commits, so
-- the COMMIT's own wait is outside every timeout above. synchronous_commit
-- = local makes that wait the local WAL flush only, never a standby's
-- confirmation, whatever synchronous_standby_names says now or later (read
-- on the primary 2026-10-30: empty, synchronous_commit on, server 16.15, so
-- today the wait is already the local flush; the line keeps it so). No
-- setting bounds the local WAL flush itself: the hold is 30 s plus that.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

ALTER TABLE dc_events
    DROP COLUMN IF EXISTS leave_anchor_at;

COMMIT;
