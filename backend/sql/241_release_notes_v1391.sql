-- 241: v1.39.1 release notes, all five locales.
-- The admin POST endpoint is an idempotent upsert into release_notes_i18n;
-- this migration performs the identical write through the migration channel
-- because the VM seat's AdminSecret does not currently verify (403) - see
-- learning #406. en is the human source; es/ru/uk/sv are machine
-- translations reviewed against the in-game catalogue terminology.

BEGIN;

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.39.1', 'en', '', $rn1391en$# v1.39.1

The biggest patch since 1.39.0 shipped: tournament quality-of-life, the FFA
early-leave rule going live, every map skin background fixed, background
audio muting, and a long list of bug-report fixes.

## Tournaments

- **Async deadline check-ins.** On the last day of your async match's 7-day
  window, the bot DMs you and your opponent: have you made contact, and do
  you plan to play today? Three buttons — **Yes** (extends the deadline 24
  hours; each player can extend once per opponent per tournament), **I
  reached out — no response / they quit**, and **Not yet — still
  coordinating**. The buttons keep working across bot restarts.
- **One willing player is no longer punished for the other's silence.** If
  an async match times out and only one of you had answered the check-in,
  that player now advances with a normal forfeit win instead of BOTH
  players being eliminated. (The losers-bracket double-DQ from this week
  was also repaired by hand — the willing player advances with a fresh
  deadline.)
- **Sync and async histories are separate now** — the Recent Tournaments
  popup shows only the sub-tab's own kind, and your placements line moved
  into that popup where it belongs.

## FFA

- **Leaving before the field has scored two points no longer costs Elo —
  and the rule is LIVE as of this release.** The server half shipped
  earlier; your client now reports the leave-time score it needs. Games
  that broke at the start stop charging (or paying) anyone. Two rounds of
  historical corrections repaired every affected past game.
- **The match-point banner no longer renders styled names HUGE** — names
  keep their color and bold, but size tags are stripped.
- **The game-over freeze is fixed**: after a player left mid-session, every
  other seat could freeze on the VICTORY screen (the rematch popup crashed
  looking up an empty team's color).
- **Ratings**: a big upset now counts even when the upset player finished
  far from you in the standings (upset inclusion beyond the adjacency
  window — server-side, already live).

## Map skins

- **Every custom map skin renders its own designed background again.** All
  23 were collapsing toward the same pinkish red. Also fixed in the same
  pass: skins losing their backdrop seconds into a round, mid-slide
  recolors (the stall that could leave players off-screen), "disable map
  lighting" never visually sticking, stale colors after switching back to a
  vanilla skin, and **unequipping your last map color now works without a
  restart**. The neutral skins (Monochrome, Platinum) read neutral again.

## Sound

- **Game audio now mutes while you're tabbed out of an online match**
  (deterministic, exact-volume restore on refocus; the match-found sound in
  queue still reaches you). Config: `MuteAudioInBackground`, default on.

## 2v2 and queues

- **Disconnect + re-queue no longer creates duplicate 2v2 series.** The
  four of you re-queuing within 30 minutes re-lock onto the original series
  with the score kept; stray empty duplicates are absorbed and wagers
  reconciled (server-side, already live).
- **"Leave All Queues" actually clears 2v2/1v2 states** — a disconnected
  player no longer stays "in a match" with no way out.

## Spectating and streaming

- Spectators see **both teams' cards in 2v2**, and Refresh block resets now
  render on spectator seats.
- The spectator camera keeps every live fighter in frame, and a rematch no
  longer spams errors from a stale crown.
- The broadcast switches to the better game when one is clearly bigger, and
  stream-ended posts link the exact Twitch/YouTube VODs.

## Chat

- Messages are tagged by source: **[Discord], [Game], [Twitch], [YouTube]**.
- The muted-players header no longer mangles styled names.

## Cosmetics

- **Two new community cosmetics**: Seasonal Spring (animated — 8 frames) and
  Nuclear glasses.

## Other fixes

- The lobby browser shows the whole roster of an open lobby ("+N more"
  works now), and four text cells clip instead of silently dropping text —
  the "(left)" disconnect marker can't vanish anymore.
- Leaderboard profile stat lines reorganized (1v1 matches the other modes'
  shape); "Top Cards" is now "Most Used Cards" in every language; async
  tournament wording clarified ("first to 2 games" in a BO3).
- 44 newly added interface strings translated in Spanish, Russian,
  Ukrainian, and Swedish.
- Toxic Cloud sometimes not appearing for the player it hit (bug 260) is
  still under investigation — this release carries a field diagnostic to
  catch the real mechanism in production.

Thanks for all the bug reports — this patch closes out the entire recent backlog.$rn1391en$, 'human', NULL)
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.39.1', 'es', '', $rn1391es$# v1.39.1

