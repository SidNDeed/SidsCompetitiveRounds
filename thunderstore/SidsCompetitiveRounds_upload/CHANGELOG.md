# Sid's Competitive Rounds — Changelog

## v1.26.3 — Tester feedback batch: unequip cosmetics, tournament push-back, block NRE safety, queue cleanup

- **Cosmetics**: clicking an equipped title or trail now unequips it (was previously a no-op). Button label flipped from `Equipped` → `Unequip`.
- **Tournaments**: when fewer than 8 confirmed signups land by lock time, the tournament now pushes its start back by 7 days instead of cancelling — keeps the cadence going while the community rallies. Stale time-slot votes (slot ≤ now) get cleared on each push.
- **Block NRE safety**: vanilla `BlockTrigger.DoBlock` was throwing NRE when one of `Block.triggers[]` was a destroyed reference, abandoning the rest of the trigger list and silently neutering the player's blocks for the round. Added a Prefix that skips destroyed instances cleanly.
- **Queue state cleanup**: the 30s `[QUEUE-JOINER]` timeout now clears `targetRoom`, `targetRegion`, and `GameStateWatcher.LeavingForRanked` (previously only cleared the pending room name). Slow Photon connects that timed out could otherwise suppress legitimate DC-win counting in the next match.
- **Diagnostic**: `[NCH-DIAG]` Prefix on `NetworkConnectionHandler.ConnectToRegion` logs every call with a trimmed stack-trace when we're in a competitive room, to chase down a v1.26.1 report of mid-room casual-fallthrough.

## v1.26.1 — Hotfix: card art auto-bootstraps for non-Thunderstore installs

Discord-installer and direct-DLL users on v1.26.0 ended up without the 67 card PNGs in `cards/`, so their tier-list export rendered every cell as text instead of art. v1.26.1 makes the loader fetch missing card art automatically.

- `CardImageLoader` counts cards on startup. If fewer than 67 are present, a background thread downloads `cards.zip` from the v1.26.0 release asset and extracts it into `cards/`. Future exports and the in-game popup pick up the new sprites without restart in most cases (a relaunch guarantees it).
- Thunderstore users were never affected — the bundle ships the cards directly — but the auto-bootstrap is harmless: scan finds 67, download is skipped.

## v1.26.0 — Card art everywhere + Tier List Maker export overhaul

The Card Stats tab is now a fully fledged **Tier List Maker** with image-based card previews and a polished export pipeline — matching the popular ROUNDS tier-list-maker community sites but with your real ranked / casual / all-mode pick + win stats baked in.

- **67 ROUNDS card icons** ship with the mod. Card preview popup (clicked from Card Stats / My Stats / 2v2 tabs) now shows the full-color card art at 360×545 with click-anywhere-to-close.
- **Tier list export image** rebuilt — each cell now shows the card art (220×330) + `## played` + `##% won`. 12 cells per row at 3000-wide canvas, near-square aspect (was tall portrait in earlier passes).
- Win-rate color band: ≥55% green / ≤45% red / otherwise white. Steam-name watermark bottom-left, mod info bottom-right (italic dark grey).
- Output: `<ROUNDS>/CompetitiveRoundsTierLists/tierlist-<filter>-<timestamp>.png`. RenderTexture pipeline so the image isn't capped to monitor aspect.
- **Tier UI in the Card Stats tab**: tier column moved to the LEFT, bold black letter for max contrast. Click-to-cycle is in-place (no re-render / re-sort) so editing one card no longer flips a different card's tier. Whole row gets a translucent tier-color highlight bounded to the data columns. Sortable column headers including the Tier column.

## v1.25.23 — Recent 2v2 Series cards: 2-per-line + tighter team columns

Hotfix on top of v1.25.22's stacked cards layout.

- Cards now stack 2 per line (`Card1, Card2`) instead of 1 per line — same total info but ~half the vertical space per game row.
- Team columns sit closer together: column width 265 → 220, inter-column gap 12 → 4. The orange (opponents) column was unnecessarily spaced from the blue (allies) column.

## v1.25.22 — 2v2 polish: scrollable tab, aligned leaderboard, mid-series rebalance leg work

