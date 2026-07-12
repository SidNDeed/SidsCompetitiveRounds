-- 114_cosmetic_submissions_and_new_artists.sql — July 12 round 3
--
-- 1) cosmetic_submissions: artists upload PNG cosmetics in-game for admin
--    review. PNG bytes live in the DB (bytea); at mod-bundle time the approved
--    art is pulled into plugin/cosmetics/ via
--      sql-readonly:SELECT encode(png_data,'base64') FROM cosmetic_submissions WHERE id=N;
--    and a catalog entry ships with the next release.
-- 2) Artist roles for lopidav + Nix (first community artists).
-- 3) Their first two cosmetics as shop rows — born OUT OF STOCK
--    (stock_limit = -1) until each artist opens sales themselves (round 3
--    item 2 rule: nobody can buy before the artist has set things up).
--    stock semantics on shop_items: NULL = unlimited, >0 = capped,
--    -1 = not opened for sale yet (purchase + gift paths reject).

BEGIN;

CREATE TABLE IF NOT EXISTS cosmetic_submissions (
    id                 BIGSERIAL PRIMARY KEY,
    artist_steam_id    TEXT NOT NULL REFERENCES artist_users(steam_id) ON DELETE CASCADE,
    name               VARCHAR(64) NOT NULL,
    slot               VARCHAR(16) NOT NULL,           -- eyes | mouth | detail
    png_data           BYTEA NOT NULL,
    png_bytes          INTEGER NOT NULL,
    status             VARCHAR(16) NOT NULL DEFAULT 'pending',  -- pending | approved | denied
    review_note        TEXT,
    reviewed_by        TEXT,
    reviewed_at        TIMESTAMPTZ,
    shop_sku           VARCHAR(64),                    -- set on approval
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cosmetic_sub_status ON cosmetic_submissions(status);

INSERT INTO artist_users (steam_id, display_name, granted_by_steam_id, notes)
VALUES
  ('76561198041616199', 'lopidav', '76561198040410653', 'granted July 12 - Sprout'),
  ('76561199101676330', 'Nix ツ',  '76561198040410653', 'granted July 12 - Star Earmuffs')
ON CONFLICT (steam_id) DO NOTHING;

INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color, artist_steam_id, stock_limit)
VALUES
  ('face_detail_sprout',   'face', 'Sprout',        'Detail: a fresh sprout, straight from the dirt. Equip in the Character editor.', 750, 'rare', '#2E9E3A', '76561198041616199', -1),
  ('face_detail_earmuffs', 'face', 'Star Earmuffs', 'Detail: cozy star-studded earmuffs. Equip in the Character editor.',             750, 'rare', '#B4182D', '76561199101676330', -1)
ON CONFLICT (sku) DO NOTHING;

-- Sanity output
SELECT steam_id, display_name FROM artist_users ORDER BY granted_at;
SELECT sku, artist_steam_id, stock_limit FROM shop_items WHERE sku IN ('face_detail_sprout','face_detail_earmuffs');

COMMIT;
