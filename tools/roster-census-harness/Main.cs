using CompetitiveRounds;
using System;
using System.Collections.Generic;

namespace CompetitiveRounds.Harness
{
    using Seat = RosterCensus.SeatObservation;

    /// <summary>The roster-census gate.
    ///
    /// Three verdicts, and all three have to hold for exit 0:
    ///
    ///   BASELINE  the real implementation passes every case, and ran more
    ///             than zero of them.
    ///   MUTANTS   every wrong implementation REDS. Each one is the natural
    ///             wrong edit for the assertion it is paired with, so a case
    ///             that cannot fail is caught here rather than believed
    ///             (#342).
    ///   CONTROLS  every behaviour-preserving implementation stays GREEN with
    ///             the same number of passing cases as the baseline. Without
    ///             this the mutants would only prove the suite reacts to
    ///             CHANGE, not that it reacts to the change in BEHAVIOUR.
    ///
    /// The mutants live here and not in the plugin: production code with a
    /// mutation switch in it is a hazard, and the delegate seam on SelfTest
    /// is enough to drive the assertions from outside.</summary>
    internal static class Program
    {
        private static int Main(string[] args)
        {
            bool quiet = Array.IndexOf(args, "--quiet") >= 0;

            Console.WriteLine("=== roster-census-harness ===");
            Console.WriteLine("baseline: RosterCensus.FormatCensus + RosterCensus.SessionLineBudget");

            RosterCensus.SelfTestResult baseline;
            try { baseline = RosterCensus.SelfTest(); }
            catch (Exception ex)
            {
                Console.WriteLine("[baseline] SelfTest THREW: " + ex);
                Console.WriteLine("roster-census-harness verdict=THREW");
                return 2;
            }

            if (!quiet) Console.Write(baseline.Report.ToString());
            int baselineRun = baseline.Passed + baseline.Failed;
            Console.WriteLine("baseline run=" + baselineRun
                              + " pass=" + baseline.Passed
                              + " fail=" + baseline.Failed);

            bool ok = true;
            if (baselineRun == 0)
            {
                Console.WriteLine("GATE FAIL | the baseline ran zero cases - a suite that asserts nothing exits green");
                ok = false;
            }
            if (baseline.Failed != 0)
            {
                Console.WriteLine("GATE FAIL | the baseline has failing cases");
                ok = false;
            }

            // ── MUTANTS: each must red ───────────────────────────────────
            Console.WriteLine();
            Console.WriteLine("--- mutants (each MUST red) ---");

            ok &= Mutant("drops-the-rows-it-could-not-read", DropUnreadable, Real,
                         "an unreadable seat still emits", quiet);
            ok &= Mutant("omits-the-probe-token", OmitProbeToken, Real,
                         "every census line carries the probe token", quiet);
            ok &= Mutant("collapses-the-boundary-to-one-summary-line", CollapseCardinality, Real,
                         "one line per seat, one seat per line", quiet);
            ok &= Mutant("reports-an-unreadable-position-as-the-origin", OriginSentinel, Real,
                         "a non-finite position is a question mark", quiet);
            ok &= Mutant("clamps-the-position-into-map-bounds", ClampPosition, Real,
                         "an out-of-bounds position is reported verbatim", quiet);
            ok &= Mutant("caps-without-logging-its-exhaustion", RosterCensus.FormatCensus, Silent,
                         "a boundary that does not fit is refused entire and announced", quiet);

            // ── CONTROLS: each must stay green, at the baseline's count ──
            Console.WriteLine();
            Console.WriteLine("--- negative controls (each MUST stay green) ---");

            ok &= Control("equivalent-census-built-in-reverse", EquivalentCensus, Real, baseline.Passed, quiet);
            ok &= Control("equivalent-budget-counting-remaining", RosterCensus.FormatCensus, Equivalent, baseline.Passed, quiet);

            Console.WriteLine();
            Console.WriteLine("roster-census-harness baselineRun=" + baselineRun
                              + " baselineFail=" + baseline.Failed
                              + " verdict=" + (ok ? "PASS" : "FAIL"));
            return ok ? 0 : 1;
        }

        // ── runners ──────────────────────────────────────────────────────

