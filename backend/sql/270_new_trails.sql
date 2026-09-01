-- New trails wave: catalog expansion from 12 to 24 trails.
-- Idempotent - ON CONFLICT (sku) DO NOTHING.

BEGIN;

INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
    ('trail_gold',     'trail', 'Midas',           'Everything you leave behind turns gold.',                                          3000,  'rare',      '#FFD24A'),
    ('trail_rose',     'trail', 'Rose Quartz',     'Soft pink shimmer. Deceptively innocent.',                                         3000,  'rare',      '#FF9EC4'),
    ('trail_tidepool', 'trail', 'Tidepool',        'Cool teal wake, fresh from the shallows.',                                         3000,  'rare',      '#2EE6C8'),

    ('trail_sunset',   'trail', 'Sunset',          'Orange melting into pink. Golden hour, every round. Two-color gradient.',           4000,  'rare',      '#FF7A2F'),
    ('trail_ember',    'trail', 'Ember',           'Bright embers cooling into ash. Two-color gradient.',                              4000,  'rare',      '#FF8A3C'),
    ('trail_lagoon',   'trail', 'Lagoon',          'Tropical teal sinking into deep blue. Two-color gradient.',                        4000,  'rare',      '#2EE6C8'),
    ('trail_dusk',     'trail', 'Dusk',            'Dusty rose fading into indigo night. Two-color gradient.',                         4000,  'rare',      '#C87890'),

    ('trail_aurora',   'trail', 'Northern Lights', 'An aurora follows you. Green and violet shimmer with sparkles.',                   5000,  'legendary', '#4DFF9E'),
    ('trail_stardust', 'trail', 'Stardust',        'A silver trail with white twinkles. Leave a little sky behind.',                   5000,  'legendary', '#C8D4FF'),
    ('trail_toxic',    'trail', 'Toxic Spill',     'Radioactive green with lime droplets. Probably safe.',                            5000,  'legendary', '#46E62E'),
    ('trail_firefly',  'trail', 'Fireflies',       'A dark trail lit by drifting warm sparks.',                                       5000,  'legendary', '#FFD24A'),

    ('trail_galaxy',   'trail', 'Galaxy',          'A slow starfield in violet and blue. Bring your own gravity.',                    10000, 'legendary', '#7A5CFF')
ON CONFLICT (sku) DO NOTHING;

COMMIT;
