-- 362: team_series.first_game_session -- the Steam session a 2v2 series'
-- physical game 1 was issued to (v1.41.0 beta review, round 9, finding M1).
--
-- Migration 359 keeps the nonce this server issues as a series' physical
-- game 1 (team_series.first_game_nonce). Round 8 issued it to the series'
-- reporter on a verified Steam session issued before the series was
-- created, which rules out a reporter that restarted. It did not rule out
-- a SECOND process of the reporter's account alive at the same time (a
-- second machine or profile, each with its own session): that process may
-- have played an earlier game of the series whose result the server has not
-- seen, and the chain issued to the first process would then count that
-- game's successor as physical game 1.
--
-- Round 9 issues physical game 1 only when, besides round 8's rules, no
-- OTHER Steam session of the reporter's account (any steam_sessions row but
-- the ask's own, verified or not) was live at any moment after the series
-- was created (its expires_at is after the series' created_at), the series
-- was created less than a day before the ask (a steam_sessions row is only
-- pruned once it expired more than a day ago, so no such row can have been
-- pruned), and the series' live-points record holds no post at all and its
-- live totals are zero (main.py, team_series_first_game). It records here
-- WHICH session it issued to:
--   first_game_session  the sha256 of the Steam session token the issue was
--                       answered to: 64 lowercase hex digits, the form
--                       steam_sessions.token_hash keeps. Written once, in
--                       the same UPDATE that writes first_game_nonce, under
--                       the series row lock, and never changed. NULL = no
--                       issue is recorded with a session (nothing was
--                       issued, or it was issued before this file, which no
--                       deployed API did), and then no game token of the
--                       series is read.
-- A match report the series records voids the issued game (first_game_nonce
-- becomes 'void') unless it carries the full issued nonce as its game_anchor
-- AND arrives on this session; a DC report sent by the reporter's account is
-- read with its game token only on this session. A report from any other
-- process of the reporter's account is therefore unproven, and its outcome
-- is the conservative one: no token is read (dc_incomplete) and, for a
-- match report, the issued game is voided.
--
-- REQUIRES 359 (team_series.first_game_nonce). Written by POST
-- /api/v1/team/series/{series_id}/first-game; read by POST
-- /api/v1/team/matches (the void) and by the DC report
-- (_TEAM_GAME_CROSSED_SQL). Not mapped in models.py: only raw SQL names it
-- (#674).
--
-- DEPLOY ORDER (#477): after 359 (and the files before it: 348, 351, 352,
-- 354), THIS FILE, as its own commit and its own deploy, then the API that
-- reads and writes it. A wrong order fails no request: the issue's UPDATE
-- names this column, so before this file it fails inside its savepoint and
-- every ask is answered "not issued" (every client stays tokenless); every
-- DC report settles as dc_incomplete (the record's read names the column
-- and fails inside its savepoint); and no match report can find a game
-- issued, because none can be. The API from before this file never names
-- the column.
--
-- Idempotent: IF NOT EXISTS (a re-run skips the whole clause, its CHECK
-- included), one explicit transaction (#340).

BEGIN;

ALTER TABLE team_series
    ADD COLUMN IF NOT EXISTS first_game_session TEXT
        CHECK (first_game_session IS NULL OR first_game_session ~ '^[0-9a-f]{64}$');

COMMIT;
