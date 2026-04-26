-- 054_player_colors.sql
-- Player body-color cosmetic. New shop kind 'player_color' overrides the
-- default team color (orange/blue) with a player-chosen tint. Cross-visible
-- via Photon custom prop cr_pbody_color so other mod users see the chosen color.
--
-- Pricing tiers:
--   3000g — solid pretty colors (10 entries)
--   4000g — premium muted/jewel tones (5 entries)
--   5000g — vibrant neons (4 entries)
--   8000g — animated specials (prismatic, rainbow)

ALTER TABLE players
    ADD COLUMN IF NOT EXISTS active_player_color_id BIGINT
        REFERENCES shop_items(id) ON DELETE SET NULL;

-- Tier 1: solid quality colors @ 3000g
INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
    ('pcolor_crimson',     'player_color', 'Crimson',      'Deep blood-red body color.',           3000, 'rare',     '#C83232'),
    ('pcolor_emerald',     'player_color', 'Emerald',      'Rich forest-green body color.',        3000, 'rare',     '#2EB872'),
    ('pcolor_sapphire',    'player_color', 'Sapphire',     'Deep ocean-blue body color.',          3000, 'rare',     '#2A6CD8'),
    ('pcolor_amethyst',    'player_color', 'Amethyst',     'Royal violet body color.',             3000, 'rare',     '#A442D6'),
    ('pcolor_amber',       'player_color', 'Amber',        'Warm honey-gold body color.',          3000, 'rare',     '#E2A43A'),
    ('pcolor_rose',        'player_color', 'Rose',         'Soft pink body color.',                3000, 'rare',     '#E66B95'),
    ('pcolor_teal',        'player_color', 'Teal',         'Cool teal body color.',                3000, 'rare',     '#26A8A8'),
    ('pcolor_charcoal',    'player_color', 'Charcoal',     'Sleek black body color.',              3000, 'rare',     '#2A2A30'),
    ('pcolor_ivory',       'player_color', 'Ivory',        'Clean white body color.',              3000, 'rare',     '#E8E2D0'),
    ('pcolor_slate',       'player_color', 'Slate',        'Cool grey body color.',                3000, 'rare',     '#5A6478')
ON CONFLICT (sku) DO NOTHING;

-- Tier 2: premium jewel/metallic tones @ 4000g
INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
    ('pcolor_obsidian',    'player_color', 'Obsidian',     'Glossy volcanic-black body color.',    4000, 'epic',     '#1A0F1F'),
    ('pcolor_mint',        'player_color', 'Mint',         'Pale spearmint body color.',           4000, 'epic',     '#7FE4B5'),
    ('pcolor_lavender',    'player_color', 'Lavender',     'Soft pastel violet body color.',       4000, 'epic',     '#C3A7E0'),
    ('pcolor_cobalt',      'player_color', 'Cobalt',       'Bright industrial blue body color.',   4000, 'epic',     '#1B5DE0'),
    ('pcolor_sunset',      'player_color', 'Sunset',       'Warm coral-orange body color.',        4000, 'epic',     '#F08561')
ON CONFLICT (sku) DO NOTHING;

-- Tier 3: vibrant neons @ 5000g
INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
    ('pcolor_neon_pink',   'player_color', 'Neon Pink',    'Eye-watering hot-pink body color.',    5000, 'epic',     '#FF2999'),
    ('pcolor_neon_lime',   'player_color', 'Neon Lime',    'Searing electric-green body color.',   5000, 'epic',     '#69FF1F'),
    ('pcolor_neon_cyan',   'player_color', 'Neon Cyan',    'Bright electric-cyan body color.',     5000, 'epic',     '#1FF0FF'),
    ('pcolor_neon_violet', 'player_color', 'Neon Violet',  'Glowing magenta body color.',          5000, 'epic',     '#C220FF')
ON CONFLICT (sku) DO NOTHING;

-- Tier 4: animated specials @ 8000g — client-side renders these with effects
INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
    ('pcolor_prismatic',   'player_color', 'Prismatic',    'Constantly cycles through the rainbow during a match.', 8000, 'legendary', '#FFFFFF'),
    ('pcolor_chrome',      'player_color', 'Chrome',       'Mirrored chrome with a soft shifting tint.',            8000, 'legendary', '#C8C8D8')
ON CONFLICT (sku) DO NOTHING;
