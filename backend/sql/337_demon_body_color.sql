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
-- Both reads are REPRODUCIBLE, not recorded:
-- backend/tests/reproduce_337_theme_color.py performs them against the
-- installed game and prints a result only if the controls below pass. It is
-- not a pytest because it needs the game's assets, which no test environment
-- is entitled to assume; run it before taking another body colour from a card
-- theme, and again if this hex is ever doubted. An earlier version of this
-- comment also cited a re-derivation of 221's poison values and a sweep of
-- every CardInfo in the file; neither is something this tree can repeat, so
-- neither is claimed here any more.
--
-- Controls, run on the same parse before either read is trusted:
--   * The 9-row theme table self-checks — each themeType's targetColor is the
--     color its name claims (DestructiveRed #CC4646, PoisonGreen #00934C,
--     MagicPink #D15088). The table is found by its SHAPE (a count of 9, then
--     nine records whose themeType is 0..8 and whose components are all in
--     [0,1]), never at a hardcoded offset.
--   * colorTheme lands where the card's own look says it should on four cards
--     named for their element: Poison bullets = PoisonGreen, Cold bullets =
--     ColdBlue, Tank = DefensiveBlue, Explosive bullet = DestructiveRed.
--   * The negative control for that offset: NOTHING in the script names the
--     component or the offset. It searches every component the five cards
--     share against every offset near the end of the record and requires
--     EXACTLY ONE pair whose int is a valid themeType on all five cards and
--     is not the same on all five — a reading that cannot vary is not a
--     reading. A second qualifying pair, which is what a neighbouring offset
--     that had started to vary would be, STOPS the run. The neighbours are
--     then reported and re-asserted constant in those terms. The five
--     path_ids above are what the run REPORTS, not what it is told: each
--     card is located by the name its GameObject carries in the asset.
--
-- Distance to what is already in the shop, CIELAB dE76 — the same metric 221
-- used. `reproduce_337_theme_color.py --distances` computes it, needs no game
-- assets, and reproduces 221's published poison numbers (Lime 24, Emerald 31,
-- Neon Lime 33, Forest 55) as its control before printing any number here.
-- Nearest of the 38 body colors the migrations seed (221's 37 plus Poison
-- itself) is Amethyst #A442D6 at 17.2, then Cobalt 19.8 and Sapphire 28.0.
-- Amethyst is the closest call in the set — it is a lighter, redder violet —
-- but 17.2 is past the "clearly different" line the earlier waves held to.
--
-- No client patch is required. PlayerColorCosmetic parses preview_color
-- directly for any non-special SKU: the hex travels as active_player_color_hex
-- (main.py, the player_color branch of the active-cosmetic lookup, reading
-- ShopItem.preview_color) and is parsed by PlayerColorCosmetic.ParseHex
-- (PlayerColorCosmetic.cs:786). Only pcolor_prismatic and pcolor_chrome are
-- special-cased (IsAnimatedSku, PlayerColorCosmetic.cs:503), and the shop's body glyph is generated
-- from the hex too (NativeUI.cs:18115, GetBodyGlyphSprite) — verified this pass,
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
    v_kind   TEXT;
    v_name   TEXT;
    v_desc   TEXT;
    v_hex    TEXT;
    v_price  INTEGER;
    v_rarity TEXT;
    v_ready  BOOLEAN;
    v_pool   TEXT;
    v_artist TEXT;
    v_stock  INTEGER;
BEGIN
    SELECT kind, name, description, preview_color, price, rarity,
           catalog_ready, rotation_pool, artist_steam_id, stock_limit
      INTO v_kind, v_name, v_desc, v_hex, v_price, v_rarity,
           v_ready, v_pool, v_artist, v_stock
      FROM shop_items
     WHERE sku = 'pcolor_demonic';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'pcolor_demonic row is missing after the write';
    END IF;

    -- A pre-existing row makes ON CONFLICT DO NOTHING a silent no-op, so the
    -- post-check verifies EVERY column this migration writes -- not only the
    -- ones that decide what the swatch looks like. A row that already
    -- existed at price 0, or under another name, or at the wrong rarity,
    -- passes a kind-and-hex check and then sells for nothing, or reads as
    -- something else in the shop, while the deploy reports success.
    IF v_kind <> 'player_color'
       OR upper(COALESCE(v_hex, '')) <> '#7A50D1'
       OR v_name <> 'Demonic'
       OR v_price <> 3000
       OR v_rarity <> 'rare'
       OR v_desc IS DISTINCT FROM 'The purple the Demonic Pact card is drawn in.'
    THEN
        RAISE EXCEPTION 'pcolor_demonic already existed as kind=% hex=% name=% price=% rarity=% description=% (expected player_color / #7A50D1 / Demonic / 3000 / rare)',
            v_kind, v_hex, v_name, v_price, v_rarity, v_desc;
    END IF;

    -- Ownership and stock, which are a different question from identity: a
    -- house colour is unowned and unlimited. A non-NULL artist_steam_id
    -- routes the row through the /artist stock, gift and block rules
    -- (migration 109), and stock_limit caps copies in circulation -- where
    -- -1 is the born-out-of-stock state migration 131 stamps, which nothing
    -- in this migration would ever clear. Either one leaves the item
    -- unbuyable or someone else's while the row looks perfectly fine.
    IF v_artist IS NOT NULL OR v_stock IS NOT NULL THEN
        RAISE EXCEPTION 'pcolor_demonic is not a plain house item (artist_steam_id=%, stock_limit=%)',
            v_artist, v_stock;
    END IF;

    -- Visibility invariants, re-read this pass rather than carried over from
    -- 221. list_shop_items (main.py, /api/v1/shop/items) filters on
    -- rotation_pool IS NULL AND catalog_ready, and the purchase path
    -- re-checks catalog_ready under its lock.
    --
    -- /api/v1/shop/newest is NOT a surface this row reaches. An earlier
    -- version of this comment presented it as one by saying it filters "on
    -- the same pair": newest_shop_items was narrowed to kind='face' plus the
    -- caller's supported music albums (Sept 2026), so a player_color never
    -- appears in the Home tab's newest panel. Expected, not a defect to
    -- chase later.
    --
    -- The two columns are not symmetric either. catalog_ready = FALSE makes
    -- the item invisible AND unbuyable, because the purchase path re-checks
    -- it. A non-NULL rotation_pool always hides it from the list, but only
    -- the literal 'achievement' refuses a PURCHASE (main.py:29315) -- any
    -- other non-NULL value would leave the item buyable by sku while nothing
    -- lists it. NULL is the only value this row may carry, which is what
    -- this check asserts: stricter than either endpoint, deliberately.
    IF NOT v_ready OR v_pool IS NOT NULL THEN
        RAISE EXCEPTION
            'pcolor_demonic would be hidden from the shop (catalog_ready=%, rotation_pool=%)',
            v_ready, v_pool;
    END IF;

    RAISE NOTICE 'post-check OK: pcolor_demonic live, hex % at %g', v_hex, v_price;
END $$;

COMMIT;
