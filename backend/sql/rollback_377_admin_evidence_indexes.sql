-- rollback_377_admin_evidence_indexes.sql
--
-- Removes what 377_admin_evidence_indexes.sql added: the four order indexes on
-- `matches` (idx_matches_pair, idx_matches_p1_order, idx_matches_p2_order and
-- idx_matches_series) and the extended statistics object stx_matches_pair.
-- Nothing reads the five by name: the report routes are correct without them
-- and only unbounded in time (377's header), so this file is safe in either
-- order with the api. An api build that still declares the four indexes on its
-- Match model runs as before (the model's declaration is read only when a
-- schema is built from it). No row, no column and none of 001's three player
-- indexes is touched. Re-runnable: every DROP is IF EXISTS, so a second run
-- does nothing.
--
-- DEPLOY ORDER: EITHER ORDER WITH THE API; prefer the api first, so the
-- unindexed scans run only on a build that has no report routes.
--
-- Each DROP INDEX takes ACCESS EXCLUSIVE on `matches` for the drop itself,
-- which is short; `lock_timeout` bounds how long the file waits to start it,
-- and a timeout rolls the whole file back with nothing dropped.

BEGIN;
SET LOCAL lock_timeout = '5s';

DROP STATISTICS IF EXISTS stx_matches_pair;
DROP INDEX IF EXISTS idx_matches_series;
DROP INDEX IF EXISTS idx_matches_p2_order;
DROP INDEX IF EXISTS idx_matches_p1_order;
DROP INDEX IF EXISTS idx_matches_pair;

COMMIT;
