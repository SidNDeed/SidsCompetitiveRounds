-- 380_seed_machine_translations_ffa_readmit.sql
--
-- Machine-translated proposal seeds (es/ru/uk/sv) for the client strings FFA mid-game
-- readmission adds (15 keys of 379, 60 pairs). Same contract as 184/213/303/313/318: PENDING
-- proposals only, sentinel proposer 'claude-mt', license_assent TRUE at the machine-translation
-- terms revision. These proposals exist so human translators can see and refine them through
-- the portal (an approval overrides the bundled value via the pack overlay).
--
-- key_id = sha1("client" || chr(0) || source)[:16] - the NUL-separator form
-- tools/i18n_sync_keys.py uses.
--
-- ORDERING: seeds only keys already present in i18n_keys. Run order:
-- deploy API, then apply 379 (or run tools/i18n_sync_keys.py), then apply this
-- file. On an unsynced database the assertion below RAISEs and the transaction
-- rolls back; re-run after the keys land. Explicit BEGIN/COMMIT (#340); every
-- statement is idempotent under the wrapper's re-run (#243).
BEGIN;

CREATE TEMP TABLE _seed380 (
  key_id      VARCHAR(16) NOT NULL,
  lang        VARCHAR(8)  NOT NULL,
  source_hash VARCHAR(40) NOT NULL,
  target      TEXT        NOT NULL
) ON COMMIT DROP;

INSERT INTO _seed380 (key_id, lang, source_hash, target) VALUES
  -- "Your FFA match is still running. Rejoin? {0}"
     ('01c1ced9ae420dcb', 'es', 'a09387a2e372ec9a480465c4d160e094e93a97a9', $t$Tu partida FFA sigue en curso. ¿Volver a entrar? {0}$t$)
  ,  ('01c1ced9ae420dcb', 'ru', 'a09387a2e372ec9a480465c4d160e094e93a97a9', $t$Твой матч FFA ещё идёт. Вернуться? {0}$t$)
  ,  ('01c1ced9ae420dcb', 'uk', 'a09387a2e372ec9a480465c4d160e094e93a97a9', $t$Ваш матч FFA ще триває. Повернутися? {0}$t$)
  ,  ('01c1ced9ae420dcb', 'sv', 'a09387a2e372ec9a480465c4d160e094e93a97a9', $t$Din FFA-match pågår fortfarande. Gå med igen? {0}$t$)
  -- "You are in another queue"
  ,  ('29bd0b648d3d1e87', 'es', 'dbfce522b1a9fd91cdefe7ede4251f864eeeb51f', $t$Estás en otra cola$t$)
  ,  ('29bd0b648d3d1e87', 'ru', 'dbfce522b1a9fd91cdefe7ede4251f864eeeb51f', $t$Ты в другой очереди$t$)
  ,  ('29bd0b648d3d1e87', 'uk', 'dbfce522b1a9fd91cdefe7ede4251f864eeeb51f', $t$Ви в іншій черзі$t$)
  ,  ('29bd0b648d3d1e87', 'sv', 'dbfce522b1a9fd91cdefe7ede4251f864eeeb51f', $t$Du står i en annan kö$t$)
  -- "Joining the match at the next point"
  ,  ('45601925442a93f3', 'es', 'ea08b8e2ea3faa610418cbe49c746f47e2190943', $t$Entrando en la partida en el próximo punto$t$)
  ,  ('45601925442a93f3', 'ru', 'ea08b8e2ea3faa610418cbe49c746f47e2190943', $t$Вход в матч со следующего очка$t$)
  ,  ('45601925442a93f3', 'uk', 'ea08b8e2ea3faa610418cbe49c746f47e2190943', $t$Вхід у матч з наступного очка$t$)
  ,  ('45601925442a93f3', 'sv', 'ea08b8e2ea3faa610418cbe49c746f47e2190943', $t$Går med i matchen vid nästa poäng$t$)
  -- "That match has ended"
  ,  ('479ff1480605bff3', 'es', '89af1992a09f84e3cfd2e108474917e71cdab03c', $t$Esa partida ha terminado$t$)
  ,  ('479ff1480605bff3', 'ru', '89af1992a09f84e3cfd2e108474917e71cdab03c', $t$Этот матч закончился$t$)
  ,  ('479ff1480605bff3', 'uk', '89af1992a09f84e3cfd2e108474917e71cdab03c', $t$Цей матч завершився$t$)
  ,  ('479ff1480605bff3', 'sv', '89af1992a09f84e3cfd2e108474917e71cdab03c', $t$Den matchen är slut$t$)
  -- "Automatic pick: {0}"
  ,  ('553c1cb857bf44de', 'es', '0ef31b05fb51c0f4d4f26373278ece2b440a98f6', $t$Elección automática: {0}$t$)
  ,  ('553c1cb857bf44de', 'ru', '0ef31b05fb51c0f4d4f26373278ece2b440a98f6', $t$Автоматический выбор: {0}$t$)
  ,  ('553c1cb857bf44de', 'uk', '0ef31b05fb51c0f4d4f26373278ece2b440a98f6', $t$Автоматичний вибір: {0}$t$)
  ,  ('553c1cb857bf44de', 'sv', '0ef31b05fb51c0f4d4f26373278ece2b440a98f6', $t$Automatiskt val: {0}$t$)
  -- "{0} (away) got {1}"
  ,  ('5be7e933e570652e', 'es', '0afb928a9a1a63e43a466df8800e5bf2db693dab', $t${0} (ausente) recibió {1}$t$)
  ,  ('5be7e933e570652e', 'ru', '0afb928a9a1a63e43a466df8800e5bf2db693dab', $t${0} (отсутствует) получил {1}$t$)
  ,  ('5be7e933e570652e', 'uk', '0afb928a9a1a63e43a466df8800e5bf2db693dab', $t${0} (відсутній) отримав {1}$t$)
  ,  ('5be7e933e570652e', 'sv', '0afb928a9a1a63e43a466df8800e5bf2db693dab', $t${0} (borta) fick {1}$t$)
  -- "Could not rejoin at this point"
  ,  ('66acd1c2d1011708', 'es', 'b259a93aa0fdab38481cedea7268c2e454ada899', $t$No se pudo volver a entrar en este momento$t$)
  ,  ('66acd1c2d1011708', 'ru', 'b259a93aa0fdab38481cedea7268c2e454ada899', $t$Сейчас вернуться не удалось$t$)
  ,  ('66acd1c2d1011708', 'uk', 'b259a93aa0fdab38481cedea7268c2e454ada899', $t$Зараз повернутися не вдалося$t$)
  ,  ('66acd1c2d1011708', 'sv', 'b259a93aa0fdab38481cedea7268c2e454ada899', $t$Kunde inte gå med igen just nu$t$)
  -- "{0} did not return; seat released"
  ,  ('6f660f7ab40c9fb1', 'es', 'dde36fb32699b8f418e4ddd09014d5b814a911d4', $t${0} no volvió; plaza liberada$t$)
  ,  ('6f660f7ab40c9fb1', 'ru', 'dde36fb32699b8f418e4ddd09014d5b814a911d4', $t${0} не вернулся; место освобождено$t$)
  ,  ('6f660f7ab40c9fb1', 'uk', 'dde36fb32699b8f418e4ddd09014d5b814a911d4', $t${0} не повернувся; місце звільнено$t$)
  ,  ('6f660f7ab40c9fb1', 'sv', 'dde36fb32699b8f418e4ddd09014d5b814a911d4', $t${0} kom inte tillbaka; platsen släpptes$t$)
  -- "Could not confirm your seat. Retrying"
  ,  ('86fd5a3453cbbbad', 'es', 'a946a02658260725c4a859acbedd45aa9f8c9bcf', $t$No se pudo confirmar tu plaza. Reintentando$t$)
  ,  ('86fd5a3453cbbbad', 'ru', 'a946a02658260725c4a859acbedd45aa9f8c9bcf', $t$Не удалось подтвердить твоё место. Повторяем$t$)
  ,  ('86fd5a3453cbbbad', 'uk', 'a946a02658260725c4a859acbedd45aa9f8c9bcf', $t$Не вдалося підтвердити ваше місце. Повторюємо$t$)
  ,  ('86fd5a3453cbbbad', 'sv', 'a946a02658260725c4a859acbedd45aa9f8c9bcf', $t$Kunde inte bekräfta din plats. Försöker igen$t$)
  -- "You left that match"
  ,  ('98cb664fca411c1c', 'es', '58e59499aca516fd0e4882b43fd6ed5781b5b9a8', $t$Abandonaste esa partida$t$)
  ,  ('98cb664fca411c1c', 'ru', '58e59499aca516fd0e4882b43fd6ed5781b5b9a8', $t$Ты покинул этот матч$t$)
  ,  ('98cb664fca411c1c', 'uk', '58e59499aca516fd0e4882b43fd6ed5781b5b9a8', $t$Ви покинули цей матч$t$)
  ,  ('98cb664fca411c1c', 'sv', '58e59499aca516fd0e4882b43fd6ed5781b5b9a8', $t$Du lämnade den matchen$t$)
  -- "Seat held for {0}: {1}"
  ,  ('98dca83410faa64d', 'es', '90aaed15747edd34574438630be3c33807ba421f', $t$Plaza reservada para {0}: {1}$t$)
  ,  ('98dca83410faa64d', 'ru', '90aaed15747edd34574438630be3c33807ba421f', $t$Место удерживается для {0}: {1}$t$)
  ,  ('98dca83410faa64d', 'uk', '90aaed15747edd34574438630be3c33807ba421f', $t$Місце утримується для {0}: {1}$t$)
  ,  ('98dca83410faa64d', 'sv', '90aaed15747edd34574438630be3c33807ba421f', $t$Platsen hålls för {0}: {1}$t$)
  -- "The seat was released before you returned"
  ,  ('ade21bda2fc0c1a5', 'es', '599201187ca682b14c718c1edf1c2e8f8f1d5919', $t$La plaza se liberó antes de que volvieras$t$)
  ,  ('ade21bda2fc0c1a5', 'ru', '599201187ca682b14c718c1edf1c2e8f8f1d5919', $t$Место освободили до твоего возвращения$t$)
  ,  ('ade21bda2fc0c1a5', 'uk', '599201187ca682b14c718c1edf1c2e8f8f1d5919', $t$Місце звільнили до вашого повернення$t$)
  ,  ('ade21bda2fc0c1a5', 'sv', '599201187ca682b14c718c1edf1c2e8f8f1d5919', $t$Platsen släpptes innan du kom tillbaka$t$)
  -- "{0} is back"
  ,  ('b933f3c706c40e83', 'es', 'cc3dd7d00b80a320c4d93ae1705baf8de7816bdb', $t${0} ha vuelto$t$)
  ,  ('b933f3c706c40e83', 'ru', 'cc3dd7d00b80a320c4d93ae1705baf8de7816bdb', $t${0} вернулся$t$)
  ,  ('b933f3c706c40e83', 'uk', 'cc3dd7d00b80a320c4d93ae1705baf8de7816bdb', $t${0} повернувся$t$)
  ,  ('b933f3c706c40e83', 'sv', 'cc3dd7d00b80a320c4d93ae1705baf8de7816bdb', $t${0} är tillbaka$t$)
  -- "You are back in the match"
  ,  ('bd57f21b2e779ae1', 'es', '812fabb8632244503f103b70e66d722740ae855b', $t$Has vuelto a la partida$t$)
  ,  ('bd57f21b2e779ae1', 'ru', '812fabb8632244503f103b70e66d722740ae855b', $t$Ты снова в матче$t$)
  ,  ('bd57f21b2e779ae1', 'uk', '812fabb8632244503f103b70e66d722740ae855b', $t$Ви знову в матчі$t$)
  ,  ('bd57f21b2e779ae1', 'sv', '812fabb8632244503f103b70e66d722740ae855b', $t$Du är tillbaka i matchen$t$)
  -- "Another player is using your seat identity"
  ,  ('c350b64d06ed03ad', 'es', '26795e3f584178571150f96c7886efc9bfe1cef7', $t$Otro jugador está usando la identidad de tu plaza$t$)
  ,  ('c350b64d06ed03ad', 'ru', '26795e3f584178571150f96c7886efc9bfe1cef7', $t$Другой игрок использует идентификатор твоего места$t$)
  ,  ('c350b64d06ed03ad', 'uk', '26795e3f584178571150f96c7886efc9bfe1cef7', $t$Інший гравець використовує ідентифікатор вашого місця$t$)
  ,  ('c350b64d06ed03ad', 'sv', '26795e3f584178571150f96c7886efc9bfe1cef7', $t$En annan spelare använder din platsidentitet$t$)
;

INSERT INTO i18n_proposals
  (key_id, language_code, source_hash, proposed_target, proposer_steam_id,
   license_assent, license_terms_rev, assented_at, status, created_at)
SELECT v.key_id, v.lang, v.source_hash, v.target, 'claude-mt',
       TRUE, 'machine-v1', clock_timestamp(), 'pending', clock_timestamp()
  FROM _seed380 v
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
    FROM _seed380 v
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
      FROM (SELECT v.key_id, v.lang FROM _seed380 v
             WHERE NOT EXISTS (
                     SELECT 1 FROM i18n_proposals p
                      WHERE p.key_id = v.key_id AND p.language_code = v.lang
                        AND (p.source_hash = v.source_hash OR p.status = 'pending'))
               AND NOT EXISTS (
                     SELECT 1 FROM i18n_entries e
                      WHERE e.key_id = v.key_id AND e.language_code = v.lang
                        AND e.state = 'approved')
             LIMIT 5) x;
    RAISE EXCEPTION 'migration 380: % of 60 seed pairs did not land (e.g. %) - the usual cause is that 379 / tools/i18n_sync_keys.py has not run against this database yet; nothing committed', uncovered, sample;
  END IF;
  IF (SELECT COUNT(*) FROM _seed380) <> 60 THEN
    RAISE EXCEPTION 'migration 380: the seed table holds % pairs, expected 60', (SELECT COUNT(*) FROM _seed380);
  END IF;

  RAISE NOTICE 'migration 380: all 60 seed pairs covered (15 keys x es/ru/uk/sv)';
END $$;

COMMIT;
