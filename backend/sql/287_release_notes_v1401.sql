-- 287: v1.40.1 release notes, all five locales.
-- The admin POST endpoint is an idempotent upsert into release_notes_i18n;
-- this migration performs the identical write through the migration channel
-- because the VM seat's tooling cannot sign the admin HMAC (learning #443 -
-- the tools read ADMIN_HMAC_SECRET from the environment, never set here).
-- en is the source; es/ru/uk/sv are machine translations matched to the
-- in-game catalogue terminology (same pipeline as 250/262/283).

BEGIN;

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.40.1', 'en', '', $rn1401en$# v1.40.1

## MUSIC: PREPARATION AT THE MAIN MENU

- Downloaded tracks are now decoded only inside a click at the main menu (a
  Music-tab control such as Prepare or a track's Play, or the Shop's Preview),
  one track per click - v1.40.0 could decode several just-downloaded tracks
  together around the first card pick, which was the hitch some of you felt
  there. The Music tab's Prepare button shows what is still pending. With Loop
  on (the default), a track that ends before the next one is prepared repeats
  instead of going quiet, and a failed decode is retried by a click, never on
  its own.

## CLAVAR LA BALA: 14 TRACKS

- "Principio de Ronda" and "Nube Tóxica" join the album as tracks 13 and 14.
  The existing tracks and your ratings are unchanged.

## NETWORK DIAGNOSTICS

- The 1v1 match report now carries a compact set of network facts from the
  reporting seat only (frame hitches, Photon resend and queue counts, and
  tags that mark gaps a still opponent or a Phoenix charge can explain).
  Never public, never part of the match signature. The corner HUD shows a
  one-way replica-age estimate and recent frame and resend facts.

## QUEUE

- The 1v1 queue poll now requires your own Steam session; if it is refused
  for 30 seconds straight, polling stops with a notice and the server clears
  your seat shortly. Match-making
  writes are reciprocal: the room is issued only to a pair whose rows still
  name each other, and declining a pre-room match frees the partner (after a leave
  is recorded, the partner's next accepted poll frees them).
$rn1401en$, 'human', NULL)
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.40.1', 'es', '', $rn1401es$# v1.40.1

## MÚSICA: PREPARACIÓN EN EL MENÚ PRINCIPAL

- Los temas descargados ahora se decodifican solo con un clic en el menú
  principal (un control de la pestaña MUSIC como "Prepare music" o el Play de un
  tema, o la Vista previa de la tienda), un tema por clic - la 1.40.0 podía
  decodificar varios temas recién descargados a la vez en torno a la primera
  elección de cartas, y ese era el tirón que algunos notasteis ahí. El botón
  "Prepare music" de la pestaña MUSIC (los botones del juego están en
  inglés) muestra lo que queda pendiente. Con el bucle
  activado (por defecto), un tema que termina antes de que el siguiente esté
  preparado se repite en vez de quedar en silencio, y una decodificación
  fallida se reintenta con un clic, nunca por sí sola.

## CLAVAR LA BALA: 14 TEMAS

- "Principio de Ronda" y "Nube Tóxica" se unen al álbum como temas 13 y 14.
  Los temas existentes y tus valoraciones no cambian.

## DIAGNÓSTICO DE RED

- El informe de partida 1v1 ahora lleva un conjunto compacto de datos de red
  solo del asiento que informa (tirones de fotogramas, reenvíos y colas de
  Photon, y etiquetas que marcan los huecos que un rival quieto o una carga
  de Phoenix pueden explicar). Nunca son públicos ni forman parte de la firma
  de la partida. El HUD de la esquina muestra una estimación de retraso de
  réplica de ida y datos recientes de fotogramas y reenvíos.

## COLA

- La consulta de la cola 1v1 ahora requiere tu propia sesión de Steam; si se
  rechaza durante 30 segundos seguidos, el sondeo se detiene con un aviso y
  el servidor libera tu puesto en breve. Las
  escrituras del emparejamiento son recíprocas: la sala solo se asigna a una
  pareja cuyas filas aún se nombran mutuamente, y rechazar una partida sin sala libera
  al compañero (tras registrarse una salida, la siguiente consulta aceptada
  del compañero lo libera).
$rn1401es$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.40.1', 'ru', '', $rn1401ru$# v1.40.1