El parche más grande desde que salió 1.39.0: mejoras de calidad de vida en
torneos, la regla de salida temprana de FFA ya en vigor, todos los fondos de
las skins de mapa arreglados, silenciado del audio en segundo plano y una
larga lista de correcciones de reportes de bugs.

## Torneos

- **Avisos de plazo en async.** El último día de la ventana de 7 días de tu
  partida async, el bot les envía un MD a ti y a tu rival: ¿hicieron
  contacto y piensan jugar hoy? Tres botones — **Sí** (extiende el plazo
  24 horas; cada jugador puede extender una vez por rival por torneo),
  **Contacté — sin respuesta / abandonó** y **Todavía no — seguimos
  coordinando**. Los botones siguen funcionando aunque el bot se
  reinicie.
- **Un jugador dispuesto ya no es castigado por el silencio del otro.** Si
  una partida async expira y solo uno de los dos respondió al aviso, ese
  jugador ahora avanza con una victoria normal por rendición del rival, en
  lugar de que AMBOS jugadores queden eliminados. (La doble descalificación
  de esta semana en el cuadro de perdedores también se reparó a mano — el
  jugador dispuesto avanza con un plazo nuevo.)
- **Los historiales de sync y async ahora están separados** — el popup de
  Torneos recientes muestra solo el tipo de su propia sub-pestaña, y tu
  línea de posiciones se movió a ese popup, donde corresponde.

## FFA

- **Salir antes de que el grupo anote dos puntos ya no cuesta Elo — y la
  regla está ACTIVA desde esta versión.** La mitad del servidor salió
  antes; tu cliente ahora reporta el marcador al momento de salir que
  aquella necesita. Los juegos que se rompen al inicio dejan de cobrarle (o
  pagarle) a nadie. Dos rondas de correcciones históricas repararon todos
  los juegos pasados afectados.
- **El banner de punto de partida ya no muestra ENORMES los nombres con
  estilo** — los nombres conservan su color y negrita, pero las etiquetas
  de tamaño se eliminan.
- **El congelamiento del final de partida está arreglado**: después de que
  un jugador se fuera a mitad de sesión, los demás asientos podían quedarse
  congelados en la pantalla de VICTORY (el popup de revancha fallaba al
  buscar el color de un equipo vacío).
- **Rating**: una gran victoria sorpresa (upset) ahora cuenta aunque el
  jugador que la logró terminara lejos de ti en la tabla (inclusión de
  upsets más allá de la ventana de adyacencia — del lado del servidor, ya
  activa).

## Skins de mapa

- **Cada skin de mapa personalizada vuelve a mostrar su propio fondo
  diseñado.** Las 23 estaban colapsando hacia el mismo rojo rosado.
  También arreglado en la misma pasada: skins que perdían su fondo a los
  pocos segundos de empezar la ronda, recoloreos a mitad de transición (el
  atasco que podía dejar jugadores fuera de pantalla), la "luz del mapa"
  desactivada que nunca se aplicaba visualmente, colores obsoletos al
  volver a una skin vanilla, y **desequipar tu último color de mapa ahora
  funciona sin reiniciar**. Las skins neutras (Monochrome, Platinum)
  vuelven a verse neutras.

## Sonido

