-- 351: team_series_games keyed by the game's identity, never by when a post
-- arrived (lead-forfeit hotfix, round 1: v1.41.0 beta review, round 2,
-- finding 1).
--
-- 348 numbered a post's game by the series' win counters at the moment the
-- post was processed, and asked a 90-second window after the game's opening
-- to tell a real crossing from a previous game's late post. A clock cannot
-- make that call: a real crossing inside the window was discarded, and a late
-- post outside it was counted. The rule in main.py (_record_team_game_points,
-- _team_game_crossed_two) now reads no time. It needs:
--   sitting_room      the room of the sitting the game is played in,
--                     team_series.photon_room_id as the series row stood
--                     under its lock when the post was processed. A relock
--                     clears that room and the next sitting is issued a new
--                     one, so a replayed game number in a new sitting is a
--                     different row. '' marks rows written before this file;
--                     the rule never reads them.
--   pair_seats        which seat posted which pair: bit 4*(3*t1 + t2) + seat,
--                     each side capped at 2, seats 0..3 = t1a, t1b, t2a, t2b.
--                     Only ever OR-ed, so nothing is cleared.
--   attested_max_sum  the largest capped pair sum carried by a post that
--                     named this exact game and sitting (the optional signed
--                     game_number and room). 0 = none.
-- The primary key becomes (series_id, game_ordinal, sitting_room), and the
-- window's columns, crossed_at and max_points_sum, are dropped: nothing reads
-- them any more, and a column that looks like the answer and is not is how
-- the next reader gets it wrong.
--
-- REQUIRES 348 (the table). Written only by
-- POST /api/v1/team/series/{series_id}/live-points, read only by the DC report.
--
-- DEPLOY ORDER: THIS FILE FIRST -- 348, then this file, then the API deploy
-- that writes and reads these columns. Both the writer and the reader are
-- savepointed, so either wrong order fails no request: the live-points POST
-- still answers, and every DC report settles as dc_incomplete (no automatic
-- forfeit) until both this file and the new API are in place. An API from
-- before this file, running against it, records nothing and reads nothing
-- (its upsert names the dropped columns and the old key): the same
-- conservative answer.
--
-- Idempotent: IF [NOT] EXISTS on every column, the key rebuilt only when the
-- new key is absent, one explicit transaction (#340).

BEGIN;

ALTER TABLE team_series_games
    ADD COLUMN IF NOT EXISTS sitting_room TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS pair_seats BIGINT NOT NULL DEFAULT 0
        CHECK (pair_seats BETWEEN 0 AND 68719476735),
    ADD COLUMN IF NOT EXISTS attested_max_sum INTEGER NOT NULL DEFAULT 0
        CHECK (attested_max_sum BETWEEN 0 AND 4);

DO $rekey$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'team_series_games'::regclass
                      AND conname = 'team_series_games_sitting_pkey') THEN
        ALTER TABLE team_series_games DROP CONSTRAINT IF EXISTS team_series_games_pkey;
        ALTER TABLE team_series_games
            ADD CONSTRAINT team_series_games_sitting_pkey
            PRIMARY KEY (series_id, game_ordinal, sitting_room);
    END IF;
END
$rekey$;

ALTER TABLE team_series_games
    DROP COLUMN IF EXISTS crossed_at,
    DROP COLUMN IF EXISTS max_points_sum;

COMMIT;
