-- 233_ffa_early_leave_grace.sql
-- FFA early-leave grace (Sid, 2026-08-20).
--
-- A player who leaves an FFA before the FIELD has scored two points is no
-- longer rated for that game: below two half-points nothing has been decided,
-- so the placement the report hands them is not evidence about anybody. Same
-- threshold as every other "2 points scored" rule we run (the bet cutoff, the
-- 2v2 dc_leadforfeit gate) and as the client's own bug-#114 fresh-game cancel.
--
-- The server marks them `absent` (the existing "did not play THIS game" flag,
-- which already excludes a row from rating, XP/gold, the rating-history graph
-- and every profile aggregate). This column is what tells the two cases apart
-- afterwards:
--
--   absent + game_points_at_leave IS NULL  -> carried roster ghost: left in an
--                                             EARLIER game of the sitting.
--   absent + game_points_at_leave = 0 or 1 -> left THIS game inside the grace
--                                             window; the value is the field's
--                                             point total at the moment they
--                                             left, as reported by a survivor.
--   NOT absent + game_points_at_leave set  -> a normal rated leaver (left at 2+
--                                             points), or a grace claim the
--                                             signed-tally guard refused. The
--                                             value is kept either way so a
--                                             refusal stays visible evidence.
--
-- Additive-safe: one nullable column, no backfill, no rewrite. Rows written
-- before this migration and by clients that do not send the field stay NULL,
-- which reads correctly as "not reported".
--
-- Numbering note: 231 was claimed by two parallel work streams (Lexia admin,
-- NotNic gold) and 232 left free for the loser of that race.

ALTER TABLE ffa_match_players
    ADD COLUMN IF NOT EXISTS game_points_at_leave SMALLINT;

COMMENT ON COLUMN ffa_match_players.game_points_at_leave IS
    'Total points scored by the whole field at the moment this player left, '
    'reported by a surviving client. Only ever set for left_early rows. '
    'NULL = not reported (pre-v1.39 client, or a carried roster ghost). '
    'Below FFA_LEAVE_GRACE_POINTS the player is unrated for the game.';
