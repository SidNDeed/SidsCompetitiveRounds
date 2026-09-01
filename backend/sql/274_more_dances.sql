-- Six more dances (Sid, Sep 1: "add more unique dances ... go a bit crazy").
-- Client half: plugin/DanceEmotes.cs Defs indexes 2-7 (append-only wire ids)
-- plus the CONTRACT v2 input lock (dancing is now allowed mid-battle and
-- locks the dancer's own move/shoot/block for the duration).
--
-- Same rollout shape as 272 (see its header for the full design). Rows are
-- born catalog_ready = FALSE (the #163 pattern) and migration 275 flips them
-- TRUE. This keeps the rollout ORDER-IMMUNE: the api's list/newest queries
-- already filter catalog_ready, so applying this migration while an older
-- api or client is still live exposes nothing — no client can see or buy a
-- dance it could never use. After 275 flips the rows on, the api's
-- DANCES_MIN_VERSION gate (main.py) plus 275's client-release timing rule
-- own the exposure decision.
-- Prices are Sid's knobs. Idempotent - ON CONFLICT (sku) DO NOTHING.

BEGIN;

INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color, catalog_ready) VALUES
    ('dance_jacks',      'dance', 'Jumping Jacks',  'Hop to attention - arms snap up and out on every beat. Dancing locks your controls for the duration.',      2500, 'rare',      '#FFC8F0', FALSE),
    ('dance_shimmy',     'dance', 'The Shimmy',     'Rapid-fire shoulder shake with pulsing arms. Dancing locks your controls for the duration.',                2500, 'rare',      '#FFC8F0', FALSE),
    ('dance_disco',      'dance', 'Disco Fever',    'Point to the sky, point to the floor, sway those hips. Dancing locks your controls for the duration.',      3000, 'rare',      '#FFC8F0', FALSE),
    ('dance_helicopter', 'dance', 'The Helicopter', 'Wind up the right arm and take off. Dancing locks your controls for the duration.',                         3500, 'epic',      '#FFC8F0', FALSE),
    ('dance_robot',      'dance', 'The Robot',      'Precision-stepped poses, one servo at a time. Dancing locks your controls for the duration.',               4500, 'epic',      '#FFC8F0', FALSE),
    ('dance_floss',      'dance', 'The Floss',      'Hips one way, arms the other - the classic. Dancing locks your controls for the duration.',                 5000, 'legendary', '#FFC8F0', FALSE)
ON CONFLICT (sku) DO NOTHING;

COMMIT;
