-- 385_seed_machine_translations_stage2_hold.sql
--
-- Machine-translated proposal seeds (es/ru/uk/sv) for the client strings of 2v2 and 1v2
-- mid-game readmission (Stage 2 design V3; 11 keys, 44 pairs). Same contract as 318:
-- PENDING proposals only, sentinel proposer 'claude-mt', license_assent TRUE at the
-- machine-translation terms revision. These proposals exist so human translators can see
-- and refine them through the portal; native-reader review runs there after the build.
--
-- key_id = sha1("client" || chr(0) || source)[:16] - the NUL-separator form
-- tools/i18n_sync_keys.py uses.
--
-- ORDERING: seeds only keys already present in i18n_keys. Run order:
-- deploy API -> apply 384 (or run tools/i18n_sync_keys.py) -> apply this
-- file. On an unsynced database the assertion below RAISEs and the transaction
-- rolls back; re-run after the keys land. Explicit BEGIN/COMMIT (#340); every
-- statement is idempotent under the wrapper's re-run (#243).
BEGIN;

CREATE TEMP TABLE _seed385 (
  key_id      VARCHAR(16) NOT NULL,
  lang        VARCHAR(8)  NOT NULL,
  source_hash VARCHAR(40) NOT NULL,
  target      TEXT        NOT NULL
) ON COMMIT DROP;

INSERT INTO _seed385 (key_id, lang, source_hash, target) VALUES
  -- "Seat held for {0}: {1}"
     ('98dca83410faa64d', 'es', '90aaed15747edd34574438630be3c33807ba421f', E'Asiento reservado para {0}: {1}')
  ,  ('98dca83410faa64d', 'ru', '90aaed15747edd34574438630be3c33807ba421f', E'Место удерживается для {0}: {1}')
  ,  ('98dca83410faa64d', 'uk', '90aaed15747edd34574438630be3c33807ba421f', E'Місце утримується для {0}: {1}')
  ,  ('98dca83410faa64d', 'sv', '90aaed15747edd34574438630be3c33807ba421f', E'Platsen hålls för {0}: {1}')
  -- "Press Esc to leave. The match then ends as a disconnect."
  ,  ('21a77f99b9e86f48', 'es', '30a77f9e3bf9ae019331df0d619b7df314378a26', E'Pulsa Esc para salir. La partida terminará entonces como una desconexión.')
  ,  ('21a77f99b9e86f48', 'ru', '30a77f9e3bf9ae019331df0d619b7df314378a26', E'Нажмите Esc, чтобы выйти. Тогда матч завершится как отключение.')
  ,  ('21a77f99b9e86f48', 'uk', '30a77f9e3bf9ae019331df0d619b7df314378a26', E'Натисніть Esc, щоб вийти. Тоді матч завершиться як відключення.')
  ,  ('21a77f99b9e86f48', 'sv', '30a77f9e3bf9ae019331df0d619b7df314378a26', E'Tryck på Esc för att lämna. Matchen avslutas då som en frånkoppling.')
  -- "Checking whether {0} can rejoin"
  ,  ('e247d0f66676e2fa', 'es', '6ef502c0684ae18a7d85f5fb02a9a9d27c39c120', E'Comprobando si {0} puede volver a unirse')
  ,  ('e247d0f66676e2fa', 'ru', '6ef502c0684ae18a7d85f5fb02a9a9d27c39c120', E'Проверяем, может ли {0} вернуться')
  ,  ('e247d0f66676e2fa', 'uk', '6ef502c0684ae18a7d85f5fb02a9a9d27c39c120', E'Перевіряємо, чи може {0} повернутися')
  ,  ('e247d0f66676e2fa', 'sv', '6ef502c0684ae18a7d85f5fb02a9a9d27c39c120', E'Kontrollerar om {0} kan återansluta')
  -- "{0} is rejoining"
  ,  ('690eba24c1191a59', 'es', '37a2e787a323c769817b4d2446d54a8b45a264f3', E'{0} está volviendo a unirse')
  ,  ('690eba24c1191a59', 'ru', '37a2e787a323c769817b4d2446d54a8b45a264f3', E'{0} возвращается в матч')
  ,  ('690eba24c1191a59', 'uk', '37a2e787a323c769817b4d2446d54a8b45a264f3', E'{0} повертається до матчу')
  ,  ('690eba24c1191a59', 'sv', '37a2e787a323c769817b4d2446d54a8b45a264f3', E'{0} återansluter')
  -- "{0} is back"
  ,  ('b933f3c706c40e83', 'es', 'cc3dd7d00b80a320c4d93ae1705baf8de7816bdb', E'{0} ha vuelto')
  ,  ('b933f3c706c40e83', 'ru', 'cc3dd7d00b80a320c4d93ae1705baf8de7816bdb', E'{0} снова в игре')
  ,  ('b933f3c706c40e83', 'uk', 'cc3dd7d00b80a320c4d93ae1705baf8de7816bdb', E'{0} знову в грі')
  ,  ('b933f3c706c40e83', 'sv', 'cc3dd7d00b80a320c4d93ae1705baf8de7816bdb', E'{0} är tillbaka')
  -- "{0} did not return. The match ends as a disconnect."
  ,  ('dff040f0708dc38d', 'es', '7648b75aafbc51b1bbd6a7cf069caa774fac6b5e', E'{0} no volvió. La partida termina como una desconexión.')
  ,  ('dff040f0708dc38d', 'ru', '7648b75aafbc51b1bbd6a7cf069caa774fac6b5e', E'{0} не вернулся. Матч завершается как отключение.')
  ,  ('dff040f0708dc38d', 'uk', '7648b75aafbc51b1bbd6a7cf069caa774fac6b5e', E'{0} не повернувся. Матч завершується як відключення.')
  ,  ('dff040f0708dc38d', 'sv', '7648b75aafbc51b1bbd6a7cf069caa774fac6b5e', E'{0} kom inte tillbaka. Matchen avslutas som en frånkoppling.')
  -- "Another player left. The match ends as a disconnect."
  ,  ('fe3e2890029979eb', 'es', '07b5dcb71a45699b4b3a8cf0402f48cfe3485d91', E'Otro jugador se fue. La partida termina como una desconexión.')
  ,  ('fe3e2890029979eb', 'ru', '07b5dcb71a45699b4b3a8cf0402f48cfe3485d91', E'Ещё один игрок вышел. Матч завершается как отключение.')
  ,  ('fe3e2890029979eb', 'uk', '07b5dcb71a45699b4b3a8cf0402f48cfe3485d91', E'Ще один гравець вийшов. Матч завершується як відключення.')
  ,  ('fe3e2890029979eb', 'sv', '07b5dcb71a45699b4b3a8cf0402f48cfe3485d91', E'En annan spelare lämnade. Matchen avslutas som en frånkoppling.')
  -- "Your match is still running. Rejoin? {0}"
  ,  ('5ff81c1cbcb1bc7b', 'es', '3bddba2aa07f0439693aac97861343544b2aa635', E'Tu partida sigue en curso. ¿Volver a unirte? {0}')
  ,  ('5ff81c1cbcb1bc7b', 'ru', '3bddba2aa07f0439693aac97861343544b2aa635', E'Ваш матч ещё идёт. Вернуться? {0}')
  ,  ('5ff81c1cbcb1bc7b', 'uk', '3bddba2aa07f0439693aac97861343544b2aa635', E'Ваш матч ще триває. Повернутися? {0}')
  ,  ('5ff81c1cbcb1bc7b', 'sv', '3bddba2aa07f0439693aac97861343544b2aa635', E'Din match pågår fortfarande. Återansluta? {0}')
  -- "Could not rejoin at this point"
  ,  ('66acd1c2d1011708', 'es', 'b259a93aa0fdab38481cedea7268c2e454ada899', E'No se pudo volver a unir en este momento')
  ,  ('66acd1c2d1011708', 'ru', 'b259a93aa0fdab38481cedea7268c2e454ada899', E'Не удалось вернуться на этом этапе')
  ,  ('66acd1c2d1011708', 'uk', 'b259a93aa0fdab38481cedea7268c2e454ada899', E'Не вдалося повернутися на цьому етапі')
  ,  ('66acd1c2d1011708', 'sv', 'b259a93aa0fdab38481cedea7268c2e454ada899', E'Kunde inte återansluta vid det här läget')
  -- "You are back in the match"
  ,  ('bd57f21b2e779ae1', 'es', '812fabb8632244503f103b70e66d722740ae855b', E'Has vuelto a la partida')
  ,  ('bd57f21b2e779ae1', 'ru', '812fabb8632244503f103b70e66d722740ae855b', E'Вы снова в матче')
  ,  ('bd57f21b2e779ae1', 'uk', '812fabb8632244503f103b70e66d722740ae855b', E'Ви знову в матчі')
  ,  ('bd57f21b2e779ae1', 'sv', '812fabb8632244503f103b70e66d722740ae855b', E'Du är tillbaka i matchen')
  -- "{0} (away) got {1}"
  ,  ('5be7e933e570652e', 'es', '0afb928a9a1a63e43a466df8800e5bf2db693dab', E'{0} (ausente) obtuvo {1}')
  ,  ('5be7e933e570652e', 'ru', '0afb928a9a1a63e43a466df8800e5bf2db693dab', E'{0} (отсутствует) получает {1}')
  ,  ('5be7e933e570652e', 'uk', '0afb928a9a1a63e43a466df8800e5bf2db693dab', E'{0} (відсутній) отримує {1}')
  ,  ('5be7e933e570652e', 'sv', '0afb928a9a1a63e43a466df8800e5bf2db693dab', E'{0} (borta) fick {1}')
;

INSERT INTO i18n_proposals
  (key_id, language_code, source_hash, proposed_target, proposer_steam_id,
   license_assent, license_terms_rev, assented_at, status, created_at)
SELECT v.key_id, v.lang, v.source_hash, v.target, 'claude-mt',
       TRUE, 'machine-v1', clock_timestamp(), 'pending', clock_timestamp()
  FROM _seed385 v
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
DECLARE
  uncovered INTEGER;
  sample TEXT;
BEGIN
  SELECT COUNT(*) INTO uncovered
    FROM _seed385 v
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
      FROM (SELECT v.key_id, v.lang FROM _seed385 v
             WHERE NOT EXISTS (
                     SELECT 1 FROM i18n_proposals p
                      WHERE p.key_id = v.key_id AND p.language_code = v.lang
                        AND (p.source_hash = v.source_hash OR p.status = 'pending'))
               AND NOT EXISTS (
                     SELECT 1 FROM i18n_entries e
                      WHERE e.key_id = v.key_id AND e.language_code = v.lang
                        AND e.state = 'approved')
             LIMIT 5) x;
    RAISE EXCEPTION 'migration 385: % of 44 seed pairs did not land (e.g. %) - the usual cause is that 384 / tools/i18n_sync_keys.py has not run against this database yet; nothing committed', uncovered, sample;
  END IF;

  RAISE NOTICE 'migration 385: all 44 seed pairs covered (11 keys x es/ru/uk/sv)';
END $$;

COMMIT;
