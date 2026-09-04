using System;
using System.Globalization;
using System.Text;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Release B §1 — the in-room "vs NAME · last played · H2H · ranked
    /// series" line. One GET /api/v1/h2h/{me}/{opponent} per room
    /// incarnation, aggregates only (the response carries counters, a name
    /// and one timestamp — nothing room-derived). Rendered as a 10 s banner
    /// under the corner HUD label (CompetitiveUI.DrawH2HBanner) and as a
    /// header line on the hold-Tab board (TabStatsOverlay) for the rest of
    /// the sitting.
    ///
    /// Trigger, each Poll tick: a live online room (never PUN offline mode —
    /// InRoom stays true at the post-Sandbox menu, #473b), this seat a
    /// fighter (never a spectator), no ffa_/team_/ovt_ prefix and no cr_ff
    /// room property, exactly two active fighters, and the other fighter
    /// resolved by ResolveOpponent: its actor number, plus the id the line
    /// keys on — for a queue-issued room whose name this client still holds,
    /// the SERVER-ATTESTED opponent (ApiClient.TryGetIssuedOpponent, design
    /// r3 §1.2 MEDIUM: the peer's u_id is peer-controlled); for any other
    /// room, that actor's own u_id property (RoomActors.SteamIdOf, read per
    /// actor every tick, so a replacement opponent is seen as one). Either
    /// way the server answers with ITS name for the id and the line is
    /// labelled with that name; this line is the id's only consumer here.
    ///
    /// Key: the attempt and its result belong to (room incarnation, opponent
    /// actor number, opponent id) — r3 §1.2/1.3 MEDIUM. When the actor or
    /// the id changes, or no single other fighter remains (the opponent
    /// left, a third fighter arrived), the line is cleared and the next
    /// resolvable opponent gets its own request, under the same
    /// one-request-per-key rule; keyGen moves with every such change so a
    /// response for the previous key is discarded.
    ///
    /// Binding: a request captures the Room OBJECT it was sent from, an
    /// incarnation counter bumped on every OnJoinedRoom and Invalidate
    /// (#473b: bind to the object reference, never a name or a boolean) and
    /// the key generation — a response landing after a leave, a rejoin, a
    /// same-named recreation or an opponent change is discarded.
    /// Invalidate() runs first in OnLeftRoom and OnDisconnected.
    ///
    /// Retry: a 401 ends the attempt — ApiClient.HandleSessionReject drops
    /// the refused token if it is still current, and the request is re-sent
    /// once, only after SteamAuth.SessionToken differs from the token that
    /// was refused. One re-send after a transport failure/timeout. 429 and
    /// every other HTTP refusal: Unavailable for this key.
    ///
    /// Log: [H2H] lines carry transitions and counts only — never an id,
    /// never a room name, never a response body.
    /// </summary>
    internal static class H2HSummary
    {
        private enum State { Idle, Loading, Ready, Unavailable }

        internal const float BANNER_SECONDS = 10f;
        private const float TRANSPORT_RETRY_DELAY = 3f;
        private const int NAME_MAX = 24;

        private static State state = State.Idle;
        private static int incarnation;
        private static Photon.Realtime.Room boundRoom;
        private static string refusedToken;
        private static int sessionResends;
        private static int transportRetries;
        private static float notBefore = -1f;
        private static float readyAt = -1f;

        // The key of the current attempt/result under this incarnation:
        // the other fighter's actor number and the id the line keys on
        // ("" until it is known). keyGen moves on every key change and
        // every reset, so a response for a previous key is discarded.
        private static int keyActor = -1;
        private static string keyId = "";
        private static int keyGen;

        // Facts as the server answered them.
        private static string opponentName = "";
        private static int gamesWon, gamesLost, seriesTotal;
        private static bool playedToday;
        private static DateTime? lastPlayedUtc;

        // The display line, built once per Ready and rebuilt only on a
        // catalogue change — both surfaces read it per Repaint (#162).
        private static string line = "";
        private static int lineGen = -1;

        /// <summary>Plugin.OnJoinedRoom: a fresh incarnation. The queue's
        /// retained pairing describes exactly one room — a join to any other
        /// room retires it here.</summary>
        internal static void OnJoinedRoom()
        {
            incarnation++;
            ResetIncarnation();
            try
            {
                var room = Photon.Pun.PhotonNetwork.CurrentRoom;
                ApiClient.RetireIssuedPairUnless(room != null ? room.Name : null);
            }
            catch { }
        }

        /// <summary>Plugin.OnLeftRoom / OnDisconnected, first statement. Any
        /// in-flight response is stale by counter as well as by room
        /// reference after this.</summary>
        internal static void Invalidate()
        {
            incarnation++;
            ResetIncarnation();
        }

        private static void ResetIncarnation()
        {
            ResetAttempt();
            keyActor = -1;
            keyId = "";
        }

        /// <summary>Everything that belongs to one key's attempt and result:
        /// the state machine, its retry budget, the facts and the built line.
        /// keyGen moves so an in-flight response for the old key is
        /// discarded.</summary>
        private static void ResetAttempt()
        {
            keyGen++;
            state = State.Idle;
            boundRoom = null;
            refusedToken = null;
            sessionResends = 0;
            transportRetries = 0;
            notBefore = -1f;
            readyAt = -1f;
            opponentName = "";
            gamesWon = 0; gamesLost = 0; seriesTotal = 0;
            playedToday = false;
            lastPlayedUtc = null;
            line = "";
            lineGen = -1;
        }

        /// <summary>Ticked right after GameStateWatcher.Poll(). Runs in every
        /// state: the key check must see an opponent change while a result
        /// is showing, not only while Idle.</summary>
        internal static void Tick()
        {
            Photon.Realtime.Room room;
            int actor;
            string opp;
            bool attested;
            try
            {
                if (!Photon.Pun.PhotonNetwork.InRoom || Photon.Pun.PhotonNetwork.OfflineMode) { NoteNoOpponent(); return; }
                room = Photon.Pun.PhotonNetwork.CurrentRoom;
                if (room == null || !IsPlainTwoFighterRoom(room)) { NoteNoOpponent(); return; }
                if (!ResolveOpponent(room, out actor, out opp, out attested)) { NoteNoOpponent(); return; }
            }
            catch { return; }

            if (actor != keyActor || !string.Equals(opp, keyId, StringComparison.Ordinal))
            {
                // A different actor, or a different id on the same actor, is
                // a different opponent: the line showing (if any) was his
                // predecessor's. An id arriving on an actor that had none is
                // the resolver completing, not a change — nothing to clear.
                bool changed = keyActor >= 0 && (actor != keyActor || keyId.Length > 0);
                ResetAttempt();
                keyActor = actor;
                keyId = opp;
                if (changed) Plugin.Log.LogInfo("[H2H] opponent changed — line cleared, re-fetching for the new opponent");
            }
            if (state != State.Idle) return;
            if (notBefore > 0f && Time.realtimeSinceStartup < notBefore) return;

            string me = MatchTracker.LocalSteamId;
            // opp is "" until the actor's u_id property arrives.
            if (!IsSteamId64(me) || !IsSteamId64(opp)) return;
            if (string.Equals(me, opp, StringComparison.Ordinal)) return;
            string tok = SteamAuth.SessionToken;
            if (string.IsNullOrEmpty(tok)) return;   // no session yet: the heartbeat mints one
            if (refusedToken != null && string.Equals(tok, refusedToken, StringComparison.Ordinal)) return;

            state = State.Loading;
            boundRoom = room;
            int sentInc = incarnation;
            int sentKey = keyGen;
            Photon.Realtime.Room sentRoom = room;
            string sentTok = tok;
            Plugin.Log.LogInfo(sessionResends + transportRetries == 0
                ? $"[H2H] request sent ({(attested ? "queue-attested" : "room-resolved")} opponent)"
                : $"[H2H] request re-sent (session re-sends {sessionResends}, transport retries {transportRetries})");
            ApiClient.FetchH2HSummary(me, opp, (ok, resp) => OnResponse(ok, resp, sentRoom, sentInc, sentKey, sentTok));
        }

        /// <summary>No single resolvable other fighter right now — the
        /// opponent left, a third fighter arrived, the room stopped being a
        /// plain 1v1, or there is no room. The attempt and its line end here;
        /// the next resolvable opponent starts a new key.</summary>
        private static void NoteNoOpponent()
        {
            if (keyActor < 0 && state == State.Idle) return;
            bool hadLine = state != State.Idle;
            ResetIncarnation();
            if (hadLine) Plugin.Log.LogInfo("[H2H] opponent left or room shape changed — line cleared");
        }

        /// <summary>The other fighter and the id the line keys on. Actor: the
        /// single other active fighter (RoomActors' census). Id: the
        /// server-attested opponent for a queue-issued room this client still
        /// holds the name of (ApiClient.TryGetIssuedOpponent), otherwise the
        /// actor's own u_id property — "" until it arrives. False when there
        /// is not exactly one other fighter.</summary>
        private static bool ResolveOpponent(Photon.Realtime.Room room, out int actor, out string id, out bool attested)
        {
            actor = -1;
            id = "";
            attested = false;
            var others = RoomActors.OtherActiveFighters();
            if (others == null || others.Length != 1 || others[0] == null) return false;
            actor = others[0].ActorNumber;
            string issued;
            if (ApiClient.TryGetIssuedOpponent(room.Name, out issued))
            {
                id = issued;
                attested = true;
            }
            else
            {
                id = RoomActors.SteamIdOf(others[0]) ?? "";
            }
            return true;
        }

        /// <summary>The §1.2 room rule: not a spectator seat, no ffa_/team_/
        /// ovt_ prefix, no cr_ff property, exactly two active fighters
        /// (RoomActors' census — PlayerCount reads 3 with a spectator seat
        /// filled). Same pieces as GameStateWatcher.IsPlainOneVOneForHud
        /// minus its match-started latch: this line belongs to the lobby
        /// too.</summary>
        private static bool IsPlainTwoFighterRoom(Photon.Realtime.Room room)
        {
            if (room == null) return false;
            if (RoomActors.LocalIsSpectator) return false;
            string n = room.Name ?? "";
            if (n.StartsWith("ffa_", StringComparison.Ordinal)
                || n.StartsWith("team_", StringComparison.Ordinal)
                || n.StartsWith("ovt_", StringComparison.Ordinal)) return false;
            if (room.CustomProperties != null && room.CustomProperties.ContainsKey("cr_ff")) return false;
            return RoomActors.ActiveFighterCount() == 2;
        }

        private static void OnResponse(bool ok, string resp, Photon.Realtime.Room sentRoom, int sentInc, int sentKey, string sentTok)
        {
            try
            {
                if (sentInc != incarnation || !ReferenceEquals(sentRoom, boundRoom))
                {
                    Plugin.Log.LogInfo("[H2H] stale response discarded (room changed)");
                    return;
                }
                if (sentKey != keyGen)
                {
                    Plugin.Log.LogInfo("[H2H] stale response discarded (opponent changed)");
                    return;
                }
                if (state != State.Loading) return;

                if (ok)
                {
                    if (Parse(resp))
                    {
                        state = State.Ready;
                        readyAt = Time.realtimeSinceStartup;
                        line = "";
                        lineGen = -1;
                        Plugin.Log.LogInfo(gamesWon + gamesLost == 0 && seriesTotal == 0
                            ? "[H2H] ready: first time"
                            : $"[H2H] ready: games {gamesWon}-{gamesLost}, ranked series {seriesTotal}, last played {(lastPlayedUtc.HasValue ? DaysAgo(lastPlayedUtc.Value) + "d ago" : "never before today")}{(playedToday ? ", also today" : "")}");
                    }
                    else
                    {
                        state = State.Unavailable;
                        Plugin.Log.LogInfo("[H2H] unavailable: unreadable response");
                    }
                    return;
                }

                string err = resp ?? "";
                if (err.StartsWith("HTTP 401", StringComparison.Ordinal))
                {
                    if (sessionResends < 1)
                    {
                        sessionResends++;
                        refusedToken = sentTok;
                        state = State.Idle;
                        Plugin.Log.LogInfo("[H2H] session refused — re-sending once after a newer session is minted");
                    }
                    else
                    {
                        state = State.Unavailable;
                        Plugin.Log.LogInfo("[H2H] unavailable: session refused again");
                    }
                    return;
                }
                if (err.StartsWith("HTTP ", StringComparison.Ordinal) || err == "outdated" || err == "no-consent")
                {
                    state = State.Unavailable;
                    Plugin.Log.LogInfo($"[H2H] unavailable: {StatusOnly(err)}");
                    return;
                }
                // Transport failure or timeout: no status code at all.
                if (transportRetries < 1)
                {
                    transportRetries++;
                    state = State.Idle;
                    notBefore = Time.realtimeSinceStartup + TRANSPORT_RETRY_DELAY;
                    Plugin.Log.LogInfo("[H2H] request failed (transport) — retrying once");
                }
                else
                {
                    state = State.Unavailable;
                    Plugin.Log.LogInfo("[H2H] unavailable: transport failed twice");
                }
            }
            catch (Exception ex)
            {
                state = State.Unavailable;
                Plugin.Log.LogWarning($"[H2H] unavailable: {ex.GetType().Name}");
            }
        }

        /// <summary>"HTTP 429: {...}" → "HTTP 429" — the status only, never
        /// the body.</summary>
        private static string StatusOnly(string err)
        {
            if (string.IsNullOrEmpty(err)) return "request failed";
            int colon = err.IndexOf(':');
            return colon > 0 ? err.Substring(0, colon) : err;
        }

        /// <summary>Flat object, no arrays: the codebase's escape-aware key
        /// readers (ExtractJsonString handles \" and \u escapes; a key
        /// pattern cannot be spoofed from inside a string value because the
        /// value's quotes arrive escaped). Never JsonUtility.</summary>
        private static bool Parse(string json)
        {
            if (string.IsNullOrEmpty(json) || json.IndexOf("\"games_total\":", StringComparison.Ordinal) < 0) return false;
            opponentName = Neutralise(ApiClient.ExtractJsonStringPublic(json, "opponent_display_name"));
            gamesWon = Math.Max(0, ApiClient.ExtractJsonIntPublic(json, "games_won"));
            gamesLost = Math.Max(0, ApiClient.ExtractJsonIntPublic(json, "games_lost"));
            seriesTotal = Math.Max(0, ApiClient.ExtractJsonIntPublic(json, "series_total"));
            playedToday = ApiClient.ExtractJsonBoolPublic(json, "played_today");
            lastPlayedUtc = null;
            string ts = ApiClient.ExtractJsonStringPublic(json, "last_played_at");
            if (!string.IsNullOrEmpty(ts))
            {
                DateTime dt;
                if (DateTime.TryParse(ts, CultureInfo.InvariantCulture,
                        DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal, out dt))
                    lastPlayedUtc = dt;
            }
            return true;
        }

        /// <summary>FfaSafeRich's treatment for an IMGUI label: control
        /// characters (C0, C1 incl. U+0085, U+2028/2029) flatten to spaces
        /// so the line stays one line; the surfaces draw it with
        /// richText=false, which is IMGUI's equivalent of the entity escape
        /// (IMGUI never decodes entities, so escaping would print them).
        /// Truncated to NAME_MAX.</summary>
        private static string Neutralise(string value)
        {
            if (string.IsNullOrEmpty(value)) return "";
            var sb = new StringBuilder(value.Length);
            foreach (char ch in value)
                sb.Append(ch < ' ' || (ch >= (char)0x7F && ch <= (char)0x9F)
                          || ch == (char)0x2028 || ch == (char)0x2029 ? ' ' : ch);
            string s = sb.ToString().Trim();
            return s.Length > NAME_MAX ? s.Substring(0, NAME_MAX) : s;
        }

        private static bool IsSteamId64(string s)
        {
            if (string.IsNullOrEmpty(s) || s.Length != 17) return false;
            for (int i = 0; i < s.Length; i++)
                if (s[i] < '0' || s[i] > '9') return false;
            return true;
        }

        private static int DaysAgo(DateTime utc)
        {
            int days = (int)(DateTime.UtcNow.Date - utc.Date).TotalDays;
            return days < 1 ? 1 : days;
        }

        // ── display ─────────────────────────────────────────────────────

        /// <summary>The corner-HUD banner text for the first BANNER_SECONDS
        /// after Ready; "" otherwise. Empty again if the room stops being a
        /// plain two-fighter room.</summary>
        internal static string BannerLine
        {
            get
            {
                if (state != State.Ready || readyAt < 0f) return "";
                if (Time.realtimeSinceStartup - readyAt > BANNER_SECONDS) return "";
                return CurrentLine();
            }
        }

        /// <summary>The hold-Tab header line for the rest of the sitting;
        /// "" until Ready or once the room is no longer a plain 1v1.</summary>
        internal static string TabLine
        {
            get
            {
                if (state != State.Ready) return "";
                return CurrentLine();
            }
        }

        private static string CurrentLine()
        {
            try
            {
                if (!IsPlainTwoFighterRoom(Photon.Pun.PhotonNetwork.CurrentRoom)) return "";
                if (line.Length > 0 && lineGen == I18n.CatalogueGeneration) return line;
                lineGen = I18n.CatalogueGeneration;
                line = BuildLine();
                return line;
            }
            catch { return ""; }
        }

        private static string BuildLine()
        {
            string name = string.IsNullOrEmpty(opponentName) ? I18n.Tr("Unknown player") : opponentName;
            if (gamesWon + gamesLost == 0 && seriesTotal == 0)
                return I18n.TrF("First time playing {0}", name);
            string core;
            if (!lastPlayedUtc.HasValue)
                core = playedToday
                    ? I18n.TrF("First played today · H2H {0}-{1} · Ranked series {2}", gamesWon, gamesLost, seriesTotal)
                    : I18n.TrF("H2H {0}-{1} · Ranked series {2}", gamesWon, gamesLost, seriesTotal);
            else if (playedToday)
                core = I18n.TrF("Last played {0} · also played today · H2H {1}-{2} · Ranked series {3}",
                    Ago(lastPlayedUtc.Value), gamesWon, gamesLost, seriesTotal);
            else
                core = I18n.TrF("Last played {0} · H2H {1}-{2} · Ranked series {3}",
                    Ago(lastPlayedUtc.Value), gamesWon, gamesLost, seriesTotal);
            return I18n.TrF("vs {0}", name) + "  ·  " + core;
        }

        /// <summary>Calendar days in UTC: the server's timestamp is strictly
        /// before the caller's current UTC day, so this is at least
        /// "yesterday".</summary>
        private static string Ago(DateTime utc)
        {
            int days = DaysAgo(utc);
            if (days == 1) return I18n.Tr("yesterday");
            if (days < 14) return I18n.TrF("{0} days ago", days);
            if (days < 60) return I18n.TrF("{0} weeks ago", days / 7);
            if (days < 365) return I18n.TrF("{0} months ago", days / 30);
            if (days < 730) return I18n.Tr("a year ago");
            return I18n.TrF("{0} years ago", days / 365);
        }
    }
}
