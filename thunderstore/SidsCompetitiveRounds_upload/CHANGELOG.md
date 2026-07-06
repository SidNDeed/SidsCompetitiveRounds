# Sid's Competitive Rounds — Changelog

## v1.29.0 — 2026-07-06 — RELEASED — features + July bug sweep (rolls up the unshipped v1.28.3 client)

> Backend deployed 2026-07-06 (snapshot `cc_cc-v129-pre-migrate__20260706_092540`; migrations 102 + 103 applied). Client released as **v1.29.0** same day after 8 rounds of map-rendering iteration with Sid. `MIN_MOD_VERSION` stays 1.28.2 (no forced update). Bug-comments posted on #28/#29/#36/#37/#38/#39/#40/#41/#42/#43.

**Round 9 (release polish)** — premium twinkle slowed to a 1.6s drift with 1-in-3 glint (was 0.45s / half — read as strobing).

**New features**
- **Online counter (F1)** — queue tab shows "N online" next to the queue count. Client pings `/presence/ping` every 60s from the always-on loop; `/queue/count` also stamps presence and returns `online`. In-memory on the server (no DB writes).
- **Achievements (F2)** — *Regicide* renamed **Sid Slayer** (same key, rows intact). New **Stan Slayer** (beat Stan `76561198983423367` in a ranked series — `SLAYER_TARGETS` map, extensible) and **Grand Master** (2330+ rating, 1v1 or 2v2; granted at every Glicko-update site). Migration backfilled 2 Stan-slayers + granted the slayer TITLES to all achievement holders.
- **Compare tab (F3)** — new metrics: Top Streaks (ranked/casual, grouped bars), 5-0s Given/Taken, Bets Won/Lost, Keys/Sec, Avg Game Length, 2v2 Rating, and an **Achievement Grid** (per-achievement YES/– table per selected player). Server: stats response adds `avg_keys_per_sec`, `avg_game_seconds`, `bets_won/lost`, `bet_gold_net` (refunds excluded), `team_rating`, `rank_name/color`. Client tracks keystrokes (anyKeyDown) + active-combat seconds per match, reported as `local_keys_pressed`/`local_active_seconds` (advisory, not in HMAC).
- **Multi-language support (F4)** — runtime TMP fallback fonts built from installed OS fonts (Segoe UI + CJK families) appended to the game font's fallback table + TMP_Settings. Cyrillic/CJK Steam names and chat now render instead of squares. No ASCII stripping existed anywhere — this was purely a glyph problem.
- **Booster gold (F5)** — Discord boosters get **2000 gold/month**. Bot sweeps `guild.premium_subscribers` every 12h → `/internal/booster-grant`; idempotent per (discord_id, month) via `booster_grants` unique constraint. Unlinked boosters get a one-time DM nudge to `!link`. (Discord doesn't expose per-member boost count — one grant per boosting member.)
- **Custom bet amounts (F6)** — in-game: "..." button on every bet row opens an amount prompt (1–100,000g, Enter to place). Discord: "Custom on X..." buttons open a modal. Server already accepted arbitrary amounts.
- **Rank titles (F7)** — leaderboard rating column is colored by rank tier; player detail shows "Rank: Master V" in the **live Discord role color** (bot pushes all 25 role colors to `rank_role_colors` on start + every 6h; verified 25 pushed on deploy). New free shop title **"Current Rank"** (`title_rank`) renders as your live tier name+color everywhere titles show (leaderboard/chat/stats) and updates automatically on rank change. **Sid Slayer** / **Stan Slayer** titles are achievement-granted, non-purchasable (`rotation_pool='achievement'`).

**Bug fixes**
- **Shield Charge dead after ranked reconnect (#39/#40)** — proven in lopi's log: aborted `ShieldCharge.OnDestroy` leaves its `ShieldChargeCollide` key in ChildRPC's dictionaries → next game `Start()` throws duplicate-key and aborts BEFORE the Block subscription (blocking fine, charge dead). The StartGame scrub now also removes dead-target entries from ChildRPC string→delegate dictionaries. *(client)*
- **Orange pick-body invisible in 1v1 ranked (#29)** — the 2v2 anti-stack X-offset (picker 0 → X=-6) ran in ALL competitive rooms and shoved the 1v1 visualizer body off-camera while the face applied to the un-moved root. Offset now cr_ff-only. *(client)*
- **Jump-to-join stuck (#37)** — spawn guard was correct but unbreakable: stale game scene + no room = suppressed forever. 30s continuous suppression now triggers NetworkRestart → clean menu return with a notice. *(client)*
- **Velvet walls invisible after Shift (#28, second attempt)** — burst re-fire via Clear+Simulate(0)+Play is unreliable; now live particles are recolored **in place** (GetParticles/SetParticles) with zero clearing — nothing can go invisible on any emitter type. *(client)*
- **Map backgrounds grey/blue (B1)** — every map-color SKU now has a hand-picked vivid backdrop hue (same family as the primary, shifted so walls/bg don't blend; mono/charcoal stay neutral). Scene-wide colorFilter lean eased 0.6→0.42 so backdrop hues survive the multiply. *(client)*
- **F5 lag for both players (B2)** — three fixes: cosmetic Photon publishes only fire when the cosmetic set actually changed (was 5 broadcasts to every client per menu open — the opponent-side blip); match-history parse spread across frames (~80 entries/frame instead of 2000 in one hitch); ForceUpdateCanvases only after a fresh page build. *(client)*
- **Series don't resume across sessions (#43)** — undecided mid-BO3s stay the pair's current series for **7 days** and resume at the real score. Stalled series: bets refund at 60 min (unchanged) but the row stays active; abandoned only when the window lapses (`series_expired`). `/series/active` liveness is now activity-based. **LIVE.**
- **Refunded bets showed as losses (#41)** — refunds (payout == stake) are excluded from Recent Ranked Series. **LIVE.**
- **Bets created for ranked-disabled players (#42)** — preflight/match-report no longer force-enable `ranked_enabled`; preflight returns `not_ranked` (no series/ping) and reports downgrade to casual when either player opted out (queue rooms exempt — queueing is consent). Client shows "Casual match" notice. **LIVE** (server), client notice in this build.
- **Bug-report DMs inconsistent (#38) + no Discord bug category (#30)** — root cause: rolling 90s window + in-memory dedup = every bot restart dropped pending DMs (deploys coincide with comment sweeps). Now ack-based at-least-once delivery (`notified_at`/`channel_posted_at` + `/internal/bug-reports/events/ack`). Every bug report now gets its own **thread** in the feed channel with comments/status changes mirrored in. **LIVE.**
- Bets endpoint now enforces the "locked once any game is decided" rule it always displayed. **LIVE.**

**Schema changes** — migration `102_v129_titles_presence_compare.sql`: players.keys_pressed_total/active_seconds_total, matches.local_keys_pressed/local_active_seconds, bug_report_events.notified_at, bug_reports.channel_posted_at (+backfills), tables `rank_role_colors` + `booster_grants`, 3 title shop items, slayer/GM backfills. Migration `103_premium_map_colors.sql`: Gilded/Platinum/Aurora shop items.

**Round 2 (same session, Sid's follow-ups)**
- **Bet cap**: max bet is now **2,000g** on every endpoint (1v1 / 2v2 / Discord) + both custom-amount UIs. **LIVE.**
- **New achievements visible**: the client's hardcoded `AchievementDefs` mirror was never updated — Sid Slayer rename + Stan Slayer + Grand Master now show in the Achievements tab and leaderboard detail. *(client)*
- **Avg Game Length decimals**: bar labels show `5.4m` instead of rounding to whole minutes (Keys/Sec also gets F1). *(client)*
- **"Elo over time"** compare metric: same line graph, x-axis is the real calendar (date gridlines) instead of game index. Snapshot dates now parsed from `recent_rating_history`. *(client)*
- **Leaderboard shows everyone**: server limit cap 200→500, client fetches 500 (was 100 — cut the board at 100/105); existing prev/next pager handles pages. **LIVE** (server) + *(client)*.
- **Maps, the REAL background**: `ArtHandler.m_background` is a dedicated sky GameObject our tints never touched — the vanilla blue backdrop leaked through everything (why "green skins turned blue" after the colorFilter was eased). New sky tint pass colorizes its renderers toward the skin's background color, with vanilla-restore when a default skin is active. Palette redone per Sid: only dusk/obsidian/abyss stay blue; **Forest bg is brown**; Mono/Lavender/Pine/Charcoal backgrounds are same-family-darker than their walls; the rest complement their walls. Velvet + Forest get the Magma-style dark "shadow" mood. *(client)*
- **Premium skins**: **Gilded** (8,000g — molten gold glinting to white-gold), **Platinum** (12,000g — silver glinting to pure white), **Aurora** (10,000g — teal↔violet northern lights). Walls emit random-between two colors per particle (the per-particle shimmer that was a bug for normal skins is the premium effect). Shop items **LIVE**; rendering ships with the client.

**Round 7-8 (bloom to "right above 0" + the green cast's true source)**
- Bloom capped at intensity 1.2 with a NEUTRAL white tint + higher threshold on every skin profile (Sid: effect "right above 0"); wall slabs dimmed to sub-bloom brightness. *(client)*
- **The universal green cast was ours** (learning #119): the round-4 "tint every SolidColor camera" pass was overwriting the SFSS **LightCamera's** clear color — RGBA(1,0,0,0) is the light/shadow buffer's init value, not a backdrop — corrupting the lighting buffer on every skin. Off-screen cameras (targetTexture / Light-named) are now restored and permanently left alone; the stencil-utility quad is likewise excluded from scenery tints. *(client)*

**Round 6 (the log names everything — learning #118)**
- The scene sun-light is `radius=0.5, intensity=10, PURE BLUE` — the round-5 "big light" filter (radius ≥ 20) skipped exactly the light that paints the sky, leaving the master blue source untinted; its blue × per-art backdrops also produced the mystery casts (blue × Gold-art yellow = Sid's green screens). Light detection now keys on intensity/parallax — the last blue source is tinted. *(client)*
- The `OutOfBounds/*` "walls" we've tinted since v1.26 are actually the **players' out-of-bounds warning effects** (7 per player, `playing=False` by design). The old restart code force-played them (that's what the colored border beams ever were) and clearing them was the REAL invisible-walls bug. Pass retired — warnings return to vanilla red; the skin's visible walls are the base art's glow slabs, which now carry the **primary/secondary two-tone**. *(client)*
- Premium sparkle rebuilt as requested: sub-bloom brightness (caps 0.85/0.95 — no more floodlights) + an actual **twinkle loop** (re-rolls which particles glint every 0.45s). *(client)*
- Pine + Forest secondaries switched from rust/bark browns to greens (walls stay green; Forest's brown lives in the background). *(client)*

**Round 5 (SFSS lighting + honesty pass)**
- Round 4's camera fix was a **no-op** — Sid's log shows MainCam clears Depth only, so backgroundColor is ignored. The real background system is **SFSS 2D lighting**: the sky is a backdrop lit by the big SFLight, the shadow beams are `SFRenderer._ambientLight` (tooltip literally suggests "a darker grey, **blue**..."). Now the big light gets a bright version of each skin's background and the ambient a dark version — sky + shadows take the designed hue, walls/geometry keep theirs. Camera + backdrop-quad tints kept as belt-and-suspenders. *(client)*
- **Blinding premiums fixed**: near-white wall colors × 1.6 lift = HDR bloom blowout. All lifted colors now brightness-capped (≤1.15) and the sparkle glint is a subtle Lerp toward the sparkle color, not a white-hot second color. *(client)*
- **Stale deferred tints fixed** (log-proven: burgundy tints landing after shifting to pine): a deferred apply now skips if the current sku changed during its 2s wait. *(client)*
- **Diagnostics** for whatever remains: `[MAPCOLOR-CAMS]`, `[MAPCOLOR-LIGHT]`, `[MAPCOLOR-BG]` (backdrop inventory with vanilla values), `[MAPCOLOR-WALLDIAG]` (names any wall system that is EMPTY right after a tint pass, with emission state) — one test session pinpoints any still-wrong layer. *(client)*

**Round 4 (the actual background, finally)**
- Round 3's strong filter repainted walls along with the sky ("Forest completely not green", walls == background) — because a colorFilter multiplies EVERYTHING. The real backdrop turns out to be **MainCam's clear color**, an editor constant vanilla never changes (which is why backgrounds never changed on Shift and always leaned blue). Now: **camera clear color = the skin's designed background** (instant on Shift, restored on default skins), colorFilter back to near-neutral (0.30 primary lean, mood only) so walls keep their own colors. Learning #116. *(client)*

**Round 3 (Sid's screenshots + game decompile)**
- **The real scene painter found** (learning #114): Sid's screenshots showed the premiums rendering as three different VANILLA arts even though the log proved the custom path ran. Cause: in ROUNDS, the ColorGrading **colorFilter paints the whole scene** (sky, SFSS shadow beams, geometry — all near-neutral art multiplied by it); our 0.42 grey-lerp was too weak to repaint the base art AND was overwriting every per-preset filter with a primary-derived formula. Now the filter is a **strong (0.80) lean toward each skin's designed background color** — sky/shadows/geometry become the skin's family, walls keep their high-lift primary/secondary through the multiply, and the "still 20 blue maps" problem dies at the root. *(client)*
- **Sparkle made visible**: the glint gradient now also drives the **atmosphere particles** (full-brightness two-color) and the sky object's particles — the border walls alone were too thin to read as sparkle. *(client)*
- **"Keys / Game"** compare metric (avg key presses per game, reporter-side per-match average). **LIVE** (server) + *(client)*.

# Changelog

## v1.28.2 — block/empower root-cause fix, two-tone maps, security hardening

- Fixed block dying after game 1 in ranked AND the "infinite empower" carryover — same root cause (a card's between-games teardown leaving a dead handler on your block/gun). The mod now sweeps dead handlers at game start + each block press.
- Map walls are two-tone again (primary + secondary by segment, e.g. Magma red + amber); backgrounds read more strongly as their named color.
- Performance: removed two stale old-game patches; crash-error swallowers no longer destroy pooled/Photon bullets (a likely stutter source).
- Security review: rate limiting + request cap, HMAC-signed the previously-open state endpoints, server-side speedhack flagging, mod-wide bans (matching a banned cheater leaves the match), hardened match-report/disconnect/admin paths.

## v1.28.1 — block fix (ranked), phantom series scores, hover/refresh fix, Discord feed

- Fixed block in ranked/matchmade games: it could activate but absorb nothing (you'd "block" and still take the hit). Caused by the round-start block reset stripping the block's action delegates each round; now it only rebuilds when a trigger was actually destroyed.
- Fixed the per-series HUD game counter showing phantom scores past best-of-3 (e.g. "4-0") for the non-reporting player; it now self-corrects from the BO3 score.
- Fixed the My Stats card-hover tooltip covering the refresh button — its hover zone was the full (mostly empty) row width and is now sized to the actual card text.
- Discord series feed: win streaks no longer capped at 20 (1v1 + 2v2); rating changes show one decimal so sub-1.0 Glicko moves no longer read as "0".
- Raised bug reports per day from 3 to 10.
- Widened matchmaking-disconnect diagnostics to cover 1v1.

## v1.28.0 — round-start freeze fix, map color rework, Compare charts, cursor shapes

- Fixed a freeze where a player could get stuck mid-screen (no move/block/shoot) and end up off-screen the next round.
- Map colors reworked so each map clearly reads as its named color; Shift shows the map-skin name; cycling no longer auto-shuffles to dull skins.
- Compare tab: up to 12 players, charts for every stat (bars + pie charts), Total XP shown as levels, player search.
- Cursor shape selectable in Settings (default / arrow / dot / crosshair / circle); shop Cursor/Effects/Other tabs; body-color unequip fix; bug-report form click-through fix.

Full notes: https://github.com/SidNDeed/SidsCompetitiveRounds/releases

## v1.27.0 — custom map colors, shop expansion, level rewards, 2v2 series rework, performance pass

Full notes: https://github.com/SidNDeed/SidsCompetitiveRounds/releases

(see GitHub releases for the complete, formatted changelog)
