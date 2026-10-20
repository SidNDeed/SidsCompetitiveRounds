// Night 2026-10-19 calibration lane: the receiver-side inbound stall detector.
// Pure (no Unity, Photon or Harmony type), so the DSN-free control in
// tools/tests/net-stall-detect compiles and drives this exact file.
using System;
using System.Globalization;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// A receiver-side stall whose socket keeps receiving: commands arrive and
    /// sit in this seat's inbound queue (the raw socket queue plus the channel
    /// lists, sampled before every Dispatch drain by
    /// NetworkSeatTelemetry.NoteInboundDepth) while the frames stay normal, so
    /// the hold is not this seat's main thread. Every silence detector in the
    /// mod needs the socket to go quiet first, and one held reliable command
    /// keeps the socket busy while it holds everything behind it; this one
    /// reads the queue instead.
    ///
    /// The bound: the night of 2026-10-19 measured the per-window MAXIMUM of
    /// the sampled depth over 4645 one-second windows of five seats: under 10
    /// in 88.7 percent, under 20 in 96.8, under 30 in 98.0, 48 to 99 in 43
    /// single windows (spikes up to 78 that drained by the next window), and
    /// over 99 only inside the one 6 s stall (62, 108, 157, 199 in four
    /// consecutive windows). A depth above QUEUE_BOUND that is still above it
    /// MIN_STALL_MS later is not a spike: the routine spikes drain within one
    /// Dispatch, and a second of growth at the stall's rate (about 47 commands
    /// a second with two remote fighters) is what crosses the bound from the
    /// ordinary range.
    ///
    /// What the line says and what it does not: the depth stayed above the
    /// bound for durMs while this seat's frames stayed under FRAME_OK_MS, and
    /// the named remote streams delivered no accepted batch in that span. It
    /// never names a leg (learning 446): a held reliable command, a slow
    /// downlink and a relay burst read the same here.
    ///
    /// Cost: the hot path is one unsigned range comparison on a depth the
    /// telemetry already samples; only leaving the current depth band runs
    /// the slow path (and permits the caller to read its clock).
    /// </summary>
    internal sealed class InboundStallCore
    {
        internal const int QUEUE_BOUND = 48;
        internal const int LOW_MARK = 24;          // QUEUE_BOUND / 2: the rise is timed from the last sample at or below it
        internal const long MIN_STALL_MS = 1000;
        internal const int FRAME_OK_MS = 50;
        internal const int MAX_LINES_PER_ROOM = 8;
        internal const int MAX_STREAMS = 16;

        // Inclusive bands: 0..24 quiet, 25..48 rising, 49..peak open.
        // An unsigned offset comparison catches either edge in one test.
        private int _bandFloor;
        private uint _bandWidth = LOW_MARK;

        private bool _rising;
        private long _riseStartMs;
        private bool _open;
        private long _openMs;
        private int _peak;
        private int _frames;
        private int _worstFrameMs;
        private readonly int[] _openActors = new int[MAX_STREAMS];
        private readonly long[] _openBatches = new long[MAX_STREAMS];
        private int _openStreams;

        // Per game (the NET-SEAT summary) and per room (the line budget).
        internal int GameStalls { get; private set; }
        internal long GameLongestMs { get; private set; }
        internal int GameFrameExcluded { get; private set; }
        private int _roomLines;
        internal int GameSuppressed { get; private set; }

        /// <summary>The remote stream snapshot the caller hands the core: the
        /// actor numbers and their cumulative accepted batch counts, n valid
        /// entries. Filled by NetworkReplicaDiagnostics in the plugin and by
        /// the control in the harness.</summary>
        internal delegate int StreamSnapshot(int[] actors, long[] batches);

        /// <summary>The quiet-path test the plugin makes before it reads a
        /// clock: false for every sample inside the current band.</summary>
        internal bool Wants(int depth) { return unchecked((uint)(depth - _bandFloor)) > _bandWidth; }

        /// <summary>One depth sample. Returns the [NET-STALL] line to write
        /// when a stall closed with this sample, else null.</summary>
        internal string OnDepth(int depth, long nowMs, StreamSnapshot snap, int game, int terminalFrameMs = 0)
        {
            if (unchecked((uint)(depth - _bandFloor)) <= _bandWidth) return null;
            return Slow(depth, nowMs, snap, game, terminalFrameMs);
        }

        private string Slow(int depth, long nowMs, StreamSnapshot snap, int game, int terminalFrameMs)
        {
            string line = null;
            if (depth <= LOW_MARK)
            {
                if (_open) line = Close(nowMs, snap, game, false, terminalFrameMs);
                _rising = false;
                _bandFloor = 0; _bandWidth = LOW_MARK;
                return line;
            }
            if (!_rising) { _rising = true; _riseStartMs = nowMs; }
            _bandFloor = LOW_MARK + 1; _bandWidth = QUEUE_BOUND - LOW_MARK - 1;
            if (depth > QUEUE_BOUND)
            {
                if (!_open)
                {
                    _open = true;
                    _openMs = nowMs;
                    _peak = depth;
                    _frames = 0;
                    _worstFrameMs = 0;
                    _openStreams = 0;
                    try { if (snap != null) _openStreams = Math.Min(MAX_STREAMS, Math.Max(0, snap(_openActors, _openBatches))); } catch { _openStreams = 0; }
                }
                else if (depth > _peak) _peak = depth;
                _bandFloor = QUEUE_BOUND + 1; _bandWidth = (uint)(_peak - _bandFloor);
            }
            else if (_open)
            {
                line = Close(nowMs, snap, game, false, terminalFrameMs);
            }
            return line;
        }

        /// <summary>One frame wall gap, from the telemetry's per-frame tick.
        /// Only counted while a stall is open (a boolean on the quiet path).</summary>
        internal void OnFrame(int frameMs)
        {
            if (!_open) return;
            _frames++;
            if (frameMs > _worstFrameMs) _worstFrameMs = frameMs;
        }

        internal bool Open { get { return _open; } }

        /// <summary>Game end or room exit: a stall still open is closed here,
        /// marked open=1 (it had no drain to end it).</summary>
        internal string Flush(long nowMs, StreamSnapshot snap, int game, int terminalFrameMs = 0)
        {
            string line = _open ? Close(nowMs, snap, game, true, terminalFrameMs) : null;
            _rising = false;
            _bandFloor = 0; _bandWidth = LOW_MARK;
            return line;
        }

        private readonly int[] _closeActors = new int[MAX_STREAMS];
        private readonly long[] _closeBatches = new long[MAX_STREAMS];

        private string Close(long nowMs, StreamSnapshot snap, int game, bool openAtEnd, int terminalFrameMs)
        {
            _open = false;
            long dur = nowMs - _openMs;
            if (dur <= MIN_STALL_MS) return null;
            // The closing RPC can precede Update. Observe its pending wall
            // gap without counting another completed frame.
            if (terminalFrameMs > _worstFrameMs) _worstFrameMs = terminalFrameMs;
            if (_worstFrameMs >= FRAME_OK_MS)
            {
                // This seat's own frames covered the hold: a local hitch, not
                // a network stall. Counted, never logged as one.
                GameFrameExcluded++;
                return null;
            }
            GameStalls++;
            if (dur > GameLongestMs) GameLongestMs = dur;
            int streams = 0, stopped = 0;
            try
            {
                int n = snap != null ? Math.Min(MAX_STREAMS, Math.Max(0, snap(_closeActors, _closeBatches))) : 0;
                for (int i = 0; i < _openStreams; i++)
                {
                    streams++;
                    bool advanced = false;
                    for (int j = 0; j < n; j++)
                        if (_closeActors[j] == _openActors[i]) { advanced = _closeBatches[j] > _openBatches[i]; break; }
                    if (!advanced) stopped++;
                }
            }
            catch { }
            if (_roomLines >= MAX_LINES_PER_ROOM) { GameSuppressed++; return null; }
            _roomLines++;
            var sb = new StringBuilder(200);
            sb.Append("[NET-STALL] game=").Append(game.ToString(CultureInfo.InvariantCulture))
              .Append(" n=").Append(GameStalls.ToString(CultureInfo.InvariantCulture))
              .Append(" durMs=").Append(dur.ToString(CultureInfo.InvariantCulture))
              .Append(" riseMs=").Append((nowMs - _riseStartMs).ToString(CultureInfo.InvariantCulture))
              .Append(" peakQ=").Append(_peak.ToString(CultureInfo.InvariantCulture))
              .Append(" frames=").Append(_frames.ToString(CultureInfo.InvariantCulture))
              .Append(" worstFrameMs=").Append(_worstFrameMs.ToString(CultureInfo.InvariantCulture))
              .Append(" remoteStreams=").Append(streams.ToString(CultureInfo.InvariantCulture))
              .Append(" stopped=").Append(stopped.ToString(CultureInfo.InvariantCulture))
              .Append(" bound=").Append(QUEUE_BOUND.ToString(CultureInfo.InvariantCulture))
              .Append(" open=").Append(openAtEnd ? "1" : "0")
              .Append(" (durMs = depth above bound; riseMs = from the last depth at or below ")
              .Append(LOW_MARK.ToString(CultureInfo.InvariantCulture)).Append("; leg undetermined)");
            return sb.ToString();
        }

        /// <summary>The NET-SEAT game summary fields.</summary>
        internal string SummaryFields()
        {
            return " stalls=" + GameStalls.ToString(CultureInfo.InvariantCulture)
                + " longestStallMs=" + GameLongestMs.ToString(CultureInfo.InvariantCulture)
                + " stallsFrameExcluded=" + GameFrameExcluded.ToString(CultureInfo.InvariantCulture)
                + " stallLinesSuppressed=" + GameSuppressed.ToString(CultureInfo.InvariantCulture);
        }

        internal void ResetGame()
        {
            GameStalls = 0; GameLongestMs = 0; GameFrameExcluded = 0;
            GameSuppressed = 0;
            _open = false; _rising = false; _bandFloor = 0; _bandWidth = LOW_MARK;
        }

        internal void ResetRoom()
        {
            ResetGame();
            _roomLines = 0;
        }
    }
}
