-- 305: v1.40.2 release notes, all five locales.
-- The admin POST endpoint is an idempotent upsert into release_notes_i18n;
-- this migration performs the identical write through the migration channel
-- because the VM seat's tooling cannot sign the admin HMAC (learning #443 -
-- the tools read ADMIN_HMAC_SECRET from the environment, never set here).
-- en is the source; es/ru/uk/sv are machine translations matched to the
-- in-game catalogue terminology (same pipeline as 250/262/283/287). Every
-- locale was checked to carry the same section and bullet counts as en
-- before this file was generated - a translation that drops a section would
-- otherwise ship a shorter page with no error anywhere.

BEGIN;

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.40.2', 'en', '', $rn1402$# v1.40.2

## MAIL

- A new Mail page: write to other players (up to 8 at a time, a subject and a
  2,000-character message), read, reply, copy, report, block and delete, with a
  toast and a tone when new mail arrives. Settings gains "Who can mail me"
  (everyone, or only players you have played) and a blocked-sender list.
- Mail and Music are icons now, at the top right above the tabs; the mail icon
  carries a red badge with your unread count. Each opens as a popup over the
  page instead of taking it over: Escape or a click outside closes it, the page
  underneath is untouched, and a half-written message survives closing and
  reopening.

## HOVER A NAME, SEE THE PLAYER

- Hover a player's name on the F5 page - the 1v1 ranked and casual history, the
  four leaderboards, the 1v2 boards and the leaderboard's selected player - and
  a mini-profile opens: name and title, tier, rating and level, online status,
  and your head-to-head in every mode, your last meeting, the current ranked
  streak and your net rating change against them. Click the name to pin the
  card; Escape or a click elsewhere closes it.

## SESSION REPORTS

- A Session button on the ranked, casual, 2v2, FFA and 1v2 history rows opens a
  per-game report of that sitting: damage and score over time, DPS, hit and
  block rates, ping and FPS, totals and builds. On the 1v1 rows there is one
  Session button per opponent per sitting, beside the ID button, on the newest
  game you played them in. A sitting is your finished games split wherever more
  than three hours passed between two of them, so playing someone else in
  between keeps it alive. Requires Steam sign-in; games recorded before
  telemetry show what exists.

## HEAD-TO-HEAD AT MATCH START

- Joining a two-player room shows a corner line for ten seconds, and a Tab-Info
  line for the match: "vs NAME - Last played 3 days ago - H2H 12-8 - Ranked
  series 4", or "First time playing NAME". If the other player is replaced, the
  line clears and fetches again for whoever is there now.

## THE ROOM'S REGION IS PICKED FROM BOTH PINGS

- At the menu, and while you wait in the 1v1 ranked queue, your game pings each
  Photon region itself and sends the numbers with your queue entry. When both of
  you have recent numbers, the room goes to the region that is best for the
  pair, provided that costs neither of you more than 20 ms by your own
  measurements. Otherwise the previous rules stand - and they no longer depend
  on which of the two of you asked for the room first. 2v2 and FFA rooms are
  unchanged for now.

## MATCHED BUT NEVER CONNECTED

- The first player into a queued room is no longer swept out of it after about
  15 seconds and into a public quick-match search while their partner was still
  arriving. That is how a queued player could end up in a casual game against a
  random opponent. The mod's own 60-second wait is the only exit now, with the
  toast at 15 seconds.
- Queueing from the menu straight after an online match no longer fails with a
  60-second timeout: the join now waits for the connection instead of firing
  into it.
- A queued 2v2 lobby that has not filled after 90 seconds returns you to the
  menu and leaves the team queue, instead of sitting on a notification with no
  way out.

## PRESS JUMP TO JOIN

- The stall where the other player is standing in the lobby and the match never
  starts is fixed at its source. Two of the game's own messages can land a frame
  apart, and the guest's body then takes the host's place in the player list, so
  the list never reaches two and the game never starts. Nothing was reported
  anywhere when it happened. Applies to every online 1v1 room, ranked included.
- The other shape - a full room where the other player's body never appears at
  all - now offers an escape hatch after 20 seconds, with Requeue and Return to
  menu. Nothing counts against you.

## OVERPOWER

- Overpower with a box in the blast no longer skips the rest of the explosion,
  so a player processed after the box is hit. Every room type.

## GROW: 240 FPS -> 120 FPS

- Every eligible Grow bullet now grows as if its shooter ran at 120 FPS instead
  of 240: one copy is about x3.1 over a full flight (it was x1.8), two copies
  x9.6, three x30. A room that mixes this version with an older one falls back
  to vanilla growth on every seat, so both of you see the same thing; that lasts
  as long as older versions are in play.
- The Grow article's vanilla numbers were wrong and are corrected. They had been
  worked out from the code's defaults rather than from the card the game
  actually ships.

## LEADERBOARDS

- A green dot marks players who are online. It needs a heartbeat within the last
  three minutes, and it is hidden for anyone using Appear Offline. The boards
  are served from a replica, so when that replica is behind you see no dots
  rather than stale ones.
- Players with no contact in the last 90 days are hidden by default; a toggle
  shows everyone, with their rows marked inactive. Podium places and the titles
  that come with them are held by shown players only. Tournament sign-up and
  seeding are not filtered, and your own position is still reported while you
  are inactive. Discord's `/lb` gains the same option.
- The 2v2 board refreshes every 30 seconds while it is open; it used to load
  once per session.

## RATING

- Rating graphs gain an axis toggle - Updates (one point per completed ranked
  series, the default), Calendar, or Since first, which starts every line
  together - and it is remembered between sessions. The two time axes are step
  plots, so an idle week is a flat run and never a slope. Graphs now start at
  your first recorded update instead of an assumed 1500, and always show your
  most recent 500 updates.
- New previews before a game: FFA (what first, last and each place would do to
  everyone listed) and 2v2. Discord's `/elo` becomes `/elo 1v1`, `/elo 2v2` and
  `/elo ffa`, and `/graph` gains the axis option.

## MUSIC

- A track plays on the first click. There is no prepare step any more: it opens
  in a few milliseconds and decodes while it plays, and tracks you have opened
  stay loaded until the game closes, so switching back to one is instant.
- Deselecting every track plays the game's own music instead of silence.

## DANCES AND CHAT

- The shop lists each dance with its duration, the emote wheel shows it on the
  highlighted slice, and while your emote plays a thin ring above your player
  counts down the time left. Only you see the ring.
- The minimised chat is drawn with the same font as the full chat, so emoji and
  non-Latin names render there the way they do in F5. They stay monochrome for
  now; colour emoji is a separate follow-up.
