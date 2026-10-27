using System;
using System.Reflection;
using HarmonyLib;
using Photon.Pun;

namespace CompetitiveRounds
{
    /// <summary>v1.41.0 beta round 7: the game's own lifecycle on this seat,
    /// as TeamGameNumber reads it.
    ///
    /// Finding F29: GM_ArmsRace.DoStartGame runs on every seat once per game
    /// (the first game through StartGame, every same-room rematch through
    /// IDoRematch, #138), whatever the watcher's polls see. TeamGameNumber
    /// (Tracker.OnGmStart) counts those starts to tell a game start the game
    /// reported from one it did not (a join or a rejoin in the middle of a
    /// game, a watcher that missed a game), and holds a physical-game ordinal
    /// only across starts the game reported.
    ///
    /// Finding F30: GM_ArmsRace.GameOverTransition runs on every seat at its
    /// game over, started by GameOver inside the RPCA_NextRound call that sets
    /// the scoreboard to the game over, and DoStartGame runs in the same step
    /// as IDoRematch's ResetMatch, which clears it. The tracker ends the
    /// game's token at both (Tracker.OnGmGameOver, OnGmStart), so no reading
    /// of the next game can come before the last game's token ended, whatever
    /// the watcher saw. A post or a DC report carries a token only while both
    /// hooks are attached (HooksLive, read by TokenFor): a hook that never
    /// attaches leaves every post and report tokenless, and one that never
    /// runs leaves every game start unreported (no physical game, so no
    /// token), so a failure only ever withholds.
    ///
    /// Every sibling prefix on these methods runs whatever the others return
    /// (#352; HarmonyX has no __runOriginal, #510): FfaMode replaces the start
    /// flow in FFA, and SpectatorPatches suppresses both on a spectator. So
    /// each prefix here runs last, carries its own gates (online, a fighter
    /// seat, a cr_ff room), changes nothing (a void prefix: it never touches
    /// __result) and depends on no ordering.</summary>
    internal static class TeamGameLifecycle
    {
        /// <summary>Set by each patch class's [HarmonyCleanup] once its prefix
        /// is installed (the PoisonSync.PatchesLive pattern, #83).</summary>
        internal static bool StartHookLive, OverHookLive;

        /// <summary>Both hooks attached: the only state in which a post or a
        /// DC report carries a game token (Tracker.TokenFor).</summary>
        internal static bool HooksLive { get { return StartHookLive && OverHookLive; } }

        /// <summary>The gates both prefixes share: online, in a room, a
        /// fighter seat, a cr_ff room.</summary>
        internal static bool InTeamRoom()
        {
            if (PhotonNetwork.OfflineMode || !PhotonNetwork.InRoom || RoomActors.LocalIsSpectator) return false;
            var props = PhotonNetwork.CurrentRoom?.CustomProperties;
            return props != null && props.ContainsKey("cr_ff");
        }
    }

    [HarmonyPatch(typeof(GM_ArmsRace), "DoStartGame")]
    internal static class TeamGameLifecycle_DoStartGame_Patch
    {
        [HarmonyPriority(Priority.Last)]
        private static void Prefix()
        {
            try
            {
                if (!TeamGameLifecycle.InTeamRoom()) return;
                string line = TeamGameNumber.Live.OnGmStart(PhotonNetwork.CurrentRoom?.Name ?? "");
                if (line != null) Plugin.Log.LogInfo(line);
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
                {
                    TeamGameLifecycle.StartHookLive = true;
                    Plugin.Log.LogInfo(TeamGameNumber.LogTag + " lifecycle hook attached: GM_ArmsRace.DoStartGame");
                }
            }
            catch { }
            return exception;
        }
    }

    /// <summary>Round 7, finding F30: the game's own game over on this seat
    /// (TeamGameLifecycle).</summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "GameOverTransition")]
    internal static class TeamGameLifecycle_GameOverTransition_Patch
    {
        [HarmonyPriority(Priority.Last)]
        private static void Prefix()
        {
            try
            {
                if (!TeamGameLifecycle.InTeamRoom()) return;
                string line = TeamGameNumber.Live.OnGmGameOver();
                if (line != null) Plugin.Log.LogInfo(line);
            }
            catch { }
        }

        /// <summary>The positive attach signal (#83), as above.</summary>
        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            try
            {
                if (exception == null)
                {
                    TeamGameLifecycle.OverHookLive = true;
                    Plugin.Log.LogInfo(TeamGameNumber.LogTag + " lifecycle hook attached: GM_ArmsRace.GameOverTransition");
                }
            }
            catch { }
            return exception;
        }
    }
}
