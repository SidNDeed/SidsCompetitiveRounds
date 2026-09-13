-- 312: i18n client keys for the Sept 12 Player Cards feedback batch (18 NEW keys): the pack
-- history pager, the discarded stamp, the daily-limit exemption copy, the Info article on cards
-- and the picture/settings help. This is the additive half of what POST /admin/i18n/sync-keys
-- does, written through the migration channel because this seat's tooling cannot sign the admin
-- HMAC (learning #443). Same contract as 302: additive-only (reworded strings get NEW key_ids;
-- their predecessors are left for the real sync tool's retire pass), key_id = sha1("client\0" +
-- English)[:16], source_hash = sha1(English), sensitive and context per tools/i18n_sync_keys.py.
-- One key is contextual (English + U+0004 + context, the TrC form) and is written as an E'' literal
-- so the separator byte is explicit. Idempotent AND contract-convergent: the conflict arm is the
-- sync endpoint's own full update, and the post-check RAISES if any expected key is missing,
-- retired, or carries a different source_hash / context or a stray max_px. Explicit transaction
-- (#340). The game namespace is unchanged. Run order: deploy API -> apply this file -> apply 313.

BEGIN;

INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, max_px, context, updated_at)
SELECT v.key_id, v.namespace, v.msgctxt, v.source_hash, v.sensitive, NULL, v.context, NOW()
  FROM (VALUES
('00b53afaf4c8e38d', 'client', $k312$<color=#FFD94D><b>YOUR PICTURE ON OTHER PEOPLE'S CARDS</b></color>

- The card of you shows your <b>in-game character</b>: the body, face items, colour and effect you play with, drawn by your own PC the first time you visit the Collection tab after a change, and sent once. Nobody else's PC renders you.
- Before your PC has sent it, your card shows your <b>Steam profile picture</b>, which the server takes from your public profile.
- <b>Card picture</b> in Settings switches between your character and None. None hides both from the next render on; the character your PC sent stays stored until you send another.
- <b>Character preset</b> picks which saved character your picture shows: Follow uses the one you have selected in the character menu, or pin a preset. The small preview under it is what will be sent.

<color=#FFD94D><b>THE OTHER SETTINGS</b></color>

- <b>Opt out</b> stops new cards of you: none is minted from then on and pulls of you are no longer announced. Cards of you that people already hold stay in their binders with their frozen stats and show the plain card emblem in place of your picture. It does not hide your binder and it does not delete any card.
- <b>Public collection</b> is the setting that shows or hides your binder from others (/collection in Discord); opting out leaves it alone.
- <b>Announce my pulls</b> allows Discord posts about your Epic-or-better, Foil and Signed pulls, and about pulls of YOUR card - both sides must have it on for a post to happen.
- Deleting your account is what removes cards: it empties your binder. Cards of you that others hold stay, with a neutral label in place of your name.

<color=#FFD94D><b>WHY A CARD SHOWS WHAT IT SHOWS</b></color>

- A card's rating, record, rank tier and shop title are frozen at the snapshot it was minted from. If you rank up tomorrow, cards of you minted today keep today's rank; the next snapshot's cards get the new one.
- The name and the picture are live: a card of a renamed player shows the new name, and its picture follows what that player's PC last sent (or their Steam picture, or the emblem).
- If the player opts out, cards of them stay in binders with their frozen stats and the emblem in place of the picture. If the player deletes their account, cards of them stay too, with a neutral label in place of the name and no picture.$k312$, '8893ed17adde56199e9c2415bed815e15a9fa99b', TRUE, E'InfoLibrary · (file scope)'),
('023462e2144bac77', 'client', $k312$Player Cards are collectible cards of the people who play here. Every registered player who has not opted out (and is not currently banned) has a card in the pool; you open packs, keep the cards you like, discard the rest for shards and chase the rare ones. Everything lives under <color=#7FD4FF>Shop > Collection</color>: <b>Open Packs</b>, <b>Binder</b> and <b>Get packs</b>.

<color=#FFD94D><b>THE POOL, EDITIONS AND SNAPSHOTS</b></color>

- The <b>pool</b> is every eligible player, frozen in a <b>snapshot</b>: rating, record, rank tier, top card and title as they were that day. A card you pull keeps those as the snapshot saw them and they never change afterwards - that is what makes an old card an old card. Two things on a card stay live: the player's name (a rename follows) and their picture (see Card pictures & settings).
- An <b>edition</b> (Ed. 1, Ed. 2 ...) is one run of snapshots. The edition and the date your card was minted are printed along its bottom edge, with a short print number that is unique to your copy.
- The pool line under the pack buttons tells you how many players the current snapshot holds and when it was taken.$k312$, '006f045319b6c5930c931d97e34d755fec4e56c6', TRUE, E'InfoLibrary · (file scope)'),
('21805a6155a21285', 'client', $k312$Newer >$k312$, '03301bf980ea6a980fb2cc0bbd2bc77d811a526e', FALSE, E'PlayerCardsUI · BuildOpenView'),
('21b41babb49a1c4f', 'client', $k312$Card pictures & settings$k312$, '84148b567249dfa38d278200b986e32e0d5fd5e0', FALSE, E'InfoLibrary · (file scope)'),
('2ed4fbc31d00c3dc', 'client', $k312$Reading a card$k312$, 'ea1e194a903d0c5f05c139f2012997ac724f3808', FALSE, E'InfoLibrary · (file scope)'),
('38b6cdfd96ae16c2', 'client', $k312$A card freezes its player's title, rating, record and rank as the leaderboard had them on the day it was pulled; the name and the picture stay live (a renamed player shows their new name). Anyone with the mod can be pulled unless they turn it off in Settings or are currently banned; your own settings for being a card, a public binder and pull announcements live there too.$k312$, 'b0ffe51bfe82553704cc014c3f95955797f4b040', TRUE, E'PlayerCardsUI · RefreshInfo'),
('399ed0d6343742dd', 'client', $k312${0} paid packs today - no daily limit on this account - {1} cards each$k312$, 'e46a6351a2a17383127d33142062257b0b527adb', FALSE, E'PlayerCardsUI · RefreshOpen'),
('3d3f357c73935320', 'client', $k312$Your packs$k312$, '8da4806ae9fda2e1398ea936d55ccfba37c2b98e', FALSE, E'PlayerCardsUI · BuildOpenView'),
('5a6d5767d4ffd983', 'client', $k312$<color=#FFD94D><b>THE HEADER</b></color>

- The player's current name - a rename follows onto every card of them - and under it the shop title they were wearing when the snapshot was taken (nothing there if they wear the rank title or no title at all).
- The chip in the corner is the band: COM, UNC, RARE, EPIC or LEG, with FOIL beneath it on a foil.

<color=#FFD94D><b>THE PICTURE</b></color>

- The player's own in-game character - body, face, colour and effect - once their PC has sent it. Until then, their Steam profile picture. Players who set their picture to None show the plain card emblem instead. See <color=#7FD4FF>Card pictures & settings</color>.
- A Top card badge in the lower-left corner means the snapshot found a card they pick more than any other; its name is on the text block when the picture is not shown.

<color=#FFD94D><b>THE STATS</b></color>

- <b>RANK</b> is the rating tier the player was in at the snapshot - Beginner I up to Grand Master V, the same tiers as the leaderboard. It is never the shop title.
- <b>RATING</b> is their rating at the snapshot, or Unranked.
- <b>POOL #</b> is their position in the card pool at the snapshot - the ordering that decides the band (see Player Cards). A lower number is a rarer card.
- <b>BOARD #</b> is their leaderboard position at the snapshot: five or more ranked series and recently active. A dash means they were not on the board that day.
- <b>RECORD</b> is ranked series won and lost at the snapshot.

<color=#FFD94D><b>THE MARKS</b></color>

- A <b>Signed</b> card carries the player's autograph across the picture and a seal.
- The bottom edge has the edition, the minted date, and your copy's print number. The View button on a binder tile shows the card full size.$k312$, '5cf38ade68df0936e75f8f570410fac8f8331130', TRUE, E'InfoLibrary · (file scope)'),
('733167cb61ddd428', 'client', $k312$<color=#FFD94D><b>GETTING PACKS</b></color>

- <b>One free pack a day</b> - press Claim on the Open Packs tab or use /daily in Discord. The day resets at midnight UTC.
- <b>Paid packs</b> cost 100 Gold or 100 shards and hold 5 cards. Up to 5 paid packs a day for most accounts; the Get packs tab says what applies to yours.
- <b>Earned packs</b>: winning a ranked 1v1 series grants a pack one time in five, and a 2-0 sweep always does. 2v2, 1v2 and FFA wins grant one time in ten, a sweep one time in two (an FFA sweep is every round won and nobody else scoring). Earned and claimed packs wait under <b>Packs waiting</b> until you open them, as long as you like.

<color=#FFD94D><b>WHAT IS IN A PACK</b></color>

- Each card rolls its band on its own: <color=#8085A0>Common 60%</color>, <color=#4DB861>Uncommon 25%</color>, <color=#408CFA>Rare 11%</color>, <color=#9E52EB>Epic 3.5%</color>, <color=#FFB82E>Legendary 0.5%</color>.
- The band decides WHO you get: the pool is ordered (players who have played a ranked series first, then by rating), and pool position #1 is the one Legendary card, #2-10 are Epic, #11-20 Rare, #21-40 Uncommon, and everyone past that is Common.
- Independently of the band, any card can come out <b>Foil</b> (1 in 200) or <b>Signed</b> (1 in 2,000) - a foil shimmers, a signed card carries the player's autograph.
- The strip under the buttons shows your last pack, and the Older / Newer buttons page back through every pack you have opened. A card you discarded stays in its pack, stamped DISCARDED.

<color=#FFD94D><b>DUPLICATES AND SHARDS</b></color>

- A card you already own is marked DUPLICATE when it lands (+1, +2 ... for how many copies you held before it).
- <b>Discard</b> turns a card into shards: <color=#8085A0>Common 5</color>, <color=#4DB861>Uncommon 15</color>, <color=#408CFA>Rare 40</color>, <color=#9E52EB>Epic 150</color>, <color=#FFB82E>Legendary 600</color>. It asks you to click twice. <b>Dupes</b> discards every copy except one in a single go.
- Shards buy packs at the same price as Gold - 100 for a pack.

<color=#FFD94D><b>DISCORD</b></color>

- /daily claims the free pack, /collection shows a binder, /card shows one card - all with a linked Discord account.
- A pull that is Epic or better is announced in the leaderboard channel, and so is a pull of your own card, a Foil or a Signed print at any rarity - but only when BOTH you and the player on the card have <b>Announce my pulls</b> on (see Card pictures & settings). A Rare or lower pull that is none of those is not announced.$k312$, '76474015293ba19d6288acfe18f911bc894e9055', TRUE, E'InfoLibrary · (file scope)'),
('81ab6a5164d7d1c1', 'client', $k312$DISCARDED (+{0} shards)$k312$, '3b117a5e8e0fa8872483047881d6b04bec06b182', FALSE, E'PlayerCardsUI · DiscardedLine'),
('82e0829a59d1bea3', 'client', $k312$Your card can show your in-game character - the same body, face, colour and effect you play with, drawn by this PC and sent once. Until this PC has sent it, your card shows your Steam profile picture. Set it to None and your card shows the plain card emblem instead.$k312$, '2728cfc802cf26e33d0bca8c6d51462f6b33cd15', FALSE, E'PlayerCardsUI · BuildSettingsRows'),
('93d3e25b197db4a8', 'client', $k312$< Older$k312$, '7c37dffe3cd849b936fb65db2ea032b4e002aa2f', FALSE, E'PlayerCardsUI · BuildOpenView'),
('a9e67c1a4c1f9c6a', 'client', E'DISCARDED\x04pack open', '59c318787a497767b03e4c6f2e2299460369a0ff', FALSE, E'PlayerCardsUI · DiscardedLine · pack open'),
('df18e7c25bc9a523', 'client', $k312$Pack {0} of {1} ({2}) - {3}$k312$, 'e8b2e6df79d2ab485ab205bfbfdac84b8212edb9', FALSE, E'PlayerCardsUI · RefreshOpen'),
('df73b3e97fba0f69', 'client', $k312$DISCARDED$k312$, '278d6c0448fc24279c6837735dda38cf6963e8c4', FALSE, E'PlayerCardsUI · DiscardedLine'),
('fef31b7fdfed7ccc', 'client', $k312$- Buy one for {0} gold or {1} shards. No daily limit on this account.$k312$, '8d343394988fbe4e53cd65a191f5e808fbaa2b99', TRUE, E'PlayerCardsUI · RefreshInfo'),
('ffbcc4a35c38478e', 'client', $k312$Loading your packs...$k312$, '06763d5bb728c2a48d3cb2d365737b30c614e598', FALSE, E'PlayerCardsUI · RefreshOpen')
  ) AS v(key_id, namespace, msgctxt, source_hash, sensitive, context)
ON CONFLICT (key_id) DO UPDATE
   SET namespace = EXCLUDED.namespace, msgctxt = EXCLUDED.msgctxt,
       source_hash = EXCLUDED.source_hash, sensitive = EXCLUDED.sensitive,
       max_px = EXCLUDED.max_px, context = EXCLUDED.context,
       retired_at = NULL, updated_at = NOW();

-- Post-check (enforcing): every expected key live with the expected source_hash and context.
DO $$
DECLARE
    v_expected INT := 18;
    v_ok INT;
BEGIN
    SELECT COUNT(*) INTO v_ok
      FROM i18n_keys k
      JOIN (VALUES
        ('00b53afaf4c8e38d', '8893ed17adde56199e9c2415bed815e15a9fa99b', E'InfoLibrary · (file scope)'),
        ('023462e2144bac77', '006f045319b6c5930c931d97e34d755fec4e56c6', E'InfoLibrary · (file scope)'),
        ('21805a6155a21285', '03301bf980ea6a980fb2cc0bbd2bc77d811a526e', E'PlayerCardsUI · BuildOpenView'),
        ('21b41babb49a1c4f', '84148b567249dfa38d278200b986e32e0d5fd5e0', E'InfoLibrary · (file scope)'),
        ('2ed4fbc31d00c3dc', 'ea1e194a903d0c5f05c139f2012997ac724f3808', E'InfoLibrary · (file scope)'),
        ('38b6cdfd96ae16c2', 'b0ffe51bfe82553704cc014c3f95955797f4b040', E'PlayerCardsUI · RefreshInfo'),
        ('399ed0d6343742dd', 'e46a6351a2a17383127d33142062257b0b527adb', E'PlayerCardsUI · RefreshOpen'),
        ('3d3f357c73935320', '8da4806ae9fda2e1398ea936d55ccfba37c2b98e', E'PlayerCardsUI · BuildOpenView'),
        ('5a6d5767d4ffd983', '5cf38ade68df0936e75f8f570410fac8f8331130', E'InfoLibrary · (file scope)'),
        ('733167cb61ddd428', '76474015293ba19d6288acfe18f911bc894e9055', E'InfoLibrary · (file scope)'),
        ('81ab6a5164d7d1c1', '3b117a5e8e0fa8872483047881d6b04bec06b182', E'PlayerCardsUI · DiscardedLine'),
        ('82e0829a59d1bea3', '2728cfc802cf26e33d0bca8c6d51462f6b33cd15', E'PlayerCardsUI · BuildSettingsRows'),
        ('93d3e25b197db4a8', '7c37dffe3cd849b936fb65db2ea032b4e002aa2f', E'PlayerCardsUI · BuildOpenView'),
        ('a9e67c1a4c1f9c6a', '59c318787a497767b03e4c6f2e2299460369a0ff', E'PlayerCardsUI · DiscardedLine · pack open'),
        ('df18e7c25bc9a523', 'e8b2e6df79d2ab485ab205bfbfdac84b8212edb9', E'PlayerCardsUI · RefreshOpen'),
        ('df73b3e97fba0f69', '278d6c0448fc24279c6837735dda38cf6963e8c4', E'PlayerCardsUI · DiscardedLine'),
        ('fef31b7fdfed7ccc', '8d343394988fbe4e53cd65a191f5e808fbaa2b99', E'PlayerCardsUI · RefreshInfo'),
        ('ffbcc4a35c38478e', '06763d5bb728c2a48d3cb2d365737b30c614e598', E'PlayerCardsUI · RefreshOpen')
      ) AS e(key_id, source_hash, context) ON e.key_id = k.key_id
     WHERE k.namespace = 'client' AND k.retired_at IS NULL
       AND k.source_hash = e.source_hash
       AND k.max_px IS NULL AND k.context IS NOT DISTINCT FROM e.context;
    IF v_ok <> v_expected THEN
        RAISE EXCEPTION 'post-check FAILED: % of % expected sept12 client keys are live with the expected source_hash and context', v_ok, v_expected;
    END IF;
    RAISE NOTICE 'post-check OK: % sept12 client keys live', v_ok;
END $$;

COMMIT;
