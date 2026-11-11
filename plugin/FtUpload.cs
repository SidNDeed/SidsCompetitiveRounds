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
    /// cost per writer type, for every scope that runs collector-originated work off the main thread in format M and
    /// for the receive handlers of the peer's collector traffic. FtUpload's queues are closed in this variant
    /// (FtUpload above). Three types, keyed in wu and tok by TypeNames:
    ///
    /// log: BepInEx's disk log (BepInEx 5.4.19 DiskLogListener). LogEvent writes each line into LogWriter on the
    /// logging thread, and a thread-pool timer (FlushTimer, every 2 s) flushes LogWriter to the file. Install wraps
    /// LogWriter (Tap). A line written on the main thread while a collector scope is open (FtSpan.CollectorOpen) is a
    /// token: it is enqueued in the arm of the window it was written in, its write into the buffer runs as a W scope
    /// (FtSpan.PushWriter), and it is done at the next Flush, on whatever thread, in the arm of the window open then.
    /// The flush's own executed cycles (FtClock.Cycles on the flushing thread) are charged whole to the tokens it
    /// carries. A flush serves every buffered line, so this overstates the collector lines' share.
    ///
    /// hash: SeatEvidence's identity hash. SeatEvidence.HashPending runs its jobs (the mod's DLL, then the game's) on
    /// the thread StartHashing starts, or on the main thread on the quitting path (CompleteIdentityNow). Each job is
    /// enqueued as it starts and done as it ends (HashBegin, HashEnd), and its cycles are read on the thread that runs
    /// it (FtClock.Cycles reads the calling thread's counter). A job that throws is discarded, its cycles still counted.
    ///
    /// recv: the receive handlers of the peer's collector traffic, SeatEvidence.EnterRpc (each inbound RPC's
    /// envelope, from PhotonNetwork.ExecuteRpc) and PeerBuild's per-seat read of a peer's cr_build (PeerBuild.Tick).
    /// Each message handled is one unit and one token, enqueued at the handler's entry and done at its exit; its
    /// cycles are the handler's own, on its thread. SeatEvidence.ExitRpc adds its cycles with no unit. RecvOffMain
    /// counts handler entries off the main thread. On the main thread these cycles are already inside the frame's C;
    /// recv names them, it adds nothing to C.
    ///
    /// Counters are cumulative and taken under one lock (Take), so every type's tok reconciles in every window:
    /// open0 + enqON + enqOFF = doneON + doneOFF + disc + open1. An event's arm is FtGate.Off when it happens. Take
    /// also carries FtSpan.Marks, the window's nm.</summary>
    internal static class FtLedger
    {
        internal const int Log = 0, Hash = 1, Recv = 2, Types = 3;
        internal static readonly string[] TypeNames = { "log", "hash", "recv" };

        /// <summary>Per type t, at t * Per: enqON, enqOFF, doneON, doneOFF, disc, units, cycles. Then FtSpan.Marks.</summary>
        internal const int EnqOn = 0, EnqOff = 1, DoneOn = 2, DoneOff = 3, Disc = 4, Units = 5, Cyc = 6, Per = 7;
        internal const int Nm = Types * Per, Fields = Nm + 1;

        private static readonly long[] _c = new long[Nm];
        private static readonly object _lock = new object();
        private static long _pendingLog;
        internal static bool LogTapped;
        internal static long RecvOffMain;   // recv handler entries off the main thread
        internal static long CycleMiss;     // a scope whose cycle read failed (its cycles are counted as 0)

        /// <summary>Main thread (FtFrames).</summary>
        internal static void Take(long[] into)
        {
            lock (_lock) System.Array.Copy(_c, into, Nm);
            into[Nm] = FtSpan.Marks;
        }

        /// <summary>Type t's inventory in a snapshot: enqueued, not yet done or discarded.</summary>
        internal static long Level(long[] s, int t)
        {
            int b = t * Per;
            return s[b + EnqOn] + s[b + EnqOff] - s[b + DoneOn] - s[b + DoneOff] - s[b + Disc];
        }

        /// <summary>wu=type:units:cycles;... from two snapshots.</summary>
        internal static void AppendWu(StringBuilder sb, long[] a, long[] b)
        {
            for (int t = 0; t < Types; t++)
            {
                int o = t * Per;
                if (t > 0) sb.Append(';');
                sb.Append(TypeNames[t]).Append(':').Append(b[o + Units] - a[o + Units]).Append(':').Append(b[o + Cyc] - a[o + Cyc]);
            }
        }

        /// <summary>tok=type:open0,enqON,enqOFF,doneON,doneOFF,disc,open1;... from two snapshots.</summary>
        internal static void AppendTok(StringBuilder sb, long[] a, long[] b)
        {
            for (int t = 0; t < Types; t++)
            {
                int o = t * Per;
                if (t > 0) sb.Append(';');
                sb.Append(TypeNames[t]).Append(':').Append(Level(a, t))
                  .Append(',').Append(b[o + EnqOn] - a[o + EnqOn]).Append(',').Append(b[o + EnqOff] - a[o + EnqOff])
                  .Append(',').Append(b[o + DoneOn] - a[o + DoneOn]).Append(',').Append(b[o + DoneOff] - a[o + DoneOff])
                  .Append(',').Append(b[o + Disc] - a[o + Disc]).Append(',').Append(Level(b, t));
            }
        }

        /// <summary>nm: the window's class transitions.</summary>
        internal static long Marks(long[] a, long[] b) { return b[Nm] - a[Nm]; }

        private static void Enq(int t, long n)
        {
            lock (_lock) _c[t * Per + (FtGate.Off ? EnqOff : EnqOn)] += n;
        }

        /// <summary>n tokens served (done, or discarded when !ok), with their units and the cycles between two reads.</summary>
        private static void Serve(int t, long n, bool ok, ulong k0, ulong k1)
        {
            long c = 0;
            if (k0 == 0 || k1 == 0) Interlocked.Increment(ref CycleMiss); else c = unchecked((long)(k1 - k0));
            lock (_lock)
            {
                int o = t * Per;
                if (ok) { _c[o + (FtGate.Off ? DoneOff : DoneOn)] += n; _c[o + Units] += n; }
                else _c[o + Disc] += n;
                _c[o + Cyc] += c;
            }
        }

        /// <summary>SeatEvidence.HashPending, on the thread that runs the job: one job starts.</summary>
        internal static ulong HashBegin()
        {
            Enq(Hash, 1);
            return FtClock.Cycles();
        }

        /// <summary>The job started by HashBegin ended: done when ok, discarded when it threw.</summary>
        internal static void HashEnd(ulong k0, bool ok)
        {
            Serve(Hash, 1, ok, k0, FtClock.Cycles());
        }

        /// <summary>A recv handler's entry, on its thread: one message.</summary>
        internal static ulong RecvEnter()
        {
            if (Thread.CurrentThread.ManagedThreadId != FtSpan.MainThread) Interlocked.Increment(ref RecvOffMain);
            Enq(Recv, 1);
            return FtClock.Cycles();
        }

        /// <summary>The handler entered by RecvEnter exits (finally): the message is done.</summary>
        internal static void RecvExit(ulong k0)
        {
            Serve(Recv, 1, true, k0, FtClock.Cycles());
        }

        /// <summary>Recv work with no message of its own (SeatEvidence.ExitRpc): cycles only.</summary>
        internal static void RecvCycles(ulong k0)
        {
            Serve(Recv, 0, true, k0, FtClock.Cycles());
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
            Plugin.Log.LogInfo("[FRAME-TIME] ledger log=" + (LogTapped ? 1 : 0) + " why=" + why + " types=" + string.Join(",", TypeNames));
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
                lock (_lock) { _c[Log * Per + (FtGate.Off ? EnqOff : EnqOn)]++; _pendingLog++; }
            }

            public override void Flush()
            {
                ulong k0 = FtClock.Cycles();
                _in.Flush();
                ulong k1 = FtClock.Cycles();
                long n;
                lock (_lock) { n = _pendingLog; _pendingLog = 0; }
                // the whole flush is charged to the lines it carries (ruled conservative, SHARED.md D5); a flush that
                // carries none charges nothing
                if (n > 0) Serve(Log, n, true, k0, k1);
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