- ALT while typing switches the language channel - global, each language channel
  in turn, back to global. The Settings note said Tab; it says Alt now.

## THE LIBRARY

- "On Damage Types and Buff Activation" now carries five drawn charts: the
  damage interaction matrix, the Silence sequences, the 0.35 s window sequences,
  the Refresh gate and the full damage flow. The text tables they replace are
  gone, the article is split into shorter pages, and library search still finds
  what is in the charts.

## LEAVING A RANKED SERIES

- When an opponent leaves part-way through, the record of that leave now
  survives a failed send. It remembers which series it belongs to and is retried
  in the background, across a restart if need be, for as long as the server will
  still accept it - the old budget ran out after about an hour and threw away
  reports the server would have taken. A leave that arrives before its proof is
  retried rather than discarded, and only the server retires one for good.
- The background queue of unsent match reports no longer stops for the rest of a
  session because one pass over it failed.

## SMALLER THINGS

- Match history: the stray "repli" at the end of the Ping cell is gone, the
  opponent cell is wider and is now fitted by pixels rather than by counting
  characters, and when a name and title will not both fit the title is dropped
  instead of rendering as "[Beginne..]".
- Page overlays - the search boxes, hover graphs, the session report, the shop
  previews, the profile card - no longer paint over the Music and Mail popups,
  the Info and tournament popups or the full-screen card preview.
- Settings: "Who can mail me" and "Blocked senders" are button-sized like their
  neighbours instead of spanning the panel.
- Lag notices, in Settings and off by default: short corner lines while your
  game is dropping frames, your ping to the relay is high, or the opponent's
  updates are arriving late. 1v1 fighter seats only, and nothing is sent
  anywhere.
- A local build newer than the advertised version no longer reads as outdated.
- The Phoenix sound fix was looking for a method that was never there: 46
  warnings a session, and it patched nothing.
- A report of "no sound effects" now leaves a description of the audio stack in
  the log and in the bug-report bundle, so the next one can be diagnosed.$rn1402$, 'human', NULL)
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.40.2', 'es', '', $rn1402$# v1.40.2

## CORREO

- Nueva página de Correo: escribe a otros jugadores (hasta 8 a la vez, con un
  asunto y un mensaje de 2.000 caracteres), lee, responde, copia, reporta,
  bloquea y elimina, con un aviso y un sonido cuando llega correo nuevo.
  Ajustes gana "Quién puede escribirme" (todos, o solo con quien has jugado)
  y una lista de remitentes bloqueados.
- Correo y Música ahora son iconos, arriba a la derecha sobre las pestañas; el
  icono de correo lleva una insignia roja con tus mensajes sin leer. Cada uno
  se abre como una ventana sobre la página en vez de ocuparla: Escape o un clic
  fuera la cierra, la página de debajo queda intacta, y un mensaje a medio
  escribir sobrevive a cerrar y volver a abrir.

## PASA EL CURSOR POR UN NOMBRE, VE AL JUGADOR

- Pasa el cursor por el nombre de un jugador en la página F5 - el historial
  ranked y casual 1v1, las cuatro clasificaciones, las tablas 1v2 y el jugador
  seleccionado de la clasificación - y se abre un miniperfil: nombre y título,
  tier, rating y nivel, estado de conexión, y tu H2H en cada modo, el último
  encuentro, la racha ranked actual y tu rating neto contra ese rival. Haz clic
  en el nombre para fijar la tarjeta; Escape o un clic en otro sitio la cierra.

## INFORMES DE SESIÓN

- Un botón Sesión en las filas del historial ranked, casual, 2v2, FFA y 1v2
  abre un informe por juego de esa sesión: daño y puntuación a lo largo del
  tiempo, DPS, tasas de acierto y bloqueo, ping y FPS, totales y builds. En las
  filas 1v1 hay un botón Sesión por rival y por sesión, junto al botón ID, en
  el juego más reciente que jugaste contra él. Una sesión son tus juegos
  terminados, cortados allí donde pasaron más de tres horas entre dos de ellos,
  así que jugar contra otra persona por medio la mantiene viva. Requiere
  iniciar sesión en Steam; los juegos registrados antes de la telemetría
  muestran lo que haya.

## H2H AL INICIO DE LA PARTIDA

- Entrar en una sala de dos jugadores muestra una línea en la esquina durante
  diez segundos, y una línea de info en Tab para la partida: "vs NOMBRE -
  Última partida hace 3 días - H2H 12-8 - Series ranked 4", o "Primera vez
  jugando contra NOMBRE". Si el otro jugador es reemplazado, la línea se borra
  y se vuelve a pedir para quien esté ahí ahora.

## LA REGIÓN DE LA SALA SE ELIGE CON LOS PINGS DE AMBOS

- En el menú, y mientras esperas en la cola ranked 1v1, tu juego hace ping a
  cada región de Photon por su cuenta y envía los números con tu entrada en la
  cola. Cuando ambos jugadores tienen números recientes, la sala va a la región
  que es mejor para la pareja, siempre que eso no le cueste a ninguno de los
  dos más de 20 ms según sus propias medidas. Si no, siguen valiendo las reglas
  anteriores - y ya no dependen de cuál de los dos pidió la sala primero. Las
  salas 2v2 y FFA no cambian por ahora.

## EMPAREJADOS PERO SIN CONECTAR

- Al primer jugador que entra en una sala de la cola ya no se le saca de ella a
  los 15 segundos para meterlo en una búsqueda rápida pública mientras su
  pareja todavía estaba llegando. Así era como un jugador en cola podía acabar
  en una partida casual contra un rival al azar. Ahora la única salida es la
  espera de 60 segundos del propio mod, con el aviso a los 15 segundos.
- Entrar en cola desde el menú justo después de una partida online ya no falla
  con un tiempo de espera de 60 segundos: ahora la entrada espera a la conexión
  en vez de dispararse contra ella.
- Una sala 2v2 de la cola que no se ha llenado a los 90 segundos te devuelve al
  menú y sale de la cola de equipo, en vez de quedarse en una notificación sin
  salida.

## PULSA SALTAR PARA UNIRTE

- El atasco en el que el otro jugador está de pie en la sala y la partida nunca
  empieza está arreglado en su origen. Dos mensajes del propio juego pueden
  llegar con un frame de diferencia, y entonces el cuerpo del invitado ocupa el
  sitio del anfitrión en la lista de jugadores, así que la lista nunca llega a
  dos y la partida nunca empieza. Cuando pasaba no se avisaba en ninguna parte.
  Vale para cualquier sala 1v1 online, ranked incluida.
