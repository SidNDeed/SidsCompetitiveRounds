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
    /// ── FAILURE DIRECTION (#276 / #430) ───────────────────────────────────
    /// The census is pure observation and gates nothing. A seat it cannot
    /// read emits <c>active=? dead=? pos=?</c> and STILL emits its line:
    /// an unreadable seat is the single most interesting row in the census,
    /// and dropping the row you cannot fill is the filter that discards the
    /// line it measures (#441). <see cref="FormatCensus"/> therefore has no
    /// branch that can return fewer lines than it was handed seats.
    ///
    /// A refusal here costs a reader the ability to say where a seat was, and
    /// buys nothing, so there is no refusal — except the session budget
    /// below, whose refusal is announced rather than silent.
    ///
    /// ── THE PROBE TOKEN (#306) ────────────────────────────────────────────
    /// <see cref="Probe"/> exists for no other purpose than to be grepped. It
    /// is not a product string, it is never localised and it names no mode,
    /// so a check that looks for it cannot start passing forever because
    /// someone renamed something. Every line this file emits carries it,
    /// including the budget's exhaustion notice — a notice the probe grep
    /// could not see would make a truncated census indistinguishable from a
    /// census that found nothing.</summary>
    internal static class RosterCensus
    {
        internal const string Prefix = "[ROSTER-CENSUS]";

        /// <summary>Grep target. See the class remarks (#306).</summary>
        internal const string Probe = "SCR_ROSTER_PROBE=1";

        internal const string BoundaryMap = "map";
        internal const string BoundaryGame = "game";

        /// <summary>Printed for every field the reporting seat could not
        /// read. Deliberately not a number: a sentinel that looks like a real
        /// value invents a fact (#305).</summary>
        internal const string Unknown = "?";

        /// <summary>Lines per SESSION, not per room. Section 4.1's census is
        /// one line per fighter per map load — about 700 lines in a sitting
        /// the length of the one this was written for — so this is roughly
        /// six such sittings before the budget refuses, and the refusal says
        /// so out loud. Open question q3 in the diagnosis asks Sid to confirm
        /// the volume; this is the default that ships until he answers.</summary>
        internal const int SessionLineCap = 4000;

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
        }

        /// <summary>A seat present in the room whose body the reporting client
        /// could not resolve at all. It still gets a line.</summary>
        internal static SeatObservation UnreadableSeat(int actor, long viewBatches)
        {
            var s = new SeatObservation();
            s.Actor = actor;
            s.PlayerId = -1;
            s.Team = -1;
            s.ActiveKnown = false;
            s.DeadKnown = false;
            s.PositionKnown = false;
            s.ViewBatches = viewBatches < 0 ? -1 : viewBatches;
            return s;
        }

        /// <summary>A seat read field by field. Each Known flag is passed
        /// separately because the caller reads the four properties through
        /// four independent accesses, any one of which can fail on its own.</summary>
        internal static SeatObservation ReadSeat(
            int actor, int playerId, int team,
            bool activeKnown, bool active,
            bool deadKnown, bool dead,
            bool positionKnown, float x, float y,
            long viewBatches)
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
            return s;
        }

        // ── formatting ───────────────────────────────────────────────────

        internal static string FormatLine(int generation, string boundary, SeatObservation seat)
        {
            var sb = new StringBuilder(160);
            sb.Append(Prefix)
              .Append(" gen=").Append(Num(generation))
              .Append(" boundary=").Append(Label(boundary))
              .Append(" actor=").Append(Num(seat.Actor))
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

        /// <summary>Exactly one line per seat handed in, in the order handed
        /// in. There is no filter and no early exit: see the class remarks on
        /// #441. A null list is zero seats, which is zero lines and not an
        /// exception.</summary>
        internal static List<string> FormatCensus(int generation, string boundary, IList<SeatObservation> seats)
        {
            int n = seats == null ? 0 : seats.Count;
            var lines = new List<string>(n);
            for (int i = 0; i < n; i++)
                lines.Add(FormatLine(generation, boundary, seats[i]));
            return lines;
        }

        /// <summary>The one line the budget prints when it refuses a boundary.
        /// It carries the probe token (see the class remarks) and
        /// <c>census=suppressed</c>, so a reader counting seats at a boundary
        /// can tell "the cap stopped here" from "the census saw nothing".</summary>
        internal static string FormatExhaustionNotice(
            int generation, string boundary, int cap, int used, int wouldEmit)
        {
            return Prefix
                + " gen=" + Num(generation)
                + " boundary=" + Label(boundary)
                + " census=suppressed reason=session-line-cap"
                + " cap=" + Num(cap)
                + " used=" + Num(used)
                + " wouldEmit=" + Num(wouldEmit)
                + " " + Probe;
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

        /// <summary>Every field in the line is <c>key=value</c> separated by a
        /// single space, so a boundary label carrying whitespace would split
        /// one field into two and silently shift every field after it. The
        /// two labels this ships with contain none; the replacement is here
        /// so that a third one added later cannot corrupt the format.</summary>
        private static string Label(string boundary)
        {
            if (string.IsNullOrEmpty(boundary)) return Unknown;
            var sb = new StringBuilder(boundary.Length);
            for (int i = 0; i < boundary.Length; i++)
            {
                char c = boundary[i];
                sb.Append(char.IsWhiteSpace(c) ? '_' : c);
            }
            return sb.ToString();
        }

        // ── the session budget ───────────────────────────────────────────

        /// <summary>Seam for the harness: the wrong budgets are handed to the
        /// same assertions as the real one.</summary>
        internal interface ILineBudget
        {
            /// <summary>Charges <paramref name="lines"/> against the budget.
            /// True means the caller may emit exactly that many lines. False
            /// means it must emit none of them, and the FIRST false of a
            /// session hands back a notice to print.</summary>
            bool TryReserve(int generation, string boundary, int lines, out string exhaustionNotice);
        }

        /// <summary>Whole boundary or nothing, and it says when it stops.
        ///
        /// A partial boundary would be worse than no boundary: the witness
        /// bar counts census lines against the fighter count, and a boundary
        /// truncated mid-way makes a missing seat — the exact defect shape
        /// the census hunts — indistinguishable from a budget running out.
        /// So a boundary that does not fit is refused entire, and the refusal
        /// prints once (#430: a guard is judged by what its refusal costs, and
        /// a silent refusal costs the reader the knowledge that the record
        /// stopped).</summary>
        internal sealed class SessionLineBudget : ILineBudget
        {
            private readonly int _cap;
            private int _used;
            private bool _announced;

            internal SessionLineBudget(int cap)
            {
                _cap = cap < 0 ? 0 : cap;
            }

            internal int Cap { get { return _cap; } }
            internal int Used { get { return _used; } }
            internal bool Announced { get { return _announced; } }

            public bool TryReserve(int generation, string boundary, int lines, out string exhaustionNotice)
            {
                exhaustionNotice = null;
                // A boundary with no seats is not a reservation and must not
                // be able to announce exhaustion: nothing was refused.
                if (lines <= 0) return false;
                if (_used <= _cap - lines)
                {
                    _used += lines;
                    return true;
                }
                if (!_announced)
                {
                    _announced = true;
                    exhaustionNotice = FormatExhaustionNotice(generation, boundary, _cap, _used, lines);
                }
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
        internal delegate List<string> CensusEmitter(int generation, string boundary, IList<SeatObservation> seats);

        /// <summary>The budget under test. Same seam, same reason.</summary>
        internal delegate ILineBudget BudgetFactory(int cap);

        internal static SelfTestResult SelfTest()
        {
            return SelfTest(FormatCensus, DefaultBudget);
        }

        private static ILineBudget DefaultBudget(int cap)
        {
            return new SessionLineBudget(cap);
        }

        internal static SelfTestResult SelfTest(CensusEmitter emit, BudgetFactory budget)
        {
            var r = new SelfTestResult();
            if (emit == null || budget == null)
            {
                r.Failed++;
                r.Report.Append("FAIL | case=selftest was handed no implementation | got=null\n");
                return r;
            }

            // The 1v2 the report was about: a solo seat on one side and two
            // seats on the other. Seat 3 is the one every case below is
            // interested in, because it is the one whose rendered position
            // the reporting seat could not otherwise be asked about.
            SeatObservation Solo() { return ReadSeat(1, 0, 0, true, true, true, false, true, 1.5f, 0.25f, 12); }
            SeatObservation DuoA() { return ReadSeat(2, 1, 1, true, true, true, false, true, -3.75f, 0.5f, 9); }

            // 1. CARDINALITY. Three seats in, three lines out, one per actor.
            {
                var seats = new List<SeatObservation> { Solo(), DuoA(), ReadSeat(3, 2, 1, true, true, true, false, true, 4.5f, -1.25f, 7) };
                var lines = emit(11, BoundaryMap, seats);
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
                var seats = new List<SeatObservation> { Solo(), DuoA(), ReadSeat(3, 2, 1, true, false, true, false, true, 4.5f, -1.25f, 0) };
                var lines = emit(11, BoundaryMap, seats);
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
                var seats = new List<SeatObservation> { Solo(), DuoA(), UnreadableSeat(3, -1) };
                var lines = emit(11, BoundaryMap, seats);
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
                var seats = new List<SeatObservation> { Solo(), DuoA(), ReadSeat(3, 2, 1, true, true, true, false, true, 9999.5f, -4321.25f, 3) };
                var lines = emit(11, BoundaryMap, seats);
                string line = Field(lines, "actor", "3");
                bool ok = line != null && Value(line, "pos") == "9999.5,-4321.25";
                Check(r, "an out-of-bounds position is reported verbatim", ok, line == null ? Describe(lines) : Value(line, "pos"));
            }

            // 5. A position that cannot be read is a question mark, never an
            //    origin sentinel (#305). Both non-finite forms.
            {
                var nan = new List<SeatObservation> { ReadSeat(3, 2, 1, true, true, true, false, true, float.NaN, 1f, 3) };
                var inf = new List<SeatObservation> { ReadSeat(3, 2, 1, true, true, true, false, true, 2f, float.PositiveInfinity, 3) };
                string a = Field(emit(11, BoundaryMap, nan), "actor", "3");
                string b = Field(emit(11, BoundaryMap, inf), "actor", "3");
                bool ok = a != null && b != null
                          && Value(a, "pos") == Unknown && Value(b, "pos") == Unknown;
                Check(r, "a non-finite position is a question mark, not an origin",
                      ok, (a == null ? "(null)" : Value(a, "pos")) + " / " + (b == null ? "(null)" : Value(b, "pos")));
            }

            // 6. Every line carries the probe token (#306).
            {
                var seats = new List<SeatObservation> { Solo(), DuoA(), UnreadableSeat(3, -1) };
                var lines = emit(11, BoundaryGame, seats);
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
                var seats = new List<SeatObservation> { ReadSeat(3, 2, 1, true, true, true, false, true, 4.5f, -1.25f, 3) };
                string line = Field(emit(11, BoundaryMap, seats), "actor", "3");
                bool ok = line != null && Value(line, "pos") == "4.5,-1.25";
                Check(r, "an in-bounds position is reported unchanged", ok,
                      line == null ? "(null)" : Value(line, "pos"));
            }

            // 8. The scalar fields have the same two states as the flags.
            {
                var seats = new List<SeatObservation> { ReadSeat(4, -1, -1, true, true, true, false, true, 0f, 0f, -1) };
                string line = Field(emit(11, BoundaryMap, seats), "actor", "4");
                bool ok = line != null
                          && Value(line, "pid") == Unknown
                          && Value(line, "team") == Unknown
                          && Value(line, "viewBatchesSinceLastBoundary") == Unknown
                          && Value(line, "pos") == "0,0";   // a READ zero is still a fact
                Check(r, "unread scalars are question marks and a read zero is not", ok, line ?? "(null)");
            }

            // 9. Degenerate inputs are empty, not exceptions.
            {
                var none = emit(11, BoundaryMap, new List<SeatObservation>());
                var nil = emit(11, BoundaryMap, null);
                bool ok = none != null && none.Count == 0 && nil != null && nil.Count == 0;
                Check(r, "no seats is no lines, not an exception", ok,
                      (none == null ? "null" : none.Count.ToString(CultureInfo.InvariantCulture))
                      + " / " + (nil == null ? "null" : nil.Count.ToString(CultureInfo.InvariantCulture)));
            }

            // 10. Both boundary labels reach the line as themselves, because a
            //     reader pairs map boundaries with game boundaries to read a
            //     sitting back.
            {
                var seats = new List<SeatObservation> { Solo() };
                string m = Field(emit(11, BoundaryMap, seats), "actor", "1");
                string g = Field(emit(12, BoundaryGame, seats), "actor", "1");
                bool ok = m != null && g != null
                          && Value(m, "boundary") == BoundaryMap && Value(m, "gen") == "11"
                          && Value(g, "boundary") == BoundaryGame && Value(g, "gen") == "12";
                Check(r, "the boundary label and generation reach the line", ok,
                      (m == null ? "(null)" : Value(m, "boundary") + "/" + Value(m, "gen"))
                      + " " + (g == null ? "(null)" : Value(g, "boundary") + "/" + Value(g, "gen")));
            }

            // 11. THE BUDGET IS WHOLE-BOUNDARY-OR-NOTHING, AND IT ANNOUNCES.
            //     Cap 5, two three-seat boundaries: the first fits, the second
            //     does not, and the refusal hands back a notice.
            {
                var b = budget(5);
                string first, second;
                bool okFirst = b.TryReserve(11, BoundaryMap, 3, out first);
                bool okSecond = b.TryReserve(12, BoundaryMap, 3, out second);
                bool ok = okFirst && first == null && !okSecond && second != null;
                Check(r, "a boundary that does not fit is refused entire and announced", ok,
                      "first=" + okFirst + "/" + (first ?? "(null)") + " second=" + okSecond + "/" + (second ?? "(null)"));
            }

            // 12. Exhaustion is announced exactly once per session: a log that
            //     repeats the notice at every boundary is the volume the cap
            //     exists to bound.
            {
                var b = budget(5);
                string first, second, third;
                b.TryReserve(11, BoundaryMap, 3, out first);
                b.TryReserve(12, BoundaryMap, 3, out second);
                bool okThird = b.TryReserve(13, BoundaryGame, 3, out third);
                bool ok = second != null && !okThird && third == null;
                Check(r, "exhaustion is announced exactly once", ok,
                      "second=" + (second == null ? "(null)" : "set") + " third=" + okThird + "/" + (third ?? "(null)"));
            }

            // 13. The notice is greppable by the same token as the census and
            //     says what it suppressed.
            {
                var b = budget(2);
                string notice;
                b.TryReserve(11, BoundaryMap, 3, out notice);
                bool ok = notice != null
                          && Value(notice, "SCR_ROSTER_PROBE") == "1"
                          && Value(notice, "census") == "suppressed"
                          && Value(notice, "wouldEmit") == "3"
                          && Value(notice, "cap") == "2"
                          && Value(notice, "boundary") == BoundaryMap;
                Check(r, "the exhaustion notice carries the probe token and its cause", ok, notice ?? "(null)");
            }

            // 14. NEGATIVE CONTROL for 11 to 13. A boundary inside the budget
            //     is granted and says nothing, so those cases measure the
            //     refusal and not "this budget always produces a notice".
            {
                var b = budget(SessionLineCap);
                string notice;
                bool granted = b.TryReserve(11, BoundaryMap, 3, out notice);
                Check(r, "a boundary inside the budget is granted silently",
                      granted && notice == null, "granted=" + granted + " notice=" + (notice ?? "(null)"));
            }

            // 15. A zero-seat boundary reserves nothing and cannot announce
            //     exhaustion — nothing was refused. Without this an empty room
            //     would burn the one notice the session has.
            {
                var b = budget(0);
                string notice;
                bool granted = b.TryReserve(11, BoundaryMap, 0, out notice);
                string later;
                b.TryReserve(12, BoundaryMap, 1, out later);
                Check(r, "a zero-seat boundary neither reserves nor announces",
                      !granted && notice == null && later != null,
                      "granted=" + granted + " notice=" + (notice ?? "(null)") + " later=" + (later == null ? "(null)" : "set"));
            }

            return r;
        }

        // ── assertion helpers ────────────────────────────────────────────

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
