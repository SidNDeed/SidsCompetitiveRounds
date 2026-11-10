-- rollback_402_seat_evidence_findings_match.sql
--
-- Removes what 402_seat_evidence_findings_match.sql added: the partial index
-- ix_seat_evidence_findings_game_match. No row and no other object changes.
-- Re-runnable: the DROP is IF EXISTS, so a second run does nothing.
--
-- DEPLOY ORDER: THE API FIRST. Deploy an api build without phase 3, then run
-- this file. An api with phase 3 keeps answering without the index (its
-- lookup by match then scans the scope 'game' rows), so the order bounds the
-- cost of the lookup, not its result.
--
-- The DROP takes ACCESS EXCLUSIVE on seat_evidence_findings for the drop
-- itself, which is short; `lock_timeout` bounds how long the file waits to
-- start it, and a timeout rolls the file back with nothing dropped.

BEGIN;
SET LOCAL lock_timeout = '5s';

DROP INDEX IF EXISTS ix_seat_evidence_findings_game_match;

COMMIT;
