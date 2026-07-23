-- 146_show_discord_optout.sql — July 22 (v1.34.1): flip Discord visibility to OPT-OUT
--
-- ============================================================================
-- !! DEPLOY ORDER: apply BEFORE the API deploy (models.py default flips to
-- !! TRUE to match — learning #2: SQL default and ORM default must agree).
-- ============================================================================
--
-- v1.34.0 shipped show_discord as opt-IN (default FALSE). Per Sid it should be
-- opt-OUT: people asking for ranked via Search Ranked want to be @-able in
-- Discord by default, and the leaderboard should show linked names unless a
-- player deliberately hides. Nobody meaningfully "chose" FALSE (it was the
-- default of an opt-in feature that shipped hours ago), so blanket TRUE is the
-- correct migration — a player who wants to hide flips the Settings toggle.

ALTER TABLE players ALTER COLUMN show_discord SET DEFAULT TRUE;
UPDATE players SET show_discord = TRUE WHERE show_discord = FALSE;
