-- Rollback of 402: remove the Purgatory shop row, but only while nobody owns
-- it. A player_items row for the sku means gold has moved; deleting the item
-- would cascade that purchase away (player_items.item_id ON DELETE CASCADE,
-- 021), so the file RAISES instead and leaves every row in place. Refunds are
-- a person's decision, made before this file is run again. A rerun after a
-- successful rollback finds no row and changes nothing.
--
-- Lock first, then judge, inside one transaction (#340, #1072): the ownership
-- check and the delete see the same rows.
--
-- DEPLOY ORDER: THIS FILE FIRST and alone; the api needs no change either way.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

DO $$
DECLARE
    owners INTEGER;
BEGIN
    PERFORM 1 FROM shop_items WHERE sku = 'mapcolor_purgatory' FOR UPDATE;
    SELECT COUNT(*) INTO owners
      FROM player_items pi
      JOIN shop_items si ON si.id = pi.item_id
     WHERE si.sku = 'mapcolor_purgatory';
    IF owners > 0 THEN
        RAISE EXCEPTION 'rollback_402: mapcolor_purgatory is owned by % player(s); refund by hand before removing the item', owners;
    END IF;
    DELETE FROM shop_items WHERE sku = 'mapcolor_purgatory';
    RAISE NOTICE 'rollback_402: mapcolor_purgatory removed (or was already absent)';
END $$;

COMMIT;
