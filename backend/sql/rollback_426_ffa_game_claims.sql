-- rollback_426_ffa_game_claims.sql
-- Reverses migration 426: drops ffa_game_claims.
--
-- ORDER: the api that writes the table goes first (deploy the previous api,
-- or every held-report Accept and Credit fails on the missing table).
--
-- What this loses: the record of which games were applied or credited from
-- held reports. The payments, the games' rows, the held rows' statuses and
-- the moderator records stay. A rerun is a no-op (IF EXISTS).

BEGIN;

DROP TABLE IF EXISTS ffa_game_claims;

COMMIT;
