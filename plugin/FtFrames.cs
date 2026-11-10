#if SCR_FRAMETIME
using System;
using System.Text;

namespace CompetitiveRounds
{
    internal static partial class FtClock
    {
        static partial void OnFrameClosed(long f, long s, ulong c, ulong p, int gc0, int gc1, bool ended, bool closing)
        {
            FtFrames.Frame(f, s, c, p, gc0, gc1, ended, closing);
        }
    }

    /// <summary>FrameTime M2 and M7 (METHOD-V4.md 3.1), first form: per-point and
    /// per-window integer sums of the measured live frames. A point's measured frames
    /// start at its second live frame (the first carries the arm switch and the zero-state
    /// check) and end at its last full live frame: the point's closing frame (combat ended, or
    /// FtSchedule.GameOver ran, inside it; FtSchedule.ClosingFrame) is excluded and counted (excl on the point line). sP and psP are the process's cycles over all threads
    /// (unplanted and planted frames). At the next point's start in the same game a between line
    /// gives the between-point spans' ticks and calls since this point ended, with this point's arm
    /// (V4 3.9: between-point costs are reported from transitions after ON points). Every 120 measured frames a window line;
    /// at each point end a point line. A full window also carries medF, the lower median of
    /// its frames 3 to 120, and for H = 4, 8 and 16 ms the run-count bounds k_min,k_max
    /// (METHOD-V4.md 3.8, F07): a frame is long when F - medF >= H + 2 ticks, short when
    /// F - medF < H - 2, uncertain otherwise; an event is a run of long frames inside the
    /// window; a two-state pass gives the least and greatest run count over every
    /// assignment of the uncertain frames, the frame before frame 3 counting as short. A
    /// partial window is logged and kept in the sums, not in the event counts. A window is
    /// wholly planted or not (FtPlant, M5): its line says plant=0|1, and the point line
    /// carries the unplanted sums (n, sF, sS, sC) and the planted ones (pn, psF, psS, psC)
    /// apart, with plant_mixed counting frames whose plant state differs from their
    /// window's first frame (0 by construction; VR2). At the end of the session's first
    /// OFF point with a full unplanted window, c_plant is fixed at round(0.03 x its mean F).
    /// The point line also carries the point's census and span totals (live moment):
    /// span_g/span_gn the gated spans' ticks and calls, span_u/span_un the upkeep spans',
    /// on_calls the census calls with the gate clear and guarded the guarded returns. At a
    /// gated point span_g, span_gn and on_calls are 0 by construction (VR5). zs and zl are
    /// the point's zero-state result (FtZero); t0 and t1 the Stopwatch ticks at the point's
    /// first live frame boundary and at its end (B3: the hashing job's interval against them).</summary>
    internal static class FtFrames
    {
        internal const int W = 120;

        private static readonly long[] WinF = new long[W];
        private static readonly long[] Sorted = new long[W - 2];
        private static readonly int[] HMs = { 4, 8, 16 };
        private static int _wn;
        private static long _wF, _wS, _wMaxF;
        private static ulong _wC;
        private static int _wGc0, _wGc1;
        private static ulong _wP, _pP, _qP;   // process cycles, all threads: window, unplanted and planted point sums
        private static long _excl;            // a point's closing (partial) live frames, excluded
        private static long _btT0 = -1, _btC0;    // between-point span sums at the last point end (-1: none owed)
        private static string _btArm = "";
        private static int _windows;
        private static bool _wPlant;
        private static long _qn, _qF, _qS, _plantMixed;
        private static ulong _qC;
        private static long _g0, _gn0, _u0, _un0, _on0, _guard0;   // span and census sums at the point's start

        private static long _pn, _pF, _pS, _pMaxF, _pMissingEnd;
        internal static long LastN, LastSF;   // the last point's unplanted frames and F sum (FtMenu's base)
        private static ulong _pC;

        /// <summary>Frame f closed; FtSchedule still holds frame f's state.</summary>
        internal static void Frame(long f, long s, ulong c, ulong p, int gc0, int gc1, bool ended, bool closing)
        {
            if (!FtSchedule.Live || FtSchedule.LiveFrame < 2) return;
            if (closing) { _excl++; return; }   // combat ended inside this frame: partial, never measured
            if (!ended) _pMissingEnd++;
            if (_wn == 0) { _wGc0 = gc0; _wPlant = FtPlant.Now; }
            else if (FtPlant.Now != _wPlant) _plantMixed++;
            _wGc1 = gc1;
            WinF[_wn++] = f;
            _wF += f; _wS += s; _wC += c; _wP += p;
            if (f > _wMaxF) _wMaxF = f;
            if (_wPlant) { _qn++; _qF += f; _qS += s; _qC += c; _qP += p; }
            else { _pn++; _pF += f; _pS += s; _pC += c; _pP += p; }
            if (f > _pMaxF) _pMaxF = f;
            if (_wn == W) FlushWindow(false);
        }

