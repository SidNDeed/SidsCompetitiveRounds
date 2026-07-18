-- 128_galaxyice_cosmetics.sql — July 17
--
-- 1) Artist role for Galaxyice (third community artist).
-- 2) Their first two cosmetics as shop rows — born OUT OF STOCK
--    (stock_limit = -1) until the artist opens sales themselves, same rule
--    as every artist item since 114. Prices are starting points; the artist
--    adjusts from the Artist tab.
--    Star Spin is the first community-artist ANIMATED item (6-frame orbit).

BEGIN;

INSERT INTO artist_users (steam_id, display_name, granted_by_steam_id, notes)
VALUES
  ('76561199013169799', 'galaxy ice', '76561198040410653', 'granted July 17 - Rounds Cat + Star Spin')
ON CONFLICT (steam_id) DO NOTHING;

INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color, artist_steam_id, stock_limit)
VALUES
  ('face_detail_rounds_cat', 'face', 'Rounds Cat', 'Detail: a round little cat, riding along on your head. Equip in the Character editor.',        750,  'rare', '#9A9A9A', '76561199013169799', -1),
  ('face_detail_star_spin',  'face', 'Star Spin',  'Detail: a shooting star circling overhead (animated). Equip in the Character editor.',        2500, 'epic', '#F5E663', '76561199013169799', -1)
ON CONFLICT (sku) DO NOTHING;

-- Sanity output
SELECT steam_id, display_name FROM artist_users ORDER BY granted_at;
SELECT sku, artist_steam_id, price, stock_limit FROM shop_items WHERE sku IN ('face_detail_rounds_cat','face_detail_star_spin');

COMMIT;
