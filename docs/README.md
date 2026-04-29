# Sid's Competitive Rounds

A ranked competitive mod for **vanilla ROUNDS v1.1.2 ONLY** by Landfall. Built for the Competitive Rounds Discord community (~2,500 members).

> **⚠️ IMPORTANT: This mod is designed exclusively for vanilla ROUNDS v1.1.2 (the "Default Public Version" on Steam). It is NOT compatible with older versions, beta branches, or other mods. The mod will automatically disable itself if it detects an incompatible game version or other BepInEx plugins installed.**

## Features

### Ranked play
- **Glicko-2 rating system** with RD-aware matchmaking
- **Best-of-3 ranked series** — Elo changes apply on series completion
- **Ranked matchmaking queue** with Elo-tiered matching, mutual ready-up, and ranked-only toggle
- **In-game leaderboard** with player detail panel, rating history line graph, series-based recent form, head-to-head records, and achievements
- **Match history** grouped by BO3 series, with card picks, opponent cards, XP, and gold earned
- **Card stats** with pick counts, win rates, and pass rates, filterable by Ranked / Casual / All

### Economy & cosmetics
- **Gold currency** — earn from matches, ranked wins, sweeps, and achievements (100g each)
- **Shop** with titles, cosmetic trails, map color presets, and name styling
- **Cosmetic trails** — Photon-synced so other modded players see your trail during matches, plus a local in-shop preview
- **Map color presets** — ~30 variants including vanilla art swaps and 15+ custom ColorGrading + per-particle tinted presets (Forest, Rose, Amethyst, Mint, Sunset, …)
- **Name styling** — stackable Bold / Italic / Underline / Strike plus single-active colors, sizes, font-style transforms, and a real SDF glow (glow is modded-only; non-modded players see an unstyled name with no visual artifacts)
- **Titles** visible on the leaderboard, chat messages (in-game + Discord), and match history rows

### Betting
- **Wager gold on live ranked series** with RD-aware odds via Glicko expectancy
- Betting locks at **2 points scored in game 1** (preserves pre-series mystery) or once any game finishes
- One bet per series, can't bet on your own matches, payouts settle automatically

### Chat & Discord integration
- **In-game ↔ Discord chat bridge** over WebSocket — press **T** anywhere (not just the F5 menu) to chat
- Scrollback of the last 50 messages persisted server-side
- Ratings and titles attach to every message so you can verify who you're talking to
- On-screen chat overlay (toggleable) so you don't have to open F5 to see new messages
- **Discord linking** auto-assigns rank roles, posts series results to a log channel

### Anti-cheat & admin
- **Sub-60s match-pattern detection** auto-flags and retroactively invalidates suspicious streaks (XP + gold reversed, series marked invalid)
- **Too-many-cards, inactive-reporter heuristics** — flagged to a private admin channel for review
- **In-game admin tab** (whitelisted Steam IDs only) for banning, achievement grants, series reversal, and flag triage — every action audit-logged
- **HMAC-signed** match reports and admin endpoints prevent spoofing

### Quality of life
- **11 achievements** — Untouchable, Silent Assassin, Total Mayhem, Fragile Perfection, No Escape, Rise from the Ashes, The Comeback Kid, Stacked Deck, Regicide, Pacifist, Immovable Object (each grants 100g)
- **XP & leveling** with bonus XP for wins, sweeps, ranked play, and top-5 finishes
- **Auto-update** — newer mod versions are downloaded and applied automatically on next launch
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
