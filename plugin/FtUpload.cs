#if SCR_FRAMETIME
using System.Collections.Generic;
using System.Reflection;
using System.Text;
using System.Threading;
using HarmonyLib;

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
    /// cycles are the handler's own, on its thread. SeatEvidence.ExitRpc adds its cycles with no unit
    /// (RecvCyclesEnter, RecvCycles). RecvOffMain counts handler entries off the main thread. On the main thread these
    /// cycles are already inside the frame's C; recv names them, it adds nothing to C. V6 (rulings R6-A3.11.146 and
    /// .147): each recv scope on the main thread is also a class-P scope (FtSpan.EnterP, LeaveP), so its cycles and
    /// bytes are the window line's cP and aP.
    ///
    /// sock: Photon's socket receive thread, one datagram per IPhotonSocket.HandleReceivedDatagram call (FtSockPatch
    /// below). Each datagram is one unit and one token; its producer's arm is not known here, so every sock token is
    /// enqueued ON (the conservative side), and done in the arm open when the call returns. Its cycles are the
    /// call's on its own thread. Per point the p line adds the datagrams' cycle distribution (SockStats). In the
    /// reference build the patch is absent and sock's wu prints NA.
    ///
    /// Counters are cumulative and taken under one lock (Take), so every type's tok reconciles in every window:
    /// open0 + enqON + enqOFF = doneON + doneOFF + disc + open1. An event's arm is FtGate.Off when it happens. Take
    /// also carries FtSpan.Marks, the window's nm.
    ///
    /// wa (V6): the allocation counter (FtAlloc) is read where each off-thread scope reads its cycles, so a log flush, a
    /// hash job and a datagram also carry the bytes allocated between their two reads. The counter is the process's,
    /// so those bytes include what other threads allocated in that time (the wider cap, accepted by ruling .147
    /// (3)(g)). recv's bytes are class P's on the main thread (aP), not wa's.</summary>
    internal static class FtLedger
    {
        internal const int Log = 0, Hash = 1, Recv = 2, Sock = 3, Types = 4;
        internal static readonly string[] TypeNames = { "log", "hash", "recv", "sock" };

        /// <summary>The writer types wa prints, in order: the off-thread scopes.</summary>
        internal static readonly int[] WaTypes = { Log, Hash, Sock };

        /// <summary>Per type t, at t * Per: enqON, enqOFF, doneON, doneOFF, disc, units, cycles, bytes. Then
        /// FtSpan.Marks.</summary>
        internal const int EnqOn = 0, EnqOff = 1, DoneOn = 2, DoneOff = 3, Disc = 4, Units = 5, Cyc = 6, Al = 7, Per = 8;
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
#if SCR_FT_NOCOLLECTORS
                if (t == Sock) { sb.Append(TypeNames[t]).Append(":NA:NA"); continue; }
#endif
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

        /// <summary>wa=type:bytes;... over WaTypes from two snapshots; every value NA when the counter is not (ok).</summary>
        internal static void AppendWa(StringBuilder sb, long[] a, long[] b, bool ok)
        {
            for (int i = 0; i < WaTypes.Length; i++)
            {
                int t = WaTypes[i], o = t * Per;
                if (i > 0) sb.Append(';');
                sb.Append(TypeNames[t]).Append(':');
#if SCR_FT_NOCOLLECTORS
                if (t == Sock) { sb.Append("NA"); continue; }
#endif
                if (ok) sb.Append(b[o + Al] - a[o + Al]); else sb.Append("NA");
            }
        }

        /// <summary>nm: the window's class transitions.</summary>
        internal static long Marks(long[] a, long[] b) { return b[Nm] - a[Nm]; }

        private static void Enq(int t, long n)
        {
            lock (_lock) _c[t * Per + (FtGate.Off ? EnqOff : EnqOn)] += n;
        }

        /// <summary>n tokens served (done, or discarded when !ok), with their units, the cycles between two reads and,
        /// when both counter reads stood (aok), the bytes between them.</summary>
        private static void Serve(int t, long n, bool ok, ulong k0, ulong k1, long a0, long a1, bool aok)
        {
            long c = 0;
            if (k0 == 0 || k1 == 0) Interlocked.Increment(ref CycleMiss); else c = unchecked((long)(k1 - k0));
            long al = aok ? FtAlloc.Delta(a0, a1) : 0;
            lock (_lock)
            {
                int o = t * Per;
                if (ok) { _c[o + (FtGate.Off ? DoneOff : DoneOn)] += n; _c[o + Units] += n; }
                else _c[o + Disc] += n;
                _c[o + Cyc] += c;
                _c[o + Al] += al;
            }
        }

        // the counter's reading at the start of the calling thread's open hash job or datagram (each thread runs one at a
        // time: the hash thread its jobs in turn, a receive thread its datagrams)
        [System.ThreadStatic] private static long _aHash, _aSock;
        [System.ThreadStatic] private static bool _aHashOk, _aSockOk;

        /// <summary>SeatEvidence.HashPending, on the thread that runs the job: one job starts.</summary>
        internal static ulong HashBegin()
        {
            Enq(Hash, 1);
            _aHashOk = FtAlloc.Read(out _aHash);
            return FtClock.Cycles();
        }

        /// <summary>The job started by HashBegin ended: done when ok, discarded when it threw.</summary>
        internal static void HashEnd(ulong k0, bool ok)
        {
            ulong k1 = FtClock.Cycles();
            long a1;
            bool aok = FtAlloc.Read(out a1) && _aHashOk;
            Serve(Hash, 1, ok, k0, k1, _aHash, a1, aok);
        }

        /// <summary>A recv handler's entry, on its thread: one message, and on the main thread a class-P scope.</summary>
        internal static ulong RecvEnter()
        {
            if (Thread.CurrentThread.ManagedThreadId != FtSpan.MainThread) Interlocked.Increment(ref RecvOffMain);
            Enq(Recv, 1);
            FtSpan.EnterP();
            return FtClock.Cycles();
        }

        /// <summary>The handler entered by RecvEnter exits (finally): the message is done, the P scope closed.</summary>
        internal static void RecvExit(ulong k0)
        {
            Serve(Recv, 1, true, k0, FtClock.Cycles(), 0, 0, false);
            FtSpan.LeaveP();
        }

        /// <summary>Recv work with no message of its own (SeatEvidence.ExitRpc) starts: a class-P scope on the main
        /// thread, and its start cycles. Pair with RecvCycles.</summary>
        internal static ulong RecvCyclesEnter()
        {
            FtSpan.EnterP();
            return FtClock.Cycles();
        }

        /// <summary>The work RecvCyclesEnter started ends: cycles only, the P scope closed.</summary>
        internal static void RecvCycles(ulong k0)
        {
            Serve(Recv, 0, true, k0, FtClock.Cycles(), 0, 0, false);
            FtSpan.LeaveP();
        }

        // -- sock: the receive thread's datagrams -----------------------------------------------------------------

        /// <summary>Cycle-per-datagram buckets: bucket i holds [SockEdge[i-1], SockEdge[i]), edges about 2^(1/4) apart
        /// up to 2^44; the last bucket is open above.</summary>
        internal const int SockBuckets = 177;
        internal static readonly long[] SockEdge = SockEdges();
        private static readonly long[] _sockHist = new long[SockBuckets];
        internal static long SockMain;       // datagram calls on the main thread
        internal static long SockSwitches;   // calls on a thread other than the previous call's
        private static int _sockThread = -1;

        /// <summary>SockTake's layout: the buckets, then SockMain, then SockSwitches.</summary>
        internal const int SockFields = SockBuckets + 2;

        private static long[] SockEdges()
        {
            var e = new long[SockBuckets - 1];
            long prev = 0;
            for (int i = 0; i < e.Length; i++)
            {
                long v = (long)System.Math.Ceiling(System.Math.Pow(2.0, (i + 1) / 4.0));
                e[i] = v > prev ? v : prev + 1;
                prev = e[i];
            }
            return e;
        }

        /// <summary>The bucket of c cycles: the first edge above c.</summary>
        internal static int SockBucket(long c)
        {
            int i = System.Array.BinarySearch(SockEdge, c);
            return i >= 0 ? i + 1 : ~i;
        }

        /// <summary>FtSockPatch's prefix, on the receive thread: one datagram enqueued (ON: its producer's arm is not
        /// known), its start cycles on this thread.</summary>
        internal static ulong SockEnter()
        {
            int id = Thread.CurrentThread.ManagedThreadId;
            if (id == FtSpan.MainThread) Interlocked.Increment(ref SockMain);
            if (id != _sockThread)
            {
                if (_sockThread != -1) Interlocked.Increment(ref SockSwitches);
                _sockThread = id;
            }
            lock (_lock) _c[Sock * Per + EnqOn]++;
            _aSockOk = FtAlloc.Read(out _aSock);
            return FtClock.Cycles();
        }

        /// <summary>FtSockPatch's finalizer, on the same thread: the datagram done, its cycles counted and bucketed.</summary>
        internal static void SockExit(ulong k0)
        {
            ulong k1 = FtClock.Cycles();
            long a1;
            bool aok = FtAlloc.Read(out a1) && _aSockOk;
            Serve(Sock, 1, true, k0, k1, _aSock, a1, aok);
            long c = k0 == 0 || k1 == 0 ? 0 : unchecked((long)(k1 - k0));
            Interlocked.Increment(ref _sockHist[SockBucket(c)]);
        }

        /// <summary>Main thread (FtFrames' point bounds): the cumulative buckets and thread counters.</summary>
        internal static void SockTake(long[] into)
        {
            for (int i = 0; i < SockBuckets; i++) into[i] = Interlocked.Read(ref _sockHist[i]);
            into[SockBuckets] = Interlocked.Read(ref SockMain);
            into[SockBuckets + 1] = Interlocked.Read(ref SockSwitches);
        }

        /// <summary>The p line's sock fields between two SockTake snapshots: sock_p95, the upper edge of the bucket
        /// holding the nearest-rank 95th percentile of cycles per datagram (an upper bound; NA with no datagram, or
        /// when it falls in the open last bucket), sock_n the datagrams, sock_thr the thread switches, sock_main the
        /// calls on the main thread.</summary>
        internal static string SockStats(long[] a, long[] b)
        {
            long n = 0;
            for (int i = 0; i < SockBuckets; i++) n += b[i] - a[i];
            string p95 = "NA";
            if (n > 0)
            {
                long rank = (95 * n + 99) / 100, cum = 0;
                for (int i = 0; i < SockBuckets; i++)
                {
                    cum += b[i] - a[i];
                    if (cum < rank) continue;
                    if (i < SockEdge.Length) p95 = SockEdge[i].ToString();
                    break;
                }
            }
            return "sock_p95=" + p95 + " sock_n=" + n + " sock_thr=" + (b[SockBuckets + 1] - a[SockBuckets + 1])
                + " sock_main=" + (b[SockBuckets] - a[SockBuckets]);
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
                long a0, a1;
                bool aok = FtAlloc.Read(out a0);
                ulong k0 = FtClock.Cycles();
                _in.Flush();
                ulong k1 = FtClock.Cycles();
                aok = FtAlloc.Read(out a1) && aok;
                long n;
                lock (_lock) { n = _pendingLog; _pendingLog = 0; }
                // the whole flush is charged to the lines it carries (ruled conservative, SHARED.md D5); a flush that
                // carries none charges nothing
                if (n > 0) Serve(Log, n, true, k0, k1, a0, a1, aok);
            }

            protected override void Dispose(bool disposing)
            {
                if (disposing) _in.Dispose();
                base.Dispose(disposing);
            }
        }
    }

