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
  -- ── wave 4 (2026-08-03 evening): 730 new keys x es/ru — full-coverage
  -- sweep (leaderboard detail, tournaments, My Stats history, settings,
  -- bug form, FFA/1v2/2v2 internals, TabStats overlay) + the SHOP catalog
  -- (names + descriptions, Sid's item 3 reversal). Same sentinel, same
  -- rerun guards.
  , ('83dff324198dd780', 'es', '33de31eaa86df586fc5cdac587e01a4da1d8fcd6', '  (últ.: {0})')
  , ('5228b8e02c86210c', 'es', '53b74b7f2271d94b654a77d49d0bb23fa6af9042', '  <color=#888>(pág. {0}/{1}, {2} en total)</color>')
  , ('78f8e040217c152e', 'es', 'fe8ecd2e7ce2de3f4e5cd9f5d0455d92809bdbc6', '  En sala con {0}')
  , ('59e3487efe729e16', 'es', '69dbcae41ae96b4d28fd39fbc75d2d0d810cd266', '  vs {0}:  <color={1}>{2}W-{3}L en total</color>{4}')
  , ('ccd6c2ba67bfee1e', 'es', 'c25067a12dfc7a94ec107c6073e215ab8f45ec06', '  vs {0}:  ¡Primer enfrentamiento!')
  , ('63f971a282654786', 'es', 'b0247bb4bb0764888d3c797e0f15daaa92c2ca9e', '  {0}  <color=#888>{1} de su lado</color>  <color=#666>{2}</color>')
  , ('777a4ed3a4e9d1b0', 'es', 'e0aa04851ac53a1bd32f85ccfe859005fe4e0a5e', ' <color=#888888>(se fue)</color>')
  , ('2252a0cefefdafdd', 'es', 'c91246a5320a509c2bb9418d366d1f8825a028a9', '(no se leyó contenido de registro de: {0})')
  , ('97af61d8389c2364', 'es', 'fbcf4b3dcfbb44db1dbf490faaf83040b2bdeee5', '(aún no hay registro de la sesión anterior — el mod lo escribe cuando ROUNDS se cierra bien, así que en el primer arranque está vacío)

Ruta esperada: {0}')
  , ('e32ff3a09330d729', 'es', '4199a762764740366c8e076eb4282d07e375c215', '(puestos {0})')
  , ('c0b74f3dc3058639', 'es', '0598c8fb1fcafc544b9570ef561d84c8e7941f27', '* <color=#C8C8C8>2.º</color> - {0}g / {1} XP / rol Runner Up')
  , ('41fd1756bebbcf9c', 'es', 'd7c39a6a3788feb33bcaa658e81338bf0f548e22', '* <color=#D4894A>3.º</color> - {0}g / {1} XP / rol 3rd Place (perdedor de la final de LB)')
  , ('5deba6276fd8a551', 'es', '905ab236d174b26450639245ec52f92ca75cc3a9', '* <color=#FFE580>1.º</color> - {0}g / {1} XP / rol Winner')
  , ('6c60e1d8262b75b2', 'es', 'de0ac0c428d1d09d04ae156d8084da226a9774b6', '3.er puesto')
  , ('d0b5fd1cf1d6756a', 'es', '8e0c8efc54fa35ec670bfcebb81f7b5fdd60edd2', '<b>Sala 1v2</b>  <color=#888>({0} — se cierra con 3)</color>')
  , ('29bc540f182069e6', 'es', 'ef44278d615ad0dfbd3a35bea5d164c5c9ded7d9', '<b>2v2 Ranked</b>  <color={0}>({1} buscando)</color>')
  , ('49e1dea08aba7261', 'es', '99ad986f0701d66b8842024bfda93a105359e48d', '<b><color=#FFD94D>CÓMO FUNCIONA (Async)</color></b>
  1. Inscríbete en cualquier momento durante los 7 días de inscripción (Discord debe estar vinculado)
  2. Al cerrarse, se crea el cuadro y se activan las partidas de la primera ronda
  3. Coordina con tu rival con <b>/dm-opponent</b> en Discord
  4. Los dos activan Ranked, entran a cualquier sala privada de ROUNDS y juegan el BO3
  5. <b>El mod registra el resultado automáticamente</b> - sin reporte manual ni código de sala
  6. El ganador avanza en el cuadro; el perdedor baja a LB (o queda eliminado)

<b><color=#FFD94D>REQUISITOS DEL AUTO-REGISTRO</color></b>
  * Ambos jugadores deben tener <b>Ranked</b> activado en el juego al jugar
  * Vale cualquier sala privada de ROUNDS - el torneo no obliga a una sala concreta
  * Al llegar a 2 victorias de BO3, el mod avanza el cuadro y te avisa

<b><color=#FFD94D>CALENDARIO</color></b>
  * Sin hora fija de inicio - a tu ritmo, <b>7 días por partida</b>
  * El torneo completo dura de 6 a 9 semanas según lo rápido que se jueguen las partidas
  * Si no llegas al plazo, pierdes esa partida por incomparecencia (cuenta en el % de penalización)

<b><color=#FFD94D>FORMATO</color></b>
  * BO3 de <b>doble eliminación</b> - pierde una vez y bajas al cuadro de perdedores
  * Gran final: campeón de WB vs campeón de LB (el cuadro se reinicia si LB gana el primer BO3)
  * Todas las partidas cuentan para el Elo ranked

<b><color=#FFD94D>% DE PENALIZACIÓN</color></b>
  * Sube cuando te inscribes pero pierdes una partida por no cumplir el plazo de 7 días')
  , ('2a6188ce0acf8037', 'es', '630d5fe7b6a1288b2d2def76fbc528dd95a739c4', '<b><color=#FFD94D>CÓMO FUNCIONA (Sync)</color></b>
  1. Marca todas las horas de inicio a las que puedas y luego inscríbete (Discord debe estar vinculado)
  2. Se cierra cuando <b>8+ jugadores coinciden en una hora</b> - se decide <b>2 días antes</b> del inicio por defecto, así que siempre tienes 24h+ de aviso; los jugadores que no puedan a la hora ganadora se retiran (sin penalización)
  3. <b>Ten ROUNDS abierto a la hora de inicio</b> (el menú principal vale - no hace falta quedarse en la pestaña)
  4. El mod <b>te conecta solo con tu rival</b> - sin cola ni invitaciones
  5. Juega el BO3, el cuadro avanza automáticamente - <b>reserva un par de horas en total</b>

<b><color=#FFD94D>ENTRE PARTIDAS</color></b>
  * ~7 min de respiro antes de cada una de tus partidas tras la ronda 1
  * Ambos jugadores pulsan <b>Jugar Ahora</b> para saltarse la pausa y empezar antes
  * Preséntate en los 10 min de tu partida o la pierdes
  * El cuadro está oculto hasta el inicio (nada de espiar a tu primer rival)

<b><color=#FFD94D>FORMATO</color></b>
  * BO3 de <b>doble eliminación</b> (primero a 2) - perder una vez te baja al cuadro de perdedores
  * Las partidas van en paralelo: tu siguiente partida se programa en cuanto se conocen sus jugadores
  * Los mejores seeds reciben byes si se inscriben menos de 16
  * Gran final: campeón de WB vs campeón de LB (el cuadro se reinicia si LB gana el primer BO3)
  * Todas las partidas cuentan para el Elo ranked

<b><color=#FFD94D>% DE PENALIZACIÓN</color></b>
  * Sube cuando te inscribes y no te presentas a la hora de la partida
  * Menos penalización = prioridad si se inscriben más de 16')
  , ('3fa2e1d1b7b13d65', 'es', '1681c1ad66e8b53940d57f71ec05cd6f6cbd6f17', '<b><color=#FFD94D>PREMIOS</color></b> <color=#888>(con {0} jugadores)</color>')
  , ('185ea4043021ff08', 'es', '24a4b3b2e962abfb33dbb275b5574999fa2a3c1e', '<b><color=#FFD94D>PREMIOS</color></b> <color=#888>(con {0} jugadores, en vivo)</color>')
  , ('4b40a37c0f75e082', 'es', '5d0cfe13e0112ed053a0d334953c1a598ef0f059', '<b><color={0}>{1}</color></b>  <color=#888>(sin rango - cargando...)</color>')
  , ('c014368fb258c367', 'es', '964083dde3b9086daa465f67dd2f060fef1afe91', '<b><color={0}>{1}</color></b>  <color=#888>(sin rango - aún sin juegos)</color>')
  , ('e7f929f2fc14ab9b', 'es', '37e09b5ca64b2263c149efe2e584442a59ccf277', '<b><color={0}>{1}</color></b>  <color=#888>(sin rango - {2} jugadores)</color>')
  , ('7d817ff529af1f06', 'es', '58139b6f61ab48387be44eb29431ba6209e10f4e', '<b>Clasificación FFA</b>  <color=#888>({0} con rango)</color>')
  , ('45cc733ef5540b01', 'es', 'a33b19409eb5e945af5ac6000a7f968edb0f0d95', '<b>Clasificación FFA</b>  <color=#888>- aún sin FFA ranked</color>')
  , ('951b9b16227f135f', 'es', 'cd95b4632dc60bdec486a3611eed91c56d5736bb', '<b>Registros del juego (final)</b> — se adjuntan a tu reporte si marcas la casilla.')
  , ('68ffce8bbb14ce05', 'es', '8f377602579db81b3a6824ecb1e4175b54dbc1fd', '<b>¿Cómo reproducirlo?</b> <color=#888>(opcional)</color>')
  , ('cd0163493ecac4fa', 'es', 'c0dafbb700e42748454366596685977879f28bbe', '<b>1v2 recientes</b>  <color=#888>({0} series)</color>')
  , ('5215fcf61178e3e3', 'es', '54e706d52a91eaf6738072af7af1ea59473bdfc0', '<b>1v2 recientes</b>  <color=#888>- aún ninguno</color>')
  , ('9d033a263ddf51d5', 'es', '1f710e4b0e713951c4646e1f85cdf30df5e941b9', '<b>FFA casual recientes</b>')
  , ('d0083333e06cfaf1', 'es', 'ef69c20bdd62dbc159ca5c52064ba8b5eed1773e', '<b>FFA casual recientes</b>  <color=#888>({0} en total)</color>')
  , ('3d37b7ba02553145', 'es', 'aed453ecdecb7d986af81013f773383e4624f25b', '<b>FFA casual recientes</b>  <color=#888>- aún ninguno</color>')
  , ('ef2ee75085947329', 'es', '18c28fcab9c64bd35ce03e8e016602b6795ecc8f', '<b>FFA ranked recientes</b>  <color=#888>({0} en total)</color>')
  , ('687c1dcb181ecf45', 'es', 'c655a4e371ec3c52666e977042a3cc98eb9de6dc', '<b>FFA ranked recientes</b>  <color=#888>- aún ninguno</color>')
  , ('e93c7974349c8d09', 'es', '8500bc4d384b9f21e290610ab0c760e7ca028ba7', '<b>¿Qué pasó?</b> <color=#FF9966>(obligatorio)</color>')
  , ('5b4560f5fd3ca74d', 'es', 'dbc49e21b64e298c965187ecea7dcf1bcdd62263', '<b>Tú</b>')
  , ('b7f586245cf37349', 'es', '49c3d520a6cf011fc93ce62b10afbe9e6bdfaec3', '<b>Contra ti:</b> <color={0}>{1}W - {2}L ({3} juegos)</color>')
  , ('4c68914b7aabfcfa', 'es', 'bf002f47ea0d0549603ae705e59cb5f1a515bf3e', '<b>{0} Parches de rendimiento</b>  {1}')
  , ('510bbb2d5c28e2ed', 'es', '23e6796a6dd6767a12be4b513543ebf8e5e4abb7', '<color=#00FF00><b>GANADA</b></color> {0}-{1}')
  , ('e08bba79fc405bb1', 'es', '0be65425d5df8a3381741d8b1359dde94d3a039a', '<color=#00FF00>Vinculado a Discord</color> ({0})')
  , ('3e892a1a275b71e0', 'es', '0052bf33f0e0a2fca12bc8925dbe2a6505d7419b', '<color=#00FF00>Vinculado a Discord</color> <color=#888>(clic para ver)</color>')
  , ('ea83337993a45755', 'es', '585d7397eb695e72f42e0bacc337f5de1767d40a', '<color=#00FF00>GANADA</color>')
  , ('e494424cf053f992', 'es', '4b8ca35da1156502e8dd33e7421caeb030b28894', '<color=#00FFFF>{0}</color>  - escribe <color=#FFFFFF>!link {1}</color> en Discord')
  , ('ebb00fa13d937164', 'es', '6d963ba9ef802936517c691221c2197fe179c635', '<color=#664444>-> {0} apostó {1}g a {2} - perdida</color>')
  , ('493df93f52bd5e55', 'es', '185f137dbfc6210724da22e7a90deda846e8ce92', '<color=#666>(clic para copiar)</color>')
  , ('80a36c40325aac15', 'es', '593d09650a9947c940874fcff9cb819b859aef53', '<color=#666><i>Ocúltate aquí: Ajustes -> Aparecer desconectado.</i></color>')
  , ('5c528222367454fd', 'es', '568602877de41bc9414cac985c77b8c26ac84eaa', '<color=#666>sin cartas</color>')
  , ('42814ecc2b658aff', 'es', 'c914a0dd6b7a82aa21bbc158bcd04239601f6345', '<color=#666>—</color>  <b>Juego {0}</b>: {1} {2}-{3}')
  , ('1a9fd2fffa505395', 'es', 'b44b4f1c38f706c3657474e5325330c3f8c42265', '<color=#667788>Cartas:</color>')
  , ('a6a35197bee61edc', 'es', '7a9481236d37894202154793757d34325a34387c', '<color=#667788>ninguna en mano</color>')
  , ('c7e1faeda4aff802', 'es', 'd0fde2869f5db199bb2e6fc56d6ec641b7e9ff32', '<color=#667788>serie:</color>')
  , ('b3c7d24dc7d7d5f0', 'es', '5e3ff648c349f07d096defc5f364a9bf02be7bd1', '<color=#6677AA>Tú:</color>')
  , ('accb99d11995227c', 'es', 'f79172f515472bfbdcf012289d572cba03244088', '<color=#66CCFF>Descargando...</color>')
  , ('590709f4939b85b6', 'es', '07bd257b33b6b7dae2457c8b3cfe4b5949484973', '<color=#66CCFF>Buscando {0}...</color>  <b>{1}/4</b>')
  , ('225de4a62c9c9a2c', 'es', '37dd9921db9da397984723b18a5138c9c8013b18', '<color=#66CCFF>buscando</color>')
  , ('d42e053f6b13ff64', 'es', 'bbcb83eae9983000e8f0f516b4318bb399bf67be', '<color=#66DD66>APROBADO</color>')
  , ('fb1a4b3a5f4e1d5d', 'es', 'dc2a54c6ab19d126c840dfe2b19216c508821c64', '<color=#66DD66>APROBADO</color> <color=#888>(la rev {0} espera una actualización del mod)</color>')
  , ('b84788a98e84201d', 'es', 'a7e2659bd9f21d6579b628236a12968cdc7e4d87', '<color=#66DD66>En partida FFA.</color>')
  , ('04ea724f3226d3a6', 'es', 'f232d32135d7a1a9257b868b63a89efd1ef8d344', '<color=#66DD66>En partida 1v2.</color>')
  , ('0d7cc210312198ae', 'es', '34fa10fede90cb20a1ddf3da58a43404436557eb', '<color=#66DD66>¡Partida encontrada! Entrando…</color>  <color=#FFB347>{0}</color> <color=#888>vs</color> <color=#88AAFF>{1}</color>')
  , ('b3eb79e601bb099b', 'es', '1b796b9e660114c40780b5f70ed1977413c71cbd', '<color=#66FF88>En línea ahora</color>')
  , ('0a7da31bb71a460a', 'es', '86af06d8ad49429bceb0be6f1616d05dda47ec9f', '<color=#777>(apuesta hecha)</color>')
  , ('3961b1463268849f', 'es', '730b09723eeadb523d9b0aa6dacbb50480fb8ec0', '<color=#777>(pasa el cursor para la gráfica)</color>')
  , ('6b912c60e510d768', 'es', '13c8a3c88fb5be85116ae4e6a94a3dc35feeb24e', '<color=#777>(tu sala)</color>')
  , ('1c5acd21065ca4ea', 'es', '3c8ec61681d4250b1d3d48235800cfb3557f2f9b', '<color=#7788AA>-> {0} apostó {1}g a {2} - pendiente</color>')
  , ('8311a697b4bf1aac', 'es', '4b40a0907e3234e0cc2fe724d87f31cc5cbe9cdc', '<color=#7FD4FF>Historial 1v2</color>')
  , ('e4e808986976f25b', 'es', '5223c763248dbdfa305993651bdeeca05fe2509e', '<color=#7FD4FF>1v2:</color> {0}W/{1}L')
  , ('825271b6ccbea3da', 'es', '96ee7b1438ffe3f13aa82d7096953dfa1ad77687', '<color=#7FE8C3>Cada inscrito por encima de 8 aumenta el bote - ¡16 jugadores lo duplican! (ahora: {0})</color>')
  , ('db7dd81ac45d3a49', 'es', '1933cbafaed52c8b035f1a5e2855631e4afbee83', '<color=#7FE8C3>¡Bote máximo - 16 jugadores!</color>')
  , ('c7cd96f7c337c372', 'es', '89e542520d4d04153f795491a4d854749727701f', '<color=#888>(equípalo en el editor de personaje)</color>')
  , ('a0a84bb37b74480c', 'es', '4623a6a3410fc70b8cc383dcf0a6cb4c4f933517', '<color=#888>(en curso)</color>')
  , ('33495944a2734539', 'es', '4cd18a046f43841d4fe50b03aa465f0e26bc5d92', '<color=#888>(la última posición aprobada sigue activa)</color>')
  , ('8424897272503312', 'es', '227fdfe98dd6eb33929a1358e01817cbd13f6e83', '<color=#888>(carta extra del solo)</color>')
  , ('ac53cb1d4b497deb', 'es', 'd64a6ab3ed242d778aac287190982a900e112064', '<color=#888><i>Consíguelos en la pestaña Tienda.</i></color>')
  , ('ac2f3c9d04c1d307', 'es', '29b2cfb1815a45fe5f93cce227df3453f78ad1dd', '<color=#888><i>Oculto</i></color>')
  , ('85126096ca57c79a', 'es', '46a5af2585c769ed0e95767115d47c4374011355', '<color=#888><i>Cargando historial de partidas...</i></color>')
  , ('f88cc3f973d9f363', 'es', '7556b0ea5d14482def62171cdb787dab6eb19915', '<color=#888><i>Cargando...</i></color>')
  , ('5fdeeb0b9c1ec66a', 'es', '6b1ea4c0eeeb654cbd9aa79535b60b966080d110', '<color=#888><i>Nadie visible ahora mismo.</i></color>')
  , ('2d17a111ecfa7be7', 'es', '2fe8b21054cd17ebd00a292566d04d71f3148cde', '<color=#888><i>Actualización de {0} - consíguela en la pestaña Tienda.</i></color>')
  , ('02481d4bc4f0e5ee', 'es', '69a9c6e275a41f86330f6c8e4513a47b83f6625e', '<color=#888><i>Actualizaciones de {0} y {1} - consíguelas en la pestaña Tienda.</i></color>')
  , ('bce10b6d42caa61d', 'es', 'c34d4b466d6b20a538710fabf9f43f8d410d46fb', '<color=#888>Discord:</color>')
  , ('885802821e8af4f4', 'es', '875ba602929e490fa025f4fab86ce7d1bcaa9674', '<color=#888>Saliendo de la cola…</color>')
  , ('29956eb093b192eb', 'es', 'fcff73f47ee10219a3876754afb842f262ea44cb', '<color=#888>Saliendo...</color>')
  , ('a11c16b210120f55', 'es', '2552c92999af87111790f7a90d41be061c01da98', '<color=#888>Cargando…</color>')
  , ('94d8eeb7835cacb2', 'es', '988e5666d9c440209aa8a616f309be4c3d8d7c7b', '<color=#888>Mod: <i>no detectado</i></color>')
  , ('fae2abbd1d51f67d', 'es', 'c40c6b2fcce0e40b069812932bfe25f200cac3ab', '<color=#888>Mod:</color>')
  , ('08e57eb5ea26362e', 'es', '17ac025c7e380c8abcd7f65f12ff482a44d57839', '<color=#888>Aún no tienes objetos asignados - el arte se vincula a tu cuenta cuando sale en una actualización del mod.</color>')
  , ('b9020ddf292a653a', 'es', '33ec8a32092c71c0303fb402975eaea93a946cbe', '<color=#888>Elige <b>Buscar aleatorio</b> para emparejar, o <b>Buscar sala custom</b> para elegir equipos.</color>')
  , ('fd4d752a09b135c7', 'es', 'c33489a0e5e55f1129255554ed18ba2ac2a49972', '<color=#888>Steam ID:</color>')
  , ('f46b07ee62c695cb', 'es', 'a028d3b8e8c2a227aaf8885796b90d57ddc6ee4a', '<color=#888>cualquier lado</color>')
  , ('02c6d926d2a73a47', 'es', '06d342169002a46b2dcd8b255afee37003292dad', '<color=#888>vendidos {0}, regalados {1}</color>')
  , ('e6e6c58af19307ec', 'es', 'bac173ecd4e58b18541d82f573f1faaa20dff16c', '<color=#888>{0}% pen</color>')
  , ('81d1594bd1091bc2', 'es', '07a8c3315325a7a113f2f1fc08be063c770e592e', '<color=#888>{0}</color>  <b>{1}</b> compró <color=#C8A2FF>{2}</color> por <color=#FFD94D>{3}g</color>  <color=#7FE8C3>+{4}g para ti</color>')
  , ('357effe73805facd', 'es', '68d71224c58674c112890a7fb61d7191d171f9bc', '<color=#888>{0}</color>  <b>{1}</b> recibió <color=#C8A2FF>{2}</color>  <color=#888>(regalo)</color>')
  , ('86369abfe6bb0dd4', 'es', '8b5f2ed9c71b4f4d439f18f5e87d00c642ab65a5', '<color=#8899AA>1 - 2000 de oro</color>')
  , ('c8e19ea38805cd06', 'es', '9a62a068439228473cef75e0adeea9dea9ffe2ee', '<color=#8899AA>¿Cuánto tiempo vas a buscar? (se muestra a los jugadores como caducidad)</color>')
  , ('603409ff6c82dce6', 'es', '40e65024e861fed568d872aea26bc7171255c387', '<color=#8899AA>Menciona el rol Ranked Looking For Player (máx. 1 por hora). Mensaje opcional:</color>')
  , ('7d8e43ec3c542605', 'es', '2a30c4721b799ef8018b7e5b23cfe8062c17039c', '<color=#8899AA>Buscar</color>')
  , ('a55363b0ad23e5b7', 'es', '11d01c5ab646d71262d1c38154e66cc97b7f8c6f', '<color=#88AAFF><b>DÚO</b></color>')
  , ('5c7f514fa12c66ce', 'es', '239e7d1a3132fda68ccef926a05bad2726b26e2f', '<color=#88AAFF>ganó el dúo</color>')
  , ('71b9427f56eb8491', 'es', '94f1bd1317408d4db6879578e89e2baff37efcd9', '<color=#88AAFF>quiere dúo</color>')
  , ('a1244673752f5b09', 'es', '63e3488e68c75920133d1af00d41414a0297f6b5', '<color=#88CC88>-> {0} apostó {1}g a {2} -> <b>+{3}g</b></color>')
  , ('c7db091c6a0581e2', 'es', '6535f8599ca23255d61a3b1d7d6ffe9e652dccb1', '<color=#88FF88>Equipado.</color>')
  , ('296bc9618defb504', 'es', '9c6bbae583fc1361282e70616ace14758f6e8c73', '<color=#88FF88>¡Comprado!</color>')
  , ('bb1576b33cca66ca', 'es', '0f8972798a7dc8831f9c0d900bead94bda16f1e6', '<color=#88FF88>¡Listo! Esperando a los otros 3...</color>')
  , ('53c81b79be7734cc', 'es', '72eb49bc0c8d4b39c1a19186f6230c1c6173dd38', '<color=#88FF88>¡Enviado! Gracias. Registrado como <b>#{0}</b>.</color>')
  , ('9808e56f61cea810', 'es', '3d51ed996dee97375f2a58108ab35dd1d4c07482', '<color=#88FF88>¡Enviado! Gracias.</color>')
  , ('8a48a19c9b583f44', 'es', '9c9a18c65d8497f6d65c240a21e317c325b88e1c', '<color=#88FF88>cerrada</color>')
  , ('3072afe4d390a26d', 'es', '7458c742a0778b5861439c00af14c2518f2cbbcb', '<color=#88FF88>{0}/{1} activos</color>')
  , ('a13ace4753916354', 'es', '794de690ee3249fb9aff60d3748de5b98a0f7388', '<color=#8FA3B8>{0} fps</color>')
  , ('57da6b22ccc01814', 'es', '3be3caf7dc4aae34dc52ce4e084379b3f38f3e0c', '<color=#99AAEE>Logros:</color>')
  , ('ba0b8dc8f6cd3b7d', 'es', '99179cc9e74d882fb29effe8c3d16396cba0d1b2', '<color=#99AAEE>Historial Ranked:</color> <color=#888><i>aún sin series ranked</i></color>')
  , ('713c1176bf2b2b9e', 'es', '12fb0ff3ca8074a3192cd4aaaf78ba614b8a4d6b', '<color=#99AAEE>Historial Ranked</color>  <color=#888>(series recientes)</color>')
  , ('afda56e261c5dbc8', 'es', 'f9f7dc430ffd04be72b8680756d5da9a0e4a961b', '<color=#99AAEE>Cartas top:</color>')
  , ('a446fd1a40e8f265', 'es', '9b98f2ba99a70e922939b50ed9c6c6ddf333e077', '<color=#99B3E6>Bloqueo {0}%</color>')
  , ('a6d07574629f099c', 'es', '2e7ba4b2a8d879503b315cf86da06a7eef63cde3', '<color=#99B3E6>Tú: Acierto {0}%</color>')
  , ('ac200ad7911d1b33', 'es', 'fea4a3b41a3af17529f68a323d94e259bf710236', '<color=#99B3E6>{0} teclas/s</color>')
  , ('ca42603f393a8386', 'es', '55d0abe95e269b9549242e572909ab1b7406f21c', '<color=#99CCFF>Bloqueo:</color> {0}% <color=#888>({1}/{2})</color>')
  , ('d8623cf1d650881c', 'es', '60e0678c7e19e5c414e5c7ff1a7879c3427fdbb9', '<color=#99CCFF>Bloqueo</color> {0}%')
  , ('0fc211da8b7173b4', 'es', '72f0ed2b9b3989238388e7edddaf252c81a7cb9f', '<color=#9AD0FF>Tus envíos:</color>')
  , ('b5699b2c6706d70a', 'es', '9e8ba6414d716552ea534ba3d65e2773b984fe5e', '<color=#AA9955>-> {0} apostó {1}g a {2} - devuelta</color>')
  , ('97eed477558a8ce8', 'es', 'cdedff3bd78198557df9dfac25d6db4d5e4f0d8c', '<color=#AAAAAA>Los reportes van al equipo del mod. Sé específico — qué pasó, cuándo y qué estabas haciendo.</color>')
  , ('7ca5ac14f4529d8a', 'es', '215a414b3ec2e0a6014946b0e501d09b88707d21', '<color=#AABBEE>{0}</color>  Ganador: <color=#FFE580>{1}</color>  <color=#888>({2}p)</color>')
  , ('b0435f9624a0ff08', 'es', '0f187adf4f36222c3e229d3a7cfc62c483482453', '<color=#CCCCCC>Llevas <b>{0}s</b> en esta sala de Photon sin que empiece la partida. El emparejamiento vanilla a veces se cuelga aquí cuando un jugador tiene ROUNDS sin foco. Haz clic en la ventana de ROUNDS y vuelve a probar con espacio, o usa la salida de emergencia de abajo.</color>')
  , ('89a698611907f9ec', 'es', '2fa2251cb22a70a509d217abe8ec11e024e0aaae', '<color=#D8A7FF>Historial FFA</color>')
  , ('683fba7afbb36532', 'es', 'd9e3fd10875116ad5e4e38dca5bf31fbc487fdf5', '<color=#D8A7FF>FFA:</color> {0}W-{1}L')
  , ('4e9df1482c91e705', 'es', '77768f2cddef5881738c018e0d4d539bbfb2df96', '<color=#DDDDDD>{0}</color> <color=#777>-</color> {1} jugadores <color=#777>-</color> <color=#8FA3B8>{2}</color> <color=#777>-</color> {3}')
  , ('1e9c55fbc95244de', 'es', 'dbe957ca740a4bf3b02108f054f8b42164ac836e', '<color=#E69988>Bloqueo {0}%</color>')
  , ('c60975242010a2c8', 'es', '4fbccb024c897c74e187b3121bf5a8fae54a0244', '<color=#E69988>Rival: Acierto {0}%</color>')
  , ('6dc74c450a0a3571', 'es', 'e45c22cefdaf554364a1b1064fa6ee80d5760c8d', '<color=#E69988>{0} teclas/s</color>')
  , ('f3111e697b8a3499', 'es', '503a6feddafea172e50dcab91e9b6ca9fd5c5415', '<color=#FF6666>(SIN STOCK - el artista aún no abrió las ventas)</color>')
  , ('5960a9ad7ea21934', 'es', '3459beeb88871e1e04b203c8a2bae6ad0c375949', '<color=#FF6666>(AGOTADO)</color>')
  , ('0243596e5d193a51', 'es', '18aff0f77f00d58e0135fbbe73602eea442793d2', '<color=#FF6666>+{0} reemplazadas</color> <color=#556270>(pasa el cursor)</color>')
  , ('0caa0cb269d0e9b4', 'es', '402a9cda67e01dc4345b39756827e04ea577666a', '<color=#FF6666><b>PERDIDA</b></color> {0}-{1}')
  , ('6f22a3d809f5159c', 'es', '77f34486d741bddbd1feecfab4257ae67faa108b', '<color=#FF6666>RECHAZADO</color>')
  , ('da749f60b9684f21', 'es', 'd7e0867b602018ada5fd37c4c1a1842af50c54b1', '<color=#FF6666>Fallo al borrar: {0}</color>')
  , ('59811c83538f6ef1', 'es', '163d90dba8fe50450a04fb5fdad8c164068508db', '<color=#FF6666>Falló: {0}</color>')
  , ('3bb6abceb257a687', 'es', 'da927b7271e6f8d59cbacce1b80066741b590663', '<color=#FF6666>PERDIDA</color>')
  , ('4f840542dec022c0', 'es', '8aa97ef1388ab04f260985fe6a7f5c5f08b4a5a4', '<color=#FF6666>SIN ABRIR - ¡pon stock para empezar a vender!</color>')
  , ('7f75b6449785f3eb', 'es', '6aa9d58290a51803f53daabf11161a4a059e4bd0', '<color=#FF8888>Falló: {0}</color>')
  , ('03bc4458323fd933', 'es', '5382a6697adcab5246f2e9a8c1ef6290ebaa2c09', '<color=#FF8888>La compra falló: {0}</color>')
  , ('b1eef294c20d4576', 'es', 'bb8114dd2fbea5b0ee5612f9aae23305f631796a', '<color=#FF9966>GENERAL: OFF</color>')
  , ('79d12f448ea4ecb8', 'es', 'f2c531693552d14d45c172e385c65845c14edac4', '<color=#FF9966>CAMBIO DE POSICIÓN RECHAZADO</color>')
  , ('2380439a94a853ee', 'es', 'c71e0391acbc34eefbfee6148971ec18fac0b669', '<color=#FF9988>Acierto:</color> {0}% <color=#888>({1}/{2})</color>')
  , ('8b00982d542b583f', 'es', 'f48e8d83176749e28e622b50540c3ae0f29b907c', '<color=#FF9988>Acierto</color> {0}%')
  , ('f469e16744d7e631', 'es', '025b122607398d54c7dac36a0d9b0fdb10f1ab8e', '<color=#FF9BE0>¡muy pronto!</color>')
  , ('e2d283f46c6565a8', 'es', 'e80eed1854086d8b9db4aefdb9f0edcdfe901eb8', '<color=#FFB347>Sala 1v2 pendiente</color> — Sal para disolverla si no pasa nada.')
  , ('fdb683f06819a160', 'es', 'c0db3cd062a38f3cacf680a2109f3dd736a64c13', '<color=#FFB347>Historial 2v2</color>')
  , ('a77c56b241124324', 'es', '7b102ce6e585783508febe4bddb64faf39b56156', '<color=#FFB347>2v2:</color> {0}W/{1}L')
  , ('d4c5f1e400063fb8', 'es', 'e6712306e7d7cc9c2eafd0893c231cff06249886', '<color=#FFB347><b>SOLO</b></color>')
  , ('f0c37983395b1b27', 'es', '1fe1aeab7143e93fea9d5b783b4e71539de01982', '<color=#FFB347>Serie en pausa — los mismos 4 pueden reencolar para seguir</color>  <color=#FF6688>{0}:{1}</color>  <color=#888>(marcador {2}-{3})</color>')
  , ('99a1c6367212642d', 'es', '50fc7f597d225aa9330d5d5c4c309e5a30070477', '<color=#FFB347>ganó el solo</color>')
  , ('30510d105badfe4d', 'es', '58b20b963fdc084822180221b0b2e2e33ff98c14', '<color=#FFB347>quiere solo</color>')
  , ('c4c4f162ef3a08eb', 'es', 'a3fd02a92f217c87cd4ec996e33fe07c4b77ebca', '<color=#FFCC44>Buscando…</color> {0} en la sala <color=#888>(se cierra con 3)</color>')
  , ('ec409b24b6baa83d', 'es', '1a7f980a682a95d6db7309ad484f1c7ff80776a2', '<color=#FFD080>La pantalla de partida encontrada puede estar colgada</color>')
  , ('330b2a3cb2dd7af7', 'es', 'c6ace38f182cbc9fec7803e444562aadce3d2c54', '<color=#FFD94D>(quedan {0} de {1})</color>')
  , ('11c7534fb8b7839c', 'es', '22e12b0d3921df432cf0884ac46c4dce85a50d83', '<color=#FFD94D>APROBADO - esperando actualización del mod</color>')
  , ('3fb6e8f61142d09f', 'es', 'b9513bd50f6f2b2febd1b0b20d5f97faec07384b', '<color=#FFD94D>Apuesta personalizada</color> a <color=#FFFFFF>{0}</color>')
  , ('0578f75137c0ac92', 'es', 'd413a2bca5b58733396502254c2879888129a70b', '<color=#FFD94D>¡Partida encontrada! Pulsa <b>Listo</b>.</color>')
  , ('fa6435193f8ec7ab', 'es', '5201388e750ee115b4d891876b605efd08ef984e', '<color=#FFD94D>POSICIÓN PENDIENTE DE REVISIÓN</color> <color=#888>(la última posición aprobada sigue activa)</color>')
  , ('c0be4316b3888ca4', 'es', '2466fa8171f0d173bff6eb5ad9409cf0d6e423cd', '<color=#FFD94D>Ranked (series): {0}W / {1}L</color>')
  , ('811f0b6757adca50', 'es', '0112ccb6625408665001abf2b2b43ef9105e6e86', '<color=#FFD94D>Ranked Looking For Player</color> - ping de Discord')
  , ('bf327ab5b8dbdcc1', 'es', '0278a637c0b4224f4b2e502196bbf1aeac42848f', '<color=#FFD94D>Serie Ranked contra ti</color>')
  , ('bcdff3edc272aa6b', 'es', 'c41e0c77ac7efea07d68b205c2ecda2ffefff35e', '<color=#FFD94D>Ranked:</color> {0}W/{1}L')
  , ('85ecd41da4fb57e5', 'es', 'd93c51495c04409d37e36b4dce1930a45ce9de61', '<color=#FFD94D>Torneos:</color>')
  , ('70fd04265821e7cd', 'es', '447bf00a8adf3e15948428f8d350b4499a403d82', '<color=#FFD94D>ganados {0}g</color>')
  , ('dd4ea253253e8050', 'es', '4aa5a0655e06b7f207582228c71b66d5028d5cb9', '<color=#FFD94D>en curso</color>')
  , ('0eef1f90d4357dc2', 'es', '4a8962e2f2c84e3dce462d200654ced2b3d2d81d', '<color=#FFD94D>pendiente de revisión inicial</color>')
  , ('d8ede9573dbac9c7', 'es', '7e01cae4dee9862c4d799b06bd66d619c0c0bf92', '<color=#FFE580>1.ºx{0}</color>  <color=#C8C8C8>2.ºx{1}</color>  <color=#D4894A>3.ºx{2}</color>  <color=#888>(jugados {3})</color>')
  , ('5e6611223ccd2e52', 'es', '38a56a2898844a92391b086b48afb2f86e9b282d', '<color=#FFE580>Reportar bug</color>')
  , ('725a66f0f66e8076', 'es', '2aa5db947eb5e12f3d13857640ae1a52c1cee360', '<color={0}>Azul</color>')
  , ('48fd57c668c63dc7', 'es', '68e41b4c2415fc16a601f9284cc62d1a0d1e1253', '<color={0}>Abandono: {1}/{2} ({3}%)</color>')
  , ('2f4cf0864647f848', 'es', '9d44c73676aa56f6df4f33a819ebcc1b81cd2034', '<color={0}>Naranja</color>')
  , ('57f539baa20955f8', 'es', '28329a6c2291ab34539160eafed7e0a58654883f', 'Un cursor de ratón rojo intenso.')
  , ('7420d8cc3e98ff5e', 'es', 'f26aed94347cea2e644f80d3c4339839bf4741c5', 'Una corona trenzada de espinas retorcidas, con puntas de sangre.')
  , ('28d4ff2dae7455f9', 'es', '23e39b1ad591fe7bb634d0bb71deb0af7c7f6c47', 'Un cursor de ratón naranja brillante.')
  , ('936c8c700ad2e14e', 'es', '09760c239e5f1eaaaed919af1b3c0b4b59cde787', 'Un amarillo vivo y soleado.')
  , ('fc23457a57683e0e', 'es', 'fd205b824b53ed05147b7286bfcdbef4e9d8c77a', 'Una corona de fuego ardiente. ANIMADA.')
  , ('71e3ee43149aa274', 'es', 'd1bf71529da76b7d1a3d412a4db22ec2f634c046', 'Una línea blanca limpia. Lo básico.')
  , ('f68275e9faed6821', 'es', 'e5f0c878ca68b6046f356f8b4e10dff4be9ab299', 'Un cursor de ratón blanco impecable.')
  , ('f5fa897d8e716419', 'es', '72115355dca2abe0a4c5925cae462041c92fb3f3', 'Un cursor de ratón cian fresco.')
  , ('a70f99966e0958b8', 'es', '3d27acca20b71363bd39579002d1e2d47ab735bd', 'Un anillo crepitante de rayos vivos. ANIMADO.')
  , ('878cbf198b4c88e0', 'es', 'ad047b0b34bba2c06aa7eaf784f0aa9c665c11bc', 'Un cursor de ratón azul profundo.')
  , ('054aa178a79fbbd0', 'es', '8ccaaa302ea73bdb9bead1a6ec141229cea2d9dc', 'Un índigo profundo entre el púrpura y el cian.')
  , ('b0b49ff92e08c74a', 'es', '70b6c54dc1c13ff24f68f5b1e66b0170e9871bd4', 'Un rojo vino profundo.')
  , ('2aad25bde6099301', 'es', 'c1855544914c1abd869dc681d7a531ee05833e2c', 'Un verde bosque profundo.')
  , ('809359b5ebebe8d5', 'es', '067b43f4b1519da09b0ac300e59a647f12ae7d65', 'Un tono de piel oscuro y profundo.')
  , ('95f4cbc38f450bc9', 'es', '841134a9aa1e8b90a49cb4c5b535ebb37e812e5a', 'Un amarillo terroso y profundo.')
  , ('7be9b5f7a848839b', 'es', 'ef5205084dc052e1551b3a5b29613d80ee2d61be', 'Una corona festiva de luces parpadeantes rematada con una estrella dorada palpitante.')
  , ('3739b2d530f6debd', 'es', '04f6ac1ae02e6475938fb263bc4b7960aaa14465', 'Un rojo vivo y ardiente.')
  , ('abe3b20d82427246', 'es', 'e0b04f7776991125df7976fc25df6c378d7ee39d', 'Un cursor de ratón rosa fucsia.')
  , ('b75fe59845fa7ecd', 'es', '4a82ef21d0b89f6ba37a2b6c2fe3be74c8e23d34', 'Un tono de piel claro y cálido.')
  , ('583edabb1e09ee16', 'es', '9f3a21630b49c6794c32656c33e432d3bf84e405', 'Un verde oliva apagado y terroso.')
  , ('8a633c693695b715', 'es', '5393acd21dc5762f827bd626eb1baa00e2a5f856', 'Un destello solar dorado y radiante. Cegadoramente virtuoso.')
  , ('0f54805e99c76854', 'es', 'a60ac5e701992bb53799c6435d8fa9cfeebbbcd0', 'Una capa negra andrajosa con forro rojo sangre.')
  , ('e763ddfa52f56c01', 'es', 'f9440b94808ba8103d9205ae89bd4358d0263fec', 'Un dorado rico y reluciente.')
  , ('97048d0dbba0b0ad', 'es', '6b92c53eadd095e5577c7c13641831ea4e80d518', 'Un tono de piel marrón cálido e intenso.')
  , ('7f1e2dff680a21ea', 'es', '26435e21d715685d5614c144df3ac5faaf6a77e5', 'Un cursor de ratón púrpura real.')
  , ('76de6671a0e43d50', 'es', '12d7c24417f733987cc887cc155326577389eee7', 'Un arcoíris de partículas reluciente gira a tu alrededor.')
  , ('185819c37faec22c', 'es', '5d67c42eb8f5c9f4a3e92e8852f30b18b536c4c9', 'Un cursor de ratón negro elegante.')
  , ('e3e5ec5ee886c897', 'es', '1c8cdb1aadf7440df733f47304d419a4e7dc9ab2', 'Un gatito gris basado en mi gato de verdad')
  , ('b842e9bcebcddf77', 'es', 'bb1a91bcbeb57bb030beb06e6801c3123650ebc8', 'Un ámbar suave, distinto del dorado.')
  , ('7a9dce7f07ce4812', 'es', 'd6682c54bc14e1ceeaab8f5c5f4d028edeb46ae9', 'Un aura verde suave que dice que sabes lo que haces.')
  , ('3a765650a0fabfe1', 'es', '084e935f9f75ddb12ece11b4db28468ba8e41034', 'Un tono de piel medio, besado por el sol.')
  , ('72f872abc86378a5', 'es', '0e3adaa92340b7253fd391d5801e47286f66c549', 'Un cursor de ratón amarillo soleado.')
  , ('9c7b9e8923006966', 'es', '2b5232add8ebb0b0b10d3340988527aba0746bcd', 'Un verde vibrante entre el dorado y el cian.')
  , ('82a50967a8775147', 'es', 'b6ccb321cd37c9a941a874741f8a5b53b4e22012', 'Un cursor de ratón verde vivo.')
  , ('b55e98320a2c5883', 'es', 'c0d79153a0f91fd7a0675abc1920dbfb911a8244', 'Un rosa coral cálido a juego con el nuevo cuerpo Coral.')
  , ('84dea13d4f8749b7', 'es', '4d33160cf65e8ee1374dbcda15cd04d741ffbaf8', 'Un rosa coral cálido con toques de naranja.')
  , ('705f3184942e5c20', 'es', '093f93f6bc96df2c125019d556d7ef7a8e6b54e2', 'Un verde amarillento con chispa.')
  , ('bc5daf52ecfcb394', 'es', 'baf48506da4f8fcb158b020e9780f52833d663a4', 'TODO MAYÚSCULAS')
  , ('34323f3c43b0f286', 'es', '030d9312f32b78411ae6fd45521eafa5e3f16e4e', 'Abismo')
  , ('f1ad6bb2e30613b4', 'es', 'a733b809d2f1233496ab516eed0f3ef75cf3791a', 'Activo')
  , ('3a70a1caae7433a3', 'es', '5bcd1bc127edaf471cf8fc9daae11e05d0ea4bac', 'Subraya tu nombre. Combinable con otros estilos de nombre.')
  , ('fb141f420287e2e0', 'es', '7f73305879a039b508248f80ce6511bbd64ef4b4', 'Añade espaciado extra entre letras.')
  , ('37501be191dd7d66', 'es', 'd738ebfc6a7ca0bfb0966d34a7228b7448258df0', 'Bronce metálico envejecido con un brillo cálido.')
  , ('b89ffcf2f3023062', 'es', 'cc6b2a579218473a35deacda2f0d5d288cf56c9d', 'Vino añejo — rojo profundo con un matiz marrón.')
  , ('9ad25dd88adfebfa', 'es', 'cee5ec293ece08f8b8d87a2b278c5a6bcd35fe37', 'Antenas alienígenas')
  , ('2c0bcac005222b8a', 'es', '0cffeabac63123322aba0bfa89e7867134d572bf', 'Todos (combinados)')
  , ('f1144eb024aa03eb', 'es', '940bbeb152752a33c9934bdce09b0298902a4d0e', 'Todas las elecciones (más antiguas primero) - rojo = reemplazada:')
  , ('20d99221097e1fef', 'es', '27a01d4772038a3f83552908e0470604e773f8af', 'Ámbar')
  , ('e74a5c961fcffa93', 'es', '55879cd931aa5e3de8d5fdf3e442cf30a8cc34c8', 'Nombre ámbar')
  , ('dcbcb0e4299e1c29', 'es', '1ef532cce6fea64ba94eed1237cc785bcbd74ad0', 'Amatista')
  , ('2b07bbabfb8a43f6', 'es', '407c60401b79318f2877683ed6df36f0bda6cfee', 'Munición')
  , ('394f228c337224fb', 'es', '4c459601c34257dd40797c08e6fe2bcf0ee51d72', 'Apex')
  , ('c56cdc211517120c', 'es', '5f7ffa4a353bda2e5e403cc3f8b5fcbf11e82722', 'Rabito de manzana')
  , ('22eac961461ab249', 'es', 'c6db2ec02dcf3556a6323441f9db90a8db6c6932', 'Ascendente')
  , ('9eff451fa8b7f65e', 'es', '67d0b166e08a2db71d9486f96ac1bb9a2c9ad486', 'Adjuntar registros del juego (recomendado)')
  , ('6994bb12f92bd491', 'es', '2b4881723e1320d2b12e0ad31fc9dfc27794c0a8', 'Cadencia')
  , ('9409ce3813df7c43', 'es', 'eeee9b76ec5d1cfa27c511f2def4981c9c5b667c', 'Aurora')
  , ('ac3f9e4803a9463c', 'es', '96fe497e8d08bf63fbd473f4404b51f515bb3dac', 'Degradado aurora')
  , ('9c9b2f5a2d506195', 'es', '122a68a5ef9fadcd527704d0d89be3776ce44871', 'Elo aliados')
  , ('fff050a62953a165', 'es', 'b2df7e1ebbcf4c9557f59de9e8d9e16ff8b7817a', 'Pto.med')
  , ('61ecc3a70166ed11', 'es', 'caacb9c4120653ddad8aa9d39ba9c52e144d097d', 'Cometa azur')
  , ('8a4c4be43c067b23', 'es', '63b68012cb0fa6028ec65f7f56bd1e09a7ecad78', 'Globófonos')
  , ('dca50b9ed118cbdb', 'es', 'c079b59c65f4a283f90f1a0511b37ff20c393880', 'Vence a Sid en una serie ranked')
  , ('cecd4fa7f2642aba', 'es', '315b3a7ff79a5d9a069de5c4b40c89545a06f6e7', 'Vence a Stan en una serie ranked')
  , ('4e3adbbd8a6ed18f', 'es', 'd8b47f574662c9e2de4a022fe7f25db087c9b9b9', 'BepInEx (actual)')
  , ('785b325c520dbc5b', 'es', '072719c3fc70bbe17a0c02b6968f63fb1de66a2d', 'BepInEx (sesión anterior)')
  , ('7491833f08beadc5', 'es', '7d812b6c0cf9b06224698bf549532e4dfa84626f', 'Berserker')
  , ('047de86df5071d35', 'es', 'f03b60f7e52b7ce49ed1e4f9fa511c452a2185bb', 'Beta')
  , ('3828219f201c6509', 'es', '28544273e2aef2357d775fe43b318ba43f33a6be', 'Nombre grande')
  , ('cb88c065adf80933', 'es', 'dcce1b666e42b2516c4264ee76dabb367fb176b1', 'Más grande que Grande, más pequeño que Enorme.')
  , ('620a77e0a38cd666', 'es', 'cee82537870ea52d5f32f6a15bd0752b3c43183d', 'Cursor negro')
  , ('4012ddaf0c5772db', 'es', '5b07f7088b0080a88cd696619c5ce3aaef4e8bfd', 'Ébano')
  , ('77b1c8d67327bc59', 'es', '8882e4bb2a3ab29b02ac332ae19a66cdb130dbad', 'Blitz')
  , ('31af90c64e73ac01', 'es', 'dae5a0121abb5fa0da729304b67493a1e3ea7978', 'CD bloqueo')
  , ('7e7de6c72b86824d', 'es', '54c45c033f5eb914fae27a646cbd9e23d3750d19', 'Bloqueos')
  , ('75f7ef63c5238e27', 'es', '1aecb54aae1e2b5ed8dfe32d82d5a452ea62616c', 'Cursor azul')
  , ('e91af1cc53639bfd', 'es', '19e07430eed6d97d6d73cb4a2967b1f316520f54', 'Negrita')
  , ('5102a46fc36366ae', 'es', '4e36289d0951a7bd412ec33c4053fe33bef6b588', 'Rebotador')
  , ('17e39c5f5faa04a8', 'es', 'fffb1ac23479a3b099333fa68dd4b912625af777', 'Rebotes')
  , ('7b10209c6ab33112', 'es', '0861596efe0b8976d831f3ea080decca2798d09b', 'Bouncy')
  , ('f7c82f02b929a7d6', 'es', 'a9c34a32e6e79b3c17f81be6765ab239ba111db6', 'Main de Bouncy')
  , ('31730649fbdd137e', 'es', '46ed5de23cef330d5db5771f01c745d52d1f1195', 'Reinicio del cuadro')
  , ('1dcbb7f9eb5c256c', 'es', '32f934bf1243eb49222743a5d0f32e178fca1845', 'Bastón cerebral')
  , ('62d51247bd7470f7', 'es', 'c93e38d0d4ff579fde2f4a80a077a881667a17f9', 'Color de cuerpo cian eléctrico brillante.')
  , ('ad0a6dae771517ad', 'es', '9ec32ed642cbdcae1c042f9b03791ebc2d4e9c6a', 'Color de cuerpo azul industrial brillante.')
  , ('8d3e5929f807c196', 'es', 'af3102527f03c95d8e79825f965d8663c7fdf780', 'Bronce')
  , ('8e2573140ef55a27', 'es', '58356fb4cac0b801f011b397f9dff45adb863892', 'Burbujas')
  , ('390f22c995b624ac', 'es', '89183a133ac470f8daf7ceb62ad266022b240fc8', 'Reporte de bug enviado. ¡Gracias!')
  , ('7811a5db8d47eda1', 'es', '9fe72981cc879912316e26db5261095ec4da3688', 'Reporte de bug enviado. ¡Gracias! (#{0})')
  , ('1e088d00a6318256', 'es', 'ca3230fafdeab8aaaca7de56a4c8ece290129e03', 'Hecho para el ranked.')
  , ('c4d1897e0b92927e', 'es', '1982b45375c2d30f60024c602fa49444a089bddb', 'Bala lenta')
  , ('2b6f6945b122da91', 'es', '3f7097dd693481d4b33a1a1360bbaeab8ec78561', 'Vel. bala')
  , ('1b9b94fd93c13e2e', 'es', 'ce55c51755db07c0da74f585b4c7a4582d55ac19', 'Tope de partículas de impacto (2/frame)')
  , ('44958e96b42c92ac', 'es', '7509c5747e5db3dfa3373afc42eca9f5b27a8599', 'Balas')
  , ('d689c0344f85b91a', 'es', 'f48fa5b998d1a20e5aefa573097ab4dfd104f679', 'Borgoña')
  , ('9ef2d087c80357dc', 'es', 'c3523aedb7179f0f1ed0e80801a4c320b1e398fa', 'Ráfagas')
  , ('42b58b0e9f96b45e', 'es', '7db325b3e21b1a5687cdeadba0a48cc535576391', 'Comprando {0}...')
  , ('2bc7b81351452373', 'es', 'ae687d91ac348704cf2ceb4910feaccbed518dfb', 'CANCELADO (faltan jugadores)')
  , ('4d4720dda0a927bb', 'es', '6dc2daaed756f492c0b47af2ae68dfc26d827fab', 'COMPLETADO')
  , ('70483da324b9a680', 'es', '1c1bcb24cffa054e5fd7d06de56bf73a3e74d02e', 'CRASH')
  , ('f45db7482d67a389', 'es', '58e286b87091b07259c44d7904e679e9be73eddf', 'Tinte verde bosque tranquilo, de baja saturación.')
  , ('de467d3edb721838', 'es', '4b1b1758c6a36dfe7213f6432757a25f25b44fb6', 'Limita las partículas de impacto a 2/frame — la mejora más visible en tiroteos intensos.')
  , ('c7400849ff3404d4', 'es', '4d4ce73b15660f20977ad7efab2283c51bdae008', 'Carta')
  , ('feb7846e483876c6', 'es', '0f830bc25e52f96121b00a67378be1abeaa3f274', 'Cartas')
  , ('1ed575a86bc9d240', 'es', 'a6bcb0b542f89a1109f41bfa09c4216c3cd8991f', 'Cartas:')
  , ('5d2ca42b2c4789b8', 'es', '5fafc6ce92411f8dd5808ec5a87bc12b0a48c8d9', 'Cartas: <color=#88FF88>COMPLETAS</color>')
  , ('56eeae7c606f171b', 'es', '72e5a30e619dd5488bc8f47b9a2b6c904e40e38e', 'Cartas: <color=#FFCC66>abrev.</color>')
  , ('1b4effb239673333', 'es', '8a968fb7dbc2ab1fb3e31e87aea9d81c5b4fc4a1', 'La boca de Casi')
  , ('d7d0e9e219b53281', 'es', '75114685463170b6592d652473ef40eb0a6eceb7', 'Ojos de Casicorn')
  , ('05dc830214a8b91f', 'es', 'ed02eaec1b7cdfe54ca5d028db8b31807f7252fc', 'Casual: {0}W / {1}L')
  , ('f6a637efb68bcea0', 'es', '33aed4926d6006ad15fdb8c60b6fa786a37b41f9', 'Casual: {0}W/{1}L')
  , ('ea0992cf6e04fc9f', 'es', '61b9204fa30ab100d2a82ad42f62e455b1d2df3a', 'Categoría:')
  , ('8fd18c1dd49bf9a8', 'es', '879f0b1bef59eeebf78cfd3a22f6f8077810cecf', 'Canal')
  , ('d3a2f4060b4d4faa', 'es', 'c81e2a08f7e0b5c4162685cc5b5ede3c1ec05062', 'Carbón')
  , ('040fdcdc9fe82d97', 'es', '6fdc92710bf9a1c37713696ed1898bd196a848c9', 'Madera carbonizada — marrón oscuro cálido rozando el negro.')
  , ('6c93b4c00e97aaba', 'es', 'b986a8e56e3b5c3b9f806bc270f5e67bb0499f24', 'Chat [{0}]  <color=#888>(pulsa T para chatear)</color>')
  , ('de0019878b425396', 'es', '3653056b385b377aa4fe8be7000f0a0f318e2157', 'Canal de chat')
  , ('6d74d0c0e8ae9292', 'es', '5d378529c5ccf974fbf710c541fe49c260696b4a', 'El chat tiene canales por idioma - usa el desplegable de la pestaña Inicio, o Tab mientras escribes, para cambiar.')
  , ('1ec90b2ecc0c22a7', 'es', '218e75c7a912404b048fff0747e40108873b6334', 'Cromo')
  , ('755e04f636c21f2a', 'es', '568dba56e5fadf7f411898e5b4c5ee9790606f36', 'Limita el init-spawn del ObjectPool a 4 en partida — reduce tirones por nuevas asignaciones del pool.')
  , ('9f57ff0905238412', 'es', 'a3b330fc7dec25ff7c2417fdf084196120632e2b', 'Estela limpia')
  , ('d8852fbbce7d5315', 'es', 'b9a010b399b7896b4c0e26e06e1b2d16738d947f', 'Color de cuerpo blanco impecable.')
  , ('d1e0f9e0812bfad8', 'es', 'bbfa773e5a63a5ea58c9b6207e608ca0120e592a', 'Cerrar')
  , ('0bd62ee5c52d93de', 'es', '58d28d96646957acfa9a8c908d0d61aad25b77c4', 'Payaso')
  , ('96ed0e7311a525a3', 'es', 'c509eac2111b5bd8b67314feb259572255c6f6cc', 'Cobalto')
  , ('8d3bc6bf3cb691f6', 'es', '4fac4cec0922ba3d0b40514b9e35526635575dcf', 'Motas frías de violeta y cian giran en un halo oscuro.')
  , ('f69708bf886ba7c7', 'es', 'e355071ea9b079a72d85687e2ac34ec406ee7927', 'Colorea tu nombre de cian.')
  , ('7238f6a0f006bd2f', 'es', 'ce90982b634c51797500d1fa3c0537d9160f3cc4', 'Colorea tu nombre de dorado.')
  , ('a29939fd5310702c', 'es', '378e60aaa1606276e4ecbe32a4488f37421a3a4a', 'Colorea tu nombre de verde.')
  , ('97bf484344ec2873', 'es', '2ec2ab8e8e10dd4bac423d81ba3df5fb10f5a85b', 'Colorea tu nombre de rosa.')
  , ('b75b645fcf4adb75', 'es', '2889f9f551f5371f6892e307d5cf5c60025bb0c1', 'Colorea tu nombre de púrpura.')
  , ('cd7de4ecc01c1d92', 'es', 'e076968ac0727a056d40623d209ebf3b394200e1', 'Colorea tu nombre de rojo.')
  , ('059bb297892d12b5', 'es', 'ce1c631db455b6205a45b767991b570a3cc36d42', 'Coloso')
  , ('8618c3d156db5aa5', 'es', '7de90a65241a6cdbd9ade485d777715d99285a1e', 'Común')
  , ('096503131133e107', 'es', '470568764445128dbbde3a4861ab484f4d7f3bb7', 'Competidor')
  , ('8107c94687b5513e', 'es', '04a212215ef9fbf686d280802eb81ee7a6e681cd', 'Confirmar')
  , ('23a2363525a63d2b', 'es', '7216727508f5cdbfb1e167595a4e44b10237b778', 'Recorre el arcoíris sin parar durante la partida.')
  , ('2c0b482cb7fb2078', 'es', 'b3184788eb8c6ab50e98bdded730901d8b5f4505', 'Energía azul fría crepitando a tu espalda.')
  , ('1edaccb2dca7ceaf', 'es', '0c4e7b1605bb2b6079143cb3ff386f3d2882a487', 'Gris pizarra frío y desaturado — descansa la vista.')
  , ('5286435b58b15502', 'es', 'd47ddde92346ea04ff6d780400e1c300eb81639e', 'Color de cuerpo gris frío.')
  , ('0157a9143665e238', 'es', '669a338cd831e006a68d71778ac389a20d8e40f3', 'Bloques gris azulado fríos sobre un fondo frío y tenue.')
  , ('111b9b5a0d6725d6', 'es', '3f4e6fe068c428db8f08c82ec6f320768c3e77c4', 'Color de cuerpo verde azulado frío.')
  , ('5c819efd5e47b749', 'es', 'a7a705f4f6e2ae44ccf76ce8ec20cb3f7825828f', 'Lava enfriada — sangre de toro volcánica al borde del negro.')
  , ('3242c3ee66b19424', 'es', 'd27ca6c0dabe676d07af8742683d39325665cd59', 'Coral')
  , ('a72ae56c0ded3702', 'es', '57a485e2451d558c03fa971091c39322dd7ab285', 'Nombre coral')
  , ('a18255a7c68182e3', 'es', '52b4f7979734d5a9daa6702b008bc4dd1047377f', 'Ojos desquiciados')
  , ('7ae8c98cd55250eb', 'es', 'd1e2abc18a8b508f620471e42c72adf3818c6480', 'Crema')
  , ('1566b2c6e09119fc', 'es', 'b3f39ab486dccbade852f17535c258ceb02694ae', 'Carmesí')
  , ('8aa3777be23776ab', 'es', 'e1d3d4a4ebd01690499f49db911a9f70902a7e8c', 'Ráfaga carmesí')
  , ('f027d1391cc75d18', 'es', '410494f2cf468cb98b4655657880ea42f72183c0', 'Corona')
  , ('c8a0e2e08bdb7f47', 'es', 'f996d22f90fe3880c9bf2c0026b7e64b2c9d234a', 'Rango actual')
  , ('3768972fb7662437', 'es', '21a1cca38ce259e8e8241d9335c19da50c1c6eb3', 'Cursor: <color=#88CCFF>{0}</color>')
  , ('e307fa465c2af7fb', 'es', 'fc9e3a357cf300a24d8e3496e2a38f19a2b8d2ee', 'Cuernos carmesíes curvados para tu demonio interior.')
  , ('306025349f761c7f', 'es', '26744388a2aad194db923050c4fe31ade1973f3f', 'Cursor cian')
  , ('b1ab6e33f7326e5b', 'es', '747761927d1053584caa147babb5f8bb92befb6e', 'Nombre cian')
  , ('b4874c5e05d6538d', 'es', '7bf6d1d3a58a22ee49f3b78fc132bc5e98633e4a', 'Daño')
  , ('b5a636572c560a3f', 'es', 'd1337bd66502e493e3dd898db928623e5e720ba0', 'Aura oscura')
  , ('10cc5458fd27e27a', 'es', '6400ddf76a965495252cffa62e366cd2e1e5670f', 'Bloques rojo oscuro sobre un fondo cálido y tenue.')
  , ('fe95157ea5d812b9', 'es', '94ee8869082873abf458deca86a2b8e3a3091aa0', 'Formato de fecha')
  , ('8b736b068bcaa904', 'es', '08596d25c886c9f955df32042b64f4be840b7528', 'Formato de fecha: <color=#88CCFF>{0}</color>')
  , ('3af3d6023d5ff20e', 'es', 'a10292c3bb3a1332f06c324215d42310757b082c', 'Decente')
  , ('bbe3197e69738bd2', 'es', '698769e3384f77f8587a7217e7ac7b3a9c9990c7', 'Color de cuerpo rojo sangre profundo.')
  , ('7b5aaa66e23a080d', 'es', 'bda30be42cb140a97c3e1a67751c1da38c2ceb11', 'El azul violáceo profundo del momento tras la puesta de sol.')
  , ('efe79bae30a5be47', 'es', 'b30ee14d6f5a4695053e04642b94ecb60916730f', 'Azules de crepúsculo profundos y fríos con exposición atenuada.')
  , ('ce5c7a3baf9b6aa4', 'es', 'ef88541ebbea1230910389468e407d07bf0c5d46', 'Bloques verde abeto profundos sobre un fondo atenuado con tinte verde.')
  , ('13d0d287c990cb23', 'es', '01d54aa6323503c2e4424a176601f7b00c366139', 'Verde bosque profundo que sube a jade brillante. Degradado de dos colores.')
  , ('3a1384cf68cbafa9', 'es', '6b2e6d11146de2269d0295012c6fd7f7061101b1', 'Medianoche de océano profundo — negro con un toque de azul frío.')
  , ('b95f34ace2fa0325', 'es', '0c7459d1da70cc3b119267a865e39cb294ce276a', 'Color de cuerpo azul océano profundo.')
  , ('f05cbe9e346dc452', 'es', '343c93580548bc432445ab81ff3add7560c3d74c', 'Humo rojo intenso que sigue cada uno de tus movimientos.')
  , ('91dc11e808ee40a1', 'es', 'cba6e53a33069151fb549a1f0e6934023b31955b', 'Púrpura real profundo, de los que absorben hasta el último fotón.')
  , ('f4999184f00fd765', 'es', 'ab5e0dd7f1c6d715060995c24097c27dabc964a1', 'Por defecto (aleatorio)')
  , ('77698eafc221e602', 'es', '133e5f657b000e24c75606ccd1808f5d6fb5a618', 'Inicio por defecto: <color=#AABBEE>{0}</color>   Cierre de inscripciones: {1}')
  , ('664c773cdf0bb4c7', 'es', 'a957d1b7bc867ae01a8723a614a867b018c111b4', 'Alas de demonio')
  , ('2fc6ee0492894d1d', 'es', 'a1b943b041c4467fd8e874c41839ca774a8879e4', 'Elimina balas fuera de pantalla — el anfitrión borra las balas que salen de la cámara.')
  , ('6fb3f056a5481e85', 'es', '55a2bf4d07dee2378de337391d28fcb235be8066', 'Detalle: una estrella fugaz orbitando tu cabeza (animada). Equípala en el editor de personaje.')
  , ('83c7c50f88df9d10', 'es', 'b76e06ba2922bd5320f09988df4115981726164b', 'Detalle: ángel certificado. Equípalo en el editor de personaje.')
  , ('57f1bdcef79892ac', 'es', '91e791312991c216c7bdca715ee22fa1062f21d0', 'Detalle: cosmético de la comunidad. Llega con la próxima actualización del mod; equípalo en el editor de personaje.')
  , ('0599d7612e9c92b0', 'es', '3606ab5ea0cab3d56f0f7fb96596c962e44194b9', 'Detalle: orejeras acogedoras salpicadas de estrellas. Equípalas en el editor de personaje.')
  , ('9c528b8f8d623258', 'es', 'd35ece05488a58ed9adbf2fd9423a0e4bd0c206c', 'Detalle: pesada es la cabeza. Equípalo en el editor de personaje.')
  , ('0cff0a7295d0881c', 'es', '0f2a3d6e36b590dba6e93f3a10088a8f34103cae', 'Cuernos de diablo')
  , ('71ab18d24bbd5f46', 'es', '170d1f2f961db1e8e435c04f979012f0c4813bb2', 'Ocultar (1 min)')
  , ('a30778fa3d629f33', 'es', 'b7453a2df406d0e7a753fa2a13a759aea4dd2294', 'Muestra tu rango en vivo (se actualiza solo al subir o bajar de rango)')
  , ('d44b7e9515f5e841', 'es', 'bd67e561431b21dc42d2874a3fa3ff6248e3fa8a', 'Clasificación Dúo')
  , ('e15f7f445c46ae93', 'es', '4db13aa08e06f68b46f6d3819cdb45cae2b882d0', 'Crepúsculo')
  , ('3367c75f1b297a7e', 'es', '58f3cb1034a175e1d3f0bb7523c2449f731a9bb3', 'Rosa crepuscular que arde hasta el carmesí. Degradado de dos colores.')
  , ('1d3249d2a988a709', 'es', 'abc5f75a23c865711420044ed601217ae35bea54', 'Bloques rosa empolvado sobre un fondo cálido y tenue.')
  , ('554216dc58af09c4', 'es', '9b0acd4461ab7da7585950db970135db010f6aa8', 'Cada letra de tu nombre en un color distinto del arcoíris.')
  , ('5f1ededf6306d873', 'es', '7efda4c6d275389b1bfd26f7a15ac191beb583c8', 'Se come el daño')
  , ('fde511fb7c73ed95', 'es', 'e738c7d89afb7a9acb548496f7ce7ca8d6b2a2f0', 'Echo')
  , ('94289445357e1566', 'es', '4899aea0ad7311f429c135299da2adc96ca17eda', 'Main de Echo')
  , ('9d675c20af88ac85', 'es', '29ff1525ee6fdd2e6fd0e55e379a4e224f5776e5', 'Silenciar NRE EdgeBounce')
  , ('2b5b3a47fa9ab0b2', 'es', 'b4ce3eb96421a2bc09e75479472c6baa5a0610ee', 'Chispas eléctricas chasquean y revolotean a tu alrededor.')
  , ('c8a63c1732410b70', 'es', '9d2514d92ca9b022beab74865f8146bd878801be', 'Nombre neón cian eléctrico con un halo de brillo suave. Visible para todos; los jugadores con mod también ven el brillo.')
  , ('2c2b83458da6e21e', 'es', '50b385ec12fd86912cc1c6ecc39e0abf1a282cca', 'Degradado brasa')
  , ('17623eac4b59b734', 'es', 'f95951bd6069d431a0a73fc47ac7e0d3e44e622b', 'Brasas')
  , ('aabf3a6bbef39977', 'es', 'da32ecab00cdd3a4cfccfe58a62338d64fbe94a2', 'Esmeralda')
  , ('3273d686feea4e85', 'es', 'd84efbd1322c23b8b2a9cc87004e3c450ea13a8c', 'Brillo esmeralda')
  , ('fe85ade52f92f64e', 'es', '2c9dde1029ae34d4232e975c93a7a04067eb085b', 'Nombre esmeralda')
  , ('1fd64c1efd7d9083', 'es', '83bdd3b5230da99776ea3b56316a89419519fbcf', 'Main de Empty Power')
  , ('04af4b0b1909b0cb', 'es', 'a13f4b9bac07d2b398f39f962a4e6e6f64ec7afb', 'Orbes de energía')
  , ('69df762b04945155', 'es', '747064df7c49f0b13a9bb661d6209045ec2e3fdd', 'Bosque perenne al atardecer.')
  , ('31d3f2a1c4e5d101', 'es', '2ded2d6e7d0c2c2df38250fac32026e3469bedad', 'Todos empiezan por algún sitio.')
  , ('67c04e155d92e2fb', 'es', 'd7a501f83242fd940b8190529432e0703dd7606f', 'Experto')
  , ('f8722c358b268c6e', 'es', '16b52078a6f08d64300bd48fcb78dec76756adbb', 'Color de cuerpo rosa fucsia que hace llorar los ojos.')
  , ('14315d8bfdc142da', 'es', '42004fbbdfdd9e28f20bc7b40b8340b1016a8473', 'Ojos: cosmético de la comunidad. Llega con la próxima actualización del mod; equípalo en el editor de personaje.')
  , ('0f34e682111c0d18', 'es', '0ac81439129159c9c49e680faf69be65fb6d761d', 'Ojos: estrellas doradas. Equípalos en el editor de personaje.')
  , ('b8c027d3e3a34c81', 'es', '2684f8c6647a0ec56162173475a06b2700f4688d', 'Ojos: corazones enamorados. Equípalos en el editor de personaje.')
  , ('ed148bb9c7be8e8c', 'es', 'fabb304f63738fae1d8b8290dfa48d39166bd688', 'Main de Fast Forward')
  , ('1ac50717539486a6', 'es', '142cf28bcdc25525a041a6fdec70244bd7f34e83', 'Remata rápido')
  , ('6a77c5ad69934952', 'es', '9727f8a805db983c5d5372d96d511ce90094cbe2', 'Pocos llegan. Menos aún pueden pagarse el título.')
  , ('43b2f69fc34f5d0d', 'es', 'cdc31cb72e817957694d9471984bd835a93dafc1', 'Cresta de llamas')
  , ('4d0ae42a5167a39c', 'es', '455a8cfec6c15aa9f024bd2cb4d2dd92bafc3c6d', 'Nombre flotante')
  , ('857d64183e061d3e', 'es', '6c741cc15dd127d0473f2b78bab3176ede8c2057', 'Corazones rosas flotantes brotan de tu cuerpo.')
  , ('faad0c987e1f8490', 'es', 'c6b8dfc0f49980b4284e35414a755c6e2d0fa5f9', 'Para quienes se ganaron el derecho. Aun así, cuesta una fortuna.')
  , ('3482219b5141fa38', 'es', 'bc90b7b7a0f89810a21b4c074f2a6a74152ea24e', 'Forzar salida de sala')
  , ('26f48ec14590c3ae', 'es', '6038950c3ffe7f90843135db324457e4fa5b86b1', 'Fuerza que tu nombre se muestre en mayúsculas.')
  , ('37e3bb991b9d0230', 'es', '3f93069046dd262e169342cd220aa004644ab861', 'El inicio forzado se desbloquea con {0} inscritos ({1}/{2})')
  , ('acbb2acd18c65dd7', 'es', '86bb334f8ed2d24e6c396de77e5ca2c7be2bb490', 'Votos de inicio forzado: {0}/{1}')
  , ('c8b11f4b97ff6849', 'es', 'f41c4e4dab0b44d75dad0c04a0156d326c95b774', 'Bosque')
  , ('f72488c19efdac04', 'es', '8be4bf379229e1042e85793249e4608bdaa255c8', 'Del arte de la carta "Healing Field"')
  , ('280a08e85e79e12d', 'es', '6032a672e309a4dfd10a6c41199d5fd8c5c83da9', 'Escarcha')
  , ('aa96a51a1e9af834', 'es', '9905006070eedb6ae48e11bb4b977e1ba02955c6', 'JUGABILIDAD')
  , ('9234ccf14b5a0045', 'es', 'bf317bc7c73647140d56b21fbf2329d373e385cd', 'Degradado galaxia')
  , ('79a0762ddaf41128', 'es', 'd9cc3dc4f2aba64784ee730953c68b885afbe01c', 'Juego ?')
  , ('7b0dc0b4d08487af', 'es', '70016b079c5047ff972d699f67163ceeabf3ab5f', 'Juego {0}')
  , ('e5afdc07523f8396', 'es', '0b9ce69dc04eeb6c6027497ff1dc0da1030da5d2', 'Juego {0} - {1} jugadores')
  , ('fd8d7e51279627ed', 'es', '4200a0fa64073d825b8861ad95ee0536180ae1f7', 'Progresión del juego {0}')
  , ('fff10c9a1a7ab76e', 'es', '398ed329814977519b9f899253338884a2ba941f', 'Juegos')
  , ('b43c450431d13f59', 'es', 'f75572ef86d5cfaece368a57351d584911134e8e', 'Suaves pompas de jabón flotan a tu alrededor.')
  , ('ed2d10114d8fa1c7', 'es', '109fe33ee568cdbfcc2bccb3d5667edb0cfcc4a9', 'Áureo')
  , ('ecf3deede556e555', 'es', '5f1184f7df96c5928092ad9c6b550699bf887826', 'Global')
  , ('8de6c27992aeba7b', 'es', 'acbaf66b3f491443e004f29007d7da47b05d138d', 'Color de cuerpo negro volcánico brillante.')
  , ('8516a2f129517456', 'es', 'db4c6e762d551cdd15ce81da6fa4d2916ee2c8e3', 'Brillo amarillo')
  , ('3e6d65a6be5e46d4', 'es', '4f7ba9d9a46c7284d51a3dc4e628fabb3acec15c', 'Brasas ardientes crepitan y ascienden.')
  , ('41261dfa6845c60f', 'es', '0c0de17323ea7ac0e7c27b2c1521765db1278f0d', 'Color de cuerpo magenta brillante.')
  , ('0e8218c38e24e14a', 'es', '4ccdeb2b81cdab9d1fe2c4707b86bb05059e0f20', 'Nombre neón magenta brillante con un halo de brillo suave. Visible para todos; los jugadores con mod también ven el brillo.')
  , ('6c8b90ec9540ad5e', 'es', '72fdf7b43d255bfca709ad5b2f17f4c501334a6b', 'Nombre dorado')
  , ('badd96d7af08d83e', 'es', '361a685997549953a08875007aa5a09476ac95de', 'Gran final')
  , ('0621e139a09a22b7', 'es', '1e3c573a02d261117603239280b2414106d2de67', 'Abuela')
  , ('3426d61e9ffeccc9', 'es', '3ff31ec176822ae0d4a3602b4b80563f74ca6119', 'Cursor verde')
  , ('c91478ec31d61956', 'es', '3f508506b3bbc0e084dffe7ce76e5c8ec800e0ad', 'Nombre verde')
  , ('fb1478c1f65baa33', 'es', '82974e1f3b7ac1ae1fd1714ea5e215b421da1805', 'Gato gris')
  , ('0ac4a55c5f1ccb06', 'es', 'd77d0b27955f008358918e195742c4c8208699e1', 'ALTA')
  , ('8fec4bc289417df0', 'es', 'f3681d8bf189692334f17228e4c6f6976fc76e68', 'Halo')
  , ('112f0a217f5a096e', 'es', '6ce2c7378614f190440e5da3487b936abbd6781c', 'Difícil de golpear')
  , ('3960a6d82453549a', 'es', '06e27642e791a899db92ec7fc9fc01900dd8d863', 'Apresurado')
  , ('1e5e8f7d43e5b601', 'es', '6cad85d7f7dcd1b52fab90c0435e0ef4df7ef791', 'Sanador')
  , ('0b8a96a36bbd6047', 'es', '31f3455e822c8b2187691d06a5cbce86abba2ce1', 'Main de Healing Field')
  , ('90c59f6f9a2fdb41', 'es', '48ee9e4fba600c1e5238b5b30afe832cee3f4452', 'Ojos de corazón')
  , ('824fe214604ba4a1', 'es', '99f9bf69ff7f179b358e1191419dafa45a0d75db', 'Corazones')
  , ('4bdf43c6198c4944', 'es', '9de786a3c943e4fc74c3ab105df60d4a8cd2b8f9', 'Reservado al top 3 de la clasificación ranked')
  , ('341bc3956a62a4c9', 'es', 'a14b11926312cad57e30de5af74a2d2f016fe58f', 'Oculta tu oro a todos en la clasificación. Actívalo o desactívalo cuando quieras desde la pestaña Otros.')
  , ('a13104d1f01151a6', 'es', '7d45cd2bcca78ca9b078914744db3bdc40609f21', 'Silenciar NRE HitSound')
  , ('071c8c4641b18c3a', 'es', '2b77056d8510cbf771ae1eabe376618a805c01e7', 'Main de Homing')
  , ('7839675d71513a87', 'es', '0a651c070742e5b205bdf0d6ec0b389fa0524d53', '¡Mec, mec!')
  , ('e4ed2e45c87a71a4', 'es', '55d34abe601f847d5d3c021c49f5bf80f5db5d6e', 'Nombre neón rosa fucsia con un halo de brillo suave. Visible para todos; los jugadores con mod también ven el brillo.')
  , ('c6ea11f664524a12', 'es', 'cf4e2230ffef8a783fcf4ea4e36306115c1023c3', 'Cómo funciona - Async (6 semanas)')
  , ('58adc2e93f0e5669', 'es', 'b4a5f85c718b851bc30c568fe28f4ef79037ce0b', 'Cómo funciona - Sync (semanal)')
  , ('f501fa2dd1f5cbc4', 'es', '5eb10c630fc6887d4a44e6d2b996c378edff9152', 'Cómo se escriben las fechas en los menús del mod (historial, clasificaciones, torneos).')
  , ('8dfae9b58d919fe0', 'es', '32978fbe93d3be31d803d0f25bc182a893e9a2f2', 'Huge')
  , ('a95527c4eb90449a', 'es', '96096beb7426ce6ce5e38c347d4d90ad2a3f936b', 'Nombre enorme')
  , ('bce43d5b196d8359', 'es', '0c99c0f89091cfd5c213bec88778fa6d7c4b67e1', 'Main de Huge')
  , ('1491ccbbab4f77f2', 'es', 'e41832724539bffc1b27e6bf1721c3d4b02fee0a', 'Ojos de espiral hipnótica. Totalmente desquiciados.')
  , ('d8ba12181cae06db', 'es', 'b18f1b30f790bc9203c185bcbf4e886783ef9d75', 'Estela azul hielo que se funde en blanco. Degradado de dos colores.')
  , ('29acfd71fca68846', 'es', 'b2c854c19c069e8f54d7bc38119fa68daba14613', 'Idiota')
  , ('cf6154247e010be9', 'es', '896aeebe623741dcf08c97d02e0111f4311b39e9', 'Nombre índigo')
  , ('6155cc874330ae15', 'es', 'ad8477c02907e0acf0430c6c33bcc17614b5cbe2', 'Gris acero industrial al que le han drenado toda la calidez.')
  , ('742b61a27b8f06c2', 'es', '8564fe3b4b674b36c08f22266d713f860a15ca99', 'Hierro')
  , ('27972bcd47cb6e6e', 'es', '1616e2e5405e69c4e3914c67c644a9bd3ac00956', 'Cursiva')
  , ('5bebdfe868db2544', 'es', '39973be20679a94e4c998a58c0f6c76daaf6cd11', 'Marfil')
  , ('cb5be6eb1a54e3b3', 'es', '1eba140fdd9c6860a1730c408e3064aa417ca2a3', 'Salto')
  , ('14ff90268c5dfe1d', 'es', '933adea19eee0a6883654433bf5abd0a524cc8c6', 'Saltos')
  , ('101d281fb7725477', 'es', '27e105212199fa01c8a9ddb8d5052a43b991fbae', 'Matarreyes')
  , ('70ef6c5c94097ef3', 'es', 'f5b75e673715471ccd9edc10e29ada4d24f5dfdf', 'Gran yelmo de caballero')
  , ('2c692d50a4ccf781', 'es', 'f898dcaa913e7d96aa2f5cc90629d9e61f5f363e', 'Empuje')
  , ('683bcd6f2e8b0c87', 'es', '6990f01ad9d2dd9bf6acbd5330b2a51dc97e62e5', 'EN VIVO')
  , ('ad1e59715a6ba031', 'es', '826eff5d83a7f019b3d90ef265f759162f982ea5', 'CERRADO - EMPIEZA PRONTO')
  , ('bd5f6718ab6205d7', 'es', 'd8b9679fad55bd0178081bc796a093eec7fd845c', 'BAJA')
  , ('c5768a1032dce392', 'es', '75c88f3a0072cbd028982b65a0fcf2db0c4a5b15', 'Lavanda')
  , ('2130d9c2eb9e3c76', 'es', '4459b791a680572873dc2cf033487dc21edfcb9c', 'Limón')
  , ('a204547475823743', 'es', '417f106adb9eb8a88f7f754dff056d4ad92f62fa', 'Robo vida')
  , ('5431d62eb89eb032', 'es', '647b0df3eb0dc7b333f9063728d3b2e3785878de', 'Eleva tu nombre un poco sobre su base para que parezca flotar.')
  , ('a59a55265cfb11eb', 'es', '7e845d62d2ff38633cd16021f0b03eb78640abe0', 'Lima')
  , ('3b4605576de92799', 'es', '0582db7c610c15142547997e9e2b19457eef92cc', 'Amiguito rosa')
  , ('a48e13d370e30ad1', 'es', 'ce6afbd4b60bf8dfe8e4a2a6327ac8598e740559', 'Vidas')
  , ('c731a1c891e2ba81', 'es', '7ecb9e49219df7f9e2fafd4f4cd75eb164d24290', 'Fija el mapa a la paleta Gold de ROUNDS (amarillo cálido).')
  , ('d9f0ab270fa95deb', 'es', '1ca68d13c18e8e434805d0a510762510ca601ac1', 'Fija el mapa a la paleta Poison de ROUNDS (verde ácido).')
  , ('26d766cf70a26dd6', 'es', '9ae747eccb6b6170ae4f18896e498142e45387f4', 'Fija el mapa a la paleta Rainbow de ROUNDS.')
  , ('77501ba1887630dc', 'es', 'e07f293196ef7e0937ab9343b1984c5ffaf4e71a', 'Fija el mapa a la paleta Sky de ROUNDS (azul claro).')
  , ('5215a7389616213e', 'es', '2dc9a74a3d4c4d4552153339ca5aaf59af7a8a61', 'Fija el mapa a la paleta Soviet de ROUNDS (rojo profundo).')
  , ('a499e490a762a41a', 'es', 'c2cb065aefa60150ca2e076e295363c45308b3d6', 'Fija el mapa a la paleta Sweden de ROUNDS (azul + amarillo).')
  , ('28ade4ed4e32aabe', 'es', '6ce79956bdb35a2d91a54cbcd83332de043345d7', 'Perdedores')
  , ('0c996f453fd078f8', 'es', 'a47242e6772160f53510181c157f8401003ae798', 'Las minúsculas se muestran como mayúsculas más pequeñas.')
  , ('a28f48411a5bcb0c', 'es', '939ab68bfd22b3400b502c8401ff4be78f05031e', 'Trébol de la suerte')
  , ('0bc4ff39724d6896', 'es', '9fa8c9a61e28dd229fc118d6c8e04e77a7a2a087', 'Tréboles verdes de la suerte revolotean a tu alrededor.')
  , ('605b23aab951f318', 'es', 'aaebd0c4faae71a489204727bee2e9b3773fd5a8', 'STATS DE PARTIDA  <color=#888><size=12>(mantén Tab)</size></color>')
  , ('84ed7380201d44df', 'es', 'f68525ad751f8a1d932458c4c58a214bdf0b30e9', 'MEDIA')
  , ('61abcf4400fd7a42', 'es', '3548c9250892c509047e2c7ec04d76bf39c63524', 'Magma')
  , ('77f5fa96a313fa19', 'es', 'ca6ebdf49e3b17cc5b9a43d5ab6a00aef37e3a3f', 'Granate')
  , ('32ef039ee20872b3', 'es', 'ea6dfcad0bbb0197cc432580a763bdd37c55ef73', 'Omitir update del menú')
  , ('5aa6d8c6966b7d57', 'es', 'aaa70f58c89e39722304f18ce50db0b7bf8907e1', 'Menta')
  , ('c92f5f7bded0170e', 'es', 'b6af76411b6d6bc9e35cd94b8b7ea98f83b14aaf', 'Cromo espejado con un tinte suave y cambiante.')
  , ('4f87758656255ee4', 'es', '1dda992b70d55b62ecc5e22ba264afe7a9f07d02', 'Monocromo')
  , ('0844884be994ab63', 'es', '037358024aa12328fac8d7804df79d1552816c63', 'Mes/Día/Año (EE. UU.)')
  , ('53fc58107ad3018e', 'es', '6938f3389402f793e6adddb682e3586aec57a2e4', 'Más ranked que casual.')
  , ('67a6d0f456b16987', 'es', '752fbb36578511afe3527c40c95abe3e1f95d7bd', 'Musgo')
  , ('44296b8aa369d553', 'es', '3d934064bc875a99085c8782d09dde442c97d696', 'Bigote')
  , ('1d0c46aee85e3de7', 'es', '7f2f10fba7859343ca2963aa166a642641709abe', 'Boca: un distinguido bigote de manillar. Equípalo en el editor de personaje.')
  , ('53236f8f806d6a56', 'es', '9b4279e882d9e4eb0133e566ccdea4fd7247638b', 'Boca: cosmético de la comunidad. Llega con la próxima actualización del mod; equípalo en el editor de personaje.')
  , ('a55f45e878c399c3', 'es', '1e7a29d5061a52a7f293263e92f9a5aba4275e1e', 'Boca: cosida y sellada. Equípala en el editor de personaje.')
  , ('baba0a75c39bf4ee', 'es', 'ae53d6915d23e165765583cc340533e6e418cbd7', 'Vel. mov.')
  , ('06283c7ad737ef2a', 'es', '931e8d8cc7286798b1633cc33805cf51193e14f9', 'Mostaza')
  , ('36d700539721f63f', 'es', '6845c6d90585c24d63de266c9a6da04090ed2dc2', 'RED')
  , ('d6f2bbfbd961e078', 'es', '8c4507cb4fa8d59453f7770418e0681c1acdcfa1', 'Bloques casi negros sobre fondo negro — contraste máximo.')
  , ('6db0703509c1dfd1', 'es', '7633072baa568d07dcc6acf347d8e0c67d78267f', 'Cristal volcánico casi negro. Se funde con la noche.')
  , ('76a3b977b8f74add', 'es', 'e91fae69ed9d52f9a959fd0aa232df98f563c6ee', 'Neón cian')
  , ('1ce0cf2cdb6b1aa8', 'es', '664681d96609b863f34e7bda85acda6b22882fc8', 'Neón lima')
  , ('7ce4510e0289c059', 'es', '02140665ff58b93bef26879f6a7975a896f578d5', 'Neón naranja')
  , ('a7c09f9477311f3f', 'es', 'ff2c0cb639d80711db062bae5aec601a4e61ce51', 'Neón rosa')
  , ('83394acf5203df01', 'es', '3b3e75bdc737be9d9289b248cf3318803f001c65', 'Neón tóxico')
  , ('9fc067aacc4b389f', 'es', '25e66746dc67e99386bfd26e11749d59a7a08c7e', 'Neón violeta')
  , ('e82cae6d83d41b06', 'es', '7688eb7fae9a048dbbeed0e73b646bf684cc09f2', 'Sin torneo activo')
  , ('72839b0611990203', 'es', 'b47b90daf74ab5d4bbf2b814f199f2ddf3ca8ded', 'Noobie')
  , ('692dbb3bbe0f1257', 'es', 'b8a8dabdec32830a601c4453d32a42f6722011b4', 'No es genial. No es terrible.')
  , ('40db0a284e076c04', 'es', 'dcf9125b0badf4d4589de22a864504ddd27927f6', 'Despawn de balas OOB')
  , ('7ec612c4edc75150', 'es', '957c024b38ce820878f03177ce3d2b83c26a82d0', 'OTRO')
  , ('a719fac14ec5fa11', 'es', '72d696a4f4dc7c22c8686bf0360cf923d40de5aa', 'Límite init ObjectPool (en partida)')
  , ('2a0816edad12844a', 'es', '24c869802c3e242e28585a1c90c21847f259e4f8', 'Obsidiana')
  , ('7da210afed1bb3ea', 'es', '7e4c3a7dbaa079df9174e3a12981708587d175ed', 'Degradado océano')
  , ('0f0e4598b4018d73', 'es', '8f62f4336f1907e6dc87f983416184094f6ff35d', 'Oliva')
  , ('3242ce42885c8179', 'es', '9a11776ea9b0901090a67e662d47f5e9fe990089', 'Abrir formulario de reporte')
  , ('45faa04dd395d9ae', 'es', '1e9ed67a9b31975b8a43893fcd351af7231d2512', 'Rival:')
  , ('7e1141fef186c747', 'es', '00611e720d436d942093ef05ad8481bacf52f082', 'Tu rival aún no se conecta — espera...')
  , ('4d8c0cc6fc7fefd5', 'es', '783dedc30ac7f71e7f9b2ebba24f435e2f0ea30c', 'Elecciones del rival')
  , ('b99e6172f212d16b', 'es', '1af2afeff5d2f90ab6966cb74e75ab1e1082b53d', 'Cursor naranja')
  , ('572dd774b6ee6a62', 'es', '3997c754c441e48d35184d2d9db0a028a6c9346d', 'Degradado de naranja a amarillo que abrasa la arena.')
  , ('8ab8f916e666eb1a', 'es', '998da40bba23a7b05d2c404389849f0f793b49dd', 'Azul hielo pálido, como un cielo de invierno.')
  , ('bf950976d4c6643b', 'es', '9c702f519475562bf73e49dc3a37c10b50a87674', 'Nombre amarillo pálido luminoso con su halo de brillo a juego. Imita el clásico truco de color de nombre de Steam.')
  , ('51b860af248239b9', 'es', '33965e30fc529ff12defc4f985185e526707cd07', 'Bloques menta pálido sobre un fondo frío y tenue.')
  , ('bbafbcbefeee1a04', 'es', 'afd15ef89657a69cc8d382f43cae628b459cc1b2', 'Color de cuerpo hierbabuena pálido.')
  , ('8276060936caacd4', 'es', '9d32fee8673386fcb48650a016fe7874c5c0f377', 'Corona de fiesta')
  , ('02a88da890abd1ce', 'es', 'd0cfb954a9334a6c99881784734346cd543a750a', 'Pasa%')
  , ('8227d56c911268e1', 'es', 'f08ec7ca421c33b887294dd88f4ba78c26fd48d7', 'Degradado por letra de cian brillante → índigo profundo. De la superficie a la fosa.')
  , ('b03342feaff2e735', 'es', '3f1c0d14e823390910e171a2cb32a8ad991d59c2', 'Degradado por letra de amarillo brillante → rojo profundo. De la llama al carbón.')
  , ('b42387c8be516f9e', 'es', '57a7a6cdae35659fdaab629a1af89418c8b819e0', 'Degradado por letra de magenta → cian. Nebulosa interestelar.')
  , ('cf5aad12a3f6733b', 'es', 'e33445036b26cc0c43db07baa039c326346c1692', 'Degradado por letra de verde azulado → violeta. Destello de cielo nocturno frío.')
  , ('30ad5fe9e45c303f', 'es', '32efb45b331be9c80dc68d23882fe31dcfb8b1f2', 'Equilibrio perfecto. Una mitad clara, otra oscura.')
  , ('2cd796c73bb4cce7', 'es', 'baae5e74ea779b7a0764d7e688a498b8ce825e73', 'Interruptor general de rendimiento — activa o desactiva TODOS los parches de abajo a la vez.')
  , ('7df6272aa44de13e', 'es', '3e978fbf8aad93b7520fcec25f666a8823b47615', 'Phoenix')
  , ('e77e0b2592889257', 'es', 'e667878de6874deec7efb0c65ddf39bb296521af', 'Llama de fénix')
  , ('1cd08b528d6cb3fb', 'es', 'a1b97d981b566c2923f68b338c4d2b81ee2018a2', 'Elige tus horas de inicio <color=#888>(selección múltiple, obligatorio para inscribirse)</color>  <color=#7FE8C3>mejor hora: {0}/{1} de acuerdo</color>')
  , ('4be253b8080d3f06', 'es', 'f5f61efb04cc0bde68137d2124c1656a262a2038', 'Elecc.')
  , ('21464be1e8300f5e', 'es', '456e097f4ceb19803ed7d70dbf2d28a51848d23f', 'Pino')
  , ('4bb91d4741ebaf17', 'es', 'b12540f76b8ae0ed79395737854d6d05a71804a7', 'Cursor rosa')
  , ('88d9415535dd3e6d', 'es', 'b6744ad14e80c3f4975d1874d4abeac76118559c', 'Nombre rosa')
  , ('a39999e17f4758a1', 'es', '96ef7f60b0e12322ce4490d8ea26c66eb5e0576c', 'Apostar')
  , ('1d7d88d5ab1ccb40', 'es', 'c93fa0a5953ea725bfad3d51caa53e0abd992fd2', 'Platino')
  , ('e9939d439ec9d4f0', 'es', 'e53407cfe1a5156b9f0d1eed3bab5ef3ae75cfd8', 'Jugador')
  , ('3bc81240cf6b8795', 'es', '315b1f52cdff2bd5975f933f866c66ac0a84f8ac', 'Jugador {0}')
  , ('cdf6bf28ca817ee2', 'es', '971b5de3da8d8c6ca118ca7ced01592c6e67bf00', 'Podio')
  , ('b4afe6f94d8a1b3b', 'es', '6de0b0c656444c55bac48c2e467aa0f841083cdc', 'Poison')
  , ('c7ff4f384e1ed8c3', 'es', '994ef00e3288928269240324105bb35e1304c87e', 'Main de Poison')
  , ('0e72750e37c7c6a4', 'es', '53b8d6d04b42c5527575738edfd453c84e07ad7f', 'Envenenador')
  , ('6ca9dd38e68467c1', 'es', '79e59b6d40ad67a86922bb3f5937e4a051c43f13', 'Porcelana')
  , ('68b06756b591710e', 'es', 'd603c62a187b010ba86e02a8a3eae5477f7da9ca', 'Tirador de precisión')
  , ('90d0551d9d3aec2a', 'es', '2fd710fc7265cbfa6686c3f0b03de6975d70e6f7', 'Premium: muros de plata fría que destellan a blanco puro, sobre gris metálico oscuro')
  , ('51afe625aeb8a965', 'es', '22f4f84ddb194e43610ebb98e62014a7317abfe9', 'Premium: muros de oro fundido que destellan a oro blanco, sobre una bóveda de bronce profundo')
  , ('a1b12781f1dcf408', 'es', '381ae69d6dec239a744146b21683d1da1f3ef1c0', 'Premium: muros de aurora boreal que titilan entre verde polar y violeta en plena noche polar')
  , ('a1b5a04f8d591cb8', 'es', 'd42e29e77884854a5e8b41eb4d0996d9758c52e4', 'Previa de registros')
  , ('75b908029624d68e', 'es', 'd2b78d262308d18630b0a15b9c03018be74b5d16', 'Previa: {0}  <color=#888>({1})</color>')
  , ('204f8caeaf9b9177', 'es', 'ffad6acebcb46cb4a5b292d6ce8b9156bb2952e3', 'Prismático')
  , ('88fd0dc2b471baea', 'es', '04a4408655caed1756da3dd8fddd01e0563e0a94', 'Estela prismática')
  , ('8dcd95733f0c2303', 'es', 'f33e1d33043740f2b9906fcb880abd6d11a6a22c', 'Título de pronombre.')
  , ('b90ef63e7495e242', 'es', '1bd8f1b24f475d07e65940615d102d138bfb866b', 'Agresividad pura')
  , ('b8fdc86007277b7b', 'es', '58574a4f8f3a1703dd84bf2e5628e34cc1c666c9', 'Escala de grises pura — mínima distracción visual.')
  , ('30517b69c320de25', 'es', 'b9dff734194f8410236cfa4ea86d68ede85cdb6c', 'Cursor púrpura')
  , ('15902baa613f6be8', 'es', 'e1b4569dbbad3384f405de04efad13c425231ab2', 'Nombre púrpura')
  , ('b184685895afcf0d', 'es', 'ac2f7ec50caa3e176d76d18c4b08ddc29913a773', 'Estela de sombra púrpura y negra. Se siente mal en el mejor sentido.')
  , ('7b55f022da9fc830', 'es', 'fa664531b4a41c6178b16cb21826ade02ac9de83', 'Main de Quick Reload')
  , ('19028acb5fad6b86', 'es', '75e2d41b04a8463628b2f2bc5c724326fc3488ac', 'Nombre neón verde amarillento radiactivo con un halo de brillo intenso. Visible para todos; los jugadores con mod también ven el brillo.')
  , ('5f7558f212422e9c', 'es', 'b4a9395d25398654fd5d000e4b82a1d8273339bd', 'Rainbow')
  , ('b6862f5ae4f76951', 'es', '9b8cce5d7eccd2e22579b152d9d9be67ab1466fc', 'Aura arcoíris')
  , ('0dc7d933cccba541', 'es', '153fd22a1e9af7179306e615f49ac52f49829bc6', 'Nombre arcoíris')
  , ('ba3394d24a886db0', 'es', '41434103e0f30de4583dbd5d09e8fbdce6268ecc', 'Banderas de guerra')
  , ('287bb7dfc58feb5b', 'es', '5ae95848f1654fdab6009b60a2e5515c472863d9', 'Rango: <b><color={0}>{1}</color></b>')
  , ('e0ed74112b5d0272', 'es', '4e02c65a3230ab22a99e846d79d4b4d46cd9901e', 'Ranked 1v1 - 2v2 - torneos - cosméticos   <color=#666>v{0}</color>')
  , ('8e9f5c5b8f417285', 'es', 'debb4916739eaee8059bb06b20b9668167be4310', 'Forma Ranked  <color={0}>{1}W-{2}L</color>')
  , ('1249b6f1e502b718', 'es', '9010764c511b06ab2dc58692c34c829ba1fe04b3', 'Series Ranked: {0}W / {1}L')
  , ('e316e9a339cb0454', 'es', 'cce370d2f9781af0f85d591ccdfad1fe365a619f', 'Rara')
  , ('948adf594528007a', 'es', '6437b7bf655854909262d5f53fbe3bc7a6665b48', 'Rating')
  , ('07b271831742817a', 'es', 'dffa7f7a058fb0d2e1dd78e84871a125326455aa', 'Historial de rating  ({0} Elo)')
  , ('3142710df7c231f6', 'es', 'e84f8f8af9ca7d8045a45616eeebdb971f4ba6d1', 'Historial de rating  ({0} Elo, {1} juegos)')
  , ('b01fdd24bef99b35', 'es', 'f6c0bd7cdb978fec1a5df08a6c5cea49360c6da7', 'Rating: {0}   RD: {1}   Pico: {2}')
  , ('4dd589a0e595aa79', 'es', 'c4097eedd44962a5de126d3bf379be9849404efc', 'Renace tras la derrota')
  , ('1f35f046ca078416', 'es', '8944bac56fb71a84e3ae82e1b90e93e2f2b4bb1d', 'Cursor rojo')
  , ('505d826bac112c1d', 'es', '126a8e3bc4cc743f66d97a23baa4fbd94bca9cd1', 'Nombre rojo')
  , ('725c315d1c164ba0', 'es', 'eb5c821caab94e7e985a15dfcbf1150b086c8ba2', 'Regen')
  , ('cb173826046b9943', 'es', '8d4e4ef3ea5252ec5235e4b1dd463ae9c302422c', 'Habitual')
  , ('e4b1a55872ab7dc2', 'es', 'cce7155371fc26686b89c7452337d8419692f31e', 'Recarga')
  , ('0348defe86351f3c', 'es', '35360f9710e178438cf0beacd29bc2cf155be508', 'Recargador')
  , ('6fe9842db9d19141', 'es', 'f8f842c1e0272e4182ba74a5e1e671b7f8a60f30', 'Muestra tu nombre al 130% de tamaño.')
  , ('83f263b559925710', 'es', '452eca3c01172368dcdcba51547a09396c0414a5', 'Muestra tu nombre al 160% de tamaño.')
  , ('8746ab9f9b6503e4', 'es', '1c9cc5f67a8641039f1e6e54ad1f7adec3a9c7c9', 'Muestra tu nombre al 80% de tamaño.')
  , ('3f6dd33f95a50171', 'es', 'cb3df1b14988aa02a85af24309f57e8594a845eb', 'El reporte no se envió - inténtalo de nuevo en un momento.')
  , ('6aefe5059d63d0e1', 'es', '3e4d1a0220051e28866e692fcc1749e765c15125', 'Restaura la rotación aleatoria de colores de mapa por defecto.')
  , ('145d5e6640ad6679', 'es', '64beb88d5891e40c3adbadb8b1959b410db02d70', 'Color de cuerpo verde bosque intenso.')
  , ('1ee9d7c98695afd0', 'es', '969e7cedcc56832829613fa1b9a6909c8e2c57e4', 'Bloques púrpura intenso sobre un fondo frío y tenue.')
  , ('06d95cefa1d007e6', 'es', 'c3916b69a2b9f6d25258ad6c41417cea07f376f8', 'Gran yelmo de acero remachado con visor en T.')
  , ('35ad337d5d3a9060', 'es', '51ad0eae3f66ecd3c72bfac9373650513d6f6603', 'Rosa')
  , ('0b37036b006bc7c2', 'es', '2c16ea11eedff827b4e8ce41cee5f947d3418592', 'Regio')
  , ('2b9dc3fb741aa589', 'es', 'c085d0e3b3ec14e7c2c9f0463ff2c8a00dec591e', 'Púrpura real que deriva hacia cian pálido. Degradado de dos colores.')
  , ('319ab86ed9da45f2', 'es', 'e13a8edd76d54551c7e4fbee3597e104900c26f7', 'Color de cuerpo violeta real.')
  , ('cde7ff6ff03c626f', 'es', '2ba111743a13e4814bdbebc66f111af1605fcea4', 'E s p a c i a d o')
  , ('ba7370f908154504', 'es', 'b36fbc6e8df68fb14280742f8b5bf0c0460a6fe0', 'Arena')
  , ('970796f2ee569bbc', 'es', '52086129a3b5fc408aafd7614d3de4b7de05c35a', 'Zafiro')
  , ('61873d24740b083e', 'es', '1207638e87127a3ee0ecce2ac2254ea4a7aa6c90', 'Escarlata')
  , ('f7c0cd90c321493a', 'es', '3295f8d8261083d7f28652ae6b6758ca2369e347', 'Progresión de puntos')
  , ('03fd7046e9ef2d63', 'es', 'd2ad76935ab2f3bb89bab2b67c98d79e2728d61e', 'Vibración de pantalla: <color={0}>{1}</color>')
  , ('8b51734bf0cceea4', 'es', 'c2e5f7ff5a1b8a7c192fd6c5c49f8ff3a27c1d45', 'Color de cuerpo verde eléctrico abrasador.')
  , ('371c04da36be20b2', 'es', '6605cbf9da74dcde301ce970f5892a9c6f3697f1', 'Nombre neón lima abrasador con un halo de brillo suave. Visible para todos; los jugadores con mod también ven el brillo.')
  , ('c8a7d841ea12ccc7', 'es', '4e759bc7fb00171c1450a5abdb85e63a0d4be467', 'Conocerse a uno mismo es una virtud.')
  , ('c6e48e66ff28d8d5', 'es', '3054ab05070e872c716ae126a3e99c407fdf4eb1', 'Enviar ping')
  , ('56f4b006168b90b0', 'es', '31b7561e9ca64f61bfd860c5d4af7ecf229dabfe', 'Serie {0}  vs {1}  (en curso)')
  , ('694b7bbd6fe29463', 'es', 'cbf8b1e91683087706a4ed11db627eb9673a72b2', 'Serie {0} {1}  vs {2}')
  , ('2974b8e5c24bb499', 'es', '5d92c2e8b2137b358d6e0cee27dc8213007e445f', 'Gravedad:')
  , ('e20ec9323e546397', 'es', 'a35631709ba4e1f56d3e2be869b3d25dd947b31a', 'Recorre el espectro mientras te mueves. Puro postureo.')
  , ('2ff4e59a6ac2fe45', 'es', '98f69d719183344b0e6cf41bda85c41161fb7494', 'Siena')
  , ('44a663da8c3a7fdd', 'es', '393bd9e94e9108ea7fcbcb67d93d3269709ea07b', 'Inscríbete para desbloquear el inicio forzado')
  , ('f522e76707a4e0d9', 'es', 'b7152342a267362add3c0d7f69f720f7a9c76c9e', 'Tamaño')
  , ('23ba5ae4bf44caf7', 'es', '237ffaf765bbff962746c4fd0c785881512d1eff', 'Omite MenuControllerHandler.Update durante una partida activa.')
  , ('e23866b89558a941', 'es', 'b3d97fd6dece388a968e367f3ac4b9e64d739f52', 'Sky')
  , ('5b1fa8823faaa4dd', 'es', '26d7b218c9b5641b37dfddc13b955184f3ce868f', 'Pizarra')
  , ('567890efd6eb4e17', 'es', 'b0476d817e62b78a6d6b13910299b1a6c90d3d83', 'Color de cuerpo negro elegante.')
  , ('811bf05184f39e45', 'es', 'a8e56ef9b0223468ffe7a2e5ba21d538d23afc66', 'VeRsAlItAs')
  , ('9237062066f5d776', 'es', 'bb79f3faedd4b8feda0906367e3938079bb3cd8c', 'Nombre pequeño')
  , ('21a19e853e62a77b', 'es', '7b3d0b443ce4a8405de90ed439b33999c90d489e', 'Humeante')
  , ('be93e1ed6ec90fec', 'es', '2081d06ecb8f68cbf79e9de820f81f7f82fa4625', 'Sniper')
  , ('91d61c894d41c995', 'es', 'a3ad936a7ceda44469920ce62fe5947bde0aa040', 'Medalla de sniper')
  , ('5def38b6c29f4d9c', 'es', 'f9d59a6ea8c756838f928f0d95c9d34e4d99db37', 'Casco de refresco')
  , ('fcdaa994cb09a325', 'es', 'ce8d0da33206ab07f9dad187d28ae162ccc22b29', 'Pizarra suave')
  , ('6df0149175e82e19', 'es', '2394bba21d20d3da5d703014c5a214f15bcef2be', 'Lavanda pastel suave — contraste mínimo.')
  , ('3e776304a375d625', 'es', '1b7253a3591f76e461aebe6335506a201a17601e', 'Color de cuerpo violeta pastel suave.')
  , ('9d9a02388f682516', 'es', 'f7bce6256e4c4cbfffd0c61e2708265490027f17', 'Color de cuerpo rosa suave.')
  , ('658d71d742121ed2', 'es', '3d40c20821471e017a6f118ca7911fbcea797946', 'Clasificación Solo')
  , ('321d3d0d79d4c6db', 'es', '65cfa78989387ca19f18d1d54af0d45dfb8fd9ee', 'Soberano')
  , ('093cb8d328f0f8c8', 'es', '42724976abf218f52fcf92c452432ec282de21a7', 'Soviet')
  , ('4de9de6e1f656ebe', 'es', '45bfc012fbf82490776101b9c6b63887c8a0fb1d', 'Chispas')
  , ('94f1cace756e2725', 'es', 'e0ad3ab875f57eac75ebd47534939215a9b96daa', 'Espectro')
  , ('64f50d41089a0db6', 'es', 'a6a7b70436b1cb9914649ca0f29a787099ee1c15', 'Saltarines espeluznantes')
  , ('74892e8d7d529b3c', 'es', '2bde101117a83786a9fe359d813c1badf4a6b2ee', 'Dispersión')
  , ('f0f169d5182d3441', 'es', '1c0cb5239f106c2576fc15b5249d073c7cf406e0', 'Orejeras estrelladas')
  , ('67639960c926c58e', 'es', 'f2698c4901757c1e713246a5a58dd359698f9f54', 'Estrella en órbita')
  , ('608561ba53ff573f', 'es', '6134bd38cec65de46eba3419acc1c714ffe1cd20', 'Ojos estrellados')
  , ('e8f48481d4bd7c9c', 'es', 'e3c95802a4529c0f536dbb1eaf80bab813a2d5c0', 'Empieza: <color=#FFDE88>{0}</color>')
  , ('854774247858c849', 'es', '084282a69463a804d2336837e4f92bd0b0d0160c', 'Estado: <color=#88FF88>Permitido</color> - los datos de partida y la vinculación están activos.')
  , ('3756e6cfebef3865', 'es', '1701a52158cb5b8eee96db12e0453dc68ee4b165', 'Estado: <color=#DDDD66>Sin definir</color> - el aviso de consentimiento aparecerá en el próximo arranque.')
  , ('ac2ac9790f0283fc', 'es', '593dddce7c4ef2c47cc34038dd0fc0cc18c8e576', 'Estado: <color=#FF9966>Denegado</color> - el mod funciona sin conexión. Ningún dato sale de tu equipo.')
  , ('c181f97737843bb1', 'es', '79144fb22b8fe57dc5e4025fa2451b9c9fbe973a', 'Sonrisa cosida')
  , ('8c303afe63579dd8', 'es', 'e6dc9396aa17a023a695be860dd2f06ed4399346', 'Halo de tormenta')
  , ('7d6b3939f985247d', 'es', 'f9ae58aa354c851627202a2bbae82b33dd0da9c6', 'Tachado')
  , ('f0ca80932eaf824e', 'es', '78d736bb8b31ffc0d1147e4a8bb2bbb2bf209874', 'Tacha tu nombre. Combinable con otros estilos de nombre.')
  , ('d65e985d67ed0fe9', 'es', 'e41871fcab992523ffd460e45c652811a5aa37cb', 'Null-guard de stun')
  , ('d1444d8ccb532eed', 'es', '702282ee3b8e83ab98bab528edd90b1983df3f06', 'Null-guard de StunPlayer — corta el spam de NRE cuando un jugador se destruye en pleno stun.')
  , ('476093e331464f11', 'es', '2dacf65959849884a011f36f76a04eebea94c5ea', 'Enviar')
  , ('c76ede26fcd816e4', 'es', '1ca00033fee3d4e5ee3de55b2d380368d9310d48', 'Enviar reporte')
  , ('9b898dc5487d84cd', 'es', '46a1a6919d196b4d95a74a37cc19f2ed4c66d0eb', 'Enviando...')
  , ('1d212540835c92ae', 'es', 'dd5499d7f0a2d38242360148c069aa29f121ccbb', 'Halo solar')
  , ('60bbbc527e3744da', 'es', '181bcd5760fd32163554c899301a30b2cd381cf4', 'Atardecer')
  , ('8fc96ffa03aaafbe', 'es', 'e6e56698abc25872406e861b0aa5e10015632ae8', 'Degradado atardecer')
  , ('7fbedacc6efea800', 'es', '13b3faceb8360fa55fb94098c6b1e5b6b8d19f27', 'Silencia NRE de RayHitBulletSound de padres destruidos.')
  , ('c7a5a26638393134', 'es', '868d0b7d0ffa614abcff7ba14ad2d6bde86a1b2c', 'Silencia NRE de ScreenEdgeBounce de balas destruidas.')
  , ('6ebdd285f3b71ef8', 'es', 'f53f0af5f87f3ba660422807a1435727faeed72b', 'El sudor es solo XP en forma líquida.')
  , ('62945646ff725873', 'es', '0c95f4a83a19eb2e8965d24c44c42df5b61d5388', 'Sudado')
  , ('6028e9eac2094a5a', 'es', '72ddd2b619af6d6a73febf80f7fcad22495498cd', 'Sweden')
  , ('cab4937719a22718', 'es', '133552ebfbcce8310f8920695422699d5256bac9', 'Bronceado')
  , ('247786047e006128', 'es', '0ba4d1aee6f233efc1f3b78141b4af7d08b86c3c', 'Tanque')
  , ('abd355e13a15e46d', 'es', 'f9fb8665cb51f149f63f06a976a3324713219468', 'Main de Target Bounce')
  , ('50ac155d36ece430', 'es', '5f6aa78e382c01b370e8b343a9c1b5a2b5fa6705', 'Capa andrajosa')
  , ('3b01b61b340a5223', 'es', '619a16e83766383c2d21a829f80bd5d01c671c25', 'Alas de murciélago carmesíes hechas jirones, recién salidas del abismo. El alma se vende aparte.')
  , ('eb382d1678858a9c', 'es', 'df0ad373b7ff60d6a8987458fb00c1e4832ef605', 'Verde azulado')
  , ('b234d0122bbaa63f', 'es', '117e0234bc721029ca23bc4468eaaf69939a267a', 'Gracias por probar el mod durante la beta. Gratis; se retira al acabar la beta.')
  , ('e18bda3d30d526af', 'es', '526a09199b53f93b3d5427114172a2671c6cd74e', 'Corona de espinas')
  , ('12f7c7e33d999282', 'es', 'cb7c351d80fb7f2eb5d656664b0709b7a3bd0416', 'Tres esferas de energía pura en órbita. ANIMADO.')
  , ('1271aee114daa4c4', 'es', '5bd44ebe63cd3b9445ca759f970513d78b28a61c', 'Tier')
  , ('e571d7422af03bcb', 'es', '0ce8e5dac8f6f61d3eba42d016f55230f093a2c7', 'Titán')
  , ('190526c2629dbea2', 'es', 'e5f48c13ee118dc3dacd8e536d53a9d26f5301df', 'La cima de la cadena alimentaria')
  , ('f734b208caa4f204', 'es', 'c15771fc77a45dae33911c04bb171e6f49fa33cb', 'Rastreador')
  , ('9c494c7f25abb2c3', 'es', '502598c638643dedcad27c187b7569ebb08e4615', 'Colores del orgullo trans con destellos de partículas.')
  , ('6f4efddd4bda07b6', 'es', '1599ddb3455a45ccc59a3fac422049947650292b', 'Tride')
  , ('0cab6cacbbc851b9', 'es', '0c06f367e6f129656bdd8dd841192a6f4d2dcb57', 'Tryhard')
  , ('b35fb4ad612dfe48', 'es', '05622e2e52c968bbde79af9c43a01a69c348ffd0', 'Se esfuerza, y mucho.')
  , ('cd5edd2dfb625384', 'es', '6caad4cda78d3c6ad47660162f70accf6748494f', 'Ocaso')
  , ('61bb06cc51843ce1', 'es', 'a9b6b056b13b501af43880063da2ed0de4059f24', 'Dos estandartes de batalla cruzados. ¡Por la causa!')
  , ('fbbce02111ccebf0', 'es', 'fc31465be9e079dfb54cb2d55d591edc83fd4ceb', 'Dos antenas verdes brillantes. Llévame ante tu líder.')
  , ('66b1bfa0c7da43ad', 'es', '1255b7d12b59020bccf9dffde6b463bb84d3eedb', 'Tierra')
  , ('55d6340624531595', 'es', '630e0b25835dd27620dc4ef0c6b4d0300696b62f', 'Poco común')
  , ('ef8b357138a3ef69', 'es', '39773aa3efa19090c918baedac1fe737dea25b92', 'Subrayado')
  , ('3c3c5f6eac20881b', 'es', '1b1d817f13affedf2bc1117a61c3b4ca949b2e62', 'Unity / Juego')
  , ('b8726a2e1acd9dfe', 'es', '1d4d43cc6f3a833e0340a0d1794b6d7b9958657e', 'Usar')
  , ('dbcea9ac17806e03', 'es', '67e7a92881ae1200be8d73f68942f37d8b841edd', 'VOTACIÓN / INSCRIPCIONES ABIERTAS')
  , ('e222892ca8d0f4f1', 'es', '50c8e9195e5ecd5791a33f4dc54310bbea98a77f', 'Terciopelo')
  , ('3950da75a154598a', 'es', '9a39b423a562fe4943decb524e92851ad0c94a4f', 'Nombre neón naranja vivo con un halo de brillo suave. Visible para todos; los jugadores con mod también ven el brillo.')
  , ('2dca86b596943f57', 'es', '207c7c00630b836d3afb46848bdb24a92023331d', 'Vacío')
  , ('4e8fc7c0e6288df8', 'es', 'ec5f447f3fa0edd8c92f7101ef7f729f6466b96d', 'Onda del vacío')
  , ('6023f2dc69b9be58', 'es', 'd44941df851133e25121f54f10ddffbc79ed5ed4', 'Voidshot')
  , ('e59b71033ad70521', 'es', 'f7585ab975d96d0a37f8cb0b66d945ba600cafd2', 'Esperando a que se conecten los 3 jugadores — espera...')
  , ('1a75ea9cccafc189', 'es', 'dbe4d86fb51352879c5bc4e9cb3c5823c4ee486c', 'Color de cuerpo naranja coral cálido.')
  , ('dd76e64b87e0aa28', 'es', '4700ad8692d08573598fbb4950115440b6c1c7ac', 'Paleta cálida de crema + tostado.')
  , ('c198ec18f335a171', 'es', '427a3cd1255e088f822589a37ac6636241598de9', 'Tonos cálidos de arena del desierto.')
  , ('05a9b2435b114fb5', 'es', 'c148920398c05ff36e4fcbd84d182dc5c3cc1650', 'Color de cuerpo dorado miel cálido.')
  , ('e5e3095c005a72cc', 'es', '8b99503fef5328110821262702556cf11f1dc23b', 'Bloques naranja cálido sobre un fondo de tonos de atardecer.')
  , ('b25a2fb5ec8a68e0', 'es', '7afa3cb197e2dfdfb6813dd41d7d5de2c47e7c19', 'Cursor blanco')
  , ('d3932de27d2daea3', 'es', 'c0365b235944850932d02480035816faa8e51970', 'Windup')
  , ('403c28519696a825', 'es', '7bef0c61f63c0bafbdd397fcdb4fd5388041c31f', 'Main de Windup')
  , ('8f7d96d5e823b55f', 'es', '1d50bf1d8b44e075c6690ac4d150713976be836d', 'Ganadores')
  , ('0da8c2b28b8377a5', 'es', 'b6c015d12e1b59bd78fb246985e37730e38521f8', 'Vict.')
  , ('be9560e3832c8bb9', 'es', '1b48a60b0d625b75c26ce2cf730ff892e74f4114', 'Gana sin disparar')
  , ('8c0133547ab53ad0', 'es', '05cb4b22604d22cab8e2fae50a1050c33fa3521a', 'Sabia más allá de tus años.')
  , ('c7c6e4fba9dcb3c6', 'es', '6f3c2cb5e1f2e4a068c8389405e3e496e4f9ef97', 'Volutas de humo gris se desprenden de tu cuerpo.')
  , ('28f008bfef758548', 'es', '504f4643d13463af8dc37482c5cbe0acc4a75d6b', 'Volutas de sombra viva coronan tu cabeza. ANIMADO.')
  , ('e1dbf69f1828cbc7', 'es', 'bca16e3079936dcb4198b1cfc3ffba6610a7e47d', 'Lo llevan quienes escalaron la montaña.')
  , ('695949eccf2a3eb4', 'es', 'c99d12a2a8f36120e482c0fc40e974443dba78bb', 'Pon tu nombre en <b>negrita</b>. Combinable con otros estilos de nombre.')
  , ('ada862d6c0f469e7', 'es', '609dfb565c93a98b2b30104355b3a4232da847f4', 'Pon tu nombre en <i>cursiva</i>. Combinable con otros estilos de nombre.')
  , ('37343c87c3b2e4f5', 'es', 'b8c7196ddeefdf59f5ef6da9406d00a866271c3a', 'Nombre XL')
  , ('dcc9b37fdb87b814', 'es', 'ee87adceb5e62cb4131c19198f5051250f0d91c2', 'Cursor amarillo')
  , ('5ef0b9cf34f0aff2', 'es', '89ffbc49c5cd513fb7f444af55b747d977cda309', 'Yin & Yang')
  , ('a8064a9ac9627e7d', 'es', 'bfcb6f0bdfeaee7d87fac66f8d55ddb559b17ec6', 'Siempre te presentas.')
  , ('64e8a47541007536', 'es', '2bbe77e5794acb118c3f9cadfd5a8b5130e9a46d', 'Tu nombre pasa de ámbar cálido a rosa profundo.')
  , ('bd97142ff2899914', 'es', '932d39ba6afffe50ecdb9d96f8e9953fc8738c51', 'Tu penalización por no presentarte: <color=#FFCC44>{0}%</color>')
  , ('9c9228360f345cff', 'es', 'f8acd4ea8b53c8e63f98ea885d48befcc946b1e1', 'Tus elecciones')
  , ('698827c82f5162bc', 'es', '07165fcd109bbf9198d1f39c2f4d6149df178a3c', 'Tus puestos:  <color=#FFE580>1.ºx{0}</color>  <color=#C8C8C8>2.ºx{1}</color>  <color=#D4894A>3.ºx{2}</color>  <color=#888>(jugados {3})</color>')
  , ('149bf365c330d13c', 'es', '8833ad12d379ff3fa61c32bb9e943d7b06b5856d', 'como DÚO (con {0}) vs {1}')
  , ('0aa6a16a1673de73', 'es', '1bd88366f34ba7f14fb904e5ed1646c4644328cc', 'como SOLO vs {0} + {1}')
  , ('0cd2498ace5eb5b1', 'es', 'd317f861f54f6c4a8fd4dac6ff0efcea37ec2e1d', 'sala 2v2 custom')
  , ('bd6d31d0b058348d', 'es', '16ef1d431149d2a08902873a443dbbe54c85cddb', 'dúo')
  , ('6c3530c8c280b3ff', 'es', '11ef3b2ae60a4251cd73fef09e480569d29ecdfd', 'ahora: <b>{0}</b>')
  , ('1e0ef297c1e3d8b3', 'es', 'f9c0c29d091d50a9086354e063e47954c59e1b90', 'un color a la vez')
  , ('8cad63c636cdcf6f', 'es', 'ff83a9a220be04b92113dda6c44401123dc40b01', 'una fuente a la vez')
  , ('3bd7fbbab2fca8f1', 'es', '35a7375e3bb813dfde5e763661731fac75a6e0d2', 'un brillo a la vez - solo jugadores con mod')
  , ('e165e5ae840a62fb', 'es', '7ab9c8362a5abfb2e9bfcbaa02d5a3f8fc771179', 'un tamaño a la vez')
  , ('8e4bd5a8e9eec6ae', 'es', '0570f3e02cc6e225a109dc75f565ed8681b8252e', 'una tipografía a la vez - solo jugadores con mod')
  , ('b8adf2986f373097', 'es', 'bea1572501beca2ebef3a391a800868da0c570a0', 'acumulable')
  , ('e6066223b0b305c1', 'es', '50d8b4a941c26b89482c94ab324b5a274f9ced66', 'desconocido')
  , ('c4abfe07405d45b5', 'es', '4902794a18b07e5f86e7f33d4029788b2034de4f', 'ruta desconocida')
  , ('eb897bb9be7c79b8', 'es', 'e1a6f0b6f73a57a8b3ee30419e28f6cb95143908', 'ilimitado')
  , ('dc6588862dd02f39', 'es', '6aefdf8cf3774a76db4f21466926eaa31e1bf15c', '{0} <b>ganó</b> {1}-{2}')
  , ('23f3e8961d9a6d6d', 'es', '5519c24b363f6799a1bfaab8e067c25e0eca51e3', '{0} elo')
  , ('f175d5d9643750aa', 'es', 'cceed712efad9af4f4ef2b04ce0b8d5a66f086ce', '{0} juegos    {1}W - {2}L    {3}')
  , ('563f328fb4d4aa1d', 'es', '60af1d144ac434a965bf13bb977aa7aadb4bb8d3', '{0} eventos de medio punto')
  , ('256d2b14212ba5d4', 'es', '1ab5b75b0bfcc6c62c111b526749c2b8fdbd47ed', '{0} objeto(s), {1} copia(s) en circulación.')
  , ('2aa987f867bde0fc', 'es', 'da5d5190f132c40421541404bfbc922fa7b4115e', '{0} partidas ({1}W / {2}L)  WR: {3}%')
  , ('c9cc67272a1c866f', 'es', 'ce9deb48ef00eef45a5b3b38a2161430725ea158', 'quedan {0} de {1}')
  , ('3f3e4849188126ca', 'es', '1b349c2c85da7aa6f6fce0e2315fe90c1db905ef', '{0} de {1} jugadores')
  , ('2ef8c7b3a201cae0', 'es', 'a24642bb9528015ac471a91a10e938a1cbe5d461', '{0} cartas iniciales')
  , ('2eb242866aaaf376', 'es', '65d4768dbb287c5c86628ac8189b2366ee6700ab', '{0} jugadores con rango')
  , ('8652c96055f60c8c', 'es', '2968d53cd798cf7fb980789d461ea11b3a0d2aa4', '{0}: <color=#888>(sin asignar)</color>')
  , ('b3e2957858fb3018', 'es', '22d79b7411b323a43df61650426791552bdec4ae', '{0}: <color=#FF9966>NO</color>')
  , ('83dff324198dd780', 'ru', '33de31eaa86df586fc5cdac587e01a4da1d8fcd6', '  (посл.: {0})')
  , ('5228b8e02c86210c', 'ru', '53b74b7f2271d94b654a77d49d0bb23fa6af9042', '  <color=#888>(стр. {0}/{1}, всего {2})</color>')
  , ('78f8e040217c152e', 'ru', 'fe8ecd2e7ce2de3f4e5cd9f5d0455d92809bdbc6', '  В комнате с {0}')
  , ('59e3487efe729e16', 'ru', '69dbcae41ae96b4d28fd39fbc75d2d0d810cd266', '  против {0}:  <color={1}>{2}W-{3}L за всё время</color>{4}')
  , ('ccd6c2ba67bfee1e', 'ru', 'c25067a12dfc7a94ec107c6073e215ab8f45ec06', '  против {0}:  Первая игра вместе!')
  , ('63f971a282654786', 'ru', 'b0247bb4bb0764888d3c797e0f15daaa92c2ca9e', '  {0}  <color=#888>{1} на их стороне</color>  <color=#666>{2}</color>')
  , ('777a4ed3a4e9d1b0', 'ru', 'e0aa04851ac53a1bd32f85ccfe859005fe4e0a5e', ' <color=#888888>(вышел)</color>')
  , ('2252a0cefefdafdd', 'ru', 'c91246a5320a509c2bb9418d366d1f8825a028a9', '(лог не прочитан: {0})')
  , ('97af61d8389c2364', 'ru', 'fbcf4b3dcfbb44db1dbf490faaf83040b2bdeee5', '(лога прошлой сессии ещё нет — мод записывает его при корректном закрытии ROUNDS, так что при самом первом запуске тут пусто)

Ожидаемый путь: {0}')
  , ('e32ff3a09330d729', 'ru', '4199a762764740366c8e076eb4282d07e375c215', '(места {0})')
  , ('c0b74f3dc3058639', 'ru', '0598c8fb1fcafc544b9570ef561d84c8e7941f27', '* <color=#C8C8C8>2-е</color> - {0}g / {1} XP / роль Runner Up')
  , ('41fd1756bebbcf9c', 'ru', 'd7c39a6a3788feb33bcaa658e81338bf0f548e22', '* <color=#D4894A>3-е</color> - {0}g / {1} XP / роль 3rd Place (проигравший финала LB)')
  , ('5deba6276fd8a551', 'ru', '905ab236d174b26450639245ec52f92ca75cc3a9', '* <color=#FFE580>1-е</color> - {0}g / {1} XP / роль Winner')
  , ('6c60e1d8262b75b2', 'ru', 'de0ac0c428d1d09d04ae156d8084da226a9774b6', '3-е место')
  , ('d0b5fd1cf1d6756a', 'ru', '8e0c8efc54fa35ec670bfcebb81f7b5fdd60edd2', '<b>Лобби 1v2</b>  <color=#888>({0} — закроется при 3)</color>')
  , ('29bc540f182069e6', 'ru', 'ef44278d615ad0dfbd3a35bea5d164c5c9ded7d9', '<b>Ранговый 2v2</b>  <color={0}>({1} в поиске)</color>')
  , ('49e1dea08aba7261', 'ru', '99ad986f0701d66b8842024bfda93a105359e48d', '<b><color=#FFD94D>КАК ЭТО РАБОТАЕТ (Асинх.)</color></b>
  1. Запишись в любой момент 7-дневного окна записи (Discord должен быть привязан)
  2. По закрытии записи строится сетка и активируются матчи первого раунда
  3. Договорись с соперником через <b>/dm-opponent</b> в Discord
  4. Оба включаете Ranked, заходите в любое приватное лобби ROUNDS и играете BO3
  5. <b>Мод записывает результат сам</b> - без ручных отчётов и кодов комнат
  6. Победитель идёт дальше по сетке; проигравший падает в LB (или выбывает)

<b><color=#FFD94D>УСЛОВИЯ АВТОЗАПИСИ</color></b>
  * У обоих игроков в игре должен быть включён <b>Ranked</b>
  * Подходит любое приватное лобби ROUNDS - турнир не навязывает комнату
  * Как только у тебя 2 победы в BO3, мод двигает сетку и уведомляет тебя

<b><color=#FFD94D>РАСПИСАНИЕ</color></b>
  * Фиксированного старта нет - свой темп, <b>7 дней на матч</b>
  * Весь турнир идёт до 6-9 недель в зависимости от скорости матчей
  * Пропустил дедлайн - техпоражение в матче (учитывается в % штрафа)

<b><color=#FFD94D>ФОРМАТ</color></b>
  * <b>Double-elim</b> BO3 - одно поражение, и ты в нижней сетке
  * Гранд-финал: чемпион WB против чемпиона LB (сброс сетки, если LB берёт первый BO3)
  * Все матчи идут в рейтинговый Elo

<b><color=#FFD94D>% ШТРАФА</color></b>
  * Растёт, когда ты записался, но получил техпоражение, пропустив 7-дневный дедлайн')
  , ('2a6188ce0acf8037', 'ru', '630d5fe7b6a1288b2d2def76fbc528dd95a739c4', '<b><color=#FFD94D>КАК ЭТО РАБОТАЕТ (Синхро)</color></b>
  1. Отметь все времена старта, которые тебе подходят, и запишись (Discord должен быть привязан)
  2. Запись закрывается, когда <b>8+ игроков сходятся на одном времени</b> - это решается <b>за 2 дня</b> до старта по умолчанию, так что у тебя всегда 24ч+ предупреждения; кто не может в выигравшее время, снимается без штрафа
  3. <b>Держи ROUNDS открытым к времени старта</b> (главное меню подходит - сидеть во вкладке не нужно)
  4. Мод <b>сам соединит тебя с соперником</b> - без очереди и приглашений
  5. Играй BO3, сетка двигается автоматически - <b>закладывай пару часов на всё</b>

<b><color=#FFD94D>МЕЖДУ МАТЧАМИ</color></b>
  * ~7 мин передышки перед каждым твоим матчем после 1-го раунда
  * Оба игрока жмут <b>Играть сейчас</b>, чтобы пропустить паузу и начать раньше
  * Явись в течение 10 мин после начала матча, иначе техпоражение
  * Сетка скрыта до старта (первого соперника не поскаутишь)

<b><color=#FFD94D>ФОРМАТ</color></b>
  * <b>Double-elim</b> BO3 (до 2 побед) - одно поражение, и ты в нижней сетке
  * Матчи идут параллельно: твой следующий матч назначается, как только известны его игроки
  * Топ-сиды получают пропуск раунда, если записалось меньше 16
  * Гранд-финал: чемпион WB против чемпиона LB (сброс сетки, если LB берёт первый BO3)
  * Все матчи идут в рейтинговый Elo

<b><color=#FFD94D>% ШТРАФА</color></b>
  * Растёт, когда ты записался, но не явился к матчу
  * Меньше штраф = приоритет, если записалось больше 16')
  , ('3fa2e1d1b7b13d65', 'ru', '1681c1ad66e8b53940d57f71ec05cd6f6cbd6f17', '<b><color=#FFD94D>ПРИЗЫ</color></b> <color=#888>(при {0} игроках)</color>')
  , ('185ea4043021ff08', 'ru', '24a4b3b2e962abfb33dbb275b5574999fa2a3c1e', '<b><color=#FFD94D>ПРИЗЫ</color></b> <color=#888>(при {0} игроках, сейчас)</color>')
  , ('4b40a37c0f75e082', 'ru', '5d0cfe13e0112ed053a0d334953c1a598ef0f059', '<b><color={0}>{1}</color></b>  <color=#888>(без рейтинга - загрузка...)</color>')
  , ('c014368fb258c367', 'ru', '964083dde3b9086daa465f67dd2f060fef1afe91', '<b><color={0}>{1}</color></b>  <color=#888>(без рейтинга - игр пока нет)</color>')
  , ('e7f929f2fc14ab9b', 'ru', '37e09b5ca64b2263c149efe2e584442a59ccf277', '<b><color={0}>{1}</color></b>  <color=#888>(без рейтинга - {2} игроков)</color>')
  , ('7d817ff529af1f06', 'ru', '58139b6f61ab48387be44eb29431ba6209e10f4e', '<b>Таблица FFA</b>  <color=#888>({0} в рейтинге)</color>')
  , ('45cc733ef5540b01', 'ru', 'a33b19409eb5e945af5ac6000a7f968edb0f0d95', '<b>Таблица FFA</b>  <color=#888>- рейтинговых FFA пока нет</color>')
  , ('951b9b16227f135f', 'ru', 'cd95b4632dc60bdec486a3611eed91c56d5736bb', '<b>Логи игры (хвост)</b> — прикрепляются к репорту, когда стоит галочка.')
  , ('68ffce8bbb14ce05', 'ru', '8f377602579db81b3a6824ecb1e4175b54dbc1fd', '<b>Как воспроизвести?</b> <color=#888>(необязательно)</color>')
  , ('cd0163493ecac4fa', 'ru', 'c0dafbb700e42748454366596685977879f28bbe', '<b>Недавние игры 1v2</b>  <color=#888>({0} серий)</color>')
  , ('5215fcf61178e3e3', 'ru', '54e706d52a91eaf6738072af7af1ea59473bdfc0', '<b>Недавние игры 1v2</b>  <color=#888>- пока нет</color>')
  , ('9d033a263ddf51d5', 'ru', '1f710e4b0e713951c4646e1f85cdf30df5e941b9', '<b>Недавние казуальные FFA</b>')
  , ('d0083333e06cfaf1', 'ru', 'ef69c20bdd62dbc159ca5c52064ba8b5eed1773e', '<b>Недавние казуальные FFA</b>  <color=#888>(всего {0})</color>')
  , ('3d37b7ba02553145', 'ru', 'aed453ecdecb7d986af81013f773383e4624f25b', '<b>Недавние казуальные FFA</b>  <color=#888>- пока нет</color>')
  , ('ef2ee75085947329', 'ru', '18c28fcab9c64bd35ce03e8e016602b6795ecc8f', '<b>Недавние ранговые FFA</b>  <color=#888>(всего {0})</color>')
  , ('687c1dcb181ecf45', 'ru', 'c655a4e371ec3c52666e977042a3cc98eb9de6dc', '<b>Недавние ранговые FFA</b>  <color=#888>- пока нет</color>')
  , ('e93c7974349c8d09', 'ru', '8500bc4d384b9f21e290610ab0c760e7ca028ba7', '<b>Что случилось?</b> <color=#FF9966>(обязательно)</color>')
  , ('5b4560f5fd3ca74d', 'ru', 'dbc49e21b64e298c965187ecea7dcf1bcdd62263', '<b>Вы</b>')
  , ('b7f586245cf37349', 'ru', '49c3d520a6cf011fc93ce62b10afbe9e6bdfaec3', '<b>Против вас:</b> <color={0}>{1}W - {2}L ({3} игр)</color>')
  , ('4c68914b7aabfcfa', 'ru', 'bf002f47ea0d0549603ae705e59cb5f1a515bf3e', '<b>{0} Патчи производительности</b>  {1}')
  , ('510bbb2d5c28e2ed', 'ru', '23e6796a6dd6767a12be4b513543ebf8e5e4abb7', '<color=#00FF00><b>ПОБЕДА</b></color> {0}-{1}')
  , ('e08bba79fc405bb1', 'ru', '0be65425d5df8a3381741d8b1359dde94d3a039a', '<color=#00FF00>Discord привязан</color> ({0})')
  , ('3e892a1a275b71e0', 'ru', '0052bf33f0e0a2fca12bc8925dbe2a6505d7419b', '<color=#00FF00>Discord привязан</color> <color=#888>(клик — показать)</color>')
  , ('ea83337993a45755', 'ru', '585d7397eb695e72f42e0bacc337f5de1767d40a', '<color=#00FF00>ПОБЕДА</color>')
  , ('e494424cf053f992', 'ru', '4b8ca35da1156502e8dd33e7421caeb030b28894', '<color=#00FFFF>{0}</color>  - введи <color=#FFFFFF>!link {1}</color> в Discord')
  , ('ebb00fa13d937164', 'ru', '6d963ba9ef802936517c691221c2197fe179c635', '<color=#664444>-> {0} поставил {1}g на {2} - проигрыш</color>')
  , ('493df93f52bd5e55', 'ru', '185f137dbfc6210724da22e7a90deda846e8ce92', '<color=#666>(клик — копировать)</color>')
  , ('80a36c40325aac15', 'ru', '593d09650a9947c940874fcff9cb819b859aef53', '<color=#666><i>Скрыться отсюда: Настройки -> Казаться оффлайн.</i></color>')
  , ('5c528222367454fd', 'ru', '568602877de41bc9414cac985c77b8c26ac84eaa', '<color=#666>без карт</color>')
  , ('42814ecc2b658aff', 'ru', 'c914a0dd6b7a82aa21bbc158bcd04239601f6345', '<color=#666>—</color>  <b>Игра {0}</b>: {1} {2}-{3}')
  , ('1a9fd2fffa505395', 'ru', 'b44b4f1c38f706c3657474e5325330c3f8c42265', '<color=#667788>Карты:</color>')
  , ('a6a35197bee61edc', 'ru', '7a9481236d37894202154793757d34325a34387c', '<color=#667788>карт нет</color>')
  , ('c7e1faeda4aff802', 'ru', 'd0fde2869f5db199bb2e6fc56d6ec641b7e9ff32', '<color=#667788>серия:</color>')
  , ('b3c7d24dc7d7d5f0', 'ru', '5e3ff648c349f07d096defc5f364a9bf02be7bd1', '<color=#6677AA>Вы:</color>')
  , ('accb99d11995227c', 'ru', 'f79172f515472bfbdcf012289d572cba03244088', '<color=#66CCFF>Скачивание...</color>')
  , ('590709f4939b85b6', 'ru', '07bd257b33b6b7dae2457c8b3cfe4b5949484973', '<color=#66CCFF>Ищем {0}...</color>  <b>{1}/4</b>')
  , ('225de4a62c9c9a2c', 'ru', '37dd9921db9da397984723b18a5138c9c8013b18', '<color=#66CCFF>в поиске</color>')
  , ('d42e053f6b13ff64', 'ru', 'bbcb83eae9983000e8f0f516b4318bb399bf67be', '<color=#66DD66>ОДОБРЕНО</color>')
  , ('fb1a4b3a5f4e1d5d', 'ru', 'dc2a54c6ab19d126c840dfe2b19216c508821c64', '<color=#66DD66>ОДОБРЕНО</color> <color=#888>(рев. {0} ждёт обновления мода)</color>')
  , ('b84788a98e84201d', 'ru', 'a7e2659bd9f21d6579b628236a12968cdc7e4d87', '<color=#66DD66>В матче FFA.</color>')
  , ('04ea724f3226d3a6', 'ru', 'f232d32135d7a1a9257b868b63a89efd1ef8d344', '<color=#66DD66>В матче 1v2.</color>')
  , ('0d7cc210312198ae', 'ru', '34fa10fede90cb20a1ddf3da58a43404436557eb', '<color=#66DD66>Матч найден! Входим…</color>  <color=#FFB347>{0}</color> <color=#888>против</color> <color=#88AAFF>{1}</color>')
  , ('b3eb79e601bb099b', 'ru', '1b796b9e660114c40780b5f70ed1977413c71cbd', '<color=#66FF88>Сейчас онлайн</color>')
  , ('0a7da31bb71a460a', 'ru', '86af06d8ad49429bceb0be6f1616d05dda47ec9f', '<color=#777>(ставка сделана)</color>')
  , ('3961b1463268849f', 'ru', '730b09723eeadb523d9b0aa6dacbb50480fb8ec0', '<color=#777>(наведи — график счёта)</color>')
  , ('6b912c60e510d768', 'ru', '13c8a3c88fb5be85116ae4e6a94a3dc35feeb24e', '<color=#777>(ваше лобби)</color>')
  , ('1c5acd21065ca4ea', 'ru', '3c8ec61681d4250b1d3d48235800cfb3557f2f9b', '<color=#7788AA>-> {0} поставил {1}g на {2} - ожидание</color>')
  , ('8311a697b4bf1aac', 'ru', '4b40a0907e3234e0cc2fe724d87f31cc5cbe9cdc', '<color=#7FD4FF>История 1v2</color>')
  , ('e4e808986976f25b', 'ru', '5223c763248dbdfa305993651bdeeca05fe2509e', '<color=#7FD4FF>1v2:</color> {0}W/{1}L')
  , ('825271b6ccbea3da', 'ru', '96ee7b1438ffe3f13aa82d7096953dfa1ad77687', '<color=#7FE8C3>Каждая заявка после 8-й растит банк - 16 игроков удваивают его! (сейчас: {0})</color>')
  , ('db7dd81ac45d3a49', 'ru', '1933cbafaed52c8b035f1a5e2855631e4afbee83', '<color=#7FE8C3>Максимальный банк - 16 игроков!</color>')
  , ('c7cd96f7c337c372', 'ru', '89e542520d4d04153f795491a4d854749727701f', '<color=#888>(надевается в редакторе персонажа)</color>')
  , ('a0a84bb37b74480c', 'ru', '4623a6a3410fc70b8cc383dcf0a6cb4c4f933517', '<color=#888>(идёт)</color>')
  , ('33495944a2734539', 'ru', '4cd18a046f43841d4fe50b03aa465f0e26bc5d92', '<color=#888>(действует последняя одобренная позиция)</color>')
  , ('8424897272503312', 'ru', '227fdfe98dd6eb33929a1358e01817cbd13f6e83', '<color=#888>(доп. карта соло)</color>')
  , ('ac53cb1d4b497deb', 'ru', 'd64a6ab3ed242d778aac287190982a900e112064', '<color=#888><i>Забирай на вкладке Магазин.</i></color>')
  , ('ac2f3c9d04c1d307', 'ru', '29b2cfb1815a45fe5f93cce227df3453f78ad1dd', '<color=#888><i>Скрыто</i></color>')
  , ('85126096ca57c79a', 'ru', '46a5af2585c769ed0e95767115d47c4374011355', '<color=#888><i>Загрузка истории матчей...</i></color>')
  , ('f88cc3f973d9f363', 'ru', '7556b0ea5d14482def62171cdb787dab6eb19915', '<color=#888><i>Загрузка...</i></color>')
  , ('5fdeeb0b9c1ec66a', 'ru', '6b1ea4c0eeeb654cbd9aa79535b60b966080d110', '<color=#888><i>Сейчас никого не видно.</i></color>')
  , ('2d17a111ecfa7be7', 'ru', '2fe8b21054cd17ebd00a292566d04d71f3148cde', '<color=#888><i>Обновление {0} - забирай на вкладке Магазин.</i></color>')
  , ('02481d4bc4f0e5ee', 'ru', '69a9c6e275a41f86330f6c8e4513a47b83f6625e', '<color=#888><i>Обновления {0} и {1} - забирай на вкладке Магазин.</i></color>')
  , ('bce10b6d42caa61d', 'ru', 'c34d4b466d6b20a538710fabf9f43f8d410d46fb', '<color=#888>Discord:</color>')
  , ('885802821e8af4f4', 'ru', '875ba602929e490fa025f4fab86ce7d1bcaa9674', '<color=#888>Выходим из очереди…</color>')
  , ('29956eb093b192eb', 'ru', 'fcff73f47ee10219a3876754afb842f262ea44cb', '<color=#888>Выходим...</color>')
  , ('a11c16b210120f55', 'ru', '2552c92999af87111790f7a90d41be061c01da98', '<color=#888>Загрузка…</color>')
  , ('94d8eeb7835cacb2', 'ru', '988e5666d9c440209aa8a616f309be4c3d8d7c7b', '<color=#888>Мод: <i>не найден</i></color>')
  , ('fae2abbd1d51f67d', 'ru', 'c40c6b2fcce0e40b069812932bfe25f200cac3ab', '<color=#888>Мод:</color>')
  , ('08e57eb5ea26362e', 'ru', '17ac025c7e380c8abcd7f65f12ff482a44d57839', '<color=#888>На вас пока не записано предметов - арт привяжут к аккаунту, когда он выйдет в обновлении мода.</color>')
  , ('b9020ddf292a653a', 'ru', '33ec8a32092c71c0303fb402975eaea93a946cbe', '<color=#888>Жми <b>Поиск: рандом</b> для подбора или <b>Найти кастом-лобби</b>, чтобы выбрать команды.</color>')
  , ('fd4d752a09b135c7', 'ru', 'c33489a0e5e55f1129255554ed18ba2ac2a49972', '<color=#888>Steam ID:</color>')
  , ('f46b07ee62c695cb', 'ru', 'a028d3b8e8c2a227aaf8885796b90d57ddc6ee4a', '<color=#888>любая роль</color>')
  , ('02c6d926d2a73a47', 'ru', '06d342169002a46b2dcd8b255afee37003292dad', '<color=#888>продано {0}, подарено {1}</color>')
  , ('e6e6c58af19307ec', 'ru', 'bac173ecd4e58b18541d82f573f1faaa20dff16c', '<color=#888>{0}% штраф</color>')
  , ('81d1594bd1091bc2', 'ru', '07a8c3315325a7a113f2f1fc08be063c770e592e', '<color=#888>{0}</color>  <b>{1}</b> купил <color=#C8A2FF>{2}</color> за <color=#FFD94D>{3}g</color>  <color=#7FE8C3>+{4}g вам</color>')
  , ('357effe73805facd', 'ru', '68d71224c58674c112890a7fb61d7191d171f9bc', '<color=#888>{0}</color>  <b>{1}</b> получил <color=#C8A2FF>{2}</color>  <color=#888>(подарок)</color>')
  , ('86369abfe6bb0dd4', 'ru', '8b5f2ed9c71b4f4d439f18f5e87d00c642ab65a5', '<color=#8899AA>1 - 2000 золота</color>')
  , ('c8e19ea38805cd06', 'ru', '9a62a068439228473cef75e0adeea9dea9ffe2ee', '<color=#8899AA>Сколько будешь искать? (игрокам показывается как срок действия)</color>')
  , ('603409ff6c82dce6', 'ru', '40e65024e861fed568d872aea26bc7171255c387', '<color=#8899AA>Пингует роль Ranked Looking For Player (не чаще 1 в час). Сообщение (необязательно):</color>')
  , ('7d8e43ec3c542605', 'ru', '2a30c4721b799ef8018b7e5b23cfe8062c17039c', '<color=#8899AA>Поиск</color>')
  , ('a55363b0ad23e5b7', 'ru', '11d01c5ab646d71262d1c38154e66cc97b7f8c6f', '<color=#88AAFF><b>ДУО</b></color>')
  , ('5c7f514fa12c66ce', 'ru', '239e7d1a3132fda68ccef926a05bad2726b26e2f', '<color=#88AAFF>дуо победило</color>')
  , ('71b9427f56eb8491', 'ru', '94f1bd1317408d4db6879578e89e2baff37efcd9', '<color=#88AAFF>хочет дуо</color>')
  , ('a1244673752f5b09', 'ru', '63e3488e68c75920133d1af00d41414a0297f6b5', '<color=#88CC88>-> {0} поставил {1}g на {2} -> <b>+{3}g</b></color>')
  , ('c7db091c6a0581e2', 'ru', '6535f8599ca23255d61a3b1d7d6ffe9e652dccb1', '<color=#88FF88>Надето.</color>')
  , ('296bc9618defb504', 'ru', '9c6bbae583fc1361282e70616ace14758f6e8c73', '<color=#88FF88>Куплено!</color>')
  , ('bb1576b33cca66ca', 'ru', '0f8972798a7dc8831f9c0d900bead94bda16f1e6', '<color=#88FF88>Готов! Ждём остальных троих...</color>')
  , ('53c81b79be7734cc', 'ru', '72eb49bc0c8d4b39c1a19186f6230c1c6173dd38', '<color=#88FF88>Отправлено! Спасибо. Номер <b>#{0}</b>.</color>')
  , ('9808e56f61cea810', 'ru', '3d51ed996dee97375f2a58108ab35dd1d4c07482', '<color=#88FF88>Отправлено! Спасибо.</color>')
  , ('8a48a19c9b583f44', 'ru', '9c9a18c65d8497f6d65c240a21e317c325b88e1c', '<color=#88FF88>собрано</color>')
  , ('3072afe4d390a26d', 'ru', '7458c742a0778b5861439c00af14c2518f2cbbcb', '<color=#88FF88>{0}/{1} активно</color>')
  , ('a13ace4753916354', 'ru', '794de690ee3249fb9aff60d3748de5b98a0f7388', '<color=#8FA3B8>{0} fps</color>')
  , ('57da6b22ccc01814', 'ru', '3be3caf7dc4aae34dc52ce4e084379b3f38f3e0c', '<color=#99AAEE>Достижения:</color>')
  , ('ba0b8dc8f6cd3b7d', 'ru', '99179cc9e74d882fb29effe8c3d16396cba0d1b2', '<color=#99AAEE>История рейтинга:</color> <color=#888><i>рейтинговых серий пока нет</i></color>')
  , ('713c1176bf2b2b9e', 'ru', '12fb0ff3ca8074a3192cd4aaaf78ba614b8a4d6b', '<color=#99AAEE>История рейтинга</color>  <color=#888>(недавние серии)</color>')
  , ('afda56e261c5dbc8', 'ru', 'f9f7dc430ffd04be72b8680756d5da9a0e4a961b', '<color=#99AAEE>Топ карт:</color>')
  , ('a446fd1a40e8f265', 'ru', '9b98f2ba99a70e922939b50ed9c6c6ddf333e077', '<color=#99B3E6>Блок {0}%</color>')
  , ('a6d07574629f099c', 'ru', '2e7ba4b2a8d879503b315cf86da06a7eef63cde3', '<color=#99B3E6>Вы: попад. {0}%</color>')
  , ('ac200ad7911d1b33', 'ru', 'fea4a3b41a3af17529f68a323d94e259bf710236', '<color=#99B3E6>{0} кл/с</color>')
  , ('ca42603f393a8386', 'ru', '55d0abe95e269b9549242e572909ab1b7406f21c', '<color=#99CCFF>Блок:</color> {0}% <color=#888>({1}/{2})</color>')
  , ('d8623cf1d650881c', 'ru', '60e0678c7e19e5c414e5c7ff1a7879c3427fdbb9', '<color=#99CCFF>Блок</color> {0}%')
  , ('0fc211da8b7173b4', 'ru', '72f0ed2b9b3989238388e7edddaf252c81a7cb9f', '<color=#9AD0FF>Ваши заявки:</color>')
  , ('b5699b2c6706d70a', 'ru', '9e8ba6414d716552ea534ba3d65e2773b984fe5e', '<color=#AA9955>-> {0} поставил {1}g на {2} - возврат</color>')
  , ('97eed477558a8ce8', 'ru', 'cdedff3bd78198557df9dfac25d6db4d5e4f0d8c', '<color=#AAAAAA>Репорты идут команде мода. Пиши конкретно — что случилось, когда и что ты делал.</color>')
  , ('7ca5ac14f4529d8a', 'ru', '215a414b3ec2e0a6014946b0e501d09b88707d21', '<color=#AABBEE>{0}</color>  Победитель: <color=#FFE580>{1}</color>  <color=#888>({2} оч.)</color>')
  , ('b0435f9624a0ff08', 'ru', '0f187adf4f36222c3e229d3a7cfc62c483482453', '<color=#CCCCCC>Вы в этой комнате Photon уже <b>{0}с</b>, а матч не начался. Ванильный подбор иногда виснет тут, если у одного из игроков окно ROUNDS не в фокусе. Кликни в окно ROUNDS и снова нажми пробел, либо используй аварийный выход ниже.</color>')
  , ('89a698611907f9ec', 'ru', '2fa2251cb22a70a509d217abe8ec11e024e0aaae', '<color=#D8A7FF>История FFA</color>')
  , ('683fba7afbb36532', 'ru', 'd9e3fd10875116ad5e4e38dca5bf31fbc487fdf5', '<color=#D8A7FF>FFA:</color> {0}W-{1}L')
  , ('4e9df1482c91e705', 'ru', '77768f2cddef5881738c018e0d4d539bbfb2df96', '<color=#DDDDDD>{0}</color> <color=#777>-</color> {1} игроков <color=#777>-</color> <color=#8FA3B8>{2}</color> <color=#777>-</color> {3}')
  , ('1e9c55fbc95244de', 'ru', 'dbe957ca740a4bf3b02108f054f8b42164ac836e', '<color=#E69988>Блок {0}%</color>')
  , ('c60975242010a2c8', 'ru', '4fbccb024c897c74e187b3121bf5a8fae54a0244', '<color=#E69988>Соп.: попад. {0}%</color>')
  , ('6dc74c450a0a3571', 'ru', 'e45c22cefdaf554364a1b1064fa6ee80d5760c8d', '<color=#E69988>{0} кл/с</color>')
  , ('f3111e697b8a3499', 'ru', '503a6feddafea172e50dcab91e9b6ca9fd5c5415', '<color=#FF6666>(НЕТ В ПРОДАЖЕ - художник ещё не открыл продажи)</color>')
  , ('5960a9ad7ea21934', 'ru', '3459beeb88871e1e04b203c8a2bae6ad0c375949', '<color=#FF6666>(РАСПРОДАНО)</color>')
  , ('0243596e5d193a51', 'ru', '18aff0f77f00d58e0135fbbe73602eea442793d2', '<color=#FF6666>+{0} заменено</color> <color=#556270>(наведи)</color>')
  , ('0caa0cb269d0e9b4', 'ru', '402a9cda67e01dc4345b39756827e04ea577666a', '<color=#FF6666><b>ПОРАЖЕНИЕ</b></color> {0}-{1}')
  , ('6f22a3d809f5159c', 'ru', '77f34486d741bddbd1feecfab4257ae67faa108b', '<color=#FF6666>ОТКЛОНЕНО</color>')
  , ('da749f60b9684f21', 'ru', 'd7e0867b602018ada5fd37c4c1a1842af50c54b1', '<color=#FF6666>Удаление не удалось: {0}</color>')
  , ('59811c83538f6ef1', 'ru', '163d90dba8fe50450a04fb5fdad8c164068508db', '<color=#FF6666>Ошибка: {0}</color>')
  , ('3bb6abceb257a687', 'ru', 'da927b7271e6f8d59cbacce1b80066741b590663', '<color=#FF6666>ПОРАЖЕНИЕ</color>')
  , ('4f840542dec022c0', 'ru', '8aa97ef1388ab04f260985fe6a7f5c5f08b4a5a4', '<color=#FF6666>НЕ ОТКРЫТО - укажи запас, чтобы начать продажи!</color>')
  , ('7f75b6449785f3eb', 'ru', '6aa9d58290a51803f53daabf11161a4a059e4bd0', '<color=#FF8888>Ошибка: {0}</color>')
  , ('03bc4458323fd933', 'ru', '5382a6697adcab5246f2e9a8c1ef6290ebaa2c09', '<color=#FF8888>Покупка не удалась: {0}</color>')
  , ('b1eef294c20d4576', 'ru', 'bb8114dd2fbea5b0ee5612f9aae23305f631796a', '<color=#FF9966>МАСТЕР ВЫКЛ</color>')
  , ('79d12f448ea4ecb8', 'ru', 'f2c531693552d14d45c172e385c65845c14edac4', '<color=#FF9966>СМЕНА ПОЗИЦИИ ОТКЛОНЕНА</color>')
  , ('2380439a94a853ee', 'ru', 'c71e0391acbc34eefbfee6148971ec18fac0b669', '<color=#FF9988>Попадания:</color> {0}% <color=#888>({1}/{2})</color>')
  , ('8b00982d542b583f', 'ru', 'f48e8d83176749e28e622b50540c3ae0f29b907c', '<color=#FF9988>Попадания</color> {0}%')
  , ('f469e16744d7e631', 'ru', '025b122607398d54c7dac36a0d9b0fdb10f1ab8e', '<color=#FF9BE0>скоро!</color>')
  , ('e2d283f46c6565a8', 'ru', 'e80eed1854086d8b9db4aefdb9f0edcdfe901eb8', '<color=#FFB347>Лобби 1v2 в ожидании</color> — если ничего не происходит, жми «Выйти», чтобы распустить его.')
  , ('fdb683f06819a160', 'ru', 'c0db3cd062a38f3cacf680a2109f3dd736a64c13', '<color=#FFB347>История 2v2</color>')
  , ('a77c56b241124324', 'ru', '7b102ce6e585783508febe4bddb64faf39b56156', '<color=#FFB347>2v2:</color> {0}W/{1}L')
  , ('d4c5f1e400063fb8', 'ru', 'e6712306e7d7cc9c2eafd0893c231cff06249886', '<color=#FFB347><b>СОЛО</b></color>')
  , ('f0c37983395b1b27', 'ru', '1fe1aeab7143e93fea9d5b783b4e71539de01982', '<color=#FFB347>Серия на паузе — те же 4 могут встать в очередь и продолжить</color>  <color=#FF6688>{0}:{1}</color>  <color=#888>(счёт {2}-{3})</color>')
  , ('99a1c6367212642d', 'ru', '50fc7f597d225aa9330d5d5c4c309e5a30070477', '<color=#FFB347>соло победил</color>')
  , ('30510d105badfe4d', 'ru', '58b20b963fdc084822180221b0b2e2e33ff98c14', '<color=#FFB347>хочет соло</color>')
  , ('c4c4f162ef3a08eb', 'ru', 'a3fd02a92f217c87cd4ec996e33fe07c4b77ebca', '<color=#FFCC44>Поиск…</color> {0} в лобби <color=#888>(закроется при 3)</color>')
  , ('ec409b24b6baa83d', 'ru', '1a7f980a682a95d6db7309ad484f1c7ff80776a2', '<color=#FFD080>Экран «матч найден», похоже, завис</color>')
  , ('330b2a3cb2dd7af7', 'ru', 'c6ace38f182cbc9fec7803e444562aadce3d2c54', '<color=#FFD94D>(осталось {0} из {1})</color>')
  , ('11c7534fb8b7839c', 'ru', '22e12b0d3921df432cf0884ac46c4dce85a50d83', '<color=#FFD94D>ОДОБРЕНО - ждёт обновления мода</color>')
  , ('3fb6e8f61142d09f', 'ru', 'b9513bd50f6f2b2febd1b0b20d5f97faec07384b', '<color=#FFD94D>Своя ставка</color> на <color=#FFFFFF>{0}</color>')
  , ('0578f75137c0ac92', 'ru', 'd413a2bca5b58733396502254c2879888129a70b', '<color=#FFD94D>Матч найден! Нажми <b>Готов</b>.</color>')
  , ('fa6435193f8ec7ab', 'ru', '5201388e750ee115b4d891876b605efd08ef984e', '<color=#FFD94D>ПОЗИЦИЯ НА ПРОВЕРКЕ</color> <color=#888>(действует последняя одобренная)</color>')
  , ('c0be4316b3888ca4', 'ru', '2466fa8171f0d173bff6eb5ad9409cf0d6e423cd', '<color=#FFD94D>Рейтинг (серии): {0}W / {1}L</color>')
  , ('811f0b6757adca50', 'ru', '0112ccb6625408665001abf2b2b43ef9105e6e86', '<color=#FFD94D>Ranked Looking For Player</color> - пинг в Discord')
  , ('bf327ab5b8dbdcc1', 'ru', '0278a637c0b4224f4b2e502196bbf1aeac42848f', '<color=#FFD94D>Рейтинговые серии против вас</color>')
  , ('bcdff3edc272aa6b', 'ru', 'c41e0c77ac7efea07d68b205c2ecda2ffefff35e', '<color=#FFD94D>Рейтинг:</color> {0}W/{1}L')
  , ('85ecd41da4fb57e5', 'ru', 'd93c51495c04409d37e36b4dce1930a45ce9de61', '<color=#FFD94D>Турниры:</color>')
  , ('70fd04265821e7cd', 'ru', '447bf00a8adf3e15948428f8d350b4499a403d82', '<color=#FFD94D>заработано {0}g</color>')
  , ('dd4ea253253e8050', 'ru', '4aa5a0655e06b7f207582228c71b66d5028d5cb9', '<color=#FFD94D>идёт</color>')
  , ('0eef1f90d4357dc2', 'ru', '4a8962e2f2c84e3dce462d200654ced2b3d2d81d', '<color=#FFD94D>ждёт первой проверки</color>')
  , ('d8ede9573dbac9c7', 'ru', '7e01cae4dee9862c4d799b06bd66d619c0c0bf92', '<color=#FFE580>1stx{0}</color>  <color=#C8C8C8>2ndx{1}</color>  <color=#D4894A>3rdx{2}</color>  <color=#888>(сыграно {3})</color>')
  , ('5e6611223ccd2e52', 'ru', '38a56a2898844a92391b086b48afb2f86e9b282d', '<color=#FFE580>Сообщить о баге</color>')
  , ('725a66f0f66e8076', 'ru', '2aa5db947eb5e12f3d13857640ae1a52c1cee360', '<color={0}>Синий</color>')
  , ('48fd57c668c63dc7', 'ru', '68e41b4c2415fc16a601f9284cc62d1a0d1e1253', '<color={0}>Уходы: {1}/{2} ({3}%)</color>')
  , ('2f4cf0864647f848', 'ru', '9d44c73676aa56f6df4f33a819ebcc1b81cd2034', '<color={0}>Оранжевый</color>')
  , ('57f539baa20955f8', 'ru', '28329a6c2291ab34539160eafed7e0a58654883f', 'Дерзкий красный курсор.')
  , ('7420d8cc3e98ff5e', 'ru', 'f26aed94347cea2e644f80d3c4339839bf4741c5', 'Плетёный венец из терний с каплями крови на шипах.')
  , ('28d4ff2dae7455f9', 'ru', '23e39b1ad591fe7bb634d0bb71deb0af7c7f6c47', 'Ярко-оранжевый курсор.')
  , ('936c8c700ad2e14e', 'ru', '09760c239e5f1eaaaed919af1b3c0b4b59cde787', 'Яркий солнечный жёлтый.')
  , ('fc23457a57683e0e', 'ru', 'fd205b824b53ed05147b7286bfcdbef4e9d8c77a', 'Пылающий огненный венец. АНИМИРОВАН.')
  , ('71e3ee43149aa274', 'ru', 'd1bf71529da76b7d1a3d412a4db22ec2f634c046', 'Чистая белая линия. Классика.')
  , ('f68275e9faed6821', 'ru', 'e5f0c878ca68b6046f356f8b4e10dff4be9ab299', 'Чистый белый курсор.')
  , ('f5fa897d8e716419', 'ru', '72115355dca2abe0a4c5925cae462041c92fb3f3', 'Прохладный голубой курсор.')
  , ('a70f99966e0958b8', 'ru', '3d27acca20b71363bd39579002d1e2d47ab735bd', 'Трещащее кольцо живых молний. АНИМИРОВАНО.')
  , ('878cbf198b4c88e0', 'ru', 'ad047b0b34bba2c06aa7eaf784f0aa9c665c11bc', 'Глубокий синий курсор.')
  , ('054aa178a79fbbd0', 'ru', '8ccaaa302ea73bdb9bead1a6ec141229cea2d9dc', 'Глубокий индиго — между фиолетовым и циановым.')
  , ('b0b49ff92e08c74a', 'ru', '70b6c54dc1c13ff24f68f5b1e66b0170e9871bd4', 'Глубокий винный красный.')
  , ('2aad25bde6099301', 'ru', 'c1855544914c1abd869dc681d7a531ee05833e2c', 'Глубокий лесной зелёный.')
  , ('809359b5ebebe8d5', 'ru', '067b43f4b1519da09b0ac300e59a647f12ae7d65', 'Глубокий тёмный тон кожи.')
  , ('95f4cbc38f450bc9', 'ru', '841134a9aa1e8b90a49cb4c5b535ebb37e812e5a', 'Глубокий землистый жёлтый.')
  , ('7be9b5f7a848839b', 'ru', 'ef5205084dc052e1551b3a5b29613d80ee2d61be', 'Праздничная корона из мерцающих огоньков с пульсирующей золотой звездой.')
  , ('3739b2d530f6debd', 'ru', '04f6ac1ae02e6475938fb263bc4b7960aaa14465', 'Огненно-яркий красный.')
  , ('abe3b20d82427246', 'ru', 'e0b04f7776991125df7976fc25df6c378d7ee39d', 'Ядрёно-розовый курсор.')
  , ('b75fe59845fa7ecd', 'ru', '4a82ef21d0b89f6ba37a2b6c2fe3be74c8e23d34', 'Светлый тёплый тон кожи.')
  , ('583edabb1e09ee16', 'ru', '9f3a21630b49c6794c32656c33e432d3bf84e405', 'Приглушённый землистый оливковый.')
  , ('8a633c693695b715', 'ru', '5393acd21dc5762f827bd626eb1baa00e2a5f856', 'Лучезарный золотой всполох. Слепяще праведный.')
  , ('0f54805e99c76854', 'ru', 'a60ac5e701992bb53799c6435d8fa9cfeebbbcd0', 'Драный чёрный плащ с кроваво-красной подкладкой.')
  , ('e763ddfa52f56c01', 'ru', 'f9440b94808ba8103d9205ae89bd4358d0263fec', 'Насыщенное блестящее золото.')
  , ('97048d0dbba0b0ad', 'ru', '6b92c53eadd095e5577c7c13641831ea4e80d518', 'Насыщенный тёплый коричневый тон кожи.')
  , ('7f1e2dff680a21ea', 'ru', '26435e21d715685d5614c144df3ac5faaf6a77e5', 'Королевский фиолетовый курсор.')
  , ('76de6671a0e43d50', 'ru', '12d7c24417f733987cc887cc155326577389eee7', 'Мерцающая радуга частиц кружит вокруг тебя.')
  , ('185819c37faec22c', 'ru', '5d67c42eb8f5c9f4a3e92e8852f30b18b536c4c9', 'Строгий чёрный курсор.')
  , ('e3e5ec5ee886c897', 'ru', '1c8cdb1aadf7440df733f47304d419a4e7dc9ab2', 'Маленький серый кот, списанный с моего настоящего кота')
  , ('b842e9bcebcddf77', 'ru', 'bb1a91bcbeb57bb030beb06e6801c3123650ebc8', 'Мягкий янтарь — не путать с Золотым.')
  , ('7a9dce7f07ce4812', 'ru', 'd6682c54bc14e1ceeaab8f5c5f4d028edeb46ae9', 'Мягкая зелёная аура — сразу видно, что ты знаешь, что делаешь.')
  , ('3a765650a0fabfe1', 'ru', '084e935f9f75ddb12ece11b4db28468ba8e41034', 'Средний тон кожи с лёгким загаром.')
  , ('72f872abc86378a5', 'ru', '0e3adaa92340b7253fd391d5801e47286f66c549', 'Солнечно-жёлтый курсор.')
  , ('9c7b9e8923006966', 'ru', '2b5232add8ebb0b0b10d3340988527aba0746bcd', 'Сочный зелёный — между золотым и циановым.')
  , ('82a50967a8775147', 'ru', 'b6ccb321cd37c9a941a874741f8a5b53b4e22012', 'Сочный зелёный курсор.')
  , ('b55e98320a2c5883', 'ru', 'c0d79153a0f91fd7a0675abc1920dbfb911a8244', 'Тёплый коралловый розовый — в тон новому телу Коралл.')
  , ('84dea13d4f8749b7', 'ru', '4d33160cf65e8ee1374dbcda15cd04d741ffbaf8', 'Тёплый коралловый розовый с нотками оранжевого.')
  , ('705f3184942e5c20', 'ru', '093f93f6bc96df2c125019d556d7ef7a8e6b54e2', 'Задорный жёлто-зелёный.')
  , ('bc5daf52ecfcb394', 'ru', 'baf48506da4f8fcb158b020e9780f52833d663a4', 'КАПС')
  , ('34323f3c43b0f286', 'ru', '030d9312f32b78411ae6fd45521eafa5e3f16e4e', 'Бездна')
  , ('f1ad6bb2e30613b4', 'ru', 'a733b809d2f1233496ab516eed0f3ef75cf3791a', 'Активный')
  , ('3a70a1caae7433a3', 'ru', '5bcd1bc127edaf471cf8fc9daae11e05d0ea4bac', 'Подчёркивает твоё имя. Совместимо с другими стилями имени.')
  , ('fb141f420287e2e0', 'ru', '7f73305879a039b508248f80ce6511bbd64ef4b4', 'Добавляет разрядку между буквами.')
  , ('37501be191dd7d66', 'ru', 'd738ebfc6a7ca0bfb0966d34a7228b7448258df0', 'Состаренная бронза с тёплым отблеском.')
  , ('b89ffcf2f3023062', 'ru', 'cc6b2a579218473a35deacda2f0d5d288cf56c9d', 'Выдержанное вино — глубокий красный с коричневым подтоном.')
  , ('9ad25dd88adfebfa', 'ru', 'cee5ec293ece08f8b8d87a2b278c5a6bcd35fe37', 'Антенны пришельца')
  , ('2c0bcac005222b8a', 'ru', '0cffeabac63123322aba0bfa89e7867134d572bf', 'Все (вместе)')
  , ('f1144eb024aa03eb', 'ru', '940bbeb152752a33c9934bdce09b0298902a4d0e', 'Все пики (старые сверху) - красным = заменены:')
  , ('20d99221097e1fef', 'ru', '27a01d4772038a3f83552908e0470604e773f8af', 'Янтарь')
  , ('e74a5c961fcffa93', 'ru', '55879cd931aa5e3de8d5fdf3e442cf30a8cc34c8', 'Янтарное имя')
  , ('dcbcb0e4299e1c29', 'ru', '1ef532cce6fea64ba94eed1237cc785bcbd74ad0', 'Аметист')
  , ('2b07bbabfb8a43f6', 'ru', '407c60401b79318f2877683ed6df36f0bda6cfee', 'Патроны')
  , ('394f228c337224fb', 'ru', '4c459601c34257dd40797c08e6fe2bcf0ee51d72', 'Апекс')
  , ('c56cdc211517120c', 'ru', '5f7ffa4a353bda2e5e403cc3f8b5fcbf11e82722', 'Яблочный хвостик')
  , ('22eac961461ab249', 'ru', 'c6db2ec02dcf3556a6323441f9db90a8db6c6932', 'Восходящий')
  , ('9eff451fa8b7f65e', 'ru', '67d0b166e08a2db71d9486f96ac1bb9a2c9ad486', 'Прикрепить логи игры (рекомендуется)')
  , ('6994bb12f92bd491', 'ru', '2b4881723e1320d2b12e0ad31fc9dfc27794c0a8', 'Темп атаки')
  , ('9409ce3813df7c43', 'ru', 'eeee9b76ec5d1cfa27c511f2def4981c9c5b667c', 'Аврора')
  , ('ac3f9e4803a9463c', 'ru', '96fe497e8d08bf63fbd473f4404b51f515bb3dac', 'Градиент: аврора')
  , ('9c9b2f5a2d506195', 'ru', '122a68a5ef9fadcd527704d0d89be3776ce44871', 'Ср. Elo тим.')
  , ('fff050a62953a165', 'ru', 'b2df7e1ebbcf4c9557f59de9e8d9e16ff8b7817a', 'Ср.место')
  , ('61ecc3a70166ed11', 'ru', 'caacb9c4120653ddad8aa9d39ba9c52e144d097d', 'Лазурная комета')
  , ('8a4c4be43c067b23', 'ru', '63b68012cb0fa6028ec65f7f56bd1e09a7ecad78', 'Шарофоны')
  , ('dca50b9ed118cbdb', 'ru', 'c079b59c65f4a283f90f1a0511b37ff20c393880', 'Выиграй рейтинговую серию у Sid')
  , ('cecd4fa7f2642aba', 'ru', '315b3a7ff79a5d9a069de5c4b40c89545a06f6e7', 'Выиграй рейтинговую серию у Stan')
  , ('4e3adbbd8a6ed18f', 'ru', 'd8b47f574662c9e2de4a022fe7f25db087c9b9b9', 'BepInEx (текущий)')
  , ('785b325c520dbc5b', 'ru', '072719c3fc70bbe17a0c02b6968f63fb1de66a2d', 'BepInEx (прошлая сессия)')
  , ('7491833f08beadc5', 'ru', '7d812b6c0cf9b06224698bf549532e4dfa84626f', 'Берсерк')
  , ('047de86df5071d35', 'ru', 'f03b60f7e52b7ce49ed1e4f9fa511c452a2185bb', 'Бета')
  , ('3828219f201c6509', 'ru', '28544273e2aef2357d775fe43b318ba43f33a6be', 'Имя побольше')
  , ('cb88c065adf80933', 'ru', 'dcce1b666e42b2516c4264ee76dabb367fb176b1', 'Больше, чем Побольше, меньше, чем Огромное.')
  , ('620a77e0a38cd666', 'ru', 'cee82537870ea52d5f32f6a15bd0752b3c43183d', 'Чёрный курсор')
  , ('4012ddaf0c5772db', 'ru', '5b07f7088b0080a88cd696619c5ce3aaef4e8bfd', 'Чернолесье')
  , ('77b1c8d67327bc59', 'ru', '8882e4bb2a3ab29b02ac332ae19a66cdb130dbad', 'Блиц')
  , ('31af90c64e73ac01', 'ru', 'dae5a0121abb5fa0da729304b67493a1e3ea7978', 'КД блока')
  , ('7e7de6c72b86824d', 'ru', '54c45c033f5eb914fae27a646cbd9e23d3750d19', 'Блоки')
  , ('75f7ef63c5238e27', 'ru', '1aecb54aae1e2b5ed8dfe32d82d5a452ea62616c', 'Синий курсор')
  , ('e91af1cc53639bfd', 'ru', '19e07430eed6d97d6d73cb4a2967b1f316520f54', 'Жирный')
  , ('5102a46fc36366ae', 'ru', '4e36289d0951a7bd412ec33c4053fe33bef6b588', 'Вышибала')
  , ('17e39c5f5faa04a8', 'ru', 'fffb1ac23479a3b099333fa68dd4b912625af777', 'Отскоки')
  , ('7b10209c6ab33112', 'ru', '0861596efe0b8976d831f3ea080decca2798d09b', 'Bouncy')
  , ('f7c82f02b929a7d6', 'ru', 'a9c34a32e6e79b3c17f81be6765ab239ba111db6', 'Bouncy-мейн')
  , ('31730649fbdd137e', 'ru', '46ed5de23cef330d5db5771f01c745d52d1f1195', 'Сброс сетки')
  , ('1dcbb7f9eb5c256c', 'ru', '32f934bf1243eb49222743a5d0f32e178fca1845', 'Трость-мозг')
  , ('62d51247bd7470f7', 'ru', 'c93e38d0d4ff579fde2f4a80a077a881667a17f9', 'Цвет тела: яркий электрический циан.')
  , ('ad0a6dae771517ad', 'ru', '9ec32ed642cbdcae1c042f9b03791ebc2d4e9c6a', 'Цвет тела: яркий индустриальный синий.')
  , ('8d3e5929f807c196', 'ru', 'af3102527f03c95d8e79825f965d8663c7fdf780', 'Бронза')
  , ('8e2573140ef55a27', 'ru', '58356fb4cac0b801f011b397f9dff45adb863892', 'Пузыри')
  , ('390f22c995b624ac', 'ru', '89183a133ac470f8daf7ceb62ad266022b240fc8', 'Баг-репорт отправлен. Спасибо!')
  , ('7811a5db8d47eda1', 'ru', '9fe72981cc879912316e26db5261095ec4da3688', 'Баг-репорт отправлен. Спасибо! (#{0})')
  , ('1e088d00a6318256', 'ru', 'ca3230fafdeab8aaaca7de56a4c8ece290129e03', 'Создан для рейтинга.')
  , ('c4d1897e0b92927e', 'ru', '1982b45375c2d30f60024c602fa49444a089bddb', 'Замедление')
  , ('2b6f6945b122da91', 'ru', '3f7097dd693481d4b33a1a1360bbaeab8ec78561', 'Скор. пуль')
  , ('1b9b94fd93c13e2e', 'ru', 'ce55c51755db07c0da74f585b4c7a4582d55ac19', 'Лимит частиц попаданий (2/кадр)')
  , ('44958e96b42c92ac', 'ru', '7509c5747e5db3dfa3373afc42eca9f5b27a8599', 'Пули')
  , ('d689c0344f85b91a', 'ru', 'f48fa5b998d1a20e5aefa573097ab4dfd104f679', 'Бордо')
  , ('9ef2d087c80357dc', 'ru', 'c3523aedb7179f0f1ed0e80801a4c320b1e398fa', 'Очереди')
  , ('42b58b0e9f96b45e', 'ru', '7db325b3e21b1a5687cdeadba0a48cc535576391', 'Покупка {0}...')
  , ('2bc7b81351452373', 'ru', 'ae687d91ac348704cf2ceb4910feaccbed518dfb', 'ОТМЕНЁН (не хватило игроков)')
  , ('4d4720dda0a927bb', 'ru', '6dc2daaed756f492c0b47af2ae68dfc26d827fab', 'ЗАВЕРШЁН')
  , ('70483da324b9a680', 'ru', '1c1bcb24cffa054e5fd7d06de56bf73a3e74d02e', 'КРАШ')
  , ('f45db7482d67a389', 'ru', '58e286b87091b07259c44d7904e679e9be73eddf', 'Спокойный лесной зелёный с низкой насыщенностью.')
  , ('de467d3edb721838', 'ru', '4b1b1758c6a36dfe7213f6432757a25f25b44fb6', 'Ограничить частицы попаданий до 2/кадр — самый заметный выигрыш в жарких перестрелках.')
  , ('c7400849ff3404d4', 'ru', '4d4ce73b15660f20977ad7efab2283c51bdae008', 'Карта')
  , ('feb7846e483876c6', 'ru', '0f830bc25e52f96121b00a67378be1abeaa3f274', 'Карты')
  , ('1ed575a86bc9d240', 'ru', 'a6bcb0b542f89a1109f41bfa09c4216c3cd8991f', 'Карты:')
  , ('5d2ca42b2c4789b8', 'ru', '5fafc6ce92411f8dd5808ec5a87bc12b0a48c8d9', 'Карты: <color=#88FF88>ПОЛНЫЕ</color>')
  , ('56eeae7c606f171b', 'ru', '72e5a30e619dd5488bc8f47b9a2b6c904e40e38e', 'Карты: <color=#FFCC66>значки</color>')
  , ('1b4effb239673333', 'ru', '8a968fb7dbc2ab1fb3e31e87aea9d81c5b4fc4a1', 'Рот Casi')
  , ('d7d0e9e219b53281', 'ru', '75114685463170b6592d652473ef40eb0a6eceb7', 'Глаза Casicorn')
  , ('05dc830214a8b91f', 'ru', 'ed02eaec1b7cdfe54ca5d028db8b31807f7252fc', 'Обычные: {0}W / {1}L')
  , ('f6a637efb68bcea0', 'ru', '33aed4926d6006ad15fdb8c60b6fa786a37b41f9', 'Обычные: {0}W/{1}L')
  , ('ea0992cf6e04fc9f', 'ru', '61b9204fa30ab100d2a82ad42f62e455b1d2df3a', 'Категория:')
  , ('8fd18c1dd49bf9a8', 'ru', '879f0b1bef59eeebf78cfd3a22f6f8077810cecf', 'Канал')
  , ('d3a2f4060b4d4faa', 'ru', 'c81e2a08f7e0b5c4162685cc5b5ede3c1ec05062', 'Уголь')
  , ('040fdcdc9fe82d97', 'ru', '6fdc92710bf9a1c37713696ed1898bd196a848c9', 'Обугленное дерево — тёплый тёмно-коричневый на грани чёрного.')
  , ('6c93b4c00e97aaba', 'ru', 'b986a8e56e3b5c3b9f806bc270f5e67bb0499f24', 'Чат [{0}]  <color=#888>(нажми T для чата)</color>')
  , ('de0019878b425396', 'ru', '3653056b385b377aa4fe8be7000f0a0f318e2157', 'Канал чата')
  , ('6d74d0c0e8ae9292', 'ru', '5d378529c5ccf974fbf710c541fe49c260696b4a', 'В чате есть языковые каналы - переключай их через список на вкладке Главная или клавишей Tab при вводе.')
  , ('1ec90b2ecc0c22a7', 'ru', '218e75c7a912404b048fff0747e40108873b6334', 'Хром')
  , ('755e04f636c21f2a', 'ru', '568dba56e5fadf7f411898e5b4c5ee9790606f36', 'Ограничить стартовый спавн ObjectPool до 4 в матче — меньше подтормаживаний от выделения новых пулов.')
  , ('9f57ff0905238412', 'ru', 'a3b330fc7dec25ff7c2417fdf084196120632e2b', 'Чистый след')
  , ('d8852fbbce7d5315', 'ru', 'b9a010b399b7896b4c0e26e06e1b2d16738d947f', 'Цвет тела: чистый белый.')
  , ('d1e0f9e0812bfad8', 'ru', 'bbfa773e5a63a5ea58c9b6207e608ca0120e592a', 'Закрыть')
  , ('0bd62ee5c52d93de', 'ru', '58d28d96646957acfa9a8c908d0d61aad25b77c4', 'Клоун')
  , ('96ed0e7311a525a3', 'ru', 'c509eac2111b5bd8b67314feb259572255c6f6cc', 'Кобальт')
  , ('8d3bc6bf3cb691f6', 'ru', '4fac4cec0922ba3d0b40514b9e35526635575dcf', 'Холодные фиолетовые и голубые искорки кружат в тёмном ореоле.')
  , ('f69708bf886ba7c7', 'ru', 'e355071ea9b079a72d85687e2ac34ec406ee7927', 'Красит имя в циановый.')
  , ('7238f6a0f006bd2f', 'ru', 'ce90982b634c51797500d1fa3c0537d9160f3cc4', 'Красит имя в золотой.')
  , ('a29939fd5310702c', 'ru', '378e60aaa1606276e4ecbe32a4488f37421a3a4a', 'Красит имя в зелёный.')
  , ('97bf484344ec2873', 'ru', '2ec2ab8e8e10dd4bac423d81ba3df5fb10f5a85b', 'Красит имя в розовый.')
  , ('b75b645fcf4adb75', 'ru', '2889f9f551f5371f6892e307d5cf5c60025bb0c1', 'Красит имя в фиолетовый.')
  , ('cd7de4ecc01c1d92', 'ru', 'e076968ac0727a056d40623d209ebf3b394200e1', 'Красит имя в красный.')
  , ('059bb297892d12b5', 'ru', 'ce1c631db455b6205a45b767991b570a3cc36d42', 'Колосс')
  , ('8618c3d156db5aa5', 'ru', '7de90a65241a6cdbd9ade485d777715d99285a1e', 'Обычная')
  , ('096503131133e107', 'ru', '470568764445128dbbde3a4861ab484f4d7f3bb7', 'Соперник')
  , ('8107c94687b5513e', 'ru', '04a212215ef9fbf686d280802eb81ee7a6e681cd', 'Подтвердить')
  , ('23a2363525a63d2b', 'ru', '7216727508f5cdbfb1e167595a4e44b10237b778', 'Непрерывно переливается всеми цветами радуги во время матча.')
  , ('2c0b482cb7fb2078', 'ru', 'b3184788eb8c6ab50e98bdded730901d8b5f4505', 'Холодная синяя энергия потрескивает за спиной.')
  , ('1edaccb2dca7ceaf', 'ru', '0c4e7b1605bb2b6079143cb3ff386f3d2882a487', 'Прохладный приглушённый серо-сланцевый — глазам приятно.')
  , ('5286435b58b15502', 'ru', 'd47ddde92346ea04ff6d780400e1c300eb81639e', 'Цвет тела: холодный серый.')
  , ('0157a9143665e238', 'ru', '669a338cd831e006a68d71778ac389a20d8e40f3', 'Холодные серо-синие блоки на тусклом холодном фоне.')
  , ('111b9b5a0d6725d6', 'ru', '3f4e6fe068c428db8f08c82ec6f320768c3e77c4', 'Цвет тела: холодная бирюза.')
  , ('5c819efd5e47b749', 'ru', 'a7a705f4f6e2ae44ccf76ce8ec20cb3f7825828f', 'Остывшая лава — вулканический цвет бычьей крови на грани чёрного.')
  , ('3242c3ee66b19424', 'ru', 'd27ca6c0dabe676d07af8742683d39325665cd59', 'Коралл')
  , ('a72ae56c0ded3702', 'ru', '57a485e2451d558c03fa971091c39322dd7ab285', 'Коралловое имя')
  , ('a18255a7c68182e3', 'ru', '52b4f7979734d5a9daa6702b008bc4dd1047377f', 'Безумные глаза')
  , ('7ae8c98cd55250eb', 'ru', 'd1e2abc18a8b508f620471e42c72adf3818c6480', 'Кремовый')
  , ('1566b2c6e09119fc', 'ru', 'b3f39ab486dccbade852f17535c258ceb02694ae', 'Багровый')
  , ('8aa3777be23776ab', 'ru', 'e1d3d4a4ebd01690499f49db911a9f70902a7e8c', 'Багровый росчерк')
  , ('f027d1391cc75d18', 'ru', '410494f2cf468cb98b4655657880ea42f72183c0', 'Корона')
  , ('c8a0e2e08bdb7f47', 'ru', 'f996d22f90fe3880c9bf2c0026b7e64b2c9d234a', 'Текущий ранг')
  , ('3768972fb7662437', 'ru', '21a1cca38ce259e8e8241d9335c19da50c1c6eb3', 'Курсор: <color=#88CCFF>{0}</color>')
  , ('e307fa465c2af7fb', 'ru', 'fc9e3a357cf300a24d8e3496e2a38f19a2b8d2ee', 'Изогнутые багровые рога для твоего внутреннего демона.')
  , ('306025349f761c7f', 'ru', '26744388a2aad194db923050c4fe31ade1973f3f', 'Голубой курсор')
  , ('b1ab6e33f7326e5b', 'ru', '747761927d1053584caa147babb5f8bb92befb6e', 'Циановое имя')
  , ('b4874c5e05d6538d', 'ru', '7bf6d1d3a58a22ee49f3b78fc132bc5e98633e4a', 'Урон')
  , ('b5a636572c560a3f', 'ru', 'd1337bd66502e493e3dd898db928623e5e720ba0', 'Тёмная аура')
  , ('10cc5458fd27e27a', 'ru', '6400ddf76a965495252cffa62e366cd2e1e5670f', 'Тёмно-красные блоки на тусклом тёплом фоне.')
  , ('fe95157ea5d812b9', 'ru', '94ee8869082873abf458deca86a2b8e3a3091aa0', 'Формат даты')
  , ('8b736b068bcaa904', 'ru', '08596d25c886c9f955df32042b64f4be840b7528', 'Формат даты: <color=#88CCFF>{0}</color>')
  , ('3af3d6023d5ff20e', 'ru', 'a10292c3bb3a1332f06c324215d42310757b082c', 'Достойный')
  , ('bbe3197e69738bd2', 'ru', '698769e3384f77f8587a7217e7ac7b3a9c9990c7', 'Цвет тела: глубокий кроваво-красный.')
  , ('7b5aaa66e23a080d', 'ru', 'bda30be42cb140a97c3e1a67751c1da38c2ceb11', 'Глубокий сине-фиолетовый — миг сразу после заката.')
  , ('efe79bae30a5be47', 'ru', 'b30ee14d6f5a4695053e04642b94ecb60916730f', 'Глубокая холодная синева сумерек с приглушённой экспозицией.')
  , ('ce5c7a3baf9b6aa4', 'ru', 'ef88541ebbea1230910389468e407d07bf0c5d46', 'Глубокие хвойно-зелёные блоки на пригашенном зеленоватом фоне.')
  , ('13d0d287c990cb23', 'ru', '01d54aa6323503c2e4424a176601f7b00c366139', 'Глубокий лесной зелёный, восходящий к яркому нефриту. Двухцветный градиент.')
  , ('3a1384cf68cbafa9', 'ru', '6b2e6d11146de2269d0295012c6fd7f7061101b1', 'Полночь океана — чёрный с примесью холодной синевы.')
  , ('b95f34ace2fa0325', 'ru', '0c7459d1da70cc3b119267a865e39cb294ce276a', 'Цвет тела: глубокий океанский синий.')
  , ('f05cbe9e346dc452', 'ru', '343c93580548bc432445ab81ff3add7560c3d74c', 'Тёмно-красный дым следует за каждым твоим движением.')
  , ('91dc11e808ee40a1', 'ru', 'cba6e53a33069151fb549a1f0e6934023b31955b', 'Глубокий королевский пурпур — из тех, что поглощают каждый фотон.')
  , ('f4999184f00fd765', 'ru', 'ab5e0dd7f1c6d715060995c24097c27dabc964a1', 'По умолчанию (случайно)')
  , ('77698eafc221e602', 'ru', '133e5f657b000e24c75606ccd1808f5d6fb5a618', 'Старт по умолчанию: <color=#AABBEE>{0}</color>   Запись до: {1}')
  , ('664c773cdf0bb4c7', 'ru', 'a957d1b7bc867ae01a8723a614a867b018c111b4', 'Крылья демона')
  , ('2fc6ee0492894d1d', 'ru', 'a1b943b041c4467fd8e874c41839ca774a8879e4', 'Удалять пули за экраном — хост убирает пули, вылетевшие за пределы камеры.')
  , ('6fb3f056a5481e85', 'ru', '55a2bf4d07dee2378de337391d28fcb235be8066', 'Деталь: падающая звезда кружит над головой (анимация). Надевается в редакторе персонажа.')
  , ('83c7c50f88df9d10', 'ru', 'b76e06ba2922bd5320f09988df4115981726164b', 'Деталь: сертифицированный ангел. Надевается в редакторе персонажа.')
  , ('57f1bdcef79892ac', 'ru', '91e791312991c216c7bdca715ee22fa1062f21d0', 'Деталь: косметика от сообщества. Появится со следующим обновлением мода; надевается в редакторе персонажа.')
  , ('0599d7612e9c92b0', 'ru', '3606ab5ea0cab3d56f0f7fb96596c962e44194b9', 'Деталь: уютные наушники в звёздочку. Надевается в редакторе персонажа.')
  , ('9c528b8f8d623258', 'ru', 'd35ece05488a58ed9adbf2fd9423a0e4bd0c206c', 'Деталь: тяжела ты, шапка Мономаха. Надевается в редакторе персонажа.')
  , ('0cff0a7295d0881c', 'ru', '0f2a3d6e36b590dba6e93f3a10088a8f34103cae', 'Рога дьявола')
  , ('71ab18d24bbd5f46', 'ru', '170d1f2f961db1e8e435c04f979012f0c4813bb2', 'Скрыть (1 мин)')
  , ('a30778fa3d629f33', 'ru', 'b7453a2df406d0e7a753fa2a13a759aea4dd2294', 'Показывает твой актуальный ранг (обновляется сам при повышении и понижении)')
  , ('d44b7e9515f5e841', 'ru', 'bd67e561431b21dc42d2874a3fa3ff6248e3fa8a', 'Таблица дуо')
  , ('e15f7f445c46ae93', 'ru', '4db13aa08e06f68b46f6d3819cdb45cae2b882d0', 'Сумрак')
  , ('3367c75f1b297a7e', 'ru', '58f3cb1034a175e1d3f0bb7523c2449f731a9bb3', 'Пыльно-розовый, разгорающийся до багрового. Двухцветный градиент.')
  , ('1d3249d2a988a709', 'ru', 'abc5f75a23c865711420044ed601217ae35bea54', 'Пыльно-розовые блоки на тёплом тусклом фоне.')
  , ('554216dc58af09c4', 'ru', '9b0acd4461ab7da7585950db970135db010f6aa8', 'Каждая буква имени — своим цветом радуги.')
  , ('5f1ededf6306d873', 'ru', '7efda4c6d275389b1bfd26f7a15ac191beb583c8', 'Ест урон')
  , ('fde511fb7c73ed95', 'ru', 'e738c7d89afb7a9acb548496f7ce7ca8d6b2a2f0', 'Echo')
  , ('94289445357e1566', 'ru', '4899aea0ad7311f429c135299da2adc96ca17eda', 'Echo-мейн')
  , ('9d675c20af88ac85', 'ru', '29ff1525ee6fdd2e6fd0e55e379a4e224f5776e5', 'Глушить NRE EdgeBounce')
  , ('2b5b3a47fa9ab0b2', 'ru', 'b4ce3eb96421a2bc09e75479472c6baa5a0610ee', 'Электрические искры щёлкают и мечутся вокруг тебя.')
  , ('c8a63c1732410b70', 'ru', '9d2514d92ca9b022beab74865f8146bd878801be', 'Электрически-циановое неоновое имя с мягким ореолом свечения. Имя видят все; игроки с модом видят и свечение.')
  , ('2c2b83458da6e21e', 'ru', '50b385ec12fd86912cc1c6ecc39e0abf1a282cca', 'Градиент: угли')
  , ('17623eac4b59b734', 'ru', 'f95951bd6069d431a0a73fc47ac7e0d3e44e622b', 'Угольки')
  , ('aabf3a6bbef39977', 'ru', 'da32ecab00cdd3a4cfccfe58a62338d64fbe94a2', 'Изумруд')
  , ('3273d686feea4e85', 'ru', 'd84efbd1322c23b8b2a9cc87004e3c450ea13a8c', 'Изумрудное свечение')
  , ('fe85ade52f92f64e', 'ru', '2c9dde1029ae34d4232e975c93a7a04067eb085b', 'Изумрудное имя')
  , ('1fd64c1efd7d9083', 'ru', '83bdd3b5230da99776ea3b56316a89419519fbcf', 'Empty Power-мейн')
  , ('04af4b0b1909b0cb', 'ru', 'a13f4b9bac07d2b398f39f962a4e6e6f64ec7afb', 'Сферы энергии')
  , ('69df762b04945155', 'ru', '747064df7c49f0b13a9bb661d6209045ec2e3fdd', 'Хвойный лес в сумерках.')
  , ('31d3f2a1c4e5d101', 'ru', '2ded2d6e7d0c2c2df38250fac32026e3469bedad', 'Все с чего-то начинают.')
  , ('67c04e155d92e2fb', 'ru', 'd7a501f83242fd940b8190529432e0703dd7606f', 'Эксперт')
  , ('f8722c358b268c6e', 'ru', '16b52078a6f08d64300bd48fcb78dec76756adbb', 'Цвет тела: до слёз ядрёный розовый.')
  , ('14315d8bfdc142da', 'ru', '42004fbbdfdd9e28f20bc7b40b8340b1016a8473', 'Глаза: косметика от сообщества. Появится со следующим обновлением мода; надевается в редакторе персонажа.')
  , ('0f34e682111c0d18', 'ru', '0ac81439129159c9c49e680faf69be65fb6d761d', 'Глаза: золотые звёзды. Надевается в редакторе персонажа.')
  , ('b8c027d3e3a34c81', 'ru', '2684f8c6647a0ec56162173475a06b2700f4688d', 'Глаза: влюблённые сердечки. Надевается в редакторе персонажа.')
  , ('ed148bb9c7be8e8c', 'ru', 'fabb304f63738fae1d8b8290dfa48d39166bd688', 'Fast Forward-мейн')
  , ('1ac50717539486a6', 'ru', '142cf28bcdc25525a041a6fdec70244bd7f34e83', 'Быстрый финишер')
  , ('6a77c5ad69934952', 'ru', '9727f8a805db983c5d5372d96d511ce90094cbe2', 'Дойдут немногие. Позволить себе титул — единицы.')
  , ('43b2f69fc34f5d0d', 'ru', 'cdc31cb72e817957694d9471984bd835a93dafc1', 'Огненный венец')
  , ('4d0ae42a5167a39c', 'ru', '455a8cfec6c15aa9f024bd2cb4d2dd92bafc3c6d', 'Парящее имя')
  , ('857d64183e061d3e', 'ru', '6c741cc15dd127d0473f2b78bab3176ede8c2057', 'Розовые сердечки взлетают от твоего тела.')
  , ('faad0c987e1f8490', 'ru', 'c6b8dfc0f49980b4284e35414a755c6e2d0fa5f9', 'Для тех, кто заслужил это право. Стоит всё равно целое состояние.')
  , ('3482219b5141fa38', 'ru', 'bc90b7b7a0f89810a21b4c074f2a6a74152ea24e', 'Принуд. выход из комнаты')
  , ('26f48ec14590c3ae', 'ru', '6038950c3ffe7f90843135db324457e4fa5b86b1', 'Принудительно пишет имя ЗАГЛАВНЫМИ.')
  , ('37e3bb991b9d0230', 'ru', '3f93069046dd262e169342cd220aa004644ab861', 'Форс-старт откроется при {0} заявках ({1}/{2})')
  , ('acbb2acd18c65dd7', 'ru', '86bb334f8ed2d24e6c396de77e5ca2c7be2bb490', 'Голоса за форс-старт: {0}/{1}')
  , ('c8b11f4b97ff6849', 'ru', 'f41c4e4dab0b44d75dad0c04a0156d326c95b774', 'Лесной')
  , ('f72488c19efdac04', 'ru', '8be4bf379229e1042e85793249e4608bdaa255c8', 'С арта карты "Healing Field"')
  , ('280a08e85e79e12d', 'ru', '6032a672e309a4dfd10a6c41199d5fd8c5c83da9', 'Иней')
  , ('aa96a51a1e9af834', 'ru', '9905006070eedb6ae48e11bb4b977e1ba02955c6', 'ГЕЙМПЛЕЙ')
  , ('9234ccf14b5a0045', 'ru', 'bf317bc7c73647140d56b21fbf2329d373e385cd', 'Градиент: галактика')
  , ('79a0762ddaf41128', 'ru', 'd9cc3dc4f2aba64784ee730953c68b885afbe01c', 'Игра ?')
  , ('7b0dc0b4d08487af', 'ru', '70016b079c5047ff972d699f67163ceeabf3ab5f', 'Игра {0}')
  , ('e5afdc07523f8396', 'ru', '0b9ce69dc04eeb6c6027497ff1dc0da1030da5d2', 'Игра {0} - {1} игроков')
  , ('fd8d7e51279627ed', 'ru', '4200a0fa64073d825b8861ad95ee0536180ae1f7', 'Игра {0}: ход счёта')
  , ('fff10c9a1a7ab76e', 'ru', '398ed329814977519b9f899253338884a2ba941f', 'Игры')
  , ('b43c450431d13f59', 'ru', 'f75572ef86d5cfaece368a57351d584911134e8e', 'Нежные мыльные пузыри поднимаются вокруг тебя.')
  , ('ed2d10114d8fa1c7', 'ru', '109fe33ee568cdbfcc2bccb3d5667edb0cfcc4a9', 'Позолота')
  , ('ecf3deede556e555', 'ru', '5f1184f7df96c5928092ad9c6b550699bf887826', 'Общий')
  , ('8de6c27992aeba7b', 'ru', 'acbaf66b3f491443e004f29007d7da47b05d138d', 'Цвет тела: глянцевый вулканический чёрный.')
  , ('8516a2f129517456', 'ru', 'db4c6e762d551cdd15ce81da6fa4d2916ee2c8e3', 'Жёлтое свечение')
  , ('3e6d65a6be5e46d4', 'ru', '4f7ba9d9a46c7284d51a3dc4e628fabb3acec15c', 'Тлеющие угольки потрескивают и взлетают.')
  , ('41261dfa6845c60f', 'ru', '0c0de17323ea7ac0e7c27b2c1521765db1278f0d', 'Цвет тела: сияющая фуксия.')
  , ('0e8218c38e24e14a', 'ru', '4ccdeb2b81cdab9d1fe2c4707b86bb05059e0f20', 'Неоновое имя цвета фуксии с мягким ореолом свечения. Имя видят все; игроки с модом видят и свечение.')
  , ('6c8b90ec9540ad5e', 'ru', '72fdf7b43d255bfca709ad5b2f17f4c501334a6b', 'Золотое имя')
  , ('badd96d7af08d83e', 'ru', '361a685997549953a08875007aa5a09476ac95de', 'Гранд-финал')
  , ('0621e139a09a22b7', 'ru', '1e3c573a02d261117603239280b2414106d2de67', 'Бабуля')
  , ('3426d61e9ffeccc9', 'ru', '3ff31ec176822ae0d4a3602b4b80563f74ca6119', 'Зелёный курсор')
  , ('c91478ec31d61956', 'ru', '3f508506b3bbc0e084dffe7ce76e5c8ec800e0ad', 'Зелёное имя')
  , ('fb1478c1f65baa33', 'ru', '82974e1f3b7ac1ae1fd1714ea5e215b421da1805', 'Серый кот')
  , ('0ac4a55c5f1ccb06', 'ru', 'd77d0b27955f008358918e195742c4c8208699e1', 'ВЫСОКАЯ')
  , ('8fec4bc289417df0', 'ru', 'f3681d8bf189692334f17228e4c6f6976fc76e68', 'Нимб')
  , ('112f0a217f5a096e', 'ru', '6ce2c7378614f190440e5da3487b936abbd6781c', 'Попробуй попади')
  , ('3960a6d82453549a', 'ru', '06e27642e791a899db92ec7fc9fc01900dd8d863', 'Торопыга')
  , ('1e5e8f7d43e5b601', 'ru', '6cad85d7f7dcd1b52fab90c0435e0ef4df7ef791', 'Целитель')
  , ('0b8a96a36bbd6047', 'ru', '31f3455e822c8b2187691d06a5cbce86abba2ce1', 'Healing Field-мейн')
  , ('90c59f6f9a2fdb41', 'ru', '48ee9e4fba600c1e5238b5b30afe832cee3f4452', 'Глаза-сердечки')
  , ('824fe214604ba4a1', 'ru', '99f9bf69ff7f179b358e1191419dafa45a0d75db', 'Сердечки')
  , ('4bdf43c6198c4944', 'ru', '9de786a3c943e4fc74c3ab105df60d4a8cd2b8f9', 'Носят только топ-3 рейтинговой таблицы')
  , ('341bc3956a62a4c9', 'ru', 'a14b11926312cad57e30de5af74a2d2f016fe58f', 'Скрывает твой запас золота от всех в таблице. Включай и выключай когда угодно на вкладке Прочее.')
  , ('a13104d1f01151a6', 'ru', '7d45cd2bcca78ca9b078914744db3bdc40609f21', 'Глушить NRE звука попадания')
  , ('071c8c4641b18c3a', 'ru', '2b77056d8510cbf771ae1eabe376618a805c01e7', 'Homing-мейн')
  , ('7839675d71513a87', 'ru', '0a651c070742e5b205bdf0d6ec0b389fa0524d53', 'Бип-бип.')
  , ('e4ed2e45c87a71a4', 'ru', '55d34abe601f847d5d3c021c49f5bf80f5db5d6e', 'Ядрёно-розовое неоновое имя с мягким ореолом свечения. Имя видят все; игроки с модом видят и свечение.')
  , ('c6ea11f664524a12', 'ru', 'cf4e2230ffef8a783fcf4ea4e36306115c1023c3', 'Как это работает - Асинх. (6 нед.)')
  , ('58adc2e93f0e5669', 'ru', 'b4a5f85c718b851bc30c568fe28f4ef79037ce0b', 'Как это работает - Синхро (еженед.)')
  , ('f501fa2dd1f5cbc4', 'ru', '5eb10c630fc6887d4a44e6d2b996c378edff9152', 'Как пишутся даты в меню мода (история, таблицы, турниры).')
  , ('8dfae9b58d919fe0', 'ru', '32978fbe93d3be31d803d0f25bc182a893e9a2f2', 'Huge')
  , ('a95527c4eb90449a', 'ru', '96096beb7426ce6ce5e38c347d4d90ad2a3f936b', 'Огромное имя')
  , ('bce43d5b196d8359', 'ru', '0c99c0f89091cfd5c213bec88778fa6d7c4b67e1', 'Huge-мейн')
  , ('1491ccbbab4f77f2', 'ru', 'e41832724539bffc1b27e6bf1721c3d4b02fee0a', 'Глаза-гипноспирали. Полностью с катушек.')
  , ('d8ba12181cae06db', 'ru', 'b18f1b30f790bc9203c185bcbf4e886783ef9d75', 'Ледяной синий след, тающий в белизну. Двухцветный градиент.')
  , ('29acfd71fca68846', 'ru', 'b2c854c19c069e8f54d7bc38119fa68daba14613', 'Идиот')
  , ('cf6154247e010be9', 'ru', '896aeebe623741dcf08c97d02e0111f4311b39e9', 'Имя индиго')
  , ('6155cc874330ae15', 'ru', 'ad8477c02907e0acf0430c6c33bcc17614b5cbe2', 'Индустриальная сталь — серый, из которого выкачали всё тепло.')
  , ('742b61a27b8f06c2', 'ru', '8564fe3b4b674b36c08f22266d713f860a15ca99', 'Железо')
  , ('27972bcd47cb6e6e', 'ru', '1616e2e5405e69c4e3914c67c644a9bd3ac00956', 'Курсив')
  , ('5bebdfe868db2544', 'ru', '39973be20679a94e4c998a58c0f6c76daaf6cd11', 'Айвори')
  , ('cb5be6eb1a54e3b3', 'ru', '1eba140fdd9c6860a1730c408e3064aa417ca2a3', 'Прыжок')
  , ('14ff90268c5dfe1d', 'ru', '933adea19eee0a6883654433bf5abd0a524cc8c6', 'Прыжки')
  , ('101d281fb7725477', 'ru', '27e105212199fa01c8a9ddb8d5052a43b991fbae', 'Цареубийца')
  , ('70ef6c5c94097ef3', 'ru', 'f5b75e673715471ccd9edc10e29ada4d24f5dfdf', 'Рыцарский шлем')
  , ('2c692d50a4ccf781', 'ru', 'f898dcaa913e7d96aa2f5cc90629d9e61f5f363e', 'Отброс')
  , ('683bcd6f2e8b0c87', 'ru', '6990f01ad9d2dd9bf6acbd5330b2a51dc97e62e5', 'ИДЁТ')
  , ('ad1e59715a6ba031', 'ru', '826eff5d83a7f019b3d90ef265f759162f982ea5', 'СБОР ЗАКРЫТ - СКОРО СТАРТ')
  , ('bd5f6718ab6205d7', 'ru', 'd8b9679fad55bd0178081bc796a093eec7fd845c', 'НИЗКАЯ')
  , ('c5768a1032dce392', 'ru', '75c88f3a0072cbd028982b65a0fcf2db0c4a5b15', 'Лаванда')
  , ('2130d9c2eb9e3c76', 'ru', '4459b791a680572873dc2cf033487dc21edfcb9c', 'Лимон')
  , ('a204547475823743', 'ru', '417f106adb9eb8a88f7f754dff056d4ad92f62fa', 'Вампиризм')
  , ('5431d62eb89eb032', 'ru', '647b0df3eb0dc7b333f9063728d3b2e3785878de', 'Чуть приподнимает имя над строкой — оно словно парит.')
  , ('a59a55265cfb11eb', 'ru', '7e845d62d2ff38633cd16021f0b03eb78640abe0', 'Лайм')
  , ('3b4605576de92799', 'ru', '0582db7c610c15142547997e9e2b19457eef92cc', 'Розовый дружочек')
  , ('a48e13d370e30ad1', 'ru', 'ce6afbd4b60bf8dfe8e4a2a6327ac8598e740559', 'Жизни')
  , ('c731a1c891e2ba81', 'ru', '7ecb9e49219df7f9e2fafd4f4cd75eb164d24290', 'Фиксирует палитру карты: Gold из ROUNDS (тёплый жёлтый).')
  , ('d9f0ab270fa95deb', 'ru', '1ca68d13c18e8e434805d0a510762510ca601ac1', 'Фиксирует палитру карты: Poison из ROUNDS (кислотный зелёный).')
  , ('26d766cf70a26dd6', 'ru', '9ae747eccb6b6170ae4f18896e498142e45387f4', 'Фиксирует палитру карты: Rainbow из ROUNDS.')
  , ('77501ba1887630dc', 'ru', 'e07f293196ef7e0937ab9343b1984c5ffaf4e71a', 'Фиксирует палитру карты: Sky из ROUNDS (голубой).')
  , ('5215a7389616213e', 'ru', '2dc9a74a3d4c4d4552153339ca5aaf59af7a8a61', 'Фиксирует палитру карты: Soviet из ROUNDS (глубокий красный).')
  , ('a499e490a762a41a', 'ru', 'c2cb065aefa60150ca2e076e295363c45308b3d6', 'Фиксирует палитру карты: Sweden из ROUNDS (синий + жёлтый).')
  , ('28ade4ed4e32aabe', 'ru', '6ce79956bdb35a2d91a54cbcd83332de043345d7', 'Нижняя сетка')
  , ('0c996f453fd078f8', 'ru', 'a47242e6772160f53510181c157f8401003ae798', 'Строчные буквы отображаются как уменьшенные заглавные.')
  , ('a28f48411a5bcb0c', 'ru', '939ab68bfd22b3400b502c8401ff4be78f05031e', 'Клевер удачи')
  , ('0bc4ff39724d6896', 'ru', '9fa8c9a61e28dd229fc118d6c8e04e77a7a2a087', 'Счастливые зелёные клеверы кувыркаются вокруг тебя.')
  , ('605b23aab951f318', 'ru', 'aaebd0c4faae71a489204727bee2e9b3773fd5a8', 'СТАТЫ МАТЧА  <color=#888><size=12>(держи Tab)</size></color>')
  , ('84ed7380201d44df', 'ru', 'f68525ad751f8a1d932458c4c58a214bdf0b30e9', 'СРЕДНЯЯ')
  , ('61abcf4400fd7a42', 'ru', '3548c9250892c509047e2c7ec04d76bf39c63524', 'Магма')
  , ('77f5fa96a313fa19', 'ru', 'ca6ebdf49e3b17cc5b9a43d5ab6a00aef37e3a3f', 'Марун')
  , ('32ef039ee20872b3', 'ru', 'ea6dfcad0bbb0197cc432580a763bdd37c55ef73', 'Пропуск апдейта меню')
  , ('5aa6d8c6966b7d57', 'ru', 'aaa70f58c89e39722304f18ce50db0b7bf8907e1', 'Мята')
  , ('c92f5f7bded0170e', 'ru', 'b6af76411b6d6bc9e35cd94b8b7ea98f83b14aaf', 'Зеркальный хром с мягко плывущим оттенком.')
  , ('4f87758656255ee4', 'ru', '1dda992b70d55b62ecc5e22ba264afe7a9f07d02', 'Монохром')
  , ('0844884be994ab63', 'ru', '037358024aa12328fac8d7804df79d1552816c63', 'Месяц/День/Год (США)')
  , ('53fc58107ad3018e', 'ru', '6938f3389402f793e6adddb682e3586aec57a2e4', 'Чаще в рейтинге, чем вне его.')
  , ('67a6d0f456b16987', 'ru', '752fbb36578511afe3527c40c95abe3e1f95d7bd', 'Мох')
  , ('44296b8aa369d553', 'ru', '3d934064bc875a99085c8782d09dde442c97d696', 'Усы')
  , ('1d0c46aee85e3de7', 'ru', '7f2f10fba7859343ca2963aa166a642641709abe', 'Рот: солидные закрученные усы. Надевается в редакторе персонажа.')
  , ('53236f8f806d6a56', 'ru', '9b4279e882d9e4eb0133e566ccdea4fd7247638b', 'Рот: косметика от сообщества. Появится со следующим обновлением мода; надевается в редакторе персонажа.')
  , ('a55f45e878c399c3', 'ru', '1e7a29d5061a52a7f293263e92f9a5aba4275e1e', 'Рот: зашит наглухо. Надевается в редакторе персонажа.')
  , ('baba0a75c39bf4ee', 'ru', 'ae53d6915d23e165765583cc340533e6e418cbd7', 'Скор. бега')
  , ('06283c7ad737ef2a', 'ru', '931e8d8cc7286798b1633cc33805cf51193e14f9', 'Горчица')
  , ('36d700539721f63f', 'ru', '6845c6d90585c24d63de266c9a6da04090ed2dc2', 'СЕТЬ')
  , ('d6f2bbfbd961e078', 'ru', '8c4507cb4fa8d59453f7770418e0681c1acdcfa1', 'Почти чёрные блоки на чёрном фоне — максимум контраста.')
  , ('6db0703509c1dfd1', 'ru', '7633072baa568d07dcc6acf347d8e0c67d78267f', 'Почти чёрное вулканическое стекло. Растворяется в ночи.')
  , ('76a3b977b8f74add', 'ru', 'e91fae69ed9d52f9a959fd0aa232df98f563c6ee', 'Неон-циан')
  , ('1ce0cf2cdb6b1aa8', 'ru', '664681d96609b863f34e7bda85acda6b22882fc8', 'Неон-лайм')
  , ('7ce4510e0289c059', 'ru', '02140665ff58b93bef26879f6a7975a896f578d5', 'Неон-оранж')
  , ('a7c09f9477311f3f', 'ru', 'ff2c0cb639d80711db062bae5aec601a4e61ce51', 'Неон-пинк')
  , ('83394acf5203df01', 'ru', '3b3e75bdc737be9d9289b248cf3318803f001c65', 'Неон-токсин')
  , ('9fc067aacc4b389f', 'ru', '25e66746dc67e99386bfd26e11749d59a7a08c7e', 'Неон-виолет')
  , ('e82cae6d83d41b06', 'ru', '7688eb7fae9a048dbbeed0e73b646bf684cc09f2', 'Нет активного турнира')
  , ('72839b0611990203', 'ru', 'b47b90daf74ab5d4bbf2b814f199f2ddf3ca8ded', 'Нубик')
  , ('692dbb3bbe0f1257', 'ru', 'b8a8dabdec32830a601c4453d32a42f6722011b4', 'Не великолепно, но и не ужасно.')
  , ('40db0a284e076c04', 'ru', 'dcf9125b0badf4d4589de22a864504ddd27927f6', 'Деспавн пуль вне экрана')
  , ('7ec612c4edc75150', 'ru', '957c024b38ce820878f03177ce3d2b83c26a82d0', 'ПРОЧЕЕ')
  , ('a719fac14ec5fa11', 'ru', '72d696a4f4dc7c22c8686bf0360cf923d40de5aa', 'Лимит инициализации ObjectPool (в матче)')
  , ('2a0816edad12844a', 'ru', '24c869802c3e242e28585a1c90c21847f259e4f8', 'Обсидиан')
  , ('7da210afed1bb3ea', 'ru', '7e4c3a7dbaa079df9174e3a12981708587d175ed', 'Градиент: океан')
  , ('0f0e4598b4018d73', 'ru', '8f62f4336f1907e6dc87f983416184094f6ff35d', 'Олива')
  , ('3242ce42885c8179', 'ru', '9a11776ea9b0901090a67e662d47f5e9fe990089', 'Открыть форму репорта')
  , ('45faa04dd395d9ae', 'ru', '1e9ed67a9b31975b8a43893fcd351af7231d2512', 'Соп.:')
  , ('7e1141fef186c747', 'ru', '00611e720d436d942093ef05ad8481bacf52f082', 'Соперник ещё не подключился — подожди...')
  , ('4d8c0cc6fc7fefd5', 'ru', '783dedc30ac7f71e7f9b2ebba24f435e2f0ea30c', 'Пики соперника')
  , ('b99e6172f212d16b', 'ru', '1af2afeff5d2f90ab6966cb74e75ab1e1082b53d', 'Оранжевый курсор')
  , ('572dd774b6ee6a62', 'ru', '3997c754c441e48d35184d2d9db0a028a6c9346d', 'Оранжево-жёлтый градиент, обжигающий арену.')
  , ('8ab8f916e666eb1a', 'ru', '998da40bba23a7b05d2c404389849f0f793b49dd', 'Бледный ледяной голубой, как зимнее небо.')
  , ('bf950976d4c6643b', 'ru', '9c702f519475562bf73e49dc3a37c10b50a87674', 'Бледное светящееся жёлтое имя с ореолом в тон. Отсылка к классическому трюку с цветом ника в Steam.')
  , ('51b860af248239b9', 'ru', '33965e30fc529ff12defc4f985185e526707cd07', 'Бледно-мятные блоки на холодном тусклом фоне.')
  , ('bbafbcbefeee1a04', 'ru', 'afd15ef89657a69cc8d382f43cae628b459cc1b2', 'Цвет тела: бледная мята.')
  , ('8276060936caacd4', 'ru', '9d32fee8673386fcb48650a016fe7874c5c0f377', 'Праздничная корона')
  , ('02a88da890abd1ce', 'ru', 'd0cfb954a9334a6c99881784734346cd543a750a', 'Проп.%')
  , ('8227d56c911268e1', 'ru', 'f08ec7ca421c33b887294dd88f4ba78c26fd48d7', 'Побуквенный градиент: яркий циан → глубокий индиго. От поверхности до впадины.')
  , ('b03342feaff2e735', 'ru', '3f1c0d14e823390910e171a2cb32a8ad991d59c2', 'Побуквенный градиент: яркий жёлтый → глубокий красный. От пламени до углей.')
  , ('b42387c8be516f9e', 'ru', '57a7a6cdae35659fdaab629a1af89418c8b819e0', 'Побуквенный градиент: фуксия → циан. Межзвёздная туманность.')
  , ('cf5aad12a3f6733b', 'ru', 'e33445036b26cc0c43db07baa039c326346c1692', 'Побуквенный градиент: бирюза → фиолет. Мерцание холодного ночного неба.')
  , ('30ad5fe9e45c303f', 'ru', '32efb45b331be9c80dc68d23882fe31dcfb8b1f2', 'Идеальный баланс: один светлый, один тёмный.')
  , ('2cd796c73bb4cce7', 'ru', 'baae5e74ea779b7a0764d7e688a498b8ce825e73', 'Главный переключатель производительности — разом переключает ВСЕ патчи ниже.')
  , ('7df6272aa44de13e', 'ru', '3e978fbf8aad93b7520fcec25f666a8823b47615', 'Феникс')
  , ('e77e0b2592889257', 'ru', 'e667878de6874deec7efb0c65ddf39bb296521af', 'Пламя феникса')
  , ('1cd08b528d6cb3fb', 'ru', 'a1b97d981b566c2923f68b338c4d2b81ee2018a2', 'Выберите время старта <color=#888>(несколько вариантов, обязательно для записи)</color>  <color=#7FE8C3>лучшее время: {0}/{1} согласны</color>')
  , ('4be253b8080d3f06', 'ru', 'f5f61efb04cc0bde68137d2124c1656a262a2038', 'Пики')
  , ('21464be1e8300f5e', 'ru', '456e097f4ceb19803ed7d70dbf2d28a51848d23f', 'Сосна')
  , ('4bb91d4741ebaf17', 'ru', 'b12540f76b8ae0ed79395737854d6d05a71804a7', 'Розовый курсор')
  , ('88d9415535dd3e6d', 'ru', 'b6744ad14e80c3f4975d1874d4abeac76118559c', 'Розовое имя')
  , ('a39999e17f4758a1', 'ru', '96ef7f60b0e12322ce4490d8ea26c66eb5e0576c', 'Поставить')
  , ('1d7d88d5ab1ccb40', 'ru', 'c93fa0a5953ea725bfad3d51caa53e0abd992fd2', 'Платина')
  , ('e9939d439ec9d4f0', 'ru', 'e53407cfe1a5156b9f0d1eed3bab5ef3ae75cfd8', 'Игрок')
  , ('3bc81240cf6b8795', 'ru', '315b1f52cdff2bd5975f933f866c66ac0a84f8ac', 'Игрок {0}')
  , ('cdf6bf28ca817ee2', 'ru', '971b5de3da8d8c6ca118ca7ced01592c6e67bf00', 'Пьедестал')
  , ('b4afe6f94d8a1b3b', 'ru', '6de0b0c656444c55bac48c2e467aa0f841083cdc', 'Poison')
  , ('c7ff4f384e1ed8c3', 'ru', '994ef00e3288928269240324105bb35e1304c87e', 'Poison-мейн')
  , ('0e72750e37c7c6a4', 'ru', '53b8d6d04b42c5527575738edfd453c84e07ad7f', 'Отравитель')
  , ('6ca9dd38e68467c1', 'ru', '79e59b6d40ad67a86922bb3f5937e4a051c43f13', 'Фарфор')
  , ('68b06756b591710e', 'ru', 'd603c62a187b010ba86e02a8a3eae5477f7da9ca', 'Стреляет без промаха')
  , ('90d0551d9d3aec2a', 'ru', '2fd710fc7265cbfa6686c3f0b03de6975d70e6f7', 'Премиум: холодное серебро стен с бликами до чистой белизны на тёмной оружейной стали')
  , ('51afe625aeb8a965', 'ru', '22f4f84ddb194e43610ebb98e62014a7317abfe9', 'Премиум: расплавленное золото стен с бликами белого золота под сводом глубокой бронзы')
  , ('a1b12781f1dcf408', 'ru', '381ae69d6dec239a744146b21683d1da1f3ef1c0', 'Премиум: стены из северного сияния переливаются полярной бирюзой и фиолетом в полярной ночи')
  , ('a1b5a04f8d591cb8', 'ru', 'd42e29e77884854a5e8b41eb4d0996d9758c52e4', 'Превью логов')
  , ('75b908029624d68e', 'ru', 'd2b78d262308d18630b0a15b9c03018be74b5d16', 'Превью: {0}  <color=#888>({1})</color>')
  , ('204f8caeaf9b9177', 'ru', 'ffad6acebcb46cb4a5b292d6ce8b9156bb2952e3', 'Призма')
  , ('88fd0dc2b471baea', 'ru', '04a4408655caed1756da3dd8fddd01e0563e0a94', 'Призматический след')
  , ('8dcd95733f0c2303', 'ru', 'f33e1d33043740f2b9906fcb880abd6d11a6a22c', 'Титул-местоимение.')
  , ('b90ef63e7495e242', 'ru', '1bd8f1b24f475d07e65940615d102d138bfb866b', 'Чистая агрессия')
  , ('b8fdc86007277b7b', 'ru', '58574a4f8f3a1703dd84bf2e5628e34cc1c666c9', 'Чистые оттенки серого — минимум визуального шума.')
  , ('30517b69c320de25', 'ru', 'b9dff734194f8410236cfa4ea86d68ede85cdb6c', 'Фиолетовый курсор')
  , ('15902baa613f6be8', 'ru', 'e1b4569dbbad3384f405de04efad13c425231ab2', 'Фиолетовое имя')
  , ('b184685895afcf0d', 'ru', 'ac2f7ec50caa3e176d76d18c4b08ddc29913a773', 'Фиолетово-чёрный теневой след. Ощущается неправильно — в лучшем смысле.')
  , ('7b55f022da9fc830', 'ru', 'fa664531b4a41c6178b16cb21826ade02ac9de83', 'Quick Reload-мейн')
  , ('19028acb5fad6b86', 'ru', '75e2d41b04a8463628b2f2bc5c724326fc3488ac', 'Радиоактивное жёлто-зелёное неоновое имя с жарким ореолом. Имя видят все; игроки с модом видят и свечение.')
  , ('5f7558f212422e9c', 'ru', 'b4a9395d25398654fd5d000e4b82a1d8273339bd', 'Rainbow')
  , ('b6862f5ae4f76951', 'ru', '9b8cce5d7eccd2e22579b152d9d9be67ab1466fc', 'Радужная аура')
  , ('0dc7d933cccba541', 'ru', '153fd22a1e9af7179306e615f49ac52f49829bc6', 'Радужное имя')
  , ('ba3394d24a886db0', 'ru', '41434103e0f30de4583dbd5d09e8fbdce6268ecc', 'Боевые знамёна')
  , ('287bb7dfc58feb5b', 'ru', '5ae95848f1654fdab6009b60a2e5515c472863d9', 'Ранг: <b><color={0}>{1}</color></b>')
  , ('e0ed74112b5d0272', 'ru', '4e02c65a3230ab22a99e846d79d4b4d46cd9901e', 'Рейтинговые 1v1 - 2v2 - турниры - косметика   <color=#666>v{0}</color>')
  , ('8e9f5c5b8f417285', 'ru', 'debb4916739eaee8059bb06b20b9668167be4310', 'Форма в рейтинге  <color={0}>{1}W-{2}L</color>')
  , ('1249b6f1e502b718', 'ru', '9010764c511b06ab2dc58692c34c829ba1fe04b3', 'Рейтинговые серии: {0}W / {1}L')
  , ('e316e9a339cb0454', 'ru', 'cce370d2f9781af0f85d591ccdfad1fe365a619f', 'Редкая')
  , ('948adf594528007a', 'ru', '6437b7bf655854909262d5f53fbe3bc7a6665b48', 'Рейтинг')
  , ('07b271831742817a', 'ru', 'dffa7f7a058fb0d2e1dd78e84871a125326455aa', 'История рейтинга  ({0} Elo)')
  , ('3142710df7c231f6', 'ru', 'e84f8f8af9ca7d8045a45616eeebdb971f4ba6d1', 'История рейтинга  ({0} Elo, {1} игр)')
  , ('b01fdd24bef99b35', 'ru', 'f6c0bd7cdb978fec1a5df08a6c5cea49360c6da7', 'Рейтинг: {0}   RD: {1}   Пик: {2}')
  , ('4dd589a0e595aa79', 'ru', 'c4097eedd44962a5de126d3bf379be9849404efc', 'Возрождается после поражения')
  , ('1f35f046ca078416', 'ru', '8944bac56fb71a84e3ae82e1b90e93e2f2b4bb1d', 'Красный курсор')
  , ('505d826bac112c1d', 'ru', '126a8e3bc4cc743f66d97a23baa4fbd94bca9cd1', 'Красное имя')
  , ('725c315d1c164ba0', 'ru', 'eb5c821caab94e7e985a15dfcbf1150b086c8ba2', 'Реген')
  , ('cb173826046b9943', 'ru', '8d4e4ef3ea5252ec5235e4b1dd463ae9c302422c', 'Завсегдатай')
  , ('e4b1a55872ab7dc2', 'ru', 'cce7155371fc26686b89c7452337d8419692f31e', 'Перезар.')
  , ('0348defe86351f3c', 'ru', '35360f9710e178438cf0beacd29bc2cf155be508', 'Заряжающий')
  , ('6fe9842db9d19141', 'ru', 'f8f842c1e0272e4182ba74a5e1e671b7f8a60f30', 'Имя в размере 130%.')
  , ('83f263b559925710', 'ru', '452eca3c01172368dcdcba51547a09396c0414a5', 'Имя в размере 160%.')
  , ('8746ab9f9b6503e4', 'ru', '1c9cc5f67a8641039f1e6e54ad1f7adec3a9c7c9', 'Имя в размере 80%.')
  , ('3f6dd33f95a50171', 'ru', 'cb3df1b14988aa02a85af24309f57e8594a845eb', 'Репорт не отправился - попробуй ещё раз через мгновение.')
  , ('6aefe5059d63d0e1', 'ru', '3e4d1a0220051e28866e692fcc1749e765c15125', 'Возвращает ванильную случайную смену палитр карты.')
  , ('145d5e6640ad6679', 'ru', '64beb88d5891e40c3adbadb8b1959b410db02d70', 'Цвет тела: насыщенный лесной зелёный.')
  , ('1ee9d7c98695afd0', 'ru', '969e7cedcc56832829613fa1b9a6909c8e2c57e4', 'Насыщенно-фиолетовые блоки на тусклом холодном фоне.')
  , ('06d95cefa1d007e6', 'ru', 'c3916b69a2b9f6d25258ad6c41417cea07f376f8', 'Клёпаный стальной шлем с Т-образной смотровой щелью.')
  , ('35ad337d5d3a9060', 'ru', '51ad0eae3f66ecd3c72bfac9373650513d6f6603', 'Роза')
  , ('0b37036b006bc7c2', 'ru', '2c16ea11eedff827b4e8ce41cee5f947d3418592', 'Королевский')
  , ('2b9dc3fb741aa589', 'ru', 'c085d0e3b3ec14e7c2c9f0463ff2c8a00dec591e', 'Королевский пурпур, перетекающий в бледный циан. Двухцветный градиент.')
  , ('319ab86ed9da45f2', 'ru', 'e13a8edd76d54551c7e4fbee3597e104900c26f7', 'Цвет тела: королевский фиолетовый.')
  , ('cde7ff6ff03c626f', 'ru', '2ba111743a13e4814bdbebc66f111af1605fcea4', 'Р а з р я д к а')
  , ('ba7370f908154504', 'ru', 'b36fbc6e8df68fb14280742f8b5bf0c0460a6fe0', 'Песок')
  , ('970796f2ee569bbc', 'ru', '52086129a3b5fc408aafd7614d3de4b7de05c35a', 'Сапфир')
  , ('61873d24740b083e', 'ru', '1207638e87127a3ee0ecce2ac2254ea4a7aa6c90', 'Алый')
  , ('f7c0cd90c321493a', 'ru', '3295f8d8261083d7f28652ae6b6758ca2369e347', 'Ход счёта')
  , ('03fd7046e9ef2d63', 'ru', 'd2ad76935ab2f3bb89bab2b67c98d79e2728d61e', 'Тряска камеры: <color={0}>{1}</color>')
  , ('8b51734bf0cceea4', 'ru', 'c2e5f7ff5a1b8a7c192fd6c5c49f8ff3a27c1d45', 'Цвет тела: жгучий электрический зелёный.')
  , ('371c04da36be20b2', 'ru', '6605cbf9da74dcde301ce970f5892a9c6f3697f1', 'Жгуче-лаймовое неоновое имя с мягким ореолом свечения. Имя видят все; игроки с модом видят и свечение.')
  , ('c8a7d841ea12ccc7', 'ru', '4e759bc7fb00171c1450a5abdb85e63a0d4be467', 'Самоирония — добродетель.')
  , ('c6e48e66ff28d8d5', 'ru', '3054ab05070e872c716ae126a3e99c407fdf4eb1', 'Отправить пинг')
  , ('56f4b006168b90b0', 'ru', '31b7561e9ca64f61bfd860c5d4af7ecf229dabfe', 'Серия {0}  против {1}  (идёт)')
  , ('694b7bbd6fe29463', 'ru', 'cbf8b1e91683087706a4ed11db627eb9673a72b2', 'Серия {0} {1}  против {2}')
  , ('2974b8e5c24bb499', 'ru', '5d92c2e8b2137b358d6e0cee27dc8213007e445f', 'Важность:')
  , ('e20ec9323e546397', 'ru', 'a35631709ba4e1f56d3e2be869b3d25dd947b31a', 'Переливается по спектру, пока ты двигаешься. Чистой воды выпендрёж.')
  , ('2ff4e59a6ac2fe45', 'ru', '98f69d719183344b0e6cf41bda85c41161fb7494', 'Сиена')
  , ('44a663da8c3a7fdd', 'ru', '393bd9e94e9108ea7fcbcb67d93d3269709ea07b', 'Запишись, чтобы открыть форс-старт')
  , ('f522e76707a4e0d9', 'ru', 'b7152342a267362add3c0d7f69f720f7a9c76c9e', 'Размер')
  , ('23ba5ae4bf44caf7', 'ru', '237ffaf765bbff962746c4fd0c785881512d1eff', 'Пропускать MenuControllerHandler.Update во время активного матча.')
  , ('e23866b89558a941', 'ru', 'b3d97fd6dece388a968e367f3ac4b9e64d739f52', 'Sky')
  , ('5b1fa8823faaa4dd', 'ru', '26d7b218c9b5641b37dfddc13b955184f3ce868f', 'Сланец')
  , ('567890efd6eb4e17', 'ru', 'b0476d817e62b78a6d6b13910299b1a6c90d3d83', 'Цвет тела: строгий чёрный.')
  , ('811bf05184f39e45', 'ru', 'a8e56ef9b0223468ffe7a2e5ba21d538d23afc66', 'КаПиТеЛь')
  , ('9237062066f5d776', 'ru', 'bb79f3faedd4b8feda0906367e3938079bb3cd8c', 'Имя поменьше')
  , ('21a19e853e62a77b', 'ru', '7b3d0b443ce4a8405de90ed439b33999c90d489e', 'Дымок')
  , ('be93e1ed6ec90fec', 'ru', '2081d06ecb8f68cbf79e9de820f81f7f82fa4625', 'Снайпер')
  , ('91d61c894d41c995', 'ru', 'a3ad936a7ceda44469920ce62fe5947bde0aa040', 'Медаль снайпера')
  , ('5def38b6c29f4d9c', 'ru', 'f9d59a6ea8c756838f928f0d95c9d34e4d99db37', 'Шлем-банка')
  , ('fcdaa994cb09a325', 'ru', 'ce8d0da33206ab07f9dad187d28ae162ccc22b29', 'Мягкий сланец')
  , ('6df0149175e82e19', 'ru', '2394bba21d20d3da5d703014c5a214f15bcef2be', 'Мягкая пастельная лаванда — минимум контраста.')
  , ('3e776304a375d625', 'ru', '1b7253a3591f76e461aebe6335506a201a17601e', 'Цвет тела: мягкий пастельный фиолетовый.')
  , ('9d9a02388f682516', 'ru', 'f7bce6256e4c4cbfffd0c61e2708265490027f17', 'Цвет тела: нежно-розовый.')
  , ('658d71d742121ed2', 'ru', '3d40c20821471e017a6f118ca7911fbcea797946', 'Таблица соло')
  , ('321d3d0d79d4c6db', 'ru', '65cfa78989387ca19f18d1d54af0d45dfb8fd9ee', 'Владыка')
  , ('093cb8d328f0f8c8', 'ru', '42724976abf218f52fcf92c452432ec282de21a7', 'Soviet')
  , ('4de9de6e1f656ebe', 'ru', '45bfc012fbf82490776101b9c6b63887c8a0fb1d', 'Искры')
  , ('94f1cace756e2725', 'ru', 'e0ad3ab875f57eac75ebd47534939215a9b96daa', 'Призрак')
  , ('64f50d41089a0db6', 'ru', 'a6a7b70436b1cb9914649ca0f29a787099ee1c15', 'Жуткие попрыгунчики')
  , ('74892e8d7d529b3c', 'ru', '2bde101117a83786a9fe359d813c1badf4a6b2ee', 'Разброс')
  , ('f0f169d5182d3441', 'ru', '1c0cb5239f106c2576fc15b5249d073c7cf406e0', 'Звёздные наушники')
  , ('67639960c926c58e', 'ru', 'f2698c4901757c1e713246a5a58dd359698f9f54', 'Звездоворот')
  , ('608561ba53ff573f', 'ru', '6134bd38cec65de46eba3419acc1c714ffe1cd20', 'Звёзды в глазах')
  , ('e8f48481d4bd7c9c', 'ru', 'e3c95802a4529c0f536dbb1eaf80bab813a2d5c0', 'Старт: <color=#FFDE88>{0}</color>')
  , ('854774247858c849', 'ru', '084282a69463a804d2336837e4f92bd0b0d0160c', 'Статус: <color=#88FF88>Разрешено</color> - данные матчей и привязка активны.')
  , ('3756e6cfebef3865', 'ru', '1701a52158cb5b8eee96db12e0453dc68ee4b165', 'Статус: <color=#DDDD66>Не задано</color> - запрос согласия появится при следующем запуске.')
  , ('ac2ac9790f0283fc', 'ru', '593dddce7c4ef2c47cc34038dd0fc0cc18c8e576', 'Статус: <color=#FF9966>Отклонено</color> - мод работает оффлайн. Данные не покидают твой компьютер.')
  , ('c181f97737843bb1', 'ru', '79144fb22b8fe57dc5e4025fa2451b9c9fbe973a', 'Зашитая ухмылка')
  , ('8c303afe63579dd8', 'ru', 'e6dc9396aa17a023a695be860dd2f06ed4399346', 'Грозовой нимб')
  , ('7d6b3939f985247d', 'ru', 'f9ae58aa354c851627202a2bbae82b33dd0da9c6', 'Зачёркивание')
  , ('f0ca80932eaf824e', 'ru', '78d736bb8b31ffc0d1147e4a8bb2bbb2bf209874', 'Зачёркивает твоё имя. Совместимо с другими стилями имени.')
  , ('d65e985d67ed0fe9', 'ru', 'e41871fcab992523ffd460e45c652811a5aa37cb', 'Null-защита стана')
  , ('d1444d8ccb532eed', 'ru', '702282ee3b8e83ab98bab528edd90b1983df3f06', 'Null-защита StunPlayer — убирает спам NRE, когда игрока уничтожают во время стана.')
  , ('476093e331464f11', 'ru', '2dacf65959849884a011f36f76a04eebea94c5ea', 'Отправить')
  , ('c76ede26fcd816e4', 'ru', '1ca00033fee3d4e5ee3de55b2d380368d9310d48', 'Отправить репорт')
  , ('9b898dc5487d84cd', 'ru', '46a1a6919d196b4d95a74a37cc19f2ed4c66d0eb', 'Отправка...')
  , ('1d212540835c92ae', 'ru', 'dd5499d7f0a2d38242360148c069aa29f121ccbb', 'Солнечный нимб')
  , ('60bbbc527e3744da', 'ru', '181bcd5760fd32163554c899301a30b2cd381cf4', 'Закат')
  , ('8fc96ffa03aaafbe', 'ru', 'e6e56698abc25872406e861b0aa5e10015632ae8', 'Градиент: закат')
  , ('7fbedacc6efea800', 'ru', '13b3faceb8360fa55fb94098c6b1e5b6b8d19f27', 'Глушить NRE RayHitBulletSound от уничтоженных родителей.')
  , ('c7a5a26638393134', 'ru', '868d0b7d0ffa614abcff7ba14ad2d6bde86a1b2c', 'Глушить NRE ScreenEdgeBounce от уничтоженных пуль.')
  , ('6ebdd285f3b71ef8', 'ru', 'f53f0af5f87f3ba660422807a1435727faeed72b', 'Пот — это просто опыт в жидкой форме.')
  , ('62945646ff725873', 'ru', '0c95f4a83a19eb2e8965d24c44c42df5b61d5388', 'Потный')
  , ('6028e9eac2094a5a', 'ru', '72ddd2b619af6d6a73febf80f7fcad22495498cd', 'Sweden')
  , ('cab4937719a22718', 'ru', '133552ebfbcce8310f8920695422699d5256bac9', 'Загар')
  , ('247786047e006128', 'ru', '0ba4d1aee6f233efc1f3b78141b4af7d08b86c3c', 'Танк')
  , ('abd355e13a15e46d', 'ru', 'f9fb8665cb51f149f63f06a976a3324713219468', 'Target Bounce-мейн')
  , ('50ac155d36ece430', 'ru', '5f6aa78e382c01b370e8b343a9c1b5a2b5fa6705', 'Рваный плащ')
  , ('3b01b61b340a5223', 'ru', '619a16e83766383c2d21a829f80bd5d01c671c25', 'Драные багровые крылья летучей мыши прямиком из преисподней. Душа продаётся отдельно.')
  , ('eb382d1678858a9c', 'ru', 'df0ad373b7ff60d6a8987458fb00c1e4832ef605', 'Бирюза')
  , ('b234d0122bbaa63f', 'ru', '117e0234bc721029ca23bc4468eaaf69939a267a', 'Спасибо, что тестил мод в бете. Бесплатно; исчезнет после завершения беты.')
  , ('e18bda3d30d526af', 'ru', '526a09199b53f93b3d5427114172a2671c6cd74e', 'Терновый венец')
  , ('12f7c7e33d999282', 'ru', 'cb7c351d80fb7f2eb5d656664b0709b7a3bd0416', 'Три сферы чистой энергии на орбите вокруг тебя. АНИМИРОВАНО.')
  , ('1271aee114daa4c4', 'ru', '5bd44ebe63cd3b9445ca759f970513d78b28a61c', 'Тир')
  , ('e571d7422af03bcb', 'ru', '0ce8e5dac8f6f61d3eba42d016f55230f093a2c7', 'Титан')
  , ('190526c2629dbea2', 'ru', 'e5f48c13ee118dc3dacd8e536d53a9d26f5301df', 'Вершина пищевой цепи')
  , ('f734b208caa4f204', 'ru', 'c15771fc77a45dae33911c04bb171e6f49fa33cb', 'Следопыт')
  , ('9c494c7f25abb2c3', 'ru', '502598c638643dedcad27c187b7569ebb08e4615', 'Цвета транс-флага с искрящимися частицами.')
  , ('6f4efddd4bda07b6', 'ru', '1599ddb3455a45ccc59a3fac422049947650292b', 'Tride')
  , ('0cab6cacbbc851b9', 'ru', '0c06f367e6f129656bdd8dd841192a6f4d2dcb57', 'Трайхард')
  , ('b35fb4ad612dfe48', 'ru', '05622e2e52c968bbde79af9c43a01a69c348ffd0', 'Старается. Очень.')
  , ('cd5edd2dfb625384', 'ru', '6caad4cda78d3c6ad47660162f70accf6748494f', 'Сумерки')
  , ('61bb06cc51843ce1', 'ru', 'a9b6b056b13b501af43880063da2ed0de4059f24', 'Два скрещённых боевых штандарта. За дело!')
  , ('fbbce02111ccebf0', 'ru', 'fc31465be9e079dfb54cb2d55d591edc83fd4ceb', 'Два светящихся зелёных усика. Веди меня к своему лидеру.')
  , ('66b1bfa0c7da43ad', 'ru', '1255b7d12b59020bccf9dffde6b463bb84d3eedb', 'Умбра')
  , ('55d6340624531595', 'ru', '630e0b25835dd27620dc4ef0c6b4d0300696b62f', 'Необычная')
  , ('ef8b357138a3ef69', 'ru', '39773aa3efa19090c918baedac1fe737dea25b92', 'Подчёркивание')
  , ('3c3c5f6eac20881b', 'ru', '1b1d817f13affedf2bc1117a61c3b4ca949b2e62', 'Unity / Игра')
  , ('b8726a2e1acd9dfe', 'ru', '1d4d43cc6f3a833e0340a0d1794b6d7b9958657e', 'Применить')
  , ('dbcea9ac17806e03', 'ru', '67e7a92881ae1200be8d73f68942f37d8b841edd', 'ГОЛОСОВАНИЕ / ЗАПИСЬ')
  , ('e222892ca8d0f4f1', 'ru', '50c8e9195e5ecd5791a33f4dc54310bbea98a77f', 'Бархат')
  , ('3950da75a154598a', 'ru', '9a39b423a562fe4943decb524e92851ad0c94a4f', 'Ярко-оранжевое неоновое имя с мягким ореолом свечения. Имя видят все; игроки с модом видят и свечение.')
  , ('2dca86b596943f57', 'ru', '207c7c00630b836d3afb46848bdb24a92023331d', 'Пустота')
  , ('4e8fc7c0e6288df8', 'ru', 'ec5f447f3fa0edd8c92f7101ef7f729f6466b96d', 'Рябь пустоты')
  , ('6023f2dc69b9be58', 'ru', 'd44941df851133e25121f54f10ddffbc79ed5ed4', 'Залп пустоты')
  , ('e59b71033ad70521', 'ru', 'f7585ab975d96d0a37f8cb0b66d945ba600cafd2', 'Ждём подключения всех 3 игроков — подожди...')
  , ('1a75ea9cccafc189', 'ru', 'dbe4d86fb51352879c5bc4e9cb3c5823c4ee486c', 'Цвет тела: тёплый кораллово-оранжевый.')
  , ('dd76e64b87e0aa28', 'ru', '4700ad8692d08573598fbb4950115440b6c1c7ac', 'Тёплая палитра: крем + загар.')
  , ('c198ec18f335a171', 'ru', '427a3cd1255e088f822589a37ac6636241598de9', 'Тёплые тона пустынного песка.')
  , ('05a9b2435b114fb5', 'ru', 'c148920398c05ff36e4fcbd84d182dc5c3cc1650', 'Цвет тела: тёплое медовое золото.')
  , ('e5e3095c005a72cc', 'ru', '8b99503fef5328110821262702556cf11f1dc23b', 'Тёплые оранжевые блоки на закатном фоне.')
  , ('b25a2fb5ec8a68e0', 'ru', '7afa3cb197e2dfdfb6813dd41d7d5de2c47e7c19', 'Белый курсор')
  , ('d3932de27d2daea3', 'ru', 'c0365b235944850932d02480035816faa8e51970', 'Windup')
  , ('403c28519696a825', 'ru', '7bef0c61f63c0bafbdd397fcdb4fd5388041c31f', 'Windup-мейн')
  , ('8f7d96d5e823b55f', 'ru', '1d50bf1d8b44e075c6690ac4d150713976be836d', 'Верхняя сетка')
  , ('0da8c2b28b8377a5', 'ru', 'b6c015d12e1b59bd78fb246985e37730e38521f8', 'Победы')
  , ('be9560e3832c8bb9', 'ru', '1b48a60b0d625b75c26ce2cf730ff892e74f4114', 'Побеждает без единого выстрела')
  , ('8c0133547ab53ad0', 'ru', '05cb4b22604d22cab8e2fae50a1050c33fa3521a', 'Мудрость не по годам.')
  , ('c7c6e4fba9dcb3c6', 'ru', '6f3c2cb5e1f2e4a068c8389405e3e496e4f9ef97', 'Струйки серого дыма тянутся от твоего тела.')
  , ('28f008bfef758548', 'ru', '504f4643d13463af8dc37482c5cbe0acc4a75d6b', 'Пряди живой тени венчают твою голову. АНИМИРОВАНО.')
  , ('e1dbf69f1828cbc7', 'ru', 'bca16e3079936dcb4198b1cfc3ffba6610a7e47d', 'Носят те, кто покорил эту гору.')
  , ('695949eccf2a3eb4', 'ru', 'c99d12a2a8f36120e482c0fc40e974443dba78bb', 'Делает имя <b>жирным</b>. Совместимо с другими стилями имени.')
  , ('ada862d6c0f469e7', 'ru', '609dfb565c93a98b2b30104355b3a4232da847f4', 'Пишет имя <i>курсивом</i>. Совместимо с другими стилями имени.')
  , ('37343c87c3b2e4f5', 'ru', 'b8c7196ddeefdf59f5ef6da9406d00a866271c3a', 'Имя XL')
  , ('dcc9b37fdb87b814', 'ru', 'ee87adceb5e62cb4131c19198f5051250f0d91c2', 'Жёлтый курсор')
  , ('5ef0b9cf34f0aff2', 'ru', '89ffbc49c5cd513fb7f444af55b747d977cda309', 'Инь и ян')
  , ('a8064a9ac9627e7d', 'ru', 'bfcb6f0bdfeaee7d87fac66f8d55ddb559b17ec6', 'Ты хотя бы заходишь.')
  , ('64e8a47541007536', 'ru', '2bbe77e5794acb118c3f9cadfd5a8b5130e9a46d', 'Имя перетекает из тёплого янтаря в глубокий розовый.')
  , ('bd97142ff2899914', 'ru', '932d39ba6afffe50ecdb9d96f8e9953fc8738c51', 'Твой штраф за неявку: <color=#FFCC44>{0}%</color>')
  , ('9c9228360f345cff', 'ru', 'f8acd4ea8b53c8e63f98ea885d48befcc946b1e1', 'Твои пики')
  , ('698827c82f5162bc', 'ru', '07165fcd109bbf9198d1f39c2f4d6149df178a3c', 'Ваши места:  <color=#FFE580>1stx{0}</color>  <color=#C8C8C8>2ndx{1}</color>  <color=#D4894A>3rdx{2}</color>  <color=#888>(сыграно {3})</color>')
  , ('149bf365c330d13c', 'ru', '8833ad12d379ff3fa61c32bb9e943d7b06b5856d', 'за ДУО (с {0}) против {1}')
  , ('0aa6a16a1673de73', 'ru', '1bd88366f34ba7f14fb904e5ed1646c4644328cc', 'за СОЛО против {0} + {1}')
  , ('0cd2498ace5eb5b1', 'ru', 'd317f861f54f6c4a8fd4dac6ff0efcea37ec2e1d', 'кастом-лобби 2v2')
  , ('bd6d31d0b058348d', 'ru', '16ef1d431149d2a08902873a443dbbe54c85cddb', 'дуо')
  , ('6c3530c8c280b3ff', 'ru', '11ef3b2ae60a4251cd73fef09e480569d29ecdfd', 'сейчас: <b>{0}</b>')
  , ('1e0ef297c1e3d8b3', 'ru', 'f9c0c29d091d50a9086354e063e47954c59e1b90', 'один цвет за раз')
  , ('8cad63c636cdcf6f', 'ru', 'ff83a9a220be04b92113dda6c44401123dc40b01', 'один шрифт за раз')
  , ('3bd7fbbab2fca8f1', 'ru', '35a7375e3bb813dfde5e763661731fac75a6e0d2', 'одно свечение за раз - только у игроков с модом')
  , ('e165e5ae840a62fb', 'ru', '7ab9c8362a5abfb2e9bfcbaa02d5a3f8fc771179', 'один размер за раз')
  , ('8e4bd5a8e9eec6ae', 'ru', '0570f3e02cc6e225a109dc75f565ed8681b8252e', 'одна гарнитура за раз - только у игроков с модом')
  , ('b8adf2986f373097', 'ru', 'bea1572501beca2ebef3a391a800868da0c570a0', 'суммируется')
  , ('e6066223b0b305c1', 'ru', '50d8b4a941c26b89482c94ab324b5a274f9ced66', 'неизвестно')
  , ('c4abfe07405d45b5', 'ru', '4902794a18b07e5f86e7f33d4029788b2034de4f', 'неизвестный путь')
  , ('eb897bb9be7c79b8', 'ru', 'e1a6f0b6f73a57a8b3ee30419e28f6cb95143908', 'без лимита')
  , ('dc6588862dd02f39', 'ru', '6aefdf8cf3774a76db4f21466926eaa31e1bf15c', '{0} <b>победил</b> {1}-{2}')
  , ('23f3e8961d9a6d6d', 'ru', '5519c24b363f6799a1bfaab8e067c25e0eca51e3', '{0} elo')
  , ('f175d5d9643750aa', 'ru', 'cceed712efad9af4f4ef2b04ce0b8d5a66f086ce', '{0} игр    {1}W - {2}L    {3}')
  , ('563f328fb4d4aa1d', 'ru', '60af1d144ac434a965bf13bb977aa7aadb4bb8d3', '{0} полуочков')
  , ('256d2b14212ba5d4', 'ru', '1ab5b75b0bfcc6c62c111b526749c2b8fdbd47ed', 'Предметов: {0}, копий в обороте: {1}.')
  , ('2aa987f867bde0fc', 'ru', 'da5d5190f132c40421541404bfbc922fa7b4115e', '{0} матчей ({1}W / {2}L)  WR: {3}%')
  , ('c9cc67272a1c866f', 'ru', 'ce9deb48ef00eef45a5b3b38a2161430725ea158', 'осталось {0} из {1}')
  , ('3f3e4849188126ca', 'ru', '1b349c2c85da7aa6f6fce0e2315fe90c1db905ef', '{0} из {1} игроков')
  , ('2ef8c7b3a201cae0', 'ru', 'a24642bb9528015ac471a91a10e938a1cbe5d461', '{0} стартовых раздач')
  , ('2eb242866aaaf376', 'ru', '65d4768dbb287c5c86628ac8189b2366ee6700ab', '{0} игроков в рейтинге')
  , ('8652c96055f60c8c', 'ru', '2968d53cd798cf7fb980789d461ea11b3a0d2aa4', '{0}: <color=#888>(не назначено)</color>')
  , ('b3e2957858fb3018', 'ru', '22d79b7411b323a43df61650426791552bdec4ae', '{0}: <color=#FF9966>ВЫКЛ</color>')
  -- wave 4b: 14 keys unlocked by the Aug-3 extractor token fix + review-round templates.
  , ('e4fb9840494d3adc', 'es', '01b9362930e07bb2a94346903e16d28f961c65ba', '<color=#777>{0} de daño recibido · {1} bloqueos exitosos · marcas = puntos anotados</color>')
  , ('e4fb9840494d3adc', 'ru', '01b9362930e07bb2a94346903e16d28f961c65ba', '<color=#777>{0} урона получено · {1} успешных блоков · метки = очки</color>')
  , ('4365d9ddba0624aa', 'es', '3635e1da1b47b8c6773060fc109076df6934101a', '<color=#777>{0} disparos · {1} aciertos · {2:F0}% · marcas = puntos anotados</color>')
  , ('4365d9ddba0624aa', 'ru', '3635e1da1b47b8c6773060fc109076df6934101a', '<color=#777>{0} выстрелов · {1} попаданий · {2:F0}% · метки = очки</color>')
  , ('30b450ba41d7ad92', 'es', '92738744d5b41f06fd27010c32808fb496c82066', '<color=#888>+carta</color>')
  , ('30b450ba41d7ad92', 'ru', '92738744d5b41f06fd27010c32808fb496c82066', '<color=#888>+карта</color>')
  , ('66051d24143f7b65', 'es', 'e1cc9ab4a908fe9ada26a951e5e130dda9e6eef0', '<color=#CCCCCC>Bloqueo — <color={1}>{0}</color></color>  <color={2}>daño recibido</color> <color=#888>·</color> <color={3}>bloqueos</color>')
  , ('66051d24143f7b65', 'ru', 'e1cc9ab4a908fe9ada26a951e5e130dda9e6eef0', '<color=#CCCCCC>Блок — <color={1}>{0}</color></color>  <color={2}>урон получен</color> <color=#888>·</color> <color={3}>блоки</color>')
  , ('7a7823c2087f2573', 'es', 'a42b5210eecd90c46304776157124b18a67cc340', '<color=#CCCCCC>FPS durante la partida</color>  <color=#99B3E6>{0}</color>')
  , ('7a7823c2087f2573', 'ru', 'a42b5210eecd90c46304776157124b18a67cc340', '<color=#CCCCCC>FPS за матч</color>  <color=#99B3E6>{0}</color>')
  , ('a0004b0dedd9eb35', 'es', '033ba4e6b0c113f2a8b8d2edd374e66ae20e3a6d', '<color=#CCCCCC>Acierto — <color={1}>{0}</color></color>  <color={2}>disparos</color> <color=#888>·</color> <color={3}>aciertos</color>')
  , ('a0004b0dedd9eb35', 'ru', '033ba4e6b0c113f2a8b8d2edd374e66ae20e3a6d', '<color=#CCCCCC>Попадания — <color={1}>{0}</color></color>  <color={2}>выстрелы</color> <color=#888>·</color> <color={3}>попадания</color>')
  , ('c52cca2c773022ae', 'es', '4ec13493affca1bdbebebe9038ae5d87d1b035f2', '<color=#CCCCCC>Latencia (ms) durante la partida</color>  <color=#99B3E6>{0}</color>')
  , ('c52cca2c773022ae', 'ru', '4ec13493affca1bdbebebe9038ae5d87d1b035f2', '<color=#CCCCCC>Задержка (мс) за матч</color>  <color=#99B3E6>{0}</color>')
  , ('f101e7dfe9aebb16', 'es', 'e831ea71c515905031066ca0811cc3514f4b19eb', '<size=80%><color=#7CFF7C>(tú)</color></size>')
  , ('f101e7dfe9aebb16', 'ru', 'e831ea71c515905031066ca0811cc3514f4b19eb', '<size=80%><color=#7CFF7C>(ты)</color></size>')
  , ('558fc3496ae9d9c9', 'es', '689cd25e4f221a18734b96f3bf83f166c4a7115a', 'Día/Mes/Año')
  , ('558fc3496ae9d9c9', 'ru', '689cd25e4f221a18734b96f3bf83f166c4a7115a', 'День/Месяц/Год')
  , ('14796e67387865fd', 'es', '67cc0b8a50586de358efae7157a8c921a6fa5e8f', 'Él/él')
  , ('14796e67387865fd', 'ru', '67cc0b8a50586de358efae7157a8c921a6fa5e8f', 'Он/его')
  , ('625836003d87ac6f', 'es', '444a011d29f4155587f4e755e604c1fa955899e9', 'Ella/ella')
  , ('625836003d87ac6f', 'ru', '444a011d29f4155587f4e755e604c1fa955899e9', 'Она/её')
  , ('288dbb0fdf1491bc', 'es', '2a94b32a35c314d000ef6cd80beca279a0e2067b', 'Elle/elle')
  , ('288dbb0fdf1491bc', 'ru', '2a94b32a35c314d000ef6cd80beca279a0e2067b', 'Они/их')
  , ('1256b14cad0e0458', 'es', '4eb88001f59d0dff9c3b238ba04dce6e865ae9c1', 'Año/Mes/Día')
  , ('1256b14cad0e0458', 'ru', '4eb88001f59d0dff9c3b238ba04dce6e865ae9c1', 'Год/Месяц/День')
  , ('65643a73af1222dd', 'es', '289751437f860828c589bd3ecdcf0c5d29fe8c9d', 'mismas cartas')
  , ('65643a73af1222dd', 'ru', '289751437f860828c589bd3ecdcf0c5d29fe8c9d', 'общие карты')
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
  IF seeded < 2466 THEN
    RAISE NOTICE 'migration 184: % of 2466 live seed pairs are MISSING - run tools/i18n_sync_keys.py, then re-run this migration', 2466 - seeded;
  END IF;
END $$;
