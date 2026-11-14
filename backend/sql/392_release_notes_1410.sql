-- 392: v1.41.0 release notes, all five locales.
-- The admin POST endpoint is an idempotent upsert into release_notes_i18n;
-- this migration performs the identical write through the migration channel
-- because the VM seat's tooling cannot sign the admin HMAC (learning #443 -
-- the tools read ADMIN_HMAC_SECRET from the environment, never set here).
-- en is the source; es/ru/uk/sv are machine translations matched to the
-- in-game catalogue terminology (same pipeline as 250/262/283/287/305). Every
-- locale was checked to carry the same section and bullet counts as en (12
-- sections, 31 bullets) before this file was generated - a translation that
-- drops a section would otherwise ship a shorter page with no error anywhere.
-- Length: the client renders a body with MarkdownToTmp (plugin/ApiClient.cs),
-- which wraps every heading and bullet in rich-text tags, and cuts the
-- RENDERED text past 9000 characters. Each body was measured that way before
-- this file was generated (longest: ru, 8961 rendered). The post-check
-- refuses a body whose rendered length can pass 9000 - stored length plus 25
-- per bullet line plus 44 per heading line, for a body with no inline markup
-- and no indented bullet - so a later edit cannot ship a page cut short.
-- A second run writes nothing: each upsert rewrites a row only when a stored
-- value differs (backend/tests/test_migration_reruns.py measures a re-run by
-- row version, and SET x = EXCLUDED.x over an unchanged row still rewrites
-- it). The post-check also refuses a body that still holds a placeholder or
-- a draft marker, so a half-finished file cannot commit. Its probe strings
-- are split with || so that a grep of this file for a leftover placeholder
-- (the ship runbook's F6 check) counts only real leftovers, not the probes.
-- Two NOTICEs close a run that commits: how many of the five rows it wrote
-- (5 on a first run, 0 on a re-run over the same text), then the
-- post-check's OK line.
-- Line endings: each body is stored through replace(..., chr(13), ''). A
-- Windows checkout (core.autocrlf=true) turns this file's LF into CRLF, and a
-- run from such a copy must store the same bytes as the LXC clone's LF copy.
-- Timeouts: lock_timeout bounds only the wait to acquire a lock (5 s); a
-- lock once taken is held until COMMIT. statement_timeout bounds each
-- statement and idle_in_transaction_session_timeout each pause between
-- statements, on separate budgets, and PostgreSQL 16 has no
-- transaction_timeout, so their sum bounds the hold only for a single
-- statement. This file therefore runs ONE statement between its SET LOCAL
-- lines and COMMIT, the DO block below (the five upserts and the
-- post-check).
-- THE COMMIT. PostgreSQL disables the statement timer before it commits, so
-- the COMMIT's own work is outside every timeout above. synchronous_commit
-- = local keeps that work LOCAL: it never waits for a standby's
-- confirmation, whatever synchronous_standby_names says now or later (read
-- on the primary 2026-10-30: empty, synchronous_commit on, server 16.15).
-- BOUNDED: everything before COMMIT -- the wait for the lock (5 s, before
-- the hold starts) and the hold up to COMMIT (statement 25 s + idle 5 s =
-- 30 s). NOT BOUNDED: the COMMIT's local completion -- the WAL flush and the
-- transaction-status (pg_xact) write, which can read an evicted page -- I/O
-- that no PostgreSQL setting bounds, for this or any transaction. The hold
-- is therefore 30 s plus the COMMIT's local completion.
-- backend/tests/test_migration_reruns.py holds this file and its rollback
-- to one statement, to synchronous_commit = local and to the 30 s sum of
-- the two budgets it can measure.
-- Rollback: rollback_392_release_notes_1410.sql.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

DO $m392$
DECLARE n INT; c INT; p INT; k INT; w INT := 0;
BEGIN

    INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
    VALUES ('v1.41.0', 'en', '', replace($rn1410$# v1.41.0

## PLAYER CARDS

- Player Cards: collectible cards of the people who play here, in a new
  Collection tab in the Shop group. Packs come from a free daily claim, gold
  or shards, and by chance from ranked wins.
- Every unbanned player who has run the mod on Steam has a card. Rarity is
  the player's rank in the card pool on the day of the pull (top two:
  Legendary), and any card can also come out Foil or Signed.
- A card shows its player's public Steam picture until their game uploads
  their character. Pictures are now framed on the character itself, so your
  game redraws and re-uploads yours when you first open Player Cards.
  Deleting your data removes every card of you.
- Shard cards one at a time, in a batch, or from the pull tab with Shard
  dupes; a card received in a trade gives no shards, and discarded cards stay
  stamped in your pack history. Trade cards in the new Trades view; switches
  in the Player Cards settings turn trading on or off and choose whether
  others see your cards and whether your rare pulls may be posted in Discord.
- Dance on my card plays one of your dances on your card. Your Top card is
  named on your card face with its art; the Settings picture row shows your
  whole card as others see it. Sort the binder by each player's standing
  today; card editions roll over on a schedule.
- In Discord, /pack and /binder show your packs and collection as images,
  /daily opens your daily pack, /buypack buys one with gold or shards, and
  /card shows a player's full card and posts its dance as a GIF once its
  preview is ready. The bot's leaderboard channel carries the 1v1, 2v2 and FFA
  boards, and sync tournaments use one rule for who counts toward the start
  vote.

## REJOIN

- 2v2 and 1v2: when a player drops, the game waits at the next point so they
  can come back; if they do not, the disconnect is handled as before. This
  needs everyone in the room on 1.41.0.
- FFA late entry and mid-game rejoin, with card picks made for an absent
  player, are on in FFA rooms where everyone runs 1.41.0.

## TITLE LADDERS

- Title ladders now live in the Shop's Titles section, five tiers each (click
  one to open them); titles up to 16 characters show whole on FFA boards. The
  Voidshot and Kingslayer titles are retired and refunded in gold.

## SETTINGS AND CONTROLS

- Controls: a new Controls sub-tab in Settings rebinds the mod's own keys and
  the game's controls.
- Settings is rebuilt as eight sub-tabs of one-line rows with a help pane;
  every sub-tab but Privacy & account resets to recommended values (Controls
  to the default keys); a controller can switch sub-tabs and press rows.
- Damage and healing numbers above players: Off, Me or Everyone (Off by
  default). Two avatar defaults: a modded one where everyone has the mod, a
  vanilla one for Quick Match and games with someone without it; the game
  switches for that room and back when you leave.
- A new icon beside Mail and Music opens the bug-report form; the F5 footer
  gains a scrmod.com button.

## ROOM RULES

- Same Cards works in every mode (1v1 when both players want it, hosted modes
  when the host turns it on); 2v2 and 1v2 hosts can turn friendly fire off.
  Both rules are fixed at room creation, shown in a strip at the top of the
  screen and recorded in every history (per game in FFA) and Discord result
  post.

## FFA

- A ranked FFA is rated only when every player runs 1.41.0 or newer. In such
  a room the start waits while players connect; if one cannot, the lobby
  re-forms with the rest or closes before the match.
- With players on different mod versions, everyone's card pick counts again
  (bugs 435, 436). Attempted fix: Lifestealer re-picks its target each time
  it activates, in rooms where everyone runs 1.41.0 or newer (bugs 389,
  437-439).
- Leaving before the field has scored four half points in total (whether or
  not any became a full point) earns no rating, game gold or XP for that game,
  as the Info pages now say. The post-session report tells a failed connection
  apart from a chosen leave.

## 2V2 AND 1V2

- A 2v2 series with a disconnect is no longer settled automatically: reported
  games stand, rating and gold do not move, and an admin awards or voids the
  series. Disconnects are reported more reliably (bugs 384, 385).
- An abandoned 1v2 series closes after 14 days without a game, with no
  winner; the solo seat can no longer change mid-series; a decided game
  reported after a cancellation still pays its gold and XP.

## QUEUES AND CONNECTION

- The 1v1 ranked search opens to any rating after two minutes. 2v2, 1v2 and
  FFA rooms pick their region from every member's pings; ranked 1v1 rooms
  start from both players' home regions (bug 457) and can move to a shared
  region that cuts the pair's worst ping by over 20 ms. A corner notice warns
  you while the match connection is failing.

## SESSION REPORTS

- New builds pages (one block per game), four Totals pages and a score race in
  rounds won against the target; each game shows its gold, and its XP in 1v1
  and FFA.

## MAIL AND MUSIC

- Link your Discord account and new mail can also reach you there as a DM
  you can answer; the switch is in the mail settings.
- Custom music is quieter at the top of its slider and more even between
  tracks, and the first track after a silent menu fades in.

## PRIVACY AND LOGS

- Optional automatic log upload (Privacy & account, off by default) sends the
  bug-report bundle after a room you played in; turning consent off stops an
  upload under way. Log handling is updated; the bug-report form, log viewer
  and match history no longer stall the game.

## FIXES

- Attempted fixes: a Saw's effects stop once its target is dead;
  Lifestealer's range ring shows its real range. With everyone on 1.41.0, a
  shot as a round ends no longer leaves the gun on cooldown next round, poison
  lands the same on both screens (bugs 406, 407) and a dead player no longer
  shields a living one from a Saw.
- Your picked avatar shows at card pick and spawn, not the default face
  (bug 444). Esc closes chat and keeps your draft; switching accounts clears
  it (bugs 351, 382).
- The Recent Ranked Series page no longer goes blank over a name with a
  character the font lacks.
- Bet refunds return the exact stake, and one failed refund no longer blocks
  the rest. A chat filter word that is also a common name was removed.
- An oversized cosmetic upload states the exact limit; the Translate portal
  button checks the secure connection itself instead of asking for a restart.
- Tournament fixes: brackets for 9 to 15 players (with 9 to 14 the tournament
  could not lock); a withdrawal after the lock no longer stalls the bracket,
  and a match left with no players shows dashes in game; the bot's
  availability buttons act only for the account now linked to your Discord.
- New in the shop: the Demonic body colour and five community faces that
  need 1.41.0. Every client text that became translatable since 1.40.3
  (over a thousand, Demonic's shop text and the new card trading, mail
  relay and dance-reason texts among them) is in Spanish, Russian, Ukrainian
  and Swedish; eight Spanish labels that still showed English are fixed.$rn1410$, chr(13), ''), 'human', NULL)
    ON CONFLICT (tag, language_code) DO UPDATE
       SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
           translated_by = EXCLUDED.translated_by, updated_at = NOW()
     WHERE release_notes_i18n.body          IS DISTINCT FROM EXCLUDED.body
        OR release_notes_i18n.title         IS DISTINCT FROM EXCLUDED.title
        OR release_notes_i18n.source        IS DISTINCT FROM EXCLUDED.source
        OR release_notes_i18n.translated_by IS DISTINCT FROM EXCLUDED.translated_by;
    GET DIAGNOSTICS k = ROW_COUNT;
    w := w + k;

    INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
    VALUES ('v1.41.0', 'es', '', replace($rn1410$# v1.41.0

## PLAYER CARDS

- Player Cards: cartas coleccionables de quienes juegan aquí, en una nueva
  pestaña Colección (grupo Tienda). Sobres: un reclamo diario gratis, oro o
  fragmentos y, por azar, victorias ranked.
- Todo jugador no baneado que usó el mod en Steam tiene carta. La rareza es
  su puesto en el pool de cartas el día de la tirada (los dos primeros:
  Legendaria); toda carta puede salir además Foil o Firmada.
- Una carta muestra la foto pública de Steam del jugador hasta que su juego
  sube su personaje, ahora encuadrado sobre él: tu juego rehace y sube la
  tuya al abrir Player Cards por primera vez. Borrar tus datos elimina las
  cartas que te muestran.
- Fragmenta cartas una a una, en lote o desde la pestaña de apertura con
  Fragmentar duplicados; una carta obtenida por intercambio no da fragmentos
  y las descartadas quedan marcadas en tu historial de sobres. Intercambia en
  la nueva vista Intercambios; en los ajustes de Player Cards eliges si
  intercambias, si otros ven tus cartas y si tus tiradas raras salen en
  Discord.
- Baile en mi carta pone uno de tus bailes en tu carta, que nombra tu Top
  card con su arte; la fila de imagen de Ajustes muestra tu carta entera como
  la ven otros. Ordena el álbum por la posición actual de cada jugador; las
  ediciones rotan por calendario.
- En Discord, /pack y /binder muestran tus sobres y tu colección como
  imágenes, /daily abre tu sobre diario, /buypack compra uno con oro o
  fragmentos y /card muestra la carta entera de un jugador y publica su baile
  como GIF con su vista previa lista. El canal de clasificación lleva las
  tablas de 1v1, 2v2 y FFA; los torneos Sync usan una regla para quién vota
  el inicio.

## VOLVER A LA PARTIDA

- 2v2 y 1v2: si un jugador se cae, la partida lo espera en el siguiente
  punto; si no vuelve, la desconexión se trata como antes. Requiere a todos
  en la 1.41.0.
- FFA: la entrada tardía y la vuelta a mitad de partida (eligiendo cartas por
  quien falta) están activas en las salas FFA donde todos tienen la 1.41.0.

## ESCALERAS DE TÍTULOS

- Las escaleras de títulos pasan a Títulos (Tienda), cinco niveles cada una
  (clic para abrirlos); los títulos de hasta 16 caracteres se ven enteros en
  las tablas de FFA. Voidshot y Kingslayer se retiran y se reembolsan en oro.

## AJUSTES Y CONTROLES

- Controles: una nueva subpestaña Controles en Ajustes reasigna las teclas
  propias del mod y los controles del juego.
- Ajustes se rehace en ocho subpestañas de filas de una línea con panel de
  ayuda; todas menos Privacidad y cuenta vuelven a lo recomendado (Controles,
  a las teclas por defecto); con un mando se cambia de subpestaña y se pulsan
  filas.
- Números de daño y curación sobre los jugadores: No, Yo o Todos (No por
  defecto). Dos avatares por defecto: uno con mod donde todos lo tienen y uno
  vanilla para Quick Match y partidas con alguien sin mod; el juego lo cambia
  en esa sala y lo devuelve al salir.
- Un icono nuevo junto a Correo y Música abre el formulario de bugs; el pie
  de F5 gana un botón scrmod.com.

## REGLAS DE SALA

- Mismas cartas funciona en todos los modos (1v1 si ambos lo quieren, modos
  con anfitrión si este lo activa); los anfitriones de 2v2 y 1v2 pueden
  quitar el fuego amigo. Ambas reglas se fijan al crear la sala, se ven en
  una franja arriba y constan en todo historial (por partida en FFA) y
  resultado en Discord.

## FFA

- Un FFA ranked solo cuenta para el rating si todos usan la 1.41.0 o
  posterior. En esa sala el inicio espera a que se conecten todos; si uno no
  puede, la sala se rehace con el resto o se cierra antes de empezar.
- Con versiones distintas del mod, la elección de carta de cada uno vuelve a
  contar (bugs 435, 436). Intento de arreglo: Lifestealer vuelve a elegir
  objetivo en cada activación si todos usan la 1.41.0 o posterior (bugs 389,
  437-439).
- Irte antes de que el campo sume cuatro medios puntos en total, se hayan
  convertido o no en un punto completo, te deja sin rating, oro ni XP de esa
  partida, como ya dicen las páginas de Info. El informe tras la sesión
  distingue una conexión caída de una salida voluntaria.

## 2V2 Y 1V2

- Una serie 2v2 con una desconexión ya no se resuelve sola: las partidas
  reportadas se mantienen, rating y oro no cambian y un admin otorga o anula
  la serie. Las desconexiones se reportan con más fiabilidad (bugs 384, 385).
- Una serie 1v2 abandonada se cierra tras 14 días sin partidas, sin ganador;
  el asiento solo ya no cambia a mitad de serie; una partida decidida
  reportada tras una cancelación aún paga su oro y XP.

## COLAS Y CONEXIÓN

- La búsqueda ranked 1v1 se abre a cualquier rating tras dos minutos. Las
  salas 2v2, 1v2 y FFA eligen región con los pings de cada miembro; el 1v1
  ranked parte de las regiones de origen de ambos jugadores (bug 457) y puede
  pasar a una región común que baje el peor ping de la pareja en más de 20 ms.
  Un aviso en la esquina indica cuándo falla la conexión.

## INFORMES DE SESIÓN

- Nuevas páginas de builds (un bloque por partida), cuatro páginas de Totales
  y una carrera de puntos en rondas ganadas hacia el objetivo; cada partida
  muestra su oro, y su XP en 1v1 y FFA.

## CORREO Y MÚSICA

- Vincula tu cuenta de Discord y el correo nuevo te llegará también allí como
  DM que puedes responder; el interruptor está en los ajustes de correo.
- La música propia suena más baja en lo alto del control y más pareja entre
  pistas, y la primera pista tras un menú en silencio entra con fundido.

## PRIVACIDAD Y LOGS

- Subida automática de logs opcional (Privacidad y cuenta, apagada por
  defecto): tras cada sala jugada envía el paquete del formulario de bugs;
  retirar el consentimiento detiene la subida en curso. Se actualizó el
  tratamiento de logs; el formulario de bugs, el visor de logs y el historial
  ya no traban el juego.

## ARREGLOS

- Intentos de arreglo: los efectos de una Saw cesan al morir su objetivo; el
  anillo de Lifestealer muestra su alcance real. Con todos en la 1.41.0, un
  disparo al acabar una ronda ya no deja el arma en enfriamiento en la
  siguiente, el veneno llega igual en ambas pantallas (bugs 406, 407) y un
  jugador muerto ya no protege a uno vivo de una Saw.
- Tu avatar elegido se ve al elegir carta y al aparecer, no la cara por
  defecto (bug 444). Esc cierra el chat y guarda tu borrador; cambiar de
  cuenta lo borra (bugs 351, 382).
- La página de Series ranked recientes ya no sale en blanco por un nombre con
  un carácter que la fuente no tiene.
- Los reembolsos de apuestas son exactos, y uno fallido ya no bloquea los
  demás. Se quitó del filtro del chat una palabra que también es un nombre
  común.
- Una subida de cosmético excesiva indica el límite exacto; el botón del
  portal de traducción comprueba la conexión segura sin pedir un reinicio.
- Arreglos de torneo: cuadros de 9 a 15 jugadores (con 9 a 14 el torneo no
  podía cerrarse); una retirada tras el cierre ya no atasca el cuadro, y una
  partida sin jugadores muestra guiones en el juego; los botones de
  disponibilidad del bot solo valen para la cuenta vinculada ahora a tu
  Discord.
- Nuevo en la tienda: el color de cuerpo Demonic y cinco caras de la comunidad
  que requieren la 1.41.0. Cada texto del cliente que pasó a ser traducible
  tras la 1.40.3 (más de mil, entre ellos el de Demonic y los nuevos de
  intercambios, reenvío de correo y motivos de baile) está en español, ruso,
  ucraniano y sueco; ocho etiquetas en español que seguían en inglés ya están
  traducidas.$rn1410$, chr(13), ''), 'machine', 'claude-mt')
    ON CONFLICT (tag, language_code) DO UPDATE
       SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
           translated_by = EXCLUDED.translated_by, updated_at = NOW()
     WHERE release_notes_i18n.body          IS DISTINCT FROM EXCLUDED.body
        OR release_notes_i18n.title         IS DISTINCT FROM EXCLUDED.title
        OR release_notes_i18n.source        IS DISTINCT FROM EXCLUDED.source
        OR release_notes_i18n.translated_by IS DISTINCT FROM EXCLUDED.translated_by;
    GET DIAGNOSTICS k = ROW_COUNT;
    w := w + k;

    INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
    VALUES ('v1.41.0', 'ru', '', replace($rn1410$# v1.41.0

## PLAYER CARDS

- Player Cards: коллекционные карты людей, которые здесь играют, в новой
  вкладке «Коллекция» в группе «Магазин». Паки дают раз в день бесплатно, за
  золото или осколки и с шансом за рейтинговые победы.
- Карта есть у каждого незабаненного игрока, запускавшего мод в Steam.
  Редкость — место игрока в пуле карт в день вытягивания (у двух первых —
  легендарная), и любая карта может выпасть ещё фольгированной или
  подписанной.
- Карта показывает публичную аватарку Steam своего игрока, пока его игра не
  загрузит его персонажа. Картинка теперь кадрируется по самому персонажу,
  поэтому твоя игра сама перерисует и загрузит твою при первом открытии
  Player Cards. Удаление твоих данных убирает все карты с тобой.
- Превращай карты в осколки по одной, партией или прямо во вкладке открытия
  кнопкой «Разбить дубликаты»; карта, полученная в обмене, осколков не даёт, а
  сброшенные карты остаются с пометкой в истории паков. Обменивайся картами в
  новом разделе «Обмены»; переключатели в настройках Player Cards
  переключают обмен и решают, видят ли другие твои карты и можно ли
  публиковать твои редкие выпадения в Discord.
- «Танец на моей карте» показывает на твоей карте один из твоих танцев. Твоя
  Top card названа на лицевой стороне карты вместе с артом;
  строка картинки в «Настройках» показывает твою карту целиком, как её видят
  другие. Альбом сортируется по тому, где игрок с карты стоит сегодня; издания
  карт сменяются по расписанию.
- В Discord /pack и /binder показывают твои паки и коллекцию картинками,
  /daily открывает ежедневный пак, /buypack покупает пак за золото или
  осколки, а /card показывает карту игрока целиком и публикует её танец
  гифкой, когда превью готово. В канале лидерборда есть таблицы 1v1, 2v2 и
  FFA, а в турнирах Sync одно правило решает, кто голосует за старт.

## ВОЗВРАТ В ИГРУ

- 2v2 и 1v2: когда игрок выпадает, игра ждёт его на следующем очке; если он
  не вернётся, отключение обрабатывается как раньше. Нужно, чтобы у всех в
  комнате была 1.41.0.
- Поздний вход в FFA и возврат посреди игры (с автоматическим выбором карт за
  отсутствующего) включены в комнатах FFA, где у всех 1.41.0.

## ЛЕСТНИЦЫ ТИТУЛОВ

- Лестницы титулов теперь в разделе «Титулы» в «Магазине», по пять ступеней в
  каждой (нажми, чтобы открыть); титулы до 16 символов целиком видны в
  таблицах FFA. Титулы Voidshot и Kingslayer выведены, их цена возвращена
  золотом.

## НАСТРОЙКИ И УПРАВЛЕНИЕ

- Управление: новая подвкладка «Управление» в «Настройках» переназначает
  клавиши самого мода и управление игры.
- «Настройки» пересобраны в восемь подвкладок из однострочных строк с панелью
  справки; все, кроме «Приватность и аккаунт», сбрасываются к рекомендуемым
  значениям («Управление» — к клавишам по умолчанию); геймпадом можно
  переключать подвкладки и нажимать строки.
- Числа урона и лечения над игроками: Выкл, Я или Все (по умолчанию Выкл).
  Два аватара по умолчанию: модовый там, где мод есть у всех, и ванильный для
  Quick Match и игр с игроком без мода; игра переключает его на эту комнату и
  возвращает при выходе.
- Новая иконка рядом с «Почтой» и «Музыкой» открывает форму баг-репорта; в
  подвале F5 появилась кнопка scrmod.com.

## ПРАВИЛА КОМНАТЫ

- «Те же карты» работают во всех режимах (в 1v1, если оба игрока хотят, в
  режимах с хостом, если хост их включит); хосты 2v2 и 1v2 могут выключить
  огонь по своим. Оба правила закрепляются при создании комнаты, видны в
  полосе вверху и записываются во все истории (в FFA по каждой игре) и посты
  результатов в Discord.

## FFA

- Рейтинговый FFA идёт в рейтинг, только если у всех игроков 1.41.0 или
  новее. В такой комнате старт ждёт, пока игроки подключаются; если кто-то не
  может, лобби пересобирается из остальных или закрывается до начала матча.
- При игроках на разных версиях мода выбор карты каждого снова засчитывается
  (баги 435, 436). Попытка исправления: Lifestealer заново выбирает цель при
  каждой активации, если у всех 1.41.0 или новее (баги 389, 437-439).
- Уход до того, как поле наберёт в сумме четыре половины очка (ставшие полным
  очком или нет), не даёт за эту игру ни рейтинга, ни игрового золота, ни XP,
  как теперь сказано на страницах «Инфо». Отчёт после сессии отличает упавшее
  соединение от ухода по своей воле.

## 2V2 И 1V2

- Серия 2v2 с отключением больше не решается автоматически: засчитанные игры
  остаются, рейтинг и золото не меняются, а админ присуждает или аннулирует
  серию. Об отключениях сообщается надёжнее (баги 384, 385).
- Брошенная серия 1v2 закрывается через 14 дней без игр, без победителя;
  одиночное место больше не меняется посреди серии; решённая игра,
  сообщённая после отмены, всё равно платит золото и XP.

## ОЧЕРЕДИ И СОЕДИНЕНИЕ

- Поиск рейтингового 1v1 после двух минут открывается для любого рейтинга.
  Комнаты 2v2, 1v2 и FFA выбирают регион по пингам каждого участника;
  рейтинговый 1v1 стартует с домашних регионов обоих игроков (баг 457) и может
  перейти в общий регион, если тот снижает худший пинг пары больше чем на
  20 мс. Уведомление в углу предупреждает, пока соединение матча сбоит.

## ОТЧЁТЫ СЕССИЙ

- Новые страницы билдов (один блок на игру), четыре страницы итогов и гонка
  счёта в выигранных раундах против цели; каждая игра показывает своё золото,
  а в 1v1 и FFA ещё и XP.

## ПОЧТА И МУЗЫКА

- Привяжи аккаунт Discord, и новая почта будет приходить и туда личным
  сообщением, на которое можно ответить; переключатель в настройках почты.
- Своя музыка тише на максимуме ползунка и ровнее между треками, а первый трек
  после тихого меню плавно нарастает.

## ПРИВАТНОСТЬ И ЛОГИ

- Необязательная автозагрузка логов («Приватность и аккаунт», по умолчанию
  выключена) отправляет пакет формы баг-репорта после комнаты, где ты играл;
  отзыв согласия останавливает уже идущую загрузку. Обработка логов
  обновлена; форма баг-репорта, просмотр логов и история матчей больше не
  подвешивают игру.

## ИСПРАВЛЕНИЯ

- Попытки исправления: эффекты Saw прекращаются, когда её цель мертва; кольцо
  дальности Lifestealer показывает реальную дальность. Когда у всех 1.41.0,
  выстрел в самом конце раунда больше не оставляет оружие на перезарядке в
  следующем, урон ядом одинаков на обоих экранах (баги 406, 407), а мёртвый
  игрок больше не заслоняет от Saw живого.
- Выбранный аватар виден при выборе карты и появлении, а не лицо по
  умолчанию (баг 444). Esc закрывает чат и сохраняет черновик; смена аккаунта
  его стирает (баги 351, 382).
- Страница «Недавние рейтинговые серии» больше не пустеет из-за символа в
  имени, который шрифт не может нарисовать.
- Возврат ставок отдаёт точную сумму, и один неудачный возврат больше не
  блокирует остальные. Из фильтра чата убрано слово, совпадающее с
  распространённым именем.
- Слишком большая загрузка косметики называет точный лимит; кнопка портала
  переводов сама проверяет защищённое соединение вместо просьбы
  перезапуститься.
- Исправления турниров: сетки на 9-15 игроков (при 9-14 турнир не мог
  залочиться); выход после лока больше не стопорит сетку, а матч без игроков
  показан в игре прочерками; кнопки бота о доступности работают только для
  аккаунта, сейчас привязанного к твоему Discord.
- Новое в магазине: цвет тела Demonic и пять лиц от сообщества, которым
  нужна 1.41.0. Каждый текст клиента, ставший доступным для перевода
  после 1.40.3 (более тысячи, включая текст Demonic и новые тексты обмена
  картами, пересылки почты и причин танца), переведён на испанский,
  русский, украинский и шведский; восемь испанских подписей, оставшихся
  на английском, исправлены.$rn1410$, chr(13), ''), 'machine', 'claude-mt')
    ON CONFLICT (tag, language_code) DO UPDATE
       SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
           translated_by = EXCLUDED.translated_by, updated_at = NOW()
     WHERE release_notes_i18n.body          IS DISTINCT FROM EXCLUDED.body
        OR release_notes_i18n.title         IS DISTINCT FROM EXCLUDED.title
        OR release_notes_i18n.source        IS DISTINCT FROM EXCLUDED.source
        OR release_notes_i18n.translated_by IS DISTINCT FROM EXCLUDED.translated_by;
    GET DIAGNOSTICS k = ROW_COUNT;
    w := w + k;

    INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
    VALUES ('v1.41.0', 'uk', '', replace($rn1410$# v1.41.0

## PLAYER CARDS

- Player Cards: колекційні картки людей, які тут грають, у новій вкладці
  «Колекція» в групі «Магазин». Паки дають раз на день безплатно, за золото
  або уламки і з шансом за рейтингові перемоги.
- Картка є в кожного гравця без бану, який запускав мод у Steam. Рідкість —
  місце гравця в пулі карток у день витягування (у двох перших —
  легендарна), і будь-яка картка може випасти ще й фольгованою або
  підписаною.
- Картка показує публічне фото Steam свого гравця, доки його гра не
  завантажить його персонажа. Зображення тепер кадрується за самим
  персонажем, тож ваша гра сама перемалює й завантажить ваше, коли ви
  вперше відкриєте Player Cards. Видалення ваших даних прибирає всі картки з
  вами.
- Перетворюйте картки на уламки по одній, партією або просто у вкладці
  відкриття кнопкою «Розбити дублікати»; картка, отримана в обміні, уламків не
  дає, а скинуті картки лишаються з позначкою в історії паків. Обмінюйтеся
  картками в новому розділі «Обміни»; перемикачі в налаштуваннях Player Cards
  перемикають обмін і вирішують, чи бачать інші ваші картки і чи можна
  публікувати ваші рідкісні випадіння в Discord.
- «Танець на моїй картці» показує на вашій картці один із ваших танців. Ваша
  Top card названа на лицьовому боці картки разом з артом; рядок
  зображення в «Налаштуваннях» показує вашу картку повністю, як її бачать
  інші. Альбом сортується за тим, де гравець з картки стоїть сьогодні; видання
  карток змінюються за розкладом.
- У Discord /pack і /binder показують ваші паки й колекцію зображеннями,
  /daily відкриває щоденний пак, /buypack купує пак за золото або уламки, а
  /card показує картку гравця повністю й публікує її танець гіфкою, коли
  прев'ю готове. У каналі лідерборду є таблиці 1v1, 2v2 і FFA, а в турнірах
  Sync одне правило вирішує, хто голосує за старт.

## ПОВЕРНЕННЯ В ГРУ

- 2v2 і 1v2: коли гравець випадає, гра чекає на нього на наступному очку;
  якщо він не повернеться, відключення обробляється як раніше. Потрібно, щоб
  у всіх у кімнаті була 1.41.0.
- Пізній вхід у FFA і повернення посеред гри (з автоматичним вибором карток за
  відсутнього) увімкнені в кімнатах FFA, де в усіх 1.41.0.

## ДРАБИНИ ТИТУЛІВ

- Драбини титулів тепер у розділі «Титули» в «Магазині», по п'ять щаблів у
  кожній (натисніть, щоб відкрити); титули до 16 символів повністю видно в
  таблицях FFA. Титули Voidshot і Kingslayer виведено, їхню ціну повернуто
  золотом.

## НАЛАШТУВАННЯ Й КЕРУВАННЯ

- Керування: нова підвкладка «Керування» в «Налаштуваннях» перепризначає
  клавіші самого мода й керування гри.
- «Налаштування» перебудовано у вісім підвкладок з однорядкових рядків з
  панеллю довідки; усі, крім «Приватність і акаунт», скидаються до
  рекомендованих значень («Керування» — до типових клавіш); геймпадом можна
  перемикати підвкладки й натискати рядки.
- Числа шкоди й лікування над гравцями: Вимк, Я або Усі (типово Вимк). Два
  типові аватари: модовий там, де мод є в усіх, і ванільний для Quick Match та
  ігор із гравцем без мода; гра перемикає його на цю кімнату й повертає при
  виході.
- Нова іконка поруч із «Поштою» та «Музикою» відкриває форму баг-репорту; у
  підвалі F5 з'явилася кнопка scrmod.com.

## ПРАВИЛА КІМНАТИ

- «Ті самі карти» працюють у всіх режимах (в 1v1, якщо обидва гравці хочуть,
  у режимах із хостом, якщо хост їх увімкне); хости 2v2 і 1v2 можуть вимкнути
  вогонь по своїх. Обидва правила закріплюються під час створення кімнати,
  видні в смузі вгорі й записуються в усі історії (у FFA по кожній грі) та
  дописи результатів у Discord.

## FFA

- Рейтинговий FFA йде в рейтинг, лише якщо в усіх гравців 1.41.0 або
  новіша. У такій кімнаті старт чекає, поки гравці підключаються; якщо хтось
  не може, лобі перебудовується з рештою або закривається до початку матчу.
- За гравців на різних версіях мода вибір картки кожного знову зараховується
  (баги 435, 436). Спроба виправлення: Lifestealer заново вибирає ціль за
  кожної активації, якщо в усіх 1.41.0 або новіша (баги 389, 437-439).
- Вихід до того, як поле набере загалом чотири половинки очка (що стали повним
  очком чи ні), не дає за цю гру ні рейтингу, ні ігрового золота, ні XP, як
  тепер сказано на сторінках «Інфо». Звіт після сесії відрізняє обірване
  з'єднання від виходу з власної волі.

## 2V2 І 1V2

- Серія 2v2 з відключенням більше не вирішується автоматично: зараховані ігри
  лишаються, рейтинг і золото не змінюються, а адмін присуджує або анулює
  серію. Про відключення повідомляється надійніше (баги 384, 385).
- Покинута серія 1v2 закривається через 14 днів без ігор, без переможця;
  одиночне місце більше не змінюється посеред серії; вирішена гра,
  повідомлена після скасування, однаково платить золото й XP.

## ЧЕРГИ Й З'ЄДНАННЯ

- Пошук рейтингового 1v1 після двох хвилин відкривається для будь-якого
  рейтингу. Кімнати 2v2, 1v2 і FFA обирають регіон за пінгами кожного
  учасника; рейтинговий 1v1 стартує з домашніх регіонів обох гравців (баг 457)
  і може перейти в спільний регіон, якщо той знижує найгірший пінг пари більш
  ніж на 20 мс. Сповіщення в куті попереджає, поки з'єднання матчу збоїть.

## ЗВІТИ СЕСІЇ

- Нові сторінки білдів (один блок на гру), чотири сторінки підсумків і
  перегони рахунку у виграних раундах проти мети; кожна гра показує своє
  золото, а в 1v1 і FFA ще й XP.

## ПОШТА Й МУЗИКА

- Прив'яжіть акаунт Discord, і нова пошта надходитиме й туди особистим
  повідомленням, на яке можна відповісти; перемикач у налаштуваннях пошти.
- Власна музика тихіша на максимумі повзунка й рівніша між треками, а перший
  трек після тихого меню плавно наростає.

## ПРИВАТНІСТЬ І ЛОГИ

- Необов'язкове автозавантаження логів («Приватність і акаунт», типово
  вимкнене) надсилає пакет форми баг-репорту після кімнати, де ви грали;
  відкликання згоди зупиняє вже розпочате завантаження. Обробку логів
  оновлено; форма баг-репорту, перегляд логів та історія матчів більше не
  підвішують гру.

## ВИПРАВЛЕННЯ

- Спроби виправлення: ефекти Saw припиняються, коли її ціль мертва; кільце
  дальності Lifestealer показує справжню дальність. Коли в усіх 1.41.0,
  постріл у самому кінці раунду більше не лишає зброю на перезарядці в
  наступному, шкода від отрути однакова на обох екранах (баги 406, 407), а
  мертвий гравець більше не затуляє від Saw живого.
- Вибраний аватар видно під час вибору картки й появи, а не типове обличчя
  (баг 444). Esc закриває чат і зберігає чернетку; зміна акаунта її стирає
  (баги 351, 382).
- Сторінка «Нещодавні рейтингові серії» більше не порожніє через символ в
  імені, який шрифт не може намалювати.
- Повернення ставок віддає точну суму, і одне невдале повернення більше не
  блокує решту. З фільтра чату прибрано слово, що збігається з поширеним
  іменем.
- Завелике завантаження косметики називає точний ліміт; кнопка порталу
  перекладів сама перевіряє захищене з'єднання замість прохання
  перезапуститися.
- Виправлення турнірів: сітки на 9-15 гравців (при 9-14 турнір не міг
  зафіксуватися); вихід після фіксації більше не зупиняє сітку, а матч без
  гравців показано в грі прочерками; кнопки бота щодо доступності діють лише
  для акаунта, зараз прив'язаного до вашого Discord.
- Нове в магазині: колір тіла Demonic і п'ять облич від спільноти, яким
  потрібна 1.41.0. Кожен текст клієнта, що став доступним для перекладу
  після 1.40.3 (понад тисячу, зокрема текст Demonic і нові тексти обміну
  картками, пересилання пошти та причин танцю), перекладено іспанською,
  російською, українською та шведською; вісім іспанських підписів, що
  лишалися англійською, виправлено.$rn1410$, chr(13), ''), 'machine', 'claude-mt')
    ON CONFLICT (tag, language_code) DO UPDATE
       SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
           translated_by = EXCLUDED.translated_by, updated_at = NOW()
     WHERE release_notes_i18n.body          IS DISTINCT FROM EXCLUDED.body
        OR release_notes_i18n.title         IS DISTINCT FROM EXCLUDED.title
        OR release_notes_i18n.source        IS DISTINCT FROM EXCLUDED.source
        OR release_notes_i18n.translated_by IS DISTINCT FROM EXCLUDED.translated_by;
    GET DIAGNOSTICS k = ROW_COUNT;
    w := w + k;

    INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
    VALUES ('v1.41.0', 'sv', '', replace($rn1410$# v1.41.0

## PLAYER CARDS

- Player Cards: samlarkort med folket som spelar här, i en ny Samling-flik i
  Butik-gruppen. Paket får du gratis varje dag, för guld eller skärvor och med
  en chans vid rankade vinster.
- Varje spelare som inte är bannad och har kört modden på Steam har ett kort.
  Sällsyntheten är spelarens plats i kortpoolen den dag kortet dras (de två
  översta är legendariska), och alla kort kan också komma ut som Foil eller
  Signerade.
- Ett kort visar spelarens offentliga Steam-bild tills hens spel laddat upp
  hens karaktär. Bilden ramas nu in kring själva karaktären, så ditt spel
  ritar om och laddar upp din av sig självt första gången du öppnar Player
  Cards. Raderar du dina data försvinner alla kort av dig.
- Gör kort till skärvor ett i taget, i en omgång eller från dragfliken med
  Dubbletter till skärvor; ett kort du fått i ett byte ger inga skärvor, och
  kastade kort står kvar, märkta, i din pakethistorik. Byt kort i den nya vyn
  Byten; brytare i Player Cards-inställningarna slår på eller av byten och
  väljer om andra ser dina kort och om dina sällsynta dragningar får läggas
  upp i Discord.
- Dans på mitt kort spelar upp en av dina danser på ditt kort. Ditt Top card
  står namngivet på kortets framsida med sin bild; bildraden i Inställningar
  visar hela ditt kort så som andra ser det. Sortera pärmen efter var varje
  spelare står i dag; kortutgåvor byts enligt ett schema.
- I Discord visar /pack och /binder dina paket och din samling som bilder,
  /daily öppnar ditt dagliga paket, /buypack köper ett för guld eller skärvor,
  och /card visar en spelares hela kort och lägger upp dess dans som en GIF
  när förhandsvisningen är klar. Topplistekanalen har tavlorna för 1v1, 2v2
  och FFA, och i Sync-turneringar avgör en regel vem som får rösta om start.

## ÅTERANSLUTNING

- 2v2 och 1v2: när en spelare faller bort väntar matchen på hen vid nästa
  poäng; kommer hen inte tillbaka hanteras frånkopplingen som förut. Kräver
  att alla i rummet kör 1.41.0.
- Sen anslutning till FFA och återinsläpp mitt i en match (kortvalen görs åt
  den som är borta) är påslagna i FFA-rum där alla kör 1.41.0.

## TITELSTEGAR

- Titelstegarna ligger nu i Butikens Titlar-sektion, fem nivåer var (klicka
  för att öppna); titlar på upp till 16 tecken syns hela på FFA-tavlorna.
  Titlarna Voidshot och Kingslayer har tagits bort och återbetalats i guld.

## INSTÄLLNINGAR OCH KONTROLLER

- Kontroller: en ny Kontroller-underflik i Inställningar binder om moddens
  egna tangenter och spelets kontroller.
- Inställningar är ombyggt till åtta underflikar med rader på en rad var och
  en hjälppanel; alla utom Integritet & konto återställs till rekommenderade
  värden (Kontroller till standardtangenterna); en handkontroll kan byta
  underflik och trycka på rader.
- Skade- och läkningssiffror ovanför spelarna: Av, Jag eller Alla (Av som
  standard). Två standardavatarer: en moddad där alla har modden och en
  vanilj för Quick Match och matcher med någon utan modden; spelet byter för
  det rummet och byter tillbaka när du lämnar.
- En ny ikon bredvid Post och Musik öppnar buggrapportformuläret; F5-sidfoten
  får en scrmod.com-knapp.

## RUMSREGLER

- Samma kort fungerar i alla lägen (i 1v1 när båda spelarna vill, i lägen med
  värd när värden slår på det); värdar för 2v2 och 1v2 kan stänga av
  vänskaplig eld. Båda reglerna fastställs när rummet skapas, visas i en
  remsa högst upp och sparas i varje historik (per match i FFA) och
  resultatinlägg i Discord.

## FFA

- En rankad FFA räknas till rating bara när alla spelare kör 1.41.0 eller
  nyare. I ett sådant rum väntar starten medan spelarna ansluter; om någon
  inte kan ansluta byggs lobbyn om med resten eller stängs före matchen.
- Med spelare på olika moddversioner räknas allas kortval igen
  (buggar 435, 436). Försök till fix: Lifestealer väljer om sitt mål varje
  gång den aktiveras, om alla kör 1.41.0 eller nyare (buggar 389, 437-439).
- Lämnar du innan fältet fått fyra halvpoäng sammanlagt, oavsett om någon
  blivit en hel poäng, ger matchen ingen rating, inget matchguld och ingen XP,
  som Info-sidorna nu säger. Rapporten efter sessionen skiljer en bruten
  anslutning från en spelare som valde att gå.

## 2V2 OCH 1V2

- En 2v2-serie med en frånkoppling avgörs inte längre automatiskt:
  rapporterade matcher står kvar, rating och guld ändras inte, och en admin
  tilldelar eller ogiltigförklarar serien. Frånkopplingar rapporteras mer
  tillförlitligt (buggar 384, 385).
- En övergiven 1v2-serie stängs efter 14 dagar utan match, utan vinnare;
  soloplatsen kan inte längre bytas mitt i serien; en avgjord match som
  rapporteras efter att serien ställts in betalar ändå sitt guld och sin XP.

## KÖER OCH ANSLUTNING

- Rankad 1v1-sökning öppnas för alla ratingar efter två minuter. 2v2-, 1v2-
  och FFA-rum väljer region utifrån varje medlems pingar; rankad 1v1 utgår
  från båda spelarnas hemregioner (bugg 457) och kan flytta till en gemensam
  region som sänker parets sämsta ping med mer än 20 ms. En hörnnotis varnar
  dig medan matchanslutningen fallerar.

## SESSIONSRAPPORTER

- Nya build-sidor (ett block per match), fyra Totalt-sidor och en
  poängkapplöpning i vunna rundor mot vinstmålet; varje match visar sitt guld,
  och sin XP i 1v1 och FFA.

## POST OCH MUSIK

- Koppla ditt Discord-konto så kan ny post också nå dig där som ett DM som du
  kan svara på; brytaren finns i postinställningarna.
- Egen musik är tystare högst upp på reglaget och jämnare mellan spåren, och
  första spåret efter en tyst meny tonas in.

## INTEGRITET OCH LOGGAR

- Valfri automatisk logguppladdning (Integritet & konto, av som standard)
  skickar buggrapportformulärets paket efter ett rum du spelade i; drar du
  tillbaka samtycket stoppas en pågående uppladdning. Logghanteringen är
  uppdaterad; buggformuläret, loggvisaren och matchhistoriken låser inte
  längre spelet.

## FIXAR

- Försök till fix: en Saws effekter slutar när dess mål är dött;
  Lifestealers räckviddsring visar sin verkliga räckvidd. När alla kör 1.41.0
  lämnar ett skott i slutet av en runda inte längre vapnet på nedkylning i
  nästa, giftskada landar likadant på båda skärmarna (buggar 406, 407) och en
  död spelare skyddar inte längre en levande från en Saw.
- Din valda avatar syns vid kortval och när du dyker upp, inte
  standardansiktet (bugg 444). Esc stänger chatten och sparar ditt utkast;
  byter du konto rensas det (buggar 351, 382).
- Sidan Senaste rankade serier blir inte längre tom av ett namn med ett tecken
  som typsnittet saknar.
- Återbetalda insatser ger tillbaka exakt belopp, och en misslyckad
  återbetalning stoppar inte längre de andra. Ett chattfilterord som också är
  ett vanligt namn är borttaget.
- En för stor kosmetikuppladdning anger den exakta gränsen;
  översättningsportalens knapp kontrollerar själv den säkra anslutningen i
  stället för att be om omstart.
- Turneringsrättelser: träd för 9 till 15 spelare (med 9 till 14 kunde
  turneringen inte låsas); ett uttag efter låsningen stoppar inte längre
  trädet, och en match utan spelare visas med streck i spelet; botens
  tillgänglighetsknappar gäller bara kontot som nu är länkat till din Discord.
- Nytt i butiken: kroppsfärgen Demonic och fem ansikten från communityn som
  kräver 1.41.0. Varje klienttext som blivit översättningsbar sedan 1.40.3
  (över tusen, bland dem Demonics text och de nya texterna för kortbyte,
  vidarebefordran av post och dansorsaker) finns på spanska, ryska, ukrainska
  och svenska; åtta spanska etiketter som fortfarande visade engelska är
  rättade.$rn1410$, chr(13), ''), 'machine', 'claude-mt')
    ON CONFLICT (tag, language_code) DO UPDATE
       SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
           translated_by = EXCLUDED.translated_by, updated_at = NOW()
     WHERE release_notes_i18n.body          IS DISTINCT FROM EXCLUDED.body
        OR release_notes_i18n.title         IS DISTINCT FROM EXCLUDED.title
        OR release_notes_i18n.source        IS DISTINCT FROM EXCLUDED.source
        OR release_notes_i18n.translated_by IS DISTINCT FROM EXCLUDED.translated_by;
    GET DIAGNOSTICS k = ROW_COUNT;
    w := w + k;

    SELECT COUNT(*) INTO n FROM release_notes_i18n
     WHERE tag = 'v1.41.0' AND language_code IN ('en','es','ru','uk','sv')
       AND length(body) > 500;
    IF n <> 5 THEN
        RAISE EXCEPTION 'post-check FAILED: % of 5 v1.41.0 locales stored with a real body (migration 392)', n;
    END IF;
    -- MarkdownToTmp adds 25 characters to a top-level bullet line, at most 44
    -- to a heading line and nothing else; inline markup or an indented bullet
    -- would add more, so a body carrying either is refused, not estimated.
    SELECT COUNT(*) INTO c FROM release_notes_i18n
     WHERE tag = 'v1.41.0' AND language_code IN ('en','es','ru','uk','sv')
       AND (length(body) + 25 * regexp_count(body, '^[-+] ', 1, 'n')
                         + 44 * regexp_count(body, '^#', 1, 'n') > 9000
            OR body ~ '[*`]'
            OR position('__' IN body) > 0
            OR body ~ '\n[ \t]+[-+] ');
    IF c <> 0 THEN
        RAISE EXCEPTION 'post-check FAILED: % v1.41.0 bodies can render past the client''s 9000-character cut (migration 392)', c;
    END IF;
    SELECT COUNT(*) INTO p FROM release_notes_i18n
     WHERE tag = 'v1.41.0'
       AND (position('[Q8 KEYBINDS' || ' LINE' IN body) > 0
            OR position('DRAFT FOR THE' || ' INTEGRATOR' IN body) > 0
            OR position('[SHIP' || ' DATE]' IN body) > 0
            OR position('<!' || '--' IN body) > 0);
    IF p <> 0 THEN
        RAISE EXCEPTION 'post-check FAILED: % v1.41.0 bodies still hold a placeholder or a draft marker (migration 392)', p;
    END IF;
    RAISE NOTICE 'migration 392 wrote % of the 5 v1.41.0 rows', w;
    RAISE NOTICE 'post-check OK: all 5 v1.41.0 release-note locales stored, no placeholder left (migration 392)';
END $m392$;

COMMIT;
