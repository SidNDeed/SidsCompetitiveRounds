using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using BepInEx;
using HarmonyLib;
using Photon.Pun;
using UnityEngine;
using K = CompetitiveRounds.CardDrawEvidenceCore;

namespace CompetitiveRounds
{
    /// <summary>CARD DRAW EVIDENCE (B4), the Unity half: six collectors on the
    /// pick phase (C1 StartPick, C2 CardInfo.Awake, C3 RPCA_DoEndPick, C4
    /// RPCA_DonePicking, C5 RPCA_Pick, C6 OFFLINE_Pick), the dispatch, the
    /// tick that turns what they captured into CardDrawEvidenceCore's game,
    /// the census of this seat's own pool, the build, and the [Debug]
    /// CardPoolCensusDump lever.
    ///
    /// Two halves (fix pass 2, F4). The HOOK side runs inside the game's own
    /// methods and the result callbacks: each collector copies a hard-capped
    /// snapshot of what the game holds (object references and numbers, at
    /// most SL_CAP slots, TARGET_CAP targets, PO_CAP players and HELD_CAP
    /// held cards) into a preallocated event slot of a fixed ring, and
    /// nothing else: no pool index, no census, no hand close, no
    /// allocation. The TICK side, from Plugin's persistent tick outside
    /// combat, drains the ring in order: per game a fresh census of the pool
    /// the game's first phase named (CD-M4), the pool indexes, the hands, the
    /// seal, the build.
    ///
    /// Containment: every hook wraps its one call in try/catch; every
    /// collector body runs inside its own try/catch that counts the fault in
    /// the record and marks the game incomplete (CD-M3). No collector writes
    /// a field the game reads, changes a hand, a card, a pick, picks,
    /// pickrID, IsPicking, spawnedCards, currentCards or a card bar, starts a
    /// coroutine, creates or destroys an object, or reads the game's random
    /// generator. Nothing is sent to other players.
    ///
    /// Gate: the collectors record in an online 1v1 fighter room (the opening
    /// phase precedes the asynchronous ranked resolution, so ranked is
    /// required at the dispatch instead); spectator, broadcast, FFA, team and
    /// 1v2 rooms record nothing. A casual game's state is never built.</summary>
    internal static class CardDrawEvidence
    {
        internal const string TAG = "[CARD-EV]";
        internal const long FROZEN_MS = 120000;
        private static readonly Stopwatch _sw = Stopwatch.StartNew();

        // ===================================================================================
        // The hook side: O(1) per call, hard-capped copies only (F4)
        // ===================================================================================

        private static bool _hookOpen, _hookTaken, _hookExited, _hookPhase, _hookFirstDone, _hookOrphan;
        private static int _hookG = -1;
        private static string _hookRoom = "";
        private static long _hookExitedAtMs;
        private static int _hookInc, _hookLost, _c1Stage;

        // the open phase's picker on this seat
        private static Player _picker;
        private static int _pickerActor;

        // per collector: calls, total_us, max_us, faults, in_combat (row i at i * COST_W)
        private const int COST_W = 5;
        private static readonly long[] _cost = new long[K.COLLECTORS * COST_W];
        private static readonly bool[] _faultLogged = new bool[K.COLLECTORS];
        // a fault's line, written by the tick (the collector only counts)
        private static readonly string[] _faultNote = new string[K.COLLECTORS];

        // the room's card facts as they stood before a room reset (CD-M2)
        private static bool _frzValid;
        private static string _frzRoom = "", _frzProp;
        private static int _frzRule = -1, _frzVerdict = -1, _frzShared = -1;

        private const int TARGET_CAP = 8, SLOT_SCAN_CAP = 64, PLAYER_SCAN_CAP = 16, EV_CAP = 256;
        private const int EV_PHASE = 1, EV_SPAWN = 2, EV_ENDPICK = 3, EV_DONE = 4, EV_APPLY = 5, EV_SEAL = 6;

        /// <summary>One collector call as the hook copied it. Preallocated and
        /// reused: a hook writes fields, never allocates. Faulted stays true
        /// until the collector finished its copy, so a partial event is
        /// recognisable.</summary>
        private sealed class Ev
        {
            internal int Kind, G;
            internal string Room;
            internal bool Faulted;
            internal int Shared, Gl, Sq;
            internal long Hn;
            // C1
            internal bool First;
            internal int Role, Picks, Rs, Ro, Ns, PoolLen, PoN;
            internal CardInfo[] Pool;
            internal readonly int[] Po = new int[K.PO_CAP];
            internal readonly CardInfo[][] Held = { new CardInfo[K.HELD_CAP], new CardInfo[K.HELD_CAP] };
            internal readonly int[] HeldN = new int[2];
            // C2
            internal CardInfo Src;
            internal int Creator;
            // C3
            internal readonly CardInfo[] Slots = new CardInfo[K.SL_CAP];
            internal int SlotN, Pi, Vid, Pk, Wp, SenderOk;
            // C5, C6
            internal int ApKind, Outcome, TgtN;
            internal readonly int[] Tgt = new int[TARGET_CAP];
            // the seal
            internal bool Keep;
            internal string Seat, Other, Attach, End, RulesProp, BuildValue;
            internal int Rule, Verdict, Closing, Inc;
            internal readonly long[] Cost = new long[K.COLLECTORS * COST_W];
        }

        private static readonly Ev[] _ring = NewRing();
        private static int _evHead, _evCount;

        private static Ev[] NewRing()
        {
            var r = new Ev[EV_CAP];
            for (int i = 0; i < EV_CAP; i++) r[i] = new Ev();
            return r;
        }

        /// <summary>The next free event slot, reset; null when the ring is
        /// full (counted: the game is marked incomplete at its seal). The last
        /// slot is kept for a seal, so a game whose events overflowed is still
        /// sealed and recorded, with INC_LOST.</summary>
        private static Ev Push(int kind)
        {
            if (_evCount >= EV_CAP - (kind == EV_SEAL ? 0 : 1)) { _hookLost++; return null; }
            var e = _ring[(_evHead + _evCount) % EV_CAP];
            _evCount++;
            e.Kind = kind; e.G = _hookG; e.Room = _hookRoom; e.Faulted = true;
            e.Shared = -1; e.Gl = -1; e.Sq = -1; e.Hn = -1;
            e.First = false; e.Role = -1; e.Picks = -1; e.Rs = -1; e.Ro = -1; e.Ns = 0; e.PoolLen = 0; e.PoN = 0; e.Pool = null;
            e.HeldN[0] = -1; e.HeldN[1] = -1;
            e.Src = null; e.Creator = -1;
            e.SlotN = 0; e.Pi = -1; e.Vid = -1; e.Pk = -1; e.Wp = -1; e.SenderOk = -1;
            e.ApKind = 0; e.Outcome = K.APPLY_FAULTED; e.TgtN = 0;
            e.Keep = false; e.Seat = e.Other = e.Attach = e.End = e.RulesProp = e.BuildValue = null;
            e.Rule = -1; e.Verdict = -1; e.Closing = -1; e.Inc = 0;
            return e;
        }

