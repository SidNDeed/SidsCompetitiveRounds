using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using HarmonyLib;
using Photon.Pun;
using UnityEngine;
using PhotonPlayer = Photon.Realtime.Player;

namespace CompetitiveRounds
{
    /// <summary>The client half of the FFA assembly (connect-failure design
    /// V11, sec3.5 items 1-4 and 6-11, and the gate, the grant set and the
    /// lock's config of item 13). Everything here is active only for a lock
    /// whose payload says `assembly: 1`; a lock without the key (an older
    /// server) or with `assembly: 0` records a statement that reads the room
    /// as ungated, so every ungated room keeps today's behaviour.
    ///
    /// The late entry, the kept epoch, the kept-actor view, the quarantine
    /// and the authority fence live in FfaLateEntry; the pure decisions live
    /// in FfaLateRules (Unity-free, executed by the late-rules harness).</summary>
    internal static class FfaAssembly
    {
        // ------------------------------------------------------------ the advertisement (sec5.1)

        internal const string CapsToken = "ffa_asm1";
        internal const string AdmCapsToken = "ffa_adm1";

        /// <summary>WP5: the room property a short start publishes; its
        /// writer and its reader name this constant.</summary>
        internal const string PropAsmHint = "cr_asm_hint";

        /// <summary>False in every build until the production-enabling release
        /// (sec8.4 G3); only the G3 configuration's SCR_G3 advertises the
        /// admission token before it.</summary>
        internal const bool AdmProductionEnabled = false;
#if SCR_G3
        internal const bool G3Build = true;
#else
        internal const bool G3Build = false;
#endif
        internal static bool AdvertiseAdm => AdmProductionEnabled || G3Build;

        // The six conditions of ffa_asm1 (sec5.1).
        internal static bool Initialised;                 // 1
        internal static bool DoStartPrefixAttached;       // 2 (the DoStartGame prefix's cleanup)
        internal static bool LoadGateAttached;            // 3 (the load gate's cleanup)
        internal const bool ExitHookHandoffCompiled = true;   // 4, with Tick below
        internal const bool BarrierCompiled = true;       // 5 (K20 proves its position)
        // 6: FfaLateEntry.QuarantineAttached()
        internal static bool CallInHoldAttached;          // the admission list's call-in hold
        internal static bool TickSeen;

        /// <summary>Every condition of ffa_asm1: initialised, the start prefix
        /// and the load gate attached, the exit-hook handoff and the Tick
        /// compiled in, the barrier compiled into FfaDoStartGame, and item 13's
        /// patches attached.</summary>
        internal static bool AsmCapable()
        {
            return Initialised && DoStartPrefixAttached && LoadGateAttached
                   && ExitHookHandoffCompiled && BarrierCompiled
                   && FfaLateEntry.QuarantineAttached();
        }

        /// <summary>The admission list of sec3.5 needs the Stage 1 automatic
        /// pick record and the RJ-DRIFT room game number, neither of which
        /// exists on this lane (DEPENDENCY). So this build never advertises
        /// ffa_adm1, whatever AdvertiseAdm says.</summary>
        internal static bool AdmissionListComplete()
        {
            return false;
        }

        /// <summary>The enroll call's caps, comma-joined ("" when neither).</summary>
        internal static string Caps()
        {
            bool asm = AsmCapable();
            bool adm = asm && AdmissionListComplete() && CallInHoldAttached && AdvertiseAdm;
            if (asm && adm) return CapsToken + "," + AdmCapsToken;
            if (asm) return CapsToken;
            return "";
        }

        /// <summary>Plugin.Awake, after the Harmony pass: every attach flag is
        /// known by then.</summary>
        internal static void Init()
        {
            Initialised = true;
            try
            {
                Plugin.Log.LogInfo("[FFA-ASM] init caps=" + (Caps().Length > 0 ? Caps() : "none")
                                   + " start=" + B(DoStartPrefixAttached) + " load=" + B(LoadGateAttached)
                                   + " quarantine=" + B(FfaLateEntry.QuarantineAttached())
                                   + " callin=" + B(CallInHoldAttached) + " adm_list=" + B(AdmissionListComplete()));
            }
            catch { }
        }

        // ------------------------------------------------------------ the payload's windows

        internal static float StartHoldS = 30f;
        internal static float LateWaitS = 6f;
        internal static float SpawnOpenS = 6f;
        internal static float EpochAckS = 2f;
        internal static float StampWaitS = 2f;
        internal static float FenceS = 3f;
        internal const float SuppressLeaseS = 6f;
        internal const float JoinCapS = 125f;
        internal const float ReformCapS = 130f;
        internal const int PostTimeout = 4;

        // ------------------------------------------------------------ the lock

        internal sealed class LockInfo
        {
            public string Lobby = "";
            public string Room = "";
            public string Region = "";
            public int Slot;
            public int N;
            public int Admission;
            public int Admissible;
            public int AdmitLeftMs = -1;
            public int ServerAgeMs = -1;
            public float ReceivedRt;
            public bool Reform;
        }

        /// <summary>The latest gated lock (assembly: 1); null after an ungated
        /// lock.</summary>
        internal static LockInfo Lock;
        /// <summary>The lobby of the room this seat arrived in, captured from
        /// the lock that set that room.</summary>
        internal static string RoomLobbyId;
        internal static string ArrivedRoom;
        /// <summary>The prejoin properties the latest lock staged, republished
        /// by the identity check (item 1).</summary>
        internal static ExitGames.Client.Photon.Hashtable StagedPrejoin;
        /// <summary>V11 item 6: a re-form's StagedPrejoin is still to be set in
        /// IssueJoinOrCreate, immediately before JoinOrCreateRoom (#287).</summary>
        internal static bool PrejoinAtJoin;

        internal sealed class LockCfg
        {
            public string Lobby = "";
            public string Room = "";
            public int Target;
            public int Candidates;
            public int Picks;
            public int Cap;
            public bool Same;
            public bool Ranked;
            public bool Sudden;
        }

        /// <summary>The seven config fields of the latest gated lock, held
        /// across every room leave (item 13, the config; V9, N4).</summary>
        internal static LockCfg LockConfig;

        internal static bool IsGatedRoom(string room)
        {
            var l = Lock;
            return l != null && !string.IsNullOrEmpty(room) && room == l.Room;
        }

        internal static bool IsAdmissionRoom(string room)
        {
            var l = Lock;
            return l != null && l.Admission == 1 && !string.IsNullOrEmpty(room) && room == l.Room;
        }

        internal static bool IsGatedLobby(string lobby)
        {
            var l = Lock;
            return l != null && !string.IsNullOrEmpty(lobby) && lobby == l.Lobby;
        }

