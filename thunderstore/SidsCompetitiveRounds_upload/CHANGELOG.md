## v1.41.0 — 2026-11-13

**Player Cards arrive in the client**

- Player Cards arrive in the client: collectible cards of the people who play
  here, under a new Collection tab in the Shop group, with Open Packs, Binder
  and Get packs views. A pack open that is interrupted can be recovered.
- Packs come from a free daily claim, from buying with gold or shards, and as
  a chance reward when you win a ranked series or a ranked FFA match.
- Players who have run the mod from a Steam account and are not banned have a
  card in the pool. A card's rarity is its player's rank in the card pool on
  the day of the pull, and the pool's top two are Legendary.
- Any card can also come out Foil or Signed; a Signed card carries its
  player's autograph.
- A card's picture is the player's public Steam profile picture until their
  own game uploads their in-game character. The cards of a player who deletes
  their data are cleaned up.
- The card picture is now framed on the character itself, so a gun or a
  one-sided cosmetic widens the frame instead of pushing the body off centre.
  Because the framing changed, every stored card picture is out of date: the
  first time you open Player Cards on this version, your game draws your card
  picture again and uploads the new one. Nothing needs to be done by hand.
- Batch shard: several cards can be turned into shards in one batch, and a
  discard sends one request per discarded copy. A card you received in a trade
  gives no shards when discarded, and a discarded card still shows in your
  pack history, stamped as discarded.
- Shard on the fly: the pull tab's five cards carry the binder's actions, and
  Shard dupes there counts only the shown pack's cards you own right now.
- The binder can be ordered by where each card's player stands on the board
  today.
- Card trading: a Trades view in the Collection with Incoming, Sent and Recent
  sections, where you propose trades and answer the ones sent to you. A Card
  trading row in the Player Cards settings turns card trading on or off.
- Two more rows in the Player Cards settings choose whether other players can
  see which cards you hold, in the mod and in Discord, and whether your rare
  pulls may be posted in Discord with your name.
- Dance on my card: choose one of your dances in the Player Cards settings and
  your card plays it as an animation.
- Card editions end and roll over on a schedule.
- The Settings picture row now shows your whole card as other players see it.
- Your Top card is named on your card face with its art, in that card's own
  ink colour. Its thumbnail sits inside the badge frame instead of over its
  rounded corners, and its art uses the same rectangle on the server-drawn
  cards as in the game.

**Player Cards reach Discord**

- Player Cards drawn for Discord carry the Top card's art, placed where the
  game draws it (bug 408).
- In Discord, /pack and /binder show your packs and collection as images,
  /daily opens your daily pack, /buypack buys one with gold or shards, and
  /card shows a player's full card and posts its dance as a GIF once its
  preview is ready.

**The Discord bot**

- The leaderboard channel carries the 1v1, 2v2 and FFA boards, and a board is
  replaced only after its new copy is posted.
- Sync tournaments: one rule decides who counts toward the start vote, and
  availability checks go only to eligible entrants.

**Tournaments**

- Double-elimination brackets for 9 to 15 players are built in full: a field
  of 9 to 14 could not lock before, and in a field of 15 one player could be
  out after a single loss.
- A withdrawal after the lock no longer stalls the bracket. When the place
  stays empty, a match missing one player becomes a bye for the player who is
  there, a match with no player in either place is passed over, and a
  tournament whose final is decided that way completes. Before, such a match
  waited for good and held up the grand final.
- In the in-game bracket, a match with no player in either place shows dashes.
- After a tournament locks, the server refuses a leave request sent from the
  game; the game then says "Couldn't leave the tournament - it may have locked
  or started" and refreshes the Tournaments tab. The rule book now says that
  after the lock you withdraw by answering No on the bot's availability-check
  DM.
- The availability-check DM's buttons act only for the SCR account now linked
  to your Discord account: on a DM sent before an unlink or relink they say
  "Couldn't use this button" with the reason, and the server checks the link
  again when it records a No.
- A Yes pressed on the availability-check DM after your No went through no
  longer shows "Confirmed": the bot answers that you have already withdrawn.
  It gives that answer until it sends you a new availability-check DM for that
  tournament, prepared after your No went through, or until the bot restarts.
- A tournament action button pressed while the Tournaments tab is out of step
  with the tournament data the game holds does nothing: it says "Tournament
  info is refreshing - try again in a moment" and refreshes the tab.
- The Force Start count on the Tournaments tab counts only the votes the start
  rule counts.
- The bot's tournament-complete post names only the places that were awarded,
  and its bracket progress leaves out byes with no player in them.

**Title ladders move into the Shop**

- Title ladders move into the Shop's Titles section, and the separate Titles
  tab is gone. Each ladder has five tiers, and clicking a ladder opens its
  tiers in a dropdown under it.
- A player who has not started a ladder is told so, instead of being told the
  ladder service is unavailable.
- Titles up to 16 characters show whole on the FFA leaderboard and recent-match
  rows (they were cut at 12 and 14), and the F5 board fits a name and a title
  in its column.
- The Voidshot and Kingslayer titles are retired; everyone who bought one got
  the price back in gold.

**Settings is rebuilt around eight sub-tabs**

- Controls: a new Controls sub-tab in Settings rebinds the mod's own keys and
  the game's controls.
- Settings is rebuilt as eight sub-tabs of one-line rows, with a help pane for
  the rows. Every sub-tab except Privacy & account has a reset: to its
  recommended values, or on Controls to the default keys.
- A controller can drive the Settings page: the shoulder buttons move between
  sub-tabs and the bottom face button activates a row.
- The language row names the detected language as a word ("Detected:
  Svenska").
- Damage numbers: optional numbers above players for damage dealt and health
  healed, Off, Me or Everyone, Off by default.
- Avatar defaults: two presets. Your modded avatar is worn wherever everyone
  runs the mod; a vanilla avatar is worn in Quick Match and in any game where
  someone does not, because modded face items show as empty slots to them. The
  game switches for that room and gives your own face back when you leave.
  Only presets a base-game player's game can load are offered as the vanilla
  default.
- HP precision: the HP precision setting existed but had no row, so no one
  could reach it. It now has a row in Settings.
- The leaderboard's active-player count and the Show inactive players row
  state the inactivity window the server advertises, or no day count when it
  states none, instead of a fixed 90 days, and update when the window arrives.
- The bug-report form opens from a bug icon in the page title row beside Mail
  and Music. The box near the bottom of Settings is gone.
- The F5 footer gains a scrmod.com button after Thunderstore.
- On a window that is not 16:9, the mod now clears the bands above and below
  the game to black. Before, a closed page left its title, Back button and
  footer behind in those bands until something else drew there.

**Room rules stay with the room**

- Same Cards works in every mode: in 1v1 when both players want it, and in
  hosted modes when the host turns it on. 2v2 and 1v2 hosts can turn friendly
  fire off.
- Friendly fire and Same Cards are fixed on the room when it is created and
  reported by every history surface and by the Discord result posts.
- A strip at the top centre names the room's rules for the whole game, Same
  Cards and friendly fire off included, so a player who joined after they
  were set, or reconnected, can still see them. The config key [UI]
  ShowRoomRulesIndicator hides it.
- FFA history shows the settings frozen for that game.

**2v2, 1v2 and FFA players can come back mid-game**

- 2v2 and 1v2: when a player drops, the game waits at the next point boundary
  so they can come back. If they do not return in time, the disconnect is
  handled as before. This needs every player in the room on 1.41.0; a room
  with an older client in it plays exactly as before.
- FFA late entry (a player joining a game already under way) and FFA mid-game
  readmission (a dropped player let back into the same game, with their card
  picks made for them while they are away) are on in FFA rooms where every
  player runs 1.41.0. With an older client in the room, neither is used.

**Ranked FFA handles joins and mixed versions**

- Joining a ranked FFA room where every player runs 1.41.0: the game follows
  each player's connection and the match start waits while players connect.
  If a player cannot connect, the lobby re-forms with the players still there,
  or closes before the match.
- A ranked FFA counts for rating only when every player in the room runs
  1.41.0 or newer, the version with the Lifestealer fix below; otherwise the
  game is unrated.
- In a ranked FFA where players run different mod versions, the closing seat
  collects every player's card pick again, older builds' picks included
  (bugs 435, 436).
- Attempted fix for bugs 389 and 437-439: Lifestealer kept draining the one
  player it first picked, anywhere on the map. In rooms where every player
  runs 1.41.0 or newer, it now picks its target again each time it activates,
  the way the game itself picks one.
- Early leave: a player who leaves a ranked FFA before the field has scored
  four half points in total, whether or not any became a full point, is not
  rated for that game and earns no game gold or XP.
- One earlier ranked FFA game was corrected under this rule: the player who
  left it early had that game's rating change reversed. Gold and XP were not
  touched, and no other player's result in that game changed.
- The Info library's FFA, economy and rule-book pages and the FFA mode text
  state the early-leave rule above. They described an older one: two half
  points, and only while the leaver's own tally was still zero.
- An FFA result sent by a mod version older than 1.39.1 is refused when it
  names a player who left during that game, so update the mod.
- The ranked-FFA shutout achievements say they count the players who finished
  the game, which is the rule the server applies.
- The in-game post-session report tells a player whose connection failed
  apart from one who chose to leave.

**Disconnected 2v2 series wait for review**

- A 2v2 series in which a player disconnects is no longer settled
  automatically by the lead-forfeit. The games already reported stand, rating
  and gold do not move, and an admin awards or voids the series from the admin
  panel. Each game's number comes from the series' own recorded score, so a
  player who rejoins numbers the games the same way as everyone else.
- 2v2 disconnects are reported more reliably, and a backup report no longer
  overrides the real one (bugs 384, 385).

**Queues widen and rooms choose a region**

- The 1v1 ranked search accepts any rating once you have waited two minutes.
  If the server accepts the queue leave that your cancel or your ranked-off
  switch sends, while it still has your search, and you search again within 30
  seconds, your wait time carries over, unless it has reached the 30-minute cap
  by then or the server restarted in between.
- 2v2, 1v2 and FFA queue rooms and hosted lobbies pick their region from every
  member's own ping measurements.
- Ranked 1v1: when both players' ping maps arrive in time, the room moves to
  the shared region with the lowest worst ping for the pair, within each
  player's own limit, if that beats the usual region by more than 20 ms.
- Ranked 1v1 rooms start from the two players' home regions. The region your
  game was last connected to, for example after quick play, decides a room
  only when both players were connected to a region one of them calls home,
  or when no home region was sent or none that the server can confirm is
  still in service. Before, it could keep a pair on a region far from one of
  them whatever their ping maps said (bug 457). Each player's limit is now
  measured against both players' home regions (the region each game pings
  lowest, and its cached home region when the game measured it) and the
  region the room would otherwise get, so the limit no longer keeps a pair
  from the best region they share when each game measured the other's
  lowest-ping region.
