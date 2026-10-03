using BepInEx;
using HarmonyLib;
using Photon.Pun;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Text;
using System.Threading;
using UnityEngine;
using C = CompetitiveRounds.SeatEvidenceCore;

namespace CompetitiveRounds
{
    /// <summary>SEAT EVIDENCE, the Unity half (contract V2,
    /// ai-collab/integrity-1001/SEAT-EVIDENCE-CONTRACT-V2.md). For one ranked
    /// 1v1 game this seat records what it did itself and what arrived from the
    /// other seat, and after the game sends one record. The pure half
    /// (serialising, the budgeter, signing, the answer table) is
    /// SeatEvidenceCore.
    ///
    /// It ships in every build with no setting in front of it. It records and
    /// sends; it holds no threshold and decides nothing about any seat.
    ///
    /// Containment: every entry point catches its own faults and returns, so
    /// a collector fault never changes a hit, a block, a push, a shot or a
    /// timing; the hooks that call in also wrap each call. Nothing here logs
    /// per frame; every buffer is bounded; the record is built after the game
    /// and sent only while no battle is live.</summary>
    internal static class SeatEvidence
    {
        internal const string TAG = "[SEAT-EV]";
        private const string ROUTE_RECORD = "/api/v1/matches/seat-evidence";
        private const string ROUTE_COMPAT = "/api/v1/client/compat-outcome";
        private const string ROUTE_CARD = "/api/v1/matches/card-evidence";

        private static readonly Stopwatch _sw = Stopwatch.StartNew();
        internal static long SwMs { get { return _sw.ElapsedMilliseconds; } }

        private static int ServerNow()
        {
            try { return PhotonNetwork.ServerTimestamp; } catch { return 0; }
        }

        // -- the game window ------------------------------------------------------------

        private static bool _open;
        private static int _oppActor;
        private static int _localActor;
        private static bool _masterAtStart, _rankedAtStart;

        // A window closed by a room exit before any record was built: frozen as
        // it stood, for the room-exit dispatch (or a DC-win report) to take.
        private static bool _frozen;
        private static long _frozenAtMs;
        internal const long FROZEN_MS = 120000;
        private static string _room = "";
        private static string _end;   // C.END_KINDS, or null: this seat saw the game over

        /// <summary>The end kind noted for the current game (read-only; the
        /// card draw record carries the same kind as the seat record).</summary>
        internal static string NotedEnd { get { return _end; } }

        /// <summary>Opened at the start of combat of a game with exactly two
        /// fighters (GameStateWatcher's start block); everything below resets.</summary>
        internal static void BeginGame(bool oneVOne, bool rankedAtStart)
        {
            try
            {
                ResetGame();
                _open = oneVOne;
                if (!_open) return;
                try { _room = PhotonNetwork.CurrentRoom != null ? (PhotonNetwork.CurrentRoom.Name ?? "") : ""; } catch { _room = ""; }
                _rankedAtStart = rankedAtStart;
                try { _masterAtStart = PhotonNetwork.IsMasterClient; } catch { _masterAtStart = false; }
                try { _localActor = PhotonNetwork.LocalPlayer != null ? PhotonNetwork.LocalPlayer.ActorNumber : 0; } catch { _localActor = 0; }
                ResolveOpponent();
                _sw0 = SwMs; _server0 = ServerNow(); _unscaled0 = Time.unscaledTime; _thAccum = 0;
                _clockAnchored = _server0 != 0;
            }
            catch { _open = false; }
        }

        /// <summary>Room exit: the window stops collecting and is frozen as it
        /// stands, so a game cut short by a leave or a drop still yields the
        /// record of what this seat collected up to the exit. The dispatch that
        /// takes it is GameStateWatcher's room-exit branch, or OnGameOver for a
        /// DC win; a frozen window that no dispatch takes within FROZEN_MS, or
        /// a dispatch for another room, never becomes a record.</summary>
        internal static void RoomExit()
        {
            try
            {
                if (_open) { _open = false; _frozen = true; _frozenAtMs = SwMs; }
                _ctxDepth = 0;
            }
            catch { }
        }

        /// <summary>How the game ended as this seat observed it (C.END_KINDS).
        /// The first kind noted for the game is kept.</summary>
        internal static void NoteEnd(string kind)
        {
            try
            {
                if ((_open || _frozen) && _end == null && C.IsEndKind(kind)) _end = kind;
            }
            catch { }
        }

        /// <summary>The noted end no longer holds (the other seat came back to
        /// the room); the game continues as if none was noted.</summary>
        internal static void ClearEnd()
        {
            try { if (_open) _end = null; } catch { }
        }

        private static void ResolveOpponent()
        {
            try
            {
                var others = RoomActors.OtherActiveFighters();
                _oppActor = others != null && others.Length == 1 && others[0] != null ? others[0].ActorNumber : 0;
            }
            catch { _oppActor = 0; }
        }

        // -- per-game state (all bounded) ------------------------------------------------

        private static C.AgeStats _ageView = new C.AgeStats(11), _ageRpc = new C.AgeStats(12), _ageHit = new C.AgeStats(13), _ageBlk = new C.AgeStats(14);
        // The collectors a dispatch hands to its capture (F4): never cleared,
        // only replaced, so a capture's references stay exactly as the game left them.
        private static C.SampleLog _samples = new C.SampleLog();
        private static C.Cadence _cad = new C.Cadence();
        private static C.EventList _blkSent = new C.EventList(), _hitRecv = new C.EventList(), _blkRecv = new C.EventList(), _hitSent = new C.EventList();
        private static readonly C.Ordinals _ordBlkSent = new C.Ordinals(), _ordBlkRecv = new C.Ordinals(), _ordHitRecv = new C.Ordinals(), _ordHitSent = new C.Ordinals();
        private static readonly C.HitWindow _winRecv = new C.HitWindow(), _winSent = new C.HitWindow();
        private static readonly long[] _shots = new long[3], _imp = new long[3], _dec = new long[2], _push = new long[7];
        private static HashSet<int> _impDistinct = new HashSet<int>();
        private const int IMP_DISTINCT_CAP = 8192;
        private static long _fireFloor, _blkFaults, _unpairBlocks, _unpairHits;
        private static int _lastFireStamp; private static bool _hasFireStamp;

        /// <summary>One block copy's history on this seat: the block that last
        /// reset its sinceBlock (B7), whether any reset ran this game, and the
        /// root stamp its Echo windows key under.</summary>
        private sealed class Copy
        {
            internal bool EverReset, HasLast, HasRoot;
            internal int LastTb, LastKind, LastOrd, RootTb;
            internal void Clear() { EverReset = HasLast = HasRoot = false; LastTb = LastKind = LastOrd = RootTb = 0; }
        }
        private static readonly Copy _mine = new Copy(), _opp = new Copy();

        // own window opened by a direct (non-RPC) Default block, waiting for
        // the stamp PUN writes into the outgoing RPCAO_DoBlock (B5)
        private static bool _ownOpenPending; private static int _ownOpenStamp;

        // the newest unblocked hit_recv entry whose damage envelope has not arrived
        private static long[] _awaitDamage;

        // own clocks
        private static long _sw0; private static int _server0; private static float _unscaled0; private static double _thAccum;
        private static bool _clockAnchored;
        private static long _rttSum, _rttN, _rttMax;
        private static long _offUpdates, _offStepMax; private static bool _offHas; private static int _offLast;
        private static long _nextSampleMs;
        private static bool _oppSampleDue;      // a 3 s sample fell due; its opponent half waits for no combat (F4)

        // the other seat's own statements, as relayed (snapshotted at most every 3 s, outside combat)
        private static string _oppBuild = ""; private static List<string> _oppKeys = new List<string>(); private static long[] _oppPub;

        private static void ResetGame()
        {
            _open = false; _oppActor = 0; _masterAtStart = false; _rankedAtStart = false;
            _frozen = false; _frozenAtMs = 0; _room = ""; _end = null;
            Handover();
            _ordBlkSent.Clear(); _ordBlkRecv.Clear(); _ordHitRecv.Clear(); _ordHitSent.Clear();
            _winRecv.Clear(); _winSent.Clear();
            Array.Clear(_shots, 0, 3); Array.Clear(_imp, 0, 3); Array.Clear(_dec, 0, 2); Array.Clear(_push, 0, 7);
            _fireFloor = _blkFaults = _unpairBlocks = _unpairHits = 0; _hasFireStamp = false;
            _mine.Clear(); _opp.Clear();
            _ownOpenPending = false; _awaitDamage = null;
            _rttSum = _rttN = _rttMax = 0; _offUpdates = _offStepMax = 0; _offHas = false;
            _oppBuild = ""; _oppKeys = new List<string>(); _oppPub = null;
            _nextSampleMs = 0; _oppSampleDue = false;
        }

        /// <summary>Fresh collectors in place of the game's: O(1), no copy and
        /// no clear (F4). The old ones belong to whoever took them (a capture),
        /// or to nobody.</summary>
        private static void Handover()
        {
            _ageView = new C.AgeStats(11); _ageRpc = new C.AgeStats(12); _ageHit = new C.AgeStats(13); _ageBlk = new C.AgeStats(14);
            _samples = new C.SampleLog(); _cad = new C.Cadence();
            _blkSent = new C.EventList(); _hitRecv = new C.EventList(); _blkRecv = new C.EventList(); _hitSent = new C.EventList();
            _impDistinct = new HashSet<int>();
            _oppKeys = new List<string>();
        }

        // -- RPC context (PhotonNetwork.ExecuteRpc prefix / finalizer) ---------------------

        private struct Ctx { internal int Stamp, ViewId, Sender; internal string Method; internal bool HasStamp, Consumed; }
        private const int CTX_CAP = 16;
        private static readonly Ctx[] _ctx = new Ctx[CTX_CAP];
        private static int _ctxDepth;
        private static readonly object K0 = (byte)0, K2 = (byte)2, K3 = (byte)3, K5 = (byte)5;

