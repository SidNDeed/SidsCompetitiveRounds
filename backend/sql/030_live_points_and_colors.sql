-- v1.22.0 additions:
--   * Live point tracking on ranked_series so betting can lock at "first 2 points scored
--     in game 1" — sub-game-1 mystery preserved. Bet endpoint rejects when sum >= 2.
--   * map color shop kind: cosmetic preset for ROUNDS' Shift-cycle map art.
--   * players.active_color_id mirrors active_title_id / active_trail_id.
--
-- Idempotent.

ALTER TABLE ranked_series ADD COLUMN IF NOT EXISTS live_p1_points INTEGER NOT NULL DEFAULT 0;
ALTER TABLE ranked_series ADD COLUMN IF NOT EXISTS live_p2_points INTEGER NOT NULL DEFAULT 0;

ALTER TABLE players ADD COLUMN IF NOT EXISTS active_color_id BIGINT REFERENCES shop_items(id) ON DELETE SET NULL;

-- Initial map color presets. Cheap (75g) so everyone can afford a few. SKU stores the
-- ROUNDS art profile name we'll target. The actual list of in-game arts is exposed by
-- a one-time logging Harmony patch on ArtHandler.Awake — these are defensible defaults
-- that map to well-known background presets in the base game.
--
-- The first row, `mapcolor_default`, is a special "let the game pick randomly" sku that
-- tells the client to NOT override the Shift-cycle behavior — sold so users can revert.
INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
    ('mapcolor_default',  'color', 'Default (random)',  'Restore the vanilla random map color rotation.',                  0,    'common', '#888888'),
    ('mapcolor_soft',     'color', 'Soft Slate',        'Muted slate-gray theme — easy on the eyes.',                      75,   'common', '#5A6A78'),
    ('mapcolor_moss',     'color', 'Moss',              'Calm green moss palette.',                                        75,   'common', '#3F6B47'),
    ('mapcolor_cream',    'color', 'Cream',             'Warm cream + tan palette.',                                       75,   'common', '#D9C9A0'),
    ('mapcolor_lavender', 'color', 'Lavender',          'Soft lavender + violet — low-contrast.',                          75,   'common', '#9D8FBE'),
    ('mapcolor_dusk',     'color', 'Dusk',              'Deep dusk blues.',                                                75,   'common', '#3A4960'),
    ('mapcolor_sand',     'color', 'Sand',              'Warm desert sand tones.',                                         75,   'common', '#C8A67B'),
    ('mapcolor_mono',     'color', 'Monochrome',        'Pure greyscale — minimum visual distraction.',                    100,  'common', '#A0A0A0')
ON CONFLICT (sku) DO NOTHING;
