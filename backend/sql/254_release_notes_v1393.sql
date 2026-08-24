-- 254: v1.39.3 release notes, all five locales.
-- The admin POST endpoint is an idempotent upsert into release_notes_i18n;
-- this migration performs the identical write through the migration channel
-- because the VM seat's AdminSecret still does not verify (403, learning
-- #406/#421). en is the human source (the GitHub release body); es/ru/uk/sv
-- are machine translations reviewed against the in-game catalogue
-- terminology. Shape identical to migration 250.

BEGIN;

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.39.3', 'en', '', $rn1393en$# v1.39.3

The Info library gets search, clickable cross-references and a community research paper; background mute becomes opt-in; the stream rotates the night-pack skins during card picks.

## Info library

- **Search** — a box above the topic list filters articles by title and full text, live, in every language.
- **Clickable cross-references** — the blue article names inside a page now open that article when clicked.
- **New article: "Damage types & buffs", by Spirit** — his complete research on which damage triggers Scavenger, Brawler, Taste of Blood, lifesteal and Refresh: the full damage-interaction table, the RefreshValid model, the 0.35-second window and the damage thresholds. Community research, fully credited.
- The "How stats are tracked" button left Settings — the same content is the library's 'How stats are tracked' article.

## Settings

- "Mute audio when tabbed out" now defaults OFF (bug 267) and has its own toggle in Settings › Performance. Existing installs flip once automatically; turn it back on if you liked it.

## Stream

- The broadcast seat rotates only the dark night-pack map skins for now, and swaps them during the card pick phase instead of mid-battle. Normal spectators keep their own equipped skins and Shift cycling.
$rn1393en$, 'human', NULL)
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.39.3', 'es', '', $rn1393es$# v1.39.3

La biblioteca de información recibe búsqueda, referencias cruzadas clicables y un artículo de investigación de la comunidad; el silencio en segundo plano pasa a ser opcional; el stream rota las skins del pack nocturno durante la elección de cartas.

## Biblioteca de información

- **Búsqueda** — un cuadro sobre la lista de temas filtra los artículos por título y texto completo, en vivo, en todos los idiomas.
- **Referencias cruzadas clicables** — los nombres de artículos en azul dentro de una página ahora abren ese artículo al hacer clic.
- **Nuevo artículo: "Damage types & buffs", por Spirit** — su investigación completa sobre qué daño activa Scavenger, Brawler, Taste of Blood, el robo de vida y Refresh: la tabla completa de interacciones de daño, el modelo RefreshValid, la ventana de 0.35 segundos y los umbrales de daño. Investigación de la comunidad, con crédito completo.
- El botón "Cómo se registran las estadísticas" salió de Ajustes — el mismo contenido es el artículo correspondiente de la biblioteca.

## Ajustes

- "Silenciar el audio al cambiar de ventana" ahora está DESACTIVADO por defecto (bug 267) y tiene su propio interruptor en Ajustes › Rendimiento. Las instalaciones existentes cambian una sola vez automáticamente; vuelve a activarlo si te gustaba.

## Stream

- El asiento de transmisión rota por ahora solo las skins oscuras del pack nocturno, y las cambia durante la fase de elección de cartas en lugar de en plena batalla. Los espectadores normales conservan sus propias skins equipadas y el ciclo con Shift.
$rn1393es$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.39.3', 'ru', '', $rn1393ru$# v1.39.3

Библиотека информации получает поиск, кликабельные перекрёстные ссылки и исследовательскую статью от сообщества; приглушение звука в фоне становится опциональным; стрим меняет скины ночного набора во время выбора карт.

## Библиотека информации

- **Поиск** — поле над списком тем фильтрует статьи по названию и полному тексту, мгновенно, на любом языке.
- **Кликабельные перекрёстные ссылки** — синие названия статей внутри страницы теперь открывают эту статью по клику.
- **Новая статья: "Damage types & buffs" от Spirit** — его полное исследование о том, какой урон активирует Scavenger, Brawler, Taste of Blood, кражу жизни и Refresh: полная таблица взаимодействий урона, модель RefreshValid, окно 0.35 секунды и пороги урона. Исследование сообщества, с полным указанием авторства.
- Кнопка "Как отслеживается статистика" убрана из настроек — тот же материал есть в библиотеке в виде одноимённой статьи.

