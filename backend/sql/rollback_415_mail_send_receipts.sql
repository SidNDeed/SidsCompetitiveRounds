-- rollback_415_mail_send_receipts.sql
--
-- NUMBER: written as rollback_404, and renumbered together with
-- 415_mail_send_receipts.sql before landing.
--
-- Removes what 415_mail_send_receipts.sql added: the trigger
-- trg_mail_send_receipt on mail_messages, its function
-- mail_send_receipt_sync(), and the table mail_send_receipts with every
-- receipt in it (its index goes with it). Restores what 415 dropped: 297's
-- foreign key on mail_messages.in_reply_to, REFERENCES mail_messages(id) ON
-- DELETE SET NULL. 297's UNIQUE (sender_id, idempotency_key) is not touched:
-- 415 keeps it. Re-runnable: every DROP is IF EXISTS and the foreign key is
-- added only when none covers in_reply_to, so a second run changes nothing.
--
-- DEPLOY ORDER: THE API FIRST. Deploy an api build without this change (one
-- that does not name mail_send_receipts), then run this file. An api that
-- still names the table fails every send, reply and broadcast once it is
-- gone. The build without the change answers a repeated key from the
-- message row again, so a key whose message the janitor has purged is no
-- longer answered from anything.
--
-- THE FOREIGN KEY. While 415 is applied, a reply keeps its parent's id after
-- the janitor purges the parent. Before the key is added, each such
-- in_reply_to is set to NULL -- the value 297's ON DELETE SET NULL gave it
-- at the purge -- so the key validates. When a foreign key already covers
-- in_reply_to the file adds none: exactly one, with 297's definition as
-- PostgreSQL prints it (pg_get_constraintdef), is accepted; anything else
-- aborts the file, naming what it found, with nothing changed.
--
-- RESERVED KEYS. A message whose receipt the janitor deleted while the
-- message was still kept carries a reserved idempotency_key (version digit
-- 0), drawn at random (main._MAIL_RECEIPT_SWEEP_SQL). The file leaves
-- it: the build without the change then sends a repeat of the message's
-- original key as a new message, and that key's answer had ended with its
-- receipt, MAIL_RETENTION_DAYS after the send. That build does not refuse a
-- reserved key in a request, and no shipped caller of it sends one.
--
-- LOCKS. DROP TRIGGER takes ACCESS EXCLUSIVE on mail_messages until COMMIT,
-- so reads and writes of the table wait from there; the in_reply_to update
-- and the foreign key's validation scan the table under that lock.
-- `lock_timeout` bounds how long the file waits to start each step, and a
-- timeout rolls the whole file back with nothing dropped.

BEGIN;
SET LOCAL lock_timeout = '5s';

DROP TRIGGER IF EXISTS trg_mail_send_receipt ON mail_messages;
DROP FUNCTION IF EXISTS mail_send_receipt_sync();
DROP TABLE IF EXISTS mail_send_receipts;

DO $r415irt$
DECLARE
  total integer;
  same integer;
BEGIN
  SELECT count(*),
         count(*) FILTER (WHERE pg_get_constraintdef(k.oid)
                                = 'FOREIGN KEY (in_reply_to) REFERENCES mail_messages(id) ON DELETE SET NULL')
    INTO total, same
    FROM pg_constraint k
    JOIN pg_class c ON c.oid = k.conrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = c.oid
   WHERE n.nspname = current_schema()
     AND c.relname = 'mail_messages'
     AND k.contype = 'f'
     AND a.attname = 'in_reply_to'
     AND NOT a.attisdropped
     AND a.attnum = ANY (k.conkey);
  IF total = 0 THEN
    UPDATE mail_messages m
       SET in_reply_to = NULL
     WHERE m.in_reply_to IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM mail_messages p WHERE p.id = m.in_reply_to);
    ALTER TABLE mail_messages
      ADD CONSTRAINT mail_messages_in_reply_to_fkey
      FOREIGN KEY (in_reply_to) REFERENCES mail_messages(id) ON DELETE SET NULL;
  ELSIF total <> 1 OR same <> 1 THEN
    RAISE EXCEPTION 'rollback 415: the foreign key on mail_messages.in_reply_to differs from 297''s (found: %)',
      (SELECT string_agg(format('%s %s', k.conname, pg_get_constraintdef(k.oid)), '; ' ORDER BY k.conname)
         FROM pg_constraint k
         JOIN pg_class c ON c.oid = k.conrelid
         JOIN pg_namespace n ON n.oid = c.relnamespace
         JOIN pg_attribute a ON a.attrelid = c.oid
        WHERE n.nspname = current_schema()
          AND c.relname = 'mail_messages'
          AND k.contype = 'f'
          AND a.attname = 'in_reply_to'
          AND NOT a.attisdropped
          AND a.attnum = ANY (k.conkey));
  END IF;
END $r415irt$;

COMMIT;
