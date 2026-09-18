-- 337_demon_body_color.sql
--
-- One new body-color SKU, in the shape of 221_poison_body_color.sql: the
-- purple ROUNDS itself paints the Demonic Pact card with. Asked for after the
-- poison one; "Demon Wings" (CustomCosmetics.cs:134) is the community face
-- cosmetic this most likely pairs with, the way 221's was a poison face set.
--
-- Provenance of the hex, because it matters that this is not a guess. Unlike
-- Poison, Demonic Pact flashes nothing on a victim, so there is no RayHit*
-- color to read; the card's color is its THEME. Two serialized reads, both out
-- of the shipped assets and neither out of the decompile (#579 — a decompile
-- shows a MonoBehaviour's C# field DEFAULTS, not what the prefab ships):
--   1. "Demonic pact" prefab, sharedassets0.assets path_id 10145, CardInfo:
--      colorTheme = 4 = CardThemeColor.CardThemeColorType.EvilPurple.
--   2. CardChoice, level0 path_id 3810, cardThemes[] entry themeType=4:
--      targetColor = RGBA(0.4777, 0.3137, 0.8196, 1.0)  ->  #7A50D1
-- CardChoice.GetCardColor() is the accessor the game uses for that same field,
-- so this is the color the card is drawn with rather than a color near it.
--
-- Controls run on the same parse before trusting either read:
--   * A_Poison / RayHitPoison.color re-derives #4AD652 and A_Parasite #9E79FF
--     — the two values 221 recorded, reproduced byte for byte.
--   * colorTheme read across all 67 CardInfo objects spans the full enum 0-8
--     and lands where the card's look says it should (Cold bullets = ColdBlue,
--     Poison bullets = PoisonGreen, Tank = DefensiveBlue, Explosive bullet =
--     DestructiveRed). An earlier field offset that read 0 for all 67 cards was
--     rejected on exactly that: a reading that cannot vary is not a reading.
--   * The 9-row theme table self-checks — each themeType's targetColor is the
--     color its name claims (DestructiveRed #CC4646, PoisonGreen #00934C,
--     MagicPink #D15088).
--
-- Distance to what is already in the shop (CIELAB dE76, same metric 221 used —
-- the implementation reproduces 221's published poison numbers: Lime 24,
-- Emerald 31, Neon Lime 33, Forest 55). Nearest of the 38 body colors the
-- migrations seed (221's 37 plus Poison itself) is Amethyst #A442D6 at 17.2,
-- then Cobalt 19.8 and Sapphire 28.0. Amethyst is
-- the closest call in the set — it is a lighter, redder violet — but 17.2 is
-- past the "clearly different" line the earlier waves held to.
--
-- No client patch is required. PlayerColorCosmetic parses preview_color
-- directly for any non-special SKU: the hex travels as active_player_color_hex
-- (main.py, the player_color branch of the active-cosmetic lookup, reading
-- ShopItem.preview_color) and is parsed by PlayerColorCosmetic.ParseHex
-- (PlayerColorCosmetic.cs:786). Only pcolor_prismatic and pcolor_chrome are
-- special-cased (IsAnimatedSku, :503), and the shop's body glyph is generated
-- from the hex too (NativeUI.GetBodyGlyphSprite, :18058) — verified this pass,
-- not assumed from 221.
--
-- kind='player_color' is deliberately untouched by trg_gate_new_face_shop_item:
-- that trigger forces catalog_ready = FALSE only for kind='face', because a
-- face needs its PNG bundled into the client before it can render (migration
-- 148:348-365). A solid color has no art to ship, so the TRUE default is
-- correct and this item is live the moment the migration applies.
--
-- Pricing: 3000g / rare, following 054_player_colors.sql's solid-color block
-- (Amethyst is 3000/rare there, 054:21) and pcolor_poison (221, 3000/rare),
-- which is the direct precedent - a body color taken from an in-game effect,
-- same shape as this one.
--
-- NOT Twilight. An earlier version of this comment cited Twilight as a match;
-- it is 4000g (092_more_body_colors.sql:29). The whole 092 batch priced its
-- RARE colors at 4000 (bronze likewise), so rarity does not determine price
-- in this catalog and "3000g / rare" is not a tier that follows from the
-- label. 3000 is a choice to sit with 054/221 rather than with 092; check the
-- named rows, not the rarity, before pricing the next one.
--
-- Explicit transaction: the deploy wrapper invokes `psql -f`, which does NOT
-- wrap a file in one (#340) — every statement would otherwise autocommit and a
-- failed post-check would report a failed deploy over already-committed data.
-- Idempotent statement-by-statement, and the post-check asserts the end state
-- rather than trusting that the INSERT is what produced it.

BEGIN;

INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
    ('pcolor_demonic', 'player_color', 'Demonic',
     'The purple the Demonic Pact card is drawn in.',
     3000, 'rare', '#7A50D1')
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
     WHERE sku = 'pcolor_demonic';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'pcolor_demonic row is missing after the write';
    END IF;

    -- A pre-existing row would have made ON CONFLICT DO NOTHING a silent
    -- no-op, so verify the row we ended up with is the one intended.
    IF v_kind <> 'player_color' OR upper(COALESCE(v_hex, '')) <> '#7A50D1' THEN
        RAISE EXCEPTION
            'pcolor_demonic already existed as kind=% hex=% (expected player_color / #7A50D1)',
            v_kind, v_hex;
    END IF;

    -- Visibility invariants, re-read this pass rather than carried over from
    -- 221: list_shop_items (main.py, /api/v1/shop/items) filters on
    -- rotation_pool IS NULL AND catalog_ready, newest_shop_items
    -- (/api/v1/shop/newest) on the same pair, and the purchase path re-checks
    -- catalog_ready under its lock. rotation_pool is the achievement-gated
    -- pool. Either column set wrong makes the item unbuyable while the row
    -- looks perfectly fine in the table.
    IF NOT v_ready OR v_pool IS NOT NULL THEN
        RAISE EXCEPTION
            'pcolor_demonic would be hidden from the shop (catalog_ready=%, rotation_pool=%)',
            v_ready, v_pool;
    END IF;

    RAISE NOTICE 'post-check OK: pcolor_demonic live, hex % at %g', v_hex, v_price;
END $$;

COMMIT;
