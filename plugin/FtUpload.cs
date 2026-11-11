#if SCR_FRAMETIME
using System.Collections.Generic;
using System.Text;
using System.Threading;

namespace CompetitiveRounds
{
    /// <summary>FrameTime part b (FORMAT-M-PLAN.md V2 section 3), uploads: in this variant nothing the
    /// sitting builds leaves the seat, then or at any later launch, and no pending file changes. Each
    /// path is closed by a branch that exists only in this variant: the seat-evidence queue (Enqueue
    /// returns as on success without loading or saving), the closing files (SpoolClosing likewise,
    /// without writing), the pump and the queue's Load, the report outbox (EnqueueFailedReport,
    /// LoadOutbox, PersistOutbox, OutboxTick), chat (ChatClient.Connect) and every request the route
    /// classifier refuses. Closed is a property, not a constant, so the original code after each
    /// branch stays reachable to the compiler and the warning count stays Release's.
    /// Each refusal is counted per what and route. Refuse logs every refusal with the pair's running
    /// count (these paths are rare); RefuseQuiet, for the route classifier's frequent polls, logs only
    /// the first of each pair. Every pair's count is logged at each game over and at quit (VR6).</summary>
    internal static class FtUpload
    {
        internal static bool Closed => true;

        private static readonly Dictionary<string, long> _counts = new Dictionary<string, long>();

        internal static void Refuse(string what, string route)
        {
            long n = Count(what, route);
            Plugin.Log.LogInfo("[FRAME-TIME] refused what=" + what + " route=" + (route ?? "-") + " n=" + n);
        }

        internal static void RefuseQuiet(string what, string route)
        {
            if (Count(what, route) == 1)
                Plugin.Log.LogInfo("[FRAME-TIME] refused what=" + what + " route=" + (route ?? "-") + " n=1");
        }

        internal static long Count(string what, string route)
        {
            string k = what + ":" + (route ?? "-");
            lock (_counts)
            {
                long n;
                _counts.TryGetValue(k, out n);
                _counts[k] = n + 1;
                return n + 1;
            }
        }

        internal static void LogCounts(string why)
        {
            var sb = new StringBuilder(200);
            sb.Append("[FRAME-TIME] refusals why=").Append(why).Append(" pairs=").Append(_counts.Count);
            lock (_counts) foreach (var kv in _counts) sb.Append(' ').Append(kv.Key).Append('=').Append(kv.Value);
            Plugin.Log.LogInfo(sb.ToString());
        }
    }

    /// <summary>The writer ledger (ruling R6-A3.11.136 (2)(a); method-v54.md:33-48; B11 SHARED.md D5): tokens and service
    /// cost for every scope that runs collector-originated work off the main thread in format M. FtUpload's queues are
    /// closed in this variant (FtUpload above), so two scopes remain:
    ///
    /// LOG, BepInEx's disk log (BepInEx 5.4.19 DiskLogListener): LogEvent writes each line into LogWriter on the
    /// logging thread, and a thread-pool timer (FlushTimer, every 2 s) flushes LogWriter to the file. Install wraps
    /// LogWriter (Tap). A line written on the main thread while a collector scope is open (FtSpan.CollectorOpen) is a
    /// token: it is enqueued in the arm of the window it was written in (the gate then), its write into the buffer
    /// runs as a W scope (FtSpan.PushWriter), and it is done at the next Flush, on whatever thread, in the arm of the
    /// window open then; the flush's own executed cycles (FtClock.Cycles on the flushing thread) are its service.
    /// A flush serves every buffered line, so its cycles overstate the collector lines' share.
    ///
    /// HASH, SeatEvidence's identity hash (SeatEvidence.HashPending on its own thread): FtHeavy.HashT0 and HashT1,
    /// which the hash thread stamps at its start and end, are polled at every frame boundary (PollHash): the job is
    /// enqueued when HashT0 is first seen and done when HashT1 is. Its executed cycles are not readable here (its
    /// thread is not the caller's), so its wu cycles print NA.
    ///
    /// Counters are cumulative and taken under one lock (Take), so a window's tok always reconciles:
    /// open0 + enqON + enqOFF = doneON + doneOFF + disc + open1. No scope discards (disc 0).</summary>
    internal static class FtLedger
    {
        internal const int Log = 0, Hash = 1, Types = 2;
        internal static readonly string[] TypeNames = { "log", "hash" };
        private static readonly bool[] CyclesKnown = { true, false };

        /// <summary>Take's layout: enqON, enqOFF, doneON, doneOFF, disc, then per type its units and cycles done.</summary>
        internal const int EnqOn = 0, EnqOff = 1, DoneOn = 2, DoneOff = 3, Disc = 4, Fields = 5 + 2 * Types;

        private static readonly long[] _c = new long[Fields];
        private static readonly object _lock = new object();
        private static long _pendingLog;
        private static bool _hashEnq, _hashDone;
        internal static bool LogTapped;

