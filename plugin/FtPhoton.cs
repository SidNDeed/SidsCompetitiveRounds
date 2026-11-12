#if SCR_FRAMETIME
using System;
using System.Collections.Generic;
using System.Reflection;
using HarmonyLib;

namespace CompetitiveRounds
{
    /// <summary>Class X (B11 SHARED.md, "V6: the direct bound"; rulings R6-A3.11.146 and .147): Photon's own main-thread
    /// work, charged whole for all traffic. A class-X scope wraps each main-thread entry of
    /// ExitGames.Client.Photon.PhotonPeer that moves messages, the four of Photon3Unity3D 4.1.7.0 (confirmed against the
    /// shipped assembly: instance methods with no parameters, Service returning void and the other three bool, none
    /// overridden by Photon.Realtime.LoadBalancingPeer). Inside them, each listener callback of
    /// Photon.Realtime.LoadBalancingClient opens a class-E scope: the four IPhotonPeerListener methods it implements,
    /// OnMessage(object) and OnDisconnectMessageReceived(DisconnectMessage), the handler it registers for the peer's
    /// disconnect messages. A game handler then runs in E, and a collector handler opens its own class inside it (P for
    /// the recv scopes, S or R for a component scope). Every prefix runs first and every finalizer last, so the scope
    /// holds every other patch on the same target. Off the main thread nothing moves (FtSpan.PhotonOffMain).
    /// A missing target throws in TargetMethods, which the patch loop logs as "Failed to patch"; ReportPatched prints
    /// the boot line `[FRAME-TIME] photon patches n= names=` from Harmony's own patch table. PlantNest is K3.</summary>
    internal static class FtPhoton
    {
        internal static readonly string[] XNames = { "DispatchIncomingCommands", "SendOutgoingCommands", "SendAcksOnly", "Service" };

        /// <summary>The listener callbacks and their exact parameter lists.</summary>
        internal static readonly KeyValuePair<string, Type[]>[] ENames =
        {
            new KeyValuePair<string, Type[]>("OnOperationResponse", new[] { typeof(ExitGames.Client.Photon.OperationResponse) }),
            new KeyValuePair<string, Type[]>("OnEvent", new[] { typeof(ExitGames.Client.Photon.EventData) }),
            new KeyValuePair<string, Type[]>("OnStatusChanged", new[] { typeof(ExitGames.Client.Photon.StatusCode) }),
            new KeyValuePair<string, Type[]>("DebugReturn", new[] { typeof(ExitGames.Client.Photon.DebugLevel), typeof(string) }),
            new KeyValuePair<string, Type[]>("OnMessage", new[] { typeof(object) }),
            new KeyValuePair<string, Type[]>("OnDisconnectMessageReceived", new[] { typeof(ExitGames.Client.Photon.DisconnectMessage) }),
        };

        internal static IEnumerable<MethodBase> XTargets()
        {
            var list = new List<MethodBase>();
            foreach (string n in XNames)
            {
                var m = AccessTools.Method(typeof(ExitGames.Client.Photon.PhotonPeer), n, Type.EmptyTypes);
                if (m == null || m.DeclaringType != typeof(ExitGames.Client.Photon.PhotonPeer))
                    throw new Exception("PhotonPeer." + n + "() not found - no class X scope");
                list.Add(m);
            }
            return list;
        }

        internal static IEnumerable<MethodBase> ETargets()
        {
            var list = new List<MethodBase>();
            foreach (var kv in ENames)
            {
                var m = AccessTools.Method(typeof(Photon.Realtime.LoadBalancingClient), kv.Key, kv.Value);
                if (m == null || m.DeclaringType != typeof(Photon.Realtime.LoadBalancingClient))
                    throw new Exception("LoadBalancingClient." + kv.Key + " not found - no class E scope");
                list.Add(m);
            }
            return list;
        }

        /// <summary>Plugin.Awake, after its patch loop: the targets whose patch table lists both of the scope's own
        /// methods (same module, same metadata token), as `[FRAME-TIME] photon patches n=<count> names=<T.m,...>`.</summary>
        internal static void ReportPatched()
        {
            var names = new List<string>();
            Count(names, XTargets, typeof(FtPhotonXPatch));
            Count(names, ETargets, typeof(FtPhotonEPatch));
            Plugin.Log.LogInfo("[FRAME-TIME] photon patches n=" + names.Count + " names=" + string.Join(",", names.ToArray()));
        }