        /// <summary>A mutant counts as caught only when the case it is PAIRED
        /// with reds. "Some case somewhere failed" is not evidence that the
        /// paired assertion can fail, and an assertion that cannot fail is
        /// worse than no assertion (#342).</summary>
        private static bool Mutant(string name, RosterCensus.CensusEmitter emit,
                                   RosterCensus.BudgetFactory budget, string pairedCase, bool quiet)
        {
            RosterCensus.SelfTestResult r;
            try { r = RosterCensus.SelfTest(emit, budget); }
            catch (Exception ex)
            {
                // A mutant that throws has not been SHOWN to red on an
                // assertion, so it does not count as caught.
                Console.WriteLine("MUTANT THREW | " + name + " | " + ex.GetType().Name + ": " + ex.Message);
                return false;
            }
            string failures = FailingCases(r);
            bool pairedRed = failures.Contains("case=" + pairedCase);
            Console.WriteLine((pairedRed ? "caught  " : "ESCAPED ") + "| mutant=" + name
                              + " | pass=" + r.Passed + " fail=" + r.Failed
                              + " | paired=\"" + pairedCase + "\" red=" + pairedRed);
            if (!quiet) Console.Write(pairedRed ? failures : r.Report.ToString());
            return pairedRed;
        }

        private static bool Control(string name, RosterCensus.CensusEmitter emit,
                                    RosterCensus.BudgetFactory budget, int baselinePassed, bool quiet)
        {
            RosterCensus.SelfTestResult r;
            try { r = RosterCensus.SelfTest(emit, budget); }
            catch (Exception ex)
            {
                Console.WriteLine("CONTROL THREW | " + name + " | " + ex.GetType().Name + ": " + ex.Message);
                return false;
            }
            bool green = r.Failed == 0 && r.Passed == baselinePassed;
            Console.WriteLine((green ? "green  " : "REDDENED") + " | control=" + name
                              + " | pass=" + r.Passed + " fail=" + r.Failed
                              + " (baseline pass=" + baselinePassed + ")");
            if (!green && !quiet) Console.Write(r.Report.ToString());
            return green;
        }

        private static string FailingCases(RosterCensus.SelfTestResult r)
        {
            var sb = new System.Text.StringBuilder();
            foreach (string line in r.Report.ToString().Split('\n'))
                if (line.StartsWith("FAIL", StringComparison.Ordinal)) sb.Append("    ").Append(line).Append('\n');
            return sb.ToString();
        }

        // ── the real implementations, named so the pairings read ─────────

        private static RosterCensus.ILineBudget Real(int cap)
        {
            return new RosterCensus.SessionLineBudget(cap);
        }

        // ── mutant emitters ──────────────────────────────────────────────

        /// <summary>The natural, wrong, defensive edit and the whole shape of
        /// the defect the census exists to catch: skip the seats whose state
        /// could not be read. Pairs with the unreadable-seat and cardinality
        /// cases.</summary>
        private static List<string> DropUnreadable(int generation, string boundary, IList<Seat> seats)
        {
            var kept = new List<Seat>();
            int n = seats == null ? 0 : seats.Count;
            for (int i = 0; i < n; i++)
                if (seats[i].ActiveKnown && seats[i].PositionKnown) kept.Add(seats[i]);
            return RosterCensus.FormatCensus(generation, boundary, kept);
        }

        /// <summary>The token stops being emitted - a rename, a "tidy up the
        /// log line" pass. Pairs with the probe-token case (#306).</summary>
        private static List<string> OmitProbeToken(int generation, string boundary, IList<Seat> seats)
        {
            var lines = RosterCensus.FormatCensus(generation, boundary, seats);
            for (int i = 0; i < lines.Count; i++)
                lines[i] = lines[i].Replace(" " + RosterCensus.Probe, string.Empty);
            return lines;
        }

        /// <summary>One line per BOUNDARY instead of one per seat - the
        /// "reduce log volume" edit. Pairs with every cardinality case.</summary>
        private static List<string> CollapseCardinality(int generation, string boundary, IList<Seat> seats)
        {
            int n = seats == null ? 0 : seats.Count;
            return new List<string>
            {
                RosterCensus.Prefix + " gen=" + generation + " boundary=" + boundary
                + " seats=" + n + " " + RosterCensus.Probe
            };
        }

