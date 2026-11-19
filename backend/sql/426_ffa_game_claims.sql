-- 426_ffa_game_claims.sql
-- One claim per FFA game that an admin applied or credited from a held
-- report (QAPPLY-1). A game is named by its lobby and its game number; the
-- primary key makes a second claim of one game impossible, whatever number
-- of held rows describe that game.
--
-- The api's held-report Accept writes a row of kind 'accept' in the game's
-- own transaction; Credit writes a row of kind 'credit' before it pays. Both
-- read the table under the lobby's row lock and refuse a game that holds a
-- row; the insert itself is ON CONFLICT DO NOTHING and the api refuses when
-- it returns nothing, so the key refuses a second claim even where a read
-- was skipped. quarantine_id is the held row the claim was made from.
--
-- DEPLOY ORDER: this file first, then the api (the api of this lane writes
-- the table on every Accept and Credit of a held report; the api before it
-- never names the table).
--
-- A rerun is a no-op: every statement is guarded by IF NOT EXISTS.

BEGIN;

CREATE TABLE IF NOT EXISTS ffa_game_claims (
    lobby_id UUID NOT NULL,
    game_number SMALLINT NOT NULL,
    kind TEXT NOT NULL,
    quarantine_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_ffa_game_claims PRIMARY KEY (lobby_id, game_number),
    CONSTRAINT ck_ffa_game_claims_kind CHECK (kind IN ('accept', 'credit')),
    CONSTRAINT ck_ffa_game_claims_game CHECK (game_number BETWEEN 1 AND 999)
);

COMMIT;
