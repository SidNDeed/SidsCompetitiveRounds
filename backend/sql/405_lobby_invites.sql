-- 405_lobby_invites.sql
--
-- PROVISIONAL NUMBER. 405 is this lane's working number. The lane builds on
-- 404 (mail send receipts), which lands first. The integrator assigns the
-- final number at landing (the next above the highest file on main) and
-- renames this file, its rollback and the tests that name them.
--
-- Lobby invites. A lobby member invites a player into their 2v2, 1v2
-- or FFA lobby, or a player challenges another from their name, which opens
-- a lobby and invites them into it. The invitee gets the invite as a mail row
-- of kind 'invite' and answers it from the mail row or a popup.
--
--   lobby_invites                  NEW table, one row per invite: the mode and
--                                  lobby it is for (lobby_id names a row of
--                                  that mode's lobby table, so it has no
--                                  foreign key), sender and invitee, how it
--                                  was made (kind), its state and, for
--                                  'void', why (end_reason), the invitee's
--                                  mail row (mail_message_id, SET NULL when
--                                  the mail janitor purges that row: the
--                                  invite does not live or die with its mail),
--                                  created_at, expires_at (fixed at send) and
--                                  ended_at (set when it leaves 'pending').
--   uq_lobby_invites_pending       UNIQUE (mode, lobby_id, invitee_player_id)
--                                  WHERE state = 'pending': one pending
--                                  invite per lobby and invitee, whoever
--                                  sent it.
--   ix_lobby_invites_invitee_pending  (invitee_player_id) WHERE pending: the
--                                  invitee's pending list.
--   ix_lobby_invites_lobby         (mode, lobby_id): a lobby's invite list
--                                  (pending and lately ended), the pending
--                                  cap and the sweep.
--   ix_lobby_invites_sender_created  (sender_player_id, created_at): the
--                                  sender's rate count.
--   ix_lobby_invites_expires       (expires_at): retention's delete.
--   invite_receipts                NEW table, one row per keyed invite request
--                                  that committed a change (send, accept,
--                                  decline, cancel), keyed by the caller and
--                                  the request's idempotency key: the route,
--                                  the invite it made or answered (ON DELETE
--                                  CASCADE: the receipt lives exactly as long
--                                  as that invite), request_fp, the SHA-256 of
--                                  the request's canonical form, and
--                                  created_at. A repeated key is answered from
--                                  here before any route, path or state check.
--   ix_invite_receipts_invite      (invite_id): the cascade.
--   ck_mail_messages_kind          REPLACES 297's unnamed check on
--                                  mail_messages.kind (found by its
--                                  definition): admits 'invite' as well as
--                                  'direct' and 'system_broadcast'.
--
-- MAIL'S KEY SPACE IS NOT SPLIT. 297's UNIQUE (sender_id, idempotency_key)
-- stays as 404 keeps it. An invite's mail rows hold a reserved key drawn at
-- random (version digit 0, see 404's RESERVED KEYS), which every mail route
-- refuses in a request, so no send, reply or broadcast meets one. 404's
-- trigger fires only for kinds 'direct' and 'system_broadcast' (its WHEN
-- condition), so an invite's mail row gets no mail_send_receipts row: mail's
-- replay and its rate and spam counts never see an invite. This file leaves
-- 404's trigger and function as they are.
--
-- DEPLOY ORDER: THIS FILE FIRST, THE API SECOND.
-- -----------------------------------------------
-- The api build carrying this change reads and writes both new tables on
-- every invite route, its janitor sweeps them, and its invite sends write
-- mail rows of kind 'invite'. Against a schema without them every invite
-- route fails. So the file lands first: the migrate verb applies it on the
-- primary, the standby receives it by streaming replication, and only then
-- does the code deploy. The previous api build runs on the migrated schema
-- unchanged: it never names the new tables, it writes only kinds the wider
-- check admits, and no row of kind 'invite' exists until the new build
-- writes one.
--
-- LOCKS. On a first run the two tables and their indexes are created empty
-- and no other session sees them before COMMIT. Their foreign keys take
-- SHARE ROW EXCLUSIVE on players and on mail_messages: writes to either
-- table wait from that statement until COMMIT, and reads do not. Replacing
-- the kind check takes ACCESS EXCLUSIVE on mail_messages and reads the table
-- once to validate the new check: every mail read and write waits from that
-- statement until COMMIT. mail_messages is small (the primary held 9 rows on
-- 12 Nov 2026). `lock_timeout` bounds how long each step waits to START
-- behind a transaction already in flight; if it expires, the whole file
-- rolls back with nothing changed and is re-applied.
--
-- CREATE OR REFUSE. The two tables are new and this file alone makes them,
-- so it either creates them or proves they are its own work, and refuses
-- every other state with nothing changed:
--   - neither name stands in the schema: the file creates both tables, with
--     their keys and indexes, and stamps each with its mark, a table comment
--     holding the SHA-256 of the statements between the DDL START and DDL END
--     lines (comment and blank lines dropped, each line trimmed). A name
--     those statements create that already stands in the schema (an index,
--     a key's index, a table's row type) refuses the run before any of them;
--   - both are ordinary tables and both carry exactly that mark: they are
--     this file's own committed work, and the file issues nothing for them
--     and takes no lock on them;
--   - anything else refuses: one without the other, either one unmarked or
--     marked otherwise, or either one not an ordinary table.
-- On the create path the applying role creates both tables in this
-- transaction, so it owns them and holds every privilege on them. A test
-- recomputes the mark from this text, so the statements between the markers
-- cannot change without the mark: tables an older text made are refused.
-- The file does not police a change made to a marked table after it created
-- it: a re-run accepts such a table, because a re-run issues nothing for the
-- tables and no deploy step depends on one.
--
-- RE-RUNS. The kind check's replacement is issued only when mail_messages
-- has no check named ck_mail_messages_kind with this file's definition, so
-- a second run issues no DDL and takes no lock on any table. No statement
-- stands outside every guard except BEGIN, SET LOCAL, the guard blocks
-- themselves and COMMIT.
--
-- POST-CHECK. After the guards, one read compares mail_messages' checks with
-- this file: exactly one check names kind, and it is ck_mail_messages_kind
-- with this file's definition. Anything else aborts the file, naming what it
-- found. mail_messages is an existing table, so the claim stays that narrow:
-- the file compares nothing else of it.

BEGIN;
SET LOCAL lock_timeout = '5s';

-- The two tables: created and marked, or found marked, or refused (CREATE
-- OR REFUSE above).
DO $m405tables$
DECLARE
  mark CONSTANT text := 'lobby invites, DDL sha256 d8c6427e321c7e2eebe713174e46aa968e34c02cbb8f92901adeabe4ff9d4b6b';
  taken text;
  found text;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = current_schema()
                    AND c.relname IN ('lobby_invites', 'invite_receipts')) THEN
    SELECT string_agg(x.name, ', ' ORDER BY x.name) INTO taken
      FROM (SELECT c.relname::text AS name
              FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = current_schema()
               AND c.relname IN ('lobby_invites_pkey', 'uq_lobby_invites_pending',
                                 'ix_lobby_invites_invitee_pending', 'ix_lobby_invites_lobby',
                                 'ix_lobby_invites_sender_created', 'ix_lobby_invites_expires',
                                 'invite_receipts_pkey', 'ix_invite_receipts_invite')
            UNION ALL
            SELECT t.typname::text
              FROM pg_type t
              JOIN pg_namespace n ON n.oid = t.typnamespace
             WHERE n.nspname = current_schema()
               AND t.typname IN ('lobby_invites', 'invite_receipts')) x;
    IF taken IS NOT NULL THEN
      RAISE EXCEPTION '405: a name this file creates already stands in schema % (found: %)',
        current_schema(), taken;
    END IF;
    -- DDL START
    CREATE TABLE lobby_invites (
      id                 UUID        NOT NULL DEFAULT gen_random_uuid(),
      mode               TEXT        NOT NULL,
      lobby_id           UUID        NOT NULL,
      sender_player_id   UUID        NOT NULL,
      invitee_player_id  UUID        NOT NULL,
      kind               TEXT        NOT NULL,
      state              TEXT        NOT NULL DEFAULT 'pending',
      end_reason         TEXT        NULL,
      mail_message_id    UUID        NULL,
      created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
      expires_at         TIMESTAMPTZ NOT NULL,
      ended_at           TIMESTAMPTZ NULL,
      CONSTRAINT lobby_invites_pkey PRIMARY KEY (id),
      CONSTRAINT fk_lobby_invites_sender FOREIGN KEY (sender_player_id) REFERENCES players(id),
      CONSTRAINT fk_lobby_invites_invitee FOREIGN KEY (invitee_player_id) REFERENCES players(id),
      CONSTRAINT fk_lobby_invites_mail FOREIGN KEY (mail_message_id)
        REFERENCES mail_messages(id) ON DELETE SET NULL,
      CONSTRAINT ck_lobby_invites_mode CHECK (mode IN ('team', 'ovt', 'ffa')),
      CONSTRAINT ck_lobby_invites_kind CHECK (kind IN ('invite', 'challenge')),
      CONSTRAINT ck_lobby_invites_state
        CHECK (state IN ('pending', 'accepted', 'declined', 'cancelled', 'expired', 'void')),
      CONSTRAINT ck_lobby_invites_end_reason
        CHECK (end_reason IN ('lobby_closed', 'lobby_started', 'sender_left', 'invitee_kicked')),
      CONSTRAINT ck_lobby_invites_void_reason CHECK ((state = 'void') = (end_reason IS NOT NULL)),
      CONSTRAINT ck_lobby_invites_ended CHECK ((state = 'pending') = (ended_at IS NULL)),
      CONSTRAINT ck_lobby_invites_not_self CHECK (sender_player_id <> invitee_player_id),
      CONSTRAINT ck_lobby_invites_expiry CHECK (expires_at > created_at)
    );
    CREATE UNIQUE INDEX uq_lobby_invites_pending
      ON lobby_invites (mode, lobby_id, invitee_player_id) WHERE state = 'pending';
    CREATE INDEX ix_lobby_invites_invitee_pending
      ON lobby_invites (invitee_player_id) WHERE state = 'pending';
    CREATE INDEX ix_lobby_invites_lobby ON lobby_invites (mode, lobby_id);
    CREATE INDEX ix_lobby_invites_sender_created
      ON lobby_invites (sender_player_id, created_at);
    CREATE INDEX ix_lobby_invites_expires ON lobby_invites (expires_at);
    CREATE TABLE invite_receipts (
      caller_player_id   UUID        NOT NULL,
      idempotency_key    UUID        NOT NULL,
      route              TEXT        NOT NULL,
      invite_id          UUID        NOT NULL,
      request_fp         BYTEA       NOT NULL,
      created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
      CONSTRAINT invite_receipts_pkey PRIMARY KEY (caller_player_id, idempotency_key),
      CONSTRAINT fk_invite_receipts_invite FOREIGN KEY (invite_id)
        REFERENCES lobby_invites(id) ON DELETE CASCADE,
      CONSTRAINT ck_invite_receipts_route CHECK (route IN ('send', 'accept', 'decline', 'cancel')),
      CONSTRAINT ck_invite_receipts_request_fp CHECK (octet_length(request_fp) = 32)
    );
    CREATE INDEX ix_invite_receipts_invite ON invite_receipts (invite_id);
    -- DDL END
    EXECUTE format('COMMENT ON TABLE lobby_invites IS %L', mark);
    EXECUTE format('COMMENT ON TABLE invite_receipts IS %L', mark);
  ELSE
    SELECT string_agg(format('%s %s', w.name, coalesce((
             SELECT CASE WHEN c.relkind <> 'r' THEN 'not a table'
                         WHEN obj_description(c.oid, 'pg_class') = mark THEN 'marked'
                         ELSE 'unmarked' END
               FROM pg_class c
               JOIN pg_namespace n ON n.oid = c.relnamespace
              WHERE n.nspname = current_schema() AND c.relname = w.name), 'absent')),
           ', ' ORDER BY w.name)
      INTO found
      FROM (VALUES ('invite_receipts'), ('lobby_invites')) AS w(name);
    IF found IS DISTINCT FROM 'invite_receipts marked, lobby_invites marked' THEN
      RAISE EXCEPTION '405: lobby_invites and invite_receipts are neither both absent nor both marked by this file (found: %)',
        found;
    END IF;
  END IF;