- La otra variante - una sala llena donde el cuerpo del otro jugador no aparece
  nunca - ahora ofrece una salida a los 20 segundos, con Reencolar y Volver al
  menú. Nada cuenta en tu contra.

## OVERPOWER

- Overpower con una caja dentro de la onda ya no se salta el resto de la
  explosión, así que un jugador procesado después de la caja sí recibe el
  golpe. En todos los tipos de sala.

## GROW: 240 FPS -> 120 FPS

- Cada bala Grow que califica ahora crece como si su tirador fuera a 120 FPS en
  vez de 240: una copia es unas x3.1 en un vuelo completo (antes era x1.8), dos
  copias x9.6, tres x30. Una sala que mezcla esta versión con una anterior
  vuelve al crecimiento vanilla en todos los puestos, así que ambos ven lo
  mismo; eso dura mientras haya versiones antiguas en juego.
- Los números vanilla del artículo de Grow estaban mal y quedan corregidos. Se
  habían sacado de los valores por defecto del código en vez de la carta que el
  juego trae de verdad.

## CLASIFICACIONES

- Un punto verde marca a los jugadores en línea. Necesita una señal de vida en
  los últimos tres minutos, y se oculta para quien use Aparecer desconectado.
  Las tablas se sirven desde una réplica, así que cuando esa réplica va por
  detrás no ves ningún punto en vez de ver puntos viejos.
- Los jugadores sin contacto en los últimos 90 días se ocultan por defecto; un
  interruptor los muestra a todos, con sus filas marcadas como (inactivo). Los
  puestos de podio y los títulos que traen consigo solo los ocupan jugadores
  mostrados. La inscripción a torneos y el sembrado no se filtran, y tu propia
  posición se sigue informando mientras estás inactivo. El `/lb` de Discord
  gana la misma opción.
- La tabla 2v2 se refresca cada 30 segundos mientras está abierta; antes se
  cargaba una vez por sesión.

## RATING

- Las gráficas de rating ganan un selector de eje - Actualizaciones (un punto
  por serie ranked terminada, el valor por defecto), Calendario o Desde el
  primero, que arranca todas las líneas juntas - y se recuerda entre sesiones.
  Los dos ejes de tiempo son gráficas de escalones, así que una semana parado
  es un tramo plano y nunca una pendiente. Las gráficas ahora empiezan en tu
  primera actualización registrada en vez de en un 1500 supuesto, y siempre
  muestran tus 500 actualizaciones más recientes.
- Nuevas previsiones antes de un juego: FFA (qué le haría a cada uno de los
  listados quedar primero, último y en cada puesto) y 2v2. El `/elo` de Discord
  pasa a ser `/elo 1v1`, `/elo 2v2` y `/elo ffa`, y `/graph` gana la opción de
  eje.

## MÚSICA

- Una pista suena al primer clic. Ya no hay paso de preparación: se abre en
  unos milisegundos y se decodifica mientras suena, y las pistas que ya has
  abierto siguen cargadas hasta que cierras el juego, así que volver a una es
  instantáneo.
- Deseleccionar todas las pistas hace sonar la música propia del juego en vez
  de silencio.

## BAILES Y CHAT

- La tienda lista cada baile con su duración, la rueda de bailes la muestra en
  el sector resaltado, y mientras se reproduce tu baile un anillo fino sobre tu
  jugador descuenta el tiempo que queda. El anillo solo lo ves tú.
- El chat minimizado se dibuja con la misma fuente que el chat completo, así
  que los emojis y los nombres no latinos se ven ahí igual que en F5. De
  momento siguen en monocromo; los emojis en color son un asunto aparte.
- ALT mientras escribes cambia el canal de idioma - global, cada canal de
  idioma por turno, y de vuelta a global. La nota de Ajustes decía Tab; ahora
  dice Alt.

## LA BIBLIOTECA

- "Sobre tipos de daño y activación de buffs" ahora lleva cinco diagramas
  dibujados: la matriz de interacciones del daño, las secuencias de Silence,
  las secuencias de la ventana de 0,35 s, la puerta de Refresh y el flujo
  completo del daño. Las tablas de texto a las que sustituyen ya no están, el
  artículo se reparte en páginas más cortas, y la búsqueda de la biblioteca
  sigue encontrando lo que hay en los diagramas.

## SALIR DE UNA SERIE RANKED

- Cuando un rival se va a mitad de serie, el registro de esa salida ahora
  sobrevive a un envío fallido. Recuerda a qué serie pertenece y se reintenta
  en segundo plano, incluso tras un reinicio si hace falta, mientras el
  servidor lo siga aceptando - el margen antiguo se agotaba en cosa de una hora
  y tiraba informes que el servidor habría aceptado. Una salida que llega antes
  que su prueba se reintenta en vez de descartarse, y solo el servidor la
  retira para siempre.
- La cola en segundo plano de informes de partida sin enviar ya no se para el
  resto de la sesión porque haya fallado una pasada.

## COSAS MÁS PEQUEÑAS

- Historial de partidas: el "repli" suelto al final de la celda de Ping ya no
  está, la celda del rival es más ancha y ahora se ajusta por píxeles en vez de
  contando caracteres, y cuando un nombre y un título no caben juntos se quita
  el título en vez de dibujarlo como "[Principia..]".
- Las capas de la página - los cuadros de búsqueda, las gráficas al pasar el
  cursor, el informe de sesión, las vistas previas de la tienda, la tarjeta de
  perfil - ya no se pintan encima de las ventanas de Música y Correo, de las de
  Info y torneos ni de la vista previa de carta a pantalla completa.
- Ajustes: "Quién puede escribirme" y "Remitentes bloqueados" tienen tamaño de
  botón como sus vecinos en vez de ocupar todo el panel.
- Avisos de lag, en Ajustes y desactivados por defecto: líneas cortas en la
  esquina mientras tu juego pierde fotogramas, tu ping al relay es alto o las
  actualizaciones del rival llegan tarde. Solo en puestos de luchador 1v1, y no
  se envía nada a ninguna parte.
- Una compilación local más nueva que la versión anunciada ya no se lee como
  desactualizada.
- El arreglo del sonido de Phoenix buscaba un método que nunca estuvo ahí: 46
  avisos por sesión, y no parcheaba nada.
- Un reporte de "sin efectos de sonido" ahora deja una descripción de la pila
  de audio en el registro y en el paquete del reporte de bug, para poder
  diagnosticar el siguiente.$rn1402$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.40.2', 'ru', '', $rn1402$# v1.40.2

