-- 379: i18n client keys for FFA mid-game readmission (15 NEW keys): the absent-seat automatic
-- pick and its survivor line, the seat-hold, rejoin-offer, back and released lines, the
-- self-kept line, one refusal text per readmission refusal reason, and the late-entry literal
-- "Joining the match at the next point", which moves into I18n in the same change. The
-- continued-without-you refusal text already carries its key (seeded by 184 and 213) and is
-- not repeated here. This is the additive half of what POST /admin/i18n/sync-keys does,
-- written through the migration channel (learning #443). Same contract as 302/312/317:
-- additive-only, key_id = sha1("client\0" + English)[:16], source_hash = sha1(English),
-- sensitive per tools/i18n_sync_keys.py (no marker matches any of these strings). Context is
-- left NULL here: the extractor's surface and location records belong to the client lane, and
-- the real sync tool fills them. Idempotent AND contract-convergent: the conflict arm is the
-- sync endpoint's own full update, and the post-check RAISES if any expected key is missing,
-- retired, or carries a different source_hash or a stray max_px. Explicit transaction (#340).
-- Run order: deploy API, then apply this file, then apply 380.

BEGIN;

INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, max_px, context, updated_at)
SELECT v.key_id, v.namespace, v.msgctxt, v.source_hash, v.sensitive, NULL, v.context, clock_timestamp()
  FROM (VALUES
('01c1ced9ae420dcb', 'client', $k379$Your FFA match is still running. Rejoin? {0}$k379$, 'a09387a2e372ec9a480465c4d160e094e93a97a9', FALSE, CAST(NULL AS VARCHAR(160))),
('29bd0b648d3d1e87', 'client', $k379$You are in another queue$k379$, 'dbfce522b1a9fd91cdefe7ede4251f864eeeb51f', FALSE, CAST(NULL AS VARCHAR(160))),
('45601925442a93f3', 'client', $k379$Joining the match at the next point$k379$, 'ea08b8e2ea3faa610418cbe49c746f47e2190943', FALSE, CAST(NULL AS VARCHAR(160))),
('479ff1480605bff3', 'client', $k379$That match has ended$k379$, '89af1992a09f84e3cfd2e108474917e71cdab03c', FALSE, CAST(NULL AS VARCHAR(160))),
('553c1cb857bf44de', 'client', $k379$Automatic pick: {0}$k379$, '0ef31b05fb51c0f4d4f26373278ece2b440a98f6', FALSE, CAST(NULL AS VARCHAR(160))),
('5be7e933e570652e', 'client', $k379${0} (away) got {1}$k379$, '0afb928a9a1a63e43a466df8800e5bf2db693dab', FALSE, CAST(NULL AS VARCHAR(160))),
('66acd1c2d1011708', 'client', $k379$Could not rejoin at this point$k379$, 'b259a93aa0fdab38481cedea7268c2e454ada899', FALSE, CAST(NULL AS VARCHAR(160))),
('6f660f7ab40c9fb1', 'client', $k379${0} did not return; seat released$k379$, 'dde36fb32699b8f418e4ddd09014d5b814a911d4', FALSE, CAST(NULL AS VARCHAR(160))),
('86fd5a3453cbbbad', 'client', $k379$Could not confirm your seat. Retrying$k379$, 'a946a02658260725c4a859acbedd45aa9f8c9bcf', FALSE, CAST(NULL AS VARCHAR(160))),
('98cb664fca411c1c', 'client', $k379$You left that match$k379$, '58e59499aca516fd0e4882b43fd6ed5781b5b9a8', FALSE, CAST(NULL AS VARCHAR(160))),
('98dca83410faa64d', 'client', $k379$Seat held for {0}: {1}$k379$, '90aaed15747edd34574438630be3c33807ba421f', FALSE, CAST(NULL AS VARCHAR(160))),
('ade21bda2fc0c1a5', 'client', $k379$The seat was released before you returned$k379$, '599201187ca682b14c718c1edf1c2e8f8f1d5919', FALSE, CAST(NULL AS VARCHAR(160))),
('b933f3c706c40e83', 'client', $k379${0} is back$k379$, 'cc3dd7d00b80a320c4d93ae1705baf8de7816bdb', FALSE, CAST(NULL AS VARCHAR(160))),
('bd57f21b2e779ae1', 'client', $k379$You are back in the match$k379$, '812fabb8632244503f103b70e66d722740ae855b', FALSE, CAST(NULL AS VARCHAR(160))),
('c350b64d06ed03ad', 'client', $k379$Another player is using your seat identity$k379$, '26795e3f584178571150f96c7886efc9bfe1cef7', FALSE, CAST(NULL AS VARCHAR(160)))
  ) AS v(key_id, namespace, msgctxt, source_hash, sensitive, context)
ON CONFLICT (key_id) DO UPDATE
   SET namespace = EXCLUDED.namespace, msgctxt = EXCLUDED.msgctxt,
       source_hash = EXCLUDED.source_hash, sensitive = EXCLUDED.sensitive,
       max_px = EXCLUDED.max_px, context = EXCLUDED.context,
       retired_at = NULL, updated_at = clock_timestamp();

-- Post-check (enforcing): every expected key live with the expected source_hash.
DO $$
DECLARE
    v_expected INT := 15;
    v_ok INT;
BEGIN
    SELECT COUNT(*) INTO v_ok
      FROM i18n_keys k
      JOIN (VALUES
        ('01c1ced9ae420dcb', 'a09387a2e372ec9a480465c4d160e094e93a97a9'),
        ('29bd0b648d3d1e87', 'dbfce522b1a9fd91cdefe7ede4251f864eeeb51f'),
        ('45601925442a93f3', 'ea08b8e2ea3faa610418cbe49c746f47e2190943'),
        ('479ff1480605bff3', '89af1992a09f84e3cfd2e108474917e71cdab03c'),
        ('553c1cb857bf44de', '0ef31b05fb51c0f4d4f26373278ece2b440a98f6'),
        ('5be7e933e570652e', '0afb928a9a1a63e43a466df8800e5bf2db693dab'),
        ('66acd1c2d1011708', 'b259a93aa0fdab38481cedea7268c2e454ada899'),
        ('6f660f7ab40c9fb1', 'dde36fb32699b8f418e4ddd09014d5b814a911d4'),
        ('86fd5a3453cbbbad', 'a946a02658260725c4a859acbedd45aa9f8c9bcf'),
        ('98cb664fca411c1c', '58e59499aca516fd0e4882b43fd6ed5781b5b9a8'),
        ('98dca83410faa64d', '90aaed15747edd34574438630be3c33807ba421f'),
        ('ade21bda2fc0c1a5', '599201187ca682b14c718c1edf1c2e8f8f1d5919'),
        ('b933f3c706c40e83', 'cc3dd7d00b80a320c4d93ae1705baf8de7816bdb'),
        ('bd57f21b2e779ae1', '812fabb8632244503f103b70e66d722740ae855b'),
        ('c350b64d06ed03ad', '26795e3f584178571150f96c7886efc9bfe1cef7')
      ) AS e(key_id, source_hash) ON e.key_id = k.key_id
     WHERE k.namespace = 'client' AND k.retired_at IS NULL
       AND k.source_hash = e.source_hash
       AND k.max_px IS NULL;
    IF v_ok <> v_expected THEN
        RAISE EXCEPTION 'post-check FAILED: % of % expected ffa readmission client keys are live with the expected source_hash', v_ok, v_expected;
    END IF;
    RAISE NOTICE 'post-check OK: % ffa readmission client keys live', v_ok;
END $$;

COMMIT;