        // -- collector frame: cost and fault accounting ------------------------------------------

        private static bool InCombat()
        {
            try { return GameManager.instance != null && GameManager.instance.battleOngoing; } catch { return false; }
        }

        private static void Cost(int i, long t0)
        {
            try
            {
                long us = (Stopwatch.GetTimestamp() - t0) * 1000000L / Stopwatch.Frequency;
                int b = i * COST_W;
                _cost[b]++; _cost[b + 1] += us; if (us > _cost[b + 2]) _cost[b + 2] = us;
                if (InCombat()) _cost[b + 4]++;
            }
            catch { }
        }

        /// <summary>A collector body threw: counted in its cost row, and the
        /// game marked as having a collector fault. A C1 fault before the game
        /// it belongs to was known marks the next game's first phase as not
        /// captured; one in a game's first phase marks that game's first phase
        /// (CD-M3), and no later phase is ever taken as the first.</summary>
        private static void Fault(int i, Exception ex)
        {
            try
            {
                _cost[i * COST_W + 3]++;
                _hookInc |= K.INC_FAULT;
                if (i == 0)
                {
                    if (_c1Stage == 0) _hookOrphan = true;
                    else if (!_hookFirstDone) { _hookInc |= K.INC_FIRST; _hookFirstDone = true; }
                }
                if (_faultLogged[i]) return;
                _faultLogged[i] = true;
                _faultNote[i] = ex != null ? ex.GetType().Name : "?";
            }
            catch { }
        }

        // -- the six collectors (each: gate at the first line, body in its own try) ---------------

        /// <summary>C1, StartPick postfix: a phase opens; the first phase of a
        /// game also copies the player order and the held cards.</summary>
        internal static void PhaseStarted(CardChoice choice)
        {
            if (!GateRoom()) return;
            long t0 = Stopwatch.GetTimestamp();
            try { C1(choice); } catch (Exception ex) { Fault(0, ex); }
            Cost(0, t0);
        }

        /// <summary>C2, CardInfo.Awake postfix: a network card spawn while a
        /// phase is open (view ids are assigned before activation).</summary>
        internal static void CardAwake(CardInfo card)
        {
            if (!_hookOpen || _hookExited || _hookTaken || !_hookPhase) return;
            long t0 = Stopwatch.GetTimestamp();
            try { C2(card); } catch (Exception ex) { Fault(1, ex); }
            Cost(1, t0);
        }

        /// <summary>C3, RPCA_DoEndPick prefix: the hand in slot order and the pick.</summary>
        internal static void EndPick(int[] cardIds, int targetCardId, int theInt, int pickId)
        {
            if (!_hookOpen || _hookExited || _hookTaken || !_hookPhase) return;
            long t0 = Stopwatch.GetTimestamp();
            try { C3(cardIds, targetCardId, theInt, pickId); } catch (Exception ex) { Fault(2, ex); }
            Cost(2, t0);
        }

        /// <summary>C4, RPCA_DonePicking prefix: the phase is done.</summary>
        internal static void DonePicking()
        {
            if (!_hookOpen || _hookExited || _hookTaken || !_hookPhase) return;
            long t0 = Stopwatch.GetTimestamp();
            try { C4(); } catch (Exception ex) { Fault(3, ex); }
            Cost(3, t0);
        }

        /// <summary>C5, RPCA_Pick postfix and finalizer (CD-M1): one call per
        /// application AFTER the original, with its outcome: APPLY_DONE (it
        /// ran and completed), APPLY_SKIPPED (a sibling prefix skipped it) or
        /// APPLY_FAULTED (it threw). Only APPLY_DONE is ever an application.</summary>
        internal static void PickApplied(ApplyCardStats stats, int[] actorIds, int outcome)
        {
            if (!_hookOpen || _hookExited || _hookTaken) return;
            long t0 = Stopwatch.GetTimestamp();
            try { C5(stats, actorIds, outcome); } catch (Exception ex) { Fault(4, ex); }
            Cost(4, t0);
        }

        /// <summary>C6, OFFLINE_Pick postfix and finalizer: as C5.</summary>
        internal static void OfflinePickApplied(ApplyCardStats stats, Player[] players, int outcome)
        {
            if (!_hookOpen || _hookExited || _hookTaken) return;
            long t0 = Stopwatch.GetTimestamp();
            try { C6(stats, players, outcome); } catch (Exception ex) { Fault(5, ex); }
            Cost(5, t0);
        }

        private static void C1(CardChoice choice)
        {
            _c1Stage = 0;
            int g = VanillaCardSequence.Game;
            string room = RoomName();
            if (!_hookOpen || _hookG != g || _hookRoom != room || _hookExited || _hookTaken) HookBegin(g, room);
            _c1Stage = 1;
            _hookPhase = true;
            _picker = PlayerById(choice.pickrID);
            _pickerActor = ActorOf(_picker);
            var e = Push(EV_PHASE);
            if (e == null)
            {
                if (!_hookFirstDone) { _hookInc |= K.INC_FIRST; _hookFirstDone = true; }
                return;
            }
            e.First = !_hookFirstDone;
            e.Role = RoleOf(_picker);
            e.Picks = choice.picks;
            Rounds(out e.Rs, out e.Ro);
            e.Pool = choice.cards;
            e.PoolLen = e.Pool != null ? e.Pool.Length : 0;
            e.Ns = choice.transform.childCount;
            e.Shared = SharedNow();
            if (e.First) FirstPhase(e);
            e.Faulted = false;
            _hookFirstDone = true;
        }

        private static void C2(CardInfo card)
        {
            var view = card.GetComponent<PhotonView>();
            if (view == null || view.ViewID == 0) return;
            var e = Push(EV_SPAWN);
            if (e == null) return;
            e.Creator = _pickerActor == 0 ? -1 : (view.CreatorActorNr == _pickerActor ? 1 : 0);
            e.Src = card.sourceCard;
            e.Shared = SharedNow();
            Facts(e);
            e.Faulted = false;
        }