        /// <summary>Copies the envelope's view, stamp and method (the static
        /// rpcEvent is reused by any RPC sent inside this one, so nothing holds
        /// the table) and returns the depth to restore.</summary>
        internal static int EnterRpc(ExitGames.Client.Photon.Hashtable data, Photon.Realtime.Player sender)
        {
            int before = _ctxDepth;
            try
            {
                var c = new Ctx();
                if (data != null)
                {
                    object o = data[K0]; c.ViewId = o is int ? (int)o : 0;
                    o = data[K2]; c.HasStamp = o is int; c.Stamp = c.HasStamp ? (int)o : 0;
                    o = data[K5];
                    if (o is byte)
                    {
                        int i = (byte)o;
                        var list = PhotonNetwork.PhotonServerSettings != null ? PhotonNetwork.PhotonServerSettings.RpcList : null;
                        c.Method = list != null && i < list.Count ? list[i] : null;
                    }
                    else c.Method = data[K3] as string;
                }
                c.Sender = sender != null ? sender.ActorNumber : 0;
                if (before >= 0 && before < CTX_CAP) _ctx[before] = c;
                _ctxDepth = before + 1;
                if (_open && c.HasStamp && c.Sender != 0 && c.Sender == _oppActor) NoteRemoteRpc(c);
            }
            catch { }
            return before;
        }

        internal static void ExitRpc(int before)
        {
            if (before >= 0) _ctxDepth = before;
        }

        /// <summary>The innermost RPC frame when it runs `method` on `viewId`
        /// and is not yet taken by an earlier hook of this RPC.</summary>
        private static bool TopFrame(string a, string b, int viewId, bool take, out Ctx c)
        {
            c = default(Ctx);
            int top = _ctxDepth - 1;
            if (top < 0 || top >= CTX_CAP) return false;
            c = _ctx[top];
            if (c.Consumed || !c.HasStamp || c.ViewId != viewId || (c.Method != a && (b == null || c.Method != b))) return false;
            if (take) _ctx[top].Consumed = true;
            return true;
        }

        private static void NoteRemoteRpc(Ctx c)
        {
            int now = ServerNow();
            int age = C.WrapDiff(now, c.Stamp);
            _ageRpc.Add(age);
            _samples.Add(now, age, _offUpdates, false, c.Stamp, SwMs);
            if (c.Method == "RPCA_DoHit") _ageHit.Add(age);
            else if (c.Method == "RPCAO_DoBlock" || c.Method == "RPCA_DoBlock") _ageBlk.Add(age);
        }

        // -- view batches (NetworkReplicaDiagnostics.CommitTiming) ------------------------

        /// <summary>One player-stream batch from `actor` stamped `stamp` by its sender.</summary>
        internal static void NoteView(int actor, int stamp)
        {
            try
            {
                if (!_open || actor == 0 || actor != _oppActor) return;
                int now = ServerNow();
                int age = C.WrapDiff(now, stamp);
                long sw = SwMs;
                _ageView.Add(age);
                _samples.Add(now, age, _offUpdates, true, stamp, sw);
                _cad.Add(stamp, sw);
            }
            catch { }
        }

        // -- blocks -------------------------------------------------------------------------

        private static bool CopyOf(Component c, out bool mine, out bool opp, out CharacterData data)
        {
            mine = opp = false; data = null;
            if (c == null) return false;
            data = c.GetComponent<CharacterData>();
            var v = data != null ? data.view : null;
            if (v == null) return false;
            mine = v.IsMine;
            opp = !mine && _oppActor != 0 && v.OwnerActorNr == _oppActor;
            return mine || opp;
        }

        private struct BlockFrame { internal bool Live, Mine, Keyed, Recv; internal int Tb, Kind, Ord, Ta; internal bool OnlyEffects; internal Block B; }
        private const int BF_CAP = 8;
        private static readonly BlockFrame[] _bf = new BlockFrame[BF_CAP];
        private static int _bfDepth;

        /// <summary>Block.RPCA_DoBlock prefix: classifies the window (kind 0/1
        /// from the RPC that carried it, 3 for an Echo under its root, others
        /// unkeyed) and returns a frame for the finalizer, or -1.</summary>
        internal static int BlockEnter(Block b, bool firstBlock, BlockTrigger.BlockTriggerType trig, bool onlyEffects)
        {
            try
            {
                if (!_open || b == null) return -1;
                bool mine, opp; CharacterData data;
                if (!CopyOf(b, out mine, out opp, out data)) return -1;
                var f = new BlockFrame { Live = true, Mine = mine, B = b, OnlyEffects = onlyEffects };
                var copy = mine ? _mine : _opp;
                Ctx c;
                if (TopFrame("RPCAO_DoBlock", "RPCA_DoBlock", data.view.ViewID, true, out c))
                {
                    f.Keyed = true; f.Tb = c.Stamp; f.Kind = onlyEffects ? 1 : 0;
                    f.Ord = (mine ? _ordBlkSent : _ordBlkRecv).Next(f.Tb, f.Kind, 0);
                    if (f.Kind == 0) { copy.HasRoot = true; copy.RootTb = f.Tb; }
                    if (mine)
                    {
                        // the local leg of this seat's own All-target block RPC: the window opens now
                        _blkSent.Add(C.BlkSentEntry(f.Tb, f.Kind, f.Ord, C.WrapDiff(ServerNow(), f.Tb)));
                        if (f.Kind == 0) Admit(_winRecv, _hitRecv, f.Tb);
                    }
                    else { f.Recv = true; f.Ta = ServerNow(); }
                }
                else if (trig == BlockTrigger.BlockTriggerType.Echo)
                {
                    if (!copy.HasRoot) { _unpairBlocks++; f.Keyed = false; }
                    else
                    {
                        f.Keyed = true; f.Tb = copy.RootTb; f.Kind = 3;
                        f.Ord = (mine ? _ordBlkSent : _ordBlkRecv).Next(f.Tb, 3, 0);
                        if (mine) _blkSent.Add(C.BlkSentEntry(f.Tb, 3, f.Ord, C.WrapDiff(ServerNow(), f.Tb)));
                        else { f.Recv = true; f.Ta = ServerNow(); }
                    }
                }
                else if (mine && trig == BlockTrigger.BlockTriggerType.Default && firstBlock && !onlyEffects)
                {
                    // this seat's own block: the stamp arrives with the outgoing RPC
                    _ownOpenPending = true; _ownOpenStamp = ServerNow();
                    f.Keyed = false; f.Kind = -1;
                }
                else { _unpairBlocks++; f.Keyed = false; }
                int idx = _bfDepth;
                if (idx < 0 || idx >= BF_CAP) return -1;
                _bf[idx] = f; _bfDepth = idx + 1;
                return idx;
            }
            catch { return -1; }
        }

        /// <summary>Block.RPCA_DoBlock finalizer: `started` is whether this
        /// copy's sinceBlock reset ran in the synchronous part (B7).</summary>
        internal static void BlockExit(int idx)
        {
            try
            {
                if (idx < 0 || idx >= BF_CAP) return;
                var f = _bf[idx];
                _bfDepth = idx;
                if (!f.Live || f.B == null) return;
                bool started = !f.OnlyEffects && f.B.sinceBlock == 0f;
                var copy = f.Mine ? _mine : _opp;
                if (started)
                {
                    copy.EverReset = true;
                    if (f.Keyed) { copy.HasLast = true; copy.LastTb = f.Tb; copy.LastKind = f.Kind; copy.LastOrd = f.Ord; }
                    else if (f.Kind != -1) copy.HasLast = false;
                }
                if (f.Recv)
                {
                    _blkRecv.Add(C.BlkRecvEntry(f.Tb, f.Kind, f.Ord, f.Ta, started));
                    if (f.Kind == 0 && !started) _blkFaults++;
                    if (f.Kind == 0 || f.Kind == 3) Admit(_winSent, _hitSent, f.Tb);
                }
            }
            catch { }
        }

        /// <summary>PhotonNetwork.RPC postfix: this seat's own RPCAO_DoBlock to
        /// Others has just been stamped; the stamp is read from the envelope PUN
        /// filled (PhotonNetwork.rpcEvent, B5), never from a separate clock read.</summary>
        internal static void BlockSent(PhotonView view, string method, RpcTarget target)
        {
            try
            {
                if (!_open || !_ownOpenPending || method != "RPCAO_DoBlock" || target != RpcTarget.Others || view == null || !view.IsMine) return;
                var ev = PhotonNetwork.rpcEvent;
                if (ev == null) return;
                object v = ev[K0], s = ev[K2];
                if (!(v is int) || (int)v != view.ViewID || !(s is int)) return;
                int tb = (int)s;
                _ownOpenPending = false;
                int ord = _ordBlkSent.Next(tb, 0, 0);
                _blkSent.Add(C.BlkSentEntry(tb, 0, ord, C.WrapDiff(_ownOpenStamp, tb)));
                _mine.HasRoot = true; _mine.RootTb = tb;
                // the own copy's reset ran before this stamp existed; it now has a key
                if (_mine.EverReset) { _mine.HasLast = true; _mine.LastTb = tb; _mine.LastKind = 0; _mine.LastOrd = ord; }
                Admit(_winRecv, _hitRecv, tb);
            }
            catch { }
        }

        /// <summary>Block.DoBlock / TryBlockMe finalizers: a reset with no block
        /// key (a blocked impact), so the copy's last_* no longer names a block.</summary>
        internal static void UnkeyedReset(Block b)
        {
            try
            {
                if (!_open || b == null || b.sinceBlock != 0f) return;
                bool mine, opp; CharacterData data;
                if (!CopyOf(b, out mine, out opp, out data)) return;
                var copy = mine ? _mine : _opp;
                copy.EverReset = true; copy.HasLast = false;
            }
            catch { }
        }

