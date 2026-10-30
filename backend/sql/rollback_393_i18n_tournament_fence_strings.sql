-- rollback_393_i18n_tournament_fence_strings.sql
-- Takes back what 393_i18n_tournament_fence_strings.sql adds to the review
-- surfaces, the way the key sync's retirement does: the four client keys are
-- RETIRED, never deleted, so entries and proposal history survive, and every
-- PENDING proposal on them is decided 'superseded' (the review endpoints refuse
-- to approve or reject a proposal on a retired key, so one left pending would
-- sit in the queue for good). Keys before proposals, the order the key sync and
-- the review endpoint take. The previous TournHow and TournForfeits body keys
-- are not touched: 393 never writes them.
-- NOT a release-train migration. Re-runnable: with the keys retired and nothing
-- pending on them, it writes no row.
-- DEPLOY ORDER: only while no shipped client carries these four strings, or with
-- that client's rollback. A client that already shows them keeps its bundled
-- drafts, and the next key sync from such a client makes the keys live again.
-- Explicit transaction (learning #340) under the same four lines as 393: 5 s on
-- each lock wait, 25 s on each top-level statement, 5 s on a pause between
-- statements, and synchronous_commit = local. The statement and idle budgets are
-- separate (PostgreSQL 16 has no transaction_timeout), so the longest this file
-- can hold locks before its COMMIT is their SUM, 30 s, and that holds because both
-- UPDATEs run inside ONE statement, a DO block whose inner statements share its
-- 25 s. COMMIT itself is outside statement_timeout; with synchronous_commit = local
-- it does not wait on a synchronous standby, so its own wait is the local WAL flush
-- only, which no setting bounds.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

DO $r393$
BEGIN
    UPDATE i18n_keys
       SET retired_at = clock_timestamp(), updated_at = clock_timestamp()
     WHERE namespace = 'client'
       AND key_id IN ('c4d5526dfaef7312', '8b0f70cb42c1cda3',
                      'f76648a14f012b93', 'fc5b6244bdd13c72')
       AND retired_at IS NULL;

    UPDATE i18n_proposals
       SET status = 'superseded', review_note = 'key retired by rollback_393',
           reviewed_at = clock_timestamp()
     WHERE key_id IN ('c4d5526dfaef7312', '8b0f70cb42c1cda3',
                      'f76648a14f012b93', 'fc5b6244bdd13c72')
       AND status = 'pending';
END $r393$;

COMMIT;
