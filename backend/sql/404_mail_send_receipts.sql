-- 404_mail_send_receipts.sql
--
-- PROVISIONAL NUMBER. 404 is this lane's working number. The integrator
-- assigns the final one at landing (the next above the highest file on main)
-- and renames this file, its rollback and the tests that name them.
--
-- Mail send receipts. A repeated idempotency_key on POST /mail, on POST
-- /mail/{id}/reply and on the admin broadcast is answered from a receipt of
-- the send instead of from the message row, so the answer is the same
-- whatever the message's delivery and whether the janitor has purged the row
-- since (main._mail_prior_send).
--
--   mail_send_receipts             NEW table, one row per (sender_id,
--                                  idempotency_key) a direct message, a reply
--                                  or a broadcast committed under: the message
--                                  id it answered with, its kind, a
--                                  broadcast's recipient count, created_at and
--                                  request_fp, the SHA-256 digest of the
--                                  request (main._mail_request_fp; NULL on the
--                                  rows this file and its trigger write). No
--                                  foreign keys: a receipt outlives the purge
--                                  of its message. The janitor deletes it
--                                  MAIL_RETENTION_DAYS after the send, and
--                                  account deletion deletes the sender's rows.
--   ix_mail_send_receipts_created  btree (created_at), the janitor's sweep.
--   mail_send_receipt_sync()       NEW trigger function.
--   trg_mail_send_receipt          NEW trigger on mail_messages: AFTER INSERT
--                                  OR UPDATE OF recipient_count, for each row
--                                  of kind 'direct' or 'system_broadcast'.
--   uq_mail_messages_sender_idem   DROPPED (297). A key's uniqueness per
--                                  sender is the receipt's primary key now;
--                                  nothing reads mail_messages by key any
--                                  more.
--
-- WHY THE TRIGGER. The api build carrying this change writes each receipt
-- itself, in the sending transaction, with the request's digest. The trigger
-- is for every other writer of mail_messages, the previous api build during
-- the deploy first of all: a message it commits gets a receipt too, so a
-- retry of its key reaching the new build is answered. On INSERT the trigger
-- writes a receipt with no digest (recipients = NEW.recipient_count) unless
-- the key already has one; on UPDATE OF recipient_count it fills the count
-- of that message's receipt while the count is still NULL, which is how a
-- broadcast's count reaches its receipt (both builds set the count after the
-- fan-out, in the same transaction). The api's own write is an upsert that
-- completes the trigger's row (main._MAIL_RECEIPT_SQL).
--
-- BACKFILL. Every message row present when the trigger is created gets a
-- receipt with no digest: created_at is the message's; recipients is NULL
-- for a direct message and, for a broadcast, its recipient_count, or on a
-- row written before 300 added that column the count of its delivered
-- envelopes -- the answer the previous build's replay gave for it. The
-- backfill runs in the trigger's guard block right after CREATE TRIGGER,
-- whose SHARE ROW EXCLUSIVE lock on mail_messages holds every concurrent
-- write of the table until COMMIT, so no message commits between the trigger
-- and the backfill; the block then counts the message rows left without a
-- receipt and aborts the file unless there are none.
--
-- DEPLOY ORDER: THIS FILE FIRST, THE API SECOND.
-- -----------------------------------------------
-- The api build carrying this change reads and writes mail_send_receipts on
-- every send, reply and broadcast, and its janitor sweeps it (the boot-time
-- EXPLAIN self-test reaches that sweep). Against a schema without the table
-- every send fails. So the file lands first, as a migration-only precursor
-- commit: the migrate verb applies it on the primary, the standby receives
-- it by streaming replication, and only then does the code deploy. The
-- previous api build runs on the migrated schema unchanged: it never names
-- the table, the trigger gives every message it commits a receipt, and its
-- replay's read of the message row by (sender_id, idempotency_key) is served
-- by ix_mail_messages_sender_created once the constraint's index is gone.
--
-- LOCKS. On a first run the new table and its index are created empty and
-- no other session sees them before COMMIT. CREATE TRIGGER takes SHARE ROW
-- EXCLUSIVE on mail_messages: every send, reply, broadcast, sender delete and
-- janitor purge waits from that statement until COMMIT, while reads go on.
-- The backfill reads mail_messages and mail_recipients under that lock. The
-- constraint's drop then takes ACCESS EXCLUSIVE on mail_messages, so its
-- reads wait as well for the rest of the file (the post-check, which reads
-- only the catalog). `lock_timeout` bounds how long each step waits to START
-- behind a transaction already in flight; if it expires, the whole file
-- rolls back with nothing changed and is re-applied.
--
-- RE-RUNS. Each catalog guard below issues its step only when its object is
-- absent (the constraint's drop only when the constraint is present), so a
-- second run issues none of them and takes no lock on mail_messages or on
-- mail_send_receipts; the statements inside the guards keep `IF NOT EXISTS`
-- or `IF EXISTS`. The one statement outside every guard is CREATE OR REPLACE
-- FUNCTION mail_send_receipt_sync(), which runs unconditionally on each run
-- and re-creates the same function body; it takes no lock on either table.
--
-- POST-CHECK. After the guards, one read compares every object with the
-- definition this file states: the table's seven columns (type, NOT NULL,
-- created_at's default), its primary key and its three named checks with
-- their expressions, and no other constraint; the index (btree
-- (created_at), valid, not unique); the trigger (AFTER INSERT OR UPDATE OF
-- recipient_count, for each row, with this file's WHEN condition, enabled,
-- calling this file's function); the function (returns trigger); and 297's
-- constraint, which must be gone. Any same-named object that differs aborts
-- the file, naming what it found, because a guard alone would accept it.

BEGIN;
SET LOCAL lock_timeout = '5s';

DO $m404tbl$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = current_schema()
                    AND c.relname = 'mail_send_receipts') THEN
    CREATE TABLE IF NOT EXISTS mail_send_receipts (
      sender_id        UUID        NOT NULL,
      idempotency_key  UUID        NOT NULL,
      kind             TEXT        NOT NULL,
      request_fp       BYTEA       NULL,
      message_id       UUID        NOT NULL,
      recipients       INTEGER     NULL,
      created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      PRIMARY KEY (sender_id, idempotency_key),
      CONSTRAINT ck_mail_send_receipts_kind
        CHECK (kind IN ('direct', 'system_broadcast')),
      CONSTRAINT ck_mail_send_receipts_fp
        CHECK (request_fp IS NULL OR octet_length(request_fp) = 32),
      CONSTRAINT ck_mail_send_receipts_recipients
        CHECK (recipients IS NULL OR recipients >= 0)
    );
  END IF;
END $m404tbl$;

DO $m404idx$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = current_schema()
                    AND c.relname = 'ix_mail_send_receipts_created') THEN
    CREATE INDEX IF NOT EXISTS ix_mail_send_receipts_created ON mail_send_receipts (created_at);
  END IF;