        private static void Admit(C.HitWindow w, C.EventList list, int tb)
        {
            var a = w.Block(tb, 1);
            for (int i = 0; i < a.Count && i < C.HitWindow.PENDING_CAP; i++) list.Add(a[i]);
        }

        // -- hits ---------------------------------------------------------------------------

        private struct HitFrame { internal bool Live, Path1, HasStamp, Blocked, HasLast; internal int Pid, Stamp, LastTb, LastKind, LastOrd; internal long Since; }
        private const int HF_CAP = 8;
        private static readonly HitFrame[] _hf = new HitFrame[HF_CAP];
        private static int _hfDepth;

        /// <summary>ProjectileHit.RPCA_DoHit prefix, before the body can reset
        /// a block. Victim side: hit_recv. Shooter side: hit_sent, from this
        /// seat's own decision (path 0 through the hit RPC; path 1 waits in a
        /// frame for the damage envelope sent inside the body).
        ///
        /// Path 1 is ONE-SIDED by construction (ruling D2, amendment A2): the
        /// victim seat cannot tell a direct hit's damage envelope from any other
        /// damage envelope the other seat sends, so it never lists path 1 in
        /// hit_recv and counts such envelopes in unpair[1]. A hit_sent entry
        /// with path 1 is therefore the named one-sided kind, never a hit whose
        /// partner went missing; the path field itself is the label.</summary>
        internal static int HitEnter(ProjectileHit ph, int pid, int viewID, bool wasBlocked)
        {
            try
            {
                if (!_open || ph == null || viewID == -1) return -1;
                var pv = ph.GetComponent<PhotonView>();
                var target = PhotonNetwork.GetPhotonView(viewID);
                if (pv == null || target == null) return -1;
                var data = target.GetComponent<CharacterData>();
                if (data == null) return -1;
                Ctx c;
                bool rpc = TopFrame("RPCA_DoHit", null, pv.ViewID, true, out c);
                if (target.IsMine)
                {
                    if (!rpc || c.Sender == 0 || c.Sender != _oppActor) return -1;
                    _imp[0]++;
                    if (wasBlocked) _imp[1]++;
                    else if (_impDistinct.Count < IMP_DISTINCT_CAP) _impDistinct.Add(pid);
                    long own = C.SinceMs(_mine.EverReset, data.block != null ? data.block.sinceBlock : float.NaN);
                    var e = C.HitRecvEntry(0, c.Stamp, 0, _ordHitRecv.Next(0, c.Stamp, 0), ServerNow(), wasBlocked, false, own);
                    if (_winRecv.Offer(e, c.Stamp)) _hitRecv.Add(e);
                    _awaitDamage = wasBlocked ? null : e;
                    return -1;
                }
                if (!pv.IsMine || _oppActor == 0 || target.OwnerActorNr != _oppActor) return -1;
                long since = C.SinceMs(_opp.EverReset, data.block != null ? data.block.sinceBlock : float.NaN);
                if (rpc)
                {
                    _dec[0]++;
                    if (wasBlocked) _dec[1]++;
                    var e = C.HitSentEntry(0, c.Stamp, 0, _ordHitSent.Next(0, c.Stamp, 0), since, wasBlocked,
                                           _opp.HasLast, _opp.LastTb, _opp.LastKind, _opp.LastOrd);
                    if (_winSent.Offer(e, c.Stamp)) _hitSent.Add(e);
                    return -1;
                }
                int idx = _hfDepth;
                if (idx < 0 || idx >= HF_CAP) { _unpairHits++; return -1; }
                _hf[idx] = new HitFrame { Live = true, Path1 = true, Pid = pid, Since = since, Blocked = wasBlocked,
                                          HasLast = _opp.HasLast, LastTb = _opp.LastTb, LastKind = _opp.LastKind, LastOrd = _opp.LastOrd };
                _hfDepth = idx + 1;
                return idx;
            }
            catch { return -1; }
        }

        internal static void HitExit(int idx)
        {
            try
            {
                if (idx < 0 || idx >= HF_CAP) return;
                var f = _hf[idx];
                _hfDepth = idx;
                if (!f.Live) return;
                if (!f.HasStamp) { _unpairHits++; return; }
                var e = C.HitSentEntry(1, f.Stamp, f.Pid, _ordHitSent.Next(1, f.Stamp, f.Pid), f.Since, f.Blocked,
                                       f.HasLast, f.LastTb, f.LastKind, f.LastOrd);
                if (_winSent.Offer(e, f.Stamp)) _hitSent.Add(e);
            }
            catch { }
        }

        /// <summary>HealthHandler.RPCA_SendTakeDamage prefix: whether the
        /// damage this envelope carries passes the game's own predicate here,
        /// read before the body: RPCA_SendTakeDamage returns at once on zero
        /// damage, and TakeDamage applies only nonzero damage to a seat that
        /// is playing, simulated and not dead (the RPC path passes ignoreBlock,
        /// so the block term never applies). `nonzero` is the hook's
        /// `damage != Vector2.zero`.</summary>
        internal static bool DamageGate(HealthHandler hh, bool nonzero)
        {
            try
            {
                if (!nonzero) return false;
                var d = hh != null ? hh.GetComponent<CharacterData>() : null;
                return d != null && d.isPlaying && !d.dead && d.playerVel != null && d.playerVel.simulated;
            }
            catch { return false; }
        }

        /// <summary>HealthHandler.RPCA_SendTakeDamage finalizer. On the victim:
        /// marks dmg on the hit it follows (1 only when the prefix's predicate
        /// held AND the method completed without an exception of its own), or
        /// counts a damage envelope no hit RPC keys (unpair[1]). On the
        /// shooter: the local leg inside a direct impact gives path 1 its
        /// stamp.</summary>
        internal static void DamageArrived(HealthHandler hh, bool gate, bool completed)
        {
            try
            {
                if (!_open || hh == null) return;
                var d = hh.GetComponent<CharacterData>();
                if (d == null || d.view == null) return;
                Ctx c;
                if (!TopFrame("RPCA_SendTakeDamage", null, d.view.ViewID, false, out c)) return;
                if (d.view.IsMine)
                {
                    if (c.Sender == 0 || c.Sender != _oppActor) return;
                    if (_awaitDamage != null) { _awaitDamage[6] = gate && completed ? 1 : 0; _awaitDamage = null; }
                    else _unpairHits++;
                    return;
                }
                if (c.Sender != _localActor || d.view.OwnerActorNr != _oppActor) return;
                int top = _hfDepth - 1;
                if (top >= 0 && top < HF_CAP && _hf[top].Live && _hf[top].Path1 && !_hf[top].HasStamp)
                {
                    _hf[top].HasStamp = true; _hf[top].Stamp = c.Stamp;
                }
            }
            catch { }
        }

        // -- shots ---------------------------------------------------------------------------

        /// <summary>A projectile init RPC from the other seat (kind 0 ammo, 1
        /// no-ammo, 2 separate gun). For ammo shots of a single-shot gun,
        /// fire_floor counts gaps between consecutive distinct sender stamps
        /// shorter than the gun's cooldown as this seat's copy of the gun holds
        /// it (usedCooldown / attackSpeedMultiplier). A count, nothing more.</summary>
        internal static void ShotArrived(Component init, int kind)
        {
            try
            {
                if (!_open || init == null) return;
                var pv = init.GetComponent<PhotonView>();
                if (pv == null) return;
                Ctx c;
                string m = kind == 0 ? "RPCA_Init" : (kind == 1 ? "RPCA_Init_noAmmoUse" : "RPCA_Init_SeparateGun");
                if (!TopFrame(m, null, pv.ViewID, false, out c) || c.Sender == 0 || c.Sender != _oppActor) return;
                _shots[kind < 0 || kind > 2 ? 2 : kind]++;
                if (kind != 0) return;
                if (_hasFireStamp && c.Stamp != _lastFireStamp)
                {
                    int gap = C.WrapDiff(c.Stamp, _lastFireStamp);
                    var p = PlayerManager.instance != null ? PlayerManager.instance.GetPlayerWithActorID(c.Sender) : null;
                    var gun = p != null && p.data != null && p.data.weaponHandler != null ? p.data.weaponHandler.gun : null;
                    if (gap > 0 && gun != null && gun.bursts <= 1 && gun.timeBetweenBullets == 0f && !gun.useCharge
                        && gun.numberOfProjectiles <= 1 && gun.attackSpeedMultiplier > 0f)
                    {
                        double floorMs = gun.usedCooldown / gun.attackSpeedMultiplier * 1000.0;
                        if (gap < floorMs) _fireFloor++;
                    }
                }
                _hasFireStamp = true; _lastFireStamp = c.Stamp;
            }
            catch { }
        }

        /// <summary>From HitEvidence.PointEnd: one point's pairing of the
        /// damage and knockback messages the other seat sent this seat.</summary>
        internal static void AddPush(int actor, int dmg, int force, int paired, int dmgAlone, int forceAlone, int inert, int dot)
        {
            try
            {
                if (!_open || actor == 0 || actor != _oppActor) return;
                _push[0] += dmg; _push[1] += force; _push[2] += paired; _push[3] += dmgAlone;
                _push[4] += forceAlone; _push[5] += inert; _push[6] += dot;
            }
            catch { }
        }

        // -- own clocks and the send loop (the host's per-frame tick) --------------------------

        private static FieldInfo _peerField, _offField;
        private static bool _offUnreadable;

