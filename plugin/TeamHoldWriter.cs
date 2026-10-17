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
                if (_cut != null)
                {
                    if (!HoldsAnother(p)) return false;
                    OnSecondDeparture(p);
                    return true;
                }
                if (!Classify(p)) return false;
                // The cascade prefix suppresses on the same memo, so from here
                // the departure is held whatever fails below: the cut is
                // latched first and filled field by field.
                var cut = new TeamHoldRules.DropCut { Actor = p.ActorNumber, At = Time.unscaledTime };
                _cut = cut;
                _leaveAt = Time.unscaledTime;
                _purged = _resolved = false;
                try { Fill(cut, p, buildPlan); }
                catch (Exception ex) { Plugin.Log.LogWarning(TAG + " cut incomplete: " + ex.Message); }
                Plugin.Log.LogInfo(TAG + " cascade suppressed slot=" + cut.Slot.ToString(CultureInfo.InvariantCulture)
                    + " team=" + cut.Team.ToString(CultureInfo.InvariantCulture) + " g=" + (cut.G ?? "")
                    + " eligibility=" + cut.Eligibility);
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
        }

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
            TeamHoldRules.HoldGate.Clear();
        }
    }
}
