# v1.18.5 Changelog

## Bug Fixes
- **Menu overlay bug** — Opening the competitive menu (F5) on submenus no longer causes menus to overlap when going back. Fixed by removing mainMenuGroup toggling entirely; uses a full-screen raycast-blocking background instead.
- **Scroll and button regression** — Fixed scrolling and Refresh button not working in the competitive menu (caused by overly aggressive raycaster disabling in v1.18.4).
- **Unknown card rarities** — Cards like "Leach", "BombsAway", and "Glasscannon" now correctly resolve to their proper names and rarities. The rarity lookup now registers both the internal card name and the Unity GameObject name with automatic alias mapping.
- **Duplicate card entries** — Card names from log capture are now normalized to canonical names before storage, preventing duplicates like "Leach" vs "Leech".
- **Achievement: Untouchable false positive** — No longer triggers on disconnects or incomplete games. Only evaluates when a player actually reaches the win threshold.
- **Achievement: Silent Assassin** — Now correctly detects both "Sneaky" and "Sneaky Bullets" card names.
- **Achievement: Regicide** — Moved to server-side. Now properly awards when any player beats Sid in a ranked series, regardless of which client reports the match.
- **Achievement: Pacifist** — Card pick clicks (left mouse) between rounds no longer count as "firing a shot". Only tracks during active combat.
- **Achievement: Immovable Object** — Space bar presses during card picks and round transitions no longer count as movement. Only tracks during active combat.
- **Discord /stats command** — Casual W/L no longer double-counts ranked games. Now uses proper server-side casual match tracking.
- **Ranked streaks** — Now count per series completion, not per individual match.

## New Features
- **Match found sound** — A two-tone notification beep plays when a ranked match is found in the queue.
- **Taskbar flash** — ROUNDS' taskbar icon flashes when a ranked match is found while the game is alt-tabbed. Contributed by lopidav.
- **Update check** — The mod checks the server for the latest version on startup. Version number in the bottom-left is now bold with a status indicator showing "✓ up to date" or "⚠ update available".
- **Split /stats and /rank** — `/rank` is now ranked-focused (Elo, peak, series W/L, streaks, sweeps, leaderboard position). `/stats` shows overall and casual stats (total record, casual W/L, level, XP, top cards).
- **Sweep tracking** — Server now tracks 5-0 sweeps given and taken. Shown in both Discord commands.
- **Auto-installer** — Standalone Windows app that detects ROUNDS, installs BepInEx, and downloads the latest mod from GitHub. Includes version comparison and uninstall options.