        /// <summary>From Plugin's persistent tick, ABOVE its modDisabled return
        /// (queued records pump whatever the mod's state; F5). Own clocks while
        /// a game is open; then, only while no battle is live in THIS frame
        /// (F3: read here, not from a flag refreshed later in the frame), the
        /// work the hooks and the dispatch deferred (F4): the opponent sample,
        /// the answer of the request in flight, the pending record builds,
        /// and one send.</summary>
        internal static void Tick()
        {
            try
            {
                long now = SwMs;
                if (_open)
                {
                    _thAccum += TimeHandler.deltaTime;
                    ReadOffset();
                    if (now >= _nextSampleMs)
                    {
                        _nextSampleMs = now + 3000;
                        SamplePing();
                        _oppSampleDue = true;
                    }
                }
                if (CombatLive()) return;       // before any load, save, attempt accounting or request setup
                if (_open && _oppSampleDue) { _oppSampleDue = false; SampleOpponent(); }
                TakeAnswer(now);
                BuildCaptures(false);
                Pump(now);
            }
            catch { }
        }

        /// <summary>Whether a battle is live in the CURRENT frame: the game's
        /// own GameManager.battleOngoing read now (FfaMode and vanilla both
        /// write it), or the diagnostics flag (the spectator path drives it).
        /// Either one live is live.</summary>
        internal static bool CombatLive()
        {
            bool live = false;
            try { live = GameManager.instance != null && GameManager.instance.battleOngoing; } catch { }
            try { live = live || NetworkReplicaDiagnostics.BattleActive; } catch { }
            return live;
        }

        private static void ReadOffset()
        {
            if (_offUnreadable) return;
            try
            {
                var peer = PhotonNetwork.NetworkingClient != null ? PhotonNetwork.NetworkingClient.LoadBalancingPeer : null;
                if (peer == null) return;
                if (_peerField == null)
                {
                    _peerField = AccessTools.Field(typeof(ExitGames.Client.Photon.PhotonPeer), "peerBase");
                    _offField = _peerField != null ? AccessTools.Field(_peerField.FieldType, "serverTimeOffset") : null;
                    if (_offField == null) { _offUnreadable = true; return; }
                }
                object pb = _peerField.GetValue(peer);
                if (pb == null) return;
                int v = (int)_offField.GetValue(pb);
                if (_offHas && v != _offLast)
                {
                    _offUpdates++;
                    long step = Math.Abs((long)C.WrapDiff(v, _offLast));
                    if (step > _offStepMax) _offStepMax = step;
                }
                _offHas = true; _offLast = v;
            }
            catch { _offUnreadable = true; }
        }

        /// <summary>The 3 s round-trip sample: one call, taken in combat too.</summary>
        private static void SamplePing()
        {
            try
            {
                int ping = PhotonNetwork.GetPing();
                if (ping >= 0) { _rttSum += ping; _rttN++; if (ping > _rttMax) _rttMax = ping; }
            }
            catch { }
        }

        private const int OPP_KEYS_SCAN_CAP = 256;

        /// <summary>The other seat's own statements (its property keys, build
        /// and published stats): a room lookup and a property enumeration
        /// (capped at OPP_KEYS_SCAN_CAP), so only the tick runs it, outside
        /// combat (F4), at most once per 3 s sample.</summary>
        private static void SampleOpponent()
        {
            try
            {
                if (_oppActor == 0) ResolveOpponent();
                var room = PhotonNetwork.CurrentRoom;
                var p = room != null && _oppActor != 0 ? room.GetPlayer(_oppActor) : null;
                var cp = p != null ? p.CustomProperties : null;
                if (cp == null) return;
                var keys = new List<string>();
                int seen = 0;
                foreach (object k in cp.Keys)
                {
                    if (++seen > OPP_KEYS_SCAN_CAP) break;
                    var s = k as string; if (s != null) keys.Add(s);
                }
                _oppKeys = keys;
                object b = cp[PeerBuildCore.BuildProp];
                if (b is string) _oppBuild = (string)b;
                object g = cp["cr_gstats"];
                if (g is string) { var pub = ParsePub((string)g); if (pub != null) _oppPub = pub; }
            }
            catch { }
        }

        /// <summary>other_pub from the other seat's cr_gstats ("fired|hit|
        /// blkAct|blkSucc|keys|activeSecs|fps|...|rtt(12th)"), or null.</summary>
        internal static long[] ParsePub(string raw)
        {
            var p = raw.Split('|');
            if (p.Length < 7) return null;
            long fired, hit, act, succ, fps, rtt = 0;
            if (!Num(p[0], out fired) || !Num(p[1], out hit) || !Num(p[2], out act) || !Num(p[3], out succ) || !Num(p[6], out fps)) return null;
            if (p.Length >= 12 && !Num(p[11], out rtt)) rtt = 0;
            return new long[] { fps, rtt, fired, hit, act, succ };
        }

        private static bool Num(string s, out long v)
        {
            return long.TryParse(s, NumberStyles.None, CultureInfo.InvariantCulture, out v) && v >= 0;
        }

        private static long[] ClockPpm()
        {
            if (!_clockAnchored) return null;
            long dSw = SwMs - _sw0;
            int server = ServerNow();
            if (dSw < 10000 || server == 0) return null;
            double dServer = C.WrapDiff(server, _server0);
            double dUnity = (Time.unscaledTime - _unscaled0) * 1000.0;
            double dTh = _thAccum * 1000.0;
            return new long[] { Ppm(dServer, dSw), Ppm(dUnity, dSw), Ppm(dTh, dSw) };
        }

        private static long Ppm(double d, long dSw)
        {
            double ppm = (d - dSw) * 1e6 / dSw;
            if (double.IsNaN(ppm)) return 0;
            return C.Clamp((long)Math.Round(ppm), -1000000, 1000000);
        }

        // -- build identity (hashed off the main thread at boot) -------------------------------

        /// <summary>The identity state while the boot hash still runs. In memory
        /// only: a build waits until both identities are completed (F7), so it
        /// is never written into a record.</summary>
        internal const string ID_PENDING = "pending";

        private static volatile string _dllSha = "", _dllState = ID_PENDING, _gameSha = "", _gameState = ID_PENDING;
        private static string _ownPath, _gamePath;
        private static bool _hashStarted;
        private static string _compat = "not_run";

        /// <summary>The game DLL's hash and its state, as hashed at boot
        /// (read-only; the card draw record's deal-profile id). The state is
        /// ID_PENDING until the hash completed.</summary>
        internal static string GameDllSha { get { return _gameSha; } }
        internal static string GameDllState { get { return _gameState; } }

        /// <summary>This mod DLL's own hash and its state, as hashed at boot
        /// (read-only; the card draw record's dealer-implementation identity,
        /// CD-M5). ID_PENDING until the hash completed.</summary>
        internal static string OwnDllSha { get { return _dllSha; } }
        internal static string OwnDllState { get { return _dllState; } }

        /// <summary>Both identities completed: ok, read_failed, or no_location
        /// for an empty assembly location.</summary>
        internal static bool IdentityReady { get { return _dllState != ID_PENDING && _gameState != ID_PENDING; } }

        /// <summary>At boot, and from a build that finds the identity still
        /// pending (a no-op once started). An EMPTY assembly location is final
        /// at once as no_location; a location that cannot even be asked for is
        /// read_failed; every other location is hashed on a background thread
        /// to ok or read_failed. Nothing on the game's thread waits for it.</summary>
        internal static void StartHashing()
        {
            try
            {
                if (_hashStarted) return;
                _hashStarted = true;
                _ownPath = LocationOf(typeof(SeatEvidence));
                _gamePath = LocationOf(typeof(GM_ArmsRace));
                if (_ownPath == null) { _dllSha = ""; _dllState = "read_failed"; }
                else if (_ownPath.Length == 0) { _dllSha = ""; _dllState = "no_location"; }
                if (_gamePath == null) { _gameSha = ""; _gameState = "read_failed"; }
                else if (_gamePath.Length == 0) { _gameSha = ""; _gameState = "no_location"; }
                if (IdentityReady) return;
                var t = new Thread(HashPending);
                t.IsBackground = true;
                t.Start();
            }
            catch { FailPending(); }
        }

        /// <summary>The assembly's location: "" when it has none, null when
        /// asking for it failed.</summary>
        private static string LocationOf(Type t)
        {
            try { return t.Assembly.Location ?? ""; } catch { return null; }
        }

        private static void HashPending()
        {
            try
            {
                string s, st;
                if (_dllState == ID_PENDING) { Hash(_ownPath, out s, out st); _dllSha = s; _dllState = st; }
                if (_gameState == ID_PENDING) { Hash(_gamePath, out s, out st); _gameSha = s; _gameState = st; }
            }
            catch { FailPending(); }
        }

        private static void FailPending()
        {
            if (_dllState == ID_PENDING) { _dllSha = ""; _dllState = "read_failed"; }
            if (_gameState == ID_PENDING) { _gameSha = ""; _gameState = "read_failed"; }
        }

        /// <summary>The quitting path only (no later frame comes): a hash still
        /// running is completed on this thread. Both threads compute the same
        /// value from the same file.</summary>
        internal static void CompleteIdentityNow()
        {
            try { StartHashing(); HashPending(); } catch { FailPending(); }
        }

        private static void Hash(string path, out string sha, out string state)
        {
            sha = ""; state = "no_location";
            if (path == null) { state = "read_failed"; return; }
            if (path.Length == 0) return;
            try { sha = C.Sha256Hex(File.ReadAllBytes(path)); state = "ok"; }
            catch { sha = ""; state = "read_failed"; }
        }

        /// <summary>From Plugin's other-plug-in check: "pass" only from a
        /// completed run; "not_run" from its catch arm; "finding" when it found
        /// another plug-in (the record is never built then: the mod disables).
        /// finding / not_run also queue the compat outcome (contract 5.1).</summary>
        internal static void NoteCompat(string outcome, IList<string> guids)
        {
            try
            {
                _compat = outcome == "pass" ? "pass" : "not_run";
                if (outcome == "finding" || outcome == "not_run")
                {
                    _compatOutcome = outcome;
                    _compatPlugins = C.CompatPlugins(guids);
                }
            }
            catch { }
        }

