# Sid's Competitive Rounds — Changelog

## v1.25.11 — 2v2 reporting + assembly-failure handling

Internal-facing release — addresses two issues from v1.25.10 testing.

### 2v2 reporting fix
Games were logging in My Stats as casual 1v1 matches instead of the 2v2 channel.
- **Root cause A:** `matchIsRanked` was using 1v1 logic — it set `matchIsRanked = RankedEnabled && opponentIsRanked && OpponentHasMod()`, where `opponentIsRanked` is per-single-opponent. In 2v2 with 3 other players the first opponent's `/mod/check` could race and flip the whole match to casual. Fix: in `cr_ff` rooms, force `matchIsRanked = true` (it's a queue-issued team room — definitionally ranked).
- **Root cause B:** `TryReportTeamMatch` was returning false silently at one of `pm == null`, `pm.players == null`, or `teamFieldInfo == null`, with no log line, so the routing fell through to the 1v1 path. Added explicit `[2v2-REPORT]` warnings on every silent return-false so the next failure is diagnosable.

### Match-assembly failure handling
v1.25.10 testing reproduced a case where 4 players ready up but only 3 join the Photon room, then sit on the ready screen for 30s waiting for our force-StartGame timeout to give up. Now:
- New `team_series.spawn_confirmations` counter (migration `059_team_series_spawn_confirmations.sql`).
- New `POST /team/series/{id}/spawn-confirm` endpoint — each client posts when its 2v2 auto-spawn override successfully creates the local Player. Idempotent per (series, player) via a JSONB membership check.
- New `GET /team/series/{id}/state` endpoint — when polled, lazily auto-cancels the series if `now() - created_at > 15s` AND `spawn_confirmations < 4` (sets `status='canceled'`, `invalidation_reason='assembly_timeout'`).
- Client polls the state endpoint every 2s for the first 22s after joining a `cr_ff` room. When it sees `canceled / assembly_timeout`, shows "Match couldn't assemble — only X of 4 connected. Returning to menu" and leaves the room.

Scoped to `cr_ff` rooms only — 1v1 ranked, tournaments, and private rooms unaffected.

## v1.25.10 — 2v2 continue + color fixes

Internal-facing release — second 2v2 testing session surfaced three issues. All three addressed root-cause.

- **Continue popup auto-confirms in 2v2 rooms.** Vanilla `PopUpHandler.StartPicking` waits for any local-mine player to press Jump on a Yes/No selector — there's no network sync of the choice, each client decides independently. In 2v2 this broke: when 2 of 4 hit Yes, those clients ran `DoContinue` and started the next-round transition while the other 2 were still stuck on the popup, couldn't input cards, and the room desynced. Now in `cr_ff` rooms the Prefix invokes the supplied callback with `Yes` immediately and skips the picker — all 4 clients call `DoContinue` simultaneously. Players who don't want to continue can DC during the next card-pick (the report path treats DC there as a normal forfeit).
- **Local player skin renders correct team color.** Root cause for "I was team orange, my teammate was blue": `PlayerSkinHandler.Init()` reads `data.player.PlayerID` and bakes a skin GameObject during `PhotonNetwork.Instantiate`, which runs *before* our `AssignPlayerID` call lands. So local players always rendered with skin index 0 (orange) regardless of slot. Remote `Player.Start.ReadPlayerID` sets it correctly, which is why the teammate was rendered with the right (blue) color from the user's perspective — local was wrong, remote was right. Fix: in the `CreatePlayer` override, after `AssignPlayerID`, destroy the wrongly-baked skin children and re-call `Init` via reflection so the skin GameObject is rebuilt with the correct PlayerID.
- **Aggressive PlayerColorCosmetic reapply for late joiners.** Photon's `OnPlayerPropertiesUpdate` callback fires only on prop UPDATES — but late joiners receive the room's existing player props at join time without an update event, so the cosmetic apply path is never triggered for them. Result: some clients saw other players' custom body colors as "white" (color hex defaulted to white because the prop wasn't in the local cache when `DelayedApplyAll` ran) or as a stale prismatic frame. New 12s polling loop calls `PlayerColorCosmetic.ReapplyForActor` for every non-local actor every 2s after `cr_ff` room join — catches late prop arrivals and gets the animation tick state initialized for animated SKUs.
- **`[2v2-COLOR]` diagnostics.** Logs every distinct (original→mapped) `PlayerSkinBank.GetPlayerSkinColors` lookup once per 5s — confirms when/whether the team-color normalization patch is actually firing.

Scoped to `cr_ff` rooms only — 1v1 ranked, tournaments, and private rooms unaffected.

## v1.25.9 — 2v2 polish pass

Internal-facing release — first 4-player attempt with v1.25.8 reached gameplay successfully. This pass cleans up the rough edges that surfaced.

- **Cleared the giant "Searching" overlay for late joiners.** Vanilla `RPCA_FoundGame` is what calls `LoadingScreen.StopLoading()` (kills the searching particle systems + sets `m_isLoading=false`). With `RpcTarget.All` instead of `AllBuffered`, players 3 and 4 miss it. Now we manually clear `m_isLoading`, stop the searching/match-found systems, and hide the cancel-text on `cr_ff` room join.
- **Spawn positions sorted by team.** `PlayerManager.MovePlayers` indexes `spawnPoints[i]` for `players[i]`, but the SpawnPoint child order in map prefabs isn't guaranteed left-to-right. Now `MapManager.GetSpawnPoints` is sorted by `localStartPos.x` ascending in `cr_ff` rooms — slots 0/1 (team 0) land left, slots 2/3 (team 1) land right.
- **Default team colors share within team.** `PlayerSkinBank.GetPlayerSkinColors(playerID)` returns a different color per slot in vanilla. In `cr_ff` rooms the playerID is normalized to `(playerID/2)*2` so both team-0 players look orange and both team-1 players look blue. Custom Body Color cosmetic still overrides on top.
- **Card bars extended to 4 players.** Vanilla `CardBarHandler` only has 2 CardBars (`cardBars[0]` = team 0, `cardBars[1]` = team 1). Vanilla `AddCard(int teamId, ...)` is called with `PlayerID` at the call site, so PlayerID 2/3 picks hit IndexOutOfRange and disappeared. Now in `cr_ff` rooms we either activate inactive prefab CardBars (if 4 exist) or clone bars 0 and 1 with a vertical offset. Result: each of the 4 players gets their own visible card-pick bar.
- **One-leaves-all-leave on disconnect.** Removed the `cr_ff` `OnPlayerLeftRoom` cascade-DC suppress (added in v1.25.5 to mitigate the spawn race, which is now fixed). Vanilla's cascade now fires when any player leaves a 2v2 room — the remaining 3 return to menu instead of sitting forever.
- **2v2 reporting routing diagnostics.** Added `[2v2-REPORT-ROUTE]` log line on every match-end naming `shouldReport`, `ActiveTeamSeriesId`, `PlayerList.Length`, and the room's `cr_ff` flag. Plus a `FELL THROUGH to 1v1 path despite 2v2 signals` warning if any of those are set but routing skipped — caught the v1.25.8 case where games were reporting as 1v1.