END $m405tables$;

-- mail_messages.kind admits 'invite'. 297 declared the check inline, so its
-- name is the server's (mail_messages_kind_check on every box this repo has
-- built); it is found by its definition instead, and only a check of exactly
-- 297's definition is dropped. Any other check naming kind is left for the
-- post-check to refuse.
DO $m405kind$
DECLARE
  old_check name;
  mm oid;
BEGIN
  SELECT c.oid INTO mm
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = current_schema() AND c.relname = 'mail_messages';
  IF mm IS NULL THEN
    RAISE EXCEPTION '405: mail_messages is not in schema %', current_schema();
  END IF;
  IF NOT EXISTS (
       SELECT 1 FROM pg_constraint c
        WHERE c.conrelid = mm
          AND c.contype = 'c'
          AND c.conname = 'ck_mail_messages_kind'
          AND pg_get_constraintdef(c.oid)
              = 'CHECK ((kind = ANY (ARRAY[''direct''::text, ''system_broadcast''::text, ''invite''::text])))') THEN
    FOR old_check IN
      SELECT c.conname FROM pg_constraint c
       WHERE c.conrelid = mm
         AND c.contype = 'c'
         AND pg_get_constraintdef(c.oid)
             = 'CHECK ((kind = ANY (ARRAY[''direct''::text, ''system_broadcast''::text])))'
    LOOP
      EXECUTE format('ALTER TABLE mail_messages DROP CONSTRAINT %I', old_check);
    END LOOP;
    ALTER TABLE mail_messages ADD CONSTRAINT ck_mail_messages_kind
      CHECK (kind IN ('direct', 'system_broadcast', 'invite'));
  END IF;
END $m405kind$;

DO $m405check$
DECLARE
  found text;
  want text;
  mm oid;
BEGIN
  -- mail_messages: exactly one check names kind, and it is this file's.
  SELECT c.oid INTO mm
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = current_schema() AND c.relname = 'mail_messages';
  SELECT string_agg(format('%s %s', c.conname, pg_get_constraintdef(c.oid)), '; ' ORDER BY c.conname)
    INTO found
    FROM pg_constraint c
   WHERE c.conrelid = mm
     AND c.contype = 'c'
     AND pg_get_constraintdef(c.oid) ~ '\mkind\M';
  want := 'ck_mail_messages_kind CHECK ((kind = ANY (ARRAY[''direct''::text, ''system_broadcast''::text, '
       || '''invite''::text])))';
  IF found IS DISTINCT FROM want THEN
    RAISE EXCEPTION '405: mail_messages kind checks differ from this file (found: %)', found;
  END IF;
END $m405check$;

COMMIT;
