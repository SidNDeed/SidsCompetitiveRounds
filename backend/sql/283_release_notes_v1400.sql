-- 283: v1.40.0 release notes, all five locales.
-- The admin POST endpoint is an idempotent upsert into release_notes_i18n;
-- this migration performs the identical write through the migration channel
-- because the VM seat's tooling cannot sign the admin HMAC (learning #443 -
-- the tools read ADMIN_HMAC_SECRET from the environment, never set here).
-- en is the source; es/ru/uk/sv are machine translations matched to the
-- in-game catalogue terminology (same pipeline as 250/262).

BEGIN;

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.40.0', 'en', '', $rn1400en$# v1.40.0

## MUSIC IS HERE

- New MUSIC tab (F5): a full music player - play/pause, skip, seek, shuffle,
  loop, volume - with the vanilla ROUNDS OST plus every album you own. Pick
  exactly which songs play in your matches; everything sounds vanilla until
  you change something.
- Two albums by Sid in the Shop's MUSIC section: Another Round (7 tracks,
  Metal / Phonk, 1g) and Clavar la Bala (12 tracks, Flamenco Metal, 1,000g).
  Expand an album to preview any song for 30 seconds before buying.
- Rate songs 0-5 stars right in the track list. Your ratings are private;
  the community average updates on a delay.
- Music artists earn 50% of album sales and can gift copies. New settings:
  menu music (default / your playlist / silence) and an opt-in "Now Playing"
  credit line.

## DANCES GOT LEGS (SORT OF)

- Six new dances in the shop: Jumping Jacks, The Shimmy, Disco Fever, The
  Helicopter, The Robot, and The Floss - and every dance now moves the whole
  body: hops, leans, shimmies and hip-sway, not just arms.

## EVERYTHING FROM THE LAST BATCH

- Quick chat is a wheel (hold Q), dance emotes on their own wheel (hold E),
  the Silence X actually renders, betting locks when it should, healing you
  can see, and a pile of smaller fixes.
$rn1400en$, 'human', NULL)
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.40.0', 'es', '', $rn1400es$# v1.40.0

## LA MÚSICA YA ESTÁ AQUÍ

- Nueva pestaña MUSIC (F5): un reproductor completo - reproducir/pausar,
  saltar, adelantar, aleatorio, bucle, volumen - con la OST vanilla de
  ROUNDS más todos los álbumes que tengas. Elige exactamente qué canciones
  suenan en tus partidas; todo suena vanilla hasta que cambies algo.
- Dos álbumes de Sid en la sección MUSIC de la tienda: Another Round
  (7 temas, Metal / Phonk, 1g) y Clavar la Bala (12 temas, Flamenco Metal,
  1,000g). Despliega un álbum para escuchar 30 segundos de cualquier tema
  antes de comprar.
- Puntúa las canciones de 0 a 5 estrellas directamente en la lista de
  temas. Tus valoraciones son privadas; la media de la comunidad se
  actualiza con retraso.
- Los artistas musicales ganan el 50% de las ventas de sus álbumes y pueden
  regalar copias. Ajustes nuevos: música del menú (por defecto / tu
  playlist / silencio) y una línea de crédito "Now Playing" opcional.

## LOS BAILES YA TIENEN PIERNAS (MÁS O MENOS)

- Seis bailes nuevos en la tienda: Jumping Jacks, The Shimmy, Disco Fever,
  The Helicopter, The Robot y The Floss - y ahora cada baile mueve todo el
  cuerpo: saltitos, inclinaciones, meneos y vaivén de caderas, no solo los
  brazos.

## TODO LO DEL LOTE ANTERIOR

- El chat rápido ahora es una rueda (mantén Q), los emotes de baile tienen
  su propia rueda (mantén E), el Silence X por fin se ve, las apuestas se
  bloquean cuando toca, curación que se puede ver, y un montón de arreglos
  menores.
$rn1400es$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.40.0', 'ru', '', $rn1400ru$# v1.40.0

## МУЗЫКА УЖЕ ЗДЕСЬ

- Новая вкладка MUSIC (F5): полноценный плеер - воспроизведение/пауза,
  пропуск, перемотка, перемешивание, повтор, громкость - с ванильным OST
  ROUNDS плюс все альбомы, которыми вы владеете. Выбирайте, какие именно
  песни звучат в ваших матчах; всё звучит ванильно, пока вы что-то не
  измените.
- Два альбома от Sid в разделе MUSIC магазина: Another Round (7 треков,
  Metal / Phonk, 1g) и Clavar la Bala (12 треков, Flamenco Metal, 1,000g).
  Разверните альбом, чтобы прослушать 30 секунд любой песни перед покупкой.
- Оценивайте песни от 0 до 5 звёзд прямо в списке треков. Ваши оценки
  приватны; средняя оценка сообщества обновляется с задержкой.
