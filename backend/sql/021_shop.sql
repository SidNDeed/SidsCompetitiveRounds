-- 021_shop.sql
--
-- Shop catalog, player inventories, and the active-title column.
--
-- `shop_items.rotation_pool`:
--   NULL        → always-available, never rotates out
--   non-null    → belongs to a named rotation pool. A future daily job picks
--                 N items per pool for that day's shop. Schema supports it now
--                 but the current UI only surfaces always-available items.
--
-- `player_items.purchase_price` is the snapshotted price at time of purchase
-- so price changes / sales later don't alter historical records.
--
-- `players.active_title_id` FKs back into shop_items. Enforced only when the
-- title is actually owned by the player — we check that at set-time.

CREATE TABLE IF NOT EXISTS shop_items (
    id              BIGSERIAL PRIMARY KEY,
    sku             VARCHAR(64) UNIQUE NOT NULL,
    kind            VARCHAR(16) NOT NULL,    -- 'title' (trails coming later)
    name            VARCHAR(128) NOT NULL,
    description     VARCHAR(256),
    price           INTEGER NOT NULL CHECK (price >= 0),
    rarity          VARCHAR(16) NOT NULL DEFAULT 'common',  -- 'common'|'rare'|'legendary'
    rotation_pool   VARCHAR(32),                            -- NULL = always on
    preview_color   VARCHAR(16),                            -- hex (#RRGGBB) for titles
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS player_items (
    player_id      UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    item_id        BIGINT NOT NULL REFERENCES shop_items(id) ON DELETE CASCADE,
    purchased_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    purchase_price INTEGER NOT NULL,
    PRIMARY KEY (player_id, item_id)
);

CREATE INDEX IF NOT EXISTS idx_player_items_player ON player_items (player_id);

ALTER TABLE players
    ADD COLUMN IF NOT EXISTS active_title_id BIGINT REFERENCES shop_items(id) ON DELETE SET NULL;

-- Initial catalog — all always-available, none rotating yet. Prices are sized
-- so the cheapest title (~500g) takes ≈20 hours of average play to afford.
INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
    ('title_beginner',    'title', 'Beginner',     'Freshly unlocked. Welcome aboard.',                      500,  'common',    '#AAAAAA'),
    ('title_regular',     'title', 'Regular',      'You show up.',                                           500,  'common',    '#FFFFFF'),
    ('title_active',      'title', 'Active',       'More ranked than not.',                                  500,  'common',    '#44CC88'),
    ('title_sweaty',      'title', 'Sweaty',       'Sweat is just XP in liquid form.',                       1500, 'rare',      '#FFCC33'),
    ('title_tryhard',     'title', 'Tryhard',      'Trying, hard.',                                          1500, 'rare',      '#FF9933'),
    ('title_competitor',  'title', 'Competitor',   'Built for ranked.',                                      1500, 'rare',      '#AA88FF'),
    ('title_gold_rush',   'title', 'Gold Rush',    'Liquid gold, flowing.',                                  5000, 'legendary', '#FFD94D'),
    ('title_grandmaster', 'title', 'Grandmaster',  'Few reach it. Fewer afford the title.',                  5000, 'legendary', '#FF66EE'),
    ('title_clown',       'title', 'Clown',        'Honk honk.',                                             800,  'common',    '#FF6688'),
    ('title_regicide',    'title', 'Kingslayer',   'For those who earned the right. Still costs a fortune.', 3000, 'rare',      '#CC3366')
ON CONFLICT (sku) DO NOTHING;
