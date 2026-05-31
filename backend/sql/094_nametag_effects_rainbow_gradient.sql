-- 094_nametag_effects_rainbow_gradient.sql
--
-- Two distinctive "effect" nametags that don't fit the wrap-with-a-tag model
-- of the existing styler entries:
--   nametag_rainbow         — each character of the name in a cycling color
--                             across a 6-color palette. Static (no animation),
--                             rendered natively by TMP, no shader cost.
--   nametag_gradient_sunset — split into amber-then-pink halves so the name
--                             reads as a warm sunset gradient.
--
-- Both occupy the "color" subgroup (single-active) — equipping one swaps out
-- any plain color, neon, or other effect nametag. Premium tier (1000g) since
-- these read as more visually striking than the 100g solid colors.

INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
('nametag_rainbow',         'nametag', 'Rainbow Name',
 'Each letter of your name in a different color of the rainbow.',
 1000, 'rare', '#FFB347'),
('nametag_gradient_sunset', 'nametag', 'Sunset Gradient',
 'Your name fades from warm amber into deep pink.',
 1000, 'rare', '#E64C8A')
ON CONFLICT (sku) DO NOTHING;
