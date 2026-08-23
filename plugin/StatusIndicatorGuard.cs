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
    /// </summary>
    internal static class StatusIndicatorGuard
    {
        private static readonly Color SilenceColor =
            new Color(0.6226f, 0.2614f, 0.2842f, 1f);
        private static readonly Color StunColor =
            new Color(0.2979f, 0.4277f, 0.6132f, 1f);

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
