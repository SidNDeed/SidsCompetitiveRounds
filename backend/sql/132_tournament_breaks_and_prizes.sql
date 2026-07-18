-- 132_tournament_breaks_and_prizes.sql — July 17 round 2 (item 2)
--
-- 1) tournaments.prize_player_count: confirmed player count snapshotted at
--    lock. Prizes now scale with player count (base at 8 = double the old
--    16-player full tier, 2x base at 16) via _prize_amounts() in
--    tournaments.py — prize_tier stays populated for legacy readers.
-- 2) tournament_matches break state: sync rounds 2+ enter status='scheduled'
--    with scheduled_ready_at = activation + 7 min; both players pressing
--    Play Now (early_ok_signup_ids) skips the break. The no-show sweep only
--    watches status='ready', so the break can never forfeit anyone.

BEGIN;

ALTER TABLE tournaments
    ADD COLUMN IF NOT EXISTS prize_player_count SMALLINT;

ALTER TABLE tournament_matches
    ADD COLUMN IF NOT EXISTS scheduled_ready_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS early_ok_signup_ids UUID[] NOT NULL DEFAULT '{}';

COMMIT;