- The server refuses a region ping map that carries an entry with no region
  code, like every other malformed map. Before, such a map was stored and
  could decide a ranked 1v1 room.

**Connection trouble explains itself**

- While the match connection is failing, a corner notice says so and clears
  when data flows again. At a disconnect that message is handed over to the
  disconnect notice instead of being torn down.
- A game you try to spectate that the server refuses shows why.

**Session reports show more of each game**

- Builds pages: one compact block per game. Totals become four pages, every
  number taken from a named recorded field. The score race plots rounds won
  against the mode's win target.
- Each game in the report shows its gold in every mode, and its XP in 1v1 and
  FFA games.
- After a set it has watched, the broadcast pages through that set's
  post-session report, the same pages players see in the game. When the
  report is unavailable, it shows its own report screens instead.
- The broadcast's idle showcase walks every Compare category.

**Mail can reach Discord**

- Players who link their Discord account can also get new mail as a Discord
  DM and reply from Discord. The Discord relay switch in the mail settings
  turns it on or off for you.

**Custom music meets the game's level**

- The custom music slider's top is now measured against the game's own music
  level, so custom tracks no longer play far louder than the game, and clips
  are evened out to one target level. A slider stored at 100 moves to the new
  default once. The first track after a silent main menu fades in.

**Log uploads are opt-in and prepared before sending**

- Automatic log upload, opt-in and off by default, in Privacy & account: when
  you leave a room you played in, the game sends the same bundle the
  bug-report form sends. The bundle is built off the game thread, and turning
  consent off stops an upload already under way.
- Revoking consent clears an open chat line and its resume notice as well as
  the stashed draft.
- The first-run data-consent prompt says in red what stops working without
  consent: the leaderboard, ranked matchmaking, chat, player cards and bug
  reports with logs. Decline now asks you to confirm first; Back returns to
  the prompt.
- Log handling for bug reports and automatic uploads has been updated.
- The bug-report form and the log viewer are prepared off the game thread, and
  match history is read a little at a time each frame, so neither stalls the
  game.

**Five community faces**

- Gold headband, Orbit, Pumpking Hat, leafy mushroom and Red Scarf join the
  shop in the detail slot, marked out of stock until each face's artist opens
  sales. Until then the server refuses a purchase ("Not for sale yet"), and a
  face's artist can still gift it. They need 1.41.0: the server leaves them
  out of an older version's shop and refuses its purchase of one, and it
  accepts a gift of one only when the last mod version it recorded for the
  recipient is 1.41.0 or newer.

**Fixes**

- Attempted vanilla fix, in rooms where every player runs 1.41.0: a shot
  fired in the last moments of a round no longer leaves the gun on that
  reload when the next round starts; the round revive now clears the weapon
  cooldown like the other timers it resets.
- Attempted fix for bugs 406 and 407, in rooms where every player runs
  1.41.0: poison and other damage over time converge on every seat. Each tick
  is applied once per life, a tick for a life this seat has not reached yet
  waits for it, and a player no longer appears to take no poison damage on the
  other screen.
- Attempted vanilla fixes: a Saw's particle effects stop once its target is
  dead, and in rooms where every player runs 1.41.0 a dead player no longer
  shields a living one from a Saw. Lifestealer's range ring is drawn at the
  range it really reaches.
- The avatar you picked is the one that shows at card pick and at spawn, not
  the default face (bug 444).
- Esc closes chat without sending and keeps your draft; switching to another
  account clears the previous account's draft (bugs 351, 382).
- The Recent Ranked Series page no longer renders blank when a player's name
  holds a character the game font cannot draw; every list-panel name passes
  one glyph sanitiser.
- A player name with angle brackets in it is no longer read as empty or cut
  short: the mod shows those brackets as round ones, so `<Name>` reads
  (Name) and `AC<DC>Fan` reads AC(DC)Fan.
- An abandoned 1v2 series is closed after 14 days with no game, with no
  winner and no award, and the solo seat can no longer change in the middle of
  a 1v2 series. A decided 1v2 game reported after its series was cancelled
  still pays its gold and XP.
- Bet refunds return the exact stake, and one refund that fails no longer
  blocks the others.
- A word in the chat filter that is also a common given name was removed, so
  that name is no longer filtered.
- Moderation: a mute reason containing a null character, which the database
  cannot store, is refused with a message saying so instead of a server error
  that lost the mute.
- An oversized cosmetic upload states the exact limit it enforces.
- The Translate portal button, on the backup connection, checks the secure
  connection first and opens the portal in the same press when it answers; a
  timer keeps retrying in the background, and no restart is needed.
- The server lists shop items that share a price in one fixed order, so the
  shop shows them in the same order on every visit while its items stay the
  same.
- Nineteen community faces that were already in the shop show their own
  descriptions instead of the general "community cosmetic" line. In 1.41.0
  these descriptions are also in Spanish, Russian, Ukrainian and Swedish.
- The Star Earmuffs face has new art.
- A new body colour, Demonic, is in the shop. Every client text that became
  translatable since 1.40.3 (over a thousand, Demonic's shop text and the new
  card trading, mail relay and dance-reason texts among them) ships in
  Spanish, Russian, Ukrainian and Swedish; eight Spanish labels that still
  showed English are translated.

**Schema changes:** migrations added since v1.40.3, by number: 306, 307, 308,
309, 310, 311, 312, 313, 314, 315, 316, 317, 318, 319, 320, 321, 324, 325,
327, 330, 331, 332, 333, 336, 337, 338, 340, 341, 342, 348, 349, 351, 352,
353, 354, 355, 356, 358, 359, 360, 361, 363, 364, 365, 366, 367, 368, 370,
372, 373, 376, 377, 378, 379, 380, 383, 384, 385, 386, 387, 388, 389, 390,
391, 392, 393, 396, 397, 398, 399, 400, 401.
Rollback files ship beside the newer ones; 374 and 375 are rollback-only files
for the mail relay.

- 363 revoked four ranked-FFA shutout awards below the finishing-count rule.
- 398 makes the five community faces visible in the shop once this release is
  published; they stay out of stock until their artists open sales.
