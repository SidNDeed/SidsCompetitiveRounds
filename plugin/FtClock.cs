#if SCR_FRAMETIME
using System;
using System.Diagnostics;
using System.Runtime.InteropServices;

namespace CompetitiveRounds
{
    /// <summary>FrameTime M1 (METHOD-V4.md 3.1): two player-loop entries stamp every frame.
    /// FT_Start runs first in EarlyUpdate and reads Stopwatch ticks (t0) and the main
    /// thread's cycle counter (k0, QueryThreadCycleTime on the GetCurrentThread
    /// pseudo-handle); FT_End runs last in PreLateUpdate and reads t1. When frame f+1
    /// starts, frame f closes with
    ///   F = t0(f+1) - t0(f)   ticks, the frame period;
    ///   S = t1(f) - t0(f)     ticks, the script phase;
    ///   C = k0(f+1) - k0(f)   cycles, the main thread's CPU time over the whole frame,
    ///   P = p0(f+1) - p0(f)   cycles, the process's CPU time over all threads (QueryProcessCycleTime;
    ///                         V4 3.5's process CPU difference, reported beside U, never judged),
    /// all integers, handed to OnFrameClosed (implemented by the window lines, part 3 of the build
    /// brief) with whether FT_End ran in frame f (VR2), the gen-0 GC count at frame f's start and at
    /// its end (a window's gc counts from its first measured frame's start, round-1 MEDIUM
    /// FtFrames.cs:63), and whether frame f is a point's partial closing frame. The live state of
    /// frame f+1 is read once, BEFORE frame f is accumulated: the frame in which combat ended is
    /// excluded (round-1 MEDIUM, FtClock.cs:116), and the schedule decides frame f+1 from that same
    /// read.
    /// The partition (method-v54.md (a)): at the same boundary FtSpan.Cut gives the open class the cycles up to
    /// k0(f+1), so frame f's class differences (W, R, S, E) plus its G equal C exactly, all in main-thread cycles.
    /// G is the GC hook's difference over the frame (GcCycles, set by FtGc only while the native hook is live);
    /// the hook is read here once per frame, and a frame whose G is not known (no hook, a hook that changed at its
    /// start, or a read that threw) is passed with gok false and G 0, its GC then inside its classes.</summary>
    internal static partial class FtClock
    {
        [DllImport("kernel32.dll")]
        private static extern IntPtr GetCurrentThread();

