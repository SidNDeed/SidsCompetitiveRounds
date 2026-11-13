-- 405_lobby_invites.sql
--
-- PROVISIONAL NUMBER. 405 is this lane's working number. The lane builds on
-- 404 (mail send receipts), which lands first. The integrator assigns the
-- final number at landing (the next above the highest file on main) and
-- renames this file, its rollback and the tests that name them.
--
-- Lobby invites (ask 6). A lobby member invites a player into their 2v2, 1v2
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
-- and no other session sees them before COMMIT. Replacing the kind check
-- takes ACCESS EXCLUSIVE on mail_messages and reads the table once to
-- validate the new check: every mail read and write waits from that
-- statement until COMMIT. mail_messages is small (the primary held 9 rows on
-- 12 Nov 2026). `lock_timeout` bounds how long each step waits to START
-- behind a transaction already in flight; if it expires, the whole file
-- rolls back with nothing changed and is re-applied.
--
-- RE-RUNS. Each catalog guard below issues its step only when its object is
-- absent (the check's replacement only when mail_messages has no check named
-- ck_mail_messages_kind with this file's definition), so a second run issues
-- none of them and takes no lock on any table; the statements inside the
-- guards keep `IF NOT EXISTS`. No statement stands outside every guard
-- except BEGIN, SET LOCAL, the guard blocks themselves and COMMIT.
--
-- POST-CHECK. After the guards, one read compares every object with the
-- definition this file states, because a guard alone accepts any object
-- that has the right name: each table is an ordinary permanent table with
-- no row security, no rules and no trigger; its columns in order (type,
-- NOT NULL, default); its constraints by name and definition, and no other;
-- its indexes by name, uniqueness and definition, all valid, and no other.
-- On mail_messages: exactly one check names kind, and it is
-- ck_mail_messages_kind with this file's definition. Anything that differs
-- aborts the file, naming what it found. Not compared: ownership and
-- privileges (a missing grant fails the first statement that needs it), and
-- storage and statistics settings, which change no row and no answer.

BEGIN;
SET LOCAL lock_timeout = '5s';

DO $m405tables$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = current_schema()
                    AND c.relname = 'lobby_invites') THEN
    CREATE TABLE IF NOT EXISTS lobby_invites (
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
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = current_schema()
                    AND c.relname = 'uq_lobby_invites_pending') THEN
    CREATE UNIQUE INDEX IF NOT EXISTS uq_lobby_invites_pending
      ON lobby_invites (mode, lobby_id, invitee_player_id) WHERE state = 'pending';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = current_schema()
                    AND c.relname = 'ix_lobby_invites_invitee_pending') THEN
    CREATE INDEX IF NOT EXISTS ix_lobby_invites_invitee_pending
      ON lobby_invites (invitee_player_id) WHERE state = 'pending';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = current_schema()
                    AND c.relname = 'ix_lobby_invites_lobby') THEN
    CREATE INDEX IF NOT EXISTS ix_lobby_invites_lobby ON lobby_invites (mode, lobby_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = current_schema()
                    AND c.relname = 'ix_lobby_invites_sender_created') THEN
    CREATE INDEX IF NOT EXISTS ix_lobby_invites_sender_created
      ON lobby_invites (sender_player_id, created_at);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = current_schema()
                    AND c.relname = 'ix_lobby_invites_expires') THEN
    CREATE INDEX IF NOT EXISTS ix_lobby_invites_expires ON lobby_invites (expires_at);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = current_schema()
                    AND c.relname = 'invite_receipts') THEN
    CREATE TABLE IF NOT EXISTS invite_receipts (
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
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = current_schema()
                    AND c.relname = 'ix_invite_receipts_invite') THEN
    CREATE INDEX IF NOT EXISTS ix_invite_receipts_invite ON invite_receipts (invite_id);
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
  inv oid;
  rcp oid;
  mm oid;