- 399 replaces the placeholder description of nineteen community faces already
  in the shop, once this release is published.

## v1.40.3 — 2026-09-09

**The ranked room's region is measured again**

- The room a ranked match lands in is supposed to be chosen from both players'
  own Photon pings. In practice those measurements were usually too old to be
  used, and for some players they never ran at all. Three things were wrong and
  all three are fixed.
- The client refreshed its ping map only once it was older than 300 seconds,
  while the server refuses any map stamped more than 180 seconds before the room
  is issued. Everything in that gap was measured, uploaded, and then declined.
  The refresh threshold is now 60 seconds.
- The only trigger that could refresh the map while you were queueing was gated
  on being connected to Photon's master server — which you are not, at the main
  menu, which is where ranked players queue from. The queue-side refresh no
  longer asks about Photon's connection state; the idle menu sweep still does.
- A player who only ever queues ranked had no region list to ping in the first
  place. Photon builds that list solely from a name-server request it issues
  while it has no region set, and a ranked join sets one before that ever
  happens — so the ping never ran once for the whole session. The mod now
  fetches its own copy of the list from Photon's name server when the game has
  none. It is a separate, short-lived connection that reads the list and closes;
  it does not touch the game's own.
- A region left behind by the Sandbox no longer reports as the region you are
  connected to. Photon keeps the last region on the client after the Sandbox's
  offline mode ends, and it looks live: the connected flag and the server name
  both read normal, so a stale value was sent as a live one and outranked both
  players' real caches. The same read also went out mid-disconnect, naming the
  region being torn down.
- If the measurement still cannot run, nothing changes from before: the map is
  simply absent and the server picks the room from the regions it already knows.

**Fixes**

- Turning the thicker menu text setting back off no longer breaks chat. Every
  label the mod draws shared one font material, and the toggle destroyed it
  while the chat overlay and the hover profile card were still pointing at it —
  so their panels kept painting and their text did not, permanently. The toggle
  now re-points those labels instead of destroying anything. (Bug 351)
- Watching a match no longer opens the round winner's point orb already full.
  Nothing on a spectator seat ever returned the orb fills to zero between
  sequences, so a scored point carried over into the next one. Covers 1v2 and
  2v2 as well as 1v1. (Bug 350)
- Match reports no longer fail on the interval parameters used to age a report,
  which had to be typed explicitly for the database driver to accept them.

## v1.40.2 — 2026-09-08

**One Session button per sitting, beside the ID button**

- The Ranked and Casual history boxes carry ONE Session button per opponent per
  sitting, on the newest game you played them in that sitting, directly right
  of the ID button; W/L and the score moved right to make room. A sitting is the
  My Stats "Session Info" rule applied on the server: your finished games in any
  mode, split where more than 3 hours passed between two of them. Playing someone
  else in between keeps the sitting alive, so the button sits on the last game
  the two of you played in it. The report it opens covers every game of that
  pair in that sitting, ranked and casual together, with gold per game and no
  rating (the session rules). Time in the menu is not activity on the server: a
  break of over 3 hours with the game open splits the server's sitting where the
  panel's session would not. 2v2, 1v2 and FFA rows keep their per-series and
  per-game buttons.
- Needs the new server: against an older server the 1v1 rows show no Session
  buttons at all.

**Grow competitive clock: 240 FPS -> 120 FPS**

