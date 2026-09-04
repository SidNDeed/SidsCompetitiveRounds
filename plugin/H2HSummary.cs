using System;
using System.Text;
using BepInEx.Configuration;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Release B §1 — the in-room "vs NAME · last played · H2H · ranked
    /// series" line. One GET /api/v1/h2h/{me}/{opponent} per room
    /// incarnation, aggregates only (the response carries counters, a name,
    /// one timestamp and the server's day count for it — nothing
    /// room-derived). Rendered as a 10 s banner under the corner HUD label
    /// (CompetitiveUI.DrawH2HBanner) and as a header line on the hold-Tab
    /// board (TabStatsOverlay) for the rest of the sitting.
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
    /// The attested id names a PAIR, not a seat (review r6 MEDIUM): it is
    /// bound to the first (incarnation, other-fighter actor) it is consumed
    /// for — H2HRules.ResolveIssued, state held on ApiClient's issued pair —
    /// and any other actor or incarnation in that room gets no line at all,
    /// never the advertised id: a replacement fighter would otherwise be
    /// shown the original opponent's record under the original's name.
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
    /// Retry (H2HRules.OnFailure, review r6 LOW): a 401 ends the attempt —
    /// ApiClient.HandleSessionReject drops the refused token if it is still
    /// current, and the request is re-sent once, only after
    /// SteamAuth.SessionToken differs from the token that was refused. One
    /// re-send after a transport failure/timeout, 6 s later — beyond the
    /// server's 5 s per-pair debounce, which the lost request may have
    /// armed. A 429 is retried once, after the body's retry_after plus 1 s
    /// (6 s without one, 10 s at most). Every other HTTP refusal:
    /// Unavailable for this key. At most four requests per key.
    ///
    /// Relative day (review r6 LOW): "yesterday / N days ago" renders the
    /// server's last_played_days_ago — whole UTC days on the server's clock
    /// — never a client-clock subtraction; a response without that integer
    /// states no day.
    ///
    /// Log: [H2H] lines carry transitions and counts only — never an id,
    /// never a room name, never a response body.
    /// </summary>
    internal static class H2HSummary
    {
        private enum State { Idle, Loading, Ready, Unavailable }

        internal const float BANNER_SECONDS = 10f;
        private const int NAME_MAX = 24;

        private static State state = State.Idle;
        private static int incarnation;
        private static Photon.Realtime.Room boundRoom;
        private static string refusedToken;
        private static H2HRules.RetryBudget budget;
        private static float notBefore = -1f;
        private static float readyAt = -1f;

        // The key of the current attempt/result under this incarnation:
        // the other fighter's actor number and the id the line keys on
        // ("" until it is known). keyGen moves on every key change and
        // every reset, so a response for a previous key is discarded.
        private static int keyActor = -1;
        private static string keyId = "";
        private static int keyGen;

        // One "no line for this fighter" log per incarnation; the
        // suppression itself is re-derived every tick.
        private static bool suppressionLogged;

        // Facts as the server answered them.
        private static string opponentName = "";
        private static int gamesWon, gamesLost, seriesTotal;
        private static bool playedToday;
        private static bool hasEarlierHistory;     // last_played_at present
        private static int? lastPlayedDaysAgo;     // its server-computed day count

        // The display line, built once per Ready and rebuilt only on a
        // catalogue change — both surfaces read it per Repaint (#162).
        private static string line = "";
        private static int lineGen = -1;

        private static bool startupDone;
        private static ConfigEntry<bool> selfTestLever;

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
            ResetKey();
            suppressionLogged = false;
        }

        /// <summary>The current key and everything under it. The incarnation
        /// stands, and so does the issued pair's binding (ApiClient holds
        /// it): a fighter the pairing was not bound to stays unresolved
        /// through any number of key resets.</summary>
        private static void ResetKey()
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
            budget = default(H2HRules.RetryBudget);
            notBefore = -1f;
            readyAt = -1f;
            opponentName = "";
            gamesWon = 0; gamesLost = 0; seriesTotal = 0;
            playedToday = false;
            hasEarlierHistory = false;
            lastPlayedDaysAgo = null;
            line = "";
            lineGen = -1;
        }

        /// <summary>Ticked right after GameStateWatcher.Poll(). Runs in every
        /// state: the key check must see an opponent change while a result
        /// is showing, not only while Idle.</summary>
        internal static void Tick()
        {
            if (!startupDone) EnsureStartup();
            Photon.Realtime.Room room;
            int actor;
            string opp;
            bool attested, suppressed;
            try
            {
                if (!Photon.Pun.PhotonNetwork.InRoom || Photon.Pun.PhotonNetwork.OfflineMode) { NoteNoOpponent(false); return; }
                room = Photon.Pun.PhotonNetwork.CurrentRoom;
                if (room == null || !IsPlainTwoFighterRoom(room)) { NoteNoOpponent(false); return; }
                if (!ResolveOpponent(room, out actor, out opp, out attested, out suppressed)) { NoteNoOpponent(suppressed); return; }
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
            Plugin.Log.LogInfo(budget.Total == 0
                ? $"[H2H] request sent ({(attested ? "queue-attested" : "room-resolved")} opponent)"
                : $"[H2H] request re-sent (session re-sends {budget.SessionResends}, transport retries {budget.TransportRetries}, debounce retries {budget.DebounceRetries})");
            ApiClient.FetchH2HSummary(me, opp, (ok, resp) => OnResponse(ok, resp, sentRoom, sentInc, sentKey, sentTok));
        }

        /// <summary>No single resolvable other fighter right now — the
        /// opponent left, a third fighter arrived, the room stopped being a
        /// plain 1v1, there is no room, or (suppressed) the other fighter in
        /// a queue-issued room is not the one the pairing was bound to. The
        /// attempt and its line end here; the next resolvable opponent
        /// starts a new key.</summary>
        private static void NoteNoOpponent(bool suppressed)
        {
            if (suppressed && !suppressionLogged)
            {
                suppressionLogged = true;
                Plugin.Log.LogInfo("[H2H] other fighter is not the one the queue paired this seat with — no line for this fighter");
            }
            if (keyActor < 0 && state == State.Idle) return;
            bool hadLine = state != State.Idle;
            ResetKey();
            if (hadLine) Plugin.Log.LogInfo(suppressed ? "[H2H] line cleared" : "[H2H] opponent left or room shape changed — line cleared");
        }

        /// <summary>The other fighter and the id the line keys on. Actor: the
        /// single other active fighter (RoomActors' census). Id: the
        /// server-attested opponent for a queue-issued room this client still
        /// holds the name of (ApiClient.TryGetIssuedOpponent — Attested only
        /// for the actor and incarnation the pairing is bound to), otherwise
        /// the actor's own u_id property — "" until it arrives. False when
        /// there is not exactly one other fighter, or (suppressed = true)
        /// when the queue-issued room's other fighter is not the bound one:
        /// then the advertised id is not consulted (review r6 MEDIUM).</summary>
        private static bool ResolveOpponent(Photon.Realtime.Room room, out int actor, out string id, out bool attested, out bool suppressed)
        {
            actor = -1;
            id = "";
            attested = false;
            suppressed = false;
            var others = RoomActors.OtherActiveFighters();
            if (others == null || others.Length != 1 || others[0] == null) return false;
            actor = others[0].ActorNumber;
            string issued;
            switch (ApiClient.TryGetIssuedOpponent(room.Name, incarnation, actor, out issued))
            {
                case H2HRules.IssuedOpponent.Attested:
                    id = issued;
                    attested = true;
                    return true;
                case H2HRules.IssuedOpponent.Suppressed:
                    suppressed = true;
                    return false;
                default:
                    id = RoomActors.SteamIdOf(others[0]) ?? "";
                    return true;
            }
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
                            : $"[H2H] ready: games {gamesWon}-{gamesLost}, ranked series {seriesTotal}, last played {(lastPlayedDaysAgo.HasValue ? lastPlayedDaysAgo.Value + "d ago" : hasEarlierHistory ? "before today (no day count)" : "never before today")}{(playedToday ? ", also today" : "")}");
                    }
                    else
                    {
                        state = State.Unavailable;
                        Plugin.Log.LogInfo("[H2H] unavailable: unreadable response");
                    }
                    return;
                }

                string err = resp ?? "";
                bool http = err.StartsWith("HTTP ", StringComparison.Ordinal);
                int retryAfter = err.StartsWith("HTTP 429", StringComparison.Ordinal)
                    ? ApiClient.ExtractJsonIntPublic(err, "retry_after") : 0;
                float delay;
                switch (H2HRules.OnFailure(err, retryAfter, ref budget, out delay))
                {
                    case H2HRules.FailureAction.ResendAfterNewSession:
                        refusedToken = sentTok;
                        state = State.Idle;
                        Plugin.Log.LogInfo("[H2H] session refused — re-sending once after a newer session is minted");
                        return;
                    case H2HRules.FailureAction.RetryAfterDelay:
                        state = State.Idle;
                        notBefore = Time.realtimeSinceStartup + delay;
                        Plugin.Log.LogInfo($"[H2H] {(http ? StatusOnly(err) : "request failed (transport)")} — retrying once in {delay:0.#}s");
                        return;
                    default:
                        state = State.Unavailable;
                        Plugin.Log.LogInfo(http || err == "outdated" || err == "no-consent"
                            ? $"[H2H] unavailable: {StatusOnly(err)}"
                            : "[H2H] unavailable: transport failed twice");
                        return;
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
            // A string-valued last_played_at (the string reader answers "" for
            // null or absent) says a counted game ended before the caller's
            // UTC day; how many days before is the server's integer, never a
            // subtraction against this clock.
            hasEarlierHistory = !string.IsNullOrEmpty(ApiClient.ExtractJsonStringPublic(json, "last_played_at"));
            lastPlayedDaysAgo = H2HRules.DaysAgo(ApiClient.ExtractJsonIntPublic(json, "last_played_days_ago"));
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

        /// <summary>Once per process, from the first Tick: binds
        /// [H2H] H2HRulesSelfTest through the plugin's ConfigFile (the shape
        /// of LagNotices' lever) and runs H2HRules.SelfTest when it is true.
        /// The run logs and does nothing else.</summary>
        private static void EnsureStartup()
        {
            startupDone = true;
            try
            {
                ConfigFile cf = Plugin.ConfigFileForLevers;
                if (cf != null)
                    selfTestLever = cf.Bind(
                        "H2H", "H2HRulesSelfTest",
                        false,
                        "Development only: once at startup, run the head-to-head line's decision rules (queue attestation binding, retry policy, relative-day copy) over canned inputs and log one [H2H] selftest line per case plus a summary line. Nothing is shown, sent or persisted.");
            }
            catch (Exception ex) { Plugin.Log?.LogWarning("[H2H] self-test bind failed: " + ex.Message); }
            bool run = false;
            try { run = selfTestLever != null && selfTestLever.Value; } catch { }
            if (!run) return;
            try
            {
                int fail;
                H2HRules.SelfTest(s => Plugin.Log?.LogInfo(s), out fail);
            }
            catch (Exception ex) { Plugin.Log?.LogWarning("[H2H] self-test failed to run: " + ex.GetType().Name); }
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

        /// <summary>H2HRules.ShapeFor picks the string; the strings stay here
        /// as literals for the catalogue extractor.</summary>
        private static string BuildLine()
        {
            string name = string.IsNullOrEmpty(opponentName) ? I18n.Tr("Unknown player") : opponentName;
            string core;
            switch (H2HRules.ShapeFor(gamesWon + gamesLost == 0 && seriesTotal == 0, hasEarlierHistory, lastPlayedDaysAgo, playedToday))
            {
                case H2HRules.LineShape.FirstTime:
                    return I18n.TrF("First time playing {0}", name);
                case H2HRules.LineShape.FirstPlayedToday:
                    core = I18n.TrF("First played today · H2H {0}-{1} · Ranked series {2}", gamesWon, gamesLost, seriesTotal);
                    break;
                case H2HRules.LineShape.LastPlayedAlsoToday:
                    core = I18n.TrF("Last played {0} · also played today · H2H {1}-{2} · Ranked series {3}",
                        Ago(lastPlayedDaysAgo.Value), gamesWon, gamesLost, seriesTotal);
                    break;
                case H2HRules.LineShape.LastPlayed:
                    core = I18n.TrF("Last played {0} · H2H {1}-{2} · Ranked series {3}",
                        Ago(lastPlayedDaysAgo.Value), gamesWon, gamesLost, seriesTotal);
                    break;
                default:
                    core = I18n.TrF("H2H {0}-{1} · Ranked series {2}", gamesWon, gamesLost, seriesTotal);
                    break;
            }
            return I18n.TrF("vs {0}", name) + "  ·  " + core;
        }

        /// <summary>The server's whole-UTC-day count through the catalogue;
        /// H2HRules.AgoBucket picks the string (1 is "yesterday").</summary>
        private static string Ago(int days)
        {
            int n;
            switch (H2HRules.AgoBucket(days, out n))
            {
                case H2HRules.AgoKind.Yesterday: return I18n.Tr("yesterday");
                case H2HRules.AgoKind.Days: return I18n.TrF("{0} days ago", n);
                case H2HRules.AgoKind.Weeks: return I18n.TrF("{0} weeks ago", n);
                case H2HRules.AgoKind.Months: return I18n.TrF("{0} months ago", n);
                case H2HRules.AgoKind.Year: return I18n.Tr("a year ago");
                default: return I18n.TrF("{0} years ago", n);
            }
        }
    }
}
