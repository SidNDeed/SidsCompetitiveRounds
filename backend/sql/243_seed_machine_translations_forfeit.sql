-- 243_seed_machine_translations_forfeit.sql
--
-- Machine-translated proposal seeds (es/ru/uk/sv) for the 4 forfeit keys
-- restored by the tournament forfeit rebuild (Aug 22 lifecycle pass). The
-- English sources are the HONEST forms the v1.39.1 round-2 review required
-- (its find 6): the success copy says the forfeit was RECORDED and the
-- match resolves shortly - never a completed surrender or an awarded
-- technical loss - and every translation below carries the same
-- recorded-not-resolved semantics.
--
-- Same contract as 184/189/213/223/239: PENDING proposals only, sentinel
-- proposer 'claude-mt', license_assent TRUE at the machine-translation
-- terms revision. The same 16 translations ship BUNDLED in
-- I18nCatalogues.cs, so the client renders them without any approval;
-- these proposals exist so human translators can see/refine them through
-- the portal (an approval then overrides the bundled value via the pack
-- overlay).
--
-- PREREQUISITE: the integrator must first run tools/i18n_extract.py in
-- write mode so tools/i18n_source.json contains the four ADDED keys.
--
-- ORDERING: seeds only keys already present in i18n_keys, which
-- tools/i18n_sync_keys.py populates. Run order: deploy API -> run
-- tools/i18n_sync_keys.py -> apply this file. On an unsynced database the
-- assertion below RAISEs and the transaction rolls back; re-run after the
-- sync. Explicit BEGIN/COMMIT because the deploy wrapper's psql -f does
-- not wrap the file in a transaction (#340), and the wrapper's || fallback
-- re-runs the whole file (#243) - every statement is idempotent.
BEGIN;

CREATE TEMP TABLE _seed243 (
  key_id      VARCHAR(16) NOT NULL,
  lang        VARCHAR(8)  NOT NULL,
  source_hash VARCHAR(40) NOT NULL,
  target      TEXT        NOT NULL
) ON COMMIT DROP;

INSERT INTO _seed243 (key_id, lang, source_hash, target) VALUES
  -- 'Forfeit'
  ('29dd7d7b1c852928', 'es', '79424e785ea2fcce076a8fbcdba199e4a0edaa1d', 'Rendirse')
  , ('29dd7d7b1c852928', 'ru', '79424e785ea2fcce076a8fbcdba199e4a0edaa1d', 'Сдаться')
  , ('29dd7d7b1c852928', 'uk', '79424e785ea2fcce076a8fbcdba199e4a0edaa1d', 'Здатися')
  , ('29dd7d7b1c852928', 'sv', '79424e785ea2fcce076a8fbcdba199e4a0edaa1d', 'Ge upp')
  -- 'Click again to forfeit'
  , ('203775486c7a82a6', 'es', '6af3fdd7b6c6bd9921d66438a79392f88442f1d3', 'Pulsa otra vez para rendirte')
  , ('203775486c7a82a6', 'ru', '6af3fdd7b6c6bd9921d66438a79392f88442f1d3', 'Нажми ещё раз, чтобы сдаться')
  , ('203775486c7a82a6', 'uk', '6af3fdd7b6c6bd9921d66438a79392f88442f1d3', 'Натисніть ще раз, щоб здатися')
  , ('203775486c7a82a6', 'sv', '6af3fdd7b6c6bd9921d66438a79392f88442f1d3', 'Klicka igen för att ge upp')
  -- 'Forfeit recorded - the match will be resolved shortly.'
  , ('df07898130ca13ef', 'es', '012cc72f181623655f86f1ab4b06654ca4412740', 'Rendición registrada - la partida se resolverá en breve.')
  , ('df07898130ca13ef', 'ru', '012cc72f181623655f86f1ab4b06654ca4412740', 'Сдача записана - матч скоро будет завершён.')
  , ('df07898130ca13ef', 'uk', '012cc72f181623655f86f1ab4b06654ca4412740', 'Здачу записано - матч невдовзі буде завершено.')
  , ('df07898130ca13ef', 'sv', '012cc72f181623655f86f1ab4b06654ca4412740', 'Uppgivning registrerad - matchen avgörs inom kort.')
  -- 'Forfeit failed'
  , ('d1136733b5c62c42', 'es', '22333d4dfcca347a29c73248ab2e93e9930e41be', 'No se pudo registrar la rendición')
  , ('d1136733b5c62c42', 'ru', '22333d4dfcca347a29c73248ab2e93e9930e41be', 'Не удалось записать сдачу')
  , ('d1136733b5c62c42', 'uk', '22333d4dfcca347a29c73248ab2e93e9930e41be', 'Не вдалося записати здачу')
  , ('d1136733b5c62c42', 'sv', '22333d4dfcca347a29c73248ab2e93e9930e41be', 'Kunde inte registrera uppgivningen');

INSERT INTO i18n_proposals
  (key_id, language_code, source_hash, proposed_target, proposer_steam_id,
   license_assent, license_terms_rev, assented_at, status, created_at)
SELECT v.key_id, v.lang, v.source_hash, v.target, 'claude-mt',
       TRUE, 'machine-v1', NOW(), 'pending', NOW()
  FROM _seed243 v
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
    FROM _seed243 v
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
      FROM (SELECT v.key_id, v.lang FROM _seed243 v
             WHERE NOT EXISTS (
                     SELECT 1 FROM i18n_proposals p
                      WHERE p.key_id = v.key_id AND p.language_code = v.lang
                        AND (p.source_hash = v.source_hash OR p.status = 'pending'))
               AND NOT EXISTS (
                     SELECT 1 FROM i18n_entries e
                      WHERE e.key_id = v.key_id AND e.language_code = v.lang
                        AND e.state = 'approved')
             LIMIT 5) x;
    RAISE EXCEPTION 'migration 243: % of 16 seed pairs did not land (e.g. %) - the usual cause is that tools/i18n_sync_keys.py has not run against this database yet; nothing was committed', uncovered, sample;
  END IF;

  RAISE NOTICE 'migration 243: all 16 seed pairs covered (4 keys x es/ru/uk/sv)';
END $$;

COMMIT;
