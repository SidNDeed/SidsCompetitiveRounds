-- 102: v1.29 features — rank/slayer titles, booster grants, rank role colors,
--      input-rate compare metrics.
-- Idempotent: safe to re-run.

-- ── Input-rate metrics (Compare tab: avg keystrokes/sec) ─────────────────
ALTER TABLE players ADD COLUMN IF NOT EXISTS keys_pressed_total  BIGINT           NOT NULL DEFAULT 0;
ALTER TABLE players ADD COLUMN IF NOT EXISTS active_seconds_total DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS local_keys_pressed   INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS local_active_seconds DOUBLE PRECISION;

-- ── Durable bug-report notifications (bug #38 / #30) ─────────────────────
-- Server-side delivery acks replace the bot's rolling time-window polls,
-- which dropped every DM/feed-post that landed during a bot restart.
ALTER TABLE bug_report_events ADD COLUMN IF NOT EXISTS notified_at TIMESTAMPTZ;
ALTER TABLE bug_reports       ADD COLUMN IF NOT EXISTS channel_posted_at TIMESTAMPTZ;
-- Backfill: everything that exists today counts as already-delivered so the
-- first ack-based poll doesn't re-broadcast weeks of history.
UPDATE bug_report_events SET notified_at = created_at WHERE notified_at IS NULL;
UPDATE bug_reports       SET channel_posted_at = created_at WHERE channel_posted_at IS NULL;

-- ── Discord rank-role colors (synced by the bot) ─────────────────────────
CREATE TABLE IF NOT EXISTS rank_role_colors (
    name       VARCHAR(48) PRIMARY KEY,
    color_hex  VARCHAR(16) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Monthly Discord-booster gold grants ──────────────────────────────────
CREATE TABLE IF NOT EXISTS booster_grants (
    id         BIGSERIAL PRIMARY KEY,
    discord_id VARCHAR(20) NOT NULL,
    player_id  UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    month      VARCHAR(7)  NOT NULL,   -- "2026-07"
    amount     INTEGER     NOT NULL,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_booster_grant_month UNIQUE (discord_id, month)
);

-- ── Titles ────────────────────────────────────────────────────────────────
-- Dynamic "Current Rank" title: free, visible in the shop, display text/color
-- resolved live from the player's rank tier by the API.
INSERT INTO shop_items (sku, kind, name, description, price, rarity, rotation_pool, preview_color)
SELECT 'title_rank', 'title', 'Current Rank',
       'Displays your live rank tier (updates automatically as you rank up or down)',
       0, 'rare', NULL, '#2ECC71'
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'title_rank');

-- Achievement-gated slayer titles: hidden from the shop (rotation_pool =
-- 'achievement'), granted automatically with their achievement.
INSERT INTO shop_items (sku, kind, name, description, price, rarity, rotation_pool, preview_color)
SELECT 'title_sid_slayer', 'title', 'Sid Slayer',
       'Beat Sid in a ranked series', 0, 'legendary', 'achievement', '#FF4655'
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'title_sid_slayer');

INSERT INTO shop_items (sku, kind, name, description, price, rarity, rotation_pool, preview_color)
SELECT 'title_stan_slayer', 'title', 'Stan Slayer',
       'Beat Stan in a ranked series', 0, 'legendary', 'achievement', '#00E5FF'
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'title_stan_slayer');

-- ── Backfills ─────────────────────────────────────────────────────────────
-- Everyone who already has the regicide achievement (now displayed as
-- "Sid Slayer") gets the matching title item.
INSERT INTO player_items (player_id, item_id, purchase_price)
SELECT pa.player_id, si.id, 0
  FROM player_achievements pa
  JOIN shop_items si ON si.sku = 'title_sid_slayer'
 WHERE pa.achievement_key = 'regicide'
ON CONFLICT DO NOTHING;

-- Stan Slayer backfill: everyone who has beaten Stan (76561198983423367) in a
-- completed ranked series gets the achievement + title retroactively.
INSERT INTO player_achievements (player_id, achievement_key, unlocked_at)
SELECT DISTINCT w.id, 'stan_slayer', NOW()
  FROM ranked_series rs
  JOIN players stan ON stan.steam_id = '76561198983423367'
  JOIN players w    ON w.id = rs.winner_id
 WHERE rs.status = 'completed'
   AND rs.winner_id IS NOT NULL
   AND rs.winner_id <> stan.id
   AND (rs.player1_id = stan.id OR rs.player2_id = stan.id)
ON CONFLICT (player_id, achievement_key) DO NOTHING;

INSERT INTO player_items (player_id, item_id, purchase_price)
SELECT pa.player_id, si.id, 0
  FROM player_achievements pa
  JOIN shop_items si ON si.sku = 'title_stan_slayer'
 WHERE pa.achievement_key = 'stan_slayer'
ON CONFLICT DO NOTHING;

-- Grand Master backfill: anyone whose current or peak 1v1/2v2 rating is
-- already past 2330 gets the achievement.
INSERT INTO player_achievements (player_id, achievement_key, unlocked_at)
SELECT q.player_id, 'grand_master', NOW()
  FROM (
    SELECT player_id FROM glicko_ratings     WHERE GREATEST(rating, COALESCE(peak_rating, rating)) >= 2330
    UNION
    SELECT player_id FROM glicko_ratings_2v2 WHERE GREATEST(rating, COALESCE(peak_rating, rating)) >= 2330
  ) q
ON CONFLICT (player_id, achievement_key) DO NOTHING;
