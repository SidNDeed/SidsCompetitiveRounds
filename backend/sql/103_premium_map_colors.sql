-- 103: v1.29 premium sparkle map skins (Gilded / Platinum / Aurora).
-- Idempotent: safe to re-run.

INSERT INTO shop_items (sku, kind, name, description, price, rarity, rotation_pool, preview_color)
SELECT 'mapcolor_gilded', 'color', 'Gilded',
       'Premium: molten gold walls that glint to white-gold, over a deep bronze vault',
       8000, 'legendary', NULL, '#FFD24A'
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'mapcolor_gilded');

INSERT INTO shop_items (sku, kind, name, description, price, rarity, rotation_pool, preview_color)
SELECT 'mapcolor_platinum', 'color', 'Platinum',
       'Premium: cold silver walls that glint to pure white, over gunmetal dark',
       12000, 'legendary', NULL, '#DDE2EA'
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'mapcolor_platinum');

INSERT INTO shop_items (sku, kind, name, description, price, rarity, rotation_pool, preview_color)
SELECT 'mapcolor_aurora', 'color', 'Aurora',
       'Premium: northern-lights walls shimmering between polar teal and violet in a polar night',
       10000, 'legendary', NULL, '#5FE8C8'
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'mapcolor_aurora');
