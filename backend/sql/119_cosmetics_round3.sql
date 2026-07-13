-- 119_cosmetics_round3.sql
--
-- Eight more face cosmetics (July 13 round 2): Demon Wings plus a 7-item
-- house batch, two of them animated (Dark Aura / Energy Orbs — 4-frame
-- __fN pipeline @ 7fps).
-- Client catalog + art ship in the next release; same forward-safe behavior
-- as migration 118 (unknown IDs render as empty slots on old clients).

INSERT INTO shop_items (sku, kind, name, description, price, rarity, artist_steam_id) VALUES
('face_detail_demon_wings',   'face', 'Demon Wings',
 'Tattered crimson bat wings straight from the pit. Soul sold separately.',
 2500, 'epic', '76561198040410653'),
('face_detail_thorn_crown',   'face', 'Thorn Crown',
 'A braided crown of twisted thorns, blood-tipped.',
 800, 'rare', '76561198040410653'),
('face_detail_sun_halo',      'face', 'Sunburst Halo',
 'A radiant golden sunburst. Blindingly righteous.',
 800, 'rare', '76561198040410653'),
('face_detail_knight_helm',   'face', 'Knight Great-Helm',
 'Riveted steel great-helm with a T-slit visor.',
 1000, 'rare', '76561198040410653'),
('face_detail_mini_flags',    'face', 'Rally Flags',
 'Two crossed battle standards. For the cause!',
 600, 'rare', '76561198040410653'),
('face_detail_dark_aura',     'face', 'Dark Aura',
 'Wisps of living shadow crown your head. ANIMATED.',
 2000, 'epic', '76561198040410653'),
('face_detail_energy_orbs',   'face', 'Energy Orbs',
 'Three orbiting spheres of raw energy. ANIMATED.',
 2000, 'epic', '76561198040410653'),
('face_detail_tattered_cape', 'face', 'Tattered Cape',
 'A ragged black cloak with a blood-red lining.',
 1000, 'rare', '76561198040410653')
ON CONFLICT (sku) DO NOTHING;
