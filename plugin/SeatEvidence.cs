using BepInEx;
using HarmonyLib;
using Photon.Pun;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Reflection;
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
        private static readonly C.SampleLog _samples = new C.SampleLog();
        private static C.Cadence _cad = new C.Cadence();
        private static readonly C.EventList _blkSent = new C.EventList(), _hitRecv = new C.EventList(), _blkRecv = new C.EventList(), _hitSent = new C.EventList();
        private static readonly C.Ordinals _ordBlkSent = new C.Ordinals(), _ordBlkRecv = new C.Ordinals(), _ordHitRecv = new C.Ordinals(), _ordHitSent = new C.Ordinals();
        private static readonly C.HitWindow _winRecv = new C.HitWindow(), _winSent = new C.HitWindow();
        private static readonly long[] _shots = new long[3], _imp = new long[3], _dec = new long[2], _push = new long[7];
        private static readonly HashSet<int> _impDistinct = new HashSet<int>();
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

        // the other seat's own statements, as relayed (snapshotted every 3 s)
        private static string _oppBuild = ""; private static List<string> _oppKeys = new List<string>(); private static long[] _oppPub;

        private static void ResetGame()
        {
            _open = false; _oppActor = 0; _masterAtStart = false; _rankedAtStart = false;
            _frozen = false; _frozenAtMs = 0; _room = ""; _end = null;
            _ageView = new C.AgeStats(11); _ageRpc = new C.AgeStats(12); _ageHit = new C.AgeStats(13); _ageBlk = new C.AgeStats(14);
            _samples.Clear(); _cad = new C.Cadence();
            foreach (var l in new[] { _blkSent, _hitRecv, _blkRecv, _hitSent }) { l.Items.Clear(); l.Omitted = 0; }
            _ordBlkSent.Clear(); _ordBlkRecv.Clear(); _ordHitRecv.Clear(); _ordHitSent.Clear();
            _winRecv.Clear(); _winSent.Clear();
            Array.Clear(_shots, 0, 3); Array.Clear(_imp, 0, 3); Array.Clear(_dec, 0, 2); Array.Clear(_push, 0, 7);
            _impDistinct.Clear();
            _fireFloor = _blkFaults = _unpairBlocks = _unpairHits = 0; _hasFireStamp = false;
            _mine.Clear(); _opp.Clear();
            _ownOpenPending = false; _awaitDamage = null;
            _rttSum = _rttN = _rttMax = 0; _offUpdates = _offStepMax = 0; _offHas = false;
            _oppBuild = ""; _oppKeys = new List<string>(); _oppPub = null;
            _nextSampleMs = 0;
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
            foreach (var e in w.Block(tb, 1)) list.Add(e);
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
        /// damage this envelope carries passes TakeDamage's gate here (the RPC
        /// path applies with ignoreBlock).</summary>
        internal static bool DamageGate(HealthHandler hh)
        {
            try
            {
                var d = hh != null ? hh.GetComponent<CharacterData>() : null;
                return d != null && d.isPlaying && !d.dead && d.playerVel != null && d.playerVel.simulated;
            }
            catch { return false; }
        }

        /// <summary>HealthHandler.RPCA_SendTakeDamage finalizer. On the victim:
        /// marks dmg on the hit it follows, or counts a damage envelope no hit
        /// RPC keys (unpair[1]). On the shooter: the local leg inside a direct
        /// impact gives path 1 its stamp.</summary>
        internal static void DamageArrived(HealthHandler hh, bool gate)
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
                    if (_awaitDamage != null) { _awaitDamage[6] = gate ? 1 : 0; _awaitDamage = null; }
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
                        Sample();
                    }
                }
                Pump(now);
            }
            catch { }
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

        private static void Sample()
        {
            try
            {
                int ping = PhotonNetwork.GetPing();
                if (ping >= 0) { _rttSum += ping; _rttN++; if (ping > _rttMax) _rttMax = ping; }
            }
            catch { }
            try
            {
                if (_oppActor == 0) ResolveOpponent();
                var room = PhotonNetwork.CurrentRoom;
                var p = room != null && _oppActor != 0 ? room.GetPlayer(_oppActor) : null;
                var cp = p != null ? p.CustomProperties : null;
                if (cp == null) return;
                var keys = new List<string>();
                foreach (object k in cp.Keys) { var s = k as string; if (s != null) keys.Add(s); }
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

        private static volatile string _dllSha = "", _dllState = "no_location", _gameSha = "", _gameState = "no_location";
        private static bool _hashStarted;
        private static string _compat = "not_run";

        internal static void StartHashing()
        {
            try
            {
                if (_hashStarted) return;
                _hashStarted = true;
                string own = "", game = "";
                try { own = typeof(SeatEvidence).Assembly.Location ?? ""; } catch { }
                try { game = typeof(GM_ArmsRace).Assembly.Location ?? ""; } catch { }
                var t = new Thread(() =>
                {
                    string s, st;
                    Hash(own, out s, out st); _dllSha = s; _dllState = st;
                    Hash(game, out s, out st); _gameSha = s; _gameState = st;
                });
                t.IsBackground = true;
                t.Start();
            }
            catch { }
        }

        private static void Hash(string path, out string sha, out string state)
        {
            sha = ""; state = "no_location";
            if (string.IsNullOrEmpty(path)) return;
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

        private static string OwnSteamId()
        {
            try { return Steamworks.SteamUser.GetSteamID().m_SteamID.ToString(CultureInfo.InvariantCulture); } catch { return ""; }
        }

        /// <summary>Above Plugin's modDisabled return: once this seat's Steam id
        /// is known, the pending compat outcome is signed and persisted (sent by
        /// the queue on a launch whose api is up). On a seat the finding has
        /// disabled, the compat sender then makes its one bounded attempt.</summary>
        internal static void CompatTick()
        {
            try
            {
                if (_compatOutcome != null)
                {
                    string seat = OwnSteamId();
                    if (C.IsSteamId(seat))
                    {
                        string outcome = _compatOutcome; _compatOutcome = null;
                        string sig = ApiClient.SeatEvidenceSig(C.CompatCanonical(seat, outcome, _compatPlugins));
                        string body = C.CompatBody(seat, outcome, _compatPlugins, sig);
                        if (body == null) Plugin.Log.LogWarning(TAG + " compat outcome not queued: a field is outside its bound");
                        else
                        {
                            Enqueue("c", body);
                            Plugin.Log.LogInfo(TAG + " compat outcome queued: " + outcome + " plugins=" + _compatPlugins.Count.ToString(CultureInfo.InvariantCulture));
                        }
                    }
                }
                CompatSend();
            }
            catch { }
        }

        // -- the compat sender (V1 6.4) ------------------------------------------------------

        private static int _sendPhase;          // 0 not started, 1 running, 2 finished for this launch
        private static long _sendStartMs, _nextAuthMs;

        /// <summary>A seat the other-plug-in check disabled never initialises
        /// the api, so the queue's own pump never runs on it. Instead this makes
        /// ONE bounded attempt (C.COMPAT_SEND_LIMIT_MS) to send the queued compat
        /// outcome: it points the api at the configured base without starting
        /// any of its loops, obtains a session through the existing Steam ticket
        /// exchange, and posts the compat route once. Seat evidence game records
        /// are never sent from here. Without data consent nothing is sent; an
        /// outcome not sent stays queued for the next launch.</summary>
        private static void CompatSend()
        {
            if (_sendPhase == 2 || !Plugin.modDisabled) return;
            Load();
            bool queued = false;
            foreach (var q in _queue) if (q.Route == "c") { queued = true; break; }
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
                    Pump(SwMs, "c");
                    Plugin.Log.LogInfo(TAG + " compat outcome: one send attempted while the mod stays disabled");
                    return;
                case C.SendStep.GiveUp:
                    _sendPhase = 2;
                    Plugin.Log.LogInfo(TAG + " compat outcome not sent within " + (C.COMPAT_SEND_LIMIT_MS / 1000).ToString(CultureInfo.InvariantCulture) + " s: kept for the next launch");
                    return;
                case C.SendStep.NoConsent:
                    _sendPhase = 2;
                    Plugin.Log.LogInfo(TAG + " compat outcome not sent: no data consent");
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

        // -- the record (built once, after the match report is queued) -------------------------

        /// <summary>From OnGameOver, after ApiClient.ReportMatch returned; from
        /// GameStateWatcher's room-exit branch for a game cut short; from the
        /// quit hook for a game still live while the game closes. Ranked 1v1
        /// games only, both seats. Takes the live window, or a frozen one of
        /// the same room no older than FROZEN_MS, builds, budgets, signs and
        /// persists the envelope before any network work. The end kind this
        /// seat noted rides in the record; none means it saw the game over.</summary>
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
                string stable = StableOf(attach);
                if (stable == null || !C.IsSteamId(seat) || !C.IsSteamId(other))
                {
                    Plugin.Log.LogWarning(TAG + " no record: game key or seat ids outside the contract");
                    return;
                }
                bool fromToken;
                int t0 = GameStateWatcher.SeatEvidenceT0(out fromToken);
                var r = new C.Record
                {
                    T0 = t0, T0Src = fromToken ? "m" : "o", Master = _masterAtStart ? 1 : 0, Ranked = _rankedAtStart ? 1 : 0,
                    RoundsSelf = roundsSelf, RoundsOther = roundsOther, End = _end,
                    Build = C.SplitBuild(PeerBuild.BuildValue()) ?? new[] { "", "", "" },
                    DllSha = _dllSha, DllState = _dllState, GameDllSha = _gameSha, GameDllState = _gameState,
                    Compat = _compat,
                    RttAvg = _rttN > 0 ? _rttSum / _rttN : 0, RttMax = _rttMax,
                    OffsetUpdates = _offUpdates, OffsetStepMax = _offStepMax,
                    ClkPpm = ClockPpm(), MonoSend = SwMs,
                    AgeView = _ageView.Four(), AgeRpc = _ageRpc.Four(), AgeHit = _ageHit.Three(), AgeBlk = _ageBlk.Three(),
                    AgeB = _samples.AgeBuckets(t0), DriftV = _samples.DriftTriple(t0), Cad = _cad.Five(),
                    OtherBuildV = _oppBuild, OtherCapsV = C.OtherCaps(_oppKeys), OtherPub = _oppPub,
                    FireFloor = _fireFloor, BlkFaults = _blkFaults, UnpairBlocks = _unpairBlocks, UnpairHits = _unpairHits,
                };
                long fa, fo; Foreign(out fa, out fo); r.ForeignAsm = fa; r.ForeignOwners = fo;
                NetworkReplicaDiagnostics.ObsSnapshot o;
                if (NetworkReplicaDiagnostics.TryGetOpponentGameObs(out o))
                    r.Obs = new long[] { o.Gap300, o.Gap750, o.Gap1500, o.MaxGapMs, o.Excess150, o.MaxExcessMs,
                                         o.PayloadEqualGaps, o.ReceiverFrameGaps, o.PhoenixIntervals, o.Batches };
                Array.Copy(_shots, r.Shots, 3);
                r.Imp = new long[] { _imp[0], _imp[1], _impDistinct.Count };
                Array.Copy(_dec, r.Dec, 2); Array.Copy(_push, r.Push, 7);
                r.BlkSent = new List<long[]>(_blkSent.Items); r.HitRecv = new List<long[]>(_hitRecv.Items);
                r.BlkRecv = new List<long[]>(_blkRecv.Items); r.HitSent = new List<long[]>(_hitSent.Items);
                r.Omit = new long[] { _blkSent.Omitted, _hitRecv.Omitted, _blkRecv.Omitted, _hitSent.Omitted, 0 };
                string text = C.Budget(r.ToObj());
                string sig = ApiClient.SeatEvidenceSig(C.Canonical(seat, other, stable, attach, text));
                string env = C.Envelope(seat, other, stable, attach, text, sig);
                if (env == null) { Plugin.Log.LogWarning(TAG + " no record: the envelope is outside the contract"); return; }
                Enqueue("e", env);
                Plugin.Log.LogInfo(TAG + " record queued: " + text.Length.ToString(CultureInfo.InvariantCulture) + " bytes, lists "
                    + r.BlkSent.Count + "/" + r.HitRecv.Count + "/" + r.BlkRecv.Count + "/" + r.HitSent.Count
                    + ", unpaired " + _unpairBlocks + "/" + _unpairHits + ", t0 " + (fromToken ? "m" : "o")
                    + ", end " + (r.End ?? "game_over"));
            }
            catch (Exception ex)
            {
                try { Plugin.Log.LogWarning(TAG + " no record: " + ex.GetType().Name); } catch { }
            }
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
        private static long _nextPumpMs;

        private static string QueuePath() { return Path.Combine(Paths.ConfigPath, "CompetitiveRounds.seat-evidence.jsonl"); }

        private static long UnixNow() { return DateTimeOffset.UtcNow.ToUnixTimeSeconds(); }

        private static void Load()
        {
            if (_loaded) return;
            _loaded = true;
            try
            {
                string path = QueuePath(), tmp = path + ".tmp";
                if (!File.Exists(path) && File.Exists(tmp)) path = tmp;
                if (!File.Exists(path)) return;
                long now = UnixNow();
                foreach (var line in File.ReadAllLines(path))
                {
                    var p = C.ParseLine(line);
                    if (p == null || now - p.FirstUnix >= C.EXPIRY_S) continue;
                    if (_queue.Count < QUEUE_CAP) _queue.Add(p);
                }
            }
            catch { }
        }

        private static void Save()
        {
            try
            {
                string path = QueuePath(), tmp = path + ".tmp";
                var lines = new List<string>();
                foreach (var p in _queue) lines.Add(C.Line(p));
                File.WriteAllLines(tmp, lines.ToArray());
                if (File.Exists(path)) File.Delete(path);
                File.Move(tmp, path);
            }
            catch { }
        }

        /// <summary>Persists the frozen body before any network yield. Every
        /// retry sends these exact bytes.</summary>
        private static void Enqueue(string route, string body)
        {
            Load();
            if (_queue.Count >= QUEUE_CAP) _queue.RemoveAt(0);
            _queue.Add(new C.Pending { Route = route, Body = body, FirstUnix = UnixNow() });
            Save();
            _nextPumpMs = 0;
        }

        /// <summary>One send of the oldest due request (of `onlyRoute` when
        /// given), never during combat and only with a session.</summary>
        private static void Pump(long nowMs, string onlyRoute = null)
        {
            if (_inFlight || nowMs < _nextPumpMs) return;
            _nextPumpMs = nowMs + 5000;
            Load();
            if (_queue.Count == 0) return;
            if (NetworkReplicaDiagnostics.BattleActive) return;     // never during combat
            if (!ApiClient.SeatEvidenceReady) return;
            long now = UnixNow();
            C.Pending p = null;
            foreach (var q in _queue)
                if ((onlyRoute == null || q.Route == onlyRoute) && !q.HoldUntilNextLaunch && q.NotBeforeUnix <= now) { p = q; break; }
            if (p == null) return;
            p.Attempts++;
            Save();
            _inFlight = true;
            var sent = p;
            bool started = ApiClient.SeatEvidencePost(p.Route == "c" ? ROUTE_COMPAT : ROUTE_RECORD, p.Body, (ok, text, carried) =>
            {
                try { Answer(sent, ok, text, carried); } catch { }
                _inFlight = false;
            });
            if (!started) { _inFlight = false; p.Attempts--; Save(); }
        }

        private static void Answer(C.Pending p, bool ok, string text, bool carried)
        {
            int status, retryAfter; string body;
            C.ParseAnswer(ok, text, out status, out body, out retryAfter);
            long now = UnixNow();
            if (!carried && status != 0)
            {
                // answered without the session token: says nothing about this record
                p.Attempts--; p.NotBeforeUnix = now + 60; Save();
                return;
            }
            long delay; string reason;
            var act = C.Decide(p, status, body, retryAfter, now, out delay, out reason);
            string what = p.Route == "c" ? "compat outcome" : "record";
            switch (act)
            {
                case C.Act.Drop:
                    _queue.Remove(p);
                    Plugin.Log.LogInfo(TAG + " " + what + " settled: " + reason + " (HTTP " + status.ToString(CultureInfo.InvariantCulture) + ", attempt " + p.Attempts.ToString(CultureInfo.InvariantCulture) + ")");
                    break;
                case C.Act.RetryNextLaunch:
                    p.HoldUntilNextLaunch = true;
                    Plugin.Log.LogInfo(TAG + " " + what + " kept for the next launch: " + reason);
                    break;
                default:
                    p.NotBeforeUnix = now + delay;
                    if (p.Attempts == 1 || act == C.Act.RefreshAndRetry)
                        Plugin.Log.LogInfo(TAG + " " + what + " retry in " + delay.ToString(CultureInfo.InvariantCulture) + " s: " + reason);
                    break;
            }
            Save();
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
