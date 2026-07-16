-- 126_appear_offline_and_home.sql
--
-- Home-tab support (v1.33): appear-offline privacy toggle for the new
-- online / recently-online player lists on the F5 Home tab. When true the
-- player is hidden from both lists; the anonymous online COUNT still
-- includes them (it carries no identity).
--
-- Also indexes players.last_seen — the recently-online query orders by it,
-- and presence pings now stamp it (throttled) so the list stays fresh.
-- Idempotent (IF NOT EXISTS guards).

ALTER TABLE players ADD COLUMN IF NOT EXISTS appear_offline BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_players_last_seen ON players (last_seen DESC);

SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'players' AND column_name = 'appear_offline';