- **El audio del juego ahora se silencia mientras estás fuera de la ventana
  en una partida en línea** (restauración determinista del volumen exacto
  al volver; el sonido de partida encontrada en cola sigue llegándote).
  Config: `MuteAudioInBackground`, activado por defecto.

## 2v2 y colas

- **Desconectarse y volver a la cola ya no crea series 2v2 duplicadas.** Si
  los cuatro vuelven a la cola en menos de 30 minutos, se reenganchan a la
  serie original con el marcador conservado; los duplicados vacíos sueltos
  se absorben y las apuestas se reconcilian (del lado del servidor, ya
  activo).
- **"Salir de colas" ahora sí limpia los estados de 2v2/1v2** — un jugador
  desconectado ya no se queda "en partida" sin salida.

## Espectadores y streaming

- Los espectadores ven **las cartas de ambos equipos en 2v2**, y los
  reinicios de bloqueo de Refresh ahora se muestran en los asientos de
  espectador.
- La cámara de espectador mantiene en cuadro a todos los luchadores vivos,
  y una revancha ya no genera errores en cadena por una corona obsoleta.
- La transmisión cambia al mejor juego cuando uno es claramente más grande,
  y las publicaciones de fin de stream enlazan los VOD exactos de
  Twitch/YouTube.

## Chat

- Los mensajes se etiquetan por origen: **[Discord], [Game], [Twitch],
  [YouTube]**.
- El encabezado de jugadores silenciados ya no rompe los nombres con
  estilo.

## Cosméticos

- **Dos nuevos cosméticos de la comunidad**: Seasonal Spring (animado — 8
  fotogramas) y Nuclear glasses.

## Otras correcciones

- El navegador de lobbies muestra la lista completa de un lobby abierto (el
  "+N más" ahora funciona), y cuatro celdas de texto se recortan en lugar
  de perder texto en silencio — el marcador de desconexión "(left)" ya no
  puede desaparecer.
- Las líneas de estadísticas del perfil en la clasificación se
  reorganizaron (1v1 sigue la misma forma que los otros modos); "Top
  Cards" ahora es "Cartas más usadas" en todos los idiomas; el texto de
  torneos async se aclaró ("primero a 2 juegos" en un BO3).
- 44 cadenas de interfaz recién añadidas traducidas al español, ruso,
  ucraniano y sueco.
- Que Toxic Cloud a veces no aparezca para el jugador golpeado (bug 260)
  sigue en investigación — esta versión incluye un diagnóstico de campo
  para captar el mecanismo real en producción.

Gracias por todos los reportes de bugs — este parche cierra todos los
reportes pendientes recientes.$rn1391es$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.39.1', 'ru', '', $rn1391ru$# v1.39.1

Самый крупный патч с выхода 1.39.0: удобства для турниров, правило раннего
выхода в FFA теперь в силе, исправлены фоны всех скинов карт, приглушение
звука в фоне и длинный список исправлений по баг-репортам.

## Турниры

- **Проверки перед дедлайном в async.** В последний день 7-дневного окна
  вашего async-матча бот пишет в ЛС вам и вашему сопернику: связались ли
  вы и планируете ли сыграть сегодня? Три кнопки — **Да** (продлевает
  срок на 24 часа; каждый игрок может продлить один раз на соперника за
  турнир), **Я написал — нет ответа / он ушёл** и **Пока нет — ещё
  договариваемся**. Кнопки продолжают работать и после перезапусков
  бота.
- **Готовый играть игрок больше не наказывается за молчание другого.**
  Если время async-матча вышло и на проверку ответил только один из вас,
  этот игрок теперь проходит дальше с обычной победой (соперник считается
  сдавшимся), вместо того чтобы вылетали ОБА игрока. (Двойная
  дисквалификация в нижней сетке на этой неделе тоже исправлена вручную —
  готовый играть игрок проходит дальше с новым сроком.)
- **Истории sync и async теперь разделены** — попап «Недавние турниры»
  показывает только тип своей под-вкладки, а строка с вашими местами
  переехала в этот попап, где ей и место.

