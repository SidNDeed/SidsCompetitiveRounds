using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using ExitGames.Client.Photon;
using HarmonyLib;
using InControl;
using Photon.Pun;
using Photon.Realtime;
using UnityEngine;
using PhotonPlayer = Photon.Realtime.Player;

namespace CompetitiveRounds
{
    /// <summary>The client half of item 13 (connect-failure design V11, sec3.5)
    /// and the late entry of item 5: the kept epoch and its events, the one
    /// kept-actor view, the quarantine, the authority fence, the count's
    /// EVT_SCALE, LAG_OUT, the boundary digest and the late seat's path.
    ///
    /// Every decision is FfaLateRules' (Unity-free, executed by the late-rules
    /// harness); this class feeds it plain values and applies the answer. In a
    /// room the gate reads as ungated every view here passes every actor and
    /// every master, so an ungated room keeps today's behaviour. Every view
    /// fails safe: IsKeptActor is true, and the fence passes, on an exception.
    ///
    /// The kept epoch's events (EVT_READY, EVT_EPOCH, EVT_EPOCH_ACK and
    /// EVT_CALLIN) and the late entry exist only in an admission room (sec5.1,
    /// sec10); the grant set, the quarantine, the fence, EVT_SCALE and LAG_OUT
    /// run in every gated room.</summary>
    internal static class FfaLateEntry
    {
        internal const byte EVT_READY = 53;
        internal const byte EVT_EPOCH = 54;
        internal const byte EVT_SCALE = 55;
        internal const byte EVT_EPOCH_ACK = 56;
        internal const byte EVT_CALLIN = 57;
        internal const byte EVT_MASTER = 58;
        internal const string LateMarker = "late";
        internal const string LateClosed = "late_closed";

        /// <summary>WP5: the player properties other clients read, one
        /// constant per name, named by every writer and reader. cr_late is
        /// "{lobby8}" (sticky for the sitting), cr_bd "{g}:{k}:{hash}" and
        /// cr_lag "{lobby8}:{g}:{k}" (FfaLateRules.LagValue).</summary>
        internal const string PropLate = "cr_late";
        internal const string PropBd = "cr_bd";
        internal const string PropLag = "cr_lag";

        // ------------------------------------------------------------ attach state (sec5.1 condition 6)

        internal static bool PickPrefixAttached;
        internal static bool ForcePrefixAttached;
        internal static bool SyncPrefixAttached;
        internal static bool MapReportPrefixAttached;
        internal static bool VisiblePostfixAttached;
        internal static bool SimulatedPostfixAttached;
        internal static bool RegisterPostfixAttached;

        /// <summary>Item 13 compiled in and each of its patches attached; the
        /// combat refusal rides the DoDamage prefix DamageRulesGate, whose own
        /// cleanup records it.</summary>
        internal static bool QuarantineAttached()
        {
            bool damage = false;
            try { damage = VanillaFixSupport.IsAttached("DamageRulesGate"); } catch { }
            return PickPrefixAttached && ForcePrefixAttached && SyncPrefixAttached && MapReportPrefixAttached
                   && VisiblePostfixAttached && SimulatedPostfixAttached && RegisterPostfixAttached && damage;
        }

        // ------------------------------------------------------------ the sitting's state

        /// <summary>The highest-n kept-epoch record this client verified in its
        /// own answers for this lobby.</summary>
        internal static FfaLateRules.EpochRecord Record = new FfaLateRules.EpochRecord();
        /// <summary>The highest epoch this client ever applied, and its chain
        /// (e3, e5, s4).</summary>
        internal static int EpochApplied;
        internal static string AppliedChain = "0";
        /// <summary>The epoch of the set this client paired at its last
        /// call-in: every reader of which actors are kept reads it (V11, N9).</summary>
        internal static int PointEpoch;
        /// <summary>The call-in master of the last call-in this client paired
        /// (a valid stamp or a stamp_late), or the sitting's first game start's
        /// master; -1 after LAG_OUT.</summary>
        internal static int LastPairMaster = -1;
        private static bool _pairedAny;
        private static bool _firstGameOfSitting = true;
        /// <summary>The latest `late` list of this client's own answers.</summary>
        internal static List<FfaLateRules.EpochEntry> LateList = new List<FfaLateRules.EpochEntry>();
        /// <summary>The lobby this seat read `admitted_late` for (the reporter
        /// rule and the release read it, never the cr_late property).</summary>
        internal static string AdmittedLateLobby;
        internal static bool LateArmed;
        /// <summary>The game this client's LAG_OUT covers (0: none); the report
        /// builder and its fallback read it locally.</summary>
        internal static int LagGame;
        /// <summary>The count of HandleNextRound calls in the room's current
        /// game (the boundary's point k).</summary>
        internal static int PointK;
        private static string _sittingLobby;
        private static string _runningRoom;

        internal static int EpochSeen => Record != null ? Record.N : 0;

        internal static string Lobby8
        {
            get
            {
                string l = FfaAssembly.RoomLobbyId;
                if (string.IsNullOrEmpty(l) && FfaAssembly.Lock != null) l = FfaAssembly.Lock.Lobby;
                return JoinTimeline.Id8(l);
            }
        }

        /// <summary>A lock for another lobby: the sitting's epoch, pairing,
        /// late and lag state start over.</summary>
        internal static void ResetSitting(string lobby)
        {
            _sittingLobby = lobby;
            Record = new FfaLateRules.EpochRecord();
            EpochApplied = 0;
            AppliedChain = "0";
            PointEpoch = 0;
            LastPairMaster = -1;
            _pairedAny = false;
            _firstGameOfSitting = true;
            LateList = new List<FfaLateRules.EpochEntry>();
            AdmittedLateLobby = null;
            LateArmed = false;
            _lateEntered = false;
            _lateLoads = 0;
            _lateFailures = 0;
            _pendingSnap = null;
            LagGame = 0;
            _ready.Clear();
            _readySent = 0;
            _acks.Clear();
            _ackSent.Clear();
            _stamps.Clear();
            _callInMaster.Clear();
            _ownStamp.Clear();
            _lateRequests.Clear();
            _lateWaits.Clear();
            _runningRoom = null;
            _knownKept.Clear();
        }

        // ------------------------------------------------------------ the views (item 13)

        internal static bool GatedRunning
        {
            get
            {
                try { return FfaAssembly.SittingStarted(); }
                catch { return false; }
            }
        }

        private static int OwnActor()
        {
            try { return PhotonNetwork.LocalPlayer != null ? PhotonNetwork.LocalPlayer.ActorNumber : -1; }
            catch { return -1; }
        }

        private static int MasterActor()
        {
            try
            {
                var m = PhotonNetwork.MasterClient;
                return m != null ? m.ActorNumber : -1;
            }
            catch { return -1; }
        }

        /// <summary>This client's own grant set names its own current actor.</summary>
        internal static bool HoldsGrant
        {
            get
            {
                int a = OwnActor();
                return a > 0 && FfaLateRules.InGrants(a, FfaAssembly.Granted);
            }
        }

        private static bool Kept(int actor)
        {
            return FfaLateRules.KeptSender(actor, FfaAssembly.Granted, Record, PointEpoch);
        }

        /// <summary>The one kept-actor view: !GatedRunning || (HoldsGrant &amp;&amp;
        /// kept(a)). True on an exception.</summary>
        internal static bool IsKeptActor(int actor)
        {
            try
            {
                return FfaLateRules.KeptActorValue(FfaAssembly.CurrentGate(), HoldsGrant, actor,
                                                   FfaAssembly.Granted, Record, PointEpoch);
            }
            catch { return true; }
        }

        internal static bool IsQuarantinedActor(int actor)
        {
            try { return GatedRunning && !IsKeptActor(actor); }
            catch { return false; }
        }

        internal static int OwnerOf(Player p)
        {
            try
            {
                return p != null && p.data != null && p.data.view != null ? p.data.view.OwnerActorNr : -1;
            }
            catch { return -1; }
        }

        /// <summary>A body is quarantined by its current owner actor.</summary>
        internal static bool IsQuarantined(Player p)
        {
            int a = OwnerOf(p);
            return a > 0 && IsQuarantinedActor(a);
        }

        /// <summary>Any of the bodies is quarantined (a hit's dealer or target,
        /// one call per surface span).</summary>
        internal static bool IsQuarantined(params Player[] bodies)
        {
            if (bodies == null) return false;
            foreach (var p in bodies)
            {
                int a = OwnerOf(p);
                if (a > 0 && IsQuarantinedActor(a)) return true;
            }
            return false;
        }

        /// <summary>PlayerManager.instance.players filtered to the bodies whose
        /// current owner actor passes IsKeptActor, in list order.</summary>
        internal static List<Player> KeptPlayers()
        {
            var list = new List<Player>();
            try
            {
                var src = PlayerManager.instance != null ? PlayerManager.instance.players : null;
                if (src == null) return list;
                bool gated = GatedRunning;
                for (int i = 0; i < src.Count; i++)
                {
                    var p = src[i];
                    if (p == null) continue;
                    if (gated)
                    {
                        int a = OwnerOf(p);
                        if (a > 0 && !IsKeptActor(a)) continue;
                    }
                    list.Add(p);
                }
            }
            catch { }
            return list;
        }

        /// <summary>This client's own actor is not kept on its own client, in a
        /// gated room (pre or started).</summary>
        internal static bool LocalSitsOut()
        {
            try
            {
                if (!FfaAssembly.SittingGated()) return false;
                int own = OwnActor();
                return !(HoldsGrant && Kept(own));
            }
            catch { return false; }
        }

        /// <summary>The current Photon master's actor is kept on this client.</summary>
        internal static bool MasterKept()
        {
            try
            {
                int m = MasterActor();
                if (m < 0) return true;
                return FfaLateRules.MasterKeptValue(FfaAssembly.CurrentGate(), HoldsGrant, FfaAssembly.ReadGranted,
                                                    m, FfaAssembly.Granted, Record, PointEpoch);
            }
            catch { return true; }
        }

        internal static bool LagOutNow() { return _lagOut; }

        /// <summary>Every mod master sender reads this in place of a bare
        /// IsMasterClient.</summary>
        internal static bool MasterMaySend()
        {
            try { return PhotonNetwork.IsMasterClient && MasterKept() && !LagOutNow(); }
            catch { return false; }
        }

