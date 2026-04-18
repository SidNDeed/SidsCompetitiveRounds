-- 016_discord_username.sql
-- Cache the Discord username on the player row so the in-game UI can show
-- "Linked as @sidndeed" instead of "ID: 123456789". Bot writes this at
-- link time; backfill is deferred — missing rows just fall back to ID.

ALTER TABLE players ADD COLUMN IF NOT EXISTS discord_username VARCHAR(64);