- Whole 2v2 tab wrapped in a vertical ScrollView so the queue panels can grow to fit 8+ queuers each without crushing the leaderboard / history below.
- 2v2 Leaderboard rework: floating sort buttons replaced with clickable column headers aligned to data columns. Title moved to suffix `Name [Title]`. "Mate Elo" → "Avg Mate Elo". Capacity bumped to 100 visible rows. Active sort highlighted with a brighter button + `v` indicator. Columns: `# | Player | Rating | W-L | WR | Avg Mate Elo | Gold | XP`.
- Recent 2v2 Series: pagination row inline with the header label (`< 1/3 >`); buttons hide at first/last page. Per-game card display rebuilt: instead of one snake line, each game shows two stacked card columns side-by-side (left team / right team). Each column lists every card pick grouped under the player's bolded name, no truncation. Row height auto-grows to fit the taller column.
- Mid-series auto-balance (backend leg work): after each non-completing match in an auto-balanced series whose point margin ≥ 3, the server swaps the weakest winner with the strongest loser for the NEXT match. `team_series` slot order + `team_queue.team_assigned` updated; `rebalance_count` incremented. `TeamMatchResponse.rebalance_assignments` populated. Client parses, logs `[2v2-REBALANCE]`, shows a notification. Full client-side mid-match team mutation (TeamID + spawn + body color update propagation) is the next round's work.

## v1.25.21 — 2v2 mega follow-up: economy, leaderboard expansion, paginated history, queue/face/UI fixes

- **2v2 economy**: per-match XP base 600 with x1.5 win multiplier (~600 lost / ~900 won), `+50g` series winner / `+25g` series loser. Tracked separately on `players.team_{gold,xp}_earned` so the leaderboard can surface "Total 2v2 Gold" / "Total 2v2 XP" without summing transactions.
- **Matchmaker fix**: trusts 2v2 elo when RD has converged below 110 even with low series count. Fixes the case where two high-elo veterans (one with 20 series, one with 4) couldn't get matched as opponents because the balancer fell back to the new account's 1v1 elo.
- **Live 2v2 series**: the Live Ranked Games panel now renders 2v2 entries even when there are no 1v1 games in flight (early-return bug).
- **Recent 2v2 Series rewritten** off a new `/team/all-series-paged` endpoint — now shows the global series feed (every player can see every series), paginated 3 per page, with per-slot ratings + title + rating delta + gold + XP earned plus per-game card breakdowns.
- **2v2 Leaderboard expanded** with title prefix, average teammate elo, total 2v2 gold + XP. Sortable by `Rating / Wins / WR / Avg Mate Elo / Gold / XP`.
- **Decoupled queues** — Random matchmaking vs Custom-Lobby pick-teams flow are now two independent queues that never cross-match. F5 tab gets `Search Random` and `Find Custom Lobby` buttons. `In Queue` panel splits into `Random Queue (N)` and `Custom Lobbies (N)` sections.
- **Card-pick face/character bug**: `FacePublisher.PublishLocal()` now logs the specific early-return path; republishes when this client is the picker AND when a peer joins the room (defends against the property-replication race that was leaving 2 of 4 players faceless).
- **Card-pick body color** in 2v2 was rendering with the wrong team's hue at card-pick despite the in-match body rendering correctly. New `CardPickBodyTinter` coroutine walks the visualizer hierarchy and recolors anything that matches the wrong-team baseline to the picker's actual team color.
- **Body-color toggle off** now also re-bakes every player's `PlayerSkin` via vanilla's `PlayerSkinHandler.Init` so live `SpriteRenderer.color` writes get redrawn.
- **Misc**: Casual History `txtOpp` column widened so long names don't bleed into the FPS column. Session Info now records all three opponents in 2v2 (was a single-opponent latch from 1v1).

## v1.25.20 — Card-pick body color fix

A team-1 picker's body rendered as the wrong team color (orange) in the card-pick visualizer despite the in-match body rendering correctly. Vanilla `CardChoiceVisuals` spawns a skin clone whose body sprites/particles get baked at instantiation time from a path our `PlayerSkinBank.GetPlayerSkinColors` patch couldn't reach. New `CardPickBodyTinter` coroutine fires from the `CardChoiceVisuals.Show` Postfix, waits 4 frames for the visualizer's children to populate, walks every `SpriteRenderer`, `ParticleSystem`, and `PlayerSkin/Handler` Color field, and recolors anything that matches the wrong-team baseline.

