-- Shop expansion (v1.22.0).
--
-- New titles:
--   3 pronoun titles (100g, common, grey/white)
--   3 mid-tier titles (1000g, uncommon) — Grandma matches Grandmaster's magenta so
--                                          it slots in visually next to it.
--
-- New trails (4000g, rare, two-color gradients, no particle effects):
--   Colossus, Ascendant, Sovereign, Titan
--
-- New trail (5000g, legendary, trans flag colors, particle effects):
--   Tride
--
-- Idempotent — ON CONFLICT (sku) DO NOTHING.

INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
    ('title_pronoun_she',  'title', 'She/her',   'Pronoun title.',                 100,  'common',     '#EEEEEE'),
    ('title_pronoun_they', 'title', 'They/them', 'Pronoun title.',                 100,  'common',     '#EEEEEE'),
    ('title_pronoun_he',   'title', 'He/him',    'Pronoun title.',                 100,  'common',     '#EEEEEE'),

    ('title_idiot',        'title', 'Idiot',     'Self-awareness is a virtue.',   1000,  'uncommon',   '#DDAA33'),
    ('title_grandma',      'title', 'Grandma',   'Wise beyond your years.',       1000,  'uncommon',   '#FF66EE'),
    ('title_decent',       'title', 'Decent',    'Not great. Not terrible.',      1000,  'uncommon',   '#88CC44'),

    ('trail_colossus',     'trail', 'Colossus',  'Icy blue trail fading to white. Two-color gradient.',         4000, 'rare', '#4CADD0'),
    ('trail_ascendant',    'trail', 'Ascendant', 'Deep forest green rising to bright jade. Two-color gradient.', 4000, 'rare', '#71FF9E'),
    ('trail_sovereign',    'trail', 'Sovereign', 'Royal purple drifting into pale cyan. Two-color gradient.',    4000, 'rare', '#8E4CD0'),
    ('trail_titan',        'trail', 'Titan',     'Dusky pink burning into crimson. Two-color gradient.',         4000, 'rare', '#FF4848'),

    ('trail_tride',        'trail', 'Tride',     'Trans pride colors with particle sparkles.',                   5000, 'legendary', '#55CDFC')
ON CONFLICT (sku) DO NOTHING;
