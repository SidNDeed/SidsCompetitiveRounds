-- v1.23.x — Lifetime gun accuracy + block success tracking.
--
-- Per-match counts flow through the reporter side of /api/v1/matches; the server adds
-- each successful (non-invalidated) match's deltas into these lifetime columns on the
-- reporter's Player row. Only the reporter sees these numbers — the higher Steam ID's
-- client never sees match completion (see learnings.md note 4), so these are one-sided
-- counters that accumulate from whichever player happened to report each match.
--
-- Definitions:
--   bullets_fired     — total Gun.Attack projectiles fired (sum of numberOfProjectiles per
--                       trigger pull, so shotguns count each pellet)
--   bullets_hit       — count of damage events dealt to an opposing player (self-damage
--                       from rebounds does not count)
--   blocks_activated  — count of Block.TryBlock invocations (right-click attempts)
--   blocks_successful — count of Block.DoBlock invocations where triggerType=Default
--                       (i.e. an actual projectile was absorbed — timing-only right-clicks
--                       on empty air do not count)
--
-- All columns BIGINT because hit counts across hundreds of ranked matches can exceed int32
-- for heavy gun-users (a 20-minute shotgun match fires ~2000 bullets).
--
-- Idempotent.

ALTER TABLE players ADD COLUMN IF NOT EXISTS bullets_fired     BIGINT NOT NULL DEFAULT 0;
ALTER TABLE players ADD COLUMN IF NOT EXISTS bullets_hit       BIGINT NOT NULL DEFAULT 0;
ALTER TABLE players ADD COLUMN IF NOT EXISTS blocks_activated  BIGINT NOT NULL DEFAULT 0;
ALTER TABLE players ADD COLUMN IF NOT EXISTS blocks_successful BIGINT NOT NULL DEFAULT 0;
