## v1.38.5 — 2026-08-13

**New**

- **Your end-of-game build is now recorded and shown in match history.** Hover a
  game's card names and you get the full card list *and* the build those cards
  produced — damage, attack speed, reload, ammo, blocks, move speed, HP and the
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
  (stays on screen) and muted — and when you mute, other players can see that in
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
  which is a minority of real play — a genuinely earned achievement in a private
  or public lobby simply never fired.
- **Server-side achievements now tell you when you earn them (bug 201).** Silent
  Drill, Clutch, Lumberjack, the sweeps, the slayers and the rank thresholds are
  granted by the server, and the client had no path to announce any of them.
- **Muffled audio while spectating (bug 210).** A failed sound event was never
  retired, so its voices leaked until the pool ran dry and started stealing
  voices from healthy sounds — quiet layers first, which is what made it sound
  muffled rather than silent.
- **Discord FFA results show half points (bug 215)**, matching the in-game score.
- **Rage Quit %** now measures what it was always meant to: how often your
  quickplay opponents quit on *you*, not how often you quit.
- **Spectating**: the connect screen explains itself instead of looking like a
  blank cover, cards are cleared between games so nobody appears to start with
  extra ones, and titles render bracketed in their real colours.
- **Async tournaments work the way they were designed.** No room code, no region,
  no ready-up — you and your opponent play a private lobby whenever suits you
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

## v1.38.4 (2026-08-11) — Translator titles and portal progress

Schema: migration **214**.

- **Three new achievement titles for translators** — **Rosetta** (10 strings),
  **Dragoman** (100) and **Babel** (1000), paying 100g / 300g / 1000g. A
  string counts once it is APPROVED, and both people behind it earn it: the
  translator who proposed it and the moderator who reviewed it. Doing both
  yourself on the same string still counts once, and moderators still cannot
  approve their own work. Existing contributors were back-granted.
- **Progress bars in the translation portal**, one per language. The green
  fill is approved and live; the lighter bar behind it is everything with a
  draft awaiting review; the dark remainder is what has no usable
  translation at all — so rejecting a bad machine draft correctly pushes the
  bar back and shows the work that is genuinely left. Ukrainian and Swedish
  count the base-game strings too, since the game does not ship those
  languages; Spanish and Russian do not, because it does.
- The Compare tab's achievement grid now sizes its columns to the space
  available — at 50 achievements the old fixed two columns ran off the
  bottom of the panel on common resolutions.
- Granting an achievement from the admin panel now also grants its title.
  This was missed for Sid Slayer and Stan Slayer too, and re-granting repairs
  an old one.

## v1.38.3 (2026-08-11) — Ukrainian + Swedish

Two new full mod languages, plus first-of-its-kind base-game localization.

- **Ukrainian (Українська) and Swedish (Svenska)** join English, Spanish and
  Russian as complete mod languages: every UI string (1,708 keys per
  language), machine-drafted, independently reviewed, seeded into the
  translation portal for community moderation, and selectable from the
  first-launch prompt or Settings.
- **The base game itself speaks Ukrainian and Swedish now.** ROUNDS ships 9
  official languages — Ukrainian and Swedish are not among them (the vanilla
  files even contain an unused "Svenska" label, so this one is overdue). With
  the mod language set to uk/sv, all 242 vanilla strings — menus, prompts,
  card names and descriptions — render translated via a runtime-injected
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
  table standing for the whole sitting — the burial now runs synchronously
  the moment the join replay provably ends. Live leftovers (cards whose local
  destruction never got scheduled) are swept a few seconds after each round
  boundary, and the card-picker avatar is hidden at the boundary instead of
  lingering over the next battle.
- **Poison and Decay now move health bars on spectator seats.** The
  spectator's round lifecycle runs slightly behind the fighters', and the
  damage engine silently ate every DOT verdict that arrived in that gap —
  then the late revive erased the rest of the stream. Spectator seats now
  render DOT verdicts directly (display only, clamped above zero — a
  spectator can never broadcast a death; kills only show via the fighters'
  own death event), and live streams survive the spectator's late revive.
- Dark team-color stamps (Charcoal, Obsidian, Midnight) get a readability
  lift wherever they paint **text** — 2v2 recent-series names, FFA history
  score counters — while dots and graphs keep the true color.
- **Team-identity colors reach the last hardcoded surfaces**: the spectator
  score bar, the hold-Tab match-stats header (fighters had this bug too — a
  Midnight team read as "blue"), and the 2v2 live-bets rows in the F5 menu
  (which now also name a stamped side "Team Midnight" instead of "Team 1").
- **The 15-FPS deep idle no longer engages mid-spectate** — the spectator
  seat was invisible to both of its "never during online play" gates.
- **A sound-engine guard** stops one broken voice from aborting every other
  sound's update each frame (555 errors in one spectator session's log).
- **Translation portal**: the review queue now shows proposer display names
  instead of raw Steam IDs (machine drafts still read "by claude-mt").

## v1.38.1 (2026-08-10)

New community cosmetic: **Twisted Topper** (detail slot) joins the shop
catalog this release.

### Spectator mode — the desync is fixed (bugs 187/188/190/192/194)

- **The spectator's game clock is fixed.** It was never armed on the spectate
  join path, and every round-ending kill ratcheted it further down with
  nothing restoring it — bullets, gun timers, character limb IK, the floating
  nametag follower and gravity all run on that clock, which is why everything
  visibly trailed the (real-time) position stream: slow-motion bullets,
  instant hits, lagging names, floating bodies.
- **Removed a vanilla trap** where the spectator client silently dropped into
  TEST-MAP mode on its first map load — which teleport-revived dead fighters
  at random spawn points on the spectator's screen 2.5 seconds after every
  death, and contaminated map bookkeeping for the whole session.
- **Fixed the ghost-object registry.** The join-time cleanup hid the room's
  inherited object history but left its Photon view registrations alive, so
  from game 2 of a sitting every new object collided with a ghost view ID and
  live boxes/bullets stopped updating for spectators (the doubled/desynced
  string-box reports). Ghosts are now buried AND locally unregistered at
  source — which also removes the join-time error wall (700+ exceptions in
  one burst) that correlated with the "lag spike when you joined" reports.
