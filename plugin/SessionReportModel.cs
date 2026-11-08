using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using UnityEngine;
using static CompetitiveRounds.SessionReportRules;

namespace CompetitiveRounds
{
    // ROUNDS' own ::Player (the global namespace) outranks a `using static`
    // import; the report's roster entry is named here, inside the namespace.
    using Player = SessionReportRules.Player;

    /// <summary>Sept 6 batch (Group 4 item c) - the PURE view-model behind the
    /// interactive session report. Two halves, both free of Unity UI:
    ///
    ///  1. SessionReportRules.Parse (Sept 28, board row 30a: moved out of this
    ///     file so the harness EXECUTES it) turns the server's versioned
    ///     envelope (GET /api/v1/report, v1) into an Envelope. Every statistic
    ///     is keyed by the player's steam id as a string; there is NO
    ///     viewer-relative field anywhere and nothing here asks "who is me".
    ///
    ///  2. <see cref="Build"/> turns an Envelope into <see cref="Model"/>: the
    ///     pages' polylines, tables, labels and build blocks, pre-composed once (#162)
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
        /// <summary>The rolling window's floor; a decimated stream widens it
        /// (SessionReportRules.StrideWindow, lesson 318).</summary>
        internal const float WINDOW_S = 20f;
        /// <summary>The least shots / blocks a window must hold to print a percentage.</summary>
        internal const float MIN_SHOTS = 5f, MIN_BLOCKS = 2f;
        /// <summary>Pages with a fixed layout (timeline, rates, and the four
        /// Totals pages: set, players, per game, progress - board row 30d). The
        /// builds follow: one block per game, as many blocks per page as fit
        /// and as many pages as they need - their count depends on the body
        /// size, so the VIEW owns it (SessionReportView.PageCount) and nothing
        /// is ever dropped for not fitting (review r1, board row 30c).</summary>
        internal const int FIXED_PAGES = 6;
        private const int NAME_CAP = 18;
        /// <summary>A card chip's cap: long enough for the longest shipped
        /// localized card name, short enough that one chip fits a column.</summary>
        private const int CARD_CAP = 28;
        private static readonly CultureInfo INV = CultureInfo.InvariantCulture;

        // ── view model ───────────────────────────────────────────────────────

        internal sealed class Poly
        {
            public string PlayerId;
            public Color Tint;
            public List<Vector2> Pts;    // x = seconds on the SESSION axis
            public bool Step;            // drawn as steps: a count that jumps, never ramps
            public int Player = -1;      // roster index of the player whose series this is (-1: a side's)
            public int Side = -1;        // index into Model.Sides for a side's series (the race)
            public float MaxGap;         // > 0: points further apart than this are a gap (a rate line skipped samples), not a segment
        }

        /// <summary>A recorded end score placed at its game's end (a race whose
        /// games carry no point events: 2v2, 1v2, or a game with no stream).</summary>
        internal sealed class Dot
        {
            public float X, Y;           // session seconds, rounds
            public Color Tint;
            public string Label = "";
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
            /// <summary>Board row 30e: a rounds race - the y-axis is the rounds
            /// the mode is played to, one grid line per round.</summary>
            public bool Rounds;
            public float MaxY = 1f;
            public readonly List<Poly> Lines = new List<Poly>();
            /// <summary>Secondary thin lines (the race's within-round points);
            /// the view draws them only where they are legible.</summary>
            public readonly List<Poly> Thin = new List<Poly>();
            public readonly List<Dot> Dots = new List<Dot>();
            /// <summary>A line the view prints under the title (round 2 M2: a
            /// race whose target is not recorded says so); null for none.</summary>
            public string Note;
            // ask 9 stage C: composed once at build, so the draw path allocates nothing
            public string MissingRich, NoteRich, AvgLabel;
            public string[] AxisLabels = new string[0];
            public float Avg = float.NaN;    // a reference line (the set's own ratio); NaN = none
        }

        internal sealed class Span
        {
            public float X0, X1;
            public string LabelLong = "", LabelShort = "";
            public string ClockLabel = "";   // Clock(X1) in the muted ink, composed once
            public readonly List<Mark> Picks = new List<Mark>();
        }

        /// <summary>One card of a builds block: its display name, its rarity
        /// colour, and whether the FFA rolling cap later pushed it out of the
        /// build (drawn dimmed, still in pick order).</summary>
        internal sealed class Chip
        {
            public string Text = "";         // plain: what the view measures
            public string Label = "";        // Text in its colour: what the view draws
            public Color Tint;
            public bool Rolled;
            public string Card = "";         // the card's name, for the art lookup (ask 9 stage C)
        }

        /// <summary>One player's column of a builds block.</summary>
        internal sealed class BuildCol
        {
            public string Name = "";         // in the player's colour
            public readonly List<Chip> Chips = new List<Chip>();
            public string Note = "";         // "no cards recorded" when there is no chip
            public string NoteRich = "";
            /// <summary>The raw end-of-game stat wire ("" when not recorded): the
            /// view lays it out for its column width (NativeUI.BuildStatsTipBlock).</summary>
            public string StatsWire = "";
        }

        /// <summary>Board row 30c: one compact block per game - the header
        /// (game number, recorded score), the game's length, and one column
        /// per player who played it, in roster order.</summary>
        internal sealed class GameBuild
        {
            public int Number;               // 1-based position in the set
            public string Header = "";
            public string Length = "";       // "" when the game's duration is unknown
            public string LengthRich = "";
            public bool HasRolled;           // a chip of this block is a rolled-out card
            public readonly List<BuildCol> Cols = new List<BuildCol>();
        }

        /// <summary>A Set page tile: what it counts, the number, a footnote.</summary>
        internal sealed class Tile { public string Label = "", Value = "", Sub = "", LabelRich = "", SubRich = ""; }

        /// <summary>One timed game on the game-length strip.</summary>
        internal sealed class StripSeg
        {
            public float Seconds;
            public string Label = "", Short = "";
            public int Mark;                 // 1 = the set's shortest game, 2 = its longest
        }

        /// <summary>A Totals table: the columns some player has a value for,
        /// one row per player; a cell with no value reads "-".</summary>
        internal sealed class Table
        {
            public string Title = "";
            /// <summary>Round 2 L1: what the view prints when no column was kept.</summary>
            public string Missing = "";
            public string MissingRich = "";  // the same in the muted ink, composed once
            public readonly List<string> Header = new List<string>();
            public readonly List<string> HeaderRich = new List<string>();
            public readonly List<List<string>> Rows = new List<List<string>>();
        }

        /// <summary>Per-game grouped bars: one group per game, one bar per
        /// player (null: the player did not play that game, or it recorded no
        /// value) - the element for per-game comparisons.</summary>
        internal sealed class Bars
        {
            public string Title = "", Unit = "", Missing;
            public float MaxY = 1f;
            public readonly List<float?[]> Values = new List<float?[]>();
            public readonly List<string[]> Texts = new List<string[]>();
            public readonly List<string> Labels = new List<string>();
            public bool Percent;             // a 0..100 axis
            public float Avg = float.NaN;    // the set's own ratio as a reference line; NaN = none
            public string AvgLabel = "", MissingRich;
            public string[] AxisLabels = new string[0];
        }

        /// <summary>The Set totals page's race figure (ask 9 stage C): each side's
        /// (FFA: each player's) games won after every game, as steps over the game
        /// index, with each game's short score under its column.</summary>
        internal sealed class SetRace
        {
            public readonly List<Poly> Lines = new List<Poly>();   // x = games played (0 = before game 1), y = wins
            public readonly List<string> Pills = new List<string>();
            public readonly List<string> Labels = new List<string>();  // the game numbers, muted
            public float MaxY = 1f;
            public string[] AxisLabels = new string[0];
        }

