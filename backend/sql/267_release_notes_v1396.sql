-- 267: v1.39.6 release notes, all five locales.
-- Same channel as migrations 250/254/262: the admin POST endpoint's idempotent
-- upsert into release_notes_i18n, performed through the migration channel
-- (the VM seat's tools read ADMIN_HMAC_SECRET from env, which this seat does
-- not set — learning #443). en is the human source; es/ru/uk/sv are machine
-- translations reviewed against the in-game catalogue terminology.

BEGIN;

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.39.6', 'en', '', $rn1396en$# v1.39.6

## Your menu is yours again

- While the F5 menu is open, clicks and keys stay OUT of the match: no more firing your gun through a menu button, no more Space readying you up or confirming a card behind the menu, no more surprise charged shot when the menu closes.
- Escape with the menu open only closes the menu — it no longer opens the game's pause menu behind it, and no longer cancels a ranked match that is mid-connect.
- The mod's main-menu button comes back after visiting Sandbox.

## Tournaments

- **The Forfeit button is here.** It has its own row on your My Match panel while your match is in its ready phase, with a two-click confirm.
- The Tournaments tab now opens on the sub-tab that holds YOUR live match (once the mod's regular match check has spotted it), so your match panel is right there.

## Leaving a match

- The escape menu now has a **LEAVE MATCH** row during competitive play — two-click confirm, with per-mode text that says exactly what leaving costs before you do it.

## New players

- Until your first ranked game, the Search Ranked button glows through a rainbow cycle with a callout pointing at it.

## Info library

- New "Controls & keys" article with a keyboard map, plus nine new charts and diagrams across seven articles: DoT ticks vs the 0.3s block window, the rank ladder, rating confidence, the XP curve, gold sources, best-of-3 flow, and FFA scoring.

## Health bar

- Spectators now see the red damage-over-time drain segment, and everyone gets a NEW blue "recently healed" segment — lifesteal and regeneration are finally visible as health flowing back in.

## Cosmetics

- Five community faces: The Mobsta, Well Wraped Hat, Phoneix Gaze (ANIMATED), Smart Specs, The Cryptid.

## Fixes and moderation

- Silence's red X (and the stun triangles) render again.
- Chat moderation now reaches across platforms: mutes follow a person over in-game/Discord/Twitch/YouTube, deleting a message removes its mirrored copies, and moderators can lock the bridged chat during an incident (you see an explicit notice instead of messages silently vanishing).
$rn1396en$, 'human', NULL)
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.39.6', 'es', '', $rn1396es$# v1.39.6

## Tu menú vuelve a ser tuyo

- Mientras el menú F5 está abierto, los clics y las teclas se quedan FUERA de la partida: se acabó disparar tu arma a través de un botón del menú, que Espacio te marque como listo o confirme una carta detrás del menú, o el disparo cargado sorpresa al cerrar el menú.
- Escape con el menú abierto solo cierra el menú — ya no abre el menú de pausa del juego detrás, y ya no cancela una partida clasificatoria que está conectándose.
- El botón del mod en el menú principal vuelve a aparecer después de visitar Sandbox.

## Torneos

- **El botón de Rendirse (Forfeit) ya está aquí.** Tiene su propia fila en tu panel My Match mientras tu partida está en su fase de preparación, con confirmación de dos clics.
- La pestaña de Torneos ahora se abre en la sub-pestaña donde está TU partida activa (en cuanto la comprobación periódica del mod la detecta), así tu panel queda a la vista.

## Abandonar una partida

- El menú de escape ahora tiene una fila **LEAVE MATCH** durante el juego competitivo — confirmación de dos clics, con texto por modo que dice exactamente qué cuesta abandonar antes de hacerlo.

## Jugadores nuevos

- Hasta tu primera partida clasificatoria, el botón Search Ranked brilla con un ciclo arcoíris y un aviso flotante que lo señala.

## Biblioteca de información

- Nuevo artículo "Controls & keys" con un mapa del teclado, más nueve gráficos y diagramas nuevos en siete artículos: los ticks de daño continuo frente a la ventana de bloqueo de 0.3s, la escalera de rangos, la confianza de la puntuación, la curva de XP, las fuentes de oro, el flujo de mejor-de-3 y la puntuación de FFA.

## Barra de vida

- Los espectadores ahora ven el segmento rojo de drenaje por daño continuo, y todos reciben un NUEVO segmento azul de "curación reciente" — el robo de vida y la regeneración por fin se ven como vida que vuelve.

## Cosméticos

- Cinco caras de la comunidad: The Mobsta, Well Wraped Hat, Phoneix Gaze (ANIMADA), Smart Specs, The Cryptid.

## Correcciones y moderación

- La X roja de Silence (y los triángulos de aturdimiento) vuelven a mostrarse.
- La moderación del chat ahora cruza plataformas: los silenciamientos siguen a la persona por el juego/Discord/Twitch/YouTube, borrar un mensaje elimina sus copias espejadas, y los moderadores pueden bloquear el chat puenteado durante un incidente (ves un aviso explícito en lugar de mensajes que desaparecen en silencio).
$rn1396es$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.39.6', 'ru', '', $rn1396ru$# v1.39.6

## Меню снова ваше

- Пока меню F5 открыто, клики и клавиши НЕ попадают в матч: больше никакой стрельбы сквозь кнопку меню, Пробел не отмечает готовность и не подтверждает карту за меню, и никакого внезапного заряженного выстрела при закрытии меню.
- Escape при открытом меню только закрывает меню — он больше не открывает игровое меню паузы позади и не отменяет рейтинговый матч во время подключения.
- Кнопка мода в главном меню снова появляется после посещения Sandbox.

## Турниры

- **Кнопка сдачи (Forfeit) на месте.** У неё своя строка на панели My Match, пока ваш матч в фазе готовности, с подтверждением в два клика.
- Вкладка турниров теперь открывается на той под-вкладке, где идёт ВАШ матч (как только регулярная проверка мода его заметит), так что ваша панель сразу под рукой.

## Выход из матча

- В меню Escape во время соревновательной игры появилась строка **LEAVE MATCH** — подтверждение в два клика, с текстом для каждого режима, который заранее говорит, чего стоит выход.

## Новым игрокам

- До вашей первой рейтинговой игры кнопка Search Ranked переливается радугой, и на неё указывает плавающая подсказка.

## Библиотека информации

- Новая статья "Controls & keys" с картой клавиатуры, плюс девять новых графиков и диаграмм в семи статьях: тики периодического урона против окна блока 0.3с, лестница рангов, уверенность рейтинга, кривая опыта, источники золота, схема best-of-3 и подсчёт очков FFA.

## Полоса здоровья

- Зрители теперь видят красный сегмент утекающего периодического урона, и у всех появился НОВЫЙ синий сегмент "недавнее лечение" — вампиризм и регенерация наконец видны как возвращающееся здоровье.

## Косметика

- Пять лиц от сообщества: The Mobsta, Well Wraped Hat, Phoneix Gaze (АНИМИРОВАННОЕ), Smart Specs, The Cryptid.

## Исправления и модерация

- Красный X Silence (и треугольники оглушения) снова отображаются.
- Модерация чата теперь работает между платформами: мут следует за человеком в игре/Discord/Twitch/YouTube, удаление сообщения убирает его зеркальные копии, а модераторы могут заблокировать общий чат во время инцидента (вы видите явное уведомление, а не молча исчезающие сообщения).
$rn1396ru$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.39.6', 'uk', '', $rn1396uk$# v1.39.6

## Меню знову ваше

- Поки меню F5 відкрите, кліки та клавіші НЕ потрапляють у матч: більше жодної стрільби крізь кнопку меню, Пробіл не позначає готовність і не підтверджує карту за меню, і жодного раптового зарядженого пострілу при закритті меню.
- Escape з відкритим меню лише закриває меню — він більше не відкриває ігрове меню паузи позаду і не скасовує рейтинговий матч під час підключення.
- Кнопка мода в головному меню знову з'являється після відвідин Sandbox.

## Турніри

- **Кнопка здачі (Forfeit) на місці.** У неї свій рядок на панелі My Match, поки ваш матч у фазі готовності, з підтвердженням у два кліки.
- Вкладка турнірів тепер відкривається на тій під-вкладці, де йде ВАШ матч (щойно регулярна перевірка мода його помітить), тож ваша панель одразу поруч.

## Вихід із матчу

- У меню Escape під час змагальної гри з'явився рядок **LEAVE MATCH** — підтвердження у два кліки, з текстом для кожного режиму, який заздалегідь каже, чого коштує вихід.

## Новим гравцям

- До вашої першої рейтингової гри кнопка Search Ranked переливається веселкою, і на неї вказує плаваюча підказка.

## Бібліотека інформації

- Нова стаття "Controls & keys" з картою клавіатури, плюс дев'ять нових графіків і діаграм у семи статтях: тіки періодичної шкоди проти вікна блоку 0.3с, драбина рангів, впевненість рейтингу, крива досвіду, джерела золота, схема best-of-3 і підрахунок очок FFA.

## Смуга здоров'я

- Глядачі тепер бачать червоний сегмент витікання періодичної шкоди, і всі отримали НОВИЙ синій сегмент "нещодавнє лікування" — вампіризм і регенерація нарешті видно як здоров'я, що повертається.

## Косметика

- П'ять облич від спільноти: The Mobsta, Well Wraped Hat, Phoneix Gaze (АНІМОВАНЕ), Smart Specs, The Cryptid.

## Виправлення та модерація

- Червоний X Silence (і трикутники оглушення) знову відображаються.
- Модерація чату тепер працює між платформами: мут іде за людиною в грі/Discord/Twitch/YouTube, видалення повідомлення прибирає його дзеркальні копії, а модератори можуть заблокувати спільний чат під час інциденту (ви бачите явне повідомлення, а не мовчки зниклі рядки).
$rn1396uk$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.39.6', 'sv', '', $rn1396sv$# v1.39.6

## Menyn är din igen

- Medan F5-menyn är öppen stannar klick och tangenter UTANFÖR matchen: inget mer vapenavfyrande genom en menyknapp, inget Mellanslag som gör dig redo eller bekräftar ett kort bakom menyn, och inget överraskande laddat skott när menyn stängs.
- Escape med menyn öppen stänger bara menyn — den öppnar inte längre spelets pausmeny bakom, och avbryter inte längre en rankad match som håller på att ansluta.
- Moddens knapp i huvudmenyn kommer tillbaka efter ett besök i Sandbox.

## Turneringar

- **Forfeit-knappen är här.** Den har sin egen rad på din My Match-panel medan din match är i sin redo-fas, med bekräftelse i två klick.
- Turneringsfliken öppnas nu på den underflik som håller DIN aktiva match (så snart moddens regelbundna matchkoll har sett den), så din panel finns direkt där.

## Att lämna en match

- Escape-menyn har nu en **LEAVE MATCH**-rad under tävlingsspel — bekräftelse i två klick, med text per läge som säger exakt vad det kostar att lämna innan du gör det.

## Nya spelare

- Fram till din första rankade match lyser Search Ranked-knappen i en regnbågscykel med en svävande hänvisning som pekar på den.

## Infobiblioteket

- Ny artikel "Controls & keys" med en tangentbordskarta, plus nio nya diagram i sju artiklar: DoT-tick mot blockfönstret på 0.3s, rangstegen, betygssäkerhet, XP-kurvan, guldkällor, bäst-av-3-flödet och FFA-poängräkning.

## Hälsomätaren

- Åskådare ser nu det röda segmentet när skada-över-tid dränerar en spelare, och alla får ett NYTT blått "nyligen läkt"-segment — livsstöld och regeneration syns äntligen som hälsa på väg tillbaka.

## Kosmetika

- Fem communityansikten: The Mobsta, Well Wraped Hat, Phoneix Gaze (ANIMERAT), Smart Specs, The Cryptid.

## Fixar och moderering

- Silences röda X (och stun-trianglarna) visas igen.
- Chattmoderering når nu över plattformar: en mute följer personen över spelet/Discord/Twitch/YouTube, borttagning av ett meddelande tar bort dess speglade kopior, och moderatorer kan låsa den bryggade chatten under en incident (du ser ett tydligt meddelande i stället för att rader tyst försvinner).
$rn1396sv$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

COMMIT;
