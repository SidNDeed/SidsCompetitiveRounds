-- 303_seed_machine_translations_sept8.sql
--
-- Machine-translated proposal seeds (es/ru/uk/sv) for the strings the Sept 6/7/8
-- batches added (12 keys, 48 pairs). Same contract as 184/189/213/223/239/243/249/256/265/289:
-- PENDING proposals only, sentinel proposer 'claude-mt', license_assent TRUE at
-- the machine-translation terms revision. The same 48 translations ship
-- BUNDLED in I18nCatalogues.cs, so the client renders them without approval;
-- these proposals exist so human translators can see/refine them through the
-- portal (an approval overrides the bundled value via the pack overlay).
--
-- key_id = sha1("client" || chr(0) || source)[:16] - the NUL-separator form
-- tools/i18n_sync_keys.py uses.
--
-- ORDERING: seeds only keys already present in i18n_keys. Run order:
-- deploy API -> apply 302 (or run tools/i18n_sync_keys.py) -> apply this
-- file. On an unsynced database the assertion below RAISEs and the transaction
-- rolls back; re-run after the keys land. Explicit BEGIN/COMMIT (#340); every
-- statement is idempotent under the wrapper's || re-run (#243).
BEGIN;

CREATE TEMP TABLE _seed303 (
  key_id      VARCHAR(16) NOT NULL,
  lang        VARCHAR(8)  NOT NULL,
  source_hash VARCHAR(40) NOT NULL,
  target      TEXT        NOT NULL
) ON COMMIT DROP;

INSERT INTO _seed303 (key_id, lang, source_hash, target) VALUES
  -- "Uncommon"
     ('277adba289bdb3bc', 'es', '1b25b1def15facfdbd36fe3ebb0382030e196693', E'Poco común')
  ,  ('277adba289bdb3bc', 'ru', '1b25b1def15facfdbd36fe3ebb0382030e196693', E'Необычная')
  ,  ('277adba289bdb3bc', 'uk', '1b25b1def15facfdbd36fe3ebb0382030e196693', E'Незвичайна')
  ,  ('277adba289bdb3bc', 'sv', '1b25b1def15facfdbd36fe3ebb0382030e196693', E'Ovanlig')
  -- "Other"
  ,  ('30c705a5b9565018', 'es', 'a08428d584d214df32ded6b0efd35e8feada35b2', E'Otros')
  ,  ('30c705a5b9565018', 'ru', 'a08428d584d214df32ded6b0efd35e8feada35b2', E'Прочее')
  ,  ('30c705a5b9565018', 'uk', 'a08428d584d214df32ded6b0efd35e8feada35b2', E'Інше')
  ,  ('30c705a5b9565018', 'sv', 'a08428d584d214df32ded6b0efd35e8feada35b2', E'Övrigt')
  -- "LOCKED"
  ,  ('3c85c6b1e187fb93', 'es', '92c5a22cba39cecfb28e19eab491c7bcfb365f26', E'CERRADO')
  ,  ('3c85c6b1e187fb93', 'ru', '92c5a22cba39cecfb28e19eab491c7bcfb365f26', E'ЗАКРЫТО')
  ,  ('3c85c6b1e187fb93', 'uk', '92c5a22cba39cecfb28e19eab491c7bcfb365f26', E'ЗАКРИТО')
  ,  ('3c85c6b1e187fb93', 'sv', '92c5a22cba39cecfb28e19eab491c7bcfb365f26', E'LÅST')
  -- "Common"
  ,  ('8b7f3f68f2b2a6be', 'es', '4fc0b8faff24d53cee4e9e20d595ec38dd3c45a9', E'Común')
  ,  ('8b7f3f68f2b2a6be', 'ru', '4fc0b8faff24d53cee4e9e20d595ec38dd3c45a9', E'Обычная')
  ,  ('8b7f3f68f2b2a6be', 'uk', '4fc0b8faff24d53cee4e9e20d595ec38dd3c45a9', E'Звичайна')
  ,  ('8b7f3f68f2b2a6be', 'sv', '4fc0b8faff24d53cee4e9e20d595ec38dd3c45a9', E'Vanlig')
  -- "Unknown"
  ,  ('acd99861498c86bc', 'es', 'cba56bc5bb2f58f1481c22801b7fe24b52339b1f', E'Desconocido')
  ,  ('acd99861498c86bc', 'ru', 'cba56bc5bb2f58f1481c22801b7fe24b52339b1f', E'Неизвестно')
  ,  ('acd99861498c86bc', 'uk', 'cba56bc5bb2f58f1481c22801b7fe24b52339b1f', E'Невідомо')
  ,  ('acd99861498c86bc', 'sv', 'cba56bc5bb2f58f1481c22801b7fe24b52339b1f', E'Okänd')
  -- "Un-stacked, full flight. The mod pins every eligible Grow bu"
  ,  ('b39e6f71b9eb5aee', 'es', 'b8a882a44e53375306a932c3daa7f72a063fe4ff', E'Sin acumular, vuelo completo. El mod fija cada bala Grow apta al mismo reloj de crecimiento de 120 FPS.')
  ,  ('b39e6f71b9eb5aee', 'ru', 'b8a882a44e53375306a932c3daa7f72a063fe4ff', E'Без копий, полный полёт. Мод привязывает каждую подходящую пулю Grow к единому таймеру роста 120 FPS.')
  ,  ('b39e6f71b9eb5aee', 'uk', 'b8a882a44e53375306a932c3daa7f72a063fe4ff', E'Без копій, повний політ. Мод прив\'язує кожну придатну кулю Grow до єдиного таймера росту 120 FPS.')
  ,  ('b39e6f71b9eb5aee', 'sv', 'b8a882a44e53375306a932c3daa7f72a063fe4ff', E'Ostaplad, full flykt. Modden låser varje giltig Grow-kula till samma tillväxtklocka på 120 FPS.')
  -- "<color=#FFD94D><b>THE KEYS IN PRACTICE</b></color> F5 works "
  ,  ('d4f8ae22554cca00', 'es', 'bceb5f723e36bb6507cde87f4f07e2cc5992e6d3', E'<color=#FFD94D><b>LAS TECLAS EN LA PRÁCTICA</b></color>\nF5 funciona en todas partes - menú, sala, en plena partida. Con el menú abierto tus entradas no llegan al juego: los clics no disparan tu arma, Espacio no te pone listo, y Escape solo cierra el menú - no cancelará una partida que se está conectando. Ciérralo y todo vuelve a fluir.\n\nEl chat tiene tres puertas. T escribe un mensaje, mantener Q abre la rueda de chat rápido - apunta a una frase y suelta para enviarla, o elige Más... para la lista completa - y Enter sigue abriendo el cuadro vanilla - el mod no lo toca. M alterna el modo de visualización del chat. Mientras escribes, un toque de Alt cambia el canal de idioma al que va tu mensaje - global, luego cada canal de idioma por turno, y de vuelta a global; el desplegable de la pestaña Inicio también lo fija.\n\nMantener E abre la rueda de emotes - incluso en plena batalla: apunta a un baile que poseas y suelta para bailarlo ante todos los que usan el mod. Tus propios controles se bloquean hasta que el baile termina, y el baile se corta si te zarandean o disparas. Los bailes se compran en la sección BAILES de la tienda, donde Previa muestra los movimientos exactos.\n\nMantén Tab durante una partida para el marcador en vivo: puntuación, cartas, precisión e información de conexión de todos en la sala, sin abrir el menú completo.\n\nShift alterna entre tus skins de color de mapa equipadas cuando una nueva ronda se pinta. Si no tienes ninguna equipada, no hace nada.\n\nLa reasignación vanilla vive en las opciones del juego; las teclas del mod son fijas. Para saber qué practicar con todo esto, lee <color=#7FD4FF>Cómo mejorar</color>.')
  ,  ('d4f8ae22554cca00', 'ru', 'bceb5f723e36bb6507cde87f4f07e2cc5992e6d3', E'<color=#FFD94D><b>КЛАВИШИ НА ПРАКТИКЕ</b></color>\nF5 работает везде - меню, лобби, посреди игры. Пока меню открыто, твой ввод в игру не попадает: клики не стреляют из пушки, Space не готовит тебя, а Escape только закрывает меню - подключающийся матч он не отменит. Закрой его - и всё снова течёт.\n\nУ чата три двери. T печатает сообщение, удержание Q открывает колесо быстрого чата - наведись на фразу и отпусти, чтобы отправить, или выбери «Ещё...» для полного списка, - а Enter по-прежнему открывает ванильное окно - мод его не трогает. M переключает режим оверлея чата. Во время набора нажатие Alt переключает языковой канал, в который уйдёт сообщение - общий, затем каждый языковой канал по очереди, потом снова общий; список на вкладке Главная задаёт его тоже.\n\nУдержание E открывает колесо эмоций - даже посреди боя: наведись на танец, которым владеешь, и отпусти, чтобы исполнить его для всех, у кого стоит мод. Твоё управление заблокировано до конца танца, а танец прерывается, если тебя расшвыряло или ты выстрелил. Танцы покупаются в разделе ТАНЦЫ магазина, где Превью показывает точные движения.\n\nДержи Tab во время матча - живое табло: счёт, карты, точность и данные о соединении всех в комнате, без открытия полного меню.\n\nShift переключает надетые цветовые скины карты, когда прорисовывается новый раунд. Если ничего не надето, он ничего не делает.\n\nВанильная перепривязка живёт в настройках игры; сами клавиши мода фиксированы. Что со всем этим тренировать - читай <color=#7FD4FF>Как играть лучше</color>.')
  ,  ('d4f8ae22554cca00', 'uk', 'bceb5f723e36bb6507cde87f4f07e2cc5992e6d3', E'<color=#FFD94D><b>КЛАВІШІ НА ПРАКТИЦІ</b></color>\nF5 працює всюди - меню, лобі, посеред гри. Поки меню відкрите, ваші натискання не потрапляють у гру: кліки не стріляють, Space не готує вас до бою, а Escape лише закриває меню - він не скасує матч, що під\'єднується. Закрийте його - і все знову тече як зазвичай.\n\nУ чату троє дверей. T набирає повідомлення, утримування Q відкриває колесо швидкого чату - наведіть на фразу й відпустіть, щоб надіслати, або виберіть «Більше...» для повного списку - а Enter, як і раніше, відкриває ванільне віконце - мод його не чіпає. M перемикає режим показу оверлея чату. Під час набору натискання Alt перемикає мовний канал, у який піде повідомлення - загальний, потім кожен мовний канал по черзі, потім знову загальний; список на вкладці Головна теж його задає.\n\nУтримування E відкриває колесо емоцій - навіть посеред бою: наведіть на танець, яким володієте, і відпустіть, щоб станцювати для всіх, у кого стоїть мод. Ваше власне керування блокується до кінця танцю, а танець зупиняється, якщо вас відкинуло або ви вистрілили. Танці купуються в розділі DANCES магазину, де «Перегляд» показує точні рухи.\n\nУтримуйте Tab під час матчу для живого табло: рахунок, карти, точність і стан з\'єднання всіх у кімнаті, без відкривання повного меню.\n\nShift перемикає ваші вдягнені кольорові скіни мап, коли промальовується новий раунд. Якщо нічого не вдягнено, він нічого не робить.\n\nВанільне перепризначення клавіш живе в налаштуваннях гри; клавіші мода фіксовані. Про те, що з усім цим тренувати, читайте <color=#7FD4FF>Як стати кращим</color>.')
  ,  ('d4f8ae22554cca00', 'sv', 'bceb5f723e36bb6507cde87f4f07e2cc5992e6d3', E'<color=#FFD94D><b>TANGENTERNA I PRAKTIKEN</b></color>\nF5 fungerar överallt - i menyn, i lobbyn, mitt i matchen. Medan menyn är öppen hålls dina inmatningar utanför spelet: klick avfyrar inte ditt vapen, mellanslag gör dig inte redo, och Escape stänger bara menyn - den avbryter inte en match som håller på att ansluta. Stäng den och allt flyter igen.\n\nChatten har tre dörrar. T skriver ett meddelande, håll Q för att öppna snabbchattshjulet - sikta på en fras och släpp för att skicka den, eller välj Mer... för hela listan - och Enter öppnar fortfarande originalrutan - modden rör den inte. M växlar chattoverlayens visningsläge. Medan du skriver byter ett tryck på Alt vilken språkkanal meddelandet går till - global, sedan varje språkkanal i tur och ordning, sedan tillbaka till global; listrutan på Hem-fliken ställer också in den.\n\nHåll E för att öppna emote-hjulet - även mitt i striden: sikta på en dans du äger och släpp för att spela den för alla som kör modden. Dina egna kontroller låses tills dansen är slut, och dansen avbryts om du blir omkullknuffad eller skjuter. Danser köps i butikens DANSER-sektion, där Förhandsvisa visar exakt vilka rörelser det blir.\n\nHåll Tab under en match för live-resultattavlan: poäng, kort, träffsäkerhet och anslutningsinfo för alla i rummet, utan att öppna hela menyn.\n\nShift växlar mellan dina utrustade kartfärgsskins när en ny rond målas upp. Har du inga utrustade händer ingenting.\n\nOmkoppling av originalspelets tangenter finns i spelets inställningar; moddens egna tangenter är fasta. För vad du kan öva på med allt det här, läs <color=#7FD4FF>Bli bättre</color>.')
  -- "Rare"
  ,  ('de18f3040b883b5b', 'es', 'ada8fa22929d535cad04b537fd39614612ad9d59', E'Rara')
  ,  ('de18f3040b883b5b', 'ru', 'ada8fa22929d535cad04b537fd39614612ad9d59', E'Редкая')
  ,  ('de18f3040b883b5b', 'uk', 'ada8fa22929d535cad04b537fd39614612ad9d59', E'Рідкісна')
  ,  ('de18f3040b883b5b', 'sv', 'ada8fa22929d535cad04b537fd39614612ad9d59', E'Sällsynt')
  -- "Grow is the one card whose damage depends on the shooter's F"
  ,  ('f6aadcc70032390e', 'es', 'b3c9e95927a0652365c01644ca86eb2e5220af9f', E'Grow es la única carta cuyo daño depende de la TASA DE FRAMES del tirador. En vanilla, la misma bala de Grow disparada por un jugador a 60 FPS pega mucho más fuerte que una disparada a 400 FPS - y el mod la normaliza en juego competitivo.\n\n<color=#FFD94D><b>LA MATEMÁTICA REAL</b></color>\n\nGrow multiplica el daño de la bala un poco en cada frame renderizado mientras vuela, durante más o menos las primeras 30 unidades de recorrido. Componer un multiplicador por frame tiene una consecuencia extraña: la velocidad de la bala se cancela del total, y lo que realmente fija el multiplicador final es la duración de los frames del tirador. Menos frames, más largos, componen más fuerte.\n\nSin acumular, en un vuelo completo:\n\n- Tirador a 400 FPS: alrededor de <color=#7FD4FF>x1.07</color>\n- Tirador a 60 FPS: alrededor de <color=#7FD4FF>x1.53</color>\n- Tirador a 30 FPS: alrededor de <color=#7FD4FF>x2.31</color>\n\nAcumular multiplica la tasa de crecimiento, así que la brecha explota. Con cuatro copias: alrededor de x1.29 a 400 FPS, <color=#FF6666>x5.47 a 60 FPS, y x28.5 a 30 FPS</color>.\n\nLos tirones son el peor caso: <color=#FF6666>un solo frame congelado de 200 ms multiplica la bala por unas x2.16 él solo</color>. Un parón a mitad de vuelo puede convertir un disparo normal en un one-shot.\n\n<color=#FFD94D><b>POR QUÉ SUS FPS SE VUELVEN TU PROBLEMA</b></color>\n\nEl daño en ROUNDS lo decide el tirador: la máquina del tirador computa lo que la víctima recibe, y todos los demás aplican ese número (ver <color=#7FD4FF>Netcode y Photon</color>). El crecimiento de Grow ocurre en los frames del tirador, así que las balas de Grow de un rival con FPS bajos o tirones pegan de verdad más fuerte. No es lag, no es tu imaginación, y en vanilla tampoco es trampa - es la matemática de la carta.\n\n<color=#FFD94D><b>LA NORMALIZACIÓN DEL MOD</b></color>\n\nEn salas elegibles, el mod fija el reloj de crecimiento de Grow: <color=#7FE87F>cada bala de Grow crece como si su tirador corriera a 120 FPS, en todas las máquinas</color>. Contra una base de FPS altísimos eso significa alrededor de +24 por ciento en un vuelo completo sin acumular, +53 por ciento con dos copias, +134 con cuatro - lo mismo para todos, en cada partida. La tasa de referencia va compilada en el mod a propósito: si fuera un ajuste, cambiarla cambiaría tu propio daño.\n\nDónde aplica:\n\n- Cada luchador de la sala debe usar una build actual del mod (los espectadores no cuentan). <color=#FF6666>Un luchador vanilla o desactualizado significa crecimiento vanilla para toda la sala</color>, igual en cada pantalla - una sala mixta nunca queda medio normalizada.\n- Las salas de cola del mod (ranked 1v1, 2v2, 1v2, FFA, salas de torneo) normalizan siempre que todos están al día.\n- Las partidas privadas por código y el quickplay normalizan solo cuando, además, cada luchador tenía el interruptor Ranked ACTIVO al conectar.\n- La decisión se fija por bala al dispararla y nunca cambia en pleno vuelo. Nunca está activa offline.\n\nUn residuo honesto: a tasas de frames muy bajas una bala normalizada puede crecer ligeramente MENOS que el objetivo (un pequeño porcentaje acumulado; más en un tirón fuerte). El error siempre apunta hacia abajo - nunca hacia el one-shot.')
  ,  ('f6aadcc70032390e', 'ru', 'b3c9e95927a0652365c01644ca86eb2e5220af9f', E'Grow - единственная карта, чей урон зависит от ЧАСТОТЫ КАДРОВ стрелка. В ванили одна и та же пуля Grow, выпущенная игроком на 60 FPS, бьёт заметно больнее, чем на 400 FPS, - и в соревновательной игре мод это нормализует.\n\n<color=#FFD94D><b>НАСТОЯЩАЯ МАТЕМАТИКА</b></color>\n\nGrow понемногу умножает урон пули каждый отрисованный кадр, пока она летит, примерно на первых 30 юнитах пути. У накопления покадрового множителя странное следствие: скорость пули из итога сокращается, и финальный множитель на деле задаёт длина кадров стрелка. Меньше кадров, длиннее кадры - жёстче накопление.\n\nБез стаков, за полный полёт:\n\n- Стрелок на 400 FPS: около <color=#7FD4FF>x1.07</color>\n- Стрелок на 60 FPS: около <color=#7FD4FF>x1.53</color>\n- Стрелок на 30 FPS: около <color=#7FD4FF>x2.31</color>\n\nСтакание умножает скорость роста, и разрыв взрывается. На четырёх стаках: около x1.29 при 400 FPS, <color=#FF6666>x5.47 при 60 FPS и x28.5 при 30 FPS</color>.\n\nХудший случай - лаги: <color=#FF6666>один зависший кадр в 200 мс умножает пулю примерно на x2.16 сам по себе</color>. Один статтер посреди полёта превращает обычный выстрел в ваншот.\n\n<color=#FFD94D><b>ПОЧЕМУ ИХ FPS СТАНОВИТСЯ ТВОЕЙ ПРОБЛЕМОЙ</b></color>\n\nУрон в ROUNDS авторитетен на стрелке: его машина вычисляет, что получит жертва, и все применяют это число (см. <color=#7FD4FF>Неткод и Photon</color>). Рост Grow происходит на кадрах стрелка, так что пули Grow соперника с низким FPS или статтерами реально бьют больнее. Это не лаг, не твоё воображение и в ванили даже не чит - это математика карты.\n\n<color=#FFD94D><b>НОРМАЛИЗАЦИЯ МОДА</b></color>\n\nВ подходящих комнатах мод фиксирует часы роста Grow: <color=#7FE87F>каждая пуля Grow растёт так, будто её стрелок бежит на 120 FPS, на любой машине</color>. Против базовой линии очень высокого FPS это примерно +24 процентов за полный полёт без стаков, +53 на двух стаках, +134 на четырёх - одинаково для всех, каждую игру. Опорная частота вшита в мод намеренно: будь она настройкой, её изменение меняло бы твой собственный урон.\n\nГде это действует:\n\n- Каждый боец в комнате должен играть на свежей сборке мода (зрители не считаются). <color=#FF6666>Один ванильный или устаревший боец - ванильный рост на всю комнату</color>, одинаково на каждом экране: смешанное лобби никогда не бывает полунормализованным.\n- Комнаты очередей мода (рейтинговый 1v1, 2v2, 1v2, FFA, турнирные комнаты) нормализуются всякий раз, когда все свежие.\n- Приватные игры по коду комнаты и quickplay нормализуются, только если поверх этого у каждого бойца был включён Ranked на момент подключения.\n- Решение фиксируется на пулю в момент выстрела и посреди полёта не переворачивается. Офлайн оно не активно никогда.\n\nОдин честный остаток: на очень низкой частоте кадров нормализованная пуля может вырасти чуть МЕНЬШЕ цели (пара процентов на стаках; больше на тяжёлом лаге). Ошибка всегда смотрит вниз - никогда в сторону ваншота.')
  ,  ('f6aadcc70032390e', 'uk', 'b3c9e95927a0652365c01644ca86eb2e5220af9f', E'Grow - єдина карта, чия шкода залежить від ЧАСТОТИ КАДРІВ стрільця. У ванілі та сама куля Grow, випущена гравцем на 60 FPS, б\'є значно сильніше за випущену на 400 FPS - і мод нормалізує це у змагальній грі.\n\n<color=#FFD94D><b>СПРАВЖНЯ МАТЕМАТИКА</b></color>\n\nGrow трохи множить шкоду кулі кожен відрендерений кадр польоту, приблизно перші 30 одиниць шляху. Нарощування покадрового множника має дивний наслідок: швидкість кулі скорочується з підсумку, і фінальний множник насправді задає довжина кадрів стрільця. Менше кадрів, але довших - нарощують сильніше.\n\nБез копій, за повний політ:\n\n- стрілець на 400 FPS: близько <color=#7FD4FF>x1.07</color>\n- стрілець на 60 FPS: близько <color=#7FD4FF>x1.53</color>\n- стрілець на 30 FPS: близько <color=#7FD4FF>x2.31</color>\n\nСтакання множить темп росту, тож прірва вибухає. На чотирьох копіях: близько x1.29 на 400 FPS, <color=#FF6666>x5.47 на 60 FPS і x28.5 на 30 FPS</color>.\n\nНайгірший випадок - підвисання: <color=#FF6666>один завислий кадр на 200 мс сам по собі множить кулю приблизно на x2.16</color>. Один статер посеред польоту може перетворити звичайний постріл на ваншот.\n\n<color=#FFD94D><b>ЧОМУ ЇХНІЙ FPS СТАЄ ВАШОЮ ПРОБЛЕМОЮ</b></color>\n\nШкода в ROUNDS авторитетна за стрільцем: машина стрільця обчислює, скільки отримує жертва, і всі решта застосовують це число (див. <color=#7FD4FF>Неткод і Photon</color>). Ріст Grow іде на кадрах стрільця, тож кулі Grow суперника з низьким FPS чи статерами справді б\'ють сильніше. Це не лаг, не ваша уява і у ванілі навіть не чит - це математика карти.\n\n<color=#FFD94D><b>НОРМАЛІЗАЦІЯ ВІД МОДА</b></color>\n\nУ придатних кімнатах мод фіксує годинник росту Grow: <color=#7FE87F>кожна куля Grow росте так, ніби її стрілець грає на 120 FPS, на кожній машині</color>. Проти бази з дуже високим FPS це означає приблизно +24 відсотків за повний політ без копій, +53 на двох копіях, +134 на чотирьох - однаково для всіх, кожну гру. Опорна частота навмисно вшита в мод: якби це було налаштування, його зміна міняла б вашу власну шкоду.\n\nДе це діє:\n\n- Кожен боєць у кімнаті мусить грати на актуальному білді мода (глядачі не рахуються). <color=#FF6666>Один ванільний чи застарілий боєць - і ванільний ріст на всю кімнату</color>, однаково на кожному екрані: змішане лобі ніколи не буває напівнормалізованим.\n- Кімнати черг мода (рейтингові 1v1, 2v2, 1v2, FFA, турнірні кімнати) нормалізують щоразу, коли всі актуальні.\n- Приватні ігри за кодом кімнати та квікплей нормалізують лише коли, на додачу, кожен боєць мав Ranked УВІМКНЕНИМ на момент підключення.\n- Рішення фіксується для кожної кулі на пострілі й ніколи не перемикається в польоті. В офлайні воно не активне ніколи.\n\nОдин чесний залишок: на дуже низьких частотах кадрів нормалізована куля може вирости трохи МЕНШЕ за ціль (кілька відсотків зі стаком; більше на важкому підвисанні). Похибка завжди вниз - ніколи в бік ваншота.')
  ,  ('f6aadcc70032390e', 'sv', 'b3c9e95927a0652365c01644ca86eb2e5220af9f', E'Grow är det enda kortet vars skada beror på skyttens BILDFREKVENS. I originalet slår samma Grow-kula avfyrad av en 60 FPS-spelare mycket hårdare än en avfyrad vid 400 FPS - och modden normaliserar det i tävlingsspel.\n\n<color=#FFD94D><b>DEN RIKTIGA MATEMATIKEN</b></color>\n\nGrow multiplicerar kulans skada lite varje renderad bildruta medan den flyger, genom ungefär de första 30 enheterna av färden. Att ackumulera en per-bildruta-multiplikator har en märklig konsekvens: kulans hastighet försvinner ur totalen, och det som faktiskt bestämmer slutmultiplikatorn är längden på skyttens bildrutor. Färre, längre bildrutor ackumulerar hårdare.\n\nUtan stackning, över en full flygbana:\n\n- 400 FPS-skytt: ungefär <color=#7FD4FF>x1.07</color>\n- 60 FPS-skytt: ungefär <color=#7FD4FF>x1.53</color>\n- 30 FPS-skytt: ungefär <color=#7FD4FF>x2.31</color>\n\nStackning multiplicerar tillväxttakten, så gapet exploderar. Vid fyra stackar: ungefär x1.29 vid 400 FPS, <color=#FF6666>x5.47 vid 60 FPS och x28.5 vid 30 FPS</color>.\n\nHackningar är värsta fallet: <color=#FF6666>en enda 200 ms frusen bildruta multiplicerar kulan med ungefär x2.16 helt själv</color>. En hackning mitt i flygbanan kan förvandla ett normalt skott till en one-shot.\n\n<color=#FFD94D><b>VARFÖR DERAS FPS BLIR DITT PROBLEM</b></color>\n\nSkada i ROUNDS är skytte-auktoritativ: skyttens maskin räknar ut vad offret tar, och alla andra applicerar den siffran (se <color=#7FD4FF>Nätkod & Photon</color>). Grows tillväxt sker på skyttens bildrutor, så en motståndares Grow-kulor slår genuint hårdare vid låg FPS eller hackande. Det är inte lagg, det är inte din fantasi, och i originalet är det inte fusk heller - det är kortets matematik.\n\n<color=#FFD94D><b>MODDENS NORMALISERING</b></color>\n\nI berättigade rum låser modden Grows tillväxtklocka: <color=#7FE87F>varje Grow-kula växer som om dess skytt körde 120 FPS, på varje maskin</color>. Mot en mycket-hög-FPS-baslinje betyder det ungefär +24 procent över en full flygbana utan stackning, +53 procent vid två stackar, +134 procent vid fyra - samma för alla, varje match. Referenstakten är inkompilerad i modden med flit: vore den en inställning skulle en ändring ändra din egen skada.\n\nVar det gäller:\n\n- Varje kämpe i rummet måste köra ett aktuellt moddbygge (åskådare räknas inte). <color=#FF6666>En enda kämpe utan modden eller med föråldrad modd betyder originaltillväxt för hela rummet</color>, samma på varje skärm - en blandad lobby är aldrig halvnormaliserad.\n- Moddens körum (Ranked 1v1, 2v2, 1v2, FFA, turneringsrum) normaliserar när alla är aktuella.\n- Privata rumskods- och quickplay-matcher normaliserar bara när, utöver det, varje kämpe hade Ranked-växeln PÅ när de anslöt.\n- Beslutet låses per kula vid avfyrningen och byter aldrig mitt i flygbanan. Det är aldrig aktivt offline.\n\nEn ärlig rest: vid mycket låga bildfrekvenser kan en normaliserad kula växa något MINDRE än målet (några procent stackat; mer vid en kraftig hackning). Felet pekar alltid nedåt - aldrig mot one-shoten.')
  -- "competitive clock: 120 FPS"
  ,  ('f81f26ce4b5af021', 'es', 'f89dbad40ddd7997cc2643ea0dd31f5156b2c380', E'reloj competitivo: 120 FPS')
  ,  ('f81f26ce4b5af021', 'ru', 'f89dbad40ddd7997cc2643ea0dd31f5156b2c380', E'соревновательный таймер: 120 FPS')
  ,  ('f81f26ce4b5af021', 'uk', 'f89dbad40ddd7997cc2643ea0dd31f5156b2c380', E'змагальний таймер: 120 FPS')
  ,  ('f81f26ce4b5af021', 'sv', 'f89dbad40ddd7997cc2643ea0dd31f5156b2c380', E'tävlingsklocka: 120 FPS')
  -- "ALT (tap, while typing in chat) - switch the chat language c"
  ,  ('fad65cb9bd9fbc64', 'es', '9a36624f1ee1a5e95a3068fa7235369803261294', E'ALT (toque, mientras escribes en el chat) - cambia el canal de idioma del chat')
  ,  ('fad65cb9bd9fbc64', 'ru', '9a36624f1ee1a5e95a3068fa7235369803261294', E'ALT (нажатие, во время набора в чате) - переключить языковой канал чата')
  ,  ('fad65cb9bd9fbc64', 'uk', '9a36624f1ee1a5e95a3068fa7235369803261294', E'ALT (натискання, під час набору в чаті) - перемкнути мовний канал чату')
  ,  ('fad65cb9bd9fbc64', 'sv', '9a36624f1ee1a5e95a3068fa7235369803261294', E'ALT (tryck, medan du skriver i chatten) - byt chattens språkkanal')
  -- "Chat has language channels - use the dropdown on the Home ta"
  ,  ('fb7745c00b2d52ff', 'es', 'ebc78f21b3224fa060eed08983da3a29b8b5e7e9', E'El chat tiene canales por idioma - usa el desplegable de la pestaña Inicio, o toca Alt mientras escribes, para cambiar.')
  ,  ('fb7745c00b2d52ff', 'ru', 'ebc78f21b3224fa060eed08983da3a29b8b5e7e9', E'В чате есть языковые каналы - переключай их через список на вкладке Главная или нажатием Alt при вводе.')
  ,  ('fb7745c00b2d52ff', 'uk', 'ebc78f21b3224fa060eed08983da3a29b8b5e7e9', E'У чаті є мовні канали - перемикайте через список на вкладці Головна або натисканням Alt під час набору.')
  ,  ('fb7745c00b2d52ff', 'sv', 'ebc78f21b3224fa060eed08983da3a29b8b5e7e9', E'Chatten har språkkanaler - byt via listrutan på Hem-fliken eller med ett tryck på Alt medan du skriver.')
;

INSERT INTO i18n_proposals
  (key_id, language_code, source_hash, proposed_target, proposer_steam_id,
   license_assent, license_terms_rev, assented_at, status, created_at)
SELECT v.key_id, v.lang, v.source_hash, v.target, 'claude-mt',
       TRUE, 'machine-v1', NOW(), 'pending', NOW()
  FROM _seed303 v
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
DECLARE
  uncovered INTEGER;
  sample TEXT;
BEGIN
  SELECT COUNT(*) INTO uncovered
    FROM _seed303 v
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
      FROM (SELECT v.key_id, v.lang FROM _seed303 v
             WHERE NOT EXISTS (
                     SELECT 1 FROM i18n_proposals p
                      WHERE p.key_id = v.key_id AND p.language_code = v.lang
                        AND (p.source_hash = v.source_hash OR p.status = 'pending'))
               AND NOT EXISTS (
                     SELECT 1 FROM i18n_entries e
                      WHERE e.key_id = v.key_id AND e.language_code = v.lang
                        AND e.state = 'approved')
             LIMIT 5) x;
    RAISE EXCEPTION 'migration 303: % of 48 seed pairs did not land (e.g. %) - the usual cause is that 302 / tools/i18n_sync_keys.py has not run against this database yet; nothing committed', uncovered, sample;
  END IF;

  RAISE NOTICE 'migration 303: all 48 seed pairs covered (12 keys x es/ru/uk/sv)';
END $$;

COMMIT;
