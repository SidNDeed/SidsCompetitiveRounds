using System;
using HarmonyLib;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Ask 16(a) section 2, round pips. Vanilla's RoundCounter.GetPointPos
    /// returns GetChild(rounds) with no bound (decompiled RoundCounter
    /// :134-142), and PointVisualizer calls it on every round win (:150-166).
    /// A team whose rounds reach its pip count, which only a game past its pips
    /// can do, would throw there on every round win.
    ///
    /// This prefix leaves every in-range call to vanilla, untouched, and answers
    /// an out-of-range one with the nearest pip's position. A game that stays
    /// within its pips never reaches that branch, so it needs no gate. Keeping
    /// the pip count at the base when a target rises is lane 2's, with the
    /// record that raises it.
    /// </summary>
    [HarmonyPatch(typeof(RoundCounter), "GetPointPos")]
    internal static class RoundCounterGetPointPosClampPatch
    {
        [HarmonyPrefix]
        private static bool BeforeGetPointPos(RoundCounter __instance, int teamID, ref Vector3 __result,
                                              bool __runOriginal)
        {
            if (!__runOriginal) return true;   // an earlier prefix has answered
            try
            {
                if (__instance == null) return true;
                Transform parent = teamID == 0 ? __instance.p1Parent : __instance.p2Parent;
                int rounds = teamID == 0 ? __instance.p1Rounds : __instance.p2Rounds;
                if (parent == null || (rounds >= 0 && rounds < parent.childCount)) return true;
                int count = parent.childCount;
                __result = count > 0 ? parent.GetChild(rounds < 0 ? 0 : count - 1).transform.position
                                     : parent.position;
                VanillaFixSupport.DiagLimited("round-pips", "[PIPS] team " + teamID + " at " + rounds
                    + " rounds past " + count + " pips: the nearest pip answers", 5);
                return false;
            }
            catch (Exception ex) { VanillaFixSupport.LogError("RoundPipClamp", ex); }
            return true;
        }
    }
}
