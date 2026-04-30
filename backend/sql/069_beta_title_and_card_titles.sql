-- v1.25.24: Beta title (auto-granted to every existing + future player while
-- the mod is in beta) plus a wave of new card-themed titles.
--
-- All titles <= 11 characters (Grandmaster is the longest existing slot and
-- the in-game UI doesn't accommodate longer text without shrinking).

-- Beta — free, dark blue, auto-granted to all current players and equipped
-- if they have no active title. Future joiners get it via get_or_create_player
-- in main.py.
INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color)
VALUES
    ('title_beta', 'title', 'Beta',
     'Thanks for testing the mod during beta. Free, removed after beta ends.',
     0, 'common', '#2A66B5')
ON CONFLICT (sku) DO NOTHING;

-- Card-mains (top-tier preference set per Sid: Poison, Windup, Quick Reload,
-- Huge, Fast Forward, Bouncy)
INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
    ('title_poisoner', 'title', 'Poisoner',  'Poison main',          1500, 'rare',     '#66CC44'),
    ('title_windup',   'title', 'Windup',    'Windup main',          1500, 'rare',     '#AA66FF'),
    ('title_reloader', 'title', 'Reloader',  'Quick Reload main',    1500, 'rare',     '#99CCDD'),
    ('title_huge',     'title', 'Huge',      'Huge main',            1500, 'rare',     '#FFCC33'),
    ('title_hasty',    'title', 'Hasty',     'Fast Forward main',    1500, 'rare',     '#FF6633'),
    ('title_bouncy',   'title', 'Bouncy',    'Bouncy main',          1500, 'rare',     '#66CCEE')
ON CONFLICT (sku) DO NOTHING;

-- Meme card mains (community ask: Healing Field, Target Bounce, Homing)
INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
    ('title_healer',   'title', 'Healer',    'Healing Field main',   2000, 'rare',     '#44DD99'),
    ('title_bouncer',  'title', 'Bouncer',   'Target Bounce main',   2000, 'rare',     '#BBDD44'),
    ('title_tracker',  'title', 'Tracker',   'Homing main',          2000, 'rare',     '#FF6677')
ON CONFLICT (sku) DO NOTHING;

-- Generic flair (different colors, still <= 11 chars)
INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
    ('title_sniper',    'title', 'Sniper',    'Precision shooter',   2500, 'rare',     '#88CCFF'),
    ('title_tank',      'title', 'Tank',      'Eats damage',         2500, 'rare',     '#88AA88'),
    ('title_pacifist',  'title', 'Pacifist',  'Wins without firing', 3000, 'rare',     '#FFFFFF'),
    ('title_berserker', 'title', 'Berserker', 'Pure aggression',     3000, 'rare',     '#FF3333'),
    ('title_phoenix',   'title', 'Phoenix',   'Reborn after defeat', 3500, 'epic',     '#FF8833'),
    ('title_specter',   'title', 'Specter',   'Hard to hit',         3500, 'epic',     '#AABBFF'),
    ('title_blitz',     'title', 'Blitz',     'Fast finisher',       2500, 'rare',     '#FFEE33'),
    ('title_apex',      'title', 'Apex',      'Top of the food chain', 4500, 'epic',   '#FFAA00'),
    ('title_echo',      'title', 'Echo',      'Echo main',           2000, 'rare',     '#88FFCC'),
    ('title_voidshot',  'title', 'Voidshot',  'Empty Power main',    2500, 'rare',     '#7744AA')
ON CONFLICT (sku) DO NOTHING;

-- Backfill: grant Beta to every existing player + auto-equip if they don't
-- already have a title (don't override active titles people already chose).
WITH beta AS (SELECT id FROM shop_items WHERE sku = 'title_beta')
INSERT INTO player_items (player_id, item_id, purchase_price)
SELECT p.id, beta.id, 0
  FROM players p, beta
 WHERE p.deleted_at IS NULL
ON CONFLICT (player_id, item_id) DO NOTHING;

UPDATE players p
   SET active_title_id = (SELECT id FROM shop_items WHERE sku = 'title_beta')
 WHERE p.deleted_at IS NULL
   AND p.active_title_id IS NULL;
