using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;
using Photon.Pun;
using Photon.Realtime;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Stackable rich-text "nametag" styling. Active styles come from the server in
    /// CachedPlayerStats.active_nametag_skus; we wrap the player's Steam nickname with
    /// &lt;b&gt;/&lt;i&gt;/&lt;u&gt;/&lt;s&gt; tags and write the result back into
    /// PhotonNetwork.LocalPlayer.NickName so every client (modded or not) renders the
    /// styling — ROUNDS' player-name UI is TextMeshPro, which parses those tags natively.
    ///
    /// Only formatting tags that Steam itself allows in display names are shipped here
    /// (bold/italic/underline/strike). Colors + fonts would leak mod-only cosmetics to
    /// non-modded players, so they're intentionally excluded.
    /// </summary>
    internal static class NametagStyler
    {
        // Cached "base" display name, stripped of any prior rich-text tags. Populated once
        // per session the first time we see LocalPlayer.NickName — so repeated PublishToPhoton
        // calls don't double-wrap ("<b><b>Name</b></b>") or lose the original text.
        private static string _baseName;

        private static readonly Dictionary<string, (string open, string close)> _tagsBySku =
            new Dictionary<string, (string, string)>(StringComparer.OrdinalIgnoreCase)
            {
                // Stackable formatting — no subgroup, can all be on at once.
                { "nametag_bold",      ("<b>",  "</b>") },
                { "nametag_italic",    ("<i>",  "</i>") },
                { "nametag_underline", ("<u>",  "</u>") },
                { "nametag_strike",    ("<s>",  "</s>") },

                // Colors — one active at a time (subgroup "color"). Hex values match
                // preview_color on the corresponding shop_items rows so the shop preview
                // dot and the in-game name color line up.
                { "nametag_color_red",    ("<color=#FF5566>", "</color>") },
                { "nametag_color_cyan",   ("<color=#55CCFF>", "</color>") },
                { "nametag_color_gold",   ("<color=#FFCC44>", "</color>") },
                { "nametag_color_purple", ("<color=#BB88FF>", "</color>") },
                { "nametag_color_green",  ("<color=#77DD88>", "</color>") },
                { "nametag_color_pink",   ("<color=#FF99CC>", "</color>") },

                // Neon — premium tier (500g). Rich-text color is a more saturated
                // version of the regular color set; the matching glow side fires
                // automatically for modded clients via GetGlowColor below. Subgroup
                // is "color" so a Neon and a regular Color name can't both equip.
                { "nametag_neon_pink",   ("<color=#FF1F8C>", "</color>") },
                { "nametag_neon_cyan",   ("<color=#1FF0FF>", "</color>") },
                { "nametag_neon_lime",   ("<color=#5BFF1F>", "</color>") },
                { "nametag_neon_orange", ("<color=#FF7A1F>", "</color>") },
                { "nametag_neon_violet", ("<color=#D420FF>", "</color>") },
                { "nametag_neon_toxic",  ("<color=#A8FF1F>", "</color>") },
                // The "Steam glow yellow" the user remembers — a near-white pale yellow
                // that reads as a soft luminous glow when ROUNDS' TMP renders it. People
                // used this exact hex in their Steam display name (raw <color> tag) before
                // we started stripping rich-text on incoming nicknames.
                { "nametag_neon_glowyellow", ("<color=#FFFB9D>", "</color>") },

                // Glows are NOT in this map. Inline <mark> was too flat/underwhelming and
                // leaked a visible rectangle to non-modded clients. Glow is now applied
                // locally on modded clients only, via NametagGlowRenderer which clones the
                // target TMP label's material and enables the SDF shader's _GlowColor /
                // _GlowOuter properties. Active glow sku is published via Photon custom
                // prop "cr_nametag_glow" instead of going through NickName.

                // Font-style transforms — single-active (subgroup "font"). These reshape
                // the existing SDF glyphs rather than swap fonts, so they work with the
                // Gravity font ROUNDS already ships with — no font asset required.
                { "nametag_font_caps",      ("<allcaps>",      "</allcaps>") },
                { "nametag_font_smallcaps", ("<smallcaps>",    "</smallcaps>") },
                { "nametag_font_spaced",    ("<cspace=0.4em>", "</cspace>") },

                // Sizes — single-active (subgroup "size"). <size=NN%> survives the
                // Photon NickName roundtrip and TMP renders it natively.
                { "nametag_size_smaller", ("<size=80%>",  "</size>") },
                { "nametag_size_bigger",  ("<size=130%>", "</size>") },
                { "nametag_size_huge",    ("<size=160%>", "</size>") },
            };

        /// <summary>Glow color for a given glow SKU — used by NametagGlowRenderer to set
        /// the cloned TMP material's _GlowColor property. Returns Color.clear if the sku
        /// isn't a glow sku.</summary>
        public static Color GetGlowColor(string sku)
        {
            if (string.IsNullOrEmpty(sku)) return Color.clear;
            switch (sku)
            {
                case "nametag_glow_red":  return new Color(1.00f, 0.27f, 0.33f, 1f);
                case "nametag_glow_blue": return new Color(0.27f, 0.53f, 1.00f, 1f);
                case "nametag_glow_gold": return new Color(1.00f, 0.80f, 0.27f, 1f);
                case "nametag_glow_pink": return new Color(1.00f, 0.53f, 0.80f, 1f);
                // Neon items double as their own glow source. Brighter / more saturated
                // than the regular glow set so they read as "neon" rather than just tinted.
                case "nametag_neon_pink":   return new Color(1.00f, 0.12f, 0.55f, 1f);
                case "nametag_neon_cyan":   return new Color(0.12f, 0.94f, 1.00f, 1f);
                case "nametag_neon_lime":   return new Color(0.36f, 1.00f, 0.12f, 1f);
                case "nametag_neon_orange": return new Color(1.00f, 0.48f, 0.12f, 1f);
                case "nametag_neon_violet": return new Color(0.83f, 0.13f, 1.00f, 1f);
                case "nametag_neon_toxic":  return new Color(0.66f, 1.00f, 0.12f, 1f);
                case "nametag_neon_glowyellow": return new Color(1.00f, 0.98f, 0.61f, 1f);
                default: return Color.clear;
            }
        }

        /// <summary>Return the subgroup for a nametag SKU, or null for stackable items.
        /// Mirrors the server's _nametag_subgroup — used client-side for optimistic
        /// single-active replacement before the server round-trip.</summary>
        public static string GetSubgroup(string sku)
        {
            if (string.IsNullOrEmpty(sku)) return null;
            if (sku.StartsWith("nametag_color_",    StringComparison.OrdinalIgnoreCase)) return "color";
            // Neon items occupy the "color" slot — equipping a neon swaps any plain
            // color name out (and vice versa). Their glow side fires for free via
            // GetGlowColor without colliding with the separate "glow" subgroup, so
            // a player can stack a Neon + a separate plain Glow if they want to.
            if (sku.StartsWith("nametag_neon_",     StringComparison.OrdinalIgnoreCase)) return "color";
            if (sku.StartsWith("nametag_glow_",     StringComparison.OrdinalIgnoreCase)) return "glow";
            if (sku.StartsWith("nametag_size_",     StringComparison.OrdinalIgnoreCase)) return "size";
            if (sku.StartsWith("nametag_typeface_", StringComparison.OrdinalIgnoreCase)) return "typeface";
            if (sku.StartsWith("nametag_font_",     StringComparison.OrdinalIgnoreCase)) return "font";
            return null;
        }

        /// <summary>Active typeface sku (one of nametag_typeface_*) from the cached stats, or "".
        /// Typefaces are rendered locally by NametagFontRenderer after publishing via Photon
        /// custom prop "cr_nametag_typeface" — non-modded clients see the plain name, no glyph
        /// boxes. Kept separate from nametag_font_* (ALL CAPS / spaced / etc) so both can stack.</summary>
        public static string GetActiveTypefaceSku(List<string> activeSkus)
        {
            if (activeSkus == null) return "";
            foreach (var s in activeSkus)
                if (!string.IsNullOrEmpty(s)
                    && s.StartsWith("nametag_typeface_", StringComparison.OrdinalIgnoreCase))
                    return s;
            return "";
        }


        /// <summary>Strip existing rich-text tags from an incoming nickname and return the
        /// bare display name. Safe on null/empty input.</summary>
        public static string Clean(string name)
        {
            if (string.IsNullOrEmpty(name)) return name;
            return Regex.Replace(name, "<.*?>", "").Trim();
        }

        /// <summary>Single-SKU preview — wraps the name in just the tag(s) for this SKU.
        /// Glow and typeface SKUs have no inline rich-text representation (they're rendered
        /// locally via material/font swap on the preview label by the shop UI), so they
        /// return the clean name. A <mark> fallback used to live here but turned into the
        /// "flat colored box" users saw overlaying the real glow — we killed that.</summary>
        public static string WrapForSku(string name, string sku)
        {
            if (string.IsNullOrEmpty(name)) return name;
            if (sku == null) return name;
            if (_tagsBySku.TryGetValue(sku, out var t))
                return t.open + name + t.close;
            return name;
        }

        /// <summary>Compose all active inline-rich-text styles around the cleaned name.
        /// Glow is intentionally NOT handled here — it's applied locally via material
        /// clone in NametagGlowRenderer, so non-modded clients see a clean unstyled name
        /// rather than a flat <mark> rectangle. Tag nesting order is stable (innermost →
        /// outermost: font-transform, size, color, strike, underline, italic, bold) so
        /// the name doesn't flicker across stat-refresh orderings.</summary>
        public static string Wrap(string name, List<string> activeSkus)
        {
            string clean = Clean(name);
            if (string.IsNullOrEmpty(clean)) return clean;
            if (activeSkus == null || activeSkus.Count == 0) return clean;

            // Innermost first — each pass wraps the previous result. Subgroups (color/
            // size/font) have multiple possible SKUs per subgroup; we walk all of them
            // and the single-active enforcement on server + client ensures at most one
            // per subgroup is present in activeSkus.
            string[][] layers = new[]
            {
                new[] { "nametag_font_caps", "nametag_font_smallcaps", "nametag_font_spaced" },
                new[] { "nametag_size_smaller", "nametag_size_bigger", "nametag_size_huge" },
                new[] { "nametag_color_red", "nametag_color_cyan", "nametag_color_gold",
                        "nametag_color_purple", "nametag_color_green", "nametag_color_pink",
                        // Neon items occupy the color slot (single-active vs plain colors)
                        // and ALSO drive the glow side via GetGlowColor — so they need to
                        // appear in this color-wrapping layer or the rich-text color tag
                        // never gets emitted into NickName and the name reads as plain white.
                        "nametag_neon_pink", "nametag_neon_cyan", "nametag_neon_lime",
                        "nametag_neon_orange", "nametag_neon_violet", "nametag_neon_toxic",
                        "nametag_neon_glowyellow" },
                new[] { "nametag_strike" },
                new[] { "nametag_underline" },
                new[] { "nametag_italic" },
                new[] { "nametag_bold" },
            };

            string wrapped = clean;
            foreach (var layer in layers)
            {
                foreach (var sku in layer)
                {
                    if (activeSkus.Contains(sku) && _tagsBySku.TryGetValue(sku, out var t))
                    {
                        wrapped = t.open + wrapped + t.close;
                        break;
                    }
                }
            }
            return wrapped;
        }

        /// <summary>Return the active glow sku from the cached stats, or empty if none.
        /// Used by NametagGlowRenderer for the local-player case and published into a
        /// Photon custom prop so other modded clients can read it for their renders.</summary>
        public static string GetActiveGlowSku(List<string> activeSkus)
        {
            if (activeSkus == null) return "";
            // Plain glow items take precedence (they're in the dedicated 'glow'
            // subgroup), but if none is equipped, an active neon doubles as the
            // glow source.
            foreach (var s in activeSkus)
                if (!string.IsNullOrEmpty(s)
                    && s.StartsWith("nametag_glow_", StringComparison.OrdinalIgnoreCase))
                    return s;
            foreach (var s in activeSkus)
                if (!string.IsNullOrEmpty(s)
                    && s.StartsWith("nametag_neon_", StringComparison.OrdinalIgnoreCase))
                    return s;
            return "";
        }

        /// <summary>Push the current styled nickname to PhotonNetwork.LocalPlayer so it
        /// broadcasts to every client in the room. Also publishes the glow sku via a
        /// separate "cr_nametag_glow" custom property so modded opponents can apply the
        /// local glow material to their render of this player's name (non-modded clients
        /// just ignore the prop). Safe to call outside a room (no-op) or before stats
        /// have loaded (uses the current NickName as base). Cheap enough to invoke on
        /// every stat refresh + shop toggle + room join.</summary>
        public static void PublishToPhoton()
        {
            try
            {
                if (!PhotonNetwork.IsConnected || PhotonNetwork.LocalPlayer == null) return;

                // Capture the base name once per session. On subsequent calls the LocalPlayer
                // NickName will already be tag-wrapped by us, so stripping catches the raw
                // Steam name from the first call.
                if (string.IsNullOrEmpty(_baseName))
                    _baseName = Clean(PhotonNetwork.LocalPlayer.NickName);

                string cleanBase = Clean(PhotonNetwork.LocalPlayer.NickName);
                if (!string.IsNullOrEmpty(cleanBase))
                    _baseName = cleanBase;  // keep fresh if Steam persona changed
                if (string.IsNullOrEmpty(_baseName)) return;

                var skus = ApiClient.CachedPlayerStats?.active_nametag_skus;
                string styled = Wrap(_baseName, skus);

                if (PhotonNetwork.LocalPlayer.NickName != styled)
                {
                    PhotonNetwork.LocalPlayer.NickName = styled;
                    Plugin.Log.LogInfo($"[NAMETAG] Published '{styled}' ({(skus == null ? 0 : skus.Count)} style(s))");
                }

                // Separate custom props for the two local-only effects (glow, typeface). Only
                // modded clients read them — non-modded players see an unstyled name with no
                // leaked artifacts. Batch both into one SetCustomProperties call so there's at
                // most a single Photon roundtrip per PublishToPhoton invocation.
                string glowSku = GetActiveGlowSku(skus);
                string typefaceSku = GetActiveTypefaceSku(skus);
                try
                {
                    var props = PhotonNetwork.LocalPlayer.CustomProperties;
                    object existingGlow, existingFont;
                    bool glowChanged = !props.TryGetValue("cr_nametag_glow", out existingGlow)
                        || (existingGlow?.ToString() ?? "") != glowSku;
                    bool fontChanged = !props.TryGetValue("cr_nametag_typeface", out existingFont)
                        || (existingFont?.ToString() ?? "") != typefaceSku;
                    if (glowChanged || fontChanged)
                    {
                        var upd = new ExitGames.Client.Photon.Hashtable();
                        if (glowChanged) upd["cr_nametag_glow"] = glowSku;
                        if (fontChanged) upd["cr_nametag_typeface"] = typefaceSku;
                        PhotonNetwork.LocalPlayer.SetCustomProperties(upd);
                    }
                }
                catch { }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[NAMETAG] Publish failed: {ex.Message}"); }
        }
    }
}
