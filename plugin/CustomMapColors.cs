using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering.PostProcessing;

namespace CompetitiveRounds
{
    /// <summary>
    /// Runtime-authored ColorGrading overrides for the "calm" map color presets. The patch
    /// applies a vanilla base art for the bloom/particle backdrop, then ApplyPost'es a CLONE
    /// of that base art's PostProcessProfile with our ColorGrading injected. The clone is
    /// cached per SKU so we don't allocate every NextArt call AND the original shared
    /// art profile (e.g. Sky's profile) is NEVER mutated — vanilla Shift cycling stays clean.
    /// </summary>
    internal static class CustomMapColors
    {
        // sku → cached cloned profile (built once per session, reused on every NextArt).
        private static readonly Dictionary<string, PostProcessProfile> _profileCache =
            new Dictionary<string, PostProcessProfile>(StringComparer.OrdinalIgnoreCase);

        // SKU → preset. Each preset has:
        //   BaseArt       — vanilla ROUNDS art applied first for particle backdrop + base profile
        //   MapBlockColor — color tint applied to the physical map block renderers (Map.Start patch)
        //   Configure     — ColorGrading params layered on top via the cloned profile
        // Designed so map blocks visually pop against their backdrop and both player colors
        // (orange + blue) stay readable. Backgrounds are darkened (post-exposure -0.2 to -0.45)
        // on most presets so the player avatars stand out — Soft Slate + Cream stay lighter
        // for users who prefer the brighter look from the previous batch.
        private struct Preset
        {
            public string BaseArt;
            public Color? MapBlockColor;
            // Optional second color used to alternate particle systems (OutOfBounds walls +
            // vanilla art particle backdrops). Without this every particle gets MapBlockColor
            // → flat single-tone wall. With it, half the particles get Main and half get
            // Secondary → restores the multi-color "atmosphere" feel of vanilla arts.
            public Color? SecondaryColor;
            public Action<ColorGrading> Configure;
        }

