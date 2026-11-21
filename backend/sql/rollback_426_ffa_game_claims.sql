-- rollback_426_ffa_game_claims.sql
-- Reverses migration 426: drops ffa_game_claims.
--
-- ORDER: the api that writes the table goes first (deploy the previous api,
-- or every held-report Accept and Credit fails on the missing table).
--
-- What this loses: the record of which games were applied or credited from
-- held reports. The payments, the games' rows, the held rows' statuses and
-- the moderator records stay. A rerun is a no-op (IF EXISTS). The claims
-- 426 seeded for games credited before the table existed are rows of the
-- table, so the drop removes them too; this file needs nothing more for
-- them.

BEGIN;

DROP TABLE IF EXISTS ffa_game_claims;

COMMIT;