#if !SCR_FT_NOCOLLECTORS
    /// <summary>FtLedger's sock scope (B11 SHARED.md D5; to-p1-r2.md): Photon's per-datagram receive handler,
    /// IPhotonSocket.HandleReceivedDatagram(byte[], int, bool) in Photon3Unity3D 4.1.7.0. Every transport's receive
    /// path calls it once per datagram: SocketUdp.ReceiveLoop on the thread SocketUdp.DnsAndConnect starts per
    /// connection (PhotonPeer's Udp default), and likewise SocketTcp, SocketTcpAsync, SocketUdpAsync,
    /// SocketUdpBlocking and PhotonClientWebSocket. The call's cycles are read on the thread that runs it. FrameTime
    /// only; the reference build (SCR_FT_NOCOLLECTORS) leaves it out, and Release and Thunderstore never compile
    /// this file.</summary>
    [HarmonyPatch]
    internal static class FtSockPatch
    {
        private static MethodBase TargetMethod()
        {
            var m = AccessTools.Method(typeof(ExitGames.Client.Photon.IPhotonSocket), "HandleReceivedDatagram",
                new[] { typeof(byte[]), typeof(int), typeof(bool) });
            if (m == null) throw new System.Exception("IPhotonSocket.HandleReceivedDatagram(byte[], int, bool) not found - no sock scope");
            return m;
        }

        [HarmonyPrefix]
        private static void Prefix(out ulong __state)
        {
            __state = FtLedger.SockEnter();
        }

        [HarmonyFinalizer]
        private static void Finalizer(ulong __state)
        {
            FtLedger.SockExit(__state);
        }
    }
#endif
}
#endif
