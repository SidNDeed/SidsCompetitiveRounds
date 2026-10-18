using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using ExitGames.Client.Photon;
using Photon.Pun;
using UnityEngine;
using Hashtable = ExitGames.Client.Photon.Hashtable;

namespace CompetitiveRounds
{
    /// <summary>
    /// Stage 2 S3, the returner and the master's hand-over. Discovery at the
    /// main menu (after the session is minted) and at the 2v2 and 1v2 tabs;
    /// the claim, the staged join, the bind each beat period, the snapshot
    /// gate, the seeding, the deck replay through OFFLINE_Pick (never
    /// committed) and the entry receipt. The token T stays in memory and is
    /// never logged. Admission (KX3) and registration (KX4) are seams that
    /// never complete while unbound, so the entry bound ends the hold toward
    /// today and the boundary stays closed until then.
    /// </summary>
    internal static class TeamHoldReturn
    {
        internal const string KEY_TBD = TeamHoldRules.KEY_TBD;

        /// <summary>KX3: the roster latch released for the bound actor.</summary>
        internal static Func<bool> AdmissionLatched;
        /// <summary>KX4: the sorted registration and spawn of the returner.</summary>
        internal static Func<bool> Registered;

        // KX3: the admission seam, bound here. The returner's own view of
        // its latch: its Steam id is on the pinned series roster of this
        // flagged room, its roster is frozen to that roster when it has none,
        // a latch the roster now covers is released, and it is not
        // unauthorized. A room with no roster pin never completes it.
        static TeamHoldReturn() { AdmissionLatched = AdmissionNow; }

        private static bool AdmissionNow()
        {
            var me = PhotonNetwork.LocalPlayer;
            if (me == null) return false;
            var roster = TeamHoldRules.LockRoster(TeamHoldWriter.CurrentRoom(), null);
            if (roster == null) return false;
            string sid = RoomActors.SteamIdOf(me);
            if (string.IsNullOrEmpty(sid) || !roster.Contains(sid)) return false;
            if (!RoomActors.RosterFrozen && roster.Count >= 2) RoomActors.FreezeFighterRoster(roster);
            if (RoomActors.IsRejected(me)) RoomActors.ReleaseCoveredLatches();
            return !RoomActors.IsUnauthorized(me);
        }

        private static TeamHoldNet.MineAnswer _offer;
        private static double _offerAt;
        private static bool _menuDone;
        private static TeamHoldRules.ReturnRoute _route;
        private static TeamHoldNet.ClaimAnswer _claim;
        private static TeamHoldNet.MineAnswer _claimed;
        private static string _token;
        private static double _lastBind = -1000;
        private static bool _callInFlight, _enteredPosted, _replayed;
        private static TeamHoldRules.Snapshot _snap;

        internal static string Message { get; private set; }
        internal static double MessageAt { get; private set; } = -1000;

        private static double Now { get { return Time.unscaledTime; } }

        /// <summary>The offer shown to this player, or null.</summary>
        internal static TeamHoldNet.MineAnswer Offer { get { return _route == null ? _offer : null; } }
        internal static double OfferLeft { get { return _offer == null ? 0 : Math.Max(0, _offer.HoldS - (Now - _offerAt)); } }

        /// <summary>GET mine: shown only for a readmissible answer (T3.9).</summary>
        internal static void Discover(string why)
        {
            try
            {
                if (string.IsNullOrEmpty(SteamAuth.SessionToken) || PhotonNetwork.InRoom || _route != null) return;
                TeamHoldNet.Call("GET", TeamHoldNet.PathMine, null, (st, body) =>
                {
                    TeamHoldNet.MineAnswer a;
                    TeamHoldNet.TryParseMine(st, body, out a);
                    if (!TeamHoldRules.DiscoveryShows(a)) { _offer = null; return; }
                    _offer = a;
                    _offerAt = Now;
                });
            }
            catch { }
        }

        internal static void Dismiss() { _offer = null; }

        /// <summary>Rejoin: step 1, the claim.</summary>
        internal static void Claim()
        {
            var offer = _offer;
            if (offer == null || _route != null) return;
            _offer = null;
            _route = new TeamHoldRules.ReturnRoute();
            _claimed = offer;
            _snap = null;
            _enteredPosted = _replayed = false;
            _callInFlight = true;
            var route = _route;
            TeamHoldNet.Call("POST", TeamHoldNet.PathClaim(offer.HoldId), "{}", (st, body) =>
            {
                _callInFlight = false;
                if (route != _route) return;
                TeamHoldNet.ClaimAnswer a;
                if (!TeamHoldNet.TryParseClaim(st, body, out a) || a == null || !a.Ok)
                {
                    Fail(TeamHoldRules.ReturnRoute.Stage.Claim, a != null ? a.Reason : "no_answer");
                    return;
                }
                _claim = a;
                _token = a.Token;
                route.Slot = a.Slot;
                Stage(offer, a);
                route.Done(TeamHoldRules.ReturnRoute.Stage.Claim, true, Now);
            });
        }

