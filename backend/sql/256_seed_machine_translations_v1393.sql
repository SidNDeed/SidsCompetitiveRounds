-- 256_seed_machine_translations_v1393.sql
--
-- Machine-translated proposal seeds (es/ru/uk/sv) for the 76 client keys
-- that had none: the Aug 23 Info-library batch (migration 251's 68 keys,
-- whose seeding was deferred at ship) and the v1.39.3 batch (253's 8).
-- 73 keys x 4 languages are fresh agent drafts validated against the
-- mirrored rules (tag-sequence, holes, length, cross-ref/title
-- consistency - the in-game hyperlink matcher literally compares these);
-- the 3 mute keys reuse their I18nCatalogues.cs bundled translations
-- VERBATIM so portal and client can never disagree.
--
-- Same contract as 184/189/213/223/239/249: PENDING proposals only,
-- sentinel proposer 'claude-mt', license_assent TRUE at machine terms rev.
-- Hash-joined so a seed whose English changed inserts NOTHING (213's
-- rule). Explicit BEGIN/COMMIT (#340); idempotent for the wrapper's ||
-- re-run (#243). NOT bundled client-side this release (v1.39.3 already
-- shipped): approvals reach players live via the pack overlay; bundling
-- rides the next release's catalogue regen.
BEGIN;

CREATE TEMP TABLE _seed256 (
  key_id      VARCHAR(16) NOT NULL,
  lang        VARCHAR(8)  NOT NULL,
  source_hash VARCHAR(40) NOT NULL,
  target      TEXT        NOT NULL
) ON COMMIT DROP;

INSERT INTO _seed256 (key_id, lang, source_hash, target) VALUES
    ('04753f943853fd1f', 'es', '13ec3760f87bc6150209123ec11bdef4b9363e74', $s256$Tienda y cosméticos$s256$)
  , ('04753f943853fd1f', 'ru', '13ec3760f87bc6150209123ec11bdef4b9363e74', $s256$Магазин и косметика$s256$)
  , ('04753f943853fd1f', 'sv', '13ec3760f87bc6150209123ec11bdef4b9363e74', $s256$Butik & kosmetik$s256$)
  , ('04753f943853fd1f', 'uk', '13ec3760f87bc6150209123ec11bdef4b9363e74', $s256$Магазин і косметика$s256$)
  , ('06906a07a445cfbd', 'es', 'd217db06d210b8c6c176928e820ebe2d83c720dd', $s256$Movimiento y técnicas de escudo$s256$)
  , ('06906a07a445cfbd', 'ru', 'd217db06d210b8c6c176928e820ebe2d83c720dd', $s256$Движение и техника щита$s256$)
  , ('06906a07a445cfbd', 'sv', 'd217db06d210b8c6c176928e820ebe2d83c720dd', $s256$Rörelse & sköldteknik$s256$)
  , ('06906a07a445cfbd', 'uk', 'd217db06d210b8c6c176928e820ebe2d83c720dd', $s256$Рух і техніка щита$s256$)
  , ('09a7675c5e72711f', 'es', 'f530ca4de09a53c8c6516e772d8aff7afabe8644', $s256$Sid's Competitive Rounds añade una capa competitiva completa a ROUNDS: 1v1, 2v2 y todos contra todos en ranked con sus propios ratings Glicko-2 (más una beta 1v2, registrada pero sin rating por ahora), una economía de XP y Oro con tienda de cosméticos, torneos semanales, apuestas en vivo sobre las partidas, logros e integración con Discord. Todo está construido y gestionado por la comunidad.

<color=#FFD94D><b>LAS DOS GARANTÍAS</b></color>

Dos reglas se cumplen en todas partes, y el mod entero está diseñado alrededor de ellas:

- <color=#7FE87F>Un jugador sin mod siempre recibe gameplay vanilla puro.</color> Los cambios de sala completa (la normalización de Grow, las funciones del motor FFA) se apagan solos salvo que cada combatiente lleve una copia actual del mod - un cliente vanilla o desactualizado significa reglas vanilla para todos, idénticas - y el arreglo del veneno sigue al jugador envenenado, así que una víctima sin mod conserva el veneno vanilla.
- <color=#7FE87F>Lo único del mod que un rival sin mod puede llegar a ver es el estilo del nombre.</color>

Dos matices, detallados en <color=#7FD4FF>Vanilla sigue siendo vanilla</color>: las protecciones contra crashes están siempre activas (reparan estados que vanilla nunca pretendió - un bloqueo muerto, un input congelado - y no cambian ninguna regla), y entre jugadores TODOS con mod, actualizados y con Ranked activado, los arreglos de equidad del veneno y de Grow se aplican incluso en quickplay y códigos de sala.

<color=#FFD94D><b>CÓMO FUNCIONA ESTA BIBLIOTECA</b></color>

La columna de la izquierda lista todos los artículos, agrupados por categoría. Haz clic en un tema y se abre en este panel. Los nombres en azul como (ver <color=#7FD4FF>Bloqueo</color>) apuntan a otros artículos de la misma lista. <color=#8A8A93>Todo este menú es F5. T abre el chat del juego y Esc cierra el menú.</color>

<color=#FFD94D><b>DÓNDE PEDIR AYUDA</b></color>

- <color=#7FD4FF>Discord</color> - el botón de Discord al pie de este menú abre el servidor de la comunidad. Allí responden personas reales, y también el bot del servidor - pregúntale cosas como 'cómo funciona el ranked' o 'cómo consigo oro' y contesta por su cuenta.
- <color=#7FD4FF>Reportes de bugs</color> - en la pestaña Ajustes, busca 'Reportar un bug' y pulsa Abrir formulario. Puedes adjuntar los logs del juego (un botón de Vista previa muestra exactamente qué se envía), tienes hasta 10 reportes al día y, si tu cuenta de Discord está vinculada, las respuestas del equipo llegan por MD.

Si algo se ve mal en plena partida, envía el reporte justo después de esa sesión - el log adjunto suele ser lo que permite encontrar el bug.$s256$)
  , ('09a7675c5e72711f', 'ru', 'f530ca4de09a53c8c6516e772d8aff7afabe8644', $s256$Sid's Competitive Rounds добавляет в ROUNDS полноценный соревновательный слой: рейтинговые 1v1, 2v2 и «все против всех» со своими рейтингами Glicko-2 (плюс бета 1v2 - записывается, но пока без рейтинга), экономику XP и золота с магазином косметики, еженедельные турниры, живые ставки на матчи, достижения и интеграцию с Discord. Всё это построено сообществом и живёт силами сообщества.

<color=#FFD94D><b>ДВЕ ГАРАНТИИ</b></color>

Два правила действуют везде, и весь мод построен вокруг них:

- <color=#7FE87F>Игрок без мода всегда получает чистый ванильный геймплей.</color> Изменения на всю комнату (нормализация Grow, движок FFA) сами себя выключают, если хоть один боец не на актуальной копии мода: один ванильный или устаревший клиент - ванильные правила для всех, одинаково; а фикс яда следует за отравленным игроком, так что жертва без мода сохраняет ванильный яд.
- <color=#7FE87F>Единственное, что соперник без мода вообще может увидеть от мода, - это стиль твоего неймтега.</color>

Два нюанса, расписанные в <color=#7FD4FF>Ваниль остаётся ванилью</color>: защита от крашей включена всегда (она чинит состояния, которых ваниль не задумывала, - мёртвый блок, замёрзший ввод - и не меняет ни одного правила), а между игроками, у которых у ВСЕХ стоит актуальный мод и включён Ranked, фиксы честности для яда и Grow работают даже в quickplay и комнатах по коду.

<color=#FFD94D><b>КАК УСТРОЕНА ЭТА БИБЛИОТЕКА</b></color>

Колонка слева перечисляет все статьи по категориям. Кликни тему - и она откроется в этой панели. Синие названия вроде (см. <color=#7FD4FF>Блокирование</color>) ведут к другим статьям того же списка. <color=#8A8A93>Всё это меню - F5. T открывает внутриигровой чат, Esc закрывает меню.</color>

<color=#FFD94D><b>ГДЕ ПОЛУЧИТЬ ПОМОЩЬ</b></color>

- <color=#7FD4FF>Discord</color> - кнопка Discord внизу этого меню открывает сервер сообщества. Там отвечают живые люди - и бот сервера тоже: спроси его «как работает рейтинг» или «как получить золото», и он ответит сам.
- <color=#7FD4FF>Репорты багов</color> - на вкладке Настройки найди «Репорт бага» и нажми «Открыть форму репорта». Можно приложить логи игры (кнопка предпросмотра показывает ровно то, что уйдёт), лимит - до 10 репортов в день, а если твой Discord привязан, ответы команды приходят в ЛС.

Если посреди матча что-то выглядит сломанным, отправь репорт сразу после той сессии - обычно именно приложенный лог делает баг находимым.$s256$)
  , ('09a7675c5e72711f', 'sv', 'f530ca4de09a53c8c6516e772d8aff7afabe8644', $s256$Sid's Competitive Rounds lägger ett komplett tävlingslager ovanpå ROUNDS: ranked 1v1, 2v2 och alla-mot-alla med egna Glicko-2-ratingar (plus en 1v2-beta som registreras men ännu inte rankas), en XP- och guldekonomi med kosmetikbutik, veckoturneringar, livevadslagning på matcher, prestationer och Discord-integration. Alltihop är byggt och drivet av communityn.

<color=#FFD94D><b>DE TVÅ GARANTIERNA</b></color>

Två regler gäller överallt, och hela modden är byggd kring dem:

- <color=#7FE87F>En spelare utan modden får alltid ren vanilla-gameplay.</color> Ändringar som gäller hela rummet (Grow-normaliseringen, FFA-motorns funktioner) stänger av sig själva om inte varje fighter kör en aktuell kopia av modden - en enda vanilla- eller föråldrad klient betyder vanilla-regler för alla, identiskt - och giftfixen följer den förgiftade spelaren, så ett omoddat offer behåller vanilla-gift.
- <color=#7FE87F>Det enda en motståndare utan modden någonsin kan se av modden är namnskyltsstil.</color>

Två nyanser, utskrivna i <color=#7FD4FF>Vanilla förblir vanilla</color>: kraschskydden är alltid på (de reparerar tillstånd som vanilla aldrig avsåg - ett dött block, en frusen input - och ändrar ingen regel), och mellan spelare som ALLA är moddade, aktuella och har samtyckt till Ranked gäller rättvisefixarna för gift och Grow även i quickplay och rumskoder.

<color=#FFD94D><b>SÅ FUNGERAR BIBLIOTEKET</b></color>

Kolumnen till vänster listar varje artikel, grupperad per kategori. Klicka på ett ämne så öppnas det i den här rutan. Blå namn som (se <color=#7FD4FF>Blockering</color>) pekar på andra artiklar i samma lista. <color=#8A8A93>Hela den här menyn är F5. T öppnar chatten i spelet, och Esc stänger menyn.</color>

<color=#FFD94D><b>VAR DU FÅR HJÄLP</b></color>

- <color=#7FD4FF>Discord</color> - Discord-knappen längst ner i den här menyn öppnar communityservern. Riktiga människor svarar på frågor där, och det gör serverbotten också - fråga den saker som 'hur funkar ranked' eller 'hur får jag guld' så svarar den på egen hand.
- <color=#7FD4FF>Buggrapporter</color> - på fliken Inställningar, hitta 'Rapportera en bugg' och tryck på Öppna rapportformulär. Du kan bifoga dina spelloggar (en förhandsgranskningsknapp visar exakt vad som skickas), du får upp till 10 rapporter per dag, och om ditt Discord-konto är länkat kommer teamets svar som DM.

Om något ser fel ut mitt i en match, skicka rapporten direkt efter den sessionen - den bifogade loggen är oftast det som gör en bugg hittbar.$s256$)
  , ('09a7675c5e72711f', 'uk', 'f530ca4de09a53c8c6516e772d8aff7afabe8644', $s256$Sid's Competitive Rounds додає до ROUNDS повноцінний змагальний шар: рейтингові 1v1, 2v2 і «кожен сам за себе» з власними рейтингами Glicko-2 (плюс бета 1v2 - записується, але поки без рейтингу), економіку XP і золота з магазином косметики, щотижневі турніри, живі ставки на матчі, досягнення та інтеграцію з Discord. Усе це створено спільнотою і працює силами спільноти.

<color=#FFD94D><b>ДВІ ГАРАНТІЇ</b></color>

Два правила діють скрізь, і весь мод побудовано навколо них:

- <color=#7FE87F>Гравець без мода завжди отримує чистий ванільний геймплей.</color> Зміни на всю кімнату (нормалізація Grow, можливості рушія FFA) самі вимикаються, якщо не кожен боєць має актуальну копію мода - один ванільний чи застарілий клієнт означає ванільні правила для всіх, однаково - а виправлення отрути йде за отруєним гравцем, тож жертва без мода зберігає ванільну отруту.
- <color=#7FE87F>Єдине, що суперник без мода може взагалі побачити від мода, - стилізація неймтега.</color>

Два нюанси, розписані у <color=#7FD4FF>Ваніль лишається ваніллю</color>: захист від крашів увімкнений завжди (він лагодить стани, яких ваніль не задумувала, - мертвий блок, замерзлий ввід - і не змінює жодного правила), а між гравцями, які ВСІ мають мод, актуальні й дали згоду на Ranked, виправлення чесності отрути та Grow діють навіть у швидких матчах і кімнатах за кодом.

<color=#FFD94D><b>ЯК ПРАЦЮЄ ЦЯ БІБЛІОТЕКА</b></color>

У колонці ліворуч - усі статті, згруповані за категоріями. Клацніть тему - і вона відкриється в цій панелі. Сині назви на кшталт (див. <color=#7FD4FF>Блокування</color>) ведуть до інших статей у тому самому списку. <color=#8A8A93>Усе це меню - F5. T відкриває внутрішньоігровий чат, а Esc закриває меню.</color>

<color=#FFD94D><b>ДЕ ШУКАТИ ДОПОМОГУ</b></color>

- <color=#7FD4FF>Discord</color> - кнопка Discord унизу цього меню відкриває сервер спільноти. Там відповідають живі люди, а ще - бот сервера: спитайте його щось на кшталт «як працює рейтинг» чи «як заробити золото», і він відповість сам.
- <color=#7FD4FF>Повідомлення про баги</color> - на вкладці Налаштування знайдіть «Повідомити про баг» і натисніть «Відкрити форму репорту». Можна прикріпити логи гри (кнопка перегляду показує, що саме буде надіслано), у вас до 10 репортів на день, а якщо ваш Discord прив’язано, відповіді команди приходять у DM.

Якщо посеред матчу щось виглядає не так, надішліть репорт одразу після тієї сесії - зазвичай саме прикріплений лог дозволяє знайти баг.$s256$)
  , ('0f58f10cbab027e1', 'es', 'f1a69beeabd980c74bf3e17ddd9ae4aeb0a0a681', $s256$Tu escudo absorbe durante exactamente 0.3 segundos por pulsación, la decisión de absorber se toma en la máquina del TIRADOR, y un montón de cartas van montadas en el evento de bloqueo. Esta página cubre todo eso.

<color=#FFD94D><b>QUÉ HACE PULSAR BLOQUEO</b></color>

Una pulsación de bloqueo sin enfriamiento hace tres cosas a la vez, haya bala o no:

- Ejecuta cada efecto de carta montado en tu bloqueo. Shield Charge se dispara antes que todo lo demás, luego la cadena principal - Empower se carga aquí, las cartas de curación al bloquear curan aquí, y las cartas que colocan efectos al bloquear (Frost Slam, Supernova, Teleport) los colocan aquí.
- Inicia el enfriamiento.
- Arma la ventana de absorción: <color=#7FE87F>tu escudo absorbe durante exactamente 0.3 segundos tras la pulsación</color>.

Activar y absorber son eventos separados. La pulsación ocurre siempre; la absorción solo ocurre si una bala te alcanza dentro de la ventana.

<color=#FFD94D><b>QUÉ HACE UNA BALA ABSORBIDA</b></color>

- No hace daño, ni knockback, ni ralentización, y no genera ninguno de sus efectos de impacto.
- Su velocidad se invierte - vuela de vuelta por donde vino.
- El tirador pierde su inmunidad a ella: <color=#7FE87F>una bala reflejada puede golpear a su propio tirador</color>.
- Tus efectos de carta 'al bloquear con éxito' se disparan - salvo que la bala que bloqueaste fuera una de las tuyas.
- Unas pocas balas especiales se destruyen al bloquearlas en vez de reflejarse.

La misma ventana anula casi todo lo demás que puede tocarte: daño directo, knockback, ralentización de balas, ralentización y silencio de explosiones, aturdimiento, y ticks de veneno o quemadura (ver <color=#7FD4FF>Veneno y daño en el tiempo</color>). Una caja o una sierra que golpea tu escudo sale rebotada con más fuerza que si rebotara en tu cuerpo. Hasta el borde de la arena lo respeta: salir volando de la pantalla mientras bloqueas no cuesta daño y te lanza de vuelta con el doble de fuerza (ver <color=#7FD4FF>Movimiento y técnicas de escudo</color>).

<color=#FFD94D><b>ENFRIAMIENTO</b></color>

- El enfriamiento base es de 4 segundos. Las cartas lo modifican sumándole o multiplicándolo.
- El temporizador corre en tiempo de juego, así que los momentos a cámara lenta lo estiran en tiempo real.
- La recarga se anuncia: una partícula de recarga y un sonido suenan en cuanto tu escudo vuelve a estar listo.
- <color=#FF6666>Las pulsaciones durante el enfriamiento no hacen nada en absoluto</color> - ni ventana, ni efectos de carta.

<color=#FFD94D><b>BLOQUEOS DE ECO</b></color>

Las cartas que otorgan bloqueos adicionales convierten una pulsación en una ráfaga: el primer bloqueo programa los extras en rápida sucesión, y cada eco vuelve a ejecutar la cadena completa de cartas y rearma la ventana de absorción de 0.3 segundos <color=#7FE87F>sin reiniciar el enfriamiento</color>. Una pulsación compra un tramo más largo de cobertura casi continua.

Dos detalles: los efectos de carta pueden ignorar tipos de bloqueo concretos, y Empower es el que importa - solo se carga con una pulsación real, nunca con ecos ni dashes de Shield Charge, y la carga se gasta en tu siguiente disparo.

<color=#FFD94D><b>BLOQUEÉ A TIEMPO Y AUN ASÍ ME DIERON</b></color>

La decisión de absorber no se toma en tu máquina. Cada bala se simula por separado en el PC de cada jugador, y la copia que cuenta es la del tirador. Cuando su copia de la bala te alcanza, su juego consulta su copia de TU escudo - y esa copia solo se enciende cuando tu pulsación ha cruzado la red, más o menos la mitad de tu ping más la mitad del suyo después de pulsar. Una bala que te alcanzó en su pantalla dentro de ese hueco se declara no bloqueada, el daño se envía como número final, y nada en tu máquina puede rechazarlo. Que tu escudo se vea levantado en tu pantalla nunca entra en la decisión.

La otra cara es simétrica: tus balas se juzgan en TU pantalla. Si tu disparo conectó en tu máquina, conecta. El mecanismo completo y los números viven un artículo más allá (ver <color=#7FD4FF>Netcode y Photon</color>).

<color=#FFD94D><b>QUÉ REPARA EL MOD</b></color>

ROUNDS vanilla tiene una familia de bugs donde el bloqueo muere en silencio entre juegos: la limpieza de la revancha puede destruir objetos de carta a medias, dejando hooks 'zombis' muertos pegados a tu bloqueo. Al siguiente juego tu escudo se anima e inicia su enfriamiento pero no absorbe nada - o el bloqueo básico funciona mientras un efecto de carta como Shield Charge no vuelve a dispararse.

El mod barre esos hooks muertos al empezar cada juego, en cada revancha y justo antes de ejecutar cada bloqueo, y un hook de carta roto ya no cancela el resto de tu bloqueo. Estas reparaciones corren en todas partes porque solo eliminan restos demostrablemente muertos - restauran el bloqueo que vanilla quería darte, nunca inventan una regla nueva. <color=#7FE87F>Un jugador sin mod siempre recibe gameplay vanilla puro</color> (ver <color=#7FD4FF>Vanilla sigue siendo vanilla</color>). La lista completa de reparaciones vive en <color=#7FD4FF>Arreglos de bugs del mod</color>.$s256$)
  , ('0f58f10cbab027e1', 'ru', 'f1a69beeabd980c74bf3e17ddd9ae4aeb0a0a681', $s256$Твой щит поглощает ровно 0.3 секунды за нажатие, решение о поглощении принимается на машине СТРЕЛКА, а на событии блока едет целая пачка карт. Эта страница покрывает всё это.

<color=#FFD94D><b>ЧТО ДЕЛАЕТ НАЖАТИЕ БЛОКА</b></color>

Нажатие блока вне отката делает три вещи сразу, есть пуля или нет:

- Запускает каждый карточный эффект, который едет на твоём блоке. Shield Charge срабатывает раньше всего, затем основная цепочка: Empower заряжается здесь, карты лечения от блока лечат здесь, а карты, создающие эффекты от блока (Frost Slam, Supernova, Teleport), ставят свои эффекты здесь.
- Запускает откат.
- Взводит окно поглощения: <color=#7FE87F>твой щит поглощает ровно 0.3 секунды после нажатия</color>.

Активация и поглощение - отдельные события. Нажатие происходит всегда; поглощение - только если пуля долетает до тебя внутри окна.

<color=#FFD94D><b>ЧТО ДЕЛАЕТ ПОГЛОЩЁННАЯ ПУЛЯ</b></color>

- Она не наносит ни урона, ни отброса, ни замедления и не создаёт ни одного из своих эффектов при попадании.
- Её скорость разворачивается - она летит ровно туда, откуда прилетела.
- Стрелок теряет к ней иммунитет: <color=#7FE87F>отражённая пуля может попасть в собственного стрелка</color>.
- Твои карточные эффекты «при успешном блоке» срабатывают - если только заблокированная пуля не была твоей собственной.
- Несколько особых пуль при блоке уничтожаются, а не отражаются.

То же окно гасит почти всё остальное, что может тебя коснуться: прямой урон, отброс, замедление от пуль, замедление и сайленс от взрывов, стан и тики яда или горения (см. <color=#7FD4FF>Яд и урон со временем</color>). Ящик или пила, ударившие в щит, отлетают сильнее, чем от твоего тела. Даже край арены его уважает: вылет за экран во время блока не стоит урона и запускает тебя обратно вдвое сильнее (см. <color=#7FD4FF>Движение и техника щита</color>).

<color=#FFD94D><b>ОТКАТ</b></color>

- Базовый откат - 4 секунды. Карты меняют его прибавками или множителями.
- Таймер идёт по игровому времени, так что моменты слоу-мо растягивают его в реальном времени.
- Перезарядка объявляется: в момент готовности щита играют партикл перезарядки и звук.
- <color=#FF6666>Нажатия во время отката не делают вообще ничего</color> - ни окна, ни карточных эффектов.

<color=#FFD94D><b>ЭХО-БЛОКИ</b></color>

Карты, дающие дополнительные блоки, превращают одно нажатие в очередь: первый блок планирует дополнительные с малыми промежутками, и каждое эхо заново прогоняет полную цепочку карт и заново взводит окно поглощения в 0.3 секунды <color=#7FE87F>без перезапуска отката</color>. Одно нажатие покупает длинный отрезок почти непрерывной защиты.

Две тонкости: карточные эффекты могут игнорировать отдельные типы блока, и важен тут Empower - он заряжается только от настоящего нажатия, никогда от эха или рывков Shield Charge, а заряд тратится на твой следующий выстрел.

<color=#FFD94D><b>Я ЗАБЛОКИРОВАЛ ВОВРЕМЯ И ВСЁ РАВНО ПОЛУЧИЛ УРОН</b></color>

Решение о поглощении принимается не на твоей машине. Каждая пуля симулируется отдельно на PC каждого игрока, и считается копия стрелка. Когда его копия пули долетает до тебя, его игра проверяет его копию ТВОЕГО щита - а та включается только после того, как твоё нажатие пересекло сеть: примерно половина твоего пинга плюс половина его после нажатия. Пуля, долетевшая до тебя на его экране внутри этого зазора, считается незаблокированной, урон отправляется финальным числом, и ничто на твоей машине не может его отклонить. То, что щит виден поднятым на твоём экране, в решении не участвует вообще.

Обратная сторона симметрична: твои пули судятся на ТВОЁМ экране. Если твой выстрел попал на твоей машине - он попал. Полный механизм и цифры живут в соседней статье (см. <color=#7FD4FF>Неткод и Photon</color>).

<color=#FFD94D><b>ЧТО ЧИНИТ МОД</b></color>

В ванильном ROUNDS есть семейство багов, где блок тихо умирает между играми: снос объектов при рематче может уничтожить карточные объекты наполовину, оставив на твоём блоке мёртвые «зомби»-хуки. В следующей игре щит анимируется и уходит в откат, но не поглощает ничего - или базовый блок работает, а карточный эффект вроде Shield Charge больше никогда не срабатывает.

Мод выметает эти мёртвые хуки на старте каждой игры, при каждом рематче и прямо перед выполнением каждого блока, и один сломанный хук карты больше не отменяет остальной блок. Эти ремонты работают везде, потому что лишь убирают доказуемо мёртвые остатки - возвращая блок, который ваниль тебе и предназначала, и не изобретая новых правил. <color=#7FE87F>Игрок без мода всегда получает чистый ванильный геймплей</color> (см. <color=#7FD4FF>Ваниль остаётся ванилью</color>). Полный список ремонтов - в статье <color=#7FD4FF>Исправления багов в моде</color>.$s256$)
  , ('0f58f10cbab027e1', 'sv', 'f1a69beeabd980c74bf3e17ddd9ae4aeb0a0a681', $s256$Din sköld absorberar i exakt 0.3 sekunder per tryck, absorberingsbeslutet fattas på SKYTTENS maskin, och en hög kort rider på blockhändelsen. Den här sidan täcker allt det.

<color=#FFD94D><b>VAD ETT BLOCKTRYCK GÖR</b></color>

Ett blocktryck utan cooldown gör tre saker på en gång, kula eller ingen kula:

- Kör varje korteffekt som rider på ditt block. Shield Charge avfyras före allt annat, sedan huvudkedjan - Empower laddas här, block-heal-kort helar här, och block-spawn-kort (Frost Slam, Supernova, Teleport) placerar sina effekter här.
- Startar cooldownen.
- Aktiverar absorberingsfönstret: <color=#7FE87F>din sköld absorberar i exakt 0.3 sekunder efter trycket</color>.

Att aktivera och att absorbera är separata händelser. Trycket sker alltid; absorbering sker bara om en kula når dig inom fönstret.

<color=#FFD94D><b>VAD EN ABSORBERAD KULA GÖR</b></color>

- Den gör ingen skada, ingen knockback, ingen slow, och spawnar inga av sina träffeffekter.
- Dess hastighet vänds - den flyger rakt tillbaka samma väg den kom.
- Skytten förlorar sin immunitet mot den: <color=#7FE87F>en reflekterad kula kan träffa sin egen skytt</color>.
- Dina korteffekter för 'lyckat block' avfyras - om inte kulan du blockade var en av dina egna.
- Några speciella kulor förstörs vid block i stället för att reflekteras.

Samma fönster upphäver nästan allt annat som kan röra dig: direkt skada, knockback, kul-slow, explosions-slow och silence, stun, och gift- eller brännticks (se <color=#7FD4FF>Gift & skada över tid</color>). En låda eller såg som träffar din sköld studsar iväg hårdare än den skulle från din kropp. Till och med arenakanten respekterar det: att flyga ut ur bild medan du blockerar kostar ingen skada och skjuter dig tillbaka in dubbelt så hårt (se <color=#7FD4FF>Rörelse & sköldteknik</color>).

<color=#FFD94D><b>COOLDOWN</b></color>

- Bascooldownen är 4 sekunder. Kort ändrar den genom att addera till den eller multiplicera den.
- Timern går på speltid, så slow motion-ögonblick sträcker ut den i realtid.
- Uppladdningen annonseras: en omladdningspartikel och ett ljud spelas i samma stund som din sköld är redo igen.
- <color=#FF6666>Tryck under cooldown gör ingenting alls</color> - inget fönster, inga korteffekter.

<color=#FFD94D><b>EKOBLOCK</b></color>

Kort som ger extra block gör ett tryck till en skur: det första blocket schemalägger extrablocken i snabb följd, och varje eko kör om hela kortkedjan och aktiverar 0.3-sekundersfönstret på nytt <color=#7FE87F>utan att starta om cooldownen</color>. Ett tryck köper en längre sträcka av nästan obruten täckning.

Två detaljer: korteffekter kan ignorera specifika blocktyper, och Empower är den som spelar roll - den laddas bara av ett riktigt tryck, aldrig av ekon eller Shield Charge-rusher, och laddningen förbrukas på ditt nästa avlossade skott.

<color=#FFD94D><b>JAG BLOCKADE I TID OCH BLEV TRÄFFAD ÄNDÅ</b></color>

Absorberingsbeslutet fattas inte på din maskin. Varje kula simuleras separat på varje spelares dator, och kopian som räknas är skyttens. När deras kopia av kulan når dig kontrollerar deras spel deras kopia av DIN sköld - och den kopian slås på först när ditt tryck har korsat nätverket, ungefär halva din ping plus halva deras efter att du tryckte. En kula som nådde dig på deras skärm inom det gapet döms som oblockerad, skadan skickas som en färdig siffra, och inget på din maskin kan vägra den. Att din sköld syns uppe på din skärm ingår aldrig i beslutet.

Baksidan är symmetrisk: dina kulor döms på DIN skärm. Om ditt skott träffade på din maskin, träffar det. Hela mekanismen och siffrorna finns en artikel bort (se <color=#7FD4FF>Nätkod & Photon</color>).

<color=#FFD94D><b>VAD MODDEN REPARERAR</b></color>

Vanilla-ROUNDS har en familj av buggar där blocket dör tyst mellan matcher: nedmonteringen mellan matcher kan förstöra kortobjekt halvvägs och lämna döda 'zombiekrokar' på ditt block. Nästa match animerar din sköld och startar sin cooldown men absorberar ingenting - eller så fungerar basblocket medan en korteffekt som Shield Charge aldrig avfyras igen.

Modden sopar bort de döda krokarna vid varje matchstart, vid varje rematch och precis innan varje block körs, och en trasig kortkrok avbryter inte längre resten av ditt block. De här reparationerna körs överallt eftersom de bara tar bort bevisligen döda rester - de återställer blocket som vanilla avsåg att du skulle ha, aldrig en ny regel. <color=#7FE87F>En spelare utan modden får alltid ren vanilla-gameplay</color> (se <color=#7FD4FF>Vanilla förblir vanilla</color>). Den kompletta reparationslistan finns i <color=#7FD4FF>Buggfixar i modden</color>.$s256$)
  , ('0f58f10cbab027e1', 'uk', 'f1a69beeabd980c74bf3e17ddd9ae4aeb0a0a681', $s256$Ваш щит поглинає рівно 0.3 секунди на натискання, рішення про поглинання ухвалюється на машині СТРІЛЬЦЯ, а на події блоку їде ціла купа карт. Ця сторінка охоплює все це.

<color=#FFD94D><b>ЩО РОБИТЬ НАТИСКАННЯ БЛОКУ</b></color>

Натискання блоку поза відкатом робить три речі водночас, є куля чи немає:

- Запускає кожен ефект карти, що їде на вашому блоці. Shield Charge спрацьовує перед усім іншим, далі основний ланцюжок - тут заряджається Empower, тут лікують карти блок-лікування, і тут ставлять свої ефекти блок-спавн карти (Frost Slam, Supernova, Teleport).
- Запускає відкат.
- Зводить вікно поглинання: <color=#7FE87F>ваш щит поглинає рівно 0.3 секунди після натискання</color>.

Активація і поглинання - окремі події. Натискання відбувається завжди; поглинання - лише якщо куля досягне вас усередині вікна.

<color=#FFD94D><b>ЩО РОБИТЬ ПОГЛИНУТА КУЛЯ</b></color>

- Вона не завдає ні шкоди, ні відкидання, ні сповільнення і не породжує жодного зі своїх ефектів при влучанні.
- Її швидкість обертається - вона летить рівно туди, звідки прилетіла.
- Стрілець втрачає імунітет до неї: <color=#7FE87F>відбита куля може влучити у власного стрільця</color>.
- Ваші ефекти карт «при успішному блоці» спрацьовують - якщо тільки заблокована куля не була вашою власною.
- Кілька особливих куль на блоці знищуються, а не відбиваються.

Те саме вікно скасовує майже все інше, що може вас торкнутися: пряму шкоду, відкидання, сповільнення від куль, сповільнення й сайленс від вибухів, оглушення, а також тіки отрути чи горіння (див. <color=#7FD4FF>Отрута та поступова шкода</color>). Ящик або пилка, що б’є у щит, відскакує сильніше, ніж від вашого тіла. Навіть край арени поважає його: виліт за екран під час блоку не коштує шкоди і запускає вас назад удвічі сильніше (див. <color=#7FD4FF>Рух і техніка щита</color>).

<color=#FFD94D><b>ВІДКАТ</b></color>

- Базовий відкат - 4 секунди. Карти змінюють його додаванням або множенням.
- Таймер іде на ігровому часі, тож моменти слоу-мо розтягують його в реальному часі.
- Про перезарядку повідомляється: щойно щит знову готовий, грають частинка і звук перезарядки.
- <color=#FF6666>Натискання під час відкату не роблять зовсім нічого</color> - ні вікна, ні ефектів карт.

<color=#FFD94D><b>ЕХО-БЛОКИ</b></color>

Карти, що дають додаткові блоки, перетворюють одне натискання на чергу: перший блок планує додаткові швидкою серією, і кожне відлуння знову проганяє весь ланцюжок карт і знову зводить вікно поглинання на 0.3 секунди <color=#7FE87F>без перезапуску відкату</color>. Одне натискання купує довший відрізок майже безперервного прикриття.

Дві тонкощі: ефекти карт можуть ігнорувати окремі типи блоку, і важливий тут саме Empower - він заряджається лише від справжнього натискання, ніколи від відлунь чи ривків Shield Charge, а заряд витрачається на ваш наступний постріл.

<color=#FFD94D><b>Я ЗАБЛОКУВАВ ВЧАСНО І ВСЕ ОДНО ОТРИМАВ ВЛУЧАННЯ</b></color>

Рішення про поглинання ухвалюється не на вашій машині. Кожна куля симулюється окремо на ПК кожного гравця, і рахується копія стрільця. Коли їхня копія кулі досягає вас, їхня гра перевіряє їхню копію ВАШОГО щита - а та копія вмикається лише тоді, коли ваше натискання перетнуло мережу, тобто приблизно через половину вашого пінгу плюс половину їхнього після натискання. Куля, що на їхньому екрані дійшла до вас усередині цього проміжку, вважається незаблокованою, шкода надсилається готовим числом, і ніщо на вашій машині не може її відхилити. Те, що щит видимо піднятий на вашому екрані, у рішенні взагалі не бере участі.

Зворотний бік симетричний: ваші кулі судяться на ВАШОМУ екрані. Якщо ваш постріл влучив на вашій машині - він влучив. Повний механізм і числа - у сусідній статті (див. <color=#7FD4FF>Неткод і Photon</color>).

<color=#FFD94D><b>ЩО ЛАГОДИТЬ МОД</b></color>

У ванільному ROUNDS є родина багів, коли блок тихо вмирає між іграми: розбирання перед рематчем може знищити об’єкти карт наполовину, лишивши на вашому блоці мертві «зомбі»-гачки. У наступній грі щит анімується і запускає відкат, але нічого не поглинає - або базовий блок працює, а ефект карти на кшталт Shield Charge більше ніколи не спрацьовує.

Мод вимітає ці мертві гачки на старті кожної гри, при кожному рематчі та безпосередньо перед виконанням кожного блоку, і один зламаний гачок карти більше не скасовує решту вашого блоку. Ці ремонти працюють скрізь, бо лише прибирають доведено мертві залишки - повертаючи блок, який ваніль вам і призначала, і не вигадуючи жодного нового правила. <color=#7FE87F>Гравець без мода завжди отримує чистий ванільний геймплей</color> (див. <color=#7FD4FF>Ваніль лишається ваніллю</color>). Повний список ремонтів - у <color=#7FD4FF>Виправлення багів у моді</color>.$s256$)
  , ('127ceae105cad5ec', 'es', 'c42e9abf5a38ab33401c8bf8760d6a1a2d460ddd', $s256$Registro y juego limpio$s256$)
  , ('127ceae105cad5ec', 'ru', 'c42e9abf5a38ab33401c8bf8760d6a1a2d460ddd', $s256$Учёт и честная игра$s256$)
  , ('127ceae105cad5ec', 'sv', 'c42e9abf5a38ab33401c8bf8760d6a1a2d460ddd', $s256$Spårning & fair play$s256$)
  , ('127ceae105cad5ec', 'uk', 'c42e9abf5a38ab33401c8bf8760d6a1a2d460ddd', $s256$Облік і чесна гра$s256$)
  , ('15a0134039dff3c3', 'es', '8e761bd4b08d438e4c4386b39a7cfaa00c272edf', $s256$Las partidas competitivas en vivo de todos los modos pueden verse desde dentro del mod - ranked 1v1, 2v2, 1v2 y FFA (las salas casual 1v1 normales no se listan). Ves la partida real, en vivo, desde un lugar construido para que no pueda tocar el combate.

<color=#FFD94D><b>CÓMO VER UNA PARTIDA</b></color>

- Los botones <color=#7FD4FF>VER</color> aparecen en las filas de partidas en vivo por todo el menú F5: la franja de series en vivo de la Clasificación, las salas en vivo de la pestaña FFA, el panel en vivo de la pestaña 1v2 y las filas en vivo de Inicio. Nunca ves VER en tu propia partida.
- Hacer clic te mete en la sala real de Photon como asiento no jugador. No puedes empezar a espectar estando en una sala online o en mitad de una cola.
- Una partida es accesible mientras sus combatientes están en combate en vivo, hay un lugar de espectador libre y todos los combatientes permiten espectadores.

<color=#FFD94D><b>QUÉ VES</b></color>

- La partida real en vivo - movimiento real y proyectiles reales, no una repetición ni una señal retrasada.
- La pantalla se queda en negro hasta el primer límite de ronda limpio, y entonces la partida aparece sincronizada. Si tu cliente tiene que ponerse al día a mitad de ronda, ves la escena en vivo con un aviso de Sincronizando en vez de negro.
- Las elecciones de carta son visibles, y cada límite de ronda trae los mazos completos de todos. En FFA ves resultados de elección y mazos, no la mano privada de candidatas de cada jugador.
- Una barra superior mínima muestra el marcador y los nombres, títulos y ratings de los combatientes. Mantén Tab para la tabla de stats. El chat funciona (y puede silenciarse). Esc abre el menú de salida.

<color=#FFD94D><b>POR QUÉ UN ESPECTADOR NO PUEDE TOCAR LA PARTIDA</b></color>

El asiento de espectador es un observador por construcción, no por cortesía:

- <color=#7FE87F>No puede hacer daño ni causar una muerte.</color> Un candado a nivel de asiento hace inalcanzable la rama de muerte desde cada ruta de daño en ese asiento - las muertes que ves ocurren en los clientes de los combatientes y solo se dibujan en el tuyo.
- No puede generar un jugador, ponerse listo ni ocupar una plaza - hasta el aviso de saltar-para-entrar está suprimido.
- Nunca responde ni envía las peticiones de sincronización que los combatientes usan para mantenerse acompasados, y nunca reporta cargas de mapa, así que no puede frenar ni desincronizar el combate.
- No puede elegir cartas y no ejecuta nada del ciclo de la partida - solo aplica los marcadores que difunde el maestro.
- Es invisible para todo recuento de combatientes: los quórums, la elección de quién reporta y los recuentos de inicio excluyen a los espectadores.
- <color=#7FE87F>Que un espectador se vaya nunca termina la partida de los combatientes.</color>

<color=#FFD94D><b>PRIVACIDAD, RECUENTOS Y LÍMITES</b></color>

- Los combatientes siempre lo saben: cada asiento de la sala - combatientes y espectadores por igual - ve abajo a la derecha una línea de Espectadores con nombres mientras alguien mira, y la lista de partidas muestra el número de espectadores públicamente.
- <color=#7FD4FF>Permitir espectadores</color> es una opción por jugador en Ajustes de F5, activada por defecto. Si un solo combatiente de una partida la tiene desactivada, esa partida no puede verse - y la razón mostrada es genérica, nunca quién se excluyó. Desactivarla a mitad de partida quita a los espectadores sentados en unos instantes.
- La única excepción: las partidas de torneo sync siempre pueden verse.
- Los lugares públicos de espectador se limitan a 4 por partida, y un lugar extra queda reservado para la cuenta oficial de retransmisión que emite el stream de la comunidad, así los espectadores públicos nunca pueden dejarla fuera. Una partida llena responde 'espectadores al completo'.

<color=#FFD94D><b>SALIR, Y SER DEVUELTO</b></color>

- Esc, y luego salir. Salir nunca molesta a la partida - tu nombre simplemente desaparece de la línea de Espectadores.
- Tu lugar es una concesión que tu cliente renueva cada pocos segundos. Cuando la partida termina o un combatiente se excluye, la concesión acaba y vuelves al menú automáticamente. <color=#7FE87F>Un tropiezo de red nunca te expulsa</color> - solo lo hace una respuesta definitiva del servidor.

<color=#FFD94D><b>ESPECTADORES Y APUESTAS</b></color>

- Los espectadores pueden apostar. Las ventanas de cierre temprano de apuestas son la barrera de información: las apuestas de 1v1 y 2v2 se cierran cuando se anotan 2 puntos en el juego 1, y las de FFA cuando se anotan 2 medios puntos en la partida apostada (antes en salas cortas) - así que quedarse mirando no enseña nada útil antes de que la ventana se cierre.
- El único grupo vetado son los propios miembros de una sala: nunca puedes apostar en tu propia sala.$s256$)
  , ('15a0134039dff3c3', 'ru', '8e761bd4b08d438e4c4386b39a7cfaa00c272edf', $s256$Живые соревновательные игры каждого режима можно смотреть прямо из мода - рейтинговые 1v1, 2v2, 1v2 и FFA (обычные казуальные комнаты 1v1 не показываются). Ты видишь настоящую игру, вживую, с места, устроенного так, что оно не может тронуть матч.

<color=#FFD94D><b>КАК СМОТРЕТЬ</b></color>

- Кнопки <color=#7FD4FF>СМОТРЕТЬ</color> появляются на строках живых игр по всему меню F5: полоса живых серий на Таблице лидеров, живые лобби на вкладке FFA, живая панель вкладки 1v2 и живые строки на Главной. На своей игре кнопку СМОТРЕТЬ ты не увидишь никогда.
- Клик по ней сажает тебя в настоящую комнату Photon неиграющим местом. Нельзя начать смотреть, пока ты в онлайн-комнате или в очереди.
- Игра доступна для входа, пока её бойцы ведут живой бой, есть свободное зрительское место и каждый боец разрешает зрителей.

<color=#FFD94D><b>ЧТО ТЫ ВИДИШЬ</b></color>

- Настоящую живую игру - реальные движения и реальные снаряды, не реплей и не задержанную трансляцию.
- Экран остаётся чёрным до первой чистой границы раунда, затем игра появляется синхронно. Если клиенту приходится догонять посреди раунда, ты видишь живую сцену с пометкой о синхронизации вместо черноты.
- Пики карт видны, и каждая граница раунда несёт полные колоды всех. В FFA ты видишь результаты пиков и колоды, но не чью-то личную руку кандидатов.
- Минимальная верхняя полоса показывает счёт и имена, титулы и рейтинги бойцов. Держи Tab для доски статистики. Чат работает (и его можно замьютить). Esc открывает меню выхода.

<color=#FFD94D><b>ПОЧЕМУ ЗРИТЕЛЬ НЕ МОЖЕТ ТРОНУТЬ ИГРУ</b></color>

Зрительское место - наблюдатель по построению, а не из вежливости:

- <color=#7FE87F>Оно не может нанести урон или вызвать смерть.</color> Ограничитель на всё место делает ветку смерти недостижимой из любого пути урона на нём - смерти, которые ты видишь, происходят на клиентах бойцов и лишь отрисовываются на твоём.
- Оно не может заспавнить игрока, нажать готовность или занять слот - подавлена даже подсказка «нажми прыжок, чтобы войти».
- Оно никогда не отвечает на запросы синхронизации, которыми бойцы держат строй, и не шлёт их, и не отчитывается о загрузке карт - так что не может замедлить или рассинхронизировать матч.
- Оно не может выбирать карты и не запускает ничего из жизненного цикла игры - только применяет счёт, который объявляет мастер.
- Оно невидимо для любых подсчётов бойцов: проверки кворума, выбор репортёра и подсчёты на старте матча исключают зрителей.
- <color=#7FE87F>Уход зрителя никогда не завершает матч бойцов.</color>

<color=#FFD94D><b>ПРИВАТНОСТЬ, СЧЁТЧИКИ И ЛИМИТЫ</b></color>

- Бойцы всегда в курсе: каждое место в комнате - и бойцы, и зрители - видит внизу справа строку «Зрители» с именами, пока кто-то смотрит, а список игр показывает число зрителей публично.
- <color=#7FD4FF>Разрешить зрителей</color> - личный переключатель в Настройках F5, включён по умолчанию. Если хоть один боец в игре его выключил, эту игру смотреть нельзя - и причина показывается общая, никогда не «кто именно». Выключение посреди матча убирает сидящих зрителей за считанные мгновения.
- Единственное исключение: матчи синхро-турниров можно смотреть всегда.
- Публичных зрительских мест максимум 4 на игру, и одно дополнительное зарезервировано за официальным аккаунтом трансляции, ведущим стрим сообщества, - публичные зрители не могут его вытеснить. Полная игра отвечает «зрительские места заняты».

<color=#FFD94D><b>ВЫХОД - И ВОЗВРАТ</b></color>

- Esc, затем выход. Уход никогда не тревожит матч - твоё имя просто пропадает из строки «Зрители».
- Твоё место - аренда, которую клиент продлевает каждые несколько секунд. Когда игра кончается или боец запрещает зрителей, аренда истекает, и тебя автоматически возвращают в меню. <color=#7FE87F>Сетевой сбой тебя никогда не выкидывает</color> - только однозначный ответ сервера.

<color=#FFD94D><b>НАБЛЮДЕНИЕ И СТАВКИ</b></color>

- Зрители могут ставить. Информационный шлюз - это ранние окна закрытия ставок: ставки 1v1 и 2v2 закрываются после 2 очков в игре 1, а ставки FFA - после 2 пол-очков в игре, на которую ставят (в коротких лобби раньше), - так что засидевшееся место не узнаёт ничего полезного до закрытия окна.
- Единственная отрезанная группа - участники самого лобби: на своё лобби ставить нельзя никогда.$s256$)
  , ('15a0134039dff3c3', 'sv', '8e761bd4b08d438e4c4386b39a7cfaa00c272edf', $s256$Pågående tävlingsmatcher i varje läge kan ses inifrån modden - ranked 1v1, 2v2, 1v2 och FFA (vanliga casual-1v1-rum listas inte). Du ser den riktiga matchen, live, från en plats som är byggd så att den inte kan röra matchen.

<color=#FFD94D><b>SÅ TITTAR DU</b></color>

- <color=#7FD4FF>TITTA</color>-knappar dyker upp på rader med pågående matcher i hela F5-menyn: topplistans remsa med pågående serier, FFA-flikens aktiva lobbyer, 1v2-flikens livepanel och Hem-flikens liverader. Du ser aldrig TITTA på din egen match.
- Ett klick sätter dig i det riktiga Photon-rummet som en icke-spelande plats. Du kan inte börja åskåda medan du är i ett onlinerum eller mitt i en kö.
- En match går att ansluta till medan dess fighters är i aktiv strid, en åskådarplats är ledig och varje fighter tillåter åskådare.

<color=#FFD94D><b>VAD DU SER</b></color>

- Den äkta livematchen - riktig rörelse och riktiga projektiler, inte en repris eller ett fördröjt flöde.
- Skärmen är svart fram till den första rena rondgränsen, sedan dyker matchen upp i synk. Om din klient någon gång måste komma ikapp mitt i en rond ser du livescenen med en Synkar-notis i stället för svart.
- Kortval syns, och varje rondgräns bär allas fulla kortlekar. I FFA ser du valresultat och kortlekar, inte varje väljares privata hand av kandidater.
- En minimal topprad visar ställningen och fighternas namn, titlar och rating. Håll Tab för statistiktavlan. Chatten fungerar (och kan tystas). Esc öppnar lämna-menyn.

<color=#FFD94D><b>VARFÖR EN ÅSKÅDARE INTE KAN RÖRA MATCHEN</b></color>

Åskådarplatsen är en observatör per konstruktion, inte av artighet:

- <color=#7FE87F>Den kan inte göra skada eller orsaka en död.</color> En platsbred spärr gör dödsgrenen onåbar från varje skadeväg på den platsen - dödsfallen du ser sker på fighternas klienter och renderas bara på din.
- Den kan inte spawna en spelare, bli redo eller ta en plats - till och med tryck-hopp-för-att-gå-med-prompten undertrycks.
- Den besvarar eller skickar aldrig de synkroniseringsförfrågningar fighters använder för att hålla takten, och rapporterar aldrig kartladdningar, så den kan inte sakta ner eller desynka matchen.
- Den kan inte välja kort och kör inget av matchens livscykel - den tillämpar bara ställningarna som mastern sänder ut.
- Den är osynlig för varje fighterräkning: kvorumkontroller, rapportörsval och matchstartsräkningar utesluter alla åskådare.
- <color=#7FE87F>En åskådare som lämnar avslutar aldrig fighternas match.</color>

<color=#FFD94D><b>INTEGRITET, ANTAL OCH GRÄNSER</b></color>

- Fighters vet alltid: varje plats i rummet - fighters som åskådare - ser en Åskådare-rad nere till höger med namn medan någon tittar, och matchlistan visar åskådarantal offentligt.
- <color=#7FD4FF>Tillåt åskådare</color> är en inställning per spelare i F5 Inställningar, på som standard. Om en enda fighter i en match har den av kan matchen inte ses - och skälet som visas är generiskt, aldrig vem som valde bort. Att slå av den mitt i en match tar bort sittande åskådare inom kort.
- Det enda undantaget: synkturneringsmatcher går alltid att åskåda.
- Publika åskådarplatser är max 4 per match, och en extra plats är reserverad för det officiella sändningskontot som kör communityströmmen, så publika åskådare kan aldrig tränga ut det. En full match svarar 'åskådarplatserna fulla'.

<color=#FFD94D><b>ATT LÄMNA, OCH ATT SKICKAS TILLBAKA</b></color>

- Esc, sedan lämna. Att lämna stör aldrig matchen - ditt namn försvinner bara från Åskådare-raden.
- Din plats är ett tidsbegränsat tillstånd som din klient förnyar med några sekunders mellanrum. När matchen slutar eller en fighter väljer bort avslutas tillståndet och du skickas automatiskt tillbaka till menyn. <color=#7FE87F>Ett nätverkshack sparkar dig aldrig</color> - bara ett definitivt svar från servern gör det.

<color=#FFD94D><b>ÅSKÅDANDE OCH VADSLAGNING</b></color>

- Åskådare kan satsa. De tidiga stängningsfönstren är informationsgrinden: 1v1- och 2v2-vad låses när 2 poäng gjorts i match 1, och FFA-vad låses när 2 halvpoäng gjorts i matchen vadet gäller (tidigare i korta lobbyer) - så en kvardröjande plats lär sig inget användbart innan fönstret stängs.
- Den enda utestängda gruppen är en lobbys egna medlemmar: du kan aldrig satsa på din egen lobby.$s256$)
  , ('15a0134039dff3c3', 'uk', '8e761bd4b08d438e4c4386b39a7cfaa00c272edf', $s256$Живі змагальні ігри в кожному режимі можна дивитися просто з мода - рейтингові 1v1, 2v2, 1v2 і FFA (звичайні кімнати 1v1 у списку не з’являються). Ви бачите справжню гру, наживо, з місця, збудованого так, що воно не може торкнутися матчу.

<color=#FFD94D><b>ЯК ДИВИТИСЯ</b></color>

- Кнопки <color=#7FD4FF>ДИВИТИСЯ</color> з’являються на рядках живих ігор по всьому меню F5: стрічка живих серій на Таблиці лідерів, живі лобі вкладки FFA, жива панель вкладки 1v2 і живі рядки Головної. На власній грі кнопки ДИВИТИСЯ ви не побачите ніколи.
- Клік по ній садить вас у справжню кімнату Photon як неігрове місце. Не можна почати дивитися, поки ви в онлайн-кімнаті чи в черзі.
- До гри можна приєднатися, поки її бійці у живому бою, місце глядача вільне і кожен боєць дозволяє глядачів.

<color=#FFD94D><b>ЩО ВИ БАЧИТЕ</b></color>

- Справжню живу гру - реальний рух і реальні снаряди, не повтор і не затриману трансляцію.
- Екран лишається чорним до першої чистої межі раунду, далі гра з’являється синхронно. Якщо вашому клієнту доведеться наздоганяти посеред раунду, ви бачите живу сцену з поміткою «Синхронізація» замість чорноти.
- Вибори карт видно, і кожна межа раунду несе повні колоди всіх. У FFA ви бачите результати виборів і колоди, але не приватну руку кандидатів кожного, хто обирає.
- Мінімальна верхня панель показує рахунок та імена, титули й рейтинги бійців. Утримуйте Tab для табло статистики. Чат працює (і його можна вимкнути). Esc відкриває меню виходу.

<color=#FFD94D><b>ЧОМУ ГЛЯДАЧ НЕ МОЖЕ ТОРКНУТИСЯ ГРИ</b></color>

Місце глядача - спостерігач за конструкцією, а не з ввічливості:

- <color=#7FE87F>Воно не може завдати шкоди чи спричинити смерть.</color> Обмежувач на все місце робить гілку смерті недосяжною з будь-якого шляху шкоди на цьому місці - смерті, які ви бачите, стаються на клієнтах бійців і лише рендеряться на вашому.
- Воно не може заспавнити гравця, приготуватися чи зайняти слот - навіть підказка «стрибни, щоб приєднатися» прихована.
- Воно ніколи не відповідає на запити синхронізації, якими бійці тримаються в ногу, і не звітує про завантаження мап, тож не може сповільнити чи розсинхронізувати матч.
- Воно не може обирати карти і не виконує жодної частини життєвого циклу гри - лише застосовує рахунки, які розсилає майстер.
- Воно невидиме для кожного підрахунку бійців: перевірки кворуму, вибори звітувальника і підрахунки старту матчу глядачів не враховують.
- <color=#7FE87F>Вихід глядача ніколи не завершує матч бійців.</color>

<color=#FFD94D><b>ПРИВАТНІСТЬ, ЛІЧИЛЬНИКИ Й ЛІМІТИ</b></color>

- Бійці завжди знають: кожне місце в кімнаті - і бійці, і глядачі - бачить унизу праворуч рядок «Глядачі» з іменами, поки хтось дивиться, а список ігор показує кількість глядачів публічно.
- <color=#7FD4FF>Допускати глядачів</color> - особистий перемикач у Налаштуваннях F5, типово ввімкнений. Якщо бодай один боєць у грі його вимкнув, цю гру дивитися не можна - і показується загальна причина, ніколи не хто саме відмовився. Вимкнення посеред матчу прибирає присутніх глядачів за мить.
- Єдиний виняток: матчі синхронних турнірів можна дивитися завжди.
- Публічних місць глядачів - максимум 4 на гру, і одне додаткове місце зарезервоване за офіційним акаунтом трансляції, що веде стрім спільноти, тож публічні глядачі ніколи його не витіснять. Повна гра відповідає «місць глядачів немає».

<color=#FFD94D><b>ВИХІД - І ПОВЕРНЕННЯ</b></color>

- Esc, потім вихід. Вихід ніколи не турбує матч - ваше ім’я просто зникає з рядка «Глядачі».
- Ваше місце - оренда, яку ваш клієнт поновлює що кілька секунд. Коли гра завершується або боєць вимикає дозвіл, оренда закінчується і вас автоматично повертає в меню. <color=#7FE87F>Мережевий збій ніколи вас не викидає</color> - лише однозначна відповідь сервера.

<color=#FFD94D><b>ГЛЯДАЧІ Й СТАВКИ</b></color>

- Глядачі можуть ставити. Ранні вікна закриття ставок і є інформаційним бар’єром: ставки 1v1 і 2v2 замикаються, щойно у грі 1 набрано 2 очки, а ставки FFA - щойно у грі, на яку ставлять, набрано 2 половинки очок (у коротких лобі раніше) - тож засиджене місце не дізнається нічого корисного до закриття вікна.
- Єдина заборонена група - учасники самого лобі: на власне лобі ставити не можна ніколи.$s256$)
  , ('17359b8ec6399a4a', 'es', 'ba3b5585c9b14b2966768e5003f9dabd61b2ba22', $s256$Cómo mejorar$s256$)
  , ('17359b8ec6399a4a', 'ru', 'ba3b5585c9b14b2966768e5003f9dabd61b2ba22', $s256$Как стать лучше$s256$)
  , ('17359b8ec6399a4a', 'sv', 'ba3b5585c9b14b2966768e5003f9dabd61b2ba22', $s256$Bli bättre$s256$)
  , ('17359b8ec6399a4a', 'uk', 'ba3b5585c9b14b2966768e5003f9dabd61b2ba22', $s256$Як стати кращим$s256$)
  , ('18a1d1922241aa36', 'es', 'ba1d95f2de6da3db559cea3ba7bdc3d360dd4e35', $s256$El mod y vanilla$s256$)
  , ('18a1d1922241aa36', 'ru', 'ba1d95f2de6da3db559cea3ba7bdc3d360dd4e35', $s256$Мод и ваниль$s256$)
  , ('18a1d1922241aa36', 'sv', 'ba1d95f2de6da3db559cea3ba7bdc3d360dd4e35', $s256$Modden & vanilla$s256$)
  , ('18a1d1922241aa36', 'uk', 'ba1d95f2de6da3db559cea3ba7bdc3d360dd4e35', $s256$Мод і ваніль$s256$)
  , ('1bd91200b53d69fb', 'es', 'bdc8edc8e6f87a7432574daa3dfd55564ef74fdd', $s256$Qué ven los jugadores sin mod$s256$)
  , ('1bd91200b53d69fb', 'ru', 'bdc8edc8e6f87a7432574daa3dfd55564ef74fdd', $s256$Что видят игроки без мода$s256$)
  , ('1bd91200b53d69fb', 'sv', 'bdc8edc8e6f87a7432574daa3dfd55564ef74fdd', $s256$Vad omoddade spelare ser$s256$)
  , ('1bd91200b53d69fb', 'uk', 'bdc8edc8e6f87a7432574daa3dfd55564ef74fdd', $s256$Що бачать гравці без мода$s256$)
  , ('2423e49b4ee3ddaf', 'es', '98eb77f46816e71dab3df085044de8ba26f2542a', $s256$Los títulos son las etiquetas cortas que se muestran junto a tu nombre por todo el mod - filas de la clasificación, Series recientes, Récords, Comparar y cada mensaje de chat T que envías. Puedes poseer cuantos quieras, pero solo uno está activo a la vez: elígelo en la pestaña Tienda con <color=#7FD4FF>Activar</color>.

<color=#FFD94D><b>RANGO ACTUAL - GRATIS PARA TODOS</b></color>

<color=#7FD4FF>Rango actual</color> cuesta 0 de oro y está en la tienda para todos los jugadores. Es dinámico: allá donde se muestre, enseña el nombre de tu rango 1v1 en vivo con el color de ese rango, resuelto en el momento de dibujarse. Sube de rango y el título se mejora solo; baja de rango y también te sigue. La escalera detrás tiene 25 peldaños, desde Principiante I con 0 de rating hasta Gran Maestro V con 2610.

<color=#FFD94D><b>TÍTULOS DE PODIO</b></color>

Hay tres títulos de podio, uno por escalera ranked: 1v1, 2v2 y FFA. Cada uno se otorga de forma permanente al entrar en el top 3 visible de esa tabla <color=#8A8A93>(la comprobación corre sobre una tabla cacheada, así que el otorgamiento puede llegar un minuto o dos después de tu subida)</color>. Una tabla solo lista jugadores con al menos una serie contada - o, en FFA, una partida registrada - así que una cuenta recién creada no puede ocupar un podio.

Lo interesante es cómo se dibuja:

- Mientras ocupas un puesto de podio, el título se muestra en vivo como <color=#FFD700>1.er Puesto</color>, <color=#C0C0C0>2.º Puesto</color> o <color=#CD7F32>3.er Puesto</color> en oro, plata o bronce - siempre tu posición ACTUAL, con un prefijo 2v2 o FFA en todas partes salvo en la propia tabla de esa escalera.
- <color=#FF6666>Fuera del podio, el título equipado no muestra nada en absoluto</color> hasta que vuelvas a subir al top 3. El otorgamiento es permanente; la exhibición es de alquiler.

Los títulos de podio nunca rotan por calendario y no pueden comprarse jamás. La única entrada es el top 3.

<color=#FFD94D><b>TÍTULOS SLAYER</b></color>

Dos trofeos legendarios por vencer a los nombres de la puerta:

<color=#7FD4FF>Sid Slayer</color> - gana una serie ranked 1v1 completada en la que Sid sea el perdedor. Se muestra en <color=#FF4655>rojo</color>.
<color=#7FD4FF>Stan Slayer</color> - gana una serie ranked 1v1 completada en la que Stan sea el perdedor. Se muestra en <color=#00E5FF>cian</color>.

Cada uno llega unido a su logro, que además paga <color=#7FE87F>1000 de oro</color> (ver <color=#7FD4FF>Guía de logros</color>). Quitarles un solo juego no basta - la serie tiene que completarse contigo como ganador.

<color=#FFD94D><b>TÍTULOS DE TRADUCTOR</b></color>

El trabajo de traducción verificado a través del portal de traducción otorga tres niveles. La unidad es una cadena publicada: una traducción aprobada en la que fuiste el proponente o el revisor - hacer ambos trabajos en la misma cadena cuenta una sola vez.

<color=#7FD4FF>Rosetta</color> (rara) - 10 cadenas publicadas. Paga 100 de oro.
<color=#7FD4FF>Dragomán</color> (épica) - 100 cadenas publicadas. Paga 300 de oro.
<color=#7FD4FF>Babel</color> (legendaria) - 1000 cadenas publicadas. Paga 1000 de oro.

<color=#FFD94D><b>TÍTULOS COMPRADOS</b></color>

Los títulos normales están en la tienda con un precio en oro y funcionan como cualquier otro cosmético: compra una vez, tuyo para siempre, póntelo cuando te apetezca.

<color=#FFD94D><b>EQUIPAR Y DÓNDE SE VEN LOS TÍTULOS</b></color>

- Los títulos ganados (podio, slayer, traductor) están ocultos del listado público de la tienda, pero cada uno que TÚ poseas aparece en tu propia vista de la tienda con su botón Activar. <color=#FF6666>Comprarlos siempre se rechaza</color> - ganarse el momento es la única moneda que aceptan.
- Equipar un título nuevo sustituye al anterior; los títulos nunca se acumulan.
- Los títulos se ven en las superficies propias del mod: la clasificación, Series recientes, Récords, Comparar, los paneles de stats, tus mensajes de chat T (en el color del título) y el puente de chat de Discord.
- Los títulos NO aparecen en la etiqueta de nombre sobre tu cabeza en partida, y los jugadores sin el mod nunca los ven - toda superficie de títulos vive en la interfaz del mod o en Discord.$s256$)
  , ('2423e49b4ee3ddaf', 'ru', '98eb77f46816e71dab3df085044de8ba26f2542a', $s256$Титулы - это короткие подписи, которые рендерятся рядом с твоим именем по всему моду: строки таблицы лидеров, Недавние серии, Рекорды, Сравнение и каждое твоё сообщение в T-чате. Владеть можно любым их числом, но активен один: выбери его на вкладке Магазин кнопкой <color=#7FD4FF>Включить</color>.

<color=#FFD94D><b>ТЕКУЩИЙ РАНГ - БЕСПЛАТНО ДЛЯ ВСЕХ</b></color>

<color=#7FD4FF>Текущий ранг</color> стоит 0 золота и лежит в магазине у каждого игрока. Он динамический: где бы он ни рендерился, он показывает твоё живое имя ранга 1v1 в цвете этого ранга, разрешаясь свежим в момент отрисовки. Поднялся в ранге - титул обновился сам; спустился - он последует и туда. Лестница за ним - 25 ступеней, от Новичок I на 0 рейтинга до Грандмастер V на 2610.

<color=#FFD94D><b>ТИТУЛЫ ПОДИУМА</b></color>

Титулов подиума три, по одному на каждую рейтинговую лестницу: 1v1, 2v2 и FFA. Каждый выдаётся навсегда, когда ты входишь в видимый топ-3 этой таблицы <color=#8A8A93>(проверка позиции идёт по кешированной таблице, так что выдача может отстать от твоего подъёма на минуту-другую)</color>. Таблица показывает только игроков хотя бы с одной зачтённой серией - или, для FFA, с одной записанной игрой, - так что свежий аккаунт держать подиум не может.

Самое интересное - рендер:

- Пока ты держишь место на подиуме, титул рендерится вживую как <color=#FFD700>1-е место</color>, <color=#C0C0C0>2-е место</color> или <color=#CD7F32>3-е место</color> в золоте, серебре или бронзе - всегда твоя ТЕКУЩАЯ позиция, с префиксом 2v2 или FFA везде, кроме таблицы самой этой лестницы.
- <color=#FF6666>Вне подиума надетый титул рендерится как ничто</color>, пока ты не заберёшься обратно в топ-3. Выдача навсегда; показ - в аренду.

Титулы подиума никогда не ротируются по расписанию и не могут быть куплены. Единственный вход - топ-3.

<color=#FFD94D><b>ТИТУЛЫ СЛЕЕРОВ</b></color>

Два легендарных трофея за победу над именами на двери:

<color=#7FD4FF>Sid Slayer</color> - выиграй завершённую рейтинговую серию 1v1, в которой Sid - проигравший. Рендерится <color=#FF4655>красным</color>.
<color=#7FD4FF>Stan Slayer</color> - выиграй завершённую рейтинговую серию 1v1, в которой Stan - проигравший. Рендерится <color=#00E5FF>циановым</color>.

Каждый приходит вместе со своим достижением, которое ещё и платит <color=#7FE87F>1000 золота</color> (см. <color=#7FD4FF>Гид по достижениям</color>). Снять с них одну игру мало - серия должна завершиться с тобой в роли победителя.

<color=#FFD94D><b>ТИТУЛЫ ПЕРЕВОДЧИКОВ</b></color>

Подтверждённая работа над переводами через портал переводов даёт три уровня. Единица - живая строка: одобренный перевод, где ты был автором или ревьюером; обе роли на одной строке всё равно считаются один раз.

<color=#7FD4FF>Розетта</color> (редкий) - 10 живых строк. Платит 100 золота.
<color=#7FD4FF>Драгоман</color> (эпический) - 100 живых строк. Платит 300 золота.
<color=#7FD4FF>Вавилон</color> (легендарный) - 1000 живых строк. Платит 1000 золота.

<color=#FFD94D><b>КУПЛЕННЫЕ ТИТУЛЫ</b></color>

Обычные титулы лежат в магазине с ценой в золоте и работают как любая косметика: купил один раз - владеешь навсегда, носи когда захочется.

<color=#FFD94D><b>НАДЕВАНИЕ И ГДЕ ТИТУЛЫ ВИДНЫ</b></color>

- Заработанные титулы (подиум, слееры, переводчики) скрыты из публичной витрины магазина, но каждый, которым владеешь ТЫ, виден в твоём собственном магазине со своей кнопкой Включить. <color=#FF6666>Покупка их всегда отклоняется</color> - единственная валюта, которую они принимают, - заработанный момент.
- Новый надетый титул заменяет старый; титулы никогда не складываются.
- Титулы видны на поверхностях самого мода: таблица лидеров, Недавние серии, Рекорды, Сравнение, панели статистики, твои сообщения в T-чате (в цвете титула) и мост чата в Discord.
- Титулы НЕ появляются на неймтеге над головой в игре, и игроки без мода их не видят никогда - каждая поверхность титулов живёт в UI мода или в Discord.$s256$)
  , ('2423e49b4ee3ddaf', 'sv', '98eb77f46816e71dab3df085044de8ba26f2542a', $s256$Titlar är de korta etiketterna som renderas bredvid ditt namn i hela modden - topplistrader, Senaste serier, Rekord, Jämför och varje T-chattmeddelande du skickar. Du kan äga hur många som helst, men bara en är aktiv i taget: välj den på Butik-fliken med <color=#7FD4FF>Aktivera</color>.

<color=#FFD94D><b>NUVARANDE RANG - GRATIS FÖR ALLA</b></color>

<color=#7FD4FF>Nuvarande rang</color> kostar 0 guld och ligger i butiken för varje spelare. Den är dynamisk: var den än renderas visar den ditt aktuella 1v1-rangnamn i rangens färg, uppslaget färskt vid renderingen. Ranka upp och titeln uppgraderar sig själv; ranka ner och den följer med dit också. Stegen bakom den har 25 pinnar, från Nybörjare I vid 0 i rating till Stormästare V vid 2610.

<color=#FFD94D><b>PODIETITLAR</b></color>

Det finns tre podietitlar, en per rankad stege: 1v1, 2v2 och FFA. Var och en ges permanent när du går in i den tavlans synliga topp 3 <color=#8A8A93>(positionskollen körs mot en cachad tavla, så tilldelningen kan släpa efter din klättring en minut eller två)</color>. En tavla listar bara spelare med minst en räknad serie - eller, för FFA, en registrerad match - så ett färskt konto kan inte hålla ett podium.

Renderingen är det intressanta:

- Medan du håller en podieplats renderas titeln live som <color=#FFD700>1:a plats</color>, <color=#C0C0C0>2:a plats</color> eller <color=#CD7F32>3:e plats</color> i guld, silver eller brons - alltid din NUVARANDE position, med prefixet 2v2 eller FFA överallt utom på den stegens egen tavla.
- <color=#FF6666>Utanför podiet renderas den utrustade titeln som ingenting alls</color> tills du klättrar tillbaka in i topp 3. Tilldelningen är permanent; visningen är hyrd.

Podietitlar roterar aldrig enligt schema och kan aldrig köpas. Enda vägen in är topp 3.

<color=#FFD94D><b>SLAYER-TITLAR</b></color>

Två legendariska troféer för att slå namnen på dörren:

<color=#7FD4FF>Sid Slayer</color> - vinn en avslutad ranked 1v1-serie där Sid är förloraren. Renderas <color=#FF4655>röd</color>.
<color=#7FD4FF>Stan Slayer</color> - vinn en avslutad ranked 1v1-serie där Stan är förloraren. Renderas <color=#00E5FF>cyan</color>.

Var och en kommer fäst vid sin prestation, som också betalar <color=#7FE87F>1000 guld</color> (se <color=#7FD4FF>Prestationsguide</color>). Att ta en enskild match av dem räcker inte - serien måste avslutas med dig som vinnare.

<color=#FFD94D><b>ÖVERSÄTTARTITLAR</b></color>

Verifierat översättningsarbete genom översättningsportalen ger tre nivåer. Enheten är en aktiv sträng: en godkänd översättning där du var förslagsställare eller granskare - att göra båda jobben på samma sträng räknas ändå en gång.

<color=#7FD4FF>Rosetta</color> (sällsynt) - 10 aktiva strängar. Betalar 100 guld.
<color=#7FD4FF>Dragoman</color> (episk) - 100 aktiva strängar. Betalar 300 guld.
<color=#7FD4FF>Babel</color> (legendarisk) - 1000 aktiva strängar. Betalar 1000 guld.

<color=#FFD94D><b>KÖPTA TITLAR</b></color>

Vanliga titlar ligger i butiken med ett guldpris och fungerar som vilken kosmetik som helst: köp en gång, äg för alltid, bär den när du känner för det.

<color=#FFD94D><b>ATT UTRUSTA, OCH VAR TITLAR SYNS</b></color>

- Förtjänade titlar (podium, slayer, översättare) är dolda i den publika butikslistan, men varje titel DU äger visas i din egen butiksvy med sin Aktivera-knapp. <color=#FF6666>Att köpa dem vägras alltid</color> - att förtjäna ögonblicket är den enda valuta de accepterar.
- Att utrusta en ny titel ersätter den gamla; titlar staplas aldrig.
- Titlar syns på moddens egna ytor: topplistan, Senaste serier, Rekord, Jämför, statistikpanelerna, dina T-chattmeddelanden (i titelns färg) och Discord-chattbryggan.
- Titlar visas INTE på namnskylten ovanför huvudet i spelet, och spelare utan modden ser dem aldrig - varje titelyta bor i moddens UI eller på Discord.$s256$)
  , ('2423e49b4ee3ddaf', 'uk', '98eb77f46816e71dab3df085044de8ba26f2542a', $s256$Титули - це короткі підписи, що рендеряться біля вашого імені по всьому моду: рядки таблиці лідерів, Останні серії, Рекорди, Порівняння і кожне ваше повідомлення в T-чаті. Володіти можна будь-якою кількістю, але активний лише один: оберіть його на вкладці Магазин через <color=#7FD4FF>Активувати</color>.

<color=#FFD94D><b>ПОТОЧНИЙ РАНГ - БЕЗКОШТОВНО ДЛЯ ВСІХ</b></color>

<color=#7FD4FF>Поточний ранг</color> коштує 0 золота і лежить у магазині для кожного гравця. Він динамічний: хоч би де він рендерився, він показує вашу живу назву рангу 1v1 у кольорі цього рангу, обчислену свіжою в момент рендера. Підніметеся рангом - титул оновиться сам; опуститеся - він піде за вами й туди. Драбина за ним має 25 щаблів, від Початківця I на 0 рейтингу до Грандмайстра V на 2610.

<color=#FFD94D><b>ПОДІУМНІ ТИТУЛИ</b></color>

Подіумних титулів три, по одному на кожну рейтингову драбину: 1v1, 2v2 і FFA. Кожен видається назавжди, щойно ви входите у видимий топ-3 тієї таблиці <color=#8A8A93>(перевірка позиції йде по кешованій таблиці, тож видача може відстати від вашого підйому на хвилину-дві)</color>. Таблиця показує лише гравців із принаймні однією зарахованою серією - а для FFA з однією записаною грою - тож свіжий акаунт подіум тримати не може.

Найцікавіше тут - рендеринг:

- Поки ви тримаєте місце на подіумі, титул рендериться наживо як <color=#FFD700>1-ше місце</color>, <color=#C0C0C0>2-ге місце</color> або <color=#CD7F32>3-тє місце</color> у золоті, сріблі чи бронзі - завжди ваша ПОТОЧНА позиція, з префіксом 2v2 або FFA скрізь, окрім таблиці самої цієї драбини.
- <color=#FF6666>Поза подіумом активований титул рендериться як ніщо</color>, поки ви не повернетеся в топ-3. Видача - назавжди; показ - в оренду.

Подіумні титули ніколи не ротуються за розкладом і їх не можна купити. Єдиний вхід - топ-3.

<color=#FFD94D><b>ТИТУЛИ SLAYER</b></color>

Два легендарні трофеї за перемогу над іменами на дверях:

<color=#7FD4FF>Sid Slayer</color> - виграйте завершену рейтингову серію 1v1, у якій програв Sid. Рендериться <color=#FF4655>червоним</color>.
<color=#7FD4FF>Stan Slayer</color> - виграйте завершену рейтингову серію 1v1, у якій програв Stan. Рендериться <color=#00E5FF>ціановим</color>.

Кожен приходить разом зі своїм досягненням, яке також платить <color=#7FE87F>1000 золота</color> (див. <color=#7FD4FF>Посібник із досягнень</color>). Забрати в них одну гру недостатньо - серія має завершитися з вами як переможцем.

<color=#FFD94D><b>ТИТУЛИ ПЕРЕКЛАДАЧІВ</b></color>

Підтверджена робота над перекладами через портал перекладів дає три рівні. Одиниця - живий рядок: схвалений переклад, де ви були автором або рецензентом - обидві ролі на тому самому рядку однаково рахуються один раз.

<color=#7FD4FF>Розетта</color> (рідкісний) - 10 живих рядків. Платить 100 золота.
<color=#7FD4FF>Драгоман</color> (епічний) - 100 живих рядків. Платить 300 золота.
<color=#7FD4FF>Вавилон</color> (легендарний) - 1000 живих рядків. Платить 1000 золота.

<color=#FFD94D><b>КУПЛЕНІ ТИТУЛИ</b></color>

Звичайні титули лежать у магазині з ціною в золоті й працюють як будь-яка косметика: купуєте раз, володієте назавжди, вдягаєте коли заманеться.

<color=#FFD94D><b>АКТИВАЦІЯ І ДЕ ТИТУЛИ ВИДНО</b></color>

- Зароблені титули (подіумні, slayer, перекладацькі) приховані з публічного списку магазину, але кожен, яким володієте ВИ, з’являється у вашому власному перегляді магазину з кнопкою Активувати. <color=#FF6666>Купівля їх завжди відхиляється</color> - єдина валюта, яку вони приймають, - зароблений момент.
- Активація нового титулу замінює старий; титули ніколи не складаються.
- Титули видно на власних поверхнях мода: таблиця лідерів, Останні серії, Рекорди, Порівняння, панелі статистики, ваші повідомлення в T-чаті (у кольорі титулу) і міст чату в Discord.
- Титули НЕ з’являються на неймтезі над головою в грі, і гравці без мода не бачать їх ніколи - кожна поверхня титулів живе в UI мода або в Discord.$s256$)
  , ('243cd0d8462d92a0', 'es', '15506e4394620a3ac95b282acc4f1601ce59df92', $s256$Los torneos son cuadros de doble eliminación de 8-16 jugadores con series al mejor de 3, gestionados de punta a punta por el mod y el bot. Hay dos tipos: <color=#7FD4FF>Sync</color> (todo el cuadro se juega en una sentada) y <color=#7FD4FF>Async</color> (cada partida tiene una semana para jugarse). Ambos son ranked - cada juego mueve tu rating 1v1 normal.

<color=#FFD94D><b>LOS DOS TIPOS</b></color>

<color=#7FD4FF>Sync</color> - semanal. El inicio por defecto es el sábado a mediodía, hora del Pacífico, pero el campo vota la hora real: al inscribirte marcas a qué horas de inicio puedes, entre 8 franjas en pasos de 6 horas alrededor de la hora por defecto. El torneo se cierra 48 horas antes del inicio POR DEFECTO - la hora votada puede quedar hasta un día a cada lado.

<color=#7FD4FF>Async</color> - se abre uno nuevo 2 días después de terminar el anterior. Las inscripciones duran 7 días, luego se cierra y empieza de inmediato. Cada partida tiene un plazo de 7 días (los check-ins pueden añadir un día), así que un cuadro completo tarda unas 6-9 semanas según lo rápido que juegue la gente.

<color=#FFD94D><b>INSCRIBIRSE</b></color>

- Inscríbete en la pestaña Torneos de F5. Hace falta una cuenta de Discord vinculada - el bot lo gestiona todo por MD (ver <color=#7FD4FF>El bot y los check-ins</color>).

- Las inscripciones sync deben marcar al menos una hora de inicio. Inscribirse de nuevo sustituye tus votos de hora.

- Puedes darte de baja durante la votación o tras el cierre, pero <color=#FF6666>no una vez el torneo está en marcha</color> - a partir de ahí, no presentarte es una derrota por incomparecencia y cuenta en tu % de incomparecencia.

- El campo se limita a 16. Las inscripciones que pasan del límite se vuelven <color=#7FD4FF>especulativas</color>: no juegan, pero son la reserva de reemplazo - si un jugador confirmado se va antes del inicio, el especulativo más fiable hereda su asiento. El orden para entrar entre los 16 (y salir de la reserva) va por % de incomparecencia primero, luego por hora de inscripción.

- Tu <color=#7FD4FF>% de incomparecencia</color> es una medida móvil de 90 días de los torneos a los que te inscribiste y luego faltaste. Las faltas viejas se van desvaneciendo a lo largo de los 90 días.

<color=#FFD94D><b>CÓMO FUNCIONA EL CIERRE</b></color>

- El sync se cierra 48 horas antes del inicio por defecto. Necesita al menos 8 jugadores confirmados Y una franja horaria a la que puedan al menos 8 inscritos (especulativos incluidos); si no, todo el torneo se aplaza una semana y tus votos se mantienen.

- La franja ganadora se convierte en la hora de inicio. <color=#FF6666>Si no marcaste la franja ganadora, tu inscripción se retira</color> - sin penalización, y el bot te explica por MD el porqué. Los especulativos ascienden a los asientos liberados.

- El sync también puede empezar antes: con al menos 8 jugadores dentro, si cada jugador confirmado pulsa <color=#7FD4FF>Forzar inicio</color> en la pestaña con menos de 10 minutos entre sí, el torneo empieza 10 minutos después.

- El async no tiene voto de hora - tras la ventana de inscripción de 7 días se cierra solo por número de jugadores y empieza de inmediato.

- El cierre congela el bote de premios según el número de jugadores confirmados y borra cualquier bloqueo de ranked entre participantes - inscribirte es aceptar jugar contra quien más se haya inscrito.

<color=#FFD94D><b>SEEDS Y EL CUADRO</b></color>

- Tu seed es tu rating 1v1 congelado al cierre; el rating más alto es el seed 1. El emparejamiento es la colocación estándar de cuadro, con los seeds 1 y 2 empezando en mitades opuestas. Los números de seed quedan ocultos hasta que el torneo empieza, así nadie puede deducir a su rival de la ronda 1 por adelantado.

- Con 9 a 15 jugadores el cuadro se construye para 16 y los mejores seeds reciben byes de primera ronda para rellenar el hueco.

- La doble eliminación en claro: pierde una partida del cuadro de ganadores y caes al cuadro de perdedores; pierde allí y estás fuera. El campeón del cuadro de perdedores se enfrenta al del cuadro de ganadores en la gran final - y si gana el del cuadro de perdedores, se juega una partida extra decisiva, porque el campeón del cuadro de ganadores aún no había perdido ninguna serie.

- Cada partida es un al mejor de 3, jugado como una serie ranked normal.

<color=#FFD94D><b>EL DÍA DE JUEGO SYNC</b></color>

El contrato entero es: <color=#7FE87F>ten ROUNDS abierto a la hora de inicio - estar en el menú principal vale.</color> El mod hace todo lo demás.

- Mientras ROUNDS corre, el mod hace ping al servidor cada 20 segundos; cuentas como presente mientras tu último ping tenga menos de 2 minutos. El menú F5 no necesita estar abierto nunca.

- Desde 15 minutos antes recibes un MD recordatorio y un banner de cuenta atrás en el juego; cada momento de partida lista tiene también su propio MD (ver <color=#7FD4FF>El bot y los check-ins</color>).

- Cuando tu partida está lista y ambos jugadores presentes, el mod te conecta automáticamente - banner verde, sonido de partida encontrada, parpadeo en la barra de tareas. Si estás en mitad de una partida casual recibes un banner rojo, y el mod te saca de esa sala sin penalización por desconexión.

- Las partidas dan 10 minutos de gracia para presentarse. Si tu rival nunca entra en tu sala, el mod te avisa a los 90 segundos y te devuelve al menú a los 6 minutos - sigues contando como listo, y el servidor le da la partida por perdida si no aparece.

- Entre tus partidas hay un respiro de 7 minutos con la siguiente sala ya preparada. Si ambos jugadores pulsan <color=#7FD4FF>Jugar Ahora</color> en la pestaña Torneos, empieza antes.

- El servidor elige la región de conexión de cada partida para ambos jugadores, así siempre caes en la misma sala tenga tu menú la región que tenga.

<color=#FFD94D><b>JUGAR UNA PARTIDA ASYNC</b></color>

- Cuando tu partida se activa, el bot os manda un MD a los dos con el plazo. No hay instante de inicio, ni autoconexión, ni código de sala del cuadro.

- Acuerda una hora con tu rival (usa /dm-opponent en Discord, o simplemente escríbele), y luego jugad una sala privada normal: menú principal, Online, Host Room, y uno le pasa al otro el código de 6 caracteres.

- El resultado se registra automáticamente siempre que ambos tengáis el mod corriendo con <color=#7FD4FF>Ranked activado</color> - el servidor liga la serie a vuestro emparejamiento del cuadro desde cualquier sala. El mod te enciende Ranked cuando una partida de torneo tuya está activa (ver <color=#7FD4FF>Plazos e incomparecencias</color>).

- En las últimas 24 horas antes del plazo el bot envía un MD de check-in; responder que planeáis jugar hoy extiende el plazo 24 horas, una vez por rival.$s256$)
  , ('243cd0d8462d92a0', 'ru', '15506e4394620a3ac95b282acc4f1601ce59df92', $s256$Турниры - это сетки double elimination на 8-16 игроков из серий до 2 побед, которые от и до ведут мод и бот. Их два вида: <color=#7FD4FF>Синхро</color> (вся сетка отыгрывается за один присест) и <color=#7FD4FF>Асинхро</color> (у каждого матча есть неделя, чтобы случиться). Оба рейтинговые - каждая игра двигает твой обычный рейтинг 1v1.

<color=#FFD94D><b>ДВА ВИДА</b></color>

<color=#7FD4FF>Синхро</color> - еженедельный. Старт по умолчанию - суббота, полдень по тихоокеанскому времени, но реальное время выбирают участники: при записи ты отмечаешь, какие времена старта тебе подходят, из 8 слотов с шагом 6 часов вокруг умолчания. Запись закрывается за 48 часов до старта ПО УМОЛЧАНИЮ - выбранное время может лежать до суток в любую сторону от него.

<color=#7FD4FF>Асинхро</color> - новый открывается через 2 дня после конца предыдущего. Запись идёт 7 дней, затем закрытие и немедленный старт. У каждого матча дедлайн 7 дней (чек-ины могут добавить день), так что полная сетка занимает примерно 6-9 недель, смотря как быстро люди играют.

<color=#FFD94D><b>ЗАПИСЬ</b></color>

- Записывайся на вкладке Турниры (F5). Нужен привязанный Discord - бот ведёт всё через ЛС (см. <color=#7FD4FF>Бот и чек-ины</color>).

- Синхро-запись должна отметить хотя бы одно время старта. Повторная запись заменяет твои голоса за время.

- Сняться можно во время голосования или после закрытия, но <color=#FF6666>не когда турнир уже идёт</color> - с этого момента неявка означает техпоражение и идёт в твой % неявок.

- Поле ограничено 16 местами. Записи сверх лимита становятся <color=#7FD4FF>запасными</color>: они не играют, но образуют пул замен - если подтверждённый игрок уходит до старта, его место наследует самый надёжный запасной. Порядок в 16 (и из пула) - сперва % неявок, затем время записи.

- Твой <color=#7FD4FF>% неявок</color> - скользящая мера за 90 дней: турниры, куда ты записался и не пришёл. Старые пропуски за 90 дней выцветают.

<color=#FFD94D><b>КАК РАБОТАЕТ ЗАКРЫТИЕ</b></color>

- Синхро закрывается за 48 часов до старта по умолчанию. Нужно минимум 8 подтверждённых игроков И один слот времени, подходящий хотя бы 8 записям (запасные считаются); иначе весь турнир сдвигается на неделю, а твои голоса переносятся.

- Победивший слот становится временем старта. <color=#FF6666>Если ты не отметил победивший слот, твоя запись снимается</color> - без штрафа, и бот напишет в ЛС, почему. Запасные повышаются на освободившиеся места.

- Синхро может стартовать и раньше: когда внутри минимум 8 игроков, все подтверждённые, нажавшие <color=#7FD4FF>Форс-старт</color> на вкладке в пределах 10 минут друг от друга, запускают турнир через 10 минут.

- У асинхро голосования за время нет - после 7-дневного окна записи он закрывается по одному числу игроков и стартует сразу.

- Закрытие фиксирует призовой фонд по числу подтверждённых игроков и снимает любые рейтинговые блокировки между участниками - записываясь, ты соглашаешься играть с любым записавшимся.

<color=#FFD94D><b>СИДЫ И СЕТКА</b></color>

- Твой сид - твой рейтинг 1v1, снятый при закрытии; высший рейтинг - сид 1. Пары - стандартная рассадка сетки, сиды 1 и 2 начинают в противоположных половинах. Номера сидов скрыты до старта турнира, чтобы никто заранее не вычислил соперника первого раунда.

- При 9-15 игроках сетка строится на 16, и верхние сиды получают пропуски первого раунда, закрывающие дыру.

- Double elimination по-простому: проиграл матч в верхней сетке - падаешь в нижнюю; проиграл там - выбыл. Чемпион нижней сетки встречает чемпиона верхней в гранд-финале - и если побеждает чемпион нижней, играется один дополнительный решающий матч, потому что чемпион верхней ещё не проигрывал ни одной серии.

- Каждый матч - серия до 2 побед, играется как обычная рейтинговая серия.

<color=#FFD94D><b>ИГРОВОЙ ДЕНЬ СИНХРО</b></color>

Весь контракт: <color=#7FE87F>держи ROUNDS открытым к времени старта - сидеть в главном меню нормально.</color> Остальное делает мод.

- Пока ROUNDS запущен, мод пингует сервер каждые 20 секунд; ты считаешься присутствующим, пока последнему пингу меньше 2 минут. Меню F5 открывать не нужно.

- За 15 минут до старта приходит напоминание в ЛС и внутриигровой баннер отсчёта; каждый момент готовности матча получает и своё ЛС (см. <color=#7FD4FF>Бот и чек-ины</color>).

- Когда твой матч готов и оба игрока присутствуют, мод соединяет вас автоматически - зелёный баннер, звук найденного матча, мигание в панели задач. Если ты посреди казуальной игры, вместо этого будет красный баннер, и мод вытащит тебя из той комнаты без штрафа за отключение.

- Матчи дают 10 минут льготы на явку. Если соперник так и не зашёл в твою комнату, мод предупредит на 90 секундах и вернёт тебя в меню через 6 минут - ты остаёшься готовым, и сервер отдаст матч тебе техпоражением, если он не покажется.

- Между твоими матчами - передышка в 7 минут с уже подготовленной следующей комнатой. Оба игрока, нажавшие <color=#7FD4FF>Играть сейчас</color> на вкладке Турниры, начинают раньше.

- Регион подключения каждого матча выбирает сервер для обоих игроков, так что вы всегда попадаете в одну комнату, какой бы регион ни стоял в твоём меню.

<color=#FFD94D><b>КАК ИГРАЕТСЯ АСИНХРО-МАТЧ</b></color>

- Когда твой матч оживает, бот пишет обоим в ЛС с дедлайном. Нет ни момента старта, ни автоподключения, ни кода комнаты из сетки.

- Договорись с соперником о времени (через /dm-opponent в Discord или просто напиши ему), затем сыграйте обычное приватное лобби: главное меню, Online, Host Room, и один шлёт другому 6-символьный код.

- Результат записывается автоматически, пока у вас обоих запущен мод с <color=#7FD4FF>включённым Ranked</color> - сервер привяжет серию к вашей паре в сетке из любой комнаты. Когда турнирный матч жив, мод сам включает тебе Ranked (см. <color=#7FD4FF>Дедлайны и техпоражения</color>).

- В последние 24 часа перед дедлайном бот присылает чек-ин; ответ, что вы планируете сыграть сегодня, продлевает дедлайн на 24 часа - один раз на соперника.$s256$)
  , ('243cd0d8462d92a0', 'sv', '15506e4394620a3ac95b282acc4f1601ce59df92', $s256$Turneringar är dubbelelimineringsbrackets för 8-16 spelare med serier i bäst av 3, körda från början till slut av modden och botten. Det finns två sorter: <color=#7FD4FF>Sync</color> (hela bracketen spelas i en sittning) och <color=#7FD4FF>Async</color> (varje match har en vecka på sig). Båda är rankade - varje match flyttar din vanliga 1v1-rating.

<color=#FFD94D><b>DE TVÅ SORTERNA</b></color>

<color=#7FD4FF>Sync</color> - varje vecka. Standardstarten är lördag klockan 12 Pacific-tid, men fältet röstar om den verkliga tiden: i anmälan markerar du vilka starttider du kan, bland 8 tider i 6-timmarssteg runt standarden. Turneringen låses 48 timmar före STANDARD-starten - den röstade tiden kan ligga upp till ett dygn åt endera hållet.

<color=#7FD4FF>Async</color> - en ny öppnar 2 dagar efter att den förra avslutats. Anmälan pågår i 7 dagar, sedan låses den och startar omedelbart. Varje match har en 7-dagars tidsfrist (incheckningar kan lägga till en dag), så en full bracket tar ungefär 6-9 veckor beroende på hur fort folk spelar.

<color=#FFD94D><b>ATT ANMÄLA SIG</b></color>

- Anmäl dig på F5-fliken Turneringar. Ett länkat Discord-konto krävs - botten sköter allt via DM (se <color=#7FD4FF>Botten & incheckningar</color>).

- Sync-anmälningar måste markera minst en starttid. Anmäler du dig igen ersätts dina tidsröster.

- Du kan avanmäla dig under röstningen eller efter låsningen, men <color=#FF6666>inte när turneringen väl är igång</color> - därifrån är att inte dyka upp en walkover, och det räknas på din uteblivande-%.

- Fältet har ett tak på 16. Anmälningar över taket blir <color=#7FD4FF>spekulativa</color>: de spelar inte, men de är reservpoolen - lämnar en bekräftad spelare före starten ärver den mest pålitliga spekulativa deras plats. Ordningen in bland de 16 (och ut ur poolen) går efter uteblivande-% först, sedan anmälningstid.

- Din <color=#7FD4FF>uteblivande-%</color> är ett rullande 90-dagarsmått på turneringar du anmält dig till och sedan missat. Gamla missar tonas bort över de 90 dagarna.

<color=#FFD94D><b>SÅ FUNGERAR LÅSNINGEN</b></color>

- Sync låses 48 timmar före standardstarten. Det kräver minst 8 bekräftade spelare OCH en tid som minst 8 anmälda (spekulativa inräknade) kan; annars skjuts hela turneringen en vecka och dina röster följer med.

- Den vinnande tiden blir starttiden. <color=#FF6666>Markerade du inte den vinnande tiden tas din anmälan bort</color> - inget straff, och botten DM:ar dig varför. Spekulativa befordras in på de friade platserna.

- Sync kan också starta tidigt: när minst 8 spelare är inne, och varje bekräftad spelare trycker <color=#7FD4FF>Tvångsstarta</color> på fliken inom 10 minuter från varandra, startar turneringen 10 minuter senare.

- Async har ingen tidsröstning - efter 7-dagarsfönstret låses den på spelarantalet ensamt och startar direkt.

- Låsningen fryser prispotten vid det bekräftade spelarantalet och rensar alla ranked-blockeringar mellan deltagare - att anmäla sig är att tacka ja till att spela mot vem som helst annan som anmält sig.

<color=#FFD94D><b>SEEDNING OCH BRACKETEN</b></color>

- Din seed är din 1v1-rating fryst vid låsningen; högst rating är seed 1. Parningen är standardplacering i bracket, med seed 1 och 2 i motsatta halvor. Seednumren hålls dolda tills turneringen startar, så ingen kan lista ut sin rond 1-motståndare i förväg.

- Med 9 till 15 spelare byggs bracketen för 16 och toppseedarna får friomgångar i rond 1 för att fylla gapet.

- Dubbeleliminering på ren svenska: förlora en match i vinnarbracketen och du faller ner i förlorarbracketen; förlora där och du är ute. Förlorarbrackets mästare möter vinnarbrackets mästare i den stora finalen - och om förlorarbrackets mästare vinner den spelas en extra avgörande match, eftersom vinnarbrackets mästare ännu inte hade förlorat någon serie.

- Varje match är en bäst av 3, spelad som en vanlig ranked-serie.

<color=#FFD94D><b>SYNC-SPELDAGEN</b></color>

Hela kontraktet är: <color=#7FE87F>ha ROUNDS öppet vid starttiden - att sitta i huvudmenyn duger fint.</color> Modden gör allt annat.

- Medan ROUNDS kör pingar modden servern var 20:e sekund; du räknas som närvarande medan din senaste ping är under 2 minuter gammal. F5-menyn behöver aldrig vara öppen.

- Från 15 minuter före får du en påminnelse-DM och en nedräkningsbanner i spelet; varje match-redo-ögonblick får också sin egen DM (se <color=#7FD4FF>Botten & incheckningar</color>).

- När din match är redo och båda spelarna är närvarande ansluter modden dig automatiskt - grön banner, matchhittad-ljud, blinkande aktivitetsfält. Är du mitt i en casual-match får du en röd banner i stället, och modden tar ut dig ur det rummet utan disconnect-straff.

- Matcher ger 10 minuters uppdykandefrist. Om din motståndare aldrig ansluter till ditt rum varnar modden dig vid 90 sekunder och skickar dig till menyn efter 6 minuter - du förblir redo, och servern ger dig matchen på walkover om de inte dyker upp.

- Mellan dina matcher finns en 7-minuters andhämtning med nästa rum redan förberett. Trycker båda spelarna <color=#7FD4FF>Spela nu</color> på Turneringar-fliken startar den tidigare.

- Servern väljer varje matchs anslutningsregion för båda spelarna, så ni landar alltid i samma rum oavsett vad din menyregion är satt till.

<color=#FFD94D><b>ATT SPELA EN ASYNC-MATCH</b></color>

- När din match går live DM:ar botten er båda med tidsfristen. Det finns inget startögonblick, ingen auto-anslutning och ingen rumskod från bracketen.

- Kom överens om en tid med din motståndare (använd /dm-opponent i Discord, eller skriv direkt), och spela sedan en vanlig privat lobby: huvudmenyn, Online, Host Room, och en av er skickar den andra 6-teckenskoden.

- Resultatet registreras automatiskt så länge ni båda har modden igång med <color=#7FD4FF>Ranked aktiverat</color> - servern binder serien till er bracketparning från vilket rum som helst. Modden slår på Ranked åt dig när en turneringsmatch är live (se <color=#7FD4FF>Tidsfrister & walkover</color>).

- Under de sista 24 timmarna före tidsfristen skickar botten en incheckning via DM; svarar du att ni tänker spela idag förlängs tidsfristen 24 timmar, en gång per motståndare.$s256$)
  , ('243cd0d8462d92a0', 'uk', '15506e4394620a3ac95b282acc4f1601ce59df92', $s256$Турніри - це сітки подвійного вибування на 8-16 гравців із серій best-of-3, які від початку до кінця ведуть мод і бот. Їх два види: <color=#7FD4FF>Sync</color> (уся сітка розігрується за один присіст) і <color=#7FD4FF>Async</color> (кожен матч має тиждень, щоб відбутися). Обидва рейтингові - кожна гра рухає ваш звичайний рейтинг 1v1.

<color=#FFD94D><b>ДВА ВИДИ</b></color>

<color=#7FD4FF>Sync</color> - щотижневий. Типовий старт - субота опівдні за тихоокеанським часом, але справжній час обирає поле: реєстрація включає позначення часів старту, які вам підходять, із 8 слотів кроком у 6 годин навколо типового. Турнір закривається за 48 годин до ТИПОВОГО старту - обраний час може лежати до доби в обидва боки від нього.

<color=#7FD4FF>Async</color> - новий відкривається через 2 дні після завершення попереднього. Реєстрація триває 7 днів, потім закриття і негайний старт. Кожен матч має 7-денний термін (чек-іни можуть додати день), тож повна сітка займає приблизно 6-9 тижнів, залежно від швидкості гравців.

<color=#FFD94D><b>РЕЄСТРАЦІЯ</b></color>

- Реєструйтеся на вкладці Турніри в F5. Потрібен прив’язаний Discord - бот веде все через DM (див. <color=#7FD4FF>Бот і чек-іни</color>).

- Реєстрація на Sync мусить позначити хоча б один час старту. Повторна реєстрація замінює ваші голоси за час.

- Знятися можна під час голосування або після закриття, але <color=#FF6666>не коли турнір уже йде</color> - відтоді неявка є технічною поразкою і рахується у ваш % неявок.

- Поле обмежене 16. Реєстрації понад ліміт стають <color=#7FD4FF>запасними</color>: вони не грають, але саме вони - пул заміни: якщо підтверджений гравець піде до старту, його місце успадковує найнадійніший запасний. Порядок у 16 (і з пулу) - спочатку за % неявок, потім за часом реєстрації.

- Ваш <color=#7FD4FF>% неявок</color> - ковзний 90-денний показник турнірів, куди ви зареєструвалися й не з’явилися. Старі пропуски за 90 днів вивітрюються.

<color=#FFD94D><b>ЯК ПРАЦЮЄ ЗАКРИТТЯ</b></color>

- Sync закривається за 48 годин до типового старту. Потрібно щонайменше 8 підтверджених гравців І один часовий слот, який підходить принаймні 8 реєстраціям (із запасними включно); інакше весь турнір зсувається на тиждень, а ваші голоси переносяться.

- Переможний слот стає часом старту. <color=#FF6666>Якщо ви не позначили переможний слот, вашу реєстрацію знято</color> - без штрафу, і бот напише в DM чому. Запасні підвищуються на звільнені місця.

- Sync може стартувати й раніше: щойно є принаймні 8 гравців, натискання <color=#7FD4FF>Примусовий старт</color> на вкладці кожним підтвердженим гравцем у межах 10 хвилин одне від одного запускає турнір через 10 хвилин.

- В Async голосування за час немає - після 7-денного вікна реєстрації він закривається лише за кількістю гравців і стартує одразу.

- Закриття фіксує призовий фонд за кількістю підтверджених гравців і знімає всі рейтингові блокування між учасниками - реєстрація означає згоду грати з будь-ким, хто теж зареєструвався.

<color=#FFD94D><b>ПОСІВ І СІТКА</b></color>

- Ваш посів - це рейтинг 1v1, зафіксований на закритті; найвищий рейтинг - посів 1. Розстановка - стандартне розміщення в сітці, посіви 1 і 2 починають у протилежних половинах. Номери посіву приховані до старту турніру, тож ніхто не вирахує свого суперника першого раунду наперед.

- З 9-15 гравцями сітка будується на 16, і верхні посіви отримують пропуски першого раунду, щоб закрити прогалину.

- Подвійне вибування простими словами: програєте матч верхньої сітки - падаєте в нижню; програєте там - ви вибули. Чемпіон нижньої сітки зустрічає чемпіона верхньої у гранд-фіналі - і якщо гранд-фінал виграє чемпіон нижньої, грається один додатковий вирішальний матч, бо чемпіон верхньої сітки ще не програв жодної серії.

- Кожен матч - best-of-3, грається як звичайна рейтингова серія.

<color=#FFD94D><b>ІГРОВИЙ ДЕНЬ SYNC</b></color>

Увесь контракт: <color=#7FE87F>тримайте ROUNDS відкритим на час старту - сидіти в головному меню цілком досить.</color> Решту робить мод.

- Поки ROUNDS запущений, мод пінгує сервер кожні 20 секунд; ви присутні, поки вашому останньому пінгу менш як 2 хвилини. Меню F5 відкривати не потрібно.

- За 15 хвилин ви отримуєте нагадування в DM і внутрішньоігровий банер зворотного відліку; кожен момент готовності матчу теж має власний DM (див. <color=#7FD4FF>Бот і чек-іни</color>).

- Коли ваш матч готовий і обидва гравці присутні, мод з’єднує вас автоматично - зелений банер, звук знайденого матчу, блимання панелі завдань. Якщо ви посеред звичайної гри, замість цього буде червоний банер, і мод витягне вас із тієї кімнати без штрафу за дисконект.

- Матчі дають 10 хвилин пільги на явку. Якщо суперник так і не зайде у вашу кімнату, мод попередить на 90-й секунді й поверне вас у меню через 6 хвилин - ви лишаєтеся готовим, і сервер зарахує матч вам, якщо вони не з’являться.

- Між вашими матчами - 7-хвилинний перепочинок із уже підготованою наступною кімнатою. Обидва гравці, натиснувши <color=#7FD4FF>Грати зараз</color> на вкладці Турніри, починають раніше.

- Регіон з’єднання кожного матчу для обох гравців обирає сервер, тож ви завжди потрапляєте в одну кімнату, хоч який регіон стоїть у вашому меню.

<color=#FFD94D><b>ЯК ГРАЄТЬСЯ ASYNC-МАТЧ</b></color>

- Коли ваш матч оживає, бот пише обом у DM із терміном. Немає ні моменту старту, ні автопід’єднання, ні коду кімнати від сітки.

- Домовтеся про час із суперником (/dm-opponent у Discord або просто напишіть їм), потім грайте звичайне приватне лобі: головне меню, Online, Host Room, і один надсилає другому 6-символьний код.

- Результат записується автоматично, поки у вас обох запущений мод з увімкненим <color=#7FD4FF>Ranked</color> - сервер прив’язує серію до вашої пари в сітці з будь-якої кімнати. Коли турнірний матч живий, мод вмикає Ranked за вас (див. <color=#7FD4FF>Терміни й технічні поразки</color>).

- В останні 24 години перед терміном бот надсилає чек-ін у DM; відповідь, що ви плануєте зіграти сьогодні, подовжує термін на 24 години, раз на суперника.$s256$)
  , ('24fd7e49c61320e1', 'es', '3ff9955dc97667e88bcef6f8331317d3909831ab', $s256$ROUNDS viene con bugs reales - algunos cosméticos, otros que deciden rondas. El catálogo: síntoma, causa real y si el mod lo repara. Detalles de las reparaciones: (ver <color=#7FD4FF>Arreglos de bugs del mod</color>).

<color=#FFD94D><b>BUGS DE INPUT Y DE SALA</b></color>

<color=#7FD4FF>La tecla Escape muere para siempre, o los inputs se congelan al encontrar partida</color> - el juego conmuta el input de todos los jugadores sin comprobar nulos; un jugador a medio aparecer rompe el bucle. <color=#7FE87F>Arreglado por el mod, siempre activo.</color>

<color=#7FD4FF>'No hay hueco para ponerse listo' - no puedes aparecer en una sala</color> - el juego intenta generar tu personaje antes de que estés realmente en una sala, crashea y nunca se recupera. <color=#7FE87F>Arreglado por el mod, siempre activo</color>; 30 segundos atascado te devuelve al menú.

<color=#7FD4FF>Escribir confirma una elección de carta, Enter abre la caja de código de sala, Espacio te pone listo a media frase</color> - tres sitios leen el teclado en bruto sin comprobar si hay una caja de texto abierta. <color=#7FE87F>Arreglado para el chat propio del mod</color>; la caja de chat vanilla conserva sus manías.

<color=#FFD94D><b>BUGS DE COMBATE</b></color>

<color=#7FD4FF>Tras una revancha, tu bloqueo entra en enfriamiento pero no absorbe nada - o Shield Charge deja de dispararse mientras el bloqueo básico funciona</color> - la limpieza entre juegos puede destruir objetos de carta a medias, dejando hooks muertos en tu bloqueo. <color=#7FE87F>Arreglado por el mod en todas partes</color> (ver <color=#7FD4FF>Bloqueo</color>).

<color=#7FD4FF>Las barras de vida con veneno no coinciden entre pantallas, y bloquear el veneno es una moneda al aire</color> - cada máquina hace correr su propia copia del veneno contra su propia copia de tu escudo; la vida nunca se resincroniza. <color=#7FE87F>Sustituido por el veneno con autoridad de la víctima del mod</color> cuando la víctima lleva el mod (ver <color=#7FD4FF>Veneno y daño en el tiempo</color>).

<color=#7FD4FF>Un tick de veneno mata a alguien durante la animación de ronda ganada, regalando una ronda fantasma</color> - el daño en el tiempo sigue cayendo después de decidirse la ronda. <color=#7FE87F>Arreglado en cada cliente con mod, en cualquier sala</color> - la protección completa solo necesita que el asiento anfitrión de la sala (normalmente con mod) también esté parcheado.

<color=#7FD4FF>Una bala sobrante del punto anterior te golpea justo después de reaparecer todos</color> - nada en vanilla despawnea las balas en el aire en el límite del punto. <color=#7FE87F>Arreglado: los clientes con mod limpian sus propias balas sobrantes.</color>

<color=#7FD4FF>Los disparos conectan a la vista pero no hacen daño en tu pantalla, o una bala de Drill a bocajarro se vuelve invisible</color> - los componentes especiales de la bala pueden registrarse en el orden equivocado en la máquina receptora. <color=#7FE87F>Arreglado por el mod en cualquier sala.</color>

<color=#7FD4FF>Grow te mata de un disparo salido de la nada</color> - más matemática rota que bug: el daño de Grow se acumula por fotograma en la máquina del tirador, así que los FPS bajos y los tirones lo multiplican una barbaridad. <color=#7FE87F>Normalizado por el mod en juego competitivo</color> (ver <color=#7FD4FF>Grow</color>).

<color=#7FD4FF>Tras un juego con Demonic Pact, las armas de fuego mantenido como Spray dejan de autodisparar toda la sesión</color> - la marca de no-autodisparo se copia en un solo sentido y nunca se restablece entre juegos. <color=#7FE87F>Arreglado por el mod en cualquier partida.</color>

<color=#7FD4FF>Radiance barre visiblemente a una multitud y golpea a una sola persona</color> - la onda solo comprueba al objetivo más cercano y se detiene tras un golpe. <color=#FF6666>Arreglado solo en FFA</color> - allí golpea a todos los que barre; los demás modos conservan vanilla.

<color=#7FD4FF>El texto de la carta Chase lista un bono de Vida</color> - datos muertos que el juego nunca aplica; la carta jamás lo ha otorgado. <color=#7FE87F>El mod arregla la etiqueta.</color>

<color=#7FD4FF>Que te ofrezcan una carta que ya tienes</color> - no es un bug; la segunda copia sube de nivel a la primera.

<color=#FFD94D><b>BUGS DE MODO Y VISUALES</b></color>

<color=#7FD4FF>En 2v2 o 1v2, quien elige carta está de pie en un escenario vacío, o se muestra el cuerpo equivocado eligiendo</color> - vanilla solo presenta a un elector por ronda, usando un número de equipo como número de jugador. <color=#7FE87F>Arreglado en salas de mod 2v2 y 1v2.</color>

<color=#7FD4FF>Phoenix revive a alguien en el aire - invisible, intocable, atascado</color> - la reanimación busca al jugador por posición en la lista, errónea cuando la lista ha cambiado (alguien que se fue del FFA), y la marca de muerte nunca se pone. <color=#7FE87F>Arreglado por el mod en todas partes.</color>

<color=#7FD4FF>El nombre de otro jugador se muestra como el literal PlayerName</color> - una búsqueda fallida del nombre de Steam nunca se reintenta. <color=#7FE87F>Arreglado: el mod reintenta la búsqueda (hasta 15 intentos en medio minuto) y repinta el nombre cuando llega.</color>

<color=#7FD4FF>El bucle de giro de una sierra suena para siempre, o el audio queda amortiguado toda la sesión</color> - los sonidos en bucle sobreviven a su dueño y agotan las voces del motor de sonido. <color=#7FE87F>Arreglado: los bucles filtrados se barren tras cada ronda.</color>

<color=#7FD4FF>Spam de errores inofensivo en el log durante las transiciones de mapa</color> - la animación de movimiento del mapa retiene referencias a piezas sustituidas en pleno movimiento. <color=#8A8A93>No arreglado - ruido benigno. (Lo que deba tocar el mapa en pleno movimiento, como las skins de mapa del propio mod, espera a que pase esa ventana.)</color>

<color=#FFD94D><b>DÓNDE CORREN LOS ARREGLOS</b></color>

Las protecciones contra crashes y las reparaciones de estados muertos corren en todas partes - reparan estados que vanilla nunca pretendió, sin cambiar ninguna regla. Los cambios de reglas están cerrados con llave: la lógica de modo necesita su propia sala creada por el mod, la normalización de Grow necesita a todos los combatientes con mod y consintiendo, y la autoridad del veneno sigue al jugador envenenado - una víctima sin mod conserva el veneno vanilla. <color=#7FE87F>Un jugador sin mod siempre recibe gameplay vanilla puro</color> - y lo único del mod que puede llegar a ver es el estilo del nombre (ver <color=#7FD4FF>Vanilla sigue siendo vanilla</color>).$s256$)
  , ('24fd7e49c61320e1', 'ru', '3ff9955dc97667e88bcef6f8331317d3909831ab', $s256$В ROUNDS есть настоящие баги - какие-то косметические, какие-то решают раунды. Каталог: симптом, реальная причина и чинит ли это мод. Детали ремонтов: (см. <color=#7FD4FF>Исправления багов в моде</color>).

<color=#FFD94D><b>БАГИ ВВОДА И ЛОББИ</b></color>

<color=#7FD4FF>Escape навсегда умер, или ввод замёрз в момент найденного матча</color> - игра переключает ввод у всех игроков без единой проверки на null; один наполовину заспавненный игрок роняет цикл. <color=#7FE87F>Исправлено модом, включено всегда.</color>

<color=#7FD4FF>«Нет места для готовности» - ты не можешь заспавниться в лобби</color> - игра пытается создать твоего персонажа до того, как ты реально в комнате, падает и не восстанавливается. <color=#7FE87F>Исправлено модом, включено всегда</color>; 30 секунд застревания возвращают в меню.

<color=#7FD4FF>Печать подтверждает пик карты, Enter открывает поле кода комнаты, Space жмёт готовность посреди фразы</color> - три места читают сырую клавиатуру, не проверяя, открыто ли текстовое поле. <color=#7FE87F>Исправлено для собственного чата мода</color>; ванильное поле чата сохраняет свои причуды.

<color=#FFD94D><b>БОЕВЫЕ БАГИ</b></color>

<color=#7FD4FF>После рематча блок уходит в откат, но ничего не поглощает - или Shield Charge перестаёт срабатывать при работающем базовом блоке</color> - снос объектов между играми может уничтожить карточные объекты наполовину, бросив на блоке мёртвые хуки. <color=#7FE87F>Исправлено модом везде</color> (см. <color=#7FD4FF>Блокирование</color>).

<color=#7FD4FF>Полоски здоровья при яде расходятся между экранами, а блок яда - подбрасывание монетки</color> - каждая машина тикает свою копию яда против своей копии твоего щита; здоровье никогда не пересинхронизируется. <color=#7FE87F>Заменено модовым ядом с авторитетом жертвы</color>, когда жертва на моде (см. <color=#7FD4FF>Яд и урон со временем</color>).

<color=#7FD4FF>Тик яда убивает кого-то во время анимации выигранного раунда, начисляя фантомный раунд</color> - урон со временем продолжает падать после решённого раунда. <color=#7FE87F>Исправлено на каждом модовом клиенте, в любой комнате</color> - для полной защиты нужно лишь, чтобы (обычно модовое) место хоста комнаты тоже было пропатчено.

<color=#7FD4FF>Оставшаяся с прошлого очка пуля бьёт тебя сразу после общего респавна</color> - в ванили ничто не убирает пули в воздухе на границе очка. <color=#7FE87F>Исправлено: модовые клиенты чистят свои оставшиеся пули.</color>

<color=#7FD4FF>Выстрелы видимо попадают, но не наносят урона на твоём экране, или дрель-пуля в упор становится невидимой</color> - особые компоненты пули могут зарегистрироваться в неправильном порядке на принимающей машине. <color=#7FE87F>Исправлено модом в любой комнате.</color>

<color=#7FD4FF>Grow ваншотит тебя из ниоткуда</color> - скорее сломанная математика, чем баг: урон Grow накапливается покадрово на машине стрелка, так что низкая частота кадров и фризы умножают его в разы. <color=#7FE87F>Нормализовано модом в соревновательной игре</color> (см. <color=#7FD4FF>Grow</color>).

<color=#7FD4FF>После одной игры с Demonic Pact пушки с зажимом вроде Spray перестают автострелять до конца сессии</color> - флаг запрета автоогня копируется в одну сторону и никогда не сбрасывается между играми. <color=#7FE87F>Исправлено модом в любой игре.</color>

<color=#7FD4FF>Radiance видимо проходит сквозь толпу и попадает в одного</color> - волна всегда проверяет только ближайшую цель и останавливается после одного попадания. <color=#FF6666>Исправлено только в FFA</color> - там она бьёт каждого, кого прошла; остальные режимы сохраняют ваниль.

<color=#7FD4FF>Текст карты Chase перечисляет бонус к здоровью</color> - мёртвые данные, которые игра никогда не применяет; карта его никогда не давала. <color=#7FE87F>Мод чинит подпись.</color>

<color=#7FD4FF>Тебе предлагают карту, которая у тебя уже есть</color> - не баг; вторая копия прокачивает первую.

<color=#FFD94D><b>БАГИ РЕЖИМОВ И ВИЗУАЛА</b></color>

<color=#7FD4FF>В 2v2 или 1v2 выбирающий стоит на пустой сцене, или выбирает не то тело</color> - ваниль представляет лишь одного пикера за раунд, используя номер команды как номер игрока. <color=#7FE87F>Исправлено в модовых комнатах 2v2 и 1v2.</color>

<color=#7FD4FF>Phoenix воскрешает кого-то в пустоту - невидимого, неуязвимого, застрявшего</color> - воскрешение находит игрока по позиции в списке, неверной, если список изменился (ушедший в FFA), а флаг смерти не выставляется. <color=#7FE87F>Исправлено модом везде.</color>

<color=#7FD4FF>Имя другого игрока показано как буквальная заглушка PlayerName</color> - неудачный запрос имени Steam не повторяется. <color=#7FE87F>Исправлено: мод повторяет запрос (до 15 попыток за полминуты) и перерисовывает имя, когда оно приходит.</color>

<color=#7FD4FF>Звук пилы крутится вечно, или звук на всю сессию становится глухим</color> - зацикленные звуки переживают владельца и лишают звуковой движок голосов. <color=#7FE87F>Исправлено: утёкшие циклы выметаются после каждого раунда.</color>

<color=#7FD4FF>Безвредный спам ошибок в логе при переходах карт</color> - анимация переезда карты держит ссылки на куски, заменённые посреди переезда. <color=#8A8A93>Не чинится - безобидный шум. (Всё, что должно трогать карту посреди переезда, вроде модовых скинов карт, обходит это окно стороной.)</color>

<color=#FFD94D><b>ГДЕ РАБОТАЮТ ФИКСЫ</b></color>

Защита от крашей и ремонт мёртвых состояний работают везде - они чинят состояния, которых ваниль не задумывала, не меняя правил. Изменения правил закрыты шлюзами: логике режимов нужна своя комната, выданная модом, нормализации Grow - все бойцы на моде и согласны, а авторитет яда следует за отравленным: жертва без мода сохраняет ванильный яд. <color=#7FE87F>Игрок без мода всегда получает чистый ванильный геймплей</color> - и единственное, что он вообще может увидеть от мода, - стиль неймтега (см. <color=#7FD4FF>Ваниль остаётся ванилью</color>).$s256$)
  , ('24fd7e49c61320e1', 'sv', '3ff9955dc97667e88bcef6f8331317d3909831ab', $s256$ROUNDS levereras med riktiga buggar - några kosmetiska, några som avgör ronder. Katalogen: symptom, verklig orsak, och om modden reparerar den. Reparationsdetaljer: (se <color=#7FD4FF>Buggfixar i modden</color>).

<color=#FFD94D><b>INPUT- OCH LOBBYBUGGAR</b></color>

<color=#7FD4FF>Escape-tangenten permanent död, eller inputs frusna när en match hittas</color> - spelet växlar input över alla spelare utan nullkontroller; en halvspawnad spelare kraschar loopen. <color=#7FE87F>Fixad av modden, alltid på.</color>

<color=#7FD4FF>'Ingen plats att bli redo på' - du kan inte spawna in i en lobby</color> - spelet försöker spawna din karaktär innan du faktiskt är i ett rum, kraschar och återhämtar sig aldrig. <color=#7FE87F>Fixad av modden, alltid på</color>; 30 sekunder fast skickar dig tillbaka till menyn.

<color=#7FD4FF>Att skriva bekräftar ett kortval, Enter öppnar rumskodsrutan, mellanslag gör dig redo mitt i en mening</color> - tre ställen läser det råa tangentbordet utan att kolla efter en öppen textruta. <color=#7FE87F>Fixad för moddens egen chatt</color>; vanillas chattruta behåller sina egenheter.

<color=#FFD94D><b>STRIDSBUGGAR</b></color>

<color=#7FD4FF>Efter en rematch går ditt block på cooldown men absorberar ingenting - eller Shield Charge slutar avfyras medan basblocket fungerar</color> - nedmonteringen mellan matcher kan förstöra kortobjekt halvvägs och strandsätta döda krokar på ditt block. <color=#7FE87F>Fixad av modden överallt</color> (se <color=#7FD4FF>Blockering</color>).

<color=#7FD4FF>Gift-hälsomätare skiljer sig mellan skärmar, och att blocka gift är en slantsingling</color> - varje maskin tickar sin egen kopia av giftet mot sin egen kopia av din sköld; hälsa omsynkas aldrig. <color=#7FE87F>Ersatt av moddens offerauktoritativa gift</color> när offret kör modden (se <color=#7FD4FF>Gift & skada över tid</color>).

<color=#7FD4FF>En gifttick dödar någon under vunnen-rond-animationen och delar ut en fantomrond</color> - skada över tid fortsätter landa efter att ronden är avgjord. <color=#7FE87F>Fixad på varje moddad klient, i vilket rum som helst</color> - fullt skydd kräver bara att rummets (oftast moddade) värdplats också är patchad.

<color=#7FD4FF>En kvarbliven kula från förra poängen träffar dig strax efter att alla respawnat</color> - inget i vanilla despawnar kulor i luften vid poänggränsen. <color=#7FE87F>Fixad: moddade klienter rensar sina egna kvarblivna kulor.</color>

<color=#7FD4FF>Skott träffar synligt men gör ingen skada på din skärm, eller en Drill-kula på nära håll blir osynlig</color> - kulans specialkomponenter kan registreras i fel ordning på den mottagande maskinen. <color=#7FE87F>Fixad av modden i vilket rum som helst.</color>

<color=#7FD4FF>Grow one-shottar dig från ingenstans</color> - trasig matte mer än en bugg: Grows skada ackumuleras per bildruta på skyttens maskin, så låga bildfrekvenser och hack multiplicerar den massivt. <color=#7FE87F>Normaliserad av modden i tävlingsspel</color> (se <color=#7FD4FF>Grow</color>).

<color=#7FD4FF>Efter en match med Demonic Pact slutar håll-för-att-skjuta-vapen som Spray att autoskjuta hela sessionen</color> - ingen-autoeld-flaggan kopieras åt ett håll och nollställs aldrig mellan matcher. <color=#7FE87F>Fixad av modden i vilken match som helst.</color>

<color=#7FD4FF>Radiance sveper synligt genom en folkmassa och träffar en person</color> - vågen kollar bara det enskilt närmaste målet och stannar efter en träff. <color=#FF6666>Fixad enbart i FFA</color> - där träffar den alla den sveper över; övriga lägen behåller vanilla.

<color=#7FD4FF>Chases korttext listar en hälsobonus</color> - död data som spelet aldrig tillämpar; kortet har aldrig gett den. <color=#7FE87F>Modden fixar etiketten.</color>

<color=#7FD4FF>Att erbjudas ett kort du redan äger</color> - ingen bugg; den andra kopian levlar upp den första.

<color=#FFD94D><b>LÄGES- OCH GRAFIKBUGGAR</b></color>

<color=#7FD4FF>I 2v2 eller 1v2 står en kortväljare på en tom scen, eller fel kropp visas välja</color> - vanilla presenterar bara en väljare per rond, och använder ett lagnummer som spelarnummer. <color=#7FE87F>Fixad i 2v2- och 1v2-rum från modden.</color>

<color=#7FD4FF>Phoenix återupplivar någon ut i tomma intet - osynlig, oträffbar, fast</color> - återupplivningen hittar spelaren via listposition, fel så fort listan ändrats (en FFA-avhoppare), och dödsflaggan sätts aldrig. <color=#7FE87F>Fixad av modden överallt.</color>

<color=#7FD4FF>En annan spelares namn visas som den bokstavliga platshållaren PlayerName</color> - en misslyckad Steam-namnuppslagning görs aldrig om. <color=#7FE87F>Fixad: modden försöker igen (upp till 15 försök över en halv minut) och målar om namnet när det landar.</color>

<color=#7FD4FF>En sågs snurrloop spelar för evigt, eller ljudet blir dovt för sessionen</color> - loopande ljud överlever sin ägare och svälter ljudmotorn på röster. <color=#7FE87F>Fixad: läckta loopar sopas bort efter varje rond.</color>

<color=#7FD4FF>Ofarligt felspam i loggen under kartövergångar</color> - kartflyttsanimationen håller referenser till delar som ersätts mitt i flytten. <color=#8A8A93>Inte fixad - godartat brus. (Allt som måste röra kartan mitt i flytten, som moddens egna kartskins, väntar ut det fönstret i stället.)</color>

<color=#FFD94D><b>VAR FIXARNA KÖRS</b></color>

Kraschskydd och reparationer av döda tillstånd körs överallt - de reparerar tillstånd som vanilla aldrig avsåg, utan att ändra någon regel. Regeländringar är grindade: lägeslogik kräver sitt eget modd-utfärdade rum, Grow-normaliseringen kräver att varje fighter är moddad och samtyckande, och giftauktoriteten följer den förgiftade spelaren - ett omoddat offer behåller vanilla-gift. <color=#7FE87F>En spelare utan modden får alltid ren vanilla-gameplay</color> - och det enda de någonsin kan se av modden är namnskyltsstil (se <color=#7FD4FF>Vanilla förblir vanilla</color>).$s256$)
  , ('24fd7e49c61320e1', 'uk', '3ff9955dc97667e88bcef6f8331317d3909831ab', $s256$ROUNDS постачається зі справжніми багами - якісь косметичні, якісь вирішують раунди. Каталог: симптом, справжня причина і чи лагодить це мод. Деталі ремонтів: (див. <color=#7FD4FF>Виправлення багів у моді</color>).

<color=#FFD94D><b>БАГИ ВВОДУ І ЛОБІ</b></color>

<color=#7FD4FF>Клавіша Escape мертва назавжди, або ввід замерзає в момент знайденого матчу</color> - гра перемикає ввід усім гравцям без перевірок на null; один напівзаспавнений гравець валить цикл. <color=#7FE87F>Виправлено модом, завжди ввімкнено.</color>

<color=#7FD4FF>«Немає місця, щоб приготуватися» - ви не можете заспавнитися в лобі</color> - гра намагається заспавнити вашого персонажа до того, як ви реально в кімнаті, падає і не відновлюється. <color=#7FE87F>Виправлено модом, завжди ввімкнено</color>; 30 секунд застрягання повертають вас у меню.

<color=#7FD4FF>Набір тексту підтверджує вибір карти, Enter відкриває поле коду кімнати, Space готує вас посеред речення</color> - три місця читають сиру клавіатуру, не перевіряючи відкритого текстового поля. <color=#7FE87F>Виправлено для власного чату мода</color>; ванільне поле чату зберігає свої дивацтва.

<color=#FFD94D><b>БОЙОВІ БАГИ</b></color>

<color=#7FD4FF>Після рематчу блок іде на відкат, але нічого не поглинає - або Shield Charge перестає спрацьовувати, хоча базовий блок працює</color> - розбирання між іграми може знищити об’єкти карт наполовину, лишивши на блоці мертві гачки. <color=#7FE87F>Виправлено модом скрізь</color> (див. <color=#7FD4FF>Блокування</color>).

<color=#7FD4FF>Смужки здоров’я з отрутою розходяться між екранами, а блокування отрути - підкидання монетки</color> - кожна машина тікає власну копію отрути проти власної копії вашого щита; здоров’я ніколи не пересинхронізується. <color=#7FE87F>Замінено модовою отрутою з авторитетом жертви</color>, коли жертва має мод (див. <color=#7FD4FF>Отрута та поступова шкода</color>).

<color=#7FD4FF>Тік отрути вбиває когось під час анімації виграного раунду, даруючи фантомний раунд</color> - поступова шкода продовжує падати після того, як раунд вирішено. <color=#7FE87F>Виправлено на кожному клієнті з модом, у будь-якій кімнаті</color> - для повного захисту потрібне лише пропатчене (зазвичай модове) місце хоста кімнати.

<color=#7FD4FF>Залишкова куля з попереднього очка влучає у вас одразу після респавну всіх</color> - у ванілі ніщо не деспавнить кулі в повітрі на межі очка. <color=#7FE87F>Виправлено: клієнти з модом прибирають власні залишкові кулі.</color>

<color=#7FD4FF>Постріли видимо влучають, але не завдають шкоди на вашому екрані, або впритул пущена куля з Drill стає невидимою</color> - особливі компоненти кулі можуть зареєструватися в неправильному порядку на машині-отримувачі. <color=#7FE87F>Виправлено модом у будь-якій кімнаті.</color>

<color=#7FD4FF>Grow ваншотить вас нізвідки</color> - радше зламана математика, ніж баг: шкода Grow нарощується щокадру на машині стрільця, тож низька частота кадрів і фризи множать її колосально. <color=#7FE87F>Нормалізовано модом у змагальній грі</color> (див. <color=#7FD4FF>Grow</color>).

<color=#7FD4FF>Після однієї гри з Demonic Pact зброя з утриманням вогню, як-от Spray, перестає автоматично стріляти всю сесію</color> - прапорець без-автовогню копіюється в один бік і між іграми не скидається. <color=#7FE87F>Виправлено модом у будь-якій грі.</color>

<color=#7FD4FF>Radiance видимо прокочується крізь натовп і влучає в одну людину</color> - хвиля щоразу перевіряє лише єдину найближчу ціль і зупиняється після одного влучання. <color=#FF6666>Виправлено лише у FFA</color> - там вона влучає в кожного, кого прокочує; інші режими зберігають ваніль.

<color=#7FD4FF>Текст карти Chase обіцяє бонус здоров’я</color> - мертві дані, які гра ніколи не застосовує; карта ніколи цього не давала. <color=#7FE87F>Мод виправляє підпис.</color>

<color=#7FD4FF>Вам пропонують карту, яка у вас уже є</color> - не баг; друга копія прокачує першу.

<color=#FFD94D><b>БАГИ РЕЖИМІВ І ВІЗУАЛУ</b></color>

<color=#7FD4FF>У 2v2 чи 1v2 той, хто обирає карту, стоїть на порожній сцені, або обирати показано не те тіло</color> - ваніль показує лише одного обирача за раунд, використовуючи номер команди як номер гравця. <color=#7FE87F>Виправлено в модових кімнатах 2v2 і 1v2.</color>

<color=#7FD4FF>Phoenix оживляє когось у порожнечу - невидимий, невразливий, застряг</color> - оживлення шукає гравця за позицією у списку, що хибить, коли список змінився (вихід у FFA), а прапорець смерті не ставиться. <color=#7FE87F>Виправлено модом скрізь.</color>

<color=#7FD4FF>Ім’я іншого гравця показується як буквальний заповнювач PlayerName</color> - невдалий запит імені Steam ніколи не повторюється. <color=#7FE87F>Виправлено: мод повторює запит (до 15 спроб за пів хвилини) і перемальовує ім’я, коли воно приходить.</color>

<color=#7FD4FF>Звук пилки, що крутиться, грає вічно, або звук глушиться до кінця сесії</color> - зациклені звуки переживають власника і виїдають голоси звукового рушія. <color=#7FE87F>Виправлено: витеклі цикли вимітаються після кожного раунду.</color>

<color=#7FD4FF>Нешкідливий спам помилок у лозі під час переходів мапи</color> - анімація переїзду мапи тримає посилання на шматки, замінені посеред руху. <color=#8A8A93>Не виправлено - безпечний шум. (Усе, що мусить торкнутися мапи посеред переїзду, як-от власні скіни мап мода, натомість обходить це вікно з відкладенням.)</color>

<color=#FFD94D><b>ДЕ ПРАЦЮЮТЬ ВИПРАВЛЕННЯ</b></color>

Захист від крашів і ремонти мертвих станів працюють скрізь - вони лагодять стани, яких ваніль не задумувала, не змінюючи жодного правила. Зміни правил закриті воротами: логіка режимів потребує власної модової кімнати, нормалізація Grow - усіх бійців із модом і згодою, а авторитет отрути йде за отруєним гравцем - жертва без мода зберігає ванільну отруту. <color=#7FE87F>Гравець без мода завжди отримує чистий ванільний геймплей</color> - і єдине, що вони взагалі можуть побачити від мода, це стилізація неймтега (див. <color=#7FD4FF>Ваніль лишається ваніллю</color>).$s256$)
  , ('251cda79e9ae8cec', 'es', '040dc80582ef2677d666706843f7c57d1b9b407a', $s256$El veneno no tiene número de daño propio. El total que una bala de veneno inflige en el tiempo es igual al daño de esa bala en el instante en que te dio (el goteo más largo de Toxic Cloud redondea un par de puntos por encima) - por eso la misma bala verde a veces hace cosquillas y a veces mata de un golpe.

<color=#FFD94D><b>QUÉ HACE UN IMPACTO DE VENENO</b></color>

- El impacto en sí inflige solo <color=#7FD4FF>1 de daño</color> - pero knockback completo. El knockback escala con el daño de la bala aunque ese daño se convierta en veneno, y por eso un venenazo grande te lanza por el mapa mientras tu barra de vida apenas se mueve.
- Luego empieza el veneno: el daño completo de la bala, partido en ticks iguales repartidos uniformemente por la duración del veneno. Para la carta <color=#7FD4FF>Poison</color> eso son 10 ticks en 3 segundos - uno cada 0.3 segundos, un 10% del daño de la bala cada uno, y el primero cae en el instante en que la bala conecta. El veneno de <color=#7FD4FF>Toxic Cloud</color> gotea más largo y más fino: unos 17 ticks en 5 segundos. La cadencia corre en tiempo de juego (la cámara lenta estira los huecos).
- <color=#FF6666>Cada tick es letal por sí mismo.</color> No existe una regla de piedad de 'el veneno no puede rematarte'.

<color=#FFD94D><b>POR QUÉ A VECES MATA DE UN GOLPE</b></color>

El total es el daño de la bala DESPUÉS de todo lo que la infló: cartas de daño, tamaño de bala, crecimiento en vuelo (ver <color=#7FD4FF>Grow</color>), una carga de Empower. Una bala inflada a 500 de daño se vuelve diez ticks de 50 - 500 en total contra un jugador de 100 HP, muerto antes de la mitad del goteo. Nunca es el veneno lo que te mata de un golpe - es la bala de debajo, pagada a plazos.

<color=#FFD94D><b>BLOQUEAR TICKS - LA REGLA EXACTA</b></color>

Primero, la victoria gratis: bloquea la BALA de veneno y no hay veneno en absoluto - una bala absorbida no genera ninguno de sus efectos de impacto (ver <color=#7FD4FF>Bloqueo</color>). El resto de esta sección va de los ticks después de que una bala ya pasara.

Cada tick es un evento de daño bloqueable normal, comprobado contra tu ventana de bloqueo de 0.3 segundos.

- <color=#7FE87F>Un tick bloqueado se consume, no se retrasa.</color> El veneno marca esa porción como infligida antes de consultar tu escudo, así que una porción bloqueada se borra para siempre. El goteo nunca se alarga, nunca se pausa y nunca vuelve a por ella.
- Bloquear no cancela el goteo. Los ticks restantes siguen cayendo puntuales.
- La cuenta de supervivencia: cada tick es una parte igual del total - un 10% en Poison. Si el total de un veneno es exactamente el justo para matarte, borrar un tick significa que ya no puede matarte - y cada tick extra bloqueado es otra parte completa que te quedas.
- La cadencia juega a tu favor: los ticks llegan cada 0.3 segundos y una ventana de bloqueo dura exactamente 0.3 segundos, así que <color=#7FE87F>una pulsación bien medida borra uno o dos ticks - el 10-20% de un Poison, el 6-12% de un Toxic Cloud</color>. Ese es todo el mecanismo detrás de 'bloquea un tick o dos y sobrevives'.
- Los bloqueos de eco rearman la ventana sin reiniciar el enfriamiento, así que una pulsación puede cubrir más de un tick.
- <color=#FF6666>El sonido del tick suena incluso en los ticks bloqueados.</color> Fíate de la barra de vida, no del clic.

<color=#FFD94D><b>ACUMULACIÓN</b></color>

Cada impacto de veneno inicia su propio goteo independiente con su propio calendario. Nada se fusiona y nada se reinicia: dos balas de veneno son dos goteos completos, daño totalmente aditivo, cada uno con su ritmo. Que te marquen dos veces no reinicia el primer veneno - duplica el goteo.

<color=#FFD94D><b>MUERTE, REANIMACIONES, DECAY, ROBO DE VIDA</b></color>

- Morir o ser reanimado en una transición de ronda cancela todos los goteos al instante. El veneno nunca cruza de una ronda a otra.
- Las cartas tipo Decay convierten CADA golpe directo que recibe su dueño en un goteo repartido que hace tick cada cuarto de segundo. Aplican las mismas reglas: cada tick es bloqueable, y las porciones bloqueadas se borran.
- Cada tick no bloqueado alimenta los efectos al-hacer-daño del atacante: una build de robo de vida se cura de ti tick a tick.

<color=#FFD94D><b>LA SINCRONIZACIÓN DE VENENO DEL MOD</b></color>

El veneno vanilla está roto online. Cada máquina ejecuta su propia copia privada de tu veneno y la comprueba contra su propia copia de tu escudo; tu pulsación de bloqueo llega a cada máquina en un momento distinto; la vida nunca se resincroniza. Las pantallas discrepan en silencio sobre tu HP ('HP fantasma') hasta la siguiente ronda - y la discrepancia puede decidir una ronda, porque la muerte se dispara desde la primera máquina cuya copia cruce el cero.

El mod sustituye esto por autoridad de la víctima: <color=#7FE87F>tu propio cliente ejecuta el único bucle real de ticks del veneno que llevas encima</color>, juzga cada tick contra el estado real de tu escudo y anuncia cada veredicto. Cada máquina con mod - la tuya incluida - aplica solo veredictos anunciados, así que todas coinciden en cada tick, los totales y la cadencia siguen la matemática de vanilla, y bloquear funciona exactamente como se describe arriba.

Dónde está activo: cualquier sala online - salas de cola, códigos de sala privados, quickplay - siempre que el jugador envenenado lleve una build actual del mod. Las salas mixtas degradan con seguridad:

- En una sala de cola del mod con un jugador sin mod o desactualizado, los clientes con mod acuerdan que los ticks de veneno ignoran el bloqueo - la consistencia gana a la división del HP fantasma, pero allí bloquear no reducirá el veneno.
- En una partida privada por código con un jugador sin mod, los bloqueos de una víctima con mod siguen contando; una víctima sin mod recibe el comportamiento vanilla en bruto, desincronización incluida.
- Offline y sandbox son vanilla puro - una simulación única no tiene nada que desincronizar.$s256$)
  , ('251cda79e9ae8cec', 'ru', '040dc80582ef2677d666706843f7c57d1b9b407a', $s256$У яда нет собственного числа урона. Сумма, которую ядовитая пуля наносит со временем, равна стату урона этой пули в момент попадания (долгая капель Toxic Cloud выходит на пару процентов выше) - вот почему одна и та же зелёная пуля то щекочет, то ваншотит.

<color=#FFD94D><b>ЧТО ДЕЛАЕТ ЯДОВИТОЕ ПОПАДАНИЕ</b></color>

- Сам удар наносит лишь <color=#7FD4FF>1 урона</color> - но полный отброс. Отброс масштабируется от стата урона пули, даже когда этот урон превращён в яд, - вот почему большой ядовитый выстрел швыряет тебя через карту, а полоска здоровья почти не двигается.
- Затем начинается яд: полный урон пули, разбитый на равные тики, растянутые по длительности яда. Для карты <color=#7FD4FF>Poison</color> это 10 тиков за 3 секунды - один каждые 0.3 секунды, по 10% урона пули каждый, и первый падает в момент касания. Яд <color=#7FD4FF>Toxic Cloud</color> капает дольше и тоньше: около 17 тиков за 5 секунд. Ритм идёт по игровому времени (слоу-мо растягивает промежутки).
- <color=#FF6666>Каждый тик смертелен сам по себе.</color> Правила пощады «яд не может добить» не существует.

<color=#FFD94D><b>ПОЧЕМУ ОН ИНОГДА ВАНШОТИТ</b></color>

Сумма - это урон пули ПОСЛЕ всего, что его накачало: карты урона, размер пули, рост в полёте (см. <color=#7FD4FF>Grow</color>), заряд Empower. Пуля, накачанная до 500 урона, становится десятью тиками по 50 - 500 в игрока со 100 HP, мёртв до середины потока. Тебя никогда не ваншотит яд - тебя ваншотит пуля под ним, выплаченная в рассрочку.

<color=#FFD94D><b>БЛОК ТИКОВ - ТОЧНОЕ ПРАВИЛО</b></color>

Сначала бесплатная победа: заблокируй саму ядовитую ПУЛЮ - и яда не будет вовсе: поглощённая пуля не создаёт ни одного из своих эффектов при попадании (см. <color=#7FD4FF>Блокирование</color>). Остальной раздел - о тиках после пули, которая уже прошла.

Каждый тик - обычное блокируемое событие урона, сверяемое с твоим окном блока в 0.3 секунды.

- <color=#7FE87F>Заблокированный тик потрачен, а не отложен.</color> Яд помечает этот кусочек выданным ещё до проверки щита, так что заблокированный кусочек стёрт навсегда. Поток никогда не удлиняется, не встаёт на паузу и не возвращается за ним.
- Блок не отменяет поток. Оставшиеся тики падают по расписанию.
- Математика выживания: каждый тик - равная доля суммы, 10% у Poison. Если сумма яда - ровно столько, сколько нужно, чтобы тебя убить, стирание одного тика означает, что убить он уже не может, - а каждый следующий заблокированный тик - ещё одна полная доля, которую ты оставляешь себе.
- Ритм на твоей стороне: тики приходят каждые 0.3 секунды, а окно блока длится ровно 0.3 секунды, так что <color=#7FE87F>одно выверенное нажатие стирает один-два тика - 10-20% Poison, 6-12% Toxic Cloud</color>. Это и есть весь механизм за «заблокируй тик-другой - и выживешь».
- Эхо-блоки перевзводят окно без перезапуска отката, так что одно нажатие может накрыть больше одного тика.
- <color=#FF6666>Звук тика играет даже у заблокированных тиков.</color> Суди по полоске здоровья, не по щелчку.

<color=#FFD94D><b>СТАКИ</b></color>

Каждое ядовитое попадание запускает свой независимый поток на своей шкале времени. Ничего не сливается и не обновляется: две ядовитые пули - два полных потока, урон целиком складывается, каждый тикает по своему расписанию. Второй укус не сбрасывает первый яд - он удваивает капель.

<color=#FFD94D><b>СМЕРТЬ, ВОСКРЕШЕНИЯ, DECAY, ВАМПИРИЗМ</b></color>

- Смерть или воскрешение на переходе раунда мгновенно отменяет все бегущие потоки. Яд никогда не переносится через раунд.
- Карты класса Decay превращают КАЖДОЕ прямое попадание по владельцу в растянутый поток с тиком каждые четверть секунды. Правила те же: каждый тик блокируем, а заблокированные кусочки стёрты.
- Каждый незаблокированный тик кормит эффекты атакующего «при нанесении урона»: билд с вампиризмом лечится с тебя тик за тиком.

<color=#FFD94D><b>МОДОВАЯ СИНХРОНИЗАЦИЯ ЯДА</b></color>

Ванильный яд сломан онлайн. Каждая машина крутит свою личную копию твоего яда и сверяет её со своей копией твоего щита; твоё нажатие блока доходит до разных машин в разное время; здоровье никогда не пересинхронизируется. Экраны тихо расходятся о твоём HP («призрачное HP») до следующего раунда - и расхождение может решить раунд, потому что смерть стреляет с той машины, чья копия первой пересечёт ноль.

Мод заменяет это авторитетом жертвы: <color=#7FE87F>единственный настоящий цикл тиков яда на тебе крутит твой собственный клиент</color>, судит каждый тик по твоему истинному состоянию щита и объявляет каждый вердикт. Каждая модовая машина - включая твою - применяет только объявленные вердикты, так что все согласны о каждом тике, суммы и ритм следуют ванильной математике, а блок работает ровно как написано выше.

Где это активно: любая онлайн-комната - комнаты очередей, приватные коды комнат, quickplay - всякий раз, когда отравленный игрок на актуальной сборке мода. Смешанные комнаты откатываются безопасно:

- В модовой комнате очереди, где есть игрок без мода или с устаревшим модом, модовые клиенты договариваются, что тики яда игнорируют блок, - согласованность важнее раскола «призрачного HP», но блок там яд не уменьшит.
- В приватной игре по коду комнаты с игроком без мода блоки модовой жертвы всё равно считаются; жертва без мода получает сырое ванильное поведение, вместе с рассинхроном.
- Оффлайн и песочница - чистая ваниль: единственной симуляции нечему рассинхронизироваться.$s256$)
  , ('251cda79e9ae8cec', 'sv', '040dc80582ef2677d666706843f7c57d1b9b407a', $s256$Gift har ingen egen skadesiffra. Totalen en giftkula ger över tid är lika med kulans skadevärde i det ögonblick den träffade dig (Toxic Clouds längre dropp avrundar ett par procent över det) - vilket är varför samma gröna kula ibland kittlar och ibland one-shottar.

<color=#FFD94D><b>VAD EN GIFTTRÄFF GÖR</b></color>

- Själva anslaget gör bara <color=#7FD4FF>1 skada</color> - men full knockback. Knockback skalar med kulans skadevärde även när skadan omvandlats till gift, vilket är varför ett stort giftskott slungar dig över kartan medan din hälsomätare knappt rör sig.
- Sedan börjar giftet: kulans fulla skada, delad i lika stora ticks jämnt utspridda över giftets varaktighet. För kortet <color=#7FD4FF>Poison</color> är det 10 ticks över 3 sekunder - en var 0.3 sekund, 10% av kulans skada vardera, den första i samma stund som kulan träffar. <color=#7FD4FF>Toxic Cloud</color>s gift droppar längre och tunnare: cirka 17 ticks över 5 sekunder. Takten går på speltid (slow motion sträcker ut mellanrummen).
- <color=#FF6666>Varje tick är dödlig på egen hand.</color> Det finns ingen barmhärtighetsregel om att 'gift inte kan göra slut på dig'.

<color=#FFD94D><b>VARFÖR DET IBLAND ONE-SHOTTAR</b></color>

Totalen är kulans skada EFTER allt som pumpat upp den: skadekort, kulstorlek, tillväxt under flykten (se <color=#7FD4FF>Grow</color>), en Empower-laddning. En kula pumpad till 500 skada blir tio ticks på 50 - 500 totalt in i en spelare med 100 HP, död innan strömmen är halvvägs. Det är aldrig giftet som one-shottar dig - det är kulan under det, betald i delbetalningar.

<color=#FFD94D><b>ATT BLOCKA TICKS - DEN EXAKTA REGELN</b></color>

Först gratisvinsten: blocka själva gift-KULAN så uppstår inget gift alls - en absorberad kula spawnar inga av sina träffeffekter (se <color=#7FD4FF>Blockering</color>). Resten av det här avsnittet handlar om ticksen efter att en kula redan kommit igenom.

Varje tick är en vanlig blockbar skadehändelse, prövad mot ditt 0.3 sekunder långa blockfönster.

- <color=#7FE87F>En blockad tick förbrukas, fördröjs inte.</color> Giftet bokför den skivan som utdelad innan det kontrollerar din sköld, så en blockad skiva är utraderad för alltid. Strömmen förlängs aldrig, pausar aldrig och kommer aldrig tillbaka efter den.
- Att blocka avbryter inte strömmen. Resterande ticks landar enligt schema.
- Överlevnadsmatten: varje tick är en lika stor andel av totalen - 10% för Poison. Om ett gifts total är exakt nog att döda dig betyder en utraderad tick att det inte längre kan döda dig - och varje extra blockad tick är ytterligare en hel andel du behåller.
- Takten är på din sida: ticks kommer var 0.3 sekund och ett blockfönster varar exakt 0.3 sekunder, så <color=#7FE87F>ett vältajmat tryck raderar en eller två ticks - 10-20% av en Poison, 6-12% av en Toxic Cloud</color>. Det är hela mekanismen bakom 'blocka en tick eller två och du överlever'.
- Ekoblock aktiverar fönstret på nytt utan att starta om cooldownen, så ett tryck kan täcka mer än en tick.
- <color=#FF6666>Tickljudet spelas även för blockade ticks.</color> Döm efter hälsomätaren, inte efter klicket.

<color=#FFD94D><b>STAPLING</b></color>

Varje giftträff startar sin egen oberoende ström på sin egen tidslinje. Inget slås ihop och inget förnyas: två giftkulor är två fulla strömmar, skadan helt additiv, var och en tickande enligt sitt eget schema. Att bli träffad två gånger nollställer inte det första giftet - det dubblar droppet.

<color=#FFD94D><b>DÖD, ÅTERUPPLIVNING, DECAY, LIFESTEAL</b></color>

- Att dö eller återupplivas vid en rondövergång avbryter varje pågående ström omedelbart. Gift följer aldrig med över en rond.
- Kort av Decay-typ omvandlar VARJE direktträff innehavaren tar till en utspridd ström som tickar var kvarts sekund. Samma regler gäller: varje tick är blockbar, och blockade skivor raderas.
- Varje oblockerad tick matar angriparens vid-skada-effekter: en lifesteal-build helar av dig tick för tick.

<color=#FFD94D><b>MODDENS GIFTSYNK</b></color>

Vanilla-gift är trasigt online. Varje maskin kör sin egen privata kopia av ditt gift och prövar den mot sin egen kopia av din sköld; ditt blocktryck når olika maskiner vid olika tidpunkter; hälsa omsynkas aldrig. Skärmarna blir i tysthet oense om din HP ('spök-HP') fram till nästa rond - och oenigheten kan avgöra en rond, eftersom en död avfyras från den maskin vars kopia först korsar noll.

Modden ersätter detta med offerauktoritet: <color=#7FE87F>din egen klient kör den enda riktiga tickloopen för gift på dig</color>, dömer varje tick mot ditt sanna sköldtillstånd och annonserar varje utslag. Varje moddad maskin - din inräknad - tillämpar bara annonserade utslag, så alla är överens om varje tick, totalerna och takten följer vanillas matte, och blockning fungerar exakt som skrivet ovan.

Var det är aktivt: alla onlinerum - kö-rum, privata rumskoder, quickplay - närhelst den förgiftade spelaren kör en aktuell moddversion. Blandade rum faller tillbaka säkert:

- I ett kö-rum från modden som innehåller en omoddad eller föråldrad spelare enas de moddade klienterna om att giftticks ignorerar blockning - konsekvens slår spök-HP-splittringen, men blockning minskar inte gift där.
- I en privat rumskodsmatch med en omoddad spelare räknas ett moddat offers block fortfarande; ett omoddat offer får rått vanilla-beteende, desync inkluderad.
- Offline och sandbox är ren vanilla - en ensam simulering har inget att desynka.$s256$)
  , ('251cda79e9ae8cec', 'uk', '040dc80582ef2677d666706843f7c57d1b9b407a', $s256$В отрути немає власного числа шкоди. Сума, яку отруйна куля завдає з часом, дорівнює показнику шкоди цієї кулі в мить влучання (довша крапельниця Toxic Cloud округлює на пару відсотків вище) - ось чому та сама зелена куля іноді лоскоче, а іноді ваншотить.

<color=#FFD94D><b>ЩО РОБИТЬ ОТРУЙНЕ ВЛУЧАННЯ</b></color>

- Сам удар завдає лише <color=#7FD4FF>1 шкоди</color> - але з повним відкиданням. Відкидання масштабується від показника шкоди кулі, навіть коли цю шкоду перетворено на отруту, - тому велика отруйна куля жбурляє вас через мапу, хоча смужка здоров’я ледь ворухнулася.
- Потім стартує отрута: повна шкода кулі, розбита на рівні тіки, розкладені рівномірно по тривалості отрути. Для карти <color=#7FD4FF>Poison</color> це 10 тіків за 3 секунди - один кожні 0.3 секунди, по 10% шкоди кулі, перший падає в мить контакту. Отрута <color=#7FD4FF>Toxic Cloud</color> крапає довше й тонше: близько 17 тіків за 5 секунд. Ритм іде на ігровому часі (слоу-мо розтягує проміжки).
- <color=#FF6666>Кожен тік смертельний сам по собі.</color> Правила милосердя «отрута не може добити» не існує.

<color=#FFD94D><b>ЧОМУ ВОНА ІНОДІ ВАНШОТИТЬ</b></color>

Сума - це шкода кулі ПІСЛЯ всього, що її розігнало: карти шкоди, розмір кулі, ріст у польоті (див. <color=#7FD4FF>Grow</color>), заряд Empower. Куля, розігнана до 500 шкоди, стає десятьма тіками по 50 - 500 сумарно в гравця на 100 HP, мертвий ще до половини потоку. Ваншотить вас ніколи не отрута - а куля під нею, виплачена частинами.

<color=#FFD94D><b>БЛОКУВАННЯ ТІКІВ - ТОЧНЕ ПРАВИЛО</b></color>

Спершу безкоштовна перемога: заблокуйте саму отруйну КУЛЮ - і отрути не буде взагалі: поглинута куля не породжує жодного зі своїх ефектів при влучанні (див. <color=#7FD4FF>Блокування</color>). Решта розділу - про тіки після того, як куля вже пройшла.

Кожен тік - звичайна блокована подія шкоди, що перевіряється проти вашого вікна блоку 0.3 секунди.

- <color=#7FE87F>Заблокований тік спожито, а не відкладено.</color> Отрута позначає цю частку виданою ще до перевірки щита, тож заблокована частка стерта назавжди. Потік ніколи не подовжується, не стає на паузу і не повертається по неї.
- Блок не скасовує потік. Решта тіків падає за розкладом.
- Математика виживання: кожен тік - рівна частка суми, 10% для Poison. Якщо суми отрути рівно вистачає, щоб вас убити, стирання одного тіка означає, що вбити вона більше не може - і кожен додатково заблокований тік - ще одна повна частка, яку ви зберігаєте.
- Ритм на вашому боці: тіки приходять кожні 0.3 секунди, а вікно блоку триває рівно 0.3 секунди, тож <color=#7FE87F>одне влучне натискання стирає один-два тіки - 10-20% від Poison, 6-12% від Toxic Cloud</color>. Це і є весь механізм за порадою «заблокуй тік-другий і виживеш».
- Ехо-блоки зводять вікно заново без перезапуску відкату, тож одне натискання може накрити більш ніж один тік.
- <color=#FF6666>Звук тіка грає навіть для заблокованих тіків.</color> Судіть по смужці здоров’я, а не по клацанню.

<color=#FFD94D><b>СКЛАДАННЯ</b></color>

Кожне отруйне влучання запускає власний незалежний потік на власній шкалі часу. Ніщо не зливається і ніщо не оновлюється: дві отруйні кулі - два повні потоки, шкода повністю додається, кожен тікає за власним розкладом. Друге влучання не скидає першу отруту - воно подвоює крапельницю.

<color=#FFD94D><b>СМЕРТЬ, ОЖИВЛЕННЯ, DECAY, ЛАЙФСТІЛ</b></color>

- Смерть або оживлення на переході раунду миттєво скасовує кожен активний потік. Отрута ніколи не переноситься через раунд.
- Карти класу Decay перетворюють КОЖНЕ пряме влучання по власнику на розтягнутий потік із тіком кожні чверть секунди. Правила ті самі: кожен тік блокований, а заблоковані частки стерті.
- Кожен незаблокований тік годує ефекти нападника «при завданій шкоді»: лайфстіл-білд лікується з вас тік за тіком.

<color=#FFD94D><b>СИНХРОНІЗАЦІЯ ОТРУТИ В МОДІ</b></color>

Ванільна отрута онлайн зламана. Кожна машина ганяє власну приватну копію вашої отрути і звіряє її з власною копією вашого щита; ваше натискання блоку досягає різних машин у різний час; здоров’я ніколи не пересинхронізується. Екрани мовчки розходяться щодо вашого HP («примарне HP») аж до наступного раунду - і ця розбіжність може вирішити раунд, бо смерть спрацьовує з тієї машини, чия копія першою перетне нуль.

Мод замінює це авторитетом жертви: <color=#7FE87F>ваш власний клієнт ганяє єдиний справжній цикл тіків отрути на вас</color>, судить кожен тік проти вашого справжнього стану щита й оголошує кожен вердикт. Кожна машина з модом - і ваша теж - застосовує лише оголошені вердикти, тож усі вони згодні щодо кожного тіка, суми й ритм слідують ванільній математиці, а блокування працює рівно як написано вище.

Де це активно: будь-яка онлайн-кімната - кімнати черги, приватні коди кімнат, швидкі матчі - щоразу, коли отруєний гравець має актуальну збірку мода. Змішані кімнати безпечно відкочуються:

- У модовій кімнаті черги з гравцем без мода чи із застарілим модом клієнти з модом домовляються, що тіки отрути ігнорують блокування - узгодженість перемагає розкол примарного HP, але блок там отруту не зменшить.
- У приватній грі за кодом кімнати з гравцем без мода блоки жертви з модом усе одно рахуються; жертва без мода отримує сиру ванільну поведінку, разом із десинхом.
- Офлайн і пісочниця - чиста ваніль: єдиній симуляції нема з чим розходитись.$s256$)
  , ('292ca68628bacd23', 'es', 'd8eb5564ef93ac1a12635ff57f715edc227be02e', $s256$Silencia el audio del juego mientras la ventana no tiene el foco durante partidas en línea. El menú sigue sonando; el sonido vuelve en cuanto regresas.$s256$)
  , ('292ca68628bacd23', 'ru', 'd8eb5564ef93ac1a12635ff57f715edc227be02e', $s256$Глушит звук игры, пока окно не в фокусе во время онлайн-игры. В меню звук остаётся; он возвращается, как только вы вернётесь в окно.$s256$)
  , ('292ca68628bacd23', 'sv', 'd8eb5564ef93ac1a12635ff57f715edc227be02e', $s256$Tystar spelets ljud medan fönstret saknar fokus under onlinespel. Menyn hörs fortfarande; ljudet kommer tillbaka så fort du växlar tillbaka.$s256$)
  , ('292ca68628bacd23', 'uk', 'd8eb5564ef93ac1a12635ff57f715edc227be02e', $s256$Глушить звук гри, поки вікно не у фокусі під час онлайн-гри. У меню звук залишається; він повертається, щойно ви повернетеся у вікно.$s256$)
  , ('2d6511ec4b504a94', 'es', '628cdffdd054c7b2adf27040cb7f983e06e20fc0', $s256$Qué pueden ver y qué no los demás jugadores de tu mod. La versión corta es una garantía: <color=#7FE87F>lo único del mod que un rival sin mod puede llegar a ver es el estilo de tu nombre.</color> Todo lo demás o necesita el mod en el lado del espectador o nunca sale de tu máquina.

<color=#FFD94D><b>QUÉ VE UN RIVAL SIN MOD</b></color>

<color=#7FD4FF>Estilo del nombre - visible, con dos excepciones abajo.</color> El formato (negrita, cursiva, subrayado, tachado, flotante), los colores sólidos y neón, los tamaños, las transformaciones de mayúsculas y espaciado, el arcoíris y los degradados se dibujan en un cliente completamente sin mod. El mecanismo: el mod escribe el estilo en tu apodo de Photon como texto enriquecido, y las etiquetas de nombre propias de vanilla ya dibujan texto enriquecido - los jugadores metían etiquetas de estilo en bruto en sus nombres de Steam mucho antes de que este mod existiera. Por eso esta única clase tiene permitido cruzar.

Dos estilos de nombre son la excepción y se dibujan solo con mod:

- <color=#7FD4FF>Brillos</color> - aplicados localmente en pantallas con mod. Un rival vanilla ve tu nombre sin el brillo (cualquier otro estilo que acumules sí se ve), y sin ningún artefacto sobrante.
- <color=#7FD4FF>Tipografías</color> - un cambio de fuente local. Un rival vanilla ve tu nombre en la fuente por defecto.

Todo lo demás no muestra nada a un jugador sin mod:

- <color=#7FD4FF>Cosméticos de cara</color> - el ID del objeto viaja por el canal de caras propio de vanilla, pero un cliente vanilla no conoce el ID y dibuja un hueco VACÍO en su lugar. Sin crash, sin objeto sustituto - ese hueco queda desnudo en su pantalla, y las piezas de cara vanilla que lleves se ven con normalidad.
- <color=#7FD4FF>Estelas</color> - nada.
- <color=#7FD4FF>Colores de cuerpo</color> - ven el naranja/azul de equipo por defecto.
- <color=#7FD4FF>Auras</color> - nada.
- <color=#7FD4FF>Títulos, estilo de chat, Ocultar oro</color> - solo existen en superficies del mod (el menú F5, el chat T, Discord). Vanilla no tiene dónde mostrarlos.

<color=#FFD94D><b>QUÉ VE UN RIVAL CON MOD</b></color>

El catálogo entero: tus cosméticos de cara se dibujan completos (el arte viene dentro del mod), más tu estela, color de cuerpo, aura, brillo y tipografía del nombre, y tu título en las tablas y el chat.

Tres salvedades:

- Los espectadores con mod pueden desactivar individualmente estelas, colores de cuerpo y cosméticos animados en Ajustes - tu cosmético se dibuja solo para quien los dejó activados.
- Un color de cuerpo también se vuelve tu identidad de equipo en pantallas con mod: los anuncios de punto, los puntos del contador de rondas y la franja de marcador FFA lo usan. Quien tenga esa opción apagada ve los equipos vanilla de siempre.
- Los títulos nunca aparecen sobre tu cabeza en partida, para nadie. Se dibujan en las tablas de F5, en el chat T y en Discord, nada más.

<color=#FFD94D><b>QUÉ NUNCA SALE DE TU MÁQUINA</b></color>

- <color=#7FD4FF>Skins de mapa</color> - nunca se envían por red. Nadie ve tu skin de mapa, con mod o sin él: cada jugador ve su propia skin equipada, o vanilla. Equipar una cambia exactamente una pantalla - la tuya.
- <color=#7FD4FF>Color y forma del cursor</color> - tu propio cursor, en tu propia pantalla.

<color=#7FE87F>Tus cosméticos nunca producen un visual roto, un rectángulo vacío ni un crash en una pantalla sin mod.</color> <color=#8A8A93>Una implementación temprana del brillo sí filtraba un rectángulo visible a clientes vanilla - se eliminó exactamente por esa razón, y desde entonces los brillos se dibujan solo con mod.</color>$s256$)
  , ('2d6511ec4b504a94', 'ru', '628cdffdd054c7b2adf27040cb7f983e06e20fc0', $s256$Что другие игроки могут и не могут видеть от твоего мода. Короткая версия - гарантия: <color=#7FE87F>единственное, что соперник без мода вообще может увидеть от мода, - это стиль твоего неймтега.</color> Всему остальному нужен мод на стороне зрителя - либо оно вообще не покидает твою машину.

<color=#FFD94D><b>ЧТО ВИДИТ СОПЕРНИК БЕЗ МОДА</b></color>

<color=#7FD4FF>Стиль неймтега - виден, с двумя исключениями ниже.</color> Форматирование (жирный, курсив, подчёркивание, зачёркивание, парение), сплошные и неоновые цвета, размеры, трансформации регистра и интервалов, радуга и градиенты - всё рендерится на полностью немодифицированном клиенте. Механизм: мод записывает стиль в твой ник Photon как rich text, а ванильные подписи имён и так умеют rich text - игроки совали сырые теги стиля в имена Steam задолго до этого мода. Поэтому этому единственному классу и позволено пересекать границу.

Два стиля неймтега - исключение, они рендерятся только на модовой стороне:

- <color=#7FD4FF>Свечения</color> - применяются локально на модовых экранах. Ванильный соперник видит твоё имя без свечения (остальной наложенный стиль виден) и никаких артефактов-остатков.
- <color=#7FD4FF>Шрифты</color> - локальная замена шрифта. Ванильный соперник видит твоё имя в стандартном шрифте.

Всё остальное игроку без мода не показывает ничего:

- <color=#7FD4FF>Косметика лица</color> - ID предмета едет по ванильному каналу лиц, но ванильный клиент этот ID не знает и рендерит ПУСТОЙ слот. Ни краша, ни подменного предмета - на его экране этот слот голый, а ванильные части лица, которые ты носишь, показываются нормально.
- <color=#7FD4FF>Шлейфы</color> - ничего.
- <color=#7FD4FF>Цвета тела</color> - он видит стандартные командные оранжевый/синий.
- <color=#7FD4FF>Ауры</color> - ничего.
- <color=#7FD4FF>Титулы, стиль чата, Скрыть золото</color> - они существуют только на поверхностях мода (оверлей F5, T-чат, Discord). Ванили негде их показать.

<color=#FFD94D><b>ЧТО ВИДИТ СОПЕРНИК С МОДОМ</b></color>

Весь каталог: твоя косметика лица рендерится полностью (арт едет внутри мода), плюс твой шлейф, цвет тела, аура, свечение и шрифт неймтега и твой титул на таблицах и в чате.

Три оговорки:

- Модовые зрители могут по отдельности отключить шлейфы, цвета тела и анимированную косметику в Настройках - твоя косметика рендерится только у тех, кто это оставил включённым.
- Цвет тела на модовых экранах - ещё и твоя командная принадлежность: его используют объявления очков, точки счётчика раундов и полоса счёта FFA. Зритель с выключенной настройкой видит обычные ванильные команды.
- Титулы ни у кого не появляются над головой в матче. Они рендерятся на таблицах F5, в T-чате и в Discord.

<color=#FFD94D><b>ЧТО НИКОГДА НЕ ПОКИДАЕТ ТВОЮ МАШИНУ</b></color>

- <color=#7FD4FF>Скины карт</color> - вообще не сетевые. Твой скин карты не видит никто, с модом или без: каждый игрок видит свой надетый скин или ваниль. Надевание меняет ровно один экран - твой.
- <color=#7FD4FF>Цвет и форма курсора</color> - твой курсор, на твоём экране.

<color=#7FE87F>Твоя косметика никогда не порождает сломанный визуал, пустой прямоугольник или краш на экране без мода.</color> <color=#8A8A93>Одна ранняя реализация свечения действительно протекала видимым прямоугольником на ванильные клиенты - её убрали ровно поэтому, и с тех пор свечения рендерятся только на модовой стороне.</color>$s256$)
  , ('2d6511ec4b504a94', 'sv', '628cdffdd054c7b2adf27040cb7f983e06e20fc0', $s256$Vad andra spelare kan och inte kan se av din modd. Kortversionen är en garanti: <color=#7FE87F>det enda en motståndare utan modden någonsin kan se av modden är din namnskyltsstil.</color> Allt annat kräver antingen modden på betraktarens sida eller lämnar aldrig din maskin.

<color=#FFD94D><b>VAD EN OMODDAD MOTSTÅNDARE SER</b></color>

<color=#7FD4FF>Namnskyltsstil - synlig, med två undantag nedan.</color> Formatering (fet, kursiv, understruken, genomstruken, svävande), solida färger och neonfärger, storlekar, versal- och avståndstransformer, regnbågen och gradienterna renderas alla på en helt omoddad klient. Mekanismen: modden skriver stilen i ditt Photon-smeknamn som rich text, och vanillas egna namnetiketter renderar redan rich text - spelare stoppade råa stiltaggar i sina Steam-namn långt innan den här modden fanns. Det är därför just den klassen får korsa.

Två namnskyltsstilar är undantaget och renderas bara på moddsidan:

- <color=#7FD4FF>Glöd</color> - läggs på lokalt på moddade skärmar. En vanilla-motståndare ser ditt namn utan glöden (all annan stil du staplat syns fortfarande), och ingen kvarlämnad artefakt.
- <color=#7FD4FF>Typsnitt</color> - ett lokalt teckensnittsbyte. En vanilla-motståndare ser ditt namn i standardtypsnittet.

Allt annat visar en omoddad spelare ingenting:

- <color=#7FD4FF>Ansiktskosmetik</color> - artikel-ID:t färdas över vanillas egen ansiktskanal, men en vanilla-klient känner inte igen ID:t och renderar en TOM plats i stället. Ingen krasch, inget ersättningsobjekt - den platsen är bar på deras skärm, och vanilla-ansiktsdelar du bär syns som vanligt.
- <color=#7FD4FF>Spår</color> - ingenting.
- <color=#7FD4FF>Kroppsfärger</color> - de ser standardlagens orange/blå.
- <color=#7FD4FF>Auror</color> - ingenting.
- <color=#7FD4FF>Titlar, chattstil, Dölj guld</color> - dessa finns bara på moddytor (F5-overlayen, T-chatten, Discord). Vanilla har ingen plats att visa dem på.

<color=#FFD94D><b>VAD EN MODDAD MOTSTÅNDARE SER</b></color>

Hela katalogen: din ansiktskosmetik renderas fullt ut (konsten skeppas inuti modden), plus ditt spår, din kroppsfärg, din aura, din namnskyltsglöd och ditt typsnitt, och din titel på tavlorna och i chatten.

Tre förbehåll:

- Moddade betraktare kan individuellt välja bort spår, kroppsfärger och animerad kosmetik i Inställningar - din kosmetik renderas bara för betraktare som lämnat dem på.
- En kroppsfärg blir också din lagidentitet på moddade skärmar: poängutrop, rondräknarens prickar och FFA-poängremsan använder den. En betraktare med den inställningen av ser vanliga vanilla-lag.
- Titlar visas aldrig över ditt huvud i matchen, för någon. De renderas på F5-tavlorna, i T-chatten och på Discord.

<color=#FFD94D><b>VAD SOM ALDRIG LÄMNAR DIN MASKIN</b></color>

- <color=#7FD4FF>Kartskins</color> - nätverkas aldrig alls. Ingen ser ditt kartskin, moddad eller inte: varje spelare ser sitt eget utrustade skin, eller vanilla. Att utrusta ett ändrar exakt en skärm - din.
- <color=#7FD4FF>Pekarfärg och pekarform</color> - din egen pekare, på din egen skärm.

<color=#7FE87F>Din kosmetik ger aldrig en trasig grafik, en tom rektangel eller en krasch på en omoddad skärm.</color> <color=#8A8A93>En tidig glödimplementation läckte faktiskt en synlig rektangel till vanilla-klienter - den togs bort av exakt det skälet, och glöd har renderats enbart på moddsidan sedan dess.</color>$s256$)
  , ('2d6511ec4b504a94', 'uk', '628cdffdd054c7b2adf27040cb7f983e06e20fc0', $s256$Що інші гравці можуть і не можуть бачити з вашого мода. Коротка версія - гарантія: <color=#7FE87F>єдине, що суперник без мода може взагалі побачити від мода, - стилізація вашого неймтега.</color> Усе інше або потребує мода з боку глядача, або ніколи не покидає вашу машину.

<color=#FFD94D><b>ЩО БАЧИТЬ СУПЕРНИК БЕЗ МОДА</b></color>

<color=#7FD4FF>Стилізація неймтега - видима, з двома винятками нижче.</color> Форматування (жирний, курсив, підкреслення, закреслення, підвис), суцільні та неонові кольори, розміри, трансформації регістру й розрядки, райдуга та градієнти рендеряться на повністю ванільному клієнті. Механізм: мод записує стиль у ваш нікнейм Photon як rich text, а ванільні підписи імен уже рендерять rich text - гравці вставляли сирі теги стилю у свої імена Steam задовго до цього мода. Саме тому цьому єдиному класу дозволено проходити.

Два стилі неймтега - виняток, вони рендеряться лише на боці мода:

- <color=#7FD4FF>Світіння</color> - накладаються локально на екранах з модом. Ванільний суперник бачить ваше ім’я без світіння (решта нашарованої стилізації показується), і без залишкових артефактів.
- <color=#7FD4FF>Гарнітури</color> - локальна підміна шрифту. Ванільний суперник бачить ваше ім’я типовим шрифтом.

Усе решта не показує гравцеві без мода нічого:

- <color=#7FD4FF>Косметика обличчя</color> - ID предмета їде ванільним каналом облич, але ванільний клієнт не знає цього ID і рендерить ПОРОЖНІЙ слот. Без краху, без запасного предмета - той слот на їхньому екрані голий, а ванільні частини обличчя, які ви носите, показуються нормально.
- <color=#7FD4FF>Шлейфи</color> - нічого.
- <color=#7FD4FF>Кольори тіла</color> - вони бачать типові командні помаранчевий/синій.
- <color=#7FD4FF>Аури</color> - нічого.
- <color=#7FD4FF>Титули, стилізація чату, Приховати золото</color> - це існує лише на поверхнях мода (оверлей F5, T-чат, Discord). Ванілі нема де їх показати.

<color=#FFD94D><b>ЩО БАЧИТЬ СУПЕРНИК З МОДОМ</b></color>

Увесь каталог: ваша косметика обличчя рендериться повністю (арт їде всередині мода), плюс ваш шлейф, колір тіла, аура, світіння і гарнітура неймтега, і ваш титул на таблицях та в чаті.

Три застереження:

- Глядачі з модом можуть особисто вимкнути шлейфи, кольори тіла й анімовану косметику в Налаштуваннях - ваша косметика рендериться лише для тих, хто це лишив увімкненим.
- Колір тіла також стає вашою командною ідентичністю на екранах з модом: його використовують оголошення очок, крапки лічильника раундів і смуга рахунку FFA. Глядач із вимкненим налаштуванням бачить прості ванільні команди.
- Титули ніколи не з’являються над головою в матчі, ні для кого. Вони рендеряться на таблицях F5, у T-чаті та в Discord.

<color=#FFD94D><b>ЩО НІКОЛИ НЕ ПОКИДАЄ ВАШУ МАШИНУ</b></color>

- <color=#7FD4FF>Скіни мап</color> - взагалі не передаються мережею. Ваш скін мапи не бачить ніхто, з модом чи без: кожен гравець бачить власний вдягнений скін або ваніль. Вдягання скіна змінює рівно один екран - ваш.
- <color=#7FD4FF>Колір і форма курсора</color> - ваш курсор, на вашому екрані.

<color=#7FE87F>Ваша косметика ніколи не породжує зламаний візуал, порожній прямокутник чи краш на екрані без мода.</color> <color=#8A8A93>Одна рання реалізація світіння таки протікала видимим прямокутником на ванільні клієнти - її прибрали рівно з цієї причини, і відтоді світіння рендериться лише на боці мода.</color>$s256$)
  , ('304838dece8548b7', 'es', 'c56bfd5ef74259ffdcb3e6339e5ae62aabc44604', $s256$El reglamento de qué se registra y qué se descarta: partidas, series, desconexiones, apuestas. Si un resultado parece perdido, la razón casi siempre está en esta página.

<color=#FFD94D><b>NUNCA SE REGISTRA</b></color>

- Consentimiento de datos desactivado: el mod funciona totalmente offline. Nunca se envía nada salvo una comprobación de versión.
- Partidas offline, de práctica y de sandbox: el cliente nunca las reporta, y el servidor las rechaza como refuerzo.
- Los asientos de espectador no registran ni reportan nada.

<color=#FFD94D><b>RANKED O CASUAL</b></color>

- Cualquiera de los dos con el Ranked desactivado en una partida por código de sala - se juega como CASUAL. Se registra igualmente con stats y XP; nunca toca el rating (ver <color=#7FD4FF>Cómo se registran las partidas</color>).
- El rival nunca ha usado el mod - siempre casual, nunca se asciende. (Una serie viva sin terminar de una sentada anterior es lo único que mantiene el estado ranked a través de un hueco.)
- Apagar Ranked A MITAD DE SERIE no anula la serie. El al-mejor-de-3 en curso es tu registro de consentimiento; sus juegos siguen siendo ranked.
- Una partida reportada como casual se ASCIENDE a ranked cuando el servidor puede ver que ambos jugadores llevan el mod, ambos tienen Ranked activado y la sentada está viva.
- Un participante con ban de ranked fuerza el 1v1 a casual en el momento del reporte - incluso en sala de cola, incluso a mitad de serie. (Los demás modos cierran la puerta a los baneados directamente.)
- Las salas creadas por el mod llevan el consentimiento incluido; encolarse es consentir. La cola ranked, el 2v2 y los torneos puntúan; las salas FFA ranked puntúan y las casual no; el 1v2 registra sin puntuar.

<color=#FFD94D><b>DESCONEXIONES - 1V1</b></color>

- Dejas una partida para entrar a tu partida ranked de cola - la partida que dejaste se cancela: no se registra nada, no se apunta salida.
- El rival se desconecta con 4-4 - te llevas la victoria, registrada 5-4.
- El rival se desconecta mientras tú tienes 4 rondas - te llevas la victoria con el marcador vigente.
- Cualquier otra DC - <color=#FF6666>la partida se cancela y no se registra ningún resultado</color>, incluso si quien se fue iba ganando. Nadie recibe una victoria gratis y nadie se traga una derrota injusta (la salida en sí puede quedar apuntada - ver abajo).
- % de salida ranked: se apunta una DC contra quien se va cuando la partida ACTUAL tuvo juego con sustancia (2 o más puntos anotados, o una ronda completada) y ninguno de los dos estaba a 4 rondas. Una DC por jugador y serie. La stat es tus DC divididas entre tus series ranked jugadas más tus DC.
- Rabietas casual: CUALQUIER salida a mitad de partida en un 1v1 casual se apunta, incluso con 4-0. Alimenta la stat de % de abandono (cuánto te abandonan los rivales) - nunca el rating. (Un superviviente que ya tenía 4 rondas se lleva igualmente la victoria casual y su XP.)

<color=#FFD94D><b>DESCONEXIONES - 2V2 Y FFA</b></color>

- 2v2: un equipo se desconecta mientras el otro lidera la serie y la partida abandonada llevaba 2 o más puntos - el equipo líder se lleva la serie entera, con ratings y recompensas completos.
- Cualquier otra DC en 2v2 - la serie se PAUSA para resolución manual de un admin en vez de decidirse sola. Si los mismos cuatro reencolan en unos 30 minutos, el emparejador los devuelve a la misma serie con el marcador guardado.
- El FFA sigue jugándose cuando alguien se va, mientras queden 2 o más (una partida que baja de 3 jugadores antes de que el campo anotara 2 medios puntos se cancela). Los números de quien se fue se congelan, y aun así se le coloca y puntúa en la partida que dejó - <color=#FF6666>irse con 0 puntos no esquiva la derrota</color>.
- Gracia por salida temprana en FFA: quien se fue antes de que el campo anotara 2 medios puntos, con su propio marcador a cero, queda sin puntuar en esa partida - aún no se había decidido nada.
- Un jugador FFA que se fue en una partida ANTERIOR viaja en los reportes posteriores como ausente, excluido de los ratings y recompensas de esas partidas.

<color=#FFD94D><b>SERIES: REANUDAR, ESTANCARSE, CADUCAR</b></color>

- <color=#7FE87F>Un al-mejor-de-3 sin decidir se reanuda sin límite de tiempo.</color> Cruza con el mismo rival mañana o la semana que viene y el juego 1 sigue en pie. Una vez existió una caducidad - los que se iban la esperaban para embolsarse el rating, así que se eliminó.
- El rating se mueve SOLO cuando una serie se completa (primero a 2 juegos ganados). Los juegos de una serie que nunca se completa conservan sus filas de partida, XP y oro; el cambio de rating simplemente nunca ocurre.
- Una serie sin ninguna partida registrada 30 minutos después de crearse se abandona y sus apuestas se reembolsan.
- Un estancamiento de una hora a mitad de serie reembolsa las apuestas, pero la serie sigue activa y reanudable.
- Las series de torneo están exentas de esta poda - el cuadro es dueño de su ciclo de vida. Una partida de torneo decidida por incomparecencia no admite apuestas.

<color=#FFD94D><b>DESCARTADO A POSTERIORI</b></color>

- La única invalidación AUTOMÁTICA de todo el mod: un patrón repetido de partidas inverosímilmente cortas entre los mismos dos jugadores en una ventana corta. La partida actual Y las cortas anteriores se invalidan juntas, su oro y XP se revierten, sus series se anulan.
- Reversión de admin: un admin puede anular una serie - cambios de rating restados, oro recuperado, cada partida invalidada, apuestas sin liquidar reembolsadas. Las partidas invalidadas desaparecen de todas las tablas y stats.
- Cuarentena (2v2 y FFA): un reporte que llega para una sala ya inactiva no se borra - queda retenido para revisión de admin, y un admin aún puede aceptarlo en el registro o descartarlo.

<color=#FFD94D><b>SI EL REPORTE NO PUEDE ENVIARSE</b></color>

- Un reporte fallido va a una bandeja de salida persistente: se reintenta en segundo plano y se guarda en disco, así que se reenvía en tu siguiente arranque aunque cierres justo después de la partida. Verás 'No se pudo registrar la partida - reintentando en segundo plano', y luego 'Partida registrada' cuando llegue.
- Quien reportaba el 1v1 crashea antes de que exista el reporte - la ruta de desconexión del rival superviviente suele registrar el resultado en su lugar.
- El FFA elige a quien reporta entre los jugadores aún presentes, así que un cliente crasheado nunca sale elegido. Un ganador que se va antes del reporte queda registrado igual con sus números congelados.
- Una partida 2v2 que termina sin el id de su serie reintenta la búsqueda y aplaza el envío; si eso también falla, la partida no se registra.$s256$)
  , ('304838dece8548b7', 'ru', 'c56bfd5ef74259ffdcb3e6339e5ae62aabc44604', $s256$Свод правил о том, что записывается, а что выбрасывается: игры, серии, отключения, ставки. Если результат выглядит пропавшим, причина почти всегда на этой странице.

<color=#FFD94D><b>НЕ ЗАПИСЫВАЕТСЯ ВООБЩЕ</b></color>

- Согласие на данные выключено: мод работает полностью оффлайн. Не отправляется ничего, кроме проверки версии.
- Оффлайн, тренировка и песочница: клиент их никогда не отправляет, а сервер для подстраховки отклоняет.
- Зрительские места ничего не отслеживают и ничего не отправляют.

<color=#FFD94D><b>РЕЙТИНГ ИЛИ КАЗУАЛ</b></color>

- Переключатель Ranked выключен у любого из игроков в игре по коду комнаты - она играется как КАЗУАЛ. Всё равно полностью записывается со статистикой и XP; рейтинг не трогает никогда (см. <color=#7FD4FF>Как записываются игры</color>).
- Соперник никогда не запускал мод - всегда казуал, без повышения. (Живая незавершённая серия с прошлой сессии - единственное, что сохраняет рейтинговый статус через паузу.)
- Выключение Ranked ПОСРЕДИ СЕРИИ не аннулирует серию. Идущая серия до 2 побед - твоя запись о согласии; её игры остаются рейтинговыми.
- Игра, отправленная как казуальная, ПОВЫШАЕТСЯ до рейтинговой, когда сервер видит: оба игрока на моде, у обоих включён Ranked, и сессия жива.
- Участник с рейтинговым баном превращает 1v1 в казуал в момент отчёта - даже в комнате очереди, даже посреди серии. (Остальные режимы не пускают забаненных с порога.)
- Комнаты, выданные модом, согласованы по определению: очередь - это согласие. Рейтинговая очередь, 2v2 и турниры рейтингуются; рейтинговые FFA-лобби рейтингуются, казуальные - нет; 1v2 записывается без рейтинга.

<color=#FFD94D><b>ОТКЛЮЧЕНИЯ - 1V1</b></color>

- Ты выходишь из игры, чтобы зайти в свой найденный рейтинговый матч, - покинутая игра отменяется: ничего не записано, выход не отмечен.
- Соперник отключился при 4-4 - ты получаешь победу, записывается 5-4.
- Соперник отключился, пока у тебя 4 раунда, - победа тебе при текущем счёте.
- Любое другое отключение - <color=#FF6666>игра отменяется, результат не записывается</color>, даже если ушедший вёл. Никто не получает дармовую победу и никто не ест нечестное поражение (сам выход всё же может быть отмечен - см. ниже).
- % выходов в рейтинге: DC записывается на ушедшего, когда в ТЕКУЩЕЙ игре была осмысленная игра (2 и больше очков или завершённый раунд) и никто не стоял на 4 раундах. Один DC на игрока на серию. Стат - твои DC, делённые на сыгранные рейтинговые серии плюс DC.
- Казуальные рейдж-квиты: ЛЮБОЙ выход посреди казуальной 1v1 отмечается, даже при 4-0. Он кормит стат Rage Quit % (как часто соперники уходят от тебя) - никогда рейтинг. (Оставшийся, уже стоящий на 4 раундах, всё равно берёт казуальную победу и её XP.)

<color=#FFD94D><b>ОТКЛЮЧЕНИЯ - 2V2 И FFA</b></color>

- 2v2: команда отключается, пока другая ведёт серию, и в брошенной игре было 2 и больше очков - ведущая команда забирает всю серию, с полными рейтингами и наградами.
- Любой другой DC в 2v2 - серия СТАВИТСЯ НА ПАУЗУ до ручного решения админа вместо авторешения. Если те же четверо снова встают в очередь в пределах примерно 30 минут, подбор возвращает их на ту же серию с сохранённым счётом.
- FFA продолжает играться, когда кто-то уходит, пока остаются 2 и больше (игра, упавшая ниже 3 игроков до того, как в ней набрано 2 пол-очка, вместо этого отменяется). Счётчики ушедшего замораживаются, и его всё равно расставляют и рейтингуют за игру, из которой он ушёл, - <color=#FF6666>уход на 0 очков не уворачивается от поражения</color>.
- Льгота раннего ухода в FFA: ушедший до 2 набранных пол-очков, с нулевым собственным счётом, за ту игру не рейтингуется - ничего ещё не было решено.
- FFA-игрок, ушедший в БОЛЕЕ РАННЕЙ игре, едет в поздних отчётах отсутствующим, исключённым из рейтингов и наград тех игр.

<color=#FFD94D><b>СЕРИИ: ВОЗОБНОВЛЕНИЕ, ЗАВИСАНИЕ, ИСТЕЧЕНИЕ</b></color>

- <color=#7FE87F>Нерешённая серия до 2 побед возобновляется без лимита времени.</color> Встреть того же соперника завтра или через неделю - игра 1 всё ещё стоит. Истечение когда-то существовало - ушедшие пересиживали его, чтобы забанкировать рейтинг, и его убрали.
- Рейтинг двигается ТОЛЬКО при завершении серии (первый до 2 выигранных игр). Игры серии, которая так и не завершилась, сохраняют строки матчей, XP и золото; изменение рейтинга просто не происходит.
- Серия без единой записанной игры через 30 минут после создания бросается, её ставки возвращаются.
- Часовое зависание посреди серии возвращает ставки, но сама серия остаётся активной и возобновимой.
- Турнирные серии из этой чистки исключены - их жизненным циклом владеет сетка. На турнирный матч, решённый техпоражением, ставить нельзя.

<color=#FFD94D><b>ВЫБРОШЕНО ЗАДНИМ ЧИСЛОМ</b></color>

- Единственная АВТОМАТИЧЕСКАЯ инвалидация во всём моде: повторяющийся паттерн неправдоподобно коротких матчей между одними и теми же двумя игроками в коротком окне. Инвалидируются вместе текущий матч И ранние короткие, их золото и XP отматываются, их серии аннулируются.
- Отмена админом: админ может аннулировать серию - изменения рейтинга вычитаются, золото возвращается, каждый её матч инвалидируется, неразрешённые ставки возвращаются. Инвалидированные матчи исчезают из всех таблиц и статов.
- Карантин (2v2 и FFA): отчёт, пришедший для уже неактивного лобби, не удаляется - он придерживается до проверки админом, и админ может принять его в запись или отбросить.

<color=#FFD94D><b>ЕСЛИ ОТЧЁТ НЕ ОТПРАВЛЯЕТСЯ</b></color>

- Неудачный отчёт уходит в постоянный ящик исходящих: он повторяется в фоне и сохраняется на диск, так что переотправится при следующем запуске, даже если ты вышел сразу после игры. Ты увидишь «Не удалось записать матч - повторяем в фоне», а затем «Матч записан», когда он дойдёт.
- Репортёр 1v1 упал до появления отчёта - результат обычно записывает путь отключения выжившего соперника.
- FFA выбирает репортёра среди ещё присутствующих игроков, так что упавший репортёр не избирается никогда. Победитель, вышедший до отчёта, всё равно записывается по своим замороженным счётчикам.
- Игра 2v2, закончившаяся без id своей серии, повторяет поиск и откладывает отправку; если не удалось и это, игра не записывается.$s256$)
  , ('304838dece8548b7', 'sv', 'c56bfd5ef74259ffdcb3e6339e5ae62aabc44604', $s256$Regelboken för vad som registreras och vad som kastas: matcher, serier, disconnects, vad. Ser ett resultat ut att saknas finns orsaken nästan alltid på den här sidan.

<color=#FFD94D><b>REGISTRERAS ALDRIG ALLS</b></color>

- Datasamtycke av: modden kör helt offline. Ingenting skickas någonsin utom en versionskontroll.
- Offline-, övnings- och sandboxmatcher: rapporteras aldrig av klienten, och vägras av servern som en extra spärr.
- Åskådarplatser spårar ingenting och rapporterar ingenting.

<color=#FFD94D><b>RANKED ELLER CASUAL</b></color>

- Någon spelares Ranked-inställning av i en rumskodsmatch - den spelas som CASUAL. Fortfarande fullt registrerad med statistik och XP; den rör aldrig rating (se <color=#7FD4FF>Så registreras matcher</color>).
- Motståndaren har aldrig kört modden - alltid casual, uppgraderas aldrig. (En levande oavslutad serie från en tidigare sittning är det enda som bevarar ranked-status över ett uppehåll.)
- Att stänga av Ranked MITT I EN SERIE ogiltigförklarar inte serien. Den pågående bäst av 3:an är ditt samtyckesbevis; dess matcher förblir rankade.
- En match rapporterad som casual UPPGRADERAS till ranked när servern kan se att båda spelarna är moddade, båda har Ranked på och sittningen är levande.
- En ranked-avstängd deltagare tvingar en 1v1 till casual vid rapporttillfället - även i ett kö-rum, även mitt i en serie. (De andra lägena stänger ute avstängda spelare redan vid dörren.)
- Rum som modden utfärdar är samtyckta per definition; att köa är samtycke. Ranked-kön, 2v2 och turneringar rankas; rankade FFA-lobbyer rankas medan casual-lobbyer inte gör det; 1v2 registrerar utan att ranka.

<color=#FFD94D><b>DISCONNECTS - 1V1</b></color>

- Du lämnar en match för att ansluta till en köad ranked-match - matchen du lämnade avbryts: inget registreras, inget avhopp loggas.
- Motståndaren DC:ar vid 4-4 - du får vinsten, registrerad 5-4.
- Motståndaren DC:ar medan du håller 4 ronder - du får vinsten på den stående ställningen.
- Varje annan DC - <color=#FF6666>matchen avbryts och inget resultat registreras</color>, även när avhopparen låg i ledning. Ingen får en gratisvinst och ingen äter en orättvis förlust (själva avhoppet kan ändå loggas - se nedan).
- Ranked avhopps-%: en DC loggas mot avhopparen när den PÅGÅENDE matchen hade meningsfullt spel (2 eller fler poäng, eller en avslutad rond) och ingen sida stod på 4 ronder. En DC per spelare och serie. Statistiken är dina DC:ar delat med dina spelade ranked-serier plus dina DC:ar.
- Casual-ragequits: VARJE avhopp mitt i en casual-1v1 loggas, även vid 4-0. Det matar statistiken Ragequit-% (hur ofta motståndare går ifrån dig) - aldrig rating. (En överlevare som redan står på 4 ronder tar ändå casual-vinsten och dess XP.)

<color=#FFD94D><b>DISCONNECTS - 2V2 OCH FFA</b></color>

- 2v2: ett lag DC:ar medan det andra laget leder serien och den övergivna matchen hade 2 eller fler poäng - det ledande laget tar hela serien, med full rating och fulla belöningar.
- Varje annan 2v2-DC - serien PAUSAS för manuell adminhantering i stället för att avgöras automatiskt. Köar samma fyra om inom cirka 30 minuter sätter matchningen dem tillbaka på samma serie med ställningen kvar.
- FFA fortsätter spela när någon lämnar, så länge 2 eller fler är kvar (en match som faller under 3 spelare innan fältet gjort 2 halvpoäng avbryts i stället). Avhopparens siffror fryses, och de placeras och rankas ändå för matchen de lämnade under - <color=#FF6666>att lämna på 0 poäng duckar inte förlusten</color>.
- FFA-frist vid tidigt avhopp: en avhoppare som lämnade innan fältet gjort 2 halvpoäng, med en egen räkning på noll, rankas inte för den matchen - inget var avgjort ännu.
- En FFA-spelare som lämnade i en TIDIGARE match följer med i senare rapporter som frånvarande, utesluten ur de matchernas rating och belöningar.

<color=#FFD94D><b>SERIER: ÅTERUPPTA, STANNA, LÖPA UT</b></color>

- <color=#7FE87F>En oavgjord bäst av 3 återupptas utan tidsgräns.</color> Möt samma motståndare imorgon eller nästa vecka och match 1 står kvar. Ett utgångsdatum fanns en gång - avhoppare väntade ut det för att rädda sin rating, så det togs bort.
- Rating flyttas BARA när en serie avslutas (först till 2 matchvinster). Matcher i en serie som aldrig avslutas behåller sina matchrader, XP och guld; ratingändringen sker bara aldrig.
- En serie utan registrerad match 30 minuter efter att den skapats överges och dess vad återbetalas.
- Ett seriestopp på en timme mitt i återbetalar vaden, men serien förblir aktiv och återupptagbar.
- Turneringsserier är undantagna från den här gallringen - bracketen äger deras livscykel. En turneringsmatch avgjord på walkover går inte att satsa på.

<color=#FFD94D><b>UTSLÄNGT I EFTERHAND</b></color>

- Den enda AUTOMATISKA ogiltigförklaringen i hela modden: ett upprepat mönster av orimligt korta matcher mellan samma två spelare inom ett kort fönster. Den aktuella matchen OCH de tidigare korta ogiltigförklaras tillsammans, deras guld och XP återförs, deras serier annulleras.
- Adminåterkallelse: en admin kan annullera en serie - ratingändringar dras tillbaka, guld återkrävs, varje match i den ogiltigförklaras, oavgjorda vad återbetalas. Ogiltigförklarade matcher försvinner från varje tavla och statistik.
- Karantän (2v2 och FFA): en rapport som anländer för en lobby som inte längre är aktiv raderas inte - den hålls för admingranskning, och en admin kan ändå ta in den i registret eller kasta den.

<color=#FFD94D><b>OM RAPPORTEN INTE KAN SKICKAS</b></color>

- En misslyckad rapport går till en beständig utkorg: den försöks om i bakgrunden och sparas till disk, så den skickas om vid nästa start även om du stänger direkt efter matchen. Du ser 'Kunde inte registrera matchen - försöker igen i bakgrunden', sedan 'Match registrerad' när den landar.
- 1v1-rapportören kraschar innan rapporten finns - den överlevande motståndarens disconnect-väg registrerar oftast resultatet i stället.
- FFA väljer sin rapportör bland spelarna som fortfarande är kvar, så en kraschad rapportör väljs aldrig. En vinnare som stänger före rapporten registreras ändå från sina frysta siffror.
- En 2v2-match som slutar utan sitt serie-id försöker slå upp det igen och skjuter upp sändningen; misslyckas även det registreras inte matchen.$s256$)
  , ('304838dece8548b7', 'uk', 'c56bfd5ef74259ffdcb3e6339e5ae62aabc44604', $s256$Книга правил про те, що записується, а що викидається: ігри, серії, дисконекти, ставки. Якщо результату наче бракує, причина майже завжди на цій сторінці.

<color=#FFD94D><b>НЕ ЗАПИСУЄТЬСЯ ВЗАГАЛІ</b></color>

- Згоду на дані вимкнено: мод працює повністю офлайн. Не надсилається нічого, крім перевірки версії.
- Офлайн, тренування та пісочниця: клієнт їх ніколи не звітує, а сервер про всяк випадок відмовляє.
- Місця глядачів нічого не відстежують і нічого не звітують.

<color=#FFD94D><b>РЕЙТИНГОВА ЧИ ЗВИЧАЙНА</b></color>

- Перемикач Ranked будь-кого з гравців вимкнено у грі за кодом кімнати - вона грається як ЗВИЧАЙНА. Усе одно повністю записується зі статистикою та XP; рейтингу не торкається ніколи (див. <color=#7FD4FF>Як записуються ігри</color>).
- Суперник ніколи не запускав мод - завжди звичайна, ніколи не підвищується. (Жива незавершена серія з ранішої сесії - єдине, що зберігає рейтинговий статус через перерву.)
- Вимкнення Ranked ПОСЕРЕД СЕРІЇ серію не скасовує. Запущений best-of-3 - ваш запис згоди; його ігри лишаються рейтинговими.
- Гра, заявлена як звичайна, ПІДВИЩУЄТЬСЯ до рейтингової, коли сервер бачить: обидва гравці з модом, в обох Ranked увімкнено, сесія жива.
- Учасник із рейтинговим баном перетворює 1v1 на звичайну в момент звіту - навіть у кімнаті черги, навіть посеред серії. (Інші режими натомість не пускають забанених від самих дверей.)
- Модові кімнати - згода за визначенням; черга і є згодою. Рейтингова черга, 2v2 і турніри рейтингуються; рейтингові лобі FFA рейтингуються, звичайні ні; 1v2 записується без рейтингу.

<color=#FFD94D><b>ДИСКОНЕКТИ - 1V1</b></color>

- Ви виходите з гри, щоб приєднатися до рейтингового матчу з черги, - покинута гра скасовується: нічого не записано, вихід не залоговано.
- Суперник дисконектить на 4-4 - перемога ваша, записується 5-4.
- Суперник дисконектить, коли ви тримаєте 4 раунди, - перемога ваша за поточним рахунком.
- Будь-який інший DC - <color=#FF6666>гра скасовується і результат не записується</color>, навіть коли той, хто вийшов, вів. Ніхто не отримує безкоштовну перемогу і ніхто не їсть несправедливу поразку (сам вихід усе одно може бути залогований - див. нижче).
- Рейтинговий % виходів: DC логується проти того, хто вийшов, коли в ПОТОЧНІЙ грі була змістовна гра (2 і більше очок або завершений раунд) і жодна сторона не мала 4 раундів. Один DC на гравця на серію. Статистика - ваші DC, поділені на зіграні рейтингові серії плюс ваші DC.
- Рейдж-квіти у звичайних: БУДЬ-ЯКИЙ вихід посеред звичайної 1v1 логується, навіть на 4-0. Він живить статистику % рейдж-квітів (як часто суперники йдуть від вас) - ніколи рейтинг. (Той, хто лишився і вже мав 4 раунди, все одно бере звичайну перемогу та її XP.)

<color=#FFD94D><b>ДИСКОНЕКТИ - 2V2 І FFA</b></color>

- 2v2: команда дисконектить, поки інша веде серію, а покинута гра мала 2 і більше очок, - команда-лідер бере всю серію, з повними рейтингами й нагородами.
- Будь-який інший DC у 2v2 - серія СТАЄ НА ПАУЗУ для ручного розбору адміном замість автовирішення. Якщо ті самі четверо повторно стануть у чергу впродовж ~30 хвилин, підбір поверне їх на ту саму серію зі збереженим рахунком.
- FFA продовжує гратися, коли хтось іде, поки лишається 2 і більше (гра, що падає нижче 3 гравців до того, як поле набрало 2 половинки очок, натомість скасовується). Показники того, хто вийшов, заморожуються, і його все одно розставляють і рейтингують за гру, яку він покинув, - <color=#FF6666>вихід на 0 очок від поразки не рятує</color>.
- Пільга раннього виходу FFA: той, хто вийшов до 2 набраних полем половинок очок із власним нульовим підсумком, за ту гру не рейтингується - ще нічого не було вирішено.
- Гравець FFA, що вийшов у РАНІШІЙ грі, їде в пізніших звітах як відсутній, виключений із рейтингів і нагород тих ігор.

<color=#FFD94D><b>СЕРІЇ: ВІДНОВЛЕННЯ, СТОП, ЗАКІНЧЕННЯ</b></color>

- <color=#7FE87F>Невирішений best-of-3 відновлюється без обмеження часу.</color> Зустріньте того самого суперника завтра чи наступного тижня - гра 1 досі в силі. Колись існував строк давності - ті, хто виходив, пересиджували його, щоб забанкувати рейтинг, тож його прибрали.
- Рейтинг рухається ЛИШЕ коли серія завершується (перший до 2 виграних ігор). Ігри серії, що так і не завершиться, зберігають свої рядки матчів, XP і золото; просто зміна рейтингу не настає.
- Серія без жодної записаної гри через 30 хвилин після створення закидається, а її ставки повертаються.
- Годинний стоп посеред серії повертає ставки, але сама серія лишається активною і відновлюваною.
- Турнірні серії звільнені від цього прибирання - їхнім життєвим циклом володіє сітка. На турнірний матч, вирішений технічною поразкою, ставити не можна.

<color=#FFD94D><b>ВИКИНУТЕ ЗАДНІМ ЧИСЛОМ</b></color>

- Єдина АВТОМАТИЧНА інвалідація в усьому моді: повторюваний патерн неправдоподібно коротких матчів між тими самими двома гравцями в короткому вікні. Поточний матч І раніші короткі інвалідуються разом, їхні золото та XP відкочуються, їхні серії анулюються.
- Реверс адміном: адмін може анулювати серію - зміни рейтингу віднімаються, золото вилучається, кожен матч у ній інвалідовано, неврегульовані ставки повернено. Інвалідовані матчі зникають з усіх таблиць і статистик.
- Карантин (2v2 і FFA): звіт, що приходить на вже неактивне лобі, не видаляється - він притримується для розбору адміном, і адмін може або прийняти його в запис, або відкинути.

<color=#FFD94D><b>ЯКЩО ЗВІТ НЕ НАДСИЛАЄТЬСЯ</b></color>

- Невдалий звіт іде в постійний вихідний лоток: повторюється у фоні та зберігається на диск, тож перенадсилається при наступному запуску, навіть якщо ви вийшли одразу після гри. Ви побачите «Не вдалося записати матч - повторюємо у фоні», а потім «Матч записано», коли він сяде.
- Звітувальник 1v1 падає до появи звіту - шлях дисконекту вцілілого суперника зазвичай записує результат замість нього.
- FFA обирає звітувальника серед гравців, ще присутніх, тож звітувальник, що впав, не обирається ніколи. Переможець, що вийшов до звіту, все одно записується з його заморожених показників.
- Гра 2v2, що завершується без id своєї серії, повторює пошук і відкладає надсилання; якщо не вдається і це, гра не записується.$s256$)
  , ('325b2f12f56594dd', 'es', 'f9da8a515f187b04c3b8e3e1499e4fd62bec8b7a', $s256$Cada partida que juegas con el mod pasa por el mismo circuito: cada cliente con mod observa la partida, uno de ellos presenta el reporte y el servidor decide qué cuenta. Esta página cubre cómo se clasifica y reporta una partida. Para qué mide cada stat, ver <color=#7FD4FF>Cómo se registran las stats</color>.

<color=#FFD94D><b>QUÉ HACE COMPETITIVA UNA PARTIDA</b></color>

- Las salas que el mod crea llevan el consentimiento incluido - encolarse ES tu consentimiento. La cola ranked, el 2v2 y los torneos juegan puntuando; las salas FFA ranked puntúan sus partidas y las casual no; el 1v2 registra sin puntuar.
- Una partida privada por código es ranked solo cuando tres cosas se cumplen a la vez: <color=#7FE87F>tu Ranked está activado, tu rival lleva el mod, y su ajuste de Ranked también está activado</color>. El mod reconoce a un rival con mod por los datos de presencia que su cliente publica en la sala; un jugador vanilla no tiene ninguno.
- Tu cliente pregunta al servidor si el rival tiene Ranked activado, y sigue recomprobándolo un rato después de que entre - un jugador que arrancó su juego hace segundos puede parecer brevemente no-ranked.
- En cuanto se confirma un emparejamiento ranked, el cliente registra la serie en el servidor, así el HUD de marcador y el panel de apuestas funcionan desde el juego 1.
- Si cualquiera de los dos tiene Ranked apagado, el servidor responde 'no ranked', tu cliente pasa la partida a casual y recibes un aviso por sala diciéndolo.
- El servidor lo recomprueba todo otra vez cuando llega el reporte. Un cambio del ajuste a mitad de serie no puede anular un al-mejor-de-3 ya en marcha, y una partida reportada como casual se asciende a ranked cuando el servidor ve que ambos llevan el mod, ambos consintieron y la sentada está viva. Un rival que nunca ha usado el mod no puede ascenderse jamás - el quickplay genuino se queda casual para siempre. (Una serie viva sin terminar de una sentada anterior es lo único que mantiene el estado ranked a través de un hueco.)

<color=#FFD94D><b>QUIÉN ENVÍA EL REPORTE</b></color>

- Un cliente reporta cada partida: el jugador con el Steam ID numéricamente MENOR. Ambos clientes aplican la misma regla, así que casi nunca compiten - y si un raro borde temprano de sala hace que ambos envíen, el servidor conserva exactamente uno. Contra un rival vanilla siempre reporta el jugador con mod - nadie más puede.
- El 2v2 elige el Steam ID menor de los cuatro, el 1v2 el menor de los tres, y el FFA el menor entre los jugadores aún PRESENTES al terminar (quien se fue no puede reportar).
- En 1v1, si el reportador elegido crashea o se va, el superviviente toma el relevo y las reglas de desconexión deciden el resultado; el FFA simplemente elige entre quienes siguen presentes (ver <color=#7FD4FF>Cuándo cuenta una partida</color>).
- El servidor también impone un-reporte-por-partida en su lado: nada se registra ni se paga dos veces, y un envío duplicado o recibe el resultado ya registrado o se aparta.

<color=#FFD94D><b>QUÉ LLEVA UN REPORTE</b></color>

- El resultado: rondas y puntos de ambos lados, duración de la partida, región y un id de sala por juego.
- Cartas: cada elección con su ronda y orden de elección, más - para el jugador que reporta - qué le ofrecieron y qué dejó pasar. Tus ofertas solo salen de tu propio cliente, nunca del de tu rival.
- Stats de combate: balas disparadas y acertadas, intentos y éxitos de bloqueo, daño infligido y (en 1v1) muertes con su causa.
- Líneas de tiempo para las gráficas: FPS, ping, progreso de acierto/bloqueo y daño, muestreados cada pocos segundos durante toda la partida. (El 1v2 lleva un juego más ligero por ahora.)
- Salud de la conexión (más completa en 1v1): congelaciones de fotogramas, huecos de silencio de red y si las actualizaciones en vivo del rival se estancaron.
- Una instantánea de la build final de cada jugador, tomada al terminar antes de que nada pueda borrarla.
- Ritmo de input: cuántas teclas y clics de juego pulsaste estando vivo en combate. El conteo cubre solo las teclas de movimiento, disparo y bloqueo, corre solo durante combate activo y se detiene mientras escribes en un chat o tienes el menú abierto.
- <color=#7FE87F>El resultado central va FIRMADO por el cliente que reporta</color>, así no puede alterarse en tránsito y un programa cualquiera no puede falsificar uno. La telemetría de stats viaja fuera de la firma y se trata como orientativa - datos útiles, nunca prueba.

<color=#FFD94D><b>QUÉ HACE EL OTRO CLIENTE</b></color>

- El que no reporta ejecuta igualmente todo el circuito de fin de partida - logros, recuentos de sesión, su propia captura de stats. Solo que no envía la partida.
- Durante la partida, ambos clientes se publican sus stats en vivo a través de la sala cada pocos segundos. Así es como el reporte lleva TUS números de disparos/aciertos/bloqueos cuando quien lo presenta es tu rival.
- Solo el cliente que reporta ve la respuesta del servidor, y por eso el aviso de XP y el marcador de la serie aterrizan primero en una pantalla.

<color=#FFD94D><b>LAS PARTIDAS CASUAL TAMBIÉN SE REGISTRAN</b></color>

- Un 1v1 casual escribe la misma fila de partida completa que uno ranked: marcador, cartas, duración, toda la telemetría.
- Ambos jugadores ganan XP - base 250, x1.5 por victoria, +100 por una barrida 5-0 - y la XP se convierte en oro al habitual 100 XP = 1 Oro. Los logros de racha casual también cuentan.
- Lo que el casual nunca toca: ni serie, ni cambio de rating, ni apuestas, ni % de salida ranked.
- Un rival vanilla recibe una página de stats autocreada a partir del reporte. <color=#7FE87F>Conserva el gameplay vanilla puro, y la única parte del mod que puede llegar a ver es el estilo del nombre</color> (ver <color=#7FD4FF>Qué ven los jugadores sin mod</color>).$s256$)
  , ('325b2f12f56594dd', 'ru', 'f9da8a515f187b04c3b8e3e1499e4fd62bec8b7a', $s256$Каждая твоя игра с модом проходит один и тот же конвейер: каждый модовый клиент наблюдает матч, один из них отправляет отчёт, а сервер решает, что тот значит. Эта страница - о том, как игра классифицируется и отправляется. Что именно измеряет каждый стат - см. <color=#7FD4FF>Как считается статистика</color>.

<color=#FFD94D><b>ЧТО ДЕЛАЕТ ИГРУ СОРЕВНОВАТЕЛЬНОЙ</b></color>

- Комнаты, которые мод создаёт сам, согласованы по определению - встать в очередь И ЕСТЬ твоё согласие. Рейтинговая очередь, 2v2 и турниры играются с рейтингом; рейтинговые FFA-лобби рейтингуют свои игры, казуальные - нет; 1v2 записывается без рейтинга.
- Приватная игра по коду комнаты рейтинговая, только когда верны три вещи разом: <color=#7FE87F>твой переключатель Ranked включён, соперник запускает мод, и его настройка Ranked тоже включена</color>. Мод узнаёт модового соперника по данным присутствия, которые его клиент публикует в комнату; у ванильного игрока их нет.
- Твой клиент спрашивает сервер, включён ли у соперника Ranked, и какое-то время перепроверяет после его входа - игрок, запустивший игру секунды назад, может ненадолго выглядеть нерейтинговым.
- Как только рейтинговая пара подтверждена, клиент регистрирует серию на сервере, так что HUD счёта и панель ставок работают с игры 1.
- Если Ranked выключен у любой стороны, сервер отвечает «не рейтинговая», твой клиент переводит игру в казуал, и ты получаешь одно уведомление на комнату об этом.
- Сервер перепроверяет всё ещё раз, когда приходит отчёт. Переключатель посреди серии не может аннулировать уже идущую серию до 2 побед, а игра, отправленная казуальной, повышается до рейтинговой, когда сервер видит: оба на моде, оба согласны, сессия жива. Соперник, никогда не запускавший мод, повышен быть не может - настоящий quickplay остаётся казуалом навсегда. (Живая незавершённая серия с прошлой сессии - единственное, что сохраняет рейтинговый статус через паузу.)

<color=#FFD94D><b>КТО ОТПРАВЛЯЕТ ОТЧЁТ</b></color>

- Каждую игру отправляет один клиент: игрок с численно МЕНЬШИМ Steam ID. Оба клиента применяют одно правило, так что гонки почти не бывает - а если редкая ранняя гонка комнаты заставит отправить обоих, сервер оставит ровно один. Против ванильного соперника отправляет всегда модовый игрок - больше некому.
- 2v2 выбирает меньший Steam ID из четырёх, 1v2 - из трёх, а FFA - меньший среди игроков, ещё ПРИСУТСТВУЮЩИХ на конце игры (ушедший отправить не может).
- В 1v1, если избранный репортёр упал или ушёл, его подменяет выживший, и результат решают правила отключений; FFA просто выбирает среди тех, кто ещё на месте (см. <color=#7FD4FF>Когда игра засчитывается</color>).
- Сервер и со своей стороны требует «один отчёт на игру»: ничто никогда не записывается и не оплачивается дважды, а дублю отвечают уже записанным результатом или откладывают его.

<color=#FFD94D><b>ЧТО ВНУТРИ ОТЧЁТА</b></color>

- Результат: раунды и очки обеих сторон, длительность матча, регион и id комнаты на игру.
- Карты: каждый пик со своим раундом и порядком выбора, плюс - для отправляющего игрока - что ему предлагали и от чего он отказался. Твои предложенные карты приходят только с твоего клиента, никогда с клиента соперника.
- Боевые статы: выпущенные и попавшие пули, попытки и успехи блока, нанесённый урон и (в 1v1) смерти с их причинами.
- Таймлайны для графиков: FPS, пинг, прогресс попаданий/блоков и урон, снимаемые каждые несколько секунд всю игру. (1v2 пока несёт облегчённый набор.)
- Здоровье соединения (полнее всего в 1v1): фризы кадров, паузы сетевой тишины и стопорились ли живые обновления соперника.
- Снимок финального билда каждого игрока, снятый на конце игры, пока его ничто не стёрло.
- Темп ввода: сколько игровых клавиш и кликов ты нажал, пока был жив в бою. Подсчёт покрывает только клавиши движения, огня и блока, идёт только в живом бою и останавливается, пока ты печатаешь в любом чате или держишь меню открытым.
- <color=#7FE87F>Ядро результата ПОДПИСАНО отправляющим клиентом</color>, так что его нельзя подменить в пути, а посторонняя программа не может его подделать. Статистическая телеметрия едет вне подписи и считается справочной - полезные данные, но никогда не доказательство.

<color=#FFD94D><b>ЧТО ДЕЛАЕТ ВТОРОЙ КЛИЕНТ</b></color>

- Неотправляющий тоже прогоняет весь конвейер конца игры - достижения, счётчики сессии, свой съём статистики. Он просто не отправляет матч.
- Во время матча оба клиента каждые несколько секунд публикуют друг другу свои живые статы через комнату. Так отчёт несёт ТВОИ числа выстрелов/попаданий/блоков, когда его отправляет соперник.
- Ответ сервера видит только клиент репортёра - поэтому уведомление XP и счёт серии сначала появляются на одном экране.

<color=#FFD94D><b>КАЗУАЛЬНЫЕ ИГРЫ ТОЖЕ ЗАПИСЫВАЮТСЯ</b></color>

- Казуальная 1v1 пишет ту же полную строку матча, что и рейтинговая: счёт, карты, длительность, вся телеметрия.
- Оба игрока получают XP - база 250, x1.5 за победу, +100 за сухую 5-0 - и XP конвертируется в золото по обычным 100 XP = 1 золото. Казуальные достижения за победы подряд тоже считаются.
- Чего казуал не трогает никогда: ни серий, ни изменений рейтинга, ни ставок, ни рейтингового % выходов.
- Ванильный соперник получает страницу статистики, автосозданную из отчёта. <color=#7FE87F>Он сохраняет чистый ванильный геймплей, и единственная часть мода, которую он вообще может увидеть, - стиль неймтега</color> (см. <color=#7FD4FF>Что видят игроки без мода</color>).$s256$)
  , ('325b2f12f56594dd', 'sv', 'f9da8a515f187b04c3b8e3e1499e4fd62bec8b7a', $s256$Varje match du spelar med modden kör samma pipeline: varje moddad klient bevakar matchen, en av dem skickar rapporten, och servern avgör vad den räknas som. Den här sidan täcker hur en match klassificeras och rapporteras. För vad varje statistikvärde faktiskt mäter, se <color=#7FD4FF>Så räknas statistiken</color>.

<color=#FFD94D><b>VAD SOM GÖR EN MATCH TÄVLINGSMÄSSIG</b></color>

- Rum som modden själv skapar är samtyckta per definition - att köa ÄR ditt samtycke. Ranked-kön, 2v2 och turneringar spelas rankat; rankade FFA-lobbyer rankar sina matcher medan casual-lobbyer inte gör det; 1v2 registrerar utan att ranka.
- En privat rumskodsmatch är rankad bara när tre saker alla är sanna: <color=#7FE87F>din Ranked-inställning är på, din motståndare kör modden, och deras Ranked-inställning är också på</color>. Modden känner igen en moddad motståndare på närvarodatan som deras klient publicerar i rummet; en vanilla-spelare har ingen.
- Din klient frågar servern om motståndaren har Ranked aktiverat, och fortsätter fråga en stund efter att de anslutit - en spelare som startade sitt spel för några sekunder sedan kan en kort stund se orankad ut.
- Så snart en rankad parning bekräftats registrerar klienten serien hos servern, så ställnings-HUD:en och vadpanelen fungerar från match 1.
- Har någon av er Ranked av svarar servern 'inte rankad', din klient växlar matchen till casual, och du får en avisering per rum som säger det.
- Servern kontrollerar allt igen när rapporten landar. En inställningsändring mitt i serien kan inte ogiltigförklara en bäst av 3 som redan pågår, och en match rapporterad som casual uppgraderas till ranked när servern kan se att båda spelarna är moddade, båda samtyckt och sittningen är levande. En motståndare som aldrig kört modden kan aldrig uppgraderas - äkta quickplay förblir casual för alltid. (En levande oavslutad serie från en tidigare sittning är det enda som bevarar ranked-status över ett uppehåll.)

<color=#FFD94D><b>VEM SOM SKICKAR RAPPORTEN</b></color>

- En klient rapporterar varje match: spelaren med det numeriskt LÄGRE Steam-ID:t. Båda klienterna tillämpar samma regel, så de kapplöper nästan aldrig - och om en sällsynt tidig rumskant får båda att skicka behåller servern exakt en. Mot en vanilla-motståndare rapporterar den moddade spelaren alltid - ingen annan kan.
- 2v2 väljer det lägsta Steam-ID:t av de fyra, 1v2 det lägsta av tre, och FFA det lägsta bland spelare som fortfarande är NÄRVARANDE vid matchslutet (en avhoppare kan inte rapportera).
- Om den valda rapportören i 1v1 kraschar eller lämnar tar överlevaren över och disconnect-reglerna avgör resultatet; FFA väljer helt enkelt bland dem som är kvar (se <color=#7FD4FF>När en match räknas</color>).
- Servern upprätthåller en-rapport-per-match på sin sida också: inget registreras eller betalas två gånger, och en dubblettsändning besvaras antingen med det redan registrerade resultatet eller läggs åt sidan.

<color=#FFD94D><b>VAD SOM FINNS I EN RAPPORT</b></color>

- Resultatet: båda sidors ronder och poäng, matchlängd, region och ett rums-id per match.
- Kort: varje val med sin rond och valordning, plus - för den rapporterande spelaren - vad de erbjöds och tackade nej till. Dina erbjudanden kommer alltid bara från din egen klient, aldrig från motståndarens.
- Stridsstatistik: kulor avfyrade och träffade, blockförsök och lyckade block, utdelad skada, och (i 1v1) dödsfall med hur de skedde.
- Tidslinjer för graferna: FPS, ping, träff-/blockutveckling och skada, samplade med några sekunders mellanrum genom hela matchen. (1v2 bär en lättare uppsättning tills vidare.)
- Anslutningshälsa (fylligast i 1v1): bildfrysningar, tysta nätverksgap, och om motståndarens live-uppdateringar stannade.
- En ögonblicksbild av varje spelares slutliga build, tagen vid matchslutet innan något kan sudda den.
- Inputtakt: hur många spelknappar och klick du tryckte medan du var vid liv i strid. Räkningen täcker bara rörelse-, skjut- och blockknapparna, körs bara under aktiv strid, och stannar medan du skriver i en chatt eller har menyn öppen.
- <color=#7FE87F>Kärnresultatet är SIGNERAT av den rapporterande klienten</color>, så det kan inte ändras på vägen och ett godtyckligt program kan inte förfalska ett. Statistiktelemetrin åker utanför signaturen och behandlas som rådgivande - användbar data, aldrig bevis.

<color=#FFD94D><b>VAD DEN ANDRA KLIENTEN GÖR</b></color>

- Icke-rapportören kör också hela matchslutspipelinen - prestationer, sittningsräkningar, sin egen statistikfångst. Den skickar bara inte matchen.
- Under matchen publicerar båda klienterna sin livestatistik till varandra genom rummet med några sekunders mellanrum. Det är så rapporten bär DINA avfyrat/träffat/block-siffror när det är motståndaren som skickar den.
- Bara rapportörens klient ser serverns svar, vilket är varför XP-aviseringen och serieställningen landar på den ena skärmen först.

<color=#FFD94D><b>CASUAL-MATCHER REGISTRERAS OCKSÅ</b></color>

- En casual-1v1 skriver samma fulla matchrad som en rankad: ställning, kort, längd, all telemetri.
- Båda spelarna tjänar XP - bas 250, x1.5 för en vinst, +100 för en 5-0-utklassning - och XP omvandlas till guld enligt de vanliga 100 XP = 1 guld. Casual-vinstsvitprestationer räknas också.
- Vad casual aldrig rör: ingen serie, ingen ratingändring, inga vad, ingen ranked avhopps-%.
- En vanilla-motståndare får en statistiksida autoskapad från rapporten. <color=#7FE87F>De behåller ren vanilla-gameplay, och den enda del av modden de någonsin kan se är namnskyltsstil</color> (se <color=#7FD4FF>Vad omoddade spelare ser</color>).$s256$)
  , ('325b2f12f56594dd', 'uk', 'f9da8a515f187b04c3b8e3e1499e4fd62bec8b7a', $s256$Кожна гра з модом проходить один конвеєр: кожен клієнт з модом спостерігає матч, один із них подає звіт, а сервер вирішує, чим він рахується. Ця сторінка - про те, як гра класифікується і звітується. Що саме міряє кожна метрика - див. <color=#7FD4FF>Як рахується статистика</color>.

<color=#FFD94D><b>ЩО РОБИТЬ ГРУ ЗМАГАЛЬНОЮ</b></color>

- Кімнати, які мод створює сам, - згода за визначенням: стати в чергу І Є ваша згода. Рейтингова черга, 2v2 і турніри граються рейтингово; рейтингові лобі FFA рейтингують свої ігри, звичайні ні; 1v2 записується без рейтингу.
- Приватна гра за кодом кімнати рейтингова лише тоді, коли істинні всі три речі: <color=#7FE87F>ваш перемикач Ranked увімкнено, суперник має мод, і його налаштування Ranked теж увімкнено</color>. Мод розпізнає суперника з модом за даними присутності, які його клієнт публікує в кімнату; у ванільного гравця їх немає.
- Ваш клієнт питає сервер, чи має суперник увімкнений Ranked, і ще певний час після їхнього приходу перепитує - гравець, що запустив гру секунди тому, може ненадовго виглядати нерейтинговим.
- Щойно рейтингова пара підтверджена, клієнт реєструє серію на сервері, тож HUD рахунку і панель ставок працюють із гри 1.
- Якщо в когось Ranked вимкнено, сервер відповідає «не рейтингова», ваш клієнт перемикає гру у звичайну, і ви отримуєте одне сповіщення на кімнату про це.
- Сервер переперевіряє все ще раз, коли сідає звіт. Перемикання посеред серії не може анулювати вже запущений best-of-3, а гра, заявлена звичайною, підвищується до рейтингової, коли сервер бачить: обидва з модом, обидва зі згодою, сесія жива. Суперника, що ніколи не запускав мод, підвищити не можна - справжній швидкий матч назавжди лишається звичайним. (Жива незавершена серія з ранішої сесії - єдине, що тримає рейтинговий статус через перерву.)

<color=#FFD94D><b>ХТО НАДСИЛАЄ ЗВІТ</b></color>

- Кожну гру звітує один клієнт: гравець із чисельно МЕНШИМ Steam ID. Обидва клієнти застосовують те саме правило, тож вони майже ніколи не змагаються - а якщо рідкісний ранньокімнатний випадок змусить надіслати обох, сервер лишає рівно один. Проти ванільного суперника завжди звітує гравець з модом - більше нікому.
- 2v2 обирає найменший Steam ID із чотирьох, 1v2 - найменший із трьох, а FFA - найменший серед гравців, ще ПРИСУТНІХ на кінець гри (той, хто вийшов, звітувати не може).
- В 1v1, якщо обраний звітувальник падає чи виходить, перехоплює вцілілий, і результат вирішують правила дисконекту; FFA просто обирає серед тих, хто ще присутній (див. <color=#7FD4FF>Коли гра зараховується</color>).
- Сервер зі свого боку теж пильнує «один звіт на гру»: ніщо не записується і не платиться двічі, а дубльоване надсилання або отримує вже записаний результат, або відкладається набік.

<color=#FFD94D><b>ЩО ВСЕРЕДИНІ ЗВІТУ</b></color>

- Результат: раунди й очки обох сторін, тривалість матчу, регіон і id кімнати на кожну гру.
- Карти: кожен вибір з його раундом і порядком вибору, плюс - для гравця-звітувальника - що йому пропонували і від чого він відмовився. Ваші пропозиції приходять лише з вашого клієнта, ніколи з клієнта суперника.
- Бойова статистика: випущені й влучені кулі, спроби й успіхи блоків, завдана шкода і (в 1v1) смерті з причинами.
- Часові ряди для графіків: FPS, пінг, прогрес влучань/блоків і шкода, семпльовані що кілька секунд упродовж усієї гри. (1v2 поки що несе полегшений набір.)
- Здоров’я з’єднання (найповніше в 1v1): фрізи кадрів, паузи мережевої тиші і чи спинялися живі оновлення суперника.
- Знімок фінального білда кожного гравця, зроблений на кінці гри, перш ніж щось встигне його стерти.
- Темп вводу: скільки ігрових клавіш і кліків ви натиснули, поки були живі в бою. Рахуються лише клавіші руху, вогню і блоку, лише під час активного бою, і лічба стає на паузу, поки ви друкуєте в будь-якому чаті чи тримаєте меню відкритим.
- <color=#7FE87F>Ядро результату ПІДПИСАНЕ клієнтом-звітувальником</color>, тож його не змінити в дорозі, а стороння програма не зможе його підробити. Статистична телеметрія їде поза підписом і вважається довідковою - корисні дані, ніколи не доказ.

<color=#FFD94D><b>ЩО РОБИТЬ ІНШИЙ КЛІЄНТ</b></color>

- Не-звітувальник теж проганяє весь конвеєр кінця гри - досягнення, підсумки сесії, власний збір статистики. Він просто не надсилає матч.
- Під час матчу обидва клієнти що кілька секунд публікують одне одному через кімнату свою живу статистику. Саме так звіт несе ВАШІ числа пострілів/влучань/блоків, коли подає його суперник.
- Відповідь сервера бачить лише клієнт звітувальника - тому сповіщення XP і рахунок серії спершу з’являються на одному екрані.

<color=#FFD94D><b>ЗВИЧАЙНІ ІГРИ ТЕЖ ЗАПИСУЮТЬСЯ</b></color>

- Звичайна 1v1 пише той самий повний рядок матчу, що й рейтингова: рахунок, карти, тривалість, уся телеметрія.
- Обидва гравці заробляють XP - база 250, x1.5 за перемогу, +100 за суху 5-0 - і XP конвертується в золото за звичайним курсом 100 XP = 1 золото. Звичайні стріки перемог для досягнень теж рахуються.
- Чого звичайна не торкається ніколи: ні серій, ні зміни рейтингу, ні ставок, ні рейтингового % виходів.
- Ванільний суперник отримує сторінку статистики, автостворену зі звіту. <color=#7FE87F>Вони зберігають чистий ванільний геймплей, і єдина частина мода, яку вони взагалі можуть побачити, - стилізація неймтега</color> (див. <color=#7FD4FF>Що бачать гравці без мода</color>).$s256$)
  , ('33e496e0673a0869', 'es', '731149dda4262f45fd2b9920bd5e2584ed18d14a', $s256$Nadie en una partida de ROUNDS es el host. Cada partida pasa por los servidores en la nube de Photon, cada jugador simula el combate localmente, y cada tirador es el árbitro de sus propias balas. Esta página explica cómo encaja todo.

<color=#FFD94D><b>CÓMO OCURRE UNA CONEXIÓN</b></color>

- Tu cliente habla primero con un servidor de nombres de Photon, hace ping a las 15 regiones (us, eu, asia, au y el resto) y elige la mejor. El resultado se guarda entre arranques.
- Luego se conecta al servidor maestro de esa región, que lleva el emparejamiento. Unirte a una sala o crearla te transfiere a un servidor de juego de esa región, y la sala vive ALLÍ: todo el tráfico es tú, subiendo a Photon, bajando a los demás jugadores. Nunca hay un enlace directo entre los PC de los jugadores.
- El quickplay solo empareja jugadores de tu región actual. Si pasas 15 segundos buscando solo, el juego salta de región por su cuenta, cambiando un poco de ping por un grupo de jugadores mayor.

<color=#FFD94D><b>CÓDIGOS DE SALA Y JUEGO ENTRE REGIONES</b></color>

Un código de sala privado son 6 letras: la PRIMERA codifica la región del host, las otras 5 son aleatorias. Unirse por código lee esa letra y te mueve a la región del host antes de buscar, y por eso amigos en continentes distintos siempre pueden juntarse. Las invitaciones de Steam llevan la región igual. Las salas de cola del mod se saltan todo esto: el servidor nombra la sala y elige UNA región para todos los emparejados, así que una pareja encolada no puede partirse entre regiones.

<color=#FFD94D><b>EL CLIENTE MAESTRO</b></color>

Un jugador de cada sala es el cliente maestro - al principio quien creó la sala (en 1v1, el jugador naranja). El maestro no es un host; su máquina solo recibe los trabajos de desempate:

- tira el siguiente mapa y lo anuncia,
- anuncia cada punto y resultado de ronda - cada cliente aplica el marcador del maestro al pie de la letra, así el marcador no puede discrepar entre pantallas,
- posee y simula físicamente las cajas, sierras y plataformas móviles; los demás reciben sus posiciones como un flujo, y tus empujones a una caja se envían al maestro como peticiones.

Si el maestro se va, Photon nombra a otro - aunque en el 1v1 vanilla apenas importa, porque cualquier jugador que se va termina la partida para todos.

<color=#FFD94D><b>QUÉ VIAJA POR EL CABLE, QUÉ SE QUEDA LOCAL</b></color>

- <color=#7FD4FF>Movimiento del jugador</color> - en flujo. Tu máquina envía tu posición, inputs y velocidad hasta 30 veces por segundo, y las copias de ti en los demás reproducen ese flujo. Una copia remota de un jugador nunca lee input.
- <color=#7FD4FF>Bloqueos</color> - instantáneos en tu pantalla, retransmitidos a los demás como evento. Su copia de tu escudo se enciende cuando el evento llega.
- <color=#7FD4FF>Balas</color> - generadas una vez, luego simuladas por separado en cada máquina, fotograma a fotograma, sin corrección en vuelo (salvo unas pocas cartas guiadas). La bala en tu pantalla y la misma bala en la suya son dos copias que divergen despacio.
- <color=#7FD4FF>Daño</color> - calculado una vez, en la máquina del tirador, y enviado como número final. La vida nunca se resincroniza; las pantallas coinciden solo porque todos aplican los mismos eventos de daño. <color=#8A8A93>(La única excepción es la sincronización de veneno del mod, donde el cliente de la VÍCTIMA juzga los ticks - ver <color=#7FD4FF>Veneno y daño en el tiempo</color>.)</color>

<color=#FFD94D><b>AUTORIDAD DEL DAÑO</b></color>

Solo el dueño de una bala puede declarar un impacto. Cuando la copia del tirador de su bala te toca, su máquina consulta su copia de tu escudo y tu posición, dictamina bloqueada o no y difunde el resultado. Tu máquina lo aplica sin votar.

Todo lo defensivo que hagas cuenta, por tanto, solo cuando ha LLEGADO a la pantalla del tirador. Pulsa bloqueo, y allí te protege más o menos la mitad de tu ping más la mitad del suyo después de que te protegiera en casa. Esta única regla explica los clásicos: 'bloqueé a tiempo y aun así me dieron' - tu pulsación todavía no les había llegado (ver <color=#7FD4FF>Bloqueo</color>); y 'me dieron detrás de la esquina' - en su pantalla aún no estabas tras la esquina, porque su copia de tu posición corre tarde por el mismo retraso más hasta un tick de movimiento de 33 ms. El consuelo es la simetría: tus balas se dictaminan en TU pantalla.

<color=#FFD94D><b>QUÉ MIDE REALMENTE EL PING</b></color>

El número de ping (el mod lo muestra en el overlay de la esquina, junto a tu región) es el viaje de ida y vuelta entre TÚ y el servidor de Photon - no entre tú y tu rival. El retraso que sientes contra otro jugador es aproximadamente la mitad de tu ping más la mitad del suyo, más hasta un tick de movimiento de 33 ms. Dos jugadores a 40 ms cada uno juegan una partida más fina que uno de 20 ms contra uno de 150 ms, por bonito que luzca ese 20.

<color=#FFD94D><b>QUÉ CAMBIA LA TASA DE FOTOGRAMAS</b></color>

- Las balas integran su movimiento una vez por fotograma dibujado, así que tasas distintas producen trayectorias ligeramente distintas para la MISMA bala en máquinas distintas - una divergencia pequeña pero estructural.
- El movimiento del jugador corre en un paso de física fijo y es mucho menos sensible a los FPS.
- El caso extremo es la carta Grow, cuyo daño se acumula por fotograma en la máquina del tirador (ver <color=#7FD4FF>Grow</color>).
- Por debajo de unos 30 FPS tu máquina drena el flujo de movimiento entrante más despacio de lo que llega, así que las copias enemigas se ven notablemente más entrecortadas.
- <color=#8A8A93>Una partida puede sentirse horrible con las gráficas de FPS y ping planas - los tirones en el flujo replicado son invisibles para ambos números.</color>$s256$)
  , ('33e496e0673a0869', 'ru', '731149dda4262f45fd2b9920bd5e2584ed18d14a', $s256$В матче ROUNDS никто не хост. Каждая игра идёт через облачные серверы Photon, каждый игрок симулирует бой локально, и каждый стрелок - судья собственных пуль. Эта страница - о том, как всё это складывается вместе.

<color=#FFD94D><b>КАК ПРОИСХОДИТ ПОДКЛЮЧЕНИЕ</b></color>

- Твой клиент сперва обращается к нейм-серверу Photon, пингует 15 регионов (us, eu, asia, au и остальные) и выбирает лучший. Результат кешируется между запусками.
- Затем он подключается к мастер-серверу этого региона, который ведает матчмейкингом. Вход в комнату или её создание передаёт тебя игровому серверу региона, и комната живёт ТАМ: весь трафик - это ты, вверх к Photon, вниз к другим игрокам. Прямой связи между PC игроков нет никогда.
- Quickplay сводит только игроков твоего текущего региона. Если ты сидишь в поиске один 15 секунд, игра сама прыгает по регионам, меняя немного пинга на больший пул игроков.

<color=#FFD94D><b>КОДЫ КОМНАТ И ИГРА МЕЖДУ РЕГИОНАМИ</b></color>

Приватный код комнаты - 6 букв: ПЕРВАЯ кодирует регион хоста, остальные 5 случайны. Вход по коду читает эту букву и переносит тебя в регион хоста до поиска - вот почему друзья с разных континентов всегда могут зайти друг к другу. Приглашения Steam несут регион так же. Комнаты модовых очередей всё это пропускают: сервер сам называет комнату и выбирает ОДИН регион для всех, кого свёл, так что сведённая пара не может расщепиться по регионам.

<color=#FFD94D><b>МАСТЕР-КЛИЕНТ</b></color>

Один игрок в каждой комнате - мастер-клиент: изначально создатель комнаты (в 1v1 - оранжевый игрок). Мастер не хост; его машина просто получает работу третейского судьи:

- разыгрывает следующую карту-арену и объявляет её,
- объявляет каждый результат очка и раунда - каждый клиент применяет счёт мастера дословно, так что табло не может разойтись между экранами,
- владеет и физически симулирует ящики, пилы и движущиеся платформы; остальные получают их позиции потоком, а твои толчки ящика отправляются мастеру как запросы.

Если мастер уходит, Photon назначает нового - впрочем, в ванильном 1v1 это почти неважно: любой ушедший игрок завершает матч для всех.

<color=#FFD94D><b>ЧТО ЕДЕТ ПО ПРОВОДУ, А ЧТО ОСТАЁТСЯ ЛОКАЛЬНЫМ</b></color>

- <color=#7FD4FF>Движение игрока</color> - потоком. Твоя машина шлёт позицию, ввод и скорость до 30 раз в секунду, а чужие копии тебя проигрывают этот поток. Удалённая копия игрока никогда не читает ввод.
- <color=#7FD4FF>Блоки</color> - мгновенны на твоём экране, остальным ретранслируются событием. Их копия твоего щита включается, когда событие доходит.
- <color=#7FD4FF>Пули</color> - создаются один раз, затем симулируются отдельно на каждой машине, кадр за кадром, без коррекции в полёте (кроме пары управляемых карт). Пуля на твоём экране и та же пуля на их - две медленно расходящиеся копии.
- <color=#7FD4FF>Урон</color> - считается один раз, на машине стрелка, и отправляется финальным числом. Здоровье никогда не пересинхронизируется; экраны согласны лишь потому, что все применяют одни и те же события урона. <color=#8A8A93>(Единственное исключение - модовая синхронизация яда, где тики судит клиент ЖЕРТВЫ - см. <color=#7FD4FF>Яд и урон со временем</color>.)</color>

<color=#FFD94D><b>АВТОРИТЕТ УРОНА</b></color>

Объявить попадание может только владелец пули. Когда копия пули стрелка касается тебя, его машина проверяет свою копию твоего щита и твоей позиции, судит «блокировано или нет» и рассылает результат. Твоя машина применяет его без голосования.

Поэтому всё защитное, что ты делаешь, считается только когда ДОЕХАЛО до экрана стрелка. Нажми блок - и там он защитит тебя примерно на половину твоего пинга плюс половину его позже, чем защитил дома. Одно это правило объясняет классику: «я заблокировал вовремя и всё равно получил» - твоё нажатие ещё не дошло до них (см. <color=#7FD4FF>Блокирование</color>); и «меня ударило за углом» - на их экране ты ещё не был за углом, потому что их копия твоей позиции опаздывает на ту же задержку плюс до одного тика движения в 33 мс. Утешение - симметрия: твои пули судятся на ТВОЁМ экране.

<color=#FFD94D><b>ЧТО НА САМОМ ДЕЛЕ МЕРЯЕТ ПИНГ</b></color>

Число пинга (мод показывает его в угловом оверлее, рядом с твоим регионом) - это круговой путь между ТОБОЙ и сервером Photon, не между тобой и соперником. Задержка, которую ты чувствуешь против другого игрока, - примерно половина твоего пинга плюс половина его, плюс до одного тика движения в 33 мс. Два игрока по 40 мс играют плотнее, чем игрок с 20 мс против игрока со 150 мс, хотя эти 20 выглядят прекрасно.

<color=#FFD94D><b>ЧТО МЕНЯЕТ ЧАСТОТА КАДРОВ</b></color>

- Пули интегрируют своё движение раз на отрисованный кадр, так что разные частоты кадров дают слегка разные траектории ОДНОЙ И ТОЙ ЖЕ пули на разных машинах - малое, но структурное расхождение.
- Движение игрока идёт на фиксированном шаге физики и куда меньше зависит от частоты кадров.
- Крайний случай - карта Grow, чей урон накапливается покадрово на машине стрелка (см. <color=#7FD4FF>Grow</color>).
- Ниже примерно 30 FPS твоя машина сливает входящий поток движения медленнее, чем он приходит, и чужие копии становятся заметно дёрганее.
- <color=#8A8A93>Игра может ощущаться ужасно при ровных графиках FPS и пинга - дрожь в реплицированном потоке невидима для обоих чисел.</color>$s256$)
  , ('33e496e0673a0869', 'sv', '731149dda4262f45fd2b9920bd5e2584ed18d14a', $s256$Ingen i en ROUNDS-match är värden. Varje match går genom Photons molnservrar, varje spelare simulerar striden lokalt, och varje skytt är domare över sina egna kulor. Den här sidan är hur allt det hänger ihop.

<color=#FFD94D><b>SÅ SKER EN ANSLUTNING</b></color>

- Din klient pratar först med en Photon-namnserver, pingar de 15 regionerna (us, eu, asia, au och resten) och väljer den bästa. Resultatet cachas mellan starter.
- Den ansluter sedan till regionens masterserver, som sköter matchmaking. Att gå med i eller skapa ett rum lämnar över dig till en spelserver i den regionen, och rummet bor DÄR: all trafik är du, upp till Photon, ner till de andra spelarna. Det finns aldrig en direkt länk mellan spelarnas datorer.
- Quickplay matchar bara spelare i din nuvarande region. Sitter du ensam i en sökning i 15 sekunder byter spelet region på egen hand och byter lite ping mot en större spelarpool.

<color=#FFD94D><b>RUMSKODER OCH SPEL ÖVER REGIONER</b></color>

En privat rumskod är 6 bokstäver: den FÖRSTA bokstaven kodar värdens region, de andra 5 är slumpade. Att gå med via kod läser den bokstaven och flyttar dig till värdens region innan sökningen, vilket är varför vänner på olika kontinenter alltid kan spela ihop. Steam-inbjudningar bär regionen på samma sätt. Moddens kö-rum hoppar över allt detta: servern namnger rummet och väljer EN region för alla den matchat, så ett köat par kan aldrig splittras över regioner.

<color=#FFD94D><b>MASTERKLIENTEN</b></color>

En spelare i varje rum är masterklienten - från början den som skapade rummet (i 1v1 den orangea spelaren). Mastern är ingen värd; deras maskin får bara skiljedomarjobben:

- slumpar nästa karta och annonserar den,
- annonserar varje poäng- och rondresultat - varje klient tillämpar masterns ställning ordagrant, så poängtavlan kan inte skilja sig mellan skärmar,
- äger och simulerar fysiken för lådorna, sågarna och de rörliga plattformarna; alla andra tar emot deras positioner som en ström, och dina knuffar på en låda skickas till mastern som förfrågningar.

Om mastern lämnar utser Photon en ny - fast i vanilla-1v1 spelar det knappt någon roll, eftersom vilken spelare som helst som lämnar avslutar matchen för alla.

<color=#FFD94D><b>VAD SOM FÄRDAS PÅ TRÅDEN, VAD SOM STANNAR LOKALT</b></color>

- <color=#7FD4FF>Spelarrörelse</color> - strömmas. Din maskin skickar din position, dina inputs och din hastighet upp till 30 gånger i sekunden, och andra spelares kopior av dig spelar upp den strömmen. En fjärrkopia av en spelare läser aldrig input.
- <color=#7FD4FF>Block</color> - omedelbara på din egen skärm, vidarebefordrade till alla andra som en händelse. Deras kopia av din sköld slås på när händelsen anländer.
- <color=#7FD4FF>Kulor</color> - spawnas en gång, simuleras sedan separat på varje maskin, bildruta för bildruta, utan korrigering under flykten (ett fåtal styrda kort undantagna). Kulan på din skärm och samma kula på deras är två långsamt divergerande kopior.
- <color=#7FD4FF>Skada</color> - beräknas en gång, på skyttens maskin, och skickas som en färdig siffra. Hälsa omsynkas aldrig; skärmarna är överens bara för att alla tillämpar samma skadehändelser. <color=#8A8A93>(Det enda undantaget är moddens giftsynk, där OFFRETS klient dömer ticksen - se <color=#7FD4FF>Gift & skada över tid</color>.)</color>

<color=#FFD94D><b>SKADEAUKTORITET</b></color>

Bara en kulas ägare kan utropa en träff. När skyttens kopia av deras kula rör dig kontrollerar deras maskin sin kopia av din sköld och din position, dömer blockad eller inte, och sänder ut resultatet. Din maskin tillämpar det utan omröstning.

Allt defensivt du gör räknas därför först när det har ANLÄNT till skyttens skärm. Tryck block, och det skyddar dig där ungefär halva din ping plus halva deras senare än det skyddade dig hemma. Den enda regeln förklarar klassikerna: 'jag blockade i tid och blev träffad ändå' - ditt tryck hade inte nått dem än (se <color=#7FD4FF>Blockering</color>); och 'jag blev träffad runt hörnet' - på deras skärm var du inte bakom hörnet än, eftersom deras kopia av din position ligger efter med samma fördröjning plus upp till en rörelsetick på 33 ms. Trösten är symmetrin: dina kulor döms på DIN skärm.

<color=#FFD94D><b>VAD PING FAKTISKT MÄTER</b></color>

Pingsiffran (modden visar den i hörnoverlayen, bredvid din region) är rundresan mellan DIG och Photon-servern - inte mellan dig och din motståndare. Fördröjningen du känner mot en annan spelare är ungefär halva din ping plus halva deras, plus upp till en rörelsetick på 33 ms. Två spelare på 40 ms vardera spelar en tightare match än en 20 ms-spelare mot en 150 ms-spelare, även om den där 20:an ser vacker ut.

<color=#FFD94D><b>VAD BILDFREKVENSEN ÄNDRAR</b></color>

- Kulor integrerar sin rörelse en gång per renderad bildruta, så olika bildfrekvenser ger något olika banor för SAMMA kula på olika maskiner - en liten men strukturell divergens.
- Spelarrörelse går på ett fast fysiksteg och är mycket mindre känslig för bildfrekvens.
- Extremfallet är kortet Grow, vars skada ackumuleras per bildruta på skyttens maskin (se <color=#7FD4FF>Grow</color>).
- Under ungefär 30 FPS tömmer din maskin den inkommande rörelseströmmen långsammare än den anländer, så fiendekopior blir synligt hackigare.
- <color=#8A8A93>En match kan kännas hemsk medan både FPS- och pinggraferna är platta - hack i den replikerade strömmen är osynligt för båda siffrorna.</color>$s256$)
  , ('33e496e0673a0869', 'uk', '731149dda4262f45fd2b9920bd5e2584ed18d14a', $s256$У матчі ROUNDS ніхто не хост. Кожна гра йде через хмарні сервери Photon, кожен гравець симулює бій локально, і кожен стрілець - суддя власних куль. Ця сторінка про те, як усе це складається докупи.

<color=#FFD94D><b>ЯК ВІДБУВАЄТЬСЯ З’ЄДНАННЯ</b></color>

- Ваш клієнт спершу говорить із сервером імен Photon, пінгує 15 регіонів (us, eu, asia, au та решту) і обирає найкращий. Результат кешується між запусками.
- Далі він під’єднується до майстер-сервера цього регіону, який займається підбором. Вхід чи створення кімнати передає вас ігровому серверу того регіону, і кімната живе ТАМ: увесь трафік - це ви, вгору до Photon, вниз до інших гравців. Прямого з’єднання між ПК гравців немає ніколи.
- Швидкий матч підбирає лише гравців вашого поточного регіону. Якщо ви просиділи в пошуку самі 15 секунд, гра сама стрибає регіонами, міняючи трохи пінгу на більший пул гравців.

<color=#FFD94D><b>КОДИ КІМНАТ І ГРА МІЖ РЕГІОНАМИ</b></color>

Приватний код кімнати - 6 літер: ПЕРША кодує регіон хоста, решта 5 випадкові. Вхід за кодом читає цю літеру і переносить вас у регіон хоста перед пошуком - тому друзі з різних континентів завжди можуть зайти одне до одного. Запрошення Steam несуть регіон так само. Модові кімнати черги все це пропускають: сервер сам називає кімнату й обирає ОДИН регіон для всіх, кого підібрав, тож пара з черги ніколи не розщепиться між регіонами.

<color=#FFD94D><b>МАЙСТЕР-КЛІЄНТ</b></color>

Один гравець у кожній кімнаті - майстер-клієнт: спочатку той, хто створив кімнату (в 1v1 - помаранчевий гравець). Майстер - не хост; його машина просто отримує роботи-арбітри:

- кидає наступну мапу й оголошує її,
- оголошує кожне очко і результат раунду - кожен клієнт застосовує рахунок майстра дослівно, тож табло не може розійтися між екранами,
- володіє ящиками, пилками та рухомими платформами і фізично їх симулює; решта отримують їхні позиції потоком, а ваші поштовхи ящика надсилаються майстру як запити.

Якщо майстер іде, Photon призначає нового - хоча у ванільному 1v1 це майже не важить, бо вихід будь-якого гравця завершує матч для всіх.

<color=#FFD94D><b>ЩО ЇДЕ ДРОТОМ, А ЩО ЛИШАЄТЬСЯ ЛОКАЛЬНО</b></color>

- <color=#7FD4FF>Рух гравця</color> - потоком. Ваша машина шле вашу позицію, ввід і швидкість до 30 разів на секунду, і чужі копії вас відтворюють цей потік. Віддалена копія гравця ніколи не читає ввід.
- <color=#7FD4FF>Блоки</color> - миттєві на вашому екрані, решті ретранслюються подією. Їхня копія вашого щита вмикається, коли подія прибуває.
- <color=#7FD4FF>Кулі</color> - заспавнені один раз, далі симулюються окремо на кожній машині, кадр за кадром, без корекції в польоті (кілька керованих карт - виняток). Куля на вашому екрані і та сама куля на їхньому - дві копії, що повільно розходяться.
- <color=#7FD4FF>Шкода</color> - обчислюється один раз, на машині стрільця, і надсилається готовим числом. Здоров’я ніколи не пересинхронізується; екрани сходяться лише тому, що всі застосовують ті самі події шкоди. <color=#8A8A93>(Єдиний виняток - модова синхронізація отрути, де тіки судить клієнт ЖЕРТВИ - див. <color=#7FD4FF>Отрута та поступова шкода</color>.)</color>

<color=#FFD94D><b>АВТОРИТЕТ ШКОДИ</b></color>

Лише власник кулі може оголосити влучання. Коли копія кулі стрільця торкається вас, його машина перевіряє власну копію вашого щита і вашої позиції, судить «блоковано чи ні» і розсилає результат. Ваша машина застосовує його без голосування.

Тому все захисне, що ви робите, рахується лише тоді, коли воно ПРИБУЛО на екран стрільця. Натисніть блок - і там він захистить вас приблизно на половину вашого пінгу плюс половину їхнього пізніше, ніж захистив удома. Це одне правило пояснює класику: «я заблокував вчасно і все одно отримав» - ваше натискання ще не дійшло до них (див. <color=#7FD4FF>Блокування</color>); і «мене вдарило за рогом» - на їхньому екрані ви ще не були за рогом, бо їхня копія вашої позиції спізнюється на ту саму затримку плюс до одного 33-мс тіка руху. Втіха - симетрія: ваші кулі судяться на ВАШОМУ екрані.

<color=#FFD94D><b>ЩО НАСПРАВДІ МІРЯЄ ПІНГ</b></color>

Число пінгу (мод показує його в кутовому оверлеї, поруч із вашим регіоном) - це час туди-назад між ВАМИ і сервером Photon, не між вами й суперником. Затримка, яку ви відчуваєте проти іншого гравця, - приблизно половина вашого пінгу плюс половина їхнього, плюс до одного 33-мс тіка руху. Двоє гравців по 40 мс грають щільнішу гру, ніж гравець на 20 мс проти гравця на 150 мс, хоч ті 20 і виглядають красиво.

<color=#FFD94D><b>ЩО ЗМІНЮЄ ЧАСТОТА КАДРІВ</b></color>

- Кулі інтегрують свій рух раз на відрендерений кадр, тож різні частоти кадрів дають трохи різні траєкторії ТІЄЇ САМОЇ кулі на різних машинах - мала, але структурна розбіжність.
- Рух гравця йде на фіксованому фізичному кроці й від частоти кадрів залежить значно менше.
- Крайній випадок - карта Grow, чия шкода нарощується щокадру на машині стрільця (див. <color=#7FD4FF>Grow</color>).
- Нижче приблизно 30 FPS ваша машина зливає вхідний потік руху повільніше, ніж він прибуває, тож ворожі копії смикаються помітно сильніше.
- <color=#8A8A93>Гра може відчуватися жахливо, коли графіки і FPS, і пінгу рівні - смикання в реплікованому потоці невидиме для обох чисел.</color>$s256$)
  , ('39b640c135d8a2c3', 'es', 'a56da30dfbe68320419ddfbcbf5fb5a103ff4de5', $s256$Ningún artículo coincide con tu búsqueda.$s256$)
  , ('39b640c135d8a2c3', 'ru', 'a56da30dfbe68320419ddfbcbf5fb5a103ff4de5', $s256$По твоему запросу статей не найдено.$s256$)
  , ('39b640c135d8a2c3', 'sv', 'a56da30dfbe68320419ddfbcbf5fb5a103ff4de5', $s256$Inga artiklar matchar din sökning.$s256$)
  , ('39b640c135d8a2c3', 'uk', 'a56da30dfbe68320419ddfbcbf5fb5a103ff4de5', $s256$За вашим запитом статей не знайдено.$s256$)
  , ('3a55d6d7a2ec803c', 'es', '2b8293c4e72cd26a912b45941620fcee37ccdda8', $s256$Los colores de cuerpo en ROUNDS son colores de equipo: el juego guarda cuatro skins de cuerpo y elige una por número de equipo. Quién recibe qué color se deduce de cómo numera sus equipos cada modo.

<color=#FFD94D><b>1v1 VANILLA</b></color>

En un 1v1 cada jugador es su propio equipo: el primer asiento es el equipo 0 y juega de <color=#7FD4FF>naranja</color>, el segundo es el equipo 1 y juega de <color=#7FD4FF>azul</color>. Vanilla nunca usa más que estos dos equipos online.

<color=#FFD94D><b>MODOS DE EQUIPO: 2v2 Y 1v2</b></color>

- <color=#7FD4FF>2v2</color> - el servidor parte a los cuatro jugadores en dos parejas al cerrarse el emparejamiento. Los compañeros comparten un color de cuerpo: naranja el primer equipo, azul el segundo.
- <color=#7FD4FF>1v2</color> - el jugador solo es un equipo (naranja); el dúo comparte el otro (azul).

<color=#FFD94D><b>FFA: DIEZ JUGADORES, CUATRO SKINS</b></color>

En FFA cada jugador es su propio equipo, numerado por plaza de la sala. ROUNDS trae exactamente cuatro skins de cuerpo, así que <color=#FF6666>los colores se repiten cada cuatro jugadores</color>: el 1.º, el 5.º y el 9.º comparten color, el 2.º, el 6.º y el 10.º comparten el siguiente, y así. Es deliberado - el mod no añade skins nuevas, y las etiquetas de nombre sobre la cabeza son lo que distingue a jugadores del mismo color. En una sala grande, lee el nombre, no solo el cuerpo.

<color=#FFD94D><b>LA PANTALLA DE ELECCIÓN DE CARTA</b></color>

El cuerpo de pie en el escenario de elección es un clon de la skin del elector. En modos de equipo vanilla tiene dos problemas ahí: una carrera de orden de carga puede hornear el color del equipo EQUIVOCADO en ese clon, y vanilla solo presenta a un elector por ronda aunque un equipo perdedor tenga dos.

El mod arregla ambos. Recomprueba los colores de equipo reales unos fotogramas después de aparecer el escenario y retiñe el cuerpo si salió mal, y en 2v2 y 1v2 repite el escenario para cada elector por turno - así cada elector aparece como sí mismo, con su color correcto. El FFA no usa el escenario vanilla en absoluto: todos eligen a la vez en su propia pantalla.

<color=#FFD94D><b>COLORES DE JUGADOR PERSONALIZADOS</b></color>

Un cosmético de <color=#7FD4FF>color de jugador</color> de la tienda (ver <color=#7FD4FF>Tienda y cosméticos</color>) sustituye tu color de equipo en la pantalla de cada jugador con mod; los espectadores pueden desactivarlo con el ajuste Mostrar colores de jugador. Los especiales animados como Prismático y Cromo ciclan su color unas 30 veces por segundo. <color=#7FE87F>Los jugadores sin el mod siguen viendo el naranja y azul estándar - para ellos tu partida se ve intacta.</color>

En pantallas con mod el color es además tu identidad de equipo: los anuncios de punto nombran tu color (punto para MOSTAZA, en vez de NARANJA), los puntos del contador de rondas y la franja de marcador FFA se tiñen a juego, y tu etiqueta de nombre en partida también se tiñe - salvo que lleves equipado un color de nombre de pago, que siempre gana. La identidad se resuelve desde datos compartidos, así que todos con la función activada ven los mismos nombres y puntos; quien la tenga apagada ve cuerpos y tintes vanilla (los NOMBRES de equipo personalizados sí se muestran).$s256$)
  , ('3a55d6d7a2ec803c', 'ru', '2b8293c4e72cd26a912b45941620fcee37ccdda8', $s256$Цвета тел в ROUNDS - командные: игра держит четыре скина тела и выбирает один по номеру команды. Кто получает какой цвет, следует из того, как каждый режим нумерует команды.

<color=#FFD94D><b>ВАНИЛЬНЫЙ 1v1</b></color>

В 1v1 каждый игрок - своя команда: первое место - команда 0 и играет <color=#7FD4FF>оранжевым</color>, второе - команда 1 и играет <color=#7FD4FF>синим</color>. Онлайн ваниль никогда не использует больше этих двух команд.

<color=#FFD94D><b>КОМАНДНЫЕ РЕЖИМЫ: 2v2 И 1v2</b></color>

- <color=#7FD4FF>2v2</color> - сервер делит четырёх игроков на две пары при фиксации матча. Тиммейты делят один цвет тела: оранжевый у первой команды, синий у второй.
- <color=#7FD4FF>1v2</color> - соло-игрок - одна команда (оранжевая); дуо делит другую (синюю).

<color=#FFD94D><b>FFA: ДЕСЯТЬ ИГРОКОВ, ЧЕТЫРЕ СКИНА</b></color>

В FFA каждый игрок - своя команда с номером по слоту лобби. ROUNDS поставляет ровно четыре скина тела, так что <color=#FF6666>цвета повторяются каждые четыре игрока</color>: 1-й, 5-й и 9-й делят один цвет, 2-й, 6-й и 10-й - следующий, и так далее. Это сознательно - мод не добавляет новых скинов, а различают одноцветных игроков неймтеги над головой. В большом лобби читай имя, а не только тело.

<color=#FFD94D><b>ЭКРАН ВЫБОРА КАРТ</b></color>

Тело на сцене выбора - клон скина выбирающего. В командных режимах у ванили там две проблемы: гонка порядка загрузки может запечь в этот клон цвет НЕ ТОЙ команды, и ваниль всегда представляет лишь одного пикера за раунд, даже когда у проигравшей команды их два.

Мод чинит обе. Он перепроверяет реальные командные цвета через несколько кадров после появления сцены и перекрашивает тело, если оно вышло неправильным, а в 2v2 и 1v2 перезапускает сцену для каждого пикера по очереди - каждый появляется как он сам, в правильном цвете. FFA ванильную сцену не использует вовсе: все выбирают одновременно, каждый на своём экране.

<color=#FFD94D><b>КАСТОМНЫЕ ЦВЕТА ИГРОКА</b></color>

Косметика <color=#7FD4FF>цвет игрока</color> из магазина (см. <color=#7FD4FF>Магазин и косметика</color>) заменяет твой командный цвет на экране каждого модового игрока; зрители могут отказаться настройкой «Показывать цвета игроков». Анимированные особые вроде Prismatic и Chrome меняют цвет примерно 30 раз в секунду. <color=#7FE87F>Игроки без мода продолжают видеть стандартные оранжевый и синий - для них твоя игра выглядит нетронутой.</color>

На модовых экранах цвет - ещё и твоя командная принадлежность: объявления очков называют имя твоего цвета (очко берёт MUSTARD, а не ORANGE), точки счётчика раундов и полоса счёта FFA подкрашиваются под него, и твой внутриигровой неймтег тоже - если не надет платный цвет неймтега, который всегда побеждает. Принадлежность разрешается из общих данных, так что все с включённой настройкой видят одни и те же имена и точки; игрок с выключенной видит ванильные тела и подкраски (кастомные ИМЕНА команд всё равно видны).$s256$)
  , ('3a55d6d7a2ec803c', 'sv', '2b8293c4e72cd26a912b45941620fcee37ccdda8', $s256$Kroppsfärger i ROUNDS är lagfärger: spelet har fyra kroppsskins och väljer ett efter lagnummer. Vem som får vilken färg följer av hur varje läge numrerar sina lag.

<color=#FFD94D><b>VANILLA-1v1</b></color>

I en 1v1 är varje spelare sitt eget lag: första platsen är lag 0 och spelar <color=#7FD4FF>orange</color>, andra platsen är lag 1 och spelar <color=#7FD4FF>blå</color>. Vanilla använder aldrig fler än dessa två lag online.

<color=#FFD94D><b>LAGLÄGEN: 2v2 OCH 1v2</b></color>

- <color=#7FD4FF>2v2</color> - servern delar de fyra spelarna i två par när matchen låses. Lagkamrater delar en kroppsfärg: orange för första laget, blå för andra.
- <color=#7FD4FF>1v2</color> - solospelaren är ett lag (orange); duon delar det andra (blå).

<color=#FFD94D><b>FFA: TIO SPELARE, FYRA SKINS</b></color>

I FFA är varje spelare sitt eget lag, numrerat efter lobbyplats. ROUNDS levererar exakt fyra kroppsskins, så <color=#FF6666>färgerna upprepas var fjärde spelare</color>: spelare 1, 5 och 9 delar en färg, spelare 2, 6 och 10 delar nästa, och så vidare. Det är avsiktligt - modden lägger inte till nya skins, och namnskyltarna ovanför är det som skiljer likafärgade spelare åt. I en stor lobby: läs namnet, inte bara kroppen.

<color=#FFD94D><b>KORTVALSSKÄRMEN</b></color>

Kroppen som står på valscenen är en klon av väljarens skin. I laglägen har vanilla två problem där: en kapplöpning i laddningsordningen kan baka in FEL lags färg i klonen, och vanilla visar bara en väljare per rond även när ett förlorande lag har två.

Modden fixar båda. Den kontrollerar de riktiga lagfärgerna igen några bildrutor efter att scenen dykt upp och tonar om kroppen om den blev fel, och i 2v2 och 1v2 kör den om scenen för varje väljare i tur och ordning - så varje väljare visas som sig själv, i rätt färg. FFA använder inte vanilla-scenen alls: alla väljer samtidigt på sin egen skärm.

<color=#FFD94D><b>EGNA SPELARFÄRGER</b></color>

En <color=#7FD4FF>spelarfärg</color>-kosmetik från butiken (se <color=#7FD4FF>Butik & kosmetik</color>) ersätter din lagfärg på varje moddad spelares skärm; betraktare kan välja bort med inställningen Visa spelarfärger. Animerade specialare som Prismatic och Chrome cyklar sin färg ungefär 30 gånger i sekunden. <color=#7FE87F>Spelare utan modden fortsätter se standardorange och standardblått - för dem ser din match orörd ut.</color>

På moddade skärmar är färgen också din lagidentitet: poängutrop ropar din färgs namn (SENAP tog en poäng, i stället för ORANGE), rondräknarens prickar och FFA-poängremsan tonas för att matcha, och din namnskylt i matchen tonas också - om inte en betald namnskyltsfärg är utrustad, för den vinner alltid. Identiteten löses från delade data, så alla med funktionen på ser samma namn och prickar; en spelare med den av ser vanilla-kroppar och vanilla-toner (de egna lagNAMNEN syns fortfarande).$s256$)
  , ('3a55d6d7a2ec803c', 'uk', '2b8293c4e72cd26a912b45941620fcee37ccdda8', $s256$Кольори тіла в ROUNDS - командні: гра тримає чотири скіни тіла й обирає один за номером команди. Хто отримує який колір - випливає з того, як кожен режим нумерує свої команди.

<color=#FFD94D><b>ВАНІЛЬНИЙ 1v1</b></color>

У 1v1 кожен гравець - власна команда: перше місце - команда 0 і грає <color=#7FD4FF>помаранчевим</color>, друге - команда 1 і грає <color=#7FD4FF>синім</color>. Ваніль онлайн ніколи не використовує більше цих двох команд.

<color=#FFD94D><b>КОМАНДНІ РЕЖИМИ: 2v2 І 1v2</b></color>

- <color=#7FD4FF>2v2</color> - сервер ділить чотирьох гравців на дві пари в момент фіксації матчу. Тімейти ділять один колір тіла: помаранчевий у першої команди, синій у другої.
- <color=#7FD4FF>1v2</color> - соло-гравець - одна команда (помаранчева); дуо ділить іншу (синю).

<color=#FFD94D><b>FFA: ДЕСЯТЬ ГРАВЦІВ, ЧОТИРИ СКІНИ</b></color>

У FFA кожен гравець - власна команда, нумерована за слотом лобі. ROUNDS постачає рівно чотири скіни тіла, тож <color=#FF6666>кольори повторюються кожні чотири гравці</color>: 1-й, 5-й і 9-й гравці ділять один колір, 2-й, 6-й і 10-й - наступний, і так далі. Це навмисно - мод не додає нових скінів, а неймтеги над головами і є тим, що розрізняє однокольорових. У великому лобі читайте ім’я, а не лише тіло.

<color=#FFD94D><b>ЕКРАН ВИБОРУ КАРТ</b></color>

Тіло на сцені вибору - клон скіна того, хто обирає. У командних режимах ваніль має там дві проблеми: гонка порядку завантаження може запекти в цей клон колір НЕ ТІЄЇ команди, і ваніль показує лише одного обирача за раунд, навіть коли в команди, що програла, їх двоє.

Мод виправляє обидві. Він переперевіряє справжні командні кольори за кілька кадрів після появи сцени й перефарбовує тіло, якщо воно вийшло не тим, а у 2v2 і 1v2 проганяє сцену для кожного обирача по черзі - тож кожен обирач з’являється як він сам, у правильному кольорі. FFA ванільної сцени не використовує взагалі: всі обирають одночасно, кожен на своєму екрані.

<color=#FFD94D><b>КАСТОМНІ КОЛЬОРИ ГРАВЦІВ</b></color>

Косметика <color=#7FD4FF>колір гравця</color> з магазину (див. <color=#7FD4FF>Магазин і косметика</color>) замінює ваш командний колір на екрані кожного гравця з модом; глядачі можуть відмовитися налаштуванням «Показувати кольори гравців». Анімовані особливі, як-от Prismatic і Chrome, циклять свій колір близько 30 разів на секунду. <color=#7FE87F>Гравці без мода далі бачать стандартні помаранчевий і синій - для них ваша гра виглядає незайманою.</color>

На екранах з модом колір - це ще і ваша командна ідентичність: оголошення очок називають ім’я вашого кольору (очко здобув ГІРЧИЧНИЙ, а не ПОМАРАНЧЕВИЙ), крапки лічильника раундів і смуга рахунку FFA підфарбовуються в тон, і ваш внутрішньоігровий неймтег теж - якщо не вдягнено платний колір неймтега, який завжди перемагає. Ідентичність розв’язується зі спільних даних, тож усі з увімкненою функцією бачать ті самі імена й крапки; гравець із вимкненою бачить ванільні тіла й тони (кастомні НАЗВИ команд усе одно показуються).$s256$)
  , ('3bf441e561ef91aa', 'es', '477344d232738a1940fb13fed234ad833fbb080f', $s256$Empieza aquí$s256$)
  , ('3bf441e561ef91aa', 'ru', '477344d232738a1940fb13fed234ad833fbb080f', $s256$Начни здесь$s256$)
  , ('3bf441e561ef91aa', 'sv', '477344d232738a1940fb13fed234ad833fbb080f', $s256$Börja här$s256$)
  , ('3bf441e561ef91aa', 'uk', '477344d232738a1940fb13fed234ad833fbb080f', $s256$Почніть тут$s256$)
  , ('3e3901c226612420', 'es', '4c632b2b3d50160e981787806714546a155d2569', $s256$Antitrampas$s256$)
  , ('3e3901c226612420', 'ru', '4c632b2b3d50160e981787806714546a155d2569', $s256$Античит$s256$)
  , ('3e3901c226612420', 'sv', '4c632b2b3d50160e981787806714546a155d2569', $s256$Antifusk$s256$)
  , ('3e3901c226612420', 'uk', '4c632b2b3d50160e981787806714546a155d2569', $s256$Античит$s256$)
  , ('42ca762d56c495c7', 'es', '79ed67952069104e31b39c3145b76a56f1902994', $s256$Cómo funcionan los torneos$s256$)
  , ('42ca762d56c495c7', 'ru', '79ed67952069104e31b39c3145b76a56f1902994', $s256$Как проходят турниры$s256$)
  , ('42ca762d56c495c7', 'sv', '79ed67952069104e31b39c3145b76a56f1902994', $s256$Så fungerar turneringar$s256$)
  , ('42ca762d56c495c7', 'uk', '79ed67952069104e31b39c3145b76a56f1902994', $s256$Як проходять турніри$s256$)
  , ('455b2461eac3e08d', 'es', 'cca4166af39b86d542170871f61b1311ebcee489', $s256$Rating (Glicko-2)$s256$)
  , ('455b2461eac3e08d', 'ru', 'cca4166af39b86d542170871f61b1311ebcee489', $s256$Рейтинги (Glicko-2)$s256$)
  , ('455b2461eac3e08d', 'sv', 'cca4166af39b86d542170871f61b1311ebcee489', $s256$Rating (Glicko-2)$s256$)
  , ('455b2461eac3e08d', 'uk', 'cca4166af39b86d542170871f61b1311ebcee489', $s256$Рейтинги (Glicko-2)$s256$)
  , ('492328683cba65c5', 'es', 'e01ce49fac28b9d9fd21bfb3e832d94aece20e29', $s256$El mod trae 50 logros. Cada uno se desbloquea exactamente una vez por cuenta y paga oro al momento - <color=#7FE87F>100 de oro</color> por defecto, hasta <color=#7FE87F>1000</color> los más difíciles; cada línea de abajo muestra su pago. Míralos en <color=#7FD4FF>Mis stats - Logros</color> del menú F5: cada fila muestra la condición, tu fecha de desbloqueo, el porcentaje de jugadores conocidos del mod que lo tiene y su oro. Haz clic en una fila para ver quién lo ha conseguido (los primeros 500, en orden de desbloqueo).

<color=#FFD94D><b>CÓMO SE COMPRUEBAN</b></color>

- Existen dos comprobadores. 14 logros los juzga tu propio juego en cuanto termina una partida; los otros 36 los juzga el servidor - la mayoría cuando llega una partida, una serie o una actualización de rating, y los tres niveles de traductor cuando se aprueba trabajo de traducción. <color=#8A8A93>Los desbloqueos del servidor pueden saltar un momento después de la partida - es normal.</color>
- Los logros comprobados en cliente necesitan una partida online real. El sandbox, el juego offline y espectar nunca otorgan nada.
- Cada rastreador de condición es por partida y se reinicia al empezar una nueva - una revancha es borrón y cuenta nueva, así que el daño recibido en el juego 1 no puede estropear Intocable en el juego 2. (Los contadores de racha, a propósito, son la excepción: abarcan varias partidas.)
- Los rastreadores de input (Pacifista, Objeto inamovible, Con los pies en la tierra) solo muestrean tus teclas mientras estás vivo y luchando. Las elecciones de carta, la fase de elección y el tiempo muerto nunca cuentan en tu contra, y tampoco escribir en el chat del mod ni el menú F5.
- Los logros comprobados en cliente corren en partidas 1v1, 2v2 y 1v2. Nunca saltan en partidas FFA - el FFA tiene sus propios seis, comprobados por el servidor.
- Una <color=#7FD4FF>barrida</color> comprobada en cliente significa ganar con el rival a 0 rondas. En una sala con objetivo de rondas más corto, un 3-0 también cuenta. <color=#FF6666>Los logros 5-0 comprobados por el servidor exigen al rival a 0 con al menos 5 rondas ganadas.</color>

<color=#FFD94D><b>COMPROBADOS EN CLIENTE: PARTIDAS DE PRECISIÓN</b></color>

- <color=#7FD4FF>Intocable</color> - gana una partida en la que tu vida nunca bajó, ni una vez. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Pacifista</color> - gana sin mantener nunca el botón de disparo durante el combate activo. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Objeto inamovible</color> - gana sin mantener nunca una tecla de movimiento o salto durante el combate activo. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Con los pies en la tierra</color> - gana sin mantener nunca una tecla de salto (Espacio, W, Arriba). <color=#7FE87F>100g</color>
- <color=#7FD4FF>Instinto</color> - gana con 3 o más elecciones de carta, tomando en cada elección la carta de más a la izquierda ya resaltada, sin mover nunca la selección. <color=#8A8A93>Solo se comprueba en salas de cola y de torneo sync - las partidas por código, partidas de torneo async incluidas, lo omiten.</color> <color=#7FE87F>100g</color>

<color=#FFD94D><b>COMPROBADOS EN CLIENTE: BARRIDAS Y PROEZAS</b></color>

- <color=#7FD4FF>Asesino silencioso</color> - barre con Sneaky (o Sneaky Bullets) en tu build. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Total Mayhem</color> - barre con Mayhem en tu build. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Perfección frágil</color> - barre con Glass Cannon en tu build. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Sin escapatoria</color> - barre con Chase en tu build. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Renacer de las cenizas</color> - barre con Phoenix en tu build, sin morir y sin que salte nunca una reanimación de Phoenix. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Rey de la remontada</color> - gana después de que las rondas llegaran a estar tú 0, rival 4 o más. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Baraja trucada</color> - termina una partida con 5 o más copias de una misma carta. No hace falta ganar. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Build divina</color> - gana con Shields Up en tu build, terminando la partida con un arma de 1 bala o menos que recarga en 1 segundo o menos. <color=#7FE87F>100g</color>
- <color=#7FD4FF>De cabeza a lo hondo</color> - toma Abyssal Countdown como tu PRIMERA elección de la partida, actívalo en cada ronda y gana. <color=#7FE87F>300g</color>

<color=#FFD94D><b>BUILDS 1v1 COMPROBADAS POR EL SERVIDOR</b></color>

Se juzgan desde la partida reportada. Debes ser el ganador de la partida salvo que una línea diga otra cosa.

- <color=#7FD4FF>Infierno de balas</color> - gana 5-0 con Barrage en tu build. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Spray and Pray</color> - gana 5-0 con Spray. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Demoledor</color> - gana 5-0 con Explosive Bullet. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Controlled Burst</color> - gana 5-0 con Burst. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Médico de campaña</color> - gana 5-0 con Healing Field. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Nova doble</color> - gana con 2 o más Supernovas. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Leñador</color> - gana con 2 o más Saws. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Pristine Perfection</color> - gana con 2 o más copias de Pristine Perseverance. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Viviendo al límite</color> - gana con 2 o más Glass Cannons. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Silly Drill</color> - gana con Sneaky y Drill juntas. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Poder sostenido</color> - gana con Empower y Healing Field juntas. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Coleccionista</color> - gana con 4 o más copias de una misma carta. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Clutch</color> - gana después de que el marcador llegara a estar en 0 puntos para ti contra 6 o más del rival - es decir, 0-3 abajo en rondas. <color=#7FE87F>100g</color>
- <color=#7FD4FF>¡Gemelos!</color> - ambos jugadores terminan con exactamente 5 cartas cada uno y builds idénticas, número de copias incluido. Lo desbloquean los dos; nadie necesita ganar. <color=#7FE87F>500g</color>$s256$)
  , ('492328683cba65c5', 'ru', 'e01ce49fac28b9d9fd21bfb3e832d94aece20e29', $s256$Мод поставляет 50 достижений. Каждое открывается ровно один раз на аккаунт и платит золото на месте - <color=#7FE87F>100 золота</color> по умолчанию, до <color=#7FE87F>1000</color> за самые тяжёлые; у каждой строки ниже указана её выплата. Смотри их в <color=#7FD4FF>Моя статистика - Достижения</color> в меню F5: каждая строка показывает условие, дату твоего открытия, долю известных игроков мода с ним и его золото. Клик по строке показывает, кто его заработал (первые 500, в порядке открытия).

<color=#FFD94D><b>КАК ОНИ ПРОВЕРЯЮТСЯ</b></color>

- Проверяющих двое. 14 достижений судит твоя собственная игра в момент конца игры; остальные 36 судит сервер - большинство при приходе матча, серии или обновления рейтинга, а три уровня переводчика - при одобрении работы над переводами. <color=#8A8A93>Серверные открытия могут выскочить через мгновение после игры - это нормально.</color>
- Клиентским достижениям нужна настоящая онлайн-игра. Песочница, оффлайн и наблюдение не выдают ничего.
- Каждый трекер условия живёт одну игру и сбрасывается на старте новой - рематч это чистый лист, так что урон, полученный в игре 1, не портит Неприкасаемого в игре 2. (Счётчики побед подряд, по замыслу, исключение: они тянутся через игры.)
- Трекеры ввода (Пацифист, Неподвижный объект, Приземлённый) снимают клавиши, только пока ты жив и дерёшься. Пики карт, фаза выбора и время в мёртвых не считаются против тебя, как и печать в чате мода или меню F5.
- Клиентские достижения работают в играх 1v1, 2v2 и 1v2. Из FFA они не срабатывают никогда - у FFA своя шестёрка, проверяемая сервером.
- Клиентская <color=#7FD4FF>сухая победа</color> означает выигрыш с соперником на 0 раундов. В комнате с укороченной целью по раундам 3-0 тоже считается. <color=#FF6666>Серверные достижения 5-0 требуют соперника на 0 при минимум 5 выигранных раундах.</color>

<color=#FFD94D><b>КЛИЕНТСКИЕ: ТОЧНЫЕ ЗАБЕГИ</b></color>

- <color=#7FD4FF>Неприкасаемый</color> - выиграй игру, в которой твоё здоровье не упало ни разу. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Пацифист</color> - выиграй, ни разу не удержав кнопку огня в живом бою. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Неподвижный объект</color> - выиграй, ни разу не удержав клавишу движения или прыжка в живом бою. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Приземлённый</color> - выиграй, ни разу не удержав клавишу прыжка (Space, W, Up). <color=#7FE87F>100g</color>
- <color=#7FD4FF>Инстинкт</color> - выиграй с 3 и больше пиками карт, беря заранее подсвеченную крайнюю левую карту в каждом пике и ни разу не сдвинув выбор. <color=#8A8A93>Проверяется только в комнатах очереди и синхро-турниров - игры по коду комнаты, включая асинхро-матчи, его пропускают.</color> <color=#7FE87F>100g</color>

<color=#FFD94D><b>КЛИЕНТСКИЕ: СУХИЕ ПОБЕДЫ И ТРЮКИ</b></color>

- <color=#7FD4FF>Бесшумный убийца</color> - сухая победа со Sneaky (или Sneaky Bullets) в билде. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Total Mayhem</color> - сухая победа с Mayhem в билде. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Хрупкое совершенство</color> - сухая победа с Glass Cannon в билде. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Не убежишь</color> - сухая победа с Chase в билде. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Восставший из пепла</color> - сухая победа с Phoenix в билде, без смертей и без единого срабатывания воскрешения Phoenix. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Король камбэков</color> - выиграй после того, как счёт по раундам стоял: у тебя 0, у соперника 4 и больше. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Краплёная колода</color> - закончи игру с 5 и больше копиями одной карты. Победа не требуется. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Божественный билд</color> - выиграй с Shields Up в билде, закончив игру на пушке с 1 патроном или меньше и перезарядкой за 1 секунду или меньше. <color=#7FE87F>100g</color>
- <color=#7FD4FF>С головой в омут</color> - возьми Abyssal Countdown ПЕРВЫМ пиком игры, активируй его в каждом раунде и выиграй. <color=#7FE87F>300g</color>

<color=#FFD94D><b>СЕРВЕРНЫЕ БИЛДЫ 1v1</b></color>

Судятся по отправленному матчу. Ты должен быть победителем игры, если строка не говорит иначе.

- <color=#7FD4FF>Пулевой ад</color> - выиграй 5-0 с Barrage в билде. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Spray and Pray</color> - выиграй 5-0 со Spray. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Подрывник</color> - выиграй 5-0 с Explosive Bullet. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Controlled Burst</color> - выиграй 5-0 с Burst. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Полевой медик</color> - выиграй 5-0 с Healing Field. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Double Nova</color> - выиграй с 2 и больше Supernova. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Дровосек</color> - выиграй с 2 и больше Saw. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Pristine Perfection</color> - выиграй с 2 и больше копиями Pristine Perseverance. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Жизнь на грани</color> - выиграй с 2 и больше Glass Cannon. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Silly Drill</color> - выиграй со Sneaky и Drill вместе. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Неиссякаемая сила</color> - выиграй с Empower и Healing Field вместе. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Коллекционер</color> - выиграй с 4 и больше копиями любой одной карты. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Клатч</color> - выиграй после того, как счёт стоял 0 очков у тебя против 6 и больше у соперника - то есть 0-3 по раундам. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Близнецы!</color> - оба игрока заканчивают ровно с 5 картами и идентичными билдами, включая число копий. Открывают оба; побеждать никому не нужно. <color=#7FE87F>500g</color>$s256$)
  , ('492328683cba65c5', 'sv', 'e01ce49fac28b9d9fd21bfb3e832d94aece20e29', $s256$Modden levererar 50 prestationer. Var och en låses upp exakt en gång per konto och betalar guld på fläcken - <color=#7FE87F>100 guld</color> som standard, upp till <color=#7FE87F>1000</color> för de svåraste; varje rad nedan visar sin utbetalning. Bläddra bland dem under <color=#7FD4FF>Min statistik - Prestationer</color> i F5-menyn: varje rad visar villkoret, ditt upplåsningsdatum, andelen kända moddspelare som har den, och dess guld. Klicka på en rad för att se vilka som förtjänat den (de första 500, i upplåsningsordning).

<color=#FFD94D><b>SÅ KONTROLLERAS DE</b></color>

- Två kontrollanter finns. 14 prestationer döms av ditt eget spel i samma stund en match slutar; övriga 36 döms av servern - de flesta när en match, serie eller ratinguppdatering landar, de tre översättarnivåerna när översättningsarbete godkänns. <color=#8A8A93>Serverdömda upplåsningar kan dyka upp ett ögonblick efter matchen - det är normalt.</color>
- Klientdömda prestationer kräver en riktig onlinematch. Sandbox, offlinespel och åskådande ger aldrig något.
- Varje villkorsspårare är per match och nollställs när en ny match börjar - en rematch är ett rent blad, så skada tagen i match 1 kan inte förstöra Orörbar i match 2. (Sviträknare är, avsiktligt, undantaget: de spänner över matcher.)
- Inputspårarna (Pacifist, Orubbligt föremål, Markbunden) samplar bara dina tangenter medan du är vid liv och strider. Kortval, valfasen och tid som död räknas aldrig mot dig, och inte heller att skriva i moddens chatt eller F5-menyn.
- Klientdömda prestationer körs i 1v1-, 2v2- och 1v2-matcher. De utlöses aldrig från FFA-matcher - FFA har sina egna sex, dömda av servern.
- En klientdömd <color=#7FD4FF>utklassning</color> betyder att du vinner med motståndaren på 0 ronder. I ett rum med kortare rondmål räknas ett 3-0 ändå. <color=#FF6666>De serverdömda 5-0-prestationerna kräver motståndaren på 0 med minst 5 vunna ronder.</color>

<color=#FFD94D><b>KLIENTDÖMDA: PRECISIONSLOPP</b></color>

- <color=#7FD4FF>Orörbar</color> - vinn en match där din hälsa aldrig sjönk, inte en enda gång. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Pacifist</color> - vinn utan att någonsin hålla skjutknappen under aktiv strid. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Orubbligt föremål</color> - vinn utan att någonsin hålla en rörelse- eller hopptangent under aktiv strid. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Markbunden</color> - vinn utan att någonsin hålla en hopptangent (mellanslag, W, upp). <color=#7FE87F>100g</color>
- <color=#7FD4FF>Instinkt</color> - vinn med 3 eller fler kortval, där du tar det förmarkerade kortet längst till vänster i varje val utan att någonsin flytta markeringen. <color=#8A8A93>Kontrolleras bara i kö- och synkturneringsrum - rumskodsmatcher, async-turneringsmatcher inräknade, hoppar över den.</color> <color=#7FE87F>100g</color>

<color=#FFD94D><b>KLIENTDÖMDA: UTKLASSNINGAR OCH KONSTSTYCKEN</b></color>

- <color=#7FD4FF>Tyst lönnmördare</color> - utklassa med Sneaky (eller Sneaky Bullets) i din build. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Total Mayhem</color> - utklassa med Mayhem i din build. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Skör perfektion</color> - utklassa med Glass Cannon i din build. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Ingen utväg</color> - utklassa med Chase i din build. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Upp ur askan</color> - utklassa med Phoenix i din build, utan att dö och utan att en Phoenix-återupplivning någonsin utlöses. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Comeback-kungen</color> - vinn efter att ronderna någon gång stått du 0, motståndaren 4 eller mer. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Riggad kortlek</color> - avsluta en match med 5 eller fler kopior av ett kort. Ingen vinst krävs. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Gudomlig build</color> - vinn med Shields Up i din build, och avsluta matchen med ett vapen på 1 ammo eller mindre som laddar om på 1 sekund eller mindre. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Ut på djupt vatten</color> - ta Abyssal Countdown som ditt FÖRSTA val i matchen, utlös det i varje rond, och vinn. <color=#7FE87F>300g</color>

<color=#FFD94D><b>SERVERDÖMDA 1v1-BUILDS</b></color>

Döms från den rapporterade matchen. Du måste vara matchens vinnare om inte raden säger annat.

- <color=#7FD4FF>Kulhelvete</color> - vinn 5-0 med Barrage i din build. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Spray and Pray</color> - vinn 5-0 med Spray. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Sprängexpert</color> - vinn 5-0 med Explosive Bullet. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Controlled Burst</color> - vinn 5-0 med Burst. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Fältläkare</color> - vinn 5-0 med Healing Field. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Double Nova</color> - vinn med 2 eller fler Supernova. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Skogshuggare</color> - vinn med 2 eller fler Saw. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Pristine Perfection</color> - vinn med 2 eller fler kopior av Pristine Perseverance. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Livet på gränsen</color> - vinn med 2 eller fler Glass Cannon. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Silly Drill</color> - vinn med Sneaky och Drill tillsammans. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Ihållande kraft</color> - vinn med Empower och Healing Field tillsammans. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Samlare</color> - vinn med 4 eller fler kopior av ett och samma kort. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Clutch</color> - vinn efter att ställningen någon gång stått 0 poäng för dig mot 6 eller fler för motståndaren - alltså 0-3 i ronder. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Tvillingar!</color> - båda spelarna avslutar med exakt 5 kort var och identiska builds, kopieantal inräknat. Båda låser upp den; ingen behöver vinna. <color=#7FE87F>500g</color>$s256$)
  , ('492328683cba65c5', 'uk', 'e01ce49fac28b9d9fd21bfb3e832d94aece20e29', $s256$Мод постачає 50 досягнень. Кожне відкривається рівно раз на акаунт і одразу платить золото - <color=#7FE87F>100 золота</color> за замовчуванням, до <color=#7FE87F>1000</color> за найважчі; кожен рядок нижче показує свою виплату. Переглядайте їх у <color=#7FD4FF>Моя статистика - Досягнення</color> в меню F5: кожен рядок показує умову, дату вашого відкриття, відсоток відомих гравців мода, що його мають, і золото. Клацніть рядок, щоб побачити, хто його заробив (перші 500, у порядку відкриття).

<color=#FFD94D><b>ЯК ВОНИ ПЕРЕВІРЯЮТЬСЯ</b></color>

- Перевіряльників два. 14 досягнень судить ваша власна гра в мить кінця гри; решту 36 судить сервер - більшість коли сідає матч, серія чи оновлення рейтингу, а три рівні перекладачів - коли схвалюється перекладацька робота. <color=#8A8A93>Серверні відкриття можуть вискочити на мить пізніше гри - це нормально.</color>
- Клієнтські досягнення потребують справжньої онлайн-гри. Пісочниця, офлайн і глядацтво не дають нічого й ніколи.
- Кожен трекер умови - на одну гру і скидається зі стартом нової: рематч - чистий аркуш, тож шкода, отримана у грі 1, не зіпсує Недоторканного у грі 2. (Лічильники стріків, за задумом, виняток: вони тягнуться через ігри.)
- Трекери вводу (Пацифіст, Непорушний об’єкт, Приземлений) семплюють ваші клавіші лише поки ви живі й б’єтеся. Вибори карт, фаза вибору і час у мертвих не рахуються проти вас, як і друк у чаті мода чи меню F5.
- Клієнтські досягнення працюють в іграх 1v1, 2v2 і 1v2. З ігор FFA вони не спрацьовують ніколи - у FFA власна шістка, яку перевіряє сервер.
- Клієнтська <color=#7FD4FF>суха</color> означає перемогу з суперником на 0 раундів. У кімнаті з коротшою ціллю раундів 3-0 теж рахується. <color=#FF6666>Серверні досягнення за 5-0 вимагають суперника на 0 і щонайменше 5 виграних раундів.</color>

<color=#FFD94D><b>КЛІЄНТСЬКІ: ТОЧНІ ЗАБІГИ</b></color>

- <color=#7FD4FF>Недоторканний</color> - виграйте гру, в якій ваше здоров’я не впало ані разу. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Пацифіст</color> - виграйте, ні разу не затиснувши кнопку вогню в живому бою. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Непорушний об’єкт</color> - виграйте, ні разу не затиснувши клавішу руху чи стрибка в живому бою. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Приземлений</color> - виграйте, ні разу не затиснувши клавішу стрибка (Space, W, вгору). <color=#7FE87F>100g</color>
- <color=#7FD4FF>Інстинкт</color> - виграйте з 3 і більше виборами карт, беручи на кожному виборі підсвічену крайню ліву карту й ні разу не посунувши вибір. <color=#8A8A93>Перевіряється лише в кімнатах черги і синхронних турнірів - ігри за кодом кімнати, включно з async-турнірами, його пропускають.</color> <color=#7FE87F>100g</color>

<color=#FFD94D><b>КЛІЄНТСЬКІ: СУХІ ПЕРЕМОГИ І ТРЮКИ</b></color>

- <color=#7FD4FF>Безшумний убивця</color> - суха зі Sneaky (або Sneaky Bullets) у білді. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Total Mayhem</color> - суха з Mayhem у білді. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Крихка досконалість</color> - суха з Glass Cannon у білді. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Не втечеш</color> - суха з Chase у білді. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Повсталий з попелу</color> - суха з Phoenix у білді, без смертей і без жодного спрацювання оживлення Phoenix. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Король камбеків</color> - виграйте після того, як раунди стояли: у вас 0, у суперника 4 і більше. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Підтасована колода</color> - завершіть гру з 5 і більше копіями однієї карти. Перемога не потрібна. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Божественний білд</color> - виграйте з Shields Up у білді, закінчивши гру на зброї з 1 набоєм чи менше, що перезаряджається за 1 секунду чи швидше. <color=#7FE87F>100g</color>
- <color=#7FD4FF>З головою у вир</color> - візьміть Abyssal Countdown ПЕРШИМ вибором гри, активуйте його в кожному раунді й виграйте. <color=#7FE87F>300g</color>

<color=#FFD94D><b>СЕРВЕРНІ БІЛДИ 1v1</b></color>

Судяться зі звітованого матчу. Ви маєте бути переможцем гри, якщо рядок не каже інакше.

- <color=#7FD4FF>Кульове пекло</color> - виграйте 5-0 з Barrage у білді. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Spray and Pray</color> - виграйте 5-0 зі Spray. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Підривник</color> - виграйте 5-0 з Explosive Bullet. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Controlled Burst</color> - виграйте 5-0 з Burst. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Польовий медик</color> - виграйте 5-0 з Healing Field. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Double Nova</color> - виграйте з 2 і більше Supernova. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Лісоруб</color> - виграйте з 2 і більше Saw. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Досконалість Pristine</color> - виграйте з 2 і більше копіями Pristine Perseverance. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Життя на межі</color> - виграйте з 2 і більше Glass Cannon. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Silly Drill</color> - виграйте зі Sneaky і Drill разом. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Невичерпна сила</color> - виграйте з Empower і Healing Field разом. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Колекціонер</color> - виграйте з 4 і більше копіями будь-якої однієї карти. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Клатч</color> - виграйте після того, як рахунок стояв 0 очок у вас проти 6 і більше в суперника - тобто 0-3 за раундами. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Близнюки!</color> - обидва гравці завершують рівно з 5 картами кожен та ідентичними білдами, разом із кількістю копій. Відкривають обидва; вигравати нікому не треба. <color=#7FE87F>500g</color>$s256$)
  , ('496ab005cd8a3b4f', 'es', 'ed706f2149025b474c9a6e245bf4a9e6908ecbe6', $s256$Técnicas de movimiento verificadas: el rebote de escudo en el borde, los saltos de pared y el rebote en vuelo. Cada regla de esta página sale directamente del código del juego.

<color=#FFD94D><b>EL REBOTE DE ESCUDO EN EL BORDE</b></color>

La arena tiene un límite letal duro justo fuera de pantalla. Mientras lo has cruzado, el juego te comprueba cada 0.1 segundos:

- <color=#FF6666>Sin bloquear:</color> recibes un golpe letal de 51 de daño y un impulso de vuelta hacia la arena. Con 100 HP, dos golpes de borde sin escudo te matan.
- <color=#7FE87F>Bloqueando:</color> ningún daño, y el impulso de vuelta es el doble de fuerte. Tu velocidad anterior se pone a cero primero, así que el rebote es limpio y predecible por rápido que salieras volando.

La ventana de bloqueo dura 0.3 segundos y la comprobación del borde corre cada 0.1 segundos, así que la pulsación puede ir un poco DETRÁS de tu salida y aun así contar. Salir despedido de la pantalla es sobrevivible a voluntad: bloquea al cruzar el borde y vuelves con más fuerza, gratis. En una guerra de knockback esa es la diferencia entre un punto perdido y una contra.

<color=#FFD94D><b>SALTOS DE PARED Y RECARGA DE SALTOS</b></color>

- Tocar una pared en el aire mientras mantienes el movimiento HACIA ella cuenta como agarre de pared. Salvo que hayas saltado en los últimos 0.15 segundos, <color=#7FE87F>tocar pared recarga TODOS tus saltos</color>.
- Pulsar salto en los 0.1 segundos siguientes a tocar pared ejecuta un salto de pared: hacia arriba y lejos de la pared en vez de recto hacia arriba.
- Los saltos desde el suelo añaden empuje horizontal extra proporcional a lo rápido que ya te movías de lado; los saltos de pared se saltan ese bono.
- Mantener salto sigue añadiendo fuerza hacia arriba un instante tras despegar - toque corto para un saltito, mantenido para la altura completa.
- Mientras cuelgas pegado a una pared, tu tiempo en el aire cuenta más despacio para los sistemas del juego que miran el tiempo aéreo.

<color=#FFD94D><b>EL REBOTE EN VUELO</b></color>

Un golpe lo bastante grande para ponerte en estado 'volando' cambia cómo te tratan las paredes: mientras vuelas, chocar con la geometría del mapa refleja tu velocidad contra la superficie, te aturde 0.2 segundos e inflige un autogolpe de 5 de daño. El lanzamiento reflejado sale tras una retención de un cuarto de segundo.

Ese autogolpe es un golpe bloqueable normal: <color=#7FE87F>bloquear en el momento del impacto contra la pared anula los 5 de daño</color>.

<color=#FFD94D><b>MITOS A LOS QUE EL CÓDIGO DICE QUE NO</b></color>

- <color=#8A8A93>El deslizamiento por la pared es real, pero no donde crees: empujar hacia la pared amortigua un poco tu velocidad y reinicia una y otra vez la rampa de gravedad, así que sí caes más despacio - mientras que la stat llamada literalmente 'wall grab drag' no hace nada en absoluto.</color>
- <color=#8A8A93>Las cartas que anuncian un autoempuje al bloquear no hacen nada con una pulsación de bloqueo normal - la propia ventana de bloqueo del juego suprime el empuje antes de que pueda aplicarse. No las elijas por el movimiento.</color>

<color=#FFD94D><b>SHIELD CHARGE ES EL VERDADERO MOVIMIENTO DE BLOQUEO</b></color>

Shield Charge te lanza en la dirección de tu APUNTADO con cualquier pulsación de bloqueo, y el lanzamiento funciona durante tu propia ventana de bloqueo. Golpear a un jugador cancela el lanzamiento, le hace daño y knockback, y otorga un bloqueo extra. Además combina con las reglas de pared de arriba: embiste una pared, recarga tus saltos y sal con un salto de pared.$s256$)
  , ('496ab005cd8a3b4f', 'ru', 'ed706f2149025b474c9a6e245bf4a9e6908ecbe6', $s256$Проверенная техника движения: отскок от края со щитом, прыжки от стен и полётный отскок. Каждое правило на этой странице - прямо из кода игры.

<color=#FFD94D><b>ОТСКОК ОТ КРАЯ СО ЩИТОМ</b></color>

У арены есть жёсткая смертельная граница сразу за экраном. Пока ты за ней, игра проверяет тебя каждые 0.1 секунды:

- <color=#FF6666>Без блока:</color> ты получаешь смертельный удар в 51 урона и импульс назад к арене. На 100 HP два незащищённых удара границы убивают.
- <color=#7FE87F>С блоком:</color> никакого урона, а возвратный импульс вдвое сильнее. Твоя старая скорость сперва обнуляется, так что отскок чистый и предсказуемый, как бы быстро ты ни вылетал.

Окно блока - 0.3 секунды, а проверка края тикает каждые 0.1 секунды, так что нажатие может слегка ОТСТАТЬ от вылета и всё равно засчитаться. Вылет за экран выживаем по требованию: блокируй на пересечении края - и вернёшься сильнее, бесплатно. В войне отбросов это разница между потерянным очком и ответным залпом.

<color=#FFD94D><b>ПРЫЖКИ ОТ СТЕН И ОБНОВЛЕНИЕ ПРЫЖКОВ</b></color>

- Касание стены в воздухе с зажатым движением В неё считается захватом стены. Если ты не прыгал в последние 0.15 секунды, <color=#7FE87F>касание стены обновляет ВСЕ твои прыжки</color>.
- Нажатие прыжка в пределах 0.1 секунды от касания стены даёт прыжок от стены: вверх и от стены, а не строго вверх.
- Прыжки с земли добавляют горизонтальный толчок пропорционально твоей уже набранной боковой скорости; прыжки от стены этот бонус пропускают.
- Удержание прыжка продолжает добавлять подъёмную силу короткий момент после отрыва - тапни для короткого прыжка, держи для полной высоты.
- Пока ты висишь вплотную к стене, твоё время в воздухе для систем, которым оно важно, идёт медленнее.

<color=#FFD94D><b>ПОЛЁТНЫЙ ОТСКОК</b></color>

Удар, достаточно сильный, чтобы отправить тебя в «полёт», меняет отношение стен к тебе: в полёте удар о геометрию карты отражает твою скорость от поверхности, станит на 0.2 секунды и наносит самоудар в 5 урона. Отражённый запуск выходит после задержки в четверть секунды.

Этот самоудар - обычный блокируемый удар: <color=#7FE87F>блок в момент удара о стену гасит эти 5 урона</color>.

<color=#FFD94D><b>МИФЫ, КОТОРЫМ КОД ГОВОРИТ «НЕТ»</b></color>

- <color=#8A8A93>Скольжение по стене существует, но не там, где ты думаешь: зажим в стену слегка гасит скорость и всё время сбрасывает разгон гравитации, так что падаешь ты и правда медленнее - а стат с именем «wall grab drag» не делает вообще ничего.</color>
- <color=#8A8A93>Карты, обещающие самотолчок при блоке, при обычном нажатии блока не делают ничего - собственное окно блока игры давит толчок раньше, чем тот применится. Не бери их ради движения.</color>

<color=#FFD94D><b>SHIELD CHARGE - НАСТОЯЩЕЕ ДВИЖЕНИЕ ОТ БЛОКА</b></color>

Shield Charge запускает тебя по направлению ПРИЦЕЛА при любом нажатии блока, и запуск работает во время твоего собственного окна блока. Попадание по игроку отменяет рывок, наносит ему урон и отброс и даёт бонусный блок. Он же комбинируется с правилами стен выше: рывок в стену, обновлённые прыжки, прыжок от стены наружу.$s256$)
  , ('496ab005cd8a3b4f', 'sv', 'ed706f2149025b474c9a6e245bf4a9e6908ecbe6', $s256$Verifierad rörelseteknik: sköldkantstudsen, vägghopp och flygstudsen. Varje regel på den här sidan kommer direkt från spelets kod.

<color=#FFD94D><b>SKÖLDKANTSTUDSEN</b></color>

Arenan har en hård dödsgräns strax utanför bild. Medan du är bortom den kontrollerar spelet dig var 0.1 sekund:

- <color=#FF6666>Blockerar inte:</color> du tar en dödlig träff på 51 skada och en impuls tillbaka mot arenan. Vid 100 HP dödar två oskyddade kantträffar dig.
- <color=#7FE87F>Blockerar:</color> ingen skada alls, och returimpulsen är dubbelt så stark. Din gamla hastighet nollas först, så studsen är ren och förutsägbar oavsett hur fort du flög ut.

Blockfönstret är 0.3 sekunder och kantkollen tickar var 0.1 sekund, så trycket kan komma något EFTER din sorti och ändå räknas. Att bli utslungad ur bild är överlevbart på begäran: blocka när du korsar kanten så kommer du tillbaka in hårdare, gratis. I ett knockbackkrig är det skillnaden mellan en förlorad poäng och en retursalva.

<color=#FFD94D><b>VÄGGHOPP OCH HOPPFÖRNYELSE</b></color>

- Att röra en vägg i luften medan du håller rörelse IN mot den räknas som ett vägggrepp. Om du inte hoppat de senaste 0.15 sekunderna gäller: <color=#7FE87F>en väggberöring förnyar ALLA dina hopp</color>.
- Att trycka hopp inom 0.1 sekunder från en väggberöring utför ett vägghopp: uppåt och bort från väggen i stället för rakt upp.
- Markhopp lägger till extra horisontell skjuts proportionell mot hur fort du redan rörde dig i sidled; vägghopp hoppar över den bonusen.
- Att hålla hopp fortsätter addera uppåtkraft en kort stund efter avstampet - tryck kort för ett litet skutt, håll för full höjd.
- Medan du hänger nära en vägg räknas din tid i luften långsammare för spelsystem som bryr sig om lufttid.

<color=#FFD94D><b>FLYGSTUDSEN</b></color>

En träff stor nog att sätta dig i 'flygläge' ändrar hur väggar behandlar dig: medan du flyger reflekterar kartgeometri din hastighet mot ytan, stunnar dig i 0.2 sekunder och ger en självträff på 5 skada. Den reflekterade utskjutningen kommer efter en kvartssekunds paus.

Den självträffen är en vanlig blockbar träff: <color=#7FE87F>att blocka i väggträffens ögonblick upphäver de 5 i skada</color>.

<color=#FFD94D><b>MYTER SOM KODEN SÄGER NEJ TILL</b></color>

- <color=#8A8A93>Väggglidning är verklig, men inte där du tror: att trycka in mot en vägg dämpar din fart lite och nollställer gravitationsrampen om och om igen, så du faller faktiskt långsammare - medan värdet som faktiskt heter 'wall grab drag' inte gör någonting alls.</color>
- <color=#8A8A93>Kort som utlovar en självknuff vid block gör ingenting vid ett normalt blocktryck - spelets eget blockfönster undertrycker knuffen innan den hinner verka. Drafta dem inte för rörelse.</color>

<color=#FFD94D><b>SHIELD CHARGE ÄR DEN RIKTIGA BLOCKRÖRELSEN</b></color>

Shield Charge skjuter iväg dig längs din SIKTriktning vid varje blocktryck, och utskjutningen fungerar under ditt eget blockfönster. Att träffa en spelare avbryter rusningen, skadar och knuffar bort dem, och ger ett bonusblock. Den kombinerar också med väggreglerna ovan: rusa in i en vägg, få dina hopp förnyade, vägghoppa ut.$s256$)
  , ('496ab005cd8a3b4f', 'uk', 'ed706f2149025b474c9a6e245bf4a9e6908ecbe6', $s256$Перевірена техніка руху: відбій щитом на краю, стрибки від стін і летючий рикошет. Кожне правило на цій сторінці - прямо з коду гри.

<color=#FFD94D><b>ВІДБІЙ ЩИТОМ НА КРАЮ</b></color>

Одразу за екраном арена має жорстку межу знищення. Поки ви за нею, гра перевіряє вас кожні 0.1 секунди:

- <color=#FF6666>Без блоку:</color> ви отримуєте летальний удар на 51 шкоди та імпульс назад до арени. На 100 HP два незахищені удари краю вбивають.
- <color=#7FE87F>З блоком:</color> жодної шкоди, а зворотний імпульс удвічі сильніший. Ваша стара швидкість спершу обнуляється, тож відбій чистий і передбачуваний, хоч як швидко ви вилітали.

Вікно блоку - 0.3 секунди, а перевірка краю тікає кожні 0.1 секунди, тож натискання може трохи ВІДСТАТИ від вашого вильоту і все одно зарахуватися. Викидання за екран - виживане за бажанням: заблокуйте на перетині краю - і повернетеся сильнішими, безкоштовно. У війні відкидань це різниця між втраченим очком і зустрічним залпом.

<color=#FFD94D><b>СТРИБКИ ВІД СТІН І ПОНОВЛЕННЯ СТРИБКІВ</b></color>

- Торкання стіни в повітрі з утриманням руху В НЕЇ рахується як хват стіни. Якщо ви не стрибали в останні 0.15 секунди, <color=#7FE87F>торкання стіни поновлює ВСІ ваші стрибки</color>.
- Натискання стрибка в межах 0.1 секунди від торкання стіни виконує стрибок від стіни: вгору і геть від стіни замість прямо вгору.
- Стрибки з землі додають горизонтальний поштовх пропорційно вашій уже наявній боковій швидкості; стрибки від стін цього бонусу не мають.
- Утримання стрибка ще коротку мить після відриву додає підйомної сили - тап для короткого стрибка, утримання для повної висоти.
- Поки ви висите близько до стіни, ваш час у повітрі для ігрових систем, яким він важливий, рахується повільніше.

<color=#FFD94D><b>ЛЕТЮЧИЙ РИКОШЕТ</b></color>

Удар, достатньо великий, щоб зробити вас «летючим», змінює ставлення стін: у польоті зіткнення з геометрією мапи відбиває вашу швидкість від поверхні, оглушує на 0.2 секунди і завдає самоудар на 5 шкоди. Відбитий запуск виходить після чвертьсекундної затримки.

Цей самоудар - звичайний блокований удар: <color=#7FE87F>блок у мить удару об стіну скасовує ті 5 шкоди</color>.

<color=#FFD94D><b>МІФИ, ЯКИМ КОД КАЖЕ НІ</b></color>

- <color=#8A8A93>Ковзання по стіні реальне, але не там, де ви думаєте: притискання до стіни трохи гасить швидкість і постійно скидає розгін гравітації, тож ви справді падаєте повільніше - а стат, буквально названий «drag хвата стіни», не робить нічого.</color>
- <color=#8A8A93>Карти, що обіцяють самопоштовх на блоці, на звичайному натисканні не роблять нічого - власне вікно блоку гри гасить поштовх, перш ніж він застосується. Не беріть їх заради руху.</color>

<color=#FFD94D><b>SHIELD CHARGE - СПРАВЖНІЙ РУХ ВІД БЛОКУ</b></color>

Shield Charge запускає вас у напрямку ПРИЦІЛУ на будь-якому натисканні блоку, і запуск працює під час вашого власного вікна блоку. Влучання в гравця скасовує запуск, шкодить йому й відкидає, і дарує бонусний блок. Він також комбінується з правилами стін вище: увірвіться в стіну, поновіть стрибки, вистрибніть від стіни геть.$s256$)
  , ('507db85caf0e602a', 'es', 'cf45d3edae079b8b38a35974796750918fa489e0', $s256$Veneno y daño en el tiempo$s256$)
  , ('507db85caf0e602a', 'ru', 'cf45d3edae079b8b38a35974796750918fa489e0', $s256$Яд и урон со временем$s256$)
  , ('507db85caf0e602a', 'sv', 'cf45d3edae079b8b38a35974796750918fa489e0', $s256$Gift & skada över tid$s256$)
  , ('507db85caf0e602a', 'uk', 'cf45d3edae079b8b38a35974796750918fa489e0', $s256$Отрута та поступова шкода$s256$)
  , ('540aa824d2c28b31', 'es', '149285f05807fe0061d475398bb6fbfd0917916b', $s256$Arreglos de bugs del mod$s256$)
  , ('540aa824d2c28b31', 'ru', '149285f05807fe0061d475398bb6fbfd0917916b', $s256$Исправления багов в моде$s256$)
  , ('540aa824d2c28b31', 'sv', '149285f05807fe0061d475398bb6fbfd0917916b', $s256$Buggfixar i modden$s256$)
  , ('540aa824d2c28b31', 'uk', '149285f05807fe0061d475398bb6fbfd0917916b', $s256$Виправлення багів у моді$s256$)
  , ('5893137c242888d0', 'es', '24ecf950cbf20b50adeae5290099ca654fb8fc93', $s256$Abrir la biblioteca de información$s256$)
  , ('5893137c242888d0', 'ru', '24ecf950cbf20b50adeae5290099ca654fb8fc93', $s256$Открыть библиотеку знаний$s256$)
  , ('5893137c242888d0', 'sv', '24ecf950cbf20b50adeae5290099ca654fb8fc93', $s256$Öppna infobiblioteket$s256$)
  , ('5893137c242888d0', 'uk', '24ecf950cbf20b50adeae5290099ca654fb8fc93', $s256$Відкрити бібліотеку Інфо$s256$)
  , ('5d139a2aa3e9277f', 'es', '0c6b6d4f70cfb4212b1bf230c43ac7f9db37a841', $s256$Modo espectador$s256$)
  , ('5d139a2aa3e9277f', 'ru', '0c6b6d4f70cfb4212b1bf230c43ac7f9db37a841', $s256$Наблюдение$s256$)
  , ('5d139a2aa3e9277f', 'sv', '0c6b6d4f70cfb4212b1bf230c43ac7f9db37a841', $s256$Åskådarläge$s256$)
  , ('5d139a2aa3e9277f', 'uk', '0c6b6d4f70cfb4212b1bf230c43ac7f9db37a841', $s256$Режим глядача$s256$)
  , ('5dd73a36dbbf1de3', 'es', '0dfd2c2a42475a101ace09e8af90e5a56cf53e0c', $s256$Qué hace cada arreglo de bugs de vanilla y dónde se aplica. Las reglas de activación están en <color=#7FD4FF>Vanilla sigue siendo vanilla</color>: las protecciones contra crashes corren en todas partes, los cambios de gameplay solo donde todos llevan el mod y han consentido.

<color=#FFD94D><b>SIEMPRE ACTIVOS - PROTECCIONES DE CRASH Y ESTADO</b></color>

Corren en todas las partidas, quickplay incluido. Ninguno cambia una regla: cada uno sustituye un crash o un estado roto por lo que el juego pretendía.

<color=#7FD4FF>Inputs congelados, Escape muerto</color> - el conmutador de input de vanilla crashea con un jugador a medio aparecer, congelando tus teclas al encontrar partida o matando Escape para siempre. El mod salta al jugador a medio conectar y sigue.

<color=#7FD4FF>No puedes ponerte listo</color> - vanilla puede intentar generarte antes de que la conexión haya entrado a una sala y dejarte sin anillo de listo. El mod retiene la aparición hasta que la sala es real; pasados 30 segundos te devuelve al menú.

<color=#7FD4FF>Bloqueos muertos, Shield Charge silencioso, Empower invisible</color> - entre juegos, vanilla puede desmontar las cartas en el orden equivocado y dejar manejadores muertos en tu bloqueo y tu arma: un bloqueo que no hace nada, un Shield Charge que no vuelve a activarse, un Empower invisible de daño doble. El mod los purga antes de cada bloqueo y al empezar cada juego y cada revancha.

<color=#7FD4FF>Crash de la reanimación de Phoenix</color> - tras irse alguien del FFA, el Phoenix de vanilla busca a su objetivo de reanimación por posición en la lista, crashea y lo deja invisible e intocable en todas las pantallas, para siempre. La reanimación ahora se resuelve por ID de jugador.

<color=#7FD4FF>Desincronización de vida en una pantalla</color> - un crash del motor de sonido durante el robo de vida podía abortar el golpe entrante ENTERO en tu cliente, y ROUNDS nunca resincroniza la vida - las dos pantallas quedaban en desacuerdo sobre tu HP para siempre. El fallo de sonido se traga para que el daño aterrice igual.

<color=#7FD4FF>Reparaciones de imagen y audio</color> - alguien que se va y vacía un equipo ya no congela a todos en la pantalla de victoria; una búsqueda fallida de nombre de Steam se reintenta (15 intentos en medio minuto) en vez de llamarte 'PlayerName' toda la sala; el texto de la carta Chase pierde su línea de Vida (vanilla nunca aplica esa stat - la carta en sí no cambia); las voces de sonido filtradas ya no amortiguan la sesión; los sonidos en bucle (sierras de mapa, la carga de Abyssal Countdown) se detienen al acabar su ronda; más caducar un visual de radar que se filtraba, acallar errores de la corona y silenciar crashes que eran puro ruido de log.

<color=#FFD94D><b>CUALQUIER PARTIDA - REPARACIONES LOCALES</b></color>

Estos corren también en cualquier sala online. Cada uno repara la contabilidad de tu pantalla hacia lo que el dueño de la bala ya decidió - sin cambios de reglas, sin desacuerdos nuevos.

<color=#7FD4FF>Spray pierde el autodisparo</color> - un Demonic Pact envenena todos los juegos posteriores de la sala: vanilla copia su marca de no-autodisparo al arma y nunca la limpia, volviendo Spray un-clic-por-disparo. Se limpia entre juegos.

<color=#7FD4FF>Balas de Drill invisibles</color> - una bala de Drill a bocajarro podía volverse invisible en la otra pantalla (su efecto se registraba antes de que la bala terminara de inicializarse). El mod la coloca en su posición real y vuelve a registrar las piezas que faltan.

<color=#7FD4FF>Veneno que impacta pero no hace nada</color> - la misma carrera afectaba al veneno: la bala impacta a la vista en tu pantalla pero no llega daño, porque el veneno nunca se registró en la copia remota. Se vuelve a registrar, con una deduplicación para que nunca pueda registrarse dos veces y hacer daño doble.

<color=#7FD4FF>Muertes fantasma al final de ronda</color> - los ticks de veneno y quemadura durante la animación de ronda ganada podían matar en plena transición y regalar una ronda fantasma. Los clientes con mod ignoran el daño en el tiempo y las muertes durante la ventana de transición; la protección completa de la sala necesita también el asiento anfitrión (normalmente con mod).

<color=#7FD4FF>Balas sobrantes tras el punto</color> - vanilla nunca limpia las balas en el aire en el límite del punto, así que una bala de veneno de final de ronda podía golpearte DESPUÉS de reaparecer. Cada cliente despawnea ahora sus propias balas en el límite, con la propia llamada de despawn de vanilla.$s256$)
  , ('5dd73a36dbbf1de3', 'ru', '0dfd2c2a42475a101ace09e8af90e5a56cf53e0c', $s256$Что делает каждый фикс ванильных багов и где он применяется. Правила шлюзов - в <color=#7FD4FF>Ваниль остаётся ванилью</color>: защита от крашей работает везде, изменения геймплея - только там, где все на моде и согласны.

<color=#FFD94D><b>ВСЕГДА ВКЛЮЧЕНО - ЗАЩИТА ОТ КРАШЕЙ И СОСТОЯНИЙ</b></color>

Это работает в каждой игре, включая quickplay. Ничто из этого не меняет правил: каждый пункт заменяет краш или сломанное состояние тем, что игра задумывала.

<color=#7FD4FF>Замёрзший ввод, мёртвый Escape</color> - ванильное переключение ввода падает на наполовину заспавненном игроке, замораживая клавиши на найденном матче или навсегда убивая Escape. Мод пропускает недособранного игрока и идёт дальше.

<color=#7FD4FF>Не получается нажать готовность</color> - ваниль может попытаться заспавнить тебя до того, как соединение вошло в комнату, и оставить без кольца готовности. Мод держит спавн, пока комната не станет настоящей; через 30 секунд возвращает в меню.

<color=#7FD4FF>Мёртвые блоки, молчащий Shield Charge, невидимый Empower</color> - между играми ваниль может снести карты в неправильном порядке и оставить мёртвые обработчики на блоке и пушке: блок, который не делает ничего, Shield Charge, который больше никогда не срабатывает, невидимый Empower с двойным уроном. Мод вычищает их перед каждым блоком и на старте каждой игры и рематча.

<color=#7FD4FF>Краш воскрешения Phoenix</color> - после ушедшего в FFA ванильный Phoenix ищет цель воскрешения по позиции в списке, падает и оставляет её невидимой и неуязвимой на каждом экране, навсегда. Теперь воскрешение разрешается по ID игрока.

<color=#7FD4FF>Рассинхрон здоровья одного экрана</color> - краш звукового движка во время вампиризма мог оборвать на твоём клиенте ВЕСЬ входящий удар, а ROUNDS никогда не пересинхронизирует здоровье - экраны навсегда расходились о твоём HP. Звуковой сбой проглатывается, и урон всё равно ложится.

<color=#7FD4FF>Ремонт отображения и звука</color> - ушедший, опустошивший команду, больше не замораживает всех на экране победы; неудачный запрос имени Steam повторяется (15 попыток за полминуты) вместо того, чтобы звать тебя «PlayerName» всю комнату; текст карты Chase теряет строку про здоровье (ваниль этот стат никогда не применяет - сама карта не тронута); утёкшие звуковые голоса больше не глушат сессию; зацикленные звуки (пилы карт, заряд Abyssal Countdown) останавливаются с концом своего раунда; плюс истечение утекающего радарного визуала, приглушение ошибок короны и заглушение крашей, которые были чистым шумом в логе.

<color=#FFD94D><b>ЛЮБАЯ ИГРА - ЛОКАЛЬНЫЙ РЕМОНТ</b></color>

Это тоже работает в каждой онлайн-комнате. Каждый пункт чинит бухгалтерию твоего экрана к тому, что владелец пули уже решил, - без смены правил и без новых расхождений.

<color=#7FD4FF>Spray теряет автоогонь</color> - один Demonic Pact отравляет каждую позднюю игру комнаты: ваниль копирует его флаг запрета автоогня на пушку и никогда не чистит, делая Spray «клик за выстрел». Чистится между играми.

<color=#7FD4FF>Невидимые пули Drill</color> - пуля Drill в упор могла стать невидимой на другом экране (её эффект регистрировался до конца инициализации пули). Мод примагничивает её к истинной позиции и дорегистрирует недостающие куски.

<color=#7FD4FF>Яд, который попадает и ничего не делает</color> - та же гонка била по яду: пуля видимо попадает на твоём экране, но урона нет, потому что яд не зарегистрировался на удалённой копии. Дорегистрируется, с дедупликацией, чтобы никогда не зарегистрироваться дважды на двойной урон.

<color=#7FD4FF>Фантомные убийства на конце раунда</color> - тики яда и горения во время анимации выигранного раунда могли убить посреди перехода и начислить фантомный раунд. Модовые клиенты игнорируют урон со временем и смерти в окне перехода; полная защита всей комнаты требует лишь, чтобы (обычно модовое) место хоста комнаты тоже было пропатчено.

<color=#7FD4FF>Оставшиеся пули после очка</color> - ваниль никогда не чистит пули в воздухе на границе очка, так что ядовитая пуля конца раунда могла ударить тебя ПОСЛЕ респавна. Теперь каждый клиент убирает свои пули на границе - через собственный ванильный вызов деспавна.$s256$)
  , ('5dd73a36dbbf1de3', 'sv', '0dfd2c2a42475a101ace09e8af90e5a56cf53e0c', $s256$Vad varje vanilla-buggfix gör och var den gäller. Grindreglerna finns i <color=#7FD4FF>Vanilla förblir vanilla</color>: kraschskydd körs överallt, gameplay-ändringar bara där alla är moddade och överens.

<color=#FFD94D><b>ALLTID PÅ - KRASCH- OCH TILLSTÅNDSSKYDD</b></color>

De här körs i varje match, quickplay inräknat. Ingen ändrar en regel: var och en ersätter en krasch eller ett trasigt tillstånd med vad spelet avsåg.

<color=#7FD4FF>Frusna inputs, död Escape</color> - vanillas inputväxling kraschar på en halvspawnad spelare och fryser dina tangenter vid matchhittad eller dödar Escape permanent. Modden hoppar över den halvkopplade spelaren och fortsätter.

<color=#7FD4FF>Kan inte bli redo</color> - vanilla kan försöka spawna dig innan anslutningen gått med i ett rum och lämna dig utan redo-ring. Modden håller spawnen tills rummet är verkligt; efter 30 sekunder skickas du tillbaka till menyn.

<color=#7FD4FF>Döda block, tyst Shield Charge, osynlig Empower</color> - mellan matcher kan vanilla montera ner kort i fel ordning och lämna döda hanterare på ditt block och vapen: ett block som ingenting gör, en Shield Charge som aldrig utlöses igen, en osynlig Empower med dubbel skada. Modden skrubbar bort dem före varje block och vid varje match- och rematchstart.

<color=#7FD4FF>Phoenix-återupplivningskraschen</color> - efter en FFA-avhoppare slår vanillas Phoenix upp sitt återupplivningsmål via listposition, kraschar, och lämnar spelaren osynlig och oträffbar på varje skärm, för alltid. Återupplivningen löses nu via spelar-ID.

<color=#7FD4FF>Hälsodesync på en skärm</color> - en ljudmotorkrasch under lifesteal kunde avbryta din klients HELA inkommande träff, och ROUNDS omsynkar aldrig hälsa - de två skärmarna var sedan oense om din HP för alltid. Ljudfelet sväljs så att skadan ändå landar.

<color=#7FD4FF>Visnings- och ljudreparationer</color> - en avhoppare som tömmer ett lag fryser inte längre alla på segerskärmen; en misslyckad Steam-namnuppslagning görs om (15 försök över en halv minut) i stället för att du heter 'PlayerName' hela rummet; Chases korttext tappar sin hälsorad (vanilla tillämpar aldrig det värdet - själva kortet är oförändrat); läckta ljudröster gör inte längre sessionen dov; loopande ljud (kartsågar, Abyssal Countdowns laddning) stannar när deras rond slutar; plus en läckande radarvisual som får löpa ut, tystade kronfel och nedtystade rena loggbruskrascher.

<color=#FFD94D><b>VILKEN MATCH SOM HELST - LOKALA REPARATIONER</b></color>

De här körs också i varje onlinerum. Var och en reparerar din skärms bokföring mot vad kulans ägare redan beslutat - inga regeländringar, inga nya oenigheter.

<color=#7FD4FF>Spray tappar autoeld</color> - en Demonic Pact förgiftar varje senare match i rummet: vanilla kopierar sin ingen-autoeld-flagga till vapnet och nollställer den aldrig, vilket gör Spray klick-per-skott. Rensas mellan matcher.

<color=#7FD4FF>Osynliga Drill-kulor</color> - en Drill-kula på nära håll kunde bli osynlig på den andra skärmen (dess effekt registrerades innan kulan initierats klart). Modden knäpper den till dess sanna position och omregistrerar de saknade delarna.

<color=#7FD4FF>Gift som landar men ingenting gör</color> - samma kapplöpning drabbade gift: kulan träffar synligt på din skärm men ingen skada följer, eftersom giftet aldrig registrerades på fjärrkopian. Omregistrerat, med en dedupe så att det aldrig kan registreras dubbelt för dubbel skada.

<color=#7FD4FF>Fantomkills vid rondslut</color> - gift- och brännticks under vunnen-rond-animationen kunde döda mitt i övergången och dela ut en fantomrond. Moddade klienter ignorerar skada över tid och dödsfall under övergångsfönstret; fullt rumsbrett skydd kräver också rummets (oftast moddade) värdplats.

<color=#7FD4FF>Kvarblivna kulor efter poängen</color> - vanilla rensar aldrig kulor i luften vid en poänggräns, så en giftkula från rondslutet kunde träffa dig EFTER respawn. Varje klient despawnar nu sina egna kulor vid gränsen, via vanillas eget despawn-anrop.$s256$)
  , ('5dd73a36dbbf1de3', 'uk', '0dfd2c2a42475a101ace09e8af90e5a56cf53e0c', $s256$Що робить кожне виправлення ванільного бага і де воно діє. Правила воріт - у <color=#7FD4FF>Ваніль лишається ваніллю</color>: захист від крашів працює скрізь, зміни геймплею - лише там, де всі з модом і згодні.

<color=#FFD94D><b>ЗАВЖДИ ВВІМКНЕНО - ЗАХИСТ ВІД КРАШІВ І СТАНІВ</b></color>

Це працює в кожній грі, включно зі швидкими матчами. Ніщо з цього не змінює правило: кожне замінює краш чи зламаний стан тим, що гра задумувала.

<color=#7FD4FF>Замерзлий ввід, мертвий Escape</color> - ванільний перемикач вводу падає на напівзаспавненому гравці, заморожуючи ваші клавіші на знайденому матчі або назавжди вбиваючи Escape. Мод пропускає недопід’єднаного гравця і йде далі.

<color=#7FD4FF>Не можна приготуватися</color> - ваніль може спробувати заспавнити вас до того, як з’єднання ввійшло в кімнату, і лишити без кільця готовності. Мод тримає спавн, поки кімната не стане справжньою; через 30 секунд повертає вас у меню.

<color=#7FD4FF>Мертві блоки, німий Shield Charge, невидимий Empower</color> - між іграми ваніль може розбирати карти в неправильному порядку й лишати мертві обробники на вашому блоці та зброї: блок, що не робить нічого, Shield Charge, що більше не спрацює, невидимий Empower подвійної шкоди. Мод вичищає їх перед кожним блоком і на старті кожної гри та рематчу.

<color=#7FD4FF>Краш оживлення Phoenix</color> - після виходу гравця з FFA ванільний Phoenix шукає ціль оживлення за позицією у списку, падає і лишає її невидимою і невразливою на кожному екрані, назавжди. Оживлення тепер розв’язується за ID гравця.

<color=#7FD4FF>Десинх здоров’я одного екрана</color> - краш звукового рушія під час лайфстілу міг обірвати ЦІЛЕ вхідне влучання на вашому клієнті, а ROUNDS ніколи не пересинхронізує здоров’я - два екрани далі назавжди розходилися щодо вашого HP. Звукова помилка тепер ковтається, і шкода все одно сідає.

<color=#7FD4FF>Ремонти показу і звуку</color> - той, хто виходом спустошив команду, більше не заморожує всіх на екрані перемоги; невдалий запит імені Steam повторюється (15 спроб за пів хвилини) замість «PlayerName» на всю кімнату; текст карти Chase втрачає рядок здоров’я (ваніль той стат ніколи не застосовує - сама карта незмінна); витеклі звукові голоси більше не глушать сесію; зациклені звуки (пилки мап, заряд Abyssal Countdown) зупиняються з кінцем свого раунду; плюс гасіння витікаючого візуалу радара, приглушення помилок корони і тиша для крашів, що були чистим шумом у лозі.

<color=#FFD94D><b>БУДЬ-ЯКА ГРА - ЛОКАЛЬНІ РЕМОНТИ</b></color>

Це теж працює в кожній онлайн-кімнаті. Кожен ремонт підтягує бухгалтерію вашого екрана до того, що власник кулі вже вирішив, - без змін правил і без нових розбіжностей.

<color=#7FD4FF>Spray втрачає автовогонь</color> - один Demonic Pact труїть кожну наступну гру в кімнаті: ваніль копіює його прапорець без-автовогню на зброю і ніколи не чистить, перетворюючи Spray на клік-за-постріл. Чиститься між іграми.

<color=#7FD4FF>Невидимі кулі Drill</color> - куля Drill впритул могла стати невидимою на іншому екрані (її ефект реєструвався до завершення ініціалізації кулі). Мод пристібає її до справжньої позиції й дореєстровує відсутні частини.

<color=#7FD4FF>Отрута, що влучає, але не робить нічого</color> - та сама гонка била й по отруті: куля видимо влучає на вашому екрані, але шкоди немає, бо отрута не зареєструвалася на віддаленій копії. Дореєстровується, з дедуплікацією, щоб ніколи не зареєструватися двічі на подвійну шкоду.

<color=#7FD4FF>Фантомні вбивства на кінці раунду</color> - тіки отрути й горіння під час анімації виграного раунду могли вбити посеред переходу й подарувати фантомний раунд. Клієнти з модом ігнорують поступову шкоду і смерті у вікні переходу; повний захист на всю кімнату потребує ще пропатченого (зазвичай модового) місця хоста кімнати.

<color=#7FD4FF>Залишкові кулі після очка</color> - ваніль ніколи не чистить кулі в повітрі на межі очка, тож отруйна куля з кінця раунду могла влучити у вас ПІСЛЯ респавну. Тепер кожен клієнт деспавнить власні кулі на межі, тим самим викликом деспавну, що й ваніль.$s256$)
  , ('5e7990ce511a1502', 'es', '722b8253ed5d9130b7ce842a66865d6780fa4b64', $s256$Vanilla sigue siendo vanilla$s256$)
  , ('5e7990ce511a1502', 'ru', '722b8253ed5d9130b7ce842a66865d6780fa4b64', $s256$Ваниль остаётся ванилью$s256$)
  , ('5e7990ce511a1502', 'sv', '722b8253ed5d9130b7ce842a66865d6780fa4b64', $s256$Vanilla förblir vanilla$s256$)
  , ('5e7990ce511a1502', 'uk', '722b8253ed5d9130b7ce842a66865d6780fa4b64', $s256$Ваніль лишається ваніллю$s256$)
  , ('5e99bccde500db1a', 'es', '9c58c47f379b8af787fea4b478aac44660dcf37a', $s256$Dos equipos de dos juegan una serie al mejor de 3.

<color=#FFD94D><b>CÓMO SE JUEGA</b></color>

- La cola aleatoria usa una banda de Elo que se amplía
  mientras esperas. El servidor equilibra los equipos.
- Las salas custom no tienen banda de Elo.
  Entrar a la sala es consentir jugar.
- Los 4 jugadores tienen 120 segundos para ponerse listos.
  Si el tiempo acaba, los de cola automática vuelven a
  buscar; una sala custom simplemente se libera.
- Diseñado pero aún no activo: tras un juego de cola
  automática con margen de 3 o más puntos, el ganador
  más débil cambiará de sitio con el perdedor más
  fuerte. Hasta entonces, los equipos quedan fijos toda la serie.

<color=#FFD94D><b>PUNTUACIÓN</b></color>

- El primer equipo en ganar 2 juegos gana la serie.
- El 2v2 usa su propio rating Glicko.
  No cambia tu rating de 1v1.
- El rating se actualiza al completar la serie.
- W-L y WR cuentan series completadas, no juegos sueltos.

<color=#FFD94D><b>RECOMPENSAS</b></color>

- Cada juego da 600 XP base.
  Ganar el juego da x1.5, es decir 900 XP base.
- Ganar la serie da 50 de Oro base.
  Perderla da 25 de Oro base.
- El tier de rating del equipo rival puede multiplicar las recompensas base.
- La XP de juego se convierte en Oro a 100 XP = 1 Oro.

<color=#FFD94D><b>COLUMNAS DE LA CLASIFICACIÓN</b></color>

<color=#7FD4FF>Rank</color> - Posición en el orden seleccionado.
<color=#7FD4FF>Player</color> - Nombre visible del jugador.
<color=#7FD4FF>Rating</color> - Rating Glicko de 2v2, separado.
<color=#7FD4FF>W-L</color> - Series completadas ganadas y perdidas.
<color=#7FD4FF>WR</color> - Series ganadas entre series completadas.
<color=#7FD4FF>Avg Mate Elo</color> - Rating medio de tus compañeros.
  Un compañero usa su rating 2v2 tras 5 series completadas.
  Antes, se usa su rating 1v1, o 1500 si no hay.
<color=#7FD4FF>Gold</color> - Oro total ganado solo en 2v2.
<color=#7FD4FF>XP</color> - XP total ganada solo en 2v2.
  El Oro y la XP no afectan a tu puesto por rating.

<color=#FFD94D><b>OJO</b></color>

- Salir a mitad de juego queda registrado.$s256$)
  , ('5e99bccde500db1a', 'ru', '9c58c47f379b8af787fea4b478aac44660dcf37a', $s256$Две команды по два играют серию до 2 побед (BO3).

<color=#FFD94D><b>КАК ИГРАТЬ</b></color>

- Общая очередь использует диапазон Elo, который
  расширяется по мере ожидания.
  Сервер сам балансирует команды.
- В своих лобби диапазона Elo нет.
  Вход в лобби - согласие играть.
- У всех 4 игроков есть 120 секунд на готовность.
  Если время вышло, игроки авто-очереди возвращаются
  в поиск, а своё лобби просто распускается.
- Задумано, но пока не в игре: после игры из
  авто-очереди с разницей очков 3 и больше слабейший
  из победителей поменяется местами с сильнейшим из
  проигравших. Пока это не вышло, команды закреплены
  на всю серию.

<color=#FFD94D><b>СЧЁТ</b></color>

- Серию берёт команда, первой выигравшая 2 игры.
- У 2v2 свой рейтинг Glicko.
  Он не меняет твой рейтинг 1v1.
- Рейтинг обновляется после завершённой серии.
- W-L и WR считают завершённые серии, а не
  отдельные игры.

<color=#FFD94D><b>НАГРАДЫ</b></color>

- Каждая игра даёт 600 базового XP.
  Победа в игре даёт x1.5, то есть 900 базового XP.
- Победа в серии даёт 50 базового золота.
  Поражение в серии даёт 25 базового золота.
- Тир рейтинга соперников может умножить награды.
- XP за игры меняется на золото: 100 XP = 1 золото.

<color=#FFD94D><b>СТОЛБЦЫ ТАБЛИЦЫ</b></color>

<color=#7FD4FF>Rank</color> - Позиция в выбранной сортировке.
<color=#7FD4FF>Player</color> - Отображаемое имя игрока.
<color=#7FD4FF>Rating</color> - Отдельный рейтинг Glicko для 2v2.
<color=#7FD4FF>W-L</color> - Завершённые серии: победы и поражения.
<color=#7FD4FF>WR</color> - Победы в сериях, делённые на завершённые.
<color=#7FD4FF>Avg Mate Elo</color> - Средний рейтинг прошлых тиммейтов.
  После 5 завершённых серий у тиммейта берётся его
  рейтинг 2v2. До этого - его рейтинг 1v1, а если
  его нет - 1500.
<color=#7FD4FF>Gold</color> - Золото, заработанное только в 2v2.
<color=#7FD4FF>XP</color> - XP, заработанный только в 2v2.
  Золото и XP не влияют на место по рейтингу.

<color=#FFD94D><b>НЮАНСЫ</b></color>

- Выход посреди игры записывается.$s256$)
  , ('5e99bccde500db1a', 'sv', '9c58c47f379b8af787fea4b478aac44660dcf37a', $s256$Två lag om två spelar en serie i bäst av 3.

<color=#FFD94D><b>SÅ SPELAR DU</b></color>

- Slumpkön använder ett Elo-spann som vidgas medan du väntar.
  Servern balanserar lagen automatiskt.
- Anpassade lobbyer har inget Elo-spann.
  Att gå med i lobbyn är samtycke till att spela.
- Alla 4 spelare har 120 sekunder på sig att bli redo.
  Om tiden går ut återgår autokö-spelare till
  sökning; en anpassad lobby släpps helt enkelt.
- Designat men inte aktivt ännu: efter en autokö-match
  med en poängmarginal på 3 eller mer ska den svagaste
  vinnaren byta plats med den starkaste förloraren.
  Tills det lanseras är lagen låsta hela serien.

<color=#FFD94D><b>POÄNG</b></color>

- Första laget som vinner 2 matcher vinner serien.
- 2v2 använder en egen Glicko-rating.
  Den ändrar inte din 1v1-rating.
- Ratingen uppdateras efter avslutad serie.
- W-L och WR räknar avslutade serier, inte enskilda matcher.

<color=#FFD94D><b>BELÖNINGAR</b></color>

- Varje match ger 600 bas-XP.
  En matchvinst ger x1.5, alltså 900 bas-XP.
- En serievinst ger 50 basguld.
  En serieförlust ger 25 basguld.
- Motståndarlagets ratingtier kan multiplicera basbelöningarna.
- Match-XP omvandlas till guld: 100 XP = 1 guld.

<color=#FFD94D><b>TOPPLISTANS KOLUMNER</b></color>

<color=#7FD4FF>Rang</color> - Plats i den valda sorteringen.
<color=#7FD4FF>Spelare</color> - Spelarens visningsnamn.
<color=#7FD4FF>Rating</color> - Spelarens separata Glicko-rating för 2v2.
<color=#7FD4FF>W-L</color> - Avslutade serier, vunna och förlorade.
<color=#7FD4FF>WR</color> - Serievinster delat med avslutade serier.
<color=#7FD4FF>Snitt-Elo lagkamrater</color> - Snittrating för tidigare lagkamrater.
  En lagkamrat räknas med sin 2v2-rating efter 5 avslutade serier.
  Innan dess används 1v1-ratingen, eller 1500 om den saknas.
<color=#7FD4FF>Guld</color> - Guld tjänat enbart i 2v2, totalt.
<color=#7FD4FF>XP</color> - XP tjänat enbart i 2v2, totalt.
  Guld och XP påverkar inte din ratingbaserade placering.

<color=#FFD94D><b>ATT TÄNKA PÅ</b></color>

- Att lämna mitt i en match registreras.$s256$)
  , ('5e99bccde500db1a', 'uk', '9c58c47f379b8af787fea4b478aac44660dcf37a', $s256$Дві команди по двоє грають серію BO3 (до 2 перемог).

<color=#FFD94D><b>ЯК ГРАТИ</b></color>

- Випадкова черга використовує діапазон Elo, що розширюється з очікуванням.
  Сервер автоматично балансує команди.
- У користувацьких лобі діапазону Elo немає.
  Вхід у лобі означає згоду грати.
- Усі 4 гравці мають 120 секунд, щоб підтвердити готовність.
  Якщо час спливе, гравці авточерги повертаються до
  пошуку; користувацьке лобі просто відпускається.
- Задумано, але ще не працює: після гри з авточерги
  з різницею у 3 очки або більше найслабший переможець
  мінятиметься місцями з найсильнішим із переможених. Поки
  це не вийшло, команди зафіксовані всю серію.

<color=#FFD94D><b>РАХУНОК</b></color>

- Серію виграє команда, що першою виграє 2 гри.
- У 2v2 власний рейтинг Glicko.
  Він не змінює ваш рейтинг 1v1.
- Рейтинг оновлюється після завершеної серії.
- W-L і WR рахують завершені серії, а не окремі ігри.

<color=#FFD94D><b>НАГОРОДИ</b></color>

- Кожна гра дає 600 базового XP.
  Перемога в грі дає x1.5, тобто 900 базового XP.
- Перемога в серії дає 50 базового золота.
  Поразка в серії дає 25 базового золота.
- Рейтинговий рівень команди суперників може помножити базові нагороди.
- XP за ігри конвертується в золото: 100 XP = 1 золото.

<color=#FFD94D><b>СТОВПЦІ ТАБЛИЦІ ЛІДЕРІВ</b></color>

<color=#7FD4FF>Ранг</color> - Позиція у вибраному сортуванні.
<color=#7FD4FF>Гравець</color> - Ігрове ім’я гравця.
<color=#7FD4FF>Рейтинг</color> - Окремий рейтинг Glicko для 2v2.
<color=#7FD4FF>W-L</color> - Виграні й програні завершені серії.
<color=#7FD4FF>WR</color> - Перемоги в серіях, поділені на завершені серії.
<color=#7FD4FF>Сер. Elo союзників</color> - Середній рейтинг минулих союзників.
  Союзник використовує рейтинг 2v2 після 5 завершених серій.
  До того береться його рейтинг 1v1, а без нього - 1500.
<color=#7FD4FF>Золото</color> - Усього золота, заробленого лише у 2v2.
<color=#7FD4FF>XP</color> - Усього XP, заробленого лише у 2v2.
  Золото та XP не впливають на місце за рейтингом.

<color=#FFD94D><b>НЮАНСИ</b></color>

- Вихід посеред гри записується.$s256$)
  , ('5ebd9e4ca23d91dc', 'es', '0d48973d722572c1f7817750bcfdc1c93a212f35', $s256$Rating y recompensas$s256$)
  , ('5ebd9e4ca23d91dc', 'ru', '0d48973d722572c1f7817750bcfdc1c93a212f35', $s256$Рейтинги и награды$s256$)
  , ('5ebd9e4ca23d91dc', 'sv', '0d48973d722572c1f7817750bcfdc1c93a212f35', $s256$Rating & belöningar$s256$)
  , ('5ebd9e4ca23d91dc', 'uk', '0d48973d722572c1f7817750bcfdc1c93a212f35', $s256$Рейтинги та нагороди$s256$)
  , ('60a0927f3dfe3ebd', 'es', '79f5b225cffab11e22dc40b6f05abef1d33d1561', $s256$Modos$s256$)
  , ('60a0927f3dfe3ebd', 'ru', '79f5b225cffab11e22dc40b6f05abef1d33d1561', $s256$Режимы$s256$)
  , ('60a0927f3dfe3ebd', 'sv', '79f5b225cffab11e22dc40b6f05abef1d33d1561', $s256$Spellägen$s256$)
  , ('60a0927f3dfe3ebd', 'uk', '79f5b225cffab11e22dc40b6f05abef1d33d1561', $s256$Режими$s256$)
  , ('614580a23bb3bc8f', 'es', '41a4fddf3fcf4db5dd068dc9cf886d86b18d4384', $s256$Grow es la única carta cuyo daño depende de la TASA DE FOTOGRAMAS del tirador. En vanilla, la misma bala de Grow disparada por un jugador a 60 FPS golpea mucho más fuerte que una disparada a 400 FPS - y el mod la normaliza en juego competitivo.

<color=#FFD94D><b>LA MATEMÁTICA REAL</b></color>

Grow multiplica un poco el daño de la bala en cada fotograma dibujado mientras vuela, durante aproximadamente las primeras 30 unidades de recorrido. Componer un multiplicador por fotograma tiene una consecuencia extraña: la velocidad de la bala se cancela del total, y lo que de verdad fija el multiplicador final es la duración de los fotogramas del tirador. Menos fotogramas, más largos, componen más fuerte.

Sin acumular, en un vuelo completo:

- tirador a 400 FPS: alrededor de <color=#7FD4FF>x1.07</color>
- tirador a 60 FPS: alrededor de <color=#7FD4FF>x1.53</color>
- tirador a 30 FPS: alrededor de <color=#7FD4FF>x2.31</color>

Acumular copias multiplica la tasa de crecimiento, así que la brecha explota. Con cuatro copias: alrededor de x1.29 a 400 FPS, <color=#FF6666>x5.47 a 60 FPS y x28.5 a 30 FPS</color>.

Los tirones son el peor caso: <color=#FF6666>un solo fotograma congelado de 200 ms multiplica la bala por cerca de x2.16 él solo</color>. Un tirón a mitad de vuelo puede convertir un disparo normal en uno letal.

<color=#FFD94D><b>POR QUÉ SUS FPS SE VUELVEN TU PROBLEMA</b></color>

El daño en ROUNDS tiene autoridad del tirador: la máquina del tirador calcula lo que recibe la víctima, y todos los demás aplican ese número (ver <color=#7FD4FF>Netcode y Photon</color>). El crecimiento de Grow ocurre en los fotogramas del tirador, así que las balas de Grow de un rival con FPS bajos o con tirones golpean de verdad más fuerte. No es lag, no es tu imaginación, y en vanilla tampoco es trampa - es la matemática de la carta.

<color=#FFD94D><b>LA NORMALIZACIÓN DEL MOD</b></color>

En salas elegibles, el mod fija el reloj de crecimiento de Grow: <color=#7FE87F>cada bala de Grow crece como si su tirador corriera a 240 FPS, en todas las máquinas</color>. Frente a una base de FPS altísimos eso significa cerca de +11 por ciento en un vuelo completo sin acumular, +23 por ciento con dos copias, +53 con cuatro - lo mismo para todos, en cada partida. La tasa de referencia está compilada dentro del mod a propósito: si fuera un ajuste, cambiarlo cambiaría tu propio daño.

Dónde se aplica:

- Cada combatiente de la sala debe llevar una build actual del mod (los espectadores no cuentan). <color=#FF6666>Un combatiente vanilla o desactualizado significa crecimiento vanilla para toda la sala</color>, igual en cada pantalla - una sala mixta nunca queda medio normalizada.
- Las salas de cola del mod (ranked 1v1, 2v2, 1v2, FFA, salas de torneo) normalizan siempre que todos estén al día.
- Las partidas privadas por código y de quickplay normalizan solo cuando, además, cada combatiente tenía el Ranked ACTIVADO al conectarse.
- La decisión se fija por bala al dispararse y nunca cambia en pleno vuelo. Nunca está activa offline.

Un residuo honesto: con tasas de fotogramas muy bajas una bala normalizada puede crecer ligeramente MENOS que el objetivo (unos pocos puntos acumulando; más con un tirón fuerte). El error siempre apunta hacia abajo - nunca hacia el disparo letal.$s256$)
  , ('614580a23bb3bc8f', 'ru', '41a4fddf3fcf4db5dd068dc9cf886d86b18d4384', $s256$Grow - единственная карта, чей урон зависит от ЧАСТОТЫ КАДРОВ стрелка. В ванили одна и та же пуля Grow от игрока на 60 FPS бьёт куда сильнее, чем от игрока на 400 FPS, - и мод нормализует это в соревновательной игре.

<color=#FFD94D><b>НАСТОЯЩАЯ МАТЕМАТИКА</b></color>

Grow понемногу умножает урон пули каждый отрисованный кадр её полёта, примерно на первых 30 юнитах пути. У накопления покадрового множителя странное следствие: скорость пули сокращается из итога, и финальный множитель на самом деле задаёт длина кадров стрелка. Кадров меньше и они длиннее - накопление сильнее.

Без стаков, за полный полёт:

- стрелок на 400 FPS: около <color=#7FD4FF>x1.07</color>
- стрелок на 60 FPS: около <color=#7FD4FF>x1.53</color>
- стрелок на 30 FPS: около <color=#7FD4FF>x2.31</color>

Стаки умножают скорость роста, и разрыв взрывается. На четырёх стаках: около x1.29 при 400 FPS, <color=#FF6666>x5.47 при 60 FPS и x28.5 при 30 FPS</color>.

Худший случай - фризы: <color=#FF6666>один замёрзший кадр в 200 мс сам по себе умножает пулю примерно на x2.16</color>. Один статтер посреди полёта может превратить обычный выстрел в ваншот.

<color=#FFD94D><b>ПОЧЕМУ ИХ FPS - ТВОЯ ПРОБЛЕМА</b></color>

Урон в ROUNDS авторитетен для стрелка: машина стрелка вычисляет, что получит жертва, и все остальные применяют это число (см. <color=#7FD4FF>Неткод и Photon</color>). Рост Grow происходит на кадрах стрелка, так что пули Grow соперника с низким FPS или статтерами реально бьют сильнее. Это не лаг, не твоё воображение, и в ванили это даже не чит - это математика карты.

<color=#FFD94D><b>МОДОВАЯ НОРМАЛИЗАЦИЯ</b></color>

В подходящих комнатах мод фиксирует часы роста Grow: <color=#7FE87F>каждая пуля Grow растёт так, будто её стрелок бежит на 240 FPS, на каждой машине</color>. Против самого высокого FPS это около +11 процентов за полный полёт без стаков, +23 на двух стаках, +53 на четырёх - одинаково для всех, каждую игру. Опорная частота вкомпилирована в мод сознательно: будь она настройкой, её изменение меняло бы твой собственный урон.

Где это применяется:

- Каждый боец комнаты должен быть на актуальной сборке мода (зрители не считаются). <color=#FF6666>Один ванильный или устаревший боец - ванильный рост для всей комнаты</color>, одинаковый на каждом экране: смешанное лобби никогда не бывает полунормализованным.
- Комнаты модовых очередей (рейтинговые 1v1, 2v2, 1v2, FFA, турнирные комнаты) нормализуют всякий раз, когда все актуальны.
- Приватные игры по коду комнаты и quickplay нормализуются, только когда вдобавок у каждого бойца был включён Ranked на момент подключения.
- Решение фиксируется на пулю при выстреле и никогда не переворачивается в полёте. Оффлайн оно не активно никогда.

Один честный остаток: на очень низких частотах кадров нормализованная пуля может вырасти чуть МЕНЬШЕ цели (пара процентов со стаками; больше при тяжёлом фризе). Ошибка всегда смотрит вниз - никогда в сторону ваншота.$s256$)
  , ('614580a23bb3bc8f', 'sv', '41a4fddf3fcf4db5dd068dc9cf886d86b18d4384', $s256$Grow är det enda kortet vars skada beror på skyttens BILDFREKVENS. I vanilla slår samma Grow-kula avfyrad av en 60 FPS-spelare mycket hårdare än en avfyrad vid 400 FPS - och modden normaliserar det i tävlingsspel.

<color=#FFD94D><b>DEN RIKTIGA MATTEN</b></color>

Grow multiplicerar kulans skada lite varje renderad bildruta medan den flyger, genom ungefär de första 30 enheterna av färden. Att ackumulera en multiplikator per bildruta har en märklig konsekvens: kulans hastighet tar ut sig själv ur totalen, och det som faktiskt sätter slutmultiplikatorn är längden på skyttens bildrutor. Färre, längre bildrutor ackumulerar hårdare.

Ostaplad, över en full flygning:

- Skytt på 400 FPS: cirka <color=#7FD4FF>x1.07</color>
- Skytt på 60 FPS: cirka <color=#7FD4FF>x1.53</color>
- Skytt på 30 FPS: cirka <color=#7FD4FF>x2.31</color>

Stapling multiplicerar tillväxttakten, så gapet exploderar. Vid fyra staplar: cirka x1.29 vid 400 FPS, <color=#FF6666>x5.47 vid 60 FPS och x28.5 vid 30 FPS</color>.

Hack är värsta fallet: <color=#FF6666>en enda frusen bildruta på 200 ms multiplicerar kulan med cirka x2.16 helt själv</color>. Ett hack mitt i flykten kan göra ett normalt skott till en one-shot.

<color=#FFD94D><b>VARFÖR DERAS FPS BLIR DITT PROBLEM</b></color>

Skada i ROUNDS är skytteauktoritativ: skyttens maskin beräknar vad offret tar, och alla andra tillämpar den siffran (se <color=#7FD4FF>Nätkod & Photon</color>). Grows tillväxt sker på skyttens bildrutor, så Grow-kulor från en motståndare med låg FPS eller hack slår genuint hårdare. Det är inte lagg, det är inte din inbillning, och i vanilla är det inte fusk heller - det är kortets matte.

<color=#FFD94D><b>MODDENS NORMALISERING</b></color>

I berättigade rum låser modden Grows tillväxtklocka: <color=#7FE87F>varje Grow-kula växer som om dess skytt körde 240 FPS, på varje maskin</color>. Mot en baslinje med mycket hög FPS betyder det cirka +11 procent över en full flygning ostaplad, +23 procent vid två staplar, +53 vid fyra - samma för alla, varje match. Referensfrekvensen är avsiktligt inkompilerad i modden: vore den en inställning skulle en ändring ändra din egen skada.

Var det gäller:

- Varje fighter i rummet måste köra en aktuell moddversion (åskådare räknas inte). <color=#FF6666>En enda vanilla- eller föråldrad fighter betyder vanilla-tillväxt för hela rummet</color>, likadant på varje skärm - en blandad lobby är aldrig halvnormaliserad.
- Moddens kö-rum (ranked 1v1, 2v2, 1v2, FFA, turneringsrum) normaliserar närhelst alla är aktuella.
- Privata rumskods- och quickplaymatcher normaliserar bara när, utöver det, varje fighter hade Ranked-inställningen PÅ när de anslöt.
- Beslutet låses per kula vid avfyrningen och vänder aldrig mitt i flykten. Det är aldrig aktivt offline.

En ärlig rest: vid mycket låga bildfrekvenser kan en normaliserad kula växa något MINDRE än målet (några procent staplad; mer vid ett tungt hack). Felet pekar alltid nedåt - aldrig mot one-shotten.$s256$)
  , ('614580a23bb3bc8f', 'uk', '41a4fddf3fcf4db5dd068dc9cf886d86b18d4384', $s256$Grow - єдина карта, чия шкода залежить від ЧАСТОТИ КАДРІВ стрільця. У ванілі та сама куля Grow, пущена гравцем на 60 FPS, б’є значно сильніше за пущену на 400 FPS - і мод нормалізує це у змагальній грі.

<color=#FFD94D><b>СПРАВЖНЯ МАТЕМАТИКА</b></color>

Grow потроху множить шкоду кулі кожен відрендерений кадр польоту, приблизно на перших 30 одиницях шляху. Складання покадрового множника має дивний наслідок: швидкість кулі скорочується із суми, і фінальний множник насправді задає довжина кадрів стрільця. Менше і довших кадрів - сильніше складання.

Без стаків, за повний політ:

- стрілець на 400 FPS: близько <color=#7FD4FF>x1.07</color>
- стрілець на 60 FPS: близько <color=#7FD4FF>x1.53</color>
- стрілець на 30 FPS: близько <color=#7FD4FF>x2.31</color>

Стакання множить темп росту, тож розрив вибухає. На чотирьох стаках: близько x1.29 на 400 FPS, <color=#FF6666>x5.47 на 60 FPS і x28.5 на 30 FPS</color>.

Найгірший випадок - фризи: <color=#FF6666>один замерзлий кадр на 200 мс сам по собі множить кулю приблизно на x2.16</color>. Один затик посеред польоту може перетворити звичайний постріл на ваншот.

<color=#FFD94D><b>ЧОМУ ЇХНІЙ FPS СТАЄ ВАШОЮ ПРОБЛЕМОЮ</b></color>

Шкода в ROUNDS авторитетна для стрільця: машина стрільця обчислює, скільки отримує жертва, і всі решта застосовують це число (див. <color=#7FD4FF>Неткод і Photon</color>). Ріст Grow відбувається на кадрах стрільця, тож кулі Grow суперника з низьким FPS чи фризами справді б’ють сильніше. Це не лаг, не ваша уява, і у ванілі це навіть не чит - це математика карти.

<color=#FFD94D><b>НОРМАЛІЗАЦІЯ МОДА</b></color>

У придатних кімнатах мод пришпилює годинник росту Grow: <color=#7FE87F>кожна куля Grow росте так, ніби її стрілець грає на 240 FPS, на кожній машині</color>. Проти базлайну з дуже високим FPS це близько +11 відсотків за повний політ без стаків, +23 на двох стаках, +53 на чотирьох - однаково для всіх, кожної гри. Еталонна частота навмисно вшита в мод: якби це було налаштування, його зміна змінювала б вашу власну шкоду.

Де це діє:

- Кожен боєць у кімнаті мусить мати актуальну збірку мода (глядачі не рахуються). <color=#FF6666>Один ванільний чи застарілий боєць означає ванільний ріст для всієї кімнати</color>, однаковий на кожному екрані - змішане лобі ніколи не буває напівнормалізованим.
- Модові кімнати черги (рейтингові 1v1, 2v2, 1v2, FFA, турнірні кімнати) нормалізують щоразу, коли всі актуальні.
- Ігри за приватним кодом кімнати і швидкі матчі нормалізуються лише коли, поверх того, кожен боєць мав перемикач Ranked УВІМКНЕНИМ на момент підключення.
- Рішення фіксується для кожної кулі при пострілі й ніколи не перевертається в польоті. Офлайн воно не активне ніколи.

Один чесний залишок: на дуже низьких частотах кадрів нормалізована куля може вирости трохи МЕНШЕ за ціль (кілька відсотків зі стаками; більше на важкому фризі). Похибка завжди дивиться вниз - ніколи в бік ваншота.$s256$)
  , ('624efda8fd0ebd84', 'es', 'a2a07fe57be14e9898f98cbb8ed17e6b00fe1370', $s256$<color=#FFD94D><b>CÓMO ATERRIZA REALMENTE UNA ELECCIÓN</b></color>

- Confirmar una carta no aplica nada - ni siquiera en tu propia pantalla. Cada elector publica su elección, el maestro de la sala las reúne y publica una única lista aceptada, y cada cliente aplica exactamente esa lista en el mismo orden. Por eso las 3-10 pantallas siempre coinciden en quién recibió qué.
- Los números: 45 segundos base, más 20 extra cada vez que una elección aterriza cerca del final, con tope en 90.
- El 0 en pantalla es exactamente el momento de autoconfirmación - el cliente confirma un poco antes, para que una conexión lenta no pueda comerse tu elección.
- <color=#FF6666>Dos casos raros siguen sin dar carta:</color> una elección publicada en el último instante puede no llegar al corte (recibes un aviso diciéndolo), y un asiento crasheado se finaliza sin ella.

<color=#FFD94D><b>QUÉ HACE DE VERDAD SUSTITUIR UNA CARTA</b></color>

- ROUNDS no tiene forma de restar las stats de una carta. Cuando tu carta más antigua sale, el mod reinicia tu personaje por completo y vuelve a aplicar en silencio tus cartas supervivientes en su orden original. Un aviso en cada pantalla nombra lo que perdiste.

<color=#FFD94D><b>ESCALADO DE MAPA</b></color>

- Con 5 o más jugadores el mapa crece un 6 por ciento por jugador por encima de 4, con tope en x1.40: cinco jugadores juegan a x1.06, diez a x1.36. Las partidas de 3-4 jugadores no se escalan.
- La cámara, el límite letal y las posiciones de aparición escalan con él.
- Los mapas vanilla traen solo cuatro puntos de aparición, así que en mapas escalados el mod escanea el mapa recién cargado buscando suelo estático sólido y da a los jugadores 5-10 sus propias apariciones en vez de coordenadas compartidas.

<color=#FFD94D><b>DIEZ JUGADORES, CUATRO COLORES</b></color>

- ROUNDS trae exactamente cuatro colores de cuerpo, así que los colores se repiten cada 4 jugadores. Las etiquetas de nombre distinguen a los duplicados, y los cosméticos de color de cuerpo equipados se siguen viendo.
- Para ayudarte a encontrarte, la pantalla se oscurece alrededor de tu propio jugador durante el primer segundo tras cada aparición - el mismo segundo en el que nadie puede disparar ni bloquear (<color=#7FD4FF>gracia de aparición</color>).

<color=#FFD94D><b>KO DOBLE</b></color>

- Si los últimos jugadores vivos se matan entre sí en un mismo cruce, nadie anota y la ronda simplemente termina - anunciado en cada pantalla.
- El ganador se decide al final del fotograma, así que una muerte mutua no puede regalar la ronda a quien murió una fracción de segundo después.

<color=#FFD94D><b>QUIENES SE VAN, CON PRECISIÓN</b></color>

- Los puntos, medios puntos y kills de quien se va se congelan en el momento de irse y siguen contando para la posición en cada reporte posterior de la sentada.
- Si quien se fue era uno de los dos últimos en pie, el superviviente se lleva el medio punto.
- <color=#7FE87F>Gracia por salida temprana:</color> sal de una partida antes de que el campo anote 2 medios puntos, con tu propio marcador (puntos, medios puntos, kills) aún a cero, y esa partida no te puntúa - sin cambio de rating, sin paga. Cualquier salida posterior o con marcador cuenta entera: irse pronto no esquiva la derrota.
- Los jugadores que se fueron en una partida ANTERIOR viajan como fantasmas ausentes - en la lista, excluidos de rating y paga.
- Una partida que baja de 3 jugadores antes de anotarse 2 medios puntos se cancela; bajar de 3 tras un fin de partida termina la sentada.$s256$)
  , ('624efda8fd0ebd84', 'ru', 'a2a07fe57be14e9898f98cbb8ed17e6b00fe1370', $s256$<color=#FFD94D><b>КАК НА САМОМ ДЕЛЕ ЛОЖИТСЯ ПИК</b></color>

- Подтверждение карты не применяет ничего - даже на твоём экране. Каждый пикер публикует свой выбор, мастер комнаты собирает их и публикует один принятый список, и каждый клиент применяет ровно этот список в одном и том же порядке. Поэтому все 3-10 экранов всегда согласны, кому что досталось.
- Числа: 45 секунд базы, плюс 20 каждый раз, когда чей-то пик ложится под конец, с потолком 90.
- Ноль на экране - это ровно момент автоподтверждения: клиент подтверждает чуть заранее, чтобы медленное соединение не съело твой пик.
- <color=#FF6666>Два редких случая всё же оставляют без карты:</color> пик, опубликованный в последнее мгновение, может не успеть к отсечке (придёт уведомление об этом), а упавшее место финализируется без карты.

<color=#FFD94D><b>ЧТО НА САМОМ ДЕЛЕ ДЕЛАЕТ ЗАМЕНА КАРТЫ</b></color>

- ROUNDS не умеет вычитать статы одной карты. Когда твоя старейшая карта выкатывается, мод полностью сбрасывает персонажа и молча переигрывает выжившие карты в их исходном порядке. Уведомление на каждом экране называет, что ты потерял.

<color=#FFD94D><b>МАСШТАБИРОВАНИЕ КАРТ</b></color>

- С 5 и больше игроками карта растёт на 6 процентов за каждого игрока сверх 4, с потолком x1.40: пятеро играют на x1.06, десятеро на x1.36. Игры на 3-4 не масштабируются.
- Камера, смертельная граница и позиции спавна масштабируются вместе с ней.
- Ванильные карты несут лишь четыре точки спавна, так что на масштабированных картах мод сканирует свежезагруженную карту на твёрдую статичную землю и даёт игрокам 5-10 собственные спавны вместо общих координат.

<color=#FFD94D><b>ДЕСЯТЬ ИГРОКОВ, ЧЕТЫРЕ ЦВЕТА</b></color>

- ROUNDS несёт ровно четыре цвета тела, так что цвета повторяются каждые 4 игрока. Неймтеги различают дубли, а надетые косметические цвета тела всё равно видны.
- Чтобы ты нашёл себя, экран затемняется вокруг твоего игрока первую секунду после каждого спавна - ту же секунду, в которую никто не может стрелять и блокировать (<color=#7FD4FF>защита при спавне</color>).

<color=#FFD94D><b>ДВОЙНОЕ КО</b></color>

- Если последние живые убивают друг друга одним разменом, очка не получает никто и раунд просто заканчивается - с объявлением на каждом экране.
- Победитель решается в самом конце кадра, так что взаимное убийство не может отдать раунд тому, кто умер на долю секунды позже.

<color=#FFD94D><b>УШЕДШИЕ, ТОЧНО</b></color>

- Очки, пол-очки и убийства ушедшего замораживаются в момент ухода и по-прежнему считаются в расстановке мест в каждом позднем отчёте сессии.
- Если ушедший был одним из последних двух стоящих, выживший берёт пол-очка.
- <color=#7FE87F>Льгота раннего ухода:</color> уйди из игры до того, как в ней набрано 2 пол-очка, пока твой собственный счёт (очки, пол-очки, убийства) ещё нулевой, - и та игра для тебя не рейтингуется: без изменения рейтинга, без оплаты. Любой более поздний уход или уход со счётом считается полностью: ранний выход не уворачивается от поражения.
- Игроки, ушедшие в БОЛЕЕ РАННЕЙ игре, едут дальше отсутствующими призраками - в ростере, но вне рейтинга и оплаты.
- Игра, упавшая ниже 3 игроков до 2 набранных пол-очков, отменяется; падение ниже 3 после конца игры завершает сессию.$s256$)
  , ('624efda8fd0ebd84', 'sv', 'a2a07fe57be14e9898f98cbb8ed17e6b00fe1370', $s256$<color=#FFD94D><b>HUR ETT KORTVAL FAKTISKT LANDAR</b></color>

- Att bekräfta ett kort tillämpar ingenting - inte ens på din egen skärm. Varje väljare publicerar sitt val, rumsmastern samlar in dem och publicerar en accepterad lista, och varje klient tillämpar exakt den listan i samma ordning. Det är därför alla 3-10 skärmar alltid är överens om vem som fick vad.
- Siffrorna: 45 sekunder bas, plus 20 till varje gång ett val landar nära slutet, med tak vid 90.
- Nollan på skärmen är exakt ögonblicket för autobekräftelse - klienten bekräftar aningen tidigt, så en långsam anslutning kan inte äta upp ditt val.
- <color=#FF6666>Två sällsynta fall ger ändå inget kort:</color> ett val som publiceras i absolut sista stund kan missa brytpunkten (du får en avisering som säger det), och en kraschad plats slutförs utan kort.

<color=#FFD94D><b>VAD ETT KORTBYTE EGENTLIGEN GÖR</b></color>

- ROUNDS kan inte dra ifrån ett enskilt korts stats. När ditt äldsta kort rullar ut återställer modden din karaktär helt och spelar i tysthet upp dina kvarvarande kort igen i ursprunglig ordning. En avisering på varje skärm anger vad du förlorade.

<color=#FFD94D><b>KARTSKALNING</b></color>

- Med 5 eller fler spelare växer kartan 6 procent per spelare över 4, med tak vid x1.40: fem spelare spelar på x1.06, tio på x1.36. Matcher med 3-4 spelare skalas inte.
- Kameran, dödsgränsen och spawnpositionerna skalas med.
- Vanilla-kartor har bara fyra spawnpunkter, så på skalade kartor skannar modden den nyladdade kartan efter fast statisk mark och ger spelare 5-10 egna spawnpunkter i stället för delade koordinater.

<color=#FFD94D><b>TIO SPELARE, FYRA FÄRGER</b></color>

- ROUNDS har exakt fyra kroppsfärger, så färgerna upprepas var 4:e spelare. Namnskyltarna håller isär dubbletter, och utrustade kroppsfärgskosmetiker syns fortfarande.
- För att du ska hitta dig själv tonas skärmen ner runt din egen spelare den första sekunden efter varje spawn - samma sekund som ingen kan skjuta eller blockera (<color=#7FD4FF>spawnfrist</color>).

<color=#FFD94D><b>DUBBEL-KO</b></color>

- Om de sista spelarna vid liv dödar varandra i samma utväxling får ingen poängen och ronden tar bara slut - det meddelas på varje skärm.
- Vinnaren avgörs allra sist i bildrutan, så en ömsesidig kill kan inte ge ronden till den som råkade dö en tiondel senare.

<color=#FFD94D><b>DE SOM LÄMNAR, I DETALJ</b></color>

- Poäng, halvpoäng och kills fryses i det ögonblick någon lämnar och räknas fortfarande för placering i varje senare rapport under sittningen.
- Om den som lämnade var en av de två sista stående tar överlevaren halvpoänget.
- <color=#7FE87F>Frist vid tidigt avhopp:</color> lämna en match innan fältet gjort 2 halvpoäng, medan din egen räkning (poäng, halvpoäng, kills) fortfarande är noll, så rankas den matchen inte för dig - ingen ratingändring, ingen betalning. Varje senare avhopp, eller med poäng på tavlan, räknas fullt ut: att lämna tidigt duckar inte förlusten.
- Spelare som lämnade i en TIDIGARE match följer med som frånvarande i senare rapporter - kvar på listan, men utanför rating och betalning.$s256$)
  , ('624efda8fd0ebd84', 'uk', 'a2a07fe57be14e9898f98cbb8ed17e6b00fe1370', $s256$<color=#FFD94D><b>ЯК НАСПРАВДІ СІДАЄ ВИБІР</b></color>

- Підтвердження карти не застосовує нічого - навіть на вашому екрані. Кожен, хто обирає, публікує свій вибір, майстер кімнати збирає їх і публікує один прийнятий список, і кожен клієнт застосовує рівно цей список у тому самому порядку. Тому всі 3-10 екранів завжди згодні, хто що отримав.
- Числа: 45 секунд бази, плюс 20 щоразу, коли чийсь вибір сідає під кінець, зі стелею 90.
- Нуль на екрані - це рівно момент автопідтвердження: клієнт підтверджує трохи заздалегідь, тож повільне з’єднання не з’їсть ваш вибір.
- <color=#FF6666>Два рідкісні випадки все ж лишають без карти:</color> вибір, опублікований в останню мить, може не встигнути до відсічки (ви отримаєте сповіщення про це), а місце, що впало, фіналізується без карти.

<color=#FFD94D><b>ЩО НАСПРАВДІ РОБИТЬ ЗАМІНА КАРТИ</b></color>

- ROUNDS не вміє відняти стати однієї карти. Коли ваша найстаріша карта викочується, мод повністю скидає персонажа і мовчки перепрограє вцілілі карти в первісному порядку. Сповіщення на кожному екрані називає, що ви втратили.

<color=#FFD94D><b>МАСШТАБУВАННЯ МАПИ</b></color>

- З 5 і більше гравцями мапа росте на 6 відсотків за кожного гравця понад 4, зі стелею x1.40: п’ятеро грають на x1.06, десятеро на x1.36. Ігри на 3-4 гравці немасштабовані.
- Камера, межа знищення і позиції спавну масштабуються разом із нею.
- Ванільні мапи мають лише чотири точки появи, тож на масштабованих мапах мод сканує щойно завантажену мапу на тверду статичну землю і дає гравцям 5-10 власні спавни замість спільних координат.

<color=#FFD94D><b>ДЕСЯТЬ ГРАВЦІВ, ЧОТИРИ КОЛЬОРИ</b></color>

- ROUNDS постачає рівно чотири кольори тіла, тож кольори повторюються кожні 4 гравці. Неймтеги розрізняють дублікати, а вдягнена косметика кольору тіла показується.
- Щоб ви знайшли себе, першу секунду після кожного спавну екран затемнюється навколо вашого гравця - у ту саму секунду, коли ніхто не може стріляти чи блокувати (<color=#7FD4FF>пауза після появи</color>).

<color=#FFD94D><b>ПОДВІЙНИЙ КО</b></color>

- Якщо останні живі гравці вбивають одне одного в одному обміні, очка не отримує ніхто і раунд просто завершується - з оголошенням на кожному екрані.
- Переможець визначається в самому кінці кадру, тож взаємне вбивство не віддасть раунд тому, хто помер на частку секунди пізніше.

<color=#FFD94D><b>ВИХОДИ, ТОЧНО</b></color>

- Очки, половинки очок і вбивства того, хто вийшов, заморожуються в мить виходу і далі рахуються для розстановки в кожному пізнішому звіті сесії.
- Якщо той, хто вийшов, був одним із двох останніх на ногах, вцілілий бере половинку очка.
- <color=#7FE87F>Пільга раннього виходу:</color> вийдіть із гри до того, як поле набрало 2 половинки очок, поки ваш власний підсумок (очки, половинки, вбивства) ще нульовий, - і та гра для вас не рейтингується: ні зміни рейтингу, ні виплати. Будь-який пізніший вихід чи вихід із балами рахується повністю: ранній вихід від поразки не рятує.
- Гравці, що вийшли в РАНІШІЙ грі, їдуть далі відсутніми привидами - у ростері, але поза рейтингом і виплатами.
- Гра, що падає нижче 3 гравців до 2 набраних половинок очок, скасовується; падіння нижче 3 після кінця гри завершує сесію.$s256$)
  , ('66de64e1b1a3b21c', 'es', 'd785c0d4b3b9c24878b62f64a7bcf78e9506ab27', $s256$Bloqueo$s256$)
  , ('66de64e1b1a3b21c', 'ru', 'd785c0d4b3b9c24878b62f64a7bcf78e9506ab27', $s256$Блокирование$s256$)
  , ('66de64e1b1a3b21c', 'sv', 'd785c0d4b3b9c24878b62f64a7bcf78e9506ab27', $s256$Blockering$s256$)
  , ('66de64e1b1a3b21c', 'uk', 'd785c0d4b3b9c24878b62f64a7bcf78e9506ab27', $s256$Блокування$s256$)
  , ('6aac6cbbebced3a5', 'es', '4dcbd19d1118a776e37c240a8993203892053054', $s256$<color=#FFD94D><b>QUIÉN RECIBE EL ASIENTO DE SOLO</b></color>

- Puedes encolarte con un lado preferido. El cierre toma a los tres encolados vivos que más llevan esperando; el asiento de solo va al que entró antes pidiendo solo, o al que entró antes sin más si nadie lo pidió. Los otros dos son el dúo.
- La región de Photon de la sala es la primera región que alguien de la cola reportó de verdad, en orden de cola, con US como reserva.

<color=#FFD94D><b>LADOS DE APARICIÓN</b></color>

- Cada mapa vanilla trae exactamente cuatro puntos de aparición, dos por mitad. En 1v2 el solo toma el punto exterior izquierdo y el dúo recibe toda la mitad derecha - un jugador del dúo nunca aparece en el lado del solo.

<color=#FFD94D><b>LA ELECCIÓN EXTRA DEL SOLO, CON PRECISIÓN</b></color>

- En la cola aleatoria, basta con que un jugador se encole con ella activada para encenderla en la serie; en una sala alojada decide el ajuste del anfitrión.
- El robo extra se aplica solo a la elección INICIAL: el solo elige dos cartas antes de la ronda 1, y luego una por elección, como todos.

<color=#FFD94D><b>MULTIPLICADORES DE PAGA</b></color>

Los números base de XP y oro de arriba se multiplican por un multiplicador de dificultad:

- El asiento de solo siempre gana x1.5.
- Un solo que juega SIN la elección extra gana un x1.2 adicional; un dúo que enfrenta a un solo con elección extra gana x1.1.
- El tier de rating 1v1 de tus rivales también multiplica (hasta x3.0), y enfrentar a un jugador del podio de 1v2 añade x1.35, ganes o pierdas.
- El producto de dificultad tiene tope en x4.0, con el bono de victoria x1.5 aplicado encima. El oro de serie se escala solo por el tier del rival.

<color=#FFD94D><b>DESCONEXIONES</b></color>

- Mientras el 1v2 sea una beta sin rating no tiene circuito de DC: los resultados salen solo de partidas registradas, y no existe contador de salidas para 1v2.
- Irse estando emparejado con cero partidas jugadas disuelve el emparejamiento - la serie se cancela, los supervivientes de la cola vuelven a buscar y los de una sala alojada simplemente quedan libres.
- Una salida a mitad de partida deja el resultado al reporte normal de la partida.
- Si una sala emparejada nunca se llena: aviso a los 35 segundos, y vuelta automática al menú a los 90. <color=#7FE87F>Sin penalización.</color>$s256$)
  , ('6aac6cbbebced3a5', 'ru', '4dcbd19d1118a776e37c240a8993203892053054', $s256$<color=#FFD94D><b>КТО ПОЛУЧАЕТ МЕСТО СОЛО</b></color>

- Можно встать в очередь с предпочтением стороны. Фиксация берёт трёх самых давних живых очередников; место соло уходит самому раннему, кто просил соло, или просто самому раннему, если не просил никто. Двое других - дуо.
- Регион Photon комнаты - первый регион, который кто-то в очереди реально сообщил, в порядке очереди, с US как запасным.

<color=#FFD94D><b>СТОРОНЫ СПАВНА</b></color>

- Каждая ванильная карта несёт ровно четыре точки спавна, по две на половину. В 1v2 соло берёт внешнюю левую точку, а дуо достаётся вся правая половина - игрок дуо никогда не спавнится на стороне соло.

<color=#FFD94D><b>ДОП. ПИК СОЛО, ТОЧНО</b></color>

- В общей очереди опцию включает для серии любой очередник с включённой настройкой; в хостовом лобби решает настройка хоста.
- Дополнительная раздача касается только СТАРТОВОГО пика: соло берёт две карты перед раундом 1, а дальше по одной за пик, как все.

<color=#FFD94D><b>МНОЖИТЕЛИ ОПЛАТЫ</b></color>

Базовые XP и золото выше умножаются на множитель сложности:

- Место соло всегда получает x1.5.
- Соло, играющий БЕЗ доп. пика, получает ещё x1.2; дуо против соло с доп. пиком получает x1.1.
- Тир рейтинга 1v1 соперников тоже умножает (до x3.0), а встреча с игроком подиума 1v2 добавляет x1.35, при победе и при поражении.
- Произведение сложности ограничено x4.0, и бонус x1.5 за победу идёт поверх потолка. Золото серии масштабируется только тиром соперников.

<color=#FFD94D><b>ОТКЛЮЧЕНИЯ</b></color>

- Пока 1v2 - нерейтинговая бета, у неё нет конвейера DC: исходы берутся только из записанных игр, и счётчика выходов для 1v2 не существует.
- Уход из зафиксированного матча с нулём сыгранных игр распускает его - серия отменяется, выжившие из очереди возвращаются в поиск, а выжившие хостового лобби просто освобождаются.
- Уход посреди игры оставляет исход обычному отчёту матча.
- Если зафиксированная комната так и не заполнилась: предупреждение на 35 секундах, затем автоматический возврат в меню на 90. <color=#7FE87F>Без штрафа.</color>$s256$)
  , ('6aac6cbbebced3a5', 'sv', '4dcbd19d1118a776e37c240a8993203892053054', $s256$<color=#FFD94D><b>VEM FÅR SOLOPLATSEN</b></color>

- Du kan köa med en föredragen sida. Låsningen tar de tre live-köare som väntat längst; soloplatsen går till den tidigast anslutna som bett om solo, eller annars till den tidigast anslutna rakt av. De andra två blir duon.
- Rummets Photon-region är den första region någon i kön faktiskt rapporterat, i köordning, med US som reserv.

<color=#FFD94D><b>SPAWNSIDOR</b></color>

- Varje vanilla-karta har exakt fyra spawnpunkter, två per halva. I 1v2 tar solon den yttre vänstra punkten och duon får hela högra halvan - en duospelare spawnar aldrig på solons sida.

<color=#FFD94D><b>SOLONS EXTRAKORT, I DETALJ</b></color>

- I slumpkön räcker det att en spelare köar med det aktiverat för att det ska gälla serien; i en värdlobby avgör värdens inställning.
- Extradragningen gäller enbart den FÖRSTA dragningen: solon väljer två kort före rond 1, sedan ett per val precis som alla andra.

<color=#FFD94D><b>BETALNINGSMULTIPLIKATORER</b></color>

Bassiffrorna för XP och guld ovan multipliceras med en svårighetsmultiplikator:

- Soloplatsen får alltid x1.5.
- En solo som spelar UTAN extrakortet får ytterligare x1.2; en duo som möter en solo med extrakort får x1.1.
- Dina motståndares 1v1-ratingtier multiplicerar också (upp till x3.0), och att möta en 1v2-podiespelare ger x1.35, vid vinst som förlust.
- Svårighetsprodukten har ett tak på x4.0, med vinstbonusen x1.5 ovanpå taket. Serieguld skalas enbart efter motståndartier.

<color=#FFD94D><b>DISCONNECTS</b></color>

- Så länge 1v2 är en orankad beta finns ingen DC-pipeline: utfall kommer enbart från registrerade matcher, och ingen avhoppsräknare finns för 1v2.
- Att lämna i låst läge med noll spelade matcher upplöser låsningen - serien avbryts, kö-överlevare återgår till sökning och en värdlobbys kvarvarande släpps helt enkelt.
- Ett avhopp mitt i en match lämnar utfallet till den vanliga matchrapporten.
- Om ett låst rum aldrig fylls: en varning vid 35 sekunder, sedan automatisk återgång till menyn vid 90. <color=#7FE87F>Inget straff.</color>$s256$)
  , ('6aac6cbbebced3a5', 'uk', '4dcbd19d1118a776e37c240a8993203892053054', $s256$<color=#FFD94D><b>КОМУ ДІСТАЄТЬСЯ МІСЦЕ СОЛО</b></color>

- У чергу можна стати з бажаною стороною. Фіксація бере трьох живих гравців черги, що чекають найдовше; місце соло йде найранішому, хто просив соло, або просто найранішому, якщо не просив ніхто. Двоє інших - дуо.
- Photon-регіон кімнати - перший регіон, про який хтось у черзі реально відзвітував, у порядку черги, з US як запасним.

<color=#FFD94D><b>СТОРОНИ СПАВНУ</b></color>

- Кожна ванільна мапа має рівно чотири точки появи, по дві на половину. У 1v2 соло бере зовнішню ліву точку, а дуо отримує всю праву половину - гравець дуо ніколи не спавниться на боці соло.

<color=#FFD94D><b>ДОДАТКОВИЙ ВИБІР СОЛО, ТОЧНО</b></color>

- У випадковій черзі його вмикає для серії будь-хто, хто став у чергу з увімкненим; у хостованому лобі вирішує налаштування хоста.
- Додатковий добір діє лише на ПЕРШИЙ вибір: соло бере дві карти перед раундом 1, далі одну за вибір, як усі.

<color=#FFD94D><b>МНОЖНИКИ ВИПЛАТ</b></color>

Базові числа XP і золота вище множаться на множник складності:

- Місце соло завжди заробляє x1.5.
- Соло, що грає БЕЗ додаткового вибору, заробляє ще x1.2; дуо проти соло з додатковим вибором заробляє x1.1.
- Рейтинговий рівень 1v1 ваших суперників теж множить (до x3.0), а гра проти гравця подіуму 1v2 додає x1.35, перемога чи поразка.
- Добуток складності обмежений x4.0, з бонусом за перемогу x1.5 поверх нього. Золото серії масштабується лише рівнем суперника.

<color=#FFD94D><b>ДИСКОНЕКТИ</b></color>

- Поки 1v2 - нерейтингова бета, конвеєра DC вона не має: результати йдуть лише із записаних ігор, і лічильника виходів для 1v2 не існує.
- Вихід у фіксації з нулем зіграних ігор розчиняє фіксацію - серія скасовується, вцілілі з черги повертаються до пошуку, а вцілілих хостованого лобі просто відпускає.
- Вихід посеред гри лишає результат звичайному звіту про матч.
- Якщо зафіксована кімната так і не заповниться: попередження на 35-й секунді, потім автоматичне повернення в меню на 90-й. <color=#7FE87F>Без штрафу.</color>$s256$)
  , ('6b5fb58c52c8a481', 'es', '25f8ec2ccd6de665d397ed4d11c7720be30e0c93', $s256$<color=#FFD94D><b>LA VENTANA DE 0.35 SEGUNDOS</b></color>

Para prepararte para este conocimiento, primero debo admitir que mentí en la tabla. Donde dice que el daño de bala activa un Refresh con un Sí a secas, debería llevar un asterisco: lo hace la mayoría de las veces, pero no todas. Presumiblemente para ayudar a equilibrar cartas como Burst y Spray, los desarrolladores montaron un sistema que convierte el daño no Condicional repetido con rapidez en daño Condicional. Dispara a un rival una vez y obtienes daño no Condicional; dispárale otra vez dentro de una ventana de alrededor de 0.35 segundos y ese segundo disparo es Condicional. La ventana se reinicia tras cada disparo. Abajo, los disparos secundarios (y terciarios) rápidos se anotan QShoot:

<color=#FFD94D>RefreshValid</color><pos=30%>False<pos=44%>False<pos=58%>True<pos=72%>False<pos=86%>True
<color=#FFD94D>Acción</color><pos=30%>Disparo<pos=44%>QShoot<pos=58%>Silence<pos=72%>QShoot<pos=86%>Silence
<color=#FFD94D>¿Refresh?</color><pos=30%>Sí<pos=44%>No<pos=58%>Sí<pos=72%>No<pos=86%>Sí

<color=#FFD94D>RefreshValid</color><pos=30%>False<pos=44%>False<pos=58%>True<pos=72%>False<pos=86%>True
<color=#FFD94D>Acción</color><pos=30%>Disparo<pos=44%>Silence<pos=58%>QShoot<pos=72%>Silence<pos=86%>QShoot
<color=#FFD94D>¿Refresh?</color><pos=30%>Sí<pos=44%>No<pos=58%>Sí<pos=72%>No<pos=86%>Sí

<color=#FFD94D><b>NO HAY TIPOS DE DAÑO</b></color>

Ahora que entiendes esto, debo admitir que mentí por segunda vez. Te engañé, te embauqué, para que creyeras que el daño Condicional y el no Condicional son dos tipos de daño separados, concedidos uno a uno a ciertos ataques por los desarrolladores. Es incorrecto. El daño se trata igual venga de donde venga. En realidad no hay tipos de daño en absoluto. Entonces, ¿cómo se decide si un daño es Condicional o no? Lo decide el daño. Literalmente. Cuántos puntos de daño intentas infligir determina si Refresh no se activa en absoluto, se activa Condicionalmente o se activa siempre (salvo que caiga dentro de la ventana de 0.35 segundos, en cuyo caso se vuelve Condicional).

Lo descubrí acumulando Silence. Mientras que un Silence normal tiene un daño máximo de alrededor de 9, acumular dos Silence puede llegar hasta 17, probablemente más. Digo 'llegar' porque Silence hace daño de área - cuanto más lejos estás del objetivo, menos daño haces. En cualquier caso: con el daño de Silence por encima de 10, se vuelve no Condicional. Acumula dos Silence y un Refresh y puedes encadenar Silence infinitamente - siempre que cada Silence aterrice en el rango de daño superior a 10. Cae en el rango de 5 a 10 y vuelve a ser Condicional; baja de 5 de daño y no se activa ningún Refresh jamás. Tampoco puedes ciclar los Silence demasiado rápido, o la ventana de 0.35 segundos salta y vuelve Condicional tu daño no Condicional otra vez. (Ya ves por qué esto fue una pesadilla de descifrar.)

Lo mágico es que este rango se aplica a absolutamente todas las fuentes de daño. Acumula suficientes Frost Slam o Shockwave y puedes producir el mismo resultado. Lo mismo vale para el daño de explosión en área de Timed Detonation o Explosive Bullet. Las balas normales tienen un daño mínimo de 14, así que no puedes llegar a Condicional solo con reducción de daño - pero si tu rival consigue Decay, cada tick individual lleva un daño tan bajo que no recuperas ningún Refresh. O al menos no deberías: por la inconsistencia de los ticks puede que de vez en cuando consigas uno o dos, a un ritmo enormemente reducido. A la inversa, acumula suficiente daño y aunque se reparta entre ticks aún te alcanza para Refresh constantes. Para cartas como EMP y Bombs Away, que no pueden cambiar su daño, esta revelación no significa nada. También significa poco para Demonic Pact, Frost Slam y Shockwave, porque la acumulación necesaria para subir su daño a la siguiente banda no es realista dentro de una partida normal.

<color=#FFD94D><b>LA DECISIÓN COMPLETA, COMO FLUJO</b></color>

Inflige daño:
- Menos de 5 de daño: no pasa nada.
- Entre 5 y 10 de daño (Condicional):
   Si RefreshValid es true - se activa un Refresh, y RefreshValid pasa a false.
   Si RefreshValid es false - no hay Refresh, y RefreshValid pasa a true.
- Más de 10 de daño:
   Dentro de la ventana de 0.35 segundos - la ventana se reinicia y el golpe se trata como el caso de 5 a 10 de arriba.
   Fuera de la ventana - siempre se activa un Refresh, la ventana empieza, y RefreshValid se pone a false.

Eso resume todo mi entendimiento actual del daño Condicional. Mi modelo de lo que pasa entre bambalinas es enteramente una construcción (no he visto el código fuente), pero predice correctamente todo el comportamiento probado hasta ahora, y he sido minucioso. Aun así, hay límites: no sé si el booleano RefreshValid lo guarda el atacante o el objetivo - es decir, si cada jugador tiene un tope sobre los Refresh que puede activar para sí, o cada objetivo tiene un tope sobre los Refresh que puede activar para otros. En un 1v1 no cambia nada, pero en un FFA sí cambiaría. ¡Si al menos existiera un modo de juego tipo free-to-play que pudiera usar para probar esta característica!

<color=#FFD94D><b>CONCLUSIÓN</b></color>

Ahora bien, por bellamente complejo que sea este sistema, tengo que preguntar cómo demonios pensaron los desarrolladores que sería buena idea. ¿Qué se supone que equilibra? ¿Por qué la cantidad de daño dicta los Refresh? ¿Cómo iba nadie a saber nada de esto? Preguntas que solo puede responder la mente retorcida que soñó este sistema.

Aprecio las sutilezas del sistema, pero desde la perspectiva del gameplay es abominable. Ningún humano real va a calcular con precisión su estado de RefreshValid en mitad de una pelea - eso, si alguna vez te sale una build en la que esta información importe. Las probabilidades de que mis hallazgos afecten a tus próximas 30 partidas van de bajas a inexistentes. Al final del día, la experiencia de jugador que este sistema produce es de confusión, frustración y azar. Y aun así, dicho todo esto, no querría que lo cambiaran. ¿Por qué? Porque si lo hicieran, la última semana de mi vida habría sido en vano.

Gracias por leer mis divagaciones. Espero que al menos la tabla te resulte útil.

<color=#8A8A93>Lecturas relacionadas: <color=#7FD4FF>Bloqueo</color> cubre qué hace realmente un bloqueo y qué cartas van montadas en él; <color=#7FD4FF>Veneno y daño en el tiempo</color> cubre cómo aterrizan y se sincronizan los ticks de daño.</color>$s256$)
  , ('6b5fb58c52c8a481', 'ru', '25f8ec2ccd6de665d397ed4d11c7720be30e0c93', $s256$<color=#FFD94D><b>ОКНО В 0.35 СЕКУНДЫ</b></color>

Чтобы подготовить тебя к этому знанию, я обязан сперва признаться, что солгал в таблице. Там, где сказано, что урон пулями запускает Refresh простым «Да», должна стоять звёздочка: так бывает большую часть времени, но не всегда. Видимо, чтобы помочь балансу карт вроде Burst и Spray, разработчики поставили систему, превращающую быстро повторённый безусловный урон в условный. Выстрели в соперника один раз - получишь безусловный урон; выстрели снова в окне около 0.35 секунды - и этот второй выстрел условный. Окно сбрасывается после каждого выстрела. Ниже быстрые вторые (и третьи) выстрелы обозначены QShoot:

<color=#FFD94D>RefreshValid</color><pos=30%>False<pos=44%>False<pos=58%>True<pos=72%>False<pos=86%>True
<color=#FFD94D>Действие</color><pos=30%>Выстрел<pos=44%>QShoot<pos=58%>Silence<pos=72%>QShoot<pos=86%>Silence
<color=#FFD94D>Refresh?</color><pos=30%>Да<pos=44%>Нет<pos=58%>Да<pos=72%>Нет<pos=86%>Да

<color=#FFD94D>RefreshValid</color><pos=30%>False<pos=44%>False<pos=58%>True<pos=72%>False<pos=86%>True
<color=#FFD94D>Действие</color><pos=30%>Выстрел<pos=44%>Silence<pos=58%>QShoot<pos=72%>Silence<pos=86%>QShoot
<color=#FFD94D>Refresh?</color><pos=30%>Да<pos=44%>Нет<pos=58%>Да<pos=72%>Нет<pos=86%>Да

<color=#FFD94D><b>ТИПОВ УРОНА НЕ СУЩЕСТВУЕТ</b></color>

Теперь, когда ты это понял, я обязан признаться, что солгал во второй раз. Я ввёл тебя в заблуждение, внушив, будто условный и безусловный урон - два отдельных типа урона, поштучно назначенных разработчиками определённым атакам. Это неверно. Урон обрабатывается одинаково независимо от источника. В действительности типов урона нет вовсе. Как же тогда решается, условен урон или нет? Это решает сам урон. Буквально. Сколько очков урона ты пытаешься нанести - вот что определяет, не сработает ли Refresh вовсе, сработает условно или сработает всегда (если только урон не лёг внутрь окна 0.35 секунды - тогда он становится условным).

Я открыл это, стакая Silence. Обычный Silence имеет максимум урона около 9, но стак из двух Silence достаёт до 17, а вероятно и выше. Я говорю «достаёт», потому что Silence наносит AoE-урон: чем дальше ты от цели, тем меньше урона наносишь. Как бы то ни было: с уроном Silence больше 10 он становится безусловным. Стакни два Silence и Refresh - и можно зациклить Silence бесконечно, при условии, что каждый Silence ложится в диапазон урона выше 10. Упади в диапазон от 5 до 10 - он снова условный; упади ниже 5 урона - Refresh не запускается вовсе. Ещё нельзя циклить Silence слишком быстро, иначе срабатывает окно 0.35 секунды и снова превращает твой безусловный урон в условный. (Понимаешь теперь, каким кошмаром было в этом разобраться.)

Волшебство в том, что этот диапазон применяется к каждому источнику урона без исключения. Стакни достаточно Frost Slam или Shockwave - получишь тот же результат. То же верно для AoE-урона взрывов от Timed Detonation или Explosive Bullet. У обычных пуль минимальный урон 14, так что одним снижением урона до условного не добраться - но если сопернику попадётся Decay, отдельные тики несут настолько малый урон, что Refresh ты не получаешь. Ну или не должен: из-за нестабильности тиков иногда перепадёт один-другой, с сильно сниженной частотой. И наоборот: стакни достаточно урона - и даже поделённый между тиками он остаётся достаточным для постоянных Refresh. Для карт вроде EMP и Bombs Away, которые не могут менять свой урон, это откровение не значит ничего. Мало значит оно и для Demonic Pact, Frost Slam и Shockwave: стак, нужный, чтобы поднять их урон в следующий диапазон, нереален в обычной игре.

<color=#FFD94D><b>ПОЛНОЕ РЕШЕНИЕ, КАК СХЕМА</b></color>

Наносишь урон:
- Меньше 5 урона: не происходит ничего.
- От 5 до 10 урона (условный):
   Если RefreshValid равен true - Refresh срабатывает, и RefreshValid переключается в false.
   Если RefreshValid равен false - Refresh нет, и RefreshValid переключается в true.
- Больше 10 урона:
   Внутри окна 0.35 секунды - окно сбрасывается, и удар обрабатывается как случай 5-10 выше.
   Вне окна - Refresh срабатывает всегда, окно начинается, RefreshValid ставится в false.

Это всё моё текущее понимание условного урона. Моя модель происходящего за кулисами - целиком конструкция (исходного кода я не видел), но она верно предсказывает всё проверенное на данный момент поведение, а проверял я тщательно. И всё же есть пределы: я не знаю, у кого хранится бул RefreshValid - у атакующего или у цели; то есть у каждого ли игрока лимит на Refresh, которые он может запустить себе, или у каждой цели лимит на Refresh, которые она может запустить другим. В 1v1 разницы нет, а вот в FFA была бы. Если бы только существовал какой-нибудь бесплатный режим формата «все против всех», где я мог бы это проверить!

<color=#FFD94D><b>ЗАКЛЮЧЕНИЕ</b></color>

Теперь, при всей прекрасной сложности этой системы, я обязан спросить: как вообще разработчикам пришло в голову, что это хорошая идея? Что она должна балансировать? Почему количество урона диктует Refresh? Как кто-то должен был обо всём этом узнать? Вопросы, ответить на которые может лишь тот изощрённый ум, что эту систему выдумал.

Я ценю тонкости системы, но с точки зрения геймплея она чудовищна. Ни один живой человек не станет точно вычислять своё состояние RefreshValid посреди боя - если тебе вообще когда-нибудь достанется билд, где эта информация важна. Шансы, что мои находки повлияют на твои следующие 30 матчей, - от низких до несуществующих. В конечном счёте игровой опыт, который эта система порождает, - это растерянность, фрустрация и случайность. И всё же, при всём сказанном, я не хотел бы её менять. Почему? Потому что иначе последняя неделя моей жизни была бы потрачена зря.

Спасибо, что прочёл мои разглагольствования. Надеюсь, таблица тебе хотя бы пригодится.

<color=#8A8A93>Смежное чтение: <color=#7FD4FF>Блокирование</color> - что на самом деле делает блок и какие карты на нём едут; <color=#7FD4FF>Яд и урон со временем</color> - как ложится и синхронизируется тиковый урон.</color>$s256$)
  , ('6b5fb58c52c8a481', 'sv', '25f8ec2ccd6de665d397ed4d11c7720be30e0c93', $s256$<color=#FFD94D><b>0.35-SEKUNDERSFÖNSTRET</b></color>

För att förbereda dig på denna kunskap måste jag först erkänna att jag ljög i tabellen. Där det står att Kulskada utlöser en Refresh med ett rent Ja borde det stå en asterisk: det gör den för det mesta, men inte alltid. Förmodligen för att hjälpa till att balansera kort som Burst och Spray har utvecklarna infört ett system som förvandlar snabbt upprepad icke-Villkorlig skada till Villkorlig skada. Skjut en motståndare en gång och du får icke-Villkorlig skada; skjut dem igen inom ett fönster på ungefär 0.35 sekunder och det andra skottet är Villkorligt. Fönstret nollställs efter varje skott. Nedan betecknas snabba andra- (och tredje-)skott QShoot:

<color=#FFD94D>RefreshValid</color><pos=30%>Falskt<pos=44%>Falskt<pos=58%>Sant<pos=72%>Falskt<pos=86%>Sant
<color=#FFD94D>Handling</color><pos=30%>Skjut<pos=44%>QShoot<pos=58%>Silence<pos=72%>QShoot<pos=86%>Silence
<color=#FFD94D>Refresh?</color><pos=30%>Ja<pos=44%>Nej<pos=58%>Ja<pos=72%>Nej<pos=86%>Ja

<color=#FFD94D>RefreshValid</color><pos=30%>Falskt<pos=44%>Falskt<pos=58%>Sant<pos=72%>Falskt<pos=86%>Sant
<color=#FFD94D>Handling</color><pos=30%>Skjut<pos=44%>Silence<pos=58%>QShoot<pos=72%>Silence<pos=86%>QShoot
<color=#FFD94D>Refresh?</color><pos=30%>Ja<pos=44%>Nej<pos=58%>Ja<pos=72%>Nej<pos=86%>Ja

<color=#FFD94D><b>DET FINNS INGA SKADETYPER</b></color>

Nu när du förstår detta måste jag erkänna att jag ljög en andra gång. Jag vilseledde dig, lirkade in dig i tron att Villkorlig och icke-Villkorlig skada är två separata skadetyper, individuellt tilldelade vissa attacker av utvecklarna. Detta är felaktigt. Skada behandlas likadant oavsett källa. I själva verket finns det inga skadetyper alls. Så hur avgörs det om skada är Villkorlig eller inte? Skadan avgör det. Bokstavligen. Hur många poäng skada du försöker göra avgör om Refresh inte aktiveras alls, aktiveras Villkorligt, eller alltid aktiveras (om den inte landar inom 0.35-sekundersfönstret, i vilket fall den blir Villkorlig).

Jag upptäckte detta när jag staplade Silence. Medan en vanlig Silence har en maxskada på runt 9, kan två staplade Silence nå så högt som 17, troligen mer. Jag säger 'nå' eftersom Silence gör AoE-skada - ju längre från målet du är, desto mindre skada gör du. Hur som helst: med Silences skada över 10 blir den icke-Villkorlig. Stapla två Silence och en Refresh och du kan loopa Silence i oändlighet - förutsatt att du landar varje Silence i skadeintervallet över 10. Faller du in i intervallet 5 till 10 blir den Villkorlig igen; faller du under 5 skada utlöses ingen Refresh alls. Du kan inte heller cykla Silence för fort, för då slår 0.35-sekundersfönstret till och gör din icke-Villkorliga skada Villkorlig igen. (Förstår du varför detta var en mardröm att lista ut.)

Det magiska är att detta intervall gäller varenda skadekälla. Stapla nog med Frost Slam eller Shockwave och du kan framkalla samma resultat. Detsamma gäller AoE-explosionsskada från Timed Detonation eller Explosive Bullet. Vanliga kulor har en minimiskada på 14, så du kan inte nå Villkorlig med enbart skadereduktion - men om din motståndare får Decay bär de enskilda ticksen så låg skada att du inte får några Refresh tillbaka. Eller det borde du åtminstone inte: på grund av tick-inkonsekvens kan du någon gång få en eller två, i kraftigt reducerad takt. Omvänt: stapla nog med skada och även när den delas mellan ticks har du fortfarande nog för konstanta Refresh. För kort som EMP och Bombs Away, som inte kan ändra sin skada, betyder denna uppenbarelse ingenting. Den betyder också lite för Demonic Pact, Frost Slam och Shockwave, då staplingen som krävs för att lyfta deras skada till nästa band inte är realistisk inom en normal match.

<color=#FFD94D><b>HELA BESLUTET, SOM ETT FLÖDE</b></color>

Gör skada:
- Under 5 skada: ingenting händer.
- Mellan 5 och 10 skada (Villkorlig):
   Om RefreshValid är sant - en Refresh utlöses, och RefreshValid slår om till falskt.
   Om RefreshValid är falskt - ingen Refresh, och RefreshValid slår om till sant.
- Över 10 skada:
   Inom 0.35-sekundersfönstret - fönstret nollställs och träffen behandlas som 5-till-10-fallet ovan.
   Utanför fönstret - en Refresh utlöses alltid, fönstret börjar, och RefreshValid sätts till falskt.

Det utgör hela min nuvarande förståelse av Villkorlig skada. Min modell av vad som pågår bakom kulisserna är helt och hållet en konstruktion (jag har inte sett källkoden), men den förutsäger korrekt allt hittills testat beteende, och jag har varit grundlig. Ändå finns gränser: jag vet inte om RefreshValid-boolen hålls av angriparen eller målet - alltså om varje spelare har ett tak på de Refresh de kan utlösa åt sig själva, eller varje mål har ett tak på de Refresh de kan utlösa åt andra. I en 1v1 spelar det ingen roll, men i en FFA skulle det göra det. Om det bara fanns ett free-to-play-aktigt spelläge jag kunde använda för att testa den saken!

<color=#FFD94D><b>SLUTSATS</b></color>

Nu, hur vackert komplext detta system än är, måste jag ändå fråga hur i hela friden utvecklarna tänkte att det här var en bra idé. Vad är det tänkt att balansera? Varför dikterar skademängden Refresh? Hur skulle någon någonsin kunna veta något av detta? Frågor som bara det förvridna sinne som drömde ihop systemet kan besvara.

Jag uppskattar systemets subtiliteter, men ur ett spelperspektiv är det avskyvärt. Ingen verklig människa kommer att korrekt beräkna sitt RefreshValid-tillstånd mitt i en strid - det vill säga, om du ens någonsin får en build där denna information spelar roll. Chansen att mina fynd här påverkar dina nästa 30 matcher sträcker sig från låg till obefintlig. I slutändan är spelarupplevelsen detta system ger en av förvirring, frustration och slumpmässighet. Ändå, allt detta sagt, skulle jag inte vilja att det ändrades. Varför? För om det gjordes skulle den senaste veckan av mitt liv ha varit bortkastad.

Tack för att du läste mina utläggningar. Jag hoppas att du åtminstone får nytta av tabellen.

<color=#8A8A93>Relaterad läsning: <color=#7FD4FF>Blockering</color> täcker vad ett block faktiskt gör och vilka kort som rider på det; <color=#7FD4FF>Gift & skada över tid</color> täcker hur tickskada landar och synkas.</color>$s256$)
  , ('6b5fb58c52c8a481', 'uk', '25f8ec2ccd6de665d397ed4d11c7720be30e0c93', $s256$<color=#FFD94D><b>ВІКНО 0.35 СЕКУНДИ</b></color>

Щоб підготувати вас до цього знання, мушу спершу зізнатися, що збрехав у таблиці. Там, де сказано, що шкода від куль тригерить Refresh простим «Так», мала б стояти зірочка: так буває здебільшого, але не завжди. Ймовірно, щоб допомогти збалансувати карти на кшталт Burst і Spray, розробники вбудували систему, яка перетворює швидко повторену НЕумовну шкоду на Умовну. Влучіть у суперника раз - отримаєте неумовну шкоду; влучіть знову в межах вікна близько 0.35 секунди - і той другий постріл Умовний. Вікно скидається після кожного пострілу. Нижче швидкі другі (і треті) постріли позначені QShoot:

<color=#FFD94D>RefreshValid</color><pos=30%>False<pos=44%>False<pos=58%>True<pos=72%>False<pos=86%>True
<color=#FFD94D>Дія</color><pos=30%>Постріл<pos=44%>QShoot<pos=58%>Silence<pos=72%>QShoot<pos=86%>Silence
<color=#FFD94D>Refresh?</color><pos=30%>Так<pos=44%>Ні<pos=58%>Так<pos=72%>Ні<pos=86%>Так

<color=#FFD94D>RefreshValid</color><pos=30%>False<pos=44%>False<pos=58%>True<pos=72%>False<pos=86%>True
<color=#FFD94D>Дія</color><pos=30%>Постріл<pos=44%>Silence<pos=58%>QShoot<pos=72%>Silence<pos=86%>QShoot
<color=#FFD94D>Refresh?</color><pos=30%>Так<pos=44%>Ні<pos=58%>Так<pos=72%>Ні<pos=86%>Так

<color=#FFD94D><b>ТИПІВ ШКОДИ НЕ ІСНУЄ</b></color>

Тепер, коли ви це зрозуміли, мушу зізнатися, що збрехав удруге. Я ввів вас в оману, вмовив повірити, що Умовна і неумовна шкода - два окремі типи шкоди, персонально роздані певним атакам розробниками. Це не так. Шкода обробляється однаково незалежно від джерела. Насправді типів шкоди немає взагалі. То як же вирішується, Умовна шкода чи ні? Це вирішує сама шкода. Буквально. Скільки очок шкоди ви намагаєтеся завдати - ось що визначає, чи Refresh не спрацює зовсім, чи спрацює Умовно, чи спрацює завжди (хіба що влучання впаде у вікно 0.35 секунди - тоді воно стає Умовним).

Я відкрив це, стакаючи Silence. Звичайний Silence має максимум близько 9 шкоди, а два стаковані Silence сягають аж 17, певно й більше. Кажу «сягають», бо Silence завдає AoE-шкоди: що далі ви від цілі, то менше шкоди завдаєте. Хай там як: коли шкода Silence перевалює за 10, вона стає неумовною. Стакніть два Silence і Refresh - і можна крутити Silence нескінченно, за умови, що кожен Silence влучає в діапазоні понад 10 шкоди. Впадете в діапазон 5-10 - шкода знову Умовна; нижче 5 - Refresh не спрацьовує взагалі. І циклити Silence надто швидко теж не можна, бо тоді спрацює вікно 0.35 секунди і зробить вашу неумовну шкоду знову Умовною. (Розумієте, чому це був такий кошмар для розшифрування.)

Магія в тому, що цей діапазон стосується кожного джерела шкоди. Настакайте досить Frost Slam чи Shockwave - і отримаєте той самий результат. Те саме з AoE-шкодою вибухів від Timed Detonation чи Explosive Bullet. Звичайні кулі мають мінімум 14 шкоди, тож самим лише зниженням шкоди до Умовної не дістатися - але якщо суперник візьме Decay, окремі тіки несуть настільки малу шкоду, що Refresh ви не отримуєте. Принаймні не мали б: через нестабільність тіків інколи один-два таки проскочать, значно рідше. І навпаки: настакайте досить шкоди - і навіть поділеної між тіками її вистачає на постійні Refresh. Для карт як EMP і Bombs Away, що не можуть змінити свою шкоду, це відкриття не означає нічого. Мало означає воно й для Demonic Pact, Frost Slam і Shockwave: стакання, потрібне, щоб підняти їхню шкоду в наступний діапазон, нереалістичне в межах звичайної гри.

<color=#FFD94D><b>ПОВНЕ РІШЕННЯ, ЯК СХЕМА</b></color>

Завдаєте шкоду:
- Менше 5 шкоди: не стається нічого.
- Від 5 до 10 шкоди (Умовна):
   Якщо RefreshValid true - Refresh спрацьовує, а RefreshValid перемикається у false.
   Якщо RefreshValid false - Refresh немає, а RefreshValid перемикається у true.
- Понад 10 шкоди:
   Усередині вікна 0.35 секунди - вікно скидається, і влучання обробляється як випадок 5-10 вище.
   Поза вікном - Refresh спрацьовує завжди, вікно починається, а RefreshValid ставиться у false.

Оце і все моє теперішнє розуміння Умовної шкоди. Моя модель того, що коїться за лаштунками, - цілком конструкція (вихідного коду я не бачив), але вона правильно передбачає всю наразі перевірену поведінку, а перевіряв я ретельно. Межі все ж є: я не знаю, чи булеве RefreshValid тримає нападник, чи ціль, - тобто чи кожен гравець має стелю Refresh, які може тригернути для себе, чи кожна ціль має стелю Refresh, які може тригернути для інших. У 1v1 різниці немає, а от у FFA була б. От якби існував якийсь безкоштовний режим гри, де я міг би це перевірити!

<color=#FFD94D><b>ВИСНОВОК</b></color>

І от, хоч якою прекрасно складною є ця система, я мушу спитати: як, заради всього святого, розробники вирішили, що це гарна ідея? Що вона мала б балансувати? Чому кількість шкоди диктує Refresh? Звідки хтось узагалі мав про це дізнатися? Питання, на які відповість лише той викривлений розум, що цю систему вигадав.

Я ціную тонкощі системи, але з погляду геймплею вона огидна. Жодна жива людина не буде точно обчислювати стан свого RefreshValid посеред бою - це якщо вам узагалі колись трапиться білд, де ця інформація важить. Шанси, що мої знахідки вплинуть на ваші наступні 30 матчів, - від низьких до неіснуючих. Зрештою, гравецький досвід, який породжує ця система, - це збентеження, фрустрація і випадковість. І все ж, попри все сказане, я не хотів би, щоб її змінювали. Чому? Бо тоді останній тиждень мого життя був би змарнований.

Дякую, що прочитали мої просторікування. Сподіваюся, бодай таблиця стане вам у пригоді.

<color=#8A8A93>Суміжне читання: <color=#7FD4FF>Блокування</color> пояснює, що насправді робить блок і які карти на ньому їдуть; <color=#7FD4FF>Отрута та поступова шкода</color> - як сідає і синхронізується тікова шкода.</color>$s256$)
  , ('6b9260da4b06a2c5', 'es', '2d2ff271edf97f022c61da788ed38114dbe3f96d', $s256$Cómo se registran las partidas$s256$)
  , ('6b9260da4b06a2c5', 'ru', '2d2ff271edf97f022c61da788ed38114dbe3f96d', $s256$Как записываются игры$s256$)
  , ('6b9260da4b06a2c5', 'sv', '2d2ff271edf97f022c61da788ed38114dbe3f96d', $s256$Så registreras matcher$s256$)
  , ('6b9260da4b06a2c5', 'uk', '2d2ff271edf97f022c61da788ed38114dbe3f96d', $s256$Як записуються ігри$s256$)
  , ('70575acc4c8435c3', 'es', 'e530201df3b466b7afb745f02669182642d7a8ef', $s256$Plazos e incomparecencias$s256$)
  , ('70575acc4c8435c3', 'ru', 'e530201df3b466b7afb745f02669182642d7a8ef', $s256$Дедлайны и техпоражения$s256$)
  , ('70575acc4c8435c3', 'sv', 'e530201df3b466b7afb745f02669182642d7a8ef', $s256$Tidsfrister & walkover$s256$)
  , ('70575acc4c8435c3', 'uk', 'e530201df3b466b7afb745f02669182642d7a8ef', $s256$Терміни й технічні поразки$s256$)
  , ('77d8d2d50b004dd4', 'es', '7e2299a8cab8d708d1c275e314cf72784ffaa7c9', $s256$Grow$s256$)
  , ('77d8d2d50b004dd4', 'ru', '7e2299a8cab8d708d1c275e314cf72784ffaa7c9', $s256$Grow$s256$)
  , ('77d8d2d50b004dd4', 'sv', '7e2299a8cab8d708d1c275e314cf72784ffaa7c9', $s256$Grow$s256$)
  , ('77d8d2d50b004dd4', 'uk', '7e2299a8cab8d708d1c275e314cf72784ffaa7c9', $s256$Grow$s256$)
  , ('7f82c46780cd1b48', 'es', 'afb7bfc9b084206a7ffa2cc8b3d901c8516df3d3', $s256$Todos contra todos para 3-10 jugadores. Cada jugador es su propio equipo.
Puntuación estándar de ROUNDS - el primero a {0} puntos se lleva la partida.

<color=#FFD94D><b>CÓMO SE JUEGA</b></color>

- No hay banda de Elo. Entrar a una sala es consentir jugar.

- Crea una sala o únete a una abierta desde la lista.
  El ANFITRIÓN pulsa Empezar cuando hay al menos 3
  jugadores (hasta 10). Puede haber varias salas abiertas.

- Si el anfitrión se va, el miembro que más lleva
  esperando pasa a ser el nuevo anfitrión.

- Tras cada punto, todos menos el ganador del punto
  eligen una carta a la vez.

- El tiempo de elección se ve en pantalla. Una elección
  cerca del final da a todos un poco de tiempo extra.
  Cuando tu tiempo llega a cero, tu carta resaltada se
  elige automáticamente - alejarte del PC nunca se
  salta tu elección. Solo una elección que pierde la
  ventana por completo (una congelación, un crash o el
  último instante) queda sin carta, con un aviso que lo dice.

- Llevas hasta {1} cartas.
  Elegir una más sustituye tu carta más antigua.

<color=#FFD94D><b>AJUSTES DEL ANFITRIÓN</b></color>

- El anfitrión puede ajustar la sala antes de empezar:
  puntos objetivo (3-10), robos iniciales, cartas por
  robo (1-5), cartas máximas (3-5 en ranked, hasta 6
  en casual), la regla de Mismas cartas y ranked/casual.

- Regla de Mismas cartas: el robo N de cada jugador
  ofrece las MISMAS candidatas, en el mismo orden - si a
  ti y a un rival os ofrecieron cartas idénticas toda la
  partida, ningún resultado puede achacarse a la suerte
  del robo. Las de copia única (como Phoenix) salen como mucho una vez por partida para todos.

- Tras un cambio de ajustes la sala no puede empezar
  durante 60 segundos (y un momento tras entrar alguien),
  para que todos lean qué cambió. Las salas casual pagan
  recompensas reducidas y nunca tocan el rating.

<color=#FFD94D><b>RATING</b></color>

- El FFA es ranked con su propio rating Glicko.

- La posición usa puntos, luego todas las rondas ganadas
  (incluidas las gastadas) y luego las kills.
  Los empates restantes comparten puesto en orden de
  competición: 1, 2, 2, 4.

- Tu rating se puntúa contra los jugadores colocados
  más cerca de ti (hasta 4), así una partida no puede
  mover tu rating varias veces más fuerte en una sala de
  10 que en una de 3. Una comparación extra puede unirse
  a esas cuatro: la mayor brecha de rating de 250+ que
  terminó invertida fuera de ellas.

- Un puesto empatado cuenta como empate. Los ratings
  nuevos se mueven rápido y se asientan al jugar más.

<color=#FFD94D><b>RECOMPENSAS</b></color>

- La paga se mide por la LUCHA, no por cifras planas
  por partida: las rondas decisivas son la unidad de
  trabajo, y el tiempo transcurrido limita lo rápido
  que se cobran - las tácticas de alargar quedan
  acotadas, y las partidas más largas y grandes pagan más.

- Las salas más grandes pagan mejor tarifa por minuto,
  y un FFA de 10 jugadores es la mejor tarifa de oro del juego.

- Tu posición define tu parte: el 1.º gana unas cinco
  veces lo del último. Parte se paga como XP, parte como
  Oro de posición, y un campo rival más fuerte
  multiplica el bote (el bono de tier habitual).

- La XP se convierte en Oro a 100 XP = 1 Oro, y subir de
  nivel paga su Oro extra habitual. Una subida de nivel
  durante una partida aparece dentro del +g de esa
  partida - así un último puesto puede a veces ganar más que el vencedor.

- Los espectadores pueden apostar Oro en las salas FFA desde esta pestaña.

<color=#FFD94D><b>LEER LA LISTA DE FFA RECIENTES</b></color>

<color=#7FD4FF>Círculos + N(P)</color> - Puntos completos ganados.
<color=#7FD4FF>Medios círculos + N(H)</color> - Rondas ganadas que
  no llegaron a ser un punto completo de ese jugador.
<color=#7FD4FF>Nk</color> - Kills.
<color=#7FD4FF>+xp +g</color> - XP y Oro de esa partida
  (incluido cualquier bono por subir de nivel).
<color=#7FD4FF>Número verde/rojo</color> - Cambio de rating FFA.
<color=#7FD4FF>Cartas</color> - La mano al acabar la partida.
  <color=#FF6666>+N sustituidas</color> cuenta elecciones
  expulsadas por el tope de cartas - pasa el cursor por
  la línea para ver cada elección en orden.

<color=#FFD94D><b>COLUMNAS DE LA CLASIFICACIÓN</b></color>

<color=#7FD4FF>Rank</color> - Posición en el orden seleccionado.
<color=#7FD4FF>Player</color> - Nombre visible del jugador.
<color=#7FD4FF>Rating</color> - Rating Glicko de FFA, separado.
<color=#7FD4FF>Games</color> - Partidas FFA registradas.
<color=#7FD4FF>Wins</color> - Partidas acabadas en 1.er puesto.
<color=#7FD4FF>Top3</color> - Partidas acabadas 1.ª, 2.ª o 3.ª.
<color=#7FD4FF>AvgPl</color> - Puesto final medio. Cuanto más bajo,
  mejor - 1.0 es ganar todas.
<color=#7FD4FF>WR</color> - Proporción de partidas ganadas.

<color=#FFD94D><b>OJO</b></color>

- Salir a mitad de partida queda registrado. Quien se va
  conserva sus números y se le coloca y puntúa en la
  partida que dejó - salvo que se fuera antes de que el
  campo anotara 2 medios puntos con su propio marcador
  aún a cero, en cuyo caso esa partida no le puntúa.$s256$)
  , ('7f82c46780cd1b48', 'ru', 'afb7bfc9b084206a7ffa2cc8b3d901c8516df3d3', $s256$Каждый сам за себя, 3-10 игроков. Каждый - своя команда.
Обычный счёт ROUNDS - игру берёт первый с {0} очками.

<color=#FFD94D><b>КАК ИГРАТЬ</b></color>

- Диапазона Elo нет. Вход в лобби - согласие играть.

- Создай лобби или войди в открытое из списка.
  ХОСТ жмёт Старт, когда внутри хотя бы 3 игрока
  (до 10). Открытых лобби может быть несколько.

- Если хост уходит, новым хостом автоматически
  становится тот, кто ждёт дольше всех.

- После каждого очка все, кроме взявшего очко,
  выбирают карту одновременно.

- Таймер выбора виден на экране. Выбор под самый
  конец даёт всем немного больше времени.
  Когда твой таймер дойдёт до нуля, подсвеченная
  карта будет выбрана за тебя автоматически - отход
  от клавиатуры никогда не пропускает твой пик. Без
  карты оставляет лишь пик, целиком не попавший в
  окно (фриз, краш или самое последнее мгновение), -
  с уведомлением об этом.

- У тебя может быть до {1} карт.
  Новая карта заменяет самую старую.

<color=#FFD94D><b>НАСТРОЙКИ ХОСТА</b></color>

- До старта хост может настроить лобби: цель по
  очкам (3-10), стартовые раздачи, карт в раздаче
  (1-5), лимит карт на руках (3-5 в рейтинге, до 6
  в казуале), правило «Те же карты» и рейтинг/казуал.

- Правило «Те же карты»: N-я раздача у всех предлагает
  ОДНИ И ТЕ ЖЕ карты в одном порядке - если вам с
  соперником всю игру давали одинаковые карты, итог
  не спишешь на удачу раздачи. Карты в одном
  экземпляре (например Phoenix) выпадают максимум
  раз за игру - на всех.

- После смены настроек лобби 60 секунд не может
  стартовать (и недолго после входа новичка), чтобы
  все успели прочитать изменения. Казуальные лобби
  платят меньше и не трогают рейтинг.

<color=#FFD94D><b>РЕЙТИНГ</b></color>

- FFA - рейтинговый режим со своим рейтингом Glicko.

- Место считают по очкам, потом по всем выигранным
  раундам (включая потраченные), потом по убийствам.
  Оставшиеся ничьи делят место по спортивному
  порядку: 1, 2, 2, 4.

- Твой рейтинг считается против ближайших к тебе по
  месту игроков (до 4), так что одна игра в лобби на
  10 человек не качнёт рейтинг в разы сильнее, чем в
  лобби на 3. К этой четвёрке может добавиться одно
  сравнение: самый большой разрыв рейтинга в 250+,
  закончившийся вверх ногами вне неё.

- Равное место считается ничьёй. Новый рейтинг
  двигается быстро и успокаивается с опытом.

<color=#FFD94D><b>НАГРАДЫ</b></color>

- Оплата меряется по БОРЬБЕ, а не по плоским суммам
  за игру: единица работы - решающие раунды, а время
  игры ограничивает скорость их оплаты - затяжка даёт
  лишь ограниченный выигрыш, а долгие крупные игры
  платят больше.

- Большие лобби платят лучше в пересчёте на минуту,
  а FFA на 10 игроков - лучший курс золота в игре.

- Место определяет долю: 1-е получает примерно
  впятеро больше последнего. Часть платится как XP,
  часть - как золото за место, а сильные соперники
  умножают банк (обычный бонус за тир).

- XP меняется на золото по курсу 100 XP = 1 золото, а
  новые уровни платят свой обычный бонус. Уровень,
  взятый прямо в игре, попадает в её +g - вот почему
  последнее место иногда зарабатывает больше
  победителя.

- Зрители могут ставить золото на лобби FFA с этой
  вкладки.

<color=#FFD94D><b>КАК ЧИТАТЬ СПИСОК НЕДАВНИХ FFA</b></color>

<color=#7FD4FF>Точки + N(P)</color> - Взятые полные очки.
<color=#7FD4FF>Полуточки + N(H)</color> - Выигранные раунды,
  не ставшие полным очком этого игрока.
<color=#7FD4FF>Nk</color> - Убийства.
<color=#7FD4FF>+xp +g</color> - XP и золото этой игры
  (включая бонус за уровень).
<color=#7FD4FF>Зелёное/красное число</color> - Изменение рейтинга FFA.
<color=#7FD4FF>Карты</color> - Рука на конец игры.
  <color=#FF6666>+N заменено</color> - выборы, вытесненные
  лимитом карт - наведи на строку, чтобы увидеть
  все выборы по порядку.

<color=#FFD94D><b>СТОЛБЦЫ ТАБЛИЦЫ</b></color>

<color=#7FD4FF>Rank</color> - Позиция в выбранной сортировке.
<color=#7FD4FF>Player</color> - Отображаемое имя игрока.
<color=#7FD4FF>Rating</color> - Отдельный рейтинг Glicko для FFA.
<color=#7FD4FF>Games</color> - Записанные игры FFA.
<color=#7FD4FF>Wins</color> - Игры, законченные на 1-м месте.
<color=#7FD4FF>Top3</color> - Игры с финишем на 1-м, 2-м или 3-м.
<color=#7FD4FF>AvgPl</color> - Среднее место на финише. Меньше -
  лучше: 1.0 значит победа в каждой игре.
<color=#7FD4FF>WR</color> - Доля игр, выигранных чисто.

<color=#FFD94D><b>НЮАНСЫ</b></color>

- Выход посреди игры записывается. Ушедший сохраняет
  свои счётчики, его расставляют и рейтингуют за
  игру, из которой он ушёл, - кроме случая, когда он
  ушёл до 2 набранных пол-очков поля при своём ещё
  нулевом счёте: тогда та игра его не рейтингует.$s256$)
  , ('7f82c46780cd1b48', 'sv', 'afb7bfc9b084206a7ffa2cc8b3d901c8516df3d3', $s256$Alla mot alla för 3-10 spelare. Varje spelare är sitt eget lag.
Vanlig ROUNDS-poängräkning - först till {0} poäng tar matchen.

<color=#FFD94D><b>SÅ SPELAR DU</b></color>

- Det finns inget Elo-spann. Att gå med i en lobby är samtycke till att spela.

- Skapa en lobby, eller gå med i en öppen via listan.
  VÄRDEN trycker på Starta när minst 3 spelare är inne
  (upp till 10). Flera lobbyer kan vara öppna samtidigt.

- Om värden lämnar blir den som väntat längst
  automatiskt ny värd.

- Efter varje poäng väljer alla utom poängvinnaren
  ett kort samtidigt.

- Valtimern visas på skärmen. Ett val nära slutet
  ger alla lite extra tid.
  När din timer når noll väljs ditt markerade kort
  automatiskt åt dig - att gå ifrån hoppar aldrig
  över ditt val. Bara ett val som helt missar
  fönstret (en frysning, en krasch eller den allra
  sista tiondelen) ger inget kort, med en avisering
  som säger det.

- Du håller upp till {1} kort.
  Väljer du ett till ersätts ditt äldsta kort.

<color=#FFD94D><b>VÄRDINSTÄLLNINGAR</b></color>

- Värden kan justera lobbyn före start: poängmål
  (3-10), startdragningar, kort per dragning (1-5),
  max antal kort (3-5 ranked, upp till 6 casual),
  regeln Samma kort samt ranked/casual.

- Regeln Samma kort: allas N:te kortdragning erbjuder
  SAMMA kandidater i samma ordning - om du och en rival
  fick identiska kort hela matchen kan inget resultat
  skyllas på dragningstur. Kort med ett exemplar (som Phoenix)
  dyker upp högst en gång per match - för alla.

- Efter en inställningsändring kan lobbyn inte starta på 60
  sekunder (och en kort stund efter att någon ny går med), så
  alla hinner läsa vad som ändrats. Casual-lobbyer ger
  lägre belöningar och rör aldrig ratingen.

<color=#FFD94D><b>RATING</b></color>

- FFA är rankat med en egen Glicko-rating.

- Placering avgörs av poäng, sedan alla vunna ronder
  (även förbrukade), sedan kills.
  Resterande oavgjorda delar plats enligt
  tävlingsordning: 1, 2, 2, 4.

- Din rating beräknas mot spelarna placerade
  närmast dig (upp till 4), så en match kan inte
  svänga din rating flera gånger hårdare i en lobby
  med 10 spelare än i en med 3. En extra jämförelse
  kan sälla sig till de fyra: det största ratinggapet
  på 250+ som slutade upp och ner utanför dem.

- Delad placering räknas som oavgjort. Nya ratingar
  ändras snabbt och stabiliseras ju mer du spelar.

<color=#FFD94D><b>BELÖNINGAR</b></color>

- Belöningen mäts efter STRIDEN, inte som fasta summor
  per match: avgörande ronder är beräkningsenheten, och
  speltiden sätter taket för hur snabbt de betalas ut -
  förhalning ger bara en begränsad fördel, och längre,
  större matcher ger mer.

- Större lobbyer ger bättre utdelning per minut, och en
  FFA med 10 spelare ger spelets bästa guldtakt.

- Din placering styr din andel: 1:an får ungefär
  fem gånger sistaplatsens andel. En del betalas i XP,
  en del i placeringsguld, och ett starkare motståndarfält
  multiplicerar potten (den vanliga tierbonusen).

- XP omvandlas till guld: 100 XP = 1 guld, och nya nivåer
  ger sitt vanliga bonusguld. En nivåhöjning under
  en match räknas in i matchens +g-siffra - det är
  därför en sista plats ibland kan tjäna mer än vinnaren.

- Åskådare kan satsa guld på FFA-lobbyer i den här fliken.

<color=#FFD94D><b>LÄSA LISTAN ÖVER SENASTE FFA</b></color>

<color=#7FD4FF>Prickar + N(P)</color> - Hela poäng som vunnits.
<color=#7FD4FF>Halvprickar + N(H)</color> - Rondvinster som
  inte blev ett av spelarens hela poäng.
<color=#7FD4FF>Nk</color> - Kills.
<color=#7FD4FF>+xp +g</color> - Matchens XP och guld
  (inklusive eventuell nivåbonus).
<color=#7FD4FF>Grön/röd siffra</color> - Ändring i FFA-rating.
<color=#7FD4FF>Kort</color> - Handen vid matchens slut.
  <color=#FF6666>+N ersatta</color> räknar kortval som
  trängts ut av korttaket - håll pekaren över raden
  för att se varje val i ordning.

<color=#FFD94D><b>TOPPLISTANS KOLUMNER</b></color>

<color=#7FD4FF>Rang</color> - Placering i den valda sorteringen.
<color=#7FD4FF>Spelare</color> - Spelarens visningsnamn.
<color=#7FD4FF>Rating</color> - Spelarens separata FFA-Glicko-rating.
<color=#7FD4FF>Matcher</color> - Registrerade FFA-matcher.
<color=#7FD4FF>Vinster</color> - Matcher avslutade på 1:a plats.
<color=#7FD4FF>Top3</color> - Matcher avslutade 1:a, 2:a eller 3:a.
<color=#7FD4FF>Snittpl.</color> - Genomsnittlig slutplacering. Lägre är
  bättre - 1.0 betyder vinst i varje match.
<color=#7FD4FF>WR</color> - Andel matcher som vunnits rakt av.

<color=#FFD94D><b>FALLGROPAR</b></color>

- Att lämna mitt i en match registreras. Den som lämnar
  behåller sina siffror och placeras och rankas för
  matchen som lämnades - såvida inte avhoppet skedde
  innan fältet gjort 2 halvpoäng och med egna siffror
  fortfarande på noll, för då rankas inte den matchen.$s256$)
  , ('7f82c46780cd1b48', 'uk', 'afb7bfc9b084206a7ffa2cc8b3d901c8516df3d3', $s256$Кожен сам за себе, 3-10 гравців. Кожен гравець - окрема команда.
Звичайний рахунок ROUNDS - гру бере перший, хто набере {0} очок.

<color=#FFD94D><b>ЯК ГРАТИ</b></color>

- Діапазону Elo немає. Вхід у лобі - згода грати.

- Створіть лобі або увійдіть у відкрите зі списку.
  ХОСТ натискає «Почати», щойно є щонайменше 3 гравці
  (до 10). Одночасно може бути кілька відкритих лобі.

- Якщо хост іде, новим хостом автоматично стає
  той, хто чекає найдовше.

- Після кожного очка всі, крім того, хто його взяв,
  обирають карту одночасно.

- Таймер вибору видно на екрані. Вибір під самий
  кінець дає всім трохи додаткового часу. Коли ваш
  таймер сягне нуля, підсвічену карту буде обрано за
  вас автоматично - відхід від клавіатури ніколи не
  пропускає ваш вибір. Без карти лишає тільки вибір,
  що повністю промахнувся повз вікно (фриз, краш або
  остання частка секунди), зі сповіщенням про це.

- Ви тримаєте до {1} карт.
  Ще один вибір замінює вашу найстарішу карту.

<color=#FFD94D><b>НАЛАШТУВАННЯ ХОСТА</b></color>

- До старту хост може налаштувати лобі: ціль за
  очками (3-10), стартові роздачі, карт на роздачу
  (1-5), ліміт карт (3-5 рейтингове, до 6
  звичайне), правило «Ті самі карти» і Ranked/звичайне.

- Правило «Ті самі карти»: N-та роздача у всіх пропонує
  ТІ САМІ карти в тому самому порядку - якщо вам і
  супернику всю гру пропонували однакові карти, результат
  не спишеш на удачу роздачі. Карти в одному екземплярі
  (як-от Phoenix) випадають щонайбільше раз за гру - всім.

- Після зміни налаштувань лобі не може стартувати
  60 секунд (і трохи після приходу новачка), щоб
  усі встигли прочитати зміни. Звичайні лобі дають
  менші нагороди й не змінюють рейтингів.

<color=#FFD94D><b>РЕЙТИНГ</b></color>

- FFA - рейтинговий режим із власним рейтингом Glicko.

- Місце визначають очки, далі всі виграні раунди
  (включно з витраченими), далі вбивства.
  Якщо нічия лишається, гравці ділять місце за
  змагальним порядком: 1, 2, 2, 4.

- Рейтинг рахується проти найближчих до вас за місцем
  гравців (до 4 із них), тож одна гра не хитне ваш
  рейтинг у лобі на 10 гравців у кілька разів сильніше,
  ніж у лобі на 3. До тих чотирьох може долучитись одне
  додаткове порівняння: найбільший розрив рейтингу 250+,
  що поза ними завершився догори дриґом.

- Однакове місце вважається нічиєю. Новий рейтинг
  швидко змінюється й стабілізується з грою.

<color=#FFD94D><b>НАГОРОДИ</b></color>

- Оплата міряється за БОРОТЬБОЮ, а не за фіксованими
  сумами за гру: одиниця роботи - вирішальні раунди,
  а час гри обмежує швидкість їх виплати - затягування
  дає лише обмежену вигоду, а довші й більші ігри
  платять більше.

- У більших лобі кращий курс за хвилину, а FFA на
  10 гравців - найкращий курс золота в грі.

- Місце визначає вашу частку: 1-ше отримує приблизно
  вп’ятеро більше за останнє. Частина видається як XP,
  частина - як золото за місце, а сильніший склад
  суперників множить банк (звичний бонус за рівень).

- XP конвертується в золото за курсом 100 XP = 1 золото,
  а нові рівні платять звичний бонус золотом. Рівень,
  узятий просто під час гри, потрапляє в її +g - ось
  чому останнє місце інколи заробляє більше за переможця.

- Глядачі можуть ставити золото на лобі FFA з цієї вкладки.

<color=#FFD94D><b>ЯК ЧИТАТИ СПИСОК НЕДАВНІХ FFA</b></color>

<color=#7FD4FF>Крапки + N(P)</color> - Здобуті повні очки.
<color=#7FD4FF>Півкрапки + N(H)</color> - Виграні раунди,
  що не стали повним очком цього гравця.
<color=#7FD4FF>Nk</color> - Убивства.
<color=#7FD4FF>+xp +g</color> - XP і золото цієї гри
  (включно з бонусом за рівень).
<color=#7FD4FF>Зелене/червоне число</color> - Зміна рейтингу FFA.
<color=#7FD4FF>Карти</color> - Рука на кінець гри.
  <color=#FF6666>+N замінено</color> - вибори, витіснені
  лімітом карт - наведіть на рядок, щоб побачити
  всі вибори по порядку.

<color=#FFD94D><b>СТОВПЦІ ТАБЛИЦІ ЛІДЕРІВ</b></color>

<color=#7FD4FF>Ранг</color> - Позиція в поточному сортуванні.
<color=#7FD4FF>Гравець</color> - Видиме ім’я гравця.
<color=#7FD4FF>Рейтинг</color> - Окремий рейтинг Glicko для FFA.
<color=#7FD4FF>Ігри</color> - Записані зіграні ігри FFA.
<color=#7FD4FF>Перемоги</color> - Ігри, завершені на 1-му місці.
<color=#7FD4FF>Top3</color> - Ігри з фінішем на 1-му, 2-му чи 3-му.
<color=#7FD4FF>Сер. місце</color> - Середнє фінішне місце. Менше -
  краще: 1.0 означає перемогу в кожній грі.
<color=#7FD4FF>WR</color> - Частка ігор, виграних одноосібно.

<color=#FFD94D><b>НЮАНСИ</b></color>

- Вихід посеред гри записується. Той, хто вийшов,
  зберігає показники, і його розставляють та рейтингують
  за гру, яку він покинув, - хіба що він вийшов до
  2 набраних полем половинок очок із власним ще нульовим
  підсумком: тоді та гра його не рейтингує.$s256$)
  , ('89f91f91fd4ef06f', 'es', 'b2548c95d5dfdc947754eb8e7d9bd831b3c9f3e1', $s256$<color=#FFD94D><b>DAÑO PROPIO VS DAÑO AL RIVAL</b></color>

De la tabla queda bastante claro que la mayoría del daño cae en dos categorías: daño infligido a tu rival y daño infligido a ti mismo. El daño a tu rival activará casi siempre todas las cartas y buffs, mientras que el daño a ti mismo solo activará jamás Scavenger. Este fundamento se mantiene sea daño directo de balas, efectos de área o incluso efectos de nicho como el drenaje de vida de Demonic Pact.

<color=#FFD94D><b>RAREZAS</b></color>

- <color=#7FE87F>Abyssal Countdown</color> - pese a infligir daño de área directo a un rival, nunca activará ninguna carta ni buff. Ni siquiera Scavenger. Es único en esto.
- <color=#7FE87F>Brawler</color> - por la razón que sea, el efecto de partículas de Brawler se activa con el daño propio, pese a que Brawler no se activa de verdad. Posiblemente algo que agradecería un arreglo de Sid.
- <color=#7FE87F>Demonic Pact</color> - de forma única, su área no afecta al usuario. Para equilibrarlo y evitar acumulación de daño, el área tiene un escalado de daño y knockback terrible, aunque no del todo inexistente. Su daño de drenaje se aplica antes del disparo, no después, con lo que al jugador siempre le falta una bala pese a no poder quedarse sin munición (salvo que acumular Combine lo reduzca a una sola bala en el cargador - imposible sin superar el máximo de cartas, y por tanto irrelevante). Y Scavenger se activa igualmente aunque el jugador no pierda vida de verdad por la prevención de muerte.
- <color=#7FE87F>Life Stealer</color> - igual que con Demonic Pact, todas las cartas y buffs correspondientes se activan aunque no se drene vida de verdad por la prevención de muerte. Esto incluye el robo de vida: parece que el robo de vida se calcula desde el daño máximo que podría aplicarse, no desde la bajada real de vida. Más pruebas con daño de bala excesivo y Leech lo confirman. El daño por ticks como el de Parasite, en cambio, no dará el retorno máximo de robo de vida al morir el objetivo. Algo a tener en cuenta en FFA o contra Phoenix.

<color=#FFD94D><b>REFRESH Y EL DAÑO CONDICIONAL</b></color>

Llegamos al daño Condicional. En pocas palabras, el daño Condicional 'equilibra' Refresh, de modo que nunca puedes activar dos Refresh seguidos con daño Condicional. De mi investigación ha quedado claro que cada jugador guarda un valor booleano invisible que llamaré RefreshValid. Como booleano puede ocupar dos estados, true o false. Cuando RefreshValid es true, la próxima vez que infliges daño Condicional obtienes un Refresh exitoso, pero RefreshValid pasa entonces a false. Si infliges daño Condicional con RefreshValid en false, no recibes Refresh - pero RefreshValid vuelve a true, así que tu siguiente instancia de daño Condicional activará uno. Tener ya un bloqueo listo, y por tanto no necesitar un Refresh, no influye en este vaivén.

Las ramificaciones de gameplay se ilustran mejor con Silence. Al empezar una partida, RefreshValid está en false, así que tu primer Silence no logra activar un Refresh. (No he podido probar si el booleano se reinicia entre rondas - no se reinicia al morir, al resucitar ni al elegir cartas nuevas, así que sospecho que no.) Tras tu primer Refresh fallido, RefreshValid queda en true. Así, tu siguiente Silence activa un Refresh pero devuelve RefreshValid a false. Y sigue en un bucle sin fin donde un Silence de cada dos activa un Refresh exitoso. Cada columna de abajo es una acción; la fila superior es el estado de RefreshValid ANTES de ella:

<color=#FFD94D>RefreshValid</color><pos=30%>False<pos=44%>True<pos=58%>False<pos=72%>True<pos=86%>False
<color=#FFD94D>Acción</color><pos=30%>Silence<pos=44%>Silence<pos=58%>Silence<pos=72%>Silence<pos=86%>Silence
<color=#FFD94D>¿Refresh?</color><pos=30%>No<pos=44%>Sí<pos=58%>No<pos=72%>Sí<pos=86%>No

Sin embargo, esto es si solo usas Silence. Otros activadores de Refresh pueden romper el patrón alterno: dale a tu rival con una bala (daño no Condicional) y recibes un Refresh exitoso Y devuelves RefreshValid a false. Según dónde coloques tu disparo dentro del patrón, puedes arañar un Refresh extra:

<color=#FFD94D>RefreshValid</color><pos=30%>False<pos=44%>True<pos=58%>False<pos=72%>True<pos=86%>False
<color=#FFD94D>Acción</color><pos=30%>Silence<pos=44%>Disparo<pos=58%>Silence<pos=72%>Silence<pos=86%>Silence
<color=#FFD94D>¿Refresh?</color><pos=30%>No<pos=44%>Sí<pos=58%>No<pos=72%>Sí<pos=86%>No

<color=#FFD94D>RefreshValid</color><pos=30%>False<pos=44%>True<pos=58%>False<pos=72%>False<pos=86%>True
<color=#FFD94D>Acción</color><pos=30%>Silence<pos=44%>Silence<pos=58%>Disparo<pos=72%>Silence<pos=86%>Silence
<color=#FFD94D>¿Refresh?</color><pos=30%>No<pos=44%>Sí<pos=58%>Sí<pos=72%>No<pos=86%>Sí

Por desgracia, este no es el final del documento, porque los desarrolladores de ROUNDS tuvieron a bien introducir otra mecánica más. Espero, querido lector, que aprecies la relativa facilidad con la que posees esta información, comparada con las horas de locura que pasé obteniéndola.$s256$)
  , ('89f91f91fd4ef06f', 'ru', 'b2548c95d5dfdc947754eb8e7d9bd831b3c9f3e1', $s256$<color=#FFD94D><b>УРОН СЕБЕ И УРОН СОПЕРНИКУ</b></color>

Из таблицы довольно ясно, что большая часть урона делится на две категории: урон сопернику и урон себе. Урон сопернику почти всегда запускает все карты и баффы, тогда как урон себе запускает разве что Scavenger. Эта основа верна для урона напрямую от пуль, от AoE-эффектов и даже для нишевых эффектов вроде вытяжки жизни Demonic Pact.

<color=#FFD94D><b>СТРАННОСТИ</b></color>

- <color=#7FE87F>Abyssal Countdown</color> - хотя он наносит сопернику прямой AoE-урон, он никогда не запускает никакие карты и баффы. Даже Scavenger. В этом он уникален.
- <color=#7FE87F>Brawler</color> - по какой-то причине партикл-эффект Brawler активируется при уроне себе, хотя по-настоящему Brawler не срабатывает. Возможно, нечто, что оценило бы фикс от Sid.
- <color=#7FE87F>Demonic Pact</color> - уникально: его AoE не задевает владельца. Для баланса и защиты от стака урона у этого AoE ужасный, хотя и не совсем нулевой, скейлинг урона и отброса. Урон его вытяжки применяется до выстрела, а не после, то есть игроку всегда не хватает одной пули, хотя патроны у него кончиться не могут (если только стак Combine не сведёт обойму к единственной пуле - что невозможно без превышения лимита карт, а потому неважно). А Scavenger всё равно активируется, даже когда игрок фактически не теряет здоровья из-за защиты от смерти.
- <color=#7FE87F>Life Stealer</color> - как и у Demonic Pact, все подходящие карты и баффы активируются, даже если здоровье фактически не вытянуто из-за защиты от смерти. Включая вампиризм: похоже, вампиризм считается от максимального урона, который мог быть нанесён, а не от фактической убыли здоровья. Дальнейшие тесты с избыточным уроном пуль и Leech это подтверждают. Тиковый урон вроде Parasite, однако, не даст максимального возврата вампиризма при смерти. Стоит помнить в FFA или против Phoenix.

<color=#FFD94D><b>REFRESH И УСЛОВНЫЙ УРОН</b></color>

Теперь перейдём к условному урону. Проще говоря, условный урон «балансирует» Refresh так, что условным уроном нельзя запустить два Refresh подряд. Из моих исследований стало ясно, что каждый игрок держит невидимое булево значение, которое я назову RefreshValid. Как булево оно занимает два состояния, true или false. Когда RefreshValid равен true, следующий условный урон даёт успешный Refresh, но RefreshValid переключается в false. Если нанести условный урон при RefreshValid равном false, Refresh ты не получаешь - но RefreshValid переключается обратно в true, так что следующая порция условного урона его запустит. Уже готовый блок, которому Refresh не нужен, на это переключение никак не влияет.

Игровые последствия лучше всего показывает Silence. В начале игры RefreshValid установлен в false, так что твой первый Silence не запускает Refresh. (Проверить, сбрасывается ли бул между раундами, я не смог - он не сбрасывается при смерти, воскрешении и новых пиках карт, так что подозреваю, что нет.) После первого несработавшего Refresh RefreshValid ставится в true. Значит, следующий Silence запускает Refresh, но сбрасывает RefreshValid в false. Так и продолжается бесконечный цикл, где каждый второй Silence запускает успешный Refresh. Каждый столбец ниже - одно действие; верхняя строка - состояние RefreshValid ПЕРЕД ним:

<color=#FFD94D>RefreshValid</color><pos=30%>False<pos=44%>True<pos=58%>False<pos=72%>True<pos=86%>False
<color=#FFD94D>Действие</color><pos=30%>Silence<pos=44%>Silence<pos=58%>Silence<pos=72%>Silence<pos=86%>Silence
<color=#FFD94D>Refresh?</color><pos=30%>Нет<pos=44%>Да<pos=58%>Нет<pos=72%>Да<pos=86%>Нет

Однако это если пользоваться одним лишь Silence. Другие активаторы Refresh могут сломать шахматный порядок: попади в соперника пулей (безусловный урон) - и ты получаешь успешный Refresh И сбрасываешь RefreshValid в false. В зависимости от того, куда в паттерне вставить выстрел, можно урвать лишний Refresh:

<color=#FFD94D>RefreshValid</color><pos=30%>False<pos=44%>True<pos=58%>False<pos=72%>True<pos=86%>False
<color=#FFD94D>Действие</color><pos=30%>Silence<pos=44%>Выстрел<pos=58%>Silence<pos=72%>Silence<pos=86%>Silence
<color=#FFD94D>Refresh?</color><pos=30%>Нет<pos=44%>Да<pos=58%>Нет<pos=72%>Да<pos=86%>Нет

<color=#FFD94D>RefreshValid</color><pos=30%>False<pos=44%>True<pos=58%>False<pos=72%>False<pos=86%>True
<color=#FFD94D>Действие</color><pos=30%>Silence<pos=44%>Silence<pos=58%>Выстрел<pos=72%>Silence<pos=86%>Silence
<color=#FFD94D>Refresh?</color><pos=30%>Нет<pos=44%>Да<pos=58%>Да<pos=72%>Нет<pos=86%>Да

Увы, это не конец документа, потому что разработчики ROUNDS сочли нужным ввести ещё одну механику. Надеюсь, ты, дорогой читатель, ценишь ту относительную лёгкость, с которой получаешь эту информацию, - в сравнении с часами безумия, потраченными мной на её добычу.$s256$)
  , ('89f91f91fd4ef06f', 'sv', 'b2548c95d5dfdc947754eb8e7d9bd831b3c9f3e1', $s256$<color=#FFD94D><b>SJÄLVSKADA KONTRA MOTSTÅNDARSKADA</b></color>

Av tabellen framgår det ganska tydligt att det mesta av skadan faller i två kategorier: skada på din motståndare och skada på dig själv. Skada på din motståndare utlöser nästan alltid alla kort och buffar, medan skada på dig själv bara någonsin utlöser Scavenger. Denna grundprincip håller vare sig det gäller skada direkt från kulor, AoE-effekter, eller till och med nischeffekter som Demonic Pacts livsdränering.

<color=#FFD94D><b>EGENHETER</b></color>

- <color=#7FE87F>Abyssal Countdown</color> - trots att det gör direkt AoE-skada på en motståndare utlöser det aldrig några kort eller buffar. Inte ens Scavenger. Det är unikt i detta.
- <color=#7FE87F>Brawler</color> - av någon anledning aktiveras partikeleffekten på Brawler vid självskada, trots att Brawler inte aktiveras på riktigt. Möjligen något som skulle uppskatta en fix från Sid.
- <color=#7FE87F>Demonic Pact</color> - unikt nog påverkar dess AoE inte användaren. För att balansera detta och förhindra skadestapling har AoE:n urusel, om än inte helt obefintlig, skade- och knockbackskalning. Dess dräneringsskada tillämpas före skottet, inte efter, vilket betyder att spelaren alltid saknar en kula trots att ammunitionen inte kan ta slut (om inte Combine-stapling reducerar dem till en enda kula i magasinet - omöjligt utan att överskrida kortmaximum, och därmed irrelevant). Och Scavenger aktiveras ändå även när spelaren faktiskt inte förlorar någon hälsa tack vare dödsprevention.
- <color=#7FE87F>Life Stealer</color> - i likhet med Demonic Pact aktiveras alla tillämpliga kort och buffar även om ingen hälsa faktiskt dräneras tack vare dödsprevention. Detta inkluderar lifesteal: det verkar som att lifesteal beräknas från den maximala skada som kunde ha tillämpats, inte den faktiska hälsominskningen. Vidare tester med overkill-kulskada och Leech bekräftar detta. Tickskada som Parasite ger dock inte maximal lifesteal-avkastning vid död. Något att vara medveten om i FFA eller mot Phoenix.

<color=#FFD94D><b>REFRESH OCH VILLKORLIG SKADA</b></color>

Nu kommer vi till Villkorlig skada. Enkelt uttryckt 'balanserar' Villkorlig skada Refresh, så att du aldrig kan utlösa två Refresh i rad med Villkorlig skada. Från min forskning har det blivit tydligt att varje spelare bär på ett osynligt booleskt värde som jag kallar RefreshValid. Som boolesk kan det anta två tillstånd, sant eller falskt. När RefreshValid är sant får du en lyckad Refresh nästa gång du gör Villkorlig skada, men RefreshValid slår då om till falskt. Gör du Villkorlig skada medan RefreshValid är falskt får du ingen Refresh - men RefreshValid slår tillbaka till sant, så din nästa instans av Villkorlig skada utlöser en. Att redan ha ett block redo, och alltså inte behöva en Refresh, påverkar inte detta omslående.

Spelkonsekvenserna illustreras bäst genom Silence. Vid matchstart är RefreshValid satt till falskt, så din första Silence misslyckas att utlösa en Refresh. (Jag har inte kunnat testa om boolen nollställs mellan ronder - den nollställs inte vid död, återuppståndelse eller nya kortval, så jag misstänker att den inte gör det.) Efter din första misslyckade Refresh sätts RefreshValid till sant. Alltså utlöser din nästa Silence en Refresh men nollställer RefreshValid till falskt. Så fortsätter det i en ändlös loop där varannan Silence utlöser en lyckad Refresh. Varje kolumn nedan är en handling; översta raden är RefreshValid-tillståndet FÖRE den:

<color=#FFD94D>RefreshValid</color><pos=30%>Falskt<pos=44%>Sant<pos=58%>Falskt<pos=72%>Sant<pos=86%>Falskt
<color=#FFD94D>Handling</color><pos=30%>Silence<pos=44%>Silence<pos=58%>Silence<pos=72%>Silence<pos=86%>Silence
<color=#FFD94D>Refresh?</color><pos=30%>Nej<pos=44%>Ja<pos=58%>Nej<pos=72%>Ja<pos=86%>Nej

Men detta gäller om du enbart använder Silence. Andra Refresh-aktiverare kan störa varannan-mönstret: träffa din motståndare med en kula (icke-Villkorlig skada) så får du en lyckad Refresh OCH nollställer RefreshValid till falskt. Beroende på var i mönstret du placerar ditt skott kan du knipa en extra Refresh:

<color=#FFD94D>RefreshValid</color><pos=30%>Falskt<pos=44%>Sant<pos=58%>Falskt<pos=72%>Sant<pos=86%>Falskt
<color=#FFD94D>Handling</color><pos=30%>Silence<pos=44%>Skjut<pos=58%>Silence<pos=72%>Silence<pos=86%>Silence
<color=#FFD94D>Refresh?</color><pos=30%>Nej<pos=44%>Ja<pos=58%>Nej<pos=72%>Ja<pos=86%>Nej

<color=#FFD94D>RefreshValid</color><pos=30%>Falskt<pos=44%>Sant<pos=58%>Falskt<pos=72%>Falskt<pos=86%>Sant
<color=#FFD94D>Handling</color><pos=30%>Silence<pos=44%>Silence<pos=58%>Skjut<pos=72%>Silence<pos=86%>Silence
<color=#FFD94D>Refresh?</color><pos=30%>Nej<pos=44%>Ja<pos=58%>Ja<pos=72%>Nej<pos=86%>Ja

Tyvärr är detta inte slutet på dokumentet, eftersom ROUNDS-utvecklarna fann för gott att införa ytterligare en mekanik. Jag hoppas verkligen att du, kära läsare, uppskattar den relativa lätthet med vilken du får ta del av denna information, jämfört med de timmar av vansinne jag lade på att skaffa den.$s256$)
  , ('89f91f91fd4ef06f', 'uk', 'b2548c95d5dfdc947754eb8e7d9bd831b3c9f3e1', $s256$<color=#FFD94D><b>ШКОДА СОБІ ПРОТИ ШКОДИ СУПЕРНИКУ</b></color>

Із таблиці доволі ясно, що більшість шкоди падає у дві категорії: шкода, завдана суперникові, і шкода, завдана собі. Шкода суперникові майже завжди тригерить усі карти й бафи, тоді як шкода собі тригерить лише Scavenger і більше нічого. Ця основа тримається незалежно від того, чи йде шкода прямо від куль, від AoE-ефектів, чи навіть від нішевих ефектів на кшталт висмоктування життя Demonic Pact.

<color=#FFD94D><b>ДИВИНИ</b></color>

- <color=#7FE87F>Abyssal Countdown</color> - попри пряму AoE-шкоду суперникові, він ніколи не тригерить жодних карт чи бафів. Навіть Scavenger. У цьому він унікальний.
- <color=#7FE87F>Brawler</color> - чомусь ефект частинок, причеплений до Brawler, активується на шкоді собі, хоча сам Brawler по-справжньому не активується. Потенційно те, що Sid міг би полагодити.
- <color=#7FE87F>Demonic Pact</color> - унікально, його AoE не зачіпає користувача. Щоб урівноважити це й запобігти стаканню шкоди, AoE має жахливе, хоч і не повністю нульове, масштабування шкоди й відкидання. Його шкода-плата застосовується перед пострілом, не після, тобто гравцеві завжди бракує однієї кулі, хоч закінчитися набої не можуть (хіба що стакання Combine зведе магазин до однієї кулі - неможливо без перевищення ліміту карт, тож неактуально). А Scavenger усе одно активується, навіть коли гравець фактично не втрачає здоров’я через захист від смерті.
- <color=#7FE87F>Life Stealer</color> - подібно до Demonic Pact, усі належні карти й бафи активуються, навіть якщо через захист від смерті здоров’я фактично не витягнуто. Це стосується і лайфстілу: схоже, лайфстіл рахується від максимальної шкоди, яку можна було б завдати, а не від фактичного зменшення здоров’я. Подальші тести з надлишковою шкодою куль і Leech це підтверджують. А от тікова шкода на кшталт Parasite максимального повернення лайфстілу на смерті не дасть. Варто пам’ятати у FFA чи проти Phoenix.

<color=#FFD94D><b>REFRESH І УМОВНА ШКОДА</b></color>

Тепер про Умовну шкоду. Простими словами, Умовна шкода «балансує» Refresh так, що Умовною шкодою ніколи не тригернути два Refresh поспіль. З моїх досліджень стало ясно, що кожен гравець тримає невидиме булеве значення, яке я зватиму RefreshValid. Як булеве, воно має два стани: true або false. Коли RefreshValid true, наступна ваша Умовна шкода дає успішний Refresh, але RefreshValid перемикається у false. Якщо ви завдаєте Умовної шкоди, коли RefreshValid false, Refresh ви не отримуєте - але RefreshValid повертається у true, тож ваш наступний випадок Умовної шкоди його тригерне. Те, що блок уже готовий і Refresh вам не потрібен, на це перемикання не впливає.

Ігрові наслідки найкраще ілюструє Silence. На початку гри RefreshValid стоїть у false, тож ваш перший Silence не тригерить Refresh. (Мені не вдалося перевірити, чи скидається бул між раундами - на смерті, воскресінні чи нових виборах карт він не скидається, тож підозрюю, що ні.) Після першого невдалого Refresh RefreshValid стає true. Тож ваш наступний Silence тригерить Refresh, але скидає RefreshValid у false. Так воно й крутиться нескінченною петлею, де кожен другий Silence дає успішний Refresh. Кожна колонка нижче - одна дія; верхній рядок - стан RefreshValid ПЕРЕД нею:

<color=#FFD94D>RefreshValid</color><pos=30%>False<pos=44%>True<pos=58%>False<pos=72%>True<pos=86%>False
<color=#FFD94D>Дія</color><pos=30%>Silence<pos=44%>Silence<pos=58%>Silence<pos=72%>Silence<pos=86%>Silence
<color=#FFD94D>Refresh?</color><pos=30%>Ні<pos=44%>Так<pos=58%>Ні<pos=72%>Так<pos=86%>Ні

Але це якщо користуватися самим лише Silence. Інші активатори Refresh можуть зламати патерн «кожен другий»: влучіть у суперника кулею (неумовна шкода) - і ви отримаєте успішний Refresh ТА скинете RefreshValid у false. Залежно від того, куди в патерні поставити постріл, можна вихопити зайвий Refresh:

<color=#FFD94D>RefreshValid</color><pos=30%>False<pos=44%>True<pos=58%>False<pos=72%>True<pos=86%>False
<color=#FFD94D>Дія</color><pos=30%>Silence<pos=44%>Постріл<pos=58%>Silence<pos=72%>Silence<pos=86%>Silence
<color=#FFD94D>Refresh?</color><pos=30%>Ні<pos=44%>Так<pos=58%>Ні<pos=72%>Так<pos=86%>Ні

<color=#FFD94D>RefreshValid</color><pos=30%>False<pos=44%>True<pos=58%>False<pos=72%>False<pos=86%>True
<color=#FFD94D>Дія</color><pos=30%>Silence<pos=44%>Silence<pos=58%>Постріл<pos=72%>Silence<pos=86%>Silence
<color=#FFD94D>Refresh?</color><pos=30%>Ні<pos=44%>Так<pos=58%>Так<pos=72%>Ні<pos=86%>Так

На жаль, це не кінець документа, бо розробники ROUNDS визнали за потрібне ввести ще один механізм. Сподіваюся, ви, любий читачу, цінуєте відносну легкість, з якою отримуєте цю інформацію, порівняно з годинами божевілля, витраченими на її здобуття.$s256$)
  , ('910f67b5efb72a02', 'es', '1f26a904194291df57645321da8a65d06c1b48d2', $s256$Cosméticos e identidad$s256$)
  , ('910f67b5efb72a02', 'ru', '1f26a904194291df57645321da8a65d06c1b48d2', $s256$Косметика и образ$s256$)
  , ('910f67b5efb72a02', 'sv', '1f26a904194291df57645321da8a65d06c1b48d2', $s256$Kosmetik & identitet$s256$)
  , ('910f67b5efb72a02', 'uk', '1f26a904194291df57645321da8a65d06c1b48d2', $s256$Косметика та ідентичність$s256$)
  , ('9568055ad9672251', 'es', 'c801ffbe17db6bee98ea4167dbe677e5af7def51', $s256$El ranked solo funciona si se puede confiar en los resultados. La versión corta: cada reporte va firmado y con identidad verificada, los clientes de ambos jugadores reúnen pruebas el uno del otro, los detectores marcan para revisión humana en vez de castigar solos (un patrón estrecho de farmeo es la única excepción), y una persona toma la decisión final.

<color=#FFD94D><b>DETECCIÓN DE MACROS</b></color>

- Tu cliente muestrea el input de juego cada fotograma - movimiento, disparo, bloqueo - solo mientras estás vivo en combate activo, nunca mientras escribes o estás en menús.
- El input sostenido muy por encima del ritmo de cualquier humano se registra como ventanas sospechosas con tasas por segundo exactas y picos por partida.
- AMBOS jugadores guardan las pruebas. Cada cliente publica sus contadores al otro durante la partida, así el reporte lleva también las ventanas del rival - y en 1v1 un cliente con pruebas serias las presenta además directamente al servidor, firmadas, para que sobrevivan aunque la copia de quien reporta esté vieja o perdida.
- Las fusiones de pruebas solo pueden reforzar: un envío posterior nunca puede debilitar picos o ventanas ya capturados. Si una alerta ya fue revisada, las pruebas nuevas abren una revisión fresca en vez de editar la decidida.
- Los sospechosos de macro marcados se excluyen en silencio del grupo de jugadores similares de la pestaña Comparar hasta quedar limpios - un perfil de input con macro envenenaría las comparaciones de todos.

<color=#FFD94D><b>DETECCIÓN DE AFK</b></color>

- Quien reporta un 1v1 con cero disparos, cero bloqueos y cero elecciones de carta en una partida de más de dos minutos queda marcado. La comprobación de cartas es la que soporta el peso: las builds pacifistas y de melé terminan partidas legítimamente sin disparar una bala, pero nadie elige cero cartas estando al teclado.

<color=#FFD94D><b>RITMOS IMPOSIBLES</b></color>

- Los speedhacks aceleran el reloj del propio cliente, así que el servidor nunca se fía de las duraciones reportadas. Mide el tiempo real entre llegadas de reportes con su propio reloj; una serie que llega más rápido de lo que físicamente pueden jugarse las partidas queda marcada, con los intervalos exactos guardados para revisión.
- La única sanción automática de todo el sistema: un patrón repetido de partidas inverosímilmente cortas entre los mismos dos jugadores se invalida de plano, partidas anteriores del patrón incluidas - oro y XP revertidos, series anuladas. Todo lo demás de esta página marca para revisión humana.
- Los FPS crónicamente bajos y las conexiones ásperas se juzgan contra TU PROPIO historial reciente, así que una máquina que siempre va así nunca se marca; los bajones repentinos y convenientes se juzgan contra lo normal de esa misma partida.

<color=#FFD94D><b>FIRMADO, DEDUPLICADO, EN CUARENTENA</b></color>

- Cada reporte de partida va firmado y con identidad verificada: quien reporta debe ser participante de la partida y tener la sesión de Steam viva de esa cuenta. <color=#7FE87F>Nadie puede reportar COMO tú</color> - y nada que reporte otro puede poner un número en las tablas de récords bajo tu nombre.
- Cada partida puede registrarse exactamente una vez. Los duplicados y las repeticiones se absorben - el servidor devuelve el resultado ya registrado y nada paga dos veces.
- Un reporte de equipo o FFA que llega para una sala cerrada entra en cuarentena para revisión de admin, ni se confía en él ni se descarta en silencio.

<color=#FFD94D><b>NADIE PUEDE PLANTAR DATOS BAJO TU NOMBRE</b></color>

- Las tablas de récords solo muestran filas de los reportes PROPIOS de cada jugador, así que el cliente de un rival no puede poner un número bajo tu nombre envíe lo que envíe.
- Los récords de robo de cartas funcionan igual: un reporte cuenta solo para el asiento de quien reporta en la tabla de los Más afortunados.
- Lo peor que puede hacer un cliente modificado es mentir sobre SÍ MISMO - y los números autoreportados son exactamente lo que vigilan los detectores de patrones, siguen siendo orientativos hasta que un humano los revisa, y son reversibles después.

<color=#FFD94D><b>CIERRES DE APUESTAS</b></color>

- Las apuestas se cierran en cuanto existe información real. En 1v1 y 2v2 son 2 puntos anotados en el juego 1, o cualquier juego de la serie decidido; en FFA son 2 puntos entre todo el campo en la partida actual (1 en una sala a 3).
- El cierre lo impone el servidor al colocar la apuesta, no solo se oculta en el menú. No puedes apostar en tu propia partida, y es una apuesta por serie (por partida en FFA) por jugador.

<color=#FFD94D><b>REVISIÓN HUMANA</b></color>

- Cada alerta aterriza delante de un admin con sus pruebas exactas - para una alerta de macro, las ventanas, los picos y ambas fuentes.
- Un veredicto queda ligado a las pruebas exactas que el admin revisó. Si llegan pruebas más fuertes a mitad de revisión, la revisión se rehace contra ellas - una lectura vieja no puede decidir una alerta.
- Un veredicto de falso positivo sobre algo autoinvalidado dispara una reparación registrada del oro y el rating afectados.
- Un veredicto confirmado no dispara una sanción automática. La ejecución pasa por herramientas de admin separadas y auditadas una a una: bans y reversión de series. Un ban corta el acceso en vivo de inmediato - sesiones revocadas, colas bloqueadas, ranked rechazado - y si alguna vez te emparejas con un jugador baneado, tu cliente se va automáticamente con un aviso.$s256$)
  , ('9568055ad9672251', 'ru', 'c801ffbe17db6bee98ea4167dbe677e5af7def51', $s256$Рейтинг работает, только если результатам можно доверять. Коротко: каждый отчёт подписан и проверен по личности, клиенты обоих игроков собирают доказательства друг о друге, детекторы отправляют флаги на проверку человеку, а не наказывают сами (единственное исключение - один узкий паттерн фарма), и финальное решение принимает человек.

<color=#FFD94D><b>ДЕТЕКЦИЯ МАКРОСОВ</b></color>

- Твой клиент снимает игровой ввод каждый кадр - движение, огонь, блок - только пока ты жив в активном бою, и никогда во время печати или в меню.
- Устойчивый ввод, далеко превышающий человеческий темп, записывается как подозрительные окна с точными посекундными частотами и пиками за матч.
- Доказательства держат ОБА игрока. Каждый клиент публикует свои счётчики другому во время матча, так что отчёт несёт и окна соперника, - а в 1v1 клиент с серьёзными доказательствами ещё и отправляет их серверу напрямую, подписанными, чтобы они выжили, даже когда копия репортёра устарела или потерялась.
- Слияние доказательств может только усиливать: поздняя отправка никогда не ослабит уже зафиксированные пики и окна. Если флаг уже рассмотрен, новые доказательства открывают свежую проверку вместо правки решённой.
- Флагнутые как подозреваемые в макросах тихо исключаются из пула похожих игроков вкладки Сравнение до снятия подозрения - макросный профиль ввода отравил бы сравнения всем.

<color=#FFD94D><b>ДЕТЕКЦИЯ AFK</b></color>

- Репортёр 1v1 с нулём выстрелов, нулём блоков и нулём пиков карт за матч длиннее двух минут получает флаг. Несущая проверка - карты: пацифистские и ближнебойные билды честно заканчивают игры без единой пули, но никто не выбирает ноль карт, сидя за клавиатурой.

<color=#FFD94D><b>НЕВОЗМОЖНЫЙ ТЕМП</b></color>

- Спидхаки ускоряют собственные часы клиента, поэтому сервер никогда не доверяет длительностям из отчётов. Он меряет стеночное время между приходами отчётов по собственным часам; серия, приходящая быстрее, чем игры физически играются, флажится, с точными интервалами для проверки.
- Единственное автоматическое наказание во всей системе: повторяющийся паттерн неправдоподобно коротких матчей между одними и теми же двумя игроками инвалидируются сразу, включая ранние игры паттерна, - золото и XP отматываются, серии аннулируются. Всё остальное на этой странице - флаг на проверку человеком.
- Хронически низкий FPS и шероховатые соединения судятся по ТВОЕЙ СОБСТВЕННОЙ недавней истории, так что машина, всегда работающая так, не флажится никогда; внезапные удобные просадки судятся по норме того же матча.

<color=#FFD94D><b>ПОДПИСАНО, ДЕДУПЛИЦИРОВАНО, В КАРАНТИНЕ</b></color>

- Каждый отчёт о матче подписан и проверен по личности: репортёр должен быть участником матча и держать живую Steam-сессию этого аккаунта. <color=#7FE87F>Никто не может отправить отчёт ЗА тебя</color> - и ничей чужой отчёт не может положить число на доски рекордов под твоим именем.
- Каждая игра записывается ровно один раз. Дубли и повторы поглощаются - сервер возвращает уже записанный результат, и ничто не платится дважды.
- Командный или FFA-отчёт, пришедший для закрытого лобби, отправляется в карантин на проверку админом - не принимается на веру и не отбрасывается молча.

<color=#FFD94D><b>НИКТО НЕ ПОДЛОЖИТ ДАННЫЕ ПОД ТВОЁ ИМЯ</b></color>

- Доски рекордов показывают только строки из СОБСТВЕННЫХ отчётов игрока, так что клиент соперника не может положить число под твоё имя, что бы он ни отправил.
- Рекорды раздач карт работают так же: отчёт считается только за собственное место репортёра на доске Самых удачливых.
- Худшее, что может модифицированный клиент, - соврать о СЕБЕ; а самоотчётные числа - ровно то, за чем следят детекторы паттернов: они остаются справочными до проверки человеком и обратимы после.

<color=#FFD94D><b>ЗАМКИ СТАВОК</b></color>

- Ставки закрываются в момент появления настоящей информации. В 1v1 и 2v2 это 2 очка в игре 1 либо любая решённая игра серии; в FFA - 2 очка на всё поле в текущей игре (1 в лобби до 3).
- Замок применяется сервером в момент размещения ставки, а не просто прячется в меню. На собственный матч ставить нельзя, и ставка одна на серию (в FFA - на игру) на игрока.

<color=#FFD94D><b>ПРОВЕРКА ЧЕЛОВЕКОМ</b></color>

- Каждый флаг ложится перед админом с точными доказательствами - для флага макросов это окна, пики и оба источника.
- Вердикт привязывается к тем доказательствам, которые админ рассмотрел. Если посреди проверки приходят более сильные, проверка переигрывается против них - устаревшее чтение не может решить флаг.
- Вердикт «ложное срабатывание» по чему-то автоинвалидированному запускает отслеживаемый ремонт затронутого золота и рейтинга.
- Подтверждённый вердикт не запускает автоматического наказания. Принуждение идёт через отдельные, поштучно аудируемые инструменты админа: баны и отмену серий. Бан немедленно режет живой доступ - сессии отозваны, очереди закрыты, рейтинг отклоняется, - а если тебе когда-нибудь сведёт с забаненным игроком, твой клиент выйдет сам с уведомлением.$s256$)
  , ('9568055ad9672251', 'sv', 'c801ffbe17db6bee98ea4167dbe677e5af7def51', $s256$Ranked fungerar bara om resultaten går att lita på. Kortversionen: varje rapport signeras och identitetskontrolleras, båda spelarnas klienter samlar bevis om varandra, detektorer flaggar för mänsklig granskning i stället för att autostraffa (ett smalt odlingsmönster är enda undantaget), och en människa fattar det slutliga beslutet.

<color=#FFD94D><b>MAKRODETEKTERING</b></color>

- Din klient samplar spelinput varje bildruta - rörelse, eld, block - bara medan du är vid liv i aktiv strid, aldrig medan du skriver eller är i menyer.
- Ihållande input långt bortom någon människas takt registreras som misstänkta fönster med exakta frekvenser per sekund och toppar per match.
- BÅDA spelarna håller bevisen. Varje klient publicerar sina räknare till den andra under matchen, så rapporten bär motståndarens fönster också - och i 1v1 skickar en klient med allvarliga bevis dem dessutom direkt till servern, signerade, så att de överlever även när rapportörens kopia är inaktuell eller förlorad.
- Bevissammanslagningar kan bara stärka: en senare inlämning kan aldrig försvaga toppar eller fönster som redan fångats. Om en flagga redan granskats öppnar nya bevis en färsk granskning i stället för att redigera den avgjorda.
- Flaggade makromisstänkta utesluts i tysthet ur Jämför-flikens pool av liknande spelare tills de friats - en makro-inputprofil skulle förgifta matchningarna för alla.

<color=#FFD94D><b>AFK-DETEKTERING</b></color>

- En 1v1-rapportör med noll skott, noll block och noll kortval över en match längre än två minuter flaggas. Kortkollen är den bärande: pacifist- och närstridsbuilds avslutar legitimt matcher utan att avfyra en kula, men ingen väljer noll kort medan de sitter vid tangentbordet.

<color=#FFD94D><b>OMÖJLIG TAKT</b></color>

- Speedhacks snabbar upp klientens egen klocka, så servern litar aldrig på klientrapporterade tider. Den mäter väggtiden mellan rapporternas ankomster på sin egen klocka; en serie som anländer snabbare än matcher fysiskt kan spelas flaggas, med de exakta intervallen sparade för granskning.
- Det enda automatiska straffet i hela systemet: ett upprepat mönster av orimligt korta matcher mellan samma två spelare ogiltigförklaras direkt, tidigare matcher i mönstret inräknade - guld och XP återförs, serier annulleras. Allt annat på den här sidan flaggar för mänsklig granskning.
- Kroniskt låg FPS och skakiga anslutningar bedöms mot DIN EGEN senaste historik, så en maskin som alltid kör så flaggar aldrig; plötsliga lägliga dippar bedöms mot samma matchs normalläge.

<color=#FFD94D><b>SIGNERAT, DEDUPLICERAT, KARANTÄNSATT</b></color>

- Varje matchrapport signeras och identitetskontrolleras: rapportören måste vara deltagare i matchen och hålla kontots aktiva Steam-session. <color=#7FE87F>Ingen kan rapportera SOM du</color> - och inget som någon annan rapporterar kan sätta en siffra på rekordtavlorna under ditt namn.
- Varje match kan registreras exakt en gång. Dubbletter och omsändningar absorberas - servern lämnar tillbaka det redan registrerade resultatet och inget betalar två gånger.
- En lag- eller FFA-rapport som anländer för en stängd lobby karantänsätts för admingranskning, varken betrodd eller tyst kastad.

<color=#FFD94D><b>INGEN KAN PLANTERA DATA UNDER DITT NAMN</b></color>

- Rekordtavlorna visar bara rader från en spelares EGNA rapporter, så en motståndares klient kan inte sätta en siffra under ditt namn oavsett vad den skickar.
- Kortdragningsrekord fungerar likadant: en rapport räknas bara för rapportörens egen plats på Luckiest-tavlan.
- Det värsta en modifierad klient kan göra är att ljuga om SIG SJÄLV - och självrapporterade siffror är precis vad mönsterdetektorerna bevakar; de förblir rådgivande tills en människa granskat dem, och är reversibla efteråt.

<color=#FFD94D><b>VADSLAGNINGSLÅS</b></color>

- Vadslagningen stängs i samma stund som verklig information finns. I 1v1 och 2v2 är det 2 poäng gjorda i match 1, eller att någon match i serien avgjorts; i FFA 2 poäng över fältet i den pågående matchen (1 i en först-till-3-lobby).
- Låset upprätthålls av servern när vadet läggs, inte bara gömt i menyn. Du kan inte satsa på din egen match, och det är ett vad per serie (per match i FFA) och spelare.

<color=#FFD94D><b>MÄNSKLIG GRANSKNING</b></color>

- Varje flagga landar framför en admin med sina exakta bevis - för en makroflagga fönstren, topparna och båda källorna.
- Ett utslag binds till exakt de bevis som adminen granskade. Anländer starkare bevis mitt i granskningen görs den om mot dem - en inaktuell läsning kan inte avgöra en flagga.
- Ett falskt positivt utslag på något auto-ogiltigförklarat utlöser en spårad reparation av berört guld och rating.
- Ett bekräftat utslag avfyrar inget automatiskt straff. Verkställighet går genom separata, individuellt loggade adminverktyg: avstängningar och serieåterkallelse. En avstängning kapar tillgången omedelbart - sessioner återkallas, köer blockeras, ranked vägras - och matchas du någonsin med en avstängd spelare lämnar din klient automatiskt med en notis.$s256$)
  , ('9568055ad9672251', 'uk', 'c801ffbe17db6bee98ea4167dbe677e5af7def51', $s256$Рейтинг працює, лише якщо результатам можна довіряти. Коротко: кожен звіт підписаний і перевірений на особу, клієнти обох гравців збирають докази одне про одного, детектори позначають для людського розбору замість автопокарань (єдиний виняток - один вузький патерн фармлення), і фінальне рішення ухвалює людина.

<color=#FFD94D><b>ДЕТЕКЦІЯ МАКРОСІВ</b></color>

- Ваш клієнт семплює ігровий ввід щокадру - рух, вогонь, блок - лише поки ви живі в активному бою, ніколи під час друку чи в меню.
- Тривалий ввід далеко за межами людського темпу записується як підозрілі вікна з точними посекундними частотами й піками на матч.
- Докази тримають ОБИДВА гравці. Кожен клієнт публікує свої лічильники іншому під час матчу, тож звіт несе і вікна суперника - а в 1v1 клієнт із серйозними доказами ще й подає їх серверу напряму, підписаними, тож вони виживають, навіть коли копія звітувальника застаріла чи втрачена.
- Злиття доказів може лише підсилювати: пізніше подання ніколи не ослабить уже зафіксовані піки чи вікна. Якщо позначку вже розібрано, нові докази відкривають свіжий розбір, а не редагують вирішений.
- Позначені підозрювані в макросах тихо виключаються з пулу схожих гравців вкладки Порівняння, поки їх не очистять, - макросний профіль вводу отруїв би підбірки для всіх.

<color=#FFD94D><b>ДЕТЕКЦІЯ AFK</b></color>

- Звітувальник 1v1 із нулем пострілів, нулем блоків і нулем виборів карт за матч, довший ніж дві хвилини, отримує позначку. Несуча перевірка - карти: пацифістські й ближні білди легітимно закінчують ігри без жодної кулі, але ніхто не обирає нуль карт, сидячи за клавіатурою.

<color=#FFD94D><b>НЕМОЖЛИВИЙ ТЕМП</b></color>

- Спідхаки пришвидшують годинник самого клієнта, тож сервер ніколи не довіряє тривалостям зі звітів. Він міряє реальний час між прибуттями звітів власним годинником; серія, що прибуває швидше, ніж ігри фізично граються, позначається, з точними інтервалами для розбору.
- Єдине автоматичне покарання в усій системі: повторюваний патерн неправдоподібно коротких матчів між тими самими двома гравцями інвалідується одразу, з ранішими іграми патерну включно - золото та XP відкочуються, серії анулюються. Усе інше на цій сторінці позначається для людського розбору.
- Хронічно низький FPS і шорсткі з’єднання судяться проти ВАШОЇ ВЛАСНОЇ недавньої історії, тож машина, що завжди так працює, не позначиться ніколи; раптово зручні просідання судяться проти норми того самого матчу.

<color=#FFD94D><b>ПІДПИСАНО, ДЕДУПЛІКОВАНО, В КАРАНТИНІ</b></color>

- Кожен звіт матчу підписаний і перевірений на особу: звітувальник мусить бути учасником матчу і тримати живу Steam-сесію цього акаунта. <color=#7FE87F>Ніхто не може звітувати ЗА вас</color> - і ніщо, що звітує хтось інший, не поставить число на таблицях рекордів під вашим іменем.
- Кожна гра записується рівно один раз. Дублікати й повтори поглинаються - сервер віддає вже записаний результат, і ніщо не платиться двічі.
- Командний чи FFA-звіт, що приходить на закрите лобі, іде в карантин на розбір адміном - йому не довіряють і його не викидають мовчки.

<color=#FFD94D><b>НІХТО НЕ ПІДКИНЕ ДАНІ ПІД ВАШИМ ІМЕНЕМ</b></color>

- Таблиці рекордів показують лише рядки з ВЛАСНИХ звітів гравця, тож клієнт суперника не поставить число під вашим іменем, хоч що надішле.
- Рекорди роздач карт працюють так само: звіт рахується лише за місце самого звітувальника на таблиці Найщасливіших.
- Найгірше, що може модифікований клієнт, - збрехати про СЕБЕ; а самозвітовані числа - рівно те, за чим стежать детектори патернів: вони лишаються довідковими, поки людина їх не розбере, і зворотні опісля.

<color=#FFD94D><b>ЗАМКИ СТАВОК</b></color>

- Ставки закриваються в мить, коли з’являється справжня інформація. В 1v1 і 2v2 це 2 набрані очки у грі 1 або будь-яка вирішена гра серії; у FFA - 2 очки по полю в поточній грі (1 у лобі до 3).
- Замок забезпечується сервером у момент розміщення ставки, а не лише ховається в меню. На власний матч ставити не можна, і ставка одна на серію (у FFA - на гру) на гравця.

<color=#FFD94D><b>ЛЮДСЬКИЙ РОЗБІР</b></color>

- Кожна позначка лягає перед адміном з її точними доказами - для макро-позначки це вікна, піки й обидва джерела.
- Вердикт прив’язується до рівно тих доказів, які адмін розбирав. Якщо посеред розбору приходять сильніші докази, розбір переробляється проти них - застаріле прочитання не може вирішити позначку.
- Вердикт «хибна тривога» щодо чогось автоінвалідованого запускає відстежуваний ремонт зачепленого золота й рейтингу.
- Підтверджений вердикт не запускає автоматичного покарання. Примус іде окремими, індивідуально аудитованими адмінськими інструментами: бани й реверс серій. Бан рубає живий доступ одразу - сесії відкликано, черги заблоковано, рейтинг відмовлено - а якщо вам колись випаде забанений гравець, ваш клієнт вийде автоматично зі сповіщенням.$s256$)
  , ('98d8d78a1d5e941d', 'es', '347a0be24a5721872306ab043a41e82eebcc112c', $s256$<color=#FFD94D><b>CERRADO A SALA COMPLETA - CAMBIOS REALES DE GAMEPLAY</b></color>

Estos cambian la simulación compartida. Grow, el reescalado de cajas y el repartidor de mismas cartas se cierran a sala completa: <color=#7FE87F>un combatiente vanilla o desactualizado y todos reciben vanilla, simétricamente.</color> La sincronización de veneno es por víctima, con sus propias reservas para salas mixtas.

<color=#7FD4FF>Sincronización de veneno</color> - vanilla ejecuta el veneno por separado en cada cliente, cada uno juzgando tu bloqueo con su propio tempo - las pantallas discrepan permanentemente sobre qué ticks cayeron ('HP fantasma'). Ahora el propio cliente de la víctima decide cada tick y publica el veredicto; cada cliente con mod aplica exactamente ese conjunto. Una víctima sin mod recibe el bucle vanilla puro. Funciona en cualquier sala online. <color=#8A8A93>En salas creadas por el mod con un cliente no capaz presente, los clientes con mod acuerdan en cambio que el bloqueo no anula el veneno - el acuerdo gana a la división del HP fantasma.</color>

<color=#7FD4FF>Normalización de Grow</color> - el daño de Grow se compone por FOTOGRAMA en la máquina del tirador: cerca de x1.07 en un vuelo completo a 400 FPS, x1.53 a 60, x2.31 a 30 sin acumular, peor acumulado - así es como los jugadores con FPS bajos matan de un disparo con Grow más cualquier explosivo. Las balas normalizadas crecen a una tasa fija. Cierre: todos los combatientes con mod y al día, Y una sala creada por el mod o el Ranked de todos ACTIVADO al conectar. Si no, crecimiento vanilla para todos.

<color=#7FD4FF>Cajas que caen en mapas FFA grandes</color> - en mapas FFA escalados vanilla regenera las cajas y sierras en red demasiado pequeñas, las cuerdas fallan, y caen al empezar la ronda. Se reescalan solo cuando cada combatiente es capaz; solo salas de cola FFA.

<color=#7FD4FF>Repartidor de mismas cartas FFA</color> - la regla de Mismas cartas reparte robos idénticos; necesita a cada miembro al día, si no cada cliente tira en privado.

<color=#FFD94D><b>SOLO SALAS DE MODO</b></color>

ROUNDS vanilla está construido para exactamente dos equipos, así que las salas FFA sustituyen el motor de rondas por completo: fin de ronda, puntuación, objetivo de cartas (vanilla apuntaba las cartas de 'el otro equipo' al primer jugador), apariciones, tolerancia a quienes se van. Nada de eso puede correr fuera de salas FFA.

<color=#7FD4FF>Radiance en FFA</color> - la onda de vanilla golpeaba a su propio lanzador en cuanto se movía, y se detenía tras UN golpe mientras barría a la vista a todos los demás. La versión FFA excluye al lanzador y golpea a cada rival que el anillo barre, una vez, terminando cuando el anillo termina.

<color=#7FD4FF>La corona en 2v2</color> - vanilla no puede mover la corona más allá de los dos primeros jugadores; la lleva el EQUIPO líder, ambos miembros.

<color=#7FD4FF>Escenario de elección en 2v2/1v2</color> - vanilla muestra solo el cuerpo de UN elector por ronda (a veces el equivocado), dejando al segundo elector en un escenario vacío. Cada elector se vuelve a presentar por turno; la elección extra del solo de 1v2 arregla además un crash de vanilla que colgaba la ronda.

<color=#7FD4FF>Autocontinuar</color> - las salas del mod autoconfirman el diálogo de revancha. Las partidas por código conservan a propósito el diálogo vanilla: cuando un lado pulsa Sí, vanilla arranca un temporizador de 10 segundos que echa a ese lado al menú si el otro nunca responde - un auto-Sí unilateral mata al jugador al que intenta ayudar.$s256$)
  , ('98d8d78a1d5e941d', 'ru', '347a0be24a5721872306ab043a41e82eebcc112c', $s256$<color=#FFD94D><b>ШЛЮЗ НА ВСЁ ЛОББИ - НАСТОЯЩИЕ ИЗМЕНЕНИЯ ГЕЙМПЛЕЯ</b></color>

Это меняет общую симуляцию. Grow, перемасштабирование ящиков и одинаковый раздатчик карт закрыты шлюзом на всю комнату: <color=#7FE87F>один ванильный или устаревший боец - и все получают ваниль, симметрично.</color> Синхронизация яда - по-жертвенная, со своими откатами для смешанных комнат.

<color=#7FD4FF>Синхронизация яда</color> - ваниль крутит яд отдельно на каждом клиенте, и каждый судит твой блок по своему таймингу - экраны навсегда расходятся о том, какие тики легли («призрачное HP»). Теперь каждый тик решает собственный клиент жертвы и публикует вердикт; каждый модовый клиент применяет ровно этот набор. Жертва без мода получает чистый ванильный цикл. Работает в любой онлайн-комнате. <color=#8A8A93>В комнатах, выданных модом, при неспособном клиенте модовые клиенты вместо этого соглашаются, что блок не гасит яд, - согласие важнее раскола призрачного HP.</color>

<color=#7FD4FF>Нормализация Grow</color> - урон Grow накапливается по КАДРАМ на машине стрелка: около x1.07 за полный полёт при 400 FPS, x1.53 при 60, x2.31 при 30 без стаков, со стаками хуже - вот как игроки с низким FPS ваншотят связкой Grow плюс любая взрывчатка. Нормализованные пули растут с одной фиксированной скоростью. Шлюз: каждый боец на актуальном моде И либо комната выдана модом, либо у всех был включён Ranked на подключении. Иначе - ванильный рост для всех.

<color=#7FD4FF>Падающие ящики на больших картах FFA</color> - на масштабированных картах FFA ваниль респавнит сетевые ящики и пилы слишком маленькими, верёвки промахиваются, и всё падает на старте раунда. Перемасштабируется, только когда каждый боец способен; только комнаты очереди FFA.

<color=#7FD4FF>Одинаковый раздатчик карт FFA</color> - правило «Те же карты» раздаёт идентичные наборы; нужен каждый участник на актуальной версии, иначе каждый клиент крутит рулетку приватно.

<color=#FFD94D><b>ТОЛЬКО КОМНАТЫ РЕЖИМОВ</b></color>

Ванильный ROUNDS построен ровно на две команды, так что комнаты FFA заменяют движок раундов целиком: конец раунда, счёт, прицеливание карт (ваниль наводила карты «другой команды» на первого игрока), спавны, терпимость к ушедшим. Ничто из этого не может работать вне комнат FFA.

<color=#7FD4FF>Radiance в FFA</color> - ванильная волна била собственного кастера, стоило ему шевельнуться, и останавливалась после ОДНОГО попадания, видимо проходя сквозь всех остальных. FFA-версия исключает кастера и бьёт каждого соперника, которого проходит кольцо, по одному разу, заканчиваясь с концом кольца.

<color=#7FD4FF>Корона в 2v2</color> - ваниль не умеет двигать корону дальше первых двух игроков; теперь её носит ведущая КОМАНДА, оба участника.

<color=#7FD4FF>Сцена выбора карт в 2v2/1v2</color> - ваниль показывает тело лишь ОДНОГО пикера за раунд (иногда не того), оставляя второго на пустой сцене. Каждый пикер выводится на сцену по очереди; доп. пик соло в 1v2 заодно чинит ванильный краш, вешавший раунд.

<color=#7FD4FF>Автопродолжение</color> - модовые комнаты сами подтверждают окно рематча. Игры по коду комнаты сознательно оставляют ванильное окно: после «Да» одной стороны ваниль запускает 10-секундный таймер, выкидывающий эту сторону в меню, если вторая так и не ответила, - односторонний авто-«Да» убивает игрока, которому пытается помочь.$s256$)
  , ('98d8d78a1d5e941d', 'sv', '347a0be24a5721872306ab043a41e82eebcc112c', $s256$<color=#FFD94D><b>GRINDAT PER HEL LOBBY - RIKTIGA GAMEPLAY-ÄNDRINGAR</b></color>

De här ändrar den delade simuleringen. Grow, lådomskalningen och samma-kort-givaren är grindade per helt rum: <color=#7FE87F>en enda vanilla- eller föråldrad fighter och alla får vanilla, symmetriskt.</color> Giftsynken är per offer, med sina egna reservlägen för blandade rum.

<color=#7FD4FF>Giftsynk</color> - vanilla kör giftet separat på varje klient, där var och en dömer ditt block efter sin egen timing - skärmarna är permanent oense om vilka ticks som landade ('spök-HP'). Nu avgör offrets egen klient varje tick och publicerar utslaget; varje moddad klient tillämpar exakt den uppsättningen. Ett omoddat offer får den rena vanilla-loopen i stället. Fungerar i vilket onlinerum som helst. <color=#8A8A93>I modd-utfärdade rum med en oförmögen klient närvarande enas de moddade klienterna i stället om att blockning inte upphäver gift - enighet slår spök-HP-splittringen.</color>

<color=#7FD4FF>Grow-normalisering</color> - Grows skada ackumuleras per BILDRUTA på skyttens maskin: cirka x1.07 över en full flygning vid 400 FPS, x1.53 vid 60, x2.31 vid 30 ostaplad, värre staplad - vilket är hur låg-FPS-spelare one-shottar med Grow plus valfri explosiv. Normaliserade kulor växer i en fast takt. Grind: varje fighter moddad och aktuell, OCH ett modd-utfärdat rum eller allas Ranked PÅ vid anslutning. Annars vanilla-tillväxt för alla.

<color=#7FD4FF>Fallande lådor på stora FFA-kartor</color> - på skalade FFA-kartor respawnar vanilla nätverkade lådor och sågar för små, rep missar, och de faller vid rondstart. Omskalas bara när varje fighter är kapabel; enbart FFA-körum.

<color=#7FD4FF>FFA:s samma-kort-givare</color> - regeln Samma kort delar ut identiska dragningar; kräver att varje medlem är aktuell, annars slumpar varje klient privat.

<color=#FFD94D><b>ENBART LÄGESRUM</b></color>

Vanilla-ROUNDS är byggt för exakt två lag, så FFA-rum ersätter rondmotorn rakt av: rondslut, poängräkning, kortens målsökning (vanilla riktade 'andra lagets' kort mot första spelaren), spawner, avhopparttolerans. Inget av det kan köras utanför FFA-rum.

<color=#7FD4FF>Radiance i FFA</color> - vanillas våg träffade sin egen kastare i samma stund som de rörde sig, och stannade efter EN träff medan den synligt svepte över alla andra. FFA-versionen undantar kastaren och träffar varje motståndare ringen sveper över, en gång, och slutar när ringen slutar.

<color=#7FD4FF>Kronan i 2v2</color> - vanilla kan inte flytta kronan förbi de två första spelarna; det ledande LAGET bär den, båda medlemmarna.

<color=#7FD4FF>Kortvalsscenen i 2v2/1v2</color> - vanilla visar bara EN väljares kropp per rond (ibland fel kropp), och lämnar den andra väljaren på en tom scen. Varje väljare får scenen på nytt i tur och ordning; 1v2-solons extrakort fixar också en vanilla-krasch som hängde ronden.

<color=#7FD4FF>Auto-fortsätt</color> - moddens rum autobekräftar rematch-prompten. Rumskodsmatcher behåller medvetet vanilla-prompten: efter att ena sidan klickat Ja startar vanilla en 10-sekunderstimer som sparkar den sidan till menyn om den andra aldrig svarar - ett ensidigt auto-Ja dödar spelaren det försöker hjälpa.$s256$)
  , ('98d8d78a1d5e941d', 'uk', '347a0be24a5721872306ab043a41e82eebcc112c', $s256$<color=#FFD94D><b>ВОРОТА НА ВСЕ ЛОБІ - СПРАВЖНІ ЗМІНИ ГЕЙМПЛЕЮ</b></color>

Це змінює спільну симуляцію. Grow, перемасштабування ящиків і роздавач однакових карт закриті воротами на всю кімнату: <color=#7FE87F>один ванільний чи застарілий боєць - і всі отримують ваніль, симетрично.</color> Синхронізація отрути - на кожну жертву окремо, з власними відкатами для змішаних кімнат.

<color=#7FD4FF>Синхронізація отрути</color> - ваніль ганяє отруту окремо на кожному клієнті, кожен судить ваш блок за власним таймінгом - екрани назавжди розходяться щодо того, які тіки сіли («примарне HP»). Тепер кожен тік вирішує клієнт самої жертви й публікує вердикт; кожен клієнт з модом застосовує рівно цей набір. Жертва без мода натомість отримує чистий ванільний цикл. Працює в будь-якій онлайн-кімнаті. <color=#8A8A93>У модових кімнатах, де присутній нездатний клієнт, клієнти з модом натомість домовляються, що блокування не скасовує отруту, - згода перемагає розкол примарного HP.</color>

<color=#7FD4FF>Нормалізація Grow</color> - шкода Grow нарощується поКАДРОВО на машині стрільця: близько x1.07 за повний політ на 400 FPS, x1.53 на 60, x2.31 на 30 без стаків, зі стаками гірше - ось як гравці з низьким FPS ваншотять Grow плюс будь-якою вибухівкою. Нормалізовані кулі ростуть з одним фіксованим темпом. Ворота: кожен боєць з модом і актуальний, ПЛЮС модова кімната або Ranked у всіх УВІМКНЕНИЙ на момент підключення. Інакше - ванільний ріст для всіх.

<color=#7FD4FF>Падючі ящики на великих мапах FFA</color> - на масштабованих мапах FFA ваніль респавнить мережеві ящики й пилки замалими, мотузки не дістають, і вони падають на старті раунду. Перемасштабовується лише коли кожен боєць здатний; лише кімнати черги FFA.

<color=#7FD4FF>Роздавач однакових карт FFA</color> - правило «Ті самі карти» роздає ідентичні роздачі; потребує актуальності кожного учасника, інакше кожен клієнт крутить приватно.

<color=#FFD94D><b>ЛИШЕ КІМНАТИ РЕЖИМІВ</b></color>

Ванільний ROUNDS збудовано рівно під дві команди, тож кімнати FFA замінюють рушій раундів цілком: кінець раунду, рахунок, прицілювання карт (ваніль цілила карти «іншої команди» в першого гравця), спавни, терпимість до виходів. Ніщо з цього не може працювати поза кімнатами FFA.

<color=#7FD4FF>Radiance у FFA</color> - ванільна хвиля била власного кастера, щойно він рухався, і зупинялася після ОДНОГО влучання, видимо прокочуючись крізь усіх інших. FFA-версія виключає кастера і б’є кожного суперника, якого прокочує кільце, по разу, завершуючись із кінцем кільця.

<color=#7FD4FF>Корона у 2v2</color> - ваніль не вміє рухати корону далі перших двох гравців; тепер її носить КОМАНДА-лідер, обидва учасники.

<color=#7FD4FF>Сцена вибору карт у 2v2/1v2</color> - ваніль показує лише тіло ОДНОГО обирача за раунд (іноді не того), лишаючи другого на порожній сцені. Кожен обирач виводиться на сцену по черзі; додатковий вибір соло в 1v2 також виправляє ванільний краш, що вішав раунд.

<color=#7FD4FF>Автопродовження</color> - модові кімнати самі підтверджують питання рематчу. Ігри за кодом кімнати свідомо зберігають ванільне питання: після того, як одна сторона клацає Yes, ваніль запускає 10-секундний таймер, що викидає цю сторону в меню, якщо інша так і не відповість, - односторонній авто-Yes убиває гравця, якому намагається допомогти.$s256$)
  , ('99685a1ab2965e95', 'es', 'f96cb1e2a99916b8478ad8dbedcc9ece51d1da2e', $s256$Qué pasa cuando alguien no se presenta, abandona o deja un torneo - y exactamente cómo se calculan los premios. Versión corta: <color=#7FE87F>una serie terminada siempre vale</color>, lo que se castiga es la ausencia, y las victorias por incomparecencia nunca pagan premios de podio.

<color=#FFD94D><b>PLAZOS</b></color>

- Sync: las partidas dan 10 minutos de gracia para presentarse desde que quedan listas. Una partida que sigue a una partida JUGADA pasa antes por un respiro de 7 minutos (una alimentada por un bye puede quedar lista de inmediato), y una partida aún en su respiro no puede dar por perdido a nadie. Mientras ambos jugadores estén presentes el servidor espera - una partida sync puede pasarse de su plazo.

- Async: cada partida, el reinicio de la gran final incluido, tiene un plazo de 7 días desde que se activa. El MD de check-in del plazo puede extenderlo 24 horas, una vez por rival. La presencia no salva una partida async - solo jugar lo hace.

<color=#FFD94D><b>CUANDO LLEGA EL PLAZO</b></color>

El servidor resuelve una partida vencida en este orden exacto - la primera regla que aplica la decide:

- 1. <color=#7FE87F>Una serie terminada siempre vale</color> - nada pasa por encima de un resultado jugado.
- 2. Si exactamente un asiento está baneado, el otro jugador avanza de inmediato.
- 3. Una partida reportada en los últimos 45 minutos significa una serie viva - la partida se deja en paz.
- 4. Solo sync: ambos jugadores presentes - el servidor sigue esperando.
- 5. Exactamente un jugador presente - <color=#FF6666>el ausente pierde por incomparecencia</color> y el presente avanza.
- 6. En otro caso: si la serie se empezó y el marcador está desnivelado, avanza el líder del marcador. Si no, si exactamente uno de los dos respondió el check-in del plazo async - cualquier respuesta - ese jugador avanza sobre el silencioso. Si tampoco, avanza el % de incomparecencia más bajo, y un empate total cae a un desempate fijo arbitrario.

Solo los asientos ausentes reciben la marca de incomparecencia (un asiento baneado pierde esté presente o no, y un asiento silencioso puede perder los desempates async estando presente). Tu <color=#7FD4FF>% de incomparecencia</color> es una tasa móvil de 90 días que decide tu prioridad en futuros torneos, el orden de reemplazo y estos desempates.

<color=#FFD94D><b>QUÉ HACE UNA INCOMPARECENCIA - Y QUÉ NO</b></color>

- El cuadro avanza exactamente como si la partida se hubiera completado - el ganador sigue, el perdedor baja o queda fuera.

- <color=#FF6666>Una incomparecencia no acuña nada.</color> Los puestos de podio solo existen para series jugadas y completadas - un puesto de podio decidido por incomparecencia no paga premio.

- Ningún rating se mueve. El rating solo cambia cuando una serie se completa; la serie de una partida perdida por incomparecencia simplemente nunca se completa ni se puntúa.

- Las apuestas se cierran: la serie de una partida decidida por incomparecencia no admite apuestas.

<color=#FFD94D><b>IRSE, Y QUIÉN TE SUSTITUYE</b></color>

- Durante la votación: date de baja libremente.

- Tras el cierre, antes del inicio: corre el flujo de reemplazo - la inscripción especulativa más fiable toma tu plaza exacta del cuadro (con su propio rating); sin especulativos disponibles, tus futuros rivales reciben byes. Irse así no conlleva penalización.

- Una vez en marcha: no puedes darte de baja. No presentarte da tus partidas por perdidas y cuenta en tu % de incomparecencia.

- Abandonar a mitad de partida sigue las reglas normales de desconexión del 1v1: la DC cae en tu % de salida, y salvo que tu rival estuviera a punto de partida (entonces se lleva el juego, lo que puede cerrar la serie) la serie queda abierta con su marcador. El barrido de plazos resuelve una serie abandonada: pasada la gracia de 45 minutos gana un rival aún presente; si ambos se marcharon, avanza el líder del marcador.

<color=#FFD94D><b>LA ANULACIÓN DE RANKED</b></color>

- Cuando una de tus partidas de torneo está activa y tu Ranked está apagado, el mod lo ENCIENDE y te lo dice. Las partidas async ocurren en salas privadas, que solo se registran como ranked cuando ambos jugadores tienen Ranked activado - la anulación garantiza que tu resultado se registre.

- <color=#FF6666>Queda ENCENDIDO tras la partida.</color> No hay reversión automática: apágalo en Ajustes si no quieres que las partidas posteriores puntúen. Apagarlo entre partidas de torneo hace que se vuelva a encender cuando tu siguiente partida se active.

<color=#FFD94D><b>PREMIOS, TROFEOS Y APUESTAS</b></color>

- El bote escala con el número de jugadores congelado al cierre. Con 8 jugadores: 1000 / 600 / 120 de Oro y 5000 / 3000 / 150 de XP para 1.º / 2.º / 3.º. Crece linealmente con el campo, doblándose con 16 jugadores: 2000 / 1200 / 240 de Oro y 10000 / 6000 / 300 de XP.

- <color=#7FE87F>Los premios se pagan cuando el cuadro entero se completa</color>, no cuando termina tu última partida. Un puesto decidido por incomparecencia se salta, no se hereda hacia abajo.

- <color=#8A8A93>La XP de premio se comporta como cualquier otra: se convierte en Oro al habitual 100 XP = 1 Oro, y un límite de nivel que cruce paga la recompensa de nivel normal.</color>

- Los trofeos son roles de Discord: SCR Tournament Winner, Runner Up y 3rd Place; repetir el mismo puesto mejora el rol a su versión (x2). Cada participante confirmado recibe el rol Participant. Los torneos no otorgan títulos de la tienda del juego.

- Cada partida de torneo es un al mejor de 3 ranked normal: mueve tu rating 1v1 habitual llegues o no al podio.

- Las partidas de torneo admiten apuestas en los mismos términos que cualquier serie ranked en vivo: las apuestas se cierran con 2 puntos en vivo en el juego 1 o en cuanto se decide cualquier juego. Un emparejamiento async que espera días sigue siendo apostable toda la espera a 0-0.$s256$)
  , ('99685a1ab2965e95', 'ru', 'f96cb1e2a99916b8478ad8dbedcc9ece51d1da2e', $s256$Что происходит, когда кто-то не приходит, выходит или покидает турнир, - и как именно считаются призы. Коротко: <color=#7FE87F>доигранная серия всегда стоит</color>, наказывается отсутствие, а победы техпоражением никогда не платят призов подиума.

<color=#FFD94D><b>ДЕДЛАЙНЫ</b></color>

- Синхро: матчи дают 10 минут льготы на явку с момента готовности. Матч, идущий за СЫГРАННЫМ матчем, сперва сидит в 7-минутной передышке (матч после пропуска раунда может стать готовым сразу), и матч в передышке не может дать техпоражение никому. Пока оба игрока присутствуют, сервер ждёт - синхро-матч может выйти за свой дедлайн.

- Асинхро: у каждого матча, включая переигровку гранд-финала, дедлайн 7 дней с момента активации. Чек-ин дедлайна может продлить его на 24 часа, один раз на соперника. Присутствие асинхро-матч не спасает - спасает только игра.

<color=#FFD94D><b>КОГДА ДЕДЛАЙН НАСТУПАЕТ</b></color>

Сервер решает просроченный матч ровно в этом порядке - решает первое подошедшее правило:

- 1. <color=#7FE87F>Доигранная серия всегда стоит</color> - сыгранный результат не перекрывается ничем.
- 2. Если забанено ровно одно место, второй игрок проходит немедленно.
- 3. Игра, записанная в последние 45 минут, означает живую серию - матч не трогают.
- 4. Только синхро: оба игрока присутствуют - сервер продолжает ждать.
- 5. Присутствует ровно один игрок - <color=#FF6666>отсутствующий получает техпоражение</color>, присутствующий проходит.
- 6. Иначе: если серия начата и счёт неравный, проходит лидер счёта. Не вышло - если ровно один из вас ответил на асинхро-чек-ин, любым ответом, этот игрок проходит вперёд молчавшего. Не вышло и это - проходит меньший % неявок, а мёртвую ничью решает фиксированный произвольный тайбрейк.

Отметку неявки получают только отсутствующие места (забаненное место получает техпоражение независимо от присутствия, а молчавшее может проиграть асинхро-тайбрейки и присутствуя). Твой <color=#7FD4FF>% неявок</color> - скользящая 90-дневная доля, решающая твой приоритет в будущих турнирах, порядок замен и эти тайбрейки.

<color=#FFD94D><b>ЧТО ДЕЛАЕТ ТЕХПОРАЖЕНИЕ - И ЧЕГО НЕ ДЕЛАЕТ</b></color>

- Сетка продвигается ровно как при доигранном матче - победитель идёт дальше, проигравший падает или выбывает.

- <color=#FF6666>Техпоражение не чеканит ничего.</color> Места подиума существуют только для сыгранных, завершённых серий - подиумное место, решённое техпоражением, приза не платит.

- Рейтинг не двигается. Рейтинг меняется только при завершении серии; серия матча, решённого техпоражением, просто никогда не завершается и не оценивается.

- Ставки закрываются: на серию такого матча ставить нельзя.

<color=#FFD94D><b>УХОД - И КТО ТЕБЯ ЗАМЕНЯЕТ</b></color>

- Во время голосования: снимайся свободно.

- После закрытия, до старта: работает поток замен - самый надёжный запасной берёт ровно твой слот сетки (со своим рейтингом); нет запасного - твои несостоявшиеся соперники получают пропуска. Такой уход без штрафа.

- Когда турнир идёт: сняться нельзя. Неявка даёт техпоражения в твоих матчах и идёт в % неявок.

- Выход посреди игры следует обычным правилам отключений 1v1: DC ложится в твой % выходов, и если соперник не стоял на матч-пойнте (тогда он берёт игру, что может закончить серию), серия остаётся открытой на своём счёте. Брошенную серию решает дедлайн-чистка: после 45-минутной льготы всё ещё присутствующий соперник побеждает; если ушли оба, проходит лидер счёта.

<color=#FFD94D><b>РЕЙТИНГОВЫЙ ОВЕРРАЙД</b></color>

- Когда твой турнирный матч жив, а переключатель Ranked выключен, мод включает его и говорит тебе об этом. Асинхро-матчи играются в приватных лобби, которые записываются рейтинговыми только при включённом Ranked у обоих, - оверрайд гарантирует, что твой результат запишется.

- <color=#FF6666>После матча он остаётся ВКЛЮЧЁННЫМ.</color> Автовозврата нет: выключи его в Настройках, если не хочешь рейтинговать поздние игры. Выключенный между турнирными матчами, он снова включится, когда оживёт твой следующий матч.

<color=#FFD94D><b>ПРИЗЫ, ТРОФЕИ И СТАВКИ</b></color>

- Фонд масштабируется числом игроков, снятым при закрытии. На 8 игроках: 1000 / 600 / 120 золота и 5000 / 3000 / 150 XP за 1-е / 2-е / 3-е. Он растёт линейно с полем, удваиваясь на 16 игроках: 2000 / 1200 / 240 золота и 10000 / 6000 / 300 XP.

- <color=#7FE87F>Призы платятся, когда завершается вся сетка</color>, а не когда кончается твой последний матч. Место, решённое техпоражением, пропускается, а не передаётся вниз.

- <color=#8A8A93>Призовой XP ведёт себя как любой XP: конвертируется в золото по обычным 100 XP = 1 золото, а пересечённая граница уровня платит обычную награду уровня.</color>

- Трофеи - это роли Discord: SCR Tournament Winner, Runner Up и 3rd Place; второе такое же место повышает роль до её версии (x2). Каждый подтверждённый участник получает роль Participant. Турниры не выдают внутриигровых титулов магазина.

- Каждая турнирная игра - обычная рейтинговая серия до 2 побед: она двигает твой обычный рейтинг 1v1, добрался ты до подиума или нет.

- Ставки на турнирные матчи работают на тех же условиях, что на любую живую рейтинговую серию: ставки закрываются на 2 живых очках в игре 1 или как только решена любая игра. Асинхро-пара, ждущая днями, доступна для ставок всё ожидание при счёте 0-0.$s256$)
  , ('99685a1ab2965e95', 'sv', 'f96cb1e2a99916b8478ad8dbedcc9ece51d1da2e', $s256$Vad som händer när någon inte dyker upp, hoppar av eller lämnar en turnering - och exakt hur priser beräknas. Kortversionen: <color=#7FE87F>en färdigspelad serie står alltid fast</color>, frånvaro är det som straffas, och walkover-vinster betalar aldrig podiepriser.

<color=#FFD94D><b>TIDSFRISTER</b></color>

- Sync: matcher ger 10 minuters uppdykandefrist från det ögonblick de blir redo. En match som följer på en SPELAD match ligger först i en 7-minuters andhämtning (en match matad av en friomgång kan bli redo direkt), och en match som ännu är i sin andhämtning kan aldrig ge någon walkover. Medan båda spelarna är närvarande väntar servern - en sync-match kan löpa förbi sin tidsfrist.

- Async: varje match, den stora finalens reset inräknad, har en 7-dagars tidsfrist från att den går live. Incheckningen via DM kan förlänga den 24 timmar, en gång per motståndare. Närvaro räddar inte en async-match - bara spelande gör det.

<color=#FFD94D><b>NÄR TIDSFRISTEN SLÅR TILL</b></color>

Servern avgör en försenad match i exakt denna ordning - den första regel som gäller avgör:

- 1. <color=#7FE87F>En färdigspelad serie står alltid fast</color> - inget kör över ett spelat resultat.
- 2. Om exakt en plats är avstängd går den andra spelaren vidare omedelbart.
- 3. En match rapporterad de senaste 45 minuterna betyder en levande serie - matchen lämnas i fred.
- 4. Endast sync: båda spelarna närvarande - servern fortsätter vänta.
- 5. Exakt en spelare närvarande - <color=#FF6666>den frånvarande spelaren förlorar på walkover</color> och den närvarande går vidare.
- 6. Annars: om serien startats och ställningen är ojämn går poängledaren vidare. Annars, om exakt en av er svarade på async-incheckningen - vilket svar som helst - går den spelaren före den tysta. Annars går den med lägst uteblivande-% vidare, och ett dött lopp faller på en fast godtycklig särskiljning.

Bara frånvarande platser får uteblivandemarkeringen (en avstängd plats förlorar på walkover oavsett närvaro, och en tyst plats kan förlora async-särskiljningarna trots närvaro). Din <color=#7FD4FF>uteblivande-%</color> är en rullande 90-dagarsandel som styr din prioritet in i framtida turneringar, reservordningen och de här särskiljningarna.

<color=#FFD94D><b>VAD EN WALKOVER GÖR - OCH INTE GÖR</b></color>

- Bracketen går vidare precis som om matchen spelats klart - vinnaren går vidare, förloraren faller eller är ute.

- <color=#FF6666>En walkover myntar ingenting.</color> Podieplaceringar finns bara för spelade, avslutade serier - en podieplats avgjord på walkover betalar inget pris.

- Ingen rating flyttas. Rating ändras bara när en serie avslutas; en walkover-matchs serie blir helt enkelt aldrig avslutad eller poängsatt.

- Vadslagningen stängs: en walkover-avgjord matchs serie kan inte satsas på.

<color=#FFD94D><b>ATT LÄMNA, OCH VEM SOM ERSÄTTER DIG</b></color>

- Under röstningen: avanmäl dig fritt.

- Efter låsningen, före starten: reservflödet körs - den mest pålitliga spekulativa anmälningen tar din exakta bracketplats (med sin egen rating); finns ingen spekulativ får dina skulle-ha-varit-motståndare friomgångar. Att lämna på det här sättet ger inget straff.

- När den väl är igång: du kan inte avanmäla dig. Att inte dyka upp ger walkover i dina matcher och räknas på din uteblivande-%.

- Att hoppa av mitt i en match följer vanliga 1v1-disconnectregler: DC:n landar på din avhopps-%, och om inte din motståndare stod på matchboll (då tar de matchen, vilket kan avsluta serien) förblir serien öppen på sin ställning. Tidsfristsvepet löser en övergiven serie: efter 45-minutersfristen vinner en ännu närvarande motståndare; gick båda därifrån går poängledaren vidare.

<color=#FFD94D><b>RANKED-ÖVERSTYRNINGEN</b></color>

- När en av dina turneringsmatcher är live och din Ranked-inställning är av, slår modden PÅ den och berättar det. Async-matcher spelas i privata lobbyer, som bara registreras som rankade när båda spelarna har Ranked aktiverat - överstyrningen garanterar att ditt resultat registreras.

- <color=#FF6666>Den förblir PÅ efter matchen.</color> Det finns ingen automatisk återgång: stäng av den i Inställningar om du inte vill att senare matcher rankas. Stänger du av den mellan turneringsmatcher slås den på igen när din nästa match går live.

<color=#FFD94D><b>PRISER, TROFÉER OCH VADSLAGNING</b></color>

- Potten skalar med spelarantalet fryst vid låsningen. Vid 8 spelare: 1000 / 600 / 120 guld och 5000 / 3000 / 150 XP för 1:a / 2:a / 3:e plats. Den växer linjärt med fältet och dubblas vid 16 spelare: 2000 / 1200 / 240 guld och 10000 / 6000 / 300 XP.

- <color=#7FE87F>Priser betalas när hela bracketen är klar</color>, inte när din sista match slutar. En walkover-avgjord placering hoppas över i stället för att skickas vidare nedåt.

- <color=#8A8A93>Pris-XP beter sig som all annan XP: den omvandlas till guld enligt de vanliga 100 XP = 1 guld, och en nivågräns den korsar betalar den normala nivåbelöningen.</color>

- Troféer är Discord-roller: SCR Tournament Winner, Runner Up och 3rd Place; en andra likadan placering uppgraderar rollen till sin (x2)-version. Varje bekräftad deltagare får rollen Participant. Turneringar ger inga butikstitlar i spelet.

- Varje turneringsmatch är en normal ranked bäst av 3: den flyttar din vanliga 1v1-rating vare sig du når podiet eller inte.

- Turneringsmatcher går att satsa på på samma villkor som varje annan pågående ranked-serie: vadslagningen låses vid 2 live-poäng i match 1 eller när någon match avgjorts. En async-parning som väntar i dagar förblir satsningsbar hela väntan vid 0-0.$s256$)
  , ('99685a1ab2965e95', 'uk', 'f96cb1e2a99916b8478ad8dbedcc9ece51d1da2e', $s256$Що стається, коли хтось не з’являється, кидає гру або покидає турнір - і як саме обчислюються призи. Коротко: <color=#7FE87F>дограна серія завжди в силі</color>, карається саме відсутність, а перемоги технічною поразкою ніколи не платять подіумних призів.

<color=#FFD94D><b>ТЕРМІНИ</b></color>

- Sync: матчі дають 10 хвилин пільги на явку з моменту готовності. Матч одразу після ЗІГРАНОГО матчу спершу сидить у 7-хвилинному перепочинку (матч після пропуску раунду може стати готовим одразу), і матч у своєму перепочинку нікому не може зарахувати технічну поразку. Поки обидва гравці присутні, сервер чекає - sync-матч може вийти за свій термін.

- Async: кожен матч, включно з перегравкою гранд-фіналу, має 7-денний термін з моменту, коли він оживає. Чек-ін у DM може подовжити його на 24 години, раз на суперника. Присутність async-матч не рятує - рятує лише гра.

<color=#FFD94D><b>КОЛИ ТЕРМІН СПЛИВАЄ</b></color>

Сервер вирішує прострочений матч рівно в цьому порядку - вирішує перше правило, що підходить:

- 1. <color=#7FE87F>Дограна серія завжди в силі</color> - зіграний результат не перекриває ніщо.
- 2. Якщо рівно одне місце забанене - інший гравець проходить далі одразу.
- 3. Гра, звітована за останні 45 хвилин, означає живу серію - матч не чіпають.
- 4. Лише sync: обидва гравці присутні - сервер чекає далі.
- 5. Рівно один гравець присутній - <color=#FF6666>відсутній отримує технічну поразку</color>, а присутній проходить далі.
- 6. Інакше: якщо серію почато і рахунок нерівний, проходить лідер рахунку. Якщо ні - і рівно один із вас відповів на чек-ін терміну (будь-якою відповіддю), той проходить повз мовчазного. Якщо й це ні - проходить менший % неявок, а мертву нічию вирішує фіксований довільний тайбрейк.

Позначку неявки отримують лише відсутні місця (забанене місце програє технічно незалежно від присутності, а мовчазне може програти async-тайбрейки навіть присутнім). Ваш <color=#7FD4FF>% неявок</color> - ковзний 90-денний показник, що вирішує ваш пріоритет у майбутні турніри, порядок заміни й ці тайбрейки.

<color=#FFD94D><b>ЩО РОБИТЬ ТЕХНІЧНА ПОРАЗКА - І ЧОГО НІ</b></color>

- Сітка просувається рівно так, ніби матч завершився: переможець іде далі, переможений падає або вибуває.

- <color=#FF6666>Технічна поразка не карбує нічого.</color> Подіумні місця існують лише для зіграних, завершених серій - подіум, вирішений технічною поразкою, призу не платить.

- Рейтинг не рухається. Рейтинг змінюється лише коли серія завершується; серія матчу з технічною поразкою просто ніколи не завершується і не оцінюється.

- Ставки закриваються: на серію матчу з технічною поразкою ставити не можна.

<color=#FFD94D><b>ВИХІД, І ХТО ВАС ЗАМІНЮЄ</b></color>

- Під час голосування: знімайтеся вільно.

- Після закриття, до старту: працює потік заміни - найнадійніша запасна реєстрація займає точно ваш слот у сітці (зі своїм рейтингом); якщо запасних немає, ваші потенційні суперники отримують пропуски. Такий вихід без штрафу.

- Коли турнір уже йде: знятися не можна. Неявка дає технічні поразки у ваших матчах і рахується у ваш % неявок.

- Кидання посеред гри йде за звичайними правилами дисконекту 1v1: DC лягає у ваш % виходів, і якщо суперник не був на матч-пойнті (тоді він бере гру, що може завершити серію), серія лишається відкритою на своєму рахунку. Прострочену покинуту серію вирішує прибиральник термінів: після 45-хвилинної пільги досі присутній суперник виграє; якщо пішли обидва - проходить лідер рахунку.

<color=#FFD94D><b>ПЕРЕВИЗНАЧЕННЯ RANKED</b></color>

- Коли один із ваших турнірних матчів живий, а ваш перемикач Ranked вимкнений, мод вмикає його і каже вам про це. Async-матчі граються в приватних лобі, які записуються рейтинговими лише коли Ranked увімкнено в обох - перевизначення гарантує, що ваш результат запишеться.

- <color=#FF6666>Після матчу він ЛИШАЄТЬСЯ УВІМКНЕНИМ.</color> Автоповернення немає: вимкніть у Налаштуваннях, якщо не хочете, щоб пізніші ігри оцінювалися. Вимкнений між турнірними матчами, він знову вмикається, коли оживає ваш наступний матч.

<color=#FFD94D><b>ПРИЗИ, ТРОФЕЇ І СТАВКИ</b></color>

- Фонд масштабується з кількістю гравців, зафіксованою на закритті. На 8 гравцях: 1000 / 600 / 120 золота і 5000 / 3000 / 150 XP за 1-ше / 2-ге / 3-тє. Він росте лінійно з полем і подвоюється на 16 гравцях: 2000 / 1200 / 240 золота і 10000 / 6000 / 300 XP.

- <color=#7FE87F>Призи платяться, коли завершується вся сітка</color>, а не коли закінчується ваш останній матч. Місце, вирішене технічною поразкою, пропускається, а не передається нижче.

- <color=#8A8A93>Призовий XP поводиться як будь-який інший XP: конвертується в золото за звичними 100 XP = 1 золото, а перетнута ним межа рівня платить звичайну нагороду рівня.</color>

- Трофеї - це ролі Discord: SCR Tournament Winner, Runner Up і 3rd Place; повторне те саме місце підвищує роль до її версії (x2). Кожен підтверджений учасник отримує роль Participant. Турніри не дають ігрових титулів магазину.

- Кожна турнірна гра - звичайний рейтинговий best-of-3: вона рухає ваш звичайний рейтинг 1v1, досягнете ви подіуму чи ні.

- На турнірні матчі ставлять на тих самих умовах, що й на будь-яку живу рейтингову серію: ставки замикаються на 2 живих очках у грі 1 або щойно вирішено будь-яку гру. Async-пара, що чекає днями, лишається ставною весь цей час на 0-0.$s256$)
  , ('9e4688ee7855897b', 'es', '82787788a58b2381733c8d8cd22405f47bf7231b', $s256$Cuándo cuenta una partida$s256$)
  , ('9e4688ee7855897b', 'ru', '82787788a58b2381733c8d8cd22405f47bf7231b', $s256$Когда игра засчитывается$s256$)
  , ('9e4688ee7855897b', 'sv', '82787788a58b2381733c8d8cd22405f47bf7231b', $s256$När en match räknas$s256$)
  , ('9e4688ee7855897b', 'uk', '82787788a58b2381733c8d8cd22405f47bf7231b', $s256$Коли гра зараховується$s256$)
  , ('a4ae6fe168654f46', 'es', '43b20143fadbcc200b573c5b37b0768ad48fa1ba', $s256$<color=#FFD94D><b>RACHAS</b></color>

Todas las rachas son solo de 1v1. Las rachas casual cuentan partidas; las ranked cuentan series completadas.

- <color=#7FD4FF>Impecable</color> - cinco victorias 5-0 seguidas. Cuentan ranked y casual; <color=#FF6666>cualquier partida que no sea una victoria 5-0 la reinicia</color>. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Club de los cien</color> - 100 victorias casual seguidas. Una derrota casual la reinicia; las partidas ranked no tocan el contador. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Conquistador casual</color> - 200 victorias casual seguidas. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Touch Grass</color> - 500 victorias casual seguidas. <color=#7FE87F>1000g</color>
- <color=#7FD4FF>En racha</color> - gana 25 series ranked completadas seguidas. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Imparable</color> - 50 series ranked seguidas. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Inmortal</color> - 100 series ranked seguidas. <color=#7FE87F>500g</color>

<color=#FFD94D><b>RATING, SLAYERS Y 2v2</b></color>

Los hitos de rating se comprueban cada vez que se actualiza tu rating 1v1 o 2v2. Los movimientos de rating FFA no los disparan.

- <color=#7FD4FF>Estrella en ascenso</color> - alcanza 1700 de rating. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Maestro</color> - alcanza 1980 de rating. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Gran Maestro</color> - alcanza 2330 de rating. <color=#7FE87F>1000g</color>
- <color=#7FD4FF>Sid Slayer</color> - gana una serie ranked 1v1 completada contra Sid. Otorga el título equipable Sid Slayer. <color=#7FE87F>1000g</color>
- <color=#7FD4FF>Stan Slayer</color> - gana una serie ranked 1v1 completada contra Stan. Otorga el título Stan Slayer. <color=#7FE87F>1000g</color>
- <color=#7FD4FF>Barrida en equipo</color> - gana un solo juego de 2v2 por 5-0. Lo desbloquean ambos miembros del equipo ganador; es por juego, no por serie. <color=#7FE87F>500g</color>

<color=#FFD94D><b>FFA Y TRADUCTOR</b></color>

Los seis de FFA requieren una sala FFA RANKED y todos se comprueban en el servidor.

- <color=#7FD4FF>Limpieza general</color> - gana un FFA 5-0: los cinco puntos tuyos y nadie más convierte un punto completo, en una sala que sentó a 3 o más jugadores. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Aguafiestas</color> - lo mismo con 4 o más sentados. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Adquisición hostil</color> - lo mismo con 5 o más sentados. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Masacre</color> - más de 50 kills en una partida. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Bajas</color> - más de 100 kills en una partida. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Corazón roto</color> - pierde una partida con 10 o más rondas ganadas que nunca llegaron a puntos completos. <color=#7FE87F>300g</color>

Los 5-0 se anidan: <color=#7FE87F>un 5-0 en sala de 5 jugadores desbloquea los tres a la vez, 900 de oro en total</color>. Sentados significa la lista al cerrarse la sala, no quién aguantó hasta el final - y los perdedores con rondas ganadas sobrantes no rompen tu 5-0; solo lo hace un punto completo convertido. <color=#8A8A93>Los conteos de kills solo se registran cuando la partida la reportó una versión del mod al día.</color>

Los niveles de traductor vienen del portal de traducción, no de las partidas. Una cadena publicada es una traducción aprobada que propusiste o revisaste; hacer ambos trabajos en una cadena cuenta una vez. Cada nivel otorga además su título correspondiente (ver <color=#7FD4FF>Títulos</color>).

- <color=#7FD4FF>Rosetta</color> - 10 cadenas publicadas. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Dragomán</color> - 100 cadenas publicadas. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Babel</color> - 1000 cadenas publicadas. <color=#7FE87F>1000g</color>$s256$)
  , ('a4ae6fe168654f46', 'ru', '43b20143fadbcc200b573c5b37b0768ad48fa1ba', $s256$<color=#FFD94D><b>ПОБЕДЫ ПОДРЯД</b></color>

Все серии побед - только 1v1. Казуальные считают игры; рейтинговые считают завершённые серии.

- <color=#7FD4FF>Безупречный</color> - пять побед 5-0 подряд. Считаются и рейтинг, и казуал; <color=#FF6666>любая игра, не являющаяся победой 5-0, сбрасывает счёт</color>. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Клуб сотни</color> - 100 казуальных побед подряд. Казуальное поражение сбрасывает; рейтинговые игры счётчик не трогают. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Покоритель казуала</color> - 200 казуальных побед подряд. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Потрогай траву</color> - 500 казуальных побед подряд. <color=#7FE87F>1000g</color>
- <color=#7FD4FF>В ударе</color> - выиграй 25 завершённых рейтинговых серий подряд. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Неудержимый</color> - 50 рейтинговых серий подряд. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Бессмертный</color> - 100 рейтинговых серий подряд. <color=#7FE87F>500g</color>

<color=#FFD94D><b>РЕЙТИНГ, СЛЕЕРЫ И 2v2</b></color>

Рейтинговые вехи проверяются при каждом обновлении твоего рейтинга 1v1 или 2v2. Движения рейтинга FFA их не запускают.

- <color=#7FD4FF>Восходящая звезда</color> - достигни рейтинга 1700. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Мастер</color> - достигни рейтинга 1980. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Грандмастер</color> - достигни рейтинга 2330. <color=#7FE87F>1000g</color>
- <color=#7FD4FF>Sid Slayer</color> - выиграй завершённую рейтинговую серию 1v1 против Sid. Даёт надеваемый титул Sid Slayer. <color=#7FE87F>1000g</color>
- <color=#7FD4FF>Stan Slayer</color> - выиграй завершённую рейтинговую серию 1v1 против Stan. Даёт титул Stan Slayer. <color=#7FE87F>1000g</color>
- <color=#7FD4FF>Командный разгром</color> - выиграй одну игру 2v2 со счётом 5-0. Открывают оба члена победившей команды; это за игру, не за серию. <color=#7FE87F>500g</color>

<color=#FFD94D><b>FFA И ПЕРЕВОДЧИК</b></color>

Шестёрке FFA нужно РЕЙТИНГОВОЕ FFA-лобби; все они проверяются сервером.

- <color=#7FD4FF>Генеральная уборка</color> - выиграй FFA 5-0: все пять очков твои и никто другой не конвертирует полное очко, в лобби, где сидело 3 и больше игроков. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Незваный гость</color> - то же при 4 и больше сидевших. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Враждебное поглощение</color> - то же при 5 и больше сидевших. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Неистовство</color> - больше 50 убийств за одну игру. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Убийства</color> - больше 100 убийств за одну игру. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Разбитое сердце</color> - проиграй игру, держа 10 и больше выигранных раундов, так и не ставших полными очками. <color=#7FE87F>300g</color>

Сухие серии вложены: <color=#7FE87F>один шатаут на 5 игроков открывает все три разом, 900 золота итого</color>. «Сидело» - это ростер на момент фиксации лобби, а не досидевшие до конца; проигравшие с остаточными выигранными раундами твой шатаут не ломают - ломает только конвертированное полное очко. <color=#8A8A93>Счётчики убийств регистрируются, только когда игру отправила актуальная версия мода.</color>

Уровни переводчика приходят из портала переводов, а не из матчей. Живая строка - одобренный перевод, который ты предложил или отревьюил; обе роли на одной строке считаются один раз. Каждый уровень даёт и соответствующий титул (см. <color=#7FD4FF>Титулы</color>).

- <color=#7FD4FF>Розетта</color> - 10 живых строк. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Драгоман</color> - 100 живых строк. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Вавилон</color> - 1000 живых строк. <color=#7FE87F>1000g</color>$s256$)
  , ('a4ae6fe168654f46', 'sv', '43b20143fadbcc200b573c5b37b0768ad48fa1ba', $s256$<color=#FFD94D><b>SVITER</b></color>

Alla sviter är endast 1v1. Casual-sviter räknar matcher; ranked-sviter räknar avslutade serier.

- <color=#7FD4FF>Felfri</color> - fem 5-0-vinster i rad. Ranked och casual räknas båda; <color=#FF6666>varje match som inte är en 5-0-vinst nollställer den</color>. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Hundraklubben</color> - 100 casual-vinster i rad. En casual-förlust nollställer; ranked-matcher rör inte räknaren. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Casual-erövrare</color> - 200 casual-vinster i rad. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Touch Grass</color> - 500 casual-vinster i rad. <color=#7FE87F>1000g</color>
- <color=#7FD4FF>Glödhet</color> - vinn 25 avslutade ranked-serier i följd. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Ostoppbar</color> - 50 ranked-serier i rad. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Odödlig</color> - 100 ranked-serier i rad. <color=#7FE87F>500g</color>

<color=#FFD94D><b>RATING, SLAYERS OCH 2v2</b></color>

Ratingmilstolparna kontrolleras varje gång din 1v1- eller 2v2-rating uppdateras. FFA-ratingrörelser utlöser dem inte.

- <color=#7FD4FF>Stigande stjärna</color> - nå 1700 i rating. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Mästare</color> - nå 1980 i rating. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Stormästare</color> - nå 2330 i rating. <color=#7FE87F>1000g</color>
- <color=#7FD4FF>Sid Slayer</color> - vinn en avslutad ranked 1v1-serie mot Sid. Ger den utrustningsbara titeln Sid Slayer. <color=#7FE87F>1000g</color>
- <color=#7FD4FF>Stan Slayer</color> - vinn en avslutad ranked 1v1-serie mot Stan. Ger titeln Stan Slayer. <color=#7FE87F>1000g</color>
- <color=#7FD4FF>Lagutklassning</color> - vinn en enskild 2v2-match 5-0. Båda medlemmarna i det vinnande laget låser upp den; den gäller per match, inte per serie. <color=#7FE87F>500g</color>

<color=#FFD94D><b>FFA OCH ÖVERSÄTTARE</b></color>

FFA-sexan kräver en RANKAD FFA-lobby och är alla serverdömda.

- <color=#7FD4FF>Storstädning</color> - vinn en FFA 5-0: alla fem poängen dina och ingen annan konverterar en hel poäng, i en lobby som hade 3 eller fler spelare. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Objuden gäst</color> - samma sak med 4 eller fler i lobbyn. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Fientligt övertagande</color> - samma sak med 5 eller fler i lobbyn. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Massaker</color> - över 50 kills i en match. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Dödstal</color> - över 100 kills i en match. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Krossat hjärta</color> - förlora en match med 10 eller fler rondvinster som aldrig blev hela poäng. <color=#7FE87F>300g</color>

Utklassningarna nästlas: <color=#7FE87F>en 5-spelarutklassning låser upp alla tre på en gång, 900 guld totalt</color>. Med i lobbyn räknas truppen när lobbyn låstes, inte vilka som stannade till slutet - och förlorare som håller kvarvarande rondvinster bryter inte din utklassning; bara en konverterad hel poäng gör det. <color=#8A8A93>Killräkningar registreras bara när matchen rapporterades av en uppdaterad moddversion.</color>

Översättarnivåerna kommer från översättningsportalen, inte från matcher. En aktiv sträng är en godkänd översättning du föreslog eller granskade; att göra båda jobben på en sträng räknas en gång. Varje nivå ger också sin matchande titel (se <color=#7FD4FF>Titlar</color>).

- <color=#7FD4FF>Rosetta</color> - 10 aktiva strängar. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Dragoman</color> - 100 aktiva strängar. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Babel</color> - 1000 aktiva strängar. <color=#7FE87F>1000g</color>$s256$)
  , ('a4ae6fe168654f46', 'uk', '43b20143fadbcc200b573c5b37b0768ad48fa1ba', $s256$<color=#FFD94D><b>СТРІКИ</b></color>

Усі стріки - лише 1v1. Звичайні стріки рахують ігри; рейтингові рахують завершені серії.

- <color=#7FD4FF>Бездоганний</color> - п’ять перемог 5-0 поспіль. Рахуються і рейтингові, і звичайні; <color=#FF6666>будь-яка гра, що не є перемогою 5-0, скидає його</color>. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Клуб сотні</color> - 100 звичайних перемог поспіль. Звичайна поразка скидає; рейтингові ігри лічильника не чіпають. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Підкорювач звичайних</color> - 200 звичайних перемог поспіль. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Торкніться трави</color> - 500 звичайних перемог поспіль. <color=#7FE87F>1000g</color>
- <color=#7FD4FF>В ударі</color> - виграйте 25 завершених рейтингових серій поспіль. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Нестримний</color> - 50 рейтингових серій поспіль. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Безсмертний</color> - 100 рейтингових серій поспіль. <color=#7FE87F>500g</color>

<color=#FFD94D><b>РЕЙТИНГ, SLAYER І 2v2</b></color>

Рейтингові рубежі перевіряються щоразу, коли оновлюється ваш рейтинг 1v1 чи 2v2. Рухи рейтингу FFA їх не запускають.

- <color=#7FD4FF>Висхідна зірка</color> - досягніть рейтингу 1700. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Майстер</color> - досягніть рейтингу 1980. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Грандмайстер</color> - досягніть рейтингу 2330. <color=#7FE87F>1000g</color>
- <color=#7FD4FF>Sid Slayer</color> - виграйте завершену рейтингову серію 1v1 проти Sid. Дає титул Sid Slayer, який можна вдягнути. <color=#7FE87F>1000g</color>
- <color=#7FD4FF>Stan Slayer</color> - виграйте завершену рейтингову серію 1v1 проти Stan. Дає титул Stan Slayer. <color=#7FE87F>1000g</color>
- <color=#7FD4FF>Командний розгром</color> - виграйте одну гру 2v2 з рахунком 5-0. Відкривають обидва члени переможної команди; це за гру, не за серію. <color=#7FE87F>500g</color>

<color=#FFD94D><b>FFA І ПЕРЕКЛАДАЧІ</b></color>

Шістка FFA потребує РЕЙТИНГОВОГО лобі FFA, і всі вони серверні.

- <color=#7FD4FF>Генеральне прибирання</color> - виграйте FFA 5-0: усі п’ять очок ваші й ніхто інший не конвертує повного очка, у лобі, де сиділо 3 і більше гравців. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Незваний гість</color> - те саме з 4 і більше. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Вороже поглинання</color> - те саме з 5 і більше. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Шаленство</color> - понад 50 вбивств за одну гру. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Убивства</color> - понад 100 вбивств за одну гру. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Розбите серце</color> - програйте гру, тримаючи 10 і більше виграних раундів, що так і не стали повними очками. <color=#7FE87F>300g</color>

Сухі перемоги вкладаються одна в одну: <color=#7FE87F>один шатаут у лобі на 5 відкриває всі три одразу, 900 золота сумарно</color>. «Сиділо» означає ростер на момент фіксації лобі, а не тих, хто досидів до кінця, - і залишкові виграні раунди тих, хто програв, вашого шатауту не ламають; ламає лише конвертоване повне очко. <color=#8A8A93>Лічильники вбивств реєструються, лише коли гру звітувала актуальна версія мода.</color>

Рівні перекладачів приходять із порталу перекладів, не з матчів. Живий рядок - схвалений переклад, який ви запропонували або рецензували; обидві ролі на одному рядку рахуються один раз. Кожен рівень також дає відповідний титул (див. <color=#7FD4FF>Титули</color>).

- <color=#7FD4FF>Розетта</color> - 10 живих рядків. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Драгоман</color> - 100 живих рядків. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Вавилон</color> - 1000 живих рядків. <color=#7FE87F>1000g</color>$s256$)
  , ('a5b68a6c5bcde4fc', 'es', 'c3320119dd20477311675076c815e2caa5e43360', $s256$Netcode y Photon$s256$)
  , ('a5b68a6c5bcde4fc', 'ru', 'c3320119dd20477311675076c815e2caa5e43360', $s256$Неткод и Photon$s256$)
  , ('a5b68a6c5bcde4fc', 'sv', 'c3320119dd20477311675076c815e2caa5e43360', $s256$Nätkod & Photon$s256$)
  , ('a5b68a6c5bcde4fc', 'uk', 'c3320119dd20477311675076c815e2caa5e43360', $s256$Неткод і Photon$s256$)
  , ('a802c5f027c63d99', 'es', '8f74390c71443cd9546ba57bc48e3ca3fe9fa0fe', $s256$Silenciar audio al salir de la ventana: <color=#88FF88>SÍ</color>$s256$)
  , ('a802c5f027c63d99', 'ru', '8f74390c71443cd9546ba57bc48e3ca3fe9fa0fe', $s256$Глушить звук вне окна: <color=#88FF88>ВКЛ</color>$s256$)
  , ('a802c5f027c63d99', 'sv', '8f74390c71443cd9546ba57bc48e3ca3fe9fa0fe', $s256$Tysta ljudet när du byter fönster: <color=#88FF88>PÅ</color>$s256$)
  , ('a802c5f027c63d99', 'uk', '8f74390c71443cd9546ba57bc48e3ca3fe9fa0fe', $s256$Глушити звук поза вікном: <color=#88FF88>УВІМК</color>$s256$)
  , ('a824f29d33590ce9', 'es', '9deba99e00d05dced7ec579c859f8b250bb287b9', $s256$<color=#FFD94D><b>CÓMO TE VALORA EL EQUILIBRADOR</b></color>

- El equilibrador usa tu rating 2v2 cuando ya es fiable: 10 o más series completadas, o antes si el rating se ha asentado (su incertidumbre ha bajado lo suficiente). Hasta entonces, tu rating 1v1 lo sustituye.
- Los ratings se congelan al entrar a la cola - el equilibrador trabaja con esos valores.
- El servidor prueba las tres formas de partiros a los cuatro en parejas y se queda con la partición con menor diferencia de rating total por equipo.

<color=#FFD94D><b>EL INTERCAMBIO A MITAD DE SERIE, CON PRECISIÓN</b></color>

- Solo se dispara en series autoequilibradas - las salas manuales nunca intercambian.
- El diseño: tras un juego con margen de 3 o más puntos, el ganador más débil cambia de sitio con el perdedor más fuerte para el siguiente juego, bajo la misma regla de rating 2v2-si-fiable, si-no-1v1 de arriba.
- <color=#FF6666>Aún no activo:</color> el cambio de equipo dentro del juego todavía está por publicarse, así que por ahora el equilibrador solo apunta el intercambio que habría hecho y los equipos quedan fijos toda la serie.

<color=#FFD94D><b>QUIÉN ES NARANJA, QUIÉN ES AZUL</b></color>

- El Equipo 1 es el equipo naranja del juego; el Equipo 2 es el azul. Dentro de un equipo, el Steam ID menor toma la primera plaza.
- En una sala manual puedes reclamar el Equipo 1 o el 2 antes del cierre. La cola automática siempre ejecuta el equilibrador e ignora las preferencias.
- Un equipo puede además llevar el color de cuerpo equipado de un miembro como identidad visible, decidido una vez al crearse la serie: un único portador de color da nombre al equipo, dos portadores es una moneda al aire, ninguno significa vanilla. En un duelo espejo, el Equipo 2 recurre al color de su otro miembro. <color=#8A8A93>Solo visual - el color de cuerpo real de nadie cambia.</color>

<color=#FFD94D><b>DESCONEXIONES</b></color>

- <color=#FF6666>Rendición con ventaja:</color> si el otro equipo se desconecta de un juego que llevaba 2 o más puntos totales mientras TU equipo ya va un juego arriba en la serie, la serie entera se completa a tu favor en el acto, con rating y oro completos. No puedes dejar un 2v2 para esquivar una derrota cuando ya vas un juego abajo.
- Cualquier otra DC no conlleva NINGUNA sanción automática: la serie se aparta para resolución manual de un admin, y cada juego ya reportado se mantiene.
- <color=#7FE87F>Reanudación pegajosa:</color> si los mismos cuatro jugadores reencolan en unos 30 minutos, el emparejador os vuelve a fijar en esa serie - equipos originales, marcador guardado.

<color=#FFD94D><b>RECOMPENSAS, POR PLAZA</b></color>

- La XP y el oro se acumulan por plaza de jugador dentro de la serie, así que el panel muestra el +g y +xp propios de cada jugador, y las columnas de Oro/XP de por vida cuentan solo el juego 2v2.
- El multiplicador de tier usa el PROMEDIO de los ratings 2v2 de los dos rivales; un jugador aún sin rating 2v2 cuenta como 1500 - y 1500 ya cae en el tier Intermedio x1.5, así que una sala recién estrenada paga por encima de la base.$s256$)
  , ('a824f29d33590ce9', 'ru', '9deba99e00d05dced7ec579c859f8b250bb287b9', $s256$<color=#FFD94D><b>КАК БАЛАНСИРОВЩИК ТЕБЯ ОЦЕНИВАЕТ</b></color>

- Балансировщик использует твой рейтинг 2v2, как только тот заслуживает доверия: 10 и больше завершённых серий, или раньше, когда рейтинг устоялся (его неопределённость достаточно упала). До тех пор вместо него берётся твой рейтинг 1v1.
- Рейтинги снимаются в момент входа в очередь - балансировщик работает с этими значениями.
- Сервер пробует все три способа разбить вашу четвёрку на пары и оставляет разбиение с наименьшей разницей суммарного рейтинга команд.

<color=#FFD94D><b>ОБМЕН ПОСРЕДИ СЕРИИ, ТОЧНО</b></color>

- Он срабатывает только в автосбалансированных сериях - ручные лобби не меняются никогда.
- Замысел: после игры с разницей очков 3 и больше слабейший из победителей меняется местами с сильнейшим из проигравших на следующую игру, по тому же правилу «2v2, если заслуживает доверия, иначе 1v1».
- <color=#FF6666>Пока не в игре:</color> внутриигровая смена команды ещё не вышла, так что пока балансировщик лишь записывает обмен, который сделал бы, а команды закреплены на всю серию.

<color=#FFD94D><b>КТО ОРАНЖЕВЫЙ, КТО СИНИЙ</b></color>

- Команда 1 - внутриигровая оранжевая; команда 2 - синяя. Внутри команды первый слот берёт меньший Steam ID.
- В ручном лобби можно занять Команду 1 или Команду 2 до фиксации. Автоочередь всегда запускает балансировщик и игнорирует предпочтения.
- Команда может нести надетый цвет тела одного из участников как свою отображаемую принадлежность, решается один раз при создании серии: единственный обладатель цвета называет команду, два обладателя - подброс монетки, никого - ваниль. В зеркальном матче Команда 2 откатывается на цвет второго участника. <color=#8A8A93>Только отображение - ничей реальный цвет тела не меняется.</color>

<color=#FFD94D><b>ОТКЛЮЧЕНИЯ</b></color>

- <color=#FF6666>Форфейт лидеру:</color> если другая команда отключается из игры, где было 2 и больше суммарных очков, пока ТВОЯ команда уже ведёт по играм серии, вся серия немедленно завершается в твою пользу, с полным рейтингом и золотом. Нельзя уйти из 2v2, чтобы увернуться от поражения, когда ты уже уступаешь по играм.
- Любой другой DC не несёт НИКАКОГО автоматического наказания: серия откладывается на ручное решение админа, и каждая уже отправленная игра стоит.
- <color=#7FE87F>Липкое возобновление:</color> если те же четыре игрока встают в очередь в пределах примерно 30 минут, подбор возвращает вас на ту серию - исходные команды, счёт сохранён.

<color=#FFD94D><b>НАГРАДЫ, ПО СЛОТАМ</b></color>

- XP и золото копятся на каждый игровой слот внутри серии, так что панель показывает собственные +g и +xp каждого игрока, а колонки пожизненных Gold/XP считают только игру в 2v2.
- Множитель тира использует СРЕДНЕЕ рейтингов двух соперников по 2v2; игрок без рейтинга 2v2 считается как 1500 - а 1500 уже лежит в тире Средний с x1.5, так что свежее лобби платит выше базы.$s256$)
  , ('a824f29d33590ce9', 'sv', '9deba99e00d05dced7ec579c859f8b250bb287b9', $s256$<color=#FFD94D><b>SÅ BEDÖMER BALANSERAREN DIG</b></color>

- Balanseraren använder din 2v2-rating när den går att lita på: 10 eller fler avslutade serier, eller tidigare när ratingen har satt sig (osäkerheten har sjunkit tillräckligt). Tills dess används din 1v1-rating.
- Ratingar snapshotas när du går med i kön - balanseraren arbetar med de värdena.
- Servern provar alla tre sätt att dela upp er fyra i par och behåller uppdelningen med minst skillnad i total lagrating.

<color=#FFD94D><b>BYTET MITT I SERIEN, I DETALJ</b></color>

- Det gäller bara autobalanserade serier - manuella lobbyer byter aldrig.
- Designen: efter en match med en poängmarginal på 3 eller mer byter den svagaste vinnaren plats med den starkaste förloraren inför nästa match, enligt samma regel som ovan (2v2 om betrodd, annars 1v1).
- <color=#FF6666>Inte aktivt ännu:</color> lagbytet i spelet är inte färdiglevererat, så tills vidare loggar balanseraren bara det byte den skulle ha gjort och lagen förblir låsta hela serien.

<color=#FFD94D><b>VEM ÄR ORANGE, VEM ÄR BLÅ</b></color>

- Lag 1 är det orangea laget i spelet; Lag 2 är blått. Inom ett lag tar det lägre Steam-ID:t första platsen.
- I en manuell lobby kan du göra anspråk på Lag 1 eller Lag 2 före låsningen. Autokön kör alltid balanseraren och ignorerar önskemål.
- Ett lag kan också bära en medlems utrustade kroppsfärg som visningsidentitet, avgjort en gång när serien skapas: en ensam färginnehavare namnger laget, två innehavare blir slantsingling, ingen betyder vanilla. I en spegelmatch faller Lag 2 tillbaka på sin andra medlems färg. <color=#8A8A93>Endast visning - ingens faktiska kroppsfärg ändras.</color>

<color=#FFD94D><b>DISCONNECTS</b></color>

- <color=#FF6666>Forfeit vid ledning:</color> om andra laget DC:ar ur en match som hade 2 eller fler totala poäng medan DITT lag redan leder serien, avslutas hela serien till er på fläcken, med full rating och fullt guld. Man kan inte lämna en 2v2 för att slippa en förlust när man ligger under med en match.
- Alla andra DC:ar ger INGET automatiskt straff: serien läggs åt sidan för manuell adminhantering, och varje redan rapporterad match står kvar.
- <color=#7FE87F>Klistrig återupptagning:</color> om samma fyra spelare köar om inom cirka 30 minuter låser matchningen er tillbaka på den serien - ursprungliga lag, ställningen kvar.

<color=#FFD94D><b>BELÖNINGAR, PER PLATS</b></color>

- XP och guld samlas per spelarplats i serien, så panelen visar varje spelares egna +g och +xp, och livstidskolumnerna för guld/XP räknar enbart 2v2-spel.
- Tiermultiplikatorn använder GENOMSNITTET av de två motståndarnas 2v2-rating; en spelare utan 2v2-rating räknas som 1500 - och 1500 ligger redan i Medel-tiern på x1.5, så en helt ny lobby betalar över bas.$s256$)
  , ('a824f29d33590ce9', 'uk', '9deba99e00d05dced7ec579c859f8b250bb287b9', $s256$<color=#FFD94D><b>ЯК БАЛАНСУВАЛЬНИК ВАС ОЦІНЮЄ</b></color>

- Балансувальник використовує ваш рейтинг 2v2, щойно той стає надійним: 10 і більше завершених серій, або раніше, коли рейтинг устоявся (його невизначеність достатньо впала). До того замість нього стоїть ваш рейтинг 1v1.
- Рейтинги знімаються в момент входу в чергу - балансувальник працює з тими значеннями.
- Сервер пробує всі три способи розбити вас чотирьох на пари і лишає розбиття з найменшою різницею сумарного рейтингу команд.

<color=#FFD94D><b>ОБМІН ПОСЕРЕД СЕРІЇ, ТОЧНО</b></color>

- Він спрацьовує лише в автозбалансованих серіях - ручні лобі не міняються ніколи.
- Задум: після гри з різницею у 3 і більше очок найслабший переможець міняється місцями з найсильнішим із переможених на наступну гру, за тим самим правилом «2v2, якщо надійний, інакше 1v1», що вище.
- <color=#FF6666>Ще не працює:</color> внутрішньоігровий обмін командами ще в розробці, тож поки що балансувальник лише логує обмін, який зробив би, а команди зафіксовані на всю серію.

<color=#FFD94D><b>ХТО ПОМАРАНЧЕВИЙ, ХТО СИНІЙ</b></color>

- Команда 1 - внутрішньоігрова помаранчева команда; команда 2 - синя. Всередині команди менший Steam ID бере перший слот.
- У ручному лобі можна зайняти Команду 1 чи Команду 2 до фіксації. Авточерга завжди запускає балансувальник і ігнорує побажання.
- Команда також може нести вдягнений колір тіла свого учасника як показову ідентичність, що вирішується раз при створенні серії: єдиний власник кольору називає команду, два власники - підкидання монетки, жодного - ваніль. У дзеркальному матчі Команда 2 відкочується до кольору свого іншого учасника. <color=#8A8A93>Лише показ - нічий справжній колір тіла не змінюється.</color>

<color=#FFD94D><b>ДИСКОНЕКТИ</b></color>

- <color=#FF6666>Форфейт лідера:</color> якщо інша команда дисконектить із гри, що мала 2 і більше сумарних очок, поки ВАША команда вже веде на гру в серії, вся серія завершується на вашу користь на місці, з повним рейтингом і золотом. Не можна покинути 2v2, щоб ухилитися від поразки, коли ви вже поступаєтеся грою.
- Будь-який інший DC не несе автоматичного покарання: серія відкладається на ручний розбір адміном, і кожна вже звітована гра в силі.
- <color=#7FE87F>Липке відновлення:</color> якщо ті самі четверо повторно стануть у чергу впродовж ~30 хвилин, підбір зафіксує вас назад на ту серію - первісні команди, рахунок збережено.

<color=#FFD94D><b>НАГОРОДИ, ПО СЛОТАХ</b></color>

- XP і золото накопичуються на слот гравця всередині серії, тож панель показує кожному його власні +g і +xp, а колонки золота/XP за весь час рахують лише гру у 2v2.
- Множник рівня використовує СЕРЕДНЄ рейтингів 2v2 двох суперників; гравець ще без рейтингу 2v2 рахується як 1500 - а 1500 уже сидить у рівні Середній x1.5, тож свіже лобі платить вище бази.$s256$)
  , ('aa14ce6adac1c333', 'es', 'ade6d8a331450ec2260ca05e486f8e48e21d0df4', $s256$Mejorar en ROUNDS competitivo es mecánico, no místico: disciplina de bloqueo, conciencia del netcode, saber draftear y leer los números que el mod ya guarda sobre ti. Cada consejo de abajo va atado a una mecánica real que puedes ir a probar.

<color=#FFD94D><b>DISCIPLINA DE BLOQUEO</b></color>

El bloqueo es la habilidad que decide las partidas ajustadas, y tiene un modelo de costes que conviene respetar.

- Un bloqueo que no absorbe nada gasta igualmente todo su enfriamiento. <color=#FF6666>Bloquear en pánico al oír un gatillo no te compra nada y regala a tu rival una ventana gratis mientras recarga.</color>
- Reacciona a la bala, no al gatillo: mira el arma del rival y el propio disparo, y entrena bloqueos de reacción hasta que sean reflejo.
- Una activación puede absorber varias balas. Un bloqueo guardado para una ráfaga o una descarga rebotada trabaja mucho más que uno gastado en un perdigón suelto.
- Las cartas de efecto al bloquear multiplican la habilidad de timing: las repeticiones de Echo y los dashes de Shield Charge pertenecen todos al clic derecho que los inició, así que un bloqueo bien medido dispara la cadena entera.
- Un tick de veneno o quemadura que cae dentro de tu bloqueo se consume - se borra, no se aplaza - así que bloquear envenenado es prevención de daño real. <color=#8A8A93>(Una sala que mezcla versiones del mod actuales y desactualizadas puede degradar a veneno que ignora bloqueos, para todos por igual - ver <color=#7FD4FF>Vanilla sigue siendo vanilla</color>.)</color>

<color=#FFD94D><b>JUEGA CON EL NETCODE</b></color>

- ROUNDS no es peer-to-peer. Ambos jugadores hablan con un servidor intermedio de Photon en la región de la sala; el jugador naranja no es host y no tiene ventaja de host. <color=#7FE87F>Tu ping a la región es el número que importa.</color>
- Cada cliente simula cada bala, y el daño tiene autoridad del tirador: lo que un disparo te quita se decide en la máquina del tirador. Su pantalla ve tu movimiento tarde, y por eso puedes morir un paso después de llegar a cobertura - y por eso quien asoma primero ve al otro antes de ser visto.
- Tu bloqueo es la imagen especular: ocurre primero en tu máquina y llega a la simulación del rival un compás después. Un bloqueo levantado un pelín antes por reacción te protege en situaciones donde uno al fotograma perfecto no, porque tu último fotograma ya es pasado en su pantalla.
- Lo que parece una hitbox rota es casi siempre este desajuste: ping, interpolación, cartas de tamaño y disparos rebotados. El mod nunca toca las hitboxes (ver <color=#7FD4FF>Netcode y Photon</color>).
- La tasa de fotogramas es una stat de gameplay oculta en ROUNDS vanilla. El Grow vanilla compone su daño por fotograma: alrededor de x1.5 para un tirador a 60 FPS contra x1.07 a 400 FPS con una sola copia, y acumular ensancha la brecha rápido. En salas del mod - y en partidas privadas donde todos llevan el mod, están al día y tienen Ranked activado - Grow se normaliza para que la tasa de fotogramas deje de decidir el daño (un tirón fuerte aún puede crecer un poco de menos - el error solo apunta hacia abajo); contra clientes vanilla o desactualizados la regla vanilla se mantiene. <color=#7FE87F>Una tasa de fotogramas estable es una ventaja competitiva real</color> - la pestaña Ajustes tiene una sección de rendimiento exactamente para esto.

<color=#FFD94D><b>DRAFTEA PARA UNA BUILD</b></color>

- Las cartas son un plan, no una hoja de stats. El robo de vida cura desde la cadena de daño infligido, y los ticks de daño en el tiempo pasan por esa misma cadena - robo de vida más veneno es un motor, no una coincidencia. Echo y Shield Charge convierten la habilidad de bloqueo en ofensiva. Elige la segunda carta para la primera.
- Lee lo que una carta hace de verdad, y luego pruébala. El texto de la carta y su comportamiento son cosas distintas: Chase mostró durante años una línea de '+30% de Vida' que la carta vanilla nunca otorgó (el mod quitó la línea). Las partidas de sandbox nunca se registran, así que experimenta libremente allí.
- La regla de Mismas cartas del FFA es el mejor profesor de draft del mod: con ella activada, el robo N de todos ofrece las mismas candidatas en el mismo orden, así que una derrota no puede achacarse a la suerte del robo - la diferencia fueron las decisiones. La lista de FFA recientes guarda cada elección en orden (pasa el cursor por la línea de cartas de un jugador), así puedes repasar el draft del ganador contra el tuyo.
- Tu historial de partidas 1v1 guarda las elecciones de ambos jugadores en orden para cada partida. Tras una derrota ajustada, relee el draft antes de reencolar.

<color=#FFD94D><b>USA TUS PROPIOS NÚMEROS</b></color>

Mis stats registra más sobre tu juego de lo que probablemente crees. Qué significan las stats principales:

- <color=#7FD4FF>% de acierto</color> - cuenta balas, no clics: un clic de Buckshot cuenta cada perdigón, y solo cuentan los impactos directos y no bloqueados a enemigos - los ticks de veneno y quemadura, las explosiones y los autoimpactos nunca. Una build de escopeta lee bajo por construcción. <color=#FF6666>Compara una build contra sí misma en el tiempo, nunca contra el número de un francotirador.</color>
- <color=#7FD4FF>Éxito de bloqueo</color> - un clic derecho sin enfriamiento es un intento, y como máximo un éxito por intento absorba las balas que absorba. Los bloqueos preventivos que no encuentran bala son normales, no un error - mira la tendencia entre partidas, no una sola.
- Las gráficas de línea de tiempo muestrean cada 3 a 5 segundos y siempre abarcan la partida entera. Úsalas para encontrar dónde giran las partidas: la línea del marcador muestra cuándo se escapó una ventaja, y las líneas de acierto y daño muestran qué cambió en ese momento.
- Una partida 1v1 registra el ping medio y el peor más los eventos de congelación (parones de fotograma de más de medio segundo); las partidas de equipo y FFA llevan datos de conexión más ligeros. Antes de culpar a tu puntería por una mala partida, mira si los números de conexión ya la explican (ver <color=#7FD4FF>Cómo se registran las stats</color>).

<color=#FFD94D><b>MIRA A JUGADORES MEJORES</b></color>

- Las partidas en vivo de la pestaña Clasificación llevan un botón VER cuando pueden verse. Un asiento de espectador muestra la partida real desde dentro de la sala, y cómo un jugador top gasta bloqueos y draftea bajo presión enseña más rápido que encolar a ciegas. Las salas FFA pueden verse igual desde la pestaña FFA.
- El bot de Discord responde preguntas de mecánicas con datos en vivo: pregúntale 'cómo funciona el bloqueo', o cuánto elo ganarías contra un jugador concreto y calcula la previsión Glicko real para ambos lados, probabilidad de victoria incluida (ambas cuentas necesitan Discord vinculado).$s256$)
  , ('aa14ce6adac1c333', 'ru', 'ade6d8a331450ec2260ca05e486f8e48e21d0df4', $s256$Стать лучше в соревновательном ROUNDS - вопрос механики, а не мистики: дисциплина блока, понимание неткода, драфт и чтение чисел, которые мод уже ведёт о тебе. Каждый совет ниже привязан к реальной механике, которую можно пойти и проверить.

<color=#FFD94D><b>ДИСЦИПЛИНА БЛОКА</b></color>

Блок - навык, решающий близкие игры, и у него есть модель стоимости, которую стоит уважать.

- Блок, не поглотивший ничего, всё равно тратит полный откат. <color=#FF6666>Паника-блок на звук выстрела не покупает ничего и дарит сопернику свободное окно, пока щит перезаряжается.</color>
- Реагируй на пулю, а не на звук: смотри на пушку соперника и сам выстрел и тренируй блоки по реакции, пока они не станут рефлексом.
- Одна активация может поглотить несколько пуль. Блок, придержанный под очередь или отражённый залп, делает куда больше работы, чем потраченный на одинокую дробинку.
- Карты с эффектами от блока умножают навык тайминга: повторы Echo и рывки Shield Charge принадлежат тому правому клику, что их начал, - одно выверенное нажатие запускает всю цепочку.
- Тик яда или горения, легший внутрь твоего блока, потрачен - стёрт, а не отложен, - так что блок под ядом - это настоящее предотвращение урона. <color=#8A8A93>(Комната, смешивающая актуальные и устаревшие версии мода, может откатиться к «яд игнорирует блоки», для всех одинаково - см. <color=#7FD4FF>Ваниль остаётся ванилью</color>.)</color>

<color=#FFD94D><b>ИГРАЙ ВМЕСТЕ С НЕТКОДОМ</b></color>

- ROUNDS - не peer-to-peer. Оба игрока говорят с релейным сервером Photon в регионе комнаты; оранжевый игрок не хост и не имеет преимущества хоста. <color=#7FE87F>Твой пинг до региона - то число, которое имеет значение.</color>
- Каждый клиент симулирует каждую пулю, и урон авторитетен для стрелка: сколько выстрел с тебя снимет, решается на машине стрелка. Его экран видит твоё движение с опозданием - вот почему можно умереть на шаг после укрытия, и вот почему выглядывающий первым видит другого раньше, чем его увидят.
- Твой блок - зеркальное отражение: он происходит сначала на твоей машине и доходит до симуляции соперника тактом позже. Блок, поднятый по реакции чуть заранее, защищает там, где кадрово-идеальный не защищает, потому что твой последний кадр на их экране - уже прошлое.
- То, что читается как сломанный хитбокс, почти всегда это рассогласование: пинг, интерполяция, карты размера и отражённые выстрелы. Мод хитбоксы не трогает никогда (см. <color=#7FD4FF>Неткод и Photon</color>).
- Частота кадров - скрытый игровой стат в ванильном ROUNDS. Ванильный Grow накапливает урон покадрово: около x1.5 у стрелка на 60 FPS против x1.07 на 400 FPS за одну копию, и стаки быстро расширяют разрыв. В модовых комнатах - и в приватных матчах, где все на моде, актуальны и с включённым Ranked - Grow нормализован, и частота кадров перестаёт решать урон (тяжёлый статтер всё ещё может слегка недорастить - ошибка всегда смотрит только вниз); против ванильных или устаревших клиентов действует ванильное правило. <color=#7FE87F>Стабильная частота кадров - реальное соревновательное преимущество</color> - на вкладке Настройки для этого есть раздел производительности.

<color=#FFD94D><b>ДРАФТИ ПОД БИЛД</b></color>

- Карты - это план, а не таблица статов. Вампиризм лечит с цепочки нанесённого урона, и тики урона со временем идут через ту же цепочку - вампиризм плюс яд это двигатель, а не совпадение. Echo и Shield Charge превращают навык блока в атаку. Бери вторую карту под первую.
- Читай, что карта реально делает, и проверяй. Текст карты и поведение карты - разные вещи: Chase годами показывал строку «+30% Health», которую ванильная карта никогда не давала (мод убрал строку). Игры в песочнице никогда не записываются - экспериментируй там свободно.
- Правило «Те же карты» в FFA - лучший учитель драфта в моде: когда оно включено, N-я раздача у всех предлагает одни и те же карты в одном порядке, так что поражение не списать на удачу раздачи - разницей были решения. Список Недавних FFA хранит каждый пик в порядке выбора (наведи на строку карт игрока), так что можно переиграть драфт победителя против своего.
- Твоя история матчей 1v1 хранит пики обоих игроков по порядку для каждой игры. После близкого поражения перечитай драфт, прежде чем вставать в очередь снова.

<color=#FFD94D><b>ПОЛЬЗУЙСЯ СВОИМИ ЧИСЛАМИ</b></color>

Моя статистика отслеживает о твоей игре больше, чем ты, вероятно, думаешь. Что значат главные статы:

- <color=#7FD4FF>% попаданий</color> - считает пули, а не клики: один клик Buckshot считает каждую дробинку, и считаются только прямые незаблокированные попадания по врагам - тики яда и горения, взрывы и самоудары не считаются никогда. Дробовичный билд читается низким по построению. <color=#FF6666>Сравнивай билд с самим собой во времени, никогда - с числом снайпера.</color>
- <color=#7FD4FF>Успешность блока</color> - один правый клик вне отката - одна попытка, и максимум один успех на попытку, сколько бы пуль она ни поглотила. Превентивные блоки, не встретившие пулю, - норма, а не ошибка: смотри на тренд по играм, а не на одну игру.
- Графики таймлайнов снимают точку каждые 3-5 секунд и всегда покрывают всю игру. Ищи по ним, где игры переворачиваются: таймлайн счёта показывает, когда уплыло преимущество, а линии попаданий и урона - что изменилось в этот момент.
- Игра 1v1 записывает средний и худший пинг плюс события фризов (остановки кадров дольше полсекунды); командные и FFA-игры несут облегчённые данные соединения. Прежде чем винить прицел за одну плохую игру, проверь, не объясняют ли её числа соединения (см. <color=#7FD4FF>Как считается статистика</color>).

<color=#FFD94D><b>СМОТРИ ИГРОКОВ СИЛЬНЕЕ СЕБЯ</b></color>

- Живые игры на вкладке Таблица лидеров несут кнопку СМОТРЕТЬ, когда их можно смотреть. Зрительское место показывает настоящий матч изнутри комнаты, и то, как топ-игрок тратит блоки и драфтит под давлением, учит быстрее, чем слепая очередь. Лобби FFA так же смотрятся с вкладки FFA.
- Discord-бот отвечает на вопросы о механиках живыми данными: спроси его «как работает блок» - или сколько elo ты получишь против названного игрока, и он посчитает настоящий превью Glicko для обеих сторон, с вероятностью победы (обоим аккаунтам нужен привязанный Discord).$s256$)
  , ('aa14ce6adac1c333', 'sv', 'ade6d8a331450ec2260ca05e486f8e48e21d0df4', $s256$Att bli bättre i tävlings-ROUNDS är mekaniskt, inte mystiskt: blockdisciplin, nätkodsmedvetenhet, draftande, och att läsa siffrorna modden redan för över dig. Varje tips nedan är knutet till en verklig mekanik du kan gå och testa.

<color=#FFD94D><b>BLOCKDISCIPLIN</b></color>

Blockning är färdigheten som avgör jämna matcher, och den har en kostnadsmodell värd att respektera.

- Ett block som inget absorberar spenderar ändå hela sin cooldown. <color=#FF6666>Panikblock vid ljudet av en avtryckare köper dig ingenting och ger motståndaren ett gratisfönster medan det laddar om.</color>
- Reagera på kulan, inte på avtryckaren: titta på motståndarens vapen och själva skottet, och nöt reaktionsblock tills de sitter i ryggmärgen.
- En aktivering kan absorbera flera kulor. Ett block som hålls för en skur eller en studsad salva gör långt mer nytta än ett spenderat på en ensam hagelkula.
- Blockeffektkort multiplicerar timingskicklighet: Echo-repriser och Shield Charge-rusher tillhör alla högerklicket som startade dem, så ett vältajmat block avfyrar hela kedjan.
- En gift- eller branntick som landar i ditt block förbrukas - raderas, inte skjuts upp - så att blocka medan du är förgiftad är verklig skadeprevention. <color=#8A8A93>(Ett rum som blandar aktuella och föråldrade moddversioner kan falla tillbaka till att gift ignorerar block, lika för alla - se <color=#7FD4FF>Vanilla förblir vanilla</color>.)</color>

<color=#FFD94D><b>SPELA MED NÄTKODEN</b></color>

- ROUNDS är inte peer-to-peer. Båda spelarna pratar med en Photon-reläserver i rummets region; den orangea spelaren är ingen värd och har ingen värdfördel. <color=#7FE87F>Din ping till regionen är siffran som spelar roll.</color>
- Varje klient simulerar varje kula, och skada är skytteauktoritativ: vad ett skott drar av dig avgörs på skyttens maskin. Deras skärm ser din rörelse sent, vilket är varför du kan dö ett steg efter att du nått skydd - och varför den som kikar fram först ser den andra innan den själv syns.
- Ditt block är spegelbilden: det sker på din maskin först och når motståndarens simulering ett slag senare. Ett block som höjs aningen tidigt på reaktion skyddar dig i lägen där ett bildruteperfekt inte gör det, eftersom din senaste bildruta redan är dåtid på deras skärm.
- Det som ser ut som en trasig hitbox är nästan alltid den här förskjutningen: ping, interpolering, storlekskort och studsade skott. Modden rör aldrig hitboxar (se <color=#7FD4FF>Nätkod & Photon</color>).
- Bildfrekvens är ett dolt spelvärde i vanilla-ROUNDS. Vanilla-Grow ackumulerar sin skada per bildruta: runt x1.5 för en 60 FPS-skytt mot x1.07 vid 400 FPS för en enda kopia, och stapling vidgar gapet snabbt. I moddens rum - och i privata matcher där alla är moddade, aktuella och har Ranked aktiverat - normaliseras Grow så att bildfrekvensen slutar avgöra skadan (ett tungt hack kan fortfarande ge lite för lite tillväxt - felet pekar bara nedåt); mot vanilla- eller föråldrade klienter står vanilla-regeln. <color=#7FE87F>En stabil bildfrekvens är en verklig tävlingsfördel</color> - fliken Inställningar har en prestandasektion för exakt det här.

<color=#FFD94D><b>DRAFTA FÖR EN BUILD</b></color>

- Kort är en plan, inte ett statblad. Lifesteal helar från utdelad skada-kedjan, och skada över tid-ticks går genom samma kedja - lifesteal plus gift är en motor, inte en slump. Echo och Shield Charge gör blockskicklighet till offensiv. Drafta det andra kortet för det första.
- Läs vad ett kort faktiskt gör, testa det sedan. Korttext och kortbeteende är två olika saker: Chase visade i åratal en '+30% Health'-rad som vanilla-kortet aldrig faktiskt gav (modden tog bort raden). Sandboxmatcher registreras aldrig, så experimentera fritt där.
- FFA-regeln Samma kort är moddens bästa draftlärare: när den är på erbjuds alla samma kandidater i samma ordning i sin N:te dragning, så en förlust kan inte skyllas på dragningstur - skillnaden var valen. Listan Senaste FFA sparar varje val i valordning (håll pekaren över en spelares kortrad), så du kan spela upp vinnarens draft mot din egen.
- Din 1v1-matchhistorik lagrar båda spelarnas val i ordning för varje match. Efter en jämn förlust: läs om draften innan du köar om.

<color=#FFD94D><b>ANVÄND DINA EGNA SIFFROR</b></color>

Min statistik spårar mer om ditt spel än du nog anar. Vad huvudvärdena betyder:

- <color=#7FD4FF>Träff-%</color> - räknar kulor, inte klick: ett Buckshot-klick räknar varje hagel, och bara direkta, oblockerade träffar på fiender räknas - gift- och brännticks, explosioner och självträffar gör det aldrig. En hagelbuild läser lågt per konstruktion. <color=#FF6666>Jämför en build mot sig själv över tid, aldrig mot en prickskytts siffra.</color>
- <color=#7FD4FF>Blockframgång</color> - ett högerklick utan cooldown är ett försök, och högst en framgång per försök oavsett hur många kulor det absorberade. Förebyggande block som inte möter någon kula är normalt, inte ett misstag - titta på trenden över matcher, inte på en match.
- Tidslinjegrafer samplar var 3:e till 5:e sekund och spänner alltid över hela matchen. Använd dem för att hitta var matcher vänder: poängtidslinjen visar när en ledning gled iväg, och träff- och skadelinjerna visar vad som ändrades när den gjorde det.
- En 1v1-match registrerar snitt- och värstaping plus frysningar (bildstopp över en halv sekund); lag- och FFA-matcher bär lättare anslutningsdata. Innan du skyller en dålig match på ditt sikte: kolla om anslutningssiffrorna redan förklarar den (se <color=#7FD4FF>Så räknas statistiken</color>).

<color=#FFD94D><b>TITTA PÅ BÄTTRE SPELARE</b></color>

- Pågående matcher på Topplista-fliken bär en TITTA-knapp när de går att åskåda. En åskådarplats visar den riktiga matchen inifrån rummet, och hur en toppspelare spenderar block och draftar under press lär snabbare än att köa blint. FFA-lobbyer kan ses från FFA-fliken på samma sätt.
- Discord-botten svarar på mekanikfrågor med livedata: fråga den 'hur funkar blockning', eller fråga hur mycket elo du skulle vinna mot en namngiven spelare så räknar den den verkliga Glicko-förhandsvisningen för båda sidor, vinstchans inkluderad (båda kontona behöver länkad Discord).$s256$)
  , ('aa14ce6adac1c333', 'uk', 'ade6d8a331450ec2260ca05e486f8e48e21d0df4', $s256$Ставати кращим у змагальному ROUNDS - механіка, а не містика: дисципліна блокування, розуміння неткоду, драфт і читання чисел, які мод уже веде про вас. Кожна порада нижче прив’язана до реальної механіки, яку можна піти й перевірити.

<color=#FFD94D><b>ДИСЦИПЛІНА БЛОКУВАННЯ</b></color>

Блокування - навичка, що вирішує близькі ігри, і в неї є модель вартості, яку варто поважати.

- Блок, що нічого не поглинув, усе одно витрачає повний відкат. <color=#FF6666>Панічний блок на звук пострілу не купує нічого і дарує суперникові вільне вікно, поки він перезаряджається.</color>
- Реагуйте на кулю, а не на тригер: дивіться на зброю суперника і сам постріл, і тренуйте блоки-на-реакцію до рефлексу.
- Одна активація може поглинути кілька куль. Блок, потриманий під чергу чи відбитий залп, робить значно більше роботи, ніж витрачений на самотню дробинку.
- Карти блок-ефектів множать навичку таймінгу: повтори Echo і ривки Shield Charge усі належать правому кліку, що їх почав, тож один влучний блок запускає весь ланцюжок.
- Тік отрути чи горіння, що потрапив у ваш блок, спожито - стерто, а не відкладено, тож блокувати під отрутою - справжнє запобігання шкоді. <color=#8A8A93>(Кімната зі змішаними актуальною і застарілою версіями мода може відкотитися до «отрута ігнорує блоки», для всіх однаково - див. <color=#7FD4FF>Ваніль лишається ваніллю</color>.)</color>

<color=#FFD94D><b>ГРАЙТЕ РАЗОМ ІЗ НЕТКОДОМ</b></color>

- ROUNDS - не peer-to-peer. Обидва гравці говорять із релейним сервером Photon у регіоні кімнати; помаранчевий гравець - не хост і не має хостової переваги. <color=#7FE87F>Ваш пінг до регіону - число, яке важить.</color>
- Кожен клієнт симулює кожну кулю, а шкода авторитетна для стрільця: що постріл зніме з вас, вирішується на машині стрільця. Їхній екран бачить ваш рух із запізненням - тому ви можете померти на крок після того, як досягли укриття, і тому той, хто визирає першим, бачить іншого раніше, ніж його побачать.
- Ваш блок - дзеркальне відображення: він стається спершу на вашій машині і досягає симуляції суперника на такт пізніше. Блок, піднятий трохи заздалегідь на реакції, захищає вас там, де кадрово-точний не встигає, бо ваш останній кадр на їхньому екрані - уже минуле.
- Те, що читається як зламаний хітбокс, майже завжди саме цей розрив: пінг, інтерполяція, карти розміру, відбиті постріли. Мод хітбоксів не торкається ніколи (див. <color=#7FD4FF>Неткод і Photon</color>).
- Частота кадрів - прихований ігровий стат у ванільному ROUNDS. Ванільний Grow нарощує шкоду щокадру: близько x1.5 у стрільця на 60 FPS проти x1.07 на 400 FPS за одну копію, і стакання швидко розширює розрив. У модових кімнатах - і в приватних матчах, де всі з модом, актуальні й з увімкненим Ranked - Grow нормалізовано, тож частота кадрів перестає вирішувати шкоду (важкий фриз усе ще може трохи недоростити - похибка завжди дивиться лише вниз); проти ванільних чи застарілих клієнтів діє ванільне правило. <color=#7FE87F>Стабільна частота кадрів - реальна змагальна перевага</color> - на вкладці Налаштування є розділ продуктивності рівно для цього.

<color=#FFD94D><b>ДРАФТІТЬ ПІД БІЛД</b></color>

- Карти - це план, а не аркуш статів. Лайфстіл лікується з ланцюжка завданої шкоди, і тіки поступової шкоди йдуть тим самим ланцюжком - лайфстіл плюс отрута це двигун, а не збіг. Echo і Shield Charge перетворюють навичку блокування на атаку. Другу карту драфтіть під першу.
- Прочитайте, що карта реально робить, і перевірте. Текст карти і поведінка карти - різні речі: Chase роками показувала рядок «+30% Health», якого ванільна карта ніколи не давала (мод той рядок прибрав). Ігри в пісочниці не записуються ніколи, тож експериментуйте там вільно.
- Правило «Ті самі карти» у FFA - найкращий учитель драфту в моді: коли воно ввімкнене, N-та роздача у всіх пропонує тих самих кандидатів у тому самому порядку, тож поразку не спишеш на удачу роздачі - різницею були вибори. Список Недавніх FFA зберігає кожен вибір у порядку вибору (наведіть на рядок карт гравця), тож можна перегрnative... переграти драфт переможця проти свого.
- Ваша історія матчів 1v1 зберігає вибори обох гравців по порядку для кожної гри. Після близької поразки перечитайте драфт, перш ніж знову ставати в чергу.

<color=#FFD94D><b>КОРИСТУЙТЕСЯ ВЛАСНИМИ ЧИСЛАМИ</b></color>

Моя статистика стежить за вашою грою більше, ніж ви, мабуть, думаєте. Що означають головні стати:

- <color=#7FD4FF>% влучань</color> - рахує кулі, а не кліки: один клік Buckshot рахує кожну дробинку, і рахуються лише прямі, незаблоковані влучання по ворогах - тіки отрути й горіння, вибухи і самоудари не рахуються ніколи. Дробовиковий білд за побудовою читається низько. <color=#FF6666>Порівнюйте білд із самим собою в часі, ніколи з числом снайпера.</color>
- <color=#7FD4FF>Успішність блока</color> - один правий клік поза відкатом - одна спроба, і щонайбільше один успіх на спробу, хоч скільки куль він поглинув. Превентивні блоки, що не зустріли кулі, - норма, а не помилка: дивіться тренд через ігри, а не одну гру.
- Графіки в часі семплюють кожні 3-5 секунд і завжди охоплюють усю гру. Використовуйте їх, щоб знайти, де ігри перевертаються: часовий ряд рахунку показує, коли вислизнула перевага, а лінії влучань і шкоди - що змінилося в той момент.
- Гра 1v1 записує середній і найгірший пінг плюс події фрізів (зависання кадру понад пів секунди); командні та FFA-ігри несуть полегшені дані з’єднання. Перш ніж винуватити приціл за одну погану гру, гляньте, чи не пояснюють її вже числа з’єднання (див. <color=#7FD4FF>Як рахується статистика</color>).

<color=#FFD94D><b>ДИВІТЬСЯ СИЛЬНІШИХ ГРАВЦІВ</b></color>

- Живі ігри на вкладці Таблиця лідерів несуть кнопку ДИВИТИСЯ, коли їх можна дивитися. Місце глядача показує справжній матч ізсередини кімнати, і те, як топ-гравець витрачає блоки і драфтить під тиском, вчить швидше за сліпу чергу. Лобі FFA так само дивляться з вкладки FFA.
- Discord-бот відповідає на питання про механіки живими даними: спитайте його «як працює блокування», або скільки elo ви здобули б проти названого гравця - і він порахує справжній прев’ю Glicko для обох сторін, з імовірністю перемоги включно (обом акаунтам потрібен прив’язаний Discord).$s256$)
  , ('b0a7c6d3a3a1f50e', 'es', '563c35f5fd7311e5b35e3c9b4db101e77b832981', $s256$Guías de cada mecánica: bloqueo, veneno, netcode, modos, ratings, recompensas, torneos, antitrampas, y qué cambia el mod (y qué no cambia a propósito).$s256$)
  , ('b0a7c6d3a3a1f50e', 'ru', '563c35f5fd7311e5b35e3c9b4db101e77b832981', $s256$Гайды по каждой механике: блокирование, яд, неткод, режимы, рейтинги, награды, турниры, античит - и что мод меняет (а что сознательно не трогает).$s256$)
  , ('b0a7c6d3a3a1f50e', 'sv', '563c35f5fd7311e5b35e3c9b4db101e77b832981', $s256$Guider till varje mekanik: blockering, gift, nätkod, spellägen, rating, belöningar, turneringar, antifusk och vad modden ändrar (och medvetet inte ändrar).$s256$)
  , ('b0a7c6d3a3a1f50e', 'uk', '563c35f5fd7311e5b35e3c9b4db101e77b832981', $s256$Посібники з кожної механіки: блокування, отрута, неткод, режими, рейтинги, нагороди, турніри, античит - і що мод змінює (а що свідомо ні).$s256$)
  , ('b28a75d1dad8e07b', 'es', 'd056314a57971f778cacd0c93848f1b7240058eb', $s256$El mod cambia el gameplay vanilla solo donde todos los jugadores lo han aceptado. Esta página explica exactamente cómo lo decide, y qué está garantizado cuando juegas con gente sin mod.

<color=#FFD94D><b>LA GARANTÍA</b></color>

<color=#7FE87F>Un jugador sin mod siempre recibe gameplay vanilla puro, y cualquier puerta que no pueda demostrar que un cambio es seguro lo deja apagado.</color> Los cambios de sala completa fallan cerrados para todos por igual. La única función por jugador es la sincronización de veneno, que sigue al jugador envenenado - el veneno de una víctima sin mod se queda vanilla.

Si el mod no puede demostrar que una función es segura, ejecuta vanilla.

<color=#FFD94D><b>CÓMO SE CLASIFICAN LAS SALAS</b></color>

El gameplay ligado a un modo corre solo en salas que el propio mod creó, y el nombre de la sala dice qué modo la emitió:

- <color=#7FD4FF>ranked_</color> - salas de la cola ranked 1v1
- <color=#7FD4FF>team_</color> (o el marcador de sala 2v2) - salas 2v2
- <color=#7FD4FF>sct-</color> - salas de torneo sync
- <color=#7FD4FF>ovt_</color> - salas 1v2
- <color=#7FD4FF>ffa_</color> - salas FFA, y solo mientras el motor de salas FFA está realmente activo

Una sala pública de quickplay o un código de sala normal de 6 caracteres no coincide con ninguno, así que todo cambio de gameplay ligado a un modo queda apagado allí.

<color=#FFD94D><b>PUERTAS DE CAPACIDAD</b></color>

Los cambios a la simulación compartida van un paso más allá: el mod de cada jugador anuncia una etiqueta de capacidad ANTES de entrar a la sala, así que cualquier cliente que pueda siquiera verte ya recibió tu etiqueta. Entonces:

- La <color=#7FD4FF>normalización de Grow</color>, el <color=#7FD4FF>escalado de objetos de mapa FFA</color> y el <color=#7FD4FF>repartidor de mismas cartas FFA</color> requieren la etiqueta de CADA combatiente. <color=#7FE87F>Un jugador vanilla, un mod desactualizado o un jugador cuyo mod se desactivó apaga la función para toda la sala - simétricamente, en todas las pantallas a la vez.</color> Nadie juega con una regla distinta a la de su rival.
- La <color=#7FD4FF>sincronización de veneno</color> se activa por víctima, en cualquier sala online: el propio cliente de una víctima al día juzga su veneno; el veneno de una víctima sin mod se queda vanilla. Los detalles de salas mixtas viven en <color=#7FD4FF>Veneno y daño en el tiempo</color>.
- Los espectadores nunca cuentan a favor ni en contra de estas comprobaciones.
- Si el parche de una función no logra instalarse, ese cliente nunca anuncia la etiqueta. Si se detecta cualquier otro mod de BepInEx al arrancar, el mod entero se desactiva y revoca sus etiquetas - comportamiento vanilla completo.

<color=#FFD94D><b>DOS CLASES DE ARREGLOS</b></color>

No todo está tras una puerta, y la distinción importa:

<color=#7FD4FF>Prevención de crashes</color> - siempre activa, en todas partes, quickplay incluido. Estas protecciones frenan bugs vanilla como el crash de inputs congelados al encontrar partida, la tecla Escape muerta para siempre y el crash de la reanimación de Phoenix. No cambian ninguna regla: cada una sustituye un crash o un estado roto por lo que el juego pretendía.

<color=#7FD4FF>Cambios de gameplay</color> - tras las puertas de arriba. La lógica de modo necesita su sala creada por el mod; Grow y las funciones FFA necesitan la comprobación de capacidad de sala completa; la autoridad del veneno es por víctima como se describió.

Entre las dos hay una banda de reparaciones locales (volver a registrar los efectos de bala rotos del propio vanilla, limpiar una marca de autodisparo atascada entre juegos) que corren en cualquier partida - pero solo reparan la contabilidad de tu propia pantalla hacia lo que el dueño de la bala ya decidió. Nunca cambian una regla, y no pueden crear un desacuerdo que vanilla no tuviera ya. El inventario completo está en <color=#7FD4FF>Arreglos de bugs del mod</color>.

<color=#FFD94D><b>QUICKPLAY CON EL MOD</b></color>

Jugando quickplay o un código de sala con el mod instalado, recibes reglas vanilla más registro: tus resultados y stats casual se siguen registrando, y los logros pueden seguir desbloqueándose. <color=#8A8A93>Una protección de recuperación puede además reiniciarte una búsqueda de quickplay muerta - eso es fontanería de conexión, no gameplay.</color>

Dos arreglos de equidad pueden llegar a quickplay y partidas por código: la <color=#7FD4FF>normalización de Grow</color> (todos los combatientes al día, el Ranked de todos activado al conectar - ambos lados siempre coinciden en ello) y la sincronización de veneno por víctima, que sigue al jugador envenenado allá donde juegue (ver <color=#7FD4FF>Veneno y daño en el tiempo</color> para los detalles de salas mixtas).

<color=#7FE87F>Y tu rival nunca tiene por qué saber que el mod está ahí: lo único que un jugador sin mod puede llegar a ver de él es el estilo del nombre</color> (ver <color=#7FD4FF>Qué ven los jugadores sin mod</color>).$s256$)
  , ('b28a75d1dad8e07b', 'ru', 'd056314a57971f778cacd0c93848f1b7240058eb', $s256$Мод меняет ванильный геймплей только там, где на это согласился каждый игрок. Эта страница объясняет, как именно он решает - и что гарантировано, когда ты играешь с людьми без мода.

<color=#FFD94D><b>ГАРАНТИЯ</b></color>

<color=#7FE87F>Игрок без мода всегда получает чистый ванильный геймплей, а любой шлюз, который не может доказать безопасность изменения, оставляет его выключенным.</color> Изменения на всю комнату отказывают закрыто и для всех одинаково. Единственная по-игроковая фича - синхронизация яда, которая следует за отравленным: яд жертвы без мода остаётся ванильным.

Если мод не может доказать, что фичу безопасно запускать, он запускает ваниль.

<color=#FFD94D><b>КАК КЛАССИФИЦИРУЮТСЯ КОМНАТЫ</b></color>

Привязанный к режимам геймплей работает только в комнатах, которые мод создал сам, и имя комнаты говорит, какой режим её выдал:

- <color=#7FD4FF>ranked_</color> - комнаты рейтинговой очереди 1v1
- <color=#7FD4FF>team_</color> (или маркер комнаты 2v2) - комнаты 2v2
- <color=#7FD4FF>sct-</color> - комнаты синхро-турниров
- <color=#7FD4FF>ovt_</color> - комнаты 1v2
- <color=#7FD4FF>ffa_</color> - комнаты FFA, и только пока реально активен движок FFA-лобби

Публичная quickplay-комната или обычный 6-символьный код комнаты не подходят ни под одно из этого, так что каждое привязанное к режимам изменение геймплея там выключено.

<color=#FFD94D><b>ШЛЮЗЫ ВОЗМОЖНОСТЕЙ</b></color>

Изменения общей симуляции идут на шаг дальше: мод каждого игрока объявляет тег возможности ДО входа в комнату, так что любой клиент, который вообще может тебя видеть, уже получил твой тег. Далее:

- <color=#7FD4FF>Нормализация Grow</color>, <color=#7FD4FF>масштабирование объектов карт FFA</color> и <color=#7FD4FF>одинаковый раздатчик карт FFA</color> требуют тега КАЖДОГО бойца. <color=#7FE87F>Один ванильный игрок, один устаревший мод или один игрок, чей мод сам себя отключил, выключает фичу для всей комнаты - симметрично, на всех экранах разом.</color> Никто не играет по правилу, отличному от правила соперника.
- <color=#7FD4FF>Синхронизация яда</color> активируется по-жертвенно, в любой онлайн-комнате: яд актуальной жертвы судит её собственный клиент; яд жертвы без мода остаётся ванильным. Детали смешанных комнат - в <color=#7FD4FF>Яд и урон со временем</color>.
- Зрители никогда не считаются ни в эти проверки, ни против них.
- Если патч фичи не смог установиться, тот клиент никогда не объявляет тег. Если на старте обнаружен любой другой BepInEx-мод, весь мод отключает себя и отзывает свои теги - полностью ванильное поведение.

<color=#FFD94D><b>ДВА ВИДА ФИКСОВ</b></color>

Шлюзами закрыто не всё, и различие важно:

<color=#7FD4FF>Защита от крашей</color> - всегда включена, везде, включая quickplay. Эти стражи останавливают ванильные баги вроде замёрзшего ввода на найденном матче, навсегда мёртвой клавиши Escape и краша воскрешения Phoenix. Они не меняют ни одного правила: каждый заменяет краш или сломанное состояние тем, что игра задумывала.

<color=#7FD4FF>Изменения геймплея</color> - закрыты шлюзами, как выше. Логике режимов нужна своя выданная модом комната; Grow и фичам FFA - проверка возможностей всей комнаты; авторитет яда по-жертвенный, как описано.

Между этими двумя лежит полоса локальных ремонтов (дорегистрация собственных сломанных эффектов пуль ванили, чистка застрявшего флага автоогня между играми), которые работают в любой игре, - но они лишь чинят бухгалтерию твоего экрана к тому, что владелец пули уже решил. Они никогда не меняют правило и не могут создать расхождение, которого у ванили ещё не было. Полная опись - в <color=#7FD4FF>Исправления багов в моде</color>.

<color=#FFD94D><b>QUICKPLAY С МОДОМ</b></color>

Играя quickplay или код комнаты с установленным модом, ты получаешь ванильные правила плюс учёт: твои казуальные результаты и статы всё равно записываются, а достижения всё ещё могут открыться. <color=#8A8A93>Ещё восстановительный страж может перезапустить тебе мёртвый quickplay-поиск - это сантехника соединения, не геймплей.</color>

Два фикса честности могут дотянуться до quickplay и игр по коду комнаты: <color=#7FD4FF>нормализация Grow</color> (каждый боец актуален, Ranked включён у всех на подключении - обе стороны всегда согласны о нём) и по-жертвенная синхронизация яда, которая следует за отравленным, где бы он ни играл (детали смешанных комнат - см. <color=#7FD4FF>Яд и урон со временем</color>).

<color=#7FE87F>И твоему сопернику незачем знать, что мод здесь: единственное, что игрок без мода вообще может от него увидеть, - стиль неймтега</color> (см. <color=#7FD4FF>Что видят игроки без мода</color>).$s256$)
  , ('b28a75d1dad8e07b', 'sv', 'd056314a57971f778cacd0c93848f1b7240058eb', $s256$Modden ändrar vanilla-gameplay bara där varje spelare samtyckt till det. Den här sidan förklarar exakt hur den avgör det, och vad som garanteras när du spelar med icke-moddade personer.

<color=#FFD94D><b>GARANTIN</b></color>

<color=#7FE87F>En spelare utan modden får alltid ren vanilla-gameplay, och varje grind som inte kan bevisa att en ändring är säker lämnar den avstängd.</color> Ändringar för hela rum stänger säkert för alla identiskt. Den enda funktionen per spelare är giftsynken, som följer den förgiftade spelaren - ett omoddat offers gift förblir vanilla.

Om modden inte kan bevisa att en funktion är säker att köra, kör den vanilla.

<color=#FFD94D><b>SÅ KLASSIFICERAS RUM</b></color>

Lägesbunden gameplay körs bara i rum som modden själv skapat, och rummets namn säger vilket läge som utfärdade det:

- <color=#7FD4FF>ranked_</color> - 1v1-rum från ranked-kön
- <color=#7FD4FF>team_</color> (eller 2v2-rumsmarkören) - 2v2-rum
- <color=#7FD4FF>sct-</color> - synkturneringsrum
- <color=#7FD4FF>ovt_</color> - 1v2-rum
- <color=#7FD4FF>ffa_</color> - FFA-rum, och bara medan FFA-lobbymotorn faktiskt är aktiv

Ett publikt quickplayrum eller en normal 6-teckens rumskod matchar inget av dessa, så varje lägesbunden gameplay-ändring förblir avstängd där.

<color=#FFD94D><b>KAPACITETSGRINDAR</b></color>

Ändringar av den delade simuleringen går ett steg längre: varje spelares modd annonserar en kapacitetstagg INNAN den går med i rummet, så varje klient som ens kan se dig har redan fått din tagg. Sedan:

- <color=#7FD4FF>Grow-normaliseringen</color>, <color=#7FD4FF>FFA-kartobjektskalningen</color> och <color=#7FD4FF>FFA:s samma-kort-givare</color> kräver VARJE fighters tagg. <color=#7FE87F>En vanilla-spelare, en föråldrad modd eller en spelare vars modd stängt av sig själv slår av funktionen för hela rummet - symmetriskt, på varje skärm samtidigt.</color> Ingen spelar efter en annan regel än sin motståndare.
- <color=#7FD4FF>Giftsynken</color> aktiveras per offer, i vilket onlinerum som helst: ett aktuellt offers egen klient dömer deras gift; ett omoddat offers gift förblir vanilla. Detaljerna för blandade rum finns i <color=#7FD4FF>Gift & skada över tid</color>.
- Åskådare räknas aldrig för eller emot de här kontrollerna.
- Om en funktions patch misslyckas att installera annonserar den klienten aldrig taggen. Om någon annan BepInEx-modd upptäcks vid start stänger hela modden av sig själv och drar tillbaka sina taggar - fullt vanilla-beteende.

<color=#FFD94D><b>TVÅ SORTERS FIXAR</b></color>

Allt är inte grindat, och skillnaden spelar roll:

<color=#7FD4FF>Kraschskydd</color> - alltid på, överallt, quickplay inräknat. De här skydden stoppar vanilla-buggar som frusna-inputs-vid-matchhittad-kraschen, den permanent döda Escape-tangenten och Phoenix-återupplivningskraschen. De ändrar ingen regel: var och en ersätter en krasch eller ett trasigt tillstånd med vad spelet avsåg.

<color=#7FD4FF>Gameplay-ändringar</color> - grindade som ovan. Lägeslogik kräver sitt modd-utfärdade rum; Grow och FFA-funktionerna kräver kapacitetskontrollen för hela rummet; giftauktoriteten är per offer som beskrivet.

Mellan de två ligger ett band av lokala reparationer (omregistrering av vanillas egna trasiga kuleffekter, rensning av en fastnad autoeldflagga mellan matcher) som körs i vilken match som helst - men de reparerar bara din egen skärms bokföring mot vad kulans ägare redan beslutat. De ändrar aldrig en regel, och kan inte skapa en oenighet som vanilla inte redan hade. Hela inventariet finns i <color=#7FD4FF>Buggfixar i modden</color>.

<color=#FFD94D><b>QUICKPLAY MED MODDEN</b></color>

Spelar du quickplay eller en rumskod med modden installerad får du vanilla-regler plus spårning: dina casual-resultat och din statistik registreras fortfarande, och prestationer kan fortfarande låsas upp. <color=#8A8A93>Ett återhämtningsskydd kan också starta om en död quickplay-sökning åt dig - det är anslutningsrörmokeri, inte gameplay.</color>

Två rättvisefixar kan nå quickplay- och rumskodsmatcher: <color=#7FD4FF>Grow-normaliseringen</color> (varje fighter aktuell, allas Ranked på vid anslutning - båda sidor är alltid överens om den) och giftsynken per offer, som följer den förgiftade spelaren var de än spelar (se <color=#7FD4FF>Gift & skada över tid</color> för detaljerna om blandade rum).

<color=#7FE87F>Och din motståndare behöver aldrig veta att modden finns där: det enda en spelare utan modden någonsin kan se av den är namnskyltsstil</color> (se <color=#7FD4FF>Vad omoddade spelare ser</color>).$s256$)
  , ('b28a75d1dad8e07b', 'uk', 'd056314a57971f778cacd0c93848f1b7240058eb', $s256$Мод змінює ванільний геймплей лише там, де на це погодився кожен гравець. Ця сторінка пояснює, як саме він це вирішує і що гарантовано, коли ви граєте з людьми без мода.

<color=#FFD94D><b>ГАРАНТІЯ</b></color>

<color=#7FE87F>Гравець без мода завжди отримує чистий ванільний геймплей, а будь-які ворота, що не можуть довести безпечність зміни, лишають її вимкненою.</color> Зміни на всю кімнату відмовляють у закритий бік для всіх однаково. Єдина по-гравцева можливість - синхронізація отрути, що йде за отруєним гравцем: отрута жертви без мода лишається ванільною.

Якщо мод не може довести, що можливість безпечна, він грає ваніль.

<color=#FFD94D><b>ЯК КЛАСИФІКУЮТЬСЯ КІМНАТИ</b></color>

Прив’язаний до режимів геймплей працює лише в кімнатах, які мод створив сам, а ім’я кімнати каже, який режим її видав:

- <color=#7FD4FF>ranked_</color> - кімнати рейтингової черги 1v1
- <color=#7FD4FF>team_</color> (або маркер кімнати 2v2) - кімнати 2v2
- <color=#7FD4FF>sct-</color> - кімнати синхронних турнірів
- <color=#7FD4FF>ovt_</color> - кімнати 1v2
- <color=#7FD4FF>ffa_</color> - кімнати FFA, і лише поки рушій лобі FFA реально активний

Публічна кімната швидкого матчу чи звичайний 6-символьний код кімнати не відповідають жодному з цих імен, тож кожна прив’язана до режиму зміна геймплею там вимкнена.

<color=#FFD94D><b>ВОРОТА ЗДАТНОСТЕЙ</b></color>

Зміни спільної симуляції йдуть на крок далі: мод кожного гравця оголошує тег здатності ЩЕ ПЕРЕД входом у кімнату, тож будь-який клієнт, що взагалі може вас бачити, вже отримав ваш тег. Далі:

- <color=#7FD4FF>Нормалізація Grow</color>, <color=#7FD4FF>масштабування об’єктів мап FFA</color> і <color=#7FD4FF>роздавач однакових карт FFA</color> вимагають тега КОЖНОГО бійця. <color=#7FE87F>Один ванільний гравець, один застарілий мод чи один гравець, чий мод сам себе вимкнув, - і можливість вимикається для всієї кімнати: симетрично, на кожному екрані водночас.</color> Ніхто не грає за іншим правилом, ніж його суперник.
- <color=#7FD4FF>Синхронізація отрути</color> активується на кожну жертву окремо, в будь-якій онлайн-кімнаті: власний клієнт актуальної жертви судить її отруту; отрута жертви без мода лишається ванільною. Деталі змішаних кімнат - у <color=#7FD4FF>Отрута та поступова шкода</color>.
- Глядачі ніколи не рахуються ні за, ні проти цих перевірок.
- Якщо патч можливості не встановився, той клієнт свого тега не оголошує. Якщо на старті виявлено будь-який інший мод BepInEx, весь мод вимикає себе і відкликає свої теги - повна ванільна поведінка.

<color=#FFD94D><b>ДВА ВИДИ ВИПРАВЛЕНЬ</b></color>

Ворота стоять не на всьому, і різниця важлива:

<color=#7FD4FF>Захист від крашів</color> - завжди увімкнений, скрізь, зі швидкими матчами включно. Ці запобіжники зупиняють ванільні баги на кшталт замерзлого вводу на знайденому матчі, назавжди мертвої клавіші Escape і краша оживлення Phoenix. Вони не змінюють жодного правила: кожен замінює краш чи зламаний стан тим, що гра задумувала.

<color=#7FD4FF>Зміни геймплею</color> - за воротами, як вище. Логіка режимів потребує своєї модової кімнати; Grow і можливості FFA - перевірки здатностей усієї кімнати; авторитет отрути - по-гравцевий, як описано.

Між цими двома лежить смуга локальних ремонтів (дореєстрація зламаних ванільних ефектів куль, чищення застряглого прапорця автовогню між іграми), що працюють у будь-якій грі - але вони лише підтягують бухгалтерію вашого екрана до того, що власник кулі вже вирішив. Вони не змінюють правило і не можуть створити розбіжність, якої ваніль уже не мала. Повний перелік - у <color=#7FD4FF>Виправлення багів у моді</color>.

<color=#FFD94D><b>ШВИДКІ МАТЧІ З МОДОМ</b></color>

Граючи швидкий матч чи код кімнати з установленим модом, ви отримуєте ванільні правила плюс облік: ваші звичайні результати і статистика записуються, а досягнення можуть відкриватися. <color=#8A8A93>Запобіжник відновлення також може перезапустити мертвий пошук швидкого матчу за вас - це сантехніка з’єднання, а не геймплей.</color>

Два виправлення чесності можуть досягати швидких матчів та ігор за кодом: <color=#7FD4FF>Нормалізація Grow</color> (кожен боєць актуальний, Ranked у всіх увімкнений на момент підключення - обидві сторони завжди згодні щодо цього) і по-гравцева синхронізація отрути, що йде за отруєним гравцем, хоч би де він грав (див. <color=#7FD4FF>Отрута та поступова шкода</color> щодо деталей змішаних кімнат).

<color=#7FE87F>А ваш суперник узагалі не мусить знати, що мод тут: єдине, що гравець без мода може від нього побачити, - стилізація неймтега</color> (див. <color=#7FD4FF>Що бачать гравці без мода</color>).$s256$)
  , ('b58acd5e29be1ec7', 'es', '13adb395aafe582e56beeb4950df2212c37ed5c3', $s256$XP, Oro y niveles$s256$)
  , ('b58acd5e29be1ec7', 'ru', '13adb395aafe582e56beeb4950df2212c37ed5c3', $s256$XP, золото и уровни$s256$)
  , ('b58acd5e29be1ec7', 'sv', '13adb395aafe582e56beeb4950df2212c37ed5c3', $s256$XP, guld & nivåer$s256$)
  , ('b58acd5e29be1ec7', 'uk', '13adb395aafe582e56beeb4950df2212c37ed5c3', $s256$XP, золото та рівні$s256$)
  , ('b5f34f740a723641', 'es', '9c44d8b9070ee32670d2c711ac5c17177adacca6', $s256$Bugs conocidos de vanilla$s256$)
  , ('b5f34f740a723641', 'ru', '9c44d8b9070ee32670d2c711ac5c17177adacca6', $s256$Известные баги ванили$s256$)
  , ('b5f34f740a723641', 'sv', '9c44d8b9070ee32670d2c711ac5c17177adacca6', $s256$Kända vanilla-buggar$s256$)
  , ('b5f34f740a723641', 'uk', '9c44d8b9070ee32670d2c711ac5c17177adacca6', $s256$Відомі баги ванілі$s256$)
  , ('b6d9767052faaed9', 'es', 'eed6829db70d00d75f1575ea1f18feaa88b4b97b', $s256$Guía de logros$s256$)
  , ('b6d9767052faaed9', 'ru', 'eed6829db70d00d75f1575ea1f18feaa88b4b97b', $s256$Гид по достижениям$s256$)
  , ('b6d9767052faaed9', 'sv', 'eed6829db70d00d75f1575ea1f18feaa88b4b97b', $s256$Prestationsguide$s256$)
  , ('b6d9767052faaed9', 'uk', 'eed6829db70d00d75f1575ea1f18feaa88b4b97b', $s256$Посібник із досягнень$s256$)
  , ('b866b3bb57469add', 'es', '34e1da105396b008eb570bdf67a78f97037f438e', $s256$<color=#8A8A93>Investigación y redacción de Spirit - 'Sobre los tipos de daño y la activación de buffs', Universidad de Rounds. Reproducido para esta biblioteca con un reformateo ligero; las pruebas, los hallazgos y la voz son todos suyos.</color>

Mediante pruebas minuciosas en el modo sandbox con un jugador adicional con mando, he catalogado qué tipos de daño activan qué cartas y buffs. Las cartas principales en cuestión son Scavenger, Refresh, Brawler y Taste of Blood. También se ha considerado el robo de vida como stat de personaje que otorgan numerosas cartas. Mis resultados dividen el daño en tres categorías principales: daño al rival, daño propio y daño Condicional. El daño a tu rival por casi cualquier medio activará todas las cartas y buffs, con la excepción de tipos concretos de daño Condicional. Por varias razones, parte del daño Condicional, típicamente el de cartas de bloqueo, no activará Refresh de forma consistente pero sí activará el resto de buffs. Por último, cualquier forma de daño propio siempre activará Scavenger, y nada más. Hay, por supuesto, numerosas rarezas y excepciones.

<color=#FFD94D><b>LA TABLA DE INTERACCIONES DE DAÑO</b></color>

Columnas: Scav = Scavenger, Brawl = Brawler, ToB = Taste of Blood, Steal = robo de vida, Refr = Refresh. Cond = se activa condicionalmente (explicado abajo).

<color=#FFD94D>Fuente de daño<pos=34%>Scav<pos=45%>Brawl<pos=56%>ToB<pos=67%>Steal<pos=78%>Refr</color>
Daño de bala<pos=34%>Sí<pos=45%>Sí<pos=56%>Sí<pos=67%>Sí<pos=78%>Sí
Daño de bala (propio)<pos=34%>Sí<pos=45%>No<pos=56%>No<pos=67%>No<pos=78%>No
Abyssal Countdown<pos=34%>No<pos=45%>No<pos=56%>No<pos=67%>No<pos=78%>No
Bombs Away<pos=34%>Sí<pos=45%>Sí<pos=56%>Sí<pos=67%>Sí<pos=78%>Cond
Bombs Away (propio)<pos=34%>Sí<pos=45%>No<pos=56%>No<pos=67%>No<pos=78%>No
Decay<pos=34%>Sí<pos=45%>Sí<pos=56%>Sí<pos=67%>Sí<pos=78%>Cond
Decay (propio)<pos=34%>Sí<pos=45%>No<pos=56%>No<pos=67%>No<pos=78%>No
Demonic Pact (propio)<pos=34%>Sí<pos=45%>No<pos=56%>No<pos=67%>No<pos=78%>No
Demonic Pact (AoE)<pos=34%>Sí<pos=45%>Sí<pos=56%>Sí<pos=67%>Sí<pos=78%>Cond
EMP<pos=34%>Sí<pos=45%>Sí<pos=56%>Sí<pos=67%>Sí<pos=78%>Cond
EMP (propio)<pos=34%>Sí<pos=45%>No<pos=56%>No<pos=67%>No<pos=78%>No
Explosive Bullet<pos=34%>Sí<pos=45%>Sí<pos=56%>Sí<pos=67%>Sí<pos=78%>Cond
Explosive Bullet (propio)<pos=34%>Sí<pos=45%>No<pos=56%>No<pos=67%>No<pos=78%>No
Frost Slam<pos=34%>Sí<pos=45%>Sí<pos=56%>Sí<pos=67%>Sí<pos=78%>No
Lifestealer<pos=34%>Sí<pos=45%>Sí<pos=56%>Sí<pos=67%>Sí<pos=78%>Cond
Overpower<pos=34%>Sí<pos=45%>Sí<pos=56%>Sí<pos=67%>Sí<pos=78%>Sí
Parasite<pos=34%>Sí<pos=45%>Sí<pos=56%>Sí<pos=67%>Sí<pos=78%>Cond
Parasite (propio)<pos=34%>Sí<pos=45%>No<pos=56%>No<pos=67%>No<pos=78%>No
Poison<pos=34%>Sí<pos=45%>Sí<pos=56%>Sí<pos=67%>Sí<pos=78%>Cond
Poison (propio)<pos=34%>Sí<pos=45%>No<pos=56%>No<pos=67%>No<pos=78%>No
Radiance<pos=34%>Sí<pos=45%>Sí<pos=56%>Sí<pos=67%>Sí<pos=78%>Cond
Saw<pos=34%>Sí<pos=45%>Sí<pos=56%>Sí<pos=67%>Sí<pos=78%>Cond
Shield Charge<pos=34%>Sí<pos=45%>Sí<pos=56%>Sí<pos=67%>Sí<pos=78%>Sí
Silence<pos=34%>Sí<pos=45%>Sí<pos=56%>Sí<pos=67%>Sí<pos=78%>Cond
Shockwave<pos=34%>Sí<pos=45%>Sí<pos=56%>Sí<pos=67%>Sí<pos=78%>No
Static Field<pos=34%>Sí<pos=45%>Sí<pos=56%>Sí<pos=67%>Sí<pos=78%>Cond
Supernova<pos=34%>Sí<pos=45%>Sí<pos=56%>Sí<pos=67%>Sí<pos=78%>Sí
Timed Detonation<pos=34%>Sí<pos=45%>Sí<pos=56%>Sí<pos=67%>Sí<pos=78%>Cond
Timed Detonation (propio)<pos=34%>Sí<pos=45%>No<pos=56%>No<pos=67%>No<pos=78%>No
Toxic Cloud<pos=34%>Sí<pos=45%>Sí<pos=56%>Sí<pos=67%>Sí<pos=78%>Cond
Toxic Cloud (propio)<pos=34%>Sí<pos=45%>No<pos=56%>No<pos=67%>No<pos=78%>No

Todas estas pruebas se realizaron en el modo sandbox con dos jugadores, uno con teclado y el otro con mando. Cada prueba se repitió varias veces para asegurar que los resultados fueran consistentes, o al menos consistentemente inconsistentes. No se distinguió entre el daño de área de Timed Detonation adherido a un jugador y el adherido a una superficie.

Prometedores causantes de daño en potencia, como Chilling Presence, quedaron excluidos tanto por no activar ninguna carta ni buff como por no infligir daño alguno. Cada entrada de la lista inflige daño de alguna forma, y cada manera única de infligir daño tiene su entrada. Por tanto, no hay métodos para activar cartas o buffs de daño sin infligir algo de daño. Puede parecer obvio pero, dada la rareza del resto del sistema, nunca se es demasiado precavido.$s256$)
  , ('b866b3bb57469add', 'ru', '34e1da105396b008eb570bdf67a78f97037f438e', $s256$<color=#8A8A93>Исследование и текст - Spirit: «О типах урона и активации баффов», Университет Rounds. Воспроизведено для этой библиотеки с лёгкой переформатировкой; тесты, находки и голос - целиком его.</color>

Тщательным тестированием в режиме песочницы с дополнительным игроком на контроллере я каталогизировал, какие типы урона запускают какие карты и баффы. Главные карты в вопросе - Scavenger, Refresh, Brawler и Taste of Blood. Учтён и вампиризм как стат персонажа, даруемый многими картами. Мои результаты делят урон на три главные категории: урон сопернику, урон себе и условный урон. Урон сопернику почти любым способом запускает все карты и баффы, за исключением отдельных видов условного урона. По разным причинам часть условного урона, обычно от блоковых карт, не запускает Refresh стабильно, но всё равно запускает все остальные баффы. Наконец, любая форма урона себе всегда активирует Scavenger - и ничего больше. Есть, конечно, многочисленные странности и исключения.

<color=#FFD94D><b>ТАБЛИЦА ВЗАИМОДЕЙСТВИЙ УРОНА</b></color>

Столбцы: Scav = Scavenger, Brawl = Brawler, ToB = Taste of Blood, Steal = вампиризм, Refr = Refresh. Усл. = срабатывает условно (объяснено ниже).

<color=#FFD94D>Источник урона<pos=34%>Scav<pos=45%>Brawl<pos=56%>ToB<pos=67%>Steal<pos=78%>Refr</color>
Урон пулями<pos=34%>Да<pos=45%>Да<pos=56%>Да<pos=67%>Да<pos=78%>Да
Урон пулями (себе)<pos=34%>Да<pos=45%>Нет<pos=56%>Нет<pos=67%>Нет<pos=78%>Нет
Abyssal Countdown<pos=34%>Нет<pos=45%>Нет<pos=56%>Нет<pos=67%>Нет<pos=78%>Нет
Bombs Away<pos=34%>Да<pos=45%>Да<pos=56%>Да<pos=67%>Да<pos=78%>Усл.
Bombs Away (себе)<pos=34%>Да<pos=45%>Нет<pos=56%>Нет<pos=67%>Нет<pos=78%>Нет
Decay<pos=34%>Да<pos=45%>Да<pos=56%>Да<pos=67%>Да<pos=78%>Усл.
Decay (себе)<pos=34%>Да<pos=45%>Нет<pos=56%>Нет<pos=67%>Нет<pos=78%>Нет
Demonic Pact (себе)<pos=34%>Да<pos=45%>Нет<pos=56%>Нет<pos=67%>Нет<pos=78%>Нет
Demonic Pact (AoE)<pos=34%>Да<pos=45%>Да<pos=56%>Да<pos=67%>Да<pos=78%>Усл.
EMP<pos=34%>Да<pos=45%>Да<pos=56%>Да<pos=67%>Да<pos=78%>Усл.
EMP (себе)<pos=34%>Да<pos=45%>Нет<pos=56%>Нет<pos=67%>Нет<pos=78%>Нет
Explosive Bullet<pos=34%>Да<pos=45%>Да<pos=56%>Да<pos=67%>Да<pos=78%>Усл.
Explosive Bullet (себе)<pos=34%>Да<pos=45%>Нет<pos=56%>Нет<pos=67%>Нет<pos=78%>Нет
Frost Slam<pos=34%>Да<pos=45%>Да<pos=56%>Да<pos=67%>Да<pos=78%>Нет
Lifestealer<pos=34%>Да<pos=45%>Да<pos=56%>Да<pos=67%>Да<pos=78%>Усл.
Overpower<pos=34%>Да<pos=45%>Да<pos=56%>Да<pos=67%>Да<pos=78%>Да
Parasite<pos=34%>Да<pos=45%>Да<pos=56%>Да<pos=67%>Да<pos=78%>Усл.
Parasite (себе)<pos=34%>Да<pos=45%>Нет<pos=56%>Нет<pos=67%>Нет<pos=78%>Нет
Poison<pos=34%>Да<pos=45%>Да<pos=56%>Да<pos=67%>Да<pos=78%>Усл.
Poison (себе)<pos=34%>Да<pos=45%>Нет<pos=56%>Нет<pos=67%>Нет<pos=78%>Нет
Radiance<pos=34%>Да<pos=45%>Да<pos=56%>Да<pos=67%>Да<pos=78%>Усл.
Saw<pos=34%>Да<pos=45%>Да<pos=56%>Да<pos=67%>Да<pos=78%>Усл.
Shield Charge<pos=34%>Да<pos=45%>Да<pos=56%>Да<pos=67%>Да<pos=78%>Да
Silence<pos=34%>Да<pos=45%>Да<pos=56%>Да<pos=67%>Да<pos=78%>Усл.
Shockwave<pos=34%>Да<pos=45%>Да<pos=56%>Да<pos=67%>Да<pos=78%>Нет
Static Field<pos=34%>Да<pos=45%>Да<pos=56%>Да<pos=67%>Да<pos=78%>Усл.
Supernova<pos=34%>Да<pos=45%>Да<pos=56%>Да<pos=67%>Да<pos=78%>Да
Timed Detonation<pos=34%>Да<pos=45%>Да<pos=56%>Да<pos=67%>Да<pos=78%>Усл.
Timed Detonation (себе)<pos=34%>Да<pos=45%>Нет<pos=56%>Нет<pos=67%>Нет<pos=78%>Нет
Toxic Cloud<pos=34%>Да<pos=45%>Да<pos=56%>Да<pos=67%>Да<pos=78%>Усл.
Toxic Cloud (себе)<pos=34%>Да<pos=45%>Нет<pos=56%>Нет<pos=67%>Нет<pos=78%>Нет

Все эти тесты проводились в режиме песочницы с двумя игроками: один на клавиатуре, другой на контроллере. Каждый тест повторялся несколько раз, чтобы убедиться, что результаты стабильны - или хотя бы стабильно нестабильны. Разницы между AoE-уроном Timed Detonation, прицепленным к игроку и прицепленным к поверхности, не делалось.

Многообещающие потенциальные источники урона, такие как Chilling Presence, исключены из-за их неспособности как запустить хоть какие-то карты и баффы, так и нанести хоть какой-то урон. Каждая запись в списке наносит урон в той или иной форме, и у каждого уникального способа нанести урон есть запись. Стало быть, способов запустить завязанные на урон карты и баффы, не нанося урона, не существует. Это может показаться очевидным, но, учитывая странность всей остальной системы, лишний раз убедиться не помешает.$s256$)
  , ('b866b3bb57469add', 'sv', '34e1da105396b008eb570bdf67a78f97037f438e', $s256$<color=#8A8A93>Forskning och text av Spirit - 'Om skadetyper och buffaktivering', University of Rounds. Återgiven för det här biblioteket med lätt omformatering; testerna, fynden och rösten är helt och hållet hans.</color>

Genom grundliga tester i sandbox-läget med en extra kontrollerspelare har jag katalogiserat vilka typer av skada som utlöser vilka kort och buffar. Huvudkorten i fråga är Scavenger, Refresh, Brawler och Taste of Blood. Lifesteal som karaktärsvärde, skänkt av åtskilliga kort, har också beaktats. Mina resultat delar skadan i tre huvudkategorier: motståndarskada, självskada och Villkorlig skada. Skada på din motståndare via nästan vilket medel som helst utlöser alla kort och buffar, med undantag för vissa typer av Villkorlig skada. Av olika skäl kommer viss Villkorlig skada, typiskt från blockkort, inte att konsekvent utlösa Refresh men ändå utlösa alla andra buffar. Slutligen aktiverar varje form av självskada alltid Scavenger, men inget annat. Det finns förstås åtskilliga egenheter och undantag.

<color=#FFD94D><b>TABELLEN ÖVER SKADEINTERAKTIONER</b></color>

Kolumner: Scav = Scavenger, Brawl = Brawler, ToB = Taste of Blood, Steal = lifesteal, Refr = Refresh. Villk = utlöses villkorligt (förklaras nedan).

<color=#FFD94D>Skadekälla<pos=34%>Scav<pos=45%>Brawl<pos=56%>ToB<pos=67%>Steal<pos=78%>Refr</color>
Kulskada<pos=34%>Ja<pos=45%>Ja<pos=56%>Ja<pos=67%>Ja<pos=78%>Ja
Kulskada (själv)<pos=34%>Ja<pos=45%>Nej<pos=56%>Nej<pos=67%>Nej<pos=78%>Nej
Abyssal Countdown<pos=34%>Nej<pos=45%>Nej<pos=56%>Nej<pos=67%>Nej<pos=78%>Nej
Bombs Away<pos=34%>Ja<pos=45%>Ja<pos=56%>Ja<pos=67%>Ja<pos=78%>Villk
Bombs Away (själv)<pos=34%>Ja<pos=45%>Nej<pos=56%>Nej<pos=67%>Nej<pos=78%>Nej
Decay<pos=34%>Ja<pos=45%>Ja<pos=56%>Ja<pos=67%>Ja<pos=78%>Villk
Decay (själv)<pos=34%>Ja<pos=45%>Nej<pos=56%>Nej<pos=67%>Nej<pos=78%>Nej
Demonic Pact (själv)<pos=34%>Ja<pos=45%>Nej<pos=56%>Nej<pos=67%>Nej<pos=78%>Nej
Demonic Pact (AoE)<pos=34%>Ja<pos=45%>Ja<pos=56%>Ja<pos=67%>Ja<pos=78%>Villk
EMP<pos=34%>Ja<pos=45%>Ja<pos=56%>Ja<pos=67%>Ja<pos=78%>Villk
EMP (själv)<pos=34%>Ja<pos=45%>Nej<pos=56%>Nej<pos=67%>Nej<pos=78%>Nej
Explosive Bullet<pos=34%>Ja<pos=45%>Ja<pos=56%>Ja<pos=67%>Ja<pos=78%>Villk
Explosive Bullet (själv)<pos=34%>Ja<pos=45%>Nej<pos=56%>Nej<pos=67%>Nej<pos=78%>Nej
Frost Slam<pos=34%>Ja<pos=45%>Ja<pos=56%>Ja<pos=67%>Ja<pos=78%>Nej
Lifestealer<pos=34%>Ja<pos=45%>Ja<pos=56%>Ja<pos=67%>Ja<pos=78%>Villk
Overpower<pos=34%>Ja<pos=45%>Ja<pos=56%>Ja<pos=67%>Ja<pos=78%>Ja
Parasite<pos=34%>Ja<pos=45%>Ja<pos=56%>Ja<pos=67%>Ja<pos=78%>Villk
Parasite (själv)<pos=34%>Ja<pos=45%>Nej<pos=56%>Nej<pos=67%>Nej<pos=78%>Nej
Poison<pos=34%>Ja<pos=45%>Ja<pos=56%>Ja<pos=67%>Ja<pos=78%>Villk
Poison (själv)<pos=34%>Ja<pos=45%>Nej<pos=56%>Nej<pos=67%>Nej<pos=78%>Nej
Radiance<pos=34%>Ja<pos=45%>Ja<pos=56%>Ja<pos=67%>Ja<pos=78%>Villk
Saw<pos=34%>Ja<pos=45%>Ja<pos=56%>Ja<pos=67%>Ja<pos=78%>Villk
Shield Charge<pos=34%>Ja<pos=45%>Ja<pos=56%>Ja<pos=67%>Ja<pos=78%>Ja
Silence<pos=34%>Ja<pos=45%>Ja<pos=56%>Ja<pos=67%>Ja<pos=78%>Villk
Shockwave<pos=34%>Ja<pos=45%>Ja<pos=56%>Ja<pos=67%>Ja<pos=78%>Nej
Static Field<pos=34%>Ja<pos=45%>Ja<pos=56%>Ja<pos=67%>Ja<pos=78%>Villk
Supernova<pos=34%>Ja<pos=45%>Ja<pos=56%>Ja<pos=67%>Ja<pos=78%>Ja
Timed Detonation<pos=34%>Ja<pos=45%>Ja<pos=56%>Ja<pos=67%>Ja<pos=78%>Villk
Timed Detonation (själv)<pos=34%>Ja<pos=45%>Nej<pos=56%>Nej<pos=67%>Nej<pos=78%>Nej
Toxic Cloud<pos=34%>Ja<pos=45%>Ja<pos=56%>Ja<pos=67%>Ja<pos=78%>Villk
Toxic Cloud (själv)<pos=34%>Ja<pos=45%>Nej<pos=56%>Nej<pos=67%>Nej<pos=78%>Nej

Alla dessa tester utfördes i sandbox-läget med två spelare, en på tangentbord och den andra på kontroller. Varje test upprepades flera gånger för att säkerställa att resultaten var konsekventa, eller åtminstone konsekvent inkonsekventa. Ingen skillnad gjordes mellan Timed Detonation-AoE-skada fäst på en spelare kontra fäst på en yta.

Lovande potentiella skadegörare, som Chilling Presence, uteslöts på grund av både sitt misslyckande att utlösa några kort eller buffar och sitt misslyckande att göra någon skada. Varje post på listan gör skada i någon form, och varje unikt sätt att göra skada har en post. Alltså finns det inga sätt att utlösa skadegivande kort eller buffar utan att göra någon mängd skada. Det kan tyckas självklart men, med tanke på hur konstigt resten av systemet är, kan man aldrig vara nog säker.$s256$)
  , ('b866b3bb57469add', 'uk', '34e1da105396b008eb570bdf67a78f97037f438e', $s256$<color=#8A8A93>Дослідження і текст - Spirit: «Про типи шкоди та активацію бафів», Університет Rounds. Відтворено для цієї бібліотеки з легким переформатуванням; тестування, висновки і голос - цілком його.</color>

Шляхом ретельного тестування в режимі пісочниці з додатковим гравцем на контролері я склав каталог того, які типи шкоди тригерять які карти й бафи. Головні карти під питанням - Scavenger, Refresh, Brawler і Taste of Blood. Лайфстіл як стат персонажа, який дають численні карти, теж врахований. Мої результати ділять шкоду на три головні категорії: шкода суперникові, шкода собі та Умовна шкода. Шкода вашому суперникові майже будь-яким способом тригерить усі карти й бафи, за винятком окремих видів Умовної шкоди. З різних причин деяка Умовна шкода, типово від блок-карт, тригеритиме Refresh нестабільно, але тригеритиме всі інші бафи. Нарешті, будь-яка форма шкоди собі завжди активує Scavenger - і більше нічого. Є, звісно, численні дивини й винятки.

<color=#FFD94D><b>ТАБЛИЦЯ ВЗАЄМОДІЙ ШКОДИ</b></color>

Колонки: Scav = Scavenger, Brawl = Brawler, ToB = Taste of Blood, Steal = лайфстіл, Refr = Refresh. Умовно = тригерить умовно (пояснено нижче).

<color=#FFD94D>Джерело шкоди<pos=34%>Scav<pos=45%>Brawl<pos=56%>ToB<pos=67%>Steal<pos=78%>Refr</color>
Шкода від куль<pos=34%>Так<pos=45%>Так<pos=56%>Так<pos=67%>Так<pos=78%>Так
Шкода від куль (собі)<pos=34%>Так<pos=45%>Ні<pos=56%>Ні<pos=67%>Ні<pos=78%>Ні
Abyssal Countdown<pos=34%>Ні<pos=45%>Ні<pos=56%>Ні<pos=67%>Ні<pos=78%>Ні
Bombs Away<pos=34%>Так<pos=45%>Так<pos=56%>Так<pos=67%>Так<pos=78%>Умовно
Bombs Away (собі)<pos=34%>Так<pos=45%>Ні<pos=56%>Ні<pos=67%>Ні<pos=78%>Ні
Decay<pos=34%>Так<pos=45%>Так<pos=56%>Так<pos=67%>Так<pos=78%>Умовно
Decay (собі)<pos=34%>Так<pos=45%>Ні<pos=56%>Ні<pos=67%>Ні<pos=78%>Ні
Demonic Pact (собі)<pos=34%>Так<pos=45%>Ні<pos=56%>Ні<pos=67%>Ні<pos=78%>Ні
Demonic Pact (AoE)<pos=34%>Так<pos=45%>Так<pos=56%>Так<pos=67%>Так<pos=78%>Умовно
EMP<pos=34%>Так<pos=45%>Так<pos=56%>Так<pos=67%>Так<pos=78%>Умовно
EMP (собі)<pos=34%>Так<pos=45%>Ні<pos=56%>Ні<pos=67%>Ні<pos=78%>Ні
Explosive Bullet<pos=34%>Так<pos=45%>Так<pos=56%>Так<pos=67%>Так<pos=78%>Умовно
Explosive Bullet (собі)<pos=34%>Так<pos=45%>Ні<pos=56%>Ні<pos=67%>Ні<pos=78%>Ні
Frost Slam<pos=34%>Так<pos=45%>Так<pos=56%>Так<pos=67%>Так<pos=78%>Ні
Lifestealer<pos=34%>Так<pos=45%>Так<pos=56%>Так<pos=67%>Так<pos=78%>Умовно
Overpower<pos=34%>Так<pos=45%>Так<pos=56%>Так<pos=67%>Так<pos=78%>Так
Parasite<pos=34%>Так<pos=45%>Так<pos=56%>Так<pos=67%>Так<pos=78%>Умовно
Parasite (собі)<pos=34%>Так<pos=45%>Ні<pos=56%>Ні<pos=67%>Ні<pos=78%>Ні
Poison<pos=34%>Так<pos=45%>Так<pos=56%>Так<pos=67%>Так<pos=78%>Умовно
Poison (собі)<pos=34%>Так<pos=45%>Ні<pos=56%>Ні<pos=67%>Ні<pos=78%>Ні
Radiance<pos=34%>Так<pos=45%>Так<pos=56%>Так<pos=67%>Так<pos=78%>Умовно
Saw<pos=34%>Так<pos=45%>Так<pos=56%>Так<pos=67%>Так<pos=78%>Умовно
Shield Charge<pos=34%>Так<pos=45%>Так<pos=56%>Так<pos=67%>Так<pos=78%>Так
Silence<pos=34%>Так<pos=45%>Так<pos=56%>Так<pos=67%>Так<pos=78%>Умовно
Shockwave<pos=34%>Так<pos=45%>Так<pos=56%>Так<pos=67%>Так<pos=78%>Ні
Static Field<pos=34%>Так<pos=45%>Так<pos=56%>Так<pos=67%>Так<pos=78%>Умовно
Supernova<pos=34%>Так<pos=45%>Так<pos=56%>Так<pos=67%>Так<pos=78%>Так
Timed Detonation<pos=34%>Так<pos=45%>Так<pos=56%>Так<pos=67%>Так<pos=78%>Умовно
Timed Detonation (собі)<pos=34%>Так<pos=45%>Ні<pos=56%>Ні<pos=67%>Ні<pos=78%>Ні
Toxic Cloud<pos=34%>Так<pos=45%>Так<pos=56%>Так<pos=67%>Так<pos=78%>Умовно
Toxic Cloud (собі)<pos=34%>Так<pos=45%>Ні<pos=56%>Ні<pos=67%>Ні<pos=78%>Ні

Усі ці тести виконано в режимі пісочниці з двома гравцями: один на клавіатурі, другий на контролері. Кожен тест повторено кілька разів, щоб переконатися, що результати стабільні - або принаймні стабільно нестабільні. Різниці між AoE-шкодою Timed Detonation, причепленою до гравця, і причепленою до поверхні, не робилося.

Перспективних потенційних завдавачів шкоди, як-от Chilling Presence, виключено - і через нездатність тригернути хоч якісь карти чи бафи, і через нездатність завдати хоч якоїсь шкоди. Кожен запис у списку так чи інакше завдає шкоди, і кожен унікальний спосіб завдати шкоди має свій запис. Отже, способів тригернути карти чи бафи, що спрацьовують від шкоди, без завдання хоч якоїсь шкоди не існує. Це може здатися очевидним, але, зважаючи на дивність решти системи, обережність не завадить.$s256$)
  , ('c14135018e41f6f6', 'es', 'befb751987d134277812bfa647884dbbdeffbd1f', $s256$Cada partida terminada paga XP, la XP se convierte en Oro a 100 XP = 1 Oro, y el juego ranked multiplica las recompensas base de abajo por el tier de rango de tu rival. Esta es la tabla de pagas - números exactos, modo a modo. (Los premios de podio de torneo van aparte; ver <color=#7FD4FF>Plazos e incomparecencias</color>.)

<color=#FFD94D><b>EL MULTIPLICADOR DE TIER</b></color>

En juego ranked, las recompensas base se multiplican por el tier de rango del RIVAL - <color=#7FE87F>ganes o pierdas. Jugar hacia arriba siempre paga.</color>

<color=#7FD4FF>Principiante</color> (menos de 1500) - x1.0
<color=#7FD4FF>Intermedio</color> (1500 o más) - x1.5
<color=#7FD4FF>Avanzado</color> (1675 o más) - x2.0
<color=#7FD4FF>Maestro</color> (1980 o más) - x2.5
<color=#7FD4FF>Gran Maestro</color> (2330 o más) - x3.0

Se aplica a la XP y al Oro de serie, y un rival sin rating registrado cuenta como 1500 (x1.5). Cuál es 'el rating del rival': su rating 1v1 en 1v1, el rating 2v2 medio del equipo contrario en 2v2, el rating 1v1 medio del asiento contrario en 1v2, y el rating FFA medio de tus rivales en FFA.

<color=#FFD94D><b>1v1</b></color>

Por partida, los multiplicadores se acumulan y el total se trunca a un número entero:

- Base de <color=#7FE87F>250 XP</color> por partida terminada, casual incluido.
- Victoria de partida: x1.5. Ranked: x1.5. Tier del rival: x1.0 a x3.0 (solo ranked).
- Una victoria sin conceder rondas (rival a 0) añade +100 XP fijos, después de los multiplicadores.

Ejemplos exactos: derrota casual 250, victoria casual 375; derrota ranked contra un Principiante 375; victoria ranked contra un Principiante 562, contra un Intermedio 843, contra un Gran Maestro 1687 (+100 más si es 5-0).

Oro de serie, solo BO3 ranked - el juego casual no crea series y no paga ninguno:

- Perdedor: 5 x tier del rival, truncado. Ganador: el doble.
- El ganador dobla OTRA VEZ si el vencido está ahora mismo en el top 3 de la clasificación.
- +2 fijos encima por una barrida 2-0.
- Ganador/perdedor por tier del rival, antes de podio y barrida: Principiante 10/5, Intermedio 14/7, Avanzado 20/10, Maestro 24/12, Gran Maestro 30/15.

<color=#FFD94D><b>2v2</b></color>

- Por juego: 600 XP x el tier del equipo rival, luego x1.5 si tu equipo ganó el juego.
- Sala por defecto todo-1500: 900 XP por derrota, 1350 por victoria.
- Oro de serie: 50 (cada ganador) o 25 (cada perdedor), x el tier del equipo rival. Sala por defecto: 75/37.

<color=#FFD94D><b>1v2</b></color>

Base de 500 XP por juego, x1.5 al ganar, luego un multiplicador de dificultad por asiento:

- Asiento de solo: x1.5.
- Solo jugando SIN la ventaja de elección extra: otro x1.20.
- Asientos del dúo frente a un solo potenciado (elección extra activada): x1.10.
- Tier del rival, leído del rating 1v1 medio del asiento contrario - el 1v2 no tiene rating propio.
- Rival ahora mismo en el top 3 de la clasificación 1v2: x1.35, ganes o pierdas.
- El producto completo tiene tope en x4.0; el bono de victoria x1.5 se aplica encima del tope.

Por defecto con elección extra activada: el solo gana 1125 XP por derrota y 1687 por victoria; cada miembro del dúo 825/1237.

Oro de serie: 40 (lado ganador) o 20 (lado perdedor), x solo el tier del rival - los factores de asiento, ventaja y podio viven en la XP. Por defecto: 60/30.

<color=#FFD94D><b>FFA - EL MEDIDOR</b></color>

El FFA paga por LUCHAR, no por tiempo en la sala. La fórmula, en forma legible:

- La unidad de trabajo son las <color=#7FD4FF>batallas</color>: cada ronda decisiva anotada por cualquiera en la partida. <color=#FF6666>Campear no añade nada al bote</color>, y la parte de último puesto que gana es la porción más pequeña de lo que generaron los demás.
- Un techo de ritmo limita lo rápido que se cobran las batallas. Para una sala de P jugadores, se espera una batalla cada 3.08 + 6.54 x P segundos aproximadamente (P contado como mínimo 3 y máximo 6 aquí), y la partida paga como mucho el DOBLE de ese ritmo sobre el tiempo transcurrido según el reloj del servidor - alargar o farmear puntos no puede superarlo.
- La tarifa base es 3.5 de Oro por jugador-minuto, +5% por cada jugador por encima de 4. Un FFA de 10 jugadores es la mejor tarifa de Oro del juego.
- La posición define tu parte del bote: el 1.er puesto gana 1.666x la media de la sala, el último 0.334x - una horquilla de unas 5x. Los jugadores que comparten puesto comparten la misma parte.
- Un campo más fuerte multiplica el bote: el tier medio de tus rivales dividido entre 1.5, así que un campo por defecto de 1500 es exactamente x1.0. Las salas casual toman el factor mínimo (cerca de x0.667) y nunca tocan los ratings.
- El bote es una cantidad de Oro. El 55% se paga directamente como Oro de posición (mínimo 1). El otro 45% se paga como XP a 100 XP por punto de bote (mínimo 50 XP), que vuelve goteando como Oro por la conversión normal.
- La posición se ordena por puntos, luego todas las rondas ganadas (incluidas las gastadas) y luego las kills donde el desempate por kills de la sala está activo; los empates restantes comparten puesto.
- Los fantasmas y quienes se fueron pronto con gracia no cobran ni puntúan esa partida: irse antes de que el campo anote 2 medios puntos, con tu propio marcador (puntos, medios puntos, kills) aún a cero, te saca de ella por completo.

<color=#FFD94D><b>NIVELES Y EL GOTEO DE XP A ORO</b></color>

- La XP se convierte a <color=#7FE87F>100 XP = 1 Oro</color>, pagado cada vez que tu total acumulado cruza una centena. La XP de todos los modos - premios de torneo incluidos - alimenta el mismo total.
- Subir al nivel L cuesta 100 x L^1.5 XP, truncado: el nivel 2 cuesta 282, el 5 cuesta 1118, el 10 cuesta 3162, el 50 cuesta 35355, el 100 cuesta 100000. El nivel máximo es 100.
- Entrar en un nivel múltiplo de 5 paga Oro extra: <color=#7FE87F>100g para los niveles 5 a 50, 500g para los 55 a 100</color> - 6000g de por vida si llegas al tope. Cae en el momento en que cualquier XP hace sonar el nivel - cualquier modo, premios de torneo incluidos; una subida durante una partida FFA aparece dentro del +g de esa partida.

<color=#FFD94D><b>ORO DE LOGROS</b></color>

Cada logro paga <color=#7FE87F>100g</color> salvo los listados aquí:

- <color=#7FD4FF>1000g</color> - Sid Slayer, Stan Slayer, Gran Maestro (llegar a 2330), Touch Grass, Babel.
- <color=#7FD4FF>500g</color> - Maestro (llegar a 1980), Barrida en equipo, Renacer de las cenizas, Conquistador casual, ¡Gemelos!, Inmortal, Adquisición hostil, Bajas.
- <color=#7FD4FF>300g</color> - Baraja trucada, Impecable, Silly Drill, De cabeza a lo hondo, Club de los cien, Imparable, Aguafiestas, Corazón roto, Dragomán.

Los 5-0 de FFA se anidan: una victoria 5-0 en una sala de 5 jugadores paga Limpieza general (100g) + Aguafiestas (300g) + Adquisición hostil (500g) en una sola partida. Los logros de traductor (Rosetta, Dragomán, Babel) se disparan a las 10, 100 y 1000 cadenas publicadas aprobadas.

<color=#8A8A93>Fuera de las partidas: los boosters del servidor de Discord cobran 2000g mensuales, y los artistas de la comunidad ganan una regalía del 30% (redondeada hacia abajo a Oro entero) cuando otro jugador compra su objeto - los regalos no pagan nada.</color>$s256$)
  , ('c14135018e41f6f6', 'ru', 'befb751987d134277812bfa647884dbbdeffbd1f', $s256$Каждая законченная игра платит XP, XP конвертируется в золото по 100 XP = 1 золото, а рейтинговая игра умножает базовые награды ниже на тир ранга соперника. Это таблица оплаты - точные числа, режим за режимом. (Призы турнирного подиума отдельно; см. <color=#7FD4FF>Дедлайны и техпоражения</color>.)

<color=#FFD94D><b>МНОЖИТЕЛЬ ТИРА</b></color>

В рейтинговой игре базовые награды умножаются на тир ранга СОПЕРНИКА - <color=#7FE87F>при победе и при поражении. Игра вверх платит всегда.</color>

<color=#7FD4FF>Новичок</color> (меньше 1500) - x1.0
<color=#7FD4FF>Средний</color> (1500 и выше) - x1.5
<color=#7FD4FF>Продвинутый</color> (1675 и выше) - x2.0
<color=#7FD4FF>Мастер</color> (1980 и выше) - x2.5
<color=#7FD4FF>Грандмастер</color> (2330 и выше) - x3.0

Он применяется к XP и к золоту серии, а соперник без записанного рейтинга считается как 1500 (x1.5). Чей рейтинг «рейтинг соперника»: его рейтинг 1v1 в 1v1, средний рейтинг 2v2 команды соперников в 2v2, средний рейтинг 1v1 противоположной стороны в 1v2 и средний рейтинг FFA твоих соперников в FFA.

<color=#FFD94D><b>1v1</b></color>

За игру, множители складываются перемножением, затем итог усекается до целого:

- База <color=#7FE87F>250 XP</color> за законченную игру, казуал включён.
- Победа в игре: x1.5. Рейтинговая: x1.5. Тир соперника: от x1.0 до x3.0 (только рейтинг).
- Сухая победа (соперник на 0 раундов) добавляет +100 XP плоско, после множителей.

Точные примеры: казуальное поражение 250, казуальная победа 375; рейтинговое поражение Новичку 375; рейтинговая победа над Новичком 562, над Средним 843, над Грандмастером 1687 (+100 сверху, если 5-0).

Золото серии, только рейтинговый BO3 - казуальная игра серий не создаёт и не платит ничего:

- Проигравший: 5 x тир соперника, усечённо. Победитель: вдвое больше.
- Победитель удваивает ЕЩЁ РАЗ, если побеждённый сейчас сидит в топ-3 таблицы лидеров.
- +2 плоско сверху за сухую серию 2-0.
- Победитель/проигравший по тиру соперника, до подиума и свипа: Новичок 10/5, Средний 14/7, Продвинутый 20/10, Мастер 24/12, Грандмастер 30/15.

<color=#FFD94D><b>2v2</b></color>

- За игру: 600 XP x тир команды соперников, затем x1.5, если твоя команда выиграла игру.
- Стандартное лобби всех-по-1500: 900 XP за поражение, 1350 за победу.
- Золото серии: 50 (каждому победителю) или 25 (каждому проигравшему), x тир команды соперников. Стандартное лобби: 75/37.

<color=#FFD94D><b>1v2</b></color>

База 500 XP за игру, x1.5 за победу, затем по-местный множитель сложности:

- Место соло: x1.5.
- Соло, играющий БЕЗ гандикапа доп. пика: ещё x1.20.
- Места дуо против усиленного соло (доп. пик включён): x1.10.
- Тир соперника, читаемый по среднему рейтингу 1v1 противоположной стороны, - собственного рейтинга у 1v2 нет.
- Соперник сейчас в топ-3 таблицы 1v2: x1.35, при победе и поражении.
- Всё произведение ограничено x4.0; бонус x1.5 за победу применяется поверх потолка.

Стандарт с включённым доп. пиком: соло получает 1125 XP за поражение и 1687 за победу; каждый участник дуо - 825/1237.

Золото серии: 40 (победившая сторона) или 20 (проигравшая), x только тир соперника - множители места, гандикапа и подиума живут на XP. Стандарт: 60/30.

<color=#FFD94D><b>FFA - СЧЁТЧИК</b></color>

FFA платит за БОРЬБУ, а не за время в лобби. Формула, читаемым языком:

- Единица работы - <color=#7FD4FF>битвы</color>: каждый решающий раунд, взятый кем угодно в игре. <color=#FF6666>Кемпинг не добавляет в банк ничего</color>, а доля последнего места, которую он приносит, - наименьший кусок того, что сгенерировали остальные.
- Потолок темпа ограничивает, как быстро битвы обналичиваются. Для лобби из P игроков одна битва ожидается примерно каждые 3.08 + 6.54 x P секунд (P считается минимум 3 и максимум 6 здесь), и игра платит максимум ВДВОЕ быстрее этого темпа по прошедшему времени игры на часах сервера - затяжка и фарм очков его не обгонят.
- Базовая ставка - 3.5 золота за игроко-минуту, +5% за каждого игрока сверх 4. FFA на 10 игроков - лучший курс золота в игре.
- Место задаёт твою долю банка: 1-е место получает 1.666x от среднего по лобби, последнее - 0.334x, разброс примерно в 5 раз. Игроки, делящие место, делят одну долю.
- Сильное поле умножает банк: средний тир твоих соперников, делённый на 1.5, так что стандартное поле 1500 - это ровно x1.0. Казуальные лобби берут нижний множитель (около x0.667) и не трогают рейтинг никогда.
- Банк - это сумма золота. 55% платится напрямую как золото за место (минимум 1). Остальные 45% платятся как XP по 100 XP за пункт банка (минимум 50 XP), которые обычной конверсией капают обратно золотом.
- Само место сортируется по очкам, затем по всем выигранным раундам (включая потраченные), затем по убийствам, где активен тайбрейк убийств лобби; оставшиеся ничьи делят место.
- Призраки и ушедшие рано по льготе не оплачиваются и не рейтингуются за ту игру: уход до 2 набранных пол-очков поля при твоём ещё нулевом счёте (очки, пол-очки, убийства) выводит тебя из неё целиком.

<color=#FFD94D><b>УРОВНИ И КАПЕЛЬ XP-В-ЗОЛОТО</b></color>

- XP конвертируется по <color=#7FE87F>100 XP = 1 золото</color>, выплачиваясь каждый раз, когда твоя бегущая сумма пересекает сотню. XP каждого режима - включая турнирные призы - кормит одну и ту же сумму.
- Подъём на уровень L стоит 100 x L^1.5 XP, усечённо: уровень 2 стоит 282, уровень 5 - 1118, уровень 10 - 3162, уровень 50 - 35355, уровень 100 - 100000. Максимальный уровень - 100.
- Вход на уровень, кратный 5, платит бонусное золото: <color=#7FE87F>100g за уровни с 5 по 50, 500g за 55-100</color> - 6000g за жизнь, если добраться до потолка. Оно падает в момент, когда любая выдача XP дёргает уровень - в любом режиме, включая турнирные призы; динь посреди FFA-игры показывается внутри её числа +g.

<color=#FFD94D><b>ЗОЛОТО ДОСТИЖЕНИЙ</b></color>

Каждое достижение платит <color=#7FE87F>100g</color>, если не указано здесь:

- <color=#7FD4FF>1000g</color> - Sid Slayer, Stan Slayer, Грандмастер (достигни 2330), Потрогай траву, Вавилон.
- <color=#7FD4FF>500g</color> - Мастер (достигни 1980), Командный разгром, Восставший из пепла, Покоритель казуала, Близнецы!, Бессмертный, Враждебное поглощение, Убийства.
- <color=#7FD4FF>300g</color> - Краплёная колода, Безупречный, Silly Drill, С головой в омут, Клуб сотни, Неудержимый, Незваный гость, Разбитое сердце, Драгоман.

Сухие серии FFA вложены: одна победа 5-0 в лобби на 5 игроков платит Генеральную уборку (100g) + Незваного гостя (300g) + Враждебное поглощение (500g) за одну игру. Достижения переводчика (Розетта, Драгоман, Вавилон) срабатывают на 10, 100 и 1000 одобренных живых строках.

<color=#8A8A93>Вне матчей: бустеры сервера Discord получают 2000g ежемесячно, а художники сообщества зарабатывают роялти 30% (округлённые вниз до целого золота), когда другой игрок покупает их предмет, - подарки не платят ничего.</color>$s256$)
  , ('c14135018e41f6f6', 'sv', 'befb751987d134277812bfa647884dbbdeffbd1f', $s256$Varje avslutad match betalar XP, XP omvandlas till guld enligt 100 XP = 1 guld, och rankat spel multiplicerar basbelöningarna nedan med din motståndares rangtier. Det här är lönetabellen - exakta siffror, läge för läge. (Turneringarnas podiepriser är separata; se <color=#7FD4FF>Tidsfrister & walkover</color>.)

<color=#FFD94D><b>TIERMULTIPLIKATORN</b></color>

I rankat spel multipliceras basbelöningar med MOTSTÅNDARENS rangtier - <color=#7FE87F>vid vinst som förlust. Att spela uppåt lönar sig alltid.</color>

<color=#7FD4FF>Nybörjare</color> (under 1500) - x1.0
<color=#7FD4FF>Medel</color> (1500 eller mer) - x1.5
<color=#7FD4FF>Avancerad</color> (1675 eller mer) - x2.0
<color=#7FD4FF>Mästare</color> (1980 eller mer) - x2.5
<color=#7FD4FF>Stormästare</color> (2330 eller mer) - x3.0

Den gäller XP och serieguld, och en motståndare utan registrerad rating räknas som 1500 (x1.5). Vilken rating som är 'motståndarens': deras 1v1-rating i 1v1, motståndarlagets snitt-2v2-rating i 2v2, motståndarsidans snitt-1v1-rating i 1v2, och dina motståndares snitt-FFA-rating i FFA.

<color=#FFD94D><b>1v1</b></color>

Per match; multiplikatorerna staplas, sedan trunkeras totalen till ett heltal:

- Bas <color=#7FE87F>250 XP</color> per avslutad match, casual inräknat.
- Matchvinst: x1.5. Ranked: x1.5. Motståndartier: x1.0 till x3.0 (endast ranked).
- En utklassningsvinst (motståndaren på 0 ronder) ger +100 XP platt, efter multiplikatorerna.

Exakta exempel: casual-förlust 250, casual-vinst 375; ranked-förlust mot en Nybörjare 375; ranked-vinst mot en Nybörjare 562, mot en Medel 843, mot en Stormästare 1687 (+100 till vid 5-0).

Serieguld, endast ranked BO3 - casualspel skapar ingen serie och betalar inget:

- Förlorare: 5 x motståndartier, trunkerat. Vinnare: dubbla det.
- Vinnaren dubblar IGEN om den besegrade spelaren just nu ligger i topplistans topp 3.
- +2 platt ovanpå för en 2-0-utklassning.
- Vinnare/förlorare per motståndartier, före podium och utklassning: Nybörjare 10/5, Medel 14/7, Avancerad 20/10, Mästare 24/12, Stormästare 30/15.

<color=#FFD94D><b>2v2</b></color>

- Per match: 600 XP x motståndarlagets tier, sedan x1.5 om ditt lag vann matchen.
- Standardlobby där alla ligger på 1500: 900 XP för en förlust, 1350 för en vinst.
- Serieguld: 50 (varje vinnare) eller 25 (varje förlorare), x motståndarlagets tier. Standardlobby: 75/37.

<color=#FFD94D><b>1v2</b></color>

Bas 500 XP per match, x1.5 vid vinst, sedan en svårighetsmultiplikator per plats:

- Soloplatsen: x1.5.
- Solo som spelar UTAN extrakortshandikappet: ytterligare x1.20.
- Duoplatser mot en förstärkt solo (extrakort på): x1.10.
- Motståndartier, läst från motståndarsidans snitt-1v1-rating - 1v2 har ingen egen rating.
- Motståndare just nu i 1v2-topplistans topp 3: x1.35, vid vinst som förlust.
- Hela produkten har ett tak på x4.0; vinstbonusen x1.5 läggs ovanpå taket.

Standard med extrakort på: solon tjänar 1125 XP för en förlust och 1687 för en vinst; varje duomedlem 825/1237.

Serieguld: 40 (vinnande sida) eller 20 (förlorande sida), x endast motståndartier - plats-, handikapps- och podiefaktorerna bor på XP:n. Standard: 60/30.

<color=#FFD94D><b>FFA - MÄTAREN</b></color>

FFA betalar för STRIDEN, inte för tid i lobbyn. Formeln, i läsbar form:

- Arbetsenheten är <color=#7FD4FF>strider</color>: varje avgörande rond som någon i matchen vinner. <color=#FF6666>Camping tillför potten ingenting</color>, och sistaplatsandelen den ger är den minsta delen av vad alla andra genererade.
- Ett takttak begränsar hur fort strider betalas ut. För en lobby med P spelare förväntas en strid ungefär var 3.08 + 6.54 x P sekund (P räknas som minst 3 och högst 6 här), och matchen betalar högst DUBBLA den takten över matchens förflutna tid på serverns klocka - förhalning eller poängodling kan inte springa ifrån det.
- Basgraden är 3.5 guld per spelarminut, +5% för varje spelare över 4. En FFA med 10 spelare är spelets bästa guldtakt.
- Placeringen formar din andel av potten: 1:a plats tjänar 1.666x lobbysnittet, sista plats 0.334x - ungefär en 5x-spridning. Spelare som delar plats delar samma andel.
- Ett starkare fält multiplicerar potten: dina motståndares snitt-tier delat med 1.5, så ett standardfält på 1500 är exakt x1.0. Casual-lobbyer tar bottenfaktorn (cirka x0.667) och rör aldrig ratingar.
- Potten är ett guldbelopp. 55% betalas direkt som placeringsguld (minst 1). Övriga 45% betalas som XP med 100 XP per pottpoäng (minst 50 XP), som droppar tillbaka som guld genom den vanliga omvandlingen.
- Placeringen i sig sorteras efter poäng, sedan alla vunna ronder (även förbrukade), sedan kills där lobbyns kill-särskiljning är aktiv; kvarvarande oavgjorda delar plats.
- Spöken och avhoppare med tidig frist är obetalda och orankade för den matchen: att lämna innan fältet gjort 2 halvpoäng, med egen räkning (poäng, halvpoäng, kills) på noll, tar dig ur den helt.

<color=#FFD94D><b>NIVÅER OCH XP-TILL-GULD-DROPPET</b></color>

- XP omvandlas enligt <color=#7FE87F>100 XP = 1 guld</color>, utbetalt varje gång din löpande total korsar ett hundramärke. Varje läges XP - turneringspriser inräknade - matar samma total.
- Att kliva in i nivå L kostar 100 x L^1.5 XP, trunkerat: nivå 2 kostar 282, nivå 5 kostar 1118, nivå 10 kostar 3162, nivå 50 kostar 35355, nivå 100 kostar 100000. Maxnivån är 100.
- Att gå in i en nivå delbar med 5 betalar bonusguld: <color=#7FE87F>100g för nivåerna 5 till 50, 500g för 55 till 100</color> - 6000g under en livstid om du når taket. Det landar i samma stund som någon XP-utdelning tar dig över nivån - vilket läge som helst, turneringspriser inräknade; en nivåhöjning under en FFA-match syns inuti den matchens +g-siffra.

<color=#FFD94D><b>PRESTATIONSGULD</b></color>

Varje prestation betalar <color=#7FE87F>100g</color> om den inte listas här:

- <color=#7FD4FF>1000g</color> - Sid Slayer, Stan Slayer, Stormästare (nå 2330), Touch Grass, Babel.
- <color=#7FD4FF>500g</color> - Mästare (nå 1980), Lagutklassning, Upp ur askan, Casual-erövrare, Tvillingar!, Odödlig, Fientligt övertagande, Dödstal.
- <color=#7FD4FF>300g</color> - Riggad kortlek, Felfri, Silly Drill, Ut på djupt vatten, Hundraklubben, Ostoppbar, Objuden gäst, Krossat hjärta, Dragoman.

FFA-utklassningarna nästlas: en 5-0-vinst i en 5-spelarlobby betalar Storstädning (100g) + Objuden gäst (300g) + Fientligt övertagande (500g) i en och samma match. Översättarprestationerna (Rosetta, Dragoman, Babel) utlöses vid 10, 100 och 1000 godkända aktiva strängar.

<color=#8A8A93>Utanför matcher: Discord-serverboostare betalas 2000g i månaden, och communitykonstnärer tjänar 30% royalty (avrundad nedåt till helt guld) när en annan spelare köper deras artikel - gåvor betalar inget.</color>$s256$)
  , ('c14135018e41f6f6', 'uk', 'befb751987d134277812bfa647884dbbdeffbd1f', $s256$Кожна завершена гра платить XP, XP конвертується в золото за курсом 100 XP = 1 золото, а рейтингова гра множить базові нагороди нижче на ранговий рівень суперника. Це таблиця виплат - точні числа, режим за режимом. (Подіумні призи турнірів окремо; див. <color=#7FD4FF>Терміни й технічні поразки</color>.)

<color=#FFD94D><b>МНОЖНИК РІВНЯ</b></color>

У рейтинговій грі базові нагороди множаться на ранговий рівень СУПЕРНИКА - <color=#7FE87F>перемога чи поразка. Гра вгору завжди платить.</color>

<color=#7FD4FF>Початківець</color> (до 1500) - x1.0
<color=#7FD4FF>Середній</color> (1500 і більше) - x1.5
<color=#7FD4FF>Просунутий</color> (1675 і більше) - x2.0
<color=#7FD4FF>Майстер</color> (1980 і більше) - x2.5
<color=#7FD4FF>Грандмайстер</color> (2330 і більше) - x3.0

Він застосовується до XP і до золота серій, а суперник без рейтингу в записі рахується як 1500 (x1.5). Що таке «рейтинг суперника»: їхній рейтинг 1v1 в 1v1, середній рейтинг 2v2 команди суперників у 2v2, середній рейтинг 1v1 протилежної сторони в 1v2 і середній рейтинг FFA ваших суперників у FFA.

<color=#FFD94D><b>1v1</b></color>

За гру, множники стакаються, потім сума обрізається до цілого:

- База <color=#7FE87F>250 XP</color> за завершену гру, звичайні включно.
- Перемога у грі: x1.5. Рейтингова: x1.5. Рівень суперника: x1.0 до x3.0 (лише рейтингові).
- Суха перемога (суперник на 0 раундів) додає рівні +100 XP, після множників.

Точні приклади: звичайна поразка 250, звичайна перемога 375; рейтингова поразка проти Початківця 375; рейтингова перемога проти Початківця 562, проти Середнього 843, проти Грандмайстра 1687 (+100 зверху, якщо 5-0).

Золото серії, лише рейтинговий BO3 - звичайна гра серій не створює і не платить нічого:

- Той, хто програв: 5 x рівень суперника, обрізано. Переможець: удвічі більше.
- Переможець подвоює ЩЕ РАЗ, якщо переможений зараз сидить у топ-3 таблиці лідерів.
- +2 рівно зверху за суху 2-0.
- Переможець/переможений за рівнем суперника, до подіуму і сухої: Початківець 10/5, Середній 14/7, Просунутий 20/10, Майстер 24/12, Грандмайстер 30/15.

<color=#FFD94D><b>2v2</b></color>

- За гру: 600 XP x рівень команди суперників, потім x1.5, якщо ваша команда виграла гру.
- Типове лобі всіх-по-1500: 900 XP за поразку, 1350 за перемогу.
- Золото серії: 50 (кожному переможцю) або 25 (кожному переможеному), x рівень команди суперників. Типове лобі: 75/37.

<color=#FFD94D><b>1v2</b></color>

База 500 XP за гру, x1.5 за перемогу, далі по-місцевий множник складності:

- Місце соло: x1.5.
- Соло, що грає БЕЗ гандикапу додаткового вибору: ще x1.20.
- Місця дуо проти посиленого соло (додатковий вибір увімкнено): x1.10.
- Рівень суперника, читаний із середнього рейтингу 1v1 протилежної сторони - власного рейтингу 1v2 не існує.
- Суперник зараз у топ-3 таблиці 1v2: x1.35, перемога чи поразка.
- Весь добуток обмежений x4.0; бонус за перемогу x1.5 застосовується поверх стелі.

Типові значення з увімкненим додатковим вибором: соло заробляє 1125 XP за поразку і 1687 за перемогу; кожен гравець дуо - 825/1237.

Золото серії: 40 (переможна сторона) або 20 (сторона, що програла), x лише рівень суперника - місце, гандикап і подіум живуть на XP. Типово: 60/30.

<color=#FFD94D><b>FFA - ЛІЧИЛЬНИК</b></color>

FFA платить за БІЙ, а не за час у лобі. Формула, в читабельному вигляді:

- Одиниця роботи - <color=#7FD4FF>бої</color>: кожен вирішальний раунд, здобутий будь-ким у грі. <color=#FF6666>Кемпінг не додає в банк нічого</color>, а частка останнього місця, яку він заробляє, - найменший шматок того, що згенерували всі інші.
- Стеля темпу обмежує, як швидко бої переводяться в гроші. Для лобі з P гравців один бій очікується приблизно кожні 3.08 + 6.54 x P секунд (P тут рахується як щонайменше 3 і щонайбільше 6), і гра платить щонайбільше ПОДВІЙНИЙ цей темп упродовж часу гри за годинником сервера - затягування чи фарм очок його не обженуть.
- Базовий курс - 3.5 золота за гравце-хвилину, +5% за кожного гравця понад 4. FFA на 10 гравців - найкращий курс золота в грі.
- Місце формує вашу частку банку: 1-ше заробляє 1.666x середнього по лобі, останнє - 0.334x, розкид близько 5x. Гравці зі спільним місцем ділять однакову частку.
- Сильніше поле множить банк: середній рівень ваших суперників, поділений на 1.5, тож типове поле 1500 - рівно x1.0. Звичайні лобі беруть нижній коефіцієнт (близько x0.667) і рейтингів не торкаються.
- Банк - це сума золота. 55% платиться напряму як золото за місце (мінімум 1). Решта 45% платиться як XP по 100 XP за пункт банку (мінімум 50 XP), що крапає назад золотом через звичайну конвертацію.
- Саме місце сортується за очками, далі всіма здобутими виграними раундами (з витраченими включно), далі вбивствами там, де активний тайбрейк вбивств лобі; решта нічиїх ділять місце.
- Привиди і гравці з пільгою раннього виходу за ту гру не отримують ні виплат, ні рейтингу: вихід до 2 набраних полем половинок очок із власним ще нульовим підсумком (очки, половинки, вбивства) виводить вас із неї цілком.

<color=#FFD94D><b>РІВНІ І КРАПЕЛЬНИЦЯ XP-В-ЗОЛОТО</b></color>

- XP конвертується за курсом <color=#7FE87F>100 XP = 1 золото</color>, виплачуваним щоразу, коли ваш накопичений підсумок перетинає сотню. XP кожного режиму - з турнірними призами включно - живить один спільний підсумок.
- Підйом на рівень L коштує 100 x L^1.5 XP, обрізано: рівень 2 коштує 282, рівень 5 - 1118, рівень 10 - 3162, рівень 50 - 35355, рівень 100 - 100000. Максимальний рівень - 100.
- Вхід на рівень, кратний 5, платить бонусне золото: <color=#7FE87F>100g за рівні з 5 по 50, 500g за 55 по 100</color> - 6000g за все життя, якщо дійдете до стелі. Воно падає в мить, коли будь-яка виплата XP дає рівень - будь-який режим, турнірні призи включно; дінь посеред гри FFA з’являється всередині +g тієї гри.

<color=#FFD94D><b>ЗОЛОТО ЗА ДОСЯГНЕННЯ</b></color>

Кожне досягнення платить <color=#7FE87F>100g</color>, якщо не вказано тут:

- <color=#7FD4FF>1000g</color> - Sid Slayer, Stan Slayer, Грандмайстер (досягніть 2330), Торкніться трави, Вавилон.
- <color=#7FD4FF>500g</color> - Майстер (досягніть 1980), Командний розгром, Повсталий з попелу, Підкорювач звичайних, Близнюки!, Безсмертний, Вороже поглинання, Убивства.
- <color=#7FD4FF>300g</color> - Підтасована колода, Бездоганний, Silly Drill, З головою у вир, Клуб сотні, Нестримний, Незваний гість, Розбите серце, Драгоман.

Сухі FFA вкладаються: одна перемога 5-0 у лобі на 5 гравців платить Генеральне прибирання (100g) + Незваний гість (300g) + Вороже поглинання (500g) за одну гру. Перекладацькі досягнення (Розетта, Драгоман, Вавилон) спрацьовують на 10, 100 і 1000 схвалених живих рядків.

<color=#8A8A93>Поза матчами: бустери сервера Discord отримують 2000g щомісяця, а художники спільноти заробляють 30% роялті (округлено вниз до цілого золота), коли інший гравець купує їхній предмет - подарунки не платять нічого.</color>$s256$)
  , ('c19efa9de8c603da', 'es', '1462856754fe43cab560f9ae38427dfb892331a3', $s256$Todo torneo pasa por MD de Discord del bot SCR. Ninguno te llega si tu Discord no está vinculado (F5, pestaña Vincular Discord). Los avisos grandes (cierre, partida activa, resultados) son duraderos - si el bot está caído cuando uno salta, reintenta hasta que tu MD aterriza. Los empujoncitos del día de juego (empieza-en-15, siguiente-turno, te-esperamos) son de mejor esfuerzo y pueden perderse con un reinicio del bot.

<color=#FFD94D><b>ANTES DEL TORNEO</b></color>

<color=#7FD4FF>Consulta de disponibilidad</color> - enviada de 1 a 4 días antes del cierre, cuando el torneo tiene jugadores suficientes. Dos botones:
- 'Sí, cuento' - edita el mensaje a una confirmación. No cambia nada en el servidor; ya estabas inscrito.
- 'No, sácame' - retira tu inscripción, exactamente igual que darte de baja en el juego. Sin penalización.

<color=#7FD4FF>MD de cierre</color> - estás dentro. Sync: tu hora de inicio más el contrato (ten ROUNDS abierto a esa hora). Async: cómo coordinarse y jugar. Si el servidor te vio por última vez con una versión vieja del mod, se añade un aviso de actualización - actualiza antes de jugar. Sin botones.

<color=#7FD4FF>Retirado al cierre</color> (sync) - el campo acordó una hora que no marcaste como disponible, así que tu inscripción se retiró. Sin penalización; inscríbete de nuevo la semana que viene.

Si el cierre se aplaza una semana en cambio (pocos jugadores, o ninguna franja en la que coincidan 8), sale una consulta de disponibilidad fresca para la nueva fecha.

<color=#FFD94D><b>DÍA DE JUEGO SYNC</b></color>

<color=#7FD4FF>Empieza en 15 minutos</color> - abre ROUNDS ya y quédate en el menú principal; el mod hace el resto. También se publica en el canal del torneo.

<color=#7FD4FF>Partida lista</color> - tu partida contra X está lista, entra a ROUNDS ya. <color=#FF6666>No presentarse pierde la partida en pocos minutos.</color>

<color=#7FD4FF>Siguiente turno</color> (rondas 2 en adelante) - tu siguiente rival y hora de inicio tras un respiro corto, sin prisa. ¿Queréis jugar ya? Pulsad AMBOS Jugar Ahora en la pestaña Torneos de F5.

<color=#7FD4FF>Te esperamos</color> - enviado cuando a tu partida lista le quedan menos de 90 segundos para su límite de incomparecencia, o lo ha pasado mientras figuras presente. Significa: ve al menú principal de ROUNDS y deja cualquier partida casual. Se repite como mucho cada 5 minutos.

<color=#FFD94D><b>PARTIDAS ASYNC</b></color>

<color=#7FD4FF>Partida activa</color> - tu rival, el plazo de 7 días y cómo jugar: acordad una hora, alojad juntos una sala privada, el resultado se registra automáticamente.

<color=#7FD4FF>Aún pendiente</color> - cuando tu partida lleva 3 días lista sin jugarse, un recordatorio diario con tu plazo y cómo coordinarse. Sin botones.

<color=#7FD4FF>Check-in del plazo</color> - enviado en las últimas 24 horas antes de tu plazo. Tres botones, y tu última respuesta sustituye a las anteriores:
- 'Sí - planeamos jugar hoy' - se registra, y <color=#7FE87F>extiende el plazo 24 horas</color> - una vez por rival por torneo. Pulsarlo una segunda vez registra la respuesta pero el plazo no se mueve.
- 'Le escribí - sin respuesta / lo dejó' - se registra.
- 'Aún no - seguimos coordinando' - se registra.

Lo que vale una respuesta: si el plazo pasa con la partida sin decidir y nadie por delante, <color=#7FE87F>un jugador que respondió el check-in - cualquiera de las tres respuestas - gana a uno que calló.</color> El orden completo de resolución está en <color=#7FD4FF>Plazos e incomparecencias</color>. Los botones recomprueban que tu Discord siga vinculado a la misma cuenta antes de actuar.

<color=#FFD94D><b>RESULTADOS</b></color>

Tras cada partida, ambos lados reciben un MD de conclusión honesto sobre cómo terminó: una victoria jugada dice que ganaste; una incomparecencia dice 'Avanzas - tu rival no compareció'; una incomparecencia mutua dice 'Avanzas por el desempate de incomparecencia'. Una incomparecencia nunca se disfraza de victoria jugada.

Cuando el cuadro se completa, el podio se anuncia en el canal del torneo y se reparten los roles de trofeo.

<color=#FFD94D><b>COMANDOS Y EL TABLÓN</b></color>

<color=#7FD4FF>/dm-opponent</color> seguido de tu mensaje - el bot lo reenvía a los MD de tu rival actual de torneo. Limitado a 8 mensajes por minuto.

<color=#7FD4FF>/opp-online</color> - comprueba si tu rival de torneo figura ahora mismo como conectado en Discord.

El canal del torneo mantiene un tablón vivo para ambos tipos de torneo, refrescado cada 2 minutos.$s256$)
  , ('c19efa9de8c603da', 'ru', '1462856754fe43cab560f9ae38427dfb892331a3', $s256$Каждый турнир идёт через Discord-ЛС от бота SCR. Ни одно из них не дойдёт, если твой Discord не привязан (F5, вкладка Привязка Discord). Большие уведомления (закрытие записи, матч жив, результаты) - надёжные: если бот лежал, когда одно из них выстрелило, он повторяет, пока твоё ЛС не дойдёт. Подталкивания игрового дня (старт-через-15, следующий матч, ждём-тебя) - по возможности, и их можно пропустить через рестарт бота.

<color=#FFD94D><b>ПЕРЕД ТУРНИРОМ</b></color>

<color=#7FD4FF>Проверка доступности</color> - отправляется за 1-4 дня до закрытия записи, когда у турнира достаточно игроков. Две кнопки:
- «Да, я в деле» - превращает сообщение в подтверждение. На сервере ничего не меняется; ты и так был записан.
- «Нет, снимите меня» - снимает твою запись, ровно как снятие в игре. Без штрафа.

<color=#7FD4FF>ЛС о закрытии</color> - ты в деле. Синхро: твоё время старта плюс контракт (держи ROUNDS открытым к этому времени). Асинхро: как скоординироваться и сыграть. Если сервер в последний раз видел тебя на старой версии мода, добавляется предупреждение об обновлении - обновись до игры. Без кнопок.

<color=#7FD4FF>Снят при закрытии</color> (синхро) - участники сошлись на времени, которое ты не отметил как доступное, и твоя запись снята. Без штрафа; запишись снова на следующей неделе.

Если закрытие вместо этого сдвигается на неделю (слишком мало игроков или нет слота, устраивающего 8), на новую дату уходит свежая проверка доступности.

<color=#FFD94D><b>ИГРОВОЙ ДЕНЬ СИНХРО</b></color>

<color=#7FD4FF>Старт через 15 минут</color> - открой ROUNDS сейчас и сиди в главном меню; остальное сделает мод. Также постится в канал турнира.

<color=#7FD4FF>Матч готов</color> - твой матч против X готов, заходи в ROUNDS сейчас. <color=#FF6666>Неявка через несколько минут станет техпоражением.</color>

<color=#7FD4FF>Следующий матч</color> (раунды 2 и дальше) - твой следующий соперник и время старта после короткой передышки, без спешки. Хотите сыграть сразу? Вы ОБА жмёте Играть сейчас на вкладке Турниры в F5.

<color=#7FD4FF>Ждём тебя</color> - отправляется, когда твоему готовому матчу меньше 90 секунд до дедлайна неявки, или когда он уже за ним, а ты отмечен присутствующим. Значит: иди в главное меню ROUNDS и выйди из любой казуальной игры. Повторяется не чаще чем раз в 5 минут.

<color=#FFD94D><b>АСИНХРО-МАТЧИ</b></color>

<color=#7FD4FF>Матч жив</color> - твой соперник, 7-дневный дедлайн и как играть: договоритесь о времени, вместе захостите приватное лобби, результат запишется автоматически.

<color=#7FD4FF>Всё ещё не сыгран</color> - когда твой матч просидел готовым 3 дня без игры, ежедневное напоминание с твоим дедлайном и как скоординироваться. Без кнопок.

<color=#7FD4FF>Чек-ин дедлайна</color> - отправляется в последние 24 часа перед дедлайном. Три кнопки, и твой последний ответ заменяет прежние:
- «Да - планируем сыграть сегодня» - записывается и <color=#7FE87F>продлевает дедлайн на 24 часа</color> - один раз на соперника за турнир. Второе нажатие записывает ответ, но дедлайн стоит на месте.
- «Я писал - нет ответа / он ушёл» - записывается.
- «Пока нет - ещё координируемся» - записывается.

Чего стоит ответ: если дедлайн проходит с нерешённым матчем и никто не ведёт, <color=#7FE87F>игрок, ответивший на чек-ин - любым из трёх ответов - побеждает игрока, который промолчал.</color> Полный порядок разбора - в <color=#7FD4FF>Дедлайны и техпоражения</color>. Кнопки перед действием перепроверяют, что твой Discord всё ещё привязан к тому же аккаунту.

<color=#FFD94D><b>РЕЗУЛЬТАТЫ</b></color>

После каждого матча обе стороны получают завершающее ЛС, честное о том, как он кончился: сыгранная победа говорит, что ты победил; техпоражение говорит «Ты проходишь - соперник получил техпоражение»; обоюдная неявка говорит «Ты проходишь по тайбрейку неявок». Техпоражение никогда не наряжают сыгранной победой.

Когда сетка завершается, подиум объявляется в канале турнира и раздаются роли-трофеи.

<color=#FFD94D><b>КОМАНДЫ И ДОСКА</b></color>

<color=#7FD4FF>/dm-opponent</color> плюс твоё сообщение - бот передаёт его в ЛС твоего текущего турнирного соперника. Лимит 8 сообщений в минуту.

<color=#7FD4FF>/opp-online</color> - проверяет, показывается ли твой турнирный соперник сейчас онлайн в Discord.

Канал турнира держит живую доску по обоим видам турниров, обновляемую каждые 2 минуты.$s256$)
  , ('c19efa9de8c603da', 'sv', '1462856754fe43cab560f9ae38427dfb892331a3', $s256$Varje turnering körs genom Discord-DM från SCR-botten. Ingen av dem når dig om inte din Discord är länkad (F5, fliken Discord-länk). De stora meddelandena (låsning, match live, resultat) är beständiga - är botten nere när ett avfyras försöker den igen tills din DM landar. Speldagens knuffar (startar-om-15, näst-på-tur, väntar-på-dig) är bästa försök och kan missas över en botomstart.

<color=#FFD94D><b>FÖRE TURNERINGEN</b></color>

<color=#7FD4FF>Tillgänglighetskoll</color> - skickas 1 till 4 dagar före låsningen, när turneringen har tillräckligt många spelare. Två knappar:
- 'Ja, jag är med' - redigerar meddelandet till en bekräftelse. Den ändrar ingenting på servern; du var redan anmäld.
- 'Nej, ta bort mig' - tar bort din anmälan, precis som att avanmäla sig i spelet. Inget straff.

<color=#7FD4FF>Låsnings-DM</color> - du är med. Sync: din starttid plus kontraktet (ha ROUNDS öppet vid den tiden). Async: hur ni koordinerar och spelar. Om servern senast såg dig på en gammal moddversion bifogas en uppdateringsvarning - uppdatera innan du spelar. Inga knappar.

<color=#7FD4FF>Borttagen vid låsning</color> (sync) - fältet enades om en tid du inte markerat som möjlig, så din anmälan togs bort. Inget straff; anmäl dig igen nästa vecka.

Om låsningen i stället skjuts en vecka (för få spelare, eller ingen tid som 8 spelare kan enas om) går en ny tillgänglighetskoll ut för det nya datumet.

<color=#FFD94D><b>SYNC-SPELDAGEN</b></color>

<color=#7FD4FF>Startar om 15 minuter</color> - öppna ROUNDS nu och sitt i huvudmenyn; modden gör resten. Postas också i turneringskanalen.

<color=#7FD4FF>Match redo</color> - din match mot X är redo, in i ROUNDS nu. <color=#FF6666>Att inte dyka upp ger walkover inom några minuter.</color>

<color=#7FD4FF>Näst på tur</color> (rond 2 och senare) - din nästa motståndare och starttid efter en kort andhämtning, ingen brådska. Vill ni spela direkt? Ni trycker BÅDA på Spela nu på F5-fliken Turneringar.

<color=#7FD4FF>Väntar på dig</color> - skickas när din redo-match är under 90 sekunder från sin walkover-gräns, eller står förbi den medan du är markerad som närvarande. Det betyder: ta dig till ROUNDS huvudmeny och lämna alla casual-matcher. Upprepas högst var 5:e minut.

<color=#FFD94D><b>ASYNC-MATCHER</b></color>

<color=#7FD4FF>Matchen är live</color> - din motståndare, 7-dagarsfristen och hur ni spelar: kom överens om en tid, hosta en privat lobby ihop, resultatet registreras automatiskt.

<color=#7FD4FF>Fortfarande ospelad</color> - när din match legat redo i 3 dagar ospelad, en daglig påminnelse med din tidsfrist och hur ni koordinerar. Inga knappar.

<color=#7FD4FF>Tidsfrist-incheckning</color> - skickas under de sista 24 timmarna före din tidsfrist. Tre knappar, och ditt senaste svar ersätter tidigare:
- 'Ja - vi tänker spela idag' - registreras, och <color=#7FE87F>förlänger tidsfristen 24 timmar</color> - en gång per motståndare per turnering. Ett andra tryck registrerar svaret men tidsfristen står kvar.
- 'Jag hörde av mig - inget svar / de slutade' - registreras.
- 'Inte än - vi koordinerar fortfarande' - registreras.

Vad ett svar är värt: om tidsfristen passerar med matchen oavgjord och ingen i ledning, <color=#7FE87F>slår en spelare som svarade på incheckningen - vilket som helst av de tre svaren - en spelare som förblev tyst.</color> Hela avgörandeordningen finns i <color=#7FD4FF>Tidsfrister & walkover</color>. Knapparna kontrollerar på nytt att din Discord fortfarande är länkad till samma konto innan de agerar.

<color=#FFD94D><b>RESULTAT</b></color>

Efter varje match får båda sidor en avslutnings-DM som är ärlig om hur den slutade: en spelad vinst säger att du vann; en walkover säger 'Du går vidare - din motståndare lämnade walkover'; ett ömsesidigt uteblivande säger 'Du går vidare på uteblivande-särskiljningen'. En walkover kläs aldrig ut till en spelad vinst.

När bracketen är klar tillkännages podiet i turneringskanalen och trofé-roller delas ut.

<color=#FFD94D><b>KOMMANDON OCH TAVLAN</b></color>

<color=#7FD4FF>/dm-opponent</color> följt av ditt meddelande - botten vidarebefordrar det till din nuvarande turneringsmotståndares DM. Begränsat till 8 meddelanden per minut.

<color=#7FD4FF>/opp-online</color> - kollar om din turneringsmotståndare just nu visas som online på Discord.

Turneringskanalen håller en levande tavla för båda turneringssorterna, uppdaterad varannan minut.$s256$)
  , ('c19efa9de8c603da', 'uk', '1462856754fe43cab560f9ae38427dfb892331a3', $s256$Кожен турнір іде через Discord DM від бота SCR. Жодне з них вас не досягне, якщо Discord не прив’язано (F5, вкладка Прив’язка Discord). Великі повідомлення (закриття, матч живий, результати) - надійні: якщо в момент події бот лежав, він повторюватиме, поки ваш DM не сяде. Штовхачі ігрового дня (старт-за-15, наступний матч, чекаємо-на-вас) - за можливості, і їх можна пропустити через рестарт бота.

<color=#FFD94D><b>ПЕРЕД ТУРНІРОМ</b></color>

<color=#7FD4FF>Перевірка доступності</color> - надсилається за 1-4 дні до закриття, щойно турнір має досить гравців. Дві кнопки:
- «Так, я в грі» - редагує повідомлення на підтвердження. На сервері нічого не змінює; ви вже були зареєстровані.
- «Ні, приберіть мене» - знімає вашу реєстрацію, рівно як зняття в грі. Без штрафу.

<color=#7FD4FF>DM про закриття</color> - ви в турнірі. Sync: ваш час старту плюс контракт (тримайте ROUNDS відкритим на той час). Async: як координуватись і грати. Якщо сервер востаннє бачив вас на старій версії мода, додається попередження про оновлення - оновіться до гри. Без кнопок.

<color=#7FD4FF>Знято при закритті</color> (sync) - поле зійшлося на часі, який ви не позначили доступним, тож вашу реєстрацію знято. Без штрафу; реєструйтеся знову наступного тижня.

Якщо закриття натомість зсувається на тиждень (замало гравців або немає слоту, на який згодні 8), на нову дату виходить свіжа перевірка доступності.

<color=#FFD94D><b>ІГРОВИЙ ДЕНЬ SYNC</b></color>

<color=#7FD4FF>Старт за 15 хвилин</color> - відкривайте ROUNDS зараз і сидіть у головному меню; решту зробить мод. Також поститься в канал турнірів.

<color=#7FD4FF>Матч готовий</color> - ваш матч проти X готовий, заходьте в ROUNDS негайно. <color=#FF6666>Неявка за кілька хвилин стане технічною поразкою.</color>

<color=#7FD4FF>Наступний</color> (раунди 2 і далі) - ваш наступний суперник і час старту після короткого перепочинку, без поспіху. Хочете грати одразу? ВИ ОБИДВА тиснете «Грати зараз» на вкладці Турніри в F5.

<color=#7FD4FF>Чекаємо на вас</color> - надсилається, коли вашому готовому матчу лишилося менш як 90 секунд до дедлайну неявки, або він уже за ним, поки ви позначені присутнім. Означає: ідіть у головне меню ROUNDS і покиньте будь-яку звичайну гру. Повторюється щонайбільше раз на 5 хвилин.

<color=#FFD94D><b>ASYNC-МАТЧІ</b></color>

<color=#7FD4FF>Матч живий</color> - ваш суперник, 7-денний термін і як грати: домовтеся про час, хостіть приватне лобі разом, результат запишеться автоматично.

<color=#7FD4FF>Досі очікує</color> - коли ваш матч просидів готовим 3 дні незіграним, щоденне нагадування з вашим терміном і як координуватися. Без кнопок.

<color=#7FD4FF>Чек-ін терміну</color> - надсилається в останні 24 години перед вашим терміном. Три кнопки, і ваша остання відповідь замінює попередні:
- «Так - плануємо зіграти сьогодні» - записується і <color=#7FE87F>подовжує термін на 24 години</color> - раз на суперника на турнір. Повторне натискання записує відповідь, але термін стоїть на місці.
- «Я писав - без відповіді / вони покинули» - записується.
- «Ще ні - досі домовляємось» - записується.

Чого варта відповідь: якщо термін минає з невирішеним матчем і без лідера в рахунку, <color=#7FE87F>гравець, що відповів на чек-ін - будь-якою з трьох відповідей - обходить гравця, що промовчав.</color> Повний порядок вирішення - у <color=#7FD4FF>Терміни й технічні поразки</color>. Кнопки перед дією ще раз перевіряють, що ваш Discord досі прив’язаний до того самого акаунта.

<color=#FFD94D><b>РЕЗУЛЬТАТИ</b></color>

Після кожного матчу обидві сторони отримують DM про завершення, чесний щодо того, як усе скінчилося: зіграна перемога каже, що ви виграли; технічна - «Ви проходите далі - суперник отримав технічну поразку»; взаємна неявка - «Ви проходите далі за тайбрейком неявок». Технічна поразка ніколи не вбирається в зіграну перемогу.

Коли сітка завершується, подіум оголошується в каналі турнірів і роздаються ролі-трофеї.

<color=#FFD94D><b>КОМАНДИ І ТАБЛО</b></color>

<color=#7FD4FF>/dm-opponent</color> з вашим повідомленням - бот ретранслює його в DM вашого поточного турнірного суперника. Ліміт 8 повідомлень на хвилину.

<color=#7FD4FF>/opp-online</color> - перевіряє, чи ваш турнірний суперник зараз показується онлайн у Discord.

Канал турнірів тримає живе табло для обох видів турнірів, оновлюване кожні 2 хвилини.$s256$)
  , ('c1b4072db0812e45', 'es', '3bb894d2341044a3da1369fb9b1cfb1ba55c742b', $s256$Un jugador solo se enfrenta a un dúo en una serie al mejor de 3.

<color=#FFD94D><b>CÓMO SE JUEGA</b></color>

- Es una cola por consentimiento, sin banda de Elo y sin confirmación de listos.
- El servidor asigna un solo y dos jugadores de dúo.
- La Carta inicial extra del Solo es opcional: el solo roba
  2 cartas en la elección inicial. En la cola aleatoria la
  activa cualquier jugador que opte por ella; en una sala
  alojada decide el ajuste del anfitrión.

<color=#FFD94D><b>PUNTUACIÓN</b></color>

- El primer lado en ganar 2 juegos gana la serie.
- El 1v2 es una beta SIN RANGO. Aún no se aplica rating.
- Los juegos se registran y contarán cuando llegue el modo ranked.

<color=#FFD94D><b>RECOMPENSAS</b></color>

- La XP base es 500 por juego, x1.5 al ganar - luego un
  multiplicador de dificultad la escala, con tope en x4
  (el bono de victoria va encima del tope):
  el solo gana x1.5 (y x1.20 más cuando la elección
  extra está apagada), un dúo frente a un solo potenciado
  gana x1.10, y el tier de rating de los rivales multiplica hasta x3.
  Enfrentar a un top-3 de 1v2 añade x1.35, ganes o pierdas.
- Fin de serie: 40 de Oro base por ganador, 20 por perdedor,
  escalado por el tier de rating de los rivales.
- La XP de juego se convierte en Oro a 100 XP = 1 Oro, y
  subir de nivel paga su Oro extra habitual.

<color=#FFD94D><b>COLUMNAS DE LA CLASIFICACIÓN</b></color>

- La pestaña tiene tablas separadas de Solo y Dúo.
- Solo apareces en las tablas de los roles que jugaste.
<color=#7FD4FF>Rank</color> - Orden de actividad: victorias, WR, juegos.
<color=#7FD4FF>Player</color> - Nombre visible del jugador.
<color=#7FD4FF>W-L</color> - Juegos ganados y perdidos solo en ese rol.
<color=#7FD4FF>WR</color> - Tasa de victorias en ese rol.
- Son tablas de actividad. No se ordenan por Oro.

<color=#FFD94D><b>OJO</b></color>

- Irse estando emparejado sin juegos jugados cancela la
  serie; una salida a mitad de juego deja el resultado al
  reporte normal de la partida. La beta no tiene contador de salidas.$s256$)
  , ('c1b4072db0812e45', 'ru', '3bb894d2341044a3da1369fb9b1cfb1ba55c742b', $s256$Один игрок соло против дуо в серии до 2 побед (BO3).

<color=#FFD94D><b>КАК ИГРАТЬ</b></color>

- Это очередь по согласию: без диапазона Elo и
  без подтверждения готовности.
- Сервер сам назначает одного соло и двух в дуо.
- Доп. стартовая карта Соло - опция: соло берёт
  2 карты в первой раздаче. В общей очереди её
  включает согласие любого игрока; в хостовом
  лобби решает настройка хоста.

<color=#FFD94D><b>СЧЁТ</b></color>

- Серию берёт сторона, первой выигравшая 2 игры.
- 1v2 - бета БЕЗ РЕЙТИНГА. Рейтинг пока не меняется.
- Игры записываются и зачтутся, когда выйдет
  рейтинговый режим.

<color=#FFD94D><b>НАГРАДЫ</b></color>

- Базовый XP - 500 за игру, x1.5 за победу - затем
  его масштабирует множитель сложности с потолком x4
  (бонус за победу идёт поверх потолка):
  соло получает x1.5 (и ещё x1.20 при выключенном
  доп. пике), дуо против усиленного соло - x1.10,
  а тир рейтинга соперников умножает до x3.
  Встреча с топ-3 игроком 1v2 добавляет x1.35,
  при победе и поражении.
- Конец серии: 40 базового золота победителю, 20
  проигравшему, масштабируется тиром соперников.
- XP за игры меняется на золото: 100 XP = 1 золото,
  а новые уровни платят свой обычный бонус.

<color=#FFD94D><b>СТОЛБЦЫ ТАБЛИЦЫ</b></color>

- На вкладке отдельные таблицы Соло и Дуо.
- Ты попадаешь только в таблицы сыгранных ролей.
<color=#7FD4FF>Rank</color> - Порядок активности: победы, WR, игры.
<color=#7FD4FF>Player</color> - Отображаемое имя игрока.
<color=#7FD4FF>W-L</color> - Победы и поражения только в этой роли.
<color=#7FD4FF>WR</color> - Доля побед в играх этой роли.
- Это таблицы активности. Они не сортируются по золоту.

<color=#FFD94D><b>НЮАНСЫ</b></color>

- Уход из зафиксированного матча без сыгранных игр
  отменяет серию; уход посреди игры оставляет
  результат обычному отчёту матча. У беты нет
  счётчика выходов.$s256$)
  , ('c1b4072db0812e45', 'sv', '3bb894d2341044a3da1369fb9b1cfb1ba55c742b', $s256$En solospelare möter en duo i en serie i bäst av 3.

<color=#FFD94D><b>SÅ SPELAR DU</b></color>

- Det här är en samtyckeskö utan Elo-spann och utan redobekräftelse.
- Servern utser en solospelare och två duospelare.
- Extra startkort för solo är valfritt: solon drar
  2 kort i den första dragningen. I slumpkön räcker
  det att någon spelare valt till det; i en värdlobby
  avgör värdens inställning.

<color=#FFD94D><b>POÄNG</b></color>

- Den sida som först vinner 2 matcher tar serien.
- 1v2 är en ORANKAD beta. Ingen rating tillämpas ännu.
- Matcherna registreras och räknas när ranked-läget lanseras.

<color=#FFD94D><b>BELÖNINGAR</b></color>

- Bas-XP är 500 per match, x1.5 vid vinst - sedan
  skalas det av en svårighetsmultiplikator, med tak
  på x4 (vinstbonusen läggs ovanpå taket):
  solon får x1.5 (och x1.20 till när extrakortet är
  av), en duo mot en förstärkt solo får x1.10, och
  motståndarnas ratingtier multiplicerar upp till x3.
  Att möta en topp-3-spelare i 1v2 ger x1.35,
  vid både vinst och förlust.
- Serieslut: 40 basguld per vinnare, 20 per förlorare,
  skalat efter motståndarnas ratingtier.
- Match-XP omvandlas till guld: 100 XP = 1 guld, och
  nya nivåer ger sitt vanliga bonusguld.

<color=#FFD94D><b>TOPPLISTANS KOLUMNER</b></color>

- Fliken har separata Solo- och Duo-listor.
- Du visas bara på listor för roller du har spelat.
<color=#7FD4FF>Rang</color> - Aktivitetsordning: vinster, sedan WR, sedan matcher.
<color=#7FD4FF>Spelare</color> - Spelarens visningsnamn.
<color=#7FD4FF>W-L</color> - Vunna och förlorade matcher i just den rollen.
<color=#7FD4FF>WR</color> - Andel vinster i den rollen.
- Det här är aktivitetslistor. De sorteras inte efter guld.

<color=#FFD94D><b>ATT TÄNKA PÅ</b></color>

- Att lämna i låst läge utan spelade matcher avbryter
  serien; ett avhopp mitt i en match lämnar resultatet
  till den vanliga matchrapporten. Betan har ingen
  avhoppsräknare.$s256$)
  , ('c1b4072db0812e45', 'uk', '3bb894d2341044a3da1369fb9b1cfb1ba55c742b', $s256$Один соло-гравець грає проти дуо в серії до 2 перемог (BO3).

<color=#FFD94D><b>ЯК ГРАТИ</b></color>

- Це черга за згодою: без діапазону Elo і без підтвердження готовності.
- Сервер призначає одного соло-гравця та двох гравців у дуо.
- Додатковий початковий вибір для соло необов’язковий:
  соло бере 2 карти під час першого вибору. У випадковій
  черзі його вмикає згода будь-кого з гравців; у
  хостованому лобі вирішує налаштування хоста.

<color=#FFD94D><b>РАХУНОК</b></color>

- Серію виграє сторона, що першою взяла 2 гри.
- 1v2 - бета БЕЗ РЕЙТИНГУ. Рейтинг поки не застосовується.
- Ігри записуються й зарахуються після запуску рейтингового режиму.

<color=#FFD94D><b>НАГОРОДИ</b></color>

- Базовий XP - 500 за гру, x1.5 за перемогу - далі
  його масштабує множник складності, зі стелею x4
  (бонус за перемогу сидить поверх стелі):
  соло заробляє x1.5 (і ще x1.20, коли додатковий
  вибір вимкнено), дуо проти посиленого соло - x1.10,
  а рівень рейтингу суперників множить до x3.
  Гра проти топ-3 гравця 1v2 додає x1.35, перемога чи поразка.
- Кінець серії: 40 базового золота кожному переможцю, 20
  кожному, хто програв, масштабовано рівнем рейтингу суперників.
- XP за ігри конвертується в золото: 100 XP = 1 золото,
  а нові рівні платять звичний бонус золотом.

<color=#FFD94D><b>СТОВПЦІ ТАБЛИЦІ ЛІДЕРІВ</b></color>

- На вкладці окремі таблиці для соло та дуо.
- Ви з’являєтеся лише в таблицях ролей, у яких грали.
<color=#7FD4FF>Ранг</color> - Порядок активності: перемоги, потім WR, потім ігри.
<color=#7FD4FF>Гравець</color> - Ігрове ім’я гравця.
<color=#7FD4FF>W-L</color> - Перемоги й поразки лише в цій ролі.
<color=#7FD4FF>WR</color> - Відсоток перемог у цій ролі.
- Це таблиці активності. Вони не сортуються за золотом.

<color=#FFD94D><b>НЮАНСИ</b></color>

- Вихід у фіксації без зіграних ігор скасовує серію;
  вихід посеред гри лишає результат звичайному
  звіту про матч. Бета не має лічильника виходів.$s256$)
  , ('c4facebcda2e750a', 'es', '917f11b4b3832aee2c3e82d3c9f3ff95def18f6b', $s256$El Ranked 1v1 es el modo central del mod: series al mejor de 3, un rating Glicko, y dos formas de empezar una serie puntuada - la cola, o una sala privada donde ambos jugadores llevan el mod. Esta página cubre la cola desde Buscar hasta la sala, cómo una sala privada pasa a puntuar, y exactamente qué hace una desconexión.

<color=#FFD94D><b>ENCONTRAR RIVAL</b></color>

- Pulsar Buscar es en sí el consentimiento de ranked - entrar a la cola activa Ranked en tu cuenta.
- Tu banda de búsqueda empieza en 100 de rating a cada lado y se amplía mientras esperas: 200 a los 30 segundos, 400 a los 60, 800 a los 120. Nunca pasa de 800.
- El solape es <color=#7FD4FF>bilateral</color>: debes estar dentro de la banda de tu rival Y él dentro de la tuya. Quien lleva 2 minutos con banda ancha no puede atrapar a un recién llegado cuya banda estrecha lo excluye.
- Entre candidatos válidos, gana el rating más cercano.
- Los jugadores que rechazaste en los últimos 5 minutos, los bloqueados (en cualquier dirección) y las cuentas baneadas nunca se ofrecen.
- Buscar mientras juegas casual está bien - el quickplay vanilla y las salas casual normales nunca cancelan tu búsqueda. Entrar a cualquier sala creada por el mod (un torneo, 2v2, 1v2 o FFA) sí, de inmediato.
- Tras 30 minutos de búsqueda se te retira de la cola. <color=#8A8A93>Reencola si sigues ahí - el cliente 1v1 nunca reencola por ti.</color>

<color=#FFD94D><b>LISTOS, RECHAZAR Y LA SALA</b></color>

- Al emparejarte recibes un banner de ¡EMPAREJADO! con el nombre y rating de tu rival, un sonido y un parpadeo en la barra de tareas. Debes pulsar Listo - no hay auto-listo.
- Tienes 90 segundos, y cuando cualquiera pulsa Listo la ventana se reinicia a 90 frescos para ambos - un alt-tab lento siempre recibe el tiempo completo. Si se agota, los dos volvéis a buscar.
- Rechazar os devuelve a ambos a la cola y os impide volver a emparejaros durante 5 minutos. Una vez emitida la sala, rechazar ya no funciona.
- Cuando ambos están listos el servidor emite una sala ranked privada y elige la región de Photon: si ambos clientes reportan la misma región de casa, esa gana; si no, recurre a las regiones en vivo de los jugadores, luego a cualquiera de las de casa, luego a US.
- Tu cliente fija esa región antes de entrar, así los dos caéis en una sala en vez de en dos salas del mismo nombre en dos continentes.
- Si tu rival nunca llega: aviso a los 25 segundos, y vuelta automática al menú a los 60. <color=#7FE87F>Sin penalización para ninguno.</color>

<color=#FFD94D><b>RANKED EN SALA PRIVADA</b></color>

- Una partida por código puntúa cuando tres cosas son ciertas: tu Ranked está activado, tu rival tiene Ranked activado, y tu rival lleva el mod. Un rival que nunca ha usado el mod no puede hacer puntuar una partida jamás. (Una excepción deliberada: una serie viva sin terminar de una sentada anterior conserva su estado ranked cuando os volvéis a ver.)
- En cuanto ambos mods se ven, el cliente registra la serie en el servidor (el <color=#7FD4FF>preflight</color>) - así la serie existe, y admite apuestas, durante el juego 1.
- Si cualquiera tiene Ranked desactivado, el servidor rechaza la serie y recibes un aviso: la partida se juega como casual. Las partidas casual se registran igual - solo que nunca tocan el rating.
- Las salas de cola y de torneo se saltan estas comprobaciones por completo: encolarse fue el consentimiento.

<color=#FFD94D><b>LA SERIE</b></color>

- El primero en ganar 2 juegos se lleva la serie. <color=#7FE87F>El rating se mueve solo cuando una serie se completa</color> - la serie entera es un único resultado de rating, y los juegos sueltos nunca mueven rating por sí solos.
- Una serie sin decidir - al menos un juego jugado, nadie con 2 victorias - <color=#7FE87F>nunca caduca</color>. Juega con el mismo rival mañana o la semana que viene y el juego 1 sigue en pie; tu HUD retoma el marcador vigente en vez de reiniciar a 0-0.
- Esa regla de no-caducidad es deliberada: una ventana de caducidad permitía a un jugador 0-1 abajo abandonar la serie y esperar al reloj para esquivar la derrota.
- Una serie no-torneo donde nunca se terminó ningún juego se abandona a los 30 minutos; el próximo cruce empieza de cero. Las series de torneo esperan a su cuadro.
- Las apuestas de una serie estancada 60 minutos se reembolsan (series de torneo exceptuadas) - la serie en sí sigue siendo reanudable.
- Durante la ronda 1 de cada juego, el cliente reporta los puntos en vivo al servidor. Las apuestas se cierran cuando se anotan 2 puntos totales en el juego 1 (un 1-1 cuenta) - o en el momento en que se decide cualquier juego de la serie.

<color=#FFD94D><b>DESCONEXIONES</b></color>

Lo que hace una DC depende del marcador, y la juzga el jugador que SE QUEDÓ:

- Estabas a punto de partida (4 rondas) cuando tu rival se cayó: ganas el juego con el marcador vigente.
- 4-4: te llevas el juego, registrado como 5-4.
- En cualquier otro punto - incluido un rival que se cae yendo POR DELANTE - la partida se cancela. Nadie recibe victoria, nadie recibe derrota.
- Dejar una partida para entrar a tu propia partida ranked de cola se anuncia por adelantado y nunca cuenta en tu contra.

Las reglas antiabuso:

- Solo el jugador que se quedó en la sala y vio irse al otro puede reclamar una victoria por DC. <color=#7FE87F>El cliente de quien se va nunca puede otorgarse nada a sí mismo.</color>
- Si el rival se reconecta antes de que te vayas, la reclamación se descarta.
- Si AMBOS jugadores se caen, nadie se quedó a observar: ni victoria, ni marca de salida. Con un juego completado en el marcador la serie sigue activa y se reanuda la próxima vez que os veáis.
- <color=#FF6666>Un juego cancelado no borra la serie</color> - los juegos completados se mantienen, y la serie se reanuda como arriba.

<color=#FFD94D><b>PORCENTAJE DE SALIDA</b></color>

- Una DC ranked con juego de sustancia detrás (2 o más puntos, o una ronda completada, en la partida ACTUAL), sin nadie a punto de partida, se registra como salida contra quien se fue - como mucho una por jugador y serie.
- <color=#7FD4FF>% de salida</color> = DC ranked divididas entre victorias + derrotas + DC de series ranked. Menos del 5 por ciento se muestra verde, de 5 a menos de 15 ámbar, de 15 en adelante rojo - visible para todos en la clasificación.
- Una DC a punto de partida se convierte en victoria por DC para el otro jugador, no en marca de salida.

Para el árbol de decisión completo de qué se registra, ver <color=#7FD4FF>Cuándo cuenta una partida</color>.$s256$)
  , ('c4facebcda2e750a', 'ru', '917f11b4b3832aee2c3e82d3c9f3ff95def18f6b', $s256$Рейтинговый 1v1 - ядро мода: серии до 2 побед, один рейтинг Glicko и два способа начать рейтинговую серию - очередь или приватная комната, где оба игрока на моде. Эта страница покрывает очередь от Поиска до комнаты, то, как приватное лобби становится рейтинговым, и что именно делает отключение.

<color=#FFD94D><b>ПОИСК СОПЕРНИКА</b></color>

- Клик по Поиску сам по себе - согласие на рейтинг: вход в очередь включает Ranked на твоём аккаунте.
- Твоя полоса поиска начинается со 100 рейтинга в обе стороны и расширяется с ожиданием: 200 после 30 секунд, 400 после 60, 800 после 120. Шире 800 она не расширяется никогда.
- Пересечение <color=#7FD4FF>двустороннее</color>: ты должен быть внутри полосы соперника И он внутри твоей. Ждущий 2 минуты с широкой полосой не может схватить свежего очередника, чья узкая полоса его исключает.
- Среди годных кандидатов побеждает ближайший рейтинг.
- Игроки, которых ты отклонил за последние 5 минут, игроки в блоке (в любую сторону) и забаненные аккаунты не предлагаются никогда.
- Искать, играя казуал, можно - ванильный quickplay и обычные казуальные комнаты твой поиск не отменяют. Вход в любую выданную модом комнату (турнир, 2v2, 1v2 или FFA) отменяет немедленно.
- После 30 минут поиска тебя убирают из очереди. <color=#8A8A93>Перезайди, если ты ещё тут, - клиент 1v1 никогда не перезаходит за тебя.</color>

<color=#FFD94D><b>ГОТОВНОСТЬ, ОТКАЗ И КОМНАТА</b></color>

- На найденном матче ты получаешь баннер MATCH FOUND с именем и рейтингом соперника, звук и мигание в панели задач. Нужно нажать Готов - автоготовности нет.
- У тебя 90 секунд, и когда любой игрок жмёт Готов, окно сбрасывается на свежие 90 для обоих - медленный альт-табер всегда получает полное время. Если оно истекает, оба возвращаетесь в поиск.
- Отказ возвращает обоих в очередь и блокирует вашу пару от повторного сведения на 5 минут. Когда комната уже выдана, отказ больше не работает.
- Когда готовы оба, сервер выдаёт приватную рейтинговую комнату и выбирает регион Photon: если оба клиента сообщают один домашний регион, он и побеждает; иначе перебор: живые регионы игроков, затем любой домашний, затем US.
- Твой клиент закрепляет этот регион до входа, так что вы оба попадаете в одну комнату, а не в две одноимённые на двух континентах.
- Если соперник так и не пришёл: предупреждение на 25 секундах, затем автоматический возврат в меню на 60. <color=#7FE87F>Без штрафа для обеих сторон.</color>

<color=#FFD94D><b>РЕЙТИНГ В ПРИВАТНОЙ КОМНАТЕ</b></color>

- Игра по коду комнаты рейтингуется, когда верны три вещи: твой переключатель Ranked включён, у соперника включён Ranked, и соперник запускает мод. Соперник, никогда не запускавший мод, сделать игру рейтинговой не может. (Одно сознательное исключение: живая незавершённая серия с прошлой сессии сохраняет рейтинговый статус при новой встрече.)
- В момент, когда оба мода видят друг друга, клиент регистрирует серию на сервере (<color=#7FD4FF>префлайт</color>) - серия существует, и на неё можно ставить, уже во время игры 1.
- Если у любого игрока Ranked выключен, сервер отказывает серии, и ты получаешь одно уведомление: матч играется как казуал. Казуальные игры всё равно записываются - они просто никогда не трогают рейтинг.
- Комнаты очереди и турниров пропускают эти проверки целиком: очередь и была согласием.

<color=#FFD94D><b>СЕРИЯ</b></color>

- Серию берёт первый до 2 выигранных игр. <color=#7FE87F>Рейтинг двигается только при завершении серии</color> - вся серия это один рейтинговый исход, и отдельные игры сами по себе рейтинг не двигают никогда.
- Нерешённая серия - минимум одна сыгранная игра, никто не на 2 победах - <color=#7FE87F>не истекает никогда</color>. Сыграй с тем же соперником завтра или через неделю - игра 1 всё ещё стоит; твой HUD подхватит текущий счёт вместо старта с 0-0.
- Это правило без истечения сознательное: окно истечения позволяло игроку на 0-1 бросить серию и пересидеть часы, чтобы увернуться от поражения.
- Не турнирная серия, где не была закончена ни одна игра, бросается через 30 минут; следующая встреча начинается заново. Турнирные серии вместо этого ждут свою сетку.
- Ставки на серию, зависшую на 60 минут, возвращаются (кроме турнирных серий) - сама серия остаётся возобновимой.
- Во время раунда 1 каждой игры клиент сообщает серверу живые очки. Ставки закрываются, когда в игре 1 набрано 2 суммарных очка (1-1 считается), - или в момент, когда решена любая игра серии.

<color=#FFD94D><b>ОТКЛЮЧЕНИЯ</b></color>

Что делает DC, зависит от счёта, и судит его игрок, который ОСТАЛСЯ:

- Ты стоял на матч-пойнте (4 раунда), когда соперник отвалился: ты берёшь игру при текущем счёте.
- 4-4: ты берёшь игру, записывается 5-4.
- Всё остальное - включая соперника, отвалившегося ВЕДЯ, - игра отменяется. Никто не получает победу, никто не получает поражение.
- Выход из игры ради своего найденного рейтингового матча объявляется заранее и никогда не считается против тебя.

Правила против злоупотреблений:

- Требовать DC-победу может только игрок, который остался в комнате и видел уход другого. <color=#7FE87F>Клиент самого ушедшего не может присудить себе ничего.</color>
- Если соперник переподключается до твоего ухода, требование снимается.
- Если отвалились ОБА, наблюдать было некому: ни победы, ни отметки выхода. С законченной игрой на табло серия остаётся активной и возобновляется при следующей встрече.
- <color=#FF6666>Отменённая игра не стирает серию</color> - законченные игры стоят, и серия возобновляется, как описано выше.

<color=#FFD94D><b>ПРОЦЕНТ ВЫХОДОВ</b></color>

- Рейтинговый DC с осмысленной игрой за плечами (2 и больше очков или завершённый раунд в ТЕКУЩЕЙ игре), когда ни одна сторона не на матч-пойнте, записывается как выход на ушедшего - максимум один на игрока на серию.
- <color=#7FD4FF>% выходов</color> = рейтинговые DC, делённые на победы + поражения + DC рейтинговых серий. Меньше 5 процентов показывается зелёным, от 5 до 15 - янтарным, от 15 - красным; виден всем в таблице лидеров.
- DC на матч-пойнте становится DC-победой другого игрока, а не отметкой выхода.

Полное дерево решений «записано ли это» - см. <color=#7FD4FF>Когда игра засчитывается</color>.$s256$)
  , ('c4facebcda2e750a', 'sv', '917f11b4b3832aee2c3e82d3c9f3ff95def18f6b', $s256$Ranked 1v1 är moddens kärnläge: serier i bäst av 3, en Glicko-rating, och två sätt att starta en rankad serie - kön, eller ett privat rum där båda spelarna kör modden. Den här sidan täcker kön från Sök till rum, hur en privat lobby blir rankad, och exakt vad en disconnect gör.

<color=#FFD94D><b>ATT HITTA EN MOTSTÅNDARE</b></color>

- Att klicka på Sök är i sig ranked-samtycket - att gå med i kön slår på Ranked för ditt konto.
- Ditt sökspann börjar på 100 rating åt vardera hållet och vidgas medan du väntar: 200 efter 30 sekunder, 400 efter 60, 800 efter 120. Det vidgas aldrig förbi 800.
- Överlappningen är <color=#7FD4FF>dubbelsidig</color>: du måste vara inom din motståndares spann OCH de inom ditt. En 2-minutersväntare med brett spann kan inte hugga en färsk köare vars smala spann utesluter dem.
- Bland giltiga kandidater vinner den närmaste ratingen.
- Spelare du avböjt de senaste 5 minuterna, spelare du blockerat (åt endera hållet) och avstängda konton erbjuds aldrig.
- Att söka medan du spelar casual går bra - vanilla-quickplay och vanliga casual-rum avbryter aldrig din sökning. Att gå med i ett rum från modden (turnering, 2v2, 1v2 eller FFA) gör det, omedelbart.
- Efter 30 minuters sökning tas du ur kön. <color=#8A8A93>Köa igen om du fortfarande är kvar - 1v1-klienten köar aldrig om åt dig.</color>

<color=#FFD94D><b>REDO, AVBÖJ OCH RUMMET</b></color>

- Vid en match får du en MATCH HITTAD-banner med motståndarens namn och rating, ett ljud och ett blinkande aktivitetsfält. Du måste klicka Redo - det finns ingen auto-redo.
- Du har 90 sekunder, och när endera spelaren klickar Redo nollställs fönstret till nya 90 för båda - en långsam alt-tabbare får alltid full tid. Rinner det ut går ni båda tillbaka till sökningen.
- Avböj sätter er båda tillbaka i kön och blockerar er två från att paras om i 5 minuter. När rummet väl har utfärdats fungerar Avböj inte längre.
- När båda är redo utfärdar servern ett privat ranked-rum och väljer Photon-region: rapporterar båda klienterna samma hemregion vinner den; annars faller den genom spelarnas live-regioner, sedan endera hemregionen, sedan US.
- Din klient låser den regionen innan den ansluter, så ni båda landar i ett rum i stället för i två likanamnade rum på två kontinenter.
- Om din motståndare aldrig dyker upp: en varning vid 25 sekunder, sedan automatisk återgång till menyn vid 60. <color=#7FE87F>Inget straff för någondera sidan.</color>

<color=#FFD94D><b>RANKED I ETT PRIVAT RUM</b></color>

- En rumskodsmatch rankas när tre saker är sanna: din Ranked-inställning är på, din motståndare har Ranked aktiverat, och din motståndare kör modden. En motståndare som aldrig kört modden kan aldrig göra en match rankad. (Ett avsiktligt undantag: en levande oavslutad serie från en tidigare sittning behåller sin ranked-status när ni möts igen.)
- I samma stund som båda moddarna ser varandra registrerar klienten serien hos servern (<color=#7FD4FF>preflighten</color>) - så serien finns, och går att satsa på, redan under match 1.
- Har någon av er Ranked avstängt vägrar servern serien och du får en avisering: matchen spelas som casual. Casual-matcher registreras fortfarande - de rör bara aldrig rating.
- Kö- och turneringsrum hoppar över de här kontrollerna helt: att köa var samtycket.

<color=#FFD94D><b>SERIEN</b></color>

- Först till 2 matchvinster tar serien. <color=#7FE87F>Rating flyttas bara när en serie avslutas</color> - hela serien är ett enda ratingutfall, och enskilda matcher flyttar aldrig rating på egen hand.
- En oavgjord serie - minst en match spelad, ingen på 2 vinster - <color=#7FE87F>löper aldrig ut</color>. Spela samma motståndare imorgon eller nästa vecka och match 1 står kvar; din HUD plockar upp ställningen i stället för att börja om på 0-0.
- Regeln utan utgångsdatum är avsiktlig: ett utgångsfönster lät en spelare i underläge 0-1 överge serien och vänta ut klockan för att slippa förlusten.
- En icke-turneringsserie där ingen match någonsin avslutats överges efter 30 minuter; nästa möte börjar om. Turneringsserier väntar på sin bracket i stället.
- Vad på en serie som stått stilla i 60 minuter återbetalas (turneringsserier undantagna) - serien i sig förblir återupptagbar.
- Under rond 1 i varje match rapporterar klienten live-poäng till servern. Vadslagningen låses när 2 totala poäng gjorts i match 1 (ett 1-1 räknas) - eller i samma stund någon match i serien avgörs.

<color=#FFD94D><b>DISCONNECTS</b></color>

Vad en DC gör beror på ställningen, och den döms av spelaren som STANNADE:

- Du stod på matchboll (4 ronder) när din motståndare försvann: du vinner matchen på den stående ställningen.
- 4-4: du tar matchen, registrerad 5-4.
- Allt annat - inklusive en motståndare som droppar i LEDNING - matchen avbryts. Ingen får en vinst, ingen får en förlust.
- Att lämna en match för att ansluta till din egen köade ranked-match annonseras i förväg och räknas aldrig mot dig.

Reglerna mot missbruk:

- Bara spelaren som stannade i rummet och såg den andra lämna kan göra anspråk på en DC-vinst. <color=#7FE87F>En avhoppares egen klient kan aldrig tilldela sig själv någonting.</color>
- Återansluter motståndaren innan du lämnar släpps anspråket.
- Droppar BÅDA spelarna stannade ingen kvar som observerade: ingen vinst, ingen avhoppsmarkering. Med en avslutad match på tavlan förblir serien aktiv och återupptas nästa gång ni möts.
- <color=#FF6666>En avbruten match raderar inte serien</color> - avslutade matcher står kvar, och serien återupptas som ovan.

<color=#FFD94D><b>AVHOPPSPROCENT</b></color>

- En ranked-DC med meningsfullt spel bakom sig (2 eller fler poäng, eller en avslutad rond, i den PÅGÅENDE matchen), utan att någon sida stod på matchboll, registreras som ett avhopp mot avhopparen - högst ett per spelare och serie.
- <color=#7FD4FF>Avhopps-%</color> = ranked-DC:ar delat med ranked-serievinster + förluster + DC:ar. Under 5 procent visas grönt, 5 till under 15 bärnstensgult, 15 och uppåt rött - synligt för alla på topplistan.
- En DC på matchboll blir en DC-vinst för den andra spelaren i stället, inte en avhoppsmarkering.

För hela beslutsträdet om vad som registreras, se <color=#7FD4FF>När en match räknas</color>.$s256$)
  , ('c4facebcda2e750a', 'uk', '917f11b4b3832aee2c3e82d3c9f3ff95def18f6b', $s256$Ranked 1v1 - серцевина мода: серії best-of-3, один рейтинг Glicko і два способи почати оцінювану серію - черга, або приватна кімната, де мод мають обидва гравці. Ця сторінка покриває чергу від Пошуку до кімнати, як приватне лобі стає рейтинговим, і що саме робить дисконект.

<color=#FFD94D><b>ПОШУК СУПЕРНИКА</b></color>

- Клік по Пошуку і є згодою на рейтинг - вхід у чергу вмикає Ranked на вашому акаунті.
- Ваша смуга пошуку починається зі 100 рейтингу в обидва боки і ширшає з очікуванням: 200 після 30 секунд, 400 після 60, 800 після 120. Далі 800 вона не ширшає ніколи.
- Перекриття <color=#7FD4FF>двостороннє</color>: ви маєте бути всередині смуги суперника, І вони мають бути всередині вашої. 2-хвилинний очікувач із широкою смугою не схопить свіжого гравця, чия вузька смуга його виключає.
- Серед валідних кандидатів перемагає найближчий рейтинг.
- Гравці, яких ви відхилили за останні 5 хвилин, гравці, яких ви заблокували (в будь-який бік), і забанені акаунти не пропонуються ніколи.
- Шукати, граючи звичайну гру, - нормально: ванільний швидкий матч і звичайні кімнати пошук не скасовують ніколи. Вхід у будь-яку модову кімнату (турнір, 2v2, 1v2 чи FFA) скасовує його негайно.
- Після 30 хвилин пошуку вас знімають із черги. <color=#8A8A93>Станьте знову, якщо ви ще тут, - клієнт 1v1 сам за вас не повертається.</color>

<color=#FFD94D><b>ГОТОВНІСТЬ, ВІДХИЛЕННЯ І КІМНАТА</b></color>

- На матчі ви отримуєте банер МАТЧ ЗНАЙДЕНО з ім’ям і рейтингом суперника, звук і блимання панелі завдань. Треба клацнути Готовність - автоготовності немає.
- У вас 90 секунд, і коли будь-хто з гравців тисне Готовність, вікно скидається на свіжі 90 для обох - повільний альт-табер завжди отримує повний час. Якщо час вийде, обидва повертаються до пошуку.
- Відхилення повертає обох у чергу і блокує вашу пару від повторного злучення на 5 хвилин. Щойно кімнату видано, відхилення більше не працює.
- Коли обидва готові, сервер видає приватну рейтингову кімнату й обирає регіон Photon: якщо обидва клієнти звітують один домашній регіон, він і перемагає; інакше вибір падає через живі регіони гравців, потім будь-який домашній, потім US.
- Ваш клієнт пришпилює той регіон перед входом, тож ви обоє потрапляєте в одну кімнату, а не у дві однойменні на двох континентах.
- Якщо суперник так і не прийде: попередження на 25-й секунді, автоматичне повернення в меню на 60-й. <color=#7FE87F>Без штрафу для жодної сторони.</color>

<color=#FFD94D><b>РЕЙТИНГ У ПРИВАТНІЙ КІМНАТІ</b></color>

- Гра за кодом кімнати оцінюється, коли істинні три речі: ваш перемикач Ranked увімкнено, суперник має Ranked увімкнено, і суперник має мод. Суперник, що ніколи не запускав мод, зробити гру рейтинговою не може. (Один свідомий виняток: жива незавершена серія з ранішої сесії зберігає рейтинговий статус, коли ви зустрінетеся знову.)
- У мить, коли обидва моди бачать одне одного, клієнт реєструє серію на сервері (<color=#7FD4FF>preflight</color>) - тож серія існує, і на неї можна ставити, вже під час гри 1.
- Якщо в когось Ranked вимкнено, сервер відмовляє серії, і ви отримуєте одне сповіщення: матч грається як звичайний. Звичайні ігри теж записуються - вони просто ніколи не торкаються рейтингу.
- Кімнати черги і турнірів пропускають ці перевірки цілком: черга і була згодою.

<color=#FFD94D><b>СЕРІЯ</b></color>

- Серію бере перший до 2 виграних ігор. <color=#7FE87F>Рейтинг рухається лише коли серія завершується</color> - вся серія є одним рейтинговим результатом, і окремі ігри самі по собі рейтинг не рухають ніколи.
- Невирішена серія - принаймні одна зіграна гра, ніхто не на 2 перемогах - <color=#7FE87F>не спливає ніколи</color>. Зіграйте з тим самим суперником завтра чи через тиждень - гра 1 досі в силі; ваш HUD підхоплює поточний рахунок замість рестарту з 0-0.
- Це правило без строку давності свідоме: вікно давності дозволяло гравцеві в рахунку 0-1 покинути серію і пересидіти годинник, щоб ухилитися від поразки.
- Нетурнірна серія, де жодну гру так і не дограли, закидається через 30 хвилин; наступна зустріч починає з чистого. Турнірні серії натомість чекають своєї сітки.
- Ставки на серію, що застигла на 60 хвилин, повертаються (турнірні серії - виняток) - сама серія лишається відновлюваною.
- Під час раунду 1 кожної гри клієнт звітує живі очки серверу. Ставки замикаються, щойно у грі 1 набрано 2 сумарні очки (1-1 рахується) - або в мить, коли вирішено будь-яку гру серії.

<color=#FFD94D><b>ДИСКОНЕКТИ</b></color>

Що робить DC, залежить від рахунку, і судить його гравець, що ЛИШИВСЯ:

- Ви були на матч-пойнті (4 раунди), коли суперник відвалився: ви берете гру за поточним рахунком.
- 4-4: ви берете гру, записується 5-4.
- Будь-де інде - включно з суперником, що відвалюється, ВЕДУЧИ, - гра скасовується. Ніхто не отримує перемоги, ніхто поразки.
- Вихід із гри заради власного матчу з рейтингової черги оголошується заздалегідь і ніколи не рахується проти вас.

Правила проти зловживань:

- Лише гравець, що лишився в кімнаті й бачив вихід іншого, може заявити перемогу за DC. <color=#7FE87F>Клієнт того, хто вийшов, не може присудити собі нічого.</color>
- Якщо суперник перепід’єднається до вашого виходу, заявка знімається.
- Якщо відвалюються ОБИДВА, спостерігати не лишився ніхто: ні перемоги, ні позначки виходу. Із завершеною грою на табло серія лишається активною і відновлюється при наступній зустрічі.
- <color=#FF6666>Скасована гра не стирає серію</color> - завершені ігри в силі, і серія відновлюється, як вище.

<color=#FFD94D><b>ВІДСОТОК ВИХОДІВ</b></color>

- Рейтинговий DC зі змістовною грою за плечима (2 і більше очок або завершений раунд у ПОТОЧНІЙ грі), коли жодна сторона не на матч-пойнті, записується як вихід проти того, хто вийшов, - щонайбільше один на гравця на серію.
- <color=#7FD4FF>% виходів</color> = рейтингові DC, поділені на перемоги + поразки + DC рейтингових серій. Нижче 5 відсотків показується зеленим, від 5 до 15 - бурштиновим, 15 і вище - червоним; його бачать усі на таблиці лідерів.
- DC на матч-пойнті стає натомість перемогою за DC для іншого гравця, а не позначкою виходу.

Повне дерево рішень «чи це записано» - див. <color=#7FD4FF>Коли гра зараховується</color>.$s256$)
  , ('c5596757a88ea76b', 'es', 'a5a0320e13168f43cecad4cfc1ddee6c594f7202', $s256$Las apuestas de Oro corren sobre partidas en vivo de 1v1, 2v2 y FFA. Esta página cubre quién puede apostar, cómo se calculan las cuotas, exactamente cuándo abren y cierran las ventanas, y qué pasa con lo apostado.

<color=#FFD94D><b>QUIÉN PUEDE APOSTAR</b></color>

- Cualquier jugador registrado, apostando de 1 a 2000 de Oro por apuesta. Lo apostado se cobra en el momento de colocar la apuesta.
- No puedes apostar en una partida o sala en la que juegas, y los jugadores baneados no pueden apostar.
- <color=#7FE87F>Los espectadores SÍ pueden apostar.</color> Es seguro por diseño: las ventanas de abajo se cierran con la puntuación temprana, así que mirar una partida nunca te consigue una apuesta sobre un resultado ya decidido.
- Una apuesta por serie en 1v1 y 2v2; una apuesta por partida en FFA.
- Si algún participante lleva un mod anterior a 1.38.1, apostar en esa partida se rechaza. Los clientes viejos no pueden reportar puntos en vivo, así que el corte por puntuación no podría saltar nunca - <color=#FF6666>el sistema falla cerrado antes que dejar una ventana abierta.</color>
- Una cuenta de Discord vinculada puede colocar las mismas apuestas con los comandos del bot.

<color=#FFD94D><b>CUOTAS: 1v1 Y 2v2</b></color>

- Tu multiplicador es 1 dividido entre la probabilidad de victoria de tu lado, calculada con los ratings de ambos lados Y su RD (ver <color=#7FD4FF>Rating (Glicko-2)</color>). Suelo: 1.01x.
- La incertidumbre limita el precio. Con ambos lados establecidos (RD 100 o menos) el multiplicador puede llegar a 3.0x; el tope baja hasta 1.0x según la RD más alta sube a 300. Una cuenta nueva con RD 350 deja el precio por debajo de la puerta de aceptación de 1.10x - <color=#FF6666>sobre un desconocido simplemente no se puede apostar, así que un smurf no puede farmearse por Oro.</color>
- Un lado solo acepta apuestas a 1.10x o mejor; por debajo está bloqueado.
- El 2v2 cotiza sobre el rating medio de la pareja. El rating 2v2 propio de un jugador cuenta cuando tiene 10 series completadas; antes lo sustituye su rating 1v1.

<color=#FFD94D><b>CUOTAS: FFA</b></color>

- El servidor hace correr a cada jugador hacia los puntos objetivo de la sala y calcula la probabilidad real de que tu elegido lo consiga primero. Tu multiplicador es la mitad del precio justo - la casa se queda la otra mitad.
- Suelos: 2.0x en salas de 5 o más, 1.4x con 3-4 jugadores. Para grandes favoritos el suelo cede a 0.95 dividido entre su probabilidad de victoria, así que una apuesta de beneficio garantizado no puede existir.
- Tope: 5.0x, o la mitad del tamaño de la sala si es menor, y encoge cuando los ratings son inciertos.
- Un jugador aún sin partidas FFA se cotiza con su rating 1v1 a incertidumbre completa.

<color=#FFD94D><b>CUÁNDO ABREN Y CIERRAN LAS APUESTAS</b></color>

El corte son puntos anotados, nunca un reloj:

- <color=#7FD4FF>1v1 y 2v2</color> - abiertas desde que la serie existe. Cerradas cuando se anotan 2 puntos totales en el juego 1, o en el momento en que se decide cualquier juego de la serie. Las series de torneo siguen listadas durante toda la espera de días antes de que la pareja juegue de verdad.
- <color=#7FD4FF>FFA</color> - cada apuesta apunta a la SIGUIENTE partida de la sala. La ventana se cierra cuando el campo anota 2 puntos en esa partida (1 punto si los puntos objetivo de la sala son 3 o menos). Una sala solo se lista mientras una próxima partida es plausible: hasta 15 minutos mientras se forma sin partidas aún, y hasta 30 minutos tras su última partida registrada. <color=#FF6666>Las salas casual nunca admiten apuestas.</color> Los miembros que se fueron no son objetivos válidos.
- <color=#7FD4FF>Apuestas en fase de sala</color> - las salas alojadas de 2v2 y FFA aceptan apuestas mientras aún se LLENAN. Aún no se cotiza ninguna cuota; al darle a Empezar, la apuesta se cotiza con el campo final y se convierte en una apuesta normal - siempre que tu objetivo siga ahí y pasen las comprobaciones habituales. Cualquier otra cosa (objetivo que se fue, cuota demasiado baja, sala que no empieza en 6 horas) reembolsa lo apostado.
- El 1v2 no tiene apuestas en absoluto.

<color=#FFD94D><b>PAGOS Y LA TASA DEL COMBATIENTE</b></color>

- Un pago ganador incluye la devolución de lo apostado. El 1v1 y el 2v2 pagan apuesta x cuota redondeada al Oro más cercano; el FFA redondea HACIA ABAJO.
- Si la cuota guardada de tu apuesta ganadora era 1.50x o menos, el 20% del BENEFICIO va al combatiente o equipo que respaldaste - merecer apuestas también les paga a ellos. El pago potencial que se te cotiza al apostar ya incluye esta tasa.

<color=#FFD94D><b>REEMBOLSOS, Y DÓNDE VERLO TODO</b></color>

Un reembolso devuelve exactamente lo apostado:

- 1v1: una serie no-torneo sin partida reportada en sus primeros 30 minutos se abandona y reembolsa sus apuestas. Una serie estancada 60 minutos a mitad también reembolsa las suyas, aunque la serie siga siendo reanudable - <color=#FF6666>una apuesta reembolsada sigue reembolsada aunque esa serie se termine después.</color>
- 2v2: reembolsa solo cuando una serie se cancela. Las series pausadas por desconexión esperan el fallo del admin antes de liquidar nada.
- FFA: reembolsa solo una partida que nunca produjo resultado registrado. Las partidas jugadas siempre se liquidan como ganadas o perdidas.
- Con apuestas diminutas una VICTORIA puede pagar exactamente lo apostado (1g a 1.10x paga 1g). Sigue siendo victoria: lo que se muestra es el estado guardado de cada apuesta - abierta, ganada, perdida o reembolsada - no la aritmética.
- Tu historial completo de apuestas de todos los modos es el libro de apuestas del menú F5. Las partidas apostables en vivo se listan en el juego y se reflejan en el canal de apuestas en vivo de Discord y sus comandos de apuestas.$s256$)
  , ('c5596757a88ea76b', 'ru', 'a5a0320e13168f43cecad4cfc1ddee6c594f7202', $s256$Ставки золотом идут на живые игры 1v1, 2v2 и FFA. Эта страница покрывает, кто может ставить, как считаются коэффициенты, когда именно окна открываются и закрываются и что происходит со ставкой.

<color=#FFD94D><b>КТО МОЖЕТ СТАВИТЬ</b></color>

- Любой зарегистрированный игрок, от 1 до 2000 золота за ставку. Ставка списывается в момент размещения.
- Нельзя ставить на матч или лобби, в котором играешь сам, и забаненные ставить не могут.
- <color=#7FE87F>Зрители ставить МОГУТ.</color> Это безопасно по конструкции: окна ниже закрываются на ранних очках, так что просмотр игры никогда не даёт ставку на уже решённый результат.
- Одна ставка на серию в 1v1 и 2v2; одна ставка на игру в FFA.
- Если любой участник запускает мод старше 1.38.1, ставки на эту игру отклоняются. Старые клиенты не умеют сообщать живые очки, так что отсечка по очкам не могла бы сработать, - <color=#FF6666>система отказывает закрыто, а не оставляет окно открытым.</color>
- Привязанный аккаунт Discord может размещать те же ставки командами бота.

<color=#FFD94D><b>КОЭФФИЦИЕНТЫ: 1v1 И 2v2</b></color>

- Твой множитель - 1, делённая на шанс победы твоей стороны, посчитанный из рейтингов обеих сторон И их RD (см. <color=#7FD4FF>Рейтинги (Glicko-2)</color>). Пол: 1.01x.
- Неопределённость ограничивает цену. С обеими устоявшимися сторонами (RD 100 и ниже) множитель может дойти до 3.0x; потолок съезжает к 1.0x по мере роста большего RD к 300. Свежий аккаунт с RD 350 держит цену ниже приёмного порога 1.10x - <color=#FF6666>на неизвестного просто нельзя поставить, так что смурфа не пофармить на золото.</color>
- Сторона принимает ставки только при 1.10x и лучше; ниже она заблокирована.
- 2v2 ценится по среднему рейтингу пары. Собственный рейтинг 2v2 игрока считается после 10 завершённых серий; до того вместо него стоит его 1v1.

<color=#FFD94D><b>КОЭФФИЦИЕНТЫ: FFA</b></color>

- Сервер прогоняет гонку всех игроков к целевому счёту лобби и считает истинный шанс твоего выбора добежать первым. Твой множитель - половина честной цены; вторую половину держит дом.
- Полы: 2.0x в лобби от 5, 1.4x при 3-4 игроках. Для тяжёлых фаворитов пол уступает 0.95, делённому на их шанс победы, - гарантированно прибыльной ставки существовать не может.
- Потолок: 5.0x или половина размера лобби, если она меньше, и он сжимается при неопределённых рейтингах.
- Игрок без игр FFA ценится по его рейтингу 1v1 с полной неопределённостью.

<color=#FFD94D><b>КОГДА СТАВКИ ОТКРЫВАЮТСЯ И ЗАКРЫВАЮТСЯ</b></color>

Отсечка - набранные очки, никогда не часы:

- <color=#7FD4FF>1v1 и 2v2</color> - открыты с момента существования серии. Закрыты после 2 суммарных очков в игре 1 или в момент, когда решена любая игра серии. Турнирные серии остаются в списке через всё многодневное ожидание, пока пара реально не сыграет.
- <color=#7FD4FF>FFA</color> - каждая ставка целится в СЛЕДУЮЩУЮ игру лобби. Окно закрывается, когда поле набирает 2 очка в этой игре (1 очко, если цель лобби 3 и ниже). Лобби показывается, только пока следующая игра правдоподобна: до 15 минут при сборке без игр и до 30 минут после последней записанной игры. <color=#FF6666>Казуальные лобби не ставятся никогда.</color> Ушедшие участники - не годные цели.
- <color=#7FD4FF>Ставки на этапе лобби</color> - хостовые лобби 2v2 и FFA принимают пари ещё во время ЗАПОЛНЕНИЯ. Коэффициенты пока не даются; на Старте ставка оценивается по финальному полю и становится обычной - при условии, что твоя цель ещё там и обычные проверки прошли. Всё остальное (цель ушла, коэффициент слишком низкий, лобби не стартовало за 6 часов) возвращает ставку.
- В 1v2 ставок нет вовсе.

<color=#FFD94D><b>ВЫПЛАТЫ И НАЛОГ БОЙЦА</b></color>

- Выигрышная выплата включает возврат ставки. 1v1 и 2v2 платят «ставка x коэффициент» с округлением до ближайшего золота; FFA округляет ВНИЗ.
- Если сохранённый коэффициент твоей выигравшей ставки был 1.50x и ниже, 20% ПРИБЫЛИ уходит бойцу или команде, за которых ты ставил, - быть достойным ставок платит и им. Потенциальная выплата, показанная при размещении, этот налог уже включает.

<color=#FFD94D><b>ВОЗВРАТЫ И ГДЕ ВСЁ ЭТО ВИДНО</b></color>

Возврат отдаёт ровно твою ставку:

- 1v1: не турнирная серия без единой отправленной игры за первые 30 минут бросается и возвращает свои ставки. Серия, зависшая на 60 минут посреди, тоже возвращает ставки, а сама остаётся возобновимой - <color=#FF6666>возвращённая ставка остаётся возвращённой, даже если ту серию позже доиграют.</color>
- 2v2: возврат только при отмене серии. Серии, приостановленные отключением, ждут решения админа, прежде чем что-либо рассчитается.
- FFA: возврат только за игру, так и не давшую записанного результата. Сыгранные игры всегда рассчитываются как выигрыш или проигрыш.
- На крошечных ставках ВЫИГРЫШ может заплатить ровно твою ставку (1g при 1.10x платит 1g). Это всё равно выигрыш: показывается сохранённое состояние каждой ставки - открыта, выиграна, проиграна или возвращена, - а не арифметика.
- Полная история твоих ставок по всем режимам - реестр ставок в меню F5. Живые игры для ставок перечислены в игре и зеркалятся в Discord-канале живых ставок и его командах.$s256$)
  , ('c5596757a88ea76b', 'sv', 'a5a0320e13168f43cecad4cfc1ddee6c594f7202', $s256$Guldvadslagning körs på pågående 1v1-, 2v2- och FFA-matcher. Den här sidan täcker vem som får satsa, hur oddsen prissätts, exakt när fönster öppnas och stängs, och vad som händer med din insats.

<color=#FFD94D><b>VEM FÅR SATSA</b></color>

- Varje registrerad spelare, med insatser på 1 till 2000 guld per vad. Insatsen dras i samma stund som vadet läggs.
- Du kan inte satsa på en match eller lobby du själv spelar i, och avstängda spelare kan inte satsa.
- <color=#7FE87F>Åskådare KAN satsa.</color> Det är säkert per design: fönstren nedan stängs på tidiga poäng, så att titta på en match ger dig aldrig ett vad på ett resultat som redan är avgjort.
- Ett vad per serie i 1v1 och 2v2; ett vad per match i FFA.
- Om någon deltagare kör en modd äldre än 1.38.1 vägras vad på den matchen. Äldre klienter kan inte rapportera live-poäng, så poängbrytpunkten skulle aldrig kunna slå till - <color=#FF6666>systemet stänger hellre än lämnar ett fönster öppet.</color>
- Ett länkat Discord-konto kan lägga samma vad genom bottens kommandon.

<color=#FFD94D><b>ODDS: 1v1 OCH 2v2</b></color>

- Din multiplikator är 1 delat med din sidas vinstchans, beräknad från båda sidors rating OCH deras RD (se <color=#7FD4FF>Rating (Glicko-2)</color>). Golv: 1.01x.
- Osäkerhet sätter tak på priset. Med båda sidor etablerade (RD 100 eller lägre) kan multiplikatorn nå 3.0x; taket glider ner mot 1.0x när den högre RD:n stiger mot 300. Ett färskt konto på RD 350 får sitt tak under acceptansgränsen 1.10x - <color=#FF6666>en okänd går helt enkelt inte att satsa på, så en smurf kan inte odlas för guld.</color>
- En sida tar bara emot vad vid 1.10x eller bättre; under det är den låst.
- 2v2 prissätts på parets snittrating. En spelares egen 2v2-rating räknas när de har 10 avslutade serier; innan dess står 1v1-ratingen in.

<color=#FFD94D><b>ODDS: FFA</b></color>

- Servern kör varje spelare i kapp mot lobbyns poängmål och beräknar din kandidats verkliga chans att nå det först. Din multiplikator är halva det rättvisa priset - huset behåller andra halvan.
- Golv: 2.0x i lobbyer med 5 eller fler, 1.4x vid 3-4 spelare. För tunga favoriter ger golvet vika för 0.95 delat med deras vinstchans, så ett garanterat vinstvad kan inte existera.
- Tak: 5.0x, eller halva lobbystorleken om den är lägre, och det krymper när ratingarna är osäkra.
- En spelare utan FFA-matcher ännu prissätts på sin 1v1-rating med full osäkerhet.

<color=#FFD94D><b>NÄR VAD ÖPPNAS OCH STÄNGS</b></color>

Brytpunkten är gjorda poäng, aldrig en klocka:

- <color=#7FD4FF>1v1 och 2v2</color> - öppna från det ögonblick serien finns. Stängda när 2 totala poäng gjorts i match 1, eller i samma stund någon match i serien avgörs. Turneringsserier står listade genom hela flerdagarsväntan innan paret faktiskt spelar.
- <color=#7FD4FF>FFA</color> - varje vad gäller lobbyns NÄSTA match. Fönstret stängs när fältet gör 2 poäng i den matchen (1 poäng om lobbyns poängmål är 3 eller lägre). En lobby listas bara medan en nästa match är rimlig: upp till 15 minuter under uppsamling utan matcher ännu, och upp till 30 minuter efter dess senast registrerade match. <color=#FF6666>Casual-lobbyer går aldrig att satsa på.</color> Medlemmar som lämnat är inte giltiga mål.
- <color=#7FD4FF>Vad i lobbyfasen</color> - hostade 2v2- och FFA-lobbyer tar emot insatser medan de fortfarande FYLLS. Inga odds anges ännu; vid Start prissätts vadet från det slutliga fältet och blir ett normalt vad - förutsatt att ditt mål är kvar och de vanliga kontrollerna passerar. Allt annat (målet lämnade, för låga odds, lobbyn startar aldrig inom 6 timmar) återbetalar insatsen.
- 1v2 har ingen vadslagning alls.

<color=#FFD94D><b>UTBETALNINGAR OCH FIGHTERSKATTEN</b></color>

- En vinnande utbetalning inkluderar din insats tillbaka. 1v1 och 2v2 betalar insats x odds avrundat till närmaste guld; FFA avrundar NEDÅT.
- Om ditt vinnande vads lagrade odds var 1.50x eller lägre går 20% av VINSTEN till fightern eller laget du höll på - att vara värd att satsa på betalar dem också. Den möjliga utbetalning som visas när du lägger vadet inkluderar redan den skatten.

<color=#FFD94D><b>ÅTERBETALNINGAR, OCH VAR DU SER ALLT</b></color>

En återbetalning ger tillbaka exakt din insats:

- 1v1: en icke-turneringsserie utan rapporterad match under sina första 30 minuter överges och återbetalar sina vad. En serie som stått stilla 60 minuter mitt i återbetalar också sina vad, medan serien i sig förblir återupptagbar - <color=#FF6666>ett återbetalat vad förblir återbetalat även om den serien spelas klart senare.</color>
- 2v2: återbetalning bara när en serie annulleras. Disconnect-pausade serier väntar på adminbeslutet innan något avgörs.
- FFA: återbetalning bara för en match som aldrig gav ett registrerat resultat. Spelade matcher avgörs alltid som vunna eller förlorade.
- Vid pyttesmå insatser kan en VINST betala exakt din insats (1g vid 1.10x betalar 1g). Det är fortfarande en vinst: varje vads lagrade tillstånd - öppet, vunnet, förlorat eller återbetalat - är det som visas, inte aritmetiken.
- Din fulla vadhistorik över alla lägen är vadslagningsliggaren i F5-menyn. Pågående satsningsbara matcher listas i spelet och speglas i Discords livevadskanal och dess vadkommandon.$s256$)
  , ('c5596757a88ea76b', 'uk', 'a5a0320e13168f43cecad4cfc1ddee6c594f7202', $s256$Ставки золотом ідуть на живі ігри 1v1, 2v2 і FFA. Ця сторінка покриває, хто може ставити, як обчислюються коефіцієнти, коли саме вікна відкриваються й закриваються, і що стається з вашою ставкою.

<color=#FFD94D><b>ХТО МОЖЕ СТАВИТИ</b></color>

- Будь-який зареєстрований гравець, від 1 до 2000 золота на ставку. Сума знімається в момент розміщення.
- Не можна ставити на матч чи лобі, в якому граєте ви самі, і не можуть ставити забанені гравці.
- <color=#7FE87F>Глядачі ставити МОЖУТЬ.</color> Це безпечно за задумом: вікна нижче закриваються на ранніх балах, тож перегляд гри ніколи не дасть ставку на вже вирішений результат.
- Одна ставка на серію в 1v1 і 2v2; одна ставка на гру в FFA.
- Якщо будь-який учасник грає модом, старішим за 1.38.1, ставки на ту гру відмовляються. Старші клієнти не вміють звітувати живі очки, тож відсічка за балами ніколи не могла б спрацювати - <color=#FF6666>система відмовляє в закритий бік, замість лишити вікно відчиненим.</color>
- Прив’язаний акаунт Discord може розміщувати ті самі ставки через команди бота.

<color=#FFD94D><b>КОЕФІЦІЄНТИ: 1v1 І 2v2</b></color>

- Ваш множник - одиниця, поділена на шанс перемоги вашої сторони, обчислений з рейтингів обох сторін ТА їхніх RD (див. <color=#7FD4FF>Рейтинги (Glicko-2)</color>). Мінімум: 1.01x.
- Невизначеність обмежує ціну. З обома усталеними сторонами (RD 100 або нижче) множник може сягати 3.0x; стеля з’їжджає до 1.0x, коли вищий RD росте до 300. Свіжий акаунт на RD 350 має стелю нижче прохідних 1.10x - <color=#FF6666>на невідомого просто не можна поставити, тож смурфа не нафармиш на золото.</color>
- Сторона приймає ставки лише на 1.10x чи краще; нижче вона замкнена.
- 2v2 оцінюється від середнього рейтингу пари. Власний рейтинг 2v2 гравця рахується, щойно в нього 10 завершених серій; до того замість нього стоїть 1v1.

<color=#FFD94D><b>КОЕФІЦІЄНТИ: FFA</b></color>

- Сервер проганяє перегони кожного гравця до цілі рахунку лобі й обчислює справжній шанс вашого вибору забанкувати її першим. Ваш множник - половина чесної ціни; другу половину лишає собі дім.
- Мінімуми: 2.0x у лобі на 5 і більше, 1.4x на 3-4 гравцях. Для важких фаворитів мінімум поступається 0.95, поділеним на їхній шанс перемоги, тож ставки з гарантованим прибутком існувати не може.
- Стеля: 5.0x, або половина розміру лобі, якщо вона нижча, і вона стискається, коли рейтинги невизначені.
- Гравець ще без ігор FFA оцінюється від рейтингу 1v1 із повною невизначеністю.

<color=#FFD94D><b>КОЛИ СТАВКИ ВІДКРИВАЮТЬСЯ І ЗАКРИВАЮТЬСЯ</b></color>

Відсічка - набрані очки, ніколи не годинник:

- <color=#7FD4FF>1v1 і 2v2</color> - відкриті з моменту, коли існує серія. Закриті, щойно у грі 1 набрано 2 сумарні очки, або в мить, коли вирішено будь-яку гру серії. Турнірні серії лишаються в списку крізь усе багатоденне очікування, поки пара реально зіграє.
- <color=#7FD4FF>FFA</color> - кожна ставка цілить у НАСТУПНУ гру лобі. Вікно закривається, коли поле набирає 2 очки в тій грі (1 очко, якщо ціль рахунку лобі - 3 чи нижче). Лобі в списку, лише поки наступна гра правдоподібна: до 15 хвилин під час збирання без ігор і до 30 хвилин після останньої записаної гри. <color=#FF6666>Звичайні лобі не ставні ніколи.</color> Учасники, що вийшли, не є валідними цілями.
- <color=#7FD4FF>Ставки фази лобі</color> - хостовані лобі 2v2 і FFA приймають ставки, ще ПОКИ ЗБИРАЮТЬСЯ. Коефіцієнти поки не оголошуються; на Старті ставка оцінюється від фінального складу і стає звичайною - за умови, що ваша ціль ще там і звичні перевірки проходять. Усе інше (ціль пішла, коефіцієнт занизький, лобі не стартувало за 6 годин) повертає суму.
- В 1v2 ставок немає взагалі.

<color=#FFD94D><b>ВИПЛАТИ І ПОДАТОК БІЙЦЯ</b></color>

- Виграшна виплата включає повернення вашої суми. 1v1 і 2v2 платять суму x коефіцієнт, округлено до найближчого золота; FFA округлює ВНИЗ.
- Якщо збережений коефіцієнт вашої виграшної ставки був 1.50x чи нижче, 20% ПРИБУТКУ іде бійцеві чи команді, на яких ви ставили, - бути вартим ставки платить і їм. Потенційна виплата, показана при розміщенні, цей податок уже враховує.

<color=#FFD94D><b>ПОВЕРНЕННЯ, І ДЕ ЦЕ ВСЕ ВИДНО</b></color>

Повернення віддає рівно вашу суму:

- 1v1: нетурнірна серія без жодної звітованої гри за перші 30 хвилин закидається і повертає свої ставки. Серія, застигла на 60 хвилин посередині, теж повертає ставки, а сама лишається відновлюваною - <color=#FF6666>повернена ставка лишається поверненою, навіть якщо ту серію пізніше дограють.</color>
- 2v2: повернення лише тоді, коли серію скасовано. Серії на паузі через дисконект чекають рішення адміна, перш ніж щось врегулюється.
- FFA: повернення лише за гру, що так і не дала записаного результату. Зіграні ігри завжди врегульовуються як виграні або програні.
- На крихітних сумах ВИГРАШ може заплатити рівно вашу суму (1g на 1.10x платить 1g). Це все одно виграш: показується збережений стан кожної ставки - відкрита, виграна, програна чи повернена, - а не арифметика.
- Повна історія ваших ставок в усіх режимах - у журналі ставок меню F5. Живі ставні ігри перелічені в грі та віддзеркалені в Discord-каналі живих ставок і його командах ставок.$s256$)
  , ('c62b982567217472', 'es', '69950fdaeb7cbb81edfbeb8d1a8521dbf0cf3f8d', $s256$Ranked 1v1$s256$)
  , ('c62b982567217472', 'ru', '69950fdaeb7cbb81edfbeb8d1a8521dbf0cf3f8d', $s256$Рейтинговый 1v1$s256$)
  , ('c62b982567217472', 'sv', '69950fdaeb7cbb81edfbeb8d1a8521dbf0cf3f8d', $s256$Ranked 1v1$s256$)
  , ('c62b982567217472', 'uk', '69950fdaeb7cbb81edfbeb8d1a8521dbf0cf3f8d', $s256$Ranked 1v1$s256$)
  , ('c64eb8b40ee8fec4', 'es', '4e66bcda284b43d3d5f66c282f86cea9fe749319', $s256$Sobre esta biblioteca$s256$)
  , ('c64eb8b40ee8fec4', 'ru', '4e66bcda284b43d3d5f66c282f86cea9fe749319', $s256$Об этой библиотеке$s256$)
  , ('c64eb8b40ee8fec4', 'sv', '4e66bcda284b43d3d5f66c282f86cea9fe749319', $s256$Om det här biblioteket$s256$)
  , ('c64eb8b40ee8fec4', 'uk', '4e66bcda284b43d3d5f66c282f86cea9fe749319', $s256$Про цю бібліотеку$s256$)
  , ('c84c43c265080ec2', 'es', 'dfe626546b634d9bfe3f685b9e583517f207bb03', $s256$Los cosméticos viven en la pestaña Tienda de F5 y se compran con el oro que ganas jugando. Esta página cubre cada clase, cómo se equipa cada una, cómo funcionan las tiradas y el stock, y de dónde sale el arte.

<color=#FFD94D><b>QUÉ HACE CADA CLASE</b></color>

<color=#7FD4FF>Títulos</color> - la etiqueta junto a tu nombre en las superficies del mod (ver <color=#7FD4FF>Títulos</color>).
<color=#7FD4FF>Estelas</color> - una estela de color tras tu cuerpo en las partidas. La longitud escala con el precio: las de 3,000 de oro son cortas, las de 5,000 medias, las de 10,000 largas.
<color=#7FD4FF>Skins de mapa</color> - recolorean el mapa entero y el fondo. Equipa cuantas quieras y cíclalas en plena partida con Shift izquierdo. El catálogo tiene recolores al estilo de los seis artes vanilla, más de treinta presets originales incluido el pack nocturno, y tres skins premium con destellos: Gilded, Platinum y Aurora. <color=#7FE87F>Las skins de mapa son solo tuyas</color> - nunca se envían a otros jugadores, así que cada uno ve su propia elección.
<color=#7FD4FF>Estilos de nombre</color> - estilo acumulable sobre tu nombre visible. El formato (negrita, cursiva, subrayado, tachado, flotante) se acumula libremente; brillo, tamaño, transformación y tipografía admiten uno cada uno, y los efectos de color (sólidos, neones, arcoíris, degradados por letra) comparten un hueco.
<color=#7FD4FF>Colores de jugador</color> - sustituyen tu naranja o azul de equipo por un color propio, y se vuelven tu identidad de equipo en pantallas con mod (ver <color=#7FD4FF>Colores de equipo y cuerpo</color>).
<color=#7FD4FF>Colores de cursor</color> - recolorean tu cursor. La FORMA del cursor (por defecto, flecha, punto, mira, círculo) es una preferencia gratis. Nadie más ve nunca tu cursor.
<color=#7FD4FF>Efectos de jugador</color> - un aura de partículas que sigue a tu cuerpo en las partidas.
<color=#7FD4FF>Caras</color> - ojos, bocas y accesorios personalizados que se insertan en el editor de personaje propio de ROUNDS junto a las piezas vanilla, y se dibujan allá donde se dibuje una cara. Algunos son animados; el ajuste Cosméticos animados los fija en un fotograma quieto si lo prefieres.
<color=#7FD4FF>Ocultar oro</color> - un interruptor de utilidad que enmascara tu oro en las superficies de clasificación.

<color=#FFD94D><b>EQUIPAR</b></color>

- De uno en uno: títulos, estelas, colores de jugador, colores de cursor y efectos de jugador usan <color=#7FD4FF>Activar</color> / <color=#7FD4FF>Quitar</color>.
- Multiequipar: los estilos de nombre y las skins de mapa usan <color=#7FD4FF>Equipar</color> / <color=#7FD4FF>Quitar</color> - acumula tus estilos de nombre, mantén una rotación de skins.
- Ocultar oro es un interruptor de sí/no.

<color=#FFD94D><b>QUIÉN VE QUÉ</b></color>

- <color=#7FE87F>El único cosmético que un jugador SIN el mod puede llegar a ver es el estilo del nombre</color> - los nombres con estilo viajan en el mismo campo de nombre que vanilla ya dibuja, y meter estilo en un nombre siempre ha sido posible en ROUNDS vanilla. Incluso ahí, el brillo y la tipografía son extras del mod que una pantalla vanilla no puede mostrar.
- Todo lo demás - estelas, colores de jugador, auras, caras, skins de mapa - se dibuja solo para jugadores con mod. Un rival vanilla ve tu color de cuerpo por defecto, sin estela, sin aura, y un hueco vacío donde iría una pieza de cara personalizada. <color=#8A8A93>El juego salta la pieza desconocida limpiamente: sin crash, sin sustituir nada.</color>
- Los espectadores con mod pueden desactivar individualmente en Ajustes las estelas, colores de jugador y cosméticos animados de otros.

<color=#FFD94D><b>STOCK, TIRADAS Y ADELANTOS</b></color>

- La tienda lo lista todo por precio y muestra qué posees, el artista de cada objeto y el stock.
- Los objetos de la comunidad pueden ser limitados: una tirada muestra N de M restantes y se apaga al agotarse.
- Un objeto puede existir antes de abrirse su venta - figura como no a la venta hasta que el artista la abre, y las novedades se adelantan primero en el panel de cosméticos nuevos de la pestaña Inicio. <color=#FF6666>Ver un objeto en Inicio no significa que ya puedas comprarlo.</color>
- No puedes comprar un objeto dos veces, y una compra que no puedes pagar se rechaza - sin deudas, sin compras parciales.

<color=#FFD94D><b>EL ESTUDIO DE ARTISTAS</b></color>

Los artistas de la comunidad hacen buena parte del catálogo. El circuito:

- Un artista (un rol otorgado en el juego) envía arte desde la pestaña Artista: un PNG o fotogramas animados, posicionados sobre una vista previa en vivo sobre el cuerpo con hueco, escala y desplazamiento.
- El envío pasa a revisión. La aprobación sola no lo pone a la venta: el arte tiene que salir dentro de una versión del mod primero, porque los cosméticos van empaquetados en el mod para que el juego de cada jugador pueda dibujarlos.
- Una vez publicado, el artista abre la venta y controla el precio, el tope de stock y quién puede comprar - un artista puede bloquear a jugadores concretos para que no compren sus objetos.
- El artista gana <color=#7FE87F>una regalía del 30%</color> (redondeada hacia abajo a Oro entero) cuando otro jugador compra su objeto. Sin regalía en los regalos.

<color=#FFD94D><b>REGALOS</b></color>

Solo los artistas pueden regalar, y solo sus propios objetos: una copia gratis a cualquier jugador que haya usado el mod, incluso antes de abrirse la venta. Los regalos consumen stock igualmente en una tirada limitada. No hay regalos entre jugadores, ni forma de enviar oro a otro jugador.$s256$)
  , ('c84c43c265080ec2', 'ru', 'dfe626546b634d9bfe3f685b9e583517f207bb03', $s256$Косметика живёт на вкладке Магазин (F5) и покупается за золото, которое ты зарабатываешь игрой. Эта страница покрывает каждый вид, как он надевается, как работают дропы и сток и откуда берётся арт.

<color=#FFD94D><b>ЧТО ДЕЛАЕТ КАЖДЫЙ ВИД</b></color>

<color=#7FD4FF>Титулы</color> - подпись рядом с твоим именем на поверхностях мода (см. <color=#7FD4FF>Титулы</color>).
<color=#7FD4FF>Шлейфы</color> - цветной след за твоим телом в матчах. Длина растёт с ценой: шлейфы за 3,000 золота короткие, за 5,000 средние, за 10,000 длинные.
<color=#7FD4FF>Скины карт</color> - перекрашивают всю карту и фон. Надевай сколько хочешь и листай их посреди игры левым Shift. В каталоге перекраски в духе шести ванильных артов, больше тридцати оригинальных пресетов, включая ночной пак, и три премиальных скина с блёстками: Gilded, Platinum и Aurora. <color=#7FE87F>Скины карт - только твои</color>: другим игрокам они не отправляются никогда, каждый видит свой выбор.
<color=#7FD4FF>Стиль имени</color> - стакуемый стиль на твоём отображаемом имени. Форматирование (жирный, курсив, подчёркивание, зачёркивание, парение) стакается свободно; свечение, размер, трансформация регистра и шрифт - по одному, а цветовые эффекты (сплошные, неон, радуга, побуквенные градиенты) делят один слот.
<color=#7FD4FF>Цвета игрока</color> - заменяют твой командный оранжевый или синий собственным цветом и становятся твоей командной принадлежностью на модовых экранах (см. <color=#7FD4FF>Цвета команд и тел</color>).
<color=#7FD4FF>Цвета курсора</color> - перекрашивают курсор мыши. ФОРМА курсора (стандарт, стрелка, точка, прицел, круг) - бесплатная настройка. Твой курсор не видит никто и никогда.
<color=#7FD4FF>Эффекты игрока</color> - партикловая аура, следующая за твоим телом в матчах.
<color=#7FD4FF>Лица</color> - кастомные глаза, рты и аксессуары, которые встают в родной редактор персонажа ROUNDS рядом с ванильными частями и рендерятся везде, где рендерится лицо. Часть анимированные; настройка «Анимация косметики» при желании закрепляет их на статичном кадре.
<color=#7FD4FF>Скрыть золото</color> - утилитарный переключатель, маскирующий твоё золото на поверхностях таблиц.

<color=#FFD94D><b>НАДЕВАНИЕ</b></color>

- По одному: титулы, шлейфы, цвета игрока, цвета курсора и эффекты игрока используют <color=#7FD4FF>Включить</color> / <color=#7FD4FF>Снять</color>.
- Мульти-надевание: стили имени и скины карт используют <color=#7FD4FF>Надеть</color> / <color=#7FD4FF>Убрать</color> - стакай стили имени, держи ротацию скинов.
- Скрыть золото - переключатель вкл/выкл.

<color=#FFD94D><b>КТО ЧТО ВИДИТ</b></color>

- <color=#7FE87F>Единственная косметика, которую игрок БЕЗ мода вообще может увидеть, - стиль имени</color>: стилизованные имена едут в том же поле имени, которое ваниль и так рендерит, а класть стиль в имя в ванильном ROUNDS можно было всегда. Даже там свечение и шрифт - модовые надстройки, которые ванильный экран показать не может.
- Всё остальное - шлейфы, цвета игрока, ауры, лица, скины карт - рендерится только модовым игрокам. Ванильный соперник видит твой стандартный цвет тела, без шлейфа, без ауры и пустой слот на месте кастомной части лица. <color=#8A8A93>Игра чисто пропускает неизвестную часть: без краша, без подмены.</color>
- Модовые зрители могут по отдельности выключить чужие шлейфы, цвета игрока и анимированную косметику в Настройках.

<color=#FFD94D><b>СТОК, ДРОПЫ И ТИЗЕРЫ</b></color>

- Магазин перечисляет всё по цене и показывает, чем ты владеешь, художника каждого предмета и сток.
- Предметы сообщества могут быть ограниченными: дроп показывает «осталось N из M» и сереет после распродажи.
- Предмет может существовать до открытия продаж - он показывается как «не продаётся», пока художник не откроет продажи, а совсем новые прибытия сперва тизерятся в панели новинок на Главной. <color=#FF6666>Видеть предмет на Главной не значит, что его уже можно купить.</color>
- Купить предмет дважды нельзя, а покупка не по карману отклоняется - без долгов и частичных покупок.

<color=#FFD94D><b>СТУДИЯ ХУДОЖНИКА</b></color>

Художники сообщества делают большую долю каталога. Конвейер:

- Художник (роль, выдаваемая в игре) отправляет арт со вкладки Художник: PNG или анимированные кадры, размещённые на живом превью на теле, со слотом, масштабом и смещением.
- Заявка уходит на проверку. Одно одобрение не выставляет её на продажу: арт сперва должен уехать внутри релиза мода, потому что косметика вшивается в мод, чтобы игра каждого игрока могла её отрендерить.
- После выхода художник открывает продажи и управляет ценой, потолком стока и тем, кому можно покупать, - художник может закрыть покупку своих предметов отдельным игрокам.
- Художник зарабатывает <color=#7FE87F>роялти 30%</color> (округлённые вниз до целого золота), когда его предмет покупает другой игрок. С подарков роялти нет.

<color=#FFD94D><b>ПОДАРКИ</b></color>

Дарить могут только художники и только свои предметы: бесплатная копия любому игроку, который пользовался модом, в том числе до открытия продаж. Подарки всё равно тратят сток ограниченного дропа. Дарения между игроками нет, и способа передать золото другому игроку нет.$s256$)
  , ('c84c43c265080ec2', 'sv', 'dfe626546b634d9bfe3f685b9e583517f207bb03', $s256$Kosmetik bor på F5-fliken Butik och köps med guldet du tjänar genom att spela. Den här sidan täcker varje sort, hur var och en utrustas, hur släpp och lager fungerar, och varifrån konsten kommer.

<color=#FFD94D><b>VAD VARJE SORT GÖR</b></color>

<color=#7FD4FF>Titlar</color> - etiketten bredvid ditt namn på moddytor (se <color=#7FD4FF>Titlar</color>).
<color=#7FD4FF>Spår</color> - ett färgat spår bakom din kropp i matcher. Längden skalar med priset: spår för 3 000 guld är korta, 5 000 medellånga, 10 000 långa.
<color=#7FD4FF>Kartskins</color> - färgar om hela kartan och bakgrunden. Utrusta hur många du vill och växla mellan dem mitt i matchen med vänster Shift. Katalogen rymmer omfärgningar i stil med de sex vanilla-arterna, över trettio egna förinställningar inklusive nattpaketet, och tre premium-gnistskins: Gilded, Platinum och Aurora. <color=#7FE87F>Kartskins är dina ensamma</color> - de skickas aldrig till andra spelare, så varje spelare ser sitt eget val.
<color=#7FD4FF>Namnstil</color> - staplingsbar stil på ditt visningsnamn. Formatering (fet, kursiv, understruken, genomstruken, svävande) staplas fritt; glöd, storlek, teckentransform och typsnitt tillåter en var, och färgeffekterna (solida, neon, regnbåge, gradient per bokstav) delar en plats.
<color=#7FD4FF>Spelarfärger</color> - ersätter ditt lags orange eller blå med en egen färg, och blir din lagidentitet på moddade skärmar (se <color=#7FD4FF>Lag- & kroppsfärger</color>).
<color=#7FD4FF>Pekarfärger</color> - färgar om din muspekare. Pekarens FORM (standard, pil, prick, hårkors, cirkel) är en gratis preferens. Ingen annan ser någonsin din pekare.
<color=#7FD4FF>Spelareffekter</color> - en partikelaura som följer din kropp i matcher.
<color=#7FD4FF>Ansikten</color> - egna ögon, munnar och accessoarer som tar plats i ROUNDS egen karaktärseditor bredvid vanilla-delarna, och renderas överallt där ett ansikte renderas. Vissa är animerade; inställningen Animerad kosmetik låser dem till en stillbild om du föredrar det.
<color=#7FD4FF>Dölj guld</color> - en nyttoinställning som maskerar ditt guld på topplistytor.

<color=#FFD94D><b>ATT UTRUSTA</b></color>

- En i taget: titlar, spår, spelarfärger, pekarfärger och spelareffekter använder <color=#7FD4FF>Aktivera</color> / <color=#7FD4FF>Ta av</color>.
- Flera samtidigt: namnstilar och kartskins använder <color=#7FD4FF>Utrusta</color> / <color=#7FD4FF>Ta bort</color> - stapla dina namnstilar, håll en rotation av skins.
- Dölj guld är en på/av-inställning.

<color=#FFD94D><b>VEM SER VAD</b></color>

- <color=#7FE87F>Den enda kosmetik en spelare UTAN modden någonsin kan se är namnstil</color> - stiliserade namn åker med samma namnfält som vanilla redan renderar, och att lägga stil i ett namn har alltid varit möjligt i vanilla-ROUNDS. Till och med där är glöd och typsnitt modd-extra som en vanilla-skärm inte kan visa.
- Allt annat - spår, spelarfärger, auror, ansikten, kartskins - renderas bara för moddade spelare. En vanilla-motståndare ser din standardkroppsfärg, inget spår, ingen aura och en tom plats där en egen ansiktsdel skulle sitta. <color=#8A8A93>Spelet hoppar rent över den okända delen: ingen krasch, inget ersatt.</color>
- Moddade betraktare kan individuellt stänga av andra spelares spår, spelarfärger och animerade kosmetik i Inställningar.

<color=#FFD94D><b>LAGER, SLÄPP OCH TEASERS</b></color>

- Butiken listar allt efter pris och visar vad du äger, varje artikels konstnär och lagret.
- Communityartiklar kan vara begränsade: ett släpp visar N av M kvar och gråas ut när det är slutsålt.
- En artikel kan finnas innan dess försäljning öppnat - den visas som ej till salu tills konstnären öppnar försäljningen, och helt nya ankomster teasas först på Hem-flikens panel för nyaste kosmetik. <color=#FF6666>Att se en artikel på Hem betyder inte att du kan köpa den än.</color>
- Du kan inte köpa en artikel två gånger, och ett köp du inte har råd med vägras - ingen skuld, inga delköp.

<color=#FFD94D><b>KONSTNÄRSSTUDION</b></color>

Communitykonstnärer står för en stor del av katalogen. Pipelinen:

- En konstnär (en roll som ges i spelet) skickar in konst från Konstnärsfliken: en PNG eller animerade bildrutor, positionerade på en live-förhandsvisning på kroppen med plats, skala och offset.
- Bidraget går till granskning. Godkännande ensamt lägger inte ut det till försäljning: konsten måste först skeppas inuti en moddrelease, eftersom kosmetik buntas in i modden så att varje spelares spel kan rendera den.
- När den skeppats öppnar konstnären försäljningen och styr priset, lagertaket och vem som får köpa - en konstnär kan blockera specifika spelare från att köpa sina artiklar.
- Konstnären tjänar <color=#7FE87F>30% i royalty</color> (avrundad nedåt till helt guld) när en annan spelare köper deras artikel. Ingen royalty på gåvor.

<color=#FFD94D><b>GÅVOR</b></color>

Bara konstnärer kan ge gåvor, och bara sina egna artiklar: en gratis kopia till valfri spelare som använt modden, även innan försäljningen öppnat. Gåvor förbrukar ändå lager i ett begränsat släpp. Det finns ingen gåvogivning spelare-till-spelare, och inget sätt att skicka guld till en annan spelare.$s256$)
  , ('c84c43c265080ec2', 'uk', 'dfe626546b634d9bfe3f685b9e583517f207bb03', $s256$Косметика живе на вкладці Магазин у F5 і купується за золото, зароблене грою. Ця сторінка покриває кожен вид, як кожен вдягається, як працюють дропи й запас, і звідки береться арт.

<color=#FFD94D><b>ЩО РОБИТЬ КОЖЕН ВИД</b></color>

<color=#7FD4FF>Титули</color> - підпис біля вашого імені на поверхнях мода (див. <color=#7FD4FF>Титули</color>).
<color=#7FD4FF>Шлейфи</color> - кольоровий слід за вашим тілом у матчах. Довжина масштабується з ціною: шлейфи за 3,000 золота короткі, 5,000 - середні, 10,000 - довгі.
<color=#7FD4FF>Скіни мап</color> - перефарбовують усю мапу і тло. Вдягайте скільки завгодно і циклюйте їх посеред гри лівим Shift. Каталог тримає перефарбування в стилі шести ванільних артів, понад тридцять оригінальних пресетів, включно з нічним паком, і три преміальні блискучі скіни: Gilded, Platinum і Aurora. <color=#7FE87F>Скіни мап - лише ваші</color>: вони ніколи не надсилаються іншим гравцям, тож кожен бачить власний вибір.
<color=#7FD4FF>Стилізація імені</color> - стековані стилі на вашому видимому імені. Форматування (жирний, курсив, підкреслення, закреслення, підвис) стакається вільно; світіння, розмір, трансформація шрифту і гарнітура - по одному кожного, а колірні ефекти (суцільні, неони, райдуга, політерні градієнти) ділять один слот.
<color=#7FD4FF>Кольори гравця</color> - замінюють ваші командні помаранчевий чи синій на власний колір і стають вашою командною ідентичністю на екранах з модом (див. <color=#7FD4FF>Кольори команд і тіла</color>).
<color=#7FD4FF>Кольори курсора</color> - перефарбовують ваш курсор миші. ФОРМА курсора (типова, стрілка, крапка, приціл, коло) - безкоштовне вподобання. Ваш курсор не бачить більше ніхто й ніколи.
<color=#7FD4FF>Ефекти гравця</color> - аура частинок, що йде за вашим тілом у матчах.
<color=#7FD4FF>Обличчя</color> - кастомні очі, роти й аксесуари, що вставляються у власний редактор персонажа ROUNDS поруч із ванільними частинами і рендеряться скрізь, де рендериться обличчя. Деякі анімовані; налаштування «Анімована косметика» за бажанням пришпилює їх до нерухомого кадру.
<color=#7FD4FF>Приховати золото</color> - службовий перемикач, що маскує ваше золото на поверхнях таблиць лідерів.

<color=#FFD94D><b>ЯК ВДЯГАТИ</b></color>

- По одному: титули, шлейфи, кольори гравця, кольори курсора та ефекти гравця використовують <color=#7FD4FF>Активувати</color> / <color=#7FD4FF>Зняти</color>.
- Кілька водночас: стилі імені та скіни мап використовують <color=#7FD4FF>Застосувати</color> / <color=#7FD4FF>Прибрати</color> - стакайте стилі імені, тримайте ротацію скінів.
- Приховати золото - перемикач увімк/вимк.

<color=#FFD94D><b>ХТО ЩО БАЧИТЬ</b></color>

- <color=#7FE87F>Єдина косметика, яку гравець БЕЗ мода може взагалі побачити, - стилізація імені</color>: стилізовані імена їдуть тим самим полем імені, яке ваніль і так рендерить, а вставляти стилі в ім’я в ROUNDS можна було завжди. Та навіть тут світіння і гарнітура - модові додатки, які ванільний екран показати не може.
- Усе решта - шлейфи, кольори гравця, аури, обличчя, скіни мап - рендериться лише гравцям з модом. Ванільний суперник бачить ваш типовий колір тіла, без шлейфа, без аури і порожній слот там, де була б кастомна частина обличчя. <color=#8A8A93>Гра чисто пропускає невідому частину: без краху, без підміни.</color>
- Глядачі з модом можуть особисто вимкнути чужі шлейфи, кольори гравця й анімовану косметику в Налаштуваннях.

<color=#FFD94D><b>ЗАПАС, ДРОПИ І ТИЗЕРИ</b></color>

- Магазин перелічує все за ціною і показує, чим ви володієте, художника кожного предмета і запас.
- Предмети спільноти можуть бути лімітовані: дроп показує «лишилось N з M» і сіріє, коли розпродано.
- Предмет може існувати ще до відкриття продажу - він показується як «не продається», поки художник не відкриє продаж, а новоприбулі спершу тизеряться на панелі найновішої косметики Головної. <color=#FF6666>Бачити предмет на Головній не означає, що його вже можна купити.</color>
- Не можна купити предмет двічі, а купівля, на яку бракує золота, відхиляється - без боргу, без часткових покупок.

<color=#FFD94D><b>СТУДІЯ ХУДОЖНИКА</b></color>

Художники спільноти роблять велику частину каталогу. Конвеєр:

- Художник (роль, що видається в грі) подає арт із вкладки Художник: PNG чи анімовані кадри, розміщені на живому прев’ю на тілі, зі слотом, масштабом і зсувом.
- Подання йде на розгляд. Саме схвалення продажу ще не відкриває: арт спершу мусить вийти всередині релізу мода, бо косметика пакується в мод, щоб гра кожного гравця могла її рендерити.
- Щойно арт вийшов, художник відкриває продаж і керує ціною, стелею запасу і тим, кому можна купувати, - художник може заблокувати окремим гравцям купівлю своїх предметів.
- Художник заробляє <color=#7FE87F>30% роялті</color> (округлено вниз до цілого золота), коли інший гравець купує його предмет. З подарунків роялті немає.

<color=#FFD94D><b>ПОДАРУНКИ</b></color>

Дарувати можуть лише художники, і лише власні предмети: безкоштовна копія будь-якому гравцеві, що користувався модом, включно з часом до відкриття продажу. Подарунки все одно споживають запас лімітованого дропу. Дарування між гравцями немає, і надіслати золото іншому гравцеві не можна.$s256$)
  , ('c8d198d08b2458b4', 'es', '40e583e2c5196cc44e0152a1ec7f0e9003b05c8a', $s256$El bot y los check-ins$s256$)
  , ('c8d198d08b2458b4', 'ru', '40e583e2c5196cc44e0152a1ec7f0e9003b05c8a', $s256$Бот и чек-ины$s256$)
  , ('c8d198d08b2458b4', 'sv', '40e583e2c5196cc44e0152a1ec7f0e9003b05c8a', $s256$Botten & incheckningar$s256$)
  , ('c8d198d08b2458b4', 'uk', '40e583e2c5196cc44e0152a1ec7f0e9003b05c8a', $s256$Бот і чек-іни$s256$)
  , ('c995f8cdd8ce52e7', 'es', '6239d1b9fc40140857855287b71416de29d03380', $s256$Apuestas$s256$)
  , ('c995f8cdd8ce52e7', 'ru', '6239d1b9fc40140857855287b71416de29d03380', $s256$Ставки$s256$)
  , ('c995f8cdd8ce52e7', 'sv', '6239d1b9fc40140857855287b71416de29d03380', $s256$Vadslagning$s256$)
  , ('c995f8cdd8ce52e7', 'uk', '6239d1b9fc40140857855287b71416de29d03380', $s256$Ставки$s256$)
  , ('cb80aaef215f676c', 'es', '10d9adc648f4c2f08f64a863676777cec2bce624', $s256$Tipos de daño y buffs$s256$)
  , ('cb80aaef215f676c', 'ru', '10d9adc648f4c2f08f64a863676777cec2bce624', $s256$Типы урона и баффы$s256$)
  , ('cb80aaef215f676c', 'sv', '10d9adc648f4c2f08f64a863676777cec2bce624', $s256$Skadetyper & buffar$s256$)
  , ('cb80aaef215f676c', 'uk', '10d9adc648f4c2f08f64a863676777cec2bce624', $s256$Типи шкоди та бафи$s256$)
  , ('d1b8be2788734885', 'es', '4f964480316f94e0572347d15d1effbcf33e228a', $s256$Colores de equipo y cuerpo$s256$)
  , ('d1b8be2788734885', 'ru', '4f964480316f94e0572347d15d1effbcf33e228a', $s256$Цвета команд и тел$s256$)
  , ('d1b8be2788734885', 'sv', '4f964480316f94e0572347d15d1effbcf33e228a', $s256$Lag- & kroppsfärger$s256$)
  , ('d1b8be2788734885', 'uk', '4f964480316f94e0572347d15d1effbcf33e228a', $s256$Кольори команд і тіла$s256$)
  , ('d4e55c6cad6429ea', 'es', '1fae01eacc86b66836f084c259bcb7a1700793cb', $s256$Mecánicas del juego$s256$)
  , ('d4e55c6cad6429ea', 'ru', '1fae01eacc86b66836f084c259bcb7a1700793cb', $s256$Механики игры$s256$)
  , ('d4e55c6cad6429ea', 'sv', '1fae01eacc86b66836f084c259bcb7a1700793cb', $s256$Spelmekanik$s256$)
  , ('d4e55c6cad6429ea', 'uk', '1fae01eacc86b66836f084c259bcb7a1700793cb', $s256$Ігрові механіки$s256$)
  , ('edf4af82b6d6ea0e', 'es', '83faee2755ec624629eae20327b5e665067401b3', $s256$Silenciar audio al salir de la ventana: <color=#FF9966>NO</color>$s256$)
  , ('edf4af82b6d6ea0e', 'ru', '83faee2755ec624629eae20327b5e665067401b3', $s256$Глушить звук вне окна: <color=#FF9966>ВЫКЛ</color>$s256$)
  , ('edf4af82b6d6ea0e', 'sv', '83faee2755ec624629eae20327b5e665067401b3', $s256$Tysta ljudet när du byter fönster: <color=#FF9966>AV</color>$s256$)
  , ('edf4af82b6d6ea0e', 'uk', '83faee2755ec624629eae20327b5e665067401b3', $s256$Глушити звук поза вікном: <color=#FF9966>ВИМК</color>$s256$)
  , ('ffd0bcba80bcba7d', 'es', '7092efd0e1c1a7263fce0c81c6c69b2e65a70b3e', $s256$Cada modo ranked te puntúa con Glicko-2: un rating, más una medida de cuán seguro está el sistema de él. Esta página explica qué significan los números, por qué se mueven como se mueven, cuándo actualiza cada modo, y la escalera de rangos completa.

<color=#FFD94D><b>LOS TRES NÚMEROS</b></color>

<color=#7FD4FF>Rating</color> - la estimación de habilidad. Todos empiezan en 1500. No hay suelo ni techo en ningún sitio; tu pico se registra por modo.
<color=#7FD4FF>RD (desviación del rating)</color> - cuán incierta es la estimación. Una cuenta recién creada empieza en 350. La RD encoge cada vez que juegas - cuanto más juegas, más seguro está el sistema.
<color=#7FD4FF>Volatilidad</color> - cuán erráticos han sido tus resultados. Empieza en 0.06 y se ajusta sola según llegan resultados.

El tamaño de un movimiento de rating escala con TU RD. Por eso las cuentas nuevas oscilan fuerte - sus primeros resultados las mueven mucho - mientras que los resultados de un veterano lo mueven poco a poco. Jugar más partidas es lo único que lo asienta.

<color=#FFD94D><b>POR QUÉ GANANCIAS Y PÉRDIDAS NO SON IGUALES</b></color>

Antes de puntuar un resultado, el sistema calcula tu resultado esperado según la brecha de rating. Tu cambio es proporcional a la diferencia entre lo que pasó y lo esperado:

- Vence a un jugador de rating mucho más bajo y ganas casi nada - la victoria era lo esperado. Pierde contra él y pagas caro.
- Vence a uno de rating más alto y te llevas el lado grande del mismo trato.
- La RD del rival también importa: los resultados contra rivales inciertos (RD alta) se amortiguan. Vencer a una cuenta bien establecida mueve tu rating más que vencer a una desconocida recién llegada.

<color=#FFD94D><b>CUÁNDO SE MUEVEN LOS RATINGS</b></color>

Cada modo mantiene su propio rating Glicko totalmente separado. Nada de lo que hagas en un modo mueve jamás el número de otro.

- <color=#7FD4FF>1v1</color> - actualiza cuando la serie se completa (primero a 2 juegos ganados). La serie entera cuenta como UNA observación de victoria o derrota: un 2-0 y un 2-1 mueven tu rating idénticamente.
- <color=#7FD4FF>2v2</color> - actualiza cuando la serie se completa. Se te puntúa contra AMBOS jugadores rivales. Una serie decidida por desconexión aplica ratings completos, igual que una jugada entera.
- <color=#7FD4FF>FFA</color> - actualiza tras cada partida, cuando llega su reporte.
- <color=#7FD4FF>1v2</color> - <color=#FF6666>beta sin rating. Ningún rating se mueve.</color> Las partidas se registran y podrán contar cuando llegue el 1v2 ranked.

Las partidas casual nunca tocan ningún rating.

<color=#FFD94D><b>CÓMO PUNTÚA EL FFA UNA SALA</b></color>

Una partida de 10 jugadores no se trata como 9 duelos separados - eso movería tu rating varias veces más fuerte que una de 3. En su lugar:

- Se te compara contra 4 rivales como mucho: los colocados MÁS CERCA de ti.
- Una comparación extra de 'sorpresa' puede unirse: la mayor brecha de rating de 250 o más que terminó invertida fuera de esas elecciones. Una por partida, hubiera las sorpresas que hubiera.
- Cada comparación puntúa como victoria si quedaste por encima, derrota si por debajo, y <color=#7FE87F>un puesto compartido cuenta como empate</color>.
- Las partidas cortas pesan menos: una a 3 cuenta como media partida, la de por defecto a 5 cuenta entera, y los objetivos más largos nunca cuentan más de una partida.

<color=#FFD94D><b>LA REGLA DE CONFIANZA DEL 2v2</b></color>

Tu rating 2v2 empieza como una conjetura, así que el emparejador no se fía de él de entrada:

- El equilibrado de equipos usa tu rating 2v2 cuando tienes 10 series completadas, O cuando su RD ha convergido a 110 o menos.
- Hasta entonces, lo sustituye tu rating 1v1.
- La columna Avg Mate Elo de la clasificación se fía del rating 2v2 de un compañero tras 5 series completadas; antes usa su rating 1v1, o 1500 si no tiene.

<color=#FFD94D><b>LA ESCALERA DE RANGOS</b></color>

Cinco tiers, cada uno partido en peldaños I a V - V es lo más alto de su tier. El número es el suelo: ocupas un peldaño con ese rating o más.

- <color=#7FD4FF>Gran Maestro</color> - I 2330, II 2400, III 2470, IV 2540, V 2610
- <color=#7FD4FF>Maestro</color> - I 1980, II 2050, III 2120, IV 2190, V 2260
- <color=#7FD4FF>Avanzado</color> - I 1675, II 1725, III 1780, IV 1845, V 1910
- <color=#7FD4FF>Intermedio</color> - I 1500, II 1525, III 1555, IV 1590, V 1630
- <color=#7FD4FF>Principiante</color> - I 0, II 1140, III 1260, IV 1360, V 1440

Llegar a 1980 (Maestro) o 2330 (Gran Maestro) en ranked 1v1 o 2v2 otorga además el logro correspondiente - el rating FFA no los dispara. Los roles de rango de Discord siguen tu rating 1v1, y el título de tienda Rango actual siempre muestra el nombre de tu rango en vivo con el color de su tier. El tier de tu rival también multiplica tus recompensas de partida (ver <color=#7FD4FF>XP, Oro y niveles</color>).$s256$)
  , ('ffd0bcba80bcba7d', 'ru', '7092efd0e1c1a7263fce0c81c6c69b2e65a70b3e', $s256$Каждый рейтинговый режим оценивает тебя Glicko-2: рейтинг плюс мера того, насколько система в нём уверена. Эта страница объясняет, что значат числа, почему они двигаются именно так, когда обновляется каждый режим, и полную лестницу рангов.

<color=#FFD94D><b>ТРИ ЧИСЛА</b></color>

<color=#7FD4FF>Рейтинг</color> - оценка силы. Все начинают с 1500. Ни пола, ни потолка нигде нет; твой пик отслеживается по режимам.
<color=#7FD4FF>RD (отклонение рейтинга)</color> - насколько оценка неопределённа. Новый аккаунт начинает с 350. RD сжимается с каждой игрой - чем больше играешь, тем увереннее система.
<color=#7FD4FF>Волатильность</color> - насколько скачущими были твои результаты. Начинается с 0.06 и подстраивается сама по мере результатов.

Размер движения рейтинга масштабируется с ТВОИМ RD. Поэтому новые аккаунты качает сильно - первые результаты двигают их значительно, - а результаты ветерана двигают его понемногу. Единственное, что это успокаивает, - больше игр.

<color=#FFD94D><b>ПОЧЕМУ ПРИБАВКИ И ПОТЕРИ НЕ РАВНЫ</b></color>

Перед оценкой результата система считает твой ожидаемый результат из разницы рейтингов. Твоё изменение пропорционально разнице между случившимся и ожидаемым:

- Победи игрока много ниже - и не получишь почти ничего: победа ожидалась. Проиграй ему - и заплатишь дорого.
- Победи игрока выше - и возьмёшь большую сторону той же сделки.
- RD соперника тоже важен: результаты против неопределённых (высокий RD) соперников приглушаются. Победа над устоявшимся аккаунтом двигает твой рейтинг сильнее, чем над свежим неизвестным.

<color=#FFD94D><b>КОГДА РЕЙТИНГИ ДВИГАЮТСЯ</b></color>

Каждый режим держит свой полностью отдельный рейтинг Glicko. Ничто, сделанное в одном режиме, никогда не двигает число другого.

- <color=#7FD4FF>1v1</color> - обновляется при завершении серии (первый до 2 выигранных игр). Вся серия считается ОДНИМ наблюдением победы или поражения: 2-0 и 2-1 двигают рейтинг одинаково.
- <color=#7FD4FF>2v2</color> - обновляется при завершении серии. Ты оцениваешься против ОБОИХ игроков соперника. Серия, решённая отключением, применяет полные рейтинги, как и доигранная.
- <color=#7FD4FF>FFA</color> - обновляется после каждой отдельной игры, когда приходит её отчёт.
- <color=#7FD4FF>1v2</color> - <color=#FF6666>бета без рейтинга. Рейтинг не двигается вовсе.</color> Игры записываются и смогут зачесться позже, когда выйдет рейтинговый 1v2.

Казуальные игры не трогают никакой рейтинг никогда.

<color=#FFD94D><b>КАК FFA ОЦЕНИВАЕТ ЛОББИ</b></color>

Игра на 10 не считается девятью отдельными дуэлями - это качало бы твой рейтинг в разы сильнее игры на 3. Вместо этого:

- Тебя сравнивают максимум с 4 соперниками: с теми, чьи места БЛИЖАЙШИЕ к твоему.
- К ним может добавиться одно сравнение-«апсет»: самый большой разрыв рейтинга в 250 с лишним, закончившийся вверх ногами вне этой выборки. Одно на игру, сколько бы апсетов ни случилось.
- Каждое сравнение считается победой, если ты выше по месту, поражением, если ниже, а <color=#7FE87F>разделённое место считается ничьёй</color>.
- Короткие игры весят меньше: до 3 считается половиной игры, стандартная до 5 - целой, а более длинные цели никогда не считаются больше одной игры.

<color=#FFD94D><b>ПРАВИЛО ДОВЕРИЯ 2v2</b></color>

Твой рейтинг 2v2 начинается как догадка, так что матчмейкер не доверяет ему сразу:

- Балансировка команд использует твой рейтинг 2v2, когда у тебя 10 завершённых серий ИЛИ его RD сошёлся к 110 и ниже.
- До тех пор вместо него стоит твой рейтинг 1v1.
- Колонка Avg Mate Elo таблицы лидеров доверяет рейтингу 2v2 тиммейта после 5 завершённых серий; до того берёт его 1v1 или 1500, если рейтинга нет.

<color=#FFD94D><b>ЛЕСТНИЦА РАНГОВ</b></color>

Пять тиров, каждый разбит на ступени от I до V - V вершина своего тира. Число - это пол: ты держишь ступень при рейтинге на нём или выше.

- <color=#7FD4FF>Грандмастер</color> - I 2330, II 2400, III 2470, IV 2540, V 2610
- <color=#7FD4FF>Мастер</color> - I 1980, II 2050, III 2120, IV 2190, V 2260
- <color=#7FD4FF>Продвинутый</color> - I 1675, II 1725, III 1780, IV 1845, V 1910
- <color=#7FD4FF>Средний</color> - I 1500, II 1525, III 1555, IV 1590, V 1630
- <color=#7FD4FF>Новичок</color> - I 0, II 1140, III 1260, IV 1360, V 1440

Достижение 1980 (Мастер) или 2330 (Грандмастер) в рейтинговом 1v1 или 2v2 даёт и соответствующее достижение - рейтинг FFA их не запускает. Ранговые роли Discord следуют твоему рейтингу 1v1, а магазинный титул Текущий ранг всегда рендерит твоё живое имя ранга в цвете тира. Тир соперника ещё и умножает твои награды за матч (см. <color=#7FD4FF>XP, золото и уровни</color>).$s256$)
  , ('ffd0bcba80bcba7d', 'sv', '7092efd0e1c1a7263fce0c81c6c69b2e65a70b3e', $s256$Varje rankat läge poängsätter dig med Glicko-2: en rating, plus ett mått på hur säkert systemet är på den. Den här sidan förklarar vad siffrorna betyder, varför de rör sig som de gör, när varje läge uppdaterar, och hela rangstegen.

<color=#FFD94D><b>DE TRE SIFFRORNA</b></color>

<color=#7FD4FF>Rating</color> - skicklighetsuppskattningen. Alla börjar på 1500. Det finns inget golv och inget tak någonstans; din topp spåras per läge.
<color=#7FD4FF>RD (rating deviation)</color> - hur osäker uppskattningen är. Ett helt nytt konto börjar på 350. RD krymper varje gång du spelar - ju mer du spelar, desto säkrare blir systemet.
<color=#7FD4FF>Volatilitet</color> - hur ojämna dina resultat varit. Börjar på 0.06 och justerar sig själv allteftersom resultaten kommer in.

Storleken på en ratingrörelse skalar med DIN RD. Det är därför nya konton svänger hårt - deras första resultat flyttar dem mycket - medan en veterans resultat flyttar dem lite i taget. Att spela fler matcher är det enda som stillar det.

<color=#FFD94D><b>VARFÖR VINSTER OCH FÖRLUSTER INTE ÄR LIKA</b></color>

Innan ett resultat poängsätts beräknar systemet ditt förväntade resultat från ratinggapet. Din ändring är proportionell mot skillnaden mellan vad som hände och vad som förväntades:

- Slå en mycket lägre rankad spelare och du vinner nästan ingenting - vinsten var väntad. Förlora mot dem och du betalar dyrt.
- Slå en högre rankad spelare och du tar den stora sidan av samma affär.
- Motståndarens RD spelar också roll: resultat mot osäkra motståndare (hög RD) dämpas. Att slå ett väletablerat konto flyttar din rating mer än att slå ett färskt okänt.

<color=#FFD94D><b>NÄR RATING FLYTTAS</b></color>

Varje läge har sin helt egna Glicko-rating. Inget du gör i ett läge flyttar någonsin ett annat läges siffra.

- <color=#7FD4FF>1v1</color> - uppdaterar när serien avslutas (först till 2 matchvinster). Hela serien räknas som EN vinst- eller förlustobservation: ett 2-0 och ett 2-1 flyttar din rating identiskt.
- <color=#7FD4FF>2v2</color> - uppdaterar när serien avslutas. Du poängsätts mot BÅDA motståndarna. En serie avgjord av en disconnect tillämpar full rating, precis som en färdigspelad.
- <color=#7FD4FF>FFA</color> - uppdaterar efter varje enskild match, när dess rapport landar.
- <color=#7FD4FF>1v2</color> - <color=#FF6666>orankad beta. Ingen rating flyttas alls.</color> Matcher registreras och kan räknas senare när rankad 1v2 lanseras.

Casual-matcher rör aldrig någon rating.

<color=#FFD94D><b>SÅ POÄNGSÄTTER FFA EN LOBBY</b></color>

En match med 10 spelare behandlas inte som 9 separata dueller - det skulle svänga din rating flera gånger hårdare än en match med 3. I stället:

- Du jämförs med högst 4 motståndare: de som placerats NÄRMAST dig.
- En extra 'skräll'-jämförelse kan sälla sig till dem: det största ratinggapet på 250 eller mer som slutade upp och ner utanför de valda. En per match, hur många skrällar som än skedde.
- Varje jämförelse räknas som vinst om du placerades över dem, förlust om under, och <color=#7FE87F>en delad plats räknas som oavgjort</color>.
- Korta matcher väger mindre: en först-till-3 räknas som en halv match, standardens först-till-5 räknas fullt, och längre mål räknas aldrig som mer än en match.

<color=#FFD94D><b>2v2-FÖRTROENDEREGELN</b></color>

Din 2v2-rating börjar som en gissning, så matchmakern litar inte på den direkt:

- Lagbalanseringen använder din 2v2-rating när du har 10 avslutade serier, ELLER när dess RD konvergerat till 110 eller lägre.
- Tills dess står din 1v1-rating in.
- Topplistans kolumn Snitt-Elo lagkamrater litar på en lagkamrats 2v2-rating efter 5 avslutade serier; innan dess används deras 1v1-rating, eller 1500 om den saknas.

<color=#FFD94D><b>RANGSTEGEN</b></color>

Fem tiers, var och en delad i pinnar I till V - V är toppen av sin tier. Siffran är golvet: du håller en pinne vid eller över den ratingen.

- <color=#7FD4FF>Stormästare</color> - I 2330, II 2400, III 2470, IV 2540, V 2610
- <color=#7FD4FF>Mästare</color> - I 1980, II 2050, III 2120, IV 2190, V 2260
- <color=#7FD4FF>Avancerad</color> - I 1675, II 1725, III 1780, IV 1845, V 1910
- <color=#7FD4FF>Medel</color> - I 1500, II 1525, III 1555, IV 1590, V 1630
- <color=#7FD4FF>Nybörjare</color> - I 0, II 1140, III 1260, IV 1360, V 1440

Att nå 1980 (Mästare) eller 2330 (Stormästare) i ranked 1v1 eller 2v2 ger också motsvarande prestation - FFA-rating utlöser inte dessa. Discords rangroller följer din 1v1-rating, och butikstiteln Nuvarande rang renderar alltid ditt aktuella rangnamn i sin tierfärg. Din motståndares tier multiplicerar dessutom dina matchbelöningar (se <color=#7FD4FF>XP, guld & nivåer</color>).$s256$)
  , ('ffd0bcba80bcba7d', 'uk', '7092efd0e1c1a7263fce0c81c6c69b2e65a70b3e', $s256$Кожен рейтинговий режим оцінює вас Glicko-2: рейтинг плюс міра того, наскільки система в ньому впевнена. Ця сторінка пояснює, що означають числа, чому вони рухаються саме так, коли оновлюється кожен режим, і повну драбину рангів.

<color=#FFD94D><b>ТРИ ЧИСЛА</b></color>

<color=#7FD4FF>Рейтинг</color> - оцінка сили. Всі починають з 1500. Ні підлоги, ні стелі ніде немає; ваш пік відстежується для кожного режиму.
<color=#7FD4FF>RD (відхилення рейтингу)</color> - наскільки оцінка невизначена. Новий акаунт починає з 350. RD стискається щоразу, як ви граєте, - що більше граєте, то впевненіша система.
<color=#7FD4FF>Волатильність</color> - наскільки нестабільними були ваші результати. Починається з 0.06 і підлаштовується сама з новими результатами.

Розмір руху рейтингу масштабується з ВАШИМ RD. Ось чому нові акаунти гойдає сильно - перші результати рухають їх багато, - а результати ветерана рухають його потроху. Єдине, що це вгамовує, - грати більше.

<color=#FFD94D><b>ЧОМУ ЗДОБУТКИ І ВТРАТИ НЕРІВНІ</b></color>

Перш ніж оцінити результат, система обчислює ваш очікуваний результат із розриву рейтингів. Ваша зміна пропорційна різниці між тим, що сталося, і тим, що очікувалося:

- Переможете значно нижчого за рейтингом - не здобудете майже нічого: перемога була очікуваною. Програєте йому - заплатите дорого.
- Переможете вищого за рейтингом - берете велику сторону тієї самої угоди.
- RD суперника теж важить: результати проти невизначених (з високим RD) суперників приглушуються. Перемога над устояним акаунтом рухає ваш рейтинг більше, ніж над свіжим невідомим.

<color=#FFD94D><b>КОЛИ РУХАЮТЬСЯ РЕЙТИНГИ</b></color>

Кожен режим тримає власний повністю окремий рейтинг Glicko. Ніщо, зроблене в одному режимі, не рухає число іншого.

- <color=#7FD4FF>1v1</color> - оновлюється, коли завершується серія (перший до 2 виграних ігор). Уся серія рахується як ОДНЕ спостереження перемоги чи поразки: 2-0 і 2-1 рухають рейтинг ідентично.
- <color=#7FD4FF>2v2</color> - оновлюється, коли завершується серія. Вас оцінюють проти ОБОХ гравців суперника. Серія, вирішена дисконектом, застосовує повні рейтинги, як і дограна.
- <color=#7FD4FF>FFA</color> - оновлюється після кожної окремої гри, коли сідає її звіт.
- <color=#7FD4FF>1v2</color> - <color=#FF6666>нерейтингова бета. Рейтинг не рухається взагалі.</color> Ігри записуються і зможуть зарахуватися пізніше, коли запуститься рейтинговий 1v2.

Звичайні ігри не торкаються жодного рейтингу ніколи.

<color=#FFD94D><b>ЯК FFA ОЦІНЮЄ ЛОБІ</b></color>

Гра на 10 гравців не трактується як 9 окремих дуелей - це гойдало б ваш рейтинг у кілька разів сильніше за гру на 3. Натомість:

- Вас порівнюють щонайбільше з 4 суперниками: тими, чиї місця НАЙБЛИЖЧІ до вашого.
- До них може долучитись одне додаткове порівняння-«апсет»: найбільший розрив рейтингу 250+, що завершився догори дриґом поза тими вибраними. Одне на гру, хоч скільки апсетів сталося.
- Кожне порівняння оцінюється як перемога, якщо ви розмістилися вище за них, поразка - якщо нижче, а <color=#7FE87F>спільне місце рахується нічиєю</color>.
- Короткі ігри важать менше: перший-до-3 рахується як пів гри, типовий перший-до-5 - повністю, а довші цілі ніколи не рахуються більше за одну гру.

<color=#FFD94D><b>ПРАВИЛО ДОВІРИ 2v2</b></color>

Ваш рейтинг 2v2 починається як здогад, тож підбирач не довіряє йому одразу:

- Балансування команд використовує ваш рейтинг 2v2, щойно у вас 10 завершених серій, АБО щойно його RD зійшовся до 110 чи нижче.
- До того замість нього стоїть ваш рейтинг 1v1.
- Колонка «Сер. Elo союзників» таблиці лідерів довіряє рейтингу 2v2 союзника після 5 завершених серій; до того бере його 1v1, або 1500, якщо його немає.

<color=#FFD94D><b>ДРАБИНА РАНГІВ</b></color>

П’ять рівнів, кожен поділений на щаблі I-V - V нагорі свого рівня. Число - підлога: ви тримаєте щабель на цьому рейтингу або вище.

- <color=#7FD4FF>Грандмайстер</color> - I 2330, II 2400, III 2470, IV 2540, V 2610
- <color=#7FD4FF>Майстер</color> - I 1980, II 2050, III 2120, IV 2190, V 2260
- <color=#7FD4FF>Просунутий</color> - I 1675, II 1725, III 1780, IV 1845, V 1910
- <color=#7FD4FF>Середній</color> - I 1500, II 1525, III 1555, IV 1590, V 1630
- <color=#7FD4FF>Початківець</color> - I 0, II 1140, III 1260, IV 1360, V 1440

Досягнення 1980 (Майстер) чи 2330 (Грандмайстер) у рейтингових 1v1 чи 2v2 також дає відповідне досягнення - рейтинг FFA їх не запускає. Ролі рангів Discord ідуть за вашим рейтингом 1v1, а магазинний титул Поточний ранг завжди рендерить вашу живу назву рангу в кольорі його рівня. Рівень суперника також множить ваші нагороди за матч (див. <color=#7FD4FF>XP, золото та рівні</color>).$s256$)
;

INSERT INTO i18n_proposals
  (key_id, language_code, source_hash, proposed_target, proposer_steam_id,
   license_assent, license_terms_rev, assented_at, status, created_at)
SELECT v.key_id, v.lang, v.source_hash, v.target, 'claude-mt',
       TRUE, 'machine-v1', NOW(), 'pending', NOW()
  FROM _seed256 v
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
    FROM _seed256 v
   WHERE NOT EXISTS (
           SELECT 1 FROM i18n_proposals p
            WHERE p.key_id = v.key_id AND p.language_code = v.lang
              AND (p.source_hash = v.source_hash OR p.status = 'pending'))
     AND NOT EXISTS (
           SELECT 1 FROM i18n_entries e
            WHERE e.key_id = v.key_id AND e.language_code = v.lang
              AND e.state = 'approved');
  IF uncovered <> 0 THEN
    SELECT string_agg(x.key_id || '/' || x.lang, ', ') INTO sample
      FROM (SELECT v.key_id, v.lang FROM _seed256 v
             WHERE NOT EXISTS (
                     SELECT 1 FROM i18n_proposals p
                      WHERE p.key_id = v.key_id AND p.language_code = v.lang
                        AND (p.source_hash = v.source_hash OR p.status = 'pending'))
               AND NOT EXISTS (
                     SELECT 1 FROM i18n_entries e
                      WHERE e.key_id = v.key_id AND e.language_code = v.lang
                        AND e.state = 'approved')
             LIMIT 5) x;
    RAISE EXCEPTION 'migration 256: % of 304 seed pairs did not land (e.g. %) - usual cause: key inserts (251/253) missing on this database; nothing was committed', uncovered, sample;
  END IF;
  RAISE NOTICE 'migration 256: all 304 seed pairs covered (76 keys x es/ru/uk/sv)';
END $$;

COMMIT;
