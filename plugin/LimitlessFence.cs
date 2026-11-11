using System;
using System.Collections.Generic;
using System.Reflection;
using System.Security.Cryptography;
using HarmonyLib;
using Photon.Pun;

namespace CompetitiveRounds
{
    /// <summary>
    /// Ask 16(a) lane 2, design v4 (md5 4283f353) 4.2 to 4.7: the game's
    /// identity, the seat's epoch and its handoff count, the capability, the
    /// record and the fence's message, wired to Photon's edges. The rules are
    /// LimitlessFenceRules; this class holds the seat's state and reads the
    /// room.
    /// - The gid is the room property cr_lgid. The creating seat stamps a first
    ///   value into the room's initial properties. Each physical game mints a
    ///   new one by compare-and-set, in the game-start prefix below.
    /// - A seat adopts a value only as the server relays it, with the room's
    ///   properties at its join or in OnRoomPropertiesUpdate. Its own write
    ///   counts only at its echo (lesson 428).
    /// - The epoch rises at each of the seat's own game starts (a spectator's
    ///   is its first call-in after the terminal score) and at room exit. The
    ///   handoff count rises at every master switch, before anything else
    ///   there.
    /// Nothing here is a barrier: no seat waits for a gid (lessons 280, 287).
    /// </summary>
    internal static class LimitlessFence
    {
        internal const string GidKey = "cr_lgid";

        /// <summary>4.3, F2: the mirror for joiners, holding the whole record.</summary>
        internal const string RecordKey = "cr_lrec";

        /// <summary>4.7, R2: a fighter's opt-in, holding the gid it opts into.</summary>
        internal const string OptInKey = "cr_limitless";

        private static readonly LimitlessFenceRules.GidLedger _ledger = new LimitlessFenceRules.GidLedger();
        private static int _epoch;
        private static int _handoff;
        private static bool _awaiting;
        private static bool _startedInRoom;
        private static bool _spectatorBoundaryDue;

        internal static int Epoch { get { return _epoch; } }
        internal static int HandoffCount { get { return _handoff; } }

        /// <summary>The seat's live gid, or null while it holds none.</summary>
        internal static string CurrentLiveGid
        {
            get
            {
                var g = _ledger.CurrentGid;
                return _ledger.IsLiveGid(g) ? g : null;
            }
        }

        internal static string NewGid()
        {
            var b = new byte[LimitlessFenceRules.GidLength / 2];
            using (var rng = RandomNumberGenerator.Create()) rng.GetBytes(b);
            return LimitlessFenceRules.GidOf(b);
        }

        /// <summary>4.2: the creating seat's first value goes into the room's
        /// initial properties, so no write races it.</summary>
        internal static void StampInitialGid(ExitGames.Client.Photon.Hashtable roomProps)
        {
            try
            {
                if (roomProps != null) roomProps[GidKey] = NewGid();
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning("[LIMIT] gid stamp failed, the room runs without the feature: " + ex.Message);
            }
        }

        private static string RoomGid()
        {
            var room = PhotonNetwork.CurrentRoom;
            var props = room != null ? room.CustomProperties : null;
            object v = null;
            if (props != null) props.TryGetValue(GidKey, out v);
            return v as string;
        }

        private static string GidPrefix(string gid)
        {
            return LimitlessFenceRules.IsGid(gid) ? gid.Substring(0, 8) : "none";
        }

        /// <summary>The join: the seat adopts the value it receives with the
        /// room's properties.</summary>
        internal static void NoteJoinedRoom()
        {
            RetireRecord("join");
            _joinRecordRead = false;
            _uncoveredLeaving = false;
            _startedInRoom = false;
            _spectatorBoundaryDue = false;
            _awaiting = true;
            _optInWanted = false;
            TryAdopt(RoomGid(), "join");
            WriteOptIn("join");   // clears a value the join carried in
        }

        /// <summary>Room exit is a terminal path (5.3): the current gid ends,
        /// and the epoch rises.</summary>
        internal static void NoteLeftRoom()
        {
            _epoch++;
            _ledger.ExitRoom();
            RetireRecord("room exit");
            _uncoveredLeaving = false;
            _optInWanted = false;
            _awaiting = false;
            _startedInRoom = false;
            _spectatorBoundaryDue = false;
        }

        /// <summary>A master switch. The handoff count rises first, so work
        /// scheduled under the previous master period never acts in this one,
        /// even when this seat is master again (4.3). A seat that becomes master
        /// after its own game start while it holds no live gid mints (4.2).</summary>
        internal static void NoteMasterSwitched(Photon.Realtime.Player newMaster)
        {
            _handoff++;
            Terminate("master change");   // 4.6: a master change terminates a live record
            if (newMaster != null && newMaster.IsLocal) TryMint("handoff");
        }

        /// <summary>The seat's own physical game start (the prefix below). The
        /// epoch rises; the previous gid ends; the room's value is adopted if
        /// this seat has not ended it, else the seat awaits the next arrival.
        /// Then the master mints over a value it has ended.</summary>
        internal static void NoteOwnGameStart()
        {
            RetireRecord("game start");
            _epoch++;
            _startedInRoom = true;
            _spectatorBoundaryDue = false;
            bool adopted = _ledger.AtOwnGameStart(RoomGid());
            _awaiting = !adopted;
            _optInWanted = false;   // D6: the radio resets to off at every game start
            _answerLogged.Clear();
            WriteOptIn("game start");
            Plugin.Log.LogInfo("[LIMIT] game start: epoch=" + _epoch + " gid=" + (adopted ? GidPrefix(_ledger.CurrentGid) : "awaiting"));
            TryMint("start");
        }

        /// <summary>A spectator's terminal score (GM: the observer's game over;
        /// FFA: SpectatorCheckGameOver). The observed game is over, so its gid
        /// ends, and the next call-in opens the next game (5.3). Only the first
        /// report of a game counts.</summary>
        internal static void NoteSpectatorGameOver(string mode)
        {
            if (_spectatorBoundaryDue) return;
            _spectatorBoundaryDue = true;
            var g = _ledger.CurrentGid;
            if (g != null) _ledger.EndGid(g);
            Plugin.Log.LogInfo("[LIMIT] spectator game over (" + mode + "): gid " + GidPrefix(g) + " ended");
        }

        /// <summary>A spectator's call-in. The first after the terminal score
        /// opens the next game: the epoch rises, and the room's value is adopted
        /// if this seat has not ended it. In the server's order the master's
        /// mint precedes its call-in, so the value has usually arrived.</summary>
        internal static void NoteSpectatorCallIn()
        {
            if (!_spectatorBoundaryDue) return;
            _spectatorBoundaryDue = false;
            _epoch++;
            RetireRecord("spectator boundary");
            TryAdopt(RoomGid(), "spectator boundary");
            Plugin.Log.LogInfo("[LIMIT] spectator next game: epoch=" + _epoch + " gid=" + GidPrefix(CurrentLiveGid));
        }

        /// <summary>A room property change, as the server relays it.</summary>
        internal static void NoteRoomProps(ExitGames.Client.Photon.Hashtable changed)
        {
            if (changed == null) return;
            if (changed.ContainsKey(RecordKey)) NoteMirrorSeen(changed[RecordKey] as object[]);
            if (!changed.ContainsKey(GidKey)) return;
            TryAdopt(changed[GidKey] as string, "arrival");
        }

        /// <summary>The mirror's arrival as the server relays it, on every seat
        /// and at the writer's own echo. Logs only: it is the positive
        /// control's line in lane 2's two-seat recipe.</summary>
        private static void NoteMirrorSeen(object[] o)
        {
            bool shaped = o != null && o.Length > 3;
            Plugin.Log.LogInfo("[LIMIT] mirror seen: gid=" + GidPrefix(shaped ? o[1] as string : null)
                + " target=" + (shaped ? o[2] : "?") + " end=" + (shaped ? o[3] : "?"));
        }

