#if SCR_FRAMETIME
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Reflection;
using System.Reflection.Emit;
using System.Runtime.CompilerServices;
using System.Text;
using HarmonyLib;

namespace CompetitiveRounds
{
    /// <summary>FrameTime M6 and M8 (METHOD-V4.md 3.1, 3.6). Calibration runs at process
    /// start and at every game start, outside live combat; every value is logged as an
    /// integer (ticks or cycles), converted once in analysis.
    /// (a) f_hat: the largest of five cycles-per-second ratios over 50 ms spins
    ///     (preemption lowers a ratio, never raises it).
    /// (b) Dispatch, one run PER PATCHED ENTRY (round-1 MEDIUM, FtCalib.cs:163: one dummy shape
    ///     cannot stand for targets whose argument lists, return types and patch sets differ).
    ///     For each census entry that is a Harmony patch, the calibration builds a dummy with the
    ///     real target's exact signature (static or instance, every parameter type and name, the
    ///     return type) in a dynamic assembly, and patches it, under this calibration's own Harmony
    ///     id, with that entry's REAL patch methods (its patch class, FtE.PatchType, generated from
    ///     the source by gen_entries.py; the class's target is read back from Harmony's own patch
    ///     table). 20 batches of 25,000 calls unpatched, then the same patched, with the gate set,
    ///     so every patch body runs the closed path a gated entry runs at an OFF point and the
    ///     difference is what the OFF arm cannot remove for that entry. The census counter the
    ///     closed path increments is restored afterwards. The line's shape is the entry's census
    ///     id, and the census maps every patched entry to itself, so D_up prices each entry with
    ///     its own run (V4 3.6). A direct-call entry uses "call": a call whose body opens with the
    ///     census check, against the empty loop. The entry table is built only after Plugin.Awake
    ///     signals, right after its own Harmony patch loop, that this plugin's patches are applied
    ///     (OwnPatchesApplied; ruling FRAME-TIME-ROUND-R6-A1); the process-start run sits before that
    ///     loop, so it logs that the table is not built yet and makes no entry run. VR2 requires
    ///     every entry's run at every game start, so a failed entry run (logged) fails VR2.
    /// (c) The span's own cost: an outermost span around an empty body (x++), against the
    ///     body alone, in the calibration's own span slot (FtSpan.Cal).
    /// The settled line (M8) is written once per game and once at process start.</summary>
    internal static class FtCalib
    {
        private const int Batches = 20;
        private const int Calls = 100000;
        private const int EntryCalls = 25000;
        private const int Spins = 5;
        internal const string HarmonyId = "competitiverounds.frametime.calibration";

        internal static long FHat;
        private static int _runs;
        private static int _sink;

        internal static class Dummy
        {
            [MethodImpl(MethodImplOptions.NoInlining)]
            internal static void CallGated()
            {
                if (FtCensus.Skip(CalEntry)) return;
                _sink++;
            }
        }

        /// <summary>The census slot the direct-call closed path counts in: never registered, so no census
        /// line and no sum includes it.</summary>
        internal const int CalEntry = 255;

        /// <summary>A loop shape that needs no patch: "call" and the span's own cost.</summary>
        private struct Shape
        {
            internal string Name;
            internal int Loop;
            internal int Baseline;
        }

        private static readonly Shape[] Shapes =
        {
            new Shape { Name = "call", Loop = 15, Baseline = 6 },
            new Shape { Name = "span.empty", Loop = 5, Baseline = 6 },
        };

        /// <summary>One patched entry's calibration: the dummy with the target's signature, its call loop,
        /// and the entry's own patch methods.</summary>
        private sealed class EntryCal
        {
            internal int Entry;
            internal string Name;
            internal MethodInfo Dummy;
            internal Action<int> Loop;
            internal HarmonyMethod Pre, Post, Fin;
            internal string Error;
        }

        private static EntryCal[] _cals;
        private static ModuleBuilder _module;
        private static readonly EntryCal[] NotBuilt = new EntryCal[0];

        /// <summary>The positive signal that this plugin's own Harmony patches exist: set only by
        /// OwnPatchesApplied, which Plugin.Awake calls right after its patch loop logs "[HARMONY] Patches
        /// applied" (ruling FRAME-TIME-ROUND-R6-A1). Another mod's patches never set it.</summary>
        private static volatile bool _ownPatchesApplied;

