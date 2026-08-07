using System;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using Photon.Pun;
using Photon.Realtime;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Local-only glow rendering for player name labels. Glow skus are published via the
    /// Photon custom property "cr_nametag_glow" (set by NametagStyler.PublishToPhoton).
    /// This component polls the scene for TextMeshProUGUI / TextMeshPro labels whose
    /// rendered text matches a room player's clean nickname, clones their font material,
    /// and enables the TMP SDF shader's GLOW_ON keyword with _GlowColor / _GlowOuter /
    /// _GlowPower set. Non-modded clients never instantiate this component, so they see
    /// the plain name with no visual artifacts.
    ///
    /// Everything goes through reflection — the project has a no-direct-TMPro-reference
    /// rule (see CLAUDE.md). Types and properties are cached on first successful poll
    /// so subsequent passes are cheap.
    /// </summary>
    internal class NametagGlowRenderer : MonoBehaviour
    {
        private const float POLL_INTERVAL = 0.5f;

        // Reflection handles (cached).
        private static Type _tTmpText;                     // TMPro.TMP_Text base class (covers UGUI + world)
        private static PropertyInfo _pText;                // string text
        private static PropertyInfo _pFontSharedMaterial;  // Material fontSharedMaterial (get/set)
        private static PropertyInfo _pFontMaterial;        // Material fontMaterial (instanced)
        private static MethodInfo  _mSetMaterialDirty;     // void SetMaterialDirty()
        private static MethodInfo  _mSetVerticesDirty;     // void SetVerticesDirty()
        private static MethodInfo  _mSetLayoutDirty;       // void SetLayoutDirty()
        private static MethodInfo  _mUpdateMaterial;       // void UpdateMaterial() — TMP-specific; flushes MPB
        private static bool _reflectionReady;

        // Per-label state. Keyed by the TMP_Text instance (as Component for the dictionary key).
        // We store the original fontSharedMaterial so we can restore when the glow is
        // removed, and the sku last applied to avoid redundant work.
        private class LabelState
        {
            public Material OriginalMaterial;
            public string LastAppliedSku;
            public Material AppliedMaterial;
        }
        private readonly Dictionary<Component, LabelState> _states = new Dictionary<Component, LabelState>();

        // sku → pre-built cloned material keyed off a representative font. Built lazily
        // the first time we encounter each font × sku combination. Prevents allocating a
        // fresh material every poll.
        private class MaterialCacheKey : IEquatable<MaterialCacheKey>
        {
            public Material BaseMaterial;
            public string Sku;
            public bool Equals(MaterialCacheKey other)
                => other != null && ReferenceEquals(BaseMaterial, other.BaseMaterial) && Sku == other.Sku;
            public override bool Equals(object obj) => Equals(obj as MaterialCacheKey);
            public override int GetHashCode()
                => (BaseMaterial?.GetInstanceID() ?? 0) ^ (Sku?.GetHashCode() ?? 0);
        }
        private readonly Dictionary<MaterialCacheKey, Material> _matCache =
            new Dictionary<MaterialCacheKey, Material>();

        private static bool TryBindReflection()
        {
            if (_reflectionReady) return true;
            try
            {
                foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                {
                    _tTmpText = asm.GetType("TMPro.TMP_Text");
                    if (_tTmpText != null) break;
                }
                if (_tTmpText == null) return false;
                var bf = BindingFlags.Public | BindingFlags.Instance;
                _pText = _tTmpText.GetProperty("text", bf);
                _pFontSharedMaterial = _tTmpText.GetProperty("fontSharedMaterial", bf);
                _pFontMaterial = _tTmpText.GetProperty("fontMaterial", bf);
                _mSetMaterialDirty = _tTmpText.GetMethod("SetMaterialDirty", bf);
                _mSetVerticesDirty = _tTmpText.GetMethod("SetVerticesDirty", bf);
                _mSetLayoutDirty = _tTmpText.GetMethod("SetLayoutDirty", bf);
                _mUpdateMaterial = _tTmpText.GetMethod("UpdateMaterial", bf);
                _reflectionReady = _pText != null && _pFontSharedMaterial != null;
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
                catch (Exception ex) { Plugin.Log.LogWarning($"[GLOW] scan error: {ex.Message}"); }
                yield return wait;
            }
        }

        private void ScanAndApply()
        {
            if (!TryBindReflection()) return;

            // Outside a room → nothing to match. Clear all applied glows so labels in
            // menus (which may match nicknames by accident) don't stay tinted.
            if (!PhotonNetwork.InRoom)
            {
                if (_states.Count > 0) RestoreAllLabels();
                return;
            }

            // Build a "clean nickname → glow sku" index for the players currently in the
            // room. Clean nicknames strip any rich-text tags so we can compare against
            // tmp.text (which is the already-wrapped styled nickname).
            var nickToGlow = new Dictionary<string, string>(StringComparer.Ordinal);
            // Census: fighters only (same collision rule as the font renderer).
            foreach (var pp in RoomActors.ActiveFighters())
            {
                if (pp == null) continue;
                string cleanNick = NametagStyler.Clean(pp.NickName ?? "");
                if (string.IsNullOrEmpty(cleanNick)) continue;
                string glowSku = "";
                try
                {
                    if (pp.CustomProperties != null
                        && pp.CustomProperties.TryGetValue("cr_nametag_glow", out object v))
                        glowSku = v?.ToString() ?? "";
                }
                catch { }
                nickToGlow[cleanNick] = glowSku;
            }
            if (nickToGlow.Count == 0) return;

            // Scan TMP_Text labels and apply / restore per match. FindObjectsOfType on
            // every poll scales with total TMP count in the scene — fine at 0.5Hz.
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

                if (!nickToGlow.TryGetValue(cleanText, out string sku))
                {
                    // This label doesn't match any current room player → restore if we
                    // had previously applied a glow to it.
                    RestoreLabel(comp);
                    continue;
                }
                ApplyGlow(comp, sku);
            }

            // Prune state for labels we no longer see (destroyed).
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

        private void ApplyGlow(Component comp, string sku)
        {
            if (!_states.TryGetValue(comp, out var state))
            {
                state = new LabelState();
                Material current;
                try { current = _pFontSharedMaterial.GetValue(comp) as Material; }
                catch { return; }
                if (current == null) return;
                // Detect "current is actually one of our previous clones" — happens because
                // fontSharedMaterial is shared across all TMP_Text sharing a font asset; a
                // label spawned after we applied a glow inherits the clone as its default.
                // Reuse the prior base material for this sku so we don't build a clone-of-clone
                // (which was visible in logs as "base=...SDF Material + nametag_glow_gold + ...").
                if (current.name != null && current.name.Contains(" + nametag_"))
                {
                    Material priorBase = null;
                    foreach (var kv in _matCache)
                        if (ReferenceEquals(kv.Value, current)) { priorBase = kv.Key.BaseMaterial; break; }
                    state.OriginalMaterial = priorBase ?? current;
                }
                else
                {
                    state.OriginalMaterial = current;
                }
                _states[comp] = state;
            }

            // Restoration path — sku empty means the player turned glow off.
            if (string.IsNullOrEmpty(sku))
            {
                if (state.LastAppliedSku != "")
                {
                    try { _pFontSharedMaterial.SetValue(comp, state.OriginalMaterial); } catch { }
                    state.LastAppliedSku = "";
                }
                return;
            }
            if (sku == state.LastAppliedSku) return;

            Material mat;
            var key = new MaterialCacheKey { BaseMaterial = state.OriginalMaterial, Sku = sku };
            if (!_matCache.TryGetValue(key, out mat) || mat == null)
            {
                mat = BuildGlowMaterial(state.OriginalMaterial, sku);
                if (mat == null) return;
                _matCache[key] = mat;
            }
            try
            {
                // Use fontMaterial (per-instance override) instead of fontSharedMaterial. The
                // shared path was contaminating every TMP_Text using the same font asset and
                // producing "clone of our own clone" chains seen in earlier logs. Instance
                // setter on TMP creates a per-label material slot that won't bleed to other
                // labels. If fontMaterial is unavailable (older TMP), fall back to shared.
                if (_pFontMaterial != null) _pFontMaterial.SetValue(comp, mat);
                else _pFontSharedMaterial.SetValue(comp, mat);
            }
            catch { return; }
            // Flush TMP's internal caches so the effect actually becomes visible. Without
            // these calls, TMP keeps rendering with its last committed MaterialPropertyBlock,
            // and our GLOW_ON / UNDERLAY_ON / _OutlineWidth tweaks appear in the material
            // but never reach the renderer.
            try { _mSetMaterialDirty?.Invoke(comp, null); } catch { }
            try { _mSetVerticesDirty?.Invoke(comp, null); } catch { }
            try { _mSetLayoutDirty?.Invoke(comp, null); } catch { }
            try { _mUpdateMaterial?.Invoke(comp, null); } catch { }
            state.LastAppliedSku = sku;
            state.AppliedMaterial = mat;
            Plugin.Log.LogInfo($"[GLOW] Applied {sku} to label '{comp.name}'");
        }

        /// <summary>Clone a TMP SDF material and apply the glow for this SKU. Exposed so the
        /// shop preview can render an actual glowing nametag instead of a flat rich-text hint
        /// that doesn't resemble what appears in-game. Returns null if the base material isn't
        /// a TMP SDF material or the clone fails.</summary>
        public static Material BuildGlowMaterial(Material baseMat, string sku)
        {
            if (baseMat == null) return null;
            try
            {
                var clone = new Material(baseMat);
                clone.name = baseMat.name + " + " + sku;
                clone.hideFlags = HideFlags.HideAndDontSave;
                Color gc = NametagStyler.GetGlowColor(sku);

                // User feedback: "still a box". Reducing outline below the threshold where
                // adjacent letter outlines bleed into a continuous block. Also forcing _FaceColor
                // to white (was Color.clear inheriting from base caused the face to disappear,
                // leaving only outline which reads as a solid shape at small sizes). Keep
                // softness low so the outline reads as a thin rim not a smear.
                try { clone.DisableKeyword("UNDERLAY_ON"); } catch { }
                try { clone.DisableKeyword("GLOW_ON"); } catch { }
                if (clone.HasProperty("_OutlineColor"))     clone.SetColor("_OutlineColor", gc);
                if (clone.HasProperty("_OutlineWidth"))     clone.SetFloat("_OutlineWidth", 0.15f);
                if (clone.HasProperty("_OutlineSoftness"))  clone.SetFloat("_OutlineSoftness", 0.25f);
                if (clone.HasProperty("_FaceColor"))        clone.SetColor("_FaceColor", Color.white);
                if (clone.HasProperty("_FaceDilate"))       clone.SetFloat("_FaceDilate", 0f);

                // Explicitly zero out underlay/glow params so inherited values from the base
                // material can't sneak through if the shader does happen to sample them.
                if (clone.HasProperty("_UnderlayColor"))    clone.SetColor("_UnderlayColor", Color.clear);
                if (clone.HasProperty("_UnderlayDilate"))   clone.SetFloat("_UnderlayDilate", 0f);
                if (clone.HasProperty("_UnderlaySoftness")) clone.SetFloat("_UnderlaySoftness", 0f);
                if (clone.HasProperty("_GlowOuter"))        clone.SetFloat("_GlowOuter", 0f);
                if (clone.HasProperty("_GlowPower"))        clone.SetFloat("_GlowPower", 0f);

                // Diagnostic: dump the actual post-set property values so we can verify in the
                // log whether our changes took hold or TMP clobbered them during assignment.
                float ow = clone.HasProperty("_OutlineWidth") ? clone.GetFloat("_OutlineWidth") : -1f;
                float os = clone.HasProperty("_OutlineSoftness") ? clone.GetFloat("_OutlineSoftness") : -1f;
                Color fc = clone.HasProperty("_FaceColor") ? clone.GetColor("_FaceColor") : Color.magenta;
                Color oc = clone.HasProperty("_OutlineColor") ? clone.GetColor("_OutlineColor") : Color.magenta;
                Plugin.Log.LogInfo($"[GLOW] post-set props: outlineWidth={ow} outlineSoftness={os} faceColor=({fc.r:F2},{fc.g:F2},{fc.b:F2},{fc.a:F2}) outlineColor=({oc.r:F2},{oc.g:F2},{oc.b:F2},{oc.a:F2})");

                string keywords = "";
                try { keywords = string.Join(",", clone.shaderKeywords); } catch { }
                Plugin.Log.LogInfo($"[GLOW] Built material for {sku} (base={baseMat.name}, shader={clone.shader?.name}, keywords=[{keywords}])");
                return clone;
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[GLOW] BuildGlowMaterial({sku}) failed: {ex.Message}");
                return null;
            }
        }

        /// <summary>Swap a specific TMP text label's sharedMaterial to a glow-cloned version for
        /// <paramref name="sku"/>, or restore to the original if <paramref name="sku"/> is empty.
        /// Intended for one-off usages like the shop preview — the label's own state lives in the
        /// caller-provided <paramref name="originalMaterialStore"/>, keyed by label instance, so
        /// the original can be restored when the label is reused for a non-glow item next pass.
        /// Returns true if the material was changed from the currently-applied one. Tolerates
        /// missing reflection / non-TMP / null labels by returning false silently.</summary>
        public static bool ApplyGlowToLabel(object tmpLabel, string sku,
            Dictionary<object, Material> originalMaterialStore,
            Dictionary<string, Material> glowMaterialCache)
        {
            if (tmpLabel == null) return false;
            if (!TryBindReflection()) return false;
            try
            {
                Material current = _pFontSharedMaterial.GetValue(tmpLabel) as Material;
                // Capture the original on first encounter. We only track labels that are currently
                // showing an unmodified material — if the user already equipped a glow on this label
                // elsewhere, skip caching to avoid the "original" being a glow material.
                if (originalMaterialStore != null && !originalMaterialStore.ContainsKey(tmpLabel) && current != null)
                    originalMaterialStore[tmpLabel] = current;

                Material originalMat = (originalMaterialStore != null && originalMaterialStore.TryGetValue(tmpLabel, out var om)) ? om : current;
                Material targetMat;
                if (string.IsNullOrEmpty(sku))
                {
                    targetMat = originalMat;
                }
                else
                {
                    if (glowMaterialCache == null || !glowMaterialCache.TryGetValue(sku, out targetMat) || targetMat == null)
                    {
                        targetMat = BuildGlowMaterial(originalMat, sku);
                        if (glowMaterialCache != null && targetMat != null) glowMaterialCache[sku] = targetMat;
                    }
                }
                if (targetMat == null || ReferenceEquals(current, targetMat)) return false;
                // Use fontMaterial (instance) and flush TMP's internal caches — same reasoning
                // as the live renderer. Without these, the preview label holds old MPB state
                // and none of our glow/outline tweaks render.
                if (_pFontMaterial != null) _pFontMaterial.SetValue(tmpLabel, targetMat);
                else _pFontSharedMaterial.SetValue(tmpLabel, targetMat);
                try { _mSetMaterialDirty?.Invoke(tmpLabel, null); } catch { }
                try { _mSetVerticesDirty?.Invoke(tmpLabel, null); } catch { }
                try { _mUpdateMaterial?.Invoke(tmpLabel, null); } catch { }
                return true;
            }
            catch { return false; }
        }

        /// <summary>Clone a TMP SDF material with a thin dark outline — used by the
        /// leaderboard to keep podium-row text readable over the gold/silver/bronze
        /// row tints (v1.32 round 2, Sid: "Stan's elo is hard to read"). Face
        /// properties are inherited from the base so rich-text vertex colors render
        /// unchanged; only the rim is added.</summary>
        public static Material BuildDarkOutlineMaterial(Material baseMat)
        {
            if (baseMat == null) return null;
            try
            {
                var clone = new Material(baseMat);
                clone.name = baseMat.name + " + podium-outline";
                clone.hideFlags = HideFlags.HideAndDontSave;
                try { clone.DisableKeyword("UNDERLAY_ON"); } catch { }
                try { clone.DisableKeyword("GLOW_ON"); } catch { }
                if (clone.HasProperty("_OutlineColor"))    clone.SetColor("_OutlineColor", new Color(0f, 0f, 0f, 0.9f));
                if (clone.HasProperty("_OutlineWidth"))    clone.SetFloat("_OutlineWidth", 0.18f);
                if (clone.HasProperty("_OutlineSoftness")) clone.SetFloat("_OutlineSoftness", 0.1f);
                return clone;
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[GLOW] BuildDarkOutlineMaterial failed: {ex.Message}");
                return null;
            }
        }

        /// <summary>Toggle the dark readability outline on a TMP label. Same shape as
        /// ApplyGlowToLabel: the caller owns the original-material store (keyed by
        /// label) and the clone cache (keyed by base material — leaderboard cells all
        /// share one Gravity SDF material, so one clone serves every cell).</summary>
        public static bool ApplyOutlineToLabel(object tmpLabel, bool on,
            Dictionary<object, Material> originalMaterialStore,
            Dictionary<Material, Material> outlineMaterialCache)
        {
            if (tmpLabel == null) return false;
            if (!TryBindReflection()) return false;
            try
            {
                Material current = _pFontSharedMaterial.GetValue(tmpLabel) as Material;
                if (originalMaterialStore != null && !originalMaterialStore.ContainsKey(tmpLabel) && current != null)
                    originalMaterialStore[tmpLabel] = current;
                Material originalMat = (originalMaterialStore != null && originalMaterialStore.TryGetValue(tmpLabel, out var om)) ? om : current;
                Material targetMat;
                if (!on)
                {
                    targetMat = originalMat;
                }
                else
                {
                    if (originalMat == null) return false;
                    if (outlineMaterialCache == null || !outlineMaterialCache.TryGetValue(originalMat, out targetMat) || targetMat == null)
                    {
                        targetMat = BuildDarkOutlineMaterial(originalMat);
                        if (outlineMaterialCache != null && targetMat != null) outlineMaterialCache[originalMat] = targetMat;
                    }
                }
                if (targetMat == null || ReferenceEquals(current, targetMat)) return false;
                if (_pFontMaterial != null) _pFontMaterial.SetValue(tmpLabel, targetMat);
                else _pFontSharedMaterial.SetValue(tmpLabel, targetMat);
                try { _mSetMaterialDirty?.Invoke(tmpLabel, null); } catch { }
                try { _mSetVerticesDirty?.Invoke(tmpLabel, null); } catch { }
                try { _mUpdateMaterial?.Invoke(tmpLabel, null); } catch { }
                return true;
            }
            catch { return false; }
        }

        private void RestoreLabel(Component comp)
        {
            if (comp == null) return;
            if (!_states.TryGetValue(comp, out var state)) return;
            if (!string.IsNullOrEmpty(state.LastAppliedSku) && state.OriginalMaterial != null)
            {
                try { _pFontSharedMaterial.SetValue(comp, state.OriginalMaterial); } catch { }
            }
            state.LastAppliedSku = "";
        }

        private void RestoreAllLabels()
        {
            foreach (var kv in _states)
            {
                if (kv.Key == null) continue;
                if (string.IsNullOrEmpty(kv.Value.LastAppliedSku)) continue;
                if (kv.Value.OriginalMaterial == null) continue;
                try { _pFontSharedMaterial.SetValue(kv.Key, kv.Value.OriginalMaterial); } catch { }
                kv.Value.LastAppliedSku = "";
            }
        }
    }
}
