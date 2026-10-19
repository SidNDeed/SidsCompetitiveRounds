// Night 2026-10-19 calibration lane: DSN-free controls over the real plugin
// files (see NetStallTests.csproj). One line per case: PASS name / FAIL name
// detail. Exit 0 only when every selected case passes. Arguments select
// cases by name (run_tests.py runs one target and one control per mutant).
using System;
using System.Collections.Generic;
using System.Linq;
using CompetitiveRounds;

namespace NetStallTests
{
    internal static class Program
    {
        private static int _fail;
        private static readonly List<string> Out = new List<string>();

        private static void Check(string name, Func<string> body)
        {
            string err;
            try { err = body(); } catch (Exception ex) { err = "threw " + ex.GetType().Name + ": " + ex.Message; }
            if (err == null) Out.Add("PASS " + name);
            else { Out.Add("FAIL " + name + " " + err); _fail++; }
        }

        private static int Main(string[] args)
        {
            var cases = new List<KeyValuePair<string, Func<string>>>
            {
                new KeyValuePair<string, Func<string>>("stall_night", StallNight),
                new KeyValuePair<string, Func<string>>("stall_frames_hitch", StallFramesHitch),
                new KeyValuePair<string, Func<string>>("stall_cap", StallCap),
                new KeyValuePair<string, Func<string>>("stall_ordinary_spikes", StallOrdinarySpikes),
                new KeyValuePair<string, Func<string>>("stall_streams_flowing", StallStreamsFlowing),
                new KeyValuePair<string, Func<string>>("jitter_reserve", JitterReserve),
                new KeyValuePair<string, Func<string>>("jitter_top", JitterTop),
                new KeyValuePair<string, Func<string>>("poison_kill_every_epoch", PoisonKillEveryEpoch),
                new KeyValuePair<string, Func<string>>("poison_cut_marker", PoisonCutMarker),
                new KeyValuePair<string, Func<string>>("lag_bar_met_1v2", LagBarMet1v2),
                new KeyValuePair<string, Func<string>>("lag_1v2_gate", Lag1v2Gate),
                new KeyValuePair<string, Func<string>>("lag_1v1_fires", Lag1v1Fires),
                new KeyValuePair<string, Func<string>>("lag_1v1_setting_off", Lag1v1SettingOff),
                new KeyValuePair<string, Func<string>>("focus_lockstep", FocusLockstep),
            };
            var only = new HashSet<string>(args);
            foreach (var c in cases) if (only.Count == 0 || only.Contains(c.Key)) Check(c.Key, c.Value);
            foreach (var l in Out) Console.WriteLine(l);
            Console.WriteLine("cases=" + Out.Count + " fail=" + _fail);
            return _fail == 0 ? 0 : 1;
        }

        // ── the inbound stall detector ───────────────────────────────────

        // The other seat's queue on the night (446, game 2 windows 529..535,
        // NightWindows.OtherSeat1v2Game2 QIn column): 1 at the start of 530,
        // 21, 62, 108, 157, 199 at the ends of 530..534, drained in 535. The
        // depth is interpolated between those knots, sampled every 18 ms.
        private static readonly int[] KnotMs = { 0, 1000, 2000, 3000, 4000, 5000 };
        private static readonly int[] KnotQ = { 1, 21, 62, 108, 157, 199 };
        private const int SampleMs = 18;

        private static int NightDepth(int t)
        {
            if (t >= 5000) return 3;   // drained
            for (int k = 1; k < KnotMs.Length; k++)
                if (t < KnotMs[k])
                    return KnotQ[k - 1] + (KnotQ[k] - KnotQ[k - 1]) * (t - KnotMs[k - 1]) / (KnotMs[k] - KnotMs[k - 1]);
            return 3;
        }

        private static int Snap(int[] actors, long[] batches, long a2, long a3)
        {
            actors[0] = 2; batches[0] = a2;
            actors[1] = 3; batches[1] = a3;
            return 2;
        }

