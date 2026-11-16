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
-- a no-op and takes no lock.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

DO $r418$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_constraint c
              WHERE c.conrelid = to_regclass(format('%I.player_bans', current_schema()))
                AND c.conname = 'player_bans_max_one_year') THEN
    ALTER TABLE player_bans DROP CONSTRAINT player_bans_max_one_year;
  END IF;
END $r418$;

COMMIT;
