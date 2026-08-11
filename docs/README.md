# Sid's Competitive Rounds

A ranked competitive mod for **vanilla ROUNDS v1.1.2 ONLY** by Landfall. Built for the Competitive Rounds Discord community (~2,500 members).

> **⚠️ IMPORTANT: This mod is designed exclusively for vanilla ROUNDS v1.1.2 (the "Default Public Version" on Steam). It is NOT compatible with older versions, beta branches, or other mods. The mod will automatically disable itself if it detects an incompatible game version or other BepInEx plugins installed.**

## Features

### Four game modes — three ranked ladders
- **Glicko-2 rating system** with RD-aware matchmaking; **best-of-3 ranked series** in 1v1 (Elo applies on series completion)
- **2v2 ranked** — own Glicko ladder and leaderboard; queue solo into rating-balanced teams or open a **custom lobby** and pick teams with 3 friends
- **Free-For-All (3-10 players), ranked** — last player standing scores, first to 5 points wins; simultaneous card picks, live per-player scoreboard with the leader crowned, rolling 5-card deck cap, maps that scale up with lobby size, and leaver-tolerant matches (survivors play on). Own FFA rating and leaderboard
- **1v2 (unranked beta)** — one solo versus a duo, with separate Solo and Duo activity boards and an optional extra starting pick for the solo
- **25 rank tiers** — Beginner I through Grand Master V, mirrored as auto-updating Discord roles
- **Matchmaking queues** — Elo-tiered matching with mutual ready-up in 1v1/2v2; consent-based instant queues in 1v2/FFA; 30-minute search cap everywhere
- **In-game leaderboards** with player detail panel, rating-history graph (rank-tier reference lines), series-based recent form, head-to-head records, and achievements — plus a **Compare** view charting up to 12 players side by side
- **Match history** grouped by series, with card picks, opponent cards, per-game Hit% / Block%, XP, and gold earned
- **Card stats** with pick counts, win rates, and pass rates, filterable by Ranked / Casual / All
- **Tournaments** — weekly same-time brackets with auto-connected matches, plus long-running async tournaments, run through Discord
- **Tier List Maker** — assign every card an S/A/B/C/D/E/F tier with click-to-cycle, three independent lists (Casual / Ranked / All) persisted server-side. Click any card to pop a full-color art preview. Export the whole tier list as a near-square PNG: the real ROUNDS card art for every card + your live `## played` / `##% won` underneath, color-coded by win band (≥55% green / ≤45% red). Output lands in `<ROUNDS>/CompetitiveRoundsTierLists/tierlist-<filter>-<timestamp>.png`.

### Spectator mode
- **Watch a live ranked match** — **WATCH** buttons appear on Live Ranked Games in the Leaderboard tab and on the 2v2, 1v2, and FFA live panels. You join with no character, no team, and no effect on the people playing
- **Four spectator seats per game**; you can't watch a match you're in, and players can turn spectating off for their own games
- **Joins at a clean boundary** — you land on a "Synchronizing" screen and start watching at the next battle (at most one point away), with both players' decks and health rebuilt exactly, rather than dropping into a half-played round showing the wrong state
- **Full match view** — the arena, both bodies with their faces/colors/trails/effects, the crown, live card picks, plus a top bar with names, titles, ratings, series score and game score. Hold **Tab** for the scoreboard
- **Players see who's watching** — a *Spectators (N)* line, so nobody is observed silently

### Languages
- **Five languages: English, Spanish, Russian, Ukrainian, Swedish** — the entire mod UI (1,700+ strings), chosen on first launch or from Settings
- **Ukrainian and Swedish also translate the BASE GAME** — ROUNDS ships neither language, so the mod supplies its own: vanilla menus, prompts, and all card names and descriptions render translated alongside the mod's own UI
- **Community-moderated** — appointed translators propose and review corrections through a web portal, and approved fixes reach players without waiting for a mod update
- **Per-language chat channels** bridged to matching Discord rooms, plus release notes published in every language

### Economy & cosmetics
- **Gold currency** — earn from matches, series wins, sweeps, and achievements; ranked rewards scale with your opponent's rank tier
- **Shop** with titles, cosmetic trails, map color skins (premium animated ones included), body colors, cursor colors, player aura effects, and name styling
- **Community character cosmetics** — artist-made faces and accessories (including animated ones) that render for everyone; artists submit, price, and manage their art entirely in-game
- **Cosmetic trails** — Photon-synced so other modded players see your trail during matches, plus a local in-shop preview
- **Map color presets** — ~30 variants including vanilla art swaps and custom-designed two-tone presets (Forest, Rose, Amethyst, Mint, Sunset, …)
- **Name styling** — stackable Bold / Italic / Underline / Strike plus single-active colors, sizes, font-style transforms, and a real SDF glow (modded-only; non-modded players see an unstyled name)
- **Titles** visible on the leaderboard, chat messages (in-game + Discord), and match history rows