        internal static void Take(long[] into)
        {
            lock (_lock) System.Array.Copy(_c, into, Fields);
        }

        /// <summary>The inventory in a snapshot: enqueued, not yet done or discarded.</summary>
        internal static long Level(long[] s)
        {
            return s[EnqOn] + s[EnqOff] - s[DoneOn] - s[DoneOff] - s[Disc];
        }

        /// <summary>wu=type:units:cycles;... from two snapshots (cycles NA where the scope's cycles are not read).</summary>
        internal static void AppendWu(StringBuilder sb, long[] a, long[] b)
        {
            for (int t = 0; t < Types; t++)
            {
                if (t > 0) sb.Append(';');
                sb.Append(TypeNames[t]).Append(':').Append(b[5 + 2 * t] - a[5 + 2 * t]).Append(':');
                if (CyclesKnown[t]) sb.Append(b[6 + 2 * t] - a[6 + 2 * t]); else sb.Append("NA");
            }
        }

        /// <summary>tok=open0,enqON,enqOFF,doneON,doneOFF,disc,open1 from two snapshots.</summary>
        internal static void AppendTok(StringBuilder sb, long[] a, long[] b)
        {
            sb.Append(Level(a)).Append(',').Append(b[EnqOn] - a[EnqOn]).Append(',').Append(b[EnqOff] - a[EnqOff])
              .Append(',').Append(b[DoneOn] - a[DoneOn]).Append(',').Append(b[DoneOff] - a[DoneOff])
              .Append(',').Append(b[Disc] - a[Disc]).Append(',').Append(Level(b));
        }

        /// <summary>FtClock.Install: wraps the disk log's writer. Logged either way.</summary>
        internal static void Install()
        {
            string why = "no_disk_listener";
            try
            {
                foreach (var l in BepInEx.Logging.Logger.Listeners)
                {
                    var d = l as BepInEx.Logging.DiskLogListener;
                    if (d == null) continue;
                    if (d.LogWriter is Tap) { why = "already"; break; }
                    var set = typeof(BepInEx.Logging.DiskLogListener).GetProperty("LogWriter").GetSetMethod(true);
                    set.Invoke(d, new object[] { new Tap(d.LogWriter) });
                    LogTapped = true;
                    why = "ok";
                    break;
                }
            }
            catch (System.Exception ex) { why = "failed:" + ex.GetType().Name; }
            Plugin.Log.LogInfo("[FRAME-TIME] ledger log=" + (LogTapped ? 1 : 0) + " why=" + why + " hash=poll");
        }

        /// <summary>FtClock.OnStart, every frame boundary: the hash job's tokens from the hash thread's stamps.</summary>
        internal static void PollHash()
        {
            if (!_hashEnq && Interlocked.Read(ref FtHeavy.HashT0) != 0)
            {
                _hashEnq = true;
                lock (_lock) _c[FtGate.Off ? EnqOff : EnqOn]++;
            }
            if (_hashEnq && !_hashDone && Interlocked.Read(ref FtHeavy.HashT1) != 0)
            {
                _hashDone = true;
                lock (_lock) { _c[FtGate.Off ? DoneOff : DoneOn]++; _c[5 + 2 * Hash]++; }
            }
        }

        private sealed class Tap : System.IO.TextWriter
        {
            private readonly System.IO.TextWriter _in;

            internal Tap(System.IO.TextWriter inner) { _in = inner; }

            public override Encoding Encoding => _in.Encoding;
            public override void Write(char value) { _in.Write(value); }
            public override void Write(string value) { _in.Write(value); }
            public override void Write(char[] buffer, int index, int count) { _in.Write(buffer, index, count); }
            public override void WriteLine() { _in.WriteLine(); }

            public override void WriteLine(string value)
            {
                if (Thread.CurrentThread.ManagedThreadId != FtSpan.MainThread || !FtSpan.CollectorOpen)
                {
                    _in.WriteLine(value);
                    return;
                }
                FtSpan.PushWriter();
                try { _in.WriteLine(value); }
                finally { FtSpan.PopWriter(); }
                // counted after the write, so a concurrent flush can never mark done a line not yet in the buffer
                lock (_lock) { _c[FtGate.Off ? EnqOff : EnqOn]++; _pendingLog++; }
            }

            public override void Flush()
            {
                ulong k0 = FtClock.Cycles();
                _in.Flush();
                ulong k1 = FtClock.Cycles();
                lock (_lock)
                {
                    long n = _pendingLog;
                    _pendingLog = 0;
                    _c[FtGate.Off ? DoneOff : DoneOn] += n;
                    _c[5 + 2 * Log] += n;
                    _c[6 + 2 * Log] += unchecked((long)(k1 - k0));
                }
            }

            protected override void Dispose(bool disposing)
            {
                if (disposing) _in.Dispose();
                base.Dispose(disposing);
            }
        }
    }
}
#endif
