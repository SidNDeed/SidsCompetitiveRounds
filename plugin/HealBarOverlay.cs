using System;
using System.Collections.Generic;
using System.Reflection;
using HarmonyLib;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Blue "recently healed" segment on the vanilla health bar
    /// (owner item 3, Aug 30; design-reviewed by Codex the same day).
    ///
    /// Vanilla HealthBar has exactly two fills: hp (live) and white (the red
    /// trailing "recently lost" segment, frozen by sinceDamage for 0.5s while
    /// hp springs down). Healing has NO bar visual at all — Heal() emits a
    /// particle burst and nothing else. This overlay mirrors the red
    /// segment's design with the polarity flipped: a third fill drawn BEHIND
    /// both vanilla fills jumps to the live target while hp springs up, so
    /// the visible blue band is the health being regained and it closes as
    /// hp catches up. Pure per-seat display: no vanilla field is ever
    /// written, no events, no network (#338-safe on every seat, spectator
    /// included — spectator lifesteal renders through Heal and moves
    /// data.health, which is all this reads).
    ///
    /// Review-mandated shape (design round, Aug 30):
    /// - FRESH GameObject with only RectTransform + reflected Image — never
    ///   Instantiate(hb.hp.gameObject): the serialized fill can carry
    ///   arbitrary behaviours whose clones would run their lifecycles.
    /// - Runtime sibling validation, fail-closed: hp and white must share a
    ///   parent with whiteIndex &lt; hpIndex; blue inserts before white and
    ///   the final order blue &lt; white &lt; hp is re-read and asserted. Any
    ///   mismatch logs once and disables ONLY the blue overlay.
    /// - Explicit baseline init + reset on Revive/OnEnable so spawn-in and
    ///   revival full-health assignments never read as heals.
    /// - Cumulative sub-epsilon rise detection so slow regeneration is not
    ///   discarded frame-by-frame.</summary>
    internal sealed class HealBarOverlay : MonoBehaviour
    {
        private const float HOLD_SECONDS = 0.5f;   // matches white's re-sync window
        private const float HEAL_EPSILON = 0.3f;   // hp; accumulates across frames
        private static readonly Color BLUE = new Color(0.32f, 0.72f, 1f);

        private static PropertyInfo pFillAmount, pImgSprite, pImgMaterial, pImgColor,
            pImgType, pImgFillMethod, pImgFillOrigin, pImgFillClockwise, pImgPreserveAspect, pImgRaycast;
        private static bool reflectResolved, reflectFailed;

        private HealthBar bar;
        private CharacterData data;
        private object blueImg;          // reflected UnityEngine.UI.Image
        private GameObject blueGO;
        private float prevHealth;
        private float healAccum;
        private float sinceHeal = 999f;
        private bool disabledForever;

        private static bool ResolveReflection(object sampleImage)
        {
            if (reflectResolved) return !reflectFailed;
            reflectResolved = true;
            try
            {
                var t = UIFactory.tImage ?? sampleImage?.GetType();
                if (t == null) { reflectFailed = true; return false; }
                const BindingFlags bf = BindingFlags.Public | BindingFlags.Instance;
                pFillAmount = t.GetProperty("fillAmount", bf);
                pImgSprite = t.GetProperty("sprite", bf);
                pImgMaterial = t.GetProperty("material", bf);
                pImgColor = t.GetProperty("color", bf);
                pImgType = t.GetProperty("type", bf);
                pImgFillMethod = t.GetProperty("fillMethod", bf);
                pImgFillOrigin = t.GetProperty("fillOrigin", bf);
                pImgFillClockwise = t.GetProperty("fillClockwise", bf);
                pImgPreserveAspect = t.GetProperty("preserveAspect", bf);
                pImgRaycast = t.GetProperty("raycastTarget", bf);
                reflectFailed = pFillAmount == null || pImgColor == null;
            }
            catch { reflectFailed = true; }
            return !reflectFailed;
        }

        private void Start()
        {
            try
            {
                bar = GetComponent<HealthBar>();
                data = GetComponentInParent<CharacterData>();
                // hp/white are typed UnityEngine.UI.Image — an assembly this
                // csproj deliberately never references (#15), so the fields
                // are read by reflection and handled as object/Component.
                object hpImg = bar != null ? AccessTools.Field(typeof(HealthBar), "hp")?.GetValue(bar) : null;
                object whiteImg = bar != null ? AccessTools.Field(typeof(HealthBar), "white")?.GetValue(bar) : null;
                if (bar == null || data == null || hpImg == null || whiteImg == null
                    || (hpImg as UnityEngine.Object) == null || (whiteImg as UnityEngine.Object) == null
                    || !ResolveReflection(hpImg))
                { DisableBlue("missing bar/fills"); return; }

                var hpRT = ((Component)hpImg).GetComponent<RectTransform>();
                var whiteRT = ((Component)whiteImg).GetComponent<RectTransform>();
                if (hpRT == null || whiteRT == null || hpRT.parent == null
                    || !ReferenceEquals(hpRT.parent, whiteRT.parent))
                { DisableBlue("hp/white parents differ"); return; }
                if (whiteRT.GetSiblingIndex() >= hpRT.GetSiblingIndex())
                { DisableBlue("unexpected vanilla fill order"); return; }

                blueGO = new GameObject("CR_HealFill");
                blueGO.transform.SetParent(hpRT.parent, false);
                var rt = blueGO.AddComponent<RectTransform>();
                rt.anchorMin = hpRT.anchorMin; rt.anchorMax = hpRT.anchorMax;
                rt.pivot = hpRT.pivot;
                rt.anchoredPosition = hpRT.anchoredPosition;
                rt.sizeDelta = hpRT.sizeDelta;
                rt.localScale = hpRT.localScale;
                rt.localRotation = hpRT.localRotation;
                blueImg = blueGO.AddComponent(UIFactory.tImage);
                // Copy the render-relevant Image settings from the live fill;
                // color becomes blue with the authored alpha.
                CopyProp(pImgSprite, hpImg); CopyProp(pImgMaterial, hpImg);
                CopyProp(pImgType, hpImg); CopyProp(pImgFillMethod, hpImg);
                CopyProp(pImgFillOrigin, hpImg); CopyProp(pImgFillClockwise, hpImg);
                CopyProp(pImgPreserveAspect, hpImg);
                try { pImgRaycast?.SetValue(blueImg, false); } catch { }
                float a = 1f;
                try { var c = (Color)pImgColor.GetValue(hpImg); a = c.a; } catch { }
                var blue = BLUE; blue.a = a;
                pImgColor.SetValue(blueImg, blue);

                blueGO.transform.SetSiblingIndex(whiteRT.GetSiblingIndex());
                if (!(blueGO.transform.GetSiblingIndex() < whiteRT.GetSiblingIndex()
                      && whiteRT.GetSiblingIndex() < hpRT.GetSiblingIndex()))
                { DisableBlue("post-insert order assert failed"); return; }

                ResetBaseline();
            }
            catch (Exception ex) { DisableBlue("init threw: " + ex.Message); }
        }

        private void CopyProp(PropertyInfo p, object src)
        {
            try { if (p != null) p.SetValue(blueImg, p.GetValue(src)); } catch { }
        }

        private static bool orderWarned;
        private void DisableBlue(string why)
        {
            disabledForever = true;
            try { if (blueGO != null) UnityEngine.Object.Destroy(blueGO); } catch { }
            blueGO = null; blueImg = null;
            if (!orderWarned)
            {
                orderWarned = true;
                try { Plugin.Log?.LogWarning("[HEALBAR] blue overlay disabled: " + why); } catch { }
            }
            enabled = false;
        }

        /// <summary>Baseline = current health, no armed heal. Called from
        /// Start, OnEnable and the Revive postfix so initialization and the
        /// full-health revival assignment never read as healing.</summary>
        internal void ResetBaseline()
        {
            try { prevHealth = data != null ? data.health : 0f; } catch { prevHealth = 0f; }
            healAccum = 0f;
            sinceHeal = 999f;
            try
            {
                if (blueImg != null && bar != null && pFillAmount != null)
                    pFillAmount.SetValue(blueImg, bar.hpCur);
            }
            catch { }
        }

        private void OnEnable()
        {
            if (bar != null) ResetBaseline();
        }

        private void LateUpdate()
        {
            if (disabledForever) return;
            try
            {
                if (bar == null || data == null || blueImg == null || blueGO == null)
                { DisableBlue("component went away"); return; }
                // Runs AFTER every Update (Unity finishes all Updates before
                // any LateUpdate), so hpCur/hpTarg are this frame's values.
                float h = data.health;
                float delta = h - prevHealth;
                prevHealth = h;
                if (delta > 0f)
                {
                    healAccum += delta;
                    if (healAccum >= HEAL_EPSILON) { healAccum = 0f; sinceHeal = 0f; }
                }
                else if (delta < 0f)
                {
                    healAccum = 0f;   // damage clears any sub-epsilon build-up
                }
                sinceHeal += TimeHandler.deltaTime;
                bool showing = sinceHeal < HOLD_SECONDS;
                float fill = showing ? Mathf.Max(bar.hpCur, bar.hpTarg) : bar.hpCur;
                pFillAmount.SetValue(blueImg, fill);
            }
            catch { DisableBlue("tick threw"); }
        }
    }

    /// <summary>Attach/reset hooks. HealthBar.Start runs once per component
    /// lifetime; the AddComponent is still guarded by an exact component
    /// check (idempotent under cloning or patch reapplication).</summary>
    [HarmonyPatch(typeof(HealthBar), "Start")]
    internal static class HealthBar_AttachHealOverlay_Patch
    {
        private static void Postfix(HealthBar __instance)
        {
            try
            {
                if (__instance == null) return;
                if (__instance.GetComponent<HealBarOverlay>() != null) return;
                __instance.gameObject.AddComponent<HealBarOverlay>();
            }
            catch { }
        }
    }

    /// <summary>Revive assigns full health directly; without this reset the
    /// overlay would paint a half-second blue band on every round respawn
    /// (design-review CONFIRMED finding).</summary>
    [HarmonyPatch(typeof(HealthHandler), "Revive")]
    internal static class HealthHandler_HealOverlayReviveReset_Patch
    {
        private static void Postfix(HealthHandler __instance)
        {
            try
            {
                var ov = __instance != null ? __instance.GetComponentInChildren<HealBarOverlay>(true) : null;
                if (ov != null) ov.ResetBaseline();
            }
            catch { }
        }
    }
}
