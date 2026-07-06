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
        // v1.28 palette pass — design rules:
        //   * RENDER MODEL IS COLORIZE, NOT MULTIPLY (Plugin.cs ApplyPhysicalTintsForSku).
        //     Walls = preset color scaled by the vanilla particle's LUMINANCE, so the
        //     designed hue renders true REGARDLESS of BaseArt. (Old multiply tied the wall
        //     hue to the base art's own color: amber×red Soviet = dark red → Magma had no
        //     yellow; grey×blue Sky = blue-grey → mono/charcoal looked "too blue".) BaseArt
        //     now only controls particle SHAPES / density / bloom, never the final color.
        //   * Walls are a designed COMPLEMENTARY TWO-COLOR pair (primary + secondary), each
        //     chosen to read clearly and be unique per skin.
        //   * Backgrounds: postExposure in the -0.30 (light grey) to -0.72 (dark) band, never
        //     pitch black, never bright. colorFilter carries a SUBTLE thematic tint
        //     (brightness ~0.36-0.55) so each map's backdrop has its own gentle color that
        //     goes with the walls — plus the atmosphere particles get a dim, desaturated
        //     secondary glow (see Plugin.cs). No bright yellow/white backgrounds.
        //   * The brown physics boxes are NEVER tinted (the Map.Start patch only touches
        //     OutOfBounds particles + ArtInstance atmosphere particles), so they stay brown.
        private struct Preset
        {
            public string BaseArt;
            public Color? MapBlockColor;
            // Optional second color used to alternate particle systems (OutOfBounds walls +
            // vanilla art particle backdrops). Without this every particle gets MapBlockColor
            // → flat single-tone wall. With it, half the particles get Main and half get
            // Secondary → restores the multi-color "atmosphere" feel of vanilla arts.
            public Color? SecondaryColor;
            // Premium sparkle (v1.29): when set, wall particles emit BETWEEN their
            // layer color and this color (per-particle random) — the per-particle
            // shimmer that was a bug for normal skins (failed approach #3 in
            // Plugin.cs) is the FEATURE for the gold/platinum/aurora skins.
            public Color? Sparkle;
            public Action<ColorGrading> Configure;
        }

        private static readonly Dictionary<string, Preset> _presets =
            new Dictionary<string, Preset>(StringComparer.OrdinalIgnoreCase)
            {
                // ── Light / mid backgrounds ──

                // Soft Slate — slate blue-grey walls + warm peach accent on a soft grey bg.
                { "mapcolor_soft", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.52f, 0.60f, 0.72f),
                    SecondaryColor = new Color(0.92f, 0.66f, 0.48f),
                    Configure = cg => {
                        cg.saturation.Override(-24f);
                        cg.temperature.Override(4f);
                        cg.postExposure.Override(-0.35f);
                        cg.colorFilter.Override(new Color(0.50f, 0.50f, 0.54f));
                    }
                }},
                // Moss — moss-green walls + earthy tan accent on a gentle green-grey bg.
                { "mapcolor_moss", new Preset {
                    BaseArt = "Poison",
                    MapBlockColor = new Color(0.44f, 0.64f, 0.40f),
                    SecondaryColor = new Color(0.78f, 0.62f, 0.38f),
                    Configure = cg => {
                        cg.saturation.Override(-18f);
                        cg.temperature.Override(8f);
                        cg.postExposure.Override(-0.50f);
                        cg.colorFilter.Override(new Color(0.42f, 0.47f, 0.42f));
                    }
                }},
                // Cream — warm cream walls + soft sky-blue accent on a warm light grey bg.
                { "mapcolor_cream", new Preset {
                    BaseArt = "Gold",
                    MapBlockColor = new Color(0.90f, 0.82f, 0.62f),
                    SecondaryColor = new Color(0.56f, 0.74f, 0.92f),
                    Configure = cg => {
                        cg.saturation.Override(-16f);
                        cg.temperature.Override(-8f);
                        cg.postExposure.Override(-0.32f);
                        cg.colorFilter.Override(new Color(0.54f, 0.53f, 0.52f));
                    }
                }},
                // Lavender — pastel lavender walls + soft gold accent on a lilac-grey bg.
                { "mapcolor_lavender", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.72f, 0.62f, 0.92f),
                    SecondaryColor = new Color(0.92f, 0.80f, 0.50f),
                    Configure = cg => {
                        cg.saturation.Override(-18f);
                        cg.temperature.Override(4f);
                        cg.postExposure.Override(-0.40f);
                        cg.colorFilter.Override(new Color(0.50f, 0.48f, 0.55f));
                    }
                }},
                // Dusk — deep navy walls + warm amber accent on a dim blue-grey bg.
                { "mapcolor_dusk", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.34f, 0.46f, 0.78f),
                    SecondaryColor = new Color(0.96f, 0.64f, 0.30f),
                    Configure = cg => {
                        cg.saturation.Override(-14f);
                        cg.temperature.Override(8f);
                        cg.postExposure.Override(-0.60f);
                        cg.colorFilter.Override(new Color(0.39f, 0.40f, 0.48f));
                    }
                }},
                // Sand — sandy gold walls + cool teal accent on a warm dune-grey bg.
                { "mapcolor_sand", new Preset {
                    BaseArt = "Gold",
                    MapBlockColor = new Color(0.90f, 0.72f, 0.42f),
                    SecondaryColor = new Color(0.38f, 0.72f, 0.74f),
                    Configure = cg => {
                        cg.saturation.Override(-14f);
                        cg.temperature.Override(-8f);
                        cg.postExposure.Override(-0.40f);
                        cg.colorFilter.Override(new Color(0.52f, 0.50f, 0.45f));
                    }
                }},
                // Monochrome — light grey + dark grey walls on a true neutral grey bg.
                // Colorize (Plugin.cs) makes these read as real greys now — no blue bleed.
                { "mapcolor_mono", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.82f, 0.82f, 0.83f),
                    SecondaryColor = new Color(0.42f, 0.42f, 0.43f),
                    Configure = cg => {
                        cg.saturation.Override(-100f);
                        cg.postExposure.Override(-0.42f);
                        cg.colorFilter.Override(new Color(0.49f, 0.49f, 0.49f));
                    }
                }},

                // ── Jewel / nature tones ──

                // Forest — deep evergreen walls + warm bark-brown accent on a BROWN
                // forest-floor bg (Sid, v1.29). Magma-style shadow mood: darker
                // exposure + warm light so the greens glow against deep shade.
                { "mapcolor_forest", new Preset {
                    BaseArt = "Poison",
                    MapBlockColor = new Color(0.26f, 0.54f, 0.30f),
                    // Secondary switched bark-brown → light leaf green (Sid: "make
                    // Forest GREEN; the bg carries the brown now").
                    SecondaryColor = new Color(0.46f, 0.72f, 0.34f),
                    Configure = cg => {
                        cg.saturation.Override(-8f);
                        cg.temperature.Override(10f);
                        cg.postExposure.Override(-0.66f);
                        cg.colorFilter.Override(new Color(0.42f, 0.41f, 0.35f));
                    }
                }},
                // Amethyst — amethyst purple walls + warm gold accent on a violet-grey bg.
                { "mapcolor_amethyst", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.66f, 0.42f, 0.88f),
                    SecondaryColor = new Color(0.90f, 0.72f, 0.38f),
                    Configure = cg => {
                        cg.saturation.Override(-10f);
                        cg.temperature.Override(8f);
                        cg.postExposure.Override(-0.48f);
                        cg.colorFilter.Override(new Color(0.45f, 0.42f, 0.49f));
                    }
                }},
                // Charcoal — neutral light grey + mid slate walls on a dark neutral bg.
                // Kept genuinely grey (no blue lean) — Sid/lopi wanted the original look.
                { "mapcolor_charcoal", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.74f, 0.75f, 0.76f),
                    SecondaryColor = new Color(0.44f, 0.45f, 0.47f),
                    Configure = cg => {
                        cg.saturation.Override(-80f);
                        cg.postExposure.Override(-0.60f);
                        cg.colorFilter.Override(new Color(0.39f, 0.39f, 0.41f));
                    }
                }},
                // Crimson — crimson red walls + teal accent on a dim warm-neutral bg.
                { "mapcolor_crimson_map", new Preset {
                    BaseArt = "Soviet",
                    MapBlockColor = new Color(0.84f, 0.28f, 0.30f),
                    SecondaryColor = new Color(0.30f, 0.68f, 0.64f),
                    Configure = cg => {
                        cg.saturation.Override(-10f);
                        cg.temperature.Override(-8f);
                        cg.postExposure.Override(-0.56f);
                        cg.colorFilter.Override(new Color(0.44f, 0.39f, 0.40f));
                    }
                }},
                // Slate — slate-blue walls + copper accent on a cool grey bg.
                { "mapcolor_slate", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.46f, 0.58f, 0.74f),
                    SecondaryColor = new Color(0.84f, 0.56f, 0.32f),
                    Configure = cg => {
                        cg.saturation.Override(-20f);
                        cg.temperature.Override(6f);
                        cg.postExposure.Override(-0.46f);
                        cg.colorFilter.Override(new Color(0.46f, 0.48f, 0.51f));
                    }
                }},
                // Rose — dusty rose walls + sage-teal accent on a soft mauve-grey bg.
                { "mapcolor_rose", new Preset {
                    BaseArt = "Gold",
                    MapBlockColor = new Color(0.88f, 0.52f, 0.60f),
                    SecondaryColor = new Color(0.44f, 0.74f, 0.64f),
                    Configure = cg => {
                        cg.saturation.Override(-14f);
                        cg.temperature.Override(4f);
                        cg.postExposure.Override(-0.40f);
                        cg.colorFilter.Override(new Color(0.52f, 0.48f, 0.51f));
                    }
                }},
                // Mint — pale mint walls + warm coral accent on a cool light grey bg.
                { "mapcolor_mint", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.56f, 0.88f, 0.70f),
                    SecondaryColor = new Color(0.98f, 0.58f, 0.50f),
                    Configure = cg => {
                        cg.saturation.Override(-10f);
                        cg.temperature.Override(-2f);
                        cg.postExposure.Override(-0.40f);
                        cg.colorFilter.Override(new Color(0.48f, 0.52f, 0.50f));
                    }
                }},
                // Sunset — sunset orange walls + violet accent on a warm dusk-grey bg.
                { "mapcolor_sunset", new Preset {
                    BaseArt = "Gold",
                    MapBlockColor = new Color(0.98f, 0.56f, 0.30f),
                    SecondaryColor = new Color(0.56f, 0.42f, 0.78f),
                    Configure = cg => {
                        cg.saturation.Override(-6f);
                        cg.temperature.Override(-6f);
                        cg.postExposure.Override(-0.48f);
                        cg.colorFilter.Override(new Color(0.48f, 0.43f, 0.47f));
                    }
                }},

                // ── Deep / moody (still grey bg, never black) ──

                // Obsidian — dark blue-grey walls + bright silver-blue accent on a dark cool bg.
                { "mapcolor_obsidian", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.42f, 0.48f, 0.60f),
                    SecondaryColor = new Color(0.66f, 0.74f, 0.88f),
                    Configure = cg => {
                        cg.saturation.Override(-30f);
                        cg.temperature.Override(-8f);
                        cg.postExposure.Override(-0.70f);
                        cg.colorFilter.Override(new Color(0.36f, 0.37f, 0.42f));
                    }
                }},
                // Abyss — deep teal-blue walls + bright cyan accent on a dark teal-grey bg.
                { "mapcolor_abyss", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.24f, 0.52f, 0.64f),
                    SecondaryColor = new Color(0.42f, 0.86f, 0.88f),
                    Configure = cg => {
                        cg.saturation.Override(-10f);
                        cg.temperature.Override(-22f);
                        cg.tint.Override(-8f);
                        cg.postExposure.Override(-0.70f);
                        cg.colorFilter.Override(new Color(0.34f, 0.40f, 0.44f));
                    }
                }},
                // Pine — cool pine blue-green walls + muted rust accent on a cool green-grey
                // bg. Cooler and woodsier than Forest's warmer evergreen.
                { "mapcolor_pine", new Preset {
                    BaseArt = "Poison",
                    MapBlockColor = new Color(0.28f, 0.52f, 0.44f),
                    // Secondary switched rust-brown → lighter pine green (Sid: pine
                    // walls read brown; keep the whole skin in the green family).
                    SecondaryColor = new Color(0.44f, 0.68f, 0.52f),
                    Configure = cg => {
                        cg.saturation.Override(-14f);
                        cg.temperature.Override(-6f);
                        cg.postExposure.Override(-0.60f);
                        cg.colorFilter.Override(new Color(0.37f, 0.43f, 0.41f));
                    }
                }},
                // Iron — steel grey walls + oxidized-rust accent on a cool neutral grey bg.
                { "mapcolor_iron", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.56f, 0.60f, 0.66f),
                    SecondaryColor = new Color(0.82f, 0.50f, 0.28f),
                    Configure = cg => {
                        cg.saturation.Override(-30f);
                        cg.temperature.Override(4f);
                        cg.postExposure.Override(-0.54f);
                        cg.colorFilter.Override(new Color(0.42f, 0.43f, 0.46f));
                    }
                }},
                // Burgundy — wine-red walls + slate-blue accent on a dim plum-grey bg.
                { "mapcolor_burgundy", new Preset {
                    BaseArt = "Soviet",
                    MapBlockColor = new Color(0.68f, 0.24f, 0.36f),
                    SecondaryColor = new Color(0.38f, 0.54f, 0.82f),
                    Configure = cg => {
                        cg.saturation.Override(-10f);
                        cg.temperature.Override(6f);
                        cg.postExposure.Override(-0.64f);
                        cg.colorFilter.Override(new Color(0.41f, 0.36f, 0.42f));
                    }
                }},
                // Magma — molten oxblood-red walls + glowing amber-YELLOW accent on a dark
                // warm bg. Colorize (Plugin.cs) finally lets the yellow render (multiply
                // turned it dark red on the Soviet base — the long-standing "no yellow" bug).
                { "mapcolor_magma", new Preset {
                    BaseArt = "Soviet",
                    MapBlockColor = new Color(0.82f, 0.26f, 0.16f),
                    SecondaryColor = new Color(0.99f, 0.76f, 0.24f),
                    Configure = cg => {
                        cg.saturation.Override(-4f);
                        cg.temperature.Override(20f);
                        cg.postExposure.Override(-0.54f);
                        cg.colorFilter.Override(new Color(0.46f, 0.40f, 0.35f));
                    }
                }},
                // Velvet — royal purple walls + gilded gold accent on a deep purple bg.
                // Magma-style shadow mood (Sid, v1.29): deeper exposure, richer
                // saturation — candle-lit theatre look.
                { "mapcolor_velvet", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.50f, 0.28f, 0.70f),
                    SecondaryColor = new Color(0.90f, 0.70f, 0.36f),
                    Configure = cg => {
                        cg.saturation.Override(-4f);
                        cg.temperature.Override(8f);
                        cg.postExposure.Override(-0.70f);
                        cg.colorFilter.Override(new Color(0.42f, 0.36f, 0.48f));
                    }
                }},
                // Blackwood — charred slate timber walls + smoldering ember accent on a dark
                // warm bg. (Walls deliberately slate, not brown, so they don't blend with
                // the brown physics boxes.)
                { "mapcolor_blackwood", new Preset {
                    BaseArt = "Gold",
                    MapBlockColor = new Color(0.50f, 0.50f, 0.54f),
                    SecondaryColor = new Color(0.90f, 0.54f, 0.24f),
                    Configure = cg => {
                        cg.saturation.Override(-26f);
                        cg.temperature.Override(12f);
                        cg.postExposure.Override(-0.66f);
                        cg.colorFilter.Override(new Color(0.38f, 0.37f, 0.38f));
                    }
                }},

                // ── Premium (v1.29) — sparkle skins ──
                // Sparkle = per-particle random-between(layer color, Sparkle color) on
                // the walls: every particle glints its own shade. Gold base art brings
                // the bloom that sells the glitter.

                // Gilded — molten gold walls glinting to white-gold, deep bronze bg.
                { "mapcolor_gilded", new Preset {
                    BaseArt = "Gold",
                    MapBlockColor = new Color(1.00f, 0.80f, 0.26f),
                    SecondaryColor = new Color(0.94f, 0.62f, 0.18f),
                    Sparkle = new Color(1.00f, 0.97f, 0.80f),
                    Configure = cg => {
                        cg.saturation.Override(8f);
                        cg.temperature.Override(18f);
                        cg.postExposure.Override(-0.52f);
                        cg.colorFilter.Override(new Color(0.50f, 0.45f, 0.36f));
                    }
                }},
                // Platinum — cold silver walls glinting to pure white, gunmetal bg.
                { "mapcolor_platinum", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.80f, 0.84f, 0.90f),
                    SecondaryColor = new Color(0.58f, 0.62f, 0.70f),
                    Sparkle = new Color(1.00f, 1.00f, 1.00f),
                    Configure = cg => {
                        cg.saturation.Override(-55f);
                        cg.temperature.Override(-4f);
                        cg.postExposure.Override(-0.54f);
                        cg.colorFilter.Override(new Color(0.44f, 0.45f, 0.48f));
                    }
                }},
                // Aurora — northern-lights walls shimmering between polar teal and
                // violet over a polar-night bg.
                { "mapcolor_aurora", new Preset {
                    BaseArt = "Sky",
                    MapBlockColor = new Color(0.22f, 0.88f, 0.62f),
                    SecondaryColor = new Color(0.58f, 0.36f, 0.96f),
                    Sparkle = new Color(0.55f, 0.95f, 1.00f),
                    Configure = cg => {
                        cg.saturation.Override(10f);
                        cg.temperature.Override(-10f);
                        cg.postExposure.Override(-0.66f);
                        cg.colorFilter.Override(new Color(0.38f, 0.42f, 0.47f));
                    }
                }},
            };

        public static bool IsCustomSku(string sku) => sku != null && _presets.ContainsKey(sku);

        /// <summary>Human-readable skin name for the Shift toast, e.g. "mapcolor_magma" →
        /// "Magma", "mapcolor_crimson_map" → "Crimson". Title-cases the sku tail.</summary>
        public static string FriendlyName(string sku)
        {
            if (string.IsNullOrEmpty(sku)) return "Default";
            string s = sku.StartsWith("mapcolor_", StringComparison.OrdinalIgnoreCase) ? sku.Substring(9) : sku;
            if (s.EndsWith("_map", StringComparison.OrdinalIgnoreCase)) s = s.Substring(0, s.Length - 4);
            s = s.Replace('_', ' ').Trim();
            if (s.Length == 0) return "Default";
            // Title-case each word.
            var parts = s.Split(' ');
            for (int i = 0; i < parts.Length; i++)
                if (parts[i].Length > 0) parts[i] = char.ToUpperInvariant(parts[i][0]) + parts[i].Substring(1);
            return string.Join(" ", parts);
        }

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

        // ── Background (atmosphere) colors, v1.29 ─────────────────────────────
        // Dedicated per-skin BACKDROP hue for the ArtInstance atmosphere
        // particles. Design rules (Sid's feedback: "backgrounds are too
        // grey/blue... more diverse... at least slightly different from the
        // walls so they don't all blend into one"):
        //   * Same color FAMILY as the skin's primary (the map must still read
        //     as its name) but hue-shifted and saturated so the backdrop is
        //     clearly its own layer, never a dimmer copy of the walls.
        //   * Warm skins get warm backdrops, cool skins cool — but NOT grey
        //     unless the skin is deliberately monochrome (mono/charcoal).
        // The bg pass in Plugin.cs lerps toward this from grey and applies its
        // own luminance lift, so these read darker in-game than raw values.
        // v1.29 second pass (Sid's feedback: "still too blue — only 2-3 blue
        // backgrounds; Mono/Lavender/Pine/Charcoal same-ish as their walls;
        // Forest brown; backgrounds should COMPLEMENT walls, not clone them").
        // Blue is reserved for the three naturally-blue skins: dusk, obsidian,
        // abyss (+ aurora's polar night). Everything else is warm or green.
        private static readonly Dictionary<string, Color> _backgroundColors =
            new Dictionary<string, Color>(StringComparer.OrdinalIgnoreCase)
            {
                { "mapcolor_soft",        new Color(0.62f, 0.50f, 0.40f) }, // warm taupe (peach family)
                { "mapcolor_moss",        new Color(0.30f, 0.42f, 0.22f) }, // deep olive green
                { "mapcolor_cream",       new Color(0.72f, 0.52f, 0.30f) }, // warm amber
                { "mapcolor_lavender",    new Color(0.52f, 0.42f, 0.68f) }, // muted lavender (same-ish as walls)
                { "mapcolor_dusk",        new Color(0.24f, 0.26f, 0.52f) }, // indigo night (BLUE - by design)
                { "mapcolor_sand",        new Color(0.72f, 0.46f, 0.22f) }, // burnt dune orange
                { "mapcolor_mono",        new Color(0.42f, 0.42f, 0.44f) }, // grey (same-ish as walls, darker)
                { "mapcolor_forest",      new Color(0.44f, 0.30f, 0.16f) }, // BROWN forest floor (Sid)
                { "mapcolor_amethyst",    new Color(0.50f, 0.24f, 0.46f) }, // plum-magenta
                { "mapcolor_charcoal",    new Color(0.27f, 0.27f, 0.29f) }, // dark slate (same-ish as walls)
                { "mapcolor_crimson_map", new Color(0.48f, 0.14f, 0.18f) }, // deep blood red
                { "mapcolor_slate",       new Color(0.52f, 0.36f, 0.24f) }, // warm copper behind cool walls
                { "mapcolor_rose",        new Color(0.56f, 0.26f, 0.34f) }, // deep rose
                { "mapcolor_mint",        new Color(0.20f, 0.44f, 0.28f) }, // deep leaf green (not teal)
                { "mapcolor_sunset",      new Color(0.66f, 0.28f, 0.30f) }, // hot coral-red horizon
                { "mapcolor_obsidian",    new Color(0.20f, 0.24f, 0.40f) }, // steel indigo (BLUE - by design)
                { "mapcolor_abyss",       new Color(0.08f, 0.24f, 0.46f) }, // ocean depth (BLUE - by design)
                { "mapcolor_pine",        new Color(0.20f, 0.40f, 0.34f) }, // deep pine (same-ish as walls, darker)
                { "mapcolor_iron",        new Color(0.40f, 0.30f, 0.22f) }, // rusted umber
                { "mapcolor_burgundy",    new Color(0.36f, 0.14f, 0.24f) }, // deep wine
                { "mapcolor_magma",       new Color(0.64f, 0.28f, 0.06f) }, // molten burnt orange (Sid likes it)
                { "mapcolor_velvet",      new Color(0.34f, 0.18f, 0.44f) }, // deep royal purple (was indigo)
                { "mapcolor_blackwood",   new Color(0.42f, 0.22f, 0.09f) }, // smoldering ember-brown
                // Premium
                { "mapcolor_gilded",      new Color(0.42f, 0.30f, 0.10f) }, // deep bronze vault
                { "mapcolor_platinum",    new Color(0.24f, 0.26f, 0.29f) }, // gunmetal
                { "mapcolor_aurora",      new Color(0.10f, 0.14f, 0.28f) }, // polar night
            };

        /// <summary>Dedicated backdrop hue for the atmosphere particles, or null
        /// to fall back to the primary-leaning legacy tint.</summary>
        public static Color? GetBackgroundColor(string sku)
        {
            if (sku != null && _backgroundColors.TryGetValue(sku, out var c)) return c;
            return null;
        }

        /// <summary>Premium sparkle endpoint — wall particles emit random-between
        /// (layer color, this) when set. Null for standard skins.</summary>
        public static Color? GetSparkleColor(string sku)
        {
            if (sku != null && _presets.TryGetValue(sku, out var p)) return p.Sparkle;
            return null;
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
                // OVERRIDE the colorFilter to LEAN toward the skin's PRIMARY color. The
                // per-preset filters were near-neutral grey so the whole scene read as
                // grey/samey no matter the skin (Sid: "no change noticed" — the small wall
                // particles alone can't shift the impression; the screen-wide ColorGrading
                // can). colorFilter multiplies the entire rendered scene, so this makes the
                // map unmistakably its named color. Grey skins (mono/charcoal) have a grey
                // primary, so they stay grey for free. Moderate blend keeps gameplay readable.
                try
                {
                    // v1.29 FINAL model (third pass — see learning #116): the big flat
                    // backdrop is the CAMERA CLEAR COLOR (an editor constant; vignette
                    // fakes the gradient). Vanilla arts repaint the whole screen with
                    // brutally strong colorFilters — which is exactly why a strong
                    // filter here wrecked the walls ("Forest completely not green",
                    // walls == background). Correct split: the camera clear color
                    // carries the designed BACKGROUND (set in Plugin.cs,
                    // ApplyCameraBackground), and the filter stays NEAR-NEUTRAL with a
                    // mild primary lean so walls/geometry keep their own colors.
                    Color prim = GetMapBlockColor(sku) ?? new Color(0.5f, 0.5f, 0.5f);
                    Color litPrim = new Color(
                        Mathf.Clamp01(0.35f + prim.r * 0.75f),
                        Mathf.Clamp01(0.35f + prim.g * 0.75f),
                        Mathf.Clamp01(0.35f + prim.b * 0.75f));
                    Color cf = Color.Lerp(new Color(0.5f, 0.5f, 0.5f), litPrim, 0.30f);
                    cg.colorFilter.Override(cf);
                    // Keep the hue vivid for COLORED skins (don't let a preset's negative
                    // saturation mute the scene). Grey skins (mono/charcoal — primary
                    // r≈g≈b) keep THEIR preset saturation (e.g. -100) untouched.
                    float mx = Mathf.Max(prim.r, Mathf.Max(prim.g, prim.b));
                    float mn = Mathf.Min(prim.r, Mathf.Min(prim.g, prim.b));
                    bool greySkin = (mx - mn) < 0.08f;
                    if (!greySkin) cg.saturation.Override(12f);
                }
                catch { }
                clone.AddSettings(cg);

                // Bloom pass (v1.29 round 7, Sid: "I like the effect but it needs
                // to be set to like right above 0"). The base arts ship strong,
                // TINTED bloom — on the cyan-leaning Sky profile that tint washes
                // warm backdrops toward GREEN (the "still green" maps) and is most
                // of the wall flashiness. Keep the effect but barely: low intensity,
                // neutral white tint, slightly higher threshold so only true
                // highlights glow.
                try
                {
                    UnityEngine.Rendering.PostProcessing.Bloom bloom;
                    if (clone.TryGetSettings(out bloom) && bloom != null)
                    {
                        Plugin.Log.LogInfo($"[MAPCOLOR] {sku}: base bloom intensity={bloom.intensity.value:F1} tint={bloom.color.value} threshold={bloom.threshold.value:F2}");
                        bloom.intensity.Override(Mathf.Min(bloom.intensity.value, 1.2f));
                        bloom.color.Override(Color.white);
                        bloom.threshold.Override(Mathf.Max(bloom.threshold.value, 1.05f));
                    }
                }
                catch (Exception bx) { Plugin.Log.LogWarning($"[MAPCOLOR] bloom tune failed for {sku}: {bx.Message}"); }

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
