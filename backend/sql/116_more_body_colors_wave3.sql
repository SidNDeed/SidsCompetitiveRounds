-- 116_more_body_colors_wave3.sql
--
-- Twelve new body-color SKUs per request: yellows, more greens, skin tones,
-- and a couple more reds. Solid colors only — PlayerColorCosmetic reads
-- preview_color directly for any non-special SKU, so no client patch needed
-- (same as waves 054/092).
--
-- Pricing follows the established tiers: 3000 rare base, 4000 for the two
-- "prestige" shades (Gold, Maroon). Hexes chosen for tonal distinctness from
-- the existing 25 (e.g. Lemon/Mustard vs Amber's orange lean; Forest/Olive/
-- Lime vs Emerald/Mint/Neon Lime; Scarlet/Maroon vs Crimson/Coral/Sunset).
-- The four skin tones span light to deep.

INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
-- Yellows
('pcolor_lemon',     'player_color', 'Lemon',
 'A bright, sunny yellow.',
 3000, 'rare', '#F2E23A'),
('pcolor_mustard',   'player_color', 'Mustard',
 'A deep, earthy yellow.',
 3000, 'rare', '#C9A227'),
('pcolor_gold',      'player_color', 'Gold',
 'A rich, gleaming gold.',
 4000, 'epic', '#E8C21C'),
-- Greens
('pcolor_forest',    'player_color', 'Forest',
 'A deep woodland green.',
 3000, 'rare', '#2E6B34'),
('pcolor_olive',     'player_color', 'Olive',
 'A muted, earthy olive green.',
 3000, 'rare', '#7A8038'),
('pcolor_lime',      'player_color', 'Lime',
 'A zesty yellow-green.',
 3000, 'rare', '#9ADE3B'),
-- Skin tones
('pcolor_porcelain', 'player_color', 'Porcelain',
 'A light, warm skin tone.',
 3000, 'rare', '#F4D9C2'),
('pcolor_tan',       'player_color', 'Tan',
 'A sun-kissed medium skin tone.',
 3000, 'rare', '#D9A876'),
('pcolor_sienna',    'player_color', 'Sienna',
 'A rich, warm brown skin tone.',
 3000, 'rare', '#A9714B'),
('pcolor_umber',     'player_color', 'Umber',
 'A deep, dark skin tone.',
 3000, 'rare', '#6E4630'),
-- Reds
('pcolor_scarlet',   'player_color', 'Scarlet',
 'A fiery bright red.',
 3000, 'rare', '#E43B2C'),
('pcolor_maroon',    'player_color', 'Maroon',
 'A deep wine red.',
 4000, 'rare', '#7E2233')
ON CONFLICT (sku) DO NOTHING;
