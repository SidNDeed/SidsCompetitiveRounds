-- rollback_405_lobby_invites.sql
--
-- Undoes 405_lobby_invites.sql (provisional number; renamed with it).
--
-- ORDER: THE API FIRST, THIS FILE SECOND. The api build carrying 405 reads
-- and writes both tables on every invite route and writes mail rows of kind
-- 'invite'; roll it back first, then apply this file, back to back.
-- Between the two steps traffic is not quiesced: the previous api lists each
-- invite's mail row, to its own sender (Sent) and invitee (inbox), as an
-- ordinary mail with the server's text. The row holds no room, no password
-- and no player-written text, and no other player can read it; step 2 below
-- deletes it. Deleting invite mail before the api rollback would not close
-- that gap, since sends go on until the api is rolled back.
--
-- What it does, in one transaction:
--   1. drops invite_receipts, then lobby_invites (with their indexes);
--   2. deletes every mail row of kind 'invite': the previous api build has
--      no reader for them, and 297's check cannot be put back while one
--      exists. Their recipient rows go with them (297's ON DELETE CASCADE).
--      An invite's text is the server's, so no player-written text is lost;
--   3. replaces ck_mail_messages_kind with 297's check, ('direct',
--      'system_broadcast'), under the name 297's inline check takes on a
--      fresh build, unless a check of exactly that definition exists.
--
-- Re-running it changes nothing more: the drops are IF EXISTS, the delete
-- then finds no row, and the check's step is guarded by its definition.

BEGIN;
SET LOCAL lock_timeout = '5s';

DROP TABLE IF EXISTS invite_receipts;
DROP TABLE IF EXISTS lobby_invites;

DELETE FROM mail_messages WHERE kind = 'invite';

ALTER TABLE mail_messages DROP CONSTRAINT IF EXISTS ck_mail_messages_kind;

DO $r405kind$
DECLARE
  mm oid;
BEGIN
  SELECT c.oid INTO mm
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = current_schema() AND c.relname = 'mail_messages';
  IF mm IS NULL THEN
    RAISE EXCEPTION 'rollback 405: mail_messages is not in schema %', current_schema();
  END IF;
  IF NOT EXISTS (
       SELECT 1 FROM pg_constraint c
        WHERE c.conrelid = mm
          AND c.contype = 'c'
          AND pg_get_constraintdef(c.oid)
              = 'CHECK ((kind = ANY (ARRAY[''direct''::text, ''system_broadcast''::text])))') THEN
    ALTER TABLE mail_messages ADD CONSTRAINT mail_messages_kind_check
      CHECK (kind IN ('direct', 'system_broadcast'));
  END IF;
END $r405kind$;

COMMIT;
