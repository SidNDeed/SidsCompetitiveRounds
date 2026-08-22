## v1.39.1 — 2026-08-22

**Tournaments: deadline check-ins and tidier histories (Aug 22)**

- **Async deadline check-in DMs.** On the last day of an async match's
  7-day window, the bot DMs both players asking whether they've made
  contact and plan to play today - three buttons: yes (extends the deadline
  24 hours - once per opponent per tournament, each player has their own
  extension), "I reached out - no response / they quit", "not yet - still
  coordinating". The buttons survive bot restarts and verify the clicker
  owns the linked account.
- **One player wanting to play is no longer punished for the other's
  silence.** When an async match times out with neither side ready, a
  player who had answered the check-in now wins a
  normal forfeit instead of both players being eliminated - the exact
  losers-bracket double-DQ that hit this week is impossible now. (That
  match was also repaired by hand: the willing player advances with a
  fresh 7-day deadline.)
- **The tournament Forfeit button is deliberately held for a dedicated
  lifecycle pass.** Forfeited finals still need correct podium minting,
  terminal series need wager settlement, and late reports need isolation
  from already-resolved matches.
- **Sync and async tournament histories are separate now.** The Recent
  Tournaments popup shows only the sub-tab's own kind, and your
  placements line lives in that popup instead of the page bottom.
- **The FFA match-point banner no longer renders styled names HUGE.** A
  nametag size tag reaching the banner made the name enormous; names keep
  their color/bold styling but geometry tags are stripped.
- **FFA game-over freeze fixed** (bug 261): once a player in slot 0/1 had
  left, every other seat froze on the VICTORY screen because the rematch
  popup crashed looking up an empty team's color.
- **Muted-players header fixed** (bug 259): a styled nametag no longer
  renders as "(color=#55CCFF" - styling tags are stripped before
  truncation, and real angle brackets in names still show as parens.
- **Invisible Toxic Cloud** (bug 260): two fix designs were refuted in
  review (the second disproved the diagnosis itself); the report stays
  open with a field diagnostic riding this release to catch the real
  mechanism in production logs.
- **New cosmetics**: Seasonal Spring (animated, 8 frames) and Nuclear
  glasses, both by the community artist behind the Poison set.
- **FFA early-leave grace goes LIVE with this release** - the client now
  reports the leave-time score the server rule has been waiting for. A
  second one-off correction (migration 236) repaired the one affected
  game played since the first backfill. The async losers-bracket repair
  is migration 237.

Schema changes: migrations **238** (tournament check-ins + deadline
extensions), **239** (machine-translation seeds for 44 new strings x 4
languages), **240** (cosmetic release flips).

**Bug-report sweep (Aug 21)**

- **2v2 DC-rejoin no longer creates duplicate series** (bug 245, dedicated
  hardening pass after four review rounds). The disconnect report has marked
  a series "incomplete, admin decides" since the manual-control policy, but
  the queue's resume path still only looked for the legacy paused state — so
  four players re-queuing after a DC always got a brand-new series, leaving
  up to three live rows for one sitting in the 2v2 tab. Re-queuing within 30
  minutes (queue OR hosted lobby) now re-locks the four onto their original
  series (same teams, score kept, spawn/room state reset); every same-four
  creation path shares one serialization and resolves the WHOLE family
  (zero-game husks superseded with bets reconciled); a late disconnect
  report about the abandoned room can no longer forfeit the resumed sitting
  (room fence + wall-clock relock stamp); lobby wagers staged against a
  fresh series are refunded rather than bound when the Start adopts a
  series with a decided game; and the continuation self-heal picks the row
  the caller can actually use, never a husk.
- **The broadcaster switches to the better game** (bug 244). The rotation
  rule could only fire when the rotation set held two games, so a lone
  higher-priority game (a 2v2 outscoring the watched 1v1, or a lone
  tournament game) could never preempt — the seat stayed on the lesser game
  indefinitely. The dwell window (no switching inside 3 minutes) is
  unchanged.
- **Tournament games are labeled in the stream posts** (bug 250). The
  matchup lines said "Ranked 1v1" for tournament games because the label
  consulted the narrow mandatory-spectate classifier; a display-only
  resolver now follows the game to its series and labels "Tournament 1v1"
  (with the trophy) for sync, async, and code-room tournament games alike.
- **Spectators see both teams' cards in 2v2** (bug 243). Spectator seats
  never extended the card-bar array past vanilla's two, so team 2's cards
  threw index errors and both visible bars carried team 1 — every spectator
  saw one team's cards. Spectator seats now get the same four-bar layout as
  fighters.
- **Spectators see Refresh block resets** (bug 241). The spectator poison
  path rendered only lifesteal; the block-cooldown reset from "block back
  when you deal damage" now renders too, so a Poison+Refresh fighter's
  block no longer reads as permanently down on spectator seats.
- **Spectator crown error storm fixed** (bug 251). A rematch could leave the
  crown pointing at a severed body anchor on spectator seats, erroring every
  frame until the room died; the between-games flush now resets the crown
  and the update skips severed states.
- **"Leave All Queues" actually clears 2v2/1v2 beliefs** (bug 247). The
  escape hatch missed the 2v2/1v2 pending slots and the team queue state, so
  a DC'd player stayed "in a match" to the spectate gate with no way out.
- **Leaderboard profile stat lines reorganized** (bug 218, Stan's format):
  1v1 now matches the 2v2/FFA line shape with its board rank, 1v2 groups
  with the modes, and a blank line separates the block from the match
  summary.
- **Async tournament wording** (bugs 219/220): "Once you win a BO3 (first to
  2 games)..." — two players read "2 BO3 wins" as two series.
- **Chat source tags** (bug 248): now [Discord], [Game], [Twitch],
  [YouTube].
- **Compare tab** (bug 252): "Top Cards" renamed "Most Used Cards" in all
  languages.
- **Game audio mutes while tabbed out in online play** (bug 210, per Sid):
  deterministic instead of the OS's intermittent ducking; restores your
  exact volume on refocus. Menu/queue audio untouched (the match-found
  sound still reaches you), broadcast seat exempt. Config:
  `MuteAudioInBackground`, default on.
- **Black YouTube VOD thumbnails** (bug 255, VM bot): the thumbnail engine
  had no content check and uploaded provably uniform-black captures (5 of
  its first 6). Every capture is now probed with a tiny pixel decode and
  rejected below live-measured luminance thresholds; a rejected report
  retries while still on screen, and a session that ends with only black
  frames says so in the bot log. Pre-engine VODs keep YouTube's auto
  thumbnail (the stream goes live on a near-black card) unless backfilled.

Schema changes: migrations **229** (`stream_channel_posts` gains
`twitch_vod_url` / `youtube_vod_url`; retro-fixed 16 finalized posts —
applied 2026-08-18), **230** (`stream_channel_posts.matchups` session
matchup list; applied 2026-08-18), **233** (`ffa_match_players.game_points_at_leave`),
**234** (one-off: un-rates ten pre-fix early-leave rows).

Backend data: migration **231** — one-shot 20,000g `admin_grant` to
NotNic for a community promo video (applied 2026-08-19). Same shape as
`067`, plus ledger-keyed idempotency so a re-run is a no-op.

**Lobby and text-cell fixes (Aug 20)**

- **The lobby browser now shows the whole roster.** The "who is inside"
  line under each open lobby shared one fixed-height cell with the lobby
  header, and a cell can only carry one wrapping mode -- so a full lobby's
  roster clipped at the cell edge and the trailing "+N more" counter never
  appeared, in exactly the case that counter exists for. The roster is now
  its own element that sizes itself to its content and takes as many lines
  as it needs. Rows are usually SHORTER than before, not taller.
- **Four text cells no longer drop their text instead of clipping it.** The
  FFA and 2v2 leaderboard name cells, the FFA recent-games identity cell and
  the 2v2 series line all left word wrap on inside fixed-height boxes, so an
  over-long "name [title]" wrapped onto a line the box could not show and the
  wrapped part was discarded rather than clipped. Most visible on the
  translated "(left)" disconnect marker, which could vanish entirely.

**Admin (Aug 20)**

- **Lexia granted admin** (migration **232**).

**FFA early-leave grace (Aug 20)**

