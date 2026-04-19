-- v1.22.5 — additional custom map colors with physical block tinting.
-- All existing SKUs preserved; this is purely additive.

INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
    ('mapcolor_forest',     'color', 'Forest',    'Deep evergreen blocks on a dimmed green-tinged backdrop.',   75,  'common', '#2D5C3D'),
    ('mapcolor_amethyst',   'color', 'Amethyst',  'Rich purple blocks on a dim cool backdrop.',                 75,  'common', '#6B338C'),
    ('mapcolor_charcoal',   'color', 'Charcoal',  'Near-black blocks on a black background — max contrast.',   100,  'common', '#2D2D33'),
    ('mapcolor_crimson_map','color', 'Crimson',   'Dark red blocks on a dim warm backdrop.',                    75,  'common', '#732629'),
    ('mapcolor_slate',      'color', 'Slate',     'Cool grey-blue blocks on a dim cool backdrop.',              75,  'common', '#52667F'),
    ('mapcolor_rose',       'color', 'Rose',      'Dusty rose blocks on a warm dim backdrop.',                  75,  'common', '#9E5C6B'),
    ('mapcolor_mint',       'color', 'Mint',      'Pale mint blocks on a cool dim backdrop.',                   75,  'common', '#8CC7A6'),
    ('mapcolor_sunset',     'color', 'Sunset',    'Warm orange blocks on a sunset-toned backdrop.',             75,  'common', '#D9734D')
ON CONFLICT (sku) DO NOTHING;