## FFA

- **Выход до того, как участники набрали два очка, больше не стоит Elo —
  и правило ДЕЙСТВУЕТ с этого релиза.** Серверная часть вышла раньше;
  теперь ваш клиент передаёт нужный ей счёт на момент выхода. Игры,
  сломавшиеся на старте, перестают списывать (или начислять) кому-либо
  рейтинг. Два раунда исторических корректировок исправили все затронутые
  прошлые игры.
- **Баннер матчбола больше не выводит стилизованные имена ОГРОМНЫМИ** —
  имена сохраняют цвет и жирность, но теги размера вырезаются.
- **Исправлено зависание в конце игры**: после того как игрок выходил
  посреди сессии, все остальные могли зависнуть на экране VICTORY (попап
  реванша падал, пытаясь получить цвет пустой команды).
- **Рейтинг**: крупный апсет теперь учитывается, даже если совершивший его
  игрок финишировал далеко от вас в таблице (учёт апсетов за пределами
  окна соседних мест — на стороне сервера, уже в силе).

## Скины карт

- **Каждый кастомный скин карты снова показывает свой собственный
  задуманный фон.** Все 23 сползали к одному и тому же розовато-красному.
  В том же проходе исправлено: скины, терявшие фон через несколько секунд
  после начала раунда, перекраска посреди перехода (затык, из-за которого
  игроки могли остаться за экраном), выключенный «свет карты», который
  визуально не применялся, устаревшие цвета при возврате на ванильный
  скин, и **снятие последнего цвета карты теперь работает без
  перезапуска**. Нейтральные скины (Monochrome, Platinum) снова выглядят
  нейтрально.

## Звук

- **Звук игры теперь приглушается, пока вы свёрнуты во время
  онлайн-матча** (детерминированное восстановление точной громкости при
  возврате; звук найденного матча в очереди по-прежнему доходит).
  Настройка: `MuteAudioInBackground`, включена по умолчанию.

## 2v2 и очереди

- **Дисконект и повторная очередь больше не создают дубликаты серий
  2v2.** Если вы вчетвером снова встаёте в очередь в течение 30 минут, вы
  возвращаетесь в исходную серию с сохранённым счётом; лишние пустые
  дубликаты поглощаются, а ставки сверяются (на стороне сервера, уже в
  силе).
- **«Выйти из очередей» теперь действительно очищает состояния 2v2/1v2**
  — отключившийся игрок больше не застревает «в матче» без выхода.

## Зрители и стриминг

- Зрители видят **карты обеих команд в 2v2**, а сбросы блока от Refresh
  теперь отображаются на местах зрителей.
- Камера зрителя держит всех живых бойцов в кадре, а реванш больше не
  сыпет ошибками из-за устаревшей короны.
- Трансляция переключается на более значимую игру, когда одна из них явно
  крупнее, а посты об окончании стрима ссылаются на точные VOD на
  Twitch/YouTube.

## Чат

- Сообщения помечаются источником: **[Discord], [Game], [Twitch],
  [YouTube]**.
- Заголовок списка заглушённых игроков больше не коверкает стилизованные
  имена.

## Косметика

- **Два новых косметических предмета от сообщества**: Seasonal Spring
  (анимированный — 8 кадров) и Nuclear glasses.

## Прочие исправления

- Браузер лобби показывает весь состав открытого лобби («+N ещё» теперь
  работает), а четыре текстовые ячейки обрезаются вместо того, чтобы
  молча терять текст — метка дисконекта «(left)» больше не может
  исчезнуть.
- Строки статистики в профиле таблицы лидеров переупорядочены (1v1 теперь
  той же формы, что и другие режимы); «Top Cards» теперь называется
  «Самые используемые карты» на всех языках; формулировка async-турниров
  уточнена («первый до 2 игр» в BO3).
- 44 недавно добавленные строки интерфейса переведены на испанский,
  русский, украинский и шведский.
