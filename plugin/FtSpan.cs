#if SCR_FRAMETIME
using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Threading;

namespace CompetitiveRounds
{
    /// <summary>FrameTime M4 (METHOD-V4.md 3.1): outermost spans. A depth counter opens a
    /// span only at depth 0, so work one component does inside another's span is counted
    /// once (HIGH 7). Span time (Stopwatch ticks) and calls accumulate per component, per
    /// moment, per phase (inside or outside the script phase FT_Start..FT_End) and per
    /// kind: GATED (the gate removes it at OFF windows), UPKEEP (class iii upkeep, runs in
    /// both arms, F13), REPLAY (F18 reading A, reported separately) and WRITER (collector
    /// output service, FtLedger). Stated as elapsed time inside the spans: an upper bound on
    /// their own CPU time, used for the census, absorption (VR9) and placement (B3), never as
    /// the B1 estimate.
    ///
    /// The partition (method-v54.md (a), ruling R6-A3.11.136 (2)): every Open and Close also moves the main
    /// thread's executed cycles (FtClock.Cycles) between five exclusive classes, C = G + W + R + S + E. Each scope's
    /// class is fixed when it opens (Gated is S, switched; Upkeep and Replay are R, retained; Writer is W). A nested
    /// scope suspends its parent: the cycles between two transitions go to the class on top of the stack. Ownership
    /// precedence is GC, writer, remaining collector, outside: inside a writer scope every nested scope stays W, and
    /// main-thread GC (FtClock.GcCycles, when the hook is live) is taken out of whichever class it ran in and counted
    /// as G by FtClock. E is the class with no scope open. FtClock.OnStart cuts the open class at every frame boundary
    /// (Cut), so a frame's class sums plus its G equal its C exactly.
    /// Main thread only: the depth counter and the class stack are one thread's, so a call from any other thread opens
    /// nothing, leaves both alone and is counted in OffThread (the offthread line).
    /// Use: bool s = FtSpan.Open(FtSpan.Combat, FtSpan.Gated); try { body } finally { FtSpan.Close(s); }</summary>
    internal static class FtSpan
    {
        // Components, in the census order; Cal is the calibration's own slot, never reported as a component.
        internal const int Combat = 0, Hit = 1, Seat = 2, Identity = 3, CardDraw = 4, Point = 5, PeerBuild = 6, Cal = 7;
        internal const int Components = 8;
        internal static readonly string[] ComponentNames =
            { "CombatEvidence", "HitEvidence", "SeatEvidence", "IdentityClockEvidence", "CardDrawEvidence", "PointEvidence", "PeerBuild", "Cal" };

        // Moments: set by the schedule (part 3); Menu until a game starts.
        internal const int Live = 0, Between = 1, Pick = 2, GameOver = 3, Menu = 4;
        internal const int Moments = 5;
        internal static readonly string[] MomentNames = { "live", "between", "pick", "over", "menu" };

        // Kinds.
        internal const int Gated = 0, Upkeep = 1, Replay = 2, Writer = 3;
        internal const int Kinds = 4;
        internal static readonly string[] KindNames = { "gated", "upkeep", "replay", "writer" };

        // The partition's classes (method-v54.md:11). G is never a scope's class: FtClock counts it.
        internal const int ClsG = 0, ClsW = 1, ClsR = 2, ClsS = 3, ClsE = 4;
        internal const int Classes = 5;
        private static readonly int[] ClassOfKind = { ClsS, ClsR, ClsR, ClsW };

        internal const int Phases = 2; // 0 inside the script phase, 1 outside

        internal static int Moment = Menu;

        internal static readonly long[] Ticks = new long[Components * Moments * Phases * Kinds];
        internal static readonly long[] Calls = new long[Components * Moments * Phases * Kinds];

        /// <summary>Exclusive executed cycles per class since install, GC taken out while the hook is live (index
        /// ClsG unused). Never reset: FtClock takes per-frame differences.</summary>
        internal static readonly long[] Acc = new long[Classes];

        /// <summary>Set by FtClock.Install (Plugin.Awake, the main thread) before anything else.</summary>
        internal static int MainThread = -1;
        internal static long OffThread;
        internal static long ClassOverflow;   // scopes past the class stack's depth (their class is not pushed)
        internal static long GcReadFailures;  // a GC hook read that threw inside a frame

        private const int StackCap = 64;
        private static readonly int[] _prev = new int[StackCap];
        private static int _cls = ClsE;
        private static ulong _k;
        private static long _g;
        private static bool _gok;

        private static int _depth;
        private static int _component;
        private static int _kind;
        private static long _t0;

        internal static int Index(int component, int moment, int phase, int kind)
        {
            return ((component * Moments + moment) * Phases + phase) * Kinds + kind;
        }

        /// <summary>The class now running on the main thread (E with no scope open).</summary>
        internal static int Current => _cls;

        /// <summary>A collector scope is open on the main thread now (its class is R or S): the producer test of
        /// FtLedger's tokens. Main thread only.</summary>
        internal static bool CollectorOpen => _depth > 0 && (_cls == ClsR || _cls == ClsS);