### Betting
- **Wager gold on live ranked series** with RD-aware odds via Glicko expectancy
- Betting locks once game 1 is underway; abandoned series auto-refund
- One bet per series, can't bet on your own matches, payouts settle automatically

### Chat & Discord integration
- **In-game ↔ Discord chat bridge** over WebSocket — press **T** anywhere (not just the F5 menu) to chat
- Scrollback of the last 50 messages persisted server-side
- Ratings and titles attach to every message so you can verify who you're talking to
- On-screen chat overlay (toggleable) so you don't have to open F5 to see new messages
- **Discord linking** auto-assigns rank roles, posts series results to a log channel

### Anti-cheat & admin
- **Sub-60s match-pattern detection** auto-flags and retroactively invalidates suspicious streaks (XP + gold reversed, series marked invalid)
- **Macro detection, too-many-cards, inactive-reporter heuristics** — flagged to a private admin channel for review
- **In-game admin tab** (whitelisted Steam IDs only) for banning, achievement grants, series reversal, and flag triage — every action audit-logged
- **HMAC-signed** match reports and admin endpoints prevent spoofing

### Quality of life
- **50 achievements** (100-1000g by difficulty, several unlock exclusive titles) — card-build challenges, marathon streaks, rating milestones, and FFA feats — with retroactive grants from your existing match history
- **XP & leveling** with bonus XP for wins, sweeps, and ranked play, scaled by your opponent's rank tier
- **Hold Tab: live match scoreboard** — every player's current build, stats, and card list at a glance mid-game
- **Auto-update** — newer mod versions are downloaded and applied automatically on next launch (Thunderstore builds defer to the mod manager)
- **Maintenance-mode banner** and reconnect indicator so short server restarts feel graceful
- **FPS + ping + region** overlay, taskbar-flash + match-found sound for alt-tabbed players
- **First-launch consent modal** with Revoke / Delete-my-data controls (GDPR-style)

## Compatibility

- **Required**: ROUNDS v1.1.2 (Steam "Default Public Version")
- **Required**: BepInEx 5.4.1901 (installed automatically by either installer path)
- **NOT compatible** with any other BepInEx mods — this mod must be the only plugin installed
- **NOT compatible** with older ROUNDS versions or Steam beta branches

## Installation

Pick one of the two methods below — don't use both at the same time.

### Method 1 — Auto-installer (recommended, Windows)

1. Join the [Competitive Rounds Discord](https://discord.gg/4tsWadH6tc) and grab the latest `CompetitiveRoundsInstaller.exe` from the pinned install link.
2. Run the installer. It auto-detects your ROUNDS install (Steam default), installs BepInEx if needed, and places the mod under `ROUNDS\BepInEx\plugins\CompetitiveRounds\`.
3. Launch ROUNDS. If a newer version is available, the mod auto-downloads and applies it on next launch — no manual updates required.

### Method 2 — Thunderstore / r2modman

1. Install [r2modman](https://thunderstore.io/package/ebkr/r2modman/) or the Thunderstore Mod Manager.
2. Choose the ROUNDS game profile.
3. Search for **Sid's Competitive Rounds** and install. The Thunderstore-flavoured build auto-installs BepInEx as a dependency and shows in-game update notifications (it doesn't self-apply updates — use r2modman's update flow instead).
4. Launch via the mod manager's "Start modded" button.

## Getting started

1. Launch ROUNDS — the mod loads automatically.
2. Accept the first-launch data-consent prompt (or Decline to play fully offline).
3. Click **SID'S COMPETITIVE ROUNDS** on the main menu.
4. Enable **Ranked** to start tracking your matches.
5. Use **Search Ranked** in the queue tab to find opponents at your Elo.
6. Open the Discord for community and matchmaking: https://discord.gg/4tsWadH6tc

## Controls

- **F5** — Toggle the competitive overlay (in-game)
- **T** — Open the chat input (in-game; also works inside the F5 menu)
- **ESC** — Close the competitive overlay

## Links

- **Discord**: https://discord.gg/4tsWadH6tc
- **GitHub**: https://github.com/SidNDeed/SidsCompetitiveRounds
- **Thunderstore**: https://thunderstore.io/c/rounds/p/SidNDeed/SidsCompetitiveRounds/
