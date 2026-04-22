-- v1.22.x — Nametag expansion: real font variants (Unicode substitution) + size subgroup,
-- and rename glows → highlights to better match what TMP <mark> actually renders (a flat
-- semi-transparent rectangle, not an emissive glow).
--
-- Subgroups added:
--   nametag_size_*  → single-active scale via TMP <size=NN%>
-- Fonts added (still in nametag_font_* subgroup, alongside ALL CAPS / SmAlLcApS / Spaced):
--   sans_bold, sans_italic, monospace, script — character-substituted via Unicode
--   Mathematical Alphanumeric ranges. Renders for everyone IF the player's TMP fallback
--   chain has those glyphs; otherwise shows as boxes. Documented in description.
--
-- Idempotent.

-- New size subgroup. <size=NN%> tags survive Photon NickName broadcast.
INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
    ('nametag_size_smaller', 'nametag', 'Smaller Name', 'Render your name at 80% size.',  100, 'common', '#FFFFFF'),
    ('nametag_size_bigger',  'nametag', 'Bigger Name',  'Render your name at 130% size.', 100, 'common', '#FFFFFF'),
    ('nametag_size_huge',    'nametag', 'Huge Name',    'Render your name at 160% size.', 100, 'common', '#FFFFFF')
ON CONFLICT (sku) DO NOTHING;

-- Unicode-substituted fonts. Each replaces ASCII letters with the corresponding glyph
-- from a Mathematical Alphanumeric range. May render as boxes on clients whose TMP
-- font asset chain doesn't cover the codepoints — there's no way to ship a real TMP
-- font asset via the BepInEx mod that would survive the Photon NickName roundtrip.
INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
    ('nametag_font_sans_bold',   'nametag', 'Sans Bold Font',   'Unicode font swap: bold sans-serif. May show as boxes on some clients.', 100, 'common', '#FFFFFF'),
    ('nametag_font_sans_italic', 'nametag', 'Sans Italic Font', 'Unicode font swap: italic sans-serif. May show as boxes on some clients.', 100, 'common', '#FFFFFF'),
    ('nametag_font_monospace',   'nametag', 'Monospace Font',   'Unicode font swap: fixed-width monospace. May show as boxes on some clients.', 100, 'common', '#FFFFFF'),
    ('nametag_font_script',      'nametag', 'Script Font',      'Unicode font swap: cursive bold script. May show as boxes on some clients.', 100, 'common', '#FFFFFF')
ON CONFLICT (sku) DO NOTHING;

-- Rename existing glows → highlights so the label matches what <mark> actually renders.
-- Existing purchases keep their item_id; only the display name + description text change.
UPDATE shop_items SET name = 'Red Highlight',  description = 'Red highlight rectangle behind your name.'
    WHERE sku = 'nametag_glow_red';
UPDATE shop_items SET name = 'Blue Highlight', description = 'Blue highlight rectangle behind your name.'
    WHERE sku = 'nametag_glow_blue';
UPDATE shop_items SET name = 'Gold Highlight', description = 'Gold highlight rectangle behind your name.'
    WHERE sku = 'nametag_glow_gold';
UPDATE shop_items SET name = 'Pink Highlight', description = 'Pink highlight rectangle behind your name.'
    WHERE sku = 'nametag_glow_pink';
