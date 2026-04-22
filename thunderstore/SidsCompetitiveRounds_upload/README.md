# Sid's Competitive Rounds

A ranked competitive mod for **vanilla ROUNDS v1.1.2 ONLY** by Landfall. Built for the Competitive Rounds Discord community (~1,100 members).

> **⚠️ IMPORTANT: Designed exclusively for vanilla ROUNDS v1.1.2 (the "Default Public Version" on Steam). NOT compatible with older versions, beta branches, or any other mods. The mod will automatically disable itself if it detects an incompatible game version or another BepInEx plugin.**

## Features

- **Glicko-2 ranked series** — skill-based matchmaking with RD-aware odds, BO3 series, Elo + rating history tracked server-side.
- **Matchmaking queue** — Elo-tiered search with mutual ready-up and optional ranked-only toggle.
- **In-game leaderboard** — sortable, with player detail panel, rating history line graph, series-based recent form, head-to-head, and achievements.
- **Match history + card stats** — BO3 series grouping, opponent cards, pass rates, filterable by Ranked / Casual / All.
- **Gold economy + shop** — earn gold from matches and achievements, spend on titles, Photon-synced cosmetic trails, map color presets, and stackable name styling (bold/italic/color/size/font-style/glow).
- **Betting** — wager gold on live ranked series with Glicko-expectancy odds; locks at 2 points scored in game 1.
- **In-game ↔ Discord chat bridge** — press **T** anywhere in-game to chat, messages round-trip through the Competitive Rounds Discord with ratings and titles attached.
- **11 achievements** (100g each) with retroactive grants on version bumps.
- **Anti-cheat** — sub-60s match-pattern auto-flagging, too-many-cards detection, HMAC-signed match reports, and an admin tab for ban / flag review / series reversal.
- **Auto-update notifications** — the Thunderstore build shows an in-game prompt when a new version is available (use r2modman or the Thunderstore Mod Manager to apply the update).
- **Maintenance-mode awareness** — server restarts surface as a graceful banner, not a disconnect.
- **Privacy-first** — first-launch consent prompt, revoke any time, full Delete-my-data path in Settings.

## Compatibility

- **Required**: ROUNDS v1.1.2 (Steam "Default Public Version")
- **Required**: BepInEx 5.4.22 (declared as a Thunderstore dependency — auto-installed)
- **NOT compatible** with any other BepInEx mods. The mod must be the only plugin installed.
- **NOT compatible** with older ROUNDS versions or Steam beta branches.

## Installation

There are two supported ways to install. Pick one — don't combine them on the same ROUNDS install.

### Thunderstore (this page — recommended if you already use r2modman)

1. Open **r2modman** or the **Thunderstore Mod Manager** and choose the ROUNDS profile.
2. Find **Sid's Competitive Rounds** in the Online tab and click **Download** — BepInEx is pulled in automatically as a dependency.
3. Click **Start modded** to launch ROUNDS through the mod manager. That's it.
4. When a new version is released, the in-game banner flags it — apply it from r2modman's Update tab.

### Auto-installer (Windows .exe from Discord)

1. Join the [Competitive Rounds Discord](https://discord.gg/4tsWadH6tc) and grab `CompetitiveRoundsInstaller.exe` from the pinned install link.
2. Run it — the installer auto-detects your ROUNDS install, installs BepInEx if needed, and drops the mod into `ROUNDS\BepInEx\plugins\CompetitiveRounds\`.
3. Launch ROUNDS. New mod versions are auto-downloaded and applied on next launch — no r2modman required for updates on this path.

Both paths produce the same gameplay; the only functional difference is that the direct-Discord build self-applies mod updates while the Thunderstore build defers to the mod manager (Thunderstore's distribution rules don't allow the self-updater's helper script).

## Getting started

1. Launch ROUNDS — the mod loads automatically.
2. Accept the first-launch data-consent prompt (or Decline to play fully offline).
3. Click **SID'S COMPETITIVE ROUNDS** on the main menu.
4. Enable **Ranked** to start tracking your matches.
5. Use **Search Ranked** to find an opponent at your Elo.
6. Open the Discord for community, matchmaking, and chat: https://discord.gg/4tsWadH6tc

## Controls

- **F5** — Toggle the competitive overlay
- **T** — Open the chat input (works both in-menu and in-game)
- **ESC** — Close the competitive overlay

## Links

- **Discord**: https://discord.gg/4tsWadH6tc
- **GitHub**: https://github.com/SidNDeed/SidsCompetitiveRounds
