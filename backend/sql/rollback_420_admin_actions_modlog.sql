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
--
-- ONE RUN AT A TIME, and a rerun is a no-op: each drop is the IF EXISTS
-- form of the statement itself, which takes the table's ACCESS EXCLUSIVE
-- lock and then decides under it; a second run started while the first is
-- open waits at its first drop, then finds nothing to drop. After the drops
-- the file checks its own result: exit 0 means the index, the check and
-- both columns are gone; anything still standing ends the transaction in an
-- error and nothing is dropped.
--
-- THE ENVIRONMENT, setting by setting (420's header has the reasons): the
-- isolation level is pinned to READ COMMITTED (line BEGIN); the table's
-- identity is resolved by the session's path and the path is then pinned,
-- pg_catalog first, the table's schema second, the temporary schema last
-- (the env block), so the bare names below are the table and its index;
-- the identity is an oid compared as oid with oid, and the functions are
-- qualified, so no operator or function of the table's schema is taken;
-- nothing is deparsed or compared as text, so quote_all_identifiers,
-- IntervalStyle, DateStyle, TimeZone and extra_float_digits do not enter;
-- no literal holds a backslash, so standard_conforming_strings does not
-- enter; under a read-only session default the first DROP fails inside the
-- transaction and nothing is dropped.

BEGIN ISOLATION LEVEL READ COMMITTED;   -- as 420
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '30s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

-- The table's identity is held as an oid and compared as oid with oid, and
-- every function is qualified (420's header, "exact operators").
DO $env420r$
DECLARE
  tbl pg_catalog.oid := pg_catalog.to_regclass(
    pg_catalog.format('%I.admin_actions', pg_catalog.current_schema()))::pg_catalog.oid;
  nsp pg_catalog.text;
BEGIN
  IF tbl IS NULL THEN
    RAISE EXCEPTION 'rollback 420: admin_actions is missing from the current schema %; nothing changed',
      pg_catalog.current_schema();
  END IF;
  SELECT n.nspname INTO nsp
    FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid OPERATOR(pg_catalog.=) c.relnamespace
   WHERE c.oid OPERATOR(pg_catalog.=) tbl;
  PERFORM pg_catalog.set_config('search_path',
    pg_catalog.format('pg_catalog, %I, pg_temp', nsp), true);   -- the bare names below are the table's
  IF pg_catalog.to_regclass('admin_actions')::oid IS DISTINCT FROM tbl THEN   -- planned after the line above
    RAISE EXCEPTION 'rollback 420: the name admin_actions resolves to another table; nothing changed';
  END IF;
END $env420r$;

DROP INDEX IF EXISTS ix_admin_actions_affected;
ALTER TABLE admin_actions DROP CONSTRAINT IF EXISTS ck_admin_actions_reason_len;
ALTER TABLE admin_actions DROP COLUMN IF EXISTS affected_steam_ids;
ALTER TABLE admin_actions DROP COLUMN IF EXISTS reason;

-- Its own result: each of the four is gone, else the transaction ends in an
-- error and nothing is dropped (exit 0 means all four are gone).
DO $post420r$
DECLARE
  tbl pg_catalog.oid := pg_catalog.to_regclass('admin_actions')::pg_catalog.oid;
  left_over pg_catalog.text;
BEGIN
  SELECT pg_catalog.string_agg(x, ', ') INTO left_over FROM (
    SELECT 'column ' || a.attname::text AS x FROM pg_attribute a
     WHERE a.attrelid = tbl AND NOT a.attisdropped AND a.attname IN ('affected_steam_ids', 'reason')
    UNION ALL
    SELECT 'constraint ' || k.conname::text FROM pg_constraint k
     WHERE k.conrelid = tbl AND k.conname = 'ck_admin_actions_reason_len'
    UNION ALL
    SELECT 'index ' || c.relname::text FROM pg_class c
     WHERE c.relname = 'ix_admin_actions_affected'
       AND c.relnamespace = (SELECT t.relnamespace FROM pg_class t WHERE t.oid = tbl)) s;
  IF tbl IS NULL OR left_over IS NOT NULL THEN
    RAISE EXCEPTION 'rollback 420: still standing after the drops: %; nothing changed',
      coalesce(left_over, 'admin_actions is not found');
  END IF;
END $post420r$;

COMMIT;
