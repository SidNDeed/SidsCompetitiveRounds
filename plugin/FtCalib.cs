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
    ///     Harmony id, then unpatched again; and a direct call behind the gate read. Each
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
        }

        private static class Patches
        {
            internal static void Post() { }
            internal static bool Pre() { return true; }
            internal static void PostResult(ref int __result) { }
            internal static void PostInstance(Dummy __instance) { }
            internal static Exception Fin(Exception __exception) { return __exception; }
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
            new Shape { Name = "static0.post", Loop = 0, Baseline = 0, Target = "S0", Postfix = "Post" },
            new Shape { Name = "static0.pre", Loop = 0, Baseline = 0, Target = "S0", Prefix = "Pre" },
            new Shape { Name = "static0.prepost", Loop = 0, Baseline = 0, Target = "S0", Prefix = "Pre", Postfix = "Post" },
            new Shape { Name = "static0.fin", Loop = 0, Baseline = 0, Target = "S0", Finalizer = "Fin" },
            new Shape { Name = "static1.result.post", Loop = 1, Baseline = 1, Target = "S1", Postfix = "PostResult" },
            new Shape { Name = "inst0.instance.post", Loop = 2, Baseline = 2, Target = "I0", Postfix = "PostInstance" },
            new Shape { Name = "static2.ref.post", Loop = 3, Baseline = 3, Target = "S2", Postfix = "Post" },
            new Shape { Name = "gate.direct", Loop = 4, Baseline = 0, Target = null },
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
                try
                {
                    Loop(s.Loop, 1000);
                    for (int b = 0; b < Batches; b++) p[b] = Loop(s.Loop, Calls);
                }
                finally
                {
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
                + " gc_incremental=" + incremental + " gc_slice_ns=" + slice + " f18=" + FtConfig.F18
                + " armfile=" + (FtConfig.Present ? 1 : 0) + " force=" + FtConfig.Force
                + (FtConfig.Problems.Length > 0 ? " problems=" + FtConfig.Problems.Trim().Replace(' ', ',') : "")
                + " clock=" + (FtClock.Installed ? 1 : 0) + " frames=" + FtClock.Frames + " missing_end=" + FtClock.MissingEnd
                + " cycle_failures=" + FtClock.CycleFailures + " span_depth_violations=" + FtClock.DepthViolations);
        }
    }
}
#endif
