using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// Stage 2 HTTP shapes: request bodies, answer parsers and the hold-open
    /// canonical. Pure (no Unity, Photon or Harmony), compiled by the harness.
    ///
    /// THE SEAM (lane notes row 1). Every call needs ApiClient's shared request
    /// path and its HMAC helper, which are private to an FFA-owned file. This
    /// file therefore carries two delegates, <see cref="Send"/> and
    /// <see cref="Sign"/>, which ApiClient.BindTeamHold binds at Initialize
    /// (Send through <see cref="Bound"/>: no session token, no send). Unbound,
    /// without a token, or answered 401, a call answers <see cref="NoTransport"/>
    /// and every caller ends toward today (V3:157). Answers are parsed by manual string splitting:
    /// JsonUtility silently fails on nested arrays.
    /// </summary>
    internal static class TeamHoldNet
    {
        /// <summary>method, path, JSON body (null for GET), completion(status, body).</summary>
        internal delegate void Transport(string method, string path, string body, Action<int, string> done);

        /// <summary>The build HMAC over a canonical, hex.</summary>
        internal delegate string Signer(string canonical);

        internal static Transport Send;
        internal static Signer Sign;

        /// <summary>The status an unbound or throwing transport answers.</summary>
        internal const int NoTransport = 0;

        internal const string PathGameStart = "/api/v1/match/game/start";
        internal const string PathBeat = "/api/v1/match/hold/beat";
        internal const string PathOpen = "/api/v1/match/hold/open";
        internal const string PathMine = "/api/v1/match/hold/mine";

        // KX9: every query and body field below is the server request
        // model's (match_hold.py; field table in the refit notes).
        internal static string PathMineFor(string steamId) { return PathMine + "?steam_id=" + Uri.EscapeDataString(steamId ?? ""); }
        internal static string PathState(string holdId, string steamId)
        {
            return "/api/v1/match/hold/" + Uri.EscapeDataString(holdId ?? "") + "/state?steam_id=" + Uri.EscapeDataString(steamId ?? "");
        }
        internal static string PathEnd(string holdId) { return "/api/v1/match/hold/" + Uri.EscapeDataString(holdId ?? "") + "/end"; }
        internal static string PathClaim(string holdId) { return "/api/v1/match/hold/" + Uri.EscapeDataString(holdId ?? "") + "/claim"; }
        internal static string PathBind(string holdId) { return "/api/v1/match/hold/" + Uri.EscapeDataString(holdId ?? "") + "/bind"; }
        internal static string PathEntered(string holdId) { return "/api/v1/match/hold/" + Uri.EscapeDataString(holdId ?? "") + "/entered"; }

        internal static string PathByRoom(string room, string g, string steamId)
        {
            return "/api/v1/match/hold/by-room?room=" + Uri.EscapeDataString(room ?? "") + "&game_id=" + Uri.EscapeDataString(g ?? "")
                   + "&steam_id=" + Uri.EscapeDataString(steamId ?? "");
        }

        /// <summary>One call. Unbound or throwing transport: NoTransport, at once.</summary>
        internal static void Call(string method, string path, string body, Action<int, string> done)
        {
            var t = Send;
            if (t == null) { done(NoTransport, "no-transport"); return; }
            try { t(method, path, body, done); }
            catch { done(NoTransport, "transport-threw"); }
        }

        // ── The binding (KX1) ──────────────────────────────────────────────

        /// <summary>The shared request path of ApiClient as KX1 hands it in:
        /// method, path, JSON body (null for GET), answer(ok, text), where text
        /// is the body on success and ApiClient.FormatRequestError's
        /// "HTTP &lt;code&gt;: &lt;body&gt;" on a refusal (anything else: no answer).</summary>
        internal delegate void SharedSend(string method, string path, string body, Action<bool, string> answer);

        /// <summary>The body a 401 maps to; the status is NoTransport, so the
        /// caller ends toward today exactly as with no transport (V3:157).</summary>
        internal const string SessionRequired = "session_required";

        /// <summary>The bound transport. A call goes out only when the session
        /// token is held AND the shared path would carry it on this route
        /// (<paramref name="carries"/>: ApiClient's credentialed-transport
        /// rule); otherwise it answers NoTransport at once and nothing is sent,
        /// because every hold route requires a verified session. Each answer
        /// is mapped once by <see cref="MapShared"/>.</summary>
        internal static Transport Bound(Func<string> token, Func<string, bool> carries, SharedSend shared)
        {
            if (token == null || carries == null || shared == null) return null;
            return (method, path, body, done) =>
            {
                bool carried;
                try { carried = !string.IsNullOrEmpty(token()) && carries(path); } catch { carried = false; }
                if (!carried) { done(NoTransport, "no-session"); return; }
                bool answered = false;
                shared(method, path, body, (ok, text) =>
                {
                    if (answered) return;
                    answered = true;
                    int st; string b;
                    MapShared(ok, text, out st, out b);
                    done(st, b);
                });
            };
        }

        /// <summary>The shared path's (ok, text) as (status, body): success is
        /// 200 with the body; "HTTP &lt;code&gt;: &lt;body&gt;" is that code with its
        /// body (a trailing Retry-After line dropped); a 401 is NoTransport with
        /// <see cref="SessionRequired"/>; anything else (a timeout, a local
        /// refusal) is NoTransport with the text.</summary>
        internal static void MapShared(bool ok, string text, out int status, out string body)
        {
            if (ok) { status = 200; body = text ?? ""; return; }
            status = NoTransport;
            body = text ?? "";
            if (string.IsNullOrEmpty(text) || !text.StartsWith("HTTP ", StringComparison.Ordinal)) return;
            int colon = text.IndexOf(':', 5);
            int code;
            if (colon <= 5 || !int.TryParse(text.Substring(5, colon - 5).Trim(), NumberStyles.Integer, CultureInfo.InvariantCulture, out code)) return;
            if (code == 401) { body = SessionRequired; return; }
            string rest = text.Substring(colon + 1).TrimStart();
            int ra = rest.IndexOf("\nRetry-After:", StringComparison.Ordinal);
            status = code;
            body = ra >= 0 ? rest.Substring(0, ra) : rest;
        }

        /// <summary>The pin of S1 step 2 from a join answer naming the room:
        /// the team ready_join or the 1v2 poll ready_join. `hold` is read from
        /// the answer; an answer without it pins false (unflagged: today).
        /// A written pin never changes for its room (TeamHoldRules.PinRoom).</summary>
        internal static void PinFromJoin(string answer, string mode, string room, string seriesId, IEnumerable<string> roster)
        {
            TeamHoldRules.PinRoom(room, BoolField(answer, "hold"), mode, seriesId, roster);
        }

        /// <summary>The hold-open canonical (RJS-L3), new and separate from the
        /// team-DC, team-report and 1v2 canonicals, which stay as signed today.</summary>
        internal static string HoldOpenCanonical(string mode, string room, string g, string heldSteam, int slot, int team, string openerSteam)
        {
            return "hold-open:" + mode + ":" + room + ":" + g + ":" + heldSteam + ":" + I(slot) + ":" + I(team) + ":" + openerSteam;
        }

        /// <summary>The signature, or null when no signer is bound (the open is
        /// then not sent: toward today).</summary>
        internal static string SignOrNull(string canonical)
        {
            var s = Sign;
            if (s == null) return null;
            try { return s(canonical); } catch { return null; }
        }

        // ── bodies ─────────────────────────────────────────────────────────

        private static string I(int v) { return v.ToString(CultureInfo.InvariantCulture); }

        internal static string Q(string s)
        {
            if (s == null) return "null";
            var sb = new StringBuilder("\"");
            foreach (char c in s)
            {
                if (c == '"' || c == '\\') sb.Append('\\').Append(c);
                else if (c < 0x20) sb.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                else sb.Append(c);
            }
            return sb.Append('"').ToString();
        }

        // KX9: each body is its server request model, field for field
        // (match_hold.py at the fix 1 author tip): GameStartReq, BeatReq,
        // HoldOpenReq, HoldEndReq, HoldClaimReq, HoldBindReq, HoldEnteredReq.
        // steam_id is the caller's own id; every route also carries the
        // session token through the KX1 binding.

        internal static string GameStartBody(string steamId, string mode, string seriesId, string room, string prevG)
        {
            return "{\"steam_id\":" + Q(steamId) + ",\"mode\":" + Q(mode) + ",\"series_id\":" + Q(seriesId)
                   + ",\"room\":" + Q(room) + ",\"prev_game\":" + Q(prevG) + "}";
        }

        internal static string BeatBody(string steamId, string mode, string seriesId, string room, int actor,
                                        IList<KeyValuePair<int, string>> seen, string boundaryDigest)
        {
            var sb = new StringBuilder("{\"steam_id\":").Append(Q(steamId)).Append(",\"mode\":").Append(Q(mode))
                .Append(",\"series_id\":").Append(Q(seriesId))
                .Append(",\"room\":").Append(Q(room)).Append(",\"actor\":").Append(I(actor)).Append(",\"seen\":[");
            for (int i = 0; seen != null && i < seen.Count; i++)
            {
                if (i > 0) sb.Append(',');
                sb.Append("{\"actor\":").Append(I(seen[i].Key)).Append(",\"u_id\":").Append(Q(seen[i].Value)).Append('}');
            }
            return sb.Append("],\"boundary_digest\":").Append(Q(boundaryDigest)).Append('}').ToString();
        }

        /// <summary>HoldOpenReq: the M1 exact slot and team, the M6 request
        /// id, the M7 point snapshot at the drop (team holds require it), and
        /// the build HMAC over the hold-open canonical as `hmac`.</summary>
        internal static string OpenBody(string requestId, string mode, string room, string g, string heldSteam, int slot, int team,
                                        string openerSteam, int t1Points, int t2Points, string sig)
        {
            return "{\"request_id\":" + Q(requestId) + ",\"opener_steam_id\":" + Q(openerSteam) + ",\"mode\":" + Q(mode)
                   + ",\"room\":" + Q(room) + ",\"game_id\":" + Q(g)
                   + ",\"held_steam_id\":" + Q(heldSteam) + ",\"slot\":" + I(slot) + ",\"team\":" + I(team)
                   + ",\"t1_points\":" + I(t1Points) + ",\"t2_points\":" + I(t2Points)
                   + ",\"hmac\":" + Q(sig) + "}";
        }

        /// <summary>The server's END_REASONS (match_hold.py): a reason outside
        /// it is refused with 400, so every local reason is mapped into it.</summary>
        internal static readonly string[] EndReasons = {
            "refused", "no_answer", "second_departure", "ceiling", "survivor_leave",
            "token_refused", "snapshot_failed", "registration_refused",
            "activation_timeout", "entry_refused", "bind_timeout",
        };

        /// <summary>A writer reason as the server reads it: itself when it is
        /// one of END_REASONS, its word before ':' when that is ("refused:x"),
        /// else "refused".</summary>
        internal static string EndReasonFor(string local)
        {
            if (string.IsNullOrEmpty(local)) return "refused";
            if (Array.IndexOf(EndReasons, local) >= 0) return local;
            int i = local.IndexOf(':');
            if (i > 0 && Array.IndexOf(EndReasons, local.Substring(0, i)) >= 0) return local.Substring(0, i);
            return "refused";
        }

        /// <summary>The returner's end, by the route stage that failed.</summary>
        internal static string ReturnEndReason(string stage, string why)
        {
            switch (stage)
            {
                case "Token": return "token_refused";
                case "Snapshot": return "snapshot_failed";
                case "Register": return "registration_refused";
                case "Activate": return "activation_timeout";
                case "Ended": return "activation_timeout";
                case "Bind": return why == "timeout" ? "bind_timeout" : "entry_refused";
                default: return "entry_refused";
            }
        }

        internal static string EndBody(string steamId, string reason)
        {
            return "{\"steam_id\":" + Q(steamId) + ",\"reason\":" + Q(EndReasonFor(reason)) + "}";
        }
        internal static string ClaimBody(string steamId) { return "{\"steam_id\":" + Q(steamId) + "}"; }
        internal static string BindBody(string steamId, int actor, string region)
        {
            return "{\"steam_id\":" + Q(steamId) + ",\"actor\":" + I(actor) + ",\"region\":" + Q(region) + "}";
        }
        internal static string EnteredBody(string steamId, string g, int actor)
        {
            return "{\"steam_id\":" + Q(steamId) + ",\"game_id\":" + Q(g) + ",\"actor\":" + I(actor) + "}";
        }

        // ── answer parsing (manual) ────────────────────────────────────────

        /// <summary>The raw token after "key": in a flat JSON object: a string
        /// (unescaped), a number, true, false or null. Null when absent.</summary>
        internal static string Field(string json, string key)
        {
            if (string.IsNullOrEmpty(json) || string.IsNullOrEmpty(key)) return null;
            string pat = "\"" + key + "\"";
            int at = 0;
            while (true)
            {
                int k = json.IndexOf(pat, at, StringComparison.Ordinal);
                if (k < 0) return null;
                int i = k + pat.Length;
                while (i < json.Length && char.IsWhiteSpace(json[i])) i++;
                if (i >= json.Length || json[i] != ':') { at = k + 1; continue; }
                i++;
                while (i < json.Length && char.IsWhiteSpace(json[i])) i++;
                if (i >= json.Length) return null;
                if (json[i] == '"')
                {
                    var sb = new StringBuilder();
                    for (int j = i + 1; j < json.Length; j++)
                    {
                        char c = json[j];
                        if (c == '\\' && j + 1 < json.Length)
                        {
                            char e = json[++j];
                            if (e == 'n') sb.Append('\n'); else if (e == 't') sb.Append('\t');
                            else if (e == 'u' && j + 4 < json.Length)
                            {
                                int code;
                                if (int.TryParse(json.Substring(j + 1, 4), NumberStyles.HexNumber, CultureInfo.InvariantCulture, out code)) sb.Append((char)code);
                                j += 4;
                            }
                            else sb.Append(e);
                            continue;
                        }
                        if (c == '"') return sb.ToString();
                        sb.Append(c);
                    }
                    return null;
                }
                int end = i;
                while (end < json.Length && json[end] != ',' && json[end] != '}' && json[end] != ']' && !char.IsWhiteSpace(json[end])) end++;
                string raw = json.Substring(i, end - i);
                return raw == "null" ? null : raw;
            }
        }

        internal static int IntField(string json, string key, int dflt)
        {
            int v;
            string s = Field(json, key);
            return s != null && int.TryParse(s, NumberStyles.Integer, CultureInfo.InvariantCulture, out v) ? v : dflt;
        }

        internal static bool BoolField(string json, string key)
        {
            string s = Field(json, key);
            return s == "true" || s == "1";
        }

        /// <summary>A two-integer JSON array `"key": [a, b]` (the server's
        /// series_tally); false when absent, null or not two integers.</summary>
        internal static bool IntPairField(string json, string key, out int a, out int b)
        {
            a = -1; b = -1;
            if (string.IsNullOrEmpty(json)) return false;
            string pat = "\"" + key + "\"";
            int k = json.IndexOf(pat, StringComparison.Ordinal);
            if (k < 0) return false;
            int i = k + pat.Length;
            while (i < json.Length && char.IsWhiteSpace(json[i])) i++;
            if (i >= json.Length || json[i] != ':') return false;
            i++;
            while (i < json.Length && char.IsWhiteSpace(json[i])) i++;
            if (i >= json.Length || json[i] != '[') return false;
            int end = json.IndexOf(']', i);
            if (end < 0) return false;
            var parts = json.Substring(i + 1, end - i - 1).Split(',');
            if (parts.Length != 2) return false;
            a = TeamHoldRules.ParseInt(parts[0].Trim(), -1);
            b = TeamHoldRules.ParseInt(parts[1].Trim(), -1);
            return a >= 0 && b >= 0;
        }

        internal sealed class OpenAnswer
        {
            internal bool Opened;
            internal string HoldId;
            internal int Seq;
            internal int HoldS;
            internal string Reason;
        }

        /// <summary>`opened` with hold_id, seq and hold_s, or `refused` with a
        /// reason, in the answer's `status` field (the server half's name).</summary>
        internal static bool TryParseOpen(int status, string body, out OpenAnswer a)
        {
            a = null;
            if (status != 200 || string.IsNullOrEmpty(body)) return false;
            string outcome = Field(body, "status");
            if (outcome == "opened")
            {
                a = new OpenAnswer { Opened = true, HoldId = Field(body, "hold_id"), Seq = IntField(body, "seq", -1), HoldS = IntField(body, "hold_s", 0) };
                return !string.IsNullOrEmpty(a.HoldId) && a.Seq >= 0 && a.HoldS > 0;
            }
            if (outcome == "refused") { a = new OpenAnswer { Opened = false, Reason = Field(body, "reason") ?? "" }; return true; }
            return false;
        }

        internal sealed class StateAnswer
        {
            internal string HoldId;
            internal string G;
            internal char State;
            internal int Seq;
            internal int DeadlineS;
            internal int BoundActor;
            internal bool Closed;
            internal string ClosedReason;
            internal string Verifier;
        }

        /// <summary>The hold row as the server answers it to a series member.
        /// `state` is one of opened, claimed, bound, entered, closed (the
        /// server half's words, match_hold.py _state_word).</summary>
        internal static bool TryParseState(int status, string body, out StateAnswer a)
        {
            a = null;
            if (status != 200 || string.IsNullOrEmpty(body)) return false;
            string st = Field(body, "state");
            char c;
            switch (st)
            {
                case "opened": c = 'o'; break;
                case "claimed": c = 'c'; break;
                case "bound": c = 'b'; break;
                case "entered": c = 'e'; break;
                case "closed": c = 'x'; break;
                default: return false;
            }
            a = new StateAnswer
            {
                HoldId = Field(body, "hold_id"), G = Field(body, "game_id"), State = c, Seq = IntField(body, "seq", -1),
                DeadlineS = IntField(body, "deadline_s", 0), BoundActor = IntField(body, "bound_actor", 0),
                Closed = Field(body, "closed_at") != null, ClosedReason = Field(body, "closed_reason"), Verifier = Field(body, "verifier"),
            };
            if (c == 'x' && !a.Closed) return false;
            return !string.IsNullOrEmpty(a.HoldId) && a.Seq >= 0;
        }

        internal sealed class MineAnswer
        {
            internal bool Readmissible;
            internal string HoldId;
            internal int N;
            internal string Mode;
            internal string Room;
            internal string Region;
            internal int Slot = -1;
            internal int Team = -1;
            internal int HoldS;
            internal int W0, W1;
        }

        /// <summary>The discovery answer; `series_tally` is the array [w0, w1].</summary>
        internal static bool TryParseMine(int status, string body, out MineAnswer a)
        {
            a = null;
            if (status != 200 || string.IsNullOrEmpty(body)) return false;
            a = new MineAnswer { Readmissible = BoolField(body, "readmissible") };
            if (!a.Readmissible) return true;
            a.HoldId = Field(body, "hold_id"); a.N = IntField(body, "n", 0); a.Mode = Field(body, "mode");
            a.Room = Field(body, "room_name"); a.Region = Field(body, "room_region");
            a.Slot = IntField(body, "slot", -1); a.Team = IntField(body, "team", -1); a.HoldS = IntField(body, "hold_s", 0);
            IntPairField(body, "series_tally", out a.W0, out a.W1);
            bool ok = !string.IsNullOrEmpty(a.HoldId) && !string.IsNullOrEmpty(a.Room) && a.Slot >= 0 && a.Team >= 0
                      && (a.Mode == TeamHoldRules.MODE_TEAM || a.Mode == TeamHoldRules.MODE_OVT) && a.W0 >= 0 && a.W1 >= 0;
            if (!ok) a.Readmissible = false;
            return true;
        }

        internal sealed class ClaimAnswer
        {
            internal bool Ok;
            internal string Reason;
            internal string Token;
            internal string Room;
            internal string Region;
            internal int Slot = -1;
            internal int Team = -1;
            internal string G;
            internal bool Hold;
            internal string BoundaryDigest;
            internal string SeriesId;
            internal int W0 = -1, W1 = -1;
        }

        internal static bool TryParseClaim(int status, string body, out ClaimAnswer a)
        {
            a = null;
            if (string.IsNullOrEmpty(body)) return false;
            if (status != 200 || Field(body, "status") != "claimed")
            { a = new ClaimAnswer { Ok = false, Reason = Field(body, "reason") ?? ("http_" + status.ToString(CultureInfo.InvariantCulture)) }; return true; }
            a = new ClaimAnswer
            {
                Ok = true, Token = Field(body, "token"), Room = Field(body, "room_name"), Region = Field(body, "room_region"),
                Slot = IntField(body, "slot", -1), Team = IntField(body, "team", -1), G = Field(body, "game_id"),
                Hold = BoolField(body, "hold"), BoundaryDigest = Field(body, "boundary_digest"), SeriesId = Field(body, "series_id"),
            };
            IntPairField(body, "series_tally", out a.W0, out a.W1);
            if (string.IsNullOrEmpty(a.Token) || string.IsNullOrEmpty(a.Room) || a.Slot < 0 || string.IsNullOrEmpty(a.G))
            { a.Ok = false; a.Reason = "malformed"; }
            if (a.Ok) SeatDeckLog.Emit("[HOLD] claimed slot=" + a.Slot.ToString(CultureInfo.InvariantCulture) + " g=" + a.G);
            return true;
        }

        /// <summary>`bound` with seq, or a refusal reason (uncorroborated is retried).</summary>
        internal static bool TryParseBind(int status, string body, out bool bound, out string reason)
        {
            bound = false; reason = null;
            if (string.IsNullOrEmpty(body)) return false;
            if (status == 200 && Field(body, "status") == "bound") { bound = true; SeatDeckLog.Emit("[HOLD] bound"); return true; }
            reason = Field(body, "reason") ?? ("http_" + status.ToString(CultureInfo.InvariantCulture));
            return true;
        }

        /// <summary>The entry receipt: true only for a 200 whose `status` is
        /// entered. The server answers a refusal as 200 with status refused
        /// and a reason, which is a failure (toward today), never an entry.</summary>
        internal static bool TryParseEntered(int status, string body, out string reason)
        {
            reason = null;
            if (status == 200 && Field(body, "status") == "entered") return true;
            reason = Field(body, "reason") ?? ("entered_" + status.ToString(CultureInfo.InvariantCulture));
            return false;
        }

        internal static bool TryParseGameStart(int status, string body, out string g)
        {
            g = null;
            if (status != 200 || string.IsNullOrEmpty(body)) return false;
            g = Field(body, "game_id");
            return !string.IsNullOrEmpty(g) && g.IndexOf(':') < 0 && g.IndexOf(';') < 0;
        }
    }
}
