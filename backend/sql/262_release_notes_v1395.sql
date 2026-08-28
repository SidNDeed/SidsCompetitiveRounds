-- 262: v1.39.5 release notes, all five locales.
-- Same channel as migrations 250/254: the admin POST endpoint's idempotent
-- upsert into release_notes_i18n, performed through the migration channel
-- (the VM seat's tools read ADMIN_HMAC_SECRET from env, which this seat does
-- not set — learning #443). en is the human source; es/ru/uk/sv are machine
-- translations reviewed against the in-game catalogue terminology.

BEGIN;

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.39.5', 'en', '', $rn1395en$# v1.39.5

The launch build — Competitive ROUNDS is officially out of beta. Welcome, everyone joining from the announcement!

## Titles

- **New players now start with the live rank title equipped** — it updates automatically as you climb the ladder.
- **The Beta title is retired.** Nobody new can get it, but if you played during the beta it is yours forever and stays equippable. Wear it proudly — you built this.
$rn1395en$, 'human', NULL)
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.39.5', 'es', '', $rn1395es$# v1.39.5

La build de lanzamiento: Competitive ROUNDS sale oficialmente de la beta. ¡Bienvenidos todos los que llegan desde el anuncio!

## Títulos

- **Los jugadores nuevos ahora empiezan con el título de rango en vivo equipado** — se actualiza automáticamente a medida que subes en la clasificación.
- **El título Beta se retira.** Nadie nuevo puede conseguirlo, pero si jugaste durante la beta es tuyo para siempre y se puede seguir equipando. Llévalo con orgullo: tú ayudaste a construir esto.
$rn1395es$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.39.5', 'ru', '', $rn1395ru$# v1.39.5

Релизная сборка — Competitive ROUNDS официально выходит из беты. Добро пожаловать всем, кто пришёл после анонса!

## Титулы

- **Новые игроки теперь начинают с надетым живым титулом ранга** — он обновляется автоматически по мере подъёма в таблице.
- **Титул Beta уходит на покой.** Новые игроки его больше не получат, но если вы играли в бету — он ваш навсегда, и его по-прежнему можно надеть. Носите с гордостью: вы помогли всё это создать.
$rn1395ru$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.39.5', 'uk', '', $rn1395uk$# v1.39.5

Реліз-збірка — Competitive ROUNDS офіційно виходить з бети. Ласкаво просимо всім, хто прийшов після анонсу!

## Титули

- **Нові гравці тепер починають з одягненим живим титулом рангу** — він оновлюється автоматично, коли ви підіймаєтеся в таблиці.
- **Титул Beta більше не видається.** Нові гравці його не отримають, але якщо ви грали в бету — він ваш назавжди, і його досі можна одягнути. Носіть із гордістю: ви допомогли це створити.
$rn1395uk$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.39.5', 'sv', '', $rn1395sv$# v1.39.5

Lanseringsbygget — Competitive ROUNDS lämnar officiellt betan. Välkomna alla som hittar hit från tillkännagivandet!

## Titlar

- **Nya spelare börjar nu med den levande rangtiteln utrustad** — den uppdateras automatiskt när du klättrar på stegen.
- **Beta-titeln pensioneras.** Ingen ny spelare kan få den, men spelade du under betan är den din för alltid och kan fortfarande utrustas. Bär den med stolthet — ni byggde det här.
$rn1395sv$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

COMMIT;
