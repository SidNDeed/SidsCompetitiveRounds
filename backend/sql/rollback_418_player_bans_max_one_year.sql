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
-- THE SESSION'S SETTINGS (the list in test_ban_cap_pg.py, SESSION_SETTINGS):
--   * default_transaction_isolation does not enter: the transaction is READ
--     COMMITTED whatever the session brought (the BEGIN below, the same form
--     as 418), and the drop's IF EXISTS asks the catalog under the ALTER's
--     lock in any case.
--   * default_transaction_read_only enters as a refusal: with the CHECK
--     present the ALTER (the drop) fails inside the transaction, nothing
--     applied; with it absent the file changes nothing and ends rc 0.
--   * search_path enters at the DO's first read (current_schema() names the
--     table) and at the drop (the bare name player_bans, the first table of
--     that name on the path): the same table whenever the current schema
--     holds one, and with none there the file drops nothing and ends rc 0.
--     Nothing is parsed into a stored expression and no text is compared,
--     so no operator another schema holds enters.
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
BEGIN
  IF EXISTS (SELECT 1 FROM pg_constraint c
              WHERE c.conrelid = to_regclass(format('%I.player_bans', current_schema()))
                AND c.conname = 'player_bans_max_one_year') THEN
    ALTER TABLE player_bans DROP CONSTRAINT IF EXISTS player_bans_max_one_year;
  END IF;
END $r418$;

COMMIT;
