-- v1.23.x — Shelve custom typefaces and glows.
--
-- Neither feature reached a shipping state:
--   * Typefaces (22 OFL fonts, migration 041): Unity's AssetBundle pipeline produces
--     bundles only compatible with the exact Unity build that made them. ROUNDS runs
--     on a Unity 2022.3.34f1 build that is no longer available on Unity's archive page
--     (Unity re-released the label with a different git hash). Bundles built with the
--     current archive version fail to load with "AssetBundle ... not compatible with
--     this newer version of the Unity runtime" regardless of serialization-option tweaks.
--     Two sessions of in-game testing confirmed zero typefaces rendered for any player.
--   * Glows (4 SKUs from migration 035): ROUNDS' TMP shader variants have GLOW_ON and
--     UNDERLAY_ON samplers stripped at build time. Setting the keywords + properties on
--     cloned materials has no rendering effect — only outline renders (confirmed by
--     logs where _OutlineWidth took effect but _GlowColor was ignored). A "halo" glow
--     is not achievable with the shaders available at runtime.
--
-- This migration removes both feature SKUs from the shop, refunds every purchase, and
-- strips the items from active nametag styles. The feature code (NametagFontRenderer,
-- NametagGlowRenderer, AssetBundle loader, unity-font-bundler project) stays in-repo
-- as infrastructure for future attempts — see docs/typeface-glow-shelved.md for what
-- was tried and what to revisit if the pipeline becomes viable.
--
-- Idempotent: re-running after success is a no-op.

-- 1. Post a refund transaction for every purchase of a shelved sku.
INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
SELECT pi.player_id, pi.purchase_price, 'refund_feature_shelved', si.sku
  FROM player_items pi
  JOIN shop_items si ON si.id = pi.item_id
 WHERE si.sku LIKE 'nametag_typeface_%'
    OR si.sku IN ('nametag_glow_red', 'nametag_glow_blue',
                  'nametag_glow_gold', 'nametag_glow_pink');

-- 2. Clamp gold_spent back down by the sum of refunds per player.
UPDATE players p
   SET gold_spent = GREATEST(0, p.gold_spent - refund.total_refund)
  FROM (
      SELECT pi.player_id, SUM(pi.purchase_price) AS total_refund
        FROM player_items pi
        JOIN shop_items si ON si.id = pi.item_id
       WHERE si.sku LIKE 'nametag_typeface_%'
          OR si.sku IN ('nametag_glow_red', 'nametag_glow_blue',
                        'nametag_glow_gold', 'nametag_glow_pink')
    GROUP BY pi.player_id
  ) refund
 WHERE p.id = refund.player_id;

-- 3. Strip the shelved skus from every player's active_nametag_skus array (stored as
--    shop_items.id in nametag_style_ids — the array must not hold dangling ids after
--    the shop rows get deleted).
UPDATE players
   SET nametag_style_ids = (
       SELECT COALESCE(array_agg(x), ARRAY[]::bigint[])
         FROM unnest(nametag_style_ids) x
        WHERE x NOT IN (
            SELECT id FROM shop_items
             WHERE sku LIKE 'nametag_typeface_%'
                OR sku IN ('nametag_glow_red', 'nametag_glow_blue',
                           'nametag_glow_gold', 'nametag_glow_pink')
        )
   )
 WHERE nametag_style_ids && (
       SELECT COALESCE(array_agg(id), ARRAY[]::bigint[]) FROM shop_items
        WHERE sku LIKE 'nametag_typeface_%'
           OR sku IN ('nametag_glow_red', 'nametag_glow_blue',
                      'nametag_glow_gold', 'nametag_glow_pink')
 );

-- 4. Drop inventory rows for the shelved skus.
DELETE FROM player_items
 WHERE item_id IN (
   SELECT id FROM shop_items
    WHERE sku LIKE 'nametag_typeface_%'
       OR sku IN ('nametag_glow_red', 'nametag_glow_blue',
                  'nametag_glow_gold', 'nametag_glow_pink')
 );

-- 5. Delete the shop rows themselves.
DELETE FROM shop_items
 WHERE sku LIKE 'nametag_typeface_%'
    OR sku IN ('nametag_glow_red', 'nametag_glow_blue',
               'nametag_glow_gold', 'nametag_glow_pink');