## v1.25.19 — Queue auto-refresh, per-game card history actually populates, no phantom 1v1 series

- `RefreshTeamTab` only ran on dirty events so the Random Queue / Custom Lobbies panels stayed frozen. Added a per-frame ticker that polls every 2s while you're on the 2v2 tab.
- Per-game cards in 2v2 history were silently failing to render because `FindMatchingBracket` only handles `[]` and the `cards_by_player` object needs `{}` matching. Added `FindMatchingBrace`. Server data was always there.
- `GameStateWatcher` series-preflight branch was creating phantom 1v1 `ranked_series` rows inside `cr_ff` rooms (up to 3 per match — one per opponent the poll latched onto). Gated to non-2v2 rooms. Phantoms cleaned up server-side.
- `FacePublisher.TryReadAndApply` previously returned false silently on every fail path. Now logs `[POPUP-DIAG]` with the specific gate that tripped.

## v1.25.18 — Decoupled Random vs Pick-Teams 2v2 queues + per-game card history + queue UX

- Two independent queues. `Search Random` joins matchmaking; `Find Custom Lobby` joins the pick-teams flow. They never cross-match.
- Manual queue always honors each player's `preferred_team` — joining IS the consent, no quorum gate.
- F5 `In Queue` panel split into `Random Queue (N)` and `Custom Lobbies (N)` sections.
- Per-series header restored as the parent row (outcome + final score + elo delta + teams) with per-game rows beneath, each showing `Game N: 5-2` and the cards each team picked.
- `(N searching)` count in the 2v2 header turns green when anyone is searching.
- Team 1 / Team 2 buttons highlight the claimed side with `✓ Team N` and a brighter color.
- Queue-list polling tightened from 5s → 2s.

## v1.25.14 — Critical Harmony loader fix + 1v1 quality-of-life

A single mis-named parameter in v1.25.10 silently broke a chunk of the mod's Harmony patches for the past 4 releases. Fixed in this drop, and the Harmony loader is now resilient (one bad patch can't disable everything else).

**What re-lands now that the loader is fixed:**
- Custom map colors (the post-process color grading + wall tint patches) reliably apply on map load and on Shift cycle.
- 2v2 spawn-point sort by X (so team 0 lands left, team 1 lands right).
- Card-pick face Postfix (Photon-custom-prop face fallback for the RPC timing race).
- A bunch of `[2v2-DIAG]` patches that surface failures.

**1v1 + sync-tournament quality-of-life:**
- **Auto-continue popup** — the post-game "Continue?" prompt auto-confirms in any mod-issued ranked room (1v1 ranked, 2v2, sync tournaments). Vanilla casual / private rooms still get the manual popup. Players who want to leave can simply leave during the next card pick.
- **Cosmetic late-prop reapply** — opponents' custom body colors and trails now show reliably even when the Photon properties were cached at room-join time (no `OnPlayerPropertiesUpdate` event fires for that case).
- **Card-pick face fix** — the right face now shows next to the picker on every client (no more RPC timing races).

## v1.25.13 — 2v2 mode lands

The big drop since the last Thunderstore release: 2-vs-2 ranked matchmaking, with a separate Glicko-2 ladder, queue, balancer, ready-up flow, and Discord channel. Plus all the cosmetic and stability work in between.

**2v2 ranked mode** — search the 2v2 tab in F5. Server matches you and a teammate against another pair, all 4 ready-up, you spawn into a `cr_ff`-flagged Photon room with proper team-based spawn positions, color-grouped skins, all 4 players' card-pick bars visible, and faces synced via Photon custom props (no RPC timing races). Continue prompts auto-confirm so all 4 advance together. Match-assembly timeout at 15s if fewer than 4 players spawn. Vanilla disconnect cascade fires gracefully if any player leaves mid-match. Full 2v2 leaderboard, stats tab, match history, and Discord live-game beacon.

**Body colors + neon nametags** — new Body Color shop subtab with 21 tints across 4 tiers (3000g-8000g, including animated Prismatic + Chrome). 7 new Neon nametag styles at 500g each with matching SDF glow halos.

**FPS in match history** — both players' average FPS now captured and rendered per match.

**Block debug overlay** — toggle in Settings to visualize block timing classifications during play.

