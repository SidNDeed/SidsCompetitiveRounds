-- 246_night_pack_and_gradients.sql
--
-- Aug 23 "night pack" (Sid: more skins like Blackwood — dark brown / pitch
-- black / deep red backgrounds, walls darker than usual; moon, eclipse,
-- underworld, night, rainy day; a Forest Fire with little fire effects) plus
-- ten new per-letter gradient name styles.
--
-- Pricing follows precedent and is SID'S BALANCE KNOB (#331): dark skins at
-- 75g common (migration 095's tier); the six skins that carry an ambient
-- particle effect (embers / rain / stars) at 150g rare; gradients at
-- 1500g epic (migration 096's tier). rotation_pool is deliberately omitted
-- (NULL) — list_shop_items hides any row with a pool. catalog_ready keeps its
-- TRUE default (non-face kinds need no bundled art). Idempotent via
-- ON CONFLICT; explicit transaction because psql -f does not add one (#340).

BEGIN;

INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
('mapcolor_forest_fire', 'color', 'Forest Fire',
 'Night-forest green and bark walls under a dark smoky sky, with embers drifting up through the backdrop.',
 150, 'rare', '#2E5734'),
('mapcolor_moonlit',     'color', 'Moonlit',
 'Pale silver-blue walls over a pitch-black night, with a faint star glint.',
 150, 'rare', '#757F94'),
('mapcolor_eclipse',     'color', 'Eclipse',
 'Charcoal walls rimmed with corona amber on a true black sky.',
 75, 'common', '#2B292E'),
('mapcolor_underworld',  'color', 'Underworld',
 'Ash walls with a dark crimson accent over a deep blood-red dark, red embers rising.',
 150, 'rare', '#524040'),
('mapcolor_night_city',  'color', 'Night City',
 'Dark steel walls with amber window glow against a black-navy sky, city lights twinkling behind.',
 150, 'rare', '#333D52'),
('mapcolor_night_park',  'color', 'Night Park',
 'Deep green hedges and bark-brown walls on a dark brown night.',
 75, 'common', '#265230'),
('mapcolor_rainy_day',   'color', 'Rainy Day',
 'Wet teal-grey stone walls under an overcast slate sky, rain streaking down the backdrop.',
 150, 'rare', '#3B4F54'),
('mapcolor_midnight',    'color', 'Midnight',
 'Dark indigo walls on the purest black background in the catalogue.',
 75, 'common', '#332E61'),
('mapcolor_blood_moon',  'color', 'Blood Moon',
 'Dark ash walls with a pale rose-silver accent over a deep red night, with a faint red glint.',
 150, 'rare', '#3D3638')
ON CONFLICT (sku) DO NOTHING;

INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
('nametag_gradient_fade',     'nametag', 'Fade Gradient',
 'Per-letter white → dark charcoal gradient. Fades out as it goes.',
 1500, 'epic', '#FFFFFF'),
('nametag_gradient_earth',    'nametag', 'Earth Gradient',
 'Per-letter leaf green → bark brown gradient. Canopy to roots.',
 1500, 'epic', '#73D959'),
('nametag_gradient_orchid',   'nametag', 'Orchid Gradient',
 'Per-letter violet → hot pink gradient.',
 1500, 'epic', '#9E59F2'),
('nametag_gradient_sapphire', 'nametag', 'Sapphire Gradient',
 'Per-letter sky blue → deep royal blue gradient.',
 1500, 'epic', '#8CD9FF'),
('nametag_gradient_emerald',  'nametag', 'Emerald Gradient',
 'Per-letter mint → deep forest green gradient.',
 1500, 'epic', '#8CFFA6'),
('nametag_gradient_steel',    'nametag', 'Steel Gradient',
 'Per-letter silver → gunmetal blue gradient. Cold and clean.',
 1500, 'epic', '#DBE0EB'),
('nametag_gradient_ash',      'nametag', 'Ash Gradient',
 'Per-letter warm grey → ember red gradient. Cooling coals.',
 1500, 'epic', '#B8B3AD'),
('nametag_gradient_royal',    'nametag', 'Royal Gradient',
 'Per-letter rich gold → ivory white gradient.',
 1500, 'epic', '#FFC733'),
('nametag_gradient_blood',    'nametag', 'Blood Gradient',
 'Per-letter bright red → dark wine gradient.',
 1500, 'epic', '#FF3838'),
('nametag_gradient_twilight', 'nametag', 'Twilight Gradient',
 'Per-letter sunset orange → dusk purple gradient.',
 1500, 'epic', '#FF9438')
ON CONFLICT (sku) DO NOTHING;

COMMIT;
