using System;
using System.Collections.Generic;
using System.Globalization;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// FFA mid-game readmission, the client half of V3 P4.2 (design
    /// ai-collab/rejoin/RJ-READMIT-DESIGN-V3.md): discovery when the FFA tab
    /// opens, the non-modal bar, the claim, the bind each census period, the
    /// decline, the entered step, and the presence census of a readmission
    /// lobby. The decisions are FfaReadmitEntryRules'; this file only carries
    /// them to the server, the room and the screen. The token is held in
    /// memory only and never logged.
    /// </summary>
    internal static class FfaReadmit
    {
        internal static readonly FfaReadmitEntryRules.RdmClient State = new FfaReadmitEntryRules.RdmClient();

        private static bool _discovered;
        private static bool _discoveryInFlight;
        private static bool _postInFlight;
        private static float _nextBindRt;
        private static float _lastPresenceRt = -999f;

        /// <summary>The assembly POST timeout (K23: every assembly, presence and
        /// connect POST passes four seconds), the same constant.</summary>
        private const int PostTimeout = FfaAssembly.PostTimeout;

        private static string I(int v) { return v.ToString(CultureInfo.InvariantCulture); }

        /// <summary>V3 P5, the client rungs of the positive ladder: one line on
        /// the transition into offered, claimed and bound (and entered at the
        /// self-kept moment), from FfaReadmitEntryRules.LadderRung.</summary>
        private static void Ladder(FfaReadmitEntryRules.RdmState before, bool selfKept, string extra)
        {
            string line = FfaReadmitEntryRules.LadderLine(FfaReadmitEntryRules.LadderRung(before, State.State, selfKept),
                                                          JoinTimeline.Id8(State.Lobby), State);
            if (line != null) Plugin.Log.LogInfo(line + (extra ?? ""));
        }

        /// <summary>The self-kept moment of a kind r seat (OnSelfKept).</summary>
        internal static void LadderEntered()
        {
            Ladder(State.State, true, null);
        }

        private static float Now() { return Time.realtimeSinceStartup; }

        // ------------------------------------------------------------ discovery (P4.2)

        /// <summary>The FFA tab's opener, in place of the bare probe: the
        /// read-only offer GET first; today's probe runs only on an answer that
        /// offers nothing (0, an error, an older server). Once per launch, as
        /// the probe is; a seat already polling skips straight to the probe,
        /// and the poll's belt carries the offer for it.</summary>
        internal static void DiscoverThenProbe()
        {
            if (_discovered || _discoveryInFlight) return;
            if (ApiClient.IsFfaQueuePolling)
            {
                _discovered = true;
                ApiClient.FfaProbeServerState();
                return;
            }
            string sid = MatchTracker.LocalSteamId;
            if (string.IsNullOrEmpty(sid) || sid == "unknown") return;
            _discoveryInFlight = true;
            ApiClient.FfaReadmitOffer(sid, (ok, resp) =>
            {
                _discoveryInFlight = false;
                _discovered = true;
                bool offered = false;
                try
                {
                    if (ok && !string.IsNullOrEmpty(resp))
                    {
                        var m = FfaAssembly.Members(resp);
                        int rd = FfaAssembly.ExtractJsonInt(m, "readmissible", 0);
                        string lobby = FfaAssembly.ExtractJsonString(m, "lobby_id");
                        int slot = FfaAssembly.ExtractJsonInt(m, "slot", -1);
                        int n = FfaAssembly.ExtractJsonInt(m, "n", 0);
                        int holdS = FfaAssembly.ExtractJsonInt(m, "hold_s", 0);
                        if (FfaReadmitEntryRules.DiscoveryOffers(rd, lobby, n, holdS))
                        {
                            Offer(lobby, slot, n, holdS, "discovery");
                            offered = true;
                        }
                    }
                }
                catch (Exception ex) { Plugin.Log.LogWarning("[FFA-RDM] offer parse: " + ex.Message); }
                if (!offered) ApiClient.FfaProbeServerState();
            });
        }

        /// <summary>The poll's belt (a ready_join for a held seat): the bar,
        /// never a join or a leave.</summary>
        internal static void OfferFromPoll(string lobby, int slot, int n, int holdS)
        {
            if (!FfaReadmitEntryRules.DiscoveryOffers(1, lobby, n, holdS)) return;
            Offer(lobby, slot, n, holdS, "poll");
        }

        private static void Offer(string lobby, int slot, int n, int holdS, string src)
        {
            var before = State.State;
            FfaReadmitEntryRules.Offer(State, lobby, slot, n, holdS, Now());
            Ladder(before, false, " hold_s=" + I(holdS) + " src=" + src);
            try { NativeUI.MarkDirty(); } catch { }
        }

        /// <summary>Whether this client holds a claim for the lobby (the belt
        /// proceeds to the join for it).</summary>
        internal static bool ClaimedFor(string lobby)
        {
            return !string.IsNullOrEmpty(lobby) && State.Lobby == lobby
                   && (State.State == FfaReadmitEntryRules.RdmState.Claimed
                       || State.State == FfaReadmitEntryRules.RdmState.Binding
                       || State.State == FfaReadmitEntryRules.RdmState.Admitted);
        }

        /// <summary>Whether this seat entered (or is entering) the lobby by
        /// readmission: its late entry is kind r.</summary>
        internal static bool ReadmittedInto(string lobby)
        {
            return !string.IsNullOrEmpty(lobby) && State.Lobby == lobby
                   && (State.State == FfaReadmitEntryRules.RdmState.Admitted
                       || State.State == FfaReadmitEntryRules.RdmState.Entered);
        }

        /// <summary>The pre-join staging (#287): with a claim held for this
        /// lobby, cr_rdt = "{n}:{T}" rides the join itself. No cr_spec: the
        /// seat joins as a fighter.</summary>
        internal static void StageInto(ExitGames.Client.Photon.Hashtable prejoin, string lobby)
        {
            if (prejoin == null || !ClaimedFor(lobby) || string.IsNullOrEmpty(State.Token)) return;
            prejoin[FfaReadmitEntryRules.RdtProp] = FfaReadmitEntryRules.RdtValue(State.N, State.Token);
        }

        // ------------------------------------------------------------ the bar's buttons

        internal static bool BarVisible
        {
            get { return State.State == FfaReadmitEntryRules.RdmState.Offered; }
        }

        internal static int BarSeconds
        {
            get { return FfaReadmitEntryRules.SecondsLeft(State, Now()); }
        }

        private static GUIStyle _barText, _barButton;

        /// <summary>The non-modal readmission bar (V3 P4), from DrawUI: the
        /// remaining hold in seconds, Yes claims, Decline ends the hold.</summary>
        internal static void DrawBar()
        {
            if (!BarVisible) return;
            if (_barText == null)
            {
                _barText = new GUIStyle(GUI.skin.label)
                {
                    fontSize = 15, richText = true, fontStyle = FontStyle.Bold, alignment = TextAnchor.MiddleLeft,
                };
                _barButton = new GUIStyle(GUI.skin.button) { fontSize = 14, fontStyle = FontStyle.Bold };
            }
            float w = 640f, h = 46f;
            float x = (Screen.width - w) / 2f, y = 60f;
            GUI.DrawTexture(new Rect(x, y, w, h), Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0,
                            new Color(0.08f, 0.10f, 0.14f, 0.94f), 0, 0);
            GUI.Label(new Rect(x + 14f, y + 4f, w - 250f, h - 8f),
                      I18n.TrF("Your FFA match is still running. Rejoin? {0}", I(BarSeconds) + "s"), _barText);
            if (GUI.Button(new Rect(x + w - 226f, y + 8f, 100f, 30f), I18n.Tr("Yes"), _barButton)) Accept();
            if (GUI.Button(new Rect(x + w - 116f, y + 8f, 100f, 30f), I18n.Tr("Decline"), _barButton)) Decline();
        }

        internal static void Accept()
        {
            if (State.State != FfaReadmitEntryRules.RdmState.Offered || _postInFlight) return;
            State.State = FfaReadmitEntryRules.RdmState.Claiming;
            Send("claim", 0, 0);
            try { NativeUI.MarkDirty(); } catch { }
        }

        internal static void Decline()
        {
            if (State.State != FfaReadmitEntryRules.RdmState.Offered || _postInFlight) return;
            Send("decline", 0, 0);
            State.State = FfaReadmitEntryRules.RdmState.Declined;
            try { NativeUI.MarkDirty(); } catch { }
            ApiClient.FfaProbeServerState();
        }

        // ------------------------------------------------------------ the route

        private static void Send(string step, int actor, int game)
        {
            string lobby = State.Lobby;
            if (string.IsNullOrEmpty(lobby)) return;
            string region = "";
            if (step == "bind") region = FfaAssembly.LiveRegionCode();
            string body = FfaReadmitEntryRules.RequestBody(ApiClient.JsonEscapeFullPublic(MatchTracker.LocalSteamId ?? ""),
                                                           step, State.N, actor,
                                                           ApiClient.JsonEscapeFullPublic(region), game,
                                                           JoinTimeline.ClientMs());
            _postInFlight = true;
            ApiClient.AsmPost(ApiClient.BaseUrl + "/api/v1/ffa/lobby/" + lobby + "/readmit", body, (ok, resp) =>
            {
                _postInFlight = false;
                if (!ok)
                {
                    Plugin.Log.LogWarning("[FFA-RDM] " + step + " post failed: " + (resp ?? "") );
                    if (step == "claim" && State.State == FfaReadmitEntryRules.RdmState.Claiming)
                        State.State = FfaReadmitEntryRules.RdmState.Offered;   // the bar stays; the player may retry
                    return;
                }
                FfaReadmitEntryRules.RdmAnswer a = null;
                try { a = ParseAnswer(resp); } catch (Exception ex) { Plugin.Log.LogWarning("[FFA-RDM] answer parse: " + ex.Message); }
                if (a == null) return;
                var before = State.State;
                var next = FfaReadmitEntryRules.OnAnswer(State, step, a, Now());
                Ladder(before, false, null);
                Act(step, next, a);
            }, timeout: PostTimeout);
        }

        private static FfaReadmitEntryRules.RdmAnswer ParseAnswer(string resp)
        {
            var outer = FfaAssembly.Members(resp);
            var m = FfaAssembly.Members(FfaAssembly.ExtractJsonRaw(outer, "readmit"));
            if (m.Count == 0) return null;
            return new FfaReadmitEntryRules.RdmAnswer
            {
                Status = FfaAssembly.ExtractJsonString(m, "status") ?? "",
                Reason = FfaAssembly.ExtractJsonString(m, "reason") ?? "",
                Retry = FfaAssembly.ExtractJsonInt(m, "retry", 0),
                Token = FfaAssembly.ExtractJsonString(m, "token"),
                Room = FfaAssembly.ExtractJsonString(m, "room"),
                Region = FfaAssembly.ExtractJsonString(m, "region"),
                Slot = FfaAssembly.ExtractJsonInt(m, "slot", -1),
                N = FfaAssembly.ExtractJsonInt(m, "n", 0),
                HoldS = FfaAssembly.ExtractJsonInt(m, "hold_s", -1),
                Game = FfaAssembly.ExtractJsonInt(m, "game", 0),
                Kind = FfaAssembly.ExtractJsonString(m, "kind"),
                Actor = FfaAssembly.ExtractJsonInt(m, "actor", 0),
            };
        }

        private static void Act(string step, FfaReadmitEntryRules.RdmNext next, FfaReadmitEntryRules.RdmAnswer a)
        {
            switch (next)
            {
                case FfaReadmitEntryRules.RdmNext.JoinRoom:
                    // The claim set this seat's queue row to ready_join for the
                    // lobby: the poll's lock routine joins the room, with
                    // cr_rdt staged pre-join (StageInto).
                    _nextBindRt = 0f;
                    ApiClient.FfaStartReadmitPoll();
                    break;
                case FfaReadmitEntryRules.RdmNext.BindAgain:
                    _nextBindRt = Now() + FfaReadmitEntryRules.PresencePeriodS;
                    if (!_retryToastShown)
                    {
                        _retryToastShown = true;
                        try { CompetitiveUI.ShowNotification("Could not confirm your seat. Retrying", new Color(1f, 0.8f, 0.4f), 6f); } catch { }
                    }
                    break;
                case FfaReadmitEntryRules.RdmNext.ArmLate:
                    try
                    {
                        FfaLateEntry.PrepareReadmitEntry();
                        FfaLateEntry.OnAdmittedLate(new FfaAssembly.Answer
                        {
                            Route = "readmit", Step = "bind", Lobby = State.Lobby,
                            Room = FfaAssembly.CurrentRoomName() ?? "", Status = "admitted_late",
                            Assembly = 1, Game = State.Game, Rt = Now(),
                        });
                    }
                    catch (Exception ex) { Plugin.Log.LogWarning("[FFA-RDM] arm late: " + ex.Message); }
                    break;
                case FfaReadmitEntryRules.RdmNext.Leave:
                    Refusal(State.LastReason, true);
                    break;
                case FfaReadmitEntryRules.RdmNext.Probe:
                    if (State.State == FfaReadmitEntryRules.RdmState.Refused) Refusal(State.LastReason, false);
                    ApiClient.FfaProbeServerState();
                    break;
                case FfaReadmitEntryRules.RdmNext.Done:
                    // Step 10: a seat that entered may drop again; the next
                    // FFA tab open discovers hold n + 1.
                    _discovered = false;
                    break;
            }
            try { NativeUI.MarkDirty(); } catch { }
        }

        private static bool _retryToastShown;

        /// <summary>A refused readmission: a truthful toast from the reason
        /// (V3 P4.5), then the seat leaves its room and the queue row the
        /// claim set, never sitting as a bodiless actor.</summary>
        private static void Refusal(string reason, bool leave)
        {
            Plugin.Log.LogInfo("[FFA-RDM] refused reason=" + (reason ?? "-") + (leave ? " leave=1" : ""));
            var amber = new Color(1f, 0.8f, 0.4f);
            try
            {
                switch (FfaReadmitEntryRules.ClassOf(reason))
                {
                    case FfaReadmitEntryRules.RefusalClass.Released:
                        CompetitiveUI.ShowNotification("The seat was released before you returned", amber, 7f); break;
                    case FfaReadmitEntryRules.RefusalClass.Ended:
                        CompetitiveUI.ShowNotification("That match has ended", amber, 7f); break;
                    case FfaReadmitEntryRules.RefusalClass.Departed:
                        CompetitiveUI.ShowNotification("You left that match", amber, 7f); break;
                    case FfaReadmitEntryRules.RefusalClass.OtherQueue:
                        CompetitiveUI.ShowNotification("You are in another queue", amber, 7f); break;
                    case FfaReadmitEntryRules.RefusalClass.Retrying:
                        CompetitiveUI.ShowNotification("Could not confirm your seat. Retrying", amber, 7f); break;
                    case FfaReadmitEntryRules.RefusalClass.Identity:
                        CompetitiveUI.ShowNotification("Another player is using your seat identity", amber, 7f); break;
                    default:
                        CompetitiveUI.ShowNotification("Could not rejoin at this point", amber, 7f); break;
                }
            }
            catch { }
            if (!leave) return;
            try
            {
                if (PhotonNetwork.InRoom && PhotonNetwork.CurrentRoom != null && PhotonNetwork.CurrentRoom.Name == State.Room)
                    PhotonNetwork.LeaveRoom();
            }
            catch { }
            try { ApiClient.FfaLeaveQueue(label: "readmit_refused"); } catch { }
        }

        // ------------------------------------------------------------ the survivors' texts (P4)

        private static Dictionary<int, int> _holds;
        private static readonly Dictionary<int, int> _kindRAtHold = new Dictionary<int, int>();

        private static int KindRCount(int slot)
        {
            int c = 0;
            var rec = FfaLateEntry.Record;
            if (rec != null && rec.Entries != null)
                foreach (var e in rec.Entries) if (e.Slot == slot && e.Kind == 'r') c++;
            return c;
        }

        /// <summary>A readmission lobby answer's `holds`: "Seat held for {0}:
        /// {1}" when a seat's hold starts, "{0} did not return; seat released"
        /// when it ends without a bind. An answer without the key shows nothing.</summary>
        internal static void OnHoldsAnswer(string raw)
        {
            if (raw == null) return;
            var now = new Dictionary<int, int>();
            foreach (var o in FfaAssembly.JsonObjects(raw))
            {
                var e = FfaAssembly.Members(o);
                int s = FfaAssembly.ExtractJsonInt(e, "slot", -1), h = FfaAssembly.ExtractJsonInt(e, "hold_s", 0);
                if (s >= 0 && h > 0) now[s] = h;
            }
            var bound = new HashSet<int>();
            if (_holds != null)
                foreach (var kv in _holds)
                {
                    int at;
                    if (_kindRAtHold.TryGetValue(kv.Key, out at) && KindRCount(kv.Key) > at) bound.Add(kv.Key);
                }
            var started = new List<int>();
            var released = new List<int>();
            FfaReadmitEntryRules.HoldsDiff(_holds, now, bound, started, released);
            var c = new Color(1f, 0.85f, 0.5f);
            foreach (int s in started)
            {
                _kindRAtHold[s] = KindRCount(s);
                Plugin.Log.LogInfo("[FFA-RDM] seat held slot=" + I(s) + " hold_s=" + I(now[s]));
                try { CompetitiveUI.ShowNotification(I18n.TrF("Seat held for {0}: {1}", FfaMode.SeatName(s), I(now[s]) + "s"), c, 6f); } catch { }
            }
            foreach (int s in released)
            {
                _kindRAtHold.Remove(s);
                Plugin.Log.LogInfo("[FFA-RDM] seat released slot=" + I(s));
                try { CompetitiveUI.ShowNotification(I18n.TrF("{0} did not return; seat released", FfaMode.SeatName(s)), c, 6f); } catch { }
            }
            _holds = now;
        }

        // ------------------------------------------------------------ entered (P4.3 step 11)

        /// <summary>The kind r seat's `entered`: game g, n and the bound actor.</summary>
        internal static void PostEntered(int game)
        {
            if (State.State != FfaReadmitEntryRules.RdmState.Admitted) return;
            int actor = 0;
            try { actor = PhotonNetwork.LocalPlayer.ActorNumber; } catch { }
            Send("entered", actor, game);
        }

        // ------------------------------------------------------------ the tick

        /// <summary>Every frame from FfaAssembly.Tick: the bar's lapse, the
        /// bind each census period once in the claimed room, and the presence
        /// census of a readmission lobby.</summary>
        internal static void Tick()
        {
            float now = Now();
            var next = FfaReadmitEntryRules.Tick(State, now);
            if (next != FfaReadmitEntryRules.RdmNext.None)
            {
                Act("lapse", next, null);
                return;
            }
            string room = null;
            try { room = PhotonNetwork.InRoom && PhotonNetwork.CurrentRoom != null ? PhotonNetwork.CurrentRoom.Name : null; } catch { }
            if ((State.State == FfaReadmitEntryRules.RdmState.Claimed || State.State == FfaReadmitEntryRules.RdmState.Binding)
                && room != null && room == State.Room && !_postInFlight && now >= _nextBindRt)
            {
                _nextBindRt = now + FfaReadmitEntryRules.PresencePeriodS;
                int actor = 0;
                try { actor = PhotonNetwork.LocalPlayer.ActorNumber; } catch { }
                if (actor > 0)
                {
                    State.State = FfaReadmitEntryRules.RdmState.Binding;
                    Send("bind", actor, 0);
                }
            }
            bool readmit = FfaAssembly.ReadmitLobby;
            if (!readmit) return;
            int own = 0;
            try { own = PhotonNetwork.LocalPlayer.ActorNumber; } catch { }
            bool granted = false;
            foreach (var g in FfaAssembly.Granted)
                if (g.Actor == own) { granted = true; break; }
            if (FfaReadmitEntryRules.PresenceDue(readmit, room != null, granted, now, _lastPresenceRt))
            {
                var pin = FfaAssembly.ReadmitPin;
                if (pin != null && FfaAssembly.SendPresenceCensus(pin.Lobby)) _lastPresenceRt = now;
            }
        }
    }
}
