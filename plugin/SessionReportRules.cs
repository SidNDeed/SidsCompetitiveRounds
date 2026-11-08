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
            /// <summary>Board row 30d: this game's own ledger gold and XP record
            /// per player (sparse).</summary>
            public readonly Dictionary<string, int> Gold = new Dictionary<string, int>();
            public readonly Dictionary<string, int> Xp = new Dictionary<string, int>();
            /// <summary>Board row 30e: the rounds this FFA game was played to
            /// (settings.score_target); 0 when the settings are not known.</summary>
            public int ScoreTarget;
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
            /// <summary>Board row 30d: what the set earned (set_summary.gold_total /
            /// xp_total). HasTotals is false for a server that predates them; the
            /// page then shows the legacy `gold` and no XP.</summary>
            public bool HasTotals;
            public readonly Dictionary<string, int> GoldTotal = new Dictionary<string, int>();
            public readonly Dictionary<string, int> XpTotal = new Dictionary<string, int>();
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
                    case "gold": Ints(kv.Value, g.Gold); break;
                    case "xp": Ints(kv.Value, g.Xp); break;
                    case "settings":
                        foreach (var e in Members(kv.Value))
                            if (e.Key == "score_target") g.ScoreTarget = Math.Max(0, (int)Num(e.Value, 0f));
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
                else if (kv.Key == "gold") Ints(kv.Value, env.Gold);
                else if (kv.Key == "gold_total") { env.HasTotals = true; Ints(kv.Value, env.GoldTotal); }
                else if (kv.Key == "xp_total") { env.HasTotals = true; Ints(kv.Value, env.XpTotal); }
            }
        }

        /// <summary>{key: number} into `into`, a non-number skipped (sparse).</summary>
        private static void Ints(string obj, Dictionary<string, int> into)
        {
            foreach (var e in Members(obj))
            {
                float v = Num(e.Value, float.NaN);
                if (!float.IsNaN(v)) into[e.Key] = (int)v;
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

        // -- board row 30b: the page's own IMGUI and the report ------------------

        /// <summary>Whether one of the F5 page's own IMGUI elements may paint
        /// and take input this frame: its search fields (Compare, Leaderboard,
        /// Card Stats, Info, History, the metric picker's field, the admin
        /// player search), the first-timer ranked callout that points at a
        /// page button, and the FFA and 1v2 tabs' row hover tooltips. IMGUI
        /// stacks by call order and the fields and the callout are drawn AFTER
        /// the report in CompetitiveUI.DrawUI, so while the report was open
        /// they painted over it and a focused field kept taking keystrokes. The
        /// two tooltips paint from their tabs' own behaviours
        /// (FfaRecentGraphDrawer, OneVTwoHoverDrawer), whose OnGUI Unity orders
        /// against DrawUI's by GUI.depth, not by DrawUI's call order, and they
        /// ask to be on top. Each now stands down instead: it neither paints
        /// nor takes input, and a field's focus flag (the T-chat mutex) stays
        /// false. `onItsSurface` is the element's own gate (its tab, the picker
        /// open, the modal open, the callout wanted). The uGUI overlay-canvas
        /// pattern does not apply: IMGUI paints above every canvas
        /// (TmpOverlayPanel.cs).</summary>
        internal static bool PageElementMayDraw(bool pageOpen, bool onItsSurface, bool reportOpen)
            => pageOpen && onItsSurface && !reportOpen;

        // -- board row 30c: the builds pages' layout (pure) ---------------------

        /// <summary>First block index of every page when blocks of the given
        /// heights are laid top to bottom in a column `usable` tall: a block that
        /// does not fit starts the next page, and a block taller than a page
        /// still gets a page of its own - every block lands on exactly one page,
        /// none is dropped, and there is no per-page cap (board row 30c).</summary>
        internal static List<int> PackPages(IList<float> heights, float usable)
        {
            var starts = new List<int> { 0 };
            float used = 0f;
            for (int i = 0; i < heights.Count; i++)
            {
                float h = Math.Max(0f, heights[i]);
                if (used > 0f && used + h > usable)
                {
                    starts.Add(i);
                    used = 0f;
                }
                used += h;
            }
            return starts;
        }

        /// <summary>Chips in the given order (pick order) flowed into a line
        /// `lineW` wide: a chip that would cross the right edge starts the next
        /// row, and a chip wider than the line gets a row of its own. Returns
        /// (x, row) per chip; `rows` is the number of rows used (0 for none).</summary>
        internal static List<Pt> FlowChips(IList<float> widths, float lineW, float gap, out int rows)
        {
            var at = new List<Pt>(widths.Count);
            float x = 0f;
            int row = 0;
            for (int i = 0; i < widths.Count; i++)
            {
                float w = Math.Max(0f, widths[i]);
                if (x > 0f && x + w > lineW)
                {
                    row++;
                    x = 0f;
                }
                at.Add(new Pt(x, row));
                x += w + gap;
            }
            rows = widths.Count == 0 ? 0 : row + 1;
            return at;
        }

        // -- board row 30d: the Totals pages' numbers (pure) --------------------

        /// <summary>ROUNDS' two-sided rule: a round is won at 2 points
        /// (GameStateWatcher's recorder; the mod does not change it).</summary>
        internal const int POINTS_PER_ROUND = 2;

        /// <summary>A two-sided game's point events replayed (1v1, and since ask 9
        /// 2v2 and 1v2, whose recorder writes the same pairs): who scored first, each
        /// side's longest run of consecutive points, its worst deficit in rounds,
        /// the seconds it led in rounds, how often the lead changed hands, and
        /// the rounds race itself. The recorder writes each side's value as
        /// rounds * 2 + points inside the round (GameStateWatcher; the server
        /// passes it through as the `score` stream), so a round win zeroes BOTH
        /// sides' points. `Exact` is false - and nothing else is set - when the
        /// streams cannot be replayed one point per event into the recorded
        /// rounds (a decimated or damaged stream): a derived number is shown
        /// only when the events prove it.</summary>
        internal sealed class Momentum
        {
            public bool Exact;
            public int FirstScorer = -1;
            public readonly int[] LongestStreak = new int[2];
            public readonly int[] WorstDeficit = new int[2];
            public readonly float[] LeadS = new float[2];
            public int LeadChanges;
            /// <summary>(t, rounds) at every round end, from (0, 0).</summary>
            public readonly List<Pt>[] Rounds = { new List<Pt>(), new List<Pt>() };
        }

        internal static Momentum ReplayTwoSided(List<Pt> a, List<Pt> b, int roundsA, int roundsB, float durationS)
        {
            if (a == null || b == null || a.Count == 0 || a.Count != b.Count) return new Momentum();
            var m = new Momentum();
            int ra = 0, rb = 0, pa = 0, pb = 0, run = 0, runSide = -1;
            int leader = -1, lastLeader = -1;
            float lastT = 0f;
            m.Rounds[0].Add(new Pt(0f, 0f));
            m.Rounds[1].Add(new Pt(0f, 0f));
            for (int i = 0; i < a.Count; i++)
            {
                int va = (int)Math.Round(a[i].Y), vb = (int)Math.Round(b[i].Y);
                float t = a[i].X;
                if (va < 0 || vb < 0 || t < lastT || Math.Abs(b[i].X - t) > 0.05f) return new Momentum();
                int na = va / POINTS_PER_ROUND, npa = va % POINTS_PER_ROUND;
                int nb = vb / POINTS_PER_ROUND, npb = vb % POINTS_PER_ROUND;
                int side = Scorer(ra, pa, rb, pb, na, npa, nb, npb);
                if (side < 0) return new Momentum();
                if (m.FirstScorer < 0) m.FirstScorer = side;
                run = side == runSide ? run + 1 : 1;
                runSide = side;
                if (run > m.LongestStreak[side]) m.LongestStreak[side] = run;
                if (leader >= 0) m.LeadS[leader] += t - lastT;
                lastT = t;
                bool roundEnded = na != ra || nb != rb;
                ra = na; pa = npa; rb = nb; pb = npb;
                if (roundEnded)
                {
                    m.Rounds[0].Add(new Pt(t, ra));
                    m.Rounds[1].Add(new Pt(t, rb));
                    leader = ra > rb ? 0 : rb > ra ? 1 : -1;
                    if (leader >= 0 && lastLeader >= 0 && leader != lastLeader) m.LeadChanges++;
                    if (leader >= 0) lastLeader = leader;
                    m.WorstDeficit[0] = Math.Max(m.WorstDeficit[0], rb - ra);
                    m.WorstDeficit[1] = Math.Max(m.WorstDeficit[1], ra - rb);
                }
            }
            if (ra != roundsA || rb != roundsB) return new Momentum();
            if (leader >= 0 && durationS > lastT) m.LeadS[leader] += durationS - lastT;
            m.Exact = true;
            return m;
        }

        /// <summary>Which side scored the ONE point that moved (ra, pa, rb, pb)
        /// to the new state: 0, 1, or -1 when no single point explains it.</summary>
        private static int Scorer(int ra, int pa, int rb, int pb, int na, int npa, int nb, int npb)
        {
            if (na == ra && nb == rb && npa == pa + 1 && npb == pb) return 0;
            if (na == ra && nb == rb && npb == pb + 1 && npa == pa) return 1;
            // the point that won the round: both sides' points reset
            if (na == ra + 1 && nb == rb && npa == 0 && npb == 0 && pa == POINTS_PER_ROUND - 1) return 0;
            if (nb == rb + 1 && na == ra && npa == 0 && npb == 0 && pb == POINTS_PER_ROUND - 1) return 1;
            return -1;
        }

        /// <summary>One player's line of the Totals pages. Every field is
        /// derived from named envelope fields (the field map is in the lane
        /// notes); null means the data does not exist for this set or mode,
        /// and the page omits it - never a zero.</summary>
        internal sealed class PlayerLine
        {
            public int Games;
            /// <summary>Stored counters summed over the games that recorded them.</summary>
            public readonly Dictionary<string, float> Sum = new Dictionary<string, float>();
            public float? Kills;
            public int? CardsPicked, PointsWon, PointsLost;
            public int? FirstBloods, LongestStreak, BiggestComeback;
            public float? LeadS;
            public int? Gold, Xp;
            public readonly List<float?> DamageByGame = new List<float?>();
            public readonly List<float?> KillsByGame = new List<float?>();
            public readonly List<float?> DeathsByGame = new List<float?>();
            public readonly List<float?> HitPctByGame = new List<float?>();
            public readonly List<float?> BlockPctByGame = new List<float?>();
            public readonly List<float?> GoldByGame = new List<float?>();
            public readonly List<float?> XpByGame = new List<float?>();

            internal float? Total(string counter)
            {
                float v;
                return Sum.TryGetValue(counter, out v) ? v : (float?)null;
            }
        }

        internal sealed class SetLine
        {
            public int Games, Timed;
            public float TotalS, ShortestS, LongestS, AverageS;
            public int ShortestGame = -1, LongestGame = -1;
            /// <summary>Per player: games won (a 2v2 / 1v2 player carries the
            /// side's wins; an FFA game is won by its unique top score).</summary>
            public int[] Wins = new int[0];
            /// <summary>Two-sided sets whose every game replays exactly, else -1.</summary>
            public int LeadChanges = -1;
        }

        internal sealed class Derived
        {
            public readonly SetLine Set = new SetLine();
            public readonly List<PlayerLine> Players = new List<PlayerLine>();
            /// <summary>Per game; null when the set is not two-sided (FFA).</summary>
            public readonly List<Momentum> Moments = new List<Momentum>();
            /// <summary>The set's sides (ask 9 stage C: Sides), in side order.</summary>
            public readonly List<Side> Sides = new List<Side>();
        }

        internal static bool IsTwoSided(string kind) => kind == "team" || kind == "ovt";

        // -- ask 9 stage C: sides (pure) -------------------------------------------

        /// <summary>One side of a set: the roster indices of its players, in
        /// roster order. Every score the server records is a SIDE's (each
        /// player of a side carries the side's rounds, points and `score`
        /// stream), so the race, the labels and the momentum numbers read a
        /// side, never players[0] / players[1].</summary>
        internal sealed class Side
        {
            /// <summary>1 or 2 in a two-sided set (2v2: the teams; 1v2: solo 1,
            /// duo 2; 1v1: roster order); the roster index + 1 otherwise.</summary>
            public int Team;
            public readonly List<int> Slots = new List<int>();
        }

        /// <summary>The sides of a set, derived the way the server derives the
        /// score streams (backend/api/main.py _report_sides): every player
        /// carries team 1 or 2 and both teams are present - two sides by team;
        /// else exactly two players of a kind that is not FFA - two sides of
        /// one; else one side per player (FFA, whose streams are per player,
        /// and any roster the kind cannot pair). An FFA of two is NOT a 1v1:
        /// its streams are half points, not the recorder's pairs.</summary>
        internal static List<Side> Sides(string kind, IList<Player> players)
        {
            var sides = new List<Side>();
            int n = players == null ? 0 : players.Count;
            if (n == 0) return sides;
            bool teams = kind != "ffa";
            for (int i = 0; teams && i < n; i++) teams = players[i].Team == 1 || players[i].Team == 2;
            if (teams)
            {
                var one = new Side { Team = 1 };
                var two = new Side { Team = 2 };
                for (int i = 0; i < n; i++) (players[i].Team == 1 ? one : two).Slots.Add(i);
                if (one.Slots.Count > 0 && two.Slots.Count > 0)
                {
                    sides.Add(one);
                    sides.Add(two);
                    return sides;
                }
            }
            if (kind != "ffa" && n == 2)
            {
                var a = new Side { Team = 1 };
                a.Slots.Add(0);
                var b = new Side { Team = 2 };
                b.Slots.Add(1);
                sides.Add(a);
                sides.Add(b);
                return sides;
            }
            for (int i = 0; i < n; i++)
            {
                var s = new Side { Team = i + 1 };
                s.Slots.Add(i);
                sides.Add(s);
            }
            return sides;
        }

        /// <summary>Whether the set is a race of two sides (1v1, 2v2, 1v2):
        /// the replay, points lost and the two-score labels apply. Never FFA.</summary>
        internal static bool TwoSided(string kind, IList<Side> sides)
        {
            return kind != "ffa" && sides != null && sides.Count == 2;
        }

        /// <summary>Roster index -> index into `sides` (-1 for a player on no side).</summary>
        internal static int[] SideIndex(IList<Side> sides, int players)
        {
            var at = new int[players];
            for (int i = 0; i < players; i++) at[i] = -1;
            if (sides != null)
                for (int si = 0; si < sides.Count; si++)
                    foreach (int pi in sides[si].Slots)
                        if (pi >= 0 && pi < players) at[pi] = si;
            return at;
        }

        /// <summary>A side's stream in game g: the first member's that has one
        /// (the server puts the side's stream on every member); null when none.</summary>
        internal static List<Pt> SideStream(Game g, IList<Player> players, Side side, string name)
        {
            if (g == null || players == null || side == null) return null;
            foreach (int pi in side.Slots)
            {
                if (pi < 0 || pi >= players.Count) continue;
                var s = Stream(g, players[pi].Id, name);
                if (s != null && s.Count > 0) return s;
            }
            return null;
        }

        /// <summary>A side's recorded score in g: the key of its first member who
        /// played g (every member carries the side's rounds), `at` that member's
        /// roster index; -1 and at = -1 when no member has a key (round 2 M1: a
        /// missing key is never a 0).</summary>
        internal static int SideScoreOf(Game g, IList<Player> players, Side side, out int at)
        {
            at = -1;
            if (g == null || players == null || side == null) return -1;
            foreach (int pi in side.Slots)
            {
                int v;
                if (pi < 0 || pi >= players.Count || !g.Scores.TryGetValue(players[pi].Id, out v)) continue;
                at = pi;
                return v;
            }
            return -1;
        }

        /// <summary>The deaths the members of `side` recorded in g, summed; NaN
        /// when a member who played g has no deaths counter (then nothing can be
        /// derived from them) or none played.</summary>
        private static float SideDeaths(Game g, IList<Player> players, Side side)
        {
            float sum = 0f;
            int counted = 0;
            foreach (int pi in side.Slots)
            {
                string id = players[pi].Id;
                if (!g.Scores.ContainsKey(id)) continue;
                Dictionary<string, float> tot;
                float d;
                if (!g.Totals.TryGetValue(id, out tot) || tot == null || !tot.TryGetValue("deaths", out d)) return float.NaN;
                sum += d;
                counted++;
            }
            return counted > 0 ? sum : float.NaN;
        }

        /// <summary>The Totals pages' numbers for `players` (the de-duplicated
        /// roster, in order) over every game of the envelope.</summary>
        internal static Derived Derive(Envelope env, IList<Player> players)
        {
            var d = new Derived();
            int n = players.Count;
            string kind = env.Kind ?? "";
            var sides = Sides(kind, players);
            d.Sides.AddRange(sides);
            bool twoSided = TwoSided(kind, sides);
            var sideOf = SideIndex(sides, n);
            var set = d.Set;
            set.Games = env.Games.Count;
            set.Wins = new int[n];
            set.ShortestS = float.MaxValue;
            for (int gi = 0; gi < env.Games.Count; gi++)
            {
                var g = env.Games[gi];
                if (g.DurationS > 0f)
                {
                    set.Timed++;
                    set.TotalS += g.DurationS;
                    if (g.DurationS < set.ShortestS) { set.ShortestS = g.DurationS; set.ShortestGame = gi; }
                    if (g.DurationS > set.LongestS) { set.LongestS = g.DurationS; set.LongestGame = gi; }
                }
                CountWins(kind, g, players, sides, set.Wins);
            }
            if (set.Timed > 0) set.AverageS = set.TotalS / set.Timed;
            else set.ShortestS = 0f;

            // The two sides' point events replayed per game - every two-sided
            // kind since ask 9 (the 2v2 / 1v2 recorder writes the same pairs), not
            // 1v1 alone. A game whose side streams do not replay exactly into its
            // recorded rounds, or where a side has no key, leaves every momentum
            // number of the set unset: a derived number is shown only when the
            // events prove it.
            bool allExact = twoSided && env.Games.Count > 0;
            for (int gi = 0; gi < env.Games.Count; gi++)
            {
                Momentum mo = null;
                if (twoSided)
                {
                    var g = env.Games[gi];
                    int ia, ib;
                    int ra = SideScoreOf(g, players, sides[0], out ia), rb = SideScoreOf(g, players, sides[1], out ib);
                    mo = ia >= 0 && ib >= 0
                        ? ReplayTwoSided(SideStream(g, players, sides[0], "score"), SideStream(g, players, sides[1], "score"),
                                         ra, rb, g.DurationS)
                        : new Momentum();
                    if (!mo.Exact) allExact = false;
                }
                d.Moments.Add(mo);
            }
            if (allExact)
            {
                set.LeadChanges = 0;
                foreach (var mo in d.Moments) set.LeadChanges += mo.LeadChanges;
            }

            for (int pi = 0; pi < n; pi++)
            {
                string pid = players[pi].Id;
                int si = sideOf[pi];
                // The lone fighter of a side (a 1v1 fighter, the 1v2 solo) made
                // every kill on the other side, so with no kills counter of its
                // own its kills are the opponents' recorded deaths. A member of a
                // side of two cannot be told apart from its partner that way.
                Side opponents = twoSided && si >= 0 && sides[si].Slots.Count == 1 ? sides[1 - si] : null;
                var line = new PlayerLine();
                bool killsRecorded = false, killsDerived = false, capped = false;
                float kills = 0f, derivedKills = 0f;
                int picks = 0, won = 0, lost = 0;
                bool wonKnown = false, lostKnown = kind != "ffa";
                for (int gi = 0; gi < env.Games.Count; gi++)
                {
                    var g = env.Games[gi];
                    bool played = g.Scores.ContainsKey(pid);
                    Dictionary<string, float> tot;
                    g.Totals.TryGetValue(pid, out tot);
                    float? gKills = null, gDeaths = null, gDmg = null, gHit = null, gBlock = null;
                    if (played)
                    {
                        line.Games++;
                        if (tot != null)
                        {
                            foreach (var kv in tot)
                            {
                                float cur;
                                line.Sum.TryGetValue(kv.Key, out cur);
                                line.Sum[kv.Key] = cur + kv.Value;
                            }
                            float v;
                            if (tot.TryGetValue("damage", out v)) gDmg = v;
                            if (tot.TryGetValue("deaths", out v)) gDeaths = v;
                            if (tot.TryGetValue("kills", out v)) { gKills = v; kills += v; killsRecorded = true; }
                            float shots, hits, blocks, ok;
                            if (tot.TryGetValue("shots", out shots) && tot.TryGetValue("hits", out hits) && shots > 0f)
                                gHit = 100f * hits / shots;
                            if (tot.TryGetValue("blocks", out blocks) && tot.TryGetValue("blocks_ok", out ok) && blocks > 0f)
                                gBlock = 100f * ok / blocks;
                        }
                        if (gKills == null && opponents != null)
                        {
                            float od = SideDeaths(g, players, opponents);
                            if (!float.IsNaN(od))
                            {
                                gKills = od;
                                derivedKills += od;
                                killsDerived = true;
                            }
                        }
                        foreach (var pk in g.Picks) if (pk.Id == pid) picks++;
                        if (g.PicksCapped) capped = true;
                        int pts;
                        if (g.Points.TryGetValue(pid, out pts)) { won += pts; wonKnown = true; }
                        if (lostKnown)
                        {
                            int opp = OpponentPoints(kind, g, players, sides, si);
                            if (opp < 0) lostKnown = false; else lost += opp;
                        }
                    }
                    line.DamageByGame.Add(gDmg);
                    line.KillsByGame.Add(gKills);
                    line.DeathsByGame.Add(gDeaths);
                    line.HitPctByGame.Add(gHit);
                    line.BlockPctByGame.Add(gBlock);
                    int gv;
                    line.GoldByGame.Add(played && g.Gold.TryGetValue(pid, out gv) ? gv : (float?)null);
                    line.XpByGame.Add(played && g.Xp.TryGetValue(pid, out gv) ? gv : (float?)null);
                }
                if (killsRecorded) line.Kills = kills;
                else if (killsDerived) line.Kills = derivedKills;
                if (line.Games > 0 && !capped) line.CardsPicked = picks;
                if (wonKnown) line.PointsWon = won;
                if (lostKnown && line.Games > 0) line.PointsLost = lost;
                if (allExact && si >= 0)
                {
                    // Side numbers: every member of a side carries them (a
                    // teammate's first blood is the side's).
                    int fb = 0, streak = 0, comeback = 0;
                    float lead = 0f;
                    for (int gi = 0; gi < d.Moments.Count; gi++)
                    {
                        var mo = d.Moments[gi];
                        if (mo.FirstScorer == si) fb++;
                        streak = Math.Max(streak, mo.LongestStreak[si]);
                        lead += mo.LeadS[si];
                        var g = env.Games[gi];
                        int ia, ib;
                        if (SideScoreOf(g, players, sides[si], out ia) > SideScoreOf(g, players, sides[1 - si], out ib))
                            comeback = Math.Max(comeback, mo.WorstDeficit[si]);
                    }
                    line.FirstBloods = fb;
                    line.LongestStreak = streak;
                    line.BiggestComeback = comeback;
                    line.LeadS = lead;
                }
                int total;
                if (env.HasTotals)
                {
                    if (env.GoldTotal.TryGetValue(pid, out total)) line.Gold = total;
                    if (env.XpTotal.TryGetValue(pid, out total)) line.Xp = total;
                }
                else if (env.Gold.TryGetValue(pid, out total)) line.Gold = total;
                d.Players.Add(line);
            }
            return d;
        }

        /// <summary>Who won game g: the index into `sides` of the side with the
        /// higher recorded score in a two-sided set, else the roster index of
        /// the unique top score (FFA); -1 on a tie, on a side with no key, or
        /// with no score at all. The set's wins and its race figure read this.</summary>
        internal static int Winner(string kind, Game g, IList<Player> players, IList<Side> sides)
        {
            if (g == null || players == null) return -1;
            if (TwoSided(kind, sides))
            {
                int ia, ib;
                int s1 = SideScoreOf(g, players, sides[0], out ia), s2 = SideScoreOf(g, players, sides[1], out ib);
                if (ia < 0 || ib < 0 || s1 == s2) return -1;
                return s1 > s2 ? 0 : 1;
            }
            int best = int.MinValue, at = -1;
            bool tie = false;
            for (int i = 0; i < players.Count; i++)
            {
                int v;
                if (!g.Scores.TryGetValue(players[i].Id, out v)) continue;
                if (v > best) { best = v; at = i; tie = false; }
                else if (v == best) tie = true;
            }
            return at >= 0 && !tie ? at : -1;
        }

        /// <summary>The win of game g on the roster: every member of the winning
        /// side who played it (two-sided), or the unique top scorer (FFA).</summary>
        private static void CountWins(string kind, Game g, IList<Player> players, IList<Side> sides, int[] wins)
        {
            int w = Winner(kind, g, players, sides);
            if (w < 0) return;
            if (TwoSided(kind, sides))
            {
                foreach (int pi in sides[w].Slots) if (g.Scores.ContainsKey(players[pi].Id)) wins[pi]++;
            }
            else wins[w]++;
        }

        /// <summary>The points scored against the player on side `si` in game g:
        /// the other side's points (its first member with a key); -1 when the
        /// game does not say, and always for FFA (no "against").</summary>
        private static int OpponentPoints(string kind, Game g, IList<Player> players, IList<Side> sides, int si)
        {
            if (!TwoSided(kind, sides) || si < 0 || si > 1) return -1;
            foreach (int oi in sides[1 - si].Slots)
            {
                int v;
                if (g.Points.TryGetValue(players[oi].Id, out v)) return v;
            }
            return -1;
        }

        /// <summary>A 1v1 fighter's rounds for the replay maths, where both
        /// fighters of every game carry a key. Never a label: a rendered score
        /// goes through Standings / SideScore, which omit a missing key.</summary>
        internal static int Score(Game g, string id)
        {
            int v;
            return g.Scores.TryGetValue(id, out v) ? v : 0;
        }

        // -- round 2, M1: who played a game (pure) ----------------------------

        /// <summary>The roster indices of the players who PLAYED game g (a
        /// score key in it), best score first, roster order on a tie. A player
        /// of a fluid lobby's union roster with no key in g sat that game out:
        /// they are not in its standings, so no header, divider or row of that
        /// game names them, and a missing key is never read as a score.</summary>
        internal static List<int> Standings(Game g, IList<Player> players)
        {
            var order = new List<int>();
            if (g == null || players == null) return order;
            for (int i = 0; i < players.Count; i++)
                if (g.Scores.ContainsKey(players[i].Id)) order.Add(i);
            order.Sort((x, y) =>
            {
                int c = g.Scores[players[y].Id].CompareTo(g.Scores[players[x].Id]);
                return c != 0 ? c : x.CompareTo(y);
            });
            return order;
        }

        /// <summary>A two-sided game's score for side `team` (every player of a
        /// side carries the side's rounds): the key of the side's first roster
        /// player who played g, and `at` that player's roster index; -1 (and
        /// at = -1) when nobody of the side has a key in g.</summary>
        internal static int SideScore(Game g, IList<Player> players, int team, out int at)
        {
            at = -1;
            if (g == null || players == null) return -1;
            for (int i = 0; i < players.Count; i++)
            {
                int v;
                if (players[i].Team != team || !g.Scores.TryGetValue(players[i].Id, out v)) continue;
                at = i;
                return v;
            }
            return -1;
        }

        /// <summary>A two-sided game's pair of scores - side 1's, then side 2's -
        /// only when EACH side has a member with a key in g (a missing key is
        /// never a 0, round 2 M1); `ia` and `ib` are the roster indices of the
        /// members whose keys were read (each side's first playing member), for
        /// the label's colour. False for FFA and for a roster the kind cannot
        /// pair: the caller lists the standings instead.</summary>
        internal static bool SideScores(string kind, Game g, IList<Player> players, IList<Side> sides,
                                        out int sa, out int sb, out int ia, out int ib)
        {
            sa = sb = 0;
            ia = ib = -1;
            if (g == null || players == null || !TwoSided(kind, sides)) return false;
            sa = SideScoreOf(g, players, sides[0], out ia);
            sb = SideScoreOf(g, players, sides[1], out ib);
            if (ia >= 0 && ib >= 0) return true;
            sa = sb = 0;
            return false;
        }

        internal static List<Pt> Stream(Game g, string id, string name)
        {
            Dictionary<string, List<Pt>> streams;
            List<Pt> s;
            if (g.Timelines.TryGetValue(id, out streams) && streams != null && streams.TryGetValue(name, out s)) return s;
            return null;
        }

        // -- board row 30e: the race axis (pure) --------------------------------

        /// <summary>A game is won at 5 rounds in 1v1, 2v2 and 1v2
        /// (GameStateWatcher's roundsToWin default, read from GM.roundsToWinGame
        /// at runtime; the mod changes it for none of them). An FFA game plays
        /// its lobby's score target, and only a RECORDED one counts: the server
        /// sends settings=null for a game with no settings record, on purpose
        /// (early FFA games were first-to-3, so the server reports unknown
        /// rather than a plausible value), and such a game's target is
        /// TARGET_UNKNOWN - never a guessed default (round 2 M2).</summary>
        internal const int ROUNDS_TO_WIN = 5;
        internal const int TARGET_UNKNOWN = 0;

        /// <summary>The rounds a game is played to: the top of its race axis;
        /// TARGET_UNKNOWN for an FFA game whose settings are not recorded.</summary>
        internal static int WinTarget(string kind, Game g)
        {
            if (kind == "ffa") return g != null && g.ScoreTarget > 0 ? g.ScoreTarget : TARGET_UNKNOWN;
            return ROUNDS_TO_WIN;
        }

        /// <summary>The race's y-axis top over the games of a set: the highest
        /// KNOWN target, raised to the highest recorded value (`recordedTop`)
        /// so nothing is clipped, at least 1. `unknown` counts the games whose
        /// target is not recorded; with every target unknown the axis ends at
        /// the top recorded score - no race to a guessed number is drawn, and
        /// the view says the target is not recorded (round 2 M2).</summary>
        internal static float RaceTop(string kind, IList<Game> games, float recordedTop, out int unknown)
        {
            unknown = 0;
            float top = 1f;
            if (games != null)
                foreach (var g in games)
                {
                    int t = WinTarget(kind, g);
                    if (t == TARGET_UNKNOWN) unknown++;
                    else top = Math.Max(top, t);
                }
            if (!float.IsNaN(recordedTop)) top = Math.Max(top, recordedTop);
            return (float)Math.Ceiling(top);
        }

        /// <summary>A score stream's value per round won: 2 in 1v1, 2v2 and 1v2
        /// (the recorder's TimelineAppend writes rounds * 2 + points for both
        /// sides; since ask 9 a 2v2 / 1v2 match uploads the pairs too and the
        /// server carries each side's stream, so every two-sided kind races - a
        /// game recorded before that has no stream and shows its end score as
        /// the race's dot), 1 in FFA (rounds plus half a point per live half-point).</summary>
        internal static float RaceDivisor(string kind)
        {
            return kind == "ffa" ? 1f : POINTS_PER_ROUND;
        }

        /// <summary>The rounds won at every sample of a score stream:
        /// floor(value / per). With `progress` the within-round part is kept
        /// (value / per) - the race panel's thin secondary line.</summary>
        internal static List<Pt> RoundsSeries(List<Pt> s, float per, bool progress)
        {
            var o = new List<Pt>(s == null ? 0 : s.Count);
            if (s == null || per <= 0f) return o;
            foreach (var p in s)
            {
                float v = Math.Max(0f, p.Y) / per;
                o.Add(new Pt(p.X, progress ? v : (float)Math.Floor(v + 0.0001f)));
            }
            return o;
        }

        // -- board row 30g: the broadcaster's playback (pure) ----------------------

        /// <summary>The broadcaster's dwell per session report page when the
        /// config names none or a value that cannot be a dwell (0 or less,
        /// NaN, infinite), and the bounds any other value is held to.</summary>
        internal const float BROADCAST_PAGE_SECONDS = 12f, BROADCAST_PAGE_MIN_SECONDS = 3f, BROADCAST_PAGE_MAX_SECONDS = 300f;

        internal static float BroadcastPageDwell(float configured)
        {
            if (float.IsNaN(configured) || float.IsInfinity(configured) || configured <= 0f)
                return BROADCAST_PAGE_SECONDS;
            return Math.Min(BROADCAST_PAGE_MAX_SECONDS, Math.Max(BROADCAST_PAGE_MIN_SECONDS, configured));
        }

        /// <summary>The page after `page` in the broadcaster's walk, or -1 once
        /// every page has been shown. `pages` is the count the view measured at
        /// this screen size (the fixed pages plus the builds pages); a count
        /// that shrank to or below the current page ends the walk rather than
        /// wrapping.</summary>
        internal static int BroadcastNextPage(int page, int pages)
        {
            int next = page + 1;
            return next >= 1 && next < pages ? next : -1;
        }

        // -- round 2 M3: the one gate into the broadcaster's playback (pure) ------

        internal const int PLAYBACK_DEFER = 0, PLAYBACK_REPORT = 1, PLAYBACK_SCREENS = 2;

        /// <summary>Whether the broadcaster may start playing a queued set: only
        /// while the stream is live, or for the dev lever's own entry (a seat
        /// under a maintenance pause has no stream). The stream is ASKED here,
        /// at the moment of the decision, never taken from a value read before
        /// a fetch; a probe that throws or is missing reads as not live.</summary>
        internal static bool PlaybackMayStart(Func<bool> streamLive, bool devEntry)
        {
            if (devEntry) return true;
            try { return streamLive != null && streamLive(); }
            catch { return false; }
        }

        /// <summary>Where a finished fetch enters: PLAYBACK_DEFER unless
        /// PlaybackMayStart; then the session report when a model was built,
        /// else the screens (its fallback: an HTTP failure, the timeout, a body
        /// that is not an envelope, or no anchor). Every outcome passes this one
        /// gate - success, failure and timeout alike.</summary>
        internal static int PlaybackAfterFetch(bool haveModel, Func<bool> streamLive, bool devEntry)
        {
            if (!PlaybackMayStart(streamLive, devEntry)) return PLAYBACK_DEFER;
            return haveModel ? PLAYBACK_REPORT : PLAYBACK_SCREENS;
        }

        // Round 2 L1: the report's metric names, one per chart / bar set /
        // table whose data can be absent.
        internal const string MET_DAMAGE = "damage", MET_SCORE = "score", MET_HIT = "hit", MET_BLOCK = "block",
                              MET_PING = "ping", MET_FPS = "fps", MET_DAMAGE_TOTAL = "damage_total",
                              MET_KILLS = "kills", MET_XP = "xp", MET_COMBAT = "combat", MET_GOLD = "gold",
                              MET_PLAY = "play", MET_DURATION = "duration";
        internal const int MISSING_SET = 1, MISSING_MODE = 2;

        // What a set of each mode CAN carry: what the server's loader for that
        // mode puts on a game (backend/api/main.py _report_load_1v1 / _team /
        // _ovt / _ffa - the timeline streams, the totals counters, XP; 1v1
        // kills are the other fighter's recorded deaths) plus what every mode
        // records (gold, picks and points, game length). The score race
        // (MET_SCORE) is carried by every mode: 1v1 and FFA games carry its
        // point stream, and every game's end scores are drawn as the race's
        // dots (SessionReportModel.FinishRace) - for 2v2 and 1v2 those dots are
        // the whole race (round 3 L1) until a game recorded under migration 403
        // (ask 9): the server then carries each side's point stream, per-player
        // damage, kills and deaths, and 1v2's full telemetry, in the 1v1 keys,
        // so 2v2 and 1v2 carry what 1v1 carries except XP.
        // backend/tests/test_session_report.py executes the four loaders on
        // saturated rows and compares with these lists, in both directions.
        private static readonly string[] CARRIES_1V1 = { MET_DAMAGE, MET_SCORE, MET_HIT, MET_BLOCK, MET_PING, MET_FPS,
            MET_DAMAGE_TOTAL, MET_KILLS, MET_XP, MET_COMBAT, MET_GOLD, MET_PLAY, MET_DURATION };
        private static readonly string[] CARRIES_TEAM = { MET_DAMAGE, MET_SCORE, MET_HIT, MET_BLOCK, MET_PING, MET_FPS,
            MET_DAMAGE_TOTAL, MET_KILLS, MET_COMBAT, MET_GOLD, MET_PLAY, MET_DURATION };
        private static readonly string[] CARRIES_OVT = { MET_DAMAGE, MET_SCORE, MET_HIT, MET_BLOCK, MET_PING, MET_FPS,
            MET_DAMAGE_TOTAL, MET_KILLS, MET_COMBAT, MET_GOLD, MET_PLAY, MET_DURATION };
        private static readonly string[] CARRIES_FFA = { MET_DAMAGE, MET_SCORE, MET_HIT, MET_BLOCK, MET_PING, MET_FPS,
            MET_DAMAGE_TOTAL, MET_KILLS, MET_XP, MET_COMBAT, MET_GOLD, MET_PLAY, MET_DURATION };

        /// <summary>Round 2 L1: whether some set of `kind` can carry `metric`.
        /// A kind this build does not know makes no claim about its mode (true:
        /// the set simply has none).</summary>
        internal static bool ModeCarries(string kind, string metric)
        {
            string[] carries;
            switch (kind)
            {
                case "ranked": case "casual": carries = CARRIES_1V1; break;
                case "team": carries = CARRIES_TEAM; break;
                case "ovt": carries = CARRIES_OVT; break;
                case "ffa": carries = CARRIES_FFA; break;
                default: return true;
            }
            return Array.IndexOf(carries, metric) >= 0;
        }

        /// <summary>Round 2 L1: why a set of `kind` shows no `metric` -
        /// MISSING_SET when the mode carries it (this set has none recorded),
        /// MISSING_MODE only when no set of the mode can carry it.</summary>
        internal static int MissingReason(string kind, string metric)
        {
            return ModeCarries(kind, metric) ? MISSING_SET : MISSING_MODE;
        }

        /// <summary>Round 2 M4: whether a dev lever that replays a recorded set
        /// may run against the API this client is configured for - ONLY a
        /// local test server: exactly "localhost", or a loopback address
        /// (127.0.0.0/8, ::1). Production (the public host, and the LAN
        /// addresses of the backend boxes and the edge that the seat's cfg
        /// uses) and every other host refuse; so does a URL with user info or
        /// one that does not parse. `host` is what the URL named, for the
        /// refusal's log line ("" when it did not parse).</summary>
        internal static bool DevLeverApiAllowed(string baseUrl, out string host)
        {
            host = "";
            Uri uri;
            if (string.IsNullOrEmpty(baseUrl) || !Uri.TryCreate(baseUrl.Trim(), UriKind.Absolute, out uri)) return false;
            host = uri.Host ?? "";
            if (!string.IsNullOrEmpty(uri.UserInfo)) return false;
            if (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps) return false;
            if (string.Equals(host, "localhost", StringComparison.OrdinalIgnoreCase)) return true;
            System.Net.IPAddress ip;
            return System.Net.IPAddress.TryParse(host.Trim('[', ']'), out ip) && System.Net.IPAddress.IsLoopback(ip);
        }

        /// <summary>Round 4 LOW 2: whether a report-status answer may replace
        /// the broadcaster's target, and with what. The server answers each
        /// game with the account's own watch GRANT (mode and roster together)
        /// and the report read accepts only a granted tuple, so an answer is
        /// adopted WHOLE or not at all - never its roster under the target's
        /// old mode. Adoptable: a mode the broadcaster plays (1v1, 2v2, ffa)
        /// with a roster of at least two distinct steam ids, exactly two for
        /// a 1v1 (the read compares a sourceless 1v1's played pair with the
        /// granted roster exactly). `ids` is the roster in the answer's
        /// order; on refusal `playMode` is "" and `ids` empty.</summary>
        internal static bool StatusTarget(string mode, string rosterCsv, out string playMode, out string[] ids)
        {
            playMode = "";
            ids = new string[0];
            string m = (mode ?? "").Trim().ToLowerInvariant();
            if (m != "1v1" && m != "2v2" && m != "ffa") return false;
            var list = new List<string>();
            foreach (var part in (rosterCsv ?? "").Split(','))
            {
                string id = part.Trim();
                if (id.Length == 0) continue;
                if (list.Contains(id)) return false;
                list.Add(id);
            }
            if (list.Count < 2 || (m == "1v1" && list.Count != 2)) return false;
            playMode = m;
            ids = list.ToArray();
            return true;
        }

        /// <summary>A game the broadcaster may anchor the watched set's report
        /// on: its id, its end (server UTC) and the steam ids of the players
        /// who PLAYED it (an FFA frozen-roster ghost is not one).</summary>
        internal sealed class AnchorGame
        {
            public string Id = "";
            public DateTime End;
            public readonly List<string> Played = new List<string>();
        }

        /// <summary>The anchor of the watched set's report: the NEWEST game
        /// ending inside [lo, hi] whose id is a UUID (the route's selectors
        /// are), and the player to ask for it - `preferred` when they played
        /// it, else the first player of `roster` who did. Null, with no viewer,
        /// when no game qualifies or nobody of the roster played the newest.</summary>
        internal static AnchorGame NewestAnchor(IList<AnchorGame> games, DateTime lo, DateTime hi,
                                                string preferred, IList<string> roster, out string viewer)
        {
            viewer = null;
            AnchorGame best = null;
            if (games == null) return null;
            foreach (var g in games)
            {
                if (g == null || g.End < lo || g.End > hi) continue;
                Guid parsed;
                if (!Guid.TryParse(g.Id ?? "", out parsed)) continue;
                if (best == null || g.End > best.End) best = g;
            }
            if (best == null) return null;
            if (!string.IsNullOrEmpty(preferred) && best.Played.Contains(preferred)) { viewer = preferred; return best; }
            if (roster != null)
                foreach (var id in roster)
                    if (!string.IsNullOrEmpty(id) && best.Played.Contains(id)) { viewer = id; return best; }
            return null;
        }

        // -- series maths (pure) -----------------------------------------------

        /// <summary>Value of a cumulative series at time x (0 at or before the
        /// origin, linear between samples, held after the last one) for a
        /// NON-DECREASING run of x: `j` is the first sample at or after the
        /// previous x and only advances, so a pass over a series costs O(n)
        /// where a search from the start costs O(n^2) (ask 9 stage C; the
        /// self-test holds it equal to the per-sample definition on a grid).</summary>
        private static float AtFrom(List<Pt> s, float x, ref int j)
        {
            if (s == null || s.Count == 0 || x <= 0f) return 0f;
            while (j < s.Count && s[j].X < x) j++;
            if (j >= s.Count) return s[s.Count - 1].Y;
            float px = j > 0 ? s[j - 1].X : 0f, pv = j > 0 ? s[j - 1].Y : 0f;
            float span = s[j].X - px;
            return span <= 0f ? s[j].Y : pv + (s[j].Y - pv) * ((x - px) / span);
        }

        /// <summary>Rate over the trailing window at each sample time:
        /// (v(t) - v(t - w)) / w, clamped at 0 (a counter reset is not a
        /// negative rate). Needs two samples to mean anything.</summary>
        internal static List<Pt> Rolling(List<Pt> cum, float window)
        {
            var out_ = new List<Pt>();
            if (cum == null || cum.Count < 2 || window <= 0f) return out_;
            int j = 0;
            for (int i = 0; i < cum.Count; i++)
            {
                float t = cum[i].X;
                float d = cum[i].Y - AtFrom(cum, t - window, ref j);
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
            int jd = 0, jn0 = 0, jn1 = 0;
            for (int i = 0; i < den.Count; i++)
            {
                float t = den[i].X;
                float dd = den[i].Y - AtFrom(den, t - window, ref jd);
                if (dd < minDen) continue;
                float dn = AtFrom(num, t, ref jn1) - AtFrom(num, t - window, ref jn0);
                out_.Add(new Pt(t, Math.Max(0f, Math.Min(100f, 100f * dn / dd))));
            }
            return out_;
        }

        /// <summary>The rolling window for a stream the server decimated (lesson
        /// 318: the sample stride doubles with the cap, so a long game's samples
        /// are sparser): at least `minWindow`, and at least five median sample
        /// spacings, so a window always spans several samples and a long game's
        /// rate line does not turn into a comb of single-sample spikes.</summary>
        internal static float StrideWindow(List<Pt> s, float minWindow)
        {
            if (s == null || s.Count < 3) return minWindow;
            var gaps = new List<float>(s.Count - 1);
            for (int i = 1; i < s.Count; i++) gaps.Add(Math.Max(0f, s[i].X - s[i - 1].X));
            gaps.Sort();
            return Math.Max(minWindow, 5f * gaps[gaps.Count / 2]);
        }

        // -- ask 9 stage C: colour, Unity-free (OKLab) ------------------------------

        /// <summary>The report's categorical slots for a player whose in-game
        /// colour the server does not send: the dataviz skill's validated dark
        /// set (on the report's backdrop every adjacent pair passes the
        /// colour-vision and normal-vision separation checks and 3:1 contrast).
        /// Never cycled: a ninth such player takes MUTED_HEX and is told apart by
        /// its label (the validator's rule for a palette past eight).</summary>
        internal static readonly string[] SLOT_HEX =
            { "#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767" };
        /// <summary>The ink tokens: values and captions wear these, never a series colour.</summary>
        internal const string INK_HEX = "#f0efec", INK2_HEX = "#c3c2b7", MUTED_HEX = "#898781";
        /// <summary>The band a series colour is held to on the dark backdrop (the
        /// validator's dark-mode lightness band and chroma floor, OKLab): a
        /// player's in-game HUE is kept - it is the identity players already
        /// know - its lightness clamped into the band and a faint colour
        /// deepened to the chroma floor, so a white or pastel in-game colour
        /// still reads as a line. A grey (chroma under TINT_C_GREY: no hue to
        /// keep) only has its lightness fixed.</summary>
        internal const float TINT_L_MIN = 0.48f, TINT_L_MAX = 0.67f, TINT_C_MIN = 0.10f, TINT_C_GREY = 0.02f;

        /// <summary>The stat tint's thirteen steps, worst (step -6, index 0)
        /// through the neutral ink (step 0, index 6) to best (step +6, index 12):
        /// OKLab interpolation from INK_HEX to the good pole #0ca30c and to the
        /// red pole #da5f59 (one step short of the status palette's critical
        /// #d03b3b, whose 4.0:1 fails as small text). Every step is at least
        /// 5.3:1 on the backdrop and lightness falls monotonically from the middle
        /// outwards. The number is always printed beside its tint: the colour
        /// never carries the meaning alone.</summary>
        internal static readonly string[] DIVERGE_HEX =
        {
            "#da5f59", "#e17971", "#e69189", "#eba9a1", "#eec1ba", "#f0d8d3",
            "#f0efec",
            "#d1e3cc", "#b2d7ac", "#93cb8c", "#72be6a", "#4cb146", "#0ca30c",
        };
        internal const int DIVERGE_STEPS = 6;

        /// <summary>"#rrggbb" (a leading '#' optional, a trailing alpha pair
        /// ignored, "#rgb" expanded) -> channels in 0..1; false for anything else.</summary>
        internal static bool ParseHex(string hex, out float r, out float g, out float b)
        {
            r = g = b = 0f;
            if (string.IsNullOrEmpty(hex)) return false;
            string h = hex.Trim();
            if (h.StartsWith("#")) h = h.Substring(1);
            if (h.Length == 3) h = new string(new[] { h[0], h[0], h[1], h[1], h[2], h[2] });
            if (h.Length == 8) h = h.Substring(0, 6);
            if (h.Length != 6) return false;
            int rr, gg, bb;
            if (!int.TryParse(h.Substring(0, 2), NumberStyles.HexNumber, INV, out rr)
                || !int.TryParse(h.Substring(2, 2), NumberStyles.HexNumber, INV, out gg)
                || !int.TryParse(h.Substring(4, 2), NumberStyles.HexNumber, INV, out bb)) return false;
            r = rr / 255f; g = gg / 255f; b = bb / 255f;
            return true;
        }

        internal static string ToHex(float r, float g, float b)
        {
            return "#" + ((int)Math.Round(Clamp01(r) * 255f)).ToString("x2", INV)
                       + ((int)Math.Round(Clamp01(g) * 255f)).ToString("x2", INV)
                       + ((int)Math.Round(Clamp01(b) * 255f)).ToString("x2", INV);
        }

        private static float Clamp01(float v) => v < 0f ? 0f : v > 1f ? 1f : v;
        private static double Lin(double c) => c <= 0.04045 ? c / 12.92 : Math.Pow((c + 0.055) / 1.055, 2.4);
        private static double Gam(double c) => c <= 0.0031308 ? 12.92 * c : 1.055 * Math.Pow(c, 1.0 / 2.4) - 0.055;
        private static double Cbrt(double x) => x >= 0 ? Math.Pow(x, 1.0 / 3.0) : -Math.Pow(-x, 1.0 / 3.0);

        /// <summary>sRGB (0..1) -> OKLab (Bjorn Ottosson's matrices).</summary>
        internal static void ToOklab(float r, float g, float b, out float L, out float a, out float bb)
        {
            double rl = Lin(Clamp01(r)), gl = Lin(Clamp01(g)), bl = Lin(Clamp01(b));
            double l = Cbrt(0.4122214708 * rl + 0.5363325363 * gl + 0.0514459929 * bl);
            double m = Cbrt(0.2119034982 * rl + 0.6806995451 * gl + 0.1073969566 * bl);
            double s = Cbrt(0.0883024619 * rl + 0.2817188376 * gl + 0.6299787005 * bl);
            L = (float)(0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s);
            a = (float)(1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s);
            bb = (float)(0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s);
        }

        /// <summary>OKLab -> sRGB (0..1), unclamped: a channel outside 0..1 means
        /// the colour is out of the sRGB gamut.</summary>
        internal static void FromOklab(float L, float a, float bb, out float r, out float g, out float b)
        {
            double l_ = L + 0.3963377774 * a + 0.2158037573 * bb;
            double m_ = L - 0.1055613458 * a - 0.0638541728 * bb;
            double s_ = L - 0.0894841775 * a - 1.2914855480 * bb;
            double l = l_ * l_ * l_, m = m_ * m_ * m_, s = s_ * s_ * s_;
            r = (float)Gam(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s);
            g = (float)Gam(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s);
            b = (float)Gam(-0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s);
        }

        /// <summary>Holds a series colour to the dark band (TINT_*): hue kept,
        /// lightness clamped, chroma raised to the floor, then chroma eased back
        /// until the colour is inside the sRGB gamut. A colour already in the
        /// band is a fixed point (the eight SLOT_HEX are).</summary>
        internal static void SnapTint(ref float r, ref float g, ref float b)
        {
            float L, a, bb;
            ToOklab(r, g, b, out L, out a, out bb);
            double C = Math.Sqrt((double)a * a + (double)bb * bb), h = Math.Atan2(bb, a);
            L = L < TINT_L_MIN ? TINT_L_MIN : L > TINT_L_MAX ? TINT_L_MAX : L;
            if (C >= TINT_C_GREY && C < TINT_C_MIN) C = TINT_C_MIN;
            for (int k = 0; k < 24; k++)
            {
                float rr, gg, b2;
                FromOklab(L, (float)(C * Math.Cos(h)), (float)(C * Math.Sin(h)), out rr, out gg, out b2);
                if (rr >= -0.002f && rr <= 1.002f && gg >= -0.002f && gg <= 1.002f && b2 >= -0.002f && b2 <= 1.002f)
                {
                    r = Clamp01(rr); g = Clamp01(gg); b = Clamp01(b2);
                    return;
                }
                C *= 0.92;
            }
            float r3, g3, b3;
            FromOklab(L, 0f, 0f, out r3, out g3, out b3);
            r = Clamp01(r3); g = Clamp01(g3); b = Clamp01(b3);
        }

        /// <summary>The discovered range of one statistic over a page's values
        /// (every player, every game): a value's tint step is its distance from
        /// the average in sixths of the way to the discovered extreme on its
        /// side - DIVERGE_STEPS (the best) .. 0 (the average: ink) .. -DIVERGE_STEPS
        /// (the worst), the index into DIVERGE_HEX being step + DIVERGE_STEPS. A
        /// small spread stays near ink: the distance is measured against the
        /// larger of the spread and half the average, so 10 kills against 11 do
        /// not read as a rout. `lowerIsBetter` (deaths, ping) flips the sign.</summary>
        internal sealed class StatScale
        {
            public int Count;
            public float Sum, Min = float.MaxValue, Max = float.MinValue;

            public void Add(float v)
            {
                if (float.IsNaN(v) || float.IsInfinity(v)) return;
                Count++;
                Sum += v;
                if (v < Min) Min = v;
                if (v > Max) Max = v;
            }

            public void Add(float? v) { if (v.HasValue) Add(v.Value); }

            public float Avg => Count > 0 ? Sum / Count : 0f;

            public int Step(float v, bool lowerIsBetter)
            {
                if (Count < 2 || float.IsNaN(v) || float.IsInfinity(v)) return 0;
                float avg = Avg, floor = 0.5f * Math.Abs(avg), dv = v - avg;
                float span = Math.Max(dv >= 0f ? Max - avg : avg - Min, floor);
                if (span <= 0f) return 0;
                int step = (int)Math.Round(DIVERGE_STEPS * dv / span, MidpointRounding.AwayFromZero);
                step = Math.Max(-DIVERGE_STEPS, Math.Min(DIVERGE_STEPS, step));
                return lowerIsBetter ? -step : step;
            }

            public int Step(float? v, bool lowerIsBetter) => v.HasValue ? Step(v.Value, lowerIsBetter) : 0;
        }
    }
}
