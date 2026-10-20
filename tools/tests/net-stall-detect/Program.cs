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
                new KeyValuePair<string, Func<string>>("stall_rise_explained", StallRiseExplained),
                new KeyValuePair<string, Func<string>>("snapshot_roster", SnapshotRoster),
                new KeyValuePair<string, Func<string>>("snapshot_spectator", SnapshotSpectator),
                new KeyValuePair<string, Func<string>>("snapshot_overflow", SnapshotOverflow),
                new KeyValuePair<string, Func<string>>("jitter_ties", JitterTies),
                new KeyValuePair<string, Func<string>>("jitter_same_room_reset", JitterSameRoomReset),
                new KeyValuePair<string, Func<string>>("lag_setting_flips", LagSettingFlips),
                new KeyValuePair<string, Func<string>>("focus_reset_match", () => Pin("m7_focus_match_reset")),
                new KeyValuePair<string, Func<string>>("focus_reset_state", () => Pin("m7_focus_state_reset")),
    new KeyValuePair<string, Func<string>>("fps_focus_clamp_wire", FpsFocusClampWire),
    new KeyValuePair<string, Func<string>>("fps_focus_clamp_short", FpsFocusClampShort),
    new KeyValuePair<string, Func<string>>("focus_outlier_unfocused", () => FocusTrackedBucket(true)),
    new KeyValuePair<string, Func<string>>("focus_all_focused", () => FocusTrackedBucket(false)),
                new KeyValuePair<string, Func<string>>("lag_gate_subsecond_end", () => Pin("m4_game_end") ?? LagGateZeroWindow(true)),
                new KeyValuePair<string, Func<string>>("lag_gate_disconnect_before_window", () => Pin("m4_disconnect") ?? LagGateZeroWindow(false)),
                new KeyValuePair<string, Func<string>>("lag_gate_repeated_end", LagGateRepeatedEnd),
                new KeyValuePair<string, Func<string>>("stall_night", StallNight),
                new KeyValuePair<string, Func<string>>("stall_frames_hitch", StallFramesHitch),
                new KeyValuePair<string, Func<string>>("stall_terminal_hitch_game_end", () => StallTerminal(true, 100)),
                new KeyValuePair<string, Func<string>>("stall_terminal_hitch_depth_close", () => StallTerminal(false, 100)),
                new KeyValuePair<string, Func<string>>("stall_terminal_fast", StallTerminalFast),
                new KeyValuePair<string, Func<string>>("stall_steady_bands", StallSteadyBands),
                new KeyValuePair<string, Func<string>>("stall_band_crossings", StallBandCrossings),
                new KeyValuePair<string, Func<string>>("stall_cap", StallCap),
                new KeyValuePair<string, Func<string>>("stall_suppressed_per_game", StallSuppressedPerGame),
                new KeyValuePair<string, Func<string>>("stall_room_reset", StallRoomReset),
                new KeyValuePair<string, Func<string>>("stall_ordinary_spikes", StallOrdinarySpikes),
                new KeyValuePair<string, Func<string>>("stall_streams_flowing", StallStreamsFlowing),
                new KeyValuePair<string, Func<string>>("jitter_reserve", JitterReserve),
                new KeyValuePair<string, Func<string>>("jitter_top", JitterTop),
                new KeyValuePair<string, Func<string>>("poison_kill_every_epoch", PoisonKillEveryEpoch),
                new KeyValuePair<string, Func<string>>("poison_cut_marker", PoisonCutMarker),
                new KeyValuePair<string, Func<string>>("poison_replacement_before_upkeep", PoisonReplacementBeforeUpkeep),
                new KeyValuePair<string, Func<string>>("poison_adoption_before_local_boundary", PoisonAdoptionBeforeLocalBoundary),
                new KeyValuePair<string, Func<string>>("poison_duplicate_and_older_stamps", PoisonDuplicateAndOlderStamps),
                new KeyValuePair<string, Func<string>>("poison_stamp_wrap", PoisonStampWrap),
                new KeyValuePair<string, Func<string>>("poison_ordinary_lines_between", PoisonOrdinaryLinesBetween),
                new KeyValuePair<string, Func<string>>("poison_two_games", PoisonTwoGames),
                new KeyValuePair<string, Func<string>>("poison_room_reset", PoisonRoomReset),
                new KeyValuePair<string, Func<string>>("lag_bar_met_1v2", LagBarMet1v2),
                new KeyValuePair<string, Func<string>>("lag_1v2_gate", Lag1v2Gate),
                new KeyValuePair<string, Func<string>>("lag_1v1_fires", Lag1v1Fires),
                new KeyValuePair<string, Func<string>>("lag_1v1_setting_off", Lag1v1SettingOff),
                new KeyValuePair<string, Func<string>>("focus_lockstep", FocusLockstep),
            };
            var only = new HashSet<string>(args);
            foreach (string name in only)
                if (!cases.Any(c => c.Key == name)) Check(name, () => "unknown case");
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

        // Python checks exact production spans, including sources not compiled
        // by this harness, and passes a result for these named Program cases.
        private static string Pin(string name)
        {
            string result = Environment.GetEnvironmentVariable("NET_STALL_PIN_" + name);
            return result == "PASS" ? null : "source pin " + name + ": " + (result ?? "missing");
        }

        private static string StallTerminal(bool gameEnd, int terminalMs)
        {
            string pin = Pin(gameEnd ? "h1_game_end" : "h1_depth_close");
            if (pin != null) return pin;
            foreach (int closeDepth in new[] { 24, 48 })
            {
                var core = new InboundStallCore();
                core.OnDepth(60, 0, null, 1);
                for (int i = 0; i < 60; i++) core.OnFrame(18);
                string line = gameEnd ? core.Flush(1200, null, 1, terminalMs)
                                      : core.OnDepth(closeDepth, 1200, null, 1, terminalMs);
                // The delayed Update must not count or emit after closure.
                core.OnFrame(100);
                if (core.Flush(1300, null, 1, 100) != null) return "closure repeated";
                if (terminalMs >= 50)
                {
                    if (line != null || core.GameStalls != 0 || core.GameFrameExcluded != 1)
                        return "pending hitch qualified: " + core.SummaryFields();
                }
                else
                {
                    if (line == null) return "fast terminal frame rejected";
                    if (Field(line, "frames") != "60" || Field(line, "worstFrameMs") != Math.Max(18, terminalMs).ToString()
                        || Field(line, "durMs") != "1200" || Field(line, "open") != (gameEnd ? "1" : "0"))
                        return "terminal fields " + line;
                }
            }
            return null;
        }

        private static string StallTerminalFast()
        {
            return StallTerminal(true, 18) ?? StallTerminal(false, 18)
                ?? StallTerminal(true, 23) ?? StallTerminal(false, 23);
        }


        private static string StallRiseExplained()
        {
            var core = new InboundStallCore();
            core.OnDepth(10, 0, null, 1);
            core.OnDepth(30, 900, null, 1);
            core.OnDepth(49, 1000, null, 1);
            core.OnFrame(18);
            string line = core.OnDepth(0, 2201, null, 1);
            if (line == null) return "no qualifying close";
            if (Field(line, "durMs") != "1201" || Field(line, "riseMs") != "1301") return "rise numeric " + line;
            if (!line.Contains("riseMs = from the first sampled depth above 24")) return "rise explanation " + line;
            return null;
        }

        private static string StallSteadyBands()
        {
            foreach (int depth in new[] { 0, 24, 25, 30, 48, 49, 60 })
            {
                var core = new InboundStallCore();
                int clockReads = 0;
                for (int i = 0; i < 100; i++)
                {
                    bool wants = core.Wants(depth);
                    if (wants != (depth > 24 && i == 0)) return "steady gate depth=" + depth + " sample=" + i;
                    if (wants) { clockReads++; core.OnDepth(depth, i, null, 1); }
                }
                if (clockReads != (depth > 24 ? 1 : 0)) return "clock reads depth=" + depth + ": " + clockReads;
            }
            return Pin("m1_band_expression");
        }

        private static string StallBandCrossings()
        {
            var core = new InboundStallCore();
            int[] times = { 0, 100, 900, 1000, 1100, 1200, 1500, 1800, 2000, 2401,
                            2500, 2600, 2700, 9000, 9100, 10301 };
            int[] depths = { 0, 24, 25, 30, 48, 49, 49, 60, 59, 48, 49, 48, 24, 25, 49, 24 };
            var lines = new List<string>();
            for (int i = 0; i < times.Length; i++)
            {
                core.OnFrame(18);
                if (!core.Wants(depths[i])) continue;
                string line = core.OnDepth(depths[i], times[i], null, 1, 18);
                if (line != null) lines.Add(line);
            }
            if (lines.Count != 2) return "crossing lines=" + lines.Count;
            string[] rises = { "1501", "1301" }, peaks = { "60", "49" }, frames = { "4", "1" };
            for (int i = 0; i < lines.Count; i++)
                if (Field(lines[i], "durMs") != "1201" || Field(lines[i], "riseMs") != rises[i]
                    || Field(lines[i], "peakQ") != peaks[i] || Field(lines[i], "frames") != frames[i])
                    return "crossing fields " + lines[i];
            if (core.SummaryFields() != " stalls=2 longestStallMs=1201 stallsFrameExcluded=0 stallLinesSuppressed=0")
                return "crossing summary " + core.SummaryFields();
            core.ResetGame();
            if (core.Wants(24) || !core.Wants(25)) return "reset band";
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
            if (core.GameStalls != 10 || core.GameSuppressed != 2) return "counts stalls=" + core.GameStalls + " suppressed=" + core.GameSuppressed;
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

        private static string OneStall(InboundStallCore core, int offset, int game)
        {
            core.OnDepth(60, offset, null, game);
            core.OnFrame(18);
            return core.OnDepth(0, offset + 1201, null, game, 18);
        }

        private static string StallSuppressedPerGame()
        {
            var core = new InboundStallCore();
            int lines = 0;
            for (int i = 0; i < 10; i++) if (OneStall(core, i * 2000, 1) != null) lines++;
            if (lines != 8 || core.GameSuppressed != 2) return "first game budget/count";
            core.ResetGame();
            if (core.SummaryFields() != " stalls=0 longestStallMs=0 stallsFrameExcluded=0 stallLinesSuppressed=0")
                return "game two inherited suppression: " + core.SummaryFields();
            if (OneStall(core, 30000, 2) != null || core.GameSuppressed != 1 || core.GameStalls != 1)
                return "game reset replenished room budget or miscounted suppression";
            return null;
        }

        private static string StallRoomReset()
        {
            var core = new InboundStallCore();
            for (int i = 0; i < 10; i++) OneStall(core, i * 2000, 1);
            core.ResetRoom();
            if (core.GameSuppressed != 0 || core.GameStalls != 0) return "room reset retained game counters";
            if (OneStall(core, 30000, 1) == null || core.GameSuppressed != 0) return "room reset did not restore line budget";
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

        // Register all seven cases in Main. These run the real ledger,
        // activation and diagnostic core. The accompanying source pins check
        // that PoisonSync makes the same before/after handoffs.
        private const string PoisonKilled = "v3 off why=killed:point-boundary";
        private const string PoisonWaiting = "v3 off why=not-acked 0/2";
        private const string PoisonCut = "v3 lines for this point cut at 12 (the next point boundary resets the budget)";

        private sealed class PoisonCaptureRig
        {
            internal readonly PoisonLedgerCore Ledger = new PoisonLedgerCore();
            internal readonly ActivationCore Act = new ActivationCore();
            internal readonly V3LineLog Log = new V3LineLog();
            internal readonly List<string> Lines = new List<string>();
            private readonly int[] _fighters = { 1, 2 };
            private int _aid = 1;

            internal PoisonCaptureRig()
            {
                Act.OnActivate(1, 1, _aid, _fighters, default(LifeEpoch), 0);
                Upkeep();
            }
            internal void Emit(string line) { if (line != null) Lines.Add(line); }
            internal void Note(string line) { Emit(Log.Note(line)); }
            internal void Boundary(int stamp)
            {
                LifeEpoch before = Ledger.PointEpoch, prior = Act.Epoch;
                bool live = Act.Live;
                Ledger.NotePointBoundary(stamp);
                Emit(Log.OnPoint(before, Ledger.PointEpoch, prior, live));
            }
            internal void Activate(LifeEpoch point)
            {
                LifeEpoch before = Ledger.PointEpoch, prior = Act.Epoch;
                bool live = Act.Live;
                if (!Act.OnActivate(1, 1, ++_aid, _fighters, point, 0)) throw new Exception("test activation refused");
                if (point.Set) Ledger.AdoptPoint(point.Ts);
                Emit(Log.OnPoint(before, Ledger.PointEpoch, prior, live));
                Note("activation received");
            }
            internal void Upkeep(bool capable = true)
            {
                LifeEpoch before = Ledger.PointEpoch, prior = Act.Epoch;
                bool live = Act.Live;
                string why;
                bool on = Act.Evaluate(_fighters, actor => capable || actor != 2, 0, Ledger.PointEpoch, out why);
                Emit(Log.OnPoint(before, Ledger.PointEpoch, prior, live));
                Emit(Log.State(on ? "v3 " + why : "v3 off why=" + why));
            }
            internal void ResetRoom()
            {
                Ledger.Clear(); Act.Clear(); Log.Reset(); Lines.Clear();
                Act.OnActivate(1, 1, ++_aid, _fighters, default(LifeEpoch), 0);
            }
        }

        private static string PoisonExact(string step, List<string> lines, params string[] expected)
        {
            return lines.SequenceEqual(expected) ? null : step + " expected=[" + string.Join(" | ", expected)
                + "] actual=[" + string.Join(" | ", lines) + "]";
        }

        private static string PoisonReplacementBeforeUpkeep()
        {
            string pin = Pin("m3_boundary_capture"); if (pin != null) return pin;
            var r = new PoisonCaptureRig();
            string e = PoisonExact("setup", r.Lines, PoisonWaiting); if (e != null) return e;
            r.Lines.Clear();
            for (int i = 0; i < 12; i++) r.Note("old" + i);
            e = PoisonExact("old budget exhausted", r.Lines,
                Enumerable.Range(0, 11).Select(i => "old" + i).Concat(new[] { PoisonCut }).ToArray());
            if (e != null) return e;
            r.Lines.Clear();
            r.Boundary(100);
            e = PoisonExact("boundary before replacement", r.Lines, PoisonKilled); if (e != null) return e;
            r.Activate(LifeEpoch.At(100));
            r.Upkeep();
            e = PoisonExact("replacement before upkeep", r.Lines, PoisonKilled, "activation received", PoisonWaiting);
            if (e != null) return e;
            r.Lines.Clear();
            for (int i = 0; i < 10; i++) r.Note("new" + i);
            return PoisonExact("kill occupied first new-point slot", r.Lines,
                Enumerable.Range(0, 9).Select(i => "new" + i).Concat(new[] { PoisonCut }).ToArray());
        }

        private static string PoisonAdoptionBeforeLocalBoundary()
        {
            string pin = Pin("m3_activation_capture"); if (pin != null) return pin;
            var r = new PoisonCaptureRig();
            string e = PoisonExact("setup", r.Lines, PoisonWaiting); if (e != null) return e;
            r.Lines.Clear();
            r.Activate(LifeEpoch.At(100));
            e = PoisonExact("adoption captured old activation", r.Lines, PoisonKilled, "activation received");
            if (e != null) return e;
            r.Lines.Clear();
            r.Boundary(100);
            e = PoisonExact("same-stamp local boundary", r.Lines); if (e != null) return e;
            r.Upkeep();
            e = PoisonExact("new activation still waiting", r.Lines, PoisonWaiting); if (e != null) return e;
            r.Lines.Clear();
            for (int i = 0; i < 9; i++) r.Note("ordinary" + i);
            e = PoisonExact("remaining new-point budget", r.Lines,
                Enumerable.Range(0, 9).Select(i => "ordinary" + i).ToArray()); if (e != null) return e;
            r.Lines.Clear();
            r.Boundary(100);
            r.Note("overflow");
            return PoisonExact("local boundary did not replenish budget", r.Lines, PoisonCut);
        }

        private static string PoisonDuplicateAndOlderStamps()
        {
            var r = new PoisonCaptureRig();
            string e = PoisonExact("setup", r.Lines, PoisonWaiting); if (e != null) return e;
            r.Lines.Clear();
            r.Boundary(100); r.Activate(LifeEpoch.At(100)); r.Upkeep();
            e = PoisonExact("first boundary", r.Lines, PoisonKilled, "activation received", PoisonWaiting);
            if (e != null) return e;
            r.Lines.Clear();
            for (int i = 0; i < 9; i++) r.Note("ordinary" + i);
            e = PoisonExact("fill point", r.Lines, Enumerable.Range(0, 9).Select(i => "ordinary" + i).ToArray());
            if (e != null) return e;
            r.Lines.Clear();
            r.Boundary(100); r.Note("after duplicate");
            e = PoisonExact("duplicate stamp", r.Lines, PoisonCut); if (e != null) return e;
            r.Boundary(90); r.Note("after older");
            e = PoisonExact("older boundary", r.Lines, PoisonCut); if (e != null) return e;
            r.Activate(LifeEpoch.At(90));
            e = PoisonExact("older adoption", r.Lines, PoisonCut); if (e != null) return e;
            if (r.Log.Suppressed != 3) return "duplicate/older suppression=" + r.Log.Suppressed;
            r.Lines.Clear();
            r.Boundary(110);
            e = PoisonExact("already-stale activation is not newly invalidated", r.Lines); if (e != null) return e;
            r.Note("first line of later point");
            return PoisonExact("later point budget still resets", r.Lines, "first line of later point");
        }

        private static string PoisonStampWrap()
        {
            var r = new PoisonCaptureRig();
            string e = PoisonExact("setup", r.Lines, PoisonWaiting); if (e != null) return e;
            r.Lines.Clear();
            r.Boundary(int.MaxValue - 3); r.Activate(LifeEpoch.At(int.MaxValue - 3)); r.Upkeep();
            e = PoisonExact("before wrap", r.Lines, PoisonKilled, "activation received", PoisonWaiting);
            if (e != null) return e;
            r.Lines.Clear();
            r.Boundary(int.MinValue + 3);
            e = PoisonExact("wrapped advance", r.Lines, PoisonKilled); if (e != null) return e;
            r.Upkeep();
            e = PoisonExact("wrapped sampled kill deduplicated", r.Lines, PoisonKilled); if (e != null) return e;
            r.Boundary(int.MaxValue - 3);
            return PoisonExact("pre-wrap replay is older", r.Lines, PoisonKilled);
        }

        private static string PoisonOrdinaryLinesBetween()
        {
            string pin = Pin("m3_upkeep_capture"); if (pin != null) return pin;
            var r = new PoisonCaptureRig();
            string e = PoisonExact("setup", r.Lines, PoisonWaiting); if (e != null) return e;
            r.Lines.Clear();
            r.Boundary(100); r.Note("ordinary between boundary and upkeep");
            e = PoisonExact("ordinary line", r.Lines, PoisonKilled, "ordinary between boundary and upkeep");
            if (e != null) return e;
            r.Upkeep(); r.Upkeep();
            e = PoisonExact("sampled kill stays deduplicated", r.Lines, PoisonKilled, "ordinary between boundary and upkeep");
            if (e != null) return e;
            r.Upkeep(false); r.Upkeep(true);
            return PoisonExact("intervening capability state keeps one kill", r.Lines, PoisonKilled,
                "ordinary between boundary and upkeep", "v3 off why=cap-missing actor=2");
        }

        private static string PoisonTwoGames()
        {
            var r = new PoisonCaptureRig();
            string e = PoisonExact("setup", r.Lines, PoisonWaiting); if (e != null) return e;
            for (int game = 1; game <= 2; game++)
            {
                r.Lines.Clear();
                r.Boundary(game * 100); r.Activate(LifeEpoch.At(game * 100)); r.Upkeep();
                e = PoisonExact("game " + game, r.Lines, PoisonKilled, "activation received", PoisonWaiting);
                if (e != null) return e;
            }
            return null;
        }

        private static string PoisonRoomReset()
        {
            var r = new PoisonCaptureRig();
            string e = PoisonExact("setup", r.Lines, PoisonWaiting); if (e != null) return e;
            r.Lines.Clear();
            r.Boundary(100);
            for (int i = 0; i < 12; i++) r.Note("old" + i);
            e = PoisonExact("old room", r.Lines, new[] { PoisonKilled }
                .Concat(Enumerable.Range(0, 11).Select(i => "old" + i)).Concat(new[] { PoisonCut }).ToArray());
            if (e != null) return e;
            if (r.Log.Suppressed != 1) return "old-room suppression=" + r.Log.Suppressed;
            r.ResetRoom();
            if (r.Log.Suppressed != 0) return "room reset kept suppression";
            r.Upkeep();
            e = PoisonExact("new room state", r.Lines, PoisonWaiting); if (e != null) return e;
            r.Lines.Clear();
            r.Boundary(100);
            e = PoisonExact("same stamp in new room", r.Lines, PoisonKilled); if (e != null) return e;
            r.Upkeep();
            e = PoisonExact("new room duplicate upkeep", r.Lines, PoisonKilled); if (e != null) return e;
            r.ResetRoom();
            // If an observation was unavailable, the original sampled fallback still works.
            r.Ledger.NotePointBoundary(101); r.Upkeep();
            return PoisonExact("room reset restores sampled fallback", r.Lines, PoisonKilled);
        }

        private const string ZeroWindowGate = "[LAG-NOTICE-GATE] windows=0 setting_off=0 not_plain_1v1=0 unkeyed=0 evaluated=0 enters=0 suppressed=0";

        private static void PrepareZeroWindowLag(bool setting)
        {
            Plugin.Log = new LogSink();
            Plugin.LagNoticesEnabled = new BepInEx.Configuration.ConfigEntry<bool> { Value = setting };
            GameStateWatcher.PlainOneVOne = true;
            RoomActors.LocalIsSpectator = false;
            BroadcastMode.IsBroadcastIdentity = false;
            NetworkSeatTelemetry.Ring.Clear();
        }

        private static string LagGateZeroWindow(bool setting)
        {
            PrepareZeroWindowLag(setting);
            LagNotices.OnGameStarted();
            // A subsecond game-end/disconnect forced closure does not feed
            // the evaluator; the started edge alone authorizes its gate line.
            if (LagNotices.WindowFeedsEvaluator(true, true, false)) return "forced close fed evaluator";
            LagNotices.OnGameEnded();
            if (Plugin.Log.Lines.Count != 1 || Plugin.Log.Lines[0] != ZeroWindowGate)
                return "zero-window game lines=" + Plugin.Log.Lines.Count + " [" + string.Join(" | ", Plugin.Log.Lines) + "]";
            return null;
        }

        private static string LagGateRepeatedEnd()
        {
            string pin = Pin("m4_game_end");
            if (pin != null) return pin;
            PrepareZeroWindowLag(true);
            LagNotices.OnGameStarted();
            LagNotices.OnGameEnded();
            if (Plugin.Log.Lines.Count != 1 || Plugin.Log.Lines[0] != ZeroWindowGate)
                return "first started end did not write one zero record";
            LagNotices.OnGameEnded();
            LagNotices.OnGameEnded();
            if (Plugin.Log.Lines.Count != 1) return "repeated end wrote " + Plugin.Log.Lines.Count + " records";
            LagNotices.OnGameStarted();
            LagNotices.OnGameEnded();
            if (Plugin.Log.Lines.Count != 2 || Plugin.Log.Lines[1] != ZeroWindowGate)
                return "next started game did not rearm gate line";
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

        private static string FocusTrackedBucket(bool unfocusedOutlier)
        {
            if (unfocusedOutlier)
            {
                string pin = Pin("m5_focus_order");
                if (pin != null) return pin;
            }
            bool anyUnfocused = false;
            int frames = 0, accepted = 0, excluded = 0, closes = 0, flag = -1;
            float bucketTime = 0f, acceptedTime = 0f, closedTime = 0f;
            int closedFrames = 0, fps = -1;
            for (int frame = 0; frame < 11; frame++)
            {
                bool outlier = frame == 4;
                float dt = outlier ? 1.2f : 0.5f;
                bool focused = !outlier || !unfocusedOutlier;
                anyUnfocused = FpsFocusCore.ObserveFrame(anyUnfocused, focused, dt);
                if (dt <= 0f || dt > 1f) { excluded++; continue; }
                accepted++; acceptedTime += dt;
                frames++; bucketTime += dt;
                if (bucketTime >= 5f)
                {
                    closes++;
                    closedFrames = frames; closedTime = bucketTime;
                    fps = (int)Math.Round(frames / (double)bucketTime);
                    flag = FpsFocusCore.BucketFlag(anyUnfocused);
                    anyUnfocused = false;
                    frames = 0; bucketTime = 0f;
                }
            }
            if (accepted != 10 || excluded != 1 || acceptedTime != 5f) return "FPS outlier exclusion changed";
            if (closes != 1 || closedFrames != 10 || closedTime != 5f || fps != 2) return "not one complete five-second bucket";
            if (flag != (unfocusedOutlier ? 0 : 1)) return "bucket flag " + flag + " for " + (unfocusedOutlier ? "unfocused" : "focused") + " outlier";
            if (anyUnfocused || frames != 0 || bucketTime != 0f) return "bucket did not reset";
            return null;
        }

        private static string FpsWireField(string wire, string key)
        {
            using (var doc = System.Text.Json.JsonDocument.Parse("{" + wire.TrimEnd(',') + "}"))
                return doc.RootElement.GetProperty(key).GetString();
        }

        private static string FpsFocusClampWire()
        {
            var fps = Enumerable.Range(0, 103).Select(i => (1000 + i).ToString(System.Globalization.CultureInfo.InvariantCulture)).ToArray();
            var focus = Enumerable.Range(0, 103).Select(i => i % 7 == 3 ? "0" : "1").ToArray();
            string fpsCsv = string.Join(",", fps), focusCsv = string.Join(",", focus);
            int[] expectedIndices = Enumerable.Range(0, 52).Select(i => i * 2).ToArray();
            int[] indices;
            string clamped = FpsWireProduction.Clamp(fpsCsv, 512, out indices);
            if (!indices.SequenceEqual(expectedIndices)) return "retained source indices " + string.Join(",", indices);
            string expectedFps = string.Join(",", expectedIndices.Select(i => fps[i]));
            string expectedFocus = string.Join(",", expectedIndices.Select(i => focus[i]));
            if (clamped != expectedFps || clamped != LegacyClampTimeline(fpsCsv)) return "FPS bytes changed";
            string wire = FpsWireProduction.Wire(fpsCsv, focusCsv);
            string wireFps = FpsWireField(wire, "local_fps_timeline");
            string wireFocus = FpsWireField(wire, "local_fps_focus_timeline");
            if (wireFps != expectedFps) return "wire FPS bytes changed";
            if (wireFocus != expectedFocus) return "wire focus source indices differ: fps=" + wireFps.Split(',').Length + " focus=" + wireFocus.Split(',').Length;
            if (wireFps.Split(',').Length != 52 || wireFocus.Split(',').Length != 52) return "wire counts";

            // The old fallback can emit a partial first sample. Keep its
            // bytes and that sample's source index, or the whole first sample
            // when a comma boundary fits. Neither path invents an index.
            string error = ClampIndicesCase("1234,5678", 6, "1234", new[] { 0 });
            if (error != null) return error;
            error = ClampIndicesCase("123456789", 4, "1234", new[] { 0 });
            if (error != null) return error;
            error = ClampIndicesCase("v2|1234,5678", 9, "v2|1234", new[] { 0 });
            if (error != null) return error;
            error = ClampIndicesCase("1111,2222,3333,4444,5555", 6, "1111", new[] { 0 });
            if (error != null) return error;
            return ClampLegacyParity();
        }

        private static string FpsFocusClampShort()
        {
            const string fps = "60,75,90,120", focus = "1,0,0,0";
            string wire = FpsWireProduction.Wire(fps, focus, "80,85,90");
            if (FpsWireField(wire, "local_fps_timeline") != fps) return "short FPS changed";
            if (FpsWireField(wire, "local_fps_focus_timeline") != focus) return "short focus changed";
            if (FpsWireField(wire, "opp_fps_timeline") != "80,85,90") return "opponent FPS changed";
            int[] indices;
            if (FpsWireProduction.Clamp(fps, 512, out indices) != fps || !indices.SequenceEqual(new[] { 0, 1, 2, 3 })) return "short source indices";
            if (FpsWireProduction.Clamp(null, 512, out indices) != "" || indices.Length != 0) return "null clamp";
            if (FpsWireProduction.Clamp("", 512, out indices) != "" || indices.Length != 0) return "empty clamp";
            if (FpsFocusCore.EncodeRetained(null, new[] { 0 }) != "") return "absent focus invented";
            if (FpsFocusCore.EncodeRetained("1", new[] { 1 }) != "") return "missing focus invented";
            return null;
        }

        private static string ClampIndicesCase(string input, int max, string expected, int[] expectedIndices)
        {
            int[] indices;
            string actual = FpsWireProduction.Clamp(input, max, out indices);
            if (actual != expected || actual != LegacyClampTimeline(input, max)) return "backstop FPS bytes changed at cap " + max;
            if (!indices.SequenceEqual(expectedIndices)) return "backstop source indices at cap " + max + ": " + string.Join(",", indices);
            string flags = string.Join(",", Enumerable.Range(0, input.Split(',').Length).Select(i => i == 0 ? "0" : "1"));
            if (FpsFocusCore.EncodeRetained(flags, indices) != "0") return "backstop focus source changed";
            return null;
        }

        private static string ClampLegacyParity()
        {
            // Frozen base oracle below: regression evidence for the existing
            // bytes, independent from the new source-index calculations.
            var inputs = new List<string> { null, "", "v2|", "1", "123456789", ",", ",,", "1,", ",1", "1,22,333,4444", "v2|1,22,333,4444" };
            foreach (int count in new[] { 2, 3, 4, 5, 50, 102, 103, 104, 127, 260 })
            {
                string s = string.Join(",", Enumerable.Range(0, count).Select(i => (1000 + i).ToString(System.Globalization.CultureInfo.InvariantCulture)));
                inputs.Add(s); inputs.Add("v2|" + s);
            }
            foreach (string input in inputs)
            foreach (int max in new[] { -1, 0, 1, 2, 3, 4, 5, 6, 9, 16, 511, 512, 1024 })
            {
                string expected = null, actual = null;
                Type oldError = null, newError = null;
                try { expected = LegacyClampTimeline(input, max); } catch (Exception ex) { oldError = ex.GetType(); }
                try { int[] ignored; actual = FpsWireProduction.Clamp(input, max, out ignored); } catch (Exception ex) { newError = ex.GetType(); }
                if (expected != actual || oldError != newError) return "legacy clamp parity at cap " + max + " input length " + (input == null ? -1 : input.Length);
            }
            return null;
        }

        // Exact ClampTimeline body frozen from base 96d9f454, renamed only.
        // It is an expected-value oracle, never the implementation under test.
        private static string LegacyClampTimeline(string t, int max = 512)
        {
            t = t ?? "";
            if (t.Length <= max) return t;
            string prefix = "";
            if (t.StartsWith("v2|", StringComparison.Ordinal)) { prefix = "v2|"; t = t.Substring(3); }
            int budget = max - prefix.Length;
            var parts = t.Split(',');
            string joined = t;
            while (joined.Length > budget && parts.Length > 2)
            {
                var kept = new List<string>(parts.Length / 2 + 2) { parts[0] };
                for (int i = 2; i + 1 < parts.Length; i += 2) kept.Add(parts[i]);
                kept.Add(parts[parts.Length - 1]);
                parts = kept.ToArray();
                joined = string.Join(",", parts);
            }
            if (joined.Length > budget)
            {
                int cut = joined.LastIndexOf(',', Math.Min(budget, joined.Length) - 1);
                joined = cut > 0 ? joined.Substring(0, cut) : joined.Substring(0, Math.Max(0, budget));
            }
            return prefix + joined;
        }

        private static string SnapshotRoster()
        {
            NetworkReplicaDiagnostics.TestResetReplica(false);
            NetworkReplicaDiagnostics.TestActor(2, 102, 1, 5);
            NetworkReplicaDiagnostics.TestActor(3, 103, 1, 9);
            var core = new InboundStallCore();
            core.OnDepth(80, 0, NetworkReplicaDiagnostics.SnapshotRemoteStreams, 1);
            // Actor 2 left the live room roster. Its recorded game window
            // remains, while actor 4 is first observed after the stall opened.
            NetworkReplicaDiagnostics.TestActor(2, 102, 1, 5, false);
            NetworkReplicaDiagnostics.TestActor(3, 103, 2, 10);
            NetworkReplicaDiagnostics.TestActor(4, 104, 1, 6);
            NetworkReplicaDiagnostics.TestActor(5, 105, 0, 0);
            var actors = new int[16]; var batches = new long[16];
            int n = NetworkReplicaDiagnostics.SnapshotRemoteStreams(actors, batches);
            if (n != 3 || !actors.Take(n).Contains(2) || !actors.Take(n).Contains(4))
                return "current snapshot lost departed actor, missed later joiner, or included empty view: n=" + n;
            core.OnFrame(18);
            string line = core.OnDepth(2, 1501, NetworkReplicaDiagnostics.SnapshotRemoteStreams, 1, 18);
            if (line == null || Field(line, "remoteStreams") != "2" || Field(line, "stopped") != "1")
                return "opening cohort must retain departed actor and omit later joiner: " + line;
            return null;
        }

        private static string SnapshotSpectator()
        {
            NetworkReplicaDiagnostics.TestResetReplica(true);
            NetworkReplicaDiagnostics.TestActor(2, 0, 1, 5);
            NetworkReplicaDiagnostics.TestActor(3, 103, 1, 8);
            var actors = new int[16]; var batches = new long[16];
            int n = NetworkReplicaDiagnostics.SnapshotRemoteStreams(actors, batches);
            int i = Array.IndexOf(actors, 2, 0, n);
            if (n != 2 || i < 0 || batches[i] != 5) return "spectator non-Player view omitted";
            // No Player view became known, but actor-level accepted traffic
            // advanced. This explicitly establishes the spectator limitation.
            NetworkReplicaDiagnostics.TestActor(2, 0, 2, 6);
            n = NetworkReplicaDiagnostics.SnapshotRemoteStreams(actors, batches);
            i = Array.IndexOf(actors, 2, 0, n);
            if (n != 2 || i < 0 || batches[i] != 6) return "spectator aggregate counter did not advance";
            SpectatorSession.IsLocalSpectator = false;
            n = NetworkReplicaDiagnostics.SnapshotRemoteStreams(actors, batches);
            if (n != 1 || actors[0] != 3) return "fighter snapshot admitted an unconfirmed Player view";
            return null;
        }

        private static string SnapshotOverflow()
        {
            NetworkReplicaDiagnostics.TestResetReplica(false);
            for (int i = 1; i <= 20; i++) NetworkReplicaDiagnostics.TestActor(i, 100 + i, 1, i);
            var actors = new int[16]; var batches = new long[16];
            int n = NetworkReplicaDiagnostics.SnapshotRemoteStreams(actors, batches);
            if (n != 16 || actors.Distinct().Count() != 16) return "overflow snapshot n=" + n;
            for (int i = 0; i < n; i++)
                if (actors[i] < 1 || actors[i] > 20 || batches[i] != actors[i]) return "misaligned overflow entry=" + i;
            if (NetworkReplicaDiagnostics.SnapshotRemoteStreams(new int[4], new long[2]) != 2)
                return "shorter batches array bound";
            if (NetworkReplicaDiagnostics.SnapshotRemoteStreams(null, batches) != 0 ||
                NetworkReplicaDiagnostics.SnapshotRemoteStreams(actors, null) != 0) return "null array bound";
            return null;
        }

        private static string JitterTies()
        {
            var budget = new NetJitterBudgetCore();
            bool reserve;
            for (int actor = 2; actor <= 5; actor++) budget.Offer(actor, 2000, 40, 1960, 1, out reserve);
            string top = Field(budget.SummaryFields(), "jitterTop");
            if (top != "a2:2000ms/s40/x1960/g1;a3:2000ms/s40/x1960/g1;a4:2000ms/s40/x1960/g1")
                return "equal-gap order " + top;
            return null;
        }

        private static string JitterSameRoomReset()
        {
            NetworkReplicaDiagnostics.TestResetReplica(false);
            NetworkReplicaDiagnostics.TestPrimeSameRoom();
            var budget = NetworkReplicaDiagnostics.TestJitterBudget;
            bool reserve;
            int emitted = 0;
            for (int i = 0; i < 12; i++) if (budget.Offer(2, 350, 40, 310, 1, out reserve)) emitted++;
            for (int i = 0; i < 4; i++) if (budget.Offer(3, 2000 + i, 40, 1960 + i, 1, out reserve)) emitted++;
            if (budget.Offer(4, 8000, 40, 7960, 1, out reserve)) return "exhausted budget emitted";
            string before = budget.SummaryFields();
            if (emitted != 16 || Field(before, "jitterQualifying") != "17" || Field(before, "jitterSuppressed") != "1")
                return "setup " + before;
            NetworkReplicaDiagnostics.OnRoomJoined(); // exact production callback text
            string after = budget.SummaryFields();
            if (budget.Used != 0 || budget.Spent) return "same-room callback did not restore line slots: " + after;
            if (Field(after, "jitterQualifying") != "17" || Field(after, "jitterSuppressed") != "1" ||
                Field(after, "jitterTop") != Field(before, "jitterTop")) return "same-room callback erased evidence: " + after;
            if (VanillaFixSupport.DiagResets.Count != 3 || VanillaFixSupport.DiagResets[0] != NetworkReplicaDiagnostics.JitterDiagKey)
                return "production callback did not take same-room diagnostics-reset branch";
            if (!budget.Offer(2, 350, 40, 310, 1, out reserve) || budget.Used != 1)
                return "restored same-room slot unavailable";
            // Cumulative emitted lines are now 17 across this callback. The
            // contract is a line budget between resets, with retained evidence.
            return null;
        }

        private static string LagSettingFlips()
        {
            Plugin.Log = new LogSink();
            Plugin.LagNoticesEnabled = new BepInEx.Configuration.ConfigEntry<bool> { Value = true };
            // Other cases replace the test configuration object. Model fresh
            // startup for this case so the REAL EnsureStartup subscribes to
            // this object, and every flip reaches the real event handler.
            var flags = System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static;
            typeof(LagNotices).GetField("_startupDone", flags).SetValue(null, false);
            GameStateWatcher.PlainOneVOne = true;
            RoomActors.LocalIsSpectator = false;
            BroadcastMode.IsBroadcastIdentity = false;
            NetworkSeatTelemetry.Ring.Clear();
            LagNotices.OnGameStarted();
            int seq = 0;
            Action<int, bool> window = (ping, keyed) =>
            {
                NetworkSeatTelemetry.Ring.Add(new NetworkSeatTelemetry.WindowFacts {
                    Seq = ++seq, WorstMs = 18, OwnPing = ping, PeerRtt = 40,
                    OppActor = keyed ? 2 : 0, OppId = keyed ? "A" : null });
                LagNotices.OnWindowClosed();
            };
            window(40, false); window(40, false);
            for (int i = 0; i < 3; i++) window(200, true);
            if (LagNotices.ActiveLines.Length != 1) return "first OWN_PING entry missing";
            var slots = (LagNotices.Slot[])typeof(LagNotices).GetField("_slots", flags).GetValue(null);
            // Age only the real slot clock origin; production OnWindowClosed
            // and Step still perform every transition and count every edge.
            slots[(int)LagNotices.State.OWN_PING].EnterS -= 6;
            for (int i = 0; i < 3; i++) window(40, true);
            for (int i = 0; i < 3; i++) window(200, true);
            if (!Plugin.Log.Lines.Any(l => l.Contains("state=OWN_PING edge=suppressed"))) return "real cooldown suppression missing";
            Plugin.LagNoticesEnabled.Value = false;
            window(200, false);
            Plugin.LagNoticesEnabled.Value = true;
            window(40, false);
            for (int i = 0; i < 3; i++) window(200, true);
            if (LagNotices.ActiveLines.Length != 1) return "post-flip OWN_PING entry missing";
            Plugin.LagNoticesEnabled.Value = false;
            if (LagNotices.ActiveLines.Length != 0) return "setting-off callback did not clear HUD immediately";
            Plugin.LagNoticesEnabled.Value = true;
            LagNotices.OnGameEnded();
            string gate = Plugin.Log.Lines.LastOrDefault(l => l.StartsWith("[LAG-NOTICE-GATE] ", StringComparison.Ordinal));
            string expected = "[LAG-NOTICE-GATE] windows=16 setting_off=1 not_plain_1v1=0 unkeyed=3 evaluated=12 enters=2 suppressed=1";
            if (gate != expected) return "gate across flips " + gate + " expected " + expected;
            return null;
        }

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
