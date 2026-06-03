-- 098_cursor_effects_hidegold.sql
--
-- v1.28 shop expansion + owner auto-grant support.
--
-- New cosmetic kinds:
--   'cursor_color'  — recolors the player's in-menu mouse cursor. Single-equip,
--                     local-only render (Cursor.SetCursor with a procedurally
--                     tinted arrow). Cheap. Column players.active_cursor_color_id.
--   'player_effect' — in-match particle aura on the player body, cross-visible
--                     via Photon custom prop cr_effect_sku. Single-equip. Column
--                     players.active_player_effect_id. Client renders procedural
--                     ParticleSystems keyed by sku (see PlayerEffectCosmetic.cs).
--
-- New utility item:
--   'utility' kind, sku 'util_hide_gold' (10000g). Buying it unlocks the ability
--   to hide your gold on the leaderboard. The toggle state lives in
--   players.hide_gold (default false); the /hide-gold endpoint flips it and
--   requires ownership. When hide_gold is true the leaderboard returns the gold
--   field as -1 (client renders "Hidden"); the player still sees their own real
--   balance in the Shop / stats panel.
--
-- Owner auto-grant is implemented server-side (main.py treats SHOP_OWNER_STEAM_IDS
-- as owning every item) so no per-item player_items rows are needed for Sid.
--
-- Idempotent — safe to re-run.

-- ── New player columns ──────────────────────────────────────────
ALTER TABLE players
    ADD COLUMN IF NOT EXISTS active_cursor_color_id BIGINT
        REFERENCES shop_items(id) ON DELETE SET NULL;

ALTER TABLE players
    ADD COLUMN IF NOT EXISTS active_player_effect_id BIGINT
        REFERENCES shop_items(id) ON DELETE SET NULL;

ALTER TABLE players
    ADD COLUMN IF NOT EXISTS hide_gold BOOLEAN NOT NULL DEFAULT FALSE;


-- ── Cursor colors (kind='cursor_color') @ 150g ──────────────────
-- Cheap collectible recolors of the menu cursor. preview_color is the cursor tint.
INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
    ('cursor_red',     'cursor_color', 'Red Cursor',     'A bold red mouse cursor.',          150, 'common', '#E8413C'),
    ('cursor_orange',  'cursor_color', 'Orange Cursor',  'A bright orange mouse cursor.',     150, 'common', '#F08A24'),
    ('cursor_yellow',  'cursor_color', 'Yellow Cursor',  'A sunny yellow mouse cursor.',      150, 'common', '#F5D636'),
    ('cursor_green',   'cursor_color', 'Green Cursor',   'A vivid green mouse cursor.',       150, 'common', '#46C84A'),
    ('cursor_cyan',    'cursor_color', 'Cyan Cursor',    'A cool cyan mouse cursor.',         150, 'common', '#34D6D6'),
    ('cursor_blue',    'cursor_color', 'Blue Cursor',    'A deep blue mouse cursor.',         150, 'common', '#3C7BE8'),
    ('cursor_purple',  'cursor_color', 'Purple Cursor',  'A royal purple mouse cursor.',      150, 'common', '#9B47E0'),
    ('cursor_pink',    'cursor_color', 'Pink Cursor',    'A hot pink mouse cursor.',          150, 'common', '#F25BB0'),
    ('cursor_white',   'cursor_color', 'White Cursor',   'A clean white mouse cursor.',       150, 'common', '#F0F0F0'),
    ('cursor_black',   'cursor_color', 'Black Cursor',   'A sleek black mouse cursor.',       150, 'common', '#202024')
ON CONFLICT (sku) DO NOTHING;


-- ── Player effects (kind='player_effect') ───────────────────────
-- In-match particle auras. Client renders each sku procedurally (PlayerEffectCosmetic).
-- preview_color drives the shop swatch + the dominant particle tint.
INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
    ('effect_smoke',    'player_effect', 'Smoking',      'Wisps of grey smoke drift off your body.',                4000, 'epic',      '#8A8A92'),
    ('effect_clover',   'player_effect', 'Lucky Clover', 'Lucky green clovers tumble around you.',                   4000, 'epic',      '#3FB552'),
    ('effect_hearts',   'player_effect', 'Hearts',       'Floating pink hearts rise from your body.',               4000, 'epic',      '#F25B95'),
    ('effect_bubbles',  'player_effect', 'Bubbles',      'Gentle soap bubbles float up around you.',                4000, 'epic',      '#7FC8F0'),
    ('effect_embers',   'player_effect', 'Embers',       'Glowing fire embers crackle and rise.',                   5000, 'epic',      '#F0792A'),
    ('effect_sparks',   'player_effect', 'Sparks',       'Electric sparks snap and dart around you.',               5000, 'epic',      '#F5E14A'),
    ('effect_rainbow',  'player_effect', 'Rainbow Aura', 'A shimmering rainbow of particles cycles around you.',    8000, 'legendary', '#FF5FD0'),
    ('effect_void',     'player_effect', 'Void',         'Cold violet and cyan motes swirl in a dark halo.',        8000, 'legendary', '#9B5BE0')
ON CONFLICT (sku) DO NOTHING;


-- ── Hide-gold utility (kind='utility') @ 10000g ─────────────────
INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
    ('util_hide_gold', 'utility', 'Hide Gold', 'Hide your gold balance from everyone on the leaderboard. Toggle it on or off any time from the Other tab.', 10000, 'legendary', '#FFD94D')
ON CONFLICT (sku) DO NOTHING;