## ПОЧТА

- Новая страница «Почта»: пиши другим игрокам (до 8 сразу, тема и сообщение
  до 2000 символов), читай, отвечай, копируй, жалуйся, блокируй и удаляй, а
  при новом письме приходит уведомление со звуком. В «Настройках» появились
  «Кто может писать мне» (все или только те, с кем ты играл) и список
  заблокированных.
- Почта и Музыка теперь иконки — вверху справа над вкладками; на иконке
  почты красный значок с числом непрочитанных. Каждая открывается окном
  поверх страницы, а не вместо неё: Escape или клик снаружи закрывает его,
  страница под ним остаётся нетронутой, а недописанное сообщение переживает
  закрытие и повторное открытие.

## НАВЕДИ НА ИМЯ — УВИДИШЬ ИГРОКА

- Наведи на имя игрока на странице F5 — история рейтинговых и обычных 1v1,
  четыре таблицы лидеров, таблицы 1v2 и выбранный игрок в таблице лидеров —
  и откроется мини-профиль: имя и титул, тир, рейтинг и уровень, статус в
  сети, твой H2H в каждом режиме, ваша последняя встреча, текущий
  рейтинговый стрик и итог рейтинга с ним. Клик по имени закрепляет
  карточку; Escape или клик в стороне закрывает её.

## ОТЧЁТЫ СЕССИЙ

- Кнопка «Сессия» в строках истории рейтинговых, обычных, 2v2, FFA и 1v2
  открывает отчёт сессии по каждой игре того захода: урон и счёт во
  времени, DPS, точность и % блоков, пинг и FPS, итоги и сборки. В строках
  1v1 кнопка «Сессия» одна на соперника за заход — рядом с кнопкой ID, на
  самой свежей игре с ним. Заход — это твои завершённые игры, разрезанные
  там, где между двумя из них прошло больше трёх часов, так что игра с
  кем-то другим в промежутке его не обрывает. Нужен вход через Steam; игры,
  записанные до телеметрии, показывают то, что есть.

## H2H НА СТАРТЕ МАТЧА

- Вход в комнату на двоих показывает строку в углу на десять секунд и
  строку Tab-Info для матча: "против ИМЯ - Последняя игра 3 дн. назад - H2H
  12-8 - Рейтинговые серии 4" или "Первая игра против ИМЯ". Если второй
  игрок сменился, строка очищается и запрашивается заново — уже для того,
  кто в комнате сейчас.

## РЕГИОН КОМНАТЫ ВЫБИРАЕТСЯ ПО ОБОИМ ПИНГАМ

- В меню и пока ты ждёшь в рейтинговой очереди 1v1, игра сама пингует
  каждый регион Photon и отправляет числа вместе с твоей заявкой в очередь.
  Когда у обоих есть свежие числа, комната уходит в регион, который лучше
  для пары — при условии, что это не стоит никому из вас больше 20 ms по
  собственным измерениям. Иначе действуют прежние правила — и они больше не
  зависят от того, кто из вас двоих запросил комнату первым. Комнаты 2v2 и
  FFA пока без изменений.

## НАШЛИ, НО ТАК И НЕ СОЕДИНИЛИСЬ

- Первого игрока, зашедшего в комнату из очереди, больше не выкидывает
  оттуда примерно через 15 секунд в публичный быстрый поиск, пока напарник
  ещё заходил. Именно так игрок из очереди мог оказаться в обычной игре
  против случайного соперника. Теперь единственный выход — собственное
  60-секундное ожидание мода, с уведомлением на 15 секундах.
- Постановка в очередь из меню сразу после онлайн-матча больше не падает с
  60-секундным таймаутом: вход теперь дожидается соединения, а не бьёт в
  него.
- Лобби 2v2 из очереди, которое не заполнилось за 90 секунд, возвращает
  тебя в меню и выводит из командной очереди, вместо того чтобы оставить
  висеть на уведомлении без выхода.

## НАЖМИ ПРЫЖОК, ЧТОБЫ ВОЙТИ

- Зависание, когда второй игрок стоит в лобби, а матч так и не начинается,
  исправлено в самом источнике. Два собственных сообщения игры могут прийти
  с разницей в кадр, и тело гостя тогда занимает место хоста в списке
  игроков, так что список никогда не доходит до двух и игра не стартует.
  Нигде и ничего при этом не сообщалось. Касается всех онлайн-комнат 1v1,
  включая рейтинговые.
- Второй вариант — полная комната, в которой тело второго игрока вообще не
  появляется — теперь через 20 секунд даёт запасной выход с кнопками «Снова
  в очередь» и «В меню». Ничего тебе при этом не засчитывается.

## OVERPOWER

- Overpower с ящиком в зоне взрыва больше не пропускает остаток взрыва, так
  что игрок, обработанный после ящика, получает удар. Во всех типах комнат.

## GROW: 240 FPS -> 120 FPS

- Каждая подходящая пуля Grow теперь растёт так, будто у стрелка 120 FPS, а
  не 240: одна копия — примерно x3.1 за весь полёт (было x1.8), две копии —
  x9.6, три — x30. Комната, где эта версия смешана со старой, откатывается
  к ванильному росту на всех местах, чтобы вы оба видели одно и то же; так
  будет, пока в игре есть старые версии.
- В статье про Grow ванильные числа были неверными и исправлены. Их вывели
  из значений по умолчанию в коде, а не из карты, которую игра на самом
  деле поставляет.

## ТАБЛИЦЫ ЛИДЕРОВ

- Зелёная точка отмечает игроков в сети. Нужен сигнал за последние три
  минуты, и она скрыта у всех, кто включил «Казаться оффлайн». Таблицы
  отдаются с реплики, поэтому, когда реплика отстаёт, ты видишь не
  устаревшие точки, а вообще никаких.
- Игроки без контакта за последние 90 дней по умолчанию скрыты;
  переключатель показывает всех, их строки помечены как неактивные. Места
  на пьедестале и титулы, которые к ним прилагаются, достаются только
  показанным игрокам. Запись на турнир и посев не фильтруются, а твоя
  собственная позиция по-прежнему сообщается, пока ты неактивен. У `/lb` в
  Discord появилась та же опция.
- Таблица 2v2 обновляется каждые 30 секунд, пока открыта; раньше она
  загружалась один раз за сессию.

## РЕЙТИНГ

