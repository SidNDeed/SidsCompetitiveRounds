using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;

namespace CompetitiveRounds
{
    /// <summary>One case per evidence hook (every [HarmonyPatch] class the
    /// generator copied). With every collector throwing, each hook must:
    /// call at least one collector (or the case proves nothing), let no
    /// exception out of any prefix, postfix or finalizer, never skip the
    /// original (prefixes return void), and return exactly the exception its
    /// finalizer was given (a sentinel, then null). The ExecuteRpc hook must
    /// also restore the previous RPC sender. Usage: HookTests [Class ...];
    /// "--list" prints the classes. Exit 0 only when every case passes.</summary>
    internal static class HookProgram
    {
        private const BindingFlags All = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static;

        private static object Arg(ParameterInfo p, Dictionary<string, object> state)
        {
            Type t = p.ParameterType.IsByRef ? p.ParameterType.GetElementType() : p.ParameterType;
            if (p.Name == "__state" && state.ContainsKey("__state")) return state["__state"];
            if (t == typeof(Photon.Realtime.Player)) return new Photon.Realtime.Player { ActorNumber = 9 };
            if (t == typeof(string)) return "RPCAO_DoBlock";
            if (t == typeof(Photon.Pun.RpcTarget)) return Photon.Pun.RpcTarget.Others;
            if (t.IsValueType) return Activator.CreateInstance(t);
            if (t == typeof(Exception)) return null;
            if (!t.IsAbstract && t.GetConstructor(Type.EmptyTypes) != null) return Activator.CreateInstance(t);
            return null;
        }

        private static object[] Args(MethodInfo m, Dictionary<string, object> state, Exception given)
        {
            var ps = m.GetParameters();
            var a = new object[ps.Length];
            for (int i = 0; i < ps.Length; i++) a[i] = ps[i].Name == "__exception" ? given : Arg(ps[i], state);
            return a;
        }

        private static List<MethodInfo> Marked(Type t, string attr)
        {
            return t.GetMethods(All).Where(m => m.GetCustomAttributes(false).Any(a => a.GetType().Name == attr)).ToList();
        }

        private static void Case(Type t)
        {
            var tm = t.GetMethod("TargetMethod", All);
            if (tm != null && tm.Invoke(null, null) == null) throw new Exception("TargetMethod returned null");
            var pre = Marked(t, "HarmonyPrefix");
            var post = Marked(t, "HarmonyPostfix");
            var fin = Marked(t, "HarmonyFinalizer");
            if (pre.Count + post.Count + fin.Count == 0) throw new Exception("no hook methods");
            bool rpcHook = t.Name == "HitEvidence_ExecuteRpcPatch";
            if (rpcHook) HitEvidence.RpcSender = 7;
            int before = Planted.Calls;
            var state = new Dictionary<string, object>();
            foreach (var m in pre)
            {
                if (m.ReturnType != typeof(void)) throw new Exception("prefix " + m.Name + " can skip the original");
                var a = Args(m, state, null);
                m.Invoke(null, a);   // a TargetInvocationException here is a fault that escaped
                var ps = m.GetParameters();
                for (int i = 0; i < ps.Length; i++) if (ps[i].Name == "__state") state["__state"] = a[i];
            }
            if (rpcHook && HitEvidence.RpcSender != 9) throw new Exception("the prefix did not record the sender");
            foreach (var m in post) m.Invoke(null, Args(m, state, null));
            var sentinel = new InvalidOperationException("the original's own exception");
            foreach (var m in fin)
            {
                if (m.ReturnType != typeof(Exception)) throw new Exception("finalizer " + m.Name + " does not return the exception");
                object r = m.Invoke(null, Args(m, state, sentinel));
                if (!ReferenceEquals(r, sentinel)) throw new Exception("finalizer " + m.Name + " changed the original's exception");
                object r2 = m.Invoke(null, Args(m, state, null));
                if (r2 != null) throw new Exception("finalizer " + m.Name + " invented an exception");
            }
            if (rpcHook && HitEvidence.RpcSender != 7) throw new Exception("the finalizer did not restore the previous sender");
            if (Planted.Calls == before) throw new Exception("no collector was called: the case proves nothing");
        }

        private static int Main(string[] args)
        {
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
