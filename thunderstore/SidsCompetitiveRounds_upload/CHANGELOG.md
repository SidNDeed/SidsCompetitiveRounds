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

## v1.35.0 — 2026-07-28 — NEW MODE: Free-For-All, rank ladder reorganization, 1v2 overhaul

### Rank reorganization (July 28, round 3)
- **New rank ladder** (community proposal): tier-group floors move to
  Intermediate **1500**, Advanced **1675**, Master **1980** — Grand Master stays
  **2330** — and the sub-tiers widen toward the bottom so early ranks are
  meaningful climbs (Beginner I is now 0-1139 instead of a 16-point sliver).
  Every tier spells out its numeral: Beginner I-V, Intermediate I-V, Advanced
  I-V, Master I-V, Grand Master I-V.
- **Discord roles follow automatically** once the new `/setup-rank-roles`
  command has been run (renames the existing 25 roles in place — colors,
  position and members are preserved — then the regular role sync re-sorts
  everyone onto their new rung within ~30 minutes).
- **Rating-history graph** (Leaderboard tab, player detail): the reference
  lines now sit on the tier boundaries — 1139 (top of Beginner I), then the
  1500 / 1675 / 1980 / 2330 tier floors — colored to match the Discord rank
  families.
- **Master achievement** now unlocks at **1980** (the new Master I floor), and
  everyone whose peak 1v1/2v2 rating already clears it gets it backfilled with
  its full 500g reward.
- **Opponent-tier reward multipliers** track the new floors (a 1990-rated
  opponent now pays Master-tier gold/XP, matching their displayed rank).

### FFA — bigger maps for bigger lobbies (July 28, round 3)
- **Maps now scale up 3% per player above 4** (a 10-player lobby plays on a
  ~18% larger arena). The whole world scales together — platforms spread out
  and grow, the camera zooms to match, and the kill boundary moves out
  proportionally — so the game feels identical, just roomier. The factor is
  published by the lobby master each round, so every client plays the exact
  same map. 4 or fewer players = exactly vanilla.

### Queues — 30-minute cap + ghost cleanup (July 28, round 3)
- **Queue searches now cap at 30 minutes** in every mode (1v1, 2v2, 1v2, FFA).
  If you hit the cap you get a clear in-game notice — rejoin if you're still
  around. No more all-afternoon phantom queue entries.
- **Fixed the 2v2 queue cleanup crash**: the background sweeper had been dying
  every tick since July 27 on a Postgres locking error, so crashed clients'
  queue rows were never removed — that's how one player showed "285 minutes in
  queue" on the 2v2 tab, and how stale rows made custom lobbies look fuller
  than they were. The sweeper is fixed AND each cleanup now runs isolated so
  one failure can never kill the others again.
