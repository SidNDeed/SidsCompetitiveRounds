-- 118_cosmetics_round2.sql
--
-- Six new house face cosmetics (July 13 batch) matching the client catalog
-- additions in CustomCosmetics.cs. Storm Halo and Flame Crest are the first
-- ANIMATED cosmetics (4-frame __fN pipeline). Requires the client release
-- that ships the art — until then the shop rows resolve but render no
-- thumbnail and can't be equipped by older clients (safe: unknown IDs render
-- as empty slots per the cosmetics design).

INSERT INTO shop_items (sku, kind, name, description, price, rarity, artist_steam_id) VALUES
('face_eyes_crazed',           'face', 'Crazed Eyes',
 'Hypno-spiral eyes. Completely unhinged.',
 250, 'common', '76561198040410653'),
('face_eyes_yinyang',          'face', 'Yin & Yang',
 'Perfect balance. One light, one dark.',
 400, 'rare', '76561198040410653'),
('face_detail_devil_horns',    'face', 'Devil Horns',
 'Curved crimson horns for your inner demon.',
 750, 'rare', '76561198040410653'),
('face_detail_alien_antennae', 'face', 'Alien Antennae',
 'Two glowing green feelers. Take me to your leader.',
 500, 'rare', '76561198040410653'),
('face_detail_storm_halo',     'face', 'Storm Halo',
 'A crackling ring of living lightning. ANIMATED.',
 1500, 'epic', '76561198040410653'),
('face_detail_flame_crest',    'face', 'Flame Crest',
 'A burning crown of fire. ANIMATED.',
 1500, 'epic', '76561198040410653')
ON CONFLICT (sku) DO NOTHING;
