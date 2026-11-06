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
    /// counted from Harmony's own patch table: a target counts only when that table lists the gate's own prefix
    /// method for it, by identity (R6-A3.11.1 (4)). The timer half (ii) is FtChurnFreezePatch below. Leaves are not
    /// gated (R6-A3.11.2): a leave enters no room, and every entry after one is refused here by name.</summary>
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
            // Each target is paired with the ONE prefix method that must guard it, and it counts only when Harmony's
            // patch table lists that very method (same module, same metadata token) among its prefixes. Any other
            // prefix on the same target (VanillaFixes, the quickplay guards, all owned by this plugin's id) does
            // not count (ruling R6-A3.11.1 (4)).
            var missing = new List<string>();
            var entry = new List<KeyValuePair<MethodBase, MethodInfo>>();
            List<string> excluded = new List<string>();
            MethodInfo punPre = PrefixOf(typeof(FtRoomGatePunPatch)), voidPre = PrefixOf(typeof(FtRoomGateNchVoidPatch)),
                routinePre = PrefixOf(typeof(FtRoomGateNchRoutinePatch));
            try { foreach (var m in SweepPun(out excluded)) entry.Add(new KeyValuePair<MethodBase, MethodInfo>(m, punPre)); }
            catch (Exception ex) { missing.Add("sweep: " + ex.Message); }
            foreach (var n in NchVoid) AddNamed(entry, n, voidPre, missing);
            foreach (var n in NchRoutine) AddNamed(entry, n, routinePre, missing);
            int patched = CountGuarded(entry, missing);
            Plugin.Log.LogInfo("[FRAME-TIME] FT-GATE patched " + patched + " entry points expected=" + entry.Count
                + " excluded=" + string.Join(",", excluded.ToArray())
                + (missing.Count == 0 ? "" : " missing=" + string.Join(",", missing.ToArray())));
        }

        private static MethodInfo PrefixOf(Type t)
        {
            return t.GetMethod("Prefix", BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.DeclaredOnly);
        }

        private static void AddNamed(List<KeyValuePair<MethodBase, MethodInfo>> list, string n, MethodInfo pre, List<string> missing)
        {
            var m = AccessTools.Method(typeof(NetworkConnectionHandler), n);
            if (m == null) missing.Add("NCH." + n + " (absent)"); else list.Add(new KeyValuePair<MethodBase, MethodInfo>(m, pre));
        }

        private static int CountGuarded(List<KeyValuePair<MethodBase, MethodInfo>> list, List<string> missing)
        {
            int n = 0;
            foreach (var kv in list)
            {
                bool ours = false;
                try
                {
                    MethodInfo want = kv.Value;
                    var info = want != null ? Harmony.GetPatchInfo(kv.Key) : null;
                    if (info != null)
                        foreach (var p in info.Prefixes)
                            if (p.PatchMethod != null && p.PatchMethod.Module == want.Module
                                && p.PatchMethod.MetadataToken == want.MetadataToken)
                            { ours = true; break; }
                }
                catch { }
                if (ours) n++; else missing.Add(kv.Key.DeclaringType.Name + "." + kv.Key.Name);
            }
            return n;
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
            // Finding 12 (F8 read r1): the name is the argument whose PARAMETER is named roomName, wherever it sits
            // (JoinRandomOrCreateRoom carries a Hashtable first and its roomName later); an operation with no such
            // parameter carries no name. The name only reaches the refusal line for the NoName operations.
            string name = null;
            if (__args != null)
            {
                ParameterInfo[] ps = __originalMethod.GetParameters();
                for (int i = 0; i < ps.Length && i < __args.Length; i++)
                    if (string.Equals(ps[i].Name, "roomName", StringComparison.Ordinal)) { name = __args[i] as string; break; }
            }
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

    /// <summary>F8 bar B10 (rulings R6-A3.11.19 Q3, R6-A3.11.20 (2)): the occupancy sample's time. The count is the
    /// argument, evaluated first; the wall-clock time is read in the same call, so the [NET] line's ft_utc is the
    /// moment its actor count was read, not the moment the line was written.</summary>
    internal static class FtSampleClock
    {
        internal static int Count(int playerCount, out DateTime utc)
        {
            utc = DateTime.UtcNow;
            return playerCount;
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
            // Finding 8 (F8 read r1): the room identity line. One per join, the name read from
            // PhotonNetwork.CurrentRoom.Name (never the ROOM_CODE property vanilla prints) and running to the end of
            // the line, so a reader compares the WHOLE name. offline=1 marks an offline room, for which vanilla
            // prints no Unity "Joined room:" line; the bar compares the offline=0 count with the Unity count.
            try
            {
                var cur = PhotonNetwork.CurrentRoom;
                Plugin.Log.LogInfo("[FRAME-TIME] FT-ROOM joined offline=" + (PhotonNetwork.OfflineMode ? "1" : "0")
                    + " name=" + (cur != null ? cur.Name : "(none)"));
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[FRAME-TIME] FT-ROOM read failed: " + ex.Message); }
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