- У графиков рейтинга появился переключатель оси — «Обновления» (по точке
  на завершённую рейтинговую серию, по умолчанию), «Календарь» или «С
  первого», где все линии стартуют вместе, — и он запоминается между
  сессиями. Обе временные оси рисуются ступенями, так что неделя простоя —
  это ровная полка, а не наклон. Графики теперь начинаются с твоего первого
  записанного обновления, а не с предполагаемых 1500, и всегда показывают
  последние 500 обновлений.
- Новые превью перед игрой: FFA (что первое, последнее и каждое место
  сделают со всеми в списке) и 2v2. `/elo` в Discord превращается в
  `/elo 1v1`, `/elo 2v2` и `/elo ffa`, а у `/graph` появляется выбор оси.

## МУЗЫКА

- Трек играет с первого клика. Шага подготовки больше нет: трек
  открывается за несколько миллисекунд и декодируется на ходу, а открытые
  тобой треки остаются загруженными до закрытия игры, так что вернуться к
  одному из них можно мгновенно.
- Если снять выделение со всех треков, играет собственная музыка игры, а не
  тишина.

## ТАНЦЫ И ЧАТ

- Магазин показывает у каждого танца его длительность, колесо эмоций
  показывает её на подсвеченном секторе, а пока эмоция играет, тонкое
  кольцо над твоим игроком отсчитывает оставшееся время. Кольцо видишь
  только ты.
- Свёрнутый чат рисуется тем же шрифтом, что и полный, так что эмодзи и
  нелатинские имена отображаются там так же, как в F5. Пока они
  чёрно-белые; цветные эмодзи — отдельная задача на потом.
- ALT во время набора переключает языковой канал — общий, затем каждый
  языковой канал по очереди, и обратно на общий. В заметке в «Настройках»
  был указан Tab; теперь там Alt.

## БИБЛИОТЕКА

- «О типах урона и активации баффов» теперь содержит пять нарисованных
  схем: матрицу взаимодействия урона, последовательности Silence,
  последовательности окна 0.35 с, гейт Refresh и полный поток урона.
  Текстовые таблицы, которые они заменили, убраны, статья разбита на более
  короткие страницы, а поиск по библиотеке по-прежнему находит то, что есть
  на схемах.

## ВЫХОД ИЗ РЕЙТИНГОВОЙ СЕРИИ

- Когда соперник выходит на середине, запись об этом выходе теперь
  переживает неудачную отправку. Она помнит, к какой серии относится, и
  повторяется в фоне, при необходимости через перезапуск, столько, сколько
  сервер её ещё примет — прежний бюджет кончался примерно через час и
  выбрасывал отчёты, которые сервер бы принял. Выход, пришедший раньше
  своего подтверждения, теперь повторяется, а не отбрасывается, и списать
  его окончательно может только сервер.
- Фоновая очередь неотправленных отчётов о матчах больше не встаёт до конца
  сессии из-за одного неудачного прохода по ней.

## ПО МЕЛОЧИ

- История матчей: лишнее «repli» в конце ячейки пинга убрано, ячейка
  соперника стала шире и подгоняется по пикселям, а не по подсчёту
  символов, а когда имя и титул вместе не влезают, отбрасывается титул,
  вместо того чтобы рисовать «[Новичо..]».
- Оверлеи страницы — поля поиска, графики по наведению, отчёт сессии,
  превью в магазине, карточка профиля — больше не рисуются поверх окон
  Музыки и Почты, окон Инфо и турниров и полноэкранного превью карты.
- Настройки: «Кто может писать мне» и «Заблокированные» теперь размером с
  кнопку, как соседние пункты, а не во всю панель.
- Уведомления о лагах, в «Настройках» и выключены по умолчанию: короткие
  строки в углу, когда твоя игра теряет кадры, пинг до релея высокий или
  обновления от соперника приходят с опозданием. Только для бойцовских мест
  1v1, и никуда ничего не отправляется.
- Локальная сборка новее объявленной версии больше не считается устаревшей.
- Исправление звука Phoenix искало метод, которого там никогда не было: 46
  предупреждений за сессию, и ничего не патчилось.
- Жалоба на «нет звуковых эффектов» теперь оставляет описание аудиостека в
  логе и в пакете баг-репорта, чтобы следующую можно было диагностировать.$rn1402$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.40.2', 'uk', '', $rn1402$# v1.40.2

## ПОШТА

- Нова сторінка Пошта: пишіть іншим гравцям (до 8 за раз, тема й
  повідомлення на 2,000 символів), читайте, відповідайте, копіюйте,
  скаржтеся, блокуйте й видаляйте, зі сповіщенням і звуком, коли надходить
  нова пошта. У Налаштуваннях з'являється «Хто може писати мені» (усі або
  лише ті, з ким ви грали) і список заблокованих відправників.
- Пошта й Музика тепер іконки, угорі праворуч над вкладками; на іконці
  пошти червоний значок із кількістю непрочитаних. Кожна відкривається
  спливаючим вікном поверх сторінки, а не замість неї: Escape або клік поза
  вікном закриває його, сторінка під ним лишається недоторканою, а
  недописане повідомлення переживає закриття й повторне відкриття.

## НАВЕДІТЬ НА ІМ'Я - ПОБАЧИТЕ ГРАВЦЯ

- Наведіть на ім'я гравця на сторінці F5 - історія рейтингових і звичайних
  ігор 1v1, чотири таблиці лідерів, таблиці 1v2 і вибраний гравець у
  таблиці лідерів - і відкриється міні-профіль: ім'я й титул, тір, рейтинг
  і рівень, статус онлайн, ваш H2H у кожному режимі, ваша остання зустріч,
  поточний стрік у Ranked і чиста зміна рейтингу проти нього. Клацніть на
  ім'я, щоб закріпити картку; Escape або клік деінде закриває її.

## ЗВІТИ СЕСІЇ

- Кнопка «Сесія» в рядках історії Ranked, звичайних ігор, 2v2, FFA і 1v2
  відкриває погровий звіт тієї сесії: шкода й рахунок у часі, DPS, %
  влучань і % блоків, пінг і FPS, підсумки та збірки. У рядках 1v1 на
  кожного суперника припадає одна кнопка «Сесія» за сесію - поруч із
  кнопкою ID, на найновішій грі, яку ви з ним зіграли. Сесія - це ваші
  завершені ігри, розбиті там, де між двома з них минуло понад три години,
  тож гра з кимось іншим у проміжку її не обриває. Потрібен вхід через
  Steam; ігри, записані до телеметрії, показують те, що є.

## H2H НА СТАРТІ МАТЧУ