- **Map loads are serialized on spectators** (vanilla corrupts its own
  scene-wrapper handoff when two additive loads overlap — routine for a
  chronically-behind spectator), with boundary reconciles that supersede
  cleanly instead of stacking, and deck rebuilds that tolerate mid-apply
  leavers.
- **Spectating no longer touches fighter gameplay.** A spectator joining or
  leaving used to arm a 3-second poison "roster quarantine" that disabled
  block-honoring on live poison streams — spectator churn was changing
  fighter damage. The poison census now runs on replicated data identically
  on every seat. Ejecting an unauthorized watcher can also no longer end the
  fighters' match through the vanilla disconnect cascade.
- **Kicks are honest now.** Stock Photon ships CloseConnection DISABLED on
  both ends — every spectator "kick" to date was a silent no-op. Kicks now
  work cooperatively between mod clients (revoked leases, wrong protocols,
  unauthorized entrants), fighters remain un-kickable by design, and the
  server-side lease system stays the real enforcement.
- **Spectate protocol floor -> 2** (migration 210): old-protocol clients carry
  the hazards above, so mixed rooms are excluded. Between the backend deploy
  and the client release, spectate grants are refused on purpose.

### Spectator mode — quality of life (Sid's list + bugs 184/191/193)

- **No more black flashes between points.** The fullscreen "Synchronizing"
  cover now exists only before the first sync; after that the live arena
  stays visible, and vanilla's own between-points score sequence (the
  orange/blue orbs with HALF/ROUND pips) plays for spectators exactly as
  fighters see it. Round starts are no longer hidden behind a reconcile.
- **The top bar shows the full picture**: team-colored names with the game
  score including half points ("Archnith 2.5 - 3 NotNic"), the current
  series score, and the SESSION series tally between the two fighters (how
  many series each has won this sitting — carried in the snapshot protocol).
- **Spectators can see who else is spectating** (the same bottom-right roster
  fighters already had — it was explicitly gated off for spectators).
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
  the bet-close windows are the information gate — bets lock once a game is
  decided (or the FFA time window closes), so watching live can't out-inform
  a locked bet. Spectators watch from the beginning of a series until
  disconnect and bet under the same windows as everyone else.

### Fixed

- **2v2 betting now actually closes at 1-0 on the server.** The live-bets
  panel has always shown 1-0 series as locked, but the endpoint itself only
  refused bets at 2 wins — a crafted request could bet on the leader after
  game 1. The server now enforces the same first-decided-game close as 1v1.

- **GROW's damage no longer depends on frame rate in competitive play.** The
  card's growth compounded per rendered frame, making its total multiplier
  exponential in frame TIME: a 60 FPS shooter dealt ~1.4× the Grow damage of a
  400 FPS shooter before stacking, several times more with stacked copies, and
  a single 200 ms hitch frame multiplied damage ×2.16 by itself — the "low-FPS
  Grow nukes" reports. In queue-matched ranked 1v1, 2v2, 1v2, FFA and
  sync-tournament rooms — and in private/quickplay rooms where BOTH players
  had Ranked enabled when they connected — growth is now normalized to
  a fixed 240-FPS-equivalent rate — near-identical growth per unit of distance
  flown for every player (the small remaining frame-granularity differences
  always err toward LESS growth, never more). Private/quickplay rooms with a
  ranked-off player, rooms with an unmodded player, and the sandbox keep
  vanilla behavior (mode rooms — queue, tournament, hosted lobbies — apply it
  regardless of the 1v1 Ranked toggle, since entering the mode is the mode's
  consent); the fix only activates when EVERY player in the room runs a
  version that has it (mixed rooms stay vanilla on all seats).
- **Drill bullets fired point-blank into a wall/box no longer vanish for the
  other players.** A same-frame race on the receiving client could drop the
  drill effect from the bullet's hit processing, so the remote copy died at
  the wall while the shooter's bullet drilled through and kept hitting —
  an invisible bullet. The hit is now deferred one frame and the drill
  re-registered (bug #186's second half; extends the v1.37 drill-position
  fix).
