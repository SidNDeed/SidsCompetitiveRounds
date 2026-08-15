-- 221_poison_body_color.sql
--
-- One new body-color SKU: the exact green ROUNDS' Poison card flashes on its
-- victims. Requested by a community artist building a poison-themed face set
-- (eyes / mouth / weeping) who wanted a body color to match it — none of the
-- 37 existing body colors is close. Forest shares the hue almost exactly
-- (126 deg vs 123 deg) but renders at half the brightness; Emerald leans
-- jade; Neon Lime and Lime lean yellow. Perceptual distance (CIELAB dE76)
-- from the poison green: Lime 24, Emerald 31, Neon Lime 33, Forest 55 —
-- all of them well past "clearly different".
--
-- Provenance of the hex, because it matters that this is not a guess: the
-- value is NOT RayHitPoison.color's field initializer (the decompile shows
-- `= Color.red`, which is a C# default, never the shipped value — the
-- serialized prefab data is ground truth for any tuned card value). It was
-- read out of the A_Poison prefab in ROUNDS_Data/sharedassets0.assets:
--     RGBA(0.2891, 0.8396, 0.3207, 1.0)  ->  #4AD652
-- Cross-check on the same parse: A_Parasite comes out #9E79FF, matching the
-- purple that card visibly uses in game, so the field offsets are right.
--
-- No client patch is required. PlayerColorCosmetic parses preview_color
-- directly for any non-special SKU — same as body-color waves 054 / 092 / 116.
--
-- kind='player_color' is deliberately untouched by trg_gate_new_face_shop_item:
-- that trigger forces catalog_ready = FALSE only for kind='face', because a
-- face needs its PNG bundled into the client before it can render (migration
-- 148). A solid color has no art to ship, so the TRUE default is correct and
-- this item is live the moment the migration applies.
--
-- Pricing follows the established solid-color tier: 3000g / rare, matching the
-- other solid greens (Forest, Olive, Lime).
--
-- Explicit transaction: the deploy wrapper invokes `psql -f`, which does NOT
-- wrap a file in one (every statement would otherwise autocommit and a failed
-- post-check would report a failed deploy over already-committed data).
-- Idempotent statement-by-statement: the wrapper's `||` fallback re-runs the
-- whole file on any nonzero exit, and the post-check asserts the end state
-- rather than trusting that the INSERT is what produced it.

BEGIN;

INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
    ('pcolor_poison', 'player_color', 'Poison',
     'The exact green a poison tick flashes on its victim.',
     3000, 'rare', '#4AD652')
ON CONFLICT (sku) DO NOTHING;

DO $$
DECLARE
    v_kind  TEXT;
    v_hex   TEXT;
    v_price INTEGER;
    v_ready BOOLEAN;
    v_pool  TEXT;
BEGIN
    SELECT kind, preview_color, price, catalog_ready, rotation_pool
      INTO v_kind, v_hex, v_price, v_ready, v_pool
      FROM shop_items
     WHERE sku = 'pcolor_poison';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'pcolor_poison row is missing after the write';
    END IF;

    -- A pre-existing row would have made ON CONFLICT DO NOTHING a silent
    -- no-op, so verify the row we ended up with is the one intended.
    IF v_kind <> 'player_color' OR upper(COALESCE(v_hex, '')) <> '#4AD652' THEN
        RAISE EXCEPTION
            'pcolor_poison already existed as kind=% hex=% (expected player_color / #4AD652)',
            v_kind, v_hex;
    END IF;

    -- Visibility invariants: list_shop_items and /shop/newest both require
    -- catalog_ready, and /shop/items excludes rotation_pool IS NOT NULL
    -- (that pool is for achievement-gated items). Either would make the
    -- item unbuyable while looking perfectly fine in the table.
    IF NOT v_ready OR v_pool IS NOT NULL THEN
        RAISE EXCEPTION
            'pcolor_poison would be hidden from the shop (catalog_ready=%, rotation_pool=%)',
            v_ready, v_pool;
    END IF;

    RAISE NOTICE 'post-check OK: pcolor_poison live, hex % at %g', v_hex, v_price;
END $$;

COMMIT;
