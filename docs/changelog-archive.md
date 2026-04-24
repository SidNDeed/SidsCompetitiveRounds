# Sid's Competitive Rounds — Completed-work archive

Prior sessions' "Completed This Session" entries. Newest dated heading on top. See `docs/CHANGELOG.md` for the version-oriented record; this file is organized by when the work was done, not by what version carried it.

---

## 2026-04-22 — v1.23.0 shipped (nametag styles, multi-color maps, hit/block/pass stats)

### v1.23.0 — Nametag Styles, Multi-Color Maps, Hit/Block/Pass Stats, Polish
Lifetime Hit % / Block % / Card Pass % stats with per-projectile hit gating and 1s dedup on block successes. 16 stackable nametag style SKUs (bold/italic/underline/strike + 6 colors + 3 sizes + 3 font transforms) visible to modded AND vanilla opponents via rich-text NickName. Multi-equip map colors with in-match Shift cycle (previously single-active). Shop category tabs + 200-row pool fix for "disappearing items". Ranked gold doubled + ranked XP multiplier 1.2x→1.5x. Live Ranked Games header pulsing (2.5s cadence). Card-name dedup: 175 offers + 297 match-cards across 11 variants. Phantom offline-room matches blocked + purged. New-install ranked-sync race fixed. Full details: CHANGELOG.md v1.23.0.

### v1.23.1 — Map cycle moving-box tint regression hotfix
Pressing Left Shift to cycle map colors was tinting every SpriteRenderer under `Map/*` (the 49 moving physics boxes) and every non-UI/non-player scene sprite. The tint pass now applies only where intended: the `OutOfBounds/*` wall particle systems + ArtInstance atmosphere particles. Moving boxes keep vanilla art.

---

## Older than v1.23

### v1.22.0 — Anti-cheat, Admin Tools, Map Colors, Polish
Anti-cheat flagging + auto-invalidation, admin tab with HMAC-signed endpoints and audit log, RD-aware betting odds + cutoff at 2 points in game 1 + one-bet-per-series, cosmetic trail Photon-late-arrival fix + in-shop preview, shop expansion (pronoun/uncommon titles, 4 rare trails, Tride legendary, vanilla and custom map color presets, Tride gradient), chat outside F5 with T key + bot reconnect catch-up + sync dedup, maintenance mode + server-status banner, Immovable/Pacifist pick-phase gate fix, admin username backfill.

### v1.20.0 — Economy, Chat, Betting, Trails
Gold currency, shop tab, 10 titles + 7 trails, betting with Elo odds, WebSocket in-game ↔ Discord chat bridge, pass-rate tracking on cards, data consent modal + Delete-my-data, version gate, auto-update, settings tab.

### v1.18.7 — Leaderboard polish, leave % tracking
Rating history line graph, Recent Ranked Series pagination, leave % tracking full stack, rating history inline snapshots, rating change swap fix, auto-update Thunderstore compatibility.

### v1.18.6
Menu overlay canvas, match found panel split, 3-column leaderboard, Recent Ranked Series panel, form graph, LB-detail achievements, achievement state reset, active-combat gate, API retry, match found sound, taskbar flash, casual W/L + sweep tracking, mod version endpoint, Discord bot rank/stats redesign, card aliases, installer polish.

### v1.18.4 → v1.18.5
(see git log for the granular summary — baseline of the ranked queue, Glicko-2, matchmaking, leaderboard tabs)
