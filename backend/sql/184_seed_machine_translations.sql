-- 184: seed machine-translated proposals for moderator review.
--
-- Sid, 2026-08-03: "do the actual translating ... for the stuff that is or
-- will be in the web portal, make a proposal, and when i get moderators,
-- they'll come by and approve or reject and rewrite."
--
-- These land as PENDING proposals, never as approved entries: nothing here
-- reaches a player through the portal path until a human approves it. The
-- same strings also ship as bundled offline drafts in I18nCatalogues.cs, so
-- a rejected proposal only means the server pack stops overriding the
-- bundled draft for that key.
--
-- Proposer identity is the sentinel 'claude-mt' rather than a real Steam ID,
-- so the portal's audit trail shows plainly that a machine wrote these and a
-- moderator has not yet reviewed them. license_assent is TRUE with a
-- machine-translation terms revision: these are not a human's licensed
-- contribution and must be distinguishable from one forever.
--
-- Rerunnable: the NOT EXISTS guard skips a key+language when a pending
-- proposal (anyone's) already exists, AND skips any (key, language, source
-- revision) this sentinel has EVER proposed regardless of status — a
-- moderator's reject/approve must stay decided across reruns (Codex Aug-3
-- r2 find 7: the pending-only guard resurrected rejected work). A future
-- re-seed after an English change carries a new source_hash and legitimately
-- inserts fresh.
INSERT INTO i18n_proposals
  (key_id, language_code, source_hash, proposed_target, proposer_steam_id,
   license_assent, license_terms_rev, assented_at, status, created_at)