- Вхід у кімнату на двох показує рядок у кутку на десять секунд і рядок
  матчу в інфо по Tab: "проти NAME - Остання гра 3 дні тому - H2H 12-8 -
  Рейтингові серії: 4" або "Перша гра проти NAME". Якщо другого гравця
  замінює хтось інший, рядок очищається і завантажується знову для того,
  хто там зараз.

## РЕГІОН КІМНАТИ ОБИРАЄТЬСЯ ЗА ПІНГАМИ ОБОХ

- У меню й поки ви чекаєте в черзі 1v1 Ranked, ваша гра сама пінгує кожен
  регіон Photon і надсилає ці числа разом із заявкою в чергу. Коли свіжі
  числа є в обох, кімната йде в регіон, найкращий для пари, - за умови, що
  це не коштує жодному з вас більше ніж 20 ms за його власними вимірами.
  Інакше діють попередні правила - і вони більше не залежать від того, хто
  з вас двох попросив кімнату першим. Кімнати 2v2 і FFA поки без змін.

## ЗНАЙШЛО ПАРУ, АЛЕ З'ЄДНАННЯ НЕ БУЛО

- Гравця, який зайшов у кімнату з черги першим, більше не викидає звідти
  приблизно за 15 секунд у публічний пошук швидкого матчу, поки напарник
  ще під'єднувався. Саме так гравець із черги міг опинитися у звичайній
  грі проти випадкового суперника. Тепер єдиний вихід - власне
  60-секундне очікування мода, зі сповіщенням на 15-й секунді.
- Постановка в чергу з меню одразу після онлайн-матчу більше не
  завершується 60-секундним таймаутом: приєднання тепер чекає на
  з'єднання, а не стріляє в нього.
- Лобі 2v2 із черги, яке не заповнилося за 90 секунд, повертає вас у меню
  й виводить із командної черги, а не лишає висіти на сповіщенні без
  виходу.

## НАТИСНІТЬ СТРИБОК, ЩОБ ПРИЄДНАТИСЯ

- Зависання, коли другий гравець стоїть у лобі, а матч так і не
  починається, виправлено в корені. Два власні повідомлення гри можуть
  прийти з різницею в кадр, і тіло гостя тоді займає місце господаря у
  списку гравців, тож список ніколи не доходить до двох, а гра не
  стартує. Ніде нічого про це не повідомлялося. Стосується кожної
  онлайн-кімнати 1v1, включно з Ranked.
- Інша форма - повна кімната, де тіло другого гравця взагалі не
  з'являється - тепер дає аварійний вихід через 20 секунд, із кнопками
  «У чергу знову» і «Повернутися в меню». Нічого вам не зараховується.

## OVERPOWER

- Overpower із ящиком у зоні вибуху більше не пропускає решту вибуху, тож
  гравець, оброблений після ящика, отримує влучання. Усі типи кімнат.

## GROW: 240 FPS -> 120 FPS

- Кожна придатна куля Grow тепер росте так, ніби той, хто стріляв, грав на
  120 FPS, а не на 240: одна копія дає приблизно x3.1 за повний політ
  (було x1.8), дві копії - x9.6, три - x30. Кімната, де ця версія змішана
  зі старішою, відкочується до ванільного росту на всіх місцях, щоб обидва
  бачили одне й те саме; так буде, доки в грі лишаються старіші версії.
- Ванільні числа у статті про Grow були неправильні й виправлені. Їх
  вирахували з дефолтів у коді, а не з карти, яку гра насправді постачає.

## ТАБЛИЦІ ЛІДЕРІВ

- Зелена крапка позначає гравців, які онлайн. Для неї потрібен сигнал за
  останні три хвилини, і вона прихована для тих, хто ввімкнув «Здаватися
  офлайн». Таблиці віддає репліка, тож коли репліка відстає, ви бачите
  відсутність крапок, а не застарілі.
- Гравців без контакту за останні 90 днів типово приховано; перемикач
  показує всіх, а їхні рядки позначено як неактивні. Місця на подіумі й
  титули, що йдуть із ними, належать лише показаним гравцям. Реєстрацію на
  турніри й посів це не фільтрує, а ваша власна позиція повідомляється й
  тоді, коли ви неактивні. У Discord `/lb` отримує такий самий параметр.
- Таблиця 2v2 оновлюється кожні 30 секунд, поки вона відкрита; раніше вона
  завантажувалася раз на сесію.

## РЕЙТИНГ

- Графіки рейтингу отримують перемикач осі - «Оновлення» (одна точка на
  завершену рейтингову серію, типово), «Календар» або «Від першого», що
  зводить усі лінії на старт, - і він запам'ятовується між сесіями. Обидві
  часові осі східчасті, тож тиждень простою це рівна ділянка, а не нахил.
  Графіки тепер починаються з вашого першого записаного оновлення, а не з
  умовних 1500, і завжди показують ваші 500 останніх оновлень.
- Нові прев'ю перед грою: FFA (що дадуть перше місце, останнє й кожне інше
  всім переліченим) і 2v2. У Discord `/elo` стає `/elo 1v1`, `/elo 2v2` і
  `/elo ffa`, а `/graph` отримує вибір осі.

## МУЗИКА

- Трек грає з першого кліку. Кроку підготовки більше немає: він
  відкривається за кілька мілісекунд і декодується під час відтворення, а
  відкриті вами треки лишаються завантаженими до виходу з гри, тож
  повернення до одного з них миттєве.
- Якщо зняти вибір з усіх треків, гратиме власна музика гри, а не тиша.

## ТАНЦІ Й ЧАТ

- Магазин показує тривалість кожного танцю, колесо танців показує її на
  підсвіченому секторі, а поки грає ваш танець, тонке кільце над вашим
  гравцем відлічує решту часу. Кільце бачите тільки ви.
- Згорнутий чат малюється тим самим шрифтом, що й повний, тож емодзі й
  нелатинські імена виглядають там так само, як у F5. Поки вони
  монохромні; кольорові емодзі - окреме продовження.
- ALT під час набору перемикає мовний канал - глобальний, далі кожен
  мовний канал по черзі, і назад у глобальний. У примітці в Налаштуваннях
  був Tab; тепер там Alt.

## БІБЛІОТЕКА

- «Про типи шкоди й активацію бафів» тепер має п'ять намальованих схем:
  таблиця взаємодій шкоди, послідовності Silence, послідовності вікна
  0.35 с, ворота Refresh і повний потік шкоди. Текстові таблиці, які вони
  замінили, прибрано, статтю розбито на коротші сторінки, а пошук по
  бібліотеці й далі знаходить те, що є на схемах.

## ВИХІД ІЗ РЕЙТИНГОВОЇ СЕРІЇ

