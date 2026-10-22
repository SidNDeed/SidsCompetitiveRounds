-- 389_ffa_exclusion_reasons.sql
-- Store the exclusion reasons applied by an FFA settlement beside its
-- effective absent decision. Existing rows retain NULL; no backfill.
-- Additive schema-only precursor; API code follows in a separate SHA.
-- Idempotent; explicit transaction (learning #340).
-- DEPLOY ORDER: THIS FILE FIRST, then the API, as two SHAs (learning #477).

BEGIN;

ALTER TABLE ffa_match_players
    ADD COLUMN IF NOT EXISTS exclusion_reasons TEXT[];

COMMENT ON COLUMN ffa_match_players.exclusion_reasons IS
    'The reasons the settlement applied to this seat: ghost, grace, asm_a, asm_b, asm_d. '
    'An empty array means none applied. NULL means a row settled before migration 389. '
    'absent remains the effective decision; comparison reuses stored assembly reasons.';

COMMIT;
