-- 096_more_gradient_nametags.sql
--
-- v1.26.9 nametag expansion: 4 new per-character gradient effects.
-- The existing Sunset Gradient (migration 094) was a 2-char midpoint split
-- which read as "1 letter color A, 1 letter color B" on short names. The
-- client-side renderer was rewritten in v1.26.9 to do per-character linear
-- interpolation between two endpoint colors, so all gradient SKUs now read
-- as smooth gradients across the entire name. Existing Sunset owners get the
-- upgrade for free without a re-equip.
--
-- Pricing: 1500g — premium gradient tier. Above the neon set (500g) per the
-- user's "more expensive than the neon ones" spec, and above the original
-- Sunset Gradient + Rainbow (1000g) because these read as more polished
-- with the new per-character algorithm.

INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
('nametag_gradient_aurora',  'nametag',
 'Aurora Gradient',
 'Per-letter teal → violet gradient. Cold-night-sky shimmer.',
 1500, 'epic', '#4FE0CC'),
('nametag_gradient_ocean',   'nametag',
 'Ocean Gradient',
 'Per-letter bright cyan → deep indigo gradient. Surface to trench.',
 1500, 'epic', '#5BD8FF'),
('nametag_gradient_ember',   'nametag',
 'Ember Gradient',
 'Per-letter bright yellow → deep red gradient. Flame to coal.',
 1500, 'epic', '#FFD42E'),
('nametag_gradient_galaxy',  'nametag',
 'Galaxy Gradient',
 'Per-letter magenta → cyan gradient. Interstellar nebula.',
 1500, 'epic', '#FF59D9')
ON CONFLICT (sku) DO NOTHING;