        private static long _t0;   // Stopwatch ticks at the point's first live frame boundary (B3's interval)

        private static long BetweenTicks()
        {
            return FtSpan.Sum(FtSpan.Ticks, FtSpan.Between, FtSpan.Gated) + FtSpan.Sum(FtSpan.Ticks, FtSpan.Between, FtSpan.Upkeep)
                + FtSpan.Sum(FtSpan.Ticks, FtSpan.Pick, FtSpan.Gated) + FtSpan.Sum(FtSpan.Ticks, FtSpan.Pick, FtSpan.Upkeep);
        }

        private static long BetweenCalls()
        {
            return FtSpan.Sum(FtSpan.Calls, FtSpan.Between, FtSpan.Gated) + FtSpan.Sum(FtSpan.Calls, FtSpan.Between, FtSpan.Upkeep)
                + FtSpan.Sum(FtSpan.Calls, FtSpan.Pick, FtSpan.Gated) + FtSpan.Sum(FtSpan.Calls, FtSpan.Pick, FtSpan.Upkeep);
        }

        /// <summary>A game ends (the owed between line is dropped: game-over work is the game's, not a transition's).</summary>
        internal static void GameBoundary() { _btT0 = -1; }

        internal static void StartPoint()
        {
            if (_btT0 >= 0)
                Plugin.Log.LogInfo("[FRAME-TIME] between g=" + FtSchedule.Game + " after=" + _btArm + " ticks=" + (BetweenTicks() - _btT0)
                    + " calls=" + (BetweenCalls() - _btC0));
            _btT0 = -1;
            _wn = 0; _wF = 0; _wS = 0; _wC = 0; _wMaxF = 0; _wP = 0;
            _pn = 0; _pF = 0; _pS = 0; _pC = 0; _pMaxF = 0; _pMissingEnd = 0; _pP = 0; _excl = 0;
            _qn = 0; _qF = 0; _qS = 0; _qC = 0; _plantMixed = 0; _qP = 0;
            _g0 = FtSpan.Sum(FtSpan.Ticks, FtSpan.Live, FtSpan.Gated);
            _gn0 = FtSpan.Sum(FtSpan.Calls, FtSpan.Live, FtSpan.Gated);
            _u0 = FtSpan.Sum(FtSpan.Ticks, FtSpan.Live, FtSpan.Upkeep);
            _un0 = FtSpan.Sum(FtSpan.Calls, FtSpan.Live, FtSpan.Upkeep);
            _on0 = FtCensus.SumOn();
            _guard0 = FtCensus.SumGuarded();
            _windows = 0;
            _t0 = System.Diagnostics.Stopwatch.GetTimestamp();
        }