        /// <summary>Called once by Plugin.Awake after its own patch loop: sets the signal, then builds the entry
        /// table at once, so the startup log carries its counts line (own-owner targets, entries, errors).</summary>
        internal static void OwnPatchesApplied()
        {
            _ownPatchesApplied = true;
#if SCR_FT_NOCOLLECTORS
            // FrameTimeRef: no collector patch is installed, so no entry is calibrated
            Plugin.Log.LogInfo("[FRAME-TIME] cal i=-1 why=patches kind=entries reference=1 built=0");
            return;
#else
            try { Cals(); }
            catch (Exception ex) { Plugin.Log.LogWarning("[FRAME-TIME] cal i=-1 why=patches kind=entries failed: " + ex.GetType().Name + ": " + ex.Message); }
#endif
        }

        /// <summary>One calibration run; why names the moment (start, or game g).</summary>
        internal static void Run(string why)
        {
            int i = _runs++;
            try { RunFHat(i, why); }
            catch (Exception ex) { Plugin.Log.LogWarning("[FRAME-TIME] cal i=" + i + " kind=fhat failed: " + ex.Message); }
            try { RunDispatch(i, why); }
            catch (Exception ex) { Plugin.Log.LogWarning("[FRAME-TIME] cal i=" + i + " kind=disp failed: " + ex.Message); }
            try { FtA3.Calibrate(i, why); }
            catch (Exception ex) { Plugin.Log.LogWarning("[FRAME-TIME] cal i=" + i + " kind=a3 failed: " + ex.Message); }
            try { RunEntries(i, why); }
            catch (Exception ex) { Plugin.Log.LogWarning("[FRAME-TIME] cal i=" + i + " kind=disp entries failed: " + ex.Message); }
        }

        private static void RunFHat(int i, string why)
        {
            long freq = Stopwatch.Frequency;
            long spin = freq / 20;
            long best = 0;
            var sb = new StringBuilder();
            for (int n = 0; n < Spins; n++)
            {
                ulong k0 = FtClock.Cycles();
                long t0 = Stopwatch.GetTimestamp();
                long t1;
                do { t1 = Stopwatch.GetTimestamp(); } while (t1 - t0 < spin);
                ulong k1 = FtClock.Cycles();
                ulong dk = k1 - k0;
                long dt = t1 - t0;
                long r = (long)(dk * (ulong)freq / (ulong)dt);
                if (r > best) best = r;
                sb.Append(n == 0 ? "" : ",").Append(dk).Append('/').Append(dt);
            }
            FHat = best;
            Plugin.Log.LogInfo("[FRAME-TIME] cal i=" + i + " why=" + why + " kind=fhat f_hat=" + best + " spins=" + sb);
        }

        private static long Loop(int loop, int n)
        {
            int x = 0;
            long t0 = Stopwatch.GetTimestamp();
            switch (loop)
            {
                case 5: for (int j = 0; j < n; j++) { bool sp = FtSpan.Open(FtSpan.Cal, FtSpan.Gated); x++; FtSpan.Close(sp); } break;
                case 6: for (int j = 0; j < n; j++) { x++; } break;
                case 15: for (int j = 0; j < n; j++) { Dummy.CallGated(); x++; } break;
            }
            long t = Stopwatch.GetTimestamp() - t0;
            _sink += x;
            return t;
        }

        private static void RunDispatch(int i, string why)
        {
            foreach (Shape s in Shapes)
            {
                var u = new long[Batches];
                var p = new long[Batches];
                Loop(s.Baseline, 1000);
                for (int b = 0; b < Batches; b++) u[b] = Loop(s.Baseline, Calls);
                // The closed path needs the gate set: a write of FtGate.Off outside FtSchedule.Boundary, inside
                // this calibration, with nothing else running on the main thread, restored after; the census
                // counter it increments is restored too.
                bool gate = FtGate.Off;
                long guarded = FtCensus.Guarded[CalEntry];
                bool span = s.Name.StartsWith("span.");
                if (!span) FtGate.Off = true;
                try
                {
                    Loop(s.Loop, 1000);
                    for (int b = 0; b < Batches; b++) p[b] = Loop(s.Loop, Calls);
                }
                finally
                {
                    FtGate.Off = gate;
                    FtCensus.Guarded[CalEntry] = guarded;
                }
                Plugin.Log.LogInfo("[FRAME-TIME] cal i=" + i + " why=" + why + " kind=" + (span ? "span" : "disp") + " shape=" + s.Name + " n=" + Calls
                    + " u=" + string.Join(",", u) + " p=" + string.Join(",", p));
            }
        }

