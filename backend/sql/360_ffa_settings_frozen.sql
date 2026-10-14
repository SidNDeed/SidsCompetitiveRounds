-- 360: ffa_matches.settings_frozen -- the settings each FFA game was played
-- under, frozen into the game's own row when its result is recorded (v1.41.0,
-- item 22).
--
-- Every FFA history surface read its settings block (score target, card cap,
-- initial picks, card candidates, the same-card rule, sudden death) LIVE off
-- the lobby row, ffa_lobbies. Those columns are written while the lobby is
-- open and once more when it starts, so today the live row still describes
-- the lobby's games; but a history that reads another table's current state
-- is one writer away from describing a game by settings it was not played
-- under. The transaction that records a game now copies the block into the
-- game's own row, and the history reads it from there.
--   settings_frozen  a JSON object with exactly the six keys of the history
--                    `settings` block: score_target, card_cap, initial_picks
--                    and card_candidates (numbers), same_card_rule and
--                    sudden_death (booleans), taken from the lobby row the
--                    report locks, in the transaction that records the game.
--                    Written once, by the INSERT, and never updated.
--                    NULL = the game was recorded before this file, or its
--                    lobby's settings are unknown (settings_known FALSE,
--                    migration 186); the history then reads the lobby row,
--                    as every row did before this file.
--
-- REQUIRES ffa_matches. Written by POST /api/v1/ffa/matches (submit_ffa_match,
-- its INSERT); read through _ffa_settings_block by the five FFA history
-- surfaces: GET /api/v1/matches/by-code/{code}, /api/v1/series/recent-
-- multimode, /api/v1/ffa/recent, /api/v1/players/{steam_id}/ffa-history and
-- the set report's FFA loader (GET /api/v1/report). Not mapped in models.py:
-- only raw SQL names it (#674).
--
-- DEPLOY ORDER (#477): THIS FILE FIRST, as its own commit and its own deploy,
-- then the API that writes and reads it. The reverse order fails requests:
-- the new API's INSERT names this column, so against a schema without it
-- every FFA report answers 500 and records nothing, and the five history
-- surfaces select it and answer 500 as well. The API from before this file
-- never names the column and runs unchanged against the new schema; a game
-- it records in the window carries NULL, which the new API reads exactly as
-- it reads a game recorded before this file.
--
-- Idempotent: IF NOT EXISTS (a re-run skips the whole clause, its CHECK
-- included), one explicit transaction (#340).

BEGIN;

ALTER TABLE ffa_matches
    ADD COLUMN IF NOT EXISTS settings_frozen JSONB
        CHECK (settings_frozen IS NULL OR jsonb_typeof(settings_frozen) = 'object');

COMMENT ON COLUMN ffa_matches.settings_frozen IS
    'The FFA settings block this game was played under (score_target, card_cap, initial_picks, card_candidates, same_card_rule, sudden_death), copied from the locked lobby row by the INSERT that records the game and never updated. NULL before migration 360, or when the lobby settings are unknown: the history then reads the lobby row.';

COMMIT;