        private static void Count(List<string> names, Func<IEnumerable<MethodBase>> targets, Type patch)
        {
            MethodInfo pre = AccessTools.Method(patch, "Prefix"), fin = AccessTools.Method(patch, "Finalizer");
            IEnumerable<MethodBase> ms;
            try { ms = targets(); }
            catch { return; }
            foreach (var m in ms)
            {
                bool p = false, f = false;
                try
                {
                    var info = Harmony.GetPatchInfo(m);
                    if (info != null)
                    {
                        foreach (var x in info.Prefixes) if (Same(x.PatchMethod, pre)) p = true;
                        foreach (var x in info.Finalizers) if (Same(x.PatchMethod, fin)) f = true;
                    }
                }
                catch { }
                if (p && f) names.Add(m.DeclaringType.Name + "." + m.Name);
            }
        }

        private static bool Same(MethodInfo a, MethodInfo b)
        {
            return a != null && b != null && a.Module == b.Module && a.MetadataToken == b.MetadataToken;
        }

        /// <summary>K3, the boot line `[FRAME-TIME] nest plant asked=<us> x=<us> e=<us> p=<us>`: X around E around P, each
        /// opened by the code its patch or site runs (FtSpan.EnterX, FtSpan.EnterListener, FtLedger.RecvEnter), with one
        /// spin of FtSpan.PlantUs in each before the next opens; each class's gain in microseconds at f_hat. E's base is
        /// read after X opens, so the cycles before the plant (which fall to E) are not E's reading. The class state is
        /// restored after. FtClock.OnStart, at the first frame boundary.</summary>
        internal static void PlantNest()
        {
            var st = FtSpan.Save();
            long x0 = FtSpan.Acc[FtSpan.ClsX], p0 = FtSpan.Acc[FtSpan.ClsP];
            int dx = FtSpan.EnterX();
            long e0 = FtSpan.Acc[FtSpan.ClsE];
            FtSpan.Spin(FtSpan.PlantUs);
            int de = FtSpan.EnterListener();
            FtSpan.Spin(FtSpan.PlantUs);
            ulong k = FtLedger.RecvEnter();
            FtSpan.Spin(FtSpan.PlantUs);
            FtLedger.RecvExit(k);
            FtSpan.Leave(de);
            FtSpan.Leave(dx);
            long x = FtSpan.Acc[FtSpan.ClsX] - x0, e = FtSpan.Acc[FtSpan.ClsE] - e0, p = FtSpan.Acc[FtSpan.ClsP] - p0;
            FtSpan.Restore(st);
            Plugin.Log.LogInfo("[FRAME-TIME] nest plant asked=" + FtSpan.PlantUs + " x=" + FtSpan.Us(x) + " e=" + FtSpan.Us(e)
                + " p=" + FtSpan.Us(p));
        }
    }

    /// <summary>Class X: the four PhotonPeer entries (FtPhoton).</summary>
    [HarmonyPatch]
    internal static class FtPhotonXPatch
    {
        private static IEnumerable<MethodBase> TargetMethods()
        {
            return FtPhoton.XTargets();
        }

        [HarmonyPrefix]
        [HarmonyPriority(Priority.First)]
        private static void Prefix(out int __state)
        {
            __state = FtSpan.EnterX();
        }

        [HarmonyFinalizer]
        [HarmonyPriority(Priority.Last)]
        private static void Finalizer(int __state)
        {
            FtSpan.Leave(__state);
        }
    }

    /// <summary>Class E: the LoadBalancingClient listener callbacks (FtPhoton).</summary>
    [HarmonyPatch]
    internal static class FtPhotonEPatch
    {
        private static IEnumerable<MethodBase> TargetMethods()
        {
            return FtPhoton.ETargets();
        }

        [HarmonyPrefix]
        [HarmonyPriority(Priority.First)]
        private static void Prefix(out int __state)
        {
            __state = FtSpan.EnterListener();
        }

        [HarmonyFinalizer]
        [HarmonyPriority(Priority.Last)]
        private static void Finalizer(int __state)
        {
            FtSpan.Leave(__state);
        }
    }
}
#endif