        private static long Time(Action<int> loop, int n)
        {
            long t0 = Stopwatch.GetTimestamp();
            loop(n);
            return Stopwatch.GetTimestamp() - t0;
        }

        private static void RunEntries(int i, string why)
        {
#if SCR_FT_NOCOLLECTORS
            Plugin.Log.LogInfo("[FRAME-TIME] cal i=" + i + " why=" + why + " kind=entries reference=1 built=0");
            return;
#else
            EntryCal[] cals = Cals();
            if (!_ownPatchesApplied)
            {
                // Plugin.Awake has not yet signalled that this plugin's own patches are applied (the process-start
                // run sits before its patch loop): the table is not built, nothing is cached, and the first run after
                // the signal builds it
                Plugin.Log.LogInfo("[FRAME-TIME] cal i=" + i + " why=" + why + " kind=entries built=0 own_patches=not-applied");
                return;
            }
            if (cals.Length == 0)
            {
                Plugin.Log.LogWarning("[FRAME-TIME] cal i=" + i + " why=" + why + " kind=entries failed: the built table holds no patched entry");
                return;
            }
            var harmony = new Harmony(HarmonyId);
            foreach (EntryCal c in cals)
            {
                if (c.Error != null)
                {
                    Plugin.Log.LogWarning("[FRAME-TIME] cal i=" + i + " why=" + why + " kind=disp shape=" + c.Name + " failed: " + c.Error);
                    continue;
                }
                var u = new long[Batches];
                var p = new long[Batches];
                bool gate = FtGate.Off;
                long guarded = FtCensus.Guarded[c.Entry];
                bool patched = false;
                string failed = null;
                FtGate.Off = true;
                try
                {
                    c.Loop(1000);
                    for (int b = 0; b < Batches; b++) u[b] = Time(c.Loop, EntryCalls);
                    harmony.Patch(c.Dummy, c.Pre, c.Post, null, c.Fin, null);
                    patched = true;
                    c.Loop(1000);
                    for (int b = 0; b < Batches; b++) p[b] = Time(c.Loop, EntryCalls);
                }
                catch (Exception ex) { failed = ex.GetType().Name + ": " + ex.Message; }
                finally
                {
                    FtGate.Off = gate;
                    FtCensus.Guarded[c.Entry] = guarded;
                    if (patched)
                    {
                        try { harmony.Unpatch(c.Dummy, HarmonyPatchType.All, HarmonyId); }
                        catch (Exception ex) { failed = (failed ?? "") + " unpatch: " + ex.Message; }
                    }
                }
                if (failed != null)
                {
                    Plugin.Log.LogWarning("[FRAME-TIME] cal i=" + i + " why=" + why + " kind=disp shape=" + c.Name + " failed: " + failed);
                    continue;
                }
                Plugin.Log.LogInfo("[FRAME-TIME] cal i=" + i + " why=" + why + " kind=disp shape=" + c.Name + " n=" + EntryCalls
                    + " u=" + string.Join(",", u) + " p=" + string.Join(",", p));
            }
#endif
        }

        /// <summary>Every patched entry's calibration. Before Plugin.Awake's signal (OwnPatchesApplied) it returns
        /// an empty table and stores nothing; after it, the table is built once from the patches owned by this
        /// plugin's own Harmony id (PatchedTargets) and kept. An entry whose patch class has no such target after
        /// the signal is a patch that did not attach (lesson #83): its error names the class and is logged by
        /// name on every run (RunEntries), so VR2 and the menu check fail on it by name.</summary>
        private static EntryCal[] Cals()
        {
            if (_cals != null) return _cals;
            if (!_ownPatchesApplied) return NotBuilt;
            Dictionary<Type, MethodBase> targets = PatchedTargets();
            int errors = 0;
            var list = new List<EntryCal>();
            for (int e = 0; e < FtE.Count; e++)
            {
                Type pt = FtE.PatchType(e);
                if (pt == null) continue;
                var c = new EntryCal { Entry = e, Name = FtCensus.ShapeOf[e] ?? ("entry" + e) };
                try { Build(c, pt, targets); }
                catch (Exception ex) { c.Error = ex.GetType().Name + ": " + ex.Message; errors++; }
                list.Add(c);
            }
            _cals = list.ToArray();
            Plugin.Log.LogInfo("[FRAME-TIME] cal i=-1 why=patches kind=entries built=1 own_owner=" + Plugin.ModId
                + " own_targets=" + targets.Count + " entries=" + _cals.Length + " errors=" + errors);
            return _cals;
        }

