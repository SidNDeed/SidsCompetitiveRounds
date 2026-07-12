-- 107_face_cosmetics_test_items.sql
--
-- Custom character cosmetics framework (v1.30 WIP): 6 test face items,
-- kind='face'. These are purchasable in the F5 shop (Other tab) and equipped
-- inside ROUNDS' own character-editing menu — the mod injects owned items into
-- the vanilla eyes/mouth/detail grids (client CustomCosmetics.cs; IDs 1000+).
-- The server stores NO equip state for faces (vanilla PlayerPrefs + face RPC
-- carry it); shop rows only gate ownership. Catalog parity note: every sku
-- here must have a matching entry in the client's CustomCosmetics.Catalog.
--
-- Idempotent via ON CONFLICT (sku) DO NOTHING.

BEGIN;

INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color)
VALUES
  ('face_eyes_star',    'face', 'Star Eyes',     'Eyes: golden stars. Equip in the Character editor.',            250, 'common',   '#FFD028'),
  ('face_eyes_hearts',  'face', 'Heart Eyes',    'Eyes: lovestruck hearts. Equip in the Character editor.',       250, 'common',   '#E82C4A'),
  ('face_mouth_stache', 'face', 'Moustache',     'Mouth: a distinguished handlebar. Equip in the Character editor.', 250, 'common', '#4A2E18'),
  ('face_mouth_stitch', 'face', 'Stitched Grin', 'Mouth: sewn shut. Equip in the Character editor.',               250, 'common',   '#28282E'),
  ('face_detail_crown', 'face', 'Crown',         'Detail: heavy is the head. Equip in the Character editor.',      750, 'rare',     '#FFC420'),
  ('face_detail_halo',  'face', 'Halo',          'Detail: certified angel. Equip in the Character editor.',        750, 'rare',     '#FFE250')
ON CONFLICT (sku) DO NOTHING;

COMMIT;