**Bug fixes since 1.25.3** — DC-at-4-rounds exploit, `vunknown` / `v2.1.0` installer bugs, phantom-ranked private-room matches, leaderboard pagination cap, MapTransition NRE on map-cycle particle tinting, and dozens of 2v2-specific fixes (auto-spawn, late-joiner GM_ArmsRace activation, character-select OOB, Searching overlay cleanup, prismatic anim loop kicking, late trail prop reapply, cosmetic skin re-bake after AssignPlayerID, match reporting routing).

## v1.25.3 — DC exploit fix, ranked-detection race fix, private-room series visibility

Non-mandatory but recommended.

- **DC-at-4-rounds exploit closed.** Disconnecting at 4 rounds while ahead no longer gives the DC'er the win. Cancels unless both players are at ≥4 (4-4 tiebreak goes to the non-DC'er). Leave-% penalty still applies.
- **First-match-vs-new-opponent ranked-detection fix.** When two mod users met for the first time, a startup-sync race could leave the match flagged casual permanently. Opponent ranked-check now retries every 5s while in room, picks up status when sync lands.
- **Private-room ranked games appear in Live Ranked Games immediately** via a new preflight beacon. Previously the series row was only created at first-match-completion.
- **Internal**: 2v2 lock-path fixes, block-activation counter only credits when block was actually ready (no inflation from cooldown right-clicks).

## v1.25.2 — Hotfix follow-up

- **Ranked detection corrected.** Random vanilla matchmaking between two real mod users counts as ranked again — that's the intended path. v1.25.1's room-name gate broke that. New check: opponent must have the mod actively running (Photon `cr_*` custom property presence). Vanilla players → casual; two real mod users → ranked.
- **Auto-installer "v2.1.0" bug fixed.** v1.25.1's regex was reading `netstandard, Version=2.1.0.0` instead of the real ModVersion. Now anchors directly on the BepInPlugin attribute layout.

## v1.25.1 — Hotfixes

- **Casual private-room matches no longer get reported as ranked** (note: corrected in 1.25.2 — the original 1.25.1 fix over-reached). Server-side data correction was applied.
- **Block activation counter** no longer increments while your block is on cooldown. Idle right-clicks were inflating your activation denominator.
- **Auto-installer "vunknown"** detection fixed for v1.20.0+ (further refined in 1.25.2).

## v1.25.0 — Body colors, neon nametags, FPS tracking, polish

Non-mandatory update.

