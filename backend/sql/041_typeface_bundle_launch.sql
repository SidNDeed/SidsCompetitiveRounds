-- v1.23.x — Replace broken OS-font typefaces with the pre-baked OFL font bundle.
--
-- Context: the 5 typefaces from migration 039 (impact, segoe, papyrus, comic, courier)
-- tried to create TMP_FontAssets from Unity's OS-font API at runtime. Logs confirmed
-- this fails with "Unable to load font face for [Papyrus]" — Unity explicitly documents
-- that dynamic OS fonts are incompatible with TMP's SDF pipeline. Zero players ever saw
-- the font render visually.
--
-- Resolution: ship TMP_FontAssets pre-baked in Unity Editor (unity-font-bundler/)
-- inside an AssetBundle the mod loads at runtime. 22 OFL-licensed fonts across 11
-- distinct visual styles (cursive, gothic, retro-game, horror, western, newspaper-serif,
-- 3D/arcade, handwritten, typewriter, sci-fi, graffiti).
--
-- This migration:
--   1. Refunds every purchase of the 5 broken SKUs as a gold_transactions row, reduces
--      the buyer's gold_spent, and removes the items from their inventories and active
--      style lists.
--   2. Deletes the broken shop rows.
--   3. Inserts the 22 new SKUs with tiered rarity + pricing:
--        3 common (100g), 8 uncommon (150g), 7 rare (250g), 4 legendary (500g).
--
-- Idempotent: re-running after a successful apply is a no-op (DELETEs see empty sets,
-- INSERT uses ON CONFLICT DO NOTHING).

-- Step 1a: post a refund transaction for each legacy-typeface purchase.
INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
SELECT pi.player_id, pi.purchase_price, 'refund_feature_removed', si.sku
  FROM player_items pi
  JOIN shop_items si ON si.id = pi.item_id
 WHERE si.sku IN ('nametag_typeface_impact','nametag_typeface_segoe',
                  'nametag_typeface_papyrus','nametag_typeface_comic',
                  'nametag_typeface_courier');

-- Step 1b: clamp gold_spent back down by the sum of those refunds.
UPDATE players p
   SET gold_spent = GREATEST(0, p.gold_spent - refund.total_refund)
  FROM (
      SELECT pi.player_id, SUM(pi.purchase_price) AS total_refund
        FROM player_items pi
        JOIN shop_items si ON si.id = pi.item_id
       WHERE si.sku IN ('nametag_typeface_impact','nametag_typeface_segoe',
                        'nametag_typeface_papyrus','nametag_typeface_comic',
                        'nametag_typeface_courier')
    GROUP BY pi.player_id
  ) refund
 WHERE p.id = refund.player_id;

-- Step 1c: strip the refunded items from every player's active nametag styles before
-- we delete the shop_items row (otherwise the FK would stop us or the array would hold
-- dangling ids).
UPDATE players
   SET nametag_style_ids = (
       SELECT COALESCE(array_agg(x), ARRAY[]::bigint[])
         FROM unnest(nametag_style_ids) x
        WHERE x NOT IN (
            SELECT id FROM shop_items
             WHERE sku IN ('nametag_typeface_impact','nametag_typeface_segoe',
                           'nametag_typeface_papyrus','nametag_typeface_comic',
                           'nametag_typeface_courier')
        )
   )
 WHERE nametag_style_ids && (
       SELECT COALESCE(array_agg(id), ARRAY[]::bigint[]) FROM shop_items
        WHERE sku IN ('nametag_typeface_impact','nametag_typeface_segoe',
                      'nametag_typeface_papyrus','nametag_typeface_comic',
                      'nametag_typeface_courier')
 );

-- Step 1d: remove inventory rows.
DELETE FROM player_items
 WHERE item_id IN (
   SELECT id FROM shop_items
    WHERE sku IN ('nametag_typeface_impact','nametag_typeface_segoe',
                  'nametag_typeface_papyrus','nametag_typeface_comic',
                  'nametag_typeface_courier')
 );

-- Step 2: delete the broken shop rows.
DELETE FROM shop_items
 WHERE sku IN ('nametag_typeface_impact','nametag_typeface_segoe',
               'nametag_typeface_papyrus','nametag_typeface_comic',
               'nametag_typeface_courier');