- Toxic Cloud, который иногда не появляется у игрока, в которого попал
  (баг 260), всё ещё расследуется — в этом релизе есть полевая
  диагностика, чтобы поймать реальный механизм в продакшене.

Спасибо за все баг-репорты — этот патч закрывает все недавно
накопившиеся репорты.$rn1391ru$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.39.1', 'uk', '', $rn1391uk$# v1.39.1

Найбільший патч з виходу 1.39.0: зручності для турнірів, правило раннього
виходу в FFA тепер діє, виправлено фони всіх скінів мап, приглушення звуку
у фоні та довгий список виправлень за баг-репортами.

## Турніри

- **Перевірки перед дедлайном в async.** В останній день 7-денного вікна
  вашого async-матчу бот пише в ПП вам і вашому супернику: чи зв'язалися
  ви і чи плануєте зіграти сьогодні? Три кнопки — **Так** (подовжує
  термін на 24 години; кожен гравець може подовжити один раз на суперника
  за турнір), **Я написав — без відповіді / він пішов** і **Ще ні — досі
  домовляємося**. Кнопки продовжують працювати й після перезапусків
  бота.
- **Готовий грати гравець більше не карається за мовчання іншого.** Якщо
  час async-матчу вийшов і на перевірку відповів лише один із вас, цей
  гравець тепер проходить далі зі звичайною перемогою (суперник
  вважається таким, що здався), замість того щоб вилітали ОБИДВА гравці.
  (Подвійну дискваліфікацію в нижній сітці цього тижня також виправлено
  вручну — готовий грати гравець проходить далі з новим терміном.)
- **Історії sync і async тепер розділені** — попап «Останні турніри»
  показує лише тип власної під-вкладки, а рядок з вашими місцями переїхав
  у цей попап, де йому й місце.

## FFA

- **Вихід до того, як учасники набрали два очки, більше не коштує Elo — і
  правило ДІЄ з цього релізу.** Серверна частина вийшла раніше; тепер ваш
  клієнт передає потрібний їй рахунок на момент виходу. Ігри, що зламалися
  на старті, перестають списувати (або нараховувати) будь-кому рейтинг.
  Два раунди історичних коригувань виправили всі зачеплені минулі ігри.
- **Банер матчболу більше не показує стилізовані імена ВЕЛЕТЕНСЬКИМИ** —
  імена зберігають колір і жирність, але теги розміру вирізаються.
- **Виправлено зависання в кінці гри**: після того як гравець виходив
  посеред сесії, усі інші могли зависнути на екрані VICTORY (попап
  реваншу падав, шукаючи колір порожньої команди).
- **Рейтинг**: великий апсет тепер враховується, навіть якщо гравець,
  який його здійснив, фінішував далеко від вас у таблиці (врахування
  апсетів за межами вікна сусідніх місць — на боці сервера, вже діє).

## Скіни мап

- **Кожен кастомний скін мапи знову показує свій власний задуманий фон.**
  Усі 23 сповзали до одного й того самого рожевувато-червоного. У тому ж
  проході виправлено: скіни, що втрачали фон за кілька секунд після
  початку раунду, перефарбування посеред переходу (застрягання, через яке
  гравці могли лишитися за екраном), вимкнене «освітлення мапи», що
  візуально не застосовувалося, застарілі кольори після повернення на
  ванільний скін, і **зняття останнього кольору мапи тепер працює без
  перезапуску**. Нейтральні скіни (Monochrome, Platinum) знову виглядають
  нейтрально.

## Звук

- **Звук гри тепер приглушується, поки ви згорнуті під час
  онлайн-матчу** (детерміноване відновлення точної гучності при
  поверненні; звук знайденого матчу в черзі все одно доходить).
  Налаштування: `MuteAudioInBackground`, увімкнено за замовчуванням.

## 2v2 і черги

- **Дисконект і повторна черга більше не створюють дублікати серій 2v2.**
  Якщо ви вчотирьох знову стаєте в чергу протягом 30 хвилин, ви
  повертаєтеся в початкову серію зі збереженим рахунком; зайві порожні
  дублікати поглинаються, а ставки звіряються (на боці сервера, вже діє).