        private static List<string> RunSeries(InboundStallCore core, Func<int, int> depth, int endMs, int frameMs,
                                              Func<int, long> batches, int baseMs = 0, int game = 2)
        {
            var lines = new List<string>();
            for (int t = 0; t <= endMs; t += SampleMs)
            {
                core.OnFrame(frameMs);
                int tt = t;
                InboundStallCore.StreamSnapshot snap = (a, b) => Snap(a, b, batches(tt), 2 * batches(tt));
                int d = depth(t);
                if (!core.Wants(d)) continue;
                string l = core.OnDepth(d, baseMs + t, snap, game);
                if (l != null) lines.Add(l);
            }
            return lines;
        }

        private static string Field(string line, string key)
        {
            int i = line.IndexOf(" " + key + "=", StringComparison.Ordinal);
            if (i < 0) return null;
            int s = i + key.Length + 2;
            int e = line.IndexOf(' ', s);
            return e < 0 ? line.Substring(s) : line.Substring(s, e - s);
        }

        private static string StallNight()
        {
            // Independent expectation from the series itself.
            int open = -1, close = -1, rise = -1, peak = 0, framesIn = 0;
            for (int t = 0; t <= 6000; t += SampleMs)
            {
                int d = NightDepth(t);
                if (rise < 0 && d > 24) rise = t;
                if (open < 0 && d > 48) open = t;
                if (open >= 0 && close < 0 && d <= 48) { close = t; break; }
                if (open >= 0 && d > peak) peak = d;
            }
            for (int t = open + SampleMs; t <= close; t += SampleMs) framesIn++;
            var core = new InboundStallCore();
            var lines = RunSeries(core, NightDepth, 6000, 18, t => 1000);
            if (lines.Count != 1) return "lines=" + lines.Count + " (want exactly 1)";
            string l = lines[0];
            if (!l.StartsWith("[NET-STALL] game=2 n=1 ", StringComparison.Ordinal)) return "head " + l;
            if (Field(l, "durMs") != (close - open).ToString()) return "durMs " + Field(l, "durMs") + " want " + (close - open);
            if (close - open < 3000) return "series shape: the stall above the bound must last over 3 s, got " + (close - open);
            if (Field(l, "riseMs") != (close - rise).ToString()) return "riseMs " + Field(l, "riseMs") + " want " + (close - rise);
            if (Field(l, "peakQ") != peak.ToString()) return "peakQ " + Field(l, "peakQ") + " want " + peak;
            if (Field(l, "frames") != framesIn.ToString()) return "frames " + Field(l, "frames") + " want " + framesIn;
            if (Field(l, "worstFrameMs") != "18") return "worstFrameMs " + Field(l, "worstFrameMs");
            if (Field(l, "remoteStreams") != "2" || Field(l, "stopped") != "2") return "streams " + l;
            if (Field(l, "open") != "0") return "open " + l;
            if (core.GameStalls != 1 || core.GameLongestMs != close - open) return "summary " + core.SummaryFields();
            if (!core.SummaryFields().Contains(" stalls=1 longestStallMs=" + (close - open) + " ")) return "summary text " + core.SummaryFields();
            return null;
        }

        private static string StallFramesHitch()
        {
            var core = new InboundStallCore();
            var lines = RunSeries(core, NightDepth, 6000, 60, t => 1000);
            if (lines.Count != 0) return "a stall covered by 60 ms frames was logged: " + lines[0];
            if (core.GameStalls != 0 || core.GameFrameExcluded != 1) return "counts " + core.SummaryFields();
            return null;
        }

