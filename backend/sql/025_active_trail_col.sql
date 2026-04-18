-- 025_active_trail_col.sql
-- Active trail selection. Parallels active_title_id. Set-active rejects items
-- the player doesn't own just like titles do.

ALTER TABLE players
    ADD COLUMN IF NOT EXISTS active_trail_id BIGINT REFERENCES shop_items(id) ON DELETE SET NULL;