- **«Вийти з усіх черг» тепер справді очищає стани 2v2/1v2** — гравець,
  що відключився, більше не застрягає «в матчі» без виходу.

## Глядачі та стримінг

- Глядачі бачать **карти обох команд у 2v2**, а скидання блоку від
  Refresh тепер відображаються на місцях глядачів.
- Камера глядача тримає всіх живих бійців у кадрі, а реванш більше не
  сипле помилками через застарілу корону.
- Трансляція перемикається на більш значущу гру, коли одна з них явно
  більша, а пости про завершення стриму посилаються на точні VOD на
  Twitch/YouTube.

## Чат

- Повідомлення позначаються джерелом: **[Discord], [Game], [Twitch],
  [YouTube]**.
- Заголовок списку заглушених гравців більше не спотворює стилізовані
  імена.

## Косметика

- **Два нові косметичні предмети від спільноти**: Seasonal Spring
  (анімований — 8 кадрів) і Nuclear glasses.

## Інші виправлення

- Браузер лобі показує весь склад відкритого лобі («+N ще» тепер працює),
  а чотири текстові комірки обрізаються замість того, щоб мовчки втрачати
  текст — позначка дисконекту «(left)» більше не може зникнути.
- Рядки статистики в профілі таблиці лідерів перевпорядковано (1v1 тепер
  тієї ж форми, що й інші режими); «Top Cards» тепер називається
  «Найчастіше використовувані карти» всіма мовами; формулювання
  async-турнірів уточнено («перший до 2 ігор» у BO3).
- 44 нещодавно додані рядки інтерфейсу перекладено іспанською,
  російською, українською та шведською.
- Toxic Cloud, який іноді не з'являється у гравця, в якого влучив (баг
  260), досі розслідується — цей реліз містить польову діагностику, щоб
  зловити справжній механізм у продакшені.

Дякуємо за всі баг-репорти — цей патч закриває всі нещодавно накопичені
репорти.$rn1391uk$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.39.1', 'sv', '', $rn1391sv$# v1.39.1

Den största patchen sedan 1.39.0 släpptes: förbättringar för turneringar,
FFA-regeln för tidiga avhopp är nu aktiv, alla kartskinns bakgrunder
lagade, ljuddämpning i bakgrunden och en lång lista buggrapportfixar.

## Turneringar

- **Avstämningar inför deadline i async.** Den sista dagen i din
  async-matchs 7-dagarsfönster skickar boten ett DM till dig och din
  motståndare: har ni fått kontakt, och tänker ni spela idag? Tre
  knappar — **Ja** (förlänger tidsfristen 24 timmar; varje spelare kan
  förlänga en gång per motståndare per turnering), **Jag hörde av mig —
  inget svar / de slutade** och **Inte än — vi planerar fortfarande**.
  Knapparna fortsätter fungera även om boten startas om.
- **En villig spelare straffas inte längre för den andras tystnad.** Om en
  async-match löper ut och bara en av er hade svarat på avstämningen går
  den spelaren nu vidare med en vanlig vinst (motståndaren räknas som att
  ha gett upp), i stället för att BÅDA spelarna slås ut. (Dubbel-DQ:n i
  förlorarsidan den här veckan reparerades också för hand — den villiga
  spelaren går vidare med en ny tidsfrist.)
- **Sync- och async-historiken är nu separerade** — popupen Senaste
  turneringarna visar bara sin egen underfliks typ, och din placeringsrad
  har flyttat in i den popupen där den hör hemma.

## FFA

- **Att lämna innan fältet har tagit två poäng kostar inte längre Elo —
  och regeln är AKTIV från och med den här versionen.** Serverhalvan
  släpptes tidigare; din klient rapporterar nu ställningen vid avhoppet
  som den behöver. Spel som gick sönder i starten slutar debitera (eller
  betala) någon. Två omgångar historiska korrigeringar har reparerat alla
  drabbade tidigare spel.
