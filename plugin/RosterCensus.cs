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
    /// objects, then dispatch PlayerManager.MovePlayers) has not run yet. So
    /// every field on a call-in row describes the state this seat INHERITED
    /// from the point that just ended: the previous round's terminal
    /// positions and the pre-revive dead flags. It is a useful row, and a
    /// misleading one if read as the state on the map being loaded.
    ///
    /// <see cref="BoundaryMapSettled"/> is taken a fixed delay later, from
    /// the per-frame tick, and carries <c>sinceCallInMs</c> so a reader sees
    /// the gap that was actually measured rather than trusting a claim about
    /// it. THAT DELAY IS ALL THE ROW ASSERTS ABOUT ITSELF: it is a sample
    /// taken about two seconds after the call-in, carrying the elapsed time
    /// it measured. The delay was chosen against learning #304's reading that
    /// the per-player MovePlayers coroutine runs on the order of a second,
    /// but a sample's TIMING is a timing and never an ORDERING.
    ///
    /// Saying it any more strongly would be the false guarantee #351 is
    /// about, and it would be false in exactly the case the instrument exists
    /// for (#302): when the transition is the thing that stalled, the settled
    /// row still carries the state the previous point ended in, and wording
    /// that placed the row past the transition would file that reading under
    /// a claim untrue of it.
    ///
    /// ── THE ONE CANONICAL INTERPRETATION ──────────────────────────────────
    /// Each of the three sample sites carries the SAME interpretation
    /// sentence, word for word, between the two markers below. The markers
    /// exist for no other purpose than to be found (#306), and
    /// tools/roster-census-harness/check-source-claims.ps1 holds the sentence
    /// itself: between the markers the text must match it exactly, and
    /// outside them a sample site may not use any of the vocabulary that
    /// checker prints. The earlier arrangement was a list of forbidden
    /// phrases, which is a check that cannot fail (#342 / #431) — a reworded
    /// outcome claim walked straight past it.
    /// SCR_CENSUS_MOVE_CLAIM_BEGIN
    /// A settled row asserts the delay it measured and never a position in
    /// vanilla's transition, so a call-in row and a settled row carrying
    /// equal pos fields are two observations that agree and are not a
    /// reading that the seat did not move.
    /// SCR_CENSUS_MOVE_CLAIM_END
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

        /// <summary>The sample taken in the Postfix of the call-in RPC, at
        /// the moment that RPC is received, and carrying no elapsed field.
        /// The label asserts WHEN the sample was taken; what the fields on
        /// such a row then describe is the class remarks' business.</summary>
        internal const string BoundaryMapCallIn = "map-callin";

        /// <summary>The sample taken about two seconds after the call-in,
        /// from the per-frame tick, carrying the elapsed time it measured as
        /// <c>sinceCallInMs</c>. The label asserts that delay and nothing
        /// about where the transition had got to by then.
        ///
        /// SCR_CENSUS_MOVE_CLAIM_BEGIN
        /// A settled row asserts the delay it measured and never a position
        /// in vanilla's transition, so a call-in row and a settled row
        /// carrying equal pos fields are two observations that agree and are
        /// not a reading that the seat did not move.
        /// SCR_CENSUS_MOVE_CLAIM_END</summary>
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

        /// <summary>The roster read itself raised. Nothing is known about the
        /// room's actor set: this is the instrument failing to read, not a
        /// reading of an empty room.</summary>
        internal const string ReasonRosterReadThrew = "roster-read-threw";

        /// <summary>The roster read COMPLETED and handed back no list at all.
        /// Distinct from a raise because the call returned — a different
        /// question about the same subsystem, and a different next step for
        /// the reader.</summary>
        internal const string ReasonRosterListNull = "roster-list-null";

        /// <summary>The read completed, handed back a list, and the list held
        /// no actors. The only one of the four that is a READING of the room
        /// rather than a failure to read it.</summary>
        internal const string ReasonRosterEmpty = "roster-read-empty";

        /// <summary>The read completed and every actor it held declared the
        /// spectator role, so the census set is empty by the filter rather
        /// than by the room. EVERY entry: an entry the read handed back as
        /// null is not a spectator declaration, so a roster holding one of
        /// those cannot carry this token — see
        /// <see cref="ReasonRosterEntryNull"/>.</summary>
        internal const string ReasonAllSpectators = "every-actor-is-a-spectator";

        /// <summary>The read completed and handed back at least one NULL
        /// entry, and no entry became a census seat. A null entry is an
        /// observation in its own right, not an absence: skipping it before
        /// classifying would let a roster of one null entry and one spectator
        /// entry print the all-spectators token, which is a claim about every
        /// entry that the null entry falsifies (#441).</summary>
        internal const string ReasonRosterEntryNull = "roster-entry-null";

        /// <summary>Not an empty cause at all: the observation produced at
        /// least one census seat, so the boundary emits rows rather than a
        /// notice. It is a token so that <see cref="ReasonForObservation"/>
        /// is TOTAL — every observation it can be handed maps to exactly one
        /// token that describes it, and the seats-present case is not an
        /// absent answer or a null (#276).</summary>
        internal const string ReasonRosterSeatsPresent = "roster-seats-present";

        /// <summary>A zero-seat boundary whose cause was not classified. It
        /// exists so that the unhandled case fails toward saying something
        /// TRUE (#276 / #430): a cause nobody classified must not borrow the
        /// token of one that was, because <c>roster-read-empty</c> is a
        /// positive claim that the room really held no actors.</summary>
        internal const string ReasonRosterEmptyUnclassified = "roster-empty-unclassified";

        /// <summary>The four ways a roster read reaches the census with no
        /// seats. An enum rather than four call sites each choosing a string,
        /// because the mapping is then one total function a harness can drive
        /// — and a collapse of any two causes reds a named case instead of
        /// waiting for a reader to notice (#342).</summary>
        internal enum EmptyCause
        {
            ReadThrew = 0,
            ListNull = 1,
            NoActors = 2,
            AllSpectators = 3,
        }

        /// <summary>Every cause its own token, and an unrecognised cause its
        /// own token as well. Separating "the read raised" from "the read
        /// returned nothing" ON THE LINE is the whole requirement: the two
        /// have different next steps and used to print the same word.</summary>
        internal static string ReasonForEmptyCause(EmptyCause cause)
        {
            switch (cause)
            {
                case EmptyCause.ReadThrew: return ReasonRosterReadThrew;
                case EmptyCause.ListNull: return ReasonRosterListNull;
                case EmptyCause.NoActors: return ReasonRosterEmpty;
                case EmptyCause.AllSpectators: return ReasonAllSpectators;
            }
            return ReasonRosterEmptyUnclassified;
        }

        /// <summary>Every reason a zero-seat boundary can carry. The per-cause
        /// notice throttles are built from this array, so the set of causes
        /// and the set of throttles cannot drift apart — and the array is
        /// filled once at type initialisation and never appended to, which is
        /// what makes the throttle set bounded.</summary>
        internal static readonly string[] EmptyCauseReasons =
        {
            ReasonRosterReadThrew,
            ReasonRosterListNull,
            ReasonRosterEmpty,
            ReasonAllSpectators,
            ReasonRosterEntryNull,
            ReasonRosterEmptyUnclassified,
        };

        // ── the roster observation, and the TOTAL mapping over it ─────────

        /// <summary>What the roster read actually handed back, counted by
        /// KIND before anything is classified. Three counts, because three
        /// kinds is everything an entry can be once the read itself has
        /// succeeded: the entry was null, the entry declared the spectator
        /// role, or the entry became a census seat.
        ///
        /// The counts exist because the classification has to be a function
        /// of what was OBSERVED, and an entry dropped by a filter before the
        /// classification runs is an observation the cause token can then
        /// contradict. <see cref="NotObserved"/> is the honest state for the
        /// two causes that happen BEFORE any entry is seen — a read that
        /// raised and a read that returned no list observed nothing, and
        /// printing three zeroes there would assert three facts nobody
        /// measured (#305).</summary>
        internal struct RosterObservation
        {
            internal int NullEntries;
            internal int SpectatorEntries;
            internal int SeatEntries;

            internal static RosterObservation Of(int nullEntries, int spectatorEntries, int seatEntries)
            {
                RosterObservation o;
                o.NullEntries = nullEntries;
                o.SpectatorEntries = spectatorEntries;
                o.SeatEntries = seatEntries;
                return o;
            }

            /// <summary>No entry was reached at all. Every count is negative,
            /// which is what makes the fields print as <see cref="Unknown"/>
            /// rather than as a measured zero.</summary>
            internal static RosterObservation NotObserved
            {
                get { return Of(-1, -1, -1); }
            }

            internal bool Observed
            {
                get { return NullEntries >= 0 && SpectatorEntries >= 0 && SeatEntries >= 0; }
            }

            internal int Entries
            {
                get { return Observed ? NullEntries + SpectatorEntries + SeatEntries : -1; }
            }
        }

        /// <summary>The TOTAL mapping from an observation to the one token
        /// that describes it. Total means every observation this can be
        /// handed — every multiset of null, spectator and seat entries, and
        /// the un-observed state as well — reaches exactly one token, and the
        /// token is true of the observation that produced it.
        ///
        /// The order of the arms is the whole content of the fix. A seat
        /// present means rows, whatever else was seen. Otherwise a NULL entry
        /// is decided BEFORE the spectator arm, because
        /// <see cref="ReasonAllSpectators"/> is a claim about EVERY entry and
        /// one null entry falsifies it: the earlier arrangement counted
        /// spectators over a list the nulls had already been dropped from, so
        /// a roster of one null entry and one spectator entry reported that
        /// every actor had declared spectator. A cause a reader cannot
        /// separate on the line is not distinguished, and a cause that does
        /// not describe the observation is worse than none (#276 / #430).
        ///
        /// A negative count is not a multiset and cannot be described by any
        /// of the four, so it takes the unclassified token rather than the
        /// nearest plausible one.</summary>
        internal static string ReasonForObservation(RosterObservation observed)
        {
            if (!observed.Observed) return ReasonRosterEmptyUnclassified;
            if (observed.SeatEntries > 0) return ReasonRosterSeatsPresent;
            if (observed.NullEntries > 0) return ReasonRosterEntryNull;
            if (observed.SpectatorEntries > 0) return ReasonAllSpectators;
            return ReasonRosterEmpty;
        }

        /// <summary>The room sizes the observation mapping is enumerated over
        /// by the self-test. Eight rather than four: a 2v2 room is four
        /// seats, an FFA lobby is larger, and the bound is stated here so the
        /// enumeration cannot quietly shrink to the sizes that happen to
        /// pass.</summary>
        internal const int ObservationEnumerationBound = 8;

        // ── the settled sample's clock ────────────────────────────────────

        /// <summary>Where the settled sample's clock is anchored, and when it
        /// comes due. Pure arithmetic, so the rule can be EXECUTED rather
        /// than asserted about (#391).
        ///
        /// It is handed BOTH readings on purpose. The anchor is the one taken
        /// BEFORE the call-in rows were emitted, because the field the
        /// settled row prints is the call-in-to-sample delay: anchoring on
        /// the reading taken AFTER the emission folds the cost of emitting
        /// those rows into the gap and the printed field then UNDERSTATES the
        /// delay by that cost, which on a slow synchronous log sink is the
        /// part of the interval a reader most wants back. A wrong
        /// implementation can therefore pick the wrong reading, which is what
        /// makes the assertion able to fail.</summary>
        internal static void ScheduleSettle(long beforeEmissionTicks, long afterEmissionTicks,
                                            long frequency, double delaySeconds,
                                            out long anchorTicks, out long dueTicks)
        {
            anchorTicks = beforeEmissionTicks;
            dueTicks = beforeEmissionTicks + (long)(delaySeconds * frequency);
        }

        /// <summary>Milliseconds between two stopwatch readings. A backwards
        /// pair reads 0 and an unusable frequency reads -1, which prints as
        /// <see cref="Unknown"/> — never a fabricated number.</summary>
        internal static long ElapsedMilliseconds(long fromTicks, long toTicks, long frequency)
        {
            long delta = toTicks - fromTicks;
            if (delta < 0) return 0;
            if (frequency <= 0) return -1;
            return (long)(delta * 1000.0 / frequency);
        }

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
            BoundaryContext ctx, string reason, RosterObservation observed, int suppressed, bool final)
        {
            var sb = new StringBuilder(260);
            sb.Append(Prefix);
            AppendBoundaryFields(sb, ctx);
            sb.Append(" census=empty reason=").Append(Label(reason));
            // The counts the reason was DERIVED from, on the same line as the
            // reason. Without the null count a reader cannot tell the
            // all-spectators reading from a roster that held entries the read
            // could not hand back, and those have different next steps.
            sb.Append(" observedEntries=").Append(Count(observed.Entries))
              .Append(" nullEntries=").Append(Count(observed.NullEntries))
              .Append(" spectatorEntries=").Append(Count(observed.SpectatorEntries))
              .Append(" seatEntries=").Append(Count(observed.SeatEntries));
            AppendNoticeTail(sb, suppressed, final);
            return sb.ToString();
        }

        /// <summary>A count that was measured, or <see cref="Unknown"/> when
        /// nothing was observed. A negative count never prints as a number:
        /// "0 null entries" and "no entry was reached" are different
        /// readings and the line has to keep them apart (#305).</summary>
        private static string Count(int v)
        {
            return v < 0 ? Unknown : v.ToString(CultureInfo.InvariantCulture);
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

        // ── one throttle per CAUSE ───────────────────────────────────────

        /// <summary>Seam for the harness: the wrong throttle sets are handed
        /// to the same assertions as the real one.</summary>
        internal interface ICauseNotices
        {
            /// <summary>True when THIS occurrence of THIS cause should print.
            /// <paramref name="suppressed"/> counts occurrences of the SAME
            /// cause since that cause's previous notice, and
            /// <paramref name="final"/> marks the last notice this cause will
            /// print. "Same cause" means same throttle: for a reason the set
            /// was built with, that is the reason alone.</summary>
            bool ShouldFire(string reason, int generation, out int suppressed, out bool final);
        }

        internal delegate ICauseNotices CauseNoticesFactory(int interval, int ceiling);

        /// <summary>One <see cref="NoticeThrottle"/> per cause, and no shared
        /// state between them.
        ///
        /// A single throttle across all causes suppresses by ARRIVAL ORDER
        /// rather than by cause: the first zero-seat boundary of a roster
        /// generation spends the generation's notice, and a boundary of a
        /// DIFFERENT cause in the same generation is then silent — so the
        /// cause a reader most needs to see is the one least likely to be on
        /// the record, because it is whichever one happened second. Splitting
        /// the state is the fix: each cause has its own first notice, its own
        /// suppressed-since counter, its own interval clock and its own
        /// ceiling, so each cause's last line is marked <c>final=true</c> on
        /// its own terms (#430) and the end of one cause's record is not the
        /// end of another's.
        ///
        /// BOUNDED BY CONSTRUCTION: the dictionary is filled once from the
        /// reasons handed in and never grows. A reason not on that list still
        /// announces — through ONE shared fallback throttle rather than
        /// through silence, because the unhandled case must fail toward
        /// saying something (#276). Two unlisted reasons would therefore share
        /// a throttle, which is the price of a bounded set; it is not a live
        /// path, because <see cref="EmptyCauseReasons"/> carries every reason
        /// the emitter can produce — including the unclassified one — and
        /// that array is where a new cause is added.</summary>
        internal sealed class CauseNoticeThrottles : ICauseNotices
        {
            private readonly Dictionary<string, NoticeThrottle> _byReason;
            private readonly NoticeThrottle _unlisted;

            internal CauseNoticeThrottles(int interval, int ceiling, string[] reasons)
            {
                _byReason = new Dictionary<string, NoticeThrottle>(StringComparer.Ordinal);
                if (reasons != null)
                    for (int i = 0; i < reasons.Length; i++)
                    {
                        string reason = reasons[i];
                        if (reason == null || _byReason.ContainsKey(reason)) continue;
                        _byReason.Add(reason, new NoticeThrottle(interval, ceiling));
                    }
                _unlisted = new NoticeThrottle(interval, ceiling);
            }

            public bool ShouldFire(string reason, int generation, out int suppressed, out bool final)
            {
                NoticeThrottle throttle;
                if (reason == null || !_byReason.TryGetValue(reason, out throttle))
                    throttle = _unlisted;
                return throttle.ShouldFire(generation, out suppressed, out final);
            }
        }

        /// <summary>The real throttle set, over the real cause list.</summary>
        internal static ICauseNotices DefaultCauseNotices(int interval, int ceiling)
        {
            return new CauseNoticeThrottles(interval, ceiling, EmptyCauseReasons);
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

        /// <summary>The empty-roster notice under test. A separate seam from
        /// <see cref="NoticeFormatter"/> because this line carries the counts
        /// the reason was derived from, and "drop the counts, the reason says
        /// it all" is the natural tidy-up edit that has to be shown to
        /// fail.</summary>
        internal delegate string EmptyNoticeFormatter(BoundaryContext ctx, string reason,
                                                      RosterObservation observed, int suppressed, bool final);

        /// <summary>The observation classifier under test. Same seam, same
        /// reason: dropping the null entries before counting spectators is
        /// the natural tidy-up edit ("a null entry is not an actor"), and
        /// without a seam the enumeration asserting a TOTAL mapping could
        /// never be shown to fail (#342).</summary>
        internal delegate string RosterObservationClassifier(RosterObservation observed);

        /// <summary>The settled sample's clock under test. Same seam: taking
        /// the reading after the call-in rows were emitted is the natural
        /// edit ("arm it when the work is done"), and it is only visible as a
        /// defect when the two readings differ.</summary>
        internal delegate void SettleScheduler(long beforeEmissionTicks, long afterEmissionTicks,
                                               long frequency, double delaySeconds,
                                               out long anchorTicks, out long dueTicks);

        /// <summary>The empty-cause classifier under test. Same seam, same
        /// reason: collapsing two causes onto one token is the natural
        /// tidy-up edit ("they are both a failed read"), and without a seam
        /// the case asserting four distinct tokens could never be shown to
        /// fail (#342).</summary>
        internal delegate string EmptyCauseClassifier(EmptyCause cause);

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
                                                EmptyNoticeFormatter emptyNotice, NoticeFormatter declinedNotice)
        {
            return SelfTest(emit, budget, emptyNotice, declinedNotice,
                            ReasonForEmptyCause, DefaultCauseNotices,
                            ReasonForObservation, ScheduleSettle);
        }

        internal static SelfTestResult SelfTest(CensusEmitter emit, BudgetFactory budget,
                                                EmptyNoticeFormatter emptyNotice, NoticeFormatter declinedNotice,
                                                EmptyCauseClassifier classify, CauseNoticesFactory causeNotices,
                                                RosterObservationClassifier observe, SettleScheduler schedule)
        {
            var r = new SelfTestResult();
            if (emit == null || budget == null || emptyNotice == null || declinedNotice == null
                || classify == null || causeNotices == null || observe == null || schedule == null)
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
                string empty = emptyNotice(ctx, ReasonRosterReadThrew,
                                           RosterObservation.NotObserved, 0, false);
                string declined = declinedNotice(ctx, ReasonNotModRoom, 4, false);
                bool ok = Value(empty, "census") == "empty"
                          && Value(empty, "reason") == ReasonRosterReadThrew
                          && Value(empty, "seats") == "0"
                          && Value(empty, "nullEntries") == Unknown
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

            // 26. THE FOUR EMPTY CAUSES REACH THE LINE AS FOUR TOKENS. A read
            //     that raised and a read that returned no list are different
            //     facts with different next steps; printing one word for both
            //     leaves the reader unable to separate them, which is the
            //     whole job of the reason field. Distinctness is asserted on
            //     the CLASSIFIER and then again on the rendered notice, so a
            //     token that is distinct in code and collapsed by the
            //     formatter still reds.
            {
                string threw = classify(EmptyCause.ReadThrew);
                string listNull = classify(EmptyCause.ListNull);
                string noActors = classify(EmptyCause.NoActors);
                string allSpec = classify(EmptyCause.AllSpectators);
                var tokens = new List<string> { threw, listNull, noActors, allSpec };

                bool ok = true;
                for (int i = 0; i < tokens.Count; i++)
                {
                    if (string.IsNullOrEmpty(tokens[i])) { ok = false; break; }
                    for (int j = i + 1; j < tokens.Count; j++)
                        if (tokens[i] == tokens[j]) { ok = false; break; }
                    if (!ok) break;
                }

                var ctx = BoundaryContext.For(11, BoundaryMapCallIn, -1, 2);
                if (ok)
                    for (int i = 0; i < tokens.Count; i++)
                        if (Value(emptyNotice(ctx, tokens[i], RosterObservation.NotObserved, 0, false),
                                  "reason") != tokens[i])
                        { ok = false; break; }

                Check(r, "the four empty causes reach the line as four distinct reasons", ok,
                      threw + " / " + listNull + " / " + noActors + " / " + allSpec);
            }

            // 27. EACH EMPTY CAUSE GETS ITS OWN FIRST NOTICE. With one
            //     throttle across all four, the first zero-seat boundary of a
            //     roster generation spends that generation's notice and a
            //     boundary of a DIFFERENT cause in the same generation is
            //     silent — so whichever cause arrived second is the one
            //     missing from the record.
            {
                var t = causeNotices(1000, 99);
                int s; bool f;
                bool a1 = t.ShouldFire(ReasonRosterReadThrew, 11, out s, out f);   // A: its first
                bool a2 = t.ShouldFire(ReasonRosterReadThrew, 11, out s, out f);   // A: suppressed
                bool b1 = t.ShouldFire(ReasonRosterListNull, 11, out s, out f);    // B: its OWN first
                bool c1 = t.ShouldFire(ReasonAllSpectators, 11, out s, out f);     // C: its OWN first
                bool ok = a1 && !a2 && b1 && c1;
                Check(r, "each empty cause announces its own first notice", ok,
                      "A=" + a1 + "/" + a2 + " B=" + b1 + " C=" + c1);
            }

            // 28. EACH EMPTY CAUSE COUNTS ITS OWN SUPPRESSED TOTAL, on its own
            //     interval clock. Occurrences of another cause in between must
            //     move neither the count nor the moment the notice is due.
            {
                var t = causeNotices(2, 99);
                int s; bool f;
                t.ShouldFire(ReasonRosterReadThrew, 11, out s, out f);   // A fires
                t.ShouldFire(ReasonRosterReadThrew, 11, out s, out f);   // A suppressed (1)
                t.ShouldFire(ReasonRosterListNull, 11, out s, out f);    // B's own first
                t.ShouldFire(ReasonRosterListNull, 11, out s, out f);    // B suppressed
                t.ShouldFire(ReasonRosterReadThrew, 11, out s, out f);   // A suppressed (2)
                int suppressedForA;
                bool due = t.ShouldFire(ReasonRosterReadThrew, 11, out suppressedForA, out f);
                bool ok = due && suppressedForA == 2;
                Check(r, "each empty cause counts its own suppressed total", ok,
                      "due=" + due + " suppressed=" + suppressedForA.ToString(CultureInfo.InvariantCulture));
            }

            // 29. EACH EMPTY CAUSE MARKS ITS OWN LAST NOTICE FINAL, and one
            //     cause reaching its ceiling must not end another cause's
            //     record. Ceiling 1 here: one notice per cause, each marked
            //     final on its own terms (#430).
            {
                var t = causeNotices(1000, 1);
                int s; bool finalA, finalB, finalLater;
                bool a1 = t.ShouldFire(ReasonRosterReadThrew, 11, out s, out finalA);
                bool b1 = t.ShouldFire(ReasonRosterListNull, 11, out s, out finalB);
                bool a2 = t.ShouldFire(ReasonRosterReadThrew, 12, out s, out finalLater);
                bool ok = a1 && finalA && b1 && finalB && !a2;
                Check(r, "each empty cause marks its own last notice final", ok,
                      "A=" + a1 + "/final=" + finalA + " B=" + b1 + "/final=" + finalB
                      + " A-after-close=" + a2);
            }

            // 30. NEGATIVE CONTROL for 27 to 29. Splitting the state per cause
            //     must not turn the throttle off: repeat occurrences of ONE
            //     cause still share that cause's own throttle. Without this,
            //     "every occurrence announces" would satisfy 27 to 29 and the
            //     three of them would be measuring nothing.
            {
                var t = causeNotices(1000, 99);
                int s; bool f;
                bool a1 = t.ShouldFire(ReasonRosterReadThrew, 11, out s, out f);
                bool a2 = t.ShouldFire(ReasonRosterReadThrew, 11, out s, out f);
                bool a3 = t.ShouldFire(ReasonRosterReadThrew, 11, out s, out f);
                bool ok = a1 && !a2 && !a3;
                Check(r, "repeat occurrences of one cause still share that cause's throttle", ok,
                      "first=" + a1 + " next=" + a2 + "/" + a3);
            }

            // 31. A CAUSE THE SET DOES NOT RECOGNISE STILL ANNOUNCES. The
            //     unhandled case has to fail toward the record, not toward
            //     silence (#276 / #430): a zero-seat boundary carrying a
            //     reason nobody listed is still a zero-seat boundary, and
            //     dropping it would make the one unclassified case the one
            //     case with no line.
            {
                var t = causeNotices(1000, 99);
                int s; bool f;
                bool fired = t.ShouldFire("a-cause-not-on-the-list", 11, out s, out f);
                Check(r, "an unrecognised empty cause still announces", fired, "fired=" + fired);
            }

            // 32. THE OBSERVATION MAPPING IS TOTAL, AND EVERY TOKEN IS TRUE
            //     OF THE OBSERVATION THAT PRODUCED IT. Not a sample of the
            //     interesting shapes: EVERY multiset over the three kinds an
            //     entry can be — null, spectator, seat — up to the stated
            //     room-size bound. Each of the four outcomes is asserted as a
            //     BICONDITIONAL against its own predicate, so a token that is
            //     right for one multiset and wrong for another still reds,
            //     and so does a mapping that returns two plausible tokens for
            //     the same observation.
            //
            //     The arm this case exists for is the null entry: the earlier
            //     arrangement dropped nulls before counting, so [null,
            //     spectator] reported that every actor had declared
            //     spectator — a cause that does not describe the observation.
            {
                bool ok = true;
                int enumerated = 0;
                string firstBad = null;
                for (int nulls = 0; nulls <= ObservationEnumerationBound && ok; nulls++)
                    for (int spectators = 0; nulls + spectators <= ObservationEnumerationBound && ok; spectators++)
                        for (int seats2 = 0;
                             nulls + spectators + seats2 <= ObservationEnumerationBound && ok;
                             seats2++)
                        {
                            var obs = RosterObservation.Of(nulls, spectators, seats2);
                            string token = observe(obs);
                            enumerated++;

                            bool wantSeats = seats2 > 0;
                            bool wantNull = !wantSeats && nulls > 0;
                            bool wantAllSpec = !wantSeats && nulls == 0 && spectators > 0;
                            bool wantEmpty = !wantSeats && nulls == 0 && spectators == 0;

                            bool row = !string.IsNullOrEmpty(token)
                                       && (token == ReasonRosterSeatsPresent) == wantSeats
                                       && (token == ReasonRosterEntryNull) == wantNull
                                       && (token == ReasonAllSpectators) == wantAllSpec
                                       && (token == ReasonRosterEmpty) == wantEmpty;
                            if (!row)
                            {
                                ok = false;
                                firstBad = "nulls=" + nulls + " spectators=" + spectators
                                           + " seats=" + seats2 + " token=" + (token ?? "(null)");
                            }
                        }

                // The un-observed state is part of the domain: a read that
                // raised or returned no list reached no entry at all, and a
                // count it never took must not be classified as a zero.
                if (ok && observe(RosterObservation.NotObserved) != ReasonRosterEmptyUnclassified)
                {
                    ok = false;
                    firstBad = "not-observed token=" + observe(RosterObservation.NotObserved);
                }

                Check(r, "the observation mapping is total over every entry multiset", ok,
                      ok ? "enumerated=" + enumerated.ToString(CultureInfo.InvariantCulture)
                         : firstBad);
            }

            // 33. THE NULL COUNT IS ON THE LINE. A token nobody can check
            //     against the counts it was derived from is a claim, and the
            //     one reading this instrument has to keep apart from
            //     all-spectators is a roster that held entries the read could
            //     not hand back.
            {
                var ctx = BoundaryContext.For(11, BoundaryMapCallIn, -1, 2);
                string reason = observe(RosterObservation.Of(1, 1, 0));
                string line = emptyNotice(ctx, reason, RosterObservation.Of(1, 1, 0), 0, false);
                bool ok = reason == ReasonRosterEntryNull
                          && Value(line, "reason") == ReasonRosterEntryNull
                          && Value(line, "nullEntries") == "1"
                          && Value(line, "spectatorEntries") == "1"
                          && Value(line, "seatEntries") == "0"
                          && Value(line, "observedEntries") == "2";
                Check(r, "a null entry carries its own token and its count onto the line", ok, line);
            }

            // 34. THE SETTLED SAMPLE'S CLOCK IS ANCHORED BEFORE THE CALL-IN
            //     ROWS ARE EMITTED. The row's whole assertion about itself is
            //     the delay it measured, so the field has to be the
            //     call-in-to-sample gap and not the gap minus whatever
            //     emitting the call-in rows cost. Anchoring after the
            //     emission understates it by exactly that cost, which is
            //     largest on the slow synchronous sink a stall investigation
            //     is most likely to be reading.
            {
                const long frequency = 1000;            // one tick per millisecond
                const long beforeEmission = 10000;      // the call-in instant
                const long afterEmission = 10450;       // emitting the rows cost 450 ms
                long anchor, due;
                schedule(beforeEmission, afterEmission, frequency, 2.0, out anchor, out due);

                long reported = ElapsedMilliseconds(anchor, due, frequency);
                long actualSinceCallIn = ElapsedMilliseconds(beforeEmission, due, frequency);

                bool ok = anchor == beforeEmission
                          && due == beforeEmission + 2000
                          && reported == actualSinceCallIn
                          && reported == 2000;
                Check(r, "the settled sample's clock is anchored at the call-in, not after the emission", ok,
                      "anchor=" + anchor.ToString(CultureInfo.InvariantCulture)
                      + " due=" + due.ToString(CultureInfo.InvariantCulture)
                      + " reported=" + reported.ToString(CultureInfo.InvariantCulture)
                      + " sinceCallIn=" + actualSinceCallIn.ToString(CultureInfo.InvariantCulture));
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
