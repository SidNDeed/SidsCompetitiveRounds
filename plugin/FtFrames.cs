#if SCR_FRAMETIME
using System;
using System.Text;

namespace CompetitiveRounds
{
    internal static partial class FtClock
    {
        static partial void OnFrameClosed(long f, long s, ulong c, ulong p, int gc0, int gc1, bool ended, bool closing,
            long cg, bool gok, long cw, long cr, long cs, long ce)
        {
            FtFrames.Frame(f, s, c, p, gc0, gc1, ended, closing, cg, gok, cw, cr, cs, ce);
        }
    }

    /// <summary>FrameTime M2 and M7 (METHOD-V4.md 3.1), first form: per-point and
    /// per-window integer sums of the measured live frames. A point's measured frames
    /// start at its second live frame (the first carries the arm switch and the zero-state
    /// check) and end at its last full live frame: the point's closing frame (combat ended, or
    /// FtSchedule.GameOver or MatchEnded ran, inside it; FtSchedule.ClosingFrame) is excluded and
    /// counted (excl on the point line). A point FtSchedule ends mid-frame (GameStart, the quit
    /// flush) leaves that partial frame out of every sum without counting it in excl, since its
    /// line is written before the frame closes. sP and psP are the process's cycles over all threads
    /// (unplanted and planted frames). At the next point's start in the same game a between line
    /// gives the between-point spans' ticks and calls since this point ended, with the arm of this point's
    /// last window. Every 120 measured frames a window line;
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
    /// point with a full unplanted OFF window, c_plant is fixed at round(0.03 x the mean F of its full unplanted
    /// OFF windows).
    /// The point line also carries the point's census and span totals (live moment):
    /// span_g/span_gn the gated spans' ticks and calls, span_u/span_un the upkeep spans',
    /// on_calls the census calls with the gate clear and guarded the guarded returns, and the same split by the
    /// frame's gate (VR5 per window): off_g/off_gn/off_on the gated spans' ticks and calls and the census calls in
    /// frames the gate held, on_guarded the guarded returns in frames it did not; VR5 needs off_g, off_gn, off_on
    /// and on_guarded 0. zs and zl are
    /// the point's zero-state result (FtZero); t0 and t1 the Stopwatch ticks at the point's
    /// first live frame boundary and at its end (B3: the hashing job's interval against them).
    ///
    /// OWNERSHIP (B11 SHARED.md): every line is written from its owner as captured when it opened, never from the
    /// schedule's state at the time of writing. A point's owner (label, its first window's arm, gate and pred) is
    /// captured at StartPoint; a window's (label, wi, f0, arm, pred, unit, run, pos, coin, plant run, res) when its
    /// first measured frame closes, which is the schedule's state for that frame. A frame whose schedule window differs
    /// from the open window's owner first writes that window as partial (own_split on the point line counts it; 0 by
    /// construction). EndPoint writes a point once: a second call before the next StartPoint does nothing.
    ///
    /// RECORDS (method-v54.md (a); ruling R6-A3.11.138 (5); SHARED.md's window line): the window line appends run,
    /// pos, unit, coin, wi, f0, pred, plant (the plant run), res, partial, gcn (collections), the partition cG (NA
    /// unless every frame's G is known), cW, cR, cS, cE, and per 12-frame bin j = floor(i/12) + 1 of the window's frame
    /// i: q (C - G - W), r (R) and qn (frames), then the writer ledger's wu and tok over the window (FtLedger). Every
    /// c*, q and r is in main-thread executed cycles (QueryThreadCycleTime). By construction sC = cG + cW + cR + cS +
    /// cE (cG as 0 when NA), sum(q) = sC - cG - cW, sum(r) = cR, sum(qn) = n.</summary>
    internal static class FtFrames
    {
        internal const int W = 120;
        internal const int Bin = 12, Bins = W / Bin;

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

        // the partition's window sums and bins (cycles)
        private static long _wG, _wW, _wR, _wS2, _wE;
        private static bool _wGok;
        private static readonly long[] _tq = new long[Bins], _tr = new long[Bins], _tn = new long[Bins];

        // the writer ledger: at the window's start, and after its last measured frame
        private static readonly long[] _lb = new long[FtLedger.Fields], _le = new long[FtLedger.Fields];

        // the window's owner, captured when its first measured frame closes
        private static string _oPt = "";
        private static long _oK, _oRun, _oF0;
        private static int _oPos, _oCoin, _oPred, _oGame, _oRound, _oPoint;
        private static bool _oArm, _oP24, _oPlantRun, _oRes;

        // the point's owner, captured at StartPoint
        private static bool _ptOpen;
        private static string _ptLabel = "";
        private static bool _ptArm, _ptGate, _ptLastArm;
        private static int _ptPred;
        private static long _ownSplit;

        // VR5 by the frame's gate: the sums at the last attribution, and the point's off/on parts
        private static long _vG, _vGn, _vOn, _vGd;
        private static long _offG, _offGn, _offOn, _onGuarded;

