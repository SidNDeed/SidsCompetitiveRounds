-- 125_nix_party_crown.sql
--
-- Nix's animated "Party Crown" face cosmetic — a 13-frame __fN Detail item
-- (twinkling lights + a pulsing gold star, 9fps; client art shipped in
-- plugin/cosmetics/detail_party_crown.png + __f2..__f13).
--
-- Shop item, kind 'face'. Credited to Nix via artist_steam_id so the standard
-- 30% artist royalty flows to him on each sale (same as his Star Earmuffs).
-- Priced in the animated-detail tier (epic). rotation_pool NULL = always-on in
-- the shop; stock_limit NULL = unlimited. Idempotent (ON CONFLICT DO NOTHING).

INSERT INTO shop_items (sku, kind, name, description, price, rarity, artist_steam_id, preview_color)
VALUES ('face_detail_party_crown', 'face', 'Party Crown',
        'A festive crown of twinkling lights topped with a pulsing gold star.',
        12000, 'epic', '76561199101676330', '#F5C84A')
ON CONFLICT (sku) DO NOTHING;

SELECT sku, name, price, rarity, artist_steam_id
FROM shop_items WHERE sku = 'face_detail_party_crown';
