-- 249_seed_machine_translations_v1392.sql
--
-- Machine-translated proposal seeds (es/ru/uk/sv) for the 53 client keys
-- bundled for v1.39.2: the night-pack map skins + gradient name styles
-- (migration 246), the five community cosmetics released in 247, and the
-- v1.39.1 cosmetics' shop strings that had never been synced.
--
-- Same contract as 184/189/213/223/239: PENDING proposals only, sentinel
-- proposer 'claude-mt', license_assent TRUE at the machine-translation
-- terms revision. The same 212 translations ship BUNDLED in
-- I18nCatalogues.cs, so the client renders them without any approval; these
-- proposals exist so human translators can see/refine them through the
-- portal (an approval then overrides the bundled value via the pack overlay).
--
-- ORDERING: seeds only keys already present in i18n_keys — migration 248
-- inserted them (this seat's AdminSecret cannot run tools/i18n_sync_keys.py,
-- #406). On a database without 248 the assertion below RAISEs and the
-- transaction rolls back. Explicit BEGIN/COMMIT (#340); every statement is
-- idempotent for the wrapper's || re-run (#243).
BEGIN;

CREATE TEMP TABLE _seed249 (
  key_id      VARCHAR(16) NOT NULL,
  lang        VARCHAR(8)  NOT NULL,
  source_hash VARCHAR(40) NOT NULL,
  target      TEXT        NOT NULL
) ON COMMIT DROP;

INSERT INTO _seed249 (key_id, lang, source_hash, target) VALUES
  ('5c299cdd5181a941', 'es', 'fbc862283106c3ad11970e3d7528cb421283e2e5', 'Una boquita graciosa para los amantes de los felinos')
  , ('5c299cdd5181a941', 'ru', 'fbc862283106c3ad11970e3d7528cb421283e2e5', 'Забавный ротик для любителей кошачьих')
  , ('5c299cdd5181a941', 'uk', 'fbc862283106c3ad11970e3d7528cb421283e2e5', 'Кумедний ротик для шанувальників котячих')
  , ('5c299cdd5181a941', 'sv', 'fbc862283106c3ad11970e3d7528cb421283e2e5', 'En fånig liten mun för kattentusiaster')
  , ('1b3f3ff1f8bc538e', 'es', 'ac1861b407332050c7ad8ece653fde7c0a2885e5', 'Degradado ceniza')
  , ('1b3f3ff1f8bc538e', 'ru', 'ac1861b407332050c7ad8ece653fde7c0a2885e5', 'Градиент: пепел')
  , ('1b3f3ff1f8bc538e', 'uk', 'ac1861b407332050c7ad8ece653fde7c0a2885e5', 'Градієнт: попіл')
  , ('1b3f3ff1f8bc538e', 'sv', 'ac1861b407332050c7ad8ece653fde7c0a2885e5', 'Askgradient')
  , ('511b49694beadfab', 'es', '6f2d396e557b5f76d31e56571112c890b8ee7430', 'Paredes de ceniza con un acento carmesí oscuro sobre una oscuridad rojo sangre profundo, con brasas rojas ascendiendo.')
  , ('511b49694beadfab', 'ru', '6f2d396e557b5f76d31e56571112c890b8ee7430', 'Пепельные стены с тёмно-багровым акцентом на фоне глубокой кроваво-красной тьмы, вверх поднимаются красные угольки.')
  , ('511b49694beadfab', 'uk', '6f2d396e557b5f76d31e56571112c890b8ee7430', 'Попелясті стіни з темно-багряним акцентом на тлі глибокої криваво-червоної темряви, вгору здіймаються червоні жаринки.')
  , ('511b49694beadfab', 'sv', '6f2d396e557b5f76d31e56571112c890b8ee7430', 'Askgrå väggar med en mörk karmosinröd accent över ett djupt blodrött mörker, med röd glöd som stiger.')
  , ('84e17af7112e2c2c', 'es', '03cb2764ec60add600368e21f4fdda7ea811af9f', 'Degradado sangre')
  , ('84e17af7112e2c2c', 'ru', '03cb2764ec60add600368e21f4fdda7ea811af9f', 'Градиент: кровь')
  , ('84e17af7112e2c2c', 'uk', '03cb2764ec60add600368e21f4fdda7ea811af9f', 'Градієнт: кров')
  , ('84e17af7112e2c2c', 'sv', '03cb2764ec60add600368e21f4fdda7ea811af9f', 'Blodgradient')
  , ('e0c347af1c2e8c45', 'es', 'a5c48a631fa6ac8b9e71d1b9a78e93f88f013c43', 'Luna de sangre')
  , ('e0c347af1c2e8c45', 'ru', 'a5c48a631fa6ac8b9e71d1b9a78e93f88f013c43', 'Кровавая луна')
  , ('e0c347af1c2e8c45', 'uk', 'a5c48a631fa6ac8b9e71d1b9a78e93f88f013c43', 'Кривавий місяць')
  , ('e0c347af1c2e8c45', 'sv', 'a5c48a631fa6ac8b9e71d1b9a78e93f88f013c43', 'Blodmåne')
  , ('38ae3616902f9e47', 'es', '527774087ad99d4cbf98e04c8c027506f3dfaa89', 'Ojos de gato')
  , ('38ae3616902f9e47', 'ru', '527774087ad99d4cbf98e04c8c027506f3dfaa89', 'Кошачьи глаза')
  , ('38ae3616902f9e47', 'uk', '527774087ad99d4cbf98e04c8c027506f3dfaa89', 'Котячі очі')
  , ('38ae3616902f9e47', 'sv', '527774087ad99d4cbf98e04c8c027506f3dfaa89', 'Kattögon')
  , ('bb044ac5a0ad150f', 'es', '8ca39fdb3e24dc0164815c29c778320c3477b994', 'Boca de gato')
  , ('bb044ac5a0ad150f', 'ru', '8ca39fdb3e24dc0164815c29c778320c3477b994', 'Кошачий рот')
  , ('bb044ac5a0ad150f', 'uk', '8ca39fdb3e24dc0164815c29c778320c3477b994', 'Котячий рот')
  , ('bb044ac5a0ad150f', 'sv', '8ca39fdb3e24dc0164815c29c778320c3477b994', 'Kattmun')
  , ('e8d68fce3701fe2e', 'es', '0da332b305a132002eabd6a4d3b1dade76c79582', 'Paredes carbón bordeadas de ámbar de corona sobre un cielo negro absoluto.')
  , ('e8d68fce3701fe2e', 'ru', '0da332b305a132002eabd6a4d3b1dade76c79582', 'Угольные стены с янтарной каймой короны на абсолютно чёрном небе.')
  , ('e8d68fce3701fe2e', 'uk', '0da332b305a132002eabd6a4d3b1dade76c79582', 'Вугільні стіни з бурштиновою облямівкою корони на абсолютно чорному небі.')
  , ('e8d68fce3701fe2e', 'sv', '0da332b305a132002eabd6a4d3b1dade76c79582', 'Kolsvarta väggar kantade med koronabärnsten mot en helt svart himmel.')
  , ('d4ffe97d52355fb3', 'es', 'b4816f88de2979e10fa5707a46a4176b09682f23', 'Paredes de ceniza oscura con un acento rosa plateado pálido sobre una noche rojo profundo, con un leve destello rojo.')
  , ('d4ffe97d52355fb3', 'ru', 'b4816f88de2979e10fa5707a46a4176b09682f23', 'Тёмно-пепельные стены с бледным розово-серебристым акцентом на фоне глубокой красной ночи, с едва заметным красным мерцанием.')
  , ('d4ffe97d52355fb3', 'uk', 'b4816f88de2979e10fa5707a46a4176b09682f23', 'Темно-попелясті стіни з блідим рожево-сріблястим акцентом на тлі глибокої червоної ночі, з ледь помітним червоним мерехтінням.')
  , ('d4ffe97d52355fb3', 'sv', 'b4816f88de2979e10fa5707a46a4176b09682f23', 'Mörka askväggar med en blek rosa-silveraccent över en djupröd natt, med ett svagt rött glitter.')
  , ('a9aa7dd7e345eacb', 'es', 'eef8bc1daff28c5ee9b334003283b6ce9b14141b', 'Paredes índigo oscuro sobre el fondo negro más puro del catálogo.')
  , ('a9aa7dd7e345eacb', 'ru', 'eef8bc1daff28c5ee9b334003283b6ce9b14141b', 'Тёмно-индиговые стены на самом чистом чёрном фоне в каталоге.')
  , ('a9aa7dd7e345eacb', 'uk', 'eef8bc1daff28c5ee9b334003283b6ce9b14141b', 'Темно-індигові стіни на найчистішому чорному тлі в каталозі.')
  , ('a9aa7dd7e345eacb', 'sv', 'eef8bc1daff28c5ee9b334003283b6ce9b14141b', 'Mörka indigoväggar mot den renaste svarta bakgrunden i katalogen.')
  , ('0b90ace75370115b', 'es', 'cc83269496c01ca47b98e106203958dcc350fa97', 'Paredes de acero oscuro con el brillo ámbar de las ventanas sobre un cielo azul marino casi negro, con luces de ciudad titilando al fondo.')
  , ('0b90ace75370115b', 'ru', 'cc83269496c01ca47b98e106203958dcc350fa97', 'Стены из тёмной стали с янтарным светом окон на чёрно-синем небе, позади мерцают огни города.')
  , ('0b90ace75370115b', 'uk', 'cc83269496c01ca47b98e106203958dcc350fa97', 'Стіни з темної сталі з бурштиновим світлом вікон на чорно-синьому небі, позаду мерехтять вогні міста.')
  , ('0b90ace75370115b', 'sv', 'cc83269496c01ca47b98e106203958dcc350fa97', 'Mörka stålväggar med bärnstensfärgat fönsterljus mot en svartblå himmel, med stadsljus som blinkar bakom.')
  , ('730802fcc588b2ac', 'es', 'e2cf54d378b402a3681ccc88f012f93dd28b5de5', 'Setos verde profundo y paredes marrón corteza en una noche marrón oscura.')
  , ('730802fcc588b2ac', 'ru', 'e2cf54d378b402a3681ccc88f012f93dd28b5de5', 'Тёмно-зелёные изгороди и стены цвета коры в тёмно-коричневой ночи.')
  , ('730802fcc588b2ac', 'uk', 'e2cf54d378b402a3681ccc88f012f93dd28b5de5', 'Темно-зелені живоплоти та стіни кольору кори в темно-коричневій ночі.')
  , ('730802fcc588b2ac', 'sv', 'e2cf54d378b402a3681ccc88f012f93dd28b5de5', 'Djupgröna häckar och barkbruna väggar i en mörkbrun natt.')
  , ('75eccff6b3ce7be0', 'es', '8f963207651b6b17c88011cc9a1cf5016ff08143', 'Degradado tierra')
  , ('75eccff6b3ce7be0', 'ru', '8f963207651b6b17c88011cc9a1cf5016ff08143', 'Градиент: земля')
  , ('75eccff6b3ce7be0', 'uk', '8f963207651b6b17c88011cc9a1cf5016ff08143', 'Градієнт: земля')
  , ('75eccff6b3ce7be0', 'sv', '8f963207651b6b17c88011cc9a1cf5016ff08143', 'Jordgradient')
  , ('52eb10fe5a54bd85', 'es', '45fc6c80b5f40c599a9996e4565f6c3c0441f578', 'Eclipse')
  , ('52eb10fe5a54bd85', 'ru', '45fc6c80b5f40c599a9996e4565f6c3c0441f578', 'Затмение')
  , ('52eb10fe5a54bd85', 'uk', '45fc6c80b5f40c599a9996e4565f6c3c0441f578', 'Затемнення')
  , ('52eb10fe5a54bd85', 'sv', '45fc6c80b5f40c599a9996e4565f6c3c0441f578', 'Förmörkelse')
  , ('9922fbe350152757', 'es', 'a58ad4865dc2d5fdf3c26319e1ec8c4619cf3819', 'Degradado esmeralda')
  , ('9922fbe350152757', 'ru', 'a58ad4865dc2d5fdf3c26319e1ec8c4619cf3819', 'Градиент: изумруд')
  , ('9922fbe350152757', 'uk', 'a58ad4865dc2d5fdf3c26319e1ec8c4619cf3819', 'Градієнт: смарагд')
  , ('9922fbe350152757', 'sv', 'a58ad4865dc2d5fdf3c26319e1ec8c4619cf3819', 'Smaragdgradient')
  , ('cdac92171e43b9bf', 'es', 'c547d9751e2e1075a2d5db9846f7bd630adf98ce', 'Degradado desvanecido')
  , ('cdac92171e43b9bf', 'ru', 'c547d9751e2e1075a2d5db9846f7bd630adf98ce', 'Градиент: затухание')
  , ('cdac92171e43b9bf', 'uk', 'c547d9751e2e1075a2d5db9846f7bd630adf98ce', 'Градієнт: згасання')
  , ('cdac92171e43b9bf', 'sv', 'c547d9751e2e1075a2d5db9846f7bd630adf98ce', 'Tonad gradient')
  , ('7c8d1536eb0fd36a', 'es', '95f3d46ddbd9f0400b8e07572a25f0f6dc0d6fc9', 'Para los más payasos. Ocupa la ranura de boca.')
  , ('7c8d1536eb0fd36a', 'ru', '95f3d46ddbd9f0400b8e07572a25f0f6dc0d6fc9', 'Для самых дурашливых. Занимает слот рта.')
  , ('7c8d1536eb0fd36a', 'uk', '95f3d46ddbd9f0400b8e07572a25f0f6dc0d6fc9', 'Для найбільших дурників. Займає слот рота.')
  , ('7c8d1536eb0fd36a', 'sv', '95f3d46ddbd9f0400b8e07572a25f0f6dc0d6fc9', 'För de fåniga. Tar upp munplatsen.')
  , ('8586bec2443a2aa0', 'es', 'b22b408fe071ebbc3d1087b8f7009a9a237ebcf6', 'Incendio forestal')
  , ('8586bec2443a2aa0', 'ru', 'b22b408fe071ebbc3d1087b8f7009a9a237ebcf6', 'Лесной пожар')
  , ('8586bec2443a2aa0', 'uk', 'b22b408fe071ebbc3d1087b8f7009a9a237ebcf6', 'Лісова пожежа')
  , ('8586bec2443a2aa0', 'sv', 'b22b408fe071ebbc3d1087b8f7009a9a237ebcf6', 'Skogsbrand')
  , ('17c00df433739b35', 'es', '5ab5f51856f65ede67445fa3f1e37faeff8c86d8', 'Bobalicón')
  , ('17c00df433739b35', 'ru', '5ab5f51856f65ede67445fa3f1e37faeff8c86d8', 'Чудик')
  , ('17c00df433739b35', 'uk', '5ab5f51856f65ede67445fa3f1e37faeff8c86d8', 'Дивак')
  , ('17c00df433739b35', 'sv', '5ab5f51856f65ede67445fa3f1e37faeff8c86d8', 'Tokstolle')
  , ('d453de367dadaf91', 'es', '558287ddcc3557b09ec00ca17b3e4be7e6645858', 'Medianoche')
  , ('d453de367dadaf91', 'ru', '558287ddcc3557b09ec00ca17b3e4be7e6645858', 'Полночь')
  , ('d453de367dadaf91', 'uk', '558287ddcc3557b09ec00ca17b3e4be7e6645858', 'Північ')
  , ('d453de367dadaf91', 'sv', '558287ddcc3557b09ec00ca17b3e4be7e6645858', 'Midnatt')
  , ('5d29024a4d44289a', 'es', '3568c7491babebb953c769947cc8f490da802f47', 'Luz de luna')
  , ('5d29024a4d44289a', 'ru', '3568c7491babebb953c769947cc8f490da802f47', 'Лунный свет')
  , ('5d29024a4d44289a', 'uk', '3568c7491babebb953c769947cc8f490da802f47', 'Місячне сяйво')
  , ('5d29024a4d44289a', 'sv', '3568c7491babebb953c769947cc8f490da802f47', 'Månsken')
  , ('41f8d6df2156cb5a', 'es', '101288b594e03b935789b8a597f09d42680fa7d0', 'Ciudad nocturna')
  , ('41f8d6df2156cb5a', 'ru', '101288b594e03b935789b8a597f09d42680fa7d0', 'Ночной город')
  , ('41f8d6df2156cb5a', 'uk', '101288b594e03b935789b8a597f09d42680fa7d0', 'Нічне місто')
  , ('41f8d6df2156cb5a', 'sv', '101288b594e03b935789b8a597f09d42680fa7d0', 'Nattstad')
  , ('f8387a7add74f327', 'es', 'd6c0ceed4033b33fc562d60d9b914946e813d9b7', 'Parque nocturno')
  , ('f8387a7add74f327', 'ru', 'd6c0ceed4033b33fc562d60d9b914946e813d9b7', 'Ночной парк')
  , ('f8387a7add74f327', 'uk', 'd6c0ceed4033b33fc562d60d9b914946e813d9b7', 'Нічний парк')
  , ('f8387a7add74f327', 'sv', 'd6c0ceed4033b33fc562d60d9b914946e813d9b7', 'Nattpark')
  , ('8dc459eeaa15acb6', 'es', '22584937a4a8382e23a56fbd261ae0dbda2c028a', 'Paredes verde bosque nocturno y corteza bajo un cielo oscuro y humeante, con brasas que ascienden por el fondo.')
  , ('8dc459eeaa15acb6', 'ru', '22584937a4a8382e23a56fbd261ae0dbda2c028a', 'Стены цвета ночного леса и коры под тёмным дымным небом, в глубине фона поднимаются угольки.')
  , ('8dc459eeaa15acb6', 'uk', '22584937a4a8382e23a56fbd261ae0dbda2c028a', 'Стіни кольору нічного лісу та кори під темним димним небом, у глибині тла здіймаються жаринки.')
  , ('8dc459eeaa15acb6', 'sv', '22584937a4a8382e23a56fbd261ae0dbda2c028a', 'Väggar i nattskogsgrönt och bark under en mörk, rökig himmel, med glöd som stiger upp genom bakgrunden.')
  , ('900bfdd2c5aaf566', 'es', '8114ab3a57601ffcee1b9eaafffb4c8561adea9b', 'Gafas nucleares')
  , ('900bfdd2c5aaf566', 'ru', '8114ab3a57601ffcee1b9eaafffb4c8561adea9b', 'Ядерные очки')
  , ('900bfdd2c5aaf566', 'uk', '8114ab3a57601ffcee1b9eaafffb4c8561adea9b', 'Ядерні окуляри')
  , ('900bfdd2c5aaf566', 'sv', '8114ab3a57601ffcee1b9eaafffb4c8561adea9b', 'Kärnkraftsglasögon')
  , ('f4db3fff7c36a085', 'es', '95e92e3918fc6682050e39c82964ff3edb266fff', 'Degradado orquídea')
  , ('f4db3fff7c36a085', 'ru', '95e92e3918fc6682050e39c82964ff3edb266fff', 'Градиент: орхидея')
  , ('f4db3fff7c36a085', 'uk', '95e92e3918fc6682050e39c82964ff3edb266fff', 'Градієнт: орхідея')
  , ('f4db3fff7c36a085', 'sv', '95e92e3918fc6682050e39c82964ff3edb266fff', 'Orkidégradient')
  , ('7122e0c69ba45d2d', 'es', 'f2817a9b2c0417af68309b2a6e5dbab82f161295', 'Paredes azul plateado pálido sobre una noche negra como boca de lobo, con un leve destello de estrellas.')
  , ('7122e0c69ba45d2d', 'ru', 'f2817a9b2c0417af68309b2a6e5dbab82f161295', 'Бледные серебристо-синие стены на фоне кромешной ночи, с едва заметным мерцанием звёзд.')
  , ('7122e0c69ba45d2d', 'uk', 'f2817a9b2c0417af68309b2a6e5dbab82f161295', 'Бліді сріблясто-сині стіни на тлі непроглядної ночі, з ледь помітним мерехтінням зірок.')
  , ('7122e0c69ba45d2d', 'sv', 'f2817a9b2c0417af68309b2a6e5dbab82f161295', 'Blekt silverblå väggar över en kolsvart natt, med ett svagt stjärnglitter.')
  , ('81c7b7cb050ea26d', 'es', '7fd885137d973cf162fe2417eadbd70ecd9734ae', 'Degradado por letra de rojo vivo → vino oscuro.')
  , ('81c7b7cb050ea26d', 'ru', '7fd885137d973cf162fe2417eadbd70ecd9734ae', 'Побуквенный градиент: ярко-красный → тёмное вино.')
  , ('81c7b7cb050ea26d', 'uk', '7fd885137d973cf162fe2417eadbd70ecd9734ae', 'Політерний градієнт: яскраво-червоний → темне вино.')
  , ('81c7b7cb050ea26d', 'sv', '7fd885137d973cf162fe2417eadbd70ecd9734ae', 'Gradient per bokstav: klarrött → mörkt vinrött.')
  , ('9a7fe17e2d48c091', 'es', 'e6cc9035282ccdebffc0f56f58f1b8d6c8a79311', 'Degradado por letra de verde hoja → marrón corteza. De la copa a las raíces.')
  , ('9a7fe17e2d48c091', 'ru', 'e6cc9035282ccdebffc0f56f58f1b8d6c8a79311', 'Побуквенный градиент: зелень листвы → коричневый коры. От кроны до корней.')
  , ('9a7fe17e2d48c091', 'uk', 'e6cc9035282ccdebffc0f56f58f1b8d6c8a79311', 'Політерний градієнт: зелень листя → коричневий кори. Від крони до коріння.')
  , ('9a7fe17e2d48c091', 'sv', 'e6cc9035282ccdebffc0f56f58f1b8d6c8a79311', 'Gradient per bokstav: lövgrönt → barkbrunt. Från krona till rot.')
  , ('65c931b05122cf6c', 'es', '908554507507c82ec5bd2d28fe10e6b51fd4fe5a', 'Degradado por letra de menta → verde bosque profundo.')
  , ('65c931b05122cf6c', 'ru', '908554507507c82ec5bd2d28fe10e6b51fd4fe5a', 'Побуквенный градиент: мята → глубокий лесной зелёный.')
  , ('65c931b05122cf6c', 'uk', '908554507507c82ec5bd2d28fe10e6b51fd4fe5a', 'Політерний градієнт: м''ята → глибокий лісовий зелений.')
  , ('65c931b05122cf6c', 'sv', '908554507507c82ec5bd2d28fe10e6b51fd4fe5a', 'Gradient per bokstav: mint → djupt skogsgrönt.')
  , ('0429c34a08c40ee2', 'es', 'a15667a26f8fbd09ac67a9c4155551d0eff857fd', 'Degradado por letra de oro intenso → blanco marfil.')
  , ('0429c34a08c40ee2', 'ru', 'a15667a26f8fbd09ac67a9c4155551d0eff857fd', 'Побуквенный градиент: насыщенное золото → белый цвета слоновой кости.')
  , ('0429c34a08c40ee2', 'uk', 'a15667a26f8fbd09ac67a9c4155551d0eff857fd', 'Політерний градієнт: насичене золото → білий кольору слонової кістки.')
  , ('0429c34a08c40ee2', 'sv', 'a15667a26f8fbd09ac67a9c4155551d0eff857fd', 'Gradient per bokstav: djupt guld → elfenbensvitt.')
  , ('10fc19103bfc00a4', 'es', 'b62204bc74efd9da27cf3ebbc7002c6e71a1a5ad', 'Degradado por letra de plata → azul metal cañón. Frío y limpio.')
  , ('10fc19103bfc00a4', 'ru', 'b62204bc74efd9da27cf3ebbc7002c6e71a1a5ad', 'Побуквенный градиент: серебро → синеватая воронёная сталь. Холодно и чисто.')
  , ('10fc19103bfc00a4', 'uk', 'b62204bc74efd9da27cf3ebbc7002c6e71a1a5ad', 'Політерний градієнт: срібло → синювата воронована сталь. Холодно й чисто.')
  , ('10fc19103bfc00a4', 'sv', 'b62204bc74efd9da27cf3ebbc7002c6e71a1a5ad', 'Gradient per bokstav: silver → blåsvart stål. Kallt och rent.')
  , ('e8318953ee3473cc', 'es', 'ffe6b732761562041ff44d44571715b12b5027da', 'Degradado por letra de azul cielo → azul real profundo.')
  , ('e8318953ee3473cc', 'ru', 'ffe6b732761562041ff44d44571715b12b5027da', 'Побуквенный градиент: небесно-голубой → глубокий королевский синий.')
  , ('e8318953ee3473cc', 'uk', 'ffe6b732761562041ff44d44571715b12b5027da', 'Політерний градієнт: небесно-блакитний → глибокий королівський синій.')
  , ('e8318953ee3473cc', 'sv', 'ffe6b732761562041ff44d44571715b12b5027da', 'Gradient per bokstav: himmelsblått → djupt kungsblått.')
  , ('17fee1da703692c3', 'es', 'a6ed417fdbecf9d7cea95373bb7f74ab8b4f42d6', 'Degradado por letra de naranja atardecer → púrpura crepuscular.')
  , ('17fee1da703692c3', 'ru', 'a6ed417fdbecf9d7cea95373bb7f74ab8b4f42d6', 'Побуквенный градиент: закатный оранжевый → сумеречный пурпур.')
  , ('17fee1da703692c3', 'uk', 'a6ed417fdbecf9d7cea95373bb7f74ab8b4f42d6', 'Політерний градієнт: помаранчевий заходу → сутінковий пурпур.')
  , ('17fee1da703692c3', 'sv', 'a6ed417fdbecf9d7cea95373bb7f74ab8b4f42d6', 'Gradient per bokstav: solnedgångsorange → skymningslila.')
  , ('9447c4a194d0bbf6', 'es', 'cbdb204cfdf3376735d0ed1cea0b9985b3bfe912', 'Degradado por letra de violeta → rosa intenso.')
  , ('9447c4a194d0bbf6', 'ru', 'cbdb204cfdf3376735d0ed1cea0b9985b3bfe912', 'Побуквенный градиент: фиолет → ярко-розовый.')
  , ('9447c4a194d0bbf6', 'uk', 'cbdb204cfdf3376735d0ed1cea0b9985b3bfe912', 'Політерний градієнт: фіолет → яскраво-рожевий.')
  , ('9447c4a194d0bbf6', 'sv', 'cbdb204cfdf3376735d0ed1cea0b9985b3bfe912', 'Gradient per bokstav: violett → knallrosa.')
  , ('d93ccfb1df90a055', 'es', '7e378d24d3eb1dd3ad959fd0244ac122c1944bca', 'Degradado por letra de gris cálido → rojo brasa. Carbones enfriándose.')
  , ('d93ccfb1df90a055', 'ru', '7e378d24d3eb1dd3ad959fd0244ac122c1944bca', 'Побуквенный градиент: тёплый серый → красный угольков. Остывающие угли.')
  , ('d93ccfb1df90a055', 'uk', '7e378d24d3eb1dd3ad959fd0244ac122c1944bca', 'Політерний градієнт: теплий сірий → червоний жаринок. Вугілля, що холоне.')
  , ('d93ccfb1df90a055', 'sv', '7e378d24d3eb1dd3ad959fd0244ac122c1944bca', 'Gradient per bokstav: varmgrått → glödrött. Svalnande kol.')
  , ('2114443a269971a4', 'es', '8566174efb4eb4edb2ed35464668e45a1334b95c', 'Degradado por letra de blanco → carbón oscuro. Se desvanece a medida que avanza.')
  , ('2114443a269971a4', 'ru', '8566174efb4eb4edb2ed35464668e45a1334b95c', 'Побуквенный градиент: белый → тёмный уголь. Затухает к концу.')
  , ('2114443a269971a4', 'uk', '8566174efb4eb4edb2ed35464668e45a1334b95c', 'Політерний градієнт: білий → темне вугілля. Згасає до кінця.')
  , ('2114443a269971a4', 'sv', '8566174efb4eb4edb2ed35464668e45a1334b95c', 'Gradient per bokstav: vitt → mörkt kol. Tonas bort efter hand.')
  , ('47d9b036144dbc30', 'es', 'f6b5a94241188908466dd4e8866efdd71a095f00', 'Ojos de Poison')
  , ('47d9b036144dbc30', 'ru', 'f6b5a94241188908466dd4e8866efdd71a095f00', 'Глаза Poison')
  , ('47d9b036144dbc30', 'uk', 'f6b5a94241188908466dd4e8866efdd71a095f00', 'Очі Poison')
  , ('47d9b036144dbc30', 'sv', 'f6b5a94241188908466dd4e8866efdd71a095f00', 'Poisons ögon')
  , ('3c0f844e8017bc56', 'es', '670012d71850926c55cf6e4df5b125e67d1e988e', 'Boca de Poison')
  , ('3c0f844e8017bc56', 'ru', '670012d71850926c55cf6e4df5b125e67d1e988e', 'Рот Poison')
  , ('3c0f844e8017bc56', 'uk', '670012d71850926c55cf6e4df5b125e67d1e988e', 'Рот Poison')
  , ('3c0f844e8017bc56', 'sv', '670012d71850926c55cf6e4df5b125e67d1e988e', 'Poisons mun')
  , ('df98d4645ac79249', 'es', '26c1d2970bb104ebf25377d761feeed044bbf63b', 'Llanto de Poison')
  , ('df98d4645ac79249', 'ru', '26c1d2970bb104ebf25377d761feeed044bbf63b', 'Слёзы Poison')
  , ('df98d4645ac79249', 'uk', '26c1d2970bb104ebf25377d761feeed044bbf63b', 'Сльози Poison')
  , ('df98d4645ac79249', 'sv', '26c1d2970bb104ebf25377d761feeed044bbf63b', 'Poisons gråt')
  , ('aa1cc75adcac35af', 'es', 'a8dbee7af410ed602b17d9c2e9c7516d63d649b1', 'Día lluvioso')
  , ('aa1cc75adcac35af', 'ru', 'a8dbee7af410ed602b17d9c2e9c7516d63d649b1', 'Дождливый день')
  , ('aa1cc75adcac35af', 'uk', 'a8dbee7af410ed602b17d9c2e9c7516d63d649b1', 'Дощовий день')
  , ('aa1cc75adcac35af', 'sv', 'a8dbee7af410ed602b17d9c2e9c7516d63d649b1', 'Regnig dag')
  , ('a5239cbe85ee4b07', 'es', '3c6ddde8fbcc54626a1b093d38b2e1f79ccb5b71', 'Degradado real')
  , ('a5239cbe85ee4b07', 'ru', '3c6ddde8fbcc54626a1b093d38b2e1f79ccb5b71', 'Градиент: королевский')
  , ('a5239cbe85ee4b07', 'uk', '3c6ddde8fbcc54626a1b093d38b2e1f79ccb5b71', 'Градієнт: королівський')
  , ('a5239cbe85ee4b07', 'sv', '3c6ddde8fbcc54626a1b093d38b2e1f79ccb5b71', 'Kunglig gradient')
  , ('24217068bcc775e9', 'es', '1c933f68509c9bed6e49ae0ae73a5485f1006267', 'Degradado zafiro')
  , ('24217068bcc775e9', 'ru', '1c933f68509c9bed6e49ae0ae73a5485f1006267', 'Градиент: сапфир')
  , ('24217068bcc775e9', 'uk', '1c933f68509c9bed6e49ae0ae73a5485f1006267', 'Градієнт: сапфір')
  , ('24217068bcc775e9', 'sv', '1c933f68509c9bed6e49ae0ae73a5485f1006267', 'Safirgradient')
  , ('35bd46d542291519', 'es', 'fbdf3954fe302a9669bb5146924faa655c14bd1e', 'Primavera estacional')
  , ('35bd46d542291519', 'ru', 'fbdf3954fe302a9669bb5146924faa655c14bd1e', 'Весенний сезон')
  , ('35bd46d542291519', 'uk', 'fbdf3954fe302a9669bb5146924faa655c14bd1e', 'Весняний сезон')
  , ('35bd46d542291519', 'sv', 'fbdf3954fe302a9669bb5146924faa655c14bd1e', 'Vårsäsong')
  , ('193478fa57528850', 'es', 'c49dfd91243662405690056d72d5545ffed41a88', 'Gafas de impacto')
  , ('193478fa57528850', 'ru', 'c49dfd91243662405690056d72d5545ffed41a88', 'Шок-очки')
  , ('193478fa57528850', 'uk', 'c49dfd91243662405690056d72d5545ffed41a88', 'Шок-окуляри')
  , ('193478fa57528850', 'sv', 'c49dfd91243662405690056d72d5545ffed41a88', 'Chockbrillor')
  , ('1ab9372118365ce8', 'es', '61ad233cad804ff442749806e155e661d6cb1fe8', 'Ojos especiales para los apasionados de los felinos')
  , ('1ab9372118365ce8', 'ru', '61ad233cad804ff442749806e155e661d6cb1fe8', 'Особые глаза для поклонников кошачьих')
  , ('1ab9372118365ce8', 'uk', '61ad233cad804ff442749806e155e661d6cb1fe8', 'Особливі очі для поціновувачів котячих')
  , ('1ab9372118365ce8', 'sv', '61ad233cad804ff442749806e155e661d6cb1fe8', 'Speciella ögon för kattälskare')
  , ('ac0a136fc03bd3ed', 'es', '5052759c37603ebc59fa10a45f0d8819b759e480', 'Degradado acero')
  , ('ac0a136fc03bd3ed', 'ru', '5052759c37603ebc59fa10a45f0d8819b759e480', 'Градиент: сталь')
  , ('ac0a136fc03bd3ed', 'uk', '5052759c37603ebc59fa10a45f0d8819b759e480', 'Градієнт: сталь')
  , ('ac0a136fc03bd3ed', 'sv', '5052759c37603ebc59fa10a45f0d8819b759e480', 'Stålgradient')
  , ('a2747db45e42ad62', 'es', '26d43bc6493e51b1047f9b89c7a4247b7c236a04', 'El retador')
  , ('a2747db45e42ad62', 'ru', '26d43bc6493e51b1047f9b89c7a4247b7c236a04', 'Претендент')
  , ('a2747db45e42ad62', 'uk', '26d43bc6493e51b1047f9b89c7a4247b7c236a04', 'Претендент')
  , ('a2747db45e42ad62', 'sv', '26d43bc6493e51b1047f9b89c7a4247b7c236a04', 'Utmanaren')
  , ('3cf0b30ec7dd441c', 'es', 'f665c772bf8a49dd52bfeb8ad1a6ac44b38cabc8', 'La expresión de un auténtico guerrero entrando en batalla. Ocupa la ranura de boca.')
  , ('3cf0b30ec7dd441c', 'ru', 'f665c772bf8a49dd52bfeb8ad1a6ac44b38cabc8', 'Выражение настоящего воина, идущего в бой. Занимает слот рта.')
  , ('3cf0b30ec7dd441c', 'uk', 'f665c772bf8a49dd52bfeb8ad1a6ac44b38cabc8', 'Вираз справжнього воїна, що йде в бій. Займає слот рота.')
  , ('3cf0b30ec7dd441c', 'sv', 'f665c772bf8a49dd52bfeb8ad1a6ac44b38cabc8', 'Uttrycket hos en sann krigare på väg i strid. Tar upp munplatsen.')
  , ('8dce4de87ebefc5b', 'es', 'f54d4c1fe052a1040ab35be570d899d745e18151', '¡Hora de enseñarles quién es el más guay de todos! Unas gafas que ocupan la ranura de ojos.')
  , ('8dce4de87ebefc5b', 'ru', 'f54d4c1fe052a1040ab35be570d899d745e18151', 'Пора показать им, кто тут самый крутой! Очки, занимающие слот глаз.')
  , ('8dce4de87ebefc5b', 'uk', 'f54d4c1fe052a1040ab35be570d899d745e18151', 'Час показати їм, хто тут найкрутіший! Окуляри, що займають слот очей.')
  , ('8dce4de87ebefc5b', 'sv', 'f54d4c1fe052a1040ab35be570d899d745e18151', 'Dags att visa dem vem som är coolast! Ett par glasögon som tar upp ögonplatsen.')
  , ('2d379480e63e50b0', 'es', '79e69b6303e570c6ed379ee5c5ee18bfd257b9db', 'Degradado crepúsculo')
  , ('2d379480e63e50b0', 'ru', '79e69b6303e570c6ed379ee5c5ee18bfd257b9db', 'Градиент: сумерки')
  , ('2d379480e63e50b0', 'uk', '79e69b6303e570c6ed379ee5c5ee18bfd257b9db', 'Градієнт: сутінки')
  , ('2d379480e63e50b0', 'sv', '79e69b6303e570c6ed379ee5c5ee18bfd257b9db', 'Skymningsgradient')
  , ('b61b00ae9924cd72', 'es', '68c5aaeaec955f166f73912d182f66e281c95d95', 'Inframundo')
  , ('b61b00ae9924cd72', 'ru', '68c5aaeaec955f166f73912d182f66e281c95d95', 'Преисподняя')
  , ('b61b00ae9924cd72', 'uk', '68c5aaeaec955f166f73912d182f66e281c95d95', 'Потойбіччя')
  , ('b61b00ae9924cd72', 'sv', '68c5aaeaec955f166f73912d182f66e281c95d95', 'Underjorden')
  , ('34b4e4fcb0da7041', 'es', 'dbfa8132673eda37733efbad711f380ae714de0a', 'Paredes de piedra gris verdosa mojada bajo un cielo pizarra encapotado, con lluvia cayendo por el fondo.')
  , ('34b4e4fcb0da7041', 'ru', 'dbfa8132673eda37733efbad711f380ae714de0a', 'Мокрые серо-бирюзовые каменные стены под пасмурным сланцевым небом, по фону стекают струи дождя.')
  , ('34b4e4fcb0da7041', 'uk', 'dbfa8132673eda37733efbad711f380ae714de0a', 'Мокрі сіро-бірюзові кам''яні стіни під похмурим сланцевим небом, по тлу стікають струмені дощу.')
  , ('34b4e4fcb0da7041', 'sv', 'dbfa8132673eda37733efbad711f380ae714de0a', 'Våta blågrå stenväggar under en mulen skifferhimmel, med regn som strimmar ner över bakgrunden.')
;

INSERT INTO i18n_proposals
  (key_id, language_code, source_hash, proposed_target, proposer_steam_id,
   license_assent, license_terms_rev, assented_at, status, created_at)
SELECT v.key_id, v.lang, v.source_hash, v.target, 'claude-mt',
       TRUE, 'machine-v1', NOW(), 'pending', NOW()
  FROM _seed249 v
  -- Hash-joined (213's rule): a seed row whose expected English no longer
  -- matches the live key's source inserts NOTHING rather than proposing a
  -- translation of text that no longer exists.
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
    FROM _seed249 v
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
      FROM (SELECT v.key_id, v.lang FROM _seed249 v
             WHERE NOT EXISTS (
                     SELECT 1 FROM i18n_proposals p
                      WHERE p.key_id = v.key_id AND p.language_code = v.lang
                        AND (p.source_hash = v.source_hash OR p.status = 'pending'))
               AND NOT EXISTS (
                     SELECT 1 FROM i18n_entries e
                      WHERE e.key_id = v.key_id AND e.language_code = v.lang
                        AND e.state = 'approved')
             LIMIT 5) x;
    RAISE EXCEPTION 'migration 249: % of 212 seed pairs did not land (e.g. %) - the usual cause is that migration 248 (the key insert) has not run against this database yet; nothing was committed', uncovered, sample;
  END IF;

  RAISE NOTICE 'migration 249: all 212 seed pairs covered (53 keys x es/ru/uk/sv)';
END $$;

COMMIT;