BEGIN
  -- The three tables this file names, in the schema it ran in.
  SELECT c.oid INTO inv
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = current_schema() AND c.relname = 'lobby_invites';
  SELECT c.oid INTO rcp
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = current_schema() AND c.relname = 'invite_receipts';
  SELECT c.oid INTO mm
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = current_schema() AND c.relname = 'mail_messages';
  IF inv IS NULL OR rcp IS NULL OR mm IS NULL THEN
    RAISE EXCEPTION '405: a table is missing from schema %', current_schema();
  END IF;

  -- The two tables: ordinary, permanent, no row security, no rules, no trigger.
  SELECT string_agg(format('%s %s %s %s %s', c.relname, c.relkind, c.relpersistence,
                           c.relrowsecurity, c.relhasrules), '; ' ORDER BY c.relname)
    INTO found
    FROM pg_class c
   WHERE c.oid IN (inv, rcp);
  want := 'invite_receipts r p false false; lobby_invites r p false false';
  IF found IS DISTINCT FROM want THEN
    RAISE EXCEPTION '405: the tables differ from this file (found: %)', found;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_trigger t
              WHERE t.tgrelid IN (inv, rcp)) THEN
    RAISE EXCEPTION '405: a trigger exists on lobby_invites or invite_receipts';
  END IF;

  -- Columns, in order: name, type, NOT NULL, default.
  SELECT string_agg(format('%s %s %s %s', a.attname, format_type(a.atttypid, a.atttypmod),
                           a.attnotnull, coalesce(pg_get_expr(d.adbin, d.adrelid), '-')),
                    ', ' ORDER BY a.attnum)
    INTO found
    FROM pg_attribute a
    LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
   WHERE a.attrelid = inv AND a.attnum > 0 AND NOT a.attisdropped;
  want := 'id uuid true gen_random_uuid(), mode text true -, lobby_id uuid true -, '
       || 'sender_player_id uuid true -, invitee_player_id uuid true -, kind text true -, '
       || 'state text true ''pending''::text, end_reason text false -, mail_message_id uuid false -, '
       || 'created_at timestamp with time zone true now(), expires_at timestamp with time zone true -, '
       || 'ended_at timestamp with time zone false -';
  IF found IS DISTINCT FROM want THEN
    RAISE EXCEPTION '405: lobby_invites columns differ from this file (found: %)', found;
  END IF;
  SELECT string_agg(format('%s %s %s %s', a.attname, format_type(a.atttypid, a.atttypmod),
                           a.attnotnull, coalesce(pg_get_expr(d.adbin, d.adrelid), '-')),
                    ', ' ORDER BY a.attnum)
    INTO found
    FROM pg_attribute a
    LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
   WHERE a.attrelid = rcp AND a.attnum > 0 AND NOT a.attisdropped;
  want := 'caller_player_id uuid true -, idempotency_key uuid true -, route text true -, '
       || 'invite_id uuid true -, request_fp bytea true -, created_at timestamp with time zone true now()';
  IF found IS DISTINCT FROM want THEN
    RAISE EXCEPTION '405: invite_receipts columns differ from this file (found: %)', found;
  END IF;

  -- Constraints by name and definition, and no other.
  SELECT string_agg(format('%s %s', c.conname, pg_get_constraintdef(c.oid)), '; ' ORDER BY c.conname)
    INTO found
    FROM pg_constraint c
   WHERE c.conrelid = inv;
  want := 'ck_lobby_invites_end_reason CHECK ((end_reason = ANY (ARRAY[''lobby_closed''::text, '
       || '''lobby_started''::text, ''sender_left''::text, ''invitee_kicked''::text]))); '
       || 'ck_lobby_invites_ended CHECK (((state = ''pending''::text) = (ended_at IS NULL))); '
       || 'ck_lobby_invites_expiry CHECK ((expires_at > created_at)); '
       || 'ck_lobby_invites_kind CHECK ((kind = ANY (ARRAY[''invite''::text, ''challenge''::text]))); '
       || 'ck_lobby_invites_mode CHECK ((mode = ANY (ARRAY[''team''::text, ''ovt''::text, ''ffa''::text]))); '
       || 'ck_lobby_invites_not_self CHECK ((sender_player_id <> invitee_player_id)); '
       || 'ck_lobby_invites_state CHECK ((state = ANY (ARRAY[''pending''::text, ''accepted''::text, '
       || '''declined''::text, ''cancelled''::text, ''expired''::text, ''void''::text]))); '
       || 'ck_lobby_invites_void_reason CHECK (((state = ''void''::text) = (end_reason IS NOT NULL))); '
       || 'fk_lobby_invites_invitee FOREIGN KEY (invitee_player_id) REFERENCES players(id); '
       || 'fk_lobby_invites_mail FOREIGN KEY (mail_message_id) REFERENCES mail_messages(id) ON DELETE SET NULL; '
       || 'fk_lobby_invites_sender FOREIGN KEY (sender_player_id) REFERENCES players(id); '
       || 'lobby_invites_pkey PRIMARY KEY (id)';
  IF found IS DISTINCT FROM want THEN
    RAISE EXCEPTION '405: lobby_invites constraints differ from this file (found: %)', found;
  END IF;
  SELECT string_agg(format('%s %s', c.conname, pg_get_constraintdef(c.oid)), '; ' ORDER BY c.conname)
    INTO found
    FROM pg_constraint c
   WHERE c.conrelid = rcp;
  want := 'ck_invite_receipts_request_fp CHECK ((octet_length(request_fp) = 32)); '
       || 'ck_invite_receipts_route CHECK ((route = ANY (ARRAY[''send''::text, ''accept''::text, '
       || '''decline''::text, ''cancel''::text]))); '
       || 'fk_invite_receipts_invite FOREIGN KEY (invite_id) REFERENCES lobby_invites(id) ON DELETE CASCADE; '
       || 'invite_receipts_pkey PRIMARY KEY (caller_player_id, idempotency_key)';
  IF found IS DISTINCT FROM want THEN
    RAISE EXCEPTION '405: invite_receipts constraints differ from this file (found: %)', found;
  END IF;

  -- Indexes by name, uniqueness and definition (after ' USING '), all valid, and no other.
  SELECT string_agg(format('%s %s %s %s', ci.relname, i.indisunique, i.indisvalid,
                           substr(pg_get_indexdef(i.indexrelid),
                                  strpos(pg_get_indexdef(i.indexrelid), ' USING ') + 7)),
                    '; ' ORDER BY ci.relname)
    INTO found
    FROM pg_index i
    JOIN pg_class ci ON ci.oid = i.indexrelid
   WHERE i.indrelid IN (inv, rcp);
  want := 'invite_receipts_pkey true true btree (caller_player_id, idempotency_key); '
       || 'ix_invite_receipts_invite false true btree (invite_id); '
       || 'ix_lobby_invites_expires false true btree (expires_at); '
       || 'ix_lobby_invites_invitee_pending false true btree (invitee_player_id) WHERE (state = ''pending''::text); '
       || 'ix_lobby_invites_lobby false true btree (mode, lobby_id); '
       || 'ix_lobby_invites_sender_created false true btree (sender_player_id, created_at); '
       || 'lobby_invites_pkey true true btree (id); '
       || 'uq_lobby_invites_pending true true btree (mode, lobby_id, invitee_player_id) '
       || 'WHERE (state = ''pending''::text)';
  IF found IS DISTINCT FROM want THEN
    RAISE EXCEPTION '405: the indexes differ from this file (found: %)', found;
  END IF;

  -- mail_messages: exactly one check names kind, and it is this file's.
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