- Every eligible Grow bullet now grows as if its shooter ran at 120 FPS (it was
  240): one copy is about x3.1 over a full flight (was x1.8), two copies x9.6
  (was x3.1), three x30 (was x5.5). The room capability key changed with the clock, so
  a room that mixes this version with an older one falls back to vanilla growth
  on every seat instead of pinning two clocks; that lasts as long as older
  versions are in play. A spectator on an older version renders vanilla-scale
  Grow visuals until they update (damage is the shooter's and unaffected). The
  Info chart badge, the Grow article and docs/grow-mechanics.md say 120.
- The Grow article's vanilla numbers were wrong and are corrected: they had been
  computed from the C# field defaults (multiplier 1 over 30 units), but the
  shipped A_Grow prefab carries multiplier 4 over 40 units (read straight out of
  the asset file). One vanilla copy is about x1.4 at 400 FPS, x9.4 at 60 and x82
  at 30; the article said x1.07 / x1.53 / x2.31. docs/grow-mechanics.md already
  had the right constants; the Info chart is now on a log scale.

**Popups, keys, settings**

- Page overlays (the search boxes, hover graphs, the session report, the shop
  effect/dance/trail previews, the ranked-hint callout, the profile card) no
  longer paint over the Music and Mail popups, the Info and tournament popups,
  the metric picker or the full-screen card preview.
- Info > Controls & keys shows ALT: a tap while typing in chat switches the
  language channel (global, each language channel in turn, back to global). The
  Settings chat note says Alt (it said Tab).
- Settings: "Who can mail me" and "Blocked senders" are button-sized like their
  neighbours instead of spanning the panel.
- Broadcast seat: a tab request from the test lever or the idle showcase closes an
  open Music/Mail popup first (it used to stay over every tab opened after it).

**Server**

- `/players/{id}/matches` rows carry `sitting_head`; `/report` accepts
  `sitting=<match uuid>`. Migrations 302 (the client keys new since v1.40.1,
  with their portal context lines) and 303 (machine-translation seeds for the
  keys that have bundled translations).

**Mail and Music are icons now, not tabs**

- The Mail and Music pages left the tab strip. Two icons sit at the top right,
  above the tabs; the mail icon carries a red badge with your unread count. Each
  opens as a popup over a dimmed backdrop instead of taking over the page: Escape
  or a click on the backdrop closes it, the page underneath is untouched, and a
  half-written message survives closing and reopening. Confirmations and the
  report form still sit on top of the popup and take Escape first. The box sizes
  itself to the screen (down to a 32:9 monitor) and every mail view fits inside
  it — the message body and the composer's text area shrink before anything else
  does. A mail action that finishes after its popup closed (a delete, a block, a
  report, a send) still updates your inbox data, but its toast belongs to the
  popup that issued it and is not shown to a later one.

**Music plays on the first click (bug 346)**

- There is no prepare step any more: a track opens as a streamed clip in a few
  milliseconds and is decoded on the audio thread while it plays. Tracks opened
  during a session stay loaded (about 4 MB each) until the game closes, so
  switching back to a track is instant and nothing is torn down under a playing
  clip. A track whose file fails to open after the read is marked "Unavailable
  until the game restarts"; a failure before the read is retried on the next
  click. A delivery watchdog stops a track that has gone silent and moves on.
  Testing levers: `[Music] TestScript` (the self-test runner, including the
  `openall` memory gate) and the `compressed_mb` / `native_delta_mb` fields on
  the `[MUSIC-RESIDENCY]` log line.
**Ranked 1v1: the room region is picked from both players' pings**

- After the mod connects to Photon (and again every five minutes in the menu,
  every 90 seconds while a search is running) it pings each region on a
  background thread and sends the results along with the queue join and its
  polls. When both players' maps are fresh
  (under three minutes old) and overlap, the room goes to the region that is best
  for the pair under one rule: neither player is moved more than 20 ms beyond
  their own best region. When a map is missing or stale the previous ladder
  decides, as before. 2v2 and FFA rooms are unchanged for now. Log lines:
  `[REGION-PINGS] sweep started …` and the completion line with per-region ms;
  the server records `[QUEUE-REGION]` with the rung that decided. Needs
  migration 301 (two nullable columns on the queue row) before the api.

**Matched but never connected (bugs 335, 336, 340)**

- The first player into a queue-issued room is no longer moved out of it after
  15 seconds. The game's own region-rotation timer runs in every room the mod
  issues (the mod's search type is not one of the two the game exempts), and
  the mod's earlier guards only engaged once both fighters were present, so a
  partner who needed more than about 15 seconds to arrive found an empty room
  while the waiter had been swept into a public quick-match search — which is
  how a queued player ended up in a casual game against a random unmodded
  opponent. The timer is now frozen on joining any mod-issued room and its
  rotation is refused there; the mod's own 60-second wait (toast at 15 s now,
  was 25 s) is the only exit. Log line: `[QUICKPLAY-GUARD] churn timer frozen -
  mod-issued room <name>`. Room-code private games keep the game's timing.
- Queueing from the menu right after an online match (the game parks the menu
  in an offline room) made the join fire while Photon was still connecting,
  twice, then give up after 60 seconds ("JoinOrCreateRoom failed … State:
  ConnectingToNameServer"). The game's connect-wait keyed on a flag that stays
  set after offline mode; the joiner now clears it before connecting and issues
  the join only from the master-server state. Log lines: `[QUEUE-JOINER]
  connect flag reset (was=…)` and the result of every JoinOrCreateRoom call.
- Queue-issued 2v2 rooms now share the 1v1 rooms' wait: a lobby that has not
  filled after 90 seconds (toast at 30 s) returns you to the menu and leaves
  the team queue, instead of sitting on a notification with no way out.

**Overpower with a box in the blast (bug 327)**

- The game hands Overpower's per-player handler every damageable object in
  range, including boxes, which carry no player data; the handler threw and the
  rest of the explosion was skipped, so a player processed after the box was
  not hit. Non-player targets are now skipped, and one collider's exception can
  no longer abort the others. Applies in every room type.

**Press Jump to Join (bug 329)**

- The stall where the other player is standing in the lobby and the match
  never starts is fixed at its source. The game creates a player's body before
  it publishes which slot that player holds, and every other seat reads the
  slot exactly once, the frame after the body appears. When the two messages
  land a frame apart the slot reads as 0 — the host's — so the guest's body
  takes the host's place in the player list, the list never reaches two, and
  the game never starts; no error is raised anywhere. The mod now holds a
  newly arrived body's setup until its slot has landed (bounded, then derived
  from the host/guest rule), and publishes its own slot before its own body so
  an unmodded opponent never sees the reverse order either. Applies to every
  online 1v1 room, ranked included. Log lines: `[VANILLA-FIX]
  RemotePlayerIdOrder attached`, `[VANILLA-FIX] LocalPlayerIdPublish attached`,
  and `remote player body arrived before its p_id/t_id … deferring` when the
  race is caught.
- The other shape — a full room where the other player's body never appears
  at all (a seat that never pressed Jump, or whose game is stuck on its ready
  prompt) — had no exit but Esc. After 20 seconds in that state the escape
  hatch appears with Requeue (quick match only) and Return to menu; nothing
  counts against you. Mod-issued rooms are unaffected — they have their own
  wait.

**Match history rows**

- The stray "repli" at the end of the Ping cell is gone: it was the start of a
  peer-reported replica-age estimate added with the v1.40.1 telemetry, clipped
  by the cell. The opponent cell is wider (296 px, was 240) and is fitted by
  pixels rather than by a character count, so a name is only shortened when the
  cell genuinely cannot hold it; when the name plus title do not fit, the title
  is dropped from the row instead of rendering as "[Beginne..]". The ranked
  series header gets the same treatment.

**Online players on the leaderboards (bug 342)**

- A green dot marks players who are online on the 1v1, 2v2, FFA and 1v2
  leaderboards. Online means the mod's presence heartbeat was seen within the
  last 3 minutes and the player has not enabled Appear Offline. The boards are
  served from a read replica, so the marker also checks that the replica is
  fresh (within 90 seconds) and shows no dots rather than stale ones when it is
  not. Presence now has its own column (`presence_seen_at`, migration 296),
  written by the heartbeat alone — a match report that mentions a player no
  longer counts as that player being present. Only a heartbeat carrying the
  player's own verified session moves the marker or the 90-day activity clock,
  and a change to Appear Offline reaches the boards within replication delay,
  at most the 90-second freshness gate.
- The 2v2 leaderboard refreshes every 30 seconds while it is open; it used to
  load once per session.

**Dance emotes (bug 341)**

- The shop lists each dance with its duration, the emote wheel shows it on the
  highlighted slice, and while your emote plays a thin ring above your own
  player counts down the time remaining. Only you see the ring; nothing extra
  is sent over the network.

**No sound effects (bug 337)**

- A report of "no SFX" carried no fault signature anywhere in the log. The mod
  now writes one line describing the audio stack's current settings at every
  match start and at the end of every bug-report bundle, plus a line whenever
  the listener volume changes that names the writer when it was the mod's own
  (the background focus mute included). Read-only: nothing here changes audio.

**Minimised chat (bug 333)**

- The minimised chat is drawn with TextMeshPro instead of the IMGUI font, so
  emoji and non-Latin names render there the way they do in the full chat
  (monochrome for now; colour emoji is a separate follow-up). Long lines are
  shortened on character boundaries with a translated "[see F5]" suffix.

**Leaderboards hide inactive players**

- Players with no contact in the last 90 days are hidden from the leaderboards
  by default. A toggle on the board shows everyone (their rows are marked
  inactive), and the Discord `/lb` command gains an option to include them.
  Podium places, and the titles that come with them, are held by shown players
  only. Tournament sign-up and seeding lists are not filtered, and a player's
  own position is still reported while they are inactive.

**Rating previews**

- New read-only endpoints preview rating changes before a game:
  `GET /api/v1/rating-preview/ffa?ids=` (what first, last and each place would
  do to every listed player) and `GET /api/v1/rating-preview/2v2?team_a=&team_b=`
  (its response says when the win probability is an estimate). The FFA preview
  takes the lobby's score target (`score_target`, also an option on `/elo ffa`)
  and states the assumption it computed under. The Discord
  `/elo` command becomes a group: `/elo 1v1`, `/elo 2v2`, `/elo ffa`. The live
  FFA settlement runs through the same helper the preview uses; the two were
  checked bit-identical on every recorded settlement.

**Translations**

- Strings whose translation depends on context (the card rarity words, the
  betting window's LOCKED) now carry a context so they can be translated
  separately; the portal shows the context as a badge. Five strings need one
  re-translation; every other string keeps its existing translation.

**Broadcast seat**

- A config-driven quit lever (`[Broadcast] TestQuit`, broadcast identity only)
  for the seat's maintenance workflow.

**Hover profile card**

- Hover a player's name on the F5 page — the 1v1 ranked and casual history
  rows, the four leaderboards, the 1v2 solo and duo boards and the
  leaderboard's selected-player panel — and after a short pause a mini-profile
  card opens: name and title, tier, 1v1 rating and level, online status (hidden
  for players who appear offline) and your head-to-head in every mode: ranked
  series and games, casual, 2v2 on opposite teams, FFA placings, 1v2 as solo
  and as duo, plus your last meeting, the current ranked-series streak and your
  net rating change against them. Click the name to pin the card; Escape, a
  click elsewhere or any popup closes it. An open card refreshes every 15
  seconds. Labels that carry several names (Online now, Recent Ranked Series,
  the 2v2/FFA/1v2 recents, Session opponents) and names that already have a
  hover (tournament brackets, Records, 2v2 telemetry cells) open no card in
  this release.
- Server: the in-room head-to-head read gains the card's two members
  additively; per-mode aggregates are cached for 60 seconds, the profile is
  read fresh so Appear Offline applies at once, and the card reads the podium
  titles from the boards' cache without refreshing it.

**In-game mail**

- A new Mail tab: write to other players (up to 8 recipients, a 120-character
  subject and a 2,000-character plain-text body), read, reply, select and copy,
  report, block and delete messages, with a toast and a tone when new mail
  arrives. Settings gains "Who can mail me" (everyone by default, or only
  players you have played) and a blocked-sender list. Admins may address any
  number of recipients, or every recently active player at once.
- Server: send, reply, inbox, blocks and the "who may mail me" setting, with
  per-sender rate limits, plain-text enforcement (no code or markup) and
  idempotent retries. Reports and automatic spam detection open moderation
  cases in the admin channel that already logs suspicious game behaviour, with
  one-click mute, ban or dismiss; each click is re-checked against the
  clicker's current grant. A retention sweep removes old mail. Admin actions
  refuse a deleted account as actor or target instead of recording its former
  id. Migrations 297 and 300.

**Session reports**

- A Session button on the ranked, casual, 2v2, FFA and 1v2 history rows opens
  a per-game report of that sitting for its participants: damage and score
  over time, DPS, hit and block rates, ping and FPS, totals and builds. Games
  from one sitting are grouped without exposing any room information; only
  games the viewer played, with one consistent roster, are shown, and FFA
  players who had left are not counted as players. The rating line is tied to
  the exact series; FFA rows carry damage, kills, score and rolled-out picks;
  long sittings page their builds instead of cutting them off; the newest
  games are shown, at most 24 and fewer when the report would exceed its size
  limit, and the report says how many older ones were left out. Requires
  Steam sign-in; games recorded before telemetry show what exists. Migrations
  298 and 299.

**Rating graph axes**

- Rating graphs now compare players over time on a common footing. In-game,
  the leaderboard profile graph and the Compare tab's Elo charts gain an axis
  toggle — Updates (one point per completed ranked series, the default),
  Calendar, or Since first (days since each player's first plotted update, so
  every line starts together) — remembered between sessions. The two time axes
  are step plots: a player idle for weeks shows a flat run, never a slope. The
  graphs start at the first recorded update instead of an assumed 1500 and
  always show a player's most recent 500 rating updates (long histories used to
  stop at the oldest 500; FFA histories now use the same window). The Compare
  metrics "Elo over games/over time" are now simply "Elo" and "FFA Elo". The
  Discord `/graph` command gains the same `axis` option.

**In-game library: Spirit's charts**

- The "On Damage Types and Buff Activation" article now carries five drawn
  charts redrawn from Spirit's diagrams: the damage interaction matrix, the
  RefreshValid Silence sequences, the 0.35 s window sequences, the Refresh
  gate, and the full damage flow. The text tables they replace are removed,
  the article is split into shorter pages, and library search still finds the
  chart contents. Card names inside the charts stay English in every language.

**Head-to-head line at match start**

- Joining a two-player room (quick queue, ranked queue or a room code) shows a
  corner line for ten seconds and a Tab-Info line for the match: "vs NAME ·
  Last played 3 days ago · H2H 12-8 · Ranked series 4", "First time playing
  NAME", or "First played today" when the only games are from today. The
  numbers come from a new session-authenticated read that returns totals only;
  the name shown is the one the server holds for the opponent. In an ordinary
  room the line follows the seat: if the other player is replaced, it clears and
  re-fetches for whoever is there now, using the id that player's game
  advertises. In the room the ranked queue most recently issued, the line waits
  for the other player's game to name the opponent, and appears only when that
  name matches the one the queue assigned; it then follows the first game that
  matched, so if someone else takes that seat afterwards the line clears rather
  than showing the assigned player's record beside a different player. If the
  queue moves you on, the room you are actually sitting in keeps that
  protection. It is an agreement between two games about who is present, not a
  check of who really is.

**Lag notices (opt-in, default off)**

- Settings → "Lag notices" turns on short corner lines under the FPS label while
  a state holds: your game dropping frames (worst N ms), your ping to the relay
  high (N ms), the opponent's updates arriving late, or the
  opponent's game reporting a high ping. Several can show at once. Each state
  needs a few one-second windows to enter, three clean windows to clear, and
  waits thirty seconds before re-announcing. 1v1 fighter seats only; nothing is
  sent anywhere; the broadcast seat never shows them. A cfg self-test key logs
  the evaluator's canned cases at startup for verification.

**Music**

- Deselecting every track now plays the game's own music instead of silence.
  (Silence is the game's music volume slider.)

**Queue and shop**

- The queue's ready call requires the caller's own session, the same rule the
  poll already applied; a refused ready writes nothing and the seat returns to
  searching.
- A purchase re-checks that the item is still available under the same lock it
  reads the price with.
- The region a ranked room is created in no longer depends on which of the two
  clients happened to ask for the room first. Two players whose games agree on
  a region still land there, as before; when the two signals disagree, the
  choice goes to the region that recent finished games were actually played in,
  rather than to the seat that reached us first. When neither region has that
  evidence — which includes every pick made shortly after a server restart — or
  when both do, the tie falls to a fixed order: still arbitrary,
  but identical for both of you and no longer an advantage for the faster
  connection. For the 1v1 ranked queue there is now a measurement too: at the
  menu and while you wait in the queue, the game pings each Photon region
  itself and sends the numbers with your queue entry. When both of you have
  recent numbers, the room goes to the region with the lowest worst-case ping
  between you, provided that costs neither of you more than 20 ms by your own
  measurements; otherwise the rules above stand. 2v2 and FFA rooms are
  unchanged.

**Diagnostics and small fixes**

- The music watchdog's "vanilla re-entry UNVERIFIED" line now records what it
  saw (the mod's guard flags and the game's own menu/in-game music flags) so
  the next occurrence can be diagnosed from the log.
- The footer's version comparison is ordered: a local build newer than the
  advertised version no longer reads as outdated.
- The Phoenix sound fix no longer attempts an exact-method lookup that always
  missed (it produced 46 HarmonyX warnings per session and patched nothing).
- When an opponent leaves a ranked series part-way through, the report of that
  leave now survives a failed send. It records which series it belongs to and
  is retried in the background, across a restart if need be, so a single
  refused request no longer loses the record that feeds leave %. The retries
  are bounded, and the bound is now the same six hours the server itself will
  still accept the report in — it used to run out after about an hour, which
  threw away reports the server would have taken. A relaunch gives a
  still-queued report a fresh set rather than resuming a spent one. The
  server accepts one such report per series per player however many times it
  arrives. A report that names the wrong series is not thrown away: the server
  falls back to working out which series the two of you are in, exactly as it
  does for a report that names none. What it will not accept is a leave filed
  against a sitting the server has since replaced — because the two of you have
  started a newer one — or against a tournament match the bracket has already
  decided. A leave queued while the server was unreachable is no longer refused
  for arriving late: it is judged on whether that sitting is still the one you
  were last put into, not on how long the report took to be delivered.
- **What counts as proof that a leave happened.** A leave reported before any
  game in the series has finished used to be accepted on the running score
  alone — and the running score is sent by your own game, so the score that
  proved the match was real could come from the same player filing the report.
  For that case the server now wants the score post from the LEAVER's game,
  which the reporter has no way to send. It asks this only of accounts that
  have signed in through Steam at least once, since those are the only ones
  that can produce it; everyone else is judged exactly as before, and a leave
  after any completed game is judged exactly as before either way. Nothing
  changes for the ordinary case: both games send the score as it changes, so by
  the time a leave is reportable, the leaver's own game has already said it was
  there.
- **A leave report is no longer thrown away for arriving before its proof.**
  "The server has no record yet that anything happened here" used to be a
  permanent refusal, and your mod deletes a permanent refusal — but the
  leaver's own score post can still be in flight when you file, since their
  game keeps re-sending it after they drop out of the room. That refusal is now
  a retry while the sitting is live, and becomes permanent once the sitting has
  been quiet for hours. The server decides that, not the mod: a queued report
  gets a fresh set of attempts on every relaunch, so only the server can retire
  one that will never qualify.
  A leave seen in the moment between one game being recorded and the next
  starting has no series to name, and is still a single attempt.
- The background queue of unsent match reports no longer stops for the rest of
  a session if one pass over it fails, and a report that lands on its first
  attempt can no longer make the queue drop a different one.
- A leave that could not be sent at the time is retried in the background on
  the same bounded budget as any other queued report, across a restart if need
  be, and is filed against the series it was
  watched in rather than whatever series is current when the retry lands. A
  report the game cannot tie to a series is sent once and not queued, so
  nothing is filed against a guess.
- New diagnostic keys in the config file, both off by default and only useful
  if you have been asked for a measurement: `[Music] StreamProbe` plays one
  track on its own private audio source and writes timing, output and memory
  readings to the log, and `[Music] StreamProbeRun` says which track. It never
  runs inside an online room and never touches your music settings.

**Broadcast seat only**

- The overlay closes itself when left open with nobody at the seat: after
  30 s without input inside a room, after 60 s at the menu; showcase-owned
  pages are left to the showcase; an open prompt counts as presence. Player
  seats are not affected (a player version was reviewed and deferred).
- The `TestOpenTab` lever accepts a click form that runs the Music tab's
  Prepare click in the tick that reads it, only with the page already open
  on the Music tab and the seat idle at the menu; anything else is refused
  with a logged reason, and transport actions are not lever-driven.

**Schema changes:** migrations **292** (`issued_room_regions` — the region and
player pair this server issued for a ranked room), **293**
(`series_dc_grants` — which sitting the server last put a pair into) and **295**
(`series_progress` — which seat posted an observation of a sitting) BEFORE the
API deploy. After it, in numeric order: **288** (client i18n keys for the new
library strings), **289** (machine-translation proposals for es/ru/uk/sv for
those keys), **290** (client i18n keys for the head-to-head and lag-notice
strings), **291** (their es/ru/uk/sv proposals) and **294** (one grant per
sitting that was already live when 293 shipped). The same translations ship
bundled in the client.

**292, 293 and 295 go first, and the order is not cosmetic.** The new
match-report path SELECTs from `issued_room_regions`; `series_dc_grants` is
wider than that — every path that puts a pair into a series writes a grant, so
an API deployed ahead of 293 would fail **match reporting, queue ready, queue
poll, preflight and leave reports** with `undefined_table` until the table
landed. That is the whole ranked hot path, not one endpoint. `series_progress`
is narrower — the leave-report predicate reads it and all three live-points
endpoints write it — but an API ahead of 295 would fail every leave report on
`undefined_table` and record no attestations, so it goes with the other two.
The i18n seeds only add rows the client already carries bundled, which is why
those four stay after.

**Two switches ship OFF and are armed from `.env` plus a container restart.**
`DC_REQUIRE_VERIFIED_SEAT` drops the fallback that judges accounts without a
verified Steam session by the old rule; do not arm it until verified sessions
are broadly held (162 of 4663 accounts have ever held one), or genuine reports
start failing. `LIVE_POINTS_REFUSE_MISMATCHED_SEAT` refuses a live-points post
whose session token names a different player than the post claims. Both are
mapped under `api:` in `docker-compose.yml`, which is what actually delivers
them: this project has no `env_file:`, so a key in `.env` that is not named
there reaches compose and never reaches the process.

**294 goes LAST, after the API is running on both boxes,** and that order is
also load-bearing but in the opposite direction. It backfills a grant for every
sitting that was live at deploy time, and only the new API writes grants — run
before the deploy, every pair who started a series in the gap would have none,
which is the exact window the backfill exists to close. It is idempotent
(`ON CONFLICT DO NOTHING`), so re-running it cannot disturb a sitting the live
code has since re-stamped.

## v1.40.1 — 2026-09-03

**Clavar la Bala: two more tracks**

- "Principio de Ronda" and "Nube Tóxica" join the album as tracks 13 and 14
  (a new immutable music asset revision, ar3; existing tracks are unchanged
  and keep their ratings). The shop listing says 14 tracks.

**Queue**

- The 1v1 queue poll now requires the caller's own Steam session; a seat
  whose polls are refused for 30 seconds straight (long enough for the
  session to be re-minted, at least three polls) stops polling and says so,
  attempts to leave,
  and otherwise lets the server's non-polling sweep clear the seat shortly. Pair writes are reciprocal: declining a pre-room match releases
  the partner only while the partner's row still points back at the caller,
  the room is issued through one conditional write that
  requires both rows to name each other (ready, room-less), and a pair that
  no longer matches dissolves only the caller's row (the ready-up answers
  "dissolved" and the client returns to searching by itself). Leaving the
  queue deletes only the leaver's row; once that deletion is recorded, a
  pre-room partner is released by its own next accepted poll, which is what
  tells that client to start searching again.

**Network diagnostics** (carried over from the reviewed-but-unshipped Release A
work of 2026-09-03; first shipped here)

- The 1v1 match report carries 25 optional per-seat network fields from the
  reporting seat only (sender counters, Photon resend/discard/CRC counts and
  queue depths, frame-hitch counters — the full histogram stays in the bug
  bundle — and observer tags that mark gaps a still opponent, a Phoenix charge
  or a receiver-side frame can explain: evidence for review, not a verdict on
  the cause). They live outside every match HMAC canonical, are never public
  response data, and need migration 284.
- Bug bundles gain versioned `[NET-*]` lines with per-view evidence; the
  corner HUD shows a labelled one-way replica-age estimate (peer-reported
  input, 1v1 only) and the recent frame/resend facts; the broadcast seat runs
  a gstats sentinel self-test.

**Music: preparation at the main menu** (Release A, first shipped here)

- Downloaded tracks are decoded only inside an explicit main-menu click (a
  Music-tab control such as Prepare or a track's Play, or the Shop's
  Preview), one track per click, and never while this seat is itself joining
  a game. v1.40.0 could decode several just-downloaded tracks together around
  the first card pick (320-700 ms each) — the hitch some players felt there.
  The Music tab's Prepare button shows what is still pending; with Loop on
  (the default) a track that ends before the next one is prepared repeats
  instead of going quiet; a failed decode is retried only by a click.

**Held from this release:** the bug #334 music change (silence instead of
vanilla while nothing is prepared, between-round clicks) did not pass its
certification rounds and is not in v1.40.1. Against v1.40.0 the music engine
changes by the Release A playback work above (the main-menu preparation rule
and a short fade on start and resume) and by the new tracks. The report stays
open.