        internal sealed class Model
        {
            public Envelope Env;
            public string Kind = "";
            public readonly List<Player> Players = new List<Player>();
            public readonly List<Color> Tints = new List<Color>();
            // ask 9 stage C: the sides (SessionReportRules.Sides), their names and tints
            public readonly List<Side> Sides = new List<Side>();
            public bool TwoSided;
            public int[] SideOf = new int[0];
            public readonly List<string> SideNames = new List<string>();   // coloured member names joined with " + "
            public readonly List<Color> SideTints = new List<Color>();
            public string Header = "", Legend = "", Sub = "", Note = "";
            // ask 9 stage C: the legend toggles' tags (a player's coloured name,
            // and the muted one while hidden), the hint beside them, and the
            // other header strings the draw path used to compose per frame
            public readonly List<string> NameTags = new List<string>(), NameTagsMuted = new List<string>();
            public string ToggleHint = "", RolledChipKey = "", RaceNoteRich = "";
            public float TotalS = 1f;
            public readonly List<Span> Spans = new List<Span>();
            public readonly List<Mark> Deaths = new List<Mark>();
            // page 1
            public Panel Damage, Score;
            // page 2
            public Panel Dps, HitPct, BlockPct, Ping, Fps;
            // the Totals pages (board row 30d): set, players, per game, progress
            public Derived Derived;
            public readonly List<Tile> SetTiles = new List<Tile>();
            public readonly List<StripSeg> Strip = new List<StripSeg>();
            public float StripTotal;
            public string StripKey = "", StripNote = "", RaceNote = "", StripMissing = "";
            public string StripNoteRich = "", StripMissingRich = "", BuildsMissingRich;
            public readonly Table Combat = new Table(), Play = new Table(), Progress = new Table();
            public Bars DamageBars, KillsBars, GoldBars, XpBars;
            public Bars DeathsBars, HitBars, BlockBars;
            public SetRace SetRace;
            // the builds pages: one block per game, packed onto pages by the view
            public readonly List<GameBuild> Builds = new List<GameBuild>();
            public string BuildsMissing;
            public readonly string[] PageTitles = new string[FIXED_PAGES];
            public string BuildsTitle = "";
            /// <summary>The builds pages' key: the rarity colours, and what a
            /// dimmed chip means (shown only on a page that has one).</summary>
            public string ChipKey = "", RolledKey = "";

            /// <summary>"Games 3-5 of 12" for a builds page holding blocks
            /// first..last (0-based), "Game 4 of 12" for a page of one.</summary>
            public string BuildsRange(int first, int last)
            {
                // composed once per page turn, not per frame (lesson 162)
                if (first == rangeFirst && last == rangeLast) return rangeText;
                rangeFirst = first; rangeLast = last;
                if (last <= first) rangeText = I18n.TrF("Game {0} of {1}", first + 1, Builds.Count);
                else rangeText = I18n.TrF("Games {0}-{1} of {2}", first + 1, last + 1, Builds.Count);
                return rangeText;
            }

            private int rangeFirst = -1, rangeLast = -1;
            private string rangeText = "";

            /// <summary>Footer title for page `pg`; a builds page names the
            /// games it holds (first..last, 0-based, as the view packed them).</summary>
            public string PageTitle(int pg, int first, int last)
            {
                if (pg < FIXED_PAGES) return pg >= 0 ? PageTitles[pg] : "";
                if (Builds.Count == 0) return BuildsTitle;
                return BuildsTitle + " - " + BuildsRange(first, last);
            }
        }

        // -- ask 9 stage C: the theme - one token set; the hexes live in the Unity-free rules --

        internal static readonly Color INK = Hex(INK_HEX), INK2 = Hex(INK2_HEX), MUTED = Hex(MUTED_HEX);
        internal static readonly Color[] DIVERGE = HexAll(DIVERGE_HEX);
        private static readonly Color[] SLOTS = HexAll(SLOT_HEX);

        internal static Color Hex(string hex)
        {
            float r, g, b;
            return ParseHex(hex, out r, out g, out b) ? new Color(r, g, b, 1f) : Color.white;
        }

        private static Color[] HexAll(string[] hexes)
        {
            var o = new Color[hexes.Length];
            for (int i = 0; i < o.Length; i++) o[i] = Hex(hexes[i]);
            return o;
        }

        /// <summary>A stat in its tint: the number is always the text; the colour
        /// is its distance from the page's average (SessionReportRules.StatScale),
        /// ink at the average, so colour never carries the meaning alone.</summary>
        internal static string Stat(string text, int step)
        {
            if (text == null) return null;
            int i = Mathf.Clamp(step + DIVERGE_STEPS, 0, DIVERGE.Length - 1);
            return i == DIVERGE_STEPS ? text : Tinted(DIVERGE[i], text);
        }

        internal static string Muted(string text) => "<color=" + MUTED_HEX + ">" + text + "</color>";

