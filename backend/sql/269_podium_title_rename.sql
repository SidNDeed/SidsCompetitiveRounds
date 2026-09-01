-- 269_podium_title_rename.sql
-- Aug 31 batch: mode-prefix the 1v1 podium title's SHOP label to match the
-- rename of its rendered text ("1st Place" -> "1v1 1st Place", which lives in
-- main.py's PODIUM_TITLES, not here — migration 216's contract: display text
-- is resolved at RENDER time; this row is only the Shop/inventory label).
-- Idempotent: the UPDATE keys on the old value, a rerun matches zero rows.
BEGIN;

UPDATE shop_items
   SET name = '1v1 Podium',
       description = 'Held by the top 3 on the 1v1 ranked leaderboard'
 WHERE sku = 'title_podium'
   AND name = 'Podium';

COMMIT;