## Настройки

- "Приглушать звук в фоне" теперь по умолчанию ВЫКЛЮЧЕНО (баг 267) и имеет собственный переключатель в Настройки › Производительность. Существующие установки переключаются один раз автоматически; включите обратно, если вам нравилось.

## Стрим

- Место трансляции пока чередует только тёмные скины ночного набора и меняет их во время фазы выбора карт, а не посреди боя. Обычные зрители сохраняют свои надетые скины и переключение по Shift.
$rn1393ru$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.39.3', 'uk', '', $rn1393uk$# v1.39.3

Бібліотека інформації отримує пошук, клікабельні перехресні посилання та дослідницьку статтю від спільноти; приглушення звуку у фоні стає опціональним; стрім змінює скіни нічного набору під час вибору карт.

## Бібліотека інформації

- **Пошук** — поле над списком тем фільтрує статті за назвою та повним текстом, миттєво, будь-якою мовою.
- **Клікабельні перехресні посилання** — сині назви статей усередині сторінки тепер відкривають цю статтю після кліку.
- **Нова стаття: "Damage types & buffs" від Spirit** — його повне дослідження про те, який урон активує Scavenger, Brawler, Taste of Blood, крадіжку життя та Refresh: повна таблиця взаємодій урону, модель RefreshValid, вікно 0.35 секунди та пороги урону. Дослідження спільноти, з повним зазначенням авторства.
- Кнопку "Як відстежується статистика" прибрано з налаштувань — той самий матеріал є в бібліотеці як однойменна стаття.

## Налаштування

- "Приглушати звук у фоні" тепер типово ВИМКНЕНО (баг 267) і має власний перемикач у Налаштування › Продуктивність. Наявні встановлення перемикаються один раз автоматично; увімкніть знову, якщо вам подобалося.

## Стрім

- Місце трансляції поки чергує лише темні скіни нічного набору та змінює їх під час фази вибору карт, а не посеред бою. Звичайні глядачі зберігають свої одягнені скіни та перемикання через Shift.
$rn1393uk$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.39.3', 'sv', '', $rn1393sv$# v1.39.3

Infobiblioteket får sökning, klickbara korsreferenser och en forskningsartikel från communityn; bakgrundsljuddämpningen blir valfri; strömmen roterar nattpaketets skins under kortvalet.

## Infobiblioteket

- **Sökning** — en ruta ovanför ämneslistan filtrerar artiklar efter titel och hela texten, direkt, på alla språk.
- **Klickbara korsreferenser** — de blå artikelnamnen inuti en sida öppnar nu den artikeln vid klick.
- **Ny artikel: "Damage types & buffs", av Spirit** — hans kompletta forskning om vilken skada som utlöser Scavenger, Brawler, Taste of Blood, livsstöld och Refresh: hela tabellen över skadeinteraktioner, RefreshValid-modellen, 0.35-sekundersfönstret och skadetrösklarna. Communityforskning, med fullt erkännande.
- Knappen "Hur statistik spåras" togs bort från Inställningar — samma innehåll är bibliotekets artikel med samma namn.

## Inställningar

- "Dämpa ljudet när du byter fönster" är nu AV som standard (bugg 267) och har en egen växel i Inställningar › Prestanda. Befintliga installationer växlar en gång automatiskt; slå på igen om du gillade det.

## Ström

- Sändningssätet roterar tills vidare bara nattpaketets mörka kartskins, och byter dem under kortvalsfasen i stället för mitt i striden. Vanliga åskådare behåller sina egna utrustade skins och Shift-växlingen.
$rn1393sv$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

-- Verification: expect 5 rows.
SELECT language_code, source, LENGTH(body) AS body_len FROM release_notes_i18n WHERE tag = 'v1.39.3' ORDER BY language_code;

COMMIT;
