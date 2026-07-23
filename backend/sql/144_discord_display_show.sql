-- 144_discord_display_show.sql — July 22 (Discord identity split + opt-in)
--
-- ============================================================================
-- !! DEPLOY ORDER: apply BEFORE the API deploy (players ORM gains both
-- !! columns; get_player_stats SELECTs them).
-- ============================================================================
--
-- Two distinct Discord identity fields:
--   discord_username     — the unique @handle (user.name). The Home tab's
--                          "Discord Link" block shows this. Historically this
--                          column held DISPLAY names; the bot re-resolves all
--                          linked rows on next startup and overwrites.
--   discord_display_name — the server/global display name (what the community
--                          knows the player as). Shown on the leaderboard
--                          player detail, ONLY when show_discord is on.
-- show_discord — opt-IN (default false, matches the ORM default; learning #2).

ALTER TABLE players ADD COLUMN IF NOT EXISTS discord_display_name VARCHAR(64);
ALTER TABLE players ADD COLUMN IF NOT EXISTS show_discord BOOLEAN NOT NULL DEFAULT FALSE;
