-- 354: team_series_games.game_token -- which PHYSICAL game a record holds
-- (v1.41.0 beta review, round 4, finding F25).
--
-- A record is named by the series' recorded games plus one and the sitting's
-- room (351). That name is not a physical game: when a game's report is still
-- on its way (the reporter's client queues a report the server did not
-- commit, and retries it 30 s later) the next game starts while the server
-- still counts one game fewer, both games freeze the same number, and the
-- two games' posts land in ONE record. A disconnect at 0-0 in the second game
-- then read the first game's crossing as its own.
--
-- The client now carries a token for the physical game: the room's host
-- publishes a fresh one as a Photon room property at every game start, every
-- seat reads that same property, and every post that names its game signs it
-- as well; the DC report names the token of the game its reporter is in. The
-- rule in main.py (_record_team_game_points, _team_game_crossed_two) needs:
--   game_token      the token of the FIRST post filed in this record that
--                   carried a valid one. Written once, never replaced. NULL =
--                   no post of this record carried a token.
--   token_seats     the pair_seats bits (bit 4*(3*t1 + t2) + seat, each side
--                   capped at 2, seats 0..3 = t1a, t1b, t2a, t2b) of the posts
--                   that carried game_token. Only ever OR-ed. A post carrying
--                   another token sets none of them.
--   token_conflict  a post carrying a token OTHER than game_token was filed
--                   in this record: two physical games shared the record.
--                   Only ever set, never cleared.
-- A lead-forfeit needs the DC report's token to be this record's game_token,
-- no conflict, the token on no other record of the series, and a pair of two
-- points from a seat of each team among token_seats. A row written before this
-- file keeps game_token NULL: no lead-forfeit is ever read from it.
--
-- REQUIRES 352 (attested_seats), and so 351 (sitting_room, pair_seats, the
-- sitting key) and 348. Written only by
-- POST /api/v1/team/series/{series_id}/live-points, read only by the DC report.
--
-- DEPLOY ORDER: THIS FILE FIRST -- 348, 351, 352, then this file, then the API
-- deploy that writes and reads these columns. Both the writer and the reader
-- are savepointed, so a wrong order fails no request: the live-points POST
-- still answers, and every DC report settles as dc_incomplete (no automatic
-- forfeit) until this file and the new API are both in place. The API from
-- before this file, running against it, writes and reads the columns it
-- always did; the three new ones keep their defaults.
--
-- Idempotent: IF NOT EXISTS on every column (a re-run skips each whole
-- clause, its CHECK included), one explicit transaction (#340).

BEGIN;

ALTER TABLE team_series_games
    ADD COLUMN IF NOT EXISTS game_token TEXT
        CHECK (game_token IS NULL OR game_token ~ '^[0-9a-f]{16}$'),
    ADD COLUMN IF NOT EXISTS token_seats BIGINT NOT NULL DEFAULT 0
        CHECK (token_seats BETWEEN 0 AND 68719476735),
    ADD COLUMN IF NOT EXISTS token_conflict BOOLEAN NOT NULL DEFAULT FALSE;

COMMIT;
