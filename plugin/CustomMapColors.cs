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
        //   MapBlockColor — PRIMARY wall color. Tints half the OutOfBounds wall particle systems
        //                   (the other half get SecondaryColor — see the two-tone wall pass in
        //                   MapPhysicalColorPatch). Multiplied onto the vanilla particle color.
        //   SecondaryColor— SECOND wall color + the atmosphere/background glow tint.
        //   Configure     — ColorGrading layered on top via the cloned profile. Controls the
        //                   BACKGROUND brightness/mood (postExposure + colorFilter) for the whole
        //                   scene.
        //
        // v1.26.11 full rework — design rules:
        //   * Backgrounds stay LIGHT GREY → DARK GREY (never pitch black). postExposure lives in
        //     the -0.30 (light grey) to -0.80 (dark) band; the old -1.45..-1.65 "dark batch"
        //     crushed the walls into the background, so those values are gone.
        //   * colorFilters are near-NEUTRAL grey (brightness ~0.34-0.56) with only a subtle tint,
        //     so the COLORED walls pop against a calm grey backdrop instead of fighting a tinted bg.
        //   * Walls are a designed TWO-COLOR pair (primary + secondary) chosen to read clearly and
        //     be unique per skin. Both colors are kept bright/saturated enough to survive the bg
        //     darkening.
        //   * The brown physics boxes are NEVER tinted (the Map.Start patch only touches OutOfBounds
        //     particles + ArtInstance atmosphere particles), so they stay brown as required.
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
                // ── Light / mid backgrounds ──

                // Soft Slate — slate blue-grey walls + warm peach accent on a light grey bg.
                { "mapcolor_soft", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.50f, 0.58f, 0.68f),
                    SecondaryColor = new Color(0.85f, 0.62f, 0.48f),
                    Configure = cg => {
                        cg.saturation.Override(-30f);
                        cg.temperature.Override(5f);
                        cg.postExposure.Override(-0.35f);
                        cg.colorFilter.Override(new Color(0.52f, 0.52f, 0.54f));
                    }
                }},
                // Moss — moss green walls + earthy tan accent on a grey-green bg.
                { "mapcolor_moss", new Preset {
                    BaseArt = "Poison",
                    MapBlockColor = new Color(0.42f, 0.62f, 0.40f),
                    SecondaryColor = new Color(0.74f, 0.60f, 0.38f),
                    Configure = cg => {
                        cg.saturation.Override(-22f);
                        cg.temperature.Override(10f);
                        cg.postExposure.Override(-0.55f);
                        cg.colorFilter.Override(new Color(0.42f, 0.46f, 0.42f));
                    }
                }},
                // Cream — warm cream-tan walls + soft sky-blue accent on a light bg.
                { "mapcolor_cream", new Preset {
                    BaseArt = "Gold",
                    MapBlockColor = new Color(0.88f, 0.80f, 0.62f),
                    SecondaryColor = new Color(0.58f, 0.74f, 0.90f),
                    Configure = cg => {
                        cg.saturation.Override(-20f);
                        cg.temperature.Override(-10f);
                        cg.postExposure.Override(-0.30f);
                        cg.colorFilter.Override(new Color(0.54f, 0.54f, 0.56f));
                    }
                }},
                // Lavender — pastel lavender walls + soft gold accent on a light grey bg.
                { "mapcolor_lavender", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.70f, 0.62f, 0.88f),
                    SecondaryColor = new Color(0.88f, 0.78f, 0.52f),
                    Configure = cg => {
                        cg.saturation.Override(-22f);
                        cg.temperature.Override(5f);
                        cg.postExposure.Override(-0.40f);
                        cg.colorFilter.Override(new Color(0.50f, 0.49f, 0.54f));
                    }
                }},
                // Dusk — navy-blue walls + warm amber accent on a darker blue-grey bg.
                { "mapcolor_dusk", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.36f, 0.46f, 0.72f),
                    SecondaryColor = new Color(0.86f, 0.60f, 0.30f),
                    Configure = cg => {
                        cg.saturation.Override(-18f);
                        cg.temperature.Override(10f);
                        cg.postExposure.Override(-0.62f);
                        cg.colorFilter.Override(new Color(0.40f, 0.40f, 0.46f));
                    }
                }},
                // Sand — sandy gold walls + cool teal accent on a warm light-grey bg.
                { "mapcolor_sand", new Preset {
                    BaseArt = "Gold",
                    MapBlockColor = new Color(0.86f, 0.70f, 0.44f),
                    SecondaryColor = new Color(0.40f, 0.70f, 0.72f),
                    Configure = cg => {
                        cg.saturation.Override(-18f);
                        cg.temperature.Override(-10f);
                        cg.postExposure.Override(-0.40f);
                        cg.colorFilter.Override(new Color(0.52f, 0.50f, 0.46f));
                    }
                }},
                // Monochrome — light grey + dark grey walls on a neutral grey bg.
                { "mapcolor_mono", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.80f, 0.80f, 0.82f),
                    SecondaryColor = new Color(0.40f, 0.40f, 0.44f),
                    Configure = cg => {
                        cg.saturation.Override(-100f);
                        cg.postExposure.Override(-0.45f);
                        cg.colorFilter.Override(new Color(0.48f, 0.48f, 0.50f));
                    }
                }},

                // ── Jewel / nature tones ──

                // Forest — deep evergreen walls + amber accent on a darker green-grey bg.
                { "mapcolor_forest", new Preset {
                    BaseArt = "Poison",
                    MapBlockColor = new Color(0.28f, 0.56f, 0.34f),
                    SecondaryColor = new Color(0.82f, 0.58f, 0.26f),
                    Configure = cg => {
                        cg.saturation.Override(-18f);
                        cg.temperature.Override(-5f);
                        cg.postExposure.Override(-0.60f);
                        cg.colorFilter.Override(new Color(0.40f, 0.44f, 0.40f));
                    }
                }},
                // Amethyst — amethyst purple walls + warm gold accent on a mid grey bg.
                { "mapcolor_amethyst", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.64f, 0.42f, 0.84f),
                    SecondaryColor = new Color(0.86f, 0.70f, 0.38f),
                    Configure = cg => {
                        cg.saturation.Override(-12f);
                        cg.temperature.Override(10f);
                        cg.postExposure.Override(-0.50f);
                        cg.colorFilter.Override(new Color(0.45f, 0.43f, 0.49f));
                    }
                }},
                // Charcoal — light cool grey + mid slate walls on a dark grey bg.
                { "mapcolor_charcoal", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.72f, 0.74f, 0.80f),
                    SecondaryColor = new Color(0.44f, 0.46f, 0.52f),
                    Configure = cg => {
                        cg.saturation.Override(-70f);
                        cg.postExposure.Override(-0.65f);
                        cg.colorFilter.Override(new Color(0.38f, 0.38f, 0.42f));
                    }
                }},
                // Crimson — crimson red walls + teal accent on a dark neutral bg.
                { "mapcolor_crimson_map", new Preset {
                    BaseArt = "Soviet",
                    MapBlockColor = new Color(0.80f, 0.28f, 0.30f),
                    SecondaryColor = new Color(0.30f, 0.64f, 0.62f),
                    Configure = cg => {
                        cg.saturation.Override(-12f);
                        cg.temperature.Override(-10f);
                        cg.postExposure.Override(-0.58f);
                        cg.colorFilter.Override(new Color(0.42f, 0.38f, 0.40f));
                    }
                }},
                // Slate — slate-blue walls + copper accent on a neutral grey bg.
                { "mapcolor_slate", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.44f, 0.56f, 0.70f),
                    SecondaryColor = new Color(0.80f, 0.54f, 0.34f),
                    Configure = cg => {
                        cg.saturation.Override(-25f);
                        cg.temperature.Override(8f);
                        cg.postExposure.Override(-0.45f);
                        cg.colorFilter.Override(new Color(0.47f, 0.48f, 0.50f));
                    }
                }},
                // Rose — dusty rose walls + sage-teal accent on a light bg.
                { "mapcolor_rose", new Preset {
                    BaseArt = "Gold",
                    MapBlockColor = new Color(0.84f, 0.50f, 0.58f),
                    SecondaryColor = new Color(0.46f, 0.72f, 0.62f),
                    Configure = cg => {
                        cg.saturation.Override(-18f);
                        cg.temperature.Override(5f);
                        cg.postExposure.Override(-0.40f);
                        cg.colorFilter.Override(new Color(0.52f, 0.49f, 0.51f));
                    }
                }},
                // Mint — pale mint walls + warm coral accent on a light bg.
                { "mapcolor_mint", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.58f, 0.86f, 0.70f),
                    SecondaryColor = new Color(0.94f, 0.56f, 0.50f),
                    Configure = cg => {
                        cg.saturation.Override(-12f);
                        cg.temperature.Override(0f);
                        cg.postExposure.Override(-0.40f);
                        cg.colorFilter.Override(new Color(0.50f, 0.52f, 0.50f));
                    }
                }},
                // Sunset — sunset orange walls + violet accent on a mid grey bg.
                { "mapcolor_sunset", new Preset {
                    BaseArt = "Gold",
                    MapBlockColor = new Color(0.94f, 0.54f, 0.30f),
                    SecondaryColor = new Color(0.54f, 0.40f, 0.74f),
                    Configure = cg => {
                        cg.saturation.Override(-8f);
                        cg.temperature.Override(-8f);
                        cg.postExposure.Override(-0.50f);
                        cg.colorFilter.Override(new Color(0.47f, 0.43f, 0.47f));
                    }
                }},

                // ── Deep / moody (still grey bg, never black) ──

                // Obsidian — dark blue-grey walls + bright silver-blue accent on a dark bg.
                { "mapcolor_obsidian", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.40f, 0.46f, 0.58f),
                    SecondaryColor = new Color(0.64f, 0.72f, 0.84f),
                    Configure = cg => {
                        cg.saturation.Override(-35f);
                        cg.temperature.Override(-10f);
                        cg.postExposure.Override(-0.72f);
                        cg.colorFilter.Override(new Color(0.36f, 0.37f, 0.42f));
                    }
                }},
                // Abyss — deep teal-blue walls + bright cyan accent on a dark cool bg.
                { "mapcolor_abyss", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.26f, 0.52f, 0.62f),
                    SecondaryColor = new Color(0.42f, 0.82f, 0.84f),
                    Configure = cg => {
                        cg.saturation.Override(-12f);
                        cg.temperature.Override(-25f);
                        cg.tint.Override(-8f);
                        cg.postExposure.Override(-0.72f);
                        cg.colorFilter.Override(new Color(0.34f, 0.40f, 0.44f));
                    }
                }},
                // Pine — pine green walls + autumn-rust accent on a darker green-grey bg.
                { "mapcolor_pine", new Preset {
                    BaseArt = "Poison",
                    MapBlockColor = new Color(0.32f, 0.54f, 0.40f),
                    SecondaryColor = new Color(0.80f, 0.48f, 0.26f),
                    Configure = cg => {
                        cg.saturation.Override(-18f);
                        cg.temperature.Override(-5f);
                        cg.postExposure.Override(-0.66f);
                        cg.colorFilter.Override(new Color(0.38f, 0.42f, 0.40f));
                    }
                }},
                // Iron — steel grey walls + oxidized-rust accent on a neutral grey bg.
                { "mapcolor_iron", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.54f, 0.58f, 0.64f),
                    SecondaryColor = new Color(0.78f, 0.48f, 0.28f),
                    Configure = cg => {
                        cg.saturation.Override(-35f);
                        cg.temperature.Override(5f);
                        cg.postExposure.Override(-0.55f);
                        cg.colorFilter.Override(new Color(0.42f, 0.43f, 0.46f));
                    }
                }},
                // Burgundy — wine-red walls + slate-blue accent on a dark bg. (The blue Sid liked.)
                { "mapcolor_burgundy", new Preset {
                    BaseArt = "Soviet",
                    MapBlockColor = new Color(0.64f, 0.24f, 0.34f),
                    SecondaryColor = new Color(0.36f, 0.52f, 0.78f),
                    Configure = cg => {
                        cg.saturation.Override(-12f);
                        cg.temperature.Override(8f);
                        cg.postExposure.Override(-0.66f);
                        cg.colorFilter.Override(new Color(0.40f, 0.36f, 0.42f));
                    }
                }},
                // Magma — molten oxblood-red walls + glowing amber-yellow accent on a dark warm bg.
                { "mapcolor_magma", new Preset {
                    BaseArt = "Soviet",
                    MapBlockColor = new Color(0.74f, 0.28f, 0.18f),
                    SecondaryColor = new Color(0.94f, 0.70f, 0.30f),
                    Configure = cg => {
                        cg.saturation.Override(-6f);
                        cg.temperature.Override(25f);
                        cg.postExposure.Override(-0.58f);
                        cg.colorFilter.Override(new Color(0.44f, 0.38f, 0.34f));
                    }
                }},
                // Velvet — royal purple walls + gilded gold accent on a dark bg.
                { "mapcolor_velvet", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.48f, 0.28f, 0.66f),
                    SecondaryColor = new Color(0.86f, 0.68f, 0.34f),
                    Configure = cg => {
                        cg.saturation.Override(-12f);
                        cg.temperature.Override(10f);
                        cg.postExposure.Override(-0.66f);
                        cg.colorFilter.Override(new Color(0.40f, 0.36f, 0.44f));
                    }
                }},
                // Blackwood — charred slate timber walls + smoldering ember accent on a dark warm bg.
                // (Walls deliberately slate, not brown, so they don't blend with the brown boxes.)
                { "mapcolor_blackwood", new Preset {
                    BaseArt = "Gold",
                    MapBlockColor = new Color(0.48f, 0.48f, 0.52f),
                    SecondaryColor = new Color(0.86f, 0.52f, 0.24f),
                    Configure = cg => {
                        cg.saturation.Override(-30f);
                        cg.temperature.Override(15f);
                        cg.postExposure.Override(-0.70f);
                        cg.colorFilter.Override(new Color(0.38f, 0.37f, 0.38f));
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
