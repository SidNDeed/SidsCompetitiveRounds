using System;
using System.Collections.Generic;
using HarmonyLib;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Stage 2 S5 client: the expiry runs the path of today with the cut as
    /// input. A 2v2 survivor executes its OWN latched eligibility (the plan
    /// the leave callback built in the leave frame: prompt or floor report
    /// with the cut's points, the fallback watch on its latched target, or
    /// nothing); then every survivor of either mode runs the vanilla leave
    /// body for the first drop. 1v2 reports nothing, as today. A survivor
    /// whose own menu leave ends the hold reports but skips the vanilla
    /// body: it is leaving the room already.
    /// </summary>
    internal static class TeamHoldExpiry
    {
        internal static void Run(TeamHoldRules.DropCut cut, string reason)
        {
            if (cut == null) return;
            var ops = TeamHoldRules.ExpiryActions(cut, null);
            foreach (var op in ops)
            {
                try
                {
                    switch (op)
                    {
                        case TeamHoldRules.ExpiryOp.ReportPrompt:
                        case TeamHoldRules.ExpiryOp.ReportFloor:
                        case TeamHoldRules.ExpiryOp.ArmFallback:
                            Cr2v2DiagCallbacks.ExecuteDcPlan(cut.Plan as Cr2v2DiagCallbacks.DcPlan);
                            break;
                        case TeamHoldRules.ExpiryOp.VanillaLeave:
                            if (reason != "survivor_leave") VanillaLeave(cut);
                            break;
                    }
                }
                catch (Exception ex) { Plugin.Log.LogWarning(TeamHold.TAG + " expiry " + op + ": " + ex.Message); }
            }
            Plugin.Log.LogInfo(TeamHold.TAG + " expiry ran (" + (reason ?? "") + ") ops=" + string.Join(",", ops));
        }

        /// <summary>The vanilla OnPlayerLeftRoom body for the first drop,
        /// with the departing Photon player retained in the cut, through the
        /// reverse-patch stub (no prefix of today runs again).</summary>
        private static void VanillaLeave(TeamHoldRules.DropCut cut)
        {
            var nch = NetworkConnectionHandler.instance;
            if (nch == null) return;
            var p = cut.Leaver as Photon.Realtime.Player;
            try { TeamHold_VanillaLeaveStub.OnPlayerLeftRoom(nch, p); }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning(TeamHold.TAG + " vanilla leave stub: " + ex.Message + "; running its statement directly");
                nch.StartCoroutine(nch.DoDisconnect(nch.m_localizedDisconnect, nch.m_localizedOtherLeft));
            }
        }
    }

    /// <summary>A copy of vanilla NetworkConnectionHandler.OnPlayerLeftRoom
    /// without any prefix: the teardown of today, run once at the expiry.</summary>
    [HarmonyPatch(typeof(NetworkConnectionHandler))]
    internal static class TeamHold_VanillaLeaveStub
    {
        [HarmonyReversePatch]
        [HarmonyPatch("OnPlayerLeftRoom")]
        internal static void OnPlayerLeftRoom(NetworkConnectionHandler instance, Photon.Realtime.Player otherPlayer)
        {
            throw new NotImplementedException("the reverse patch did not attach");
        }
    }
}
