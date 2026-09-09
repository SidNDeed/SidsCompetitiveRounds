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
    ///    5 min at the main menu, the ONE trigger that requires a Photon
    ///    connection (an idle player has no consumer for the map); every 90 s
    ///    while a 1v1 queue lifecycle is live AND polling (searching, matched
    ///    or ready-sent) — connected or not; at JoinQueue when the last map
    ///    is older than 60 s (serves the NEXT upload — a join never waits on
    ///    pings). Never started while PUN's RegionHandler is pinging, and a
    ///    running sweep yields to it (the worker waits in 50 ms steps behind
    ///    a flag the main thread mirrors every frame; a round PUN interrupts
    ///    is discarded and run again after the wait) — PUN's sample has
    ///    priority; ours never touches RegionHandler state. Aborted when a
    ///    room join begins or a live room appears.
    ///
    /// Publication is main-thread only: LastMap / LastCompletedAt / Revision.
    /// One log line per completion:
    /// <c>[REGION-PINGS] n=&lt;targets&gt; ok=&lt;k&gt; ms=&lt;elapsed&gt; aborted=&lt;b&gt; map={us:42,...}</c>,
    /// carrying <c>deadline=true</c>, <c>err=</c>, <c>errs=</c>, <c>rev=</c> and
    /// <c>yielded_ms=</c> (time waited for PUN's pinging) only when they apply.</summary>
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
        const float QUEUE_CADENCE_S = 90f;
        // 60 s. The join body is the only upload a match found on the NEXT poll
        // can use: issuance then trails the join by at most READY_TIMEOUT_SECONDS
        // (90) plus one 3 s poll, and the server refuses a map stamped more than
        // REGION_PINGS_ISSUANCE_MAX_AGE_S (180) before issuance, in
        // _region_pings_at_issuance() — so a map older than ~87 s at join can
        // be refused with nothing uploaded in between. A LONGER queue wait is not
        // covered by this number at all; it is served by the queue cadence and the
        // poll header. The sweep this starts serves the next upload, not this join.
        const float JOIN_STALE_S = 60f;
        // Left at 15 min: a >180 s map on the join body costs one JSONB write and
        // is judged stale by the server on ITS clock. It is never mistaken for fresh.
        const float UPLOAD_MAX_AGE_S = 900f;
        const int ATTEMPTS = 4;
        const int ATTEMPT_MS = 500;
        const int POLL_MS = 10;
        const int BETWEEN_ROUNDS_MS = 50;
        const int MAX_TARGETS = 24;
        const int MIN_SUCCESSES = 2;
        const int MAX_MS = 700;
        // Mirrors main.py's REGION_PINGS_ISSUANCE_MAX_AGE_S — NOT its
        // REGION_PINGS_MAX_AGE_S (900), which is the acceptance limit and sits
        // on the very next line there; the SERVER still
        // judges the age itself — this only avoids paying for an upload it cannot use.
        const float HEADER_MAX_AGE_S = 180f;
        // A REFUSED start retries here, not a whole cadence later.
        const float SKIP_RETRY_S = 15f;
        const int DEFAULT_PORT = 5055;
        const int YIELD_STEP_MS = 50;

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
            public volatile int YieldedMs;   // written by the worker only; the main thread logs it at Finish
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
        static float skipUntilRt = -1f;    // set on entry to TryStart, cleared only by a start that happens
        static string blockedWhy;
        static float blockedLoggedRt = -1f;
        static volatile bool punPinging;   // RegionHandler.IsPinging, mirrored by Tick for the worker (impl r1 M3)
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
            // Deliberately NOT lastTriggerRt. That anchor is the cadence, and
            // only a sweep that actually STARTED may spend it. Stamping it here
            // spent a whole period on a trigger TryStart can still refuse — PUN's
            // own region ping outlives the 3 s delay often enough to matter — and
            // the refusal then waited out QUEUE_CADENCE_S instead of retrying
            // after SKIP_RETRY_S. scheduledAt already stops this trigger
            // re-arming; TryStart stamps the anchor once a thread is running.
        }

        /// <summary>Trigger (c): the 1v1 JoinQueue body builder. Starts a sweep
        /// when the last completed map is older than 60 s; the join in flight
        /// never waits for it — the result serves the next upload (the poll
        /// header, or a later join).</summary>
        public static void NoteJoinQueue()
        {
            float rt = Time.realtimeSinceStartup;
            bool fresh = LastCompletedAt >= 0f && rt - LastCompletedAt < JOIN_STALE_S;
            bool refreshing = !fresh && current == null;
            Plugin.Log?.LogInfo($"[REGION-PINGS] join age={(LastCompletedAt < 0f ? -1 : AgeSeconds())} rev={Revision} refresh={(refreshing ? "yes" : "no")}");
            if (fresh) return;
            if (current != null) return;
            TryStart("join");
        }

        /// <summary>Main-thread poll from the persistent tick (self-throttled
        /// to 250 ms): completes or aborts the in-flight sweep, then evaluates
        /// the scheduled and cadence triggers.</summary>
        public static void Tick()
        {
            // Impl r1 M3 (3.2(f)): mirror PUN's own pinging flag every frame for
            // the worker, which never touches PUN's live objects (NetworkingClient,
            // RegionHandler) itself.
            try { punPinging = PhotonNetwork.NetworkingClient?.RegionHandler?.IsPinging ?? false; }
            catch { punPinging = false; }
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

            // (b) + 7/3-1 + D1: cadence. 90 s while the 1v1 queue is live, else 5 min.
            bool queueLive = QueueLive();
            float cadence = queueLive ? QUEUE_CADENCE_S : MENU_CADENCE_S;
            float anchor = Math.Max(lastTriggerRt, LastCompletedAt);
            if (anchor >= 0f && rt - anchor < cadence) return;
            if (skipUntilRt >= 0f && rt < skipUntilRt) return;
            // The queue-live path is NOT gated on a Photon connection: this sweep
            // resolves its own DNS and sends raw UDP, and PUN's region list is a
            // plain field on the one NetworkingClient (assigned at
            // LoadBalancingClient.cs:1527) that no disconnect path clears. The
            // menu path keeps both gates — an idle player has no consumer.
            bool menuIdleOk = AtMainMenu() && ConnectedToMaster();
            if (!queueLive && !menuIdleOk)
            {
                NoteBlocked(!AtMainMenu() ? "not-at-menu" : "not-connected", rt);
                return;
            }
            blockedWhy = null;
            TryStart(queueLive ? "queue" : "menu");
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
        /// (<c>us=42,eu=31;age=12</c>) on every poll while the map is young
        /// enough that the server could still take it, else null. The server
        /// judges the age on its own clock, in _region_pings_at_issuance(); this
        /// cap only avoids paying for an upload it cannot use.
        ///
        /// NOT pure — an earlier draft of this line said it was. AgeSeconds()
        /// re-reads the clock, so two calls a second apart return different
        /// strings, and eventually null. What IS stable is the instant the
        /// server derives from it: the stamp is now - age, and age and the
        /// server's clock advance together, so re-sending an unrefreshed map
        /// re-derives the same absolute instant. Nothing here can freshen a
        /// stale map, which is the property that actually matters.</summary>
        public static string PollHeaderValue()
        {
            var map = LastMap;
            if (map == null || map.Count == 0 || LastCompletedAt < 0f) return null;
            int age = AgeSeconds();
            if (age > HEADER_MAX_AGE_S) return null;
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
            // Round UP. Truncation reported a map genuinely 180.9 s old as 180,
            // which is inside the server's issuance window and is then
            // stamped as if it really were that age — so the truncation did not
            // merely mis-report, it bought the map a fresh lease on the strength
            // of a rounding error. Over-reporting is the safe direction: the
            // worst it costs is one upload declined a second early.
            return (int)Math.Ceiling((double)age);
        }

        // ── start / finish (main thread) ──

        static void TryStart(string why)
        {
            float rt = Time.realtimeSinceStartup;
            scheduledAt = -1f;
            // Set BEFORE the guards, not at each refusal: every exit that is not
            // a started sweep — including ones not enumerated here and the catch
            // below — then costs SKIP_RETRY_S instead of re-entering at Tick's
            // 250 ms rate. Cleared only once a thread is actually running.
            skipUntilRt = rt + SKIP_RETRY_S;
            try
            {
                if (PhotonNetwork.InRoom && !PhotonNetwork.OfflineMode) return;      // (e), re-checked at start
                if (!string.IsNullOrEmpty(Plugin.PendingRankedRoom)) return;
                if (current != null)
                {
                    // Tick refuses every trigger while a sweep is in flight (d),
                    // but NoteCatalogReady arrives on a Photon callback and never
                    // passes through Tick. Without this, a sweep whose thread has
                    // finished but whose result Tick has not published yet would
                    // be REPLACED here and its map lost with no line saying so.
                    Plugin.Log?.LogInfo($"[REGION-PINGS] skipped why={why}: a sweep is already in flight");
                    return;
                }
                RegionHandler rh = PhotonNetwork.NetworkingClient?.RegionHandler;
                bool punHasList = rh != null && rh.EnabledRegions != null && rh.EnabledRegions.Count > 0;
                // D2: PUN builds a region list only from an OpGetRegions response,
                // and a ranked-only session never triggers one. RegionCatalog
                // fetches the same list from the NameServer itself; when neither
                // has one this returns exactly as it did before, having asked for
                // a fetch that serves the next trigger.
                if (!punHasList && (RegionCatalog.Entries == null || RegionCatalog.Entries.Length == 0))
                {
                    try { RegionCatalog.NoteWanted(); } catch { }
                    Plugin.Log?.LogInfo($"[REGION-PINGS] skipped why={why}: no region list yet");
                    return;
                }
                if (punHasList && rh.IsPinging)
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
                // ONE construction body for both sources (#432): PUN's list when it
                // has one, else the catalog's. The catalog carries the port ITS
                // addresses were built for, so a catalog-sourced sweep does not
                // depend on the process-wide static that anyone may rewrite.
                var pairs = new List<KeyValuePair<string, string>>();
                string source;
                if (punHasList)
                {
                    source = "pun";
                    foreach (var region in rh.EnabledRegions)
                        if (region != null) pairs.Add(new KeyValuePair<string, string>(region.Code, region.HostAndPort));
                }
                else
                {
                    source = "catalog";
                    foreach (var e in RegionCatalog.Entries)
                        if (e != null) pairs.Add(new KeyValuePair<string, string>(e.Code, e.HostAndPort));
                }
                int portOverride = punHasList ? RegionHandler.PortToPingOverride : RegionCatalog.PortOverride;
                List<Target> targets = BuildTargets(pairs, portOverride);
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
                lastTriggerRt = rt;   // only a start that HAPPENS consumes the cadence
                skipUntilRt = -1f;
                // A sweep that starts and publishes nothing (Finish) still consumes
                // a full cadence period — that is the bound's real failure step:
                // one fruitless cycle costs 90 s, not SKIP_RETRY_S.
                lastThread = th;
                current = sweep;
                int port0 = targets[0].Port;
                bool mixedPorts = false;
                foreach (var t in targets) if (t.Port != port0) { mixedPorts = true; break; }
                Plugin.Log?.LogInfo($"[REGION-PINGS] sweep started why={why} src={source} n={targets.Count} port={(mixedPorts ? "mixed" : port0.ToString())}");
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
            int yielded = s.YieldedMs;
            if (yielded > 0) sb.Append(" yielded_ms=").Append(yielded);
            Plugin.Log?.LogInfo(sb.ToString());
        }

        // ── the sweep thread ──

        /// <summary>Resolves every host (cached), then runs all targets'
        /// attempts concurrently, yielding to PUN's own region ping before each
        /// resolve and each send, and at every step of a round's reply window —
        /// a round PUN interrupts is discarded and run again (impl r1/r2 M3).
        /// Writes only into the sweep's own boxes; every box is marked Done in
        /// <c>finally</c>, so an exception can never strand the main-thread
        /// poll.</summary>
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
                    YieldToPun(s);
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
                var successesAtStart = new int[n];   // the boxes as a round begins; restored when PUN interrupts it
                var minMsAtStart = new int[n];
                int round = 0;
                while (round < ATTEMPTS && !s.Abort)
                {
                    int pending = 0;
                    bool interrupted = false;
                    for (int i = 0; i < n; i++)
                    {
                        successesAtStart[i] = boxes[i].Successes;
                        minMsAtStart[i] = boxes[i].MinMs;
                    }
                    for (int i = 0; i < n; i++)
                    {
                        if (punPinging)
                        {
                            // M3: PUN's own ping began mid-round. Drop what this round
                            // has already sent (a reply that waited through the yield
                            // would inflate its sample), wait it out, then start the
                            // round over; Abort (the 8 s deadline, a room join) ends
                            // the wait and the round.
                            DisposeRound(pings);
                            pending = 0;
                            YieldToPun(s);
                            if (s.Abort) break;
                            i = -1;
                            continue;
                        }
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
                        if (punPinging)
                        {
                            // M3 (impl r2): PUN's own ping began while this round's
                            // replies were still due — its sample and ours would share
                            // the wire. Stop reading replies; the round is discarded
                            // and run again after the yield below.
                            interrupted = true;
                            break;
                        }
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
                    DisposeRound(pings);
                    if (interrupted)
                    {
                        // Discard the round's samples: the boxes go back to what they
                        // held as the round began (replies read before the flag was
                        // seen included), then wait PUN out and run the same round
                        // again. Abort (the 8 s deadline, a room join) ends the wait
                        // and the loop at its guard.
                        for (int i = 0; i < n; i++)
                        {
                            boxes[i].Successes = successesAtStart[i];
                            boxes[i].MinMs = minMsAtStart[i];
                        }
                        YieldToPun(s);
                        continue;
                    }
                    round++;
                    if (round < ATTEMPTS && !s.Abort) Thread.Sleep(BETWEEN_ROUNDS_MS);
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

        /// <summary>Impl r1 M3 (3.2(f)): while PUN's own region ping runs, wait
        /// in 50 ms steps — its sample has priority. Reads only the flag Tick
        /// mirrors; Abort (the main-thread deadline or a room join) ends the
        /// wait. The waited time accrues on the sweep as it passes, so the main
        /// thread can report it even when the deadline cuts a wait short.</summary>
        static void YieldToPun(Sweep s)
        {
            if (!punPinging) return;
            int before = s.YieldedMs;
            var sw = Stopwatch.StartNew();
            while (punPinging && !s.Abort)
            {
                Thread.Sleep(YIELD_STEP_MS);
                s.YieldedMs = before + (int)sw.ElapsedMilliseconds;
            }
        }

        static void DisposeRound(RegionPing[] pings)
        {
            for (int i = 0; i < pings.Length; i++)
            {
                var p = pings[i];
                if (p == null) continue;
                try { p.Dispose(); } catch { }
                pings[i] = null;
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

        internal static bool AtMainMenu()
        {
            try
            {
                var mm = MainMenuHandler.instance;
                return mm != null && mm.isOpen;
            }
            catch { return false; }
        }

        /// <summary>The ping targets for a list of (code, hostAndPort) pairs —
        /// the ONE construction body, whichever source the pairs came from.
        /// <paramref name="portOverride"/> is the master-port override those
        /// addresses were built for: PUN's process-wide static for PUN's list,
        /// the catalog's own captured value for the catalog's.</summary>
        static List<Target> BuildTargets(List<KeyValuePair<string, string>> pairs, int portOverride)
        {
            var targets = new List<Target>(Math.Min(MAX_TARGETS, pairs.Count));
            foreach (var pair in pairs)
            {
                if (targets.Count >= MAX_TARGETS) break;
                string code = SafeCode(pair.Key);
                string host; int addrPort; bool webSocket;
                if (code == null || !ParseHostAndPort(pair.Value, out host, out addrPort, out webSocket)) continue;
                // 7/3-4, refined (impl r1 M2): the override first; else the port the
                // address carries when it is a UDP address (on Photon Cloud that is
                // the master's 5055 PingMono assumes; a self-hosted server's own
                // port otherwise); else 5055. A ws:// or wss:// port is a TCP/TLS
                // listener, never a UDP ping target — PUN's PingMono pings UDP 5055
                // on those hosts too, and so do we.
                int port = portOverride != 0 ? portOverride
                         : (!webSocket && addrPort != 0) ? addrPort
                         : DEFAULT_PORT;
                bool dup = false;
                foreach (var t in targets) if (t.Code == code) { dup = true; break; }
                if (dup) continue;
                targets.Add(new Target { Code = code, Host = host, Port = port });
            }
            return targets;
        }

        /// <summary>A catalog fetch published a list. Nothing consumes that edge
        /// otherwise: the join trigger has already fired by then and the cadence
        /// would wait out a full period, so the first ranked queue of a
        /// ranked-only session would still sweep nothing.</summary>
        public static void NoteCatalogReady()
        {
            float rt = Time.realtimeSinceStartup;
            if (LastMap != null && LastCompletedAt >= 0f
                && rt - LastCompletedAt < JOIN_STALE_S) return;
            // This edge arrives on a Photon callback, not through Tick, so it has
            // to re-apply Tick's policy rather than inherit it. TryStart exempts
            // an OfflineMode room from its in-room guard on purpose (a lingering
            // Sandbox flag, #122, must not wedge the sweep shut at the menu), so
            // without this a fetch begun at the menu and answered after the
            // player entered Sandbox would run the whole raw-UDP sweep inside a
            // local game where nothing can consume the result.
            bool consumer;
            try { consumer = QueueLive() || (AtMainMenu() && !PhotonNetwork.InRoom); }
            catch { return; }
            if (!consumer) { NoteBlocked("catalog-no-consumer", rt); return; }
            skipUntilRt = -1f;
            TryStart("catalog");
        }

        /// <summary>True while a 1v1 queue lifecycle is live AND polling. The
        /// poll header is this map's only delivery channel, so a sweep with
        /// polling off would serve nothing; the conjunction also means a
        /// CurrentQueueState left non-Idle cannot license sweeps on its own.
        /// Matched/ReadySent are in because the room is issued at the ready
        /// branch (main.py:15192), up to READY_TIMEOUT_SECONDS after the match.</summary>
        static bool QueueLive()
        {
            try
            {
                if (!ApiClient.IsQueuePolling) return false;
                var qs = ApiClient.CurrentQueueState;
                return qs == ApiClient.QueueState.Searching
                    || qs == ApiClient.QueueState.Matched
                    || qs == ApiClient.QueueState.ReadySent;
            }
            catch { return false; }
        }

        /// <summary>One line per distinct reason, at most once a minute: a
        /// cadence that returns silently is why the shipped gate went unnoticed,
        /// and a log at Tick's rate would be worse than none.</summary>
        static void NoteBlocked(string why, float rt)
        {
            if (why == blockedWhy && blockedLoggedRt >= 0f && rt - blockedLoggedRt < 60f) return;
            blockedWhy = why; blockedLoggedRt = rt;
            Plugin.Log?.LogInfo($"[REGION-PINGS] cadence blocked why={why} age={(LastCompletedAt < 0f ? -1 : AgeSeconds())} rev={Revision}");
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

        /// <summary>Photon's <c>Region.HostAndPort</c> -> host, the port the
        /// address carries (0 when none) and whether it was a WebSocket
        /// address (impl r1 M2). Mirrors the shipped RegionPinger (Start strips
        /// the port after the LAST ':'; ResolveHost strips a leading ws:// or
        /// wss://) plus the two shapes PUN's rule mangles: a bracketed IPv6
        /// literal (<c>[2001:db8::1]:5055</c> -> the literal without brackets,
        /// the port after <c>]:</c>) and a bare IPv6 literal, kept whole (its
        /// last ':' is not a port). Anything from the first '/' after the host
        /// is dropped; an unbracketed single ':' splits only when what follows
        /// is all digits. Pure: no I/O, no state.</summary>
        internal static bool ParseHostAndPort(string hostAndPort, out string host, out int port, out bool webSocket)
        {
            host = null; port = 0; webSocket = false;
            if (string.IsNullOrEmpty(hostAndPort)) return false;
            string h = hostAndPort.Trim();
            if (h.StartsWith("wss://", StringComparison.OrdinalIgnoreCase)) { h = h.Substring(6); webSocket = true; }
            else if (h.StartsWith("ws://", StringComparison.OrdinalIgnoreCase)) { h = h.Substring(5); webSocket = true; }
            int slash = h.IndexOf('/');
            if (slash >= 0) h = h.Substring(0, slash);
            string tail;
            if (h.StartsWith("[", StringComparison.Ordinal))
            {
                int close = h.IndexOf(']');
                if (close < 2) return false;                       // "[]" or no closing bracket
                host = h.Substring(1, close - 1);
                tail = h.Substring(close + 1);                     // "" or ":port"
                if (tail.Length == 0) return true;
                if (tail[0] != ':') return false;
                tail = tail.Substring(1);
            }
            else
            {
                int first = h.IndexOf(':');
                if (first < 0 || first != h.LastIndexOf(':') || !AllDigits(h, first + 1))
                {
                    host = h;                                      // no port, a bare IPv6 literal, or a non-numeric tail
                    return h.Length > 0;
                }
                host = h.Substring(0, first);
                tail = h.Substring(first + 1);
            }
            if (host.Length == 0) return false;
            int p;
            if (tail.Length > 0 && tail.Length <= 5 && AllDigits(tail, 0) && int.TryParse(tail, out p) && p >= 1 && p <= 65535)
                port = p;
            return true;
        }

        static bool AllDigits(string s, int from)
        {
            if (from >= s.Length) return false;
            for (int i = from; i < s.Length; i++) if (s[i] < '0' || s[i] > '9') return false;
            return true;
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