END $m404idx$;

CREATE OR REPLACE FUNCTION mail_send_receipt_sync() RETURNS trigger
LANGUAGE plpgsql
SET search_path FROM CURRENT
AS $m404fn$
BEGIN
  IF TG_OP = 'INSERT' THEN
    INSERT INTO mail_send_receipts
           (sender_id, idempotency_key, kind, request_fp, message_id, recipients, created_at)
    VALUES (NEW.sender_id, NEW.idempotency_key, NEW.kind, NULL, NEW.id,
            NEW.recipient_count, NEW.created_at)
    ON CONFLICT (sender_id, idempotency_key) DO NOTHING;
  ELSE
    UPDATE mail_send_receipts
       SET recipients = NEW.recipient_count
     WHERE sender_id = NEW.sender_id
       AND idempotency_key = NEW.idempotency_key
       AND message_id = NEW.id
       AND recipients IS NULL;
  END IF;
  RETURN NULL;
END
$m404fn$;

DO $m404trg$
DECLARE
  missing integer;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger tg
                   JOIN pg_class c ON c.oid = tg.tgrelid
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = current_schema()
                    AND c.relname = 'mail_messages'
                    AND tg.tgname = 'trg_mail_send_receipt'
                    AND NOT tg.tgisinternal) THEN
    CREATE TRIGGER trg_mail_send_receipt
      AFTER INSERT OR UPDATE OF recipient_count ON mail_messages
      FOR EACH ROW
      WHEN (NEW.kind IN ('direct', 'system_broadcast'))
      EXECUTE FUNCTION mail_send_receipt_sync();
    INSERT INTO mail_send_receipts
           (sender_id, idempotency_key, kind, request_fp, message_id, recipients, created_at)
    SELECT m.sender_id, m.idempotency_key, m.kind, NULL, m.id,
           CASE WHEN m.kind = 'system_broadcast'
                THEN COALESCE(m.recipient_count,
                              (SELECT CAST(count(*) AS integer) FROM mail_recipients r
                                WHERE r.message_id = m.id AND r.delivery = 'delivered'))
           END,
           m.created_at
      FROM mail_messages m
     WHERE m.kind IN ('direct', 'system_broadcast')
    ON CONFLICT (sender_id, idempotency_key) DO NOTHING;
    SELECT count(*) INTO missing
      FROM mail_messages m
     WHERE m.kind IN ('direct', 'system_broadcast')
       AND NOT EXISTS (SELECT 1 FROM mail_send_receipts s
                        WHERE s.sender_id = m.sender_id
                          AND s.idempotency_key = m.idempotency_key);
    IF missing <> 0 THEN
      RAISE EXCEPTION '404: % message row(s) have no send receipt after the backfill', missing;
    END IF;
  END IF;
