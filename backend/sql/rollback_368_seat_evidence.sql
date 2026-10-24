-- rollback_368_seat_evidence.sql
--
-- Removes what 368_seat_evidence.sql added: its nine tables and the runtime
-- switch rows that file itself inserted. Nothing else references these
-- tables (no other table has a foreign key into them), so the drop reaches
-- nothing outside them.
--
-- ASSUMPTION, stated and guarded: the three switch keys seat_evidence_accept,
-- seat_evidence_worker and seat_evidence_purge are owned by this feature.
-- The guard does not rely on that: 368 records in seat_evidence_seeded_keys
-- each key its own insert created (a key that already existed is not
-- recorded), and this file deletes a switch row ONLY when its key is both
-- one of the three and recorded there. A switch row that existed before 368
-- ran is left in place. Re-runnable: with the ledger already gone, no row is
-- deleted.
--
-- DEPLOY ORDER: THE API FIRST. Deploy an api build without the seat-evidence
-- routes and worker, then run this file. An api that still carries them reads
-- the removed switch rows as off (the seat route and the compat route answer
-- 503, the worker idles), but its admin seat-evidence view and digest
-- registration answer 500 against the missing tables.
--
-- It discards every stored seat record and finding. flagged_matches rows the
-- worker posted are NOT removed (the audit log is append-only).

BEGIN;
SET LOCAL lock_timeout = '5s';

DO $$
BEGIN
    IF to_regclass('seat_evidence_seeded_keys') IS NOT NULL THEN
        DELETE FROM runtime_settings r
         USING seat_evidence_seeded_keys k
         WHERE r.key = k.key
           AND r.key IN ('seat_evidence_accept', 'seat_evidence_worker', 'seat_evidence_purge');
    END IF;
END
$$;

DROP TABLE IF EXISTS seat_evidence_findings;
DROP TABLE IF EXISTS seat_evidence_games;
DROP TABLE IF EXISTS seat_evidence;
DROP TABLE IF EXISTS mod_release_digests;
DROP TABLE IF EXISTS client_compat_events;
DROP TABLE IF EXISTS review_sitting_dirty;
DROP TABLE IF EXISTS review_seen;
DROP TABLE IF EXISTS review_cursor;
DROP TABLE IF EXISTS seat_evidence_seeded_keys;

COMMIT;