        private static string StallCap()
        {
            var core = new InboundStallCore();
            var all = new List<string>();
            for (int i = 0; i < 10; i++)
            {
                // a 1.5 s hold at 120, then drained
                Func<int, int> d = t => t < 1500 ? 120 : 2;
                all.AddRange(RunSeries(core, d, 1600, 18, t => 5, baseMs: i * 10000, game: 1));
            }
            if (all.Count != InboundStallCore.MAX_LINES_PER_ROOM) return "lines=" + all.Count + " want " + InboundStallCore.MAX_LINES_PER_ROOM;
            if (core.GameStalls != 10 || core.RoomSuppressed != 2) return "counts stalls=" + core.GameStalls + " suppressed=" + core.RoomSuppressed;
            core.ResetRoom();
            var again = RunSeries(core, t => t < 1500 ? 120 : 2, 1600, 18, t => 5, baseMs: 200000, game: 1);
            if (again.Count != 1) return "the room reset did not restore the budget";
            return null;
        }

        private static string StallOrdinarySpikes()
        {
            // The night's ordinary spikes: a single sample up to 78 that
            // drains at the next Dispatch, every two seconds, for a minute.
            var core = new InboundStallCore();
            var lines = RunSeries(core, t => (t % 2000) < SampleMs ? 78 : 5, 60000, 18, t => t);
            if (lines.Count != 0 || core.GameStalls != 0) return "an ordinary spike was logged as a stall";
            return null;
        }

        private static string StallStreamsFlowing()
        {
            var core = new InboundStallCore();
            var lines = RunSeries(core, NightDepth, 6000, 18, t => 1000 + t);
            if (lines.Count != 1) return "lines=" + lines.Count;
            if (Field(lines[0], "stopped") != "0") return "streams that kept delivering read as stopped: " + lines[0];
            return null;
        }

        // ── the NET-JITTER reserve ───────────────────────────────────────

        private static string JitterReserve()
        {
            var b = new NetJitterBudgetCore();
            int logged = 0, routineLogged = 0;
            bool bigLogged = false, bigReserve = false;
            for (int i = 0; i < 17; i++)
            {
                bool r;
                if (b.Offer(2, 320 + i, 50, 270 + i, 1, out r)) { logged++; routineLogged++; }
            }
            bool rr;
            bigLogged = b.Offer(3, 6000, 45, 5955, 2, out rr);
            bigReserve = rr;
            if (routineLogged != NetJitterBudgetCore.TOTAL - NetJitterBudgetCore.RESERVE) return "routine lines=" + routineLogged;
            if (!bigLogged || !bigReserve) return "the 6000 ms gap was not logged on the reserve";
            string s = b.SummaryFields();
            if (!s.Contains(" jitterTop=a3:6000ms/s45/x5955/g2;")) return "summary does not name the big gap first: " + s;
            if (!s.Contains(" jitterLines=13/16 ") || !s.Contains(" jitterSuppressed=5 ")) return "counts " + s;
            return null;
        }

        private static string JitterTop()
        {
            var b = new NetJitterBudgetCore();
            bool r;
            for (int i = 0; i < 12; i++) b.Offer(2, 330, 40, 290, 1, out r);
            int[] bigs = { 1500, 4200, 2500, 6100, 3300, 1200 };
            foreach (int g in bigs) b.Offer(3, g, 40, g - 40, 1, out r);   // the 5th and 6th find the budget spent
            if (!b.Spent) return "budget not spent";
            string s = b.SummaryFields();
            if (!s.Contains(" jitterTop=a3:6100ms/s40/x6060/g1;a3:4200ms/s40/x4160/g1;a3:3300ms/s40/x3260/g1")) return "top " + s;
            return null;
        }

        // ── poison: a kill line at every point boundary ──────────────────