        /// <summary>A position that could not be read becomes 0,0 - a
        /// sentinel that looks like a real position and so invents a fact.
        /// Pairs with the non-finite-position case.</summary>
        private static List<string> OriginSentinel(int generation, string boundary, IList<Seat> seats)
        {
            var rewritten = new List<Seat>();
            int n = seats == null ? 0 : seats.Count;
            for (int i = 0; i < n; i++)
            {
                Seat s = seats[i];
                if (!s.PositionKnown || NotFinite(s.X) || NotFinite(s.Y))
                {
                    s.PositionKnown = true;
                    s.X = 0f;
                    s.Y = 0f;
                }
                rewritten.Add(s);
            }
            return RosterCensus.FormatCensus(generation, boundary, rewritten);
        }

        /// <summary>The position is clamped into plausible map bounds - the
        /// "that reading is obviously wrong, tidy it" edit, which destroys
        /// exactly the datum the census was added for. Pairs with the
        /// out-of-bounds case.</summary>
        private static List<string> ClampPosition(int generation, string boundary, IList<Seat> seats)
        {
            var rewritten = new List<Seat>();
            int n = seats == null ? 0 : seats.Count;
            for (int i = 0; i < n; i++)
            {
                Seat s = seats[i];
                if (s.PositionKnown)
                {
                    s.X = Clamp(s.X);
                    s.Y = Clamp(s.Y);
                }
                rewritten.Add(s);
            }
            return RosterCensus.FormatCensus(generation, boundary, rewritten);
        }

        private static float Clamp(float v)
        {
            if (NotFinite(v)) return 0f;
            if (v > 100f) return 100f;
            if (v < -100f) return -100f;
            return v;
        }

        private static bool NotFinite(float v)
        {
            return float.IsNaN(v) || float.IsInfinity(v);
        }

        // ── mutant budget ────────────────────────────────────────────────

        private static RosterCensus.ILineBudget Silent(int cap)
        {
            return new SilentBudget(cap);
        }

        /// <summary>Refuses exactly like the real budget and never says so -
        /// the log simply stops, and a reader cannot tell a truncated census
        /// from a census that found nothing (#430).</summary>
        private sealed class SilentBudget : RosterCensus.ILineBudget
        {
            private readonly int _cap;
            private int _used;

            internal SilentBudget(int cap) { _cap = cap < 0 ? 0 : cap; }

            public bool TryReserve(int generation, string boundary, int lines, out string exhaustionNotice)
            {
                exhaustionNotice = null;
                if (lines <= 0) return false;
                if (_used <= _cap - lines) { _used += lines; return true; }
                return false;
            }
        }

        // ── negative controls ────────────────────────────────────────────

        /// <summary>Identical output, built by a different route. It must
        /// stay green, which is what makes the mutants above evidence about
        /// BEHAVIOUR rather than about the source file.</summary>
        private static List<string> EquivalentCensus(int generation, string boundary, IList<Seat> seats)
        {
            var lines = new List<string>();
            int n = seats == null ? 0 : seats.Count;
            for (int i = n - 1; i >= 0; i--)
                lines.Add(RosterCensus.FormatLine(generation, boundary, seats[i]));
            lines.Reverse();
            return lines;
        }

        private static RosterCensus.ILineBudget Equivalent(int cap)
        {
            return new EquivalentBudget(cap);
        }

        /// <summary>Same rule, counting what is LEFT instead of what is
        /// spent. Must stay green.</summary>
        private sealed class EquivalentBudget : RosterCensus.ILineBudget
        {
            private readonly int _cap;
            private int _remaining;
            private bool _announced;

            internal EquivalentBudget(int cap)
            {
                _cap = cap < 0 ? 0 : cap;
                _remaining = _cap;
            }

            public bool TryReserve(int generation, string boundary, int lines, out string exhaustionNotice)
            {
                exhaustionNotice = null;
                if (lines <= 0) return false;
                if (lines <= _remaining) { _remaining -= lines; return true; }
                if (!_announced)
                {
                    _announced = true;
                    exhaustionNotice = RosterCensus.FormatExhaustionNotice(
                        generation, boundary, _cap, _cap - _remaining, lines);
                }
                return false;
            }
        }
    }
}
