using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// File-backed TMP fallback fonts for glyphs missing from ROUNDS' Latin-only
    /// atlases. TMP and TextCore stay reflection-only so the plugin does not need
    /// new assembly references.
    /// </summary>
    internal static class UnicodeFallback
    {
        private const int SamplingPointSize = 48;
        private const int AtlasSize = 2048;
        private const int AtlasPadding = 5;
        private const int MaxAddedGlyphs = 1200;
        private const int GlyphRenderModeSdffaa = 4165;
        private const int GlyphLoadFlagsForSdffaa = 10; // NO_HINTING | NO_BITMAP
        // A font whose face fails to load this many times is treated as
        // permanently unusable and dropped from the fallback chain, so the
        // "don't condemn codepoints a skipped font never saw" rule below can
        // never turn into an unbounded retry loop.
        private const int MaxFaceLoadFailures = 3;

        private static readonly List<FontState> _fonts = new List<FontState>();
        private static readonly HashSet<uint> _knownCodepoints = new HashSet<uint>();
        private static readonly HashSet<uint> _missingCodepoints = new HashSet<uint>();

        private static Type _fontAssetType;
        private static Type _tmpCharacterType;
        private static Type _fontEngineType;
        private static Type _glyphRectType;
        private static Type _glyphRenderModeType;
        private static Type _glyphPackingModeType;
        private static Type _glyphLoadFlagsType;
        private static Type _atlasPopulationModeType;
        private static Type _shaderUtilitiesType;

        private static MethodInfo _initializeFontEngine;
        private static MethodInfo _loadFontFace;
        private static MethodInfo _getFaceInfo;
        private static MethodInfo _tryGetGlyph;
        private static MethodInfo _tryAddGlyphToTexture;
        private static MethodInfo _readFontAssetDefinition;
        private static ConstructorInfo _tmpCharacterConstructor;

        private static bool _installed;
        private static bool _failureLogged;
        private static bool _capLogged;
        private static bool _batchFailureLogged;
        private static int _totalAdded;   // diagnostics only; the cap is per-atlas

        public static bool Ready
        {
            get { return _installed && _fonts.Count > 0; }
        }

        /// <summary>Re-arm on a live mod-language switch (called from
        /// I18n.SetLocale before LocaleChanged fires).
        ///
        /// WHY THIS EXISTS: Install() is one-shot behind _installed and its
        /// only other caller — UIFactory.InitFont — sets fontReady=true on the
        /// same line BEFORE calling it, so InitFont's `if (fontReady) return`
        /// guard means a failed install is never retried and EnsureCharacters
        /// no-ops for the whole session (every non-ASCII glyph then renders as
        /// nothing, not even a box). Relaunching was the only recovery path,
        /// which is exactly the reported "font doesn't apply until restart".
        ///
        /// Three jobs, in order: retry Install() when not Ready; clear the
        /// permanently-missing poison set so codepoints condemned under the
        /// old font set / after a transient FontEngine hiccup get one more
        /// chance; preload the NEW locale's script range (the install-time
        /// preload list is fixed and never re-run).</summary>
        public static void OnLocaleChanged(string locale)
        {
            bool wasReady = Ready;
            if (!Ready)
            {
                // _installed true with no fonts can only come from a partially
                // rolled-back install; clear it so Install()'s guard lets the
                // retry through.
                _installed = false;
                _failureLogged = false;   // one warning per retry, not per session
                try { Install(); }
                catch (Exception ex)
                { Plugin.Log.LogWarning("[FONT] fallback install retry threw: " + UnwrapMessage(ex)); }
                if (Ready)
                    Plugin.Log.LogInfo("[FONT] fallback install RECOVERED on locale change ('"
                        + (locale ?? "?") + "') — non-ASCII text renders from now on");
            }
            if (!Ready) return;

            int rearmed = _missingCodepoints.Count;
            _missingCodepoints.Clear();
            _capLogged = false;
            _batchFailureLogged = false;

            int before = _totalAdded;
            try { AddRanges(RangesForLocale(locale)); }
            catch (Exception ex)
            { Plugin.Log.LogWarning("[FONT] locale preload failed: " + UnwrapMessage(ex)); }

            Plugin.Log.LogInfo("[FONT] re-armed for locale '" + (locale ?? "?") + "': "
                + (_totalAdded - before) + " glyphs preloaded, " + rearmed
                + " previously-missing codepoint(s) re-armed"
                + (wasReady ? "" : " (after an install retry)"));
        }

        /// <summary>Install retry for any caller that notices !Ready. With no
        /// locale hint only the always-safe Latin range is warmed; glyphs
        /// outside it still resolve on demand through EnsureCharacters, so
        /// this is a slower first paint, not a missing one. Prefer
        /// OnLocaleChanged(locale) whenever a locale is known.</summary>
        public static void Retry() { OnLocaleChanged(null); }

        /// <summary>Script blocks worth warming for a locale. Latin-1
        /// Supplement + Latin Extended-A is always included (accented Latin is
        /// reachable from any locale via player names and chat).</summary>
        private static CodepointRange[] RangesForLocale(string locale)
        {
            var latin = new CodepointRange(0x00A0u, 0x017Fu);
            string l = locale == null ? "" : locale.ToLowerInvariant();
            if (l.StartsWith("ru", StringComparison.Ordinal)
                || l.StartsWith("uk", StringComparison.Ordinal)
                || l.StartsWith("be", StringComparison.Ordinal)
                || l.StartsWith("bg", StringComparison.Ordinal)
                || l.StartsWith("sr", StringComparison.Ordinal)
                || l.StartsWith("kk", StringComparison.Ordinal))
                return new[] { latin, new CodepointRange(0x0400u, 0x04FFu) };
            if (l.StartsWith("el", StringComparison.Ordinal))
                return new[] { latin, new CodepointRange(0x0370u, 0x03FFu) };
            return new[] { latin };
        }

        public static void Install()
        {
            if (_installed) return;

            var built = new List<FontState>();
            var registrations = new List<ListRegistration>();
            try
            {
                ResolveReflection();

                string fontsDirectory = Environment.GetFolderPath(Environment.SpecialFolder.Fonts);
                if (string.IsNullOrEmpty(fontsDirectory) || !Directory.Exists(fontsDirectory))
                    fontsDirectory = @"C:\Windows\Fonts";
                // Proton/Steam Deck (Codex v1.36 client find 11): the Windows
                // fonts dir may be missing or nearly empty (a Wine prefix
                // ships almost nothing), but Font.GetPathsToOSFonts() still
                // enumerates real font FILES via the platform's own font
                // system (GDI under Wine bridges to host fontconfig), and
                // those paths feed the same FontEngine.LoadFontFace pipeline.
                // So: dir + OS-paths are BOTH consulted; Linux-common
                // Cyrillic-capable families (DejaVu/Liberation/Noto) join
                // every candidate list instead of throwing "no fallback".
                if (!Directory.Exists(fontsDirectory)) fontsDirectory = null;
                string[] osFontPaths = GetOsFontPaths();
                if (fontsDirectory == null && osFontPaths.Length == 0)
                    throw new InvalidOperationException(
                        "font selection failed: no OS fonts directory and no OS font paths (Proton/non-Windows?)");

                string latinPath = FindFont(fontsDirectory, osFontPaths, new[]
                {
                    // "segoeui.ttf" — the old first entry was the TYPO
                    // "seguiui.ttf" (no such file anywhere), so the Latin
                    // fallback was silently Arial in production.
                    "segoeui.ttf", "arial.ttf", "tahoma.ttf",
                    // Linux/Proton host fonts — all three cover Latin-ext +
                    // Greek + Cyrillic, which is what the ru locale needs.
                    "DejaVuSans.ttf", "LiberationSans-Regular.ttf",
                    "NotoSans-Regular.ttf", "FreeSans.ttf"
                });
                if (latinPath == null)
                    throw new InvalidOperationException("font selection failed: no Latin fallback file found");

                built.Add(BuildFontAsset(latinPath, GetAssetName(latinPath)));

                // Round-2 item 5: a linked player's display name is
                // Mathematical Alphanumeric Symbols (U+1D544 etc., astral
                // plane) — no Latin/CJK pick carries that block, so every
                // glyph fell into _missingCodepoints and the name boxed
                // forever. Segoe UI Symbol (or Cambria Math) covers the
                // math/letterlike/misc-symbol blocks. Own try: a broken
                // symbol font must not roll back the whole install.
                try
                {
                    string symbolPath = FindFont(fontsDirectory, osFontPaths, new[]
                    {
                        "seguisym.ttf", "cambria.ttc",
                        "NotoSansSymbols-Regular.ttf", "NotoSansSymbols2-Regular.ttf"
                    });
                    if (symbolPath != null
                        && !string.Equals(symbolPath, latinPath, StringComparison.OrdinalIgnoreCase))
                        built.Add(BuildFontAsset(symbolPath, GetAssetName(symbolPath)));
                }
                catch (Exception symEx)
                {
                    Plugin.Log.LogWarning("[FONT] symbol fallback skipped: " + UnwrapMessage(symEx));
                }

                // Review find 1: one first-match CJK asset is not enough. Microsoft
                // YaHei (Chinese) carries no Hangul, so a Korean name still rendered
                // as boxes on a PC that also had Malgun Gothic installed. Build one
                // asset per SCRIPT FAMILY (Chinese / Japanese / Korean) and let
                // EnsureCharacters try each in turn. Duplicate paths are skipped —
                // some systems point several of these at the same file.
                var cjkFamilies = new[]
                {
                    new[] { "msyh.ttc", "msyh.ttf", "simsun.ttc",        // Chinese
                            "NotoSansCJK-Regular.ttc", "NotoSansCJKsc-Regular.otf",
                            "WenQuanYiMicroHei.ttf" },
                    new[] { "YuGothM.ttc", "meiryo.ttc", "msgothic.ttc", // Japanese
                            "NotoSansCJKjp-Regular.otf" },
                    new[] { "malgun.ttf", "gulim.ttc", "batang.ttc",     // Korean
                            "NotoSansCJKkr-Regular.otf" },
                };
                var chosen = new List<string>();
                for (int fi = 0; fi < cjkFamilies.Length; fi++)
                {
                    string cjkPath = FindFont(fontsDirectory, osFontPaths, cjkFamilies[fi]);
                    if (cjkPath == null) continue;
                    bool dup = false;
                    for (int ci = 0; ci < chosen.Count; ci++)
                        if (string.Equals(chosen[ci], cjkPath, StringComparison.OrdinalIgnoreCase))
                        { dup = true; break; }
                    if (dup) continue;
                    chosen.Add(cjkPath);
                    built.Add(BuildFontAsset(cjkPath, GetAssetName(cjkPath)));
                }

                _fonts.AddRange(built);
                int preloadedBefore = _totalAdded;
                AddRanges(new[]
                {
                    new CodepointRange(0x00A0u, 0x017Fu),
                    new CodepointRange(0x0370u, 0x03FFu),
                    new CodepointRange(0x0400u, 0x04FFu)
                });
                int preloaded = _totalAdded - preloadedBefore;

                object gameFont = FindGameFont();
                if (gameFont == null)
                    throw new InvalidOperationException("registration failed: game font was not available");

                var assets = new List<object>();
                for (int i = 0; i < _fonts.Count; i++) assets.Add(_fonts[i].Asset);
                RegisterFallbacks(gameFont, assets, registrations);

                _installed = true;
                _failureLogged = false;

                var names = new string[_fonts.Count];
                var sources = new string[_fonts.Count];
                for (int i = 0; i < _fonts.Count; i++)
                {
                    names[i] = _fonts[i].Name;
                    sources[i] = Path.GetFileName(_fonts[i].Path);
                }
                Plugin.Log.LogInfo("[FONT] fallback ready: " + string.Join(", ", names)
                    + " (" + preloaded + " glyphs preloaded, source="
                    + string.Join(",", sources) + ")");
            }
            catch (Exception ex)
            {
                RollBackRegistrations(registrations);
                _fonts.Clear();
                _knownCodepoints.Clear();
                _missingCodepoints.Clear();
                _totalAdded = 0;
                DestroyBuiltFonts(built);

                if (!_failureLogged)
                {
                    Plugin.Log.LogWarning("[FONT] fallback install failed: " + UnwrapMessage(ex));
                    _failureLogged = true;
                }
            }
        }

        public static void EnsureCharacters(string s)
        {
            if (!_installed || string.IsNullOrEmpty(s)) return;

            bool allAscii = true;
            for (int i = 0; i < s.Length; i++)
            {
                if (s[i] >= 0x80)
                {
                    allAscii = false;
                    break;
                }
            }
            if (allAscii) return;

            List<uint> requested = null;
            try
            {
                HashSet<uint> seenThisCall = null;
                for (int i = 0; i < s.Length; i++)
                {
                    uint unicode;
                    char current = s[i];
                    if (char.IsHighSurrogate(current) && i + 1 < s.Length
                        && char.IsLowSurrogate(s[i + 1]))
                    {
                        unicode = (uint)char.ConvertToUtf32(current, s[i + 1]);
                        i++;
                    }
                    else
                    {
                        unicode = current;
                    }

                    if (unicode < 0x80u
                        || _knownCodepoints.Contains(unicode)
                        || _missingCodepoints.Contains(unicode))
                        continue;

                    if (requested == null)
                    {
                        requested = new List<uint>();
                        seenThisCall = new HashSet<uint>();
                    }
                    if (!seenThisCall.Add(unicode)) continue;
                    requested.Add(unicode);
                }

                if (requested == null) return;
                AddCodepoints(requested);
            }
            catch (Exception ex)
            {
                // NO BLANKET POISONING. This catch used to mark the ENTIRE
                // requested batch permanently missing, and the one thing that
                // actually throws out here — EnsureFaceLoaded, called per font
                // inside AddCodepoints — meant a single transient FontEngine
                // hiccup condemned codepoints that were never even queried, for
                // the rest of the session (they then render as nothing).
                // Genuine absences are condemned inside AddCodepoints, AFTER
                // every live fallback font has actually been asked.
                LogBatchFailureOnce(ex);
            }
        }

        private static void LogBatchFailureOnce(Exception ex)
        {
            if (_batchFailureLogged) return;
            _batchFailureLogged = true;
            Plugin.Log.LogWarning("[FONT] glyph batch failed: " + UnwrapMessage(ex)
                + " (repeats are silent until the next locale switch)");
        }

        private static void ResolveReflection()
        {
            _fontAssetType = RequireType("TMPro.TMP_FontAsset, Unity.TextMeshPro");
            _tmpCharacterType = RequireType("TMPro.TMP_Character, Unity.TextMeshPro");
            _atlasPopulationModeType = RequireType("TMPro.AtlasPopulationMode, Unity.TextMeshPro");
            _shaderUtilitiesType = RequireType("TMPro.ShaderUtilities, Unity.TextMeshPro");

            const string textCoreAssembly = "UnityEngine.TextCoreFontEngineModule";
            _fontEngineType = RequireType("UnityEngine.TextCore.LowLevel.FontEngine, " + textCoreAssembly);
            _glyphRectType = RequireType("UnityEngine.TextCore.GlyphRect, " + textCoreAssembly);
            _glyphRenderModeType = RequireType("UnityEngine.TextCore.LowLevel.GlyphRenderMode, " + textCoreAssembly);
            _glyphPackingModeType = RequireType("UnityEngine.TextCore.LowLevel.GlyphPackingMode, " + textCoreAssembly);
            _glyphLoadFlagsType = RequireType("UnityEngine.TextCore.LowLevel.GlyphLoadFlags, " + textCoreAssembly);

            const BindingFlags publicStatic = BindingFlags.Public | BindingFlags.Static;
            _initializeFontEngine = RequireMethod(_fontEngineType, "InitializeFontEngine", publicStatic, 0);
            _loadFontFace = FindMethod(_fontEngineType, "LoadFontFace", publicStatic,
                new[] { typeof(string), typeof(int) });
            _getFaceInfo = RequireMethod(_fontEngineType, "GetFaceInfo", publicStatic, 0);
            _tryGetGlyph = FindOutMethod(_fontEngineType, "TryGetGlyphWithUnicodeValue",
                publicStatic, 3);
            _tryAddGlyphToTexture = FindOutMethod(_fontEngineType, "TryAddGlyphToTexture",
                BindingFlags.NonPublic | BindingFlags.Static, 8);
            _readFontAssetDefinition = RequireMethod(_fontAssetType,
                "ReadFontAssetDefinition", BindingFlags.Public | BindingFlags.Instance, 0);

            Type glyphType = RequireType("UnityEngine.TextCore.Glyph, " + textCoreAssembly);
            _tmpCharacterConstructor = _tmpCharacterType.GetConstructor(new[]
            {
                typeof(uint), _fontAssetType, glyphType
            });

            if (_loadFontFace == null) throw new MissingMethodException("FontEngine.LoadFontFace(path,size)");
            if (_tryGetGlyph == null) throw new MissingMethodException("FontEngine.TryGetGlyphWithUnicodeValue");
            if (_tryAddGlyphToTexture == null) throw new MissingMethodException("FontEngine.TryAddGlyphToTexture");
            if (_tmpCharacterConstructor == null) throw new MissingMethodException("TMP_Character(unicode,font,glyph)");

            object initResult = _initializeFontEngine.Invoke(null, null);
            if (Convert.ToInt32(initResult) != 0)
                throw new InvalidOperationException("font engine initialization returned " + initResult);
        }

        private static FontState BuildFontAsset(string path, string assetName)
        {
            EnsureFaceLoaded(path);

            object asset = ScriptableObject.CreateInstance(_fontAssetType);
            if (asset == null) throw new InvalidOperationException("asset creation failed for " + Path.GetFileName(path));

            var state = new FontState
            {
                Path = path,
                Name = assetName,
                Asset = asset
            };

            try
            {
                ((UnityEngine.Object)asset).name = assetName;
                // Learning #16: runtime-created assets must survive ROUNDS'
                // scene changes. HideAndDontSave carries DontUnloadUnusedAsset,
                // which is the load-bearing bit here — a scene transition's
                // Resources.UnloadUnusedAssets would otherwise be free to
                // collect this font asset / atlas / material while TMP's
                // fallback tables still reference them, and the glyphs would
                // silently stop rendering mid-session.
                ((UnityEngine.Object)asset).hideFlags = HideFlags.HideAndDontSave;
                SetMember(asset, "m_Version", "1.1.0");
                SetMember(asset, "faceInfo", _getFaceInfo.Invoke(null, null));
                SetMember(asset, "atlasPopulationMode", Enum.ToObject(_atlasPopulationModeType, 0));
                SetMember(asset, "atlasWidth", AtlasSize);
                SetMember(asset, "atlasHeight", AtlasSize);
                SetMember(asset, "atlasPadding", AtlasPadding);
                SetMember(asset, "atlasRenderMode", Enum.ToObject(_glyphRenderModeType, GlyphRenderModeSdffaa));
                SetMember(asset, "isMultiAtlasTexturesEnabled", false);

                state.Texture = new Texture2D(AtlasSize, AtlasSize, TextureFormat.Alpha8, false);
                state.Texture.name = assetName + " Atlas";
                state.Texture.hideFlags = HideFlags.HideAndDontSave;
                SetMember(asset, "atlasTextures", new[] { state.Texture });

                Shader shader = GetStaticMember(_shaderUtilitiesType, "ShaderRef_MobileSDF") as Shader;
                if (shader == null) throw new InvalidOperationException("Mobile SDF shader lookup failed");

                state.Material = new Material(shader);
                state.Material.name = assetName + " Material";
                state.Material.hideFlags = HideFlags.HideAndDontSave;
                state.Material.SetTexture(GetShaderId("ID_MainTex"), state.Texture);
                state.Material.SetFloat(GetShaderId("ID_TextureWidth"), AtlasSize);
                state.Material.SetFloat(GetShaderId("ID_TextureHeight"), AtlasSize);
                state.Material.SetFloat(GetShaderId("ID_GradientScale"), AtlasPadding + 1);
                state.Material.SetFloat(GetShaderId("ID_WeightNormal"),
                    Convert.ToSingle(GetMember(asset, "normalStyle")));
                state.Material.SetFloat(GetShaderId("ID_WeightBold"),
                    Convert.ToSingle(GetMember(asset, "boldStyle")));
                SetMember(asset, "material", state.Material);

                Type rectListType = typeof(List<>).MakeGenericType(_glyphRectType);
                state.FreeGlyphRects = (IList)Activator.CreateInstance(rectListType);
                state.UsedGlyphRects = (IList)Activator.CreateInstance(rectListType);
                state.FreeGlyphRects.Add(Activator.CreateInstance(_glyphRectType,
                    new object[] { 0, 0, AtlasSize - 1, AtlasSize - 1 }));
                SetMember(asset, "freeGlyphRects", state.FreeGlyphRects);
                SetMember(asset, "usedGlyphRects", state.UsedGlyphRects);

                _readFontAssetDefinition.Invoke(asset, null);
                state.GlyphTable = GetMember(asset, "glyphTable") as IList;
                state.CharacterTable = GetMember(asset, "characterTable") as IList;
                if (state.GlyphTable == null || state.CharacterTable == null)
                    throw new InvalidOperationException("font tables were not initialized");

                return state;
            }
            catch
            {
                DestroyFont(state);
                throw;
            }
        }

        private static void AddRanges(CodepointRange[] ranges)
        {
            var requested = new List<uint>();
            for (int r = 0; r < ranges.Length; r++)
            {
                for (uint unicode = ranges[r].First; unicode <= ranges[r].Last; unicode++)
                    requested.Add(unicode);
            }
            AddCodepoints(requested);
        }

        private static void AddCodepoints(List<uint> requested)
        {
            if (requested == null || requested.Count == 0) return;

            var remaining = new List<uint>();
            for (int i = 0; i < requested.Count; i++)
            {
                uint unicode = requested[i];
                if (!_knownCodepoints.Contains(unicode) && !_missingCodepoints.Contains(unicode))
                    remaining.Add(unicode);
            }

            bool skippedFont = false;
            for (int fontIndex = 0; fontIndex < _fonts.Count && remaining.Count > 0; fontIndex++)
            {
                FontState state = _fonts[fontIndex];
                if (state.Disabled) continue;
                // Guarded per font: a face-load failure is the one error that
                // hits BEFORE any codepoint was queried, and it used to throw
                // straight out of AddCodepoints into EnsureCharacters' blanket
                // catch. Skip this font, keep the rest of the chain, and record
                // that the pass was incomplete (see the tail).
                try { EnsureFaceLoaded(state.Path); }
                catch (Exception faceEx)
                {
                    state.FaceLoadFailures++;
                    skippedFont = true;
                    if (state.FaceLoadFailures >= MaxFaceLoadFailures)
                    {
                        state.Disabled = true;
                        Plugin.Log.LogWarning("[FONT] fallback '" + state.Name + "' disabled after "
                            + state.FaceLoadFailures + " face-load failures: " + UnwrapMessage(faceEx));
                    }
                    else if (state.FaceLoadFailures == 1)
                    {
                        Plugin.Log.LogWarning("[FONT] face load failed for '" + state.Name
                            + "' — skipped this pass: " + UnwrapMessage(faceEx));
                    }
                    continue;
                }

                var notInThisFont = new List<uint>();
                var addedThisBatch = new List<uint>();
                bool changed = false;

                for (int i = 0; i < remaining.Count; i++)
                {
                    uint unicode = remaining[i];
                    // Per-ATLAS cap (review find 5). A global cap let preloaded
                    // ranges plus chat traffic exhaust the budget and then mark a
                    // later player-name glyph permanently missing while another
                    // atlas still had space. A full atlas just defers the codepoint
                    // to the next font instead of condemning it.
                    if (state.AddedCount >= MaxAddedGlyphs)
                    {
                        notInThisFont.Add(unicode);
                        LogCapOnce();
                        continue;
                    }

                    try
                    {
                        object glyph;
                        uint glyphIndex;
                        if (!TryGetGlyph(unicode, out glyph, out glyphIndex))
                        {
                            notInThisFont.Add(unicode);
                            continue;
                        }

                        object packedGlyph;
                        if (!state.GlyphsByIndex.TryGetValue(glyphIndex, out packedGlyph))
                        {
                            if (!TryPackGlyph(state, glyphIndex, out packedGlyph))
                            {
                                notInThisFont.Add(unicode);
                                continue;
                            }
                            state.GlyphTable.Add(packedGlyph);
                            state.GlyphsByIndex[glyphIndex] = packedGlyph;
                        }

                        object character = _tmpCharacterConstructor.Invoke(new[]
                        {
                            (object)unicode, state.Asset, packedGlyph
                        });
                        state.CharacterTable.Add(character);
                        addedThisBatch.Add(unicode);
                        state.AddedCount++;
                        _totalAdded++;
                        changed = true;
                    }
                    catch
                    {
                        notInThisFont.Add(unicode);
                    }
                }

                if (changed)
                {
                    try
                    {
                        _readFontAssetDefinition.Invoke(state.Asset, null);
                        state.Texture.Apply(false, false);
                        for (int i = 0; i < addedThisBatch.Count; i++)
                            _knownCodepoints.Add(addedThisBatch[i]);
                    }
                    catch
                    {
                        for (int i = 0; i < addedThisBatch.Count; i++)
                            _missingCodepoints.Add(addedThisBatch[i]);
                    }
                }

                remaining = notInThisFont;
            }

            // Condemn a codepoint only once EVERY live fallback actually got a
            // chance at it. When a font was skipped this pass (face load blew
            // up) the leftovers stay un-poisoned and retry on the next string;
            // that font disables itself after MaxFaceLoadFailures, so the retry
            // window is bounded and normal poisoning resumes.
            if (!skippedFont)
            {
                for (int i = 0; i < remaining.Count; i++)
                    _missingCodepoints.Add(remaining[i]);
            }
        }

        private static bool TryGetGlyph(uint unicode, out object glyph, out uint glyphIndex)
        {
            object[] args =
            {
                unicode,
                Enum.ToObject(_glyphLoadFlagsType, GlyphLoadFlagsForSdffaa),
                null
            };
            bool found = (bool)_tryGetGlyph.Invoke(null, args);
            glyph = args[2];
            glyphIndex = 0;
            if (!found || glyph == null) return false;

            glyphIndex = Convert.ToUInt32(GetMember(glyph, "index"));
            return glyphIndex != 0;
        }

        private static bool TryPackGlyph(FontState state, uint glyphIndex, out object packedGlyph)
        {
            // The eighth parameter is the reflected out Glyph. Keep this explicit
            // so a signature drift fails installation instead of corrupting lists.
            if (_tryAddGlyphToTexture.GetParameters().Length != 8)
                throw new InvalidOperationException("glyph packer signature changed");

            var invokeArgs = new object[8];
            invokeArgs[0] = glyphIndex;
            invokeArgs[1] = AtlasPadding;
            invokeArgs[2] = Enum.ToObject(_glyphPackingModeType, 0);
            invokeArgs[3] = state.FreeGlyphRects;
            invokeArgs[4] = state.UsedGlyphRects;
            invokeArgs[5] = Enum.ToObject(_glyphRenderModeType, GlyphRenderModeSdffaa);
            invokeArgs[6] = state.Texture;
            invokeArgs[7] = null;

            // Construct the call from the verified slots rather than depending
            // on compile-time TextCore types.
            bool added = (bool)_tryAddGlyphToTexture.Invoke(null, invokeArgs);
            packedGlyph = invokeArgs[7];
            return added && packedGlyph != null;
        }

        private static void RegisterFallbacks(object gameFont, List<object> assets,
            List<ListRegistration> registrations)
        {
            IList primary = GetOrCreateInstanceList(gameFont, "fallbackFontAssetTable",
                registrations, true);
            AddAssets(primary, assets, registrations[registrations.Count - 1]);

            IList legacy = GetOrCreateInstanceList(gameFont, "fallbackFontAssets",
                registrations, false);
            if (legacy != null)
                AddAssets(legacy, assets, registrations[registrations.Count - 1]);

            Type settingsType = RequireType("TMPro.TMP_Settings, Unity.TextMeshPro");
            PropertyInfo globalProperty = settingsType.GetProperty("fallbackFontAssets",
                BindingFlags.Public | BindingFlags.Static);
            IList global = globalProperty == null ? null : globalProperty.GetValue(null, null) as IList;
            ListRegistration globalRegistration = null;

            if (global == null)
            {
                PropertyInfo instanceProperty = settingsType.GetProperty("instance",
                    BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static);
                object settings = instanceProperty == null ? null : instanceProperty.GetValue(null, null);
                if (settings != null)
                {
                    global = GetOrCreateInstanceList(settings, "m_fallbackFontAssets",
                        registrations, true);
                    globalRegistration = registrations[registrations.Count - 1];
                }
            }
            else
            {
                globalRegistration = new ListRegistration { List = global };
                registrations.Add(globalRegistration);
            }

            if (global == null)
                throw new InvalidOperationException("registration failed: TMP settings fallback list unavailable");

            AddAssets(global, assets, globalRegistration);
        }

        private static IList GetOrCreateInstanceList(object owner, string memberName,
            List<ListRegistration> registrations, bool required)
        {
            const BindingFlags flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;
            PropertyInfo property = owner.GetType().GetProperty(memberName, flags);
            FieldInfo field = owner.GetType().GetField(memberName, flags);
            object value = property != null ? property.GetValue(owner, null)
                : field != null ? field.GetValue(owner) : null;
            IList list = value as IList;

            var registration = new ListRegistration
            {
                Owner = owner,
                Property = property,
                Field = field,
                OriginalValue = value,
                List = list
            };

            if (list == null && (property != null || field != null))
            {
                Type listType = property != null ? property.PropertyType : field.FieldType;
                list = Activator.CreateInstance(listType) as IList;
                if (list != null)
                {
                    if (property != null && property.GetSetMethod(true) != null)
                        property.SetValue(owner, list, null);
                    else if (field != null)
                        field.SetValue(owner, list);
                    else
                        list = null;
                }
                registration.List = list;
                registration.AssignedNewList = list != null;
            }

            if (list == null)
            {
                if (required)
                    throw new InvalidOperationException("registration failed: " + memberName + " unavailable");
                return null;
            }

            registrations.Add(registration);
            return list;
        }

        private static void AddAssets(IList list, List<object> assets, ListRegistration registration)
        {
            for (int i = 0; i < assets.Count; i++)
            {
                if (list.Contains(assets[i])) continue;
                list.Add(assets[i]);
                registration.Added.Add(assets[i]);
            }
        }

        private static object FindGameFont()
        {
            try
            {
                FieldInfo uiFont = typeof(UIFactory).GetField("tmpFont",
                    BindingFlags.NonPublic | BindingFlags.Static);
                object value = uiFont == null ? null : uiFont.GetValue(null);
                if (value != null && _fontAssetType.IsInstanceOfType(value))
                    return value;
            }
            catch { }

            UnityEngine.Object[] loaded = Resources.FindObjectsOfTypeAll(_fontAssetType);
            object first = null;
            for (int i = 0; i < loaded.Length; i++)
            {
                if (loaded[i] == null || loaded[i].name.StartsWith("CR_Fallback_", StringComparison.Ordinal))
                    continue;
                if (first == null) first = loaded[i];
                if (loaded[i].name.StartsWith("Gravity-", StringComparison.OrdinalIgnoreCase))
                    return loaded[i];
            }
            return first;
        }

        private static void EnsureFaceLoaded(string path)
        {
            object result = _loadFontFace.Invoke(null, new object[] { path, SamplingPointSize });
            if (Convert.ToInt32(result) != 0)
                throw new InvalidOperationException("font face load failed for " + Path.GetFileName(path)
                    + " (error " + result + ")");
        }

        private static string FindFirstExisting(string directory, string[] candidates)
        {
            for (int i = 0; i < candidates.Length; i++)
            {
                string path = Path.Combine(directory, candidates[i]);
                if (File.Exists(path)) return path;
            }
            return null;
        }

        /// <summary>Unity's platform font enumeration — returns real file
        /// paths on Windows AND Linux/Proton (find 11). Empty array on any
        /// failure so callers can treat it as "nothing extra found".</summary>
        private static string[] GetOsFontPaths()
        {
            try { return Font.GetPathsToOSFonts() ?? new string[0]; }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning("[FONT] GetPathsToOSFonts failed: " + UnwrapMessage(ex));
                return new string[0];
            }
        }

        /// <summary>Candidate resolution in PREFERENCE order: for each
        /// candidate filename, check the fonts directory (when present),
        /// then the OS-enumerated path list by case-insensitive filename.
        /// Candidate order is the priority order — a dir miss for candidate
        /// 0 must not let candidate 2 win via the directory before the OS
        /// list has been tried for candidate 0.</summary>
        private static string FindFont(string directory, string[] osPaths, string[] candidates)
        {
            for (int i = 0; i < candidates.Length; i++)
            {
                if (directory != null)
                {
                    string path = Path.Combine(directory, candidates[i]);
                    if (File.Exists(path)) return path;
                }
                for (int p = 0; p < osPaths.Length; p++)
                {
                    string file;
                    try { file = Path.GetFileName(osPaths[p]); } catch { continue; }
                    if (string.Equals(file, candidates[i], StringComparison.OrdinalIgnoreCase)
                        && File.Exists(osPaths[p]))
                        return osPaths[p];
                }
            }
            return null;
        }

        private static string GetAssetName(string path)
        {
            string file = Path.GetFileName(path);
            if (file.Equals("seguiui.ttf", StringComparison.OrdinalIgnoreCase)) return "CR_Fallback_SegoeUI";
            if (file.Equals("arial.ttf", StringComparison.OrdinalIgnoreCase)) return "CR_Fallback_Arial";
            if (file.Equals("tahoma.ttf", StringComparison.OrdinalIgnoreCase)) return "CR_Fallback_Tahoma";
            if (file.Equals("msyh.ttc", StringComparison.OrdinalIgnoreCase)) return "CR_Fallback_MicrosoftYaHei";
            if (file.Equals("malgun.ttf", StringComparison.OrdinalIgnoreCase)) return "CR_Fallback_Malgun";
            if (file.Equals("YuGothM.ttc", StringComparison.OrdinalIgnoreCase)) return "CR_Fallback_YuGothic";
            if (file.Equals("meiryo.ttc", StringComparison.OrdinalIgnoreCase)) return "CR_Fallback_Meiryo";
            if (file.Equals("simsun.ttc", StringComparison.OrdinalIgnoreCase)) return "CR_Fallback_SimSun";
            return "CR_Fallback_" + Path.GetFileNameWithoutExtension(path);
        }

        private static int GetShaderId(string fieldName)
        {
            FieldInfo field = _shaderUtilitiesType.GetField(fieldName,
                BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static);
            if (field == null) throw new MissingFieldException("ShaderUtilities." + fieldName);
            return Convert.ToInt32(field.GetValue(null));
        }

        private static object GetStaticMember(Type type, string name)
        {
            const BindingFlags flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static;
            PropertyInfo property = type.GetProperty(name, flags);
            if (property != null) return property.GetValue(null, null);
            FieldInfo field = type.GetField(name, flags);
            if (field != null) return field.GetValue(null);
            throw new MissingMemberException(type.FullName, name);
        }

        private static object GetMember(object target, string name)
        {
            const BindingFlags flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;
            PropertyInfo property = target.GetType().GetProperty(name, flags);
            if (property != null) return property.GetValue(target, null);
            FieldInfo field = target.GetType().GetField(name, flags);
            if (field != null) return field.GetValue(target);
            throw new MissingMemberException(target.GetType().FullName, name);
        }

        private static void SetMember(object target, string name, object value)
        {
            const BindingFlags flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;
            PropertyInfo property = target.GetType().GetProperty(name, flags);
            if (property != null && property.GetSetMethod(true) != null)
            {
                property.SetValue(target, value, null);
                return;
            }
            FieldInfo field = target.GetType().GetField(name, flags);
            if (field != null)
            {
                field.SetValue(target, value);
                return;
            }
            throw new MissingMemberException(target.GetType().FullName, name);
        }

        private static Type RequireType(string assemblyQualifiedName)
        {
            Type type = Type.GetType(assemblyQualifiedName, false);
            if (type == null) throw new TypeLoadException(assemblyQualifiedName);
            return type;
        }

        private static MethodInfo RequireMethod(Type type, string name,
            BindingFlags flags, int parameterCount)
        {
            MethodInfo method = FindMethod(type, name, flags, parameterCount);
            if (method == null) throw new MissingMethodException(type.FullName, name);
            return method;
        }

        private static MethodInfo FindMethod(Type type, string name,
            BindingFlags flags, int parameterCount)
        {
            MethodInfo[] methods = type.GetMethods(flags);
            for (int i = 0; i < methods.Length; i++)
            {
                if (methods[i].Name == name && methods[i].GetParameters().Length == parameterCount)
                    return methods[i];
            }
            return null;
        }

        private static MethodInfo FindMethod(Type type, string name,
            BindingFlags flags, Type[] parameterTypes)
        {
            return type.GetMethod(name, flags, null, parameterTypes, null);
        }

        private static MethodInfo FindOutMethod(Type type, string name,
            BindingFlags flags, int parameterCount)
        {
            MethodInfo[] methods = type.GetMethods(flags);
            for (int i = 0; i < methods.Length; i++)
            {
                ParameterInfo[] parameters = methods[i].GetParameters();
                if (methods[i].Name == name && parameters.Length == parameterCount
                    && parameters[parameters.Length - 1].IsOut)
                    return methods[i];
            }
            return null;
        }

        private static void LogCapOnce()
        {
            if (_capLogged) return;
            _capLogged = true;
            Plugin.Log.LogWarning("[FONT] a fallback atlas hit its glyph cap (" + MaxAddedGlyphs
                + "); further characters fall through to the next fallback font, and only"
                + " render as the missing-glyph marker if every atlas is full");
        }

        private static void RollBackRegistrations(List<ListRegistration> registrations)
        {
            for (int i = registrations.Count - 1; i >= 0; i--)
            {
                ListRegistration registration = registrations[i];
                try
                {
                    for (int a = registration.Added.Count - 1; a >= 0; a--)
                        registration.List.Remove(registration.Added[a]);

                    if (!registration.AssignedNewList) continue;
                    if (registration.Property != null
                        && registration.Property.GetSetMethod(true) != null)
                        registration.Property.SetValue(registration.Owner,
                            registration.OriginalValue, null);
                    else if (registration.Field != null)
                        registration.Field.SetValue(registration.Owner,
                            registration.OriginalValue);
                }
                catch { }
            }
        }

        private static void DestroyBuiltFonts(List<FontState> built)
        {
            for (int i = 0; i < built.Count; i++) DestroyFont(built[i]);
        }

        private static void DestroyFont(FontState state)
        {
            if (state == null) return;
            try { if (state.Material != null) UnityEngine.Object.Destroy(state.Material); } catch { }
            try { if (state.Texture != null) UnityEngine.Object.Destroy(state.Texture); } catch { }
            try
            {
                var assetObject = state.Asset as UnityEngine.Object;
                if (assetObject != null) UnityEngine.Object.Destroy(assetObject);
            }
            catch { }
        }

        private static string UnwrapMessage(Exception ex)
        {
            while (ex is TargetInvocationException && ex.InnerException != null)
                ex = ex.InnerException;
            return ex.Message;
        }

        private sealed class FontState
        {
            public string Path;
            public string Name;
            public object Asset;
            public Texture2D Texture;
            public Material Material;
            public IList GlyphTable;
            public IList CharacterTable;
            public IList FreeGlyphRects;
            public IList UsedGlyphRects;
            public int AddedCount;   // per-atlas glyph budget (review find 5)
            public int FaceLoadFailures;
            public bool Disabled;    // face load failed MaxFaceLoadFailures times
            public readonly Dictionary<uint, object> GlyphsByIndex =
                new Dictionary<uint, object>();
        }

        private sealed class ListRegistration
        {
            public object Owner;
            public PropertyInfo Property;
            public FieldInfo Field;
            public object OriginalValue;
            public IList List;
            public bool AssignedNewList;
            public readonly List<object> Added = new List<object>();
        }

        private struct CodepointRange
        {
            public readonly uint First;
            public readonly uint Last;

            public CodepointRange(uint first, uint last)
            {
                First = first;
                Last = last;
            }
        }
    }
}