**Schema changes:** migrations **284** (Release A: 50 nullable per-seat
network columns on `matches` — required before the v1.40.1 API, whose model
maps them), **285** (Clavar la Bala 12 -> 14 tracks; deploys with the API
because `/music/rate` validates `track_idx` against `music_track_count`),
**286** (i18n client keys), **287** (v1.40.1 release notes x5). Deploy order:
284 -> 285 -> 286 -> 287 on the primary (standby replay confirmed after the
migration phase) -> API on both boxes -> client release + Thunderstore ->
LATEST bump.

## v1.40.0 — 2026-09-02

**Music: a full in-game player and the first two albums**

- New MUSIC tab (F5): every album you own with per-track checkboxes, a
  bottom-docked player — play/pause, previous/next, stop, loop, shuffle, a
  seek line, and a volume slider — plus per-album ON/OFF switches. The vanilla
  ROUNDS OST (by Karl Flodin) is listed there too, selected by default, and
  the game sounds exactly like it always has until you change something.
- Two albums by Sid in the Shop's new MUSIC section: **Another Round**
  (7 tracks, Metal / Phonk, 1g) and **Clavar la Bala** (12 tracks, Flamenco
  Metal, 1,000g). Click an album row to expand its track list and preview any
  song (30s). Albums appear on the Home page like new cosmetics, with the
  artist, genre, price, and date.
