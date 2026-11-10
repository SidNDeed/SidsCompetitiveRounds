-- 402_seat_evidence_findings_match.sql
--
-- Admin evidence report, phase 3 (ship-gate row B10, review round B10-P3-R1):
-- the stored findings of a game are found by the match they were computed
-- for. The number is the next free one on the lane's branch; it is taken
-- again at merge time if another lane holds it by then.
--
--   ix_seat_evidence_findings_game_match   btree (match_id) on
--                                          seat_evidence_findings, partial:
--                                          WHERE scope = 'game'.
--
-- The admin evidence report lists a game's findings from the rows whose
-- stored match_id is the game's id (admin_evidence.FINDINGS_MATCH_SQL, which
-- names scope = 'game' as this index's predicate does), whichever records,
-- games rows or contributions of the game the page read. The table's other
-- indexes lead with scope or domain and cannot serve a lookup by match.
--
-- DEPLOY ORDER: THIS FILE FIRST, THE API SECOND.
-- -----------------------------------------------
-- An api build carrying phase 3 runs the lookup by match on every phase-3
-- page; without this index the statement still answers, by a scan of the
-- scope 'game' rows. So the file lands first, as a migration-only precursor
-- commit: the migrate verb applies it on the primary, the standby receives
-- it by streaming replication, the index is read back on both boxes, and
-- only then does the code deploy. An api build without phase 3 ignores the
-- index. It lands with phase 3 after the ship (ruling R6).
--
-- LOCKS. On a first run CREATE INDEX holds SHARE on seat_evidence_findings
-- while it builds: the evidence workers' writes of findings wait during the
-- build, readers continue. `lock_timeout` bounds only how long the file waits
-- to START the build behind a transaction already in flight; if it expires
-- the whole file rolls back with nothing changed and is re-applied.
--
-- RE-RUNS. The step is guarded on the catalog and issued only when the index
-- is absent from the current schema, so a second run issues no DDL and takes
-- no lock on the table (an `IF NOT EXISTS` spelling alone takes the table lock
-- before it checks; test_migration_reruns holds this file to that). The
-- statement inside the guard keeps `IF NOT EXISTS`.
--
-- POST-CHECK. After the guard, one read compares the index with the
-- definition this file states (btree (match_id) WHERE scope = 'game', valid,
-- not unique, on seat_evidence_findings). A same-named object of any other
-- definition aborts the file, because the guard alone would accept it.

BEGIN;
SET LOCAL lock_timeout = '5s';

DO $m402index$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = current_schema()
                    AND c.relname = 'ix_seat_evidence_findings_game_match') THEN
    CREATE INDEX IF NOT EXISTS ix_seat_evidence_findings_game_match
        ON seat_evidence_findings (match_id) WHERE scope = 'game';
  END IF;
END $m402index$;

DO $m402check$
DECLARE
  matching integer;
BEGIN
  SELECT count(*) INTO matching
    FROM pg_index i
    JOIN pg_class ci ON ci.oid = i.indexrelid
    JOIN pg_class t ON t.oid = i.indrelid
    JOIN pg_namespace n ON n.oid = ci.relnamespace
   WHERE n.nspname = current_schema()
     AND ci.relname = 'ix_seat_evidence_findings_game_match'
     AND t.relname = 'seat_evidence_findings'
     AND NOT i.indisunique
     AND i.indisvalid
     AND substr(pg_get_indexdef(i.indexrelid),
                strpos(pg_get_indexdef(i.indexrelid), ' USING ') + 7)
         = 'btree (match_id) WHERE ((scope)::text = ''game''::text)';
  IF matching <> 1 THEN
    RAISE EXCEPTION '402: ix_seat_evidence_findings_game_match differs from this file';
  END IF;
END $m402check$;

COMMIT;
