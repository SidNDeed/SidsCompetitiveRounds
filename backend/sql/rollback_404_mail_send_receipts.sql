-- rollback_404_mail_send_receipts.sql
--
-- PROVISIONAL NUMBER: renamed together with 404_mail_send_receipts.sql at
-- landing.
--
-- Removes what 404_mail_send_receipts.sql added: the trigger
-- trg_mail_send_receipt on mail_messages, its function
-- mail_send_receipt_sync(), and the table mail_send_receipts with every
-- receipt in it (its index goes with it). Restores 297's constraint
-- uq_mail_messages_sender_idem UNIQUE (sender_id, idempotency_key) on
-- mail_messages. Re-runnable: every DROP is IF EXISTS and the constraint is
-- added only when absent, so a second run changes nothing.
--
-- DEPLOY ORDER: THE API FIRST. Deploy an api build without this change (one
-- that does not name mail_send_receipts), then run this file. An api that
-- still names the table fails every send, reply and broadcast once it is
-- gone. The build without the change answers a repeated key from the
-- message row again, so a key whose message the janitor has purged is no
-- longer answered from anything.
--
-- THE CONSTRAINT CAN REFUSE. While 404 is applied, mail_messages has no
-- uniqueness on (sender_id, idempotency_key): a key can repeat for one
-- sender when its receipt has been swept (MAIL_RETENTION_DAYS after the
-- send) while its message row is still kept, and the same key is sent
-- again. If any pair repeats, adding the constraint fails and the whole file
-- rolls back with nothing changed. This read lists the pairs to decide on
-- before running the file again:
--
--   SELECT sender_id, idempotency_key, count(*) FROM mail_messages
--    GROUP BY sender_id, idempotency_key HAVING count(*) > 1;
--
-- LOCKS. DROP TRIGGER and the constraint's re-creation each take ACCESS
-- EXCLUSIVE on mail_messages until COMMIT; re-creating the constraint
-- builds its unique index over every row, so reads and writes of the table
-- wait for that build. `lock_timeout` bounds how long the file waits to
-- start each step, and a timeout rolls the whole file back with nothing
-- dropped.

BEGIN;
SET LOCAL lock_timeout = '5s';

DROP TRIGGER IF EXISTS trg_mail_send_receipt ON mail_messages;
DROP FUNCTION IF EXISTS mail_send_receipt_sync();
DROP TABLE IF EXISTS mail_send_receipts;

DO $r404uq$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint k
                   JOIN pg_class c ON c.oid = k.conrelid
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = current_schema()
                    AND c.relname = 'mail_messages'
                    AND k.conname = 'uq_mail_messages_sender_idem') THEN
    ALTER TABLE mail_messages
      ADD CONSTRAINT uq_mail_messages_sender_idem UNIQUE (sender_id, idempotency_key);
  END IF;
END $r404uq$;

COMMIT;