        internal static bool MasterFenced()
        {
            try { return PhotonNetwork.IsMasterClient && FfaLateRules.MasterFencedValue(MasterKept(), LagOutNow()); }
            catch { return false; }
        }

        /// <summary>A start trigger: this client entered the room's running game
        /// through the late entry (or started with it as a slow starter).</summary>
        internal static bool GameRunningFor(string room)
        {
            return !string.IsNullOrEmpty(room) && room == _runningRoom;
        }

        private static List<int> PresentActors()
        {
            var list = new List<int>();
            try
            {
                foreach (var a in RoomActors.PresentNonSpectators())
                    if (a != null) list.Add(a.ActorNumber);
            }
            catch { }
            return list;
        }

        private static HashSet<int> BodyActors()
        {
            var set = new HashSet<int>();
            try
            {
                var src = PlayerManager.instance != null ? PlayerManager.instance.players : null;
                if (src != null)
                    foreach (var p in src)
                    {
                        int a = OwnerOf(p);
                        if (a > 0) set.Add(a);
                    }
            }
            catch { }
            return set;
        }

        private static string CrOf(PhotonPlayer a, string key)
        {
            try
            {
                var props = a != null ? a.CustomProperties : null;
                if (props != null && props.ContainsKey(key)) return props[key] as string;
            }
            catch { }
            return null;
        }

        private static PhotonPlayer ActorByNumber(int actor)
        {
            try
            {
                foreach (var a in RoomActors.PresentNonSpectators())
                    if (a != null && a.ActorNumber == actor) return a;
            }
            catch { }
            return null;
        }

        /// <summary>Whether the actor's cr_lag names this lobby, the room's game
        /// and the current point.</summary>
        internal static bool LaggedAtPoint(int actor)
        {
            if (actor == OwnActor()) return _lagOut;
            return FfaLateRules.LagNames(CrOf(ActorByNumber(actor), PropLag), Lobby8, FfaMode.GameNumber, PointK);
        }

        /// <summary>Whether the actor's cr_lag names this lobby and game g (the
        /// election's skip, item 12).</summary>
        internal static bool LaggedInGame(int actor, int g)
        {
            if (actor == OwnActor()) return LagGame == g && g > 0;
            return FfaLateRules.LagNames(CrOf(ActorByNumber(actor), PropLag), Lobby8, g, 0);
        }

        /// <summary>Whether the actor's cr_late names this lobby (the sticky
        /// reporter rule, item 12).</summary>
        internal static bool LateInSitting(int actor)
        {
            if (actor == OwnActor()) return !string.IsNullOrEmpty(AdmittedLateLobby);
            string v = CrOf(ActorByNumber(actor), PropLate);
            return !string.IsNullOrEmpty(v) && v == Lobby8;
        }

        // ------------------------------------------------------------ grant and epoch changes

        private static readonly HashSet<int> _knownKept = new HashSet<int>();

        /// <summary>A change to the grant set: the fighter cache, the provisional
        /// counts, the quarantine and the fence.</summary>
        internal static void OnGrantedChanged()
        {
            ConfirmProvisionalScale();
            try { RoomActors.InvalidateFighterCache(); } catch { }
            ApplyQuarantine();
            FenceMaster();
        }

        /// <summary>An answer's `epoch`: verified against its chain; a verified
        /// higher record replaces the one held.</summary>
        internal static void OnEpochAnswer(string lobby, string raw)
        {
            var m = FfaAssembly.Members(raw);
            int n = FfaAssembly.ExtractJsonInt(m, "n", 0);
            string chain = FfaAssembly.ExtractJsonString(m, "chain") ?? "";
            var entries = new List<FfaLateRules.EpochEntry>();
            foreach (var o in FfaAssembly.JsonObjects(FfaAssembly.ExtractJsonRaw(m, "kept")))
            {
                var e = FfaAssembly.Members(o);
                entries.Add(new FfaLateRules.EpochEntry(FfaAssembly.ExtractJsonInt(e, "slot", 0),
                                                        FfaAssembly.ExtractJsonInt(e, "actor", 0)));
            }
            string l8 = JoinTimeline.Id8(lobby);
            string d = FfaLateRules.RecordDecision(Record, l8, n, chain, entries);
            if (d == "bad")
            {
                string want = FfaLateRules.ChainOf(l8, entries, Math.Min(n, entries.Count)) ?? "-";
                JoinTimeline.Step("epoch_bad", "n=" + I(n) + " got=" + chain + " want=" + want);
                return;
            }
            if (d != "rx") return;
            Record = new FfaLateRules.EpochRecord { N = n, Chain = chain, Entries = entries };
            JoinTimeline.Step("epoch_rx", "n=" + I(n) + " chain=" + chain + " size=" + I(entries.Count));
        }

        private static string ChainAt(int n)
        {
            return FfaLateRules.ChainOf(Lobby8, Record != null ? Record.Entries : null, n) ?? "-";
        }

        private static string KeptList()
        {
            var parts = new List<string>();
            try
            {
                foreach (int a in PresentActors())
                    if (IsKeptActor(a)) parts.Add(I(a));
            }
            catch { }
            return parts.Count == 0 ? "-" : string.Join(",", parts.ToArray());
        }

        private static void KeptLine(string src, bool down)
        {
            int own = OwnActor();
            bool self = own > 0 && FfaLateRules.ListedIn(own, Record, PointEpoch);
            JoinTimeline.Step("kept", "game=" + I(FfaMode.GameNumber) + " k=" + I(PointK) + " n=" + I(PointEpoch)
                                      + " src=" + src + " down=" + (down ? "1" : "0") + " self=" + (self ? "1" : "0")
                                      + " actors=" + KeptList());
        }

        // ------------------------------------------------------------ the game start and the point counter

        /// <summary>FfaMode.OnGameStart, for a fighter in a gated room: the
        /// point counter, the lag rule's carry, the pairing anchor and the
        /// `kept src=start` line.</summary>
        internal static void OnGameStart()
        {
            PointK = 0;
            _bdDirty = true;
            _lagPrinted = null;
            if (!FfaAssembly.SittingGated()) return;
            int g = FfaMode.GameNumber;
            // LatchMaster(g, 0): at the start site, the master at the game's start.
            _latchMaster[Key(g, 0)] = MasterActor();
            if (_lagOut)
            {
                // LAG_OUT outlasts a game's end: the new game is lagged too.
                LagGame = g;
                _lagG = g;
                _lagK = 0;
                PublishLag(g, 0);
                PostLag(g, 0, _lagWhy ?? "timeout");
            }
            else
            {
                LagGame = 0;
            }
            LastPairMaster = FfaLateRules.LastPairAtGameStart(LastPairMaster, _pairedAny, _firstGameOfSitting,
                                                               MasterActor());
            _firstGameOfSitting = false;
            try { RoomActors.InvalidateFighterCache(); } catch { }
            KeptLine("start", false);
            ApplyQuarantine();
        }

        /// <summary>HandleNextRound, after its guards: one more point in this
        /// game.</summary>
        internal static void OnNextRound()
        {
            PointK++;
            _bdDirty = true;
        }

        /// <summary>The next-round prefix, at RPCA_NextRound's dispatch: the
        /// master it sees is LatchMaster for the point this round loads.</summary>
        internal static void NoteLatch()
        {
            try { _latchMaster[Key(FfaMode.GameNumber, PointK + 1)] = MasterActor(); } catch { }
        }

        /// <summary>A pick applied through the manifest changes the digest.</summary>
        internal static void MarkDigestDirty() { _bdDirty = true; }

        // ------------------------------------------------------------ events

        private static bool _hooked;

