-- 095_more_dark_map_colors.sql
--
-- v1.26.8 designer pass: 8 new map color SKUs, all dark enough that the
-- background doesn't blind a player using the mod's "background tint follows
-- the SKU" path. Per Sid's spec: backgrounds MUST be dark, walls can carry
-- slightly more color but no pale series.
--
-- Channel-average brightness verified for each entry (target ≤ 60/255):
--   obsidian     #1A1A1F  avg 27   — near-black volcanic glass
--   abyss        #0F1822  avg 24   — deep ocean midnight
--   pine         #1F3A2E  avg 45   — dark evergreen forest
--   iron         #2A2D33  avg 46   — industrial steel grey
--   burgundy     #3A1422  avg 37   — aged wine
--   magma        #3E1414  avg 35   — volcanic oxblood (darkened from #5C1F1F to clear the cap)
--   velvet       #2A0F22  avg 30   — deep royal purple
--   blackwood    #1F1A18  avg 27   — charred timber
--
-- All priced 75g matching the existing Sky/Poison/etc tier. Obsidian and
-- Abyss could justify the 100g premium tier (alongside Mono/Charcoal) but
-- holding to 75g keeps the new set accessible.

INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
('mapcolor_obsidian',   'color', 'Obsidian',
 'Near-black volcanic glass. Disappears into the night.',
 75, 'common', '#1A1A1F'),
('mapcolor_abyss',      'color', 'Abyss',
 'Deep ocean midnight — black with a hint of cold blue.',
 75, 'common', '#0F1822'),
('mapcolor_pine',       'color', 'Pine',
 'Evergreen forest at dusk.',
 75, 'common', '#1F3A2E'),
('mapcolor_iron',       'color', 'Iron',
 'Industrial steel grey with the warmth bled out.',
 75, 'common', '#2A2D33'),
('mapcolor_burgundy',   'color', 'Burgundy',
 'Aged wine — deep red with a brown undertone.',
 75, 'common', '#3A1422'),
('mapcolor_magma',      'color', 'Magma',
 'Cooled lava — volcanic oxblood at the edge of black.',
 75, 'common', '#3E1414'),
('mapcolor_velvet',     'color', 'Velvet',
 'Deep royal purple, the kind that absorbs every photon.',
 75, 'common', '#2A0F22'),
('mapcolor_blackwood',  'color', 'Blackwood',
 'Charred timber — warm dark brown verging on black.',
 75, 'common', '#1F1A18')
ON CONFLICT (sku) DO NOTHING;
