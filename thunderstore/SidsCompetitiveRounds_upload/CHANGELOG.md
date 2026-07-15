# Changelog

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

## v1.31.0 — RELEASED 2026-07-13

**Headline: the 1v2 mode (solo vs duo, unranked beta) is live** — queue from the new Multiplayer > 1v2 tab. Plus the July 12/13 bug batches (#58, #64–#75), 15 new cosmetics (6 animated), 12 body colors, the Discord leaderboard-channel fix, and an FFA design-preview tab. Details in the section rounds below.

### Server (deployed)
- **Bug #70 — 2v2 series after the first never recorded**: `/team/series/continuation` raised NameError on its create path (function-local `uuid_mod` alias referenced from module scope) → 500 on every rematch-series open; every game after a sitting's first completed series was dropped. One-line fix; the endpoint's idempotent branch had masked it from smoke tests.
- **Bug #66 — achievement percentages meaningless**: denominator was all 2,847 auto-created player rows; now both sides count mod users only (`mod_seen_at IS NOT NULL`, ~200 players). Untouchable: 0.8% → 11.8%.
- **Bug #68 — admin series cards mashed together**: per-game encoding (`||` between games, `|` within — still JsonUtility-safe flat scalars).
- **Discord bot — leaderboard channel staleness**: loop verified ticking (10-min fetches, 200 OK) but successful edits logged nothing and older duplicate board messages could sit stale above the one being edited. Every publish outcome now logs one line; rescans delete duplicate boards and keep exactly one; `api_get` logs non-200 statuses instead of silently returning None.
- **Schema changes / migrations**:
  - `115_backfill_july12_lost_matches.sql` — restores the July 12 recording gap: 2 completed 2v2 series (5 matches) with offline-replayed Glicko (Sid +28.4, Stan +46.6, opponents −68.5 ea), gold/XP mirroring the live grant paths, plus game 7 (series-less) and Stan's lost casual vs enoch (bug #65).
  - `116_more_body_colors_wave3.sql` — 12 new body colors: yellows (Lemon, Mustard, Gold), greens (Forest, Olive, Lime), skin tones (Porcelain, Tan, Sienna, Umber), reds (Scarlet, Maroon).

### July 13 round 6 (1v2 polish: sub-tab drift, Discord beacon, extra-pick clarity + FFA preview tab)
- **Multiplayer sub-tab drift fixed** — the 2v2/1v2/FFA sub-tab bar rendered progressively lower per tab because 1v2 (padT 14) and the FFA placeholder (padT 40) parked the shared bar's anchor inside their padded content panels, while 2v2 anchors it in an unpadded outer wrapper. All three tabs now use the outer-wrapper pattern; the bar sits at the same top position everywhere.
- **1v2 Discord queue beacon** — joining the 1v2 lobby now posts to #ranked-looking-for-people like 1v1/2v2: "⚔️ NAME (elo) is searching for 1v2 — X/3 in the lobby!" (new `/ovt/queue/recent-joins` endpoint + its own guarded bot loop; the elo shown is the player's 1v1 rating, and the lobby count only counts live pollers so ghost lobbies never advertise).
- **"Solo Extra Initial Pick"** — renamed from "Solo extra pick" and the tab now explains the actual rule: the solo gets one extra card in the game's FIRST draw only, and it's ON for the match if ANY of the three lobby members enabled it (the server ORs it across the lobby — conflicting choices resolve to ON). Still labeled as not-applied-in-game-yet.
- **FFA tab v0** — the "Work In Progress" placeholder is now a real design-preview page: IN DEVELOPMENT disclaimer, the locked ruleset (4-player every-man-for-himself, last-standing rounds, first to 5, single games, the rolling 5-card bar, non-winners pick, unranked launch with full recording), and an honest "why it isn't out yet" (the card-removal netcode needs its Sandbox test matrix first). No queue controls until the mode ships.

### July 12 round 5 (1v2 finish: team-split forcing + queue visibility)
- **1v2 team-split forcing — the #1 in-game gap, now wired end-to-end.** ready_join computes each client's slot (solo=0/team 0; duo=1,2/team 1 in the server's duo_a/duo_b payload order — identical on all three clients, no sorting needed), publishes `p_id`/`t_id`/`u_id` + styled NickName + cosmetic props BEFORE the Photon join (the 2v2 no-race pattern), and the CreatePlayer override now covers `ovt_` rooms with strict mode-matching (an ovt room only honors the ovt slot, a cr_ff room only the 2v2 slot — a stale slot from the other mode can never mis-map teams). The whole 2v2 join/spawn machinery is now mode-aware via `Diag2v2.SlotToTeam()`/`PlayersNeeded()`: late-joiner GM_ArmsRace activation, LoadingScreen clear, force-StartGame at 3, extended card bars, auto-spawn (slot 2 never sees a character-select prompt), team skin mapping (solo orange, duo both blue), the skin re-bake guard, the team crown patch (solo leader = one crown, duo leaders both crowned), and the spawn-point sort.
- **1v2 queue visibility (2v2 parity, Sid's ask):** the tab now has a live lobby panel — every queuer with their 1v1 + 2v2 elo, side preference / locked side, extra-pick flag, status, and time in queue — plus a locked-lineup line ("Solo vs A + B") and a 2s-ticker refresh. New `GET /ovt/queue/list` powers it.
- **Queue robustness (server, curl-verified live incl. a full lock + timeout cycle):** ghost-prune — a crashed client's silent 'searching' row used to LOCK into a dead 3-player series (the lock query had no staleness filter); dead-lock self-heal — a lock >2 min old with no game reported cancels the series (`assembly_timeout`) and resets the lobby to searching instead of re-feeding clients a dead room; join now snapshots the 1v1 elo as fallback_rating.
- **Queue polling survives menu close** — the 1v2 poll now ticks from the plugin-level loop like 2v2's (it was tab-11-only: queueing then closing F5 meant never receiving ready_join).
- **Region fix** — 1v2 queue join now reports the client's Photon region; every 1v2 room previously pinned to "us".
- **ovt room watchdog** — the never-filled-room watchdog (learning #102) now covers `ovt_` rooms (3 arrivals, 35s notice, 90s penalty-free bail) — 1v2 has no server-side assembly timeout, so this is the only escape from a no-show.
- **Stale-slot hygiene (also fixes a latent 2v2 wart):** joining a room of the other mode now clears the leftover pending slot — previously a 2v2 slot lingering after a series kept the slot→team skin mapping active in later casual rooms.
- **Solo extra pick:** recorded on the lobby/series but NOT yet applied in-game; the tab now says so explicitly.
- **Round-5 adversarial review (19 raised / 13 confirmed / 6 refuted) — all confirmed findings fixed:**
  - *(critical)* the first cut of the dead-lock self-heal could cancel a LIVE series mid-game-1 (zero recorded games + >2min lock age is exactly what game 1 looks like; one mid-game "Join" click triggered it). Now: locks dissolve at their real end-of-life instead — `/ovt/queue/leave` cancels a zero-game lock and resets the lobby; the room watchdog and failed-join give-up both call it; the self-heal is a 10-minute last resort with a status-guarded cancel; and the Join button hides while locked so the trigger is gone.
  - *(high)* consent guard — the 1v2 queue has no ready-up step, so a lock landing hours later could yank a player out of a live ranked match (DC against them). Queueing from inside an online game is now blocked, and a lock that lands while in another room is declined (auto-leaves the 1v2 queue + dissolves the lock + notifies).
  - *(high)* the widened team-mode gate armed the 2v2 DC reporter in ovt_ rooms, where a stale `ActiveTeamSeriesId` from an earlier 2v2 sitting could receive a real Glicko-applying DC report from a 1v2 rage-quit. The DC block is now strictly non-ovt.
  - *(high)* a husk lock was unescapable (Leave hidden once locked, server re-fed the dead room forever) — Leave now shows while locked and dissolves.
  - *(medium)* the 20s ghost-prune would mass-evict every live queuer after any >20s API gap (every backend redeploy) and could deadlock two recovering pollers — now 75s + SKIP LOCKED, with the lock query independently requiring fresh polls (10s), a 3h husk sweep, and the client auto-rejoining once if its row vanishes while searching.
  - *(medium)* ovt card bars mapped duo_a's picks onto the solo's side of the screen — 1v2 now uses a 3-bar layout (solo left, duo right + right-lower).
  - *(medium)* 1v2 leaderboard rows went permanently blank after a menu-page rebuild (pooled rows never cleared — pre-existing bug); failed joins left the tab stuck on "Match found! Joining…"; leaving an ovt room now clears the sitting state on all three clients; a canceled lock no longer 409s the sitting's continuation; "5/3 in lobby" cosmetics.

### July 13 round 4 (1v2 build + cosmetic fixes + bug batch #71-75)
- **1v2 (solo vs duo) — server complete & deployed + adversarially reviewed, client built (first playtest pending)**. Launches UNSCORED (stats tracked for retroactive ranking). Server (migration 120, all curl-tested): consent queue (no Elo band), 3-player lock assigning 1 solo + 2 duo by preference, match report with gold/XP (no rating) + full replay recording, continuation (recording-gap fix from day one), series-active, unranked leaderboard. Client: `ovt_` rooms are competitive rooms, `playersNeededToStart=3` + MaxPlayers=3, a functional 1v2 tab (queue + side preference + solo-extra-pick toggle + live lobby status + leaderboard), room auto-join on lock, match-end report routing (solo vs duo from in-game team sizes). A 4-dimension adversarial review workflow (16 findings, 12 confirmed) then caught and fixed: the room MaxPlayers=2 blocker (3rd player couldn't join), a queue-lock stranding race, four 1v1-path leaks into ovt_ rooms (report fallback / session tally / BO3 HUD / DC leave-%), the unwired continuation, and server hardening (reporter-first score parity, empty-room dedup bypass, atomic XP, trio validation). **Known #1 in-game gap (documented for playtest):** 1v2 doesn't yet FORCE the 3-player team split — needs the t_id-publish + CreatePlayer override 2v2 has. **FFA deliberately deferred** — its rolling card bar is untested card-removal netcode flagged as the top risk; needs a Sandbox test matrix, not a rushed ship.
- **Cosmetics**: 8 more (Demon Wings + a 7-item house batch incl. 2 more animated); six flagged items enlarged; Tattered Cape redrawn front-view; the ship/pack skills now always bundle the art.
- **Bug #71** — bought cosmetics didn't appear in the editor: GitHub-DLL installs never received the art folder; the mod now self-bootstraps cosmetics.zip from the latest release (mirrors card art) + /ship always attaches it.
- **Bug #72** — My Stats hover regions dead until refresh (width froze before text layout; now computed live) + score-graph labels clipped (taller rects + overflow).
- **Bug #73** — shop Artist sub-tab sometimes unclickable: the click de-dupe guard was global; now per-control.
- **Bug #74** — animated cosmetics static in the shop thumbnail; now cycled at the item's fps.
- **Bug #75** — artist price/stock popup click-through: the mod's custom click handler polls the mouse directly and bypassed the uGUI blocker; it now respects modal state.

### July 13 round 3 (design lock + cosmetics batch)
- **1v2/FFA design locked**: all six open decisions answered (no 1v2 handicap + optional solo extra initial pick as a lobby toggle; unscored launch with full stat recording for retroactive ranked; FFA single-games with explicit UI labeling; 3-or-4 players at launch with everything count-parameterized for 5-6 later; rolling bar FFA-only; separate tabs). FFA player-count feasibility verified against the decompile (spawn-point synthesis is the only hard 5+ blocker). `docs/design-1v2-ffa.md` updated; next pass builds 1v2 end-to-end.
- **Demon Wings cosmetic** — source art processed into pipeline shape (painted checkerboard backdrop keyed out via flood-fill + enclosed-hole punch, cropped, 512px real alpha).
- **Seven more house cosmetics** (each reviewed against the art checklist): Thorn Crown, Sunburst Halo, Knight Great-Helm, Rally Flags, Tattered Cape, and two more ANIMATED items — Dark Aura and Energy Orbs (4 frames @ 7fps). All eight round-3 items in migration 119; art ships with the client (34 cosmetic files total).

### July 13 round 2 (Sid's five-item batch)
- **Leaderboard channel "not posting" (final)**: publishes were landing (proven by the new per-tick logs) but an EDITED Discord message never moves down the channel and keeps its original post date — the board was literally buried under newer messages. The embed now carries a live "Updated X minutes ago" timestamp, and any tick that finds the board non-bottom deletes + reposts it at the channel bottom (deployed; first tick confirmed: "board was buried — reposted at bottom").
- **Shop UX**: click any row to highlight it (whole-row tint, click again to clear); face-cosmetic art doubled to 80px with taller rows; artist filter tabs upsized 13pt/120×24 → 16pt/150×30.
- **Six new house cosmetics** (migration 118 + catalog + art): Crazed Eyes, Yin & Yang, Devil Horns, Alien Antennae, and the first two ANIMATED items — Storm Halo and Flame Crest (4 procedural frames @ 8fps through the `__fN` pipeline).
- **Stan granted admin** (migration 117).
- **1v2 + FFA groundwork**: full design in `docs/design-1v2-ffa.md` — what reuses from 2v2, the two-team-scoring constraint, the FFA rolling 5-card bar mechanism (deterministic FullReset+reapply at pick-phase barriers, guarded by the delegate sweep), server table shapes, risks ranked, and 6 decisions queued for Sid.

### Client (built, unreleased)
- **Bug #58 — 2v2 card-pick bodies missing/wrong**: the anti-stack X-spread applied a LOCAL offset under CardChoiceVisuals' 33×-scaled root — solo-pick bodies parked at world X=−198/−66 (proven 34/34 in the 7/12 log). Spread removed entirely (only one body ever exists — vanilla destroys the prior clone per Show); tint/face/body-check kept.
- **Bug #70 client hardening**: match-end now re-requests the continuation series and defers the report instead of dropping the game when no series id is held.
- **Bug #65 — report outbox**: match reports that exhaust their immediate retries queue to disk and re-send every ~60s (dup-safe via the server's unique room+players constraints).
- **Bug #64 — Tab board stale cards**: vanilla's rematch reset never clears `currentCards`; the board now baselines at each `Player.FullReset` and shows only this game's picks. Same investigation found `GM_ArmsRace.StartGame` never fires on same-room rematches — the #92/#103 block-delegate sweep now also runs from `PlayerManager.ResetCharacters` (the hook rematches actually call).
- **Bug #69 — 100% accuracy**: DOT ticks carry the same weapon object as direct hits and were pumping `bullets_hit` to the cap; hits now count only at `ProjectileHit.RPCA_DoHit` (direct, unblocked, enemy impacts).
- **Bug #67 — effect preview**: rebuilt as an IMGUI-simulated particle preview (draws above the menu by construction — no cameras/RT/menu fade); parameters mirror each SKU's real aura.
- **Leaderboard tab freshness**: switching to the tab always refetches, a 30s ticker refreshes while open, and completed fetches now repaint even when the row count is unchanged.
- **Bug #68 client half**: admin Recent Ranked Series renders one line per game (G1/G2/G3), rows auto-grow.

## v1.30.1 — RELEASED 2026-07-12 (same-day patch)

- **Bug #62 (lopidav) — cursor click point offset**: ROUNDS' vanilla cursor is a target/crosshair icon (`streamline-icon-cursor-target-1@32x32`) whose hotspot is its CENTER; the tinted default-shape cursor shipped with an arrow-style top-left hotspot, so the actual click landed at the crosshair's top-left corner. Hotspot now = texture center.
- **Bug #63 (lopidav) — unreadable dark shop names**: item NAME colors get a lightness floor (dark hues lerped toward white); swatches/art keep the true color.
- **Star Earmuffs art corrected** — the artist's intended composition (wider flat band, muffs at the edges, larger stars).
- Build hygiene: shipped DLLs are deterministic and symbol-free.

## v1.30.0 — RELEASED 2026-07-12

The biggest release since ranked launched. Everything under the `v1.30.0-dev` sections below shipped in this version; highlights:

- **Community character cosmetics**: artist-made faces/accessories (animated supported) in ROUNDS' own character editor; artist roles with price/stock/gift/block controls, an **in-game submission + admin review pipeline**, and the first two community items (Sprout by lopidav, Star Earmuffs by Nix ツ). Custom cursor colors now tint ROUNDS' original cursor shape.
- **Hold-Tab live match scoreboard** (TabInfo-style): every player's live build stats + card lists.
- **Achievements expanded to 40** (from 13 visible), with migration 113's retroactive backfill: 106 grants / 50 players / 10,600g paid. Instinct false-positive fixed (bug #60).
- **Navigation overhaul**: grouped tabs (Compare under Leaderboard, Artist under Shop, Multiplayer = 2v2 + 1v2/FFA placeholders), sub-tab row anchored inside panels, leaderboard layout truly centered (learning #132), Series-vs-You pager beside its section.
- **My Stats**: per-game length beside Hit%, live-tracking hover regions (bug #61 — no more drift while scrolling), score-history hover graph.
- **Shop/UX**: artist filter boxes + bylines, effect previews composited above the menu via a dedicated RT pass (with self-diagnosing fade fallback), Your Recent Bets (3-day window), player name-search (elo-verified) for gifts/blocks/admin grants, 12pt global font floor, readable Compare achievement grid.
- **Server**: `/players/search`, match-history `duration_seconds`, pristine/silent-drill combo keys fixed (never matched prod card names), 2v2 crown for both team members, single-worker + chat/online fixes (#51/#52), custom-lobby instant lock (#57), and the July 11 batch (#50–#59) documented below.
- Backfills/migrations this release: 107–114.

# Sid's Competitive Rounds — Changelog

## v1.29.1 — 2026-07-07 — RELEASED — ranked-attribution root fix + July 7 bug batch (#44–#50) + dark map backgrounds

> Migrations 104/105/106 applied 2026-07-07 (snapshot `cc_pre-mig-104__20260707_122159`). Backend deployed + client shipped same day. `MIN_MOD_VERSION` stays 1.28.2 (no forced update). Bug-comments posted on #44/#45/#46/#47/#48/#49/#50.

**Map backgrounds — dark/black-walled skins go pitch-black (Sid)**
- **Charcoal, Obsidian, Blackwood, Abyss** (+ **Aurora** premium) now render pitch-black / dark-smoky backgrounds instead of the old grey fog. Root fix, not just palette: `ApplyLighting`'s SFLight sky floor was a hard `+0.22`, so even a black background lifted to grey. The floor now scales with background luminance — normal/light skins are pixel-identical to v1.29.0; near-black backgrounds sink toward 0.04 so they read as actual black. Charcoal exposure deepened −0.60 → −0.72.
- **Wall-vs-background separation** audited across all 26 custom skins: every skin now has ≥31/255 max-channel distance between its background and closest wall color (Monochrome's bg was 1/255 off its dark wall — pushed to darker smoke). Reference: `docs/map_skin_colors.xlsx` (designed + on-screen-derived swatches per skin).

**The Slarn case (#47) — ranked games recording casual / "missing"**
- **Data backfill (mig 104, LIVE)**: 4 games from 7/7 flipped casual→ranked and attached to series — A_pancake game 1 (08:32) into its sitting's series, Catus games 1+2 (10:47/10:51) as a new completed 2-0 series (Glicko period + rating_history + 12g series-win gold applied, values computed offline), Catus game 3 (10:59) into the sitting's next series. XP corrected to ranked rates (+748 Sid, +375 Catus, +125 A_pancake).
- **Root cause, server (code)**: match reports now re-evaluate rankedness server-side. A live series for the pair keeps the report ranked even if a flag flipped mid-series (late startup sync / mid-series toggle can't void a BO3); a casual-claimed report between two mod-seen, ranked-enabled players upgrades to ranked (kills every client race: props lost on join, /mod/check vs preflight registration, opponent's startup sync landing mid-game). Deliberate opt-outs (`ranked_enabled=false`, no live series) still record casual.
- **Root cause, client**: report forces `isRanked=true` when a live series id exists for the room's pairing (id now cleared on room leave, mod-opponent-gated); consent revoke no longer permanently disables ranked (tracked via `RankedDisabledByConsent`, auto-restored + re-synced on re-grant — the silent trap that left players unranked forever); the "casual match" toast now always fires (was swallowed when the preflight beat the mod-check), names the opponent, and says how to fix it.
- **"Missing game" explanation**: the one slarn game played before the report WAS recorded (17:35, ranked, in series). The confusion was the `Series: 0-1` toast after Sid **won** game 1 — the score was in series-row order (slarn happened to be p1). Match-report responses now orient series_score reporter-first.

**Bug fixes**
- **#44 (Compare shows "Regicide")** — `/achievements/{id}` never included display names; the client prettified raw keys. Entries now carry `name` from ACHIEVEMENT_DEFS. *(server)*
- **#45/#48 (Current Rank title renders literally)** — the dynamic-title override now runs at the three missed render sites: match history opponent titles, 2v2 recent-series slots (resolved against 1v1 rating), 2v2 leaderboard. *(server)*
- **#48 (rank title looks unequipped in shop)** — equip state compared shop-item NAME to the served title, but the dynamic title rewrites the name to the live rank. Stats now expose `active_title_sku`; shop compares by sku (name fallback for old payloads). *(server + client)*
- **#46 (Disable button vanishes after Sandbox)** — Photon OfflineMode counts as "in a room" and lingers at the main menu after leaving Sandbox, so `inGameMode` stayed true and hid the button until relaunch. New `IsInOnlineRoom` accessor excludes offline mode. *(client)*
- **#49 (title names collide with rank tiers)** — shop titles renamed **Beginner→Noobie**, **Grandmaster→Expert** (mig 105, LIVE; skus unchanged).
- **#50 (Keys/Sec + Keys/Game not registering)** — input sampling ran inside the 10 Hz poll, but Unity's `*Down` APIs are per-FRAME edge triggers: whole games recorded ~8 active seconds / ~30 keys (prod data: 294s game → 7.7s/31). Sampling moved to the per-frame tick, counts gameplay keys only (WASD/arrows/space/L+R click) during active combat, and adds a **macro detector** (1s windows ≥25 events → advisory `suspected_macro` flag at ≥10 windows/match). Old under-counted data reset (mig 106, LIVE); server ignores key metrics from pre-1.29.1 clients so the clean baseline can't re-pollute. *(client + server)*

**Schema changes** — mig `104_backfill_unranked_first_games.sql` (data repair, see above); mig `105_rename_overlapping_titles.sql`; mig `106_macro_counter_reset_key_metrics.sql`: `matches.local_macro_suspect_seconds` + key-metric reset.

## v1.29.0 — 2026-07-06 — RELEASED — features + July bug sweep (rolls up the unshipped v1.28.3 client)

> Backend deployed 2026-07-06 (snapshot `cc_cc-v129-pre-migrate__20260706_092540`; migrations 102 + 103 applied). Client released as **v1.29.0** same day after 8 rounds of map-rendering iteration with Sid. `MIN_MOD_VERSION` stays 1.28.2 (no forced update). Bug-comments posted on #28/#29/#36/#37/#38/#39/#40/#41/#42/#43.

**Round 9 (release polish)** — premium twinkle slowed to a 1.6s drift with 1-in-3 glint (was 0.45s / half — read as strobing).

**New features**
- **Online counter (F1)** — queue tab shows "N online" next to the queue count. Client pings `/presence/ping` every 60s from the always-on loop; `/queue/count` also stamps presence and returns `online`. In-memory on the server (no DB writes).
- **Achievements (F2)** — *Regicide* renamed **Sid Slayer** (same key, rows intact). New **Stan Slayer** (beat Stan `76561198983423367` in a ranked series — `SLAYER_TARGETS` map, extensible) and **Grand Master** (2330+ rating, 1v1 or 2v2; granted at every Glicko-update site). Migration backfilled 2 Stan-slayers + granted the slayer TITLES to all achievement holders.
- **Compare tab (F3)** — new metrics: Top Streaks (ranked/casual, grouped bars), 5-0s Given/Taken, Bets Won/Lost, Keys/Sec, Avg Game Length, 2v2 Rating, and an **Achievement Grid** (per-achievement YES/– table per selected player). Server: stats response adds `avg_keys_per_sec`, `avg_game_seconds`, `bets_won/lost`, `bet_gold_net` (refunds excluded), `team_rating`, `rank_name/color`. Client tracks keystrokes (anyKeyDown) + active-combat seconds per match, reported as `local_keys_pressed`/`local_active_seconds` (advisory, not in HMAC).
- **Multi-language support (F4)** — runtime TMP fallback fonts built from installed OS fonts (Segoe UI + CJK families) appended to the game font's fallback table + TMP_Settings. Cyrillic/CJK Steam names and chat now render instead of squares. No ASCII stripping existed anywhere — this was purely a glyph problem.
- **Booster gold (F5)** — Discord boosters get **2000 gold/month**. Bot sweeps `guild.premium_subscribers` every 12h → `/internal/booster-grant`; idempotent per (discord_id, month) via `booster_grants` unique constraint. Unlinked boosters get a one-time DM nudge to `!link`. (Discord doesn't expose per-member boost count — one grant per boosting member.)
- **Custom bet amounts (F6)** — in-game: "..." button on every bet row opens an amount prompt (1–100,000g, Enter to place). Discord: "Custom on X..." buttons open a modal. Server already accepted arbitrary amounts.
- **Rank titles (F7)** — leaderboard rating column is colored by rank tier; player detail shows "Rank: Master V" in the **live Discord role color** (bot pushes all 25 role colors to `rank_role_colors` on start + every 6h; verified 25 pushed on deploy). New free shop title **"Current Rank"** (`title_rank`) renders as your live tier name+color everywhere titles show (leaderboard/chat/stats) and updates automatically on rank change. **Sid Slayer** / **Stan Slayer** titles are achievement-granted, non-purchasable (`rotation_pool='achievement'`).

**Bug fixes**
- **Shield Charge dead after ranked reconnect (#39/#40)** — proven in lopi's log: aborted `ShieldCharge.OnDestroy` leaves its `ShieldChargeCollide` key in ChildRPC's dictionaries → next game `Start()` throws duplicate-key and aborts BEFORE the Block subscription (blocking fine, charge dead). The StartGame scrub now also removes dead-target entries from ChildRPC string→delegate dictionaries. *(client)*
- **Orange pick-body invisible in 1v1 ranked (#29)** — the 2v2 anti-stack X-offset (picker 0 → X=-6) ran in ALL competitive rooms and shoved the 1v1 visualizer body off-camera while the face applied to the un-moved root. Offset now cr_ff-only. *(client)*
- **Jump-to-join stuck (#37)** — spawn guard was correct but unbreakable: stale game scene + no room = suppressed forever. 30s continuous suppression now triggers NetworkRestart → clean menu return with a notice. *(client)*
- **Velvet walls invisible after Shift (#28, second attempt)** — burst re-fire via Clear+Simulate(0)+Play is unreliable; now live particles are recolored **in place** (GetParticles/SetParticles) with zero clearing — nothing can go invisible on any emitter type. *(client)*
- **Map backgrounds grey/blue (B1)** — every map-color SKU now has a hand-picked vivid backdrop hue (same family as the primary, shifted so walls/bg don't blend; mono/charcoal stay neutral). Scene-wide colorFilter lean eased 0.6→0.42 so backdrop hues survive the multiply. *(client)*
- **F5 lag for both players (B2)** — three fixes: cosmetic Photon publishes only fire when the cosmetic set actually changed (was 5 broadcasts to every client per menu open — the opponent-side blip); match-history parse spread across frames (~80 entries/frame instead of 2000 in one hitch); ForceUpdateCanvases only after a fresh page build. *(client)*
- **Series don't resume across sessions (#43)** — undecided mid-BO3s stay the pair's current series for **7 days** and resume at the real score. Stalled series: bets refund at 60 min (unchanged) but the row stays active; abandoned only when the window lapses (`series_expired`). `/series/active` liveness is now activity-based. **LIVE.**
- **Refunded bets showed as losses (#41)** — refunds (payout == stake) are excluded from Recent Ranked Series. **LIVE.**
- **Bets created for ranked-disabled players (#42)** — preflight/match-report no longer force-enable `ranked_enabled`; preflight returns `not_ranked` (no series/ping) and reports downgrade to casual when either player opted out (queue rooms exempt — queueing is consent). Client shows "Casual match" notice. **LIVE** (server), client notice in this build.
- **Bug-report DMs inconsistent (#38) + no Discord bug category (#30)** — root cause: rolling 90s window + in-memory dedup = every bot restart dropped pending DMs (deploys coincide with comment sweeps). Now ack-based at-least-once delivery (`notified_at`/`channel_posted_at` + `/internal/bug-reports/events/ack`). Every bug report now gets its own **thread** in the feed channel with comments/status changes mirrored in. **LIVE.**
- Bets endpoint now enforces the "locked once any game is decided" rule it always displayed. **LIVE.**

**Schema changes** — migration `102_v129_titles_presence_compare.sql`: players.keys_pressed_total/active_seconds_total, matches.local_keys_pressed/local_active_seconds, bug_report_events.notified_at, bug_reports.channel_posted_at (+backfills), tables `rank_role_colors` + `booster_grants`, 3 title shop items, slayer/GM backfills. Migration `103_premium_map_colors.sql`: Gilded/Platinum/Aurora shop items.

**Round 2 (same session, Sid's follow-ups)**
- **Bet cap**: max bet is now **2,000g** on every endpoint (1v1 / 2v2 / Discord) + both custom-amount UIs. **LIVE.**
- **New achievements visible**: the client's hardcoded `AchievementDefs` mirror was never updated — Sid Slayer rename + Stan Slayer + Grand Master now show in the Achievements tab and leaderboard detail. *(client)*
- **Avg Game Length decimals**: bar labels show `5.4m` instead of rounding to whole minutes (Keys/Sec also gets F1). *(client)*
- **"Elo over time"** compare metric: same line graph, x-axis is the real calendar (date gridlines) instead of game index. Snapshot dates now parsed from `recent_rating_history`. *(client)*
- **Leaderboard shows everyone**: server limit cap 200→500, client fetches 500 (was 100 — cut the board at 100/105); existing prev/next pager handles pages. **LIVE** (server) + *(client)*.
- **Maps, the REAL background**: `ArtHandler.m_background` is a dedicated sky GameObject our tints never touched — the vanilla blue backdrop leaked through everything (why "green skins turned blue" after the colorFilter was eased). New sky tint pass colorizes its renderers toward the skin's background color, with vanilla-restore when a default skin is active. Palette redone per Sid: only dusk/obsidian/abyss stay blue; **Forest bg is brown**; Mono/Lavender/Pine/Charcoal backgrounds are same-family-darker than their walls; the rest complement their walls. Velvet + Forest get the Magma-style dark "shadow" mood. *(client)*
- **Premium skins**: **Gilded** (8,000g — molten gold glinting to white-gold), **Platinum** (12,000g — silver glinting to pure white), **Aurora** (10,000g — teal↔violet northern lights). Walls emit random-between two colors per particle (the per-particle shimmer that was a bug for normal skins is the premium effect). Shop items **LIVE**; rendering ships with the client.

**Round 7-8 (bloom to "right above 0" + the green cast's true source)**
- Bloom capped at intensity 1.2 with a NEUTRAL white tint + higher threshold on every skin profile (Sid: effect "right above 0"); wall slabs dimmed to sub-bloom brightness. *(client)*
- **The universal green cast was ours** (learning #119): the round-4 "tint every SolidColor camera" pass was overwriting the SFSS **LightCamera's** clear color — RGBA(1,0,0,0) is the light/shadow buffer's init value, not a backdrop — corrupting the lighting buffer on every skin. Off-screen cameras (targetTexture / Light-named) are now restored and permanently left alone; the stencil-utility quad is likewise excluded from scenery tints. *(client)*

**Round 6 (the log names everything — learning #118)**
- The scene sun-light is `radius=0.5, intensity=10, PURE BLUE` — the round-5 "big light" filter (radius ≥ 20) skipped exactly the light that paints the sky, leaving the master blue source untinted; its blue × per-art backdrops also produced the mystery casts (blue × Gold-art yellow = Sid's green screens). Light detection now keys on intensity/parallax — the last blue source is tinted. *(client)*
- The `OutOfBounds/*` "walls" we've tinted since v1.26 are actually the **players' out-of-bounds warning effects** (7 per player, `playing=False` by design). The old restart code force-played them (that's what the colored border beams ever were) and clearing them was the REAL invisible-walls bug. Pass retired — warnings return to vanilla red; the skin's visible walls are the base art's glow slabs, which now carry the **primary/secondary two-tone**. *(client)*
- Premium sparkle rebuilt as requested: sub-bloom brightness (caps 0.85/0.95 — no more floodlights) + an actual **twinkle loop** (re-rolls which particles glint every 0.45s). *(client)*
- Pine + Forest secondaries switched from rust/bark browns to greens (walls stay green; Forest's brown lives in the background). *(client)*

**Round 5 (SFSS lighting + honesty pass)**
- Round 4's camera fix was a **no-op** — Sid's log shows MainCam clears Depth only, so backgroundColor is ignored. The real background system is **SFSS 2D lighting**: the sky is a backdrop lit by the big SFLight, the shadow beams are `SFRenderer._ambientLight` (tooltip literally suggests "a darker grey, **blue**..."). Now the big light gets a bright version of each skin's background and the ambient a dark version — sky + shadows take the designed hue, walls/geometry keep theirs. Camera + backdrop-quad tints kept as belt-and-suspenders. *(client)*
- **Blinding premiums fixed**: near-white wall colors × 1.6 lift = HDR bloom blowout. All lifted colors now brightness-capped (≤1.15) and the sparkle glint is a subtle Lerp toward the sparkle color, not a white-hot second color. *(client)*
- **Stale deferred tints fixed** (log-proven: burgundy tints landing after shifting to pine): a deferred apply now skips if the current sku changed during its 2s wait. *(client)*
- **Diagnostics** for whatever remains: `[MAPCOLOR-CAMS]`, `[MAPCOLOR-LIGHT]`, `[MAPCOLOR-BG]` (backdrop inventory with vanilla values), `[MAPCOLOR-WALLDIAG]` (names any wall system that is EMPTY right after a tint pass, with emission state) — one test session pinpoints any still-wrong layer. *(client)*

**Round 4 (the actual background, finally)**
- Round 3's strong filter repainted walls along with the sky ("Forest completely not green", walls == background) — because a colorFilter multiplies EVERYTHING. The real backdrop turns out to be **MainCam's clear color**, an editor constant vanilla never changes (which is why backgrounds never changed on Shift and always leaned blue). Now: **camera clear color = the skin's designed background** (instant on Shift, restored on default skins), colorFilter back to near-neutral (0.30 primary lean, mood only) so walls keep their own colors. Learning #116. *(client)*

**Round 3 (Sid's screenshots + game decompile)**
- **The real scene painter found** (learning #114): Sid's screenshots showed the premiums rendering as three different VANILLA arts even though the log proved the custom path ran. Cause: in ROUNDS, the ColorGrading **colorFilter paints the whole scene** (sky, SFSS shadow beams, geometry — all near-neutral art multiplied by it); our 0.42 grey-lerp was too weak to repaint the base art AND was overwriting every per-preset filter with a primary-derived formula. Now the filter is a **strong (0.80) lean toward each skin's designed background color** — sky/shadows/geometry become the skin's family, walls keep their high-lift primary/secondary through the multiply, and the "still 20 blue maps" problem dies at the root. *(client)*
- **Sparkle made visible**: the glint gradient now also drives the **atmosphere particles** (full-brightness two-color) and the sky object's particles — the border walls alone were too thin to read as sparkle. *(client)*
- **"Keys / Game"** compare metric (avg key presses per game, reporter-side per-match average). **LIVE** (server) + *(client)*.

# Changelog

## v1.28.2 — block/empower root-cause fix, two-tone maps, security hardening

- Fixed block dying after game 1 in ranked AND the "infinite empower" carryover — same root cause (a card's between-games teardown leaving a dead handler on your block/gun). The mod now sweeps dead handlers at game start + each block press.
- Map walls are two-tone again (primary + secondary by segment, e.g. Magma red + amber); backgrounds read more strongly as their named color.
- Performance: removed two stale old-game patches; crash-error swallowers no longer destroy pooled/Photon bullets (a likely stutter source).
- Security review: rate limiting + request cap, HMAC-signed the previously-open state endpoints, server-side speedhack flagging, mod-wide bans (matching a banned cheater leaves the match), hardened match-report/disconnect/admin paths.

## v1.28.1 — block fix (ranked), phantom series scores, hover/refresh fix, Discord feed

- Fixed block in ranked/matchmade games: it could activate but absorb nothing (you'd "block" and still take the hit). Caused by the round-start block reset stripping the block's action delegates each round; now it only rebuilds when a trigger was actually destroyed.
- Fixed the per-series HUD game counter showing phantom scores past best-of-3 (e.g. "4-0") for the non-reporting player; it now self-corrects from the BO3 score.
- Fixed the My Stats card-hover tooltip covering the refresh button — its hover zone was the full (mostly empty) row width and is now sized to the actual card text.
- Discord series feed: win streaks no longer capped at 20 (1v1 + 2v2); rating changes show one decimal so sub-1.0 Glicko moves no longer read as "0".
- Raised bug reports per day from 3 to 10.
- Widened matchmaking-disconnect diagnostics to cover 1v1.

## v1.28.0 — round-start freeze fix, map color rework, Compare charts, cursor shapes

- Fixed a freeze where a player could get stuck mid-screen (no move/block/shoot) and end up off-screen the next round.
- Map colors reworked so each map clearly reads as its named color; Shift shows the map-skin name; cycling no longer auto-shuffles to dull skins.
- Compare tab: up to 12 players, charts for every stat (bars + pie charts), Total XP shown as levels, player search.
- Cursor shape selectable in Settings (default / arrow / dot / crosshair / circle); shop Cursor/Effects/Other tabs; body-color unequip fix; bug-report form click-through fix.

Full notes: https://github.com/SidNDeed/SidsCompetitiveRounds/releases

## v1.27.0 — custom map colors, shop expansion, level rewards, 2v2 series rework, performance pass

Full notes: https://github.com/SidNDeed/SidsCompetitiveRounds/releases

(see GitHub releases for the complete, formatted changelog)
