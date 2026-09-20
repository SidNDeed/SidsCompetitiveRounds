using CompetitiveRounds;
using System;
using System.Collections.Generic;
using System.Globalization;

namespace CompetitiveRounds.Harness
{
    using Seat = RosterCensus.SeatObservation;
    using Ctx = RosterCensus.BoundaryContext;

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
    /// mutation switch in it is a hazard, and the three delegate seams on
    /// SelfTest (the census, the budget, the notices) are enough to drive the
    /// assertions from outside.</summary>
    internal static class Program
    {
        private static int Main(string[] args)
        {
            bool quiet = Array.IndexOf(args, "--quiet") >= 0;

            Console.WriteLine("=== roster-census-harness ===");
            Console.WriteLine("baseline: RosterCensus.FormatCensus + SessionLineBudget + the notice builders");

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

            // ── MUTANTS: each must red on the case it is PAIRED with ─────
            Console.WriteLine();
            Console.WriteLine("--- mutants (each MUST red on its paired case) ---");

            int mutants = 0, caught = 0;

            caught += Mutant(ref mutants, "drops-the-rows-it-could-not-read",
                             Census(DropUnreadable),
                             "an unreadable seat still emits", quiet);
            caught += Mutant(ref mutants, "omits-the-probe-token",
                             Census(OmitProbeToken),
                             "every census line carries the probe token", quiet);
            caught += Mutant(ref mutants, "collapses-the-boundary-to-one-summary-line",
                             Census(CollapseCardinality),
                             "one line per seat, one seat per line", quiet);
            caught += Mutant(ref mutants, "reports-an-unreadable-position-as-the-origin",
                             Census(OriginSentinel),
                             "a non-finite position is a question mark", quiet);
            caught += Mutant(ref mutants, "clamps-the-position-into-map-bounds",
                             Census(ClampPosition),
                             "an out-of-bounds position is reported verbatim", quiet);

            // The map-boundary finding: one sample, or a settled sample that
            // cannot be told apart from the call-in that preceded it, is the
            // defect this pass exists to close.
            caught += Mutant(ref mutants, "collapses-the-two-map-samples-to-one-label",
                             Census(CollapseMapLabels),
                             "the three boundary labels reach the line and the two map samples differ", quiet);
            caught += Mutant(ref mutants, "reports-an-absent-call-in-delay-as-zero",
                             Census(ZeroAbsentDelay),
                             "the settled sample carries its measured delay and the call-in carries none", quiet);

            caught += Mutant(ref mutants, "drops-the-self-marker",
                             Census(DropSelfMarker),
                             "the reporting seat's own row is marked self", quiet);
            caught += Mutant(ref mutants, "drops-the-fighter-count",
                             Census(DropFighterCount),
                             "the fighter count and the row count are both on the line", quiet);

            caught += Mutant(ref mutants, "caps-without-logging-its-exhaustion",
                             Budget(Silent),
                             "a boundary that does not fit is refused entire and announced", quiet);
            caught += Mutant(ref mutants, "announces-its-exhaustion-once-per-session",
                             Budget(AnnounceOnce),
                             "a standing refusal re-announces after its interval", quiet);
            caught += Mutant(ref mutants, "resumes-when-a-later-boundary-happens-to-fit",
                             Budget(Resuming),
                             "the census does not resume after the cap has refused", quiet);

            caught += Mutant(ref mutants, "drops-the-reason-from-its-notices",
                             Notices(ReasonlessEmpty, ReasonlessDeclined),
                             "an empty and a declined boundary each say so, with a reason", quiet);

            ok &= caught == mutants;

            // ── CONTROLS: each must stay green, at the baseline's count ──
            Console.WriteLine();
            Console.WriteLine("--- negative controls (each MUST stay green) ---");

            int controls = 0, green = 0;

            green += Control(ref controls, "equivalent-census-built-in-reverse",
                             Census(EquivalentCensus), baseline.Passed, quiet);
            green += Control(ref controls, "equivalent-budget-counting-remaining",
                             Budget(Equivalent), baseline.Passed, quiet);
            green += Control(ref controls, "equivalent-notices-built-by-concatenation",
                             Notices(ConcatEmpty, ConcatDeclined), baseline.Passed, quiet);

            ok &= green == controls;

            Console.WriteLine();
            Console.WriteLine("roster-census-harness baselineRun=" + baselineRun
                              + " baselineFail=" + baseline.Failed
                              + " mutants=" + mutants + " caught=" + caught
                              + " controls=" + controls + " green=" + green
                              + " verdict=" + (ok ? "PASS" : "FAIL"));
            return ok ? 0 : 1;
        }