Scoped to `cr_ff` rooms only — 1v1 ranked, tournaments, and private rooms unaffected.

## v1.25.8 — 2v2 GM_ArmsRace activation for late joiners

Internal-facing release — root-cause fix for the 4-player kick-out bug found via v1.25.7 diagnostics.

- **Force-activate `GM_ArmsRace.gameObject` for late joiners.** The diagnostics in v1.25.7 caught the smoking gun: `NetworkConnectionHandler.Update` was calling `PlayOnBestActiveRegion()` → `PhotonNetwork.LeaveRoom()` ~10 seconds after spawning. Root cause: vanilla `NCH.OnPlayerEnteredRoom` fires `RPCA_FoundGame` with `RpcTarget.All` (not `AllBuffered`) when `PlayerList.Length == MAX_PLAYERS` (a vanilla const = 2). That RPC is the *only* path to `LoadingScreen.StopLoading()` → `gameMode.SetActive(true)` → `GM_ArmsRace` activated. In a 4-player room, the master fires the RPC the moment player #2 joins; players 3 & 4 (joining later) miss the broadcast forever, so their `GM_ArmsRace.gameObject` never activates. With `GM_ArmsRace.instance == null`, NCH.Update's `untilTryOtherRegionCounter` timer (gated on `!GM_ArmsRace.instance`) decrements every frame → eventually triggers `PlayOnBestActiveRegion`, which leaves the team room and tries other regions. Plus `GM_ArmsRace.PlayerJoined` (the handler that counts spawned players and calls `StartGame` at 4) is subscribed to `PlayerManager.PlayerJoinedAction` in `OnEnable`, so without an active GM the count never registers either. Fix: manually `SetActive(true)` on the inactive `GM_ArmsRace.gameObject` in our `OnJoinedRoom` Photon callback for `cr_ff` rooms — fires before any remote `Player.Start` events, so `PlayerJoined` subscriptions are in place when the spawns broadcast in. Idempotent for early joiners (vanilla activates first; our SetActive is a no-op).
- **Belt-and-suspenders `StartGame` fallback.** A polling coroutine kicks off at room join and waits up to 30s for all 4 players to spawn. Once `PlayerManager.players` has 4 non-null entries and the game hasn't started yet, it calls `GM_ArmsRace.StartGame()` directly — covers the edge case where one or two `Player.Start` events fired before our `SetActive` landed (those wouldn't trigger `PlayerJoined`).

Scoped to `cr_ff` rooms only — 1v1 ranked, tournaments, and private rooms unaffected.

## v1.25.7 — 2v2 auto-spawn + diagnostics

Internal-facing release — continued 2v2 stabilization after v1.25.6.

- **Bypass ROUNDS' character-select press-any-key gate.** Vanilla `PlayerAssigner.Update` only fires `CreatePlayer` when the local user mashes a key — but in a 2v2 room, the character-select widget container only has 2 child slots, so players assigned to slots 2/3 don't see a prompt and never trigger their local spawn. v1.25.6 testing confirmed: on Sid's PC the `[2v2] CreatePlayer override` log line was missing entirely — Sid joined the Photon room but never spawned his player locally. Now an `Auto2v2SpawnCoroutine` fires immediately after joining a `cr_ff` room and calls `PlayerAssigner.CreatePlayer` itself once the scene is ready (routes through the existing 2v2 patch which uses the server-issued slot 0-3).
- **Auto-close F5 panel on `ready_join`.** The competitive page now closes the moment the server returns 4/4 ready, so testers don't sit on the queue screen while the Photon room is loading.
- **Heavy diagnostic logging in `cr_ff` rooms.** Every `OnPlayerEnteredRoom`, `OnPlayerLeftRoom`, `OnDisconnected` (with cause), `OnLeftRoom`, `NetworkRestart` (with stack trace), `PhotonNetwork.LeaveRoom` (with caller stack), `GM_ArmsRace.PlayerJoined` (with counted/listSize/playersNeededToStart), `GM_ArmsRace.StartGame`, `Player.Start` (with pid/team/isLocal/actor), and `MapManager.UnloadAfterSeconds` exceptions are logged with `[2v2-DIAG]` prefix. Goal: when a 4-player attempt fails, the BepInEx log on each tester's PC names the exact disconnect path. Diagnostics are gated on `Pending2v2Slot >= 0` or `cr_ff` room presence, so 1v1 ranked / casual / tournament logs are unaffected.

Scoped to `cr_ff` rooms only — 1v1 ranked, tournaments, and private rooms unaffected.

## v1.25.6 — 2v2 character-select OOB fix

Internal-facing release — continued 2v2 stabilization after v1.25.5.

- **`CharacterSelectionMenu.PlayerJoined` no longer aborts on player 3.** v1.25.5 successfully spawned all 4 players via the `/queue/poll → SetCustomProperties → join Photon room → CreatePlayer` chain, but vanilla's `CharacterSelectionMenu.PlayerJoined` does `transform.GetChild(0).GetChild(players.Count - 1)` to grab the per-slot face-select widget — and the menu container only has 2 children. Player 3's join threw `Transform child out of bounds`, which aborted the multicast `PlayerJoined` event before `GM_ArmsRace.PlayerJoined` could fire. So `playersNeededToStart` never decremented past 2 and the game never started. Patched with a Prefix that skips the menu wiring when `slot >= childCount`; players 3 and 4 just don't get the per-slot face-customize widget (which isn't shown in 2v2 anyway), and `GM_ArmsRace` now sees all 4 joins and starts the round.

Scoped to `cr_ff` rooms only — 1v1 ranked, tournaments, and private rooms unaffected.

## v1.25.5 — 2v2 spawn race + cascade-disconnect fixes

Internal-facing release — continued 2v2 stabilization.

- **Eliminated the player-spawn race.** v1.25.4 set `LocalPlayer` custom properties (`p_id` / `t_id`) inside the `CreatePlayer` Prefix, but Photon's broadcast order isn't strictly guaranteed — some clients' `Player.Start.ReadPlayerID` could fire before the property update arrived, leaving them at the wrong slot. Now the props are set the moment `/queue/poll` returns `ready_join`, well before the Photon room is even joined; they ride along with the player record at room-join time so all 4 clients always see the right values.
- **Suppressed vanilla's cascade-disconnect in 2v2 rooms.** `NetworkConnectionHandler.OnPlayerLeftRoom` was hardcoded for 1v1 — any player leaving fired `DoDisconnect` → `NetworkRestart` → all clients drop. So when 2 of 4 players hit the spawn race in v1.25.4 and bailed, the other 2 got cascade-DCed too even though they were fine. New patch returns false from that handler in `cr_ff` rooms; the match keeps running with whoever's left.

Both patches are scoped to `cr_ff` rooms only — 1v1 ranked, tournaments, and private rooms are untouched.

## v1.25.4 — 2v2 game-start fix

Internal-facing release — 2v2 isn't surfaced to most users yet, but this is the patch that finally makes 4-player ranked rooms work all the way through `StartGame()` instead of network-restarting at the player-spawn handshake.

