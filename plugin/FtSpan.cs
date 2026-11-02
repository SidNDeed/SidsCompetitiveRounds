#if SCR_FRAMETIME
using System.Diagnostics;
using System.Runtime.CompilerServices;

namespace CompetitiveRounds
{
    /// <summary>FrameTime M4 (METHOD-V4.md 3.1): outermost spans. A depth counter opens a
    /// span only at depth 0, so work one component does inside another's span is counted
    /// once (HIGH 7). Span time (Stopwatch ticks) and calls accumulate per component, per
    /// moment, per phase (inside or outside the script phase FT_Start..FT_End) and per
    /// kind: GATED (the gate removes it at OFF points), UPKEEP (class iii upkeep, runs in
    /// both arms, F13) and REPLAY (F18 reading A, reported separately). Stated as elapsed
    /// time inside the spans: an upper bound on their own CPU time, used for the census,
    /// absorption (VR9) and placement (B3), never as the B1 estimate.
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
        internal const int Gated = 0, Upkeep = 1, Replay = 2;
        internal const int Kinds = 3;
        internal static readonly string[] KindNames = { "gated", "upkeep", "replay" };

        internal const int Phases = 2; // 0 inside the script phase, 1 outside

        internal static int Moment = Menu;

        internal static readonly long[] Ticks = new long[Components * Moments * Phases * Kinds];
        internal static readonly long[] Calls = new long[Components * Moments * Phases * Kinds];

        private static int _depth;
        private static int _component;
        private static int _kind;
        private static long _t0;

        internal static int Index(int component, int moment, int phase, int kind)
        {
            return ((component * Moments + moment) * Phases + phase) * Kinds + kind;
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        internal static bool Open(int component, int kind)
        {
            if (_depth++ != 0) return false;
            _component = component;
            _kind = kind;
            _t0 = Stopwatch.GetTimestamp();
            return true;
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        internal static void Close(bool opened)
        {
            _depth--;
            if (!opened) return;
            long dt = Stopwatch.GetTimestamp() - _t0;
            int i = Index(_component, Moment, FtClock.InScript ? 0 : 1, _kind);
            Ticks[i] += dt;
            Calls[i]++;
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
