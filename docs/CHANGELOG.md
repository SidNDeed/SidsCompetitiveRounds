# Sid's Competitive Rounds — v1.18.7 Changelog

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
- **In-game**: Leave percentage shown in the leaderboard player detail panel below the Ranked W/L line
- **Discord**: Leave rate shown in `/rank` and `/stats` commands (only when > 0)
- Color-coded: green (<5%), yellow (5–15%), red (>15%)
- Denominator includes both completed series AND disconnect events, so a DC that prevents a series from completing still counts properly (e.g., 1 DC with 0 completed series = 1/1 = 100%)

### Database
- New migration `012_leave_tracking.sql` adds `ranked_dc_count` column to `players` table

## Auto-Update Thunderstore Support
- Improved DLL path detection for the auto-update system
- Now uses `BepInEx.Paths.PluginPath` as a fallback when `Assembly.Location` fails, which correctly resolves the plugin directory for both vanilla installs and Thunderstore/r2modman profile installs
- Searches all subdirectories under the BepInEx plugins path (handles folder naming differences like `CompetitiveRounds/` vs `SidNDeed-CompetitiveRounds/`)
- Vanilla hardcoded path kept as a last resort fallback

---

## Files Changed

### Client (C#)
| File | Changes |
|------|---------|
| `Plugin.cs` | Version bump 1.18.6 → 1.18.7 |
| `NativeUI.cs` | Line graph, column centering, series pagination, leave % display |
| `GameStateWatcher.cs` | Opponent DC detection via PlayerList monitoring |
| `ApiClient.cs` | `ReportDisconnect()` method, `ranked_dc_count` field, Thunderstore-aware update path |

### Server (Python)
| File | Changes |
|------|---------|
| `main.py` | Rating history snapshots on series completion, `recent_form` → series-based, disconnect endpoint, `ranked_dc_count` in stats, version bump |
| `models.py` | `ranked_dc_count` column on Player model |
| `schemas.py` | `ranked_dc_count` field in PlayerStatsResponse |
| `discord_bot.py` | Leave rate in `/rank` and `/stats` embeds |

### SQL
| File | Changes |
|------|---------|
| `012_leave_tracking.sql` | Adds `ranked_dc_count INTEGER DEFAULT 0` to `players` table |