        internal static void Hook()
        {
            if (_hooked) return;
            try
            {
                PhotonNetwork.NetworkingClient.EventReceived += OnEvent;
                _hooked = true;
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[FFA-LATE] event hook failed: " + ex.Message); }
        }

        private static void OnEvent(EventData e)
        {
            try
            {
                switch (e.Code)
                {
                    case SpectatorSync.EVT_SNAPSHOT: OnLateSnapshot(e); break;
                    case EVT_READY: OnReady(e); break;
                    case EVT_EPOCH: OnProposal(e); break;
                    case EVT_SCALE: OnScale(e); break;
                    case EVT_EPOCH_ACK: OnAck(e); break;
                    case EVT_CALLIN: OnStamp(e); break;
                    case EVT_MASTER: OnMasterEvent(e); break;
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[FFA-LATE] event " + e.Code + ": " + ex.Message); }
        }

        private static bool Raise(byte code, object[] payload, RaiseEventOptions opts)
        {
            try { return PhotonNetwork.RaiseEvent(code, payload, opts, SendOptions.SendReliable); }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning("[FFA-LATE] raise " + code + ": " + ex.Message);
                return false;
            }
        }

        private static string S(object[] a, int i) { return a != null && i < a.Length ? a[i] as string : null; }

        private static int N(object[] a, int i, int dflt)
        {
            if (a == null || i >= a.Length || a[i] == null) return dflt;
            try { return Convert.ToInt32(a[i], CultureInfo.InvariantCulture); }
            catch { return dflt; }
        }

        private static long Key(int g, int k) { return ((long)g << 32) | (uint)k; }

        // ------------------------------------------------------------ EVT_READY (admission rooms)

        private static readonly Dictionary<int, int> _ready = new Dictionary<int, int>();
        private static int _readySent;

        private static bool AdmissionRoomNow()
        {
            return FfaAssembly.IsAdmissionRoom(FfaAssembly.CurrentRoomName());
        }

        private static int SelfReady()
        {
            return FfaLateRules.ReadyEpoch(Record, PresentActors(), BodyActors(), 0);
        }

        /// <summary>Every client that holds a grant sends EVT_READY for the
        /// highest n it holds once every present actor that epoch lists has a
        /// body here, and again whenever that n rises (cached in the room).</summary>
        private static void ReadyTick()
        {
            if (!AdmissionRoomNow() || !HoldsGrant) return;
            int r = SelfReady();
            if (r <= _readySent) return;
            var opts = new RaiseEventOptions { Receivers = ReceiverGroup.Others, CachingOption = EventCaching.AddToRoomCache };
            if (Raise(EVT_READY, new object[] { Lobby8, r, ChainAt(r) }, opts))
            {
                _readySent = r;
                JoinTimeline.Step("epoch_ready_tx", "n=" + I(r));
            }
        }

        private static void OnReady(EventData e)
        {
            var a = e.CustomData as object[];
            if (S(a, 0) != Lobby8) return;
            int n = N(a, 1, -1);
            int held;
            if (!_ready.TryGetValue(e.Sender, out held) || n > held) _ready[e.Sender] = n;
        }

        // ------------------------------------------------------------ the master's boundary (items 5 and 13)

        /// <summary>The single wait's test: the readiness barrier as it
        /// stands now (MasterBoundary computes n* once, after the wait).</summary>
        private static int ReadyEpochNow(List<FfaLateRules.GrantEntry> grants, int self)
        {
            return FfaLateRules.BarrierEpoch(Record, grants, PresentActors(), _ready, self, SelfReady());
        }

        private static readonly List<FfaLateRules.Proposal> _acks = new List<FfaLateRules.Proposal>();
        private static readonly Dictionary<long, bool> _ackSent = new Dictionary<long, bool>();
        private static readonly Dictionary<long, FfaLateRules.Stamp> _ownStamp = new Dictionary<long, FfaLateRules.Stamp>();
        private static readonly Dictionary<int, int> _lateRequests = new Dictionary<int, int>();   // actor -> seq
        private static readonly Dictionary<int, int> _lateWaits = new Dictionary<int, int>();

        /// <summary>Run by a master for which MasterMaySend() holds, immediately
        /// before the call-in (FfaMode.cs:1923 and 1649): the late snapshots,
        /// the single readiness wait, the proposal, the acknowledgement wait
        /// and the call-in stamp. Only in an admission room.</summary>
        internal static IEnumerator MasterBoundary()
        {
            if (!AdmissionRoomNow() || !MasterMaySend()) yield break;
            int g = FfaMode.GameNumber, k = PointK, self = OwnActor();
            var grants = FfaAssembly.Granted;
            bool selfKindS = FfaLateRules.IsKindS(self, grants);

            // Step 4: the accepted late requests get their snapshots.
            var accepted = new List<int>();
            foreach (var kv in new Dictionary<int, int>(_lateRequests))
            {
                int actor = kv.Key;
                int waits;
                _lateWaits.TryGetValue(actor, out waits);
                if (waits >= 2)
                {
                    SendSnapshot(actor, kv.Value, true);
                    _lateRequests.Remove(actor);
                    continue;
                }
                if (!FfaLateRules.ListedIn(actor, Record, Record != null ? Record.N : 0)) continue;   // deferred
                SendSnapshot(actor, kv.Value, false);
                _lateWaits[actor] = waits + 1;
                _lateRequests.Remove(actor);
                accepted.Add(actor);
            }

            // The single wait for the readiness barrier.
            float t0 = Time.realtimeSinceStartup;
            int held = Record != null ? Record.N : 0;
            if (held > PointEpoch)
            {
                while (ReadyEpochNow(grants, self) < held && Time.realtimeSinceStartup - t0 < FfaAssembly.LateWaitS)
                    yield return null;
            }
            // After the single wait: n* from the barrier, once (K38).
            int nStar = FfaLateRules.BarrierEpoch(Record, grants, PresentActors(), _ready, self, SelfReady());
            int waited = (int)((Time.realtimeSinceStartup - t0) * 1000f);
            var bodies = BodyActors();
            foreach (int actor in accepted)
                JoinTimeline.Step("late_wait", "waited_ms=" + I(waited) + " found=" + (bodies.Contains(actor) ? "1" : "0")
                                               + " slot=" + I(SlotOf(actor)));
            JoinTimeline.Step("epoch_ready", "n=" + I(nStar) + " applied=" + I(EpochApplied) + " waited_ms=" + I(waited)
                                             + " missing=" + MissingReady(nStar + 1));

            // The proposal and its acknowledgements, then the stamp.
            bool proposed = FfaLateRules.MayPropose(nStar, PointEpoch, selfKindS) && MasterMaySend();
            bool ackComplete = false;
            var proposal = new FfaLateRules.Proposal { Lobby8 = Lobby8, N = nStar, Chain = ChainAt(nStar), G = g, K = k, From = self };
            if (proposed)
            {
                _acks.Clear();
                Raise(EVT_EPOCH, new object[] { proposal.Lobby8, proposal.N, proposal.Chain, g, k },
                      new RaiseEventOptions { Receivers = ReceiverGroup.Others });
                JoinTimeline.Step("epoch_raise", "n=" + I(nStar) + " chain=" + proposal.Chain);
                var barrier = FfaLateRules.BarrierSet(Record, grants, nStar);
                float a0 = Time.realtimeSinceStartup;
                List<int> missing;
                while (true)
                {
                    ackComplete = FfaLateRules.AckComplete(barrier, PresentActors(), _acks, proposal, self, out missing);
                    if (ackComplete || Time.realtimeSinceStartup - a0 >= FfaAssembly.EpochAckS) break;
                    yield return null;
                }
                var from = new List<string>();
                foreach (var ak in _acks)
                    if (ak.N == nStar && ak.G == g && ak.K == k) from.Add(I(SlotOf(ak.From)));
                JoinTimeline.Step("epoch_ack", "n=" + I(nStar) + " from=" + (from.Count > 0 ? string.Join(",", from.ToArray()) : "none")
                                               + " missing=" + Slots(missing) + " waited_ms="
                                               + I((int)((Time.realtimeSinceStartup - a0) * 1000f)));
                if (!ackComplete)
                    JoinTimeline.Step("epoch_unacked", "n=" + I(nStar) + " missing=" + Slots(missing));
            }
            string result;
            int n;
            bool apply;
            FfaLateRules.MasterStampDecision(proposed, nStar, ackComplete, PointEpoch, out result, out n, out apply);
            if (!MasterMaySend()) yield break;   // the role moved during the waits: the next master stamps
            var stamp = new FfaLateRules.Stamp { Lobby8 = Lobby8, G = g, K = k, N = n, Chain = ChainAt(n), Result = result, From = self };
            Raise(EVT_CALLIN, new object[] { stamp.Lobby8, g, k, n, stamp.Chain, result },
                  new RaiseEventOptions { Receivers = ReceiverGroup.Others });
            JoinTimeline.Step("callin_stamp", "g=" + I(g) + " k=" + I(k) + " n=" + I(n) + " result=" + result);
            _ownStamp[Key(g, k)] = stamp;
            if (apply)
            {
                PointEpoch = n;
                EpochApplied = Math.Max(EpochApplied, n);
                AppliedChain = ChainAt(EpochApplied);
            }
            LastPairMaster = self;
            _pairedAny = true;
            AfterPair(apply ? "epoch" : "carry", false, g, k);
        }

        private static string MissingReady(int n)
        {
            var miss = new List<int>();
            try
            {
                int self = OwnActor();
                var present = PresentActors();
                foreach (int a in FfaLateRules.BarrierSet(Record, FfaAssembly.Granted, Math.Min(n, Record != null ? Record.N : 0)))
                {
                    if (a == self || !present.Contains(a)) continue;
                    int r;
                    if (!_ready.TryGetValue(a, out r) || r < n) miss.Add(a);
                }
            }
            catch { }
            return Slots(miss);
        }

        private static int SlotOf(int actor)
        {
            foreach (var e in FfaAssembly.Granted)
                if (e.Actor == actor) return e.Slot;
            if (Record != null)
                foreach (var e in Record.Entries)
                    if (e.Actor == actor) return e.Slot;
            return -1;
        }

        private static string Slots(List<int> actors)
        {
            if (actors == null || actors.Count == 0) return "none";
            var parts = new List<string>();
            foreach (int a in actors) parts.Add(I(SlotOf(a)));
            return string.Join(",", parts.ToArray());
        }

        private static void OnAck(EventData e)
        {
            if (!PhotonNetwork.IsMasterClient) return;
            var a = e.CustomData as object[];
            _acks.Add(new FfaLateRules.Proposal
            {
                Lobby8 = S(a, 0), N = N(a, 1, -1), Chain = S(a, 2), G = N(a, 3, -1), K = N(a, 4, -1), From = e.Sender,
            });
        }

        // ------------------------------------------------------------ the receiver's checks (e1-e6)

        private static void OnProposal(EventData e)
        {
            if (!HoldsGrant) return;   // a client that holds no grant ignores the proposal
            var a = e.CustomData as object[];
            var p = new FfaLateRules.Proposal
            {
                Lobby8 = S(a, 0), N = N(a, 1, -1), Chain = S(a, 2), G = N(a, 3, -1), K = N(a, 4, -1), From = e.Sender,
            };
            int g = FfaMode.GameNumber;
            bool kKnown = !LateArmed || _snapK >= 0;
            int k = LateArmed && _snapK >= 0 ? _snapK : PointK;
            string why = FfaLateRules.ValidateEpoch(p, MasterActor(), MasterKept(), Lobby8, Record, EpochApplied,
                                                    AppliedChain, g, k, kKnown, PresentActors());
            if (why != null)
            {
                JoinTimeline.Step("epoch_refused", "why=" + why + " n=" + I(p.N) + " applied=" + I(EpochApplied)
                                                   + " sender=" + I(e.Sender));
                return;
            }
            if (Raise(EVT_EPOCH_ACK, new object[] { p.Lobby8, p.N, p.Chain, p.G, p.K },
                      new RaiseEventOptions { TargetActors = new[] { e.Sender } }))
            {
                _ackSent[Key(p.G, p.K)] = true;
                JoinTimeline.Step("epoch_ack_tx", "n=" + I(p.N));
            }
        }

        // ------------------------------------------------------------ the stamp and the pairing (s1-s4)

        private sealed class HeldStamp
        {
            public FfaLateRules.Stamp Stamp;
            public float Rt;
        }

        private static readonly Dictionary<long, List<HeldStamp>> _stamps = new Dictionary<long, List<HeldStamp>>();
        private static readonly Dictionary<long, int> _callInMaster = new Dictionary<long, int>();

        private sealed class Hold
        {
            public int MapId;
            public int G;
            public int K;
            public int CallInMaster;
            public float Rt;
            public bool Done;
            public FfaLateRules.Stamp Paired;
            public FfaLateRules.PairResult Decided;
        }

        private static Hold _hold;
        private static Hold _lastHold;
        internal static bool CallInBypass;
        internal static bool CallInHeldNow;

        private static void OnStamp(EventData e)
        {
            var a = e.CustomData as object[];
            var s = new FfaLateRules.Stamp
            {
                Lobby8 = S(a, 0), G = N(a, 1, -1), K = N(a, 2, -1), N = N(a, 3, -1), Chain = S(a, 4), Result = S(a, 5),
                From = e.Sender,
            };
            long key = Key(s.G, s.K);
            List<HeldStamp> list;
            if (!_stamps.TryGetValue(key, out list)) _stamps[key] = list = new List<HeldStamp>();
            list.Add(new HeldStamp { Stamp = s, Rt = Time.realtimeSinceStartup });
            var h = _lastHold;
            if (h != null && h.Done && h.G == s.G && h.K == s.K && s.From == h.CallInMaster)
            {
                // A valid stamp of the call-in's master after the hold ended.
                string why = Validate(s, h.CallInMaster);
                if (why != null) { Refused(s, why); return; }
                var r = FfaLateRules.LateStampDecision(h.Decided, h.Paired, s);
                PairStamp(h, s, 1);
                if (r.Kind == FfaLateRules.PairKind.LagOut) LagOutStart(r.Why, false);
            }
        }

        private static string Validate(FfaLateRules.Stamp s, int callInMaster)
        {
            bool kKnown = !LateArmed || _snapK >= 0;
            int k = LateArmed && _snapK >= 0 ? _snapK : PointK;
            return FfaLateRules.ValidateStamp(s, callInMaster, Kept(s.From), FfaLateRules.IsKindS(s.From, FfaAssembly.Granted),
                                              Lobby8, Record, EpochApplied, AppliedChain, FfaMode.GameNumber, k, kKnown);
        }

        private static void Refused(FfaLateRules.Stamp s, string why)
        {
            JoinTimeline.Step("stamp_refused", "why=" + why + " g=" + I(s.G) + " k=" + I(s.K) + " n=" + I(s.N) + " sender=" + I(s.From));
        }

        /// <summary>The call-in hold's prefix (admission rooms): true runs the
        /// call-in now; false holds it for the stamp of the call-in's master,
        /// at most ASM_STAMP_WAIT_S, and replays it locally after. Item 13,
        /// receivers: a call-in sent under a master that MasterKept() rejects
        /// is refused, never replayed (that master's map flow is held, as at
        /// the load gate; a kept master's own call-in follows).</summary>
        internal static bool OnCallIn(int mapId)
        {
            if (CallInBypass)
            {
                CallInBypass = false;
                return true;
            }
            if (!MasterKept())
            {
                RefusedAuthority();
                CallInHeldNow = true;   // the observer does not count a call-in that did not run
                return false;
            }
            if (!AdmissionRoomNow() || !HoldsGrant || RoomActors.LocalIsSpectator) return true;
            int g = FfaMode.GameNumber;
            int k = LateArmed && _snapK >= 0 ? _snapK : PointK;
            int cim = MasterActor();
            long key = Key(g, k);
            _callInMaster[key] = cim;
            var h = new Hold { MapId = mapId, G = g, K = k, CallInMaster = cim, Rt = Time.realtimeSinceStartup };
            // A stamp held for this (g, k) from any other sender is dropped.
            List<HeldStamp> list;
            if (_stamps.TryGetValue(key, out list))
            {
                for (int i = list.Count - 1; i >= 0; i--)
                {
                    var s = list[i].Stamp;
                    if (s.From == cim) continue;
                    JoinTimeline.Step("stamp_superseded", "g=" + I(g) + " k=" + I(k) + " n=" + I(s.N) + " sender=" + I(s.From) + " callin=" + I(cim));
                    list.RemoveAt(i);
                }
            }
            FfaLateRules.Stamp own;
            if (cim == OwnActor() && _ownStamp.TryGetValue(key, out own))
            {
                // The master applied at its own stamp's send (MasterBoundary).
                h.Done = true;
                h.Paired = own;
                _lastHold = h;
                return true;
            }
            _hold = h;
            if (TryPair(h, false)) return true;
            CallInHeldNow = true;
            return false;
        }

        /// <summary>Pairs a held call-in when a valid stamp of its master is
        /// here, or when the hold has ended (stamp_late or LAG_OUT).</summary>
        private static bool TryPair(Hold h, bool expired)
        {
            FfaLateRules.Stamp valid = null;
            bool conflict = false;
            List<HeldStamp> list;
            if (_stamps.TryGetValue(Key(h.G, h.K), out list))
            {
                for (int i = list.Count - 1; i >= 0; i--)
                {
                    var s = list[i].Stamp;
                    if (s.From != h.CallInMaster) continue;
                    string why = Validate(s, h.CallInMaster);
                    if (why != null)
                    {
                        Refused(s, why);
                        list.RemoveAt(i);
                        continue;
                    }
                    if (valid != null && !valid.SameAs(s)) conflict = true;
                    valid = valid ?? s;
                }
            }
            if (valid == null && !conflict && !expired) return false;
            bool ackSent;
            _ackSent.TryGetValue(Key(h.G, h.K), out ackSent);
            var r = FfaLateRules.PairDecision(conflict ? null : valid, conflict, h.CallInMaster, LastPairMaster, ackSent,
                                              PointEpoch, EpochApplied, Record);
            h.Done = true;
            h.Paired = valid;
            h.Decided = r;
            _hold = null;
            _lastHold = h;
            ApplyPair(h, valid, r);
            return true;
        }

        /// <summary>I1 stamp_rx, printed once here: the call-in's pairing
        /// (late=0) and a valid stamp of the call-in's master that arrives
        /// after its hold ended (late=1) both call it.</summary>
        private static void PairStamp(Hold h, FfaLateRules.Stamp s, int late)
        {
            int waited = (int)((Time.realtimeSinceStartup - h.Rt) * 1000f);
            JoinTimeline.Step("stamp_rx", "g=" + I(h.G) + " k=" + I(h.K) + " n=" + I(s.N) + " result=" + (s.Result ?? "-")
                                          + " waited_ms=" + I(waited) + " late=" + I(late));
        }

        private static void ApplyPair(Hold h, FfaLateRules.Stamp valid, FfaLateRules.PairResult r)
        {
            switch (r.Kind)
            {
                case FfaLateRules.PairKind.Apply:
                case FfaLateRules.PairKind.Carry:
                case FfaLateRules.PairKind.CarryDown:
                    PairStamp(h, valid, 0);
                    PointEpoch = r.PointEpoch;
                    EpochApplied = r.EpochApplied;
                    AppliedChain = ChainAt(EpochApplied);
                    LastPairMaster = h.CallInMaster;
                    _pairedAny = true;
                    if (_lagOut && FfaLateRules.LagOutEnds("callin", _lagAtLoad && _lagG == h.G && _lagK == h.K))
                        LagOutEnd("callin");
                    AfterPair(r.Kind == FfaLateRules.PairKind.Apply ? "epoch" : "carry",
                              r.Kind == FfaLateRules.PairKind.CarryDown, h.G, h.K);
                    break;
                case FfaLateRules.PairKind.StampLate:
                    JoinTimeline.Step("stamp_late", "g=" + I(h.G) + " k=" + I(h.K) + " n=" + I(PointEpoch) + " master=" + I(h.CallInMaster));
                    AfterPair("carry", false, h.G, h.K);
                    break;
                default:
                    LagOutStart(r.Why ?? "timeout", false);
                    break;
            }
        }

        /// <summary>After a pairing: the kept line, the cache, the quarantine,
        /// the fence, and the newly kept actors (the late seat's own entry and
        /// the present seats' toast).</summary>
        private static void AfterPair(string src, bool down, int g, int k)
        {
            try { RoomActors.InvalidateFighterCache(); } catch { }
            KeptLine(src, down);
            ApplyQuarantine();
            FenceMaster();
            int own = OwnActor();
            var nowKept = new HashSet<int>();
            if (Record != null)
                for (int i = 0; i < PointEpoch && i < Record.Entries.Count; i++) nowKept.Add(Record.Entries[i].Actor);
            bool someoneJoined = false;
            foreach (int a in nowKept)
            {
                if (_knownKept.Contains(a)) continue;
                _knownKept.Add(a);
                if (a == own) OnSelfKept(g);
                else if (BodyActors().Contains(a)) someoneJoined = true;
            }
            if (someoneJoined && !LateArmed)
            {
                try { CompetitiveUI.ShowNotification("A player joined the match", new Color(0.6f, 0.9f, 1f), 5f); } catch { }
            }
        }

        private static void CallInHoldTick()
        {
            var h = _hold;
            if (h == null) return;
            if (FfaAssembly.CurrentRoomName() == "" || !AdmissionRoomNow())
            {
                _hold = null;
                return;
            }
            bool expired = Time.realtimeSinceStartup - h.Rt >= FfaAssembly.StampWaitS;
            if (!TryPair(h, expired)) return;
            CallInBypass = true;
            try { MapManager.instance.RPCA_CallInNewMapAndMovePlayers(h.MapId); }
            catch (Exception ex)
            {
                CallInBypass = false;
                Plugin.Log.LogWarning("[FFA-LATE] call-in replay: " + ex.Message);
            }
        }

        /// <summary>The call-in observer's fighter branch
        /// (SpectatorPatches.cs:768-780): each call-in that ran on this client.
        /// It records the call-in for the late seat, and in LAG_OUT the own
        /// player's death at this call-in.</summary>
        internal static void OnCallInObserved(int mapId)
        {
            if (CallInHeldNow)
            {
                CallInHeldNow = false;   // held by the prefix: the replay reports it
                return;
            }
            _callInCount++;
            _lastCallInLevel = mapId;
            if (!FfaAssembly.SittingGated() || RoomActors.LocalIsSpectator) return;
            FfaAssembly.AfterCallIn();
            if (_lagOut)
            {
                int g = FfaMode.GameNumber, k = PointK;
                if (!(_lagG == g && _lagK == k))
                {
                    // A later call-in it cannot pair: the point is sat out too.
                    _lagG = g;
                    _lagK = k;
                    PublishLag(g, k);
                    LagLine(_lagWhy ?? "timeout", g, k);
                }
                ScheduleOwnDeath();
            }
        }

        // ------------------------------------------------------------ LAG_OUT (V11, N9)

        private static bool _lagOut;
        private static int _lagG, _lagK;
        private static float _lagRt;
        private static bool _lagAtLoad;
        private static string _lagWhy;
        private static string _lagPrinted;

        /// <summary>This client cannot know the call-in master's set, or the
        /// scale, of the point: it sits the point out (its own player dies at
        /// once, or at the point's call-in when the state starts at its load),
        /// sends no master decision, files no report of the game, and says so.</summary>
        internal static void LagOutStart(string why, bool atLoad)
        {
            if (!FfaAssembly.SittingGated() || RoomActors.LocalIsSpectator) return;
            int g = FfaMode.GameNumber, k = PointK;
            if (!_lagOut) _lagRt = Time.realtimeSinceStartup;
            _lagOut = true;
            _lagWhy = why;
            _lagAtLoad = atLoad;
            _lagG = g;
            _lagK = k;
            LastPairMaster = -1;
            LagGame = g;
            PublishLag(g, k);
            PostLag(g, k, why);
            LagLine(why, g, k);
            try { RoomActors.InvalidateFighterCache(); } catch { }
            if (!atLoad) ScheduleOwnDeath();
            FenceMaster();
        }

        private static void LagLine(string why, int g, int k)
        {
            string key = I(g) + ":" + I(k);
            if (_lagPrinted == key) return;
            _lagPrinted = key;
            JoinTimeline.Step("lag_out", "why=" + why + " g=" + I(g) + " k=" + I(k) + " n=" + I(EpochApplied) + " master=" + I(MasterActor()));
        }

        internal static void LagOutEnd(string why)
        {
            if (!_lagOut) return;
            _lagOut = false;
            int ms = (int)((Time.realtimeSinceStartup - _lagRt) * 1000f);
            JoinTimeline.Step("lag_out_end", "why=" + why + " g=" + I(_lagG) + " k=" + I(_lagK) + " ms=" + I(ms));
            _lagPrinted = null;
            try { RoomActors.InvalidateFighterCache(); } catch { }
        }

        private static void PublishLag(int g, int k)
        {
            try
            {
                var me = PhotonNetwork.LocalPlayer;
                if (me == null) return;
                var h = new ExitGames.Client.Photon.Hashtable();
                h[PropLag] = FfaLateRules.LagValue(Lobby8, g, k);
                me.SetCustomProperties(h);
            }
            catch { }
        }

        private static void PostLag(int g, int k, string why)
        {
            string lobby = FfaAssembly.RoomLobbyId;
            if (string.IsNullOrEmpty(lobby)) return;
            FfaAssembly.Receipt(lobby, "lag", "\"game\":" + I(Math.Max(1, Math.Min(999, g))) + ",\"k\":" + I(Math.Max(0, Math.Min(999, k)))
                                              + ",\"why\":\"" + why + "\"");
        }

        private static bool _deathScheduled;

        private static void ScheduleOwnDeath()
        {
            if (_deathScheduled) return;
            _deathScheduled = true;
            try { Plugin.Instance.StartCoroutine(OwnDeathAfterCallIn()); }
            catch { _deathScheduled = false; }
        }

        /// <summary>The vanilla death its owner broadcasts, after the call-in's
        /// move and revive have run.</summary>
        private static IEnumerator OwnDeathAfterCallIn()
        {
            yield return new WaitForSecondsRealtime(1.2f);
            _deathScheduled = false;
            if (!_lagOut) yield break;
            try
            {
                var src = PlayerManager.instance != null ? PlayerManager.instance.players : null;
                if (src == null) yield break;
                foreach (var p in src)
                {
                    if (p == null || p.data == null || p.data.view == null || !p.data.view.IsMine) continue;
                    if (p.data.dead) break;
                    p.data.view.RPC("RPCA_Die", RpcTarget.All, Vector2.up);
                    break;
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[FFA-LATE] lag death: " + ex.Message); }
        }

        /// <summary>The body with this PlayerID in PlayerManager's list, or null
        /// (the revive refusal in PhoenixRespawnPatch.SafeRespawn reads it).</summary>
        internal static Player BodyByPlayerId(int pid)
        {
            try
            {
                var src = PlayerManager.instance != null ? PlayerManager.instance.players : null;
                if (src != null)
                    foreach (var p in src)
                        if (p != null && p.PlayerID == pid) return p;
            }
            catch { }
            return null;
        }

        /// <summary>A body whose owner is in LAG_OUT for the point: read from
        /// LagOutNow() on its owner's client and from its cr_lag elsewhere.</summary>
        internal static bool BodyLagged(Player p)
        {
            int a = OwnerOf(p);
            return a > 0 && LaggedAtPoint(a);
        }

        // ------------------------------------------------------------ the count, EVT_SCALE (V9, N3)

        private static readonly List<FfaLateRules.ScaleRecord> _scale = new List<FfaLateRules.ScaleRecord>();
        private static readonly Dictionary<long, int> _latchMaster = new Dictionary<long, int>();
        internal static FfaLateRules.ScaleRecord AppliedScale;

        /// <summary>The master's publish in a gated room (FfaMapScale), in place
        /// of the room property: {lobby8, game, k, count} to the others.</summary>
        internal static bool RaiseScale(int k, int count)
        {
            int g = FfaMode.GameNumber;
            if (k == 0) _latchMaster[Key(g, 0)] = OwnActor();
            return Raise(EVT_SCALE, new object[] { Lobby8, g, k, count }, new RaiseEventOptions { Receivers = ReceiverGroup.Others });
        }

        private static void OnScale(EventData e)
        {
            if (!FfaAssembly.SittingGated() || RoomActors.LocalIsSpectator) return;
            var a = e.CustomData as object[];
            string l8 = S(a, 0);
            int game = N(a, 1, -1), k = N(a, 2, -1), count = N(a, 3, -1);
            int latch;
            if (!_latchMaster.TryGetValue(Key(game, k), out latch)) latch = -1;
            // Before any granted list the sender cannot be judged: the record is
            // provisional until a granted list names it kind s.
            bool readGranted = FfaAssembly.ReadGranted;
            bool keptSender = !readGranted || Kept(e.Sender);
            string why = FfaLateRules.ScaleRecordDecision(l8, Lobby8, e.Sender, MasterActor(), latch, keptSender);
            if (why != null)
            {
                JoinTimeline.Step("scale_refused", "why=" + why);
                return;
            }
            var r = new FfaLateRules.ScaleRecord { Game = game, K = k, Count = count, From = e.Sender, Confirmed = readGranted };
            _scale.RemoveAll(x => x.Game == game && x.K == k && x.From == e.Sender);
            _scale.Add(r);
            var ap = AppliedScale;
            if (ap != null && FfaLateRules.ScaleLate(ap.Game, ap.K, ap.Count, r)) LagOutStart("scale_late", false);
        }

        private static void ConfirmProvisionalScale()
        {
            foreach (var r in _scale)
                if (!r.Confirmed && FfaLateRules.IsKindS(r.From, FfaAssembly.Granted)) r.Confirmed = true;
        }

        /// <summary>The master's own ticket serves this load (the count hold
        /// never waits on the master).</summary>
        internal static bool OwnTicketServesLoad()
        {
            try { return FfaMapScale.TicketArmedNow && PhotonNetwork.IsMasterClient; }
            catch { return false; }
        }

        /// <summary>A confirmed record for the load's (game, k) is here.</summary>
        internal static bool HasLoadRecord()
        {
            int g = FfaMode.GameNumber;
            bool kKnown = !LateArmed || _snapK >= 0;
            foreach (var r in _scale)
                if (r.Confirmed && r.Game == g && (!kKnown || r.K == PointK)) return true;
            return false;
        }

        /// <summary>ReadPublishedCount in a gated room: the record for the
        /// load's (game, k), consumed with every key at or below it; -1 and
        /// LAG_OUT (why=scale) when there is no confirmed record.</summary>
        internal static int ConsumeLoadCount()
        {
            int g = FfaMode.GameNumber, k = PointK;
            bool kKnown = !LateArmed || _snapK >= 0;
            var d = FfaLateRules.ScaleDecision(_scale, g, k, kKnown);
            FfaLateRules.ScaleRecord hit = null;
            foreach (var r in _scale)
                if (r.Confirmed && r.Game == g && (!kKnown || r.K == k) && r.Count == d.Count) { hit = r; break; }
            FfaLateRules.ConsumeScale(_scale, g, kKnown ? k : int.MaxValue - 1);
            if (d.Count < 0)
            {
                JoinTimeline.Step("scale_refused", "why=" + (d.Why ?? "none"));
                AppliedScale = null;
                if (d.LagOut) LagOutStart("scale", true);
                return -1;
            }
            AppliedScale = new FfaLateRules.ScaleRecord { Game = g, K = hit != null ? hit.K : k, Count = d.Count, From = hit != null ? hit.From : -1, Confirmed = true };
            return d.Count;
        }

        /// <summary>The ticket path's applied count (the master's own load).</summary>
        internal static void NoteAppliedScale(int count)
        {
            AppliedScale = new FfaLateRules.ScaleRecord { Game = FfaMode.GameNumber, K = PointK, Count = count, From = OwnActor(), Confirmed = true };
        }

        internal static string AppliedScaleTag()
        {
            var a = AppliedScale;
            return a == null ? "" : FfaLateRules.ScaleTag(a.Game, a.K, a.Count, a.From);
        }

        // ------------------------------------------------------------ the fence (V10, N7; V11, N9)

        private static bool _fenceEpisode;
        private static float _fenceFirstRt;
        private static int _fenceTries;
        private static bool _fenceSwitchLanded;
        private static bool _handedOffThisEntry;
        private static float _switchRt = -1f;

        /// <summary>On a master for which MasterFenced() holds: hand the role on
        /// (FenceTarget), repeating every ASM_FENCE_S, at most ASM_FENCE_TRIES
        /// tries, with the 9 s bound. Returns true when this client is such a
        /// master, so the caller's own handoff does not run too.</summary>
        internal static bool FenceMaster()
        {
            try
            {
                if (!PhotonNetwork.InRoom || !PhotonNetwork.IsMasterClient) return false;
                if (RoomActors.LocalIsSpectator) return false;
                if (!MasterFenced()) return false;
                if (!_fenceEpisode)
                {
                    _fenceEpisode = true;
                    _fenceFirstRt = Time.realtimeSinceStartup;
                    _fenceTries = 0;
                    _fenceSwitchLanded = false;
                }
                FenceTick();
                return true;
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning("[FFA-LATE] fence: " + ex.Message);
                return false;
            }
        }

        private static string FenceWhy()
        {
            if (_lagOut) return "lag_out";
            if (!HoldsGrant) return null;   // FenceTarget's own why (no_grant | no_grant_next)
            if (FfaAssembly.CurrentGate() == FfaLateRules.Gate.Pre) return "not_kind_s";
            return "unkept";
        }

        /// <summary>I1 master_fence: each hand-off (to, why, try) and the
        /// episode's end (result, ms); printed armed or not.</summary>
        private static void FenceLine(string detail)
        {
            JoinTimeline.Step("master_fence", detail);
        }

        private static void FenceTick()
        {
            if (!_fenceEpisode) return;
            if (!PhotonNetwork.InRoom)
            {
                _fenceEpisode = false;
                return;
            }
            float now = Time.realtimeSinceStartup;
            int ms = (int)((now - _fenceFirstRt) * 1000f);
            bool landed = _fenceSwitchLanded || !PhotonNetwork.IsMasterClient;
            bool keptNow = PhotonNetwork.IsMasterClient && !MasterFenced();
            var present = PresentActors();
            bool alone = present.Count <= 1;
            var act = FfaLateRules.FenceStep(now - _fenceFirstRt, _fenceTries, landed, keptNow);
            switch (act)
            {
                case FfaLateRules.FenceAct.Done:
                    FenceLine("result=done ms=" + I(ms));
                    _fenceEpisode = false;
                    return;
                case FfaLateRules.FenceAct.Kept:
                    FenceLine("result=kept ms=" + I(ms));
                    _fenceEpisode = false;
                    return;
                case FfaLateRules.FenceAct.Expired:
                    if (alone) return;   // a lone master keeps the role, sending nothing
                    FenceLine("result=expired ms=" + I(ms));
                    _fenceEpisode = false;
                    FfaAssembly.Exit("fence_expired");
                    return;
                case FfaLateRules.FenceAct.Try:
                    break;
                default:
                    return;
            }
            _fenceTries++;
            int self = OwnActor();
            var choice = FfaLateRules.FenceTarget(self, present, FfaAssembly.Granted, HoldsGrant,
                                                  a => IsKeptActor(a) && MasterKeptFor(a), a => LaggedAtPoint(a),
                                                  _handedOffThisEntry);
            string why = FenceWhy() ?? (choice.Why == "no_grant_next" ? "no_grant_next" : "no_grant");
            FenceLine("to=" + I(choice.To) + " why=" + why + " try=" + I(_fenceTries));
            if (choice.To < 0) return;
            if (choice.Why == "no_grant_next") _handedOffThisEntry = true;
            var target = ActorByNumber(choice.To);
            if (target == null) return;
            try { PhotonNetwork.SetMasterClient(target); }
            catch (Exception ex) { Plugin.Log.LogWarning("[FFA-LATE] fence switch: " + ex.Message); }
        }

        /// <summary>MasterKept() evaluated for a candidate master.</summary>
        private static bool MasterKeptFor(int actor)
        {
            try
            {
                return FfaLateRules.MasterKeptValue(FfaAssembly.CurrentGate(), HoldsGrant, FfaAssembly.ReadGranted,
                                                    actor, FfaAssembly.Granted, Record, PointEpoch);
            }
            catch { return true; }
        }

        /// <summary>Plugin's OnMasterClientSwitched, before the fence runs: the
        /// episode's switch, the EVT_MASTER telemetry.</summary>
        internal static void OnMasterSwitched(PhotonPlayer newMaster)
        {
            _switchRt = Time.realtimeSinceStartup;
            if (newMaster != null && !newMaster.IsLocal && _fenceEpisode) _fenceSwitchLanded = true;
            try
            {
                if (newMaster != null && newMaster.IsLocal && FfaAssembly.SittingGated())
                    Raise(EVT_MASTER, new object[] { Lobby8, newMaster.ActorNumber, FfaMode.GameNumber, PointK },
                          new RaiseEventOptions { Receivers = ReceiverGroup.Others });
            }
            catch { }
        }

        private static void OnMasterEvent(EventData e)
        {
            var a = e.CustomData as object[];
            if (S(a, 0) != Lobby8) return;
            int ms = _switchRt < 0f ? -1 : (int)((Time.realtimeSinceStartup - _switchRt) * 1000f);
            JoinTimeline.Step("master_ack", "from=" + I(e.Sender) + " ms=" + I(ms));
        }

        // ------------------------------------------------------------ the quarantine (surfaces 5 and the lines)

        private sealed class Hidden
        {
            public List<Collider2D> Colliders = new List<Collider2D>();
        }

        private static readonly Dictionary<int, Hidden> _hidden = new Dictionary<int, Hidden>();
        private static readonly HashSet<string> _qLogged = new HashSet<string>(StringComparer.Ordinal);
        private static float _qNextRt;

        /// <summary>Hides a quarantined body (off-screen, as vanilla's own
        /// SetPlayersVisible does), disables its colliders and sets it
        /// unsimulated; restores a body it quarantined that is now kept (its
        /// simulation then comes from its call-in Move, like every body's).</summary>
        internal static void ApplyQuarantine()
        {
            try
            {
                var src = PlayerManager.instance != null ? PlayerManager.instance.players : null;
                if (src == null) return;
                bool gated = GatedRunning;
                for (int i = 0; i < src.Count; i++)
                {
                    var p = src[i];
                    if (p == null || p.data == null) continue;
                    int id = p.GetInstanceID();
                    int a = OwnerOf(p);
                    bool q = gated && a > 0 && !IsKeptActor(a);
                    if (q)
                    {
                        Hide(p, id);
                        QuarantineLine(a);
                    }
                    else if (_hidden.ContainsKey(id))
                    {
                        Restore(p, id);
                    }
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[FFA-LATE] quarantine: " + ex.Message); }
        }

        private static void Hide(Player p, int id)
        {
            Hidden h;
            if (!_hidden.TryGetValue(id, out h))
            {
                h = new Hidden();
                try
                {
                    foreach (var c in p.GetComponentsInChildren<Collider2D>(true))
                        if (c != null && c.enabled) { c.enabled = false; h.Colliders.Add(c); }
                }
                catch { }
                _hidden[id] = h;
            }
            try { if (p.data.playerVel != null) p.data.playerVel.simulated = false; } catch { }
            try { p.data.gameObject.transform.position = Vector3.up * 200f; } catch { }
        }

        private static void Restore(Player p, int id)
        {
            Hidden h;
            if (!_hidden.TryGetValue(id, out h)) return;
            _hidden.Remove(id);
            foreach (var c in h.Colliders)
            {
                try { if (c != null) c.enabled = true; } catch { }
            }
        }

        private static void QuarantineLine(int actor)
        {
            string key = I(actor) + ":" + I(FfaMode.GameNumber) + ":" + I(PointK);
            if (!_qLogged.Add("q:" + key)) return;
            string why;
            if (FfaLateRules.InGrants(actor, FfaAssembly.Granted)) why = "unkept";
            else if (RosterMember(actor)) why = "rebound";
            else why = "ungranted";
            JoinTimeline.Step("quarantine", "actor=" + I(actor) + " why=" + why);
        }

        private static bool RosterMember(int actor)
        {
            try
            {
                string sid = RoomActors.SteamIdOf(ActorByNumber(actor));
                if (string.IsNullOrEmpty(sid)) return false;
                var roster = ApiClient.FfaLockedRoster;
                if (roster == null) return false;
                foreach (var m in roster)
                    if (m != null && m.steam_id == sid) return true;
            }
            catch { }
            return false;
        }

        /// <summary>A quarantine surface refused an actor: once per surface,
        /// actor and boundary.</summary>
        internal static void Refused(string site, int actor)
        {
            string key = site + ":" + I(actor) + ":" + I(FfaMode.GameNumber) + ":" + I(PointK);
            if (!_qLogged.Add(key)) return;
            JoinTimeline.Step("quarantine_refused", "site=" + site + " actor=" + I(actor));
        }

        internal static void Refused(string site, Player p)
        {
            Refused(site, OwnerOf(p));
        }

        /// <summary>The hit refusal's line: whichever of the two is quarantined.</summary>
        internal static void RefusedPair(string site, Player a, Player b)
        {
            int x = OwnerOf(a), y = OwnerOf(b);
            if (x > 0 && IsQuarantinedActor(x)) Refused(site, x);
            else if (y > 0) Refused(site, y);
        }

        /// <summary>The receivers' refusal of the current master's gameplay
        /// authority (the load gate, the next-round prefix, the call-in
        /// observer): quarantine_refused site=authority, once per boundary.</summary>
        internal static void RefusedAuthority()
        {
            Refused("authority", MasterActor());
        }

        // ------------------------------------------------------------ the boundary digest (cr_bd)

        private static bool _bdDirty;
        private static string _bdLast;

        private static List<FfaLateRules.SlotState> LocalSlots()
        {
            var slots = new List<FfaLateRules.SlotState>();
            foreach (var p in KeptPlayers())
            {
                if (p == null) continue;
                int t = p.TeamID;
                var s = new FfaLateRules.SlotState
                {
                    Slot = t, Rounds = FfaMode.RoundsFor(t), Points = FfaMode.PointsFor(t),
                    PointsTotal = FfaMode.PointsTotalFor(t), Kills = FfaMode.KillsFor(t),
                };
                try
                {
                    var names = FfaMode.SpectatorDeckNames(p.PlayerID);
                    if (names != null) s.Cards.AddRange(names);
                }
                catch { }
                slots.Add(s);
            }
            return slots;
        }

        private static void DigestTick()
        {
            if (!_bdDirty) return;
            _bdDirty = false;
            if (!FfaAssembly.SittingGated() || RoomActors.LocalIsSpectator) return;
            int own = OwnActor();
            if (!(HoldsGrant && Kept(own))) return;
            int level = -1;
            try { level = MapManager.instance != null ? MapManager.instance.currentLevelID : -1; } catch { }
            string bd = I(FfaMode.GameNumber) + ":" + I(PointK) + ":"
                        + FfaLateRules.BoundaryDigest(FfaMode.GameNumber, PointK, I(level), LocalSlots());
            if (bd == _bdLast) return;
            _bdLast = bd;
            try
            {
                var h = new ExitGames.Client.Photon.Hashtable();
                h[PropBd] = bd;
                PhotonNetwork.LocalPlayer.SetCustomProperties(h);
            }
            catch { }
        }

        // ------------------------------------------------------------ the late entry (item 5)

        private static bool _lateEntered;
        private static int _lateLoads;
        private static int _lateFailures;
        private static float _lateArmedRt;
        private static int _lateGame;
        private static int _callInCount;
        private static int _lastCallInLevel = -1;
        private static int _snapK = -1;
        private static object[] _pendingSnap;
        private static int _pendingCallIns;
        private static int _requestSeq = 1;

        /// <summary>Step 1, on `admitted_late {game g}`.</summary>
        internal static void OnAdmittedLate(FfaAssembly.Answer a)
        {
            if (a == null || string.IsNullOrEmpty(a.Lobby) || AdmittedLateLobby == a.Lobby) return;
            AdmittedLateLobby = a.Lobby;
            _lateGame = Math.Max(1, a.Game);
            try { Plugin.Instance.StartCoroutine(AdmittedLateRun(a)); } catch { }
        }

        /// <summary>I1 late_admitted: go=1 arms the late entry; go=0 is a
        /// slow starter that already has its body.</summary>
        private static void LateAdmittedLine(int game, bool go)
        {
            JoinTimeline.Step("late_admitted", "game=" + I(game) + (go ? " go=1 body=0" : " go=0 body=1"));
        }

        private static IEnumerator AdmittedLateRun(FfaAssembly.Answer a)
        {
            // A spawn coroutine still running decides first (at most its 12 s).
            float until = Time.realtimeSinceStartup + 13f;
            while (FfaAssembly.SpawnRunning && Time.realtimeSinceStartup < until) yield return null;
            PublishLate();
            bool body = false;
            try { body = PlayerAssigner.instance != null && PlayerAssigner.instance.hasCreatedLocalPlayer; } catch { }
            if (body)
            {
                // A slow starter: its barrier and load gate pass on admitted_late,
                // it starts with the room, and its body sits out until kept.
                LateAdmittedLine(a.Game, false);
                _runningRoom = FfaAssembly.CurrentRoomName();
                yield break;
            }
            try { SpectatorSync.PinSpectatorClockAndLifecycle("late_entry"); } catch { }
            LateArmed = true;
            _lateArmedRt = Time.realtimeSinceStartup;
            _lateLoads = 0;
            _lateFailures = 0;
            _snapK = -1;
            try { CompetitiveUI.ShowNotification("Joining the match at the next point", new Color(0.6f, 0.9f, 1f), 6f); } catch { }
            LateAdmittedLine(a.Game, true);
            FfaAssembly.ReplayHeldForLate();
        }

        private static void PublishLate()
        {
            try
            {
                var h = new ExitGames.Client.Photon.Hashtable();
                h[PropLate] = Lobby8;
                PhotonNetwork.LocalPlayer.SetCustomProperties(h);
            }
            catch { }
        }

        /// <summary>Step 2: the load gate passes a boundary load for an armed
        /// late entry; the late seat counts it and sends its request after the
        /// load starts. A third load without an entry ends the late entry.</summary>
        internal static void OnBoundaryLoad(string scene)
        {
            if (!LateArmed || _lateEntered) return;
            _lateLoads++;
            JoinTimeline.Step("late_load", "scene=" + scene);
            if (_lateLoads >= 3)
            {
                LateGiveUp();
                return;
            }
            _pendingSnap = null;
            _pendingCallIns = _callInCount;
            try { Plugin.Instance.StartCoroutine(SendLateRequest()); } catch { }
        }

        private static IEnumerator SendLateRequest()
        {
            yield return null;
            try
            {
                Raise(SpectatorSync.EVT_REQUEST, new object[] { (byte)SpectatorSession.PROTOCOL, _requestSeq++, LateMarker },
                      new RaiseEventOptions { Receivers = ReceiverGroup.MasterClient });
            }
            catch { }
        }

        private static void LateGiveUp()
        {
            LateArmed = false;
            _pendingSnap = null;
            FfaAssembly.Exit("join_timeout");
        }

        /// <summary>Step 3, the master's HandleRequest branch: a fighter's late
        /// request is accepted only when the requester is kind l in the master's
        /// grant set and in its `late` list and its u_id resolves to that
        /// entry's slot; one whose actor the master's record does not list yet
        /// is deferred to the next boundary.</summary>
        internal static void OnLateRequest(int sender, int seq)
        {
            if (!MasterMaySend() || !AdmissionRoomNow()) return;
            bool kindL = false;
            int slot = -1;
            foreach (var e in FfaAssembly.Granted)
                if (e.Actor == sender && e.Kind == 'l') { kindL = true; slot = e.Slot; }
            if (!kindL) return;
            bool listed = false;
            foreach (var e in LateList)
                if (e.Actor == sender && e.Slot == slot) listed = true;
            if (!listed) return;
            try
            {
                string sid = RoomActors.SteamIdOf(ActorByNumber(sender));
                var roster = ApiClient.FfaLockedRoster;
                if (roster == null || slot < 0 || slot >= roster.Count || roster[slot] == null
                    || roster[slot].steam_id != sid) return;
            }
            catch { return; }
            _lateRequests[sender] = seq;
        }

        /// <summary>The late snapshot: the spectator's BuildSnapshot with the
        /// late tail appended (the spectator's parse ignores it).</summary>
        private static void SendSnapshot(int actor, int seq, bool closed)
        {
            object[] payload;
            if (closed)
            {
                payload = new object[] { (byte)SpectatorSession.PROTOCOL, seq, LateClosed };
            }
            else
            {
                var snap = SpectatorSync.BuildSnapshotForLate(seq);
                if (snap == null) return;
                int g = FfaMode.GameNumber;
                int[] teams = snap.Length > 9 ? snap[9] as int[] : null;
                int maxTeam = 1;
                if (teams != null) foreach (int t in teams) if (t > maxTeam) maxTeam = t;
                var ptot = new int[maxTeam + 1];
                var kl = new int[maxTeam + 1];
                for (int t = 0; t <= maxTeam; t++) { ptot[t] = FfaMode.PointsTotalFor(t); kl[t] = FfaMode.KillsFor(t); }
                uint seed = 0;
                try { seed = FfaMode.SpawnShuffleSeed(); } catch { }
                // WP6: the late tail, in order after the snapshot's 18 fields:
                // marker 18, pointsTotal 19, kills 20, game 21, levelId 22 (the
                // snapshot's own, index 5), picks 23, seed 24, k 25, n 26, scale 27.
                int level = N(snap, 5, -1);
                var tail = new object[] { LateMarker, ptot, kl, g, level, new string[0], (int)seed, PointK, PointEpoch, AppliedScaleTag() };
                payload = new object[snap.Length + tail.Length];
                Array.Copy(snap, payload, snap.Length);
                Array.Copy(tail, 0, payload, snap.Length, tail.Length);
                JoinTimeline.Step("seed_pub", "game=" + I(g) + " seed=" + seed.ToString("x8", CultureInfo.InvariantCulture));
            }
            Raise(SpectatorSync.EVT_SNAPSHOT, payload, new RaiseEventOptions { TargetActors = new[] { actor } });
        }

        /// <summary>Step 5: the late seat on a snapshot.</summary>
        private static void OnLateSnapshot(EventData e)
        {
            if (!LateArmed || _lateEntered || RoomActors.LocalIsSpectator) return;
            var a = e.CustomData as object[];
            if (a == null) return;
            if (e.Sender != MasterActor() || !MasterKept())
            {
                Refused("authority", e.Sender);
                return;
            }
            if (a.Length >= 3 && S(a, 2) == LateClosed)
            {
                LateGiveUp();
                return;
            }
            if (a.Length < 28 || S(a, 18) != LateMarker) return;
            int level = N(a, 22, -1);
            int cur = -1;
            try { cur = MapManager.instance != null ? MapManager.instance.currentLevelID : -1; } catch { }
            if (level != cur) return;   // another map: wait for the next boundary
            _pendingSnap = a;
            _snapK = N(a, 25, -1);
            CheckPendingSnapshot();
        }

        private static float _snapCheckRt;

        /// <summary>The digest check, re-run each time a peer's cr_bd changes,
        /// until this boundary's call-in; then the seed, the scale and the spawn.</summary>
        private static void CheckPendingSnapshot()
        {
            var a = _pendingSnap;
            if (a == null) return;
            bool callInCame = _callInCount > _pendingCallIns;
            int g = N(a, 21, 0), k = N(a, 25, 0), level = N(a, 22, -1);
            string digest = SnapshotDigest(a, g, k, level);
            var peers = new List<FfaLateRules.PeerBd>();
            int master = MasterActor(), own = OwnActor();
            foreach (var p in RoomActors.PresentNonSpectators())
            {
                if (p == null || p.ActorNumber == own) continue;
                peers.Add(new FfaLateRules.PeerBd
                {
                    Actor = p.ActorNumber, Slot = SlotOf(p.ActorNumber), IsMaster = p.ActorNumber == master,
                    Kept = IsKeptActor(p.ActorNumber), Bd = CrOf(p, PropBd),
                });
            }
            int peer;
            bool digestOk = FfaLateRules.DigestGate(digest, g, k, _lateGame, peers, out peer);
            JoinTimeline.Step("late_digest", "game=" + I(g) + " k=" + I(k) + " match=" + (digestOk ? "1" : "0") + " peer=" + I(peer));
            if (!digestOk)
            {
                if (callInCame) LateFailure();
                return;
            }
            _pendingSnap = null;
            try
            {
                FfaMode.LateSeedScores(g, a[11] as int[], a[12] as int[], a[19] as int[], a[20] as int[]);
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[FFA-LATE] seed scores: " + ex.Message); }
            _runningRoom = FfaAssembly.CurrentRoomName();
            FfaAssembly.NoteTrigger(_runningRoom, "late_entry");
            uint mine = 0;
            try { mine = FfaMode.SpawnShuffleSeed(); } catch { }
            int theirs = N(a, 24, 0);
            bool seedMatch = (int)mine == theirs;
            JoinTimeline.Step("late_seeded", "seed=" + mine.ToString("x8", CultureInfo.InvariantCulture) + " match=" + (seedMatch ? "1" : "0"));
            string scale = S(a, 27) ?? "";
            bool scaleMatch = scale.Length > 0 && scale == AppliedScaleTag();
            JoinTimeline.Step("late_scale", "scale=" + (scale.Length > 0 ? scale : "-") + " match=" + (scaleMatch ? "1" : "0"));
            bool may = FfaLateRules.MaySpawn(true, false, false, true, digestOk, seedMatch, scaleMatch, callInCame);
            if (!may)
            {
                LateFailure();
                return;
            }
            LateSpawn();
        }

        private static string SnapshotDigest(object[] a, int g, int k, int level)
        {
            var slots = new List<FfaLateRules.SlotState>();
            try
            {
                var teams = a[9] as int[];
                var playerIds = a[8] as int[];
                var rounds = a[11] as int[];
                var points = a[12] as int[];
                var decks = a[13] as string[];
                var offsets = a[14] as int[];
                var ptot = a[19] as int[];
                if (teams != null)
                    for (int i = 0; i < teams.Length; i++)
                    {
                        int t = teams[i];
                        if (t < 0) continue;
                        var s = new FfaLateRules.SlotState
                        {
                            Slot = t,
                            Rounds = rounds != null && t < rounds.Length ? rounds[t] : 0,
                            Points = points != null && t < points.Length ? points[t] : 0,
                            PointsTotal = ptot != null && t < ptot.Length ? ptot[t] : 0,
                        };
                        if (decks != null && offsets != null && i + 1 < offsets.Length)
                            for (int j = offsets[i]; j < offsets[i + 1] && j < decks.Length; j++) s.Cards.Add(decks[j]);
                        slots.Add(s);
                    }
            }
            catch { }
            return FfaLateRules.BoundaryDigest(g, k, I(level), slots);
        }

        private static void LateFailure()
        {
            _pendingSnap = null;
            _lateFailures++;
            if (_lateFailures >= 2) LateGiveUp();
        }

        private static void LateSpawn()
        {
            bool ok = false;
            try
            {
                var pa = PlayerAssigner.instance;
                if (pa != null && !pa.hasCreatedLocalPlayer)
                {
                    InputDevice device = null;
                    try
                    {
                        if (InputManager.ActiveDevices != null && InputManager.ActiveDevices.Count > 0)
                            device = InputManager.ActiveDevices[0];
                    }
                    catch { }
                    pa.CreatePlayer(device, false);
                    ok = true;
                }
            }
            catch (Exception ex) { Plugin.Log.LogError("[FFA-LATE] CreatePlayer failed: " + ex.Message); }
            if (!ok)
            {
                LateFailure();
                return;
            }
            JoinTimeline.Step("late_spawn", "after_ms=" + I((int)((Time.realtimeSinceStartup - _lateArmedRt) * 1000f)));
        }

        /// <summary>The call-in stamp that commits an epoch listing this seat:
        /// its slot's recorded picks (the Stage 1 record, not built on this
        /// lane: none), the `entered` POST, the toast and game_join.</summary>
        private static void OnSelfKept(int g)
        {
            if (string.IsNullOrEmpty(AdmittedLateLobby) || _lateEntered) return;
            _lateEntered = true;
            LateArmed = false;
            JoinTimeline.Step("late_cards", "n=0");
            string lobby = AdmittedLateLobby;
            FfaAssembly.ReceiptThen(lobby, "entered", "\"game\":" + I(Math.Max(1, Math.Min(999, g))), ok =>
            {
                if (!ok) return;
                JoinTimeline.Step("game_join", "game=" + I(g));
                FfaAssembly.ClearOwedToast();
                JoinTimeline.Disarm("game_join");
            });
            try
            {
                CompetitiveUI.ShowNotification("You joined the match in progress. This game is unrated for you.",
                                               new Color(0.6f, 0.9f, 1f), 7f);
            }
            catch { }
        }

        // ------------------------------------------------------------ the tick and the room exit

        internal static void Tick()
        {
            if (!PhotonNetwork.InRoom) return;
            try { FenceTick(); } catch { }
            if (!FfaAssembly.SittingGated()) return;
            try { CallInHoldTick(); } catch (Exception ex) { Plugin.Log.LogWarning("[FFA-LATE] hold: " + ex.Message); }
            try { ReadyTick(); } catch { }
            try { DigestTick(); } catch { }
            float now = Time.realtimeSinceStartup;
            if (_pendingSnap != null && now - _snapCheckRt > 0.5f)
            {
                _snapCheckRt = now;
                try { CheckPendingSnapshot(); } catch { }
            }
            if (now >= _qNextRt && GatedRunning)
            {
                _qNextRt = now + 0.5f;
                ApplyQuarantine();
            }
        }

        /// <summary>The room exit: LAG_OUT ends, the counts, the hold, the fence
        /// episode and the per-room state go.</summary>
        internal static void OnRoomLeft(string room)
        {
            LagOutEnd("room_exit");
            _scale.Clear();
            _latchMaster.Clear();
            AppliedScale = null;
            _hold = null;
            _lastHold = null;
            CallInBypass = false;
            CallInHeldNow = false;
            _fenceEpisode = false;
            _handedOffThisEntry = false;
            _hidden.Clear();
            _qLogged.Clear();
            _bdLast = null;
            _bdDirty = false;
            PointK = 0;
            _pendingSnap = null;
            _deathScheduled = false;
            if (LateArmed) LateArmed = false;
            _readySent = 0;
        }

        private static string I(int v) { return v.ToString(CultureInfo.InvariantCulture); }
    }

    // ================================================================ the patches (item 13)

    /// <summary>Surface 2: a pick for a quarantined actor is refused.</summary>
    [HarmonyPatch(typeof(ApplyCardStats), "RPCA_Pick")]
    internal static class FfaLate_PickQuarantine_Patch
    {
        private static bool Prefix(int[] actorIDs)
        {
            try
            {
                if (actorIDs == null || !FfaLateEntry.GatedRunning) return true;
                foreach (int id in actorIDs)
                {
                    var view = PhotonNetwork.GetPhotonView(id);
                    var p = view != null ? view.GetComponent<Player>() : null;
                    if (p != null && FfaLateEntry.IsQuarantined(p))
                    {
                        FfaLateEntry.Refused("pick", p);
                        return false;
                    }
                }
            }
            catch { }
            return true;
        }

        [HarmonyCleanup]
        private static Exception Cleanup(System.Reflection.MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            if (exception == null) FfaLateEntry.PickPrefixAttached = true;
            return exception;
        }
    }

    /// <summary>Surface 3: the force RPC's receiver refuses a quarantined target.</summary>
    [HarmonyPatch(typeof(HealthHandler), "RPCA_SendTakeForce")]
    internal static class FfaLate_ForceQuarantine_Patch
    {
        private static bool Prefix(HealthHandler __instance)
        {
            try
            {
                var p = __instance != null ? __instance.GetComponent<Player>() : null;
                if (p != null && FfaLateEntry.IsQuarantined(p))
                {
                    FfaLateEntry.Refused("force", p);
                    return false;
                }
            }
            catch { }
            return true;
        }

        [HarmonyCleanup]
        private static Exception Cleanup(System.Reflection.MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            if (exception == null) FfaLateEntry.ForcePrefixAttached = true;
            return exception;
        }
    }

    /// <summary>A seat that sits out answers no sync-up request (vanilla's
    /// wait completes on the first reply).</summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "RPCO_RequestSyncUp")]
    internal static class FfaLate_NoSyncReply_Patch
    {
        private static bool Prefix()
        {
            try
            {
                if (FfaLateEntry.LocalSitsOut())
                {
                    FfaLateEntry.Refused("sync", PhotonNetwork.LocalPlayer != null ? PhotonNetwork.LocalPlayer.ActorNumber : -1);
                    return false;
                }
            }
            catch { }
            return true;
        }

        [HarmonyCleanup]
        private static Exception Cleanup(System.Reflection.MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            if (exception == null) FfaLateEntry.SyncPrefixAttached = true;
            return exception;
        }
    }

    /// <summary>A seat that sits out sends no map-loaded report (readiness is
    /// one scalar any report can satisfy).</summary>
    [HarmonyPatch(typeof(MapManager), "ReportMapLoaded")]
    internal static class FfaLate_NoMapReport_Patch
    {
        private static bool Prefix()
        {
            try { return !FfaLateEntry.LocalSitsOut(); }
            catch { return true; }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(System.Reflection.MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            if (exception == null) FfaLateEntry.MapReportPrefixAttached = true;
            return exception;
        }
    }

    /// <summary>Surface 5: the re-shows cannot show a quarantined body.</summary>
    [HarmonyPatch(typeof(PlayerManager), "SetPlayersVisible")]
    internal static class FfaLate_Visible_Patch
    {
        private static void Postfix()
        {
            try { FfaLateEntry.ApplyQuarantine(); } catch { }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(System.Reflection.MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            if (exception == null) FfaLateEntry.VisiblePostfixAttached = true;
            return exception;
        }
    }

    [HarmonyPatch(typeof(PlayerManager), "SetPlayersSimulated")]
    internal static class FfaLate_Simulated_Patch
    {
        private static void Postfix()
        {
            try { FfaLateEntry.ApplyQuarantine(); } catch { }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(System.Reflection.MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            if (exception == null) FfaLateEntry.SimulatedPostfixAttached = true;
            return exception;
        }
    }

    /// <summary>A body that appears mid-point is out of sight and out of the
    /// simulation from its first frame.</summary>
    [HarmonyPatch(typeof(PlayerManager), "RegisterPlayer")]
    internal static class FfaLate_Register_Patch
    {
        private static void Postfix()
        {
            try { FfaLateEntry.ApplyQuarantine(); } catch { }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(System.Reflection.MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            if (exception == null) FfaLateEntry.RegisterPostfixAttached = true;
            return exception;
        }
    }

    /// <summary>The call-in hold (admission rooms): the call-in waits at most
    /// ASM_STAMP_WAIT_S for the stamp of the master that sent it, then replays
    /// locally under a one-shot bypass.</summary>
    [HarmonyPatch(typeof(MapManager), "RPCA_CallInNewMapAndMovePlayers")]
    internal static class FfaLate_CallInHold_Patch
    {
        [HarmonyPriority(Priority.First)]
        private static bool Prefix(int mapID)
        {
            try { return FfaLateEntry.OnCallIn(mapID); }
            catch { return true; }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(System.Reflection.MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            if (exception == null) FfaAssembly.CallInHoldAttached = true;
            return exception;
        }
    }
}