        // c_plant's source: the point's full unplanted OFF windows
        private static long _offN, _offF;

        private static long _pn, _pF, _pS, _pMaxF, _pMissingEnd;
        internal static long LastN, LastSF;   // the last point's unplanted frames and F sum (FtMenu's base)
        private static ulong _pC;

        /// <summary>Frame f closed; FtSchedule still holds frame f's state, and FtGate.Off frame f's gate.</summary>
        internal static void Frame(long f, long s, ulong c, ulong p, int gc0, int gc1, bool ended, bool closing,
            long cg, bool gok, long cw, long cr, long cs, long ce)
        {
            if (!FtSchedule.Live) return;
            Vr5Take(FtGate.Off);
            if (FtSchedule.LiveFrame < 2)
            {
                FtLedger.Take(_lb);   // the point's first live frame closed: window 0 starts with the next frame
                return;
            }
            if (closing) { _excl++; return; }   // combat ended inside this frame: partial, never measured
            if (_wn > 0 && (CurrentK() != _oK || FtSchedule.Game != _oGame || FtSchedule.Round != _oRound || FtSchedule.PointInRound != _oPoint))
            {
                _ownSplit++;
                FlushWindow(true);
            }
            if (!ended) _pMissingEnd++;
            if (_wn == 0) { _wGc0 = gc0; _wPlant = FtPlant.Now; CaptureOwner(); }
            else if (FtPlant.Now != _wPlant) _plantMixed++;
            _wGc1 = gc1;
            int bin = _wn / Bin;
            WinF[_wn++] = f;
            _wF += f; _wS += s; _wC += c; _wP += p;
            if (f > _wMaxF) _wMaxF = f;
            if (_wPlant) { _qn++; _qF += f; _qS += s; _qC += c; _qP += p; }
            else { _pn++; _pF += f; _pS += s; _pC += c; _pP += p; }
            if (f > _pMaxF) _pMaxF = f;
            if (!gok) _wGok = false;
            _wG += cg; _wW += cw; _wR += cr; _wS2 += cs; _wE += ce;
            _tq[bin] += unchecked((long)c) - cg - cw;
            _tr[bin] += cr;
            _tn[bin]++;
            FtLedger.Take(_le);
            if (_wn == W) FlushWindow(false);
        }

        /// <summary>The schedule's window index for the frame now closing (the menu self-check's from its live frame).</summary>
        private static long CurrentK()
        {
            return FtMenu.Active ? (FtSchedule.LiveFrame - 2) / W : FtSchedule.WinK;
        }