### Body Color shop tab
- New **Body Color** category in the F5 Shop. Override the default orange/blue team color with a tint of your choice. Visible to everyone with the mod.
- 21 colors across 4 tiers — 10 × 3000g solid, 5 × 4000g jewel/metallic, 4 × 5000g neons, 2 × 8000g animated specials (**Prismatic** cycles the rainbow during combat, **Chrome** does a soft shifting cool-grey).
- Cosmetic-aware tinting filters out the face / gun / block-orb / cosmetic trails — only what was originally team-colored gets repainted.
- Colors apply from the moment you spawn (pick phase #1 included).
- New Settings toggle **`Custom player body colors: ON / OFF`** for anyone who finds the cross-player tints distracting.

### Neon nametag tier (500g each)
- 7 new **Neon** name styles (Pink, Cyan, Lime, Orange, Violet, Toxic, Glow Yellow) — brighter than the regular color set, each with a matching SDF-glow halo for modded clients. Non-modded players still see the bright color via Photon NickName rich-text.
- Single-active within the color slot. Sort order clusters Neons together as a premium block.

### FPS in match history
- Average FPS for both players is captured per match and shown next to the opponent name in History rows. Player side blue, opponent red. Opponent FPS only fills in if your opponent also has v1.25+.

### Block debug overlay (opt-in)
- New Settings toggle. Corner panel shows live block-activation vs success counts plus per-hit timing classification (`TOO SLOW`, `TOO EARLY`, `unblockable?`). Default off.

### Misc
- Leaderboard now shows top 100 on page 1.
- Discord auto-leaderboard expanded to top 100 with prev/next buttons.
- **Immovable Object** achievement no longer false-flags when you press Enter and type in chat.

## v1.24.0 — Automated tournaments (Phase 1 + Phase 2)

Non-mandatory update. Older clients still work against the live API — they just don't see the Tournaments tab or the auto-connect flow.

### Tournaments tab — sync + async modes

- **New F5 menu tab: "Tournaments"** with a SYNC / ASYNC sub-tab toggle.
- **Sync tournaments**: auto-created weekly, default slot = Saturday 12:00 PT. 7-day signup window; voting on 8 alternate start slots within ±24h of default (tallies hidden until you vote). Force-start unlocks at 8 signups with unanimous vote in a 30-min window.
- **Async tournaments**: auto-created every 6 weeks. Bracket visible from start; no scheduled start — matches activate on signup lock and each carries a 7-day deadline. Players self-coordinate via Discord (`/dm-opponent`, `/opp-online`). When both have Ranked enabled and play any private lobby, the mod auto-detects and records the result.
- **Format (both modes)**: **double-elim BO3**. Parallel play keeps 16p sync wall-clock ~90–120 min. LB absorbs WB losers round-by-round; Grand Final has bracket reset if LB champ wins first BO3.
- **Top seeds get byes** when <16 sign up. All matches count toward ranked Elo.
- **Bracket**: click-to-expand rounds. Default state shows compact round headers with `[+]`/`[-]` toggles and progress summaries.
- **Timezone picker** — tap to cycle through Local / UTC / PT / MT / CT / ET / UK / CET / EET / MSK / JST / AEST.
- **TOURNAMENT GAME indicator** under the top RANKED status when you're in a ROUNDS room with a tournament opponent.
- **Auto-enable Ranked** per-match: the mod flips Ranked on the moment your tournament match goes active.

### Auto-connect (sync)

- **Deterministic room code** derived from match_id (`sct-<prefix>`). Both clients land in the same Photon room.
- **Region-pinned**: each tournament's canonical Photon region is the mode across all signups. Auto-connect calls `ConnectToRegion` before `JoinOrCreateRoom` so cross-region pairings don't miss.
- **Reconnect button** + visible room code for manual join if auto-connect fails.
- **Plugin-level heartbeat** fires every 20s whenever you have an active tournament match — regardless of which F5 tab is open. Keeps `ready_at` fresh during gameplay.

### Discord bot

- Lifecycle announcements in `TOURNAMENT_CHANNEL` (signups open, locked roster, tournament started, podium).
- DMs to participants: signup confirm with seed, match-ready (sync + async variants), 24h deadline warning for async, daily "still pending" nag after 3 days.
- `/dm-opponent <message>` — rate-limited 8/min relay.
- `/opp-online` — check if your async opponent is online in Discord.
- Trophy roles on completion: `SCR Tournament Winner` / `Runner Up` / `3rd Place` with `(x2)` promotion on repeat placements. `SCR Tournament Participant` → `Participant 2` promotion.

### Prizes

- **Full tier (16+ players)**: 1st = 500g + 2500 XP, 2nd = 300g + 1500 XP, 3rd = 60g + 75 XP, plus trophy roles.
- Scaled 60% at 12–15 players, 30% at 8–11. Under 8 signups → tournament cancelled.

### Penalty system

- Rolling 90-day show rate with linear decay. Displayed on Tournaments tab; tiebreaker for >16 signups.
- `~` prefix marks speculative overflow slots; penalty-free late signups can bump higher-penalty speculatives before lock.
- **Leave semantics**: free during voting / locked (speculative promoted into your slot); during running, no-show forfeits + penalty.
- **Deadline tiebreak**: mutual no-show awards to lower-penalty player.

### Cross-tournament safeguards

- Player blocks auto-cleared between confirmed tournament participants at lock.
- Series lookup uses `ORDER BY created_at DESC LIMIT 1` so a player in multiple active tournaments against the same opponent doesn't crash the match handler.
- `with_for_update()` on advance-match SELECT serializes tick/hook races.

### Other UI polish

- Per-signup **bracket progress labels**: "WB R2", "LB R3", "eliminated LB R2", "CHAMPION".
- **Tournament history** on leaderboard click-a-player detail (trophy counts + last 4 placements).
- **Recent Tournaments** panel on the Tournaments tab.
- **All F5 text bold** via rich-text `<b>` fallback — readable on any SDF atlas that silently no-ops `fontStyle=Bold`.

### Signup requirements

- **Discord must be linked** (get code from My Stats tab → Discord Link → `!link CODE` in Discord).

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
