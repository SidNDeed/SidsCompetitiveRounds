# Client performance audit

This is a source-level audit of mod-owned work during a match. Impact labels are
relative estimates, not invented FPS numbers. Exact deltas require a controlled
same-map, same-build capture on representative machines.

## Bottom line

Turning map lighting and shadows back on is the strongest explanation for a
sustained FPS decrease. Those switches restore the game's full SFSS lighting
pass and shadow render pass. The mod also had several smaller continuous costs:
debug log construction in combat hooks, repeated cosmetic renderer writes,
per-Repaint overlay allocations, live particle effects when animations were
disabled, and an expensive hold-Tab display.

The accompanying changes remove or reduce those mod-owned costs:

- ordinary hit/block diagnostics now run only when Block Debug is enabled;
- static cosmetic frames and colors are written once instead of every tick;
- animated player effects pause when Animated Cosmetics is off;
- chat reuses caller-owned storage instead of allocating an array per Repaint;
- FPS/ping and match-status strings refresh at low frequency;
- the hold-Tab table snapshots stats at 8 Hz instead of rebuilding them every
  rendered frame;
- the menu-update performance patch records one state transition instead of
  updating telemetry dictionaries on every skipped frame.

## Match stat trackers

| Tracker | Duty cycle | Expected impact |
|---|---|---|
| FPS, freeze, input/KPS and macro sampling | Every tracked frame; roughly 11 input-edge checks | Low, persistent |
| Match, score and round state | 10 Hz; reflected score fields and player state | Low to medium |
| Achievement health/death state | 10 Hz; local-player scan | Low |
| Card fallback polling | 10 Hz until event tracking takes over; may split strings | Low |
| Peer FPS/combat/latency exchange | Every 3 seconds; serialization and peer parsing | Low average, possible brief pulse |
| Bullet fired/hit counters | Event-driven | Negligible |
| Damage and block counters | Event-driven | Low |
| Block Debug | Event logs plus overlay while enabled | Medium to high on busy builds; off by default |
| Point and score timelines | Score transitions only | Negligible |
| Hold-Tab live stats | 8 Hz while held after this change | Medium while held; previously high |

The three-second peer telemetry is the only notable new periodic match workload.
It is unlikely to create a large sustained loss, but it could explain a regular
brief frame-time pulse. Version-grouped telemetry is needed to confirm or reject
that possibility.

## F5 menu

Opening F5 for the first time synchronously builds all fourteen tabs. That is a
clear one-time hitch and retained-memory cost: the initial pools include 200
Shop rows, 100 Leaderboard rows, 100 Card Stats rows, and 100 leaderboard plus
80 history rows for 2v2. With F5 closed, its update path exits immediately, so
the menu is not a sustained casual-match FPS source.

| Tab while open | Relative cost | Main work |
|---|---:|---|
| Shop | Very high | Large row pool, many visible items, animated thumbnails and optional previews |
| 2v2 | Very high | Large leaderboard/history pools plus 2s, 5s and 10s refresh paths |
| Leaderboard | High | 100 rows, podium/live-series updates and periodic refreshes |
| Card Stats | High | 100 rows; sorting/refill when dirty |
| Compare | Medium-high | Graph/table construction, search and hover work |
| Home | Medium-high | Cosmetic cards, animated thumbnails, chat/presence and 15s refresh |
| Tournaments | Medium | Bracket/history pools and 10s refresh |
| My Stats | Medium | 27 history rows and hover graphs |
| Admin | Medium | Data-dependent lists and review previews |
| Artist | Medium | Items, submissions, sales and image previews |
| 1v2 | Medium | Queue/list refreshes and 3s leaderboard fetch |
| Achievements | Low-medium | Mostly static rows and dirty-driven sorting |
| Settings | Low | Static controls |
| FFA | Low | Minimal current surface |

Lazy construction of inactive tabs would remove the first-open hitch, but that
is a broader UI lifecycle change and is not needed to address FPS while F5 is
closed.

## Settings

| Setting | Gain when disabled | Notes |
|---|---:|---|
| Map Lighting | Very high | Removes the full per-frame SFSS lightmap pass; scene becomes flat/full-bright |
| Map Shadows | High | Removes shadow culling, shadow meshes and the shadow render pass while retaining lighting |
| Player Effects | Medium-high when equipped | Procedural particle auras emit 9–30 particles/s per equipped player, capped at 200; now freeze with Animated Cosmetics |
| Trails | Medium when equipped | Cost rises with player count and premium/prismatic effects |
| Animated Cosmetics | Low-medium, equipment-dependent | Freezes face frames, prismatic/chrome colors, prism trails, map shimmer and player effects |
| Player Colors | Low for static colors; medium with effects | Also acts as the visibility switch for player-effect auras |
| In-game Chat | Low | Wrapped text/layout cache; per-frame array allocation removed |
| FPS and Region/Ping | Low | Full label now refreshes twice per second |
| Match Status | Low | Series/session/H2H strings now refresh at 4 Hz |
| Chromatic Aberration | Low GPU gain | Event-driven post-processing distortion |
| Screen Shake | Low | Event-driven camera work |
| Input Overlay | Low | Only active when explicitly enabled |
| Notifications | Negligible | Intermittent |
| Auto-requeue | None during normal gameplay | Only acts on a matchmaking failure |

Static face items, nametags, titles and static body colors are cheap. Approximate
cosmetic runtime order is player effects, trails, animated body colors,
animated faces/map shimmer, then static cosmetics. Oversized sprites can add GPU
overdraw but do not create a large CPU cost by themselves.

## Performance-patch switches

- Bullet-hit particle cap: largest benefit on burst/projectile-heavy builds.
- Off-screen bullet cleanup: useful in long projectile-heavy rounds; each
  projectile pays a small half-second check.
- Object-pool initial-size clamp: reduces creation hitches rather than steady
  frame time.
- Menu-update skip: small steady gain during a match.
- Stun, hit-sound and edge-bounce guards: no normal-case FPS gain, but prevent
  exception storms from becoming catastrophic.
- Master switch: the aggregate of the enabled patches above.

## Data needed for exact FPS deltas

Use a controlled A/B test on the same machine, map, resolution and card build:

1. lighting and shadows on;
2. shadows off;
3. lighting off;
4. animated cosmetics and player effects off;
5. trails off;
6. Block Debug and hold-Tab tested separately.

For the reported regression, compare the last 30–50 matches by reporter mod
version, mode and day. Report median, p10 and p90 reporter-side FPS, match
duration, freeze timeline, ping and any three-second periodic dips. A profiler
capture is still required to assign exact milliseconds to each subsystem.
