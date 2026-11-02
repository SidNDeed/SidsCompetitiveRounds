#if SCR_FRAMETIME
using System;
using System.Text;

namespace CompetitiveRounds
{
    internal static partial class FtClock
    {
        static partial void OnFrameClosed(long f, long s, ulong c, bool ended)
        {
            FtFrames.Frame(f, s, c, ended);
        }
    }

    /// <summary>FrameTime M2 and M7 (METHOD-V4.md 3.1), first form: per-point and
    /// per-window integer sums of the measured live frames. A point's measured frames
    /// start at its second live frame (the first carries the arm switch and the zero-state
    /// check) and end at its last full live frame. Every 120 measured frames a window line;
    /// at each point end a point line. Still to come in part 3: medF and the run-count
    /// bounds e4/e8/e16 (k_min,k_max by the two-state pass over the window's 118 stored
    /// frames, F07), the plant (M5) with its planted sums, the zero-state result and the
    /// census and span totals on the point line. The window's frame values are already
    /// stored for that pass.</summary>
    internal static class FtFrames
    {
        internal const int W = 120;
        internal static long CPlant = -1;

        private static readonly long[] WinF = new long[W];
        private static int _wn;
        private static long _wF, _wS, _wMaxF;
        private static ulong _wC;
        private static int _wGc;
        private static int _windows;

        private static long _pn, _pF, _pS, _pMaxF, _pMissingEnd;
        private static ulong _pC;

        /// <summary>Frame f closed; FtSchedule still holds frame f's state.</summary>
        internal static void Frame(long f, long s, ulong c, bool ended)
        {
            if (!FtSchedule.Live || FtSchedule.LiveFrame < 2) return;
            if (!ended) _pMissingEnd++;
            if (_wn == 0) _wGc = GC.CollectionCount(0);
            WinF[_wn++] = f;
            _wF += f; _wS += s; _wC += c;
            if (f > _wMaxF) _wMaxF = f;
            _pn++; _pF += f; _pS += s; _pC += c;
            if (f > _pMaxF) _pMaxF = f;
            if (_wn == W) FlushWindow(false);
        }

        internal static void StartPoint()
        {
            _wn = 0; _wF = 0; _wS = 0; _wC = 0; _wMaxF = 0;
            _pn = 0; _pF = 0; _pS = 0; _pC = 0; _pMaxF = 0; _pMissingEnd = 0;
            _windows = 0;
        }

        internal static void EndPoint()
        {
            if (_wn > 0) FlushWindow(true);
            Plugin.Log.LogInfo("[FRAME-TIME] p pt=" + FtSchedule.Label() + " arm=" + (FtSchedule.ArmOn ? "ON" : "OFF")
                + " gate=" + (FtSchedule.GateThisPoint ? 1 : 0)
                + " pred=" + (FtSchedule.PrevArm < 0 ? "none" : FtSchedule.PrevArm == 1 ? "ON" : "OFF")
                + " n=" + _pn + " sF=" + _pF + " sS=" + _pS + " sC=" + _pC + " maxF=" + _pMaxF
                + " windows=" + _windows + " live_frames=" + FtSchedule.LiveFrame + " missing_end=" + _pMissingEnd);
        }

        private static void FlushWindow(bool partial)
        {
            _windows++;
            Plugin.Log.LogInfo("[FRAME-TIME] w pt=" + FtSchedule.Label() + " arm=" + (FtSchedule.ArmOn ? "ON" : "OFF")
                + " partial=" + (partial ? 1 : 0) + " n=" + _wn + " sF=" + _wF + " sS=" + _wS + " sC=" + _wC
                + " maxF=" + _wMaxF + " gc=" + (GC.CollectionCount(0) - _wGc));
            _wn = 0; _wF = 0; _wS = 0; _wC = 0; _wMaxF = 0;
        }
    }
}
#endif
