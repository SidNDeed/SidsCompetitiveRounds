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
