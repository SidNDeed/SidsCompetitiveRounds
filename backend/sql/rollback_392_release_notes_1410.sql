-- rollback_392_release_notes_1410.sql
-- Removes what 392_release_notes_1410.sql wrote: the five v1.41.0 rows of
-- release_notes_i18n (en, es, ru, uk, sv). NOT a release-train migration.
-- It deletes by key, not by content, so a row the admin endpoint rewrote
-- after 392 ran is removed as well. Re-runnable: with the rows gone, nothing
-- is deleted. Explicit transaction (learning #340).
-- DEPLOY ORDER: none. A tag without a row keeps the English GitHub release
-- body (185_release_notes_i18n.sql, the degrade-to-English overlay).
-- Timeouts and commit as in 392: lock_timeout bounds the wait for a lock
-- (5 s). One statement, the DELETE, runs between the SET LOCAL lines and
-- COMMIT. Statement and idle timeouts have separate budgets (PostgreSQL 16
-- has no transaction_timeout), so the hold bound is statement plus idle.
-- THE COMMIT. PostgreSQL disables the statement timer before it commits, so
-- the COMMIT's own work is outside every timeout above. synchronous_commit
-- = local keeps that work LOCAL: it never waits for a standby's
-- confirmation, whatever synchronous_standby_names says now or later (read
-- on the primary 2026-10-30: empty, synchronous_commit on, server 16.15).
-- BOUNDED: everything before COMMIT -- the wait for the lock (5 s, before
-- the hold starts) and the hold up to COMMIT (statement 25 s + idle 5 s =
-- 30 s). NOT BOUNDED: the COMMIT's local completion -- the WAL flush and the
-- transaction-status (pg_xact) write, which can read an evicted page -- I/O
-- that no PostgreSQL setting bounds, for this or any transaction. The hold
-- is therefore 30 s plus the COMMIT's local completion.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

DELETE FROM release_notes_i18n
 WHERE tag = 'v1.41.0'
   AND language_code IN ('en', 'es', 'ru', 'uk', 'sv');

COMMIT;
