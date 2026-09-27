using System;
using System.Reflection;
using HarmonyLib;
using Photon.Pun;

namespace CompetitiveRounds
{
    /// <summary>v1.41.0 beta round 7, finding F29: the game's own start, as
    /// TeamGameNumber counts it. GM_ArmsRace.DoStartGame runs on every seat
    /// once per game (the first game through StartGame, every same-room
    /// rematch through IDoRematch, #138), whatever the watcher's polls see.
    /// TeamGameNumber (Tracker.OnGmStart) counts those starts to tell a game
    /// start the game reported from one it did not (a join or a rejoin in
    /// the middle of a game, a watcher that missed a game), and holds a
    /// physical-game ordinal only across starts the game reported. A hook
    /// that never attaches, or never runs, leaves every game start
    /// unreported: no seat then takes a game token or names a physical game,
    /// so its failure only ever withholds.
    ///
    /// Every sibling prefix on DoStartGame runs whatever the others return
    /// (#352; HarmonyX has no __runOriginal, #510): FfaMode replaces the flow
    /// in FFA and SpectatorPatches suppresses it on a spectator. So this one
    /// runs last, carries its own gates (online, a fighter seat, a cr_ff
    /// room), changes nothing (a void prefix: it never touches __result) and
    /// depends on no ordering.</summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "DoStartGame")]
    internal static class TeamGameLifecycle_DoStartGame_Patch
    {
        [HarmonyPriority(Priority.Last)]
        private static void Prefix()
        {
            try
            {
                if (PhotonNetwork.OfflineMode || !PhotonNetwork.InRoom || RoomActors.LocalIsSpectator) return;
                var props = PhotonNetwork.CurrentRoom?.CustomProperties;
                if (props == null || !props.ContainsKey("cr_ff")) return;
                TeamGameNumber.Live.OnGmStart(PhotonNetwork.CurrentRoom?.Name ?? "");
            }
            catch { }
        }

        /// <summary>The positive attach signal (#83), on the shape of the
        /// shipped [HarmonyCleanup] patches: Harmony calls this once at class
        /// level with a null `original` after the patch job ran; a null
        /// `exception` there means the prefix was installed.</summary>
        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            try
            {
                if (exception == null)
                    Plugin.Log.LogInfo(TeamGameNumber.LogTag + " lifecycle hook attached: GM_ArmsRace.DoStartGame");
            }
            catch { }
            return exception;
        }
    }
}