- Your picks play in matches (card picks duck the music the way vanilla
  does); an opt-in setting plays them at the main menu too — or silences menu
  music entirely. Another opt-in shows a small "Now Playing" credit line.
  Audio downloads on first use (previews are a small pack; full albums fetch
  when you own one). Music is entirely yours-side: opponents hear their own.
- Music artists earn 50% of album sales, manage their album's shop listing
  name and price (the Music tab and now-playing keep the compiled album
  name), and can gift copies — sales show up in the Artist tab like any
  other item.
- Rate any song 0-5 stars right in the track row. Ratings are private; the
  community average updates on a random 2-24h delay so a change can't easily
  be matched to whoever was just online.

**Dances: actual body movement**

- Dance routines now move the whole dancer — hops, bobs, leans, shimmies and
  hip-sway alongside the arm work (the body motion was always there, it was
  just far too subtle to see at gameplay zoom). Six more dances join the shop:
  Jumping Jacks, The Shimmy, Disco Fever, The Helicopter, The Robot, and
  The Floss.

**Quick chat is a wheel now**

- Hold Q for the quick-chat wheel: point at a phrase and release to send it,
  or pick "More..." for the full list (social lines, courtesies, emoticons —
  including a table flip). Clicks inside the wheel never fire your gun or
  raise your block. The old Y menu and its 1-9/0 number picks are retired,
  and the phrase list was rebuilt (GG, Hi!, Nice shot, recruiting lines, and
  more). Phrases still arrive in each reader's own language.

**Dance emotes (new shop category)**

- Hold E between rounds for the emote wheel: point at a dance you own and
  release to play it for everyone in the room. Two launch dances — The
  Bounce and The Wave — live in the Shop's new DANCES section, where the
  Preview button plays the exact choreography on a puppet before you buy.
  Dances cancel instantly when combat starts and never touch gameplay.

**Silence's red X actually shows**

- The Silence status X never rendered: the base game ships the indicator
  mis-wired (its Scale animation starts at zero and nothing sets the first
  frame), so every silenced player since launch showed only the cast
  sparkle. The mod now rewires it on spawn — a silenced player has a clear
  red X overhead for the whole duration. (v1.39.6's changelog claimed this
  worked; that claim was wrong, and this is the real fix.)

