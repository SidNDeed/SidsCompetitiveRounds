-- rollback_389_ffa_exclusion_reasons.sql
-- Roll back migration 389 only after the API code that reads or writes
-- exclusion_reasons has been rolled back. NOT a release-train migration.
-- Explicit transaction (learning #340).
-- DEPLOY ORDER: THE API FIRST (roll back readers and writers), then this file.

BEGIN;

ALTER TABLE ffa_match_players
    DROP COLUMN IF EXISTS exclusion_reasons;

COMMIT;
