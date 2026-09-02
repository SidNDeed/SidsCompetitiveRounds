-- 282: i18n client keys for v1.40.0 (356 NEW keys): the Aug-31
-- mega batch (Q/E wheels, dances, trails, tournament achievements, Compare/
-- Card metrics), the Sept-1 corrections, and the whole MUSIC feature
-- (batches 1+2: Music tab, shop albums, ratings, artist commerce, dance
-- body-motion strings). This is the additive half of what
-- POST /admin/i18n/sync-keys does, written through the migration channel
-- because this seat's tooling cannot sign the admin HMAC (learning #443).
-- Verified against the live table before writing: the extractor manifest
-- (2415 client keys) retires NOTHING here (additive-only, per 248/266
-- precedent; the 12 live keys not in the manifest are left for the real
-- sync tool's retire pass) and changes no English (key_id derives from the
-- source string, so a shared key_id cannot carry a moved source_hash).
-- key_id = sha1("client\0" + English)[:16], source_hash = sha1(English),
-- sensitive per tools/i18n_sync_keys.py's SENSITIVE_MARKERS (imported, not
-- copied). 0 of the 356 collide with RETIRED rows and are
-- un-retired by the ON CONFLICT arm. Idempotent; explicit transaction (#340).
-- The game namespace is unchanged this release.

BEGIN;

INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, max_px, context, updated_at)
SELECT v.key_id, v.namespace, v.msgctxt, v.source_hash, v.sensitive, NULL, NULL, NOW()
  FROM (VALUES
('018e099fd8ed2dc5', 'client', $k282$Both clients watch everything; only the elected reporter sends. Duplicates are absorbed, and the server re-checks ranked or casual when the report lands.$k282$, '3d3d4c5ad7b1daa8ce5a6f622acab3916a7e666f', TRUE),
('0195071f9f835b41', 'client', $k282$nothing$k282$, '0feca720e2c29dafb2c900713ba560e03b758711', FALSE),
('01a4b599f350abae', 'client', $k282$no - stop$k282$, '0297fb1e6c176b4d67ea304108c33235fbb5d723', FALSE),
('027931eb075e1aa4', 'client', $k282$Top Winners$k282$, '6462a1a2c3dc92512ae5dce25012908d66eaea5d', FALSE),
('0322c42f001ed4a7', 'client', $k282${0} tracks$k282$, '5e337b6470b963b592464ec5c40d56150f192cf7', FALSE),
('039bc0c9d5cf3e9a', 'client', $k282$<color=#FFD94D>=  OTHER  =</color>$k282$, '3fb910cdf01afaf3a6efa8bfb22b2882ac1e6831', FALSE),
('04f0f934efc4061e', 'client', $k282$1V2: ONE AGAINST TWO$k282$, 'bdb3ef244fabc64235cd611c73655326395a986c', FALSE),
('054a9e0ffa32420a', 'client', $k282$SIGNAL, FLAG, HUMAN REVIEW$k282$, '9e76c2cfaa74237c4667dda1106096059423809a', FALSE),
('07ddf0eb2233d445', 'client', $k282$LOWER STEAM ID$k282$, '085c6d7c375032aee0da676b3f0a7b0f029d62ea', FALSE),
('0938287c5f713cf1', 'client', $k282$LOSERS BRACKET: one winners-bracket loss drops you here; a loss here eliminates you$k282$, '1a8e5468168f7afe3c5ddf6cc716dbb6674d4cc5', FALSE),
('09a1aa463f338351', 'client', $k282$All cosmetics - everything available, grouped by category.$k282$, 'b86445f0e6c41a5f76bc9faa3b81b6b4f2fb8959', FALSE),
('0aff582e300474d4', 'client', $k282$For sale$k282$, '8c2e0e1d55b890163a0578eee7d56dc9a8163f4e', FALSE),
('0b27001b6759297e', 'client', $k282$Shop listing name only - the Music tab and now-playing keep the compiled album name (max 64 chars)$k282$, 'c57c6f7f29a8f6c42980ae80a5dd755b51421483', FALSE),
('0c0c58a969ea6324', 'client', $k282$<color=#B0FFB0>=  MAP COLORS  =</color>$k282$, 'f51730ea676e6268149dc283145a89fd42e55431', FALSE),
('0c88e1a2a371e57d', 'client', $k282$W-L and WR count completed series. XP and Gold accrue per player slot; 1v1 rating never moves.$k282$, '9413f2a8d079b061160c6cce7968b08bb38bf16b', TRUE),
('0cfce7055946c432', 'client', $k282$Casual games$k282$, 'bb086b36eb4297b438e04630658cb14db77ba543', FALSE),
('0d18b8f43d73161e', 'client', $k282$Unique Players$k282$, '874a0591fc04611262fdd744ebec93993dacecc5', FALSE),
('0da56f0ef6ca392b', 'client', $k282$own bullets judge hits$k282$, '9d84d798f14ca14192b5a722f8deba3488997934', FALSE),
('0f3d1f351e4a7862', 'client', $k282$Async Champion$k282$, 'c40497b1048c1314d0ed1d417cba50705d6627b3', FALSE),
('107f9e44420b6a70', 'client', $k282${0} ({1} ratings, {2} listeners)$k282$, '2e5c88d9dff1ac89fe4c65eb5841e1a969463c87', FALSE),
('1107099ffb76a22b', 'client', $k282$400 FPS$k282$, '132a8134e5e820d1aa9b05a3dde48da1d3c25f44', FALSE),
('1152b9c31dbaa74f', 'client', $k282$Mode: <color=#88FF88>custom music</color>$k282$, 'cfe537a5f3289e5512190c65186f14dd08253154', FALSE),
('1198284ca4ddd03a', 'client', $k282$A winners-bracket loss drops to the lower lane; lose there and you are out.$k282$, 'dfca1636d73096541e96ab0c3463eea6b8867dde', FALSE),
('1318e9afd85da213', 'client', $k282$WALL JUMP$k282$, 'f81fae96e119e012ff27043537c33c26f0545e75', FALSE),
('136ec55c8ce85296', 'client', $k282$Revenue$k282$, '35cf82f9d2a9c8ba5943837ec0d6646d49a7a51e', FALSE),
('13b5e24f84f0ed66', 'client', $k282$default orange / blue$k282$, 'a7eaf6bc6f5bfd2e69d581a14dda0fd9d27bbc20', FALSE),
('13e7a1792e8abd1e', 'client', $k282$Tropical teal sinking into deep blue. Two-color gradient.$k282$, '35f58c657c654b247ae5592e9450f5a69c96ebff', FALSE),
('144f088248385b4a', 'client', $k282$Shop sales$k282$, '0493923fe233433dacf26ffe427e4790aacc9f7c', FALSE),
('1497e4b80e5a3664', 'client', $k282$CAPS$k282$, '16b24a0952726b5c0d2889f8abde87eec79d5dba', FALSE),
('14b128653a9a6e6f', 'client', $k282$Shop Sales$k282$, '05d289b3fe377471612bbe291e5e3f293827ed30', FALSE),
('15320b7b158aa43d', 'client', $k282$OPPONENT'S CLIENT$k282$, '4453348acf4193bd357d9dedd76c9c00ea33234e', FALSE),
('16270e075ff09c38', 'client', $k282$SALES OPEN$k282$, 'f76a4926ab971b67975e14dbee83d6872ac9bb50', FALSE),
('16f2e4dd38463d7b', 'client', $k282$You should join Competitive Rounds, it's a discord community$k282$, '908c526215debbd4ee1363e3666282a9b9c82697', FALSE),
('1810e65fb6bc6f81', 'client', $k282$SHIPS IN A RELEASE$k282$, 'd7bb69fb19763c09ddf7ae009395afc7badcfc2e', FALSE),
('190cf3b65caa555e', 'client', $k282$4 players$k282$, '8d8fcef4337c7ea051f3066658a0ba94861ea8b0', FALSE),
('1928b19204130de1', 'client', $k282$bundled into the mod$k282$, 'b0b19f7da5a641c8cd96fdb91d53b19ae2d2e36b', FALSE),
('1931b64f5776ffe6', 'client', $k282$artist sets price + stock$k282$, 'ec27f4e8a660e892b1e898de326c873c402f9da8', FALSE),
('19cf70accfab0f0d', 'client', $k282$Override the default orange/blue team color with a tint of your choice. Only visible to modded players. Premium tiers (Prismatic, Chrome) animate during combat.$k282$, '5f95d9a80a176c2d1425c1953e1eb7aafd071e43', FALSE),
('1a6c33ac1dff9370', 'client', $k282$Bold, italic, underline, strikethrough, and color/size modifiers applied to your player nametag in lobbies and matches. Visible to every player, modded or not.$k282$, 'b97598910533b3e47d54e5684ae3d32280929726', FALSE),
('1bd56f0d3fbd9153', 'client', $k282$discord.gg/comp-rounds$k282$, '2452413e142aae220bf50fbfa426f638b7816ce4', FALSE),
('1bf9b5aeb836afe7', 'client', $k282$Diagram of Spirit's research, 'On Damage Types and Buff Activation'.$k282$, '7c6f286eedfab90b66922459d09fc9166e5b14d3', FALSE),
('1c854c38083d1b76', 'client', $k282$SERVER$k282$, '8d4ba065ae312536d8bdc5b787d19bb682bdc302', FALSE),
('1d3095cabdbc923a', 'client', $k282$Your personal breakdown appears here once gold data loads.$k282$, '7c8dc31180d2f22bff91272414ca074254e9957e', TRUE),
('1d4b353260bcecaf', 'client', $k282$<color=#C8A0FF>=  PLAYER EFFECTS  =</color>$k282$, '51932d71c2a90560a3906a6e9fb9ab42ab946fce', FALSE),
('1d7fa00018397e5b', 'client', $k282$THE DUO$k282$, '5e8adebb89e8a50a78020624ead3f89d2f40de6f', FALSE),
('1dd3db8c064d9654', 'client', $k282$ASYNC MATCH DEADLINE$k282$, '246386952c55f6e0b6f2ee074517a11ea3b7cb02', FALSE),
('1dfcc098b4da261c', 'client', $k282$In-combat particle aura around your character. Only visible to modded players.$k282$, '1c15dd7ddb9d813d9dc6cfb93e6d07cca1ff84cc', FALSE),
('1e52aed7fca8a685', 'client', $k282$Midas$k282$, 'c7e4e114997188bbd97b7fab1b85eecfed1376c7', FALSE),
('1ee66467a63c926b', 'client', $k282$Titles are the short labels that render beside your name across the mod - leaderboard rows, Recent Series, Records, Compare, and every T-chat message you send. You can own any number of them, but only one is active at a time: pick it in the Shop tab with <color=#7FD4FF>Set Active</color>.

<color=#FFD94D><b>CURRENT RANK - FREE FOR EVERYONE</b></color>

<color=#7FD4FF>Current Rank</color> costs 0 gold and sits in the shop for every player. It's dynamic: wherever it renders, it shows your live 1v1 rank name in that rank's color, resolved fresh at render time. Rank up and the title upgrades itself; rank down and it follows you there too. The ladder behind it runs 25 rungs, from Beginner I at 0 rating to Grand Master V at 2610.

<color=#FFD94D><b>PODIUM TITLES</b></color>

There are three podium titles, one per ranked ladder: 1v1, 2v2 and FFA. Each is granted the moment you enter that board's visible top 3, and taken back the moment you fall out of it <color=#8A8A93>(the position check runs on a cached board, so both directions can trail the actual standings by a minute or two)</color>. A board only lists players who have at least one counted series - or, for FFA, one recorded game - so a fresh account can't hold a podium.

The rendering is the interesting part:

- While you hold a podium spot, the title renders live as <color=#FFD700>1st Place</color>, <color=#C0C0C0>2nd Place</color> or <color=#CD7F32>3rd Place</color> in gold, silver or bronze - always your CURRENT position, with a 1v1, 2v2 or FFA prefix everywhere except that ladder's own board.
- <color=#FF6666>Off the podium, the title leaves your inventory entirely</color> until you climb back into the top 3. You hold it exactly as long as you hold the spot.

Podium titles never rotate on a schedule and can never be bought. The only way in is the top 3.

<color=#FFD94D><b>SLAYER TITLES</b></color>

Two legendary trophies for beating the names on the door:

<color=#7FD4FF>Sid Slayer</color> - win a completed ranked 1v1 series where Sid is the loser. Renders <color=#FF4655>red</color>.
<color=#7FD4FF>Stan Slayer</color> - win a completed ranked 1v1 series where Stan is the loser. Renders <color=#00E5FF>cyan</color>.

Each arrives attached to its achievement, which also pays <color=#7FE87F>1000 gold</color> (see <color=#7FD4FF>Achievement guide</color>). Taking a single game off them isn't enough - the series has to complete with you as the winner.

<color=#FFD94D><b>TRANSLATOR TITLES</b></color>

Verified translation work through the translation portal earns three tiers. The unit is a live string: an approved translation where you were the proposer or the reviewer - doing both jobs on the same string still counts once.

<color=#7FD4FF>Rosetta</color> (rare) - 10 live strings. Pays 100 gold.
<color=#7FD4FF>Dragoman</color> (epic) - 100 live strings. Pays 300 gold.
<color=#7FD4FF>Babel</color> (legendary) - 1000 live strings. Pays 1000 gold.

<color=#FFD94D><b>PURCHASED TITLES</b></color>

Regular titles sit in the shop with a gold price and work like any other cosmetic: buy once, own forever, wear it whenever you feel like it.

<color=#FFD94D><b>EQUIPPING AND WHERE TITLES SHOW</b></color>

- Earned titles (podium, slayer, translator) are hidden from the public shop listing, but every one YOU own appears in your own shop view with its Set Active button. <color=#FF6666>Buying them is always refused</color> - earning the moment is the only currency they accept.
- Equipping a new title replaces the old one; titles never stack.
- Titles show on the mod's own surfaces: the leaderboard, Recent Series, Records, Compare, the stats panels, your T-chat messages (in the title's color), and the Discord chat bridge.
- Titles do NOT appear on the overhead in-game nametag, and players without the mod never see them - every title surface lives in the mod's UI or on Discord.$k282$, '2d45294cfb5df3152b549d461df19d0ddc8c8414', TRUE),
('200548f66e07ef64', 'client', $k282$<color=#8FB8FF>=  MUSIC  =</color>$k282$, '8a57dce3d90f3f7cfde4e62c118f13581c918e12', FALSE),
('20d7d7730e89c1a0', 'client', $k282$30 FPS$k282$, '7d592751d4d4fafee4c845a55414581c35ac1dfd', FALSE),
('20db26c30c3100cb', 'client', $k282$Dusty rose fading into indigo night. Two-color gradient.$k282$, 'cd56cc98a81ff4372bfb6936afdb2fc3c63b2d7d', FALSE),
('20f0dec1c5491a83', 'client', $k282$no direct PC link$k282$, '60e7dc38d58fa8d4dd69f14b8056f4fa75478377', FALSE),
('23312ec72122ea17', 'client', $k282$Use vanilla music$k282$, 'fc8aa74b208bf96597dfceec0adc76284bd94eab', FALSE),
('235e32ddb1201875', 'client', $k282$Point to the sky, point to the floor, sway those hips. Dancing locks your controls for the duration.$k282$, 'fd2f5c58c6a2ab9b9b61e5b1e568db7a14f2b934', FALSE),
('2397da0da5fcc65e', 'client', $k282$Orange melting into pink. Golden hour, every round. Two-color gradient.$k282$, 'a986c975fdbd804c9f7c6192cc28951d219f32e5', TRUE),
('24a8bf4272627e03', 'client', $k282$Shop listing name - {0}$k282$, '3c9a7b75e6c2a22994653b2e73cc4ca9ec71f098', FALSE),
('2540afb343a5f6b0', 'client', $k282$SIGNED REPORT$k282$, '8a2584377c89eac38f632458e5033c953d620077', FALSE),
('25b56b01dc34efe4', 'client', $k282$opponent has run$k282$, 'dea9d1370e983ae7e4bed0df6cf3b161e81228f4', FALSE),
('25c0e9b2f1f58bfc', 'client', $k282$Most wins carrying these cards (casual + ranked)$k282$, 'eb6ba65224fddbc1c969f37bc2b49e0744e4fef5', TRUE),
('261d9ebb1aeac0dc', 'client', $k282$ONE GAME, ONE SIGNED REPORT$k282$, '2d29f93bb633e5c66e01b643ad7b153868d9a451', FALSE),
('2657ecf2564002d6', 'client', $k282$Wind up the right arm and take off. Dancing locks your controls for the duration.$k282$, 'c3ed4e612af7644a8c04b0bb56878797d9751c8d', FALSE),
('26f0f8a2335ba795', 'client', $k282$SHIELD EDGE BOUNCE$k282$, 'fc64ad2e2aed235943184651399172baabb8d6c4', FALSE),
('26f78c1badaa8ce3', 'client', $k282$50 ACHIEVEMENTS BY PAYOUT$k282$, '6e348c0357c64c677e6641a1ce0d64222506b9c1', FALSE),
('2768f7fef66286bb', 'client', $k282$WHERE YOUR GOLD HAS COME FROM$k282$, 'b1656ecb60391d107bea3e96f0db721368eaba93', TRUE),
('2830536e6c923330', 'client', $k282$Music download failed - press Retry$k282$, 'b436e67207eb767fb094726f88bc196c02ec2cfe', FALSE),
('2862bc6be01046aa', 'client', $k282$Utility unlocks (e.g. hide your gold total on the leaderboard).$k282$, '1b613ddf1549425f05d9b31e4bdd762382c123ec', TRUE),
('28664eb4ad65366d', 'client', $k282$The cutoff is scored points, never a clock. Either lock condition closes the window.$k282$, '4b98983397b11a2cf0b05ae55891d3d7a35221b7', FALSE),
('291ff30d5079e949', 'client', $k282$Mouse-cursor color tint (local-only). Pick the cursor SHAPE — arrow, dot, crosshair, circle — in Settings; the tint colors whichever shape you choose.$k282$, '9cf80338abce8b567d68f64cfdbc22acaed2d62c', FALSE),
('2ca17fb22ceeb91e', 'client', $k282$Async Finalist$k282$, '732bc6ebb89a10d9399dafcf3162dc41462e2371', FALSE),
('2ca28458c1bba16f', 'client', $k282$no debt, no double buys$k282$, '3041bad1187c20fb9675fb2ee260fb4efa4a8055', FALSE),
('2cf57bd52862f8bd', 'client', $k282$<color=#FFD94D>=  TITLES  =</color>$k282$, '8e92ea5917efa32360585d08790d531fdb553521', FALSE),
('2f7eefed49e94df2', 'client', $k282$QF C$k282$, '341bb8dd1de413c75605a0c3834651ef423f01ec', FALSE),
('2fce258a62d8ca9f', 'client', $k282$CASUAL, RECORDED$k282$, '9848405c532ef118e7d6f79df0719e454c91ffda', FALSE),
('30d4db904ff26b1f', 'client', $k282$<color=#7FE8C3>=  CHARACTER COSMETICS  =</color>$k282$, '710f35c028bf084903e82e5b9b737dd62abd1136', FALSE),
('3375a7a17a28e03e', 'client', $k282$Play a tournament through to the end without forfeiting a single match$k282$, '7fe1293aa75e21cb2297dc2d43e8dc0d8f248425', TRUE),
('33bfac719482404c', 'client', $k282$your color$k282$, '0e2aa9db2a51762cc7ef7e2472f33a421dc2776e', FALSE),
('33d92083da701bc8', 'client', $k282$A dark trail lit by drifting warm sparks.$k282$, '4c1dc591501192d873bff90728e05c837a820f95', FALSE),
('3422362fcfe614f0', 'client', $k282$ROUNDS ships with real bugs - some cosmetic, some that decide rounds. The catalogue: symptom, real cause, and whether the mod repairs it. Repair details: (see <color=#7FD4FF>Bug fixes the mod ships</color>).

<color=#FFD94D><b>INPUT AND LOBBY BUGS</b></color>

<color=#7FD4FF>Escape key permanently dead, or inputs frozen as a match is found</color> - the game toggles input across all players with no null checks; one half-spawned player crashes the loop. <color=#7FE87F>Fixed by the mod, always on.</color>

<color=#7FD4FF>'No space to ready up' - you cannot spawn into a lobby</color> - the game tries to spawn your character before you are actually in a room, crashes, and never recovers. <color=#7FE87F>Fixed by the mod, always on</color>; 30 seconds stuck returns you to the menu.

<color=#7FD4FF>Typing confirms a card pick, Enter opens the room-code box, Space readies you up mid-sentence</color> - three places read the raw keyboard without checking for an open text box. <color=#7FE87F>Fixed for the mod's own chat</color>; the vanilla chat box keeps its quirks.

<color=#FFD94D><b>COMBAT BUGS</b></color>

<color=#7FD4FF>After a rematch, your block goes on cooldown but absorbs nothing - or Shield Charge stops firing while basic block works</color> - the between-games teardown can destroy card objects half-way, stranding dead hooks on your block. <color=#7FE87F>Fixed by the mod everywhere</color> (see <color=#7FD4FF>Blocking</color>).

<color=#7FD4FF>Poison health bars disagree between screens, and blocking poison is a coin flip</color> - every machine ticks its own copy of the poison against its own copy of your shield; health is never re-synced. <color=#7FE87F>Replaced by the mod's victim-authoritative poison</color> when the victim runs the mod (see <color=#7FD4FF>Poison & damage over time</color>).

<color=#7FD4FF>A poison tick kills someone during the round-won animation, awarding a phantom round</color> - damage-over-time keeps landing after the round is decided. <color=#7FE87F>Fixed on every modded client, in any room</color> - full protection just needs the room's (usually modded) host seat patched too.

<color=#7FD4FF>A leftover bullet from the previous point hits you just after everyone respawns</color> - nothing in vanilla despawns mid-air bullets at the point boundary. <color=#7FE87F>Fixed: modded clients clear their own leftover bullets.</color>

<color=#7FD4FF>Shots visibly connect but do no damage on your screen, or a point-blank drill bullet turns invisible</color> - the bullet's special components can register in the wrong order on the receiving machine. <color=#7FE87F>Fixed by the mod in any room.</color>

<color=#7FD4FF>Grow one-shots you out of nowhere</color> - broken math more than a bug: Grow's damage compounds per frame on the shooter's machine, so low frame rates and hitches multiply it massively. <color=#7FE87F>Normalized by the mod in competitive play</color> (see <color=#7FD4FF>Grow</color>).

<color=#7FD4FF>After one game with Demonic Pact, hold-to-fire guns like Spray stop auto-firing all session</color> - the no-auto-fire flag is copied one way and never reset between games. <color=#7FE87F>Fixed by the mod in any game.</color>

<color=#7FD4FF>Radiance visibly sweeps through a crowd and hits one person</color> - the wave only ever checks the single closest target and stops after one hit. <color=#FF6666>Fixed in FFA only</color> - there it hits everyone it sweeps; other modes keep vanilla.

<color=#7FD4FF>Chase's card text lists a Health bonus</color> - dead data the game never applies; the card has never granted it. <color=#7FE87F>The mod fixes the label.</color>

<color=#7FD4FF>Being offered a card you already own</color> - not a bug; the second copy levels up the first.

<color=#FFD94D><b>MODE AND VISUAL BUGS</b></color>

<color=#7FD4FF>In 2v2 or 1v2, a card picker stands on an empty stage, or the wrong body is shown picking</color> - vanilla only ever presents one picker per round, using a team number as a player number. <color=#7FE87F>Fixed in 2v2 and 1v2 mod rooms.</color>

<color=#7FD4FF>Phoenix revives someone into thin air - invisible, unhittable, stuck</color> - the revive finds the player by list position, wrong once the list has changed (an FFA leaver), and the death flag is never set. <color=#7FE87F>Fixed by the mod everywhere.</color>

<color=#7FD4FF>Another player's name shows as the literal placeholder PlayerName</color> - a failed Steam name lookup is never retried. <color=#7FE87F>Fixed: the mod retries the lookup (up to 15 tries over half a minute) and repaints the name when it lands.</color>

<color=#7FD4FF>A saw's spinning loop plays forever, or audio goes muffled for the session</color> - looping sounds outlive their owner and starve the sound engine of voices. <color=#7FE87F>Fixed: leaked loops are swept after every round.</color>

<color=#7FD4FF>Harmless error spam in the log during map transitions</color> - the map-move animation holds references to pieces replaced mid-move. <color=#8A8A93>Not fixed - benign noise. (Anything that must touch the map mid-move, like the mod's own map skins, defers around that window instead.)</color>

<color=#FFD94D><b>WHERE THE FIXES RUN</b></color>

Crash guards and dead-state repairs run everywhere - they repair states vanilla never intended, without changing any rule. Rule changes are gated: mode logic needs its own mod-issued room, Grow normalization needs every fighter modded and consenting, and poison authority follows the poisoned player - an unmodded victim keeps vanilla poison. <color=#7FE87F>A non-modded player always gets pure vanilla gameplay</color> - and the only things they can ever see of the mod are nametag styling and quick-chat phrases you deliberately send through the game's own chat (see <color=#7FD4FF>Vanilla stays vanilla</color>).$k282$, 'be5467fdb8c2f0918b82a4a46b9f0cf6a6a75115', TRUE),
('34c4b0f8d3827925', 'client', $k282$Sold$k282$, 'e6560d9c298e72db56c00c64c9c0c9c6a63ca288', FALSE),
('34e94342172ccc16', 'client', $k282$nothing - vanilla has no surface for them$k282$, '7c6b93acbc4088c277552ad8ef6ab2f2dd378d59', FALSE),
('35a41c9dae50afd8', 'client', $k282$Different players who have picked this card$k282$, '1e58e349feb201eaf84819b8cbf5ce95e3251093', FALSE),
('3641c4073564f471', 'client', $k282$Dances$k282$, 'b6fe8586434a4165d8531d4cc3c065a8a9e700df', FALSE),
('3786a6bd207e499c', 'client', $k282$RANKED$k282$, '1b7065ae1c038de8c69cfa7e56294b2e33055ce8', TRUE),
('3878e9a06f200884', 'client', $k282$your aura$k282$, 'eeb8efa38b04f77978c1af0170aa5d063ac81369', FALSE),
('3890f0cbb586ff4b', 'client', $k282$Downloading...$k282$, '66f3ac75224897b518295f324d2eaaffcbdae888', FALSE),
('38cb3a00ec4aae7f', 'client', $k282$Northern Lights$k282$, '6415fc8a6d53f7a4d32943d64d274f346316f7f7', FALSE),
('392b2a7a739ec173', 'client', $k282$7-track Metal / Phonk album$k282$, '680eee018198c6a159af8cf43ac17b9336e05343', FALSE),
('3b839398da0a7306', 'client', $k282$Tidepool$k282$, '60c939e8c8b5a9eee31173dadc4d14d0f36d8887', FALSE),
('3bc15e26749d12d3', 'client', $k282$PLAYER 1$k282$, 'cae59f99028ccdf1803e8bd4384e23450ec0a46f', FALSE),
('3c0d5358f8d4d5bf', 'client', $k282$WHAT EACH SEAT ACTUALLY SEES$k282$, 'f0db6799b034ff866597cee74eff4ea14f74175d', FALSE),
('3cadba6cb4d299db', 'client', $k282$A silver trail with white twinkles. Leave a little sky behind.$k282$, 'e735d970c376d796959969c8839aece4074458dc', FALSE),
('3ceb575bb104e67a', 'client', $k282$FLAG$k282$, 'aaabc04650aab77b47f331f4aacd9649ab02c710', FALSE),
('3d771675aa9386e3', 'client', $k282$SHOP$k282$, 'f2e1c7fad591bf812899592b3df6cde5ff734de6', FALSE),
('3df637f1d1f20327', 'client', $k282$Character cosmetics - faces, eyes, and accessories, many made by community artists. Buy here, then equip them in ROUNDS' own character editor (F8 or main menu). Visible to all modded players.$k282$, '571a19ec45d137f48cfba3989f252ecc1b8d8fce', FALSE),
('3e02a22d69671a03', 'client', $k282$point + release E to dance$k282$, 'faa338188b2b5cdec06937f45f707599ae35d7eb', FALSE),
('3ec5a312dd9938e0', 'client', $k282$<color=#9AD0FF>=  CURSOR COLORS  =</color>$k282$, '86a984947ac8c52cf4500bcfe364a187dd27444a', FALSE),
('3ef6e666a4087849', 'client', $k282$otherwise: score / check-in / no-show tiebreak$k282$, '8044c2aa3964a194eff018e055d8259fe024ad05', FALSE),
('3fd3cdb18f2f274c', 'client', $k282$The Shimmy$k282$, '18350a4c720998d2321ea9fb4be9972b87283f36', FALSE),
('40389559a5d3a7c2', 'client', $k282$HUMAN REVIEW$k282$, '99cf818cabe3e4801c06b9427a9ce4f4d1500280', FALSE),
('404cd01710201dc0', 'client', $k282$Nah$k282$, '78c3dc0e955697c34e9dfcdb511092a48644b44d', FALSE),
('423228a4fc37960b', 'client', $k282$Quick chat works once you are in a game with your character spawned.$k282$, '355b09f4e293431128ee7c4e69fa7ef1838b03b1', FALSE),
('4242863b150cbda8', 'client', $k282$An aurora follows you. Green and violet shimmer with sparkles.$k282$, '38d6c96d36ce8a29693c24c898c7948d153eb801', FALSE),
('42453248177629c2', 'client', $k282$More...$k282$, '3c25ce154a917b9c1539c47ac2d217ea7f6b9cf5', FALSE),
('426e6d1b01fdabd1', 'client', $k282$Downloading full album...$k282$, '438d7ff95d32eb9ec0be883747768af8db8f4a80', FALSE),
('42b363065f7bc00c', 'client', $k282$Take 2nd place in an async tournament$k282$, 'e923dca9795b936117ea5017d3a38acd54af0566', FALSE),
('435a4b2bbc8034c8', 'client', $k282$reset if LB wins$k282$, '4f3db459147e54b55553a20c115fcf8572173c35', TRUE),
('444e1ff03b6093fd', 'client', $k282$30-second previews - they stop on their own$k282$, '2b0f48724a24afff6f64901d1b39e182338465d0', FALSE),
('47d1650b03894f39', 'client', $k282$Custom faces$k282$, '7c0d87a15587ef5cae2edf1d482863312cd9e5de', FALSE),
('4813d16325219e3b', 'client', $k282$Most 5-0 sweeps carrying these cards (casual + ranked)$k282$, '7cdfe78ce185ab16eb859aa0ec1cf81fa1a15ac7', TRUE),
('4867ccd0ab09b4b7', 'client', $k282$one active, or multi-equip$k282$, '5015bc8802ef6f39234ea8b46bd73b2a9ca5ec1f', FALSE),
('492e7a1185b61208', 'client', $k282$Menu music: <color=#88CCFF>Default</color>$k282$, '932268f69f8abd8f78fcb54324acbb153db7695f', FALSE),
('49365749c7b1c2de', 'client', $k282$edge check: 0.1s; block window: 0.3s$k282$, '60c988b15337b0f7139c96ec178e4dc424949c85', FALSE),
('49f54b769f831d85', 'client', $k282$Gifted$k282$, '7e1e863c271feae27da33fc702d797697314a93b', FALSE),
('4a16145380f98364', 'client', $k282$the mod?$k282$, 'dead726bfa96a471da1ee009d3a1b131af1380c3', FALSE),
('4ad250fa964a3477', 'client', $k282$the full art$k282$, '745c907a5bceb3e19de222759912533d47907064', FALSE),
('4ade614fa0dc0708', 'client', $k282$Iron Bracket$k282$, '7263a1edd582c7b3ef9fbe39bf7fea9c382188ef', FALSE),
('4bbd82317abb0839', 'client', $k282$Builds that stacked 2+ copies (all players)$k282$, 'c2cd71ebabf6233304c88629eb6587714c60ac1f', FALSE),
('4e8e19e76bc1131d', 'client', $k282$2V2: ONE SERIES, TWO TEAMS$k282$, 'd48d8147cd24c327b544b44a62303e65da6feca6', FALSE),
('4f7e0e667293a970', 'client', $k282$SF B$k282$, '146fb58ce6a9e9e0c19f9433130c9b3e0431f1b8', FALSE),
('50514f77be6d49ff', 'client', $k282$Held by the top 3 on the 1v1 ranked leaderboard$k282$, 'bea6098ea458b065476f3ec8a265587f5a25be11', TRUE),
('51fa309a2660b60c', 'client', $k282$Hop to attention - arms snap up and out on every beat. Dancing locks your controls for the duration.$k282$, '6365d6a9d800c10fa6e483c59e130301bb787840', FALSE),
('530f0fe2b09f05af', 'client', $k282$EQUIP$k282$, 'df39fedad614b9e9ab0ed078f3d133f684213b7a', FALSE),
('530f79859164bfc5', 'client', $k282$Win a live (sync) tournament$k282$, 'b6930ee4436274d073a3d615ae030956e78e7e28', FALSE),
('538ea7a3863c3322', 'client', $k282$two teams of two$k282$, '320ea28ff8cf9fb1c048c77e5311c2c2ccbda228', FALSE),
('53c4654c16ccc2d1', 'client', $k282$finished series: result stands$k282$, '538071b476b87fe12f052546400549b2e321210c', FALSE),
('54f27396051fa05c', 'client', $k282$OPEN$k282$, '33906a7dfdec01bb765c738946d88161600ca35d', FALSE),
('5678fc6bff05c631', 'client', $k282$Join Competitive Rounds!$k282$, '1cadad1503961af2e4f1a03cf9083519e5d26a7d', FALSE),
('569b4265e5397abd', 'client', $k282$YouTube$k282$, '558865a16feb9f751b8bcebf46a954afbeba0b24', FALSE),
('572f63ba8113eadc', 'client', $k282$SPACE$k282$, '6a395052c9ebc4235d024c28291d96b8cac3053b', FALSE),
('577b16be2ddd5908', 'client', $k282${0} total$k282$, '3a0bdc132cd5be4ced44219ee0d007f2880b21d5', FALSE),
('590afb688bd26848', 'client', $k282$Loading your dances - try E again in a second.$k282$, '15fe0cc914c02a1b50fbad57027e5bdb10d7a371', FALSE),
('5981cfc4bec6d2aa', 'client', $k282$Rose Quartz$k282$, '2568e0420d78a050256fff684957c4eb34011abe', FALSE),
('5b6c67eb59c7ad5a', 'client', $k282$EDGE BOUNCE AND WALL-JUMP WINDOWS$k282$, 'b63228b8b8d05bc27009feeff1265e8eac3e82c1', FALSE),
('5c61ac09c8790e5a', 'client', $k282$QF D$k282$, 'dcc6f8c98198485da8208044f04ac1ea4a225177', FALSE),
('5d9749b7d1d2cd50', 'client', $k282$AUTO-BALANCE$k282$, 'd8796d7466c24ad713a37062fa958677b0622370', FALSE),
('5e2f844126994bca', 'client', $k282$click Preview again to stop$k282$, '16f5853cbde985dccf1dea304da084cc7b21813c', FALSE),
('631a133c537677af', 'client', $k282${0} tracks - {1} - {2}$k282$, '9c2e955e1da510a3a7ac7128096bed12c608b737', FALSE),
('63e41c49cb39356f', 'client', $k282$2v2 QUEUE$k282$, '646aceb36023cfb5fa89dc1111b69bfd7c8ec40d', FALSE),
('64dc51615fc974c9', 'client', $k282$a person makes the call$k282$, 'f8dfbbe866f95cc4ec4b4480ee1ecaf3956c6a33', FALSE),
('64fbafa71c64ea5b', 'client', $k282$music album$k282$, '1d4c4223850b4c5a79983792395382208c8f79c8', FALSE),
('66173b472176d55a', 'client', $k282$A slow starfield in violet and blue. Bring your own gravity.$k282$, 'f21e9b7f054b8df1f3badc742f510743bbbf019f', FALSE),
('66cfc06b58cc1eb9', 'client', $k282$Cool teal wake, fresh from the shallows.$k282$, '2895057a632eb8e91dfe420d751a813655e0432d', FALSE),
('66f0a10fe77a4874', 'client', $k282$invalidated outright, gold and XP reversed$k282$, 'd90a22c31ec7bdaf4e9f528f58c63a30ac020e29', TRUE),
('6743a3837d3b1790', 'client', $k282$always earns x1.5 pay$k282$, 'ca0de51d37da52488bbe822980c08e8f4b54ea66', FALSE),
('67fde0c40c147a46', 'client', $k282$Music files are missing - reinstall the mod through your mod manager$k282$, '9ffc71853c15ce02fa37020b54707f5690435f6c', FALSE),
('682d02d713ebead0', 'client', $k282$Auras$k282$, '0b5c4206710a5a0dd90dba2856fd460845b06573', FALSE),
('689a1b913ca5b95f', 'client', $k282$VANILLA GROW: FRAME RATE CHANGES DAMAGE$k282$, 'e3b2c4d88bb44675b4d10d5aa3f7a001254164b9', FALSE),
('68ae3ba5bde0a1c6', 'client', $k282$two players, one side$k282$, 'c19286c4efd42e3a0809eb95f62008936dc218fb', FALSE),
('68c4b3a3a991374b', 'client', $k282$The Floss$k282$, '4932f159926656102e9a366a3b5482b27c1c0811', FALSE),
('6917a6295e2296eb', 'client', $k282$EVERYTHING TRAVELS THROUGH PHOTON$k282$, '32ef70ca2278f2060923c0806c0b9b46af7a2341', FALSE),
('6a9b064b1f6c4773', 'client', $k282$Hop to the beat, arms pumping. Play it between rounds with the E wheel.$k282$, 'c63b8683892a259a8e3463e0f29a8dea1e962304', FALSE),
('6acb2025439df09b', 'client', $k282$Radioactive green with lime droplets. Probably safe.$k282$, '17b8b7386ad2a3ed4cf024889d17f1cac584e54e', FALSE),
('6b7e447c165e9e5a', 'client', $k282$Music download is rate-limited - waiting to retry$k282$, '9638ffe3063b448179253fb1100806c4c854316b', FALSE),
('6c12e59cb06be91e', 'client', $k282$Another Round$k282$, '857132eebe84c050a0d8339923da43657fdfcb15', FALSE),
('6ccaa73650023797', 'client', $k282$OFF$k282$, 'ad50489054ddaae044be8b3054bf4d67480648d6', FALSE),
('6cd6ad59ec9f0ff5', 'client', $k282$Music$k282$, '131260cbfbb0c821f8eae5e7c3c296c7aa4d50b9', FALSE),
('6d56f30dd3dd50f7', 'client', $k282$WINNERS CHAMP$k282$, 'a1f04d4d1e7f99b9139640cf2e9b7fa3a6154903', FALSE),
('6db3bbf4f54c0cb1', 'client', $k282$one +24h extension$k282$, '0782adb78e6c9b99ee3bcd1ef5f675a1b8147757', FALSE),
('6eac4ea23c0996dd', 'client', $k282$Mode: <color=#88CCFF>vanilla music</color>$k282$, '3fa1667ada7e05444855ca035afd6b2f5282594e', FALSE),
('6ec8b00fdee94097', 'client', $k282$solo: the outer-left point$k282$, 'c78fc60f816f6151cfedc59e75bc5099d887665f', FALSE),
('6edb1352e795ee14', 'client', $k282$Main menu music: Default = ROUNDS' own theme, My playlist = your selected custom music, None = silence. Matches always use your picks.$k282$, '5fb0b4362428b56ff9d74047337ff4f264be5e21', FALSE),
('6fde99ccb04c9464', 'client', $k282$Mode: <color=#FF8888>music error - vanilla playing (see log)</color>$k282$, 'a113da2015d647a799efb39468a15c241df25809', FALSE),
('718d188e4455bdc5', 'client', $k282$QF A$k282$, '3f95bde7012ad5270801b8142efe43e5c9a8ae95', FALSE),
('71b012c4704288df', 'client', $k282$TAB$k282$, '38d4aa698a701e2288a153e115d12aab45de5940', FALSE),
('73d934a944709623', 'client', $k282$RefreshValid = true$k282$, '8b8b2dee5ff2ae6048c22012233bb467d8c909da', FALSE),
('73fdcc5f35928195', 'client', $k282$final 24h check-in$k282$, '9a9f207e68bab4a7126b9ec05121eecc23a57a4b', FALSE),
('747964099bb289f7', 'client', $k282$Casual games keep their stats and XP but never move rating.$k282$, '93b4180f31d99408aadbdd42d402569ad35d84ae', FALSE),
('74b15a6e53f51a1e', 'client', $k282$short-match farming pattern$k282$, '20bdbf8143b5d78b30c7701b6fd05c824e7f6d93', FALSE),
('74ebc17cfc494570', 'client', $k282$8-PLAYER DOUBLE-ELIMINATION FLOW$k282$, 'e9a1a8a21f79f89a312697ef0c500e016f93e43c', FALSE),
('757475070fae24d1', 'client', $k282$macro-pace input windows$k282$, '9c40e6c83966edf6af71bfd2f2102c7b0d01024a', FALSE),
('76ca3828c8c44f21', 'client', $k282$<color=#FFD94D>{0}g</color> <color=#AAA>paid to</color> <color=#FFD94D>{1}</color> <color=#AAA>artists - {2} copies sold, {3}g gross</color>$k282$, 'b1a9647bbf64260e0acbc6c4172aeba96327b59b', FALSE),
('772a3d4462b7ff96', 'client', $k282$Sid's Competitive Rounds adds a full competitive layer to ROUNDS: ranked 1v1, 2v2 and free-for-all with their own Glicko-2 ratings (plus a 1v2 beta, recorded but unrated for now), an XP and Gold economy with a cosmetic shop, weekly tournaments, live betting on matches, achievements, and Discord integration. All of it is community-built and community-run.

<color=#FFD94D><b>THE TWO GUARANTEES</b></color>

Two rules hold everywhere, and the whole mod is designed around them:

- <color=#7FE87F>A non-modded player always gets pure vanilla gameplay.</color> Whole-room changes (Grow normalization, the FFA engine features) turn themselves off unless every fighter runs a current copy of the mod - one vanilla or outdated client means vanilla rules for everyone, identically - and the poison fix follows the poisoned player, so an unmodded victim keeps vanilla poison.
- <color=#7FE87F>The only things a non-modded opponent can ever see of the mod are nametag styling and the quick-chat phrases you choose to send</color> - quick chat goes out through the game's own chat bubble, like a typed message.

Two nuances, spelled out in <color=#7FD4FF>Vanilla stays vanilla</color>: crash-prevention guards are always on (they repair states vanilla never intended - a dead block, a frozen input - and change no rule), and between players who are ALL modded, current and Ranked-consenting, the poison and Grow fairness fixes apply even in quickplay and room codes.

<color=#FFD94D><b>HOW THIS LIBRARY WORKS</b></color>

The column on the left lists every article, grouped by category. Click a topic and it opens in this pane. Blue names like (see <color=#7FD4FF>Blocking</color>) point at other articles in the same list. <color=#8A8A93>This whole menu is F5. T opens in-game chat, and Esc closes the menu.</color>

<color=#FFD94D><b>WHERE TO GET HELP</b></color>

- <color=#7FD4FF>Discord</color> - the Discord button at the bottom of this menu opens the community server. Real people answer questions there, and so does the server bot - ask it things like 'how does ranked work' or 'how do I get gold' and it answers on its own.
- <color=#7FD4FF>Bug reports</color> - on the Settings tab, find 'Report a bug' and press Open Report Form. You can attach your game logs (a Preview button shows exactly what gets sent), you get up to 10 reports a day, and if your Discord account is linked, responses from the team arrive as DMs.

If something looks wrong mid-match, file the report right after that session - the attached log is usually what makes a bug findable.$k282$, '695f4b556a22ea8f0d77cbd168f3bb8fe91512e2', TRUE),
('78c89c8ea5a01801', 'client', $k282$recorded once$k282$, '75c4d27c742d1f6e7f36095b70192842a6fb0217', FALSE),
('799b6e13c11f28dd', 'client', $k282$7-day deadline$k282$, '06f7d0b555da9ef521a214c28fdb6bacf5ce74cc', FALSE),
('7a80d7e68ec2f588', 'client', $k282$series created$k282$, 'ba803cb03686e743d6e9702d329b5bfe5c5e2a94', FALSE),
('7ae14936a4754653', 'client', $k282$nobody yet$k282$, '35bcd8643f8ac67f525e911a2088afb8d31d4e78', FALSE),
('7b3149fddf2edfb3', 'client', $k282$Mode: <color=#FFC8F0>previewing</color>$k282$, '06d49afa15d06ec94bfe72d56446e09c74d5962f', FALSE),
('7bdae0bc3cd1610d', 'client', $k282$60 FPS$k282$, 'aa38e5e141e048571e807299696f02731a996dd5', FALSE),
('7c348c3bd4aca5bd', 'client', $k282$competitive clock: 240 FPS$k282$, '5faea509660c2904fe179e85631f377cebebe5b5', FALSE),
('7cc033f4e2ccee08', 'client', $k282$ARTIST STUDIO$k282$, '9c4cc5ddd54ef465a817bc3d4ad390d86342f142', FALSE),
('7ce772413df76f97', 'client', $k282$online, data on, fighter$k282$, '99bc7c117c72c2123f3c96eb3dd62d003748821e', FALSE),
('7d3238c8a8377e00', 'client', $k282$Community artist sales - who has items up for sale, and what they've earned$k282$, 'c6f750e3606cb1acabf51eaa12518b3cac219656', FALSE),
('7e7ce5225b69fa21', 'client', $k282$I play with a competitive framework mod called Sid's Competitive Rounds$k282$, '6a35e13d6078bf6447b978d8d41795fc54c18658', FALSE),
('7ee66c85b18c5bb0', 'client', $k282$Retry$k282$, '9f5cd8a2e8807d73efa02c844bfbca9fe552b283', FALSE),
('801db4ac576038b9', 'client', $k282$Body colors$k282$, '31412d98b3bdcdd01a31a2e05f02c6c31f34a24e', FALSE),
('8156d646ed5d3762', 'client', $k282$is elected reporter$k282$, 'bc85baafd8bb80ab1dbe6764cb0d771feba2fe72', FALSE),
('8242f437f1ba7af8', 'client', $k282$WHEN A GAME IS RECORDED AND RATED$k282$, 'f723884c1a8f207248e9f8bb98e7019a979c9d0f', FALSE),
('828f105fce189c49', 'client', $k282$ranked or casual$k282$, '251a6cbf14c3adbb715cea7913f49fac0b956c85', TRUE),
('82db2967d6278668', 'client', $k282$Nothing playing$k282$, '13ae374e9d0eb2c240c688ebb7932cc3dbb4a275', FALSE),
('84560648012ce2e1', 'client', $k282$not blocking: 51 damage + return impulse$k282$, '5ecbe3fc814b3bedd3ae2f8e48735110c17a7e27', FALSE),
('84603418a58395c8', 'client', $k282$with exact evidence$k282$, '380985fee96b8861416b2c6ba8f200ba045c59e0', FALSE),
('868d9fbdce7103c3', 'client', $k282$5-10 damage: Refresh triggers$k282$, 'c0df998c8501ac754421472bd3a94844fcb67326', FALSE),
('87c6e8bf8e7ae780', 'client', $k282$enabled?$k282$, 'b896146b87f9453da24ac71dee61c5e301b13a6a', FALSE),
('87fcd616bdd6fcd8', 'client', $k282$assigned by the server$k282$, '8b665bae87464c9df3296fae2077214efc5ab31a', FALSE),
('889d5548ce21e996', 'client', $k282$The Helicopter$k282$, 'a8e9a6158d251d77ba30554805e11a731a6d3e1f', FALSE),
('89e56876664535f9', 'client', $k282$Twitch$k282$, 'e8ea5fe2a6a5083495e58e7939264d6fc4a08efe', FALSE),
('8b17e8b203c35266', 'client', $k282$Full music albums that replace ROUNDS' combat soundtrack for you. Click an album row for 30-second track previews; after buying, pick tracks and control playback in the Music tab.$k282$, '090784407ecb4e04e63455bbe866f5a003ad9f06', FALSE),
('8c1eb356c1525df3', 'client', $k282$Hips one way, arms the other - the classic. Dancing locks your controls for the duration.$k282$, '3d54b658e24e84cbd5bf677fdcb229ba5796f7d2', FALSE),
('8c4ab8bbb2d8c374', 'client', $k282$E (hold) - dance wheel; dancing locks your controls$k282$, '10b2a3262b0f0a229a73e14c516db37e4a51d930', FALSE),
('8cd713a42dc28b19', 'client', $k282$Win an async tournament$k282$, '28f7fc6c7106e01bbdbd4bdcdff80262b106c5cc', FALSE),
('8db61be6a2860732', 'client', $k282$Each seat simulates its own replicas. Damage is computed on the shooter's seat and relayed as a final number.$k282$, 'da9ec544c59c98e53c9aaf2442e3d81d2725ec08', FALSE),
('8e55c28baa95c60c', 'client', $k282$game in last 45 min: wait$k282$, '94658d7c8c878f44e18d73f9c8affbfa3f8aa94f', FALSE),
('8e79cc7c9152efb9', 'client', $k282$Play$k282$, '5d12bd53552cafc41ca6146c04870df2e1574e13', FALSE),
('8ec026c42940c6d2', 'client', $k282$A glowing trail that follows your character body during combat. Only visible to modded players; the shop preview shows it following your cursor.$k282$, 'c814dc7375c9e38a44272ffd35f78577ece5f21d', FALSE),
('90c58689d7c96644', 'client', $k282$ROUNDS OST$k282$, 'fe8dce1485bae8c21fe8add8173abcc34654bc7b', FALSE),
('912677eb32da6ab4', 'client', $k282$SHIFT$k282$, '149b8de2b0282bcde23304b8948eaaf895a98809', FALSE),
('918ff09cc73c9768', 'client', $k282$Take 2nd place in a live (sync) tournament$k282$, 'c66d3912b0770404d0b1b5a491d20937bab1bf16', FALSE),
('91d0e41ce8239cee', 'client', $k282$Mode: <color=#FF9966>menu music is set to None - change it in Settings</color>$k282$, 'd6be16ee6ad11c21c61667420b3ea858ce6fef2d', FALSE),
('93242dc563a40eaa', 'client', $k282$Yeah$k282$, '5bf308cf1d016503a4a74b2849cc00b563192617', FALSE),
('933131317eca7e8d', 'client', $k282$Each unlocks once per account and pays on the spot: most pay 100g; the hardest pay 300g, 500g or 1000g.$k282$, 'ed3b73cc402c48f39ce1b90ef1d8947bda12267d', FALSE),
('934ede0ef4f25930', 'client', $k282$Are you good at this game?$k282$, '427951d00b193b43a44cfc0af03c9d67cf6edb60', FALSE),
('93ad7abdc83e80b3', 'client', $k282$local fight simulation$k282$, '478712e443993e3d89008450795a14a38a876383', FALSE),
('95a1dd042c370b2a', 'client', $k282$Emote dances for the hold-E wheel. Your character busts the move for everyone running the mod - but your own controls lock until the dance ends, so dance wisely.$k282$, 'a672274429e29ead95f174ff943a96fd99e2de74', FALSE),
('96e1ded8751a35de', 'client', $k282$(menu only)$k282$, 'da41f778f7ed3ad1dbcef4e78c5582014b07121a', FALSE),
('974671d54b95adb3', 'client', $k282$series ends$k282$, 'bad9bfbb27bf708a96616e3cb17bf14ecb178567', FALSE),
('9789ec57aacffa6f', 'client', $k282$Preview: {0}$k282$, '680bce4b84ac071af8bf71cc98932d5dde018070', FALSE),
('97ed03fa320e46f3', 'client', $k282$Soft pink shimmer. Deceptively innocent.$k282$, '8e9ab1eb27d0a3fe5bff1c54133eb397a100592a', FALSE),
('9861281a93a3c0c0', 'client', $k282$5-10 damage: no Refresh$k282$, 'e3ee0a9ff9034e3b2ca8c19b278b01ac6248cc55', FALSE),
('99396dedb5f2d0cd', 'client', $k282$The Robot$k282$, 'f97d3b31bdb725fbe43f10f3481dba557c7aa946', FALSE),
('99c7f1983a568f7e', 'client', $k282$confirmed - admin tools: ban, reversal$k282$, '05599a662494b836496c17e39d7810966b42c27b', TRUE),
('99ff6d9d5d869554', 'client', $k282$on the boards and in chat$k282$, 'c3f2d0282552ceccb72ae077467142fd8eb4b486', FALSE),
('9bb3752670ea25f8', 'client', $k282$Mode: <color=#DDDD66>loading custom music - vanilla plays meanwhile</color>$k282$, '69ed28b1105d8d9da2f97744cfa4365f1058cff5', FALSE),
('9c3600034286ad0a', 'client', $k282$Thunderstore$k282$, '6bc6c5a526fc83f0257710772097ebe1885b2b2b', FALSE),
('9d39ae971605ed24', 'client', $k282$LOCKED$k282$, 'da6bac2901375736cf9f663da7a9942169e4774f', FALSE),
('9d452a3cc7e4d696', 'client', $k282$What other players can and cannot see of your mod. The short version is a guarantee: <color=#7FE87F>the only things a non-modded opponent can ever see of the mod are your nametag styling and the quick-chat phrases you choose to send.</color> Quick chat is chat, not a cosmetic - it goes out through the game's own chat bubble, exactly like a typed message. Everything else either needs the mod on the viewer's side or never leaves your machine.

<color=#FFD94D><b>WHAT A NON-MODDED OPPONENT SEES</b></color>

<color=#7FD4FF>Nametag styling - visible, with two exceptions below.</color> Formatting (bold, italic, underline, strikethrough, float), solid and neon colors, sizes, caps and spacing transforms, rainbow and the gradients all render on a completely unmodded client. The mechanism: the mod writes the style into your Photon nickname as rich text, and vanilla's own name labels already render rich text - players were putting raw style tags in their Steam names long before this mod existed. That's why this one class is allowed to cross.

Two nametag styles are the exception and render mod-side only:

- <color=#7FD4FF>Glows</color> - applied locally on modded screens. A vanilla opponent sees your name without the glow (any other styling you stacked still shows), and no leftover artifact.
- <color=#7FD4FF>Typefaces</color> - a local font swap. A vanilla opponent sees your name in the default font.

Everything else shows a non-modded player nothing:

- <color=#7FD4FF>Face cosmetics</color> - the item ID travels over vanilla's own face channel, but a vanilla client doesn't know the ID and renders an EMPTY slot instead. No crash, no fallback item - that slot is bare on their screen, and any vanilla face parts you wear still show normally.
- <color=#7FD4FF>Trails</color> - nothing.
- <color=#7FD4FF>Body colors</color> - they see the default team orange/blue.
- <color=#7FD4FF>Auras</color> - nothing.
- <color=#7FD4FF>Titles, chat styling, Hide Gold</color> - these only exist on mod surfaces (the F5 overlay, T-chat, Discord). Vanilla has no place to show them.

<color=#FFD94D><b>WHAT A MODDED OPPONENT SEES</b></color>

The whole catalog: your face cosmetics render fully (the art ships inside the mod), plus your trail, body color, aura, nametag glow and typeface, and your title on the boards and in chat.

Three caveats:

- Modded viewers can individually opt out of trails, body colors, and animated cosmetics in Settings - your cosmetic renders only for viewers who left those on.
- A body color also becomes your team identity on modded screens: point announcements, the round-counter dots, and the FFA score strip use it. A viewer with that setting off sees plain vanilla teams.
- Titles never appear over your head in-match, for anyone. They render on the F5 boards, in T-chat, and on Discord only.

<color=#FFD94D><b>WHAT NEVER LEAVES YOUR MACHINE</b></color>

- <color=#7FD4FF>Map skins</color> - never networked at all. Nobody sees your map skin, modded or not: every player sees their own equipped skin, or vanilla. Equipping one changes exactly one screen - yours.
- <color=#7FD4FF>Cursor color and shape</color> - your own cursor, on your own screen.

<color=#7FE87F>Your cosmetics never produce a broken visual, an empty rectangle, or a crash on a non-modded screen.</color> <color=#8A8A93>One early glow implementation did leak a visible rectangle to vanilla clients - it was removed for exactly that reason, and glows have rendered mod-side only ever since.</color>$k282$, '667404cccb112645b3632eca1c8ed8b4a0c12407', TRUE),
('a056950ff82a33c6', 'client', $k282$Toxic Spill$k282$, '1660bad3f82d6d49f38461bde6cfddfe9830caae', FALSE),
('a0b809cf10f75d41', 'client', $k282$Flair text shown next to your name on the leaderboard, match history, and in chat.$k282$, '692f254e30158dac89e251017eaff0948bcc4bf7', FALSE),
('a0fd44d7de2285c6', 'client', $k282$Disco Fever$k282$, 'c582339cc3887c3a38bfa00b7a7c8e9ff54b118c', FALSE),
('a274aad4509f84e6', 'client', $k282$THE SOLO$k282$, 'ff0a085bff181fc81a692033955e81c60b5eed54', FALSE),
('a2f116ee16145bcb', 'client', $k282$NOT RECORDED$k282$, 'e159f84a4239ebdebbb028d2c001ae78b388aa1a', FALSE),
('a352871ddde71056', 'client', $k282$Paused: {0} - {1}$k282$, '672504530777b1b681d9f21d05eddcb13559c535', FALSE),
('a35754f4e143ed36', 'client', $k282$The Bounce$k282$, 'ba6f9d8321e8ac1ce86fc8e723247cfb4453cfa8', FALSE),
('a37e12e0c7749da9', 'client', $k282$COMPLETED SERIES$k282$, '1231f90b40c299944a06340b5ca7e8a2f92e4170', FALSE),
('a3825c2ab956ca64', 'client', $k282$your trail$k282$, '6287c791cf7634cffd62a205b30593f7bc398ca0', FALSE),
('a39001b83c5b81c1', 'client', $k282$Team 1: orange$k282$, '1f9a8b41a664901e7686ee4caca99a56d3beee86', FALSE),
('a41a6a516319d6c0', 'client', $k282$Community artists supply a large share of the catalog and earn a 30% royalty on every sale - gifts pay no royalty.$k282$, '30833899ea88dc9cb31c326cc8c85a2666cda7de', FALSE),
('a4255a4114972113', 'client', $k282$match goes live$k282$, '861be15995b350b7675a1c2783e64e1d6d1e2414', FALSE),
('a54351b7fa8f4bf7', 'client', $k282$under 5 damage: nothing; state unchanged$k282$, '5f8ea57e0f4aa31e85b064a66d579d79972eb768', FALSE),
('a662402c35b6f0bf', 'client', $k282$both Ranked$k282$, '58632221da3c855ed9e898cb8e3496ec9c4a261e', TRUE),
('a719629c97ed0c38', 'client', $k282$REFRESHVALID STATE MACHINE$k282$, '80906f59d6ca0f6e312bafd4c6582951097803b6', FALSE),
('a907a9bcecb375bf', 'client', $k282$Jumping Jacks$k282$, 'e5296ed2f8b67d8cc42d2dc7ff153822c1575f4e', FALSE),
('a9260e7026739931', 'client', $k282$blocking: 0 damage + 2x return impulse$k282$, '83e43e66b11a38d83ba77abdfad13d330f58e224', FALSE),
('a952b80387530503', 'client', $k282$can't be altered in transit$k282$, '02947f4f39f84289021e16e1b6436a5e33a0b16c', FALSE),
('aa98c15b3fd5db76', 'client', $k282$Music credit toast: <color=#FF9966>OFF</color>$k282$, '30c66db52a244cf8b873a828ba4941dc3bf1b105', FALSE),
('ab3f5cd6e8d0692c', 'client', $k282$room type?$k282$, 'b6d58313c976fea70b5d632b3f1250c39de2282c', FALSE),
('abe8e5a9fd37471a', 'client', $k282$mod-issued$k282$, 'aa50bfd83ec8c8109f2b439405fd8292fadace98', FALSE),
('ac354c1e95bc9f0d', 'client', $k282$Lagoon$k282$, '24ebe978ab7453659552dbeb029bebba00495fe3', FALSE),
('acf6218467f33f12', 'client', $k282$tracks the whole game$k282$, '6f2c72bec243a655d2179316134a66cc9d19533e', FALSE),
('ad11b6f7ca557add', 'client', $k282$Albums have unlimited stock$k282$, '05353af9d3b5d51ef1e6ad31b9a4042675e7a13c', FALSE),
('ae24752fcf1f3aee', 'client', $k282$Un-stacked, full flight. The mod pins every eligible Grow bullet to the same 240 FPS growth clock.$k282$, '3c688a6b39eb7b8e1a0d5c5f4759c3a79586679f', FALSE),
('ae2dc0c4a783a120', 'client', $k282$<color=#FFC8F0>=  DANCES  =</color>$k282$, '2b08101b6b9bc6d8943aacefab6589145b277707', FALSE),
('af192920f8bd310e', 'client', $k282$first team to 2 games$k282$, 'f48902bd433ae6ef4d653cc3eff2ed4d03a50591', FALSE),
('afcf70b297ca5d26', 'client', $k282$<color=#888>(click the row to preview tracks)</color>$k282$, 'c64430c93ebef3dbe560293a486c6b3b5785e504', FALSE),
('afecea29bc7bb5b5', 'client', $k282$HOW A COSMETIC REACHES YOUR BODY$k282$, 'd732cf6647f10509dfd37d789f659c18dce662c4', FALSE),
('affd5382eaca97d3', 'client', $k282$1v1 Podium$k282$, '3f4bed95c640cfa39f522b142b1ae86ed421fee3', FALSE),
('b10f784abe59d8ef', 'client', $k282$A MODDED PLAYER SEES$k282$, '0ed3ea4113b2726f9870b87104a8eea6a7e5e2d8', FALSE),
('b1d1da9612c4011d', 'client', $k282$wall touch refreshes all jumps unless you jumped within the last 0.15s$k282$, '6dde9dc4ea9619bfcd9b8dcbc48605479fb1cbf9', FALSE),
('b272a9274980ddf9', 'client', $k282$Ember$k282$, '20632bc30721b7b1111cc82ebfe4420e4ad7d5d8', FALSE),
('b2b856cabfe69155', 'client', $k282$WINNERS FINAL$k282$, 'e466f5b100a24b17e640948976a1fef4fe86681f', FALSE),
('b447f84a0cecd9e6', 'client', $k282$over 10, outside 0.35s: Refresh; set false$k282$, '9532d22227de6928e6b0dd3e54e9c0afeed8738a', FALSE),
('b492fedfe366aaf0', 'client', $k282$If no earlier rule settles it, score, check-in, no-show rate and a fixed tiebreak decide.$k282$, 'b3c71efa1b2e2068d719a2aa9dab639c4e5aa362', FALSE),
('b618aff81c272358', 'client', $k282$Sync Champion$k282$, '7356f9d83ad3ebef5aa96ab01b52e61f12c1cbe6', FALSE),
('b652886c9f750c58', 'client', $k282$impossibly fast series$k282$, '8358d9cff2953c92267bb21092fff91232279340', FALSE),
('b6c259ff73599f88', 'client', $k282$GAME ENDS$k282$, '256eaeedbdddb39dbb730009c35d8a52e25f9a61', FALSE),
('b7465dcd1fcafeca', 'client', $k282$What happens when someone doesn't show up, quits, or leaves a tournament - and exactly how prizes are computed. Short version: <color=#7FE87F>a finished series always stands</color>, absence is what gets punished, and forfeit wins never pay podium prizes.

<color=#FFD94D><b>DEADLINES</b></color>

- Sync: matches give a 10-minute show-up grace from the moment they go ready. A match that follows a PLAYED match sits in a 7-minute breather first (a bye-fed match can go ready immediately), and a match still in its breather can never forfeit anyone. While both players are present the server waits - a sync match can run past its deadline.

- Async: every match, the grand-final reset included, has a 7-day deadline from the moment it goes live. The deadline check-in DM can extend it 24 hours, once per opponent. Presence doesn't spare an async match - only playing does.

<color=#FFD94D><b>WHEN THE DEADLINE HITS</b></color>

The server resolves an overdue match in this exact order - the first rule that applies decides it:

- 1. <color=#7FE87F>A finished series always stands</color> - nothing overrides a played result.
- 2. If exactly one seat is banned, the other player advances immediately.
- 3. A game reported in the last 45 minutes means a live series - the match is left alone.
- 4. Sync only: both players present - the server keeps waiting.
- 5. Exactly one player present - <color=#FF6666>the absent player forfeits</color> and the present one advances.
- 6. Otherwise: if the series was started and the score is uneven, the score leader advances. Failing that, if exactly one of you answered the async deadline check-in - any answer - that player advances over the silent one. Failing that too, the lower no-show % advances, and a dead tie falls to a fixed arbitrary tiebreak.

Only absent seats get the no-show mark (a banned seat forfeits regardless of presence, and a silent seat can lose the async tiebreaks while present). Your <color=#7FD4FF>no-show %</color> is a rolling 90-day rate that decides your priority into future tournaments, backfill order, and these tiebreaks.

<color=#FFD94D><b>WHAT A FORFEIT DOES - AND DOESN'T</b></color>

- The bracket advances exactly as if the match completed - the winner moves on, the loser drops or is out.

- <color=#FF6666>A forfeit mints nothing.</color> Podium placements only exist for played, completed series - a forfeit-decided podium spot pays no prize.

- No rating moves. Rating only changes when a series completes; a forfeited match's series is simply never completed or scored.

- Betting closes: a forfeited match's series can't be bet on.

<color=#FFD94D><b>LEAVING, AND WHO REPLACES YOU</b></color>

- During voting: un-sign freely.

- After lock, before the start: the backfill flow runs - the most reliable speculative signup takes your exact bracket slot (with their own rating); no speculative available means your would-be opponents get byes. Leaving this way carries no penalty.

- Once running: you can't un-sign. Not showing up forfeits your matches and counts on your no-show %.

- Quitting mid-game follows normal 1v1 disconnect rules: the DC lands on your leave %, and unless your opponent was at match point (then they take the game, which can finish the series) the series stays open at its score. The deadline sweep resolves an abandoned series: after the 45-minute grace a still-present opponent wins; if both walked away, the score leader advances.

<color=#FFD94D><b>THE RANKED OVERRIDE</b></color>

- When one of your tournament matches is live and your Ranked toggle is off, the mod flips it ON and tells you. Async matches happen in private lobbies, which only record as ranked when both players have Ranked enabled - the override guarantees your result records.

- <color=#FF6666>It stays ON after the match.</color> There is no auto-revert: turn it off in Settings if you don't want later games rated. Turning it off between tournament matches gets it flipped back on when your next match goes live.

<color=#FFD94D><b>PRIZES, TROPHIES AND BETTING</b></color>

- The pool scales with the player count snapshotted at lock. At 8 players: 1000 / 600 / 120 Gold and 5000 / 3000 / 150 XP for 1st / 2nd / 3rd. It grows linearly with the field, doubling at 16 players: 2000 / 1200 / 240 Gold and 10000 / 6000 / 300 XP.

- <color=#7FE87F>Prizes pay when the whole bracket completes</color>, not when your final match ends. A forfeit-decided rank is skipped rather than passed down.

- <color=#8A8A93>Prize XP behaves like any other XP: it converts to Gold at the usual 100 XP = 1 Gold, and a level boundary it crosses pays the normal level reward.</color>

- Trophies are Discord roles: SCR Tournament Winner, Runner Up, and 3rd Place; a second same placement upgrades the role to its (x2) version. Every confirmed participant gets the Participant role. Roles only go out for brackets of 16 or more players. Winning or taking 2nd in a tournament also unlocks a paying achievement (separate ones for sync and async), and playing a bracket through without ever forfeiting unlocks Iron Bracket.

- Every tournament game is a normal ranked best-of-3: it moves your regular 1v1 rating whether or not you reach the podium.

- Tournament matches are bettable on the same terms as any live ranked series: betting locks at 2 live points in game 1 or once any game is decided. An async pairing that waits days stays bettable the whole wait at 0-0.$k282$, '28b99c3f6732cdc8eac5aed4e05cf8c47868fba6', TRUE),
('b8b614d78b815e1f', 'client', $k282$PHOTON CLOUD$k282$, 'bb41346607f1ed37851b0126c59333ae05444d97', FALSE),
('bb0cbec539928a34', 'client', $k282$optional extra opening pick$k282$, 'c60f08db0bad1ed802b2acf74f4b6d03af15d01c', FALSE),
('bc49fa6684de77c3', 'client', $k282$AFK: zero shots, blocks, picks$k282$, '5ae5564648a3decf4f1564b4f1973cfc7ca0d622', FALSE),
('be14fd775fc8c284', 'client', $k282$Music files failed verification - press Retry$k282$, 'bd2754668fb8f42a6f97ec724714677c6f41d803', FALSE),
('be9eea5c45cb8307', 'client', $k282$+ {0} more artists$k282$, 'ea0646b8da2ad450dbcd915b4bf8b8ad9b500d0d', FALSE),
('bea16a781a4dd7d5', 'client', $k282$one 2v2 rating outcome$k282$, 'e5398f883daa5f89eb09ddf30c9d5b97f7ec8978', FALSE),
('c0a0607f3e2d6394', 'client', $k282$game 1 starts$k282$, '3eaf750e8d8107db4ca83f8176b53e0e3a3e30e4', FALSE),
('c221bbb17e0f44d6', 'client', $k282$Map color schemes. Equip as many as you like and cycle between your owned colors with Left Shift in-game.$k282$, '792d1bb864cc19bcaf69fc46f39ecdfeabaf85f6', FALSE),
('c372037f23bf8282', 'client', $k282$events and streamed state$k282$, '95a3328110c7692a26084ccda18cf878c13df0d3', FALSE),
('c3d2282d14e75714', 'client', $k282$Rapid-fire shoulder shake with pulsing arms. Dancing locks your controls for the duration.$k282$, '6a446a531aa163cbfb6355753f8ff17e98c909b3', FALSE),
('c3ff7b61de7b2cb2', 'client', $k282$A NON-MODDED PLAYER SEES$k282$, '7a7005c30bcb5cd09fb1489f56c4acbf5968dbf1', FALSE),
('c612c77fc68ea0c9', 'client', $k282$Every tournament runs through Discord DMs from the SCR bot. None of them reach you unless your Discord is linked (F5, Discord Link tab). The big notices (lock, match live, results) are durable - if the bot is down when one fires, it retries until your DM lands. The play-day nudges (starts-in-15, next-up, waiting-on-you) are best-effort and can be missed across a bot restart.

<color=#FFD94D><b>BEFORE THE TOURNAMENT</b></color>

<color=#7FD4FF>Availability check</color> - sent 1 to 4 days before lock, once the tournament has enough players. Two buttons:
- 'Yes, I'm in' - edits the message to a confirmation. It changes nothing on the server; you were already signed up.
- 'No, remove me' - removes your signup, exactly like un-signing in game. No penalty.

<color=#7FD4FF>Lock DM</color> - you're in. Sync: your start time plus the contract (have ROUNDS open at that time). Async: how to coordinate and play. If the server last saw you on an old mod version, an update warning is appended - update before you play. No buttons.

<color=#7FD4FF>Removed at lock</color> (sync) - the field agreed on a time you didn't mark as available, so your signup was removed. No penalty; sign up again next week.

If the lock pushes back a week instead (too few players, or no time slot 8 players agree on), a fresh availability check goes out for the new date.

<color=#FFD94D><b>SYNC PLAY DAY</b></color>

<color=#7FD4FF>Starts in 15 minutes</color> - open ROUNDS now and sit at the main menu; the mod does the rest. Also posted in the tournament channel.

<color=#7FD4FF>Match ready</color> - your match vs X is ready, get in ROUNDS now. <color=#FF6666>A no-show forfeits in a few minutes.</color>

<color=#7FD4FF>Next up</color> (rounds 2 and later) - your next opponent and start time after a short breather, no rush. Want to play right away? You BOTH press Play Now on the F5 Tournaments tab.

<color=#7FD4FF>Waiting on you</color> - sent when your ready match is under 90 seconds from its no-show deadline, or sitting past it while you're marked present. It means: get to the ROUNDS main menu and leave any casual game. Repeats at most every 5 minutes.

<color=#FFD94D><b>ASYNC MATCHES</b></color>

<color=#7FD4FF>Match is live</color> - your opponent, the 7-day deadline, and how to play: agree a time, host a private lobby together, the result records automatically.

<color=#7FD4FF>Still pending</color> - once your match has sat ready for 3 days unplayed, a daily reminder with your deadline and how to coordinate. No buttons.

<color=#7FD4FF>Deadline check-in</color> - sent in the final 24 hours before your deadline. Three buttons, and your latest answer replaces earlier ones:
- 'Yes - we plan to play today' - recorded, and <color=#7FE87F>extends the deadline 24 hours</color> - once per opponent per tournament. Pressing it a second time records the answer but the deadline stays put.
- 'I reached out - no response / they quit' - recorded.
- 'Not yet - still coordinating' - recorded.

What an answer is worth: if the deadline passes with the match undecided and neither player ahead, <color=#7FE87F>a player who answered the check-in - any of the three answers - beats a player who stayed silent.</color> The full resolution order is in <color=#7FD4FF>Deadlines & forfeits</color>. Buttons re-check that your Discord is still linked to the same account before acting.

<color=#FFD94D><b>RESULTS</b></color>

After each match, both sides get a completion DM that's honest about how it ended: a played win says you won; a forfeit says 'You advance - your opponent forfeited'; a mutual no-show says 'You advance on the no-show tiebreak'. A forfeit is never dressed up as a played win.

When the bracket completes, the podium is announced in the tournament channel. Trophy roles are handed out only for brackets of 16 or more players; smaller brackets keep their prizes and achievements but hand out no Discord roles.

<color=#FFD94D><b>COMMANDS AND THE BOARD</b></color>

<color=#7FD4FF>/dm-opponent</color> followed by your message - the bot relays it to your current tournament opponent's DMs. Limited to 8 messages per minute.

<color=#7FD4FF>/opp-online</color> - checks whether your tournament opponent currently shows as online on Discord.

The tournament channel keeps a living board for both tournament kinds, refreshed every 2 minutes.$k282$, '78efcc153076dcd201fc27282452c0dd0c62e4f9', TRUE),
('c61fa7034ff70a0e', 'client', $k282$yes$k282$, 'fb360f9c09ac8c5edb2f18be5de4e80ea4c430d0', FALSE),
('c748f274fd740798', 'client', $k282$touch wall while holding into it$k282$, '661e06440fb85ef6750ea1fa15b10d3d1d12096c', FALSE),
('c952a39f8d2c92f3', 'client', $k282$casual FFA and 1v2 = recorded, not rated$k282$, 'd4e4e53c827126fca1c39f8ee242bc7e1857b9a7', FALSE),
('c9a9a504784c0fdd', 'client', $k282$<color=#FFA070>=  BODY COLORS  =</color>$k282$, 'bcca96d7c97b106a652be1b5520bf9861a73b560', FALSE),
('ca40e68882698352', 'client', $k282$Q (hold) - quick-chat wheel, release to send$k282$, '03d2d9f81c45084e0afbb42bab8d676369477d72', FALSE),
('ca67f6bba15bf734', 'client', $k282$You don't own any dances yet - check the Shop's DANCES section!$k282$, 'f3dbe5f67e8948cd7dab46f833832ddc3020a155', FALSE),
('caff242c617e9b2c', 'client', $k282$room code$k282$, '9b2aab6b06a8501fc157f91e020a7376de7c5078', FALSE),
('cb214dd8fdcdef80', 'client', $k282$one present: absent player forfeits$k282$, '5bfb30cdbd1b6e637c5e3fdd9b7cc5cbc4498c7b', TRUE),
('cb6770434c10f8c3', 'client', $k282$Sway and wave to the crowd. Play it between rounds with the E wheel.$k282$, '00d3b5a6efce0c118a61bcc07602e886b96a9ca4', FALSE),
('cb93e4d862f0d5d8', 'client', $k282$no - casual$k282$, 'b385fed762cbac170a73be10adb8a477f1761794', FALSE),
('cbc8740b1695a190', 'client', $k282$Menu music: <color=#FF9966>None</color>$k282$, 'af1789e79d5ee6ea9fa8d5ec234ff48c8db3e8b9', FALSE),
('cca48f0cfd3864b2', 'client', $k282$Most Stacked$k282$, 'c2a50d949d2b8b52c35753dee3c405940bad2ac2', FALSE),
('ce0e1f95541897c6', 'client', $k282$kill boundary$k282$, '4cbe09f6351f1f3546faeafe30805718ab64e2a4', FALSE),
('ce473d718d21724f', 'client', $k282$Mode: <color=#FF9966>stopped - press Play or Use vanilla music</color>$k282$, '4682e10052d183bd1b01ae10f9420e7a8baba6b2', FALSE),
('cee62f37b4113baf', 'client', $k282$Win rate holding this card (ranked games only)$k282$, '78c5fbf3c125733d57b79e440509b7494ac71551', TRUE),
('ceee15a894860be2', 'client', $k282$Ranked Win Rate$k282$, '758692850822b2769fe7459a6ba3ded3dd35e5cc', TRUE),
('d170dbccf38117ac', 'client', $k282$over 10 inside 0.35s: treat as Conditional$k282$, 'cf083d74ed75bf0158f1c485f1c87ab9b2ec1b4b', FALSE),
('d2e1c859dbdcdf34', 'client', $k282$Earned$k282$, '257f305b043a469cf483af28b88025aeffa6e98d', FALSE),
('d32d128d5ac713ea', 'client', $k282$Loading shop sales...$k282$, '9757b29440e4b4ef49e94e10094e5706dbe5cb93', FALSE),
('d34a0d31083dd876', 'client', $k282$Boosters$k282$, '1be0a8f67aa11f43b03ea32d1dd277f75954722e', FALSE),
('d500172fde31785a', 'client', $k282$PLAYER 2$k282$, '675c88e46ce412aa6494219653a480445cc66633', FALSE),
('d6b2086f3537ac5a', 'client', $k282$art submitted in-game$k282$, '51965c0404a0449c99b8e16f493f6b7c5bd1ec18', FALSE),
('d77eb2ed30c92497', 'client', $k282$GRAND FINAL$k282$, '8f0a822b86368ce0db1e0c6a787e4c03742f7b35', FALSE),
('d7d5fc77fbb32d5f', 'client', $k282$Menu music: <color=#88FF88>My playlist</color>$k282$, '798a99d1d8ff14b5e88ac1facc0ac563d5377c0d', FALSE),
('d84edc438cf970b4', 'client', $k282$recordable setting?$k282$, '758f79de372b7abe0da36f7a47150319187a120b', FALSE),
('d89af6b095fa7a6e', 'client', $k282$the one automatic penalty$k282$, 'a9a4378b07fb2a7eb676e4d7a5babcd48893621a', TRUE),
('d8cf14d63c80e35e', 'client', $k282$<color=#FF8888>The price changed - check the new price and buy again.</color>$k282$, '9deec55bcab0c91176b8e30340256189cb1302b5', FALSE),
('d9253ed2b22e05f4', 'client', $k282$The guarantee: only your nametag styling and the quick-chat phrases you send can ever reach a non-modded opponent.$k282$, 'cc15912c399aa848c449dacc5e83fe084a0fa5f3', FALSE),
('d94f5b08f27af934', 'client', $k282$the styled name - minus glow and typeface$k282$, '77ca2284c1b7b0157881d45cb033ce75ddf1aab4', FALSE),
('db1c0f8507f229d7', 'client', $k282$duo: the whole right half$k282$, 'b8daf3245d0bb316337366d100c95c7e657c362f', FALSE),
('dbf4faef919486db', 'client', $k282$cleared - flags alone never punish$k282$, '85b95acdb74387a141ac27ee0aa79640ecfdfb13', FALSE),
('dc38ca0bb8c08c98', 'client', $k282$Team 2: blue$k282$, '7bb41e1db3a4c09552453ba3496fed9fc7b13845', FALSE),
('dc8ca2a55307498d', 'client', $k282$Quick chat$k282$, 'd6d2248bd5af439f06e478bb3297bce222bdb7f2', FALSE),
('dd01ededf1c8c18c', 'client', $k282$Best seller$k282$, '271330d994ea7546d2efc98de562966a6a530b38', FALSE),
('dd0cbe6d69e1e26b', 'client', $k282$Bright embers cooling into ash. Two-color gradient.$k282$, '464ed8f164b2f378ec5c9090ee0ac8b522b1c081', FALSE),
('dd2445017b5ffa41', 'client', $k282$earn gold by playing$k282$, 'f1fbdca78de260855c81cbd171d9379eb4c1394a', TRUE),
('ddcce7205b472382', 'client', $k282$Downloading music...$k282$, '8319e5a5268114bf58d0eb608ded75db9b2095a7', FALSE),
('de022e1f770c414f', 'client', $k282$Everything you leave behind turns gold.$k282$, '12a0d60f9f881a3edc74172253daa3ce062126af', TRUE),
('defcda03b0e04429', 'client', $k282$Name styling$k282$, 'cc26754a33fbc8129208643f3bb5fe69742c8053', FALSE),
('df0ebeb8748ad0fc', 'client', $k282$PLAY$k282$, '42c5cda0ffa59a8691d0bf44578f236901d42363', FALSE),
('e06b0ea27a685763', 'client', $k282$RefreshValid = false$k282$, '6fed6440264c173b26f2225b8cebd0eeae8b9a0d', FALSE),
('e128123d770ddbe2', 'client', $k282$YOUR CLIENT$k282$, '83788d4175517bd358cfab6754397adc8ccb40c5', FALSE),
('e181752d3a2abb1c', 'client', $k282${0} winning picks$k282$, '16c142f517d5cd3cc3b465b392c9ea438374786d', FALSE),
('e3dd7dfe3582f5e6', 'client', $k282$Shows a small bottom-left credit line naming the track and artist whenever a custom song starts.$k282$, '28a0d9d1ba64751d2992ae548aa39bcdbfc975ca', FALSE),
('e41cbfd220932ab2', 'client', $k282$The Wave$k282$, 'a0ad0ecead7d6f934d389fc1ccb31c50dbdeb30b', FALSE),
('e66cb18f68b63ea3', 'client', $k282$jump within 0.1s: up and away$k282$, 'e076f29122f30e52c0c072566963e93522d67fd6', FALSE),
('e6d82c7fecd456b5', 'client', $k282$<color=#FFB0E0>=  NAME STYLES  =</color>$k282$, '2f5b1a23c18d38b64e27517e40dd5a639ea270db', FALSE),
('e81331915974fd55', 'client', $k282$QF B$k282$, '9e10ff0f8b9d89c366d06e06ba24fd30da382f7a', FALSE),
('e9cbfed6a11d404e', 'client', $k282$Best-of-3: first side to 2 game wins. 1v2 is an unranked beta - every game is recorded, and no rating moves yet.$k282$, 'c4c85cf747ada8e52cc6035e7744b26c75a13e40', TRUE),
('ea66c841fb926192', 'client', $k282$REVIEW$k282$, 'ed6912ad70e7f5f44c4e228e2168918d894d50ce', FALSE),
('ec0db0eef9a77b84', 'client', $k282$Lifetime totals for your account, from the live server. The rules behind each source are in the article below.$k282$, 'fef54a0228deda825b33fcb615fc718603b433b7', FALSE),
('ec3ba28ef8180508', 'client', $k282$Ranked Picks$k282$, '1c0bdb37df4c2cc2ffd2c3090286f5e5399cfc7c', TRUE),
('ec58935c8e62aad7', 'client', $k282$click a phrase - Esc closes$k282$, '1a2420720ae16deb2834e7dcc92b8fa67fdf8c8f', FALSE),
('efa2db577712bf34', 'client', $k282$nobody - your screen only, never networked$k282$, '0462fea2f9874e1ca9333be1562c930ed280d248', FALSE),
('f0879faeb75eb0b1', 'client', $k282$Galaxy$k282$, 'f69ff6e8d889fd11305a1035f80d7cfb42c367f0', FALSE),
('f1ae60f8bed4f5b8', 'client', $k282$mod-issued: queue / 2v2 / tournament / ranked FFA = ranked$k282$, '4bf611ca20f506ef1cfbbe3c15e669598075a558', TRUE),
('f1f232b77a6b7397', 'client', $k282$Times picked (ranked games only)$k282$, '55ca1d6fd64c1aa2b8364c095427f5b23e923720', TRUE),
('f2b2d44102db58c5', 'client', $k282$Dance is on cooldown - try again in a moment.$k282$, '8b7c4dd82c77a28db0f41a622064aad9ee8b1ef8', FALSE),
('f2d0a7e6347ff683', 'client', $k282$The mod changes vanilla gameplay only where every player agreed to it. This page explains exactly how it decides, and what is guaranteed when you play with non-modded people.

<color=#FFD94D><b>THE GUARANTEE</b></color>

<color=#7FE87F>A non-modded player always gets pure vanilla gameplay, and any gate that can't prove a change is safe leaves it off.</color> Whole-room changes fail closed for everyone identically. The one per-player feature is poison sync, which follows the poisoned player - an unmodded victim's poison stays vanilla.

If the mod can't prove a feature is safe to run, it runs vanilla.

<color=#FFD94D><b>HOW ROOMS ARE CLASSIFIED</b></color>

Mode-tied gameplay runs only in rooms the mod itself created, and the room's name says which mode issued it:

- <color=#7FD4FF>ranked_</color> - 1v1 ranked queue rooms
- <color=#7FD4FF>team_</color> (or the 2v2 room marker) - 2v2 rooms
- <color=#7FD4FF>sct-</color> - sync tournament rooms
- <color=#7FD4FF>ovt_</color> - 1v2 rooms
- <color=#7FD4FF>ffa_</color> - FFA rooms, and only while the FFA lobby engine is actually active

A public quickplay room or a normal 6-character room code matches none of these, so every mode-tied gameplay change stays off there.

<color=#FFD94D><b>CAPABILITY GATES</b></color>

Changes to the shared simulation go a step further: each player's mod advertises a capability tag BEFORE joining the room, so any client that can even see you has already received your tag. Then:

- <color=#7FD4FF>Grow normalization</color>, <color=#7FD4FF>FFA map-object scaling</color> and the <color=#7FD4FF>FFA same-card dealer</color> require EVERY fighter's tag. <color=#7FE87F>One vanilla player, one outdated mod, or one player whose mod disabled itself switches the feature off for the whole room - symmetrically, on every screen at once.</color> Nobody plays by a different rule than their opponent.
- <color=#7FD4FF>Poison sync</color> activates per victim, in any online room: a current victim's own client judges their poison; an unmodded victim's poison stays vanilla. The mixed-room details live in <color=#7FD4FF>Poison & damage over time</color>.
- Spectators never count toward or against these checks.
- If a feature's patch fails to install, that client never advertises the tag. If any other BepInEx mod is detected at startup, the whole mod disables itself and revokes its tags - full vanilla behavior.

<color=#FFD94D><b>TWO KINDS OF FIXES</b></color>

Not everything is gated, and the distinction matters:

<color=#7FD4FF>Crash prevention</color> - always on, everywhere, quickplay included. These guards stop vanilla bugs like the frozen-inputs-at-match-found crash, the permanently dead Escape key, and the Phoenix revive crash. They change no rule: each one replaces a crash or a broken state with what the game intended.

<color=#7FD4FF>Gameplay changes</color> - gated as above. Mode logic needs its mod-issued room; Grow and the FFA features need the full-room capability check; poison authority is per-victim as described.

Between the two sits a band of local repairs (re-registering vanilla's own broken bullet effects, clearing a stuck auto-fire flag between games) that run in any game - but these only repair your own screen's bookkeeping toward what the bullet's owner already decided. They never change a rule, and can't create a disagreement vanilla didn't already have. The full inventory is in <color=#7FD4FF>Bug fixes the mod ships</color>.

<color=#FFD94D><b>QUICKPLAY WITH THE MOD</b></color>

Playing quickplay or a room code with the mod installed, you get vanilla rules plus tracking: your casual results and stats still record, and achievements can still unlock. <color=#8A8A93>A recovery guard can also restart a dead quickplay search for you - that is connection plumbing, not gameplay.</color>

Two fairness fixes can reach quickplay and room-code games: <color=#7FD4FF>Grow normalization</color> (every fighter current, everyone's Ranked on at connect - both sides always agree on it) and the per-victim poison sync, which follows the poisoned player wherever they play (see <color=#7FD4FF>Poison & damage over time</color> for the mixed-room details).

<color=#7FE87F>And your opponent never has to know the mod is there unless you talk to them: the only things a non-modded player can ever see of it are nametag styling and quick-chat messages you send</color> (see <color=#7FD4FF>What unmodded players see</color>).$k282$, 'a415c1bcab4833e32dd4d2f7760f355aca5d935b', TRUE),
('f2f9b149b9bdc2ff', 'client', $k282$Quick chat is on cooldown - one message every couple of seconds.$k282$, '34f4ba41ace1cf468ce976bb2d07104bfcb302a1', FALSE),
('f2ffe8af3edaa0a5', 'client', $k282$<color=#FFD94D><b>THE KEYS IN PRACTICE</b></color>
F5 works everywhere - menu, lobby, mid-game. While the menu is open your inputs stay out of the game: clicks do not fire your gun, Space does not ready you up, and Escape only closes the menu - it will not cancel a match that is connecting. Close it and everything flows again.

Chat has three doors. T types a message, holding Q opens the quick-chat wheel - point at a phrase and release to send it, or pick More... for the full list - and Enter still opens the vanilla box - the mod leaves it alone. M cycles the chat overlay display mode.

Holding E opens the emote wheel - even mid-battle: point at a dance you own and release to play it for everyone running the mod. Your own controls lock until the dance ends, and the dance stops if you get knocked around or fire. Dances are bought in the Shop's DANCES section, where Preview shows the exact moves.

Hold Tab during a match for the live scoreboard: score, cards, accuracy and connection info for everyone in the room, without opening the full menu.

Shift swaps between your equipped map color skins as a new round paints in. If you have none equipped, it does nothing.

Vanilla rebinding lives in the game options; the mod keys themselves are fixed. For what to practice with all of this, read <color=#7FD4FF>Getting better</color>.$k282$, 'e381da8384a70e3b854918ffa0340328e99a7890', FALSE),
('f3d6ba57b5fb6eaf', 'client', $k282$game server relay$k282$, '9752a30de8b8b560ac88841e9d20469390e55604', FALSE),
('f4d726ae9f55a9fe', 'client', $k282$Stardust$k282$, '53cb1f455d882f798601207af0839bff46ad3b46', FALSE),
('f538fc29da07e500', 'client', $k282$<color=#A0D4FF>=  TRAILS  =</color>$k282$, 'cf3c872f8fb22c2234c807eaa7edd9a9e2d07c1f', FALSE),
('f604cbceb3fd8af0', 'client', $k282$point + release Q to send$k282$, '1312c12a42b9a5d0d5417d78e7ded8fa439e98a0', FALSE),
('f63dc62e1917bfe1', 'client', $k282$SF A$k282$, 'ddcb991b57e50d9e3d28f6969711a34b411c5a79', FALSE),
('f6e7a6de91dd5197', 'client', $k282$Precision-stepped poses, one servo at a time. Dancing locks your controls for the duration.$k282$, '6d1039cf610e6208ecf5f37f7debd6ad05afa84c', FALSE),
('f7a22af2b0e1e50b', 'client', $k282$Fireflies$k282$, 'b6ab482e980abd109633aac2a2d069bcc17bedda', FALSE),
('f8911a22f310a60e', 'client', $k282$an empty slot - no crash, no fallback$k282$, '9c22dec522b1a7430c72799f83d17ab2283012af', FALSE),
('f96d89a65de6bc21', 'client', $k282$also locks when any game is decided$k282$, 'd8010d74929ce9a0815f1768239e5630c11eea1e', FALSE),
('fbe88305123b5f30', 'client', $k282$1V1 BETTING WINDOW$k282$, 'd254ab8e5f7189a6076b2a12d4502e9ec8f8a59e', FALSE),
('fc5ddef17a60d95a', 'client', $k282$Sync Finalist$k282$, '38ecddf69e8409bc60fb8e1f9bcbc3d7ef5c603b', FALSE),
('fddf3191109ad367', 'client', $k282$Map skins$k282$, '3f5e663ffe95270650b331c4256b3a81fbff7c68', FALSE),
('fe155ed1d897c0ce', 'client', $k282$everything, glow and typeface included$k282$, 'ac7d200fa1ec6ce18c2d700dbaef2f32e2a9efa4', FALSE),
('fe55f5cffac7f3b9', 'client', $k282$LOCK: 2 total points$k282$, '43bbf6ddbbd6c835b405870a184d3714afa6b12d', FALSE),
('fed41b1541e5ebd2', 'client', $k282$Now Playing: {0} - {1}$k282$, '182fb22139d51c8a8129e6ed9c2391f7d226eb32', FALSE),
('ff0b8a8cff784697', 'client', $k282$Music credit toast: <color=#88FF88>ON</color>$k282$, '7f8a9cb51f9b131918fcb642bde7c062c1cbed24', FALSE),
('ff24240b91d77c97', 'client', $k282$Downloading music previews...$k282$, 'f0bc18fb5a18627d161794eb9056a83fe3ba03fd', FALSE)
) AS v(key_id, namespace, msgctxt, source_hash, sensitive)
ON CONFLICT (key_id) DO UPDATE SET retired_at = NULL, updated_at = NOW()
  WHERE i18n_keys.source_hash = EXCLUDED.source_hash;

DO $$
DECLARE v_live INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_live FROM i18n_keys WHERE namespace = 'client' AND retired_at IS NULL;
    IF v_live <> 2427 THEN
        RAISE EXCEPTION 'post-check FAILED: % live client keys, expected 2427', v_live;
    END IF;
    RAISE NOTICE 'post-check OK: % live client keys', v_live;
END $$;

COMMIT;
