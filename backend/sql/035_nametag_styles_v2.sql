-- v1.22.x — Nametag shop expansion.
--
-- Adds three new subgroups within kind='nametag', distinguished by SKU prefix. The
-- server's toggle endpoint reads the prefix to decide whether the item is stackable
-- (bold/italic/underline/strike — no prefix) or single-active within its subgroup:
--
--   nametag_color_* → one color active at a time (replaces any currently-equipped color)
--   nametag_glow_*  → one glow active at a time (TMP <mark> highlight rectangle)
--   nametag_font_*  → one font-style transform active at a time
--
-- All stack with the existing 4 formatting styles. Max possible simultaneous active
-- items on a single player: 4 stackable + 1 color + 1 glow + 1 font-style = 7.
--
-- Price: 100g each across the board. Keeps the shop predictable — if the user sees a
-- nametag option they want, the price is always the same, regardless of subgroup.
--
-- Idempotent.

INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
    -- Colors (6). Rich-text <color=#RRGGBB> wrap — renders for modded AND non-modded
    -- opponents since ROUNDS' player-name TMP labels parse inline color tags.
    ('nametag_color_red',    'nametag', 'Red Name',    'Colorize your name in red.',    100, 'common', '#FF5566'),
    ('nametag_color_cyan',   'nametag', 'Cyan Name',   'Colorize your name in cyan.',   100, 'common', '#55CCFF'),
    ('nametag_color_gold',   'nametag', 'Gold Name',   'Colorize your name in gold.',   100, 'common', '#FFCC44'),
    ('nametag_color_purple', 'nametag', 'Purple Name', 'Colorize your name in purple.', 100, 'common', '#BB88FF'),
    ('nametag_color_green',  'nametag', 'Green Name',  'Colorize your name in green.',  100, 'common', '#77DD88'),
    ('nametag_color_pink',   'nametag', 'Pink Name',   'Colorize your name in pink.',   100, 'common', '#FF99CC'),

    -- Glows (4). Semi-transparent <mark> highlight rectangle behind the name.
    -- Best approximation of "glow" we can get using TMP rich text alone (an outline or
    -- emissive requires a custom material, which wouldn't propagate via NickName).
    ('nametag_glow_red',   'nametag', 'Red Glow',   'Soft red highlight behind your name.',   100, 'common', '#FF4455'),
    ('nametag_glow_blue',  'nametag', 'Blue Glow',  'Soft blue highlight behind your name.',  100, 'common', '#4488FF'),
    ('nametag_glow_gold',  'nametag', 'Gold Glow',  'Soft gold highlight behind your name.',  100, 'common', '#FFCC44'),
    ('nametag_glow_pink',  'nametag', 'Pink Glow',  'Soft pink highlight behind your name.',  100, 'common', '#FF88CC'),

    -- Font-style transforms (3). These reshape the existing SDF glyphs — no new font
    -- asset required, so they survive the Photon NickName roundtrip cleanly.
    ('nametag_font_caps',      'nametag', 'ALL CAPS',    'Force your name to render uppercase.',              100, 'common', '#FFFFFF'),
    ('nametag_font_smallcaps', 'nametag', 'SmAlLcApS',   'Lowercase letters render as smaller capitals.',     100, 'common', '#FFFFFF'),
    ('nametag_font_spaced',    'nametag', 'S p a c e d', 'Add extra character spacing.',                       100, 'common', '#FFFFFF')
ON CONFLICT (sku) DO NOTHING;
