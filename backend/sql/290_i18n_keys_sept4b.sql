-- 290: i18n client keys for the Sept 4 batch (H2H + lag notices) (19 NEW keys): the head-to-head
-- banner / Tab-Info header (with its relative-date words), the lag-notice
-- toasts and their Settings toggle. This is the additive half of
-- what POST /admin/i18n/sync-keys does, written through the migration channel
-- because this seat's tooling cannot sign the admin HMAC (learning #443).
-- Additive-only (per 248/266/282/286/288 precedent): no existing string was
-- reworded by this batch (the extractor diff shows 0 REMOVED), so nothing is
-- left for the real sync tool's retire pass.
-- key_id = sha1("client\0" + English)[:16], source_hash = sha1(English),
-- sensitive per tools/i18n_sync_keys.py's SENSITIVE_MARKERS (imported, not
-- copied). Idempotent AND contract-convergent: the conflict arm is the sync
-- endpoint's own full update, and the post-check RAISES if any expected key is
-- missing, retired, or carries a different source_hash / a stray max_px or
-- context. Explicit transaction (#340). The game namespace is unchanged.
-- Run order: deploy API -> apply this file -> apply 291.

BEGIN;

INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, max_px, context, updated_at)
SELECT v.key_id, v.namespace, v.msgctxt, v.source_hash, v.sensitive, NULL, NULL, NOW()
  FROM (VALUES
('02b8b22e38fd50f7', 'client', $k290$Lag notices: <color=#FF9966>OFF</color>$k290$, '252303c6d39a40dd7f036c76f80bb69f75ae36c2', FALSE),
('08c937803617523a', 'client', $k290$First time playing {0}$k290$, '74fa1fc2c0fd51e84fa8dcc155709d41c66be2bb', FALSE),
('285d7e4d5c39d2b2', 'client', $k290$Your game is dropping frames (worst {0} ms)$k290$, '586d2a346956f0f867bcd4d3f641fe92cf790371', FALSE),
('3b76eb04250b37e5', 'client', $k290${0} months ago$k290$, '3c784acc314dd9a21178a33cfb55e12ab4f6711a', FALSE),
('458e4de1c2f8d9ab', 'client', $k290$Your ping to the relay is high ({0} ms)$k290$, '4c19162ad3fa67a9827c74dad8dbf9162e282948', FALSE),
('5366e6d1aa97a268', 'client', $k290${0} years ago$k290$, '9a3274443563edf3bd9c07afa970a039ce5ea98f', FALSE),
('645e3d3f657b13e7', 'client', $k290$Last played {0} · H2H {1}-{2} · Ranked series {3}$k290$, 'a3f322bfc21229baf76a1294517e9f556f824da8', TRUE),
('658c8881ff4b6496', 'client', $k290$yesterday$k290$, '1aa96b8f44f6515a65f3c132ce1b8842a9bd9e87', FALSE),
('7aeac17f502399de', 'client', $k290$Lag notices: <color=#88FF88>ON</color>$k290$, 'c78f63a157a29ab1fd6afca0ef577b84acf8764d', FALSE),
('98e4a76eed695306', 'client', $k290$Opponent reports {0} ms ping$k290$, '02ceb2093b5bcc236bd9551a871fa0884433fade', FALSE),
('9b0b5e78093b80dd', 'client', $k290$Opponent's updates are arriving late (in transit)$k290$, 'e5336e6106c1b000895725fd8ac765b349047068', FALSE),
('adce3a775476d686', 'client', $k290$Last played {0} · also played today · H2H {1}-{2} · Ranked series {3}$k290$, 'b7248097e6ae78ea75acdc1bf03fa3a7f754fae1', TRUE),
('bb67c219422bc077', 'client', $k290${0} weeks ago$k290$, '93a527feb58430dacc2462c4e3aec2f6dfc49791', FALSE),
('bf4ae830222e69d8', 'client', $k290$a year ago$k290$, '2e8849fcb4982de44770ca02f39c8751143b02c2', FALSE),
('c9e4dc142533d543', 'client', $k290$First played today · H2H {0}-{1} · Ranked series {2}$k290$, 'ce9fc34778b41ce8ab57abb9ce88121448338b54', TRUE),
('cd2c0619969e467e', 'client', $k290$Unknown player$k290$, 'bd7fbc1b4636f43e27e5a99f7b58bc58494bf97a', FALSE),
('d00d1cf6fc532cd8', 'client', $k290${0} days ago$k290$, '9344533c4118c35c73e68a704ed70271514f9211', FALSE),
('f6f39272fe6447ee', 'client', $k290$Corner notices when your frames drop, your ping is high or the opponent's updates arrive late. 1v1 only.$k290$, '2c8c0c76f27b62f1dbb24cb436ae7a2d42c026db', FALSE),
('fb918ff938758326', 'client', $k290$H2H {0}-{1} · Ranked series {2}$k290$, 'a3e238ceb8c700ef33b1f0452b098d04a5fe0579', TRUE)
  ) AS v(key_id, namespace, msgctxt, source_hash, sensitive)
ON CONFLICT (key_id) DO UPDATE
   SET namespace = EXCLUDED.namespace, msgctxt = EXCLUDED.msgctxt,
       source_hash = EXCLUDED.source_hash, sensitive = EXCLUDED.sensitive,
       max_px = EXCLUDED.max_px, context = EXCLUDED.context,
       retired_at = NULL, updated_at = NOW();

-- Post-check (enforcing): every expected key live with the expected source_hash.
DO $$
DECLARE
    v_expected INT := 19;
    v_ok INT;
BEGIN
    SELECT COUNT(*) INTO v_ok
      FROM i18n_keys k
      JOIN (VALUES
        ('02b8b22e38fd50f7', '252303c6d39a40dd7f036c76f80bb69f75ae36c2'),
        ('08c937803617523a', '74fa1fc2c0fd51e84fa8dcc155709d41c66be2bb'),
        ('285d7e4d5c39d2b2', '586d2a346956f0f867bcd4d3f641fe92cf790371'),
        ('3b76eb04250b37e5', '3c784acc314dd9a21178a33cfb55e12ab4f6711a'),
        ('458e4de1c2f8d9ab', '4c19162ad3fa67a9827c74dad8dbf9162e282948'),
        ('5366e6d1aa97a268', '9a3274443563edf3bd9c07afa970a039ce5ea98f'),
        ('645e3d3f657b13e7', 'a3f322bfc21229baf76a1294517e9f556f824da8'),
        ('658c8881ff4b6496', '1aa96b8f44f6515a65f3c132ce1b8842a9bd9e87'),
        ('7aeac17f502399de', 'c78f63a157a29ab1fd6afca0ef577b84acf8764d'),
        ('98e4a76eed695306', '02ceb2093b5bcc236bd9551a871fa0884433fade'),
        ('9b0b5e78093b80dd', 'e5336e6106c1b000895725fd8ac765b349047068'),
        ('adce3a775476d686', 'b7248097e6ae78ea75acdc1bf03fa3a7f754fae1'),
        ('bb67c219422bc077', '93a527feb58430dacc2462c4e3aec2f6dfc49791'),
        ('bf4ae830222e69d8', '2e8849fcb4982de44770ca02f39c8751143b02c2'),
        ('c9e4dc142533d543', 'ce9fc34778b41ce8ab57abb9ce88121448338b54'),
        ('cd2c0619969e467e', 'bd7fbc1b4636f43e27e5a99f7b58bc58494bf97a'),
        ('d00d1cf6fc532cd8', '9344533c4118c35c73e68a704ed70271514f9211'),
        ('f6f39272fe6447ee', '2c8c0c76f27b62f1dbb24cb436ae7a2d42c026db'),
        ('fb918ff938758326', 'a3e238ceb8c700ef33b1f0452b098d04a5fe0579')
      ) AS e(key_id, source_hash) ON e.key_id = k.key_id
     WHERE k.namespace = 'client' AND k.retired_at IS NULL
       AND k.source_hash = e.source_hash
       AND k.max_px IS NULL AND k.context IS NULL;
    IF v_ok <> v_expected THEN
        RAISE EXCEPTION 'post-check FAILED: % of % expected sept4b client keys are live with the expected source_hash', v_ok, v_expected;
    END IF;
    RAISE NOTICE 'post-check OK: % sept4b client keys live', v_ok;
END $$;

COMMIT;