- Коли суперник іде посеред серії, запис про цей вихід тепер переживає
  невдалу відправку. Він пам'ятає, до якої серії належить, і повторюється
  у фоні, за потреби і після перезапуску, доки сервер його ще прийме -
  старий бюджет вичерпувався приблизно за годину й викидав звіти, які
  сервер узяв би. Вихід, що надходить раніше за своє підтвердження, тепер
  повторюється, а не відкидається, і тільки сервер закриває його
  остаточно.
- Фонова черга ненадісланих звітів про матчі більше не зупиняється до
  кінця сесії через те, що один прохід по ній не вдався.

## ДРІБНІШЕ

- Історія матчів: зайве «repli» в кінці комірки «Пінг» прибрано, комірка
  суперника ширша й тепер підганяється по пікселях, а не за підрахунком
  символів, а коли ім'я й титул разом не влазять, титул прибирають замість
  того, щоб малювати «[Початківе..]».
- Оверлеї сторінки - поля пошуку, графіки при наведенні, звіт сесії,
  прев'ю магазину, картка профілю - більше не малюються поверх спливаючих
  вікон Музики й Пошти, вікон Інфо й турнірів чи повноекранного перегляду
  карти.
- Налаштування: «Хто може писати мені» і «Заблоковані відправники» тепер
  розміром із кнопку, як їхні сусіди, а не на всю панель.
- Сповіщення про лаги, у Налаштуваннях і типово вимкнені: короткі рядки в
  кутку, коли ваша гра губить кадри, ваш пінг до релею високий або
  оновлення від суперника приходять із запізненням. Тільки місця бійців у
  1v1, і нікуди нічого не надсилається.
- Локальна збірка, новіша за оголошену версію, більше не читається як
  застаріла.
- Виправлення звуку Phoenix шукало метод, якого там ніколи не було: 46
  попереджень за сесію, і воно нічого не патчило.
- Баг-репорт про «немає звукових ефектів» тепер лишає опис аудіостека в
  лозі й у пакеті баг-репорту, щоб наступний можна було діагностувати.$rn1402$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.40.2', 'sv', '', $rn1402$# v1.40.2

## POST

- En ny Post-sida: skriv till andra spelare (upp till 8 åt gången, ett ämne och
  ett meddelande på 2 000 tecken), läs, svara, kopiera, rapportera, blockera och
  radera, med en avisering och en ton när ny post kommer in. Inställningar får
  "Vem får skicka post till mig" (alla, eller bara spelare du mött) och en lista
  över blockerade avsändare.
- Post och Musik är ikoner nu, uppe till höger ovanför flikarna; postikonen bär
  en röd bricka med antalet olästa. Var och en öppnas som en popup över sidan
  istället för att ta över den: Escape eller ett klick utanför stänger den,
  sidan under är orörd, och ett halvskrivet meddelande överlever att du stänger
  och öppnar igen.

## HÅLL MUSEN ÖVER ETT NAMN, SE SPELAREN

- Håll musen över ett spelarnamn på F5-sidan - Ranked- och casual-historiken för
  1v1, de fyra topplistorna, 1v2-listorna och topplistans valda spelare - så
  öppnas en miniprofil: namn och titel, tier, rating och nivå, onlinestatus, och
  din H2H i varje läge, ert senaste möte, den aktuella Ranked-sviten och din
  nettorating mot dem. Klicka på namnet för att nåla fast kortet; Escape eller
  ett klick någon annanstans stänger det.

## SESSIONSRAPPORTER

- En Session-knapp på historikraderna för Ranked, casual, 2v2, FFA och 1v2
  öppnar en rapport per match för den sittningen: skada och poäng över tid, DPS,
  träff- och blockandelar, ping och FPS, totalt och builds. På 1v1-raderna finns
  en Session-knapp per motståndare och sittning, bredvid ID-knappen, på den
  senaste matchen du spelade mot dem. En sittning är dina avslutade matcher,
  uppdelade varhelst mer än tre timmar gick mellan två av dem, så att spela mot
  någon annan däremellan håller den vid liv. Kräver Steam-inloggning; matcher
  registrerade före telemetrin visar det som finns.

## H2H VID MATCHSTART

- När du går in i ett tvåspelarrum visas en hörnrad i tio sekunder, och en
  Tab-Info-rad för matchen: "vs NAMN - Senaste matchen för 3 dagar sedan - H2H
  12-8 - Ranked-serier 4", eller "Första gången mot NAMN". Om den andra spelaren
  byts ut rensas raden och hämtas på nytt för den som är där nu.

## RUMMETS REGION VÄLJS FRÅN BÅDAS PINGAR

- I menyn, och medan du väntar i 1v1-Ranked-kön, pingar ditt spel själv varje
  Photon-region och skickar siffrorna med din köanmälan. När ni båda har färska
  siffror hamnar rummet i den region som är bäst för paret, förutsatt att det
  inte kostar någon av er mer än 20 ms enligt era egna mätningar. Annars gäller
  de tidigare reglerna - och de beror inte längre på vem av er två som bad om
  rummet först. 2v2- och FFA-rum är oförändrade tills vidare.

## MATCHAD MEN ALDRIG ANSLUTEN

- Den första spelaren in i ett köat rum sopas inte längre ut ur det efter
  ungefär 15 sekunder och in i en publik snabbmatchssökning medan motparten
  fortfarande var på väg in. Det var så en köad spelare kunde hamna i en
  casual-match mot en slumpmässig motståndare. Moddens egen väntan på 60
  sekunder är den enda utgången nu, med aviseringen vid 15 sekunder.
- Att köa från menyn direkt efter en onlinematch misslyckas inte längre med en
  60-sekunders timeout: anslutningen till rummet väntar nu in uppkopplingen
  istället för att skjuta in i den.
- En köad 2v2-lobby som inte fyllts efter 90 sekunder tar dig tillbaka till
  menyn och lämnar lagkön, istället för att fastna på en avisering utan väg ut.

## TRYCK HOPPA FÖR ATT GÅ MED

- Stoppet där den andra spelaren står i lobbyn och matchen aldrig startar är
  fixat vid källan. Två av spelets egna meddelanden kan landa en bildruta isär,
  och gästens kropp tar då värdens plats i spelarlistan, så listan når aldrig
  två och matchen startar aldrig. Ingenting rapporterades någonstans när det
  hände. Gäller varje online-1v1-rum, Ranked inräknat.
- Den andra varianten - ett fullt rum där den andra spelarens kropp aldrig dyker
  upp alls - erbjuder nu en nödutgång efter 20 sekunder, med Köa igen och
  Tillbaka till menyn. Ingenting räknas emot dig.

