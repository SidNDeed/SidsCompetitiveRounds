-- rollback_384 restores only metadata the paired 384 apply owns.
-- Pre-existing keys return byte-equal, including their original updated_at;
-- keys inserted by 384 are retired, never deleted, so entries and proposals
-- survive. A later metadata change, a missing baseline or a missing key makes
-- the whole inverse refuse before either UPDATE. Both directions lock i18n_keys
-- before the ownership table. Repeated inverse runs change no row.
-- Explicit transaction (#340); no game or economy state is read or written.

BEGIN;
LOCK TABLE i18n_keys IN SHARE ROW EXCLUSIVE MODE;
DO $baseline$
BEGIN
    IF to_regclass('i18n_keys_384_ownership') IS NULL THEN
        RAISE EXCEPTION 'rollback_384 ownership baseline missing';
    END IF;
END $baseline$;
LOCK TABLE i18n_keys_384_ownership IN SHARE ROW EXCLUSIVE MODE;

DO $ownership$
BEGIN
    IF (SELECT count(*) FROM i18n_keys_384_ownership
        WHERE key_id IN ('fe3e2890029979eb', 'e247d0f66676e2fa', '990a134373f4fe9b', '21a77f99b9e86f48', 'df1814deb572b30b', '5ff81c1cbcb1bc7b', 'dff040f0708dc38d', '690eba24c1191a59', 'b933f3c706c40e83', '98dca83410faa64d', '66acd1c2d1011708', 'bd57f21b2e779ae1', '5be7e933e570652e')) <> 13 THEN
        RAISE EXCEPTION 'rollback_384 ownership baseline incomplete';
    END IF;
    IF EXISTS (
        SELECT 1 FROM i18n_keys_384_ownership b
        LEFT JOIN i18n_keys k USING (key_id)
        WHERE b.key_id IN ('fe3e2890029979eb', 'e247d0f66676e2fa', '990a134373f4fe9b', '21a77f99b9e86f48', 'df1814deb572b30b', '5ff81c1cbcb1bc7b', 'dff040f0708dc38d', '690eba24c1191a59', 'b933f3c706c40e83', '98dca83410faa64d', '66acd1c2d1011708', 'bd57f21b2e779ae1', '5be7e933e570652e')
          AND (b.owned IS NULL
               OR (b.active AND to_jsonb(k) IS DISTINCT FROM b.owned)
               OR (NOT b.active AND to_jsonb(k) IS DISTINCT FROM b.reversed))
    ) THEN
        RAISE EXCEPTION 'rollback_384 ownership mismatch before inverse';
    END IF;
END $ownership$;

UPDATE i18n_keys k
   SET retired_at = clock_timestamp(), updated_at = clock_timestamp()
  FROM i18n_keys_384_ownership b
 WHERE k.key_id = b.key_id AND b.key_id IN ('fe3e2890029979eb', 'e247d0f66676e2fa', '990a134373f4fe9b', '21a77f99b9e86f48', 'df1814deb572b30b', '5ff81c1cbcb1bc7b', 'dff040f0708dc38d', '690eba24c1191a59', 'b933f3c706c40e83', '98dca83410faa64d', '66acd1c2d1011708', 'bd57f21b2e779ae1', '5be7e933e570652e')
   AND b.active AND b.baseline IS NULL
   AND to_jsonb(k) = b.owned;

UPDATE i18n_keys k
   SET namespace = s.namespace, msgctxt = s.msgctxt,
       source_hash = s.source_hash, sensitive = s.sensitive,
       max_px = s.max_px, context = s.context,
       retired_at = s.retired_at, updated_at = s.updated_at
  FROM i18n_keys_384_ownership b
 CROSS JOIN LATERAL jsonb_populate_record(NULL::i18n_keys, b.baseline) AS s
 WHERE k.key_id = b.key_id AND b.key_id IN ('fe3e2890029979eb', 'e247d0f66676e2fa', '990a134373f4fe9b', '21a77f99b9e86f48', 'df1814deb572b30b', '5ff81c1cbcb1bc7b', 'dff040f0708dc38d', '690eba24c1191a59', 'b933f3c706c40e83', '98dca83410faa64d', '66acd1c2d1011708', 'bd57f21b2e779ae1', '5be7e933e570652e')
   AND b.active AND b.baseline IS NOT NULL
   AND to_jsonb(k) = b.owned;

UPDATE i18n_keys_384_ownership b
   SET reversed = to_jsonb(k), active = FALSE
  FROM i18n_keys k
 WHERE k.key_id = b.key_id AND b.key_id IN ('fe3e2890029979eb', 'e247d0f66676e2fa', '990a134373f4fe9b', '21a77f99b9e86f48', 'df1814deb572b30b', '5ff81c1cbcb1bc7b', 'dff040f0708dc38d', '690eba24c1191a59', 'b933f3c706c40e83', '98dca83410faa64d', '66acd1c2d1011708', 'bd57f21b2e779ae1', '5be7e933e570652e')
   AND b.active;

DO $proof$
BEGIN
    IF EXISTS (
        SELECT 1 FROM i18n_keys_384_ownership b
        LEFT JOIN i18n_keys k USING (key_id)
        WHERE b.key_id IN ('fe3e2890029979eb', 'e247d0f66676e2fa', '990a134373f4fe9b', '21a77f99b9e86f48', 'df1814deb572b30b', '5ff81c1cbcb1bc7b', 'dff040f0708dc38d', '690eba24c1191a59', 'b933f3c706c40e83', '98dca83410faa64d', '66acd1c2d1011708', 'bd57f21b2e779ae1', '5be7e933e570652e')
          AND (b.active OR to_jsonb(k) IS DISTINCT FROM b.reversed
               OR (b.baseline IS NOT NULL AND b.reversed IS DISTINCT FROM b.baseline)
               OR (b.baseline IS NULL AND
                   (k.retired_at IS NULL OR
                    (to_jsonb(k) - 'retired_at' - 'updated_at') IS DISTINCT FROM
                    (b.owned - 'retired_at' - 'updated_at'))))
    ) THEN
        RAISE EXCEPTION 'rollback_384 post-check FAILED for owned metadata';
    END IF;
    RAISE NOTICE 'rollback_384 post-check OK';
END $proof$;
COMMIT;
