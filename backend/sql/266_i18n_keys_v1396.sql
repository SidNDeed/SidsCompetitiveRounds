-- 266: i18n client keys for v1.39.6 (109 NEW keys: the Aug-30
-- seven-item batch's UI strings (Info-tab visuals, LEAVE MATCH row, first-timer
-- hint), the chat-moderation batch's 18 strings (migration 265 seeds against
-- these and RAISEs on an unsynced database), and the shop display strings for
-- the five v1.39.6 community faces plus the other approved-but-unshipped
-- submissions (248's precedent — the snapshot query takes all shop_items).
-- This is the additive half of what POST /admin/i18n/sync-keys does, written
-- through the migration channel because this seat's tooling cannot sign the
-- admin HMAC (learning #443). Verified against the live table before writing:
-- the extractor manifest (2071 client keys) retires NOTHING (all
-- 1962 live keys are still in the manifest) and changes no English
-- (key_id derives from the source string, so a shared key_id cannot carry a
-- moved source_hash). A plain insert IS the endpoint's effect for this
-- release. key_id = sha1("client\0" + English)[:16], source_hash =
-- sha1(English), sensitive per tools/i18n_sync_keys.py's SENSITIVE_MARKERS
-- (imported, not copied). Idempotent; explicit transaction (#340).
-- The game namespace (242 keys) is unchanged this release.

BEGIN;

INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, max_px, context, updated_at)
SELECT v.key_id, v.namespace, v.msgctxt, v.source_hash, v.sensitive, NULL, NULL, NOW()
  FROM (VALUES
('00066ff57ca04552', 'client', $k266$Higher placement takes a bigger share of the pot; the pot itself scales with lobby size, battles played and opponent tier.$k266$, '5e5ecdae061097113bb0fc42625366227134dd5a', FALSE),
('0156bb7493bde398', 'client', $k266$WASD - move.  SPACE - jump$k266$, 'ebfc95a4d5d9026a3d1e27e28ddc63b61698aac0', FALSE),
('0334124c315ddfdb', 'client', $k266$Link codes are disabled on the broadcast seat.$k266$, '275b7baf4f13ac034f94fad11c497b83c09a0630', FALSE),
('05b59a3c5f48d4e8', 'client', $k266$F5 - open / close the competitive menu$k266$, '724727fd048b142ad054df2241736afd1046a59d', FALSE),
('08e4b089323f0e2d', 'client', $k266$The white line is your rating; the band is the rating deviation - it shrinks as you play, and your rating moves less once it is narrow.$k266$, '4e0b21fb9bea2e824b17f811cb690017e9a9e984', TRUE),
('092b5f6f69738677', 'client', $k266$LMB$k266$, 'bdd2b2634fd3d1c82582c6d17bbf13f48f0f6b64', FALSE),
('0b5dc7250d46a753', 'client', $k266$Leave it open$k266$, '7d0bac8c87e12fa00925f00cc2726a6442ee30e5', FALSE),
('0d05a0ee7f392081', 'client', $k266$Leave this competitive match? Click again to confirm. Standard disconnect and early-leave rules apply - this is not a guaranteed forfeit.$k266$, '671b7f7e4974e37ade6d2c6f72a8413565573f3d', TRUE),
('0f250d61631c5546', 'client', $k266$Advanced$k266$, '4d064726954a17487f94e931f5b157b733ec22ed', FALSE),
('0fee8e919c17a19d', 'client', $k266$both$k266$, 'fc39b18f287d8bbfaceae020f4a4eb32ac5c1e70', FALSE),
('101c48b93dc18a1c', 'client', $k266$Chat has been unlocked - carry on.$k266$, '229b63d4752af1d5e5266b484a27b937791c450f', FALSE),
('11ba9036331b2f6c', 'client', $k266$ENTER - room code box / vanilla chat$k266$, 'c4d37600fe6a8b34ececbfffaf5ba84d5bfe876c', FALSE),
('16f08519634a53a5', 'client', $k266$Steam sign-in still pending - try again in a moment.$k266$, '593d57b50f41ff087c272df7180b1ab47974acb9', FALSE),
('17b168c59cb4e7f1', 'client', $k266$Chat is currently LOCKED.$k266$, '43c150859e877ae3f3011e3f47320e8383b13d67', FALSE),
('1880d7803c54ac9d', 'client', $k266$Game$k266$, 'e3e82846c32567811615378f30240185871e08e5', FALSE),
('203775486c7a82a6', 'client', $k266$Click again to forfeit$k266$, '6af3fdd7b6c6bd9921d66438a79392f88442f1d3', TRUE),
('23a74746442c4c65', 'client', $k266$The Cryptid$k266$, 'd9a3a948f03f6021f1f8317e899698c4663d22b5', FALSE),
('24268d2ea1640f9f', 'client', $k266$Play your first ranked match here$k266$, 'ddd6c173bb4cc9055abb2cb3d69a2fecbb208747', TRUE),
('29dd7d7b1c852928', 'client', $k266$Forfeit$k266$, '79424e785ea2fcce076a8fbcdba199e4a0edaa1d', TRUE),
('2f256b33d79dee66', 'client', $k266$SPACE (hold, in a lobby) - ready up / join$k266$, 'a651b4acb3daeba9b52b9efa76cb07e0661bc6af', FALSE),
('3120a8bba946965b', 'client', $k266$Chat has been locked by moderators - messages are paused.$k266$, '00e6378fd0ad4c8296ae49a11a180f2b8f595139', FALSE),
('34eaa39f9e9f80a2', 'client', $k266$HOW SURE THE SYSTEM IS$k266$, 'f579c8b1fa341ce3edef722783b5f58bc7d152ce', FALSE),
('368adc406bc7cf17', 'client', $k266$Beginner$k266$, '60575a6ebba9f780b4312324662169830d12bea1', FALSE),
('39a9fd7c9aef944d', 'client', $k266$Mouse$k266$, '573dd2c2ed953b97e3c31f3090925fe92109b779', FALSE),
('3a0f1f521d0087b1', 'client', $k266$every 5 levels: 100g, then 500g past level 50$k266$, 'a360cd1a4517c555248721ed7c005b0978680c08', FALSE),
('3d63d417e0763f1a', 'client', $k266$The mod never rebinds anything - every vanilla control works exactly as it always has, and the competitive keys are added AROUND them. The board below shows every key that does something during competitive play: gold keys belong to the mod, blue keys to the base game, purple to both.$k266$, '00ead328a3d6b748c93fcafb7260e9cc0a45baba', TRUE),
('3f657265a8382ffb', 'client', $k266$Shades for those who want to show that they are the true genius of the battlefield$k266$, '0458a184cf383c785aa5094125d6491b775dbb63', FALSE),
('406b02c730784003', 'client', $k266$RANK TIERS AND REWARD MULTIPLIERS$k266$, '0ef565eb43156859af82b408109cafaedaa9cb35', FALSE),
('41371036864d76c5', 'client', $k266$FFA games$k266$, '7e45cc8c4037f981e655aac54372fe576c73f315', FALSE),
('4e893d4679622bc9', 'client', $k266$Mute From Message...$k266$, '52e0adc5e18938e15f75d0f573f7e2f782f03a2a', FALSE),
('4ef49a8a6d86b7f0', 'client', $k266$THE ROAD TO LEVEL 100$k266$, 'ae857850d9f6a01df5c6318de07ba3b3d87eedbc', FALSE),
('50b200539b8c78ee', 'client', $k266$No server-issued chat lines are in this session's log.

Pick a message the author sent; the mute lands on whatever platform identity wrote it (Steam, Discord, Twitch or YouTube).$k266$, '29873ae5ee3063929231f7ca5477418031d025e4', FALSE),
('5150a5bb7cbaf0bf', 'client', $k266$press$k266$, 'cd09e18a9bd74edaca7d487211db598da4416565', FALSE),
('529d48be14697fb0', 'client', $k266$Chat Lockdown...$k266$, 'c1487c661b3824edef495d3a1e179de9b6fd9df3', FALSE),
('563586da39b3814b', 'client', $k266$the base award scales with your opponent's tier; podium and sweep bonuses can add more$k266$, '4f07327b6b2ffcb74a720b247fdf065d8ebb7891', FALSE),
('56bb047fa0c21ad1', 'client', $k266$How long?$k266$, '9ce819198916f31ef18b3eb733d0c0f8f44ae386', FALSE),
('5870ba76aee47a05', 'client', $k266$T - open in-game chat$k266$, 'fb17e73c809a9abb8768087eae063849f63b9412', FALSE),
('5ae909299d5434a1', 'client', $k266$Just under half of a payout arrives as XP, the rest as gold. Rating moves from pairwise comparisons against the finishers nearest you.$k266$, '3d56e9cc99258ab6de6f89390be351705194253e', TRUE),
('5eb6d5777bd80861', 'client', $k266$A grin for those who feel most devious$k266$, '07519800157f4a2da4b48a1d0b215d7c5b5a8cde', FALSE),
('62696896c58079eb', 'client', $k266$one 0.3s block window$k266$, '286e61e5c91f29635f56fae46d6fa62ff77b3552', FALSE),
('63db72595c4c8d68', 'client', $k266$1v2: leaving ends your sitting; there is no automatic forfeit.$k266$, 'abe457a4002adffed941a8e45e388126aa40c730', TRUE),
('64969edef9932b86', 'client', $k266$Toxic Cloud$k266$, 'a667fae512b63902faee00b07f06f45b68f99092', FALSE),
('665d16d4b2840e40', 'client', $k266$Intermediate$k266$, 'b1cfe72fd27178870354f9f4e07bb82072caea55', FALSE),
('68118d0219af41cf', 'client', $k266$2v2: the series settles for the other team only if they have already won a game and this game has at least 2 total points; otherwise it pauses as incomplete.$k266$, 'f6768922f2f9a8ed554246089a769ac9601ad6c2', FALSE),
('68a41081df125636', 'client', $k266$PLACEMENT PAYS$k266$, '3a78197a6777de78e110c24747b2bb709b093d5d', FALSE),
('696b16741d564cbe', 'client', $k266$New here? The glowing Search Ranked button up top queues you for your first match.$k266$, '11909a5d9524d840fe00140ae23bfe7861fcabf3', TRUE),
('6b91a0c0f2c14c99', 'client', $k266$A hard helmet for those who are going to war and need to cover their heads$k266$, '56e6b3b32501d5af9853e7f97e93a55b819286c2', FALSE),
('6dc9646c05027ed8', 'client', $k266$LMB - shoot.  RMB - block$k266$, '8fa659fa9f6fda8264f786e2bd627a2917418221', FALSE),
('6ea3113de6680882', 'client', $k266$after a handful of series$k266$, '47899b0bf8c2b9dd3fd5ee49700c77ed0d8f56a2', FALSE),
('7025fdd06041768e', 'client', $k266$LEAVE MATCH$k266$, 'f031701805141ea08448cbd97997244fc8148058', FALSE),
('738daca5c3f26df9', 'client', $k266$This is so sad. Please give this man a break$k266$, '439df3824c961ecc56f1fe97caa5ffd60c2a740b', FALSE),
('739b01547fcbd9a4', 'client', $k266$Controls & keys$k266$, '03a24c219a319f77774cd07b8c2225f4929f8e24', FALSE),
('74a3ffbd1b2e254b', 'client', $k266$CONFIRM LEAVE$k266$, '3582b0f3e9efe01dc8ee0d184bda1f3b466825df', FALSE),
('7540291f1a032c7b', 'client', $k266$100g each - the hardest pay 300g, 500g or 1000g$k266$, '522d8de7ef9c668bd7130111c9ddb031294192fa', FALSE),
('75b31f59dc8e438a', 'client', $k266$Chat is locked by moderators right now - your message was not sent.$k266$, 'ccf89e944f211bc90ff3942034ef0fa9402e2a52', FALSE),
('79d45b2ce8d63afa', 'client', $k266$A stylish hat for those in the mafia$k266$, 'a1c54a88a06fa44bfb072b8e23ae00e2ff16bc1e', FALSE),
('7aff9f0847fdcbe2', 'client', $k266$Chat is currently open.$k266$, 'b490c649eb08657196c358270e67e5c0d5f8036b', FALSE),
('7c8c5a19b3c15dcc', 'client', $k266$SHIFT - cycle your equipped map skins$k266$, 'c11af80bae28e54048d1c71ecd63f75bd729f0c6', FALSE),
('7e318ed8676d0e52', 'client', $k266$mod$k266$, '7dd30f0a95d522bfc058be4e75847f8b6df9f76b', FALSE),
('855d1e8b07c2e7d5', 'client', $k266$TAB (hold, in a match) - live scoreboard$k266$, '48b0c1f86d79f0e617c9eee867b1aaff41d758b9', FALSE),
('856fa04b654ab1e5', 'client', $k266$Each level costs more XP than the last (level^1.5). Every gold dot is a level-up: 100g each through 50, 500g after.$k266$, 'eab48914f0422378fab091ccee6ce862c737f5d4', TRUE),
('85792e54b843280f', 'client', $k266$Mute the author of which message?$k266$, '30075a9c0c58a4307ec963912d41bb023e00e4d9', FALSE),
('85ef80364c159655', 'client', $k266$a pot scaled by lobby size, battles and opponent tier, split by placement$k266$, 'fc051e48bec64b6c5b9f5f7a8795c8c9e4f9c7eb', FALSE),
('86b037a625d0b9b4', 'client', $k266$window over - cooldown keeps counting from the press$k266$, '8bb57a9623bacb4a696286be7447896412172cb2', FALSE),
('907371d0551605f7', 'client', $k266$THE 0.3 SECOND WINDOW$k266$, '24808976280582a15b1721fc0d411d73a086f625', FALSE),
('9caebef13ee3df25', 'client', $k266$Why are they being muted?$k266$, 'f7684920539e981571f6a088e2ab56e1cadbf00f', FALSE),
('9dbeace378dd4e1b', 'client', $k266$Militia Man$k266$, '3b3b2afc3f0b1587e298a86559403fee7db4e4d0', FALSE),
('ad4eadb6ec8876c5', 'client', $k266$Mute from message$k266$, 'cf62c5356606def907e33a05301d822b3ecd1e35', FALSE),
('ae21bb12835baffa', 'client', $k266$DOT TICKS VS THE BLOCK WINDOW$k266$, '4f6eba21524da93b7eea907d03f93668ee66ebb6', FALSE),
('b0020c192e5a1183', 'client', $k266$KEYS THAT DO SOMETHING$k266$, 'e4264ec8fb10bdf6a4e134e6320886298061a4b5', FALSE),
('b4bae31e5af0891d', 'client', $k266$Level-ups$k266$, '047c66202cfc53f93a8901d3d5f5e13c724815fa', FALSE),
('b4d316822b96ba26', 'client', $k266$your stake plus profit by the odds - short-odds wins are lightly taxed$k266$, '0cb58f388e3dde80555698a33dd62ee6f8cd6af5', FALSE),
('b6a4621d6912a7e6', 'client', $k266$A SERIES IS FIRST TO 2$k266$, 'c790d4c7e5ac933c97c61a08108a8515f1549902', FALSE),
('b782b304c02b0e85', 'client', $k266$Ranked series$k266$, '28c2d827acda4509832481f6d4ed5eacb610f759', TRUE),
('b9ddc17d768fa1b3', 'client', $k266$Keep it locked$k266$, '68d7017152dfa47134be41079d6cf5f23253371a', FALSE),
('bd0bc7f08f0598fa', 'client', $k266$A Shiny trinket for those who feel lucky$k266$, 'ba1d0e86c4762d03e8cf3638291ac7575929c326', FALSE),
('be620029c980686a', 'client', $k266$B (in a lobby) - add a practice bot$k266$, '3a12dba0070937a0c83d2c3a55dce1eea0c9e793', FALSE),
('bffaa52506c86556', 'client', $k266$Lucky Ears$k266$, '92c0c56a90c4346196b1221605638694fbc876e4', FALSE),
('cb26de5eb6b8bae9', 'client', $k266$Unlock chat everywhere$k266$, '0c02be9dbb6c822f3fc0b908d522d6d420a801ad', FALSE),
('cb5928d5a704187d', 'client', $k266$M - cycle the chat overlay mode$k266$, '5dd1972661f7c6dc1c186c74e14b7d40854af096', FALSE),
('cb7ebf1fcc9cbffa', 'client', $k266$Everyone starts at 1500. Higher tiers multiply series gold; each band splits into sub-tiers V to I.$k266$, '046dcf45ba01218e7d000fd0a8a3914ae591c6ea', TRUE),
('cbb0440aa5052d96', 'client', $k266$only if it is 1-1$k266$, 'effa17fb09544b590f3e2505d9d125d726ed1f86', FALSE),
('d1136733b5c62c42', 'client', $k266$Forfeit failed$k266$, '22333d4dfcca347a29c73248ab2e93e9930e41be', TRUE),
('d1568a20c1c5c81f', 'client', $k266$Ears for those who feel very lucky$k266$, 'ecdbdbbb2c39fd700bb4ae334fd2615defb3172f', FALSE),
('d1b0bffe890cc265', 'client', $k266$Smart Specs$k266$, '2d0910f5c35e9d87fffb89b1c2ab084e35940195', FALSE),
('d3dc6e977ef36a1f', 'client', $k266$regular (converged)$k266$, 'b1a78dcbad0d2834c3cf2f89267746a475b04459', FALSE),
('d463ba4d3fe6c730', 'client', $k266$Eyes for those who are burning for a true battle$k266$, '2bc4f5879207567e69e8be799e9c265524714089', FALSE),
('d4b6c2192ee2be64', 'client', $k266$WHERE GOLD COMES FROM$k266$, '07a76104d37f51b66843ad75694bac1918b012b0', TRUE),
('d84d735748f37ad0', 'client', $k266$Eyes for those who feel fiendish$k266$, '5c143e75d051c3859764af514e48c9912cbe519b', FALSE),
('da8d672ca0b035a3', 'client', $k266$Y - quick-chat wheel (1-9/0 send a phrase)$k266$, 'ae0907b9efcaa8302a0a5d6e533d255a39c9a968', FALSE),
('db538c880f1cfde9', 'client', $k266$LOCK chat everywhere$k266$, '14103e23af3a7925ed4bf8b9c7e796d2b82e9751', FALSE),
('db5fee62fd6d46d6', 'client', $k266$1v1: your opponent can take the game under the disconnect rules; the series may stay open.$k266$, '319dfc18c3c743c697453e2e356cc1a786dc6a7b', FALSE),
('dbf7b69987b7393d', 'client', $k266$Phoneix Gaze$k266$, '1c2493a2cffcc002e422dca455556ce4ebdd1b22', FALSE),
('dbfcf5cb5e976351', 'client', $k266$brand new (+/- 350)$k266$, '81dc80bb5cad62384352a74489b0ad8f36a90d30', FALSE),
('df07898130ca13ef', 'client', $k266$Forfeit recorded - the match will be resolved shortly.$k266$, '012cc72f181623655f86f1ab4b06654ca4412740', TRUE),
('dff0df94a8c1250d', 'client', $k266$Ratings, gold and the series result all settle when someone takes their 2nd game.$k266$, 'e313b4f3c742df2b6bf812407bd145e84a1f9b39', TRUE),
('e042a7be97677db8', 'client', $k266$Sinister Smile$k266$, 'aa1b3d9c7ef709cd7b74a271ae640f04b027c6fd', FALSE),
('e05f733dc555566c', 'client', $k266$Well Wraped Hat$k266$, 'eb2d72144a8eb56074736534e4fda9d819d267c0', FALSE),
('e3b65fff831bda23', 'client', $k266$Every mark is one tick of damage. A well-timed block erases the 1-2 ticks inside its window.$k266$, 'ab92d11f5f3ed5e802b7409a9fe778e877afb9a7', FALSE),
('e5dadf69deec4be8', 'client', $k266$RMB$k266$, 'cd2dd9251a1e2b57b766c5972c39c07ad8e015d6', FALSE),
('e8fffd61d2b123c0', 'client', $k266$ESC - closes this menu first, then the game menu$k266$, '77a406f15d46fbb8fcb9db489eb464c6e0c590cb', FALSE),
('eb4037a9f3bbf1a3', 'client', $k266$Lucky Coin$k266$, '8ac4bdca240a00d1d6e951be2f2c6a56c23f1fd6', FALSE),
('ec2abf1508ba136a', 'client', $k266$<color=#FFD94D><b>THE KEYS IN PRACTICE</b></color>
F5 works everywhere - menu, lobby, mid-game. While the menu is open your inputs stay out of the game: clicks do not fire your gun, Space does not ready you up, and Escape only closes the menu - it will not cancel a match that is connecting. Close it and everything flows again.

Chat has three doors. T types a message, Y opens the quick-chat wheel (then 1-9 or 0 sends a phrase), and Enter still opens the vanilla box - the mod leaves it alone. M cycles the chat overlay display mode.

Hold Tab during a match for the live scoreboard: score, cards, accuracy and connection info for everyone in the room, without opening the full menu.

Shift swaps between your equipped map color skins as a new round paints in. If you have none equipped, it does nothing.

Vanilla rebinding lives in the game options; the mod keys themselves are fixed. For what to practice with all of this, read <color=#7FD4FF>Getting better</color>.$k266$, '998c82568cf86e63a5076cdd864f7c9f28f67328', FALSE),
('ecee43db04e473cc', 'client', $k266$absorbs everything$k266$, '984d0e19218e75b60f1a78f14bcdd2f6ce92af7d', FALSE),
('f8cfffdbc154226a', 'client', $k266$FFA: your tally is kept and scored from your exit under the early-leave rules.$k266$, '97f13afb5db03819911341e5b7e782561f069219', FALSE),
('f95da11526f422b8', 'client', $k266$base game$k266$, 'd4935ba458a53152ac538277ca378c07b264d9f2', FALSE),
('fc38e4476e514059', 'client', $k266$The Mobsta$k266$, '4c2d87bcd6cb6da3b237d31d45dc55d25eb664ec', FALSE),
('fdfe7ec82dafaf6d', 'client', $k266$Sadness$k266$, '2df908378d5e5235eb570a2c8b7a70a509279c87', FALSE),
('ff097547403cfb2a', 'client', $k266$level$k266$, 'ad60c535ff88e85bf0254452fe3934f24e9668d5', FALSE)
) AS v(key_id, namespace, msgctxt, source_hash, sensitive)
ON CONFLICT (key_id) DO UPDATE SET retired_at = NULL, updated_at = NOW()
  WHERE i18n_keys.source_hash = EXCLUDED.source_hash;

DO $$
DECLARE v_live INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_live FROM i18n_keys WHERE namespace = 'client' AND retired_at IS NULL;
    IF v_live <> 2071 THEN
        RAISE EXCEPTION 'post-check FAILED: % live client keys, expected 2071', v_live;
    END IF;
    RAISE NOTICE 'post-check OK: % live client keys', v_live;
END $$;

COMMIT;
