-- 214: translator titles — Rosetta / Dragoman / Babel (Sid, Aug 11).
--
-- Three grant-only titles rewarding community translation work, on the same
-- achievement->title rail as Sid Slayer (rotation_pool='achievement' hides
-- them from the shop list, the purchase endpoint rejects them, and
-- _grant_achievement_inline grants the PlayerItem so every grant path
-- unlocks the title — learning #111/#151).
--
-- CREDIT RULE (mirrors _translator_credit in main.py exactly; if you change
-- one, change both): DISTINCT (key_id, language_code) over APPROVED
-- proposals where the person was EITHER the proposer OR the reviewer.
--   * approved only, so junk proposals cannot farm a title;
--   * both roles earn, because reviewing is the scarce work;
--   * DISTINCT collapses a self-approved string (admins may self-approve) to
--     ONE point rather than two, and collapses a re-translated string too.
-- The 'claude-mt' machine-draft sentinel is excluded — it is not a player,
-- and the human who APPROVES one of its drafts is the one credited.
--
-- Idempotent: the shop rows are ON CONFLICT DO NOTHING, and every back-grant
-- statement is guarded so a rerun grants nothing twice. Wrapped in an
-- explicit transaction because the deploy wrapper runs `psql -f` WITHOUT
-- --single-transaction (learning #340) — the titles, the achievements, the
-- gold and the ledger must land together or not at all.
BEGIN;

-- ── 1. The titles ─────────────────────────────────────────────────────────
INSERT INTO shop_items (sku, kind, name, description, price, rarity, rotation_pool, preview_color)
VALUES
  ('title_rosetta',  'title', 'Rosetta',  'Got 10 translations approved',   0, 'rare',      'achievement', '#8FD4C1'),
  ('title_dragoman', 'title', 'Dragoman', 'Got 100 translations approved',  0, 'epic',      'achievement', '#C9A227'),
  ('title_babel',    'title', 'Babel',    'Got 1000 translations approved', 0, 'legendary', 'achievement', '#B57BFF')
ON CONFLICT (sku) DO NOTHING;

-- ── 2. Who has earned what ────────────────────────────────────────────────
-- One row per (player, achievement_key) that this player now qualifies for.
CREATE TEMP TABLE _tt_earned ON COMMIT DROP AS
WITH credit AS (
    SELECT person, COUNT(*) AS n
      FROM (SELECT DISTINCT key_id, language_code,
                   unnest(ARRAY[proposer_steam_id, reviewed_by_steam_id]) AS person
              FROM i18n_proposals
             WHERE status = 'approved'
               -- Shipped languages only, mirroring _translator_credit
               -- (find 7): work under a code the pack cannot serve is not
               -- translation anyone will ever read.
               AND language_code IN ('es', 'ru', 'uk', 'sv')) d
     WHERE person IS NOT NULL AND person <> 'claude-mt'
     GROUP BY person
)
SELECT pl.id AS player_id, t.key AS achievement_key, t.sku
  FROM credit c
  JOIN players pl ON pl.steam_id = c.person AND pl.deleted_at IS NULL
  JOIN (VALUES (10, 'rosetta', 'title_rosetta'),
               (100, 'dragoman', 'title_dragoman'),
               (1000, 'babel', 'title_babel')) AS t(need, key, sku)
    ON c.n >= t.need;

-- ── 3. Achievement rows ───────────────────────────────────────────────────
INSERT INTO player_achievements (player_id, achievement_key)
SELECT DISTINCT player_id, achievement_key FROM _tt_earned
ON CONFLICT DO NOTHING;

-- ── 4. Gold, for the rows this migration actually granted ─────────────────
-- Reads the LIVE payout tiers (#229: never copy an older migration's rate) —
-- these mirror ACHIEVEMENT_GOLD_OVERRIDES: rosetta 100 / dragoman 300 /
-- babel 1000. Only pays a (player, key) that has NO prior achievement ledger
-- row for that key, so a rerun — or a player who somehow already had the
-- achievement — is never paid twice.
WITH owed AS (
    SELECT e.player_id, e.achievement_key, g.gold
      FROM (SELECT DISTINCT player_id, achievement_key FROM _tt_earned) e
      JOIN (VALUES ('rosetta', 100), ('dragoman', 300), ('babel', 1000))
             AS g(key, gold) ON g.key = e.achievement_key
     WHERE NOT EXISTS (
             SELECT 1 FROM gold_transactions gt
              WHERE gt.player_id = e.player_id
                AND gt.reason = 'achievement'
                AND gt.reference_id = e.achievement_key)
),
ledger AS (
    INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
    SELECT player_id, gold, 'achievement', achievement_key FROM owed
    RETURNING player_id, amount
),
per_player AS (
    -- #240: collapse to ONE row per player before touching `players`, or an
    -- UPDATE ... FROM with two matching source rows applies only one of them.
    SELECT player_id, SUM(amount)::int AS total FROM ledger GROUP BY player_id
)
UPDATE players p
   SET gold_earned = COALESCE(p.gold_earned, 0) + pp.total
  FROM per_player pp
 WHERE p.id = pp.player_id;

-- ── 5. The equippable title items ─────────────────────────────────────────
INSERT INTO player_items (player_id, item_id, purchase_price)
SELECT DISTINCT e.player_id, si.id, 0
  FROM _tt_earned e
  JOIN shop_items si ON si.sku = e.sku
 WHERE NOT EXISTS (
         SELECT 1 FROM player_items pi
          WHERE pi.player_id = e.player_id AND pi.item_id = si.id);


-- ── 6. Portal seeds for this feature's own display strings ────────────────
-- The three achievement names, their descriptions and the three shop
-- descriptions are new TRANSLATABLE keys. Migration 213's wave is already
-- applied, so they need their own seed or the portal would show them as
-- untranslated forever while the bundled catalogue already has them.
-- Same claude-mt contract and the same two rerun guards as 213; hash-joined
-- so a row whose English no longer matches inserts nothing. Runs AFTER
-- tools/i18n_sync_keys.py has registered the new keys (the assertion below
-- says so out loud if it has not).
INSERT INTO i18n_proposals
  (key_id, language_code, source_hash, proposed_target, proposer_steam_id,
   license_assent, license_terms_rev, assented_at, status, created_at)
SELECT v.key_id, v.lang, v.source_hash, v.target, 'claude-mt',
       TRUE, 'machine-v1', NOW(), 'pending', NOW()
  FROM (VALUES
  ('716553e5d4ffcdf8', 'es', 'db73904ee194bd4fd1333249d0a3c3d19476c274', 'Rosetta'),
  ('09223fd5f61ba258', 'es', '689010aa4282379f0479c0e024108c2a963ef5f7', 'Dragomán'),
  ('d704b66a9fc187c3', 'es', 'f3bf8dee016caf43ae3970fbea5f976d54898ed9', 'Babel'),
  ('39617d899fccdbad', 'es', '9db8b316fbbff3ed5262eb85f448b40ee0ec13ff', 'Consigue 10 traducciones aprobadas (tuyas o revisadas por ti)'),
  ('dcc82a2b178d2cf1', 'es', 'a4d4f3f811aa4c65da7efed58dbc34c2a927a36e', 'Consigue 100 traducciones aprobadas (tuyas o revisadas por ti)'),
  ('15d202c6a4014604', 'es', '3da5563a1b208c34fb55b011341811074297bc21', 'Consigue 1000 traducciones aprobadas (tuyas o revisadas por ti)'),
  ('61e297eba181127f', 'es', '7903e247cb949cf5d7b432707df4d104ed3c81aa', 'Consiguió 10 traducciones aprobadas'),
  ('e7f9f0fb5a2c0786', 'es', 'f6fe7b03c53f86154d56f1afe95a158361e7c559', 'Consiguió 100 traducciones aprobadas'),
  ('ce25ae7de19d2198', 'es', 'a66a92451d0146f81caa567f1627e7e235745728', 'Consiguió 1000 traducciones aprobadas'),
  ('716553e5d4ffcdf8', 'ru', 'db73904ee194bd4fd1333249d0a3c3d19476c274', 'Розетта'),
  ('09223fd5f61ba258', 'ru', '689010aa4282379f0479c0e024108c2a963ef5f7', 'Драгоман'),
  ('d704b66a9fc187c3', 'ru', 'f3bf8dee016caf43ae3970fbea5f976d54898ed9', 'Вавилон'),
  ('39617d899fccdbad', 'ru', '9db8b316fbbff3ed5262eb85f448b40ee0ec13ff', 'Получите 10 одобренных переводов (ваших или проверенных вами)'),
  ('dcc82a2b178d2cf1', 'ru', 'a4d4f3f811aa4c65da7efed58dbc34c2a927a36e', 'Получите 100 одобренных переводов (ваших или проверенных вами)'),
  ('15d202c6a4014604', 'ru', '3da5563a1b208c34fb55b011341811074297bc21', 'Получите 1000 одобренных переводов (ваших или проверенных вами)'),
  ('61e297eba181127f', 'ru', '7903e247cb949cf5d7b432707df4d104ed3c81aa', 'Получено 10 одобренных переводов'),
  ('e7f9f0fb5a2c0786', 'ru', 'f6fe7b03c53f86154d56f1afe95a158361e7c559', 'Получено 100 одобренных переводов'),
  ('ce25ae7de19d2198', 'ru', 'a66a92451d0146f81caa567f1627e7e235745728', 'Получено 1000 одобренных переводов'),
  ('716553e5d4ffcdf8', 'uk', 'db73904ee194bd4fd1333249d0a3c3d19476c274', 'Розетта'),
  ('09223fd5f61ba258', 'uk', '689010aa4282379f0479c0e024108c2a963ef5f7', 'Драгоман'),
  ('d704b66a9fc187c3', 'uk', 'f3bf8dee016caf43ae3970fbea5f976d54898ed9', 'Вавилон'),
  ('39617d899fccdbad', 'uk', '9db8b316fbbff3ed5262eb85f448b40ee0ec13ff', 'Отримайте 10 схвалених перекладів (ваших або перевірених вами)'),
  ('dcc82a2b178d2cf1', 'uk', 'a4d4f3f811aa4c65da7efed58dbc34c2a927a36e', 'Отримайте 100 схвалених перекладів (ваших або перевірених вами)'),
  ('15d202c6a4014604', 'uk', '3da5563a1b208c34fb55b011341811074297bc21', 'Отримайте 1000 схвалених перекладів (ваших або перевірених вами)'),
  ('61e297eba181127f', 'uk', '7903e247cb949cf5d7b432707df4d104ed3c81aa', 'Отримано 10 схвалених перекладів'),
  ('e7f9f0fb5a2c0786', 'uk', 'f6fe7b03c53f86154d56f1afe95a158361e7c559', 'Отримано 100 схвалених перекладів'),
  ('ce25ae7de19d2198', 'uk', 'a66a92451d0146f81caa567f1627e7e235745728', 'Отримано 1000 схвалених перекладів'),
  ('716553e5d4ffcdf8', 'sv', 'db73904ee194bd4fd1333249d0a3c3d19476c274', 'Rosetta'),
  ('09223fd5f61ba258', 'sv', '689010aa4282379f0479c0e024108c2a963ef5f7', 'Dragoman'),
  ('d704b66a9fc187c3', 'sv', 'f3bf8dee016caf43ae3970fbea5f976d54898ed9', 'Babel'),
  ('39617d899fccdbad', 'sv', '9db8b316fbbff3ed5262eb85f448b40ee0ec13ff', 'Få 10 översättningar godkända (dina egna eller sådana du granskat)'),
  ('dcc82a2b178d2cf1', 'sv', 'a4d4f3f811aa4c65da7efed58dbc34c2a927a36e', 'Få 100 översättningar godkända (dina egna eller sådana du granskat)'),
  ('15d202c6a4014604', 'sv', '3da5563a1b208c34fb55b011341811074297bc21', 'Få 1000 översättningar godkända (dina egna eller sådana du granskat)'),
  ('61e297eba181127f', 'sv', '7903e247cb949cf5d7b432707df4d104ed3c81aa', 'Fick 10 översättningar godkända'),
  ('e7f9f0fb5a2c0786', 'sv', 'f6fe7b03c53f86154d56f1afe95a158361e7c559', 'Fick 100 översättningar godkända'),
  ('ce25ae7de19d2198', 'sv', 'a66a92451d0146f81caa567f1627e7e235745728', 'Fick 1000 översättningar godkända')
  ) AS v(key_id, lang, source_hash, target)
  JOIN i18n_keys k ON k.key_id = v.key_id AND k.retired_at IS NULL
                  AND k.source_hash = v.source_hash
 WHERE NOT EXISTS (
   SELECT 1 FROM i18n_proposals p
    WHERE p.key_id = v.key_id AND p.language_code = v.lang
      AND p.status = 'pending')
   AND NOT EXISTS (
   SELECT 1 FROM i18n_proposals p2
    WHERE p2.key_id = v.key_id AND p2.language_code = v.lang
      AND p2.proposer_steam_id = 'claude-mt'
      AND p2.source_hash = v.source_hash);

-- ── 7. Post-check ─────────────────────────────────────────────────────────
DO $$
DECLARE n_titles INT; n_earned INT; n_ach INT; n_items INT; n_seed INT;
BEGIN
  SELECT COUNT(*) INTO n_titles FROM shop_items
   WHERE sku IN ('title_rosetta', 'title_dragoman', 'title_babel');
  IF n_titles <> 3 THEN
    RAISE EXCEPTION 'migration 214: % of 3 translator titles present', n_titles;
  END IF;
  SELECT COUNT(*) INTO n_earned FROM _tt_earned;
  -- Every earned pair must now hold BOTH the achievement and the item;
  -- anything less means a guard above matched when it should not have.
  SELECT COUNT(*) INTO n_ach FROM (SELECT DISTINCT player_id, achievement_key FROM _tt_earned) e
   WHERE EXISTS (SELECT 1 FROM player_achievements pa
                  WHERE pa.player_id = e.player_id
                    AND pa.achievement_key = e.achievement_key);
  SELECT COUNT(*) INTO n_items FROM (SELECT DISTINCT player_id, sku FROM _tt_earned) e
   WHERE EXISTS (SELECT 1 FROM player_items pi JOIN shop_items si ON si.id = pi.item_id
                  WHERE pi.player_id = e.player_id AND si.sku = e.sku);
  IF n_ach <> (SELECT COUNT(*) FROM (SELECT DISTINCT player_id, achievement_key FROM _tt_earned) x)
     OR n_items <> (SELECT COUNT(*) FROM (SELECT DISTINCT player_id, sku FROM _tt_earned) y) THEN
    RAISE EXCEPTION 'migration 214: back-grant incomplete (achievements %, items %)', n_ach, n_items;
  END IF;
  -- Section 6's seed inserts NOTHING when tools/i18n_sync_keys.py has not yet
  -- registered the nine new keys — the exact silent no-op that made migration
  -- 213 carry assertions. 9 strings x 4 languages = 36 covered pairs; anything
  -- less means the sync has not run, so fail loudly and roll the whole file
  -- back rather than half-shipping the feature's own translations.
  SELECT COUNT(*) INTO n_seed FROM (
    SELECT DISTINCT p.key_id, p.language_code
      FROM i18n_proposals p
      JOIN i18n_keys k ON k.key_id = p.key_id AND k.retired_at IS NULL
                      AND k.source_hash = p.source_hash
     WHERE k.msgctxt IN ('Rosetta', 'Dragoman', 'Babel',
                         'Get 10 translations approved (yours, or ones you reviewed)',
                         'Get 100 translations approved (yours, or ones you reviewed)',
                         'Get 1000 translations approved (yours, or ones you reviewed)',
                         'Got 10 translations approved',
                         'Got 100 translations approved',
                         'Got 1000 translations approved')
       AND p.language_code IN ('es', 'ru', 'uk', 'sv')) s;
  IF n_seed <> 36 THEN
    RAISE EXCEPTION 'migration 214: % of 36 translator-string seeds present - run tools/i18n_sync_keys.py (after the API deploy), then re-run this file', n_seed;
  END IF;
  RAISE NOTICE 'migration 214: 3 titles present; % earned (player,tier) rows all granted; 36 display-string seeds present', n_earned;
END $$;

COMMIT;
