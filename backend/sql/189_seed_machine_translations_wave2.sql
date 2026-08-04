-- 189: second wave of machine-translated proposals (Aug-4).
--
-- WHY A NEW FILE RATHER THAN MORE ROWS IN 184: migration 184 is already applied
-- in production. Appending to an applied migration is invisible to any deploy
-- that tracks which files have run, so those proposals would silently never
-- exist (Codex Aug-4 round-2 find 1 — caught before deploy, not after).
--
-- Same contract as 184: PENDING proposals only, sentinel proposer 'claude-mt'
-- so the audit trail shows plainly that a machine wrote them, license_assent
-- TRUE with a machine-translation terms revision so they can never be mistaken
-- for a human's licensed contribution.
--
-- Rerunnable on the same terms as 184: skip a key+language that already has a
-- pending proposal from ANYONE, and skip any (key, language, source revision)
-- this sentinel has EVER proposed regardless of status — a moderator's
-- reject/approve must stay decided across reruns.
--
-- ORDERING: seeds only for keys already present in i18n_keys, which
-- tools/i18n_sync_keys.py populates AFTER the API deploy. On a database whose
-- key sync has not run, this inserts ZERO rows and says so below; re-running it
-- after the sync backfills exactly the missing ones.
INSERT INTO i18n_proposals
  (key_id, language_code, source_hash, proposed_target, proposer_steam_id,
   license_assent, license_terms_rev, assented_at, status, created_at)
