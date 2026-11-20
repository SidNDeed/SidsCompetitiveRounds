-- Rollback of 419 (QDIG-1): drops digest_posted_at and digest_reminded_at and
-- restores the status column's comment. Run it only AFTER the QDIG-1 code is
-- rolled back: that code reads and writes both columns.
--
-- Rows the janitor set to 'filed' keep that word. A build before QDIG-1 lists
-- and counts only 'pending' rows, so to it a filed row reads as a reviewed one,
-- and its stored report body is untouched. Safe to run twice: each drop is
-- guarded on the catalog.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';

DO $r419$
DECLARE
  rel regclass := to_regclass(format('%I.match_report_quarantine', current_schema()));
BEGIN
  IF rel IS NULL THEN
    RAISE EXCEPTION 'rollback 419: match_report_quarantine does not exist';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_attribute a
              WHERE a.attrelid = rel AND a.attname = 'digest_posted_at' AND NOT a.attisdropped) THEN
    ALTER TABLE match_report_quarantine DROP COLUMN digest_posted_at;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_attribute a
              WHERE a.attrelid = rel AND a.attname = 'digest_reminded_at' AND NOT a.attisdropped) THEN
    ALTER TABLE match_report_quarantine DROP COLUMN digest_reminded_at;
  END IF;
END $r419$;

COMMENT ON COLUMN match_report_quarantine.status IS NULL;

COMMIT;
