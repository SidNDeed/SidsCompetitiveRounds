-- 223_seed_vocab_and_new_shop_strings.sql
--
-- Machine-translated proposal seeds (es/ru/uk/sv) for the 19 client keys
-- added 2026-08-15:
--   - 14 server-enum vocab words (shop_items.rarity + kind display words) —
--     these rendered raw English in every locale because Tr(variable) never
--     harvests (#295a) and the values were never keys (Kyltist, Aug 15).
--     Now harvested via NativeUI's TrRarity/TrKindWord literal switches.
--   - 5 shop-catalog strings from the tools/shop_strings.json refresh
--     (2v2/FFA Podium titles + descriptions, pcolor_poison description).
--
-- Same contract as 184/189/213: PENDING proposals only, sentinel proposer
-- 'claude-mt', license_assent TRUE at the machine-translation terms rev.
-- The same 76 translations also ship BUNDLED in I18nCatalogues.cs, so the
-- client renders them without any approval; these proposals exist so human
-- translators can see/refine them through the portal (an approval then
-- overrides the bundled value via the pack overlay).
--
-- ORDERING: seeds only keys already present in i18n_keys, which
-- tools/i18n_sync_keys.py populates. Run order: deploy API -> run
-- i18n_sync_keys.py -> apply this file. On an unsynced database the
-- assertion below RAISEs and the transaction rolls back; re-run after the
-- sync. Explicit BEGIN/COMMIT because the deploy wrapper's psql -f does
-- not wrap the file in a transaction (#340), and the wrapper's `||`
-- fallback re-runs the whole file (#243) — every statement is idempotent.
BEGIN;

CREATE TEMP TABLE _seed223 (
  key_id      VARCHAR(16) NOT NULL,
  lang        VARCHAR(8)  NOT NULL,
  source_hash VARCHAR(40) NOT NULL,
  target      TEXT        NOT NULL
) ON COMMIT DROP;

INSERT INTO _seed223 (key_id, lang, source_hash, target) VALUES
  ('c9f4654b7eb77513', 'es', '74bf5bd38e9052a870e6f6b0ae66bf64b39b86b7', 'Podio 2v2')
  , ('c9f4654b7eb77513', 'ru', '74bf5bd38e9052a870e6f6b0ae66bf64b39b86b7', 'Пьедестал 2v2')
  , ('c9f4654b7eb77513', 'uk', '74bf5bd38e9052a870e6f6b0ae66bf64b39b86b7', 'П''єдестал 2v2')
  , ('c9f4654b7eb77513', 'sv', '74bf5bd38e9052a870e6f6b0ae66bf64b39b86b7', '2v2-pallen')
  , ('73b4e1fa08ae8958', 'es', 'a75329613f268c94057ba2625c7b2e2c8af204ea', 'Podio FFA')
  , ('73b4e1fa08ae8958', 'ru', 'a75329613f268c94057ba2625c7b2e2c8af204ea', 'Пьедестал FFA')
  , ('73b4e1fa08ae8958', 'uk', 'a75329613f268c94057ba2625c7b2e2c8af204ea', 'П''єдестал FFA')
  , ('73b4e1fa08ae8958', 'sv', 'a75329613f268c94057ba2625c7b2e2c8af204ea', 'FFA-pallen')
  , ('9f6f3ff506740ea8', 'es', 'd8c7c8cf4f9fea827b5d13a5e50e94756615d394', 'Reservado al top 3 de la clasificación 2v2')
  , ('9f6f3ff506740ea8', 'ru', 'd8c7c8cf4f9fea827b5d13a5e50e94756615d394', 'Носят только игроки из топ-3 рейтинга 2v2')
  , ('9f6f3ff506740ea8', 'uk', 'd8c7c8cf4f9fea827b5d13a5e50e94756615d394', 'Носять лише троє найкращих у рейтингу 2v2')
  , ('9f6f3ff506740ea8', 'sv', 'd8c7c8cf4f9fea827b5d13a5e50e94756615d394', 'Bärs av topp 3 på 2v2-topplistan')
  , ('2e97ebb1aa9833a1', 'es', 'd1a8bbfa7d6b67955b884b1abf9db358b26123f2', 'Reservado al top 3 de la clasificación FFA')
  , ('2e97ebb1aa9833a1', 'ru', 'd1a8bbfa7d6b67955b884b1abf9db358b26123f2', 'Носят только игроки из топ-3 рейтинга FFA')
  , ('2e97ebb1aa9833a1', 'uk', 'd1a8bbfa7d6b67955b884b1abf9db358b26123f2', 'Носять лише троє найкращих у рейтингу FFA')
  , ('2e97ebb1aa9833a1', 'sv', 'd1a8bbfa7d6b67955b884b1abf9db358b26123f2', 'Bärs av topp 3 på FFA-topplistan')
  , ('d9ba1c95478f3c23', 'es', 'e6299bcf304aaf6ab99368c3b9166ad2b1ec5549', 'El verde exacto con el que un tic de veneno hace parpadear a su víctima.')
  , ('d9ba1c95478f3c23', 'ru', 'e6299bcf304aaf6ab99368c3b9166ad2b1ec5549', 'Тот самый зелёный, которым вспыхивает жертва от тика яда.')
  , ('d9ba1c95478f3c23', 'uk', 'e6299bcf304aaf6ab99368c3b9166ad2b1ec5549', 'Той самий зелений, яким спалахує жертва від тіку отрути.')
  , ('d9ba1c95478f3c23', 'sv', 'e6299bcf304aaf6ab99368c3b9166ad2b1ec5549', 'Exakt den gröna nyans som ett gifttick blinkar på sitt offer.')
  , ('1f906dd204f11211', 'es', '6dd0fe8001145bec4a12d0e22da711c4970d000b', 'color')
  , ('1f906dd204f11211', 'ru', '6dd0fe8001145bec4a12d0e22da711c4970d000b', 'цвет')
  , ('1f906dd204f11211', 'uk', '6dd0fe8001145bec4a12d0e22da711c4970d000b', 'колір')
  , ('1f906dd204f11211', 'sv', '6dd0fe8001145bec4a12d0e22da711c4970d000b', 'färg')
  , ('e1057c640d9c18b6', 'es', '94c8c21d08740f5da9eaa38d1f175c592692f0d1', 'rareza: común')
  , ('e1057c640d9c18b6', 'ru', '94c8c21d08740f5da9eaa38d1f175c592692f0d1', 'редкость: обычная')
  , ('e1057c640d9c18b6', 'uk', '94c8c21d08740f5da9eaa38d1f175c592692f0d1', 'рідкість: звичайна')
  , ('e1057c640d9c18b6', 'sv', '94c8c21d08740f5da9eaa38d1f175c592692f0d1', 'sällsynthet: vanlig')
  , ('b21c41222533d93c', 'es', '31ca1a3367bac9b6b3ab51e57ae6a31edca9ad7c', 'color del cursor')
  , ('b21c41222533d93c', 'ru', '31ca1a3367bac9b6b3ab51e57ae6a31edca9ad7c', 'цвет курсора')
  , ('b21c41222533d93c', 'uk', '31ca1a3367bac9b6b3ab51e57ae6a31edca9ad7c', 'колір курсора')
  , ('b21c41222533d93c', 'sv', '31ca1a3367bac9b6b3ab51e57ae6a31edca9ad7c', 'markörfärg')
  , ('73384d8d31140e09', 'es', '31fe23de06e7a9e05684f021f52cfc0e2832c19d', 'rareza: épica')
  , ('73384d8d31140e09', 'ru', '31fe23de06e7a9e05684f021f52cfc0e2832c19d', 'редкость: эпическая')
  , ('73384d8d31140e09', 'uk', '31fe23de06e7a9e05684f021f52cfc0e2832c19d', 'рідкість: епічна')
  , ('73384d8d31140e09', 'sv', '31fe23de06e7a9e05684f021f52cfc0e2832c19d', 'sällsynthet: episk')
  , ('65b696f2c39bd5da', 'es', '49dc1cb094dffe3a42dd5f448ac612b0786a67e4', 'cara')
  , ('65b696f2c39bd5da', 'ru', '49dc1cb094dffe3a42dd5f448ac612b0786a67e4', 'лицо')
  , ('65b696f2c39bd5da', 'uk', '49dc1cb094dffe3a42dd5f448ac612b0786a67e4', 'обличчя')
  , ('65b696f2c39bd5da', 'sv', '49dc1cb094dffe3a42dd5f448ac612b0786a67e4', 'ansikte')
  , ('a1a070bd7dc66637', 'es', '4c87891558ebeb3be19116efc8e9037e43f0ad1e', 'rareza: legendaria')
  , ('a1a070bd7dc66637', 'ru', '4c87891558ebeb3be19116efc8e9037e43f0ad1e', 'редкость: легендарная')
  , ('a1a070bd7dc66637', 'uk', '4c87891558ebeb3be19116efc8e9037e43f0ad1e', 'рідкість: легендарна')
  , ('a1a070bd7dc66637', 'sv', '4c87891558ebeb3be19116efc8e9037e43f0ad1e', 'sällsynthet: legendarisk')
  , ('c92a9fa248bfbe4e', 'es', '4a16571080b2d5ec503066ad09664991bc0338bb', 'etiqueta de nombre')
  , ('c92a9fa248bfbe4e', 'ru', '4a16571080b2d5ec503066ad09664991bc0338bb', 'неймтег')
  , ('c92a9fa248bfbe4e', 'uk', '4a16571080b2d5ec503066ad09664991bc0338bb', 'неймтег')
  , ('c92a9fa248bfbe4e', 'sv', '4a16571080b2d5ec503066ad09664991bc0338bb', 'namnskylt')
  , ('3581c4eb186d0477', 'es', '871899515bc960165cb986ba61c6b0e2fdfc4483', 'color de jugador')
  , ('3581c4eb186d0477', 'ru', '871899515bc960165cb986ba61c6b0e2fdfc4483', 'цвет игрока')
  , ('3581c4eb186d0477', 'uk', '871899515bc960165cb986ba61c6b0e2fdfc4483', 'колір гравця')
  , ('3581c4eb186d0477', 'sv', '871899515bc960165cb986ba61c6b0e2fdfc4483', 'spelarfärg')
  , ('d55388f40533f056', 'es', '2b5305a40a645b84a38ed158244a3dde340433b5', 'efecto de jugador')
  , ('d55388f40533f056', 'ru', '2b5305a40a645b84a38ed158244a3dde340433b5', 'эффект игрока')
  , ('d55388f40533f056', 'uk', '2b5305a40a645b84a38ed158244a3dde340433b5', 'ефект гравця')
  , ('d55388f40533f056', 'sv', '2b5305a40a645b84a38ed158244a3dde340433b5', 'spelareffekt')
  , ('33189667ce7b6ff8', 'es', 'd5e62fc1fc3b3a64ea4fc20d640432c8bd216663', 'rareza: rara')
  , ('33189667ce7b6ff8', 'ru', 'd5e62fc1fc3b3a64ea4fc20d640432c8bd216663', 'редкость: редкая')
  , ('33189667ce7b6ff8', 'uk', 'd5e62fc1fc3b3a64ea4fc20d640432c8bd216663', 'рідкість: рідкісна')
  , ('33189667ce7b6ff8', 'sv', 'd5e62fc1fc3b3a64ea4fc20d640432c8bd216663', 'sällsynthet: sällsynt')
  , ('167c8c2ffec8b6e8', 'es', '3c6de1b7dd91465d437ef415f94f36afc1fbc8a8', 'título')
  , ('167c8c2ffec8b6e8', 'ru', '3c6de1b7dd91465d437ef415f94f36afc1fbc8a8', 'титул')
  , ('167c8c2ffec8b6e8', 'uk', '3c6de1b7dd91465d437ef415f94f36afc1fbc8a8', 'титул')
  , ('167c8c2ffec8b6e8', 'sv', '3c6de1b7dd91465d437ef415f94f36afc1fbc8a8', 'titel')
  , ('a8aa6f63a0e7347f', 'es', '81a85c613b3fd4aa49573b381f6d6fc5c683c9aa', 'estela')
  , ('a8aa6f63a0e7347f', 'ru', '81a85c613b3fd4aa49573b381f6d6fc5c683c9aa', 'шлейф')
  , ('a8aa6f63a0e7347f', 'uk', '81a85c613b3fd4aa49573b381f6d6fc5c683c9aa', 'шлейф')
  , ('a8aa6f63a0e7347f', 'sv', '81a85c613b3fd4aa49573b381f6d6fc5c683c9aa', 'spår')
  , ('fe8425e82c256c70', 'es', '8d13318ea523c584ca30b15fad027045157b076b', 'rareza: poco común')
  , ('fe8425e82c256c70', 'ru', '8d13318ea523c584ca30b15fad027045157b076b', 'редкость: необычная')
  , ('fe8425e82c256c70', 'uk', '8d13318ea523c584ca30b15fad027045157b076b', 'рідкість: незвичайна')
  , ('fe8425e82c256c70', 'sv', '8d13318ea523c584ca30b15fad027045157b076b', 'sällsynthet: ovanlig')
  , ('878c2724efc99f6c', 'es', '8884fd30d64e5cf97054c14e8a217a1fb0cd7e16', 'utilidad')
  , ('878c2724efc99f6c', 'ru', '8884fd30d64e5cf97054c14e8a217a1fb0cd7e16', 'утилита')
  , ('878c2724efc99f6c', 'uk', '8884fd30d64e5cf97054c14e8a217a1fb0cd7e16', 'утиліта')
  , ('878c2724efc99f6c', 'sv', '8884fd30d64e5cf97054c14e8a217a1fb0cd7e16', 'verktyg')
;

INSERT INTO i18n_proposals
  (key_id, language_code, source_hash, proposed_target, proposer_steam_id,
   license_assent, license_terms_rev, assented_at, status, created_at)
SELECT v.key_id, v.lang, v.source_hash, v.target, 'claude-mt',
       TRUE, 'machine-v1', NOW(), 'pending', NOW()
  FROM _seed223 v
  -- Hash-joined (213's rule): a seed row whose expected English no longer
  -- matches the live key's source inserts NOTHING rather than proposing a
  -- translation of text that no longer exists.
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

DO $$
DECLARE uncovered INT; sample TEXT;
BEGIN
  -- COVERAGE = exactly the conditions under which the INSERT above may
  -- skip a row (213 find 12): current-source proposal exists (any status,
  -- any proposer), some pending proposal holds that key+language, or an
  -- approved entry is already live. Anything else = the seed did not land.
  SELECT COUNT(*) INTO uncovered
    FROM _seed223 v
   WHERE NOT EXISTS (
           SELECT 1 FROM i18n_proposals p
            WHERE p.key_id = v.key_id AND p.language_code = v.lang
              AND (p.source_hash = v.source_hash OR p.status = 'pending'))
     AND NOT EXISTS (
           SELECT 1 FROM i18n_entries e
            WHERE e.key_id = v.key_id AND e.language_code = v.lang
              AND e.state = 'approved');
  IF uncovered <> 0 THEN
    SELECT string_agg(x.key_id || '/' || x.lang, ', ')
      INTO sample
      FROM (SELECT v.key_id, v.lang FROM _seed223 v
             WHERE NOT EXISTS (
                     SELECT 1 FROM i18n_proposals p
                      WHERE p.key_id = v.key_id AND p.language_code = v.lang
                        AND (p.source_hash = v.source_hash OR p.status = 'pending'))
               AND NOT EXISTS (
                     SELECT 1 FROM i18n_entries e
                      WHERE e.key_id = v.key_id AND e.language_code = v.lang
                        AND e.state = 'approved')
             LIMIT 5) x;
    RAISE EXCEPTION 'migration 223: % of 76 seed pairs did not land (e.g. %) - the usual cause is that tools/i18n_sync_keys.py has not run against this database yet; nothing was committed', uncovered, sample;
  END IF;

  RAISE NOTICE 'migration 223: all 76 seed pairs covered (19 keys x es/ru/uk/sv)';
END $$;

COMMIT;