**Root cause:** `PlayerAssigner.CreatePlayer` in vanilla ROUNDS hardcodes `m_playerId = 0` for the master client and `1` for everyone else. With 4 players, all 3 non-master clients write to slot 1 in `PlayerManager.players`, overwriting each other — only 2 of the 4 player objects survive locally. The 3rd and 4th players' PhotonViews dangle, so when ROUNDS' game-start tries to RPC them (`RPCO_RequestSyncUp`) they don't exist, `MapManager.UnloadAfterSeconds` throws on bad scene state, and Photon emergency-restarts the network → all 4 drop.

**Fix:** Harmony Prefix on `PlayerAssigner.CreatePlayer` that, when in a `cr_ff`-flagged 2v2 room, skips the vanilla master/non-master logic and uses a unique server-issued slot 0-3 instead. Slot is computed client-side from `team_assigned` + within-team steam-id sort (matches the server's lock-time canonicalization). Plus a `GM_ArmsRace.OnEnable` Postfix that lifts `playersNeededToStart` from 2 to 4 in those rooms — vanilla actually has a debug keybind for this (hold `4`) so the rest of the engine handles 4 players fine, the constant was the only gate.

1v1 ranked, tournaments, and private rooms are unaffected — the patches only fire when the Photon room has `cr_ff = true` (set only on `team_*` rooms by `QueueJoiner`).

## v1.25.3 — DC exploit fix, ranked-detection race fix, private-room series visibility

Non-mandatory but recommended.

- **DC-at-4-rounds exploit fixed.** When someone disconnected with 4 rounds while their opponent had fewer, the disconnector was getting credited with the win because the mod awarded victory to whoever had more rounds at DC time. Now: cancels the match unless both players are at ≥4 (the 4-4 tiebreak case, where the non-DC'er wins). DC'er still hits leave-%, just no free win.
- **First-match-vs-new-opponent ranked-detection fix.** When two mod users met for the first time, the existing player's `/mod/check` could fire BEFORE the new player's startup `/toggle-ranked` sync finished, leaving the match flagged casual for the entire room. The opponent ranked-check now retries every 5s while in room with a modded-but-not-ranked opponent, so it picks up the ranked status as soon as their sync lands.
- **Private-room ranked games now appear in Live Ranked Games immediately.** Previously the series row was only created at first-match-completion (~5 min into the match), so spectators couldn't see/bet on it until then. Mod now fires a `/series/preflight` beacon when it detects a ranked match starting outside the queue. Idempotent server-side, so no duplicates.

## v1.25.2 — Hotfix follow-up

- **Ranked detection corrected.** v1.25.1's room-name gate was wrong — random vanilla matchmaking between two real mod users *should* count as ranked, that's the intended path. Replaced with an "opponent has the mod" check based on the presence of any `cr_*` Photon custom property in the room. Vanilla players publish none, mod users publish several at room-join time (cards / trail / fps / pcolor / nametag etc), so the check correctly distinguishes the two. Two ranked-toggled mod users → ranked. One mod user vs vanilla → casual, regardless of any stale DB flags.
- **Auto-installer "v2.1.0" bug fixed.** v1.25.1's broader regex was catching `netstandard, Version=2.1.0.0` from the assembly's runtime reference table instead of the real ModVersion. New regex anchors directly on the BepInPlugin attribute's serialized blob layout (`Competitive ROUNDS` ModName + 1-byte length prefix + ModVersion) so it's guaranteed to read our literal.

## v1.25.1 — Hotfixes

- **Casual matches in private rooms no longer get reported as ranked** even when both players have Ranked toggled on. The mod now requires the Photon room name to be a queue-issued one (`ranked_*` / `team_*` / `sct-*` tournament) before flagging a match ranked. Caught by Lemon vs Ghelici playing 3 casual games in a private room — Ghelici lost 448 Elo before this hotfix; their rating + the matches have been corrected on the server.
- **Block activation counter no longer increments while the block is on cooldown.** Previously every right-click fired the activation count regardless of whether the block actually triggered, which inflated the activation denominator and made Block % look worse than it was. Now gated on `Block.counter >= cooldown` at TryBlock-time.
- **Auto-installer "vunknown" version detection fixed.** Regex was anchored to `1.1X.Y` so anything 1.20.0+ reported as "unknown". Now anchors on the BepInPlugin attribute and reads any `\d+.\d+.\d+` literal that follows.

## v1.25.0 — Body colors, neon nametags, FPS tracking, polish

Non-mandatory update.

### Body Color shop tab
- New **Body Color** category in the F5 Shop. Override the default orange/blue team color with a tint of your choice. Visible to everyone with the mod.
- 21 colors across 4 tiers — 10 × 3000g solid (Crimson, Emerald, Sapphire, Amethyst, Amber, Rose, Teal, Charcoal, Ivory, Slate); 5 × 4000g jewel/metallic (Obsidian, Mint, Lavender, Cobalt, Sunset); 4 × 5000g neons (Pink, Lime, Cyan, Violet); 2 × 8000g animated specials — **Prismatic** cycles the rainbow during combat, **Chrome** does a soft shifting cool-grey.
- Cosmetic-aware tinting filters out the face / gun / block-orb / cosmetic trails so you don't end up looking like an outline. Only what was originally team-colored gets repainted.
- Colors apply from the moment you spawn (pick phase #1 included), not just at combat start.
- Re-equipping mid-match swaps cleanly without a relog — restores the previous tint then applies the new one.
- New Settings toggle **`Custom player body colors: ON / OFF`** for anyone who finds the cross-player tints distracting; off = everyone reverts to vanilla orange/blue locally.

### Neon nametag tier
- 7 new **Neon** name styles at 500g each (Pink, Cyan, Lime, Orange, Violet, Toxic, Glow Yellow).
- Brighter than the regular color set, AND each carries a matching SDF-glow halo (visible to other modded players via the existing glow renderer; non-modded players still see the bright color via Photon NickName rich-text).
- Single-active within the color slot — equipping a Neon swaps any plain color out (and vice versa). The glow side rides for free, so you can still stack a separate plain Glow halo on top in a different color.
- Sort order in the Name Styles section now clusters Neons together as a premium block instead of interleaving them alphabetically with the 100g colors.

### FPS in match history
- Average FPS for both players is now captured per match and shown in the History row. Player side renders blue, opponent side red — same color theme as the cards/opp panel below.
- Lives in its own dedicated field next to the opponent name so it doesn't crash into long usernames.
- Opponent FPS only fills in if your opponent also has v1.25+; older builds report a `-` for that side.

### Block debug overlay (opt-in)
- New Settings toggle **`Block debug overlay`**. When on, a corner panel during matches shows live counters for block activations vs successful absorbs vs deduped raw events, plus per-hit timing classification (`TOO SLOW`, `TOO EARLY`, `unblockable?`, `no recent block`) so you can see exactly why a particular block didn't land. Default off.

### Misc
- **Leaderboard** now shows the top 100 players on the first page (was 50). Pagination kicks in past 100.
- **Discord auto-leaderboard** expanded to top 100 with `◀ Prev` / `Next ▶` buttons (20/page, 5 pages).
- **Immovable Object achievement** no longer false-flags when you press Enter and type in chat. The input check is now gated on whether the chat overlay or F5 menu has focus.

### Backend / data
- New `matches.p1_fps_avg` / `p2_fps_avg` columns (migration 052).
- 21 player_color shop items (migration 054), 7 neon nametag items (migration 056).

## v1.24.0 — Automated tournaments (Phase 1 + Phase 2)

Non-mandatory update. Older clients still work against the live API — they just don't see the Tournaments tab or the auto-connect flow.

### Tournaments tab — sync + async modes

- **New F5 menu tab: "Tournaments"** with a SYNC / ASYNC sub-tab toggle.
- **Sync tournaments**: auto-created weekly, default slot = Saturday 12:00 PT. 7-day signup window; voting on 8 alternate start slots within ±24h of default (tallies hidden until you vote). 6-hour pre-lock window for time voting to settle. Force-start unlocks at 8 signups — every current signup voting within a 30-min window triggers an immediate start.
- **Async tournaments**: auto-created every 6 weeks. Bracket visible from start; no scheduled start time — matches activate on signup lock and each carries a 7-day deadline. Players self-coordinate via Discord (`/dm-opponent`, `/opp-online`). When both players have Ranked enabled and play in any private ROUNDS lobby, the mod auto-detects and records the result.
- **Format (both modes)**: **double-elim BO3**. Single-elim was replaced after playtest feedback — parallel play makes double-elim wall-clock ~90–120 min for a 16p sync bracket. LB absorbs WB losers round-by-round; Grand Final has bracket reset if LB champ wins first BO3.
- **Top seeds get byes** when under 16 sign up. All matches count toward ranked Elo.
- **Partial-advance**: a match is playable the instant both its prereqs have winners, not round-gated.
- **Bracket**: click-to-expand rounds. Default state shows compact round headers with `[+]` / `[-]` toggles and progress summaries; the currently-active round auto-expands. `[LB]`, `[GF]`, `[Bracket Reset]` tags identify bracket side.
- **Timezone picker** at the top of the tab — tap to cycle through Local / UTC / PT / MT / CT / ET / UK / CET / EET / MSK / JST / AEST. Preference persists via BepInEx config. Current time in the selected zone is shown next to the picker so you can verify.
- **TOURNAMENT GAME indicator** under the top RANKED status: yellow banner when you're in a ROUNDS room with a known tournament opponent.
- **Instruction block** per mode — distinct copy for sync (auto-connect + 5-min ready-up) vs async (self-coordination + 7-day deadline).
- **Auto-enable Ranked** fires per-match, not per-signup: the moment your tournament match goes active, the mod flips Ranked on + posts `/toggle-ranked` and notifies you. Checked fresh at every tournament game so results always record.

### Auto-connect (sync)

- **Deterministic room code** derived from match_id: `sct-<prefix>`. Both clients land in the same Photon room.
- **Region-pinned**: each tournament's canonical Photon region is the mode across all signups' regions at signup time (alphabetical tiebreak). Auto-connect passes the region to the existing `QueueJoiner` → `NCH.ConnectToRegion()` → `JoinOrCreateRoom`. No more cross-region ghost rooms.
- **Reconnect button** + visible room code in the my-match panel so players can manually rejoin if auto-connect hits a transient Photon issue, and the room code is always available for ROUNDS' native private-lobby join.
- **Plugin-level heartbeat** fires every 20s whenever you have an active tournament match — regardless of which F5 tab is open or whether the competitive UI is visible. Keeps your `ready_at` fresh during gameplay so your next sync match doesn't auto-forfeit between rounds.

### Discord bot

- **Lifecycle announcements** in `TOURNAMENT_CHANNEL`: signups open (sync + async variants), tournament locked with roster, tournament started, tournament complete + podium + prize tier.
- **DMs to participants**: signup confirmation with seed + scheduled start, match-ready notifications (different copy for sync vs async), 24h deadline warning for async, daily "still pending" nag after 3 days of inactivity.
- **Slash commands**:
  - `/dm-opponent <message>` — rate-limited 8/min relay to your current tournament opponent's DM
  - `/opp-online` — quick check on whether your async opponent is currently online in Discord (requires `DISCORD_PRESENCE_INTENT=true`; bot degrades gracefully without it)
- **Trophy role grants** on completion: 1st → `SCR Tournament Winner`, 2nd → `SCR Tournament Runner Up`, 3rd → `SCR Tournament 3rd Place`. Multi-win tracking via `(x2)` suffix variant: on a second placement at the same tier the base role is swapped for the `(x2)` role. Participant tracking uses `SCR Tournament Participant` → `SCR Tournament Participant 2` promotion.

### Prizes

- **Full tier (16+ players)**: 1st = 500g + 2500 XP, 2nd = 300g + 1500 XP, 3rd = 60g + 75 XP, plus trophy roles.
- **Scaled tiers**: 60% at 12–15 players, 30% at 8–11. Tournaments cancel under 8 signups — no prizes.
- **All matches count toward ladder Elo** — tournament seeding is a snapshot at lock time, individual series still move your rating.

### Penalty system

- Rolling 90-day show rate with linear decay: `sum(decay(age) · miss) / sum(decay(age) · signup)`.
- Signup penalty tracked per player; cached pct recomputed inline on signup and after every forfeit (no more stale display).
- **"Play first" priority**: lower penalty is the tiebreaker when more than 16 sign up. `~` prefix in the signup list marks speculative slots that can be displaced by penalty-free late joiners before lock.
- **Leave semantics**:
  - During voting: free leave, no penalty.
  - During locked (bracket built, not started): free leave, speculative signup is promoted into your slot OR your matches collapse into byes for your opponent.
  - During running: leave blocked; only path is no-show → forfeit → penalty.
- **Deadline tiebreak**: mutual no-show awards the win to the lower-penalty player (then alphabetical signup_id fallback for strict determinism).

### Cross-tournament safeguards

- **Player blocks auto-cleared** between confirmed tournament participants at lock time. Signing up opts you into playing whoever else signed up.
- **Series lookup fix** (`main.py:/matches`): `.order_by(created_at DESC).limit(1)` so a player in multiple active tournaments against the same opponent doesn't hit `MultipleResultsFound`.
- **Advance-match row lock**: `with_for_update()` on the match select in `advance_tournament_match` serializes the tick/hook race cleanly.

### Schema changes

- **047_tournaments.sql** — tournaments, tournament_signups, tournament_matches, tournament_time_votes, tournament_force_votes, player_tournament_penalty. Extends ranked_series with tournament_id + is_tournament.
- **048_tournament_region.sql** — region_at_signup on signups, photon_region on tournaments.
- **049_async_tournaments.sql** — deadline_at + prereq_roles on tournament_matches.
- **050_sync_double_elim.sql** — backfills existing voting-state sync tournaments to double_elim_bo3.

### Other UI polish

- **Signup list progress labels** on right column: shows per-player bracket status ("WB R2", "LB R3", "eliminated LB R2", "CHAMPION").
- **Tournament history** on leaderboard click-a-player detail: trophy counts + last 4 placements.
- **Tournament history** on the Tournaments tab: site-wide "Recent Tournaments" panel showing last ~12 completed events.
- **All-bold text fallback**: rich-text `<b>` wrap in `UIFactory.CreateText` and `SetText` — belt-and-suspenders against SDF atlases that silently no-op `fontStyle=Bold`. Applies to every F5 menu tab.

### Known limitations

- Async cadence is 6 weeks; worst-case LB path (9 matches × 7-day deadline) = up to 9 weeks. Back-to-back async tournaments may overlap if the prior one has stragglers; signup windows open on schedule either way.
- Bracket reset (`GF_RESET`) is dynamically inserted when the LB champ wins the first GF; it doesn't show in the bracket preview before that point.
- Trophy roles are delegated to the Discord bot. If the bot is down for >24h around a tournament completion, role grants may silently miss — widen the bot's completion window or persist the notified set to fix.

### Bot env vars (operator-side — no code change needed)

- `TOURNAMENT_CHANNEL` — Discord channel ID for tournament announcements.
- `TROPHY_ROLE_CHAMPION` / `TROPHY_ROLE_RUNNER_UP` / `TROPHY_ROLE_THIRD_PLACE` / `TROPHY_ROLE_PARTICIPANT` / `TROPHY_ROLE_PARTICIPANT2` — override names if your guild's roles differ from the SCR defaults.
- `DISCORD_PRESENCE_INTENT=true` — enables `/opp-online`. Requires the matching intent enabled in the Discord dev portal.

## v1.23.1 — Hotfix: map cycle no longer tints the moving boxes

Post-v1.23.0 ship reported a regression: pressing Left Shift to cycle map colors tinted **every** SpriteRenderer under `Map/*` (the 49 moving physics boxes) and every non-UI/non-player scene sprite, making the whole map read as a monotone color block. The fix removes those two passes so the tint now applies only where intended: the `OutOfBounds/*` wall particle systems (the primary + secondary wall colors) and the ArtInstance atmosphere particles. Moving boxes keep their vanilla art colors.

## v1.23.0 — Nametag Styles, Multi-Color Maps, Hit/Block/Pass Stats, Polish

Non-mandatory update. Older clients still work against the live API, they just don't see the new stats or shop items.

### Lifetime stat tracking — Hit %, Block %, Card Pass %

- **Hit %** — % of projectiles fired that connected with an enemy. Shown on the My Stats Record panel and on the leaderboard player-detail. Powered by a Harmony Postfix on `Gun.Attack` that counts `numberOfProjectiles` per trigger pull (shotgun pellets count individually, auto-fire counts each bullet), paired with a `HealthHandler.TakeDamage` postfix that decrements a per-projectile hit budget. Over-counting from DOT ticks / splash is naturally bounded by `bullets_hit ≤ bullets_fired`.
- **Block %** — % of right-click (or Shields Up / Empower) block activations that absorbed at least one bullet. Activation counter on `Block.TryBlock` includes card-triggered auto-blocks. Success counter on `Block.DoBlock` is deduped to a 1-second window so multi-absorb + block-extension within one activation count as one success, not many.
- **Card Pass %** — for every card you've been offered, what fraction did you pass on. Visible in Card Stats. Fed by a Harmony hook on `CardChoice.RPCA_DoEndPick` capturing all offered `cardIDs[]`. A safety net synthesizes the missed-by-Harmony pre-match pick (first pick of a match routes outside the RPC path) so pass rates aren't inflated by phantom "never picked" first-pick rows.
- Added 4 BIGINT columns on `players`: `bullets_fired`, `bullets_hit`, `blocks_activated`, `blocks_successful`. Migration 038.

### Nametag styling — stackable rich text

- 16 shop items under a new NAME STYLES section, all 100 g:
  - **Stackable formatting** (any combination): Bold, Italic, Underline, Strikethrough
  - **Colors** (single-active subgroup): Red, Cyan, Gold, Purple, Green, Pink
  - **Sizes** (single-active): Smaller (80 %), Bigger (130 %), Huge (160 %)
  - **Font-style transforms** (single-active): ALL CAPS, SmAlLcApS, S p a c e d
- Your styled nickname broadcasts via `PhotonNetwork.LocalPlayer.NickName` so every player — modded or vanilla — sees the rich-text rendering. No Photon custom props required for the publicly-visible pieces.
- Subgroup enforcement runs both client-side (optimistic UI) and server-side (`/nametag-toggle` strips same-subgroup before adding).

### Multi-equip map colors with in-match Shift cycle

- Map colors upgraded from single-active to **multi-equip** — equip as many as you want from the shop, then press **Left Shift in-match** to cycle through your owned set. Empty set → ROUNDS' vanilla random rotation.
- New `/api/v1/players/{id}/color-toggle` endpoint mirrors the nametag-toggle pattern; legacy `/active-color` endpoint keeps single-value writes in sync for backward compat.
- `ArtHandler.NextArt` Harmony prefix advances a shared `MapColorState.CurrentSku` on each call, rebuilds the post-process clone AND re-runs `MapPhysicalColorPatch.ApplyPhysicalTintsForSku` so walls / sprites / particle tints cycle in lockstep with the color grading.

### Shop UX overhaul

- **Category tabs** at the top of the Shop panel: All / Titles / Trails / Maps / Name Styles. Each tab filters the scroll view and shows a one-line description of what the category does + how it's visible to other players.
- **Row pool bumped 80 → 200**. Fixes the "disappearing items" bug — total catalogue grew past 80 this version and trailing items silently stopped rendering.
- **Set Active button label** is context-aware: "Equip" / "Remove" for multi-equip categories (nametags, colors) and "Set Active" / "Equipped" for singleton categories (title, trail).
- **Shop description** updates to be accurate: trails render on the character body during combat (preview shows cursor-follow; actual render is player-attached), titles show up in the chat overlay too, name styles are visible to every player.

### Ranked economy bump

- **Series-win gold doubled**: 10 g per win, +2 g sweep bonus (was 5 g / +1 g).
- **Ranked XP multiplier 1.2× → 1.5×**. A ranked sweep-win against a top-5 opponent now clears ~820 XP post-bonuses.
- **Gold display in Ranked History** now shows the series-win bonus. Previous row-level `gold_gained` only showed the 4-5 g per-match XP→gold conversion; the 10-12 g series bonus was invisible. Rolled the `series_gold_gained` value into the series header as `+12g` next to the elo change. Widened the elo field from 80→160 px to fit.

### Live Ranked Games — visible pulsing

- The leading `●` in the Live Ranked Games header now alternates between bright pink and dim red every 2.5 s while the Leaderboard tab is open, so it's visually obvious the panel is polling the server live. Decoupled from the 10 s fetch cadence. Previous attempt using `●` ↔ `○` rendered as identical `□` because ROUNDS' Gravity font doesn't contain either glyph.

### Anti-cheat tuning

- **Inactivity flag threshold 30 s → 300 s**. Previously every match under 2 minutes where the reporter happened to have 0 clicks (quick death) triggered a review flag. Now only truly-absent-the-whole-game sessions flag.
- **Offline practice matches blocked** from reaching the DB. ROUNDS' offline mode uses the cached online-opponent's steam_id as the "opponent" slot, so two phantom 5-0 casual matches made it into Sid's history from Nix's practice session. Triple-layer fix: client skips the report when `PhotonNetwork.OfflineMode` or the room name contains "offline"; server rejects with a 400 if the `photon_room_id` contains "offline"; migration 044 purged the 2 existing phantoms.

### Bug fixes

- **New-install ranked sync race** (the "RoarkCats" bug). Fresh installations didn't auto-sync their ranked-enabled state to the server if Steam's API hadn't returned their Steam ID by the time the startup sync fired — next two matches then got recorded as casual even though both sides had the mod. Now `GameStateWatcher.IdentifyLocalPlayer` calls `ToggleRanked` on the first successful Steam-ID resolve, so new installs auto-register and their opponent-check response is accurate for the very next match.
- **Card name duplicates** (Pristine Perseverance, Ricochet, Fast Ball, Chilling Presence, Drill Ammo, Radar Shot, Target Bounce, Taste Of Blood, Abyssal Countdown, Leech) merged into single canonical rows. Root cause: `OnOpponentCardPicked` stored opponent card names raw without going through `CardRarityLookup.GetCanonicalName`. Fixed at the write site; migration 046 backfilled 175 `card_offers` + 297 `match_cards` rows across 11 variants.
- **Poison / Poison Bullets split** — ROUNDS' current display is just "POISON"; the code's `hardAliases` was mapping the other way and keeping the pre-rename "Poison Bullets" as canonical. Reversed, migration 043 consolidated 11 offer rows + 417 match-card rows to "Poison".
- **Match-found panel's blue "Waiting for opponent..." text overflowing off-screen to the left.** The wrapper GameObject had no LayoutElement, so the parent HLG collapsed it to 0 width and the center-anchored inner TMP drew 175 units left of that collapsed point. Created the text directly in the match-row HLG with explicit width + MidLeft alignment.
- **Opponent DC wasn't incrementing `ranked_dc_count` when opponent left mid-match** on the reporter-side client. Fixed in the disconnect-handling path.

### Shelved: custom typefaces + glow halos

- Attempted 22 OFL-licensed font variants (Creepster, UnifrakturMaguntia, Press Start 2P, Pacifico, Great Vibes, Permanent Marker, Playfair Display, etc.) across Common/Uncommon/Rare/Legendary tiers via a Unity Editor project + AssetBundle pipeline. Bundle fails to load at runtime — ROUNDS' Unity build is not compatible with any build currently available on Unity's archive. Feature code + `unity-font-bundler/` Unity project stay in-repo for a future attempt. Migration 042 refunded all purchases and removed the SKUs.
- Attempted 4 glow-color halo effects via TMP SDF material clones. Confirmed via in-game material diagnostics that ROUNDS' TMP shader variants were compiled with the `GLOW_ON` and `UNDERLAY_ON` samplers stripped out — keywords get set on the material but the shader has no code to read them. Only outline renders, which doesn't look glow-like. Feature code stays in-repo. Migration 042 refunded + removed.
- Full retrospective in `docs/typeface-glow-shelved.md` — what we tried, why each path failed, and what to revisit if the pipeline becomes viable.

### Schema changes

- `038_hit_block_stats` — add 4 `BIGINT` columns to `players` for lifetime stat counters
- `039_nametag_typefaces` — add 5 broken OS-font typeface SKUs (deleted in 042)
- `040_reset_hit_counters` — one-shot reset of `bullets_fired` / `bullets_hit` for all players after the per-projectile gate landed
- `041_typeface_bundle_launch` — insert 22 OFL typeface SKUs (deleted in 042)
- `042_shelve_typefaces_glows` — refund + delete 26 shelved SKUs (22 typefaces + 4 glows)
- `043_multicolor_and_poison_fix` — add `active_color_ids BIGINT[]` column + backfill from single column; consolidate Poison Bullets → Poison
- `044_purge_offline_matches` — delete phantom offline-room matches from history
- `045_reset_sid_block_stats` — one-shot reset of Sid's block counters for clean validation data
- `046_card_name_dedup` — consolidate 175 `card_offers` + 297 `match_cards` rows across 11 near-duplicate card names

## v1.22.0 — Anti-cheat, Admin Tools, Map Colors, Polish

Mandatory update. The server rejects any client below v1.22.0 with a 426 response,
and the mod auto-prompts the update on launch.

### Anti-cheat
- **Sub-60s game-pattern detection.** Each game's duration is now reported and stored. If
  a player pair plays 2+ ranked games (or 3+ casual games) under 60 seconds within a
  2-hour session window, the streak is auto-flagged and **invalidated** retroactively —
  XP and gold reversed, series marked invalid. Per-game timer (not per-series).
- **>5 cards per player per game** triggers an instant flag + invalidation (vanilla cap
  is 5 picks per BO5 game; >5 means a sandbox or modded client snuck in).
- **Inactive-reporter heuristic**: if the reporter's bullet/block input counts are both
  zero across a non-trivial duration, the match is flagged for manual review (not
  auto-invalidated — the opponent could be the cheater instead, manual eyeball needed).
- New `flagged_matches` table is the single source of truth for the audit log.
- Discord bot polls for new flags and posts them to a private `#scr-admin` channel
  (color-coded embed per reason: too-many-cards red, short-duration orange, inactive yellow).
- Stale series cleanup — any active series with no match reported within 30 minutes gets
  marked abandoned and pending bets are refunded automatically.

### Admin tools (in-game tab)
- New **Admin tab** in the F5 menu, visible only to whitelisted Steam IDs (`admin_users`
  table seeded with Sid + Lopi).
- Lists flagged matches with `Cheat` / `False+` review buttons + the current ban list
  with `Unban` action.
- Three IMGUI prompt overlays for Ban / Grant Achievement / Reverse Series.
- All admin endpoints require both an admin Steam ID **and** an HMAC over
  `admin:{steam_id}:{action}:{target}` to prevent header-only spoofing.
- `admin_actions` audit table records every ban / unban / achievement grant / series
  reversal with the admin Steam ID + timestamps.
- Banning blocks the offender from queue (409), chat (silent drop), and betting (409).
  Banned Discord chatters are also dropped at `/chat/post` via a discord_id→steam_id lookup.

### Betting upgrades
- **Live series now appear immediately at matchmaking** (server pre-creates the
  ranked_series row in `/queue/ready` instead of waiting for game 1's report).
- **Bet cutoff at 2 points scored in game 1**. Client posts live point updates during
  the first match; server rejects bets once `live_p1 + live_p2 >= 2`. Once any game in
  the series ends, betting is also locked.
- **RD-aware odds via Glicko expectancy** — replaced pure-Elo with `g(combined_RD) *
  rating_gap`. Players with RD ≥ 100 see compressed odds; the cap drops linearly from
  3.0× at RD≤100 to 1.0× at RD≥300, then betting is locked entirely as
  "no meaningful odds yet". A fresh "expert" can't be exploited until they've played
  enough games for their rating to settle.
- **One bet per series** enforced server-side (409); client hides wager buttons preemptively.
- Live Ranked Games panel widened, text bigger + bold, auto-refresh every 10s while open,
  pagination at 5 series per page.
- After placing a bet the wager buttons get replaced inline with `You bet Ng`.

### Recent Ranked Series
- Server returns up to 100 most-recent series; UI shows 20 per page with prev/next.
- Each row now shows both players' current ELO inline.
- Settled bets appear as indented sub-rows under each series row:
  `↳ AsteRiA bet 500g on Sid → +505g` (green for winners, dim for losers).

### Cosmetic trails
- **Photon-late-arrival fix** — opponent's trail now appears in game 1 (was failing on
  the first match because Photon custom-property propagation raced our `OnMatchStart`).
  Hooks `IInRoomCallbacks.OnPlayerPropertiesUpdate` to re-attach when properties land.
- Trail length scales properly with price tier (3k/5k/10k → short/medium/long).
- **Trail preview** in the shop. Click the new `Preview` button on any trail row to
  spawn a cursor-following uGUI dot trail at sortingOrder 30001 (above the F5 menu, so
  it's actually visible). Local-only — opponents never see your preview. Auto-stops on
  re-click, switching trails, or closing F5. Soft circular alpha sprite + per-pixel
  cursor sampling so it reads as a smooth streak instead of "spray".
- Multi-stop gradients on the legendary tier (Phoenix, Void).
- Particle sparkles on Phoenix / Void / Prism / Tride.
- **Tride trail** — trans pride flag colors. Cyan + pink alternating bands (white
  removed from the gradient because it was averaging the whole trail to white).

### Shop expansion
- New titles: **She/her**, **They/them**, **He/him** (100g, common, white).
- New uncommon titles: **Idiot**, **Grandma** (matches Grandmaster's magenta), **Decent** (1000g).
- New 4k rare trails: **Colossus** (ice), **Ascendant** (jade), **Sovereign** (purple→cyan),
  **Titan** (pink→red).
- New 5k legendary trail: **Tride** with particle sparkles.
- Vanilla map colors: Sweden, Sky, Poison, Gold, Soviet, Rainbow (75g each).
- **Custom map colors** — runtime-authored ColorGrading + per-particle tinting + physical
  block tinting. 13 presets: Soft Slate, Moss, Cream, Lavender, Dusk, Sand, Monochrome
  (lighter), Forest, Amethyst, Charcoal, Crimson, Slate, Rose, Mint, Sunset (darker).
  Each composes on a vanilla base art (so bloom/vignette stay) + tints the moving boxes
  + tints `OutOfBounds` wall particles + tints the active art's particle backdrop with
  a complementary secondary color so the wall reads multi-tone.

### Chat
- **In-game chat outside F5**. Press T anywhere (not just in the menu) to open. Gated
  on active combat (won't fire while you're alive in a fighting round) so movement input
  isn't captured. Mutex with other in-game chats — checked via
  `EventSystem.currentSelectedGameObject` for any active InputField.
- **Bot reconnect catch-up** — periodic `/chat/recent` poll (every 30s) plus on-WS-reconnect
  poll backfills any messages the WS broadcast missed (lopi's silent-drop bug).
- **Synchronous message-id dedup** in the bot's forward path so the catchup poll and live
  WS path don't double-post the same message under timing races.
- Per-line truncation in the F5 chat overlay so a 9000-char paste can't overflow the
  scroll content + auto-scroll-to-bottom on each new message.

### Achievements
- Per-trophy gold reward bumped **25g → 100g**. Achievements are rare, the reward should
  matter.
- F5 Achievements tab now shows `+100g` next to each unlocked achievement's date.
- **Immovable Object & Pacifist** input gate uses an `inPickPhase` flag driven by ROUNDS
  log markers — these correctly fire only during actual combat now (was falsely
  triggering on Space-to-confirm during pick phase).

### Server reliability
- **Maintenance mode** endpoint `POST /admin/maintenance/start` flips a global flag;
  non-bypass requests get a clean `503 + Retry-After: 30` instead of connection-refused.
  Optionally broadcasts a `[server]: Server restarting in ~30 seconds` message via the
  chat bridge so in-game players + Discord see the warning.
- **F5 server-status banner** shows `● Server reconnecting…` or `● Server in maintenance —
  back in a moment` when no successful API call in the last 10s AND a recent attempt
  failed. Hidden on quiet periods (no calls = no info either way).

### Polish
- Match history rows now show opponent's current title inline: `vs Sid [Kingslayer]`.
- F5 chat scroll-lock fix — long messages no longer trap the scroll position.
- Bet button click silently dropped (double `ClickGuard.Claim()`) — fixed.
- Live Ranked Games container layout rebuilt — panel was collapsing under recent series.
- Click-through on consent modal blocked via dedicated raycast Canvas.
- F5 click-block on Gun.Attack / Block.TryBlock prefixes (only the LOCAL player), so
  clicking shop / settings buttons doesn't fire your gun.
- Discord username backfill on bot startup (no more raw IDs in chat lines).
- T chat key won't fire while the user is mid-combat or another text input has focus
  (post-Enter staleness handled).

### Schema migrations in this release
`027_anticheat` · `028_admin` · `029_shop_expansion` · `030_live_points_and_colors` ·
`031_fix_mapcolors` · `032_custom_mapcolors` · `033_more_mapcolors`

---

## v1.20.0 — Economy, Chat, Betting, Trails

Mandatory update. The server rejects any client below v1.20.0 with a 426 response,
and the mod auto-prompts the update on launch.

### Economy / Shop
- **Gold currency**. 100 XP = 1 gold. +25 gold per achievement. +5 gold on a ranked series win, +1 more on a 2-0 sweep.
- **Shop tab** with titles and trails (separated into labelled sections, sorted cheapest-first per tier).
- **Titles** (10): Beginner, Regular, Active, Clown, Sweaty, Tryhard, Competitor, Kingslayer, Grandmaster, Royal.
- **Cosmetic trails** (7): Clean Trail, Crimson Streak, Azure Comet, Emerald Glow, Phoenix Flame, Void Ripple, Prismatic Wake.
  - Trail **length scales with price tier** (3k short / 5k medium / 10k long).
  - Prismatic trail cycles through the full color spectrum in real time.
  - **Photon-synced** — other mod users see your trail behind your player during matches.
  - Toggleable in Settings → Display → Cosmetic trails.
- **Active title** renders in leaderboard rows (bold, colored), chat messages (both in-game and Discord), and the My Stats Discord Link row.
- **Gold column on the leaderboard** (sortable). My Stats shows gold balance inline with W/L.
- **Gold breakdown** in the after-match notification: `+9 gold [XP +3, Series win +5, Sweep +1]`. Match history rows show `+N xp +N g`.

### Betting
- **Live Ranked Games** panel on the Leaderboard tab shows in-progress series with current score and both players' Elo-based odds.
- Bet preset stakes (100g / 500g / 2000g) on either player. Odds = `1 / P(win)`, capped at **3x** so the largest payout is 3× stake. Favorite-bets at `|ΔElo| ≥ 800` return ~1.01x (essentially nothing).
- **Can't bet on your own match** — UI hides the stake buttons when your Steam ID is a participant, and the server 409s anyway.
- Bets settle the instant the series completes; winners credit gold automatically.

### In-game ↔ Discord chat bridge
- **WebSocket endpoint** `/api/v1/ws/chat` with long-lived connections, 25-second keepalive pings to survive NAT timeouts, and a queue-based serialized sender so rapid-fire messages don't overlap.
- **Two-way bridge** via a Discord bot subscribed to `#scr-discussion`. In-game messages appear as `**Name [Title] (1946)** (in-game): ...` in Discord.
- **Chat panel** in My Stats (under Discord Link). Press **T** while the F5 menu is open to type and send; Enter sends, Esc cancels.
- **In-game chat overlay** (bottom-left, auto-fade after 35s) so you don't have to open F5 to see new messages. Toggle in Settings.
- **Scrollback** — last 50 messages persisted server-side and loaded on connect.
- **Rating** attached to every message so you can verify someone claiming to be a top player. Works across both bridge directions.
- **Local echo** so your own message appears instantly; server-side broadcast excludes the sender to avoid duplicate rendering.

### Privacy & data consent
- **First-launch consent modal** explaining exactly what gets collected: Steam ID, Discord link, match data, Glicko history. Requires explicit Allow or Decline.
- **Revoke consent** in Settings → full offline mode. Ranked mode turns off, chat disconnects, no API traffic.
- **Delete my data** — anonymizes your row (Steam ID → `deleted_<uuid>`, display name → `[Deleted User]`, Discord link scrubbed). Matches stay so **other players' ratings and histories aren't retroactively disturbed**.
- **Deletion is irreversible** — a server-salted hash of the deleted Steam ID is kept in a blocklist. Re-registration re-creates the row as a permanent `[Deleted User]` tombstone so account-wipe-to-reset-rating spoofing isn't possible.
- **Anonymized players hidden** from leaderboards and skipped by the Glicko recalc.
- **Version gate**: `X-Mod-Version` header on every request. Client version below `MIN_MOD_VERSION` gets 426 and is prompted to update.

### Pass-tracking
- The mod captures every card **offered** during pick phase (not just the one picked), sends them with the match report.
- New `card_offers` table. Stats queries compute **pass rate** (`1 - picked / offered`) per card.
- **Pass%** column in the Card Stats tab, sortable.

### Achievement & gameplay fixes
- **Immovable Object & Pacifist** gate rewritten. The pick-phase state (Space to confirm, A/D to browse cards) was incorrectly counting as "moved" / "fired", blocking both achievements. New `inPickPhase` flag driven by ROUNDS log markers (`PICK PHASE`, `MOVE PLAYERS END`, `Round over`) — achievements fire only during actual combat now.
- Retroactive grants for Stan and Noah.
- Pacifist achievement fix from the same root cause.

### Auto-update
- Mod auto-fires the update handler on launch when it detects a newer `LATEST_MOD_VERSION` from the server.
- The direct-Discord build writes a `.bat` apply-on-exit script; Thunderstore build (no `.bat` allowed) shows a notification instead. Both paths are already gated by `#if THUNDERSTORE`.

### UI polish
- **Settings tab** (5th tab) with Data Consent status, Revoke, Delete My Data (two-step confirm + explicit irreversibility warning), and display toggles (FPS, Region/Ping, In-game chat overlay, Cosmetic trails).
- **Chat notifications** toggle controls the on-screen pop-ups for incoming chat + XP / level.
- **Click-to-reveal** on the Discord link row so streamers don't accidentally doxx themselves.
- **F5 menu auto-closes** when combat starts (on `MOVE PLAYERS END`) so it can't block clicks during play.
- F5 chat log now word-wraps.
- Leaderboard title rendered bold + in the title's color next to the name.
- Cosmetic trails can be toggled off mid-match without relaunching; toggling back on re-attaches.

### Server
- **Version-gate middleware** returns 426 with `{"required": "1.20.0", "current": "..."}` for any client below `MIN_MOD_VERSION`.
- `/api/v1/shop/items`, `/api/v1/shop/purchase`, `/api/v1/players/{steam_id}/inventory`, `/api/v1/players/{steam_id}/active-title`, `/api/v1/players/{steam_id}/active-trail`, `/api/v1/players/{steam_id}/data` (anonymize), `/api/v1/bets`, `/api/v1/series/active`, `/api/v1/chat/recent`, `/api/v1/chat/post`, `/api/v1/ws/chat`.
- **Card-stats materialized view unique index fixed**. Previously the view grouped by `(card_name, card_rarity)` but the unique index was on `card_name` alone, causing REFRESH CONCURRENTLY to fail whenever the same card appeared with multiple rarities.
- **Poison / Poison Bullets** + **Prisitne Perseverence / Pristine Perseverence** deduped — both the current stream (via client alias in `CardRarityLookup`) and the backfilled rows.
- **Discord username backfill** — the bot resolves all linked Discord IDs to usernames on startup. In-game display shows `@username` instead of numeric ID.
- **Rating-change swap fix** — `p1_rating_change` / `p2_rating_change` now map correctly to the series player order (match-report p1/p2 can differ from series creation order).

### Schema migrations in this release
`013_dedup_poison_and_card_stats_index` · `014_card_offers` · `015_dedup_cardnames_v2` ·
`016_discord_username` · `017_anonymize_not_delete` · `018_deleted_steam_ids` ·
`019_chat_messages` · `020_economy` · `021_shop` · `022_rename_gold_rush` ·
`023_bets` · `024_trail_items` · `025_active_trail_col`

---

# v1.18.7 Changelog

## Leaderboard Improvements

### Rating Line Graph
- Replaced the confusing bar chart in the player detail panel with a proper **line graph**
- When Elo rating history is available (≥2 data points), displays a blue **Rating History** line showing Elo over time with dots at each data point, y-axis labels for rating range, and a clean title above the graph
- Falls back to a green **Ranked Form** line (running W/L score) when rating history data isn't available yet
- Fixed text overlapping the graph — title now renders above the plot area instead of behind the bars

### Rating History Data Fix
- **Root cause found**: the inline Glicko-2 recalculation after ranked series completion was updating ratings but never saving snapshots to the `rating_history` table — only the weekly Monday cron did
- Now saves a `RatingHistory` snapshot for both players after every series completion, so the Elo graph populates going forward with each ranked series played

### Form Data Now Series-Based
- Recent form data now pulls from **completed ranked series** instead of all individual matches (ranked + casual)
- Each W/L entry on the graph corresponds to a series result that changed Elo, not individual games
- Graph label updated to "Ranked Form" to reflect this

### Leaderboard Column Centering
- Fixed leaderboard table alignment — columns now center in the available space instead of being pushed to one side with a visible gap

### Recent Ranked Series Pagination
- Added **Prev/Next** pagination buttons to the Recent Ranked Series panel (left column)
- Displays 8 series per page with a page indicator
- Panel no longer wastes vertical space showing an empty area below a handful of entries

## Leave % Tracking (Full Stack)

### How It Works
- Tracks when a player **disconnects during a ranked match** where ≥2 total points have been scored and neither player has ≥4 rounds
- Matches where someone already has ≥4 rounds are handled by the existing DC Win/DC Loss system and don't count toward leave %
- Only tracked for ranked matches, not casual

### Detection
- Client detects opponent disconnects by monitoring `PhotonNetwork.PlayerList` — when the list drops to 1 player during an active ranked match, the remaining player reports the disconnect
- New `POST /api/v1/report-disconnect` server endpoint records the event
- Separate from match reporting — not affected by the "lower Steam ID reports" rule

### Display
