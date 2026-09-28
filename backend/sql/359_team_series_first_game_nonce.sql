-- 359: team_series.first_game_nonce -- physical game 1 of a 2v2 series, issued
-- by the server (v1.41.0 beta review, round 8, finding F31).
--
-- A game token names a physical game by its ORDINAL, which the room's host
-- counts from the series' physical game 1 (354 keeps a token's nonce; the
-- ordinal is checked in the request). Round 7 let the room's creator name that
-- game 1 from ABSENCE alone: a read of the series showing no recorded game, no
-- relock and no pair of two points on its record. None of that rules out an
-- earlier game whose live posts all failed while its result still waits in
-- the reporter's durable outbox. A restarted creator then named the NEXT game
-- physical game 1, every seat took it, and once one queued result landed the
-- low ordinal could match the recorded games plus one while another result
-- was still queued, so a leave could be settled under the wrong physical game.
--
-- Physical game 1 is now issued by the server, once per series, to the one
-- seat whose client sends the series' match reports (its reporter, the lowest
-- Steam ID of its four members), on a verified Steam session issued before
-- the series was created (the asking process already existed when the series
-- began; a client holds its session in memory only), only while the series
-- has no recorded game, no relock, no game on record in another room and no
-- pair of two points on its record (main.py, team_series_first_game). That
-- client asks only while its durable ledger and outbox hold no report of the
-- series. A result the server still cannot see voids the issued game when it
-- lands (below).
--   first_game_nonce  the nonce the server issued: 16 lowercase hex digits,
--                     the shape of every token nonce (354's CHECK). Written
--                     once, under the series row lock, and never cleared.
--                     NULL = no physical game 1 was issued for the series,
--                     and then no game token of it is read. 'void' = it was
--                     issued and then VOIDED: a match report the series
--                     recorded did not carry the issued nonce's first 8
--                     digits (the report's game_anchor), so a game outside
--                     the issued chain may have reached the record (a
--                     report built on another machine or profile of the
--                     reporter's after the issue carries none, for one) and
--                     no game token of the series is read again. The
--                     only change ever made to a set value is to 'void'.
-- The DC report reads a token only when its nonce begins with the issued
-- nonce's first 8 digits: physical game 1's token carries the issued nonce
-- itself, and every later game's host draws its nonce as those 8 digits plus
-- 8 fresh ones (plugin/TeamGameNumber.cs).
--
-- REQUIRES team_series. Written by POST /api/v1/team/series/{series_id}/
-- first-game (the nonce) and by POST /api/v1/team/matches (the void); read by
-- those two routes and by the DC report (_TEAM_GAME_CROSSED_SQL). Not mapped
-- in models.py: only raw SQL names it (#674).
--
-- DEPLOY ORDER (#477): THIS FILE FIRST, as its own commit and its own deploy,
-- then the API that reads and writes it. A wrong order fails no request: the
-- route's issue is savepointed and answers "not issued" (every client stays
-- tokenless), every DC report settles as dc_incomplete (no automatic
-- forfeit), and a match report voids nothing while the series row has no
-- such column, until this file and the new API are both in place. The API
-- from before this file never names the column.
--
-- Idempotent: IF NOT EXISTS (a re-run skips the whole clause, its CHECK
-- included), one explicit transaction (#340).

BEGIN;

ALTER TABLE team_series
    ADD COLUMN IF NOT EXISTS first_game_nonce TEXT
        CHECK (first_game_nonce IS NULL OR first_game_nonce ~ '^([0-9a-f]{16}|void)$');

COMMIT;
