# Sid's Competitive Rounds — Changelog

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

## v1.30.0-dev (cont. 8) — July 12 round-5/6 leaderboard-layout batch — client only

> Coded + built 2026-07-12 (fifth + sixth pass; Release green, DLL installed). No backend changes.

- **Round 6 — the REAL dead-strip/misalignment root cause**: Unity layout groups inherit their flexible width from their CHILDREN (max), and both leaderboard columns contain pager rows with flexW:1 spacers — so `seriesCol` (400) and `mid` (772) were silently reporting flexibleWidth=1 and stretching ~100px past their preferred widths. That stretch WAS the dead wheel-scroll strip beyond Gold, and since the sub-tab bar centers within the (stretched) column, it also sat ~55px right of the table. Both columns now carry an explicit `flexW:0` (comments mark it load-bearing); the detail panel takes all the leftover and hugs the table.

- **Item 1 — Recent Ranked Series wrap**: long opponent names ("HOLY SHIT IS THAT THE KNIGHT") folded the line and orphaned the elo tail. Names now truncate at 16 chars, the element no longer word-wraps (residue clips at the scroll mask). Font size unchanged (nothing had grown it).
- **Item 2 — dead wheel-scroll strip beyond Gold**: the middle column was 790px vs a 768px table; trimmed to 772 so the leftover goes to the player-detail panel.
- **Item 3 — side panels back to the top (the real fix)**: the sub-tab row is no longer a full-page-width row above ALL panels — it's REPARENTED into a per-tab anchor inside the active panel. On the Leaderboard tab the anchor is the TOP OF THE MIDDLE COLUMN, so Live Ranked Games (left) and the player-detail panel (right) rise back to the tab bar exactly as before the Compare migration, and the Leaderboard/Compare buttons sit precisely over the # → Gold table span. Compare got a VLG wrapper for its anchor; Shop/Artist/2v2/1v2/FFA anchor at their panel tops (full-width, centered). One shared bar, moved on tab switch by UpdateTabBarVisual.

## v1.30.0-dev (cont. 7) — July 12 round-4 batch (5 items) — backend LIVE

> Coded + built 2026-07-12 (fourth pass; Release green, DLL installed). Migration 114 applied (snapshot `cc_pre-mig-114__20260712_050217`) + api redeployed and smoke-tested: `/artists` lists Sid/lopidav/Nix ツ, both new SKUs in `/shop/items`, submissions endpoint live behind HMAC.

