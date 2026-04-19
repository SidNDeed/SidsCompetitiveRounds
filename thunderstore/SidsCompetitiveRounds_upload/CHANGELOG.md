# Sid's Competitive Rounds — Changelog

## v1.22.0 — Anti-cheat, Admin Tools, Map Colors, Polish

Mandatory update. The server rejects any client below v1.22.0 with a 426 response.

### Anti-cheat
- Sub-60s game-pattern detection: 2+ ranked / 3+ casual sub-60s games between same pair within 2hrs → invalidate retroactively (XP + gold reversed).
- >5 cards per player per game → instant flag + invalidation.
- Inactive-reporter heuristic flag for manual review.
- Stale series cleanup: 30min no-match-reported → marked abandoned, pending bets refunded.
- All flags posted to a private `#scr-admin` Discord channel.

### Admin tools
- New Admin tab in F5 menu, visible only to whitelisted Steam IDs.
- Lists flagged matches + ban list with action buttons.
- Ban/Unban/Grant Achievement/Reverse Series via IMGUI prompt.
- HMAC-signed admin endpoints. Full audit log (`admin_actions`).
- Bans block queue, chat (in-game + Discord-relay), and betting.

### Betting
- Live series appear at matchmaking (was: only after game 1).
- Bet cutoff at 2 points scored in game 1.
- RD-aware Glicko odds — fresh experts can't be exploited; cap drops 3.0× → 1.0× as RD rises.
- One bet per series enforced; client hides wager buttons after.
- Live Ranked Games panel: bigger text, wider, auto-refresh every 10s, pagination at 5/page.
- "You bet Ng" displayed inline after wager.

### Recent Ranked Series
- 100 most-recent series, paginated 20 per page.
- Both players' ELO shown inline.
- Settled bets shown as indented sub-rows: `↳ AsteRiA bet 500g on Sid → +505g`.

### Cosmetic trails
- Photon late-arrival fix — opponent's trail appears in game 1 now (was failing).
- Trail preview button in shop. Local-only uGUI cursor trail at sortingOrder 30001 (above F5 menu).
- Multi-stop gradients on legendary trails (Phoenix, Void).
- Particle sparkles on Phoenix / Void / Prism / Tride.
- **Tride trail** (5000g legendary) — trans pride flag colors, alternating cyan + pink bands.

### Shop expansion
- New titles: She/her, They/them, He/him (100g common); Idiot, Grandma, Decent (1000g uncommon).
- New 4k rare trails: Colossus, Ascendant, Sovereign, Titan.
- New 5k legendary trail: Tride.
- Vanilla map color locks (75g): Sweden, Sky, Poison, Gold, Soviet, Rainbow.
- **Custom map colors** (75g–100g, 14 presets): Soft Slate, Moss, Cream, Lavender, Dusk, Sand, Monochrome, Forest, Amethyst, Charcoal, Crimson, Slate, Rose, Mint, Sunset. Tints physical map blocks + wall particles + active art backdrop with a complementary secondary color for multi-tone variation.

### Chat
- T chat works outside the F5 menu (gated on combat / other-input focus).
- Bot reconnect catch-up + 30s periodic poll backfills any missed broadcasts.
- Synchronous message-id dedup so live + catch-up paths can't double-post.
- Long paste chat scroll-lock fix.

### Achievements
- Per-trophy gold reward bumped 25g → 100g.
- "+100g" tag shown next to each unlocked achievement's date.
- Immovable Object & Pacifist input gate now respects ROUNDS' pick-phase log markers.

### Server reliability
- Maintenance mode endpoint with clean 503 + Retry-After:30 (no connection-refused during deploys).
- F5 server-status banner: shows when API actually appears down (not during quiet periods).

### Polish
- Match history rows show opponent's current title: `vs Sid [Kingslayer]`.
- Bet button silent-drop fix (was double-ClickGuarded).
- Click-through-blocked consent modal.
- F5 menu Gun.Attack / Block.TryBlock prefixes — clicking menu buttons no longer fires your gun.
- Discord username backfill (no more raw IDs).

### Schema migrations
`027_anticheat` · `028_admin` · `029_shop_expansion` · `030_live_points_and_colors` · `031_fix_mapcolors` · `032_custom_mapcolors` · `033_more_mapcolors`

---

## v1.20.0 — Economy, Chat, Betting, Trails

Mandatory update. The server rejects any client below v1.20.0 with a 426 response, and the mod auto-prompts the update on launch.

