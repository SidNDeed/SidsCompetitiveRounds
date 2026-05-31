-- 093_more_nametag_styles.sql
--
-- v1.26.8 expansion: 4 more solid nametag colors filling palette gaps + 1 new
-- size variant + 1 new "float" effect that lifts the name a sliver above its
-- baseline (TMP <voffset>, no new renderer code needed).
--
-- All priced 100g (color tier matches existing nametag_color_*).

INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
('nametag_color_emerald', 'nametag', 'Emerald Name',
 'A vibrant green between Gold and Cyan.',
 100, 'common', '#3DDB7B'),
('nametag_color_amber',   'nametag', 'Amber Name',
 'A soft amber distinct from Gold.',
 100, 'common', '#FFB347'),
('nametag_color_coral',   'nametag', 'Coral Name',
 'A warm coral pink matching the new Coral body.',
 100, 'common', '#FF7E72'),
('nametag_color_indigo',  'nametag', 'Indigo Name',
 'A deep indigo between Purple and Cyan.',
 100, 'common', '#7A6BFF'),
('nametag_size_xl',       'nametag', 'XL Name',
 'Bigger than Bigger, smaller than Huge.',
 100, 'common', '#FFFFFF'),
('nametag_float',         'nametag', 'Floating Name',
 'Lifts your nametag a fraction above its baseline so it appears to hover.',
 100, 'common', '#FFFFFF')
ON CONFLICT (sku) DO NOTHING;
