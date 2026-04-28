-- v1.25.11: track per-series spawn confirmations so the server can detect when
-- a 4-player team room never assembles (one or more clients fail to spawn) and
-- cancel the series after a 15s deadline instead of letting all 4 sit on the
-- ready screen until our 30s force-StartGame timeout fires.
--
-- Each client posts /team/series/{id}/spawn-confirm when its auto-spawn
-- override successfully creates the local Player. Server increments this
-- counter (idempotent per player_id via the spawn_confirmed_by JSONB array).
-- /team/series/{id}/state returns 'canceled' when (now() - created_at > 15s)
-- AND spawn_confirmations < 4 AND status = 'active'.

ALTER TABLE team_series
    ADD COLUMN IF NOT EXISTS spawn_confirmations SMALLINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS spawn_confirmed_by JSONB NOT NULL DEFAULT '[]'::jsonb;

-- Backfill any historical active series so the new endpoint logic doesn't
-- treat them as still-assembling (they're fully completed; just hadn't tracked).
UPDATE team_series
SET spawn_confirmations = 4
WHERE status IN ('completed', 'canceled', 'invalidated')
  AND spawn_confirmations = 0;