### Economy / Shop
- **Gold currency**. 100 XP = 1 gold. +25 gold per achievement. +5 gold on a ranked series win, +1 more on a 2-0 sweep.
- **Shop tab** with titles and trails (separated into labelled sections, sorted cheapest-first per tier).
- **Titles** (10): Beginner, Regular, Active, Clown, Sweaty, Tryhard, Competitor, Kingslayer, Grandmaster, Royal.
- **Cosmetic trails** (7): Clean Trail, Crimson Streak, Azure Comet, Emerald Glow, Phoenix Flame, Void Ripple, Prismatic Wake.
  - Trail **length scales with price tier** (3k short / 5k medium / 10k long).
  - Prismatic trail cycles through the full color spectrum in real time.
  - **Photon-synced** — other mod users see your trail behind your player during matches.
  - Toggleable in Settings → Display → Cosmetic trails.
- **Active title** renders in leaderboard rows (bold, colored), chat messages (both in-game and Discord), and the My Stats Discord Link row.
- **Gold column on the leaderboard** (sortable). My Stats shows gold balance inline with W/L.
- **Gold breakdown** in the after-match notification: `+9 gold [XP +3, Series win +5, Sweep +1]`. Match history rows show `+N xp +N g`.

### Betting
- **Live Ranked Games** panel on the Leaderboard tab shows in-progress series with current score and both players' Elo-based odds.
- Bet preset stakes (100g / 500g / 2000g) on either player. Odds = `1 / P(win)`, capped at **3x** so the largest payout is 3× stake.
- **Can't bet on your own match**. Bets settle the instant the series completes; winners credit gold automatically.

### In-game ↔ Discord chat bridge
- **WebSocket endpoint** `/api/v1/ws/chat` with 25-second keepalive pings and a serialized sender.
- **Two-way bridge** via a Discord bot subscribed to `#scr-discussion`. In-game messages appear as `**Name [Title] (1946)** (in-game): ...` in Discord.
- **Chat panel** in My Stats (under Discord Link). Press **T** while the F5 menu is open to type and send; Enter sends, Esc cancels.
- **In-game chat overlay** (bottom-left, auto-fade after 35s). Toggle in Settings.
- **Scrollback** — last 50 messages persisted server-side and loaded on connect.
- **Rating + title** attached to every message. Works across both bridge directions.

### Privacy & data consent
- **First-launch consent modal** explaining exactly what gets collected. Explicit Allow or Decline required.
- **Revoke consent** in Settings → full offline mode. Ranked mode turns off, chat disconnects, no API traffic.
- **Delete my data** — anonymizes your row. Matches stay so other players' ratings and histories aren't retroactively disturbed.
- **Deletion is irreversible** — server-salted hash blocklist prevents account-wipe-to-reset-rating spoofing.
- **Version gate**: `X-Mod-Version` header. Clients below `MIN_MOD_VERSION` get 426 and are prompted to update.

### Pass-tracking
- The mod captures every card **offered** during pick phase (not just the one picked).
- **Pass%** column in the Card Stats tab, sortable.

### Achievement & gameplay fixes
- **Immovable Object & Pacifist** gate rewritten. New `inPickPhase` flag driven by ROUNDS log markers — achievements fire only during actual combat now.
- Retroactive grants for Stan and Noah.

### Auto-update
- Mod auto-fires the update handler on launch when it detects a newer `LATEST_MOD_VERSION` from the server.
- Thunderstore build shows a notification to update via your mod manager (no `.bat` apply-on-exit script).

### UI polish
- **Settings tab** with Data Consent, Revoke, Delete My Data, and display toggles (FPS, Region/Ping, chat overlay, cosmetic trails).
- **Click-to-reveal** on the Discord link row so streamers don't accidentally doxx themselves.
- **F5 menu auto-closes** when combat starts so it can't block clicks during play.
- F5 chat log now word-wraps.
- Leaderboard title rendered bold + in the title's color next to the name.
- Cosmetic trails can be toggled off mid-match without relaunching; toggling back on re-attaches.

### Server fixes
- **Card-stats materialized view unique index** fixed (REFRESH CONCURRENTLY previously failed on dupes).
- **Poison / Poison Bullets** + **Pristine Perseverence** deduped in stream + backfilled rows.
- **Discord username backfill** — in-game display shows `@username` instead of numeric ID.
- **Rating-change swap fix** — `p1_rating_change` / `p2_rating_change` now map correctly to the series player order.

---

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