        private static void C3(int[] cardIds, int targetCardId, int theInt, int pickId)
        {
            var e = Push(EV_ENDPICK);
            if (e == null) return;
            int n = cardIds != null ? cardIds.Length : 0;
            for (int i = 0; i < n && i < K.SL_CAP; i++) e.Slots[i] = SourceOfView(cardIds[i]);
            e.SlotN = n;
            for (int i = 0; i < n && i < SLOT_SCAN_CAP; i++) if (cardIds[i] == targetCardId) { e.Pi = i; break; }
            int sender = HitEvidence.RpcSender;
            e.SenderOk = sender == 0 || _pickerActor == 0 ? -1 : (sender == _pickerActor ? 1 : 0);
            e.Vid = targetCardId; e.Pk = theInt; e.Wp = RoleOf(PlayerById(pickId));
            e.Shared = SharedNow();
            Facts(e);
            e.Faulted = false;
        }

        private static void C4()
        {
            _hookPhase = false;
            var e = Push(EV_DONE);
            if (e == null) return;
            e.Shared = SharedNow();
            e.Faulted = false;
        }

        private static void C5(ApplyCardStats stats, int[] actorIds, int outcome)
        {
            if (actorIds == null) return;
            var e = Push(EV_APPLY);
            if (e == null) return;
            e.ApKind = 0; e.Outcome = outcome;
            CardOf(stats, e);
            var pm = PlayerManager.instance;
            int n = actorIds.Length;
            for (int i = 0; i < n && i < TARGET_CAP; i++) e.Tgt[i] = RoleOf(pm != null ? pm.GetPlayerWithActorID(actorIds[i]) : null);
            e.TgtN = n;
            e.Faulted = false;
        }

        private static void C6(ApplyCardStats stats, Player[] players, int outcome)
        {
            if (players == null) return;
            var e = Push(EV_APPLY);
            if (e == null) return;
            e.ApKind = 1; e.Outcome = outcome;
            CardOf(stats, e);
            int n = players.Length;
            for (int i = 0; i < n && i < TARGET_CAP; i++) e.Tgt[i] = RoleOf(players[i]);
            e.TgtN = n;
            e.Faulted = false;
        }

        /// <summary>A new game on the hook side: its window, its cost rows and
        /// its incompleteness bits start here, before anything in C1 can throw.</summary>
        private static void HookBegin(int g, string room)
        {
            _hookOpen = true; _hookG = g; _hookRoom = room ?? "";
            _hookTaken = false; _hookExited = false; _hookPhase = false; _hookFirstDone = false;
            _hookInc = _hookOrphan ? K.INC_FIRST : 0;
            _hookOrphan = false;
            _hookLost = 0;
            _frzValid = false;
            Array.Clear(_cost, 0, _cost.Length);
            Array.Clear(_faultLogged, 0, _faultLogged.Length);
        }

        /// <summary>The first phase's player order (roles, at most PO_CAP) and
        /// each role's held cards (at most HELD_CAP references; the true count
        /// beside them).</summary>
        private static void FirstPhase(Ev e)
        {
            var pm = PlayerManager.instance;
            if (pm == null || pm.players == null) return;
            var ps = pm.players;
            for (int i = 0; i < ps.Count && i < PLAYER_SCAN_CAP; i++)
            {
                int r = RoleOf(ps[i]);
                if (e.PoN < K.PO_CAP) e.Po[e.PoN++] = r;
                if (r >= 0 && e.HeldN[r] < 0) HeldOf(ps[i], e.Held[r], e.HeldN, r);
            }
        }

        private static void HeldOf(Player p, CardInfo[] into, int[] counts, int r)
        {
            try
            {
                var cur = p.data != null ? p.data.currentCards : null;
                if (cur == null) return;
                int n = cur.Count;
                for (int i = 0; i < n && i < K.HELD_CAP; i++) into[i] = cur[i];
                counts[r] = n;
            }
            catch { counts[r] = -1; }
        }

        // -- reads (never writes) -------------------------------------------------------------------

