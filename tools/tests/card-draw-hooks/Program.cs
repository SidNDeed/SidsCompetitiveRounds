using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;

namespace CompetitiveRounds
{
    /// <summary>One case per card draw evidence hook (every [HarmonyPatch]
    /// class the generator copied). With every collector throwing, each hook
    /// must: call its own collector, forward exactly its own arguments in
    /// order (run twice, the bool flipped), let no exception out, never skip
    /// the original (prefixes return void) and never write __runOriginal
    /// (by value only), and carry the priority the design names. Case
    /// "testgate-off" / "testgate-on" prints and checks the test gate.
    /// Usage: CardDrawHookTests [Class ...]. Exit 0 only when every case passes.</summary>
    internal static class HookProgram
    {
        private const BindingFlags All = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static;

        // class -> (collector, priority Last required, target type, target method)
        private static readonly Dictionary<string, Tuple<string, bool, Type, string>> EXPECT = new Dictionary<string, Tuple<string, bool, Type, string>>
        {
            { "CardDrawEvidence_StartPickPatch", Tuple.Create("PhaseStarted", true, typeof(CardChoice), "StartPick") },
            { "CardDrawEvidence_CardAwakePatch", Tuple.Create("CardAwake", false, typeof(CardInfo), "Awake") },
            { "CardDrawEvidence_EndPickPatch", Tuple.Create("EndPick", false, typeof(CardChoice), "RPCA_DoEndPick") },
            { "CardDrawEvidence_DonePickingPatch", Tuple.Create("DonePicking", false, typeof(CardChoice), "RPCA_DonePicking") },
            { "CardDrawEvidence_PickPatch", Tuple.Create("PickApplied", true, typeof(ApplyCardStats), "RPCA_Pick") },
            { "CardDrawEvidence_OfflinePickPatch", Tuple.Create("OfflinePickApplied", true, typeof(ApplyCardStats), "OFFLINE_Pick") },
        };

        private static object Arg(ParameterInfo p, int pos, bool flag)
        {
            Type t = p.ParameterType.IsByRef ? p.ParameterType.GetElementType() : p.ParameterType;
            if (t == typeof(bool)) return flag;
            if (t == typeof(int)) return 11 + pos + (flag ? 0 : 100);
            if (t == typeof(int[])) return new[] { 101, 102, pos };
            if (t == typeof(Player[])) return new[] { new Player(), new Player() };
            if (!t.IsAbstract && t.GetConstructor(Type.EmptyTypes) != null) return Activator.CreateInstance(t);
            return null;
        }

        private static List<MethodInfo> Marked(Type t, string attr)
        {
            return t.GetMethods(All).Where(m => m.GetCustomAttributes(false).Any(a => a.GetType().Name == attr)).ToList();
        }

        private static void Case(Type t)
        {
            Tuple<string, bool, Type, string> want;
            if (!EXPECT.TryGetValue(t.Name, out want)) throw new Exception("no expectation for this hook class");
            var patch = t.GetCustomAttributes(false).OfType<HarmonyLib.HarmonyPatch>().ToList();
            if (patch.Count != 1 || patch[0].Target != want.Item3 || patch[0].Method != want.Item4)
                throw new Exception("patch target is not " + want.Item3.Name + "." + want.Item4);
            var prio = t.GetCustomAttributes(false).OfType<HarmonyLib.HarmonyPriority>().ToList();
            if (want.Item2 && (prio.Count != 1 || prio[0].Value != HarmonyLib.Priority.Last)) throw new Exception("priority Last missing");
            if (!want.Item2 && prio.Count != 0) throw new Exception("unexpected priority");
            var pre = Marked(t, "HarmonyPrefix");
            var post = Marked(t, "HarmonyPostfix");
            var fin = Marked(t, "HarmonyFinalizer");
            if (pre.Count + post.Count != 1 || fin.Count != 0) throw new Exception("expected exactly one prefix or postfix and no finalizer");
            var m = pre.Count == 1 ? pre[0] : post[0];
            if (m.ReturnType != typeof(void)) throw new Exception(m.Name + " returns a value (a prefix could skip the original)");
            foreach (var p in m.GetParameters())
            {
                if (p.ParameterType.IsByRef) throw new Exception("parameter " + p.Name + " is by reference (the hook could write it)");
                if (p.Name == "__result" || p.Name == "__state") throw new Exception("parameter " + p.Name + " is not a reading of the call");
            }
            foreach (bool flag in new[] { true, false })
            {
                var ps = m.GetParameters();
                var a = new object[ps.Length];
                for (int i = 0; i < ps.Length; i++) a[i] = Arg(ps[i], i, flag);
                int before = Planted.Calls;
                Planted.Collector = null; Planted.Args = null;
                m.Invoke(null, a);   // a TargetInvocationException here is a fault that escaped
                if (Planted.Calls != before + 1) throw new Exception("the collector was called " + (Planted.Calls - before) + " times");
                if (Planted.Collector != want.Item1) throw new Exception("called " + Planted.Collector + ", not " + want.Item1);
                if (Planted.Args.Length != a.Length) throw new Exception("forwarded " + Planted.Args.Length + " arguments of " + a.Length);
                for (int i = 0; i < a.Length; i++)
                {
                    bool same = a[i] != null && a[i].GetType().IsValueType ? a[i].Equals(Planted.Args[i]) : ReferenceEquals(a[i], Planted.Args[i]);
                    if (!same) throw new Exception("argument " + i + " (" + ps[i].Name + ") not forwarded in place");
                }
            }
        }

        private static int Main(string[] args)
        {
            if (args.Length == 1 && (args[0] == "testgate-off" || args[0] == "testgate-on"))
            {
                bool on = CardDrawEvidenceTestGate.On;
                Console.WriteLine("test gate On=" + on + " Marker=" + CardDrawEvidenceTestGate.Marker);
                return on == (args[0] == "testgate-on") ? 0 : 1;
            }
            var hooks = typeof(HookProgram).Assembly.GetTypes()
                .Where(t => t.Namespace == "CompetitiveRounds" && t.GetCustomAttributes(false).Any(a => a.GetType().Name == "HarmonyPatch"))
                .OrderBy(t => t.Name, StringComparer.Ordinal).ToList();
            if (args.Length == 1 && args[0] == "--list") { foreach (var h in hooks) Console.WriteLine(h.Name); return 0; }
            var run = args.Length == 0 ? hooks : hooks.Where(h => args.Contains(h.Name)).ToList();
            if (args.Length > 0 && run.Count != args.Length) { Console.WriteLine("UNKNOWN case in " + string.Join(",", args)); return 2; }
            int failed = 0;
            foreach (var t in run)
            {
                try { Case(t); Console.WriteLine("PASS " + t.Name); }
                catch (Exception ex)
                {
                    var e = ex is TargetInvocationException && ex.InnerException != null ? ex.InnerException : ex;
                    Console.WriteLine("FAIL " + t.Name + ": " + e.GetType().Name + " " + e.Message);
                    failed++;
                }
            }
            Console.WriteLine("hooks: " + run.Count + (failed == 0 ? ", ALL PASS" : ", " + failed + " FAILED"));
            return failed == 0 ? 0 : 1;
        }
    }
}