        private static readonly Dictionary<string, Preset> _presets =
            new Dictionary<string, Preset>(StringComparer.OrdinalIgnoreCase)
            {
                // ── Existing presets, retuned with darker bg + matched block color ──

                // Soft Slate — slate-grey blocks + warm peach accent. Background shifts to a
                // neutral warm grey (away from the blue-grey block family) for clearer separation.
                { "mapcolor_soft", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.42f, 0.48f, 0.56f),
                    SecondaryColor = new Color(0.56f, 0.48f, 0.42f),
                    Configure = cg => {
                        cg.saturation.Override(-45f);
                        cg.temperature.Override(10f);
                        cg.postExposure.Override(-0.95f);
                        cg.colorFilter.Override(new Color(0.38f, 0.36f, 0.34f));
                    }
                }},
                // Moss — green blocks + earthy brown accent. Background pushed to warm dark brown
                // so the green blocks don't blend into a green backdrop.
                { "mapcolor_moss", new Preset {
                    BaseArt = "Poison",
                    MapBlockColor = new Color(0.30f, 0.50f, 0.32f),
                    SecondaryColor = new Color(0.50f, 0.42f, 0.28f),
                    Configure = cg => {
                        cg.saturation.Override(-40f);
                        cg.postExposure.Override(-1.15f);
                        cg.temperature.Override(20f);
                        cg.colorFilter.Override(new Color(0.40f, 0.32f, 0.22f));
                    }
                }},
                // Cream — tan blocks + cool blue accent. Background is cool-blue now (was tan,
                // which blended with the tan blocks). True warm-cool split now.
                { "mapcolor_cream", new Preset {
                    BaseArt = "Gold",
                    MapBlockColor = new Color(0.85f, 0.78f, 0.62f),
                    SecondaryColor = new Color(0.62f, 0.72f, 0.85f),
                    Configure = cg => {
                        cg.saturation.Override(-30f);
                        cg.temperature.Override(-30f);
                        cg.postExposure.Override(-0.95f);
                        cg.colorFilter.Override(new Color(0.42f, 0.48f, 0.58f));
                    }
                }},
                // Lavender — pastel lavender blocks + gold accent. Background shifts to warm
                // gold-brown so the cool lavender blocks read against a complementary warm bg.
                { "mapcolor_lavender", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.62f, 0.55f, 0.78f),
                    SecondaryColor = new Color(0.78f, 0.72f, 0.55f),
                    Configure = cg => {
                        cg.saturation.Override(-40f);
                        cg.postExposure.Override(-1.20f);
                        cg.temperature.Override(25f);
                        cg.colorFilter.Override(new Color(0.45f, 0.38f, 0.28f));
                    }
                }},
                // Dusk — deep navy blocks + amber accent. Background swings to warm reddish-brown
                // (embers) so it complements the navy blocks instead of echoing them.
                { "mapcolor_dusk", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.20f, 0.26f, 0.40f),
                    SecondaryColor = new Color(0.50f, 0.32f, 0.18f),
                    Configure = cg => {
                        cg.saturation.Override(-30f);
                        cg.temperature.Override(25f);
                        cg.postExposure.Override(-1.20f);
                        cg.colorFilter.Override(new Color(0.42f, 0.28f, 0.20f));
                    }
                }},
                // Sand — sandy blocks + cool-blue accent. Background flips to cool dusty blue
                // (oasis sky) so the warm sand blocks contrast hard against it.
                { "mapcolor_sand", new Preset {
                    BaseArt = "Gold",
                    MapBlockColor = new Color(0.78f, 0.65f, 0.42f),
                    SecondaryColor = new Color(0.42f, 0.55f, 0.78f),
                    Configure = cg => {
                        cg.saturation.Override(-25f);
                        cg.temperature.Override(-35f);
                        cg.tint.Override(-5f);
                        cg.postExposure.Override(-1.10f);
                        cg.colorFilter.Override(new Color(0.32f, 0.40f, 0.55f));
                    }
                }},
                // Monochrome — pure grey blocks + slightly cooler grey walls. Background already
                // tiered (dark) so kept as-is — this preset reads fine already.
                { "mapcolor_mono", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.55f, 0.55f, 0.55f),
                    SecondaryColor = new Color(0.32f, 0.32f, 0.38f),
                    Configure = cg => {
                        cg.saturation.Override(-100f);
                        cg.postExposure.Override(-1.25f);
                        cg.colorFilter.Override(new Color(0.20f, 0.20f, 0.22f));
                    }
                }},

                // ── NEW presets — straying from the default-ROUNDS palette ──

                // Forest — deep evergreen + amber accent (sunlight through canopy feel).
                { "mapcolor_forest", new Preset {
                    BaseArt = "Poison",
                    MapBlockColor = new Color(0.18f, 0.36f, 0.24f),
                    SecondaryColor = new Color(0.55f, 0.42f, 0.18f),
                    Configure = cg => {
                        cg.saturation.Override(-30f);
                        cg.postExposure.Override(-1.10f);
                        cg.temperature.Override(-10f);
                        cg.colorFilter.Override(new Color(0.30f, 0.55f, 0.35f));
                    }
                }},
                // Amethyst — purple walls + warm gold background (swap from previous build).
                // Blocks are lighter lavender so they pop against the deeper-purple walls.
                { "mapcolor_amethyst", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.72f, 0.58f, 0.88f),
                    SecondaryColor = new Color(0.38f, 0.20f, 0.55f),
                    Configure = cg => {
                        cg.saturation.Override(-15f);
                        cg.postExposure.Override(-0.95f);
                        cg.temperature.Override(25f);
                        cg.colorFilter.Override(new Color(0.62f, 0.50f, 0.22f));
                    }
                }},
                // Charcoal — tiered greys, but all DARK. Previous version used medium-grey blocks
                // which made the wall particles (half-primary / half-secondary) read as glowy grey
                // against near-black bg — user feedback was "walls very bright". Now everything is
                // in the 0.14–0.32 range: blocks still visible (lightest tier), walls mid-dark,
                // background nearly black. Saturation -100 so subtle warm/cool differences don't
                // sneak in and add brightness.
                { "mapcolor_charcoal", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.32f, 0.32f, 0.35f),
                    SecondaryColor = new Color(0.18f, 0.16f, 0.14f),
                    Configure = cg => {
                        cg.saturation.Override(-100f);
                        cg.postExposure.Override(-1.50f);
                        cg.colorFilter.Override(new Color(0.10f, 0.10f, 0.12f));
                    }
                }},
                // Crimson — red blocks + teal accent. Background flips to dark teal (matching the
                // accent) so the red blocks contrast hard against their complement instead of
                // sitting on a pink-red backdrop.
                { "mapcolor_crimson_map", new Preset {
                    BaseArt = "Soviet",
                    MapBlockColor = new Color(0.45f, 0.15f, 0.18f),
                    SecondaryColor = new Color(0.15f, 0.45f, 0.42f),
                    Configure = cg => {
                        cg.saturation.Override(-25f);
                        cg.postExposure.Override(-1.10f);
                        cg.temperature.Override(-30f);
                        cg.colorFilter.Override(new Color(0.22f, 0.38f, 0.40f));
                    }
                }},
                // Slate — cool slate-blue blocks + copper accent. Background shifts to warm copper
                // (was also slate → too similar to blocks).
                { "mapcolor_slate", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.32f, 0.40f, 0.50f),
                    SecondaryColor = new Color(0.50f, 0.40f, 0.32f),
                    Configure = cg => {
                        cg.saturation.Override(-45f);
                        cg.postExposure.Override(-1.10f);
                        cg.temperature.Override(30f);
                        cg.colorFilter.Override(new Color(0.42f, 0.32f, 0.22f));
                    }
                }},
                // Rose — dusty rose + muted sage teal accent.
                { "mapcolor_rose", new Preset {
                    BaseArt = "Gold",
                    MapBlockColor = new Color(0.62f, 0.36f, 0.42f),
                    SecondaryColor = new Color(0.36f, 0.62f, 0.55f),
                    Configure = cg => {
                        cg.saturation.Override(-35f);
                        cg.postExposure.Override(-1.00f);
                        cg.temperature.Override(20f);
                        cg.colorFilter.Override(new Color(0.65f, 0.45f, 0.50f));
                    }
                }},
                // Mint — pale mint blocks + coral accent. Background flips to dusty coral (was
                // also mint → blocks blended). Now a true split-complement palette.
                { "mapcolor_mint", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.55f, 0.78f, 0.65f),
                    SecondaryColor = new Color(0.78f, 0.55f, 0.62f),
                    Configure = cg => {
                        cg.saturation.Override(-30f);
                        cg.postExposure.Override(-1.10f);
                        cg.temperature.Override(25f);
                        cg.colorFilter.Override(new Color(0.50f, 0.32f, 0.35f));
                    }
                }},
                // Sunset — orange blocks + violet accent. Background shifts to dark violet so the
                // warm orange blocks pop against their cool complement (was peachy → same warm
                // family as the blocks).
                { "mapcolor_sunset", new Preset {
                    BaseArt = "Gold",
                    MapBlockColor = new Color(0.85f, 0.45f, 0.30f),
                    SecondaryColor = new Color(0.45f, 0.30f, 0.65f),
                    Configure = cg => {
                        cg.saturation.Override(-20f);
                        cg.postExposure.Override(-1.05f);
                        cg.temperature.Override(-35f);
                        cg.tint.Override(8f);
                        cg.colorFilter.Override(new Color(0.32f, 0.25f, 0.45f));
                    }
                }},
            };

        public static bool IsCustomSku(string sku) => sku != null && _presets.ContainsKey(sku);

        public static string GetBaseArt(string sku)
        {
            if (sku != null && _presets.TryGetValue(sku, out var p)) return p.BaseArt;
            return null;
        }

        /// <summary>Returns the per-SKU map block color tint, or null if this SKU doesn't tint
        /// the physical blocks (vanilla colors and the Default sku return null).</summary>
        public static Color? GetMapBlockColor(string sku)
        {
            if (sku != null && _presets.TryGetValue(sku, out var p)) return p.MapBlockColor;
            return null;
        }

        /// <summary>Complementary accent color for particle alternation. Falls back to a darker
        /// shade of the main color so older presets without an explicit secondary still vary.</summary>
        public static Color GetSecondaryColor(string sku)
        {
            if (sku != null && _presets.TryGetValue(sku, out var p) && p.SecondaryColor.HasValue)
                return p.SecondaryColor.Value;
            // Fallback — 60% darker version of the main color.
            var main = GetMapBlockColor(sku) ?? Color.white;
            return new Color(main.r * 0.6f, main.g * 0.6f, main.b * 0.6f, main.a);
        }

        /// <summary>
        /// Build (or fetch from cache) a cloned PostProcessProfile derived from the supplied
        /// base profile. The clone has our SKU's ColorGrading replacing the base's ColorGrading;
        /// all other effects (bloom, vignette, chromatic aberration, etc.) are preserved.
        ///
        /// Cached by SKU, so the clone is built once per session. Cached clones persist across
        /// rounds/scenes (HideAndDontSave).
        /// </summary>
        public static PostProcessProfile BuildOrGetClone(string sku, PostProcessProfile baseProfile)
        {
            if (baseProfile == null || !_presets.TryGetValue(sku, out var preset)) return null;
            if (_profileCache.TryGetValue(sku, out var cached) && cached != null) return cached;

            try
            {
                // ScriptableObject.Instantiate deep-copies the profile including its settings list.
                // Each cloned PostProcessEffectSettings is a fresh ScriptableObject we can mutate.
                var clone = UnityEngine.Object.Instantiate(baseProfile);
                clone.name = $"CR_MapColor_{sku}";
                clone.hideFlags = HideFlags.HideAndDontSave;

                // Remove any pre-existing ColorGrading from the clone so ours replaces it cleanly.
                if (clone.HasSettings<ColorGrading>())
                    clone.RemoveSettings<ColorGrading>();

                var cg = ScriptableObject.CreateInstance<ColorGrading>();
                cg.hideFlags = HideFlags.HideAndDontSave;
                cg.enabled.Override(true);
                cg.gradingMode.Override(GradingMode.LowDefinitionRange);
                preset.Configure(cg);
                clone.AddSettings(cg);

                _profileCache[sku] = clone;
                return clone;
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[MAPCOLOR] Clone {sku} failed: {ex.Message}");
                return null;
            }
        }
    }
}
