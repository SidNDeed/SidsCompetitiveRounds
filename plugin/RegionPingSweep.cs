using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using Photon.Pun;
using Photon.Realtime;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Sept 7 item 3 (design v2 section 7): the ranked best-region
    /// finder's measurement half. Pings every region in Photon's current
    /// region list with our own UDP pinger and publishes a {code: min ms} map
    /// that the 1v1 queue join carries in its body and the queue poll carries
    /// as the <c>X-Region-Pings</c> header; the server's room-region pick reads
    /// both seats' maps at issuance (rung 0).
    ///
    /// Shape, and why:
    ///  * ONE dedicated background thread per sweep (BelowNormal) — never the
    ///    ThreadPool, which PUN's own RegionPinger queues on. DNS resolves on
    ///    that thread through a per-host cache (1 h); all targets' attempts then
    ///    run CONCURRENTLY from the same thread (start every socket, poll
    ///    Done() every 10 ms, 500 ms per attempt, 4 attempts, 50 ms between
    ///    rounds). A new sweep is REFUSED while the previous thread is still
    ///    alive, so a hung resolve costs at most one background thread.
    ///  * A fresh Sweep object per run with one RegionBox per target, written
    ///    by exactly that thread; the main thread polls every 250 ms and
    ///    publishes at completion, at the 8 s deadline (what completed) or
    ///    discards on Abort. An orphaned worker can never satisfy a successor.
    ///  * <see cref="RegionPing"/> is our own PhotonPing subclass: it closes
    ///    its socket on every failure path (PingMono's catch nulls the socket
    ///    without closing it) and validates replies exactly as PingMono does.
    ///  * Triggers: 3 s after ConnectedToMaster (not in OfflineMode); every
    ///    5 min at the main menu while connected and not in a live room; every
    ///    90 s while the 1v1 queue is searching; at JoinQueue when the last map
    ///    is older than 5 min (serves the NEXT join — a join never waits on
    ///    pings). Never while PUN's RegionHandler is pinging (its sweep has
    ///    priority; ours never touches RegionHandler state). Aborted when a
    ///    room join begins or a live room appears.
    ///
    /// Publication is main-thread only: LastMap / LastCompletedAt / Revision.
    /// One log line per completion:
    /// <c>[REGION-PINGS] n=&lt;targets&gt; ok=&lt;k&gt; ms=&lt;elapsed&gt; aborted=&lt;b&gt; map={us:42,...}</c>.</summary>
    internal static class RegionPingSweep
    {
        // ── published results (main thread only) ──
        public static Dictionary<string, int> LastMap;      // null until a sweep publishes
        public static float LastCompletedAt = -1f;          // Time.realtimeSinceStartup; < 0 = never
        public static int Revision;                         // bumps on every publication

        const float DEADLINE_S = 8f;
        const float POLL_S = 0.25f;
        const float CONNECT_DELAY_S = 3f;
        const float MENU_CADENCE_S = 300f;
        const float SEARCH_CADENCE_S = 90f;
        const float JOIN_STALE_S = 300f;
        const float UPLOAD_MAX_AGE_S = 900f;
        const int ATTEMPTS = 4;
        const int ATTEMPT_MS = 500;
        const int POLL_MS = 10;
        const int BETWEEN_ROUNDS_MS = 50;
        const int MAX_TARGETS = 24;
        const int MIN_SUCCESSES = 2;
        const int MAX_MS = 700;
        const int HEADER_POLLS = 3;
        const int DEFAULT_PORT = 5055;

        sealed class Target
        {
            public string Code;
            public string Host;
            public int Port;
        }

        /// <summary>One per target, written by the sweep thread only; the main
        /// thread reads after Done, or whatever is there at the deadline.</summary>
        sealed class RegionBox
        {
            public string Code;
            public volatile bool Done;
            public volatile int Successes;
            public volatile int MinMs = int.MaxValue;
            public volatile string Error;
        }

        sealed class Sweep
        {
            public Target[] Targets;
            public RegionBox[] Boxes;
            public float StartedRt;
            public string Why;
            public volatile bool Abort;
            public volatile bool Finished;
            public volatile string Error;
        }

        sealed class DnsEntry
        {
            public IPAddress Address;
            public DateTime ExpiresUtc;
        }

        static Sweep current;              // the in-flight sweep (main thread owns the reference)
        static Thread lastThread;          // refuse a new sweep while this is alive
        static float scheduledAt = -1f;    // trigger (a): fire time, < 0 = none
        static float lastTriggerRt = -1f;  // cadence anchor
        static float nextPollRt;
        static int announcedRevision;
        static int headerSendsLeft;
        static readonly Dictionary<string, DnsEntry> dnsCache = new Dictionary<string, DnsEntry>(StringComparer.OrdinalIgnoreCase);
        static readonly object dnsLock = new object();

        // ── triggers ──

        /// <summary>Trigger (a): Cr2v2DiagCallbacks.OnConnectedToMaster. Ignored
        /// in OfflineMode (the Sandbox's synthetic connection, #122/#473b);
        /// otherwise the sweep is scheduled 3 s out so PUN's own region ping
        /// and the lobby chatter have settled.</summary>
        public static void NoteConnectedToMaster()
        {
            try { if (PhotonNetwork.OfflineMode) return; } catch { return; }
            float rt = Time.realtimeSinceStartup;
            scheduledAt = rt + CONNECT_DELAY_S;
            lastTriggerRt = rt;
        }

        /// <summary>Trigger (c): the 1v1 JoinQueue body builder. Starts a sweep
        /// when the last completed map is older than 5 min; the join in flight
        /// never waits for it — the result serves the next join and the poll
        /// header.</summary>
        public static void NoteJoinQueue()
        {
            float rt = Time.realtimeSinceStartup;
            if (LastCompletedAt >= 0f && rt - LastCompletedAt < JOIN_STALE_S) return;
            if (current != null) return;
            TryStart("join");
        }

        /// <summary>Main-thread poll from the persistent tick (self-throttled
        /// to 250 ms): completes or aborts the in-flight sweep, then evaluates
        /// the scheduled and cadence triggers.</summary>
        public static void Tick()
        {
            float rt = Time.realtimeSinceStartup;
            if (rt < nextPollRt) return;
            nextPollRt = rt + POLL_S;

            bool liveRoom = false, pendingJoin = false;
            try
            {
                liveRoom = PhotonNetwork.InRoom && !PhotonNetwork.OfflineMode;
                pendingJoin = !string.IsNullOrEmpty(Plugin.PendingRankedRoom);
            }
            catch { }

            var sweep = current;
            if (sweep != null)
            {
                if (liveRoom || pendingJoin)
                {
                    // (e): a room join begins / a live room appears — discard.
                    current = null;
                    Finish(sweep, aborted: true);
                }
                else if (sweep.Finished || AllDone(sweep) || rt - sweep.StartedRt >= DEADLINE_S)
                {
                    current = null;
                    Finish(sweep, aborted: false);
                }
                return;   // (d): one sweep in flight; no trigger while it runs
            }

            if (liveRoom || pendingJoin) { scheduledAt = -1f; return; }

            // (a): the delayed post-connect sweep.
            if (scheduledAt >= 0f && rt >= scheduledAt)
            {
                scheduledAt = -1f;
                TryStart("connected");
                return;
            }

            // (b) + 7/3-1: cadence while at the menu, connected, not in a live
            // room — 90 s while the 1v1 queue is searching, 5 min otherwise.
            bool searching = false;
            try { searching = ApiClient.CurrentQueueState == ApiClient.QueueState.Searching; } catch { }
            float cadence = searching ? SEARCH_CADENCE_S : MENU_CADENCE_S;
            float anchor = Math.Max(lastTriggerRt, LastCompletedAt);
            if (anchor >= 0f && rt - anchor < cadence) return;
            if (!searching && !AtMainMenu()) return;
            if (!ConnectedToMaster()) return;
            TryStart(searching ? "searching" : "menu");
        }

        // ── upload shapes ──

        /// <summary>The 1v1 join body's extra fields, or "" when no map is
        /// worth sending: <c>,"region_pings":{"us":42,...},"region_pings_age_s":N</c>.
        /// Omitted when nothing has completed or the map is older than 15 min.</summary>
        public static string JoinBodyFields()
        {
            var map = LastMap;
            if (map == null || map.Count == 0 || LastCompletedAt < 0f) return "";
            int age = AgeSeconds();
            if (age > UPLOAD_MAX_AGE_S) return "";
            var sb = new StringBuilder(160);
            sb.Append(",\"region_pings\":{");
            bool first = true;
            foreach (var kv in map)
            {
                if (!first) sb.Append(',');
                first = false;
                sb.Append('"').Append(kv.Key).Append("\":").Append(kv.Value);
            }
            sb.Append("},\"region_pings_age_s\":").Append(age);
            return sb.ToString();
        }

        /// <summary>The <c>X-Region-Pings</c> header value
        /// (<c>us=42,eu=31;age=12</c>) for the next three polls after each new
        /// publication, else null. Call once per poll.</summary>
        public static string PollHeaderValue()
        {
            if (Revision != announcedRevision)
            {
                announcedRevision = Revision;
                headerSendsLeft = HEADER_POLLS;
            }
            if (headerSendsLeft <= 0) return null;
            var map = LastMap;
            if (map == null || map.Count == 0 || LastCompletedAt < 0f) return null;
            int age = AgeSeconds();
            if (age > UPLOAD_MAX_AGE_S) return null;
            headerSendsLeft--;
            var sb = new StringBuilder(120);
            bool first = true;
            foreach (var kv in map)
            {
                if (!first) sb.Append(',');
                first = false;
                sb.Append(kv.Key).Append('=').Append(kv.Value);
            }
            sb.Append(";age=").Append(age);
            return sb.ToString();
        }

        static int AgeSeconds()
        {
            float age = Time.realtimeSinceStartup - LastCompletedAt;
            if (age < 0f) age = 0f;
            return (int)age;
        }

        // ── start / finish (main thread) ──

        static void TryStart(string why)
        {
            float rt = Time.realtimeSinceStartup;
            lastTriggerRt = rt;
            scheduledAt = -1f;
            try
            {
                if (PhotonNetwork.InRoom && !PhotonNetwork.OfflineMode) return;      // (e), re-checked at start
                if (!string.IsNullOrEmpty(Plugin.PendingRankedRoom)) return;
                RegionHandler rh = PhotonNetwork.NetworkingClient?.RegionHandler;
                if (rh == null || rh.EnabledRegions == null || rh.EnabledRegions.Count == 0)
                {
                    Plugin.Log?.LogInfo($"[REGION-PINGS] skipped why={why}: no region list yet");
                    return;
                }
                if (rh.IsPinging)
                {
                    // (f): PUN's own sweep has priority; the next trigger retries.
                    Plugin.Log?.LogInfo($"[REGION-PINGS] skipped why={why}: RegionHandler is pinging");
                    return;
                }
                var prev = lastThread;
                if (prev != null && prev.IsAlive)
                {
                    // 7/3-2: a hung resolve costs one background thread, never two.
                    Plugin.Log?.LogWarning($"[REGION-PINGS] skipped why={why}: previous sweep thread still alive");
                    return;
                }
                int port = RegionHandler.PortToPingOverride != 0 ? RegionHandler.PortToPingOverride : DEFAULT_PORT;
                var targets = new List<Target>(Math.Min(MAX_TARGETS, rh.EnabledRegions.Count));
                foreach (var region in rh.EnabledRegions)
                {
                    if (targets.Count >= MAX_TARGETS) break;
                    if (region == null) continue;
                    string code = SafeCode(region.Code);
                    string host = HostOf(region.HostAndPort);
                    if (code == null || host == null) continue;
                    bool dup = false;
                    foreach (var t in targets) if (t.Code == code) { dup = true; break; }
                    if (dup) continue;
                    targets.Add(new Target { Code = code, Host = host, Port = port });
                }
                if (targets.Count == 0)
                {
                    Plugin.Log?.LogInfo($"[REGION-PINGS] skipped why={why}: no usable targets");
                    return;
                }
                var sweep = new Sweep
                {
                    Targets = targets.ToArray(),
                    Boxes = new RegionBox[targets.Count],
                    StartedRt = rt,
                    Why = why,
                };
                for (int i = 0; i < targets.Count; i++) sweep.Boxes[i] = new RegionBox { Code = targets[i].Code };
                var th = new Thread(() => Worker(sweep))
                {
                    IsBackground = true,
                    Priority = System.Threading.ThreadPriority.BelowNormal,
                    Name = "CR_RegionPingSweep",
                };
                th.Start();
                lastThread = th;
                current = sweep;
                Plugin.Log?.LogInfo($"[REGION-PINGS] sweep started why={why} n={targets.Count} port={port}");
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning($"[REGION-PINGS] start failed why={why}: {ex.GetType().Name}: {ex.Message}");
            }
        }

        static bool AllDone(Sweep s)
        {
            var boxes = s.Boxes;
            for (int i = 0; i < boxes.Length; i++) if (!boxes[i].Done) return false;
            return true;
        }

        /// <summary>Publishes a completed sweep (or what completed by the
        /// deadline) and logs the one line. An aborted sweep, or one whose map
        /// is empty, publishes nothing — the previous map stays.</summary>
        static void Finish(Sweep s, bool aborted)
        {
            s.Abort = true;   // the worker stops between rounds either way
            float rt = Time.realtimeSinceStartup;
            int elapsed = (int)((rt - s.StartedRt) * 1000f);
            var map = new Dictionary<string, int>();
            var errs = new StringBuilder();
            int ok = 0;
            var boxes = s.Boxes;
            for (int i = 0; i < boxes.Length; i++)
            {
                var b = boxes[i];
                if (!aborted && b.Successes >= MIN_SUCCESSES && b.MinMs <= MAX_MS)
                {
                    map[b.Code] = b.MinMs;
                    ok++;
                }
                else if (b.Error != null && errs.Length < 240)
                {
                    if (errs.Length > 0) errs.Append(' ');
                    errs.Append(b.Code).Append(':').Append(b.Error);
                }
            }
            var sb = new StringBuilder(200);
            sb.Append("[REGION-PINGS] n=").Append(boxes.Length).Append(" ok=").Append(ok)
              .Append(" ms=").Append(elapsed).Append(" aborted=").Append(aborted ? "true" : "false")
              .Append(" map={");
            bool first = true;
            foreach (var kv in map)
            {
                if (!first) sb.Append(',');
                first = false;
                sb.Append(kv.Key).Append(':').Append(kv.Value);
            }
            sb.Append('}');
            if (!s.Finished && !aborted) sb.Append(" deadline=true");
            if (s.Error != null) sb.Append(" err=").Append(s.Error);
            if (errs.Length > 0) sb.Append(" errs=").Append(errs);
            if (!aborted && map.Count > 0)
            {
                LastMap = map;
                LastCompletedAt = rt;
                Revision++;
                sb.Append(" rev=").Append(Revision);
            }
            Plugin.Log?.LogInfo(sb.ToString());
        }

        // ── the sweep thread ──

        /// <summary>Resolves every host (cached), then runs all targets'
        /// attempts concurrently. Writes only into the sweep's own boxes; every
        /// box is marked Done in <c>finally</c>, so an exception can never
        /// strand the main-thread poll.</summary>
        static void Worker(Sweep s)
        {
            var sw = Stopwatch.StartNew();
            var targets = s.Targets;
            var boxes = s.Boxes;
            int n = targets.Length;
            try
            {
                var ips = new IPAddress[n];
                for (int i = 0; i < n; i++)
                {
                    if (s.Abort) return;
                    try
                    {
                        ips[i] = Resolve(targets[i].Host);
                        if (ips[i] == null) { boxes[i].Error = "no-address"; boxes[i].Done = true; }
                    }
                    catch (Exception ex)
                    {
                        boxes[i].Error = "dns-" + ex.GetType().Name;
                        boxes[i].Done = true;
                    }
                }

                var pings = new RegionPing[n];
                var startedAt = new long[n];
                var settled = new bool[n];
                for (int round = 0; round < ATTEMPTS && !s.Abort; round++)
                {
                    int pending = 0;
                    for (int i = 0; i < n; i++)
                    {
                        settled[i] = false;
                        pings[i] = null;
                        if (ips[i] == null) continue;
                        var p = new RegionPing(targets[i].Port);
                        try
                        {
                            startedAt[i] = sw.ElapsedMilliseconds;
                            p.StartPing(ips[i].ToString());
                            pings[i] = p;
                            pending++;
                        }
                        catch (Exception ex)
                        {
                            p.Dispose();
                            boxes[i].Error = "send-" + ex.GetType().Name;
                        }
                    }
                    long windowEnd = sw.ElapsedMilliseconds + ATTEMPT_MS;
                    while (pending > 0 && !s.Abort && sw.ElapsedMilliseconds < windowEnd)
                    {
                        Thread.Sleep(POLL_MS);
                        for (int i = 0; i < n; i++)
                        {
                            var p = pings[i];
                            if (p == null || settled[i]) continue;
                            bool done;
                            try { done = p.Done(); }
                            catch { done = true; }
                            if (!done) continue;
                            settled[i] = true;
                            pending--;
                            if (p.Successful)
                            {
                                int ms = (int)(sw.ElapsedMilliseconds - startedAt[i]);
                                if (ms < 1) ms = 1;
                                boxes[i].Successes = boxes[i].Successes + 1;
                                if (ms < boxes[i].MinMs) boxes[i].MinMs = ms;
                            }
                        }
                    }
                    for (int i = 0; i < n; i++)
                    {
                        var p = pings[i];
                        if (p == null) continue;
                        try { p.Dispose(); } catch { }
                        pings[i] = null;
                    }
                    if (round < ATTEMPTS - 1 && !s.Abort) Thread.Sleep(BETWEEN_ROUNDS_MS);
                }
            }
            catch (Exception ex)
            {
                s.Error = ex.GetType().Name + ": " + ex.Message;
            }
            finally
            {
                for (int i = 0; i < n; i++) boxes[i].Done = true;
                s.Finished = true;
            }
        }

        /// <summary>Per-host cache (1 h). IPv4 preferred; an IPv4-mapped IPv6
        /// answer is unmapped; IPv6 only when the host has no IPv4 at all.
        /// Worker thread only.</summary>
        static IPAddress Resolve(string host)
        {
            lock (dnsLock)
            {
                DnsEntry e;
                if (dnsCache.TryGetValue(host, out e) && e.ExpiresUtc > DateTime.UtcNow) return e.Address;
            }
            IPAddress ip;
            IPAddress literal;
            if (IPAddress.TryParse(host, out literal))
            {
                ip = literal.IsIPv4MappedToIPv6 ? literal.MapToIPv4() : literal;
            }
            else
            {
                IPAddress v4 = null, v6 = null;
                foreach (var a in Dns.GetHostAddresses(host))
                {
                    if (a == null) continue;
                    if (a.AddressFamily == AddressFamily.InterNetwork)
                    {
                        if (v4 == null) v4 = a;
                    }
                    else if (a.AddressFamily == AddressFamily.InterNetworkV6)
                    {
                        if (a.IsIPv4MappedToIPv6) { if (v4 == null) v4 = a.MapToIPv4(); }
                        else if (v6 == null) v6 = a;
                    }
                }
                ip = v4 ?? v6;
            }
            if (ip != null)
            {
                lock (dnsLock)
                {
                    dnsCache[host] = new DnsEntry { Address = ip, ExpiresUtc = DateTime.UtcNow.AddHours(1) };
                }
            }
            return ip;
        }

        // ── predicates and parsing (main thread) ──

        static bool AtMainMenu()
        {
            try
            {
                var mm = MainMenuHandler.instance;
                return mm != null && mm.isOpen;
            }
            catch { return false; }
        }

        static bool ConnectedToMaster()
        {
            try
            {
                if (PhotonNetwork.OfflineMode) return false;
                var st = PhotonNetwork.NetworkClientState;
                return st == ClientState.ConnectedToMasterServer || st == ClientState.JoinedLobby;
            }
            catch { return false; }
        }

        /// <summary>Region.Code is already lower-cased and cluster-stripped by
        /// PUN; this keeps only what the server's region token admits
        /// (2..5 ASCII letters) so the upload is well-formed by construction.</summary>
        static string SafeCode(string code)
        {
            if (string.IsNullOrEmpty(code)) return null;
            string c = code.Trim().ToLowerInvariant();
            if (c.Length < 2 || c.Length > 5) return null;
            for (int i = 0; i < c.Length; i++)
            {
                char ch = c[i];
                if (ch < 'a' || ch > 'z') return null;
            }
            return c;
        }

        /// <summary>"host:port" -> host (RegionPinger.Start's own rule: strip
        /// from the LAST ':' when it is past position 1). The ping port is
        /// PortToPingOverride or 5055, never the master port.</summary>
        static string HostOf(string hostAndPort)
        {
            if (string.IsNullOrEmpty(hostAndPort)) return null;
            string h = hostAndPort.Trim();
            int colon = h.LastIndexOf(':');
            if (colon > 1) h = h.Substring(0, colon);
            return h.Length == 0 ? null : h;
        }
    }

    /// <summary>Our own PhotonPing (7/3-4): a UDP socket opened by the
    /// literal's address family, Connect + Send, with the socket CLOSED on
    /// any failure path — PingMono's catch nulls its socket without closing
    /// it. Done() polls with a zero timeout and validates the reply exactly as
    /// PingMono does (last byte == PingId, length == PingLength). One instance
    /// per attempt; Dispose closes.</summary>
    internal sealed class RegionPing : PhotonPing
    {
        private Socket sock;
        private readonly int port;

        public RegionPing(int port) { this.port = port; }

        public override bool StartPing(string ip)
        {
            Init();
            Close();
            Socket s = null;
            try
            {
                IPAddress addr = IPAddress.Parse(ip);
                s = new Socket(addr.AddressFamily, SocketType.Dgram, ProtocolType.Udp);
                s.Connect(new IPEndPoint(addr, port));
                PingBytes[PingBytes.Length - 1] = PingId;
                s.Send(PingBytes);
                PingBytes[PingBytes.Length - 1] = (byte)(PingId + 1);
                sock = s;
                return false;
            }
            catch
            {
                if (s != null) { try { s.Close(); } catch { } }
                sock = null;
                throw;
            }
        }

        public override bool Done()
        {
            if (GotResult || sock == null) return true;
            int received;
            try
            {
                if (!sock.Poll(0, SelectMode.SelectRead)) return false;
                received = sock.Receive(PingBytes, SocketFlags.None);
            }
            catch (Exception ex)
            {
                Close();
                DebugString = DebugString + " socket exception " + ex.GetType().Name;
                Successful = false;
                GotResult = true;
                return true;
            }
            bool match = PingBytes[PingBytes.Length - 1] == PingId && received == PingLength;
            if (!match) DebugString += " ReplyMatch is false! ";
            Successful = match;
            GotResult = true;
            return true;
        }

        public override void Dispose() { Close(); }

        private void Close()
        {
            var s = sock;
            sock = null;
            if (s == null) return;
            try { s.Close(); } catch { }
        }
    }
}
