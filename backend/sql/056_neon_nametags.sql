-- 056_neon_nametags.sql
-- Premium "neon" nametag items at 500g. Each combines a bright rich-text color
-- (visible to all players, modded or not, via Photon NickName) AND a stronger
-- glow material override (visible only to modded players, via NametagGlowRenderer).
--
-- Subgroup: 'color' — single-active among ALL color-style nametag items, since
-- a player can only have one rich-text color wrapping their name at a time. The
-- glow side rides along with the color choice.
--
-- Idempotent.

INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
    ('nametag_neon_pink',     'nametag', 'Neon Pink',     'Hot-pink neon name with a soft glow halo. Visible to everyone; modded players also see the glow.',     500, 'epic', '#FF1F8C'),
    ('nametag_neon_cyan',     'nametag', 'Neon Cyan',     'Electric-cyan neon name with a soft glow halo. Visible to everyone; modded players also see the glow.', 500, 'epic', '#1FF0FF'),
    ('nametag_neon_lime',     'nametag', 'Neon Lime',     'Searing-lime neon name with a soft glow halo. Visible to everyone; modded players also see the glow.',  500, 'epic', '#5BFF1F'),
    ('nametag_neon_orange',   'nametag', 'Neon Orange',   'Vivid orange neon name with a soft glow halo. Visible to everyone; modded players also see the glow.',  500, 'epic', '#FF7A1F'),
    ('nametag_neon_violet',   'nametag', 'Neon Violet',   'Glowing magenta neon name with a soft glow halo. Visible to everyone; modded players also see the glow.', 500, 'epic', '#D420FF'),
    -- Toxic green nods to a popular Steam-name look that uses high-saturation
    -- yellow-green accents. ~+90% brightness, glow runs slightly hotter than
    -- the others so it reads as "radioactive" rather than just bright.
    ('nametag_neon_toxic',    'nametag', 'Neon Toxic',    'Radioactive yellow-green neon name with a hot glow halo. Visible to everyone; modded players also see the glow.', 500, 'epic', '#A8FF1F'),
    -- The pale-yellow "Steam glow" — same hex some players used in raw Steam-name
    -- color tags before we started stripping rich-text. Soft luminous look rather
    -- than hard saturation; pairs especially well with a darker outline.
    ('nametag_neon_glowyellow', 'nametag', 'Glow Yellow',  'Pale luminous yellow name with a matching glow halo. Mimics the classic Steam-name color trick.',          500, 'epic', '#FFFB9D')
ON CONFLICT (sku) DO NOTHING;
