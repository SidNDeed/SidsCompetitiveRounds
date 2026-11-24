-- rollback_429_ban_record.sql
-- Reverses migration 429: drops the CHECK ck_player_bans_details_len and the
-- columns details_at, details and display_name_at_ban of player_bans.
--
-- ORDER: the api that names the columns goes first (deploy the previous api,
-- or the ban list, the ban writer, the details route and the account deletion
-- fail on the missing columns). The kept names and the details texts go with
-- the columns; each change of a text stays in its ban_details record of the
-- moderator log.
--
-- Each drop is guarded on the catalog, so a rerun after a successful rollback
-- takes no lock and changes nothing. A column of one of the three names is
-- dropped only when it has the type 429 gives it (compared by type oid);
-- another type is refused, nothing dropped, since 429 never made that column.
-- Same pinned search path and lock bound as 429 (learning #1072): wait 5 s,
-- hold at most 25 s + 5 s plus the COMMIT's local completion.

BEGIN ISOLATION LEVEL READ COMMITTED;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

DO $r429$
DECLARE
  sch pg_catalog.name := pg_catalog.current_schema();
  tbl pg_catalog.oid := pg_catalog.to_regclass(pg_catalog.format('%I.player_bans', sch))::pg_catalog.oid;
  text_oid pg_catalog.oid := 'pg_catalog.text'::pg_catalog.regtype::pg_catalog.oid;
  tstz_oid pg_catalog.oid := 'pg_catalog.timestamptz'::pg_catalog.regtype::pg_catalog.oid;
  ty_name pg_catalog.oid;
  ty_details pg_catalog.oid;
  ty_at pg_catalog.oid;
BEGIN
  IF tbl IS NULL THEN
    RAISE NOTICE 'rollback 429: no player_bans in the current schema %; nothing to do', sch;
    RETURN;
  END IF;
  PERFORM pg_catalog.set_config('search_path', pg_catalog.format('pg_catalog, %I, pg_temp', sch), true);
  IF pg_catalog.to_regclass('player_bans')::pg_catalog.oid IS DISTINCT FROM tbl THEN
    RAISE EXCEPTION 'rollback 429: player_bans under the pinned search path is %, not %; nothing dropped',
      coalesce(pg_catalog.to_regclass('player_bans')::pg_catalog.text, 'missing'), tbl::pg_catalog.regclass;
  END IF;
  SELECT a.atttypid INTO ty_name FROM pg_attribute a
   WHERE a.attrelid = tbl AND a.attname = 'display_name_at_ban' AND NOT a.attisdropped;
  SELECT a.atttypid INTO ty_details FROM pg_attribute a
   WHERE a.attrelid = tbl AND a.attname = 'details' AND NOT a.attisdropped;
  SELECT a.atttypid INTO ty_at FROM pg_attribute a
   WHERE a.attrelid = tbl AND a.attname = 'details_at' AND NOT a.attisdropped;
  IF (ty_name IS NOT NULL AND ty_name <> text_oid) OR (ty_details IS NOT NULL AND ty_details <> text_oid)
     OR (ty_at IS NOT NULL AND ty_at <> tstz_oid) THEN
    RAISE EXCEPTION 'rollback 429: a column of player_bans named as 429 names it has another type; nothing dropped';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint c
              WHERE c.conrelid = tbl AND c.conname = 'ck_player_bans_details_len') THEN
    ALTER TABLE player_bans DROP CONSTRAINT ck_player_bans_details_len;
  END IF;
  IF ty_at IS NOT NULL THEN
    ALTER TABLE player_bans DROP COLUMN details_at;
  END IF;
  IF ty_details IS NOT NULL THEN
    ALTER TABLE player_bans DROP COLUMN details;
  END IF;
  IF ty_name IS NOT NULL THEN
    ALTER TABLE player_bans DROP COLUMN display_name_at_ban;
  END IF;
END $r429$;

COMMIT;
