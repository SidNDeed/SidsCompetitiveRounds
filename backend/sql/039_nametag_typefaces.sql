-- v1.23.x — Custom nametag typefaces. Five distinctive OS-font variants that render
-- locally only on modded clients. Non-modded opponents see the plain Steam nickname —
-- this is an intentional trade-off after the failed Unicode-substitution attempt in
-- migration 036 (which rendered as boxes everywhere because ROUNDS' TMP fallback chain
-- doesn't cover the Mathematical Alphanumeric codepoints).
--
-- Client-side implementation: NametagFontRenderer.cs builds a TMP_FontAsset at runtime
-- from each Windows OS font (Font.CreateDynamicFontFromOSFont → TMP_FontAsset.CreateFontAsset)
-- and swaps TMP_Text.font on matching player labels. Active typeface publishes via Photon
-- custom prop cr_nametag_typeface so modded opponents also see it; NickName is untouched.
--
-- Subgroup: "typeface" (single-active). SKU prefix nametag_typeface_* — NEW subgroup, does
-- NOT collide with the pre-existing "font" subgroup (which covers ALL CAPS / smallcaps /
-- spaced transforms applied via inline rich text). This lets a player stack e.g. Impact
-- typeface + ALL CAPS if they want a loud look.
--
-- Idempotent.

INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color) VALUES
    ('nametag_typeface_impact',
     'nametag', 'Impact Font',
     'Chunky bold headline typeface. Only visible to modded players.',
     150, 'uncommon', '#FFFFFF'),
    ('nametag_typeface_segoe',
     'nametag', 'Script Font',
     'Flowing handwritten cursive (Segoe Script). Only visible to modded players.',
     150, 'uncommon', '#FFFFFF'),
    ('nametag_typeface_papyrus',
     'nametag', 'Papyrus Font',
     'Ancient, torn-parchment vibe. Only visible to modded players.',
     150, 'uncommon', '#FFFFFF'),
    ('nametag_typeface_comic',
     'nametag', 'Comic Font',
     'Playful, round, meme-tier. Only visible to modded players.',
     150, 'uncommon', '#FFFFFF'),
    ('nametag_typeface_courier',
     'nametag', 'Typewriter Font',
     'Fixed-width monospace (Courier New). Only visible to modded players.',
     150, 'uncommon', '#FFFFFF')
ON CONFLICT (sku) DO NOTHING;
