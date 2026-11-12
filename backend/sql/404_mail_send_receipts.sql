-- 404_mail_send_receipts.sql
--
-- PROVISIONAL NUMBER. 404 is this lane's working number. The integrator
-- assigns the final one at landing (the next above the highest file on main)
-- and renames this file, its rollback and the tests that name them.
--
-- Mail send receipts. A repeated idempotency_key on POST /mail, on POST
-- /mail/{id}/reply (and on the Discord reply route, which runs the same
-- core) and on the admin broadcast is answered from a receipt of the send
-- instead of from the message row, so the answer is the same whatever the
-- message's delivery and whether the janitor has purged the row since
-- (main._mail_prior_send).
--
--   mail_send_receipts             NEW table, one row per (sender_id,
--                                  idempotency_key) a direct message, a reply
--                                  or a broadcast committed under: the message
--                                  id it answered with, its kind, a
--                                  broadcast's recipient count, created_at,
--                                  request_fp, the SHA-256 digest of the
--                                  request (main._mail_request_fp; NULL on the
--                                  rows this file and its trigger write), and
--                                  message_fp, the SHA-256 digest of the
--                                  message's text as stored (MESSAGE_FP below;
--                                  on every row). No foreign keys: a receipt
--                                  outlives the purge of its message. The
--                                  janitor deletes it MAIL_RETENTION_DAYS
--                                  after the send, and account deletion
--                                  deletes the sender's rows.
--   ix_mail_send_receipts_created  btree (created_at), the janitor's sweep.
--   mail_send_receipt_sync()       NEW trigger function.
--   trg_mail_send_receipt          NEW trigger on mail_messages: AFTER INSERT
--                                  OR UPDATE OF recipient_count, for each row
--                                  of kind 'direct' or 'system_broadcast'.
--   in_reply_to's foreign key      DROPPED: 297's self-reference, ON DELETE
--                                  SET NULL, found by the column it covers.
--                                  in_reply_to is provenance like thread_id
--                                  now: it keeps the parent's id after the
--                                  janitor purges the parent, so a reply's
--                                  detail read gives its sender the same
--                                  in_reply_to whatever the parent's delivery
--                                  to the other players (the purge waits for
--                                  their delivered copies).
--
-- 297'S UNIQUE (sender_id, idempotency_key) STAYS. The previous api build
-- answers a repeated key from the message row and relies on it, unchanged.
-- The new build answers from the receipt alone, and a key with no receipt is
-- sent as a new message; so when the janitor deletes a receipt whose message
-- is still kept (an unread delivered copy keeps it), the same statement gives
-- that message a retired key derived from its own id
-- (main._MAIL_RECEIPT_SWEEP_SQL), and the key can be sent again without
-- meeting the constraint.
--
-- MESSAGE_FP. A receipt this file or its trigger writes has no request
-- digest; a repeat of its key is compared on message_fp instead. It is
-- SHA-256 over three fields, each pair separated by one zero byte, all UTF-8:
-- the route ('broadcast' for a broadcast, 'send' when thread_id = id,
-- 'reply' otherwise), the subject (empty for a reply, whose subject is
-- derived from its parent's) and the body, as the message row stores them.
-- The api writes the same digest on its own receipts (main._mail_message_fp)
-- and computes it for a repeated request from the request's text after the
-- same canonicalising the send applies (main._mail_request_message_fp), so a
-- repeated key with another body, or another subject on a send or a
-- broadcast, is refused 409 whichever build committed the first send. The
-- fields a message row does not store (a send's recipients, a reply's
-- `all`) are compared through request_fp only.
--
-- WHY THE TRIGGER. The api build carrying this change writes each receipt
-- itself, in the sending transaction, with the request's digest. The trigger
-- is for every other writer of mail_messages, the previous api build during
-- the deploy first of all: a message it commits gets a receipt too, so a
-- retry of its key reaching the new build is answered. On INSERT the trigger
-- writes a receipt with no request digest (recipients = NEW.recipient_count).
-- If the key already has a receipt for ANOTHER message -- the previous build
-- sends a key again once the janitor has purged the key's first message --
-- the receipt becomes this message's, which is what the previous build
-- answered with; a receipt of the same message is left as it is. On UPDATE
-- OF recipient_count it fills the count of that message's receipt while the
-- count is still NULL, which is how a broadcast's count reaches its receipt
-- (both builds set the count after the fan-out, in the same transaction).
-- The api's own write is an upsert that completes the trigger's row
-- (main._MAIL_RECEIPT_SQL).
--
-- BACKFILL. Every message row present when the trigger is created gets a
-- receipt with no request digest: created_at and message_fp are the
-- message's, recipients its recipient_count (NULL on a direct message). A
-- broadcast with no count (written before migration 300 added the column)
-- aborts the file instead of being backfilled: the previous build answers a
-- repeat of such a row's key with a count of its envelopes taken at that
-- moment, which no stored count stays equal to once a recipient's account
-- goes. The primary held no broadcast row at all on 12 Nov 2026. The
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
-- the table, the trigger gives every message it commits a receipt, its
-- replay's read of the message row by (sender_id, idempotency_key) is served
-- by 297's constraint as before, and its detail read gives a reply's
-- in_reply_to after the parent's purge as the new build does.
--
-- LOCKS. On a first run the new table and its index are created empty and
-- no other session sees them before COMMIT. CREATE TRIGGER takes SHARE ROW
-- EXCLUSIVE on mail_messages: every send, reply, broadcast, sender delete and
-- janitor purge waits from that statement until COMMIT, while reads go on.
-- The backfill reads mail_messages under that lock. The foreign key's drop
-- then takes ACCESS EXCLUSIVE on mail_messages, so its reads wait as well
-- for the rest of the file (the post-check, which reads only the catalog).
-- `lock_timeout` bounds how long each step waits to START behind a
-- transaction already in flight; if it expires, the whole file rolls back
-- with nothing changed and is re-applied.
--
-- RE-RUNS. Each catalog guard below issues its step only when its object is
-- absent (the foreign key's drop only when a foreign key still covers
-- in_reply_to), so a second run issues none of them and takes no lock on
-- mail_messages or on mail_send_receipts; the statements inside the guards
-- keep `IF NOT EXISTS`. The one statement outside every guard is CREATE OR
-- REPLACE FUNCTION mail_send_receipt_sync(), which runs unconditionally on
-- each run and re-creates the same function body; it takes no lock on
-- either table.
--
-- POST-CHECK. After the guards, one read compares every object with the
-- definition this file states, because a guard alone accepts any object
-- that has the right name. The table: an ordinary permanent table with no
-- row security, no rules, no inheritance and no trigger of its own; its
-- eight columns (type with no modifier, NOT NULL, the default expression,
-- no identity, not generated, the type's own collation); its primary key and
-- its four named checks with their expressions, and no other constraint;
-- exactly two indexes, the primary key's (btree (sender_id,
-- idempotency_key)) and ix_mail_send_receipts_created (btree (created_at),
-- not unique), both valid. The trigger (AFTER INSERT OR UPDATE OF
-- recipient_count, for each row, with this file's WHEN condition, enabled,
-- calling this file's function); the function (returns trigger; its body is
-- this file's, re-created above on every run). And no foreign key covering
-- mail_messages.in_reply_to. Anything that differs aborts the file, naming
-- what it found.

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
      message_fp       BYTEA       NOT NULL,
      message_id       UUID        NOT NULL,
      recipients       INTEGER     NULL,
      created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      PRIMARY KEY (sender_id, idempotency_key),
      CONSTRAINT ck_mail_send_receipts_kind
        CHECK (kind IN ('direct', 'system_broadcast')),
      CONSTRAINT ck_mail_send_receipts_fp
        CHECK (request_fp IS NULL OR octet_length(request_fp) = 32),
      CONSTRAINT ck_mail_send_receipts_message_fp
        CHECK (octet_length(message_fp) = 32),
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

-- The INSERT arm's message_fp is MESSAGE_FP above, spelled out once more in
-- the backfill below; tests/test_mail_receipts_pg.py compares both with
-- main._mail_message_fp.
CREATE OR REPLACE FUNCTION mail_send_receipt_sync() RETURNS trigger
LANGUAGE plpgsql
SET search_path FROM CURRENT
AS $m404fn$
BEGIN
  IF TG_OP = 'INSERT' THEN
    INSERT INTO mail_send_receipts
           (sender_id, idempotency_key, kind, request_fp, message_fp, message_id, recipients,
            created_at)
    VALUES (NEW.sender_id, NEW.idempotency_key, NEW.kind, NULL,
            sha256(convert_to(CASE WHEN NEW.kind = 'system_broadcast' THEN 'broadcast'
                                   WHEN NEW.thread_id = NEW.id THEN 'send'
                                   ELSE 'reply' END, 'UTF8')
                   || decode('00', 'hex')
                   || convert_to(CASE WHEN NEW.kind = 'direct' AND NEW.thread_id <> NEW.id
                                      THEN '' ELSE NEW.subject END, 'UTF8')
                   || decode('00', 'hex')
                   || convert_to(NEW.body, 'UTF8')),
            NEW.id, NEW.recipient_count, NEW.created_at)
    ON CONFLICT (sender_id, idempotency_key) DO UPDATE
       SET kind = EXCLUDED.kind,
           request_fp = NULL,
           message_fp = EXCLUDED.message_fp,
           message_id = EXCLUDED.message_id,
           recipients = EXCLUDED.recipients,
           created_at = EXCLUDED.created_at
     WHERE mail_send_receipts.message_id <> EXCLUDED.message_id;
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
  uncounted integer;
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
    SELECT count(*) INTO uncounted
      FROM mail_messages m
     WHERE m.kind = 'system_broadcast'
       AND m.recipient_count IS NULL;
    IF uncounted <> 0 THEN
      RAISE EXCEPTION '404: % broadcast row(s) have no recipient_count (written before migration 300); this file backfills no such row', uncounted;
    END IF;
    INSERT INTO mail_send_receipts
           (sender_id, idempotency_key, kind, request_fp, message_fp, message_id, recipients,
            created_at)
    SELECT m.sender_id, m.idempotency_key, m.kind, NULL,
           sha256(convert_to(CASE WHEN m.kind = 'system_broadcast' THEN 'broadcast'
                                  WHEN m.thread_id = m.id THEN 'send'
                                  ELSE 'reply' END, 'UTF8')
                  || decode('00', 'hex')
                  || convert_to(CASE WHEN m.kind = 'direct' AND m.thread_id <> m.id
                                     THEN '' ELSE m.subject END, 'UTF8')
                  || decode('00', 'hex')
                  || convert_to(m.body, 'UTF8')),
           m.id, m.recipient_count, m.created_at
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

-- Every foreign key that covers mail_messages.in_reply_to, whatever its name
-- or its ON DELETE action: each one makes a reply's in_reply_to follow its
-- parent's purge (SET NULL), or the purge itself (CASCADE, RESTRICT).
DO $m404irt$
DECLARE
  k record;
BEGIN
  FOR k IN SELECT con.conname
             FROM pg_constraint con
             JOIN pg_class c ON c.oid = con.conrelid
             JOIN pg_namespace n ON n.oid = c.relnamespace
             JOIN pg_attribute a ON a.attrelid = c.oid
            WHERE n.nspname = current_schema()
              AND c.relname = 'mail_messages'
              AND con.contype = 'f'
              AND a.attname = 'in_reply_to'
              AND NOT a.attisdropped
              AND a.attnum = ANY (con.conkey)
  LOOP
    EXECUTE format('ALTER TABLE mail_messages DROP CONSTRAINT %I', k.conname);
  END LOOP;
END $m404irt$;

DO $m404check$
DECLARE
  n integer;
  pk integer;
  valid integer;
  total integer;
BEGIN
  -- The table itself: an ordinary, permanent table, alone (no row
  -- security, no rewrite rule, no parent or child, no trigger of its own).
  SELECT count(*) INTO n
    FROM pg_class c
    JOIN pg_namespace ns ON ns.oid = c.relnamespace
   WHERE ns.nspname = current_schema()
     AND c.relname = 'mail_send_receipts'
     AND c.relkind = 'r'
     AND c.relpersistence = 'p'
     AND NOT c.relrowsecurity
     AND NOT c.relforcerowsecurity
     AND NOT EXISTS (SELECT 1 FROM pg_rewrite r WHERE r.ev_class = c.oid)
     AND NOT EXISTS (SELECT 1 FROM pg_inherits i WHERE i.inhrelid = c.oid OR i.inhparent = c.oid)
     AND NOT EXISTS (SELECT 1 FROM pg_trigger tg WHERE tg.tgrelid = c.oid AND NOT tg.tgisinternal);
  IF n <> 1 THEN
    RAISE EXCEPTION '404: mail_send_receipts is not the plain table this file states (kind, persistence, row security, rules, inheritance or a trigger)';
  END IF;
  SELECT count(*) INTO n
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace ns ON ns.oid = c.relnamespace
   WHERE ns.nspname = current_schema()
     AND c.relname = 'mail_send_receipts'
     AND a.attnum > 0
     AND NOT a.attisdropped;
  IF n <> 8 THEN
    RAISE EXCEPTION '404: mail_send_receipts has % columns, this file states 8', n;
  END IF;
  -- Each column whole: its type with no modifier, NOT NULL, its default
  -- expression as PostgreSQL prints it (pg_get_expr), no identity, not
  -- generated, and the collation its type brings.
  SELECT count(*) INTO n
    FROM (VALUES ('sender_id', 'uuid'::regtype, true, NULL::text),
                 ('idempotency_key', 'uuid'::regtype, true, NULL),
                 ('kind', 'text'::regtype, true, NULL),
                 ('request_fp', 'bytea'::regtype, false, NULL),
                 ('message_fp', 'bytea'::regtype, true, NULL),
                 ('message_id', 'uuid'::regtype, true, NULL),
                 ('recipients', 'integer'::regtype, false, NULL),
                 ('created_at', 'timestamptz'::regtype, true, 'now()')) AS w(col, typ, notnull_, def)
    JOIN pg_attribute a ON a.attname = w.col AND NOT a.attisdropped
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace ns ON ns.oid = c.relnamespace
    JOIN pg_type t ON t.oid = a.atttypid
    LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
   WHERE ns.nspname = current_schema()
     AND c.relname = 'mail_send_receipts'
     AND a.atttypid = w.typ
     AND a.atttypmod = -1
     AND a.attnotnull = w.notnull_
     AND a.attidentity = ''
     AND a.attgenerated = ''
     AND a.attcollation = t.typcollation
     AND pg_get_expr(d.adbin, d.adrelid) IS NOT DISTINCT FROM w.def;
  IF n <> 8 THEN
    RAISE EXCEPTION '404: mail_send_receipts columns differ from this file (found: %)',
      (SELECT string_agg(format('%s %s%s%s%s%s%s', a.attname, format_type(a.atttypid, a.atttypmod),
                                CASE WHEN a.attnotnull THEN ' NOT NULL' ELSE '' END,
                                COALESCE(' DEFAULT ' || pg_get_expr(d.adbin, d.adrelid), ''),
                                CASE WHEN a.attidentity <> '' THEN ' IDENTITY' ELSE '' END,
                                CASE WHEN a.attgenerated <> '' THEN ' GENERATED' ELSE '' END,
                                CASE WHEN a.attcollation <> t.typcollation
                                     THEN ' COLLATE ' || (SELECT co.collname FROM pg_collation co
                                                           WHERE co.oid = a.attcollation)
                                     ELSE '' END), '; ' ORDER BY a.attnum)
         FROM pg_attribute a
         JOIN pg_class c ON c.oid = a.attrelid
         JOIN pg_namespace ns ON ns.oid = c.relnamespace
         JOIN pg_type t ON t.oid = a.atttypid
         LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
        WHERE ns.nspname = current_schema()
          AND c.relname = 'mail_send_receipts'
          AND a.attnum > 0
          AND NOT a.attisdropped);
  END IF;
  -- The key and the four checks by their definitions as PostgreSQL prints
  -- them (pg_get_constraintdef, which also prints DEFERRABLE and NOT VALID),
  -- and no other constraint (NOT NULL is checked with the columns above).
  SELECT count(*) FILTER (
           WHERE (k.contype = 'p'
                  AND pg_get_constraintdef(k.oid) = 'PRIMARY KEY (sender_id, idempotency_key)')
              OR (k.contype = 'c'
                  AND (k.conname, pg_get_constraintdef(k.oid)) IN (
                        ('ck_mail_send_receipts_kind',
                         'CHECK ((kind = ANY (ARRAY[''direct''::text, ''system_broadcast''::text])))'),
                        ('ck_mail_send_receipts_fp',
                         'CHECK (((request_fp IS NULL) OR (octet_length(request_fp) = 32)))'),
                        ('ck_mail_send_receipts_message_fp',
                         'CHECK ((octet_length(message_fp) = 32))'),
                        ('ck_mail_send_receipts_recipients',
                         'CHECK (((recipients IS NULL) OR (recipients >= 0)))')))),
         count(*) FILTER (WHERE k.contype <> 'n')
    INTO n, total
    FROM pg_constraint k
    JOIN pg_class c ON c.oid = k.conrelid
    JOIN pg_namespace ns ON ns.oid = c.relnamespace
   WHERE ns.nspname = current_schema()
     AND c.relname = 'mail_send_receipts';
  IF n <> 5 OR total <> 5 THEN
    RAISE EXCEPTION '404: mail_send_receipts key or checks differ from this file (found: %)',
      (SELECT string_agg(format('%s %s', k.conname, pg_get_constraintdef(k.oid)), '; ' ORDER BY k.conname)
         FROM pg_constraint k
         JOIN pg_class c ON c.oid = k.conrelid
         JOIN pg_namespace ns ON ns.oid = c.relnamespace
        WHERE ns.nspname = current_schema()
          AND c.relname = 'mail_send_receipts'
          AND k.contype <> 'n');
  END IF;
  -- Exactly two indexes, each by its definition after ' USING ' as
  -- pg_get_indexdef prints it (method, columns, order, operator class,
  -- collation, INCLUDE and a predicate all appear there), both valid.
  SELECT count(*) FILTER (
           WHERE ci.relname = 'ix_mail_send_receipts_created'
             AND NOT i.indisunique
             AND substr(pg_get_indexdef(i.indexrelid),
                        strpos(pg_get_indexdef(i.indexrelid), ' USING ') + 7) = 'btree (created_at)'),
         count(*) FILTER (
           WHERE i.indisprimary
             AND substr(pg_get_indexdef(i.indexrelid),
                        strpos(pg_get_indexdef(i.indexrelid), ' USING ') + 7)
                 = 'btree (sender_id, idempotency_key)'),
         count(*) FILTER (WHERE i.indisvalid AND i.indisready AND i.indislive),
         count(*)
    INTO n, pk, valid, total
    FROM pg_index i
    JOIN pg_class ci ON ci.oid = i.indexrelid
    JOIN pg_class t ON t.oid = i.indrelid
    JOIN pg_namespace ns ON ns.oid = t.relnamespace
   WHERE ns.nspname = current_schema()
     AND t.relname = 'mail_send_receipts';
  IF n <> 1 OR pk <> 1 OR valid <> 2 OR total <> 2 THEN
    RAISE EXCEPTION '404: mail_send_receipts indexes differ from this file (found: %)',
      (SELECT string_agg(format('%s%s', pg_get_indexdef(i.indexrelid),
                                CASE WHEN i.indisvalid THEN '' ELSE ' (not valid)' END),
                         '; ' ORDER BY ci.relname)
         FROM pg_index i
         JOIN pg_class ci ON ci.oid = i.indexrelid
         JOIN pg_class t ON t.oid = i.indrelid
         JOIN pg_namespace ns ON ns.oid = t.relnamespace
        WHERE ns.nspname = current_schema()
          AND t.relname = 'mail_send_receipts');
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
               JOIN pg_attribute a ON a.attrelid = c.oid
              WHERE ns.nspname = current_schema()
                AND c.relname = 'mail_messages'
                AND k.contype = 'f'
                AND a.attname = 'in_reply_to'
                AND NOT a.attisdropped
                AND a.attnum = ANY (k.conkey)) THEN
    RAISE EXCEPTION '404: a foreign key still covers mail_messages.in_reply_to';
  END IF;
END $m404check$;

COMMIT;