        /// <summary>The cycles since the last transition go to the class that ran them, GC taken out when both
        /// readings of the hook are valid.</summary>
        private static void Mark(ulong k, long g, bool gok)
        {
            long d = unchecked((long)(k - _k));
            if (gok && _gok) d -= g - _g;
            Acc[_cls] += d;
            _k = k;
            _g = g;
            _gok = gok;
        }

        /// <summary>Class transitions on the main thread (every Switch): the window line's nm.</summary>
        internal static long Marks;

        private static void Switch(int cls)
        {
            Marks++;
            long g;
            bool gok = FtClock.GcRead(FtClock.GcFn, out g);
            Mark(FtClock.Cycles(), g, gok);
            _cls = cls;
        }

        /// <summary>The boot line `[FRAME-TIME] mark cost cyc= p90= n=` (B11 SHARED.md, the window line's nm): n
        /// back-to-back class transitions (Switch, the code every mark runs, its GC read included) on the main thread,
        /// each bracketed by two cycle reads, at the first frame boundary (FtClock.OnStart, before game 0). A bracket
        /// holds one cycle read beyond the transition, so cyc (the lower median) and p90 bound one transition from
        /// above. Acc, Marks and the class state are restored after, so no class gains or loses cycles: the
        /// calibration's cycles fall to the class open before it, in that menu frame. It measures the overhead; the
        /// overhead stays in the charge (method-v53.md:13-48).</summary>
        internal static void CalibrateMarks(int n)
        {
            var acc = (long[])Acc.Clone();
            int cls = _cls;
            ulong k = _k;
            long g = _g, marks = Marks;
            bool gok = _gok;
            var s = new long[n];
            for (int i = 0; i < n; i++)
            {
                ulong a = FtClock.Cycles();
                Switch((i & 1) == 0 ? ClsS : ClsR);
                s[i] = unchecked((long)(FtClock.Cycles() - a));
            }
            System.Array.Copy(acc, Acc, Classes);
            _cls = cls;
            _k = k;
            _g = g;
            _gok = gok;
            Marks = marks;
            System.Array.Sort(s);
            Plugin.Log.LogInfo("[FRAME-TIME] mark cost cyc=" + s[(n - 1) / 2] + " p90=" + s[(int)((n - 1) * 9L / 10)] + " n=" + n);
        }

        /// <summary>FtClock.OnStart, at every frame boundary, with the readings it took for the closing frame: the
        /// open class's cycles up to here are that frame's.</summary>
        internal static void Cut(ulong k, long g, bool gok)
        {
            Mark(k, g, gok);
        }

        /// <summary>FtClock.OnStart, when the GC hook it reads changed: the next interval's GC base is the new hook's
        /// reading (no cycles move).</summary>
        internal static void Rebase(long g, bool gok)
        {
            _g = g;
            _gok = gok;
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        internal static bool Open(int component, int kind)
        {
            if (Thread.CurrentThread.ManagedThreadId != MainThread) { Interlocked.Increment(ref OffThread); return false; }
            int d = _depth++;
            if (d < StackCap)
            {
                _prev[d] = _cls;
                int cls = _cls == ClsW ? ClsW : ClassOfKind[kind];
                if (cls != _cls) Switch(cls);
            }
            else ClassOverflow++;
            if (d != 0) return false;
            _component = component;
            _kind = kind;
            _t0 = Stopwatch.GetTimestamp();
            return true;
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        internal static void Close(bool opened)
        {
            if (Thread.CurrentThread.ManagedThreadId != MainThread) return;
            int d = --_depth;
            if (opened)
            {
                long dt = Stopwatch.GetTimestamp() - _t0;
                int i = Index(_component, Moment, FtClock.InScript ? 0 : 1, _kind);
                Ticks[i] += dt;
                Calls[i]++;
            }
            if (d >= 0 && d < StackCap && _prev[d] != _cls) Switch(_prev[d]);
        }

        /// <summary>A writer scope with no tick-ledger cell (FtLedger's service of collector output inside the
        /// producer's span): the class stack only. Main thread only; pair with PopWriter.</summary>
        internal static void PushWriter()
        {
            int d = _depth++;
            if (d < StackCap)
            {
                _prev[d] = _cls;
                if (_cls != ClsW) Switch(ClsW);
            }
            else ClassOverflow++;
        }

        internal static void PopWriter()
        {
            int d = --_depth;
            if (d >= 0 && d < StackCap && _prev[d] != _cls) Switch(_prev[d]);
        }

        /// <summary>Sum of arr over the seven components (not Cal) and both phases, for one moment and kind.</summary>
        internal static long Sum(long[] arr, int moment, int kind)
        {
            long s = 0;
            for (int c = 0; c < Cal; c++)
                for (int p = 0; p < Phases; p++) s += arr[Index(c, moment, p, kind)];
            return s;
        }

        /// <summary>Depth must be 0 at every frame boundary; FT_Start checks it (VR2).</summary>
        internal static int Depth => _depth;

        internal static void Reset()
        {
            for (int i = 0; i < Ticks.Length; i++) { Ticks[i] = 0; Calls[i] = 0; }
        }
    }
}
#endif