-- Step 3: insert the 22 new SKUs.
INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
    -- COMMON (100g)
    ('nametag_typeface_caveat',          'nametag', 'Caveat Font',          'Casual pen-written cursive. Visible to modded players.',         100, 'common',    '#FFFFFF'),
    ('nametag_typeface_permanentmarker', 'nametag', 'Permanent Marker',     'Sharpie-scrawl handwriting. Visible to modded players.',         100, 'common',    '#FFFFFF'),
    ('nametag_typeface_courierprime',    'nametag', 'Courier Prime',        'Clean typewriter monospace. Visible to modded players.',        100, 'common',    '#FFFFFF'),
    -- UNCOMMON (150g)
    ('nametag_typeface_pacifico',        'nametag', 'Pacifico Script',      'Retro surf-shop cursive. Visible to modded players.',           150, 'uncommon',  '#FFFFFF'),
    ('nametag_typeface_playfairdisplay', 'nametag', 'Playfair Display',     'Elegant editorial serif. Visible to modded players.',           150, 'uncommon',  '#FFFFFF'),
    ('nametag_typeface_specialelite',    'nametag', 'Special Elite',        'Beat-up distressed typewriter. Visible to modded players.',     150, 'uncommon',  '#FFFFFF'),
    ('nametag_typeface_vt323',           'nametag', 'VT323 Terminal',       'Old CRT monitor monospace. Visible to modded players.',         150, 'uncommon',  '#FFFFFF'),
    ('nametag_typeface_medievalsharp',   'nametag', 'MedievalSharp',        'Fantasy / medieval manuscript. Visible to modded players.',     150, 'uncommon',  '#FFFFFF'),
    ('nametag_typeface_smokum',          'nametag', 'Smokum',               'Cowboy slab serif. Visible to modded players.',                 150, 'uncommon',  '#FFFFFF'),
    ('nametag_typeface_rye',             'nametag', 'Rye',                  'Wild-west saloon wood-cut. Visible to modded players.',         150, 'uncommon',  '#FFFFFF'),
    ('nametag_typeface_orbitron',        'nametag', 'Orbitron',             'Sci-fi geometric sans. Visible to modded players.',             150, 'uncommon',  '#FFFFFF'),
    -- RARE (250g)
    ('nametag_typeface_greatvibes',        'nametag', 'Great Vibes',          'Ultra-fancy wedding calligraphy. Visible to modded players.',   250, 'rare',      '#FFFFFF'),
    ('nametag_typeface_cinzeldecorative',  'nametag', 'Cinzel Decorative',    'Roman inscription with flourishes. Visible to modded players.', 250, 'rare',      '#FFFFFF'),
    ('nametag_typeface_pressstart2p',      'nametag', 'Press Start 2P',       'Classic 8-bit NES pixel font. Visible to modded players.',      250, 'rare',      '#FFFFFF'),
    ('nametag_typeface_audiowide',         'nametag', 'Audiowide',            'Retro-futurist display. Visible to modded players.',            250, 'rare',      '#FFFFFF'),
    ('nametag_typeface_monoton',           'nametag', 'Monoton',              'Concentric-stripe disco. Visible to modded players.',           250, 'rare',      '#FFFFFF'),
    ('nametag_typeface_bungeeshade',       'nametag', 'Bungee Shade',         '3D layered bubble letters. Visible to modded players.',         250, 'rare',      '#FFFFFF'),
    ('nametag_typeface_metalmania',        'nametag', 'Metal Mania',          'Cracked distressed metal. Visible to modded players.',          250, 'rare',      '#FFFFFF'),
    -- LEGENDARY (500g)
    ('nametag_typeface_unifrakturmaguntia','nametag', 'UnifrakturMaguntia',   'Gothic blackletter (NYT-masthead style). Visible to modded players.', 500, 'legendary', '#FFFFFF'),
    ('nametag_typeface_creepster',         'nametag', 'Creepster',            'Dripping blood horror letters. Visible to modded players.',     500, 'legendary', '#FFFFFF'),
    ('nametag_typeface_rubikpuddles',      'nametag', 'Rubik Puddles',        'Liquid graffiti drip. Visible to modded players.',              500, 'legendary', '#FFFFFF'),
    ('nametag_typeface_rubikmarkerhatch',  'nametag', 'Rubik Marker Hatch',   'Crosshatched marker strokes. Visible to modded players.',       500, 'legendary', '#FFFFFF')
ON CONFLICT (sku) DO NOTHING;
