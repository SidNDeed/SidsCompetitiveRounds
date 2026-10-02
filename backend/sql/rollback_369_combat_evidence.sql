-- rollback_369_combat_evidence.sql
--
-- Removes what 369_combat_evidence.sql added: its four tables and its three
-- seeded runtime switches. No other table has a foreign key into them, so
-- the drop reaches nothing outside them.
--
-- DEPLOY ORDER: THE API FIRST. Deploy an api build without the combat
-- evidence route and combat pass, then run this file. An api that still
-- carries them reads the removed switch rows as off (the combat route answers
-- 503, the combat pass idles), but its admin combat evidence read answers 500
-- against the missing tables.
--
-- It discards every stored combat record, contribution and daily row.
-- Combat findings live in seat_evidence_findings (dedup key prefixed
-- 'combat|') and are removed here too; flagged_matches rows the worker posted
-- are NOT removed (the audit log is append-only).

BEGIN;

DELETE FROM seat_evidence_findings WHERE dedup_key LIKE 'combat|%';
DROP TABLE IF EXISTS combat_player_daily;
DROP TABLE IF EXISTS combat_contrib;
DROP TABLE IF EXISTS combat_games;
DROP TABLE IF EXISTS combat_evidence;

DELETE FROM runtime_settings
 WHERE key IN ('combat_evidence_accept', 'combat_evidence_worker', 'combat_evidence_purge');

COMMIT;