SELECT v.key_id, v.lang, v.source_hash, v.target, 'claude-mt',
       TRUE, 'machine-v1', NOW(), 'pending', NOW()
  FROM (VALUES
  ('6c69fb2032e145c6', 'es', '254e5c235d478498f37e652155097dfb8c0603b4', 'Sala 1v2 no se llenó — volviendo al menú. Reencola cuando quieras.'),
  ('4d2f0d8391e9a531', 'es', '7fc0f9fd178d5e0ff6bc432e6e4e01c715a6371f', '1v2 — Solo vs Dúo'),
  ('f12a5f43bddffefa', 'es', '1cd566ededf6a75719a91e6e081a7e8c4114edd6', '¡3/3 listos! Entrando a 1v2 — estás en el DÚO...'),
  ('c4318aa1ebd2a555', 'es', '2fa9e5cc35fd1f7d883c58d9c8b1c429811951fb', '< ATRÁS'),
  ('87edb6ceb5f1e62f', 'es', '92199f3eb03e1fe3f9cbb34338d9f8f1f34e3b96', '< Nuevos'),
  ('6543831301a89f5e', 'es', '8e1cffbecc609338e0ea0ba1b86c0512b1bdc972', '< Ant.'),
  ('4c6e54928271ab96', 'es', '43cae6b460032efcaf9a715a25e3f62a933fec2a', '<b>Sala 1v2</b>'),
  ('0d24770b0d02571c', 'es', '5cbda0c7a5fabc89065e6ab6d748b440a1028acd', '<b>Sala 1v2</b>  <color=#888>(vacía)</color>'),
  ('6da1ea02cbaf11d9', 'es', '0f70b6db5879e40f505af9989b9439ecf621cbf5', '<b>Clasificación 2v2</b>'),
  ('5d3ed3204781011a', 'es', '5c9c793345b996017a4330b1ceed5fe76f937c44', '<b>Clasificación 2v2</b>  <color=#888>— sin series completadas</color>'),
  ('3c754dc5b807de93', 'es', '923e761583bf029d9278ca8e77fa54f0d8a2ee6e', '<b>2v2 Competitivo</b>  <color=#888>(Glicko propio, con fuego amigo, BO3)</color>'),
  ('5075e7603c2f7d95', 'es', 'ba8d07355c743611822b60ec2429d74cb614e614', '<b><color=#88AAFF>Clasificación Dúo</color></b>  <color=#888>(sin rango)</color>'),
  ('95ebb11b87cdd04e', 'es', '0143f1c8ceedf9023223f7101de313a2e03ea3fc', '<b><color=#FF6688>* Series 2v2 en vivo</color></b>'),
  ('b635111b3aa9f6db', 'es', 'a3e061c9d22e1a76cc6e8364ffb5c439c3d0125a', '<b><color=#FFB347>Clasificación Solo</color></b>  <color=#888>(sin rango)</color>'),
  ('8f40cf6222ae1cf0', 'es', '3cca33596bd837c6a34cb127d9af34df91da4a62', '<b>Panel Admin</b>  <color=#888>(solo admins)</color>'),
  ('0a1bc5e0ce656d63', 'es', '0d848de7a26cd51381e47b52443df86b1a53b5d2', '<b>Apuestas en FFA en vivo</b>'),
  ('586c92c782a50d04', 'es', '68735523eda3b791bcc79cff57ce0e7350258dfb', '<b>Salas custom</b>'),
  ('e6683e03f8794bf3', 'es', 'cd8b5dda58ee78702ca1791aad1288a0c39510ff', '<b>FFA - TODOS VS TODOS (3-10 jugadores)</b>'),
  ('d62cb7c9d2512266', 'es', '40f3cae7c67fa3d1910d78e9c52b02d732be942d', '<b>Clasificación FFA</b>'),
  ('aff01af270318894', 'es', '69436f4e093ec1bfbb5f78046f3ce964cfcafba9', '<b>Salas FFA abiertas</b>'),
  ('567c924b2161f98f', 'es', '4f59d9374a97a2641f9e1429d63925cd4a4fc5fb', '<b>Cola aleatoria</b>'),
  ('55f3321c97728ac1', 'es', '57c6442982f612283de11e71c840a251ded99dc0', '<b>1v2 recientes</b>'),
  ('7a1462b739334b88', 'es', '99c2bd9a81258b1b9643ff1b723870cef5e1fc54', '<b>Últimas series 2v2</b>'),
  ('fd870b0522ab9f12', 'es', '3f7a0932c8fe2823698affa487d5b60a9aceba20', '<b>Últimas series 2v2</b>  <color=#888>— aún ninguna</color>'),
  ('ff02bb99d53e2f5d', 'es', '8c633183bfd632ab1fe76c7dcc732e7d831f646a', '<b>Últimas FFA competitivas</b>'),
  ('9d9c35aab8ffba08', 'es', '84a78b9d3536b18c587a9c97fee5a813c5de844c', '<b>✓ Equipo 1 (Naranja)</b>'),
  ('51d6a02c3ef257dc', 'es', 'c28ef8723c7d0df6c90a425f1ee5a09d48feb9ec', '<b>✓ Equipo 2 (Azul)</b>'),
  ('7cabc97b10238e5c', 'es', 'd8a969615148d5bc5db796e2f895f39763583cb0', '<color=#44AA44>Actualizado</color>'),
  ('e11202f27fe397f2', 'es', '5591a9faf2a275842c5e3b9d932091abfda415ee', '<color=#44FF44>Cierra ROUNDS para actualizar</color>'),
  ('0b519cc1b493a6c9', 'es', 'abed82f956d547091ba63e2e7b7f96816821eff1', '<color=#666><i>Sin series 2v2 en vivo ahora.</i></color>'),
  ('a463905a21f99458', 'es', 'c37ace37eb278bbb801475948e3df81925c3dcc0', '<color=#666><i>Sin series competitivas en vivo.</i></color>'),
  ('b691e2adfcfdea9f', 'es', 'b4e3df6ec7261496a4f2f8ee7f590f710f05d3e6', '<color=#667>haz clic en un logro para ver quién lo tiene</color>'),
  ('54c5a179c0572f49', 'es', 'b838ddc26b3bb55f1248d3403aa57b22d0d8f271', '<color=#777><i>pasa el ratón y desplaza para ver más</i></color>'),
  ('bd560f79298369cd', 'es', '803af7293eaf4ae774d92dd3026c7a8ff205d355', '<color=#7FE8C3>Ventas</color>  <color=#888>(compras y regalos, recientes primero - regalos dan 0)</color>'),
  ('8e209f74638dbafd', 'es', '23254fd9dd2f5f8dc320a34ecb2cfaea96d2eb49', '<color=#888><i>(El efecto de esta carta no es un número - lee su descripción arriba.)</i></color>'),
  ('0d948bf9a085981a', 'es', 'c2204d8738de607fe6ddbc5f3239ca27d17fb915', '<color=#888><i>Cargando novedades...</i></color>'),
  ('f472c39b32f507f1', 'es', 'cabff10c1e2283f066cd7894bde61a83efc05eb4', '<color=#888><i>Aún no hay mensajes. Los enviados aquí o en #scr-discussion de Discord aparecen aquí.</i></color>'),
  ('174c36bafbe2956f', 'es', 'c651043d9c918c7ea08eaa0e45592b82520f6d5e', '<color=#888><i>Sin ventas aún.</i></color>'),
  ('6f4fe42459b183a0', 'es', 'ce21b94e03ec948163cb7c43df1ca15c2aaa6415', '<color=#888><i>Sin estadísticas para esta carta.</i></color>'),
  ('86aba1ed8b31ffb9', 'es', '9c70ce915a157bec860acbb486261f358ee50449', '<color=#888><i>Nadie lo tiene aún. ¡Sé el primero!</i></color>'),
  ('94db66918d546008', 'es', '631013e0362fd55c596915e3fe91b9e867fc6537', '<color=#888><i>Novedades no disponibles ahora mismo.</i></color>'),
  ('2b2a2115ec5b8f48', 'es', 'a21ec038b09f098ffcc32f78e8bb80305b6f0ddb', '<color=#888><i>v  Baja para ver clasificación + series recientes  v</i></color>'),
  ('f3b2ee1e25aea5da', 'es', 'ac82efd9ca7d0955ef1bda93ee0fe8d6f9e2de72', '<color=#888>Sala custom — elige Equipo 1 o Equipo 2.</color>'),
  ('4cd4d837219a7f6f', 'es', '0de89b2afc192a9c7edfa75e67da4482ff3c9fc7', '<color=#888>Cargando jugadores...</color>'),
  ('0dcd7fa5fff1e6d4', 'es', 'c7c0a44eb576ee3f9ebbe9436946082e06cba1ec', '<color=#888>Cargando miembros...</color>'),
  ('c748ad775e67676a', 'es', 'feea14636f4f98ce478d1447ce2614d4b8cf8231', '<color=#888>Sin salas abiertas — ¡crea una e invita gente en Discord!</color>'),
  ('68aa309ca4b16cef', 'es', 'feac8a420c0e222781e205e9983eddbc6fa462c3', '<color=#888>Ranked por defecto - el anfitrión puede pasar la sala a Casual antes de empezar.</color>'),
  ('ee3d06226c9c2b97', 'es', 'c2dad79a078f8c3687a8d89f0aefb84a1d2cf78c', '<color=#888>Elige 2+ jugadores con historial Ranked para comparar Elo.</color>'),
  ('7f5d46f49545d65e', 'es', '9f7200e4b907ac32fc92d0fe39b49d07cfe3143e', '<color=#888>Carta extra inicial del solo: el solo recibe una carta extra solo en el PRIMER reparto. Está activo si CUALQUIERA de los tres miembros de la sala lo activó.  <color=#7FDF7F>Activo en juego</color> <color=#888>— su primera pantalla de robo reparte dos veces.</color>'),
  ('cc411aefa047c15a', 'es', '9a8cae38683e4f3e98c1303af44231665436fcbc', '<color=#888>haz clic para cerrar</color>'),
  ('9276508a9765ace7', 'es', '79825b95b9bdabb8aa01f605443678f50b25138c', '<color=#88AAFF>Buscar jugadores</color>'),
  ('9f0ca6838edea649', 'es', '6a39a247e137ecd2bc8324bbc4a98b4031f0fe11', '<color=#88FF88>Perfil anonimizado. Ya no se envían datos; las partidas antiguas quedan.</color>'),
  ('69db31eb590f12ae', 'es', 'eacf603f30c34bd78459c3d1302b34e33822dbb4', '<color=#C48CFF>FFA:</color> -'),
  ('9f1db78d42bdc3b7', 'es', '7438392c1065e86ecd48fa2fcff8e7d82b51bd77', '<color=#FF4444>DEBES ACTUALIZAR</color>'),
  ('da9f507760953b88', 'es', 'f28720141e74a4c015a37e1d151f0924da55a676', '<color=#FF6688>* Series Ranked en vivo</color>'),
  ('1e91995466d6d8ff', 'es', '56b2f8794b6c6e5bfde3fa67fd25718e29f1b8b8', '<color=#FF9988>Bloqueados</color>  <color=#888>(no pueden comprar tus objetos; los regalos sí)</color>'),
  ('f5e4b15f8ec88880', 'es', 'af57de8670a28aeeae77335bea05fc79ebb02c01', '<color=#FFAA55>Lista de salas no disponible — puede que el servidor se actualice.</color>'),
  ('21e20bf0ec019f0a', 'es', '8f254dc7f4f1db04fb0efd2953a95b75e6d05c86', '<color=#FFCC44>SIN ELO</color> — cuentan stats, oro y XP. El rating nunca cambia.'),
  ('486870fd71c49d67', 'es', 'd53c35475cec1d741f62a4a6cad340d2a491423e', '<color=#FFD94D>Próximas apuestas</color>'),
  ('644ccc8abba37deb', 'es', 'cc431e8b80c8979c751fb43424e33c02902d1388', '<i>El cuadro aparece cuando haya inscritos.</i>'),
  ('709024e93f016139', 'es', '7c4bd3155e01af462f64d585c6c85694a525cccd', 'ASÍNC. (6 sem.)'),
  ('1a177c3441888ac5', 'es', '6b21fb791ac05170893860c248401cd24a59b732', 'Acerca de'),
  ('c38e5d2842896ff4', 'es', 'bb54db510a92908a5a4df79fc1ad1eae8df50ec3', 'Aceptar'),
  ('444f6214f679a435', 'es', 'a6634f24b2db61aafb90e6954e00e3a9ba699d80', 'Logros'),
  ('0d6434110df619b3', 'es', '6c8fc4ba295689e94a0b72bb52f19286b2b3303b', 'Ajustar posición...'),
  ('dc9683e025054f9e', 'es', '6a72085653e4c5be8c7640c868ef787cbcf063d1', 'Todos'),
  ('8cb4eac07551b7ab', 'es', '43555f317525b8d8043a88c97bc8432a0500d549', 'Permite que el mod envíe tus resultados y estadísticas al servidor de la comunidad.'),
  ('795584614209151d', 'es', '953db08d420badd7066c9c7eb5e205966ed7ad27', 'Cosméticos animados: <color=#88FF88>ON</color>'),
  ('5346ec349129ccdd', 'es', '5529efca285a7da8d70b2fe896a6b3c9168f9870', 'Cosméticos animados: colores prismáticos/cromo, estela prisma, efectos de jugador, brillo del mapa, caras animadas. Off = todo se congela en un fotograma.'),
  ('f3812bc2b6293012', 'es', 'c294dd8cfffa97ad51155538b632d042aace7e03', 'Anonimiza tu Steam ID, tu nombre y tu enlace de Discord. Las partidas se quedan para no afectar al Elo ni al historial de otros. Dejarás de aparecer en las clasificaciones.
<b><color=#FF8888>IRREVERSIBLE:</color></b> este Steam ID no podrá registrarse nunca más. Las partidas futuras de esta cuenta saldrán como [Deleted User] y no contarán para las estadísticas.'),
  ('c88a9fc809cbd08c', 'es', 'fa7e5eb35adccb3eb968b6ecc50791ea1b621f85', 'Aparecer offline (listas Home): <color=#88FF88>ON</color>'),
  ('53eb03940dd9126a', 'es', 'a07ed85fc63acdd4554a17f354ed0ddefe01bb6b', 'Cola de cambios aprobados...'),
  ('4cd5305755696722', 'es', '6c3f3d3203630ce74ffd9609307833fc4f052892', 'Artista'),
  ('ad7b3abe61db1a27', 'es', 'adca584b7f8c32ece93a46b17db60f483cd68dc6', 'Estudio de artista'),
  ('e209685ce7cdc480', 'es', 'ee03e71aa0ce092fd93e310a80b158302071fec0', 'Saldo: -'),
  ('b2d58f4b596f2040', 'es', 'b5f65d80008ad5bc2dcac7a6c3249f23338f989e', 'Banear Steam ID...'),
  ('efa284500294a4ba', 'es', '82dc4c9ba2d0d3898232429a34fce3451ac22165', 'Baneados'),
  ('9cab5fc40afc9b86', 'es', '40880286482e1363c39814b2ce3d66651ef98349', 'Apostar'),
  ('eed713d9e5b7fa6a', 'es', '8c8871a730c2975c44c4ee6bc331c76a40aebf00', 'Bloquear jugador...'),
  ('933906c0a8b7a70f', 'es', '9393db627b5e19257ba529826c55d7246cc0dca5', 'Overlay de bloqueos (esquina): bloqueos iniciados vs bloqueos que absorbieron un golpe, y por qué falló cada uno (muy pronto / muy tarde / no bloqueable).'),
  ('23985dacf212b283', 'es', 'dc8238b1d7f34c183b4144bb47f577c8643952ce', 'Overlay de bloqueos: <color=#88FF88>ON</color>'),
  ('4c2271c1d508dbbb', 'es', 'e42a1e70b4003a66462fd8b1b6f1d551425eedd6', 'Cuadro'),
  ('8ae99931f06e822d', 'es', '0ad03cedb111af624eaf1c61118c7d5ca7ebabb3', 'Mira las salas abiertas abajo o crea la tuya.'),
  ('ef8767b213eb3ea5', 'es', '59269e612dac82734fb0bff3e7d60948afe84748', 'Reportes de bugs...'),
  ('9e63f090e317f40c', 'es', '7ceca51fcafe42567c1c49ed6ab3604d7c962875', 'Comprar'),
  ('9098cedd9b6f8315', 'es', '30134da01318f2520601f331d7a7ad2967d0af9b', 'Temblor de cámara al disparar, golpear y morir. Full = normal. Reduced = suave, mantiene el feedback de golpe. Off = cámara totalmente estable. Solo local.'),
  ('0727e7b2034857dc', 'es', '3e0baa27512846c1a24260a1e63877576b7abd52', 'No se puede abrir el portal - esta instalación usa una conexión de respaldo insegura. Reinicia ROUNDS y reintenta la segura.'),
  ('d6bc949089d7ca60', 'es', '77dfd2135f4db726c47299bb55be26f7f4525a46', 'Cancelar'),
  ('3d7912fb4dd0438d', 'es', '1001e6a796363a864472abf12ae1e511fb8778a6', 'Casual'),
  ('ec3afa95260402c3', 'es', '7d4c84fbad4425fa4f4502f5b3057dccd0a14f3b', 'Historial casual'),
  ('c146b1aae124b5ba', 'es', '37765cd85528b28ffef42e72a647700728327e82', 'Cambia la forma del cursor del menú. Funciona con un color de cursor equipado.'),
  ('8c162f5acbf077d9', 'es', '32c0692f72a53311bf1fdb49b83aaf1ba875f629', 'Chat  <color=#888>(pulsa T para hablar)</color>'),
  ('53090c351d868ada', 'es', 'cd0a753cedf7d0e984104b778141432eb712800c', 'Chat  —  Enter envía, Esc cancela'),
  ('e673a6b24221e740', 'es', '00c68073e93e01b847fdeeb7d6d09c4b0775dc02', 'Notificaciones de chat: <color=#88FF88>ON</color>'),
  ('473227dfcf7069a9', 'es', 'b59d2949c1166ebc227ebbd6c96c355c303cbc9f', 'Aberración cromática: <color=#88FF88>ON</color>'),
  ('76304d064ecdaf0b', 'es', '0a298dccb65dad64a770d7e3fdae567c30ef4331', 'Aberración cromática: el borde RGB que pulsa al disparar/golpear/morir. Off = bordes nítidos, algo más de FPS. Solo visual y local.'),
  ('7693b881f9bb10d2', 'es', '719ea396ad92e01b4757ec2b93bb1e5f270f771d', 'Borrar'),
  ('77ea4429fec09c29', 'es', '87e328dc94be6ee1930cf45d7a3e28999e9fa412', 'Borrar búsqueda'),
  ('8d72e526755bc717', 'es', '99767352d7331ce5b7a9be4ca342d6b8d73171d8', 'Pulsa <b>Buscar aleatorio</b> para encontrar un 2v2.'),
  ('1e2571adc0faf416', 'es', '5821ae9e99fd1b23089635ce0c78c13e11e76603', 'Elige un jugador'),
  ('b4753d0471a2e6ff', 'es', 'bcfc616c401341442e28f27345987840dfbac509', 'Comparar jugadores'),
  ('4801bc4d1ad5528f', 'es', 'cfd434e1ceba2df1cecded3fef55e8783672c543', 'Confirmar — sí, borrar'),
  ('9d92b32fc6bd63f4', 'es', 'fa8c098d8f7e544d019a8621d1fafe84fc8f4188', 'Revisar cosméticos...'),
  ('770b1cee5bc3959f', 'es', 'd002a24ab224f0957250799b98672bb07e8e316f', 'Estelas cosméticas: <color=#88FF88>ON</color>'),
  ('04a881a93d60819b', 'es', 'c2c427166ba31cc0e90127bf9aa5db6bd64c30a7', 'Crear sala'),
  ('0f6b4c74dec1367c', 'es', '3a6ee4336b7ca871681e18318b4ba037122dacf0', 'Colores de cuerpo propios: <color=#88FF88>ON</color>'),
  ('836f724fe5b3074d', 'es', '175c48cf6528b593772f727b6247f068ca95d6a8', 'Colores de cuerpo propios: muestra los Colores de Cuerpo de la tienda en ti y en otros jugadores con mod. Off = todos vuelven al naranja/azul básico.'),
  ('bc4565d2dfd86677', 'es', '43cd04b1d12ecf152fe28138809f095b8750be57', 'Datos y privacidad'),
  ('8bdb5aaa3ae04a72', 'es', 'c58b1c0f2b7a976f48dbdb8ed79e649f25068847', 'Obtenido el'),
  ('119b8c2381d56d77', 'es', 'b59cf9ed55bb5bd999077bce310a9641033b6485', 'Rechazar'),
  ('ab0f98bd6a6bf5f1', 'es', '808d7dca8a74d84af27a2d6602c3d786de45fe1e', 'Por defecto'),
  ('e48c0380bfbd05a1', 'es', '07c349dd6285cec25ea784f21704b057dbf48f57', 'Borrar mis datos'),
  ('6decaed07b4160c0', 'es', '5d3105ed80dc94bd4e080cbe35b6389a727a444f', 'Borrar mis datos...'),
  ('7487b825669e2214', 'es', 'dc3decbb93847518f1a049dcf49d0d7c6560bcc6', 'Detalles'),
  ('2cddd33bf9f91479', 'es', '9a7d4e0687b14e2b7cda406900b802782cd50a62', 'Desactivar'),
  ('222d85297c06217b', 'es', '36fff63ccbcd7bf96ac9014e3e482702fc2b02d4', 'Descartar'),
  ('23e7463a77676d31', 'es', 'bccc14ee7da1d20ff06b9ff2497087e8c7d9f28b', 'Discord'),
  ('1322e8bebba60a17', 'es', '6853dca9066719a20454a8182b7bdbbf4d68df5e', 'Vincular Discord'),
  ('76fd56cb105bdb10', 'es', '20063ad9053289cecaa20ae630ed2dd758282a07', 'Activar'),
  ('582670124134c55f', 'es', 'd764961a0190b30c20bb741496306ead9a1ea719', 'Equipar'),
  ('09d89a5ed17a5b36', 'es', '0f2ac9fc2d0300baafc50eda99f1f68f115de3a9', 'Exportar tier list'),
  ('76839b71857b49bc', 'es', 'c87f9c252d42a96f48c508b0dad1d7cb197bbf27', 'La sala FFA no se llenó — vuelves al menú. Reencola cuando quieras.'),
  ('3859fd8d26c1bd89', 'es', '43ba37bd870c8bada62d152083999e8646000ca0', 'Contador FPS: <color=#88FF88>ON</color>'),
  ('6baeab76d10f6515', 'es', '09fef5d8d9a3c86b2523fef60d512606e7fe0003', 'Falló'),
  ('489dabf2a6e97b73', 'es', '699484ab4b5ed92860c4908c3ec251445dc25bf1', 'Buscar sala custom'),
  ('98e3859cbd3ba125', 'es', '6d56e1c35678ccc6ae1324012172bb5876774aa4', 'Alerta confirmada.'),
  ('fe7a4ade88f61c42', 'es', '66640520cbee31c09da657ee2488012ccc40f1c5', 'Alerta: falso positivo.'),
  ('fe35b612219f0afc', 'es', 'a2e6462d89b355f988344af13d5467d6bd4d10b3', 'Partidas marcadas'),
  ('57458ad5ed088b18', 'es', '2b653211244b09239b9e1d00d3de5a10b288a0dd', 'Forzar inicio'),
  ('0a51b869b20517e8', 'es', 'f14bfe467e47f12a5514df9247ea036e5251f589', 'Fotogramas por segundo, arriba a la izquierda. Útil para ver si un ajuste sirvió.'),
  ('b2afe4968bcc4aa7', 'es', '120606dcac1a829f37539d9af0708360d5453e69', 'Obtener código'),
  ('8e5062f3dfe20e9a', 'es', '8d0a32ed63390771166c129d77e7019ed5faf21b', 'Regalar'),
  ('e195217b8dd18c80', 'es', '5442e2b64fa09764b9f593867e59a97292c84059', 'GitHub'),
  ('c470426e6955e200', 'es', 'fe7f3ff2587e3d130e5d52db5004c675ee655866', 'Rating Glicko-2'),
  ('a68b1f17c3436d85', 'es', 'a632ac0544d4b5dea727409a10ffa2a23c246da0', 'Brillo (bloom): el halo suave de cosméticos brillantes, arte del mapa y efectos. Reducido = halo menor y tenue. Off = sin halo. Solo local — no se oculta nada, el cosmético se ve igual. Algunos objetos llevan el brillo pintado en la imagen, y eso se queda.'),
  ('a36511ec6cccf2af', 'es', 'c57604db5869f60539c66f7caa4809f27133d314', 'Oro'),
  ('8269a27433f4d383', 'es', 'f33ee72ceeb88cb5f896985ce5aab3403f5b5c47', 'Dar logro...'),
  ('d997b5b7f17ee80f', 'es', 'b37dab8c0ef031eeb7a1530584d3d3a7c80629de', 'Dar artista...'),
  ('e94131143feaca60', 'es', '665bfd72831ac98231ad8352f88ee64ae4aacbef', 'Ayuda a traducir el mod: abre el portal web en tu navegador. Un admin debe darte acceso de traductor antes de enviar nada.'),
  ('80f22c97cc0aac83', 'es', '391e23160a547aa2386bfc6e88136f01474e87ec', 'Te oculta de las listas de conectados y recientes de Inicio.'),
  ('98a3fad8f87afa66', 'es', '8cecc82d72d68f9151cb0901cfe40eeac15bfca6', 'Cómo funciona'),
  ('e75c80cd71770ea9', 'es', '3c81f3e5dbb58583795d18d6b4d1d5d6fb61fd43', 'En partida — sin resultados'),
  ('58b772f9792e7de7', 'es', 'be77e0d452a5b253d62f1b462dca9f79853f28df', 'Chat en partida: <color=#88FF88>ON</color>'),
  ('ec771eaf68f39ebf', 'es', '4b631f69842530d659306c8f06dbad594a6b1807', 'Info'),
  ('511bd6cc33ca9a98', 'es', '1b5500a5682ab59e4d75826a732e0c2b221fef3b', 'Overlay de teclas (abajo izq.): muestra W, A, S, D, Space y los dos botones del ratón. Se ilumina en rojo al pulsar. Útil para streams o ver fallos de input.'),
  ('e257fa5f452ec7c9', 'es', 'a24644dfa7613e54acd8966b3c2c10881854a735', 'Overlay teclas: <color=#88FF88>ON</color>'),
  ('937a7d64c4e5b069', 'es', '7b4db7ef1fa23cfb5e115a2a2c89d46a6a2ebc4a', 'Interfaz'),
  ('c6deea52290a01d3', 'es', 'e0d73143de80d17e82de2e017ac156ca3b9c4e01', 'Unirse'),
  ('bbfe7c253f769892', 'es', '3c3ebcdf7b3f53e0dbab23a828dceb490ddeacdd', 'Unirse a 1v2'),
  ('210b4fb9ebf2be28', 'es', 'a22e64b4885cfe3ca0f1a4cecc77d3cded063a49', 'Language  /  Idioma  /  Язык'),
  ('777608da05a9cc4a', 'es', '53cd5d1778decb934a189c78a5655d1a89e0b9a2', 'Últimas versiones'),
  ('317d4929f4752d06', 'es', '7e3520a9733111c30f7ea9191099a8c7d144a4d8', 'Salir'),
  ('8e9e659354925cdc', 'es', '0079a58339aa6045be471f8a0850cdbdbe1ee2b9', 'Salir de colas'),
  ('5f180b79d0ac42fa', 'es', '38c987b3019663c25cb284dbb39be1249e4505be', 'Salir de cola'),
  ('5d98387d164dafd9', 'es', 'b184a204463eaea71321073fcd40120e63116faf', 'Darse de baja'),
  ('73dbf9f880098214', 'es', '02dceaeb2b12aa88ec87fcbae1520e6f97dd1690', 'Saliendo de cola...'),
  ('ac71054abd96ce73', 'es', 'f25d3c50abaee5db733fdf971a931d354780082c', 'Nivel 1'),
  ('7b1f1233cd6900a1', 'es', 'a47ce0315faa83adea0805be565fd26648ba3f45', 'Cargando series...'),
  ('3076a1f4dd6e2b2c', 'es', 'b04ba49f848624bb97ab094a2631d2ad74913498', 'Cargando...'),
  ('70ea7889f7bbb8aa', 'es', '11a9c89722334e53865de12f16e44151a6372071', '¡EMPAREJADO!'),
  ('11a8ce3b24581f0d', 'es', '7b186e235f284107df6b4dbe6060d2b6a5d9f1e5', 'MÁX'),
  ('95e880d9ec642215', 'es', 'abf0c9e2bd591cf88dfd596663185ee446929460', 'Gestiona tus cosméticos y gana un 30% de cada compra pagada: los regalos y tus propias compras no pagan nada. Cambiar tamaño o posición vuelve a revisión; el arte inadecuado puede rechazarse o ajustarse.'),
  ('62017cfb23dc8d2b', 'es', 'f9cdd3d419e43beb090cc154a41152fc7693148f', 'Luz del mapa: <color=#88FF88>ON</color>'),
  ('7360e52eca7e232d', 'es', 'b9654a7b502b417a86b62f424f8d295435911770', 'Luz del mapa: las luces y sombras con que se dibuja el mapa. Off = mapas planos y uniformes, más FPS.'),
  ('f191cfa21f829bad', 'es', '56b5171f1b34b209c2562ac1138f47cba321d54a', 'Sombras: <color=#88FF88>ON</color>'),
  ('c0b1c898d81f830c', 'es', '8605f969b685627b504e2187118f04a140ae4590', 'Marcado como falso positivo. Aún debes arreglar a mano las recompensas y la serie.'),
  ('b28c6095513b6482', 'es', '2f86234d58aeb5c42903f4860c359d45fe00fdf8', 'Idioma del mod. Borradores de traducción automática hasta que los modere la comunidad — el texto de las cartas sigue el idioma de ROUNDS.'),
  ('eaae164b9973a5a5', 'es', '709a23220f2c3d64d1e1d6d18c4d5280f8d82fca', 'Nombre'),
  ('d0de71ee40ca3cbb', 'es', '2ee61b35c40fa92c9003c05e1d840a53a57de02b', 'Cosméticos nuevos'),
  ('5bb3b488dc9259b7', 'es', 'f80fd0c9d9fb230fee5ea75092709ea8f07d8023', 'Sig. >'),
  ('95e4edfd85ad0058', 'es', 'eddf8963477756fa3f004564792411af5a20f827', 'Sin datos de ranking'),
  ('9fac189ff37e47b3', 'es', '29ac10d1f29b9a817ad176f846413aba22dcb719', 'Sin series'),
  ('753b9026b589b7e3', 'es', 'bcdd436f6f0ca66e0f43f93e286fcf6b21dd8688', 'Fuera de cola.'),
  ('066fa92cd9434a97', 'es', '48f932335abd4b7ab52177929989d5898e3fe3b3', 'Antiguos >'),
  ('5ef70f53892e5f41', 'es', 'e3e83bc594cc7ecde3071f3c0b105ca0345809b2', 'Avisos en pantalla para chat entrante y notificaciones de XP/nivel. El chat de Inicio se actualiza igual.'),
  ('bac8aa401a36bac7', 'es', '44a5bdcfc33755caee572a800d414defd6733252', 'Abrir carpeta Tier List'),
  ('0c1ad37d853b8de2', 'es', '7b900634f9f53532c69e92a70ddf0d76c6727e0e', 'Abrir carpeta subidas'),
  ('9aa15709e7599312', 'es', '1d82b1402be0f0e5cdcf5c6bfbb510b84cf551d3', 'Rival no entró — volviendo al menú. Vuelve a la cola cuando quieras.'),
  ('c41b2ce8fb195cfb', 'es', '34bd1f98b5ff53c0ec64db58e11c8ba454e1c881', 'Elige tus horas de inicio (las que quieras)'),
  ('30b0f82ce6dc5c3b', 'es', '4f795bce846c0e7c91c35b77741a9e4c2b77aaf2', 'Ping / región: <color=#88FF88>ON</color>'),
  ('371ca2ac52232538', 'es', '791cf8113eee5c723d227c59846570d1b6283e08', 'Jugar ya (saltar pausa)'),
  ('2b298b7271502c6c', 'es', '392feef07c53c9a7b2763d1fd30fb3f0d68099cc', 'Jugadores'),
  ('d57237dcfcae73a0', 'es', '43637cfe355335aa2af0c5f7474edd1bbe4ddf5e', 'Fallo de sesión del portal: ¿tienes sesión en Steam?'),
  ('b9da26eccc254410', 'es', 'f759566b7428a79b95a6d43e534fa03154485cf6', 'Activa primero la fila RANKED: el ping RLFP solo es para partidas ranked.'),
  ('2eb11481c6e1d81c', 'es', 'f1fbb2b43dca281d0138f4fcc92543ad143ef0b1', 'Previa'),
  ('5873dfb6d6ce0071', 'es', '3e8248e32edfca0c629622b5b669c2d9ce4d0917', 'Precio'),
  ('9f6ba43f78157173', 'es', '4a4300888933d180d78056ae2875609cc168712b', 'Premios'),
  ('caf5eeeec3117ec3', 'es', 'e04ea281201a233a32fca1d38f18e6f2ac668552', 'Premios y reglas'),
  ('f011a454829fac7c', 'es', '122c17aad3eda08a61675ed1002bce10fde0233a', 'Premios anunciados al abrir inscripciones.'),
  ('80d04622a6a5d196', 'es', '07a2ae0633edf8be3f1fc68f659230f653255a99', 'RANKED: ON'),
  ('519e272ed084c741', 'es', '092579473a08bd70d7ac3465596a270bce98cb2a', 'Ranked'),
  ('5c4c865c87f70972', 'es', 'd7108e6ab5e6f45e23c2ec5fe23f129cf7d5631a', 'Historial ranked'),
  ('5f7707fef861204c', 'es', 'd25149b5a5f3f6d2741e28fb6dfc7c7c7ae8fd5b', 'Ranked: OFF'),
  ('68d7eb35f0d51174', 'es', 'a3e1e99f26208eb83034e08c40d2fa9b9e636088', 'Rareza'),
  ('7f8d50b8e50f6ae4', 'es', '55ad58fffa08821614376510977de2bd74d273c5', 'Listo'),
  ('35a2b52c3f3448f1', 'es', 'ef4016fa589e84e154f5828386f2d08741c1efea', 'Torneos recientes'),
  ('a2bbca7fa2249434', 'es', '8386805ac1a372885719e9a22b45ad0ee7a6a723', 'Reconectar a partida'),
  ('41d390e62fe2dede', 'es', '56e3badc4e6c5cc95e0ea5a9a878b9bd09f319d4', 'Recargar'),
  ('6f43d60195f6d487', 'es', '89891d2edf2bd28e5b4952ef12239ee6da11ebd6', 'Reportes rechazados'),
  ('bced5e3b4f62b4c4', 'es', 'e963907dac5cd5c017869b4c96c18021c9bd058b', 'Quitar'),
  ('68a61bb1c87662ca', 'es', '77e4aa898269d071d37354feabcd688601921fb9', 'Fuera de la cola tras 30 min buscando: ¡vuelve a entrar si sigues aquí!'),
  ('fc89dabf25a1093d', 'es', 'fbb446a61a4468f5ad96947bdc0040fe036d44ee', 'Reportar bug'),
  ('7c822307c6b1c668', 'es', '699209ea2c9bafabb100f17a87ff4792d228abaf', 'Descartado para siempre.'),
  ('4fef188706c2844c', 'es', 'b702c754b815b4a29ee7571911b52c912154ae10', 'Reporte devuelto a la cola.'),
  ('44bd426b0542d87a', 'es', '583d156c59fe2e53385c84b50e54a60e4aa6f593', 'Revertir serie...'),
  ('a593067a8ec0d1b5', 'es', '633f1246d9f9fb9ac561e393879b8a28b0bc7814', 'Quitar artista...'),
  ('43a8dbc807b7024c', 'es', '13255b407052cfd4a359f6e8e175137b48388a31', 'Revocar permiso'),
  ('49c8adce945e10af', 'es', 'd9baef5110422c5e7f32144bde9656cc19bc8806', 'SID''S COMPETITIVE ROUNDS'),
  ('b939a9ae4f89cb0f', 'es', 'c4477dfa9e0ef6b9e35433b86e32cb10888ee6a8', 'SYNC (semanal)'),
  ('b4489e1753b09ca0', 'es', 'b0b2b820bcfb2fa8bcf150c069f23c562d765014', 'Mismas cartas: OFF'),
  ('af50d15ccc91d824', 'es', 'fb37e857128f8e9e6452c1511f0f974a99accbca', 'Mismas cartas: ON'),
  ('5e96f965b35fd77c', 'es', '71b36cbeefd3cb3cc776984731e0f86c9c663c32', 'Guardar votos'),
  ('8709d2a7417a8af1', 'es', 'fb043b0389a26d7aed0805a82374ca520672afa6', 'Buscar al azar'),
  ('0af12ce407aedc11', 'es', '903dc15e26d8934a5bd54ce5dad491d5f406b9b4', 'Buscar ranked'),
  ('843f580e89a1c339', 'es', 'fb4e2d95d98953646b6c1b210ec64b47348fe61b', 'Elige hasta 12 jugadores'),
  ('3633461f3484ae77', 'es', '7c6b3fea63421c1496aef5d5e0fcd1fe1105411a', 'Envía un reporte de bug al equipo del mod: descripción, gravedad y, si quieres, tus registros de juego. Usa Previa para ver qué se adjunta.'),
  ('73be4f1b886889cd', 'es', 'ee7f6b62b61a12ec18d69e017d11a4a8e7c9c4aa', 'Info de sesión'),
  ('ed811fd03e3e7985', 'es', '758d7f7281c0192f6d09ba1663e7af25cc8c0e15', 'Activar'),
  ('67bfd40e0352aa95', 'es', 'c7f73bb54d928922c3838bb789ee9fb8a5b1eb37', 'Ajustes'),
  ('9711b68fef7e1eb9', 'es', '55de88709232ec03a7618ceae9b2248419fdc862', 'Tienda'),
  ('ba7dca8a4cbe7f6d', 'es', 'da679c68be32dbace626c9a143329c3cc63c44cf', 'Mostrar Discord en la tabla: <color=#888>vincula Discord antes</color>'),
  ('0949f07beef44739', 'es', '4d9856099b56f185037bd58ccbdefdec3cf2f349', 'Mostrar Discord en la tabla: <color=#FF9966>OFF</color>'),
  ('13035d18b3c5b6c2', 'es', 'b76e070645519586f2e8526c52fc8df857477430', 'Mostrar oro'),
  ('23d6d84ae59939d7', 'es', '223b8527cddb50f542113f5f695eb3275b59e7d1', 'Viendo: Elo por partidas'),
  ('3c78beb9819d89e3', 'es', '9bab7bd9168724dde1e704ed3a7103e7399a2e30', 'Muestra el chat de la comunidad en la esquina al jugar. Pulsa T para responder.'),
  ('0e6859e372c55b36', 'es', '5f080b6372a7db5231fcb8805edd4b8ada17f6be', 'Muestra estelas cosméticas en ti y en otros con el mod.'),
  ('14e6e248ad06ea5b', 'es', '28e456cb2fc9eb62e6a90a66a3be46b85318cf16', 'Muestra tu nombre de Discord en la clasificación (opcional; vincula Discord en Inicio primero).'),
  ('b802826c7bb214e1', 'es', '415d6233a087d283a4ca8030301edf6599dfe13d', 'Muestra tu región de servidor actual y tu ping a ella.'),
  ('9e3df6c9efe7a876', 'es', '928414d3088da4bcd44cf4682de27b4a7a01317b', 'Rol: Todos'),
  ('1dea4fe7a34b66b0', 'es', '5ea804d3a2d1d5bc3cb0429a135b43edc310bf0d', 'Rol: Solo'),
  ('5d86deb9c0e3f802', 'es', '16c45d0311571f2a5866f4739eee429063e075cf', 'Apuntarse al torneo'),
  ('e268f01337cec8c0', 'es', '09c26725abca4f5f770be1e26e44b5ee79b7a7bd', 'Inscritos'),
  ('646589db10bb5f2c', 'es', '908c1137c947ee99598d692d1d247169b67b174c', 'Rayos de sombra suaves de la luz del mapa. Off = sin sombras (la luz sigue) y más FPS.'),
  ('5fc280a4ee756126', 'es', '02ff65909856c0d4c47e5496f4e5df4964c3982f', 'Agotado'),
  ('26cdd20b423a5097', 'es', '9ae467b5d5e0a54b70a78d38a1b96d8219c6d628', 'Extra del solo: OFF'),
  ('c0ff08581181780a', 'es', '11ac349e24b8d6338b41fb21be03420ca2abf1b8', 'Extra del solo: ON'),
  ('a9e4235a8b94ba63', 'es', '365f992a0a10615ba2ae06d707bb66c9e6c66bbe', 'Empezar'),
  ('01a2f5687a851390', 'es', 'bcecf4562f1709b1448aff7c6b49edb6acecdb12', 'Stock'),
  ('6af9389a92c0a962', 'es', '9e253470c876ee6d5c720eb777aeb82d4c26e28f', 'Parar'),
  ('bcc7673bc97a4ef3', 'es', '24338c588a7c02e9f6f4cbf38c0da960808fc6e9', 'Dejar de evitar en Ranked'),
  ('4c3422795023e95d', 'es', 'db825a8ff1b5076df3201c8038e1efe1606429ba', 'Búsqueda detenida'),
  ('4f2532a4d52ec616', 'es', '8d3f894fef9a0d6167b3bc9a6cbb1e4536c3656b', 'Esta cuenta no está registrada como artista.'),
  ('3836763834fbb27e', 'es', 'f5b022a24101fc5adb935f8dd1359ad661f7ea15', 'Traducir SCR (portal web)'),
  ('a13da205cf3e6b93', 'es', 'de6c0edd74bd11469c959c7269b1894c011895fc', 'Pon !link CÓDIGO en Discord'),
  ('5e52fd220fd26006', 'es', 'd2671bfbfdd28d9143047f6a5239296f8a690156', 'Desbanear'),
  ('7567c90e85adfb18', 'es', '12aabd251c4213f1cebfe4cb83e6547df55552c3', 'Desbloquear'),
  ('701947c757af5fa3', 'es', '6df7395e6a96187a22b6cfc54a7672e0323a6d78', 'Falta una comilla — uso: /report "Nombre Con Espacios" [motivo]'),
  ('8130edc9d99316e3', 'es', '11442128172c9afd9632fadcdf0aa392e5083094', 'Quitar'),
  ('dae179ea3b8774a4', 'es', 'bc7819b34ff87570745fbe461e36a16f80e562ce', 'Desconocido'),
  ('ade79993560f1bf0', 'es', 'fb91e24fa52d8d2b32937bf04d843f730319a902', 'Actualizar'),
  ('f21486a74e18c3bb', 'es', '7b0543786aca645a0c22d2b047ede094e3ca42c4', 'Subir un cosmético...'),
  ('b5cadb3a41019d3e', 'es', '4a26389c62013544b114efb52635035677621f0e', 'Visuales y efectos'),
  ('30f54024c484dfa7', 'es', 'e9ec8b04b776b9c340c2b12d163577e69c861c8f', 'Esperando al rival...'),
  ('f8465990452e8309', 'es', '297f06ad75081de5ae834632a5e00a251ff00202', 'Récord V/D'),
  ('6ecfb3dab02b8467', 'es', '28271452910576a33933fb47d894f1e4d8a6eb87', 'Tu partida de FFA continuó sin ti - te han sacado de ella.'),
  ('633dc1e39f94d3a0', 'es', 'a1a912243dc59524cca780830160df18bf83b01c', 'Tus puestos: <color=#888>aún no has completado torneos</color>'),
  ('b1106ea1ec6e7b1e', 'es', '45a6f9adb1df3a78aafc71391c7d3bfa7680229b', 'caducado'),
  ('6c69fb2032e145c6', 'ru', '254e5c235d478498f37e652155097dfb8c0603b4', 'Лобби 1v2 не собралось — выход в меню. Встань в очередь снова.'),
  ('4d2f0d8391e9a531', 'ru', '7fc0f9fd178d5e0ff6bc432e6e4e01c715a6371f', '1v2 — Соло/Дуо'),
  ('f12a5f43bddffefa', 'ru', '1cd566ededf6a75719a91e6e081a7e8c4114edd6', '3/3 готовы! Вход в 1v2 — ты в ДУО...'),
  ('c4318aa1ebd2a555', 'ru', '2fa9e5cc35fd1f7d883c58d9c8b1c429811951fb', '< НАЗАД'),
  ('87edb6ceb5f1e62f', 'ru', '92199f3eb03e1fe3f9cbb34338d9f8f1f34e3b96', '< Новее'),
  ('6543831301a89f5e', 'ru', '8e1cffbecc609338e0ea0ba1b86c0512b1bdc972', '< Пред'),
  ('4c6e54928271ab96', 'ru', '43cae6b460032efcaf9a715a25e3f62a933fec2a', '<b>Лобби 1v2</b>'),
  ('0d24770b0d02571c', 'ru', '5cbda0c7a5fabc89065e6ab6d748b440a1028acd', '<b>Лобби 1v2</b>  <color=#888>(пусто)</color>'),
  ('6da1ea02cbaf11d9', 'ru', '0f70b6db5879e40f505af9989b9439ecf621cbf5', '<b>Таблица 2v2</b>'),
  ('5d3ed3204781011a', 'ru', '5c9c793345b996017a4330b1ceed5fe76f937c44', '<b>Таблица 2v2</b>  <color=#888>— завершённых серий пока нет</color>'),
  ('3c754dc5b807de93', 'ru', '923e761583bf029d9278ca8e77fa54f0d8a2ee6e', '<b>Ранговый 2v2</b>  <color=#888>(свой Glicko, огонь по своим вкл., BO3)</color>'),
  ('5075e7603c2f7d95', 'ru', 'ba8d07355c743611822b60ec2429d74cb614e614', '<b><color=#88AAFF>Таблица дуо</color></b>  <color=#888>(без рейтинга)</color>'),
  ('95ebb11b87cdd04e', 'ru', '0143f1c8ceedf9023223f7101de313a2e03ea3fc', '<b><color=#FF6688>* Живые серии 2v2</color></b>'),
  ('b635111b3aa9f6db', 'ru', 'a3e061c9d22e1a76cc6e8364ffb5c439c3d0125a', '<b><color=#FFB347>Таблица соло</color></b>  <color=#888>(без рейтинга)</color>'),
  ('8f40cf6222ae1cf0', 'ru', '3cca33596bd837c6a34cb127d9af34df91da4a62', '<b>Панель админа</b>  <color=#888>(только админам)</color>'),
  ('0a1bc5e0ce656d63', 'ru', '0d848de7a26cd51381e47b52443df86b1a53b5d2', '<b>Ставки на живые лобби FFA</b>'),
  ('586c92c782a50d04', 'ru', '68735523eda3b791bcc79cff57ce0e7350258dfb', '<b>Свои лобби</b>'),
  ('e6683e03f8794bf3', 'ru', 'cd8b5dda58ee78702ca1791aad1288a0c39510ff', '<b>FFA - КАЖДЫЙ ЗА СЕБЯ (3-10 игроков)</b>'),
  ('d62cb7c9d2512266', 'ru', '40f3cae7c67fa3d1910d78e9c52b02d732be942d', '<b>Таблица FFA</b>'),
  ('aff01af270318894', 'ru', '69436f4e093ec1bfbb5f78046f3ce964cfcafba9', '<b>Открытые лобби FFA</b>'),
  ('567c924b2161f98f', 'ru', '4f59d9374a97a2641f9e1429d63925cd4a4fc5fb', '<b>Общая очередь</b>'),
  ('55f3321c97728ac1', 'ru', '57c6442982f612283de11e71c840a251ded99dc0', '<b>Недавние игры 1v2</b>'),
  ('7a1462b739334b88', 'ru', '99c2bd9a81258b1b9643ff1b723870cef5e1fc54', '<b>Недавние серии 2v2</b>'),
  ('fd870b0522ab9f12', 'ru', '3f7a0932c8fe2823698affa487d5b60a9aceba20', '<b>Недавние серии 2v2</b>  <color=#888>— пока нет</color>'),
  ('ff02bb99d53e2f5d', 'ru', '8c633183bfd632ab1fe76c7dcc732e7d831f646a', '<b>Недавние ранговые FFA</b>'),
  ('9d9c35aab8ffba08', 'ru', '84a78b9d3536b18c587a9c97fee5a813c5de844c', '<b>✓ Команда 1 (оранж.)</b>'),
  ('51d6a02c3ef257dc', 'ru', 'c28ef8723c7d0df6c90a425f1ee5a09d48feb9ec', '<b>✓ Команда 2 (син.)</b>'),
  ('7cabc97b10238e5c', 'ru', 'd8a969615148d5bc5db796e2f895f39763583cb0', '<color=#44AA44>Актуально</color>'),
  ('e11202f27fe397f2', 'ru', '5591a9faf2a275842c5e3b9d932091abfda415ee', '<color=#44FF44>Закрой ROUNDS, чтобы обновить</color>'),
  ('0b519cc1b493a6c9', 'ru', 'abed82f956d547091ba63e2e7b7f96816821eff1', '<color=#666><i>Сейчас нет активных серий 2v2.</i></color>'),
  ('a463905a21f99458', 'ru', 'c37ace37eb278bbb801475948e3df81925c3dcc0', '<color=#666><i>Сейчас нет активных ранговых серий.</i></color>'),
  ('b691e2adfcfdea9f', 'ru', 'b4e3df6ec7261496a4f2f8ee7f590f710f05d3e6', '<color=#667>нажми на достижение, чтобы увидеть обладателей</color>'),
  ('54c5a179c0572f49', 'ru', 'b838ddc26b3bb55f1248d3403aa57b22d0d8f271', '<color=#777><i>наведи на панель и прокрути дальше</i></color>'),
  ('bd560f79298369cd', 'ru', '803af7293eaf4ae774d92dd3026c7a8ff205d355', '<color=#7FE8C3>Журнал продаж</color>  <color=#888>(все покупки и подарки, новые сверху - за подарки 0)</color>'),
  ('8e209f74638dbafd', 'ru', '23254fd9dd2f5f8dc320a34ecb2cfaea96d2eb49', '<color=#888><i>(Эффект карты не число - смотри описание карты выше.)</i></color>'),
  ('0d948bf9a085981a', 'ru', 'c2204d8738de607fe6ddbc5f3239ca27d17fb915', '<color=#888><i>Загрузка списка изменений...</i></color>'),
  ('f472c39b32f507f1', 'ru', 'cabff10c1e2283f066cd7894bde61a83efc05eb4', '<color=#888><i>Сообщений пока нет. Здесь появляются сообщения отсюда и из #scr-discussion в Discord.</i></color>'),
  ('174c36bafbe2956f', 'ru', 'c651043d9c918c7ea08eaa0e45592b82520f6d5e', '<color=#888><i>Продаж пока нет.</i></color>'),
  ('6f4fe42459b183a0', 'ru', 'ce21b94e03ec948163cb7c43df1ca15c2aaa6415', '<color=#888><i>Нет данных по этой карте.</i></color>'),
  ('86aba1ed8b31ffb9', 'ru', '9c70ce915a157bec860acbb486261f358ee50449', '<color=#888><i>Этого ещё никто не получил. Будь первым!</i></color>'),
  ('94db66918d546008', 'ru', '631013e0362fd55c596915e3fe91b9e867fc6537', '<color=#888><i>Список изменений сейчас недоступен.</i></color>'),
  ('2b2a2115ec5b8f48', 'ru', 'a21ec038b09f098ffcc32f78e8bb80305b6f0ddb', '<color=#888><i>v  Листай вниз: таблица и недавние серии  v</i></color>'),
  ('f3b2ee1e25aea5da', 'ru', 'ac82efd9ca7d0955ef1bda93ee0fe8d6f9e2de72', '<color=#888>Своё лобби — займи Команду 1 или 2.</color>'),
  ('4cd4d837219a7f6f', 'ru', '0de89b2afc192a9c7edfa75e67da4482ff3c9fc7', '<color=#888>Загрузка получивших...</color>'),
  ('0dcd7fa5fff1e6d4', 'ru', 'c7c0a44eb576ee3f9ebbe9436946082e06cba1ec', '<color=#888>Загрузка участников...</color>'),
  ('c748ad775e67676a', 'ru', 'feea14636f4f98ce478d1447ce2614d4b8cf8231', '<color=#888>Нет открытых лобби — создай своё и зови игроков в Discord!</color>'),
  ('68aa309ca4b16cef', 'ru', 'feac8a420c0e222781e205e9983eddbc6fa462c3', '<color=#888>По умолчанию рейтинговое - хост может сменить лобби на обычное до старта.</color>'),
  ('ee3d06226c9c2b97', 'ru', 'c2dad79a078f8c3687a8d89f0aefb84a1d2cf78c', '<color=#888>Выбери 2+ игроков с историей рейтинга — сравни Elo.</color>'),
  ('7f5d46f49545d65e', 'ru', '9f7200e4b907ac32fc92d0fe39b49d07cfe3143e', '<color=#888>Доп. первый выбор соло: соло получает одну лишнюю карту только в ПЕРВОЙ раздаче матча. Включено, если хотя бы ОДИН из троих в лобби включил это.  <color=#7FDF7F>Активно в игре</color> <color=#888>— первый экран выбора соло раздаёт дважды.</color>'),
  ('cc411aefa047c15a', 'ru', '9a8cae38683e4f3e98c1303af44231665436fcbc', '<color=#888>клик где угодно — закрыть</color>'),
  ('9276508a9765ace7', 'ru', '79825b95b9bdabb8aa01f605443678f50b25138c', '<color=#88AAFF>Поиск игроков</color>'),
  ('9f0ca6838edea649', 'ru', '6a39a247e137ecd2bc8324bbc4a98b4031f0fe11', '<color=#88FF88>Профиль анонимизирован. Отправка данных выкл.; матчи остаются.</color>'),
  ('69db31eb590f12ae', 'ru', 'eacf603f30c34bd78459c3d1302b34e33822dbb4', '<color=#C48CFF>FFA:</color> -'),
  ('9f1db78d42bdc3b7', 'ru', '7438392c1065e86ecd48fa2fcff8e7d82b51bd77', '<color=#FF4444>НУЖНО ОБНОВИТЬ</color>'),
  ('da9f507760953b88', 'ru', 'f28720141e74a4c015a37e1d151f0924da55a676', '<color=#FF6688>* Активные рейт. серии</color>'),
  ('1e91995466d6d8ff', 'ru', '56b2f8794b6c6e5bfde3fa67fd25718e29f1b8b8', '<color=#FF9988>Чёрный список</color>  <color=#888>(не купят твои вещи; подарки работают)</color>'),
  ('f5e4b15f8ec88880', 'ru', 'af57de8670a28aeeae77335bea05fc79ebb02c01', '<color=#FFAA55>Список лобби недоступен — возможно, сервер обновляется.</color>'),
  ('21e20bf0ec019f0a', 'ru', '8f254dc7f4f1db04fb0efd2953a95b75e6d05c86', '<color=#FFCC44>БЕЗ РЕЙТИНГА</color> — статы, золото и опыт идут. Рейтинг не меняется.'),
  ('486870fd71c49d67', 'ru', 'd53c35475cec1d741f62a4a6cad340d2a491423e', '<color=#FFD94D>Ставки на матчи</color>'),
  ('644ccc8abba37deb', 'ru', 'cc431e8b80c8979c751fb43424e33c02902d1388', '<i>Сетка появится после записи игроков.</i>'),
  ('709024e93f016139', 'ru', '7c4bd3155e01af462f64d585c6c85694a525cccd', 'АСИНХ. (6 нед.)'),
  ('1a177c3441888ac5', 'ru', '6b21fb791ac05170893860c248401cd24a59b732', 'О моде'),
  ('c38e5d2842896ff4', 'ru', 'bb54db510a92908a5a4df79fc1ad1eae8df50ec3', 'Принять'),
  ('444f6214f679a435', 'ru', 'a6634f24b2db61aafb90e6954e00e3a9ba699d80', 'Достижения'),
  ('0d6434110df619b3', 'ru', '6c8fc4ba295689e94a0b72bb52f19286b2b3303b', 'Изменить позицию...'),
  ('dc9683e025054f9e', 'ru', '6a72085653e4c5be8c7640c868ef787cbcf063d1', 'Все'),
  ('8cb4eac07551b7ab', 'ru', '43555f317525b8d8043a88c97bc8432a0500d549', 'Разрешить моду отправлять результаты матчей и статистику на сервер сообщества.'),
  ('795584614209151d', 'ru', '953db08d420badd7066c9c7eb5e205966ed7ad27', 'Анимация косметики: <color=#88FF88>ВКЛ</color>'),
  ('5346ec349129ccdd', 'ru', '5529efca285a7da8d70b2fe896a6b3c9168f9870', 'Анимация косметики: призма/хром цвета тела, призм. след, эффекты игрока, мерцание скинов карт, живые лица. Выкл = всё замирает на статичном кадре.'),
  ('f3812bc2b6293012', 'ru', 'c294dd8cfffa97ad51155538b632d042aace7e03', 'Анонимизирует твой Steam ID, ник и привязку Discord. Матчи остаются, чтобы не задеть Elo и историю других игроков. Ты пропадёшь из таблиц лидеров.
<b><color=#FF8888>НЕОБРАТИМО:</color></b> этот Steam ID нельзя будет зарегистрировать заново. Будущие матчи с этого аккаунта будут показаны как [Deleted User] и не пойдут в статистику.'),
  ('c88a9fc809cbd08c', 'ru', 'fa7e5eb35adccb3eb968b6ecc50791ea1b621f85', 'Не в сети (списки Главной): <color=#88FF88>ВКЛ</color>'),
  ('53eb03940dd9126a', 'ru', 'a07ed85fc63acdd4554a17f354ed0ddefe01bb6b', 'Одобренные обновления...'),
  ('4cd5305755696722', 'ru', '6c3f3d3203630ce74ffd9609307833fc4f052892', 'Художник'),
  ('ad7b3abe61db1a27', 'ru', 'adca584b7f8c32ece93a46b17db60f483cd68dc6', 'Мастерская'),
  ('e209685ce7cdc480', 'ru', 'ee03e71aa0ce092fd93e310a80b158302071fec0', 'Баланс: -'),
  ('b2d58f4b596f2040', 'ru', 'b5f65d80008ad5bc2dcac7a6c3249f23338f989e', 'Бан Steam ID...'),
  ('efa284500294a4ba', 'ru', '82dc4c9ba2d0d3898232429a34fce3451ac22165', 'Забаненные'),
  ('9cab5fc40afc9b86', 'ru', '40880286482e1363c39814b2ce3d66651ef98349', 'Ставка'),
  ('eed713d9e5b7fa6a', 'ru', '8c8871a730c2975c44c4ee6bc331c76a40aebf00', 'Заблокировать...'),
  ('933906c0a8b7a70f', 'ru', '9393db627b5e19257ba529826c55d7246cc0dca5', 'Оверлей блока (угол): начатые блоки против тех, что реально поглотили удар, и почему остальные промахнулись (рано / поздно / не блокируется).'),
  ('23985dacf212b283', 'ru', 'dc8238b1d7f34c183b4144bb47f577c8643952ce', 'Оверлей блока: <color=#88FF88>ВКЛ</color>'),
  ('4c2271c1d508dbbb', 'ru', 'e42a1e70b4003a66462fd8b1b6f1d551425eedd6', 'Сетка'),
  ('8ae99931f06e822d', 'ru', '0ad03cedb111af624eaf1c61118c7d5ca7ebabb3', 'Смотри открытые лобби ниже или создай своё.'),
  ('ef8767b213eb3ea5', 'ru', '59269e612dac82734fb0bff3e7d60948afe84748', 'Баг-репорты...'),
  ('9e63f090e317f40c', 'ru', '7ceca51fcafe42567c1c49ed6ab3604d7c962875', 'Купить'),
  ('9098cedd9b6f8315', 'ru', '30134da01318f2520601f331d7a7ad2967d0af9b', 'Тряска камеры при выстрелах/попаданиях/смертях. Полная = как в оригинале. Слабее = мягче, отдача видна. Выкл = камера неподвижна. Только локально.'),
  ('0727e7b2034857dc', 'ru', '3e0baa27512846c1a24260a1e63877576b7abd52', 'Портал не открыть - эта установка на резервном незащищённом соединении. Перезапусти ROUNDS, чтобы вернуться к защищённому.'),
  ('d6bc949089d7ca60', 'ru', '77dfd2135f4db726c47299bb55be26f7f4525a46', 'Отмена'),
  ('3d7912fb4dd0438d', 'ru', '1001e6a796363a864472abf12ae1e511fb8778a6', 'Обычный'),
  ('ec3afa95260402c3', 'ru', '7d4c84fbad4425fa4f4502f5b3057dccd0a14f3b', 'История обычных'),
  ('c146b1aae124b5ba', 'ru', '37765cd85528b28ffef42e72a647700728327e82', 'Меняет форму курсора меню. Работает вместе с цветом курсора.'),
  ('8c162f5acbf077d9', 'ru', '32c0692f72a53311bf1fdb49b83aaf1ba875f629', 'Чат  <color=#888>(нажми T для чата)</color>'),
  ('53090c351d868ada', 'ru', 'cd0a753cedf7d0e984104b778141432eb712800c', 'Чат  —  Enter — отправить, Esc — отмена'),
  ('e673a6b24221e740', 'ru', '00c68073e93e01b847fdeeb7d6d09c4b0775dc02', 'Уведомления чата: <color=#88FF88>ВКЛ</color>'),
  ('473227dfcf7069a9', 'ru', 'b59d2949c1166ebc227ebbd6c96c355c303cbc9f', 'Хроматич. аберрация: <color=#88FF88>ВКЛ</color>'),
  ('76304d064ecdaf0b', 'ru', '0a298dccb65dad64a770d7e3fdae567c30ef4331', 'Хроматич. аберрация: RGB-кайма, пульсирующая при выстрелах/попаданиях/смертях. Выкл = чёткие края, чуть больше FPS. Только визуал, локально.'),
  ('7693b881f9bb10d2', 'ru', '719ea396ad92e01b4757ec2b93bb1e5f270f771d', 'Сброс'),
  ('77ea4429fec09c29', 'ru', '87e328dc94be6ee1930cf45d7a3e28999e9fa412', 'Сброс поиска'),
  ('8d72e526755bc717', 'ru', '99767352d7331ce5b7a9be4ca342d6b8d73171d8', 'Нажми <b>Случайный поиск</b>, чтобы найти 2v2.'),
  ('1e2571adc0faf416', 'ru', '5821ae9e99fd1b23089635ce0c78c13e11e76603', 'Выбери игрока'),
  ('b4753d0471a2e6ff', 'ru', 'bcfc616c401341442e28f27345987840dfbac509', 'Сравнить игроков'),
  ('4801bc4d1ad5528f', 'ru', 'cfd434e1ceba2df1cecded3fef55e8783672c543', 'Подтвердить — удалить'),
  ('9d92b32fc6bd63f4', 'ru', 'fa8c098d8f7e544d019a8621d1fafe84fc8f4188', 'Проверка косметики...'),
  ('770b1cee5bc3959f', 'ru', 'd002a24ab224f0957250799b98672bb07e8e316f', 'Шлейфы косметики: <color=#88FF88>ВКЛ</color>'),
  ('04a881a93d60819b', 'ru', 'c2c427166ba31cc0e90127bf9aa5db6bd64c30a7', 'Создать лобби'),
  ('0f6b4c74dec1367c', 'ru', '3a6ee4336b7ca871681e18318b4ba037122dacf0', 'Свои цвета тел игроков: <color=#88FF88>ВКЛ</color>'),
  ('836f724fe5b3074d', 'ru', '175c48cf6528b593772f727b6247f068ca95d6a8', 'Свои цвета тел: показывает купленные в магазине цвета тела у тебя и других игроков с модом. Выкл = все становятся стандартными оранжевым/синим.'),
  ('bc4565d2dfd86677', 'ru', '43cd04b1d12ecf152fe28138809f095b8750be57', 'Данные и приватность'),
  ('8bdb5aaa3ae04a72', 'ru', 'c58b1c0f2b7a976f48dbdb8ed79e649f25068847', 'Получено'),
  ('119b8c2381d56d77', 'ru', 'b59cf9ed55bb5bd999077bce310a9641033b6485', 'Отклонить'),
  ('ab0f98bd6a6bf5f1', 'ru', '808d7dca8a74d84af27a2d6602c3d786de45fe1e', 'Стандарт'),
  ('e48c0380bfbd05a1', 'ru', '07c349dd6285cec25ea784f21704b057dbf48f57', 'Удалить мои данные'),
  ('6decaed07b4160c0', 'ru', '5d3105ed80dc94bd4e080cbe35b6389a727a444f', 'Удалить мои данные...'),
  ('7487b825669e2214', 'ru', 'dc3decbb93847518f1a049dcf49d0d7c6560bcc6', 'Детали'),
  ('2cddd33bf9f91479', 'ru', '9a7d4e0687b14e2b7cda406900b802782cd50a62', 'Выключить'),
  ('222d85297c06217b', 'ru', '36fff63ccbcd7bf96ac9014e3e482702fc2b02d4', 'Сбросить'),
  ('23e7463a77676d31', 'ru', 'bccc14ee7da1d20ff06b9ff2497087e8c7d9f28b', 'Discord'),
  ('1322e8bebba60a17', 'ru', '6853dca9066719a20454a8182b7bdbbf4d68df5e', 'Привязка Discord'),
  ('76fd56cb105bdb10', 'ru', '20063ad9053289cecaa20ae630ed2dd758282a07', 'Включить'),
  ('582670124134c55f', 'ru', 'd764961a0190b30c20bb741496306ead9a1ea719', 'Надеть'),
  ('09d89a5ed17a5b36', 'ru', '0f2ac9fc2d0300baafc50eda99f1f68f115de3a9', 'Экспорт тир-листа'),
  ('76839b71857b49bc', 'ru', 'c87f9c252d42a96f48c508b0dad1d7cb197bbf27', 'Лобби FFA не заполнилось — возврат в меню. Встань в очередь снова.'),
  ('3859fd8d26c1bd89', 'ru', '43ba37bd870c8bada62d152083999e8646000ca0', 'Счётчик FPS: <color=#88FF88>ВКЛ</color>'),
  ('6baeab76d10f6515', 'ru', '09fef5d8d9a3c86b2523fef60d512606e7fe0003', 'Ошибка'),
  ('489dabf2a6e97b73', 'ru', '699484ab4b5ed92860c4908c3ec251445dc25bf1', 'Найти кастом-лобби'),
  ('98e3859cbd3ba125', 'ru', '6d56e1c35678ccc6ae1324012172bb5876774aa4', 'Флаг подтверждён.'),
  ('fe7a4ade88f61c42', 'ru', '66640520cbee31c09da657ee2488012ccc40f1c5', 'Флаг: ложное срабатывание.'),
  ('fe35b612219f0afc', 'ru', 'a2e6462d89b355f988344af13d5467d6bd4d10b3', 'Помеченные матчи'),
  ('57458ad5ed088b18', 'ru', '2b653211244b09239b9e1d00d3de5a10b288a0dd', 'Форс-старт'),
  ('0a51b869b20517e8', 'ru', 'f14bfe467e47f12a5514df9247ea036e5251f589', 'Кадры в секунду, левый верхний угол. Удобно проверять, помогла ли настройка.'),
  ('b2afe4968bcc4aa7', 'ru', '120606dcac1a829f37539d9af0708360d5453e69', 'Получить код'),
  ('8e5062f3dfe20e9a', 'ru', '8d0a32ed63390771166c129d77e7019ed5faf21b', 'Подарить'),
  ('e195217b8dd18c80', 'ru', '5442e2b64fa09764b9f593867e59a97292c84059', 'GitHub'),
  ('c470426e6955e200', 'ru', 'fe7f3ff2587e3d130e5d52db5004c675ee655866', 'Рейтинг Glicko-2'),
  ('a68b1f17c3436d85', 'ru', 'a632ac0544d4b5dea727409a10ffa2a23c246da0', 'Свечение (bloom): мягкий ореол вокруг яркой косметики, арта карт и эффектов. Слабее = меньше и тусклее. Выкл = без ореола. Только локально — ничего не скрывается, сама косметика рисуется так же. У части предметов свечение нарисовано прямо в картинке, оно останется.'),
  ('a36511ec6cccf2af', 'ru', 'c57604db5869f60539c66f7caa4809f27133d314', 'Золото'),
  ('8269a27433f4d383', 'ru', 'f33ee72ceeb88cb5f896985ce5aab3403f5b5c47', 'Выдать достижение...'),
  ('d997b5b7f17ee80f', 'ru', 'b37dab8c0ef031eeb7a1530584d3d3a7c80629de', 'Выдать художника...'),
  ('e94131143feaca60', 'ru', '665bfd72831ac98231ad8352f88ee64ae4aacbef', 'Помоги с переводом мода - откроется веб-портал в браузере. Отправка доступна только после выдачи админом доступа переводчика.'),
  ('80f22c97cc0aac83', 'ru', '391e23160a547aa2386bfc6e88136f01474e87ec', 'Скрывает тебя из списков онлайн и недавно онлайн на главной.'),
  ('98a3fad8f87afa66', 'ru', '8cecc82d72d68f9151cb0901cfe40eeac15bfca6', 'Как это работает'),
  ('e75c80cd71770ea9', 'ru', '3c81f3e5dbb58583795d18d6b4d1d5d6fb61fd43', 'В игре — результатов пока нет'),
  ('58b772f9792e7de7', 'ru', 'be77e0d452a5b253d62f1b462dca9f79853f28df', 'Оверлей чата в игре: <color=#88FF88>ВКЛ</color>'),
  ('ec771eaf68f39ebf', 'ru', '4b631f69842530d659306c8f06dbad594a6b1807', 'Инфо'),
  ('511bd6cc33ca9a98', 'ru', '1b5500a5682ab59e4d75826a732e0c2b221fef3b', 'Оверлей ввода (слева внизу): показывает W, A, S, D, Пробел и обе кнопки мыши. При нажатии горит красным. Полезно для стримов и поиска пропущенных нажатий.'),
  ('e257fa5f452ec7c9', 'ru', 'a24644dfa7613e54acd8966b3c2c10881854a735', 'Оверлей ввода: <color=#88FF88>ВКЛ</color>'),
  ('937a7d64c4e5b069', 'ru', '7b4db7ef1fa23cfb5e115a2a2c89d46a6a2ebc4a', 'Интерфейс'),
  ('c6deea52290a01d3', 'ru', 'e0d73143de80d17e82de2e017ac156ca3b9c4e01', 'Войти'),
  ('bbfe7c253f769892', 'ru', '3c3ebcdf7b3f53e0dbab23a828dceb490ddeacdd', 'Войти в лобби 1v2'),
  ('210b4fb9ebf2be28', 'ru', 'a22e64b4885cfe3ca0f1a4cecc77d3cded063a49', 'Language  /  Idioma  /  Язык'),
  ('777608da05a9cc4a', 'ru', '53cd5d1778decb934a189c78a5655d1a89e0b9a2', 'Последние версии'),
  ('317d4929f4752d06', 'ru', '7e3520a9733111c30f7ea9191099a8c7d144a4d8', 'Выйти'),
  ('8e9e659354925cdc', 'ru', '0079a58339aa6045be471f8a0850cdbdbe1ee2b9', 'Выйти из очередей'),
  ('5f180b79d0ac42fa', 'ru', '38c987b3019663c25cb284dbb39be1249e4505be', 'Выйти из очереди'),
  ('5d98387d164dafd9', 'ru', 'b184a204463eaea71321073fcd40120e63116faf', 'Снять заявку'),
  ('73dbf9f880098214', 'ru', '02dceaeb2b12aa88ec87fcbae1520e6f97dd1690', 'Выход из очереди...'),
  ('ac71054abd96ce73', 'ru', 'f25d3c50abaee5db733fdf971a931d354780082c', 'Уровень 1'),
  ('7b1f1233cd6900a1', 'ru', 'a47ce0315faa83adea0805be565fd26648ba3f45', 'Загрузка недавних серий...'),
  ('3076a1f4dd6e2b2c', 'ru', 'b04ba49f848624bb97ab094a2631d2ad74913498', 'Загрузка...'),
  ('70ea7889f7bbb8aa', 'ru', '11a9c89722334e53865de12f16e44151a6372071', 'МАТЧ НАЙДЕН!'),
  ('11a8ce3b24581f0d', 'ru', '7b186e235f284107df6b4dbe6060d2b6a5d9f1e5', 'МАКС'),
  ('95e880d9ec642215', 'ru', 'abf0c9e2bd591cf88dfd596663185ee446929460', 'Управляй косметикой и получай 30% с каждой платной покупки - подарки и свои покупки не дают ничего. Смена размера или положения уходит на проверку админам; неподходящий арт могут отклонить или поправить.'),
  ('62017cfb23dc8d2b', 'ru', 'f9cdd3d419e43beb090cc154a41152fc7693148f', 'Свет карты: <color=#88FF88>ВКЛ</color>'),
  ('7360e52eca7e232d', 'ru', 'b9654a7b502b417a86b62f424f8d295435911770', 'Свет карты: свет и тени, которыми отрисована карта. Выкл = плоские, равномерно освещённые карты и больше FPS.'),
  ('f191cfa21f829bad', 'ru', '56b5171f1b34b209c2562ac1138f47cba321d54a', 'Тени карты: <color=#88FF88>ВКЛ</color>'),
  ('c0b1c898d81f830c', 'ru', '8605f969b685627b504e2187118f04a140ae4590', 'Отмечено как ложное срабатывание. Награды и серию всё равно нужно чинить вручную.'),
  ('b28c6095513b6482', 'ru', '2f86234d58aeb5c42903f4860c359d45fe00fdf8', 'Язык интерфейса мода. Черновики машинного перевода, пока их не проверят модераторы — текст карт в матчах берётся из настроек языка ROUNDS.'),
  ('eaae164b9973a5a5', 'ru', '709a23220f2c3d64d1e1d6d18c4d5280f8d82fca', 'Имя'),
  ('d0de71ee40ca3cbb', 'ru', '2ee61b35c40fa92c9003c05e1d840a53a57de02b', 'Новая косметика'),
  ('5bb3b488dc9259b7', 'ru', 'f80fd0c9d9fb230fee5ea75092709ea8f07d8023', 'Далее >'),
  ('95e4edfd85ad0058', 'ru', 'eddf8963477756fa3f004564792411af5a20f827', 'Нет данных таблицы'),
  ('9fac189ff37e47b3', 'ru', '29ac10d1f29b9a817ad176f846413aba22dcb719', 'Нет недавних серий'),
  ('753b9026b589b7e3', 'ru', 'bcdd436f6f0ca66e0f43f93e286fcf6b21dd8688', 'Не в очереди.'),
  ('066fa92cd9434a97', 'ru', '48f932335abd4b7ab52177929989d5898e3fe3b3', 'Ранее >'),
  ('5ef70f53892e5f41', 'ru', 'e3e83bc594cc7ecde3071f3c0b105ca0345809b2', 'Всплывающие окна о новых сообщениях и уведомлениях XP/уровня. Лог чата на главной обновляется в любом случае.'),
  ('bac8aa401a36bac7', 'ru', '44a5bdcfc33755caee572a800d414defd6733252', 'Открыть папку тир-листов'),
  ('0c1ad37d853b8de2', 'ru', '7b900634f9f53532c69e92a70ddf0d76c6727e0e', 'Открыть папку загрузок'),
  ('9aa15709e7599312', 'ru', '1d82b1402be0f0e5cdcf5c6bfbb510b84cf551d3', 'Соперник не зашёл — возврат в меню. Ищи снова, когда будешь готов.'),
  ('c41b2ce8fb195cfb', 'ru', '34bd1f98b5ff53c0ec64db58e11c8ba454e1c881', 'Выбери время старта (сколько хочешь)'),
  ('30b0f82ce6dc5c3b', 'ru', '4f795bce846c0e7c91c35b77741a9e4c2b77aaf2', 'Пинг / регион: <color=#88FF88>ВКЛ</color>'),
  ('371ca2ac52232538', 'ru', '791cf8113eee5c723d227c59846570d1b6283e08', 'Играть (без паузы)'),
  ('2b298b7271502c6c', 'ru', '392feef07c53c9a7b2763d1fd30fb3f0d68099cc', 'Игроки'),
  ('d57237dcfcae73a0', 'ru', '43637cfe355335aa2af0c5f7474edd1bbe4ddf5e', 'Сессия портала не удалась - вы вошли в Steam?'),
  ('b9da26eccc254410', 'ru', 'f759566b7428a79b95a6d43e534fa03154485cf6', 'Сначала нажмите Включить в строке РЕЙТИНГ - пинг RLFP только для рейтинга.'),
  ('2eb11481c6e1d81c', 'ru', 'f1fbb2b43dca281d0138f4fcc92543ad143ef0b1', 'Превью'),
  ('5873dfb6d6ce0071', 'ru', '3e8248e32edfca0c629622b5b669c2d9ce4d0917', 'Цена'),
  ('9f6ba43f78157173', 'ru', '4a4300888933d180d78056ae2875609cc168712b', 'Призы'),
  ('caf5eeeec3117ec3', 'ru', 'e04ea281201a233a32fca1d38f18e6f2ac668552', 'Призы и правила'),
  ('f011a454829fac7c', 'ru', '122c17aad3eda08a61675ed1002bce10fde0233a', 'Призы объявляют при открытии записи.'),
  ('80d04622a6a5d196', 'ru', '07a2ae0633edf8be3f1fc68f659230f653255a99', 'РЕЙТИНГ ВКЛ'),
  ('519e272ed084c741', 'ru', '092579473a08bd70d7ac3465596a270bce98cb2a', 'Рейтинг'),
  ('5c4c865c87f70972', 'ru', 'd7108e6ab5e6f45e23c2ec5fe23f129cf7d5631a', 'История рейтинга'),
  ('5f7707fef861204c', 'ru', 'd25149b5a5f3f6d2741e28fb6dfc7c7c7ae8fd5b', 'Рейтинг ВЫКЛ'),
  ('68d7eb35f0d51174', 'ru', 'a3e1e99f26208eb83034e08c40d2fa9b9e636088', 'Редкость'),
  ('7f8d50b8e50f6ae4', 'ru', '55ad58fffa08821614376510977de2bd74d273c5', 'Готов'),
  ('35a2b52c3f3448f1', 'ru', 'ef4016fa589e84e154f5828386f2d08741c1efea', 'Недавние турниры'),
  ('a2bbca7fa2249434', 'ru', '8386805ac1a372885719e9a22b45ad0ee7a6a723', 'Вернуться в матч'),
  ('41d390e62fe2dede', 'ru', '56e3badc4e6c5cc95e0ea5a9a878b9bd09f319d4', 'Обновить'),
  ('6f43d60195f6d487', 'ru', '89891d2edf2bd28e5b4952ef12239ee6da11ebd6', 'Отклонённые'),
  ('bced5e3b4f62b4c4', 'ru', 'e963907dac5cd5c017869b4c96c18021c9bd058b', 'Убрать'),
  ('68a61bb1c87662ca', 'ru', '77e4aa898269d071d37354feabcd688601921fb9', 'Убрали из очереди после 30 минут поиска - зайдите снова, если вы ещё тут!'),
  ('fc89dabf25a1093d', 'ru', 'fbb446a61a4468f5ad96947bdc0040fe036d44ee', 'Репорт бага'),
  ('7c822307c6b1c668', 'ru', '699209ea2c9bafabb100f17a87ff4792d228abaf', 'Репорт отклонён навсегда.'),
  ('4fef188706c2844c', 'ru', 'b702c754b815b4a29ee7571911b52c912154ae10', 'Репорт вернули в очередь.'),
  ('44bd426b0542d87a', 'ru', '583d156c59fe2e53385c84b50e54a60e4aa6f593', 'Отменить серию...'),
  ('a593067a8ec0d1b5', 'ru', '633f1246d9f9fb9ac561e393879b8a28b0bc7814', 'Убрать артиста...'),
  ('43a8dbc807b7024c', 'ru', '13255b407052cfd4a359f6e8e175137b48388a31', 'Отзыв согласия'),
  ('49c8adce945e10af', 'ru', 'd9baef5110422c5e7f32144bde9656cc19bc8806', 'SID''S COMPETITIVE ROUNDS'),
  ('b939a9ae4f89cb0f', 'ru', 'c4477dfa9e0ef6b9e35433b86e32cb10888ee6a8', 'СИНХРО (нед.)'),
  ('b4489e1753b09ca0', 'ru', 'b0b2b820bcfb2fa8bcf150c069f23c562d765014', 'Те же карты: ВЫКЛ'),
  ('af50d15ccc91d824', 'ru', 'fb37e857128f8e9e6452c1511f0f974a99accbca', 'Те же карты: ВКЛ'),
  ('5e96f965b35fd77c', 'ru', '71b36cbeefd3cb3cc776984731e0f86c9c663c32', 'Сохр. голоса'),
  ('8709d2a7417a8af1', 'ru', 'fb043b0389a26d7aed0805a82374ca520672afa6', 'Поиск: рандом'),
  ('0af12ce407aedc11', 'ru', '903dc15e26d8934a5bd54ce5dad491d5f406b9b4', 'Поиск: рейтинг'),
  ('843f580e89a1c339', 'ru', 'fb4e2d95d98953646b6c1b210ec64b47348fe61b', 'Выберите до 12 игроков'),
  ('3633461f3484ae77', 'ru', '7c6b3fea63421c1496aef5d5e0fcd1fe1105411a', 'Отправьте баг-репорт команде мода - описание, важность и, по желанию, логи игры. Кнопка Превью покажет, что прикрепится.'),
  ('73be4f1b886889cd', 'ru', 'ee7f6b62b61a12ec18d69e017d11a4a8e7c9c4aa', 'Инфо сессии'),
  ('ed811fd03e3e7985', 'ru', '758d7f7281c0192f6d09ba1663e7af25cc8c0e15', 'Включить'),
  ('67bfd40e0352aa95', 'ru', 'c7f73bb54d928922c3838bb789ee9fb8a5b1eb37', 'Настройки'),
  ('9711b68fef7e1eb9', 'ru', '55de88709232ec03a7618ceae9b2248419fdc862', 'Магазин'),
  ('ba7dca8a4cbe7f6d', 'ru', 'da679c68be32dbace626c9a143329c3cc63c44cf', 'Показывать Discord в таблице: <color=#888>сначала свяжите Discord</color>'),
  ('0949f07beef44739', 'ru', '4d9856099b56f185037bd58ccbdefdec3cf2f349', 'Показывать Discord в таблице: <color=#FF9966>ВЫКЛ</color>'),
  ('13035d18b3c5b6c2', 'ru', 'b76e070645519586f2e8526c52fc8df857477430', 'Показ золота'),
  ('23d6d84ae59939d7', 'ru', '223b8527cddb50f542113f5f695eb3275b59e7d1', 'Показано: Elo по играм'),
  ('3c78beb9819d89e3', 'ru', '9bab7bd9168724dde1e704ed3a7103e7399a2e30', 'Показывает чат сообщества в углу во время игры. Нажмите T, чтобы ответить.'),
  ('0e6859e372c55b36', 'ru', '5f080b6372a7db5231fcb8805edd4b8ada17f6be', 'Показывает шлейфы у вас и других игроков с модом.'),
  ('14e6e248ad06ea5b', 'ru', '28e456cb2fc9eb62e6a90a66a3be46b85318cf16', 'Показывает имя Discord в таблице лидеров (по желанию; сначала привяжите Discord на главной).'),
  ('b802826c7bb214e1', 'ru', '415d6233a087d283a4ca8030301edf6599dfe13d', 'Показывает текущий регион сервера и ваш пинг.'),
  ('9e3df6c9efe7a876', 'ru', '928414d3088da4bcd44cf4682de27b4a7a01317b', 'Роль: Все'),
  ('1dea4fe7a34b66b0', 'ru', '5ea804d3a2d1d5bc3cb0429a135b43edc310bf0d', 'Роль: Соло'),
  ('5d86deb9c0e3f802', 'ru', '16c45d0311571f2a5866f4739eee429063e075cf', 'Записаться на турнир'),
  ('e268f01337cec8c0', 'ru', '09c26725abca4f5f770be1e26e44b5ee79b7a7bd', 'Заявки'),
  ('646589db10bb5f2c', 'ru', '908c1137c947ee99598d692d1d247169b67b174c', 'Мягкие тени от освещения карты. Выкл = без теней (свет остаётся) и больше FPS.'),
  ('5fc280a4ee756126', 'ru', '02ff65909856c0d4c47e5496f4e5df4964c3982f', 'Продано'),
  ('26cdd20b423a5097', 'ru', '9ae467b5d5e0a54b70a78d38a1b96d8219c6d628', 'Доп. карта соло: ВЫКЛ'),
  ('c0ff08581181780a', 'ru', '11ac349e24b8d6338b41fb21be03420ca2abf1b8', 'Доп. карта соло: ВКЛ'),
  ('a9e4235a8b94ba63', 'ru', '365f992a0a10615ba2ae06d707bb66c9e6c66bbe', 'Начать игру'),
  ('01a2f5687a851390', 'ru', 'bcecf4562f1709b1448aff7c6b49edb6acecdb12', 'Запас'),
  ('6af9389a92c0a962', 'ru', '9e253470c876ee6d5c720eb777aeb82d4c26e28f', 'Стоп'),
  ('bcc7673bc97a4ef3', 'ru', '24338c588a7c02e9f6f4cbf38c0da960808fc6e9', 'Не избегать в рейтинге'),
  ('4c3422795023e95d', 'ru', 'db825a8ff1b5076df3201c8038e1efe1606429ba', 'Поиск остановлен'),
  ('4f2532a4d52ec616', 'ru', '8d3f894fef9a0d6167b3bc9a6cbb1e4536c3656b', 'Этот аккаунт не зарегистрирован как автор.'),
  ('3836763834fbb27e', 'ru', 'f5b022a24101fc5adb935f8dd1359ad661f7ea15', 'Перевести SCR (веб-портал)'),
  ('a13da205cf3e6b93', 'ru', 'de6c0edd74bd11469c959c7269b1894c011895fc', 'Введите !link КОД в Discord'),
  ('5e52fd220fd26006', 'ru', 'd2671bfbfdd28d9143047f6a5239296f8a690156', 'Разбан'),
  ('7567c90e85adfb18', 'ru', '12aabd251c4213f1cebfe4cb83e6547df55552c3', 'Разблок.'),
  ('701947c757af5fa3', 'ru', '6df7395e6a96187a22b6cfc54a7672e0323a6d78', 'Незакрытая кавычка — /report "Имя С Пробелами" [причина]'),
  ('8130edc9d99316e3', 'ru', '11442128172c9afd9632fadcdf0aa392e5083094', 'Снять'),
  ('dae179ea3b8774a4', 'ru', 'bc7819b34ff87570745fbe461e36a16f80e562ce', 'Неизвестно'),
  ('ade79993560f1bf0', 'ru', 'fb91e24fa52d8d2b32937bf04d843f730319a902', 'Обновить'),
  ('f21486a74e18c3bb', 'ru', '7b0543786aca645a0c22d2b047ede094e3ca42c4', 'Загрузить косметику...'),
  ('b5cadb3a41019d3e', 'ru', '4a26389c62013544b114efb52635035677621f0e', 'Графика и эффекты'),
  ('30f54024c484dfa7', 'ru', 'e9ec8b04b776b9c340c2b12d163577e69c861c8f', 'Ждём соперника...'),
  ('f8465990452e8309', 'ru', '297f06ad75081de5ae834632a5e00a251ff00202', 'Победы/Поражения'),
  ('6ecfb3dab02b8467', 'ru', '28271452910576a33933fb47d894f1e4d8a6eb87', 'Ваш матч FFA продолжился без вас — вы удалены из него.'),
  ('633dc1e39f94d3a0', 'ru', 'a1a912243dc59524cca780830160df18bf83b01c', 'Ваши места: <color=#888>завершённых турниров пока нет</color>'),
  ('b1106ea1ec6e7b1e', 'ru', '45a6f9adb1df3a78aafc71391c7d3bfa7680229b', 'истёк')
  -- ── wave 3 (2026-08-03): 233 new keys x es/ru — consent modal, achievement
  -- names/descriptions, How-It-Works docs, TrF template conversions. Same
  -- sentinel proposer, same NOT EXISTS rerun guard.
  , ('2bb1bf93b17bd29d', 'es', '084be6fc3f55fa36a3d40c683fad5e686ff98f7a', '   (Series totales {0} - {1})')
  , ('5b55ed08358bfee9', 'es', '50e2e93f65bd2bd960221ee26b92edfba8b35840', '   -   CASUAL (SIN ELO)')
  , ('e0fcf786dd7b7b90', 'es', '715f30506d8f436b4787b770a4cc87eabfae38f5', '   -   MISMAS CARTAS PARA TODOS')
  , ('91be82a18dd171cd', 'es', '62bc9bd22039bdff56e0bd4fcee58186d7e082de', '  ({0} en cola)')
  , ('2162e2c2b5f464fe', 'es', 'e4f560bd5c376f04483f27e865429b9aa02616ec', '  <color=#66AACC>El {0:F1}% de los jugadores lo tiene</color>')
  , ('99fb1e843ffa48b1', 'es', 'b6de50bf861dc8814de845b4ea604d7139f92ae4', '  <color=#7FDBFF>|</color>  <color=#AAAAAA>{0} en línea</color>')
  , ('410c6b3196db19e4', 'es', '491a2892516650e2efb2b13a1bbef1914af24555', '  <color={0}>Racha de juegos: {1}L</color>')
  , ('9e6e059ee1f6f9d8', 'es', '131ff12826d9ed6fe685a77c1fbee5a166346b70', '  <color={0}>Racha de juegos: {1}W</color>')
  , ('3f7d936b214a5c44', 'es', 'e6ef24456d8cc38ec788b19b6efe193194317345', '  <color={0}>Racha de series: {1}L</color>')
  , ('b0196ae3471ab703', 'es', 'b1c82e918d4d6bc3462d09c8a72e196ccc681b2c', '  <color={0}>Racha de series: {1}W</color>')
  , ('aa62f023a76d12a0', 'es', '43662c1f038c90a664be45e6511968bab3328abf', '  <color={0}>Racha: {1}L</color>')
  , ('41a1ec5a6ed468da', 'es', '80e78a92f3f309fc0c1a71575668bfebae1fdbc0', '  <color={0}>Racha: {1}W</color>')
  , ('3df52f1d70da786e', 'es', 'de13cba6d1b25ba9af841a7cc5323f04b74b5fd7', '  Mejor: {0}W')
  , ('c23c3f556d4a1843', 'es', '774994f54715e39266a6307618d901ad7fd66269', '  Daño/juego: {0:F0}')
  , ('783de471a77b0e7d', 'es', 'f4b973bce333a3966b7fb58036443649af4dd861', '  Top 3: {0:F0}%  Kills/juego: {1:F1}  Puesto medio: {2:F1}{3}')
  , ('b50df2e13f58ab02', 'es', '3b88585ccc7066af5df23fdfd4cd1d8b7d835a49', '  [Rival listo]')
  , ('b89dfee35f251973', 'es', 'c94d1c070e24745e5257b847aa68b945bb5b953c', ' (Jugar Ahora enviado - esperando al rival)')
  , ('d4fad156d78d0d23', 'es', '79ee5562e90ab9cb7bff0affa6fe06d4ff9292d7', ' (ambos pulsan Jugar Ahora en F5 para empezar antes)')
  , ('51bc6ddfd6c32b36', 'es', '6f3c170bd545215b8832f0798382db9a53474f4b', ' (paga {0}g)')
  , ('a6027f92c31ba8ae', 'es', '2446ef58482e38247e7a667e3e9d471dd04f3d0b', ' a x{0}')
  , ('3feec5e324dfa40d', 'es', '31d4e7e7f8198ecfd215007826c85110b751108d', 'Próxima partida de torneo vs {0} en {1}{2}')
  , ('7cf635369783ef29', 'es', '4b4df825f33c5b554ba0e5497502d215a9312846', '+{0} de oro')
  , ('4ec92382f6f9cb9d', 'es', '9791b16ad92597fac04aa01430afe801ee5efe2a', '0 en cola')
  , ('d43beaf2e3883572', 'es', '07ea834b31ed15ee1715eb167f8547bad7f65dd2', '1v2 - Cómo funciona')
  , ('214528f7f4bc262d', 'es', '74e647231db3f6b2acc2c4622670eb503571289e', '1v2 - SIN ELO')
  , ('bff6b92b6c3e21d9', 'es', 'a18f84a9578aa306f34357a39593e4ed8dbd4bd2', 'Serie 1v2: Dúo {0} - {1} Solo')
  , ('c79a4645d2d603b4', 'es', '21632c13e41daeae9f16c3ca8ba543066827c789', 'Serie 1v2: Tú {0} - {1} Dúo')
  , ('b7cb3e6397fae3d6', 'es', '14d9e8634fcda42da86d1e2e895ca982372d4091', 'Serie 1v2 completada: {0}')
  , ('b4cb6205235dd418', 'es', '109cf27fd85482c00b4a6b6dbb2bbc91dcfba193', 'Serie 1v2: {0}')
  , ('fbb9ace819dbb6d6', 'es', '733e7baa95c66d1bfbac67551bcb7ada2719b69e', '2v2 - Cómo funciona')
  , ('8b5f2687f21600fb', 'es', '7ac0188cbabf0fd05b7d9632be98fdd87d9a2909', 'Gana 5-0 a alguien con Chase')
  , ('79dfe1086dd7baf2', 'es', '432a2d747a8cecaee4d8b0bbd8d11cbd131b8264', 'Gana 5-0 a alguien con Glass Cannon')
  , ('192168566e2a4d06', 'es', '1f256a9c14d5d3d94832169123cda8455fa2d393', 'Gana 5-0 a alguien con Mayhem')
  , ('182e3a5b598b14a6', 'es', '2179b8cbc74315cc138f2e55ff114e7aa047c749', 'Gana 5-0 a alguien con Sneaky')
  , ('9d4c37736ff9f3b7', 'es', '34daab9d40d35ab456c9e77cc9ccc2f623be684a', '<b>Clasificación 2v2</b>  <color=#888>({0} con rango)</color>')
  , ('03e012cf2d13a440', 'es', 'b49834782c6f5863a88153d700c99fc2170b14a4', '<b><color=#FF6688>* 2v2 en vivo ahora</color></b>  <color=#888>({0})</color>')
  , ('b62d5ca0a5ad78ca', 'es', 'b8aaf38308c25d47561a9defc03824a7d17b61d8', '<b>Salas FFA abiertas</b>  <color=#888>(ninguna ahora)</color>')
  , ('b5d62dcee8924655', 'es', '1780f3134b55989a3e3145349cc2a4097f142ddd', '<b>Salas FFA abiertas</b>  <color=#888>({0})</color>')
  , ('585c940fef29ab1e', 'es', '48f98d176879695850180ebf56c1e062da18d1be', '<b>Últimas series 2v2</b>  <color=#888>({0} en total)</color>')
  , ('09deebcae22bfb20', 'es', '6090fa2a628d137cb9870d67b69616b188ef5dd3', '<b>Tu sala</b>  <color=#888>({0}/{1} - el anfitrión inicia con {2}+)</color>')
  , ('334e17a45a59367f', 'es', 'fd96da4284df8057fd8a9e8c7ed13ea5d22dbdc0', '<b>{0}</b>  <color=#888>(vacía)</color>')
  , ('250dcc5547b47d05', 'es', 'a337367fad680421586b92e5238764e639863dbf', '<color=#66DD66>¡La partida empieza! Entrando como jugador {0} de {1}...</color>')
  , ('65a32e66177882b6', 'es', '8bfb3dcc1c64782da5cc10b57aa42cab47e08f32', '<color=#66DD66>Tu sala está lista.</color> {0} dentro - pulsa Empezar o espera a más (hasta {1}).')
  , ('bad2106299b6b752', 'es', 'f4364485a44965c7c825bb1e59144457e7b4ec5e', '<color=#888>No hay nadie en {0} ahora mismo.</color>')
  , ('8ab0cac8979c2a8e', 'es', '4f6b1c688d3001ecdab71a07919714cf0227e832', '<color=#99AAEE>Conectados recientemente</color>')
  , ('e91d1e0a65eab267', 'es', '8f1df6a51b94dd5af8db679c73a8d3cb4f2eea32', '<color=#99CCFF>Bloqueo:</color> -')
  , ('bcdf653ee83bbe53', 'es', 'c7635e1e070552f04640a363f9b42688d920f5c7', '<color=#99CCFF>Bloqueo:</color> {0:F1}% ({1}/{2})')
  , ('9f62981453f64b39', 'es', '70ae4797d016b4c6d8c1dba02cc9c83aac00df86', '<color=#C48CFF>FFA:</color> {0}W / {1}L ({2:F0}% victorias)')
  , ('fb110029669916f2', 'es', '995bd7e24afe7fc688d2026b7dd199ce6cbec2a3', '<color=#FF9988>Acierto:</color> -')
  , ('6527d25181574b70', 'es', '39a0a4745696d6845086d5a0a336ee7ae6cedaf1', '<color=#FF9988>Acierto:</color> {0:F1}% ({1}/{2})')
  , ('28f68e8f4b5e031a', 'es', '644c522f19a0e7153b4f63cb958665eb40c20b7e', '<color=#FFB347>2v2:</color> {0}W / {1}L ({2})  <color=#888>Rating:</color> {3:F0}  <color=#888>Pico:</color> {4:F0}')
  , ('e635b598d330a8e2', 'es', '7ae1c8b04ad592dfcf2b268a33874715bec934da', '<color=#FFCC44>En la sala de {0}</color> - esperando a que el anfitrión empiece ({1} dentro).')
  , ('5effd06b69376e5b', 'es', '5c1fa7d0cda455f717492a0bd5cfa35aee09c9a7', '<color=#FFCC44>Eres el anfitrión.</color> Esperando jugadores - {0}/{1} para empezar.')
  , ('b427669f556ea7bb', 'es', '02915b624b288814df3f1ae1b33365dcc0c576b3', '<color=#FFD94D>Skin de mapa:</color> <color=#FFFFFF>{0}</color>')
  , ('af3d1bf4c8be9543', 'es', 'f89bf703606cf6e63f8874ef15d32c00fac7e208', '<color=#FFD94D>Ranked (series):</color> {0}W / {1}L ({2})')
  , ('fa2645b70f9f5d77', 'es', 'a777582de015d6aa189d5e987dbb22330ea290f1', '<color=#FFD94D>Ranked:</color> -')
  , ('d5984dd5e64c618a', 'es', '670a333677a5cc92eb43fc800aa6d4eebb14a325', '<color=#FFFFFF>Sala de {0}</color>  <color=#7FD4FF>{1}/{2}</color>  <color=#888>abierta hace {3}</color>')
  , ('68df4873f949229d', 'es', 'f474f703aeed6b41dfd3481051df0c1ce534977e', '<color={0}>*</color> <color=#FF6688>Partidas Ranked en vivo</color>')
  , ('b2589813d7fe449c', 'es', '5bf5fdcdb65caf6b9ba3b018c97ee583e7630856', '¡Logro desbloqueado: {0}!')
  , ('08b1965af9d1ef0b', 'es', '4e7afebcfbae000b22c7c85e5560f89a2a0280b4', 'Admin')
  , ('20a200b93b0f4139', 'es', 'c663090066ad025d9f11faa0246cd410f6c5acf4', 'Saldo: <color=#FFD94D>{0}</color> de oro')
  , ('0b0990c45b3d1a1d', 'es', '8f54cd247fc90332d744f53159d73af22c2490ee', 'La apuesta falló: {0}')
  , ('2e42add77b4663b9', 'es', '91a4e283dd12cb9b87870f138798c38ee0d8ea42', 'Apuesta hecha: {0}g')
  , ('1cfe92e5e2faa80d', 'es', 'c51d1dc4be72787b45001281f94ad8d9d4d99c85', 'Apuesta hecha: {0}g al Equipo {1}')
  , ('8a9eeeb61d6172d8', 'es', '6e38da544ee550b4c1c1ee181a958f6aa9b2dda0', 'Apuesta hecha: {0}g{1}{2}')
  , ('b4ea9e5d44aae6da', 'es', '976fb1e69feae18b6c510f95d15c6df37b1954db', 'Color de cuerpo')
  , ('469f96b6fdf6a7e3', 'es', 'c2d5519c0f2e7db2a59a35a4ac44acbc2a6b42f6', 'Infierno de balas')
  , ('c30091482c3aed14', 'es', '2cf7c1c459ffac7b7755411c28a0fbd27b7ec2db', 'Stats de cartas')
  , ('7d55d57f5ad506dd', 'es', '1e0bf83f8ad8121c68bb5c86364ed4e207d8098c', 'La elección de cartas se cierra en {0}s')
  , ('2336cf45edf6056b', 'es', '7f89e50558edac544825522ec264018f192008a5', 'Conquistador casual')
  , ('ec3bbc79c58671cc', 'es', 'fc34d0bcd4850d867f1b6d5e71e32128dfd8ec52', 'Casual: -')
  , ('0552e283e3175aac', 'es', '571d9fa39175e85bb1e887c25267c5b620e5e62e', 'Casual: {0}W / {1}L ({2})')
  , ('1412a8a90c683fb3', 'es', '65ab9f618934bfa3ace72bac702ee7ca3f2ecbab', 'Club de los cien')
  , ('41f5f5cf24a035df', 'es', '4c26512201170dc20cac5a9bf043bfea51b6eb2b', 'Clutch')
  , ('33bda1024d57e8dc', 'es', 'e3199d24849eb82131394ea88ac9c22db0dbf732', 'Coleccionista')
  , ('f3e1ca269a596f07', 'es', '8d105cf44d3926289e65c1c83d8e37cb23fd049e', 'Comparar')
  , ('ecd2dadccaae041d', 'es', '8b7d0e0643225d0905a09fd3c73bf19c5d45ad5f', 'Competitive ROUNDS — Consentimiento de datos')
  , ('675047dd2ba5fab9', 'es', 'a4e08a5b9cbd3ab4220ac58c80a41675bdeb184e', 'Controlled Burst')
  , ('abf4f1283922dcc9', 'es', '9555b604bb2b33b5e29fe2c53ae409befbe84d79', 'Cosméticos')
  , ('1a2cbebcdb936308', 'es', '2239943c8d0af354a467e6cc18b9ec9e32f2afcf', 'Cursor')
  , ('de379bda8218c892', 'es', 'eea9bde7e430f89af34682373a2064689a282948', 'Salas custom')
  , ('acda0f3497987f2a', 'es', 'bbe6a0d4c7d69d2481e2d3224d708c68e8e22709', 'Rechazar (modo offline)')
  , ('9633ce2741a0b7cb', 'es', '3d44114e197112dc928b1b5e54ab7c91d191dd29', 'Demoledor')
  , ('3cceb107a990d449', 'es', 'dd9ef4e5a287b8269c0300bdefaaa072c8f4148e', 'Nova doble')
  , ('366e5c083f800ce2', 'es', '872a0ac7105096e62dc0d9a9342fd454369241b3', 'Dúo -')
  , ('25e3c84b4a5ba59f', 'es', 'f9a96ae8d3343e98d3017e9bb5e94de28b0e57b9', 'Dúo {0}W/{1}L')
  , ('d07b8c2b5af84abf', 'es', '92cfc28e94f00f9407f870995c85eeaf388a1e30', 'Obtenido por {0} jugador  <color=#888>(en orden de obtención - clic de nuevo para cerrar)</color>')
  , ('f0dc3f4c961b805e', 'es', '09d9fbb99911bd6d0227907a47221c12a2db9ca4', 'Obtenido por {0} jugadores  <color=#888>(en orden de obtención - clic de nuevo para cerrar)</color>')
  , ('47b4415f4d6a7d63', 'es', '8f25a859269ca51039632dd6bba28fb061cfb8d4', 'Efectos')
  , ('62ce5181e5a602ca', 'es', '90ce5340a6531dab9e5c720670abf91bb7d42fc4', 'FFA')
  , ('d820383e18f33ceb', 'es', 'bc6c4123d4239b8e45bc714df9bdbcd2cfadd872', 'FFA - Cómo funciona')
  , ('d14df263eb7a220f', 'es', '67a5c91fdef543bcdf7b7bdc9f5efedaee64ff1b', 'FFA - {0} jugadores - ¡el primero a {1} puntos!')
  , ('e46943688b727f28', 'es', '3b64921f2960bf7a10b9e3f462af56594d56d312', 'FFA EMPIEZA EN {0}...')
  , ('da7931ad7df4a64a', 'es', '16bc5bdd632da2ad2fd7bce2af52ce21d3809eb5', '¡VICTORIA FFA! +{0}xp')
  , ('b805204de1dc17d6', 'es', 'a926b4d61bf2b690aff0b07a8b6c41bdebdde9c9', 'FFA cancelado - no hay jugadores suficientes para una partida nueva.')
  , ('da364c22af80c86d', 'es', '514a72f6e0de5d80e678c0de5bd652d724192627', 'FFA: puesto #{0} (+{1}xp)')
  , ('5dd21d2b1effe3ed', 'es', '37ec0acb9e53c4780bc0c0fe2454681fee5cab89', 'PRIMERO A {0}   -   {1} ROBO INICIAL   -   MANO DE {2} CARTAS')
  , ('ef416e27d17769c6', 'es', '3473dbe7c23ff2a47b4c0db0213ea2c31730da1d', 'PRIMERO A {0}   -   {1} ROBOS INICIALES   -   MANO DE {2} CARTAS')
  , ('c332f8d24db253b1', 'es', '9c456cc81aecc69b660c85dcac67dc9de04f91cf', 'Médico de campaña')
  , ('330d515b831a2877', 'es', '4731820fcd676f537c7e098544de7386184f7324', 'Termina una partida con exactamente las mismas 5 cartas (y copias) que tu rival')
  , ('2267d5721109f6dc', 'es', '88c0562022ffeb4ef8821335d8fa3e20823550a1', 'Primero a:')
  , ('53dc540a825baa09', 'es', '22b9ee43aaa645b2356c82a81cf4f411e51328e8', 'Impecable')
  , ('4e17aa7c25efb66c', 'es', '93c0c7428061d19b5ae907ba7820e19445811f4b', 'Perfección frágil')
  , ('c5b99e4ded85c126', 'es', '9d483832cb5867ebec6781d58957b7499d904cd6', 'Todos contra todos para 3-10 jugadores. Cada jugador
es su propio equipo.
Puntuación estándar de ROUNDS - el primero a {0}
puntos se lleva la partida.

<color=#FFD94D><b>CÓMO SE JUEGA</b></color>

- No hay banda de Elo. Entrar a una sala es consentir
  jugar.

- Crea una sala o únete a una abierta desde la lista.
  El ANFITRIÓN pulsa Empezar cuando hay al menos 3
  jugadores (hasta 10). Puede haber varias salas
  abiertas a la vez.

- Si el anfitrión se va, el miembro que más lleva
  esperando pasa a ser el nuevo anfitrión.

- Tras cada punto, todos menos el ganador del punto
  eligen una carta a la vez.

- El tiempo de elección se ve en pantalla. Una elección
  cerca del final da a todos un poco de tiempo extra.
  Cuando tu tiempo llega a cero, tu carta resaltada se
  elige automáticamente. Siempre recibes una carta -
  saltarse una elección no es posible.

- Llevas hasta {1} cartas.
  Elegir una más sustituye tu carta más antigua.

<color=#FFD94D><b>AJUSTES DEL ANFITRIÓN</b></color>

- El anfitrión puede ajustar la sala antes de empezar:
  puntos objetivo (3-10), robos iniciales, cartas
  máximas (3-6), la regla de Mismas cartas y
  ranked/casual.

- Regla de Mismas cartas: el robo N de cada jugador
  ofrece las MISMAS candidatas, en el mismo orden - si
  a ti y a un rival os ofrecieron cartas idénticas toda
  la partida, ningún resultado puede achacarse a la
  suerte del robo. Las cartas de copia única (como
  Phoenix) salen como mucho una vez por partida para
  todos.

- Tras un cambio de ajustes la sala no puede empezar
  durante 60 segundos (y un momento tras entrar alguien
  nuevo), para que todos lean qué cambió. Las salas
  casual pagan recompensas reducidas y nunca tocan el
  rating.

<color=#FFD94D><b>RATING</b></color>

- El FFA es ranked con su propio rating Glicko.

- La posición usa puntos, luego todas las rondas
  ganadas (incluidas las gastadas) y luego las kills.
  Los empates restantes comparten puesto en orden de
  competición: 1, 2, 2, 4.

- Tu rating se puntúa contra los jugadores colocados
  más cerca de ti (hasta 4), así una partida no puede
  mover tu rating varias veces más fuerte en una sala
  de 10 que en una de 3.

- Un puesto empatado cuenta como empate. Los ratings
  nuevos se mueven rápido y se asientan al jugar más.

<color=#FFD94D><b>RECOMPENSAS</b></color>

- La paga se mide por la LUCHA, no por cifras planas
  por partida: las rondas decisivas son la unidad de
  trabajo, y el tiempo transcurrido limita lo rápido
  que se cobran - las tácticas de alargar quedan
  acotadas, y las partidas más largas y grandes pagan
  más.

- Las salas más grandes pagan mejor tarifa por minuto,
  y un FFA de 10 jugadores es la mejor tarifa de oro
  del juego.

- Tu posición define tu parte: el 1.º gana unas cinco
  veces lo del último. Parte se paga como XP, parte
  como Oro de posición, y un campo rival más fuerte
  multiplica el bote (el bono de tier habitual).

- La XP se convierte en Oro a 100 XP = 1 Oro, y subir
  de nivel paga su Oro extra habitual. Una subida de
  nivel durante una partida aparece dentro del +g de
  esa partida - así un último puesto puede a veces
  ganar más que el vencedor.

- Los espectadores pueden apostar Oro en las salas FFA
  desde esta pestaña.

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

- Salir a mitad de partida queda registrado.
  Quien se va conserva sus números para la posición.')
  , ('3083d95d9140b745', 'es', 'f4711dbd478dfa86591adfa28c7b9e2552cee2a3', 'PREPÁRATE - el disparo y el bloqueo se desbloquean en un momento')
  , ('1605fe375cfc39fe', 'es', '76eda7d248ecf2792fc4875e7baac32b49a2cd96', 'Consigue 5 copias de una carta en una partida')
  , ('be2399036371a377', 'es', '73a2014a6c0b4134cdd1bfd287bf0685a71ec92e', 'Brillo (bloom): <color={0}>{1}</color>')
  , ('077676d0bca7cfb9', 'es', '6dd2206f0985f5762623cca9ed3d8e1a74aa684b', 'Build divina')
  , ('949e54f8da1fbbb3', 'es', '0de1a3e213e5f886d02a66057987fc8a8fbd3036', 'Gran Maestro')
  , ('d0fb1e23e0d0e771', 'es', 'd5580b73bfb2949ac6d9534c49ecd66ceba94e8c', 'Con los pies en la tierra')
  , ('9914bb866193f854', 'es', '70f8bb9a8a5393ef080507a89e4b98d139000d65', 'Inicio')
  , ('946a03bb72a4fe72', 'es', '599812412c8e063215968af7cc448d65f2b3faa9', 'Inmortal')
  , ('3e6bea2210f7f3f3', 'es', '6be2477292a2c7282275bcb131607912fcdac752', 'Objeto inamovible')
  , ('5567eee60b51362d', 'es', '8b466a9d6a804f6268778e511de8a9906c9260cf', 'Instinto')
  , ('c3dcb3a7c99fa461', 'es', '104715a881fa08ef642df3c97be967c6383f5a4a', 'De cabeza a lo hondo')
  , ('de20704300c6edfd', 'es', '3a7f6bd064529d32665a9bfdacf161baab97a428', '¡SUBES DE NIVEL!  Nivel {0}')
  , ('fb0725b41f178ef8', 'es', 'ce2864f02b751fa6f9f141839fa847756de688c5', 'Idioma: <color=#88CCFF>{0}</color>')
  , ('bd8b0169d8b34641', 'es', '0381247a698736fe9930328a814e5263eeff72fd', 'Clasificación')
  , ('2bef0e5cdc0b94f1', 'es', '8051c09f7c6dfc8c86a8ea94b528253ae4137333', 'Nivel {0}')
  , ('15452feadbac32bc', 'es', 'd5cc324443a8277d639cfc7dc37ca9a42af3ce3c', 'Código de vinculación: {0}')
  , ('a2667beef62b6d0c', 'es', 'ece6bccb7dadb22b3b86139b68efb42a8ea3c7c1', 'Viviendo al límite')
  , ('acc86de9b59c25db', 'es', '32ed08835c994efa3c32d263129bb8a259d54463', 'Leñador')
  , ('dd9ed6335db7e352', 'es', '8d42a8ff760a17a66d663d7b77b0ee840976a372', '¡EMPAREJADO!  vs {0} ({1:F0})')
  , ('db64d34801d9c8ef', 'es', '80071cd75107cd5c4afdb2571725ea6733631038', 'Mapas')
  , ('9643b3e6281b9dcc', 'es', '78f3842f0201c993fec13905f2ff9ec3fdd39056', 'Maestro')
  , ('d3b7f9d9c9b6c4e4', 'es', '63168ee6a276883f20338ce8d90a19f0d972d8bd', 'Cartas máx.:')
  , ('928589c9dfa0518c', 'es', '21bd0337ae7922983486f37b7c1fea1c1a9c14eb', 'Multijugador')
  , ('a65804c100e5f740', 'es', '0cb450ece94fd1c07223dd69e80d9684937e8b96', 'Mis stats')
  , ('a37a7555118c2dae', 'es', 'accb4a8ddf0f4d799e252e947a9e7c1de73a8dd1', 'Estilos de nombre')
  , ('831575d2b0643a21', 'es', 'ac0a3ea3db64d301c566b0246f5375709f7a6b14', 'Próxima partida de torneo vs {0} pronto{1}')
  , ('321e8a8231f9be1f', 'es', '3b1fef494a099a3b85cd74865db0a55fc89dcc13', 'Sin escapatoria')
  , ('741922dd9e900e6a', 'es', '8059b63e8a2ec48a76d5c678ff28583c5d065bed', 'En racha')
  , ('53e1c75349c012da', 'es', 'f6deacd33a1819ebbb127e5a239bc44ccd4c7302', 'Un jugador solo se enfrenta a un dúo en una serie al
mejor de 3.

<color=#FFD94D><b>CÓMO SE JUEGA</b></color>

- Es una cola por consentimiento, sin banda de Elo
  y sin confirmación de listos.
- El servidor asigna un solo y dos jugadores de dúo.
- La Carta inicial extra del Solo es opcional.
  Si alguien la activa, el solo roba 2 cartas en la
  elección inicial.

<color=#FFD94D><b>PUNTUACIÓN</b></color>

- El primer lado en ganar 2 juegos gana la serie.
- El 1v2 es una beta SIN RANGO. Aún no se aplica rating.
- Los juegos se registran y contarán cuando llegue el
  modo ranked.

<color=#FFD94D><b>RECOMPENSAS</b></color>

- Cada juego da 500 XP.
  Ganar el juego da x1.5, es decir 750 XP.
- Ganar la serie da 40 de Oro a cada ganador.
  Perderla da 20 de Oro a cada perdedor.
- La XP de juego se convierte en Oro a 100 XP = 1 Oro.

<color=#FFD94D><b>COLUMNAS DE LA CLASIFICACIÓN</b></color>

- La pestaña tiene tablas separadas de Solo y Dúo.
- Solo apareces en las tablas de los roles que jugaste.
<color=#7FD4FF>Rank</color> - Orden de actividad: victorias, WR, juegos.
<color=#7FD4FF>Player</color> - Nombre visible del jugador.
<color=#7FD4FF>W-L</color> - Juegos ganados y perdidos solo en ese rol.
<color=#7FD4FF>WR</color> - Tasa de victorias en ese rol.
- Son tablas de actividad. No se ordenan por Oro.

<color=#FFD94D><b>OJO</b></color>

- Salir a mitad de juego queda registrado.')
  , ('34655ad48dcbf535', 'es', 'ac89cf0bce0114f396b22577093558484dbf3cb9', 'Robos iniciales:')
  , ('90df54c06a4560da', 'es', '6e6a6f2086bb5fe5dbfd17d8d5f502d48759834b', 'Otros')
  , ('22aaa9cf5852d31c', 'es', '34b31f7c574f47f91bb097cc3a682e84995a9325', 'ELIGE TU CARTA - {0}s')
  , ('65fcf4378f18e10e', 'es', 'eacde01371d3cfecd1d6868ac0dc890330df9229', 'Pacifista')
  , ('49923e671981b95e', 'es', '960ab5ab0edb01f24063eaa58f2593eab46db25c', 'Pristine Perfection')
  , ('9e1369ddd08e1d16', 'es', '6ad85c9fff5b14b6cf3d9aae3688c935e8f4cbe6', 'RANKED - Registrando')
  , ('7abf29cd482ae2c3', 'es', '585c9f8bfdd65b7176d0906cacf12b63bd0a5a16', 'RD: {0:F0}    Pico: {1:F0}')
  , ('54eee8c1199323da', 'es', 'f55cf47ab80a74cedc526b6091d08157c647d6d3', 'Ping RLFP disponible en {0}m {1}s (1 por hora).')
  , ('242f5f5f70d848b7', 'es', '6136170d5d17ddca75e9d37f52c04c12fc73a7ea', 'El ping RLFP falló: {0}')
  , ('6628289042207194', 'es', '09e9637fcb1efff7cf0100fe0a14567427177caa', 'Cola aleatoria')
  , ('eae155f580deb959', 'es', '9fcd0e210699f50c689ecb8e2fc7fa9105367085', 'Llega a 1700 de rating en ranked (1v1 o 2v2)')
  , ('3a98b73fa17d67ba', 'es', 'c7d01b0524369fe5b3c996b27223026f6c017607', 'Llega a 1980 de rating en ranked (1v1 o 2v2)')
  , ('77b6364f7604291c', 'es', '4739f3bac2dbf726d75cb84d2cbe3551845e51db', 'Llega a 2330 de rating en ranked (1v1 o 2v2)')
  , ('58e34f41f31eb642', 'es', '51e8026c9a204f54a6bd4b1a2d8953138483eb22', 'Reanudando la serie en {0}-{1}')
  , ('4356e1f9e0e4cc96', 'es', '97800f5d41e76e932cfd498fd7502f99f1e80a04', 'Renacer de las cenizas')
  , ('5ab18e987855fcf3', 'es', 'f2f5d68e6499e7eddf0b08d8dbbc483e134f6843', 'Estrella en ascenso')
  , ('5c65ef160d2f5147', 'es', '420b7ab0cb9993c4d5ddeec670cee91d97fb4b2c', '¡SERIE COMPLETADA {0}!')
  , ('d7951aef0fa367af', 'es', '7e0098e5bb901181e4f78f50b98fe1c46abf73b9', 'Buscando... {0}m {1}s  +/-{2}')
  , ('fdea4fee02fc1df2', 'es', '122661d9a77d8948a4efb1c1cf20a6a3cae1bfa9', 'Buscando... {0}s  +/-{1}')
  , ('cbe8c30cbcc7634d', 'es', '35b9dec4c725630964642fc46ef9413ab161ff40', 'Marcador de la serie: {0} - {1}')
  , ('2b6277b71e22c3a6', 'es', '366f6b0c2e95252863a672eae68c35cf6c90ed1a', 'Serie completada: {0}')
  , ('81d48a92efee6579', 'es', '7d8e33e493d338e360b00d9457e0ae44f44857c4', 'Serie: {0}')
  , ('18746c7ceab495d6', 'es', '6ab4534ed3f287fc8a0ea7a93221e16851853fb3', 'Sid Slayer')
  , ('410a15ed4e513db1', 'es', '1fd0163116cd53e22c4f164b9e475b32f563431f', 'Asesino silencioso')
  , ('4d580a51b66a9839', 'es', 'b5c2df0ee1dc21486cd644213de53f3f076f6371', 'Silly Drill')
  , ('dca34071afb963ee', 'es', '52381ad42460aca3d0250e9c8261b125d52754dd', 'Solo -')
  , ('fe6d0b0c1c99dfc1', 'es', 'ad4c0e8211de1e439cf86a7e625f06c86317b74c', 'Solo {0}W/{1}L')
  , ('892f1b97985931c1', 'es', 'c5db1144d4106184ee6562dda8f16d44f9d21068', 'Spray and Pray')
  , ('6f6c3c254ccd07de', 'es', '72a0000376276a7f054fdf34cbbc166d639c06e8', 'Baraja trucada')
  , ('3ec608bd07df3fb0', 'es', 'ae97475ace60cadda4ce2988ba3066b956b847c9', 'Stan Slayer')
  , ('f3d059d8adc3972f', 'es', 'af0151e8d21f97ebebc04a4921272e598ec5146e', 'Empezar (mín. {0})')
  , ('51a6d0e98b96103e', 'es', '95434373b1524d272dcd9345ec874d2a8b03b516', 'Empezar ({0}/{1})')
  , ('a84298c23afaf9c1', 'es', '3b54d47159162560b5d0cc9fabc031730a69223b', 'Inicio en {0}s')
  , ('5b789e3f0dcae3da', 'es', '24e70c2af4a5fd7a4c77d10b257d272c6d49b649', 'Poder sostenido')
  , ('6417f5d13dc1cd9b', 'es', 'c992e487ff19ddc4ae5cc59132442aaf46dd9b5a', 'Barridas: <color=#00FF00>5-0 x{0}</color>  <color=#FF6666>0-5 x{1}</color>')
  , ('aea09b3828dbdedf', 'es', '000192d1a8bc97d6ee60930274a5576366c228af', 'PARTIDA DE TORNEO vs {0} - conectando automáticamente, espera...{1}')
  , ('6449179f9d1f38ce', 'es', '09e233dea356e6cd5e938852f8755d561df79d21', 'PARTIDA DE TORNEO vs {0} EN ESPERA - ¡SAL DE ESTE JUEGO YA!{1}')
  , ('22bbf3bbfc5851b3', 'es', '23f7bcf444a010b5e29565495b64b0e169aab5bc', 'TORNEO EMPEZANDO - creando las partidas, espera...')
  , ('1ae13cdc903c028b', 'es', 'c32e6ef305f7305a05b6f89f622a0d6797911a18', 'EL TORNEO EMPIEZA EN {0} - ¡quédate en ROUNDS en el menú principal!')
  , ('4de0cd53889e1dbf', 'es', '4e4cd33a2506596163f467a032d1305efd4c07bd', 'Barrida en equipo')
  , ('be4894b729971733', 'es', 'f3e5625b48f6d3cb48733417bcdcf70a949419ae', 'Rey de la remontada')
  , ('b9c39cbeb97ffb3d', 'es', '0b4859fc9d77ed14bb61337fbaa484d5a31a7980', 'Este mod envía datos a un servidor privado gestionado por el autor del mod para dar servicio a la clasificación y al emparejamiento ranked.

Qué se registra si aceptas:
  • Tu Steam ID y tu nombre visible en el juego
  • Tu ID y nombre de usuario de Discord, SOLO si vinculas tu Discord con el código del juego
  • Cada partida que juegas: rondas ganadas, puntos, duración, cartas elegidas, cartas ofrecidas, rival
  • Tu historial de rating Glicko-2

Qué puedes hacer después:
  • Revocar el permiso cuando quieras (F5 → Ajustes → Revocar). El envío se detiene.
  • Borrar tus datos (F5 → Ajustes → Borrar mis datos). Se eliminan tu Steam ID, tu nombre y tu vínculo de Discord. Las partidas se quedan para no alterar los ratings e historiales de otros jugadores. El borrado es IRREVERSIBLE — no podrás volver a registrar este Steam ID.

Elige Permitir para usar la clasificación. Elige Rechazar para usar el mod totalmente sin conexión.')
  , ('a8e7491399151552', 'es', '698e542479926ac30ba7d470149597aaecb9e425', 'Se acabó el tiempo - {0} elegida automáticamente.')
  , ('1ea1bb377fdee4ff', 'es', 'a116f7255e19431f1fbf68cdd9f4dce3b66e6b04', 'Títulos')
  , ('e77878efbc01c8b8', 'es', '584febf2226943cce895111f9b1ff34d68fa3a3a', 'Total Mayhem')
  , ('4602ccfcb6641ef3', 'es', '21d10582916e120d4c8320df023f92494b61642c', 'Total: {0} ({1}W / {2}L)  <color=#FFD94D>Oro: {3}</color>')
  , ('65459268621110a8', 'es', 'a2c06f13201a8b0dd13595ac4dd0d24a7c4670c6', 'Touch Grass')
  , ('4254217c1c4f7bf9', 'es', 'fb10fa9913c39f956d36b21c5e77b85f398b20f2', 'Torneo en curso - tu próxima partida se conectará automáticamente. Mantén ROUNDS abierto.')
  , ('455b205f737f7f07', 'es', 'fee20df1963ec9531d0a42884334083687be1d13', 'Torneos')
  , ('1c5a31cb31fb37f3', 'es', 'abe7e366ae1c1eacb6ef6af9bb1d6c200b03a458', 'Estelas')
  , ('426d72c497d1fb76', 'es', 'd16e8b753f78e3ec681fc4f9b2778ef39c3809cc', '¡Gemelos!')
  , ('e8ed682b2d08934d', 'es', '8291e35ae377151b9711fbbc7c1b59a5e1517881', 'Dos equipos de dos juegan una serie al mejor de 3.

<color=#FFD94D><b>CÓMO SE JUEGA</b></color>

- La cola aleatoria usa una banda de Elo que se amplía
  mientras esperas. El servidor equilibra los equipos.
- Las salas custom no tienen banda de Elo.
  Entrar a la sala es consentir jugar.
- Los 4 jugadores tienen 120 segundos para ponerse
  listos. Si el tiempo acaba, todos vuelven a buscar.
- Tras un juego de cola automática con margen de 3
  puntos o más, el ganador más débil puede cambiarse
  por el perdedor más fuerte.

<color=#FFD94D><b>PUNTUACIÓN</b></color>

- El primer equipo en ganar 2 juegos gana la serie.
- El 2v2 usa su propio rating Glicko.
  No cambia tu rating de 1v1.
- El rating se actualiza al completar la serie.
- W-L y WR cuentan series completadas, no juegos
  sueltos.

<color=#FFD94D><b>RECOMPENSAS</b></color>

- Cada juego da 600 XP base.
  Ganar el juego da x1.5, es decir 900 XP base.
- Ganar la serie da 50 de Oro base.
  Perderla da 25 de Oro base.
- El tier de rating del equipo rival puede multiplicar
  las recompensas base.
- La XP de juego se convierte en Oro a 100 XP = 1 Oro.

<color=#FFD94D><b>COLUMNAS DE LA CLASIFICACIÓN</b></color>

<color=#7FD4FF>Rank</color> - Posición en el orden seleccionado.
<color=#7FD4FF>Player</color> - Nombre visible del jugador.
<color=#7FD4FF>Rating</color> - Rating Glicko de 2v2, separado.
<color=#7FD4FF>W-L</color> - Series completadas ganadas y perdidas.
<color=#7FD4FF>WR</color> - Series ganadas entre series completadas.
<color=#7FD4FF>Avg Mate Elo</color> - Rating medio de tus compañeros.
  Un compañero usa su rating 2v2 tras 5 series
  completadas. Antes, su rating 1v1, o 1500 si no hay.
<color=#7FD4FF>Gold</color> - Oro total ganado solo en 2v2.
<color=#7FD4FF>XP</color> - XP total ganada solo en 2v2.
  El Oro y la XP no afectan a tu puesto por rating.

<color=#FFD94D><b>OJO</b></color>

- Salir a mitad de juego queda registrado.')
  , ('5593dbe5ca8039d3', 'es', '39e6741f25d3f45d31f8790ca0b6174dca928597', 'Imparable')
  , ('44a291e8d72f6864', 'es', '32363366360c0121e17ca2a47b773d8e15bd3bc0', 'Intocable')
  , ('c2e6d9d121cad78b', 'es', 'a5213556d4c72afdc8eb34d8c9c1b6854bc20ddd', 'Esperando a {0} ({1:F0})...')
  , ('b11e9b8eb932f992', 'es', 'a62db852b1d4fd67229d8c1db9abc212214d14f9', 'Gana 100 partidas casual seguidas')
  , ('7878af0d6218e40f', 'es', '2b7036dfd10c1a088708a60f75f3ca0d3c38080c', 'Gana 100 series ranked seguidas')
  , ('c2080414dc4ad407', 'es', '6a83a7c5726697f6747faae9710baf615f3c39fd', 'Gana 200 partidas casual seguidas')
  , ('340a5f64fddafe56', 'es', '2a82cc109e90813127d860437aafeeb22673804e', 'Gana 25 series ranked seguidas')
  , ('dcea6ed7a205f942', 'es', 'c35aa7a4bc5418558d8050151209b86ec073635d', 'Gana 5-0 con Phoenix sin perder ninguna vida')
  , ('88e636ffe6099863', 'es', '7f8c92d2df2ed7b9d2de661abde38c650a78b757', 'Gana 50 series ranked seguidas')
  , ('0a1304bbfc6f8b68', 'es', '4d2a378dce953a8292d517344fabdca770c713d7', 'Gana 500 partidas casual seguidas')
  , ('498e2111639dc482', 'es', '52c738eb71779ebebb572ab7101e3ba0c99a061f', 'Gana una partida 2v2 por 5-0')
  , ('0a7f9dcfb7f7b30d', 'es', '0dc10933da1d6d92074a29c880208de24ac1736a', 'Gana una partida 5-0 con Barrage en tu build')
  , ('e86c99634581b48f', 'es', 'a00c23aea46eb757db62174a1007698f8d5679b6', 'Gana una partida 5-0 con Burst en tu build')
  , ('3d216c23dff44220', 'es', '0ef4874f3aef9de833424d6a9cef72c32e0f0291', 'Gana una partida 5-0 con Explosive Bullet en tu build')
  , ('7f68781b5d95c2be', 'es', '51684c861757561dafef3e283514ebf103cd7b8f', 'Gana una partida 5-0 con Healing Field en tu build')
  , ('3370f43648b2c0c3', 'es', '6adaa65a59b1108cebdbaa309fc74aa603c266c8', 'Gana una partida 5-0 con Spray en tu build')
  , ('0ab780cd5bee16fd', 'es', 'cc461b976cfa54f3f4fc80d112c44227fd752691', 'Gana una partida tras ir perdiendo 0-3')
  , ('372406d1b8cd9ace', 'es', '895f9f6d66f8bad245cd5e1e05e38d7705ea3470', 'Gana una partida sin saltar ni una vez')
  , ('7ff5a7c44329fddf', 'es', '0d164072c1c67cc0f40de17a0e756df812a9f276', 'Gana una partida sin disparar ni un tiro')
  , ('903bd2d1530486a8', 'es', '7ff9c6a9ec21ae6eee1aa022097cc772d6981aa5', 'Gana una partida sin moverte ni saltar')
  , ('154bb996c84705ea', 'es', '25d565c70ac31cc9a4e68446aefbca42024c1db2', 'Gana una partida sin recibir daño')
  , ('b0bbeabb2c6af5f3', 'es', '098f5df305727f005ed1895b5994020e1cc19406', 'Gana tras ir perdiendo 0-4')
  , ('bce06d48a403b9a4', 'es', '1792eca0039ac2d3327c9bf01f4dbca43e48e063', 'Gana a Sid en una serie ranked')
  , ('23a58ca68c16b593', 'es', '68d423046930d4adf98766d56162de081943e7f8', 'Gana a Stan en una serie ranked')
  , ('8385611059aa9da2', 'es', '7f852990398165dad77d4ed415dac0e63d4a1149', 'Gana cinco partidas 5-0 seguidas')
  , ('feb59a76f97cc1b2', 'es', '82e21ae0bb23c7bf1a5dadd5a70daa9e562ab824', 'Gana eligiendo solo la carta de más a la izquierda en cada elección, sin mirar nunca las demás')
  , ('ac570864590c58d5', 'es', '35fce3934da3c301073ba9a0ba73e8eba28a197a', 'Gana con Abyssal Countdown como tu PRIMERA elección, activándolo en cada ronda')
  , ('ba292685c6b16f5e', 'es', '061542f4315766fa49452c133d2445cf3c714521', 'Gana con Empower y Healing Field juntas')
  , ('beb56c01fc312e7e', 'es', '9cc4287e6d1f7c078c8ac963e9cd8f292f0f1f02', 'Gana con Shields Up, exactamente 1 de munición y una recarga ultrarrápida')
  , ('b0818db3177b092e', 'es', '1c1206ecc70c025967719deee7ea420f8a770c9d', 'Gana con Sneaky y Drill juntas')
  , ('4d87829d1cd53cb7', 'es', '2c1c7702a7580ec61b8151a66d8ca50c49965c34', 'Gana con cuatro copias de la misma carta')
  , ('3a644e4611722c81', 'es', '6411369e12cb04569d5e4f57f3eab0cad4248a7f', 'Gana con dos Glass Cannon en tu build')
  , ('b1bbe5774b2b4dfd', 'es', 'c53e157e2a81efdacfd391f05f42b4dc1b608a64', 'Gana con dos o más Pristine')
  , ('6066a6cb536f4b96', 'es', '809eb193730a6e60b092ac15cb906006e2d0c47d', 'Gana con dos o más Saw')
  , ('44817929693030e4', 'es', '6309e3b549f2e05f7a832b5a3ceee711e45eb469', 'Gana con dos o más Supernova')
  , ('35da6249eafff7ec', 'es', '5fdeae599e43279dabc19756a63e0bf037b96fb2', 'rival')
  , ('545cded3a4c7556c', 'es', '9480ffe6b949b61541654d37159b5729522647c9', 'conectado hace poco')
  , ('85322f19a78eccdd', 'es', 'd1788f386fb5e576b73f0c14aa294dd1c2977898', 'el anfitrión')
  , ('cbc1f7ce7819d980', 'es', 'e944ac9b80a010f18e34cd58514c85d670852aca', 'vs {0}: primera partida de esta sesión')
  , ('6e6dc7f3133d7aed', 'es', 'a3917c0620dd986c7fd0b4339f378788e8a55cff', 'vs {0}: {1}-{2} esta sesión')
  , ('3b0db3500eaa50f3', 'es', '8fa729e9316bef96c0d4cd7ce5decbcde8605aef', '{0:N0} XP')
  , ('560a32b0d16aa441', 'es', 'f44e9fd85b7ae7b1813d58f357d0ec3c223627aa', '{0} / {1} desbloqueados')
  , ('78b3d4e42121719e', 'es', '52a835c16e77c4e0732602eddc7d23596d83990b', '{0} jugador en línea ahora')
  , ('7124fad98f05cda2', 'es', '18b717861013be8d79565ed16af73c668bcacd51', '{0} jugadores en línea ahora')
  , ('e3bb623ce7ca2b09', 'es', '62abf774b7f12a0871590e49783f1c035359ecda', '¡{0} listos! Entrando...')
  , ('9065d0a94556a6f9', 'es', 'e515dbabaae121a13462690c0904e09c4db7d0ed', '{0} buscando')
  , ('b8037a9a2a6f7770', 'es', '06869a27250bbb2bd445d71839cd9317c2551ab4', '¡FFA de {0} jugadores empieza en 5 segundos!')
  , ('c81155b0fa7eca7b', 'es', 'f7ce37d55c66b97cbd23a453b13f007c5a09ac19', 'hace {0}h')
  , ('2bb1bf93b17bd29d', 'ru', '084be6fc3f55fa36a3d40c683fad5e686ff98f7a', '   (Всего серий: {0} - {1})')
  , ('5b55ed08358bfee9', 'ru', '50e2e93f65bd2bd960221ee26b92edfba8b35840', '   -   КАЗУАЛ (БЕЗ РЕЙТИНГА)')
  , ('e0fcf786dd7b7b90', 'ru', '715f30506d8f436b4787b770a4cc87eabfae38f5', '   -   ОДИНАКОВЫЕ КАРТЫ У ВСЕХ')
  , ('91be82a18dd171cd', 'ru', '62bc9bd22039bdff56e0bd4fcee58186d7e082de', '  ({0} в очереди)')
  , ('2162e2c2b5f464fe', 'ru', 'e4f560bd5c376f04483f27e865429b9aa02616ec', '  <color=#66AACC>Есть у {0:F1}% игроков</color>')
  , ('99fb1e843ffa48b1', 'ru', 'b6de50bf861dc8814de845b4ea604d7139f92ae4', '  <color=#7FDBFF>|</color>  <color=#AAAAAA>{0} онлайн</color>')
  , ('410c6b3196db19e4', 'ru', '491a2892516650e2efb2b13a1bbef1914af24555', '  <color={0}>Стрик игр: {1}L</color>')
  , ('9e6e059ee1f6f9d8', 'ru', '131ff12826d9ed6fe685a77c1fbee5a166346b70', '  <color={0}>Стрик игр: {1}W</color>')
  , ('3f7d936b214a5c44', 'ru', 'e6ef24456d8cc38ec788b19b6efe193194317345', '  <color={0}>Стрик серий: {1}L</color>')
  , ('b0196ae3471ab703', 'ru', 'b1c82e918d4d6bc3462d09c8a72e196ccc681b2c', '  <color={0}>Стрик серий: {1}W</color>')
  , ('aa62f023a76d12a0', 'ru', '43662c1f038c90a664be45e6511968bab3328abf', '  <color={0}>Стрик: {1}L</color>')
  , ('41a1ec5a6ed468da', 'ru', '80e78a92f3f309fc0c1a71575668bfebae1fdbc0', '  <color={0}>Стрик: {1}W</color>')
  , ('3df52f1d70da786e', 'ru', 'de13cba6d1b25ba9af841a7cc5323f04b74b5fd7', '  Рекорд: {0}W')
  , ('c23c3f556d4a1843', 'ru', '774994f54715e39266a6307618d901ad7fd66269', '  Урон/игра: {0:F0}')
  , ('783de471a77b0e7d', 'ru', 'f4b973bce333a3966b7fb58036443649af4dd861', '  Топ-3: {0:F0}%  Убийств/игра: {1:F1}  Ср. место: {2:F1}{3}')
  , ('b50df2e13f58ab02', 'ru', '3b88585ccc7066af5df23fdfd4cd1d8b7d835a49', '  [Соперник готов]')
  , ('b89dfee35f251973', 'ru', 'c94d1c070e24745e5257b847aa68b945bb5b953c', ' («Играть сейчас» отправлено - ждём соперника)')
  , ('d4fad156d78d0d23', 'ru', '79ee5562e90ab9cb7bff0affa6fe06d4ff9292d7', ' (оба нажмите «Играть сейчас» в F5, чтобы начать раньше)')
  , ('51bc6ddfd6c32b36', 'ru', '6f3c170bd545215b8832f0798382db9a53474f4b', ' (выплата {0}g)')
  , ('a6027f92c31ba8ae', 'ru', '2446ef58482e38247e7a667e3e9d471dd04f3d0b', ' по x{0}')
  , ('3feec5e324dfa40d', 'ru', '31d4e7e7f8198ecfd215007826c85110b751108d', 'Следующий матч турнира против {0} через {1}{2}')
  , ('7cf635369783ef29', 'ru', '4b4df825f33c5b554ba0e5497502d215a9312846', '+{0} золота')
  , ('4ec92382f6f9cb9d', 'ru', '9791b16ad92597fac04aa01430afe801ee5efe2a', '0 в очереди')
  , ('d43beaf2e3883572', 'ru', '07ea834b31ed15ee1715eb167f8547bad7f65dd2', '1v2 - Как это работает')
  , ('214528f7f4bc262d', 'ru', '74e647231db3f6b2acc2c4622670eb503571289e', '1v2 - БЕЗ РЕЙТИНГА')
  , ('bff6b92b6c3e21d9', 'ru', 'a18f84a9578aa306f34357a39593e4ed8dbd4bd2', 'Серия 1v2: Дуо {0} - {1} Соло')
  , ('c79a4645d2d603b4', 'ru', '21632c13e41daeae9f16c3ca8ba543066827c789', 'Серия 1v2: Вы {0} - {1} Дуо')
  , ('b7cb3e6397fae3d6', 'ru', '14d9e8634fcda42da86d1e2e895ca982372d4091', 'Серия 1v2 завершена: {0}')
  , ('b4cb6205235dd418', 'ru', '109cf27fd85482c00b4a6b6dbb2bbc91dcfba193', 'Серия 1v2: {0}')
  , ('fbb9ace819dbb6d6', 'ru', '733e7baa95c66d1bfbac67551bcb7ada2719b69e', '2v2 - Как это работает')
  , ('8b5f2687f21600fb', 'ru', '7ac0188cbabf0fd05b7d9632be98fdd87d9a2909', 'Обыграй кого-нибудь 5-0 с Chase')
  , ('79dfe1086dd7baf2', 'ru', '432a2d747a8cecaee4d8b0bbd8d11cbd131b8264', 'Обыграй кого-нибудь 5-0 с Glass Cannon')
  , ('192168566e2a4d06', 'ru', '1f256a9c14d5d3d94832169123cda8455fa2d393', 'Обыграй кого-нибудь 5-0 с Mayhem')
  , ('182e3a5b598b14a6', 'ru', '2179b8cbc74315cc138f2e55ff114e7aa047c749', 'Обыграй кого-нибудь 5-0 со Sneaky')
  , ('9d4c37736ff9f3b7', 'ru', '34daab9d40d35ab456c9e77cc9ccc2f623be684a', '<b>Таблица 2v2</b>  <color=#888>({0} в рейтинге)</color>')
  , ('03e012cf2d13a440', 'ru', 'b49834782c6f5863a88153d700c99fc2170b14a4', '<b><color=#FF6688>* Сейчас идут 2v2</color></b>  <color=#888>({0})</color>')
  , ('b62d5ca0a5ad78ca', 'ru', 'b8aaf38308c25d47561a9defc03824a7d17b61d8', '<b>Открытые лобби FFA</b>  <color=#888>(сейчас нет)</color>')
  , ('b5d62dcee8924655', 'ru', '1780f3134b55989a3e3145349cc2a4097f142ddd', '<b>Открытые лобби FFA</b>  <color=#888>({0})</color>')
  , ('585c940fef29ab1e', 'ru', '48f98d176879695850180ebf56c1e062da18d1be', '<b>Недавние серии 2v2</b>  <color=#888>(всего {0})</color>')
  , ('09deebcae22bfb20', 'ru', '6090fa2a628d137cb9870d67b69616b188ef5dd3', '<b>Ваше лобби</b>  <color=#888>({0}/{1} - хост стартует от {2}+)</color>')
  , ('334e17a45a59367f', 'ru', 'fd96da4284df8057fd8a9e8c7ed13ea5d22dbdc0', '<b>{0}</b>  <color=#888>(пусто)</color>')
  , ('250dcc5547b47d05', 'ru', 'a337367fad680421586b92e5238764e639863dbf', '<color=#66DD66>Игра начинается! Входим как игрок {0} из {1}...</color>')
  , ('65a32e66177882b6', 'ru', '8bfb3dcc1c64782da5cc10b57aa42cab47e08f32', '<color=#66DD66>Ваше лобби готово.</color> Внутри {0} - жмите Старт или подождите ещё (до {1}).')
  , ('bad2106299b6b752', 'ru', 'f4364485a44965c7c825bb1e59144457e7b4ec5e', '<color=#888>В {0} сейчас никого нет.</color>')
  , ('8ab0cac8979c2a8e', 'ru', '4f6b1c688d3001ecdab71a07919714cf0227e832', '<color=#99AAEE>Недавно онлайн</color>')
  , ('e91d1e0a65eab267', 'ru', '8f1df6a51b94dd5af8db679c73a8d3cb4f2eea32', '<color=#99CCFF>Блок:</color> -')
  , ('bcdf653ee83bbe53', 'ru', 'c7635e1e070552f04640a363f9b42688d920f5c7', '<color=#99CCFF>Блок:</color> {0:F1}% ({1}/{2})')
  , ('9f62981453f64b39', 'ru', '70ae4797d016b4c6d8c1dba02cc9c83aac00df86', '<color=#C48CFF>FFA:</color> {0}W / {1}L ({2:F0}% побед)')
  , ('fb110029669916f2', 'ru', '995bd7e24afe7fc688d2026b7dd199ce6cbec2a3', '<color=#FF9988>Попадания:</color> -')
  , ('6527d25181574b70', 'ru', '39a0a4745696d6845086d5a0a336ee7ae6cedaf1', '<color=#FF9988>Попадания:</color> {0:F1}% ({1}/{2})')
  , ('28f68e8f4b5e031a', 'ru', '644c522f19a0e7153b4f63cb958665eb40c20b7e', '<color=#FFB347>2v2:</color> {0}W / {1}L ({2})  <color=#888>Рейтинг:</color> {3:F0}  <color=#888>Пик:</color> {4:F0}')
  , ('e635b598d330a8e2', 'ru', '7ae1c8b04ad592dfcf2b268a33874715bec934da', '<color=#FFCC44>Вы в лобби {0}</color> - ждём, когда хост начнёт (внутри {1}).')
  , ('5effd06b69376e5b', 'ru', '5c1fa7d0cda455f717492a0bd5cfa35aee09c9a7', '<color=#FFCC44>Вы хост.</color> Ждём игроков - для старта нужно {0}/{1}.')
  , ('b427669f556ea7bb', 'ru', '02915b624b288814df3f1ae1b33365dcc0c576b3', '<color=#FFD94D>Скин карты:</color> <color=#FFFFFF>{0}</color>')
  , ('af3d1bf4c8be9543', 'ru', 'f89bf703606cf6e63f8874ef15d32c00fac7e208', '<color=#FFD94D>Рейтинг (серии):</color> {0}W / {1}L ({2})')
  , ('fa2645b70f9f5d77', 'ru', 'a777582de015d6aa189d5e987dbb22330ea290f1', '<color=#FFD94D>Рейтинг:</color> -')
  , ('d5984dd5e64c618a', 'ru', '670a333677a5cc92eb43fc800aa6d4eebb14a325', '<color=#FFFFFF>Лобби {0}</color>  <color=#7FD4FF>{1}/{2}</color>  <color=#888>открыто {3}</color>')
  , ('68df4873f949229d', 'ru', 'f474f703aeed6b41dfd3481051df0c1ce534977e', '<color={0}>*</color> <color=#FF6688>Идут рейтинговые игры</color>')
  , ('b2589813d7fe449c', 'ru', '5bf5fdcdb65caf6b9ba3b018c97ee583e7630856', 'Достижение получено: {0}!')
  , ('08b1965af9d1ef0b', 'ru', '4e7afebcfbae000b22c7c85e5560f89a2a0280b4', 'Админ')
  , ('20a200b93b0f4139', 'ru', 'c663090066ad025d9f11faa0246cd410f6c5acf4', 'Баланс: <color=#FFD94D>{0}</color> золота')
  , ('0b0990c45b3d1a1d', 'ru', '8f54cd247fc90332d744f53159d73af22c2490ee', 'Ставка не прошла: {0}')
  , ('2e42add77b4663b9', 'ru', '91a4e283dd12cb9b87870f138798c38ee0d8ea42', 'Ставка сделана: {0}g')
  , ('1cfe92e5e2faa80d', 'ru', 'c51d1dc4be72787b45001281f94ad8d9d4d99c85', 'Ставка сделана: {0}g на Команду {1}')
  , ('8a9eeeb61d6172d8', 'ru', '6e38da544ee550b4c1c1ee181a958f6aa9b2dda0', 'Ставка сделана: {0}g{1}{2}')
  , ('b4ea9e5d44aae6da', 'ru', '976fb1e69feae18b6c510f95d15c6df37b1954db', 'Цвет тела')
  , ('469f96b6fdf6a7e3', 'ru', 'c2d5519c0f2e7db2a59a35a4ac44acbc2a6b42f6', 'Пулевой ад')
  , ('c30091482c3aed14', 'ru', '2cf7c1c459ffac7b7755411c28a0fbd27b7ec2db', 'Статистика карт')
  , ('7d55d57f5ad506dd', 'ru', '1e0bf83f8ad8121c68bb5c86364ed4e207d8098c', 'Выбор карт закроется через {0}с')
  , ('2336cf45edf6056b', 'ru', '7f89e50558edac544825522ec264018f192008a5', 'Покоритель казуала')
  , ('ec3bbc79c58671cc', 'ru', 'fc34d0bcd4850d867f1b6d5e71e32128dfd8ec52', 'Обычные: -')
  , ('0552e283e3175aac', 'ru', '571d9fa39175e85bb1e887c25267c5b620e5e62e', 'Обычные: {0}W / {1}L ({2})')
  , ('1412a8a90c683fb3', 'ru', '65ab9f618934bfa3ace72bac702ee7ca3f2ecbab', 'Клуб сотни')
  , ('41f5f5cf24a035df', 'ru', '4c26512201170dc20cac5a9bf043bfea51b6eb2b', 'Клатч')
  , ('33bda1024d57e8dc', 'ru', 'e3199d24849eb82131394ea88ac9c22db0dbf732', 'Коллекционер')
  , ('f3e1ca269a596f07', 'ru', '8d105cf44d3926289e65c1c83d8e37cb23fd049e', 'Сравнить')
  , ('ecd2dadccaae041d', 'ru', '8b7d0e0643225d0905a09fd3c73bf19c5d45ad5f', 'Competitive ROUNDS — согласие на данные')
  , ('675047dd2ba5fab9', 'ru', 'a4e08a5b9cbd3ab4220ac58c80a41675bdeb184e', 'Controlled Burst')
  , ('abf4f1283922dcc9', 'ru', '9555b604bb2b33b5e29fe2c53ae409befbe84d79', 'Косметика')
  , ('1a2cbebcdb936308', 'ru', '2239943c8d0af354a467e6cc18b9ec9e32f2afcf', 'Курсор')
  , ('de379bda8218c892', 'ru', 'eea9bde7e430f89af34682373a2064689a282948', 'Свои лобби')
  , ('acda0f3497987f2a', 'ru', 'bbe6a0d4c7d69d2481e2d3224d708c68e8e22709', 'Отклонить (оффлайн-режим)')
  , ('9633ce2741a0b7cb', 'ru', '3d44114e197112dc928b1b5e54ab7c91d191dd29', 'Подрывник')
  , ('3cceb107a990d449', 'ru', 'dd9ef4e5a287b8269c0300bdefaaa072c8f4148e', 'Double Nova')
  , ('366e5c083f800ce2', 'ru', '872a0ac7105096e62dc0d9a9342fd454369241b3', 'Дуо -')
  , ('25e3c84b4a5ba59f', 'ru', 'f9a96ae8d3343e98d3017e9bb5e94de28b0e57b9', 'Дуо {0}W/{1}L')
  , ('d07b8c2b5af84abf', 'ru', '92cfc28e94f00f9407f870995c85eeaf388a1e30', 'Есть у {0} игрока  <color=#888>(в порядке получения - повторный клик закроет)</color>')
  , ('f0dc3f4c961b805e', 'ru', '09d9fbb99911bd6d0227907a47221c12a2db9ca4', 'Есть у {0} игроков  <color=#888>(в порядке получения - повторный клик закроет)</color>')
  , ('47b4415f4d6a7d63', 'ru', '8f25a859269ca51039632dd6bba28fb061cfb8d4', 'Эффекты')
  , ('62ce5181e5a602ca', 'ru', '90ce5340a6531dab9e5c720670abf91bb7d42fc4', 'FFA')
  , ('d820383e18f33ceb', 'ru', 'bc6c4123d4239b8e45bc714df9bdbcd2cfadd872', 'FFA - Как это работает')
  , ('d14df263eb7a220f', 'ru', '67a5c91fdef543bcdf7b7bdc9f5efedaee64ff1b', 'FFA - {0} игроков - до {1} очков!')
  , ('e46943688b727f28', 'ru', '3b64921f2960bf7a10b9e3f462af56594d56d312', 'FFA СТАРТУЕТ ЧЕРЕЗ {0}...')
  , ('da7931ad7df4a64a', 'ru', '16bc5bdd632da2ad2fd7bce2af52ce21d3809eb5', 'ПОБЕДА В FFA! +{0}xp')
  , ('b805204de1dc17d6', 'ru', 'a926b4d61bf2b690aff0b07a8b6c41bdebdde9c9', 'FFA отменена - не хватает игроков для новой игры.')
  , ('da364c22af80c86d', 'ru', '514a72f6e0de5d80e678c0de5bd652d724192627', 'FFA: место #{0} (+{1}xp)')
  , ('5dd21d2b1effe3ed', 'ru', '37ec0acb9e53c4780bc0c0fe2454681fee5cab89', 'ДО {0} ОЧКОВ   -   СТАРТОВАЯ РАЗДАЧА: {1}   -   КАРТ В РУКЕ: {2}')
  , ('ef416e27d17769c6', 'ru', '3473dbe7c23ff2a47b4c0db0213ea2c31730da1d', 'ДО {0} ОЧКОВ   -   СТАРТОВЫХ РАЗДАЧ: {1}   -   КАРТ В РУКЕ: {2}')
  , ('c332f8d24db253b1', 'ru', '9c456cc81aecc69b660c85dcac67dc9de04f91cf', 'Полевой медик')
  , ('330d515b831a2877', 'ru', '4731820fcd676f537c7e098544de7386184f7324', 'Закончи игру с теми же 5 картами (и копиями), что и у соперника')
  , ('2267d5721109f6dc', 'ru', '88c0562022ffeb4ef8821335d8fa3e20823550a1', 'Игра до:')
  , ('53dc540a825baa09', 'ru', '22b9ee43aaa645b2356c82a81cf4f411e51328e8', 'Безупречный')
  , ('4e17aa7c25efb66c', 'ru', '93c0c7428061d19b5ae907ba7820e19445811f4b', 'Хрупкое совершенство')
  , ('c5b99e4ded85c126', 'ru', '9d483832cb5867ebec6781d58957b7499d904cd6', 'Каждый сам за себя, 3-10 игроков. Каждый - своя команда.
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
  карта будет выбрана за тебя автоматически. Карту
  получаешь всегда - пропустить выбор нельзя.

- У тебя может быть до {1} карт.
  Новая карта заменяет самую старую.

<color=#FFD94D><b>НАСТРОЙКИ ХОСТА</b></color>

- До старта хост может настроить лобби: цель по
  очкам (3-10), стартовые раздачи, лимит карт (3-6),
  правило «Те же карты» и рейтинг/казуал.

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
  лобби на 3.

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

- Выход посреди игры записывается.
  Ушедший сохраняет свои очки для расстановки мест.')
  , ('3083d95d9140b745', 'ru', 'f4711dbd478dfa86591adfa28c7b9e2552cee2a3', 'ПРИГОТОВЬСЯ - стрельба и блок вот-вот включатся')
  , ('1605fe375cfc39fe', 'ru', '76eda7d248ecf2792fc4875e7baac32b49a2cd96', 'Собери 5 копий одной карты за игру')
  , ('be2399036371a377', 'ru', '73a2014a6c0b4134cdd1bfd287bf0685a71ec92e', 'Свечение (bloom): <color={0}>{1}</color>')
  , ('077676d0bca7cfb9', 'ru', '6dd2206f0985f5762623cca9ed3d8e1a74aa684b', 'Божественный билд')
  , ('949e54f8da1fbbb3', 'ru', '0de1a3e213e5f886d02a66057987fc8a8fbd3036', 'Грандмастер')
  , ('d0fb1e23e0d0e771', 'ru', 'd5580b73bfb2949ac6d9534c49ecd66ceba94e8c', 'Приземлённый')
  , ('9914bb866193f854', 'ru', '70f8bb9a8a5393ef080507a89e4b98d139000d65', 'Главная')
  , ('946a03bb72a4fe72', 'ru', '599812412c8e063215968af7cc448d65f2b3faa9', 'Бессмертный')
  , ('3e6bea2210f7f3f3', 'ru', '6be2477292a2c7282275bcb131607912fcdac752', 'Неподвижный объект')
  , ('5567eee60b51362d', 'ru', '8b466a9d6a804f6268778e511de8a9906c9260cf', 'Инстинкт')
  , ('c3dcb3a7c99fa461', 'ru', '104715a881fa08ef642df3c97be967c6383f5a4a', 'С головой в омут')
  , ('de20704300c6edfd', 'ru', '3a7f6bd064529d32665a9bfdacf161baab97a428', 'НОВЫЙ УРОВЕНЬ!  Уровень {0}')
  , ('fb0725b41f178ef8', 'ru', 'ce2864f02b751fa6f9f141839fa847756de688c5', 'Язык: <color=#88CCFF>{0}</color>')
  , ('bd8b0169d8b34641', 'ru', '0381247a698736fe9930328a814e5263eeff72fd', 'Таблица лидеров')
  , ('2bef0e5cdc0b94f1', 'ru', '8051c09f7c6dfc8c86a8ea94b528253ae4137333', 'Уровень {0}')
  , ('15452feadbac32bc', 'ru', 'd5cc324443a8277d639cfc7dc37ca9a42af3ce3c', 'Код привязки: {0}')
  , ('a2667beef62b6d0c', 'ru', 'ece6bccb7dadb22b3b86139b68efb42a8ea3c7c1', 'Жизнь на грани')
  , ('acc86de9b59c25db', 'ru', '32ed08835c994efa3c32d263129bb8a259d54463', 'Дровосек')
  , ('dd9ed6335db7e352', 'ru', '8d42a8ff760a17a66d663d7b77b0ee840976a372', 'МАТЧ НАЙДЕН!  против {0} ({1:F0})')
  , ('db64d34801d9c8ef', 'ru', '80071cd75107cd5c4afdb2571725ea6733631038', 'Карты')
  , ('9643b3e6281b9dcc', 'ru', '78f3842f0201c993fec13905f2ff9ec3fdd39056', 'Мастер')
  , ('d3b7f9d9c9b6c4e4', 'ru', '63168ee6a276883f20338ce8d90a19f0d972d8bd', 'Макс. карт:')
  , ('928589c9dfa0518c', 'ru', '21bd0337ae7922983486f37b7c1fea1c1a9c14eb', 'Мультиплеер')
  , ('a65804c100e5f740', 'ru', '0cb450ece94fd1c07223dd69e80d9684937e8b96', 'Моя статистика')
  , ('a37a7555118c2dae', 'ru', 'accb4a8ddf0f4d799e252e947a9e7c1de73a8dd1', 'Стили имени')
  , ('831575d2b0643a21', 'ru', 'ac0a3ea3db64d301c566b0246f5375709f7a6b14', 'Следующий матч турнира против {0} скоро{1}')
  , ('321e8a8231f9be1f', 'ru', '3b1fef494a099a3b85cd74865db0a55fc89dcc13', 'Не убежишь')
  , ('741922dd9e900e6a', 'ru', '8059b63e8a2ec48a76d5c678ff28583c5d065bed', 'В ударе')
  , ('53e1c75349c012da', 'ru', 'f6deacd33a1819ebbb127e5a239bc44ccd4c7302', 'Один игрок соло против дуо в серии до 2 побед (BO3).

<color=#FFD94D><b>КАК ИГРАТЬ</b></color>

- Это очередь по согласию: без диапазона Elo и
  без подтверждения готовности.
- Сервер сам назначает одного соло и двух в дуо.
- Доп. стартовая карта Соло - опция.
  Если её включит хоть кто-то, соло берёт 2 карты
  в первой раздаче.

<color=#FFD94D><b>СЧЁТ</b></color>

- Серию берёт сторона, первой выигравшая 2 игры.
- 1v2 - бета БЕЗ РЕЙТИНГА. Рейтинг пока не меняется.
- Игры записываются и зачтутся, когда выйдет
  рейтинговый режим.

<color=#FFD94D><b>НАГРАДЫ</b></color>

- Каждая игра даёт 500 XP.
  Победа в игре даёт x1.5, то есть 750 XP.
- Победа в серии даёт каждому победителю 40 золота.
  Поражение в серии даёт каждому проигравшему 20.
- XP за игры меняется на золото: 100 XP = 1 золото.

<color=#FFD94D><b>СТОЛБЦЫ ТАБЛИЦЫ</b></color>

- На вкладке отдельные таблицы Соло и Дуо.
- Ты попадаешь только в таблицы сыгранных ролей.
<color=#7FD4FF>Rank</color> - Порядок активности: победы, WR, игры.
<color=#7FD4FF>Player</color> - Отображаемое имя игрока.
<color=#7FD4FF>W-L</color> - Победы и поражения только в этой роли.
<color=#7FD4FF>WR</color> - Доля побед в играх этой роли.
- Это таблицы активности. Они не сортируются по золоту.

<color=#FFD94D><b>НЮАНСЫ</b></color>

- Выход посреди игры записывается.')
  , ('34655ad48dcbf535', 'ru', 'ac89cf0bce0114f396b22577093558484dbf3cb9', 'Стартовые раздачи:')
  , ('90df54c06a4560da', 'ru', '6e6a6f2086bb5fe5dbfd17d8d5f502d48759834b', 'Прочее')
  , ('22aaa9cf5852d31c', 'ru', '34b31f7c574f47f91bb097cc3a682e84995a9325', 'ВЫБЕРИ КАРТУ - {0}с')
  , ('65fcf4378f18e10e', 'ru', 'eacde01371d3cfecd1d6868ac0dc890330df9229', 'Пацифист')
  , ('49923e671981b95e', 'ru', '960ab5ab0edb01f24063eaa58f2593eab46db25c', 'Pristine Perfection')
  , ('9e1369ddd08e1d16', 'ru', '6ad85c9fff5b14b6cf3d9aae3688c935e8f4cbe6', 'РЕЙТИНГ - идёт запись')
  , ('7abf29cd482ae2c3', 'ru', '585c9f8bfdd65b7176d0906cacf12b63bd0a5a16', 'RD: {0:F0}    Пик: {1:F0}')
  , ('54eee8c1199323da', 'ru', 'f55cf47ab80a74cedc526b6091d08157c647d6d3', 'Пинг RLFP будет доступен через {0}м {1}с (1 в час).')
  , ('242f5f5f70d848b7', 'ru', '6136170d5d17ddca75e9d37f52c04c12fc73a7ea', 'Пинг RLFP не прошёл: {0}')
  , ('6628289042207194', 'ru', '09e9637fcb1efff7cf0100fe0a14567427177caa', 'Общая очередь')
  , ('eae155f580deb959', 'ru', '9fcd0e210699f50c689ecb8e2fc7fa9105367085', 'Набери рейтинг 1700 в рейтинговых матчах (1v1 или 2v2)')
  , ('3a98b73fa17d67ba', 'ru', 'c7d01b0524369fe5b3c996b27223026f6c017607', 'Набери рейтинг 1980 в рейтинговых матчах (1v1 или 2v2)')
  , ('77b6364f7604291c', 'ru', '4739f3bac2dbf726d75cb84d2cbe3551845e51db', 'Набери рейтинг 2330 в рейтинговых матчах (1v1 или 2v2)')
  , ('58e34f41f31eb642', 'ru', '51e8026c9a204f54a6bd4b1a2d8953138483eb22', 'Продолжаем серию со счёта {0}-{1}')
  , ('4356e1f9e0e4cc96', 'ru', '97800f5d41e76e932cfd498fd7502f99f1e80a04', 'Восставший из пепла')
  , ('5ab18e987855fcf3', 'ru', 'f2f5d68e6499e7eddf0b08d8dbbc483e134f6843', 'Восходящая звезда')
  , ('5c65ef160d2f5147', 'ru', '420b7ab0cb9993c4d5ddeec670cee91d97fb4b2c', 'СЕРИЯ ЗАВЕРШЕНА {0}!')
  , ('d7951aef0fa367af', 'ru', '7e0098e5bb901181e4f78f50b98fe1c46abf73b9', 'Поиск... {0}м {1}с  +/-{2}')
  , ('fdea4fee02fc1df2', 'ru', '122661d9a77d8948a4efb1c1cf20a6a3cae1bfa9', 'Поиск... {0}с  +/-{1}')
  , ('cbe8c30cbcc7634d', 'ru', '35b9dec4c725630964642fc46ef9413ab161ff40', 'Счёт серии: {0} - {1}')
  , ('2b6277b71e22c3a6', 'ru', '366f6b0c2e95252863a672eae68c35cf6c90ed1a', 'Серия завершена: {0}')
  , ('81d48a92efee6579', 'ru', '7d8e33e493d338e360b00d9457e0ae44f44857c4', 'Серия: {0}')
  , ('18746c7ceab495d6', 'ru', '6ab4534ed3f287fc8a0ea7a93221e16851853fb3', 'Sid Slayer')
  , ('410a15ed4e513db1', 'ru', '1fd0163116cd53e22c4f164b9e475b32f563431f', 'Бесшумный убийца')
  , ('4d580a51b66a9839', 'ru', 'b5c2df0ee1dc21486cd644213de53f3f076f6371', 'Silly Drill')
  , ('dca34071afb963ee', 'ru', '52381ad42460aca3d0250e9c8261b125d52754dd', 'Соло -')
  , ('fe6d0b0c1c99dfc1', 'ru', 'ad4c0e8211de1e439cf86a7e625f06c86317b74c', 'Соло {0}W/{1}L')
  , ('892f1b97985931c1', 'ru', 'c5db1144d4106184ee6562dda8f16d44f9d21068', 'Spray and Pray')
  , ('6f6c3c254ccd07de', 'ru', '72a0000376276a7f054fdf34cbbc166d639c06e8', 'Краплёная колода')
  , ('3ec608bd07df3fb0', 'ru', 'ae97475ace60cadda4ce2988ba3066b956b847c9', 'Stan Slayer')
  , ('f3d059d8adc3972f', 'ru', 'af0151e8d21f97ebebc04a4921272e598ec5146e', 'Старт (нужно {0}+)')
  , ('51a6d0e98b96103e', 'ru', '95434373b1524d272dcd9345ec874d2a8b03b516', 'Начать игру ({0}/{1})')
  , ('a84298c23afaf9c1', 'ru', '3b54d47159162560b5d0cc9fabc031730a69223b', 'Старт через {0}с')
  , ('5b789e3f0dcae3da', 'ru', '24e70c2af4a5fd7a4c77d10b257d272c6d49b649', 'Неиссякаемая сила')
  , ('6417f5d13dc1cd9b', 'ru', 'c992e487ff19ddc4ae5cc59132442aaf46dd9b5a', 'Всухую: <color=#00FF00>5-0 x{0}</color>  <color=#FF6666>0-5 x{1}</color>')
  , ('aea09b3828dbdedf', 'ru', '000192d1a8bc97d6ee60930274a5576366c228af', 'ТУРНИРНЫЙ МАТЧ против {0} - подключаемся автоматически, подожди...{1}')
  , ('6449179f9d1f38ce', 'ru', '09e233dea356e6cd5e938852f8755d561df79d21', 'ТУРНИРНЫЙ МАТЧ против {0} ЖДЁТ - ВЫЙДИ ИЗ ЭТОЙ ИГРЫ СЕЙЧАС!{1}')
  , ('22bbf3bbfc5851b3', 'ru', '23f7bcf444a010b5e29565495b64b0e169aab5bc', 'ТУРНИР НАЧИНАЕТСЯ - матчи создаются, подожди...')
  , ('1ae13cdc903c028b', 'ru', 'c32e6ef305f7305a05b6f89f622a0d6797911a18', 'ТУРНИР НАЧНЁТСЯ ЧЕРЕЗ {0} - будь в ROUNDS в главном меню!')
  , ('4de0cd53889e1dbf', 'ru', '4e4cd33a2506596163f467a032d1305efd4c07bd', 'Командный разгром')
  , ('be4894b729971733', 'ru', 'f3e5625b48f6d3cb48733417bcdcf70a949419ae', 'Король камбэков')
  , ('b9c39cbeb97ffb3d', 'ru', '0b4859fc9d77ed14bb61337fbaa484d5a31a7980', 'Этот мод отправляет данные на частный сервер автора мода - они питают таблицу лидеров и рейтинговый подбор.

Что записывается, если разрешишь:
  • Твой Steam ID и игровой ник
  • Твой Discord ID и имя пользователя - ТОЛЬКО если привяжешь Discord через игровой код привязки
  • Каждый сыгранный матч: выигранные раунды, очки, длительность, взятые карты, предложенные карты, соперник
  • История твоего рейтинга Glicko-2

Что можно сделать потом:
  • Отозвать согласие в любой момент (F5 → Настройки → Отзыв согласия). Отправка прекратится.
  • Удалить свои данные (F5 → Настройки → Удалить мои данные). Steam ID, ник и привязка Discord стираются. Матчи остаются, чтобы не задеть рейтинги и истории других игроков. Удаление НЕОБРАТИМО — заново зарегистрировать этот Steam ID будет нельзя.

Выбери «Разрешить», чтобы пользоваться таблицей лидеров. Выбери «Отклонить», чтобы мод работал полностью оффлайн.')
  , ('a8e7491399151552', 'ru', '698e542479926ac30ba7d470149597aaecb9e425', 'Время вышло - {0} выбрана автоматически.')
  , ('1ea1bb377fdee4ff', 'ru', 'a116f7255e19431f1fbf68cdd9f4dce3b66e6b04', 'Титулы')
  , ('e77878efbc01c8b8', 'ru', '584febf2226943cce895111f9b1ff34d68fa3a3a', 'Total Mayhem')
  , ('4602ccfcb6641ef3', 'ru', '21d10582916e120d4c8320df023f92494b61642c', 'Всего: {0} ({1}W / {2}L)  <color=#FFD94D>Золото: {3}</color>')
  , ('65459268621110a8', 'ru', 'a2c06f13201a8b0dd13595ac4dd0d24a7c4670c6', 'Потрогай траву')
  , ('4254217c1c4f7bf9', 'ru', 'fb10fa9913c39f956d36b21c5e77b85f398b20f2', 'Идёт турнир - следующий матч подключится автоматически. Держи ROUNDS открытым.')
  , ('455b205f737f7f07', 'ru', 'fee20df1963ec9531d0a42884334083687be1d13', 'Турниры')
  , ('1c5a31cb31fb37f3', 'ru', 'abe7e366ae1c1eacb6ef6af9bb1d6c200b03a458', 'Шлейфы')
  , ('426d72c497d1fb76', 'ru', 'd16e8b753f78e3ec681fc4f9b2778ef39c3809cc', 'Близнецы!')
  , ('e8ed682b2d08934d', 'ru', '8291e35ae377151b9711fbbc7c1b59a5e1517881', 'Две команды по два играют серию до 2 побед (BO3).

<color=#FFD94D><b>КАК ИГРАТЬ</b></color>

- Общая очередь использует диапазон Elo, который
  расширяется по мере ожидания.
  Сервер сам балансирует команды.
- В своих лобби диапазона Elo нет.
  Вход в лобби - согласие играть.
- У всех 4 игроков есть 120 секунд на готовность.
  Если время вышло, все возвращаются в поиск.
- После игры из авто-очереди с разницей очков 3 и
  больше слабейший из победителей может поменяться
  с сильнейшим из проигравших.

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

- Выход посреди игры записывается.')
  , ('5593dbe5ca8039d3', 'ru', '39e6741f25d3f45d31f8790ca0b6174dca928597', 'Неудержимый')
  , ('44a291e8d72f6864', 'ru', '32363366360c0121e17ca2a47b773d8e15bd3bc0', 'Неприкасаемый')
  , ('c2e6d9d121cad78b', 'ru', 'a5213556d4c72afdc8eb34d8c9c1b6854bc20ddd', 'Ждём {0} ({1:F0})...')
  , ('b11e9b8eb932f992', 'ru', 'a62db852b1d4fd67229d8c1db9abc212214d14f9', 'Выиграй 100 обычных игр подряд')
  , ('7878af0d6218e40f', 'ru', '2b7036dfd10c1a088708a60f75f3ca0d3c38080c', 'Выиграй 100 рейтинговых серий подряд')
  , ('c2080414dc4ad407', 'ru', '6a83a7c5726697f6747faae9710baf615f3c39fd', 'Выиграй 200 обычных игр подряд')
  , ('340a5f64fddafe56', 'ru', '2a82cc109e90813127d860437aafeeb22673804e', 'Выиграй 25 рейтинговых серий подряд')
  , ('dcea6ed7a205f942', 'ru', 'c35aa7a4bc5418558d8050151209b86ec073635d', 'Выиграй 5-0 с Phoenix, не потеряв ни одной жизни')
  , ('88e636ffe6099863', 'ru', '7f8c92d2df2ed7b9d2de661abde38c650a78b757', 'Выиграй 50 рейтинговых серий подряд')
  , ('0a1304bbfc6f8b68', 'ru', '4d2a378dce953a8292d517344fabdca770c713d7', 'Выиграй 500 обычных игр подряд')
  , ('498e2111639dc482', 'ru', '52c738eb71779ebebb572ab7101e3ba0c99a061f', 'Выиграй игру 2v2 со счётом 5-0')
  , ('0a7f9dcfb7f7b30d', 'ru', '0dc10933da1d6d92074a29c880208de24ac1736a', 'Выиграй игру 5-0 с Barrage в билде')
  , ('e86c99634581b48f', 'ru', 'a00c23aea46eb757db62174a1007698f8d5679b6', 'Выиграй игру 5-0 с Burst в билде')
  , ('3d216c23dff44220', 'ru', '0ef4874f3aef9de833424d6a9cef72c32e0f0291', 'Выиграй игру 5-0 с Explosive Bullet в билде')
  , ('7f68781b5d95c2be', 'ru', '51684c861757561dafef3e283514ebf103cd7b8f', 'Выиграй игру 5-0 с Healing Field в билде')
  , ('3370f43648b2c0c3', 'ru', '6adaa65a59b1108cebdbaa309fc74aa603c266c8', 'Выиграй игру 5-0 со Spray в билде')
  , ('0ab780cd5bee16fd', 'ru', 'cc461b976cfa54f3f4fc80d112c44227fd752691', 'Выиграй игру, проигрывая 0-3')
  , ('372406d1b8cd9ace', 'ru', '895f9f6d66f8bad245cd5e1e05e38d7705ea3470', 'Выиграй игру, ни разу не прыгнув')
  , ('7ff5a7c44329fddf', 'ru', '0d164072c1c67cc0f40de17a0e756df812a9f276', 'Выиграй игру, не сделав ни одного выстрела')
  , ('903bd2d1530486a8', 'ru', '7ff9c6a9ec21ae6eee1aa022097cc772d6981aa5', 'Выиграй игру, не двигаясь и не прыгая')
  , ('154bb996c84705ea', 'ru', '25d565c70ac31cc9a4e68446aefbca42024c1db2', 'Выиграй игру, не получив урона')
  , ('b0bbeabb2c6af5f3', 'ru', '098f5df305727f005ed1895b5994020e1cc19406', 'Выиграй, проигрывая 0-4')
  , ('bce06d48a403b9a4', 'ru', '1792eca0039ac2d3327c9bf01f4dbca43e48e063', 'Выиграй рейтинговую серию у Sid')
  , ('23a58ca68c16b593', 'ru', '68d423046930d4adf98766d56162de081943e7f8', 'Выиграй рейтинговую серию у Stan')
  , ('8385611059aa9da2', 'ru', '7f852990398165dad77d4ed415dac0e63d4a1149', 'Выиграй пять игр 5-0 подряд')
  , ('feb59a76f97cc1b2', 'ru', '82e21ae0bb23c7bf1a5dadd5a70daa9e562ab824', 'Выиграй, каждый раз беря только крайнюю левую карту, ни разу не взглянув на остальные')
  , ('ac570864590c58d5', 'ru', '35fce3934da3c301073ba9a0ba73e8eba28a197a', 'Выиграй с Abyssal Countdown, взятым ПЕРВОЙ картой, активируя его каждый раунд')
  , ('ba292685c6b16f5e', 'ru', '061542f4315766fa49452c133d2445cf3c714521', 'Выиграй с Empower и Healing Field вместе')
  , ('beb56c01fc312e7e', 'ru', '9cc4287e6d1f7c078c8ac963e9cd8f292f0f1f02', 'Выиграй с Shields Up, ровно 1 патроном и молниеносной перезарядкой')
  , ('b0818db3177b092e', 'ru', '1c1206ecc70c025967719deee7ea420f8a770c9d', 'Выиграй со Sneaky и Drill вместе')
  , ('4d87829d1cd53cb7', 'ru', '2c1c7702a7580ec61b8151a66d8ca50c49965c34', 'Выиграй с четырьмя копиями одной карты')
  , ('3a644e4611722c81', 'ru', '6411369e12cb04569d5e4f57f3eab0cad4248a7f', 'Выиграй с двумя Glass Cannon в билде')
  , ('b1bbe5774b2b4dfd', 'ru', 'c53e157e2a81efdacfd391f05f42b4dc1b608a64', 'Выиграй с двумя и более Pristine')
  , ('6066a6cb536f4b96', 'ru', '809eb193730a6e60b092ac15cb906006e2d0c47d', 'Выиграй с двумя и более Saw')
  , ('44817929693030e4', 'ru', '6309e3b549f2e05f7a832b5a3ceee711e45eb469', 'Выиграй с двумя и более Supernova')
  , ('35da6249eafff7ec', 'ru', '5fdeae599e43279dabc19756a63e0bf037b96fb2', 'соперник')
  , ('545cded3a4c7556c', 'ru', '9480ffe6b949b61541654d37159b5729522647c9', 'недавно онлайн')
  , ('85322f19a78eccdd', 'ru', 'd1788f386fb5e576b73f0c14aa294dd1c2977898', 'хост')
  , ('cbc1f7ce7819d980', 'ru', 'e944ac9b80a010f18e34cd58514c85d670852aca', 'против {0}: первая игра за сессию')
  , ('6e6dc7f3133d7aed', 'ru', 'a3917c0620dd986c7fd0b4339f378788e8a55cff', 'против {0}: {1}-{2} за сессию')
  , ('3b0db3500eaa50f3', 'ru', '8fa729e9316bef96c0d4cd7ce5decbcde8605aef', '{0:N0} XP')
  , ('560a32b0d16aa441', 'ru', 'f44e9fd85b7ae7b1813d58f357d0ec3c223627aa', '{0} / {1} открыто')
  , ('78b3d4e42121719e', 'ru', '52a835c16e77c4e0732602eddc7d23596d83990b', '{0} игрок сейчас онлайн')
  , ('7124fad98f05cda2', 'ru', '18b717861013be8d79565ed16af73c668bcacd51', '{0} игроков сейчас онлайн')
  , ('e3bb623ce7ca2b09', 'ru', '62abf774b7f12a0871590e49783f1c035359ecda', '{0} готовы! Входим...')
  , ('9065d0a94556a6f9', 'ru', 'e515dbabaae121a13462690c0904e09c4db7d0ed', '{0} в поиске')
  , ('b8037a9a2a6f7770', 'ru', '06869a27250bbb2bd445d71839cd9317c2551ab4', 'FFA на {0} игроков начнётся через 5 секунд!')
  , ('c81155b0fa7eca7b', 'ru', 'f7ce37d55c66b97cbd23a453b13f007c5a09ac19', '{0}ч назад')
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

-- ORDERING (Codex review): this seeds only for keys that ALREADY exist in
-- i18n_keys, and that table is populated out-of-band by tools/i18n_sync_keys.py
-- AFTER the API deploy. On a fresh database (181 -> 184 with no sync) this
-- inserts ZERO rows. That is safe, not silent: the check below reports the
-- shortfall, and re-running the migration after a key sync backfills exactly
-- the missing rows (the NOT EXISTS guard skips only key+language pairs that
-- already have a pending proposal).
DO $$
DECLARE n INT; seeded INT; k INT;
BEGIN
  SELECT COUNT(*) INTO n FROM i18n_proposals
   WHERE proposer_steam_id = 'claude-mt' AND status = 'pending';
  -- The shortfall test counts DISTINCT (key, language) pairs ever seeded by
  -- the sentinel on LIVE keys, matching the rerun guard: a moderator-decided
  -- seed is complete work, not a missing one (Codex Aug-3 r3 find 4), and a
  -- row whose key has since RETIRED neither counts toward the target nor
  -- masks a missing live pair (r4 find 3 — two wave-2 rows target a key
  -- retired by a later sync, so the live target is 978, not 980).
  SELECT COUNT(*) INTO seeded FROM (
    SELECT DISTINCT p.key_id, p.language_code
      FROM i18n_proposals p
      JOIN i18n_keys k2 ON k2.key_id = p.key_id AND k2.retired_at IS NULL
     WHERE p.proposer_steam_id = 'claude-mt') s;
  SELECT COUNT(*) INTO k FROM i18n_keys WHERE retired_at IS NULL;
  RAISE NOTICE 'migration 184 OK: % pending machine proposals; % live (key,language) pairs ever seeded across % live keys', n, seeded, k;
  IF seeded < 978 THEN
    RAISE NOTICE 'migration 184: % of 978 live seed pairs are MISSING - run tools/i18n_sync_keys.py, then re-run this migration', 978 - seeded;
  END IF;
END $$;
