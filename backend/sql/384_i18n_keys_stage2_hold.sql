-- 384: i18n client keys for 2v2 and 1v2 mid-game readmission (Stage 2 design V3,
-- S2, S3 and S4; 13 keys): the hold banner and its states, the rejoin offer with its
-- two answers ("Rejoin", "Not now"), the failed and completed entry, and the away-seat
-- pick line. This is the additive half of what POST /admin/i18n/sync-keys does, written
-- through the migration channel (learning #443). Same contract as 317: additive-only,
-- key_id = sha1("client\0" + English)[:16], source_hash = sha1(English), sensitive per
-- tools/i18n_sync_keys.py (none of these matches a marker).
--
-- Twelve keys are the KX7 extract of the Stage 2 client refit (refit notes row 29):
-- eight new, and four that migration 379 (FFA readmission) already inserted and that the
-- Stage 2 surfaces now share ("{0} is back", "Seat held for {0}: {1}", "Could not rejoin
-- at this point", "You are back in the match"). The thirteenth, "{0} (away) got {1}",
-- was also inserted by 379; no Stage 2 client site emits it (the FFA client's
-- ApplyManifestPick does), and it is kept here as the away-seat pick line. Each context
-- is the one tools/i18n_sync_keys.client_context derives from the refit extract, so this
-- file and the next sync write the same row.
--
-- IDEMPOTENT, and how: the conflict arm updates a row only WHERE it differs from the
-- value written here (IS DISTINCT FROM over every column the arm sets, retired_at
-- included), so the re-insert of the five keys 379 created changes exactly their context
-- once, and a second run of this file writes no row at all (updated_at included). The
-- A durable 384 ownership record keeps exact predecessor metadata for the inverse;
-- later source or context edits are refused before another forward overwrite.
-- The file unconditionally issues LOCK TABLE, INSERT INTO and UPDATE statements;
-- CREATE TABLE is guarded. The post-check RAISES unless every expected key is live
-- with the expected source_hash and
-- context and no max_px. Explicit transaction (#340). Run order: deploy API -> apply
-- this file -> apply 385. Inverse: rollback_384_i18n_keys_stage2_hold.sql.

BEGIN;

-- Capture the exact predecessor before the first overwrite. Keep it across
-- repeated apply/inverse cycles; it also preserves the original updated_at.
-- The same table order in both directions serializes metadata writers.
LOCK TABLE i18n_keys IN SHARE ROW EXCLUSIVE MODE;
CREATE TABLE IF NOT EXISTS i18n_keys_384_ownership (
    key_id VARCHAR(16) PRIMARY KEY,
    baseline JSONB,
    owned JSONB,
    reversed JSONB,
    active BOOLEAN NOT NULL DEFAULT FALSE
);
LOCK TABLE i18n_keys_384_ownership IN SHARE ROW EXCLUSIVE MODE;

INSERT INTO i18n_keys_384_ownership (key_id, baseline)
SELECT e.key_id, to_jsonb(k)
  FROM unnest(ARRAY['fe3e2890029979eb', 'e247d0f66676e2fa', '990a134373f4fe9b', '21a77f99b9e86f48', 'df1814deb572b30b', '5ff81c1cbcb1bc7b', 'dff040f0708dc38d', '690eba24c1191a59', 'b933f3c706c40e83', '98dca83410faa64d', '66acd1c2d1011708', 'bd57f21b2e779ae1', '5be7e933e570652e']::varchar[]) AS e(key_id)
  LEFT JOIN i18n_keys k USING (key_id)
ON CONFLICT (key_id) DO NOTHING;

DO $ownership$
BEGIN
    -- A repeat may revive an otherwise unchanged key, as the forward contract
    -- already permits. Changed source, context or other metadata is not owned.
    IF EXISTS (
        SELECT 1 FROM i18n_keys_384_ownership b
        LEFT JOIN i18n_keys k USING (key_id)
        WHERE b.key_id IN ('fe3e2890029979eb', 'e247d0f66676e2fa', '990a134373f4fe9b', '21a77f99b9e86f48', 'df1814deb572b30b', '5ff81c1cbcb1bc7b', 'dff040f0708dc38d', '690eba24c1191a59', 'b933f3c706c40e83', '98dca83410faa64d', '66acd1c2d1011708', 'bd57f21b2e779ae1', '5be7e933e570652e') AND b.owned IS NOT NULL
          AND ((b.active AND
                (to_jsonb(k) - 'retired_at' - 'updated_at') IS DISTINCT FROM
                (b.owned - 'retired_at' - 'updated_at'))
               OR (NOT b.active AND to_jsonb(k) IS DISTINCT FROM b.reversed))
    ) THEN
        RAISE EXCEPTION '384 ownership mismatch before apply';
    END IF;
END $ownership$;


INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, max_px, context, updated_at)
SELECT v.key_id, v.namespace, v.msgctxt, v.source_hash, v.sensitive, NULL, v.context, clock_timestamp()
  FROM (VALUES
('fe3e2890029979eb', 'client', $k384$Another player left. The match ends as a disconnect.$k384$, '07b5dcb71a45699b4b3a8cf0402f48cfe3485d91', FALSE, $k384$TeamHoldBanner · Line$k384$),
('e247d0f66676e2fa', 'client', $k384$Checking whether {0} can rejoin$k384$, '6ef502c0684ae18a7d85f5fb02a9a9d27c39c120', FALSE, $k384$TeamHoldBanner · Line$k384$),
('990a134373f4fe9b', 'client', $k384$Not now$k384$, 'e45714907316a161b3c502a4678cf42c0f4824d9', FALSE, $k384$TeamHoldReturn · DrawOffer$k384$),
('21a77f99b9e86f48', 'client', $k384$Press Esc to leave. The match then ends as a disconnect.$k384$, '30a77f9e3bf9ae019331df0d619b7df314378a26', FALSE, $k384$TeamHoldBanner · Line$k384$),
('df1814deb572b30b', 'client', $k384$Rejoin$k384$, 'c6240d696b95c7450d1dc0c394d5227906e04ab2', FALSE, $k384$TeamHoldReturn · DrawOffer$k384$),
('5ff81c1cbcb1bc7b', 'client', $k384$Your match is still running. Rejoin? {0}$k384$, '3bddba2aa07f0439693aac97861343544b2aa635', FALSE, $k384$TeamHoldReturn · DrawOffer$k384$),
('dff040f0708dc38d', 'client', $k384${0} did not return. The match ends as a disconnect.$k384$, '7648b75aafbc51b1bbd6a7cf069caa774fac6b5e', FALSE, $k384$TeamHoldBanner · Line$k384$),
('690eba24c1191a59', 'client', $k384${0} is rejoining$k384$, '37a2e787a323c769817b4d2446d54a8b45a264f3', FALSE, $k384$TeamHoldBanner · Line$k384$),
('b933f3c706c40e83', 'client', $k384${0} is back$k384$, 'cc3dd7d00b80a320c4d93ae1705baf8de7816bdb', FALSE, $k384$FfaLateEntry, TeamHoldBanner · AfterPair, Line$k384$),
('98dca83410faa64d', 'client', $k384$Seat held for {0}: {1}$k384$, '90aaed15747edd34574438630be3c33807ba421f', FALSE, $k384$FfaReadmit, TeamHoldBanner · Line, OnHoldsAnswer$k384$),
('66acd1c2d1011708', 'client', $k384$Could not rejoin at this point$k384$, 'b259a93aa0fdab38481cedea7268c2e454ada899', FALSE, $k384$FfaReadmit, TeamHoldReturn · End, Refusal$k384$),
('bd57f21b2e779ae1', 'client', $k384$You are back in the match$k384$, '812fabb8632244503f103b70e66d722740ae855b', FALSE, $k384$FfaLateEntry, TeamHoldReturn · Finish, OnSelfKept$k384$),
('5be7e933e570652e', 'client', $k384${0} (away) got {1}$k384$, '0afb928a9a1a63e43a466df8800e5bf2db693dab', FALSE, $k384$FfaMode · ApplyManifestPick$k384$)
  ) AS v(key_id, namespace, msgctxt, source_hash, sensitive, context)
ON CONFLICT (key_id) DO UPDATE
   SET namespace = EXCLUDED.namespace, msgctxt = EXCLUDED.msgctxt,
       source_hash = EXCLUDED.source_hash, sensitive = EXCLUDED.sensitive,
       max_px = EXCLUDED.max_px, context = EXCLUDED.context,
       retired_at = NULL, updated_at = clock_timestamp()
 WHERE (i18n_keys.namespace, i18n_keys.msgctxt, i18n_keys.source_hash, i18n_keys.sensitive,
        i18n_keys.max_px, i18n_keys.context, i18n_keys.retired_at)
       IS DISTINCT FROM
       (EXCLUDED.namespace, EXCLUDED.msgctxt, EXCLUDED.source_hash, EXCLUDED.sensitive,
        EXCLUDED.max_px, EXCLUDED.context, CAST(NULL AS TIMESTAMPTZ));
-- Post-check (enforcing): every expected key live with the expected source_hash and context.
DO $$
DECLARE
    v_expected INT := 13;
    v_ok INT;
BEGIN
    SELECT COUNT(*) INTO v_ok
      FROM i18n_keys k
      JOIN (VALUES
        ('fe3e2890029979eb', '07b5dcb71a45699b4b3a8cf0402f48cfe3485d91', $k384$TeamHoldBanner · Line$k384$),
        ('e247d0f66676e2fa', '6ef502c0684ae18a7d85f5fb02a9a9d27c39c120', $k384$TeamHoldBanner · Line$k384$),
        ('990a134373f4fe9b', 'e45714907316a161b3c502a4678cf42c0f4824d9', $k384$TeamHoldReturn · DrawOffer$k384$),
        ('21a77f99b9e86f48', '30a77f9e3bf9ae019331df0d619b7df314378a26', $k384$TeamHoldBanner · Line$k384$),
        ('df1814deb572b30b', 'c6240d696b95c7450d1dc0c394d5227906e04ab2', $k384$TeamHoldReturn · DrawOffer$k384$),
        ('5ff81c1cbcb1bc7b', '3bddba2aa07f0439693aac97861343544b2aa635', $k384$TeamHoldReturn · DrawOffer$k384$),
        ('dff040f0708dc38d', '7648b75aafbc51b1bbd6a7cf069caa774fac6b5e', $k384$TeamHoldBanner · Line$k384$),
        ('690eba24c1191a59', '37a2e787a323c769817b4d2446d54a8b45a264f3', $k384$TeamHoldBanner · Line$k384$),
        ('b933f3c706c40e83', 'cc3dd7d00b80a320c4d93ae1705baf8de7816bdb', $k384$FfaLateEntry, TeamHoldBanner · AfterPair, Line$k384$),
        ('98dca83410faa64d', '90aaed15747edd34574438630be3c33807ba421f', $k384$FfaReadmit, TeamHoldBanner · Line, OnHoldsAnswer$k384$),
        ('66acd1c2d1011708', 'b259a93aa0fdab38481cedea7268c2e454ada899', $k384$FfaReadmit, TeamHoldReturn · End, Refusal$k384$),
        ('bd57f21b2e779ae1', '812fabb8632244503f103b70e66d722740ae855b', $k384$FfaLateEntry, TeamHoldReturn · Finish, OnSelfKept$k384$),
        ('5be7e933e570652e', '0afb928a9a1a63e43a466df8800e5bf2db693dab', $k384$FfaMode · ApplyManifestPick$k384$)
      ) AS e(key_id, source_hash, context) ON e.key_id = k.key_id
     WHERE k.namespace = 'client' AND k.retired_at IS NULL
       AND k.source_hash = e.source_hash
       AND k.max_px IS NULL AND k.context IS NOT DISTINCT FROM e.context;
    IF v_ok <> v_expected THEN
        RAISE EXCEPTION 'post-check FAILED: % of % expected stage 2 hold client keys are live with the expected source_hash and context', v_ok, v_expected;
    END IF;
    RAISE NOTICE 'post-check OK: % stage 2 hold client keys live', v_ok;
END $$;
-- Record only rows the post-check proved, inside the same transaction.
UPDATE i18n_keys_384_ownership b
   SET owned = to_jsonb(k), active = TRUE
  FROM i18n_keys k
 WHERE k.key_id = b.key_id AND b.key_id IN ('fe3e2890029979eb', 'e247d0f66676e2fa', '990a134373f4fe9b', '21a77f99b9e86f48', 'df1814deb572b30b', '5ff81c1cbcb1bc7b', 'dff040f0708dc38d', '690eba24c1191a59', 'b933f3c706c40e83', '98dca83410faa64d', '66acd1c2d1011708', 'bd57f21b2e779ae1', '5be7e933e570652e')
   AND (NOT b.active OR b.owned IS DISTINCT FROM to_jsonb(k));

COMMIT;
