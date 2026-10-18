-- rollback_384: the inverse of 384_i18n_keys_stage2_hold.sql, for the schema phase
-- before the Stage 2 code lands. Additive-only keys are never DELETED (the proposal and
-- translation tables reference i18n_keys ON DELETE CASCADE, so a delete would remove
-- translators' work): the nine keys 384 introduced are RETIRED, as the sync's retirement
-- sweep retires a key, and the four keys migration 379 created get back the context 379
-- gave them (NULL). A key 384 introduced that no longer carries 384's source_hash is left
-- alone. Idempotent: every statement is guarded by the state it changes. Explicit
-- transaction (#340). Post-check RAISES unless the state is the pre-384 one.

BEGIN;

UPDATE i18n_keys SET retired_at = clock_timestamp(), updated_at = clock_timestamp()
 WHERE namespace = 'client' AND retired_at IS NULL
   AND key_id IN ('fe3e2890029979eb', 'e247d0f66676e2fa', '990a134373f4fe9b', '21a77f99b9e86f48', 'df1814deb572b30b', '5ff81c1cbcb1bc7b', 'dff040f0708dc38d', '690eba24c1191a59');

UPDATE i18n_keys SET context = NULL, updated_at = clock_timestamp()
 WHERE namespace = 'client' AND context IS NOT NULL
   AND key_id IN ('b933f3c706c40e83', '98dca83410faa64d', '66acd1c2d1011708', 'bd57f21b2e779ae1', '5be7e933e570652e');

DO $$
DECLARE
    v_live_added INT;
    v_ctx_left INT;
BEGIN
    SELECT COUNT(*) INTO v_live_added FROM i18n_keys
     WHERE key_id IN ('fe3e2890029979eb', 'e247d0f66676e2fa', '990a134373f4fe9b', '21a77f99b9e86f48', 'df1814deb572b30b', '5ff81c1cbcb1bc7b', 'dff040f0708dc38d', '690eba24c1191a59') AND retired_at IS NULL;
    SELECT COUNT(*) INTO v_ctx_left FROM i18n_keys
     WHERE key_id IN ('b933f3c706c40e83', '98dca83410faa64d', '66acd1c2d1011708', 'bd57f21b2e779ae1', '5be7e933e570652e') AND context IS NOT NULL;
    IF v_live_added <> 0 OR v_ctx_left <> 0 THEN
        RAISE EXCEPTION 'rollback_384 post-check FAILED: % added key(s) still live, % shared key(s) keep a context', v_live_added, v_ctx_left;
    END IF;
    RAISE NOTICE 'rollback_384 post-check OK';
END $$;
COMMIT;
