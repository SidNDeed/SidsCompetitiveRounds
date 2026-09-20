using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>The roster-census LINE and the session budget that bounds it,
    /// with no Unity, Photon or BepInEx anywhere in the file.
    ///
    /// That separation is the point, and it is the same arrangement
    /// <c>RosterCensusRules</c> uses on the FFA lane: a rule whose only gate
    /// is a source-shape test is asserted ABOUT and never RUN (#391).
    /// <see cref="SelfTest()"/> is EXECUTED by tools/roster-census-harness
    /// under a plain compiler, and the harness additionally runs the wrong
    /// implementations past the same assertions to prove they red.
    /// GameStateWatcher keeps everything genuinely contextual — the actor
    /// list, the Player transform, the view counters — and hands the result
    /// in here as plain values.
    ///
    /// ── WHAT THE CENSUS IS FOR ────────────────────────────────────────────
    /// One line per fighter seat at every map load and every game boundary,
    /// carrying the position the REPORTING seat believes each other seat
    /// occupies. That field is the whole reason the instrument exists: a
    /// report of a stalled point has to be readable from one seat's log, and
    /// presence and aliveness alone cannot separate "alive and not engaging"
    /// from "alive but not drawn where I could see it".
    ///
    /// ── TWO SAMPLES PER MAP LOAD, AND WHY ─────────────────────────────────
    /// A map load is not an instant, it is an interval, and the two ends of
    /// it hold different facts.
    ///
    /// <see cref="BoundaryMapCallIn"/> is taken in the Postfix of
    /// MapManager.RPCA_CallInNewMapAndMovePlayers. That Postfix runs when the
    /// RPC is RECEIVED — vanilla's own coroutine (wait for map, enter, clear
    /// objects, move players) has not run yet, and PlayerManager.MovePlayers
    /// is dispatched from inside it. So every field on a call-in row
    /// describes the state this seat INHERITED from the point that just
    /// ended: the previous round's terminal positions and the pre-revive dead
    /// flags. It is a useful row, and a misleading one if read as the state
    /// on the map being loaded.
    ///
    /// <see cref="BoundaryMapSettled"/> is taken a fixed delay later, from
    /// the per-frame tick, and carries <c>sinceCallInMs</c> so a reader sees
    /// the gap that was actually measured rather than trusting a claim about
    /// it. The per-player Move coroutine runs on the order of a second
    /// (learning #304 pairs one CALL IN NEW MAP block with N MOVE PLAYERS
    /// START and N END lines about a second apart), so in the ordinary case
    /// the settled row is on the far side of the move and the revive.
    ///
    /// Deliberately NOT a guarantee that the move finished (#351): when the
    /// transition is the thing that stalled, the settled row shows pre-move
    /// positions, and that is the most valuable reading this instrument can
    /// produce. The PAIR is the instrument — a settled row whose positions
    /// still equal its call-in row's is a seat that never got moved.
    ///
    /// ── FAILURE DIRECTION (#276 / #430) ───────────────────────────────────
    /// The census is pure observation and gates nothing. A seat it cannot
    /// read emits <c>active=? dead=? pos=?</c> and STILL emits its line:
    /// an unreadable seat is the single most interesting row in the census,
    /// and dropping the row you cannot fill is the filter that discards the
    /// line it measures (#441). <see cref="FormatCensus"/> therefore has no
    /// branch that can return fewer lines than it was handed seats.
    ///
    /// EVERY refusal this instrument can make announces itself, and every
    /// announcement is itself bounded and says when it will stop:
    ///   * the session budget (below) refuses a boundary that does not fit;
    ///   * the emitter refuses a boundary whose roster read came back empty;
    ///   * the emitter declines outside a mod-issued room, and on a
    ///     spectator seat.
    /// A refusal that printed nothing would leave a window of the log both
    /// empty and unmarked, which is the state a reader cannot tell from "the
    /// patch never attached" (#83). That is what <see cref="NoticeThrottle"/>
    /// exists to prevent while still bounding volume.
    ///
    /// ── THE PROBE TOKEN (#306) ────────────────────────────────────────────
    /// <see cref="Probe"/> exists for no other purpose than to be grepped. It
    /// is not a product string, it is never localised and it names no mode,
    /// so a check that looks for it cannot start passing forever because
    /// someone renamed something. Every line this file emits carries it,
    /// including every notice — a notice the probe grep could not see would
    /// make a truncated census indistinguishable from a census that found
    /// nothing.</summary>
    internal static class RosterCensus
    {
        internal const string Prefix = "[ROSTER-CENSUS]";

        /// <summary>Grep target. See the class remarks (#306).</summary>
        internal const string Probe = "SCR_ROSTER_PROBE=1";

        /// <summary>The RPC arrived and vanilla's map coroutine has NOT run:
        /// the state this seat inherited from the point that just ended. See
        /// the class remarks on why the two map labels are distinct.</summary>
        internal const string BoundaryMapCallIn = "map-callin";

        /// <summary>A fixed delay after the call-in, from the per-frame tick.
        /// Carries the measured <c>sinceCallInMs</c>.</summary>
        internal const string BoundaryMapSettled = "map-settled";

        internal const string BoundaryGame = "game";

        /// <summary>Printed for every field the reporting seat could not
        /// read, and for <c>sinceCallInMs</c> on the boundaries where no
        /// call-in delay applies. Deliberately not a number: a sentinel that
        /// looks like a real value invents a fact (#305).</summary>
        internal const string Unknown = "?";

        /// <summary>Lines per SESSION, not per room.
        ///
        /// The census is now TWO samples per map load rather than one (see
        /// the class remarks), so this horizon is half what it was when the
        /// volume question q3 was written: roughly three sittings the length
        /// of the one this was built for rather than six. Kept at the same
        /// number rather than doubled, because raising it would be ANSWERING
        /// q3 instead of recording it — the notes carry the flag.</summary>
        internal const int SessionLineCap = 4000;

        /// <summary>Re-announce a standing refusal after this many further
        /// refusals, so no long window of the log is both empty and
        /// unmarked.</summary>
        internal const int ExhaustionNoticeInterval = 50;

        /// <summary>At most this many exhaustion notices per session. The
        /// LAST one carries <c>final=true</c>, so even the notices stopping
        /// is a marked event rather than a silence (#430).</summary>
        internal const int ExhaustionNoticeCeiling = 40;

        internal const int EmptyRosterNoticeInterval = 20;
        internal const int EmptyRosterNoticeCeiling = 40;

        /// <summary>A decline fires at every boundary of every room the gate
        /// does not admit, which in casual play is most of them — so this
        /// throttle is far coarser than the others. One notice per roster
        /// generation is what marks the window an investigation is looking
        /// at; the interval is the backstop for a room whose generation never
        /// moves.</summary>
        internal const int DeclineNoticeInterval = 240;
        internal const int DeclineNoticeCeiling = 12;

        // ── reasons (each exists only to be read out of a log) ────────────

        internal const string ReasonSessionLineCap = "session-line-cap";
        internal const string ReasonNotModRoom = "not-mod-issued-room";
        internal const string ReasonLocalSpectator = "local-seat-is-spectator";
        internal const string ReasonRosterReadFailed = "roster-read-failed";
        internal const string ReasonRosterEmpty = "roster-read-empty";
        internal const string ReasonAllSpectators = "every-actor-is-a-spectator";

        // ── the boundary context ─────────────────────────────────────────

        /// <summary>Everything a line carries that is true of the BOUNDARY
        /// rather than of one seat. Passed as a struct so that adding a
        /// boundary-wide field does not re-thread every signature.</summary>
        internal struct BoundaryContext
        {
            internal int Generation;
            internal string Boundary;

            /// <summary>Milliseconds between the call-in and this sample.
            /// Negative on the boundaries where no call-in delay applies
            /// (<see cref="BoundaryMapCallIn"/> and
            /// <see cref="BoundaryGame"/>), where it prints as
            /// <see cref="Unknown"/>.</summary>
            internal long SinceCallInMs;

            /// <summary>RoomActors.ActiveFighterCount() as of this boundary —
            /// the LATCH-filtered count, which is a different set from the
            /// census rows and is on the line precisely so that the two can
            /// be compared without guessing. Negative: not read.
            ///
            /// The census set is the raw one (see the emitter's remarks), so
            /// the expected relation is <c>seats &gt;= fighters</c>: a seat
            /// the frozen roster has dropped still gets a census row, and
            /// that is the row this instrument exists to show. A census EQUAL
            /// to the fighter count is the ordinary case, not the acceptance
            /// bar.</summary>
            internal int Fighters;

            /// <summary>Census rows PRINTED at this boundary. Filled by
            /// <see cref="FormatCensus"/>; a reader counts rows OR reads
            /// this, and the two disagreeing is itself a finding.
            ///
            /// On a notice it is 0, because a notice prints no rows. What a
            /// suppressed boundary would have printed is <c>wouldEmit</c> on
            /// the exhaustion notice; a declined or empty boundary measured
            /// nothing to print, which is what its <c>reason</c> says.</summary>
            internal int Seats;

            internal static BoundaryContext For(int generation, string boundary, long sinceCallInMs, int fighters)
            {
                var c = new BoundaryContext();
                c.Generation = generation;
                c.Boundary = boundary;
                c.SinceCallInMs = sinceCallInMs;
                c.Fighters = fighters;
                c.Seats = 0;
                return c;
            }
        }

        // ── the seat record ──────────────────────────────────────────────

        /// <summary>One seat as the reporting client managed to read it. The
        /// Known flags are separate from the values so that "false" and "not
        /// read" are different states in the struct as well as in the line —
        /// <c>default(SeatObservation)</c> is never constructed in production
        /// precisely because its zeroes would read as facts; the two factory
        /// methods below are the only constructors.</summary>
        internal struct SeatObservation
        {
            internal int Actor;
            internal int PlayerId;        // negative: not read
            internal int Team;            // negative: not read
            internal bool ActiveKnown;
            internal bool Active;
            internal bool DeadKnown;
            internal bool Dead;
            internal bool PositionKnown;
            internal float X;
            internal float Y;
            internal long ViewBatches;    // negative: not read

            /// <summary>Whether this row is the REPORTING seat's own.
            ///
            /// Two things about the local row are structurally different and
            /// the rest of the line cannot express either. Its <c>pos</c> is
            /// ground truth, where every other row is this client's BELIEF
            /// about a remote seat — which is the entire distinction the
            /// witness bar asks a reader to make. And its
            /// <c>viewBatchesSinceLastBoundary</c> is ALWAYS
            /// <see cref="Unknown"/>: NetworkReplicaDiagnostics excludes the
            /// local actor by construction, so that counter is absent by
            /// design rather than unread. Without this field the local row is
            /// indistinguishable from a remote seat that had gone silent —
            /// the exact reading the census exists to support.</summary>
            internal bool SelfKnown;
            internal bool Self;
        }

        /// <summary>A seat present in the room whose body the reporting
        /// client could not resolve at all. It still gets a line.</summary>
        internal static SeatObservation UnreadableSeat(int actor, long viewBatches, bool selfKnown, bool self)
        {
            var s = new SeatObservation();
            s.Actor = actor;
            s.PlayerId = -1;
            s.Team = -1;
            s.ActiveKnown = false;
            s.DeadKnown = false;
            s.PositionKnown = false;
            s.ViewBatches = viewBatches < 0 ? -1 : viewBatches;
            s.SelfKnown = selfKnown;
            s.Self = self;
            return s;
        }

        /// <summary>A seat read field by field. Each Known flag is passed
        /// separately because the caller reads the properties through
        /// independent accesses, any one of which can fail on its
        /// own.</summary>
        internal static SeatObservation ReadSeat(
            int actor, int playerId, int team,
            bool activeKnown, bool active,
            bool deadKnown, bool dead,
            bool positionKnown, float x, float y,
            long viewBatches,
            bool selfKnown, bool self)
        {
            var s = new SeatObservation();
            s.Actor = actor;
            s.PlayerId = playerId < 0 ? -1 : playerId;
            s.Team = team < 0 ? -1 : team;
            s.ActiveKnown = activeKnown;
            s.Active = active;
            s.DeadKnown = deadKnown;
            s.Dead = dead;
            s.PositionKnown = positionKnown;
            s.X = x;
            s.Y = y;
            s.ViewBatches = viewBatches < 0 ? -1 : viewBatches;
            s.SelfKnown = selfKnown;
            s.Self = self;
            return s;
        }

        // ── formatting ───────────────────────────────────────────────────

        internal static string FormatLine(BoundaryContext ctx, SeatObservation seat)
        {
            var sb = new StringBuilder(200);
            sb.Append(Prefix);
            AppendBoundaryFields(sb, ctx);
            sb.Append(" actor=").Append(Num(seat.Actor))
              .Append(" self=").Append(seat.SelfKnown ? Flag(seat.Self) : Unknown)
              .Append(" pid=").Append(seat.PlayerId < 0 ? Unknown : Num(seat.PlayerId))
              .Append(" team=").Append(seat.Team < 0 ? Unknown : Num(seat.Team))
              .Append(" active=").Append(seat.ActiveKnown ? Flag(seat.Active) : Unknown)
              .Append(" dead=").Append(seat.DeadKnown ? Flag(seat.Dead) : Unknown)
              .Append(" pos=").Append(Position(seat))
              .Append(" viewBatchesSinceLastBoundary=")
              .Append(seat.ViewBatches < 0 ? Unknown : Num(seat.ViewBatches))
              .Append(' ').Append(Probe);
            return sb.ToString();
        }

        /// <summary>The boundary-wide fields, in the same order and spelling
        /// on a census row and on every notice, so one parse reads
        /// both.</summary>
        private static void AppendBoundaryFields(StringBuilder sb, BoundaryContext ctx)
        {
            sb.Append(" gen=").Append(Num(ctx.Generation))
              .Append(" boundary=").Append(Label(ctx.Boundary))
              .Append(" sinceCallInMs=").Append(ctx.SinceCallInMs < 0 ? Unknown : Num(ctx.SinceCallInMs))
              .Append(" fighters=").Append(ctx.Fighters < 0 ? Unknown : Num(ctx.Fighters))
              .Append(" seats=").Append(Num(ctx.Seats));
        }

        /// <summary>Exactly one line per seat handed in, in the order handed
        /// in. There is no filter and no early exit: see the class remarks on
        /// #441. A null list is zero seats, which is zero lines and not an
        /// exception — the EMITTER is what announces a zero-seat boundary,
        /// because only the emitter knows whether zero was a real reading or
        /// a failed one.</summary>
        internal static List<string> FormatCensus(BoundaryContext ctx, IList<SeatObservation> seats)
        {
            int n = seats == null ? 0 : seats.Count;
            ctx.Seats = n;
            var lines = new List<string>(n);
            for (int i = 0; i < n; i++)
                lines.Add(FormatLine(ctx, seats[i]));
            return lines;
        }

        /// <summary>The one line the budget prints when it refuses a
        /// boundary.
        ///
        /// <paramref name="suppressed"/> is how many refusals went
        /// unannounced since the previous notice — so the record shows its
        /// own gaps rather than hiding them — and <paramref name="final"/>
        /// marks the last notice this session will print.</summary>
        internal static string FormatExhaustionNotice(
            BoundaryContext ctx, int cap, int used, int wouldEmit, int suppressed, bool final)
        {
            var sb = new StringBuilder(220);
            sb.Append(Prefix);
            AppendBoundaryFields(sb, ctx);
            sb.Append(" census=suppressed reason=").Append(Label(ReasonSessionLineCap))
              .Append(" cap=").Append(Num(cap))
              .Append(" used=").Append(Num(used))
              .Append(" wouldEmit=").Append(Num(wouldEmit));
            AppendNoticeTail(sb, suppressed, final);
            return sb.ToString();
        }

        /// <summary>A boundary that reached the census with no seats to
        /// report. The one case in which the instrument fails to measure must
        /// not be the one case it says nothing about: without this, a reader
        /// counting rows against the fighter count finds a map load with zero
        /// rows and cannot tell a detached patch from a declined gate from an
        /// exhausted cap from a failed roster read.</summary>
        internal static string FormatEmptyRosterNotice(
            BoundaryContext ctx, string reason, int suppressed, bool final)
        {
            var sb = new StringBuilder(220);
            sb.Append(Prefix);
            AppendBoundaryFields(sb, ctx);
            sb.Append(" census=empty reason=").Append(Label(reason));
            AppendNoticeTail(sb, suppressed, final);
            return sb.ToString();
        }

        /// <summary>A boundary the emitter declined to census at all. The
        /// gate is for log volume and declines a great many boundaries by
        /// design, so this is throttled hard — but never to silence, because
        /// an investigation whose window declined every boundary otherwise
        /// reads as an instrument that was never installed.</summary>
        internal static string FormatDeclinedNotice(
            BoundaryContext ctx, string reason, int suppressed, bool final)
        {
            var sb = new StringBuilder(220);
            sb.Append(Prefix);
            AppendBoundaryFields(sb, ctx);
            sb.Append(" census=declined reason=").Append(Label(reason));
            AppendNoticeTail(sb, suppressed, final);
            return sb.ToString();
        }

        private static void AppendNoticeTail(StringBuilder sb, int suppressed, bool final)
        {
            sb.Append(" suppressedSinceLastNotice=").Append(Num(suppressed < 0 ? 0 : suppressed))
              .Append(" final=").Append(Flag(final))
              .Append(' ').Append(Probe);
        }

        /// <summary>The position verbatim, or <see cref="Unknown"/>. Never a
        /// clamp and never an origin fallback: a seat reported at 0,0 because
        /// its transform could not be read is a seat the reader will believe
        /// was standing at 0,0. G9 round-trips a float, so an out-of-bounds
        /// coordinate survives the formatting it exists to prove.</summary>
        private static string Position(SeatObservation seat)
        {
            if (!seat.PositionKnown) return Unknown;
            if (!IsFinite(seat.X) || !IsFinite(seat.Y)) return Unknown;
            return Coord(seat.X) + "," + Coord(seat.Y);
        }

        private static bool IsFinite(float v)
        {
            return !float.IsNaN(v) && !float.IsInfinity(v);
        }

        private static string Coord(float v)
        {
            return v.ToString("G9", CultureInfo.InvariantCulture);
        }

        private static string Num(long v)
        {
            return v.ToString(CultureInfo.InvariantCulture);
        }

        private static string Flag(bool v)
        {
            return v ? "true" : "false";
        }

        /// <summary>Every field in the line is <c>key=value</c> separated by
        /// a single space, so a label carrying whitespace would split one
        /// field into two and silently shift every field after it. The labels
        /// and reasons this ships with contain none; the replacement is here
        /// so that one added later cannot corrupt the format.</summary>
        private static string Label(string text)
        {
            if (string.IsNullOrEmpty(text)) return Unknown;
            var sb = new StringBuilder(text.Length);
            for (int i = 0; i < text.Length; i++)
            {
                char c = text[i];
                sb.Append(char.IsWhiteSpace(c) ? '_' : c);
            }
            return sb.ToString();
        }

        // ── notice throttling ────────────────────────────────────────────

        /// <summary>How often a STANDING refusal is allowed to say so.
        ///
        /// A notice that fires once per session (which is what this replaces)
        /// is true of the first refusal and false of every one after it: the
        /// window a reader is actually looking at ends up both empty and
        /// unmarked, which is the precise confusion the notice was added to
        /// prevent (#302 / #351 — a guarantee written from the one state the
        /// author had in mind). A notice that fires on every refusal is the
        /// volume the cap exists to bound.
        ///
        /// So: fire on the first, on every roster-generation edge, and after
        /// <c>interval</c> further refusals — and stop after
        /// <c>ceiling</c> notices, with the last one marked
        /// <c>final=true</c> so that even the notices stopping is an
        /// announced event and not a silence (#430).</summary>
        internal sealed class NoticeThrottle
        {
            private readonly int _interval;
            private readonly int _ceiling;
            private int _fired;
            private int _sinceLast;
            private bool _ever;
            private int _lastGeneration;
            private bool _closed;

            internal NoticeThrottle(int interval, int ceiling)
            {
                _interval = interval < 1 ? 1 : interval;
                _ceiling = ceiling < 1 ? 1 : ceiling;
            }

            internal int Fired { get { return _fired; } }
            internal bool Closed { get { return _closed; } }

            /// <summary>True when THIS occurrence should print. On true,
            /// <paramref name="suppressed"/> is how many occurrences went
            /// unannounced since the previous notice, and
            /// <paramref name="final"/> says this is the last one.</summary>
            internal bool ShouldFire(int generation, out int suppressed, out bool final)
            {
                suppressed = _sinceLast;
                final = false;
                if (_closed) { _sinceLast++; return false; }

                bool due = !_ever || generation != _lastGeneration || _sinceLast >= _interval;
                if (!due) { _sinceLast++; return false; }

                _ever = true;
                _lastGeneration = generation;
                _sinceLast = 0;
                _fired++;
                if (_fired >= _ceiling) { _closed = true; final = true; }
                return true;
            }
        }

        // ── the session budget ───────────────────────────────────────────

        /// <summary>Seam for the harness: the wrong budgets are handed to the
        /// same assertions as the real one.</summary>
        internal interface ILineBudget
        {
            /// <summary>Charges <paramref name="lines"/> against the budget.
            /// True means the caller may emit exactly that many lines. False
            /// means it must emit none of them, and hands back a notice to
            /// print whenever this refusal is one the throttle
            /// admits.</summary>
            bool TryReserve(BoundaryContext ctx, int lines, out string exhaustionNotice);
        }

        /// <summary>Whole boundary or nothing, it stops for good once it has
        /// stopped, and it keeps saying so.
        ///
        /// A partial boundary would be worse than no boundary: the witness
        /// bar counts census rows, and a boundary truncated mid-way makes a
        /// missing seat — the exact defect shape the census hunts —
        /// indistinguishable from a budget running out. So a boundary that
        /// does not fit is refused entire.
        ///
        /// And the refusal LATCHES. Charging against remaining headroom alone
        /// is non-monotonic: after the cap first refuses a three-seat
        /// boundary, a later two-seat boundary still fits and emits, so the
        /// record resumes as silently as it stopped and a reader has a marker
        /// at neither end. One clean edge is worth more than the handful of
        /// extra rows.</summary>
        internal sealed class SessionLineBudget : ILineBudget
        {
            private readonly int _cap;
            private readonly NoticeThrottle _notices;
            private int _used;
            private bool _exhausted;

            internal SessionLineBudget(int cap)
                : this(cap, ExhaustionNoticeInterval, ExhaustionNoticeCeiling) { }

            internal SessionLineBudget(int cap, int noticeInterval, int noticeCeiling)
            {
                _cap = cap < 0 ? 0 : cap;
                _notices = new NoticeThrottle(noticeInterval, noticeCeiling);
            }

            internal int Cap { get { return _cap; } }
            internal int Used { get { return _used; } }
            internal bool Exhausted { get { return _exhausted; } }

            public bool TryReserve(BoundaryContext ctx, int lines, out string exhaustionNotice)
            {
                exhaustionNotice = null;
                // A boundary with no seats is not a reservation and must not
                // be able to exhaust the budget or spend a notice: nothing
                // was refused. The emitter announces that case itself, with
                // the reason only it can know.
                if (lines <= 0) return false;

                if (!_exhausted && _used <= _cap - lines)
                {
                    _used += lines;
                    return true;
                }

                _exhausted = true;
                int suppressed;
                bool final;
                if (_notices.ShouldFire(ctx.Generation, out suppressed, out final))
                    exhaustionNotice = FormatExhaustionNotice(ctx, _cap, _used, lines, suppressed, final);
                return false;
            }
        }

        // ── self-test (EXECUTED by tools/roster-census-harness) ──────────

        internal sealed class SelfTestResult
        {
            internal int Passed;
            internal int Failed;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        /// <summary>The census under test. Production calls
        /// <see cref="FormatCensus"/> directly; the harness passes the wrong
        /// implementations through here so the assertions below measure
        /// BEHAVIOUR and not the source text of this file.</summary>
        internal delegate List<string> CensusEmitter(BoundaryContext ctx, IList<SeatObservation> seats);

        /// <summary>The budget under test. Same seam, same reason. The
        /// throttle parameters are part of the seam because the notice RULE
        /// is under test as much as the cap is.</summary>
        internal delegate ILineBudget BudgetFactory(int cap, int noticeInterval, int noticeCeiling);

        /// <summary>The notices under test. Same seam, same reason: a
        /// notice that stops naming its cause is the natural tidy-up edit,
        /// and without a seam the case asserting the reason could never be
        /// shown to fail (#342).</summary>
        internal delegate string NoticeFormatter(BoundaryContext ctx, string reason, int suppressed, bool final);

        internal static SelfTestResult SelfTest()
        {
            return SelfTest(FormatCensus, DefaultBudget);
        }

        private static ILineBudget DefaultBudget(int cap, int noticeInterval, int noticeCeiling)
        {
            return new SessionLineBudget(cap, noticeInterval, noticeCeiling);
        }

        internal static SelfTestResult SelfTest(CensusEmitter emit, BudgetFactory budget)
        {
            return SelfTest(emit, budget, FormatEmptyRosterNotice, FormatDeclinedNotice);
        }

        internal static SelfTestResult SelfTest(CensusEmitter emit, BudgetFactory budget,
                                                NoticeFormatter emptyNotice, NoticeFormatter declinedNotice)
        {
            var r = new SelfTestResult();
            if (emit == null || budget == null || emptyNotice == null || declinedNotice == null)
            {
                r.Failed++;
                r.Report.Append("FAIL | case=selftest was handed no implementation | got=null\n");
                return r;
            }

            // The 1v2 the report was about: a solo seat on one side and two
            // seats on the other. Seat 3 is the one most cases below are
            // interested in, because it is the one whose rendered position
            // the reporting seat could not otherwise be asked about. Seat 1
            // is the reporting seat itself, which is why its view counter is
            // absent (see SeatObservation.Self).
            BoundaryContext MapIn() { return BoundaryContext.For(11, BoundaryMapCallIn, -1, 3); }
            SeatObservation Solo() { return ReadSeat(1, 0, 0, true, true, true, false, true, 1.5f, 0.25f, -1, true, true); }
            SeatObservation DuoA() { return ReadSeat(2, 1, 1, true, true, true, false, true, -3.75f, 0.5f, 9, true, false); }
            SeatObservation DuoB() { return ReadSeat(3, 2, 1, true, true, true, false, true, 4.5f, -1.25f, 7, true, false); }

            // 1. CARDINALITY. Three seats in, three lines out, one per actor.
            {
                var seats = new List<SeatObservation> { Solo(), DuoA(), DuoB() };
                var lines = emit(MapIn(), seats);
                bool ok = lines != null && lines.Count == 3
                          && Field(lines, "actor", "1") != null
                          && Field(lines, "actor", "2") != null
                          && Field(lines, "actor", "3") != null;
                Check(r, "one line per seat, one seat per line", ok, Describe(lines));
            }

            // 2. RosterCensus_ReportsInactiveUndeadSeat (diagnosis §5.1). The
            //    seat that is neither active nor dead is the shape the census
            //    exists to catch, and it must appear as itself.
            {
                var seats = new List<SeatObservation>
                    { Solo(), DuoA(), ReadSeat(3, 2, 1, true, false, true, false, true, 4.5f, -1.25f, 0, true, false) };
                var lines = emit(MapIn(), seats);
                string line = Field(lines, "actor", "3");
                bool ok = lines != null && lines.Count == 3 && line != null
                          && Value(line, "active") == "false"
                          && Value(line, "dead") == "false";
                Check(r, "an inactive, undead seat is reported as itself", ok, line ?? Describe(lines));
            }

            // 3. An unreadable seat STILL emits its line (§4.1 / #441). This
            //    is the case a defensive "skip what you cannot read" edit
            //    removes, and it is the most interesting row in the census.
            {
                var seats = new List<SeatObservation> { Solo(), DuoA(), UnreadableSeat(3, -1, true, false) };
                var lines = emit(MapIn(), seats);
                string line = Field(lines, "actor", "3");
                bool ok = lines != null && lines.Count == 3 && line != null
                          && Value(line, "active") == Unknown
                          && Value(line, "dead") == Unknown
                          && Value(line, "pos") == Unknown
                          && Value(line, "pid") == Unknown
                          && Value(line, "team") == Unknown
                          && Value(line, "viewBatchesSinceLastBoundary") == Unknown;
                Check(r, "an unreadable seat still emits, as question marks", ok, line ?? Describe(lines));
            }

            // 4. RosterCensus_ReportsOutOfBoundsPositionVerbatim (§5.1). The
            //    case revision 1's evidence could not have distinguished.
            {
                var seats = new List<SeatObservation>
                    { Solo(), DuoA(), ReadSeat(3, 2, 1, true, true, true, false, true, 9999.5f, -4321.25f, 3, true, false) };
                var lines = emit(MapIn(), seats);
                string line = Field(lines, "actor", "3");
                bool ok = line != null && Value(line, "pos") == "9999.5,-4321.25";
                Check(r, "an out-of-bounds position is reported verbatim", ok, line == null ? Describe(lines) : Value(line, "pos"));
            }

            // 5. A position that cannot be read is a question mark, never an
            //    origin sentinel (#305). Both non-finite forms.
            {
                var nan = new List<SeatObservation> { ReadSeat(3, 2, 1, true, true, true, false, true, float.NaN, 1f, 3, true, false) };
                var inf = new List<SeatObservation> { ReadSeat(3, 2, 1, true, true, true, false, true, 2f, float.PositiveInfinity, 3, true, false) };
                string a = Field(emit(MapIn(), nan), "actor", "3");
                string b = Field(emit(MapIn(), inf), "actor", "3");
                bool ok = a != null && b != null
                          && Value(a, "pos") == Unknown && Value(b, "pos") == Unknown;
                Check(r, "a non-finite position is a question mark, not an origin",
                      ok, (a == null ? "(null)" : Value(a, "pos")) + " / " + (b == null ? "(null)" : Value(b, "pos")));
            }

            // 6. Every line carries the probe token (#306).
            {
                var seats = new List<SeatObservation> { Solo(), DuoA(), UnreadableSeat(3, -1, true, false) };
                var lines = emit(BoundaryContext.For(11, BoundaryGame, -1, 3), seats);
                bool ok = lines != null && lines.Count == 3;
                if (ok)
                    for (int i = 0; i < lines.Count; i++)
                        if (Value(lines[i], "SCR_ROSTER_PROBE") != "1") { ok = false; break; }
                Check(r, "every census line carries the probe token", ok, Describe(lines));
            }

            // 7. NEGATIVE CONTROL for 4 and 5. An ordinary in-bounds position
            //    is reported unchanged, so those two cases measure the
            //    clamp/sentinel behaviour and not the formatting of positions
            //    in general. A suite that reds on this as well is measuring
            //    the file rather than the behaviour.
            {
                var seats = new List<SeatObservation> { DuoB() };
                string line = Field(emit(MapIn(), seats), "actor", "3");
                bool ok = line != null && Value(line, "pos") == "4.5,-1.25";
                Check(r, "an in-bounds position is reported unchanged", ok,
                      line == null ? "(null)" : Value(line, "pos"));
            }

            // 8. The scalar fields have the same two states as the flags.
            {
                var seats = new List<SeatObservation> { ReadSeat(4, -1, -1, true, true, true, false, true, 0f, 0f, -1, true, false) };
                string line = Field(emit(MapIn(), seats), "actor", "4");
                bool ok = line != null
                          && Value(line, "pid") == Unknown
                          && Value(line, "team") == Unknown
                          && Value(line, "viewBatchesSinceLastBoundary") == Unknown
                          && Value(line, "pos") == "0,0";   // a READ zero is still a fact
                Check(r, "unread scalars are question marks and a read zero is not", ok, line ?? "(null)");
            }

            // 9. Degenerate inputs are empty, not exceptions.
            {
                var none = emit(MapIn(), new List<SeatObservation>());
                var nil = emit(MapIn(), null);
                bool ok = none != null && none.Count == 0 && nil != null && nil.Count == 0;
                Check(r, "no seats is no lines, not an exception", ok,
                      (none == null ? "null" : none.Count.ToString(CultureInfo.InvariantCulture))
                      + " / " + (nil == null ? "null" : nil.Count.ToString(CultureInfo.InvariantCulture)));
            }

            // 10. All THREE boundary labels reach the line as themselves. A
            //     reader pairs a call-in with its settled sample to see
            //     whether the move happened at all, so the two map labels
            //     being distinct is load-bearing, not cosmetic.
            {
                var seats = new List<SeatObservation> { Solo() };
                string callIn = Field(emit(BoundaryContext.For(11, BoundaryMapCallIn, -1, 1), seats), "actor", "1");
                string settled = Field(emit(BoundaryContext.For(11, BoundaryMapSettled, 2015, 1), seats), "actor", "1");
                string game = Field(emit(BoundaryContext.For(12, BoundaryGame, -1, 1), seats), "actor", "1");
                bool ok = callIn != null && settled != null && game != null
                          && Value(callIn, "boundary") == BoundaryMapCallIn && Value(callIn, "gen") == "11"
                          && Value(settled, "boundary") == BoundaryMapSettled
                          && Value(game, "boundary") == BoundaryGame && Value(game, "gen") == "12"
                          && Value(callIn, "boundary") != Value(settled, "boundary");
                Check(r, "the three boundary labels reach the line and the two map samples differ", ok,
                      (callIn == null ? "(null)" : Value(callIn, "boundary"))
                      + " / " + (settled == null ? "(null)" : Value(settled, "boundary"))
                      + " / " + (game == null ? "(null)" : Value(game, "boundary")));
            }

            // 11. THE SETTLED SAMPLE CARRIES ITS MEASURED DELAY, and the
            //     boundaries where no call-in delay applies print a question
            //     mark rather than a zero — "taken at the call-in" and "taken
            //     0 ms after the call-in" are different claims.
            {
                var seats = new List<SeatObservation> { Solo() };
                string settled = Field(emit(BoundaryContext.For(11, BoundaryMapSettled, 2015, 1), seats), "actor", "1");
                string callIn = Field(emit(BoundaryContext.For(11, BoundaryMapCallIn, -1, 1), seats), "actor", "1");
                bool ok = settled != null && callIn != null
                          && Value(settled, "sinceCallInMs") == "2015"
                          && Value(callIn, "sinceCallInMs") == Unknown;
                Check(r, "the settled sample carries its measured delay and the call-in carries none", ok,
                      (settled == null ? "(null)" : Value(settled, "sinceCallInMs"))
                      + " / " + (callIn == null ? "(null)" : Value(callIn, "sinceCallInMs")));
            }

            // 12. THE REPORTING SEAT'S OWN ROW IS MARKED. Its pos is ground
            //     truth and its view counter is absent by construction, so a
            //     row carrying viewBatchesSinceLastBoundary=? is the local
            //     seat OR a silent remote one — and only self= separates
            //     them.
            {
                var seats = new List<SeatObservation> { Solo(), DuoA(), DuoB() };
                var lines = emit(MapIn(), seats);
                string mine = Field(lines, "actor", "1");
                string theirs = Field(lines, "actor", "2");
                bool ok = mine != null && theirs != null
                          && Value(mine, "self") == "true"
                          && Value(theirs, "self") == "false"
                          && Value(mine, "viewBatchesSinceLastBoundary") == Unknown;
                Check(r, "the reporting seat's own row is marked self", ok,
                      (mine == null ? "(null)" : "self=" + Value(mine, "self")
                       + " batches=" + Value(mine, "viewBatchesSinceLastBoundary"))
                      + " / " + (theirs == null ? "(null)" : "self=" + Value(theirs, "self")));
            }

            // 13. A seat whose OWNERSHIP could not be decided prints self=?,
            //     not self=false. Guessing "not me" on an unread local actor
            //     number would hand the reader a fact nobody established.
            {
                var seats = new List<SeatObservation> { UnreadableSeat(7, -1, false, false) };
                string line = Field(emit(MapIn(), seats), "actor", "7");
                bool ok = line != null && Value(line, "self") == Unknown;
                Check(r, "an undecided self is a question mark, not false", ok,
                      line == null ? "(null)" : Value(line, "self"));
            }

            // 14. THE FIGHTER COUNT IS ON THE LINE BESIDE THE ROW COUNT. The
            //     census set (raw PlayerList minus spectators) and
            //     ActiveFighterCount (latch-filtered) are different sets, so
            //     the comparison the witness bar asks for is only possible if
            //     both numbers are in the record.
            {
                var seats = new List<SeatObservation> { Solo(), DuoA(), DuoB() };
                var lines = emit(BoundaryContext.For(11, BoundaryMapCallIn, -1, 2), seats);
                string line = Field(lines, "actor", "3");
                bool ok = line != null && Value(line, "fighters") == "2" && Value(line, "seats") == "3";
                Check(r, "the fighter count and the row count are both on the line", ok,
                      line == null ? Describe(lines) : "fighters=" + Value(line, "fighters") + " seats=" + Value(line, "seats"));
            }

            // 15. An unread fighter count is a question mark, and the row
            //     count still reports.
            {
                var seats = new List<SeatObservation> { Solo() };
                string line = Field(emit(BoundaryContext.For(11, BoundaryMapCallIn, -1, -1), seats), "actor", "1");
                bool ok = line != null && Value(line, "fighters") == Unknown && Value(line, "seats") == "1";
                Check(r, "an unread fighter count is a question mark", ok,
                      line == null ? "(null)" : "fighters=" + Value(line, "fighters") + " seats=" + Value(line, "seats"));
            }

            // 16. THE BUDGET IS WHOLE-BOUNDARY-OR-NOTHING, AND IT ANNOUNCES.
            //     Cap 5, two three-seat boundaries: the first fits, the
            //     second does not, and the refusal hands back a notice.
            {
                var b = budget(5, ExhaustionNoticeInterval, ExhaustionNoticeCeiling);
                string first, second;
                bool okFirst = b.TryReserve(BoundaryContext.For(11, BoundaryMapCallIn, -1, 3), 3, out first);
                bool okSecond = b.TryReserve(BoundaryContext.For(11, BoundaryMapCallIn, -1, 3), 3, out second);
                bool ok = okFirst && first == null && !okSecond && second != null;
                Check(r, "a boundary that does not fit is refused entire and announced", ok,
                      "first=" + okFirst + "/" + (first ?? "(null)") + " second=" + okSecond + "/" + (second ?? "(null)"));
            }

            // 17. THE CENSUS DOES NOT SILENTLY RESUME. Once the cap has
            //     refused, a later SMALLER boundary that would still fit in
            //     the remaining headroom is refused too. A record that stops
            //     and restarts with a marker at neither end is worse than one
            //     that stops.
            {
                var b = budget(5, ExhaustionNoticeInterval, ExhaustionNoticeCeiling);
                string ignored;
                b.TryReserve(BoundaryContext.For(11, BoundaryMapCallIn, -1, 3), 3, out ignored);   // 3 of 5 used
                b.TryReserve(BoundaryContext.For(11, BoundaryMapCallIn, -1, 3), 3, out ignored);   // refused, latches
                string third;
                bool okThird = b.TryReserve(BoundaryContext.For(11, BoundaryMapCallIn, -1, 2), 2, out third);
                Check(r, "the census does not resume after the cap has refused", !okThird,
                      "granted=" + okThird);
            }

            // 18. A STANDING REFUSAL KEEPS SAYING SO. Announcing once per
            //     session is true of the first refusal and false of every one
            //     after it: the window a reader is looking at ends up empty
            //     and unmarked. Interval 3 here, so the fourth refusal after
            //     a notice announces again and reports what it suppressed.
            {
                var b = budget(2, 3, ExhaustionNoticeCeiling);
                var ctx = BoundaryContext.For(11, BoundaryMapCallIn, -1, 3);
                string n1, n2, n3, n4, n5;
                b.TryReserve(ctx, 3, out n1);   // first refusal: announces
                b.TryReserve(ctx, 3, out n2);   // suppressed
                b.TryReserve(ctx, 3, out n3);   // suppressed
                b.TryReserve(ctx, 3, out n4);   // suppressed (3 since the notice)
                b.TryReserve(ctx, 3, out n5);   // due again
                bool ok = n1 != null && n2 == null && n3 == null && n4 == null && n5 != null
                          && Value(n5, "suppressedSinceLastNotice") == "3";
                Check(r, "a standing refusal re-announces after its interval", ok,
                      "n1=" + Mark(n1) + " n2=" + Mark(n2) + " n3=" + Mark(n3) + " n4=" + Mark(n4)
                      + " n5=" + Mark(n5) + "/" + (n5 == null ? "-" : Value(n5, "suppressedSinceLastNotice")));
            }

            // 19. A NEW ROSTER GENERATION ALWAYS ANNOUNCES, whatever the
            //     interval has counted. A room change, or a seat coming and
            //     going, is exactly the edge an investigation opens its
            //     window on, and it must never be the edge that is unmarked.
            {
                var b = budget(2, 1000, ExhaustionNoticeCeiling);
                string first, sameGen, newGen;
                b.TryReserve(BoundaryContext.For(11, BoundaryMapCallIn, -1, 3), 3, out first);
                b.TryReserve(BoundaryContext.For(11, BoundaryMapCallIn, -1, 3), 3, out sameGen);
                b.TryReserve(BoundaryContext.For(12, BoundaryMapCallIn, -1, 3), 3, out newGen);
                bool ok = first != null && sameGen == null && newGen != null
                          && Value(newGen, "gen") == "12";
                Check(r, "a new roster generation re-announces a standing refusal", ok,
                      "first=" + Mark(first) + " sameGen=" + Mark(sameGen) + " newGen=" + Mark(newGen));
            }

            // 20. THE NOTICES THEMSELVES STOP LOUDLY. The last notice a
            //     session will print says so, so that even the end of the
            //     record is an announced event (#430).
            {
                var b = budget(2, 1, 2);
                var ctx = BoundaryContext.For(11, BoundaryMapCallIn, -1, 3);
                string n1, n2, n3, n4;
                b.TryReserve(ctx, 3, out n1);   // first refusal: announces
                b.TryReserve(ctx, 3, out n2);   // suppressed (none yet counted)
                b.TryReserve(ctx, 3, out n3);   // one suppressed: due, and the ceiling
                b.TryReserve(ctx, 3, out n4);   // closed: silent from here
                bool ok = n1 != null && Value(n1, "final") == "false"
                          && n2 == null
                          && n3 != null && Value(n3, "final") == "true"
                          && n4 == null;
                Check(r, "the last notice of a session is marked final", ok,
                      "n1=" + (n1 == null ? "-" : Value(n1, "final"))
                      + " n2=" + Mark(n2)
                      + " n3=" + (n3 == null ? "-" : Value(n3, "final"))
                      + " n4=" + Mark(n4));
            }

            // 21. The notice is greppable by the same token as the census and
            //     says what it suppressed.
            {
                var b = budget(2, ExhaustionNoticeInterval, ExhaustionNoticeCeiling);
                string notice;
                b.TryReserve(BoundaryContext.For(11, BoundaryMapCallIn, -1, 3), 3, out notice);
                bool ok = notice != null
                          && Value(notice, "SCR_ROSTER_PROBE") == "1"
                          && Value(notice, "census") == "suppressed"
                          && Value(notice, "reason") == ReasonSessionLineCap
                          && Value(notice, "wouldEmit") == "3"
                          && Value(notice, "cap") == "2"
                          && Value(notice, "boundary") == BoundaryMapCallIn;
                Check(r, "the exhaustion notice carries the probe token and its cause", ok, notice ?? "(null)");
            }

            // 22. NEGATIVE CONTROL for 16 to 21. A boundary inside the budget
            //     is granted and says nothing, so those cases measure the
            //     refusal and not "this budget always produces a notice".
            {
                var b = budget(SessionLineCap, ExhaustionNoticeInterval, ExhaustionNoticeCeiling);
                string notice;
                bool granted = b.TryReserve(BoundaryContext.For(11, BoundaryMapCallIn, -1, 3), 3, out notice);
                Check(r, "a boundary inside the budget is granted silently",
                      granted && notice == null, "granted=" + granted + " notice=" + (notice ?? "(null)"));
            }

            // 23. A zero-seat boundary reserves nothing and cannot announce
            //     exhaustion — nothing was refused, and the emitter announces
            //     that case itself with the reason only it can know. Without
            //     this, an empty room would both burn a notice and latch the
            //     budget shut for the session.
            {
                var b = budget(0, ExhaustionNoticeInterval, ExhaustionNoticeCeiling);
                string notice;
                bool granted = b.TryReserve(BoundaryContext.For(11, BoundaryMapCallIn, -1, 0), 0, out notice);
                string later;
                b.TryReserve(BoundaryContext.For(12, BoundaryMapCallIn, -1, 1), 1, out later);
                Check(r, "a zero-seat boundary neither reserves nor announces",
                      !granted && notice == null && later != null,
                      "granted=" + granted + " notice=" + (notice ?? "(null)") + " later=" + Mark(later));
            }

            // 24. A ZERO-SEAT BOUNDARY IS STILL ON THE RECORD, and so is a
            //     declined one. The cases in which the instrument does not
            //     measure must not be the cases it says nothing about: a
            //     reader who finds a map load with no rows has to be able to
            //     tell a failed roster read from a detached patch, a declined
            //     gate and an exhausted cap.
            {
                var ctx = BoundaryContext.For(11, BoundaryMapCallIn, -1, 2);
                string empty = emptyNotice(ctx, ReasonRosterReadFailed, 0, false);
                string declined = declinedNotice(ctx, ReasonNotModRoom, 4, false);
                bool ok = Value(empty, "census") == "empty"
                          && Value(empty, "reason") == ReasonRosterReadFailed
                          && Value(empty, "seats") == "0"
                          && Value(empty, "SCR_ROSTER_PROBE") == "1"
                          && Value(declined, "census") == "declined"
                          && Value(declined, "reason") == ReasonNotModRoom
                          && Value(declined, "suppressedSinceLastNotice") == "4"
                          && Value(declined, "SCR_ROSTER_PROBE") == "1";
                Check(r, "an empty and a declined boundary each say so, with a reason", ok,
                      empty + " || " + declined);
            }

            // 25. The throttle rule itself, driven directly: the same three
            //     admissions the budget relies on. Asserting it here as well
            //     as through the budget is what makes a throttle defect
            //     readable as a throttle defect.
            {
                var t = new NoticeThrottle(2, 99);
                int s; bool f;
                bool a1 = t.ShouldFire(1, out s, out f);          // first: fires
                bool a2 = t.ShouldFire(1, out s, out f);          // suppressed (0 counted)
                bool a3 = t.ShouldFire(1, out s, out f);          // suppressed (1 counted)
                bool a4 = t.ShouldFire(1, out s, out f);          // 2 suppressed: due
                int sAfter = s;
                bool a5 = t.ShouldFire(2, out s, out f);          // generation edge: due
                bool ok = a1 && !a2 && !a3 && a4 && sAfter == 2 && a5;
                Check(r, "the throttle fires first, on its interval and on a generation edge", ok,
                      "first=" + a1 + " next=" + a2 + "/" + a3
                      + " interval=" + a4 + "/" + sAfter + " gen=" + a5);
            }

            return r;
        }

        // ── assertion helpers ────────────────────────────────────────────

        private static string Mark(string notice)
        {
            return notice == null ? "-" : "set";
        }

        /// <summary>The value of one <c>key=value</c> field, or null when the
        /// line does not carry that key. The assertions read FIELDS rather
        /// than search for substrings, so that a line which merely mentions
        /// <c>false</c> somewhere cannot satisfy a check about
        /// <c>active=</c> (#342: a check that cannot fail is worse than no
        /// check).</summary>
        private static string Value(string line, string key)
        {
            if (line == null || string.IsNullOrEmpty(key)) return null;
            string needle = " " + key + "=";
            int i = line.IndexOf(needle, StringComparison.Ordinal);
            if (i < 0) return null;
            int start = i + needle.Length;
            int end = line.IndexOf(' ', start);
            return end < 0 ? line.Substring(start) : line.Substring(start, end - start);
        }

        /// <summary>The single line whose <paramref name="key"/> field equals
        /// <paramref name="wanted"/>, or null when there is not exactly one.
        /// "Exactly one" is part of the assertion: two lines for one actor is
        /// a cardinality defect and must not read as a match.</summary>
        private static string Field(IList<string> lines, string key, string wanted)
        {
            if (lines == null) return null;
            string found = null;
            for (int i = 0; i < lines.Count; i++)
            {
                if (Value(lines[i], key) != wanted) continue;
                if (found != null) return null;
                found = lines[i];
            }
            return found;
        }

        private static string Describe(IList<string> lines)
        {
            if (lines == null) return "(null)";
            var sb = new StringBuilder();
            sb.Append("count=").Append(lines.Count.ToString(CultureInfo.InvariantCulture)).Append(" actors={");
            for (int i = 0; i < lines.Count; i++)
            {
                if (i > 0) sb.Append(',');
                sb.Append(Value(lines[i], "actor") ?? "(none)");
            }
            return sb.Append('}').ToString();
        }

        private static void Check(SelfTestResult r, string name, bool ok, string got)
        {
            if (ok) r.Passed++; else r.Failed++;
            r.Report.Append(ok ? "PASS" : "FAIL").Append(" | case=").Append(name)
                    .Append(" | got=").Append(got ?? "(null)").Append('\n');
        }
    }
}