- **Item 1 — original cursor shape, tintable**: the earlier "ROUNDS never sets a cursor texture" conclusion missed that the cursor is Unity's PLAYER-SETTINGS default (engine-applied, no SetCursor in the decompile). The cursor code now finds that texture at runtime (small Texture2D named like "cursor"), makes a readable copy via RenderTexture blit, and multiply-tints it — so shape "ROUNDS default" + an equipped color renders the ORIGINAL shape in that color (white art takes the tint fully). Falls back to the drawn arrow only if the texture can't be found, and logs `[CURSOR] vanilla cursor texture: ...` either way.
- **Item 2 — Compare status overflow**: "Selected x/12 — click a player..." was wider than its 204px column and TMP's default overflow spilled it over the graph; now wraps to two lines inside the column.
- **Item 3 — effect preview self-diagnosis**: no `[EFFECT]` lines existed in either session log, so the RT failure couldn't be root-caused remotely. The foreground pass now logs every setup stage, and ONE SECOND after starting it reads the RenderTexture back around the cursor (`[EFFECT-FG] probe`): pixels present → confirmed working; empty → logged with camera state AND auto-falls-back to the menu fade so the preview is always visible. Setup exceptions also roll back to world-render + fade. Next session's log pinpoints the failing layer.
- **Item 4 — leaderboard dead space**: the table was a fixed 560px block CENTERED between two flex spacers (the X'd gaps in the screenshot). Spacers removed, columns widened (Player 250→300 — names now truncate at 20 chars instead of 14 — Rating/W-L/Gold wider too), middle column 560→790, and the sub-tab buttons bumped to 360px so the pair spans ~730px over the table.
- **Item 5 — review-modal contents confirmed**: submission id, name, slot, artist, 512x512 + file KB, queue position, and the decoded art rendered on a grey backdrop, with Approve / Deny-with-note / Next.

## v1.30.0-dev (cont. 6) — July 12 round-3 batch (4 items) — LIVE (migrated + deployed same day)

> Coded + built 2026-07-12 (third pass, same day, Release green + DLL installed; "8 cosmetic art files" now copy to BepInEx). Migration 114 applied + api deployed in round 4.

- **Item 1 — shop byline dedupe**: "by <artist>" now renders ONCE per row (name line); the description-line copy is gone. The desc slot instead carries the stock state, including the new "OUT OF STOCK - artist hasn't opened sales yet".
- **Item 2 — artist cosmetic upload + admin review pipeline**: Artist tab gains **Upload a cosmetic...** + **Open upload folder** (drop PNGs in `plugins/CompetitiveRounds/cosmetic-uploads/` — no OS file dialog in BepInEx, folder-pick instead). Flow: pick PNG → validated (exactly 512x512, real PNG, per-pixel transparency check ≥2% clear pixels) → name it → tag the slot (eyes/mouth/detail) → HMAC-signed submit (base64 body, 1MB cap, max 5 pending per artist). Server re-validates the container (magic bytes, IHDR dims, alpha-capable color type) and stores the art as bytea in new `cosmetic_submissions` (migration 114). Admin tab gains **Cosmetic Reviews...** — a modal with the real decoded art on a grey backdrop, Approve / Deny-with-note / Next. **Approve mints the shop row born OUT OF STOCK (`stock_limit = -1`)** so nobody buys before the artist sets price/stock (purchase rejects with "artist hasn't opened sales"; artist gifting still allowed pre-open); the artist sees pending/approved/denied status lines in their tab. At bundle time the approved art is pulled via `sql-readonly:SELECT encode(png_data,'base64') ...` into plugin/cosmetics/ + a catalog entry — from then on the artist controls it like any of their items.
- **Item 3 — first community cosmetics + artists**: recreated Sid's two attachments as 512x512 transparent PNGs (PIL, 4x supersampled) — **Sprout** (lopidav, 76561198041616199) and **Star Earmuffs** (Nix ツ, 76561199101676330, the 1253-elo Nix). Catalog IDs 1006/1007, art ships with the DLL; migration 114 grants both artist roles and creates the shop rows (750g rare, stock -1 until they open sales).
- **Item 4 — screenshot markup**: sub-tab buttons widened to 300px (span roughly the content width beneath them); the leaderboard detail text is SPLIT into two elements so the **Older/Newer pager now sits directly under the Ranked-Series-vs-You section it pages** (was stranded below Ranked History), and the redundant "Series vs You" label on the pager row is gone. This also resolves round 2's truncated item 9.

## v1.30.0-dev (cont. 5) — July 12 round-2 batch (10 items) — backend LIVE, client pending ship

> Coded + built 2026-07-12 (second pass, same day, Release green + DLL installed). **Migration 113 APPLIED** (snapshot `cc_pre-mig-113__20260712_035227`): 106 new achievement grants across 50 players, 10,600g paid — rising_star ×22, controlled_burst ×13, double_glass ×13, flawless ×7, immortal/on_fire/unstoppable ×2 each (Sid + Stan); slayers/master keys showed 0 new because inline grants already covered everyone. **Backend redeployed + smoke-tested** (`/players/search` live with exact-first ordering; history rows carry `duration_seconds`).

- **Items 1-3/8 — sub-tab polish**: sub-tab buttons are centered (flex spacers both ends) and bigger (180×26 @ 14pt); the 42px title banner slimmed to 30px pays for the sub-row's height, so the Leaderboard/Multiplayer/Shop panels sit back at (or above) their pre-reorg position. Per item 8, exact per-group width alignment was dropped deliberately (tab count varies with Admin visibility).
- **Item 4 — typing 't' in the new modals opened chat**: the player-search / artist-input / roster-picker modals are now in the chat hotkey's text-input gate (same fix lopi's Compare-search got).
- **Item 5 — "Your Recent Bets"**: renamed, separated from the Live Ranked Games list with a blank line, and settled outcomes older than 3 days age out (pending bets always show — they're live money).
- **Item 6 — Multiplayer tab moved** to right after Tournaments.
- **Item 7 — animated custom cosmetics**: drop numbered frames beside any catalog PNG (`eyes_star.png` + `eyes_star__f2.png` + `eyes_star__f3.png` ...) and the item animates at 10fps (per-item Fps in the catalog). The frame cycler lives on the hidden template; vanilla's SpawnItem clones the template GameObject for every consumer (body, pick visualizer, menu portrait — verified in the decompile), so every instance animates with zero extra patches. Clients without the frame files just render the static base art — no ID/protocol change.
- **Item 9 — Artist tab thumbnails**: each item row shows the cosmetic's actual art (30px, same runtime sprite pipeline as the shop rows).
- **Item 10 — effect preview TRUE foreground**: replaced the menu-fade stopgap ("bugs out the SCR menu") with a real foreground pass — the preview particle lives on an isolated unnamed layer, a dedicated camera (mirroring Camera.main every frame) renders only that layer into a RenderTexture, and a RawImage on a sortingOrder-30050 overlay canvas composites it ABOVE the F5 page. Clicks pass through (no raycaster); main camera's cullingMask bit is removed while previewing and restored on stop.
- Item 9's trailing fragment ("Series vs You header and Older/Newer buttons") arrived without a verb — awaiting what Sid wants done with them.

## v1.30.0-dev (cont. 4) — Sid's July 12 batch (12 items + bugs #60/#61) — backend LIVE, client pending ship

> Coded + built 2026-07-12 (Release green, DLL installed locally). Migration **113** applied + backend deployed later the same day (see cont. 5). Backend deltas: `/players/search`, history `duration_seconds`, pristine/drill combo-key fix. Claude comments posted on bug reports #60/#61.

- **Bug #60 — Instinct false positive**: vanilla runs an initial pick phase at game start, BEFORE combat; `OnMatchStarted` (fires at combat start) was resetting `achLeftmostViolated`, wiping any "looked at the other cards" violation from that first pick — the pick COUNT got recovered from the pre-match buffer but the violation flag didn't (the asymmetry was the bug). The flag now only resets in `ResetMatchState` (between games). Belt-and-suspenders: the `RPCA_DoEndPick` hook now also breaks the run when the card actually TAKEN isn't slot 0 — covers any path where selection-scroll RPCs are missed entirely.
- **Bug #61 — hover popups drift when scrolling history**: hover regions (card tooltip + score graph) were baked as fixed screen rects at refresh time; scrolling moved the rows but not the rects ("refreshing alleviates it" = re-bake). Regions now carry their source RectTransform + canvas camera + rendered-width fraction and the hit test recomputes the rect LIVE every frame — plus each region clips against its ScrollView viewport, so rows scrolled out of the box can't fire tooltips through the mask anymore.
- **Item 2 — achievement backlog granting (migration 113)**: replays history and grants everything derivable from stored data — card-based combos + sweeps (both server and client lists), stacked_deck (no-win, client semantics), flawless (5 consecutive 5-0s), casual streak tiers (100/200/500), ranked-series streak tiers (25/50/100 — Stan's best run is 144, Sid's 128, so both earn Immortal), slayers (regicide ×3, stan_slayer ×2 pending), rating peaks from peak_rating (rising_star ×22, master ×2, GM ×2). Mirrors `_grant_achievement_inline` exactly: +100g each (only for rows actually inserted — idempotent ON CONFLICT), slayer titles auto-granted. Not backfillable (signals never persisted): untouchable, pacifist, immovable, grounded, instinct, god_build, deep_end, rise_from_the_ashes, comeback_kid; clutch's inline check already covers every row that has a timeline.
- **Server bug found en route: pristine_perfection + silent_drill could NEVER fire** — the combo check looked for normalized keys `PRISTINE` and `DRILL`, but prod cards normalize to `PRISTINEPERSEVERANCE` and `DRILLAMMO` (verified via match_cards). Fixed with aliases (incl. the rare `SNEAKYBULLETS` variant); the backfill grants the historical ones (4 + 1 players).
- **Item 3 — hold-Tab live stats scoreboard** (TabInfo/Infoholic port, new `TabStatsOverlay.cs`): hold Tab during any game for a per-player column view — HP, lives, damage (Infoholic's ×55 formula), attack speed, reload, ammo, bullets, bursts, bounces, bullet speed/slow, knockback, spread, lifesteal, block CD, block count, regen, move speed, jump height/count, size, plus each player's card list. All live per-frame reads (the originals' stat catalog); team-colored names; hidden while F5/chat input is open; IMGUI, zero uGUI interaction.
- **Item 4 — game length in history rows**: `m:ss` renders left of the Hit% block in Casual/Ranked history (duration-only for rows without combat telemetry). Server sends `duration_seconds` (COALESCEd with legacy `match_duration`) in `/players/{id}/matches`.
- **Item 5 — Revoke Artist lists artists**: the admin Revoke button now fetches `/artists` and opens the roster picker (upgraded from a `<` cycler `>` to a scrollable click-list showing name + steam id) with a "Revoke" action; Grant Artist uses the new player name-search instead of raw Steam64 entry.
- **Item 6 — effect previews behind the menu**: root cause — a WORLD particle system can never composite above a ScreenSpaceOverlay canvas, whatever its sortingOrder (the 30500 attempt was structurally dead). The F5 page now fades to 16% alpha (CanvasGroup) while a player-effect preview runs — aura fully visible following the cursor, buttons still clickable — and restores on stop/close.
- **Item 7 — tab reorganization**: two-row navigation. Top: My Stats · Leaderboard · Tournaments · Card Stats · Achievements · Shop · Multiplayer · Admin · Settings (Settings last, Tournaments after Leaderboard, Admin gated). Sub-tabs: **Compare under Leaderboard**, **Artist under Shop** (artist-gated), **Multiplayer = 2v2 / 1v2 / FFA** with WIP placeholder pages for the unbuilt modes. Panel indices are untouched internally, so every per-tab ticker/fetch keeps working.
- **Item 8 — Gift via player search**: Gift (and artist Block, and admin Grant-Artist) opens a name-search modal — type ≥2 letters, live results show **name + current elo + steam id** so a rename-imposter can't intercept a gift (the elo is the tell). New public `GET /players/search` (ILIKE, exact/prefix-first ordering, glicko-joined rating).
- **Item 9 — cosmetics grouped by artist**: clickable artist boxes (All / each artist / House) under the CHARACTER COSMETICS header filter the list to one artist's items; rows show "by <artist>". Filter row appears only when at least one item is artist-credited.
- **Item 11 — Block-a-player button sizing**: the Artist panel VLG force-expands children, so the button spanned the full tab width; it now sits in a non-expanding row at 190×28.
- **Item 12 — Compare achievement grid readability**: the ~40-achievement grid forced 15px rows at 11pt (below ~12pt the SDF font drops thin glyphs entirely). Now split into two side-by-side halves — rows ≥20px at a fixed 13pt bold. Plus a **global 12pt floor in `CreateText`** so nothing anywhere in the menu can render below the glyph-dropout threshold.
- **Item 10 (Stan's duration question) — answered, no code change**: duration counts from the start of round-1 combat (first MOVE PLAYERS END) to game over, one continuous wall-clock span — card picks BETWEEN rounds are included; the pre-game countdown isn't. The pick-free measure already exists separately (`active_seconds`, feeds keys/s).

## v1.30.0 — BACKEND DEPLOYED 2026-07-11, CLIENT NOT YET SHIPPED (more client work incoming)

> **Backend is LIVE** as of 2026-07-11 (snapshot `cc_pre-v1_30-backend__20260711_180859`). Migrations 109/110/111/112 applied + verified; `docker compose up -d --build api bot` done from the copied-up source. `MIN_MOD_VERSION` stays 1.28.2 and `LATEST_MOD_VERSION` stays 1.29.1, so current 1.29.1 clients are NOT prompted to update to a release that doesn't exist yet — the client half ships later as **v1.30.0** once Sid's remaining features (a follow-up session) land and it's playtested.
>
> **Live now for everyone (even 1.29.1 clients):** the single-worker compose fix (#51 online counter + #52 chat propagation — verified: 20/20 parallel `/queue/count` reads agree, chat WS registry is one process); #53 bet `vs_name`; #57 custom-lobby instant lock; server-side card-combo achievements (card-based ones grant for 1.29.1 too — the client-detected ones wait for the DLL); ranked/casual streak achievements; gambler-channel bet-outcome posts; the leaderboard-bot reliability rework + `!lb` 20/page; tournament DM/no-show hardening; the whole artist backend (Sid seeded as first artist, owns the 6 face items).
>
> **Deployed but BLOCKED — needs Sid on Discord:** the FAQ won't post — the bot got `discord.Forbidden` in channel `1159243585309384805`. Grant the bot **Send Messages** (and View Channel) there; the 6 messages are still queued in `pending_channel_posts` (none dropped) and auto-post on the next 30s tick once permission lands. Verify with `sql-readonly:SELECT sort_order, posted_at FROM pending_channel_posts ORDER BY sort_order;`.
>
> **Pending the v1.30.0 client ship (all client-side):** shop previews (face art / map swatches / effect preview / cursor tint) + admin-artist buttons + artist tab; 2v2 crown + card-pick body fixes; tournament in-game banner; per-game stats + score hover graph + `.5` scores; client achievement trackers (Grounded / Instinct / Unkillable / Deep End); bets ledger UI; Recent Series full names; leaderboard detail reorder; tier-list folder button. The local Release DLL has all of it built + installed for playtest.
>
> **Deploy gotcha logged for next time:** `deploy-all` (the ssh verb) only runs `docker compose up -d --build` on the LXC — it rebuilds from the SERVER's copy of the source. It does NOT copy local changes up. The first rebuild this session shipped stale code (endpoints 404'd, workers still split) until the Python + `docker-compose.yml` were scp'd first. Always scp `backend/api/*.py` + `discord_bot.py` + `docker-compose.yml` BEFORE the verb (the `/deploy-backend` skill does this; the bare verb does not). See learning #131.

## v1.30.0-dev (cont. 3) — Sid's July 12 playtest fixes (5 items) — backend portion LIVE, client portion pending

> Coded + built 2026-07-12. Adds migration 112 (applied). Backend items (achievement gating/streaks, artist name/desc/royalty/roster) are LIVE; client items (score display, previews, layout) ship with the v1.30.0 DLL.

- **Item 1 — "6-x" scores**: the winning point lands and the game stops BEFORE the 2-points→1-round conversion resets the counter, so winners carried rounds=5 + 2 residual points and the new half-point format displayed 6. Points ≥2 are now treated as already-counted — in the score format AND the hover-graph timeline (same double-count would have bent the final graph step).
- **Item 2 — achievement spec revisions**: **Unkillable** is now CLIENT-detected from the real gun state at game end (max ammo ≤1 + full reload cycle ≤1.0s + Shields Up + win) instead of a card-name proxy. **Into the Deep End** now requires Abyssal Countdown to be ACTIVATED every round (new `AbyssalCountdown.RPCA_Activate` hook counts local activations per round) on top of first-pick + win. **Flawless** = five 5-0 wins in a row (new `consecutive_sweeps` counter, mig 112). **Pristine Perfection** = 2×. **Silent → Silly Drill** (display rename, key unchanged). New **Field Medic** (5-0 with Healing Field). Ranked-series streaks re-tiered **25/50/100** (On Fire / Unstoppable / new **Immortal**). New casual win-streak tier: **Century Club / Casual Conqueror / Touch Grass** at 100/200/500 consecutive casual wins (new `casual_win_streak` counter; a casual loss resets, ranked games don't touch it). Both counters start at 0 from the 112 deploy.
- **Item 3 — shop/artist round 2**: Artist button now on cosmetics only; effect previews draw ABOVE the F5 menu (sortingOrder 30500 vs the canvas's 30000); vanilla-art skins (Sky, Poison, Gold, ... — presets whose name matches their BaseArt) group together at the top of the map-color list; artists can now edit **name + description** (sanitized server-side against rich-text injection) from the Artist tab, which is where all their controls live; artists earn a **30% royalty** on every sale (gold_transactions `artist_royalty`; per-item + shown as "earned Ng" in the tab); admin item-assignment is now a **picker over the defined artist roster** (new public `/api/v1/artists`), no steam-id typing. NOTE: Sid's grant-artist test failed because none of this is deployed yet — the endpoints + artist_users table only exist locally; the HMAC strings were re-verified client↔server.
- **Item 4 — tier-list button**: moved beside Export Tier List (left side) and renamed **Open Tier List Folder**; the filter buttons stay centered via a matching right spacer.
- **Item 5 — leaderboard detail layout**: the panel is now two text blocks with the pager between them — stats + "Ranked Series vs You" → **Series vs You pager directly beneath the series list** → achievements at the very bottom where they stop crowding the stats.

## v1.30.0-dev (cont. 2) — UNRELEASED — Sid's July 11 feedback batch (11 items)

> Coded + built 2026-07-11 (second pass, same day). New migration 111 pending. Still nothing deployed/shipped — full pipeline: `/migrate 109` → `/migrate 110` → `/migrate 111` → `/deploy-backend all` → playtest → `/ship 1.30.0`.

- **Item 1 — shop previews everywhere**: face cosmetics render their actual PNG art (40px thumbnail) on the row; map skins show primary/secondary/background **color-scheme swatches**; player effects get a cursor-following **Preview** (same UX as trails, same particle pipeline as the real aura, auto-stops when F5 closes). Cursor colors: the OS default arrow can't be tinted (ROUNDS never sets a cursor texture) — equipping a color with the "ROUNDS default" shape now renders the tinted arrow lookalike; unequip restores the true default. Artist byline ("by <name>") was already in. **Admin artist management**: Admin tab gains Grant/Revoke Artist buttons; every shop row gains an admin-only **Artist** button assigning that item to an artist (`/admin/artists/set` + `/admin/shop/set-artist`, admin-HMAC, audited).
- **Item 2 — tier-list export**: new **Open Screenshot Folder** button beside the filters (opens `<ROUNDS>\CompetitiveRoundsTierLists` in Explorer).
- **Item 3 — sync tournament audit + hardening** (never live-tested; ~16 players approaching). Audit answer: players must simply **have ROUNDS open at start time** — the mod heartbeats + auto-connects automatically; no tab-sitting needed (the old lock DM's "ready in the tab" wording was stale and is fixed). Gaps closed: **big in-game banner** (T-15min countdown "stay in ROUNDS" / green "connecting..." / red pulsing "LEAVE THIS GAME (M:SS)" with live forfeit countdown when you're stuck in another room / thin "tournament in progress" strip between rounds) + match-found sound + taskbar flash; bot DMs added for **T-15min pre-start**, **last-90-seconds no-show warning**, and a repeating **"both present but nobody joined the room" stall nag**; lock DM now warns signups running an **outdated mod version** (an old client is version-gated, can't heartbeat, and would silently forfeit); round ≥2 ready-up grace doubled to 10 min (finalists step away while the other semi runs); auto-connect **re-arms 60s after a failed/bounced join** (was one-shot per match per session); the lonely-room watchdog now covers `sct-*` rooms (6-min window vs the opponent's 5-min grace). Round 2/3/4 advancement verified driven by the 30s server tick + the always-on heartbeat loop (learning #50).
- **Item 4 — My Stats history upgrades**: per-game **Hit% / Block% / keys-per-second for BOTH players** under the FPS line (opponent's side rides a new `cr_gstats` Photon prop published every ~3s, reporter ships both sides; migration 111, viewer-relative in the API); hovering a row's W/L score pops a **scoring-history line graph** (green you / red opponent, gridlines per round; timeline recorded per point event, capped 64); the confusing "2-1p" half-point notation is now **2.5-style decimals**.
- **Item 5 — 20 new achievements** (all require winning): hard-card 5-0s picked from live DB win rates — Bullet Hell/Barrage 16.5%, Spray and Pray/Spray 18.7%, Demolitionist/Explosive Bullet 22.4%, Controlled Burst/Burst 22.9%; Unkillable (Shields Up + Tactical/Quick Reload/Echo/Shield Charge); Double Nova, Lumberjack (2x Saw), Pristine Perfection (3x), Silent Drill (Sneaky+Drill), Living on the Edge (2x Glass Cannon), Sustained Power (Empower+Healing Field), Into the Deep End (Abyssal Countdown FIRST pick — the "use ability every half round" part isn't tracked, simplified); Clutch (win from 0-3, detected from the new scoring timeline), Collector (4 copies), Flawless (any 5-0), Rising Star (1700), On Fire / Unstoppable (5/10 ranked-series streak, server-side at completion); Grounded (never jump, client input sampler) and Instinct (left-most card every pick without scrolling — tracked via a new `RPCA_SetCurrentSelected` postfix, ≥3 picks required). Card-combo detection is **server-side at match submit** (reporter's payload covers both players), so the winner doesn't even need the new client.
- **Item 6 — Your-bets ledger polish**: bold 15pt, full words, date, stake, and the full matchup ("7/10  Bet 2,000 gold on ImaMageBro vs Quilvet - refunded, series never finished"). `/players/{id}/bets` now carries `vs_name`.
- **Item 7 — Recent Ranked Series**: full names (no more 12-char cut, word-wrap backstop), 50 series per page so the column stays visually full to the pager.
- **Item 8 — Discord leaderboard reliability**: root cause candidate — the channel publish ran at the END of the 30-min role sync, which made one `/players/by-discord` call PER GUILD MEMBER (~2,500 requests, ~21 min) and dies permanently on any unhandled exception (discord.py stops a tasks.loop on error). Now: role sync uses ONE batched `/internal/linked-players` call, is fully guarded, and the leaderboard has its own dedicated 10-min loop; `publish_lb` remembers its message id (edits directly; the old 5-message history scan lost the board once chat buried it) and falls back to a 25-message scan. `!lb` shows 20/page (was 10).
- **Item 9 — gambler channel outcomes**: when a series with bets completes, the bot posts a "Bets settled" embed (who bet, on whom, won +N / lost) to the live-bets channel.
- **Item 10 — leaderboard detail panel**: the "Series vs You" pager was parented ABOVE the detail scroll view (floated at the top by itself); it now lives inside the scroll content directly under the series list (which is composed last), bigger + bold.
- **Item 11 — FAQ retarget**: posts to channel 1159243585309384805 instead of scr-faq (migration 110 edited in place — not yet applied anywhere).

## v1.30.0-dev (cont.) — UNRELEASED — July 11 bug batch (#51–#59) + artist controls + FAQ + achievement stats

> Coded + built 2026-07-11 (Release green, DLL installed locally), **not deployed/shipped**. New migrations 109 + 110 pending. Needs: `/deploy-backend all` + `/migrate 109` + `/migrate 110`, then ship as v1.30.0.

**The big one — #51 (online count wrong) + #52 (chat doesn't reach other mod clients) share one root cause: the July 7 API deploy runs MULTIPLE uvicorn workers.** Every piece of live state is process-memory (chat WS registry, presence dict, resend nonces, maintenance flag) — with N workers each process has its own copy, so a chat message only broadcast to sockets on the same worker (proven: bot held one WS continuously while `/chat/post` flapped `subscribers` 0↔3 per message and 0-subscriber posts never echoed back), and the online counter only counted players whose pings landed on the worker you asked. Fix: `command:` override in docker-compose.yml pins uvicorn to ONE worker regardless of what the server-side Dockerfile CMD says. (Learning #125.)

- **#51 online counter** — besides the worker fix: presence now also ticks from queue joins/polls (both ladders — 2v2 queue never counted before), match reports, live-points, preflight, and chat sends; the client's presence loop re-resolves a lost Steam-ID race every tick (menu-sitters used to ping nothing all session — observed live as steam-id-less `/queue/count` calls) and survives request exceptions (fire-and-forget instead of yielding).
- **#52 chat propagation** — single-worker restore above; no client change needed (Sid's log showed a healthy socket receiving zero pushes for two whole sessions — server-side delivery, not client).
- **#53 bet attribution / "my Discord bet didn't show in-game"** — root story: Sid's 2000g Discord bet landed on ImaMageBro's OTHER active series (vs Quilvet — the embed he clicked), which stalled at 1-0 and auto-refunded an hour later; Stan bet on the actual vs-Ku series and won. Display was factually right, but nothing ever told Sid what happened. Fixes: Discord bet confirmations now name the matchup + series id ("2,000g on ImaMageBro (vs Quilvet, series c50280a0)"), and the Leaderboard tab's live panel gains a **"Your bets" ledger** — pending bets (with matchup) + last 3 outcomes with **refunds shown explicitly** ("refunded - series never finished") instead of silently hidden.
- **#54 gradient shop previews** — `WrapForSku` (the store-preview path) only knew tag-pair SKUs; rainbow + all 5 gradients are name-REPLACING effects handled only in `Wrap()` (the equipped path), so every gradient preview rendered as a plain uncolored name for everyone (not a short-name issue — Ku just noticed). Preview now routes through the same per-character builders. (Learning #126.)
- **#55 shop Cosmetics category** — new **Cosmetics** shop tab + "CHARACTER COSMETICS" section for kind='face' items (on shipped 1.29.1 they fell into the Titles catch-all — Stan's report). Rows show "equip in the character editor", the artist byline, and stock.
- **#56 2v2 session info** — the session tracker added every non-self player as an opponent, teammate included ("vs Stan 2-0" while teamed with Stan). Teammates (matched via `t_id` prop) now record under a "w/ " key and render as "w/ Stan: 2W-0L".
- **#57 2v2 custom-lobby lock delay** — the manual queue still applied the auto-queue Elo band (±100 → ±800 only after 120s), so mixed-rating friend groups waited minutes to lock. Custom lobbies are consent-based: rating gate removed for queue_type='manual'; lock now happens on the first poll after the 4th join (≤3s). (Learning #127.)
- **#58 2v2 card-pick bodies** — three hardenings: the anti-stack X-offset is now held for the whole pick phase (~8s) instead of 10 frames (vanilla re-anchors later than that); the retint honors equipped CUSTOM body colors (it only recognized vanilla team hues, so any custom-color body read as "wrong avatar" and was left alone); and the body's root particle system is health-checked + kicked with a new `[CARDPICK-BODY]` log line per pick (playing/count/position) so the next report pinpoints the failing layer. Needs live 2v2 confirmation.
- **#59 2v2 crown** — vanilla `GameCrownHandler` is hard-1v1 (one crown, position lerped strictly between players[0] and players[1] — in a 4-player room it can't even reach half the players). In cr_ff rooms a LateUpdate replacement now computes the leading TEAM (rounds → points, vanilla precedence) and crowns **both** members (vanilla crown + a per-scene "cr_mate_crown" clone). 1v1 untouched. (Learning #128.)
- **Artist role (Sid's ask)** — community artists control their own cosmetics. Server: `artist_users` (mirrors admin_users) + `shop_items.artist_steam_id`/`stock_limit` + `artist_item_blocks` + `artist_actions` audit (migration 109); HMAC-signed endpoints for **set-price, set-stock (0=unlimited), gift (free copy, consumes stock, bypasses blocks), block/unblock buyers**; purchase path enforces artist blocks + sold-out. Client: new **Artist tab** (visible only to artist accounts) listing their items with live price/stock/sold/gifted numbers + Price/Stock/Gift buttons and a blocked-buyers manager; shop rows show "by <artist>" + "N of M left"/"SOLD OUT". Sid seeded as first artist (owns the 6 test face items) so the tab is testable; onboard real artists by inserting an artist_users row + stamping their items' artist_steam_id.
- **Achievements: Steam-style global stats (Sid's ask)** — every achievement row now shows "**X.X% of players have this**" (denominator = all non-deleted players; server-cached 5 min).
- **FAQ sheet (Sid's ask, → #scr-faq 1525606624100618381)** — full install/update/ranked/queue/economy/troubleshooting FAQ written to `docs/FAQ.md` and queued as 6 Discord messages via the new generic **`pending_channel_posts` announce pipeline** (migration 110 inserts; the bot polls every 30s and acks after each send, learning-#105 style, so restarts can't drop posts). Posts land automatically once the bot is deployed + 110 is migrated. Discord bet confirmations and future announcements can reuse the same queue.

## v1.30.0-dev — UNRELEASED — custom character cosmetics framework (overnight build 2026-07-08)

> Migration 107 applied (6 test face items, kind='face'). Client framework built + installed locally, **not shipped** — needs Sid's visual pass first (scales/offsets are first-guess).

> Migration 108 applied 2026-07-09 (data-only, snapshot `cc_pre-migrate-108__20260709_182156`): recorded the **second** 2v2 series (`dcff0002`) of the 07-09 Sid+Nix vs galaxy+Quilvet sitting — awarded to galaxy/Quilvet by DC forfeit (Nix lost internet on game 6). The four played two back-to-back BO3s in one room; the client never created a server-side series 2 because series 1 locked at first-to-2, so games 4–6 went unrecorded. Series 1 (`9369b7a5`, Sid/Nix 2-1) left untouched. Glicko recomputed for the 4 (a from-scratch replay reproduced all 26 production ratings to 0.0000 before stacking series 2): Sid 2015→1811, Nix 1627→1464, galaxy 1347→1785, Quilvet 1195→1596; +50/+25 series gold. **Latent gap:** any 2v2 set that runs past first-to-2 loses DC-forfeit protection on the later games — the client stops reporting once the BO3 locks. Worth a client fix (auto-open a series 2, or support longer sets).

- **2v2 recording-gap fix + clear-cases-only DC + in-mod admin series management** (built 2026-07-09, **not yet deployed/shipped**). Three linked changes born from the 07-09 dispute (mig 108):
  - *Recording fix*: when four players keep playing in the same cr_ff room past the first BO3 (which locks at first-to-2), the reporter now opens a **continuation series** at game start (`POST /team/series/continuation`, HMAC-signed, idempotent, requires a real recent series for the same four) so games 4+ record as ranked instead of being silently dropped. Client hook mirrors the 1v1 preflight re-arm (learning #101); resolves the lineup from `t_id` props + reporter election. Also self-heals a lost series-1 id.
  - *Clear-cases-only DC* (Sid's call): 2v2 auto-forfeit now fires **only** when the non-DC team already won a game AND ≥2 points were played in the abandoned game; every other DC (break/restart, <2 pts, grace lapse) → new **`dc_incomplete`** status, recorded and left for manual resolution. No auto-penalty for a 2v2 that breaks and needs a restart. Removed the grace-expiry auto-forfeit.
  - *Admin series management (F5 → Admin tab)*: new **Recent Ranked Series** log (1v1 + 2v2 unified) showing per-ladder series #, players, score, status, who DC'd, and card picks. Incomplete 2v2 → **Award T1 / Award T2 / Void** (`admin/team/series/{id}/resolve`, now admin-HMAC-callable, not just the internal key); completed series → **Reverse** (2v2 via new `admin/team/reverse-series`; 1v1 via the existing endpoint). Every action behind a confirm. Replaces having to hand-run a SQL migration + look up series ids in Discord. No migration: `dc_incomplete` fits the existing varchar, series # is a query-time `ROW_NUMBER()`.
- **Custom face cosmetics (F8)** — shop-purchasable eyes / mouths / details that appear inside ROUNDS' own character-editing menu and render everywhere a face renders (in-match body, card-pick visualizer, menu portraits, 2v2). New `plugin/CustomCosmetics.cs`: append-only catalog at network IDs ≥1000, resolved via two Harmony prefixes on `CharacterCreatorItemLoader.GetItem/GetItemID` — vanilla arrays untouched, saved vanilla faces stable, and clients WITHOUT an item (vanilla opponents, older mods) resolve it to null and render an empty slot (vanilla's own out-of-range fallback — no crash, no desync). Owned items are injected into the character editor via a `CharacterCreatorButtonSpawner.OpenMenu` postfix that replays vanilla's exact button flow, so equip/drag/save/sync all run vanilla code (PlayerPrefs + `RPCA_SetFace` + our `cr_face` props). Art = runtime-loaded 512px PNGs from `plugins/CompetitiveRounds/cosmetics/` (AssetBundles ruled out — ROUNDS' Unity build hash is unobtainable, see the nametag-typeface post-mortem; constants match Pykess's PlayerCustomizationUtilities: layer Player, sorting MostFront, order eyes 3 / mouth 4 / detail 5). Server: zero code — kind='face' rows gate ownership only, equip state never touches the DB. Shop tab: face items land under Other, no Set Active button (equip lives in the character editor). 6 PIL-generated test items: Star Eyes, Heart Eyes, Moustache, Stitched Grin (250g), Crown, Halo (750g rare).

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

## v1.28.3 — 2026-06-12 — bug-report sweep (⚠ backend DEPLOYED, client BUILT but NOT SHIPPED)

> **Session state for the next session:** this is a full sweep of open bug reports #26–#36. The **backend changes are LIVE** (deployed via `/deploy-backend all` on 2026-06-12 — main.py, schemas.py, discord_bot.py). The **client DLL is built and installed to the local BepInEx folder but NOT released** — no version bump yet (`ModVersion` still reads `1.28.2`), no git tag, no GitHub release. To finish: bump to 1.28.3 and run `/ship 1.28.3`. Bug-comments were posted on all of #26–#36 (and #19/#23/#24/#25 earlier). Sid closes the reports.

**Headlines for testers**
- **Block, empower, invisible block effects (#15/#19/#23/#24/#25)** — already fixed in v1.28.2; **verified** against live gameplay logs this session (the zombie-delegate scrub fires mid-series and blocks keep absorbing). Nix's #24 report was on the 1.28.1 build whose fix was a no-op; 1.28.2 fixes it for real.
- **"Matched but failed to auto join" (#26, lopidav)** — his join actually *succeeded*; the room just sat at 1/2 because the opponent never connected, and pressing Escape during the loading screen is a vanilla hard-disconnect. Now: the join sequence auto-retries once if it stalls, and if you're left alone in a ranked room you get a "hang tight" notice at 25s and a clean, penalty-free auto-return to menu at 60s. *(client — v1.28.3)*
- **Menu button disappears after a few games (#27)** — the injector's retry budget was being spent down once per second *while you were in a match*, so it ran out and never re-added the button. Now it only counts at the menu, refreshes on room exit, and self-heals slowly instead of giving up. *(client — v1.28.3)*
- **Invisible map walls after Shift (#28)** — Shifting map skins mid-round cleared "burst"-type walls (Velvet especially) and they never re-emitted until the next round. Now the particle timeline is restarted so they re-fire immediately. *(client — v1.28.3)*
- **Invisible card-pick body (#29)** — the "Pause skin particles during card pick" perf option paused the pick-phase character (which *is* a particle system) before it emitted anything, rendering the body invisible. That option was removed entirely. *(client — v1.28.3)*
- **Chat duplicates / drops / delays (#30/#34)** — the server used two different timestamps for the same message so the Discord bot couldn't dedupe, double-posting some. Messages now carry a stable database ID and everything dedupes on it. **Discord double-post fix is LIVE now**; the in-game side (reconnect no longer re-prints old messages; retried sends can't post twice; instant relay instead of a 30s poll) ships with **v1.28.3**.
- **lopidav can't attach logs (#31)** — his logs contain raw control characters, and the uploader wasn't escaping them, so the server rejected the whole submission (422) and only the no-log retry got through. All fields are now fully escaped. *(client — v1.28.3)*
- **Panels empty until manual Refresh (#32)** — Leaderboard "Recent Ranked Series" and Card Stats tiers now show "Loading…" and auto-refetch if the first fetch fails/races, instead of sitting blank. *(client — v1.28.3)*
- **Series don't resume across disconnects / sessions (#33/#35)** — a series only counted as "current" for 25 min after it was *created*, so an interrupted best-of-3 you came back to later started a brand-new series (leaving the old one — and any bets on it — stuck). The window now measures from the **last game played**, and tournament series always resume. **Backend fix is LIVE now**; the client also re-syncs your on-screen series score on reconnect in **v1.28.3**. Verified no bets are currently stuck unsettled in production.
- **Only the first series of a session can be bet on (#36)** — rematch series rows were created only at first match-report, by which point a game was already won (which locks betting). The series is now created at the **start of each game**, before any score. **Matchmaking-path fix is LIVE now**; the rematch-path fix ships with **v1.28.3**.

**Under the hood**
- New shared server helper `_find_current_active_series(db, a, b)` — one activity-based, tournament-aware series lookup used by all three find-or-create sites (match report, queue ready/poll, preflight) so they can't diverge (root of #33/#35/#36). Reuse window now = "created recently **OR** has a match that ended recently **OR** is a tournament series."
- `/series/preflight` now takes `room_id` and sets `is_private` from it (queue/tournament rooms stay bettable with the tight lock; code-join rooms keep the wider private window). Its "exists" response echoes the series score so a reconnecting client can adopt it.
- Queue poll `ready_join` now find-or-creates the series and returns `series_id` (parity with `/queue/ready`); client sets `ActiveRankedSeriesId` from it. New `series_id` field on `QueuePollResponse`.
- Client re-arms the series preflight at each ranked game start when it holds no live series id (fixes rematch series being born bet-locked). Eager-preflight room gate relaxed to allow `ranked_*`/`sct-*` (still excludes 2v2 `cr_ff`/`team_`).
- Chat: server `_persist_chat` now inserts first with `RETURNING id, created_at` and puts the id on the broadcast + scrollback; bot dedupes on `db:<id>` (with boot-time priming so a restart doesn't re-post the last 50); client `client_msg_id` nonce on every send (resend reuses it) + render-dedup by last-seen id. **Chat entry key order in `/chat/recent` is load-bearing** — `source` first, `id` mid, `timestamp` last — for the mod's manual splitter.
- Removed `CardChoiceVisualsShowParticlePause` patch + its config entry + its Settings row (perf count 8→7).
- Map wall/atmosphere recolor uses `RestartParticleSystem` (Clear→Simulate(0,restart)→Play) instead of a bare `Clear(true)`.
- `MainMenuInjector` checks `InRoom` before consuming a retry; refreshes budget on room exit; slow-retry failsafe after the cap.
- New `ApiClient.JsonEscapeFull` (all control chars → `\uXXXX`) on every bug-report field.
- `GameStateWatcher.AdoptSeriesScore` + a ranked-room "opponent never arrived" watchdog; `QueueJoiner` one-shot connect retry.
- Learnings #96–#102 added. **No DB migration** this release.

## v1.28.2 — 2026-06-10

**Headlines for testers**
- **Block + Empower finally fixed at the root.** Block dying after game 1 in ranked (and the "infinite empower" carryover) were the same bug: a card's teardown between games could abort mid-way and leave a dead "zombie" handler on your block/gun, which then threw and killed the block (or kept empower firing invisibly). The mod now sweeps those dead handlers at every game start and every block press. Verified against the current game's decompiled source.
- **Map walls are two-tone again** — primary + secondary alternating by wall segment (e.g. Magma red *and* amber), keyed so overlapping layers can't fight over color. Backgrounds read more strongly as their named color.
- **Performance patches corrected** — two old-game ports that no longer matched current ROUNDS were removed, and the crash-error swallowers no longer destroy pooled/Photon bullets (a likely source of stutters).

**Security hardening (full review)**
- Closed an unauthenticated achievement gold-farm; match reports now verify the reporter is a participant + reject duplicates/replays.
- Added server rate limiting + request size cap; HMAC-signed the previously-open state endpoints (ranked toggle, block/unblock, achievements).
- Server-side **speedhack flagging** and mod-wide **bans** now post to the admin channel; matching a banned cheater leaves the match.
- Hardened the disconnect report (bound to a real recent series), the Discord-link endpoint, and admin signatures (fail-closed).

## v1.28.1 — 2026-06-09

**Headlines for testers**
- **Block fixed in ranked/matchmade games** — block could activate but absorb nothing (you'd "block" and still take the hit) in ranked rooms. Root cause: our round-start block reset stripped the block's action delegates every round even when nothing was actually destroyed and needed rebuilding. Now it only rebuilds when a trigger was genuinely removed. Confirmed via gameplay logs: a broken-build session showed **0 successful blocks out of 70**; a fixed-build session showed block absorbing hits normally across every game.
- **Phantom series scores fixed** — the per-series game counter in the HUD could climb past best-of-3 (e.g. "4-0") for the player who *isn't* the match reporter. It now self-corrects off the BO3 score so both clients agree.
- **My Stats card-hover fixed** — the card tooltip's hover zone was the full row width (mostly empty space), so moving toward the bottom-right refresh button kept popping the tooltip over it. The hover zone is now sized to the actual card text.
- **Discord series feed** — win streaks are no longer capped at 20 (1v1 and 2v2), and rating changes now show one decimal place so sub-1.0 Glicko moves no longer display as "0".
- **Bug reports per day raised 3 → 10.**
- Matchmaking-disconnect diagnostics widened to cover 1v1 (groundwork for tracking down the intermittent queue DC).

## v1.28.0 — 2026-06-03

**Headlines for testers**
- **Round-start freeze fixed** — the bug where a player got stuck mid-screen (couldn't move/block/shoot) and was off-screen the next round. Root cause: the map-color tint ran *during* the round's player-repositioning coroutine and stalled it. Deferred safely now.
- **Map colors reworked again** — every map now clearly reads as its named color (Magma red, Pine green, Velvet purple, etc.) via scene-wide colorize. Walls flashier. **Shift now shows a map-name toast** so you can find a specific skin, and Shift-cycling no longer auto-shuffles to the dull ones each round. (Known: the secondary/accent color is washed out by the primary scene tint — being fixed next pass.)
- **Compare tab overhaul** — compare up to **12** players; every metric is now a chart (bars for FPS/Peak Elo/XP/Achievements/Avg-cards, grouped bars for Hit/Block %, **pie charts with leader-line labels** for region split); Total XP axis shows **levels**; live search box; working scrollbars; full numbers.
- **Cursor shapes** — pick ROUNDS-default / Arrow / Dot / Crosshair / Circle in Settings (combines with your cursor color).
- **Shop** — Cursor, Effects, and Other categories now have their own tabs.
- **Body color unequip fixed** (it snapped back after a second / on refresh).
- **Bug-report form** no longer passes clicks through to the F5 menu behind it.

### v1.28.0 detail — cursor colors, player effects, hide-gold, leaderboard overhaul, map fixes, 2v2 fixes
*(this block was authored as "Unreleased" across earlier turns; it all shipped in v1.28.0)*

### 2v2 (server — already deployed)
- **2v2 leaderboard recovery**: rebuilt all 2v2 Glicko ratings + series counters from history. Players who'd played completed 2v2 series but were missing rating rows (NotHoly, feauxen, MAX1T0P, and others) now appear correctly on the 2v2 leaderboard. (migrations 099 + 100)
- **Anti-abuse DC scoring**: leaving a 2v2 no longer dodges a loss. If the non-DC team has already won a game, the other team leaving forfeits the whole series to them — now with full Elo/gold/xp (previously DC completions awarded the win but applied no ratings). Resolved 3 stuck series (NotHoly's leave → Sid's team win; two old ones voided).
- **Race hardening**: 2v2 series completion is now row-locked + status-guarded so a duo rage-quitting (two simultaneous DC reports) can't double-credit Elo/gold/bets.
- New admin endpoints: force-resolve a stuck team series + rebuild 2v2 Glicko (API_SECRET_KEY gated).

### 2v2 (client — in the new DLL)
- **Both-players-orange fix**: teams now render distinct colors. Fixed the broken team-color resolution (was reading white for both teams) + added a remote-player skin re-bake guard.
- **Pick-phase disappearing/overlapping bodies fix**: the per-player X-offset now survives vanilla's re-anchor pass instead of re-stacking at the origin.
- **No-block fix**: rebuilds the block action-delegate chain on each game start, restoring the basic block proc for players whose main block trigger got destroyed between games.

> Shipped in v1.28.0 (2026-06-03): backend (migrations 098-100 + API) deployed, client DLL released + tagged.

**Headlines for testers**
- **Cursor colors** (Cursor shop tab, 10 @ 150g). Recolor your mouse cursor — shows in menus and while aiming in-match. Local-only (only you see it).
- **Player effects** (Effects shop tab, 8 @ 4000–8000g): Smoking, Lucky Clover, Hearts, Bubbles, Embers, Sparks, Rainbow Aura, Void. Particle auras on your body, visible to other modded players. One at a time; respects the "Show Player Colors" toggle.
- **Hide Gold** (new Other shop tab, 10000g). Toggle to mask your gold on the leaderboard — everyone else sees "Hidden", you still see your real balance.
- **Leaderboard player view**: clicking a player now shows their **Ranked History** and, vs other players, your **Last Ranked Series vs them** (per-game scores + both sides' cards). New **Compare** tab: overlay up to 5 players' Elo-over-games graph, or compare Top Cards.
- **Magma (and other map) colors fixed**: maps now show both their colors (e.g. Magma's yellow accent) instead of only the primary.

**Under the hood**
- Owner auto-grant: the mod owner's Steam ID owns every shop item present and future (`SHOP_OWNER_STEAM_IDS` in main.py) — computed live, no per-item rows, no future migration cost.
- Map two-tone wall coloring switched from FNV-hash parity (which collapsed nearly all walls to one color) to sorted-index parity for a guaranteed ~50/50 primary/secondary split.
- New files: `plugin/CursorColorCosmetic.cs`, `plugin/PlayerEffectCosmetic.cs`.

**Schema**
- `098_cursor_effects_hidegold.sql`: adds `players.active_cursor_color_id`, `active_player_effect_id`, `hide_gold`; seeds 10 cursor colors, 8 player effects, 1 hide-gold utility.

## v1.27.0 — custom map colors, shop expansion, level rewards, 2v2 series rework, performance pass

> Big release rolling up everything since v1.26.7. The backend (API + DB migrations 088–097) was deployed incrementally; this is the matching client ship plus the Discord Gambler bot.

**Headlines for testers**
- **Custom map colors.** A full shop tab of map-skin recolors (Soft Slate, Moss, Cream, Lavender, Dusk, Sand, Mono, Forest, Amethyst, Charcoal, Crimson, Slate, Rose, Mint, Sunset, Obsidian, Abyss, Pine, Iron, Burgundy, Magma, Velvet, Blackwood). Equip several and **cycle them in-match with Left Shift**. Each skin is a designed two-color wall pair on a light-grey-to-dark background; the brown physics boxes stay brown. Backgrounds stay readable (no more pitch-black).
- **Body colors + name styles.** New body colors (4000g) and a big nametag shop: solid colors (100g), font styles (caps / small-caps / spaced / bold / italic), size/float effects, **neon glow** variants, and premium **animated gradient** nametags (Aurora, Ember, Galaxy, Ocean, Sunset) plus Rainbow.
- **Level rewards.** Earn **100g every 5 levels** up to level 50, then **500g every 5 levels** after. Backfilled for everyone already past a milestone.
- **Card tooltips in history.** F5 history shows cards as 2-letter chips; **hover any card group to see the full names**. Now in both My Stats and the 2v2 series view.
- **2v2 "Recent Series" rework.** Series are **compact one-liners you click to expand** (clear WON/LOST + score + your Δelo + gold/xp + date). Teams are color-coded **blue vs orange** (fixes the old "everyone shows red" bug), with a `(you)` marker. Expanded games show per-player cards as chips with hover-for-full-names. The list now **fills the whole panel** (10 series/page) and **keeps your scroll position** instead of snapping to the top on refresh. 2v2 ELO now shows **±RD** on the leaderboard and beside each player in series detail.
- **Leaderboard rating graph** now shows the full series-rating history (server cap 20→500, chronological), bucketed when long so it stays readable instead of dropping points.

**Bug fixes**
- **Map-skin flicker fixed.** Custom map walls no longer strobe between textures. Root cause was overlapping transparent wall particle systems fighting for draw order frame-to-frame; each now gets a stable, distinct sort order. The harmless vanilla per-particle shimmer is preserved. Shift-cycling between skins is now an instant snap, not a slow fade.
- **"Match Found" escape hatch false-positives.** The stuck-on-match-found recovery overlay no longer appears when you enter Sandbox or flashes periodically while searching — it's now suppressed in Photon offline mode, where no real match-found stall can happen.
- **Series-win gold misrouting** (migration 090) and **Tag Team Sweep criteria** (migration 088) corrected; **duplicate/stale tournaments** cleaned up (089).
- **rating_history backfilled** (migration 097) so the leaderboard graph has full history for everyone.

**Performance**
- Ported performance patches from the community Performance Improvements mod (StunPlayer null-guard, off-screen bullet despawn, NRE finalizers for hit-sound / edge-bounce, color-ghost auto-cleanup, bullet-hit particle cap, object-pool init clamp, card-pick particle pause, menu-controller update bail, spawned-object cleanup tagging). All behind F5 → Settings toggles.
- **`[PERF]` telemetry**: each ported patch logs a one-time first-fire line and a per-match hit-count summary (on room leave) so we can verify what's actually firing in-game.

**Discord**
- **Gambler role.** Members opt in via the `/gambler` slash command or by reacting 🎲 to a pinned signup message; the bot pings the role whenever a new ranked match opens for betting. (Requires the role to be Mentionable and the bot's role to sit above it.)

**Backend / infra**
- Migrations 088–097: team-sweep fix, tournament cleanup, series-win gold fix, level-reward backfill, body colors, nametag styles, rainbow/gradient nametag effects, dark map colors + recolor, more gradient nametags, rating_history backfill.
- 2v2 team leaderboard now returns `rd` (rating deviation); level-reward grants wired into `submit_match` + `submit_team_match`.


## v1.26.7 — in-game bug reporter, 2 new achievements, input overlay, session persistence, 2v2/1v1 bet dedupe, 2v2 ready indicators, tournament auto-cleanup

**Headlines for testers**
- **Report bugs from in-game.** F5 → Settings → "Open Report Form" — fill in description + severity + category, optionally attach your game logs (BepInEx current + previous session + Unity), submit. Reports get a quotable `#N` ID and auto-post to the new Discord bug-reports channel (no logs/comments leaked there — just the metadata + description). Rate limited to 3 reports per 24h per player so accidents don't flood. Admins (currently Sid) can triage everything from F5 → Admin → Bug Reports: status changes (`open` → `triaged` → `resolved` / `wontfix` / `dupe`), comments, full activity log, attached log preview.
- **Two new achievements.**
  - **Master** — reach 2030 rating in ranked (1v1 OR 2v2).
  - **Tag Team Sweep** — win a 2v2 series 2-0.
  Both auto-grant when you cross the threshold; +100g each like the rest.
- **WASD / Space / L+R click input overlay.** Bottom-left corner toggle in F5 → Settings. Keys glow red when pressed. Useful for stream overlays and for diagnosing "my block didn't fire" reports without having to record video.
- **Session persistence.** Quit + reopen ROUNDS within 3 hours and your session counters resume — match count, ranked/casual W-L, series wins, per-opponent H2H, time-with-opponent — all of it. Past 3 h of inactivity, fresh session as before.
- **Session H2H opponent line under the in-match score banner.** Renders in BOTH ranked and casual matches now (was ranked-only). Shows `vs OpponentName: W-L this session` or `first game this session`, color-coded. 2v2 rooms skip it (opponent-latch makes the number misleading).

**Bug fixes**
- **2v2 ↔ 1v1 dedupe.** Live-bets panel + 1v1 match history were getting polluted by 2v2 matches that the client occasionally fell back to reporting through the 1v1 endpoint. Server now hard-rejects any match report with a `team_*` room ID at the 1v1 endpoint; client hard-blocks the 1v1 fallback whenever a `cr_ff` room or team series is present; query filters added so historical phantoms can't show up either. Migration 082 invalidated the 5 phantom rows that had already leaked through.
- **First-launch ranked race (round 2).** Server-side reinforcement of the v1.26.6 client fix: `/queue/join`, `/team/queue/join`, `/series-preflight`, and `/api/v1/matches` all now flip `ranked_enabled=true` on first contact. Clicking the queue button IS the opt-in. Belt and suspenders so a slow async `/toggle-ranked` can't degrade your first match.
- **Tournament list auto-cleanup.** The async tournament that finished 2026-05-13 was still showing as the "current" tournament weeks later because the `/tournaments/current` fallback query had no recency filter. Narrowed to "completed within last 3 days" so finished brackets clear automatically.
- **2v2 ready indicators.** Per-slot `[R]` / `[ ]` tags in front of every name in the lock-in prompt, including your own — no more guessing who you're waiting on.
- **2v2 right-click block (mod-rooms only).** Added a state-reset on every game start in competitive rooms — scrubs null entries from `Block.triggers` and forces all Block components ready. Targets the "right-click goes straight to cooldown" pattern that hit 2v2 series after game 1. Gated on competitive room detection so vanilla pickup games are unaffected.

**Backend / infra**
- **`bug_reports` + `bug_report_events` tables** with sequential `bug_number` IDs (migrations 083, 085, 086, 087).
- **Bug log persistence**: `docker-compose.yml` now bind-mounts `/opt/competitive-rounds/bug-reports/` on the host so log files survive API container rebuilds. Pre-existing orphaned `log_filename` pointers (from logs that died with their container) cleared in 087.
- **Discord bot**: new `poll_bug_reports` task posts a colored embed per new report to channel `BUG_REPORTS_CHANNEL` (default `1501643180049960970`).
- **Internal-only commenting endpoint** at `/api/v1/internal/bug-reports/{id}/comment` — gated to localhost + Docker bridge only. Lets Claude post triage comments via `bug-comment:N|text` through the SSH wrapper. Bypasses the version gate (it's loopback-only).
- **SSH wrapper additions** (`cc-deploy-wrapper.sh`): `bug-list`, `bug-read:N`, `bug-comment:N|text`, `bug-log:N`. Lets the mod owner + Claude triage without HMAC dancing.
- **JSON parser fix** (client-side): `ExtractJsonString` now correctly skips `\"` and other JSON escapes — previously the admin viewer's log section silently truncated at the first `"` inside log content.

**Process / docs**
- `docs/learnings.md` worth updating: BepInEx 5 ships with `AppendLog = false` by default, meaning `LogOutput.log` is truncated per launch. Application.quitting hook in Plugin.Awake now copies the current session's log to `LogOutput-prev.log` BEFORE the next launch's BepInEx truncates, so previous-session crash data survives a relaunch-to-file-report cycle.

## v1.26.6 — first-launch ranked fix, anti-cheat false-positive sweep, 2v2 menu rework, in-match session score, Sid+feauxen series recovery

**Headlines for testers**
- New installs no longer get logged as casual on their first match. Steamworks resolution is racy on first launch; we used to skip the `/toggle-ranked` server sync entirely if Steam wasn't ready by the time the plugin initialized, so the player's `ranked_enabled` stayed false on the server and every opponent saw them as casual until they restarted ROUNDS. Plugin now polls every 0.5 s for up to 30 s and fires the init the moment Steam resolves.
- The "too_many_cards" anti-cheat was wrong. ROUNDS arms-race rules give the loser of a 5-X game **6 cards** legitimately (1 pre-match auto-pick + 1 per round lost). Threshold was 5 with auto-invalidate on; every existing flag was a false positive. Bumped to 7, demoted to advisory-only, dismissed the unreviewed flags, restored the 3 wrongly-invalidated matches, re-credited gold/XP. (Migration 081.)
- In-match score banner now shows **Series** + **Session** instead of repeating the round count the game already displays. Series = current BO3 score (e.g. `1 - 0`), Session = cumulative ranked series wins/losses since the mod loaded.
- 2v2 menu rework — Random Queue + Custom Lobbies are now side-by-side, queue bodies collapse when empty, "Live 2v2 Now" strip in the 2v2 tab, scroll-affordance hint between sections, and panel images set to non-raycast so wheel/drag-scroll bubbles cleanly to the outer ScrollRect.

**Sid+feauxen 2v2 recovery (server-side, retroactive)**
- Migration **077** rebuilt 4 unreported 2v2 wins from 2026-05-09 that the queue cleanup loop swept mid-game (the underlying loop was fixed in the same deploy: `team_queue_cleanup_loop` now gates on `spawn_confirmations < 4` so post-assembly series aren't cancelled when players stop polling `/team/queue/poll` after entering Photon).
- Migration **078** split the recovery into the two BO3 series Sid+feauxen actually played that day (matches 1+2 stay on `4ea30d95...`, matches 3+4 move to a new series row).
- Migration **079** backfilled per-slot gold/XP earned (T1 +1200xp/+37g per series, T2 +1800xp/+68g per series) and credited each player's totals via real `gold_transactions` rows.
- Migration **080** approximated per-slot Glicko deltas using the live `glicko2.calculate_new_rating` against best-known pre-series inputs, so the F5 history elo chip actually renders. The recovered-series elo numbers are large because three of the four players had default 350 RD on 5/9 — accurate Glicko output, not a display bug.
- 2v2 history now reads "(card data not recorded)" once per match instead of stacking four "—" placeholders when none of the four players' card lists were captured, which kept the recovered matches from looking confused.

**Backend hardening**
- Background tasks (`queue_cleanup_loop`, `team_queue_cleanup_loop`, `tournament_tick`) are wrapped in a `_supervised(name, coro_factory)` helper that catches any non-`CancelledError` exception, logs the traceback, and restarts the loop after 5 s. Previously a single asyncpg blip killed the loop until next API restart.
- DB connection pool bumped from `pool_size=10, max_overflow=5` to `20 + 10`, with `pool_timeout=30 s`, `pool_pre_ping=True`, `pool_recycle=1800 s`. Saturday playtest peaks were brushing the prior 15-conn ceiling; the timeout means we 503 cleanly under contention instead of hanging the worker.

**Earlier in this release window — tournament + leaver/bet/block fixes (rolled in)**

The async tournament had been silently broken since the feature shipped — `start_tournament` errored on every cron tick because the `RankedSeries` SQLAlchemy model was missing the `tournament_id` / `is_tournament` / `is_private` columns. Fixed model + a pile of correctness and UX issues that surfaced once tournaments started running. Highlights:

- `RankedSeries` model gained `tournament_id`, `is_tournament`, `is_private`. Confirmed live: the active async tournament flipped from `locked` → `running` immediately on deploy, and Sid+Lopi's WB R1 series row now has `tournament_id` populated.
- `tournament_matches.photon_room_name` (migration 072) — server allocates the room name at activation time. Eliminates the dual-derivation race.
- `_prune_stale_series` skips `is_tournament=TRUE` rows. Migration 074 restored the two rows that got swept before the fix; migration 073 marked 19 zombie pre-fix `status='active'` rows as `abandoned`.
- New "Upcoming Match Bets" section in the Tournament tab. Live Ranked Games hides tournament series in `pre_match` phase. Tournament + private bets follow the same lock rules as queue series; Discord embed mirrors with `🏆 [Async]/[Sync]` and a `PRE-MATCH` callout.
- Tournament dispatch is now tab-independent: `TournamentHeartbeatLoop` plugin-level coroutine fires `SetPendingRoom` for sync-ready matches whether or not the F5 menu is open.
- Visual bracket replaced the collapsing list — positional canvas, status colors, blank skeleton during voting/locked.
- Auto-connect prefers server-issued `photon_room_name` over the legacy client-side derivation.

**Leaver penalty + eager preflight + block safety**
- `matchIsRanked` now persists across games of a series; `OnMatchStarted` re-derives it from room CustomProperties. Previously games 2+ of a series silently logged casual. Reproduced 2026-04-30 when Galaxy Ice DC'd mid-game-2 with ~6 firefights and got no leaver penalty.
- Leaver threshold: `totalPts >= 2 OR seriesGames >= 1` (was firefight-count only).
- `series/preflight` fires the moment we see opponent `cr_*` Photon properties — Discord `#live-bets` and the in-game Live Ranked Games panel surface private 1v1 matches within ~10 s of room entry.
- Verbose `[BLOCK-SAFETY]` diagnostics + Finalizer backstop on `BlockTrigger.DoBlock` after testers reported the cascade-skip wasn't catching the upstream destroyed-trigger bug.

**Stan refund + stalled-series prune**
- Refunded Stan's 2000g bet on series 4e320959 (1 match played 5-2, then players never finished — `_prune_stale_series` only handled "0 matches in 30 min", not "1+ matches then stalled"). Migration 076 also swept 5 other stuck series found in the same audit. The /series/active prune path was extended in the same deploy so future stalled series auto-prune + auto-refund.

**First-launch "casual instead of ranked" bug**
- Fresh installs whose Steamworks resolution was racy on first launch silently skipped `ApiClient.ToggleRanked` — `Plugin.cs:723` had a single bare `if (steamId != "unknown")` guard with no retry. Their server-side `ranked_enabled` stayed at the SQL default of `false`, so every opponent's `OnMatchStarted` ranked-derivation saw them as casual until the next ROUNDS restart (when Steamworks was already loaded by the time `DoInitialize` ran). Replaced the inline guard with an `InitWhenSteamReady` coroutine that polls every 0.5 s for up to 30 s, then fires the same one-shot init (`ToggleRanked` + `FetchPlayerStats` + `FetchMatchHistory` + `FetchBlockedPlayers` + `CheckAdminStatus`) once the Steam ID resolves.

**Anti-cheat: "too_many_cards" was a false-positive factory**
- The threshold was `5 cards per player per game`, but ROUNDS arms-race rules let the LOSER pick `rounds_lost + 1` cards (1 pre-match + 1 per round lost), so a clean 5-X loss legitimately produces 6. An audit of every existing `too_many_cards` flag confirmed all 5 hits matched `rounds_lost + 1` exactly — every one was a false positive.
- Bumped `ANTICHEAT_MAX_CARDS_PER_PLAYER` 5 → 7 so only true outliers (7+) flag at all.
- Demoted the flag from `auto_invalidate=True` to advisory-only.
- Migration **081** dismisses the 3 unreviewed flags as `false_positive`, restores the 3 matches that were auto-invalidated solely on `too_many_cards`, and re-credits the players' gold/XP via `reversal_undo` rows.

**Backend hardening**
- Background tasks (`queue_cleanup_loop`, `team_queue_cleanup_loop`, `tournament_tick`) are now wrapped in a `_supervised(name, coro_factory)` helper that catches every non-`CancelledError` exception, prints a stack trace, and restarts the loop after a 5 s backoff. Previously a single asyncpg blip killed the loop until the next API restart and queue/series rows accumulated forever.
- Connection pool bumped from 10 + 5 (max 15 concurrent) to 20 + 10 (max 30), with `pool_timeout=30 s`, `pool_pre_ping=True`, `pool_recycle=1800 s`. Saturday playtests with ~60 testers were pushing the prior ceiling, especially with queue polls overlapping match-submit + leaderboard reads.

## Unreleased (rolled into above) — 2v2 menu rework + Sid+feauxen series recovery

**2v2 history split + economy backfill (server)**
- Migration **078** splits the four matches recovered by 077 into the two BO3 series Sid+feauxen actually played that day. The original recovery dumped all four under one series_id; client-side history merged them into a single 0-2-extended view. Now matches 1+2 stay on `4ea30d95-…` (completed 0-2 at 11:25) and matches 3+4 move onto a new series row (completed 0-2 at 11:40), so each renders as its own line in the F5 history.
- Migration **079** backfills the per-slot `t1a/b/2a/b_xp_earned` + `_gold_earned` accumulators on both recovered series and credits the four players the gold/XP they earned at match time. Per series: T1 +1200 xp / +37g, T2 +1800 xp / +68g (matches the live submit-path math: 600/900 xp per match, 100 xp = 1g auto-conversion, +25g/+50g series-end bonus). `gold_transactions` rows inserted for the audit trail. Glicko `rating_change` is intentionally left NULL — historical 2v2 rating snapshots aren't recoverable, and the F5 row already omits the elo chip when the field is null.

**2v2 tab UX rework (client)**
- **Queue panels are now side-by-side**, two columns instead of stacked: Random Queue on the left, Custom Lobbies on the right. Was previously two 900-wide blocks stacked vertically, which wasted half the screen horizontally when ~0-2 people were queueing in either bucket.
- **Queue bodies collapse when empty** and grow to fit row count when populated (was a fixed 160 px each).
- **Live 2v2 Now strip** added directly to the 2v2 tab. One line per active team series, hidden entirely when no 2v2 is live. Mirrors the leaderboard tab's Live Ranked Games panel so users don't have to switch tabs to see what's currently in progress.
- **Scroll-affordance hint** ("↓ Scroll down for leaderboard + recent series ↓") now sits between the queue band and the leaderboard/history block. Tester feedback was that users didn't realize the tab scrolled; an always-visible hint solves the discoverability gap without pulling in a full reflection-built Unity Scrollbar.
- **Defensive raycastTarget=false** on the inner 2v2-tab panel `Image`s so mouse-wheel + drag-scroll bubble cleanly to the outer ScrollRect even when the cursor sits on a dark panel background.

**Recovered-series elo + cards (server + client)**
- Migration **080** populates approximate per-slot `rating_change` on both recovered series so the F5 history elo chip actually renders. Computed via the live `glicko2.calculate_new_rating` against best-known pre-series inputs (Sid's actual 2v2 row + defaults for the three first-time-2v2 players). T2A (Sid) +65 / +22, T2B (feauxen) +247 / +57 (huge series-A swing because she was at default 350 RD), T1A/T1B -183 / -46 each. Live `glicko_ratings_2v2` rows are intentionally NOT touched — players' current ratings already reflect everything they played AFTER these recovered series.
- 2v2 history view now renders "(card data not recorded)" instead of four "—" dashes when none of the four players have card entries for that match — clearer state for the recovered matches whose per-pick data wasn't in the source log.

## v1.26.5 — Tournament resurrection + leaver/bet/block fixes

The async tournament had been silently broken since the feature shipped — `start_tournament` errored on every cron tick because the `RankedSeries` SQLAlchemy model was missing the `tournament_id` / `is_tournament` / `is_private` columns it tries to populate. Tournaments stayed stuck at `status='locked'` forever and players' ranked games against their bracket opponents weren't attributed. Fixed model + a pile of correctness and UX issues that surfaced once tournaments started running.

**Tournament fixes (server)**
- `RankedSeries` model gained `tournament_id`, `is_tournament`, `is_private` columns to match the existing DB schema. Confirmed live: the active async tournament flipped from `locked` → `running` immediately on deploy, and Sid+Lopi's WB R1 series row now has `tournament_id` populated.
- New `tournament_matches.photon_room_name` column (migration 072) — server allocates the room name at activation time rather than each client deriving `"sct-" + match_id[:12]` independently. Eliminates the dual-derivation race.
- `_prune_stale_series` now skips `is_tournament=TRUE` rows. The 30-minute "no match reported = abandoned" cutoff was correct for queue/private series but kept sweeping async tournament series rows whose 7-day match window hadn't elapsed. Migration 074 restored the two rows that got swept before the fix.
- Migration 073 marked 19 zombie pre-fix `status='active'` ranked_series rows as `abandoned` so historical queries that don't time-bound aren't lying about the live count.
- `/api/v1/tournaments/my-active-matches` now returns `photon_room_name`, `photon_region`, `my_ready`, `opp_ready`. Used by the new client-side dispatch loop (below).
- `/api/v1/series/active` returns `phase: "pre_match" | "live"` so clients can split tournament series between Tournament-tab and Live-Ranked-Games panel.
- Dropped a dead `grant()` stub in `_pay_prizes` that sat next to the active `do_grant()` — unused since some prior refactor, copy-paste trap.

**Tournament UX (client)**
- New **"Upcoming Match Bets"** section in the Tournament tab showing every active tournament series in `pre_match` phase with the same 3-row bet UI used in Live Ranked Games. Hides automatically when there's nothing to bet on.
- Live Ranked Games panel now **filters out** tournament series that haven't gone live (`is_tournament && phase == "pre_match"`). They reappear once any in-game activity registers.
- Tournament dispatch (auto-connect to the Photon room when both players ready) is now **tab-independent**: the existing `TournamentHeartbeatLoop` plugin-level coroutine — which already runs forever for ready-up signals — also fires `SetPendingRoom` when it sees a sync `ready` match with both players ready and a server-issued room name. Previously the dispatch only fired while the user was actively on the Tournament tab in F5, which routinely meant they missed the 5-min ready window from in-game.
- Visual bracket: replaced the collapsing-list bracket render with a positional canvas — each match is a 170×48 cell anchored at a computed (x, y) within `tBracketVisual`, with L-shaped connector lines drawn between prereq matches. WB columns top-left, LB columns bottom-left, GF column far right. Status colors (cyan completed, yellow ready, green active, gray pending). Falls back to a structure-only blank bracket of the right size during voting/locked phases so players can see the shape ahead of time.
- Auto-connect prefers server-issued `photon_room_name` over the legacy client-side derivation; three call sites updated (Reconnect button, my-room-code display, sync auto-dispatch).

**Tournament + private bets are bettable on the same terms as queue series**
- Earlier in the session I had auto-locked bets on tournament + private series with `lock_reason="tournament"` / `"private_room"`. Reverted — same lock rules as queue games (≥2 firefights into game 1, OR a game has been won, OR no meaningful odds). Display tags `[TOURNAMENT Async]` and `[PRIVATE]` stay so users still know what kind of match they're betting on. Discord embed mirrors with 🏆 prefix + `[Async]/[Sync]` suffix and a `PRE-MATCH` callout when phase=="pre_match".

**Leaver penalty fixes**
- `matchIsRanked` now persists across games of a series. `OnMatchStarted` re-derives it from the room's CustomProperties (mod-issued ranked rooms force-true, vanilla rooms with both players opted-in fall through). Previously `OnGameOver` cleared `matchIsRanked` at the end of every game, but the room-join branch that re-set it only fired once per Photon room — so games 2 and 3 of a ranked series were silently treated as casual: leaver reports skipped, session W/L tallied as casual, the `[POLL]` log line read "CASUAL Match Over" mid-ranked-series. Reproduced 2026-04-30 when Galaxy Ice DC'd mid-game-2 with ~6 firefights on the board and got no leaver penalty.
- Leaver threshold widened from `totalPts >= 2` to `totalPts >= 2 OR seriesGames >= 1`. Either path counts as meaningful play: 2+ firefights in the current game, or any prior game completed in the series. The earlier threshold treated only the current game's firefight count and missed leavers who walked early in game 2 of a 1-0 series.

**Eager preflight for private rooms**
- `series/preflight` now fires the moment we see the opponent's `cr_*` Photon properties — no longer waits for the HTTP `/mod/check` round trip. Discord `#live-bets` and the in-game Live Ranked Games panel now surface private 1v1 matches within ~10s of room entry instead of "a whole game late." Server's preflight handler is idempotent and returns `skipped` if either player isn't ranked, so eager calls are harmless.

**Block-trigger safety: verbose diagnostics**
- v1.26.3's silent skip on destroyed `BlockTrigger` instances was masking an upstream bug — players (Sir Blender, NotHoly reported post-v1.26.3) ending up with their MAIN block-effect trigger destroyed, so the cascade-skip kept the iterator alive but the player's block "didn't proc" because the visual+absorb effect lived on the destroyed trigger. The patch now logs the trigger type and instance state on every skip, AND adds a `Finalizer` backstop that catches any vanilla `NullReferenceException` inside `DoBlock` (with stack trace) so we get diagnostic data on the next reproduction.

## v1.26.4 — 2v2 assembly cascade fix

Two consecutive 2v2 tests with 4 players (Sid + 3 testers) hit the same disconnect pattern: ~30 seconds after Both-Ready, the server canceled the series with reason `assembly_timeout, 3/4 confirmed` and kicked all 4 players back to the menu. Root cause was the server's 15-second deadline for all 4 clients to post `/spawn-confirm` after the room is created — Photon region pinging routinely blows past that on slow connects (Sid's logs had ~390 lines of `Trying to connect to photon` before the join even started). Once any one client busted the deadline, the cancellation cascaded: each player's `OnPlayerLeftRoom` callback fired `/report-dc` on the room exits triggered by the cancellation, which only made things noisier server-side.

- **Server**: bumped `_ASSEMBLY_DEADLINE_SECONDS` 15 → 60. Realistic window for slow Photon connects + region pinging.
- **Client**: `OnPlayerLeftRoom` now early-returns when `GameStateWatcher.IsInMatch` is false. The 2v2 DC-reporting path is gated to actual gameplay (Round 1 has started); during the assembly phase, peer leaves are silently ignored and the server's own `assembly_timeout` handler resolves anything genuinely stuck. Once the match has started, real DCs still report normally.

Both fixes complement each other — the bumped deadline catches most slow-connect cases on its own, and the client gate prevents the false-DC cascade if anything still slips through.

## v1.26.3 — Tester feedback batch: unequip cosmetics, tournament push-back, block NRE safety, queue-state cleanup, mid-room ConnectToRegion diagnostic

**Cosmetics — clicking the equipped title or trail now unequips it.** Backend already supported `item_id=null` to clear the active title/trail, but the client never sent it; clicking an "Equipped" item just re-set the same value. Now the click handler detects re-click of an active single-equip cosmetic and sends `0` (translates to omitted query param → null). Button label flipped from `Equipped` → `Unequip` so the action is obvious.

**Tournaments — under-min-signup pushes the start back a week instead of cancelling.** Previously `lock_tournament` marked the tournament `cancelled` when fewer than `min_players` (8) confirmed signups had landed by `lock_at`, and the cadence skipped that whole week. Now the same condition slides `lock_at`, `voting_closes_at`, and `default_start_ts` (or `lock_at` for async) forward by 7 days, status stays `voting`, stale slot-votes whose `slot_ts` ≤ now are dropped, and the cron re-enters lock_tournament next week. Repeats until 8+ confirmed signups land or the community gives up. Async kind tracks `lock_at`; sync kind keeps the same time-of-day on the new date.

**Block NRE safety — `BlockTrigger.DoBlock` `Prefix` now skips destroyed instances.** Lexia's logs showed 9 NREs in a single round inside vanilla `BlockTrigger.DoBlock [0x0002a]` (reading `this.gameObject` on a destroyed Component). Vanilla's `Block.IDoBlock` iterator doesn't null-check before invoking each trigger; one dangling reference (likely a card teardown leak between rounds) blew up the rest of the trigger list, silently neutering all the player's blocks for the rest of the round. Patch returns `false` from the Prefix when `__instance == null` (Unity fake-null check) so the iterator continues with the remaining triggers.

**Queue state cleanup on `[QUEUE-JOINER]` 30s timeout.** The previous reset only cleared `pendingRankedRoom`. Now it also nulls `targetRoom` / `targetRegion` and explicitly clears `GameStateWatcher.LeavingForRanked = false`. Without this, a slow Photon connect that timed out left `LeavingForRanked = true` and could subsequently suppress legitimate DC-win counting in the next match.

**Diagnostic — `[NCH-DIAG]` traces every `NetworkConnectionHandler.ConnectToRegion` call.** Lopi's v1.26.1 logs showed an unexplained `connectToRegion us` mid-ranked-room that pulled him into a vanilla EU casual lobby and stranded Lexia. Our `MainMenuHandler` was disabled and our `QueueJoiner` doesn't fire `ConnectToRegion` once already in the target room, so something else is calling it — but we can't tell what without a stack. The new Prefix logs the call with a trimmed managed stack-trace whenever it fires while we're in a competitive room. Next reproduction will tell us the exact call site.

## v1.26.1 — Hotfix: card art auto-bootstraps for non-Thunderstore installs

The v1.26.0 Thunderstore bundle ships the 67 card PNGs alongside the DLL, so Thunderstore installs got the tier list export image working out of the box. The Discord installer and direct GitHub-DLL drops only deliver the DLL though, which left those users with text-only cells in the export and a missing image popup. v1.26.1 fixes that without requiring a re-install or installer update.

- `CardImageLoader.Initialize` now counts the PNGs in `cards/` and, if the count is below the expected 67, kicks off a background-thread download of `cards.zip` from the v1.26.0 GitHub release asset. Extracts the contents into the `cards/` folder, rescans, and the next export / popup picks up the freshly downloaded sprites.
- TLS 1.2 forced on `ServicePointManager` for older runtimes that default to TLS 1.1.
- Atomic dictionary swap (`_filesByKey` is `volatile` and replaced as a unit) so reads during the rescan never see a partial map.
- Failure path is silent except for a log line — if the user is offline at startup, the download will simply retry on next launch and the export keeps falling back to text in the meantime.

## v1.26.0 — Card art everywhere + Tier List Maker export overhaul

The Card Stats tab is now a fully fledged **Tier List Maker** with image-based card previews and a polished export pipeline — matching the popular ROUNDS tier-list-maker community sites but with your real ranked / casual / all-mode pick + win stats baked in.

**67 ROUNDS card icons ship with the mod.**
- New asset directory `BepInEx/plugins/CompetitiveRounds/cards/` populated by the build target. PNGs land beside the DLL on every Release / Thunderstore build.
- New `CardImageLoader.cs` lazy-loads each PNG into a cached `Sprite` on first request. Keys are normalized (lowercase, no spaces/punct), with a fall-through via `CardRarityLookup.GetCanonicalName` so server-form and display-form names both resolve.

**Card preview popup — image-first.**
- Click any card name in the Card Stats tab (My Stats, 2v2 page, leaderboard player detail) and you now see the full-color card art at 360×545 with click-anywhere-to-close. The art carries name + description + numerical stats baked in, so we no longer render those as text.
- Cards without art (none currently) fall back to the prior text-block popup automatically.

**Tier list export image — image-based, near-square aspect.**
- Each cell now shows the card art (220×330) + `## played` + `##% won`. Card name, rarity tag, and stat lines are gone — the art covers them.
- 12 cells per row at 3000-wide canvas. Aspect lands near 1:1 (was tall portrait at 1080-wide / 2400-wide / 1840-wide in earlier iterations) — looks balanced on both phone and PC viewers.
- Win-rate color band: `≥55% green / ≤45% red / otherwise white`.
- Steam-name watermark bottom-left, mod info bottom-right (italic dark grey).
- Output path unchanged: `<ROUNDS>/CompetitiveRoundsTierLists/tierlist-<filter>-<timestamp>.png`. RenderTexture pipeline so the image isn't capped to monitor aspect.

**Tier UI iteration in the Card Stats tab (preceded the image overhaul).**
- Tier column moved to the **left** of the row; tier letter is **bold black** for max contrast against the saturated tier color background.
- Click-to-cycle is now in-place (no re-render / re-sort) so editing one card no longer flips a different card's tier.
- Whole row gets a translucent tier-color highlight bounded to the data columns.
- Export Tier List button moved into the filter row (no longer its own row above the data).
- Sortable column headers including the new Tier column (Unranked sorts to bottom).

**Backend changes shipped in this version.**
- `docker-compose.yml`: added `RELEASES_CHANNEL` env var passthrough for the Discord bot's release-poll target.
- Migration `067_grant_lopidav_gold.sql`: one-shot 20,000g admin grant to lopidav (manual `/migrate` if not already applied).

## v1.25.25 — Card Stats UX iteration + Beta title scoped to mod users

**Card Stats tier column UX:**
- Tier moved to the LEFT side of the row (was rightmost). Header `Tier | Card | Rarity | Picks | Wins | WR% | Pass%`.
- Tier text is now **black** for max contrast on the saturated tier-color backgrounds.
- Tier column is **sortable** — clicking the header cycles asc/desc, with un-tiered cards always at the bottom.
- Each card row gets a translucent background tinted in its tier color (~25% alpha, so text stays readable). None state = transparent.

**Card preview popup fix:**
- The previous version cloned vanilla CardInfo prefabs under our screen-space overlay canvas; vanilla cards render in world space, so the preview just looked like a grey backdrop with a one-frame card flash.
- Replaced with a text-based modal: card name (bold), rarity tag (colored), italic description, stat block (each `CardInfoStat` rendered with its `amount` + name, green for positive, red for negative). Click anywhere outside to dismiss.

**Beta title scoped to actual mod users:**
- Migration 071 adds `players.mod_seen_at` and revokes the Beta grant from players whose record was auto-created from a casual-opponent match report (no signal of mod install). Result: 47 confirmed mod users keep Beta; 685 passive opponents lost it.
- New helper `_mark_mod_seen()` runs in mod-only endpoints (`/queue/join`, `/team/queue/join`, `/toggle-ranked`, `/achievements/unlock`, the reporter side of `/matches` and `/team/matches`, both sides of `/series/preflight`). Stamps `mod_seen_at` and grants Beta on first call.
- `get_or_create_player` no longer auto-grants Beta — passive opponent rows no longer inherit it.

## v1.25.24 — Names + private-room tag, Beta title, card tier-list, card preview, Discord betting

**Display names lag fix:** new players now appear with their actual nickname in Live Ranked Games / Recent Series instead of their bare Steam ID. `/series/preflight` accepts optional `p1_name` / `p2_name` and the client passes both Photon NickNames in.

**Private-room ranked games tagged + bet-locked:** migration 068 adds `ranked_series.is_private` (set true on preflight). `/series/active` returns the flag and forces `bets_locked=true` with `lock_reason="private_room"`. UI / Discord can now render a 🔒 PRIVATE tag and disable bet buttons.

**Beta title (#2A66B5 dark blue) + 19 new shop titles:** migration 069 adds the Beta title (free, auto-granted on every existing + future joiner via the `get_or_create_player` hook) plus card-themed titles — Poisoner, Windup, Reloader, Huge, Hasty, Bouncy, Healer, Bouncer, Tracker — and general flair — Sniper, Tank, Pacifist, Berserker, Phoenix, Specter, Blitz, Apex, Echo, Voidshot. All ≤ 11 chars (Grandmaster benchmark). Backfilled 731 existing players with the Beta grant + auto-equip if they had no active title.

**Card Stats tier-list (S/A/B/C/D/E/F):** migration 070 adds `player_card_tiers` (player + card + filter + tier). Per-player, three independent tier lists (Casual / Ranked / All). New endpoints `GET/POST /api/v1/players/{steam_id}/card-tiers`. Card Stats panel gets a new Tier column with click-to-cycle behavior; tier badges color-coded by letter (S=red → F=grey).

**Card preview popup:** clicking a card name in Card Stats spawns the actual ROUNDS card prefab as an inert visual under our overlay canvas. Photon components stripped on the clone so nothing in-game can be affected. Click outside to dismiss.

**Discord Live Ranked Games + betting (channel `1456460424831701074`):** new bot poller `poll_live_bets` posts/edits an embed per active series with bet buttons (`100g / 500g / 2000g` per player). Bets fire via the new `/api/v1/discord-bets` endpoint (X-Internal-Key auth) which resolves Discord user → linked player and reuses the in-game bet pipeline (banned check, odds floor, lock checks, gold balance, idempotency). Users must `!link` their Discord account first.

## v1.25.23 — Recent 2v2 Series cards: 2-per-line + tighter team columns

Hotfix on top of v1.25.22's stacked cards layout.

- Cards now stack 2 per line (`Card1, Card2`) instead of 1 per line — same total info but ~half the vertical space per game row.
- Team columns sit closer together: left/right column width 265 → 220, inter-column gap 12 → 4. The orange (opponents) column was unnecessarily spaced from the blue (allies) column.
- `CountCardLines` updated to `ceil(cards/2)` so per-game row height matches the new pair-per-line format.

## v1.25.22 — 2v2 UI/UX polish: scrollable tab, aligned leaderboard, mid-series auto-balance leg work

**Scrollable 2v2 tab:** the whole tab is now wrapped in a vertical ScrollView so the queue panels can grow to fit 8+ queuers each without crushing the leaderboard / history below. Bottom row sized to 720px so its internal scrollviews still work for tall data.

**2v2 Leaderboard rework:**
- Floating sort buttons replaced with clickable column headers above each data column (mirrors 1v1 leaderboard pattern). Active sort highlighted with a brighter button + `v` indicator.
- Columns: `# | Player | Rating | W-L | WR | Avg Mate Elo | Gold | XP`
- Title moved to suffix `Name [Title]` (was prefix). "Mate Elo" → "Avg Mate Elo".
- Capacity bumped to 100 visible rows (outer scroll handles overflow if more).

**Recent 2v2 Series:**
- Pagination buttons grouped on the same row as the header label, page indicator (`1/3`) sits between `<` / `>` buttons. Buttons hide when at first/last page.
- Per-game cards row: word-wrap enabled, row height bumped 44 → 64 so two-line wraps don't clip. Each card name capped at 14 chars + 4 cards per team max with `…` for overflow.
- Title also moved to suffix in opponent names.

**Mid-series auto-balance (backend leg work):**
- New `AUTO_BALANCE_SWAP_MARGIN = 3` constant on the server. After each match in an auto-balanced series whose point margin ≥ 3 (e.g., 5-2, 5-1, 5-0), the server swaps the weakest player on the winning team with the strongest player on the losing team for the NEXT match.
- `team_series.t1a/t1b/t2a/t2b` updated with the new partition; `team_queue.team_assigned` updated for all 4 so polls reflect the swap; `rebalance_count` incremented.
- `TeamMatchResponse.rebalance_assignments` populated as `{steam_id: 1|2}`.
- Client parses + logs `[2v2-REBALANCE]` and shows a notification ("Teams will rebalance next match!"). **Full client-side mid-match team mutation (TeamID + spawn + body color update propagation) is the next round's work** — the assignments arrive but the in-game swap still requires a Photon property update flow + skin re-bake.

## v1.25.21 — 2v2 mega follow-up: economy, leaderboard expansion, paginated history, queue/face/UI fixes

Heavy batch addressing tester feedback after v1.25.20.

**Discord bot:**
- `/team/queue/recent-joins` filters to `queue_type='auto'` so #ranked-looking-for-people no longer beacons Custom Lobby joins
- GitHub-release poller posts to `#releases` only (chat mirror dropped)

**2v2 economy (#new):**
- Migration `066_team_economy.sql` adds `players.team_gold_earned` + `players.team_xp_earned` and `team_series.t{1a,1b,2a,2b}_{gold,xp}_earned` columns
- Per-match XP base 600 with `x1.5` win multiplier (lands ~600 lost / ~900 won)
- `+50g` series winner / `+25g` series loser awarded on series completion
- 100xp=1g auto-conversion still applies, so a clean BO3 sweep stacks meaningful gold

**Matchmaker:**
- `_team_balance_rating` now also trusts the 2v2 rating when RD has converged below `TEAM_TRUST_2V2_RD_BELOW=110` even if `completed_series` is below the threshold. Fixes "Sid + Sid3 (both high 2v2 elo) got matched as teammates because the balancer fell back to 1v1 elo for the lower-series account."

**Live 2v2 series:**
- `RefreshLiveSeries` no longer early-returns when 1v1 list is empty — 2v2 series now render in the Live Ranked Games panel even when there are no 1v1 games in flight

**Recent 2v2 Series (rewritten):**
- New endpoint `/api/v1/team/all-series-paged?page=N&page_size=3` returns the global series feed with per-slot ratings, title, rating delta, gold + XP earned in that series, plus matches with `cards_by_player`
- F5 panel now paginates 3 series per page with `<` / `>` buttons
- Header line shows the caller's perspective (W/L from caller's team) plus their `+Ng / +Nxp` for the series; non-participants see neutral framing
- Per-game rows render team-aggregated cards with player names

**2v2 Leaderboard:**
- New columns: title prefix on names, average teammate elo, total 2v2 gold, total 2v2 XP
- Sortable: `Rating` / `Wins` / `WR` / `Mate Elo` / `Gold` / `XP` buttons cycle the sort
- Bumped capacity from 50 to 100 visible rows per page

**Queue UX:**
- Random Queue + Custom Lobbies panels heightened to fit ~8 queuers each (per tester report: previously cut into the leaderboard below)

**Card-pick face/character bug (#3 from tester):**
- Logs from `LogOutput(14).log` showed `cr_face property not set on remote player` for two of four players
- `FacePublisher.PublishLocal` now logs the specific early-return path (was silent before)
- `CardChoiceVisuals.Show` Postfix republishes our cr_face when this client is the picker (defends against the property-replication race)
- `OnPlayerEnteredRoom` republishes when a peer joins a competitive room (fixes the case where our `OnJoinedRoom` publish lands before the peer is connected)

**Misc client fixes:**
- Body-color toggle off now also re-bakes every player's `PlayerSkin` via vanilla's `Init` so live `SpriteRenderer.color` writes we couldn't track get redrawn
- Session Info now records all three opponents in 2v2 (vs the single-opponent latch from 1v1)
- My Stats Casual History `txtOpp` column widened 180→240px so long names no longer overflow into the FPS column

**Deferred (will tackle next round):**
- Auto-balance teams between matches in the same BO3 series — needs new server logic to recompute partition mid-series and propagate via team_assigned updates
- Regicide achievement gating: already 1v1-only by virtue of running only inside `submit_match` (the 2v2 path is `submit_team_match`). No change needed.

## v1.25.20 — 2v2 follow-up #2: card-pick body re-tinted to correct team color

**Card-pick body color fix (#3 from tester feedback):**
- Symptom: a team-1 picker's body rendered orange in the card-pick visualizer despite the in-match body rendering correctly. Only happens during the card-pick phase.
- Root cause: vanilla CardChoiceVisuals spawns a skin clone whose body sprites/particles get baked at instantiation time from a path our `PlayerSkinBank.GetPlayerSkinColors` patch can't reach. So in 2v2 the team-1 visualizer ended up with team-0 (orange) hue.
- Fix: new `CardPickBodyTinter` coroutine spawned from the `CardChoiceVisuals.Show` Postfix. Waits 4 frames for the visualizer's children to populate, walks `SpriteRenderer` + `ParticleSystem` + `PlayerSkin`/`PlayerSkinHandler` Color fields, and recolors anything that matches the wrong-team baseline to the picker's actual team color. Team colors resolved at first call by sniffing the most-saturated Color field on `PlayerSkinBank.skins[0/1]` directly (bypassing my own GetPlayerSkinColors patch).
- Logs `[CARDPICK-TINT]` lines counting how many sprites/particles/fields were retinted per pick.

## v1.25.19 — 2v2 follow-up: queue auto-refresh, per-game card history actually populates, no more phantom 1v1 series

Bug-fix pass after testing v1.25.18.

**Queue lists now auto-refresh:**
- `RefreshTeamTab` only ran on dirty events, so the Random Queue / Custom Lobbies panels stayed frozen until the user navigated away and back. Added `MaybeRefreshTeamTab` ticker (parallel to `MaybeRefreshLiveSeries`) that polls `/team/queue/list` every 2s while currentTab==8. Newly arriving queuers now appear without re-opening the menu.

**Per-game cards visible in 2v2 history:**
- Root cause: `FindMatchingBracket` only handles `[]`, but the `cards_by_player` parser passed it `{}`. Parser silently bailed every time so `cards_by_player` stayed empty. Added `FindMatchingBrace` and switched the call.
- Server data was fine (`team_match_cards` rows are populated). Existing series will now show per-game card breakdowns once the new client polls fresh history.

**Phantom 1v1 series from 2v2 rooms (#5):**
- `GameStateWatcher` series-preflight branch fired inside `cr_ff` (2v2) rooms because `inCrFf` forces `matchIsRanked=true`. That spawned a 1v1 `ranked_series` row alongside each 2v2 `team_series` (3 phantoms per 4-player match in the worst case — one per opponent the poll latched onto).
- Fix: gated the preflight on `!inCrFf`. The 2v2 path already creates `team_series` at queue lock; no 1v1 row should ever be created from inside a 2v2 room.
- Migration `065_invalidate_phantom_2v2_ranked_series.sql` cancels the 3 existing phantoms (active 1v1 series with no completed matches and live points).

**Face-apply diagnostic (#3):**
- `FacePublisher.TryReadAndApply` previously returned false silently on every failure path. Added `[POPUP-DIAG]` log lines that say exactly which gate tripped (no PhotonPlayer, no `cr_face` property, empty value, malformed). Next 2v2 session will surface why Sid2's character was missing on remote clients.

## v1.25.18 — 2v2 polish pass: decoupled queues, per-game cards in history, queue UX

Follow-up to v1.25.17 testing. Splits Random matchmaking from the Pick-Teams flow into two independent queues, restores per-game detail in 2v2 history, and tightens queue-list responsiveness.

**Decoupled queues (#1, #5):**
- Migration 064: `team_queue.queue_type` (`'auto'` | `'manual'`) + CHECK + index
- Matchmaker filters candidates by `queue_type` so the two queues never cross-match
- Manual queue: always honors each player's `preferred_team` (joining IS the consent — no quorum gate). Auto queue: always runs the elo balancer.
- F5 tab: two buttons — `Search Random` (auto) and `Find Custom Lobby` (manual). Team 1 / Team 2 buttons render only inside a custom lobby.
- `In Queue` panel split into two sections: `Random Queue (N)` and `Custom Lobbies (N)`. Each lists every queuer with name, balance rating, status, wait time, plus a `T1`/`T2` tag when a side is claimed.

**2v2 history detail (#6, #7):**
- `cards_by_player` (Steam-id keyed) now flows from `/team/match-history` so the F5 history can render each game's cards
- Per-series header (outcome + final score + elo delta + teams) followed by per-game rows beneath: `Game N: 5-2` plus `PlayerA: card1, card2 | PlayerB: card3, card4`

**Queue UX:**
- `(N searching)` count in the 2v2 header is green when anyone is searching (parity with 1v1 ranked)
- Team 1 / Team 2 buttons highlight the claimed side with `✓ Team N` and a brighter color
- Queue-list polling tightened from 5s → 2s so newly-arriving queuers appear without backing out

## v1.25.17 — 2v2 mega-pass: queue visibility, manual team selection, DC tracking + sticky teams, 2v2 betting

Big multi-feature pass building on the 2v2 ranked foundation.

**Bug fixes:**
- Card-pick face=null guard (Sid3/Sid4 unconfigured face wiped the visualizer's stock face — now suppressed when all 4 face IDs are zero)
- 2v2 history grouped by series (one row per series with final score + single elo delta — same shape as 1v1 ranked history)
- Session Info 2v2 row (`Ranked: AW/BL  2v2: CW/DL  Casual: EW/FL`)
- Top-left F5 player name refreshes from `CachedPlayerStats.display_name` (was set once at panel build)
- Vanilla `NCH.OnJoinedRoom` Postfix re-styles NickName immediately after vanilla resets it (race fix for "Sid's name styling didn't show")
- 2v2 leaderboard `min_series` default 3 → 1 so testers with one completed series show up

**Queue visibility (#8):**
- New `GET /api/v1/team/queue/list` endpoint returns every queuer with name, balance rating, status, wait time, manual-pick state
- F5 2v2 tab "In Queue" panel renders the list, refreshes every 5s

**Elo-fallback transparency (#10):**
- Queue rows now expose `using_fallback_rating` + `balance_rating` + `completed_series`
- UI shows e.g. `(1547 1v1, 2/10 2v2 series)` when matchmaker is using a player's 1v1 elo because their 2v2 sample is too small

**Manual team selection (#9, #11):**
- Migration 062: `team_queue.manual_pick_enabled`, `team_queue.preferred_team`, `team_series.was_auto_balanced`
- `POST /team/queue/manual-pick-toggle` and `POST /team/queue/preferred-team` endpoints
- Matchmaker honors `preferred_team` when 3+ queuers have the toggle on; otherwise auto-balances by elo (records `was_auto_balanced` accordingly)
- F5 UI: `[ ] Allow team picking` checkbox + `Team 1 (Orange)` / `Team 2 (Blue)` buttons (greyed when quorum not met or your checkbox is off; status shows e.g. `Auto-balance by elo (1/3 allowing — need 2 more)`)

**DC tracking + sticky teams + grace window (#7):**
- Migration 061: `team_matches.dc_player_id`/`dc_at`, `team_series.dc_grace_until`/`dc_team_remaining`/`dc_player_id`
- `POST /team/series/{id}/report-dc` endpoint applying the 2v2 DC rule (combined points >= 2 → match awarded to non-DC team; series may complete or pause for 5min grace)
- Lowest-Steam-ID-remaining client auto-reports the DC from `OnPlayerLeftRoom`
- `GET /team/series/{id}/state` extended with `dc_grace_seconds_remaining`, `dc_team_remaining`, `t1/t2_series_wins`; auto-completes series with forfeit-win to remaining team when grace expires
- Server queue-match: when a queuer rejoining is part of a `dc_paused` series with grace remaining and the other 3 originals are also queueing, locks them into the EXISTING series with the SAME teams (sticky-team requeue resume)
- F5 2v2 tab DC banner: `Series paused — same 4 can re-queue to resume X:XX (score N-N)`

**2v2 betting (#6):**
- Migration 063: `team_bets` table (player_id, team_series_id, bet_on_team, amount, odds_multiplier, payout)
- `POST /team-bets` endpoint with HMAC-signed payload mirroring 1v1 (one bet per series per player, gold debit-now / credit-on-settle, odds-uncertainty floor 1.10x)
- `GET /players/{steam_id}/team-bets` for personal bet history
- `GET /team/series/active` returns active 2v2 series with team-aggregated odds for the bet UI
- Settlement: when `submit_team_match` flips a series to completed, unsettled team_bets are paid out (winning team) or closed at 0 (losing team)
- F5 Live Series UI: 2v2 series render below 1v1 with header (`2v2  Sid+Sid2 (1547)  0-0  Sid3+Sid4 (1452)`) + 2 bet rows (one per team) with 100/500/2000g buttons

**Auto-balance after series (#12) — already implicit:** every fresh series re-balances using the latest ratings via the existing matchmaker. No new code needed; the `was_auto_balanced` flag is now stored on team_series for future "stay in room and re-roll teams" features if we add them.

## v1.25.16 — 422 fix on 2v2 report, pre-join nametag publish, card-pick diagnostic, test data cleanup

Three fixes plus test-data cleanup.

- **2v2 match report no longer rejected by server with HTTP 422.** v1.25.15 made `TryReportTeamMatch` succeed (Steam IDs resolved correctly) but the server then 422'd the payload because `display_name` exceeds the schema's `max_length=64`. Sid's NickName is the styled rich-text wrap (`<b><i><u><color=#FF1F8C><size=130%>Sid</size></color></u></i></b>`) — ~70 chars. The 1v1 path strips rich-text via `StripRichText()`; the 2v2 path didn't. Now it does (and clamps to 60 chars defensively).
- **Pre-join nametag/cosmetic publish** so all clients see styled NickName, body color, and trail from the *first* match of a series. Previously the publish happened post-room-join in `GameStateWatcher.OnRoomJoin` — too late: by the time it fires, remote clients have already cached the unstyled NickName from the actor's join broadcast and the in-game nametag label never refreshes. Publish now also fires in the `/queue/poll` `ready_join` handler, before `Plugin.SetPendingRoom`. User-reported: "Sid didn't show up with all the name stylizing on anyone's screen in the first game" + "body color didn't show until game 1 finished" — both pre-join issues, both fixed by publishing earlier.
- **`[CARDPICK-DIAG]` log on every `CardChoiceVisuals.Show`** — captures `currentSkin` state (active, layer, child count, position, scale). Next test will tell us why 2 of 4 pickers consistently show no character.

**Database cleanup (migration `060_cleanup_misrouted_2v2.sql`)** removed 28 1v1 matches that were 2v2 misroutes from the v1.25.13–15 testing window, all related cards/offers/flagged-matches rows, 16 orphaned 1v1 series, and 2 phantom `photon_*` player rows. `team_series` rows that never produced a match got status flipped to `canceled` with reason `test_misroute_cleanup_v1.25.15`.

## v1.25.15 — 2v2 logs in 2v2 tab, body colors propagate at room-join, round counter team color

Three root-cause fixes from v1.25.14 testing.

- **2v2 matches now actually log to the 2v2 tab.** Log confirmed `[2v2-REPORT] couldn't resolve Steam ID for actor 1` → `TryReportTeamMatch` aborts → falls through to the 1v1 path → match logs as casual 1v1 in My Stats. Root cause: our 2v2 `CreatePlayer` override deliberately skips `AssignUserID()` (to avoid pulling in extra ROUNDS identity machinery), so the `u_id` Photon custom property that peers use to resolve actor → Steam ID was never published. Without `u_id`, `ResolvePhotonSteamId()` falls back to `"photon_<actor>"` for each peer, and the canonical 4-player Steam-ID list can't be built. Fix: publish `u_id` (= local Steam ID) alongside `p_id` and `t_id` in both pre-join and `CreatePlayer` paths. With Steam IDs resolvable, `TryReportTeamMatch` succeeds, the report posts to `/team/matches`, and the 2v2 tab populates with all 4 players' cards, FPS, and Elo deltas.
- **Round counter shows orange + blue instead of orange + orange.** v1.25.14's `PlayerSkinBank.GetPlayerSkinColors` Prefix mapped `slot→team_skin` for every call — but UI code (`PointVisualizer`, `UIHandler`) calls `GetPlayerSkinColors(0)` and `(1)` to mean "team 0 color" and "team 1 color", not slot indices. The patch turned the `1` into `0`, so both round-counter dots got the orange skin. Now the Prefix stack-walks one frame up: only player-body call sites (`PlayerSkinHandler`, `Player`, `Holdable`, `HealthHandler`, `CharacterData`, `DeathEffect`, `CardChoiceVisuals`, etc.) get the slot→team mapping. UI calls pass straight through to vanilla.
- **Body color shows for everyone else from match-start, not "after game 1 finished".** Log timeline showed the local player's `[NAMETAG] Published` fired at room-join (line 525 in user log) but `[PCOLOR] Published` didn't fire until ~540 lines later mid-game-1. That's because `PlayerColorCosmetic.PublishLocalProps()` was only triggered from the periodic stats reload — not from the room-join hook. Fix: `PlayerColorCosmetic.PublishLocalProps()` and `TrailCosmetic.PublishLocalProps()` now fire alongside `NametagStyler.PublishToPhoton()` on every room join. Remotes' `DelayedApplyAll` always finds the props on first read.

Two issues from v1.25.14 testing still under investigation:
- **Sid's name effects/color stop working *for him locally* after game 1**, but show fine for everyone else. The glow renderer log shows the glow material being applied throughout — needs a label-text-rewriter check before patching.
- **Card-pick character missing for 2 of 4 pickers.** Log shows the face Postfix and skin-bank lookups firing successfully for all 4 — something else is hiding the GameObject. Need a Postfix that logs `currentSkin`'s state and position.

## v1.25.14 — Critical Harmony loader fix, auto-continue for 1v1, generalized cosmetic reapply

### Critical fix
- **`PlayerSkinBank.GetPlayerSkinColors` Prefix had its parameter mis-named (`playerID` instead of `team`).** HarmonyX binds Prefix parameters by NAME, threw `Parameter "playerID" not found`, `PatchAll()` aborted at that point, and **every Harmony patch declared after `PlayerSkinBank` in the assembly's iteration order silently failed to apply** for the past 4 releases (v1.25.10 through v1.25.13). That broke custom map colors (`ArtHandlerNextArtPatch` never applied), map physical wall tints (`MapPhysicalColorPatch` never applied), 2v2 spawn-point sort (`MapManager_GetSpawnPoints_2v2_Patch`), most of the `[2v2-DIAG]` patches, and the v1.25.13 card-pick face fix (`CardChoiceVisuals_Show_Competitive_Patch`). Renamed the parameter to `team` so HarmonyX can bind it correctly. Most of v1.25.10–13 effectively re-lands now.
- **Per-class Harmony patching with try/catch.** Replaced the single `PatchAll()` call with a per-class loop so one bad patch can't take everything else down. New `[HARMONY] Patches applied: N ok, M failed` log at startup, and any failure logs `[HARMONY] Failed to patch <Class>: <reason>` so future name mismatches surface immediately instead of silently disabling half the mod.

### 1v1 + tournament features (lessons from 2v2)
- **Auto-continue popup extended to 1v1 ranked + sync tournaments.** "People really don't like hitting Yes at the end of the game." Auto-confirm now fires in any mod-issued competitive room (`ranked_*`, `team_*`, `sct-*`). Vanilla casual / private rooms still get the manual popup so a mod-vs-vanilla match doesn't desync.
- **Cosmetic late-prop reapply generalized to all competitive rooms.** Originally added for 2v2; now also runs in 1v1 ranked + sync tournaments. `PlayerColorCosmetic.ReapplyForActor` and `TrailCosmetic.ReattachForActor` are called for every non-local actor every 2s for 12s after room join — catches custom colors and trails whose props were already cached at room-join time and never fired `OnPlayerPropertiesUpdate`.
- **Card-pick face Postfix extended to all competitive rooms.** The Photon-custom-prop face fallback (vanilla's `RPCA_SetFace` RPC has timing races) now applies in 1v1 + tournaments, not just 2v2.
- **`matchIsRanked` forced true at room-join for all mod-issued rooms.** Was only `cr_ff` previously; now also fires for `ranked_*` and `sct-*`. Belt-and-suspenders against the racy `CheckOpponentRanked` callback.
- **`[REPORT-ROUTE]` diagnostic on the 1v1/tournament report path.** Logs room name, isRanked, tournament-prefix detection, reporter and opponent — same shape as the `[2v2-REPORT-ROUTE]` log that caught the v1.25.11 silent fall-through. If a tournament match ever silently mis-routes, this surfaces it.

### Thunderstore
This release ships a fresh Thunderstore bundle.

## v1.25.13 — 2v2 card-pick character face + Thunderstore push

Internal-facing release — fixes the card-pick visualizer showing wrong/missing faces in 2v2.

- **Card-pick face now reads from Photon custom props instead of relying on RPC timing.** Vanilla `CardChoiceVisuals.Show` fires `RPCA_SetFace` with `RpcTarget.All` only from the picker's client. In 2v2 with 4 sequential pickers, the RPC for picker N can land *after* picker N+1's `Show()` has torn down the visualizer and re-instantiated the skin — so remote clients show "yesterday's picker" face, or no face at all if the timing is bad. New `FacePublisher.PublishLocal()` serializes the local player's `selectedPlayerFaces[0]` (eye/mouth/detail/detail2 IDs + offsets) to a Photon LocalPlayer custom prop `cr_face` at room-join. New `CardChoiceVisuals.Show` Postfix reads the picker's `cr_face` from their cached Photon state and applies via `CharacterCreatorItemEquipper.EquipFace` directly — eliminates the timing race entirely. Each client renders the right face on every pick, locally.

This release also pushes a fresh Thunderstore bundle alongside the GitHub release.

Scoped to `cr_ff` rooms only — 1v1 ranked, tournaments, and private rooms unaffected.

## v1.25.12 — 2v2 reporting + colors + trails actually working

Internal-facing release — third 2v2 testing session caught five distinct bugs from v1.25.11. All five addressed root-cause.

- **`teamID` reflection lookup was on the wrong class.** `TryReportTeamMatch` did `typeof(CharacterData).GetField("teamID", ...)` which always returned null because `teamID` is on the **`Player`** class (`m_teamID` private + `TeamID` public property), not `CharacterData`. The reflection silently failed every time, the function returned false, and the routing fell through to the 1v1 casual path. That's why every 2v2 match was logging as `CASUAL` 1v1 in My Stats. Replaced with direct `Player.TeamID` access via Krafs.Publicizer.
- **`matchIsRanked` was being set inside a racy callback.** Even when the routing fired, `matchIsRanked` was being computed inside `CheckOpponentRanked`'s callback against just one of three opponents, so a single mod-check race could leave it false. Now it's set to `true` at room-join time when the room has `cr_ff` — definitionally a ranked queue room.
- **PlayerSkinBank index math was wrong.** v1.25.10 mapped `playerID = (playerID/2)*2`, which sent slots 2/3 to skin **index 2** (whatever third color the prefab has — red or green). 1v1's actual mapping is index 0 = orange (team 0), index 1 = blue (team 1). Fixed to `playerID = playerID/2` so slots 0/1 → 0 (orange), slots 2/3 → 1 (blue). That's the source of the "offshoot red/orange and green colors" report.
- **PlayerColorCosmetic anim loop wasn't kicked from late re-applies.** The HSV cycle loop was only started inside `DelayedApplyAll` (called once at match-start). `ReapplyForActor` (called from late-arriving Photon prop updates and our 2v2 forced-reapply pass) added entries to `animByActor` but never started the loop, so prismatic stayed stuck on whatever static color was last published — for prismatic that's `#FFFFFF` (no static color), hence the "blinding white" report. Now `ApplyToPlayer` itself starts the loop on every animated-sku apply.
- **Trail cosmetic wasn't kicked from cr_ff early-apply.** The trail cosmetic's `DelayedAttachAll` only ran from `OnMatchStarted`, but PCColor had a separate cr_ff early-apply at room-join. Trails were left out, so other players never saw your trail until after a much later `OnMatchStarted` (which doesn't always fire correctly in 2v2). Added a sibling `TrailCosmetic.OnMatchStart()` call to the cr_ff early-apply path. Plus the `Repeated2v2PCColorReapply` loop now also calls `TrailCosmetic.ReattachForActor` on every actor every 2s for the first 12s.

Plus a misleading log fix: the `Force-StartGame timed out` warning no longer fires when the match is mid-play (it was looping until the 30s deadline because `GameManager.instance.isPlaying` flipped true and the inner condition stopped matching).

Scoped to `cr_ff` rooms only — 1v1 ranked, tournaments, and private rooms unaffected.

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
