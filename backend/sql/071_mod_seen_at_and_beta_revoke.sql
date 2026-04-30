-- v1.25.25: differentiate actual mod users from passive opponent records
-- and clean up the over-broad Beta-title backfill.
--
-- Migration 069 granted Beta to every player row, but the players table
-- includes folks who only got recorded as casual opponents (auto-created
-- in get_or_create_player when their match was reported by someone else).
-- Those people don't have the mod installed and shouldn't carry the Beta
-- title. New `mod_seen_at` column is the durable signal.

ALTER TABLE players
    ADD COLUMN IF NOT EXISTS mod_seen_at TIMESTAMP WITH TIME ZONE;

-- Backfill mod_seen_at for any player who has clearly used the mod's
-- own client-side flows. These signals can ONLY be set by the mod, never
-- by the auto-create path:
--   ranked_enabled = TRUE          -> player toggled ranked on (mod UI)
--   discord_id IS NOT NULL         -> player ran !link from in-game
--   gold_spent > 0                 -> player bought a shop item (mod UI)
--   active_player_color_id NOT NULL -> equipped body color (mod purchase)
--   active_trail_id NOT NULL       -> equipped trail
--   active_color_id NOT NULL       -> legacy single-color slot
--   nametag_style_ids non-empty    -> equipped nametag style
--   has any non-Beta player_item   -> already owned/bought something else
UPDATE players p
   SET mod_seen_at = COALESCE(p.last_seen, NOW())
 WHERE p.mod_seen_at IS NULL
   AND p.deleted_at IS NULL
   AND (
        p.ranked_enabled = TRUE
     OR p.discord_id IS NOT NULL
     OR p.gold_spent > 0
     OR p.active_player_color_id IS NOT NULL
     OR p.active_trail_id IS NOT NULL
     OR p.active_color_id IS NOT NULL
     OR cardinality(COALESCE(p.nametag_style_ids, '{}'::bigint[])) > 0
     OR cardinality(COALESCE(p.active_color_ids,  '{}'::bigint[])) > 0
     OR EXISTS (
            SELECT 1 FROM player_items pi
              JOIN shop_items si ON si.id = pi.item_id
             WHERE pi.player_id = p.id
               AND si.sku <> 'title_beta'
        )
   );

-- Revoke the Beta grant from anyone who hasn't signaled mod-installed.
-- Two-step: clear active_title_id if it pointed at Beta, then delete the
-- player_items row that owned the Beta entitlement.
WITH beta AS (SELECT id FROM shop_items WHERE sku = 'title_beta')
UPDATE players p
   SET active_title_id = NULL
  FROM beta
 WHERE p.active_title_id = beta.id
   AND p.mod_seen_at IS NULL
   AND p.deleted_at IS NULL;

DELETE FROM player_items pi
 USING shop_items si, players p
 WHERE pi.item_id = si.id
   AND pi.player_id = p.id
   AND si.sku = 'title_beta'
   AND p.mod_seen_at IS NULL
   AND p.deleted_at IS NULL;
