# v1.18.6 Changelog

## Bug Fixes
- **Achievement state persisting across matches** — Achievement tracking flags (moved, fired, took damage, etc.) now reset at the start of each match, not just when leaving a room. Previously, moving in game 1 would prevent the Immovable Object achievement from triggering in game 2 of the same session. (Thanks lopidav!)
- **Achievements completely broken (500 errors)** — The `player_achievements` database table had INTEGER columns but `players.id` is UUID, causing every achievement unlock to fail silently. Table recreated with correct UUID types. No achievements were functional prior to this fix.
- **Regicide server-side field name** — Fixed `achievement_id` → `achievement_key` in the server-side regicide auto-grant.
- **Menu overlay showing game UI through it** — The competitive menu now always renders on its own overlay canvas instead of parenting to ROUNDS' canvas. Fixes character faces and other game UI bleeding through.
- **Match found panel text clipping** — Split from one cramped row into two: match info on top, Ready/Decline buttons below.
- **Font characters rendering as squares** — Replaced unicode characters (stars, checkmark, bullet) with ASCII alternatives compatible with ROUNDS' font.

## New Features
- **API retry logic** — Ready-up, match reporting, and achievement unlocks now retry up to 3 times with a 2-second delay on network failure. Prevents DNS hiccups from losing match data or breaking queue flow.
- **Update button** — Orange "Update" button appears in the bottom bar when a new version is available, links to GitHub releases.
- **GitHub button** — Added next to Discord button in the bottom bar.
- **Retroactive achievement grants** — Historical match data scanned to award card-based sweep achievements, Stacked Deck, and Regicide to players who earned them before achievements were functional.
- **Installer improvements** — Uninstall options (mod only or everything), version comparison on status screen, subfolder detection for existing installs.
