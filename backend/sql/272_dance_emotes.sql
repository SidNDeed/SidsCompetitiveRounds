-- Dance emotes (Aug 31 item 5): a new buyable cosmetic category. The client
-- (>= DANCES_MIN_VERSION) renders these under a DANCES shop section, previews
-- them with a choreography-driven puppet, and plays them via the hold-E wheel
-- between rounds.
--
-- Rows are born catalog_ready = FALSE (the #163 pattern) and migration 273
-- flips them TRUE. This makes the rollout ORDER-IMMUNE (round-2 review
-- blocker 2): the OLD api's list/newest queries already filter
-- catalog_ready, so applying this migration while the old api is still live
-- exposes nothing — an old client can neither see nor buy a dance it could
-- never use. The NEW api additionally version-gates kind='dance' rows away
-- from pre-dance clients (DANCES_MIN_VERSION in main.py), which is what
-- carries the guarantee after 273 flips the rows on.
-- Prices are Sid's knobs. Idempotent - ON CONFLICT (sku) DO NOTHING.

BEGIN;

INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color, catalog_ready) VALUES
    ('dance_bounce', 'dance', 'The Bounce', 'Hop to the beat, arms pumping. Play it between rounds with the E wheel.', 3000, 'rare',      '#FFC8F0', FALSE),
    ('dance_wave',   'dance', 'The Wave',   'Sway and wave to the crowd. Play it between rounds with the E wheel.',    4000, 'legendary', '#FFC8F0', FALSE)
ON CONFLICT (sku) DO NOTHING;

COMMIT;