        private static string PoisonKillEveryEpoch()
        {
            var act = new ActivationCore();
            var log = new V3LineLog();
            var lines = new List<string>();
            int[] fighters = { 1, 2, 3 };
            Func<int, bool> cap3 = a => true;
            int aid = 0, ts = -1950150256, boundaries = 0;
            long now = 0;
            Action<string> emit = l => { if (l != null) lines.Add(l); };
            Action<LifeEpoch> offer = point =>
            {
                aid++;
                emit(log.Note("activation sent a=" + aid + " fighters=3"));
                act.OnActivate(1, 1, aid, fighters, point, now);
                emit(log.Note("activation received a=" + aid + " from=1 fighters=3 ack=sent"));
                act.NoteSelfAck();
                foreach (int f in fighters) act.OnAck(f, 1, aid);
            };
            Action<LifeEpoch> upkeep = point =>
            {
                string why;
                bool on = act.Evaluate(fighters, cap3, now, point, out why);
                emit(log.State(on ? "v3 " + why : "v3 off why=" + why));
            };
            var none = default(LifeEpoch);
            upkeep(none);
            offer(none);
            upkeep(none); upkeep(none);
            for (int game = 1; game <= 2; game++)
            {
                for (int p = 0; p < 15; p++)
                {
                    ts += 11000; now += 11000; boundaries++;
                    var point = LifeEpoch.At(ts);
                    log.OnPoint();
                    upkeep(point);              // the boundary kills the activation
                    upkeep(point);              // a repeated state is not a new line
                    offer(point);               // the master re-offers over the new point
                    upkeep(point); upkeep(point);
                }
            }
            int kills = lines.Count(l => l == "v3 off why=killed:point-boundary");
            if (kills != boundaries) return "kill lines=" + kills + " boundaries=" + boundaries + " (lines " + lines.Count + ")";
            int ons = lines.Count(l => l.StartsWith("v3 on a=", StringComparison.Ordinal));
            if (ons != boundaries + 1) return "on lines=" + ons;
            return null;
        }

        private static string PoisonCutMarker()
        {
            var log = new V3LineLog();
            int written = 0, markers = 0;
            for (int i = 0; i < 40; i++)
            {
                string l = log.Note("replay to=" + i);
                if (l == null) continue;
                if (l.StartsWith("v3 lines for this point cut at", StringComparison.Ordinal)) markers++; else written++;
            }
            if (markers != 1) return "markers=" + markers;
            if (written == 0 || written >= 40) return "written=" + written;
            if (log.Suppressed != 40 - written) return "suppressed=" + log.Suppressed;
            return null;
        }

        // ── LagNotices over the night's window values ────────────────────

        private static NetworkSeatTelemetry.WindowFacts W(int[] r, int oppActor, string oppId)
        {
            return new NetworkSeatTelemetry.WindowFacts { Seq = r[0], WorstMs = r[1], OwnPing = r[2], PeerRtt = r[3], ObsLate300 = r[4], OppActor = oppActor, OppId = oppId };
        }

        private static string LagBarMet1v2()
        {
            // The pure predicate over the other seat's 1v2 windows: the
            // OPP_STREAM bar IS met (two windows of the last five with a late
            // sample and frames under 100 ms) once the stall window closes.
            var rows = NightWindows.OtherSeat1v2Game2;
            var met = new List<int>();
            for (int k = 0; k < rows.Length; k++)
            {
                var recent = new NetworkSeatTelemetry.WindowFacts[Math.Min(5, k + 1)];
                for (int i = 0; i < recent.Length; i++) recent[i] = W(rows[k - i], 0, null);
                if (LagNotices.EnterPredicate(LagNotices.State.OPP_STREAM, recent, recent.Length)) met.Add(rows[k][0]);
            }
            if (!met.Contains(535)) return "OPP_STREAM bar not met at window 535: " + string.Join(",", met);
            return null;
        }

        private static List<string> DriveGame(int[][] rows, bool setting, bool plain1v1, int oppActor, string oppId)
        {
            Plugin.Log = new LogSink();
            Plugin.LagNoticesEnabled = new BepInEx.Configuration.ConfigEntry<bool> { Value = setting };
            GameStateWatcher.PlainOneVOne = plain1v1;
            NetworkSeatTelemetry.Ring.Clear();
            LagNotices.OnGameStarted();
            foreach (var r in rows)
            {
                NetworkSeatTelemetry.Ring.Add(W(r, oppActor, oppId));
                LagNotices.OnWindowClosed();
            }
            LagNotices.OnGameEnded();
            return Plugin.Log.Lines;
        }

