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
    /// The partition (method-v54.md (a), ruling R6-A3.11.136 (2); V6, rulings R6-A3.11.146 and .147): every scope's
    /// open and close also moves the main thread's executed cycles (FtClock.Cycles) between seven exclusive classes,
    /// C = G + W + R + S + E + P + X. A component scope's class is fixed when it opens (Gated is S, switched; Upkeep and
    /// Replay are R, retained; Writer is W). P is a receive handler of the peer's collector traffic (FtLedger's recv
    /// scopes, EnterP). X is Photon's own main-thread work, the four PhotonPeer entries FtPhoton patches (EnterX).
    /// Inside X, each LoadBalancingClient listener callback (EnterListener) returns the class to E, so a game handler
    /// runs in E and a collector handler opens its own class inside it; a listener callback anywhere else keeps the
    /// class it found. A nested scope suspends its parent: the cycles between two transitions go to the class on top
    /// of the class stack. Ownership precedence is GC, writer, the rest: inside a writer scope every nested scope stays
    /// W, and main-thread GC (FtClock.GcCycles, when the hook is live) is taken out of whichever class it ran in and
    /// counted as G by FtClock. E is the class with no scope open. FtClock.OnStart cuts the open class at every frame
    /// boundary (Cut), so a frame's class sums plus its G equal its C exactly.
    /// The allocation counter (FtAlloc) is read at every transition and every cut, beside the cycle counter, and its
    /// bytes follow the cycles: AccA holds the bytes allocated while each class ran on the main thread.
    /// Two depths: the class stack (every scope, _sd) and the component spans (Open/Close only, _depth), so a component
    /// span inside an X, E or P scope is still an outermost span for the tick ledger.
    /// Main thread only: the depth counters and the class stack are one thread's, so a call from any other thread opens
    /// nothing, leaves both alone and is counted (OffThread for component scopes, PhotonOffMain for X and listener
    /// scopes). Use: bool s = FtSpan.Open(FtSpan.Combat, FtSpan.Gated); try { body } finally { FtSpan.Close(s); }</summary>
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

        // The partition's classes (method-v54.md:11; V6 adds P and X). G is never a scope's class: FtClock counts it.
        internal const int ClsG = 0, ClsW = 1, ClsR = 2, ClsS = 3, ClsE = 4, ClsP = 5, ClsX = 6;
        internal const int Classes = 7;
        private static readonly int[] ClassOfKind = { ClsS, ClsR, ClsR, ClsW };

        internal const int Phases = 2; // 0 inside the script phase, 1 outside

        internal static int Moment = Menu;

        internal static readonly long[] Ticks = new long[Components * Moments * Phases * Kinds];
        internal static readonly long[] Calls = new long[Components * Moments * Phases * Kinds];

        /// <summary>Exclusive executed cycles per class since install, GC taken out while the hook is live (index
        /// ClsG unused). Never reset: FtClock takes per-frame differences.</summary>
        internal static readonly long[] Acc = new long[Classes];

        /// <summary>Bytes allocated per class since install, while that class ran on the main thread (FtAlloc; index
        /// ClsG unused). Never reset.</summary>
        internal static readonly long[] AccA = new long[Classes];

        /// <summary>Set by FtClock.Install (Plugin.Awake, the main thread) before anything else.</summary>
        internal static int MainThread = -1;
        internal static long OffThread;
        internal static long PhotonOffMain;   // X and listener scopes entered off the main thread (no class moves)
        internal static long ClassOverflow;   // scopes past the class stack's depth (their class is not pushed)
        internal static long GcReadFailures;  // a GC hook read that threw inside a frame

        private const int StackCap = 64;
        private static readonly int[] _prev = new int[StackCap];
        private static int _cls = ClsE;
        private static int _sd;               // the class stack's depth
        private static ulong _k;
        private static long _g;
        private static bool _gok;
        private static long _a;
        private static bool _aok;

        private static int _depth;            // the component spans' depth
        private static int _component;
        private static int _kind;
        private static long _t0;

        /// <summary>K3's mutant (k_mutant=k3): a listener callback inside X keeps X.</summary>
        internal static bool MutantK3;

        internal static int Index(int component, int moment, int phase, int kind)
        {
            return ((component * Moments + moment) * Phases + phase) * Kinds + kind;
        }

        /// <summary>The class now running on the main thread (E with no scope open).</summary>
        internal static int Current => _cls;

        /// <summary>A collector scope is open on the main thread now (its class is R, S or P): the producer test of
        /// FtLedger's tokens. Main thread only.</summary>
        internal static bool CollectorOpen => _sd > 0 && (_cls == ClsR || _cls == ClsS || _cls == ClsP);

        /// <summary>The controls' mutants (FtClock.Install, from the sentinel's k_mutant key): k1 makes every counter
        /// read allocate, k2 books gated scopes in E, k3 keeps a listener callback inside X in X. Each breaks the rule
        /// its control checks, for the control's one failing run; none is set in a sitting.</summary>
        internal static void SetMutants(string k)
        {
            FtAlloc.MutantK1 = k == "k1";
            if (k == "k2") ClassOfKind[Gated] = ClsE;
            MutantK3 = k == "k3";
            Plugin.Log.LogInfo("[FRAME-TIME] controls k_mutant=" + (k == "k1" || k == "k2" || k == "k3" ? k : "none"));
        }

        /// <summary>The cycles and bytes since the last transition go to the class that ran them, GC taken out when
        /// both readings of the hook are valid, bytes counted when both readings of the counter are.</summary>
        private static void Mark(ulong k, long g, bool gok, long a, bool aok)
        {
            long d = unchecked((long)(k - _k));
            if (gok && _gok) d -= g - _g;
            Acc[_cls] += d;
            if (aok && _aok) AccA[_cls] += FtAlloc.Delta(_a, a);
            _k = k;
            _g = g;
            _gok = gok;
            _a = a;
            _aok = aok;
        }

        /// <summary>Class transitions on the main thread (every Switch): the window line's nm.</summary>
        internal static long Marks;

        private static void Switch(int cls)
        {
            Marks++;
            long g;
            bool gok = FtClock.GcRead(FtClock.GcFn, out g);
            long a;
            bool aok = FtAlloc.Read(out a);
            Mark(FtClock.Cycles(), g, gok, a, aok);
            _cls = cls;
        }

        /// <summary>The class state a calibration or a control restores after it ran.</summary>
        internal struct State
        {
            internal long[] Acc, AccA;
            internal int Cls;
            internal ulong K;
            internal long G, A, Marks;
            internal bool Gok, Aok;
        }

        internal static State Save()
        {
            return new State { Acc = (long[])Acc.Clone(), AccA = (long[])AccA.Clone(), Cls = _cls, K = _k, G = _g, A = _a,
                Marks = Marks, Gok = _gok, Aok = _aok };
        }

        /// <summary>No class gains or loses cycles or bytes: what ran since Save falls, at the next transition or cut,
        /// to the class open at Save. The class stack must be back at its depth at Save.</summary>
        internal static void Restore(State s)
        {
            System.Array.Copy(s.Acc, Acc, Classes);
            System.Array.Copy(s.AccA, AccA, Classes);
            _cls = s.Cls;
            _k = s.K;
            _g = s.G;
            _a = s.A;
            Marks = s.Marks;
            _gok = s.Gok;
            _aok = s.Aok;
        }

        /// <summary>The boot line `[FRAME-TIME] mark cost cyc= p90= n=` (B11 SHARED.md, the window line's nm): n
        /// back-to-back class transitions (Switch, the code every mark runs, its GC and counter reads included) on the
        /// main thread, each bracketed by two cycle reads, at the first frame boundary (FtClock.OnStart, before game 0).
        /// A bracket holds one cycle read beyond the transition, so cyc (the lower median) and p90 bound one transition
        /// from above. The class state is restored after (Restore). It measures the overhead; the overhead stays in the
        /// charge (method-v53.md:13-48).</summary>
        internal static void CalibrateMarks(int n)
        {
            var st = Save();
            var s = new long[n];
            for (int i = 0; i < n; i++)
            {
                ulong a = FtClock.Cycles();
                Switch((i & 1) == 0 ? ClsS : ClsR);
                s[i] = unchecked((long)(FtClock.Cycles() - a));
            }
            Restore(st);
            System.Array.Sort(s);
            Plugin.Log.LogInfo("[FRAME-TIME] mark cost cyc=" + s[(n - 1) / 2] + " p90=" + s[(int)((n - 1) * 9L / 10)] + " n=" + n);
        }

        /// <summary>FtClock.OnStart, at every frame boundary, with the readings it took for the closing frame: the
        /// open class's cycles and bytes up to here are that frame's.</summary>
        internal static void Cut(ulong k, long g, bool gok, long a, bool aok)
        {
            Mark(k, g, gok, a, aok);
        }

        /// <summary>FtClock.OnStart, when the GC hook it reads changed: the next interval's GC base is the new hook's
        /// reading (no cycles move).</summary>
        internal static void Rebase(long g, bool gok)
        {
            _g = g;
            _gok = gok;
        }

        /// <summary>One scope enters the class stack with class cls (main thread only).</summary>
        private static void Push(int cls)
        {
            int d = _sd++;
            if (d < StackCap)
            {
                _prev[d] = _cls;
                if (cls != _cls) Switch(cls);
            }
            else ClassOverflow++;
        }

        /// <summary>The innermost scope leaves: its parent's class runs again.</summary>
        private static void Pop()
        {
            int d = --_sd;
            if (d >= 0 && d < StackCap && _prev[d] != _cls) Switch(_prev[d]);
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        internal static bool Open(int component, int kind)
        {
            if (Thread.CurrentThread.ManagedThreadId != MainThread) { Interlocked.Increment(ref OffThread); return false; }
            Push(_cls == ClsW ? ClsW : ClassOfKind[kind]);
            if (_depth++ != 0) return false;
            _component = component;
            _kind = kind;
            _t0 = Stopwatch.GetTimestamp();
            return true;
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        internal static void Close(bool opened)
        {
            if (Thread.CurrentThread.ManagedThreadId != MainThread) return;
            _depth--;
            if (opened)
            {
                long dt = Stopwatch.GetTimestamp() - _t0;
                int i = Index(_component, Moment, FtClock.InScript ? 0 : 1, _kind);
                Ticks[i] += dt;
                Calls[i]++;
            }
            Pop();
        }

        /// <summary>A writer scope with no tick-ledger cell (FtLedger's service of collector output inside the
        /// producer's span): the class stack only. Main thread only; pair with PopWriter.</summary>
        internal static void PushWriter()
        {
            Push(ClsW);
        }

        internal static void PopWriter()
        {
            Pop();
        }

        /// <summary>A recv scope (FtLedger.RecvEnter, RecvCyclesEnter) on the main thread: class P, W kept inside a
        /// writer. Pair with LeaveP on the same thread.</summary>
        internal static void EnterP()
        {
            if (Thread.CurrentThread.ManagedThreadId != MainThread) return;
            Push(_cls == ClsW ? ClsW : ClsP);
        }

        internal static void LeaveP()
        {
            if (Thread.CurrentThread.ManagedThreadId != MainThread) return;
            Pop();
        }

        /// <summary>A PhotonPeer entry (FtPhoton's X prefix): class X, W kept inside a writer. Returns the class stack's
        /// depth to restore (Leave), or -1 off the main thread, where nothing moves.</summary>
        internal static int EnterX()
        {
            if (Thread.CurrentThread.ManagedThreadId != MainThread) { Interlocked.Increment(ref PhotonOffMain); return -1; }
            int d = _sd;
            Push(_cls == ClsW ? ClsW : ClsX);
            return d;
        }

        /// <summary>A LoadBalancingClient listener callback (FtPhoton's E prefix): E inside X, the class it found
        /// anywhere else. Returns the depth to restore, or -1 off the main thread.</summary>
        internal static int EnterListener()
        {
            if (Thread.CurrentThread.ManagedThreadId != MainThread) { Interlocked.Increment(ref PhotonOffMain); return -1; }
            int d = _sd;
            Push(_cls == ClsX && !MutantK3 ? ClsE : _cls);
            return d;
        }

        /// <summary>Main thread: the X and listener finalizers that found the class stack not exactly one above the depth
        /// their prefix found (an inner scope left open, or the stack already below the scope's own level).</summary>
        internal static long LeaveMismatch;

        /// <summary>The finalizer of an X or listener scope: the class stack back to the depth its prefix found; a stack
        /// at any other height than the scope's own counts once in LeaveMismatch.</summary>
        internal static void Leave(int d)
        {
            if (d < 0) return;
            if (_sd != d + 1) LeaveMismatch++;
            while (_sd > d) Pop();
        }

        internal const long PlantUs = 2000;
        internal const int PlantTries = 3;   // a plant's read pass runs at most this often: again when a spin did not complete
        /// <summary>K2, the boot line `[FRAME-TIME] scope plant asked=<us> got=<us>`: a spin of PlantUs of the main
        /// thread's own cycle time (SpinCycles) inside a gated scope (Open, class S), and the cycles class S gained, in
        /// microseconds at f_hat (NA: f_hat unknown, or no completed pass). FtClock.OnStart, at the first frame boundary.</summary>
        internal static void PlantScope()
        {
            // One unread pass of ScopeGain (below) first, so that code compiled or initialised at its first call is
            // not in the reading. Then the control's pass, its spin on the thread's own cycle counter, the clock class
            // S is read in. A pass whose spin did not complete is not read: it is run again, PlantTries passes at
            // most, and a plant without a completed pass prints NA (R6-A3.11.162; numbers at FtPhoton.PlantNest).
            bool ok; long got = ScopeGain(0, out ok);
            for (int t = 0; ; t++) { got = ScopeGain(PlantUs, out ok); if (ok || t + 1 >= PlantTries) break; }

            Plugin.Log.LogInfo("[FRAME-TIME] scope plant asked=" + PlantUs + " got=" + (ok ? Us(got) : "NA"));
        }

        /// <summary>Busy-waits us microseconds of Stopwatch time on the calling thread.</summary>
        internal static void Spin(long us)
        {
            long n = us * Stopwatch.Frequency / 1000000;
            long t0 = Stopwatch.GetTimestamp();
            while (Stopwatch.GetTimestamp() - t0 < n) { }
        }

        /// <summary>Busy-waits until the calling thread's own cycle counter (FtClock.Cycles, the clock the classes are
        /// read in) has advanced by us microseconds at f_hat, and returns true when this loop read that advance (also
        /// for us at or below 0, which spins nothing). In every other case it returns false and the length of the
        /// spin is not known: f_hat is unknown or the first counter read fails (it then spins us of Stopwatch time,
        /// Spin); a later read fails or is below the first; us is above one second (nothing is spun); or 50 times us
        /// of Stopwatch time has passed. The loop checks that limit on each of its own passes, so a counter that
        /// stands still cannot hold a running thread longer; a thread that is not running does not check.</summary>
        internal static bool SpinCycles(long us)
        {
            if (us <= 0) return true;
            if (us > 1000000) return false;
            long f = FtCalib.FHat;
            ulong c0 = FtClock.Cycles();
            if (f <= 0 || c0 == 0) { Spin(us); return false; }
            ulong n = (ulong)(us * f / 1000000);
            long t0 = Stopwatch.GetTimestamp(), lim = 50 * us * Stopwatch.Frequency / 1000000;
            for (;;)
            {
                ulong c = FtClock.Cycles();
                if (c == 0 || c < c0) return false;
                if (c - c0 >= n) return true;
                if (Stopwatch.GetTimestamp() - t0 >= lim) return false;
            }
        }

        /// <summary>One pass of K2's path: a gated scope (Open, class S) around SpinCycles(us), and the cycles class S
        /// gained; ok is SpinCycles' answer. The class state is restored after.</summary>
        private static long ScopeGain(long us, out bool ok)
        {
            var st = Save();
            long s0 = Acc[ClsS];
            bool sp = Open(Cal, Gated);
            ok = SpinCycles(us);
            Close(sp);
            long got = Acc[ClsS] - s0;
            Restore(st);
            return got;
        }

        /// <summary>Cycles as whole microseconds at f_hat, or NA while f_hat is unknown.</summary>
        internal static string Us(long cyc)
        {
            long f = FtCalib.FHat;
            return f > 0 ? ((long)System.Math.Round(cyc * 1000000.0 / f)).ToString() : "NA";
        }

        /// <summary>Sum of arr over the seven components (not Cal) and both phases, for one moment and kind.</summary>
        internal static long Sum(long[] arr, int moment, int kind)
        {
            long s = 0;
            for (int c = 0; c < Cal; c++)
                for (int p = 0; p < Phases; p++) s += arr[Index(c, moment, p, kind)];
            return s;
        }

        /// <summary>The class stack must be empty at every frame boundary; FT_Start checks it (VR2).</summary>
        internal static int Depth => _sd;

        internal static void Reset()
        {
            for (int i = 0; i < Ticks.Length; i++) { Ticks[i] = 0; Calls[i] = 0; }
        }
    }
}
#endif
