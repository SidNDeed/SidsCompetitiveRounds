-- rollback_390_combat_evidence.sql
--
-- Removes what 390_combat_evidence.sql added: its five tables (the lane's four
-- and the switch-seed ledger), the runtime switches its own insert seeded (390
-- records those in combat_evidence_seeded_keys; a switch row that existed
-- before 390 ran is left in place), and the value 'combat' of the
-- seat_evidence_findings domain CHECK, put back to 'seat' | 'card' (migration
-- 370's form) once the combat rows are gone. No other table has a foreign key
-- into the five, so the drop reaches nothing outside them (their own keys into
-- players go with them). Re-runnable: with the ledger and the rows already
-- gone, nothing is deleted.
--
-- DEPLOY ORDER: THE API FIRST. Deploy an api build without the combat
-- evidence route and combat pass, then run this file. An api that still
-- carries them reads the removed switch rows as off (the combat route answers
-- 503, the combat pass idles), but its admin combat evidence read answers 500
-- against the missing tables.
--
-- It discards every stored combat record, contribution and daily row.
-- Combat findings live in seat_evidence_findings (scope 'game', dedup key in
-- the combat namespace: it starts with 'combat ' with a space, which no seat
-- evidence dedup key can contain; since 390 they also carry domain 'combat')
-- and are removed here too; every seat and card evidence finding stays. flagged_matches rows the worker posted are NOT
-- removed (the audit log is append-only).

BEGIN;
SET LOCAL lock_timeout = '5s';

-- The domain column exists unless migration 370 was rolled back first; the
-- combat rows are found by their domain and by their key prefix alike.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_attribute
                WHERE attrelid = 'seat_evidence_findings'::regclass
                  AND attname = 'domain' AND NOT attisdropped) THEN
        DELETE FROM seat_evidence_findings
         WHERE domain = 'combat' OR (scope = 'game' AND left(dedup_key, 7) = 'combat ');
        ALTER TABLE seat_evidence_findings DROP CONSTRAINT IF EXISTS seat_evidence_findings_domain;
        ALTER TABLE seat_evidence_findings
            ADD CONSTRAINT seat_evidence_findings_domain CHECK (domain IN ('seat', 'card'));
    ELSE
        DELETE FROM seat_evidence_findings
         WHERE scope = 'game' AND left(dedup_key, 7) = 'combat ';
    END IF;
END
$$;
DROP TABLE IF EXISTS combat_player_daily;
DROP TABLE IF EXISTS combat_contrib;
DROP TABLE IF EXISTS combat_games;
DROP TABLE IF EXISTS combat_evidence;

-- Only the switch rows 390's own insert created, as its ledger records.
DO $$
BEGIN
    IF to_regclass('combat_evidence_seeded_keys') IS NOT NULL THEN
        DELETE FROM runtime_settings r
         USING combat_evidence_seeded_keys k
         WHERE r.key = k.key
           AND r.key IN ('combat_evidence_accept', 'combat_evidence_worker', 'combat_evidence_purge');
    END IF;
END
$$;
DROP TABLE IF EXISTS combat_evidence_seeded_keys;

COMMIT;
