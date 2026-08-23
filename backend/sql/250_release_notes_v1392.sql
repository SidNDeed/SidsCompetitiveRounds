-- 250: v1.39.2 release notes, all five locales.
-- The admin POST endpoint is an idempotent upsert into release_notes_i18n;
-- this migration performs the identical write through the migration channel
-- because the VM seat's AdminSecret still does not verify (403, learning
-- #406). en is the human source (the GitHub release body); es/ru/uk/sv are
-- machine translations reviewed against the in-game catalogue terminology.

BEGIN;

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.39.2', 'en', '', $rn1392en$# v1.39.2

Nine dark map skins with embers, rain and stars, ten new gradient name styles, five community cosmetics, a translation-portal fix, and a round of ranked/economy changes.

## Map skins — the Night pack

- **Forest Fire** (embers), **Moonlit** (stars), **Eclipse**, **Underworld** (embers), **Night City** (city lights), **Night Park**, **Rainy Day** (rain), **Midnight**, **Blood Moon** (red stars). All in the Blackwood family: pitch-black, dark-brown and deep-red skies with darker walls. 75g, or 150g for the six with an ambient effect.
- The effects are drawn behind the map and never in front of gameplay; the Animated Cosmetics toggle switches them off.

## Name styles

- Ten new gradients (1500g): Fade, Earth, Orchid, Sapphire, Emerald, Steel, Ash, Royal, Blood, Twilight.

## Community cosmetics

- Shock Shades, Cat Mouth, Cat Eyes, The Challenger and Goober are in the Shop; Seasonal Spring's re-approved size is live.

## Translation portal

- "Session expired" on every open for players whose game and browser reach the server through different network addresses (Cloudflare WARP, privacy relays, split-tunnel VPNs) is fixed: the session now binds to the first browser that uses it, and a genuine address mismatch is reported as such.
- 53 new keys with machine translations in Spanish, Russian, Ukrainian and Swedish — translators can refine them in the portal.

## Ranked and economy

- Glicko-2 volatility (tau) raised 0.5 → 0.6 in every mode; FFA previously used a different value.
- Heavy-favourite bet wins (odds of 1.5× or less) now send 20% of the **profit** — never the stake — to the fighter or team you backed. Quotes at bet time already show the net amount. (Community idea.)
- Match history can be searched by opponent name — there is a search box in My Stats.

## Fixes

- Rating changes show decimals for small changes consistently on every screen.
- Custom player colour could be missing on the card-pick body in room-code games.
- Looping map sounds (saws, Abyssal Countdown) could carry past their round.
- Broadcast seat: a render cap while the director is active and a single FPS governor, so a player's own frame-rate setting can no longer be lost; the rotation holds each game at least 5 minutes and waits for a break in the fighting before switching.
$rn1392en$, 'human', NULL)
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.39.2', 'es', '', $rn1392es$# v1.39.2

Nueve skins de mapa oscuras con brasas, lluvia y estrellas, diez nuevos estilos de nombre degradados, cinco cosméticos de la comunidad, un arreglo del portal de traducción y una ronda de cambios de ranked y economía.

## Skins de mapa — el pack Nocturno

- **Forest Fire** (brasas), **Moonlit** (estrellas), **Eclipse**, **Underworld** (brasas), **Night City** (luces de ciudad), **Night Park**, **Rainy Day** (lluvia), **Midnight**, **Blood Moon** (estrellas rojas). Todas de la familia de Blackwood: cielos negro absoluto, marrón oscuro y rojo profundo con paredes más oscuras. 75g, o 150g las seis con efecto ambiental.
- Los efectos se dibujan detrás del mapa y nunca delante del juego; el ajuste Cosméticos animados los desactiva.

## Estilos de nombre

- Diez degradados nuevos (1500g): Fade, Earth, Orchid, Sapphire, Emerald, Steel, Ash, Royal, Blood, Twilight.

## Cosméticos de la comunidad

- Shock Shades, Cat Mouth, Cat Eyes, The Challenger y Goober ya están en la Tienda; el tamaño re-aprobado de Seasonal Spring está activo.

## Portal de traducción

- Arreglado el «Sesión caducada» al abrir el portal para quienes llegan al servidor con direcciones de red distintas entre el juego y el navegador (Cloudflare WARP, relés de privacidad, VPN con túnel dividido): la sesión ahora se vincula al primer navegador que la usa, y un desajuste real de dirección se informa como tal.
- 53 claves nuevas con traducciones automáticas al español, ruso, ucraniano y sueco — los traductores pueden pulirlas en el portal.

## Ranked y economía

- Volatilidad Glicko-2 (tau) subida de 0.5 a 0.6 en todos los modos; FFA usaba un valor distinto.
- Las apuestas ganadas a un gran favorito (cuota de 1.5x o menos) envían ahora el 20 % de la **ganancia** — nunca de la apuesta — al luchador o equipo que apoyaste. La cuota mostrada al apostar ya refleja el neto. (Idea de la comunidad.)
- El historial de partidas se puede buscar por nombre del rival — hay un cuadro de búsqueda en Mis estadísticas.

