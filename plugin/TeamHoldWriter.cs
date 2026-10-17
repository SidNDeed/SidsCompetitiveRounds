using System;
using System.Collections.Generic;
using System.Globalization;
using ExitGames.Client.Photon;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Stage 2 room-key writers (master only). S1 step 3: the game id G, minted
    /// by the server per physical game and published as cr_tgid = {G}:s at the
    /// start, {G}:g at the game-over edge, by Photon compare-and-set. Until
    /// cr_tgid names a started G no hold can open (toward today).
    /// </summary>
    internal static class TeamHoldWriter
    {
        internal static string CurrentRoom()
        {
            try { return PhotonNetwork.InRoom && PhotonNetwork.CurrentRoom != null ? PhotonNetwork.CurrentRoom.Name : null; }
            catch { return null; }
        }

        internal static string RoomProp(string key)
        {
            try
            {
                var props = PhotonNetwork.CurrentRoom != null ? PhotonNetwork.CurrentRoom.CustomProperties : null;
                object v;
                return props != null && props.TryGetValue(key, out v) && v != null ? v.ToString() : null;
            }
            catch { return null; }
        }

        internal static string PlayerProp(Photon.Realtime.Player p, string key)
        {
            try
            {
                object v;
                return p != null && p.CustomProperties != null && p.CustomProperties.TryGetValue(key, out v) && v != null ? v.ToString() : null;
            }
            catch { return null; }
        }

        /// <summary>Photon compare-and-set of one room key: applied only when
        /// the server still holds <paramref name="expected"/>.</summary>
        internal static bool CasRoomProp(string key, string value, string expected)
        {
            return CasRoomProps(new Hashtable { { key, value } }, key, expected);
        }

        /// <summary>One Photon call setting every key of <paramref name="set"/>,
        /// applied only when <paramref name="expectKey"/> still holds
        /// <paramref name="expected"/> (no expectation when either is null).</summary>
        internal static bool CasRoomProps(Hashtable set, string expectKey, string expected)
        {
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.CurrentRoom == null) return false;
                var exp = expectKey != null && expected != null ? new Hashtable { { expectKey, expected } } : null;
                return PhotonNetwork.CurrentRoom.SetCustomProperties(set, exp);
            }
            catch { return false; }
        }

        /// <summary>S1 step 3, at GM_ArmsRace.DoStartGame in a flagged room:
        /// the master posts the start with the previous G of this room (or
        /// none) and publishes the answer. A promoted master re-posting the
        /// same previous G receives the same G, so a handover never forks a
        /// game. No answer (an unbound transport included): no G, no hold.</summary>
        internal static void OnGameStart()
        {
            try
            {
                string room = CurrentRoom();
                if (!TeamHoldRules.Flagged(room) || !PhotonNetwork.IsMasterClient) return;
                var pin = TeamHoldRules.PinFor(room);
                string old = RoomProp(TeamHoldRules.KEY_TGID);
                string prev = null;
                if (!string.IsNullOrEmpty(old))
                {
                    int i = old.LastIndexOf(':');
                    prev = i > 0 ? old.Substring(0, i) : null;
                }
                TeamHoldNet.Call("POST", TeamHoldNet.PathGameStart, TeamHoldNet.GameStartBody(pin.Mode, pin.SeriesId, room, prev), (st, body) =>
                {
                    try
                    {
                        string g;
                        if (!TeamHoldNet.TryParseGameStart(st, body, out g))
                        {
                            Plugin.Log.LogInfo("[HOLD] game id unavailable (status " + st.ToString(CultureInfo.InvariantCulture)
                                + "): no hold can open this game");
                            return;
                        }
                        if (!string.Equals(CurrentRoom(), room, StringComparison.Ordinal)) return;
                        // The game's keys start clean: cr_trd is cleared only
                        // here (S2 room keys), in the call that names the game.
                        var set = new Hashtable { { TeamHoldRules.KEY_TGID, TeamHoldRules.GidValue(g, true) }, { TeamHoldRules.KEY_TRD, "" } };
                        bool ok = CasRoomProps(set, TeamHoldRules.KEY_TGID, old);
                        Plugin.Log.LogInfo("[HOLD] game id " + g + (ok ? " published" : " not published (the key moved)"));
                    }
                    catch { }
                });
            }
            catch { }
        }

        /// <summary>The game-over edge: {G}:s becomes {G}:g.</summary>
        internal static void OnGameOver()
        {
            try
            {
                string room = CurrentRoom();
                if (!TeamHoldRules.Flagged(room) || !PhotonNetwork.IsMasterClient) return;
                string old = RoomProp(TeamHoldRules.KEY_TGID);
                string g;
                if (!TeamHoldRules.GidStarted(old, out g)) return;
                CasRoomProp(TeamHoldRules.KEY_TGID, TeamHoldRules.GidValue(g, false), old);
            }
            catch { }
        }
    }

    /// <summary>
    /// Stage 2 S1 on every client: the classifier read, the drop cut, the
    /// departure claim and the point in flight. Inert in every room the pin
    /// store does not flag, which at this lane tip is every room.
    /// </summary>
    internal static class TeamHold
    {
        internal const string TAG = "[HOLD]";

        private static TeamHoldRules.DropCut _cut;
        private static float _leaveAt;
        private static bool _purged, _resolved;
        /// <summary>Actors whose departure this client held (the first drop
        /// and any second departure). The cascade prefix reads it too, so a
        /// held departure is suppressed whichever of the prefix and the leave
        /// callback runs first, even after the hold ended.</summary>
        private static readonly HashSet<int> _held = new HashSet<int>();

        /// <summary>The state at the last boundary this client passed (S3
        /// step 7): the scoreboard and every slot's deck at that point start.</summary>
        private static int _bR0, _bR1, _bP0, _bP1;
        private static readonly Dictionary<int, List<string>> _bNames = new Dictionary<int, List<string>>();

        /// <summary>At every point start (the boundary just passed): the
        /// scoreboard and every slot's deck; this seat's own checkpoint goes
        /// out in its next beat at once.</summary>
        internal static void NoteBoundary()
        {
            var gm = GM_ArmsRace.instance;
            if (gm == null) return;
            _bR0 = gm.p1Rounds; _bR1 = gm.p2Rounds; _bP0 = gm.p1Points; _bP1 = gm.p2Points;
            _bNames.Clear();
            foreach (var slot in new List<int>(SeatDeckLog.Slots()))
            {
                SeatDeckLog.Seat s;
                if (SeatDeckLog.TryGetSeat(slot, out s)) _bNames[slot] = new List<string>(s.Names);
            }
            int mine = TeamHoldRules.ParseInt(TeamHoldWriter.PlayerProp(PhotonNetwork.LocalPlayer, Player.VAR_PLAYERID), -1);
            List<string> own;
            _bNames.TryGetValue(mine, out own);
            TeamHoldLoop.NoteBoundary(TeamHoldRules.BoundaryDigest(_bR0, _bR1, _bP0, _bP1, own ?? new List<string>()));
        }

        /// <summary>The drop this client holds for, or null.</summary>
        internal static TeamHoldRules.DropCut Cut { get { return _cut; } }

        private static int SlotOf(Photon.Realtime.Player p)
        {
            string s = TeamHoldWriter.PlayerProp(p, Player.VAR_PLAYERID);
            int slot = TeamHoldRules.ParseInt(s, -1);
            if (slot < 0 && p != null) slot = TeamHoldGlue.SlotOfActor(p.ActorNumber);
            return slot;
        }

        /// <summary>The classifier's inputs, from replicated keys and the pin
        /// only (V3 S1 step 5).</summary>
        private static TeamHoldRules.GateInputs Read(Photon.Realtime.Player p)
        {
            string room = TeamHoldWriter.CurrentRoom();
            int slot = SlotOf(p);
            return new TeamHoldRules.GateInputs
            {
                Pin = TeamHoldRules.PinFor(room),
                IsSpec = RoomActors.IsSpectatorReplicated(p),
                Uid = TeamHoldWriter.PlayerProp(p, "u_id"),
                Slot = slot,
                Tgid = TeamHoldWriter.RoomProp(TeamHoldRules.KEY_TGID),
                Trd = TeamHoldWriter.RoomProp(TeamHoldRules.KEY_TRD),
                Th = TeamHoldWriter.RoomProp(TeamHoldRules.KEY_TH),
                VLeave = TeamHoldWriter.PlayerProp(p, TeamHoldRules.KEY_VLEAVE) == "1",
                SlotMarked = SeatDeckLog.Marked(slot),
                RoomName = room,
            };
        }

        /// <summary>The memoised classification of a departure (S1 step 5),
        /// shared by the cascade prefix and the mod leave callback. Any
        /// exception answers today.</summary>
        internal static bool Classify(Photon.Realtime.Player p)
        {
            if (p == null) return false;
            try
            {
                if (!TeamHoldRules.Flagged(TeamHoldWriter.CurrentRoom())) return false;
                return TeamHoldRules.HoldGate.DecideOnce(p.ActorNumber, () => Read(p));
            }
            catch { return false; }
        }

        private static void SeriesTally(string mode, out int w0, out int w1)
        {
            w0 = w1 = 0;
            if (mode == TeamHoldRules.MODE_OVT) { w0 = GameStateWatcher.OvtSoloWins; w1 = GameStateWatcher.OvtDuoWins; return; }
            int myTeam = TeamHoldRules.ParseInt(TeamHoldWriter.PlayerProp(PhotonNetwork.LocalPlayer, Player.VAR_TEAMID), -1);
            int won = GameStateWatcher.CurrentSeriesGamesWon, lost = GameStateWatcher.CurrentSeriesGamesLost;
            if (myTeam == 0) { w0 = won; w1 = lost; } else if (myTeam == 1) { w0 = lost; w1 = won; }
        }

        /// <summary>The mod leave callback, before its DC block. True when the
        /// departure is held: the callback then skips the election and report
        /// of today (S1 step 9), whose inputs <paramref name="buildPlan"/>
        /// latched into the cut. A fighter departure while a hold waits is the
        /// second departure: it is held too (its own DC path would run after a
        /// cascade today never reaches) and ends the first hold.</summary>
        internal static bool OnLeave(Photon.Realtime.Player p, Func<TeamHoldRules.DropCut, object> buildPlan)
        {
            try
            {
                if (p == null) return false;
                if (_held.Contains(p.ActorNumber)) return true;
                if (_cut != null)
                {
                    if (!HoldsAnother(p)) return false;
                    _held.Add(p.ActorNumber);
                    OnSecondDeparture(p);
                    return true;
                }
                if (!Classify(p)) return false;
                _held.Add(p.ActorNumber);
                // The cascade prefix suppresses on the same memo, so from here
                // the departure is held whatever fails below: the cut is
                // latched first and filled field by field.
                var cut = new TeamHoldRules.DropCut { Actor = p.ActorNumber, At = Time.unscaledTime, Leaver = p };
                _cut = cut;
                _leaveAt = Time.unscaledTime;
                _purged = _resolved = false;
                try { Fill(cut, p, buildPlan); }
                catch (Exception ex) { Plugin.Log.LogWarning(TAG + " cut incomplete: " + ex.Message); }
                Plugin.Log.LogInfo(TAG + " cascade suppressed slot=" + cut.Slot.ToString(CultureInfo.InvariantCulture)
                    + " team=" + cut.Team.ToString(CultureInfo.InvariantCulture) + " g=" + (cut.G ?? "")
                    + " eligibility=" + cut.Eligibility);
                try { TeamHoldLoop.OnDrop(cut); } catch { }
                return true;
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning(TAG + " leave error: " + ex.Message);
                return false;
            }
        }

        /// <summary>A fighter other than the held one leaving while a hold
        /// waits (S1 step 6): its cascade and DC path do not run; it ends the
        /// hold into the expiry of the first drop, which runs the outcome of
        /// today once.</summary>
        internal static bool HoldsAnother(Photon.Realtime.Player p)
        {
            if (p != null && _held.Contains(p.ActorNumber)) return true;
            var c = _cut;
            return c != null && p != null && p.ActorNumber != c.Actor && !RoomActors.IsSpectatorReplicated(p)
                   && string.Equals(TeamHoldWriter.CurrentRoom(), c.Room, StringComparison.Ordinal);
        }

        /// <summary>The drop cut (S1 step 7): every input the outcome of today
        /// reads, in the leave frame, before the body goes.</summary>
        private static void Fill(TeamHoldRules.DropCut cut, Photon.Realtime.Player p, Func<TeamHoldRules.DropCut, object> buildPlan)
        {
            string room = TeamHoldWriter.CurrentRoom();
            var pin = TeamHoldRules.PinFor(room);
            cut.Room = room;
            cut.Mode = pin != null ? pin.Mode : null;
            cut.SeriesId = pin != null ? pin.SeriesId : null;
            string g;
            TeamHoldRules.GidStarted(TeamHoldWriter.RoomProp(TeamHoldRules.KEY_TGID), out g);
            cut.G = g;
            int slot = SlotOf(p);
            cut.Slot = slot;
            cut.Team = TeamHoldRules.SlotToTeam(cut.Mode, slot);
            cut.LeaverUid = TeamHoldWriter.PlayerProp(p, "u_id");
            cut.Name = p.NickName;
            var gm = GM_ArmsRace.instance;
            if (gm != null) { cut.R0 = gm.p1Rounds; cut.R1 = gm.p2Rounds; cut.P0 = gm.p1Points; cut.P1 = gm.p2Points; }
            cut.SlotLog = SeatDeckLog.Describe(slot);
            cut.LastP1 = GameStateWatcher.LastP1Points;
            cut.LastP2 = GameStateWatcher.LastP2Points;
            cut.BR0 = _bR0; cut.BR1 = _bR1; cut.BP0 = _bP0; cut.BP1 = _bP1;
            List<string> bn;
            if (_bNames.TryGetValue(slot, out bn)) cut.BNames.AddRange(bn);
            int w0, w1;
            SeriesTally(cut.Mode, out w0, out w1);
            cut.W0 = w0; cut.W1 = w1;
            // S1 step 8, before the purge: the departure claim of the S0
            // ledger. A won claim is a death, recorded as today records one.
            if (SeatDeckLog.ClaimDeparture(slot, TeamHoldGlue.CurrentTuple()) == SeatDeckLog.Claim.Won)
                GameStateWatcher.RecordDeathObserved(false, 0);
            if (cut.Mode == TeamHoldRules.MODE_TEAM && buildPlan != null)
            {
                try { cut.Plan = buildPlan(cut); }
                catch (Exception ex) { Plugin.Log.LogWarning(TAG + " cut plan error: " + ex.Message); }
            }
        }

        /// <summary>A second fighter departure while a hold waits ends it (S1
        /// step 6, S2 release).</summary>
        private static void OnSecondDeparture(Photon.Realtime.Player p)
        {
            Plugin.Log.LogInfo(TAG + " second departure actor=" + (p != null ? p.ActorNumber.ToString(CultureInfo.InvariantCulture) : "?"));
            try { TeamHoldLoop.EndLocal(Time.unscaledTime, null, "second_departure"); } catch { }
        }

        /// <summary>The hold ended toward today on this client (S2 release:
        /// a verified x, a refusal, no answer, a second departure, a local
        /// ceiling, a survivor leave). Nothing of the hold remains here.</summary>
        internal static void Expire(string reason)
        {
            var cut = _cut;
            if (cut == null) return;
            _cut = null;
            TeamHoldLoop.NoteEnded(cut, reason == "second_departure");
            Plugin.Log.LogInfo(TAG + " ended reason=" + (reason ?? "") + " slot=" + cut.Slot.ToString(CultureInfo.InvariantCulture)
                + " g=" + (cut.G ?? ""));
            // S5: the path of today, once, with the cut as input.
            try { TeamHoldExpiry.Run(cut, reason); } catch (Exception ex) { Plugin.Log.LogWarning(TAG + " expiry: " + ex.Message); }
        }

        /// <summary>A verified e: the returner is in play; nothing of the
        /// drop runs.</summary>
        internal static void Released() { _cut = null; }

        /// <summary>The hold state this client observes for the cut's drop.</summary>
        internal static char ObservedState()
        {
            if (_cut == null) return '\0';
            TeamHoldRules.HoldKey k;
            if (!TeamHoldRules.TryParseHold(TeamHoldWriter.RoomProp(TeamHoldRules.KEY_TH), out k)) return '\0';
            return k.Slot == _cut.Slot && k.G == _cut.G ? k.State : '\0';
        }

        /// <summary>Per frame. The point in flight (S1 step 8): at leave plus
        /// 0.7 s and after an observed p, o or x for this drop, every client
        /// purges the departed entries; then over the purged list a point in
        /// battle with fewer than two teams alive resolves through the master
        /// arm of vanilla PlayerDied.</summary>
        internal static void Tick()
        {
            if (_cut == null || _resolved) return;
            if (!string.Equals(TeamHoldWriter.CurrentRoom(), _cut.Room, StringComparison.Ordinal)) return;
            double since = Time.unscaledTime - _leaveAt;
            char observed = ObservedState();
            if (since < TeamHoldRules.PurgeDelay || (observed != 'p' && observed != 'o' && observed != 'x')) return;
            if (!_purged)
            {
                _purged = true;
                try { FfaMode.PurgeDepartedPlayers("hold"); } catch (Exception ex) { Plugin.Log.LogWarning(TAG + " purge: " + ex.Message); }
            }
            var pm = PlayerManager.instance;
            var gm = GM_ArmsRace.instance;
            bool battle = GameManager.instance != null && GameManager.instance.battleOngoing;
            int alive = pm != null ? pm.TeamsAlive() : 2;
            var a = TeamHoldRules.PointAfterLeave(since, observed, battle, alive);
            _resolved = true;
            if (a != TeamHoldRules.Resolve.NextRound || pm == null || gm == null) return;
            // The master arm of vanilla PlayerDied, statement for statement;
            // PlayerDied itself is never called (its first statement reads
            // the departed body). Every client slows down; the master sends.
            try { TimeHandler.instance.DoSlowDown(); } catch { }
            if (PhotonNetwork.IsMasterClient)
            {
                int losing, winning;
                TeamHoldRules.MasterArm(pm.GetLastTeamAlive(), out losing, out winning);
                gm.view.RPC("RPCA_NextRound", RpcTarget.All, losing, winning, gm.p1Points, gm.p2Points, gm.p1Rounds, gm.p2Rounds);
                Plugin.Log.LogInfo(TAG + " point resolved for the leaver's loss: team " + winning.ToString(CultureInfo.InvariantCulture) + " takes it");
            }
        }

        /// <summary>Room left: nothing of the room survives.</summary>
        internal static void OnRoomLeft()
        {
            _cut = null;
            _purged = _resolved = false;
            _held.Clear();
            _bNames.Clear();
            _bR0 = _bR1 = _bP0 = _bP1 = 0;
            TeamHoldRules.HoldGate.Clear();
        }
    }

    /// <summary>
    /// Stage 2 S2 on every client of a flagged room: the presence beat, the
    /// master writer, the transition envelope, the local ceilings and the
    /// release. Every answer the server does not give (an unbound transport,
    /// a 404, a refusal) ends toward today; the ceilings bound every wait.
    /// </summary>
    internal static class TeamHoldLoop
    {
        internal const double BeatS = 10, VerifyS = 2;

        private static TeamHoldRules.Writer _writer;
        private static bool _wasMaster;
        private static double _lastBeat = -1000, _lastVerify = -1000;
        /// <summary>This client's own last answered state read, issued after
        /// it observed the current cr_th value (generation <see cref="_readGen"/>);
        /// null while none has answered.</summary>
        private static TeamHoldNet.StateAnswer _server;
        private static int _readGen;
        private static string _obsTh;
        private static TeamHoldRules.Ceilings _ceil = new TeamHoldRules.Ceilings();
        private static string _room;
        private static TeamHoldRules.DropCut _endingCut;
        /// <summary>The cr_th value this master last sent. A compare-and-set
        /// applies on the server before the local cache shows it, so the next
        /// write expects what was sent, not the cache.</summary>
        private static string _thSent;
        /// <summary>Holds this client has ended or released ("{G}:{slot}"): a
        /// cr_th still naming one of them no longer fences this client.</summary>
        private static readonly HashSet<string> _ended = new HashSet<string>(StringComparer.Ordinal);

        /// <summary>The boundary checkpoint this seat posts in every beat
        /// (S3 step 7); empty until a boundary has been recorded.</summary>
        internal static string LastBoundaryDigest = "";

        /// <summary>A boundary passed: the new checkpoint goes out in the next
        /// frame's beat rather than up to a beat period later.</summary>
        internal static void NoteBoundary(string d)
        {
            LastBoundaryDigest = d ?? "";
            _lastBeat = -1000;
        }

        /// <summary>The survivor's replay of the returner's deck ran for this
        /// hold (once per hold, S3 step 8).</summary>
        private static bool _survivorReplayed;

        /// <summary>Once per hold, when the returner's new body (owned by the
        /// bound actor, at the held slot) exists: replay that slot's deck from
        /// this client's own record. The departed body never qualifies: its
        /// owner is the departed actor, never the bound one.</summary>
        private static void SurvivorReplay(TeamHoldRules.DropCut cut, TeamHoldRules.HoldKey k)
        {
            if (_survivorReplayed || cut == null || k == null || k.BoundActor <= 0) return;
            var pm = PlayerManager.instance;
            if (pm == null) return;
            foreach (var body in pm.players)
            {
                if (body == null || body.PlayerID != cut.Slot) continue;
                int owner = -1;
                try { owner = body.data != null && body.data.view != null ? body.data.view.OwnerActorNr : -1; } catch { }
                if (owner != k.BoundActor) continue;
                _survivorReplayed = true;
                TeamHoldReturn.Replay(false, cut.Slot);
                return;
            }
        }

        /// <summary>What the banner shows: the last verified state of the
        /// held seat, or '\0'.</summary>
        internal static char Shown { get; private set; }
        internal static double DeadlineAt { get; private set; }
        internal static string EndedName { get; private set; }
        internal static bool EndedBySecond { get; private set; }
        internal static double EndedAt { get; private set; } = -1000;

        private static double Now { get { return Time.unscaledTime; } }

        private static void ForgetRead()
        {
            _server = null;
            _readGen++;
            _obsTh = null;
            _lastVerify = -1000;
        }

        /// <summary>A new drop: the pending ceiling runs from the drop, so a
        /// client that never sees p (it was overwritten at once) still ends.</summary>
        internal static void OnDrop(TeamHoldRules.DropCut cut)
        {
            _ceil = new TeamHoldRules.Ceilings();
            _ceil.SawP(cut.At);
            ForgetRead();
            _writer = null;
            _endingCut = null;
            _survivorReplayed = false;
            Shown = 'p';
            DeadlineAt = 0;
        }

        internal static void Reset()
        {
            _writer = null;
            ForgetRead();
            _ceil = new TeamHoldRules.Ceilings();
            _wasMaster = false;
            Shown = '\0';
            _room = null;
            _endingCut = null;
            _thSent = null;
            _ended.Clear();
        }

        private static string HoldName(string g, int slot) { return (g ?? "") + ":" + slot.ToString(CultureInfo.InvariantCulture); }

        /// <summary>The fence (RJS-M4): a boundary waits while this client
        /// still holds a drop it has neither released nor expired, or while
        /// cr_th names a waiting state of a hold this client has not ended.
        /// A held drop ends at a ceiling, and an ended hold never fences this
        /// client again whatever cr_th still says.</summary>
        internal static bool FenceHolds()
        {
            string room = TeamHoldWriter.CurrentRoom();
            if (!TeamHoldRules.Flagged(room)) return false;
            if (TeamHold.Cut != null) return true;
            string th = TeamHoldWriter.RoomProp(TeamHoldRules.KEY_TH);
            if (!TeamHoldRules.FenceWaits(th)) return false;
            TeamHoldRules.HoldKey k;
            return !(TeamHoldRules.TryParseHold(th, out k) && _ended.Contains(HoldName(k.G, k.Slot)));
        }

        internal static void Tick()
        {
            string room = TeamHoldWriter.CurrentRoom();
            if (!TeamHoldRules.Flagged(room)) return;
            if (!string.Equals(room, _room, StringComparison.Ordinal)) { Reset(); _room = room; }
            double now = Now;
            Beat(now, room);
            var cut = TeamHold.Cut;
            // An expired drop's writer still finishes its end: post, wait up
            // to 3 s, write x (writer step 6).
            if (_writer != null && _endingCut != null && _endingCut != cut && PhotonNetwork.IsMasterClient
                && _writer.P == TeamHoldRules.Writer.Phase.Ending)
            {
                try { Perform(_writer.Tick(now), _endingCut); } catch { }
            }
            if (cut == null) { _wasMaster = PhotonNetwork.IsMasterClient; return; }

            bool master = PhotonNetwork.IsMasterClient;
            if (!master) _thSent = null;
            if (master)
            {
                try { RunWriter(now, cut, !_wasMaster); }
                catch (Exception ex) { Plugin.Log.LogWarning(TeamHold.TAG + " writer error: " + ex.Message); EndLocal(now, null, "writer_error"); return; }
            }
            _wasMaster = master;

            string thRaw = TeamHoldWriter.RoomProp(TeamHoldRules.KEY_TH);
            TeamHoldRules.HoldKey k;
            bool have = TeamHoldRules.TryParseHold(thRaw, out k) && k.Slot == cut.Slot && k.G == cut.G;
            if (have)
            {
                // A new room value: only a read issued after this observation
                // may verify or refute it.
                if (!string.Equals(thRaw, _obsTh, StringComparison.Ordinal)) { ForgetRead(); _obsTh = thRaw; }
                if (k.State == 'p') _ceil.SawP(now);
                else if (!string.IsNullOrEmpty(k.HoldId)) VerifyRead(now, k.HoldId);
                var v = TeamHoldRules.Verify(k, _server);
                if (v == TeamHoldRules.Verdict.End) { EndLocal(now, k, "unverified_" + k.State); return; }
                if (v == TeamHoldRules.Verdict.Act)
                {
                    switch (k.State)
                    {
                        case 'o':
                            _ceil.SawO(now, k.HoldS);
                            if (DeadlineAt <= 0 && _server != null) DeadlineAt = now + _server.DeadlineS;
                            break;
                        case 'c':
                            _ceil.SawC(now);
                            break;
                        case 'b':
                            _ceil.SawC(now);
                            // S3 steps 4, 7 and 8: the hand-over over this
                            // client's own verified read.
                            try { TeamHoldReturn.OnVerifiedBound(cut, k, _server); } catch (Exception ex) { Plugin.Log.LogWarning(TeamHold.TAG + " hand-over: " + ex.Message); }
                            try { SurvivorReplay(cut, k); } catch { }
                            break;
                        case 'e':
                            Release(cut);
                            return;
                        case 'x':
                            TeamHold.Expire(_server != null && !string.IsNullOrEmpty(_server.ClosedReason) ? _server.ClosedReason : "closed");
                            return;
                    }
                    Shown = k.State;
                }
            }
            if (_ceil.Passed(now)) EndLocal(now, have ? k : null, "ceiling");
        }

        /// <summary>Every local end reason (writer step 6): this client's own
        /// end post when the hold has an id, the master's x through its
        /// writer, then the expiry on this client.</summary>
        internal static void EndLocal(double now, TeamHoldRules.HoldKey k, string reason)
        {
            var cut = TeamHold.Cut;
            if (cut == null) return;
            string holdId = k != null ? k.HoldId : (_writer != null && _writer.Key != null ? _writer.Key.HoldId : null);
            if (PhotonNetwork.IsMasterClient && _writer != null)
            {
                _endingCut = cut;
                try { Perform(_writer.End(now, reason), cut); } catch { }
            }
            else if (!string.IsNullOrEmpty(holdId))
            {
                TeamHoldNet.Call("POST", TeamHoldNet.PathEnd(holdId), TeamHoldNet.EndBody(reason), (st, body) => { });
            }
            TeamHold.Expire(reason);
        }

        /// <summary>A verified e: the boundary proceeds with the returner in play.</summary>
        private static void Release(TeamHoldRules.DropCut cut)
        {
            Shown = 'e';
            EndedName = cut.Name;
            EndedAt = Now;
            Plugin.Log.LogInfo(TeamHold.TAG + " entered slot=" + cut.Slot.ToString(CultureInfo.InvariantCulture) + " g=" + (cut.G ?? ""));
            _ended.Add(HoldName(cut.G, cut.Slot));
            TeamHold.Released();
        }

        internal static void NoteEnded(TeamHoldRules.DropCut cut, bool second)
        {
            Shown = 'x';
            EndedName = cut != null ? cut.Name : null;
            EndedBySecond = second;
            EndedAt = Now;
            if (cut != null) _ended.Add(HoldName(cut.G, cut.Slot));
        }

        /// <summary>This client's own state read (the envelope). An answer
        /// belongs to the room value observed when it was issued; one that
        /// arrives after the value changed is dropped. An answer with nothing
        /// parsable is kept as an empty answer, which verifies nothing.</summary>
        private static void VerifyRead(double now, string holdId)
        {
            if (now - _lastVerify < VerifyS) return;
            _lastVerify = now;
            int gen = _readGen;
            TeamHoldNet.Call("GET", TeamHoldNet.PathState(holdId), null, (st, body) =>
            {
                if (gen != _readGen) return;
                TeamHoldNet.StateAnswer a;
                _server = TeamHoldNet.TryParseState(st, body, out a) ? a : new TeamHoldNet.StateAnswer();
            });
        }

        private static void Beat(double now, string room)
        {
            if (now - _lastBeat < BeatS) return;
            _lastBeat = now;
            try
            {
                if (RoomActors.LocalIsSpectator || PhotonNetwork.LocalPlayer == null) return;
                var seen = new List<KeyValuePair<int, string>>();
                foreach (var a in PhotonNetwork.PlayerList)
                {
                    if (a == null || RoomActors.IsSpectatorReplicated(a)) continue;
                    seen.Add(new KeyValuePair<int, string>(a.ActorNumber, TeamHoldWriter.PlayerProp(a, "u_id") ?? ""));
                }
                TeamHoldNet.Call("POST", TeamHoldNet.PathBeat,
                    TeamHoldNet.BeatBody(room, PhotonNetwork.LocalPlayer.ActorNumber, seen, LastBoundaryDigest), (st, body) => { });
            }
            catch { }
        }

        // ── The master writer's glue (S2 writer steps 1 to 6) ──────────────

        private static void RunWriter(double now, TeamHoldRules.DropCut cut, bool promoted)
        {
            if (_writer == null) _writer = new TeamHoldRules.Writer();
            var acts = new List<TeamHoldRules.Writer.Action>();
            if (_writer.P == TeamHoldRules.Writer.Phase.Idle)
            {
                TeamHoldRules.HoldKey cur;
                bool have = TeamHoldRules.TryParseHold(TeamHoldWriter.RoomProp(TeamHoldRules.KEY_TH), out cur)
                            && cur.Slot == cut.Slot && cur.G == cut.G;
                string req = Guid.NewGuid().ToString("N");
                if (!have) acts.AddRange(_writer.OnDrop(now, cut.Slot, cut.Team, cut.G, PhotonNetwork.LocalPlayer.ActorNumber, req));
                else if (TeamHoldRules.IsLive(cur.State)) acts.AddRange(_writer.OnPromoted(now, cur, req));
                else { _writer.P = TeamHoldRules.Writer.Phase.Done; return; }
            }
            acts.AddRange(_writer.Tick(now));
            Perform(acts, cut);
            // A writer that ended for its own reason (a refusal, no answer,
            // no signer) wrote x without a hold id, which no client can
            // verify; this client expires at once rather than at its ceiling.
            var w = _writer;
            if (w != null && w.P == TeamHoldRules.Writer.Phase.Done && w.EndReason != null && TeamHold.Cut == cut)
                TeamHold.Expire(w.EndReason);
        }

        private static void Perform(List<TeamHoldRules.Writer.Action> acts, TeamHoldRules.DropCut cut)
        {
            if (acts == null) return;
            for (int i = 0; i < acts.Count; i++)
            {
                var a = acts[i];
                switch (a.Op)
                {
                    case TeamHoldRules.Writer.Op.WriteTh:
                    {
                        string old = _thSent ?? TeamHoldWriter.RoomProp(TeamHoldRules.KEY_TH);
                        string val = a.Key.Format();
                        var set = new Hashtable { { TeamHoldRules.KEY_TH, val } };
                        // cr_trd rides the same call as the transition it records.
                        if (i + 1 < acts.Count && acts[i + 1].Op == TeamHoldRules.Writer.Op.AppendTrd)
                        {
                            var t = acts[++i];
                            set[TeamHoldRules.KEY_TRD] = TeamHoldRules.TrdAppend(TeamHoldWriter.RoomProp(TeamHoldRules.KEY_TRD), t.Key.G, t.Key.Slot, t.TrdKind);
                        }
                        if (TeamHoldWriter.CasRoomProps(set, TeamHoldRules.KEY_TH, old)) _thSent = val;
                        break;
                    }
                    case TeamHoldRules.Writer.Op.AppendTrd:
                        TeamHoldWriter.CasRoomProps(new Hashtable { { TeamHoldRules.KEY_TRD,
                            TeamHoldRules.TrdAppend(TeamHoldWriter.RoomProp(TeamHoldRules.KEY_TRD), a.Key.G, a.Key.Slot, a.TrdKind) } }, null, null);
                        break;
                    case TeamHoldRules.Writer.Op.PostOpen:
                    {
                        string me = MatchTracker.LocalSteamId;
                        string sig = TeamHoldNet.SignOrNull(TeamHoldNet.HoldOpenCanonical(cut.Mode, cut.Room, cut.G, cut.LeaverUid, cut.Slot, cut.Team, me));
                        var w = _writer;
                        if (sig == null)
                        {
                            // No signer bound: the open is not sent (toward today).
                            Perform(w.OnOpen(Now, TeamHoldNet.NoTransport, null), cut);
                            break;
                        }
                        string body = TeamHoldNet.OpenBody(w.RequestId, cut.Mode, cut.Room, cut.G, cut.LeaverUid, cut.Slot, cut.Team, me, sig);
                        TeamHoldNet.Call("POST", TeamHoldNet.PathOpen, body, (st, rb) =>
                        {
                            TeamHoldNet.OpenAnswer oa;
                            TeamHoldNet.TryParseOpen(st, rb, out oa);
                            if (w == _writer && TeamHold.Cut == cut) Perform(w.OnOpen(Now, st, oa), cut);
                        });
                        break;
                    }
                    case TeamHoldRules.Writer.Op.GetState:
                    {
                        // The writer mirrors from its own reads; the envelope
                        // of this client is verified only by VerifyRead.
                        var w = _writer;
                        TeamHoldNet.Call("GET", TeamHoldNet.PathState(a.Key.HoldId), null, (st, rb) =>
                        {
                            TeamHoldNet.StateAnswer sa;
                            if (!TeamHoldNet.TryParseState(st, rb, out sa)) return;
                            if (w == _writer && TeamHold.Cut == cut) Perform(w.OnState(Now, sa), cut);
                        });
                        break;
                    }
                    case TeamHoldRules.Writer.Op.GetByRoom:
                    {
                        var w = _writer;
                        TeamHoldNet.Call("GET", TeamHoldNet.PathByRoom(cut.Room, cut.G), null, (st, rb) =>
                        {
                            TeamHoldNet.StateAnswer sa;
                            TeamHoldNet.TryParseState(st, rb, out sa);
                            if (w == _writer && TeamHold.Cut == cut) Perform(w.OnByRoom(Now, st, sa), cut);
                        });
                        break;
                    }
                    case TeamHoldRules.Writer.Op.PostEnd:
                    {
                        var w = _writer;
                        TeamHoldNet.Call("POST", TeamHoldNet.PathEnd(a.Key.HoldId), TeamHoldNet.EndBody(a.Reason), (st, rb) =>
                        {
                            if (w == _writer) Perform(w.OnEndAnswer(Now), cut);
                        });
                        break;
                    }
                }
            }
        }
    }
}
