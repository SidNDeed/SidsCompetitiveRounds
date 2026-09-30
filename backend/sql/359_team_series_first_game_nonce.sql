-- 359: team_series.first_game_nonce -- the physical game 1 a 2v2 series'
-- game tokens are counted from (v1.41.0 beta review, round 8, finding F31;
-- round 11, finding M1).
--
-- A game token names a physical game by its ORDINAL, counted from the
-- series' physical game 1 (354 keeps a token's nonce; the ordinal and the
-- epoch are checked in the request). The DC report reads a game's crossing
-- from the posts that carried the report's token only when that token is
-- counted from the nonce this column holds: physical game 1's token carries
-- it, and every later game's nonce is derived from the whole of it (main.py,
-- _team_game_chain_nonce and _team_game_first_game_refusal).
--   first_game_nonce  16 lowercase hex digits, the shape of every token
--                     nonce (354's CHECK), or NULL. NULL = no physical game 1
--                     is on record for the series, and then no game token of
--                     it is read.
--
-- NO WRITER. No statement of the API writes this column: since round 11 no
-- physical game 1 is issued or named for any series (main.py, THE FIRST
-- GAME, above _team_game_identity), so it is NULL on every series, no DC
-- report reads a token, and the lead-forfeit settles no series: a mid-series
-- disconnect goes to dc_incomplete. Only the tests write it, to exercise its
-- readers. Read by the DC report (_TEAM_GAME_CROSSED_SQL). Not mapped in
-- models.py: only raw SQL names it (#674).
--
-- DEPLOY ORDER (#477): THIS FILE FIRST, as its own commit and its own deploy,
-- then the API that reads it. A wrong order fails no request: before this
-- file the DC report's read names a column that is not there, fails inside
-- its savepoint, and the report settles as dc_incomplete, which is what it
-- settles as with the column in place and NULL. The API from before this
-- file never names the column.
--
-- Idempotent: IF NOT EXISTS (a re-run skips the whole clause, its CHECK
-- included), one explicit transaction (#340). A database an earlier version
-- of this file already ran on keeps that version's CHECK, which also
-- admits the value 'void' (rounds 8 to 10 wrote it to void an issue); no
-- statement writes either now.

BEGIN;

ALTER TABLE team_series
    ADD COLUMN IF NOT EXISTS first_game_nonce TEXT
        CHECK (first_game_nonce IS NULL OR first_game_nonce ~ '^[0-9a-f]{16}$');

COMMIT;
