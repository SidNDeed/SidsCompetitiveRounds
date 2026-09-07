using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Sept 6 batch (Group 4 item c) — the PURE view-model behind the
    /// interactive session report. Two halves, both free of Unity UI:
    ///
    ///  1. <see cref="Parse"/> turns the server's versioned envelope
    ///     (GET /api/v1/report, v1) into <see cref="Envelope"/>. Manual,
    ///     string-aware parsing only: JsonUtility fails silently on nested
    ///     arrays, and this payload is nothing but nested arrays. Objects and
    ///     arrays are sliced with ApiClient's string-aware bracket/brace
    ///     matchers so a display name containing '{' or '"' cannot split a
    ///     member (learning #156). Every statistic is keyed by the player's
    ///     steam id as a string; there is NO viewer-relative field anywhere and
    ///     nothing here asks "who is me".
    ///
    ///  2. <see cref="Build"/> turns an Envelope into <see cref="Model"/>: the
    ///     four pages' polylines, tables and labels, pre-composed once (#162)
    ///     so the IMGUI pager (<see cref="SessionReportView"/>) only draws.
    ///     Games are laid end to end on ONE seconds axis with explicit per-game
    ///     offsets (design C-6); rolling DPS / hit % / block % are computed over
    ///     SECONDS (a 15 s window against the cumulative series), never over
    ///     sample counts — the stored cadence is variable after decimation
    ///     (#318). Set-level numbers (rating, gold) come from the envelope's
    ///     set_summary ONCE and are never summed over games (C-7). A stream a
    ///     mode does not record renders as an explicit "not recorded" panel
    ///     (C-5) rather than an empty chart.
    ///
    /// Everything server-authored that reaches a rich-text label passes
    /// <see cref="Safe"/> (tag characters stripped, length capped) — server
    /// strings are hostile input (#100/#156).</summary>
    internal static class SessionReportModel
    {
        /// <summary>Rolling-window length for DPS / hit % / block %.</summary>
        internal const float WINDOW_S = 15f;
        internal const int PAGE_COUNT = 4;
        private const int NAME_CAP = 18;
        private static readonly CultureInfo INV = CultureInfo.InvariantCulture;

        // ── envelope (wire shape, v1) ────────────────────────────────────────

        internal sealed class Player
        {
            public string Id = "", Name = "", ColorHex = "";
            public int Team;
        }

        internal sealed class Pick { public string Id = "", Card = ""; }

        internal sealed class Death { public float T; public string Id = ""; }

        internal sealed class Game
        {
            public string MatchId = "", StartedAt = "";
            public float DurationS;
            public readonly Dictionary<string, int> Scores = new Dictionary<string, int>();
            public readonly Dictionary<string, int> Points = new Dictionary<string, int>();
            /// <summary>player id -> stream name -> [t, v] samples, t in seconds
            /// from this game's start (server-stamped; kept, never re-gridded).</summary>
            public readonly Dictionary<string, Dictionary<string, List<Vector2>>> Timelines
                = new Dictionary<string, Dictionary<string, List<Vector2>>>();
            public readonly HashSet<string> Available = new HashSet<string>();
            public readonly List<Pick> Picks = new List<Pick>();
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
            public readonly List<Player> Players = new List<Player>();
            public readonly List<Game> Games = new List<Game>();
            public readonly Dictionary<string, RatingEntry> Rating = new Dictionary<string, RatingEntry>();
            public readonly Dictionary<string, int> Gold = new Dictionary<string, int>();
        }

        // ── parse ────────────────────────────────────────────────────────────

        /// <summary>Envelope or null when the text is not a JSON object. A
        /// version other than 1 still parses (the view says so) — the field
        /// exists precisely so a future shape can be told apart from garbage.</summary>
        internal static Envelope Parse(string json)
        {
            if (string.IsNullOrEmpty(json)) return null;
            int ob = json.IndexOf('{');
            if (ob < 0) return null;
            int oe = ApiClient.FindMatchingBraceStringAware(json, ob);
            if (oe < 0) return null;
            var env = new Envelope();
            foreach (var kv in Members(json, ob, oe))
            {
                switch (kv.Key)
                {
                    case "v": env.V = (int)Num(kv.Value, 0f); break;
                    case "kind": env.Kind = Str(kv.Value); break;
                    case "truncated": env.Truncated = kv.Value == "true"; break;
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
                            var streams = new Dictionary<string, List<Vector2>>();
                            foreach (var st in Members(pl.Value))
                            {
                                var pts = new List<Vector2>();
                                foreach (string pair in Elements(st.Value))
                                {
                                    var tv = Elements(pair);
                                    if (tv.Count < 2) continue;
                                    float t = Num(tv[0], float.NaN), v = Num(tv[1], float.NaN);
                                    if (float.IsNaN(t) || float.IsNaN(v)) continue;
                                    pts.Add(new Vector2(t, v));
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
                            }
                            if (pk.Id.Length > 0 && pk.Card.Length > 0) g.Picks.Add(pk);
                        }
                        break;
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

        // ── JSON primitives (string-aware, top-level only) ───────────────────

        /// <summary>The members of the object whose braces sit at [ob, oe]
        /// (inclusive) — key plus the RAW value text, so nested objects and
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
            int oe = ApiClient.FindMatchingBraceStringAware(obj, ob);
            return Members(obj, ob, oe);
        }

        /// <summary>Raw element texts of a JSON array (nested structures whole).</summary>
        internal static List<string> Elements(string arr)
        {
            var list = new List<string>();
            if (string.IsNullOrEmpty(arr)) return list;
            int ab = arr.IndexOf('[');
            if (ab < 0) return list;
            int ae = ApiClient.FindMatchingBracketStringAware(arr, ab);
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
            if (c == '{') { int e = ApiClient.FindMatchingBraceStringAware(s, i); return e < limit ? e : -1; }
            if (c == '[') { int e = ApiClient.FindMatchingBracketStringAware(s, i); return e < limit ? e : -1; }
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

        // ── view model ───────────────────────────────────────────────────────

        internal sealed class Poly
        {
            public string PlayerId;
            public Color Tint;
            public List<Vector2> Pts;    // x = seconds on the SESSION axis
        }

        internal sealed class Mark
        {
            public float X;              // session seconds
            public Color Tint;
            public int Lane;             // stacking lane (player index)
        }

        internal sealed class Panel
        {
            public string Title = "";
            public string Unit = "";
            /// <summary>Set when nothing was recorded: the text to show instead of axes.</summary>
            public string Missing;
            public bool Percent;
            public float MaxY = 1f;
            public readonly List<Poly> Lines = new List<Poly>();
        }

        internal sealed class Span
        {
            public float X0, X1;
            public string LabelLong = "", LabelShort = "";
            public readonly List<Mark> Picks = new List<Mark>();
        }

        internal sealed class BuildBlock
        {
            public string Title = "";    // "Game 2 - Spirit" (name in colour)
            public string Cards = "";    // comma-joined picks, or the no-build text
            public string Stats = "";    // BuildStatsTipBlock body, "" when not recorded
        }

        internal sealed class Model
        {
            public Envelope Env;
            public string Kind = "";
            public readonly List<Player> Players = new List<Player>();
            public readonly List<Color> Tints = new List<Color>();
            public string Header = "", Legend = "", Sub = "", Note = "";
            public float TotalS = 1f;
            public readonly List<Span> Spans = new List<Span>();
            public readonly List<Mark> Deaths = new List<Mark>();
            // page 1
            public Panel Damage, Score;
            // page 2
            public Panel Dps, HitPct, BlockPct, Ping, Fps;
            // page 3
            public readonly List<string> TotalsHeader = new List<string>();
            public readonly List<List<string>> TotalsRows = new List<List<string>>();
            public readonly List<string> SummaryLines = new List<string>();
            // page 4
            public readonly List<BuildBlock> Builds = new List<BuildBlock>();
            public string BuildsMissing;
            public readonly string[] PageTitles = new string[PAGE_COUNT];
        }

        private static readonly string[] PALETTE =
            { "#99B3E6", "#E69988", "#8FD18F", "#E6C866", "#C48CFF", "#66D9E6", "#FFB347", "#F28CC8" };

        internal static Model Build(Envelope env)
        {
            var m = new Model { Env = env, Kind = env.Kind ?? "" };
            string missing = I18n.Tr("not recorded for this mode");
            m.PageTitles[0] = I18n.Tr("Timeline");
            m.PageTitles[1] = I18n.Tr("Rates");
            m.PageTitles[2] = I18n.Tr("Totals");
            m.PageTitles[3] = I18n.Tr("Builds");

            // Roster, colours, legend.
            var idx = new Dictionary<string, int>();
            for (int i = 0; i < env.Players.Count; i++)
            {
                var p = env.Players[i];
                if (idx.ContainsKey(p.Id)) continue;
                idx[p.Id] = m.Players.Count;
                m.Players.Add(p);
                Color c;
                if (!ColorUtility.TryParseHtmlString(p.ColorHex ?? "", out c)
                    && !ColorUtility.TryParseHtmlString(PALETTE[i % PALETTE.Length], out c))
                    c = Color.white;
                c.a = 1f;
                m.Tints.Add(c);
            }
            var legend = new StringBuilder();
            for (int i = 0; i < m.Players.Count; i++)
            {
                if (i > 0) legend.Append("   ");
                legend.Append(Coloured(m, i, Safe(m.Players[i].Name)));
            }
            m.Legend = legend.ToString();

            // Session axis: games end to end, each spanning its own duration.
            float x0 = 0f;
            var setWins = new int[m.Players.Count];
            foreach (var g in env.Games)
            {
                float dur = g.DurationS > 0f ? g.DurationS : LongestT(g);
                if (dur < 1f) dur = 60f;
                var sp = new Span { X0 = x0, X1 = x0 + dur };
                x0 = sp.X1;
                int gi = m.Spans.Count + 1;
                if (m.Players.Count == 2)
                {
                    string a = m.Players[0].Id, b = m.Players[1].Id;
                    int sa = Get(g.Scores, a), sb = Get(g.Scores, b);
                    if (sa > sb) setWins[0]++; else if (sb > sa) setWins[1]++;
                    sp.LabelShort = sa.ToString(INV) + "-" + sb.ToString(INV);
                    sp.LabelLong = ScoreLine(m, 0, sa, 1, sb);
                }
                else
                {
                    sp.LabelShort = "G" + gi.ToString(INV);
                    sp.LabelLong = I18n.TrF("Game {0}", gi);
                }
                // Picks carry no timestamp in any mode: ticks on the divider, in
                // pick order, coloured by picker.
                foreach (var pk in g.Picks)
                {
                    int pi;
                    if (idx.TryGetValue(pk.Id, out pi))
                        sp.Picks.Add(new Mark { X = sp.X0, Tint = m.Tints[pi], Lane = pi });
                }
                foreach (var d in g.Deaths)
                {
                    int pi;
                    if (idx.TryGetValue(d.Id, out pi))
                        m.Deaths.Add(new Mark { X = sp.X0 + Mathf.Clamp(d.T, 0f, dur), Tint = m.Tints[pi], Lane = pi });
                }
                m.Spans.Add(sp);
            }
            m.TotalS = Mathf.Max(1f, x0);

            // Header: player-neutral, winner's name in colour (2 players); a
            // plain roster line otherwise.
            if (m.Players.Count == 2)
                m.Header = ScoreLine(m, 0, setWins[0], 1, setWins[1]);
            else
                m.Header = m.Legend;
            string kindLabel = KindLabel(m.Kind);
            m.Sub = I18n.TrF("{0} - {1} games - {2} played", kindLabel, env.Games.Count, Clock(m.TotalS));
            if (env.Truncated) m.Note = I18n.TrF("showing the newest {0} games of this sitting", env.Games.Count);
            if (env.V != 1) m.Note = I18n.TrF("report version {0} - some panels may be missing", env.V);

            // Page 1 — cumulative damage and the score race, per game segment.
            m.Damage = new Panel { Title = I18n.Tr("Damage dealt (cumulative per game)"), Unit = I18n.Tr("dmg") };
            m.Score = new Panel { Title = I18n.Tr("Score race (points per game)"), Unit = I18n.Tr("pts") };
            // Page 2 — rates over a 15 s window, plus the ping / fps strips.
            m.Dps = new Panel { Title = I18n.Tr("Rolling DPS (15 s window)"), Unit = I18n.Tr("dmg/s") };
            m.HitPct = new Panel { Title = I18n.Tr("Rolling hit % (15 s window)"), Unit = "%", Percent = true };
            m.BlockPct = new Panel { Title = I18n.Tr("Rolling block % (15 s window)"), Unit = "%", Percent = true };
            m.Ping = new Panel { Title = I18n.Tr("Ping"), Unit = I18n.Tr("ms") };
            m.Fps = new Panel { Title = I18n.Tr("FPS"), Unit = I18n.Tr("fps") };
            bool legacyBlocks = false;

            for (int gi = 0; gi < env.Games.Count; gi++)
            {
                var g = env.Games[gi];
                var sp = m.Spans[gi];
                for (int pi = 0; pi < m.Players.Count; pi++)
                {
                    string pid = m.Players[pi].Id;
                    Dictionary<string, List<Vector2>> streams;
                    if (!g.Timelines.TryGetValue(pid, out streams) || streams == null) continue;
                    List<Vector2> dmg, score, shots, hits, blocks, blocksOk, ping, fps;
                    streams.TryGetValue("damage", out dmg);
                    streams.TryGetValue("score", out score);
                    streams.TryGetValue("shots", out shots);
                    streams.TryGetValue("hits", out hits);
                    streams.TryGetValue("blocks", out blocks);
                    streams.TryGetValue("blocks_ok", out blocksOk);
                    streams.TryGetValue("ping", out ping);
                    streams.TryGetValue("fps", out fps);

                    if (dmg != null && dmg.Count > 0)
                    {
                        AddLine(m.Damage, pid, m.Tints[pi], Shift(dmg, sp.X0, true));
                        var dps = Rolling(dmg, WINDOW_S);
                        if (dps.Count > 0) AddLine(m.Dps, pid, m.Tints[pi], Shift(dps, sp.X0, false));
                    }
                    if (score != null && score.Count > 0)
                        AddLine(m.Score, pid, m.Tints[pi], Shift(score, sp.X0, true));
                    if (shots != null && hits != null && shots.Count > 0)
                    {
                        var hp = RollingRatio(hits, shots, WINDOW_S, 3f);
                        if (hp.Count > 0) AddLine(m.HitPct, pid, m.Tints[pi], Shift(hp, sp.X0, false));
                    }
                    if (blocks != null && blocksOk != null && blocks.Count > 0)
                    {
                        // Bug-181 era check: v2 block pairs are activated:successful and
                        // their last sample ends at the stored activation total; the
                        // legacy left value was damage taken, an unrelated quantity, so
                        // a legacy game renders as "not recorded" instead of a fake
                        // percentage.
                        Dictionary<string, float> tot;
                        float totBlocks;
                        bool legacy = g.Totals.TryGetValue(pid, out tot) && tot != null
                                      && tot.TryGetValue("blocks", out totBlocks)
                                      && blocks[blocks.Count - 1].y > totBlocks + 3f;
                        if (legacy) legacyBlocks = true;
                        else
                        {
                            var bp = RollingRatio(blocksOk, blocks, WINDOW_S, 1f);
                            if (bp.Count > 0) AddLine(m.BlockPct, pid, m.Tints[pi], Shift(bp, sp.X0, false));
                        }
                    }
                    if (ping != null && ping.Count > 0) AddLine(m.Ping, pid, m.Tints[pi], Shift(ping, sp.X0, false));
                    if (fps != null && fps.Count > 0) AddLine(m.Fps, pid, m.Tints[pi], Shift(fps, sp.X0, false));
                }
            }
            foreach (var pn in new[] { m.Damage, m.Score, m.Dps, m.HitPct, m.BlockPct, m.Ping, m.Fps })
                Finish(pn, missing);
            if (m.BlockPct.Missing != null && legacyBlocks)
                m.BlockPct.Missing = I18n.Tr("not recorded (older block format)");

            // Page 3 — totals strip (summed over the games that recorded them)
            // and the set summary, taken from set_summary ONCE (C-7).
            BuildTotals(m, env);

            // Page 4 — end-of-game builds.
            for (int gi = 0; gi < env.Games.Count; gi++)
            {
                var g = env.Games[gi];
                for (int pi = 0; pi < m.Players.Count; pi++)
                {
                    string pid = m.Players[pi].Id;
                    List<string> cards;
                    string stats;
                    g.EndBuild.TryGetValue(pid, out cards);
                    g.EndStats.TryGetValue(pid, out stats);
                    bool hasCards = cards != null && cards.Count > 0;
                    string body = "";
                    if (!string.IsNullOrEmpty(stats))
                    {
                        try { body = NativeUI.BuildStatsTipBlock(stats, 34) ?? ""; } catch { body = ""; }
                    }
                    if (!hasCards && body.Length == 0) continue;
                    var cb = new StringBuilder();
                    if (hasCards)
                    {
                        for (int ci = 0; ci < cards.Count; ci++)
                        {
                            if (ci > 0) cb.Append(", ");
                            cb.Append(Safe(cards[ci]));
                        }
                    }
                    m.Builds.Add(new BuildBlock
                    {
                        Title = I18n.TrF("Game {0}", gi + 1) + " - " + Coloured(m, pi, Safe(m.Players[pi].Name)),
                        Cards = hasCards ? cb.ToString() : I18n.Tr("no cards recorded"),
                        Stats = body,
                    });
                }
            }
            if (m.Builds.Count == 0) m.BuildsMissing = I18n.Tr("no build recorded for these games");
            return m;
        }

        private static void BuildTotals(Model m, Envelope env)
        {
            m.TotalsHeader.Clear();
            m.TotalsHeader.AddRange(new[]
            {
                I18n.Tr("Player"), I18n.Tr("Damage"), I18n.Tr("Shots"), I18n.Tr("Hit %"),
                I18n.Tr("Blocks"), I18n.Tr("Block %"), I18n.Tr("Keys/s"), I18n.Tr("Deaths"),
                I18n.Tr("Kills"), I18n.Tr("K/D"),
            });
            int n = m.Players.Count;
            var sum = new Dictionary<string, float>[n];
            for (int i = 0; i < n; i++) sum[i] = new Dictionary<string, float>();
            float totalDur = 0f; int durGames = 0;
            foreach (var g in env.Games)
            {
                if (g.DurationS > 0f) { totalDur += g.DurationS; durGames++; }
                for (int pi = 0; pi < n; pi++)
                {
                    Dictionary<string, float> t;
                    if (!g.Totals.TryGetValue(m.Players[pi].Id, out t) || t == null) continue;
                    foreach (var kv in t)
                    {
                        float cur;
                        sum[pi].TryGetValue(kv.Key, out cur);
                        sum[pi][kv.Key] = cur + kv.Value;
                    }
                }
                // 1v1: a fighter's kill is the other fighter's death (server-derived
                // from the point events when the row itself carries no kill count).
                if (n == 2)
                {
                    for (int pi = 0; pi < 2; pi++)
                    {
                        Dictionary<string, float> other;
                        float od;
                        if (g.Totals.TryGetValue(m.Players[1 - pi].Id, out other) && other != null
                            && other.TryGetValue("deaths", out od))
                        {
                            float cur;
                            sum[pi].TryGetValue("kills_derived", out cur);
                            sum[pi]["kills_derived"] = cur + od;
                        }
                    }
                }
            }
            for (int pi = 0; pi < n; pi++)
            {
                var s = sum[pi];
                float shots = Val(s, "shots"), hits = Val(s, "hits"), blocks = Val(s, "blocks"), ok = Val(s, "blocks_ok");
                float keys = Val(s, "keys"), act = Val(s, "active_s"), deaths = Val(s, "deaths");
                float kills = s.ContainsKey("kills") ? s["kills"] : Val(s, "kills_derived");
                var row = new List<string>
                {
                    Coloured(m, pi, Safe(m.Players[pi].Name)),
                    Cell(s, "damage"),
                    Cell(s, "shots"),
                    shots > 0f ? (100f * hits / shots).ToString("F0", INV) + "%" : "-",
                    Cell(s, "blocks"),
                    blocks > 0f ? (100f * ok / blocks).ToString("F0", INV) + "%" : "-",
                    act > 0.5f && !float.IsNaN(keys) ? (keys / act).ToString("F1", INV) : "-",
                    Cell(s, "deaths"),
                    float.IsNaN(kills) ? "-" : kills.ToString("F0", INV),
                    !float.IsNaN(kills) && !float.IsNaN(deaths)
                        ? (deaths > 0f ? (kills / deaths).ToString("F2", INV) : kills.ToString("F0", INV))
                        : "-",
                };
                m.TotalsRows.Add(row);
            }
            if (durGames > 0)
                m.SummaryLines.Add(I18n.TrF("Average game length: {0}", Clock(totalDur / durGames)));
            for (int pi = 0; pi < n; pi++)
            {
                string pid = m.Players[pi].Id;
                string who = Coloured(m, pi, Safe(m.Players[pi].Name));
                RatingEntry r;
                if (env.Rating.TryGetValue(pid, out r) && r != null)
                {
                    string delta = (r.Delta >= 0f ? "+" : "") + r.Delta.ToString("F1", INV);
                    if (r.Before.HasValue && r.After.HasValue)
                        m.SummaryLines.Add(I18n.TrF("{0}: rating {1} -> {2} ({3})", who,
                            r.Before.Value.ToString("F0", INV), r.After.Value.ToString("F0", INV), delta));
                    else
                        m.SummaryLines.Add(I18n.TrF("{0}: rating {1}", who, delta));
                }
                int gold;
                if (env.Gold.TryGetValue(pid, out gold))
                    m.SummaryLines.Add(I18n.TrF("{0}: {1} gold", who, (gold >= 0 ? "+" : "") + gold.ToString(INV)));
            }
            if (m.SummaryLines.Count == 0) m.SummaryLines.Add(I18n.Tr("no rating or gold recorded for this set"));
        }

        // ── series maths (pure) ──────────────────────────────────────────────

        /// <summary>Value of a cumulative series at time x: 0 at or before the
        /// origin, linear between samples, held after the last one.</summary>
        internal static float At(List<Vector2> s, float x)
        {
            if (s == null || s.Count == 0 || x <= 0f) return 0f;
            float px = 0f, pv = 0f;
            for (int i = 0; i < s.Count; i++)
            {
                if (x <= s[i].x)
                {
                    float span = s[i].x - px;
                    return span <= 0f ? s[i].y : pv + (s[i].y - pv) * ((x - px) / span);
                }
                px = s[i].x; pv = s[i].y;
            }
            return s[s.Count - 1].y;
        }

        /// <summary>Rate over the trailing window at each sample time:
        /// (v(t) - v(t - w)) / w, clamped at 0 (a counter reset is not a
        /// negative rate). Needs two samples to mean anything.</summary>
        internal static List<Vector2> Rolling(List<Vector2> cum, float window)
        {
            var out_ = new List<Vector2>();
            if (cum == null || cum.Count < 2 || window <= 0f) return out_;
            for (int i = 0; i < cum.Count; i++)
            {
                float t = cum[i].x;
                float d = cum[i].y - At(cum, t - window);
                float w = Mathf.Min(window, Mathf.Max(t, 1f));
                out_.Add(new Vector2(t, Mathf.Max(0f, d / w)));
            }
            return out_;
        }

        /// <summary>100 * Δnum / Δden over the trailing window at each sample
        /// time of `den`; samples whose Δden is below `minDen` are skipped
        /// (a 15 s window with one shot is noise, not a percentage).</summary>
        internal static List<Vector2> RollingRatio(List<Vector2> num, List<Vector2> den, float window, float minDen)
        {
            var out_ = new List<Vector2>();
            if (num == null || den == null || den.Count < 2 || window <= 0f) return out_;
            for (int i = 0; i < den.Count; i++)
            {
                float t = den[i].x;
                float dd = den[i].y - At(den, t - window);
                if (dd < minDen) continue;
                float dn = At(num, t) - At(num, t - window);
                out_.Add(new Vector2(t, Mathf.Clamp(100f * dn / dd, 0f, 100f)));
            }
            return out_;
        }

        private static List<Vector2> Shift(List<Vector2> s, float x0, bool leadingZero)
        {
            var out_ = new List<Vector2>(s.Count + 1);
            if (leadingZero) out_.Add(new Vector2(x0, 0f));
            for (int i = 0; i < s.Count; i++) out_.Add(new Vector2(x0 + Mathf.Max(0f, s[i].x), s[i].y));
            return out_;
        }

        private static void AddLine(Panel p, string pid, Color tint, List<Vector2> pts)
        {
            if (pts == null || pts.Count == 0) return;
            for (int i = 0; i < pts.Count; i++) if (pts[i].y > p.MaxY) p.MaxY = pts[i].y;
            p.Lines.Add(new Poly { PlayerId = pid, Tint = tint, Pts = pts });
        }

        private static void Finish(Panel p, string missing)
        {
            if (p.Lines.Count == 0) { p.Missing = missing; return; }
            if (p.Percent) p.MaxY = 100f;
            else p.MaxY = NiceCeil(p.MaxY);
        }

        internal static float NiceCeil(float v)
        {
            if (v <= 1f) return 1f;
            float mag = Mathf.Pow(10f, Mathf.Floor(Mathf.Log10(v)));
            float n = v / mag;
            float step = n <= 1f ? 1f : n <= 2f ? 2f : n <= 5f ? 5f : 10f;
            return step * mag;
        }

        private static float LongestT(Game g)
        {
            float t = 0f;
            foreach (var streams in g.Timelines.Values)
                foreach (var s in streams.Values)
                    if (s.Count > 0 && s[s.Count - 1].x > t) t = s[s.Count - 1].x;
            foreach (var d in g.Deaths) if (d.T > t) t = d.T;
            return t;
        }

        // ── small helpers ────────────────────────────────────────────────────

        private static int Get(Dictionary<string, int> d, string k) { int v; return d.TryGetValue(k, out v) ? v : 0; }

        private static float Val(Dictionary<string, float> d, string k) { float v; return d.TryGetValue(k, out v) ? v : float.NaN; }

        private static string Cell(Dictionary<string, float> d, string k)
        {
            float v;
            return d.TryGetValue(k, out v) ? v.ToString("F0", INV) : "-";
        }

        private static string ScoreLine(Model m, int ia, int sa, int ib, int sb)
        {
            string na = Safe(m.Players[ia].Name), nb = Safe(m.Players[ib].Name);
            if (sa > sb) na = Coloured(m, ia, na);
            else if (sb > sa) nb = Coloured(m, ib, nb);
            return na + " " + sa.ToString(INV) + "-" + sb.ToString(INV) + " " + nb;
        }

        internal static string Coloured(Model m, int pi, string text)
        {
            if (pi < 0 || pi >= m.Tints.Count) return text;
            return "<color=#" + ColorUtility.ToHtmlStringRGB(m.Tints[pi]) + ">" + text + "</color>";
        }

        /// <summary>Server-authored text made safe for a rich-text label: the
        /// tag characters go, control characters go, and the name is capped.</summary>
        internal static string Safe(string s)
        {
            if (string.IsNullOrEmpty(s)) return "?";
            var sb = new StringBuilder(Math.Min(s.Length, NAME_CAP));
            foreach (char c in s)
            {
                if (c == '<' || c == '>' || char.IsControl(c)) continue;
                sb.Append(c);
                if (sb.Length >= NAME_CAP) break;
            }
            return sb.Length == 0 ? "?" : sb.ToString();
        }

        internal static string Clock(float seconds)
        {
            int s = Mathf.Max(0, Mathf.RoundToInt(seconds));
            int h = s / 3600, mnt = (s % 3600) / 60, sec = s % 60;
            return h > 0
                ? h.ToString(INV) + ":" + mnt.ToString("00", INV) + ":" + sec.ToString("00", INV)
                : mnt.ToString(INV) + ":" + sec.ToString("00", INV);
        }

        private static string KindLabel(string kind)
        {
            switch (kind)
            {
                case "ranked": return I18n.Tr("Ranked");
                case "casual": return I18n.Tr("Casual");
                case "team": return I18n.Tr("2v2");
                case "ffa": return I18n.Tr("FFA");
                case "ovt": return I18n.Tr("1v2");
                default: return Safe(kind);
            }
        }
    }
}