        private static string _compatOutcome;
        private static List<string> _compatPlugins;
        private static long _compatNextTryMs;

        private static string OwnSteamId()
        {
            try { return Steamworks.SteamUser.GetSteamID().m_SteamID.ToString(CultureInfo.InvariantCulture); } catch { return ""; }
        }

        /// <summary>Above Plugin's modDisabled return, outside combat: once this
        /// seat's Steam id is known, the pending compat outcome is signed and
        /// persisted; it counts as queued only when the queue file holding it
        /// replaced the old one (F8), otherwise it is kept and tried again
        /// every 5 s. On a seat the finding has disabled, the session attempt
        /// then runs (DisabledSeatSession).</summary>
        internal static void CompatTick()
        {
            try
            {
                if (CombatLive()) return;
                if (_compatOutcome != null && SwMs >= _compatNextTryMs)
                {
                    string seat = OwnSteamId();
                    if (C.IsSteamId(seat))
                    {
                        string outcome = _compatOutcome;
                        string sig = ApiClient.SeatEvidenceSig(C.CompatCanonical(seat, outcome, _compatPlugins));
                        string body = C.CompatBody(seat, outcome, _compatPlugins, sig);
                        if (body == null)
                        {
                            _compatOutcome = null;
                            Plugin.Log.LogWarning(TAG + " compat outcome not queued: a field is outside its bound");
                        }
                        else if (Enqueue("c", body))
                        {
                            _compatOutcome = null;
                            Plugin.Log.LogInfo(TAG + " compat outcome queued: " + outcome + " plugins=" + _compatPlugins.Count.ToString(CultureInfo.InvariantCulture));
                        }
                        else _compatNextTryMs = SwMs + 5000;
                    }
                }
                DisabledSeatSession();
            }
            catch { }
        }

        // -- the disabled seat's session (V1 6.4; F5) ------------------------------------------

        private static int _sendPhase;          // 0 not started, 1 obtaining a session, 2 finished for this launch
        private static long _sendStartMs, _nextAuthMs;

        /// <summary>A seat the other-plug-in check disabled never initialises
        /// the api, so nothing there obtains a session. When such a seat holds
        /// ANY queued request (its compat outcome, or game records an earlier
        /// launch queued) and data consent, this makes ONE bounded attempt
        /// (C.COMPAT_SEND_LIMIT_MS) per launch to obtain one: it points the api
        /// at the configured base without starting any of its loops and asks
        /// for a session through the existing Steam ticket exchange for this
        /// seat's own id. The sends themselves are the queue's own pump in
        /// Tick, under exactly the conditions of an enabled seat: consent, a
        /// session, retry timing and no live combat. Without consent nothing
        /// is set or asked; past the bound everything stays queued.</summary>
        private static void DisabledSeatSession()
        {
            if (_sendPhase == 2 || !Plugin.modDisabled) return;
            if (!Load()) return;
            bool queued = _queue.Count > 0;
            if (_sendPhase == 0)
            {
                if (!queued) return;
                _sendPhase = 1; _sendStartMs = SwMs; _nextAuthMs = 0;
                if (Plugin.DataConsentGranted)
                {
                    try { ApiClient.SeatEvidenceCompatBase(Plugin.ApiBaseUrl.Value); } catch { }
                    try { SteamAuth.FallbackIdentity = OwnSteamId(); } catch { }
                }
            }
            var step = C.CompatSenderStep(Plugin.modDisabled, Plugin.DataConsentGranted, queued, !string.IsNullOrEmpty(SteamAuth.SessionToken), SwMs - _sendStartMs);
            switch (step)
            {
                case C.SendStep.Auth:
                    if (SwMs >= _nextAuthMs) { _nextAuthMs = SwMs + 1000; SteamAuth.MaybeRefresh(); }
                    return;
                case C.SendStep.Post:
                    _sendPhase = 2;
                    _nextPumpMs = 0;
                    Plugin.Log.LogInfo(TAG + " session ready: queued requests send while the mod stays disabled");
                    return;
                case C.SendStep.GiveUp:
                    _sendPhase = 2;
                    Plugin.Log.LogInfo(TAG + " no session within " + (C.COMPAT_SEND_LIMIT_MS / 1000).ToString(CultureInfo.InvariantCulture) + " s: queued requests kept for the next launch");
                    return;
                case C.SendStep.NoConsent:
                    _sendPhase = 2;
                    Plugin.Log.LogInfo(TAG + " queued requests not sent: no data consent");
                    return;
                default:
                    _sendPhase = 2;
                    return;
            }
        }

        private static void Foreign(out long asm, out long owners)
        {
            asm = 0; owners = 0;
            try
            {
                string own = typeof(SeatEvidence).Assembly.Location ?? "";
                string plugins = Paths.PluginPath ?? "", patchers = Paths.PatcherPluginPath ?? "";
                foreach (var a in AppDomain.CurrentDomain.GetAssemblies())
                {
                    string loc = "";
                    try { if (!a.IsDynamic) loc = a.Location ?? ""; } catch { }
                    if (loc.Length == 0 || string.Equals(loc, own, StringComparison.OrdinalIgnoreCase)) continue;
                    if ((plugins.Length > 0 && loc.StartsWith(plugins, StringComparison.OrdinalIgnoreCase))
                        || (patchers.Length > 0 && loc.StartsWith(patchers, StringComparison.OrdinalIgnoreCase)))
                        asm++;
                }
            }
            catch { }
            try
            {
                var seen = new HashSet<string>();
                var methods = new MethodBase[]
                {
                    AccessTools.Method(typeof(ProjectileHit), "RPCA_DoHit"), AccessTools.Method(typeof(ProjectileHit), "Hit"),
                    AccessTools.Method(typeof(HealthHandler), "RPCA_SendTakeDamage"), AccessTools.Method(typeof(HealthHandler), "RPCA_SendTakeForce"),
                    AccessTools.Method(typeof(HealthHandler), "CallTakeDamage"), AccessTools.Method(typeof(Block), "RPCA_DoBlock"),
                    AccessTools.Method(typeof(Block), "IsBlocking"), AccessTools.Method(typeof(Block), "TryBlock"),
                };
                foreach (var m in methods)
                {
                    if (m == null) continue;
                    var info = Harmony.GetPatchInfo(m);
                    if (info == null) continue;
                    foreach (var o in info.Owners) if (o != Plugin.ModId) seen.Add(o);
                }
                owners = seen.Count;
            }
            catch { }
        }

        // -- the record: captured at the dispatch, built on a later tick (F4) ------------------

        /// <summary>A game's record as the dispatch captured it (F4): the
        /// scalars and fixed-size counters copied, and the game's own variable
        /// collectors (age reservoirs, the sample log, the cadence, the event
        /// lists, the other seat's key list) TAKEN, not copied: the dispatch
        /// hands fresh ones to the live state, so these are never written
        /// again. Every aggregation over them (percentiles, age buckets, drift,
        /// cadence, the other seat's capabilities, the list copies), the
        /// key and seat id validation, the build identity, the foreign scan,
        /// the budget, the signature, the queue file and the log line are the
        /// build's, on the tick.</summary>
        private sealed class Capture
        {
            internal C.Record R;
            internal string Seat, Other, Attach, Stable, Text, Env;
            internal bool FromToken, Aggregated;
            internal C.AgeStats AgeView, AgeRpc, AgeHit, AgeBlk;
            internal C.SampleLog Samples;
            internal C.Cadence Cad;
            internal C.EventList BlkSent, HitRecv, BlkRecv, HitSent;
            internal List<string> OppKeys;
        }

        private const int CAPTURE_CAP = 4;
        private static readonly List<Capture> _captures = new List<Capture>();
        private static long _nextCaptureTryMs;
        private static bool _captureFailLogged;

        // fixed refusal texts the dispatch notes for the tick to log
        private const int NOTES_CAP = 8;
        private static readonly string[] _notes = new string[NOTES_CAP];
        private static int _noteCount;

        private static void Note(string text) { if (_noteCount < NOTES_CAP) _notes[_noteCount++] = text; }

        private static void DrainNotes()
        {
            int n = _noteCount;
            _noteCount = 0;
            for (int i = 0; i < n; i++)
            {
                try { Plugin.Log.LogWarning(TAG + _notes[i]); } catch { }
                _notes[i] = null;
            }
        }

