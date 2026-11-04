#if SCR_FRAMETIME
using System;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using HarmonyLib;
using Photon.Pun;

namespace CompetitiveRounds
{
    /// <summary>F8, ruling R6-A3.11: during a sitting (FtConfig.Present) the only room the process may enter is the
    /// one the sitting names, FtArm.ExpectedRoom(), compared byte for byte; a null or empty name is refused, and so
    /// is every operation that matches, creates, or rejoins a room by anything other than that name.
    ///
    /// The class this closes (DIAGNOSIS-R6A36 section 7(a)): a seat alone in ft_&lt;sha8&gt; for 15 s was swept by
    /// vanilla's try-another-region timer (NetworkConnectionHandler.Update to PlayOnBestActiveRegion to
    /// JoinRandomRoom) into the public quick-match lobby. The gate is one rule over every room entry point:
    /// - PhotonNetwork: every public static method whose name carries "join" or "create" (any case), derived by
    ///   sweep at patch time, minus the two names that enter no room (JoinLobby: a lobby, never a room;
    ///   LoadOrCreateSettings: a settings asset). On the shipped assembly that is 9 overloads: JoinRandomRoom x3,
    ///   JoinRandomOrCreateRoom, CreateRoom, JoinOrCreateRoom, JoinRoom, RejoinRoom, ReconnectAndRejoin.
    /// - NetworkConnectionHandler: QuickMatch and JoinRandomRoom (void), PlayOnBestActiveRegion and DoRetry
    ///   (coroutines). The coroutines are refused at entry, so the LeaveRoom each one starts with never runs.
    /// Patch-time signal: one line, "[FRAME-TIME] FT-GATE patched N entry points expected=E", where N is
    /// counted from Harmony's own patch table (a prefix owned by this plugin on each target), not from the list.
    /// The timer half (ii) is FtChurnFreezePatch below.</summary>
    internal static class FtRoomGate
    {
        /// <summary>The names the sweep returns that enter no room, kept out of the gate on purpose.</summary>
        internal static readonly string[] NotRoomEntry = { "JoinLobby", "LoadOrCreateSettings" };

        /// <summary>NetworkConnectionHandler routines that reach a random or quick-match room.</summary>
        internal static readonly string[] NchVoid = { "QuickMatch", "JoinRandomRoom" };
        internal static readonly string[] NchRoutine = { "PlayOnBestActiveRegion", "DoRetry" };

        /// <summary>PhotonNetwork operations that never carry the sitting's room name: always refused.</summary>
        private static readonly HashSet<string> NoName = new HashSet<string>(StringComparer.Ordinal)
            { "JoinRandomRoom", "JoinRandomOrCreateRoom", "ReconnectAndRejoin" };

        private static readonly object _sync = new object();
        private static readonly Dictionary<string, long> _refused = new Dictionary<string, long>(StringComparer.Ordinal);

        /// <summary>The sweep: PhotonNetwork's public static methods whose name carries "join" or "create".</summary>
        internal static List<MethodBase> SweepPun(out List<string> excluded)
        {
            var list = new List<MethodBase>();
            excluded = new List<string>();
            foreach (var m in typeof(PhotonNetwork).GetMethods(BindingFlags.Public | BindingFlags.Static))
            {
                string n = m.Name;
                if (n.IndexOf("join", StringComparison.OrdinalIgnoreCase) < 0
                    && n.IndexOf("create", StringComparison.OrdinalIgnoreCase) < 0) continue;
                if (Array.IndexOf(NotRoomEntry, n) >= 0 || m.IsGenericMethodDefinition) { excluded.Add(n); continue; }
                list.Add(m);
            }
            return list;
        }

        internal static List<MethodBase> NchTargets(string[] names)
        {
            var list = new List<MethodBase>();
            foreach (var n in names)
            {
                var m = AccessTools.Method(typeof(NetworkConnectionHandler), n);
                if (m == null) throw new MissingMethodException("NetworkConnectionHandler", n);
                list.Add(m);
            }
            return list;
        }

        /// <summary>True only for the sitting's own room, byte for byte. Every refusal is logged with the
        /// operation and the name it carried, and counted per operation.</summary>
        internal static bool Admit(string op, string name)
        {
            string want = FtArm.ExpectedRoom();
            if (!NoName.Contains(op) && !string.IsNullOrEmpty(name) && !string.IsNullOrEmpty(want)
                && string.Equals(name, want, StringComparison.Ordinal)) return true;
            long n;
            lock (_sync)
            {
                _refused.TryGetValue(op, out n);
                n++;
                _refused[op] = n;
            }
            string shown = name == null ? "(none)" : (name.Length == 0 ? "(empty)" : name);
            Plugin.Log.LogWarning("[FRAME-TIME] room call refused op=" + op + " name=" + shown + " n=" + n);
            return false;
        }

