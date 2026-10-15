-- 376_i18n_337_demonic_proposals.sql
--
-- Machine-translated proposal seeds (es/ru/uk/sv) for the Demonic body
-- colour swatch's description, the translation work owed since shop item
-- 337 (pcolor_demonic, migration 337) went live on 2026-09-25:
--   key a3ba08a25171bc89 = "The purple the Demonic Pact card is drawn in."
-- The swatch NAME "Demonic" (key 91f20ef1463a3bc2) is harvested as a key
-- in the same pass but is not seeded: like the Poison swatch, the name is
-- the card's own name and stays English in every locale.
--
-- Both keys reach the client through the tools/shop_strings.json refresh
-- -> tools/i18n_extract.py -> plugin/I18nSourceKeys.g.cs route, the same
-- route the Poison swatch's description took. UNLIKE 223, these
-- translations are NOT bundled in I18nCatalogues.cs: the client renders
-- English until a native reviewer approves a proposal in the portal, and
-- the approved text then reaches the client through the pack overlay.
--
-- Same contract as 184/189/213/223: PENDING proposals only, sentinel
-- proposer 'claude-mt', license_assent TRUE at the machine-translation
-- terms rev. Nothing here is approved.
--
-- ORDERING: seeds only keys already present in i18n_keys, which
-- tools/i18n_sync_keys.py populates. Run order: deploy API -> run
-- i18n_sync_keys.py -> apply this file. On an unsynced database the
-- assertion below RAISEs and the transaction rolls back; re-run after the
-- sync. Explicit BEGIN/COMMIT because the deploy wrapper's psql -f does
-- not wrap the file in a transaction (#340), and the wrapper's `||`
-- fallback re-runs the whole file (#243) — every statement is idempotent.
BEGIN;

CREATE TEMP TABLE _seed376 (
  key_id      VARCHAR(16) NOT NULL,
  lang        VARCHAR(8)  NOT NULL,
  source_hash VARCHAR(40) NOT NULL,
  target      TEXT        NOT NULL
) ON COMMIT DROP;

INSERT INTO _seed376 (key_id, lang, source_hash, target) VALUES
  ('a3ba08a25171bc89', 'es', '50a9d67312296bed3f5bcb9316939538b5ab0e4d', 'El morado con el que está dibujada la carta Demonic Pact.')
  , ('a3ba08a25171bc89', 'ru', '50a9d67312296bed3f5bcb9316939538b5ab0e4d', 'Тот самый фиолетовый, которым нарисована карта Demonic Pact.')
  , ('a3ba08a25171bc89', 'uk', '50a9d67312296bed3f5bcb9316939538b5ab0e4d', 'Той самий фіолетовий, яким намальовано карту Demonic Pact.')
  , ('a3ba08a25171bc89', 'sv', '50a9d67312296bed3f5bcb9316939538b5ab0e4d', 'Den lila nyans som kortet Demonic Pact är ritat i.')
;

INSERT INTO i18n_proposals
  (key_id, language_code, source_hash, proposed_target, proposer_steam_id,
   license_assent, license_terms_rev, assented_at, status, created_at)
SELECT v.key_id, v.lang, v.source_hash, v.target, 'claude-mt',
       TRUE, 'machine-v1', NOW(), 'pending', NOW()
  FROM _seed376 v
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
    FROM _seed376 v
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
      FROM (SELECT v.key_id, v.lang FROM _seed376 v
             WHERE NOT EXISTS (
                     SELECT 1 FROM i18n_proposals p
                      WHERE p.key_id = v.key_id AND p.language_code = v.lang
                        AND (p.source_hash = v.source_hash OR p.status = 'pending'))
               AND NOT EXISTS (
                     SELECT 1 FROM i18n_entries e
                      WHERE e.key_id = v.key_id AND e.language_code = v.lang
                        AND e.state = 'approved')
             LIMIT 5) x;
    RAISE EXCEPTION 'migration 376: % of 4 seed pairs did not land (e.g. %) - the usual cause is that tools/i18n_sync_keys.py has not run against this database yet; nothing was committed', uncovered, sample;
  END IF;

  RAISE NOTICE 'migration 376: all 4 seed pairs covered (1 key x es/ru/uk/sv)';
END $$;

COMMIT;
