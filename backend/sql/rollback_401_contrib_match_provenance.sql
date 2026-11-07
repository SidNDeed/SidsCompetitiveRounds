-- rollback_401_contrib_match_provenance.sql
--
-- Removes what 401_contrib_match_provenance.sql added: the indexes
-- ix_combat_contrib_match and ix_card_contrib_match, and the column
-- combat_contrib.match_id with every value the combat worker stored in it.
-- card_contrib.match_id belongs to 370 and is left in place. No other
-- object references the column or the two indexes. Re-runnable: every DROP
-- is IF EXISTS, so a second run does nothing.
--
-- DEPLOY ORDER: THE API FIRST. Deploy an api build without this lane (one
-- whose combat worker INSERT and admin report combat select do not name
-- combat_contrib.match_id), then run this file. An api that still names the
-- column fails every combat derivation and reads the report's combat
-- section as `unavailable` once the column is gone.
--
-- Each DROP takes ACCESS EXCLUSIVE on its table for the drop itself, which
-- is short; `lock_timeout` bounds how long the file waits to start it, and a
-- timeout rolls the whole file back with nothing dropped.

BEGIN;
SET LOCAL lock_timeout = '5s';

DROP INDEX IF EXISTS ix_card_contrib_match;
DROP INDEX IF EXISTS ix_combat_contrib_match;
ALTER TABLE combat_contrib DROP COLUMN IF EXISTS match_id;

COMMIT;