        /// <summary>Called once, after Plugin's patch loop. Counts the targets that carry a prefix owned by this
        /// plugin's Harmony id in Harmony's own table, and logs the one patch-time line.</summary>
        internal static void ReportPatched()
        {
            int expected = 0, patched = 0;
            var missing = new List<string>();
            var all = new List<MethodBase>();
            List<string> excluded;
            try { all.AddRange(SweepPun(out excluded)); } catch (Exception ex) { excluded = new List<string>(); missing.Add("sweep: " + ex.Message); }
            foreach (var names in new[] { NchVoid, NchRoutine })
                foreach (var n in names)
                {
                    var m = AccessTools.Method(typeof(NetworkConnectionHandler), n);
                    if (m == null) missing.Add("NCH." + n + " (absent)"); else all.Add(m);
                }
            foreach (var m in all)
            {
                expected++;
                bool ours = false;
                try
                {
                    var info = Harmony.GetPatchInfo(m);
                    if (info != null)
                        foreach (var p in info.Prefixes)
                            if (p.owner == Plugin.ModId && p.PatchMethod != null
                                && p.PatchMethod.DeclaringType != null
                                && p.PatchMethod.DeclaringType.Name.StartsWith("FtRoomGate", StringComparison.Ordinal))
                            { ours = true; break; }
                }
                catch { }
                if (ours) patched++; else missing.Add(m.DeclaringType.Name + "." + m.Name);
            }
            Plugin.Log.LogInfo("[FRAME-TIME] FT-GATE patched " + patched + " entry points expected=" + expected
                + " excluded=" + string.Join(",", excluded.ToArray())
                + (missing.Count == 0 ? "" : " missing=" + string.Join(",", missing.ToArray())));
        }

        internal static IEnumerator Empty() { yield break; }
    }

    /// <summary>F8 (i): PhotonNetwork's room entry points. Runs first, so no other prefix stages a join first.</summary>
    [HarmonyPatch]
    internal static class FtRoomGatePunPatch
    {
        private static IEnumerable<MethodBase> TargetMethods()
        {
            List<string> excluded;
            var list = FtRoomGate.SweepPun(out excluded);
            if (list.Count == 0) throw new InvalidOperationException("FT-GATE: the PhotonNetwork sweep found no room entry point");
            return list;
        }

        [HarmonyPrefix]
        [HarmonyPriority(Priority.First)]
        private static bool Prefix(MethodBase __originalMethod, object[] __args, ref bool __result)
        {
            if (!FtConfig.Present) return true;
            string name = __args != null && __args.Length > 0 ? __args[0] as string : null;
            if (FtRoomGate.Admit(__originalMethod.Name, name)) return true;
            __result = false;
            return false;
        }
    }

    /// <summary>F8 (i): NetworkConnectionHandler's void routines that reach quick-match.</summary>
    [HarmonyPatch]
    internal static class FtRoomGateNchVoidPatch
    {
        private static IEnumerable<MethodBase> TargetMethods() { return FtRoomGate.NchTargets(FtRoomGate.NchVoid); }

        [HarmonyPrefix]
        [HarmonyPriority(Priority.First)]
        private static bool Prefix(MethodBase __originalMethod)
        {
            if (!FtConfig.Present) return true;
            FtRoomGate.Admit("NCH." + __originalMethod.Name, null);
            return false;
        }
    }

    /// <summary>F8 (i): NetworkConnectionHandler's coroutines that leave the room and then join at random. Refused
    /// at entry, so their LeaveRoom (NCH:327, NCH:574) never runs; the churn timer is re-frozen with no log line.</summary>
    [HarmonyPatch]
    internal static class FtRoomGateNchRoutinePatch
    {
        private static IEnumerable<MethodBase> TargetMethods() { return FtRoomGate.NchTargets(FtRoomGate.NchRoutine); }

        [HarmonyPrefix]
        [HarmonyPriority(Priority.First)]
        private static bool Prefix(MethodBase __originalMethod, NetworkConnectionHandler __instance, ref IEnumerator __result)
        {
            if (!FtConfig.Present) return true;
            try { if (__instance != null) __instance.untilTryOtherRegionCounter = float.MaxValue; } catch { }
            FtRoomGate.Admit("NCH." + __originalMethod.Name, null);
            __result = FtRoomGate.Empty();
            return false;
        }
    }

    /// <summary>F8 (ii): while a sitting runs, vanilla's try-another-region timer is frozen on every online join,
    /// whatever the room. One line per join (OnJoinedRoom fires once per join), never per frame.</summary>
    [HarmonyPatch(typeof(NetworkConnectionHandler), "OnJoinedRoom")]
    internal static class FtChurnFreezePatch
    {
        [HarmonyPostfix]
        [HarmonyPriority(Priority.Last)]
        private static void Postfix(NetworkConnectionHandler __instance)
        {
            if (!FtConfig.Present || __instance == null) return;
            try
            {
                __instance.untilTryOtherRegionCounter = float.MaxValue;
                string room = PhotonNetwork.CurrentRoom != null ? PhotonNetwork.CurrentRoom.Name : "(none)";
                Plugin.Log.LogInfo("[FRAME-TIME] churn timer frozen room=" + room);
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[FRAME-TIME] churn freeze failed: " + ex.Message); }
        }
    }
}
#endif