- Музыкальные артисты получают 50% с продаж альбомов и могут дарить копии.
  Новые настройки: музыка в меню (по умолчанию / ваш плейлист / тишина) и
  включаемая по желанию строка "Now Playing".

## У ТАНЦЕВ ПОЯВИЛИСЬ НОГИ (ПОЧТИ)

- Шесть новых танцев в магазине: Jumping Jacks, The Shimmy, Disco Fever,
  The Helicopter, The Robot и The Floss - и теперь каждый танец двигает
  всё тело: прыжки, наклоны, шимми и покачивание бёдрами, а не только
  руки.

## ВСЁ ИЗ ПРОШЛОЙ ПАРТИИ

- Быстрый чат теперь колесо (удерживайте Q), танцевальные эмоции - на
  своём колесе (удерживайте E), Silence X наконец-то отображается, ставки
  блокируются, когда положено, лечение теперь видно, и куча мелких
  исправлений.
$rn1400ru$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.40.0', 'uk', '', $rn1400uk$# v1.40.0

## МУЗИКА ВЖЕ ТУТ

- Нова вкладка MUSIC (F5): повноцінний плеєр - відтворення/пауза, пропуск,
  перемотування, перемішування, повтор, гучність - з ванільним OST ROUNDS
  плюс усі альбоми, якими ви володієте. Обирайте, які саме пісні звучать у
  ваших матчах; усе звучить ванільно, доки ви щось не зміните.
- Два альбоми від Sid у розділі MUSIC крамниці: Another Round (7 треків,
  Metal / Phonk, 1g) і Clavar la Bala (12 треків, Flamenco Metal, 1,000g).
  Розгорніть альбом, щоб прослухати 30 секунд будь-якої пісні перед
  купівлею.
- Оцінюйте пісні від 0 до 5 зірок просто у списку треків. Ваші оцінки
  приватні; середня оцінка спільноти оновлюється із затримкою.
- Музичні артисти отримують 50% від продажів альбомів і можуть дарувати
  копії. Нові налаштування: музика в меню (за замовчуванням / ваш
  плейлист / тиша) і додатковий рядок "Now Playing" за бажанням.

## У ТАНЦІВ З'ЯВИЛИСЯ НОГИ (МАЙЖЕ)

- Шість нових танців у крамниці: Jumping Jacks, The Shimmy, Disco Fever,
  The Helicopter, The Robot і The Floss - і тепер кожен танець рухає все
  тіло: стрибки, нахили, шиммі та похитування стегнами, а не лише руки.

## УСЕ З МИНУЛОЇ ПАРТІЇ

- Швидкий чат тепер колесо (утримуйте Q), танцювальні емоції - на
  власному колесі (утримуйте E), Silence X нарешті відображається, ставки
  блокуються, коли треба, лікування тепер видно, і купа дрібних
  виправлень.
$rn1400uk$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.40.0', 'sv', '', $rn1400sv$# v1.40.0

## MUSIKEN ÄR HÄR

- Ny MUSIC-flik (F5): en komplett musikspelare - spela/pausa, hoppa över,
  spola, blanda, loopa, volym - med ROUNDS vanilla-OST plus varje album du
  äger. Välj exakt vilka låtar som spelas i dina matcher; allt låter
  vanilla tills du ändrar något.
- Två album av Sid i shoppens MUSIC-sektion: Another Round (7 spår,
  Metal / Phonk, 1g) och Clavar la Bala (12 spår, Flamenco Metal, 1,000g).
  Fäll ut ett album för att provlyssna på valfri låt i 30 sekunder innan
  du köper.
- Betygsätt låtar med 0-5 stjärnor direkt i låtlistan. Dina betyg är
  privata; communityns snittbetyg uppdateras med fördröjning.
- Musikartister tjänar 50% av albumförsäljningen och kan ge bort kopior.
  Nya inställningar: menymusik (standard / din spellista / tystnad) och en
  valfri "Now Playing"-rad.

## DANSERNA HAR FÅTT BEN (TYP)

- Sex nya danser i shoppen: Jumping Jacks, The Shimmy, Disco Fever, The
  Helicopter, The Robot och The Floss - och varje dans rör nu hela
  kroppen: hopp, lutningar, shimmys och höftgung, inte bara armarna.

## ALLT FRÅN FÖRRA OMGÅNGEN

- Snabbchatten är ett hjul (håll Q), dansemotes har ett eget hjul (håll
  E), Silence X syns faktiskt nu, vadslagningen låses när den ska, läkning
  som syns, och en hög med mindre fixar.
$rn1400sv$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

-- Verification: expect 5 rows.
SELECT language_code, source, LENGTH(body) AS body_len FROM release_notes_i18n WHERE tag = 'v1.40.0' ORDER BY language_code;

COMMIT;
