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

## v1.33.0 — RELEASED 2026-07-17 — July 17 mega-batch (rounds 1-3)

### Round 3 (Sid's 10 items + first 1v2 forensics)

### Client (mod)
- **My Stats casual record fixed (item 8)**: the Record block recomputed casual W/L (and sweeps) by scanning the locally cached history — which v1.32.1's lazy loading truncated to the head 400 matches, so lifetime losses "vanished". Both lines now use the server's lifetime fields (`casual_wins/losses`, `sweeps_given/taken`); current-streak calcs stay window-based by design.
- **Hit % undercount fixed (bug #77, Stan)**: the round-winning kill blow was dropped from `bullets_hit` — vanilla processes the lethal hit → round over → pick phase (flipping our phase flag) all before the counter's Postfix ran, so the pick-phase guard ate exactly one hit per round won, matching Stan's manual counts. Guard removed for hits (nothing can be fired during pick anyway); budget-exhausted drops now log `[HIT-DROP]`.
- **2v2 tab scroll bounce fixed (bug #76, Sid)**: the leaderboard's inner ScrollRect consumed wheel events even with nothing to scroll (elastic bounce), starving the tab's outer scroll. The inner scroll now disables itself while its content fits its viewport (wheel bubbles to the tab scroll) and re-enables when the board genuinely needs it.
- **1v2 phantom series plugged**: both 1v1 series-preflight sites now exclude `ovt_` rooms — the July 17 first live 1v2 session spawned six phantom 1v1 `ranked_series` rows pairing arbitrary trio members (the one 1v1 path the #146/#149 gate sweep missed).
- **Admin Steam ID (item 10)**: leaderboard click-a-player detail shows the player's Steam ID to admins only, click-to-copy (first `systemCopyBuffer` use).
- **Twins! (item 3)** added to the client achievement list.

### Server (to deploy — no new migration required beyond 133)
- **Twins! achievement (item 3)**: granted server-side to BOTH players when a game ends with identical 5-card multisets (duplicates counted; names normalized). 100g standard. Migration `133` backfills it retroactively from `match_cards` (same pattern as 113).
- **Sync lock timing (item 9)**: `LOCK_OFFSET_HOURS` 6 → 48 — the winning time is now decided **2 days before the default start**, and only slots ≥ ~24h after the decision can win, so every player gets at least a day's notice of the final time. Availability-check DMs re-anchored to 24-96h **before lock** (they must be answerable before the time is decided); the sync availability embed now names the lock moment and points at the vote; pushback derives the next lock from the new default (a late tick can't erode the offset); tournament creation requires lock ≥ 72h out (sometimes skipping to the Saturday after next).
- **1v2 janitor**: ovt husk queue rows and zero-game dead locks were only cleaned by poll-driven paths — with no 1v2 pollers, the July 17 leftovers dangled for 9+ hours. The periodic queue-cleanup loop now sweeps them (30-min windows, wide per learning #150 so a live game 1 can't be hit).

### Round 2 (Sid's 4 items)

### Client (mod)
- **Custom cosmetics now shade with the scene (item 1)**: our face items rendered with Unity's default unlit sprite material while everything else in ROUNDS multiplies through the SFSS lightmap — so they sat at raw PNG brightness against a lighting-darkened scene (Galaxyice's cat "too bright, green eyes invisible"). Templates now adopt the vanilla item material (lazily borrowed from a vanilla face item; startup log verifies `shader=Sprites/SFSoftShadow`), so custom items darken/tint exactly like vanilla ones on every map skin, vanilla art, and the lighting-off perf mode.
- **Tournament tab layout (item 2)**: the "Default start / Signups close" line no longer paints over the instructions (its LayoutElement now sizes to the wrapped text), and the 8 time slots render in two columns of 4. Prizes moved out of the static text into a live block. Instruction text refreshed: "have ROUNDS open" (not "keep this tab open"), couple-of-hours expectation, break/Play Now explanation, 5/10-min show-up windows, dropped the stale "cancelled under 8".
- **Between-matches UX (item 2)**: my-match panel shows the break countdown + a **Play Now (skip break)** button; a slim in-game banner shows "Next match vs X in M:SS" during breaks.
- **Tab scoreboard styled names fixed (item 4)**: rainbow/gradient nametags write per-char rich-text into Photon NickName; the Tab overlay truncated that markup mid-tag (broken literal tag, zero real characters). It now strips styling via `NametagStyler.Clean` before the 16-char truncation — full name, team-tint preserved.

### Server (to deploy — migration `132`, then API+bot)
- **Prizes scale with players (item 2)**: base = 8 players at DOUBLE the old 16-player tier (1st 1000g/5000xp, 2nd 600g/3000xp, 3rd 120g/150xp), growing linearly to 2x base at 16. Confirmed count snapshotted at lock (`tournaments.prize_player_count`); `_prize_amounts()` is the single source of truth — /current and /internal/watch carry computed numbers to the client and bot. Sync and async both.
- **Between-rounds breaks (item 2)**: sync matches after round 1 enter `status='scheduled'` with a 7-min `scheduled_ready_at`; the no-show clock only starts when the match flips to `ready` (break can never forfeit anyone). New `POST /tournaments/{id}/matches/{mid}/play-now` — both players pressing it skips the break (row-locked against the simultaneous-press race). Round-flow facts, verified: round 2 otherwise activates the instant both prereq matches resolve; previously the only gap was the 30s tick.
- Migration `132` — `prize_player_count`, `scheduled_ready_at`, `early_ok_signup_ids`.
- Migration `130` reworked per Sid's call (was: silently seed default-time votes): now DMs existing voteless sync signups via `pending_dms` telling them to pick their times or be removed at lock, including the couple-of-hours heads-up.

### Discord bot
- **Break DM (item 2)**: when a next-round match schedules, both players get "Next up: vs X (round N). Starts <t:..:R>" with the live Discord countdown + the Play Now instructions.
- **Prize displays are dynamic**: completion announcement and the tournament board embed use server-computed amounts; the board shows "Every signup past 8 grows the pot — 16 players doubles it!" during voting. Lock DM now says to plan for a couple of hours + mentions the skippable breaks. FAQ tournaments entry updated (agreement lock, prize scaling, ~2 hours).

### Adversarial review pass (round 2 — 4 finder angles, per-finding verify, 28 agents)
Confirmed and fixed before anything shipped:
- **Queue/casual games during a break would have counted as tournament games** — the series row exists 7+ min before play and `_find_current_active_series` matched tournament series in ANY room, so two opponents passing the break in the 1v1 queue would advance the bracket off warmup games. Sync tournament series now only bind in their designated `sct-` room (async unchanged — any private lobby is its design), and queue join 409s while you have a sync match scheduled/ready.
- **Players in a break read as "eliminated"** (and a bracket-reset GF read the LB champ as CHAMPION early) — `_compute_progress_labels` didn't know the `scheduled` state.
- **/dm-opponent and /opp-online failed during the break** — exactly when the break DM tells players to coordinate Play Now.
- **Bye-seeded top players' first match got a break** — a bye-fed W R2 at tournament start now goes straight to ready; the break only applies downstream of an actually-played match.
- **Two-column slot labels overflowed their 158px cells** once tallies became public — labels drop the tz suffix (named in the row above), tallies compact to "(N)", wrap off, and fully-empty rows collapse.
- **"best time: N/8" could count votes on dead slots** — the /current tally now filters to future slots like the lock does.
- **"Prizes at 0 players"** on the board pre-signups — display floored at 8.
- Old-client signup 400 now tells the player to update the mod; lock DM grace wording matches the real 5/10-min windows.

### Round 1 (Sid's 7 items)

### Client (mod)
- **T-chat popup fixed (item 7)**: every line now renders at its measured wrapped height — no more clipped letters on the bottom row, and long messages show up to 3 wrapped lines ending in an explicit `... [see F5]` indicator instead of silently cutting mid-sentence. The backdrop grows to match.
- **Artist tab sales log (item 1)**: new scrollable "Sales log" section — every purchase and gift of your items, newest first, with buyer, price paid, and your 30% cut per sale.
- **Home tab cosmetics showcase (item 4)**: art doubled 38→76px, text 14→17pt, rows now scroll, and the list covers the last TWO cosmetic-update days (dates named in the caption and per row).
- **Sync tournament voting is now mandatory (item 3)**: the time slots are pickable before signup and at least one is required to sign up (the vote rides the signup request); the header shows live "best time: N/8 agreed" progress. Save Votes still adjusts an existing signup.
- **Sprout uses lopidav's original art (item 5)** — byte-for-byte his file, replacing the recreation that shipped with v1.30.
- **Two Galaxyice cosmetics (item 6)**: Rounds Cat (static head-rider) and Star Spin — the first community-artist animated item (6-frame orbit, ~1s per lap).

### Server (to deploy — migrations `128`-`131`, then API+bot)
- **Chat flood control (item 7)**: WS chat now enforces 5 messages / 10s per sender plus an identical-message filter (20s window). Silent drops, checked before any DB work.
- `GET /artist/{id}/sales` — per-purchase log (buyer, price, per-sale royalty, date), newest first.
- `GET /shop/newest?batches=N` — restricts the newest-cosmetics list to the N most recent update days; entries now carry an `added` date.
- **Sync tournament lock rework (item 3)**: signup requires ≥1 valid time-slot vote (recorded in the same transaction); the lock now requires `min_players` (8) votes agreeing on ONE slot — otherwise the whole tournament pushes back a week (feed post says why); when it locks, the agreed slot becomes the start time and every signup that didn't vote for it is removed, no penalty, with a feed post naming them. Force-start (everyone votes "now") bypasses the gate.
- **`pending_dms` queue (migration `129`)** — generic one-off bot DM queue with the durable ack pattern; seeded with a DM to lopidav about the Sprout art fix.
- Migration `128_galaxyice_cosmetics.sql` — Galaxyice artist role + both shop rows (born out-of-stock until the artist opens sales).

### Discord bot
- **New FAQ entries (item 2)**: hosting & netcode ("is orange the host", "is it peer to peer", "does hosting matter" — ROUNDS runs through Photon relays, no host advantage) and a dedicated blocking-tips entry; "how does the comp mod work" now routes to the what-is-this-mod answer.
- **`pending_dms` drain loop** — own fully-guarded 60s loop; DMs the linked player, acks delivered/undeliverable; unparseable discord_ids flag undeliverable instead of poisoning the LIMIT-20 window.

### Adversarial review pass (8-angle, pre-ship)
The self-review on this batch surfaced and fixed, before anything shipped:
- **Past slots could win the vote** — the earliest offered slots are already past at lock time (lock is default-6h, slots span default-24h..+18h); a popular past slot would have set the start time in the past, started the tournament within 30s, and mass no-show-forfeited the field. Lock tally now only counts slots ≥30 min in the future; signup/Save-Votes reject past slots; the client is only offered future slots.
- **Pushback stranded every vote** — the +7d pushback regenerated all 8 slots while votes stayed pinned to the old timestamps, so carried signups could never re-aggregate (perpetual pushback) or got kicked wholesale next lock. Votes now translate +7d with the grid, and the pushback post says so.
- **Legacy signups would have been kicked at the first post-deploy lock** — anyone signed up under optional voting has zero vote rows. Migration `130` seeds them with the default start time (the time they implicitly agreed to).
- **Tallies were hidden pre-vote** — the old anti-snoop gate starved exactly the pre-signup players who now need to see which time is winning. Tallies are public during voting.
- **Save Votes could self-kick** — clearing every checkbox deleted all votes and earned a silent kick at lock; the shared validate+replace helper (one write path for signup AND /time-vote) rejects empty sets, past slots, and duplicate slots (which previously 500'd on the PK).
- **Re-signup silently dropped votes** — an already-signed-up client re-posting signup got a 200 while its slot picks were discarded; votes on the request are now recorded.
- **Kicked players now get a direct DM** (via `pending_dms`) — they're exactly the cohort not watching the tab; a channel post alone would never reach them.
- **Chat flood gate re-keyed to the connection** — keying by the client-supplied steam_id was spoofable per message; the dup filter now skips short lines ("gg" after each game is legit) and the bucket sweep is time-gated.
- **Stale client vote-state reset** — checkbox picks are index-based; when the offered slots change (pushback/new week) frozen local edits now reset instead of silently retargeting onto different datetimes.
- **Artist-item batch dates** — migration `131` adds `shop_items.released_at`, stamped when an artist first opens sales, so born-out-of-stock items land in the Home showcase under the day they became buyable (the Galaxyice debut would otherwise have aged out before ever appearing).
- Perf: chat overlay layout scratch buffer (no per-OnGUI allocation), animated-thumbnail ticker skips ~94% of redundant reflection sets, chat-gate prune is time-gated.

# Changelog

## v1.32.1 — RELEASED 2026-07-16

**Headline: a new Home landing tab + a FAQ auto-responder bot.**

### Home tab
The F5 menu now opens on a **Home** splash page:
- **Latest Releases** — reads the #scr-releases channel live, so you see update notes the moment they're posted.
- **Newest Cosmetics** — with real art thumbnails, animated frames included.
- **Players** — who's online now and recently online, with titles and ratings. Hide yourself via **Settings → Appear offline**.
- The **Discord Link** panel and **chat** moved here from My Stats.

### Discord FAQ bot
A new bot auto-answers common questions (how to play ranked, the modpack code, gambling, the economy, tournaments, becoming an artist, rank thresholds, and more) — in Discord server-wide AND in the in-game chat bridge. Ask in your own words. `/faq` lists every topic; it also does a live "how much elo vs @player" calculation and names the current top player.

### /compare
- **First / Prev / Next / Last** buttons page through every mutual game.
- New **head-to-head top cards** section — each player's most-picked cards against the other.

### My Stats
- **History lazy-loads** so the page opens fast; pages fill in as you scroll, full page count still shown.
- **Card Stats** and **Achievements** are now sub-tabs under My Stats.

### Fixes
- **Chat T-key** no longer disables itself after you use the in-game text chat (proper root-cause fix).

## v1.32.0 — RELEASED 2026-07-14

**Headline: the July 14 feature batch** — podium presence everywhere (top-3 leaderboard highlights + a dynamic sparkling 1st/2nd/3rd Place title + 3x XP for beating a podium holder), 1000g slayer achievements with back-pay, tournament Discord feeds + availability-check DMs with Yes/No buttons, four new FPS/accessibility settings, a reordered shop, and a big Discord bot expansion (reworked /rank + /stats, /mystats, /cards, /graph charts, head-to-head /compare, 50-row leaderboard, live tournament board).

### Client (mod)
- **Leaderboard podium highlights** — ranks 1-3 get persistent gold/silver/bronze row tints on the 1v1 board (click-select still overrides); 2v2 rank numbers and 1v2 rank tags read gold/silver/bronze too.
- **Podium title sparkle** — "1st/2nd/3rd Place" titles render with per-character glitter that shimmers on the leaderboard (only the podium rows repaint on a 0.7s tick — never a full-board repaint) and glitters statically in match history / 2v2 lists.
- **Four new Settings toggles** (standalone — not under the perf master): Screen shake (Harmony block at the Screenshaker receivers, local-only), Map lighting (full-bright, skips the whole SFSS lightmap pass), Map shadows (skips the shadow render pass, lighting stays), Animated cosmetics (freezes prismatic/chrome body colors, prism trail, map-skin shimmer, animated faces, and shop thumbnails to a static frame instantly — frozen clocks, never paused particles).
- **Shop reordered** — tabs and All-tab sections now run Cosmetics → Name Styles → Maps → Titles → Trails → Body Color → Cursor → Effects → Other.
- **Tournaments tab** — the Voting / Signups Open block reads bigger (state 24pt, times 17pt, instructions 14pt).
- **Achievements** — "Unkillable" renamed to **"God Build"**; the tab now shows the real per-trophy gold (+1000g on the slayers).
- Stale "Ranked x1.2" XP-toast label fixed to x1.5; new "Top 3 x3" label.

### Server (to deploy)
- **Slayer achievements pay 1000g** (per-key override; the unlock endpoint, inline grants, and admin grants all honor it) — migration `123` back-pays every existing earner to exactly 1000g per slayer trophy (computed delta per player; prod ledger was uneven — some earners were never paid at all by the 102 backfill).
- **Top-3 XP multiplier** — beating a CURRENT top-3 leaderboard player now triples match XP (replaces the flat +150 for those wins; top-4/5 keeps +150). Podium set matches the visible board (min_matches=1, deleted_at filtered) on a 60s cache.
- **Dynamic 'Podium' title** (`title_podium`, migration `123`) — resolves live to 1st/2nd/3rd Place in gold/silver/bronze at every render surface (leaderboards, match history, chat, 2v2, stats) and disappears entirely below 3rd; ownership auto-granted on entering the podium, never revoked. **En-route fix: achievement-unlocked titles (Sid Slayer / Stan Slayer) had NO equip surface since v1.29** — /shop/items now lists achievement-pool items you own, so all of them are finally equippable.
- **Tournament Discord feed** — signup/leave posts with live counts + Discord-localized times, @-mention posts on quorum reached, pushback, and vote-moved start times (rides the acked channel-post bus).
- **Availability-check DMs** (migration `124`) — 24-96h before a viable tournament, every confirmed signup gets a DM with Yes / No-remove-me buttons (restart-safe; No calls the real unsignup). Sync DMs restate the "just have ROUNDS open at the start time" contract; async DMs explain the 7-day-deadline scheduling so nobody thinks they need fixed availability. Pushbacks reset the notices so the new date gets a fresh ask.
- Hardening: the client unlock endpoint now only accepts the 14 client-detected achievement keys (server-granted trophies can no longer be self-awarded), and a lean `/players/{id}/rating-history` endpoint feeds bot charts without the heavy stats query.

### Discord bot
- **/rank reworked** (ranked-only: rating/RD/peak, tier, series record, live streak, position, leave rate) and **/stats reworked** (general: totals, casual, level/XP, gold — hidden when hide_gold — hit%/block%, top cards, 2v2, FPS). Fixed en route: /stats top cards had been silently empty (read fields the API never served).
- **New commands**: /mystats (the F5 page as an embed), /cards [player] [ranked|casual|all], /compare (2-4 players' ranked rating histories overlaid on a rendered chart, client-convention 1500 baseline).
- **/lb shows 100 players per page** (multi-embed) and the channel board carries all 100 in one living message.
- **Live tournament board** in scr-tournaments — one bottom-anchored living message with Sync + Async status, rosters, bracket progress, and podiums, updating every 2 min.
- Availability-DM poller with server-side acks; channel posts now ping user mentions explicitly (and can never @everyone).

### Adversarial review (27 agents, 6 dimensions): 21 raised / 18 confirmed (7 distinct) / 3 refuted — all fixed pre-ship
- *(critical)* the availability-DM pipeline was dead on arrival: the bot read notice key `id` but the server serialized `notice_id` — every notice silently skipped, never acked, queue starved at 20 rows.
- *(high)* the podium query filtered ≥5 counted matches while every visible board passes min_matches=1 — the sparkling title and x3 XP could attach to the player displayed at #4.
- *(medium)* locked-phase leave posts announced the pre-vote default start time; pushed-back tournaments could never re-ask availability (unique-row dedup); the tournament board could exceed Discord's 6000-char message budget and freeze; concurrent /compare renders raced pyplot's global state; the slayer 1000g was reachable through the client-HMAC unlock endpoint.

### Post-deploy feedback round (July 14, same day)
- **Leaderboard title brackets** now take the title's color instead of inheriting the local player's green name color; **podium rows (1-3) get a thin dark SDF outline** on every cell so the pale rank-colored ratings stay readable over the gold/silver/bronze tints. Podium highlight alphas halved (were too strong behind text).
- **/lb fixed**: showed 100/page but truncated mid-row around #67, and page 2 started at #201. Root cause was a server double-add of the page offset onto an already-absolute `ROW_NUMBER()` rank (fixed server-side); page size set to 50 for the command and the channel board, no mid-row truncation, board covers all ranked players.
- **/compare reworked to head-to-head** (exactly 2 players: overall record, ranked/casual/series split, recent mutual games with each side's cards) and the multi-player Compare-tab charts moved to **/graph** (16 metrics: elo-over-time, hit/block %, cards-per-game, FPS, peak, XP, achievements, streaks, sweeps, bets, keys, game length, 2v2, top-cards, region pies).
- **scr-tournaments board** now carries a "How it works" field per embed explaining sync (one sitting, ROUNDS open at start) vs async (7-day per-match deadlines, self-scheduled).

### Known limitation
- **"Disable map lighting" flattens the sky.** ROUNDS composes the scene as sprites × lightmap and the per-map sky color IS the lighting (the raw backdrop sprite is a fixed dark texture), so turning lighting off cannot preserve the colored sky. The toggle paints a flat slate backdrop, but on several default (non-custom-skin) maps the vanilla backdrop still reads dark/purple-tinted — the flat paint reaches `ArtHandler.m_background` but not every default map's backdrop source. Shipped as-is (opt-in, off by default); **"Disable map shadows" is the recommended perf toggle** — it's where the cost is and it keeps the scene fully lit and correct. A proper lighting-off backdrop fix is on the TODO.

### Migrations (applied to prod 2026-07-14)
- `123_slayer_gold_and_podium_title.sql` — slayer top-up (regicide 4 earners/3875g, stan_slayer 3/2900g) + Podium title seed (idempotent, re-run safe).
- `124_tournament_notices.sql` — availability-DM queue table.

---

*Older releases (v1.31.0 and earlier - the betting system, chat bridge, tournaments, cosmetics, and the road to here) are in the full changelog on GitHub: https://github.com/SidNDeed/SidsCompetitiveRounds/blob/main/docs/CHANGELOG.md*
