# Sid's Competitive Rounds

A ranked competitive mod for **vanilla ROUNDS v1.1.2 ONLY** by Landfall. Built for the Competitive Rounds Discord community (~2,500 members).

> **⚠️ IMPORTANT: Designed exclusively for vanilla ROUNDS v1.1.2 (the "Default Public Version" on Steam). NOT compatible with older versions, beta branches, or any other mods. The mod will automatically disable itself if it detects an incompatible game version or another BepInEx plugin.**

## Features

- **Glicko-2 ranked series** — skill-based matchmaking with RD-aware odds, BO3 series, Elo + rating history tracked server-side.
- **NEW: Free-For-All (3-10 players), ranked** — everyone for themselves: last player standing takes the half point, first to 5 points wins. Simultaneous card picks (no 10-player pick queue), a live per-player scoreboard with the leader crowned, a rolling 5-card deck cap, and maps that scale up with lobby size. Leavers don't end the match — survivors play on. Its own FFA rating, leaderboard, and recent-games panel.
- **2v2 ranked** — its own Glicko ladder and leaderboard: queue solo into rating-balanced random teams, or open a **custom lobby** and pick teams with 3 friends. Per-player gold/XP payouts and a crown for *both* members of the leading team.
- **1v2 (unranked beta)** — one solo versus a duo, with separate Solo and Duo activity boards and an optional extra starting pick for the solo.
- **25 rank tiers** — Beginner I through Grand Master V, mirrored as Discord roles that update automatically as your rating moves.
- **Tournaments** — a weekly same-time bracket that auto-connects your matches when both players are ready, plus long-running async tournaments with a week per round. Sign-ups, reminders, and results run through Discord.
- **Community character cosmetics** — artist-made **faces and accessories** (including **animated** ones) that equip in ROUNDS' own character editor and render for everyone: in matches, card picks, and menus. Community artists control their own creations — price, limited stock, gifting, even blocking buyers — and submit new art for review **entirely in-game** (512×512 transparent PNG, drop it in a folder and hit Upload).
- **Hold Tab: live match scoreboard** — every player's current build at a glance mid-game: damage, attack/reload speed, ammo, bullet stats, block cooldown, lifesteal, movement, and full card lists.
- **Matchmaking queues** — Elo-tiered search with mutual ready-up in 1v1/2v2, consent-based instant queues in 1v2/FFA, a 30-minute search cap everywhere, and an optional ranked-only toggle.
- **In-game leaderboard** — sortable, with player detail panel, rating history line graph, head-to-head series history, and achievements — plus a **Compare** view that charts up to 12 players side by side (ratings, accuracy, playtime, achievement grid, and more).
- **Match history + card stats** — BO3 series grouping, opponent cards, pass rates, per-game Hit% / Block% / keys-per-second for both players, game length, and a scoring-timeline graph on hover.
- **Tier List Maker** — assign every card an S/A/B/C/D/E/F tier with click-to-cycle. Three independent lists (Casual / Ranked / All) persisted server-side. Click any card to preview the full-color art. Export the whole list as a near-square PNG with real ROUNDS card art + your live `## played` / `##% won` underneath each card. PNG lands in `<ROUNDS>/CompetitiveRoundsTierLists/`.
- **Gold economy + shop** — earn gold from matches and achievements; spend it on titles, Photon-synced trails, map color skins (premium animated ones included), body colors, cursor colors, player aura effects, and stackable name styling (bold/italic/color/size/font-style/glow).
- **Betting** — wager gold on live ranked series with Glicko-expectancy odds, in-game or from Discord, with custom stake amounts. Locks once game 1 is underway; abandoned series auto-refund.
- **In-game ↔ Discord chat bridge** — press **T** anywhere in-game to chat, messages round-trip through the Competitive Rounds Discord with ratings and titles attached.
- **41 achievements** (100-1000g by difficulty, several unlock exclusive titles) — from card-build challenges (5-0 with Barrage, two Glass Cannons...) to marathon streaks (100+ casual wins in a row), with retroactive grants from your existing match history.
- **Anti-cheat** — sub-60s match-pattern auto-flagging, too-many-cards detection, HMAC-signed match reports, macro detection, and an admin tab for ban / flag review / series reversal.
- **Auto-update notifications** — the Thunderstore build shows an in-game prompt when a new version is available (use r2modman or the Thunderstore Mod Manager to apply the update).
- **Maintenance-mode awareness** — server restarts surface as a graceful banner, not a disconnect.
- **Privacy-first** — first-launch consent prompt, revoke any time, full Delete-my-data path in Settings.

## Compatibility

- **Required**: ROUNDS v1.1.2 (Steam "Default Public Version")
- **Required**: BepInExPack ROUNDS 5.4.1901 (declared as a Thunderstore dependency — auto-installed; this is the only BepInEx pack distributed for ROUNDS)
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
