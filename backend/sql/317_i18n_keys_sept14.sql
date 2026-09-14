-- 317: i18n client keys for the Sept 14 Player Cards feature batch (7 NEW keys): the pool
-- membership wording (players who have run the mod), the top-two Legendary band, the Top card
-- slot, the Get packs body and the rate-limit notices. This is the additive half of what
-- POST /admin/i18n/sync-keys does, written through the migration channel because this seat's
-- tooling cannot sign the admin HMAC (learning #443). Same contract as 302/312: additive-only
-- (reworded strings get NEW key_ids; their predecessors are left for the real sync tool's retire
-- pass), key_id = sha1("client\0" + English)[:16], source_hash = sha1(English), sensitive and
-- context per tools/i18n_sync_keys.py. Idempotent AND contract-convergent: the conflict arm is the
-- sync endpoint's own full update, and the post-check RAISES if any expected key is missing,
-- retired, or carries a different source_hash / context or a stray max_px. Explicit transaction
-- (#340). The game namespace is unchanged. Run order: deploy API -> apply this file -> apply 318.

BEGIN;

INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, max_px, context, updated_at)
SELECT v.key_id, v.namespace, v.msgctxt, v.source_hash, v.sensitive, NULL, v.context, NOW()
  FROM (VALUES
('224e05bb1d48afda', 'client', $k317$Slowing down - the server asked for a {0} s pause$k317$, 'b7c63b7e968511515555b759c3790baa9a887cb3', FALSE, E'PlayerCardsUI · DiscardNext'),
('48a24e0360ba60f2', 'client', $k317$A card freezes its player's title, rating, record and rank as the leaderboard had them on the day it was pulled; the name and the picture stay live (a renamed player shows their new name). Every player who has run the mod and is not banned can be pulled; a public binder and pull announcements are your Settings, and deleting your data removes every card of you from every binder.$k317$, '85ec2739ac823f7a2235524bde640017ab265a98', TRUE, E'PlayerCardsUI · RefreshInfo'),
('5da58f11d793eaea', 'client', $k317$<color=#FFD94D><b>GETTING PACKS</b></color>

- <b>One free pack a day</b> - press Claim on the Open Packs tab or use /daily in Discord. The day resets at midnight UTC.
- <b>Paid packs</b> cost 100 Gold or 100 shards and hold 5 cards. Up to 5 paid packs a day for most accounts; the Get packs tab says what applies to yours.
- <b>Earned packs</b>: winning a ranked 1v1 series grants a pack one time in five, and a 2-0 sweep always does. 2v2, 1v2 and FFA wins grant one time in ten, a sweep one time in two (an FFA sweep is every round won and nobody else scoring). Earned and claimed packs wait under <b>Packs waiting</b> until you open them, as long as you like.

<color=#FFD94D><b>WHAT IS IN A PACK</b></color>

- Each card rolls its band on its own: <color=#8085A0>Common 60%</color>, <color=#4DB861>Uncommon 25%</color>, <color=#408CFA>Rare 11%</color>, <color=#9E52EB>Epic 3.5%</color>, <color=#FFB82E>Legendary 0.5%</color>.
- The band decides WHO you get: the pool is ordered (players who have played a ranked series first, then by rating), and pool positions #1-2 are the two Legendary cards, #3-10 are Epic, #11-20 Rare, #21-40 Uncommon, and everyone past that is Common.
- Independently of the band, any card can come out <b>Foil</b> (1 in 200) or <b>Signed</b> (1 in 2,000) - a foil shimmers, a signed card carries the player's autograph.
- The strip under the buttons shows your last pack, and the Older / Newer buttons page back through every pack you have opened. A card you discarded stays in its pack, stamped DISCARDED.

<color=#FFD94D><b>DUPLICATES AND SHARDS</b></color>

- A card you already own is marked DUPLICATE when it lands (+1, +2 ... for how many copies you held before it).
- <b>Discard</b> turns a card into shards: <color=#8085A0>Common 5</color>, <color=#4DB861>Uncommon 15</color>, <color=#408CFA>Rare 40</color>, <color=#9E52EB>Epic 150</color>, <color=#FFB82E>Legendary 600</color>. It asks you to click twice. <b>Dupes</b> discards every copy except one in a single go.
- Shards buy packs at the same price as Gold - 100 for a pack.

<color=#FFD94D><b>DISCORD</b></color>

- /daily claims the free pack, /collection shows a binder, /card shows one card - all with a linked Discord account.
- A pull that is Epic or better is announced in the Discord gambler chat, and so is a pull of your own card, a Foil or a Signed print at any rarity - but only when BOTH you and the player on the card have <b>Announce my pulls</b> on (see Card pictures & settings). A Rare or lower pull that is none of those is not announced.$k317$, '9b3d387f32a28bab2a8a716200fb8d407610081b', TRUE, E'InfoLibrary · (file scope)'),
('6262aad1393e919b', 'client', $k317$<color=#FFD94D><b>THE HEADER</b></color>

- The player's current name - a rename follows onto every card of them - and under it the shop title they were wearing when the snapshot was taken (nothing there if they wear the rank title or no title at all).
- The chip in the corner is the band: COM, UNC, RARE, EPIC or LEG, with FOIL beneath it on a foil.

<color=#FFD94D><b>THE PICTURE</b></color>

- The player's own in-game character - body, face, colour and effect - once their PC has sent it. Until then, their Steam profile picture. See <color=#7FD4FF>Card pictures & settings</color>.
- The lower-left corner shows their Top card: the ROUNDS card the snapshot found they pick more than any other. It is drawn in-game from the card itself; cards shown outside the game (Discord) carry a plain badge there instead, and the name is on the text block when the picture is not shown.

<color=#FFD94D><b>THE STATS</b></color>

- <b>RANK</b> is the rating tier the player was in at the snapshot - Beginner I up to Grand Master V, the same tiers as the leaderboard. It is never the shop title.
- <b>RATING</b> is their rating at the snapshot, or Unranked.
- <b>POOL #</b> is their position in the card pool at the snapshot - the ordering that decides the band (see Player Cards). A lower number is a rarer card.
- <b>BOARD #</b> is their leaderboard position at the snapshot: five or more ranked series and recently active. A dash means they were not on the board that day.
- <b>RECORD</b> is ranked series won and lost at the snapshot.

<color=#FFD94D><b>THE MARKS</b></color>

- A <b>Signed</b> card carries the player's autograph across the picture and a seal.
- The bottom edge has the edition, the minted date, and your copy's print number. Click a binder tile to see the card full size.$k317$, 'cbb4762519e994327916a66f9a48f529d91a6de7', TRUE, E'InfoLibrary · (file scope)'),
('83bfe0b8abeedba6', 'client', $k317$Each pack holds {0} cards. A card's rarity is its player's rank in the card pool on the day of the pull: Legendary = #1-2, Epic #3-10, Rare #11-20, Uncommon #21-40, Common #41 and below. Odds per card: Common 60%, Uncommon 25%, Rare 11%, Epic 3.5%, Legendary 0.5%. Every card also rolls Foil (1 in 200) and Signed (1 in 2000) on its own.$k317$, 'b6319176d253732eb634c772cac7cf0e34e3fa78', FALSE, E'PlayerCardsUI · RefreshInfo'),
('e224785f648cafd4', 'client', $k317$Too many requests at once - wait a few seconds and try again$k317$, '27c832cb50f6c0ab3338996d8ebb7bd1bf16fc73', FALSE, E'PlayerCardsUI · ReasonText'),
('eb5dbe1e64ef57e1', 'client', $k317$Player Cards are collectible cards of the people who play here. Every player who has run the mod and is not currently banned has a card in the pool; you open packs, keep the cards you like, discard the rest for shards and chase the rare ones. Everything lives under <color=#7FD4FF>Shop > Collection</color>: <b>Open Packs</b>, <b>Binder</b> and <b>Get packs</b>.

<color=#FFD94D><b>THE POOL, EDITIONS AND SNAPSHOTS</b></color>

- The <b>pool</b> is every eligible player, frozen in a <b>snapshot</b>: rating, record, rank tier, top card and title as they were that day. A card you pull keeps those as the snapshot saw them and they never change afterwards - that is what makes an old card an old card. Two things on a card stay live: the player's name (a rename follows) and their picture (see Card pictures & settings).
- An <b>edition</b> (Ed. 1, Ed. 2 ...) is one run of snapshots. The edition and the date your card was minted are printed along its bottom edge, with a short print number that is unique to your copy.
- The pool line under the pack buttons tells you how many players the current snapshot holds and when it was taken.$k317$, '70e16237f3aa29d652a99f18375884e623a94094', TRUE, E'InfoLibrary · (file scope)')
  ) AS v(key_id, namespace, msgctxt, source_hash, sensitive, context)
ON CONFLICT (key_id) DO UPDATE
   SET namespace = EXCLUDED.namespace, msgctxt = EXCLUDED.msgctxt,
       source_hash = EXCLUDED.source_hash, sensitive = EXCLUDED.sensitive,
       max_px = EXCLUDED.max_px, context = EXCLUDED.context,
       retired_at = NULL, updated_at = NOW();

-- Post-check (enforcing): every expected key live with the expected source_hash and context.
DO $$
DECLARE
    v_expected INT := 7;
    v_ok INT;
BEGIN
    SELECT COUNT(*) INTO v_ok
      FROM i18n_keys k
      JOIN (VALUES
        ('224e05bb1d48afda', 'b7c63b7e968511515555b759c3790baa9a887cb3', E'PlayerCardsUI · DiscardNext'),
        ('48a24e0360ba60f2', '85ec2739ac823f7a2235524bde640017ab265a98', E'PlayerCardsUI · RefreshInfo'),
        ('5da58f11d793eaea', '9b3d387f32a28bab2a8a716200fb8d407610081b', E'InfoLibrary · (file scope)'),
        ('6262aad1393e919b', 'cbb4762519e994327916a66f9a48f529d91a6de7', E'InfoLibrary · (file scope)'),
        ('83bfe0b8abeedba6', 'b6319176d253732eb634c772cac7cf0e34e3fa78', E'PlayerCardsUI · RefreshInfo'),
        ('e224785f648cafd4', '27c832cb50f6c0ab3338996d8ebb7bd1bf16fc73', E'PlayerCardsUI · ReasonText'),
        ('eb5dbe1e64ef57e1', '70e16237f3aa29d652a99f18375884e623a94094', E'InfoLibrary · (file scope)')
      ) AS e(key_id, source_hash, context) ON e.key_id = k.key_id
     WHERE k.namespace = 'client' AND k.retired_at IS NULL
       AND k.source_hash = e.source_hash
       AND k.max_px IS NULL AND k.context IS NOT DISTINCT FROM e.context;
    IF v_ok <> v_expected THEN
        RAISE EXCEPTION 'post-check FAILED: % of % expected sept14 client keys are live with the expected source_hash and context', v_ok, v_expected;
    END IF;
    RAISE NOTICE 'post-check OK: % sept14 client keys live', v_ok;
END $$;

COMMIT;