        /// <summary>From OnGameOver, after ApiClient.ReportMatch returned; from
        /// GameStateWatcher's room-exit branch for a game cut short; from the
        /// quit hook for a game still live while the game closes. Ranked 1v1
        /// games only, both seats. Takes the live window, or a frozen one of
        /// the same room no older than FROZEN_MS, and CAPTURES it in O(1):
        /// scalars and fixed-size counters copied, the variable collectors
        /// taken by reference and replaced (Handover), so nothing in this call
        /// grows with the game's length (F4). It validates nothing that needs
        /// a loop, aggregates nothing, logs, scans, budgets and touches no
        /// file; the build (BuildCaptures) does all of that on the next tick
        /// outside combat, or on the quitting path (FlushOnQuit). The end kind
        /// this seat noted rides in the record; none means it saw the game
        /// over.</summary>
        internal static void Dispatch(string seat, string other, string attach, int roundsSelf, int roundsOther, bool rankedNow)
        {
            try
            {
                bool live = _open;
                bool frozen = !live && _frozen && SwMs - _frozenAtMs <= FROZEN_MS
                              && _room.Length > 0 && attach != null && attach.StartsWith(_room + "_", StringComparison.Ordinal);
                if (!live && !frozen) return;
                _open = false; _frozen = false;
                if (!rankedNow) return;
                bool fromToken;
                int t0 = GameStateWatcher.SeatEvidenceT0(out fromToken);
                var r = new C.Record
                {
                    T0 = t0, T0Src = fromToken ? "m" : "o", Master = _masterAtStart ? 1 : 0, Ranked = _rankedAtStart ? 1 : 0,
                    RoundsSelf = roundsSelf, RoundsOther = roundsOther, End = _end,
                    Compat = _compat,
                    RttAvg = _rttN > 0 ? _rttSum / _rttN : 0, RttMax = _rttMax,
                    OffsetUpdates = _offUpdates, OffsetStepMax = _offStepMax,
                    ClkPpm = ClockPpm(), MonoSend = SwMs,
                    OtherBuildV = _oppBuild, OtherPub = _oppPub,
                    FireFloor = _fireFloor, BlkFaults = _blkFaults, UnpairBlocks = _unpairBlocks, UnpairHits = _unpairHits,
                };
                NetworkReplicaDiagnostics.ObsSnapshot o;
                if (NetworkReplicaDiagnostics.TryGetOpponentGameObs(out o))
                    r.Obs = new long[] { o.Gap300, o.Gap750, o.Gap1500, o.MaxGapMs, o.Excess150, o.MaxExcessMs,
                                         o.PayloadEqualGaps, o.ReceiverFrameGaps, o.PhoenixIntervals, o.Batches };
                Array.Copy(_shots, r.Shots, 3);
                r.Imp = new long[] { _imp[0], _imp[1], _impDistinct.Count };
                Array.Copy(_dec, r.Dec, 2); Array.Copy(_push, r.Push, 7);
                r.Omit = new long[] { _blkSent.Omitted, _hitRecv.Omitted, _blkRecv.Omitted, _hitSent.Omitted, 0 };
                var cap = new Capture
                {
                    R = r, Seat = seat, Other = other, Attach = attach, FromToken = fromToken,
                    AgeView = _ageView, AgeRpc = _ageRpc, AgeHit = _ageHit, AgeBlk = _ageBlk, Samples = _samples, Cad = _cad,
                    BlkSent = _blkSent, HitRecv = _hitRecv, BlkRecv = _blkRecv, HitSent = _hitSent, OppKeys = _oppKeys,
                };
                Handover();
                if (_captures.Count >= CAPTURE_CAP)
                {
                    _captures.RemoveAt(0);
                    Note(" a captured record was dropped before it was persisted: too many waiting");
                }
                _captures.Add(cap);
                _nextCaptureTryMs = 0;
            }
            catch
            {
                Note(" no record: the capture failed");
            }
        }

        /// <summary>The build's first step, on the tick (F4): the game key and
        /// seat ids validated, the build tuple split, and every aggregation
        /// over the collectors the dispatch took. False: outside the contract,
        /// no record.</summary>
        private static bool Aggregate(Capture c)
        {
            if (c.Aggregated) return true;
            string stable = StableOf(c.Attach);
            if (stable == null || !C.IsSteamId(c.Seat) || !C.IsSteamId(c.Other)) return false;
            var r = c.R;
            int t0 = r.T0;
            string build = null;
            try { build = PeerBuild.BuildValue(); } catch { }      // the build lookup (reflection) is the tick's (F4)
            r.Build = C.SplitBuild(build) ?? new[] { "", "", "" };
            r.AgeView = c.AgeView.Four(); r.AgeRpc = c.AgeRpc.Four(); r.AgeHit = c.AgeHit.Three(); r.AgeBlk = c.AgeBlk.Three();
            r.AgeB = c.Samples.AgeBuckets(t0); r.DriftV = c.Samples.DriftTriple(t0); r.Cad = c.Cad.Five();
            r.OtherCapsV = C.OtherCaps(c.OppKeys);
            r.BlkSent = new List<long[]>(c.BlkSent.Items); r.HitRecv = new List<long[]>(c.HitRecv.Items);
            r.BlkRecv = new List<long[]>(c.BlkRecv.Items); r.HitSent = new List<long[]>(c.HitSent.Items);
            c.Stable = stable; c.Aggregated = true;
            c.AgeView = c.AgeRpc = c.AgeHit = c.AgeBlk = null; c.Samples = null; c.Cad = null;
            c.BlkSent = c.HitRecv = c.BlkRecv = c.HitSent = null; c.OppKeys = null;
            return true;
        }

        /// <summary>Builds and persists the captured records: from Tick (outside
        /// combat) or from FlushOnQuit (quitting = true). A build waits for a
        /// completed build identity (F7; the quitting path completes it on its
        /// own thread). On the tick a record is reported as queued only after
        /// the queue file holding it replaced the old one (F8); until then it
        /// stays captured, its built bytes kept, and is tried again every 5 s.
        /// On the quitting path it never enters the queue (F3): it is written
        /// to its own closing file (SpoolClosing), which the next launch's
        /// first load, outside combat, moves into the queue.</summary>
        private static void BuildCaptures(bool quitting)
        {
            DrainNotes();
            if (_captures.Count == 0) return;
            if (!quitting && SwMs < _nextCaptureTryMs) return;
            if (!IdentityReady)
            {
                if (quitting) CompleteIdentityNow();
                else { StartHashing(); return; }
            }
            int i = 0;
            while (i < _captures.Count)
            {
                var c = _captures[i];
                try
                {
                    if (c.Env == null)
                    {
                        if (!Aggregate(c))
                        {
                            _captures.RemoveAt(i);
                            Plugin.Log.LogWarning(TAG + " no record: game key or seat ids outside the contract");
                            continue;
                        }
                        var r = c.R;
                        r.DllSha = _dllSha; r.DllState = _dllState; r.GameDllSha = _gameSha; r.GameDllState = _gameState;
                        long fa, fo; Foreign(out fa, out fo); r.ForeignAsm = fa; r.ForeignOwners = fo;
                        string text = C.Budget(r.ToObj());
                        string sig = ApiClient.SeatEvidenceSig(C.Canonical(c.Seat, c.Other, c.Stable, c.Attach, text));
                        string env = C.Envelope(c.Seat, c.Other, c.Stable, c.Attach, text, sig);
                        if (env == null)
                        {
                            _captures.RemoveAt(i);
                            Plugin.Log.LogWarning(TAG + " no record: the envelope is outside the contract");
                            continue;
                        }
                        c.Text = text; c.Env = env;
                    }
                    bool persisted = quitting ? SpoolClosing("e", c.Env) : Enqueue("e", c.Env);
                    if (!persisted)
                    {
                        _nextCaptureTryMs = SwMs + 5000;
                        if (!_captureFailLogged)
                        {
                            _captureFailLogged = true;
                            Plugin.Log.LogWarning(TAG + " record not persisted yet (the queue file was not replaced): kept and tried again");
                        }
                        return;
                    }
                    _captures.RemoveAt(i);
                    _captureFailLogged = false;
                    var q = c.R;
                    Plugin.Log.LogInfo(TAG + (quitting ? " record kept for the next launch: " : " record queued: ")
                        + c.Text.Length.ToString(CultureInfo.InvariantCulture) + " bytes, lists "
                        + q.BlkSent.Count + "/" + q.HitRecv.Count + "/" + q.BlkRecv.Count + "/" + q.HitSent.Count
                        + ", unpaired " + q.UnpairBlocks + "/" + q.UnpairHits + ", t0 " + (c.FromToken ? "m" : "o")
                        + ", end " + (q.End ?? "game_over"));
                }
                catch (Exception ex)
                {
                    _captures.RemoveAt(i);
                    try { Plugin.Log.LogWarning(TAG + " no record: " + ex.GetType().Name); } catch { }
                }
            }
        }

        /// <summary>Application.quitting, after GameStateWatcher's quit hook
        /// captured a game still live: every captured record is built now, on
        /// this thread, because no later frame comes, and written to its own
        /// closing file, NOT the queue (F3): no queue load, save, attempt or
        /// request happens here, whether or not a battle is live in this frame.
        /// The next launch's first queue load moves it into the queue.</summary>
        internal static void FlushOnQuit()
        {
            try { BuildCaptures(true); } catch { }
        }

        /// <summary>The stable game key: the attach key without its "_r" + 1-2
        /// digit suffix, or null when it does not have that shape.</summary>
        internal static string StableOf(string attach)
        {
            if (attach == null) return null;
            int i = attach.LastIndexOf("_r", StringComparison.Ordinal);
            if (i <= 0) return null;
            string stable = attach.Substring(0, i);
            return C.IsAttachKey(stable, attach) ? stable : null;
        }

        // -- the queue (its own persisted file; see the build notes for why) ------------------

        private const int QUEUE_CAP = 64;
        private static readonly List<C.Pending> _queue = new List<C.Pending>();
        private static bool _loaded, _inFlight;
        // a write that did not replace the primary (F8): memory may be older or
        // newer than the newest whole copy on disk, so the next load adopts that copy
        private static bool _stale;
        // closing files the first load found and has not yet seen promoted (F3)
        private static bool _spoolChecked;
        // closing files a pass kept because the saved queue did not hold every
        // request they carry (F8): left for the next launch's first load
        private static readonly HashSet<string> _spoolKept = new HashSet<string>(StringComparer.Ordinal);
        private static long _nextPumpMs, _gen;

        private static string QueuePath() { return Path.Combine(Paths.ConfigPath, "CompetitiveRounds.seat-evidence.jsonl"); }

        private const string SPOOL_PREFIX = "CompetitiveRounds.seat-evidence.closing-";
        private const int SPOOL_CAP = 16;
        private static int _spoolSeq;

        private static long UnixNow() { return DateTimeOffset.UtcNow.ToUnixTimeSeconds(); }

        /// <summary>The identity of a queued request: its route and its frozen
        /// bytes. Every lookup and every merge goes by it, never by the object.</summary>
        private static int Find(List<C.Pending> list, string route, string body)
        {
            for (int i = 0; i < list.Count; i++)
                if (list[i].Route == route && list[i].Body == body) return i;
            return -1;
        }

