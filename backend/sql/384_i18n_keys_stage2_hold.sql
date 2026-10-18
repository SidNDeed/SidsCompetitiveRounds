-- 384: i18n client keys for 2v2 and 1v2 mid-game readmission (Stage 2 design V3,
-- S2, S3 and S4; 11 NEW keys): the hold banner and its states, the rejoin offer, the
-- failed and completed entry, and the away-seat pick line. This is the additive half of
-- what POST /admin/i18n/sync-keys does, written through the migration channel (learning
-- #443). Same contract as 317: additive-only, key_id = sha1("client\0" + English)[:16],
-- source_hash = sha1(English), sensitive per tools/i18n_sync_keys.py (none of these
-- matches a marker), context provisional until the client extract of the Stage 2 client
-- lane names its surface (the conflict arm is the sync endpoint's own full update, so the
-- next sync converges it). Idempotent AND contract-convergent: the post-check RAISES if
-- any expected key is missing, retired, or carries a different source_hash or context or
-- a stray max_px. Explicit transaction (#340). Run order: deploy API -> apply this file
-- -> apply 385.

BEGIN;

INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, max_px, context, updated_at)
SELECT v.key_id, v.namespace, v.msgctxt, v.source_hash, v.sensitive, NULL, v.context, clock_timestamp()
  FROM (VALUES
('98dca83410faa64d', 'client', $k384$Seat held for {0}: {1}$k384$, '90aaed15747edd34574438630be3c33807ba421f', FALSE, E'MatchHold · banner'),
('21a77f99b9e86f48', 'client', $k384$Press Esc to leave. The match then ends as a disconnect.$k384$, '30a77f9e3bf9ae019331df0d619b7df314378a26', FALSE, E'MatchHold · banner'),
('e247d0f66676e2fa', 'client', $k384$Checking whether {0} can rejoin$k384$, '6ef502c0684ae18a7d85f5fb02a9a9d27c39c120', FALSE, E'MatchHold · banner'),
('690eba24c1191a59', 'client', $k384${0} is rejoining$k384$, '37a2e787a323c769817b4d2446d54a8b45a264f3', FALSE, E'MatchHold · banner'),
('b933f3c706c40e83', 'client', $k384${0} is back$k384$, 'cc3dd7d00b80a320c4d93ae1705baf8de7816bdb', FALSE, E'MatchHold · banner'),
('dff040f0708dc38d', 'client', $k384${0} did not return. The match ends as a disconnect.$k384$, '7648b75aafbc51b1bbd6a7cf069caa774fac6b5e', FALSE, E'MatchHold · banner'),
('fe3e2890029979eb', 'client', $k384$Another player left. The match ends as a disconnect.$k384$, '07b5dcb71a45699b4b3a8cf0402f48cfe3485d91', FALSE, E'MatchHold · banner'),
('5ff81c1cbcb1bc7b', 'client', $k384$Your match is still running. Rejoin? {0}$k384$, '3bddba2aa07f0439693aac97861343544b2aa635', FALSE, E'MatchHold · discovery'),
('66acd1c2d1011708', 'client', $k384$Could not rejoin at this point$k384$, 'b259a93aa0fdab38481cedea7268c2e454ada899', FALSE, E'MatchHold · entry'),
('bd57f21b2e779ae1', 'client', $k384$You are back in the match$k384$, '812fabb8632244503f103b70e66d722740ae855b', FALSE, E'MatchHold · entry'),
('5be7e933e570652e', 'client', $k384${0} (away) got {1}$k384$, '0afb928a9a1a63e43a466df8800e5bf2db693dab', FALSE, E'MatchHold · picks')
  ) AS v(key_id, namespace, msgctxt, source_hash, sensitive, context)
ON CONFLICT (key_id) DO UPDATE
   SET namespace = EXCLUDED.namespace, msgctxt = EXCLUDED.msgctxt,
       source_hash = EXCLUDED.source_hash, sensitive = EXCLUDED.sensitive,
       max_px = EXCLUDED.max_px, context = EXCLUDED.context,
       retired_at = NULL, updated_at = clock_timestamp();
-- Post-check (enforcing): every expected key live with the expected source_hash and context.
DO $$
DECLARE
    v_expected INT := 11;
    v_ok INT;
BEGIN
    SELECT COUNT(*) INTO v_ok
      FROM i18n_keys k
      JOIN (VALUES
        ('98dca83410faa64d', '90aaed15747edd34574438630be3c33807ba421f', E'MatchHold · banner'),
        ('21a77f99b9e86f48', '30a77f9e3bf9ae019331df0d619b7df314378a26', E'MatchHold · banner'),
        ('e247d0f66676e2fa', '6ef502c0684ae18a7d85f5fb02a9a9d27c39c120', E'MatchHold · banner'),
        ('690eba24c1191a59', '37a2e787a323c769817b4d2446d54a8b45a264f3', E'MatchHold · banner'),
        ('b933f3c706c40e83', 'cc3dd7d00b80a320c4d93ae1705baf8de7816bdb', E'MatchHold · banner'),
        ('dff040f0708dc38d', '7648b75aafbc51b1bbd6a7cf069caa774fac6b5e', E'MatchHold · banner'),
        ('fe3e2890029979eb', '07b5dcb71a45699b4b3a8cf0402f48cfe3485d91', E'MatchHold · banner'),
        ('5ff81c1cbcb1bc7b', '3bddba2aa07f0439693aac97861343544b2aa635', E'MatchHold · discovery'),
        ('66acd1c2d1011708', 'b259a93aa0fdab38481cedea7268c2e454ada899', E'MatchHold · entry'),
        ('bd57f21b2e779ae1', '812fabb8632244503f103b70e66d722740ae855b', E'MatchHold · entry'),
        ('5be7e933e570652e', '0afb928a9a1a63e43a466df8800e5bf2db693dab', E'MatchHold · picks')
      ) AS e(key_id, source_hash, context) ON e.key_id = k.key_id
     WHERE k.namespace = 'client' AND k.retired_at IS NULL
       AND k.source_hash = e.source_hash
       AND k.max_px IS NULL AND k.context IS NOT DISTINCT FROM e.context;
    IF v_ok <> v_expected THEN
        RAISE EXCEPTION 'post-check FAILED: % of % expected stage 2 hold client keys are live with the expected source_hash and context', v_ok, v_expected;
    END IF;
    RAISE NOTICE 'post-check OK: % stage 2 hold client keys live', v_ok;
END $$;
COMMIT;