**Betting locks when it should (bug #324)**

- Live 1v1 points now reach the server reliably: missed/failed updates
  retry, a periodic refresh closes the gap a lost packet left, and the
  server no longer swaps the pair's points when the non-reporter's client
  sent them. Betting on a series now closes at 2 points scored in game 1 the
  way the rule says — in-game and in Discord — instead of staying open
  minutes into a decided game.

**Healing you can see**

- The health bar renders a blue segment for recent healing again (Leech,
  Pristine, regen): the segment now tracks a rolling window of the last
  ~1.2s of gained health and draws above both fill layers. It had been
  invisible since the bar's last rework.

**Tournaments**

- Discord trophy + participant roles are only assigned for tournaments with
  16 or more players.
- New achievements: win a Sync or Async tournament, take 2nd in either, and
  Iron Bracket — play a whole tournament without forfeiting (an opponent
  forfeiting to you still counts as played). Backfilled for past brackets.
- The 1v1 podium titles now read "1v1 1st Place" (etc.) in line with the
  other modes, and podium titles are revoked when a new podium displaces
  you.

**Info library**

- Nine new visual diagrams across the articles (Grow's curve, the netcode
  map, bet windows, bracket flow, forfeit clocks, refresh flow, movement
  windows, team formats, and when-what-counts), and the Controls board +
  article now teach the Q/E wheels.

**Compare, Cards & Shop**

- Compare > Cards: two new metrics — "5-0 Sweeps" (most flawless games won
  with a card) and "Most Stacked" (highest same-card stacks ever picked).
- Compare > Players: "Shop Sales" — the shop's own sales board (purchases
  and revenue per cosmetic, top sellers, totals).
- Card Stats: a search box filters the card list, next to the sort row.
- Twelve new trails (gradients, particle effects, and a 10k Galaxy
  starfield).
- SCR menu footer: YouTube, Twitch and Thunderstore buttons beside Discord
  and GitHub; your player name moved up beside the title, styled like
  in-game.
- Broadcast idle showcase: the between-games tour now walks the Compare
  metrics, scrolls the leaderboard to the featured player, and sweeps
  through profiles.

