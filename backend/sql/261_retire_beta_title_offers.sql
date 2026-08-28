-- 261: Retire the Beta title from open offers (public launch).
--
-- New players now start on the live rank title (title_rank), granted and
-- default-equipped by _mark_mod_seen on their first mod-authenticated action.
-- The Beta title must therefore stop being obtainable: it was a FREE, visible
-- shop item (rotation_pool NULL, price 0), so merely removing the grant would
-- still let any new player click Buy.
--
-- rotation_pool = 'achievement' is the codebase's existing owners-only marker:
--   * purchase 403s (main.py purchase gate),
--   * hidden from /shop/items for non-owners,
--   * still listed to existing owners, who keep their Set Active button.
-- Existing owners' player_items rows and active_title_id are untouched.
--
-- Idempotent: re-running matches zero rows once applied.

BEGIN;

UPDATE shop_items
   SET rotation_pool = 'achievement'
 WHERE sku = 'title_beta'
   AND rotation_pool IS DISTINCT FROM 'achievement';

COMMIT;
