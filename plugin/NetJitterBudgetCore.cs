// Night 2026-10-19 calibration lane: the NET-JITTER per-room line budget with
// a reserve for the large gaps, and the room-end top-3. Pure (no Unity, Photon
// or Harmony type), so the DSN-free control in tools/tests/net-stall-detect
// compiles and drives this exact file.
using System;
using System.Globalization;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// The night of 2026-10-19 spent all 16 [NET-JITTER] lines of a room on
    /// routine 300 to 380 ms gaps, so the 6 s stall that followed was never
    /// logged by its own line. Of the 16 lines, RESERVE are now held for gaps
    /// above BIG_GAP_MS (a routine gap may take only TOTAL - RESERVE), and the
    /// room summary names the TOP largest qualifying gaps whatever the budget
    /// did. A big gap may also use any routine slot still free.
    /// </summary>
    internal sealed class NetJitterBudgetCore
    {
        internal const int TOTAL = 16;
        internal const int RESERVE = 4;
        internal const int BIG_GAP_MS = 1000;
        internal const int TOP = 3;

        // Two pools: TOTAL - RESERVE routine slots, RESERVE big-gap slots. A
        // big gap takes the reserve first, then any routine slot still free.
        private int _routineUsed, _reserveUsed;
        private long _qualifying, _suppressed;

        private struct Gap { public int Actor, ArrivalMs, SenderMs, ExcessMs, Game; }
        private readonly Gap[] _top = new Gap[TOP];
        private int _topN;

        /// <summary>True once no qualifying gap can take a line any more (both
        /// the routine share and the reserve are spent): the caller's latch.</summary>
        internal bool Spent { get { return _routineUsed >= TOTAL - RESERVE && _reserveUsed >= RESERVE; } }

        /// <summary>Lines written this room, both pools.</summary>
        internal int Used { get { return _routineUsed + _reserveUsed; } }

        /// <summary>One qualifying sample (the caller has already applied the
        /// arrival and excess thresholds). Records it for the top list and
        /// returns whether it may write its line; isReserve tells the caller
        /// the line took a reserved slot.</summary>
        internal bool Offer(int actor, int arrivalMs, int senderMs, int excessMs, int game, out bool isReserve)
        {
            isReserve = false;
            _qualifying++;
            NoteTop(actor, arrivalMs, senderMs, excessMs, game);
            bool big = arrivalMs > BIG_GAP_MS;
            if (big && _reserveUsed < RESERVE) { _reserveUsed++; isReserve = true; return true; }
            if (_routineUsed < TOTAL - RESERVE) { _routineUsed++; return true; }
            _suppressed++;
            return false;
        }

        private void NoteTop(int actor, int arrivalMs, int senderMs, int excessMs, int game)
        {
            int pos = _topN;
            while (pos > 0 && _top[pos - 1].ArrivalMs < arrivalMs) pos--;
            if (pos >= TOP) return;
            int last = Math.Min(_topN, TOP - 1);
            for (int i = last; i > pos; i--) _top[i] = _top[i - 1];
            _top[pos] = new Gap { Actor = actor, ArrivalMs = arrivalMs, SenderMs = senderMs, ExcessMs = excessMs, Game = game };
            if (_topN < TOP) _topN++;
        }

        /// <summary>The room-summary fields: lines used of TOTAL, qualifying
        /// gaps, suppressed lines, and the TOP largest qualifying gaps as
        /// aACTOR:ARRIVALms/sSENDER/xEXCESS/gGAME, largest first.</summary>
        internal string SummaryFields()
        {
            var sb = new StringBuilder(160);
            sb.Append(" jitterLines=").Append(Used.ToString(CultureInfo.InvariantCulture)).Append('/').Append(TOTAL.ToString(CultureInfo.InvariantCulture))
              .Append(" jitterQualifying=").Append(_qualifying.ToString(CultureInfo.InvariantCulture))
              .Append(" jitterSuppressed=").Append(_suppressed.ToString(CultureInfo.InvariantCulture))
              .Append(" jitterTop=");
            if (_topN == 0) sb.Append("none");
            for (int i = 0; i < _topN; i++)
            {
                if (i > 0) sb.Append(';');
                sb.Append('a').Append(_top[i].Actor.ToString(CultureInfo.InvariantCulture))
                  .Append(':').Append(_top[i].ArrivalMs.ToString(CultureInfo.InvariantCulture)).Append("ms")
                  .Append("/s").Append(_top[i].SenderMs.ToString(CultureInfo.InvariantCulture))
                  .Append("/x").Append(_top[i].ExcessMs.ToString(CultureInfo.InvariantCulture))
                  .Append("/g").Append(_top[i].Game.ToString(CultureInfo.InvariantCulture));
            }
            return sb.ToString();
        }

        /// <summary>The line budget only (a same-room re-join edge that keeps
        /// the room's measurements).</summary>
        internal void ResetLines() { _routineUsed = 0; _reserveUsed = 0; }

        internal void ResetRoom()
        {
            _routineUsed = 0; _reserveUsed = 0; _qualifying = 0; _suppressed = 0; _topN = 0;
            Array.Clear(_top, 0, _top.Length);
        }
    }
}
