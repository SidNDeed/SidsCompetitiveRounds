-- 129_pending_dms.sql — July 17
--
-- Generic bot DM queue: a row is a one-off DM to a linked player, drained by
-- the bot every 60s with the durable ack pattern (same shape as
-- tournament_notices / pending_channel_posts — learning #105 family).
-- Insert a row, the bot DMs the player and stamps delivered_at (or flags
-- undeliverable for unlinked/closed-DM players so the poll doesn't starve).
--
-- Seeded with one DM to lopidav about the Sprout cosmetic art fix.

BEGIN;

CREATE TABLE IF NOT EXISTS pending_dms (
    id            BIGSERIAL PRIMARY KEY,
    steam_id      VARCHAR(20) NOT NULL,
    content       TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at  TIMESTAMPTZ,
    undeliverable BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS idx_pending_dms_pending
    ON pending_dms(created_at) WHERE delivered_at IS NULL AND NOT undeliverable;

INSERT INTO pending_dms (steam_id, content) VALUES
  ('76561198041616199',
   'Hey lopidav — about your Sprout cosmetic: when it first shipped, the art went through a conversion step to fit the game''s sprite format, and instead of using your file directly it ended up as a close recreation. Sorry about that — you sent finished art and it should have been used as-is. The next mod update replaces it with your exact original file, pixel for pixel. Thanks for the art, and for flagging it. — Sid');

-- Sanity output
SELECT id, steam_id, delivered_at FROM pending_dms ORDER BY id;

COMMIT;
