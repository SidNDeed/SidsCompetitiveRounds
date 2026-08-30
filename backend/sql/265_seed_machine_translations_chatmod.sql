-- 265_seed_machine_translations_chatmod.sql
--
-- Machine-translated proposal seeds (es/ru/uk/sv) for the 18 strings the
-- v1.39.6 chat-moderation batch added. Same contract as 184/189/213/223/239
-- and 243: PENDING proposals only, sentinel proposer 'claude-mt',
-- license_assent TRUE at the machine-translation terms revision. The same
-- 72 translations ship BUNDLED in I18nCatalogues.cs, so the client renders
-- them without approval; these proposals exist so human translators can
-- see/refine them through the portal (an approval overrides the bundled
-- value via the pack overlay).
--
-- key_id = sha1("client" || chr(0) || source)[:16] — the NUL-separator form
-- tools/i18n_sync_keys.py uses (NOT a space; the space form silently joins
-- nothing, which is how an earlier draft of a sibling migration would have
-- failed its own assertion).
--
-- ORDERING: seeds only keys already present in i18n_keys. Run order:
-- deploy API -> run tools/i18n_sync_keys.py -> apply this file (and 243).
-- On an unsynced database the assertion below RAISEs and the transaction
-- rolls back; re-run after the sync. Explicit BEGIN/COMMIT (#340); every
-- statement is idempotent under the wrapper's || re-run (#243).
BEGIN;

CREATE TEMP TABLE _seed265 (
  key_id      VARCHAR(16) NOT NULL,
  lang        VARCHAR(8)  NOT NULL,
  source_hash VARCHAR(40) NOT NULL,
  target      TEXT        NOT NULL
) ON COMMIT DROP;

INSERT INTO _seed265 (key_id, lang, source_hash, target) VALUES
  -- 'Chat Lockdown...'
    ('529d48be14697fb0', 'es', 'c1487c661b3824edef495d3a1e179de9b6fd9df3', 'Bloqueo del chat...')
  , ('529d48be14697fb0', 'ru', 'c1487c661b3824edef495d3a1e179de9b6fd9df3', 'Блокировка чата...')
  , ('529d48be14697fb0', 'uk', 'c1487c661b3824edef495d3a1e179de9b6fd9df3', 'Блокування чату...')
  , ('529d48be14697fb0', 'sv', 'c1487c661b3824edef495d3a1e179de9b6fd9df3', 'Chattlåsning...')
  -- 'Chat has been locked by moderators - messages are paused.'
  , ('3120a8bba946965b', 'es', '00e6378fd0ad4c8296ae49a11a180f2b8f595139', 'Los moderadores han bloqueado el chat - los mensajes están en pausa.')
  , ('3120a8bba946965b', 'ru', '00e6378fd0ad4c8296ae49a11a180f2b8f595139', 'Модераторы заблокировали чат - сообщения приостановлены.')
  , ('3120a8bba946965b', 'uk', '00e6378fd0ad4c8296ae49a11a180f2b8f595139', 'Модератори заблокували чат - повідомлення призупинено.')
  , ('3120a8bba946965b', 'sv', '00e6378fd0ad4c8296ae49a11a180f2b8f595139', 'Moderatorerna har låst chatten - meddelanden är pausade.')
  -- 'Chat has been unlocked - carry on.'
  , ('101c48b93dc18a1c', 'es', '229b63d4752af1d5e5266b484a27b937791c450f', 'El chat se ha desbloqueado - continúa.')
  , ('101c48b93dc18a1c', 'ru', '229b63d4752af1d5e5266b484a27b937791c450f', 'Чат разблокирован - продолжайте.')
  , ('101c48b93dc18a1c', 'uk', '229b63d4752af1d5e5266b484a27b937791c450f', 'Чат розблоковано - продовжуйте.')
  , ('101c48b93dc18a1c', 'sv', '229b63d4752af1d5e5266b484a27b937791c450f', 'Chatten är upplåst - fortsätt.')
  -- 'Chat is currently LOCKED.'
  , ('17b168c59cb4e7f1', 'es', '43c150859e877ae3f3011e3f47320e8383b13d67', 'El chat está BLOQUEADO.')
  , ('17b168c59cb4e7f1', 'ru', '43c150859e877ae3f3011e3f47320e8383b13d67', 'Чат сейчас ЗАБЛОКИРОВАН.')
  , ('17b168c59cb4e7f1', 'uk', '43c150859e877ae3f3011e3f47320e8383b13d67', 'Чат зараз ЗАБЛОКОВАНО.')
  , ('17b168c59cb4e7f1', 'sv', '43c150859e877ae3f3011e3f47320e8383b13d67', 'Chatten är LÅST just nu.')
  -- 'Chat is currently open.'
  , ('7aff9f0847fdcbe2', 'es', 'b490c649eb08657196c358270e67e5c0d5f8036b', 'El chat está abierto.')
  , ('7aff9f0847fdcbe2', 'ru', 'b490c649eb08657196c358270e67e5c0d5f8036b', 'Чат сейчас открыт.')
  , ('7aff9f0847fdcbe2', 'uk', 'b490c649eb08657196c358270e67e5c0d5f8036b', 'Чат зараз відкритий.')
  , ('7aff9f0847fdcbe2', 'sv', 'b490c649eb08657196c358270e67e5c0d5f8036b', 'Chatten är öppen just nu.')
  -- 'Chat is locked by moderators right now - your message was no'
  , ('75b31f59dc8e438a', 'es', 'ccf89e944f211bc90ff3942034ef0fa9402e2a52', 'Los moderadores han bloqueado el chat - tu mensaje no se envió.')
  , ('75b31f59dc8e438a', 'ru', 'ccf89e944f211bc90ff3942034ef0fa9402e2a52', 'Чат заблокирован модераторами - ваше сообщение не отправлено.')
  , ('75b31f59dc8e438a', 'uk', 'ccf89e944f211bc90ff3942034ef0fa9402e2a52', 'Чат заблоковано модераторами - ваше повідомлення не надіслано.')
  , ('75b31f59dc8e438a', 'sv', 'ccf89e944f211bc90ff3942034ef0fa9402e2a52', 'Chatten är låst av moderatorerna - ditt meddelande skickades inte.')
  -- 'How long?'
  , ('56bb047fa0c21ad1', 'es', '9ce819198916f31ef18b3eb733d0c0f8f44ae386', '¿Por cuánto tiempo?')
  , ('56bb047fa0c21ad1', 'ru', '9ce819198916f31ef18b3eb733d0c0f8f44ae386', 'На сколько?')
  , ('56bb047fa0c21ad1', 'uk', '9ce819198916f31ef18b3eb733d0c0f8f44ae386', 'На скільки?')
  , ('56bb047fa0c21ad1', 'sv', '9ce819198916f31ef18b3eb733d0c0f8f44ae386', 'Hur länge?')
  -- 'Keep it locked'
  , ('b9ddc17d768fa1b3', 'es', '68d7017152dfa47134be41079d6cf5f23253371a', 'Mantenerlo bloqueado')
  , ('b9ddc17d768fa1b3', 'ru', '68d7017152dfa47134be41079d6cf5f23253371a', 'Оставить заблокированным')
  , ('b9ddc17d768fa1b3', 'uk', '68d7017152dfa47134be41079d6cf5f23253371a', 'Залишити заблокованим')
  , ('b9ddc17d768fa1b3', 'sv', '68d7017152dfa47134be41079d6cf5f23253371a', 'Håll den låst')
  -- 'LOCK chat everywhere'
  , ('db538c880f1cfde9', 'es', '14103e23af3a7925ed4bf8b9c7e796d2b82e9751', 'BLOQUEAR el chat en todas partes')
  , ('db538c880f1cfde9', 'ru', '14103e23af3a7925ed4bf8b9c7e796d2b82e9751', 'ЗАБЛОКИРОВАТЬ чат везде')
  , ('db538c880f1cfde9', 'uk', '14103e23af3a7925ed4bf8b9c7e796d2b82e9751', 'ЗАБЛОКУВАТИ чат скрізь')
  , ('db538c880f1cfde9', 'sv', '14103e23af3a7925ed4bf8b9c7e796d2b82e9751', 'LÅS chatten överallt')
  -- 'Leave it open'
  , ('0b5dc7250d46a753', 'es', '7d0bac8c87e12fa00925f00cc2726a6442ee30e5', 'Dejarlo abierto')
  , ('0b5dc7250d46a753', 'ru', '7d0bac8c87e12fa00925f00cc2726a6442ee30e5', 'Оставить открытым')
  , ('0b5dc7250d46a753', 'uk', '7d0bac8c87e12fa00925f00cc2726a6442ee30e5', 'Залишити відкритим')
  , ('0b5dc7250d46a753', 'sv', '7d0bac8c87e12fa00925f00cc2726a6442ee30e5', 'Lämna den öppen')
  -- 'Link codes are disabled on the broadcast seat.'
  , ('0334124c315ddfdb', 'es', '275b7baf4f13ac034f94fad11c497b83c09a0630', 'Los códigos de vinculación están desactivados en el puesto de transmisión.')
  , ('0334124c315ddfdb', 'ru', '275b7baf4f13ac034f94fad11c497b83c09a0630', 'Коды привязки отключены на трансляционном месте.')
  , ('0334124c315ddfdb', 'uk', '275b7baf4f13ac034f94fad11c497b83c09a0630', 'Коди прив''язки вимкнено на трансляційному місці.')
  , ('0334124c315ddfdb', 'sv', '275b7baf4f13ac034f94fad11c497b83c09a0630', 'Länkkoder är inaktiverade på sändningsplatsen.')
  -- 'Mute From Message...'
  , ('4e893d4679622bc9', 'es', '52e0adc5e18938e15f75d0f573f7e2f782f03a2a', 'Silenciar desde mensaje...')
  , ('4e893d4679622bc9', 'ru', '52e0adc5e18938e15f75d0f573f7e2f782f03a2a', 'Мут по сообщению...')
  , ('4e893d4679622bc9', 'uk', '52e0adc5e18938e15f75d0f573f7e2f782f03a2a', 'Мут за повідомленням...')
  , ('4e893d4679622bc9', 'sv', '52e0adc5e18938e15f75d0f573f7e2f782f03a2a', 'Tysta via meddelande...')
  -- 'Mute from message'
  , ('ad4eadb6ec8876c5', 'es', 'cf62c5356606def907e33a05301d822b3ecd1e35', 'Silenciar desde mensaje')
  , ('ad4eadb6ec8876c5', 'ru', 'cf62c5356606def907e33a05301d822b3ecd1e35', 'Мут по сообщению')
  , ('ad4eadb6ec8876c5', 'uk', 'cf62c5356606def907e33a05301d822b3ecd1e35', 'Мут за повідомленням')
  , ('ad4eadb6ec8876c5', 'sv', 'cf62c5356606def907e33a05301d822b3ecd1e35', 'Tysta via meddelande')
  -- 'Mute the author of which message?'
  , ('85792e54b843280f', 'es', '30075a9c0c58a4307ec963912d41bb023e00e4d9', '¿Silenciar al autor de qué mensaje?')
  , ('85792e54b843280f', 'ru', '30075a9c0c58a4307ec963912d41bb023e00e4d9', 'Замутить автора какого сообщения?')
  , ('85792e54b843280f', 'uk', '30075a9c0c58a4307ec963912d41bb023e00e4d9', 'Замутити автора якого повідомлення?')
  , ('85792e54b843280f', 'sv', '30075a9c0c58a4307ec963912d41bb023e00e4d9', 'Tysta författaren till vilket meddelande?')
  -- "No server-issued chat lines are in this session's log.  Pick"
  , ('50b200539b8c78ee', 'es', '29873ae5ee3063929231f7ca5477418031d025e4', E'No hay líneas de chat emitidas por el servidor en el registro de esta sesión.\n\nElige un mensaje enviado por el autor; el silencio se aplica a la identidad de plataforma que lo escribió (Steam, Discord, Twitch o YouTube).')
  , ('50b200539b8c78ee', 'ru', '29873ae5ee3063929231f7ca5477418031d025e4', E'В журнале этой сессии нет строк чата, выданных сервером.\n\nВыберите сообщение автора; мут применяется к той платформе, с которой оно написано (Steam, Discord, Twitch или YouTube).')
  , ('50b200539b8c78ee', 'uk', '29873ae5ee3063929231f7ca5477418031d025e4', E'У журналі цієї сесії немає рядків чату, виданих сервером.\n\nВиберіть повідомлення автора; мут застосовується до платформи, з якої його написано (Steam, Discord, Twitch або YouTube).')
  , ('50b200539b8c78ee', 'sv', '29873ae5ee3063929231f7ca5477418031d025e4', E'Det finns inga serverutfärdade chattrader i den här sessionens logg.\n\nVälj ett meddelande författaren skickat; tystningen läggs på den plattformsidentitet som skrev det (Steam, Discord, Twitch eller YouTube).')
  -- 'Steam sign-in still pending - try again in a moment.'
  , ('16f08519634a53a5', 'es', '593d57b50f41ff087c272df7180b1ab47974acb9', 'El inicio de sesión de Steam sigue pendiente - inténtalo de nuevo en un momento.')
  , ('16f08519634a53a5', 'ru', '593d57b50f41ff087c272df7180b1ab47974acb9', 'Вход через Steam ещё выполняется - попробуйте чуть позже.')
  , ('16f08519634a53a5', 'uk', '593d57b50f41ff087c272df7180b1ab47974acb9', 'Вхід через Steam ще триває - спробуйте трохи пізніше.')
  , ('16f08519634a53a5', 'sv', '593d57b50f41ff087c272df7180b1ab47974acb9', 'Steam-inloggningen pågår fortfarande - försök igen om en stund.')
  -- 'Unlock chat everywhere'
  , ('cb26de5eb6b8bae9', 'es', '0c02be9dbb6c822f3fc0b908d522d6d420a801ad', 'Desbloquear el chat en todas partes')
  , ('cb26de5eb6b8bae9', 'ru', '0c02be9dbb6c822f3fc0b908d522d6d420a801ad', 'Разблокировать чат везде')
  , ('cb26de5eb6b8bae9', 'uk', '0c02be9dbb6c822f3fc0b908d522d6d420a801ad', 'Розблокувати чат скрізь')
  , ('cb26de5eb6b8bae9', 'sv', '0c02be9dbb6c822f3fc0b908d522d6d420a801ad', 'Lås upp chatten överallt')
  -- 'Why are they being muted?'
  , ('9caebef13ee3df25', 'es', 'f7684920539e981571f6a088e2ab56e1cadbf00f', '¿Por qué se le silencia?')
  , ('9caebef13ee3df25', 'ru', 'f7684920539e981571f6a088e2ab56e1cadbf00f', 'За что мут?')
  , ('9caebef13ee3df25', 'uk', 'f7684920539e981571f6a088e2ab56e1cadbf00f', 'За що мут?')
  , ('9caebef13ee3df25', 'sv', 'f7684920539e981571f6a088e2ab56e1cadbf00f', 'Varför tystas de?');

INSERT INTO i18n_proposals
  (key_id, language_code, source_hash, proposed_target, proposer_steam_id,
   license_assent, license_terms_rev, assented_at, status, created_at)
SELECT v.key_id, v.lang, v.source_hash, v.target, 'claude-mt',
       TRUE, 'machine-v1', NOW(), 'pending', NOW()
  FROM _seed265 v
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
  SELECT COUNT(*) INTO uncovered
    FROM _seed265 v
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
      FROM (SELECT v.key_id, v.lang FROM _seed265 v
             WHERE NOT EXISTS (
                     SELECT 1 FROM i18n_proposals p
                      WHERE p.key_id = v.key_id AND p.language_code = v.lang
                        AND (p.source_hash = v.source_hash OR p.status = 'pending'))
               AND NOT EXISTS (
                     SELECT 1 FROM i18n_entries e
                      WHERE e.key_id = v.key_id AND e.language_code = v.lang
                        AND e.state = 'approved')
             LIMIT 5) x;
    RAISE EXCEPTION 'migration 265: % of 72 seed pairs did not land (e.g. %) - the usual cause is that tools/i18n_sync_keys.py has not run against this database yet; nothing was committed', uncovered, sample;
  END IF;

  RAISE NOTICE 'migration 265: all 72 seed pairs covered (18 keys x es/ru/uk/sv)';
END $$;

COMMIT;
