-- rollback_397_shop_item_min_client_version.sql
-- Reverses migration 397: drops shop_items.min_client_version and the
-- shop_item_release_provenance table.
--
-- ORDER: the api that reads the column goes first (deploy the previous api,
-- or every shop read fails on the missing column), and rollback_398 before
-- this file. The DO refuses while any item still carries a minimum or any
-- provenance row exists: dropping either would silently re-expose a floored
-- item to older clients, or strand a release rollback without the record it
-- needs. Nothing is dropped then; clear the cause (rollback_398) and rerun.
-- A rerun after a successful drop is a no-op.
--
-- LOCK FIRST, THEN COUNT. Each count runs only after its table is held
-- ACCESS EXCLUSIVE (the mode the drop takes anyway; shop_items first, the
-- order 398 writes them in): a minimum or provenance row written by a
-- transaction still open when this file starts is committed before the
-- lock is granted and is counted, so the refusal sees it; nothing is
-- dropped on a count read before a concurrent write landed. A table that
-- no longer exists is not locked, so a rerun still takes no lock.
--
-- Same lock bound as 397 (learning #1072): wait 5 s, hold at most 25 s +
-- 5 s plus the COMMIT's local completion.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

DO $r397$
DECLARE
  n bigint;
BEGIN
  IF EXISTS (SELECT 1 FROM pg_attribute a
              WHERE a.attrelid = to_regclass(format('%I.shop_items', current_schema()))
                AND a.attname = 'min_client_version'
                AND NOT a.attisdropped) THEN
    EXECUTE 'LOCK TABLE shop_items IN ACCESS EXCLUSIVE MODE';
  END IF;
  IF to_regclass(format('%I.shop_item_release_provenance', current_schema())) IS NOT NULL THEN
    EXECUTE 'LOCK TABLE shop_item_release_provenance IN ACCESS EXCLUSIVE MODE';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_attribute a
              WHERE a.attrelid = to_regclass(format('%I.shop_items', current_schema()))
                AND a.attname = 'min_client_version'
                AND NOT a.attisdropped) THEN
    EXECUTE 'SELECT count(*) FROM shop_items WHERE min_client_version IS NOT NULL' INTO n;
    IF n > 0 THEN
      RAISE EXCEPTION 'rollback 397: % shop item(s) still carry a min_client_version - '
                      'run rollback_398 (or clear them) first; nothing dropped', n;
    END IF;
  END IF;
  IF to_regclass(format('%I.shop_item_release_provenance', current_schema())) IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM shop_item_release_provenance' INTO n;
    IF n > 0 THEN
      RAISE EXCEPTION 'rollback 397: % release provenance row(s) remain - run the release '
                      'rollback(s) that own them first; nothing dropped', n;
    END IF;
  END IF;
  -- Both drops are guarded on the catalog, so a rerun takes no lock.
  IF to_regclass(format('%I.shop_item_release_provenance', current_schema())) IS NOT NULL THEN
    DROP TABLE shop_item_release_provenance;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_attribute a
              WHERE a.attrelid = to_regclass(format('%I.shop_items', current_schema()))
                AND a.attname = 'min_client_version'
                AND NOT a.attisdropped) THEN
    ALTER TABLE shop_items DROP COLUMN min_client_version;
  END IF;
END $r397$;

COMMIT;