END $m404trg$;

DO $m404uq$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_constraint k
               JOIN pg_class c ON c.oid = k.conrelid
               JOIN pg_namespace n ON n.oid = c.relnamespace
              WHERE n.nspname = current_schema()
                AND c.relname = 'mail_messages'
                AND k.conname = 'uq_mail_messages_sender_idem') THEN
    ALTER TABLE mail_messages DROP CONSTRAINT IF EXISTS uq_mail_messages_sender_idem;
  END IF;
END $m404uq$;

DO $m404check$
DECLARE
  n integer;
  total integer;
BEGIN
  SELECT count(*) INTO n
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace ns ON ns.oid = c.relnamespace
   WHERE ns.nspname = current_schema()
     AND c.relname = 'mail_send_receipts'
     AND a.attnum > 0
     AND NOT a.attisdropped;
  IF n <> 7 THEN
    RAISE EXCEPTION '404: mail_send_receipts has % columns, this file states 7', n;
  END IF;
  SELECT count(*) INTO n
    FROM (VALUES ('sender_id', 'uuid'::regtype, true, false),
                 ('idempotency_key', 'uuid'::regtype, true, false),
                 ('kind', 'text'::regtype, true, false),
                 ('request_fp', 'bytea'::regtype, false, false),
                 ('message_id', 'uuid'::regtype, true, false),
                 ('recipients', 'integer'::regtype, false, false),
                 ('created_at', 'timestamptz'::regtype, true, true)) AS w(col, typ, notnull_, hasdef)
    JOIN pg_attribute a ON a.attname = w.col AND NOT a.attisdropped
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace ns ON ns.oid = c.relnamespace
   WHERE ns.nspname = current_schema()
     AND c.relname = 'mail_send_receipts'
     AND a.atttypid = w.typ
     AND a.attnotnull = w.notnull_
     AND a.atthasdef = w.hasdef;
  IF n <> 7 THEN
    RAISE EXCEPTION '404: mail_send_receipts columns differ from this file (type, NOT NULL, default)';
  END IF;
  -- The key and the three checks by their definitions as PostgreSQL prints
  -- them (pg_get_constraintdef), and no other constraint (NOT NULL is
  -- checked with the columns above).
  SELECT count(*) FILTER (
           WHERE (k.contype = 'p'
                  AND pg_get_constraintdef(k.oid) = 'PRIMARY KEY (sender_id, idempotency_key)')
              OR (k.contype = 'c'
                  AND (k.conname, pg_get_constraintdef(k.oid)) IN (
                        ('ck_mail_send_receipts_kind',
                         'CHECK ((kind = ANY (ARRAY[''direct''::text, ''system_broadcast''::text])))'),
                        ('ck_mail_send_receipts_fp',
                         'CHECK (((request_fp IS NULL) OR (octet_length(request_fp) = 32)))'),
                        ('ck_mail_send_receipts_recipients',
                         'CHECK (((recipients IS NULL) OR (recipients >= 0)))')))),
         count(*) FILTER (WHERE k.contype <> 'n')
    INTO n, total
    FROM pg_constraint k
    JOIN pg_class c ON c.oid = k.conrelid
    JOIN pg_namespace ns ON ns.oid = c.relnamespace
   WHERE ns.nspname = current_schema()
     AND c.relname = 'mail_send_receipts';
  IF n <> 4 OR total <> 4 THEN
    RAISE EXCEPTION '404: mail_send_receipts key or checks differ from this file (found: %)',
      (SELECT string_agg(format('%s %s', k.conname, pg_get_constraintdef(k.oid)), '; ' ORDER BY k.conname)
         FROM pg_constraint k
         JOIN pg_class c ON c.oid = k.conrelid
         JOIN pg_namespace ns ON ns.oid = c.relnamespace
        WHERE ns.nspname = current_schema()
          AND c.relname = 'mail_send_receipts'
          AND k.contype <> 'n');
  END IF;
  SELECT count(*) INTO n
    FROM pg_index i
    JOIN pg_class ci ON ci.oid = i.indexrelid
    JOIN pg_class t ON t.oid = i.indrelid
    JOIN pg_namespace ns ON ns.oid = ci.relnamespace
   WHERE ns.nspname = current_schema()
     AND ci.relname = 'ix_mail_send_receipts_created'
     AND t.relname = 'mail_send_receipts'
     AND NOT i.indisunique
     AND i.indisvalid
     AND substr(pg_get_indexdef(i.indexrelid),
                strpos(pg_get_indexdef(i.indexrelid), ' USING ') + 7) = 'btree (created_at)';
  IF n <> 1 THEN
    RAISE EXCEPTION '404: ix_mail_send_receipts_created differs from this file';
  END IF;
  SELECT count(*) INTO n
    FROM pg_trigger tg
    JOIN pg_class c ON c.oid = tg.tgrelid
    JOIN pg_namespace ns ON ns.oid = c.relnamespace
    JOIN pg_proc p ON p.oid = tg.tgfoid
    JOIN pg_namespace pns ON pns.oid = p.pronamespace
   WHERE ns.nspname = current_schema()
     AND c.relname = 'mail_messages'
     AND tg.tgname = 'trg_mail_send_receipt'
     AND NOT tg.tgisinternal
     AND tg.tgtype = 21                         -- for each row, after, insert or update
     AND tg.tgenabled = 'O'
     -- tgattr is an int2vector, whose subscripts start at 0, and array
     -- equality compares the start as well: its text form is compared
     -- instead (one column prints as its number).
     AND CAST(tg.tgattr AS text) = (SELECT CAST(a.attnum AS text) FROM pg_attribute a
                                     WHERE a.attrelid = c.oid
                                       AND a.attname = 'recipient_count'
                                       AND NOT a.attisdropped)
     -- the WHEN condition as PostgreSQL prints it (pg_get_triggerdef)
     AND substring(pg_get_triggerdef(tg.oid) FROM ' WHEN \((.*)\) EXECUTE ')
         = '(new.kind = ANY (ARRAY[''direct''::text, ''system_broadcast''::text]))'
     AND p.proname = 'mail_send_receipt_sync'
     AND pns.nspname = current_schema()
     AND p.prorettype = 'trigger'::regtype;
  IF n <> 1 THEN
    RAISE EXCEPTION '404: trg_mail_send_receipt or its function differs from this file (found: %)',
      COALESCE((SELECT string_agg(format('%s, enabled %s, function in %s returning %s',
                                         pg_get_triggerdef(tg.oid), tg.tgenabled, pns.nspname,
                                         CAST(p.prorettype AS regtype)), '; ')
                  FROM pg_trigger tg
                  JOIN pg_class c ON c.oid = tg.tgrelid
                  JOIN pg_namespace ns ON ns.oid = c.relnamespace
                  JOIN pg_proc p ON p.oid = tg.tgfoid
                  JOIN pg_namespace pns ON pns.oid = p.pronamespace
                 WHERE ns.nspname = current_schema()
                   AND c.relname = 'mail_messages'
                   AND tg.tgname = 'trg_mail_send_receipt'), 'no such trigger');
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint k
               JOIN pg_class c ON c.oid = k.conrelid
               JOIN pg_namespace ns ON ns.oid = c.relnamespace
              WHERE ns.nspname = current_schema()
                AND c.relname = 'mail_messages'
                AND k.conname = 'uq_mail_messages_sender_idem') THEN
    RAISE EXCEPTION '404: uq_mail_messages_sender_idem is still on mail_messages';
  END IF;
END $m404check$;

COMMIT;