- **FFA: Phoenix no longer respawns players "into thin air"** (bug #185). The
  vanilla respawn coroutine looks the player up by list POSITION, which broke
  after any leaver in an FFA lobby — the crash left the player alive-flagged,
  invisible and unhittable on every client (opponents had to suicide to
  advance the round). The lookup is now by player ID, and a Phoenix whose
  charge crosses a round transition defers to the round's own mass revive
  instead of firing into the next round.
- **Spectators no longer see phantom "card picking ends in Xs" banners** when
  nobody is picking (bug #184), and a closed pick window no longer lingers at
  0s for non-pickers.
- **The top status strip no longer cuts off** ("2 onli", "(2 in q") — the
  queue/online text now takes the full remaining row width (bug from the Aug 8
  screenshots).
- **Jump/land dust puffs now match an equipped body color** instead of staying
  vanilla orange/blue, and the **end-of-game VICTORY / REMATCH? text** follows
  the custom team color too (in FFA it uses the winner's color).
- **Block stat graph uses one y-axis** (bug #182, Stan): the activated and
  successful lines share a scale like the shots graph; only legacy
  damage-vs-blocks rows keep dual axes.

## v1.38.0 — 2026-08-08 — Hosted lobbies, alerts, chat moderation, animated cosmetics

Schema: migrations **202–206** (202 LFP modes, 203 admin alerts, 204 cosmetic
animation frames, 205 lobby kicks, 206 team/FFA colour identity — all must
apply BEFORE the API deploy). Deploy notes: the
GIF-split endpoint needs **Pillow added to the server-side API Dockerfile**
(fetch the live copy per #192, add `pip install Pillow`, push back — until
then it answers 503 and the multi-PNG path is unaffected); ship step 11 now
also POSTs the ENGLISH release notes (`en` accepted; the Home tab's primary
source is the new uncut `/release-notes/full/{locale}` — post v1.37.0's
English body retroactively at deploy so the current notes uncut too); an es/ru
seed migration for the new i18n keys is a ship-time step.

### Added

- **Hosted lobbies are THE way to play custom 2v2s and 1v2s** (Sid's follow-up:
  the old blind manual queue and the 1v2 consent queue are gone from the
  tabs). v1.37.0 shipped only the server half — no client UI existed. Now:
  FFA Create Private + password prompts + [PRIVATE] browser markers; full
  hosted-lobby panels on the 2v2 and 1v2 tabs (create, browse/join with
  password, member list, host-only Start, Leave) whose state poll keeps the
  seat lease alive even with the menu closed. **Hosts can kick** members
  before start (admins are unkickable, and a kicked player cannot rejoin that
  lobby); the 1v2 solo-extra-pick is the **host's setting** now; and every
  lobby browser shows **who is inside before you join — names, titles and
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
  name__f2.png + ... — the picker explains the convention and validates every
  frame) with an artist-set frame-rate slider in the live preview, or a GIF
  the server splits at the GIF's own speed. Admin review shows the animation
  actually moving before approval.
- **Max card draw unlocked (FFA).** Hosts set 1-5 cards offered per draw in
  the lobby settings row; non-default values show in the load-in banner and
  history.
- **Watch from the mode tabs.** WATCH buttons on the 2v2 live strip, a new
  Live 1v2 Games panel, and live FFA lobbies — same eligibility rules as the
  Leaderboard panel, which keeps its buttons. *FFA/1v2 spectating is
  first-playtest; a server-side per-mode switch can pull a mode back without a
  client update.*
- **RLFP ping upgrades.** Pick any of 1v1 / 2v2 / FFA under the duration
  selector — the Discord ping reads "LFP: ranked 1v1+FFA for 30min" — and
  `:emojiname:` in the optional message renders as real server emojis.
- **Deep idle.** After 60s unfocused outside any room/battle/match-found, the
  engine drops to 15 FPS (on top of the existing 120 cap), waking instantly on
  focus or a match. Toggleable in Settings.
- **Shop: New chip + on-body preview.** A New filter beside All shows the
  newest cosmetics; face thumbnails grew 80→112; every face row has a Preview
  button showing the item on the player body at its real shipped placement —
  animated items animate.
- **Body-color team identity (server half).** A 2v2 team is named after its
  color holder's equipped body color — sole holder wins, two holders coin-flip
  — decided once at series creation, frozen for the series (rematches inherit
  the sitting's identity, sides swapped when the split flips; mirror matches
  leave team 2 vanilla). FFA games stamp each player's color at report time.
  The stamp rides the series state/live/recent feeds and `/ffa/recent`, ready
  for the client tinting pass (points, card shading, Recent panels).
  Migration 206; actual body colors are never changed.

### Changed

- **Release notes are uncut and formatted on both surfaces.** Discord posts the
  full notes as multiple messages instead of cutting at 2000 chars
  mid-sentence; the Home tab renders the complete notes with gold headings,
  colored bullets, bold/underline/code — and stops wrapping at the author's
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
  deep version of that same color (pale version on near-black colors) — the
  first cut only darkened past a threshold and missed the HUD bar's labels
  entirely, which is why light colors read as blank white squares.
- The FFA host Start button says "Start unlocks in Ns (settings changed)"
  instead of a countdown that read as an auto-start.

### Fixed

- **FFA: Radiance no longer damages its own caster.** The FFA targeting
  replacement excluded the shooter by position, so a moving player became
  their own sun wave's nearest target — one self-hit per wave, which also
  suppressed lifesteal (the "Parasite not healing" half of the report).
- **"Leftover parasite stacks" at round start.** End-of-round projectiles
  could register hits after the victim respawned; every client now despawns
  its own bullets the moment the round is decided.
- The 2v2 live-series and team-history parsers survive display names
  containing brackets (they blanked the Live panel, 2v2 tab and spectator
  HUD line).
- The unfocused-FPS cap can no longer stick if the mod disables itself during
  an unfocused launch.
- The FFA "GET READY" banner no longer clips its text top and bottom — the
  banner box now sizes to the rendered text instead of a fixed 260px slot.

### Stan's feature requests (#178–181, all accepted)

- **Discord FFA results show every player's before→after rating** (stamped at
  match time, so later games never rewrite history), and **every ranked
  result post carries its `/game` codes** — inspect a game from Discord
  without opening ROUNDS.
- **"How stats are tracked"** — a Settings-tab page stating the verified
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
  128-sample cap) while the totals kept counting — nearly every 2v2 and FFA
  game overran it. Timelines now compress as they grow and always span the
  whole game. Also found in the same audit: FFA spawn-grace right-clicks
  were counting as block attempts that could never block — no longer.

### Review hardening (Codex adversarial rounds 3–8 — 40 further findings fixed)

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
- **Preference clicks land in order** — the last thing you clicked is what
  the server stores, and Start waits for it.
- Assorted: DPS graphs no longer halve short games; the card-letter outline
  can't leak materials; live-column and bets-ledger rows share one height
  budget; release announcements resume correctly after a crash, restart, or
  partial post.

### Review hardening (Codex adversarial round 2 — 12 confirmed findings fixed)

- Hosted-lobby groups are released (never recycled into public matchmaking)
  by EVERY dissolution path now — ready timeouts, dead-lock resets, ban
  evictions, account deletion — via one shared disposition authority; queue
  leaves are incarnation-fenced so a delayed retry can't tear down a newer
  enrollment, and joining is blocked while a leave is still settling.
- The chat auth token is never sent over the plaintext fallback socket — a
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

### Review hardening (Codex adversarial round 1 — 16 confirmed findings fixed)

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
  Steam identity is session-verified — an unauthenticated socket could
  previously mute an arbitrary victim by forging their ID. Unverified hits
  are still censored, just not persisted as strikes.
- **Admin/ops:** the ban-velocity gate is race-proof (advisory lock — parallel
  bans could previously slip past it); admin alert banners expire client-side
  when timed alerts lapse; the release announcer resumes from the failed
  chunk instead of marking a partial announcement complete; the Home tab's
  release feed anchors on ship-time order so editing an old translation can't
  hoist it above newer releases.
- **Animated cosmetics:** abandoned half-uploads free their submission slot
  even at the cap; admin frame review pages one frame per request (a 16-frame
  submission could exceed the fetch timeout and become unreviewable); GIFs
  outside the supported 0.5–15 fps band are rejected with the measured rate
  instead of silently retimed; the release-candidates feed and ship runbook
  carry frame counts + fps so an approved animation can never ship as a
  static frame 1.
- **Spectating:** pulling a mode from the server's watchable set now also
  evicts existing viewers (heartbeat + fighter validation), not just new
  grants.

## v1.36.0 — 2026-08-04 — Spanish + Russian, translation portal, native cards

Schema: migrations **179–189**. 187 adds the FFA kills-tiebreak capability columns, 188
repairs one seeded translation proposal, and **189** carries this batch's 188 new
machine-translation proposals — a NEW file rather than more rows in the already-applied
184, because a deploy that tracks applied migrations would never have run them.

Deploy order is not optional: the backend must go out BEFORE the client is released. The
client always signs the newer FFA match canonical (which carries kill counts), and only a
dual-accepting server verifies it — an updated client against the old server would have
every FFA report rejected. The reverse pairing is safe: the new server still accepts the
old canonical, so v1.35.5 clients keep working throughout.

**Minimum version stays at 1.35.4 at release** and is raised to 1.36.0 about two hours
later, so players have a window to update through Thunderstore or the auto-updater first.

### Added

- **The mod speaks Spanish and Russian.** Every one of the mod's ~1,470 user-visible strings is translated, and
  the language is chosen from Settings → Language / Idioma / Язык. Machine-translated
  drafts to start; community moderators review and rewrite them from a web portal.
- **Translation portal** at `/translate`: sign in from the game, propose translations, and
  review others'. Formatting tags are locked so a translation can't break the layout, and
  every string has a History view showing the original English, what's live now, who
  proposed and approved it, and whether the English has changed since.
- **Translated release notes.** Update notes now appear in your language on the Home tab,
  labelled as machine translations, falling back to English when a release hasn't been
  translated.
- **Ranked FFA settings are bounded**: max cards held is 3–5 for ranked lobbies, and the
  opening draw can never exceed the card cap (dealing more cards than you can hold just
  wasted picks and time).
- **FFA match history shows the settings each game used** — but only where those settings
  were genuinely chosen; older games show nothing rather than a default they never used.
- **Spawn spotlight in FFA**: the screen dims around you for a moment at the start of a
  round so you can find yourself among up to ten identical bodies.
- **Chat channels** for Spanish and Russian alongside global, both in game and in Discord.
- **Admins can appoint and remove translators from the Admin tab** (there was previously
  no in-game way to do it at all).
- **Kills now break FFA placement ties.** Placements are rounds, then points, then kills;
  only a full three-way tie still shares a place. Kill counts are now part of the signed
  match report, which is what makes them safe to rank on — reports from older clients keep
  the old two-field ordering.
- **Cards render natively.** Hovering a card now shows the game's own card — drawn live,
  in your language — instead of a bundled English screenshot. The old images remain as an
  automatic fallback, and a future release can drop the ~15 MB card image pack entirely.
- **Shop items are translated** — every cosmetic name and description, with community
  artists' own item names left as the artist wrote them.
- **Chat channels are visible and pickable.** The Home-tab chat shows which channel you're
  in, a selector switches between All/Global/Español/Русский, and you type into your
  language's channel by default. Your choice sticks between sessions.
- **Recent Casual FFAs** — casual FFA games get their own history section under the ranked
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
  pending queue and nothing replaced it, so the work looked lost — it was live the whole
  time. There is now an Approved view listing every live translation with its original
  English, who proposed it and who approved it, plus an admin-only reset.
- **Switching the Home chat's channel scrolled an empty view to the bottom** and stranded
  whatever you had typed at the top of the pane.
- **Card Stats showed the bundled screenshot instead of the live card about half the time,
  and "Remote" never rendered live at all.** Not random: our stored card name corrects the
  game's own spelling mistakes (Leach → Leech, Riccochet → Ricochet, "Poison bullets" →
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
- **Compare-tab charts had no labels at all** — including the region-time pie charts. The
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
  names are normalised at display time only — nothing stored or looked up changes.
- **The Card Stats tier letters were hard to read.** They were already bold twice over;
  the game's font ships no bold face, so the letters are now larger instead.
- **A crafted chat message could pin itself to the bottom of everyone's chat.** The
  message parser matched field names anywhere in the payload, so text typed inside a
  message could pose as the message's own timestamp.
- **Off-screen bullets could be despawned on their first frame**, before the engine had
  finished setting up their pooled effects — which corrupts the pool for the rest of the
  session. They now get a moment first. (Under investigation as a possible cause of a
  report that every shot rendered the poison effect.)
- **The English update log wrapped at a third of the panel** while Spanish and Russian
  filled it. Not a layout bug: release notes are published with their own line breaks at
  about 78 characters, so the English text carried its own wrapping wherever it was shown.
  Those breaks are now removed before display — lists, headings and paragraph breaks are
  kept — and the panel does the wrapping in every language.
- **Admins can appoint and remove translation moderators from the Admin tab again.** The
  in-game controls were missing entirely; the server side had been working the whole time.

- **A double KO in FFA no longer passes without explanation.** When the last players alive
  kill each other in the same instant there is no survivor to award the point to, so the
  round ended with nobody scoring and the next map simply loaded — correct, but completely
  silent, and indistinguishable from a scoring bug. It now says so on screen. The rule is
  unchanged (no point, round advances), and every client shows the same result: the host
  decides the outcome once and broadcasts it, so there is no disagreement between players.

### Added (August 3 feedback round 2)

- **Thicker menu text**, on by default. This is the game's own font rendered at a heavier
  weight — not a different typeface — and it applies only to the mod's own menus. The
  Settings row turns it off for the original thickness.

### Fixed (August 3 feedback round)

- **Achievement names vanished in Russian.** Translated names come from a fallback font
  with taller lines than the row cells; the truncation rule deleted the whole line. Only
  names kept in English survived.
- **Sorting the leaderboard flipped its headers back to English** — the sort rewrite
  path skipped translation. Same class of miss fixed across every sortable header.
- **The per-player FFA graphs (Hit/Block/FPS/ping) never opened on hover** — the drawing
  code only ran on other tabs.
- **"(65 tot" and "(click t"** — the FFA history header and the Discord link line were
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
  same tab instead of the Home tab — you can no longer get stranded in a language you
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

* **Spilled Icecream** — new community submission, now bundled and renderable. It is not
  on sale yet; the artist opens stock from the Artist tab.
* **Rounds Cat** — the artist's approved placement revision rescales it (1.0 → 1.7). The
  art is unchanged; existing owners will see it render larger.

### Known issue — chat ordering on a machine with a wrong system clock

Chat is now ordered by the time a message was **sent** rather than the time it arrived,
which fixes the long-standing problem of scrollback and multi-channel messages appearing
out of order. There is one case it does not handle: if your computer's clock is
significantly wrong (minutes or more) **and** the chat history has not loaded yet, or
fails to load, your own messages can be placed in the wrong position in your own chat
pane. With a fast clock your messages sit below newer ones for as long as your clock is
ahead. With a slow clock your message is filed back into history, and it can scroll off
and disappear from your pane entirely.

Only your own view is affected — the message is still delivered normally to everyone
else, and nothing about matches, ratings, gold, or the queue is involved. Restarting
ROUNDS clears it. If you see this, check that Windows "Set time automatically" is on.


## v1.35.5 — 2026-07-31 — queue strand root cause, Leave All Queues, shield charge, display toggles

Backend deployed to production on 2026-07-31. Schema: migrations **173** (free
stranded FFA seats) and **174** (`queue_leases`). The **Leave All Queues** button
now reaches players with this client build.

### Added

- **"Leave all queues" button, in Settings.** Removes you from every queue and lobby
  in every mode at once. Use it if the game thinks you're still in a match you've
  already left, or if joining a queue keeps saying you're busy. It doesn't affect a
  game you're actually playing and never touches stats, gold or rating. It's in
  Settings rather than on the queue tabs on purpose — the player who needs it is the
  one whose queue tab is misbehaving. If the server can't be reached it keeps retrying
  in the background, including after a restart.

### Changed

- **Being "in a queue" now expires on its own.** Previously the server considered you
  busy because a row existed, and you only became free again if one of about fifteen
  different cleanup routines remembered to remove it — several of which needed your
  game to still be running and cooperating. If none of them fired, you stayed blocked
  with no time limit, which is why this kept needing manual intervention. Your slot is
  now a lease with an expiry that a live game continuously renews; when the games stop,
  it lapses by itself. Nothing has to remember to clean up, so there is nothing left to
  forget. Getting it wrong now frees you slightly early — you just requeue — instead of
  locking you out indefinitely. This also fixed 2v2 specifically, where a stuck slot
  previously had no time limit at all.


> **Minimum version raised to 1.35.4.** Older clients are asked to update before
> they can play. The mod updates itself on launch; Thunderstore users update
> through their mod manager.

### Cosmetics

Five new community face items ship with this release — **Brain Cane**, **Casi's
mouth**, **Casicorn's Eyes**, **Little Pink Buddy** and **Sniper Medal**. Schema:
migration **175**. Each artist opens their own sales from the Artist tab, so an
item may show as not-yet-on-sale until they do.

### Fixed (client)

- **Shield Charge — and other block-attached card effects — could do nothing for
  an entire game (#142/#144).** After a rematch, a leftover registration from the
  previous game made the card's setup fail one step before it hooked into the
  block system. Normal blocking kept working, so the card looked equipped and
  simply had no effect. The cleanup that was meant to prevent this ran one frame
  too early — before the game had actually finished destroying the old cards —
  so it inspected them while they were still alive and cleaned up nothing.
- **The chromatic aberration toggle did nothing (#141).** It was switching the
  setting on a rendering layer that isn't the one being displayed. If you had it
  off, you were still seeing the aberration — including the screen-wide pulse on
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
  health values — worse than the current behaviour, which is at least consistent
  for everyone. Blocking the initial poison shot still avoids poison entirely.

### Fixed (server)

- **"Perma stuck in the FFA queue", and locked out of every other queue with it
  (#124/#139).** Leaving a locked FFA lobby has never once worked: the endpoint marks the
  departure by concatenating the player's id onto the lobby's `departed_ids` array, and with
  a plain bind parameter PostgreSQL types that parameter as an *array* rather than a single
  id. The driver rejected it, the whole transaction rolled back, and the statement that
  actually removes the player from the queue — the last line of the endpoint — never ran.
  Every leave returned an error; 34 of 34 leave requests in one production log window
  failed, with none succeeding. Because the leftover row reads as "this player is mid-match",
  it also blocked them from joining 1v1, 2v2 and 1v2, and the game client's retry loop kept
  the row looking permanently fresh so no automatic cleanup could ever reach it — hence the
  repeating "the server will clear you shortly" message that never came true. Broken since
  FFA shipped in v1.35.0; migrations 165 and 171 had been hand-clearing individual lobbies
  without the cause being known. Schema/data: migration **173** frees any player still
  stranded (2 freed on apply, plus 1 who escaped the moment the fix went live).

## v1.35.4 — 2026-07-30 — rope objects, poison desync, block grace, FFA casual-wait

Everything previously accumulated as "Unreleased" ships in this version: bug reports
**#125-#140** across two waves plus the July 30 lifecycle-audit closeout. Backend changes
were deployed progressively through the day; the client half lands with this release.
Schema changes: migrations **167** (FFA damage/kill telemetry), **168** (recover two wiped
FFA games), **169** (match-report quarantine), **170** (`team_series.room_issued_at`),
**171** (free a dispersed FFA sitting), **172** (publish Tattered Cape placement rev 2).

> **Version note:** 1.35.3 was cut and its Thunderstore package uploaded, then two more
> fixes landed from the #140 session analysis (the room-wide rope-scale gate and the 3-4
> player FFA teleport guard). Thunderstore versions are immutable, so the corrected build
> ships as 1.35.4 and supersedes it. 1.35.3 exists only as that superseded Thunderstore
> package — there is no 1.35.3 GitHub release.

Cosmetics: **Tattered Cape** ships an approved placement revision — it renders noticeably
larger (scale 1.70 -> 2.15). The art itself is unchanged.

### Found in Sid's 4-hour session log (#140)

- **3- and 4-player FFA rounds could leave a player un-teleported after someone left.**
  The guard that skips a departed player during the round-start teleport was tied to the
  map-growth feature, and map growth only starts at 5 players — so in smaller lobbies the
  base game's own loop ran, hit the departed player, and stopped, leaving everyone after
  them standing wherever they were while the map changed underneath. The guard now covers
  every FFA lobby size. The session log caught this race one step short of failing.

### Bug reports #131-#138 + lifecycle audit closeout (July 30, second wave)

### Client

- **Rope-hung map objects no longer fall at round start on scaled FFA maps (#133/#134).**
  Vanilla replaces every physics piece with a networked copy after the map enters, and the
  re-parent preserved the copy's world SCALE — on a scaled FFA map the copy came out ~6%
  smaller than the map around it, and a rope endpoint authored near the piece's edge missed
  its attach probe (one missed endpoint is enough: the saw case keeps the rope but drops the
  saw). The master's jointless piece then free-falls, synced to everyone. Proven from the
  serialized map data: the two reported cases cross the miss threshold exactly between the
  3% scaling of 1.35.0 and the 6% of 1.35.2. The networked copies now inherit the map's
  scale factor, which restores both the attach geometry and the pieces' visual size.
  **Capability-gated on the whole room**: these pieces are simulated by the room's host and
  streamed to everyone, so a client applying the fix under a host that lacks it fights the
  streamed positions with its larger colliders (Sid's live "boxes are vibrating" report from
  the first mixed lobby). The rescale therefore applies only when every player in the room
  is on this build — checking only the host was not enough, because the host can change
  mid-map and silently invalidate that decision. A mixed room behaves exactly as before
  (no vibration; ropes still break there until everyone updates).
- **Poison desync root-caused and closed (#135).** The previous fix exempted victims whose
  stats route damage through the damage-over-time path (Decay holders) — and every tick on
  such a victim, plain poison included, kept vanilla's per-replica block behavior. Proven
  from the reported lobby: all four clients ran the fix, two of the four held Decay. The
  exemption is removed: DoT ticks now always apply on every replica. Blocking the direct
  hit still prevents a Decay spread entirely; only the unsyncable "block mid-spread"
  niche is gone — flagged as a deliberate balance call, easy to revert if Sid disagrees.
- **The FFA spawn grace now covers block as well as fire (#136).** Suppressed at the input
  layer (the only place that replicates), so every client agrees a grace-window block
  never happened; the banner says fire AND block unlock together.
- **Waiting in a casual game while sitting in an open FFA lobby is now allowed (#132).**
  The lobby seat is only torn down when entering a COMPETITIVE room. When the host presses
  Start, members get a 5-second on-screen countdown; anyone in a casual game is pulled out
  immediately (marked as a deliberate exit, never a DC) and auto-joins with everyone else —
  if the casual exit interrupts the join, it re-arms and retries within seconds.
- **FFA score HUD restyled (#138, Stan's suggestion).** The translucent black backing box
  is gone; names carry a drop shadow instead, and every unscored point renders as a tiny
  grey dot so the first-to-5 target is legible at a glance.

### Server & bot

- **2v2 match reports rejected for lifecycle reasons are quarantined, not destroyed (audit
  item 1).** A report landing on a cancelled series is captured whole in the same admin
  quarantine the FFA path got on July 30 — previously the entire game was lost. Capture is
  trust-bound: the four reported players must be exactly the series' recorded members with
  the reporter among them, so the DLL secret cannot be used to spam the admin queue. The
  quarantine list/accept surface now understands team reports (score rendering + a
  mode-scoped "later rated results" eligibility check).
- **A leave during a live game no longer cancels the group (audit item 2, all three
  modes) — once the heartbeat-carrying client is the room's floor.** 2v2's leave cascade
  only fires when the series has zero recorded games AND no verified in-game heartbeat;
  1v2 and FFA zero-game dissolutions take the same rule, with FFA falling through to the
  played-lobby departure path. A mid-game leaver is simply marked; the match pipeline owns
  the outcome. On 1.35.2 clients (no heartbeat sender) leaves behave as before. FFA
  survivors' queue rows are no longer deleted the moment someone leaves (the janitor's
  own windows still bound their lifetime), later leavers are recorded even after their
  row is pruned, and a lobby with a verifiably live game is never closed by the
  all-but-one arithmetic.
- **The in-game heartbeat is verified and means gameplay, not room occupancy.** The
  presence ping's `in_match` claim only counts when the session token checks out and the
  pinger is a recorded member of the named group, and the client only sends it while a
  battle is actually ongoing. The ping fires as the game starts (with transport-failure
  retry), shrinking the unprotected head of game 1 to seconds. Verification inherits the
  Steam-auth enforcement ladder — accounts the ladder still treats leniently are verified
  to the same (lesser) degree everywhere else is.
- **Veto semantics split by caller shape.** Janitor closers (which re-fire and carry
  ceilings) keep the conservative "young process = veto" rule; one-shot actors (leave
  dissolutions, the assembly cancel) act only on trusted positive evidence — vetoing those
  on ignorance converted failed assemblies into permanent husks. A new janitor arm cancels
  rowless active 2v2 husks (60+ min quiet, no rows, no live evidence) as the last resort.
- **Two blind FFA closers deleted (audit item 3):** the janitor's second 3-hour rule and
  the 2-hour sweep that ran inside every leave request. The janitor's veto-aware dispersed
  close is the single lifecycle authority now.
- **2v2 assembly timeout measures from room issue, not match time (audit item 4).**
  New `room_issued_at` stamp (migration 170); 180s deadline; the heartbeat covers a live
  game whose spawn-confirm POST was lost. The janitor's 2v2 stale-series sweep takes the
  conservative veto.
- **Discord "How FFA works" FAQ updated for host lobbies and forced picks (#137).**

### Bug reports #125-#130 (July 30, first wave)

Backend + bot were deployed 2026-07-30; the client half ships here.
Schema changes: migration **167** (`ffa_match_players.damage_dealt`, `damage_dealt_timeline`,
`kill_timeline`, `absent`; applied).

- **T chat works during combat again (#128).** It now opens any time the game is running; the
  only thing that suppresses it is ROUNDS' own Enter chat actually being open. While the box has
  focus the mod holds the game's own two input flags, so typing can't move you, shoot, ready you
  up, or confirm a card pick. Also stops our Enter from toggling the vanilla chat open behind it.
- **1v2 rewards are visible and scale with difficulty (#129).** 1v2 always paid, but nothing
  displayed it and the every-5-levels bonus never fired for it. Added the display in three
  places, granted the level bonus, and scaled rewards by seat, extra-pick handicap, opponent elo
  and 1v2-leaderboard standing.
- **Recent Series no longer eats teammate names (#126).** Two-name side labels shared one
  character budget, so the second name could render as just "..".
- **My Stats → Record covers 1v2 and FFA (#130).** 1v2 split by seat; FFA win rate, top-3 rate,
  kills/game, average placement, and damage/game once games carry the new telemetry.
- **Discord mentions resolve to names in the in-game chat (#125)**, and the bot can no longer be
  used to ping the server via relayed in-game text.
- **`/game` for FFA (#127):** discarded cards shown separately, real M:SS time axis, damage and
  blocks split apart, plus new kills and damage-dealt graphs.

### Lifecycle sweep + match-report quarantine (July 30 incident)

Two completed FFA games were destroyed: a timer closed the lobby mid-sitting and the report then
came back `409 "Lobby is not active"`. The root cause is structural — the server only learns a
game happened when the REPORT lands, at game END, so every timeout was blind for the whole
duration of a live game. A 40-minute FFA is normal.

- **Rejected reports are no longer thrown away.** A report rejected for a lifecycle reason is
  captured whole in `match_report_quarantine` with an admin list / discard / accept surface.
  Integrity failures (bad signature, unknown players, impossible scores) are still rejected
  outright and never stored. **Accept records approval only — it never re-applies rating**,
  because Glicko is order dependent.
- **Timers now need positive evidence.** The presence ping carries `in_match=<group id>`; the
  dispersed, quiet and sitting-over rules veto when a game is live rather than inferring "nothing
  is happening" from silence. Bounded by a 3h ceiling, and it will not answer until the process
  has outlived its TTL so a restart cannot make every group look idle.
- **Windows retuned:** dispersed close scales with lobby size (60 min floor, 70 at 10 players),
  husk sweeps 30 → 60 min, sitting-over 5 → 15 min in both the FFA and 1v2 copies.
- **The client stopped deleting recoverable reports** — 429 (rate limited) and 401 (session
  lapsed) were being treated as permanent outbox failures.
- **Migration 168** restores the two destroyed games for all six affected players: ratings from a
  full chronological replay of every recorded FFA match plus those two, validated by reproducing
  the live ladder to within 0.1 elo when the two are excluded.

Remaining audit items (2v2's worse variant, Leave invalidating a live game 1, two more blind FFA
closers, 2v2's assembly clock) are listed in `docs/TODO.md` and detailed in
`ai-collab/codex-lifecycle-sweep.md`.

## v1.35.2 — 2026-07-29 — FFA host lobbies, betting reliability, forced picks

Everything below (previously accumulated as "Unreleased") ships in this version. Backend
changes were deployed progressively through the day; the client half lands with this release.
Schema changes: migration **166** (`ffa_lobbies.host_player_id` + open-lobby index; applied).

### FFA host lobbies (replaces the auto-gather queue; ships with the next release)

- **FFA is now played from host-controlled lobbies.** Create a lobby or join an open one from
  the new in-tab browser; the host presses **Start** once at least 3 players are in (up to 10).
  Several lobbies can be open at the same time — the old "3 players and a countdown" auto-start
  is gone from the new client.
- If the host leaves, the longest-waiting member is promoted automatically; an emptied lobby
  closes itself. Sitting in a lobby counts as your active queue everywhere else, exactly like a
  locked match.
- Players on the previous version keep the old auto-gather until they update; the two systems
  run side by side on the server during the transition, with separate pools.

### FFA pick window (client, next release)

- **Running out the pick timer no longer skips your pick.** When the on-screen countdown hits
  zero, the card you have highlighted is picked automatically (card 1 if you never moved) and a
  toast announces it. Skipping a pick used to be a way to protect a finished build from the
  rolling 5-card cap, which defeated the point of the mode's card cycle. Nothing silent: the
  timer is visible the whole time and the auto-pick is announced on screen.
- The pick deadline is now published by the lobby's host clock, so every player's countdown and
  auto-pick agree with the clock that actually closes the window — a slow-loading client can no
  longer miss its forced pick to clock skew. (Mixed-version caveats until the minimum supported
  version reaches this release: players on older builds don't auto-pick at all, and when the
  lobby's host is an older build the deadline isn't shared, so this build falls back to a local
  timer with a wider safety lead.)

### Betting reliability (server, live)

- **Bets can no longer be stranded when a lobby or series ends without a result.** Every way an
  FFA lobby or 2v2 series closes now resolves its open bets: wagers on games that were actually
  played settle against the recorded result, and wagers on games that never happened are
  refunded. A background sweep also heals any bet that slipped through (including two
  historical ones), so "charged but never resolved" can no longer persist.
- 2v2 bets gained a refund path for cancelled or voided series — previously a cancelled series
  destroyed the stake outright.
- Settlement writes are claim-based on every path that touches FFA and 2v2 bets — a bet reaches
  exactly one terminal state, so two concurrent resolution passes can never pay the same bet
  twice. Series awaiting an admin decision after a disconnect are left untouched until the
  decision lands.

### FFA tab (client, next release)

- Recent Ranked FFAs shows each player's **final hand** inline, with replaced picks collapsed
  into a red "+N replaced" chip — hover the card line to see every pick in order. Long card
  histories no longer wrap into multi-line blocks.
- Titles render **after** the player name in Recent Ranked FFAs, matching every other surface.
- Long name+title combinations no longer paint into the Rating column on the FFA leaderboard.
- The Info button is the same size in the same place on the 2v2, 1v2 and FFA headers.
- The FFA info popup was rewritten: it now explains the Recent FFAs display (points, unconverted
  round wins, kills, replaced cards, rewards and rating change), documents the automatic pick,
  carries the current reward numbers, and is spaced for reading. It also notes that a level-up
  bonus lands inside that game's gold number — which is how a last place can occasionally
  out-earn the winner.

### FFA gameplay

- **Spawn positions were wrong in every 5+ player game.** The base game caches each spawn point as
  a *local* coordinate at map load and then teleports players to that raw number as a *world*
  position — which only holds at scale 1. FFA scales the map with the lobby, so since map scaling
  shipped, every player in every round of a 5+ player game landed short of their marker, and landing
  on one of the movable crates applies damage plus an impulse. Fixed at the point the coordinate is
  consumed.
- **Players 5–10 get real spawn points.** Maps ship four; the extra slots used to reuse another
  player's exact spot. Each fresh map is now scanned for solid static ground — skipping physics
  objects, animated pieces and the networked crates — and falls back to the old duplicate only where
  a map genuinely has nowhere else to stand.
- **Maps grow faster with lobby size** (3% → 6% per player above 4). Landed together with the spawn
  fix, because a larger factor multiplied the old spawn error.
- **One second of no-fire grace at the start of each FFA round**, so you can react before being
  shot. Armed at the moment the game actually hands control back, not when the round is flagged live.
- **Shield Charge and the rolling card cap** — a stale network handler key from an aborted teardown
  could leave the card's effect unattached; the pipeline now scrubs immediately before every apply.

### FFA economy

- **Gold roughly matches 2v2 per minute played.** FFA was paying about six times less: its XP base
  was half of 2v2's, it had no flat completion bonus at all, and the lobby-size multiplier only
  applied to first place — so lobby size paid nothing to nine of ten players. All three are fixed. A
  five-player win goes from about 13 gold to about 86; last place from 3 to 19.
- **Everyone who already played FFA was back-paid** the new placement bonus.
- **FFA now grants level-up gold**, which it never did.
- **Better betting odds** — minimum 2x in a 5+ player game, up to 5x for a confidently-rated
  underdog in a full lobby. A brand-new account cannot reach the ceiling.

### Queues

- **Fixed a lockout that could strand you in "Match found" indefinitely.** Leaving an FFA room to
  re-form the lobby left your queue entry claimed, which blocked joining *any* queue in *any* mode.
  The server now frees dispersed lobbies on its own, and the client recovers when it is holding a
  lobby but is not actually in a game.
- Betting on a finished FFA sitting is no longer offered, and the server rejects it.

### Menus

- **Recent Ranked Series now lists 2v2, 1v2 and FFA games** alongside 1v1, with the bets placed on
  each. The per-mode panels are unchanged.
- **Rating-history graph benchmark lines use the real Discord rank colours** instead of a hardcoded
  copy that drifted whenever a role was recoloured.
- **FFA match history shows every opponent**, wrapped and aligned, instead of cutting the list off
  at four names — and it no longer silently omitted one player per row.
- FFA score-progression graphs use a palette wide enough for ten players; two players could
  previously draw in the identical colour.
- The in-game bug-report viewer renders attached logs correctly.
- FFA game IDs copy in the same format as every other mode and work with the Discord `/game` command.

### Discord

- Live FFA lobbies and their odds now appear in the gambler channel.
- `/game` renders FFA matches (placements, per-player stats, cards, score graph).
- Dedicated "How FFA works" and "How 1v2 works" FAQ answers.

### Fixes

- **Streak achievements have never been granted to anyone** since they were added — the code that
  reads your streak was unreachable from the code that awards them. Fixed.
- Per-opponent session records in FFA are now decided head-to-head by placement. Previously any game
  you did not win counted as a loss against every player in it.
- Your bet history shows FFA and 2v2 wagers, not just 1v1.
- New players are no longer registered under their raw Steam ID when the game has not yet reported
  their name.

## v1.35.1 — 2026-07-28 — queue single-ownership, FFA gather window, report fixes

### Packaging
- **Thunderstore changelog trimmed to recent releases** — the full-history file
  crossed Thunderstore's 100KB upload limit and blocked the v1.35.0 package.
  Older releases now live in the GitHub changelog (linked from the package).

### Queues
- **Locked-in players leave every other queue** (the "ghost in 1v1 Search
  Ranked" report): a player who queued 1v1 and then got locked into an FFA /
  2v2 / 1v2 lobby kept heartbeating their 1v1 row from inside the game —
  showing as "1 searching" to everyone for the whole sitting and even able to
  receive a mid-game MATCH FOUND. Now the moment any mode issues a room, the
  locked players' still-searching rows in the other queues are removed
  server-side — and the client itself leaves the 1v1 queue when you enter any
  online game room (with a notice), covering casual/custom rooms too.
- **FFA/1v2 rejoin resets your queue timer** (bug #109): rejoining after a
  game restart used to inherit the old row's clock ("in queue 18 minutes
  already") and a stale rating snapshot; a rejoin while still unlocked now
  starts fresh.
- **FFA gather window extends while people join** (bug #111): lobbies no
  longer hard-start 25s after the 3rd joiner — every new joiner guarantees
  20 more seconds of pile-in time (capped at 120s total), so 5-10 player
  lobbies can actually form. Full lobbies still start instantly.

### Reports & Discord
- **Admins are exempt from the 10-reports-per-day limit** (session-verified,
  so a spoofed admin Steam ID in the request body still pays the normal cap).
- **`/faq topic:<title>` now matches topic titles** (bug #110): typing a
  title from the `/faq` list used to fail for every topic because the matcher
  only understood natural questions.


---

Older versions are listed in the full changelog on GitHub:
https://github.com/SidNDeed/SidsCompetitiveRounds/blob/main/docs/CHANGELOG.md
