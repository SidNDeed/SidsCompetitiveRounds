-- 340_i18n_keys_item11.sql  (v1.41.0, item 11 — FAQ refresh, client half)
--
-- Item 11 corrected three Info-library articles against the code:
--   * the 1v1 lone-room warning is 15 s, not 25 (GameStateWatcher.cs warnAfter)
--   * the achievement gold tiers were missing the four tournament keys
--     (ACHIEVEMENT_GOLD_OVERRIDES, main.py)
--   * the artist pipeline takes a GIF or numbered frames, not only "a PNG"
--     (NativeUI.ValidateAndNameCosmetic; COSMETIC_MAX_FRAMES = 16)
--
-- A client key IS its English source string, so each edit produces a NEW
-- key_id and leaves the old one behind. THIS FILE AND 341 ARE THE PORTAL HALF
-- ONLY. plugin/InfoLibrary.cs (the English) and plugin/I18nCatalogues.cs (the
-- four locales) are the artifact a player actually renders (#583) and belong
-- to the client lane; this branch carries no change to either, and the three
-- corrections plus the catalogue entries they need are written out in
-- ai-collab/ITEM11-CLIENT-FAQ-CONTRACT.md. The ids below are derived from the
-- CORRECTED English, so the two halves meet at exactly the text that document
-- specifies; backend/tests/test_faq_surfaces.py recomputes all three from the
-- bodies in this file and matches each to the predecessor it replaces.
--
-- THE RE-KEY IS COMPLETED HERE, not deferred. Registering the successors and
-- leaving the predecessors live keeps three articles' worth of text in the
-- portal that no client can render, in four locales each — the state 251 left
-- behind when it assigned retirement to "the next real sync-keys run", and
-- that 255 had to clean up. That run cannot be made from this seat (#443), so
-- section 2 below performs 255's two writes: retire the three predecessors,
-- supersede their pending machine proposals. It carries 255's guard too — it
-- refuses if a translator has APPROVED work on a predecessor (#168) — and the
-- count, the refusal and both writes are one locked operation against the
-- review endpoint rather than a count followed by a write on a second snapshot
-- (#208; see section 2 for the lock modes and why they conflict). Idempotent,
-- because both UPDATEs are predicated on the state they leave.
--
-- key_id = sha1("client" || chr(0) || source)[:16], source_hash =
-- sha1(source), sensitive and context from tools/i18n_sync_keys.py — IMPORTED
-- by the generator, never re-implemented. The three predecessor ids were
-- derived by the same formula from the PARENT commit's tools/i18n_source.json;
-- they are the ids 251_i18n_keys_info_library.sql registered for these three
-- articles, and 251's own dollar-quoted sources are still in the repo, which
-- is how backend/tests/test_faq_surfaces.py recomputes each id from that text
-- instead of trusting the three literals below.
--
-- Explicit transaction (#340). The conflict arm is the sync endpoint's own
-- full update, but it carries a WHERE so an unchanged row is not rewritten: a
-- re-run of this file must change ZERO rows, and an updated_at that advances
-- on every apply is a write the deploy log reports as work. The post-check
-- RAISEs if any successor is missing, retired, or carries a different
-- source_hash, context or a stray max_px, and if any predecessor is still
-- live.
--
-- RUN ORDER: deploy API -> apply this file -> apply 341. Independent of 338:
-- 338 is the Discord bus, this is the translation portal. The game text itself
-- ships in the 1.41.0 DLL and needs neither.

BEGIN;

INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, max_px, context, updated_at)
SELECT v.key_id, v.namespace, v.msgctxt, v.source_hash, v.sensitive, NULL, v.context, NOW()
  FROM (VALUES
  ('fc07ba40fe031c27', 'client', $k340$Ranked 1v1 is the mod's core mode: best-of-3 series, one Glicko rating, and two ways to start a rated series - the queue, or a private room where both players run the mod. This page covers the queue from Search to room, how a private lobby becomes rated, and exactly what a disconnect does.

<color=#FFD94D><b>FINDING AN OPPONENT</b></color>

- Clicking Search is itself the ranked opt-in - joining the queue turns Ranked on for your account.
- Your search band starts at 100 rating in either direction and widens as you wait: 200 after 30 seconds, 400 after 60, 800 after 120. It never widens past 800.
- The overlap is <color=#7FD4FF>two-sided</color>: you must be inside your opponent's band AND they must be inside yours. A 2-minute waiter with a wide band can't grab a fresh joiner whose narrow band excludes them.
- Among valid candidates, the closest rating wins.
- Players you declined in the last 5 minutes, players you've blocked (in either direction) and banned accounts are never offered.
- Searching while playing casual is fine - vanilla quickplay and ordinary casual rooms never cancel your search. Joining any mod-issued room (a tournament, 2v2, 1v2 or FFA) does, immediately.
- After 30 minutes of searching you're removed from the queue. <color=#8A8A93>Rejoin if you're still there - the 1v1 client never rejoins for you.</color>

<color=#FFD94D><b>READY-UP, DECLINE AND THE ROOM</b></color>

- On a match you get a MATCH FOUND banner with your opponent's name and rating, a sound, and a taskbar flash. You must click Ready - there is no auto-ready.
- You have 90 seconds, and when either player clicks Ready the window resets to a fresh 90 for both - a slow alt-tabber always gets full time. If it runs out, both of you go back to searching.
- Decline puts both of you back in the queue and blocks the two of you from re-pairing for 5 minutes. Once the room has been issued, decline no longer works.
- When both are ready the server issues a private ranked room and picks the Photon region: if both clients report the same home region, that wins; otherwise it falls back through the players' live regions, then either home region, then US.
- Your client pins that region before joining, so both of you land in one room instead of two same-named rooms on two continents.
- If your opponent never arrives: a warning at 15 seconds, then an automatic return to the menu at 60. <color=#7FE87F>No penalty for either side.</color>

<color=#FFD94D><b>RANKED IN A PRIVATE ROOM</b></color>

- A room-code game is rated when three things are true: your Ranked toggle is on, your opponent has Ranked enabled, and your opponent runs the mod. An opponent who has never run the mod can never make a game rated. (One deliberate exception: a live unfinished series from an earlier sitting keeps its ranked status when you meet again.)
- The moment both mods see each other, the client registers the series with the server (the <color=#7FD4FF>preflight</color>) - so the series exists, and is bettable, during game 1.
- If either player has Ranked disabled, the server refuses the series and you get one toast: the match plays out as casual. Casual games are still recorded - they just never touch rating.
- Queue and tournament rooms skip these checks entirely: queueing was the consent.

<color=#FFD94D><b>THE SERIES</b></color>

- First to 2 game wins takes the series. <color=#7FE87F>Rating moves only when a series completes</color> - the whole series is one rating outcome, and individual games never move rating on their own.
- An undecided series - at least one game played, nobody at 2 wins - <color=#7FE87F>never expires</color>. Play the same opponent tomorrow or next week and game 1 still stands; your HUD picks up the standing score instead of restarting at 0-0.
- That no-expiry rule is deliberate: an expiry window let a player down 0-1 abandon the series and wait out the clock to dodge the loss.
- A non-tournament series where no game was ever finished is abandoned after 30 minutes; the next meeting starts fresh. Tournament series wait for their bracket instead.
- Bets on a series stalled for 60 minutes are refunded (tournament series excepted) - the series itself stays resumable.
- During round 1 of each game, the client reports live points to the server. Betting locks once 2 total points have been scored in game 1 (a 1-1 counts) - or the moment any game of the series is decided.

<color=#FFD94D><b>DISCONNECTS</b></color>

What a DC does depends on the score, and it is judged by the player who STAYED:

- You were at match point (4 rounds) when your opponent dropped: you win the game at the standing score.
- 4-4: you take the game, recorded as 5-4.
- Anywhere else - including an opponent who drops while AHEAD - the game is canceled. Nobody gets a win, nobody gets a loss.
- Leaving a game to join your own queued ranked match is announced in advance and never counted against you.

The anti-abuse rules:

- Only the player who stayed in the room and watched the other leave can claim a DC win. <color=#7FE87F>A leaver's own client can never award itself anything.</color>
- If the opponent reconnects before you leave, the claim is dropped.
- If BOTH players drop, nobody stayed to observe: no win, no leave mark. With a completed game on the board the series stays active and resumes whenever you next meet.
- <color=#FF6666>A canceled game doesn't wipe the series</color> - completed games stand, and the series resumes as above.

<color=#FFD94D><b>LEAVE PERCENT</b></color>

- A ranked DC with meaningful play behind it (2 or more points, or a completed round, in the CURRENT game), with neither side at match point, is recorded as a leave against the leaver - at most one per player per series.
- <color=#7FD4FF>Leave %</color> = ranked DCs divided by ranked series wins + losses + DCs. Under 5 percent shows green, 5 to under 15 amber, 15 and up red - visible to everyone on the leaderboard.
- A DC at match point becomes a DC win for the other player instead, not a leave mark.

For the full is-this-recorded decision tree, see <color=#7FD4FF>When a game counts</color>.$k340$, '0aa41f4136b6fb6ac705d0f82fccc62a6fd86ca6', TRUE, E'InfoLibrary · (file scope)'),
  ('ab40c2146a3ed0fb', 'client', $k340$Every finished game pays XP, XP converts to Gold at 100 XP = 1 Gold, and ranked play multiplies the base rewards below by your opponent's rank tier. This is the pay table - exact numbers, mode by mode. (Tournament podium prizes are separate; see <color=#7FD4FF>Deadlines & forfeits</color>.)

<color=#FFD94D><b>THE TIER MULTIPLIER</b></color>

In ranked play, base rewards are multiplied by the OPPONENT'S rank tier - <color=#7FE87F>win or lose. Playing up always pays.</color>

<color=#7FD4FF>Beginner</color> (under 1500) - x1.0
<color=#7FD4FF>Intermediate</color> (1500 or more) - x1.5
<color=#7FD4FF>Advanced</color> (1675 or more) - x2.0
<color=#7FD4FF>Master</color> (1980 or more) - x2.5
<color=#7FD4FF>Grand Master</color> (2330 or more) - x3.0

It applies to XP and to series Gold, and an opponent with no rating on record counts as 1500 (x1.5). Which rating is 'the opponent's': their 1v1 rating in 1v1, the opposing team's average 2v2 rating in 2v2, the opposing seat's average 1v1 rating in 1v2, and your opponents' average FFA rating in FFA.

<color=#FFD94D><b>1v1</b></color>

Per game, multipliers stack, then the total truncates to a whole number:

- Base <color=#7FE87F>250 XP</color> per finished game, casual included.
- Game win: x1.5. Ranked: x1.5. Opponent tier: x1.0 to x3.0 (ranked only).
- A shutout win (opponent on 0 rounds) adds +100 XP flat, after the multipliers.

Exact examples: casual loss 250, casual win 375; ranked loss vs a Beginner 375; ranked win vs a Beginner 562, vs an Intermediate 843, vs a Grand Master 1687 (+100 more if 5-0).

Series Gold, ranked BO3 only - casual play creates no series and pays none:

- Loser: 5 x opponent tier, truncated. Winner: double that.
- Winner doubles AGAIN if the beaten player currently sits in the leaderboard top 3.
- +2 flat on top for a 2-0 sweep.
- Winner/loser by opponent tier, before podium and sweep: Beginner 10/5, Intermediate 14/7, Advanced 20/10, Master 24/12, Grand Master 30/15.

<color=#FFD94D><b>2v2</b></color>

- Per game: 600 XP x the opposing team's tier, then x1.5 if your team won the game.
- Default all-1500 lobby: 900 XP for a loss, 1350 for a win.
- Series Gold: 50 (each winner) or 25 (each loser), x the opposing team's tier. Default lobby: 75/37.

<color=#FFD94D><b>1v2</b></color>

Base 500 XP per game, x1.5 on a win, then a per-seat difficulty multiplier:

- Solo seat: x1.5.
- Solo playing WITHOUT the extra-pick handicap: another x1.20.
- Duo seats facing a buffed solo (extra pick on): x1.10.
- Opponent tier, read from the opposing seat's average 1v1 rating - 1v2 has no rating of its own.
- Opponent currently in the 1v2 leaderboard top 3: x1.35, win or lose.
- The whole product is capped at x4.0; the x1.5 win bonus applies on top of the cap.

Defaults with extra pick on: the solo earns 1125 XP for a loss and 1687 for a win; each duo member 825/1237.

Series Gold: 40 (winning side) or 20 (losing side), x opponent tier only - the seat, handicap and podium factors live on XP. Default: 60/30.

<color=#FFD94D><b>FFA - THE METER</b></color>

FFA pays for FIGHTING, not for time in the lobby. The formula, in readable form:

- The work unit is <color=#7FD4FF>battles</color>: every decisive round scored by anyone in the game. <color=#FF6666>Camping adds nothing to the pool</color>, and the last-place cut it earns is the smallest share of what everyone else generated.
- A pace ceiling caps how fast battles cash in. For a lobby of P players, one battle is expected about every 3.08 + 6.54 x P seconds (P counted as at least 3 and at most 6 here), and the game pays at most TWICE that pace across the game's elapsed time on the server's clock - stalling or point-farming cannot outrun it.
- The base rate is 3.5 Gold per player-minute, +5% for every player above 4. A 10-player FFA is the best Gold rate in the game.
- Placement shapes your cut of the pool: 1st place earns 1.666x the lobby average, last place 0.334x - about a 5x spread. Players sharing a place share the same cut.
- A stronger field multiplies the pot: your opponents' average tier divided by 1.5, so a default 1500 field is exactly x1.0. Casual lobbies take the bottom factor (about x0.667) and never touch ratings.
- The pool is a Gold amount. 55% pays directly as Placement Gold (minimum 1). The other 45% pays as XP at 100 XP per point of pool (minimum 50 XP), which drips back as Gold through the normal conversion.
- Placement itself sorts by points, then all round wins earned (spent ones included), then kills where the lobby's kill tiebreak is active; remaining ties share a place.
- Ghosts and graced early leavers are unpaid and unrated for that game: leaving before the field scored 2 half points, while your own tally (points, half points, kills) is still zero, takes you out of it entirely.

<color=#FFD94D><b>LEVELS AND THE XP-TO-GOLD DRIP</b></color>

- XP converts at <color=#7FE87F>100 XP = 1 Gold</color>, paid every time your running total crosses a hundred mark. Every mode's XP - tournament prizes included - feeds the same total.
- Climbing into level L costs 100 x L^1.5 XP, truncated: level 2 costs 282, level 5 costs 1118, level 10 costs 3162, level 50 costs 35355, level 100 costs 100000. Max level is 100.
- Entering a multiple-of-5 level pays bonus Gold: <color=#7FE87F>100g for levels 5 through 50, 500g for 55 through 100</color> - 6000g lifetime if you reach the cap. It lands the moment any XP award dings the level - any mode, tournament prizes included; a ding during an FFA game shows up inside that game's +g number.

<color=#FFD94D><b>ACHIEVEMENT GOLD</b></color>

Every achievement pays <color=#7FE87F>100g</color> unless listed here:

- <color=#7FD4FF>1000g</color> - Sid Slayer, Stan Slayer, Grand Master (reach 2330), Touch Grass, Babel.
- <color=#7FD4FF>500g</color> - Master (reach 1980), Tag Team Sweep, Rise from the Ashes, Casual Conqueror, Twins!, Immortal, Hostile Takeover, Bodycount, Sync Champion, Async Champion.
- <color=#7FD4FF>300g</color> - Stacked Deck, Flawless, Silly Drill, Into the Deep End, Century Club, Unstoppable, Party Crasher, Heartbreak, Dragoman, Sync Finalist, Async Finalist.

The FFA shutouts nest: one 5-0 win in a 5-player lobby pays Clean House (100g) + Party Crasher (300g) + Hostile Takeover (500g) in a single game. The translator achievements (Rosetta, Dragoman, Babel) trigger at 10, 100 and 1000 approved live strings.

<color=#8A8A93>Outside matches: Discord server boosters are paid 2000g monthly, and community artists earn a 30% royalty (rounded down to whole Gold) when another player buys their item - gifts pay none.</color>$k340$, 'a486c9106056d299d8eccbfdcd4b495e775e2af9', TRUE, E'InfoLibrary · (file scope)'),
  ('7d2c24d463786026', 'client', $k340$Cosmetics live in the F5 Shop tab and are bought with the gold you earn by playing. This page covers every kind, how each equips, how drops and stock work, and where the art comes from.

<color=#FFD94D><b>WHAT EACH KIND DOES</b></color>

<color=#7FD4FF>Titles</color> - the label beside your name on mod surfaces (see <color=#7FD4FF>Titles</color>).
<color=#7FD4FF>Trails</color> - a colored trail behind your body in matches. Length scales with price: 3,000 gold trails are short, 5,000 medium, 10,000 long.
<color=#7FD4FF>Map skins</color> - recolor the whole map and background. Equip as many as you like and cycle through them mid-game with Left Shift. The catalog holds recolors styled after the six vanilla arts, more than thirty original presets including the night pack, and three premium sparkle skins: Gilded, Platinum and Aurora. <color=#7FE87F>Map skins are yours alone</color> - they're never sent to other players, so every player sees their own pick.
<color=#7FD4FF>Name styling</color> - stackable styling on your display name. Formatting (bold, italic, underline, strike, float) stacks freely; glow, size, font transform and typeface allow one each, and the color effects (solids, neons, rainbow, per-letter gradients) share one slot.
<color=#7FD4FF>Player colors</color> - replace your team orange or blue with a color of your own, and become your team identity on modded screens (see <color=#7FD4FF>Team & body colors</color>).
<color=#7FD4FF>Cursor colors</color> - recolor your mouse cursor. The cursor SHAPE (default, arrow, dot, crosshair, circle) is a free preference. Nobody else ever sees your cursor.
<color=#7FD4FF>Player effects</color> - a particle aura that follows your body in matches.
<color=#7FD4FF>Faces</color> - custom eyes, mouths and accessories that slot into ROUNDS' own character editor next to the vanilla parts, and render everywhere a face renders. Some are animated; the Animated Cosmetics setting pins them to a still frame if you prefer.
<color=#7FD4FF>Hide Gold</color> - a utility toggle that masks your gold on leaderboard surfaces.

<color=#FFD94D><b>EQUIPPING</b></color>

- One at a time: titles, trails, player colors, cursor colors and player effects use <color=#7FD4FF>Set Active</color> / <color=#7FD4FF>Unequip</color>.
- Multi-equip: name styles and map skins use <color=#7FD4FF>Equip</color> / <color=#7FD4FF>Remove</color> - stack your name styles, hold a rotation of skins.
- Hide Gold is an on/off toggle.

<color=#FFD94D><b>WHO SEES WHAT</b></color>

- <color=#7FE87F>The only cosmetic a player WITHOUT the mod can ever see is name styling</color> - styled names ride the same name field vanilla already renders, and putting styling in a name has always been possible in vanilla ROUNDS. Even there, glow and typeface are mod-side extras a vanilla screen can't display.
- Everything else - trails, player colors, auras, faces, map skins - renders only for modded players. A vanilla opponent sees your default body color, no trail, no aura, and an empty slot where a custom face part would be. <color=#8A8A93>The game skips the unknown part cleanly: no crash, nothing substituted.</color>
- Modded viewers can individually turn off other players' trails, player colors and animated cosmetics in Settings.

<color=#FFD94D><b>STOCK, DROPS AND TEASERS</b></color>

- The shop lists everything by price and shows what you own, each item's artist, and stock.
- Community items can be limited: a drop shows N of M left and greys out once sold out.
- An item can exist before its sale opens - it shows as not for sale until the artist opens sales, and brand-new arrivals tease on the Home tab's newest-cosmetics panel first. <color=#FF6666>Seeing an item on Home doesn't mean you can buy it yet.</color>
- You can't buy an item twice, and a purchase you can't afford is refused - no debt, no partial buys.

<color=#FFD94D><b>THE ARTIST STUDIO</b></color>

Community artists make a large share of the catalog. The pipeline:

- An artist (a role granted in-game) submits art from the Artist tab: one 512x512 PNG, a GIF, or up to 16 numbered PNG frames, positioned on a live on-body preview with slot, scale and offset.
- The submission goes to review. Approval alone doesn't put it on sale: the art has to ship inside a mod release first, because cosmetics are bundled into the mod so every player's game can render them.
- Once shipped, the artist opens sales and controls the price, the stock cap, and who may buy - an artist can block specific players from buying their items.
- The artist earns <color=#7FE87F>a 30% royalty</color> (rounded down to whole Gold) when another player buys their item. No royalty on gifts.

<color=#FFD94D><b>GIFTS</b></color>

Only artists can gift, and only their own items: a free copy to any player who has used the mod, including before sales open. Gifts still consume stock on a limited drop. There is no player-to-player gifting, and no way to send gold to another player.$k340$, '19329ffd6e3b0670e93678c0dfd1bde7861598fa', TRUE, E'InfoLibrary · (file scope)')
  ) AS v(key_id, namespace, msgctxt, source_hash, sensitive, context)
ON CONFLICT (key_id) DO UPDATE
   SET namespace = EXCLUDED.namespace, msgctxt = EXCLUDED.msgctxt,
       source_hash = EXCLUDED.source_hash, sensitive = EXCLUDED.sensitive,
       max_px = EXCLUDED.max_px, context = EXCLUDED.context,
       retired_at = NULL, updated_at = NOW()
 WHERE i18n_keys.namespace   IS DISTINCT FROM EXCLUDED.namespace
    OR i18n_keys.msgctxt     IS DISTINCT FROM EXCLUDED.msgctxt
    OR i18n_keys.source_hash IS DISTINCT FROM EXCLUDED.source_hash
    OR i18n_keys.sensitive   IS DISTINCT FROM EXCLUDED.sensitive
    OR i18n_keys.max_px      IS DISTINCT FROM EXCLUDED.max_px
    OR i18n_keys.context     IS DISTINCT FROM EXCLUDED.context
    OR i18n_keys.retired_at  IS NOT NULL;

-- ── 2. Retire the three predecessor keys ─────────────────────────────────
-- Section 1's three successors are these same three articles with item 11's
-- corrections applied, so the predecessors describe text the product no longer
-- means to show, and the portal would be offering translators work on it.
--
-- THE CLIENT HALF SHIPS SEPARATELY, and this comment does not pretend
-- otherwise. plugin/InfoLibrary.cs still carries the predecessor English in
-- this tree, and tools/i18n_source.json — its extraction artifact — still
-- extracts it. Both belong to the client lane, which applies the same three
-- corrections and adds the successors' catalogue entries as its own step
-- (ai-collab/ITEM11-CLIENT-FAQ-CONTRACT.md). Until it does, the successor keys
-- exist with no client asking for them and the predecessors are off the
-- translator surface. Nothing a PLAYER sees changes either way: a client of
-- any version renders its own DLL's bundled strings, and the portal was never
-- what fed them. What the window costs is translator work on three articles,
-- which is the direction chosen over leaving two live keys for one article.
-- 255_retire_orphan_keys.sql is the shape, including its refusal: a
-- translator's finished (approved) work must never be silently retired by a
-- hygiene pass, so this RAISEs instead.
--
-- THE COUNT AND THE RETIREMENT ARE ONE LOCKED OPERATION (#208). Counting
-- approved entries and then retiring on the strength of that count is two
-- snapshots: /i18n/review/{id} can approve a proposal in between, and the
-- migration would then retire work a translator had just finished, exactly
-- what the refusal exists to prevent. That endpoint reads the proposal's
-- key_id UNLOCKED first (it is all the request carries — #197's
-- discover-then-lock), and the FIRST LOCK it then takes is
-- `SELECT 1 FROM i18n_keys WHERE key_id = :k FOR NO KEY UPDATE`, before it
-- touches the proposal or any entry. So taking the same mode on the same
-- three key rows, in key order, serializes this file against it:
-- FOR NO KEY UPDATE self-conflicts, and it is the weakest mode that also
-- conflicts with this file's own later non-key UPDATE of retired_at, so it
-- adds no conflict with the FOR KEY SHARE that every i18n_entries insert
-- takes on these rows for its foreign key (#202). A review that got there
-- first commits before we see anything, and the re-read below then finds its
-- row; one that arrives after we hold the lock waits, and when it proceeds
-- its own authoritative re-read requires `retired_at IS NULL` and answers
-- 409 "key retired since proposal" instead of approving into a retired key.
DO $$
DECLARE v_approved INTEGER;
BEGIN
    PERFORM 1 FROM i18n_keys
     WHERE key_id IN ('c4facebcda2e750a','c14135018e41f6f6','c84c43c265080ec2')
     ORDER BY key_id
       FOR NO KEY UPDATE;
    -- Belt and braces, not the load-bearing lock. The only writer that makes
    -- an entry 'approved' today is /i18n/review, and the key lock above
    -- already serializes it. This second lock covers the class rather than
    -- that one caller (#432): a future writer that flips an entry's state
    -- WITHOUT taking the key row first would otherwise move the predicate
    -- under us. Deterministic order, and taken before the count is read.
    PERFORM 1 FROM i18n_entries
     WHERE key_id IN ('c4facebcda2e750a','c14135018e41f6f6','c84c43c265080ec2')
     ORDER BY key_id, language_code
       FOR NO KEY UPDATE;
    -- Authoritative re-read UNDER the locks. Anything committed before we got
    -- here is visible now, and nothing can move it until this file commits.
    SELECT COUNT(*) INTO v_approved
      FROM i18n_entries e
     WHERE e.key_id IN ('c4facebcda2e750a','c14135018e41f6f6','c84c43c265080ec2')
       AND e.state = 'approved';
    IF v_approved <> 0 THEN
        RAISE EXCEPTION 'migration 340: % approved entr(ies) exist on the item-11 predecessor keys - refusing to retire translator-approved work; investigate first', v_approved;
    END IF;

    UPDATE i18n_keys
       SET retired_at = NOW(), updated_at = NOW()
     WHERE key_id IN ('c4facebcda2e750a','c14135018e41f6f6','c84c43c265080ec2')
       AND retired_at IS NULL;

    UPDATE i18n_proposals
       SET status = 'superseded'
     WHERE key_id IN ('c4facebcda2e750a','c14135018e41f6f6','c84c43c265080ec2')
       AND status = 'pending';
END $$;

-- ── 3. Post-check ────────────────────────────────────────────────────────
-- Enforcing: every successor live with the expected source_hash and context,
-- and no predecessor still live or still offering pending work.
DO $$
DECLARE
    v_expected INT := 3;
    v_ok INT;
    v_old_live INT;
    v_old_pending INT;
    v_old_approved INT;
BEGIN
    SELECT COUNT(*) INTO v_ok
      FROM i18n_keys k
      JOIN (VALUES
        ('fc07ba40fe031c27', '0aa41f4136b6fb6ac705d0f82fccc62a6fd86ca6', E'InfoLibrary · (file scope)'),
        ('ab40c2146a3ed0fb', 'a486c9106056d299d8eccbfdcd4b495e775e2af9', E'InfoLibrary · (file scope)'),
        ('7d2c24d463786026', '19329ffd6e3b0670e93678c0dfd1bde7861598fa', E'InfoLibrary · (file scope)')
      ) AS e(key_id, source_hash, context) ON e.key_id = k.key_id
     WHERE k.namespace = 'client' AND k.retired_at IS NULL
       AND k.source_hash = e.source_hash
       AND k.max_px IS NULL AND k.context IS NOT DISTINCT FROM e.context;
    IF v_ok <> v_expected THEN
        RAISE EXCEPTION 'post-check FAILED: % of % expected item-11 client keys are live with the expected source_hash and context', v_ok, v_expected;
    END IF;

    SELECT COUNT(*) INTO v_old_live FROM i18n_keys
     WHERE key_id IN ('c4facebcda2e750a','c14135018e41f6f6','c84c43c265080ec2')
       AND retired_at IS NULL;
    SELECT COUNT(*) INTO v_old_pending FROM i18n_proposals
     WHERE key_id IN ('c4facebcda2e750a','c14135018e41f6f6','c84c43c265080ec2')
       AND status = 'pending';
    IF v_old_live <> 0 OR v_old_pending <> 0 THEN
        RAISE EXCEPTION 'post-check FAILED: % predecessor key(s) still live, % proposal(s) still pending on them', v_old_live, v_old_pending;
    END IF;

    -- FAIL CLOSED on the refusal itself. Section 2 reads the approved count
    -- under the key and entry locks and this re-reads it after the writes, so
    -- the file cannot commit a retirement of translator-approved work under
    -- ANY interleaving: if the lock discipline above were ever weakened or
    -- removed, an approval that slipped in is caught here and the whole
    -- transaction rolls back, rather than the count being the only thing
    -- standing between a review and a silent retirement. A post-check that
    -- only looks at what the migration itself wrote cannot fail (#342).
    SELECT COUNT(*) INTO v_old_approved FROM i18n_entries
     WHERE key_id IN ('c4facebcda2e750a','c14135018e41f6f6','c84c43c265080ec2')
       AND state = 'approved';
    IF v_old_approved <> 0 THEN
        RAISE EXCEPTION 'post-check FAILED: % approved entr(ies) on the retired predecessor keys - a review landed during this migration; nothing committed', v_old_approved;
    END IF;
    RAISE NOTICE 'post-check OK: % item-11 client keys live, 3 predecessors retired', v_ok;
END $$;

COMMIT;
