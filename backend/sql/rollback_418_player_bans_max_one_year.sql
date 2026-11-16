-- rollback_418_player_bans_max_one_year.sql
-- Reverses migration 418: drops the CHECK player_bans_max_one_year.
--
-- It does NOT restore NULL ends. The ends 418 set (banned_at + 8760 hours
-- on every row that had none, and the lowered ends) stay as they are: after
-- this file every ban still ends, and nothing records which rows had no end
-- before 418.
--
-- ORDER: apply this file BEFORE any api rollback below the ban-cap build
-- (/health ban_cap_build): an api before the cap writes a NULL end for a ban
-- without a length, which the CHECK refuses. A full rollback of the ban
-- lanes is this file, then the api below the ban-cap build, and only then
-- rollback_417 (which refuses while any active ban carries an end ahead of
-- the clock, as every active ban does after 418).
--
-- Same lock bound as 418 (learning #1072): wait 5 s, hold at most 25 s +
-- 5 s plus the COMMIT's local completion. A rerun after a successful drop is
-- a no-op and takes no lock. The first read takes no lock; the drop itself
-- (DROP CONSTRAINT IF EXISTS) asks again under the lock the ALTER takes, so
-- of two runs at once the second waits on the first, then finds nothing to
-- drop and ends without an error. This file compares no deparsed text.
--
-- rc 0 MEANS THE CHECK IS GONE: a post-check after the drop refuses while
-- player_bans still carries it. REFUSALS (nothing applied): the table
-- missing from the session's current schema (as in 418); the bare name
-- player_bans, under the pinned search path, naming another table or none;
-- the CHECK standing after the drop; a read-only session with the CHECK
-- present (the drop fails).
--
-- THE SESSION'S SETTINGS AND OBJECTS IN ANOTHER SCHEMA (the list in
-- test_ban_cap_pg.py, SESSION_SETTINGS, which runs this file under each):
--   * default_transaction_isolation does not enter: the transaction is READ
--     COMMITTED whatever the session brought (the BEGIN below, the same form
--     as 418).
--   * default_transaction_read_only enters as a refusal: with the CHECK
--     present the ALTER (the drop) fails inside the transaction, nothing
--     applied; with it absent the file changes nothing and ends rc 0.
--   * search_path and the operators it reaches: pinned as in 418. The DO
--     names the table in the session's current schema with every function
--     it calls before the pin and every type it declares qualified by
--     pg_catalog (the declarations are resolved when the block is compiled,
--     before its first statement), then pins the path to
--     pg_catalog first, that schema second and the temporary schema last,
--     and refuses unless the bare name player_bans still names that table.
--     The guard's comparisons are oid = oid and name = name, which
--     pg_catalog holds exactly and the pinned path reaches first; the
--     post-check names pg_catalog's operators outright, so it holds even if
--     the path above it read wrong.
--   * IntervalStyle, quote_all_identifiers, DateStyle, TimeZone,
--     standard_conforming_strings, extra_float_digits do not enter: the file
--     reads no deparsed text and holds no constant they print or parse.

-- the same transaction form as 418, whatever the session's default (header)
BEGIN ISOLATION LEVEL READ COMMITTED;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

DO $r418$
DECLARE
  sch pg_catalog.name := pg_catalog.current_schema();
  tbl pg_catalog.regclass := pg_catalog.to_regclass(pg_catalog.format('%I.player_bans', sch));
BEGIN
  IF tbl IS NULL THEN
    RAISE EXCEPTION 'rollback 418: table player_bans is missing';
  END IF;

  -- The search path, pinned once the table is named, as in 418 (header).
  PERFORM pg_catalog.set_config('search_path', pg_catalog.format('pg_catalog, %I, pg_temp', sch), true);
  IF pg_catalog.to_regclass('player_bans')::oid IS DISTINCT FROM tbl::oid THEN
    RAISE EXCEPTION 'rollback 418: player_bans under the pinned search path is %, not %',
      coalesce(pg_catalog.to_regclass('player_bans')::text, 'missing'), tbl;
  END IF;

  IF EXISTS (SELECT 1 FROM pg_constraint c
              WHERE c.conrelid = tbl::oid AND c.conname = 'player_bans_max_one_year') THEN
    ALTER TABLE player_bans DROP CONSTRAINT IF EXISTS player_bans_max_one_year;
  END IF;

  -- Post-check: rc 0 means the CHECK is gone. Written with pg_catalog's
  -- operators named, so it holds whatever the path above it read.
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_constraint c
              WHERE c.conrelid OPERATOR(pg_catalog.=) tbl::oid
                AND c.conname OPERATOR(pg_catalog.=) 'player_bans_max_one_year'::name) THEN
    RAISE EXCEPTION 'rollback 418: player_bans_max_one_year still stands after the drop';
  END IF;
END $r418$;

COMMIT;