- **Leaving an FFA before the field has scored two points no longer costs
  Elo.** Below two half-points nothing has been decided, so the placement
  the report hands a leaver is not evidence about anyone — the same
  threshold the bet cutoff, the 2v2 disconnect rule and the client's own
  fresh-game cancel already use. The leaver is unrated for that game
  (no rating, no XP or gold, out of everyone else's beaten counts); the
  players who stayed play on and are rated among themselves.
- This does not reopen leave-to-dodge. The dodge that rule exists to stop is
  quitting a game you are losing, and by then the field is well past two
  points. The grace window is the opening seconds, before the first round
  converts. The claim is also reported by a *surviving* client, never by the
  leaver, and is refused outright if the leaver's signed tally shows they
  actually played.
- **Ten past games corrected.** Nine players who left with a completely
  empty stat line — no rounds, no points, no kills, no damage — had that
  game's rating change reversed. Eight gain (from +22.9 to +180.5); one
  loses a +69.8 that the same rule says they should not have banked. XP and
  gold already paid are untouched, and nobody who stayed in those games has
  their result changed.

**Map skin backgrounds fixed (bug 249, Aug 19)**

- Every custom map skin now renders its own designed background. They were
  all landing on the same pinkish red — most visible on the broadcast seat,
  which cycles all 23 skins, and easy to miss on a normal seat, which holds
  one skin for a whole session.
- The cause: the map background is the background camera's clear colour, and
  that clear is pure red. Vanilla ROUNDS arts turn it into a sky with a large
  hue shift; our skins replaced that with a colour *filter*, which multiplies
  — and multiplying pure red can never produce green or blue. Every skin
  collapsed onto one hue. Verified in-game: Abyss ("near-black blue") rendered
  hot magenta before the fix and deep blue after, on the same build.
- Also fixed in the same pass: the map arts share particle systems, so
  switching off the unused arts was switching off the live skin's own backdrop
  a couple of seconds into every round; the screen-filling backdrop layers were
  being painted with the skin's *wall* colours instead of its background; the
  per-skin post-process profile was sharing its effects with the base game's
  art asset, so repeated skin changes were quietly degrading it; and a backdrop
  pass that never matched a backdrop was recolouring Homing bullets and the
  card-choice face instead. Retired.
- The neutral skins read neutral again. Monochrome and Platinum were coming out
  warm beige because the base game grades everything the main camera draws with
  a red-weighted gain, and nothing was compensating for it. The correction is
  measured from the render rather than from the profile numbers, only touches
  colours the skin actually designed as grey, and scales with brightness — so
  Magma, Abyss, Mint and Soft measured unchanged.
- Five older defects in the same subsystem, fixed in the same pass: the
  automatic per-round art change could still recolour particles in the middle of
  the map slide (the stall that used to leave players off-screen); the "disable
  map lighting" backdrop was painted at an unsafe moment and then overwritten a
  couple of seconds later, so the setting never visually stuck; the premium
  skins' shimmer ticked faster than the transition guard and reached into the
  same window; switching from a custom skin back to a vanilla one left the art
  wearing the old colours; and unequipping your LAST map colour did nothing
  until you restarted the game.

**Broadcast stream stability (Aug 18)**

- Streams no longer cut in and out: the VM director holds outputs through
  transient status blips and sitting hops (the teardown/restart cycle was
  exhausting the push legs' restart budget into up-to-10-minute dead-air
  windows), organic sitting ends are no longer misread as seat failures
  (fighter-departure evidence), and the broadcast seat no longer self-
  updates out from under its supervisor.
- YouTube title updates fixed (the API rejects two listing filters at once)
  — the channel side was already healthy.
- Spectator view: fighter info panels moved to the top corners under the
  card bars; the camera now zooms out to keep every live fighter in frame
  (vertical and horizontal), instead of losing airborne players above the
  fixed vanilla framing.
- The stream-ended Discord post keeps its links and now points at the VODs
  — the exact Twitch/YouTube VOD of that session when resolvable while
  live, the channel archive pages otherwise.
- Ops: a maintenance pause flag idles the broadcast bot's supervisors for
  up to 8 hours so builds and tests on the VM aren't fought by it.

## v1.39.0 Ã¢â‚¬â€ 2026-08-18

Schema changes: migrations **225** (`spectate_drain_tombstones` table +
spectator cap default 5; applied 2026-08-16), **226** (`stream_channel_posts`
living-stream-post table), **227** (`record_exclusions` Ã¢â‚¬â€ admin record
removal).

**Records (round 2, Aug 18)**

- **Rarest Hand** Ã¢â‚¬â€ the rare-picks record board's proper name (it measures
  the rarest hand *picked*).
- **New: Luckiest** Ã¢â‚¬â€ the rarest hand *drawn*: the share of Rare cards among
  everything a game offered a player, picked or not (counted over recorded
  hands with a full candidate set). Deliberately allows the same player to
  hold several placements Ã¢â‚¬â€ luck shouldn't favor anyone, so a name filling
  this board up is worth a second look.
- **Records now has two pages** (button top-right of the panel); new boards
  land on page 2.
- **Admins can remove records** Ã¢â‚¬â€ a small control on each row (click twice
  to confirm) excludes a cheated row from the boards without touching the
  match itself; every removal is audit-logged.
- **Record hovers carry the game** Ã¢â‚¬â€ score (half-point convention), duration,
  the holder's full name and title, and the cards one per line.
- **Home tab "Get Link Code" button no longer clips its label.**

**Corrections + polish (round 3, Aug 18)**

- Recent Tournaments popup is split into **Sync and Async sections** again.
- Bracket hover scores use the **half-point convention** (the "(x-y pts)"
  form is gone for good).
- **Text floor:** everything this batch touched renders at 14pt bold or
  bigger Ã¢â‚¬â€ records rows, bracket cells and elos, hover tooltips.
- Offer telemetry hardened: offers are recorded only for the reporting
  player's own seat, with size caps, and excluded matches stop voting in
  the card-rarity election.
- **Records boards only admit rows the holder's own client reported** Ã¢â‚¬â€ a
  modified opponent can no longer plant a fake record (stats, cards, or
  draws) under an innocent player's name. Rarity votes follow the same
  rule, and forged-length games can't own the Longest Game board.
- **Every new string is translated** (es/ru/uk/sv Ã¢â‚¬â€ 65 keys x 4 languages).

**Broadcast seat (VM-only, invisible to players)**

- The game pins itself to windowed 1920x1080 (the capture geometry OBS
  expects) and drops to 15fps after 16 minutes idle Ã¢â‚¬â€ both only on the
  broadcast identity.
- Nightly clean cycle at 05:00 (skipped while a stream is live).

**Fixed**

- **Lost identity / "PlayerName" (bug 234).** The base game sets every
  player's nickname to a literal "PlayerName" placeholder before connecting
  and repairs it from Steam only once, as the last step of joining a room Ã¢â‚¬â€
  if that single attempt fails (a transient Steam hiccup), the placeholder
  sticks for the whole game and the in-world name label never refreshes. The
  mod now retries the Steam lookup with a bounded in-room budget and
  repaints name labels whenever a player's nickname heals, in every online
  room type.
- **2v2 game details ignored team colors.** Expanding a Recent 2v2 Series
  entry showed the per-game card columns and telemetry lines in fixed
  blue/orange side colors even when the series header showed the stamped
  team-identity colors Ã¢â‚¬â€ the inner view could contradict the header (and
  read "blue" for both teams). The expanded columns now use the same
  resolved team colors as the header.
