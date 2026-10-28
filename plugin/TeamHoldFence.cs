using System.Collections;
using HarmonyLib;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Stage 2 S2, the freeze (RJS-M4). In a flagged room the two two-team
    /// transitions run as mod copies of the vanilla statements, in order
    /// (TeamHoldRules.PointSteps and RoundSteps; V:GM_ArmsRace.cs:245-258 and
    /// 276-306), with one inserted statement: HoldFence.Wait() immediately
    /// before the boundary WaitForSyncUp. The per-picker syncs of
    /// RoundTransition are not fenced, so a due pick phase completes inside
    /// the hold. A rematch DoStartGame waits on the fence before its first
    /// statement. Every unflagged room runs vanilla unchanged.
    /// </summary>
    internal static class HoldFence
    {
        /// <summary>Returns at once unless the room holds a seat this client
        /// has neither released nor expired.</summary>
        internal static IEnumerator Wait()
        {
            bool logged = false;
            while (TeamHoldLoop.FenceHolds())
            {
                if (!logged) { logged = true; Plugin.Log.LogInfo(TeamHold.TAG + " boundary waits on the hold"); }
                yield return null;
            }
        }

        /// <summary>A flagged room on a fighter seat the FFA engine does not run.</summary>
        internal static bool Active()
        {
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode || FfaMode.EngineActive()) return false;
                return TeamHoldRules.Flagged(TeamHoldWriter.CurrentRoom());
            }
            catch { return false; }
        }

        /// <summary>The mod copy of a transition: the vanilla statements of
        /// <paramref name="steps"/>, in order.</summary>
        internal static IEnumerator Run(GM_ArmsRace gm, TeamHoldRules.Step[] steps, int winningTeamID, int killedTeamID)
        {
            foreach (var s in steps)
            {
                switch (s)
                {
                    case TeamHoldRules.Step.Visualize:
                        gm.StartCoroutine(PointVisualizer.instance.DoSequence(gm.p1Points, gm.p2Points, winningTeamID == 0));
                        break;
                    case TeamHoldRules.Step.WinVisualize:
                        gm.StartCoroutine(PointVisualizer.instance.DoWinSequence(gm.p1Points, gm.p2Points, gm.p1Rounds, gm.p2Rounds, winningTeamID == 0));
                        break;
                    case TeamHoldRules.Step.Wait1:
                        yield return new WaitForSecondsRealtime(1f);
                        break;
                    case TeamHoldRules.Step.Wait05:
                        yield return new WaitForSecondsRealtime(0.5f);
                        break;
                    case TeamHoldRules.Step.Wait03:
                        yield return new WaitForSecondsRealtime(0.3f);
                        break;
                    case TeamHoldRules.Step.LoadNext:
                        MapManager.instance.LoadNextLevel();
                        break;
                    case TeamHoldRules.Step.SpeedUp:
                        TimeHandler.instance.DoSpeedUp();
                        break;
                    case TeamHoldRules.Step.SlowDown:
                        TimeHandler.instance.DoSlowDown();
                        break;
                    case TeamHoldRules.Step.PickPhase:
                        if (gm.pickPhase)
                        {
                            Debug.Log("PICK PHASE");
                            PlayerManager.instance.SetPlayersVisible(visible: false);
                            Player[] players = PlayerManager.instance.GetPlayersInTeam(killedTeamID);
                            for (int i = 0; i < players.Length; i++)
                            {
                                yield return gm.StartCoroutine(gm.WaitForSyncUp());
                                yield return CardChoice.instance.DoPick(1, players[i].PlayerID, PickerType.Player);
                                yield return new WaitForSecondsRealtime(0.1f);
                            }
                            PlayerManager.instance.SetPlayersVisible(visible: true);
                        }
                        break;
                    case TeamHoldRules.Step.Fence:
                        yield return Wait();
                        break;
                    case TeamHoldRules.Step.SyncUp:
                        yield return gm.StartCoroutine(gm.WaitForSyncUp());
                        break;
                    case TeamHoldRules.Step.CallInMove:
                        MapManager.instance.CallInNewMapAndMovePlayers(MapManager.instance.currentLevelID);
                        break;
                    case TeamHoldRules.Step.Revive:
                        PlayerManager.instance.RevivePlayers();
                        break;
                    case TeamHoldRules.Step.BattleOn:
                        GameManager.instance.battleOngoing = true;
                        break;
                    case TeamHoldRules.Step.TransitionOff:
                        gm.isTransitioning = false;
                        break;
                    case TeamHoldRules.Step.ShowCounter:
                        UIHandler.instance.ShowRoundCounterSmall(gm.p1Rounds, gm.p2Rounds, gm.p1Points, gm.p2Points);
                        break;
                }
            }
        }

        /// <summary>A rematch start: the fence, then the start flow the
        /// other DoStartGame prefixes chose, unchanged.</summary>
        internal static IEnumerator Fenced(IEnumerator inner)
        {
            yield return Wait();
            yield return inner;
        }
    }

    [HarmonyPatch(typeof(GM_ArmsRace), "PointTransition")]
    internal static class TeamHold_PointTransitionPatch
    {
        [HarmonyPrefix]
        private static bool Prefix(GM_ArmsRace __instance, int __0, ref IEnumerator __result)
        {
            try
            {
                if (!HoldFence.Active()) return true;
                __result = HoldFence.Run(__instance, TeamHoldRules.PointSteps, __0, -1);
                return false;
            }
            catch { return true; }
        }
    }

    [HarmonyPatch(typeof(GM_ArmsRace), "RoundTransition")]
    internal static class TeamHold_RoundTransitionPatch
    {
        [HarmonyPrefix]
        private static bool Prefix(GM_ArmsRace __instance, int __0, int __1, ref IEnumerator __result)
        {
            try
            {
                if (!HoldFence.Active()) return true;
                __result = HoldFence.Run(__instance, TeamHoldRules.RoundSteps, __0, __1);
                return false;
            }
            catch { return true; }
        }
    }

    /// <summary>The DoStartGame wrap. A postfix, not a prefix: the sibling
    /// prefixes (FFA, spectator) may replace the result and skip the
    /// original, and a prefix cannot see the enumerator the original creates;
    /// the postfix wraps whichever result the call produced.</summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "DoStartGame")]
    internal static class TeamHold_RematchFencePatch
    {
        [HarmonyPostfix]
        private static void Postfix(ref IEnumerator __result)
        {
            try { if (__result != null && HoldFence.Active()) __result = HoldFence.Fenced(__result); } catch { }
        }
    }
}
