-- v1.22.1 — fix the map color shop SKUs that mapped to non-existent ROUNDS art names.
--
-- v1.22.0 shipped guessed names ('Soft', 'Moss', etc.) that SetSpecificArt couldn't match.
-- The Harmony prefix returned false anyway, so no art got applied → invisible map.
--
-- This migration:
--   1. Refunds the gold of anyone who bought a non-default broken color (gold_earned += price,
--      logged via gold_transactions for traceability).
--   2. Clears active_color_id for everyone using one of the broken SKUs.
--   3. Deletes the broken SKUs (CASCADE removes player_items rows).
--   4. Inserts new SKUs mapped to actual ROUNDS art profile names: Sweden, Gold, Soviet,
--      Poison, Sky, Rainbow. RainbowSequence is a hectic mid-game cycler — skipped.
--   5. Keeps mapcolor_default unchanged (free 0g entry that disables the override).
--
-- Idempotent — guards each step. Safe to re-run.

-- 1. Refund + log transactions for current owners of broken SKUs.
INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
SELECT pi.player_id, si.price, 'refund', si.sku
FROM player_items pi
JOIN shop_items si ON si.id = pi.item_id
WHERE si.kind = 'color'
  AND si.sku IN ('mapcolor_soft','mapcolor_moss','mapcolor_cream','mapcolor_lavender',
                 'mapcolor_dusk','mapcolor_sand','mapcolor_mono');

UPDATE players p
SET gold_earned = p.gold_earned + (
    SELECT COALESCE(SUM(si.price), 0)
    FROM player_items pi
    JOIN shop_items si ON si.id = pi.item_id
    WHERE pi.player_id = p.id
      AND si.kind = 'color'
      AND si.sku IN ('mapcolor_soft','mapcolor_moss','mapcolor_cream','mapcolor_lavender',
                     'mapcolor_dusk','mapcolor_sand','mapcolor_mono')
)
WHERE EXISTS (
    SELECT 1 FROM player_items pi
    JOIN shop_items si ON si.id = pi.item_id
    WHERE pi.player_id = p.id
      AND si.kind = 'color'
      AND si.sku IN ('mapcolor_soft','mapcolor_moss','mapcolor_cream','mapcolor_lavender',
                     'mapcolor_dusk','mapcolor_sand','mapcolor_mono')
);

-- 2. Clear anyone whose active color is one of the broken SKUs.
UPDATE players SET active_color_id = NULL
WHERE active_color_id IN (
    SELECT id FROM shop_items WHERE kind = 'color'
      AND sku IN ('mapcolor_soft','mapcolor_moss','mapcolor_cream','mapcolor_lavender',
                  'mapcolor_dusk','mapcolor_sand','mapcolor_mono')
);

-- 3. Delete the broken SKUs (CASCADE removes player_items entries).
DELETE FROM shop_items WHERE kind = 'color'
  AND sku IN ('mapcolor_soft','mapcolor_moss','mapcolor_cream','mapcolor_lavender',
              'mapcolor_dusk','mapcolor_sand','mapcolor_mono');

-- 4. Insert new SKUs mapped to ACTUAL ROUNDS art names from the Awake-postfix log:
--      arts[0..8] = RainbowSequence, Rainbow, Sweden, Gold, Soviet, Poison, Gold, Sky, Poison
--    The dupes are intentional in vanilla (some maps prefer one over another). Sweden
--    is the closest thing to "calm" — blue/yellow with reasonable contrast.
INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
    ('mapcolor_sweden',  'color', 'Sweden',  'Locks the map to ROUNDS'' Sweden palette (blue + yellow).',  75, 'common', '#2A6FCB'),
    ('mapcolor_sky',     'color', 'Sky',     'Locks the map to ROUNDS'' Sky palette (light blue).',         75, 'common', '#7FC9F4'),
    ('mapcolor_poison',  'color', 'Poison',  'Locks the map to ROUNDS'' Poison palette (acid green).',      75, 'common', '#5DD05A'),
    ('mapcolor_gold',    'color', 'Gold',    'Locks the map to ROUNDS'' Gold palette (warm yellow).',       75, 'common', '#E0B842'),
    ('mapcolor_soviet',  'color', 'Soviet',  'Locks the map to ROUNDS'' Soviet palette (deep red).',        75, 'common', '#C83232'),
    ('mapcolor_rainbow', 'color', 'Rainbow', 'Locks the map to ROUNDS'' Rainbow palette.',                  75, 'common', '#FF66EE')
ON CONFLICT (sku) DO NOTHING;
