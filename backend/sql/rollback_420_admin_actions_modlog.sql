-- rollback_420_admin_actions_modlog.sql
-- Reverses migration 420: drops the index ix_admin_actions_affected, the
-- check ck_admin_actions_reason_len and the columns affected_steam_ids and
-- reason of admin_actions.
--
-- ORDER: the api that writes the columns goes first (deploy the previous api,
-- or every moderator action fails on the missing columns: the 420 writer
-- names both).
--
-- What this loses: the players and the reasons stored in the two columns
-- (the rows themselves stay, with their actor, action, target columns and
-- details, which still hold every reason the api before 420 stored there).
-- A rerun after a successful rollback is a no-op: every statement is guarded
-- on the catalog and takes no lock then.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '30s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

DO $r420$
BEGIN
  IF to_regclass(format('%I.ix_admin_actions_affected', current_schema())) IS NOT NULL THEN
    DROP INDEX ix_admin_actions_affected;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint c
              WHERE c.conname = 'ck_admin_actions_reason_len'
                AND c.conrelid = to_regclass(format('%I.admin_actions', current_schema()))) THEN
    ALTER TABLE admin_actions DROP CONSTRAINT ck_admin_actions_reason_len;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_attribute a
              WHERE a.attrelid = to_regclass(format('%I.admin_actions', current_schema()))
                AND a.attname = 'affected_steam_ids' AND NOT a.attisdropped) THEN
    ALTER TABLE admin_actions DROP COLUMN affected_steam_ids;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_attribute a
              WHERE a.attrelid = to_regclass(format('%I.admin_actions', current_schema()))
                AND a.attname = 'reason' AND NOT a.attisdropped) THEN
    ALTER TABLE admin_actions DROP COLUMN reason;
  END IF;
END $r420$;

COMMIT;
