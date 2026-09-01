using System;
using System.Reflection;
using HarmonyLib;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Status-indicator repairs: (1) REWIRES SilenceHandler.codeAnim to the
    /// authored-but-orphaned red X (vanilla mis-wires it to the stun
    /// triangles — see RewireSilenceX's comment for the asset evidence);
    /// (2) restores the serialized Player-prefab colors for silence and stun
    /// when their indicators rise. The body-color cosmetic sprite pass
    /// previously captured these gameplay indicators; re-asserting the
    /// sharedassets0 authored colors here also overrides any future tint pass
    /// (ours or a third party's) at the moment the indicator is shown.
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

        // ── Bug: the silence red X never shows, "dazzle" triangles do ──────
        // ROOT CAUSE (asset-verified, Aug 31 batch): vanilla 1.1.2's Player
        // prefab mis-wires SilenceHandler.codeAnim to the STUN indicator's
        // CodeAnimation (Effects/Stun/Scale — the three spinning blue
        // triangles), while the authored red X (Effects/Silence/Scale, two
        // red bars at +/-45deg, setFirstFrame=1 so it starts hidden, In =
        // scale 0->1, Out = 1->0) is referenced by NOTHING in the shipped
        // game. So a silenced player showed the stun triangles ("dazzle")
        // and the X was structurally unreachable — in every mode, with or
        // without the mod. The fix is a REWIRE, not new art: point codeAnim
        // at the orphaned X. Purely per-seat visual state (silence itself
        // replicates via vanilla's RPCA_AddSilence), so this needs no
        // capability gate and stays ungated (#286). After the rewire the
        // two handlers touch disjoint sprite sets, which also fixes the
        // old Reassert painting the shared triangles red on every silence.
        // NOTE the v1.39.6 changelog's "restored the silence X" claim was
        // wrong — the zero-scale belt below was real but aimed at the
        // (mis-wired) stun animator; THIS is the restoration.
        private static bool rewireLogged, rewireFailLogged;

        internal static void RewireSilenceX(SilenceHandler h)
        {
            try
            {
                if (h == null) return;
                var t = h.transform.Find("Effects/Silence/Scale");
                var x = t != null ? t.GetComponent<CodeAnimation>() : null;
                if (x == null)
                {
                    // Silent-degrade rule (#428): the "could not do it" branch
                    // logs, once — a future game update that renames the path
                    // must be diagnosable from any bug bundle.
                    if (!rewireFailLogged)
                    {
                        rewireFailLogged = true;
                        Plugin.Log?.LogWarning("[SILENCE-X] Effects/Silence/Scale not found — keeping vanilla codeAnim wiring");
                    }
                    return;
                }
                if (!ReferenceEquals(h.codeAnim, x))
                {
                    h.codeAnim = x;
                    if (!rewireLogged)
                    {
                        rewireLogged = true;
                        Plugin.Log?.LogInfo("[SILENCE-X] rewired SilenceHandler.codeAnim to the authored red X (vanilla points it at the stun triangles)");
                    }
                }
            }
            catch
            {
                // A visual repair must never break the silence debuff itself.
            }
        }

        /// <summary>Rewire at component Start (the normal path — runs before
        /// any silence can arrive on a freshly spawned player).</summary>
        [HarmonyPatch(typeof(SilenceHandler), "Start")]
        internal static class SilenceStartRewirePatch
        {
            private static void Postfix(SilenceHandler __instance)
            {
                RewireSilenceX(__instance);
            }
        }

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
                // Belt on the rewire: an RPC-driven StartSilence can in
                // principle land before the component's own Start has run —
                // rewiring here too (idempotent) means the X plays either way.
                try { RewireSilenceX(__instance); } catch { }
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
                    DumpIndicatorOnce(__instance);
                }
                catch
                {
                    // Swallow-only: indicator repair cannot interrupt silence.
                }
            }
        }

        // One-shot diagnostic: the exact subtree StartSilence just played —
        // names, sprites, colors, world scale/pos. A bug bundle then answers
        // "what did the indicator actually render as" in one grep (#428's
        // silent-degrade rule applied to a visual).
        private static bool indicatorDumped;
        private static void DumpIndicatorOnce(SilenceHandler h)
        {
            if (indicatorDumped || h == null || h.codeAnim == null) return;
            indicatorDumped = true;
            try
            {
                var sb = new System.Text.StringBuilder("[SILENCE-X] indicator dump:");
                var t = h.codeAnim.transform;
                sb.Append($" anim={t.name} parent={(t.parent != null ? t.parent.name : "-")}")
                  .Append($" active={t.gameObject.activeInHierarchy} lscale={t.localScale} wpos={t.position}");
                foreach (var sr in t.GetComponentsInChildren<SpriteRenderer>(true))
                {
                    if (sr == null) continue;
                    sb.Append($" | {sr.transform.parent?.name}/{sr.name}: sprite={(sr.sprite != null ? sr.sprite.name : "-")}")
                      .Append($" color=({sr.color.r:F2},{sr.color.g:F2},{sr.color.b:F2},{sr.color.a:F2})")
                      .Append($" en={sr.enabled} act={sr.gameObject.activeInHierarchy} ws={sr.transform.lossyScale} wp={sr.transform.position}");
                }
                Plugin.Log?.LogInfo(sb.ToString());
            }
            catch { }
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