## МУЗЫКА: ПОДГОТОВКА В ГЛАВНОМ МЕНЮ

- Скачанные треки теперь декодируются только по клику в главном меню
  (элемент вкладки MUSIC, например "Prepare music" или Play трека, либо
  предпрослушивание в магазине), по одному треку за клик - в 1.40.0 несколько
  только что скачанных треков могли декодироваться вместе около первого
  выбора карт, и это был тот самый рывок, который некоторые из вас там
  замечали. Кнопка "Prepare music" на вкладке MUSIC (кнопки в игре на
  английском) показывает, что ещё не
  готово. При включённом повторе (по умолчанию) трек, закончившийся раньше,
  чем подготовлен следующий, повторяется вместо тишины, а неудачное
  декодирование повторяется по клику, никогда само по себе.

## CLAVAR LA BALA: 14 ТРЕКОВ

- "Principio de Ronda" и "Nube Tóxica" добавлены в альбом как треки 13 и 14.
  Существующие треки и ваши оценки не изменились.

## СЕТЕВАЯ ДИАГНОСТИКА

- Отчёт о матче 1v1 теперь несёт компактный набор сетевых данных только с
  сообщающего места (провалы кадров, повторные отправки и очереди Photon,
  а также метки, отмечающие паузы, которые можно объяснить неподвижным
  соперником или зарядом Phoenix). Они никогда не публичны и не входят в
  подпись матча. HUD в углу показывает оценку задержки реплики в одну
  сторону и недавние данные о кадрах и повторах.

## ОЧЕРЕДЬ

- Опрос очереди 1v1 теперь требует вашу собственную сессию Steam; если она
  отклоняется 30 секунд подряд, опрос останавливается с уведомлением, и
  сервер вскоре освобождает ваше место.
  Записи подбора взаимны: комната выдаётся только паре, чьи записи всё ещё
  указывают друг на друга, а отказ от матча до создания комнаты освобождает
  партнёра (после записи выхода партнёра освобождает его следующий принятый
  опрос).
$rn1401ru$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.40.1', 'uk', '', $rn1401uk$# v1.40.1

## МУЗИКА: ПІДГОТОВКА В ГОЛОВНОМУ МЕНЮ

- Завантажені треки тепер декодуються лише за кліком у головному меню
  (елемент вкладки MUSIC, наприклад "Prepare music" або Play треку, чи
  попереднє прослуховування в магазині), по одному треку за клік - у 1.40.0
  кілька щойно завантажених треків могли декодуватися разом близько першого
  вибору карт, і саме це був той ривок, який дехто з вас там помічав. Кнопка
  "Prepare music" на вкладці MUSIC (кнопки у грі англійською) показує, що ще
  не готово. За ввімкненого
  повтору (типово) трек, який закінчився раніше, ніж підготовлено наступний,
  повторюється замість тиші, а невдале декодування повторюється за кліком,
  ніколи само по собі.

## CLAVAR LA BALA: 14 ТРЕКІВ

- "Principio de Ronda" та "Nube Tóxica" додано до альбому як треки 13 і 14.
  Наявні треки та ваші оцінки не змінилися.

## МЕРЕЖЕВА ДІАГНОСТИКА

- Звіт про матч 1v1 тепер несе компактний набір мережевих даних лише з
  місця, що звітує (провали кадрів, повторні надсилання та черги Photon, а
  також мітки, що позначають паузи, які можна пояснити нерухомим суперником
  чи зарядом Phoenix). Вони ніколи не публічні й не входять до підпису
  матчу. HUD у кутку показує оцінку затримки репліки в один бік і недавні
  дані про кадри та повтори.

## ЧЕРГА

- Опитування черги 1v1 тепер вимагає вашу власну сесію Steam; якщо її
  відхиляють 30 секунд поспіль, опитування зупиняється зі сповіщенням, і
  сервер невдовзі звільняє ваше місце. Записи
  підбору взаємні: кімнату видають лише парі, чиї записи досі вказують одна
  на одну, а відмова від матчу до створення кімнати звільняє партнера (після
  запису виходу партнера звільняє його наступне прийняте опитування).
$rn1401uk$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.40.1', 'sv', '', $rn1401sv$# v1.40.1

## MUSIK: FÖRBEREDELSE I HUVUDMENYN

