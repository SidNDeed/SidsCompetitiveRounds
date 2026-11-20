-- 419: held game reports in plain words (QDIG-1, 16 Nov 2026) -- the digest's
-- durable "already posted" state.
--
-- Two columns on match_report_quarantine, both NULL until written:
--   digest_posted_at   when a Discord message that listed this row was
--                      accepted (POST /api/v1/internal/quarantine/digest/posted,
--                      kind "new"); a row is listed once, so a bot restart
--                      posts nothing unless something is new.
--   digest_reminded_at when the bot's daily reminder that covered this row
--                      was accepted (the same route, kind "reminder"); the
--                      reminder's clock lives here, not in the bot's memory.
--
-- The new status word 'filed' (a pending row the janitor found to carry the
-- same result as the recorded game; reviewed_by NULL, a machine-written
-- review_note) needs NO schema change: status is VARCHAR(16) and no CHECK
-- constraint holds its words (169). This migration refuses to run if one does,
-- because such a constraint would refuse 'filed'. The word is added to the
-- column's comment below.
--
-- DEPLOY ORDER: THIS FILE FIRST, then the api, then the bot.
-- The QDIG-1 code reads and writes these columns (the digest feed, the posted
-- route, the janitor's census). Safe to apply twice: every step is guarded
-- on the catalog. Rollback: rollback_419_quarantine_digest_posted.sql, after
-- the code is rolled back.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';

DO $m419$
DECLARE
  rel regclass := to_regclass(format('%I.match_report_quarantine', current_schema()));
  got text;
  col text;
  chk bigint;
BEGIN
  IF rel IS NULL THEN
    RAISE EXCEPTION '419: match_report_quarantine does not exist (migration 169 first)';
  END IF;
  SELECT format_type(a.atttypid, a.atttypmod) INTO got
    FROM pg_attribute a
   WHERE a.attrelid = rel AND a.attname = 'status' AND NOT a.attisdropped;
  IF got IS DISTINCT FROM 'character varying(16)' THEN
    RAISE EXCEPTION '419: match_report_quarantine.status is %, not character varying(16)',
      coalesce(got, 'missing');
  END IF;
  SELECT count(*) INTO chk
    FROM pg_constraint c
   WHERE c.conrelid = rel AND c.contype = 'c'
     AND pg_get_constraintdef(c.oid) ILIKE '%status%';
  IF chk > 0 THEN
    RAISE EXCEPTION '419: % CHECK constraint(s) on match_report_quarantine name status; '
                    'the word filed would be refused', chk;
  END IF;
  FOREACH col IN ARRAY ARRAY['digest_posted_at', 'digest_reminded_at'] LOOP
    SELECT format_type(a.atttypid, a.atttypmod) INTO got
      FROM pg_attribute a
     WHERE a.attrelid = rel AND a.attname = col AND NOT a.attisdropped;
    IF got IS NOT NULL AND got <> 'timestamp with time zone' THEN
      RAISE EXCEPTION '419: match_report_quarantine.% exists as %, not timestamp with time zone',
        col, got;
    END IF;
  END LOOP;
END $m419$;

ALTER TABLE match_report_quarantine ADD COLUMN IF NOT EXISTS digest_posted_at TIMESTAMPTZ NULL;
ALTER TABLE match_report_quarantine ADD COLUMN IF NOT EXISTS digest_reminded_at TIMESTAMPTZ NULL;

COMMENT ON COLUMN match_report_quarantine.status IS
  'pending|accepted|discarded|filed. filed: the janitor found the held report gives the same '
  'result as the recorded game holding its room (only kills differ, within bounds); reviewed_by '
  'NULL, review_note machine-written; nothing is deleted (migration 419).';
COMMENT ON COLUMN match_report_quarantine.digest_posted_at IS
  'When a Discord digest message listing this row was accepted; NULL = not yet posted (migration 419).';
COMMENT ON COLUMN match_report_quarantine.digest_reminded_at IS
  'When the last Discord digest reminder covering this row was accepted (migration 419).';

DO $p419$
DECLARE
  rel regclass := to_regclass(format('%I.match_report_quarantine', current_schema()));
  col text;
  got text;
BEGIN
  FOREACH col IN ARRAY ARRAY['digest_posted_at', 'digest_reminded_at'] LOOP
    SELECT format_type(a.atttypid, a.atttypmod) INTO got
      FROM pg_attribute a
     WHERE a.attrelid = rel AND a.attname = col AND NOT a.attisdropped;
    IF got IS DISTINCT FROM 'timestamp with time zone' THEN
      RAISE EXCEPTION '419: match_report_quarantine.% is %, not timestamp with time zone',
        col, coalesce(got, 'missing');
    END IF;
  END LOOP;
END $p419$;

COMMIT;
