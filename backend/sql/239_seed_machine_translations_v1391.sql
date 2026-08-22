-- 239_seed_machine_translations_v1391.sql
--
-- Machine-translated proposal seeds (es/ru/uk/sv) for the 44 client keys
-- bundled for v1.39.1:
--   - 2 tournament-history keys in the current source delta;
--   - 42 post-session-report/records keys from the Aug 19 coverage sweeps.
--
-- Same contract as 184/189/213/223: PENDING proposals only, sentinel
-- proposer 'claude-mt', license_assent TRUE at the machine-translation
-- terms revision. The same 176 translations ship BUNDLED in
-- I18nCatalogues.cs, so the client renders them without any approval; these
-- proposals exist so human translators can see/refine them through the
-- portal (an approval then overrides the bundled value via the pack overlay).
--
-- PREREQUISITE: the integrator must first run tools/i18n_extract.py in write
-- mode so tools/i18n_source.json contains the two current ADDED keys.
--
-- ORDERING: seeds only keys already present in i18n_keys, which
-- tools/i18n_sync_keys.py populates. Run order: deploy API -> run
-- tools/i18n_sync_keys.py -> apply this file. On an unsynced database the
-- assertion below RAISEs and the transaction rolls back; re-run after the
-- sync. Explicit BEGIN/COMMIT because the deploy wrapper's psql -f does
-- not wrap the file in a transaction (#340), and the wrapper's || fallback
-- re-runs the whole file (#243) - every statement is idempotent.
BEGIN;

CREATE TEMP TABLE _seed239 (
  key_id      VARCHAR(16) NOT NULL,
  lang        VARCHAR(8)  NOT NULL,
  source_hash VARCHAR(40) NOT NULL,
  target      TEXT        NOT NULL
) ON COMMIT DROP;

INSERT INTO _seed239 (key_id, lang, source_hash, target) VALUES
  ('3d2ea36308963515', 'es', '384e8e993068a9d3b73fbdac34f69d0bbc19ffa2', '(parcial)')
  , ('3d2ea36308963515', 'ru', '384e8e993068a9d3b73fbdac34f69d0bbc19ffa2', '(частично)')
  , ('3d2ea36308963515', 'uk', '384e8e993068a9d3b73fbdac34f69d0bbc19ffa2', '(частково)')
  , ('3d2ea36308963515', 'sv', '384e8e993068a9d3b73fbdac34f69d0bbc19ffa2', '(ofullständigt)')
  , ('1230b280e4d1ca09', 'es', 'e5af4ce71a82113afedde43f70c35c40229f887c', 'Historial 1v1: series {0}W-{1}L ({2}%)   juegos {3}W-{4}L')
  , ('1230b280e4d1ca09', 'ru', 'e5af4ce71a82113afedde43f70c35c40229f887c', 'Статистика 1v1: серии {0}W-{1}L ({2}%)   игры {3}W-{4}L')
  , ('1230b280e4d1ca09', 'uk', 'e5af4ce71a82113afedde43f70c35c40229f887c', 'Статистика 1v1: серії {0}W-{1}L ({2}%)   ігри {3}W-{4}L')
  , ('1230b280e4d1ca09', 'sv', 'e5af4ce71a82113afedde43f70c35c40229f887c', '1v1-resultat: serier {0}W-{1}L ({2}%)   matcher {3}W-{4}L')
  , ('adc860031b5295e6', 'es', '9aa5d08a389c60c574c2edc82c05d79e411ac131', '<color=#CCCCCC>Historial de puntos</color>  <color=#66DD66>{0}</color> <color=#888>vs</color> <color=#DD7777>rival</color>')
  , ('adc860031b5295e6', 'ru', '9aa5d08a389c60c574c2edc82c05d79e411ac131', '<color=#CCCCCC>История очков</color>  <color=#66DD66>{0}</color> <color=#888>vs</color> <color=#DD7777>соперник</color>')
  , ('adc860031b5295e6', 'uk', '9aa5d08a389c60c574c2edc82c05d79e411ac131', '<color=#CCCCCC>Історія очок</color>  <color=#66DD66>{0}</color> <color=#888>vs</color> <color=#DD7777>суперник</color>')
  , ('adc860031b5295e6', 'sv', '9aa5d08a389c60c574c2edc82c05d79e411ac131', '<color=#CCCCCC>Poänghistorik</color>  <color=#66DD66>{0}</color> <color=#888>vs</color> <color=#DD7777>motståndare</color>')
  , ('ec8d7a94985d2f92', 'es', '7c6eec66c9a19dfba83a37b6f5d91874f364b468', 'Total: {0} juegos ({1}W-{2}L), series {3}-{4}')
  , ('ec8d7a94985d2f92', 'ru', '7c6eec66c9a19dfba83a37b6f5d91874f364b468', 'За всё время: игр {0} ({1}W-{2}L), серии {3}-{4}')
  , ('ec8d7a94985d2f92', 'uk', '7c6eec66c9a19dfba83a37b6f5d91874f364b468', 'За весь час: ігор {0} ({1}W-{2}L), серії {3}-{4}')
  , ('ec8d7a94985d2f92', 'sv', '7c6eec66c9a19dfba83a37b6f5d91874f364b468', 'Totalt: {0} matcher ({1}W-{2}L), serier {3}-{4}')
  , ('6b0ae7187440ed3c', 'es', 'c7168a4f8553df38c93f5bcdf33499da2eaa326c', 'Tasa de bloqueo - {0}')
  , ('6b0ae7187440ed3c', 'ru', 'c7168a4f8553df38c93f5bcdf33499da2eaa326c', '% блоков - {0}')
  , ('6b0ae7187440ed3c', 'uk', 'c7168a4f8553df38c93f5bcdf33499da2eaa326c', '% блоків - {0}')
  , ('6b0ae7187440ed3c', 'sv', 'c7168a4f8553df38c93f5bcdf33499da2eaa326c', 'Blockprocent - {0}')
  , ('4bded0062544c6c1', 'es', '548bc7d4e4c72a8c8109d05c37ba08480735912b', 'Juego actual: {0}')
  , ('4bded0062544c6c1', 'ru', '548bc7d4e4c72a8c8109d05c37ba08480735912b', 'Текущая игра: {0}')
  , ('4bded0062544c6c1', 'uk', '548bc7d4e4c72a8c8109d05c37ba08480735912b', 'Поточна гра: {0}')
  , ('4bded0062544c6c1', 'sv', '548bc7d4e4c72a8c8109d05c37ba08480735912b', 'Nuvarande match: {0}')
  , ('f8eda8388cbfb9d1', 'es', '896bb6be6b7ff1931057c51860c1493a0857087d', 'Serie actual: {0}')
  , ('f8eda8388cbfb9d1', 'ru', '896bb6be6b7ff1931057c51860c1493a0857087d', 'Текущая серия: {0}')
  , ('f8eda8388cbfb9d1', 'uk', '896bb6be6b7ff1931057c51860c1493a0857087d', 'Поточна серія: {0}')
  , ('f8eda8388cbfb9d1', 'sv', '896bb6be6b7ff1931057c51860c1493a0857087d', 'Nuvarande serie: {0}')
  , ('f9c988548e02a432', 'es', 'f3cec91c2f03b8c3dd9c2dfd2ad1f22b511ff8be', 'DPS')
  , ('f9c988548e02a432', 'ru', 'f3cec91c2f03b8c3dd9c2dfd2ad1f22b511ff8be', 'DPS')
  , ('f9c988548e02a432', 'uk', 'f3cec91c2f03b8c3dd9c2dfd2ad1f22b511ff8be', 'DPS')
  , ('f9c988548e02a432', 'sv', 'f3cec91c2f03b8c3dd9c2dfd2ad1f22b511ff8be', 'DPS')
  , ('c60b3fb177ffdaaa', 'es', 'b59bfaaceed86fdb77668457fd1267dc817f3da0', 'Sesión FFA - {0} jugadores')
  , ('c60b3fb177ffdaaa', 'ru', 'b59bfaaceed86fdb77668457fd1267dc817f3da0', 'Сессия FFA - игроков: {0}')
  , ('c60b3fb177ffdaaa', 'uk', 'b59bfaaceed86fdb77668457fd1267dc817f3da0', 'Сесія FFA - гравців: {0}')
  , ('c60b3fb177ffdaaa', 'sv', 'b59bfaaceed86fdb77668457fd1267dc817f3da0', 'FFA-session - {0} spelare')
  , ('9503cca363369365', 'es', 'f374c265a0669927968583a277fce4434415e7ee', 'Sesión FFA - {0} jugadores, {1} juegos')
  , ('9503cca363369365', 'ru', 'f374c265a0669927968583a277fce4434415e7ee', 'Сессия FFA - игроков: {0}, игр: {1}')
  , ('9503cca363369365', 'uk', 'f374c265a0669927968583a277fce4434415e7ee', 'Сесія FFA - гравців: {0}, ігор: {1}')
  , ('9503cca363369365', 'sv', 'f374c265a0669927968583a277fce4434415e7ee', 'FFA-session - {0} spelare, {1} matcher')
  , ('6b2353195492bb8f', 'es', 'fce204ae554cd5820b35e0ae8653db07910f77d5', 'FPS')
  , ('6b2353195492bb8f', 'ru', 'fce204ae554cd5820b35e0ae8653db07910f77d5', 'FPS')
  , ('6b2353195492bb8f', 'uk', 'fce204ae554cd5820b35e0ae8653db07910f77d5', 'FPS')
  , ('6b2353195492bb8f', 'sv', 'fce204ae554cd5820b35e0ae8653db07910f77d5', 'FPS')
  , ('59bf3e91608fa618', 'es', '367483822a4e8f99275ed1daad31fe06fda784e9', 'Cartas favoritas en Ranked')
  , ('59bf3e91608fa618', 'ru', '367483822a4e8f99275ed1daad31fe06fda784e9', 'Любимые карты в Ranked')
  , ('59bf3e91608fa618', 'uk', '367483822a4e8f99275ed1daad31fe06fda784e9', 'Улюблені карти в Ranked')
  , ('59bf3e91608fa618', 'sv', '367483822a4e8f99275ed1daad31fe06fda784e9', 'Favoritkort i Ranked')
  , ('12a2ee7e09002750', 'es', '60067c6a686e7a3821f641d7c33e0dc78179d882', 'Juego {0}   {1} jugadores')
  , ('12a2ee7e09002750', 'ru', '60067c6a686e7a3821f641d7c33e0dc78179d882', 'Игра {0}   игроков: {1}')
  , ('12a2ee7e09002750', 'uk', '60067c6a686e7a3821f641d7c33e0dc78179d882', 'Гра {0}   гравців: {1}')
  , ('12a2ee7e09002750', 'sv', '60067c6a686e7a3821f641d7c33e0dc78179d882', 'Match {0}   {1} spelare')
  , ('ea1f96e30b6c6737', 'es', '5153f35507471943f8acdcfbb27f18b027db8af7', 'Juego {0}   {1} {2} {3}')
  , ('ea1f96e30b6c6737', 'ru', '5153f35507471943f8acdcfbb27f18b027db8af7', 'Игра {0}   {1} {2} {3}')
  , ('ea1f96e30b6c6737', 'uk', '5153f35507471943f8acdcfbb27f18b027db8af7', 'Гра {0}   {1} {2} {3}')
  , ('ea1f96e30b6c6737', 'sv', '5153f35507471943f8acdcfbb27f18b027db8af7', 'Match {0}   {1} {2} {3}')
  , ('5c9bcb043b857bb2', 'es', 'fd70315e6afaa97df008369227cf0b0b4a8a6b77', 'Juego {0}: {1}-{2}')
  , ('5c9bcb043b857bb2', 'ru', 'fd70315e6afaa97df008369227cf0b0b4a8a6b77', 'Игра {0}: {1}-{2}')
  , ('5c9bcb043b857bb2', 'uk', 'fd70315e6afaa97df008369227cf0b0b4a8a6b77', 'Гра {0}: {1}-{2}')
  , ('5c9bcb043b857bb2', 'sv', 'fd70315e6afaa97df008369227cf0b0b4a8a6b77', 'Match {0}: {1}-{2}')
  , ('9e93a32d4754dbb4', 'es', '01054b0109229cab306423442f0ce81891a39f58', 'Gráficas {0}/{1}')
  , ('9e93a32d4754dbb4', 'ru', '01054b0109229cab306423442f0ce81891a39f58', 'Графики {0}/{1}')
  , ('9e93a32d4754dbb4', 'uk', '01054b0109229cab306423442f0ce81891a39f58', 'Графіки {0}/{1}')
  , ('9e93a32d4754dbb4', 'sv', '01054b0109229cab306423442f0ce81891a39f58', 'Grafer {0}/{1}')
  , ('5b3e863917a976af', 'es', 'ad63b1980e7f9c3bba418b541020bc56100c81bf', 'Tasa de acierto - {0}')
  , ('5b3e863917a976af', 'ru', 'ad63b1980e7f9c3bba418b541020bc56100c81bf', 'Точность - {0}')
  , ('5b3e863917a976af', 'uk', 'ad63b1980e7f9c3bba418b541020bc56100c81bf', 'Точність - {0}')
  , ('5b3e863917a976af', 'sv', 'ad63b1980e7f9c3bba418b541020bc56100c81bf', 'Träffprocent - {0}')
  , ('745857a8dca56064', 'es', 'da0484d06004a9aca15a1d045da97cb7447fee94', 'Acierto {0}% Bloq. {1}%')
  , ('745857a8dca56064', 'ru', 'da0484d06004a9aca15a1d045da97cb7447fee94', 'Попад. {0}% Блок {1}%')
  , ('745857a8dca56064', 'uk', 'da0484d06004a9aca15a1d045da97cb7447fee94', 'Влуч. {0}% Блок {1}%')
  , ('745857a8dca56064', 'sv', 'da0484d06004a9aca15a1d045da97cb7447fee94', 'Träff {0}% Block {1}%')
  , ('b91c29dbe86f7b7f', 'es', '36b2d3606e2ae66c86595dad5736d619ea5b7993', 'Aún no se han registrado juegos en esta sesión.')
  , ('b91c29dbe86f7b7f', 'ru', '36b2d3606e2ae66c86595dad5736d619ea5b7993', 'В этой сессии пока нет записанных игр.')
  , ('b91c29dbe86f7b7f', 'uk', '36b2d3606e2ae66c86595dad5736d619ea5b7993', 'У цій сесії ще немає записаних ігор.')
  , ('b91c29dbe86f7b7f', 'sv', '36b2d3606e2ae66c86595dad5736d619ea5b7993', 'Inga matcher har registrerats för den här sessionen ännu.')
  , ('fd708efa416a95e0', 'es', 'b8da5460b86f1e75d07c7208311170d7c9b2bc81', 'Series totales: {0}')
  , ('fd708efa416a95e0', 'ru', 'b8da5460b86f1e75d07c7208311170d7c9b2bc81', 'Общий счёт серий: {0}')
  , ('fd708efa416a95e0', 'uk', 'b8da5460b86f1e75d07c7208311170d7c9b2bc81', 'Загальний рахунок серій: {0}')
  , ('fd708efa416a95e0', 'sv', 'b8da5460b86f1e75d07c7208311170d7c9b2bc81', 'Serier totalt: {0}')
  , ('f32e779b43ec84c1', 'es', '692b07e24b3da4d3c88ffc89a129035c6b3249a9', 'Pico {0}')
  , ('f32e779b43ec84c1', 'ru', '692b07e24b3da4d3c88ffc89a129035c6b3249a9', 'Пик {0}')
  , ('f32e779b43ec84c1', 'uk', '692b07e24b3da4d3c88ffc89a129035c6b3249a9', 'Пік {0}')
  , ('f32e779b43ec84c1', 'sv', '692b07e24b3da4d3c88ffc89a129035c6b3249a9', 'Topp {0}')
  , ('4932eaba51eabdd1', 'es', '6b68e97973994116d837d4de74f29d77f895c097', 'Ping')
  , ('4932eaba51eabdd1', 'ru', '6b68e97973994116d837d4de74f29d77f895c097', 'Пинг')
  , ('4932eaba51eabdd1', 'uk', '6b68e97973994116d837d4de74f29d77f895c097', 'Пінг')
  , ('4932eaba51eabdd1', 'sv', '6b68e97973994116d837d4de74f29d77f895c097', 'Ping')
  , ('9de65b2549d666fa', 'es', '2d3f4c8923cfcfdb406bad65aba2d2e8e958f521', 'Torneos Async recientes')
  , ('9de65b2549d666fa', 'ru', '2d3f4c8923cfcfdb406bad65aba2d2e8e958f521', 'Недавние асинхронные турниры')
  , ('9de65b2549d666fa', 'uk', '2d3f4c8923cfcfdb406bad65aba2d2e8e958f521', 'Останні асинхронні турніри')
  , ('9de65b2549d666fa', 'sv', '2d3f4c8923cfcfdb406bad65aba2d2e8e958f521', 'Senaste Async-turneringarna')
  , ('e8dc06c32c0e1fac', 'es', 'c32af79262e2e235f95d678dc3e8ce1a7dbe6775', 'Torneos Sync recientes')
  , ('e8dc06c32c0e1fac', 'ru', 'c32af79262e2e235f95d678dc3e8ce1a7dbe6775', 'Недавние синхронные турниры')
  , ('e8dc06c32c0e1fac', 'uk', 'c32af79262e2e235f95d678dc3e8ce1a7dbe6775', 'Останні синхронні турніри')
  , ('e8dc06c32c0e1fac', 'sv', 'c32af79262e2e235f95d678dc3e8ce1a7dbe6775', 'Senaste Sync-turneringarna')
  , ('19c2a45c2ec2988a', 'es', '489f4877244a299131d309f0ca10733c1a41251c', 'Puntuación')
  , ('19c2a45c2ec2988a', 'ru', '489f4877244a299131d309f0ca10733c1a41251c', 'Счёт')
  , ('19c2a45c2ec2988a', 'uk', '489f4877244a299131d309f0ca10733c1a41251c', 'Рахунок')
  , ('19c2a45c2ec2988a', 'sv', '489f4877244a299131d309f0ca10733c1a41251c', 'Poäng')
  , ('ed8b774e24ef3273', 'es', '8191b3f362a11adcdfb94a6adf53f0c3ddcdc46e', 'Serie {0} (en curso)')
  , ('ed8b774e24ef3273', 'ru', '8191b3f362a11adcdfb94a6adf53f0c3ddcdc46e', 'Серия {0} (идёт)')
  , ('ed8b774e24ef3273', 'uk', '8191b3f362a11adcdfb94a6adf53f0c3ddcdc46e', 'Серія {0} (триває)')
  , ('ed8b774e24ef3273', 'sv', '8191b3f362a11adcdfb94a6adf53f0c3ddcdc46e', 'Serie {0} (pågår)')
  , ('7aa6dd3d9c00eecb', 'es', '50bcfef87aaad308e18c1ebef30e73433fa21993', 'Serie {0} {1}')
  , ('7aa6dd3d9c00eecb', 'ru', '50bcfef87aaad308e18c1ebef30e73433fa21993', 'Серия {0} {1}')
  , ('7aa6dd3d9c00eecb', 'uk', '50bcfef87aaad308e18c1ebef30e73433fa21993', 'Серія {0} {1}')
  , ('7aa6dd3d9c00eecb', 'sv', '50bcfef87aaad308e18c1ebef30e73433fa21993', 'Serie {0} {1}')
  , ('6c07743895412e87', 'es', '88f7371eb24196978c257d2c1cc4a782622f8329', 'Series de la sesión: {0}')
  , ('6c07743895412e87', 'ru', '88f7371eb24196978c257d2c1cc4a782622f8329', 'Серии за сессию: {0}')
  , ('6c07743895412e87', 'uk', '88f7371eb24196978c257d2c1cc4a782622f8329', 'Серії за сесію: {0}')
  , ('6c07743895412e87', 'sv', '88f7371eb24196978c257d2c1cc4a782622f8329', 'Sessionens serier: {0}')
  , ('3e1302982adf89d9', 'es', 'a8261c72e1c14f8f93320767108077b4c0196a16', 'Juegos de la sesión')
  , ('3e1302982adf89d9', 'ru', 'a8261c72e1c14f8f93320767108077b4c0196a16', 'Игры за сессию')
  , ('3e1302982adf89d9', 'uk', 'a8261c72e1c14f8f93320767108077b4c0196a16', 'Ігри за сесію')
  , ('3e1302982adf89d9', 'sv', 'a8261c72e1c14f8f93320767108077b4c0196a16', 'Sessionens matcher')
  , ('0323dba24dc4ca77', 'es', '32be664aa6c0a222a968b2bcdc905e2598a5ca54', 'Juegos de la sesión ({0})')
  , ('0323dba24dc4ca77', 'ru', '32be664aa6c0a222a968b2bcdc905e2598a5ca54', 'Игры за сессию ({0})')
  , ('0323dba24dc4ca77', 'uk', '32be664aa6c0a222a968b2bcdc905e2598a5ca54', 'Ігри за сесію ({0})')
  , ('0323dba24dc4ca77', 'sv', '32be664aa6c0a222a968b2bcdc905e2598a5ca54', 'Sessionens matcher ({0})')
  , ('844df63fc7799788', 'es', '4ce68df25afe5893260f76998322877642b58529', 'Series de la sesión')
  , ('844df63fc7799788', 'ru', '4ce68df25afe5893260f76998322877642b58529', 'Серии за сессию')
  , ('844df63fc7799788', 'uk', '4ce68df25afe5893260f76998322877642b58529', 'Серії за сесію')
  , ('844df63fc7799788', 'sv', '4ce68df25afe5893260f76998322877642b58529', 'Sessionens serier')
  , ('bdd76249bfe4b65a', 'es', 'fa37d118d2801580d4a50deda71f91b82a8190d1', 'Series de la sesión ({0})')
  , ('bdd76249bfe4b65a', 'ru', 'fa37d118d2801580d4a50deda71f91b82a8190d1', 'Серии за сессию ({0})')
  , ('bdd76249bfe4b65a', 'uk', 'fa37d118d2801580d4a50deda71f91b82a8190d1', 'Серії за сесію ({0})')
  , ('bdd76249bfe4b65a', 'sv', 'fa37d118d2801580d4a50deda71f91b82a8190d1', 'Sessionens serier ({0})')
  , ('99713d7607aafd3f', 'es', 'b4b229ac922197e28e6f9420c0376c910f8f7fe3', 'Sesión: {0} juegos, series {1}-{2}')
  , ('99713d7607aafd3f', 'ru', 'b4b229ac922197e28e6f9420c0376c910f8f7fe3', 'За сессию: игр {0}, серии {1}-{2}')
  , ('99713d7607aafd3f', 'uk', 'b4b229ac922197e28e6f9420c0376c910f8f7fe3', 'За сесію: ігор {0}, серії {1}-{2}')
  , ('99713d7607aafd3f', 'sv', 'b4b229ac922197e28e6f9420c0376c910f8f7fe3', 'Session: {0} matcher, serier {1}-{2}')
  , ('a3e2201f0fd7c9b3', 'es', '6e2cdaa7ba0d3d15aa4ceecce82e43494145efe2', 'Sesión: {0} series')
  , ('a3e2201f0fd7c9b3', 'ru', '6e2cdaa7ba0d3d15aa4ceecce82e43494145efe2', 'Серий за сессию: {0}')
  , ('a3e2201f0fd7c9b3', 'uk', '6e2cdaa7ba0d3d15aa4ceecce82e43494145efe2', 'Серій за сесію: {0}')
  , ('a3e2201f0fd7c9b3', 'sv', '6e2cdaa7ba0d3d15aa4ceecce82e43494145efe2', 'Session: {0} serier')
  , ('0d08c15acf64fc37', 'es', '618c86600676077552bc3fcb0201a11317e768d5', 'Cartas top (todos los modos)')
  , ('0d08c15acf64fc37', 'ru', '618c86600676077552bc3fcb0201a11317e768d5', 'Топ карт (все режимы)')
  , ('0d08c15acf64fc37', 'uk', '618c86600676077552bc3fcb0201a11317e768d5', 'Топ карт (усі режими)')
  , ('0d08c15acf64fc37', 'sv', '618c86600676077552bc3fcb0201a11317e768d5', 'Toppkort (alla lägen)')
  , ('fe4a63da748dfc1e', 'es', '7b664f70da8a35f2e7c6ef8428a7141ea0cf3c3c', 'casual')
  , ('fe4a63da748dfc1e', 'ru', '7b664f70da8a35f2e7c6ef8428a7141ea0cf3c3c', 'обычная')
  , ('fe4a63da748dfc1e', 'uk', '7b664f70da8a35f2e7c6ef8428a7141ea0cf3c3c', 'звичайна')
  , ('fe4a63da748dfc1e', 'sv', '7b664f70da8a35f2e7c6ef8428a7141ea0cf3c3c', 'casual')
  , ('918e61d0f4abde33', 'es', 'b51992409edca91e5f36b8af904c5f333dff1f5c', 'datos de la partida no disponibles')
  , ('918e61d0f4abde33', 'ru', 'b51992409edca91e5f36b8af904c5f333dff1f5c', 'данные матча недоступны')
  , ('918e61d0f4abde33', 'uk', 'b51992409edca91e5f36b8af904c5f333dff1f5c', 'дані матчу недоступні')
  , ('918e61d0f4abde33', 'sv', 'b51992409edca91e5f36b8af904c5f333dff1f5c', 'matchdata är inte tillgängliga')
  , ('11746e605482ad0f', 'es', '46ec2f98b00b79b27fba942b4baae134d4ddfacd', 'mostrando {0} de {1}')
  , ('11746e605482ad0f', 'ru', '46ec2f98b00b79b27fba942b4baae134d4ddfacd', 'показано {0} из {1}')
  , ('11746e605482ad0f', 'uk', '46ec2f98b00b79b27fba942b4baae134d4ddfacd', 'показано {0} з {1}')
  , ('11746e605482ad0f', 'sv', '46ec2f98b00b79b27fba942b4baae134d4ddfacd', 'visar {0} av {1}')
  , ('e2dccdf13c763727', 'es', 'f6150e902e7ef2d4c9b43cb55901ba01a77039a4', '{0}  {1}%  ({2} elecciones)')
  , ('e2dccdf13c763727', 'ru', 'f6150e902e7ef2d4c9b43cb55901ba01a77039a4', '{0}  {1}%  (пиков: {2})')
  , ('e2dccdf13c763727', 'uk', 'f6150e902e7ef2d4c9b43cb55901ba01a77039a4', '{0}  {1}%  (піків: {2})')
  , ('e2dccdf13c763727', 'sv', 'f6150e902e7ef2d4c9b43cb55901ba01a77039a4', '{0}  {1}%  ({2} val)')
  , ('8d1eb7f439d936f8', 'es', '01af2476cdb74ff6297b08f331bcd2a1c276cf52', '{0} + {1} más')
  , ('8d1eb7f439d936f8', 'ru', '01af2476cdb74ff6297b08f331bcd2a1c276cf52', '{0} + ещё {1}')
  , ('8d1eb7f439d936f8', 'uk', '01af2476cdb74ff6297b08f331bcd2a1c276cf52', '{0} + ще {1}')
  , ('8d1eb7f439d936f8', 'sv', '01af2476cdb74ff6297b08f331bcd2a1c276cf52', '{0} + {1} till')
  , ('ea5a4baa04c86c8d', 'es', '74461284c35ce3294a098d44ec320782994dba20', '{0} juegos  {1} victorias  Top3 {2}%  Puesto medio {3}')
  , ('ea5a4baa04c86c8d', 'ru', '74461284c35ce3294a098d44ec320782994dba20', 'Игр: {0}  побед: {1}  Top3 {2}%  Ср. место {3}')
  , ('ea5a4baa04c86c8d', 'uk', '74461284c35ce3294a098d44ec320782994dba20', 'Ігор: {0}  перемог: {1}  Top3 {2}%  Сер. місце {3}')
  , ('ea5a4baa04c86c8d', 'sv', '74461284c35ce3294a098d44ec320782994dba20', '{0} matcher  {1} vinster  Top3 {2}%  Snittplats {3}')
  , ('8d2f51bb322a407c', 'es', 'b752606308eb98d088cea0df5ed83d968850cc18', '{0} bajas   {1} de daño')
  , ('8d2f51bb322a407c', 'ru', 'b752606308eb98d088cea0df5ed83d968850cc18', 'Убийств: {0}   урон: {1}')
  , ('8d2f51bb322a407c', 'uk', 'b752606308eb98d088cea0df5ed83d968850cc18', 'Вбивств: {0}   шкода: {1}')
  , ('8d2f51bb322a407c', 'sv', 'b752606308eb98d088cea0df5ed83d968850cc18', '{0} kills   {1} skada')
  , ('515b68d89b1340f5', 'es', '152c34217212e77f1f0a331aeb6b60286b866830', '{0} jugadores')
  , ('515b68d89b1340f5', 'ru', '152c34217212e77f1f0a331aeb6b60286b866830', 'Игроков: {0}')
  , ('515b68d89b1340f5', 'uk', '152c34217212e77f1f0a331aeb6b60286b866830', 'Гравців: {0}')
  , ('515b68d89b1340f5', 'sv', '152c34217212e77f1f0a331aeb6b60286b866830', '{0} spelare')
  , ('108905e2123ecbc7', 'es', 'fdbd930f257ec2e3bbc02d2dfd80bd59887488ca', '{0} series jugadas')
  , ('108905e2123ecbc7', 'ru', 'fdbd930f257ec2e3bbc02d2dfd80bd59887488ca', 'Сыграно серий: {0}')
  , ('108905e2123ecbc7', 'uk', 'fdbd930f257ec2e3bbc02d2dfd80bd59887488ca', 'Зіграно серій: {0}')
  , ('108905e2123ecbc7', 'sv', 'fdbd930f257ec2e3bbc02d2dfd80bd59887488ca', '{0} spelade serier')
;

INSERT INTO i18n_proposals
  (key_id, language_code, source_hash, proposed_target, proposer_steam_id,
   license_assent, license_terms_rev, assented_at, status, created_at)
SELECT v.key_id, v.lang, v.source_hash, v.target, 'claude-mt',
       TRUE, 'machine-v1', NOW(), 'pending', NOW()
  FROM _seed239 v
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
    FROM _seed239 v
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
      FROM (SELECT v.key_id, v.lang FROM _seed239 v
             WHERE NOT EXISTS (
                     SELECT 1 FROM i18n_proposals p
                      WHERE p.key_id = v.key_id AND p.language_code = v.lang
                        AND (p.source_hash = v.source_hash OR p.status = 'pending'))
               AND NOT EXISTS (
                     SELECT 1 FROM i18n_entries e
                      WHERE e.key_id = v.key_id AND e.language_code = v.lang
                        AND e.state = 'approved')
             LIMIT 5) x;
    RAISE EXCEPTION 'migration 239: % of 176 seed pairs did not land (e.g. %) - the usual cause is that tools/i18n_sync_keys.py has not run against this database yet; nothing was committed', uncovered, sample;
  END IF;

  RAISE NOTICE 'migration 239: all 176 seed pairs covered (44 keys x es/ru/uk/sv)';
END $$;

COMMIT;
