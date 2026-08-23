-- 248: i18n client keys for v1.39.2 (53 NEW keys: the night-pack map
-- skins + gradient name styles (migration 246) and the v1.39.2 community
-- cosmetics + the v1.39.1 cosmetics' shop strings that had never been synced).
-- This is the additive half of what POST /admin/i18n/sync-keys does, written
-- through the migration channel because this seat's AdminSecret does not
-- verify against the server (403 Bad admin signature, learning #406 still
-- stands). Verified against the live table before writing: the extractor
-- manifest (1890 client keys) retires NOTHING (every live key is still
-- in the manifest) and changes no English (no source_hash moves), so no
-- retirement sweep and no proposal supersede is owed - a plain insert IS the
-- endpoint's effect for this release. key_id = sha1("client\0" + English)[:16],
-- source_hash = sha1(English), sensitive per tools/i18n_sync_keys.py's
-- SENSITIVE_MARKERS (imported, not copied). Idempotent; explicit transaction (#340).
-- The game namespace (242 keys) is unchanged this release.

BEGIN;

INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, max_px, context, updated_at)
SELECT v.key_id, v.namespace, v.msgctxt, v.source_hash, v.sensitive, NULL, NULL, NOW()
  FROM (VALUES
('5c299cdd5181a941', 'client', $k248$A silly little mouth for feline ethusiasts$k248$, 'fbc862283106c3ad11970e3d7528cb421283e2e5', FALSE),
('1b3f3ff1f8bc538e', 'client', $k248$Ash Gradient$k248$, 'ac1861b407332050c7ad8ece653fde7c0a2885e5', FALSE),
('511b49694beadfab', 'client', $k248$Ash walls with a dark crimson accent over a deep blood-red dark, red embers rising.$k248$, '6f2d396e557b5f76d31e56571112c890b8ee7430', FALSE),
('84e17af7112e2c2c', 'client', $k248$Blood Gradient$k248$, '03cb2764ec60add600368e21f4fdda7ea811af9f', FALSE),
('e0c347af1c2e8c45', 'client', $k248$Blood Moon$k248$, 'a5c48a631fa6ac8b9e71d1b9a78e93f88f013c43', FALSE),
('38ae3616902f9e47', 'client', $k248$Cat Eyes$k248$, '527774087ad99d4cbf98e04c8c027506f3dfaa89', FALSE),
('bb044ac5a0ad150f', 'client', $k248$Cat Mouth$k248$, '8ca39fdb3e24dc0164815c29c778320c3477b994', FALSE),
('e8d68fce3701fe2e', 'client', $k248$Charcoal walls rimmed with corona amber on a true black sky.$k248$, '0da332b305a132002eabd6a4d3b1dade76c79582', FALSE),
('d4ffe97d52355fb3', 'client', $k248$Dark ash walls with a pale rose-silver accent over a deep red night, with a faint red glint.$k248$, 'b4816f88de2979e10fa5707a46a4176b09682f23', FALSE),
('a9aa7dd7e345eacb', 'client', $k248$Dark indigo walls on the purest black background in the catalogue.$k248$, 'eef8bc1daff28c5ee9b334003283b6ce9b14141b', FALSE),
('0b90ace75370115b', 'client', $k248$Dark steel walls with amber window glow against a black-navy sky, city lights twinkling behind.$k248$, 'cc83269496c01ca47b98e106203958dcc350fa97', FALSE),
('730802fcc588b2ac', 'client', $k248$Deep green hedges and bark-brown walls on a dark brown night.$k248$, 'e2cf54d378b402a3681ccc88f012f93dd28b5de5', FALSE),
('75eccff6b3ce7be0', 'client', $k248$Earth Gradient$k248$, '8f963207651b6b17c88011cc9a1cf5016ff08143', FALSE),
('52eb10fe5a54bd85', 'client', $k248$Eclipse$k248$, '45fc6c80b5f40c599a9996e4565f6c3c0441f578', FALSE),
('9922fbe350152757', 'client', $k248$Emerald Gradient$k248$, 'a58ad4865dc2d5fdf3c26319e1ec8c4619cf3819', FALSE),
('cdac92171e43b9bf', 'client', $k248$Fade Gradient$k248$, 'c547d9751e2e1075a2d5db9846f7bd630adf98ce', FALSE),
('7c8d1536eb0fd36a', 'client', $k248$For the silly ones. Takes up the mouth slot$k248$, '95f3d46ddbd9f0400b8e07572a25f0f6dc0d6fc9', FALSE),
('8586bec2443a2aa0', 'client', $k248$Forest Fire$k248$, 'b22b408fe071ebbc3d1087b8f7009a9a237ebcf6', FALSE),
('17c00df433739b35', 'client', $k248$Goober$k248$, '5ab5f51856f65ede67445fa3f1e37faeff8c86d8', FALSE),
('d453de367dadaf91', 'client', $k248$Midnight$k248$, '558287ddcc3557b09ec00ca17b3e4be7e6645858', FALSE),
('5d29024a4d44289a', 'client', $k248$Moonlit$k248$, '3568c7491babebb953c769947cc8f490da802f47', FALSE),
('41f8d6df2156cb5a', 'client', $k248$Night City$k248$, '101288b594e03b935789b8a597f09d42680fa7d0', FALSE),
('f8387a7add74f327', 'client', $k248$Night Park$k248$, 'd6c0ceed4033b33fc562d60d9b914946e813d9b7', FALSE),
('8dc459eeaa15acb6', 'client', $k248$Night-forest green and bark walls under a dark smoky sky, with embers drifting up through the backdrop.$k248$, '22584937a4a8382e23a56fbd261ae0dbda2c028a', FALSE),
('900bfdd2c5aaf566', 'client', $k248$Nuclear glasses$k248$, '8114ab3a57601ffcee1b9eaafffb4c8561adea9b', FALSE),
('f4db3fff7c36a085', 'client', $k248$Orchid Gradient$k248$, '95e92e3918fc6682050e39c82964ff3edb266fff', FALSE),
('7122e0c69ba45d2d', 'client', $k248$Pale silver-blue walls over a pitch-black night, with a faint star glint.$k248$, 'f2817a9b2c0417af68309b2a6e5dbab82f161295', FALSE),
('81c7b7cb050ea26d', 'client', $k248$Per-letter bright red → dark wine gradient.$k248$, '7fd885137d973cf162fe2417eadbd70ecd9734ae', FALSE),
('9a7fe17e2d48c091', 'client', $k248$Per-letter leaf green → bark brown gradient. Canopy to roots.$k248$, 'e6cc9035282ccdebffc0f56f58f1b8d6c8a79311', FALSE),
('65c931b05122cf6c', 'client', $k248$Per-letter mint → deep forest green gradient.$k248$, '908554507507c82ec5bd2d28fe10e6b51fd4fe5a', FALSE),
('0429c34a08c40ee2', 'client', $k248$Per-letter rich gold → ivory white gradient.$k248$, 'a15667a26f8fbd09ac67a9c4155551d0eff857fd', TRUE),
('10fc19103bfc00a4', 'client', $k248$Per-letter silver → gunmetal blue gradient. Cold and clean.$k248$, 'b62204bc74efd9da27cf3ebbc7002c6e71a1a5ad', FALSE),
('e8318953ee3473cc', 'client', $k248$Per-letter sky blue → deep royal blue gradient.$k248$, 'ffe6b732761562041ff44d44571715b12b5027da', FALSE),
('17fee1da703692c3', 'client', $k248$Per-letter sunset orange → dusk purple gradient.$k248$, 'a6ed417fdbecf9d7cea95373bb7f74ab8b4f42d6', FALSE),
('9447c4a194d0bbf6', 'client', $k248$Per-letter violet → hot pink gradient.$k248$, 'cbdb204cfdf3376735d0ed1cea0b9985b3bfe912', FALSE),
('d93ccfb1df90a055', 'client', $k248$Per-letter warm grey → ember red gradient. Cooling coals.$k248$, '7e378d24d3eb1dd3ad959fd0244ac122c1944bca', FALSE),
('2114443a269971a4', 'client', $k248$Per-letter white → dark charcoal gradient. Fades out as it goes.$k248$, '8566174efb4eb4edb2ed35464668e45a1334b95c', FALSE),
('47d9b036144dbc30', 'client', $k248$Poison's eyes$k248$, 'f6b5a94241188908466dd4e8866efdd71a095f00', FALSE),
('3c0f844e8017bc56', 'client', $k248$Poison's mouth$k248$, '670012d71850926c55cf6e4df5b125e67d1e988e', FALSE),
('df98d4645ac79249', 'client', $k248$Poison's weeping$k248$, '26c1d2970bb104ebf25377d761feeed044bbf63b', FALSE),
('aa1cc75adcac35af', 'client', $k248$Rainy Day$k248$, 'a8dbee7af410ed602b17d9c2e9c7516d63d649b1', FALSE),
('a5239cbe85ee4b07', 'client', $k248$Royal Gradient$k248$, '3c6ddde8fbcc54626a1b093d38b2e1f79ccb5b71', FALSE),
('24217068bcc775e9', 'client', $k248$Sapphire Gradient$k248$, '1c933f68509c9bed6e49ae0ae73a5485f1006267', FALSE),
('35bd46d542291519', 'client', $k248$Seasonal Spring$k248$, 'fbdf3954fe302a9669bb5146924faa655c14bd1e', FALSE),
('193478fa57528850', 'client', $k248$Shock Shades$k248$, 'c49dfd91243662405690056d72d5545ffed41a88', FALSE),
('1ab9372118365ce8', 'client', $k248$Speacial eyes for the feline enthused$k248$, '61ad233cad804ff442749806e155e661d6cb1fe8', FALSE),
('ac0a136fc03bd3ed', 'client', $k248$Steel Gradient$k248$, '5052759c37603ebc59fa10a45f0d8819b759e480', FALSE),
('a2747db45e42ad62', 'client', $k248$The Challenger$k248$, '26d43bc6493e51b1047f9b89c7a4247b7c236a04', FALSE),
('3cf0b30ec7dd441c', 'client', $k248$The expression of a true warrior going into battle. Takes up the mouth slot$k248$, 'f665c772bf8a49dd52bfeb8ad1a6ac44b38cabc8', FALSE),
('8dce4de87ebefc5b', 'client', $k248$Time to show them who is the coolest dude around! A pair of glasses that takes up the eye slot$k248$, 'f54d4c1fe052a1040ab35be570d899d745e18151', FALSE),
('2d379480e63e50b0', 'client', $k248$Twilight Gradient$k248$, '79e69b6303e570c6ed379ee5c5ee18bfd257b9db', FALSE),
('b61b00ae9924cd72', 'client', $k248$Underworld$k248$, '68c5aaeaec955f166f73912d182f66e281c95d95', FALSE),
('34b4e4fcb0da7041', 'client', $k248$Wet teal-grey stone walls under an overcast slate sky, rain streaking down the backdrop.$k248$, 'dbfa8132673eda37733efbad711f380ae714de0a', FALSE)
  ) AS v(key_id, namespace, msgctxt, source_hash, sensitive)
ON CONFLICT (key_id) DO UPDATE SET retired_at = NULL, updated_at = NOW()
  WHERE i18n_keys.source_hash = EXCLUDED.source_hash;

DO $$
DECLARE v_live INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_live FROM i18n_keys WHERE namespace = 'client' AND retired_at IS NULL;
    IF v_live <> 1890 THEN
        RAISE EXCEPTION 'post-check FAILED: % live client keys, expected 1890', v_live;
    END IF;
    RAISE NOTICE 'post-check OK: % live client keys', v_live;
END $$;

COMMIT;