        private static void CaptureOwner()
        {
            _oPt = FtSchedule.Label();
            _oGame = FtSchedule.Game; _oRound = FtSchedule.Round; _oPoint = FtSchedule.PointInRound;
            _oK = CurrentK();
            _oF0 = FtSchedule.LiveFrame;
            _oArm = FtSchedule.ArmOn;
            if (FtMenu.Active)
            {
                // a menu segment holds one arm: its windows follow position by index, with no coin of their own
                _oRun = _oK / 4; _oPos = (int)(_oK % 4) + 1; _oP24 = (_oK & 1) == 1; _oCoin = _oArm ? 1 : 0;
                _oPred = _oK == 0 ? FtSchedule.PrevArm : (_oArm ? 1 : 0);
                _oPlantRun = false; _oRes = false;
            }
            else
            {
                _oRun = FtSchedule.WinRun; _oPos = FtSchedule.WinPos; _oP24 = FtSchedule.WinP24; _oCoin = FtSchedule.WinCoin;
                _oPred = FtSchedule.PrevArm; _oPlantRun = FtSchedule.WinPlant; _oRes = FtSchedule.WinRes;
            }
            _ptLastArm = _oArm;
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

        /// <summary>The live gated spans and census counts since the last attribution go to the gate they ran under.</summary>
        private static void Vr5Take(bool off)
        {
            long g = FtSpan.Sum(FtSpan.Ticks, FtSpan.Live, FtSpan.Gated);
            long gn = FtSpan.Sum(FtSpan.Calls, FtSpan.Live, FtSpan.Gated);
            long on = FtCensus.SumOn();
            long gd = FtCensus.SumGuarded();
            if (off) { _offG += g - _vG; _offGn += gn - _vGn; _offOn += on - _vOn; }
            else _onGuarded += gd - _vGd;
            _vG = g; _vGn = gn; _vOn = on; _vGd = gd;
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
            ResetPartition();
            _pn = 0; _pF = 0; _pS = 0; _pC = 0; _pMaxF = 0; _pMissingEnd = 0; _pP = 0; _excl = 0;
            _qn = 0; _qF = 0; _qS = 0; _qC = 0; _plantMixed = 0; _qP = 0;
            _g0 = FtSpan.Sum(FtSpan.Ticks, FtSpan.Live, FtSpan.Gated);
            _gn0 = FtSpan.Sum(FtSpan.Calls, FtSpan.Live, FtSpan.Gated);
            _u0 = FtSpan.Sum(FtSpan.Ticks, FtSpan.Live, FtSpan.Upkeep);
            _un0 = FtSpan.Sum(FtSpan.Calls, FtSpan.Live, FtSpan.Upkeep);
            _on0 = FtCensus.SumOn();
            _guard0 = FtCensus.SumGuarded();
            _vG = _g0; _vGn = _gn0; _vOn = _on0; _vGd = _guard0;
            _offG = 0; _offGn = 0; _offOn = 0; _onGuarded = 0;
            _offN = 0; _offF = 0; _ownSplit = 0;
            _windows = 0;
            _ptLabel = FtSchedule.Label();
            _ptArm = FtSchedule.ArmOn;
            _ptGate = FtSchedule.GateThisPoint;
            _ptPred = FtSchedule.PrevArm;
            _ptLastArm = _ptArm;
            _ptOpen = true;
            FtLedger.Take(_lb);
            _t0 = System.Diagnostics.Stopwatch.GetTimestamp();
        }

        internal static void EndPoint()
        {
            if (!_ptOpen) return;
            _ptOpen = false;
            if (_wn > 0) FlushWindow(true);
            Vr5Take(FtGate.Off);
            Plugin.Log.LogInfo("[FRAME-TIME] p pt=" + _ptLabel + " arm=" + (_ptArm ? "ON" : "OFF")
                + " gate=" + (_ptGate ? 1 : 0)
                + " pred=" + Arm(_ptPred)
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
                + " t0=" + _t0 + " t1=" + System.Diagnostics.Stopwatch.GetTimestamp() + " answer=" + FtReplay.AnswerField
                + " off_g=" + _offG + " off_gn=" + _offGn + " off_on=" + _offOn + " on_guarded=" + _onGuarded
                + " own_split=" + _ownSplit + " span_class_overflow=" + FtSpan.ClassOverflow
                + " gc_read_failures=" + FtSpan.GcReadFailures);
            LastN = _pn;
            LastSF = _pF;
            _btT0 = BetweenTicks();
            _btC0 = BetweenCalls();
            _btArm = _ptLastArm ? "ON" : "OFF";
            if (FtPlant.Us < 0 && FtSchedule.Game >= 0 && _offN >= W)
                FtPlant.Fix((long)Math.Round(0.03 * _offF * 1000000.0 / ((double)_offN * System.Diagnostics.Stopwatch.Frequency)),
                    _ptLabel);
        }

        private static string Arm(int a)
        {
            return a < 0 ? "none" : a == 1 ? "ON" : "OFF";
        }

        private static void ResetPartition()
        {
            _wG = 0; _wW = 0; _wR = 0; _wS2 = 0; _wE = 0; _wGok = true;
            for (int j = 0; j < Bins; j++) { _tq[j] = 0; _tr[j] = 0; _tn[j] = 0; }
        }

        private static void FlushWindow(bool partial)
        {
            _windows++;
            if (!partial && !_oArm && !_wPlant) { _offN += _wn; _offF += _wF; }
            var sb = new StringBuilder(512);
            sb.Append("[FRAME-TIME] w pt=").Append(_oPt).Append(" arm=").Append(_oArm ? "ON" : "OFF")
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
            sb.Append(" run=").Append(_oRun).Append(" pos=").Append(_oPos).Append(" unit=").Append(_oP24 ? "P24" : "P13")
              .Append(" coin=").Append(_oCoin).Append(" wi=").Append(_oK).Append(" f0=").Append(_oF0)
              .Append(" pred=").Append(Arm(_oPred)).Append(" plant=").Append(_oPlantRun ? 1 : 0).Append(" res=").Append(_oRes ? 1 : 0)
              .Append(" partial=").Append(partial ? 1 : 0).Append(" gcn=").Append(_wGc1 - _wGc0).Append(" cG=");
            if (_wGok) sb.Append(_wG); else sb.Append("NA");
            sb.Append(" cW=").Append(_wW).Append(" cR=").Append(_wR).Append(" cS=").Append(_wS2).Append(" cE=").Append(_wE);
            AppendBins(sb, " q=", _tq);
            AppendBins(sb, " r=", _tr);
            AppendBins(sb, " qn=", _tn);
            sb.Append(" wu=");
            FtLedger.AppendWu(sb, _lb, _le);
            sb.Append(" tok=");
            FtLedger.AppendTok(sb, _lb, _le);
            Plugin.Log.LogInfo(sb.ToString());
            Array.Copy(_le, _lb, FtLedger.Fields);
            _wn = 0; _wF = 0; _wS = 0; _wC = 0; _wMaxF = 0; _wP = 0;
            ResetPartition();
        }

        private static void AppendBins(StringBuilder sb, string key, long[] v)
        {
            sb.Append(key);
            for (int j = 0; j < Bins; j++)
            {
                if (j > 0) sb.Append(',');
                sb.Append(v[j]);
            }
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
