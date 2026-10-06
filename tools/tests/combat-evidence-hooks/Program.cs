using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;

namespace CompetitiveRounds
{
    /// <summary>One case per combat evidence hook (every [HarmonyPatch] class
    /// the generator copied). With every collector throwing, each hook must:
    /// attach to the target the design names; carry exactly the prefix,
    /// postfix and finalizer methods named below; call its own collector once
    /// per invocation, forwarding exactly its own arguments in order (and the
    /// constants named below), run twice with every value changed; let no
    /// exception out; never skip the original (prefix and postfix return
    /// void); take no parameter by reference except Harmony's own out
    /// __state, which a faulting collector leaves at 0; and a finalizer
    /// returns exactly the exception it was given (a sentinel, then null).
    /// Usage: CombatHookTests [Class ...]; "--list" prints the classes.
    /// Exit 0 only when every case passes.</summary>
    internal static class HookProgram
    {
        private const BindingFlags All = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static;

        // class -> (target type, target method, "Kind:Collector:arg,arg|..."); "#n" is the constant n
        private static readonly Dictionary<string, Tuple<Type, string, string>> EXPECT = new Dictionary<string, Tuple<Type, string, string>>
        {
            { "CombatEvidence_AttackPatch", Tuple.Create(typeof(Gun), "Attack",
                "Prefix:AttackEnter:__instance,forceAttack,useAmmo|Postfix:AttackExit:__instance,__result,forceAttack,__state") },
            { "CombatEvidence_InitAmmoPatch", Tuple.Create(typeof(ProjectileInit), "RPCA_Init",
                "Prefix:InitEnter:__instance,senderID,#0|Finalizer:InitExit:__instance,__state") },
            { "CombatEvidence_InitNoAmmoPatch", Tuple.Create(typeof(ProjectileInit), "RPCA_Init_noAmmoUse", "Prefix:InitEnter:__instance,senderID,#1") },
            { "CombatEvidence_InitSeparatePatch", Tuple.Create(typeof(ProjectileInit), "RPCA_Init_SeparateGun", "Prefix:InitEnter:__instance,senderID,#2") },
            { "CombatEvidence_ReloadPatch", Tuple.Create(typeof(GunAmmo), "ReloadAmmo", "Prefix:ReloadEnter:__instance,playSound") },
            { "CombatEvidence_HitPatch", Tuple.Create(typeof(ProjectileHit), "RPCA_DoHit",
                "Prefix:HitEnter:__instance,hitPoint,vel,viewID,wasBlocked|Finalizer:HitExit:__instance,__state") },
            { "CombatEvidence_ContactPatch", Tuple.Create(typeof(ProjectileHit), "Hit", "Prefix:ContactEnter:__instance,hit") },
            { "CombatEvidence_BlockPatch", Tuple.Create(typeof(Block), "RPCA_DoBlock", "Finalizer:BlockDone:__instance") },
            { "CombatEvidence_TryBlockPatch", Tuple.Create(typeof(Block), "TryBlock", "Prefix:TryBlockEnter:__instance|Postfix:TryBlockExit:__instance,__state") },
            { "CombatEvidence_DealtPatch", Tuple.Create(typeof(CharacterStatModifiers), "DealtDamage", "Postfix:Dealt:__instance") },
            { "CombatEvidence_TargetBouncePatch", Tuple.Create(typeof(BounceEffectRetarget), "SetNewVel", "Prefix:TargetBounce:__instance,newVel") },
            { "CombatEvidence_EdgeBouncePatch", Tuple.Create(typeof(ScreenEdgeBounce), "DoHit",
                "Prefix:EdgeBounce:__instance|Finalizer:EdgeBounceExit:__instance,__state") },
            { "CombatEvidence_SyncPatch", Tuple.Create(typeof(Photon.Pun.SyncProjectile), "OnPhotonSerializeView", "Postfix:SyncRead:__instance,stream") },
            { "CombatEvidence_ForcePatch", Tuple.Create(typeof(HealthHandler), "RPCA_SendTakeForce",
                "Prefix:ForceEnter:__instance,force|Finalizer:ForceExit:__instance,__state") },
            { "CombatEvidence_DamagePatch", Tuple.Create(typeof(HealthHandler), "RPCA_SendTakeDamage",
                "Prefix:DamageEnter:__instance,damage,?1=damageSource|Finalizer:DamageExit:__instance,__state") },
            { "CombatEvidence_DiePatch", Tuple.Create(typeof(HealthHandler), "RPCA_Die", "Prefix:Die:__instance") },
            { "CombatEvidence_DiePhoenixPatch", Tuple.Create(typeof(HealthHandler), "RPCA_Die_Phoenix", "Prefix:Die:__instance") },
            { "CombatEvidence_FindTargetPatch", Tuple.Create(typeof(BounceEffectRetarget), "FindTarget", "Postfix:FindTarget:__instance,hit,__result") },
            { "CombatEvidence_MovePatch", Tuple.Create(typeof(MoveTransform), "Update",
                "Prefix:MoveEnter:__instance|Finalizer:MoveExit:__instance,__state") },
        };

