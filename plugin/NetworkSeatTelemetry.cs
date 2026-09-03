using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Reflection;
using System.Text;
using ExitGames.Client.Photon;
using HarmonyLib;
using Photon.Pun;
using Photon.Realtime;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// W1 (lag-332 design v6 §1 + impl-review r1/r2): the REPORTER-SEAT
    /// network instrument.
    ///
    /// Everything here is a fact about THIS seat: what the local Player view
    /// wrote and raised (sender truth), what the Photon peer counted (resends,
    /// discards, CRC loss, queue depths sampled before every dispatch drain,
    /// fragment commands), and how the local frame behaved (a monotonic
    /// wall-clock frame gap, a fixed nine-bucket histogram, and a per-frame
    /// component ledger whose ≥60% owners become the worst frame's tags).
    /// Per-actor OBSERVATIONS of the remote stream live in
    /// NetworkReplicaDiagnostics; this class feeds it the lifecycle
    /// transitions (Die/Phoenix/Revive), the per-view movement samples, and
    /// the receiver's wall gap.
    ///
    /// Persistence is reporter-only: the 25 fields below ride the reporter's
    /// own authenticated match report (24 bounded integers + one 48-char
    /// tag). The 1 s window ring, the histogram, the component ledger and
    /// the self-profiler are BUNDLE-ONLY (logged at game end). Nothing here
    /// touches cr_gstats or any public surface (v4 §0).
    ///
    /// r1 HIGH 4: a match's 25 fields are FROZEN the moment the game closes —
    /// including a reliable room leave that precedes the survivor's
    /// disconnect-win report — and consumed exactly once by the next report;
    /// live state is reset independently. Spectator seats open/close their
    /// game from NetworkReplicaDiagnostics (r2 MEDIUM 7): frames plus this
    /// seat's own peer/queue facts (resends, discards, CRC, fragments, queue
    /// maxima, view-update faults) — never the local Player's serialize/raise
    /// counters (it owns no Player view), never a report.
    /// </summary>
    internal static class NetworkSeatTelemetry
    {
        // ── per-game aggregates (reset at match start) ───────────────────
        internal static long Writes, Unchanged;
        internal static long MoveRaiseAttempted, MoveRaiseAccepted;
        internal static int AcceptedBatchEncodedBytesContainingMovement;   // whole encoded event — never "movement bytes"; bundle-only
        internal static long ViewUpdateFaults;
        internal static long ResentReliable, Discarded, CrcLoss, FragmentCmds;
        internal static int QueuedOutMax, QueuedInMax;                     // inbound: raw socket queue + channel lists before each Dispatch drain; outbound: before each SendOutgoingCommands (r2 MEDIUM 9 / r3 MEDIUM 10)
        internal static long Hitch50, Hitch200;
        internal static int WorstFrameMs;
        internal static string WorstFrameTags = "";

        private static bool _gameOpen;
        private static bool _spectatorGame;
        private static float _windowStartRt = -1f;
        private static int _baseResent, _baseDiscarded, _baseCrc, _baseFragment;
        private static bool _baselineTaken;
        private static int _lastGcCount;

        // Monotonic Update-boundary clock (r2 MEDIUM 6/8): the frame's WALL gap
        // is measured here, never read from Time.unscaledDeltaTime (which is
        // the fixed step inside PUN's FixedUpdate dispatch).
        private static long _lastUpdateTick;
        private static int _lastFrameWallMs;

        // Fixed nine-bucket frame histogram (bundle-only, r2 MEDIUM 8), ALL open-
        // game frames: <8, <17, <34, <50, <100, <200, <500, <1000, >=1000 ms.
        private static readonly int[] HistEdgesMs = { 8, 17, 34, 50, 100, 200, 500, 1000 };
        private static readonly long[] _hist = new long[HistEdgesMs.Length + 1];

        // Per-frame component ledger (r2 MEDIUM 8): named durations measured
        // INSIDE the frame (music decode, our network callbacks). A component
        // that owns ≥60% of the frame's wall gap is a cause tag; context flags
        // (gc/load/f5/spec) are prefixed "ctx:" because they are observations,
        // not measured owners.
        private static double _compDecodeMs, _compNetCbMs;

        // Window ring (bundle-only): 64 most recent 1 s windows.
        private const int WINDOW_RING = 64;
        private struct Window
        {
            public int Seq; public long UtcMs; public int ServerTs;
            public long CloseTick;   // r6 LOW 5: monotonic close time — the HUD's recency test; UtcMs is for cross-system correlation only
            public int Writes, Unchanged, Attempted, Accepted, Resent, Discarded, Crc, Fragment, QOut, QIn, Hitch50, Hitch200, WorstMs;
            public string WorstTags;
        }
        private static readonly Window[] _ring = new Window[WINDOW_RING];
        private static int _ringCount, _ringHead, _windowSeq;
        private static long _wWrites, _wUnchanged, _wAttempted, _wAccepted, _wHitch50, _wHitch200;
        private static int _wWorstMs, _wQOut, _wQIn;
        private static int _wResent, _wDiscarded, _wCrc, _wFragment;
        private static string _wWorstTags = "";

        // Local Player view id — lazily acquired from the first local-Player
        // OnSerializeWrite (v6 §1.3), cleared on room change. Integer only:
        // no reference held on the hot path.
        private static int _localPlayerViewId;

        // r1 HIGH 4: the frozen 25-field fragment of the last closed game,
        // consumed once by AppendReportFields; null when nothing is pending.
        private static string _frozenReportFields;
        private static int _gameSeq;

        // Self-profiler for this class's own per-frame work (bundle-only).
        private static long _tickTicks, _tickCalls;

        // ── lifecycle (game/room edges) ──────────────────────────────────

        internal static void OnRoomChanged()
        {
            // A room change with an OPEN game is a reliable leave: close the
            // game (freezing its report fields) BEFORE anything is reset — the
            // survivor's disconnect-win report is built later from the frozen
            // copy (r1 HIGH 4).
            if (_gameOpen) OnMatchEnded("room-left");
            _localPlayerViewId = 0;
            ResetGame(keepFrozen: true);
        }

        internal static void OnMatchStarted()
        {
            // A new match discards an unconsumed snapshot of an earlier one:
            // that report, if it never happened, cannot be built any more.
            ResetGame(keepFrozen: false);
            _gameSeq++;
            _gameOpen = true;
            _spectatorGame = false;
            try { _spectatorGame = RoomActors.LocalIsSpectator; } catch { }
            TakePeerBaseline();
            try { _lastGcCount = GC.CollectionCount(0); } catch { }
            try { PhotonNetwork.NetworkStatisticsEnabled = true; } catch { }
            // r3 MEDIUM 12: the observer's per-frame accumulator is cleared at
            // every begin edge so intergame hook work never lands on game 2's
            // first frame (ResetHookCost clears both the game totals and it).
            try { NetworkReplicaDiagnostics.ResetHookCost(); } catch { }
            _lastUpdateTick = System.Diagnostics.Stopwatch.GetTimestamp();
            _lastFrameWall = 0;
        }

        internal static bool GameOpen => _gameOpen;

        internal static void OnMatchEnded(string reason)
        {
            if (!_gameOpen) return;
            CloseWindow(force: true);
            SamplePeerDeltas();
            _gameOpen = false;
            try { NetworkReplicaDiagnostics.DrainFrameHookTicks(); } catch { }   // r3 MEDIUM 12: clear at the end edge too
            if (!_spectatorGame)
            {
                try
                {
                    // Freeze BEFORE any reset and before NetworkReplicaDiagnostics
                    // clears its actors (it calls OnRoomChanged first, by design).
                    var sb = new StringBuilder(1024);
                    AppendLiveReportFields(sb, ApiClientEscape);
                    _frozenReportFields = sb.ToString();
                }
                catch (Exception ex) { Plugin.Log?.LogWarning($"[NET-SEAT] freeze failed: {ex.Message}"); }
            }
            try { LogGameSummary(reason); } catch { }
        }

        private static string ApiClientEscape(string s) { return ApiClient.EscapeForJson(s); }

        private static void ResetGame(bool keepFrozen)
        {
            Writes = Unchanged = 0; MoveRaiseAttempted = MoveRaiseAccepted = 0; AcceptedBatchEncodedBytesContainingMovement = 0;
            ViewUpdateFaults = 0; ResentReliable = Discarded = CrcLoss = FragmentCmds = 0; QueuedOutMax = QueuedInMax = 0;
            Hitch50 = Hitch200 = 0; WorstFrameMs = 0; WorstFrameTags = "";
            _gameOpen = false; _windowStartRt = -1f; _baselineTaken = false;
            _ringCount = 0; _ringHead = 0; _windowSeq = 0;
            Array.Clear(_hist, 0, _hist.Length);
            _tickTicks = 0; _tickCalls = 0;
            _compDecodeMs = 0; _compNetCbMs = 0;
            if (!keepFrozen) { _frozenReportFields = null; }
            ResetWindowAccumulators();
        }

        private static void ResetWindowAccumulators()
        {
            _wWrites = _wUnchanged = _wAttempted = _wAccepted = _wHitch50 = _wHitch200 = 0;
            _wWorstMs = 0; _wQOut = _wQIn = 0; _wResent = _wDiscarded = _wCrc = _wFragment = 0;
            _wWorstTags = "";
        }

        // ── per-frame (from GameStateWatcher.TickFrame) ──────────────────

        private static bool _tGc, _tLoading, _tPick, _tBattle, _tF5;

        /// <summary>The receiver's wall gap since its last Update boundary —
        /// what a stalled receiver actually lost, readable from inside PUN's
        /// FixedUpdate dispatch (r2 MEDIUM 6).</summary>
        internal static int ReceiverWallGapMsNow()
        {
            try
            {
                if (_lastUpdateTick == 0) return 0;
                long ms = (System.Diagnostics.Stopwatch.GetTimestamp() - _lastUpdateTick) * 1000L / System.Diagnostics.Stopwatch.Frequency;
                return ms > int.MaxValue ? int.MaxValue : (int)ms;
            }
            catch { return 0; }
        }

        /// <summary>A measured component of this frame (music decode ms, …).
        /// Called from inside the frame; consumed at the next TickFrame.</summary>
        internal static void NoteDecodeMs(double ms) { _compDecodeMs += ms; }

        /// <summary>battle = the FIGHTER'S vanilla battleOngoing; a spectator
        /// seat uses the observer's validated battle gate instead. Spectator
        /// seats sample frames plus their own peer/queue facts (r2 MEDIUM 7);
        /// they own no Player view, so no serialize/raise counters, and they
        /// never report.</summary>
        internal static void TickFrame(bool battle, bool pick, bool spectator)
        {
            if (!_gameOpen) return;
            long t0 = System.Diagnostics.Stopwatch.GetTimestamp();
            try
            {
                if (spectator) { try { battle = NetworkReplicaDiagnostics.BattleActive; } catch { battle = false; } }
                float rt = Time.realtimeSinceStartup;
                // Monotonic wall gap of the frame that just ended (r2 MEDIUM 8),
                // kept as a double for the ownership arithmetic (r3 LOW 15) and
                // truncated only for buckets/persisted values.
                long now = t0;
                double frameWall = _lastUpdateTick == 0 ? 0.0 : (now - _lastUpdateTick) * 1000.0 / System.Diagnostics.Stopwatch.Frequency;
                int frameMs = frameWall > int.MaxValue ? int.MaxValue : (int)frameWall;
                _lastUpdateTick = now;
                _lastFrameWallMs = frameMs;
                _lastFrameWall = frameWall;
                // Components measured inside the frame that just ended.
                double netCbMs = 0;
                try { netCbMs = NetworkReplicaDiagnostics.DrainFrameHookTicks() * 1000.0 / System.Diagnostics.Stopwatch.Frequency; } catch { }
                _compNetCbMs = netCbMs;
                // Context flags (observations, prefixed "ctx:" in the tag string).
                _tBattle = battle; _tPick = pick;
                int gc = 0;
                try { gc = GC.CollectionCount(0); } catch { }
                _tGc = gc != _lastGcCount; _lastGcCount = gc;
                try { var ls = LoadingScreen.instance; _tLoading = ls != null && ls.IsLoading; } catch { _tLoading = false; }
                try { _tF5 = NativeUI.IsOpen; } catch { _tF5 = false; }
                if (frameMs > 0)
                {
                    int b = 0;
                    while (b < HistEdgesMs.Length && frameMs >= HistEdgesMs[b]) b++;
                    _hist[b]++;
                }
                if (battle)
                {
                    if (frameMs >= 50) { Hitch50++; _wHitch50++; }
                    if (frameMs >= 200) { Hitch200++; _wHitch200++; }
                }
                if (frameMs > _wWorstMs) { _wWorstMs = frameMs; _wWorstTags = BuildTags(frameMs); }
                if (frameMs > WorstFrameMs)
                {
                    WorstFrameMs = frameMs;
                    WorstFrameTags = _wWorstTags.Length > 0 ? _wWorstTags : BuildTags(frameMs);
                }
                _compDecodeMs = 0;
                if (_windowStartRt < 0f) _windowStartRt = rt;
                else if (rt - _windowStartRt >= 1f) CloseWindow(force: false);
            }
            catch { }
            finally { _tickTicks += System.Diagnostics.Stopwatch.GetTimestamp() - t0; _tickCalls++; }
        }

        /// <summary>The worst-frame tag string, built only when a new worst
        /// frame is recorded: measured owners (≥60% of the wall gap) first,
        /// then "ctx:" observations; ≤ 40 chars.</summary>
        private static double _lastFrameWall;

        private static string BuildTags(int frameMs)
        {
            var sb = new StringBuilder(40);
            double threshold = _lastFrameWall > 0 ? _lastFrameWall * 0.6 : frameMs * 0.6;
            if (_compDecodeMs >= threshold && _compDecodeMs > 0) sb.Append("decode");
            if (_compNetCbMs >= threshold && _compNetCbMs > 0) { if (sb.Length > 0) sb.Append('|'); sb.Append("netcb"); }
            if (sb.Length == 0) sb.Append("unattributed");
            sb.Append(_tBattle ? "|ctx:battle" : _tPick ? "|ctx:pick" : "|ctx:between");
            if (_tGc) sb.Append("|ctx:gc");
            if (_tLoading) sb.Append("|ctx:load");
            if (_tF5) sb.Append("|ctx:f5");
            if (_spectatorGame) sb.Append("|ctx:spec");
            if (sb.Length > 40) sb.Length = 40;
            return sb.ToString();
        }

        private static void CloseWindow(bool force)
        {
            if (_windowStartRt < 0f && !force) return;
            SamplePeerDeltas();
            int serverTs = 0;
            try { serverTs = PhotonNetwork.ServerTimestamp; } catch { }
            var w = new Window
            {
                Seq = ++_windowSeq,
                UtcMs = (long)(DateTime.UtcNow - new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc)).TotalMilliseconds,
                CloseTick = System.Diagnostics.Stopwatch.GetTimestamp(),
                ServerTs = serverTs,
                Writes = (int)Math.Min(int.MaxValue, _wWrites), Unchanged = (int)Math.Min(int.MaxValue, _wUnchanged),
                Attempted = (int)Math.Min(int.MaxValue, _wAttempted), Accepted = (int)Math.Min(int.MaxValue, _wAccepted),
                Resent = _wResent, Discarded = _wDiscarded, Crc = _wCrc, Fragment = _wFragment,
                QOut = _wQOut, QIn = _wQIn,
                Hitch50 = (int)Math.Min(int.MaxValue, _wHitch50), Hitch200 = (int)Math.Min(int.MaxValue, _wHitch200), WorstMs = _wWorstMs,
                WorstTags = _wWorstTags,
            };
            _ring[_ringHead] = w;
            _ringHead = (_ringHead + 1) % WINDOW_RING;
            if (_ringCount < WINDOW_RING) _ringCount++;
            ResetWindowAccumulators();
            _windowStartRt = Time.realtimeSinceStartup;
        }

        /// <summary>HUD (r1 MEDIUM 16 / r2 LOW 16 / r3 LOW 14): the windows that
        /// CLOSED within the last ten seconds of wall time (a stall makes one
        /// long window, so "ten windows" would over-span) plus the current
        /// partial one, with the partial window's peer counters read LIVE
        /// (non-mutating) — never game-lifetime totals.</summary>
        internal static void RecentWindowStats(out int worstMs, out int resends, out int discards)
        {
            worstMs = _wWorstMs; resends = 0; discards = 0;
            try
            {
                var peer = PhotonNetwork.NetworkingClient?.LoadBalancingPeer;
                if (peer != null && _baselineTaken)
                {
                    // Live partial-window deltas: peer total since match start minus
                    // the totals already folded into closed windows.
                    resends = Math.Max(0, (peer.ResentReliableCommands - _baseResent) - (int)ResentReliable);
                    discards = Math.Max(0, (peer.CountDiscarded - _baseDiscarded) - (int)Discarded);
                }
                // r6 LOW 5: monotonic recency — an OS/NTP clock step must not
                // retain or drop windows; ring order and CloseTick order agree.
                long cutoffTick = System.Diagnostics.Stopwatch.GetTimestamp() - 10L * System.Diagnostics.Stopwatch.Frequency;
                for (int i = 1; i <= _ringCount; i++)
                {
                    var w = _ring[(_ringHead - i + WINDOW_RING) % WINDOW_RING];
                    if (w.CloseTick < cutoffTick) break;
                    if (w.WorstMs > worstMs) worstMs = w.WorstMs;
                    resends += w.Resent; discards += w.Discarded;
                }
            }
            catch { }
        }

        // ── Photon peer stats (deltas since match start) ─────────────────

        private static void TakePeerBaseline()
        {
            try
            {
                var peer = PhotonNetwork.NetworkingClient?.LoadBalancingPeer;
                if (peer == null) return;
                _baseResent = peer.ResentReliableCommands;
                _baseDiscarded = peer.CountDiscarded;
                _baseCrc = peer.PacketLossByCrc;
                _baseFragment = peer.TrafficStatsOutgoing != null ? peer.TrafficStatsOutgoing.FragmentCommandCount : 0;
                _baselineTaken = true;
            }
            catch { _baselineTaken = false; }
        }

        private static void SamplePeerDeltas()
        {
            try
            {
                var peer = PhotonNetwork.NetworkingClient?.LoadBalancingPeer;
                if (peer == null || !_baselineTaken) return;
                int resent = peer.ResentReliableCommands - _baseResent;
                int discarded = peer.CountDiscarded - _baseDiscarded;
                int crc = peer.PacketLossByCrc - _baseCrc;
                int fragment = (peer.TrafficStatsOutgoing != null ? peer.TrafficStatsOutgoing.FragmentCommandCount : 0) - _baseFragment;
                // Window deltas: difference against the running game totals.
                _wResent = Math.Max(0, resent - (int)ResentReliable);
                _wDiscarded = Math.Max(0, discarded - (int)Discarded);
                _wCrc = Math.Max(0, crc - (int)CrcLoss);
                _wFragment = Math.Max(0, fragment - (int)FragmentCmds);
                ResentReliable = Math.Max(0, resent);
                Discarded = Math.Max(0, discarded);
                CrcLoss = Math.Max(0, crc);
                FragmentCmds = Math.Max(0, fragment);
            }
            catch { }
        }

        /// <summary>INBOUND depth, sampled by the PhotonHandler.Dispatch Prefix
        /// (r2 MEDIUM 9 / r3 MEDIUM 10): on the ENet peer, the raw socket
        /// CommandQueue (not yet transferred to the channel lists — read through
        /// a cached private field, allocation-free) PLUS the channel lists'
        /// queued commands, immediately before DispatchIncomingCommands transfers
        /// and drains both. On a peer without that raw queue (the TCP TPeer,
        /// whose public QueuedIncomingCommands IS the list Dispatch drains — r4
        /// LOW 13) the public count alone is the complete measurement; the seat
        /// says so once.</summary>
        internal static void NoteInboundDepth()
        {
            if (!_gameOpen) return;
            try
            {
                var peer = PhotonNetwork.NetworkingClient?.LoadBalancingPeer;
                if (peer == null) return;
                int qi = peer.QueuedIncomingCommands + RawInboundQueueCount(peer);
                if (qi > QueuedInMax) QueuedInMax = qi;
                if (qi > _wQIn) _wQIn = qi;
            }
            catch { }
        }

        /// <summary>OUTBOUND depth, sampled by a PhotonPeer.SendOutgoingCommands
        /// Prefix — the exact boundary before a send drains the outgoing
        /// queue (r3 MEDIUM 10: RunViewUpdate enqueues and the same LateUpdate
        /// sends, so a Dispatch-time sample missed every view batch).</summary>
        internal static void NoteOutboundDepth(PhotonPeer peer)
        {
            if (!_gameOpen || peer == null) return;
            try
            {
                int qo = peer.QueuedOutgoingCommands;
                if (qo > QueuedOutMax) QueuedOutMax = qo;
                if (qo > _wQOut) _wQOut = qo;
            }
            catch { }
        }

        // Raw inbound queue access: PhotonPeer.peerBase (internal) → EnetPeer
        // .CommandQueue (private Queue<NCommand>). Resolved once per peer TYPE;
        // Count is read through the non-generic ICollection (no allocation).
        private static FieldInfo _fiPeerBase, _fiCommandQueue;
        private static Type _rawQueuePeerType;
        private static bool _rawQueueResolved, _rawQueueMissingLogged;
        private static int RawInboundQueueCount(PhotonPeer peer)
        {
            try
            {
                if (!_rawQueueResolved)
                {
                    _rawQueueResolved = true;
                    _fiPeerBase = typeof(PhotonPeer).GetField("peerBase", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
                    if (_fiPeerBase == null) Plugin.Log?.LogInfo("[NET-SEAT] PhotonPeer.peerBase not found — queued_in_max is the peer's public queued-incoming count");
                }
                if (_fiPeerBase == null) return 0;
                object pb = _fiPeerBase.GetValue(peer);
                if (pb == null) return 0;
                Type pt = pb.GetType();
                if (!ReferenceEquals(pt, _rawQueuePeerType))
                {
                    _rawQueuePeerType = pt;
                    _fiCommandQueue = pt.GetField("CommandQueue", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
                    if (_fiCommandQueue == null && !_rawQueueMissingLogged)
                    {
                        _rawQueueMissingLogged = true;
                        Plugin.Log?.LogInfo($"[NET-SEAT] no raw socket queue on {pt.Name} — queued_in_max is that transport's public queued-incoming count (complete for TPeer)");
                    }
                }
                if (_fiCommandQueue == null) return 0;
                var q = _fiCommandQueue.GetValue(pb) as ICollection;
                return q != null ? q.Count : 0;
            }
            catch { return 0; }
        }

        // ── sender hooks (called by the Harmony patches below) ───────────

        internal static void NoteSerializeWrite(PhotonView view, bool wroteData)
        {
            if (view == null) return;
            try
            {
                if (_localPlayerViewId == 0)
                {
                    if (view.IsMine && view.GetComponent<Player>() != null) _localPlayerViewId = view.ViewID;
                    else return;
                }
                if (view.ViewID != _localPlayerViewId) return;
                if (!_gameOpen || _spectatorGame) return;
                if (wroteData) { Writes++; _wWrites++; } else { Unchanged++; _wUnchanged++; }
            }
            catch { }
        }

        /// <summary>Prefix half: allocation-free scan of the outer/nested
        /// List&lt;object&gt; batch for the local Player view id (v6 §1.3).
        /// A throwing raise is still an ATTEMPT — counted here.</summary>
        internal static bool NoteRaiseAttempt(byte code, object content)
        {
            try
            {
                if (code != 201 && code != 206) return false;
                int id = _localPlayerViewId;
                if (id == 0) return false;
                var outer = content as IList;
                if (outer == null) return false;
                for (int i = 2; i < outer.Count; i++)
                {
                    var nested = outer[i] as IList;
                    if (nested == null || nested.Count == 0) continue;
                    if (nested[0] is int vid && vid == id)
                    {
                        if (_gameOpen && !_spectatorGame) { MoveRaiseAttempted++; _wAttempted++; }
                        return true;
                    }
                }
            }
            catch { }
            return false;
        }

        internal static void NoteRaiseResult(bool containedLocal, bool accepted)
        {
            if (!containedLocal || !accepted || !_gameOpen || _spectatorGame) return;
            try
            {
                MoveRaiseAccepted++; _wAccepted++;
                var peer = PhotonNetwork.NetworkingClient?.LoadBalancingPeer;
                if (peer != null) AcceptedBatchEncodedBytesContainingMovement = peer.ByteCountLastOperation;
            }
            catch { }
        }

        internal static void NoteViewUpdateFault()
        {
            if (_gameOpen) ViewUpdateFaults++;
        }

        // ── report fields ────────────────────────────────────────────────

        private static int Clamp(long v, int max) { return v < 0 ? 0 : v > max ? max : (int)v; }

        /// <summary>The 24 integers + tag for the match report. Consumes the
        /// FROZEN snapshot of the last closed game when one is pending (r1
        /// HIGH 4 — the disconnect-win report is built after the reliable
        /// leave reset); falls back to the live aggregates otherwise.</summary>
        internal static void AppendReportFields(StringBuilder sb, Func<string, string> escape)
        {
            string frozen = _frozenReportFields;
            if (frozen != null)
            {
                _frozenReportFields = null;   // consume once
                sb.Append(frozen);
                return;
            }
            AppendLiveReportFields(sb, escape);
        }

        private static void AppendLiveReportFields(StringBuilder sb, Func<string, string> escape)
        {
            const int C = 1000000, M = 3600000;
            sb.Append("\"local_net_writes\":").Append(Clamp(Writes, C)).Append(',');
            sb.Append("\"local_net_unchanged\":").Append(Clamp(Unchanged, C)).Append(',');
            sb.Append("\"local_net_move_raise_attempted\":").Append(Clamp(MoveRaiseAttempted, C)).Append(',');
            sb.Append("\"local_net_move_raise_accepted\":").Append(Clamp(MoveRaiseAccepted, C)).Append(',');
            sb.Append("\"local_net_resent_reliable\":").Append(Clamp(ResentReliable, C)).Append(',');
            sb.Append("\"local_net_discarded\":").Append(Clamp(Discarded, C)).Append(',');
            sb.Append("\"local_net_crc_loss\":").Append(Clamp(CrcLoss, C)).Append(',');
            sb.Append("\"local_net_queued_out_max\":").Append(Clamp(QueuedOutMax, C)).Append(',');
            sb.Append("\"local_net_queued_in_max\":").Append(Clamp(QueuedInMax, C)).Append(',');
            sb.Append("\"local_net_fragment_cmds\":").Append(Clamp(FragmentCmds, C)).Append(',');
            sb.Append("\"local_net_view_update_faults\":").Append(Clamp(ViewUpdateFaults, C)).Append(',');
            sb.Append("\"local_net_hitch50\":").Append(Clamp(Hitch50, C)).Append(',');
            sb.Append("\"local_net_hitch200\":").Append(Clamp(Hitch200, C)).Append(',');
            sb.Append("\"local_net_worst_frame_ms\":").Append(Clamp(WorstFrameMs, M)).Append(',');
            string tags = WorstFrameTags ?? "";
            if (tags.Length > 48) tags = tags.Substring(0, 48);
            sb.Append("\"local_net_worst_frame_tags\":\"").Append(escape(tags)).Append("\",");
            NetworkReplicaDiagnostics.ObsSnapshot o;
            bool haveObs = NetworkReplicaDiagnostics.TryGetOpponentGameObs(out o);
            sb.Append("\"local_obs_gap300\":").Append(haveObs ? Clamp(o.Gap300, C).ToString(CultureInfo.InvariantCulture) : "null").Append(',');
            sb.Append("\"local_obs_gap750\":").Append(haveObs ? Clamp(o.Gap750, C).ToString(CultureInfo.InvariantCulture) : "null").Append(',');
            sb.Append("\"local_obs_gap1500\":").Append(haveObs ? Clamp(o.Gap1500, C).ToString(CultureInfo.InvariantCulture) : "null").Append(',');
            sb.Append("\"local_obs_max_gap_ms\":").Append(haveObs ? Clamp(o.MaxGapMs, M).ToString(CultureInfo.InvariantCulture) : "null").Append(',');
            sb.Append("\"local_obs_excess150\":").Append(haveObs ? Clamp(o.Excess150, C).ToString(CultureInfo.InvariantCulture) : "null").Append(',');
            sb.Append("\"local_obs_max_excess_ms\":").Append(haveObs ? Clamp(o.MaxExcessMs, M).ToString(CultureInfo.InvariantCulture) : "null").Append(',');
            sb.Append("\"local_obs_payload_equal_gaps\":").Append(haveObs ? Clamp(o.PayloadEqualGaps, C).ToString(CultureInfo.InvariantCulture) : "null").Append(',');
            sb.Append("\"local_obs_receiver_frame_gaps\":").Append(haveObs ? Clamp(o.ReceiverFrameGaps, C).ToString(CultureInfo.InvariantCulture) : "null").Append(',');
            sb.Append("\"local_obs_phoenix_intervals\":").Append(haveObs ? Clamp(o.PhoenixIntervals, C).ToString(CultureInfo.InvariantCulture) : "null").Append(',');
            sb.Append("\"local_obs_batches\":").Append(haveObs ? Clamp(o.Batches, C).ToString(CultureInfo.InvariantCulture) : "null").Append(',');
        }

        private static void LogGameSummary(string reason)
        {
            var sb = new StringBuilder(640);
            sb.Append("[NET-SEAT] reason=").Append(reason).Append(" spectator=").Append(_spectatorGame)
              .Append(" writes=").Append(Writes).Append(" unchanged=").Append(Unchanged)
              .Append(" moveRaise=").Append(MoveRaiseAccepted).Append('/').Append(MoveRaiseAttempted)
              .Append(" acceptedBatchEncodedBytesContainingMovement=").Append(AcceptedBatchEncodedBytesContainingMovement)
              .Append(" resent=").Append(ResentReliable).Append(" discarded=").Append(Discarded).Append(" crc=").Append(CrcLoss)
              .Append(" fragmentCmds(global)=").Append(FragmentCmds)
              .Append(" qOutMax=").Append(QueuedOutMax).Append(" qInMax=").Append(QueuedInMax)
              .Append(" viewUpdateFaults=").Append(ViewUpdateFaults)
              .Append(" hitch50=").Append(Hitch50).Append(" hitch200=").Append(Hitch200)
              .Append(" worstFrame=").Append(WorstFrameMs).Append("ms(").Append(WorstFrameTags).Append(')');
            sb.Append(" hist(<8,<17,<34,<50,<100,<200,<500,<1000,>=1000)=");
            for (int i = 0; i < _hist.Length; i++) { if (i > 0) sb.Append('/'); sb.Append(_hist[i]); }
            Plugin.Log?.LogInfo(sb.ToString());
            // Window ring: newest last, one line, bounded.
            var wl = new StringBuilder(2048);
            wl.Append("[NET-SEAT-WINDOWS] n=").Append(_ringCount).Append(" seq@utcMs@serverTs:w/u/att/acc/res/dis/crc/frag/qoMax/qiMax/h50/h200/worst(tags) ");
            int start = (_ringHead - _ringCount + WINDOW_RING) % WINDOW_RING;
            for (int i = 0; i < _ringCount; i++)
            {
                var w = _ring[(start + i) % WINDOW_RING];
                if (i > 0) wl.Append(' ');
                wl.Append(w.Seq).Append('@').Append(w.UtcMs).Append('@').Append(w.ServerTs).Append(':')
                  .Append(w.Writes).Append('/').Append(w.Unchanged).Append('/').Append(w.Attempted).Append('/').Append(w.Accepted)
                  .Append('/').Append(w.Resent).Append('/').Append(w.Discarded).Append('/').Append(w.Crc).Append('/').Append(w.Fragment)
                  .Append('/').Append(w.QOut).Append('/').Append(w.QIn).Append('/').Append(w.Hitch50).Append('/').Append(w.Hitch200).Append('/').Append(w.WorstMs)
                  .Append('(').Append(w.WorstTags ?? "").Append(')');
            }
            Plugin.Log?.LogInfo(wl.ToString());
            // Self-profiler: this class's per-frame cost + the observer hooks'.
            double tickMs = _tickTicks * 1000.0 / System.Diagnostics.Stopwatch.Frequency;
            Plugin.Log?.LogInfo("[NET-PROF] seatTickCalls=" + _tickCalls.ToString(CultureInfo.InvariantCulture)
                + " seatTickMs=" + tickMs.ToString("F1", CultureInfo.InvariantCulture) + " "
                + NetworkReplicaDiagnostics.HookCostLine().Replace("[NET-PROF] ", ""));
        }
    }

    // ── Harmony hooks (sender truth) ─────────────────────────────────────

    /// <summary>PhotonNetwork.OnSerializeWrite(PhotonView) — private static,
    /// publicized assembly. Postfix: null result = UnreliableOnChange judged
    /// the payload unchanged (nothing sent); a list = data written.</summary>
    [HarmonyPatch]
    internal static class NetworkSeat_OnSerializeWritePatch
    {
        private static MethodBase TargetMethod()
        {
            var m = AccessTools.Method(typeof(PhotonNetwork), "OnSerializeWrite", new[] { typeof(PhotonView) });
            if (m == null) throw new Exception("PhotonNetwork.OnSerializeWrite(PhotonView) not found - seat telemetry has no sender target");
            return m;
        }

        [HarmonyPostfix]
        private static void Postfix(PhotonView __0, List<object> __result)
        {
            try { NetworkSeatTelemetry.NoteSerializeWrite(__0, __result != null); } catch { }
        }
    }

    /// <summary>PhotonNetwork.RaiseEventInternal(byte, object, RaiseEventOptions,
    /// SendOptions): Prefix scans the batch (attempt), Postfix counts the
    /// accepted raise + samples the whole-event byte count. Positional
    /// binds — no __args (#364).</summary>
    [HarmonyPatch]
    internal static class NetworkSeat_RaiseEventInternalPatch
    {
        private static MethodBase TargetMethod()
        {
            var m = AccessTools.Method(typeof(PhotonNetwork), "RaiseEventInternal",
                new[] { typeof(byte), typeof(object), typeof(RaiseEventOptions), typeof(SendOptions) });
            if (m == null) throw new Exception("PhotonNetwork.RaiseEventInternal(byte, object, RaiseEventOptions, SendOptions) not found - seat telemetry has no raise target");
            return m;
        }

        [HarmonyPrefix]
        private static void Prefix(byte __0, object __1, out bool __state)
        {
            __state = false;
            try { __state = NetworkSeatTelemetry.NoteRaiseAttempt(__0, __1); } catch { }
        }

        [HarmonyPostfix]
        private static void Postfix(bool __state, bool __result)
        {
            try { NetworkSeatTelemetry.NoteRaiseResult(__state, __result); } catch { }
        }
    }

    /// <summary>PhotonNetwork.RunViewUpdate(): Finalizer counts a fault and
    /// returns the IDENTICAL exception (null stays null) — never swallows.</summary>
    [HarmonyPatch]
    internal static class NetworkSeat_RunViewUpdatePatch
    {
        private static MethodBase TargetMethod()
        {
            var m = AccessTools.Method(typeof(PhotonNetwork), "RunViewUpdate", Type.EmptyTypes);
            if (m == null) throw new Exception("PhotonNetwork.RunViewUpdate() not found - seat telemetry has no view-update target");
            return m;
        }

        [HarmonyFinalizer]
        private static Exception Finalizer(Exception __exception)
        {
            try { if (__exception != null) NetworkSeatTelemetry.NoteViewUpdateFault(); } catch { }
            return __exception;
        }
    }

    /// <summary>PhotonHandler.Dispatch() (protected, publicized): the inbound
    /// backlog is measured BEFORE it drains (r2 MEDIUM 9). One property read
    /// per dispatch; no allocation.</summary>
    [HarmonyPatch]
    internal static class NetworkSeat_DispatchDepthPatch
    {
        private static MethodBase TargetMethod()
        {
            var m = AccessTools.Method(typeof(PhotonHandler), "Dispatch", Type.EmptyTypes);
            if (m == null) throw new Exception("PhotonHandler.Dispatch() not found - seat telemetry has no queue-depth target");
            return m;
        }

        [HarmonyPrefix]
        private static void Prefix()
        {
            try { NetworkSeatTelemetry.NoteInboundDepth(); } catch { }
        }
    }

    /// <summary>PhotonPeer.SendOutgoingCommands() Prefix: the outbound queue
    /// depth at the exact pre-send boundary (r3 MEDIUM 10). One property read
    /// per send; no allocation.</summary>
    [HarmonyPatch]
    internal static class NetworkSeat_SendOutgoingDepthPatch
    {
        private static MethodBase TargetMethod()
        {
            var m = AccessTools.Method(typeof(PhotonPeer), "SendOutgoingCommands", Type.EmptyTypes);
            if (m == null) throw new Exception("PhotonPeer.SendOutgoingCommands() not found - seat telemetry has no outbound-depth target");
            return m;
        }

        [HarmonyPrefix]
        private static void Prefix(PhotonPeer __instance)
        {
            try { NetworkSeatTelemetry.NoteOutboundDepth(__instance); } catch { }
        }
    }

    // ── Harmony hooks (remote lifecycle: accepted Die / Phoenix / Revive) ─

    /// <summary>Per-invocation state object (v6 §1.2): a sealed REFERENCE
    /// shared by Prefix (out), Postfix and Finalizer of the same patch class,
    /// so the commit is exactly-once (Committed flips before any telemetry
    /// side effect) and survives an exceptional exit of the original.</summary>
    internal sealed class LifecycleInvocation
    {
        public bool Committed;
        public bool ActiveBefore, DeadBefore, RespawningBefore;
        public int ViewId, OwnerActor;
        public int RoomGeneration;   // v6 §1.2: a commit is only valid for the room it was snapshotted in
    }

    internal static class LifecycleCommit
    {
        internal const int KindDie = 0, KindPhoenix = 1, KindRevive = 2;

        internal static LifecycleInvocation Snapshot(HealthHandler h)
        {
            var s = new LifecycleInvocation();
            var data = h.data;
            var view = data != null ? data.view : null;
            s.ActiveBefore = h.gameObject.activeSelf;
            s.DeadBefore = data != null && data.dead;
            s.RespawningBefore = h.isRespawning;
            s.ViewId = view != null ? view.ViewID : 0;
            s.OwnerActor = view != null ? view.OwnerActorNr : 0;
            s.RoomGeneration = NetworkReplicaDiagnostics.RoomGeneration;
            return s;
        }

        /// <summary>Idempotent completion: called from Postfix AND Finalizer.</summary>
        internal static void Commit(HealthHandler h, LifecycleInvocation st, int kind)
        {
            if (st == null || st.Committed) return;
            st.Committed = true;
            if (st.RoomGeneration != NetworkReplicaDiagnostics.RoomGeneration) return;   // room changed mid-call: no commit
            try
            {
                bool activeNow = h.gameObject.activeSelf;
                var data = h.data;
                bool deadNow = data != null && data.dead;
                bool respNow = h.isRespawning;
                switch (kind)
                {
                    case KindDie:
                        if (st.ActiveBefore && !activeNow && !st.DeadBefore && deadNow)
                            NetworkReplicaDiagnostics.OnAcceptedDeath(st.OwnerActor, st.ViewId, phoenix: false);
                        break;
                    case KindPhoenix:
                        if (st.ActiveBefore && !activeNow && !st.RespawningBefore && respNow)
                            NetworkReplicaDiagnostics.OnAcceptedDeath(st.OwnerActor, st.ViewId, phoenix: true);
                        break;
                    case KindRevive:
                        if (!st.ActiveBefore && activeNow)
                            NetworkReplicaDiagnostics.OnAcceptedRevive(st.OwnerActor, st.ViewId);
                        break;
                }
            }
            catch { }
        }
    }

    [HarmonyPatch(typeof(HealthHandler), "RPCA_Die")]
    internal static class NetworkSeat_LifecycleDiePatch
    {
        [HarmonyPrefix]
        private static void Prefix(HealthHandler __instance, out LifecycleInvocation __state)
        {
            __state = null;
            try { var complete = LifecycleCommit.Snapshot(__instance); __state = complete; } catch { }
        }
        [HarmonyPostfix]
        private static void Postfix(HealthHandler __instance, LifecycleInvocation __state)
        {
            try { LifecycleCommit.Commit(__instance, __state, LifecycleCommit.KindDie); } catch { }
        }
        [HarmonyFinalizer]
        private static Exception Finalizer(HealthHandler __instance, LifecycleInvocation __state, Exception __exception)
        {
            try { LifecycleCommit.Commit(__instance, __state, LifecycleCommit.KindDie); } catch { }
            return __exception;
        }
    }

    [HarmonyPatch(typeof(HealthHandler), "RPCA_Die_Phoenix")]
    internal static class NetworkSeat_LifecyclePhoenixPatch
    {
        [HarmonyPrefix]
        private static void Prefix(HealthHandler __instance, out LifecycleInvocation __state)
        {
            __state = null;
            try { var complete = LifecycleCommit.Snapshot(__instance); __state = complete; } catch { }
        }
        [HarmonyPostfix]
        private static void Postfix(HealthHandler __instance, LifecycleInvocation __state)
        {
            try { LifecycleCommit.Commit(__instance, __state, LifecycleCommit.KindPhoenix); } catch { }
        }
        [HarmonyFinalizer]
        private static Exception Finalizer(HealthHandler __instance, LifecycleInvocation __state, Exception __exception)
        {
            try { LifecycleCommit.Commit(__instance, __state, LifecycleCommit.KindPhoenix); } catch { }
            return __exception;
        }
    }

    [HarmonyPatch(typeof(HealthHandler), "Revive")]
    internal static class NetworkSeat_LifecycleRevivePatch
    {
        [HarmonyPrefix]
        private static void Prefix(HealthHandler __instance, out LifecycleInvocation __state)
        {
            __state = null;
            try { var complete = LifecycleCommit.Snapshot(__instance); __state = complete; } catch { }
        }
        [HarmonyPostfix]
        private static void Postfix(HealthHandler __instance, LifecycleInvocation __state)
        {
            try { LifecycleCommit.Commit(__instance, __state, LifecycleCommit.KindRevive); } catch { }
        }
        [HarmonyFinalizer]
        private static Exception Finalizer(HealthHandler __instance, LifecycleInvocation __state, Exception __exception)
        {
            try { LifecycleCommit.Commit(__instance, __state, LifecycleCommit.KindRevive); } catch { }
            return __exception;
        }
    }

    // ── Harmony hooks (movement capture: fighter-only Postfix) ───────────

    /// <summary>SyncPlayerMovement.OnPhotonSerializeView read branch: Prefix
    /// snapshots syncPackages.Count; Postfix reads the package vanilla
    /// appended (never a stream cursor — v3 §1.1, CONFIRMED d3/d4) and hands
    /// it to NetworkReplicaDiagnostics with the call-scoped receive context,
    /// which is where the timing window is committed on fighter seats
    /// (r1 HIGH 3: view-confirmed, never actor-keyed).</summary>
    [HarmonyPatch(typeof(SyncPlayerMovement), "OnPhotonSerializeView")]
    internal static class NetworkSeat_MovementCapturePatch
    {
        [HarmonyPrefix]
        private static void Prefix(SyncPlayerMovement __instance, PhotonStream __0, out int __state)
        {
            __state = -1;
            try
            {
                if (__0 == null || !__0.IsReading) return;
                if (SpectatorSession.IsLocalSpectator) return;   // fighter-only in Release A
                var list = __instance.syncPackages;
                __state = list != null ? list.Count : -1;
            }
            catch { __state = -1; }
        }

        [HarmonyPostfix]
        private static void Postfix(SyncPlayerMovement __instance, int __state)
        {
            if (__state < 0) return;
            try
            {
                var list = __instance.syncPackages;
                if (list == null || list.Count <= __state) return;
                var pkg = list[list.Count - 1];
                var view = __instance.photonView;
                NetworkReplicaDiagnostics.RecordMovementSample(view != null ? view.ViewID : 0, pkg.pos, pkg.vel, pkg.dir, pkg.aim,
                                                               pkg.holdJump, pkg.jump, pkg.sinceGrounded, pkg.timeDelta);
            }
            catch { }
        }
    }
}
