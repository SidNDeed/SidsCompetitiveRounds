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
    /// <see cref="Sign"/>, which KX1 binds inside ApiClient. Unbound, a call
    /// answers <see cref="NoTransport"/> at once and every caller ends toward
    /// today (V3:157). Answers are parsed by manual string splitting:
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

        internal static string PathState(string holdId) { return "/api/v1/match/hold/" + Uri.EscapeDataString(holdId ?? "") + "/state"; }
        internal static string PathEnd(string holdId) { return "/api/v1/match/hold/" + Uri.EscapeDataString(holdId ?? "") + "/end"; }
        internal static string PathClaim(string holdId) { return "/api/v1/match/hold/" + Uri.EscapeDataString(holdId ?? "") + "/claim"; }
        internal static string PathBind(string holdId) { return "/api/v1/match/hold/" + Uri.EscapeDataString(holdId ?? "") + "/bind"; }
        internal static string PathEntered(string holdId) { return "/api/v1/match/hold/" + Uri.EscapeDataString(holdId ?? "") + "/entered"; }

        internal static string PathByRoom(string room, string g)
        {
            return "/api/v1/match/hold/by-room?room=" + Uri.EscapeDataString(room ?? "") + "&g=" + Uri.EscapeDataString(g ?? "");
        }

        /// <summary>One call. Unbound or throwing transport: NoTransport, at once.</summary>
        internal static void Call(string method, string path, string body, Action<int, string> done)
        {
            var t = Send;
            if (t == null) { done(NoTransport, "no-transport"); return; }
            try { t(method, path, body, done); }
            catch { done(NoTransport, "transport-threw"); }
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

        internal static string GameStartBody(string mode, string seriesId, string room, string prevG)
        {
            return "{\"mode\":" + Q(mode) + ",\"series_id\":" + Q(seriesId) + ",\"room\":" + Q(room) + ",\"prev_game\":" + Q(prevG) + "}";
        }

        internal static string BeatBody(string room, int actor, IList<KeyValuePair<int, string>> seen, string boundaryDigest)
        {
            var sb = new StringBuilder("{\"room\":").Append(Q(room)).Append(",\"actor\":").Append(I(actor)).Append(",\"seen\":[");
            for (int i = 0; seen != null && i < seen.Count; i++)
            {
                if (i > 0) sb.Append(',');
                sb.Append("{\"actor\":").Append(I(seen[i].Key)).Append(",\"u_id\":").Append(Q(seen[i].Value)).Append('}');
            }
            return sb.Append("],\"boundary_digest\":").Append(Q(boundaryDigest)).Append('}').ToString();
        }

        internal static string OpenBody(string requestId, string mode, string room, string g, string heldSteam, int slot, int team, string openerSteam, string sig)
        {
            return "{\"request_id\":" + Q(requestId) + ",\"mode\":" + Q(mode) + ",\"room\":" + Q(room) + ",\"game_id\":" + Q(g)
                   + ",\"held_steam\":" + Q(heldSteam) + ",\"slot\":" + I(slot) + ",\"team\":" + I(team)
                   + ",\"opener_steam\":" + Q(openerSteam) + ",\"sig\":" + Q(sig) + "}";
        }

        internal static string EndBody(string reason) { return "{\"reason\":" + Q(reason) + "}"; }
        internal static string BindBody(int actor, string region) { return "{\"actor\":" + I(actor) + ",\"region\":" + Q(region) + "}"; }
        internal static string EnteredBody(string g, int actor) { return "{\"game_id\":" + Q(g) + ",\"actor\":" + I(actor) + "}"; }

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

        internal sealed class OpenAnswer
        {
            internal bool Opened;
            internal string HoldId;
            internal int Seq;
            internal int HoldS;
            internal string Reason;
        }

        /// <summary>`opened` with hold_id, seq and hold_s, or `refused` with a reason.</summary>
        internal static bool TryParseOpen(int status, string body, out OpenAnswer a)
        {
            a = null;
            if (status != 200 || string.IsNullOrEmpty(body)) return false;
            string outcome = Field(body, "outcome");
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
        /// `state` is one of open, claimed, bound, entered, closed.</summary>
        internal static bool TryParseState(int status, string body, out StateAnswer a)
        {
            a = null;
            if (status != 200 || string.IsNullOrEmpty(body)) return false;
            string st = Field(body, "state");
            char c;
            switch (st)
            {
                case "open": c = 'o'; break;
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

        /// <summary>The discovery answer; `series_tally` is "w0:w1".</summary>
        internal static bool TryParseMine(int status, string body, out MineAnswer a)
        {
            a = null;
            if (status != 200 || string.IsNullOrEmpty(body)) return false;
            a = new MineAnswer { Readmissible = BoolField(body, "readmissible") };
            if (!a.Readmissible) return true;
            a.HoldId = Field(body, "hold_id"); a.N = IntField(body, "n", 0); a.Mode = Field(body, "mode");
            a.Room = Field(body, "room_name"); a.Region = Field(body, "room_region");
            a.Slot = IntField(body, "slot", -1); a.Team = IntField(body, "team", -1); a.HoldS = IntField(body, "hold_s", 0);
            var tally = (Field(body, "series_tally") ?? "").Split(':');
            a.W0 = tally.Length == 2 ? TeamHoldRules.ParseInt(tally[0], -1) : -1;
            a.W1 = tally.Length == 2 ? TeamHoldRules.ParseInt(tally[1], -1) : -1;
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
            if (status != 200) { a = new ClaimAnswer { Ok = false, Reason = Field(body, "reason") ?? ("http_" + status.ToString(CultureInfo.InvariantCulture)) }; return true; }
            a = new ClaimAnswer
            {
                Ok = true, Token = Field(body, "token"), Room = Field(body, "room_name"), Region = Field(body, "room_region"),
                Slot = IntField(body, "slot", -1), Team = IntField(body, "team", -1), G = Field(body, "game_id"),
                Hold = BoolField(body, "hold"), BoundaryDigest = Field(body, "boundary_digest"), SeriesId = Field(body, "series_id"),
            };
            var tally = (Field(body, "series_tally") ?? "").Split(':');
            if (tally.Length == 2) { a.W0 = TeamHoldRules.ParseInt(tally[0], -1); a.W1 = TeamHoldRules.ParseInt(tally[1], -1); }
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
            if (status == 200 && Field(body, "outcome") == "bound") { bound = true; SeatDeckLog.Emit("[HOLD] bound"); return true; }
            reason = Field(body, "reason") ?? ("http_" + status.ToString(CultureInfo.InvariantCulture));
            return true;
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
