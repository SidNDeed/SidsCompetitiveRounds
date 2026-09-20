using System;

namespace CompetitiveRounds
{
    /// <summary>
    /// Bug 392 item C: the arrival-gap histogram, as decisions rather than as
    /// statements inside a Unity type.
    ///
    /// The histogram this replaces could not record the failure it exists to
    /// record. Two reasons, both visible in the reported log, which after 47
    /// seconds of total silence reported gap1500=0 and maxGap=514/514/542 ms
    /// for all three actors:
    ///
    ///   * the counters were bumped only on the ARRIVAL of a batch, so a
    ///     silence that no batch ever ends was never measured at all, and
    ///   * a sample above the 60 s cap was discarded WHOLE, so even a silence
    ///     that does end is thrown away once it is long enough to matter.
    ///
    /// Both readings were "correct" for what each measured, and together they
    /// made a check that cannot fail in the one case it is for (#431/#441).
    /// Here: an over-cap sample is CLAMPED into the top bin and counted
    /// separately, so a clamp is never mistaken for a measurement, and an open
    /// gap is flushed at the room exit through the same bin rules, so a clean
    /// exit still reports empty bins.
    ///
    /// Free of Unity, Photon and BepInEx so a harness executes it.
    /// </summary>
    internal static class NetGapAccounting
    {
        /// <summary>The largest gap that is treated as a measurement. Above
        /// this the sample is clamped to this value and counted as a clamp.
        /// Same number the analyser used before; what changed is what happens
        /// at the boundary.</summary>
        internal const int MaxMeasuredGapMs = 60000;

        internal const int Gap300Ms = 300;
        internal const int Gap750Ms = 750;
        internal const int Gap1500Ms = 1500;

        /// <summary>One window's arrival-gap counters. Deliberately only the
        /// arrival-side numbers: delivery excess is computed from a peer's own
        /// timestamps and stays with the caller, because the flush has no
        /// sender stamp to compute one from.</summary>
        internal struct Bins
        {
            internal long Gap300;
            internal long Gap750;
            internal long Gap1500;
            /// <summary>Samples whose arrival gap exceeded the cap and were
            /// clamped into the top bin. A distinct counter so a clamped row
            /// is never read as a measurement of MaxMeasuredGapMs.</summary>
            internal long GapOverCap;
            internal int MaxArrivalGapMs;

            internal void Clear()
            {
                Gap300 = 0;
                Gap750 = 0;
                Gap1500 = 0;
                GapOverCap = 0;
                MaxArrivalGapMs = 0;
            }
        }

        /// <summary>Whether a delivery-excess figure may be computed from this
        /// pair. Both halves must be inside the cap: the excess is the arrival
        /// interval less the interval the peer's own stamps account for, and
        /// with either half clamped or absurd the difference is not an
        /// observation of anything.</summary>
        internal static bool ExcessUsable(int arrivalGapMs, int senderGapMs)
        {
            return arrivalGapMs >= 0
                && arrivalGapMs <= MaxMeasuredGapMs
                && senderGapMs <= MaxMeasuredGapMs;
        }

        /// <summary>Account for a CLOSED gap - one a batch arrival ended.
        /// Returns the value that was binned (the clamp, when clamped), or -1
        /// when the sample carried no usable arrival measurement.</summary>
        internal static int Record(ref Bins bins, int arrivalGapMs, int senderGapMs)
        {
            // A negative arrival gap is a clock reading, not a measurement.
            // Dropped, exactly as before.
            if (arrivalGapMs < 0) return -1;
            bool overCap = arrivalGapMs > MaxMeasuredGapMs;
            int measured = overCap ? MaxMeasuredGapMs : arrivalGapMs;
            if (overCap) bins.GapOverCap++;
            AddToBins(ref bins, measured);
            return measured;
        }

        /// <summary>Account for an OPEN gap at a room exit - one that no batch
        /// ever ended. Same bin rules as a closed gap, so a room whose worst
        /// open gap is 40 ms still reports every bin at zero: the flush must
        /// not manufacture a terminal bin on a clean exit. No sender stamp
        /// exists for a gap that never closed, so nothing here touches
        /// delivery excess or the jitter counters.</summary>
        internal static int FlushOpenGap(ref Bins bins, int openGapMs)
        {
            if (openGapMs <= 0) return -1;
            bool overCap = openGapMs > MaxMeasuredGapMs;
            int measured = overCap ? MaxMeasuredGapMs : openGapMs;
            if (overCap) bins.GapOverCap++;
            AddToBins(ref bins, measured);
            return measured;
        }

        /// <summary>Whether an interval still open when a room ends is a
        /// MEASUREMENT, given the room's game state at that edge.
        ///
        /// The accounting above cannot answer this: handed an open gap it
        /// bins it, which is correct and is why the negative control for the
        /// flush passes whatever the caller decides. The decision is
        /// therefore the thing worth testing, and it lives here — free of
        /// engine types — rather than only as a branch inside the diagnostics
        /// class the harness cannot compile.
        ///
        /// TRUE only while a game is OPEN and has not reached its score edge.
        /// After the score edge a silence is expected: the players are reading
        /// the scoreboard, and a late orphan batch can re-arm a baseline in
        /// that window, so an ungated flush bins the reading time as a
        /// terminal outage. Before any game opens there is no stream whose
        /// silence means anything. Both unhandled directions withhold a bin
        /// rather than invent one (#276).</summary>
        internal static bool RoomExitGapIsMeasurable(bool gameActive, bool gameEnded)
        {
            return gameActive && !gameEnded;
        }

        private static void AddToBins(ref Bins bins, int measured)
        {
            if (measured >= Gap300Ms) bins.Gap300++;
            if (measured >= Gap750Ms) bins.Gap750++;
            if (measured >= Gap1500Ms) bins.Gap1500++;
            if (measured > bins.MaxArrivalGapMs) bins.MaxArrivalGapMs = measured;
        }
    }
}