        [DllImport("kernel32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool QueryThreadCycleTime(IntPtr threadHandle, out ulong cycleTime);

        [DllImport("kernel32.dll")]
        private static extern IntPtr GetCurrentProcess();

        [DllImport("kernel32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool QueryProcessCycleTime(IntPtr processHandle, out ulong cycleTime);

        private struct FtStart { }
        private struct FtEnd { }
        private struct FtPlantTick { }

        private static readonly IntPtr Self = GetCurrentThread();
        private static readonly IntPtr Proc = GetCurrentProcess();

        internal static bool Installed;
        internal static long Frames;          // frames closed since install
        internal static long MissingEnd;      // closed frames whose FT_End did not run (VR2)
        internal static long CycleFailures;   // QueryThreadCycleTime returned false (VR2)
        internal static long DepthViolations; // a span still open at a frame boundary (VR2)
        internal static bool InScript;        // between FT_Start and FT_End of the current frame

        /// <summary>The GC hook (B11 SHARED.md, GC interface): the main thread's cumulative GC execution in
        /// cycles. Null means unavailable: cG prints NA and gcn is still counted. FtGc sets it at init, only while
        /// its native hook is live.</summary>
        public static System.Func<long> GcCycles;

        /// <summary>The hook as read at the current frame's start (FtSpan reads GC through it inside the frame).</summary>
        internal static System.Func<long> GcFn;

        /// <summary>One reading of hook fn: false when it is null or throws (a throw is counted).</summary>
        internal static bool GcRead(System.Func<long> fn, out long g)
        {
            g = 0;
            if (fn == null) return false;
            try { g = fn(); return true; }
            catch { FtSpan.GcReadFailures++; return false; }
        }

        private static long _gPrev;
        private static bool _gOk;
        private static long _gcFail0;
        private static readonly long[] _acc0 = new long[FtSpan.Classes];

        private static long _t0;
        private static ulong _k0;
        private static ulong _p0;
        private static int _gc0;
        private static long _s;
        private static bool _ended;
        private static bool _open;

        /// <summary>The current thread's cycle count; 0 when the call fails (counted).</summary>
        internal static ulong Cycles()
        {
            ulong k;
            if (!QueryThreadCycleTime(Self, out k)) { CycleFailures++; return 0; }
            return k;
        }

        /// <summary>The process's cycle count over all threads; 0 when the call fails (counted).</summary>
        internal static ulong ProcessCycles()
        {
            ulong k;
            if (!QueryProcessCycleTime(Proc, out k)) { CycleFailures++; return 0; }
            return k;
        }

        /// <summary>Inserts FT_Start and FT_End. Called once from Plugin.Awake.</summary>
        internal static void Install()
        {
            FtSpan.MainThread = System.Threading.Thread.CurrentThread.ManagedThreadId;
            if (Installed) return;
            var loop = UnityEngine.LowLevel.PlayerLoop.GetCurrentPlayerLoop();
            var start = new UnityEngine.LowLevel.PlayerLoopSystem { type = typeof(FtStart), updateDelegate = OnStart };
            var end = new UnityEngine.LowLevel.PlayerLoopSystem { type = typeof(FtEnd), updateDelegate = OnEnd };
            bool a = Insert(ref loop, typeof(UnityEngine.PlayerLoop.EarlyUpdate), start, true);
            bool b = Insert(ref loop, typeof(UnityEngine.PlayerLoop.PreLateUpdate), end, false);
            var plant = new UnityEngine.LowLevel.PlayerLoopSystem { type = typeof(FtPlantTick), updateDelegate = FtPlant.OnUpdate };
            bool c = Insert(ref loop, typeof(UnityEngine.PlayerLoop.Update), plant, true);
            if (!a || !b || !c)
            {
                Plugin.Log.LogWarning("[FRAME-TIME] clock refused: player-loop phase missing (EarlyUpdate " + a + ", PreLateUpdate " + b
                    + ", Update " + c + ")");
                return;
            }
            UnityEngine.LowLevel.PlayerLoop.SetPlayerLoop(loop);
            Installed = true;
            FtPlant.Init();
            FtE.RegisterAll(); FtA3.RegisterAll();
            FtLedger.Install();
            ulong probe = Cycles();
            Plugin.Log.LogInfo("[FRAME-TIME] clock installed freq=" + Stopwatch.Frequency + " hires=" + (Stopwatch.IsHighResolution ? 1 : 0)
                + " cycles=" + (probe != 0 ? 1 : 0));
        }

        private static bool Insert(ref UnityEngine.LowLevel.PlayerLoopSystem root, Type phase,
            UnityEngine.LowLevel.PlayerLoopSystem sys, bool atStart)
        {
            var subs = root.subSystemList;
            if (subs == null) return false;
            for (int i = 0; i < subs.Length; i++)
            {
                if (subs[i].type != phase) continue;
                var list = subs[i].subSystemList ?? new UnityEngine.LowLevel.PlayerLoopSystem[0];
                var grown = new UnityEngine.LowLevel.PlayerLoopSystem[list.Length + 1];
                if (atStart)
                {
                    grown[0] = sys;
                    Array.Copy(list, 0, grown, 1, list.Length);
                }
                else
                {
                    Array.Copy(list, 0, grown, 0, list.Length);
                    grown[list.Length] = sys;
                }
                subs[i].subSystemList = grown;
                root.subSystemList = subs;
                return true;
            }
            return false;
        }

        private static bool _marksCal;
        internal const int MarkCalN = 10000;

        private static void OnStart()
        {
            long t = Stopwatch.GetTimestamp();
            ulong k = Cycles();
            ulong pk = ProcessCycles();
            int gc = GC.CollectionCount(0);
            long g;
            bool gok = GcRead(GcFn, out g);
            FtSpan.Cut(k, g, gok);
            bool live = FtSchedule.ReadLive();
            if (_open)
            {
                Frames++;
                if (!_ended) MissingEnd++;
                bool fok = gok && _gOk && FtSpan.GcReadFailures == _gcFail0;
                long[] a = FtSpan.Acc;
                OnFrameClosed(t - _t0, _ended ? _s : 0, k - _k0, pk - _p0, _gc0, gc, _ended, FtSchedule.ClosingFrame(live),
                    fok ? g - _gPrev : 0, fok, a[FtSpan.ClsW] - _acc0[FtSpan.ClsW], a[FtSpan.ClsR] - _acc0[FtSpan.ClsR],
                    a[FtSpan.ClsS] - _acc0[FtSpan.ClsS], a[FtSpan.ClsE] - _acc0[FtSpan.ClsE]);
            }
            System.Array.Copy(FtSpan.Acc, _acc0, FtSpan.Classes);
            var fn = GcCycles;   // the hook, read once per frame: a hook set or changed counts from this frame on
            if (fn != GcFn)
            {
                GcFn = fn;
                gok = GcRead(fn, out g);
                FtSpan.Rebase(g, gok);
            }
            _gPrev = g;
            _gOk = gok;
            _gcFail0 = FtSpan.GcReadFailures;
            _t0 = t;
            _k0 = k;
            _p0 = pk;
            _gc0 = gc;
            _s = 0;
            _ended = false;
            _open = true;
            if (!_marksCal)
            {
                _marksCal = true;   // once, at the first frame boundary: before game 0
                FtSpan.CalibrateMarks(MarkCalN);
            }
            if (FtSpan.Depth != 0) DepthViolations++;
            InScript = true;
            FtSchedule.Boundary(live);
        }

        private static void OnEnd()
        {
            if (!_open) return;
            _s = Stopwatch.GetTimestamp() - _t0;
            _ended = true;
            InScript = false;
        }

        /// <summary>Frame f closed: F and S in Stopwatch ticks, C in cycles, and C's partition in cycles: G (cg,
        /// known when gok) and the class differences W, R, S, E. Implemented by the window and point lines; without
        /// an implementation the call compiles away.</summary>
        static partial void OnFrameClosed(long f, long s, ulong c, ulong p, int gc0, int gc1, bool ended, bool closing,
            long cg, bool gok, long cw, long cr, long cs, long ce);
    }
}
#endif
