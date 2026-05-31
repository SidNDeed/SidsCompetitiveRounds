-- 092_more_body_colors.sql
--
-- Four new body-color SKUs covering palette gaps Sid called out in v1.26.8.
-- Solid colors only — no new renderer code needed (PlayerColorCosmetic reads
-- preview_color directly for any non-special SKU). Animated effects like
-- Prismatic / Chrome are special-cased in PlayerColorCosmetic; we'd need a
-- client patch to add new ones in that class.
--
-- Pricing tier matches the existing 4000g "second tier" (Mint, Sunset,
-- Cobalt, Lavender, Obsidian). Each color is chosen for tonal distinctness
-- from anything already in the catalog:
--   pcolor_coral      — warm pink-orange, gap between Rose (4000) and Sunset (4000)
--   pcolor_frost      — icy pale-blue, lighter than Sapphire / Cobalt
--   pcolor_bronze     — warm metallic, distinct from Amber + Gold map color
--   pcolor_twilight   — deep blue-violet, fills space between Amethyst and Obsidian

INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
('pcolor_coral',    'player_color', 'Coral',
 'A warm coral pink with hints of orange.',
 4000, 'rare', '#FF7E72'),
('pcolor_frost',    'player_color', 'Frost',
 'Pale icy blue, like a winter sky.',
 4000, 'rare', '#A8D6F0'),
('pcolor_bronze',   'player_color', 'Bronze',
 'Aged metallic bronze with a warm gleam.',
 4000, 'rare', '#B6754A'),
('pcolor_twilight', 'player_color', 'Twilight',
 'Deep blue-violet of the moment after sunset.',
 4000, 'rare', '#46396E')
ON CONFLICT (sku) DO NOTHING;