- **Tournament signup names could corrupt the whole list.** The shared
  object-array parser was not string-aware, so one display name containing a
  brace could silently corrupt every row parsed after it (#156 class).

**Tournaments**

- **Recent Tournaments is now a popup** (button under Tournament Bets):
  every participant with their locked elo, seed, bracket win-loss, final
  result, plus the tournament's duration (hours for sync, weeks for async)
  and prize snapshot. The old one-line right-column list is retired.
- **Cleaner bracket.** The long winners-to-losers drop-down connector lines
  are gone Ã¢â‚¬â€ the two brackets now only visibly meet at the grand final.
  Player elos render beside names in the bracket cells, and titles beside
  names in the signups list.
- **Hover a bracket name for the full story**: per-game scores, points,
  duration, hit/block percentages, fps/ping, and every card that player
  picked, straight from the recorded games.

**Records (Leaderboard > Compare)**

- Records are now derived from the actual record-setting GAME: each row
  carries the date, the holder's title and rating, and (on hover) the cards
  it was set with. Names are no longer truncated to 13 characters.
- Four new boards: **Highest Avg DPS** (growth builds excluded), **Luckiest**
  (highest rare-pick share in one game), **Longest Game** and **Shortest
  Game** (both participants + both builds shown).

**Broadcast**

- **Living stream post in #scr-ranked-streaming**: when the broadcast seat
  goes live, one rich Discord post appears with the current match (names,
  ratings, mode, series score) and the Twitch/YouTube links, edits itself on
  match switches and score changes, and flips to "stream ended" when the
  broadcast stops.

**Server**

- Reserved broadcast spectator seat: spectator capacity moves to 5 with the
  fifth seat reserved for the broadcast account; public capacity and listing
  semantics unchanged at 4.
- New `/broadcast/target` director endpoint (broadcast account only) that
  ranks live spectatable games and rotates between near-tied ones.
- Service-account policy: the broadcast account is structurally excluded
  from queues, matches, tournaments, betting, shop, chat, and presence
  counts, with a detection audit.
- Spectator seat lifecycle: durable drain records for seats whose physical
  departure is unconfirmed (enforcement deferred to a future client
  release).

## v1.38.7 Ã¢â‚¬â€ 2026-08-15

Schema changes: migrations **221** (`pcolor_poison` body color; applied),
**222** (`ranked_queue.home_region`; applied), **223** (76 machine-translation
seeds for the new shop/vocab keys; applied).

**Added**

- **New body color: Poison.** The exact green the Poison card flashes on its
  victims Ã¢â‚¬â€ taken from the game's own card data rather than matched by eye Ã¢â‚¬â€
  for anyone building a poison-themed look. None of the existing greens was
  close: Forest shares the hue but renders at half the brightness, Emerald
  leans jade, Neon Lime leans yellow. 3000g, under Body Colors in the shop.

- **Tournament matches announce themselves everywhere.** The in-game HUD now
  shows a gold TOURNAMENT banner (with your exact bracket position, e.g.
  "Async Tournament - Winners R2") above the RANKED line; the Discord series
  results, the live-bets board, the gambler ping, bet confirmations and the
  settled-bets posts all carry a trophy tag naming the bracket match.
- **Post-match tournament DMs (the missing notifications).** After every
  bracket match the bot now DMs both players: winners are told who they
  face next (with the async deadline when one applies) or which match
  they're waiting on; a first loss leads with "You're not out!" and names
  your next opponent Ã¢â‚¬â€ or the match that decides them; elimination
  congratulates the run, with your placement when the bracket records one;
  champions get their own DM. A separate DM lands the moment your next
  match actually goes live, and it's delivered reliably Ã¢â‚¬â€ retried until it
  reaches you. Forfeit advances are phrased honestly instead of "you won".
- **Tournament matches are always spectatable.** The spectator opt-out is
  bypassed for the two players of a live bracket match Ã¢â‚¬â€ tournament games
  are public by rule. Every other spectate safety rule still applies.

**Fixed**

- **Tournament bets popup is clickable again (bug 230).** The popup's own
  buttons were being swallowed by its click shield, and a coordinate bug made
  any click read as "outside the popup" and dismiss it.
- **Better diagnostics for post-match disconnects (bugs 227/228).** The
  connection-restart tracers now run in every room type, so the next
  code-room disconnect names its exact trigger in the log. The investigation
  found the mechanism Ã¢â‚¬â€ the base game restarts a player's connection 10
  seconds after they answer the rematch prompt if their opponent hasn't
  answered yet Ã¢â‚¬â€ but a safe fix needs both clients acting together, and
  every one-sided approach made things worse in review; it's deferred to a
  dedicated pass rather than shipped half-safe.

- **Poison hits register reliably (bug 225).** A bullet's poison component
  could miss registration on the victim's client due to a game init-ordering
  race Ã¢â‚¬â€ the hit then knocked you back but the poison (all of a poison
  bullet's real damage) never started on any screen. The missing component is
  now re-registered at hit time, with a safety net against double-application.
- **Faces show in 1v2 and 2v2 rooms (bug 224).** The last player to join a
  team room missed everyone else's face for the whole sitting (a base-game
  quirk FFA already worked around); the fix now covers team rooms too.
- **Discord language channels stop reposting ancient messages (bug 226).**
  The relay now tracks exactly what it has delivered Ã¢â‚¬â€ durably, across
  restarts Ã¢â‚¬â€ instead of relying on a memory that old test messages could
  fall out of. The stale test messages themselves are cleaned up too.
- **Live-bets boards stop fighting Discord's rate limit.** The three boards
  edited into one channel every 10 seconds and were permanently throttled;
  they now stagger and skip edits when nothing changed, while still
  recovering if a board message is deleted.
- **Round-end poison watchdog accuracy.** Streams orphaned by a round
  boundary after they started no longer produce false "possible modified
  client" log entries; genuine mid-fight silence still gets flagged.
- **Phoenix no longer floods the log** with ~2,000 harmless warnings per game
  while charging its revive.
- **Community cosmetic translations actually show** (reported by Kyltist, our
  Russian translator). Approved translations for community-made cosmetic
  names and descriptions now render in the shop, on Home, and in the preview
  Ã¢â‚¬â€ an early design decision had the game deliberately skip them while the
  translation portal kept accepting the work, so approved entries (24 in
  Russian alone) existed but never displayed.
- **Nametag size previews show again.** The Bigger / XL / Huge / Float rows
  rendered nothing after "Preview:" in every language Ã¢â‚¬â€ the preview's own
  size tag was taller than the row and got clipped whole. Those rows now
  grow to show the name at its true size, which is the point of the preview.
- **Rarity and item-kind words translate.** "(rare)", "(common)", "(face)",
  "(nametag)" and friends were never translatable at all. In Russian,
  Spanish, Ukrainian and Swedish the rarity reads as a labeled phrase
  ("Ã‘â‚¬ÃÂµÃÂ´ÃÂºÃÂ¾Ã‘ÂÃ‘â€šÃ‘Å’: Ã‘ÂÃÂ¿ÃÂ¸Ã‘â€¡ÃÂµÃ‘ÂÃÂºÃÂ°Ã‘Â") so the grammar works next to any item type.
- **Fairer ranked-queue regions.** The room region used to be whichever
  player's momentary connection region happened to win the coin toss Ã¢â‚¬â€ which
  is how two same-region players could both end up on a 200-ping US server.
  Now, when both players' Photon home region (its own ping cache) agrees,
  that region is used, and any region signal beats the old "us" default.
  Also fixed a pre-existing race where the two clients could be told
  different regions for the same match and end up in separate rooms.

**Changed**

- **Card popup images no longer need downloading.** Card art in stats popups,
  the hold-Tab board and the tier-list export now renders natively from the
  game itself (correct in every language, always up to date) Ã¢â‚¬â€ the old image
  pack download (which had been failing quietly) is gone, and the mod's
  Thunderstore package shrinks by ~15 MB. The tier-list export shows a
  progress note the first time while it renders each card.

## v1.38.5 Ã¢â‚¬â€ 2026-08-13

**New**

- **Your end-of-game build is now recorded and shown in match history.** Hover a
  game's card names and you get the full card list *and* the build those cards
  produced Ã¢â‚¬â€ damage, attack speed, reload, ammo, blocks, move speed, HP and the
  rest. Works in 1v1, 2v2, 1v2 and FFA. Older games have no build recorded and
  simply show their cards as before.
- **The rating box now covers every mode.** My Stats and the leaderboard detail
  show your 2v2 and FFA rating, RD, peak and board position alongside 1v1, with
  your rank role shown next to your 1v1 peak in its own colour. 1v2 has no elo,
  so it shows its win/loss record with the other records instead of pretending.
- **2v2 and FFA podium titles.** Top three on either board get a placement title
  of their own, and both boards now paint the top three gold/silver/bronze the
  way the 1v1 board always has.
- **Chat controls.** Press **M** in game to cycle chat between normal, pinned
  (stays on screen) and muted Ã¢â‚¬â€ and when you mute, other players can see that in
  the chat panel, so nobody wastes a message on you. Settings gains a "chat fade
  after" knob from 0 (never show chat during play) up to 90 seconds.
- **FFA card toasts show the whole round.** Every player's pick, and every card
  that rolled off the 5-card cap, laid out in a single strip across the bottom
  instead of one name at a time over the play area.
- **Animated cosmetics can be uploaded as GIFs.** Artists can submit a GIF
  directly (2-16 frames, 0.5-15 fps) instead of exporting numbered PNGs.

**Fixed**

- **FFA opening cards going missing (bug 214).** In a 6-player game four players
  lost their first card. A spectator seat had been leaking a counter into the
  pick protocol; the room then split into two numbering schemes and every pick
  made under the "wrong" one was silently discarded. Both the cause and the
  amplifier are fixed, and a drift now names exactly who lost a card in the log.
- **Betting staying open long after a match was decided (bug 212).** The lock for
  private-room series was set to a threshold the metric could never reach, so it
  had never once fired since it shipped. Bets now close at 2 points as intended,
  and the same rule is enforced in game and in Discord.
- **God Build (and every other achievement) in room-code and quickplay games
  (bug 209).** Achievements were only evaluated in rooms the mod itself created,
  which is a minority of real play Ã¢â‚¬â€ a genuinely earned achievement in a private
  or public lobby simply never fired.
- **Server-side achievements now tell you when you earn them (bug 201).** Silent
  Drill, Clutch, Lumberjack, the sweeps, the slayers and the rank thresholds are
  granted by the server, and the client had no path to announce any of them.
- **Muffled audio while spectating (bug 210).** A failed sound event was never
  retired, so its voices leaked until the pool ran dry and started stealing
  voices from healthy sounds Ã¢â‚¬â€ quiet layers first, which is what made it sound
  muffled rather than silent.
- **Discord FFA results show half points (bug 215)**, matching the in-game score.
- **Rage Quit %** now measures what it was always meant to: how often your
  quickplay opponents quit on *you*, not how often you quit.
- **Spectating**: the connect screen explains itself instead of looking like a
  blank cover, cards are cleared between games so nobody appears to start with
  extra ones, and titles render bracketed in their real colours.
- **Async tournaments work the way they were designed.** No room code, no region,
  no ready-up Ã¢â‚¬â€ you and your opponent play a private lobby whenever suits you
  before the deadline and it counts automatically. The lock DM no longer tells
  async players to be online at a start time. Sync tournaments are unchanged and
  now pick a Photon region per match that suits both players, instead of one
  region for the whole bracket.
- **Layout**: the FFA start-button countdown no longer clips (in any language),
  the 1v2/2v2/FFA tabs share one scale, the chat input no longer covers the
  messages above it, and tournament bets live behind a button instead of filling
  the tab.

**Security**

- Uploaded cosmetic images are now fully validated and re-encoded server-side, so
  nothing can ride along inside an image file.

## v1.38.6 Ã¢â‚¬â€ 2026-08-14

**Fixed**

- **The mid-fight hitch in busy games (bug 217).** When a bullet's hit
  notification arrived for something this client had already cleaned up, the
  error it threw took the rest of that network packet batch down with it Ã¢â‚¬â€
  every other player's position update queued behind it arrived late. That is
  the "bullets and player positions lag while ping looks fine" feel. The error
  is now contained (17 hits in the two reported FFA games; the previous
  night's session had 87), and a companion guard quiets the bullet-pool
  teardown error that rode the same stacks.
- **Spectator join is far cleaner (bug 216).** Replayed leftovers from the
  room's past can no longer collide with anything during the join (they are
  made physics-inert the moment they appear), and the thousands of harmless
  "no such PhotonView" warnings a spectator seat used to burn CPU and log
  space on are silenced and counted instead.
- **Poison now shows on the spectator seat.** A stale local dead/respawning
  flag on one replica could eat every accepted poison verdict for that player
  Ã¢â‚¬â€ their health bar never moved for the whole observation. The observer no
  longer vetoes the victim's own authority using local lifecycle bits.
- **FFA scoreboard log lines carry names again** instead of nametag markup,
  and the stale-projectile sweep's diagnostic no longer goes quiet after the
  first game.
- **"I poisoned him and nothing happened" at round ends (bug 221).** A poison
  hit landing in the round-transition window starts a stream no client will
  ever honor (the revive already cancelled it Ã¢â‚¬â€ vanilla behaviour), but the
  watchdog treated that silence as a possible cheat and logged accusations
  against innocent players. Boundary-window streams are now recognized for
  what they are; genuine mid-fight silence still gets flagged.
- **Map skins did their full recolor work twice at every round transition.**
  Two code paths each scheduled the same deferred tint pass, so every client
  with a map skin walked all renderers and particles twice back-to-back at
  exactly the moment rounds change Ã¢â‚¬â€ measured in two players' logs at 2x per
  transition. Now it runs once.

**New**

- **Network health line in the log.** Every 10 seconds in an online room the
  log records ping, effective fps, actor count and dispatch-guard counters Ã¢â‚¬â€
  so the next "it felt laggy" report can be diagnosed from the bundle instead
  of guessed at.

## v1.38.4 (2026-08-11) Ã¢â‚¬â€ Translator titles and portal progress

Schema: migration **214**.

- **Three new achievement titles for translators** Ã¢â‚¬â€ **Rosetta** (10 strings),
  **Dragoman** (100) and **Babel** (1000), paying 100g / 300g / 1000g. A
  string counts once it is APPROVED, and both people behind it earn it: the
  translator who proposed it and the moderator who reviewed it. Doing both
  yourself on the same string still counts once, and moderators still cannot
  approve their own work. Existing contributors were back-granted.
- **Progress bars in the translation portal**, one per language. The green
  fill is approved and live; the lighter bar behind it is everything with a
  draft awaiting review; the dark remainder is what has no usable
  translation at all Ã¢â‚¬â€ so rejecting a bad machine draft correctly pushes the
  bar back and shows the work that is genuinely left. Ukrainian and Swedish
  count the base-game strings too, since the game does not ship those
  languages; Spanish and Russian do not, because it does.
- The Compare tab's achievement grid now sizes its columns to the space
  available Ã¢â‚¬â€ at 50 achievements the old fixed two columns ran off the
  bottom of the panel on common resolutions.
- Granting an achievement from the admin panel now also grants its title.
  This was missed for Sid Slayer and Stan Slayer too, and re-granting repairs
  an old one.

## v1.38.3 (2026-08-11) Ã¢â‚¬â€ Ukrainian + Swedish

Two new full mod languages, plus first-of-its-kind base-game localization.

- **Ukrainian (ÃÂ£ÃÂºÃ‘â‚¬ÃÂ°Ã‘â€”ÃÂ½Ã‘ÂÃ‘Å’ÃÂºÃÂ°) and Swedish (Svenska)** join English, Spanish and
  Russian as complete mod languages: every UI string (1,708 keys per
  language), machine-drafted, independently reviewed, seeded into the
  translation portal for community moderation, and selectable from the
  first-launch prompt or Settings.
- **The base game itself speaks Ukrainian and Swedish now.** ROUNDS ships 9
  official languages Ã¢â‚¬â€ Ukrainian and Swedish are not among them (the vanilla
  files even contain an unused "Svenska" label, so this one is overdue). With
  the mod language set to uk/sv, all 242 vanilla strings Ã¢â‚¬â€ menus, prompts,
  card names and descriptions Ã¢â‚¬â€ render translated via a runtime-injected
  locale. Fully reversible, zero effect on any other language setting, and
  card text in the mod's own panels follows automatically.
- **Release notes in four languages**: every release's notes are now
  published in es/ru/uk/sv (machine-translated, labeled as such), and the
  current three releases were back-filled.
- Translation portal upgrades that came out of the review rounds: base-game
  strings are moderatable with their table/entry context shown (including
  Landfall's own translator notes), stale proposals against reworded English
  are refused at approval, and the shop-string snapshot now has a proper
  refresh tool.
- **Ukrainian and Swedish chat channels** join the in-game chat split: pick
  them in the chat view/typing pickers, and messages bridge to the matching
  Discord rooms (English/Spanish/Russian unchanged).
- Spanish/Russian catch-up: 13 recently-added strings (lobby betting, new
  shop cosmetics) translated, plus consistency fixes from the review pass.

Known limits, accepted for this release: a language chat channel that has
been quiet for a while can look empty when you switch to it (the in-game log
keeps one shared 60-message buffer; the server still has the history), and
changing ROUNDS' own language from the vanilla Options screen during the
few seconds the mod is setting up uk/sv will not stick.

## v1.38.2 (2026-08-11)

Mini-release: the Aug 11 playtest minor-bug batch (spectator polish + portal
fix). Also raises the server's minimum mod version to 1.38.1, which restores
2v2/FFA bettability for everyone.

- **Stuck pick cards are gone for spectators** (bug 197). A fast join could
  collapse the cleanup window to zero, leaving the room's cache-replayed card
  table standing for the whole sitting Ã¢â‚¬â€ the burial now runs synchronously
  the moment the join replay provably ends. Live leftovers (cards whose local
  destruction never got scheduled) are swept a few seconds after each round
  boundary, and the card-picker avatar is hidden at the boundary instead of
  lingering over the next battle.
- **Poison and Decay now move health bars on spectator seats.** The
  spectator's round lifecycle runs slightly behind the fighters', and the
  damage engine silently ate every DOT verdict that arrived in that gap Ã¢â‚¬â€
  then the late revive erased the rest of the stream. Spectator seats now
  render DOT verdicts directly (display only, clamped above zero Ã¢â‚¬â€ a
  spectator can never broadcast a death; kills only show via the fighters'
  own death event), and live streams survive the spectator's late revive.
- Dark team-color stamps (Charcoal, Obsidian, Midnight) get a readability
  lift wherever they paint **text** Ã¢â‚¬â€ 2v2 recent-series names, FFA history
  score counters Ã¢â‚¬â€ while dots and graphs keep the true color.
- **Team-identity colors reach the last hardcoded surfaces**: the spectator
  score bar, the hold-Tab match-stats header (fighters had this bug too Ã¢â‚¬â€ a
  Midnight team read as "blue"), and the 2v2 live-bets rows in the F5 menu
  (which now also name a stamped side "Team Midnight" instead of "Team 1").
- **The 15-FPS deep idle no longer engages mid-spectate** Ã¢â‚¬â€ the spectator
  seat was invisible to both of its "never during online play" gates.
- **A sound-engine guard** stops one broken voice from aborting every other
  sound's update each frame (555 errors in one spectator session's log).
- **Translation portal**: the review queue now shows proposer display names
  instead of raw Steam IDs (machine drafts still read "by claude-mt").

## v1.38.1 (2026-08-10)

New community cosmetic: **Twisted Topper** (detail slot) joins the shop
catalog this release.

### Spectator mode Ã¢â‚¬â€ the desync is fixed (bugs 187/188/190/192/194)

- **The spectator's game clock is fixed.** It was never armed on the spectate
  join path, and every round-ending kill ratcheted it further down with
  nothing restoring it Ã¢â‚¬â€ bullets, gun timers, character limb IK, the floating
  nametag follower and gravity all run on that clock, which is why everything
  visibly trailed the (real-time) position stream: slow-motion bullets,
  instant hits, lagging names, floating bodies.
- **Removed a vanilla trap** where the spectator client silently dropped into
  TEST-MAP mode on its first map load Ã¢â‚¬â€ which teleport-revived dead fighters
  at random spawn points on the spectator's screen 2.5 seconds after every
  death, and contaminated map bookkeeping for the whole session.
- **Fixed the ghost-object registry.** The join-time cleanup hid the room's
  inherited object history but left its Photon view registrations alive, so
  from game 2 of a sitting every new object collided with a ghost view ID and
  live boxes/bullets stopped updating for spectators (the doubled/desynced
  string-box reports). Ghosts are now buried AND locally unregistered at
  source Ã¢â‚¬â€ which also removes the join-time error wall (700+ exceptions in
  one burst) that correlated with the "lag spike when you joined" reports.
- **Map loads are serialized on spectators** (vanilla corrupts its own
  scene-wrapper handoff when two additive loads overlap Ã¢â‚¬â€ routine for a
  chronically-behind spectator), with boundary reconciles that supersede
  cleanly instead of stacking, and deck rebuilds that tolerate mid-apply
  leavers.
- **Spectating no longer touches fighter gameplay.** A spectator joining or
  leaving used to arm a 3-second poison "roster quarantine" that disabled
  block-honoring on live poison streams Ã¢â‚¬â€ spectator churn was changing
  fighter damage. The poison census now runs on replicated data identically
  on every seat. Ejecting an unauthorized watcher can also no longer end the
  fighters' match through the vanilla disconnect cascade.
- **Kicks are honest now.** Stock Photon ships CloseConnection DISABLED on
  both ends Ã¢â‚¬â€ every spectator "kick" to date was a silent no-op. Kicks now
  work cooperatively between mod clients (revoked leases, wrong protocols,
  unauthorized entrants), fighters remain un-kickable by design, and the
  server-side lease system stays the real enforcement.
- **Spectate protocol floor -> 2** (migration 210): old-protocol clients carry
  the hazards above, so mixed rooms are excluded. Between the backend deploy
  and the client release, spectate grants are refused on purpose.

### Spectator mode Ã¢â‚¬â€ quality of life (Sid's list + bugs 184/191/193)

- **No more black flashes between points.** The fullscreen "Synchronizing"
  cover now exists only before the first sync; after that the live arena
  stays visible, and vanilla's own between-points score sequence (the
  orange/blue orbs with HALF/ROUND pips) plays for spectators exactly as
  fighters see it. Round starts are no longer hidden behind a reconcile.