        private static void TryAdopt(string value, string why)
        {
            if (!LimitlessFenceRules.AdoptOnArrival(_awaiting, RoomActors.LocalIsSpectator, value, _ledger)) return;
            if (!_ledger.AdoptRelayed(value)) return;
            _awaiting = false;
            RetireRecord("new gid");
            WriteOptIn("new gid");   // the opt-in follows a gid change
            Plugin.Log.LogInfo("[LIMIT] adopted gid " + GidPrefix(value) + " (" + why + ")");
        }

        /// <summary>4.2, F1: the mint is a compare-and-set that expects the
        /// value it replaces. Of two seats that replace the same value, at most
        /// one lands, and every seat adopts the one that did. A spectator hands
        /// the master role on at once and never mints.</summary>
        private static void TryMint(string why)
        {
            try
            {
                if (RoomActors.LocalIsSpectator) return;
                var room = PhotonNetwork.CurrentRoom;
                if (room == null || PhotonNetwork.OfflineMode) return;
                string current = RoomGid();
                if (!LimitlessFenceRules.ShouldMint(PhotonNetwork.IsMasterClient, _startedInRoom, current, _ledger)) return;
                bool sent = room.SetCustomProperties(
                    new ExitGames.Client.Photon.Hashtable { { GidKey, NewGid() } },
                    new ExitGames.Client.Photon.Hashtable { { GidKey, current } });
                Plugin.Log.LogInfo("[LIMIT] mint (" + why + "): sent=" + sent + ", expecting " + GidPrefix(current));
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning("[LIMIT] mint (" + why + ") failed: " + ex.Message);
            }
        }

        // ------------------------------------------------------------------ the capability (4.7)

        /// <summary>The capability: the pre-join player property cr_lim1,
        /// holding section 2's version (LimitlessBounds.Version). It is staged
        /// out of a room only and never changed in one, so it arrives with the
        /// join (lesson 287). Spectators stage it too. A key is never reused for
        /// changed semantics: a change to the fence's protocol takes cr_lim2.</summary>
        internal const string CapabilityProp = "cr_lim1";

        /// <summary>Set by each patch's Harmony cleanup, and only when it
        /// attached. A client never advertises a rule it cannot run (#83).</summary>
        internal static bool GameStartLive;
        internal static bool RawRoundLive;
        internal static bool PlayerDiedLive;
        internal static bool RealEndLive;
        internal static bool HeldUnlockLive;
        internal static bool HeldProgressLive;
        internal static bool RealEndHoldLive { get { return RealEndLive && HeldUnlockLive && HeldProgressLive; } }
        internal static bool FencePatchesLive { get { return GameStartLive && RawRoundLive && PlayerDiedLive && RealEndHoldLive && _hooked; } }

        private static bool _staged;
        private static bool _stageFailedPermanently;

        /// <summary>BoundedDeal.StageCapability's state rules: refuse in a room,
        /// merge only from an idle client state, one-shot, retried from the
        /// persistent tick, and only after the compat verdict.</summary>
        internal static void StageFenceCapability(string source)
        {
            try
            {
                if (_staged || _stageFailedPermanently) return;
                if (!GameStartLive || !RawRoundLive || !PlayerDiedLive)
                {
                    _stageFailedPermanently = true;
                    Plugin.Log.LogError("[LIMIT] a fence patch did NOT attach - the continuation is disabled for this session");
                    return;
                }
                if (!RealEndHoldLive)
                {
                    _stageFailedPermanently = true;
                    Plugin.Log.LogError("[LIMIT] the real end's hold did NOT attach - the continuation is disabled for this session");
                    return;
                }
                if (!_hooked) return;   // the tick retries the hook first
                if (!Plugin.compatCheckComplete) return;
                if (Plugin.modDisabled) { _stageFailedPermanently = true; return; }
                if (PhotonNetwork.InRoom)
                {
                    Plugin.Log.LogError("[LIMIT] refusing to stage while in a room (" + source
                        + ") - an in-room write is the racy path this protocol forbids");
                    return;
                }
                var st = PhotonNetwork.NetworkClientState;
                if (st != Photon.Realtime.ClientState.Disconnected
                    && st != Photon.Realtime.ClientState.PeerCreated
                    && st != Photon.Realtime.ClientState.ConnectedToMasterServer
                    && st != Photon.Realtime.ClientState.JoinedLobby)
                    return;   // connecting or joining: a merge here can go undelivered
                var local = PhotonNetwork.LocalPlayer;
                if (local == null) return;
                string version = LimitlessBounds.Version;
                local.SetCustomProperties(new ExitGames.Client.Photon.Hashtable { { CapabilityProp, version } });
                _staged = true;
                Plugin.Log.LogInfo("[LIMIT] staged " + CapabilityProp + "=" + version + " pre-join (" + source + ", state=" + st + ")");
            }
            catch (Exception ex)
            {
                _stageFailedPermanently = true;
                Plugin.Log.LogError("[LIMIT] staging failed, the continuation is disabled for this session: " + ex.Message);
            }
        }

