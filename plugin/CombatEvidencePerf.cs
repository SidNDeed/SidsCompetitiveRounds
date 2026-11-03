using System;
using System.Globalization;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>A14, the combat evidence frame-time measurement (development only,
    /// off unless [Debug] CombatEvidencePerfProbe names a mode). It measures
    /// frame times on this seat in fixed windows of PERF_WINDOW_CAP frames and
    /// reports each window's median, 99th percentile and longest frame:
    ///
    ///  "menu"  : outside any room. Two identical windows (A/A: the harness's own
    ///            noise floor), then a PLANTED window that spends PLANT_MS of busy
    ///            time in every frame (the control: the harness must see a known
    ///            cost). Collectors are idle here (no game is open).
    ///  "match" : inside a ranked game while combat is live. Windows alternate A
    ///            (collectors on) and B (collectors suspended through
    ///            CombatEvidence.PerfSuspend); a game that ran a B window keeps no
    ///            combat record (its rows are incomplete).
    ///
    /// Nothing is sent; the report is the log's "[COMBAT-PERF]" lines.</summary>
    internal static class CombatEvidencePerf
    {
        internal const string TAG = "[COMBAT-PERF]";
        internal const int PERF_WINDOW_CAP = 600, BIN_US = 100, BIN_CAP = 1001, WINDOWS_CAP = 16;
        internal const double PLANT_MS = 2.0;

        private static bool _bound, _on, _done;
        private static string _mode = "off";
        private static readonly int[] _bins = new int[BIN_CAP];
        private static int _frames, _window, _warm;
        private static long _maxUs;
        private static readonly long[] _p50 = new long[WINDOWS_CAP], _p99 = new long[WINDOWS_CAP], _max = new long[WINDOWS_CAP];
        private static readonly string[] _label = new string[WINDOWS_CAP];
        private static int _reported;
        /// <summary>True from the first B window of a game until that game's capture is decided.</summary>
        internal static bool Contaminated;

        internal static string Mode { get { return _mode; } }

        private static void Bind()
        {
#if SCR_FRAMETIME
            FtA3.Read(FtA3.CE_perf_probe); FtA3.Wrote(FtA3.CE_perf_probe);
#endif
            _bound = true;
            try
            {
                var cf = Plugin.ConfigFileForLevers;
                if (cf == null) return;
                _mode = (cf.Bind("Debug", "CombatEvidencePerfProbe", "off",
                    "Development only: frame-time windows for the combat evidence (menu: A/A and a planted 2 ms control, outside rooms; match: alternating collectors on/off inside a ranked game, which then keeps no combat record). Nothing is sent.").Value ?? "off").Trim().ToLowerInvariant();
                _on = _mode == "menu" || _mode == "match";
                if (_on) Plugin.Log.LogWarning(TAG + " probe on, mode " + _mode + ", windows of " + PERF_WINDOW_CAP.ToString(CultureInfo.InvariantCulture) + " frames");
            }
            catch { _on = false; }
        }

        /// <summary>Once per frame from CombatEvidence.Tick (outside every collector).</summary>
        internal static void Frame()
        {
#if SCR_FRAMETIME
            FtA3.Read(FtA3.CE_perf_probe);
#endif
            if (!_bound) Bind();
            if (!_on || _done) return;
            long us = (long)(Time.unscaledDeltaTime * 1e6);
            if (_mode == "menu") MenuFrame(us);
            else MatchFrame(us);
        }

        private static void Add(long us)
        {
#if SCR_FRAMETIME
            FtA3.Read(FtA3.CE_perf_probe); FtA3.Wrote(FtA3.CE_perf_probe);
#endif
            if (us < 0) us = 0;
            _bins[(int)Math.Min(us / BIN_US, BIN_CAP - 1)]++;
            _frames++;
            if (us > _maxUs) _maxUs = us;
        }

        private static long Quantile(double q)
        {
#if SCR_FRAMETIME
            FtA3.Read(FtA3.CE_perf_probe);
#endif
            if (_frames == 0) return 0;
            long rank = (long)Math.Ceiling(q * _frames), acc = 0;
            if (rank < 1) rank = 1;
            for (int i = 0; i < BIN_CAP; i++) { acc += _bins[i]; if (acc >= rank) return (long)i * BIN_US + BIN_US / 2; }
            return _maxUs;
        }

        private static void Close(string label)
        {
#if SCR_FRAMETIME
            FtA3.Read(FtA3.CE_perf_probe); FtA3.Wrote(FtA3.CE_perf_probe);
#endif
            if (_window < WINDOWS_CAP)
            {
                _label[_window] = label; _p50[_window] = Quantile(0.5); _p99[_window] = Quantile(0.99); _max[_window] = _maxUs;
                try
                {
#if SCR_FRAMETIME
                    FtLog.LogInfo(TAG + " window " + (_window + 1).ToString(CultureInfo.InvariantCulture) + " " + label
#else
                    Plugin.Log.LogInfo(TAG + " window " + (_window + 1).ToString(CultureInfo.InvariantCulture) + " " + label
#endif
                        + " frames=" + _frames.ToString(CultureInfo.InvariantCulture)
                        + " p50_us=" + _p50[_window].ToString(CultureInfo.InvariantCulture)
                        + " p99_us=" + _p99[_window].ToString(CultureInfo.InvariantCulture)
                        + " max_us=" + _max[_window].ToString(CultureInfo.InvariantCulture));
                }
                catch { }
            }
            _window++;
            Array.Clear(_bins, 0, BIN_CAP); _frames = 0; _maxUs = 0;
        }

        private static void Spin(double ms)
        {
            long until = System.Diagnostics.Stopwatch.GetTimestamp() + (long)(ms / 1000.0 * System.Diagnostics.Stopwatch.Frequency);
            for (int i = 0; i < 100000000 && System.Diagnostics.Stopwatch.GetTimestamp() < until; i++) { }
        }

        private static void MenuFrame(long us)
        {
#if SCR_FRAMETIME
            FtA3.Read(FtA3.CE_perf_probe); FtA3.Wrote(FtA3.CE_perf_probe);
#endif
            bool inRoom = false;
            try { inRoom = Photon.Pun.PhotonNetwork.InRoom; } catch { }
            if (inRoom) return;
            if (_warm < 300) { _warm++; return; }              // settle after the menu loads
            if (_window >= 3) { MenuReport(); _done = true; return; }
            if (_window == 2) Spin(PLANT_MS);                  // the planted cost runs inside the measured frames
            Add(us);
            if (_frames >= PERF_WINDOW_CAP) Close(_window == 0 ? "AA1" : (_window == 1 ? "AA2" : "PLANT"));
        }

        private static void MenuReport()
        {
#if SCR_FRAMETIME
            FtA3.Read(FtA3.CE_perf_probe);
#endif
            long aaP50 = Math.Abs(_p50[1] - _p50[0]), aaP99 = Math.Abs(_p99[1] - _p99[0]);
            long plantP50 = _p50[2] - Math.Max(_p50[0], _p50[1]);
            long plantUs = (long)(PLANT_MS * 1000);
            // the control is seen when the planted window's median rises by at least half the
            // planted cost beyond the larger A/A median, and by more than the A/A spread
            bool seen = plantP50 >= plantUs / 2 && plantP50 > aaP50;
            try
            {
                Plugin.Log.LogInfo(TAG + " A/A: |d p50|=" + aaP50.ToString(CultureInfo.InvariantCulture) + "us |d p99|=" + aaP99.ToString(CultureInfo.InvariantCulture)
                    + "us; longest hitch " + Math.Max(_max[0], _max[1]).ToString(CultureInfo.InvariantCulture) + "us");
                Plugin.Log.LogInfo(TAG + " planted control: " + plantUs.ToString(CultureInfo.InvariantCulture) + "us per frame, p50 rise "
                    + plantP50.ToString(CultureInfo.InvariantCulture) + "us, detected=" + (seen ? "yes" : "no"));
                Plugin.Log.LogInfo(TAG + " menu run complete (collectors idle outside a game; the A/B in a ranked match remains)");
            }
            catch { }
        }

        private static void MatchFrame(long us)
        {
#if SCR_FRAMETIME
            int ftScope = FtA3.TEnter(); try {
#endif
#if SCR_FRAMETIME
            FtA3.Read(FtA3.CE_capture); FtA3.Read(FtA3.CE_perf_probe); FtA3.Wrote(FtA3.CE_capture);
            FtA3.Wrote(FtA3.CE_perf_probe);
#endif
            bool live = false;
            try { live = CombatEvidence.Open && SeatEvidence.CombatLive(); } catch { }
            if (!live)
            {
                if (CombatEvidence.PerfSuspend) CombatEvidence.PerfSuspend = false;
                if (_frames > 0) { _frames = 0; Array.Clear(_bins, 0, BIN_CAP); _maxUs = 0; }   // a partial window is discarded
                if (_window > 0 && _reported < _window) MatchReport();
                return;
            }
            bool b = (_window & 1) == 1;
            CombatEvidence.PerfSuspend = b;
            if (b) Contaminated = true;
            Add(us);
            if (_frames >= PERF_WINDOW_CAP) Close(b ? "B" : "A");
            if (_window >= WINDOWS_CAP) { CombatEvidence.PerfSuspend = false; MatchReport(); _done = true; }
#if SCR_FRAMETIME
            } finally { FtA3.TExit(ftScope); }
#endif
        }

        private static void MatchReport()
        {
#if SCR_FRAMETIME
            FtA3.Read(FtA3.CE_perf_probe); FtA3.Wrote(FtA3.CE_perf_probe);
#endif
            long a50 = 0, a99 = 0, b50 = 0, b99 = 0, amax = 0, bmax = 0; int na = 0, nb = 0;
            int n = Math.Min(_window, WINDOWS_CAP);
            for (int i = 0; i < n && i < WINDOWS_CAP; i++)
            {
                if ((i & 1) == 0) { a50 += _p50[i]; a99 += _p99[i]; amax = Math.Max(amax, _max[i]); na++; }
                else { b50 += _p50[i]; b99 += _p99[i]; bmax = Math.Max(bmax, _max[i]); nb++; }
            }
            _reported = _window;
            try
            {
#if SCR_FRAMETIME
                FtLog.LogInfo(TAG + " A/B over " + na.ToString(CultureInfo.InvariantCulture) + "+" + nb.ToString(CultureInfo.InvariantCulture) + " windows: A p50/p99/max "
#else
                Plugin.Log.LogInfo(TAG + " A/B over " + na.ToString(CultureInfo.InvariantCulture) + "+" + nb.ToString(CultureInfo.InvariantCulture) + " windows: A p50/p99/max "
#endif
                    + (na > 0 ? a50 / na : 0).ToString(CultureInfo.InvariantCulture) + "/" + (na > 0 ? a99 / na : 0).ToString(CultureInfo.InvariantCulture) + "/" + amax.ToString(CultureInfo.InvariantCulture)
                    + "us, B " + (nb > 0 ? b50 / nb : 0).ToString(CultureInfo.InvariantCulture) + "/" + (nb > 0 ? b99 / nb : 0).ToString(CultureInfo.InvariantCulture) + "/" + bmax.ToString(CultureInfo.InvariantCulture) + "us");
            }
            catch { }
        }
#if SCR_FRAMETIME

        // -- FrameTime A3 (FtA3; SURVIVORS.md, CE_perf_probe) -------------------------------------

        /// <summary>Close's and MatchReport's log in this build: Plugin.Log, except while FtCalPerf runs them (main
        /// thread, outside live combat), when it is the calibration's scratch source.</summary>
        private static BepInEx.Logging.ManualLogSource FtLog { get { return _ftSink ?? Plugin.Log; } }
        private static BepInEx.Logging.ManualLogSource _ftSink, _ftScratch;
        private const long FT_US = (long)(BIN_CAP - 1) * BIN_US + 7;
        private const long FT_TOP = (long)(BIN_CAP - 1) * BIN_US + BIN_US / 2;

        /// <summary>CE_perf_probe, executed (round 5, ruling FRAME-TIME-ROUND-R4-A1, M1) on the component's own
        /// statics: every static the readers touch (_bound, _on, _done, _mode, _bins, _frames, _window, _warm,
        /// _maxUs, _p50, _p99, _max, _label, _reported, Contaminated and the log hook) is saved before the call and
        /// restored, slot by slot, in a finally; the readers' lines go to FtA3.ScratchLog (no live listener, no
        /// file). EMPTY: the cheapest read, the real Frame with the probe off (bound, not on), the path of every live
        /// frame of a game without the probe: it returns at its second test. CAPACITY in its costliest content: the
        /// costliest frame of a probe-on match, the last frame of the last window, run as the readers MatchFrame
        /// calls on it, in its order: the real Add of a frame in the last bin onto a window holding PERF_WINDOW_CAP - 1
        /// frames all in the last bin, the real Close of that window (both Quantile walks cross every bin; the window
        /// line is written) and the real MatchReport the last window triggers (its line). Frame's own prefix on that
        /// frame (Time.unscaledDeltaTime, the mode compare) and MatchFrame's live test read the engine and the live
        /// combat state and are not run; that frame counts seven reads of the row (Frame, MatchFrame, Add, Close, two
        /// Quantile, MatchReport), each charged d. Checks from the readers' own effect: EMPTY wrote no line and left
        /// the frames and windows; FULL wrote the window line and the report, stored both quantiles of the window as
        /// the last bin's value (every bin walked), closed the window (bins and frames cleared, the window counted)
        /// and marked it reported.</summary>
        internal static long FtCalPerf(bool full, int n)
        {
            if (_ftScratch == null) _ftScratch = FtA3.ScratchLog("FrameTime-A3-Perf");
            bool sBound = _bound, sOn = _on, sDone = _done, sCont = Contaminated;
            string sMode = _mode;
            var sBins = (int[])_bins.Clone();
            int sFrames = _frames, sWindow = _window, sWarm = _warm, sReported = _reported;
            long sMaxUs = _maxUs;
            var sP50 = (long[])_p50.Clone();
            var sP99 = (long[])_p99.Clone();
            var sMax = (long[])_max.Clone();
            var sLabel = (string[])_label.Clone();
            var sSink = _ftSink;
            long t = 0;
            bool ok = true;
            try
            {
                _ftSink = _ftScratch;
                for (int j = 0; j < n; j++)
                {
                    _bound = true; _done = false; _mode = "match";
                    long l0, s;
                    if (full)
                    {
                        _on = true;
                        Array.Clear(_bins, 0, BIN_CAP);
                        _bins[BIN_CAP - 1] = PERF_WINDOW_CAP - 1;
                        _frames = PERF_WINDOW_CAP - 1; _maxUs = FT_US; _window = WINDOWS_CAP - 1; _reported = 0;
                        _p50[WINDOWS_CAP - 1] = 0; _p99[WINDOWS_CAP - 1] = 0;
                        l0 = FtA3.ScratchLines;
                        s = System.Diagnostics.Stopwatch.GetTimestamp();
                        Add(FT_US);
                        Close("B");
                        MatchReport();
                        t += System.Diagnostics.Stopwatch.GetTimestamp() - s;
                        ok &= FtA3.ScratchLines - l0 == 2 && _p50[WINDOWS_CAP - 1] == FT_TOP && _p99[WINDOWS_CAP - 1] == FT_TOP
                            && _window == WINDOWS_CAP && _frames == 0 && _bins[BIN_CAP - 1] == 0 && _reported == WINDOWS_CAP;
                    }
                    else
                    {
                        _on = false;
                        _frames = 5; _window = 3;
                        l0 = FtA3.ScratchLines;
                        s = System.Diagnostics.Stopwatch.GetTimestamp();
                        Frame();
                        t += System.Diagnostics.Stopwatch.GetTimestamp() - s;
                        ok &= FtA3.ScratchLines - l0 == 0 && _frames == 5 && _window == 3;
                    }
                }
            }
            finally
            {
                _bound = sBound; _on = sOn; _done = sDone; Contaminated = sCont; _mode = sMode;
                Array.Copy(sBins, _bins, BIN_CAP);
                _frames = sFrames; _window = sWindow; _warm = sWarm; _reported = sReported; _maxUs = sMaxUs;
                Array.Copy(sP50, _p50, WINDOWS_CAP); Array.Copy(sP99, _p99, WINDOWS_CAP); Array.Copy(sMax, _max, WINDOWS_CAP);
                Array.Copy(sLabel, _label, WINDOWS_CAP);
                _ftSink = sSink;
            }
            FtA3.Check(FtA3.CE_perf_probe, full ? "full-last-frame-closed-walked-reported" : "empty-probe-off-no-line", ok);
            return t;
        }
#endif
    }
}
