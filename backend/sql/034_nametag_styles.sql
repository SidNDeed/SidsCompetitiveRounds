-- v1.23.0 — Name styling shop items.
--
-- New kind='nametag': rich-text formatting that wraps the player's display name.
-- Bold/Italic/Underline/Strike are ALL stackable — unlike title/trail/color which
-- are single-active. Storage is a BIGINT[] column on players referencing shop_items.id.
--
-- The client mirrors the active set into PhotonNetwork.LocalPlayer.NickName on room
-- join + stats refresh, so non-modded players see the styling too — TextMeshPro's
-- default rich-text rendering in ROUNDS' player-name UI picks up <b>/<i>/<u>/<s>
-- tags natively. This only works for formatting Steam allows in nicknames; we do
-- not ship colors/fonts in this migration for that reason.
--
-- Price: 100g each — intentionally cheap so users can casually mix.
--
-- Idempotent.

ALTER TABLE players
    ADD COLUMN IF NOT EXISTS nametag_style_ids BIGINT[] NOT NULL DEFAULT '{}';

INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
    ('nametag_bold',      'nametag', 'Bold',      'Wrap your name in <b>bold</b>. Stackable with other name styles.',     100, 'common', '#FFFFFF'),
    ('nametag_italic',    'nametag', 'Italic',    'Wrap your name in <i>italic</i>. Stackable with other name styles.',   100, 'common', '#FFFFFF'),
    ('nametag_underline', 'nametag', 'Underline', 'Add an underline to your name. Stackable with other name styles.',     100, 'common', '#FFFFFF'),
    ('nametag_strike',    'nametag', 'Strike',    'Strike through your name. Stackable with other name styles.',          100, 'common', '#FFFFFF')
ON CONFLICT (sku) DO NOTHING;
