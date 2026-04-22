using System;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Local-only TMP_FontAsset swap for player nametag labels. The active typeface SKU is
    /// published via the Photon custom property "cr_nametag_typeface" (set by
    /// NametagStyler.PublishToPhoton). For each room player with a matching SKU, this
    /// component scans TMP labels whose text matches the player's clean nickname and sets
    /// <c>TMP_Text.font</c> to a TMP_FontAsset built at runtime from a Windows OS font.
    ///
    /// The OS-font path deliberately does NOT leak to non-modded opponents — they see the
    /// plain NickName and never instantiate this component, so there are no weird fallback
    /// glyphs or broken boxes on their end. This is the replacement for the failed Unicode-
    /// substitution attempt in migration 036 (see learnings.md / docs/TODO.md).
    ///
    /// Ordering: attached to the persistent plugin GameObject BEFORE NametagGlowRenderer so
    /// its coroutine cycle runs first each tick. Glow's material cache is keyed by the font
    /// asset's default material, which changes after a font swap, so it will rebuild its
    /// cloned glow material against the new atlas on its next poll — net effect: typeface
    /// and glow compose correctly within ~0.5s of either changing.
    /// </summary>
    internal class NametagFontRenderer : MonoBehaviour
    {
        private const float POLL_INTERVAL = 0.5f;

        // SKU → TMP font asset name inside the comp-rounds-fonts AssetBundle. The bundle is
        // built by the Unity project at unity-font-bundler/; the FontBundler.cs Editor script
        // there bakes each .ttf in Assets/FontSources/ into a TMP_FontAsset named after the
        // file stem (e.g. pacifico.ttf → TMP asset named "pacifico"). The bundle ships
        // alongside the DLL in BepInEx/plugins/CompetitiveRounds/. If the bundle is missing
        // (user hasn't run the Font Bundler), typefaces silently disable and players see the
        // default nametag — see LoadFontBundle below for the resolution path.
        private static readonly Dictionary<string, string> _skuToTmpFontName =
            new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
            {
                // Common (100g)
                { "nametag_typeface_caveat",           "caveat" },
                { "nametag_typeface_permanentmarker",  "permanentmarker" },
                { "nametag_typeface_courierprime",     "courierprime" },
                // Uncommon (150g)
                { "nametag_typeface_pacifico",         "pacifico" },
                { "nametag_typeface_playfairdisplay",  "playfairdisplay" },
                { "nametag_typeface_specialelite",     "specialelite" },
                { "nametag_typeface_vt323",            "vt323" },
                { "nametag_typeface_medievalsharp",    "medievalsharp" },
                { "nametag_typeface_smokum",           "smokum" },
                { "nametag_typeface_rye",              "rye" },
                { "nametag_typeface_orbitron",         "orbitron" },
                // Rare (250g)
                { "nametag_typeface_greatvibes",       "greatvibes" },
                { "nametag_typeface_cinzeldecorative", "cinzeldecorative" },
                { "nametag_typeface_pressstart2p",     "pressstart2p" },
                { "nametag_typeface_audiowide",        "audiowide" },
                { "nametag_typeface_monoton",          "monoton" },
                { "nametag_typeface_bungeeshade",      "bungeeshade" },
                { "nametag_typeface_metalmania",       "metalmania" },
                // Legendary (500g)
                { "nametag_typeface_unifrakturmaguntia", "unifrakturmaguntia" },
                { "nametag_typeface_creepster",        "creepster" },
                { "nametag_typeface_rubikpuddles",     "rubikpuddles" },
                { "nametag_typeface_rubikmarkerhatch", "rubikmarkerhatch" },
            };

        // Loaded once from the bundle, kept alive for the lifetime of the plugin. Keys are
        // the bundle asset names (lowercase, no spaces) that _skuToTmpFontName maps onto.
        private static Dictionary<string, object> _bundledFontsByName;
        private static bool _bundleLoadAttempted;
        private static object _fontBundle; // AssetBundle instance, held so unload doesn't release the fonts

        // Reflection handles.
        private static Type _tTmpText;                     // TMPro.TMP_Text (base, covers UGUI + world)
        private static Type _tTmpFontAsset;                // TMPro.TMP_FontAsset
        private static PropertyInfo _pText;                // string text
        private static PropertyInfo _pFont;                // TMP_FontAsset font
        private static MethodInfo  _mCreateFontAsset;      // static TMP_FontAsset CreateFontAsset(Font)
        private static MethodInfo  _mSetAllDirty;          // void SetAllDirty()
        private static MethodInfo  _mUpdateMaterial;       // void UpdateMaterial()
        private static MethodInfo  _mForceMeshUpdate;      // void ForceMeshUpdate(bool, bool)
        private static bool _reflectionReady;

        private class LabelState
        {
            public object OriginalFont;                    // TMP_FontAsset captured on first swap
            public string LastAppliedSku;                  // "" means "restored to OriginalFont"
        }
        private readonly Dictionary<Component, LabelState> _states = new Dictionary<Component, LabelState>();

        // sku → built TMP_FontAsset, lazy-populated. Skus that fail to build (OS font missing or
        // CreateFontAsset throws) cache "null" so we don't hammer the build path each poll.
        private static readonly Dictionary<string, object> _fontAssetCache = new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);
        private static readonly HashSet<string> _fontBuildFailed = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        private static bool _reflectionLoggedMissing;
        private static bool TryBindReflection()
        {
            if (_reflectionReady) return true;
            try
            {
                foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                {
                    if (_tTmpText == null) _tTmpText = asm.GetType("TMPro.TMP_Text");
                    if (_tTmpFontAsset == null) _tTmpFontAsset = asm.GetType("TMPro.TMP_FontAsset");
                    if (_tTmpText != null && _tTmpFontAsset != null) break;
                }
                if (_tTmpText == null || _tTmpFontAsset == null)
                {
                    if (!_reflectionLoggedMissing)
                    {
                        _reflectionLoggedMissing = true;
                        Plugin.Log.LogWarning($"[TYPEFACE] TMP types not found (tmpText={_tTmpText != null}, tmpFontAsset={_tTmpFontAsset != null}) — custom fonts disabled.");
                    }
                    return false;
                }
                var bf = BindingFlags.Public | BindingFlags.Instance;
                _pText = _tTmpText.GetProperty("text", bf);
                _pFont = _tTmpText.GetProperty("font", bf);
                // TMP 1.5+ signature: CreateFontAsset(Font). Older versions may only have longer
                // overloads; try the simple one first then fall back to any static that takes a Font.
                _mCreateFontAsset = _tTmpFontAsset.GetMethod(
                    "CreateFontAsset",
                    BindingFlags.Public | BindingFlags.Static,
                    binder: null,
                    types: new Type[] { typeof(Font) },
                    modifiers: null);
                if (_mCreateFontAsset == null)
                {
                    foreach (var m in _tTmpFontAsset.GetMethods(BindingFlags.Public | BindingFlags.Static))
                    {
                        if (m.Name != "CreateFontAsset") continue;
                        var ps = m.GetParameters();
                        if (ps.Length >= 1 && ps[0].ParameterType == typeof(Font))
                        {
                            _mCreateFontAsset = m;
                            break;
                        }
                    }
                }
                var bfI = BindingFlags.Public | BindingFlags.Instance;
                _mSetAllDirty = _tTmpText.GetMethod("SetAllDirty", bfI);
                _mUpdateMaterial = _tTmpText.GetMethod("UpdateMaterial", bfI);
                _mForceMeshUpdate = _tTmpText.GetMethod("ForceMeshUpdate", bfI, null, new Type[] { typeof(bool), typeof(bool) }, null);
                _reflectionReady = _pText != null && _pFont != null && _mCreateFontAsset != null;
                if (!_reflectionReady && !_reflectionLoggedMissing)
                {
                    _reflectionLoggedMissing = true;
                    Plugin.Log.LogWarning($"[TYPEFACE] reflection incomplete (pText={_pText != null}, pFont={_pFont != null}, mCreateFontAsset={_mCreateFontAsset != null}) — custom fonts disabled.");
                }
                else if (_reflectionReady)
                {
                    Plugin.Log.LogInfo("[TYPEFACE] reflection bound OK — custom fonts enabled.");
                }
                return _reflectionReady;
            }
            catch { return false; }
        }

        void OnEnable() { StartCoroutine(PollLoop()); }
        void OnDisable() { StopAllCoroutines(); RestoreAllLabels(); }

        private IEnumerator PollLoop()
        {
            var wait = new WaitForSeconds(POLL_INTERVAL);
            while (true)
            {
                try { ScanAndApply(); }
                catch (Exception ex) { Plugin.Log.LogWarning($"[TYPEFACE] scan error: {ex.Message}"); }
                yield return wait;
            }
        }

        private void ScanAndApply()
        {
            if (!TryBindReflection()) return;
            if (!PhotonNetwork.InRoom)
            {
                if (_states.Count > 0) RestoreAllLabels();
                return;
            }

            // Build "clean nickname → typeface sku" index for current room players.
            var nickToFont = new Dictionary<string, string>(StringComparer.Ordinal);
            foreach (var pp in PhotonNetwork.PlayerList)
            {
                if (pp == null) continue;
                string cleanNick = NametagStyler.Clean(pp.NickName ?? "");
                if (string.IsNullOrEmpty(cleanNick)) continue;
                string fontSku = "";
                try
                {
                    if (pp.CustomProperties != null
                        && pp.CustomProperties.TryGetValue("cr_nametag_typeface", out object v))
                        fontSku = v?.ToString() ?? "";
                }
                catch { }
                nickToFont[cleanNick] = fontSku;
            }
            if (nickToFont.Count == 0) return;

            var tmps = UnityEngine.Object.FindObjectsOfType(_tTmpText);
            var seenThisPass = new HashSet<Component>();
            foreach (var obj in tmps)
            {
                if (!(obj is Component comp)) continue;
                seenThisPass.Add(comp);

                string rawText;
                try { rawText = _pText.GetValue(comp) as string ?? ""; }
                catch { continue; }
                string cleanText = NametagStyler.Clean(rawText);
                if (string.IsNullOrEmpty(cleanText)) { RestoreLabel(comp); continue; }

                if (!nickToFont.TryGetValue(cleanText, out string sku))
                {
                    RestoreLabel(comp);
                    continue;
                }
                ApplyFont(comp, sku);
            }

            if (_states.Count > 0)
            {
                List<Component> stale = null;
                foreach (var kv in _states)
                {
                    if (!seenThisPass.Contains(kv.Key))
                    {
                        if (stale == null) stale = new List<Component>();
                        stale.Add(kv.Key);
                    }
                }
                if (stale != null)
                    foreach (var c in stale) _states.Remove(c);
            }
        }

        private void ApplyFont(Component comp, string sku)
        {
            if (!_states.TryGetValue(comp, out var state))
            {
                state = new LabelState();
                try { state.OriginalFont = _pFont.GetValue(comp); }
                catch { return; }
                if (state.OriginalFont == null) return;
                _states[comp] = state;
            }

            // Restore path.
            if (string.IsNullOrEmpty(sku))
            {
                if (state.LastAppliedSku != "")
                {
                    try { _pFont.SetValue(comp, state.OriginalFont); } catch { }
                    state.LastAppliedSku = "";
                }
                return;
            }
            if (sku == state.LastAppliedSku) return;

            object fontAsset = GetOrBuildFontAsset(sku);
            if (fontAsset == null) return;  // build failed — leave as-is
            try { _pFont.SetValue(comp, fontAsset); }
            catch { return; }
            // Flush TMP caches so the font swap actually renders. TMP's `font` setter does
            // call SetVerticesDirty / SetLayoutDirty internally, but the mesh may still hold
            // cached atlas glyphs from the old font; ForceMeshUpdate regenerates from scratch.
            try { _mSetAllDirty?.Invoke(comp, null); } catch { }
            try { _mUpdateMaterial?.Invoke(comp, null); } catch { }
            try { _mForceMeshUpdate?.Invoke(comp, new object[] { true, true }); } catch { }
            state.LastAppliedSku = sku;
            Plugin.Log.LogInfo($"[TYPEFACE] Applied {sku} to label '{comp.name}'");
        }

        /// <summary>Shared lazy font-asset builder. Returns cached asset if present, otherwise
        /// builds from the Windows OS font mapped by <paramref name="sku"/>. Null means the OS
        /// font isn't installed or TMP's CreateFontAsset threw — the sku is marked failed so we
        /// don't retry every poll.</summary>
        public static object GetOrBuildFontAsset(string sku)
        {
            if (string.IsNullOrEmpty(sku)) return null;
            if (_fontAssetCache.TryGetValue(sku, out var cached)) return cached;
            if (_fontBuildFailed.Contains(sku)) return null;
            if (!TryBindReflection()) return null;
            if (!_skuToTmpFontName.TryGetValue(sku, out string tmpName))
            {
                Plugin.Log.LogWarning($"[TYPEFACE] sku '{sku}' not in _skuToTmpFontName map — marking failed.");
                _fontBuildFailed.Add(sku);
                return null;
            }
            EnsureBundleLoaded();
            if (_bundledFontsByName != null
                && _bundledFontsByName.TryGetValue(tmpName, out var asset)
                && asset != null)
            {
                _fontAssetCache[sku] = asset;
                Plugin.Log.LogInfo($"[TYPEFACE] Resolved {sku} → {tmpName} (from bundle)");
                return asset;
            }
            Plugin.Log.LogWarning($"[TYPEFACE] TMP font '{tmpName}' for sku '{sku}' not in bundle — disabled. (Bundle present? {(_bundledFontsByName != null)})");
            _fontBuildFailed.Add(sku);
            return null;
        }

        /// <summary>Load the comp-rounds-fonts AssetBundle from disk on first access. The
        /// bundle ships next to the plugin DLL in BepInEx/plugins/CompetitiveRounds/. If it's
        /// missing (user hasn't run the Font Bundler Unity step), we log once and leave
        /// _bundledFontsByName null — every SKU then falls through to its default font
        /// silently, so the shop still functions but typefaces don't apply visually.</summary>
        private static void EnsureBundleLoaded()
        {
            if (_bundleLoadAttempted) return;
            _bundleLoadAttempted = true;
            try
            {
                // Resolve the DLL's own folder (BepInEx/plugins/CompetitiveRounds/). The
                // FontBundler Unity project writes comp-rounds-fonts there directly so
                // they're colocated; no path guessing needed.
                string dllPath = Assembly.GetExecutingAssembly().Location;
                string dllDir = System.IO.Path.GetDirectoryName(dllPath);
                string bundlePath = System.IO.Path.Combine(dllDir, "comp-rounds-fonts");
                if (!System.IO.File.Exists(bundlePath))
                {
                    Plugin.Log.LogWarning($"[TYPEFACE] Font bundle not found at {bundlePath} — typefaces disabled. Run the Unity Font Bundler to produce it.");
                    return;
                }
                var bundle = AssetBundle.LoadFromFile(bundlePath);
                if (bundle == null)
                {
                    Plugin.Log.LogWarning($"[TYPEFACE] AssetBundle.LoadFromFile returned null for {bundlePath} — corrupt or wrong Unity version.");
                    return;
                }
                _fontBundle = bundle;
                var names = bundle.GetAllAssetNames();
                _bundledFontsByName = new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);
                foreach (var assetName in names)
                {
                    var asset = bundle.LoadAsset(assetName, _tTmpFontAsset);
                    if (asset == null) continue;
                    string key = (asset as UnityEngine.Object).name;
                    if (!string.IsNullOrEmpty(key))
                        _bundledFontsByName[key] = asset;
                }
                Plugin.Log.LogInfo($"[TYPEFACE] Font bundle loaded: {_bundledFontsByName.Count} TMP_FontAssets available.");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[TYPEFACE] Bundle load failed: {ex.Message}");
            }
        }

        /// <summary>Dump every TMP_FontAsset currently loaded in memory to the log. Called
        /// once at startup. Gives us the list of fonts already shipped inside ROUNDS that we
        /// could map SKUs to in a future pass, as a replacement for the broken OS-font path.</summary>
        public static void LogAvailableTmpFonts()
        {
            if (!TryBindReflection()) return;
            try
            {
                var found = UnityEngine.Resources.FindObjectsOfTypeAll(_tTmpFontAsset);
                int n = found?.Length ?? 0;
                Plugin.Log.LogInfo($"[TYPEFACE] Available TMP_FontAssets in memory: {n}");
                if (found == null) return;
                var seen = new HashSet<string>();
                foreach (var obj in found)
                {
                    string name = (obj as UnityEngine.Object)?.name ?? "(unnamed)";
                    if (seen.Add(name))
                        Plugin.Log.LogInfo($"[TYPEFACE]   - {name}");
                }
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[TYPEFACE] LogAvailableTmpFonts failed: {ex.Message}");
            }
        }

        /// <summary>One-off font swap on a specific TMP label. Exposed so the shop preview can
        /// render an actual-font preview instead of a flat text description. Caller provides the
        /// <paramref name="originalFontStore"/> keyed by label instance so originals can be
        /// restored when rows are recycled. Returns true if the font actually changed.</summary>
        private static bool _loggedFirstApply;
        public static bool ApplyFontToLabel(object tmpLabel, string sku,
            Dictionary<object, object> originalFontStore)
        {
            if (tmpLabel == null) return false;
            if (!TryBindReflection()) return false;
            if (!_loggedFirstApply)
            {
                _loggedFirstApply = true;
                Plugin.Log.LogInfo($"[TYPEFACE] first ApplyFontToLabel call: sku='{sku}' label='{(tmpLabel as Component)?.name ?? "(null)"}'");
            }
            try
            {
                object current = _pFont.GetValue(tmpLabel);
                if (originalFontStore != null && !originalFontStore.ContainsKey(tmpLabel) && current != null)
                    originalFontStore[tmpLabel] = current;

                object originalFont = (originalFontStore != null && originalFontStore.TryGetValue(tmpLabel, out var of)) ? of : current;
                object targetFont = string.IsNullOrEmpty(sku) ? originalFont : GetOrBuildFontAsset(sku);
                if (targetFont == null) targetFont = originalFont;
                if (targetFont == null || ReferenceEquals(current, targetFont)) return false;
                _pFont.SetValue(tmpLabel, targetFont);
                try { _mSetAllDirty?.Invoke(tmpLabel, null); } catch { }
                try { _mUpdateMaterial?.Invoke(tmpLabel, null); } catch { }
                try { _mForceMeshUpdate?.Invoke(tmpLabel, new object[] { true, true }); } catch { }
                return true;
            }
            catch { return false; }
        }

        private void RestoreLabel(Component comp)
        {
            if (comp == null) return;
            if (!_states.TryGetValue(comp, out var state)) return;
            if (!string.IsNullOrEmpty(state.LastAppliedSku) && state.OriginalFont != null)
            {
                try { _pFont.SetValue(comp, state.OriginalFont); } catch { }
            }
            state.LastAppliedSku = "";
        }

        private void RestoreAllLabels()
        {
            foreach (var kv in _states)
            {
                if (kv.Key == null) continue;
                if (string.IsNullOrEmpty(kv.Value.LastAppliedSku)) continue;
                if (kv.Value.OriginalFont == null) continue;
                try { _pFont.SetValue(kv.Key, kv.Value.OriginalFont); } catch { }
                kv.Value.LastAppliedSku = "";
            }
        }
    }
}
