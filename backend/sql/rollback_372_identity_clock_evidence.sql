-- rollback_372_identity_clock_evidence.sql
--
-- Removes what 372_identity_clock_evidence.sql added: its four tables, the
-- runtime switch rows that file itself inserted, and the review findings of
-- this lane (seat_evidence_findings rows whose dedup key begins with
-- "identity "). Nothing else references the four tables (no other table has
-- a foreign key into them), so the drop reaches nothing outside them.
--
-- The switch rows: 372 records in identity_clock_seeded_keys each key its
-- own insert created (a key that already existed is not recorded), and this
-- file deletes a switch row ONLY when its key is both one of the three and
-- recorded there. A switch row that existed before 372 ran is left in place.
-- Re-runnable: with the ledger already gone, no switch row is deleted, and
-- the findings delete matches nothing a second time.
--
-- DEPLOY ORDER: THE API FIRST. Deploy an api build without the identity-clock
-- routes and worker pass, then run this file. An api that still carries them
-- reads the removed switch rows as off (the route answers 503, the pass
-- idles), but its admin identity-clock view and the game-file registration
-- answer 500 against the missing tables.
--
-- It discards every stored identity-clock record and finding.
-- flagged_matches rows the worker posted are NOT removed (the audit log is
-- append-only). mod_release_digests belongs to 368 and is not touched.

BEGIN;

DO $$
BEGIN
    IF to_regclass('identity_clock_seeded_keys') IS NOT NULL THEN
        DELETE FROM runtime_settings r
         USING identity_clock_seeded_keys k
         WHERE r.key = k.key
           AND r.key IN ('identity_clock_evidence_accept', 'identity_clock_evidence_worker',
                         'identity_clock_evidence_purge');
    END IF;
    IF to_regclass('seat_evidence_findings') IS NOT NULL THEN
        DELETE FROM seat_evidence_findings WHERE dedup_key LIKE 'identity %';
    END IF;
END
$$;

DROP TABLE IF EXISTS identity_clock_games;
DROP TABLE IF EXISTS identity_clock_evidence;
DROP TABLE IF EXISTS game_file_digests;
DROP TABLE IF EXISTS identity_clock_seeded_keys;

COMMIT;
