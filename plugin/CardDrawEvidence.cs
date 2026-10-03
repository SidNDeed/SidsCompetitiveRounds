using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
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
    /// RPCA_DonePicking, C5 RPCA_Pick, C6 OFFLINE_Pick) that resolve the game's
    /// objects into pool indexes and roles and hand them to
    /// CardDrawEvidenceCore, the census of this seat's own pool, the game-over
    /// build, and the [Debug] CardPoolCensusDump lever.
    ///
    /// Containment: every hook wraps its one call in try/catch; every
    /// collector body runs inside its own try/catch that counts the fault in
    /// the record. No collector writes a field the game reads, changes a hand,
    /// a card, a pick, picks, pickrID, IsPicking, spawnedCards, currentCards or
    /// a card bar, starts a coroutine, creates or destroys an object, or reads
    /// the game's random generator. Nothing is sent to other players.
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

        private static K.CardGame _game;
        private static int _g = -1;
        private static string _room = "";
        private static bool _exited, _taken;
        private static long _exitedAtMs;

        // the open phase's picker on this seat
        private static Player _picker;
        private static int _pickerActor;

        // this seat's pool (CardChoice.cards), rebuilt only when the array changes
        private static CardInfo[] _poolRef;
        private static readonly Dictionary<CardInfo, int> _ix = new Dictionary<CardInfo, int>();
        private static string _censusText = "", _digest = "";
        private static string[] _canon = new string[0];
        private static int[] _rar = new int[0];
        private static bool _censusCollision, _poolClassLogged;

        // per collector: calls, total_us, max_us, faults, in_combat
        private static readonly long[][] _cost = NewCost();
        private static readonly bool[] _faultLogged = new bool[K.COLLECTORS];

        private static long[][] NewCost()
        {
            var c = new long[K.COLLECTORS][];
            for (int i = 0; i < c.Length; i++) c[i] = new long[5];
            return c;
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
                var c = _cost[i];
                c[0]++; c[1] += us; if (us > c[2]) c[2] = us;
                if (InCombat()) c[4]++;
            }
            catch { }
        }

        // a fault's line, written by the tick (F4: the collector only counts)
        private static readonly string[] _faultNote = new string[K.COLLECTORS];

        private static void Fault(int i, Exception ex)
        {
            try
            {
                _cost[i][3]++;
                if (_faultLogged[i]) return;
                _faultLogged[i] = true;
                _faultNote[i] = ex != null ? ex.GetType().Name : "?";
            }
            catch { }
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

        // -- the six collectors (each: gate at the first line, body in its own try) ---------------

        /// <summary>C1, StartPick postfix: a phase opens; the first phase of a
        /// game resets the state and takes the census and held snapshots.</summary>
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
            if (_game == null || _exited || !_game.PhaseOpen) return;
            long t0 = Stopwatch.GetTimestamp();
            try { C2(card); } catch (Exception ex) { Fault(1, ex); }
            Cost(1, t0);
        }

        /// <summary>C3, RPCA_DoEndPick prefix: the hand in slot order and the pick.</summary>
        internal static void EndPick(int[] cardIds, int targetCardId, int theInt, int pickId)
        {
            if (_game == null || _exited || !_game.PhaseOpen) return;
            long t0 = Stopwatch.GetTimestamp();
            try { C3(cardIds, targetCardId, theInt, pickId); } catch (Exception ex) { Fault(2, ex); }
            Cost(2, t0);
        }

        /// <summary>C4, RPCA_DonePicking prefix: the phase is done.</summary>
        internal static void DonePicking()
        {
            if (_game == null || _exited || !_game.PhaseOpen) return;
            long t0 = Stopwatch.GetTimestamp();
            try { C4(); } catch (Exception ex) { Fault(3, ex); }
            Cost(3, t0);
        }

        /// <summary>C5, RPCA_Pick prefix (last): one application per actor.</summary>
        internal static void PickApplied(ApplyCardStats stats, int[] actorIds, bool runOriginal)
        {
            if (_game == null || _exited) return;
            long t0 = Stopwatch.GetTimestamp();
            try { C5(stats, actorIds, runOriginal); } catch (Exception ex) { Fault(4, ex); }
            Cost(4, t0);
        }

        /// <summary>C6, OFFLINE_Pick prefix (last): one application per player.</summary>
        internal static void OfflinePickApplied(ApplyCardStats stats, Player[] players, bool runOriginal)
        {
            if (_game == null || _exited) return;
            long t0 = Stopwatch.GetTimestamp();
            try { C6(stats, players, runOriginal); } catch (Exception ex) { Fault(5, ex); }
            Cost(5, t0);
        }

        private static void C1(CardChoice choice)
        {
            int g = VanillaCardSequence.Game;
            string room = RoomName();
            if (_game == null || _g != g || _room != room || _exited || _taken) Begin(choice, g, room);
            _picker = PlayerById(choice.pickrID);
            _pickerActor = ActorOf(_picker);
            int rs, ro;
            Rounds(out rs, out ro);
            _game.OpenPhase(RoleOf(_picker), choice.picks, rs, ro, SharedNow());
        }

        private static void C2(CardInfo card)
        {
            var view = card.GetComponent<PhotonView>();
            if (view == null || view.ViewID == 0) return;
            int creator = _pickerActor == 0 ? -1 : (view.CreatorActorNr == _pickerActor ? 1 : 0);
            var facts = _game.WantsFacts ? Facts() : new K.DealFacts(-1, -1, -1);
            _game.Spawn(IndexOf(card.sourceCard), creator, facts, SharedNow());
        }

        private static void C3(int[] cardIds, int targetCardId, int theInt, int pickId)
        {
            var slots = new List<long>(cardIds != null ? cardIds.Length : 0);
            if (cardIds != null) foreach (int id in cardIds) slots.Add(IndexOfView(id));
            int pi = cardIds != null ? Array.IndexOf(cardIds, targetCardId) : -1;
            int sender = HitEvidence.RpcSender;
            int senderOk = sender == 0 || _pickerActor == 0 ? -1 : (sender == _pickerActor ? 1 : 0);
            var facts = _game.WantsFacts ? Facts() : new K.DealFacts(-1, -1, -1);
            _game.EndPick(slots, pi, targetCardId, theInt, RoleOf(PlayerById(pickId)), senderOk, facts, SharedNow());
        }

        private static void C4()
        {
            _game.DonePicking(SharedNow());
        }

        private static void C5(ApplyCardStats stats, int[] actorIds, bool runOriginal)
        {
            if (actorIds == null) return;
            int ix, vid;
            CardOf(stats, out ix, out vid);
            var pm = PlayerManager.instance;
            foreach (int a in actorIds)
                _game.Apply(RoleOf(pm != null ? pm.GetPlayerWithActorID(a) : null), ix, 0, vid, runOriginal ? 0 : 1);
        }

        private static void C6(ApplyCardStats stats, Player[] players, bool runOriginal)
        {
            if (players == null) return;
            int ix, vid;
            CardOf(stats, out ix, out vid);
            foreach (var p in players) _game.Apply(RoleOf(p), ix, 1, vid, runOriginal ? 0 : 1);
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
            if (gm == null || pm == null) return;
            int team = -1;
            foreach (var p in pm.players) if (RoleOf(p) == 0) { team = p.TeamID; break; }
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
        /// the engine's draw index for an own deal.</summary>
        private static K.DealFacts Facts()
        {
            int gl = -1, sq = -1;
            long hn = -1;
            var p = _picker;
            try
            {
                var holding = p != null && p.data != null ? p.data.GetComponent<Holding>() : null;
                if (holding != null)
                {
                    var gun = holding.holdable != null ? holding.holdable.GetComponent<Gun>() : null;
                    gl = gun != null && gun.lockGunToDefault ? 1 : 0;
                }
            }
            catch { gl = -1; }
            try { if (p != null && p.data != null && p.data.currentCards != null) hn = p.data.currentCards.Count; } catch { hn = -1; }
            try { if (RoleOf(p) == 0) sq = FfaCardSequence.DrawIndexOf(p.PlayerID); } catch { sq = -1; }
            return new K.DealFacts(gl, hn, sq);
        }

        private static int IndexOf(CardInfo source)
        {
            int i;
            return source != null && _ix.TryGetValue(source, out i) ? i : -1;
        }

        private static long IndexOfView(int viewId)
        {
            var v = PhotonNetwork.GetPhotonView(viewId);
            var info = v != null ? v.GetComponent<CardInfo>() : null;
            return info != null ? IndexOf(info.sourceCard) : -1;
        }

        private static void CardOf(ApplyCardStats stats, out int ix, out int vid)
        {
            ix = -1; vid = -1;
            if (stats == null) return;
            var info = stats.GetComponent<CardInfo>();
            ix = info != null ? IndexOf(info.sourceCard) : -1;
            var v = stats.GetComponent<PhotonView>();
            vid = v != null ? v.ViewID : -1;
        }

        // -- the first phase of a game -------------------------------------------------------------

        private static void Begin(CardChoice choice, int g, string room)
        {
            _game = null;
            _g = g; _room = room; _exited = false; _taken = false;
            for (int i = 0; i < K.COLLECTORS; i++) { Array.Clear(_cost[i], 0, 5); _faultLogged[i] = false; }
            EnsurePool(choice);
            var pm = PlayerManager.instance;
            var po = new List<int>();
            var held = new List<int>[2];
            if (pm != null)
                foreach (var p in pm.players)
                {
                    int r = RoleOf(p);
                    po.Add(r);
                    if (r >= 0 && held[r] == null) held[r] = HeldOf(p);
                }
            int ns = choice != null ? choice.transform.childCount : 0;
            _game = new K.CardGame(g, ns, VanillaCardSequence.OpeningDraws, _poolRef != null ? _poolRef.Length : 0, _digest, _canon, _rar,
                                   po, new IList<int>[] { held[0], held[1] });
            _gameDigestPending = _censusCards != null;
        }

        private static List<int> HeldOf(Player p)
        {
            try
            {
                var cur = p.data.currentCards;
                if (cur == null) return null;
                var l = new List<int>(cur.Count);
                foreach (var c in cur) l.Add(IndexOf(c));
                return l;
            }
            catch { return null; }
        }

        // the pool array whose census the tick still has to compute (F4)
        private static CardInfo[] _censusCards;
        private static bool _gameDigestPending;

        /// <summary>From C1 (inside StartPick) when the pool array changed:
        /// only the index map and the canonical names the collectors read, one
        /// pass over the pool, once per pool array. The census text, its digest,
        /// the category check, the pool-class read and the census line are
        /// FinishCensus's, on the tick.</summary>
        private static void EnsurePool(CardChoice choice)
        {
            var cards = choice != null ? choice.cards : null;
            if (cards == null || ReferenceEquals(cards, _poolRef)) return;
            var canon = new string[cards.Length];
            var rar = new int[cards.Length];
            _ix.Clear();
            for (int i = 0; i < cards.Length; i++)
            {
                var c = cards[i];
                if (c == null) { canon[i] = ""; rar[i] = -1; continue; }
                if (!_ix.ContainsKey(c)) _ix[c] = i;
                string nm = c.gameObject.name;
                try { nm = CardRarityLookup.GetCanonicalName(nm) ?? nm; } catch { }
                canon[i] = nm;
                rar[i] = (int)c.rarity;
            }
            _canon = canon; _rar = rar;
            _poolRef = cards;
            _censusCards = cards;
            _digest = "";
        }

        /// <summary>From the tick (outside combat), the census dump and the
        /// quit flush: the census of the pool array C1 took (finding M4; the
        /// pool's cards are the game's prefabs, the same objects C1 indexed),
        /// its digest, the category check and, once per process, the census
        /// line. A game begun while it was pending takes the digest here.</summary>
        private static void FinishCensus()
        {
            var cards = _censusCards;
            if (cards == null) return;
            _censusCards = null;
            var census = new List<K.CensusCard>(cards.Length);
            var cats = new List<KeyValuePair<int, string>>();
            for (int i = 0; i < cards.Length; i++)
            {
                var c = cards[i];
                if (c == null) { census.Add(new K.CensusCard { Name = "" }); continue; }
                Gun gun = null;
                try { gun = c.GetComponent<Gun>(); } catch { }
                census.Add(new K.CensusCard
                {
                    Name = c.gameObject.name, Rarity = (int)c.rarity, AllowMultiple = c.allowMultiple,
                    Categories = CatNames(c.categories, cats), Blacklisted = CatNames(c.blacklistedCategories, cats),
                    Lock = gun != null && gun.lockGunToDefault,
                });
            }
            _censusText = K.CensusText(census);
            _digest = K.CensusDigest(_censusText);
            _censusCollision = K.CategoryNameCollision(cats);
            if (_game != null && _gameDigestPending) { _game.Digest = _digest; _gameDigestPending = false; }
            foreach (var p in _pending) if (p.DigestPending) { p.Game.Digest = _digest; p.DigestPending = false; }
            if (!_poolClassLogged)
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
                Plugin.Log.LogInfo(TAG + " census: " + cards.Length.ToString(CultureInfo.InvariantCulture) + " cards, digest "
                                   + _digest + ", pool class " + pool + (_censusCollision ? ", CATEGORY NAME COLLISION" : ""));
            }
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

        // -- room exit and the game-over build ------------------------------------------------------

        /// <summary>The left-room edge: collecting stops. The state is built
        /// only by a dispatch for the same room within FROZEN_MS (a game cut
        /// short by a leave or a drop); otherwise it is dropped at the next
        /// game's first phase and never becomes a record.</summary>
        internal static void RoomExit()
        {
            try
            {
                if (_game != null && !_exited) { _exited = true; _exitedAtMs = _sw.ElapsedMilliseconds; }
                else if (_exited) _game = null;
            }
            catch { }
        }

        /// <summary>A game's record as the dispatch captured it; built on the tick.</summary>
        private sealed class Pending
        {
            internal K.CardGame Game;
            internal string Seat, Other, Stable, Attach, End, Text, Env;
            internal int Rule, Verdict;
            internal long[][] Cost;
            internal bool DigestPending;
        }

        private const int PENDING_CAP = 4;
        private static readonly List<Pending> _pending = new List<Pending>();
        private static long _nextBuildMs;
        private static bool _buildFailLogged;
        private static string _noRecordNote;

        /// <summary>After the seat evidence dispatch (game over, or a game cut
        /// short). Ranked only, both seats. CAPTURES the game (F4): closes it
        /// and copies the end kind, the rule and its verdict and the cost
        /// table. The record is built, budgeted, signed and persisted by Tick
        /// outside combat (or by FlushOnQuit when the game closes); the queue
        /// sends it outside combat. The end kind is the one the seat record
        /// carries.</summary>
        internal static void Dispatch(string seat, string other, string attach, bool rankedNow)
        {
            try
            {
                var game = _game;
                if (game == null || _taken) return;
                if (_exited && _sw.ElapsedMilliseconds - _exitedAtMs > FROZEN_MS) return;
                if (_room.Length == 0 || attach == null || !attach.StartsWith(_room + "_", StringComparison.Ordinal)) return;
                _taken = true;
                if (!rankedNow && !CardDrawEvidenceTestGate.On) return;
                string stable = null, end = null;
                try { stable = SeatEvidence.StableOf(attach); } catch { stable = null; }
                try { end = SeatEvidence.NotedEnd; } catch { end = null; }
                if (stable == null || !SeatEvidenceCore.IsSteamId(seat) || !SeatEvidenceCore.IsSteamId(other))
                {
                    _noRecordNote = " no record: game key or seat ids outside the contract";
                    return;
                }
                game.Close(SharedNow());
                int rule = 0, verdict = 0;
                try
                {
                    rule = RoomRules.SameCards ? 1 : 0;
                    verdict = rule == 0 ? 0 : (FfaCardSequence.ActiveThisGame ? 1 : 2);
                }
                catch { }
                var cost = new long[K.COLLECTORS][];
                for (int i = 0; i < K.COLLECTORS; i++) cost[i] = (long[])_cost[i].Clone();
                if (_pending.Count >= PENDING_CAP) { _pending.RemoveAt(0); _noRecordNote = " a captured record was dropped before it was persisted: too many waiting"; }
                _pending.Add(new Pending
                {
                    Game = game, Seat = seat, Other = other, Stable = stable, Attach = attach, End = end,
                    Rule = rule, Verdict = verdict, Cost = cost, DigestPending = _gameDigestPending,
                });
                _gameDigestPending = false;
                _nextBuildMs = 0;
            }
            catch
            {
                _noRecordNote = " no record: the capture failed";
            }
        }

        /// <summary>From Plugin's persistent tick, ABOVE its modDisabled
        /// return: the deferred lines always; outside combat (current frame)
        /// the census and the captured records' builds.</summary>
        internal static void Tick()
        {
            try
            {
                DrainNotes();
                if (SeatEvidence.CombatLive()) return;
                FinishCensus();
                BuildPending(false);
            }
            catch { }
        }

        /// <summary>Application.quitting, after the seat evidence quit flush:
        /// every captured record is built and persisted now (no later frame).</summary>
        internal static void FlushOnQuit()
        {
            try { DrainNotes(); FinishCensus(); BuildPending(true); } catch { }
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

        /// <summary>Builds and persists the captured records. A build waits for
        /// the completed game DLL identity (F7). A record is reported as queued
        /// only after the queue file holding it replaced the old one (F8);
        /// until then it stays captured, its bytes kept, and is tried again
        /// every 5 s.</summary>
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
                        if (p.DigestPending) { p.Game.Digest = _digest; p.DigestPending = false; }
                        string sha = SeatEvidence.GameDllSha, state = SeatEvidence.GameDllState;
                        string text = K.Budget(p.Game.Record(p.End, sha, state, p.Rule, p.Verdict, p.Cost));
                        string sig = ApiClient.SeatEvidenceSig(K.Canonical(p.Seat, p.Other, p.Stable, p.Attach, text));
                        string env = K.Envelope(p.Seat, p.Other, p.Stable, p.Attach, text, sig);
                        if (env == null)
                        {
                            _pending.RemoveAt(i);
                            Plugin.Log.LogWarning(TAG + " no record: the envelope is outside the contract");
                            continue;
                        }
                        p.Text = text; p.Env = env;
                    }
                    if (!SeatEvidence.EnqueueCard(p.Env))
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
                    Plugin.Log.LogInfo(TAG + " record queued: " + p.Text.Length.ToString(CultureInfo.InvariantCulture) + " bytes, phases "
                        + (game.Tot[0][0] + game.Tot[1][0]).ToString(CultureInfo.InvariantCulture) + ", hands "
                        + (game.Tot[0][1] + game.Tot[1][1]).ToString(CultureInfo.InvariantCulture) + ", end " + (p.End ?? "game_over")
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
                            foreach (var p in info.Prefixes.Concat(info.Postfixes))
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
                EnsurePool(CardChoice.instance);
                FinishCensus();
                if (_censusCollision)
                {
                    Plugin.Log.LogError(TAG + " census dump FAILED: two category objects share a name; nothing written");
                    return;
                }
                int ns = CardChoice.instance.transform.childCount;
                var o = new SeatEvidenceCore.JObj().Add("census_version", 1L).Add("digest", _digest)
                    .Add("card_count", (long)(_poolRef != null ? _poolRef.Length : 0)).Add("slot_count", (long)ns)
                    .Add("game_dll", new List<object> { state == "ok" ? sha : "", state == "ok" ? "ok" : state })
                    .Add("census_text", _censusText);
                const string FILE = "CompetitiveRounds.card-census.json";
                File.WriteAllText(Path.Combine(Paths.ConfigPath, FILE), SeatEvidenceCore.Json(o), new UTF8Encoding(false));
                Plugin.Log.LogInfo(TAG + " census dump written to " + FILE + ": digest " + _digest + ", "
                                   + (_poolRef != null ? _poolRef.Length : 0).ToString(CultureInfo.InvariantCulture) + " cards, " + ns.ToString(CultureInfo.InvariantCulture) + " slots");
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

    /// <summary>C5: a card applied by RPC; last, so it reads the siblings'
    /// aggregate __runOriginal and never changes it.</summary>
    [HarmonyPatch(typeof(ApplyCardStats), "RPCA_Pick")]
    [HarmonyPriority(Priority.Last)]
    internal static class CardDrawEvidence_PickPatch
    {
        [HarmonyPrefix]
        private static void Prefix(ApplyCardStats __instance, int[] __0, bool __runOriginal)
        {
            try { CardDrawEvidence.PickApplied(__instance, __0, __runOriginal); } catch { }
        }
    }

    /// <summary>C6: a card applied by the offline path (the client's replays).</summary>
    [HarmonyPatch(typeof(ApplyCardStats), "OFFLINE_Pick")]
    [HarmonyPriority(Priority.Last)]
    internal static class CardDrawEvidence_OfflinePickPatch
    {
        [HarmonyPrefix]
        private static void Prefix(ApplyCardStats __instance, Player[] __0, bool __runOriginal)
        {
            try { CardDrawEvidence.OfflinePickApplied(__instance, __0, __runOriginal); } catch { }
        }
    }
}
