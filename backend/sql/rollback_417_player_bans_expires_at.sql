-- rollback_417_player_bans_expires_at.sql
-- Reverses migration 417: drops player_bans.expires_at and the unique index
-- player_bans_one_open_per_key.
--
-- ORDER: the api that reads the column goes first (deploy the previous api,
-- or every ban check fails on the missing column).
--
-- An api before 417 reads a row with unbanned_at NULL as an active ban
-- whatever its end time. So, under the table's lock, this file first closes
-- every ENDED open row (unbanned_at = expires_at, unbanned_by_steam_id =
-- 'system:expired', what the 417 api writes when it closes one), so that no
-- ended ban becomes active again; then it refuses while any open row still
-- carries an end time ahead of NOW(): dropping the column would make that
-- ban permanent. Nothing is changed then, the close included (one
-- transaction); lift or wait out those bans and rerun. A rerun after a
-- successful drop is a no-op and takes no lock.
--
-- Same lock bound as 417 (learning #1072): wait 5 s, hold at most 25 s +
-- 5 s plus the COMMIT's local completion.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

DO $r417$
DECLARE
  n bigint;
BEGIN
  IF EXISTS (SELECT 1 FROM pg_attribute a
              WHERE a.attrelid = to_regclass(format('%I.player_bans', current_schema()))
                AND a.attname = 'expires_at'
                AND NOT a.attisdropped) THEN
    EXECUTE 'LOCK TABLE player_bans IN ACCESS EXCLUSIVE MODE';
    EXECUTE 'UPDATE player_bans SET unbanned_by_steam_id = ''system:expired'', unbanned_at = expires_at'
            ' WHERE unbanned_at IS NULL AND expires_at IS NOT NULL AND expires_at <= NOW()';
    EXECUTE 'SELECT count(*) FROM player_bans WHERE unbanned_at IS NULL AND expires_at > NOW()' INTO n;
    IF n > 0 THEN
      RAISE EXCEPTION 'rollback 417: % active ban(s) still carry an end time - lift them or let '
                      'them end first; nothing dropped', n;
    END IF;
  END IF;
  -- Both drops are guarded on the catalog, so a rerun takes no lock.
  IF to_regclass(format('%I.player_bans_one_open_per_key', current_schema())) IS NOT NULL THEN
    DROP INDEX player_bans_one_open_per_key;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_attribute a
              WHERE a.attrelid = to_regclass(format('%I.player_bans', current_schema()))
                AND a.attname = 'expires_at'
                AND NOT a.attisdropped) THEN
    ALTER TABLE player_bans DROP COLUMN expires_at;
  END IF;
END $r417$;

COMMIT;