        // ── the variant under test ───────────────────────────────────────

        /// <summary>One run's four implementations. Everything not named is
        /// the real one, so each mutant differs from the baseline in exactly
        /// the way its name says.</summary>
        private sealed class Variant
        {
            internal RosterCensus.CensusEmitter Emit = RosterCensus.FormatCensus;
            internal RosterCensus.BudgetFactory Budget = Real;
            internal RosterCensus.NoticeFormatter Empty = RosterCensus.FormatEmptyRosterNotice;
            internal RosterCensus.NoticeFormatter Declined = RosterCensus.FormatDeclinedNotice;
        }

        private static Variant Census(RosterCensus.CensusEmitter emit)
        {
            var v = new Variant();
            v.Emit = emit;
            return v;
        }

        private static Variant Budget(RosterCensus.BudgetFactory budget)
        {
            var v = new Variant();
            v.Budget = budget;
            return v;
        }

        private static Variant Notices(RosterCensus.NoticeFormatter empty, RosterCensus.NoticeFormatter declined)
        {
            var v = new Variant();
            v.Empty = empty;
            v.Declined = declined;
            return v;
        }

        // ── runners ──────────────────────────────────────────────────────

        /// <summary>A mutant counts as caught only when the case it is PAIRED
        /// with reds. "Some case somewhere failed" is not evidence that the
        /// paired assertion can fail, and an assertion that cannot fail is
        /// worse than no assertion (#342).</summary>
        private static int Mutant(ref int total, string name, Variant v, string pairedCase, bool quiet)
        {
            total++;
            RosterCensus.SelfTestResult r;
            try { r = RosterCensus.SelfTest(v.Emit, v.Budget, v.Empty, v.Declined); }
            catch (Exception ex)
            {
                // A mutant that throws has not been SHOWN to red on an
                // assertion, so it does not count as caught.
                Console.WriteLine("MUTANT THREW | " + name + " | " + ex.GetType().Name + ": " + ex.Message);
                return 0;
            }
            string failures = FailingCases(r);
            bool pairedRed = failures.Contains("case=" + pairedCase);
            Console.WriteLine((pairedRed ? "caught  " : "ESCAPED ") + "| mutant=" + name
                              + " | pass=" + r.Passed + " fail=" + r.Failed
                              + " | paired=\"" + pairedCase + "\" red=" + pairedRed);
            if (!quiet) Console.Write(pairedRed ? failures : r.Report.ToString());
            return pairedRed ? 1 : 0;
        }

        private static int Control(ref int total, string name, Variant v, int baselinePassed, bool quiet)
        {
            total++;
            RosterCensus.SelfTestResult r;
            try { r = RosterCensus.SelfTest(v.Emit, v.Budget, v.Empty, v.Declined); }
            catch (Exception ex)
            {
                Console.WriteLine("CONTROL THREW | " + name + " | " + ex.GetType().Name + ": " + ex.Message);
                return 0;
            }
            bool green = r.Failed == 0 && r.Passed == baselinePassed;
            Console.WriteLine((green ? "green   " : "REDDENED") + "| control=" + name
                              + " | pass=" + r.Passed + " fail=" + r.Failed
                              + " (baseline pass=" + baselinePassed + ")");
            if (!green && !quiet) Console.Write(r.Report.ToString());
            return green ? 1 : 0;
        }

        private static string FailingCases(RosterCensus.SelfTestResult r)
        {
            var sb = new System.Text.StringBuilder();
            foreach (string line in r.Report.ToString().Split('\n'))
                if (line.StartsWith("FAIL", StringComparison.Ordinal)) sb.Append("    ").Append(line).Append('\n');
            return sb.ToString();
        }

        // ── the real budget, named so the pairings read ──────────────────

        private static RosterCensus.ILineBudget Real(int cap, int interval, int ceiling)
        {
            return new RosterCensus.SessionLineBudget(cap, interval, ceiling);
        }