        /// <summary>An online 1v1 fighter room: the room predicate the seat
        /// evidence start block uses (GameStateWatcher oneVOneMatchAtStart),
        /// plus not a spectator and not the FFA engine.</summary>
        private static bool GateRoom()
        {
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode) return false;
                if (RoomActors.LocalIsSpectator) return false;
                if (FfaMode.EngineActive()) return false;
                var room = PhotonNetwork.CurrentRoom;
                string name = room != null ? (room.Name ?? "") : "";
                if (name.StartsWith("ovt_", StringComparison.Ordinal) || name.StartsWith("team_", StringComparison.Ordinal)
                    || name.StartsWith("ffa_", StringComparison.Ordinal)) return false;
                if (room != null && room.CustomProperties != null && room.CustomProperties.ContainsKey("cr_ff")) return false;
                return RoomActors.ActiveFighterCount() == 2;
            }
            catch { return false; }
        }

        private static string RoomName()
        {
            try { return PhotonNetwork.CurrentRoom != null ? (PhotonNetwork.CurrentRoom.Name ?? "") : ""; } catch { return ""; }
        }

        private static Player PlayerById(int id)
        {
            var pm = PlayerManager.instance;
            return pm != null && id >= 0 ? pm.GetPlayerWithID(id) : null;
        }

        /// <summary>0 = this seat's own player, 1 = another player, -1 unresolved.</summary>
        private static int RoleOf(Player p)
        {
            if (p == null || p.data == null || p.data.view == null) return -1;
            return p.data.view.IsMine ? 0 : 1;
        }

        private static int ActorOf(Player p)
        {
            if (p == null || p.data == null || p.data.view == null) return 0;
            return p.data.view.ControllerActorNr;
        }

        private static void Rounds(out int rs, out int ro)
        {
            rs = ro = 0;
            var gm = GM_ArmsRace.instance;
            var pm = PlayerManager.instance;
            if (gm == null || pm == null || pm.players == null) return;
            int team = -1;
            var ps = pm.players;
            for (int i = 0; i < ps.Count && i < PLAYER_SCAN_CAP; i++) if (RoleOf(ps[i]) == 0) { team = ps[i].TeamID; break; }
            if (team == 0) { rs = gm.p1Rounds; ro = gm.p2Rounds; }
            else if (team == 1) { rs = gm.p2Rounds; ro = gm.p1Rounds; }
        }

        private static int SharedNow()
        {
            try { return VanillaCardSequence.SharedSlotsServed; } catch { return -1; }
        }

        /// <summary>The picker as a deal opens (findings M1, M3): the game's
        /// own lock predicate for the held side (1 the held gun is locked, 0
        /// not locked or no gun, -1 unread), the held count on this seat, and
        /// the engine's draw index for an own deal. Read with every spawn and
        /// end-pick; the core keeps the reading of the event that opens a deal.</summary>
        private static void Facts(Ev e)
        {
            var p = _picker;
            try
            {
                var holding = p != null && p.data != null ? p.data.GetComponent<Holding>() : null;
                if (holding != null)
                {
                    var gun = holding.holdable != null ? holding.holdable.GetComponent<Gun>() : null;
                    e.Gl = gun != null && gun.lockGunToDefault ? 1 : 0;
                }
            }
            catch { e.Gl = -1; }
            try { if (p != null && p.data != null && p.data.currentCards != null) e.Hn = p.data.currentCards.Count; } catch { e.Hn = -1; }
            try { if (RoleOf(p) == 0) e.Sq = FfaCardSequence.DrawIndexOf(p.PlayerID); } catch { e.Sq = -1; }
        }

        private static CardInfo SourceOfView(int viewId)
        {
            var v = PhotonNetwork.GetPhotonView(viewId);
            var info = v != null ? v.GetComponent<CardInfo>() : null;
            return info != null ? info.sourceCard : null;
        }

        private static void CardOf(ApplyCardStats stats, Ev e)
        {
            if (stats == null) return;
            var info = stats.GetComponent<CardInfo>();
            e.Src = info != null ? info.sourceCard : null;
            var v = stats.GetComponent<PhotonView>();
            e.Vid = v != null ? v.ViewID : -1;
        }

        // -- room exit, the room reset, the dispatch -----------------------------------------------

        /// <summary>The left-room edge: collecting stops. The game is sealed
        /// only by a dispatch for the same room within FROZEN_MS (a game cut
        /// short by a leave or a drop); otherwise it never becomes a record.</summary>
        internal static void RoomExit()
        {
            try
            {
                if (_hookOpen && !_hookExited) { _hookExited = true; _hookExitedAtMs = _sw.ElapsedMilliseconds; }
                else if (_hookExited) _hookOpen = false;
            }
            catch { }
        }

        /// <summary>From Plugin's two room-reset sites, immediately BEFORE
        /// RoomRules.ResetLatched and VanillaCardSequence.OnRoomLeft (CD-M2):
        /// the Same Cards rule and its verdict, the served-slot counter and the
        /// rules record of the game in progress, as they stood. Once per game:
        /// a second reset reads values the first already cleared.</summary>
        internal static void FreezeRoomFacts()
        {
            try
            {
                if (!_hookOpen || _hookTaken || (_frzValid && _frzRoom == _hookRoom)) return;
                _frzRoom = _hookRoom; _frzValid = true;
                _frzRule = -1; _frzVerdict = -1; _frzShared = -1; _frzProp = null;
                try
                {
                    _frzRule = RoomRules.SameCards ? 1 : 0;
                    _frzVerdict = _frzRule == 0 ? 0 : (FfaCardSequence.ActiveThisGame ? 1 : 2);
                }
                catch { _frzRule = -1; _frzVerdict = -1; }
                try { _frzShared = VanillaCardSequence.SharedSlotsServed; } catch { _frzShared = -1; }
                try { _frzProp = RoomRules.LatchedProp; } catch { _frzProp = null; }
            }
            catch { }
        }

        private static string _noRecordNote;

        /// <summary>After the seat evidence dispatch (game over, or a game cut
        /// short). Ranked only, both seats. SEALS the game in O(1) (CD-M1, F4):
        /// from here no collector records for it (the hooks check the taken
        /// flag first), and one seal event carries the seat ids, the attach
        /// key, the end kind, the Same Cards rule, its verdict, the closing
        /// served-slot counter and the rules record (frozen before a room
        /// reset when one happened, read live otherwise, -1 / NOT-RUN when
        /// neither exists: CD-M2), the build tuple, the cost rows and the
        /// incompleteness bits. Validation, the census check, the build, the
        /// budget, the signature and the queue are the tick's.</summary>
        internal static void Dispatch(string seat, string other, string attach, bool rankedNow)
        {
            try
            {
                if (!_hookOpen || _hookTaken) return;
                if (_hookExited && _sw.ElapsedMilliseconds - _hookExitedAtMs > FROZEN_MS) return;
                if (_hookRoom.Length == 0 || attach == null || !attach.StartsWith(_hookRoom + "_", StringComparison.Ordinal)) return;
                _hookTaken = true;
                var e = Push(EV_SEAL);
                if (e == null) { _noRecordNote = " no record: the capture buffer was full at the dispatch"; return; }
                e.Keep = rankedNow || CardDrawEvidenceTestGate.On;
                e.Seat = seat; e.Other = other; e.Attach = attach;
                try { e.End = SeatEvidence.NotedEnd; } catch { e.End = null; }
                if (_frzValid && _frzRoom == _hookRoom)
                {
                    e.Rule = _frzRule; e.Verdict = _frzVerdict; e.Closing = _frzShared; e.RulesProp = _frzProp;
                }
                else if (!_hookExited)
                {
                    try
                    {
                        e.Rule = RoomRules.SameCards ? 1 : 0;
                        e.Verdict = e.Rule == 0 ? 0 : (FfaCardSequence.ActiveThisGame ? 1 : 2);
                    }
                    catch { e.Rule = -1; e.Verdict = -1; }
                    e.Closing = SharedNow();
                    try { e.RulesProp = RoomRules.LatchedProp; } catch { e.RulesProp = null; }
                }
                try { e.BuildValue = PeerBuild.BuildValue(); } catch { e.BuildValue = null; }
                e.Inc = _hookInc | (_hookLost > 0 ? K.INC_LOST : 0);
                Array.Copy(_cost, e.Cost, _cost.Length);
                e.Faulted = false;
            }
            catch
            {
                _noRecordNote = " no record: the capture failed";
            }
        }

        // ===================================================================================
        // The tick side: everything variable, outside combat
        // ===================================================================================

        /// <summary>One pool's census (CD-M4): taken fresh for every game from
        /// the pool array its first phase named, and again at the build.</summary>
        private sealed class Census
        {
            internal readonly Dictionary<CardInfo, int> Ix = new Dictionary<CardInfo, int>();
            internal string[] Canon = new string[0];
            internal int[] Rar = new int[0];
            internal string Text = "", Digest = "";
            internal bool Collision, Ok;
            internal int Count;
        }

        private static bool _poolClassLogged;

        private static Census TakeCensus(CardInfo[] cards)
        {
            var c = new Census();
            if (cards == null) return c;
            try
            {
                c.Count = cards.Length;
                var canon = new string[cards.Length];
                var rar = new int[cards.Length];
                var census = new List<K.CensusCard>(cards.Length);
                var cats = new List<KeyValuePair<int, string>>();
                for (int i = 0; i < cards.Length; i++)
                {
                    var card = cards[i];
                    if (card == null) { canon[i] = ""; rar[i] = -1; census.Add(new K.CensusCard { Name = "" }); continue; }
                    if (!c.Ix.ContainsKey(card)) c.Ix[card] = i;
                    string nm = card.gameObject.name;
                    string cn = nm;
                    try { cn = CardRarityLookup.GetCanonicalName(nm) ?? nm; } catch { }
                    canon[i] = cn;
                    rar[i] = (int)card.rarity;
                    Gun gun = null;
                    try { gun = card.GetComponent<Gun>(); } catch { }
                    census.Add(new K.CensusCard
                    {
                        Name = nm, Rarity = (int)card.rarity, AllowMultiple = card.allowMultiple,
                        Categories = CatNames(card.categories, cats), Blacklisted = CatNames(card.blacklistedCategories, cats),
                        Lock = gun != null && gun.lockGunToDefault,
                    });
                }
                c.Canon = canon; c.Rar = rar;
                c.Text = K.CensusText(census);
                c.Digest = K.CensusDigest(c.Text);
                c.Collision = K.CategoryNameCollision(cats);
                c.Ok = true;
            }
            catch { c.Ok = false; }
            if (c.Ok && !_poolClassLogged)
            {
                _poolClassLogged = true;
                string pool = "?";
                try
                {
                    var f = AccessTools.Field(typeof(PhotonNetwork), "prefabPool");
                    object v = f != null ? f.GetValue(null) : null;
                    pool = v != null ? v.GetType().Name : "unset";
                }
                catch { }
                Plugin.Log.LogInfo(TAG + " census: " + c.Count.ToString(CultureInfo.InvariantCulture) + " cards, digest "
                                   + c.Digest + ", pool class " + pool + (c.Collision ? ", CATEGORY NAME COLLISION (records read pool state collision)" : ""));
            }
            return c;
        }

        private static string[] CatNames(CardCategory[] a, List<KeyValuePair<int, string>> cats)
        {
            if (a == null) return null;
            var r = new string[a.Length];
            for (int i = 0; i < a.Length; i++)
            {
                if (a[i] == null) { r[i] = null; continue; }
                r[i] = a[i].name ?? "";
                cats.Add(new KeyValuePair<int, string>(a[i].GetInstanceID(), r[i]));
            }
            return r;
        }

        // the tick's game: built from the events in order
        private static K.CardGame _game;
        private static int _dG = -1;
        private static string _dRoom;
        private static CardInfo[] _dPool;
        private static Census _dCensus;

        private static int IndexOf(CardInfo source)
        {
            int i;
            return source != null && _dCensus != null && _dCensus.Ix.TryGetValue(source, out i) ? i : -1;
        }

        private static K.DealFacts FactsOf(Ev e) { return new K.DealFacts(e.Gl, e.Hn, e.Sq); }

        /// <summary>Tick, outside combat (and the quitting path): every event
        /// the hooks pushed, in order. A fault here marks the game it hit.</summary>
        private static void DrainEvents()
        {
            int n = _evCount;
            for (int k = 0; k < n && k < EV_CAP; k++)
            {
                var e = _ring[_evHead];
                _evHead = (_evHead + 1) % EV_CAP;
                _evCount--;
                try { Take(e); }
                catch (Exception ex)
                {
                    if (_game != null) _game.Inc |= K.INC_FAULT;
                    try { Plugin.Log.LogWarning(TAG + " event not taken: " + ex.GetType().Name); } catch { }
                }
            }
        }

        private static bool Current(Ev e)
        {
            return _game != null && !_game.Sealed && e.G == _dG && e.Room == _dRoom;
        }

        private static void Take(Ev e)
        {
            if (e.Kind == EV_PHASE)
            {
                if (!Current(e)) DrainBegin(e);
                else if (e.Pool != null && !ReferenceEquals(e.Pool, _dPool)) _game.PoolState = K.POOL_CHANGED;
                if (e.Faulted) _game.Inc |= K.INC_FAULT;
                _game.OpenPhase(e.Role, e.Picks, e.Rs, e.Ro, e.Shared);
                return;
            }
            if (e.Kind == EV_SEAL) { SealGame(e); return; }
            if (!Current(e)) return;                 // no game to go to (its phase was never seen, or it is sealed)
            if (e.Faulted) { _game.Inc |= K.INC_FAULT; return; }
            switch (e.Kind)
            {
                case EV_SPAWN:
                    _game.Spawn(IndexOf(e.Src), e.Creator, FactsOf(e), e.Shared);
                    return;
                case EV_ENDPICK:
                {
                    var slots = new List<long>();
                    for (int i = 0; i < e.SlotN && i < K.SL_CAP; i++) slots.Add(IndexOf(e.Slots[i]));
                    _game.EndPick(slots, e.SlotN, e.Pi, e.Vid, e.Pk, e.Wp, e.SenderOk, FactsOf(e), e.Shared);
                    return;
                }
                case EV_DONE:
                    _game.DonePicking(e.Shared);
                    return;
                case EV_APPLY:
                {
                    int ix = IndexOf(e.Src);
                    for (int i = 0; i < e.TgtN && i < TARGET_CAP; i++) _game.Apply(e.Tgt[i], ix, e.ApKind, e.Vid, e.Outcome);
                    if (e.TgtN > TARGET_CAP && e.Outcome == K.APPLY_DONE) _game.ApOmit += e.TgtN - TARGET_CAP;
                    return;
                }
            }
        }

        /// <summary>A game's first event on the tick: a fresh census of the
        /// pool its phase named (CD-M4), and the player order and held cards
        /// only when this is the game's first phase, captured whole (CD-M3).</summary>
        private static void DrainBegin(Ev e)
        {
            _game = null;
            _dG = e.G; _dRoom = e.Room; _dPool = e.Pool;
            var c = TakeCensus(e.Pool);
            _dCensus = c;
            bool derivable = e.First && !e.Faulted;
            List<int> po = null;
            IList<int>[] held = { null, null };
            if (derivable)
            {
                po = new List<int>();
                for (int i = 0; i < e.PoN && i < K.PO_CAP; i++) po.Add(e.Po[i]);
                for (int r = 0; r < 2; r++)
                {
                    if (e.HeldN[r] < 0) continue;
                    var l = new List<int>();
                    for (int i = 0; i < e.HeldN[r] && i < K.HELD_CAP; i++) l.Add(IndexOf(e.Held[r][i]));
                    held[r] = l;
                }
            }
            var game = new K.CardGame(e.G, e.Ns, VanillaCardSequence.OpeningDraws, c.Ok ? c.Count : e.PoolLen,
                                      c.Ok ? c.Digest : "", c.Canon, c.Rar, po, held);
            game.PoolState = !c.Ok ? K.POOL_NOT_RUN : (c.Collision ? K.POOL_COLLISION : K.POOL_OK);
            for (int r = 0; r < 2; r++) if (derivable && e.HeldN[r] > K.HELD_CAP) game.Held0Omit[r] += e.HeldN[r] - K.HELD_CAP;
            if (!derivable) game.Inc |= K.INC_FIRST;
            _game = game;
        }

        /// <summary>A game's record as the dispatch sealed it; built on the tick.</summary>
        private sealed class Pending
        {
            internal K.CardGame Game;
            internal CardInfo[] PoolRef;
            internal string Seat, Other, Attach, End, BuildValue, Text, Env;
            internal int Rule, Verdict;
            internal long[][] Cost;
            internal K.Profile Prof;
            internal bool Checked;
        }

        private const int PENDING_CAP = 4;
        private static readonly List<Pending> _pending = new List<Pending>();
        private static long _nextBuildMs;
        private static bool _buildFailLogged;

        private static void SealGame(Ev e)
        {
            if (e.Faulted || !Current(e))
            {
                if (e.Keep) _noRecordNote = " no record: the game the dispatch sealed was not captured";
                return;
            }
            var game = _game;
            game.Close(e.Closing);
            game.Inc |= e.Inc;
            game.Seal();
            if (!e.Keep) return;          // a casual game is never built
            var cost = new long[K.COLLECTORS][];
            for (int i = 0; i < K.COLLECTORS; i++) { cost[i] = new long[COST_W]; Array.Copy(e.Cost, i * COST_W, cost[i], 0, COST_W); }
            if (_pending.Count >= PENDING_CAP) { _pending.RemoveAt(0); _noRecordNote = " a captured record was dropped before it was persisted: too many waiting"; }
            _pending.Add(new Pending
            {
                Game = game, PoolRef = _dPool, Seat = e.Seat, Other = e.Other, Attach = e.Attach, End = e.End,
                BuildValue = e.BuildValue, Rule = e.Rule, Verdict = e.Verdict, Cost = cost,
                Prof = new K.Profile { Rules = e.RulesProp ?? "" },
            });
            _nextBuildMs = 0;
        }

        private static void DrainNotes()
        {
            for (int i = 0; i < K.COLLECTORS; i++)
            {
                string n = _faultNote[i];
                if (n == null) continue;
                _faultNote[i] = null;
                Plugin.Log.LogWarning(TAG + " C" + (i + 1).ToString(CultureInfo.InvariantCulture) + " fault (counted, once per game): " + n);
            }
            if (_noRecordNote != null)
            {
                string n = _noRecordNote; _noRecordNote = null;
                Plugin.Log.LogWarning(TAG + n);
            }
        }

        /// <summary>From Plugin's persistent tick, ABOVE its modDisabled
        /// return: the deferred lines always; outside combat (current frame)
        /// the events, the seals and the captured records' builds.</summary>
        internal static void Tick()
        {
            try
            {
                DrainNotes();
                if (SeatEvidence.CombatLive()) return;
                DrainEvents();
                BuildPending(false);
            }
            catch { }
        }

        /// <summary>Application.quitting, after the seat evidence quit flush:
        /// the events are taken and every sealed record is built now (no later
        /// frame comes) and written to its own closing file, never the queue
        /// (F3); the next launch's first queue load moves it in.</summary>
        internal static void FlushOnQuit()
        {
            try { DrainNotes(); DrainEvents(); BuildPending(true); } catch { }
        }

        /// <summary>Whether the game DLL identity is complete (F7). Not yet:
        /// the boot hash is started (a no-op once running) and the build
        /// waits, except on the quitting path, which completes it on this
        /// thread.</summary>
        private static bool IdentityReadyOrStart(bool now)
        {
            bool ready = false;
            try { ready = SeatEvidence.IdentityReady; } catch { }
            if (ready) return true;
            if (now)
            {
                try { SeatEvidence.CompleteIdentityNow(); } catch { }
                return true;
            }
            try { SeatEvidence.StartHashing(); } catch { }
            return false;
        }

        /// <summary>Builds and persists the sealed records. A build waits for
        /// the completed identities (F7). First the seat ids and the game key
        /// are validated and the pool's census is taken again: a digest that
        /// differs from the game's own reads pool state "changed" (CD-M4). On
        /// the tick a record is reported as queued only after the queue file
        /// holding it replaced the old one (F8); until then it stays, its bytes
        /// kept, and is tried again every 5 s. On the quitting path (now) it
        /// goes to its own closing file (F3).</summary>
        private static void BuildPending(bool now)
        {
            if (_pending.Count == 0) return;
            if (!now && _sw.ElapsedMilliseconds < _nextBuildMs) return;
            if (!IdentityReadyOrStart(now)) return;
            int i = 0;
            while (i < _pending.Count)
            {
                var p = _pending[i];
                try
                {
                    if (p.Env == null)
                    {
                        string stable = SeatEvidence.StableOf(p.Attach);
                        if (stable == null || !SeatEvidenceCore.IsSteamId(p.Seat) || !SeatEvidenceCore.IsSteamId(p.Other))
                        {
                            _pending.RemoveAt(i);
                            Plugin.Log.LogWarning(TAG + " no record: game key or seat ids outside the contract");
                            continue;
                        }
                        if (!p.Checked)
                        {
                            p.Checked = true;
                            var again = TakeCensus(p.PoolRef);
                            if (!again.Ok) p.Game.PoolState = K.POOL_NOT_RUN;
                            else if (again.Digest != p.Game.Digest && p.Game.PoolState == K.POOL_OK) p.Game.PoolState = K.POOL_CHANGED;
                        }
                        var prof = p.Prof;
                        prof.GameSha = SeatEvidence.GameDllSha; prof.GameState = SeatEvidence.GameDllState;
                        prof.ModSha = SeatEvidence.OwnDllSha; prof.ModState = SeatEvidence.OwnDllState;
                        prof.Build = SeatEvidenceCore.SplitBuild(p.BuildValue) ?? new[] { "", "", "" };
                        string text = K.Budget(p.Game.Record(p.End, prof, p.Rule, p.Verdict, p.Cost));
                        string sig = ApiClient.SeatEvidenceSig(K.Canonical(p.Seat, p.Other, stable, p.Attach, text));
                        string env = K.Envelope(p.Seat, p.Other, stable, p.Attach, text, sig);
                        if (env == null)
                        {
                            _pending.RemoveAt(i);
                            Plugin.Log.LogWarning(TAG + " no record: the envelope is outside the contract");
                            continue;
                        }
                        p.Text = text; p.Env = env;
                    }
                    bool persisted = now ? SeatEvidence.SpoolClosing("k", p.Env) : SeatEvidence.EnqueueCard(p.Env);
                    if (!persisted)
                    {
                        _nextBuildMs = _sw.ElapsedMilliseconds + 5000;
                        if (!_buildFailLogged)
                        {
                            _buildFailLogged = true;
                            Plugin.Log.LogWarning(TAG + " record not persisted yet (the queue file was not replaced): kept and tried again");
                        }
                        return;
                    }
                    _pending.RemoveAt(i);
                    _buildFailLogged = false;
                    var game = p.Game;
                    Plugin.Log.LogInfo(TAG + (now ? " record kept for the next launch: " : " record queued: ")
                        + p.Text.Length.ToString(CultureInfo.InvariantCulture) + " bytes, phases "
                        + (game.Tot[0][0] + game.Tot[1][0]).ToString(CultureInfo.InvariantCulture) + ", hands "
                        + (game.Tot[0][1] + game.Tot[1][1]).ToString(CultureInfo.InvariantCulture) + ", inc "
                        + game.Inc.ToString(CultureInfo.InvariantCulture) + ", pool " + game.PoolState + ", end " + (p.End ?? "game_over")
                        + (CardDrawEvidenceTestGate.On ? ", TEST GATE OVERRIDE" : ""));
                }
                catch (Exception ex)
                {
                    _pending.RemoveAt(i);
                    try { Plugin.Log.LogWarning(TAG + " no record: " + ex.GetType().Name); } catch { }
                }
            }
        }

        // -- boot line (bar A1) ---------------------------------------------------------------------

        private static readonly string[][] HOOKS =
        {
            new[] { "C1", "CardChoice", "StartPick", "CardDrawEvidence_StartPickPatch" },
            new[] { "C2", "CardInfo", "Awake", "CardDrawEvidence_CardAwakePatch" },
            new[] { "C3", "CardChoice", "RPCA_DoEndPick", "CardDrawEvidence_EndPickPatch" },
            new[] { "C4", "CardChoice", "RPCA_DonePicking", "CardDrawEvidence_DonePickingPatch" },
            new[] { "C5", "ApplyCardStats", "RPCA_Pick", "CardDrawEvidence_PickPatch" },
            new[] { "C6", "ApplyCardStats", "OFFLINE_Pick", "CardDrawEvidence_OfflinePickPatch" },
        };

        /// <summary>Once after patching: one line listing the six patches
        /// attached (an Error line names any that is not).</summary>
        internal static void BootLine()
        {
            try
            {
                var types = new Dictionary<string, Type>
                {
                    { "CardChoice", typeof(CardChoice) }, { "CardInfo", typeof(CardInfo) }, { "ApplyCardStats", typeof(ApplyCardStats) },
                };
                var ok = new List<string>();
                var bad = new List<string>();
                foreach (var h in HOOKS)
                {
                    bool attached = false;
                    try
                    {
                        var m = AccessTools.Method(types[h[1]], h[2]);
                        var info = m != null ? Harmony.GetPatchInfo(m) : null;
                        if (info != null)
                            foreach (var p in info.Prefixes.Concat(info.Postfixes).Concat(info.Finalizers))
                                if (p.PatchMethod != null && p.PatchMethod.DeclaringType != null && p.PatchMethod.DeclaringType.Name == h[3]) attached = true;
                    }
                    catch { attached = false; }
                    (attached ? ok : bad).Add(h[0] + " " + h[1] + "." + h[2]);
                }
                string line = TAG + " card draw evidence patches attached " + ok.Count.ToString(CultureInfo.InvariantCulture) + "/" + HOOKS.Length.ToString(CultureInfo.InvariantCulture)
                              + ": " + string.Join(", ", ok.ToArray());
                if (bad.Count == 0) Plugin.Log.LogInfo(line);
                else Plugin.Log.LogError(line + "; NOT attached: " + string.Join(", ", bad.ToArray()));
                if (CardDrawEvidenceTestGate.On) Plugin.Log.LogWarning(TAG + " test gate override present: " + CardDrawEvidenceTestGate.Marker);
            }
            catch (Exception ex)
            {
                try { Plugin.Log.LogWarning(TAG + " boot line failed: " + ex.GetType().Name); } catch { }
            }
        }

        // -- the census dump lever (menu only, cfg-gated, off by default) ----------------------------

        private static bool _dumpDone;
        private static bool _dumpBound, _dumpOn;
        private static long _dumpWaitFromMs = -1;
        internal const long DUMP_HASH_WAIT_MS = 15000;

        /// <summary>From Plugin's persistent tick, at the menu (never in a
        /// room). Binds [Debug] CardPoolCensusDump; when it is true, writes
        /// this seat's census once per process to
        /// BepInEx/config/CompetitiveRounds.card-census.json (the reference
        /// census the integrator registers) and logs its digest. A category
        /// name shared by two category objects fails the dump.</summary>
        internal static void EnsureCensusDump()
        {
            try
            {
                if (_dumpDone) return;
                if (CardChoice.instance == null || PhotonNetwork.InRoom) return;
                if (!_dumpBound)
                {
                    _dumpBound = true;
                    var cf = Plugin.ConfigFileForLevers;
                    if (cf != null)
                        _dumpOn = cf.Bind("Debug", "CardPoolCensusDump", false,
                            "Development only: at the menu, write this seat's card pool census (the attributes the deal's rules read) and its digest to CompetitiveRounds.card-census.json in the config folder, once per launch. Nothing is sent.").Value;
                    if (!_dumpOn) { _dumpDone = true; return; }
                    _dumpWaitFromMs = _sw.ElapsedMilliseconds;
                }
                string state = "", sha = "";
                try { state = SeatEvidence.GameDllState; sha = SeatEvidence.GameDllSha; } catch { }
                if (state == SeatEvidence.ID_PENDING)
                {
                    // the boot hash is still running: wait (bounded), then take
                    // the identity completed on this thread
                    if (_sw.ElapsedMilliseconds - _dumpWaitFromMs < DUMP_HASH_WAIT_MS) return;
                    try { SeatEvidence.CompleteIdentityNow(); } catch { }
                    try { state = SeatEvidence.GameDllState; sha = SeatEvidence.GameDllSha; } catch { }
                }
                _dumpDone = true;
                var cards = CardChoice.instance.cards;
                var c = TakeCensus(cards);
                if (!c.Ok)
                {
                    Plugin.Log.LogError(TAG + " census dump FAILED: the pool could not be read; nothing written");
                    return;
                }
                if (c.Collision)
                {
                    Plugin.Log.LogError(TAG + " census dump FAILED: two category objects share a name; nothing written");
                    return;
                }
                int ns = CardChoice.instance.transform.childCount;
                var o = new SeatEvidenceCore.JObj().Add("census_version", 1L).Add("digest", c.Digest)
                    .Add("card_count", (long)c.Count).Add("slot_count", (long)ns)
                    .Add("game_dll", new List<object> { state == "ok" ? sha : "", state == "ok" ? "ok" : state })
                    .Add("census_text", c.Text);
                const string FILE = "CompetitiveRounds.card-census.json";
                File.WriteAllText(Path.Combine(Paths.ConfigPath, FILE), SeatEvidenceCore.Json(o), new UTF8Encoding(false));
                Plugin.Log.LogInfo(TAG + " census dump written to " + FILE + ": digest " + c.Digest + ", "
                                   + c.Count.ToString(CultureInfo.InvariantCulture) + " cards, " + ns.ToString(CultureInfo.InvariantCulture) + " slots");
            }
            catch (Exception ex)
            {
                _dumpDone = true;
                try { Plugin.Log.LogWarning(TAG + " census dump failed: " + ex.GetType().Name); } catch { }
            }
        }
    }

    /// <summary>Test-only collector-gate override (finding L3). Defined in no
    /// build configuration: with SCR_CARD_EVIDENCE_TEST_GATE a casual 1v1 game
    /// also yields a record (bar A8's casual negative control). The marker
    /// string exists only to be probed: tools/tests/card-draw-hooks byte-scans
    /// builds for it.</summary>
    internal static class CardDrawEvidenceTestGate
    {
        internal static string Marker = "";

        internal static bool On
        {
            get
            {
#if SCR_CARD_EVIDENCE_TEST_GATE
                Marker = "SCR_CARD_EVIDENCE_TEST_GATE_ON";
                return true;
#else
                return false;
#endif
            }
        }
    }

    /// <summary>C1: a phase opens on every seat for every picker (vanilla
    /// CardChoice.StartPick sets pickrID and picks, then Pick() starts the
    /// owner's deal, whose first spawn waits 0.2 s). Last, so the sibling
    /// prefixes' picks and pickrID are what it reads.</summary>
    [HarmonyPatch(typeof(CardChoice), "StartPick")]
    [HarmonyPriority(Priority.Last)]
    internal static class CardDrawEvidence_StartPickPatch
    {
        [HarmonyPostfix]
        private static void Postfix(CardChoice __instance)
        {
            try { CardDrawEvidence.PhaseStarted(__instance); } catch { }
        }
    }

    /// <summary>C2: a card object woke; a network spawn has its view id
    /// already (PUN assigns ids before activation).</summary>
    [HarmonyPatch(typeof(CardInfo), "Awake")]
    internal static class CardDrawEvidence_CardAwakePatch
    {
        [HarmonyPostfix]
        private static void Postfix(CardInfo __instance)
        {
            try { CardDrawEvidence.CardAwake(__instance); } catch { }
        }
    }

    /// <summary>C3: the end-pick, read before the body dereferences the ids.</summary>
    [HarmonyPatch(typeof(CardChoice), "RPCA_DoEndPick")]
    internal static class CardDrawEvidence_EndPickPatch
    {
        [HarmonyPrefix]
        private static void Prefix(int[] __0, int __1, int __2, int __3)
        {
            try { CardDrawEvidence.EndPick(__0, __1, __2, __3); } catch { }
        }
    }

    /// <summary>C4: the phase end.</summary>
    [HarmonyPatch(typeof(CardChoice), "RPCA_DonePicking")]
    internal static class CardDrawEvidence_DonePickingPatch
    {
        [HarmonyPrefix]
        private static void Prefix()
        {
            try { CardDrawEvidence.DonePicking(); } catch { }
        }
    }

    /// <summary>C5: a card applied by RPC, read AFTER the original (CD-M1).
    /// The postfix runs only when the original returned: __runOriginal says
    /// whether it ran (a sibling prefix may have skipped it). The finalizer
    /// reports an original that threw, and returns its exception unchanged.
    /// Last, and neither ever changes the call.</summary>
    [HarmonyPatch(typeof(ApplyCardStats), "RPCA_Pick")]
    [HarmonyPriority(Priority.Last)]
    internal static class CardDrawEvidence_PickPatch
    {
        [HarmonyPostfix]
        private static void Postfix(ApplyCardStats __instance, int[] __0, bool __runOriginal)
        {
            try { CardDrawEvidence.PickApplied(__instance, __0, __runOriginal ? CardDrawEvidenceCore.APPLY_DONE : CardDrawEvidenceCore.APPLY_SKIPPED); } catch { }
        }

        [HarmonyFinalizer]
        private static Exception Finalizer(ApplyCardStats __instance, int[] __0, Exception __exception)
        {
            try { if (__exception != null) CardDrawEvidence.PickApplied(__instance, __0, CardDrawEvidenceCore.APPLY_FAULTED); } catch { }
            return __exception;
        }
    }

    /// <summary>C6: a card applied by the offline path (the client's
    /// replays), read after the original as C5.</summary>
    [HarmonyPatch(typeof(ApplyCardStats), "OFFLINE_Pick")]
    [HarmonyPriority(Priority.Last)]
    internal static class CardDrawEvidence_OfflinePickPatch
    {
        [HarmonyPostfix]
        private static void Postfix(ApplyCardStats __instance, Player[] __0, bool __runOriginal)
        {
            try { CardDrawEvidence.OfflinePickApplied(__instance, __0, __runOriginal ? CardDrawEvidenceCore.APPLY_DONE : CardDrawEvidenceCore.APPLY_SKIPPED); } catch { }
        }

        [HarmonyFinalizer]
        private static Exception Finalizer(ApplyCardStats __instance, Player[] __0, Exception __exception)
        {
            try { if (__exception != null) CardDrawEvidence.OfflinePickApplied(__instance, __0, CardDrawEvidenceCore.APPLY_FAULTED); } catch { }
            return __exception;
        }
    }
}
