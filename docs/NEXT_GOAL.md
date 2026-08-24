# Next /goal — work queue Sid set up 2026-05-29

## Status as of 2026-05-30 goal pass

| # | Item | State |
|---|------|-------|
| 1 | Right-click block bug diagnostic | DONE — `[BLOCK-TEAM]` log line wired in `BlockTryBlockCounterPatch` postfix; next 2v2 repro will tell us if team-2/non-host is the common factor |
| 2 | Card chip tooltips in F5 history | **FULLY DONE** — 2-letter chips by default + chips↔FULL toggle (persists via `PlayerPrefs`) + true per-row hover tooltip rendered via IMGUI in `CompetitiveUI.DrawCardHoverTooltip`. Hit-tested in screen space via `RectTransform.GetWorldCorners` + canvas-mode detection (handles both Screen Space - Overlay and Screen Space - Camera) |
| 3 | Leaderboard graph "losing" games | DONE — server LIMIT bumped 20→500, ordering switched to ASC; client buckets to ~100 points when history is long |
| 4 | Body Colors + Name Style effects | **FULLY DONE** — 4 body colors at 4000g (migration 092), 6 standard nametag options at 100g (migration 093: Emerald/Amber/Coral/Indigo colors, XL size, Floating effect), and 2 premium effect nametags at 1000g (migration 094: **Rainbow Name** with per-letter color cycling across a 6-color palette, **Sunset Gradient** with amber→pink split). All rendered natively by TMP rich-text — no shader code, no per-frame string rebuild |
| 5 | Level rewards (100g/5lvl, 500g 55+) | DONE — wired into `submit_match` + `submit_team_match`. Migration 091 backfilled 45 players, 20,100g total |
| 6 | Performance pass (port from `PerformanceImprovements.Patches.StunPlayerPatchGo.cs`) | **8 of 18 PATCHES PORTED** — added `MenuControllerHandlerUpdateBail` (skip menu-controller Update during an active match) on top of the 7 from the previous pass. Remaining 10 are heavy rendering-pipeline rewrites (DynamicParticles.PlayBulletHit method replacement, GeneralParticleSystem.Play caps, PlayerSkinParticle Init/OnEnable/BlinkColor visual-disable swaps, ProjectileCollision.Die rewrite, CardChoiceVisuals.Show overlay, ArtHandler.NextArt particle caps) that REPLACE original methods rather than just guard them. Each needs an in-game soak before shipping — bad port = visible regression |

---



Five items the user wanted but didn't fit in the same pass as the matchmaking-overlay /
series-gold / match-history-cap fixes. Tackle in this order — items higher in the list have
clearer scope, items lower are open-ended.

## 1. Right-click block bug — non-host (blue / team 2) only
- User report: happened in a ranked game to opponent after game 2. Suspicion that it only
  hits team 2 (non-host) players, not team 1 (host).
- Existing patches: `BlockTryBlockScrubPatch`, `GMArmsRaceStartGameBlockResetPatch`,
  `BlockTriggerDoBlockNullSafetyPatch` in `plugin/Plugin.cs`. All gated on
  `CompetitiveRoomDetect.IsCompetitiveRoom()` already.
- Next step: add `[POPUP-DIAG]`-style structured log in `Block.TryBlock` Prefix capturing
  the local player's `m_playerId`, team, and `CharacterData.player.data.team` so the next
  repro pins down whether team-2 is the common factor. If confirmed, focus the patch on
  PlayerSkin/CharacterData lookup paths that are known to differ for non-host clients.

## 2. Card abbreviation tooltip in F5 history
- Vanilla ROUNDS shows each card as a 2-letter chip in the top-right and tooltips the full
  card on hover. Sid wants the same affordance in:
  - Casual history (My Stats tab)
  - Ranked history (My Stats tab)
  - 2v2 history (2v2 tab → Series Detail)
- Today each row shows a `cards_display` string. Replace with a per-card chip (`UIFactory`
  small button + tooltip) using the existing 67-card art bundle that the mod already loads
  (`[CARD-ART] indexed 67 card images from .../cards`). Hover tooltip should render the
  full card panel (name + rarity + description) similar to how the current `cards_picked`
  long-string already lays out.
- Performance: a 100-row history × 7 cards = 700 chips. Use the existing UI pool pattern.

## 3. Leaderboard rating graph "losing" games
- Sid's report: graph appears to skip points / show partial history. Should show the entire
  series-rating-change timeline.
- Source: `players/{steam_id}/stats` returns `rating_history` (populated inline on series completion; the old "Monday 3AM cron" never existed
  + inline on series completion). Confirm it's actually being populated for everyone (see
  earlier learnings — empty `rating_history` has been a real bug before).
- If too many points (>200), bucket by date and show daily averages so the graph stays
  readable instead of dropping points silently.

## 4. Body Colors + Name Style effects expansion
- Sid wants more pleasant + unique options:
  - New body colors (look at the existing shop tab to see what's already there — avoid
    duplicates with current SKUs)
  - New name effects beyond plain color (e.g., gradient, animated rainbow, pulse, shimmer,
    drop-shadow, outline). TMPro rich-text supports `<color>`, `<size>`, `<rotate>`,
    `<voffset>`. Check what's renderable with the Gravity SDF font (no glow / no italic
    per learning #14).
- Treat as a shop-content expansion: schema for each new SKU + price + bundle key, art
  asset (none — chip is just text or solid color square), client renderer.

## 5. Level rewards
- 100 gold every 5 levels up to level 50, then 500 gold every 5 levels.
- Detection: post-XP-grant block in `submit_match` (and `submit_team_match`) — check if
  level crossed a 5x threshold this submission; if yes, grant + `GoldTransaction` row with
  `reason='level_reward'`.
- Backfill migration for players already past existing milestones.

## 6. Performance improvements — port `PerformanceImprovements.Patches.StunPlayerPatchGo.cs`
- Source file at `A:/Downloads/PerformanceImprovements.Patches.StunPlayerPatchGo.cs`
  (107KB, from a community Performance Improvements mod for the old ROUNDS version).
- Goal: pull whichever patches are safe + applicable to current ROUNDS 1.1.2 into our mod.
  Expect Harmony patches that swap O(n²) operations for spatial-hash lookups, deferred
  destruction, particle pool reuse.
- Each ported patch needs:
  - Compile-time check that the vanilla method signature still exists
  - Gating on `CompetitiveRoomDetect.IsCompetitiveRoom()` or unconditional (case-by-case)
  - A `[PERF]` log line on first invocation per match so we can see what's actually firing

## Things to know
- Can NOT control kb/mouse from this session — Sid still has to launch ROUNDS himself
  after each `/build-mod` and test in-game.
- Standing instructions: comment on the relevant bug-report number (`bug-comment:N|...`)
  whenever shipping a fix that addresses one. Sid closes the reports himself.
- v1.26.7 was shipped on 2026-05-27; everything since is in a v1.26.8 backlog (achievement
  desc, Tag Team Sweep criteria, lobby-code ranked race, async cadence, focus override +
  watchdog, series_win gold misrouting, match history cap bump). Ship when Sid says go.
