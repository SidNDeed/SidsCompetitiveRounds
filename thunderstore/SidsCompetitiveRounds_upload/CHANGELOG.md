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

## v1.39.0 — 2026-08-18

Schema changes: migrations **225** (`spectate_drain_tombstones` table +
spectator cap default 5; applied 2026-08-16), **226** (`stream_channel_posts`
living-stream-post table), **227** (`record_exclusions` — admin record
removal).

**Records (round 2, Aug 18)**

- **Rarest Hand** — the rare-picks record board's proper name (it measures
  the rarest hand *picked*).
- **New: Luckiest** — the rarest hand *drawn*: the share of Rare cards among
  everything a game offered a player, picked or not (counted over recorded
  hands with a full candidate set). Deliberately allows the same player to
  hold several placements — luck shouldn't favor anyone, so a name filling
  this board up is worth a second look.
- **Records now has two pages** (button top-right of the panel); new boards
  land on page 2.
- **Admins can remove records** — a small control on each row (click twice
  to confirm) excludes a cheated row from the boards without touching the
  match itself; every removal is audit-logged.
- **Record hovers carry the game** — score (half-point convention), duration,
  the holder's full name and title, and the cards one per line.
- **Home tab "Get Link Code" button no longer clips its label.**

**Corrections + polish (round 3, Aug 18)**

- Recent Tournaments popup is split into **Sync and Async sections** again.
- Bracket hover scores use the **half-point convention** (the "(x-y pts)"
  form is gone for good).
- **Text floor:** everything this batch touched renders at 14pt bold or
  bigger — records rows, bracket cells and elos, hover tooltips.
- Offer telemetry hardened: offers are recorded only for the reporting
  player's own seat, with size caps, and excluded matches stop voting in
  the card-rarity election.
- **Records boards only admit rows the holder's own client reported** — a
  modified opponent can no longer plant a fake record (stats, cards, or
  draws) under an innocent player's name. Rarity votes follow the same
  rule, and forged-length games can't own the Longest Game board.
- **Every new string is translated** (es/ru/uk/sv — 65 keys x 4 languages).

**Broadcast seat (VM-only, invisible to players)**

- The game pins itself to windowed 1920x1080 (the capture geometry OBS
  expects) and drops to 15fps after 16 minutes idle — both only on the
  broadcast identity.
- Nightly clean cycle at 05:00 (skipped while a stream is live).

**Fixed**

- **Lost identity / "PlayerName" (bug 234).** The base game sets every
  player's nickname to a literal "PlayerName" placeholder before connecting
  and repairs it from Steam only once, as the last step of joining a room —
  if that single attempt fails (a transient Steam hiccup), the placeholder
  sticks for the whole game and the in-world name label never refreshes. The
  mod now retries the Steam lookup with a bounded in-room budget and
  repaints name labels whenever a player's nickname heals, in every online
  room type.
- **2v2 game details ignored team colors.** Expanding a Recent 2v2 Series
  entry showed the per-game card columns and telemetry lines in fixed
  blue/orange side colors even when the series header showed the stamped
  team-identity colors — the inner view could contradict the header (and
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
  are gone — the two brackets now only visibly meet at the grand final.
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

## v1.38.7 — 2026-08-15

Schema changes: migrations **221** (`pcolor_poison` body color; applied),
**222** (`ranked_queue.home_region`; applied), **223** (76 machine-translation
seeds for the new shop/vocab keys; applied).

**Added**

- **New body color: Poison.** The exact green the Poison card flashes on its
  victims — taken from the game's own card data rather than matched by eye —
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
  your next opponent — or the match that decides them; elimination
  congratulates the run, with your placement when the bracket records one;
  champions get their own DM. A separate DM lands the moment your next
  match actually goes live, and it's delivered reliably — retried until it
  reaches you. Forfeit advances are phrased honestly instead of "you won".
- **Tournament matches are always spectatable.** The spectator opt-out is
  bypassed for the two players of a live bracket match — tournament games
  are public by rule. Every other spectate safety rule still applies.

**Fixed**

- **Tournament bets popup is clickable again (bug 230).** The popup's own
  buttons were being swallowed by its click shield, and a coordinate bug made
  any click read as "outside the popup" and dismiss it.
- **Better diagnostics for post-match disconnects (bugs 227/228).** The
  connection-restart tracers now run in every room type, so the next
  code-room disconnect names its exact trigger in the log. The investigation
  found the mechanism — the base game restarts a player's connection 10
  seconds after they answer the rematch prompt if their opponent hasn't
  answered yet — but a safe fix needs both clients acting together, and
  every one-sided approach made things worse in review; it's deferred to a
  dedicated pass rather than shipped half-safe.

- **Poison hits register reliably (bug 225).** A bullet's poison component
  could miss registration on the victim's client due to a game init-ordering
  race — the hit then knocked you back but the poison (all of a poison
  bullet's real damage) never started on any screen. The missing component is
  now re-registered at hit time, with a safety net against double-application.
- **Faces show in 1v2 and 2v2 rooms (bug 224).** The last player to join a
  team room missed everyone else's face for the whole sitting (a base-game
  quirk FFA already worked around); the fix now covers team rooms too.
- **Discord language channels stop reposting ancient messages (bug 226).**
  The relay now tracks exactly what it has delivered — durably, across
  restarts — instead of relying on a memory that old test messages could
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
  — an early design decision had the game deliberately skip them while the
  translation portal kept accepting the work, so approved entries (24 in
  Russian alone) existed but never displayed.
- **Nametag size previews show again.** The Bigger / XL / Huge / Float rows
  rendered nothing after "Preview:" in every language — the preview's own
  size tag was taller than the row and got clipped whole. Those rows now
  grow to show the name at its true size, which is the point of the preview.
- **Rarity and item-kind words translate.** "(rare)", "(common)", "(face)",
  "(nametag)" and friends were never translatable at all. In Russian,
  Spanish, Ukrainian and Swedish the rarity reads as a labeled phrase
  ("Ã‘â‚¬ÃÂµÃÂ´ÃÂºÃÂ¾Ã‘ÂÃ‘â€šÑŒ: Ã‘ÂÃÂ¿ÃÂ¸Ã‘â€¡ÃÂµÃ‘ÂÃÂºÃÂ°Ã‘Â") so the grammar works next to any item type.
- **Fairer ranked-queue regions.** The room region used to be whichever
  player's momentary connection region happened to win the coin toss — which
  is how two same-region players could both end up on a 200-ping US server.
  Now, when both players' Photon home region (its own ping cache) agrees,
  that region is used, and any region signal beats the old "us" default.
  Also fixed a pre-existing race where the two clients could be told
  different regions for the same match and end up in separate rooms.

**Changed**

- **Card popup images no longer need downloading.** Card art in stats popups,
  the hold-Tab board and the tier-list export now renders natively from the
  game itself (correct in every language, always up to date) — the old image
  pack download (which had been failing quietly) is gone, and the mod's
  Thunderstore package shrinks by ~15 MB. The tier-list export shows a
  progress note the first time while it renders each card.

_(older entries trimmed - full history on GitHub)_