- **The top bar shows the full picture**: team-colored names with the game
  score including half points ("Archnith 2.5 - 3 NotNic"), the current
  series score, and the SESSION series tally between the two fighters (how
  many series each has won this sitting Ã¢â‚¬â€ carried in the snapshot protocol).
- **Spectators can see who else is spectating** (the same bottom-right roster
  fighters already had Ã¢â‚¬â€ it was explicitly gated off for spectators).
- **Escape is deconflicted** (bug 191): an open chat box or F5 menu consumes
  Esc first; the leave-spectating dialog only opens from the base state.
- **The F5 menu no longer force-closes** when a round starts while
  spectating (bug 193), and the whole log-driven match tracker is quiescent
  on spectator clients (watched picks can no longer leak into a later
  fighter session's telemetry).
- The FFA phantom "card picking ends in Xs" banner fix (bug 184) ships in
  this release.

### Fighter-side (spectator-adjacent)

- Removed every identified spectator-conditional cost on fighter clients: a
  master-side bookkeeping loop ran at 100x its intended cadence, spectate
  attest state leaked across rooms, a master handoff could starve spectator
  validation for a minute, and misc handlers misread spectator joins as
  "opponent joined". Fighters' own fps/ping telemetry was flat through the
  playtest; if lag persists at 1-2 spectators after this batch, the
  remaining suspect is Photon relay fan-out.

### Changed

- **Spectators can bet.** The old rule blocked anyone holding a spectator
  seat from placing bets (plus a 5-minute cooldown after leaving). Removed:
  the bet-close windows are the information gate Ã¢â‚¬â€ bets lock once a game is
  decided (or the FFA time window closes), so watching live can't out-inform
  a locked bet. Spectators watch from the beginning of a series until
  disconnect and bet under the same windows as everyone else.

### Fixed

- **2v2 betting now actually closes at 1-0 on the server.** The live-bets
  panel has always shown 1-0 series as locked, but the endpoint itself only
  refused bets at 2 wins Ã¢â‚¬â€ a crafted request could bet on the leader after
  game 1. The server now enforces the same first-decided-game close as 1v1.

- **GROW's damage no longer depends on frame rate in competitive play.** The
  card's growth compounded per rendered frame, making its total multiplier
  exponential in frame TIME: a 60 FPS shooter dealt ~1.4Ãƒâ€” the Grow damage of a
  400 FPS shooter before stacking, several times more with stacked copies, and
  a single 200 ms hitch frame multiplied damage Ãƒâ€”2.16 by itself Ã¢â‚¬â€ the "low-FPS
  Grow nukes" reports. In queue-matched ranked 1v1, 2v2, 1v2, FFA and
  sync-tournament rooms Ã¢â‚¬â€ and in private/quickplay rooms where BOTH players
  had Ranked enabled when they connected Ã¢â‚¬â€ growth is now normalized to
  a fixed 240-FPS-equivalent rate Ã¢â‚¬â€ near-identical growth per unit of distance
  flown for every player (the small remaining frame-granularity differences
  always err toward LESS growth, never more). Private/quickplay rooms with a
  ranked-off player, rooms with an unmodded player, and the sandbox keep
  vanilla behavior (mode rooms Ã¢â‚¬â€ queue, tournament, hosted lobbies Ã¢â‚¬â€ apply it
  regardless of the 1v1 Ranked toggle, since entering the mode is the mode's
  consent); the fix only activates when EVERY player in the room runs a
  version that has it (mixed rooms stay vanilla on all seats).
- **Drill bullets fired point-blank into a wall/box no longer vanish for the
  other players.** A same-frame race on the receiving client could drop the
  drill effect from the bullet's hit processing, so the remote copy died at
  the wall while the shooter's bullet drilled through and kept hitting Ã¢â‚¬â€
  an invisible bullet. The hit is now deferred one frame and the drill
  re-registered (bug #186's second half; extends the v1.37 drill-position
  fix).
- **FFA: Phoenix no longer respawns players "into thin air"** (bug #185). The
  vanilla respawn coroutine looks the player up by list POSITION, which broke
  after any leaver in an FFA lobby Ã¢â‚¬â€ the crash left the player alive-flagged,
  invisible and unhittable on every client (opponents had to suicide to
  advance the round). The lookup is now by player ID, and a Phoenix whose
  charge crosses a round transition defers to the round's own mass revive
  instead of firing into the next round.
- **Spectators no longer see phantom "card picking ends in Xs" banners** when
  nobody is picking (bug #184), and a closed pick window no longer lingers at
  0s for non-pickers.
- **The top status strip no longer cuts off** ("2 onli", "(2 in q") Ã¢â‚¬â€ the
  queue/online text now takes the full remaining row width (bug from the Aug 8
  screenshots).
- **Jump/land dust puffs now match an equipped body color** instead of staying
  vanilla orange/blue, and the **end-of-game VICTORY / REMATCH? text** follows
  the custom team color too (in FFA it uses the winner's color).
- **Block stat graph uses one y-axis** (bug #182, Stan): the activated and
  successful lines share a scale like the shots graph; only legacy
  damage-vs-blocks rows keep dual axes.

## v1.38.0 Ã¢â‚¬â€ 2026-08-08 Ã¢â‚¬â€ Hosted lobbies, alerts, chat moderation, animated cosmetics

Schema: migrations **202Ã¢â‚¬â€œ206** (202 LFP modes, 203 admin alerts, 204 cosmetic
animation frames, 205 lobby kicks, 206 team/FFA colour identity Ã¢â‚¬â€ all must
apply BEFORE the API deploy). Deploy notes: the
GIF-split endpoint needs **Pillow added to the server-side API Dockerfile**
(fetch the live copy per #192, add `pip install Pillow`, push back Ã¢â‚¬â€ until
then it answers 503 and the multi-PNG path is unaffected); ship step 11 now
also POSTs the ENGLISH release notes (`en` accepted; the Home tab's primary
source is the new uncut `/release-notes/full/{locale}` Ã¢â‚¬â€ post v1.37.0's
English body retroactively at deploy so the current notes uncut too); an es/ru
seed migration for the new i18n keys is a ship-time step.

### Added

- **Hosted lobbies are THE way to play custom 2v2s and 1v2s** (Sid's follow-up:
  the old blind manual queue and the 1v2 consent queue are gone from the
  tabs). v1.37.0 shipped only the server half Ã¢â‚¬â€ no client UI existed. Now:
  FFA Create Private + password prompts + [PRIVATE] browser markers; full
  hosted-lobby panels on the 2v2 and 1v2 tabs (create, browse/join with
  password, member list, host-only Start, Leave) whose state poll keeps the
  seat lease alive even with the menu closed. **Hosts can kick** members
  before start (admins are unkickable, and a kicked player cannot rejoin that
  lobby); the 1v2 solo-extra-pick is the **host's setting** now; and every
  lobby browser shows **who is inside before you join Ã¢â‚¬â€ names, titles and
  elo**, with 2v2/FFA elos shown only once established (10+ rated
  series/games; 1v1 elo otherwise). Start hands off to the normal
  ready-up/room flow with a match-found alert for idle members; a closed
  lobby never strands or conscripts anyone. *Multi-player flows are
  first-playtest.*
- **Standing server alerts.** Admins broadcast a notice (outage / issue /
  update / info) from the Admin tab; every player gets a one-time toast (also
  for players coming online later) and a persistent banner on every menu tab
  showing category, message, admin and time. Echoed to the admin Discord
  channel. Revocable; optional expiry.
- **Automatic chat moderation.** A hard-slur filter on both chat paths removes
  the message before it exists anywhere, auto-mutes the sender in all channels
  for 15 minutes (doubling per repeat offense in 90 days, 7-day cap), logs a
  system action, posts who/what/action to the admin channel, and tells the
  sender why their line vanished.
- **Animated cosmetic uploads in-game.** Multi-PNG sets (name.png +
  name__f2.png + ... Ã¢â‚¬â€ the picker explains the convention and validates every
  frame) with an artist-set frame-rate slider in the live preview, or a GIF
  the server splits at the GIF's own speed. Admin review shows the animation
  actually moving before approval.
- **Max card draw unlocked (FFA).** Hosts set 1-5 cards offered per draw in
  the lobby settings row; non-default values show in the load-in banner and
  history.
- **Watch from the mode tabs.** WATCH buttons on the 2v2 live strip, a new
  Live 1v2 Games panel, and live FFA lobbies Ã¢â‚¬â€ same eligibility rules as the
  Leaderboard panel, which keeps its buttons. *FFA/1v2 spectating is
  first-playtest; a server-side per-mode switch can pull a mode back without a
  client update.*
- **RLFP ping upgrades.** Pick any of 1v1 / 2v2 / FFA under the duration
  selector Ã¢â‚¬â€ the Discord ping reads "LFP: ranked 1v1+FFA for 30min" Ã¢â‚¬â€ and
  `:emojiname:` in the optional message renders as real server emojis.
- **Deep idle.** After 60s unfocused outside any room/battle/match-found, the
  engine drops to 15 FPS (on top of the existing 120 cap), waking instantly on
  focus or a match. Toggleable in Settings.
- **Shop: New chip + on-body preview.** A New filter beside All shows the
  newest cosmetics; face thumbnails grew 80Ã¢â€ â€™112; every face row has a Preview
  button showing the item on the player body at its real shipped placement Ã¢â‚¬â€
  animated items animate.
- **Body-color team identity (server half).** A 2v2 team is named after its
  color holder's equipped body color Ã¢â‚¬â€ sole holder wins, two holders coin-flip
  Ã¢â‚¬â€ decided once at series creation, frozen for the series (rematches inherit
  the sitting's identity, sides swapped when the split flips; mirror matches
  leave team 2 vanilla). FFA games stamp each player's color at report time.
  The stamp rides the series state/live/recent feeds and `/ffa/recent`, ready
  for the client tinting pass (points, card shading, Recent panels).
  Migration 206; actual body colors are never changed.

### Changed

- **Release notes are uncut and formatted on both surfaces.** Discord posts the
  full notes as multiple messages instead of cutting at 2000 chars
  mid-sentence; the Home tab renders the complete notes with gold headings,
  colored bullets, bold/underline/code Ã¢â‚¬â€ and stops wrapping at the author's
  column width (the actual bug-160 regression).
- **Admin tab restructure.** Banned users moved to a dedicated admin-only
  Banned sub-tab (full height + search); the Action Log now lives in-panel
  where the bans sat, with the searchable full log one click away. Banning 5+
  players inside 5 minutes blocks further bans and flags the admin channel;
  ban failures now surface instead of silently logging.
- **Compare tab.** The < > metric cycling arrows are back beside the dropdown
  (both stay in sync); Ranked Friends pie slices are guaranteed distinct
  colors with an honest legend (tail folds into a grey Other); labels like
  Bullet Speed size to the cell instead of a hard 10-char cut.
- **Chat is visible on every menu tab** (except Home, where the pane lives),
  anchored bottom-left as everywhere else.
- **Body-color identity polish.** The point/win animation's balls and fills
  tint to each team's equipped color; card-bar boxes fill with the player's
  color (outline back to vanilla) and the box letters are always a readable
  deep version of that same color (pale version on near-black colors) Ã¢â‚¬â€ the
  first cut only darkened past a threshold and missed the HUD bar's labels
  entirely, which is why light colors read as blank white squares.
- The FFA host Start button says "Start unlocks in Ns (settings changed)"
  instead of a countdown that read as an auto-start.

### Fixed

- **FFA: Radiance no longer damages its own caster.** The FFA targeting
  replacement excluded the shooter by position, so a moving player became
  their own sun wave's nearest target Ã¢â‚¬â€ one self-hit per wave, which also
  suppressed lifesteal (the "Parasite not healing" half of the report).
- **"Leftover parasite stacks" at round start.** End-of-round projectiles
  could register hits after the victim respawned; every client now despawns
  its own bullets the moment the round is decided.
- The 2v2 live-series and team-history parsers survive display names
  containing brackets (they blanked the Live panel, 2v2 tab and spectator
  HUD line).
- The unfocused-FPS cap can no longer stick if the mod disables itself during
  an unfocused launch.
- The FFA "GET READY" banner no longer clips its text top and bottom Ã¢â‚¬â€ the
  banner box now sizes to the rendered text instead of a fixed 260px slot.

### Stan's feature requests (#178Ã¢â‚¬â€œ181, all accepted)

- **Discord FFA results show every player's beforeÃ¢â€ â€™after rating** (stamped at
  match time, so later games never rewrite history), and **every ranked
  result post carries its `/game` codes** Ã¢â‚¬â€ inspect a game from Discord
  without opening ROUNDS.
- **"How stats are tracked"** Ã¢â‚¬â€ a Settings-tab page stating the verified
  mechanics: what counts as a shot, why one block absorbing three bullets is
  one success, which cards do and don't count as attempts, what Rage Quit %
  vs Leave actually measure, when the game-length clock runs, and which
  modes feed which lifetime stats.
- **Stat hover graphs redesigned**: two-line headers with the legend colored
  as the lines (distinct hues), real x-axis time ticks scaled to the game's
  actual length, the block graph now charts **activations vs successful
  blocks** (older games keep their honest damage-taken labels), and the
  marker footer is replaced by a real green/red "point won / point lost"
  legend that only appears when markers do.
- **The graph-vs-summary discrepancy Stan caught was real and is fixed at the
  root**: every stat timeline stopped recording at 6 minutes 24 seconds (a
  128-sample cap) while the totals kept counting Ã¢â‚¬â€ nearly every 2v2 and FFA
  game overran it. Timelines now compress as they grow and always span the
  whole game. Also found in the same audit: FFA spawn-grace right-clicks
  were counting as block attempts that could never block Ã¢â‚¬â€ no longer.

### Review hardening (Codex adversarial rounds 3Ã¢â‚¬â€œ8 Ã¢â‚¬â€ 40 further findings fixed)

- **Authenticated requests refuse plaintext transport.** If the secure
  connection ever fails and the client falls back to the legacy endpoint,
  your Steam session is no longer exchanged or attached, and admin actions
  and lobby passwords are refused outright rather than sent in the clear.
  (LAN/loopback addresses are exempt so local setups keep working.)
- **Nothing can drop you into a match you didn't consent to.** Joining the
  public 2v2 queue can no longer overwrite a live locked match; a seat in a
  closed hosted lobby is released instead of being recycled into public
  matchmaking; leave requests are bound to the exact match they were issued
  for, so a delayed retry can't dissolve a newer one.
- **Preference clicks land in order** Ã¢â‚¬â€ the last thing you clicked is what
  the server stores, and Start waits for it.
- Assorted: DPS graphs no longer halve short games; the card-letter outline
  can't leak materials; live-column and bets-ledger rows share one height
  budget; release announcements resume correctly after a crash, restart, or
  partial post.

### Review hardening (Codex adversarial round 2 Ã¢â‚¬â€ 12 confirmed findings fixed)

- Hosted-lobby groups are released (never recycled into public matchmaking)
  by EVERY dissolution path now Ã¢â‚¬â€ ready timeouts, dead-lock resets, ban
  evictions, account deletion Ã¢â‚¬â€ via one shared disposition authority; queue
  leaves are incarnation-fenced so a delayed retry can't tear down a newer
  enrollment, and joining is blocked while a leave is still settling.
- The chat auth token is never sent over the plaintext fallback socket Ã¢â‚¬â€ a
  downgraded session stays unverified (censored without strikes) instead of
  exposing the session bearer.
- Preference writes serialize one-at-a-time with Start disabled until the
  host's last change is acknowledged; recovery rejoins re-send the current
  preferences, not a stale join-time snapshot; "Team: Any" clears server-side.
- The team-color coin flip distributes to every seat and spectator via a
  room property (the continuation response only ever reached one client);
  an all-vanilla decision is now explicitly frozen so a mid-series color
  equip can't re-open it; spectators never repaint a watched room with their
  own previous series' colors.
- The Leaderboard live column enforces a single row budget across all modes
  so it can never overpaint the bet ledger; release announcements survive
  bot restarts mid-post and the manual command can no longer mark a partial
  announcement complete.

### Review hardening (Codex adversarial round 1 Ã¢â‚¬â€ 16 confirmed findings fixed)

- **Hosted lobbies:** survivors of a dissolved hosted 2v2/1v2 start are
  released outright instead of being recycled into public matchmaking; the
  client's start-vs-disband recovery uses a new read-only resolve endpoint
  (the old probe could lock you with strangers); an explicit Leave that races
  Start now reports "started" and completes through the proper queue-leave;
  seated preferences are patched one field at a time through a dedicated
  endpoint (racing Start via re-join could orphan a seat), hydrate from the
  server, and "Team: Any" actually clears a previous claim; a full kick list
  refuses new kicks rather than quietly re-admitting the earliest-kicked
  player.
- **Chat moderation:** the censor's auto-mute only fires on a socket whose
  Steam identity is session-verified Ã¢â‚¬â€ an unauthenticated socket could
  previously mute an arbitrary victim by forging their ID. Unverified hits
  are still censored, just not persisted as strikes.
- **Admin/ops:** the ban-velocity gate is race-proof (advisory lock Ã¢â‚¬â€ parallel
  bans could previously slip past it); admin alert banners expire client-side
  when timed alerts lapse; the release announcer resumes from the failed
  chunk instead of marking a partial announcement complete; the Home tab's
  release feed anchors on ship-time order so editing an old translation can't
  hoist it above newer releases.
- **Animated cosmetics:** abandoned half-uploads free their submission slot
  even at the cap; admin frame review pages one frame per request (a 16-frame
  submission could exceed the fetch timeout and become unreviewable); GIFs
  outside the supported 0.5Ã¢â‚¬â€œ15 fps band are rejected with the measured rate
  instead of silently retimed; the release-candidates feed and ship runbook
  carry frame counts + fps so an approved animation can never ship as a
  static frame 1.
- **Spectating:** pulling a mode from the server's watchable set now also
  evicts existing viewers (heartbeat + fighter validation), not just new
  grants.

## v1.36.0 Ã¢â‚¬â€ 2026-08-04 Ã¢â‚¬â€ Spanish + Russian, translation portal, native cards

Schema: migrations **179Ã¢â‚¬â€œ189**. 187 adds the FFA kills-tiebreak capability columns, 188
repairs one seeded translation proposal, and **189** carries this batch's 188 new
machine-translation proposals Ã¢â‚¬â€ a NEW file rather than more rows in the already-applied
184, because a deploy that tracks applied migrations would never have run them.

Deploy order is not optional: the backend must go out BEFORE the client is released. The
client always signs the newer FFA match canonical (which carries kill counts), and only a
dual-accepting server verifies it Ã¢â‚¬â€ an updated client against the old server would have
every FFA report rejected. The reverse pairing is safe: the new server still accepts the
old canonical, so v1.35.5 clients keep working throughout.

**Minimum version stays at 1.35.4 at release** and is raised to 1.36.0 about two hours
later, so players have a window to update through Thunderstore or the auto-updater first.

### Added

- **The mod speaks Spanish and Russian.** Every one of the mod's ~1,470 user-visible strings is translated, and
  the language is chosen from Settings Ã¢â€ â€™ Language / Idioma / ÃÂ¯ÃÂ·Ã‘â€¹ÃÂº. Machine-translated
  drafts to start; community moderators review and rewrite them from a web portal.
- **Translation portal** at `/translate`: sign in from the game, propose translations, and
  review others'. Formatting tags are locked so a translation can't break the layout, and
  every string has a History view showing the original English, what's live now, who
  proposed and approved it, and whether the English has changed since.
- **Translated release notes.** Update notes now appear in your language on the Home tab,
  labelled as machine translations, falling back to English when a release hasn't been
  translated.
- **Ranked FFA settings are bounded**: max cards held is 3Ã¢â‚¬â€œ5 for ranked lobbies, and the
  opening draw can never exceed the card cap (dealing more cards than you can hold just
  wasted picks and time).
- **FFA match history shows the settings each game used** Ã¢â‚¬â€ but only where those settings
  were genuinely chosen; older games show nothing rather than a default they never used.
- **Spawn spotlight in FFA**: the screen dims around you for a moment at the start of a
  round so you can find yourself among up to ten identical bodies.
- **Chat channels** for Spanish and Russian alongside global, both in game and in Discord.
- **Admins can appoint and remove translators from the Admin tab** (there was previously
  no in-game way to do it at all).
- **Kills now break FFA placement ties.** Placements are rounds, then points, then kills;
  only a full three-way tie still shares a place. Kill counts are now part of the signed
  match report, which is what makes them safe to rank on Ã¢â‚¬â€ reports from older clients keep
  the old two-field ordering.
- **Cards render natively.** Hovering a card now shows the game's own card Ã¢â‚¬â€ drawn live,
  in your language Ã¢â‚¬â€ instead of a bundled English screenshot. The old images remain as an
  automatic fallback, and a future release can drop the ~15 MB card image pack entirely.
- **Shop items are translated** Ã¢â‚¬â€ every cosmetic name and description, with community
  artists' own item names left as the artist wrote them.
- **Chat channels are visible and pickable.** The Home-tab chat shows which channel you're
  in, a selector switches between All/Global/EspaÃƒÂ±ol/ÃÂ Ã‘Æ’Ã‘ÂÃ‘ÂÃÂºÃÂ¸ÃÂ¹, and you type into your
  language's channel by default. Your choice sticks between sessions.
- **Recent Casual FFAs** Ã¢â‚¬â€ casual FFA games get their own history section under the ranked
  one.
- **Date order is configurable**: Month/Day/Year (default), Day/Month/Year, or
  Year/Month/Day, applied to every date in the mod from a new Settings picker.
- **Release notes on the Home tab now appear in Spanish and Russian**, starting with
  v1.35.5's notes.

### Fixed (August 3 feedback round 2)

- **The translation portal expired after about a minute and could not be recovered.** The
  session was always 45 minutes; the page simply forgot its sign-in on any reload. It now
  keeps the session across reloads, renews itself while the tab is open (up to 8 hours,
  after which you re-open it from the game), and renews immediately on load so a session
  restored near its expiry is saved rather than lost.
- **The portal's search box and its All / Untranslated / Stale / Has-pending filters did
  nothing**, and the queue reported "200" for both languages regardless of the real
  backlog. Search now matches across the English source, the current translation and the
  key, each filter shows its true count, and the queue is properly paged.
- **An approved translation appeared to vanish.** Approving a proposal removed it from the
  pending queue and nothing replaced it, so the work looked lost Ã¢â‚¬â€ it was live the whole
  time. There is now an Approved view listing every live translation with its original
  English, who proposed it and who approved it, plus an admin-only reset.
- **Switching the Home chat's channel scrolled an empty view to the bottom** and stranded
  whatever you had typed at the top of the pane.
- **Card Stats showed the bundled screenshot instead of the live card about half the time,
  and "Remote" never rendered live at all.** Not random: our stored card name corrects the
  game's own spelling mistakes (Leach Ã¢â€ â€™ Leech, Riccochet Ã¢â€ â€™ Ricochet, "Poison bullets" Ã¢â€ â€™
  Poison), so for exactly those cards the lookup matched nothing in the game and fell back
  forever. Every lookup now also accepts the game's own raw spellings.
- **The live card render was too dark to read** over the in-match overlay; it is now
  composited onto a solid backing so it reads the same everywhere.
- **Changing language needed a restart, and could leave three languages on screen at
  once.** The switch is now staged: translations swap, the font re-arms for the new
  script, the game's own language follows (previously only written to disk and applied at
  next launch, which is why card names stayed in the old language), card text and card
  images are re-rendered, and only then does the page rebuild.
- **The Tournament / 1v2 / 2v2 / FFA info popups and the per-player hover graphs were
  still English**, along with the Compare tab and several of its charts.
- **Compare-tab charts had no labels at all** Ã¢â‚¬â€ including the region-time pie charts. The
  label element was one pixel shorter than its own text needed, and the truncation rule
  drops a line that does not fit rather than clipping it.
- **Per-game gold disappeared from the Casual and Ranked history rows** (series winnings
  still showed): the cell was 65px and the text no longer fit.
- **The FFA spawn spotlight was a large square**; it is now a soft circle about three times
  the player's size.
- **The Home tab's update block wrapped at a third of its width in English** while Spanish
  and Russian used the full width.
- **Chat is now one merged, time-ordered view by default.** "Global" is renamed "English",
  All shows every channel in send order, you type into your own language's channel by
  default, Shift changes which channel you are typing into, and the two selectors are
  separate so reading everything does not force you to pick where you speak.
- **Card names were inconsistently capitalised throughout the menu** (`CAREFUL PLANNING`
  next to `Fast Forward`, and `Target BOUNCE`). The game's own table is inconsistent, so
  names are normalised at display time only Ã¢â‚¬â€ nothing stored or looked up changes.
- **The Card Stats tier letters were hard to read.** They were already bold twice over;
  the game's font ships no bold face, so the letters are now larger instead.
- **A crafted chat message could pin itself to the bottom of everyone's chat.** The
  message parser matched field names anywhere in the payload, so text typed inside a
  message could pose as the message's own timestamp.
- **Off-screen bullets could be despawned on their first frame**, before the engine had
  finished setting up their pooled effects Ã¢â‚¬â€ which corrupts the pool for the rest of the
  session. They now get a moment first. (Under investigation as a possible cause of a
  report that every shot rendered the poison effect.)
- **The English update log wrapped at a third of the panel** while Spanish and Russian
  filled it. Not a layout bug: release notes are published with their own line breaks at
  about 78 characters, so the English text carried its own wrapping wherever it was shown.
  Those breaks are now removed before display Ã¢â‚¬â€ lists, headings and paragraph breaks are
  kept Ã¢â‚¬â€ and the panel does the wrapping in every language.
- **Admins can appoint and remove translation moderators from the Admin tab again.** The
  in-game controls were missing entirely; the server side had been working the whole time.

- **A double KO in FFA no longer passes without explanation.** When the last players alive
  kill each other in the same instant there is no survivor to award the point to, so the
  round ended with nobody scoring and the next map simply loaded Ã¢â‚¬â€ correct, but completely
  silent, and indistinguishable from a scoring bug. It now says so on screen. The rule is
  unchanged (no point, round advances), and every client shows the same result: the host
  decides the outcome once and broadcasts it, so there is no disagreement between players.

### Added (August 3 feedback round 2)

- **Thicker menu text**, on by default. This is the game's own font rendered at a heavier
  weight Ã¢â‚¬â€ not a different typeface Ã¢â‚¬â€ and it applies only to the mod's own menus. The
  Settings row turns it off for the original thickness.

### Fixed (August 3 feedback round)

- **Achievement names vanished in Russian.** Translated names come from a fallback font
  with taller lines than the row cells; the truncation rule deleted the whole line. Only
  names kept in English survived.
- **Sorting the leaderboard flipped its headers back to English** Ã¢â‚¬â€ the sort rewrite
  path skipped translation. Same class of miss fixed across every sortable header.
- **The per-player FFA graphs (Hit/Block/FPS/ping) never opened on hover** Ã¢â‚¬â€ the drawing
  code only ran on other tabs.
- **"(65 tot" and "(click t"** Ã¢â‚¬â€ the FFA history header and the Discord link line were
  too narrow for their text; both widened, and the Discord line now reads
  "Linked to Discord (Click to show)".
- Several Russian labels were clipped (tournament timezone/format buttons, the 1v2 join
  button); widened.
- Hundreds of remaining English surfaces now translate: the leaderboard detail panel,
  Card Stats (including localized card names), My Stats history rows, tournament
  signup/voting block, the bug-report form, settings rows including every performance
  patch, FFA/1v2/2v2 history internals, and the hold-Tab match overlay.

### Fixed

- **Bracket resets in double-elimination tournaments could never be recorded.** The column
  storing the bracket side was four characters wide and the value needed eight, so the
  insert failed every time.
- **In-match queue leases had been failing since 2026-08-01**, which could free a player's
  queue slot early. A database parameter-typing bug; no data was lost.
- Blank Shop, 2v2, Tournaments and Admin tabs after changing language.
- Completed achievements showed `[X` with the closing bracket cut off.
- The Name Styling previews showed nothing after "Preview:".
- The admin bug-report list rendered blank whenever any report's text contained an
  unmatched `[`.
- Several messages stated things the code did not do: the bet box documented a number
  format it rejected; the tournament notice implied Ranked was only enabled temporarily
  when it stays on; the Artist Studio promised a 30% royalty on gifts, which are not paid;
  and every banned opponent was described as banned "for cheating" regardless of reason.
- 1v2 no longer advertises a ranked launch, and FFA no longer describes itself as new.

### Changed

- Language selection is a picker instead of a click-to-cycle, and it returns you to the
  same tab instead of the Home tab Ã¢â‚¬â€ you can no longer get stranded in a language you
  can't read.
- Translation moderators can no longer approve their own proposals; admins still can.
- Translation checks are stricter and fairer: broken placeholder braces are rejected
  everywhere (they used to be accepted by the portal and then silently ignored by the
  game), long texts like the FFA guide now fit through the review pipeline, and symbols
  the English original itself uses (bullets, check marks) are always allowed in a
  translation.
- **Far more of the interface is translatable now.** The first-launch data-consent screen,
  achievement names and descriptions, the "How It Works" guides for 2v2/1v2/FFA, tournament
  banners, the in-match score lines, queue status lines, and dozens of composed messages
  (bet results, level-ups, lobby status) previously rendered in English regardless of
  language; all of them now translate.

### Cosmetics

* **Spilled Icecream** Ã¢â‚¬â€ new community submission, now bundled and renderable. It is not
  on sale yet; the artist opens stock from the Artist tab.
* **Rounds Cat** Ã¢â‚¬â€ the artist's approved placement revision rescales it (1.0 Ã¢â€ â€™ 1.7). The
  art is unchanged; existing owners will see it render larger.

### Known issue Ã¢â‚¬â€ chat ordering on a machine with a wrong system clock

Chat is now ordered by the time a message was **sent** rather than the time it arrived,
which fixes the long-standing problem of scrollback and multi-channel messages appearing
out of order. There is one case it does not handle: if your computer's clock is
significantly wrong (minutes or more) **and** the chat history has not loaded yet, or
fails to load, your own messages can be placed in the wrong position in your own chat
pane. With a fast clock your messages sit below newer ones for as long as your clock is
ahead. With a slow clock your message is filed back into history, and it can scroll off
and disappear from your pane entirely.

Only your own view is affected Ã¢â‚¬â€ the message is still delivered normally to everyone
else, and nothing about matches, ratings, gold, or the queue is involved. Restarting
ROUNDS clears it. If you see this, check that Windows "Set time automatically" is on.


## v1.35.5 Ã¢â‚¬â€ 2026-07-31 Ã¢â‚¬â€ queue strand root cause, Leave All Queues, shield charge, display toggles

Backend deployed to production on 2026-07-31. Schema: migrations **173** (free
stranded FFA seats) and **174** (`queue_leases`). The **Leave All Queues** button
now reaches players with this client build.

### Added

- **"Leave all queues" button, in Settings.** Removes you from every queue and lobby
  in every mode at once. Use it if the game thinks you're still in a match you've
  already left, or if joining a queue keeps saying you're busy. It doesn't affect a
  game you're actually playing and never touches stats, gold or rating. It's in
  Settings rather than on the queue tabs on purpose Ã¢â‚¬â€ the player who needs it is the
  one whose queue tab is misbehaving. If the server can't be reached it keeps retrying
  in the background, including after a restart.

### Changed

- **Being "in a queue" now expires on its own.** Previously the server considered you
  busy because a row existed, and you only became free again if one of about fifteen
  different cleanup routines remembered to remove it Ã¢â‚¬â€ several of which needed your
  game to still be running and cooperating. If none of them fired, you stayed blocked
  with no time limit, which is why this kept needing manual intervention. Your slot is
  now a lease with an expiry that a live game continuously renews; when the games stop,
  it lapses by itself. Nothing has to remember to clean up, so there is nothing left to
  forget. Getting it wrong now frees you slightly early Ã¢â‚¬â€ you just requeue Ã¢â‚¬â€ instead of
  locking you out indefinitely. This also fixed 2v2 specifically, where a stuck slot
  previously had no time limit at all.


> **Minimum version raised to 1.35.4.** Older clients are asked to update before
> they can play. The mod updates itself on launch; Thunderstore users update
> through their mod manager.

### Cosmetics

Five new community face items ship with this release Ã¢â‚¬â€ **Brain Cane**, **Casi's
mouth**, **Casicorn's Eyes**, **Little Pink Buddy** and **Sniper Medal**. Schema:
migration **175**. Each artist opens their own sales from the Artist tab, so an
item may show as not-yet-on-sale until they do.

### Fixed (client)

- **Shield Charge Ã¢â‚¬â€ and other block-attached card effects Ã¢â‚¬â€ could do nothing for
  an entire game (#142/#144).** After a rematch, a leftover registration from the
  previous game made the card's setup fail one step before it hooked into the
  block system. Normal blocking kept working, so the card looked equipped and
  simply had no effect. The cleanup that was meant to prevent this ran one frame
  too early Ã¢â‚¬â€ before the game had actually finished destroying the old cards Ã¢â‚¬â€
  so it inspected them while they were still alive and cleaned up nothing.
- **The chromatic aberration toggle did nothing (#141).** It was switching the
  setting on a rendering layer that isn't the one being displayed. If you had it
  off, you were still seeing the aberration Ã¢â‚¬â€ including the screen-wide pulse on
  every hit, which reads as camera shake. Screen shake itself was never the
  problem; that toggle was working correctly all along.

### Changed (client)

- **Screen shake is now Full / Reduced / Off** instead of on/off, matching the
  glow setting. Reduced keeps the hit feedback at about a third strength. If you
  already had shake turned off, that carries over automatically.

### Known issue

- **Blocking still does not cancel poison ticks (#143).** The rebuild that
  restores it is written but deliberately not switched on: the mechanism that
  tells everyone in a room to use it doesn't yet guarantee they all switch at
  the same moment, and a room that's half-switched would show players different
  health values Ã¢â‚¬â€ worse than the current behaviour, which is at least consistent
  for everyone. Blocking the initial poison shot still avoids poison entirely.

### Fixed (server)

- **"Perma stuck in the FFA queue", and locked out of every other queue with it
  (#124/#139).** Leaving a locked FFA lobby has never once worked: the endpoint marks the
  departure by concatenating the player's id onto the lobby's `departed_ids` array, and with
  a plain bind parameter PostgreSQL types that parameter as an *array* rather than a single
  id. The driver rejected it, the whole transaction rolled back, and the statement that
  actually removes the player from the queue Ã¢â‚¬â€ the last line of the endpoint Ã¢â‚¬â€ never ran.
  Every leave returned an error; 34 of 34 leave requests in one production log window
  failed, with none succeeding. Because the leftover row reads as "this player is mid-match",
  it also blocked them from joining 1v1, 2v2 and 1v2, and the game client's retry loop kept
  the row looking permanently fresh so no automatic cleanup could ever reach it Ã¢â‚¬â€ hence the
  repeating "the server will clear you shortly" message that never came true. Broken since
  FFA shipped in v1.35.0; migrations 165 and 171 had been hand-clearing individual lobbies
  without the cause being known. Schema/data: migration **173** frees any player still
  stranded (2 freed on apply, plus 1 who escaped the moment the fix went live).


_(older entries trimmed - full history on GitHub)_