        /// <summary>Withdraw on compat-disable: peers must not count this seat
        /// capable when the fence will not run.</summary>
        internal static void RevokeFenceCapability()
        {
            try
            {
                if (!_staged) return;
                _staged = false;
                _stageFailedPermanently = true;   // never re-stage this session
                var local = PhotonNetwork.LocalPlayer;
                if (local == null) return;
                local.SetCustomProperties(new ExitGames.Client.Photon.Hashtable { { CapabilityProp, "" } });
                Plugin.Log.LogWarning("[LIMIT] revoked " + CapabilityProp + " - mod disabled, every game ends at its base");
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[LIMIT] revoke failed: " + ex.Message); }
        }

        // ------------------------------------------------------------------ replicated reads (4.7, F4)

        /// <summary>The fighters' actor numbers, from replicated inputs only:
        /// the raw PhotonNetwork.PlayerList filtered by the replicated spectator
        /// role, as the capability quorums read it (VanillaFixes.cs:3807), never
        /// RoomActors.ActiveFighters, whose frozen roster is local state.</summary>
        internal static List<int> ReplicatedFighters()
        {
            var o = new List<int>();
            var list = PhotonNetwork.PlayerList;
            if (list == null) return o;
            for (int i = 0; i < list.Length; i++)
            {
                var a = list[i];
                if (a != null && !RoomActors.IsSpectatorReplicated(a)) o.Add(a.ActorNumber);
            }
            return o;
        }

        /// <summary>Every fighter's opt-in (cr_limitless), as replicated. A
        /// missing or non-string value reads null, which matches no gid.</summary>
        internal static List<string> FighterOptIns()
        {
            var o = new List<string>();
            var list = PhotonNetwork.PlayerList;
            if (list == null) return o;
            for (int i = 0; i < list.Length; i++)
            {
                var a = list[i];
                if (a == null || RoomActors.IsSpectatorReplicated(a)) continue;
                object v = null;
                if (a.CustomProperties != null) a.CustomProperties.TryGetValue(OptInKey, out v);
                o.Add(v as string);
            }
            return o;
        }

        /// <summary>Every actor's capability, spectators included (4.7, 3).</summary>
        internal static List<string> ActorCapabilities()
        {
            var o = new List<string>();
            var list = PhotonNetwork.PlayerList;
            if (list == null) return o;
            for (int i = 0; i < list.Length; i++)
            {
                var a = list[i];
                if (a == null) continue;
                object v = null;
                if (a.CustomProperties != null) a.CustomProperties.TryGetValue(CapabilityProp, out v);
                o.Add(v as string);
            }
            return o;
        }

        // ------------------------------------------------------------------ the record (4.3)

        private static bool _hasRecord;
        private static LimitlessFenceRules.FenceRecord _record;
        private static LimitlessFenceRules.FencePhase _state;
        private static bool _targetRaised;   // R1: SetRecordTarget wrote a target, which the record's retirement puts back
        private static bool _targetFfa;      // the field it wrote: FFA's RoundsToWin, else GM's roundsToWinGame
        private static bool _unconfirmed;    // 4.3: the joiner's starting value from cr_lrec, until a message or the master's snapshot
        private static bool _joinRecordRead; // 4.3: a joiner reads cr_lrec once, with the join, before any snapshot
        private static bool _fenceCall;
        private static readonly HashSet<string> _refusalLogged = new HashSet<string>(StringComparer.Ordinal);

        internal static bool HasRecord { get { return _hasRecord; } }
        internal static LimitlessFenceRules.FencePhase RecordState { get { return _state; } }
        internal static LimitlessFenceRules.FenceRecord CurrentRecord { get { return _record; } }

        /// <summary>Live or terminating: the state every refusal reads.</summary>
        internal static bool RecordOpen
        {
            get { return _hasRecord && _state != LimitlessFenceRules.FencePhase.PhaseEnded; }
        }

        /// <summary>v4 section 6, Table C2: a live or terminating record of this
        /// seat's live gid. GameStateWatcher.PhysicalGameLive reads it.</summary>
        internal static bool RecordOpenForCurrentGid
        {
            get { return RecordOpen && _ledger.IsLiveGid(_record.Gid); }
        }

        /// <summary>Table B (a): FFA's RoundsToWin holds the record's target
        /// while the record is live or terminating. FFA's config writers then
        /// keep their value for the next game (FfaMode.SetConfiguredTarget).</summary>
        internal static bool HoldsFfaTarget
        {
            get { return RecordOpen && _targetRaised && _targetFfa; }
        }

        /// <summary>5.1 (F6): the record is terminating, so its end target can
        /// sit below the lead.</summary>
        internal static bool RecordTerminating
        {
            get { return _hasRecord && _state == LimitlessFenceRules.FencePhase.PhaseTerminating; }
        }

        /// <summary>4.3: a record from an accepted continuation message or from
        /// the master's snapshot, not the join's starting value.</summary>
        internal static bool RecordConfirmed
        {
            get { return _hasRecord && !_unconfirmed; }
        }

        /// <summary>4.3: retired before anything of the next physical game runs
        /// (the game-start prefix, a spectator's boundary), when the seat adopts
        /// a new gid, and at room exit.</summary>
        internal static void RetireRecord(string why)
        {
            _refusalLogged.Clear();
            _departed = false;
            if (!_hasRecord) return;
            RestoreBaseTarget(why);
            _hasRecord = false;
            _unconfirmed = false;
            _state = LimitlessFenceRules.FencePhase.PhaseLive;
            _record = default(LimitlessFenceRules.FenceRecord);
            Plugin.Log.LogInfo("[LIMIT] record retired (" + why + ")");
        }

        /// <summary>R1 (section 3): the target the record raised goes back to
        /// the base when the record retires, before anything of the next game
        /// runs. GM's roundsToWinGame takes the record's base target (vanilla's
        /// ResetMatch leaves the field alone); FFA's RoundsToWin takes the value
        /// its config writers hold for the next game (Table B (a)).</summary>
        private static void RestoreBaseTarget(string why)
        {
            if (!_targetRaised) return;
            _targetRaised = false;
            if (_targetFfa) FfaMode.RestoreConfiguredTarget();
            else
            {
                var gm = GM_ArmsRace.instance;
                if (gm != null) gm.roundsToWinGame = _record.BaseTarget;
            }
            Plugin.Log.LogInfo("[LIMIT] target back at the base (" + why + ")");
        }

        /// <summary>4.3, F2 (Table B (a), the join): a joiner reads the mirror
        /// once, with the join, before any snapshot, and only when its gid is
        /// the room's cr_lgid and live here. The record it installs is
        /// unconfirmed: it only raises the target that seeding compares with,
        /// until a continuation message from the current master confirms it or
        /// the master's snapshot replaces it (TakeSnapshotRecord).</summary>
        internal static void ReadJoinRecord(string site)
        {
            if (_joinRecordRead) return;
            _joinRecordRead = true;
            if (_hasRecord) return;
            var room = PhotonNetwork.CurrentRoom;
            object raw = null;
            if (room == null || room.CustomProperties == null || !room.CustomProperties.TryGetValue(RecordKey, out raw)) return;
            LimitlessFenceRules.FenceRecord rec;
            int[] roster, args;
            int stamp;
            if (!LimitlessFenceRules.TryDecodeRecord(raw as object[], out rec, out roster, out args, out stamp)) return;
            if (!string.Equals(rec.Gid, RoomGid(), StringComparison.Ordinal) || !_ledger.IsLiveGid(rec.Gid)) return;
            _record = rec;
            _hasRecord = true;
            _unconfirmed = true;
            _state = LimitlessFenceRules.NextState(LimitlessFenceRules.FencePhase.PhaseLive, rec.EndFlag);
            _handoffAtRecord = _handoff;
            SetRecordTarget(GM_ArmsRace.instance, FfaMode.EngineActive(), rec.TargetRounds);
            Plugin.Log.LogInfo("[LIMIT] record from the mirror (" + site + ", unconfirmed): gid=" + GidPrefix(rec.Gid)
                + " target=" + rec.TargetRounds + " " + _state);
        }

        /// <summary>5.2 (Table B (a), the spectator snapshot): the master's
        /// snapshot carries its record at [28]-[35] while the record is live or
        /// terminating and confirmed, with the seat's state, which a local
        /// termination moves without a message. Without one the snapshot keeps
        /// today's fields.</summary>
        internal static object[] AppendSnapshotRecord(object[] snap)
        {
            if (snap == null || !RecordOpen || _unconfirmed) return snap;
            var r = _record;
            r.EndFlag = _state == LimitlessFenceRules.FencePhase.PhaseTerminating;
            return LimitlessFenceRules.SnapshotWithRecord(snap, r);
        }

        /// <summary>5.2 (Table B (a), the spectator snapshot), right after its
        /// authority check and before any field applies: the master's record
        /// replaces a joiner's unconfirmed one, or installs where the seat holds
        /// none, when its gid is the room's cr_lgid and live here. A record from
        /// an accepted message stays: the messages are server-ordered. A
        /// snapshot without a record retires an unconfirmed one, since the
        /// master holds none. After the master's snapshot the mirror is not
        /// read.</summary>
        internal static void TakeSnapshotRecord(object[] snap)
        {
            _joinRecordRead = true;
            LimitlessFenceRules.FenceRecord rec;
            if (!LimitlessFenceRules.TrySnapshotRecord(snap, out rec))
            {
                if (_hasRecord && _unconfirmed) RetireRecord("the master's snapshot holds no record");
                return;
            }
            if (_hasRecord && !_unconfirmed) return;
            if (!string.Equals(rec.Gid, RoomGid(), StringComparison.Ordinal) || !_ledger.IsLiveGid(rec.Gid)) return;
            bool replaced = _hasRecord;
            _record = rec;
            _hasRecord = true;
            _unconfirmed = false;
            _state = LimitlessFenceRules.NextState(LimitlessFenceRules.FencePhase.PhaseLive, rec.EndFlag);
            _handoffAtRecord = _handoff;
            SetRecordTarget(GM_ArmsRace.instance, FfaMode.EngineActive(), rec.TargetRounds);
            Plugin.Log.LogInfo("[LIMIT] record from the snapshot (" + (replaced ? "replaces the mirror's" : "new")
                + "): gid=" + GidPrefix(rec.Gid) + " target=" + rec.TargetRounds + " " + _state);
        }

        /// <summary>4.4, F3: while this seat holds a live or terminating record,
        /// every call of RPCA_NextRound that the fence's handler did not make is
        /// refused. Every sibling that changes state on that call reads this as
        /// its first statement.</summary>
        internal static bool RawRoundRefused(string site)
        {
            if (!LimitlessFenceRules.RefuseRawRound(_hasRecord, _state, _fenceCall)) return false;
            if (_refusalLogged.Add(site))
                Plugin.Log.LogWarning("[LIMIT] a raw round call was refused (" + site + "): the record is " + _state);
            return true;
        }

        // ------------------------------------------------------------------ retained and scheduled work (4.5, Table A)

        /// <summary>4.5: what an item captures when it is scheduled: the epoch,
        /// the gid while the seat holds an open record, and the handoff count
        /// (4.4: work that sends compares it at the send).</summary>
        internal struct ResumeTicket
        {
            internal int Epoch;
            internal string Gid;
            internal int Handoff;
        }

        private static readonly HashSet<string> _stopLogged = new HashSet<string>(StringComparer.Ordinal);

        internal static ResumeTicket CaptureTicket()
        {
            return new ResumeTicket { Epoch = _epoch, Gid = RecordOpen ? _record.Gid : null, Handoff = _handoff };
        }

        /// <summary>4.5 (R): at every resume point. A captured gid's record is
        /// ended once the seat holds no record of that gid, or holds it ended.</summary>
        internal static bool TicketResumes(ResumeTicket t)
        {
            bool ended = t.Gid != null
                         && (!_hasRecord || _record.Gid != t.Gid || _state == LimitlessFenceRules.FencePhase.PhaseEnded);
            return LimitlessFenceRules.MayResume(_epoch, t.Epoch, t.Gid, _ledger, ended);
        }

        /// <summary>4.5 (C, F12): cleanup the game owns reads the epoch only.</summary>
        internal static bool TicketCleans(ResumeTicket t)
        {
            return LimitlessFenceRules.MayClean(_epoch, t.Epoch);
        }

        /// <summary>4.4 (S) at a send whose work holds a ticket (FFA's pick
        /// phase): MaySend, with the role as the caller reads it (FFA's
        /// MasterMaySend), and the epoch and the handoff count against the
        /// ticket's. With no gid in the ticket and no record open, the send keeps
        /// today's test, the role alone (F1).</summary>
        internal static bool TicketSends(ResumeTicket t, bool masterNow)
        {
            string gid = TicketGid(t);
            if (gid == null) return masterNow;
            bool live = _ledger.IsLiveGid(gid) && string.Equals(gid, _ledger.CurrentGid, StringComparison.Ordinal);
            bool ended = !_hasRecord || _record.Gid != gid || _state == LimitlessFenceRules.FencePhase.PhaseEnded;
            return LimitlessFenceRules.MaySend(masterNow, live, ended, _epoch, t.Epoch, _handoff, t.Handoff);
        }

        /// <summary>4.4 at FFA's pick phase: a master whose handoff count is no
        /// longer its ticket's (LimitlessFenceRules.HandoffPeriodMoved).</summary>
        internal static bool TicketHandoffMoved(ResumeTicket t, bool masterNow)
        {
            return LimitlessFenceRules.HandoffPeriodMoved(masterNow, TicketGid(t) != null, _handoff, t.Handoff);
        }

        /// <summary>The gid a ticket's send answers to: its own, else the open
        /// record's (a record that opened after the ticket was captured).</summary>
        private static string TicketGid(ResumeTicket t)
        {
            return t.Gid ?? (RecordOpen ? _record.Gid : null);
        }

        /// <summary>4.5 (R) for retained work that a tick or a callback resumes,
        /// not a coroutine (Table A): TicketResumes, the stop logged once per
        /// item and epoch.</summary>
        internal static bool ItemResumes(ResumeTicket t, string name)
        {
            if (TicketResumes(t)) return true;
            NoteItemStopped(name, t);
            return false;
        }
        /// <summary>4.5 (R) where Table A's row reads the epoch alone (the
        /// observer's F5 rows read the attempt generation and the epoch): the
        /// stop logged once per item and epoch.</summary>
        internal static bool EpochHolds(ResumeTicket t, string name)
        {
            if (TicketCleans(t)) return true;
            NoteItemStopped(name, t);
            return false;
        }

        /// <summary>4.5 (R) for a coroutine (Table A): the ticket is captured
        /// here, where the item is scheduled, and TicketResumes runs before every
        /// step, nested enumerators included (LimitlessFenceRules.GuardScheduled).</summary>
        internal static System.Collections.IEnumerator ResumableItem(System.Collections.IEnumerator item, string name)
        {
            var t = CaptureTicket();
            return LimitlessFenceRules.GuardScheduled(item, () => TicketResumes(t), () => NoteItemStopped(name, t));
        }

        /// <summary>4.5 (C) for a coroutine: as ResumableItem, reading the epoch only.</summary>
        internal static System.Collections.IEnumerator CleanupItem(System.Collections.IEnumerator item, string name)
        {
            var t = CaptureTicket();
            return LimitlessFenceRules.GuardScheduled(item, () => TicketCleans(t), () => NoteItemStopped(name, t));
        }

        private static void NoteItemStopped(string name, ResumeTicket t)
        {
            if (_stopLogged.Add(name + ":" + t.Epoch.ToString(System.Globalization.CultureInfo.InvariantCulture)))
                Plugin.Log.LogInfo("[LIMIT] " + name + " stops: its epoch or its record moved");
        }

        // ------------------------------------------------------------------ termination (4.6)

        private static bool _departed;

        /// <summary>4.6: the first statement of each departure route (the
        /// Plugin hook, the hold's NCH prefix and FFA's NCH prefix). The code
        /// treats their order as undefined, so whichever runs first sets
        /// termination before any of them classifies. Idempotent. A spectator's
        /// departure is not a fighter's and sets nothing, nor is a refused
        /// entrant's: it was never admitted (v4 Table B).</summary>
        internal static void TerminateOnDeparture(Photon.Realtime.Player p)
        {
            if (p == null || !RecordOpen || RoomActors.IsSpectatorReplicated(p)) return;
            // The kept-actor view still quarantines an entrant that was never admitted.
            if (FfaLateEntry.IsQuarantinedActor(p.ActorNumber)) return;
            _departed = true;
            Terminate("fighter departure");
        }

        /// <summary>Live to terminating; never back (4.3).</summary>
        private static void Terminate(string why)
        {
            if (!RecordOpen) return;
            var before = _state;
            _state = LimitlessFenceRules.NextState(_state, true);
            if (_state != before) Plugin.Log.LogInfo("[LIMIT] record terminating (" + why + ")");
        }

        /// <summary>4.6: FFA after a master change. The old master's deferred
        /// point fails MaySend, so while a record is live or terminating the
        /// new master resolves a pending point through the fence's sender, with
        /// FfaMode's own gates: no point in transition and at most one fighter
        /// alive. Plugin calls this once the master is settled.</summary>
        internal static void RedriveAfterHandoff(Photon.Realtime.Player newMaster)
        {
            if (newMaster == null || !newMaster.IsLocal || !RecordOpen || !FfaMode.EngineActive()) return;
            FfaMode.RedrivePendingPoint(GM_ArmsRace.instance);
        }

        // ------------------------------------------------------------------ the opt-in (4.7, D4, D6)

        private static bool _optInWanted;

        /// <summary>Lane 3's radio calls this: whether this seat opts in to a
        /// continuation of the current game (D4). The property cr_limitless holds
        /// the live gid only. It follows a gid change, and it clears at each of
        /// the seat's own game starts (D6), at the join and at room exit.</summary>
        internal static void SetOptIn(bool on)
        {
            _optInWanted = on;
            WriteOptIn("radio");
        }

        internal static bool OptInWanted { get { return _optInWanted; } }

        /// <summary>Writes cr_limitless in a room only when it differs from what
        /// the server last relayed for this seat: the live gid while the radio
        /// is on, otherwise nothing (null removes the key).</summary>
        private static void WriteOptIn(string why)
        {
            if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode) return;
            var local = PhotonNetwork.LocalPlayer;
            if (local == null) return;
            string gid = _ledger.CurrentGid;
            string want = _optInWanted && _ledger.IsLiveGid(gid) ? gid : null;
            object have = null;
            if (local.CustomProperties != null) local.CustomProperties.TryGetValue(OptInKey, out have);
            if (string.Equals(have as string, want, StringComparison.Ordinal)) return;
            local.SetCustomProperties(new ExitGames.Client.Photon.Hashtable { { OptInKey, want } });
            Plugin.Log.LogInfo("[LIMIT] opt-in " + (want != null ? "written" : "cleared") + " (" + why + ")");
        }