**Schema changes:** migrations **276** (Another Round album row), **277**
(album release), **278** (`music_ratings` + `deploy_markers` +
`shop_items.music_track_count`), **279** (Clavar la Bala row + royalty
columns on `player_items`), **280** (music activation marker — operator
gate), **281** (Clavar activation + artist attribution; requires 280's
marker), **282** (i18n client keys, +356), **283** (v1.40.0 release notes
x5). Deploy order is load-bearing: 278 -> 279 -> api -> 280 -> 281 (the
purchase royalty stamp is fail-closed on 279's columns).

## v1.39.6 — 2026-08-30

**The menu no longer leaks into the game**

- While the F5 menu is open, your inputs stay OUT of the match: clicks no
  longer fire your gun, Space no longer readies you up or confirms cards,
  Remote Control bullets stop tracking the cursor across menu buttons, and a
  fire button held across the menu closing can no longer deliver a surprise
  charged shot.
- Escape while the menu is open now ONLY closes the menu. It no longer opens
  the game's pause menu behind it — and no longer cancels a ranked match that
  is mid-connect (the loading screen's escape abort was reachable from the
  same key press).
- The main-menu mod button reappears after visiting Sandbox (Photon's offline
  mode kept pretending you were still in a room, which parked the injector
  forever).

**Finding your first game**

- Until your first ranked game, the Search Ranked button glows through a
  rainbow cycle with a floating callout above it pointing at it, plus a
  one-time hint toast. Clears permanently the first time you press it (per
  account).
- New Info-library article: "Controls & keys" — a keyboard map of the
  competitive and base-game controls used during play, with a plain-language
  legend.

**Tournament forfeit, finally visible**

- The tournament Forfeit button (built earlier, never shipped — it merged
  after v1.39.5 was cut) reaches players in this release: it is its own row
  on the My Match panel in the Tournaments tab whenever your match is in its
  ready phase, with a two-click confirm.
- Opening the Tournaments tab now lands on the sub-tab that holds YOUR live
  match (once the mod's ~20s match poll has seen it — a cold-start open
  stays on the default sub-tab until the first poll) — a participant whose
  tournament sat under the other sub-tab used to open the tab and see no
  match panel (and no Forfeit) at all.

**Leaving on purpose**

- The escape menu now has a LEAVE MATCH row during competitive play, with a
  two-click confirm and per-mode copy that says exactly what leaving does.
  It deliberately does NOT say "forfeit": today's rules settle a leave
  differently per mode, and the button promises only what actually happens.
  (Tournament matches keep their own Forfeit button in the Tournaments tab.)

**Info library, now with pictures**

- Seven articles gained nine charts and diagrams built from the real game
  data: the DoT tick timeline vs the 0.3s block window, the rank ladder with
  reward multipliers, rating-confidence bands, the XP curve with level-up
  gold markers, a gold-sources legend, the best-of-3 flow, FFA placement
  shares, and the keyboard guide above.

**Health bar honesty**

- Spectators now see the red "recently lost" segment when poison and other
  damage-over-time drains a fighter (the spectator display path bypassed the
  vanilla trigger).
- NEW: a blue "recently healed" segment on everyone's health bar — lifesteal
  and regeneration finally render as the health flowing back in, on every
  seat including the broadcast spectator.

**Silence's red X**

- Restored the silence X (and the stun triangles) two ways: the mod's own
  body-color pass no longer captures the indicator sprites, and a vanilla
  lifecycle trap — where the indicator's scale could be snapshotted as ZERO
  and stay invisible forever — is now repaired at the moment the debuff
  fires. If an X still fails to show after this build, the log line
  `[STATUS-X]` will say which mechanism fired.

**Five community faces**

- The Mobsta, Well Wraped Hat, Phoneix Gaze (the catalogue's second ANIMATED
  face — 4 frames at the artist's approved 5fps), Smart Specs, The Cryptid.
  Bundled from the approved placement snapshot with every PNG (and every
  animation frame) verified against its stored md5 before being written.

**Cross-platform chat moderation (server + client)**

- Moderators can now mute a person's Twitch/YouTube identity, not just their
  in-game one; a mute follows the person across every bridged surface, and
  deleting a message removes its mirrored copies from the other platforms
  too.
- Chat lockdown: moderators can pause the whole bridged chat during an
  incident; players see an explicit locked/unlocked notice instead of
  messages silently vanishing.
- Disconnect reports are now bound to the reporter's own authenticated
  session, and the POISON-SILENT diagnostic claims only what that seat
  actually observed.

**Broadcast (ops)**

- The stream no longer parks on the black between-games card: while idle the
  broadcast seat now tours the mod (Compare across the ~12 most recent
  online players, their leaderboard profiles, the 2v2/FFA boards), and
  post-game report screens no longer lose their opening ~12 seconds to the
  "Starting soon" card.
- Stream chat: mirrored in-game/Discord/YouTube lines no longer render twice
  on the overlay during normal connected operation (during a brief chat-
  server outage the mirror copy deliberately still shows so no chat is
  lost), and the Twitch mirror now spells out [Game]/[Discord]/[YouTube]
  instead of [G]/[D]/[YT].

## v1.39.5 — 2026-08-28

**The launch build**

- Public launch of the mod alongside the announcement and trailer.
- **New players now start on the live rank title** (it updates automatically
  as they climb): the rank title is granted and default-equipped on a
  player's first mod-authenticated action (`_mark_mod_seen`).
- **The Beta title is retired from offers** (migration 261): it can no longer
  be bought or granted — but everyone who owns it keeps it forever and can
  still equip it, a permanent beta-tester badge. Existing players' equipped
  titles are untouched, and a deliberately cleared title stays cleared (the
  default-equip only fires on a player's first-ever mod action).
- In-game release notes in all five languages (migration 262).

## v1.39.4 — 2026-08-26

**Hit % stopped drifting to 100%**

- Shots fired and shots hit were counted by different rules. The fired side was
  gated on a pick-phase flag driven by ROUNDS' debug-log TEXT, which is false
  from "Round over" until "PICK PHASE" is logged ~2.3s later. That window is
  live combat, so its shots were refused the denominator while their hits still
  counted, and the ratio climbed until a hits<=fired clamp pinned it at exactly
  100 rather than above it. Symmetry is now enforced at projectile birth.
- A fixed client can no longer be fooled by an unfixed PEER. The telemetry
  broadcast carries a counting-era tag, and a peer's bullet numbers go over the
  wire as NULL rather than guessed at when that tag is absent — including the
  derived hover-graph series, which shipped ungated in the first attempt and drew
  the old ~100% curve under a 0% caption. Covers the 2v2 and FFA peer paths too,
  not only the 1v1 summary.
- The 1v1 history row no longer fabricates "Opp: Hit 0%" for a peer that merely
  blocked once. Career Hit % totals are deliberately left alone: measured against
  production, the drift tops out at 50% and 0.37% of match rows saturate, so a
  wipe would destroy real history to remove a bias invisible at that scale.

**Untouchable revoked and re-earnable**

- The detector sampled a "took damage" STATE at 10 Hz instead of hooking the
  damage EVENT, so a player who went from full health straight to dead never
  occupied the state it looked for and was awarded it anyway. Revoked from
  everyone; holders KEEP the gold. The no-double-pay guard now covers all three
  paying grant paths — the third (admin grant) was missed by two revisions of
  that fix and by a docstring asserting there were only two.

**Five community faces**

- Lucky Coin, Lucky Ears, Militia Man, Sadness, Sinister Smile, bundled from the
  approved placement snapshot with each PNG verified against its stored md5
  before being written.

**Fixes**

- FFA: the first map of a sitting ran unscaled on the host while every peer
  scaled it, which is why networked crates and saws sat at the wrong positions.
- A destroyed card in the offer list could softlock the room.
- Damage tracking counts events rather than sampling at 10 Hz.
- Session tally re-arms on the series-start edge; head-to-head staleness is
  marked when a series ends; an unread marker on match history.
- Link codes require a live Steam session, and the label showing them wraps
  instead of clipping a long Discord handle or a translated string.

**Server**

- Read-replica mode: the standby skips every write path rather than attempting
  writes against a database in recovery. The podium-title grant had been failing
  silently there, from fifteen GET routes, for as long as read-routing was on.
- `/health` now reports which box answered. It returned byte-identical JSON on
  both, so nothing on the network could tell a write-skipping box from a
  writable one.
- Three pre-existing defects: a version-check loop spinning with no throttle, an
  endpoint that 500'd intermittently after catching a failed write without
  rolling back, and the admin grant path above.
- Bug-report logs are scrubbed of OS usernames and Discord ids before an admin
  reads them, on the existing endpoint as well as the new download route.

## v1.39.2 — 2026-08-23

## v1.39.3 — 2026-08-24

**The Info library — an in-game wiki (Settings › Info)**

- The Settings tab's "Stats" section grew into a full explainer library on its
  own sub-tab (Settings group › Info): 31 articles across 8 color-coded
  categories — game mechanics (blocking, poison with the real shipped tick
  numbers, Grow's frame-rate math, movement/shield tech, netcode & Photon,
  known vanilla bugs), every mode, tournaments (pairing, the bot's DMs and
  what each reply does, deadlines/forfeits/prizes), ratings & the exact
  reward formulas for every mode, betting, tracking & anti-cheat, the
  vanilla-safety guarantees, cosmetics, titles and exact achievement
  conditions for all 50.
- Left column = topics, right column = a dark reading pane sized for long
  text. Every factual claim was verified against the code (and, for poison,
  against the shipped card assets: Poison ticks 10 times over 3 seconds —
  one tick every 0.3s, exactly one block window wide).
- The Settings "Stats" box became "Info": a single pointer button into the
  library. (The old "How stats are tracked" popup button was dropped in the
  same pass, per Sid — its full content is the library's 'How stats are
  tracked' article.)
- **Search**: a search box above the topic list filters articles by title
  AND full body text, live per keystroke, in every language. Empty
  categories hide while filtering.
- **Cross-references are real links now**: the blue article names inside a
  page (e.g. "see Blocking") open that article on click.
- **New article — "Damage types & buffs", by Spirit**: his complete 'On
  Damage Types and Buff Activation' research paper, reproduced with the
  full 31-row damage-interaction table, the RefreshValid model, the 0.35s
  window, the damage thresholds, and the decision flow. All findings and
  the voice are his; credited in the byline.

**Background mute now opt-in (bug 267, Stan/Archnith)**

- "Mute audio when tabbed out" default flipped ON -> OFF with a one-shot
  migration for existing installs, and the missing F5 Settings toggle for it
  was added (Performance box).

**Broadcast seat: night-pack rotation, swapped during card picks**

- The stream's auto-rotation now cycles ONLY the 9 dark night-pack skins
  (per Sid, for the foreseeable future), and advances during the card pick
  phase instead of seconds into the next battle, so the swap lands while
  viewers are on the pick screen. FFA (no shared pick screen) keeps the
  per-map-load advance within the same night pool.
- The auto-rotation is now broadcast-identity-only: a normal spectator keeps
  their own equipped map skins and manual Shift cycling, exactly like when
  they play.
- The 2v2 / 1v2 / FFA mode explainers were corrected while composing them
  into the library: 1v2's reward text now shows the real difficulty
  multipliers (it under-promised since the economy fix), FFA's host-settings
  list gained the cards-per-draw option, the FFA pick/leaver notes now match
  the shipped rules, and 2v2's ready-timeout wording covers custom lobbies.
- Discord bot FAQ fixes riding along: async-tournament cadence (a new one
  opens 2 days after the last ends) and an up-to-date answer on Grow
  normalization.

**Map skins: the Night pack (9 new) + an ambient-effect layer**

- **Forest Fire** (embers), **Moonlit** (stars), **Eclipse**, **Underworld**
  (embers), **Night City** (city-light twinkle), **Night Park**, **Rainy Day**
  (rain), **Midnight**, **Blood Moon** (red stars). All in the Blackwood
  family: pitch-black, dark-brown and deep-red skies with walls kept darker
  than the rest of the catalogue. 75g; the six with an effect 150g.
- New backdrop-layer effect emitter (`MapSkinEffects`): embers, rain and
  stars drawn behind the map on the background camera's layer. It never
  touches the map's own particles, never sits in front of gameplay, obeys
  the Animated Cosmetics toggle, and engages only after the deferred tint
  pass. Tour-verified in game on the broadcast seat.
- Broadcast-seat verification levers: `TestOpenTab` opens the F5 overlay on a
  tab (optionally scrolling the Shop) from the cfg, re-read every 2s on that
  seat only; `TestMapSkin` accepts a comma list,
  `TestMapSkinSandbox` enters LOCAL > SANDBOX by itself, and
  `TestMapSkinTourSeconds` advances the list — a whole pack screenshots
  itself in three minutes.

**Name styles: 10 new gradients (1500g)**

- Fade, Earth, Orchid, Sapphire, Emerald, Steel, Ash, Royal, Blood,
  Twilight — one table line each; dark endpoints stay legible over the
  darkest skins.

**Community cosmetics**

- Five new face items: Shock Shades, Cat Mouth, Cat Eyes, The Challenger,
  Goober (approved placements compiled verbatim). Seasonal Spring's
  re-approved placement (scale 1.4) is published.

**Translation portal**

- "Session expired" on every open for players whose game and browser reach
  the server from different addresses (Cloudflare WARP, privacy relays,
  split-tunnel VPNs): the session now binds to the first browser that uses
  it; an address mismatch is reported as such; every gate 401 logs a
  `[PORTAL-AUTH]` line.
- 53 new client keys synced with machine translations seeded in es/ru/uk/sv
  (also bundled in the client).

**Ranked / economy (server)**

- Glicko-2 tau 0.5 → 0.6 in every mode (FFA previously fell back to a
  different value); hardcoded, with a startup log of the effective value.
- Heavy-favourite bet wins (stored odds ≤ 1.5×) redirect 20% of the PROFIT —
  never the stake — to the fighter/team you backed, in all three modes;
  quotes already reflect it; reversals claw it back. (Community idea.)
- Match history is searchable by opponent name (server filter, paged).

**Fixes**

- Rating-change displays show decimals for small changes consistently on
  every surface (Stan, #262).
- My Stats history gains a name search box (Stan, #263).
- Custom player colour missing on the card-pick body in room-code games
  (the gate matched only mod-issued rooms); also re-asserted on rematch.
- Looping map sounds (saws, Abyssal Countdown) carrying past their round:
  a round-boundary sweep stops orphaned loops, with a trailing pass relative
  to the latest boundary.
- Presence `last_seen` stamps had been failing silently since the
  MIN_MOD_VERSION auto-raise deploy (an untyped CASE parameter) — hotfixed.
- Broadcast seat: engine render cap while the director is active (GPU heat)
  and one FPS governor for the cap / unfocused cap / deep idle so a player's
  real frame-rate setting can no longer be lost; rotation dwell 5 min with a
  non-battle-moment deferral (up to +5 min).
- Broadcast bot (VM): idle-quit dormancy machinery ships INERT
  (`dormant_after_seconds` = 0, operator flag) after review; the games-only
  probe, global recovery floor and permanent safety halt are live.

**Schema changes:** 244 (`fighter_tax` on the three bet tables), 245
(`i18n_portal_sessions.first_use_at`), 246 (night-pack + gradient shop
rows), 247 (cosmetic release + Spring rev 3), 248 (53 i18n keys), 249
(212 translation seeds), 250 (release notes, five locales).

_(older entries trimmed - full history on GitHub)_
