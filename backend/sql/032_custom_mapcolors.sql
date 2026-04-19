-- v1.22.2 — re-add the "calm" map color SKUs, this time backed by runtime-authored
-- PostProcessProfiles in plugin/CustomMapColors.cs. These don't map to any vanilla
-- ROUNDS art name; the client recognizes them via CustomMapColors.IsCustomSku.
--
-- Pricing matches the vanilla locks (75g) so the visual options are evenly priced.
-- Monochrome stays at 100g — it's the most extreme effect.
--
-- Idempotent — ON CONFLICT (sku) DO NOTHING.

INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
    ('mapcolor_soft',     'color', 'Soft Slate', 'Cool desaturated slate-grey — easy on the eyes.',  75,  'common', '#5A6A78'),
    ('mapcolor_moss',     'color', 'Moss',       'Calm forest-green tint with low saturation.',     75,  'common', '#3F6B47'),
    ('mapcolor_cream',    'color', 'Cream',      'Warm cream + tan palette.',                       75,  'common', '#D9C9A0'),
    ('mapcolor_lavender', 'color', 'Lavender',   'Soft pastel lavender — minimum contrast.',        75,  'common', '#9D8FBE'),
    ('mapcolor_dusk',     'color', 'Dusk',       'Deep cool dusk blues with dimmed exposure.',      75,  'common', '#3A4960'),
    ('mapcolor_sand',     'color', 'Sand',       'Warm desert sand tones.',                         75,  'common', '#C8A67B'),
    ('mapcolor_mono',     'color', 'Monochrome', 'Pure greyscale — minimum visual distraction.',   100,  'common', '#A0A0A0')
ON CONFLICT (sku) DO NOTHING;
