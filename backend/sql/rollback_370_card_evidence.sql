-- rollback_370_card_evidence.sql
--
-- Removes what 370_card_evidence.sql added: its eight tables, the card
-- findings it caused in seat_evidence_findings (dedup keys beginning
-- 'card|' that were never posted), and the runtime switch rows that file
-- itself inserted. Nothing else references these tables (no other table has
-- a foreign key into them), so the drop reaches nothing outside them.
--
-- ASSUMPTION, stated and guarded: the three switch keys card_evidence_accept,
-- card_evidence_worker and card_evidence_purge are owned by this feature.
-- The guard does not rely on that: 370 records in card_evidence_seeded_keys
-- each key its own insert created (a key that already existed is not
-- recorded), and this file deletes a switch row ONLY when its key is both one
-- of the three and recorded there. A switch row that existed before 370 ran
-- is left in place. Re-runnable: with the ledger already gone, no row is
-- deleted.
--
-- DEPLOY ORDER: THE API FIRST. Deploy an api build without the card route and
-- the card pass, then run this file. An api that still carries them reads the
-- removed switch rows as off (the card route answers 503, the card pass
-- idles), but its admin card read and census registration answer 500 against
-- the missing tables.
--
-- It discards every stored card record, census and derived row.
-- flagged_matches rows the worker posted are NOT removed (the audit log is
-- append-only), and neither is the finding row a posted flag points at.

BEGIN;

DO $$
BEGIN
    IF to_regclass('card_evidence_seeded_keys') IS NOT NULL THEN
        DELETE FROM runtime_settings r
         USING card_evidence_seeded_keys k
         WHERE r.key = k.key
           AND r.key IN ('card_evidence_accept', 'card_evidence_worker', 'card_evidence_purge');
    END IF;
    IF to_regclass('seat_evidence_findings') IS NOT NULL THEN
        DELETE FROM seat_evidence_findings
         WHERE dedup_key LIKE 'card|%' AND flag_id IS NULL;
    END IF;
END
$$;

DROP TABLE IF EXISTS card_player_daily;
DROP TABLE IF EXISTS card_contrib;
DROP TABLE IF EXISTS card_phase_outside;
DROP TABLE IF EXISTS card_hand_outside;
DROP TABLE IF EXISTS card_games;
DROP TABLE IF EXISTS card_pool_registry;
DROP TABLE IF EXISTS card_evidence;
DROP TABLE IF EXISTS card_evidence_seeded_keys;

COMMIT;
