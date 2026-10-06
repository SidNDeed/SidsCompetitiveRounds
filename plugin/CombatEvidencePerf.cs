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
            if (!_bound) Bind();
            if (!_on || _done) return;
            long us = (long)(Time.unscaledDeltaTime * 1e6);
            if (_mode == "menu") MenuFrame(us);
            else MatchFrame(us);
        }

        private static void Add(long us)
        {
            if (us < 0) us = 0;
            _bins[(int)Math.Min(us / BIN_US, BIN_CAP - 1)]++;
            _frames++;
            if (us > _maxUs) _maxUs = us;
        }

        private static long Quantile(double q)
        {
            if (_frames == 0) return 0;
            long rank = (long)Math.Ceiling(q * _frames), acc = 0;
            if (rank < 1) rank = 1;
            for (int i = 0; i < BIN_CAP; i++) { acc += _bins[i]; if (acc >= rank) return (long)i * BIN_US + BIN_US / 2; }
            return _maxUs;
        }

        private static void Close(string label)
        {
            if (_window < WINDOWS_CAP)
            {
                _label[_window] = label; _p50[_window] = Quantile(0.5); _p99[_window] = Quantile(0.99); _max[_window] = _maxUs;
                try
                {
                    Plugin.Log.LogInfo(TAG + " window " + (_window + 1).ToString(CultureInfo.InvariantCulture) + " " + label
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
        }

        private static void MatchReport()
        {
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
                Plugin.Log.LogInfo(TAG + " A/B over " + na.ToString(CultureInfo.InvariantCulture) + "+" + nb.ToString(CultureInfo.InvariantCulture) + " windows: A p50/p99/max "
                    + (na > 0 ? a50 / na : 0).ToString(CultureInfo.InvariantCulture) + "/" + (na > 0 ? a99 / na : 0).ToString(CultureInfo.InvariantCulture) + "/" + amax.ToString(CultureInfo.InvariantCulture)
                    + "us, B " + (nb > 0 ? b50 / nb : 0).ToString(CultureInfo.InvariantCulture) + "/" + (nb > 0 ? b99 / nb : 0).ToString(CultureInfo.InvariantCulture) + "/" + bmax.ToString(CultureInfo.InvariantCulture) + "us");
            }
            catch { }
        }
    }
}
