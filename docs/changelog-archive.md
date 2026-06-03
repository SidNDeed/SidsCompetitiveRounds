# Sid's Competitive Rounds — Completed-work archive

Prior sessions' "Completed This Session" entries. Newest dated heading on top. See `docs/CHANGELOG.md` for the version-oriented record; this file is organized by when the work was done, not by what version carried it.

---

## 2026-04-28 — 2v2 polish marathon (v1.25.18 → v1.25.23)

- **v1.25.18** Decoupled Random vs Custom-Lobby 2v2 queues (migration 064 `team_queue.queue_type`); F5 Search Random / Find Custom Lobby; queue beacon filtered to auto.
- **v1.25.19** Queue auto-refresh (`MaybeRefreshTeamTab`); `FindMatchingBrace` for `{}` (cards parser bailing); series-preflight gated `!inCrFf`; migration 065 cancelled 3 phantom 1v1 rows; `[POPUP-DIAG]` logging.
- **v1.25.20** `CardPickBodyTinter` coroutine from `CardChoiceVisuals.Show` Postfix.
- **v1.25.21** 2v2 economy (migration 066); matchmaker trusts 2v2 elo when RD≤110; `/team/all-series-paged`; leaderboard columns+sort; FacePublisher republish; toggle-off skin re-bake.
- **v1.25.22** 2v2 tab ScrollView; click-to-sort; Avg Mate Elo; stacked card columns; mid-series rebalance backend (`AUTO_BALANCE_SWAP_MARGIN`, `rebalance_assignments`).
- **v1.25.23** Hotfix: cards 2-per-line + tighter team columns. Ship: backend 1.25.23 + migrations 064/065/066.

## 2026-04-24 — Automated tournaments (v1.24.0)

- Phase 1 sync + Phase 2 async tournaments, double-elim BO3 (migration 050); bracket generator (byes, GF_RESET, prereq W/L role tags); region-pinned auto-connect; deterministic room name; plugin-level heartbeat; penalty % + speculative backfill.
- Discord lifecycle DMs, trophy roles, `/dm-opponent`, `/opp-online`. Bracket click-to-expand UI; timezone/date pickers (culture-invariant); per-match ranked auto-enable; multi-tournament series-lookup fix.
- Polish: round-won animation stall fix (deferred tint 2s); locale unicode strip; `<b>` bold-wrap; AFK flag requires cards_picked==0; ready-up 30s→90s. Hotfix: `/matches` AttributeError (26 min of 500s). Ship: v1.24.0 + Thunderstore zip.

> Sessions between 2026-04-28 and 2026-06-03 (v1.26.x, v1.27.0) were not formally handed off — see git history + `docs/CHANGELOG.md`.

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
