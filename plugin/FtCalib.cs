#if SCR_FRAMETIME
using System;
using System.Diagnostics;
using System.Reflection;
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
    /// (b) Dispatch: for each patch shape, 20 batches of 100,000 calls of a NoInlining
    ///     dummy unpatched, then the same patched in that shape by this calibration's own
    ///     Harmony id, then unpatched again; and a direct call whose body opens with the census
    ///     check. Every patch body is the closed path a gated entry runs at an OFF point, run
    ///     with the gate set, so the difference is what the OFF arm cannot remove. Each
    ///     run is one unit of V4 section 3.6's allowance D_j. The census (part 2) maps
    ///     every gated entry to one of these shapes; VR2 requires a calibration line for
    ///     every mapped shape at every game start.
    /// (c) The span's own cost: an outermost span around an empty body (x++), against the
    ///     body alone, in the calibration's own span slot (FtSpan.Cal).
    /// The settled line (M8) is written once per game and once at process start.</summary>
    internal static class FtCalib
    {
        private const int Batches = 20;
        private const int Calls = 100000;
        private const int Spins = 5;
        internal const string HarmonyId = "competitiverounds.frametime.calibration";

        internal static long FHat;
        private static int _runs;
        private static int _sink;
        private static readonly Dummy TheDummy = new Dummy();

        internal sealed class Dummy
        {
            internal int V;

            [MethodImpl(MethodImplOptions.NoInlining)]
            internal static void S0() { _sink++; }

            [MethodImpl(MethodImplOptions.NoInlining)]
            internal static int S1(int a) { return a + 1; }

            [MethodImpl(MethodImplOptions.NoInlining)]
            internal void I0() { V++; }

            [MethodImpl(MethodImplOptions.NoInlining)]
            internal static void S2(ref int a, object b) { a++; }

            // Targets of the census shapes: instance void, object and bool with two arguments; static void with
            // three and with two; and a direct call whose body opens with the census check.
            [MethodImpl(MethodImplOptions.NoInlining)]
            internal void I1(int a, float b) { V += a; }

            [MethodImpl(MethodImplOptions.NoInlining)]
            internal object IR(int a, float b) { V += a; return this; }

            [MethodImpl(MethodImplOptions.NoInlining)]
            internal bool IB(int a, float b) { V += a; return (a & 1) == 0; }

            [MethodImpl(MethodImplOptions.NoInlining)]
            internal static void T3(object a, string b, int c) { _sink += c; }

            [MethodImpl(MethodImplOptions.NoInlining)]
            internal static void T2(object a, object b) { _sink++; }

            [MethodImpl(MethodImplOptions.NoInlining)]
            internal static void CallGated()
            {
                if (FtCensus.Skip(CalEntry)) return;
                _sink++;
            }
        }

        /// <summary>The census slot the calibration's closed paths count in: never registered, so no census
        /// line and no sum includes it.</summary>
        internal const int CalEntry = 255;

        private static class Patches
        {
            internal static void Post() { }
            internal static bool Pre() { return true; }
            internal static void PostResult(ref int __result) { }
            internal static void PostInstance(Dummy __instance) { }
            internal static Exception Fin(Exception __exception) { return __exception; }

            // The closed paths, one per census shape (INVENTORY.md "Patch shapes").
            internal static void S1Pre(Dummy __instance, int a) { if (FtCensus.Skip(CalEntry)) return; _sink++; }
            internal static void S2Post(Dummy __instance, int a) { if (FtCensus.Skip(CalEntry)) return; _sink++; }
            internal static void S3Post(object __0, string __1, int __2) { if (FtCensus.Skip(CalEntry)) return; _sink++; }
            internal static void S4Post(Dummy __instance, int a, object __result) { if (FtCensus.Skip(CalEntry)) return; _sink++; }
            internal static Exception S5Fin(Dummy __instance, Exception __exception)
            {
                if (FtCensus.Skip(CalEntry)) return __exception;
                _sink++;
                return __exception;
            }
            internal static void S6Pre(Dummy __instance, int a, out long __state)
            {
                if (FtCensus.Skip(CalEntry)) { __state = 0; return; }
                __state = 1;
            }
            internal static Exception S6Fin(Dummy __instance, long __state, Exception __exception)
            {
                if (FtGate.Off) return __exception;
                _sink++;
                return __exception;
            }
            internal static void S7Pre(object __0, object __1, out long __state)
            {
                if (FtCensus.Skip(CalEntry)) { __state = 0; return; }
                __state = 1;
            }
            internal static Exception S7Fin(long __state, Exception __exception)
            {
                if (FtGate.Off) return __exception;
                _sink++;
                return __exception;
            }
            internal static void S8Pre(Dummy __instance, out long __state)
            {
                if (FtCensus.Skip(CalEntry)) { __state = 0; return; }
                __state = 1;
            }
            internal static void S8Post(Dummy __instance, long __state) { if (FtGate.Off) return; _sink++; }
            internal static void S9Post(Dummy __instance, bool __result, long __state) { if (FtGate.Off) return; _sink++; }
            internal static void S11Pre() { if (FtCensus.Skip(CalEntry)) return; _sink++; }
            internal static Exception S11Fin(Exception __exception)
            {
                if (FtGate.Off) return __exception;
                _sink++;
                return __exception;
            }
        }

        /// <summary>A patch shape: the loop that calls its target, the target, and its patches.</summary>
        private struct Shape
        {
            internal string Name;
            internal int Loop;
            internal int Baseline;
            internal string Target;
            internal string Prefix;
            internal string Postfix;
            internal string Finalizer;
        }

        private static readonly Shape[] Shapes =
        {
            // The census shapes (INVENTORY.md "Patch shapes"; FtEntries.cs names each entry's), each patched
            // with its closed path; "call" is a direct call whose body opens with the census check, against
            // the empty loop. S10, S12 to S14 belong to no gated entry.
            new Shape { Name = "S1", Loop = 10, Baseline = 10, Target = "I1", Prefix = "S1Pre" },
            new Shape { Name = "S2", Loop = 10, Baseline = 10, Target = "I1", Postfix = "S2Post" },
            new Shape { Name = "S3", Loop = 13, Baseline = 13, Target = "T3", Postfix = "S3Post" },
            new Shape { Name = "S4", Loop = 11, Baseline = 11, Target = "IR", Postfix = "S4Post" },
            new Shape { Name = "S5", Loop = 10, Baseline = 10, Target = "I1", Finalizer = "S5Fin" },
            new Shape { Name = "S6", Loop = 10, Baseline = 10, Target = "I1", Prefix = "S6Pre", Finalizer = "S6Fin" },
            new Shape { Name = "S7", Loop = 14, Baseline = 14, Target = "T2", Prefix = "S7Pre", Finalizer = "S7Fin" },
            new Shape { Name = "S8", Loop = 10, Baseline = 10, Target = "I1", Prefix = "S8Pre", Postfix = "S8Post" },
            new Shape { Name = "S9", Loop = 12, Baseline = 12, Target = "IB", Prefix = "S8Pre", Postfix = "S9Post" },
            new Shape { Name = "S11", Loop = 2, Baseline = 2, Target = "I0", Prefix = "S11Pre", Finalizer = "S11Fin" },
            new Shape { Name = "call", Loop = 15, Baseline = 6, Target = null },
            new Shape { Name = "span.empty", Loop = 5, Baseline = 6, Target = null },
        };

        /// <summary>One calibration run; why names the moment (start, or game g).</summary>
        internal static void Run(string why)
        {
            int i = _runs++;
            try { RunFHat(i, why); }
            catch (Exception ex) { Plugin.Log.LogWarning("[FRAME-TIME] cal i=" + i + " kind=fhat failed: " + ex.Message); }
            try { RunDispatch(i, why); }
            catch (Exception ex) { Plugin.Log.LogWarning("[FRAME-TIME] cal i=" + i + " kind=disp failed: " + ex.Message); }
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
            Dummy d = TheDummy;
            object o = d;
            int x = 0;
            long t0 = Stopwatch.GetTimestamp();
            switch (loop)
            {
                case 0: for (int j = 0; j < n; j++) Dummy.S0(); break;
                case 1: for (int j = 0; j < n; j++) x = Dummy.S1(x); break;
                case 2: for (int j = 0; j < n; j++) d.I0(); break;
                case 3: for (int j = 0; j < n; j++) Dummy.S2(ref x, o); break;
                case 4: for (int j = 0; j < n; j++) { if (!FtGate.Off) Dummy.S0(); } break;
                case 5: for (int j = 0; j < n; j++) { bool sp = FtSpan.Open(FtSpan.Cal, FtSpan.Gated); x++; FtSpan.Close(sp); } break;
                case 6: for (int j = 0; j < n; j++) { x++; } break;
                case 10: for (int j = 0; j < n; j++) d.I1(j, 1f); break;
                case 11: for (int j = 0; j < n; j++) { if (d.IR(j, 1f) == null) x++; } break;
                case 12: for (int j = 0; j < n; j++) { if (d.IB(j, 1f)) x++; } break;
                case 13: for (int j = 0; j < n; j++) Dummy.T3(o, "m", j); break;
                case 14: for (int j = 0; j < n; j++) Dummy.T2(o, o); break;
                case 15: for (int j = 0; j < n; j++) { Dummy.CallGated(); x++; } break;
            }
            long t = Stopwatch.GetTimestamp() - t0;
            _sink += x;
            return t;
        }

        private static HarmonyMethod Hm(string name)
        {
            return name == null ? null : new HarmonyMethod(AccessTools.Method(typeof(Patches), name));
        }

        private static void RunDispatch(int i, string why)
        {
            var harmony = new Harmony(HarmonyId);
            foreach (Shape s in Shapes)
            {
                var u = new long[Batches];
                var p = new long[Batches];
                Loop(s.Baseline, 1000);
                for (int b = 0; b < Batches; b++) u[b] = Loop(s.Baseline, Calls);
                MethodInfo target = s.Target == null ? null : AccessTools.Method(typeof(Dummy), s.Target);
                if (target != null) harmony.Patch(target, Hm(s.Prefix), Hm(s.Postfix), null, Hm(s.Finalizer), null);
                // The closed paths need the gate set: the one write of FtGate.Off outside FtSchedule.Boundary,
                // inside this calibration, with nothing else running on the main thread, restored after.
                bool gate = FtGate.Off;
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
                    if (target != null) harmony.Unpatch(target, HarmonyPatchType.All, HarmonyId);
                }
                Plugin.Log.LogInfo("[FRAME-TIME] cal i=" + i + " why=" + why + " kind=" + (s.Name.StartsWith("span.") ? "span" : "disp") + " shape=" + s.Name + " n=" + Calls
                    + " u=" + string.Join(",", u) + " p=" + string.Join(",", p));
            }
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