## Arreglos

- Los cambios de rating muestran decimales para cambios pequeños de forma coherente en todas las pantallas.
- El color de jugador personalizado podía faltar en el cuerpo de la elección de cartas en salas con código.
- Los sonidos en bucle del mapa (sierras, Abyssal Countdown) podían continuar más allá de su ronda.
- Asiento de retransmisión: límite de fotogramas con el director activo y un único gobernador de FPS, para que el ajuste de fotogramas del propio jugador ya no pueda perderse; la rotación mantiene cada partida al menos 5 minutos y espera una pausa en el combate antes de cambiar.
$rn1392es$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.39.2', 'ru', '', $rn1392ru$# v1.39.2

Девять тёмных скинов карт с угольками, дождём и звёздами, десять новых градиентных стилей имени, пять косметических предметов от сообщества, исправление портала переводов и ряд изменений рейтинга и экономики.

## Скины карт — Ночной набор

- **Forest Fire** (угольки), **Moonlit** (звёзды), **Eclipse**, **Underworld** (угольки), **Night City** (огни города), **Night Park**, **Rainy Day** (дождь), **Midnight**, **Blood Moon** (красные звёзды). Все в духе Blackwood: кромешно-чёрное, тёмно-коричневое и глубоко-красное небо с более тёмными стенами. 75g, а шесть скинов с эффектом — 150g.
- Эффекты рисуются позади карты и никогда поверх игры; переключатель «Анимированная косметика» их отключает.

## Стили имени

- Десять новых градиентов (1500g): Fade, Earth, Orchid, Sapphire, Emerald, Steel, Ash, Royal, Blood, Twilight.

## Косметика от сообщества

- Shock Shades, Cat Mouth, Cat Eyes, The Challenger и Goober появились в Магазине; повторно одобренный размер Seasonal Spring включён.

## Портал переводов

- Исправлено «Сессия истекла» при каждом открытии портала у игроков, чьи игра и браузер выходят в сеть с разных адресов (Cloudflare WARP, релеи приватности, VPN с раздельным туннелем): сессия теперь привязывается к первому браузеру, который её использует, а настоящее несовпадение адресов сообщается как таковое.
- 53 новых ключа с машинными переводами на испанский, русский, украинский и шведский — переводчики могут доработать их в портале.

## Рейтинг и экономика

- Волатильность Glicko-2 (tau) повышена с 0.5 до 0.6 во всех режимах; в FFA раньше использовалось другое значение.
- Выигрышные ставки на явного фаворита (коэффициент 1.5x и ниже) теперь отдают 20 % **прибыли** — никогда не ставки — бойцу или команде, за которых вы ставили. Котировка при ставке уже показывает чистую сумму. (Идея сообщества.)
- Историю матчей можно искать по имени соперника — поле поиска в «Моя статистика».

## Исправления

- Изменения рейтинга показывают десятичные дроби для малых изменений одинаково на всех экранах.
- Пользовательский цвет игрока мог отсутствовать на теле при выборе карт в комнатах по коду.
- Зацикленные звуки карты (пилы, Abyssal Countdown) могли продолжаться после своего раунда.
- Место трансляции: ограничение кадров при активном директоре и единый регулятор FPS, чтобы собственная настройка частоты кадров игрока больше не терялась; ротация держит каждую игру не меньше 5 минут и ждёт паузы в бою перед переключением.
$rn1392ru$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.39.2', 'uk', '', $rn1392uk$# v1.39.2

Дев'ять темних скінів карт із жаринками, дощем і зірками, десять нових градієнтних стилів імені, п'ять косметичних предметів від спільноти, виправлення порталу перекладів і низка змін рейтингу та економіки.

## Скіни карт — Нічний набір

- **Forest Fire** (жаринки), **Moonlit** (зірки), **Eclipse**, **Underworld** (жаринки), **Night City** (вогні міста), **Night Park**, **Rainy Day** (дощ), **Midnight**, **Blood Moon** (червоні зірки). Усі в дусі Blackwood: непроглядно-чорне, темно-коричневе та глибоко-червоне небо з темнішими стінами. 75g, а шість скінів з ефектом — 150g.
- Ефекти малюються позаду карти й ніколи поверх гри; перемикач «Анімована косметика» їх вимикає.

## Стилі імені

- Десять нових градієнтів (1500g): Fade, Earth, Orchid, Sapphire, Emerald, Steel, Ash, Royal, Blood, Twilight.

## Косметика від спільноти

- Shock Shades, Cat Mouth, Cat Eyes, The Challenger та Goober з'явилися в Крамниці; повторно схвалений розмір Seasonal Spring увімкнено.

## Портал перекладів