        private static object Arg(ParameterInfo p, int pos, bool flag)
        {
            Type t = p.ParameterType.IsByRef ? p.ParameterType.GetElementType() : p.ParameterType;
            if (t == typeof(bool)) return pos % 2 == 0 ? flag : !flag;
            if (t == typeof(int)) return 11 + pos + (flag ? 0 : 100);
            if (t == typeof(long)) return 4242L + pos + (flag ? 0 : 1000);
            if (t == typeof(float)) return 0.5f + pos + (flag ? 0 : 7);
            if (t == typeof(UnityEngine.Vector2)) return new UnityEngine.Vector2(pos + 0.25f, flag ? 1.5f : -2.5f);
            if (t == typeof(Exception)) return null;
            if (t.IsEnum) return Enum.ToObject(t, (pos + (flag ? 0 : 1)) % 2);
            if (!t.IsAbstract && t.GetConstructor(Type.EmptyTypes) != null) return Activator.CreateInstance(t);
            return null;
        }

        private static List<MethodInfo> Marked(Type t, string attr)
        {
            return t.GetMethods(All).Where(m => m.GetCustomAttributes(false).Any(a => a.GetType().Name == attr)).ToList();
        }

        private static bool Same(object a, object b)
        {
            if (a == null || b == null) return a == null && b == null;
            return a.GetType().IsValueType ? a.Equals(b) : ReferenceEquals(a, b);
        }

        private static void Invoke(string kind, MethodInfo m, string collector, string[] fwd)
        {
            var ps = m.GetParameters();
            foreach (var p in ps)
            {
                bool harmonyState = p.Name == "__state" && p.IsOut && kind == "Prefix";
                if (p.ParameterType.IsByRef && !harmonyState) throw new Exception(kind + " parameter " + p.Name + " is by reference (the hook could write it)");
                if (p.Name == "__runOriginal") throw new Exception(kind + " reads __runOriginal (not named by the design)");
            }
            if (kind == "Finalizer")
            {
                if (m.ReturnType != typeof(Exception)) throw new Exception("the finalizer does not return the exception");
            }
            else if (m.ReturnType != typeof(void)) throw new Exception(kind + " returns a value (a prefix could skip the original)");
            foreach (bool flag in new[] { true, false })
            {
                foreach (bool threw in kind == "Finalizer" ? new[] { true, false } : new[] { false })
                {
                    var a = new object[ps.Length];
                    for (int i = 0; i < ps.Length; i++) a[i] = Arg(ps[i], i, flag);
                    var sentinel = new InvalidCastException("the original threw");
                    for (int i = 0; i < ps.Length; i++) if (ps[i].Name == "__exception") a[i] = threw ? sentinel : null;
                    int before = Planted.Calls;
                    Planted.Collector = null; Planted.Args = null;
                    object back = m.Invoke(null, a);   // a TargetInvocationException here is a fault that escaped
                    if (kind == "Finalizer" && !ReferenceEquals(back, threw ? sentinel : null))
                        throw new Exception("the finalizer did not return the original's exception unchanged");
                    if (Planted.Calls != before + 1) throw new Exception(kind + ": the collector was called " + (Planted.Calls - before) + " times");
                    if (Planted.Collector != collector) throw new Exception(kind + " called " + Planted.Collector + ", not " + collector);
                    if (Planted.Args.Length != fwd.Length) throw new Exception(kind + " forwarded " + Planted.Args.Length + " arguments, want " + fwd.Length);
                    for (int k = 0; k < fwd.Length; k++)
                    {
                        object want;
                        if (fwd[k].StartsWith("#")) want = int.Parse(fwd[k].Substring(1));
                        else if (fwd[k].StartsWith("?"))
                        {
                            // "?n=param": the hook forwards (param == n) as a bool ('=' because ':' separates the spec)
                            var sp = fwd[k].Substring(1).Split(new[] { '=' }, 2);
                            int i = Array.FindIndex(ps, p => p.Name == sp[1]);
                            if (i < 0) throw new Exception(kind + " has no parameter " + sp[1]);
                            want = Convert.ToInt32(a[i]) == int.Parse(sp[0]);
                        }
                        else
                        {
                            int i = Array.FindIndex(ps, p => p.Name == fwd[k]);
                            if (i < 0) throw new Exception(kind + " has no parameter " + fwd[k]);
                            want = a[i];
                        }
                        if (!Same(want, Planted.Args[k])) throw new Exception(kind + ": argument " + k + " (" + fwd[k] + ") not forwarded in place");
                    }
                    for (int i = 0; i < ps.Length; i++)
                        if (ps[i].Name == "__state" && ps[i].IsOut && !(Convert.ToInt64(a[i]) == 0))
                            throw new Exception("a faulting collector left __state at " + a[i] + ", not 0");
                }
            }
        }

        private static void Case(Type t)
        {
            Tuple<Type, string, string> want;
            if (!EXPECT.TryGetValue(t.Name, out want)) throw new Exception("no expectation for this hook class");
            var patch = t.GetCustomAttributes(false).OfType<HarmonyLib.HarmonyPatch>().ToList();
            if (patch.Count != 1 || patch[0].Target != want.Item1 || patch[0].Method != want.Item2)
                throw new Exception("patch target is not " + want.Item1.Name + "." + want.Item2);
            if (t.GetCustomAttributes(false).OfType<HarmonyLib.HarmonyPriority>().Any()) throw new Exception("unexpected priority");
            var plan = want.Item3.Split('|').Select(s => s.Split(':')).ToList();
            foreach (var kind in new[] { "Prefix", "Postfix", "Finalizer" })
            {
                var ms = Marked(t, "Harmony" + kind);
                var spec = plan.Where(p => p[0] == kind).ToList();
                if (ms.Count != spec.Count) throw new Exception("expected " + spec.Count + " " + kind + ", found " + ms.Count);
                if (spec.Count == 1) Invoke(kind, ms[0], spec[0][1], spec[0][2].Split(','));
            }
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