        /// <summary>The newest whole disk generation adopted as the queue (F8):
        /// its membership and order are the queue's, so every addition and
        /// every removal that generation recorded survives, whatever memory
        /// held. Memory only ever gains a request after a write that replaced
        /// the primary, so a request memory holds and that generation lacks
        /// was removed on disk and is dropped. Where both hold a request the
        /// larger attempt and session counts and the later next-eligible time
        /// win (memory's in-place updates whose write did not land), and the
        /// launch hold is memory's. A generation longer than QUEUE_CAP (only
        /// a hand-edited file) keeps its newest QUEUE_CAP requests, as
        /// Enqueue's eviction would have.</summary>
        private static void Adopt(List<C.Pending> mem, IList<C.Pending> disk)
        {
            var next = new List<C.Pending>(disk.Count);
            for (int i = Math.Max(0, disk.Count - QUEUE_CAP); i < disk.Count; i++)
            {
                var d = disk[i];
                if (Find(next, d.Route, d.Body) >= 0) continue;
                int k = Find(mem, d.Route, d.Body);
                if (k < 0) { next.Add(d.Clone()); continue; }
                var m = mem[k];
                if (d.Attempts > m.Attempts) m.Attempts = d.Attempts;
                if (d.SessionRetries > m.SessionRetries) m.SessionRetries = d.SessionRetries;
                if (d.NotBeforeUnix > m.NotBeforeUnix) m.NotBeforeUnix = d.NotBeforeUnix;
                if (d.FirstUnix < m.FirstUnix) m.FirstUnix = d.FirstUnix;
                next.Add(m);
            }
            mem.Clear();
            mem.AddRange(next);
        }

        /// <summary>A closing request admitted into `next` under Enqueue's
        /// policy (F8): one the queue already holds is not added twice; at
        /// QUEUE_CAP the oldest queued request is evicted to make room, so a
        /// closing request is never skipped. Returns whether one was evicted.</summary>
        private static bool AdmitClosing(List<C.Pending> next, C.Pending d)
        {
            if (Find(next, d.Route, d.Body) >= 0) return false;
            bool evicted = next.Count >= QUEUE_CAP;
            if (evicted) next.RemoveAt(0);
            next.Add(d.Clone());
            return evicted;
        }

        /// <summary>Every queue writer calls this first. It reads the primary
        /// AND the temporary copy, recovering the newest whole one
        /// (C.ChooseCopy), on the first call of a launch and again after any
        /// write that did not replace the primary (F8): that copy is adopted
        /// as the queue (Adopt), so no writer ever writes from a memory that
        /// lacks the newest whole copy's additions or still holds its
        /// removals. A copy that exists but cannot be
        /// read leaves the queue unloaded: its generation is unknown, so
        /// nothing is written over it, and the load is tried again later. On
        /// the first load of a launch the closing files the previous launch's
        /// quitting path wrote (F3) are admitted too, and each is deleted only
        /// after a write that replaced the primary holds its exact request
        /// (PromoteSpool). A request past the
        /// expiry or the attempt bound is loaded too: the pump settles it
        /// (C.SendRefusal) without a send, and the write that settles it
        /// removes it from the file.</summary>
        private static bool Load()
        {
            if (_loaded && !_stale && _spoolChecked) return true;
            try
            {
                if (!_loaded || _stale)
                {
                    string path = QueuePath();
                    var a = ReadCopy(path, true);
                    var b = ReadCopy(path + ".tmp", false);
                    if ((a.Present && !a.Readable) || (b.Present && !b.Readable)) return false;
                    int which = C.ChooseCopy(a, b);
                    _gen = Math.Max(_gen, Math.Max(a.Generation, b.Generation));
                    var src = which == 1 ? a.Items : (which == 2 ? b.Items : null);
                    if (src != null) Adopt(_queue, src);
                    _loaded = true;
                    _stale = false;
                }
                if (!_spoolChecked) PromoteSpool();
                return true;
            }
            catch { return false; }
        }

        /// <summary>The closing files (F3), at most SPOOL_CAP per call: every
        /// whole one's requests admitted into the queue (AdmitClosing, Enqueue's
        /// eviction at the cap), then the queue written. Only when that write
        /// replaced the primary is a whole file deleted, and only when every
        /// request it holds is present, by exact route and bytes, in the
        /// queue that write saved (F8); a file that fails that check stays for
        /// the next launch (kept out of this launch's later passes, so its
        /// requests are not admitted again and again). A file whose delete
        /// fails stays on disk; whichever later pass lists it admits it again,
        /// which adds nothing the queue already holds. A failed write keeps
        /// every file, and the next load tries again. A file that is not
        /// whole can never become whole (its writer is gone) and is deleted
        /// after the successful write.</summary>
        private static void PromoteSpool()
        {
            string[] files;
            try
            {
                var all = new List<string>(Directory.GetFiles(Paths.ConfigPath, SPOOL_PREFIX + "*.jsonl"));
                all.RemoveAll(f => _spoolKept.Contains(f));
                files = all.ToArray();
            }
            catch { return; }
            if (files.Length == 0) { _spoolChecked = true; return; }
            Array.Sort(files, StringComparer.Ordinal);
            int n = Math.Min(files.Length, SPOOL_CAP);
            var next = new List<C.Pending>(_queue);
            var copies = new C.QueueCopy[n];
            int evicted = 0;
            for (int i = 0; i < n; i++)
            {
                var c = ReadCopy(files[i], false);
                if (c.Present && !c.Readable) return;       // held by something: try again later
                copies[i] = c;
                if (c.Whole) foreach (var d in c.Items) if (AdmitClosing(next, d)) evicted++;
            }
            if (Save(next) != SAVED) return;
            _queue.Clear();
            _queue.AddRange(next);
            int moved = 0;
            for (int i = 0; i < n; i++)
            {
                var c = copies[i];
                if (!c.Present) continue;
                bool held = true;
                if (c.Whole) foreach (var d in c.Items) if (Find(next, d.Route, d.Body) < 0) { held = false; break; }
                if (!held) { _spoolKept.Add(files[i]); continue; }
                try { File.Delete(files[i]); moved++; } catch { }
            }
            _spoolChecked = files.Length <= n;
            _nextPumpMs = 0;
            Plugin.Log.LogInfo(TAG + " " + moved.ToString(CultureInfo.InvariantCulture) + " closing file(s) moved into the queue");
            if (evicted > 0) Plugin.Log.LogInfo(TAG + " queue full: " + evicted.ToString(CultureInfo.InvariantCulture) + " oldest queued request(s) dropped for closing records");
        }

        /// <summary>The quitting path's only write (F3): one request in a new
        /// file of its own, in the queue file's format with its trailer,
        /// flushed to disk. Never the queue file, never a load: the next
        /// launch's first load admits it (PromoteSpool). False: not written.</summary>
        internal static bool SpoolClosing(string route, string body)
        {
            try
            {
                if (body == null || (route != "e" && route != "k" && route != "c")) return false;
                var p = new C.Pending { Route = route, Body = body, FirstUnix = UnixNow() };
                string name = SPOOL_PREFIX + DateTime.UtcNow.Ticks.ToString("D19", CultureInfo.InvariantCulture) + "-"
                              + (++_spoolSeq).ToString("D4", CultureInfo.InvariantCulture) + ".jsonl";
                byte[] bytes = new UTF8Encoding(false).GetBytes(C.QueueText(new List<C.Pending> { p }, 1));
                using (var fs = new FileStream(Path.Combine(Paths.ConfigPath, name), FileMode.CreateNew, FileAccess.Write, FileShare.None))
                {
                    fs.Write(bytes, 0, bytes.Length);
                    fs.Flush(true);
                }
                return true;
            }
            catch { return false; }
        }

        private static C.QueueCopy ReadCopy(string path, bool primary)
        {
            if (!File.Exists(path)) return new C.QueueCopy();
            string text;
            try { text = File.ReadAllText(path); }
            catch { return new C.QueueCopy { Present = true }; }
            return C.ParseQueue(text, primary);
        }

        /// <summary>What a queue write left on disk (F6, F8). SAVED: the
        /// temporary copy replaced the primary. IN_TEMP: it did not, but the
        /// temporary copy holding exactly this generation is whole on disk,
        /// and as the newest whole copy a later load recovers it. ABSENT: no
        /// whole copy of this generation exists (read back after the failure).
        /// UNKNOWN: the read-back itself failed.</summary>
        private const int SAVED = 2, IN_TEMP = 1, ABSENT = 0, UNKNOWN = -1;

        /// <summary>Writes `items` as the next generation: the whole text to the
        /// temporary copy, flushed to disk, then the temporary replaces the
        /// primary. Anything short of SAVED marks memory stale (F8) and reads
        /// both copies back to say whether this generation is on disk anyway.</summary>
        private static int Save(List<C.Pending> items)
        {
            string path = QueuePath(), tmp = path + ".tmp";
            long gen = _gen + 1;
            _gen = gen;
            try
            {
                byte[] bytes = new UTF8Encoding(false).GetBytes(C.QueueText(items, gen));
                using (var fs = new FileStream(tmp, FileMode.Create, FileAccess.Write, FileShare.None))
                {
                    fs.Write(bytes, 0, bytes.Length);
                    fs.Flush(true);
                }
                if (File.Exists(path)) File.Delete(path);
                File.Move(tmp, path);
                return SAVED;
            }
            catch { }
            _stale = true;
            try
            {
                var a = ReadCopy(path, true);
                var b = ReadCopy(tmp, false);
                if ((a.Present && !a.Readable) || (b.Present && !b.Readable)) return UNKNOWN;
                if (a.Whole && a.Generation == gen) return SAVED;
                if (b.Whole && b.Generation == gen) return IN_TEMP;
                return ABSENT;
            }
            catch { return UNKNOWN; }
        }

