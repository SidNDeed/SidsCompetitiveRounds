-- v1.22.x — Remove broken Unicode-substitution font SKUs.
--
-- The 4 fonts introduced in 036 used Mathematical Alphanumeric Unicode codepoints
-- (U+1D4D0 etc). ROUNDS' TMP font fallback chain doesn't cover those ranges, so
-- every client — modded or not — sees them as boxes. Pulling them and deferring
-- "real fonts" to a future pass that uses runtime TMP_FontAsset creation + a
-- local-only font swap (no Unicode chars in the Photon NickName).
--
-- Safe to hard-DELETE since nobody owns any of them yet (verified via query).
-- If that ever changes in the future, use a refund-via-gold_transactions path.
--
-- Idempotent.

DELETE FROM shop_items WHERE sku IN (
    'nametag_font_sans_bold',
    'nametag_font_sans_italic',
    'nametag_font_monospace',
    'nametag_font_script'
);

-- Rename Highlight → Glow now that the implementation is a real TMP SDF shader glow
-- (NametagGlowRenderer clones the font material and enables GLOW_ON locally), not a
-- flat <mark> rectangle. SKU stays the same so no purchases are disrupted.
UPDATE shop_items SET name = 'Red Glow',   description = 'Red glow radiating from your name. Only visible to modded players.'
    WHERE sku = 'nametag_glow_red';
UPDATE shop_items SET name = 'Blue Glow',  description = 'Blue glow radiating from your name. Only visible to modded players.'
    WHERE sku = 'nametag_glow_blue';
UPDATE shop_items SET name = 'Gold Glow',  description = 'Gold glow radiating from your name. Only visible to modded players.'
    WHERE sku = 'nametag_glow_gold';
UPDATE shop_items SET name = 'Pink Glow',  description = 'Pink glow radiating from your name. Only visible to modded players.'
    WHERE sku = 'nametag_glow_pink';
