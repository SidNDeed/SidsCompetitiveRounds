-- 024_trail_items.sql
--
-- First wave of cosmetic trails. Priced as a premium cosmetic tier — cheapest
-- is 3000g (≈150 hours of average play), legendaries 10000g (long-term goals).

INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
    ('trail_white',    'trail', 'Clean Trail',     'A clean white line. The basics.',                           3000,  'rare',      '#FFFFFF'),
    ('trail_crimson',  'trail', 'Crimson Streak',  'Deep red smoke following your every move.',                 3000,  'rare',      '#FF3344'),
    ('trail_azure',    'trail', 'Azure Comet',     'Cool blue energy crackling behind you.',                    3000,  'rare',      '#44BBFF'),
    ('trail_emerald',  'trail', 'Emerald Glow',    'A soft green aura that says you know what you''re doing.',  3000,  'rare',      '#44DD88'),
    ('trail_phoenix',  'trail', 'Phoenix Flame',   'Orange-to-yellow gradient that sears the arena.',           5000,  'legendary', '#FFAA33'),
    ('trail_void',     'trail', 'Void Ripple',     'Purple-black shadow trail. Feels wrong in the best way.',   5000,  'legendary', '#AA44FF'),
    ('trail_prism',    'trail', 'Prismatic Wake',  'Shifts through the spectrum as you move. Pure show-off.',   10000, 'legendary', '#FF66EE')
ON CONFLICT (sku) DO NOTHING;
