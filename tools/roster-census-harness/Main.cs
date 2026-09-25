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
    /// mutation switch in it is a hazard, and the delegate seams on SelfTest
    /// (the census, the budget, the two notice builders, the empty-cause
    /// classifier, the per-cause throttles, the total observation classifier
    /// and the settle schedule) are enough to drive the assertions from
    /// outside.</summary>
    internal static class Program
    {
        private static int Main(string[] args)
        {
            bool quiet = Array.IndexOf(args, "--quiet") >= 0;

            Console.WriteLine("=== roster-census-harness ===");

            // THE INVOCATION, PRINTED ABOVE THE RESULTS. A tally with no
            // command above it is a number a reader cannot bind to the source
            // that produced it: they have the count and no way to say WHICH
            // build ran, from where, or with what arguments. The process
            // prints it about itself, so it cannot drift from what actually
            // ran the way a hand-written log header can.
            Console.WriteLine("invocation:     " + Environment.CommandLine);
            Console.WriteLine("invocation-cwd: " + Environment.CurrentDirectory);
            Console.WriteLine("invocation-utc: "
                              + DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture));
            Console.WriteLine("runtime:        " + Environment.Version);
            Console.WriteLine();

            Console.WriteLine("baseline: RosterCensus.FormatCensus + SessionLineBudget + the notice builders"
                              + " + the empty-cause classifier + the per-cause notice throttles"
                              + " + the total observation classifier + the settle schedule");

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

            // The zero-seat-cause findings: a reason token shared between two
            // causes, and one cause's notice spent on behalf of another.
            caught += Mutant(ref mutants, "collapses-the-roster-read-failure-causes",
                             Classifier(CollapsedCauses),
                             "the four empty causes reach the line as four distinct reasons", quiet);
            caught += Mutant(ref mutants, "shares-one-notice-throttle-across-causes",
                             Causes(SharedThrottle),
                             "each empty cause announces its own first notice", quiet);
            caught += Mutant(ref mutants, "announces-every-empty-cause-occurrence",
                             Causes(UnthrottledCauses),
                             "repeat occurrences of one cause still share that cause's throttle", quiet);
            caught += Mutant(ref mutants, "drops-a-cause-it-does-not-recognise",
                             Causes(ListedCausesOnly),
                             "an unrecognised empty cause still announces", quiet);

            // The round-3 finding: the classification was not TOTAL over what
            // was actually observed, because a null entry was skipped before
            // it ran. This mutant restores exactly that behaviour.
            caught += Mutant(ref mutants, "skips-null-entries-before-classifying",
                             Observation(SkipsNullEntries),
                             "the observation mapping is total over every entry multiset", quiet);
            // The lens finding: the enumeration's DEPTH was doing work the
            // enumeration cannot do. This mutant trips only above any depth a
            // test would choose, so case 32 cannot see it at all, and the
            // size-independence case is what reds it.
            caught += Mutant(ref mutants, "classifies-a-large-room-by-its-count-rather-than-its-sign",
                             Observation(CountThresholdObservation),
                             "the observation token depends on the counts' signs and not on the room size",
                             quiet);
            caught += Mutant(ref mutants, "drops-the-entry-counts-from-the-empty-notice",
                             Notices(CountlessEmpty, RosterCensus.FormatDeclinedNotice),
                             "a null entry carries its own token and its count onto the line", quiet);
            caught += Mutant(ref mutants, "anchors-the-settle-clock-after-the-emission",
                             Settle(AnchorAfterEmission),
                             "the settled sample's clock is anchored at the call-in, not after the emission",
                             quiet);

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

            // The INERT TWINS of the two mutation sites above: the same four
            // tokens and the same per-cause rule, reached by a different
            // route. A red here would mean the new cases measure the shape of
            // the implementation rather than what it does.
            green += Control(ref controls, "equivalent-classifier-by-lookup-table",
                             Classifier(TabulatedCauses), baseline.Passed, quiet);
            green += Control(ref controls, "equivalent-cause-notices-by-parallel-arrays",
                             Causes(ArrayCauses), baseline.Passed, quiet);

            // The INERT TWINS of the three round-3 mutants above: the same
            // mapping, the same line and the same schedule, each reached by a
            // different route. A red here would mean the new cases measure the
            // shape of the implementation rather than what it does.
            // The empty notice's own twin is `equivalent-notices-built-by-
            // concatenation` above: it builds the SAME line, counts included,
            // by concatenation, so the count-dropping mutant's red is evidence
            // about the line's CONTENT and not about how it was assembled.
            green += Control(ref controls, "equivalent-observation-classifier-by-decision-table",
                             Observation(TabulatedObservation), baseline.Passed, quiet);
            green += Control(ref controls, "equivalent-settle-schedule-by-reassociated-arithmetic",
                             Settle(ReassociatedSchedule), baseline.Passed, quiet);
            green += Control(ref controls, "equivalent-observation-classifier-by-sign-vector",
                             Observation(SignVectorObservation), baseline.Passed, quiet);

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
            internal RosterCensus.EmptyNoticeFormatter Empty = RosterCensus.FormatEmptyRosterNotice;
            internal RosterCensus.NoticeFormatter Declined = RosterCensus.FormatDeclinedNotice;
            internal RosterCensus.EmptyCauseClassifier Classify = RosterCensus.ReasonForEmptyCause;
            internal RosterCensus.CauseNoticesFactory CauseNotices = RosterCensus.DefaultCauseNotices;
            internal RosterCensus.RosterObservationClassifier Observe = RosterCensus.ReasonForObservation;
            internal RosterCensus.SettleScheduler Schedule = RosterCensus.ScheduleSettle;
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

        private static Variant Notices(RosterCensus.EmptyNoticeFormatter empty,
                                       RosterCensus.NoticeFormatter declined)
        {
            var v = new Variant();
            v.Empty = empty;
            v.Declined = declined;
            return v;
        }

        private static Variant Observation(RosterCensus.RosterObservationClassifier observe)
        {
            var v = new Variant();
            v.Observe = observe;
            return v;
        }

        private static Variant Settle(RosterCensus.SettleScheduler schedule)
        {
            var v = new Variant();
            v.Schedule = schedule;
            return v;
        }

        private static Variant Classifier(RosterCensus.EmptyCauseClassifier classify)
        {
            var v = new Variant();
            v.Classify = classify;
            return v;
        }

        private static Variant Causes(RosterCensus.CauseNoticesFactory causeNotices)
        {
            var v = new Variant();
            v.CauseNotices = causeNotices;
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
            try { r = RosterCensus.SelfTest(v.Emit, v.Budget, v.Empty, v.Declined, v.Classify, v.CauseNotices,
                                            v.Observe, v.Schedule); }
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
            try { r = RosterCensus.SelfTest(v.Emit, v.Budget, v.Empty, v.Declined, v.Classify, v.CauseNotices,
                                            v.Observe, v.Schedule); }
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
        private static string ReasonlessEmpty(Ctx ctx, string reason,
                                              RosterCensus.RosterObservation observed,
                                              int suppressed, bool final)
        {
            return StripField(
                RosterCensus.FormatEmptyRosterNotice(ctx, reason, observed, suppressed, final), "reason");
        }

        /// <summary>"census=empty already carries a reason, the counts are
        /// noise." They are not: the reason was DERIVED from them, and without
        /// the null count a reader cannot check the all-spectators token
        /// against a roster that held an entry the read could not hand
        /// back.</summary>
        private static string CountlessEmpty(Ctx ctx, string reason,
                                             RosterCensus.RosterObservation observed,
                                             int suppressed, bool final)
        {
            string line = RosterCensus.FormatEmptyRosterNotice(ctx, reason, observed, suppressed, final);
            line = StripField(line, "observedEntries");
            line = StripField(line, "nullEntries");
            line = StripField(line, "spectatorEntries");
            return StripField(line, "seatEntries");
        }

        private static string ReasonlessDeclined(Ctx ctx, string reason, int suppressed, bool final)
        {
            return StripField(RosterCensus.FormatDeclinedNotice(ctx, reason, suppressed, final), "reason");
        }

        // ── mutant empty-cause classifiers ───────────────────────────────

        /// <summary>THE PRE-FIX MAPPING. "A read that raised and a read that
        /// returned no list are both a failed read, so one word covers both" -
        /// and the reader who has to decide what to look at next then cannot
        /// tell which of the two the log is describing.</summary>
        private static string CollapsedCauses(RosterCensus.EmptyCause cause)
        {
            if (cause == RosterCensus.EmptyCause.ListNull) return RosterCensus.ReasonRosterReadThrew;
            return RosterCensus.ReasonForEmptyCause(cause);
        }

        // ── mutant observation classifiers and settle schedules ──────────

        /// <summary>THE PRE-FIX CLASSIFICATION. "A null entry is not an actor,
        /// so drop it before counting" — and a roster holding one null entry
        /// and one spectator entry then reports that EVERY actor declared the
        /// spectator role, a cause that does not describe the observation it
        /// was derived from.</summary>
        private static string SkipsNullEntries(RosterCensus.RosterObservation observed)
        {
            if (!observed.Observed) return RosterCensus.ReasonForObservation(observed);
            var withoutNulls = RosterCensus.RosterObservation.Of(
                0, observed.SpectatorEntries, observed.SeatEntries);
            return RosterCensus.ReasonForObservation(withoutNulls);
        }

        /// <summary>A classification that tests a count's MAGNITUDE rather
        /// than only its sign: above a threshold no enumeration reaches, a
        /// seats-present observation reports the unclassified token instead.
        ///
        /// It exists to show what a bounded enumeration cannot see. Case 32
        /// walks every multiset up to a stated depth and this mutant is
        /// invisible to it at any depth a test would choose, because the
        /// threshold sits above them all — and a room size is not bounded at
        /// compile time, so no depth could be chosen that covers every room.
        /// The size-independence case is what reds it, which is the whole
        /// reason that case exists.</summary>
        private static string CountThresholdObservation(RosterCensus.RosterObservation observed)
        {
            if (observed.Observed && observed.SeatEntries > 64)
                return RosterCensus.ReasonRosterEmptyUnclassified;
            return RosterCensus.ReasonForObservation(observed);
        }

        /// <summary>The same TOTAL mapping, computed from the three counts'
        /// SIGN VECTOR and nothing else. The INERT TWIN of the
        /// count-threshold mutant: the same site, the same shape of edit —
        /// one that also reads the counts before deciding — and it must stay
        /// GREEN at every magnitude, which is what makes that mutant's red
        /// evidence about magnitude-dependence rather than about the mapping
        /// having been rewritten.</summary>
        private static string SignVectorObservation(RosterCensus.RosterObservation observed)
        {
            if (!observed.Observed) return RosterCensus.ReasonRosterEmptyUnclassified;

            int signs = (observed.NullEntries > 0 ? 1 : 0)
                        | (observed.SpectatorEntries > 0 ? 2 : 0)
                        | (observed.SeatEntries > 0 ? 4 : 0);

            if ((signs & 4) != 0) return RosterCensus.ReasonRosterSeatsPresent;
            if ((signs & 1) != 0) return RosterCensus.ReasonRosterEntryNull;
            if ((signs & 2) != 0) return RosterCensus.ReasonAllSpectators;
            return RosterCensus.ReasonRosterEmpty;
        }

        /// <summary>"Arm the clock when the work is done." The settled row's
        /// measured field then reports the gap from the END of the call-in
        /// emission, understating the call-in-to-sample delay by whatever
        /// writing those rows cost.</summary>
        private static void AnchorAfterEmission(long beforeEmissionTicks, long afterEmissionTicks,
                                                long frequency, double delaySeconds,
                                                out long anchorTicks, out long dueTicks)
        {
            anchorTicks = afterEmissionTicks;
            dueTicks = afterEmissionTicks + (long)(delaySeconds * frequency);
        }

        // ── mutant per-cause notice throttles ────────────────────────────

        private static RosterCensus.ICauseNotices SharedThrottle(int interval, int ceiling)
        {
            return new SharedThrottleNotices(interval, ceiling);
        }

        private static RosterCensus.ICauseNotices UnthrottledCauses(int interval, int ceiling)
        {
            return new UnthrottledNotices();
        }

        private static RosterCensus.ICauseNotices ListedCausesOnly(int interval, int ceiling)
        {
            return new ListedOnlyNotices(interval, ceiling);
        }

        /// <summary>THE PRE-FIX THROTTLE RULE. One throttle for every cause,
        /// so suppression follows ARRIVAL ORDER rather than cause: the first
        /// zero-seat boundary of a roster generation spends the notice and a
        /// boundary of a different cause in the same generation is
        /// silent.</summary>
        private sealed class SharedThrottleNotices : RosterCensus.ICauseNotices
        {
            private readonly RosterCensus.NoticeThrottle _one;

            internal SharedThrottleNotices(int interval, int ceiling)
            {
                _one = new RosterCensus.NoticeThrottle(interval, ceiling);
            }

            public bool ShouldFire(string reason, int generation, out int suppressed, out bool final)
            {
                return _one.ShouldFire(generation, out suppressed, out final);
            }
        }

        /// <summary>The over-correction: splitting the state per cause turns
        /// into no throttle at all, so every occurrence announces and the cap
        /// the notices exist to stay under stops meaning anything.</summary>
        private sealed class UnthrottledNotices : RosterCensus.ICauseNotices
        {
            public bool ShouldFire(string reason, int generation, out int suppressed, out bool final)
            {
                suppressed = 0;
                final = false;
                return true;
            }
        }

        /// <summary>The wrong failure direction: a reason the set does not
        /// recognise is dropped instead of announced, so the one zero-seat
        /// boundary nobody classified becomes the one with no line at all
        /// (#276).</summary>
        private sealed class ListedOnlyNotices : RosterCensus.ICauseNotices
        {
            private readonly Dictionary<string, RosterCensus.NoticeThrottle> _byReason;

            internal ListedOnlyNotices(int interval, int ceiling)
            {
                _byReason = new Dictionary<string, RosterCensus.NoticeThrottle>(StringComparer.Ordinal);
                foreach (string reason in RosterCensus.EmptyCauseReasons)
                    if (!_byReason.ContainsKey(reason))
                        _byReason.Add(reason, new RosterCensus.NoticeThrottle(interval, ceiling));
            }

            public bool ShouldFire(string reason, int generation, out int suppressed, out bool final)
            {
                suppressed = 0;
                final = false;
                RosterCensus.NoticeThrottle throttle;
                if (reason == null || !_byReason.TryGetValue(reason, out throttle)) return false;
                return throttle.ShouldFire(generation, out suppressed, out final);
            }
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
        private static string ConcatEmpty(Ctx ctx, string reason,
                                          RosterCensus.RosterObservation observed,
                                          int suppressed, bool final)
        {
            return Head(ctx) + " census=empty reason=" + reason
                + " observedEntries=" + C(observed.Entries)
                + " nullEntries=" + C(observed.NullEntries)
                + " spectatorEntries=" + C(observed.SpectatorEntries)
                + " seatEntries=" + C(observed.SeatEntries)
                + Tail(suppressed, final);
        }

        private static string C(int v)
        {
            return v < 0 ? RosterCensus.Unknown : v.ToString(CultureInfo.InvariantCulture);
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

        // ── negative controls for the two new seams ──────────────────────

        /// <summary>The same four tokens, reached by a table instead of a
        /// switch. The INERT TWIN of the collapsing classifier above: same
        /// site, same shape of edit, and it must stay GREEN, which is what
        /// makes that mutant's red evidence about the MAPPING rather than
        /// about the fact that the method was rewritten.</summary>
        private static string TabulatedCauses(RosterCensus.EmptyCause cause)
        {
            string[] table =
            {
                RosterCensus.ReasonRosterReadThrew,
                RosterCensus.ReasonRosterListNull,
                RosterCensus.ReasonRosterEmpty,
                RosterCensus.ReasonAllSpectators,
            };
            int i = (int)cause;
            return i >= 0 && i < table.Length ? table[i] : RosterCensus.ReasonRosterEmptyUnclassified;
        }

        /// <summary>The same TOTAL mapping, reached by a decision table over
        /// the three kinds instead of an ordered chain of conditions. The
        /// INERT TWIN of the null-skipping mutant: same site, same shape of
        /// edit, and it must stay GREEN, which is what makes that mutant's red
        /// evidence about the MAPPING rather than about the method having been
        /// rewritten.</summary>
        private static string TabulatedObservation(RosterCensus.RosterObservation observed)
        {
            if (!observed.Observed) return RosterCensus.ReasonRosterEmptyUnclassified;

            // row index: 0 = no seats and no nulls, 1 = no seats with nulls,
            // 2 = seats present. Column: whether any spectator was seen.
            int row = observed.SeatEntries > 0 ? 2 : (observed.NullEntries > 0 ? 1 : 0);
            int column = observed.SpectatorEntries > 0 ? 1 : 0;
            string[,] table =
            {
                { RosterCensus.ReasonRosterEmpty,        RosterCensus.ReasonAllSpectators },
                { RosterCensus.ReasonRosterEntryNull,    RosterCensus.ReasonRosterEntryNull },
                { RosterCensus.ReasonRosterSeatsPresent, RosterCensus.ReasonRosterSeatsPresent },
            };
            return table[row, column];
        }

        /// <summary>The same anchor and the same due time, with the delay
        /// converted to ticks first and the multiplication reassociated. The
        /// INERT TWIN of the after-the-emission mutant; it must stay
        /// green.</summary>
        private static void ReassociatedSchedule(long beforeEmissionTicks, long afterEmissionTicks,
                                                 long frequency, double delaySeconds,
                                                 out long anchorTicks, out long dueTicks)
        {
            long delayTicks = (long)(frequency * delaySeconds);
            anchorTicks = beforeEmissionTicks;
            dueTicks = anchorTicks + delayTicks;
        }

        private static RosterCensus.ICauseNotices ArrayCauses(int interval, int ceiling)
        {
            return new ArrayCauseNotices(interval, ceiling);
        }

        /// <summary>The same per-cause rule - one throttle per cause, its own
        /// first notice, its own counter, its own ceiling, and an unlisted
        /// reason still announcing - keyed by a linear scan of parallel
        /// arrays instead of a dictionary. The INERT TWIN of the three
        /// throttle-set mutants above; it must stay green.</summary>
        private sealed class ArrayCauseNotices : RosterCensus.ICauseNotices
        {
            private readonly string[] _reasons;
            private readonly RosterCensus.NoticeThrottle[] _throttles;
            private readonly RosterCensus.NoticeThrottle _unlisted;

            internal ArrayCauseNotices(int interval, int ceiling)
            {
                _reasons = (string[])RosterCensus.EmptyCauseReasons.Clone();
                _throttles = new RosterCensus.NoticeThrottle[_reasons.Length];
                for (int i = 0; i < _reasons.Length; i++)
                    _throttles[i] = new RosterCensus.NoticeThrottle(interval, ceiling);
                _unlisted = new RosterCensus.NoticeThrottle(interval, ceiling);
            }

            public bool ShouldFire(string reason, int generation, out int suppressed, out bool final)
            {
                for (int i = 0; i < _reasons.Length; i++)
                    if (string.Equals(_reasons[i], reason, StringComparison.Ordinal))
                        return _throttles[i].ShouldFire(generation, out suppressed, out final);
                return _unlisted.ShouldFire(generation, out suppressed, out final);
            }
        }
    }
}