        /// <summary>Step 2, while not in a room (#287): stage the seat's keys,
        /// pin the flag from the claim answer, set the mode's existing pending
        /// slot and the pending room.</summary>
        private static void Stage(TeamHoldNet.MineAnswer offer, TeamHoldNet.ClaimAnswer a)
        {
            var props = new Hashtable
            {
                { Player.VAR_PLAYERID, a.Slot },
                { Player.VAR_TEAMID, a.Team >= 0 ? a.Team : TeamHoldRules.SlotToTeam(offer.Mode, a.Slot) },
                { TeamHoldRules.KEY_RDT, offer.HoldId + ":" + a.Token },
            };
            string mySid = MatchTracker.LocalSteamId;
            if (!string.IsNullOrEmpty(mySid) && mySid != "unknown") props["u_id"] = mySid;
            if (PhotonNetwork.LocalPlayer != null) PhotonNetwork.LocalPlayer.SetCustomProperties(props);
            TeamHoldRules.PinRoom(a.Room, a.Hold, offer.Mode, a.SeriesId, null);
            if (offer.Mode == TeamHoldRules.MODE_TEAM) Plugin.SetPending2v2Slot(a.Slot);
            else Plugin.SetPendingOvtSlot(a.Slot);
            Plugin.SetPendingRoom(a.Room, a.Region);
        }

        /// <summary>Any failure before entry ends toward today (S3 step 9).</summary>
        private static void Fail(TeamHoldRules.ReturnRoute.Stage stage, string why)
        {
            var route = _route;
            if (route != null && route.S != TeamHoldRules.ReturnRoute.Stage.Ended) route.Done(stage, false, Now, why);
            Plugin.Log.LogInfo(TeamHold.TAG + " rejoin failed at " + stage + ": " + (why ?? ""));
            End(why);
        }

        private static void End(string why)
        {
            var offer = _claimed;
            Message = I18n.Tr("Could not rejoin at this point");
            MessageAt = Now;
            if (offer != null && !string.IsNullOrEmpty(offer.HoldId))
                TeamHoldNet.Call("POST", TeamHoldNet.PathEnd(offer.HoldId), TeamHoldNet.EndBody("entry_failed:" + (why ?? "")), (st, b) => { });
            _route = null;
            _claim = null;
            _token = null;
            _snap = null;
            try
            {
                if (!PhotonNetwork.InRoom)
                {
                    Plugin.ClearPendingRoom();
                    Plugin.ClearPending2v2Slot();
                    Plugin.ClearPendingOvtSlot();
                }
            }
            catch { }
        }