        // ------------------------------------------------------------------ the sender (4.4, 4.7, 5.1)

        /// <summary>What the master's round end sends: vanilla's own message, the
        /// fence's message, or nothing (MaySend failed or the raise did not go
        /// out; vanilla's message would be refused on every seat).</summary>
        internal enum FenceSend { Vanilla, Sent, Withheld }

        private static int _handoffAtRecord;
        private static int _ffaEpoch;
        private static int _ffaHandoff;
        private static readonly HashSet<string> _answerLogged = new HashSet<string>(StringComparer.Ordinal);

        /// <summary>4.4: FFA's point is scheduled here, before its end-of-frame
        /// yield. MaySend at the send compares the epoch and the handoff count
        /// with these.</summary>
        internal static void NoteFfaPointScheduled()
        {
            _ffaEpoch = _epoch;
            _ffaHandoff = _handoff;
        }

        /// <summary>The master's own cr_lim1 as the server relayed it: the
        /// version every actor must advertise (4.7, 3).</summary>
        private static string OwnCapability()
        {
            var local = PhotonNetwork.LocalPlayer;
            if (local == null || local.CustomProperties == null) return null;
            object v;
            return local.CustomProperties.TryGetValue(CapabilityProp, out v) ? v as string : null;
        }

        /// <summary>4.7 on the GM master, from the PlayerDied prefix: at the round
        /// that would end the game at the base, the decision; past the base,
        /// every round. Vanilla's arguments are the ones its own send carries
        /// (GM_ArmsRace:505-510).</summary>
        internal static FenceSend GmRoundSend(GM_ArmsRace gm)
        {
            if (gm == null || FfaMode.EngineActive()) return FenceSend.Vanilla;
            if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode || !PhotonNetwork.IsMasterClient) return FenceSend.Vanilla;
            var pm = PlayerManager.instance;
            if (pm == null || pm.TeamsAlive() >= 2) return FenceSend.Vanilla;
            int winner = pm.GetLastTeamAlive();
            int[] args = { pm.GetOtherTeam(winner), winner, gm.p1Points, gm.p2Points, gm.p1Rounds, gm.p2Rounds };
            if (RecordOpen && _departed) return WithheldAfterDeparture();
            if (RecordOpen) return SendContinuation(args, new[] { gm.p1Rounds, gm.p2Rounds }, _epoch, _handoff);
            if (winner != 0 && winner != 1) return FenceSend.Vanilla;
            int ptw = gm.pointsToWinRound; if (ptw <= 0) ptw = 2;
            int wRounds = winner == 0 ? gm.p1Rounds : gm.p2Rounds;
            if (!LimitlessFenceRules.RoundEndsGame(winner == 0 ? gm.p1Points : gm.p2Points, wRounds, ptw, gm.roundsToWinGame))
                return FenceSend.Vanilla;
            return SendDecision(args, gm.roundsToWinGame, winner, wRounds, winner == 0 ? gm.p2Rounds : gm.p1Rounds, _epoch, _handoff);
        }

