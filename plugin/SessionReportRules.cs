using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>Sept 28 (board row 30a) - the Unity-free half of the session
    /// report: the envelope's wire shape and its parser, moved here out of
    /// SessionReportModel so the parse can be EXECUTED under a plain compiler
    /// (tools/client-rules-harness, suite "sessionreport") against envelopes
    /// the server's own route produced, one per kind, instead of being
    /// asserted about as source text (#391).
    ///
    /// Manual, string-aware parsing only: JsonUtility fails silently on
    /// nested arrays, and this payload is nothing but nested arrays. Objects
    /// and arrays are sliced with the string-aware matchers below (the ones
    /// ApiClient's FindMatching*StringAware delegate to), so a display name
    /// containing '{' or '"' cannot split a member (learning #156). Every
    /// statistic is keyed by the player's steam id as a string; there is NO
    /// viewer-relative field anywhere and nothing here asks "who is me".
    ///
    /// No catalogue string lives here (the model and the view translate at
    /// their own I18n call sites), so this file is deliberately absent from
    /// tools/i18n_extract.py's FILES list (#464). The self-test cases live in
    /// the harness's half of this partial class
    /// (tools/client-rules-harness/SessionReportRulesSelfTest.cs), so the
    /// shipped DLL carries no fixture.</summary>
    internal static partial class SessionReportRules
    {
        private static readonly CultureInfo INV = CultureInfo.InvariantCulture;

        // -- envelope (wire shape, v1) -----------------------------------------

        /// <summary>One timeline sample: X = seconds from the game's start
        /// (server-stamped), Y = the stream's value.</summary>
        internal struct Pt
        {
            public readonly float X, Y;
            public Pt(float x, float y) { X = x; Y = y; }
        }

        internal sealed class Player
        {
            public string Id = "", Name = "", ColorHex = "";
            public int Team;
        }

        /// <summary>One pick. `Rolled` (FFA only): the rolling card cap pushed
        /// this card OUT of the build later in the game - it was picked, it is
        /// not part of the end build.</summary>
        internal sealed class Pick { public string Id = "", Card = ""; public bool Rolled; }

        internal sealed class Death { public float T; public string Id = ""; }

        internal sealed class Game
        {
            public string MatchId = "", StartedAt = "";
            public float DurationS;
            public readonly Dictionary<string, int> Scores = new Dictionary<string, int>();
            public readonly Dictionary<string, int> Points = new Dictionary<string, int>();
            /// <summary>player id -> stream name -> [t, v] samples, t in seconds
            /// from this game's start (server-stamped; kept, never re-gridded).</summary>
            public readonly Dictionary<string, Dictionary<string, List<Pt>>> Timelines
                = new Dictionary<string, Dictionary<string, List<Pt>>>();
            public readonly HashSet<string> Available = new HashSet<string>();
            public readonly List<Pick> Picks = new List<Pick>();
            /// <summary>The server kept only the newest picks of this game (its
            /// per-report card budget); the oldest are not in Picks/EndBuild.</summary>
            public bool PicksCapped;
            public readonly List<Death> Deaths = new List<Death>();
            public readonly Dictionary<string, List<string>> EndBuild = new Dictionary<string, List<string>>();
            public readonly Dictionary<string, string> EndStats = new Dictionary<string, string>();
            /// <summary>player id -> counter name -> value. SPARSE: an absent
            /// key is "not recorded", never zero (#257).</summary>
            public readonly Dictionary<string, Dictionary<string, float>> Totals
                = new Dictionary<string, Dictionary<string, float>>();
        }

        internal sealed class RatingEntry { public float? Before, After; public float Delta; }

        internal sealed class Envelope
        {
            public int V;
            public string Kind = "";
            public bool Truncated;
            /// <summary>Games of the set the envelope does not carry (beyond the
            /// server's cap, or a different roster under the same uuid).</summary>
            public int GamesOmitted;
            public readonly List<Player> Players = new List<Player>();
            public readonly List<Game> Games = new List<Game>();
            public readonly Dictionary<string, RatingEntry> Rating = new Dictionary<string, RatingEntry>();
            public readonly Dictionary<string, int> Gold = new Dictionary<string, int>();
        }

        // -- parse --------------------------------------------------------------

        /// <summary>Envelope or null when the text is not a JSON object. A
        /// version other than 1 still parses (the view says so) - the field
        /// exists precisely so a future shape can be told apart from garbage.</summary>
        internal static Envelope Parse(string json)
        {
            if (string.IsNullOrEmpty(json)) return null;
            int ob = json.IndexOf('{');
            if (ob < 0) return null;
            int oe = MatchBrace(json, ob);
            if (oe < 0) return null;
            var env = new Envelope();
            foreach (var kv in Members(json, ob, oe))
            {
                switch (kv.Key)
                {
                    case "v": env.V = (int)Num(kv.Value, 0f); break;
                    case "kind": env.Kind = Str(kv.Value); break;
                    case "truncated": env.Truncated = kv.Value == "true"; break;
                    case "games_omitted": env.GamesOmitted = Math.Max(0, (int)Num(kv.Value, 0f)); break;
                    case "players":
                        foreach (string p in Elements(kv.Value))
                        {
                            var pl = ParsePlayer(p);
                            if (pl != null) env.Players.Add(pl);
                        }
                        break;
                    case "games":
                        foreach (string g in Elements(kv.Value))
                        {
                            var gm = ParseGame(g);
                            if (gm != null) env.Games.Add(gm);
                        }
                        break;
                    case "set_summary": ParseSummary(kv.Value, env); break;
                }
            }
            return env;
        }

        private static Player ParsePlayer(string obj)
        {
            var p = new Player();
            foreach (var kv in Members(obj))
            {
                switch (kv.Key)
                {
                    case "id": p.Id = Str(kv.Value); break;
                    case "name": p.Name = Str(kv.Value); break;
                    case "color": p.ColorHex = Str(kv.Value); break;
                    case "team": p.Team = (int)Num(kv.Value, 0f); break;
                }
            }
            return string.IsNullOrEmpty(p.Id) ? null : p;
        }

        private static Game ParseGame(string obj)
        {
            var g = new Game();
            foreach (var kv in Members(obj))
            {
                switch (kv.Key)
                {
                    case "match_id": g.MatchId = Str(kv.Value); break;
                    case "started_at": g.StartedAt = Str(kv.Value); break;
                    case "duration_s": g.DurationS = Num(kv.Value, 0f); break;
                    case "scores": foreach (var e in Members(kv.Value)) g.Scores[e.Key] = (int)Num(e.Value, 0f); break;
                    case "points": foreach (var e in Members(kv.Value)) g.Points[e.Key] = (int)Num(e.Value, 0f); break;
                    case "available": foreach (string a in Elements(kv.Value)) { string s = Str(a); if (s.Length > 0) g.Available.Add(s); } break;
                    case "timelines":
                        foreach (var pl in Members(kv.Value))
                        {
                            var streams = new Dictionary<string, List<Pt>>();
                            foreach (var st in Members(pl.Value))
                            {
                                var pts = new List<Pt>();
                                foreach (string pair in Elements(st.Value))
                                {
                                    var tv = Elements(pair);
                                    if (tv.Count < 2) continue;
                                    float t = Num(tv[0], float.NaN), v = Num(tv[1], float.NaN);
                                    if (float.IsNaN(t) || float.IsNaN(v)) continue;
                                    pts.Add(new Pt(t, v));
                                }
                                if (pts.Count > 0) streams[st.Key] = pts;
                            }
                            g.Timelines[pl.Key] = streams;
                        }
                        break;
                    case "picks":
                        foreach (string po in Elements(kv.Value))
                        {
                            var pk = new Pick();
                            foreach (var e in Members(po))
                            {
                                if (e.Key == "id") pk.Id = Str(e.Value);
                                else if (e.Key == "card") pk.Card = Str(e.Value);
                                else if (e.Key == "rolled") pk.Rolled = e.Value == "true";
                            }
                            if (pk.Id.Length > 0 && pk.Card.Length > 0) g.Picks.Add(pk);
                        }
                        break;
                    case "picks_capped": g.PicksCapped = kv.Value == "true"; break;
                    case "deaths":
                        foreach (string d in Elements(kv.Value))
                        {
                            var de = new Death { T = float.NaN };
                            foreach (var e in Members(d))
                            {
                                if (e.Key == "id") de.Id = Str(e.Value);
                                else if (e.Key == "t") de.T = Num(e.Value, float.NaN);
                            }
                            if (de.Id.Length > 0 && !float.IsNaN(de.T)) g.Deaths.Add(de);
                        }
                        break;
                    case "end_build":
                        foreach (var e in Members(kv.Value))
                        {
                            var cards = new List<string>();
                            foreach (string c in Elements(e.Value)) { string s = Str(c); if (s.Length > 0) cards.Add(s); }
                            g.EndBuild[e.Key] = cards;
                        }
                        break;
                    case "end_stats":
                        foreach (var e in Members(kv.Value)) { string s = Str(e.Value); if (s.Length > 0) g.EndStats[e.Key] = s; }
                        break;
                    case "totals":
                        foreach (var pl in Members(kv.Value))
                        {
                            var tot = new Dictionary<string, float>();
                            foreach (var e in Members(pl.Value))
                            {
                                float v = Num(e.Value, float.NaN);
                                if (!float.IsNaN(v)) tot[e.Key] = v;
                            }
                            g.Totals[pl.Key] = tot;
                        }
                        break;
                }
            }
            return string.IsNullOrEmpty(g.MatchId) ? null : g;
        }

        private static void ParseSummary(string obj, Envelope env)
        {
            foreach (var kv in Members(obj))
            {
                if (kv.Key == "rating")
                {
                    foreach (var pl in Members(kv.Value))
                    {
                        var r = new RatingEntry();
                        foreach (var e in Members(pl.Value))
                        {
                            float v = Num(e.Value, float.NaN);
                            if (e.Key == "before") r.Before = float.IsNaN(v) ? (float?)null : v;
                            else if (e.Key == "after") r.After = float.IsNaN(v) ? (float?)null : v;
                            else if (e.Key == "delta" && !float.IsNaN(v)) r.Delta = v;
                        }
                        env.Rating[pl.Key] = r;
                    }
                }
                else if (kv.Key == "gold")
                {
                    foreach (var e in Members(kv.Value))
                    {
                        float v = Num(e.Value, float.NaN);
                        if (!float.IsNaN(v)) env.Gold[e.Key] = (int)v;
                    }
                }
            }
        }

        // -- JSON primitives (string-aware, top-level only) ---------------------

        /// <summary>Index of the ']' closing the '[' at openPos, skipping any
        /// bracket inside a JSON string (escapes honoured), or -1. ApiClient's
        /// FindMatchingBracketStringAware is this function.</summary>
        internal static int MatchBracket(string s, int openPos) => Match(s, openPos, '[', ']');

        /// <summary>Curly twin of <see cref="MatchBracket"/> (learning #156: any
        /// slice over a region that can carry user-authored strings must be
        /// string-aware). ApiClient's FindMatchingBraceStringAware is this.</summary>
        internal static int MatchBrace(string s, int openPos) => Match(s, openPos, '{', '}');

        private static int Match(string s, int openPos, char open, char close)
        {
            if (s == null || openPos < 0 || openPos >= s.Length) return -1;
            int depth = 0; bool inStr = false;
            for (int i = openPos; i < s.Length; i++)
            {
                char c = s[i];
                if (inStr)
                {
                    if (c == '\\') i++;
                    else if (c == '"') inStr = false;
                    continue;
                }
                if (c == '"') { inStr = true; continue; }
                if (c == open) depth++;
                else if (c == close) { depth--; if (depth == 0) return i; }
            }
            return -1;
        }

        /// <summary>The members of the object whose braces sit at [ob, oe]
        /// (inclusive) - key plus the RAW value text, so nested objects and
        /// arrays come back whole and a nested key can never shadow a
        /// top-level one (the envelope reuses "damage" and "score" at several
        /// depths).</summary>
        internal static List<KeyValuePair<string, string>> Members(string s, int ob, int oe)
        {
            var list = new List<KeyValuePair<string, string>>();
            if (s == null || ob < 0 || oe <= ob || oe >= s.Length) return list;
            int i = ob + 1;
            while (i < oe)
            {
                while (i < oe && (s[i] == ',' || char.IsWhiteSpace(s[i]))) i++;
                if (i >= oe || s[i] != '"') break;
                int ke = StringEnd(s, i);
                if (ke < 0 || ke >= oe) break;
                string key = Unquote(s, i, ke);
                i = ke + 1;
                while (i < oe && (s[i] == ':' || char.IsWhiteSpace(s[i]))) i++;
                if (i >= oe) break;
                int ve = ValueEnd(s, i, oe);
                if (ve < i) break;
                list.Add(new KeyValuePair<string, string>(key, s.Substring(i, ve - i + 1)));
                i = ve + 1;
            }
            return list;
        }

        internal static List<KeyValuePair<string, string>> Members(string obj)
        {
            if (string.IsNullOrEmpty(obj)) return new List<KeyValuePair<string, string>>();
            int ob = obj.IndexOf('{');
            if (ob < 0) return new List<KeyValuePair<string, string>>();
            int oe = MatchBrace(obj, ob);
            return Members(obj, ob, oe);
        }

        /// <summary>Raw element texts of a JSON array (nested structures whole).</summary>
        internal static List<string> Elements(string arr)
        {
            var list = new List<string>();
            if (string.IsNullOrEmpty(arr)) return list;
            int ab = arr.IndexOf('[');
            if (ab < 0) return list;
            int ae = MatchBracket(arr, ab);
            if (ae < 0) return list;
            int i = ab + 1;
            while (i < ae)
            {
                while (i < ae && (arr[i] == ',' || char.IsWhiteSpace(arr[i]))) i++;
                if (i >= ae) break;
                int ve = ValueEnd(arr, i, ae);
                if (ve < i) break;
                list.Add(arr.Substring(i, ve - i + 1));
                i = ve + 1;
            }
            return list;
        }

        /// <summary>Index of the closing quote of the string opening at s[i].</summary>
        private static int StringEnd(string s, int i)
        {
            for (int k = i + 1; k < s.Length; k++)
            {
                if (s[k] == '\\') { k++; continue; }
                if (s[k] == '"') return k;
            }
            return -1;
        }

        /// <summary>Last index of the value starting at s[i], searched below
        /// `limit` (exclusive): a string, object, array or scalar.</summary>
        private static int ValueEnd(string s, int i, int limit)
        {
            if (i >= limit) return -1;
            char c = s[i];
            if (c == '"') { int e = StringEnd(s, i); return e < limit ? e : -1; }
            if (c == '{') { int e = MatchBrace(s, i); return e < limit ? e : -1; }
            if (c == '[') { int e = MatchBracket(s, i); return e < limit ? e : -1; }
            int k = i;
            while (k < limit && s[k] != ',' && s[k] != '}' && s[k] != ']') k++;
            k--;
            while (k > i && char.IsWhiteSpace(s[k])) k--;
            return k;
        }

        /// <summary>A quoted JSON string value -> text (escapes decoded); any
        /// other raw value -> "" (so a null or a number never poses as text).</summary>
        internal static string Str(string raw)
        {
            if (string.IsNullOrEmpty(raw)) return "";
            int q = 0;
            while (q < raw.Length && char.IsWhiteSpace(raw[q])) q++;
            if (q >= raw.Length || raw[q] != '"') return "";
            int e = StringEnd(raw, q);
            return e < 0 ? "" : Unquote(raw, q, e);
        }

        private static string Unquote(string s, int openQuote, int closeQuote)
        {
            var sb = new StringBuilder(Math.Max(0, closeQuote - openQuote));
            for (int i = openQuote + 1; i < closeQuote; i++)
            {
                char c = s[i];
                if (c != '\\' || i + 1 >= closeQuote) { sb.Append(c); continue; }
                char n = s[++i];
                switch (n)
                {
                    case 'n': sb.Append('\n'); break;
                    case 'r': sb.Append('\r'); break;
                    case 't': sb.Append('\t'); break;
                    case 'b': sb.Append('\b'); break;
                    case 'f': sb.Append('\f'); break;
                    case 'u':
                        if (i + 4 < closeQuote
                            && int.TryParse(s.Substring(i + 1, 4), NumberStyles.HexNumber, INV, out int cp))
                        { sb.Append((char)cp); i += 4; }
                        break;
                    default: sb.Append(n); break;   // \" \\ \/
                }
            }
            return sb.ToString();
        }

        /// <summary>Scalar number, or `fallback` for null / non-numeric.</summary>
        internal static float Num(string raw, float fallback)
        {
            if (string.IsNullOrEmpty(raw)) return fallback;
            string t = raw.Trim();
            if (t == "null" || t.Length == 0) return fallback;
            if (t == "true") return 1f;
            if (t == "false") return 0f;
            float v;
            return float.TryParse(t, NumberStyles.Float, INV, out v) ? v : fallback;
        }

        // -- board row 30b: the page's IMGUI search fields and the report --------

        /// <summary>Whether one of the F5 page's IMGUI search fields (Compare,
        /// Leaderboard, Card Stats, Info, History, the metric picker's field,
        /// the admin player search) may paint and take input this frame.
        /// IMGUI stacks by call order and those fields are drawn AFTER the
        /// report in CompetitiveUI.DrawUI, so while the report is open a field
        /// painted over it and a focused one kept taking keystrokes. Every
        /// field now stands down instead: it neither paints nor takes input,
        /// and its focus flag (the T-chat mutex) stays false. `onItsSurface` is
        /// the field's own gate (its tab, the picker open, the modal open). The
        /// uGUI overlay-canvas pattern does not apply: IMGUI paints above every
        /// canvas (TmpOverlayPanel.cs).</summary>
        internal static bool SearchFieldMayDraw(bool pageOpen, bool onItsSurface, bool reportOpen)
            => pageOpen && onItsSurface && !reportOpen;

        // -- series maths (pure) -----------------------------------------------

        /// <summary>Value of a cumulative series at time x: 0 at or before the
        /// origin, linear between samples, held after the last one.</summary>
        internal static float At(List<Pt> s, float x)
        {
            if (s == null || s.Count == 0 || x <= 0f) return 0f;
            float px = 0f, pv = 0f;
            for (int i = 0; i < s.Count; i++)
            {
                if (x <= s[i].X)
                {
                    float span = s[i].X - px;
                    return span <= 0f ? s[i].Y : pv + (s[i].Y - pv) * ((x - px) / span);
                }
                px = s[i].X; pv = s[i].Y;
            }
            return s[s.Count - 1].Y;
        }

        /// <summary>Rate over the trailing window at each sample time:
        /// (v(t) - v(t - w)) / w, clamped at 0 (a counter reset is not a
        /// negative rate). Needs two samples to mean anything.</summary>
        internal static List<Pt> Rolling(List<Pt> cum, float window)
        {
            var out_ = new List<Pt>();
            if (cum == null || cum.Count < 2 || window <= 0f) return out_;
            for (int i = 0; i < cum.Count; i++)
            {
                float t = cum[i].X;
                float d = cum[i].Y - At(cum, t - window);
                float w = Math.Min(window, Math.Max(t, 1f));
                out_.Add(new Pt(t, Math.Max(0f, d / w)));
            }
            return out_;
        }

        /// <summary>100 * (change of num) / (change of den) over the trailing
        /// window at each sample time of `den`; samples whose den change is
        /// below `minDen` are skipped (a 15 s window with one shot is noise,
        /// not a percentage).</summary>
        internal static List<Pt> RollingRatio(List<Pt> num, List<Pt> den, float window, float minDen)
        {
            var out_ = new List<Pt>();
            if (num == null || den == null || den.Count < 2 || window <= 0f) return out_;
            for (int i = 0; i < den.Count; i++)
            {
                float t = den[i].X;
                float dd = den[i].Y - At(den, t - window);
                if (dd < minDen) continue;
                float dn = At(num, t) - At(num, t - window);
                out_.Add(new Pt(t, Math.Max(0f, Math.Min(100f, 100f * dn / dd))));
            }
            return out_;
        }
    }
}