- Nedladdade spår avkodas nu bara vid ett klick i huvudmenyn (en kontroll på
  MUSIC-fliken som "Prepare music" eller ett spårs Play, eller butikens
  förhandsvisning), ett spår per klick - 1.40.0 kunde avkoda flera nyss
  nedladdade spår tillsammans kring det första kortvalet, vilket var hacket
  några av er kände där. MUSIC-flikens "Prepare music"-knapp (spelets knappar är
  på engelska) visar vad som återstår.
  Med Loop på (standard) upprepas ett spår som tar slut innan nästa är
  förberett i stället för att tystna, och en misslyckad avkodning görs om vid
  ett klick, aldrig på egen hand.

## CLAVAR LA BALA: 14 SPÅR

- "Principio de Ronda" och "Nube Tóxica" läggs till i albumet som spår 13
  och 14. Befintliga spår och dina betyg är oförändrade.

## NÄTVERKSDIAGNOSTIK

- 1v1-matchrapporten bär nu en kompakt uppsättning nätverksfakta enbart från
  den rapporterande platsen (bildhack, Photons omsändningar och köer, samt
  markeringar för luckor som en stillastående motståndare eller en
  Phoenix-laddning kan förklara). De är aldrig offentliga och ingår aldrig i
  matchsignaturen. Hörn-HUD:en visar en uppskattning av replikfördröjningen
  åt ett håll och aktuella bild- och omsändningsfakta.

## KÖ

- 1v1-köns avfrågning kräver nu din egen Steam-session; nekas den i 30
  sekunder i sträck stannar avfrågningen med ett meddelande och servern
  frigör din plats inom kort. Matchningens
  skrivningar är ömsesidiga: rummet ges bara till ett par vars rader
  fortfarande pekar på varandra, och att avböja en match innan rummet finns frigör partnern (när ett
  lämnande är registrerat frigör partnerns nästa godkända avfrågning dem).
$rn1401sv$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

-- Enforcing post-check (Codex r18 finding 5 / r19 finding 1): EXACTLY the five
-- intended rows — language, md5 of the exact body literal above, source,
-- translated_by, empty title — and no surplus row under the tag. A wrong-language
-- body, a truncated translation, a mis-attributed source or a sixth locale aborts
-- the transaction. The md5 values are computed from this file's own literals.
DO $$
DECLARE
    v_bad   INT;
    v_total INT;
BEGIN
    SELECT COUNT(*) INTO v_total FROM release_notes_i18n WHERE tag = 'v1.40.1';
    IF v_total <> 5 THEN
        RAISE EXCEPTION 'post-check FAILED: % rows under tag v1.40.1 (want exactly 5)', v_total;
    END IF;
    WITH expected(language_code, body_md5, source, translated_by) AS (VALUES
        ('en', '1a3a48f2f3eec3ba237bbcf3f130c738', 'human', NULL),
        ('es', '893d7c619c1ad76e836f4e68a7d42dbf', 'machine', 'claude-mt'),
        ('ru', 'f75dfe19ea66fe5fbe4ef5a03e0d643e', 'machine', 'claude-mt'),
        ('uk', 'f90f87c1e97d33a4f391c392a85dbe39', 'machine', 'claude-mt'),
        ('sv', 'd4bda9367d02fd74e51f2239892e3b3e', 'machine', 'claude-mt')
    )
    SELECT COUNT(*) INTO v_bad
      FROM expected e
      LEFT JOIN release_notes_i18n r
        ON r.tag = 'v1.40.1' AND r.language_code = e.language_code
     WHERE r.language_code IS NULL
        OR md5(r.body) <> e.body_md5
        OR r.source IS DISTINCT FROM e.source
        OR r.translated_by IS DISTINCT FROM e.translated_by
        OR r.title IS DISTINCT FROM '';
    IF v_bad <> 0 THEN
        RAISE EXCEPTION 'post-check FAILED: % of the 5 expected v1.40.1 release-note rows are missing or differ (body md5 / source / translated_by / title)', v_bad;
    END IF;
    RAISE NOTICE 'post-check OK: exactly the 5 intended v1.40.1 release-note rows';
END $$;

-- Display: expect 5 rows.
SELECT language_code, source, LENGTH(body) AS body_len FROM release_notes_i18n WHERE tag = 'v1.40.1' ORDER BY language_code;

COMMIT;
