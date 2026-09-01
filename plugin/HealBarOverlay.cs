using System;
using System.Reflection;
using HarmonyLib;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Blue "recently healed" segment on the vanilla health bar
    /// (owner item 3, Aug 30; REDESIGNED Aug 31 after Sid's "I totally don't
    /// see the blue" report).
    ///
    /// WHY THE V1 DESIGN WAS INVISIBLE (recon-proven, #351-class): v1 drew a
    /// third FILL behind both vanilla fills and held it at the live target
    /// while hp sprang up. But vanilla's spring closes ~95% of the gap in
    /// 0.12-0.2s, so the visible wedge lived ~10 frames regardless of any
    /// hold constant — mathematically bounded by hp's own catch-up time
    /// (behind-order means blue is covered the instant hpCur reaches hpTarg).
    /// Regeneration made a sub-pixel band by construction, and any heal
    /// within 0.5s of damage hid entirely under the frozen red trail.
    ///
    /// V2 DESIGN — a rolling-window SEGMENT drawn ON TOP:
    /// - blue band = [health fraction WINDOW_SECONDS ago, current fraction],
    ///   shown only while the net delta over the window is a real heal. One
    ///   rule covers every case: chunk heals show a full-width band that
    ///   persists for the whole window; regen shows a steady band equal to a
    ///   window's worth of regen; damage after (or during) the window makes
    ///   the delta non-positive and hides the band. No arming logic, no
    ///   accumulator, no interplay with the spring at all.
    /// - The segment is a CHILD of the hp fill's RectTransform with
    ///   fractional anchors — children are not cropped by fillAmount and
    ///   render after the parent, so the band paints over both vanilla fills.
    ///   Painting over the red trail's lower region is semantically right:
    ///   that part of the bar was just regained, not recently lost.
    /// - Pure per-seat display: reads data.health/MaxHealth only, writes
    ///   nothing vanilla, no events, no network (#338-safe on every seat;
    ///   spectator lifesteal renders through Heal -> data.health moves).
    ///
    /// Kept from the review-mandated v1 shape: fresh GameObject (never a
    /// clone of a serialized fill), fail-closed asserts with a single
    /// [HEALBAR] log line, explicit baseline reset on Start/OnEnable/Revive
    /// so spawn-in and revival full-health assignments never read as heals.</summary>
    internal sealed class HealBarOverlay : MonoBehaviour
    {
        private const float WINDOW_SECONDS = 1.2f;  // band = net gain over this window
        private const float SAMPLE_STEP = 0.1f;     // ring cadence (TimeHandler-scaled, like the bar's own springs)
        private const int SLOTS = 13;               // ceil(WINDOW/STEP) + 1
        private const float HEAL_EPSILON = 0.3f;    // hp; below this a "band" is noise
        private static readonly Color BLUE = new Color(0.32f, 0.72f, 1f, 0.9f);

        private static PropertyInfo pImgColor, pImgRaycast;
        private static bool reflectResolved, reflectFailed;

        private CharacterData data;
        private GameObject blueGO;
        private RectTransform blueRT;
        private readonly float[] ring = new float[SLOTS];
        private int ringHead;
        private float sampleClock;
        private float lastMax = -1f;
        private bool disabledForever;

        private static bool ResolveReflection()
        {
            if (reflectResolved) return !reflectFailed;
            reflectResolved = true;
            try
            {
                var t = UIFactory.tImage;
                if (t == null) { reflectFailed = true; return false; }
                const BindingFlags bf = BindingFlags.Public | BindingFlags.Instance;
                pImgColor = t.GetProperty("color", bf);
                pImgRaycast = t.GetProperty("raycastTarget", bf);
                reflectFailed = pImgColor == null;
            }
            catch { reflectFailed = true; }
            return !reflectFailed;
        }

        private void Start()
        {
            try
            {
                var bar = GetComponent<HealthBar>();
                data = GetComponentInParent<CharacterData>();
                // hp is a typed UnityEngine.UI.Image — an assembly this csproj
                // deliberately never references (#15) — so it is only ever
                // handled as object/Component here.
                object hpImg = bar != null ? AccessTools.Field(typeof(HealthBar), "hp")?.GetValue(bar) : null;
                if (bar == null || data == null || hpImg == null
                    || (hpImg as UnityEngine.Object) == null || !ResolveReflection())
                { DisableBlue("missing bar/fill/reflection"); return; }

                var hpRT = ((Component)hpImg).GetComponent<RectTransform>();
                if (hpRT == null) { DisableBlue("hp fill has no RectTransform"); return; }

                blueGO = new GameObject("CR_HealBand");
                blueGO.transform.SetParent(hpRT, false);
                blueRT = blueGO.AddComponent<RectTransform>();
                blueRT.anchorMin = new Vector2(0f, 0f);
                blueRT.anchorMax = new Vector2(0f, 1f);   // zero-width until a heal
                blueRT.offsetMin = Vector2.zero;
                blueRT.offsetMax = Vector2.zero;
                blueRT.localScale = Vector3.one;
                var img = blueGO.AddComponent(UIFactory.tImage);
                if (img == null) { DisableBlue("Image add failed"); return; }
                pImgColor.SetValue(img, BLUE);
                try { pImgRaycast?.SetValue(img, false); } catch { }

                ResetBaseline();
            }
            catch (Exception ex) { DisableBlue("init threw: " + ex.Message); }
        }

        private static bool healbarWarned;
        private void DisableBlue(string why)
        {
            disabledForever = true;
            try { if (blueGO != null) UnityEngine.Object.Destroy(blueGO); } catch { }
            blueGO = null; blueRT = null;
            if (!healbarWarned)
            {
                healbarWarned = true;
                try { Plugin.Log?.LogWarning("[HEALBAR] blue overlay disabled: " + why); } catch { }
            }
            enabled = false;
        }

        /// <summary>Prime the whole window with the CURRENT fraction — no band.
        /// Called from Start, OnEnable and the Revive postfix so initialization
        /// and the full-health revival assignment never read as healing.</summary>
        internal void ResetBaseline()
        {
            try
            {
                float max = data != null ? Mathf.Max(1f, data.MaxHealth) : 1f;
                float frac = data != null ? Mathf.Clamp01(data.health / max) : 0f;
                lastMax = max;
                for (int i = 0; i < SLOTS; i++) ring[i] = frac;
                ringHead = 0; sampleClock = 0f;
                SetBand(0f, 0f);
            }
            catch { }
        }

        private void OnEnable()
        {
            if (data != null) ResetBaseline();
        }

        private void SetBand(float startFrac, float endFrac)
        {
            if (blueRT == null) return;
            blueRT.anchorMin = new Vector2(Mathf.Clamp01(startFrac), 0f);
            blueRT.anchorMax = new Vector2(Mathf.Clamp01(endFrac), 1f);
            blueRT.offsetMin = Vector2.zero;
            blueRT.offsetMax = Vector2.zero;
        }

        private void LateUpdate()
        {
            if (disabledForever) return;
            try
            {
                if (data == null || blueRT == null)
                { DisableBlue("component went away"); return; }
                float max = Mathf.Max(1f, data.MaxHealth);
                if (!Mathf.Approximately(max, lastMax))
                {
                    // Max-health changes (card picks) remap every stored
                    // fraction — re-prime rather than paint a phantom band.
                    ResetBaseline();
                    return;
                }
                float frac = Mathf.Clamp01(data.health / max);
                sampleClock += TimeHandler.deltaTime;
                int guard = 0;
                while (sampleClock >= SAMPLE_STEP && guard++ < SLOTS)
                {
                    sampleClock -= SAMPLE_STEP;
                    ringHead = (ringHead + 1) % SLOTS;
                    ring[ringHead] = frac;
                }
                float oldest = ring[(ringHead + 1) % SLOTS];
                float epsFrac = Mathf.Max(HEAL_EPSILON / max, 0.004f);
                if (frac - oldest >= epsFrac) SetBand(oldest, frac);
                else SetBand(0f, 0f);
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
    /// overlay would paint a blue band on every round respawn
    /// (design-review CONFIRMED finding, kept from v1).</summary>
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