        internal static void EndPoint()
        {
            if (_wn > 0) FlushWindow(true);
            Plugin.Log.LogInfo("[FRAME-TIME] p pt=" + FtSchedule.Label() + " arm=" + (FtSchedule.ArmOn ? "ON" : "OFF")
                + " gate=" + (FtSchedule.GateThisPoint ? 1 : 0)
                + " pred=" + (FtSchedule.PrevArm < 0 ? "none" : FtSchedule.PrevArm == 1 ? "ON" : "OFF")
                + " n=" + _pn + " sF=" + _pF + " sS=" + _pS + " sC=" + _pC + " maxF=" + _pMaxF
                + " pn=" + _qn + " psF=" + _qF + " psS=" + _qS + " psC=" + _qC + " sP=" + _pP + " psP=" + _qP
                + " excl=" + _excl + " plant_mixed=" + _plantMixed
                + " windows=" + _windows + " live_frames=" + FtSchedule.LiveFrame + " missing_end=" + _pMissingEnd
                + " span_g=" + (FtSpan.Sum(FtSpan.Ticks, FtSpan.Live, FtSpan.Gated) - _g0)
                + " span_gn=" + (FtSpan.Sum(FtSpan.Calls, FtSpan.Live, FtSpan.Gated) - _gn0)
                + " span_u=" + (FtSpan.Sum(FtSpan.Ticks, FtSpan.Live, FtSpan.Upkeep) - _u0)
                + " span_un=" + (FtSpan.Sum(FtSpan.Calls, FtSpan.Live, FtSpan.Upkeep) - _un0)
                + " on_calls=" + (FtCensus.SumOn() - _on0) + " guarded=" + (FtCensus.SumGuarded() - _guard0)
                + " zs=" + FtZero.Mask + " zl=" + FtZero.LateSeen
                + " t0=" + _t0 + " t1=" + System.Diagnostics.Stopwatch.GetTimestamp() + " answer=" + FtReplay.AnswerField);
            LastN = _pn;
            LastSF = _pF;
            _btT0 = BetweenTicks();
            _btC0 = BetweenCalls();
            _btArm = FtSchedule.ArmOn ? "ON" : "OFF";
            if (FtPlant.Us < 0 && FtSchedule.Game >= 0 && !FtSchedule.ArmOn && _pn >= W)
                FtPlant.Fix((long)Math.Round(0.03 * _pF * 1000000.0 / ((double)_pn * System.Diagnostics.Stopwatch.Frequency)),
                    FtSchedule.Label());
        }

        private static void FlushWindow(bool partial)
        {
            _windows++;
            var sb = new StringBuilder(160);
            sb.Append("[FRAME-TIME] w pt=").Append(FtSchedule.Label()).Append(" arm=").Append(FtSchedule.ArmOn ? "ON" : "OFF")
              .Append(" plant=").Append(_wPlant ? 1 : 0).Append(" partial=").Append(partial ? 1 : 0).Append(" n=").Append(_wn).Append(" sF=").Append(_wF)
              .Append(" sS=").Append(_wS).Append(" sC=").Append(_wC).Append(" sP=").Append(_wP).Append(" maxF=").Append(_wMaxF);
            if (!partial)
            {
                long med = LowerMedian();
                sb.Append(" medF=").Append(med);
                for (int h = 0; h < HMs.Length; h++)
                {
                    long ticks = HMs[h] * System.Diagnostics.Stopwatch.Frequency / 1000;
                    int kmin, kmax;
                    RunBounds(med, ticks, out kmin, out kmax);
                    sb.Append(" e").Append(HMs[h]).Append('=').Append(kmin).Append(',').Append(kmax);
                }
            }
            sb.Append(" gc=").Append(_wGc1 - _wGc0);   // first measured frame's start to the last one's end
            Plugin.Log.LogInfo(sb.ToString());
            _wn = 0; _wF = 0; _wS = 0; _wC = 0; _wMaxF = 0; _wP = 0;
        }

        /// <summary>The lower median of frames 3 to 120 of a full window: s[(n + 1) / 2 - 1], n = 118.</summary>
        internal static long LowerMedian()
        {
            Array.Copy(WinF, 2, Sorted, 0, W - 2);
            Array.Sort(Sorted);
            return Sorted[(Sorted.Length + 1) / 2 - 1];
        }

        /// <summary>k_min and k_max over frames 3 to 120 for threshold h ticks above med.</summary>
        internal static void RunBounds(long med, long h, out int kmin, out int kmax)
        {
            const int None = int.MinValue;
            int minS = 0, maxS = 0, minL = None, maxL = None;   // runs so far, ending short or long
            for (int i = 2; i < W; i++)
            {
                long d = WinF[i] - med;
                bool canLong = d >= h - 2;
                bool canShort = d < h + 2;
                int nMinS = None, nMaxS = None, nMinL = None, nMaxL = None;
                if (canShort)
                {
                    nMinS = Min(minS, minL);
                    nMaxS = Max(maxS, maxL);
                }
                if (canLong)
                {
                    nMinL = Min(minS == None ? None : minS + 1, minL);
                    nMaxL = Max(maxS == None ? None : maxS + 1, maxL);
                }
                minS = nMinS; maxS = nMaxS; minL = nMinL; maxL = nMaxL;
            }
            kmin = Min(minS, minL);
            kmax = Max(maxS, maxL);
        }

        private static int Min(int a, int b)
        {
            const int None = int.MinValue;
            if (a == None) return b;
            if (b == None) return a;
            return a < b ? a : b;
        }

        private static int Max(int a, int b)
        {
            return a > b ? a : b;
        }
    }
}
#endif