        /// <summary>Harmony's own table, restricted to the patches owned by this plugin's Harmony id
        /// (Plugin.ModId, the owner of Plugin.Awake's patch loop): each such patch class and the one target it
        /// patches (null when a class patches more than one). Other owners' patches (other mods, this
        /// calibration's own dummies) never enter it.</summary>
        private static Dictionary<Type, MethodBase> PatchedTargets()
        {
            var map = new Dictionary<Type, MethodBase>();
            foreach (MethodBase m in Harmony.GetAllPatchedMethods())
            {
                HarmonyLib.Patches info = Harmony.GetPatchInfo(m);
                if (info == null) continue;
                foreach (var group in new[] { info.Prefixes, info.Postfixes, info.Finalizers, info.Transpilers })
                    foreach (Patch q in group)
                    {
                        if (q.owner != Plugin.ModId || q.PatchMethod == null) continue;
                        Type t = q.PatchMethod.DeclaringType;
                        MethodBase prev;
                        if (map.TryGetValue(t, out prev)) { if (prev != m) map[t] = null; }
                        else map[t] = m;
                    }
            }
            return map;
        }

        private static bool Has(MethodInfo m, Type attr) { return m.GetCustomAttributes(attr, false).Length > 0; }

        private static HarmonyMethod One(HarmonyMethod have, MethodInfo m)
        {
            if (have != null) throw new InvalidOperationException("two patch methods of one kind in " + m.DeclaringType.Name);
            return new HarmonyMethod(m);
        }

