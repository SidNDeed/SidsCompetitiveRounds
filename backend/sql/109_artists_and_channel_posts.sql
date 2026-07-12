-- 109_artists_and_channel_posts.sql  (v1.30)
--
-- 1) Artist role: community cosmetic creators get control over their OWN shop
--    items — price, stock cap, gifting copies, blocking specific buyers.
--    Mirrors the admin_users pattern; enforced by /artist endpoints in main.py
--    (HMAC 'artist:{steam_id}:{action}:{args}') and audited to artist_actions.
-- 2) pending_channel_posts: generic bot announce queue (first use: the
--    #scr-faq sheet, migration 110). The bot polls unposted rows and acks
--    posted_at after each successful Discord send (learning #105 pattern).

-- Item ownership + stock live on shop_items so every existing shop/equip path
-- keeps working untouched. NULL artist = house item; NULL stock = unlimited.
ALTER TABLE shop_items ADD COLUMN IF NOT EXISTS artist_steam_id VARCHAR(20);
ALTER TABLE shop_items ADD COLUMN IF NOT EXISTS stock_limit INTEGER;

CREATE TABLE IF NOT EXISTS artist_users (
    steam_id            TEXT PRIMARY KEY,
    display_name        TEXT,
    granted_by_steam_id TEXT,
    granted_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS artist_item_blocks (
    artist_steam_id  TEXT NOT NULL REFERENCES artist_users(steam_id) ON DELETE CASCADE,
    blocked_steam_id VARCHAR(20) NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (artist_steam_id, blocked_steam_id)
);

CREATE TABLE IF NOT EXISTS artist_actions (
    id              BIGSERIAL PRIMARY KEY,
    artist_steam_id TEXT NOT NULL,
    action          TEXT NOT NULL,
    target          TEXT,
    detail          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pending_channel_posts (
    id         BIGSERIAL PRIMARY KEY,
    channel_id TEXT NOT NULL,
    content    TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    posted_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_pending_channel_posts_unposted
    ON pending_channel_posts (sort_order, id) WHERE posted_at IS NULL;

-- Seed: Sid as the first artist (lets the Artist tab be play-tested before
-- community artists are onboarded). The 6 v1.30 test face items become his.
INSERT INTO artist_users (steam_id, display_name, granted_by_steam_id, notes)
VALUES ('76561198040410653', 'Sid', '76561198040410653', 'seed — mod owner')
ON CONFLICT (steam_id) DO NOTHING;

UPDATE shop_items
   SET artist_steam_id = '76561198040410653'
 WHERE kind = 'face' AND artist_steam_id IS NULL;