        // ── shared line surgery ──────────────────────────────────────────

        /// <summary>Removes one whole <c>key=value</c> field. The natural
        /// shape of "this field is noise, drop it".</summary>
        private static string StripField(string line, string key)
        {
            if (line == null) return null;
            string needle = " " + key + "=";
            int i = line.IndexOf(needle, StringComparison.Ordinal);
            if (i < 0) return line;
            int end = line.IndexOf(' ', i + needle.Length);
            return end < 0 ? line.Substring(0, i) : line.Substring(0, i) + line.Substring(end);
        }

        // ── mutant emitters ──────────────────────────────────────────────

        /// <summary>The natural, wrong, defensive edit and the whole shape of
        /// the defect the census exists to catch: skip the seats whose state
        /// could not be read. Pairs with the unreadable-seat and cardinality
        /// cases.</summary>
        private static List<string> DropUnreadable(Ctx ctx, IList<Seat> seats)
        {
            var kept = new List<Seat>();
            int n = seats == null ? 0 : seats.Count;
            for (int i = 0; i < n; i++)
                if (seats[i].ActiveKnown && seats[i].PositionKnown) kept.Add(seats[i]);
            return RosterCensus.FormatCensus(ctx, kept);
        }

        /// <summary>The token stops being emitted - a rename, a "tidy up the
        /// log line" pass. Pairs with the probe-token case (#306).</summary>
        private static List<string> OmitProbeToken(Ctx ctx, IList<Seat> seats)
        {
            var lines = RosterCensus.FormatCensus(ctx, seats);
            for (int i = 0; i < lines.Count; i++)
                lines[i] = lines[i].Replace(" " + RosterCensus.Probe, string.Empty);
            return lines;
        }

        /// <summary>One line per BOUNDARY instead of one per seat - the
        /// "reduce log volume" edit. Pairs with every cardinality case.</summary>
        private static List<string> CollapseCardinality(Ctx ctx, IList<Seat> seats)
        {
            int n = seats == null ? 0 : seats.Count;
            return new List<string>
            {
                RosterCensus.Prefix + " gen=" + ctx.Generation + " boundary=" + ctx.Boundary
                + " seats=" + n + " " + RosterCensus.Probe
            };
        }

        /// <summary>A position that could not be read becomes 0,0 - a
        /// sentinel that looks like a real position and so invents a fact.
        /// Pairs with the non-finite-position case.</summary>
        private static List<string> OriginSentinel(Ctx ctx, IList<Seat> seats)
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
            return RosterCensus.FormatCensus(ctx, rewritten);
        }

