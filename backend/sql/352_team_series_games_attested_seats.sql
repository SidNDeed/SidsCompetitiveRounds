-- 352: team_series_games.attested_seats -- which seat named which game
-- (lead-forfeit hotfix, round 2: the hotfix review's round 1, findings 1
-- and 2).
--
-- 351 kept one number for every post that named its game and sitting,
-- attested_max_sum: the largest capped pair sum any of them carried, from
-- any seat of either team, and the DC report read two points there as proof
-- of a crossing on their own. The rule in main.py (_record_team_game_points,
-- _team_game_crossed_two) now needs WHICH seat named the game with WHICH
-- pair, because:
--   * a crossing is proven only by a pair of two points or more posted by a
--     seat of EACH team for the same game (seats 0,1 = team 1, 2,3 = team 2);
--   * after the first game of a sitting only a post that named its game says
--     which game its pair describes: the production client can still have a
--     previous game's posts in flight after that game's report, and names no
--     game in them.
-- So:
--   attested_seats  the pair_seats bits (bit 4*(3*t1 + t2) + seat, each side
--                   capped at 2, seats 0..3 = t1a, t1b, t2a, t2b) of the posts
--                   that named exactly this game and sitting. Only ever
--                   OR-ed, so nothing is cleared. 0 = none. The writer sets
--                   each of these bits in pair_seats too.
-- attested_max_sum is dropped: nothing reads it, its value is the largest
-- pair sum in attested_seats, and a column that reads like proof when it is
-- not is how the next reader gets it wrong (351 dropped crossed_at and
-- max_points_sum for the same reason). A row written before this file keeps
-- attested_seats 0: whatever it held counts as unnamed.
--
-- REQUIRES 351 (sitting_room, pair_seats, the sitting key), and so 348.
-- Written only by POST /api/v1/team/series/{series_id}/live-points, read only
-- by the DC report.
--
-- DEPLOY ORDER: THIS FILE FIRST -- 348, 351, then this file, then the API
-- deploy that writes and reads this column. Both the writer and the reader
-- are savepointed, so a wrong order fails no request: the live-points POST
-- still answers, and every DC report settles as dc_incomplete (no automatic
-- forfeit) until this file and the new API are both in place. An API from
-- round 1 of the hotfix, running against this file, records nothing and reads
-- nothing (its upsert and its read name attested_max_sum): the same answer.
--
-- Idempotent: IF [NOT] EXISTS on both columns, one explicit transaction
-- (#340). Running 351 again after this file adds attested_max_sum back as a
-- column of zeros that nothing writes or reads; running this file again drops
-- it.

BEGIN;

ALTER TABLE team_series_games
    ADD COLUMN IF NOT EXISTS attested_seats BIGINT NOT NULL DEFAULT 0
        CHECK (attested_seats BETWEEN 0 AND 68719476735),
    DROP COLUMN IF EXISTS attested_max_sum;

COMMIT;