        private static void Build(EntryCal c, Type pt, Dictionary<Type, MethodBase> targets)
        {
            MethodBase target;
            if (!targets.TryGetValue(pt, out target))
                throw new InvalidOperationException(pt.Name + " is not attached: no target patched by " + Plugin.ModId + " (lesson #83)");
            if (target == null) throw new InvalidOperationException(pt.Name + " patches more than one target");
            var mi = target as MethodInfo;
            if (mi == null) throw new InvalidOperationException(pt.Name + " patches a constructor");
            if (mi.IsGenericMethod || mi.DeclaringType.IsGenericType) throw new InvalidOperationException(pt.Name + " patches a generic method");
            foreach (MethodInfo m in pt.GetMethods(BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly))
            {
                if (Has(m, typeof(HarmonyTranspiler)) || m.Name == "Transpiler") throw new InvalidOperationException(pt.Name + " has a transpiler");
                if (Has(m, typeof(HarmonyPrefix)) || m.Name == "Prefix") c.Pre = One(c.Pre, m);
                else if (Has(m, typeof(HarmonyPostfix)) || m.Name == "Postfix") c.Post = One(c.Post, m);
                else if (Has(m, typeof(HarmonyFinalizer)) || m.Name == "Finalizer") c.Fin = One(c.Fin, m);
            }
            if (c.Pre == null && c.Post == null && c.Fin == null) throw new InvalidOperationException(pt.Name + " has no patch method");

            ParameterInfo[] ps = mi.GetParameters();
            var types = new Type[ps.Length];
            for (int k = 0; k < ps.Length; k++) types[k] = ps[k].ParameterType;
            if (_module == null)
                _module = AssemblyBuilder.DefineDynamicAssembly(new AssemblyName("FtCalibDummies"), AssemblyBuilderAccess.Run)
                    .DefineDynamicModule("FtCalibDummies");
            TypeBuilder tb = _module.DefineType("FtCal_" + c.Name, TypeAttributes.Public | TypeAttributes.Sealed | TypeAttributes.Class);
            FieldBuilder fb = tb.DefineField("N", typeof(int), FieldAttributes.Public | FieldAttributes.Static);
            MethodBuilder mb = tb.DefineMethod(mi.Name, MethodAttributes.Public | MethodAttributes.HideBySig
                | (mi.IsStatic ? MethodAttributes.Static : 0), mi.ReturnType, types);
            mb.SetImplementationFlags(MethodImplAttributes.IL | MethodImplAttributes.Managed | MethodImplAttributes.NoInlining);
            for (int k = 0; k < ps.Length; k++) mb.DefineParameter(k + 1, ps[k].Attributes, ps[k].Name);
            // A body that never reads its arguments or `this` (the loop passes null and zeroes), long enough to
            // carry a detour: four increments of a static, then the return type's zero.
            ILGenerator il = mb.GetILGenerator();
            for (int k = 0; k < 4; k++)
            {
                il.Emit(OpCodes.Ldsfld, fb); il.Emit(OpCodes.Ldc_I4_1); il.Emit(OpCodes.Add); il.Emit(OpCodes.Stsfld, fb);
            }
            if (mi.ReturnType != typeof(void)) il.Emit(OpCodes.Ldloc, il.DeclareLocal(mi.ReturnType));
            il.Emit(OpCodes.Ret);
            Type dt = tb.CreateType();
            c.Dummy = dt.GetMethod(mi.Name, BindingFlags.Public | BindingFlags.Static | BindingFlags.Instance | BindingFlags.DeclaredOnly);
            if (c.Dummy == null) throw new InvalidOperationException("dummy for " + pt.Name + " not found");

            // The loop: n calls with a null instance and zero arguments (by-ref arguments point at zeroed locals).
            var dm = new DynamicMethod("FtCalLoop_" + c.Name, typeof(void), new[] { typeof(int) }, typeof(FtCalib).Module, true);
            ILGenerator g = dm.GetILGenerator();
            LocalBuilder iv = g.DeclareLocal(typeof(int));
            var args = new LocalBuilder[ps.Length];
            for (int k = 0; k < ps.Length; k++) args[k] = g.DeclareLocal(types[k].IsByRef ? types[k].GetElementType() : types[k]);
            Label body = g.DefineLabel(), cond = g.DefineLabel();
            g.Emit(OpCodes.Br, cond);
            g.MarkLabel(body);
            if (!mi.IsStatic) g.Emit(OpCodes.Ldnull);
            for (int k = 0; k < ps.Length; k++) g.Emit(types[k].IsByRef ? OpCodes.Ldloca : OpCodes.Ldloc, args[k]);
            g.Emit(OpCodes.Call, c.Dummy);
            if (mi.ReturnType != typeof(void)) g.Emit(OpCodes.Pop);
            g.Emit(OpCodes.Ldloc, iv); g.Emit(OpCodes.Ldc_I4_1); g.Emit(OpCodes.Add); g.Emit(OpCodes.Stloc, iv);
            g.MarkLabel(cond);
            g.Emit(OpCodes.Ldloc, iv); g.Emit(OpCodes.Ldarg_0); g.Emit(OpCodes.Blt, body);
            g.Emit(OpCodes.Ret);
            c.Loop = (Action<int>)dm.CreateDelegate(typeof(Action<int>));
        }

        /// <summary>M8, the settled line: once per game (game >= 0) and once at process
        /// start (game -1). cPlant is -1 until the schedule fixes it (part 3).</summary>
        internal static void Settled(int game, long cPlant)
        {
            long slice = -1;
            int incremental = -1;
            try
            {
                incremental = UnityEngine.Scripting.GarbageCollector.isIncremental ? 1 : 0;
                slice = (long)UnityEngine.Scripting.GarbageCollector.incrementalTimeSliceNanoseconds;
            }
            catch { }
            Plugin.Log.LogInfo("[FRAME-TIME] settled g=" + game + " seed=" + FtConfig.Seed + " c_plant=" + cPlant + " W=120"
                + " vsync=" + UnityEngine.QualitySettings.vSyncCount + " target=" + UnityEngine.Application.targetFrameRate
                + " freq=" + Stopwatch.Frequency + " hires=" + (Stopwatch.IsHighResolution ? 1 : 0) + " f_hat=" + FHat
                + " gc_incremental=" + incremental + " gc_slice_ns=" + slice + " f18=" + FtConfig.F18 + " answer=" + FtReplay.AnswerField
                + " armfile=" + (FtConfig.Present ? 1 : 0) + " force=" + FtConfig.Force
                + (FtConfig.Problems.Length > 0 ? " problems=" + FtConfig.Problems.Trim().Replace(' ', ',') : "")
                + " clock=" + (FtClock.Installed ? 1 : 0) + " frames=" + FtClock.Frames + " missing_end=" + FtClock.MissingEnd
                + " cycle_failures=" + FtClock.CycleFailures + " span_depth_violations=" + FtClock.DepthViolations);
        }
    }
}
#endif