SELECT v.key_id, v.lang, v.source_hash, v.target, 'claude-mt',
       TRUE, 'machine-v1', NOW(), 'pending', NOW()
  FROM (VALUES
  ('cae733acdf0cbe30', 'es', 'bb30f7c5455dcb902480e223845d98e806abe238', '(clic / usa < >)')
  , ('cae733acdf0cbe30', 'ru', 'bb30f7c5455dcb902480e223845d98e806abe238', '(клик / < >)')
  , ('8bcb3efd4061dec8', 'es', 'f28e610419f1325a85ac26b611cf6f96e8d60876', '(cargando...)')
  , ('8bcb3efd4061dec8', 'ru', 'f28e610419f1325a85ac26b611cf6f96e8d60876', '(загрузка...)')
  , ('e76f8724d967828e', 'es', 'e3fc7fd1e8476c924415195ceb0e256825cca8af', 'Rating 2v2')
  , ('e76f8724d967828e', 'ru', 'e3fc7fd1e8476c924415195ceb0e256825cca8af', 'Рейтинг 2v2')
  , ('fdbd0ecf1244c020', 'es', '1890b7a9d93676cbf2707078cbfba41e5787666e', 'Barridas 5-0')
  , ('fdbd0ecf1244c020', 'ru', '1890b7a9d93676cbf2707078cbfba41e5787666e', 'Всухую 5-0')
  , ('5eff08c9ac85a416', 'es', '53c3940e8df73697c97ab5edce695bfe72450d7d', '5-0 dadas / recibidas')
  , ('5eff08c9ac85a416', 'ru', '53c3940e8df73697c97ab5edce695bfe72450d7d', '5-0 отдано / получено')
  , ('44a9ae7c639fd2e4', 'es', '0b847feca26a4748195b25eedff430653aebabb0', '<color=#777>rondas a la izquierda - cada escalón es un punto anotado</color>')
  , ('44a9ae7c639fd2e4', 'ru', '0b847feca26a4748195b25eedff430653aebabb0', '<color=#777>раунды слева - каждый шаг = одно очко</color>')
  , ('cf1c3f9f78d8e96b', 'es', 'd264b77b8a1c62b1fabaf5152b21d294d589c9bd', '<color=#777>{0} daño / {1} bloqueos</color>')
  , ('cf1c3f9f78d8e96b', 'ru', 'd264b77b8a1c62b1fabaf5152b21d294d589c9bd', '<color=#777>{0} урона / {1} блоков</color>')
  , ('21e8b9f068f73353', 'es', '1f835b9f9fadc2c1b294ebb286b32f3d73a2c2ae', '<color=#777>{0} disparos / {1} aciertos ({2:F0}%)</color>')
  , ('21e8b9f068f73353', 'ru', '1f835b9f9fadc2c1b294ebb286b32f3d73a2c2ae', '<color=#777>{0} выстрелов / {1} попаданий ({2:F0}%)</color>')
  , ('503299a3e558e34f', 'es', '87f809301f9f7b489483cdf2291ee0be17560216', '<color=#7788AA><i>buscar jugadores...</i></color>')
  , ('503299a3e558e34f', 'ru', '87f809301f9f7b489483cdf2291ee0be17560216', '<color=#7788AA><i>поиск игроков...</i></color>')
  , ('65d7670c7a57530a', 'es', 'cf3d5ce1d2f0ce340da36b8cb047d330a7e541bb', '<color=#CCC>Daño recibido vs bloqueos</color>')
  , ('65d7670c7a57530a', 'ru', 'cf3d5ce1d2f0ce340da36b8cb047d330a7e541bb', '<color=#CCC>Урон получен / блоки</color>')
  , ('0bef6893b50362d8', 'es', '098e8c6ff86c7d21c0e60cab817654f2b8c0e276', '<color=#CCC>FPS</color>')
  , ('0bef6893b50362d8', 'ru', '098e8c6ff86c7d21c0e60cab817654f2b8c0e276', '<color=#CCC>FPS</color>')
  , ('05347a04a3a75031', 'es', '8ea095243d5e72c3eddc0d586a212666cbd8b714', '<color=#CCC>Ping (ms)</color>')
  , ('05347a04a3a75031', 'ru', '8ea095243d5e72c3eddc0d586a212666cbd8b714', '<color=#CCC>Пинг (мс)</color>')
  , ('d561d401c70c4984', 'es', '9d4ae048ec09950231d3ec5f92e1f1588918a061', '<color=#CCC>Disparos vs aciertos</color>')
  , ('d561d401c70c4984', 'ru', '9d4ae048ec09950231d3ec5f92e1f1588918a061', '<color=#CCC>Выстрелы / попадания</color>')
  , ('4f800bc0a79049a7', 'es', '408d837badbdeb85438e79c340bb2b5fa88a2802', '<color=#CCCCCC>Bloqueo — <color=#99B3E6>tú</color></color>  <color={0}>daño recibido</color> <color=#888>·</color> <color={1}>bloqueos</color>')
  , ('4f800bc0a79049a7', 'ru', '408d837badbdeb85438e79c340bb2b5fa88a2802', '<color=#CCCCCC>Блок — <color=#99B3E6>ты</color></color>  <color={0}>урон получен</color> <color=#888>·</color> <color={1}>блоки</color>')
  , ('d9c7e321f2f94b4d', 'es', '893f02fcd9e7d53be8866d876983dcc5635806fd', '<color=#CCCCCC>Bloqueo — <color=#E69988>rival</color></color>  <color={0}>daño recibido</color> <color=#888>·</color> <color={1}>bloqueos</color>')
  , ('d9c7e321f2f94b4d', 'ru', '893f02fcd9e7d53be8866d876983dcc5635806fd', '<color=#CCCCCC>Блок — <color=#E69988>соперник</color></color>  <color={0}>урон получен</color> <color=#888>·</color> <color={1}>блоки</color>')
  , ('cf5674f2c394e9f5', 'es', 'fe71233ddf90b089c1810f30aa5db406e4137f50', '<color=#CCCCCC>FPS durante la partida</color>  <color=#99B3E6>tú</color> <color=#888>vs</color> <color=#E69988>rival</color>')
  , ('cf5674f2c394e9f5', 'ru', 'fe71233ddf90b089c1810f30aa5db406e4137f50', '<color=#CCCCCC>FPS за матч</color>  <color=#99B3E6>ты</color> <color=#888>vs</color> <color=#E69988>соперник</color>')
  , ('bdab91b8c8fb2d0d', 'es', 'd7c530748fddb5ff351719de541df686dd0c13ab', '<color=#CCCCCC>Acierto — <color=#99B3E6>tú</color></color>  <color={0}>disparos</color> <color=#888>·</color> <color={1}>aciertos</color>')
  , ('bdab91b8c8fb2d0d', 'ru', 'd7c530748fddb5ff351719de541df686dd0c13ab', '<color=#CCCCCC>Попадания — <color=#99B3E6>ты</color></color>  <color={0}>выстрелы</color> <color=#888>·</color> <color={1}>попадания</color>')
  , ('22c8024854c1d08e', 'es', 'b2d6bc42dea14ebed5a3cdb1d6302871595a1d8b', '<color=#CCCCCC>Acierto — <color=#E69988>rival</color></color>  <color={0}>disparos</color> <color=#888>·</color> <color={1}>aciertos</color>')
  , ('22c8024854c1d08e', 'ru', 'b2d6bc42dea14ebed5a3cdb1d6302871595a1d8b', '<color=#CCCCCC>Попадания — <color=#E69988>соперник</color></color>  <color={0}>выстрелы</color> <color=#888>·</color> <color={1}>попадания</color>')
  , ('7f80629f57a37126', 'es', 'b9e3805cbd8a09cb53f502d1ee059cbe83bfa270', '<color=#CCCCCC>Latencia (ms) durante la partida</color>  <color=#99B3E6>tú</color> <color=#888>vs</color> <color=#E69988>rival</color>')
  , ('7f80629f57a37126', 'ru', 'b9e3805cbd8a09cb53f502d1ee059cbe83bfa270', '<color=#CCCCCC>Задержка (мс) за матч</color>  <color=#99B3E6>ты</color> <color=#888>vs</color> <color=#E69988>соперник</color>')
  , ('e31bb2a57a268bb8', 'es', '1a2d6cafc8df6926eaa128130f8910894b888c8e', '<color=#CCCCCC>Historial de puntos</color>  <color=#66DD66>tú</color> <color=#888>vs</color> <color=#DD7777>rival</color>')
  , ('e31bb2a57a268bb8', 'ru', '1a2d6cafc8df6926eaa128130f8910894b888c8e', '<color=#CCCCCC>История очков</color>  <color=#66DD66>ты</color> <color=#888>vs</color> <color=#DD7777>соперник</color>')
  , ('91796b933251df6c', 'es', '102200e3e75f1f63cb91b136385e50d3b8648dc9', '<color=#EEEEEE>sólido = {0}</color>   <color=#888888>tenue = {1}</color>')
  , ('91796b933251df6c', 'ru', '102200e3e75f1f63cb91b136385e50d3b8648dc9', '<color=#EEEEEE>ярко = {0}</color>   <color=#888888>тускло = {1}</color>')
  , ('87ca1318e268efac', 'es', 'b25566068f7a1de5405117c1faedecb7c5f826a6', '<color={1}>{0}</color> <color=#888>— telemetría de la partida</color>')
  , ('87ca1318e268efac', 'ru', 'b25566068f7a1de5405117c1faedecb7c5f826a6', '<color={1}>{0}</color> <color=#888>— телеметрия матча</color>')
  , ('d7dc886afa083aff', 'es', '6a57dfd4acb6187e4a37477d30874ac5ee9bffb7', 'Tabla de logros')
  , ('d7dc886afa083aff', 'ru', '6a57dfd4acb6187e4a37477d30874ac5ee9bffb7', 'Сетка достижений')
  , ('4b7b3bb3843c5b2a', 'es', '079b57c26436586e5179bd49537d3492f766534d', 'Comparación de logros')
  , ('4b7b3bb3843c5b2a', 'ru', '079b57c26436586e5179bd49537d3492f766534d', 'Сравнение достижений')
  , ('8fff31eb51a2e6ee', 'es', 'a50b9dbf33783b0f870ae078af30d1dd7c756577', 'Logros desbloqueados')
  , ('8fff31eb51a2e6ee', 'ru', 'a50b9dbf33783b0f870ae078af30d1dd7c756577', 'Достижений открыто')
  , ('3c6690dcdecbb716', 'es', '54f2de771fcc83e1f79f766de250ec3b99058fc1', 'FPS medios')
  , ('3c6690dcdecbb716', 'ru', '54f2de771fcc83e1f79f766de250ec3b99058fc1', 'Средний FPS')
  , ('b40fb3b19f66c416', 'es', 'a9cb3b230f62baaa2a50a30ae4021bc185ff4cf7', 'Cartas medias / juego')
  , ('b40fb3b19f66c416', 'ru', 'a9cb3b230f62baaa2a50a30ae4021bc185ff4cf7', 'Ср. карт / игра')
  , ('2c6ddebe063dbd3c', 'es', '3b5cb53623777da9da001e365460faeffffe4707', 'Cartas medias por juego  (menos = más fuerte)')
  , ('2c6ddebe063dbd3c', 'ru', '3b5cb53623777da9da001e365460faeffffe4707', 'Ср. карт за игру  (меньше = сильнее)')
  , ('3c0e4e88889a9d01', 'es', 'a5e9d8eff751109a07f683414c26a66ede6965fe', 'FPS medios')
  , ('3c0e4e88889a9d01', 'ru', 'a5e9d8eff751109a07f683414c26a66ede6965fe', 'Ср. FPS')
  , ('7b00a1e34b238a38', 'es', '733c052b3ccea1ff310008f67ea79002e90d3f23', 'Duración media')
  , ('7b00a1e34b238a38', 'ru', '733c052b3ccea1ff310008f67ea79002e90d3f23', 'Ср. длина игры')
  , ('36cecc4f534c115c', 'es', '478919ec62b4c389cfdf173b807404a7e6536d53', 'Duración media (minutos)')
  , ('36cecc4f534c115c', 'ru', '478919ec62b4c389cfdf173b807404a7e6536d53', 'Ср. длина игры (мин)')
  , ('1d06bcb7ee5096ad', 'es', '1d4a57f5312863f49c410c101712a44f6d8885ac', 'Pulsaciones medias por juego')
  , ('1d06bcb7ee5096ad', 'ru', '1d4a57f5312863f49c410c101712a44f6d8885ac', 'Ср. нажатий за игру')
  , ('32283fc1ea2d3ded', 'es', 'e130f4017b66a9d862b0106b351967a2bce36333', 'Teclas medias por segundo (en combate)')
  , ('32283fc1ea2d3ded', 'ru', 'e130f4017b66a9d862b0106b351967a2bce36333', 'Ср. нажатий в секунду (в бою)')
  , ('f492ecc3e3307ab6', 'es', '0e13a694c06a1734230915e4b3206b568908870c', 'Mejor racha')
  , ('f492ecc3e3307ab6', 'ru', '0e13a694c06a1734230915e4b3206b568908870c', 'Лучший стрик побед')
  , ('61611d5f98241ddd', 'es', '97762f31a5a61b013e1f4eebdfdd835d94ad7923', 'Apuestas gan. / perd.')
  , ('61611d5f98241ddd', 'ru', '97762f31a5a61b013e1f4eebdfdd835d94ad7923', 'Ставки W / L')
  , ('cada077cba6f8b7c', 'es', 'a40dbe4a1c7aebbf45414b3121bea1d5361d57d5', 'Balance de apuestas')
  , ('cada077cba6f8b7c', 'ru', 'a40dbe4a1c7aebbf45414b3121bea1d5361d57d5', 'Итог ставок')
  , ('99ff755f76298b3a', 'es', '82dd2cdf36f9436d89f404454654ad3e53fd428d', 'Bloqueo')
  , ('99ff755f76298b3a', 'ru', '82dd2cdf36f9436d89f404454654ad3e53fd428d', 'Блок')
  , ('a244b647cf231b38', 'es', '22189563e809c4944aac68940714bc157ddcba63', 'Casual (juegos)')
  , ('a244b647cf231b38', 'ru', '22189563e809c4944aac68940714bc157ddcba63', 'Казуал (игры)')
  , ('c15981b970bb074f', 'es', 'c401ce5826bb2f72ec8429df08aa320c18f4c542', 'Cambiar vista')
  , ('c15981b970bb074f', 'ru', 'c401ce5826bb2f72ec8429df08aa320c18f4c542', 'Сменить вид')
  , ('9bfa347dd2ca0c5e', 'es', '7c69fcf1d018fea1b4426ea07fe16464929905a0', 'Chat [{0}]  —  Enter envía, Esc cancela, Shift cambia de canal')
  , ('9bfa347dd2ca0c5e', 'ru', '7c69fcf1d018fea1b4426ea07fe16464929905a0', 'Чат [{0}]  —  Enter — отправить, Esc — отмена, Shift — смена канала')
  , ('014e44ac3404b177', 'es', '7c76a991ae48f6c5f4aaca54f04c3451df0b6050', 'Elo por partidas')
  , ('014e44ac3404b177', 'ru', '7c76a991ae48f6c5f4aaca54f04c3451df0b6050', 'Elo по играм')
  , ('f10f7f8c8bc75fdb', 'es', '00539e5e55904cbf26d075a6f2f7a22533056c61', 'Elo en el tiempo')
  , ('f10f7f8c8bc75fdb', 'ru', '00539e5e55904cbf26d075a6f2f7a22533056c61', 'Elo по времени')
  , ('11e75bf0cc1f9f07', 'es', '649df08a448ee3fa90f3746baaf6b0907df42c91', 'Inglés')
  , ('11e75bf0cc1f9f07', 'ru', '649df08a448ee3fa90f3746baaf6b0907df42c91', 'Английский')
  , ('bf972197bededb7f', 'es', '6839d82e03f5268d9a7cc97802db76c48c8cce6e', 'Dadas')
  , ('bf972197bededb7f', 'ru', '6839d82e03f5268d9a7cc97802db76c48c8cce6e', 'Отдано')
  , ('3f5d0dc0170cb607', 'es', 'ea490aaa629a0704301cf91e7a4910b910278662', 'Acierto')
  , ('3f5d0dc0170cb607', 'ru', 'ea490aaa629a0704301cf91e7a4910b910278662', 'Попадания')
  , ('68ebe98e1a246198', 'es', 'c93d8b77434bdab2d626ebd548390c53fe4108b6', '% Acierto vs % Bloqueo')
  , ('68ebe98e1a246198', 'ru', 'c93d8b77434bdab2d626ebd548390c53fe4108b6', 'Попад. % / Блок %')
  , ('5884139e3a1c369e', 'es', 'bfa62d12f6552fa084e5624db91e8f809cc967fc', 'Acierto/Bloqueo %')
  , ('5884139e3a1c369e', 'ru', 'bfa62d12f6552fa084e5624db91e8f809cc967fc', 'Попад. / Блок %')
  , ('fefd29b7cdc2891d', 'es', '3e766191a84859276c20faa0e8ef0e675f15ce42', 'Teclas / juego')
  , ('fefd29b7cdc2891d', 'ru', '3e766191a84859276c20faa0e8ef0e675f15ce42', 'Клавиш / игра')
  , ('c71afca6cc3af501', 'es', 'd76083989d43f7f7ade72236e5280c68f1313816', 'Teclas / s')
  , ('c71afca6cc3af501', 'ru', 'd76083989d43f7f7ade72236e5280c68f1313816', 'Клавиш / сек')
  , ('dca0e950beda5275', 'es', '1fd2394cf3947091a4cce007bdc3ba63bac85efe', 'Cargando logros...')
  , ('dca0e950beda5275', 'ru', '1fd2394cf3947091a4cce007bdc3ba63bac85efe', 'Загрузка достижений...')
  , ('80c96a889f9f5af9', 'es', '75a7bf994e9ac1b9d14062213673cc0a85729869', 'Perdidas')
  , ('80c96a889f9f5af9', 'ru', '75a7bf994e9ac1b9d14062213673cc0a85729869', 'Проигр.')
  , ('eb598318c184738f', 'es', 'b701924a9d0c728225b76f6f434ef89766a3c2bf', 'No hay datos de logros.')
  , ('eb598318c184738f', 'ru', 'b701924a9d0c728225b76f6f434ef89766a3c2bf', 'Нет данных о достижениях.')
  , ('58c74152577b5c36', 'es', '21c960d176f4b50c4fa7595f1e57dd48dba53808', 'Aún no hay mensajes en este canal.')
  , ('58c74152577b5c36', 'ru', '21c960d176f4b50c4fa7595f1e57dd48dba53808', 'В этом канале пока нет сообщений.')
  , ('c97d35b45f398d79', 'es', '5a581465bae3c00caeb7577b0eba5949d87517a7', 'Pico de Elo')
  , ('c97d35b45f398d79', 'ru', '5a581465bae3c00caeb7577b0eba5949d87517a7', 'Пик Elo')
  , ('6ad9912372f78640', 'es', '749826ec9c02cfbac0274840d905f2c374fab239', 'Ranked (series)')
  , ('6ad9912372f78640', 'ru', '749826ec9c02cfbac0274840d905f2c374fab239', 'Ранкед (серии)')
  , ('389ee87fa2b2226c', 'es', 'ad0e59467721c89f6c98a699c6940779ba22d939', 'Tiempo/región')
  , ('389ee87fa2b2226c', 'ru', 'ad0e59467721c89f6c98a699c6940779ba22d939', 'Регионы')
  , ('f444dd90b18a22de', 'es', 'd3c9dbb10b2776caea1c1e5bca8f578467f17836', 'Distribución por región')
  , ('f444dd90b18a22de', 'ru', 'd3c9dbb10b2776caea1c1e5bca8f578467f17836', 'Распределение регионов')
  , ('4e1a7e002aa898fb', 'es', '653473b68ffd7d51aa82c742fe125934177dd762', 'Elige jugadores (izquierda) para graficar {0}.')
  , ('4e1a7e002aa898fb', 'ru', '653473b68ffd7d51aa82c742fe125934177dd762', 'Выбери игроков слева, чтобы построить {0}.')
  , ('59f6bde0a7f60351', 'es', '1175545bb73a476b0d1a87051cb90a94ed11cc7e', 'Elige jugadores (izquierda) para comparar {0}.')
  , ('59f6bde0a7f60351', 'ru', '1175545bb73a476b0d1a87051cb90a94ed11cc7e', 'Выбери игроков слева, чтобы сравнить {0}.')
  , ('f51760d7b4a0ccaf', 'es', '757692270a6215efdebe1d9ef46bef9c6c10f012', 'Elegidos {0}/{1}  -  clic en un jugador para añadir/quitar')
  , ('f51760d7b4a0ccaf', 'ru', '757692270a6215efdebe1d9ef46bef9c6c10f012', 'Выбрано {0}/{1}  -  клик по игроку: добавить/убрать')
  , ('48aac4d36fe4eab8', 'es', 'bc2c02ad63ef5932a9bfb803d1d3de1db0bc9cd4', 'Viendo: {0}')
  , ('48aac4d36fe4eab8', 'ru', 'bc2c02ad63ef5932a9bfb803d1d3de1db0bc9cd4', 'Показано: {0}')
  , ('1d473e51fc884c2a', 'es', 'c66c12b98882a2c74600f15115c65f693c8d5f34', 'Recibidas')
  , ('1d473e51fc884c2a', 'ru', 'c66c12b98882a2c74600f15115c65f693c8d5f34', 'Получено')
  , ('e56a017d8db3c1c0', 'es', '48acb7066a69a96da3b4f6d5b775f433ce711dfd', 'Cartas top')
  , ('e56a017d8db3c1c0', 'ru', '48acb7066a69a96da3b4f6d5b775f433ce711dfd', 'Топ карт')
  , ('7c40182849a2b50d', 'es', '2bcded4477fbc29b2189244d26662a863ff2e0e2', 'Mejores rachas')
  , ('7c40182849a2b50d', 'ru', '2bcded4477fbc29b2189244d26662a863ff2e0e2', 'Топ стриков')
  , ('4829edfbd8946d0c', 'es', 'de22faa36e05c70dc66d022852845a823e484fe8', 'XP total')
  , ('4829edfbd8946d0c', 'ru', 'de22faa36e05c70dc66d022852845a823e484fe8', 'Всего XP')
  , ('248b6c3c08e4d317', 'es', '6f038cc9011f8772486e3ecf9af8265a33c6594a', 'Canal de escritura')
  , ('248b6c3c08e4d317', 'ru', '6f038cc9011f8772486e3ecf9af8265a33c6594a', 'Канал отправки')
  , ('0069145ee858ce98', 'es', 'd7bbf1714096fcd5ce093d851b29e2b07062e0ce', 'Escribiendo: {0}  (Shift cambia)')
  , ('0069145ee858ce98', 'ru', 'd7bbf1714096fcd5ce093d851b29e2b07062e0ce', 'Пишу в: {0}  (Shift — сменить)')
  , ('9566e3ebe6920019', 'es', '3cf575503d0141f8791e89998e508076168963e3', 'Canal de lectura')
  , ('9566e3ebe6920019', 'ru', '3cf575503d0141f8791e89998e508076168963e3', 'Канал просмотра')
  , ('d4409b54016af376', 'es', 'b1b05687ebbfc658992e07a3906848c0791945fe', 'Viendo: {0}  <color=#888>(pulsa T para chatear)</color>')
  , ('d4409b54016af376', 'ru', 'b1b05687ebbfc658992e07a3906848c0791945fe', 'Смотрю: {0}  <color=#888>(нажми T для чата)</color>')
  , ('2a302e5baecea9de', 'es', 'b273fb28770817940a8c1ea6a33b69274996a898', 'Ganadas')
  , ('2a302e5baecea9de', 'ru', 'b273fb28770817940a8c1ea6a33b69274996a898', 'Выигр.')
  , ('3a86a25f6f851f48', 'es', '7f1deb6a2004a9be435217ff05ec93fbbbabd6e8', 'Peores cartas')
  , ('3a86a25f6f851f48', 'ru', '7f1deb6a2004a9be435217ff05ec93fbbbabd6e8', 'Худшие карты')
  , ('2ab0436083a67623', 'es', '8d35ca7e43221d036bad3a81a6356555ee61ba8f', 'juegos ->')
  , ('2ab0436083a67623', 'ru', '8d35ca7e43221d036bad3a81a6356555ee61ba8f', 'игры ->')
  , ('eba3826ea7d1aee5', 'es', '4d968a30a022f41e9826f0cf09d36c2b6a22bfa4', 'sin datos')
  , ('eba3826ea7d1aee5', 'ru', '4d968a30a022f41e9826f0cf09d36c2b6a22bfa4', 'нет данных')
  , ('6e609efa1850f406', 'es', 'b812a48694a85178a169e0758e8e3d81298192fc', 'datos insuficientes (4+ elecciones)')
  , ('6e609efa1850f406', 'ru', 'b812a48694a85178a169e0758e8e3d81298192fc', 'мало данных (4+ выбора)')
  , ('efc2f9902bbd8f88', 'es', '921f739afc4507740d70462d75a775f0b1de78a3', 'Nv {0}')
  , ('efc2f9902bbd8f88', 'ru', '921f739afc4507740d70462d75a775f0b1de78a3', 'Ур {0}')
  , ('8f901a543698298d', 'es', 'fe604db7833da029b6d91b9e285ed91762c30526', 'Max. {0} jugadores')
  , ('8f901a543698298d', 'ru', 'fe604db7833da029b6d91b9e285ed91762c30526', 'Макс. {0} игроков')
  , ('83036a2c18f9f131', 'es', '8fff039853f5c2bbb8a28d056b579c7dcb7d137f', 'SI')
  , ('83036a2c18f9f131', 'ru', '8fff039853f5c2bbb8a28d056b579c7dcb7d137f', 'ДА')
  , ('568bed8b059b93ef', 'es', '3865e6152a8c60511725d508e1493e63c71e47c3', 'sin datos de cartas')
  , ('568bed8b059b93ef', 'ru', '3865e6152a8c60511725d508e1493e63c71e47c3', 'нет данных о картах')
  , ('ec3284a5904bb9a1', 'es', '8941784e7b51bc9575c6ad7277d273019630104a', 'vs {0}')
  , ('ec3284a5904bb9a1', 'ru', '8941784e7b51bc9575c6ad7277d273019630104a', 'против {0}')
  , ('d20bb0a584961c1a', 'es', '4b6ebac7f834ce8bb4f4d9fb1155b902d4dac0ce', 'con {0}')
  , ('d20bb0a584961c1a', 'ru', '4b6ebac7f834ce8bb4f4d9fb1155b902d4dac0ce', 'с {0}')
  , ('b51b794698a1cd64', 'es', '96d510eecdc8dec60e5e9065d67fb5b7cfb4f49c', 'con {0}   vs {1}')
  , ('b51b794698a1cd64', 'ru', '96d510eecdc8dec60e5e9065d67fb5b7cfb4f49c', 'с {0}   против {1}')
  , ('f0607d4b143a64b0', 'es', '34a21e05c30ded2a040b26c49002ff123c162768', 'Texto de menu mas grueso: <color=#88FF88>SI</color>')
  , ('f0607d4b143a64b0', 'ru', '34a21e05c30ded2a040b26c49002ff123c162768', 'Более жирный текст меню: <color=#88FF88>ВКЛ</color>')
  , ('b4d0bf3130aeccad', 'es', '5898784be18a6aba413074e338d99a93783068ef', 'Texto de menu mas grueso: <color=#FF9966>NO</color>')
  , ('b4d0bf3130aeccad', 'ru', '5898784be18a6aba413074e338d99a93783068ef', 'Более жирный текст меню: <color=#FF9966>ВЫКЛ</color>')
  , ('f235df555d002514', 'es', 'e2c34a89258190d36f1eb34cb0743e6fea492528', 'Texto de menu mas grueso. Usa la fuente del propio juego con mas peso, no otra tipografia.')
  , ('f235df555d002514', 'ru', 'e2c34a89258190d36f1eb34cb0743e6fea492528', 'Более жирный текст меню. Тот же шрифт игры, только толще — не другая гарнитура.')
  , ('2384a8ba24996fe6', 'es', 'c02329c48f348eb633688f33c499b18b31dcb947', 'Conceder')
  , ('2384a8ba24996fe6', 'ru', 'c02329c48f348eb633688f33c499b18b31dcb947', 'Выдать')
  , ('1d8bfec2606b8964', 'es', '6c9c8a13e709141fe143390523f4e2389a800362', 'Conceder rol de traduccion - busca al jugador')
  , ('1d8bfec2606b8964', 'ru', '6c9c8a13e709141fe143390523f4e2389a800362', 'Выдать роль переводчика — найдите игрока')
  , ('72227ce31f4e8e6c', 'es', '0be720759ff04d13c5706881d5d227a2621f91a6', 'Revocar')
  , ('72227ce31f4e8e6c', 'ru', '0be720759ff04d13c5706881d5d227a2621f91a6', 'Отозвать')
  , ('46fe5bdea432ddc2', 'es', 'd609539d8e0863475418b15564c55edfe9667fb6', 'Que rol de traduccion revocar?')
  , ('46fe5bdea432ddc2', 'ru', 'd609539d8e0863475418b15564c55edfe9667fb6', 'Какую роль переводчика отозвать?')
  , ('b5e4bc86afedf812', 'es', '68708e68355c1424ba1010b04a7d02bbf94ac448', 'Rol de traduccion revocado.')
  , ('b5e4bc86afedf812', 'ru', '68708e68355c1424ba1010b04a7d02bbf94ac448', 'Роль переводчика отозвана.')
  , ('48ab37a3b4f0c7b3', 'es', '8f6f68e46a3e45f48d74027000b9b28312ed6fe1', 'Que idioma para {0}?')
  , ('48ab37a3b4f0c7b3', 'ru', '8f6f68e46a3e45f48d74027000b9b28312ed6fe1', 'Какой язык для {0}?')
  , ('aba91628ab0e4069', 'es', '352e94ec0f7361050981402124252d03ad906990', '{0} ya puede traducir {1}.')
  , ('aba91628ab0e4069', 'ru', '352e94ec0f7361050981402124252d03ad906990', '{0} теперь может переводить {1}.')
  , ('6f684f202dcec6e0', 'es', 'cd357517fe20e286565b56385f12c4c3af9c4563', 'Dar traductor...')
  , ('6f684f202dcec6e0', 'ru', 'cd357517fe20e286565b56385f12c4c3af9c4563', 'Выдать переводчика...')
  , ('216f8c7dad3b04b0', 'es', '5505effc85240d0187d0a19a306e36e6f38da3e7', 'Quitar traductor...')
  , ('216f8c7dad3b04b0', 'ru', '5505effc85240d0187d0a19a306e36e6f38da3e7', 'Отозвать переводчика...')
  , ('2de3a943a045ca65', 'es', '019b92f53aad498f211a0607a94d18c8a47d2041', 'Doble KO - nadie puntuó esta ronda.')
  , ('2de3a943a045ca65', 'ru', '019b92f53aad498f211a0607a94d18c8a47d2041', 'Двойной КО — очко не присуждено.')
  ) AS v(key_id, lang, source_hash, target)
  JOIN i18n_keys k ON k.key_id = v.key_id AND k.retired_at IS NULL
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
DECLARE want INT := 188; got INT;
BEGIN
  -- Count only THIS wave's pairs, on keys that are live: a pair whose key has
  -- since retired is not missing work, and counting every sentinel seed ever
  -- made would silently pass on 184's rows alone.
  SELECT COUNT(*) INTO got FROM (
    SELECT DISTINCT p.key_id, p.language_code
      FROM i18n_proposals p
      JOIN i18n_keys k2 ON k2.key_id = p.key_id AND k2.retired_at IS NULL
     WHERE p.proposer_steam_id = 'claude-mt'
       AND (p.key_id, p.language_code) IN (('cae733acdf0cbe30','es'), ('cae733acdf0cbe30','ru'), ('8bcb3efd4061dec8','es'), ('8bcb3efd4061dec8','ru'), ('e76f8724d967828e','es'), ('e76f8724d967828e','ru'), ('fdbd0ecf1244c020','es'), ('fdbd0ecf1244c020','ru'), ('5eff08c9ac85a416','es'), ('5eff08c9ac85a416','ru'), ('44a9ae7c639fd2e4','es'), ('44a9ae7c639fd2e4','ru'), ('cf1c3f9f78d8e96b','es'), ('cf1c3f9f78d8e96b','ru'), ('21e8b9f068f73353','es'), ('21e8b9f068f73353','ru'), ('503299a3e558e34f','es'), ('503299a3e558e34f','ru'), ('65d7670c7a57530a','es'), ('65d7670c7a57530a','ru'), ('0bef6893b50362d8','es'), ('0bef6893b50362d8','ru'), ('05347a04a3a75031','es'), ('05347a04a3a75031','ru'), ('d561d401c70c4984','es'), ('d561d401c70c4984','ru'), ('4f800bc0a79049a7','es'), ('4f800bc0a79049a7','ru'), ('d9c7e321f2f94b4d','es'), ('d9c7e321f2f94b4d','ru'), ('cf5674f2c394e9f5','es'), ('cf5674f2c394e9f5','ru'), ('bdab91b8c8fb2d0d','es'), ('bdab91b8c8fb2d0d','ru'), ('22c8024854c1d08e','es'), ('22c8024854c1d08e','ru'), ('7f80629f57a37126','es'), ('7f80629f57a37126','ru'), ('e31bb2a57a268bb8','es'), ('e31bb2a57a268bb8','ru'), ('91796b933251df6c','es'), ('91796b933251df6c','ru'), ('87ca1318e268efac','es'), ('87ca1318e268efac','ru'), ('d7dc886afa083aff','es'), ('d7dc886afa083aff','ru'), ('4b7b3bb3843c5b2a','es'), ('4b7b3bb3843c5b2a','ru'), ('8fff31eb51a2e6ee','es'), ('8fff31eb51a2e6ee','ru'), ('3c6690dcdecbb716','es'), ('3c6690dcdecbb716','ru'), ('b40fb3b19f66c416','es'), ('b40fb3b19f66c416','ru'), ('2c6ddebe063dbd3c','es'), ('2c6ddebe063dbd3c','ru'), ('3c0e4e88889a9d01','es'), ('3c0e4e88889a9d01','ru'), ('7b00a1e34b238a38','es'), ('7b00a1e34b238a38','ru'), ('36cecc4f534c115c','es'), ('36cecc4f534c115c','ru'), ('1d06bcb7ee5096ad','es'), ('1d06bcb7ee5096ad','ru'), ('32283fc1ea2d3ded','es'), ('32283fc1ea2d3ded','ru'), ('f492ecc3e3307ab6','es'), ('f492ecc3e3307ab6','ru'), ('61611d5f98241ddd','es'), ('61611d5f98241ddd','ru'), ('cada077cba6f8b7c','es'), ('cada077cba6f8b7c','ru'), ('99ff755f76298b3a','es'), ('99ff755f76298b3a','ru'), ('a244b647cf231b38','es'), ('a244b647cf231b38','ru'), ('c15981b970bb074f','es'), ('c15981b970bb074f','ru'), ('9bfa347dd2ca0c5e','es'), ('9bfa347dd2ca0c5e','ru'), ('014e44ac3404b177','es'), ('014e44ac3404b177','ru'), ('f10f7f8c8bc75fdb','es'), ('f10f7f8c8bc75fdb','ru'), ('11e75bf0cc1f9f07','es'), ('11e75bf0cc1f9f07','ru'), ('bf972197bededb7f','es'), ('bf972197bededb7f','ru'), ('3f5d0dc0170cb607','es'), ('3f5d0dc0170cb607','ru'), ('68ebe98e1a246198','es'), ('68ebe98e1a246198','ru'), ('5884139e3a1c369e','es'), ('5884139e3a1c369e','ru'), ('fefd29b7cdc2891d','es'), ('fefd29b7cdc2891d','ru'), ('c71afca6cc3af501','es'), ('c71afca6cc3af501','ru'), ('dca0e950beda5275','es'), ('dca0e950beda5275','ru'), ('80c96a889f9f5af9','es'), ('80c96a889f9f5af9','ru'), ('eb598318c184738f','es'), ('eb598318c184738f','ru'), ('58c74152577b5c36','es'), ('58c74152577b5c36','ru'), ('c97d35b45f398d79','es'), ('c97d35b45f398d79','ru'), ('6ad9912372f78640','es'), ('6ad9912372f78640','ru'), ('389ee87fa2b2226c','es'), ('389ee87fa2b2226c','ru'), ('f444dd90b18a22de','es'), ('f444dd90b18a22de','ru'), ('4e1a7e002aa898fb','es'), ('4e1a7e002aa898fb','ru'), ('59f6bde0a7f60351','es'), ('59f6bde0a7f60351','ru'), ('f51760d7b4a0ccaf','es'), ('f51760d7b4a0ccaf','ru'), ('48aac4d36fe4eab8','es'), ('48aac4d36fe4eab8','ru'), ('1d473e51fc884c2a','es'), ('1d473e51fc884c2a','ru'), ('e56a017d8db3c1c0','es'), ('e56a017d8db3c1c0','ru'), ('7c40182849a2b50d','es'), ('7c40182849a2b50d','ru'), ('4829edfbd8946d0c','es'), ('4829edfbd8946d0c','ru'), ('248b6c3c08e4d317','es'), ('248b6c3c08e4d317','ru'), ('0069145ee858ce98','es'), ('0069145ee858ce98','ru'), ('9566e3ebe6920019','es'), ('9566e3ebe6920019','ru'), ('d4409b54016af376','es'), ('d4409b54016af376','ru'), ('2a302e5baecea9de','es'), ('2a302e5baecea9de','ru'), ('3a86a25f6f851f48','es'), ('3a86a25f6f851f48','ru'), ('2ab0436083a67623','es'), ('2ab0436083a67623','ru'), ('eba3826ea7d1aee5','es'), ('eba3826ea7d1aee5','ru'), ('6e609efa1850f406','es'), ('6e609efa1850f406','ru'), ('efc2f9902bbd8f88','es'), ('efc2f9902bbd8f88','ru'), ('8f901a543698298d','es'), ('8f901a543698298d','ru'), ('83036a2c18f9f131','es'), ('83036a2c18f9f131','ru'), ('568bed8b059b93ef','es'), ('568bed8b059b93ef','ru'), ('ec3284a5904bb9a1','es'), ('ec3284a5904bb9a1','ru'), ('d20bb0a584961c1a','es'), ('d20bb0a584961c1a','ru'), ('b51b794698a1cd64','es'), ('b51b794698a1cd64','ru'), ('f0607d4b143a64b0','es'), ('f0607d4b143a64b0','ru'), ('b4d0bf3130aeccad','es'), ('b4d0bf3130aeccad','ru'), ('f235df555d002514','es'), ('f235df555d002514','ru'), ('2384a8ba24996fe6','es'), ('2384a8ba24996fe6','ru'), ('1d8bfec2606b8964','es'), ('1d8bfec2606b8964','ru'), ('72227ce31f4e8e6c','es'), ('72227ce31f4e8e6c','ru'), ('46fe5bdea432ddc2','es'), ('46fe5bdea432ddc2','ru'), ('b5e4bc86afedf812','es'), ('b5e4bc86afedf812','ru'), ('48ab37a3b4f0c7b3','es'), ('48ab37a3b4f0c7b3','ru'), ('aba91628ab0e4069','es'), ('aba91628ab0e4069','ru'), ('6f684f202dcec6e0','es'), ('6f684f202dcec6e0','ru'), ('216f8c7dad3b04b0','es'), ('216f8c7dad3b04b0','ru'), ('2de3a943a045ca65','es'), ('2de3a943a045ca65','ru'))) s;
  RAISE NOTICE 'migration 189: % of % wave-2 seed pairs present', got, want;
  IF got < want THEN
    RAISE NOTICE 'migration 189: % MISSING - run tools/i18n_sync_keys.py, then re-run this file', want - got;
  END IF;
END $$;
