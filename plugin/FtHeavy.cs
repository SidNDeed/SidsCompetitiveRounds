#if SCR_FRAMETIME
using System.Diagnostics;
using System.Text;
using System.Threading;

namespace CompetitiveRounds
{
    /// <summary>FrameTime B3 (METHOD-V4.md 3.9), placement: every heavy operation is counted by the
    /// moment of the frame it ran in. Heavy, by operation (V4 3.9): the record builds
    /// (CombatEvidence.BuildCaptures, SeatEvidence.BuildCaptures, CardDrawEvidence.BuildPending,
    /// IdentityClockEvidence.BuildEnv), queue writes (SeatEvidence.Enqueue for every route, and
    /// SpoolClosing on the closing path), the upload pump, answers, the start of the hashing thread
    /// and a hash completed on the main thread. Every main-thread call also reads CombatLive itself,
    /// whatever the frame's moment says (a stale non-live moment cannot hide a live call): at_call
    /// counts calls with combat live at the call; edge counts calls in a frame that started live and
    /// whose combat ended before the call. V4 3.9's rule is that no heavy work runs in a live-combat
    /// frame, so B3 judges both (round-1 MEDIUM, FtHeavy.cs:39). The
    /// hashing thread's run is stamped (Stopwatch ticks) so the parser can test its interval against
    /// every point's live interval. Main thread only; a call from another thread is counted as off.</summary>
    internal static class FtHeavy
    {
        internal const int CeBuild = 0, SeBuild = 1, CdBuild = 2, IcBuild = 3, Enqueue = 4, Spool = 5, Pump = 6,
            Answer = 7, HashStart = 8, HashNow = 9;
        internal const int Ops = 10;
        internal static readonly string[] Names =
            { "ce_build", "se_build", "cd_build", "ic_build", "enqueue", "spool", "pump", "answer", "hash_start", "hash_now" };

        private static readonly long[] _byMoment = new long[Ops * FtSpan.Moments];
        private static readonly long[] _atCall = new long[Ops];
        private static readonly long[] _edge = new long[Ops];
        private static readonly long[] _off = new long[Ops];

        // Written by the hashing thread (one job per process, SeatEvidence._hashStarted); read at game over.
        internal static long HashT0, HashT1;

        internal static void Mark(int op)
        {
            if (Thread.CurrentThread.ManagedThreadId != FtSpan.MainThread) { Interlocked.Increment(ref _off[op]); return; }
            int m = FtSpan.Moment;
            _byMoment[op * FtSpan.Moments + m]++;
            bool live = true;
            try { live = SeatEvidence.CombatLive(); } catch { }
            if (live) _atCall[op]++;
            else if (m == FtSpan.Live) _edge[op]++;
        }

        internal static void HashBegin() { Interlocked.Exchange(ref HashT0, Stopwatch.GetTimestamp()); }

        internal static void HashDone() { Interlocked.Exchange(ref HashT1, Stopwatch.GetTimestamp()); }

        internal static void Reset()
        {
            for (int i = 0; i < _byMoment.Length; i++) _byMoment[i] = 0;
            for (int i = 0; i < Ops; i++) { _atCall[i] = 0; _edge[i] = 0; Interlocked.Exchange(ref _off[i], 0); }
        }

        /// <summary>At game over: one heavy line per operation, then the off-thread line.</summary>
        internal static void LogGame(int game)
        {
            for (int op = 0; op < Ops; op++)
            {
                var sb = new StringBuilder(160);
                sb.Append("[FRAME-TIME] heavy g=").Append(game).Append(" op=").Append(Names[op]);
                for (int m = 0; m < FtSpan.Moments; m++)
                    sb.Append(' ').Append(FtSpan.MomentNames[m]).Append('=').Append(_byMoment[op * FtSpan.Moments + m]);
                sb.Append(" at_call=").Append(_atCall[op]).Append(" edge=").Append(_edge[op])
                  .Append(" off=").Append(Interlocked.Read(ref _off[op]));
                Plugin.Log.LogInfo(sb.ToString());
            }
            Plugin.Log.LogInfo("[FRAME-TIME] offthread g=" + game + " span_off=" + FtSpan.OffThread
                + " hash_t0=" + Interlocked.Read(ref HashT0) + " hash_t1=" + Interlocked.Read(ref HashT1));
        }
    }
}
#endif