- **Matchbollsbannern visar inte längre stilade namn i JÄTTEFORMAT** —
  namnen behåller färg och fetstil, men storlekstaggar tas bort.
- **Frysningen vid spelets slut är fixad**: efter att en spelare lämnat
  mitt i en session kunde alla andra platser frysa på VICTORY-skärmen
  (revanschpopupen kraschade när den slog upp ett tomt lags färg).
- **Rating**: en stor skräll räknas nu även när skrällspelaren slutade
  långt ifrån dig i tabellen (skrällar räknas bortom närhetsfönstret — på
  serversidan, redan aktiv).

## Kartskinn

- **Varje eget kartskinn visar sin egen designade bakgrund igen.** Alla 23
  höll på att kollapsa mot samma rosaröda färg. Fixat i samma svep: skinn
  som tappade sin bakgrund några sekunder in i en rond, omfärgningar mitt
  i övergången (stoppet som kunde lämna spelare utanför skärmen),
  avstängd "kartbelysning" som aldrig syntes, kvardröjande färger efter
  byte tillbaka till ett vanilla-skinn, och **att ta av sin sista
  kartfärg fungerar nu utan omstart**. De neutrala skinnen (Monochrome,
  Platinum) ser neutrala ut igen.

## Ljud

- **Spelljudet dämpas nu när du är utanför fönstret under en
  onlinematch** (deterministisk återställning till exakt volym när du
  kommer tillbaka; ljudet för hittad match i kön når dig fortfarande).
  Inställning: `MuteAudioInBackground`, på som standard.

## 2v2 och köer

- **Frånkoppling + ny kö skapar inte längre dubblettserier i 2v2.** Om ni
  fyra köar om inom 30 minuter låses ni åter till den ursprungliga serien
  med ställningen kvar; lösa tomma dubbletter absorberas och insatserna
  stäms av (på serversidan, redan aktivt).
- **"Lämna alla köer" rensar nu faktiskt 2v2/1v2-tillstånden** — en
  frånkopplad spelare fastnar inte längre "i en match" utan utväg.

## Åskådare och streaming

- Åskådare ser **båda lagens kort i 2v2**, och Refresh-blockåterställningar
  renderas nu på åskådarplatser.
- Åskådarkameran håller varje levande spelare i bild, och en revansch
  spammar inte längre fel från en inaktuell krona.
- Sändningen växlar till det bättre spelet när ett är klart större, och
  inläggen när streamen slutar länkar till exakt rätt
  Twitch/YouTube-VOD:ar.

## Chatt

- Meddelanden taggas efter källa: **[Discord], [Game], [Twitch],
  [YouTube]**.
- Rubriken för tystade spelare förvränger inte längre stilade namn.

## Kosmetik

- **Två nya community-kosmetiker**: Seasonal Spring (animerad — 8
  bildrutor) och Nuclear glasses.

## Övriga fixar

- Lobbyläsaren visar hela spelarlistan i en öppen lobby ("+N fler"
  fungerar nu), och fyra textceller klipps i stället för att tyst tappa
  text — frånkopplingsmarkören "(left)" kan inte längre försvinna.
- Statistikraderna i topplistans profil har organiserats om (1v1 har nu
  samma form som de andra lägena); "Top Cards" heter nu "Mest använda
  kort" på alla språk; async-turneringstexten förtydligad ("först till 2
  spel" i en BO3).
- 44 nyligen tillagda gränssnittssträngar översatta till spanska, ryska,
  ukrainska och svenska.
- Att Toxic Cloud ibland inte visas för spelaren den träffade (bugg 260)
  utreds fortfarande — den här versionen innehåller en fältdiagnostik för
  att fånga den verkliga mekanismen i produktion.

Tack för alla buggrapporter — den här patchen stänger hela den senaste
rapporthögen.$rn1391sv$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

-- Verification: expect 5 rows.
SELECT language_code, source, LENGTH(body) AS body_len FROM release_notes_i18n WHERE tag = 'v1.39.1' ORDER BY language_code;

COMMIT;