- **The 2v2 tab only lists players whose game is actually polling** — ghost
  rows can no longer appear as live queuers (this is what made "4 people in a
  custom lobby" not match: some of the four were ghosts).

### NEW MODE: Free-For-All (3-10 players) — RANKED
The FFA tab (under Multiplayer) is live, hardened across two July 28 playtest
rounds (fix batches below). Big-lobby edge cases will still surface — please
keep filing bug reports with logs attached.
- **Queue:** joining is consent — no rating band, no ready-up. Once 3 people are
  searching a 25-second gather window opens so more can pile in, up to 10; a full
  lobby starts immediately.
- **The game:** everyone is their own team. Last player standing takes a half
  point, 2 half points make a point, first to 5 points wins. A player leaving
  does not end the match — the survivors play on, and the leaver keeps their
  tallies for placement.
- **Live standings:** a vanilla-style top-left scoreboard — one row per player
  in their colour, a full dot per point and a half dot for a held half point.
  The outright leader wears the crown; tied leaders do not.
- **Simultaneous card picks:** everyone picks at the same time during the opening
  draw, and after each point everyone who did not take it picks together
  again — no more sitting through a 10-player pick queue. Picks are synchronised
  so every client applies the same cards. Nothing is ever picked FOR you: the
  window stays open at least 45 seconds, extends while picks come in (90s cap),
  shows a live countdown, and missing it just means no card that cycle.
- **Placement tie-breaks:** points, then all half points earned across the game
  (spent ones included), then total kills.
- **Rolling 5-card cap:** your 6th pick pushes out your oldest card, Rolling Card
  Bar style. Your own card bar shows your live deck; hold Tab for everyone's.
- **Ranked from day one:** every match moves a real FFA rating, bounded so a
  10-player game cannot swing your rating several times harder than a 3-player one.
  Placement earns XP and gold — more players beaten, more XP, plus a winner bonus.
- **FFA leaderboard** (sortable by rating, games, wins, top-3s, average placement,
  win rate) and a **Recent Ranked FFAs** panel showing every player's placement,
  rounds, points and rating change, plus cards for the top three finishers.

### 1v2
- **Separate Solo and Duo leaderboards.** 20 solo wins and 20 duo wins are not the
  same achievement, so they no longer share a board — and you only appear on a
  board for a role you have actually played. Each board's W-L counts only that
  role's games, sorted by wins, then win rate, then games played.
- **New "Recent 1v2 Games" panel:** recent series with per-game scores, per-player
  cards, and the gold/XP each player earned.
- **The duo now spawns together.** One duo member was spawning next to the solo —
  in the spot a 2v2 teammate takes — while their partner stood alone across the
  map. The solo now gets one side to themselves and the duo share the other.
- **The second duo player gets their character back at the card-pick screen.** The
  base game only ever shows one character per round pick, which is fine for 1v1;
  with two losers, the second person picked in front of an empty stage. Everyone
  picking now gets their own body, face and colour. *(This also fixes 2v2, where
  the first picker was being shown the wrong player's character entirely.)*
- **My Stats lists your 1v2 opponents** instead of a bare "Casual 2W-0L". 1v2 games
  were being counted as casual with no opponent rows at all; they now have their
  own 1v2 line in Session Info and list everyone you played, with your duo partner
  shown as "w/ Name" the way 2v2 does.
- **The in-game top line no longer claims a 1v2 is RANKED** and no longer names just
  one opponent. It reads "1v2 BETA - Unranked" with the real 1v2 series score and
  every player in the room.
- Equipped title colours now tint player names on the 1v2 boards.

### Menus
- **Mouse-wheel scrolling is 3x faster everywhere.** It was slow enough that people
  were click-dragging every list instead.
- **Leaderboard click-drag scrolling should be smoother.** The scroll views were
  using a stencil mask, which forces an extra render pass and breaks batching
  across ~100 leaderboard rows; they now use rect clipping.
- **Non-Latin name support has been rebuilt, but the new path has not been tested
  in-game yet.** The old one could never have worked on this version of the game.
  The replacement loads fonts directly from your system: Latin-extended, Greek and
  Cyrillic are prepared up front, Chinese, Japanese and Korean are added when those
  fonts are installed, and anything else is filled in as it appears. Please report
  any names still showing as empty boxes.
- **New Info buttons on the 2v2, 1v2 and FFA tabs** explaining how each mode works
  and what every leaderboard column means — including FFA's AvgPl and 2v2's Gold,
  XP and Avg Mate Elo. The info popup, Tournaments included, is bigger with
  bigger text.
- **1v2 and FFA tab text enlarged** to match the rest of the menus, with rows,
  buttons and columns resized to suit.

### Base-game bug fixes
- **Post-death knockback and damage-over-time no longer spam console errors.** The
  base game fires those at players it has already deactivated; harmless, but it
  buried real errors in every log.
- **Cosmetic auras and colour tints no longer silently skip a round** when their
  refresh landed while you were still dead between rounds.
- **Card-effect cleanup between games now runs a second, correctly-timed pass.**
  The old sweep ran before the game tore down the previous game's card objects, so
  a broken card effect (the Shield Charge class of bug) could stay broken for a
  full game after a rematch.

### Server
- The server now records FFA queues and lobbies, match results, each player's stats
  and cards, FFA ratings, and FFA-specific Gold/XP totals.
- It now powers FFA matchmaking, result reporting, leaderboards and recent games,
  plus 1v2's recent-games panel and the separate Solo/Duo boards.
- FFA reports must match the active lobby's locked players, player count and slots.
  The server also requires one unique winner at exactly 5 points and rejects
  totals above the mode's ceilings, so a result cannot silently drop the players
  who beat you. Kill counts are stored per player and break placement ties.
- Schema: migration 160 backfills the Master achievement (+500g) for peak
  ratings already at or above the new 1980 floor.

### FFA — second-playtest round (July 28, round 2)
- **Recent Ranked FFAs got the full treatment:** per-player rows with score
  dots (points as full dots, leftover half points as half dots with a count),
  kills, gold/XP earned, equipped titles, each player's cards on their own
  line with rolled-off cards in red, a game-ID copy button, and a
  score-progression graph on hover (new games record a half-point timeline).
- **Winner rewards scale with lobby size:** the winner's XP/gold multiplier
  is x1.5 in a 3-player game growing to x5 in a full 10-player lobby.
- **FFA betting:** spectators can bet gold on any active FFA lobby from the
  FFA tab. Field odds come from FFA Glicko ratings (RD-aware); payouts scale
  with lobby size up to x5; uncertain ratings restrict betting, stakes are
  refunded if a lobby dies before the game reports.
- **Discord bot finally knows FFA exists:** queue beacon pings, a result
  embed per ranked FFA (placements, points, kills, rating moves), and the
  FAQ no longer claims FFA is "in design".
- **Player profiles show every mode:** clicking a leaderboard player now has
  1v2, 2v2 and FFA history sections alongside the 1v1 one (FFA rows carry
  player count, placement, rating move, date and the field).
- **Session Info records FFAs** (bug #106) — games, placements and
  per-opponent tallies.
- **Cross-machine cosmetics fix** (bug #102): the base game sends faces via
  an unbuffered network event at spawn time, so clients still loading missed
  early spawners' faces/cosmetics forever. Everyone re-sends theirs once the
  FFA game starts.
- **No more 2-player "FFAs"** (bug #104): leavers dropping the room below 3
  end the sitting after the current game.
- **Achievements only evaluate in competitive rooms** (bug #101): public
  quickplay could award input-tracked achievements (Instinct and friends)
  because the violation detectors never ran there. The one confirmed-false
  unlock was revoked.
- **Hold-Tab board no longer clips wrapped card lists** (bug #107), and the
  FFA leaderboard highlights the active sort column (the sorts themselves
  were working — with three players the order just rarely changes).
- Names using math-symbol Unicode (the boxes on leaderboard #47) render now:
  the font fallback chain gained Segoe UI Symbol / Cambria Math.

### FFA — first-playtest fixes (July 28)
- **Nobody's card is ever force-picked again.** The first build auto-picked your
  highlighted (first) card after 25 seconds, which looked exactly like "someone
  spamming space picks everyone's first card" (reports 92-98). Auto-pick is gone;
  see the pick-window rules above.
- **A leaver no longer strands the survivors in slow motion** (reports 99/100).
  The base game keeps the departed player's destroyed object in its player list
  and the next transition crashed on it before restoring game speed or reviving
  anyone. Departed players are now cleanly removed on every client, the
  transition survives errors, and the sync-up wait can no longer hang forever.
- **Hold-Tab board:** card names render in consistent CAPS, and hovering a card
  name shows its card art.
- The mode info popups no longer describe reporter internals, and the in-game
  language is half points / points everywhere.
- **Cross-review hardening** (adversarial review of the fix batch): the server
  no longer rejects honest long games (the half-point ceiling ignored that
  everyone's banked half is wiped when any player converts a point); a member
  quitting mid-sitting no longer closes the lobby out from under the
  survivors' reports; rematch reports after a hard disconnect still cover the
  frozen roster, with the departed member held as a zero-tally "ghost" who is
  neither rated nor rewarded for games they never played; a winner who closes
  the game instantly after clinching still gets the match reported; and the
  end-of-game placement toast now counts leavers you didn't beat.

## v1.34.5 — 2026-07-27 — attempted base-game bug fixes, menu overhaul, security batch

### Base-game bugs — ATTEMPTED FIXES, PLEASE REPORT BACK
These target bugs in ROUNDS itself, found by reading the game's own code. They are
**not confirmed fixed in live play yet** — they have had almost no play-testing, so
treat every one as "should be better, tell us if it isn't". They only apply in
competitive rooms and sandbox, never in public quickplay. If you still hit any of
these (or see something NEW go wrong around them), please file a bug report from the
Settings tab with your log attached — that is what turns these into confirmed fixes.
- **Demonic Pact should stop breaking Spray in later games.** The game copies Demonic Pact's "no holding the trigger" flag onto your gun and never clears it between games in the same room — so picking Spray in any later game fired one shot per click instead of spraying. The flag is now reset between games. *(Cause confirmed in the game's files; the fix itself still needs play-testing.)*
- **Poison "ghost damage" attempt.** Occasionally a poisoned player's own health bar stopped tracking ticks that everyone else saw land (you could still hear them). Best theory: each player's copy of the game decides separately whether a tick lands during a block window, and the copies can disagree. Ticks should now land consistently on every screen. Players holding Decay are deliberately exempt so blocking mid-spread still works exactly like the base game.
- **Drill bullets fired against a wall should no longer be invisible to other players.** The game moves the wrong object when a drilled bullet comes out the far side; the mod now moves the actual bullet on everyone else's screen. *(Lowest confidence of the five — please report whether it still happens.)*
- **Killing your opponent during the end screen should no longer corrupt the next game** (the missing map / undespawned body / death-to-nothing sequence). Kills and damage-over-time ticks that arrive after the game has already ended are now ignored.
- **Chase's card text no longer advertises "+30% Health".** The bonus is dead data inside the game files — it was never actually applied to anyone. The card's real effect (a speed boost while heading at a visible opponent) is unchanged; only the phantom line is removed. *(This one is a display-only change and is safe.)*

### Cosmetics — new community art
- **Ballooniphones** and **Soda Helm**, both by their artist through the full upload → placement review → release pipeline. They ship at the exact scale and position that were approved in-game. The artist opens sales from the Artist tab when ready.

### Menus
- **Tournaments tab no longer paints text over itself on smaller/wider windows.** The long "How It Works" and prize blocks moved behind two buttons that open a scrollable popup, and the whole left column scrolls now.
- **Settings tab reorganized** into Data & Privacy / Interface / Visuals & Effects, and every description now sits directly UNDER the setting it describes (bug #87 — they used to hug the button above them).
- **The in-match ranked line now reads "Series Score: X - X (Total Series X - X)"** where Total Series is your lifetime series record against the CURRENT opponent — replacing the confusing rolling "session" tally.

### Cosmetics — artist workflow
- **The placement drag in the artist/admin preview is now a visual aid only — it is never saved.** New cosmetics spawn centered and players position them in the character editor; already-shipped items keep their approved placements.

### Chat
- If secure chat can't connect on your network, chat falls back for that session instead of silently eating your messages (the rest of the mod already did this).

### Server & security
- Fixed a matchmaking deadlock where two players polling at the same instant could briefly wedge the 1v1 queue, plus a batch of queue-lock hardening across 1v1/2v2/1v2.
- **Leaving a queue now waits for the server to confirm.** If the leave request failed (bad connection, a busy moment), the mod used to show you as out while your slot stayed live server-side — which could lock other players into a lobby with a ghost. All three queues (1v1, 2v2, 1v2) now show "Leaving queue...", retry the request, and only then finish; joining again is held off for the moment it takes the leave to resolve.
- **A match result is no longer wedged by a disconnect forfeit or an admin correction arriving at the same moment.** If the last game of a series was reported at the same instant something else finished that same series, the two could block each other and one would lose — and when that was the match report, a real game silently didn't count. The result-writing paths (match reports, forfeits, admin resolve/reverse, the ratings rebuild) now claim their records in one consistent order in both 1v1 and 2v2, so they wait their turn instead of colliding.
- **An admin correction can no longer be half-undone by a match report landing at the same time.** Reversing a series while its final game was still being processed could leave the rating change applied anyway, and could hand out a title for a win that had just been taken back. The rating step now re-checks that the series still stands before it applies anything.
- **A problem paying out bets can no longer take the match result down with it.** Bet settlement is now isolated in 1v1 the way it already was in 2v2: if it fails, the game still counts and the ratings still apply.
- Admin actions now use a separate secret that does not ship inside the mod — previously anyone who unpacked the DLL could forge admin requests.
- Session checks extended across cosmetic equips, privacy toggles, blocks, and queue actions; bans now also revoke live sessions and stop new ones from being minted.
- Deleting your data now also clears 2v2/1v2 queue entries and login sessions, and declining a match is validated against who you're actually matched with.
- The API's public documentation pages were turned off and the minimum supported mod version was raised to 1.33.0 (older clients get the update prompt).

### Schema changes
- `151_steam_auth_arming.sql` — adds `players.steam_auth_seen_at` (monotonic steam-auth arming) with a backfill from surviving verified sessions. Applied 2026-07-27.
- `152_ban_session_cleanup.sql` — one-time revocation of sessions held by already-banned accounts. Applied 2026-07-27.
- `153_release_ballooniphones_soda_helm.sql` — publishes the two community face cosmetics bundled in this release, guarded against a post-bundle placement revision. Applied 2026-07-27.

## v1.34.4 — 2026-07-26 — 1v2 extra-pick crash fix + HTTPS endpoint

### 1v2
- **Fixed the Solo Extra Pick hang.** With the option on, the solo player picked their first card and the round froze — the solo was then dropped and the other two saw "opponent disconnected". Cause was in the base game: it clears the current picker the instant a card is chosen, and the follow-up deal then looked that picker up with the cleared value and threw. Nothing ever hit it before because the extra pick is the only mode that asks for a second card. Reported by Stan (#86) and NotNic (#85), whose logs together pinned it down.
- The second card is also now selectable at all — the same cleared value disabled card selection, so even without the crash the extra pick could not have been used.

### Connection
- **The mod now talks to the server over HTTPS.** Traffic used to be plain HTTP, so anything on the network path (public wifi, a hostile ISP) could read your session, chat, and Steam ID. Existing installs are moved over automatically on first launch; a custom server address is left alone.
- If the secure endpoint cannot be reached from your network, the mod falls back to the old one for that session and retries the secure one next launch, so nobody gets stranded.

### Cosmetics
- **Crown and Dark Aura now use their approved placement.** Both had adjustments signed off in the artist review flow that never made it into a build (#84); they now render at the size and position that were approved.

### Server
- Hardened an unauthenticated stats endpoint that could be used to read the database, and closed two internal endpoints that trusted the caller's network address instead of a key. Both fixed server-side already — no action needed.

## v1.34.3 — 2026-07-24 — First community cosmetic ships + gambler ping fix

### Cosmetics
- **Spooky Head-Bouncers by Nix is live** — the first community cosmetic to go through the full artist upload -> admin placement review -> release pipeline. It ships at the exact scale and position that were approved in-game.
- **Releases now always bundle approved cosmetics.** v1.34.2 shipped without this one because the art lives in the database until a release compiles it into the client; the ship process now requires it, with a checksum check on the extracted art and a migration guard that refuses to publish if the approved placement changed after the bundle was cut.

### Discord
- **The gambler ping no longer repeats for the same series.** Bets lock while a game is being played and re-open between games, and the bot was forgetting a series every time that happened — so the same match got announced again on the next game. It now announces once per series for its whole life.

## v1.34.2 — 2026-07-24 — Cosmetic placement workflow, flagged-match evidence, performance pass

### Cosmetics — artists & admins
- **Artists set the render scale at upload.** The in-game uploader now opens a size preview: your PNG against an orange player-body circle, with a scale slider (0.50x–2.25x) and presets. A full 512x512 canvas equals the body only at ~1.30x — the preview shows the truth instead of a rule of thumb.
- **Drag to position.** Both the artist preview and the admin review let you drag the art. Offset is only the *default* start position (players can reposition face items themselves in the character editor), so it no longer clutters the list menus — scale is what decides whether art fits.
- **Adjust placement on already-shipped cosmetics.** Previously only new submissions could be adjusted; items that shipped before the review workflow existed had no record to edit. They can now be adjusted, and the change goes back through admin review before taking effect.
- **Placement changes are reviewed, not instant.** Scale/offset are compiled into the client, so an approved change goes live with the next mod update. The live item keeps its current placement until then.
- **Admin review upgrades:** the four approval guidelines plus a scale-appropriateness rule are shown in the popup, a denial reason is required, and re-placements show the current approved scale beside the proposed one.
- **Approve/deny now DMs the artist** with the outcome (and the reason on a denial).
- **A release tracker** lists approved cosmetics awaiting a client update, with the exact scale to bundle.
- **Unreleased art can no longer appear in the shop or on Home.** Community art stays hidden until its PNG actually ships in a client release, so Newest Cosmetics can't be taken over by an unreleased batch.

### Flagged matches (admin)
- **Flags now carry real evidence.** Both the in-game Admin panel and #scr-admin show Steam IDs and the suspect, the detector's reasoning, score and point progression, cards picked by each player, combat/input/FPS telemetry, and connection data.
- **Suspected-macro flags record the exact per-second windows** that broke the threshold, from both players rather than only the match reporter.
- **Flagged Matches gets more room** in the Admin tab, and clicking Details opens a full evidence view.

### In-match HUD
- **The Session line is gone.** The series score line now carries your session series record instead: `Series: 1 - 1   (session 2-1)`.
- **Session series now counts for both players.** It previously only updated on the client that submitted the match report, so one player in every match saw `0-0` all session.

### Performance
- Overlays now only draw on render frames, slow-changing labels refresh a few times a second instead of every frame, the hold-Tab table snapshots at 8 Hz, and chat reuses its buffers. Combat diagnostics are off unless Block Debug is on.
- **Animated Cosmetics now also freezes player-effect auras** — they kept emitting after the setting was turned off.

### Discord bot
- **Elo calculator fixed** — it timed out silently and never replied; it now answers or explains why it can't.
- **FAQ accuracy pass** across many false positives and missed questions, plus new answers (Grow, room codes, series, DC rules, install safety, questions channel, Steam↔Discord lookup).
- **Malformed room codes get a heads-up** — a posted code that isn't six capital letters gets a reply explaining the game reads it as offline. Ordinary chat, slang and names are left alone.

### Fixes
- 2v2 Recent Series no longer jumps the scroll when you click a series, and the `[ID]` copy target is the chip itself instead of the whole row.
- The game-ID button sits left of the score in both ranked and casual history.
- Artist rows hidden by scrolling are no longer clickable through the section above them.

## v1.34.1 — 2026-07-22 — July 22 nine-item batch + live feedback

### Discord identity (feedback round)
- **Discord name on the leaderboard is now opt-OUT** (was opt-in): linked players' Discord `@display name` shows on their leaderboard detail by default, so people looking for a ranked game know who to @. Turn it off in Settings → "Show Discord on leaderboard".
- **Search Ranked beacons now name who to @** — the Discord "searching for a ranked match" post (and the 2v2/1v2 equivalents) includes the searcher's `@display name` as plain text. It never pings them (only the RLFP Ping button does).
- **`/mystats` shows your Discord `@display name`** under the title.

### Client (mod)
- **My Stats history stat line tightened + ID button moved** (feedback): the Hit/Block/keys text is back to hugging its content (the wide split spacing is gone), and the game-ID copy button now sits right after the score instead of next to the opponent name.
- **2v2 Recent Series widened + enlarged** (feedback): the panel takes the previously-empty space left of it, text is bigger, the game-row ID chip is just `[ID]` (click the row to copy), and the row-height math is fixed at the root so player names no longer overlap the "Game N:" line. Each game shows a per-player FPS/ping/Hit%/Block% line with a hover mini-dashboard.
- **Hit % and Block % hover graphs** in My Stats Ranked/Casual history — for you AND your opponent (4 graphs per game). The stats line under each game is now clickable territory: hover your (or their) Hit % for a shots-fired-vs-hits chart, hover a Block % for damage-taken-vs-successful-blocks. Both are cumulative over the match, sampled every 3 seconds.
- **Point markers on every match graph.** FPS, Ping, Hit % and Block % hover graphs now show a vertical marker at each point scored — green when you took the point, red when the opponent did — so you can line a bad stretch up against the scoreboard.
- **Disconnect banner (bug #81).** When anyone disconnects or quits mid-game — casual, ranked, 2v2 or 1v2 — every remaining player gets a top-of-screen banner naming who left, on the spot. Between games of an unfinished series it shows an orange "left — series unfinished (1-0)" variant, and if the player left to join a ranked match it says exactly that. In 1v1 you also get an immediate note telling you whether leaving gives you the win or voids the game (the old message only appeared after you quit out yourself).
- **Game ID buttons.** Every recorded game now has a tiny ID button (My Stats history rows) or click-to-copy row (2v2 Recent Series games) that copies a short game code — paste it into `/game` in Discord to pull up that game's full breakdown.
- **2v2 Recent Series telemetry.** Game rows now show each player's FPS / ping / Hit % / Block % line, and hovering a player pops a 4-panel mini dashboard (FPS, ping, shots-vs-hits, damage-vs-blocks). Also: the top-left player name no longer crowds the "Game N:" line.
- **1v2 Solo Extra Initial Pick is live in-game** — when the lobby had the toggle on, the solo's first card screen deals twice. (First-playtest-pending: the mechanism is vanilla's own multi-pick loop, but online multi-pick has never run in the wild.)
- **1v2 leaderboard W/L split** — solo record and duo record shown separately (orange solo 3W-1L / blue duo 2W-4L) instead of one combined tally.
- **Achievements earner lists**: now sized to their content (no more giant empty box on a 0-1 earner achievement), show 20 earners per page with a pager for the rest.
- **Leaderboard search** — a search box under the Leaderboard/Compare sub-tabs filters the board as you type (typing "t" no longer opens chat, same guard as the Compare search).
- **Discord on profiles (opt-out)**: linked players' "Discord: @displayname" shows on their leaderboard detail panel (above the Mod line) by default; a Settings toggle "Show Discord on leaderboard" turns it off.
- **Home tab Discord Link** now shows your actual Discord username (the unique @handle), not your display name; falls back to the account ID. Still click-to-reveal.

### Server
- **1v2 fixes from the July 22 forensics pass**: the janitor's status-spelling mismatch that made canceled locks invisible to the continuation lookup (unrecorded-games risk, bug #70 family); abandoned mid-series 1v2 rows now close after 24h instead of staying "active" forever; a stale-husk guard on the continuation lookup (6h activity window); series slot columns realign to the in-game truth on the first reported match (protects per-slot rewards + future ranked replay).
- **Achievements**: the earner list now resolves dynamic titles (Sid's "1st Place" podium title was silently dropped — string/UUID key mismatch), reports the true total, and serves up to 500 earners.
- **Game lookup**: `GET /matches/by-code/{code}` — full per-game detail (both/all players' stats, timelines, cards, rewards) for the Discord bot, across 1v1/2v2/1v2.
- **2v2 telemetry**: per-player FPS/ping/hit/block timelines + counters stored per game (new `team_match_telemetry` table) and served in the series feed.
- **Discord identity split**: `discord_username` now holds the real @handle, new `discord_display_name` holds the display name, plus the opt-in `show_discord` flag gating third-party visibility.
- Migrations: 141 (hit/block timelines + point times), 142 (team match telemetry), 143 (game-code indexes), 144 (discord display/show), 145 (ovt status data-fix).

### Discord bot
- **`/game <code>`** — paste a game ID copied in-game to get the full breakdown: score, per-player Hit %/Block %, FPS and ping (with graphs), cards, and gold/XP/Elo changes. (Feedback fixes: the score-progression graph reads in rounds, not doubled points, and a game with no recorded picks for a side now says so explicitly instead of dropping the field.)
- **`!link` now stores both your @username and display name**, existing links are re-resolved on the next bot restart, and renames are tracked automatically by the half-hour role sync.

### Server
- Migration 146 flips `show_discord` to opt-out (default TRUE); recent-joins queue endpoints carry the searcher's Discord display name (gated on the opt-out).

## v1.34.0 — 2026-07-22 — July 20-22 mega-batch

### Client (mod)
- **Accuracy & block counters restarted.** Hit % and Block % lifetime totals were reset to zero because the way they're counted changed this release (below) and old mixed-era totals couldn't be corrected per game. They rebuild cleanly from your next games on 1.34.0. If your Hit/Block shows "-" for a bit, that's why.
- **Block % counting reworked** to the community-agreed rule: only your **right-click blocks** count. One right-click is one activation, and if that block (or its Echo / Shield Charge follow-ups) stops a bullet it counts as one success — so blocking is never over 100%. Passive auto-blocks (Abyssal Countdown, Shields Up, etc.) don't count toward the stat at all.
- **Hit % kill-shot fix (finishing bugs #77/#80).** The round-ending kill shot was being dropped from your hit count, so high-damage builds (Careful Planning, Wind Up + Poison) could read absurdly low. Kill shots now count. Reload-spam clicks and card-spawned projectiles (EMP rings, etc.) no longer inflate your shots-fired.
- **FPS & Latency in match history.** Ranked/Casual history rows now show both players' **FPS** and **Ping** (you / opponent). Hover the FPS number for a graph of frame-rate over the match; hover Ping for a graph of latency over the match. Handy for seeing whether a rough game was a real connection issue.
- **Game-streak vs series-streak.** My Stats now shows both your ranked **game** streak and your **series** streak, each with its own Best, clearly labeled (they used to be mixed on one line).
- **Rating History graph upgrade.** The leaderboard rating graph now spans the full panel, is taller, and has fixed reference lines at 1500 / 1600 / 1800 / 2000 / 2400 so you can read a player's tier at a glance. "Ranked:" record is now labeled "Ranked (series):".
- **Achievements tab overhaul.** Sortable (Default / Rarity / Gold / Date earned — click again to reverse), the gold reward shows on every achievement even before you earn it, and clicking an achievement expands an inline list right under it of everyone who's earned it, in the order they got it, with their titles.
- **RLFP Ping button** (top bar, between Search Ranked and Enable/Disable): pings the Ranked Looking For Player role in Discord with an optional message and an expiry (15m / 30m / 1h / 3h) so people can find you a ranked game even when your game's closed. Requires a linked Discord + ranked enabled; once per hour.
- **Chromatic aberration toggle** in Settings — turn off the RGB color-fringing for crisper edges and a tiny FPS gain.
- **Body-color shop previews**: each Body Color now shows a little character-shaped color swatch so you can see the real color, not just the name.
- **Popup fixes**: on-screen messages no longer get clipped or vanish too fast, and achievement-unlock popups now show the requirement.
- **Casual-downgrade notice** now fires reliably when your opponent has ranked disabled or isn't running the mod, so you always know a game recorded casual before investing 10 minutes.
- **Matchmaking "Press Jump to Join" — mitigation (NOT confirmed fixed).** Added a fast detector that, when the dead-connection state is hit, restarts and drops you back into the quickplay queue automatically instead of stranding you on a dead screen, plus a guard for the underlying vanilla race. This still needs live verification — if you hit the dead screen again, please file a bug report with the log.
- **Account verification (opt-in, staged).** The mod now proves Steam ownership to the server via a Steam auth ticket, closing the door on someone using the mod under a Steam ID that isn't theirs. Rolls out in log-only mode first.

### Server
- **Ranked series never expire.** An unfinished series now resumes whenever you next play that person, no matter how long later — so leaving mid-series can't save your rating. 52 old unfinished series were reattached. FAQ wording updated.
- **Casual games no longer create phantom ranked series** (bug #78): a game against someone registered but not currently running the mod was being upgraded to a ranked series server-side. Fixed to require the opponent's mod to actually be live; the stray series was cleaned up.
- **Opponent-tier gold & XP.** Ranked rewards now scale by your opponent's rank tier — Beginner ×1 up to Grand Master ×3 — on both gold **and** XP, win or lose. Winning a series doubles the series reward, and beating a current top-3 player doubles it again. Series losers now earn tier-scaled gold too. Level-up gold and the correct series gold now show in match history (previously under-reported).
- **Achievement gold retiered** per difficulty (500 / 300 / 1000 tiers) with everyone's existing earns back-paid the difference.
- **Sync tournament timing.** Force-start now schedules 10 minutes out through the normal notification flow (lock DM, countdown, banner) instead of starting instantly with no warning; stale-vote window tightened; a crash mid-BO3 no longer forfeits you out of the whole bracket, and an abandoned match can't wedge the tournament forever.
- **Expanded match-review tools for admins**: additional per-match connection/performance signals (FPS/latency/freeze/heartbeat) recorded for admin review, with per-player baselines so consistent conditions aren't flagged.

### v1.33.1 (rolled into this release) — bug reports 77-80
- #77 / #80: hit-count kill-shot fix (see above).
- #78: casual phantom-series fix (see above).
- #79: matchmaking "Press Jump to Join" mitigation (see above — not confirmed fixed).

---

*Older releases (v1.33.0 and earlier - the betting system, chat bridge, tournaments, cosmetics, and the road to here) are in the full changelog on GitHub: https://github.com/SidNDeed/SidsCompetitiveRounds/blob/main/docs/CHANGELOG.md*