        /// <summary>The position is clamped into plausible map bounds - the
        /// "that reading is obviously wrong, tidy it" edit, which destroys
        /// exactly the datum the census was added for. Pairs with the
        /// out-of-bounds case.</summary>
        private static List<string> ClampPosition(Ctx ctx, IList<Seat> seats)
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
            return RosterCensus.FormatCensus(ctx, rewritten);
        }

        /// <summary>The two map samples print the same label - "they are both
        /// the map boundary, why two names". It puts the reader back where
        /// the finding found them: unable to tell the state this seat
        /// inherited from the state on the map being loaded.</summary>
        private static List<string> CollapseMapLabels(Ctx ctx, IList<Seat> seats)
        {
            if (ctx.Boundary == RosterCensus.BoundaryMapSettled)
                ctx.Boundary = RosterCensus.BoundaryMapCallIn;
            return RosterCensus.FormatCensus(ctx, seats);
        }

        /// <summary>"A missing number is zero" - which turns "taken at the
        /// call-in" into the claim "taken 0 ms after the call-in", a fact
        /// nobody measured.</summary>
        private static List<string> ZeroAbsentDelay(Ctx ctx, IList<Seat> seats)
        {
            if (ctx.SinceCallInMs < 0) ctx.SinceCallInMs = 0;
            return RosterCensus.FormatCensus(ctx, seats);
        }

        /// <summary>The self marker goes away - "the reader can work out which
        /// actor we are". They cannot: no census line and no other startup
        /// line prints the local ActorNumber, and the local row's absent view
        /// counter then reads exactly like a remote seat that went
        /// silent.</summary>
        private static List<string> DropSelfMarker(Ctx ctx, IList<Seat> seats)
        {
            var lines = RosterCensus.FormatCensus(ctx, seats);
            for (int i = 0; i < lines.Count; i++) lines[i] = StripField(lines[i], "self");
            return lines;
        }

        /// <summary>The latch-filtered fighter count goes away - "the reader
        /// can count the rows". Counting rows gives the census set; the bar
        /// compares it against a DIFFERENT set, and dropping this field is
        /// what makes that comparison a guess.</summary>
        private static List<string> DropFighterCount(Ctx ctx, IList<Seat> seats)
        {
            var lines = RosterCensus.FormatCensus(ctx, seats);
            for (int i = 0; i < lines.Count; i++) lines[i] = StripField(lines[i], "fighters");
            return lines;
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

        // ── mutant budgets ───────────────────────────────────────────────

        private static RosterCensus.ILineBudget Silent(int cap, int interval, int ceiling)
        {
            return new SilentBudget(cap);
        }

        private static RosterCensus.ILineBudget AnnounceOnce(int cap, int interval, int ceiling)
        {
            return new AnnounceOnceBudget(cap);
        }

        private static RosterCensus.ILineBudget Resuming(int cap, int interval, int ceiling)
        {
            return new ResumingBudget(cap, interval, ceiling);
        }

        /// <summary>Refuses exactly like the real budget and never says so -
        /// the log simply stops, and a reader cannot tell a truncated census
        /// from a census that found nothing (#430).</summary>
        private sealed class SilentBudget : RosterCensus.ILineBudget
        {
            private readonly int _cap;
            private int _used;
            private bool _exhausted;

            internal SilentBudget(int cap) { _cap = cap < 0 ? 0 : cap; }

            public bool TryReserve(Ctx ctx, int lines, out string exhaustionNotice)
            {
                exhaustionNotice = null;
                if (lines <= 0) return false;
                if (!_exhausted && _used <= _cap - lines) { _used += lines; return true; }
                _exhausted = true;
                return false;
            }
        }

        /// <summary>THE PRE-FIX NOTICE RULE. Latches correctly, refuses
        /// correctly, and announces only the FIRST refusal of the session - so
        /// every window after that one is both empty and unmarked, which is
        /// the state a reader cannot tell from a patch that never
        /// attached.</summary>
        private sealed class AnnounceOnceBudget : RosterCensus.ILineBudget
        {
            private readonly int _cap;
            private int _used;
            private bool _exhausted;
            private bool _announced;

            internal AnnounceOnceBudget(int cap) { _cap = cap < 0 ? 0 : cap; }

            public bool TryReserve(Ctx ctx, int lines, out string exhaustionNotice)
            {
                exhaustionNotice = null;
                if (lines <= 0) return false;
                if (!_exhausted && _used <= _cap - lines) { _used += lines; return true; }
                _exhausted = true;
                if (!_announced)
                {
                    _announced = true;
                    exhaustionNotice = RosterCensus.FormatExhaustionNotice(ctx, _cap, _used, lines, 0, false);
                }
                return false;
            }
        }

        /// <summary>THE PRE-FIX CAP ARITHMETIC. Announces on the real rule but
        /// charges against remaining headroom with no latch, so after the cap
        /// has refused a three-seat boundary a two-seat one still emits: the
        /// record resumes as silently as it stopped.</summary>
        private sealed class ResumingBudget : RosterCensus.ILineBudget
        {
            private readonly int _cap;
            private readonly RosterCensus.NoticeThrottle _notices;
            private int _used;

            internal ResumingBudget(int cap, int interval, int ceiling)
            {
                _cap = cap < 0 ? 0 : cap;
                _notices = new RosterCensus.NoticeThrottle(interval, ceiling);
            }

            public bool TryReserve(Ctx ctx, int lines, out string exhaustionNotice)
            {
                exhaustionNotice = null;
                if (lines <= 0) return false;
                if (_used <= _cap - lines) { _used += lines; return true; }
                int suppressed;
                bool final;
                if (_notices.ShouldFire(ctx.Generation, out suppressed, out final))
                    exhaustionNotice = RosterCensus.FormatExhaustionNotice(ctx, _cap, _used, lines, suppressed, final);
                return false;
            }
        }

        // ── mutant notices ───────────────────────────────────────────────

        /// <summary>The notice keeps the probe token and loses the REASON -
        /// "census=empty says it all". It does not: the four ways a boundary
        /// produces no rows have four different diagnoses behind them.</summary>
        private static string ReasonlessEmpty(Ctx ctx, string reason, int suppressed, bool final)
        {
            return StripField(RosterCensus.FormatEmptyRosterNotice(ctx, reason, suppressed, final), "reason");
        }

        private static string ReasonlessDeclined(Ctx ctx, string reason, int suppressed, bool final)
        {
            return StripField(RosterCensus.FormatDeclinedNotice(ctx, reason, suppressed, final), "reason");
        }

        // ── negative controls ────────────────────────────────────────────

        /// <summary>Identical output, built by a different route. It must
        /// stay green, which is what makes the mutants above evidence about
        /// BEHAVIOUR rather than about the source file.</summary>
        private static List<string> EquivalentCensus(Ctx ctx, IList<Seat> seats)
        {
            int n = seats == null ? 0 : seats.Count;
            ctx.Seats = n;
            var lines = new List<string>();
            for (int i = n - 1; i >= 0; i--)
                lines.Add(RosterCensus.FormatLine(ctx, seats[i]));
            lines.Reverse();
            return lines;
        }

        private static RosterCensus.ILineBudget Equivalent(int cap, int interval, int ceiling)
        {
            return new EquivalentBudget(cap, interval, ceiling);
        }

        /// <summary>Same rule - whole boundary or nothing, latched, announcing
        /// on the throttle - counting what is LEFT instead of what is spent.
        /// Must stay green.</summary>
        private sealed class EquivalentBudget : RosterCensus.ILineBudget
        {
            private readonly int _cap;
            private readonly RosterCensus.NoticeThrottle _notices;
            private int _remaining;
            private bool _closed;

            internal EquivalentBudget(int cap, int interval, int ceiling)
            {
                _cap = cap < 0 ? 0 : cap;
                _remaining = _cap;
                _notices = new RosterCensus.NoticeThrottle(interval, ceiling);
            }

            public bool TryReserve(Ctx ctx, int lines, out string exhaustionNotice)
            {
                exhaustionNotice = null;
                if (lines <= 0) return false;
                if (!_closed && lines <= _remaining) { _remaining -= lines; return true; }
                _closed = true;
                int suppressed;
                bool final;
                if (_notices.ShouldFire(ctx.Generation, out suppressed, out final))
                    exhaustionNotice = RosterCensus.FormatExhaustionNotice(
                        ctx, _cap, _cap - _remaining, lines, suppressed, final);
                return false;
            }
        }

        /// <summary>The same notice text assembled by concatenation instead of
        /// a StringBuilder. Must stay green: it is what keeps the
        /// reason-dropping mutant above evidence about the notice's CONTENT
        /// and not about how the string was built.</summary>
        private static string ConcatEmpty(Ctx ctx, string reason, int suppressed, bool final)
        {
            return Head(ctx) + " census=empty reason=" + reason + Tail(suppressed, final);
        }

        private static string ConcatDeclined(Ctx ctx, string reason, int suppressed, bool final)
        {
            return Head(ctx) + " census=declined reason=" + reason + Tail(suppressed, final);
        }

        private static string Head(Ctx ctx)
        {
            return RosterCensus.Prefix
                + " gen=" + N(ctx.Generation)
                + " boundary=" + ctx.Boundary
                + " sinceCallInMs=" + (ctx.SinceCallInMs < 0 ? RosterCensus.Unknown : N(ctx.SinceCallInMs))
                + " fighters=" + (ctx.Fighters < 0 ? RosterCensus.Unknown : N(ctx.Fighters))
                + " seats=" + N(ctx.Seats);
        }

        private static string Tail(int suppressed, bool final)
        {
            return " suppressedSinceLastNotice=" + N(suppressed < 0 ? 0 : suppressed)
                + " final=" + (final ? "true" : "false")
                + " " + RosterCensus.Probe;
        }

        private static string N(long v)
        {
            return v.ToString(CultureInfo.InvariantCulture);
        }
    }
}
