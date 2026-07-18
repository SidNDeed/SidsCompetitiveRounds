-- 131_shop_released_at.sql — July 17
--
-- Artist items are born out-of-stock (stock_limit = -1) and only become
-- visible in /shop/newest when the artist opens sales — but the Home tab's
-- "last two update batches" grouped by created_at, so an item opened days
-- after its migration competed as a STALE date and could never appear.
-- released_at = when the item actually became buyable. NULL means "was
-- never gated" — readers use COALESCE(released_at, created_at). The artist
-- set-stock endpoint stamps it on the first open from -1.

BEGIN;

ALTER TABLE shop_items ADD COLUMN IF NOT EXISTS released_at TIMESTAMPTZ;

COMMIT;