        /// <summary>A card draw envelope (route "k"), persisted like the
        /// others and sent by the same pump, outside combat. False: not
        /// persisted, the caller keeps it.</summary>
        internal static bool EnqueueCard(string body)
        {
            return Enqueue("k", body);
        }

        /// <summary>Adds a frozen body; every retry sends these exact bytes. It
        /// counts as queued only when the queue file holding it replaced the
        /// old one (F8); on false nothing in memory changed and the caller
        /// keeps the body. A body the queue already holds (an earlier try whose
        /// write reached only the temporary copy, adopted back by Load) is not
        /// added twice.</summary>
        private static bool Enqueue(string route, string body)
        {
            if (!Load()) return false;
            var next = new List<C.Pending>(_queue);
            bool evicted = false;
            if (Find(next, route, body) < 0)
            {
                evicted = next.Count >= QUEUE_CAP;
                if (evicted) next.RemoveAt(0);
                next.Add(new C.Pending { Route = route, Body = body, FirstUnix = UnixNow() });
            }
            if (Save(next) != SAVED) return false;
            _queue.Clear();
            _queue.AddRange(next);
            if (evicted) Plugin.Log.LogInfo(TAG + " queue full: the oldest queued request was dropped");
            _nextPumpMs = 0;
            return true;
        }

        private static string RouteOf(string route)
        {
            return route == "c" ? ROUTE_COMPAT : (route == "k" ? ROUTE_CARD : ROUTE_RECORD);
        }

        private static string What(string route)
        {
            return route == "c" ? "compat outcome" : (route == "k" ? "card record" : "record");
        }

        // the request in flight and its answer, as the result callback left it
        private const long FLIGHT_LIMIT_MS = 60000;
        private static string _flightRoute, _flightBody;
        private static long _flightAtMs;
        private static volatile bool _answered;
        private static bool _answerLeft, _answerOk, _answerCarried;
        private static string _answerText;

        /// <summary>One send of the oldest due request, from Tick only (after
        /// its current-frame combat check), with data consent and a session.
        /// The limits are checked before the request is set up, and again by
        /// BeforeSend immediately before its bytes leave. The result callback
        /// only stores the answer; TakeAnswer acts on it on a later tick.</summary>
        private static void Pump(long nowMs)
        {
            if (_inFlight || nowMs < _nextPumpMs) return;
            if (!Plugin.DataConsentGranted || !ApiClient.SeatEvidenceReady) return;
            _nextPumpMs = nowMs + 5000;
            if (!Load()) return;
            long now = UnixNow();
            C.Pending p = null;
            foreach (var q in _queue)
                if (!q.HoldUntilNextLaunch && q.NotBeforeUnix <= now) { p = q; break; }
            if (p == null) return;
            string refusal = C.SendRefusal(p, now);
            if (refusal != null) { Settle(p.Route, p.Body, refusal, 0); return; }
            _inFlight = true; _flightRoute = p.Route; _flightBody = p.Body; _flightAtMs = nowMs; _answered = false;
            string route = p.Route, body = p.Body;
            bool started = false;
            try
            {
                started = ApiClient.SeatEvidencePost(RouteOf(route), body, () => BeforeSend(route, body),
                    (left, ok, text, carried) =>
                    {
                        _answerLeft = left; _answerOk = ok; _answerText = text; _answerCarried = carried;
                        _answered = true;
                    });
            }
            catch { started = false; }
            if (!started) { _inFlight = false; _flightRoute = _flightBody = null; _answered = false; }
        }

        /// <summary>Called by the api's evidence path immediately before
        /// SendWebRequest, after the request is completely built and every
        /// local gate passed: the limits again, then the spent transmission
        /// and the next-eligible time are persisted (F6). The request goes
        /// exactly when that increment may be on disk: written (SAVED), whole
        /// in the temporary copy a later load recovers (IN_TEMP), or not
        /// knowable (UNKNOWN). Only when the read-back shows no copy holds it
        /// (ABSENT) is the send refused, leaving memory as it was, so no
        /// recoverable spent attempt ever exists for a request that did not
        /// go. A compat outcome is then held for the rest of this launch: one
        /// compat-route POST per launch (F9).</summary>
        private static bool BeforeSend(string route, string body)
        {
            try
            {
                if (CombatLive()) return false;
                if (!Load()) return false;
                int i = Find(_queue, route, body);
                if (i < 0) return false;
                var p = _queue[i];
                long now = UnixNow();
                if (C.SendRefusal(p, now) != null) return false;
                var t = C.AfterTransmission(p, now);
                var next = new List<C.Pending>(_queue);
                next[i] = t;
                int stage = Save(next);
                if (stage == ABSENT) return false;
                p.Attempts = t.Attempts; p.NotBeforeUnix = t.NotBeforeUnix;
                if (p.Route == "c") p.HoldUntilNextLaunch = true;
                return true;
            }
            catch { return false; }
        }

        /// <summary>Tick, outside combat: acts on the answer the result
        /// callback stored. A request that went out counts whatever came back;
        /// one that never left (a gate refused it) changes nothing. A callback
        /// that never comes (its host went away) frees the slot after
        /// FLIGHT_LIMIT_MS with the transmission still counted.</summary>
        private static void TakeAnswer(long nowMs)
        {
            if (!_inFlight) return;
            if (!_answered)
            {
                if (nowMs - _flightAtMs > FLIGHT_LIMIT_MS) { _inFlight = false; _flightRoute = _flightBody = null; }
                return;
            }
            string route = _flightRoute, body = _flightBody;
            bool left = _answerLeft, ok = _answerOk, carried = _answerCarried;
            string text = _answerText;
            _inFlight = false; _flightRoute = _flightBody = null; _answered = false;
            if (left && route != null) Answer(route, body, ok, text, carried);
        }

        private static void Answer(string route, string bodyKey, bool ok, string text, bool carried)
        {
            // a copy that cannot be read is never written over: the request
            // keeps the next-eligible time its transmission persisted
            if (!Load()) return;
            int i = Find(_queue, route, bodyKey);
            if (i < 0) return;
            var p = _queue[i];
            int status, retryAfter; string body;
            C.ParseAnswer(ok, text, out status, out body, out retryAfter);
            long now = UnixNow();
            if (!carried && status != 0)
            {
                // answered without the session token: says nothing about this
                // record; the transmission stays counted
                p.NotBeforeUnix = now + 60;
                Save(_queue);
                return;
            }
            long delay; string reason;
            var act = C.Decide(p, status, body, retryAfter, now, out delay, out reason);
            string what = What(p.Route);
            switch (act)
            {
                case C.Act.Drop:
                    Settle(route, bodyKey, reason, status);
                    return;
                case C.Act.RetryNextLaunch:
                    p.HoldUntilNextLaunch = true;
                    p.NotBeforeUnix = now;      // the hold is this launch; the next launch may send it
                    Save(_queue);
                    Plugin.Log.LogInfo(TAG + " " + what + " kept for the next launch: " + reason);
                    return;
                default:
                    p.NotBeforeUnix = now + delay;
                    Save(_queue);
                    if (p.Attempts == 1 || act == C.Act.RefreshAndRetry)
                        Plugin.Log.LogInfo(TAG + " " + what + " retry in " + delay.ToString(CultureInfo.InvariantCulture) + " s: " + reason);
                    return;
            }
        }

        /// <summary>A request that is done (recorded, refused, expired or spent)
        /// leaves the queue once the file without it replaced the old one; if
        /// that write fails it stays in memory, held for the rest of this
        /// launch, and the next launch's identical bytes meet the server's
        /// already_recorded or the same refusal.</summary>
        private static void Settle(string route, string body, string reason, int status)
        {
            if (!Load()) return;
            int i = Find(_queue, route, body);
            if (i < 0) return;
            var p = _queue[i];
            var next = new List<C.Pending>(_queue);
            next.RemoveAt(i);
            if (Save(next) == SAVED) _queue.RemoveAt(i);
            else p.HoldUntilNextLaunch = true;
            Plugin.Log.LogInfo(TAG + " " + What(p.Route) + " settled: " + reason + " (HTTP " + status.ToString(CultureInfo.InvariantCulture)
                + ", attempt " + p.Attempts.ToString(CultureInfo.InvariantCulture) + ")");
        }
    }

    /// <summary>B5: this seat's own block RPC to Others. The postfix reads the
    /// stamp PUN wrote into that envelope; it changes nothing about the send.</summary>
    [HarmonyPatch]
    internal static class SeatEvidence_RpcSendPatch
    {
        private static MethodBase TargetMethod()
        {
            var m = AccessTools.Method(typeof(PhotonNetwork), "RPC",
                new[] { typeof(PhotonView), typeof(string), typeof(RpcTarget), typeof(Photon.Realtime.Player), typeof(bool), typeof(object[]) });
            if (m == null) throw new Exception("PhotonNetwork.RPC(PhotonView, string, RpcTarget, Player, bool, object[]) not found - no block send stamp");
            return m;
        }

        [HarmonyPostfix]
        private static void Postfix(PhotonView __0, string __1, RpcTarget __2)
        {
            try { SeatEvidence.BlockSent(__0, __1, __2); } catch { }
        }
    }

    /// <summary>B7: a blocked impact resets sinceBlock with no block key.</summary>
    [HarmonyPatch(typeof(Block), "DoBlock")]
    internal static class SeatEvidence_DoBlockPatch
    {
        [HarmonyFinalizer]
        private static Exception Finalizer(Block __instance, Exception __exception)
        {
            try { SeatEvidence.UnkeyedReset(__instance); } catch { }
            return __exception;
        }
    }

    [HarmonyPatch(typeof(Block), "TryBlockMe")]
    internal static class SeatEvidence_TryBlockMePatch
    {
        [HarmonyFinalizer]
        private static Exception Finalizer(Block __instance, Exception __exception)
        {
            try { SeatEvidence.UnkeyedReset(__instance); } catch { }
            return __exception;
        }
    }
}