## OVERPOWER

- Overpower med en låda i sprängvågen hoppar inte längre över resten av
  explosionen, så en spelare som behandlas efter lådan träffas. Alla rumstyper.

## GROW: 240 FPS -> 120 FPS

- Varje berättigad Grow-kula växer nu som om dess skytt körde i 120 FPS istället
  för 240: en kopia ger ungefär x3.1 över en full flygning (det var x1.8), två
  kopior x9.6, tre x30. Ett rum som blandar den här versionen med en äldre
  faller tillbaka till originalets tillväxt hos alla, så ni båda ser samma sak;
  det gäller så länge äldre versioner är med i spelet.
- Grow-artikelns originalsiffror var fel och är rättade. De hade räknats ut från
  kodens standardvärden istället för från kortet spelet faktiskt levererar.

## TOPPLISTOR

- En grön punkt markerar spelare som är online. Den kräver en livssignal inom de
  senaste tre minuterna, och den döljs för alla som använder Visa som offline.
  Listorna levereras från en replik, så när den repliken ligger efter ser du
  inga punkter alls hellre än inaktuella.
- Spelare utan kontakt de senaste 90 dagarna är dolda som standard; en växel
  visar alla, med deras rader märkta (inaktiv). Pallplatser och titlarna som
  följer med dem innehas bara av visade spelare. Turneringsanmälan och seedning
  filtreras inte, och din egen placering rapporteras fortfarande medan du är
  inaktiv. Discords `/lb` får samma alternativ.
- 2v2-listan uppdateras var 30:e sekund medan den är öppen; tidigare laddades
  den en gång per session.

## RATING

- Ratinggrafer får en axelväxel - Uppdateringar (en punkt per avslutad
  Ranked-serie, standard), Kalender, eller Sedan första, som låter alla linjer
  starta tillsammans - och den kommer ihåg mellan sessioner. De två tidsaxlarna
  är stegdiagram, så en vecka utan spel är en platt sträcka och aldrig en
  lutning. Graferna börjar nu vid din första registrerade uppdatering istället
  för ett antaget 1500, och visar alltid dina 500 senaste uppdateringar.
- Nya förhandsvisningar före en match: FFA (vad första, sista och varje
  placering skulle göra med alla i listan) och 2v2. Discords `/elo` blir
  `/elo 1v1`, `/elo 2v2` och `/elo ffa`, och `/graph` får axelalternativet.

## MUSIK

- Ett spår spelas på första klicket. Det finns inget förberedelsesteg längre:
  det öppnas på några millisekunder och avkodas medan det spelar, och spår du
  har öppnat förblir laddade tills spelet stängs, så att byta tillbaka till ett
  går direkt.
- Att avmarkera alla spår spelar spelets egen musik istället för tystnad.

## DANSER OCH CHATT

- Butiken listar varje dans med sin längd, emote-hjulet visar den på den
  markerade delen, och medan din emote spelas räknar en tunn ring ovanför din
  spelare ner tiden som är kvar. Bara du ser ringen.
- Den minimerade chatten ritas med samma typsnitt som den fulla chatten, så
  emojier och icke-latinska namn renderas där som de gör i F5. De förblir
  enfärgade tills vidare; färgemojier är en separat uppföljning.
- ALT medan du skriver byter språkkanal - global, varje språkkanal i tur och
  ordning, tillbaka till global. Noteringen i Inställningar sa Tab; den säger
  Alt nu.

## BIBLIOTEKET

- "Om skadetyper och buffaktivering" har nu fem ritade diagram: matrisen över
  skadeinteraktioner, Silence-sekvenserna, sekvenserna för
  0,35-sekundersfönstret, Refresh-grinden och hela skadeflödet. Texttabellerna
  de ersätter är borta, artikeln är uppdelad i kortare sidor, och
  bibliotekssökningen hittar fortfarande det som står i diagrammen.

## ATT LÄMNA EN RANKED-SERIE

- När en motståndare lämnar mitt i överlever noteringen om det avhoppet nu en
  misslyckad sändning. Den minns vilken serie den hör till och görs om i
  bakgrunden, över en omstart om det behövs, så länge servern fortfarande tar
  emot den - den gamla budgeten tog slut efter ungefär en timme och kastade bort
  rapporter servern hade tagit emot. Ett avhopp som kommer fram före sitt bevis
  görs om istället för att slängas, och bara servern pensionerar ett för gott.
- Bakgrundskön med osända matchrapporter stannar inte längre resten av sessionen
  för att ett svep över den misslyckades.

## MINDRE SAKER

- Matchhistorik: det överblivna "repli" i slutet av Ping-cellen är borta,
  motståndarcellen är bredare och anpassas nu efter pixlar istället för genom
  att räkna tecken, och när ett namn och en titel inte får plats tillsammans
  stryks titeln istället för att renderas som "[Nybörja..]".
- Sidöverlägg - sökrutorna, hovergraferna, sessionsrapporten, butikens
  förhandsvisningar, profilkortet - målar inte längre över popuperna för Musik
  och Post, Info- och turneringspopuperna eller den helskärmsvisade
  kortförhandsvisningen.
- Inställningar: "Vem får skicka post till mig" och "Blockerade avsändare" är
  knappstora som sina grannar istället för att sträcka sig över hela panelen.
- Laggaviseringar, i Inställningar och avstängda som standard: korta hörnrader
  medan ditt spel tappar bildrutor, din ping till reläservern är hög, eller
  motståndarens uppdateringar kommer sent. Bara för 1v1-spelare i matchen, och
  ingenting skickas någonstans.
- Ett lokalt bygge som är nyare än den annonserade versionen läses inte längre
  som föråldrat.
- Phoenix-ljudfixen letade efter en metod som aldrig fanns: 46 varningar per
  session, och den patchade ingenting.
- En rapport om "inga ljudeffekter" lämnar nu en beskrivning av ljudstacken i
  loggen och i buggrapportspaketet, så att nästa kan diagnostiseras.$rn1402$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

DO $$
DECLARE n INT;
BEGIN
    SELECT COUNT(*) INTO n FROM release_notes_i18n
     WHERE tag = 'v1.40.2' AND language_code IN ('en','es','ru','uk','sv')
       AND length(body) > 500;
    IF n <> 5 THEN
        RAISE EXCEPTION 'post-check FAILED: % of 5 v1.40.2 locales stored with a real body', n;
    END IF;
    RAISE NOTICE 'post-check OK: all 5 v1.40.2 release-note locales stored';
END $$;

COMMIT;