        private static string Lag1v2Gate()
        {
            var lines = DriveGame(NightWindows.OtherSeat1v2Game2, true, false, 0, null);
            if (lines.Any(l => l.StartsWith("[LAG-NOTICE] state=", StringComparison.Ordinal))) return "a 1v2 seat drew a notice";
            string g = lines.FirstOrDefault(l => l.StartsWith("[LAG-NOTICE-GATE] ", StringComparison.Ordinal));
            if (g == null) return "no gate line";
            if (!g.Contains(" windows=64 ") || !g.Contains(" not_plain_1v1=64 ") || !g.Contains(" evaluated=0 ")) return "gate " + g;
            return null;
        }

        private static string Lag1v1Fires()
        {
            var lines = DriveGame(NightWindows.HostSeat1v1Game, true, true, 2, "A");
            var enters = lines.Where(l => l.StartsWith("[LAG-NOTICE] state=", StringComparison.Ordinal) && l.Contains(" edge=enter")).ToList();
            if (!enters.Any(l => l.StartsWith("[LAG-NOTICE] state=OWN_PING edge=enter", StringComparison.Ordinal))) return "no OWN_PING enter over the 1v1 night windows";
            if (!enters.Any(l => l.StartsWith("[LAG-NOTICE] state=OPP_STREAM edge=enter", StringComparison.Ordinal))) return "no OPP_STREAM enter over the 1v1 night windows";
            string g = lines.FirstOrDefault(l => l.StartsWith("[LAG-NOTICE-GATE] ", StringComparison.Ordinal));
            if (g == null || !g.Contains(" enters=" + enters.Count + " ")) return "gate " + g + " enters " + enters.Count;
            return null;
        }

        private static string Lag1v1SettingOff()
        {
            var lines = DriveGame(NightWindows.HostSeat1v1Game, false, true, 2, "A");
            if (lines.Any(l => l.StartsWith("[LAG-NOTICE] state=", StringComparison.Ordinal))) return "a notice with the setting off";
            string g = lines.FirstOrDefault(l => l.StartsWith("[LAG-NOTICE-GATE] ", StringComparison.Ordinal));
            if (g == null) return "no gate line with the setting off (the night could not say why)";
            if (!g.Contains(" setting_off=64 ") || !g.Contains(" evaluated=0 ")) return "gate " + g;
            return null;
        }

        // ── the focus flag beside each fps bucket ────────────────────────

        private static string FocusLockstep()
        {
            var fps = new DecimatedList<int>();
            var focus = new DecimatedList<int>();
            for (int i = 0; i < 300; i++)
            {
                fps.Add(i);                                       // the bucket's index stands in for its rate
                focus.Add(FpsFocusCore.BucketFlag(i % 7 == 3));   // every 7th bucket lost focus
            }
            if (fps.Count != focus.Count) return "counts " + fps.Count + " " + focus.Count;
            for (int j = 0; j < fps.Count; j++)
            {
                int want = fps.Items[j] % 7 == 3 ? 0 : 1;
                if (focus.Items[j] != want) return "bucket " + j + " (index " + fps.Items[j] + ") flag " + focus.Items[j];
            }
            string enc = FpsFocusCore.Encode(focus.Items);
            if (enc != string.Join(",", focus.Items)) return "encoding " + enc;
            if (FpsFocusCore.Encode(new List<int>()) != "") return "empty encoding";
            if (FpsFocusCore.BucketFlag(false) != 1 || FpsFocusCore.BucketFlag(true) != 0) return "flag polarity";
            return null;
        }
    }
}