        /// <summary>Per frame from the host.</summary>
        internal static void Tick()
        {
            try
            {
                if (!_menuDone && !PhotonNetwork.InRoom && !string.IsNullOrEmpty(SteamAuth.SessionToken))
                {
                    _menuDone = true;
                    Discover("menu");
                }
                var route = _route;
                if (route == null) return;
                double now = Now;
                route.Tick(now);
                if (route.S == TeamHoldRules.ReturnRoute.Stage.Ended) { Plugin.Log.LogInfo(TeamHold.TAG + " rejoin ended: " + route.EndReason); End(route.EndReason); return; }
                if (route.BoundaryReleased) { Finish(); return; }
                var a = _claim;
                if (a == null) return;
                switch (route.S)
                {
                    case TeamHoldRules.ReturnRoute.Stage.Join:
                        if (PhotonNetwork.InRoom && string.Equals(TeamHoldWriter.CurrentRoom(), a.Room, StringComparison.Ordinal))
                            route.Done(TeamHoldRules.ReturnRoute.Stage.Join, true, now);
                        break;
                    case TeamHoldRules.ReturnRoute.Stage.Bind:
                        Bind(now, route, a);
                        break;
                    case TeamHoldRules.ReturnRoute.Stage.Token:
                        // The master writes the snapshot only after its token
                        // check; its arrival for this hold is the check passing.
                        TeamHoldRules.Snapshot s;
                        if (TeamHoldRules.TryParseSnapshot(TeamHoldWriter.RoomProp(TeamHoldRules.KEY_TSN), out s) && s.HoldId == _claimed.HoldId)
                            route.Done(TeamHoldRules.ReturnRoute.Stage.Token, true, now);
                        break;
                    case TeamHoldRules.ReturnRoute.Stage.Latch:
                        if (Seam(AdmissionLatched)) route.Done(TeamHoldRules.ReturnRoute.Stage.Latch, true, now);
                        break;
                    case TeamHoldRules.ReturnRoute.Stage.Snapshot:
                        Gate(now, route, a);
                        break;
                    case TeamHoldRules.ReturnRoute.Stage.Register:
                        if (Seam(Registered)) route.Done(TeamHoldRules.ReturnRoute.Stage.Register, true, now);
                        break;
                    case TeamHoldRules.ReturnRoute.Stage.Activate:
                        if (Activated())
                        {
                            if (!_replayed) { _replayed = true; Replay(true, a.Slot); }
                            route.Done(TeamHoldRules.ReturnRoute.Stage.Activate, true, now);
                        }
                        break;
                    case TeamHoldRules.ReturnRoute.Stage.Entered:
                        PostEntered(route, a);
                        break;
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning(TeamHold.TAG + " return error: " + ex.Message); Fail(_route != null ? _route.S : TeamHoldRules.ReturnRoute.Stage.Claim, "error"); }
        }

        private static bool Seam(Func<bool> f)
        {
            if (f == null) return false;
            try { return f(); } catch { return false; }
        }

        private static bool Activated()
        {
            try { var gm = GM_ArmsRace.instance; return gm != null && gm.gameObject.activeInHierarchy; } catch { return false; }
        }

        /// <summary>Step 3: bind actor X each beat period; uncorroborated is
        /// retried until the entry bound.</summary>
        private static void Bind(double now, TeamHoldRules.ReturnRoute route, TeamHoldNet.ClaimAnswer a)
        {
            if (_callInFlight || now - _lastBind < TeamHoldLoop.BeatS) return;
            _lastBind = now;
            _callInFlight = true;
            int actor = PhotonNetwork.LocalPlayer != null ? PhotonNetwork.LocalPlayer.ActorNumber : 0;
            TeamHoldNet.Call("POST", TeamHoldNet.PathBind(_claimed.HoldId), TeamHoldNet.BindBody(actor, a.Region), (st, body) =>
            {
                _callInFlight = false;
                if (route != _route) return;
                bool bound; string reason;
                if (!TeamHoldNet.TryParseBind(st, body, out bound, out reason)) return;
                if (bound) route.Done(TeamHoldRules.ReturnRoute.Stage.Bind, true, Now);
                else if (reason != "uncorroborated") Fail(TeamHoldRules.ReturnRoute.Stage.Bind, reason);
            });
        }

        /// <summary>Step 7: the returner's gate over cr_tsn, every remaining
        /// non-master fighter's cr_tbd, the claim's G, the server tally and
        /// the server's boundary checkpoint. On pass, step 8's seeding.</summary>
        private static void Gate(double now, TeamHoldRules.ReturnRoute route, TeamHoldNet.ClaimAnswer a)
        {
            var digests = new List<string>();
            foreach (var p in PhotonNetwork.PlayerList)
            {
                if (p == null || p.IsLocal || p.IsMasterClient || RoomActors.IsSpectatorReplicated(p)) continue;
                digests.Add(TeamHoldWriter.PlayerProp(p, KEY_TBD));
            }
            int expected = _claimed.Mode == TeamHoldRules.MODE_TEAM ? 2 : 1;
            var gm = GM_ArmsRace.instance;
            int ptw = gm != null ? gm.pointsToWinRound : 2;
            TeamHoldRules.Snapshot snap;
            // The server tally: the claim answer carries none at the server
            // half's tip, so the discovery answer's series_tally (a server
            // read of the same series row) is the comparison.
            int w0 = a.W0 >= 0 ? a.W0 : _claimed.W0, w1 = a.W1 >= 0 ? a.W1 : _claimed.W1;
            string why = TeamHoldRules.CheckSnapshot(TeamHoldWriter.RoomProp(TeamHoldRules.KEY_TSN), digests, expected, a.G,
                                                     w0, w1, a.BoundaryDigest, a.Slot, ptw, out snap);
            if (why == "digest missing") return;   // a digest still in flight: wait, the entry bound ends it
            if (why != null) { Fail(TeamHoldRules.ReturnRoute.Stage.Snapshot, why); return; }
            _snap = snap;
            Seed(snap);
            route.Done(TeamHoldRules.ReturnRoute.Stage.Snapshot, true, now);
        }

        /// <summary>Step 8: the vanilla score fields and every SeatDeckLog.
        /// The watcher counters, the draw index and the cr_cards republish
        /// are KX4 (GameStateWatcher and VanillaCardSequence privates).</summary>
        private static void Seed(TeamHoldRules.Snapshot s)
        {
            var gm = GM_ArmsRace.instance;
            if (gm != null) { gm.p1Rounds = s.R0; gm.p2Rounds = s.R1; gm.p1Points = s.P0; gm.p2Points = s.P1; }
            foreach (var slot in s.Slots) SeatDeckLog.Seed(slot.Slot, slot.Names, slot.Deaths);
            Plugin.Log.LogInfo(TeamHold.TAG + " restored score " + s.R0 + "-" + s.R1 + " points " + s.P0 + "-" + s.P1);
        }

        private static void PostEntered(TeamHoldRules.ReturnRoute route, TeamHoldNet.ClaimAnswer a)
        {
            if (_enteredPosted) return;
            _enteredPosted = true;
            int actor = PhotonNetwork.LocalPlayer != null ? PhotonNetwork.LocalPlayer.ActorNumber : 0;
            TeamHoldNet.Call("POST", TeamHoldNet.PathEntered(_claimed.HoldId), TeamHoldNet.EnteredBody(a.G, actor), (st, body) =>
            {
                if (route != _route) return;
                string why;
                if (TeamHoldNet.TryParseEntered(st, body, out why)) route.Done(TeamHoldRules.ReturnRoute.Stage.Entered, true, Now);
                else Fail(TeamHoldRules.ReturnRoute.Stage.Entered, why);
            });
        }

        private static void Finish()
        {
            Message = I18n.Tr("You are back in the match");
            MessageAt = Now;
            _route = null;
            _claim = null;
            _token = null;
        }

        // ── The master's hand-over (S3 steps 4 and 7) ─────────────────────

        private static string _snapWrittenFor, _tbdFor;

        /// <summary>On a verified b, the master: the token check of X against
        /// its own server read, then cr_tsn. Every remaining fighter publishes
        /// its own cr_tbd from its own record. Called by TeamHoldLoop.</summary>
        internal static void OnVerifiedBound(TeamHoldRules.DropCut cut, TeamHoldRules.HoldKey k, TeamHoldNet.StateAnswer server)
        {
            if (cut == null || k == null || server == null) return;
            var snap = BuildSnapshot(cut, k.HoldId);
            if (_tbdFor != k.HoldId)
            {
                _tbdFor = k.HoldId;
                try
                {
                    PhotonNetwork.LocalPlayer.SetCustomProperties(new Hashtable { { KEY_TBD, TeamHoldRules.SnapshotDigest(snap) } });
                }
                catch { }
            }
            if (!PhotonNetwork.IsMasterClient || _snapWrittenFor == k.HoldId) return;
            Photon.Realtime.Player x = null;
            foreach (var p in PhotonNetwork.PlayerList) if (p != null && p.ActorNumber == k.BoundActor) x = p;
            string rdt = TeamHoldWriter.PlayerProp(x, TeamHoldRules.KEY_RDT);
            if (!TeamHoldRules.TokenCheck(rdt, k.HoldId, server.Verifier, k.BoundActor))
            {
                _snapWrittenFor = k.HoldId;
                TeamHoldLoop.EndLocal(Time.unscaledTime, k, "token_refused");
                return;
            }
            _snapWrittenFor = k.HoldId;
            TeamHoldWriter.CasRoomProps(new Hashtable { { TeamHoldRules.KEY_TSN, snap.Format() } }, null, null);
        }

        /// <summary>This client's snapshot of the held game: the score now (at
        /// the freeze), the series tally and the boundary state from its cut,
        /// every slot's record from its own SeatDeckLog.</summary>
        internal static TeamHoldRules.Snapshot BuildSnapshot(TeamHoldRules.DropCut cut, string holdId)
        {
            var gm = GM_ArmsRace.instance;
            var s = new TeamHoldRules.Snapshot
            {
                HoldId = holdId ?? "", G = cut.G ?? "",
                R0 = gm != null ? gm.p1Rounds : cut.R0, R1 = gm != null ? gm.p2Rounds : cut.R1,
                P0 = gm != null ? gm.p1Points : cut.P0, P1 = gm != null ? gm.p2Points : cut.P1,
                W0 = cut.W0, W1 = cut.W1,
                Ledger = TeamHoldRules.Fnv64Hex(TeamHoldWriter.RoomProp(TeamHoldRules.KEY_TOFF) ?? ""),
                BR0 = cut.BR0, BR1 = cut.BR1, BP0 = cut.BP0, BP1 = cut.BP1,
            };
            if (cut.BNames != null) s.BNames.AddRange(cut.BNames);
            s.BDeals = s.BNames.Count;
            // Sorted: every client must format the same slots in the same order.
            var slots = new List<int>(SeatDeckLog.Slots());
            slots.Sort();
            foreach (var slot in slots)
            {
                SeatDeckLog.Seat seat;
                if (!SeatDeckLog.TryGetSeat(slot, out seat)) continue;
                var st = new TeamHoldRules.SlotState { Slot = slot, Deals = seat.Deals, Deaths = seat.Deaths };
                st.Names.AddRange(seat.Names);
                s.Slots.Add(st);
            }
            return s;
        }

        // ── The deck replay (S3 step 8) ────────────────────────────────────

        /// <summary>Each client replays from its own SeatDeckLog through
        /// OFFLINE_Pick: the returner every slot, a survivor the returner's
        /// slot. One card per frame (#225). Never committed (S0 step 2). The
        /// coroutine runs on the game mode object, which lives for the match.</summary>
        internal static void Replay(bool returner, int heldSlot)
        {
            try
            {
                var host = GM_ArmsRace.instance;
                if (host != null) host.StartCoroutine(ReplayRun(returner, heldSlot));
            }
            catch { }
        }

        private static IEnumerator ReplayRun(bool returner, int heldSlot)
        {
            var pm = PlayerManager.instance;
            if (pm == null) yield break;
            var bodies = new List<Player>(pm.players);
            foreach (var body in bodies)
            {
                if (body == null) continue;
                if (!returner && body.PlayerID != heldSlot) continue;
                SeatDeckLog.Seat seat;
                if (!SeatDeckLog.TryGetSeat(body.PlayerID, out seat)) continue;
                foreach (var name in new List<string>(seat.Names))
                {
                    var prefab = ResolveCard(name);
                    if (prefab == null) { Plugin.Log.LogWarning(TeamHold.TAG + " replay: card '" + name + "' not found"); continue; }
                    try { FfaMode.SpectatorApplyCard(body, prefab); } catch (Exception ex) { Plugin.Log.LogWarning(TeamHold.TAG + " replay: " + ex.Message); }
                    yield return null;
                }
            }
        }

        private static CardInfo ResolveCard(string name)
        {
            try
            {
                var cards = CardChoice.instance != null ? CardChoice.instance.cards : null;
                if (cards == null) return null;
                foreach (var c in cards)
                    if (c != null && CardRarityLookup.GetCanonicalName(c.gameObject.name) == name) return c;
            }
            catch { }
            return null;
        }

        // ── The offer (IMGUI, non-modal over the menu) ─────────────────────

        private static GUIStyle _style;

        internal static void DrawOffer()
        {
            try
            {
                if (Event.current == null) return;
                var offer = Offer;
                string msg = Now - MessageAt < 6 ? Message : null;
                if (offer == null && msg == null) return;
                if (_style == null)
                {
                    _style = new GUIStyle(GUI.skin.label) { alignment = TextAnchor.MiddleCenter, fontStyle = FontStyle.Bold, fontSize = 16, wordWrap = true };
                    _style.normal.textColor = Color.white;
                }
                float w = Mathf.Min(520f, Screen.width - 16f), h = offer != null ? 96f : 40f;
                var r = new Rect((Screen.width - w) / 2f, Screen.height * 0.18f, w, h);
                var prev = GUI.color;
                try
                {
                    GUI.color = new Color(0.08f, 0.12f, 0.22f, 0.92f);
                    GUI.DrawTexture(r, Texture2D.whiteTexture, ScaleMode.StretchToFill);
                    GUI.color = Color.white;
                    if (offer == null) { GUI.Label(r, msg, _style); return; }
                    int left = (int)Math.Ceiling(OfferLeft);
                    if (left <= 0) { _offer = null; return; }
                    GUI.Label(new Rect(r.x + 8, r.y + 6, r.width - 16, 44), I18n.TrF("Your match is still running. Rejoin? {0}", left), _style);
                    if (GUI.Button(new Rect(r.x + r.width / 2f - 150, r.y + 54, 140, 32), I18n.Tr("Rejoin"))) Claim();
                    if (GUI.Button(new Rect(r.x + r.width / 2f + 10, r.y + 54, 140, 32), I18n.Tr("Not now"))) Dismiss();
                    // The panel is a backdrop: a click on it never reaches the menu.
                    if (Event.current.type == EventType.MouseDown && r.Contains(Event.current.mousePosition)) Event.current.Use();
                }
                finally { GUI.color = prev; }
            }
            catch { }
        }

        internal static void OnRoomLeft()
        {
            _snapWrittenFor = null;
            _tbdFor = null;
        }
    }
}