        internal static string CurrentRoomName()
        {
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.CurrentRoom == null) return "";
                return PhotonNetwork.CurrentRoom.Name ?? "";
            }
            catch { return ""; }
        }

        private static string RoomOfLobby(string lobby)
        {
            var l = Lock;
            if (l != null && lobby == l.Lobby) return l.Room;
            if (!string.IsNullOrEmpty(RoomLobbyId) && lobby == RoomLobbyId) return ArrivedRoom ?? "";
            return "";
        }

        /// <summary>Every lock payload, gated or not (ArmFfaLock, both the poll
        /// and a reform): the statement for the lock's room, and for a gated
        /// lock the lock itself, its windows, its config and its deadline.
        /// Returns whether the lock is gated.</summary>
        internal static bool OnLockPayload(string resp, bool reform)
        {
            try
            {
                var m = Members(resp);
                string lobby = ExtractJsonString(m, "lobby_id") ?? "";
                string room = ExtractJsonString(m, "room_name") ?? "";
                // An absent key is an older server: assembly 0, today's path.
                int assembly = ExtractJsonInt(m, "assembly", 0);
                int asmStarted = ExtractJsonInt(m, "asm_started", 0);
                float now = Time.realtimeSinceStartup;
                NewSitting(lobby);
                NoteStatement(room, lobby, assembly, asmStarted, now);
                if (assembly != 1)
                {
                    Lock = null;
                    JoinDeadlineRt = 0f;
                    return false;
                }
                var l = new LockInfo
                {
                    Lobby = lobby,
                    Room = room,
                    Region = ExtractJsonString(m, "room_region") ?? "",
                    Slot = ExtractJsonInt(m, "slot", -1),
                    N = ExtractJsonInt(m, "player_count", 0),
                    Admission = ExtractJsonInt(m, "admission", 0),
                    Admissible = ExtractJsonInt(m, "admissible", 0),
                    AdmitLeftMs = ExtractJsonInt(m, "admit_left_ms", -1),
                    ServerAgeMs = ExtractJsonInt(m, "server_age_ms", -1),
                    ReceivedRt = now,
                    Reform = reform,
                };
                Lock = l;
                StartHoldS = Window(m, "start_hold_s", 30f);
                LateWaitS = Window(m, "late_wait_s", 6f);
                SpawnOpenS = Window(m, "spawn_open_s", 6f);
                EpochAckS = Window(m, "epoch_ack_s", 2f);
                StampWaitS = Window(m, "stamp_wait_s", 2f);
                FenceS = Window(m, "fence_s", 3f);
                if (l.ServerAgeMs >= 0) _lastAgeMs = l.ServerAgeMs;
                if (l.Admissible == 1) NoteTrigger(room, "admissible");
                if (ExtractJsonRaw(m, "game_in_progress") == "true") NoteTrigger(room, "game_in_progress");
                LockConfig = new LockCfg
                {
                    Lobby = lobby,
                    Room = room,
                    Target = ExtractJsonInt(m, "score_target", 0),
                    Candidates = ExtractJsonInt(m, "card_candidates", 0),
                    Picks = ExtractJsonInt(m, "initial_picks", 0),
                    Cap = ExtractJsonInt(m, "card_cap", 0),
                    Same = ExtractJsonRaw(m, "same_card_rule") == "true",
                    Ranked = ExtractJsonRaw(m, "lobby_ranked") != "false",
                    Sudden = ExtractJsonRaw(m, "sudden_death") == "true",
                };
                // The outer join deadline (item 11): an admission room follows
                // A plus the 10 s the exclusion needs to arrive; a fallback room
                // is capped at ASM_JOIN_CAP_S; a reform re-arms it to 130 s.
                if (reform)
                    ArmDeadline(now + ReformCapS, lobby);
                else if (l.Admission == 1 && l.AdmitLeftMs >= 0)
                    ArmDeadline(now + l.AdmitLeftMs / 1000f + 10f, lobby);
                else
                    ArmDeadline(now + JoinCapS, lobby);
                _lockStatus = "";
                _spawnPrinted.Clear();
                Plugin.Log.LogInfo("[FFA-ASM] gated lock lobby=" + JoinTimeline.Id8(lobby) + " admission="
                                   + l.Admission + " n=" + l.N + " slot=" + l.Slot + (reform ? " reform=1" : ""));
                return true;
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning("[FFA-ASM] lock payload: " + ex.Message);
                return false;
            }
        }

        private static float Window(Dictionary<string, string> m, string key, float dflt)
        {
            int v = ExtractJsonInt(m, key, -1);
            return v > 0 ? v : dflt;
        }

        /// <summary>A lock for another lobby starts a new sitting: the old
        /// lobby's statements, the grant set, the epoch record and the
        /// per-lobby latches go. The start triggers stay (per room, never
        /// cleared).</summary>
        private static void NewSitting(string lobby)
        {
            if (string.IsNullOrEmpty(lobby) || lobby == _sittingLobby) return;
            _sittingLobby = lobby;
            var drop = new List<string>();
            foreach (var kv in _stmt)
                if (kv.Value.Lobby != lobby) drop.Add(kv.Key);
            foreach (var r in drop)
            {
                _stmt.Remove(r);
                _zero.Remove(r);
            }
            Granted.Clear();
            ReadGranted = false;
            _grantRoom = null;
            _grantLate = false;
            _grantRt = 0f;
            _latest = null;
            _latestStatus = "";
            _rearmedLobby = null;
            _forceStarted.Clear();
            _shortPrinted.Clear();
            _movedTo = null;
            try { FfaLateEntry.ResetSitting(lobby); } catch { }
            _gateFrame = -1;
        }

        // ------------------------------------------------------------ the gate (item 13; V9, N2)

        private sealed class Stmt
        {
            public string Lobby;
            public int Assembly;
            public int AsmStarted;
            public float Rt;
        }

        private static string _sittingLobby;
        private static readonly Dictionary<string, Stmt> _stmt = new Dictionary<string, Stmt>(StringComparer.Ordinal);
        private static readonly HashSet<string> _zero = new HashSet<string>(StringComparer.Ordinal);
        private static readonly Dictionary<string, float> _entryRt = new Dictionary<string, float>(StringComparer.Ordinal);
        private static readonly HashSet<string> _triggers = new HashSet<string>(StringComparer.Ordinal);

        /// <summary>The latest server statement of the sitting's state for a
        /// room, in memory only.</summary>
        internal static void NoteStatement(string room, string lobby, int assembly, int asmStarted, float rt)
        {
            if (string.IsNullOrEmpty(room)) return;
            _stmt[room] = new Stmt { Lobby = lobby, Assembly = assembly, AsmStarted = asmStarted, Rt = rt };
            if (assembly != 1) _zero.Add(room);
            if (asmStarted == 1) NoteTrigger(room, "asm_started");
            _gateFrame = -1;
        }

        /// <summary>This client's latest entry into a room (OnJoinedRankedRoom
        /// through OnArrived): only a statement received after it can read the
        /// room as pre.</summary>
        internal static void NoteEntry(string room)
        {
            if (string.IsNullOrEmpty(room)) return;
            _entryRt[room] = Time.realtimeSinceStartup;
            _gateFrame = -1;
        }

        /// <summary>A start trigger for a room: kept per room name and never
        /// cleared. Every trigger is a server answer to this client or this
        /// client's own start, never a peer's publication.</summary>
        internal static void NoteTrigger(string room, string why)
        {
            if (string.IsNullOrEmpty(room)) return;
            if (_triggers.Add(room)) _gateFrame = -1;
        }

        internal static FfaLateRules.GateResult GateOf(string room)
        {
            string cur = CurrentRoomName();
            bool engine = false;
            try { engine = !string.IsNullOrEmpty(room) && room == cur && FfaMode.EngineActive(); } catch { }
            bool spectator = false;
            try { spectator = RoomActors.LocalIsSpectator; } catch { }
            Stmt st = null;
            bool have = !string.IsNullOrEmpty(room) && _stmt.TryGetValue(room, out st);
            bool postEntry = false;
            if (have)
            {
                float entry;
                postEntry = _entryRt.TryGetValue(room, out entry) && st.Rt >= entry;
            }
            bool trigger = !string.IsNullOrEmpty(room) && _triggers.Contains(room);
            if (!trigger && engine)
            {
                try { trigger = FfaMode.GameStartedInRoom; } catch { }
            }
            if (!trigger)
            {
                try { trigger = FfaLateEntry.GameRunningFor(room); } catch { }
            }
            return FfaLateRules.GateValue(have, have && st.Assembly == 1 && !_zero.Contains(room),
                                          have && st.AsmStarted == 1, postEntry, trigger, engine, spectator);
        }

        private static int _gateFrame = -1;
        private static string _gateRoom = "";
        private static FfaLateRules.GateResult _gateNow = new FfaLateRules.GateResult
        { State = FfaLateRules.Gate.Ungated, Src = "default" };
        private static string _shownRoom = "";
        private static FfaLateRules.Gate _shownState = FfaLateRules.Gate.Ungated;
        private static string _shownSrc = "default";
        private static bool _gateHandling;

        /// <summary>The current room's gate, cached per frame; a statement, an
        /// entry or a trigger invalidates the cache at once. Each change of the
        /// state or its source prints `gate`; a change of the state (or of the
        /// room) also runs InvalidateFighterCache, the quarantine pass and
        /// FenceMaster.</summary>
        internal static FfaLateRules.Gate CurrentGate()
        {
            int f = Time.frameCount;
            string room = CurrentRoomName();
            if (f == _gateFrame && room == _gateRoom) return _gateNow.State;
            _gateFrame = f;
            _gateRoom = room;
            _gateNow = GateOf(room);
            if (!_gateHandling && (room != _shownRoom || _gateNow.State != _shownState || _gateNow.Src != _shownSrc))
            {
                _gateHandling = true;
                try { OnGateChanged(room); }
                finally { _gateHandling = false; }
            }
            return _gateNow.State;
        }

        private static void OnGateChanged(string room)
        {
            bool stateChanged = room != _shownRoom || _gateNow.State != _shownState;
            _shownRoom = room;
            _shownState = _gateNow.State;
            _shownSrc = _gateNow.Src;
            string state = _gateNow.State == FfaLateRules.Gate.Ungated ? "ungated"
                         : _gateNow.State == FfaLateRules.Gate.Pre ? "pre" : "started";
            // Printed for FFA rooms only: every other room is ungated by
            // construction (the engine runs only in a server-issued ffa_ room).
            if ((room ?? "").StartsWith("ffa_") || _gateNow.State != FfaLateRules.Gate.Ungated)
                JoinTimeline.Step("gate", "room=" + RoomTag(room) + " state=" + state + " src=" + _gateNow.Src);
            if (!stateChanged) return;
            try { RoomActors.InvalidateFighterCache(); } catch { }
            try { FfaLateEntry.ApplyQuarantine(); } catch { }
            try { FfaLateEntry.FenceMaster(); } catch { }
        }

        internal static bool SittingGated() { return CurrentGate() != FfaLateRules.Gate.Ungated; }
        internal static bool SittingStarted() { return CurrentGate() == FfaLateRules.Gate.Started; }

        private static string RoomTag(string room)
        {
            try { if (BroadcastMode.IsBroadcastIdentity) return "-"; } catch { }
            return string.IsNullOrEmpty(room) ? "-" : room;
        }

        // ------------------------------------------------------------ the grant set (item 13)

        /// <summary>The union of every `granted` list in this client's own
        /// answers for this lobby: monotone, no entry leaves it during the
        /// sitting (V8, V7-F2).</summary>
        internal static readonly List<FfaLateRules.GrantEntry> Granted = new List<FfaLateRules.GrantEntry>();
        /// <summary>A non-empty granted list has been read in this sitting.</summary>
        internal static bool ReadGranted;

        private static bool UnionGranted(List<FfaLateRules.GrantEntry> list)
        {
            bool changed = false;
            foreach (var e in list)
            {
                if (e.Actor <= 0) continue;
                bool have = false;
                foreach (var g in Granted)
                    if (g.Actor == e.Actor && g.Slot == e.Slot && g.Kind == e.Kind) { have = true; break; }
                if (!have)
                {
                    Granted.Add(e);
                    changed = true;
                }
            }
            if (list.Count > 0 && !ReadGranted)
            {
                ReadGranted = true;
                changed = true;
            }
            return changed;
        }

        // ------------------------------------------------------------ the answers

        internal sealed class Answer
        {
            public string Route = "";
            public string Step = "";
            public string Lobby = "";
            public string Room = "";
            public string Status = "";
            public int Assembly;
            public int AsmStarted;
            public int Pending;
            public int Hold;
            public int WaitMs;
            public int SpawnOk;
            public int SpawnOkAgeMs = -1;
            public int ServerAgeMs = -1;
            public int AdmitLeftMs = -1;
            public int StartN;
            public int Game;
            public List<int> Admissible = new List<int>();
            public List<FfaLateRules.EpochEntry> Roster = new List<FfaLateRules.EpochEntry>();
            public List<FfaLateRules.EpochEntry> Late = new List<FfaLateRules.EpochEntry>();
            public List<FfaLateRules.GrantEntry> Granted = new List<FfaLateRules.GrantEntry>();
            public bool HasLate;
            public string EpochRaw;
            public string LockRaw;
            public float Rt;
        }

        private static Answer _latest;
        private static string _latestStatus = "";
        private static string _lockStatus = "";
        private static int _lastAgeMs = -1;
        private static float _lastRenewRt;

        internal static string LatestStatus => _latestStatus;
        internal static int LatestAgeMs => _lastAgeMs;

        internal static Answer ParseAnswer(string route, string step, string lobby, string json)
        {
            var m = Members(json);
            var a = new Answer
            {
                Route = route,
                Step = step,
                Lobby = lobby,
                Room = RoomOfLobby(lobby),
                Status = ExtractJsonString(m, "status") ?? "unknown",
                Assembly = ExtractJsonInt(m, "assembly", 0),
                AsmStarted = ExtractJsonInt(m, "asm_started", 0),
                Pending = ExtractJsonInt(m, "pending", 0),
                Hold = ExtractJsonInt(m, "hold", 0),
                WaitMs = ExtractJsonInt(m, "wait_ms", 0),
                SpawnOk = ExtractJsonInt(m, "spawn_ok", 0),
                SpawnOkAgeMs = ExtractJsonInt(m, "spawn_ok_age_ms", -1),
                ServerAgeMs = ExtractJsonInt(m, "server_age_ms", -1),
                AdmitLeftMs = ExtractJsonInt(m, "admit_left_ms", -1),
                StartN = ExtractJsonInt(m, "start_n", 0),
                Game = ExtractJsonInt(m, "game", 0),
                EpochRaw = ExtractJsonRaw(m, "epoch"),
                LockRaw = ExtractJsonRaw(m, "lock"),
                Rt = Time.realtimeSinceStartup,
            };
            string adm = ExtractJsonRaw(m, "admissible");
            if (adm != null && adm.StartsWith("[")) a.Admissible = JsonInts(adm);
            foreach (var o in JsonObjects(ExtractJsonRaw(m, "roster")))
            {
                var e = Members(o);
                a.Roster.Add(new FfaLateRules.EpochEntry(ExtractJsonInt(e, "slot", 0), ExtractJsonInt(e, "actor", 0)));
            }
            string lateRaw = ExtractJsonRaw(m, "late");
            a.HasLate = lateRaw != null;
            foreach (var o in JsonObjects(lateRaw))
            {
                var e = Members(o);
                int actor = ExtractJsonInt(e, "actor", 0);
                if (actor > 0)   // a late entry is never null (I2 writer 6, V3-F3)
                    a.Late.Add(new FfaLateRules.EpochEntry(ExtractJsonInt(e, "slot", 0), actor));
            }
            foreach (var o in JsonObjects(ExtractJsonRaw(m, "granted")))
            {
                var e = Members(o);
                string kind = ExtractJsonString(e, "kind") ?? "";
                int actor = ExtractJsonInt(e, "actor", 0);
                if (actor > 0 && (kind == "s" || kind == "l"))
                    a.Granted.Add(new FfaLateRules.GrantEntry(ExtractJsonInt(e, "slot", 0), actor, kind[0]));
            }
            return a;
        }

        private static bool IsRenewing(string status)
        {
            return status == "assembling" || status == "admitting"
                   || status == "start_ok" || status == "admitted_late";
        }

        /// <summary>Every connect and assembly answer for a gated lobby.</summary>
        internal static void HandleAnswer(Answer a)
        {
            if (a == null || string.IsNullOrEmpty(a.Lobby)) return;
            if (!IsGatedLobby(a.Lobby) && a.Lobby != RoomLobbyId) return;   // an earlier lobby's late answer
            string room = a.Room;
            NoteStatement(room, a.Lobby, a.Assembly, a.AsmStarted, a.Rt);
            if (a.ServerAgeMs >= 0) _lastAgeMs = a.ServerAgeMs;
            bool postEntry = !string.IsNullOrEmpty(room) && room == CurrentRoomName();
            if (a.Status != _lockStatus)
            {
                _lockStatus = a.Status;
                JoinTimeline.Step("verdict", "status=" + a.Status + " pending=" + a.Pending + " hold=" + a.Hold
                                             + " spawn_ok=" + a.SpawnOk);
            }
            // The suppression lease (item 3): only a hold = 1 answer renews it,
            // as receipt time + ASM_SUPPRESS_LEASE_S.
            if (a.Hold == 1 && (a.Status == "assembling" || a.Status == "admitted"))
                SuppressUntil = a.Rt + SuppressLeaseS;
            // The start lease (item 8, K41): a renewing answer from any loop.
            if (IsRenewing(a.Status))
            {
                StartLeaseUntilRt = a.Rt + StartHoldS;
                _lastRenewRt = a.Rt;
            }
            // The grant set: a monotone union (V6).
            if (a.Granted.Count > 0)
            {
                NoteTrigger(room, "granted");
                if (UnionGranted(a.Granted))
                {
                    try { RoomActors.InvalidateFighterCache(); } catch { }
                    try { FfaLateEntry.OnGrantedChanged(); } catch { }
                }
            }
            if (a.EpochRaw != null)
            {
                try { FfaLateEntry.OnEpochAnswer(a.Lobby, a.EpochRaw); } catch { }
            }
            if (a.HasLate) FfaLateEntry.LateList = a.Late;
            if (a.Status == "start_ok" || a.Status == "admitting" || a.Status == "admitted_late")
                NoteTrigger(room, a.Status);
            if (a.Admissible.Count > 0) _latestAdmissible = a.Admissible;
            else if (a.Status == "start_ok") _latestAdmissible = a.Admissible;
            if (a.AdmitLeftMs >= 0 && IsAdmissionRoom(room))
            {
                _admitLeftMs = a.AdmitLeftMs;
                _admitLeftRt = a.Rt;
            }
            _latest = a;
            _latestStatus = a.Status;

            // The outer join deadline (item 11).
            if (JoinDeadlineRt > 0f && _deadlineLobby == a.Lobby)
            {
                if (IsAdmissionRoom(room))
                {
                    if (a.Status == "start_ok" || a.Status == "admitted_late" || a.Status == "dissolved"
                        || a.Status == "excluded")
                        JoinDeadlineRt = 0f;
                    else if (a.AdmitLeftMs >= 0 && a.Status != "reformed")
                        JoinDeadlineRt = a.Rt + a.AdmitLeftMs / 1000f + 10f;
                }
                else if (postEntry && a.Status != "reformed")
                {
                    JoinDeadlineRt = 0f;   // the first answer from inside the room
                }
            }

            if (IsAdmissionRoom(room) && postEntry) SpawnGate(a);

            switch (a.Status)
            {
                case "assembling":
                case "admitted":
                    if (a.Pending > 0 && postEntry)
                        Banner(a.Pending, a.WaitMs);
                    break;
                case "start_ok":
                    _grantRoom = room;
                    _grantLate = false;
                    if (_grantRt <= 0f) _grantRt = a.Rt;
                    GuardToastOwed = false;
                    if (IsAdmissionRoom(room)) ShortStart(a);
                    try { FfaLateEntry.FenceMaster(); } catch { }
                    OnLoadGrant(room, "start_ok");
                    break;
                case "admitting":
                    try { FfaLateEntry.FenceMaster(); } catch { }
                    break;
                case "admitted_late":
                    _grantRoom = room;
                    _grantLate = true;
                    if (_grantRt <= 0f) _grantRt = a.Rt;
                    GuardToastOwed = false;
                    try { FfaLateEntry.OnAdmittedLate(a); } catch (Exception ex) { Plugin.Log.LogWarning("[FFA-ASM] admitted_late: " + ex.Message); }
                    try { FfaLateEntry.FenceMaster(); } catch { }
                    OnLoadGrant(room, "admitted_late");
                    break;
                case "reformed":
                    if (!string.IsNullOrEmpty(a.LockRaw)) Move(a.LockRaw, a.Rt);
                    break;
                case "dissolved":
                case "excluded":
                    Exit(a.Status);
                    break;
                case "wrong_region":
                    if (postEntry) OnWrongRegion(a.Lobby, room);
                    break;
                default:
                    break;   // unknown: nothing, and the lease is not renewed
            }
        }

        private static List<int> _latestAdmissible = new List<int>();
        private static int _admitLeftMs = -1;
        private static float _admitLeftRt;

        private static void Banner(int pending, int waitMs)
        {
            if (!JoinTimeline.Throttle("asm_banner", 1.5f)) return;
            try
            {
                int s = Math.Max(0, (waitMs + 999) / 1000);
                CompetitiveUI.ShowNotification(I18n.TrF("Waiting for {0} player(s) to connect: {1} s", pending, s),
                                               new Color(1f, 0.85f, 0.4f), 2.5f);
            }
            catch { }
        }

        // ------------------------------------------------------------ POSTs

        private static string SteamId()
        {
            try { return MatchTracker.LocalSteamId ?? ""; } catch { return ""; }
        }

        private static string Esc(string s)
        {
            try { return ApiClient.JsonEscapeFullPublic(s ?? ""); } catch { return ""; }
        }

        private static string I(int v) { return v.ToString(CultureInfo.InvariantCulture); }
        private static string B(bool v) { return v ? "1" : "0"; }

        /// <summary>One connect or assembly POST (single try, the 4 s timeout),
        /// with the post_fail line on its failure callback.</summary>
        private static void Post(string kind, string step, string lobby, string json, Action<bool, int, string> done)
        {
            string path = "/api/v1/ffa/lobby/" + lobby + "/" + (kind == "assembly" ? "assembly" : "connect");
            ApiClient.AsmPost(ApiClient.BaseUrl + path, json, (ok, resp) =>
            {
                int code = ok ? 200 : ErrorCode(resp);
                if (!ok) PostFail(kind, step, code, resp);
                try { done?.Invoke(ok, code, resp); } catch (Exception ex) { Plugin.Log.LogWarning("[FFA-ASM] answer: " + ex.Message); }
            }, timeout: PostTimeout);
        }

        internal static int ErrorCode(string err)
        {
            if (string.IsNullOrEmpty(err) || !err.StartsWith("HTTP ")) return -1;
            int i = 5, v = 0;
            bool any = false;
            while (i < err.Length && char.IsDigit(err[i]))
            {
                v = v * 10 + (err[i] - '0');
                i++;
                any = true;
            }
            return any ? v : -1;
        }

        private static void PostFail(string kind, string step, int code, string err)
        {
            string e = "other";
            string s = err ?? "";
            if (s.Contains("read_replica")) e = "read_replica";
            else if (s.Contains("asm_deadline")) e = "deadline";
            else if (s.IndexOf("timed out", StringComparison.OrdinalIgnoreCase) >= 0
                     || s.IndexOf("timeout", StringComparison.OrdinalIgnoreCase) >= 0) e = "timeout";
            if (!JoinTimeline.Throttle("post_fail:" + kind, 10f)) return;
            JoinTimeline.Step("post_fail", "kind=" + kind + " step=" + step + " code=" + I(code) + " err=" + e);
        }

        private static string ConnectBody(string step, string extra)
        {
            var sb = new StringBuilder(160);
            sb.Append("{\"steam_id\":\"").Append(Esc(SteamId())).Append("\",\"step\":\"").Append(step).Append('"');
            if (!string.IsNullOrEmpty(extra)) sb.Append(',').Append(extra);
            sb.Append(",\"client_ms\":").Append(I(JoinTimeline.ClientMs())).Append('}');
            return sb.ToString();
        }

        /// <summary>A receipt (I2): retried up to 3 tries 1 s apart until a 2xx
        /// or a 4xx answer. Each 2xx answer is handled like every other.</summary>
        internal static void Receipt(string lobby, string step, string extra)
        {
            ReceiptThen(lobby, step, extra, null);
        }

        /// <summary>A receipt whose 2xx answer (or its end without one) is
        /// reported to the caller: true on a 2xx answer.</summary>
        internal static void ReceiptThen(string lobby, string step, string extra, Action<bool> then)
        {
            if (string.IsNullOrEmpty(lobby) || !IsGatedLobby(lobby) && lobby != RoomLobbyId) return;
            try { Plugin.Instance.StartCoroutine(ReceiptRun(lobby, step, ConnectBody(step, extra), then)); } catch { }
        }

        private static IEnumerator ReceiptRun(string lobby, string step, string json, Action<bool> then = null)
        {
            bool answered = false;
            for (int t = 1; t <= 3; t++)
            {
                bool done = false, stop = false;
                Post("connect", step, lobby, json, (ok, code, resp) =>
                {
                    done = true;
                    if (ok)
                    {
                        stop = true;
                        answered = true;
                        HandleAnswer(ParseAnswer("connect", step, lobby, resp));
                    }
                    else if (code >= 400 && code < 500)
                    {
                        stop = true;
                    }
                });
                float until = Time.realtimeSinceStartup + PostTimeout + 2f;
                while (!done && Time.realtimeSinceStartup < until) yield return null;
                if (stop) break;
                if (t < 3) yield return new WaitForSecondsRealtime(1f);
            }
            if (then != null)
            {
                try { then(answered); } catch { }
            }
        }

        /// <summary>lock_seen (the poll's ready_join, gated payloads only).</summary>
        internal static void ReceiptLockSeen(string resp)
        {
            try
            {
                var m = Members(resp);
                if (ExtractJsonInt(m, "assembly", 0) != 1) return;
                string lobby = ExtractJsonString(m, "lobby_id") ?? "";
                if (string.IsNullOrEmpty(lobby) || lobby == _lockSeenLobby) return;
                _lockSeenLobby = lobby;
                ReceiptFor(lobby, "lock_seen", null);
            }
            catch { }
        }

        private static string _lockSeenLobby;

        /// <summary>A receipt for a lobby that may not be the current Lock yet
        /// (lock_seen precedes the lock routine).</summary>
        private static void ReceiptFor(string lobby, string step, string extra)
        {
            try { Plugin.Instance.StartCoroutine(ReceiptRun(lobby, step, ConnectBody(step, extra))); } catch { }
        }

        internal static void ReceiptCountdown(string lobby, bool fired, string abortToken)
        {
            if (!IsGatedLobby(lobby)) return;
            if (fired) Receipt(lobby, "countdown", null);
            else Receipt(lobby, "countdown_abort", "\"phase\":\"" + abortToken + "\"");
        }

        /// <summary>The joiner's attempt POST (K14): beside both joiner state
        /// entries, behind JoinGate, with joinAttempts + 1.</summary>
        internal static void PostAttempt(int ordinal, string phase)
        {
            var l = Lock;
            if (l == null) return;
            int a = Math.Max(1, Math.Min(9, ordinal));
            Receipt(l.Lobby, "attempt", "\"attempt\":" + I(a) + ",\"phase\":\"" + phase + "\"");
        }

        internal static void PostFailed(string phase, int code)
        {
            var l = Lock;
            if (l == null) return;
            string st = "Idle";
            try { st = PhotonNetwork.NetworkClientState.ToString(); } catch { }
            if (st.Length > 24) st = st.Substring(0, 24);
            var sb = new StringBuilder();
            sb.Append("\"phase\":\"").Append(phase).Append('"');
            if (code != int.MinValue) sb.Append(",\"code\":").Append(I(code));
            sb.Append(",\"state\":\"").Append(st).Append('"');
            string lobby = phase == "spawn" && !string.IsNullOrEmpty(RoomLobbyId) ? RoomLobbyId : l.Lobby;
            Receipt(lobby, "failed", sb.ToString());
        }

        // ------------------------------------------------------------ arrival (item 1)

        private static bool _loopRunning;
        private static float _arrivedRt;

        /// <summary>For a gated room, beside the spawn start in
        /// OnJoinedRankedRoom: the entry, the lobby, the lock's config, the
        /// identity check and its republish, the arrived POST, and the
        /// assembly loop.</summary>
        internal static void OnArrived(string room)
        {
            var l = Lock;
            if (l == null || room != l.Room) return;
            NoteEntry(room);
            RoomLobbyId = l.Lobby;
            ArrivedRoom = room;
            _arrivedRt = Time.realtimeSinceStartup;
            ApplyLockConfig("arrived");
            int uidMissing = 0;
            string uid = "";
            try
            {
                var props = PhotonNetwork.LocalPlayer != null ? PhotonNetwork.LocalPlayer.CustomProperties : null;
                if (props != null && props.ContainsKey("u_id")) uid = props["u_id"] as string ?? "";
            }
            catch { }
            if (string.IsNullOrEmpty(uid))
            {
                uidMissing = 1;
                bool republished = false;
                try
                {
                    if (StagedPrejoin != null && PhotonNetwork.LocalPlayer != null)
                        republished = PhotonNetwork.LocalPlayer.SetCustomProperties(StagedPrejoin);
                }
                catch { }
                JoinTimeline.Step("id_publish", "republished=" + B(republished));
            }
            int actor = 0, count = 0;
            try { actor = PhotonNetwork.LocalPlayer.ActorNumber; } catch { }
            try { count = PhotonNetwork.CurrentRoom.PlayerCount; } catch { }
            string region = "";
            try { region = ApiClient.LiveOnlineRegion() ?? ""; } catch { }
            string extra = "\"actor\":" + I(Math.Max(1, actor)) + ",\"region\":\"" + Esc(RegionCode(region))
                           + "\",\"count\":" + I(Math.Min(20, count)) + ",\"uid_missing\":" + I(uidMissing);
            string lobby = l.Lobby;
            string json = ConnectBody("arrived", extra);
            try { Plugin.Instance.StartCoroutine(ArriveRun(lobby, json)); } catch { }
            if (!_loopRunning)
            {
                try { Plugin.Instance.StartCoroutine(AssemblyLoop(room, lobby)); } catch { }
            }
        }

        private static string RegionCode(string r)
        {
            if (string.IsNullOrEmpty(r)) return "";
            string s = r.Trim().ToLowerInvariant();
            return s.Length > 8 ? s.Substring(0, 8) : s;
        }

        private static IEnumerator ArriveRun(string lobby, string json)
        {
            bool answered = false;
            for (int t = 1; t <= 3 && !answered; t++)
            {
                bool done = false, stop = false;
                Post("connect", "arrived", lobby, json, (ok, code, resp) =>
                {
                    done = true;
                    if (ok)
                    {
                        stop = true;
                        answered = true;
                        var a = ParseAnswer("connect", "arrived", lobby, resp);
                        ArriveAnswerLine(a.Status, a.SpawnOk);
                        HandleAnswer(a);
                    }
                    else if (code >= 400 && code < 500)
                    {
                        stop = true;
                    }
                });
                float until = Time.realtimeSinceStartup + PostTimeout + 2f;
                while (!done && Time.realtimeSinceStartup < until) yield return null;
                if (stop) break;
                if (t < 3) yield return new WaitForSecondsRealtime(1f);
            }
            if (!answered) ArriveAnswerLine("timeout", 0);
        }

        /// <summary>I1 arrive_answer: the arrived POST's answer, or its
        /// timeout after three tries.</summary>
        private static void ArriveAnswerLine(string status, int spawnOk)
        {
            JoinTimeline.Step("arrive_answer", "status=" + status + " spawn_ok=" + I(spawnOk));
        }

        // ------------------------------------------------------------ the census and the loops (item 2)

        /// <summary>The census (K28, K48): the room's actors minus spectators,
        /// from RoomActors.PresentNonSpectators() and never a fighter view, as
        /// {a, s, b, k}, with the sender's own actor, region, room game,
        /// seen_age_ms and epoch_seen.</summary>
        internal static string CensusBody()
        {
            var bodies = new HashSet<int>();
            try
            {
                if (PlayerManager.instance != null && PlayerManager.instance.players != null)
                    foreach (var p in PlayerManager.instance.players)
                    {
                        try { if (p != null && p.data != null && p.data.view != null) bodies.Add(p.data.view.OwnerActorNr); }
                        catch { }
                    }
            }
            catch { }
            var sb = new StringBuilder(400);
            sb.Append('[');
            int n = 0;
            foreach (var a in RoomActors.PresentNonSpectators())
            {
                if (a == null || n >= 20) continue;
                int an = a.ActorNumber;
                string s = RoomActors.SteamIdOf(a) ?? "";
                if (s.Length > 32) s = s.Substring(0, 32);
                int b = bodies.Contains(an) ? 1 : 0;
                int k = FfaLateEntry.IsKeptActor(an) ? 1 : 0;
                if (n > 0) sb.Append(',');
                sb.Append("{\"a\":").Append(I(an)).Append(",\"s\":\"").Append(Esc(s)).Append("\",\"b\":").Append(I(b))
                  .Append(",\"k\":").Append(I(k)).Append('}');
                n++;
            }
            sb.Append(']');
            int actor = 1;
            try { actor = Math.Max(1, PhotonNetwork.LocalPlayer.ActorNumber); } catch { }
            string region = "";
            try { region = RegionCode(ApiClient.LiveOnlineRegion()); } catch { }
            int game = 0;
            try { game = Math.Max(0, Math.Min(999, FfaMode.GameNumber)); } catch { }
            int seen = Math.Max(0, _lastAgeMs);
            var body = new StringBuilder(sb.Length + 200);
            body.Append("{\"steam_id\":\"").Append(Esc(SteamId())).Append("\",\"actor\":").Append(I(actor))
                .Append(",\"region\":\"").Append(Esc(region)).Append("\",\"game\":").Append(I(game))
                .Append(",\"seen_age_ms\":").Append(I(seen))
                .Append(",\"epoch_seen\":").Append(I(Math.Max(0, FfaLateEntry.EpochSeen)))
                .Append(",\"census\":").Append(sb)
                .Append(",\"client_ms\":").Append(I(JoinTimeline.ClientMs())).Append('}');
            return body.ToString();
        }

        private static bool _censusInFlight;

        /// <summary>One census POST, single-flight: the flag is cleared only in
        /// the callback (K23).</summary>
        private static bool SendCensus(string lobby, string why)
        {
            if (_censusInFlight) return false;
            _censusInFlight = true;
            Post("assembly", why, lobby, CensusBody(), (ok, code, resp) =>
            {
                _censusInFlight = false;
                if (ok) HandleAnswer(ParseAnswer("assembly", why, lobby, resp));
            });
            return true;
        }

        private static bool IsDecision(string status)
        {
            return status == "start_ok" || status == "admitted_late" || status == "reformed"
                   || status == "dissolved" || status == "excluded";
        }

        /// <summary>From the arrival until a decision, game_start, a room exit
        /// or 120 s: every 2 s, single-flight with the 4 s timeout, backing off
        /// to 5 s after a failure (sec3.3).</summary>
        private static IEnumerator AssemblyLoop(string room, string lobby)
        {
            _loopRunning = true;
            try
            {
                float start = Time.realtimeSinceStartup;
                float next = start + 2f;
                bool backoff = false;
                while (true)
                {
                    float now = Time.realtimeSinceStartup;
                    if (CurrentRoomName() != room) break;
                    if (now - start > 120f) break;
                    if (IsDecision(_latestStatus) && RoomLobbyId == lobby) break;
                    bool started = false;
                    try { started = FfaMode.GameStartedInRoom; } catch { }
                    if (started) break;
                    if (now >= next && !_censusInFlight)
                    {
                        bool failed = false, done = false;
                        _censusInFlight = true;
                        Post("assembly", "census", lobby, CensusBody(), (ok, code, resp) =>
                        {
                            _censusInFlight = false;
                            done = true;
                            failed = !ok;
                            if (ok) HandleAnswer(ParseAnswer("assembly", "census", lobby, resp));
                        });
                        float until = Time.realtimeSinceStartup + PostTimeout + 2f;
                        while (!done && Time.realtimeSinceStartup < until) yield return null;
                        backoff = failed;
                        next = Time.realtimeSinceStartup + (backoff ? 5f : 2f);
                    }
                    yield return null;
                }
            }
            finally { _loopRunning = false; }
            if (IsAdmissionRoom(room) && _latestStatus == "start_ok")
            {
                try { Plugin.Instance.StartCoroutine(PresenceLoop(room, lobby)); } catch { }
            }
        }

        private static bool _presenceRunning;

        /// <summary>The presence loop (admission rooms): after a short
        /// start_ok, every granted seat POSTs its census every
        /// ASM_PRESENCE_PERIOD_S while the server's age is below A and either
        /// game 1 has not started here or its latest admissible list is
        /// non-empty.</summary>
        private static IEnumerator PresenceLoop(string room, string lobby)
        {
            if (_presenceRunning) yield break;
            _presenceRunning = true;
            try
            {
                while (CurrentRoomName() == room && RoomLobbyId == lobby)
                {
                    float left = _admitLeftMs < 0 ? 0f : _admitLeftMs / 1000f - (Time.realtimeSinceStartup - _admitLeftRt);
                    bool started = false;
                    try { started = FfaMode.GameStartedInRoom; } catch { }
                    if (left <= 0f) break;
                    if (started && _latestAdmissible.Count == 0) break;
                    SendCensus(lobby, "presence");
                    yield return new WaitForSecondsRealtime(5f);
                }
            }
            finally { _presenceRunning = false; }
        }

        private static readonly Dictionary<int, int> _callinCensus = new Dictionary<int, int>();

        /// <summary>After each call-in while the latest `late` list is
        /// non-empty: one census, after A included, at most three per late
        /// actor (I2 writer 4).</summary>
        internal static void AfterCallIn()
        {
            var late = FfaLateEntry.LateList;
            if (late == null || late.Count == 0 || string.IsNullOrEmpty(RoomLobbyId)) return;
            bool any = false;
            foreach (var e in late)
            {
                int c;
                _callinCensus.TryGetValue(e.Actor, out c);
                if (c < 3)
                {
                    _callinCensus[e.Actor] = c + 1;
                    any = true;
                }
            }
            if (any) SendCensus(RoomLobbyId, "callin");
        }

        // ------------------------------------------------------------ the spawn gate (item 1)

        private static string _spawnOpenRoom;
        private static string _spawnLateRoom;
        private static string _spawnClosedRoom;
        private static bool _spawnFirstA;
        private static readonly HashSet<string> _spawnPrinted = new HashSet<string>(StringComparer.Ordinal);
        internal static bool SpawnRunning;

        /// <summary>I1 spawn_open: open_ms is 0 on a start_ok.</summary>
        private static void SpawnOpenLine(Answer a, int openMs)
        {
            JoinTimeline.Step("spawn_open", "status=" + a.Status + " age_ms=" + I(a.ServerAgeMs) + " open_ms=" + I(openMs));
        }

        /// <summary>I1 spawn_hold: once per answer status.</summary>
        private static void SpawnHoldLine(Answer a)
        {
            if (_spawnPrinted.Add(a.Status))
                JoinTimeline.Step("spawn_hold", "status=" + a.Status + " spawn_ok=0 age_ms=" + I(a.ServerAgeMs));
        }

        /// <summary>An admission room's spawn gate: it opens only on a start_ok,
        /// or on the first state-A answer carrying spawn_ok = 1 whose window
        /// (server_age_ms - spawn_ok_age_ms, both from that answer) is at most
        /// spawn_open_s; no other clock is read (K43).</summary>
        private static void SpawnGate(Answer a)
        {
            string room = a.Room;
            if (_spawnOpenRoom == room) return;
            if (a.Status == "start_ok")
            {
                _spawnOpenRoom = room;
                SpawnOpenLine(a, 0);
                return;
            }
            if (a.Status == "assembling" || a.Status == "admitted")
            {
                if (a.SpawnOk == 1 && !_spawnFirstA)
                {
                    _spawnFirstA = true;
                    int openMs = a.ServerAgeMs - a.SpawnOkAgeMs;
                    if (a.SpawnOkAgeMs >= 0 && a.ServerAgeMs >= 0 && openMs <= SpawnOpenS * 1000f)
                    {
                        _spawnOpenRoom = room;
                        SpawnOpenLine(a, openMs);
                    }
                    else
                    {
                        JoinTimeline.Step("spawn_window_missed", "status=" + a.Status + " open_ms=" + I(openMs));
                    }
                    return;
                }
                SpawnHoldLine(a);
                return;
            }
            if (a.Status == "admitting")
            {
                SpawnHoldLine(a);
                return;
            }
            if (a.Status == "admitted_late")
            {
                _spawnLateRoom = room;
                return;
            }
            if (a.Status == "excluded" || a.Status == "dissolved" || a.Status == "reformed")
                _spawnClosedRoom = room;
        }

        /// <summary>Runs the unchanged spawn coroutine only when the gate opens;
        /// its own 12 s deadline starts when it starts.</summary>
        internal static IEnumerator GatedSpawn(Func<IEnumerator> spawn)
        {
            string room = CurrentRoomName();
            _spawnFirstA = false;
            while (true)
            {
                if (CurrentRoomName() != room) yield break;
                if (_spawnOpenRoom == room) break;
                if (_spawnLateRoom == room || _spawnClosedRoom == room) yield break;
                yield return null;
            }
            SpawnRunning = true;
            try { yield return spawn(); }
            finally { SpawnRunning = false; }
        }

        // ------------------------------------------------------------ the short start (item 4)

        private static readonly HashSet<string> _shortPrinted = new HashSet<string>(StringComparer.Ordinal);
        private static readonly HashSet<string> _forceStarted = new HashSet<string>(StringComparer.Ordinal);

        private static void ShortStart(Answer a)
        {
            var l = Lock;
            if (l == null || a.StartN <= 0 || a.StartN >= l.N) return;
            string room = a.Room;
            bool started = false;
            try { started = FfaMode.GameStartedInRoom; } catch { }
            if (_shortPrinted.Add(room))
            {
                JoinTimeline.Step("short_start", "n=" + I(a.StartN) + "/" + I(l.N) + " admissible=" + I(a.Admissible.Count)
                                                 + " age_ms=" + I(a.ServerAgeMs));
                try
                {
                    var r = PhotonNetwork.CurrentRoom;
                    if (r != null && (r.CustomProperties == null || !r.CustomProperties.ContainsKey(PropAsmHint)))
                    {
                        var h = new ExitGames.Client.Photon.Hashtable();
                        h[PropAsmHint] = JoinTimeline.Id8(a.Lobby) + ":short";
                        r.SetCustomProperties(h);
                    }
                }
                catch { }
                int k = a.Admissible.Count > 0 ? a.Admissible.Count : Math.Max(1, l.N - a.StartN);
                try
                {
                    if (k > 1)
                        CompetitiveUI.ShowNotification(I18n.TrF("{0} players could not connect. The match continues; they may join later.", k),
                                                       new Color(1f, 0.85f, 0.4f), 7f);
                    else
                        CompetitiveUI.ShowNotification("One player could not connect. The match continues; they may join later.",
                                                       new Color(1f, 0.85f, 0.4f), 7f);
                }
                catch { }
            }
            if (started) return;
            try { if (GM_ArmsRace.instance != null) GM_ArmsRace.instance.playersNeededToStart = a.StartN; } catch { }
            TryForceStart(a);
        }

        /// <summary>The force start (K37): once per room, only while the game
        /// has not started and is not playing, when the bodies whose owner is a
        /// roster actor number at least start_n, with start_n at least 3.</summary>
        private static void TryForceStart(Answer a)
        {
            string room = a.Room;
            if (_forceStarted.Contains(room) || a.StartN < 3) return;
            bool started = false;
            try { started = FfaMode.GameStartedInRoom; } catch { }
            if (started) return;
            try { if (GameManager.instance != null && GameManager.instance.isPlaying) return; } catch { return; }
            var roster = new HashSet<int>();
            foreach (var e in a.Roster) roster.Add(e.Actor);
            int bodies = 0;
            try
            {
                foreach (var p in PlayerManager.instance.players)
                {
                    try { if (p != null && p.data != null && p.data.view != null && roster.Contains(p.data.view.OwnerActorNr)) bodies++; }
                    catch { }
                }
            }
            catch { }
            if (bodies < a.StartN) return;
            var gm = GM_ArmsRace.instance;
            if (gm == null) return;
            _forceStarted.Add(room);
            Plugin.Log.LogInfo("[FFA-ASM] short start: forcing StartGame (bodies=" + bodies + "/" + a.StartN + ")");
            try { gm.StartGame(); } catch (Exception ex) { Plugin.Log.LogWarning("[FFA-ASM] StartGame: " + ex.Message); }
        }

        // ------------------------------------------------------------ the suppression lease (item 3)

        internal static float SuppressUntil;
        internal static bool StartHoldActive;
        internal static bool GuardToastOwed;
        private static int _owedPresent, _owedWanted;
        private static float _owedFullSince;

        /// <summary>On while the lease holds, a start hold is active, or this
        /// seat's latest answer is admitting or its late entry is armed. It
        /// reads no failure counter (K24).</summary>
        internal static bool SuppressActive
        {
            get
            {
                return Time.realtimeSinceStartup < SuppressUntil || StartHoldActive
                       || _latestStatus == "admitting" || FfaLateEntry.LateArmed;
            }
        }

        internal static bool SuppressGuardToast => SuppressActive;
        internal static bool SuppressStallWarn => SuppressActive;

        /// <summary>The guard's suppressed toast is owed, never dropped.</summary>
        internal static void OweGuardToast(int present, int wanted)
        {
            GuardToastOwed = true;
            _owedPresent = present;
            _owedWanted = wanted;
            _owedFullSince = 0f;
        }

        /// <summary>game_start and game_join clear the owed toast.</summary>
        internal static void ClearOwedToast()
        {
            GuardToastOwed = false;
            _owedFullSince = 0f;
        }

        private static void OwedToastTick()
        {
            if (!GuardToastOwed || SuppressActive) return;
            int present = 0, n = 0;
            try { present = PhotonNetwork.CurrentRoom != null ? PhotonNetwork.CurrentRoom.PlayerCount : 0; } catch { }
            var l = Lock;
            n = l != null ? l.N : _owedWanted;
            string why = "lease";
            if (n > 0 && present >= n)
            {
                // Every seat is here: the last is spawning, so wait up to the
                // spawn deadline plus 3 s for game 1.
                if (_owedFullSince <= 0f) _owedFullSince = Time.realtimeSinceStartup;
                if (Time.realtimeSinceStartup - _owedFullSince < 15f) return;
                why = "full_no_start";
            }
            GuardToastOwed = false;
            JoinTimeline.Step("guard_owed_shown", "why=" + why);
            Cr2v2DiagCallbacks.ShowGuardToast(_owedPresent, _owedWanted);
        }

        // ------------------------------------------------------------ the start barrier (item 8)

        private static string _grantRoom;
        private static bool _grantLate;
        private static float _grantRt;
        internal static float StartLeaseUntilRt;
        internal static string MovedOutOf;
        private static bool _startInFlight;
        private static float _startSentRt = -999f;

        /// <summary>This seat's own start_ok or admitted_late for the room: the
        /// only grant the barrier and the load gate accept.</summary>
        internal static bool HoldsStartGrant(string room)
        {
            return !string.IsNullOrEmpty(room) && room == _grantRoom;
        }

        internal static bool HoldsLateGrant(string room)
        {
            return HoldsStartGrant(room) && _grantLate;
        }

        /// <summary>The barrier applies only to the first start in a room that
        /// a gated lock set (not the rematch: GameStartedInRoom is already true
        /// in that room).</summary>
        internal static bool BarrierApplies(string room)
        {
            return IsGatedRoom(room) && room == ArrivedRoom;
        }

        private static bool LatestIsAssemblingPending0()
        {
            var a = _latest;
            return a != null && a.Status == "assembling" && a.Pending == 0;
        }

        internal sealed class Barrier
        {
            private readonly string _room;
            internal bool Passed;

            internal Barrier(string room) { _room = room; }

            /// <summary>Steps 3-5 of item 8 (steps 1 and 2 and the hold flag are
            /// FfaDoStartGame's, K20): the hold with its start cadence and its
            /// lease, then the pass under a kind-s master, then the lock's
            /// config.</summary>
            internal IEnumerator Run()
            {
                float t0 = Time.realtimeSinceStartup;
                if (!HoldsStartGrant(_room))
                {
                    StartLeaseUntilRt = t0 + StartHoldS;
                    while (true)
                    {
                        if (CurrentRoomName() != _room) { StartHoldActive = false; yield break; }
                        if (HoldsStartGrant(_room)) break;
                        string st = _latestStatus;
                        if (_room == MovedOutOf || st == "reformed" || st == "dissolved" || st == "excluded")
                        {
                            StartGrantLine("verdict", t0);
                            StartHoldActive = false;
                            yield break;
                        }
                        float now = Time.realtimeSinceStartup;
                        if (now >= StartLeaseUntilRt)
                        {
                            StartGrantLine("timeout", t0);
                            StartHoldActive = false;
                            Exit("start_timeout");
                            yield break;
                        }
                        float period = LatestIsAssemblingPending0() ? 2f : 5f;
                        if (!_startInFlight && now - _startSentRt >= period)
                            SendStart();
                        yield return null;
                    }
                }
                // Step 3: its own grant, under a kind-s master, read afresh at
                // each check, for at most ASM_START_HOLD_S from its own grant.
                while (!FfaLateEntry.MasterKept())
                {
                    if (CurrentRoomName() != _room) { StartHoldActive = false; yield break; }
                    try { FfaLateEntry.FenceMaster(); } catch { }
                    if (Time.realtimeSinceStartup - _grantRt > StartHoldS)
                    {
                        StartGrantLine("master_unkept", t0);
                        StartHoldActive = false;
                        Exit("master_unkept");
                        yield break;
                    }
                    yield return null;
                }
                // Step 5: the lock's config first, then the pass.
                if (!ApplyLockConfig("barrier"))
                {
                    StartHoldActive = false;
                    Exit("cfg_missing");
                    yield break;
                }
                StartHoldActive = false;
                StartGrantLine(_grantLate ? "late" : "ok", t0);
                Passed = true;
            }
        }

        /// <summary>The `start` step on the barrier's cadence, single-flight
        /// with the 4 s timeout; the answer is handled like every other.</summary>
        private static void SendStart()
        {
            string lobby = RoomLobbyId;
            if (string.IsNullOrEmpty(lobby)) return;
            _startInFlight = true;
            _startSentRt = Time.realtimeSinceStartup;
            Post("connect", "start", lobby, ConnectBody("start", null), (ok, code, resp) =>
            {
                _startInFlight = false;
                if (ok) HandleAnswer(ParseAnswer("connect", "start", lobby, resp));
            });
        }

        /// <summary>The one start_grant line (where the hold ends, and on a pass
        /// that needed no hold): wait_ms since the barrier began, last_ms since
        /// the last lease-renewing answer.</summary>
        private static void StartGrantLine(string result, float t0)
        {
            float now = Time.realtimeSinceStartup;
            int wait = (int)((now - t0) * 1000f);
            int last = _lastRenewRt > 0f ? (int)((now - _lastRenewRt) * 1000f) : -1;
            JoinTimeline.Step("start_grant", "result=" + result + " wait_ms=" + I(wait) + " last_ms=" + I(last));
            if (result == "timeout" || result == "master_unkept") JoinTimeline.Disarm("start_grant_" + result);
        }

        /// <summary>At this seat's own game start in a gated room (FfaMode,
        /// after OnGameStart): the `started` receipt, the start trigger, and
        /// the replay of a start load held before the start.</summary>
        internal static void AfterGameStart()
        {
            string room = CurrentRoomName();
            if (!IsGatedRoom(room) && room != ArrivedRoom) return;
            NoteTrigger(room, "game_start");
            ClearOwedToast();
            JoinDeadlineRt = 0f;
            if (!string.IsNullOrEmpty(RoomLobbyId) && FfaMode.GameNumber == 1)
                Receipt(RoomLobbyId, "started", null);
            if (_heldScene != null && _heldRoom == room && HoldsStartGrant(room))
                ReplayHeld("start_ok");
        }

        // ------------------------------------------------------------ the load gate (item 9)

        private static string _heldScene;
        private static string _heldRoom;
        private static string _holdPrinted;
        private static bool _replayBypass;
        private static string _countHoldScene;
        private static float _countHoldUntil;

        /// <summary>The prefix's decision: true lets the load run.</summary>
        internal static bool LoadGate(string sceneName)
        {
            if (_replayBypass)
            {
                _replayBypass = false;
                return true;
            }
            if (RoomActors.LocalIsSpectator) return true;
            if (!SittingGated()) return true;
            string room = CurrentRoomName();
            if (!string.IsNullOrEmpty(MovedOutOf) && room == MovedOutOf) return false;
            if (HoldsStartGrant(room))
            {
                bool late = HoldsLateGrant(room) && FfaLateEntry.LateArmed;
                bool started = false;
                try { started = FfaMode.GameStartedInRoom; } catch { }
                if (!late && !started)
                {
                    // The grant is here but this seat's own game has not
                    // started: the start load waits for it, so the load's
                    // count key is this seat's game (AfterGameStart replays).
                    HoldScene(room, sceneName);
                    return false;
                }
                // Item 13, receivers: a load dispatched under a master that
                // MasterKept() rejects is refused, never replayed (that
                // master's map flow is held; a kept master's own load follows).
                if (!FfaLateEntry.MasterKept())
                {
                    FfaLateEntry.RefusedAuthority();
                    return false;
                }
                if (late)
                {
                    try { FfaLateEntry.OnBoundaryLoad(sceneName); } catch { }
                    return CountHold(sceneName);
                }
                return CountHold(sceneName);
            }
            HoldScene(room, sceneName);
            NoteTrigger(room, "load_hold");
            return false;
        }

        private static void HoldScene(string room, string sceneName)
        {
            bool fresh = _heldScene == null;
            _heldScene = sceneName;
            _heldRoom = room;
            if (_holdPrinted != sceneName)
            {
                _holdPrinted = sceneName;
                JoinTimeline.Step("load_hold", "scene=" + sceneName);
            }
            if (fresh && !StartHoldActive) StartLeaseUntilRt = Time.realtimeSinceStartup + StartHoldS;
        }

        /// <summary>The count's hold (V10, N7): in a gated running room a
        /// boundary load whose (game, k) record has not arrived waits at most
        /// ASM_STAMP_WAIT_S, then loads (unscaled, LAG_OUT at the read).</summary>
        private static bool CountHold(string sceneName)
        {
            if (!FfaLateEntry.GatedRunning) return true;
            if (FfaLateEntry.OwnTicketServesLoad()) return true;
            if (FfaLateEntry.HasLoadRecord()) return true;
            float now = Time.realtimeSinceStartup;
            if (_countHoldScene == sceneName)
            {
                if (now >= _countHoldUntil)
                {
                    _countHoldScene = null;
                    return true;
                }
                return false;
            }
            _countHoldScene = sceneName;
            _countHoldUntil = now + StampWaitS;
            return false;
        }

        private static void CountHoldTick()
        {
            if (_countHoldScene == null) return;
            if (FfaLateEntry.HasLoadRecord() || Time.realtimeSinceStartup >= _countHoldUntil)
            {
                string s = _countHoldScene;
                _countHoldScene = null;
                _replayBypass = true;
                try { MapManager.instance.RPCA_LoadLevel(s); }
                catch (Exception ex) { _replayBypass = false; Plugin.Log.LogWarning("[FFA-ASM] count replay: " + ex.Message); }
            }
        }

        /// <summary>A grant for a room: replay its held scene locally under the
        /// one-shot bypass (never an RPC), unless this seat's own game has not
        /// started there yet (AfterGameStart replays then).</summary>
        private static void OnLoadGrant(string room, string why)
        {
            if (_heldScene == null || _heldRoom != room) return;
            if (why == "admitted_late" && FfaLateEntry.LateArmed)
            {
                ReplayHeld("late_entry");
                return;
            }
            bool started = false;
            try { started = FfaMode.GameStartedInRoom; } catch { }
            if (started) ReplayHeld(why);
        }

        private static void ReplayHeld(string why)
        {
            string held = _heldScene;
            _heldScene = null;
            _heldRoom = null;
            _holdPrinted = null;
            if (string.IsNullOrEmpty(held)) return;
            JoinTimeline.Step("load_grant", "why=" + why);
            _replayBypass = true;
            try { MapManager.instance.RPCA_LoadLevel(held); }
            catch (Exception ex) { _replayBypass = false; Plugin.Log.LogWarning("[FFA-ASM] load replay: " + ex.Message); }
        }

        /// <summary>The late entry replays a held scene on admitted_late
        /// (harmless when the boundary has passed).</summary>
        internal static void ReplayHeldForLate()
        {
            if (_heldScene != null) ReplayHeld("late_entry");
        }

        private static void DropHeld()
        {
            _heldScene = null;
            _heldRoom = null;
            _holdPrinted = null;
            _countHoldScene = null;
        }

        /// <summary>The load hold's lease (the barrier's, K41): a held scene
        /// with no renewing answer for ASM_START_HOLD_S ends in start_timeout.
        /// While the barrier holds, the barrier's own loop decides.</summary>
        private static void LoadLeaseTick()
        {
            if (_heldScene == null || StartHoldActive) return;
            if (_heldRoom != CurrentRoomName())
            {
                DropHeld();
                return;
            }
            if (Time.realtimeSinceStartup < StartLeaseUntilRt) return;
            DropHeld();
            Exit("start_timeout");
        }

        // ------------------------------------------------------------ the lock's config (item 13)

        /// <summary>SetPendingConfig from LockConfig, only when its room is the
        /// current room; cfg_apply or cfg_missing.</summary>
        internal static bool ApplyLockConfig(string site)
        {
            var c = LockConfig;
            string room = CurrentRoomName();
            if (c == null || c.Target <= 0 || c.Room != room)
            {
                JoinTimeline.Step("cfg_missing", "site=" + site);
                return false;
            }
            try
            {
                FfaMode.SetPendingConfig(c.Target, c.Candidates > 0 ? c.Candidates : 5, c.Picks > 0 ? c.Picks : 1,
                                         c.Cap > 0 ? c.Cap : 5, c.Same, c.Ranked, c.Sudden);
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning("[FFA-ASM] cfg apply: " + ex.Message);
            }
            JoinTimeline.Step("cfg_apply", "site=" + site + " target=" + I(c.Target) + " lobby=" + JoinTimeline.Id8(c.Lobby));
            return true;
        }

        // ------------------------------------------------------------ Move (item 6)

        private static string _movedTo;
        internal static string HandoffRoom;
        internal static string RegionRearmRoom;
        internal static string RegionRearmRegion;

        /// <summary>On `reformed`: idempotent per new lobby; the fence first;
        /// only the fence when a leave is already in flight; otherwise the lock
        /// routine with reform: true.</summary>
        internal static void Move(string lockRaw, float receiptRt)
        {
            string newLobby = ExtractJsonString(Members(lockRaw), "lobby_id");
            if (string.IsNullOrEmpty(newLobby) || newLobby == _movedTo) return;
            _movedTo = newLobby;
            string old = CurrentRoomName();
            if (string.IsNullOrEmpty(old) && Lock != null) old = Lock.Room;
            MovedOutOf = old;
            DropHeld();
            ClearOwedToast();
            if (ApiClient.FfaLeaveIntentPending) return;
            ApiClient.ArmFfaLock(lockRaw, ApiClient.FfaGenNow, true);
        }

        /// <summary>At the reform countdown's fire: the old room's one-shot
        /// handoff for the exit hook.</summary>
        internal static void OnReformFire()
        {
            HandoffRoom = MovedOutOf;
        }

        // ------------------------------------------------------------ the region re-arm (item 1)

        private static string _rearmedLobby;

        private static void OnWrongRegion(string lobby, string room)
        {
            if (_rearmedLobby == lobby)
            {
                Exit("wrong_region");
                return;
            }
            _rearmedLobby = lobby;
            HandoffRoom = room;
            RegionRearmRoom = room;
            RegionRearmRegion = Lock != null ? Lock.Region : "";
            JoinTimeline.Step("region_rearm", "stage=leave want=" + (string.IsNullOrEmpty(RegionRearmRegion) ? "-" : RegionRearmRegion));
            try { PhotonNetwork.LeaveRoom(); } catch (Exception ex) { Plugin.Log.LogWarning("[FFA-ASM] region leave: " + ex.Message); }
        }

        /// <summary>The room-exit hook's handoff consume (K5): true once for the
        /// room HandoffRoom names; the hook then skips FfaLeaveQueue and
        /// ClearPendingFfaSlot for exactly that room.</summary>
        internal static bool ConsumeHandoff(string room)
        {
            string h = HandoffRoom;
            if (string.IsNullOrEmpty(h)) return false;
            HandoffRoom = null;
            return h == room;
        }

        /// <summary>After the exit, in the hook's handoff consumer: the region
        /// re-arm's SetPendingRoom (the only one, K15), with the region forced.</summary>
        internal static void AfterHandoffExit(string room)
        {
            if (string.IsNullOrEmpty(RegionRearmRoom) || RegionRearmRoom != room) return;
            string region = RegionRearmRegion;
            RegionRearmRoom = null;
            RegionRearmRegion = null;
            JoinTimeline.Step("region_rearm", "stage=rearm want=" + (string.IsNullOrEmpty(region) ? "-" : region));
            Plugin.SetPendingRoom(room, region, gated: true);
        }

        // ------------------------------------------------------------ Exit and the release (item 7)

        private static bool _exiting;

        /// <summary>The seat's own end of a gated lock: the release route for
        /// fence_expired and for an admitted seat's join_timeout, the leave
        /// route for every other why; then NetworkRestart, the disarm and a
        /// toast (D-Q6).</summary>
        internal static void Exit(string why)
        {
            if (_exiting) return;
            _exiting = true;
            try
            {
                bool lagMaster = why == "fence_expired" && FfaLateEntry.LagOutNow() && PhotonNetwork.IsMasterClient;
                bool release = why == "fence_expired"
                               || (why == "join_timeout" && !string.IsNullOrEmpty(FfaLateEntry.AdmittedLateLobby));
                if (release)
                    Release(why);
                else
                    ApiClient.FfaLeaveQueue(label: LabelFor(why));
                Plugin.Log.LogInfo("[FFA-ASM] exit why=" + why + (release ? " via=release" : " via=leave"));
                DropHeld();
                StartHoldActive = false;
                JoinDeadlineRt = 0f;
                ClearOwedToast();
                // I4's excluded/join_timeout upload is BLOCKED on this lane:
                // AutoLogUpload.OnConnectFailure does not exist here (C8).
                try { if (PhotonNetwork.InRoom) NetworkConnectionHandler.instance.NetworkRestart(); }
                catch (Exception ex) { Plugin.Log.LogWarning("[FFA-ASM] exit restart: " + ex.Message); }
                JoinTimeline.Disarm(why);
                ExitToast(why, lagMaster);
            }
            finally { _exiting = false; }
        }

        private static string LabelFor(string why)
        {
            if (why == "start_timeout") return "start_timeout";
            if (why == "join_timeout") return "join_timeout";
            if (why == "wrong_region") return "wrong_region";
            return "asm_exit";
        }

        /// <summary>The exit toast. Each text is a literal argument of the
        /// notification call, which translates it, so the i18n extractor
        /// harvests every one.</summary>
        private static void ExitToast(string why, bool lagMaster)
        {
            var c = new Color(1f, 0.7f, 0.3f);
            try
            {
                if (why == "dissolved")
                    CompetitiveUI.ShowNotificationCritical("This lobby closed before the match started. Nothing was counted.", c, 9f);
                else if (why == "start_timeout")
                    CompetitiveUI.ShowNotificationCritical("The match could not be confirmed with the server. Please queue again.", c, 9f);
                else if (why == "master_unkept" || why == "cfg_missing" || why == "wrong_region")
                    CompetitiveUI.ShowNotificationCritical("The match could not start. Please queue again.", c, 9f);
                else if (why == "fence_expired" && lagMaster)
                    CompetitiveUI.ShowNotificationCritical("The match could not continue on your connection. Please queue again.", c, 9f);
                else
                    CompetitiveUI.ShowNotificationCritical("You could not connect in time. No penalty. Queue again when ready.", c, 9f);
            }
            catch { }
        }

        private static string _releaseLobby;
        private static string _releaseWhy;
        private static int _releaseTries;
        private static bool _releaseInFlight;
        internal static string ReleaseRoom;

        /// <summary>Writer 8 (V11, N10): the client clears FfaLeaveQueue
        /// performs, the release intent, the POST (single-flight, 4 s), and the
        /// one-shot ReleaseRoom the room-exit hook consumes.</summary>
        internal static void Release(string why)
        {
            string lobby = !string.IsNullOrEmpty(RoomLobbyId) ? RoomLobbyId : (Lock != null ? Lock.Lobby : "");
            if (why == "join_timeout" && !string.IsNullOrEmpty(FfaLateEntry.AdmittedLateLobby))
                lobby = FfaLateEntry.AdmittedLateLobby;
            ApiClient.FfaClientClears();
            if (string.IsNullOrEmpty(lobby)) return;
            _releaseLobby = lobby;
            _releaseWhy = why;
            _releaseTries = 0;
            ReleaseRoom = lobby;
            SendRelease();
        }

        private static void SendRelease()
        {
            if (_releaseInFlight || string.IsNullOrEmpty(_releaseLobby)) return;
            string lobby = _releaseLobby, why = _releaseWhy;
            int tryNo = ++_releaseTries;
            _releaseInFlight = true;
            string json = "{\"steam_id\":\"" + Esc(SteamId()) + "\",\"why\":\"" + why + "\"}";
            ApiClient.AsmPost(ApiClient.BaseUrl + "/api/v1/ffa/lobby/" + lobby + "/release", json, (ok, resp) =>
            {
                _releaseInFlight = false;
                int code = ok ? 200 : ErrorCode(resp);
                string result = ok ? "ok" : (code == 404 ? "gone" : "fail");
                ReleaseLine(why, lobby, tryNo, result);
                if (ok || code == 404)
                {
                    _releaseLobby = null;
                    return;
                }
                if (tryNo >= 3)
                {
                    ReleaseLine(why, lobby, tryNo, "dropped");
                    _releaseLobby = null;
                    ApiClient.IsFfaQueuePolling = false;
                    return;
                }
                // A failed try is re-sent from the queue's recovery sites.
                ApiClient.IsFfaQueuePolling = true;
            }, timeout: PostTimeout);
        }

        private static void ReleaseLine(string why, string lobby, int tryNo, string result)
        {
            JoinTimeline.Step("release", "why=" + why + " lobby=" + JoinTimeline.Id8(lobby) + " try=" + I(tryNo) + " result=" + result);
        }

        /// <summary>The queue's recovery sites (the poll's lobby, ready_join and
        /// not_in_queue branches): while a release intent is pending, re-send
        /// it and tell the caller to return before any rejoin or leave.</summary>
        internal static bool ResendRelease()
        {
            if (string.IsNullOrEmpty(_releaseLobby)) return false;
            if (!_releaseInFlight) SendRelease();
            return true;
        }

        /// <summary>The room-exit hook's release consume (K50): once; true only
        /// when it names the lobby of the room being left.</summary>
        internal static bool ConsumeRelease(string room)
        {
            string r = ReleaseRoom;
            if (string.IsNullOrEmpty(r)) return false;
            ReleaseRoom = null;
            string lobby = room == ArrivedRoom ? RoomLobbyId : RoomOfLobby(r) == room ? r : null;
            if (string.IsNullOrEmpty(lobby) || lobby != r) return false;
            JoinTimeline.Step("release_handoff", "lobby=" + JoinTimeline.Id8(r) + " why=" + (_releaseWhy ?? "-"));
            return true;
        }

        // ------------------------------------------------------------ the notice (item 10)

        private static readonly HashSet<string> _noticeToasted = new HashSet<string>(StringComparer.Ordinal);

        /// <summary>The poll callback, after the !ok return and before both
        /// discards (K25).</summary>
        internal static void OnPollNotice(string resp)
        {
            string raw;
            try { raw = ExtractJsonRaw(Members(resp), "asm_notice"); } catch { return; }
            if (string.IsNullOrEmpty(raw)) return;
            var n = Members(raw);
            OnNotice(ExtractJsonString(n, "lobby_id") ?? "", ExtractJsonString(n, "outcome") ?? "");
        }

        internal static void OnNotice(string lobby, string outcome)
        {
            if (string.IsNullOrEmpty(lobby)) return;
            bool own = lobby == ApiClient.ActiveFfaLobbyId || lobby == ApiClient.OpenFfaLobbyId;
            JoinTimeline.Step("notice", "lobby=" + JoinTimeline.Id8(lobby) + " own=" + B(own) + " outcome=" + outcome);
            if (outcome == "started") NoteTrigger(RoomOfLobby(lobby), "notice");
            if (lobby == ApiClient.ActiveFfaLobbyId || lobby == ApiClient.OpenFfaLobbyId)
            {
                ApiClient.FfaClientClears();
                if (lobby == ApiClient.OpenFfaLobbyId) ApiClient.OpenFfaLobbyId = null;
            }
            if (_noticeToasted.Add(lobby))
            {
                var c = new Color(1f, 0.7f, 0.3f);
                try
                {
                    // Literal arguments: the notification translates them and
                    // the i18n extractor harvests them.
                    if (outcome == "dissolved")
                        CompetitiveUI.ShowNotification("This lobby closed before the match started. Nothing was counted.", c, 8f);
                    else
                        CompetitiveUI.ShowNotification("You could not connect in time. No penalty. Queue again when ready.", c, 8f);
                }
                catch { }
            }
            // I4's server_asked upload is BLOCKED on this lane (C8): the
            // AutoLogUpload.OnConnectFailure hook does not exist here.
            ReceiptFor(lobby, "notice_seen", null);
        }

        // ------------------------------------------------------------ the outer join deadline (item 11)

        internal static float JoinDeadlineRt;
        private static float _deadlineArmedRt;
        private static string _deadlineLobby;

        private static void ArmDeadline(float at, string lobby)
        {
            JoinDeadlineRt = at;
            _deadlineArmedRt = Time.realtimeSinceStartup;
            _deadlineLobby = lobby;
        }

        private static void JoinDeadlineTick()
        {
            if (JoinDeadlineRt <= 0f || Time.realtimeSinceStartup < JoinDeadlineRt) return;
            JoinDeadlineRt = 0f;
            int waited = (int)((Time.realtimeSinceStartup - _deadlineArmedRt) * 1000f);
            string st = "none";
            try { st = QueueRoomJoiner.Instance != null ? QueueRoomJoiner.Instance.StateName : "none"; } catch { }
            JoinTimeline.Step("join_timeout", "waited_ms=" + I(waited) + " state=" + st);
            Exit("join_timeout");
        }

        /// <summary>A leave or a release clears the lock's own timers and a
        /// re-form's pending pre-join properties.</summary>
        internal static void OnQueueCleared()
        {
            JoinDeadlineRt = 0f;
            StartHoldActive = false;
            DropHeld();
            ClearOwedToast();
            PrejoinAtJoin = false;
        }

        // ------------------------------------------------------------ the tick

        /// <summary>The first statement of QueueRoomJoiner.Update (K31): it runs
        /// in every joiner state, the Idle park included.</summary>
        internal static void Tick()
        {
            TickSeen = true;
            try { JoinDeadlineTick(); } catch (Exception ex) { Plugin.Log.LogWarning("[FFA-ASM] deadline: " + ex.Message); }
            try { OwedToastTick(); } catch { }
            try { LoadLeaseTick(); } catch { }
            try { CountHoldTick(); } catch { }
            try { CurrentGate(); } catch { }
            try { FfaLateEntry.Tick(); } catch (Exception ex) { Plugin.Log.LogWarning("[FFA-LATE] tick: " + ex.Message); }
        }

        /// <summary>FfaMode.OnRoomLeft: per-room state that must not outlive the
        /// room. The lock's config, the statements, the triggers and the grant
        /// set are the sitting's and stay.</summary>
        internal static void OnRoomLeft(string room)
        {
            StartHoldActive = false;
            DropHeld();
            _spawnOpenRoom = null;
            _spawnLateRoom = null;
            _spawnClosedRoom = null;
            SpawnRunning = false;
            _callinCensus.Clear();
            try { FfaLateEntry.OnRoomLeft(room); } catch { }
            _gateFrame = -1;
        }

        // ------------------------------------------------------------ top-level JSON

        /// <summary>The top-level members of one JSON object (string-aware,
        /// depth-aware: a nested key never satisfies a top-level read).</summary>
        internal static Dictionary<string, string> Members(string json)
        {
            Dictionary<string, string> m;
            if (!string.IsNullOrEmpty(json) && ApiClient.TryTopLevelMembersPublic(json.Trim(), out m)) return m;
            return new Dictionary<string, string>(StringComparer.Ordinal);
        }

        internal static string ExtractJsonRaw(Dictionary<string, string> m, string key)
        {
            string v;
            return m != null && m.TryGetValue(key, out v) ? v : null;
        }

        internal static bool ExtractJsonHas(Dictionary<string, string> m, string key)
        {
            return m != null && m.ContainsKey(key);
        }

        internal static int ExtractJsonInt(Dictionary<string, string> m, string key, int dflt)
        {
            string raw = ExtractJsonRaw(m, key);
            if (raw == null) return dflt;
            raw = raw.Trim();
            int v;
            if (int.TryParse(raw, NumberStyles.Integer, CultureInfo.InvariantCulture, out v)) return v;
            double d;
            if (double.TryParse(raw, NumberStyles.Float, CultureInfo.InvariantCulture, out d)) return (int)d;
            return dflt;
        }

        internal static string ExtractJsonString(Dictionary<string, string> m, string key)
        {
            string raw = ExtractJsonRaw(m, key);
            if (raw == null || raw.Length < 2 || raw[0] != '"' || raw[raw.Length - 1] != '"') return null;
            return Unescape(raw.Substring(1, raw.Length - 2));
        }

        private static string Unescape(string s)
        {
            if (s.IndexOf('\\') < 0) return s;
            var sb = new StringBuilder(s.Length);
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                if (c != '\\' || i + 1 >= s.Length)
                {
                    sb.Append(c);
                    continue;
                }
                char e = s[++i];
                switch (e)
                {
                    case 'n': sb.Append('\n'); break;
                    case 'r': sb.Append('\r'); break;
                    case 't': sb.Append('\t'); break;
                    case 'b': sb.Append('\b'); break;
                    case 'f': sb.Append('\f'); break;
                    case 'u':
                        if (i + 4 < s.Length && int.TryParse(s.Substring(i + 1, 4), NumberStyles.HexNumber,
                                                             CultureInfo.InvariantCulture, out int cp))
                        {
                            sb.Append((char)cp);
                            i += 4;
                        }
                        break;
                    default: sb.Append(e); break;
                }
            }
            return sb.ToString();
        }

        /// <summary>The objects of a JSON array's raw text, in order.</summary>
        internal static List<string> JsonObjects(string arrayRaw)
        {
            var list = new List<string>();
            if (string.IsNullOrEmpty(arrayRaw)) return list;
            string s = arrayRaw.Trim();
            if (s.Length < 2 || s[0] != '[') return list;
            int i = 1;
            while (i < s.Length)
            {
                char c = s[i];
                if (c == '{')
                {
                    int end = ApiClient.FindMatchingBraceStringAwarePublic(s, i);
                    if (end < 0) break;
                    list.Add(s.Substring(i, end - i + 1));
                    i = end + 1;
                    continue;
                }
                if (c == ']') break;
                i++;
            }
            return list;
        }

        /// <summary>The integers of a JSON array's raw text.</summary>
        internal static List<int> JsonInts(string arrayRaw)
        {
            var list = new List<int>();
            if (string.IsNullOrEmpty(arrayRaw)) return list;
            string s = arrayRaw.Trim().TrimStart('[').TrimEnd(']');
            foreach (var part in s.Split(','))
            {
                int v;
                if (int.TryParse(part.Trim(), NumberStyles.Integer, CultureInfo.InvariantCulture, out v)) list.Add(v);
            }
            return list;
        }
    }

    /// <summary>The load gate (item 9): beside Spectator_MapLoadGate_Patch;
    /// each decides only for its own kind of seat (HarmonyX runs every sibling
    /// prefix).</summary>
    [HarmonyPatch(typeof(MapManager), "RPCA_LoadLevel")]
    internal static class FfaAssembly_LoadGate_Patch
    {
        [HarmonyPriority(Priority.First)]
        private static bool Prefix(string sceneName)
        {
            try { return FfaAssembly.LoadGate(sceneName); }
            catch { return true; }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(System.Reflection.MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            if (exception == null) FfaAssembly.LoadGateAttached = true;
            return exception;
        }
    }
}
