-- 186: distinguish REAL lobby settings from migration-176 defaults.
--
-- Codex review of the FFA-history settings feature: migration 176 added
-- score_target/card_cap/initial_picks/card_candidates/same_card_rule to
-- ffa_lobbies as NOT NULL DEFAULT columns, so every lobby that existed
-- BEFORE the configurable-lobby feature now carries a full, plausible-looking
-- config it was never played under. Early FFA games were first-to-3, but
-- those rows read score_target = 5.
--
-- Showing that in match history would be worse than showing nothing: a player
-- reading their own history would see a win target the game did not use. This
-- flag lets the API return "unknown" for those matches instead.
--
-- Cutoff is the 176 deployment (2026-08-01). A lobby created before then
-- cannot have had its settings chosen by a host, because no UI existed.
ALTER TABLE ffa_lobbies
    ADD COLUMN IF NOT EXISTS settings_known BOOLEAN NOT NULL DEFAULT TRUE;

DO $$
DECLARE marked INT;
BEGIN
    -- Idempotent by construction: re-running re-marks the same historical
    -- rows and touches nothing created after the cutoff.
    UPDATE ffa_lobbies
       SET settings_known = FALSE
     WHERE created_at < TIMESTAMPTZ '2026-08-01 00:00:00+00';
    GET DIAGNOSTICS marked = ROW_COUNT;
    RAISE NOTICE 'migration 186 OK: % pre-config lobbies marked settings_known=FALSE', marked;
END $$;
