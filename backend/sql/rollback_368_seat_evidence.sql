-- rollback_368_seat_evidence.sql
--
-- Removes what 368_seat_evidence.sql added: its seven tables and its three
-- seeded runtime switches. Nothing else references these tables (no other
-- table has a foreign key into them), so the drop reaches nothing outside them.
--
-- DEPLOY ORDER: THE API FIRST. Deploy an api build without the seat-evidence
-- routes and worker, then run this file. An api that still carries them reads
-- the removed switch rows as off (the seat route answers 503, the worker
-- idles), but its admin seat-evidence view, digest registration and
-- compat-outcome route answer 500 against the missing tables.
--
-- It discards every stored seat record and finding. flagged_matches rows the
-- worker posted are NOT removed (the audit log is append-only).

BEGIN;

DROP TABLE IF EXISTS seat_evidence_findings;
DROP TABLE IF EXISTS seat_evidence_games;
DROP TABLE IF EXISTS seat_evidence;
DROP TABLE IF EXISTS mod_release_digests;
DROP TABLE IF EXISTS client_compat_events;
DROP TABLE IF EXISTS review_sitting_dirty;
DROP TABLE IF EXISTS review_cursor;

DELETE FROM runtime_settings
 WHERE key IN ('seat_evidence_accept', 'seat_evidence_worker', 'seat_evidence_purge');

COMMIT;