- Виправлено «Сесія закінчилася» під час кожного відкриття порталу у гравців, чиї гра та браузер виходять у мережу з різних адрес (Cloudflare WARP, релеї приватності, VPN з роздільним тунелем): сесія тепер прив'язується до першого браузера, який її використовує, а справжня невідповідність адрес повідомляється як така.
- 53 нові ключі з машинними перекладами іспанською, російською, українською та шведською — перекладачі можуть доопрацювати їх у порталі.

## Рейтинг та економіка

- Волатильність Glicko-2 (tau) підвищено з 0.5 до 0.6 в усіх режимах; у FFA раніше використовувалося інше значення.
- Виграшні ставки на явного фаворита (коефіцієнт 1.5x і нижче) тепер віддають 20 % **прибутку** — ніколи не ставки — бійцю чи команді, за яких ви ставили. Котирування при ставці вже показує чисту суму. (Ідея спільноти.)
- Історію матчів можна шукати за іменем суперника — поле пошуку в «Моя статистика».

## Виправлення

- Зміни рейтингу показують десяткові дроби для малих змін однаково на всіх екранах.
- Користувацький колір гравця міг бути відсутнім на тілі під час вибору карт у кімнатах за кодом.
- Зациклені звуки карти (пилки, Abyssal Countdown) могли тривати після свого раунду.
- Місце трансляції: обмеження кадрів при активному директорі та єдиний регулятор FPS, щоб власне налаштування частоти кадрів гравця більше не втрачалося; ротація тримає кожну гру щонайменше 5 хвилин і чекає паузи в бою перед перемиканням.
$rn1392uk$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

INSERT INTO release_notes_i18n (tag, language_code, title, body, source, translated_by)
VALUES ('v1.39.2', 'sv', '', $rn1392sv$# v1.39.2

Nio mörka kartskins med glöd, regn och stjärnor, tio nya gradientstilar för namn, fem kosmetiska föremål från communityn, en fix för översättningsportalen och en omgång ändringar i ranked och ekonomi.

## Kartskins — Nattpaketet

- **Forest Fire** (glöd), **Moonlit** (stjärnor), **Eclipse**, **Underworld** (glöd), **Night City** (stadsljus), **Night Park**, **Rainy Day** (regn), **Midnight**, **Blood Moon** (röda stjärnor). Alla i Blackwood-familjen: kolsvarta, mörkbruna och djupröda himlar med mörkare väggar. 75g, eller 150g för de sex med en ambient effekt.
- Effekterna ritas bakom kartan och aldrig framför spelet; inställningen Animerad kosmetik stänger av dem.

## Namnstilar

- Tio nya gradienter (1500g): Fade, Earth, Orchid, Sapphire, Emerald, Steel, Ash, Royal, Blood, Twilight.

## Kosmetik från communityn

- Shock Shades, Cat Mouth, Cat Eyes, The Challenger och Goober finns i butiken; Seasonal Springs omgodkända storlek är aktiv.

## Översättningsportalen

- "Sessionen har gått ut" vid varje öppning för spelare vars spel och webbläsare når servern via olika nätverksadresser (Cloudflare WARP, integritetsreläer, VPN med delad tunnel) är fixat: sessionen binds nu till den första webbläsaren som använder den, och en verklig adressavvikelse rapporteras som just det.
- 53 nya nycklar med maskinöversättningar till spanska, ryska, ukrainska och svenska — översättare kan förfina dem i portalen.

## Ranked och ekonomi

- Glicko-2-volatiliteten (tau) höjd från 0.5 till 0.6 i alla lägen; FFA använde tidigare ett annat värde.
- Vunna vad på en stor favorit (odds 1.5x eller lägre) skickar nu 20 % av **vinsten** — aldrig insatsen — till den fighter eller det lag du satsade på. Oddset som visas vid vadet visar redan nettobeloppet. (Communityidé.)
- Matchhistoriken kan sökas på motståndarens namn — det finns en sökruta i Min statistik.

## Fixar

- Ratingändringar visar decimaler för små ändringar konsekvent på alla skärmar.
- Anpassad spelarfärg kunde saknas på kroppen vid kortval i rum med kod.
- Loopande kartljud (sågar, Abyssal Countdown) kunde fortsätta efter sin rond.
- Sändningssätet: ett bildfrekvenstak medan regissören är aktiv och en enda FPS-regulator, så att spelarens egen bildfrekvensinställning inte längre kan gå förlorad; rotationen håller varje match i minst 5 minuter och väntar på en paus i striden innan den byter.
$rn1392sv$, 'machine', 'claude-mt')
ON CONFLICT (tag, language_code) DO UPDATE
   SET body = EXCLUDED.body, title = EXCLUDED.title, source = EXCLUDED.source,
       translated_by = EXCLUDED.translated_by, updated_at = NOW();

-- Verification: expect 5 rows.
SELECT language_code, source, LENGTH(body) AS body_len FROM release_notes_i18n WHERE tag = 'v1.39.2' ORDER BY language_code;

COMMIT;