        internal static Model Build(Envelope env)
        {
            var m = new Model { Env = env, Kind = env.Kind ?? "" };
            m.PageTitles[0] = I18n.Tr("Timeline");
            m.PageTitles[1] = I18n.Tr("Rates");
            m.PageTitles[2] = I18n.Tr("Set totals");
            m.PageTitles[3] = I18n.Tr("Player totals");
            m.PageTitles[4] = I18n.Tr("Per game");
            m.PageTitles[5] = I18n.Tr("Progress");
            m.BuildsTitle = I18n.Tr("Builds");

            // Roster, colours, legend. A player's colour is the one the game gave
            // them - the identity players already know - held to the dark band
            // (SessionReportRules.SnapTint: hue kept, lightness and chroma in the
            // validated range); a player the server sends no colour for takes the
            // next validated slot, never a cycled one, the muted ink past eight.
            var idx = new Dictionary<string, int>();
            for (int i = 0; i < env.Players.Count; i++)
            {
                var p = env.Players[i];
                if (idx.ContainsKey(p.Id)) continue;
                idx[p.Id] = m.Players.Count;
                m.Players.Add(p);
                float r, g, b;
                Color c;
                if (ParseHex(p.ColorHex, out r, out g, out b))
                {
                    SnapTint(ref r, ref g, ref b);
                    c = new Color(r, g, b, 1f);
                }
                else c = m.Players.Count - 1 < SLOTS.Length ? SLOTS[m.Players.Count - 1] : MUTED;
                m.Tints.Add(c);
            }
            var legend = new StringBuilder();
            for (int i = 0; i < m.Players.Count; i++)
            {
                if (i > 0) legend.Append("   ");
                legend.Append(Coloured(m, i, Safe(m.Players[i].Name)));
                m.NameTags.Add(Coloured(m, i, Safe(m.Players[i].Name)));
                m.NameTagsMuted.Add(Muted(Safe(m.Players[i].Name)));
            }
            m.Legend = legend.ToString();
            m.ToggleHint = Muted(I18n.Tr("click a name to hide its lines"));

            // The sides (SessionReportRules.Sides): every recorded score, point
            // and race stream is a side's, in every mode.
            m.Sides.AddRange(Sides(m.Kind, m.Players));
            m.TwoSided = TwoSided(m.Kind, m.Sides);
            m.SideOf = SideIndex(m.Sides, m.Players.Count);
            foreach (var side in m.Sides)
            {
                var names = new StringBuilder();
                for (int k = 0; k < side.Slots.Count; k++)
                {
                    if (k > 0) names.Append(" + ");
                    names.Append(Coloured(m, side.Slots[k], Safe(m.Players[side.Slots[k]].Name)));
                }
                m.SideNames.Add(names.ToString());
                m.SideTints.Add(side.Slots.Count > 0 ? m.Tints[side.Slots[0]] : MUTED);
            }

            // Session axis: games end to end, each spanning its own duration.
            float x0 = 0f;
            var setWins = new int[2];
            foreach (var g in env.Games)
            {
                float dur = g.DurationS > 0f ? g.DurationS : LongestT(g);
                if (dur < 1f) dur = 60f;
                var sp = new Span { X0 = x0, X1 = x0 + dur };
                x0 = sp.X1;
                int gi = m.Spans.Count + 1;
                int sa, sb, ia, ib;
                if (SideScores(m.Kind, g, m.Players, m.Sides, out sa, out sb, out ia, out ib))
                {
                    // Two sides that both have a key in this game (round 2 M1: a
                    // missing key is never a 0; the standings below omit it).
                    if (sa > sb) setWins[0]++; else if (sb > sa) setWins[1]++;
                    sp.LabelShort = sa.ToString(INV) + "-" + sb.ToString(INV);
                    sp.LabelLong = ScoreLine(m, sa, sb, g);
                }
                else
                {
                    // N players (FFA, or a side with no key): the recorded points, best first.
                    sp.LabelShort = FfaScoreLabel(m, g, gi, false);
                    sp.LabelLong = FfaScoreLabel(m, g, gi, true);
                }
                sp.ClockLabel = Muted(Clock(sp.X1));
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

            // Header: the two sides' games won, the winner's score in its colour;
            // a plain roster line otherwise (FFA).
            m.Header = m.TwoSided ? ScoreLine(m, setWins[0], setWins[1]) : m.Legend;
            string kindLabel = KindLabel(m.Kind);
            m.Sub = I18n.TrF("{0} - {1} games - {2} played", kindLabel, env.Games.Count, Clock(m.TotalS));
            if (env.GamesOmitted > 0)
                m.Note = I18n.TrF("showing the newest {0} games of this sitting ({1} not shown)", env.Games.Count, env.GamesOmitted);
            else if (env.Truncated)
                m.Note = I18n.TrF("showing the newest {0} games of this sitting", env.Games.Count);
            if (env.V != 1) m.Note = I18n.TrF("report version {0} - some panels may be missing", env.V);

            // Page 1 — cumulative damage and the score race, per game segment.
            m.Damage = new Panel { Title = I18n.Tr("Damage dealt (cumulative per game)"), Unit = I18n.Tr("dmg") };
            m.Score = new Panel { Title = I18n.Tr("Score race (rounds won per game)"), Unit = I18n.Tr("rounds"), Rounds = true };
            float racePer = RaceDivisor(m.Kind);
            // Page 2 — rates over a trailing window that follows the stream's
            // stride (SessionReportRules.StrideWindow: a decimated long game
            // widens it, lesson 318), plus the ping / fps strips.
            m.Dps = new Panel { Title = I18n.Tr("Rolling DPS"), Unit = I18n.Tr("dmg/s") };
            m.HitPct = new Panel { Title = I18n.Tr("Rolling hit %"), Unit = "%", Percent = true };
            m.BlockPct = new Panel { Title = I18n.Tr("Rolling block %"), Unit = "%", Percent = true };
            m.Ping = new Panel { Title = I18n.Tr("Ping"), Unit = I18n.Tr("ms") };
            m.Fps = new Panel { Title = I18n.Tr("FPS"), Unit = I18n.Tr("fps") };
            bool legacyBlocks = false;
            // One window per rate panel, the widest any of its streams needs, and
            // every line of the panel is rolled with it, so the note under the
            // title is exact for every line (round 1 M2: one shared note named a
            // sparse damage stream's 60 s on the hit panel's 20 s lines).
            float wDps = WINDOW_S, wHit = WINDOW_S, wBlock = WINDOW_S;
            foreach (var g0 in env.Games)
                foreach (var kv in g0.Timelines)
                {
                    if (kv.Value == null) continue;
                    List<Pt> s0;
                    if (kv.Value.TryGetValue("damage", out s0)) wDps = Mathf.Max(wDps, StrideWindow(s0, WINDOW_S));
                    if (kv.Value.TryGetValue("shots", out s0)) wHit = Mathf.Max(wHit, StrideWindow(s0, WINDOW_S));
                    if (kv.Value.TryGetValue("blocks", out s0)) wBlock = Mathf.Max(wBlock, StrideWindow(s0, WINDOW_S));
                }

            for (int gi = 0; gi < env.Games.Count; gi++)
            {
                var g = env.Games[gi];
                var sp = m.Spans[gi];
                // Board row 30e: the race plots ROUNDS won (floor(value / per) at
                // every sample - SessionReportRules.RoundsSeries, executed by the
                // client harness) - one step line per SIDE from the side's stream
                // (ask 9: 2v2 drew its four identical player lines over each other),
                // with the within-round points as a thin secondary line.
                for (int si = 0; si < m.Sides.Count && racePer > 0f; si++)
                {
                    var score = SideStream(g, m.Players, m.Sides[si], "score");
                    if (score == null) continue;
                    var rounds = Shift(RoundsSeries(score, racePer, false), sp.X0, true);
                    if (rounds.Count == 0) continue;
                    AddLine(m.Score, SideId(m, si), m.SideTints[si], rounds, -1, si);
                    m.Score.Lines[m.Score.Lines.Count - 1].Step = true;
                    m.Score.Thin.Add(new Poly
                    {
                        PlayerId = SideId(m, si), Tint = m.SideTints[si], Side = si,
                        Pts = Shift(RoundsSeries(score, racePer, true), sp.X0, true),
                    });
                }
                for (int pi = 0; pi < m.Players.Count; pi++)
                {
                    string pid = m.Players[pi].Id;
                    Dictionary<string, List<Pt>> streams;
                    if (!g.Timelines.TryGetValue(pid, out streams) || streams == null) continue;
                    List<Pt> dmg, shots, hits, blocks, blocksOk, ping, fps;
                    streams.TryGetValue("damage", out dmg);
                    streams.TryGetValue("shots", out shots);
                    streams.TryGetValue("hits", out hits);
                    streams.TryGetValue("blocks", out blocks);
                    streams.TryGetValue("blocks_ok", out blocksOk);
                    streams.TryGetValue("ping", out ping);
                    streams.TryGetValue("fps", out fps);

                    if (dmg != null && dmg.Count > 0)
                    {
                        AddLine(m.Damage, pid, m.Tints[pi], Shift(dmg, sp.X0, true), pi, -1);
                        var dps = Rolling(dmg, wDps);
                        if (dps.Count > 0) AddLine(m.Dps, pid, m.Tints[pi], Shift(dps, sp.X0, false), pi, -1);
                    }
                    if (shots != null && hits != null && shots.Count > 0)
                    {
                        var hp = RollingRatio(hits, shots, wHit, MIN_SHOTS);
                        if (hp.Count > 0)
                        {
                            AddLine(m.HitPct, pid, m.Tints[pi], Shift(hp, sp.X0, false), pi, -1);
                            m.HitPct.Lines[m.HitPct.Lines.Count - 1].MaxGap = 1.5f * MedianGap(shots);
                        }
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
                                      && blocks[blocks.Count - 1].Y > totBlocks + 3f;
                        if (legacy) legacyBlocks = true;
                        else
                        {
                            var bp = RollingRatio(blocksOk, blocks, wBlock, MIN_BLOCKS);
                            if (bp.Count > 0)
                            {
                                AddLine(m.BlockPct, pid, m.Tints[pi], Shift(bp, sp.X0, false), pi, -1);
                                m.BlockPct.Lines[m.BlockPct.Lines.Count - 1].MaxGap = 1.5f * MedianGap(blocks);
                            }
                        }
                    }
                    if (ping != null && ping.Count > 0) AddLine(m.Ping, pid, m.Tints[pi], Shift(ping, sp.X0, false), pi, -1);
                    if (fps != null && fps.Count > 0) AddLine(m.Fps, pid, m.Tints[pi], Shift(fps, sp.X0, false), pi, -1);
                }
            }
            // Round 2 L1: each chart says why it is empty - this set, or the mode.
            Finish(m.Damage, MissingText(m.Kind, MET_DAMAGE));
            Finish(m.Dps, MissingText(m.Kind, MET_DAMAGE));
            Finish(m.HitPct, MissingText(m.Kind, MET_HIT));
            Finish(m.BlockPct, MissingText(m.Kind, MET_BLOCK));
            Finish(m.Ping, MissingText(m.Kind, MET_PING));
            Finish(m.Fps, MissingText(m.Kind, MET_FPS));
            FinishRace(m, env, MissingText(m.Kind, MET_SCORE));
            m.StripMissing = MissingText(m.Kind, MET_DURATION);
            if (m.BlockPct.Missing != null && legacyBlocks)
                m.BlockPct.Missing = I18n.Tr("not recorded (older block format)");
            // Each rate panel's own window, named once under its title.
            if (m.Dps.Missing == null) m.Dps.Note = I18n.TrF("{0} s window", Mathf.RoundToInt(wDps));
            if (m.HitPct.Missing == null) m.HitPct.Note = I18n.TrF("{0} s window", Mathf.RoundToInt(wHit));
            if (m.BlockPct.Missing == null) m.BlockPct.Note = I18n.TrF("{0} s window", Mathf.RoundToInt(wBlock));

            // The Totals pages (board row 30d): derived by SessionReportRules.Derive,
            // which the client harness executes; rating, gold and XP are read
            // from set_summary ONCE (C-7). The set's own hit and block ratios come
            // back as the rate panels' reference lines.
            BuildTotalsPages(m, env);

            // The builds (board row 30c): one compact block per game - its
            // number, recorded score and length in the header, then one column
            // per player who played it (roster order) with the cards as chips
            // in PICK order, each in its rarity colour. Every game gets a
            // block; the view packs as many blocks as fit on a page and adds
            // pages as needed (SessionReportRules.PackPages) - there is no cap.
            for (int gi = 0; gi < env.Games.Count; gi++)
            {
                var g = env.Games[gi];
                var gb = new GameBuild { Number = gi + 1, Header = BlockHeader(m, g, gi + 1) };
                if (g.DurationS > 0f) gb.Length = I18n.TrF("length {0}", Clock(g.DurationS));
                gb.LengthRich = gb.Length.Length > 0 ? Muted(gb.Length) : "";
                for (int pi = 0; pi < m.Players.Count; pi++)
                {
                    string pid = m.Players[pi].Id;
                    if (!g.Scores.ContainsKey(pid) && !HasCards(g, pid)) continue;
                    var col = new BuildCol { Name = Coloured(m, pi, Safe(m.Players[pi].Name)) };
                    // Picks the FFA rolling cap later pushed out stay in pick
                    // order, flagged: the view dims them (they are not the build).
                    foreach (var pk in g.Picks)
                        if (pk.Id == pid) col.Chips.Add(MakeChip(pk.Card, pk.Rolled));
                    if (col.Chips.Count == 0)
                    {
                        // No pick list for this player: the end build, in its order.
                        List<string> cards;
                        if (g.EndBuild.TryGetValue(pid, out cards) && cards != null)
                            foreach (var c in cards) col.Chips.Add(MakeChip(c, false));
                    }
                    // The server kept only the newest picks: say so ahead of them.
                    if (g.PicksCapped && col.Chips.Count > 0)
                        col.Chips.Insert(0, new Chip { Text = "...", Label = Tinted(RARITY_OTHER, "..."), Tint = RARITY_OTHER });
                    if (col.Chips.Count == 0) col.Note = I18n.Tr("no cards recorded");
                    col.NoteRich = col.Note.Length > 0 ? Muted(col.Note) : "";
                    foreach (var ch in col.Chips) gb.HasRolled |= ch.Rolled;
                    string stats;
                    if (g.EndStats.TryGetValue(pid, out stats) && !string.IsNullOrEmpty(stats)) col.StatsWire = stats;
                    gb.Cols.Add(col);
                }
                m.Builds.Add(gb);
            }
            if (m.Builds.Count == 0) m.BuildsMissing = I18n.Tr("no build recorded for these games");
            m.BuildsMissingRich = m.BuildsMissing == null ? null : Muted(m.BuildsMissing);
            m.ChipKey = Tinted(RARITY_COMMON, I18n.Tr("Common")) + "   " + Tinted(RARITY_UNCOMMON, I18n.Tr("Uncommon"))
                        + "   " + Tinted(RARITY_RARE, I18n.Tr("Rare"));
            m.RolledKey = Tinted(ROLLED_TEXT, I18n.Tr("dimmed: rolled out of the build"));
            m.RolledChipKey = m.RolledKey + "     " + m.ChipKey;

            // Every string the draw path shows is composed here, once (lesson 162).
            Compose(m.Damage); Compose(m.Score); Compose(m.Dps); Compose(m.HitPct);
            Compose(m.BlockPct); Compose(m.Ping); Compose(m.Fps);
            m.StripMissingRich = Muted(m.StripMissing);
            m.StripNoteRich = m.StripNote.Length > 0 ? Muted(m.StripNote) : "";
            m.RaceNoteRich = m.RaceNote.Length > 0 ? Muted(m.RaceNote) : "";
            m.Combat.MissingRich = Muted(m.Combat.Missing ?? "");
            m.Play.MissingRich = Muted(m.Play.Missing ?? "");
            m.Progress.MissingRich = Muted(m.Progress.Missing ?? "");
            foreach (var t in m.SetTiles)
            {
                t.LabelRich = Muted(t.Label);
                t.SubRich = t.Sub.Length > 0 ? Muted(t.Sub) : "";
            }
            return m;
        }

        /// <summary>The roster id a side's series carries (its first member's).</summary>
        private static string SideId(Model m, int si)
        {
            var side = m.Sides[si];
            return side.Slots.Count > 0 ? m.Players[side.Slots[0]].Id : "";
        }

        /// <summary>A panel's axis labels, note and empty text in the muted ink,
        /// composed once (the view used to build them every rendered frame).</summary>
        private static void Compose(Panel p)
        {
            p.MissingRich = p.Missing == null ? null : Muted(p.Missing);
            p.NoteRich = string.IsNullOrEmpty(p.Note) ? null : Muted(p.Note);
            if (!float.IsNaN(p.Avg))
                p.AvgLabel = Muted(I18n.TrF("avg {0}", p.Percent ? p.Avg.ToString("F0", INV) + "%" : p.Avg.ToString("0.#", INV)));
            int steps = p.Rounds ? Mathf.Max(1, Mathf.RoundToInt(p.MaxY)) : 4;
            p.AxisLabels = AxisLabels(p.MaxY, steps, p.Percent);
        }

        private static string[] AxisLabels(float maxY, int steps, bool percent)
        {
            var labels = new string[steps + 1];
            for (int k = 0; k <= steps; k++)
            {
                float v = maxY * k / steps;
                labels[k] = Muted(percent ? v.ToString("F0", INV) + "%" : v.ToString(v >= 100f ? "F0" : "0.#", INV));
            }
            return labels;
        }

        /// <summary>The four Totals pages (board row 30d). Every number comes
        /// from SessionReportRules.Derive over named envelope fields (the field
        /// map is in the lane notes); rating, gold and XP are the set_summary's,
        /// read ONCE (C-7). A column nobody has a value for is omitted and a
        /// missing cell reads "-" - a stat that was not recorded is never a 0.</summary>
        private static void BuildTotalsPages(Model m, Envelope env)
        {
            var d = Derive(env, m.Players);
            m.Derived = d;
            var set = d.Set;
            int n = m.Players.Count;

            // Set: the tiles, the game-length strip and the score race figure.
            m.SetTiles.Add(new Tile
            {
                Label = I18n.Tr("Games"), Value = set.Games.ToString(INV),
                Sub = env.GamesOmitted > 0 ? I18n.TrF("{0} not shown", env.GamesOmitted) : "",
            });
            if (set.Timed > 0)
            {
                string timed = set.Timed < set.Games ? I18n.TrF("{0} of {1} games timed", set.Timed, set.Games) : "";
                m.SetTiles.Add(new Tile { Label = I18n.Tr("Total time"), Value = Clock(set.TotalS), Sub = timed });
                m.SetTiles.Add(new Tile { Label = I18n.Tr("Shortest game"), Value = Clock(set.ShortestS), Sub = I18n.TrF("game {0}", set.ShortestGame + 1) });
                m.SetTiles.Add(new Tile { Label = I18n.Tr("Longest game"), Value = Clock(set.LongestS), Sub = I18n.TrF("game {0}", set.LongestGame + 1) });
                m.SetTiles.Add(new Tile { Label = I18n.Tr("Average game"), Value = Clock(set.AverageS), Sub = timed });
                m.StripNote = timed;
            }
            m.SetTiles.Add(new Tile { Label = I18n.Tr("Final score"), Value = FinalScore(m, set.Wins) });
            for (int gi = 0; gi < env.Games.Count; gi++)
            {
                var g = env.Games[gi];
                if (g.DurationS <= 0f) continue;
                m.Strip.Add(new StripSeg
                {
                    Seconds = g.DurationS,
                    Label = I18n.TrF("Game {0}", gi + 1) + "  " + Clock(g.DurationS),
                    Short = (gi + 1).ToString(INV),
                    Mark = gi == set.ShortestGame ? 1 : gi == set.LongestGame ? 2 : 0,
                });
                m.StripTotal += g.DurationS;
            }
            m.StripKey = Tinted(STRIP_SHORT, I18n.Tr("shortest")) + "   " + Tinted(STRIP_LONG, I18n.Tr("longest"));

            // The race figure (ask 9 stage C): games won after each game, one
            // step line per side (FFA: per player), each game's short score as
            // the pill under its column - the wrapped text line it replaces was
            // the one unstyled element of the page.
            var sr = new SetRace();
            int ways = m.TwoSided ? 2 : n;
            for (int w = 0; w < ways; w++)
            {
                var pts = new List<Vector2> { new Vector2(0f, 0f) };
                int wins = 0;
                for (int gi = 0; gi < env.Games.Count; gi++)
                {
                    if (Winner(m.Kind, env.Games[gi], m.Players, m.Sides) == w) wins++;
                    pts.Add(new Vector2(gi + 1, wins));
                }
                sr.MaxY = Mathf.Max(sr.MaxY, wins);
                sr.Lines.Add(m.TwoSided
                    ? new Poly { PlayerId = SideId(m, w), Tint = m.SideTints[w], Pts = pts, Step = true, Side = w }
                    : new Poly { PlayerId = m.Players[w].Id, Tint = m.Tints[w], Pts = pts, Step = true, Player = w });
            }
            for (int gi = 0; gi < env.Games.Count && gi < m.Spans.Count; gi++)
            {
                sr.Pills.Add(m.Spans[gi].LabelShort);
                sr.Labels.Add(Muted((gi + 1).ToString(INV)));
            }
            sr.AxisLabels = AxisLabels(sr.MaxY, Mathf.Max(1, Mathf.RoundToInt(sr.MaxY)), false);
            m.SetRace = sr;
            if (set.LeadChanges >= 0)
                m.RaceNote = I18n.TrF("The lead in rounds changed hands {0} times over the set", set.LeadChanges);

            // Players: combat, then cards, points and momentum. Every number is
            // tinted by its distance from the column's average (Stat): the best
            // of the page greens, the worst reds, the average stays ink.
            m.Combat.Title = I18n.Tr("Combat");
            var combat = new List<KeyValuePair<string, string[]>>();
            NumColumn(combat, I18n.Tr("Damage"), n, pi => d.Players[pi].Total("damage"), pi => F0(d.Players[pi].Total("damage")), false);
            NumColumn(combat, I18n.Tr("Dmg/game"), n, pi => Mean(d.Players[pi].DamageByGame), pi => PerGame(d.Players[pi].DamageByGame, "F0"), false);
            NumColumn(combat, I18n.Tr("Shots"), n, pi => d.Players[pi].Total("shots"), pi => F0(d.Players[pi].Total("shots")), false);
            NumColumn(combat, I18n.Tr("Hit %"), n, pi => Ratio(d.Players[pi].Total("hits"), d.Players[pi].Total("shots")),
                      pi => Pct(d.Players[pi].Total("hits"), d.Players[pi].Total("shots")), false);
            NumColumn(combat, I18n.Tr("Blocks"), n, pi => d.Players[pi].Total("blocks"), pi => F0(d.Players[pi].Total("blocks")), false);
            NumColumn(combat, I18n.Tr("Block %"), n, pi => Ratio(d.Players[pi].Total("blocks_ok"), d.Players[pi].Total("blocks")),
                      pi => Pct(d.Players[pi].Total("blocks_ok"), d.Players[pi].Total("blocks")), false);
            NumColumn(combat, I18n.Tr("Keys/s"), n, pi => KeysPerSec(d.Players[pi]), pi => KeysPerS(d.Players[pi]), false);
            NumColumn(combat, I18n.Tr("Deaths"), n, pi => d.Players[pi].Total("deaths"), pi => F0(d.Players[pi].Total("deaths")), true);
            NumColumn(combat, I18n.Tr("Kills"), n, pi => d.Players[pi].Kills, pi => F0(d.Players[pi].Kills), false);
            NumColumn(combat, I18n.Tr("Kills/game"), n, pi => Mean(d.Players[pi].KillsByGame), pi => PerGame(d.Players[pi].KillsByGame, "F1"), false);
            NumColumn(combat, I18n.Tr("K/D"), n, pi => KdRatio(d.Players[pi]), pi => Kd(d.Players[pi]), false);
            FillTable(m, m.Combat, combat);
            m.Combat.Missing = MissingText(m.Kind, MET_COMBAT);

            m.Play.Title = I18n.Tr("Cards and points");
            var play = new List<KeyValuePair<string, string[]>>();
            NumColumn(play, I18n.Tr("Cards picked"), n, pi => d.Players[pi].CardsPicked, pi => Int(d.Players[pi].CardsPicked), false);
            NumColumn(play, I18n.Tr("Cards/game"), n, pi => CardsPerGame(d.Players[pi]),
                      pi => CardsPerGame(d.Players[pi]).HasValue ? CardsPerGame(d.Players[pi]).Value.ToString("F1", INV) : null, false);
            NumColumn(play, I18n.Tr("Points won"), n, pi => d.Players[pi].PointsWon, pi => Int(d.Players[pi].PointsWon), false);
            NumColumn(play, I18n.Tr("Points lost"), n, pi => d.Players[pi].PointsLost, pi => Int(d.Players[pi].PointsLost), true);
            NumColumn(play, I18n.Tr("First bloods"), n, pi => d.Players[pi].FirstBloods, pi => Int(d.Players[pi].FirstBloods), false);
            NumColumn(play, I18n.Tr("Longest point streak"), n, pi => d.Players[pi].LongestStreak, pi => Int(d.Players[pi].LongestStreak), false);
            NumColumn(play, I18n.Tr("Biggest comeback (rounds)"), n, pi => d.Players[pi].BiggestComeback, pi => Int(d.Players[pi].BiggestComeback), false);
            NumColumn(play, I18n.Tr("Time in lead"), n, pi => d.Players[pi].LeadS,
                      pi => d.Players[pi].LeadS.HasValue ? Clock(d.Players[pi].LeadS.Value) : null, false);
            FillTable(m, m.Play, play);
            m.Play.Missing = MissingText(m.Kind, MET_PLAY);

            // Per game: one bar per player per game - damage, kills and deaths in
            // every mode (ask 9: the server carries them for 2v2 and 1v2 now), hit
            // and block rate per game against the set's own ratio.
            int games = env.Games.Count;
            float hitAvg = Ratio(SumOf(d, "hits"), SumOf(d, "shots")) ?? float.NaN;
            float blockAvg = Ratio(SumOf(d, "blocks_ok"), SumOf(d, "blocks")) ?? float.NaN;
            m.HitPct.Avg = hitAvg;
            m.BlockPct.Avg = blockAvg;
            m.DamageBars = MakeBars(I18n.Tr("Damage per game"), I18n.Tr("dmg"), d, pl => pl.DamageByGame, games, false, false,
                                    MissingText(m.Kind, MET_DAMAGE_TOTAL));
            m.KillsBars = MakeBars(I18n.Tr("Kills per game"), I18n.Tr("kills"), d, pl => pl.KillsByGame, games, false, false,
                                   MissingText(m.Kind, MET_KILLS));
            m.DeathsBars = MakeBars(I18n.Tr("Deaths per game"), I18n.Tr("deaths"), d, pl => pl.DeathsByGame, games, true, false,
                                    MissingText(m.Kind, MET_COMBAT));
            m.HitBars = MakeBars(I18n.Tr("Hit % per game"), "%", d, pl => pl.HitPctByGame, games, false, true,
                                 MissingText(m.Kind, MET_HIT));
            m.HitBars.Avg = hitAvg;
            m.BlockBars = MakeBars(I18n.Tr("Block % per game"), "%", d, pl => pl.BlockPctByGame, games, false, true,
                                   MissingText(m.Kind, MET_BLOCK));
            m.BlockBars.Avg = blockAvg;
            ComposeBars(m.DamageBars); ComposeBars(m.KillsBars); ComposeBars(m.DeathsBars);
            ComposeBars(m.HitBars); ComposeBars(m.BlockBars);

            // Progress: rating before / after / change, gold and XP this set.
            m.Progress.Title = I18n.Tr("Rating, gold and XP");
            var prog = new List<KeyValuePair<string, string[]>>();
            Column(prog, I18n.Tr("Rating before"), n, pi => RatingCell(env, m, pi, 0));
            Column(prog, I18n.Tr("Rating after"), n, pi => RatingCell(env, m, pi, 1));
            NumColumn(prog, I18n.Tr("Change"), n, pi => RatingDelta(env, m, pi), pi => RatingCell(env, m, pi, 2), false);
            NumColumn(prog, I18n.Tr("Gold this set"), n, pi => d.Players[pi].Gold, pi => Signed(d.Players[pi].Gold), false);
            NumColumn(prog, I18n.Tr("XP this set"), n, pi => d.Players[pi].Xp, pi => Signed(d.Players[pi].Xp), false);
            FillTable(m, m.Progress, prog);
            m.Progress.Missing = I18n.Tr("no rating, gold or XP recorded for this set");
            m.GoldBars = MakeBars(I18n.Tr("Gold per game"), I18n.Tr("gold"), d, pl => pl.GoldByGame, games, false, false,
                                  MissingText(m.Kind, MET_GOLD));
            m.XpBars = MakeBars(I18n.Tr("XP per game"), I18n.Tr("XP"), d, pl => pl.XpByGame, games, false, false,
                                MissingText(m.Kind, MET_XP));
            ComposeBars(m.GoldBars); ComposeBars(m.XpBars);
        }

        /// <summary>A numeric table column: the cell text from `cell`, tinted by
        /// the value's step on the column's own StatScale (ink at the average,
        /// the best green, the worst red; `lowerIsBetter` flips deaths and
        /// points lost). Kept only when some player has a value.</summary>
        private static void NumColumn(List<KeyValuePair<string, string[]>> cols, string header, int n,
                                      Func<int, float?> value, Func<int, string> cell, bool lowerIsBetter)
        {
            var scale = new StatScale();
            for (int i = 0; i < n; i++) scale.Add(value(i));
            var cells = new string[n];
            bool any = false;
            for (int i = 0; i < n; i++)
            {
                cells[i] = Stat(cell(i), scale.Step(value(i), lowerIsBetter));
                if (cells[i] != null) any = true;
            }
            if (any) cols.Add(new KeyValuePair<string, string[]>(header, cells));
        }

        private static float? Mean(List<float?> xs)
        {
            float sum = 0f;
            int k = 0;
            foreach (var x in xs) if (x.HasValue) { sum += x.Value; k++; }
            return k > 0 ? sum / k : (float?)null;
        }

        private static float? Ratio(float? num, float? den)
            => num.HasValue && den.HasValue && den.Value > 0f ? 100f * num.Value / den.Value : (float?)null;

        private static float? SumOf(Derived d, string counter)
        {
            float sum = 0f;
            bool any = false;
            foreach (var pl in d.Players)
            {
                float? v = pl.Total(counter);
                if (v.HasValue) { sum += v.Value; any = true; }
            }
            return any ? sum : (float?)null;
        }

        private static float? KeysPerSec(PlayerLine pl)
        {
            float? keys = pl.Total("keys"), act = pl.Total("active_s");
            return keys.HasValue && act.HasValue && act.Value > 0.5f ? keys.Value / act.Value : (float?)null;
        }

        private static float? KdRatio(PlayerLine pl)
        {
            float? deaths = pl.Total("deaths");
            if (!pl.Kills.HasValue || !deaths.HasValue) return null;
            return deaths.Value > 0f ? pl.Kills.Value / deaths.Value : pl.Kills.Value;
        }

        private static float? CardsPerGame(PlayerLine pl)
            => pl.CardsPicked.HasValue && pl.Games > 0 ? pl.CardsPicked.Value / (float)pl.Games : (float?)null;

        private static float? RatingDelta(Envelope env, Model m, int pi)
        {
            RatingEntry r;
            return env.Rating.TryGetValue(m.Players[pi].Id, out r) && r != null ? r.Delta : (float?)null;
        }

        /// <summary>A bar set's axis labels and empty text, composed once.</summary>
        private static void ComposeBars(Bars b)
        {
            b.MissingRich = b.Missing == null ? null : Muted(b.Missing);
            b.AxisLabels = AxisLabels(b.MaxY, 4, b.Percent);
            if (!float.IsNaN(b.Avg)) b.AvgLabel = Muted(I18n.TrF("avg {0}", b.Avg.ToString("F0", INV) + "%"));
        }

        /// <summary>A table column: kept only when some player has a value.</summary>
        private static void Column(List<KeyValuePair<string, string[]>> cols, string header, int n, Func<int, string> cell)
        {
            var cells = new string[n];
            bool any = false;
            for (int i = 0; i < n; i++)
            {
                cells[i] = cell(i);
                if (cells[i] != null) any = true;
            }
            if (any) cols.Add(new KeyValuePair<string, string[]>(header, cells));
        }

        private static void FillTable(Model m, Table t, List<KeyValuePair<string, string[]>> cols)
        {
            if (cols.Count == 0) return;
            t.Header.Add(I18n.Tr("Player"));
            foreach (var c in cols) t.Header.Add(c.Key);
            foreach (var h in t.Header) t.HeaderRich.Add(Muted(h));
            for (int pi = 0; pi < m.Players.Count; pi++)
            {
                var row = new List<string> { Coloured(m, pi, Safe(m.Players[pi].Name)) };
                foreach (var c in cols) row.Add(c.Value[pi] ?? "-");
                t.Rows.Add(row);
            }
        }

        private static Bars MakeBars(string title, string unit, Derived d, Func<PlayerLine, List<float?>> pick, int games,
                                     bool lowerIsBetter, bool percent, string missing)
        {
            var b = new Bars { Title = title, Unit = unit, Percent = percent };
            bool any = false;
            var scale = new StatScale();
            for (int gi = 0; gi < games; gi++)
            {
                var row = new float?[d.Players.Count];
                for (int pi = 0; pi < row.Length; pi++)
                {
                    var xs = pick(d.Players[pi]);
                    row[pi] = gi < xs.Count ? xs[gi] : null;
                    if (!row[pi].HasValue) continue;
                    any = true;
                    scale.Add(row[pi].Value);
                    if (row[pi].Value > b.MaxY) b.MaxY = row[pi].Value;
                }
                b.Values.Add(row);
            }
            // The value above each bar, in its tint against the page's discovered
            // average (the scale spans every player and game of the set).
            for (int gi = 0; gi < games; gi++)
            {
                var row = b.Values[gi];
                var text = new string[row.Length];
                for (int pi = 0; pi < row.Length; pi++)
                {
                    if (!row[pi].HasValue) continue;
                    float v = row[pi].Value;
                    text[pi] = Stat(v.ToString(Mathf.Abs(v - Mathf.Round(v)) < 0.05f ? "F0" : "F1", INV), scale.Step(v, lowerIsBetter));
                }
                b.Texts.Add(text);
                b.Labels.Add(Muted((gi + 1).ToString(INV)));
            }
            if (!any) b.Missing = missing;
            else b.MaxY = percent ? 100f : NiceCeil(b.MaxY);
            return b;
        }

        /// <summary>The set's final score in games won: the two sides with the
        /// winner's score in its colour (1v1, 2v2, 1v2), or the best four (FFA).</summary>
        private static string FinalScore(Model m, int[] wins)
        {
            int n = m.Players.Count;
            if (m.TwoSided)
            {
                // every member of a side carries the side's wins: read the first
                int a = m.Sides[0].Slots.Count > 0 ? wins[m.Sides[0].Slots[0]] : 0;
                int b = m.Sides[1].Slots.Count > 0 ? wins[m.Sides[1].Slots[0]] : 0;
                return ScoreLine(m, a, b);
            }
            var order = new List<int>();
            for (int i = 0; i < n; i++) order.Add(i);
            order.Sort((x, y) => wins[y] != wins[x] ? wins[y].CompareTo(wins[x]) : x.CompareTo(y));
            var sb = new StringBuilder();
            for (int k = 0; k < order.Count && k < 4; k++)
            {
                if (k > 0) sb.Append(", ");
                sb.Append(Coloured(m, order[k], Safe(m.Players[order[k]].Name))).Append(' ').Append(wins[order[k]].ToString(INV));
            }
            if (order.Count > 4) sb.Append(", ").Append(I18n.TrF("+{0} more", order.Count - 4));
            return sb.ToString();
        }

        /// <summary>set_summary.rating for player `pi`: 0 = before, 1 = after,
        /// 2 = the signed change; null when the set carries no such value.</summary>
        private static string RatingCell(Envelope env, Model m, int pi, int which)
        {
            RatingEntry r;
            if (!env.Rating.TryGetValue(m.Players[pi].Id, out r) || r == null) return null;
            if (which == 0) return r.Before.HasValue ? r.Before.Value.ToString("F0", INV) : null;
            if (which == 1) return r.After.HasValue ? r.After.Value.ToString("F0", INV) : null;
            return (r.Delta >= 0f ? "+" : "") + r.Delta.ToString("F1", INV);
        }

        private static string F0(float? v) => v.HasValue ? v.Value.ToString("F0", INV) : null;

        private static string Int(int? v) => v.HasValue ? v.Value.ToString(INV) : null;

        private static string Signed(int? v) => v.HasValue ? (v.Value >= 0 ? "+" : "") + v.Value.ToString(INV) : null;

        private static string Pct(float? num, float? den)
            => num.HasValue && den.HasValue && den.Value > 0f ? (100f * num.Value / den.Value).ToString("F0", INV) + "%" : null;

        private static string PerGame(List<float?> xs, string fmt)
        {
            float sum = 0f;
            int k = 0;
            foreach (var x in xs) if (x.HasValue) { sum += x.Value; k++; }
            return k > 0 ? (sum / k).ToString(fmt, INV) : null;
        }

        private static string KeysPerS(PlayerLine pl)
        {
            float? keys = pl.Total("keys"), act = pl.Total("active_s");
            return keys.HasValue && act.HasValue && act.Value > 0.5f ? (keys.Value / act.Value).ToString("F1", INV) : null;
        }

        private static string Kd(PlayerLine pl)
        {
            float? deaths = pl.Total("deaths");
            if (!pl.Kills.HasValue || !deaths.HasValue) return null;
            return deaths.Value > 0f ? (pl.Kills.Value / deaths.Value).ToString("F2", INV) : pl.Kills.Value.ToString("F0", INV);
        }

        // ── series maths (pure) ──────────────────────────────────────────────

        /// <summary>A game's samples placed on the SESSION axis (x0 = the
        /// game's offset), as the drawing type.</summary>
        private static List<Vector2> Shift(List<Pt> s, float x0, bool leadingZero)
        {
            var out_ = new List<Vector2>(s.Count + 1);
            if (leadingZero) out_.Add(new Vector2(x0, 0f));
            for (int i = 0; i < s.Count; i++) out_.Add(new Vector2(x0 + Mathf.Max(0f, s[i].X), s[i].Y));
            return out_;
        }

        private static void AddLine(Panel p, string pid, Color tint, List<Vector2> pts, int player, int side)
        {
            if (pts == null || pts.Count == 0) return;
            for (int i = 0; i < pts.Count; i++) if (pts[i].y > p.MaxY) p.MaxY = pts[i].y;
            p.Lines.Add(new Poly { PlayerId = pid, Tint = tint, Pts = pts, Player = player, Side = side });
        }

        /// <summary>Round 2 L1: the text of a chart, bar set or table with no
        /// data - "not recorded for this set" when a set of this mode can carry
        /// the metric, "not supported for this mode" only when no set of the
        /// mode can (SessionReportRules.MissingReason, executed by the client
        /// harness; its per-mode lists are checked against the server's
        /// loaders).</summary>
        private static string MissingText(string kind, string metric)
        {
            return MissingReason(kind, metric) == MISSING_MODE
                ? I18n.Tr("not supported for this mode")
                : I18n.Tr("not recorded for this set");
        }

        private static void Finish(Panel p, string missing)
        {
            if (p.Lines.Count == 0) { p.Missing = missing; return; }
            if (p.Percent) p.MaxY = 100f;
            else p.MaxY = NiceCeil(p.MaxY);
        }

        /// <summary>The race's end scores where a game has no point events
        /// (2v2, 1v2, or a player with no stream), and its y-axis: the rounds
        /// the mode is played to (SessionReportRules.RaceTop over WinTarget),
        /// raised only if a recorded score is higher, so nothing is ever
        /// clipped. A game whose target is not recorded (an FFA game with no
        /// settings record) contributes no target: the axis is never drawn to
        /// a guessed number, and the panel's Note says the target is not
        /// recorded (round 2 M2). The other panels keep NiceCeil.</summary>
        private static void FinishRace(Model m, Envelope env, string missing)
        {
            var p = m.Score;
            var raced = new HashSet<int>();
            for (int gi = 0; gi < env.Games.Count; gi++)
            {
                var g = env.Games[gi];
                var sp = m.Spans[gi];
                raced.Clear();
                foreach (var l in p.Lines)
                    if (l.Pts.Count > 0 && l.Pts[0].x >= sp.X0 - 0.01f && l.Pts[0].x < sp.X1) raced.Add(l.Side);
                // A side with no stream in this game (a 2v2 / 1v2 game recorded
                // before ask 9, a 1v1 with no point events): its recorded end
                // score as one dot per side, at the game's end.
                for (int si = 0; si < m.Sides.Count; si++)
                {
                    if (raced.Contains(si)) continue;
                    int at;
                    int v = SideScoreOf(g, m.Players, m.Sides[si], out at);
                    if (at < 0) continue;
                    p.Dots.Add(new Dot { X = sp.X1, Y = v, Tint = m.SideTints[si], Label = Coloured(m, at, v.ToString(INV)) });
                }
            }
            if (p.Lines.Count == 0 && p.Dots.Count == 0) { p.Missing = missing; return; }
            float recorded = 0f;
            foreach (var l in p.Lines) foreach (var pt in l.Pts) recorded = Mathf.Max(recorded, pt.y);
            foreach (var d in p.Dots) recorded = Mathf.Max(recorded, d.Y);
            int unknown;
            p.MaxY = RaceTop(m.Kind, env.Games, recorded, out unknown);
            if (unknown > 0)
                p.Note = unknown >= env.Games.Count
                    ? I18n.Tr("race target not recorded: the axis ends at the top score")
                    : I18n.TrF("race target not recorded for {0} of {1} games", unknown, env.Games.Count);
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
                    if (s.Count > 0 && s[s.Count - 1].X > t) t = s[s.Count - 1].X;
            foreach (var d in g.Deaths) if (d.T > t) t = d.T;
            return t;
        }

        // -- builds blocks --------------------------------------------------------

        // NativeUI's rarity colours (C_COMMON, C_UNCOMMON, C_RARE, and C_LABEL
        // for anything else - NativeUI.GetRarityColor), repeated because NativeUI
        // keeps them private; a source pin holds the two sets equal.
        private static readonly Color RARITY_COMMON = new Color(0.9f, 0.9f, 0.9f);
        private static readonly Color RARITY_UNCOMMON = new Color(0.3f, 0.6f, 1f);
        private static readonly Color RARITY_RARE = new Color(0.95f, 0.35f, 0.65f);
        private static readonly Color RARITY_OTHER = new Color(0.7f, 0.7f, 0.75f);
        private static readonly Color ROLLED_TEXT = new Color(0.44f, 0.48f, 0.53f);
        internal static readonly Color STRIP_SHORT = new Color(0.45f, 0.8f, 0.55f);
        internal static readonly Color STRIP_LONG = new Color(0.95f, 0.65f, 0.3f);

        internal static Color RarityTint(string rarity)
        {
            switch ((rarity ?? "").ToLowerInvariant())
            {
                case "common": return RARITY_COMMON;
                case "uncommon": return RARITY_UNCOMMON;
                case "rare": return RARITY_RARE;
                default: return RARITY_OTHER;
            }
        }

        /// <summary>A chip for a card as the server recorded it (either name
        /// form, learning #19): the localized display name, and the rarity the
        /// loaded card list gives it (grey while unknown).</summary>
        private static Chip MakeChip(string card, bool rolled)
        {
            string rarity = null, shown = null;
            try { rarity = CardRarityLookup.GetRarity(card); } catch { rarity = null; }
            try { shown = CardTextLocalizer.PrettyName(card, card); } catch { shown = null; }
            string text = Safe(string.IsNullOrEmpty(shown) ? card : shown, CARD_CAP);
            Color tint = RarityTint(rarity);
            return new Chip { Text = text, Label = Tinted(rolled ? ROLLED_TEXT : tint, text), Tint = tint, Rolled = rolled, Card = card ?? "" };
        }

        private static string Tinted(Color c, string text)
            => "<color=#" + ColorUtility.ToHtmlStringRGB(c) + ">" + text + "</color>";

        private static bool HasCards(Game g, string pid)
        {
            foreach (var pk in g.Picks) if (pk.Id == pid) return true;
            List<string> cards;
            return g.EndBuild.TryGetValue(pid, out cards) && cards != null && cards.Count > 0;
        }

        /// <summary>A builds block's header: the game's number and its recorded
        /// score, the winner in colour - the same labels the timeline's game
        /// dividers use.</summary>
        private static string BlockHeader(Model m, Game g, int number)
        {
            int sa, sb, ia, ib;
            if (SideScores(m.Kind, g, m.Players, m.Sides, out sa, out sb, out ia, out ib))
                return I18n.TrF("Game {0}: {1}", number, ScoreLine(m, sa, sb, g));
            return FfaScoreLabel(m, g, number, true);
        }

        // -- small helpers ----------------------------------------------------------

        // Round 2 M1: there is no "missing score reads 0" getter here. Every
        // rendered score comes from SessionReportRules.SideScores, SideScore or
        // Standings (executed by the client harness), which omit a player with
        // no key in the game.

        private static float Val(Dictionary<string, float> d, string k) { float v; return d.TryGetValue(k, out v) ? v : float.NaN; }

        private static string Cell(Dictionary<string, float> d, string k)
        {
            float v;
            return d.TryGetValue(k, out v) ? v.ToString("F0", INV) : "-";
        }

        /// <summary>The two sides' score line - side 1's names, the scores, side
        /// 2's names (SideNames: each member in its colour, joined with " + ") -
        /// with the winning side's SCORE in that side's tint, the loser's in ink.
        /// Every two-sided kind reads the same: a 2v2's "team 1" and a 1v2's
        /// "solo" / "duo" are the players' own names now. Handed a game, it names
        /// the members who played that game (SideNameIn); the set-wide names
        /// otherwise. It prints the side totals it is handed and reads no key.</summary>
        private static string ScoreLine(Model m, int sa, int sb, Game g = null)
        {
            string na = SideNameIn(m, 0, g), nb = SideNameIn(m, 1, g);
            string a = sa.ToString(INV), b = sb.ToString(INV);
            if (sa > sb) a = Tinted(m.SideTints[0], a);
            else if (sb > sa) b = Tinted(m.SideTints[1], b);
            return na + "  " + a + "-" + b + "  " + nb;
        }

        /// <summary>A side's name in one game: the members who played it (a key
        /// in the game's scores, or cards), each in its colour, joined with " + ";
        /// the set-wide name (SideNames) when no game is given or none of them
        /// has a key there (round 1 L1: a game's heading named a teammate who
        /// sat that game out).</summary>
        private static string SideNameIn(Model m, int si, Game g)
        {
            if (si >= m.SideNames.Count) return "?";
            if (g == null) return m.SideNames[si];
            var slots = m.Sides[si].Slots;
            StringBuilder names = null;
            for (int k = 0; k < slots.Count; k++)
            {
                string id = m.Players[slots[k]].Id;
                if (!g.Scores.ContainsKey(id) && !HasCards(g, id)) continue;
                if (names == null) names = new StringBuilder();
                else names.Append(" + ");
                names.Append(Coloured(m, slots[k], Safe(m.Players[slots[k]].Name)));
            }
            return names == null ? m.SideNames[si] : names.ToString();
        }

        private static string FfaScoreLabel(Model m, Game g, int gi, bool longForm)
        {
            var order = Standings(g, m.Players);
            if (order.Count == 0) return longForm ? I18n.TrF("Game {0}", gi) : I18n.TrF("G{0}", gi);
            if (!longForm)
                return I18n.TrF("G{0} {1}", gi, Coloured(m, order[0], g.Scores[m.Players[order[0]].Id].ToString(INV)));
            var sb = new StringBuilder();
            int shown = Math.Min(4, order.Count);
            for (int k = 0; k < shown; k++)
            {
                if (k > 0) sb.Append(", ");
                int pi = order[k];
                sb.Append(Coloured(m, pi, Safe(m.Players[pi].Name))).Append(' ')
                  .Append(g.Scores[m.Players[pi].Id].ToString(INV));
            }
            if (order.Count > shown) sb.Append(", ").Append(I18n.TrF("+{0} more", order.Count - shown));
            return I18n.TrF("Game {0}: {1}", gi, sb.ToString());
        }

        internal static string Coloured(Model m, int pi, string text)
        {
            if (pi < 0 || pi >= m.Tints.Count) return text;
            return "<color=#" + ColorUtility.ToHtmlStringRGB(m.Tints[pi]) + ">" + text + "</color>";
        }

        /// <summary>Server-authored text made safe for a rich-text label: the
        /// tag characters go, control characters go, and the name is capped.</summary>
        internal static string Safe(string s) => Safe(s, NAME_CAP);

        private static string Safe(string s, int cap)
        {
            if (string.IsNullOrEmpty(s)) return "?";
            var sb = new StringBuilder(Math.Min(s.Length, cap));
            foreach (char c in s)
            {
                if (c == '<' || c == '>' || char.IsControl(c)) continue;
                sb.Append(c);
                if (sb.Length >= cap) break;
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