        /// <summary>4.6, 4.7: after a fighter's departure in 1v1, 2v2, OVT or
        /// sct the master sends nothing more for the record. The prefix skips
        /// vanilla's body, and vanilla's departure handler tears the room down.</summary>
        private static FenceSend WithheldAfterDeparture()
        {
            if (_answerLogged.Add("departed"))
                Plugin.Log.LogInfo("[LIMIT] no round message after a departure: the room tears down");
            return FenceSend.Withheld;
        }

        /// <summary>4.7 on the FFA master, at FFA's send (ResolvePointNow), after
        /// its yield. The arguments are FFA's own (FfaMode.cs:2112).</summary>
        internal static FenceSend FfaRoundSend(int winnerTeam)
        {
            if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode) return FenceSend.Vanilla;
            int[] args = { winnerTeam, winnerTeam, 0, 0, 0, 0 };
            var sides = new List<int>();
            int other = 0;
            var pm = PlayerManager.instance;
            if (pm != null && pm.players != null)
                foreach (var p in pm.players)
                {
                    if (p == null) continue;
                    int r = FfaMode.RoundsFor(p.TeamID);
                    sides.Add(r);
                    if (p.TeamID != winnerTeam && r > other) other = r;
                }
            if (RecordOpen) return SendContinuation(args, sides, _ffaEpoch, _ffaHandoff);
            if (winnerTeam < 0) return FenceSend.Vanilla;
            int wRounds = FfaMode.RoundsFor(winnerTeam);
            if (!LimitlessFenceRules.RoundEndsGame(FfaMode.PointsFor(winnerTeam), wRounds, FfaMode.PointsToWinRound, FfaMode.RoundsToWin))
                return FenceSend.Vanilla;
            return SendDecision(args, FfaMode.RoundsToWin, winnerTeam, wRounds, other, _ffaEpoch, _ffaHandoff);
        }

        /// <summary>4.7: the decision at the round that would end the game at the
        /// base. All five tests hold, or vanilla's own message goes out and the
        /// game ends at the base as today. The record is created by each seat's
        /// handler when the message arrives, the master's own echo included.</summary>
        private static FenceSend SendDecision(int[] args, int baseTarget, int winner, int winnerRounds, int otherRounds,
                                              int epochCaptured, int handoffCaptured)
        {
            string gid = _ledger.CurrentGid;
            var d = new LimitlessFenceRules.DecisionInputs
            {
                MaySend = LimitlessFenceRules.MaySend(PhotonNetwork.IsMasterClient, _ledger.IsLiveGid(gid), false,
                                                      _epoch, epochCaptured, _handoff, handoffCaptured),
                LiveGid = gid,
                HasRecord = _hasRecord,
                FighterOptIns = FighterOptIns(),
                ActorCapabilities = ActorCapabilities(),
                MasterVersion = OwnCapability(),
                HoldHasHeldSeat = TeamHoldLoop.FenceHolds(),
                HoldHasPendingCut = TeamHold.Cut != null,
                SeriesFollows = LimitlessFenceRules.SeriesFollows(GameStateWatcher.MatchIsRanked, !FfaMode.EngineActive()),
            };
            var why = LimitlessFenceRules.DecideContinuation(d);
            if (why != LimitlessFenceRules.Decision.Continue)
            {
                if (_answerLogged.Add(why.ToString()))
                    Plugin.Log.LogInfo("[LIMIT] decision: the game ends at the base (" + why + ")");
                return FenceSend.Vanilla;
            }
            var rec = LimitlessFenceRules.DecisionRecord(gid, baseTarget, winner, winnerRounds, otherRounds,
                                                         GameStateWatcher.RankedCodeRoom1v1InProgress);
            var roster = ReplicatedFighters().ToArray();
            if (!RaiseFence(LimitlessFenceRules.EncodeRecord(rec, roster, args, PhotonNetwork.ServerTimestamp)))
            {
                Plugin.Log.LogWarning("[LIMIT] decision: the message did not go out; the game ends at the base");
                return FenceSend.Vanilla;
            }
            Plugin.Log.LogInfo("[LIMIT] decision sent: target=" + rec.TargetRounds + " fighters=" + roster.Length);
            return FenceSend.Sent;
        }

        /// <summary>4.4 and 4.7: every round past the base. MaySend runs at the
        /// send. The master re-reads the opt-ins, the capabilities and its
        /// handoff count (lesson 273): a change in any is an end, and once an end
        /// is decided every later message carries the same record (5.1).</summary>
        private static FenceSend SendContinuation(int[] args, IList<int> sides, int epochCaptured, int handoffCaptured)
        {
            bool may = LimitlessFenceRules.MaySend(PhotonNetwork.IsMasterClient,
                _ledger.IsLiveGid(_record.Gid) && string.Equals(_record.Gid, _ledger.CurrentGid, StringComparison.Ordinal),
                _state == LimitlessFenceRules.FencePhase.PhaseEnded, _epoch, epochCaptured, _handoff, handoffCaptured);
            if (!may)
            {
                if (_answerLogged.Add("withheld"))
                    Plugin.Log.LogWarning("[LIMIT] a round message was withheld: MaySend refused");
                return FenceSend.Withheld;
            }
            // 4.6: a terminating record ends at this send (an FFA departure, a master change).
            bool mustEnd = _state == LimitlessFenceRules.FencePhase.PhaseTerminating
                           || LimitlessFenceRules.MustEnd(FighterOptIns(), _record.Gid, ActorCapabilities(), OwnCapability(),
                                                          _handoff, _handoffAtRecord);
            var rec = LimitlessFenceRules.NextSendRecord(_record, mustEnd, sides);
            if (rec.EndFlag && !_record.EndFlag)
                Plugin.Log.LogInfo("[LIMIT] the master ends the continuation: end target " + rec.TargetRounds);
            if (!RaiseFence(LimitlessFenceRules.EncodeRecord(rec, null, args, PhotonNetwork.ServerTimestamp)))
            {
                Plugin.Log.LogWarning("[LIMIT] a round message did not go out");
                return FenceSend.Withheld;
            }
            return FenceSend.Sent;
        }

        // ------------------------------------------------------------------ the message (4.4, 4.7)

        /// <summary>The fence's message: a raised event (47, 49 and 51-58 are
        /// the mod's other codes).</summary>
        internal const byte EvtFence = 59;

        private static bool _hooked;

        internal static void HookFenceEvents()
        {
            if (_hooked) return;
            try
            {
                if (PhotonNetwork.NetworkingClient == null) return;
                PhotonNetwork.NetworkingClient.EventReceived += OnFenceEvent;
                _hooked = true;
            }
            catch { }
        }

        /// <summary>4.4, F9: ReceiverGroup.All, so the sender applies its own
        /// message as the server relays it, in the same order as every other
        /// seat; reliable, on channel 0 (SendOptions.SendReliable's channel).</summary>
        internal static bool RaiseFence(object[] payload)
        {
            var opts = new Photon.Realtime.RaiseEventOptions { Receivers = Photon.Realtime.ReceiverGroup.All };
            return PhotonNetwork.RaiseEvent(EvtFence, payload, opts, ExitGames.Client.Photon.SendOptions.SendReliable);
        }

        private static void OnFenceEvent(ExitGames.Client.Photon.EventData ev)
        {
            if (ev == null || ev.Code != EvtFence) return;
            try { HandleFenceEvent(ev.Sender, ev.CustomData as object[]); }
            catch (Exception ex) { Plugin.Log.LogWarning("[LIMIT] fence message: " + ex.Message); }
        }

        /// <summary>
        /// 4.7's handler, on every seat, the sender's echo included. The order is
        /// LimitlessFenceRules.HandleFenceMessage's:
        /// 1. the sender is the master now;
        /// 2. the gid is live here and its record is not ended;
        /// 3. vanilla's own transition guard drops before the record changes;
        /// 4. a seat with no record compares the decision roster with its own
        ///    replicated roster.
        /// Then come the record, the target and the master's mirror. Only after
        /// them does the round apply, through vanilla's RPCA_NextRound with the
        /// fence's flag set.
        /// </summary>
        internal static void HandleFenceEvent(int sender, object[] data)
        {
            LimitlessFenceRules.FenceRecord rec;
            int[] roster, args;
            int stamp;
            if (!LimitlessFenceRules.TryDecodeRecord(data, out rec, out roster, out args, out stamp) || args.Length != 6)
            {
                // F11: a message without every field is refused whole. One from
                // the current master is a case the fence does not cover (4.7), so
                // this seat takes its terminal path; one from any other seat
                // applies nothing, as at step 1. A build on another wire format
                // never passes the decision: WireVersion is the feature's protocol,
                // which cr_lim1 carries.
                var m = PhotonNetwork.MasterClient;
                bool fromMaster = m != null && m.ActorNumber == sender;
                Plugin.Log.LogWarning("[LIMIT] a fence message without every field was refused whole (F11), from "
                    + (fromMaster ? "the master: an uncovered case" : "a seat that is not the master"));
                if (fromMaster) TakeUncoveredPath();
                return;
            }
            var gm = GM_ArmsRace.instance;
            bool ffa = FfaMode.EngineActive();
            var master = PhotonNetwork.MasterClient;
            bool same = _hasRecord && string.Equals(_record.Gid, rec.Gid, StringComparison.Ordinal);
            var h = new LimitlessFenceRules.HandlerInputs
            {
                SenderIsMasterNow = master != null && master.ActorNumber == sender,
                MessageGid = rec.Gid,
                Ledger = _ledger,
                HasRecord = same,
                RecordEnded = same && _state == LimitlessFenceRules.FencePhase.PhaseEnded,
                TransitionGuardDrops = gm == null || (ffa ? FfaMode.FenceTransitionGuard() : gm.isTransitioning),
                DecisionRoster = roster,
                OwnFighterRoster = ReplicatedFighters(),
            };
            var outcome = LimitlessFenceRules.HandleFenceMessage(h);
            switch (outcome)
            {
                case LimitlessFenceRules.HandlerOutcome.RefuseNotMaster:
                    Plugin.Log.LogWarning("[LIMIT] refused a fence message: its sender is not the master now");
                    return;
                case LimitlessFenceRules.HandlerOutcome.RefuseUncovered:
                    Plugin.Log.LogWarning("[LIMIT] refused the master's fence message: gid " + GidPrefix(rec.Gid)
                        + " is not live here, or its record ended");
                    TakeUncoveredPath();
                    return;
                case LimitlessFenceRules.HandlerOutcome.DropTransition:
                    Plugin.Log.LogInfo("[LIMIT] dropped a fence message at vanilla's transition guard");
                    return;
                case LimitlessFenceRules.HandlerOutcome.ApplyAsVanilla:
                    Plugin.Log.LogWarning("[LIMIT] the decision roster differs from this seat's: the round applies at the base");
                    ApplyFenceRound(gm, args, stamp);
                    return;
            }
            InstallRecord(rec, outcome == LimitlessFenceRules.HandlerOutcome.CreateRecord);
            SetRecordTarget(gm, ffa, rec.TargetRounds);
            if (PhotonNetwork.IsMasterClient) WriteRecordMirror(rec);
            ApplyFenceRound(gm, args, stamp);
            // v4 section 6, Table C1 (H7): the round that created the record went
            // down RoundOver, so vanilla's GameOver block did not run at the base.
            if (outcome == LimitlessFenceRules.HandlerOutcome.CreateRecord && !ffa) RunBaseResults(gm, rec);
        }

        private static void InstallRecord(LimitlessFenceRules.FenceRecord rec, bool create)
        {
            var before = _state;
            _state = LimitlessFenceRules.NextState(create ? LimitlessFenceRules.FencePhase.PhaseLive : _state, rec.EndFlag);
            _record = rec;
            _hasRecord = true;
            _unconfirmed = false;   // 4.3: an accepted message confirms a joiner's starting value
            if (create) _handoffAtRecord = _handoff;   // MustEnd's handoff count at the decision, on every seat
            if (create)
                Plugin.Log.LogInfo("[LIMIT] record created: gid=" + GidPrefix(rec.Gid) + " target=" + rec.TargetRounds
                    + " base=" + rec.BaseWinner + ":" + rec.BaseWinnerRounds + "-" + rec.BaseOtherRounds + "/" + rec.BaseTarget);
            else if (_state != before)
                Plugin.Log.LogInfo("[LIMIT] record " + _state + ": target=" + rec.TargetRounds);
        }

        /// <summary>Step 4's target: GM's roundsToWinGame or FFA's RoundsToWin.
        /// The round pips keep the base count (lane 1's RoundPipClamp answers a
        /// pip past the last).</summary>
        private static void SetRecordTarget(GM_ArmsRace gm, bool ffa, int target)
        {
            if (ffa) FfaMode.RoundsToWin = target;
            else if (gm != null) gm.roundsToWinGame = target;
            else return;
            _targetRaised = true;   // R1: the record's retirement puts the base back
            _targetFfa = ffa;
        }

        /// <summary>4.3, F2: the mirror for joiners, written by the master only
        /// after its own handler accepted. The write is a compare-and-set that
        /// expects cr_lgid to hold the record's gid and the master key (248) to
        /// hold the writer, so a write made after a mint or a handoff does not
        /// land.</summary>
        private static void WriteRecordMirror(LimitlessFenceRules.FenceRecord rec)
        {
            try
            {
                var room = PhotonNetwork.CurrentRoom;
                var me = PhotonNetwork.LocalPlayer;
                if (room == null || me == null) return;
                room.SetCustomProperties(
                    new ExitGames.Client.Photon.Hashtable { { RecordKey, LimitlessFenceRules.EncodeRecord(rec, null, null, 0) } },
                    new ExitGames.Client.Photon.Hashtable
                    {
                        { GidKey, rec.Gid },
                        { Photon.Realtime.GamePropertyKey.MasterClientId, me.ActorNumber },
                    });
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[LIMIT] mirror write failed: " + ex.Message); }
        }

        /// <summary>Step 5: the round, through vanilla's own method, marked as
        /// the fence's call for the raw-round refusals. The call runs under the
        /// stamp its message carries (the sender's ServerTimestamp at the
        /// raise, one value on every seat), which PoisonRpcStampPatch reports
        /// for the GM's view as it does an RPC's, so poison v3's point boundary
        /// records the same stamp on every seat.</summary>
        private static void ApplyFenceRound(GM_ArmsRace gm, int[] a, int stamp)
        {
            if (gm == null || a == null || a.Length != 6) return;
            int view = gm.view != null ? gm.view.ViewID : 0;
            _fenceCall = true;
            try { PoisonRpcStampPatch.RunStamped(view, stamp, () => gm.RPCA_NextRound(a[0], a[1], a[2], a[3], a[4], a[5])); }
            finally { _fenceCall = false; }
        }

        /// <summary>v4 section 6, Table C1 (H7): set while the real end's GameOver
        /// runs on a seat that holds a live or terminating record. The two
        /// platform prefixes refuse every unlock and progress call while it is
        /// set.</summary>
        internal static bool PlatformResultsHeld;

        /// <summary>v4 section 6, Table C1 (H7), at the base. The round that
        /// created the record went down RoundOver, so vanilla's GameOver block
        /// (GM_ArmsRace:446-495) did not run. This runs it once per record, on
        /// the seat that created it, from the base result, with the base target
        /// where vanilla reads roundsToWinGame, and moves vanilla's streak
        /// counters as vanilla does. A spectator moves nothing: it has no local
        /// team, and its platform calls are suppressed.</summary>
        private static void RunBaseResults(GM_ArmsRace gm, LimitlessFenceRules.FenceRecord rec)
        {
            if (gm == null || SpectatorPatchSupport.Suppress) return;
            try
            {
                int p1, p2;
                LimitlessFenceRules.BaseRounds(rec, out p1, out p2);
                int team = (int)gm.m_localTeam;
                var aw = LimitlessFenceRules.BaseGameAwards((team & 1) != 0, (team & 2) != 0, rec.BaseWinner, p1, p2, rec.BaseTarget);
                bool three = false;
                if (aw.BaseVictory)
                {
                    PlatformCall("UnlockAchievement", "Victory");
                    PlatformCall("ProgressAchievement", "Winner");
                    PlatformCall("ProgressAchievement", "Champion");
                    int last = gm.m_lastWinningTeam, count = gm.m_winCount;
                    three = LimitlessFenceRules.StreakStep(ref last, ref count, rec.BaseWinner);
                    gm.m_lastWinningTeam = last;
                    gm.m_winCount = count;
                    if (three) PlatformCall("UnlockAchievement", "ThreeInARow");
                }
                if (aw.BaseAce) PlatformCall("UnlockAchievement", "Ace");
                if (aw.BaseJoker) PlatformCall("UnlockAchievement", "Joker");
                Plugin.Log.LogInfo("[LIMIT] the base's platform results ran once: victory=" + aw.BaseVictory
                    + " streak=" + three + " ace=" + aw.BaseAce + " joker=" + aw.BaseJoker);
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[LIMIT] the base's platform results: " + ex.Message); }
        }

        /// <summary>One of PlatformManager's two calls (decompile
        /// FriendlyFoe.Platform/PlatformManager.cs:33, :41), by name: the plugin
        /// does not reference the assembly that defines their Achievements
        /// parameter. The value is the enum member vanilla's GameOver names. A
        /// name this build of the game lacks is logged, never silent (#91).</summary>
        private static void PlatformCall(string method, string achievement)
        {
            var m = typeof(FriendlyFoe.Platform.PlatformManager).GetMethod(method, BindingFlags.Public | BindingFlags.Static);
            var p = m != null ? m.GetParameters() : null;
            if (p == null || p.Length != 1 || !p[0].ParameterType.IsEnum || !Enum.IsDefined(p[0].ParameterType, achievement))
            {
                Plugin.Log.LogWarning("[LIMIT] PlatformManager." + method + "(" + achievement + ") is not in this build of the game");
                return;
            }
            m.Invoke(null, new[] { Enum.Parse(p[0].ParameterType, achievement) });
        }

        /// <summary>4.6, Table B: a refusal of the current master's message is a
        /// case the fence does not cover. The seat leaves: a fighter through
        /// vanilla's restart (every other seat sees a departure), a spectator by
        /// the path a room-rules mismatch takes.</summary>
        private static bool _uncoveredLeaving;

        private static void TakeUncoveredPath()
        {
            if (_uncoveredLeaving) return;   // one leave; the room exit clears this
            _uncoveredLeaving = true;
            try
            {
                if (RoomActors.LocalIsSpectator) SpectatorSync.LeaveToMenu("limitless: an uncovered fence message");
                else if (NetworkConnectionHandler.instance != null) NetworkConnectionHandler.instance.NetworkRestart();
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[LIMIT] uncovered path: " + ex.Message); }
        }
    }

    /// <summary>
    /// The fence's game start (v4 4.2, 4.3). Every mode's physical game start
    /// calls DoStartGame: StartGame (GM_ArmsRace:202) and the rematch (:385),
    /// and FFA's prefix swaps in FfaDoStartGame at Normal priority. At
    /// Priority.First this runs before every sibling that changes the game.
    /// HarmonyX runs every prefix even when a sibling skips the original
    /// (#352), so the spectator gate is this prefix's own, the one the
    /// suppressor reads: a spectator's DoStartGame is suppressed
    /// (Spectator_NoDoStartGame_Patch), and its game opens at its call-in.
    /// </summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "DoStartGame")]
    internal static class LimitlessFence_GameStart_Patch
    {
        [HarmonyPriority(Priority.First)]
        private static void Prefix()
        {
            try
            {
                if (SpectatorPatchSupport.Suppress) return;
                LimitlessFence.NoteOwnGameStart();
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning("[LIMIT] game start: " + ex.Message);
            }
        }

        /// <summary>#83: the fence advertises its capability only while this
        /// prefix attached (LimitlessFence.GameStartLive).</summary>
        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            if (exception == null) LimitlessFence.GameStartLive = true;
            return VanillaFixSupport.Cleanup("LimitlessFence game start", exception);
        }
    }

    /// <summary>
    /// v4 4.4, F3: while this seat holds a live or terminating record, a call of
    /// RPCA_NextRound that the fence's handler did not make is refused. At
    /// Priority.First this skips vanilla's body. HarmonyX runs every sibling
    /// prefix and every postfix whatever this returns (#352), so each sibling
    /// that changes state on the call reads the same predicate as its first
    /// statement: FFA's prefix and HandleNextRound, the spectator prefix and
    /// SpectatorObserveRound, PoisonSync's point boundary and the stale
    /// projectile sweep. PointEndEvidencePatch needs none: on a refused call no
    /// count moves and the original did not run, so PointTaken is false.
    /// </summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "RPCA_NextRound")]
    internal static class LimitlessFence_RawRound_Patch
    {
        [HarmonyPriority(Priority.First)]
        private static bool Prefix()
        {
            return !LimitlessFence.RawRoundRefused("gm");
        }

        /// <summary>#83: the fence advertises its capability only while this
        /// prefix attached (LimitlessFence.RawRoundLive).</summary>
        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            if (exception == null) LimitlessFence.RawRoundLive = true;
            return VanillaFixSupport.Cleanup("LimitlessFence raw round", exception);
        }
    }

    /// <summary>
    /// v4 4.7: the GM master's decision at the round that would end the game at
    /// the base, and every round past it. At Priority.Last it runs after every
    /// other PlayerDied prefix and acts only when vanilla's body would still run
    /// (__runOriginal: FFA's engine, the spectator gate or the transition fix may
    /// have skipped it). When the fence sends or withholds the round, vanilla's
    /// body is skipped, and this runs that body's one other effect, the
    /// slow-down (GM_ArmsRace:505-506). A fault runs vanilla's body, as today.
    /// </summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "PlayerDied")]
    internal static class LimitlessFence_PlayerDied_Patch
    {
        [HarmonyPriority(Priority.Last)]
        private static bool Prefix(GM_ArmsRace __instance, bool __runOriginal)
        {
            if (!__runOriginal) return false;
            LimitlessFence.FenceSend sent;
            try { sent = LimitlessFence.GmRoundSend(__instance); }
            catch (Exception ex)
            {
                Plugin.Log.LogError("[LIMIT] the round send faulted: " + ex.Message);
                return true;
            }
            if (sent == LimitlessFence.FenceSend.Vanilla) return true;
            try { if (TimeHandler.instance != null) TimeHandler.instance.DoSlowDown(); } catch { }
            return false;
        }

        /// <summary>#83: the fence advertises its capability only while this
        /// prefix attached (LimitlessFence.PlayerDiedLive).</summary>
        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            if (exception == null) LimitlessFence.PlayerDiedLive = true;
            return VanillaFixSupport.Cleanup("LimitlessFence player died", exception);
        }
    }

    /// <summary>
    /// v4 section 6, Table C1 (H7), at the real end. The base already ran
    /// vanilla's GameOver block once (LimitlessFence.RunBaseResults). While this
    /// seat holds a live or terminating record, GameOver's platform calls are
    /// held by the two prefixes below, and the streak counters it moves
    /// (m_lastWinningTeam, m_winCount) are put back. The finalizer runs on every
    /// exit, a throw included, so the hold never outlives the call. HarmonyX runs
    /// every prefix (#352), so this runs beside any sibling.
    /// </summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "GameOver")]
    internal static class LimitlessFence_RealEnd_Patch
    {
        internal struct RealEndSaved
        {
            internal bool Held;
            internal int LastWinner;
            internal int WinCount;
        }

        private static void Prefix(GM_ArmsRace __instance, out RealEndSaved __state)
        {
            __state = default(RealEndSaved);
            try
            {
                if (!LimitlessFence.RecordOpen || __instance == null) return;
                __state.LastWinner = __instance.m_lastWinningTeam;
                __state.WinCount = __instance.m_winCount;
                __state.Held = true;
                LimitlessFence.PlatformResultsHeld = true;
            }
            catch { }
        }

        private static Exception Finalizer(GM_ArmsRace __instance, RealEndSaved __state, Exception __exception)
        {
            if (!__state.Held) return __exception;
            try
            {
                __instance.m_lastWinningTeam = __state.LastWinner;
                __instance.m_winCount = __state.WinCount;
            }
            catch { }
            LimitlessFence.PlatformResultsHeld = false;
            Plugin.Log.LogInfo("[LIMIT] the real end's platform results were held, and the streak counters put back");
            return __exception;
        }

        /// <summary>#83: the fence advertises its capability only while the
        /// hold attached (LimitlessFence.RealEndHoldLive).</summary>
        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            if (exception == null) LimitlessFence.RealEndLive = true;
            return VanillaFixSupport.Cleanup("LimitlessFence real end", exception);
        }
    }

    /// <summary>v4 section 6, Table C1 (H7): the hold's refusal of an unlock.</summary>
    [HarmonyPatch(typeof(FriendlyFoe.Platform.PlatformManager), "UnlockAchievement")]
    internal static class LimitlessFence_HeldUnlock_Patch
    {
        private static bool Prefix() { return !LimitlessFence.PlatformResultsHeld; }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            if (exception == null) LimitlessFence.HeldUnlockLive = true;
            return VanillaFixSupport.Cleanup("LimitlessFence held unlock", exception);
        }
    }

    /// <summary>v4 section 6, Table C1 (H7): the hold's refusal of a progress
    /// call.</summary>
    [HarmonyPatch(typeof(FriendlyFoe.Platform.PlatformManager), "ProgressAchievement")]
    internal static class LimitlessFence_HeldProgress_Patch
    {
        private static bool Prefix() { return !LimitlessFence.PlatformResultsHeld; }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            if (exception == null) LimitlessFence.HeldProgressLive = true;
            return VanillaFixSupport.Cleanup("LimitlessFence held progress", exception);
        }
    }
}
