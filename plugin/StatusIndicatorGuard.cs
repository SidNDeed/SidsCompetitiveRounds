using System;
using System.Reflection;
using HarmonyLib;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Restores the serialized Player-prefab colors for silence and stun when
    /// their indicators rise. The body-color cosmetic sprite pass previously
    /// captured these gameplay indicators; re-asserting the sharedassets0
    /// authored colors here also overrides any future tint pass (ours or a
    /// third party's) at the moment the indicator is shown.
    ///
    /// SCALE BELT (Aug 30, design-reviewed): vanilla SilenceHandler/
    /// StunHandler.OnDisable zero their codeAnim's transform.localScale, and
    /// CodeAnimation.Start captures defaultScale = localScale. If the FIRST
    /// OnDisable lands before the child's Start (players deactivate on death
    /// and can deactivate before a deferred Start), defaultScale latches
    /// ZERO and ApplyValues computes zero * curve forever — an invisible X
    /// with no error anywhere. The belt: capture the last good non-zero
    /// scale at the OnDisable PREFIX (before vanilla zeroes it), restore it
    /// in a CodeAnimation.Start PREFIX (before SetDefaults snapshots), and
    /// repair defaultScale in Start*-PREFIXES (PlayIn applies values
    /// SYNCHRONOUSLY, so a postfix is provably too late). Repairs log once
    /// per session so the next organic silence proves or refutes the
    /// zero-scale theory in any log.
    /// </summary>
    internal static class StatusIndicatorGuard
    {
        private static readonly Color SilenceColor =
            new Color(0.6226f, 0.2614f, 0.2842f, 1f);
        private static readonly Color StunColor =
            new Color(0.2979f, 0.4277f, 0.6132f, 1f);

        // Last good non-zero scale per indicator CodeAnimation. Only silence/
        // stun codeAnims ever enter this map, so the global Start prefix
        // below is a dictionary miss for every other CodeAnimation in the
        // game. Entries are captured once and never overwritten (a later
        // OnDisable mid-animation would capture a curve-scaled value).
        private static readonly System.Collections.Generic.Dictionary<CodeAnimation, Vector3>
            authoredScale = new System.Collections.Generic.Dictionary<CodeAnimation, Vector3>();
        private static bool scaleRepairLogged;

        private static void CaptureBaseline(CodeAnimation codeAnim)
        {
            try
            {
                if (codeAnim == null || authoredScale.ContainsKey(codeAnim)) return;
                if (authoredScale.Count > 64)
                {
                    // Fake-null sweep so departed players don't accumulate.
                    var dead = new System.Collections.Generic.List<CodeAnimation>();
                    foreach (var k in authoredScale.Keys) if (k == null) dead.Add(k);
                    foreach (var k in dead) authoredScale.Remove(k);
                }
                // Prefer the Start-captured authored value when it exists;
                // fall back to the live transform (still authored when Start
                // has not run — the zeroing is exactly what happens next).
                Vector3 v = codeAnim.defaultScale;
                if (v == Vector3.zero) v = codeAnim.transform.localScale;
                if (v == Vector3.zero) return;   // nothing good to keep
                authoredScale[codeAnim] = v;
            }
            catch { }
        }

        private static void RepairIfZero(CodeAnimation codeAnim, string who)
        {
            try
            {
                if (codeAnim == null) return;
                if (codeAnim.defaultScale != Vector3.zero) return;
                Vector3 v;
                if (!authoredScale.TryGetValue(codeAnim, out v) || v == Vector3.zero) return;
                codeAnim.defaultScale = v;
                if (codeAnim.transform.localScale == Vector3.zero)
                    codeAnim.transform.localScale = v;
                if (!scaleRepairLogged)
                {
                    scaleRepairLogged = true;
                    Plugin.Log?.LogWarning("[STATUS-X] " + who + " defaultScale was ZERO — repaired to " + v
                        + " (zero-capture lifecycle trap confirmed in this session)");
                }
            }
            catch { }
        }

        private static void Reassert(CodeAnimation codeAnim, Color color)
        {
            try
            {
                if (codeAnim == null) return;
                var renderers = codeAnim.transform.GetComponentsInChildren<SpriteRenderer>(true);
                foreach (var renderer in renderers)
                    if (renderer != null) renderer.color = color;
            }
            catch
            {
                // A readability repair must never affect the debuff itself.
            }
        }

        [HarmonyPatch]
        internal static class SilenceStartPatch
        {
            private static MethodBase TargetMethod()
            {
                MethodInfo method = AccessTools.Method(
                    typeof(SilenceHandler), "StartSilence", Type.EmptyTypes);
                if (method == null)
                    throw new InvalidOperationException(
                        "StatusIndicatorGuard: SilenceHandler.StartSilence() not found");
                return method;
            }

            [HarmonyPrefix]
            private static void Prefix(SilenceHandler __instance)
            {
                // BEFORE vanilla: PlayIn applies its first sample
                // synchronously, so a zero defaultScale must be repaired
                // ahead of the call, never after.
                try { if (__instance != null) RepairIfZero(__instance.codeAnim, "silence"); } catch { }
            }

            [HarmonyPostfix]
            private static void Postfix(SilenceHandler __instance)
            {
                try
                {
                    if (__instance != null) Reassert(__instance.codeAnim, SilenceColor);
                }
                catch
                {
                    // Swallow-only: indicator repair cannot interrupt silence.
                }
            }
        }

        /// <summary>Capture the good scale in an OnDisable PREFIX — the one
        /// moment the authored value is still on the transform before
        /// vanilla zeroes it (first disable), or already snapshotted in
        /// defaultScale (later disables).</summary>
        [HarmonyPatch(typeof(SilenceHandler), "OnDisable")]
        internal static class SilenceDisableCapturePatch
        {
            private static void Prefix(SilenceHandler __instance)
            {
                try { if (__instance != null) CaptureBaseline(__instance.codeAnim); } catch { }
            }
        }

        [HarmonyPatch(typeof(StunHandler), "OnDisable")]
        internal static class StunDisableCapturePatch
        {
            private static void Prefix(StunHandler __instance)
            {
                try { if (__instance != null) CaptureBaseline(__instance.codeAnim); } catch { }
            }
        }

        /// <summary>Restore the captured scale BEFORE SetDefaults snapshots
        /// it (Start's first statement chain). Dictionary miss for every
        /// CodeAnimation that is not a silence/stun indicator.</summary>
        [HarmonyPatch(typeof(CodeAnimation), "Start")]
        internal static class CodeAnimStartRestorePatch
        {
            private static void Prefix(CodeAnimation __instance)
            {
                try
                {
                    if (__instance == null || authoredScale.Count == 0) return;
                    Vector3 v;
                    if (!authoredScale.TryGetValue(__instance, out v) || v == Vector3.zero) return;
                    if (__instance.transform.localScale == Vector3.zero)
                    {
                        __instance.transform.localScale = v;
                        // This path heals the trap BEFORE SetDefaults ever
                        // snapshots zero, so RepairIfZero would stay silent —
                        // log here too or the [STATUS-X] diagnostic promise
                        // (the changelog's "the log will say which mechanism
                        // fired") is false on the most likely path (r2
                        // comment audit).
                        if (!scaleRepairLogged)
                        {
                            scaleRepairLogged = true;
                            Plugin.Log?.LogWarning("[STATUS-X] pre-Start zero scale restored to " + v
                                + " (zero-capture lifecycle trap healed before snapshot this session)");
                        }
                    }
                }
                catch { }
            }
        }

        [HarmonyPatch]
        internal static class StunStartPatch
        {
            private static MethodBase TargetMethod()
            {
                MethodInfo method = AccessTools.Method(
                    typeof(StunHandler), "StartStun", Type.EmptyTypes);
                if (method == null)
                    throw new InvalidOperationException(
                        "StatusIndicatorGuard: StunHandler.StartStun() not found");
                return method;
            }

            [HarmonyPrefix]
            private static void Prefix(StunHandler __instance)
            {
                try { if (__instance != null) RepairIfZero(__instance.codeAnim, "stun"); } catch { }
            }

            [HarmonyPostfix]
            private static void Postfix(StunHandler __instance)
            {
                try
                {
                    if (__instance != null) Reassert(__instance.codeAnim, StunColor);
                }
                catch
                {
                    // Swallow-only: indicator repair cannot interrupt stun.
                }
            }
        }
    }
}
