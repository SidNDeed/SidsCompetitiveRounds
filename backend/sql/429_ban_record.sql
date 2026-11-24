-- 429_ban_record.sql
-- What a ban remembers (BAN-RECORD-1): three nullable columns of player_bans
-- and the bound of one of them.
--
-- 1. display_name_at_ban (text, NULL): the name the account's live players
--    row carried when the ban was written, after the display-name rule
--    (main._apply_ban_core reads it under the target's identity lock); NULL
--    when there was no usable name. An admin may set or clear it later
--    through POST /api/v1/admin/ban/details (its `name`). The admin list
--    shows it only while no live players row stands under the id.
-- 2. details (text, NULL): the moderators' own text, at most 2000 characters
--    (CHECK ck_player_bans_details_len: details IS NULL OR
--    char_length(details) <= 2000; models.BAN_DETAILS_MAX).
-- 3. details_at (timestamptz, NULL): when the details last changed.
-- Every existing row stays NULL in all three, so nothing changes for any
-- account until the api writes them. Account deletion sets all three NULL on
-- every ban row of the account, in its own transaction
-- (main.delete_player_data).
--
-- DEPLOY ORDER: THIS FILE FIRST, then the api, as two SHAs (learning #477):
-- the api's ban list, ban writer, details route and account deletion name
-- the three columns in their SQL, so an api deployed before this file fails
-- each of them. This file alone changes no behaviour (three NULL columns no
-- earlier api names, and a CHECK every NULL passes), so it may land any time
-- before the api.
-- ROLLBACK ORDER: the previous api first, then rollback_429_ban_record.sql
-- (the kept names and the details texts go with the columns; each change of
-- a text stays in its ban_details record of the moderator log).
--
-- RE-RUNS. The first read takes no lock: when the three columns stand with
-- their types and the CHECK stands as this file adds it, the DO changes
-- nothing and only re-checks them. Otherwise it takes player_bans' ACCESS
-- EXCLUSIVE lock and reads everything again UNDER the lock, at READ
-- COMMITTED (only there does a read under the lock see a commit made while
-- this run waited): of two first runs at once, the second waits on the
-- first's lock (or gives up after 5 s with nothing applied), then finds the
-- columns and the CHECK under its own lock and adds nothing, the end state of
-- a second run in sequence. Each ADD runs only for what is missing, so a run
-- that finds everything writes no catalog row.
--
-- REFUSALS (RAISE EXCEPTION, one transaction, nothing applied): the table
-- missing from the session's current schema; the bare name player_bans,
-- under the pinned search path, naming another table; a column of one of the
-- three names whose type is another (compared by type oid); a constraint
-- named ck_player_bans_details_len that is not the validated CHECK this file
-- adds (compared by its deparsed text); a read-only session (the lock is the
-- first write and fails inside the transaction).
--
-- THE SESSION'S SETTINGS (as 418 and 420). The transaction is READ COMMITTED
-- whatever the session brought. The search path is pinned at the head of the
-- DO, once the table is named: pg_catalog first, the table's schema second,
-- the temporary schema last, so the CHECK's char_length and <= are
-- pg_catalog's and its deparsed text prints them bare; every function call
-- names pg_catalog; types are compared by oid; quote_all_identifiers is off
-- for the one deparsed text compared. No literal holds a backslash, a date,
-- a time, an interval or a float.
--
-- A TABLE ANOTHER CONNECTION IS READING. The ALTERs need player_bans' ACCESS
-- EXCLUSIVE lock, which waits until every open transaction that has read the
-- table ends; the api's reads of it are short. lock_timeout bounds that wait
-- (5 s): a run that does not get the lock in time is refused with nothing
-- applied and may run again. While it waits, later readers of the table
-- queue behind it, for at most those 5 s.
--
-- HOW LONG THE LOCK CAN LIVE (learning #1072). Once held, the lock lives
-- until COMMIT: statement_timeout bounds the DO (25 s) and
-- idle_in_transaction_session_timeout ends a runner stopped between the DO
-- and COMMIT (5 s), so the hold is bounded by 25 s + 5 s = 30 s plus the
-- COMMIT's local completion; synchronous_commit = local keeps that wait off
-- any standby. The ALTERs rewrite no row (nullable, no default); the CHECK
-- reads the table once to validate it (1 row on the primary).
--
-- Applied by the migrate verb (the file on psql's stdin, ON_ERROR_STOP); the
-- file is its own transaction (learning #340): BEGIN and COMMIT below.
-- backend/tests/test_ban_record_migration_pg.py applies it twice, applies it
-- while another connection holds an open read of the table, rolls it back by
-- its file and refuses each type clash, each with the catalog read after it.

-- the re-read under the lock sees another run's commit only at read committed
BEGIN ISOLATION LEVEL READ COMMITTED;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;
-- the post-check's deparsed text follows quote_all_identifiers
SET LOCAL quote_all_identifiers = off;

DO $m429$
DECLARE
  sch pg_catalog.name := pg_catalog.current_schema();
  tbl pg_catalog.oid := pg_catalog.to_regclass(pg_catalog.format('%I.player_bans', sch))::pg_catalog.oid;
  text_oid pg_catalog.oid := 'pg_catalog.text'::pg_catalog.regtype::pg_catalog.oid;
  tstz_oid pg_catalog.oid := 'pg_catalog.timestamptz'::pg_catalog.regtype::pg_catalog.oid;
  ty_name pg_catalog.oid;
  ty_details pg_catalog.oid;
  ty_at pg_catalog.oid;
  con_oid pg_catalog.oid;
  con_ok pg_catalog.bool;
  want constant pg_catalog.text := 'CHECK (((details IS NULL) OR (char_length(details) <= 2000)))';
BEGIN
  IF tbl IS NULL THEN
    RAISE EXCEPTION '429: table player_bans is missing from the current schema %; nothing changed', sch;
  END IF;

  -- The search path, pinned once the table is named (header).
  PERFORM pg_catalog.set_config('search_path', pg_catalog.format('pg_catalog, %I, pg_temp', sch), true);
  IF pg_catalog.to_regclass('player_bans')::pg_catalog.oid IS DISTINCT FROM tbl THEN
    RAISE EXCEPTION '429: player_bans under the pinned search path is %, not %; nothing changed',
      coalesce(pg_catalog.to_regclass('player_bans')::pg_catalog.text, 'missing'), tbl::pg_catalog.regclass;
  END IF;

  -- First read, without a lock.
  SELECT a.atttypid INTO ty_name FROM pg_attribute a
   WHERE a.attrelid = tbl AND a.attname = 'display_name_at_ban' AND NOT a.attisdropped;
  SELECT a.atttypid INTO ty_details FROM pg_attribute a
   WHERE a.attrelid = tbl AND a.attname = 'details' AND NOT a.attisdropped;
  SELECT a.atttypid INTO ty_at FROM pg_attribute a
   WHERE a.attrelid = tbl AND a.attname = 'details_at' AND NOT a.attisdropped;
  SELECT c.oid, (c.contype = 'c' AND c.convalidated AND pg_catalog.pg_get_constraintdef(c.oid) = want)
    INTO con_oid, con_ok
    FROM pg_constraint c WHERE c.conrelid = tbl AND c.conname = 'ck_player_bans_details_len';

  IF ty_name IS NULL OR ty_details IS NULL OR ty_at IS NULL OR con_oid IS NULL THEN
    -- Something is missing: lock, then read everything again under the lock,
    -- since a run that held the lock before this one may have added it.
    LOCK TABLE player_bans IN ACCESS EXCLUSIVE MODE;
    SELECT a.atttypid INTO ty_name FROM pg_attribute a
     WHERE a.attrelid = tbl AND a.attname = 'display_name_at_ban' AND NOT a.attisdropped;
    SELECT a.atttypid INTO ty_details FROM pg_attribute a
     WHERE a.attrelid = tbl AND a.attname = 'details' AND NOT a.attisdropped;
    SELECT a.atttypid INTO ty_at FROM pg_attribute a
     WHERE a.attrelid = tbl AND a.attname = 'details_at' AND NOT a.attisdropped;
    SELECT c.oid, (c.contype = 'c' AND c.convalidated AND pg_catalog.pg_get_constraintdef(c.oid) = want)
      INTO con_oid, con_ok
      FROM pg_constraint c WHERE c.conrelid = tbl AND c.conname = 'ck_player_bans_details_len';
  END IF;

  -- Refusals: a name that stands with another shape.
  IF ty_name IS NOT NULL AND ty_name <> text_oid THEN
    RAISE EXCEPTION '429: player_bans.display_name_at_ban is %, not text; nothing changed',
      pg_catalog.format_type(ty_name, NULL);
  END IF;
  IF ty_details IS NOT NULL AND ty_details <> text_oid THEN
    RAISE EXCEPTION '429: player_bans.details is %, not text; nothing changed',
      pg_catalog.format_type(ty_details, NULL);
  END IF;
  IF ty_at IS NOT NULL AND ty_at <> tstz_oid THEN
    RAISE EXCEPTION '429: player_bans.details_at is %, not timestamp with time zone; nothing changed',
      pg_catalog.format_type(ty_at, NULL);
  END IF;
  IF con_oid IS NOT NULL AND NOT con_ok THEN
    RAISE EXCEPTION '429: ck_player_bans_details_len is %, not the validated CHECK 429 adds; nothing changed',
      pg_catalog.pg_get_constraintdef(con_oid);
  END IF;

  -- The columns and the CHECK, each only when absent (reached only under the
  -- lock taken above).
  IF ty_name IS NULL THEN
    ALTER TABLE player_bans ADD COLUMN display_name_at_ban TEXT NULL;
    COMMENT ON COLUMN player_bans.display_name_at_ban IS
      'The name the account''s live players row carried when the ban was written, or the name an admin gave it; '
      'NULL when none (migration 429). Account deletion sets it NULL.';
  END IF;
  IF ty_details IS NULL THEN
    ALTER TABLE player_bans ADD COLUMN details TEXT NULL;
    COMMENT ON COLUMN player_bans.details IS
      'The moderators'' own text about the ban, at most 2000 characters; NULL when none (migration 429). '
      'Account deletion sets it NULL.';
  END IF;
  IF ty_at IS NULL THEN
    ALTER TABLE player_bans ADD COLUMN details_at TIMESTAMPTZ NULL;
    COMMENT ON COLUMN player_bans.details_at IS
      'When the details last changed; NULL when there are none (migration 429). Account deletion sets it NULL.';
  END IF;
  IF con_oid IS NULL THEN
    ALTER TABLE player_bans ADD CONSTRAINT ck_player_bans_details_len
      CHECK (details IS NULL OR pg_catalog.char_length(details) <= 2000);
  END IF;
  IF ty_name IS NOT NULL AND ty_details IS NOT NULL AND ty_at IS NOT NULL AND con_oid IS NOT NULL THEN
    RAISE NOTICE '429: the three columns and ck_player_bans_details_len stand; nothing changed';
  END IF;

  -- Post-check, by identity: the shape the api relies on.
  IF (SELECT a.atttypid FROM pg_attribute a
       WHERE a.attrelid = tbl AND a.attname = 'display_name_at_ban' AND NOT a.attisdropped) IS DISTINCT FROM text_oid
     OR (SELECT a.atttypid FROM pg_attribute a
          WHERE a.attrelid = tbl AND a.attname = 'details' AND NOT a.attisdropped) IS DISTINCT FROM text_oid
     OR (SELECT a.atttypid FROM pg_attribute a
          WHERE a.attrelid = tbl AND a.attname = 'details_at' AND NOT a.attisdropped) IS DISTINCT FROM tstz_oid THEN
    RAISE EXCEPTION '429: the three columns of player_bans are not text, text and timestamptz after the file';
  END IF;
  IF NOT EXISTS (
      SELECT 1 FROM pg_constraint c
       WHERE c.conrelid = tbl AND c.conname = 'ck_player_bans_details_len'
         AND c.contype = 'c' AND c.convalidated AND pg_catalog.pg_get_constraintdef(c.oid) = want) THEN
    RAISE EXCEPTION '429: ck_player_bans_details_len is not the validated CHECK after the file';
  END IF;
END $m429$;

COMMIT;
