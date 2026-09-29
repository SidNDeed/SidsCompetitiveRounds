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
        internal const float WINDOW_S = 15f;
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
        }

        internal sealed class Span
        {
            public float X0, X1;
            public string LabelLong = "", LabelShort = "";
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
        }

        /// <summary>One player's column of a builds block.</summary>
        internal sealed class BuildCol
        {
            public string Name = "";         // in the player's colour
            public readonly List<Chip> Chips = new List<Chip>();
            public string Note = "";         // "no cards recorded" when there is no chip
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
            public bool HasRolled;           // a chip of this block is a rolled-out card
            public readonly List<BuildCol> Cols = new List<BuildCol>();
        }

        /// <summary>A Set page tile: what it counts, the number, a footnote.</summary>
        internal sealed class Tile { public string Label = "", Value = "", Sub = ""; }

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
            public readonly List<string> Header = new List<string>();
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
            // the Totals pages (board row 30d): set, players, per game, progress
            public Derived Derived;
            public readonly List<Tile> SetTiles = new List<Tile>();
            public readonly List<StripSeg> Strip = new List<StripSeg>();
            public float StripTotal;
            public string StripKey = "", StripNote = "", RaceLine = "", RaceNote = "";
            public readonly Table Combat = new Table(), Play = new Table(), Progress = new Table();
            public Bars DamageBars, KillsBars, GoldBars, XpBars;
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
                if (last <= first) return I18n.TrF("Game {0} of {1}", first + 1, Builds.Count);
                return I18n.TrF("Games {0}-{1} of {2}", first + 1, last + 1, Builds.Count);
            }

            /// <summary>Footer title for page `pg`; a builds page names the
            /// games it holds (first..last, 0-based, as the view packed them).</summary>
            public string PageTitle(int pg, int first, int last)
            {
                if (pg < FIXED_PAGES) return pg >= 0 ? PageTitles[pg] : "";
                if (Builds.Count == 0) return BuildsTitle;
                return BuildsTitle + " - " + BuildsRange(first, last);
            }
        }

        private static readonly string[] PALETTE =
            { "#99B3E6", "#E69988", "#8FD18F", "#E6C866", "#C48CFF", "#66D9E6", "#FFB347", "#F28CC8" };

        internal static Model Build(Envelope env)
        {
            var m = new Model { Env = env, Kind = env.Kind ?? "" };
            string missing = I18n.Tr("not recorded for this mode");
            m.PageTitles[0] = I18n.Tr("Timeline");
            m.PageTitles[1] = I18n.Tr("Rates");
            m.PageTitles[2] = I18n.Tr("Set totals");
            m.PageTitles[3] = I18n.Tr("Player totals");
            m.PageTitles[4] = I18n.Tr("Per game");
            m.PageTitles[5] = I18n.Tr("Progress");
            m.BuildsTitle = I18n.Tr("Builds");

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
                int sa, sb;
                if (PairScores(g, m.Players, out sa, out sb))
                {
                    // Two players who both have a key in this game (round 2 M1:
                    // a missing key is never a 0; the standings below omit it).
                    if (sa > sb) setWins[0]++; else if (sb > sa) setWins[1]++;
                    sp.LabelShort = sa.ToString(INV) + "-" + sb.ToString(INV);
                    sp.LabelLong = ScoreLine(m, 0, sa, 1, sb);
                }
                else if (m.Kind == "team" || m.Kind == "ovt")
                {
                    // Two sides: the recorded side scores, winner's score in colour.
                    sp.LabelShort = TeamScoreLabel(m, g, gi, false);
                    sp.LabelLong = TeamScoreLabel(m, g, gi, true);
                }
                else
                {
                    // N players (FFA): the recorded points, best first.
                    sp.LabelShort = FfaScoreLabel(m, g, gi, false);
                    sp.LabelLong = FfaScoreLabel(m, g, gi, true);
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
            if (env.GamesOmitted > 0)
                m.Note = I18n.TrF("showing the newest {0} games of this sitting ({1} not shown)", env.Games.Count, env.GamesOmitted);
            else if (env.Truncated)
                m.Note = I18n.TrF("showing the newest {0} games of this sitting", env.Games.Count);
            if (env.V != 1) m.Note = I18n.TrF("report version {0} - some panels may be missing", env.V);

            // Page 1 — cumulative damage and the score race, per game segment.
            m.Damage = new Panel { Title = I18n.Tr("Damage dealt (cumulative per game)"), Unit = I18n.Tr("dmg") };
            m.Score = new Panel { Title = I18n.Tr("Score race (rounds won per game)"), Unit = I18n.Tr("rounds"), Rounds = true };
            float racePer = RaceDivisor(m.Kind);
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
                    Dictionary<string, List<Pt>> streams;
                    if (!g.Timelines.TryGetValue(pid, out streams) || streams == null) continue;
                    List<Pt> dmg, score, shots, hits, blocks, blocksOk, ping, fps;
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
                    if (score != null && score.Count > 0 && racePer > 0f)
                    {
                        // Board row 30e: the race plots ROUNDS won (floor(value / per)
                        // at every sample - SessionReportRules.RoundsSeries, executed
                        // by the client harness), with the within-round points as a
                        // thin secondary line.
                        var rounds = Shift(RoundsSeries(score, racePer, false), sp.X0, true);
                        AddLine(m.Score, pid, m.Tints[pi], rounds);
                        m.Score.Lines[m.Score.Lines.Count - 1].Step = true;
                        m.Score.Thin.Add(new Poly
                        {
                            PlayerId = pid, Tint = m.Tints[pi],
                            Pts = Shift(RoundsSeries(score, racePer, true), sp.X0, true),
                        });
                    }
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
                                      && blocks[blocks.Count - 1].Y > totBlocks + 3f;
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
            foreach (var pn in new[] { m.Damage, m.Dps, m.HitPct, m.BlockPct, m.Ping, m.Fps })
                Finish(pn, missing);
            FinishRace(m, env, missing);
            if (m.BlockPct.Missing != null && legacyBlocks)
                m.BlockPct.Missing = I18n.Tr("not recorded (older block format)");

            // The Totals pages (board row 30d): derived by SessionReportRules.Derive,
            // which the client harness executes; rating, gold and XP are read
            // from set_summary ONCE (C-7).
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
                    foreach (var ch in col.Chips) gb.HasRolled |= ch.Rolled;
                    string stats;
                    if (g.EndStats.TryGetValue(pid, out stats) && !string.IsNullOrEmpty(stats)) col.StatsWire = stats;
                    gb.Cols.Add(col);
                }
                m.Builds.Add(gb);
            }
            if (m.Builds.Count == 0) m.BuildsMissing = I18n.Tr("no build recorded for these games");
            m.ChipKey = Tinted(RARITY_COMMON, I18n.Tr("Common")) + "   " + Tinted(RARITY_UNCOMMON, I18n.Tr("Uncommon"))
                        + "   " + Tinted(RARITY_RARE, I18n.Tr("Rare"));
            m.RolledKey = Tinted(ROLLED_TEXT, I18n.Tr("dimmed: rolled out of the build"));
            return m;
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

            // Set: the tiles, the game-length strip and the score race summary.
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
            var race = new StringBuilder();
            for (int gi = 0; gi < env.Games.Count; gi++)
            {
                if (gi > 0) race.Append("      ");
                race.Append(BlockHeader(m, env.Games[gi], gi + 1));
            }
            m.RaceLine = race.ToString();
            if (set.LeadChanges >= 0)
                m.RaceNote = I18n.TrF("The lead in rounds changed hands {0} times over the set", set.LeadChanges);

            // Players: combat, then cards, points and momentum.
            m.Combat.Title = I18n.Tr("Combat");
            var combat = new List<KeyValuePair<string, string[]>>();
            Column(combat, I18n.Tr("Damage"), n, pi => F0(d.Players[pi].Total("damage")));
            Column(combat, I18n.Tr("Dmg/game"), n, pi => PerGame(d.Players[pi].DamageByGame, "F0"));
            Column(combat, I18n.Tr("Shots"), n, pi => F0(d.Players[pi].Total("shots")));
            Column(combat, I18n.Tr("Hit %"), n, pi => Pct(d.Players[pi].Total("hits"), d.Players[pi].Total("shots")));
            Column(combat, I18n.Tr("Blocks"), n, pi => F0(d.Players[pi].Total("blocks")));
            Column(combat, I18n.Tr("Block %"), n, pi => Pct(d.Players[pi].Total("blocks_ok"), d.Players[pi].Total("blocks")));
            Column(combat, I18n.Tr("Keys/s"), n, pi => KeysPerS(d.Players[pi]));
            Column(combat, I18n.Tr("Deaths"), n, pi => F0(d.Players[pi].Total("deaths")));
            Column(combat, I18n.Tr("Kills"), n, pi => F0(d.Players[pi].Kills));
            Column(combat, I18n.Tr("Kills/game"), n, pi => PerGame(d.Players[pi].KillsByGame, "F1"));
            Column(combat, I18n.Tr("K/D"), n, pi => Kd(d.Players[pi]));
            FillTable(m, m.Combat, combat);

            m.Play.Title = I18n.Tr("Cards and points");
            var play = new List<KeyValuePair<string, string[]>>();
            Column(play, I18n.Tr("Cards picked"), n, pi => Int(d.Players[pi].CardsPicked));
            Column(play, I18n.Tr("Cards/game"), n, pi => d.Players[pi].CardsPicked.HasValue && d.Players[pi].Games > 0
                ? (d.Players[pi].CardsPicked.Value / (float)d.Players[pi].Games).ToString("F1", INV) : null);
            Column(play, I18n.Tr("Points won"), n, pi => Int(d.Players[pi].PointsWon));
            Column(play, I18n.Tr("Points lost"), n, pi => Int(d.Players[pi].PointsLost));
            Column(play, I18n.Tr("First bloods"), n, pi => Int(d.Players[pi].FirstBloods));
            Column(play, I18n.Tr("Longest point streak"), n, pi => Int(d.Players[pi].LongestStreak));
            Column(play, I18n.Tr("Biggest comeback (rounds)"), n, pi => Int(d.Players[pi].BiggestComeback));
            Column(play, I18n.Tr("Time in lead"), n, pi => d.Players[pi].LeadS.HasValue ? Clock(d.Players[pi].LeadS.Value) : null);
            FillTable(m, m.Play, play);

            // Per game: one bar per player per game.
            int games = env.Games.Count;
            m.DamageBars = MakeBars(I18n.Tr("Damage per game"), I18n.Tr("dmg"), d, pl => pl.DamageByGame, games);
            m.KillsBars = MakeBars(I18n.Tr("Kills per game"), I18n.Tr("kills"), d, pl => pl.KillsByGame, games);

            // Progress: rating before / after / change, gold and XP this set.
            m.Progress.Title = I18n.Tr("Rating, gold and XP");
            var prog = new List<KeyValuePair<string, string[]>>();
            Column(prog, I18n.Tr("Rating before"), n, pi => RatingCell(env, m, pi, 0));
            Column(prog, I18n.Tr("Rating after"), n, pi => RatingCell(env, m, pi, 1));
            Column(prog, I18n.Tr("Change"), n, pi => RatingCell(env, m, pi, 2));
            Column(prog, I18n.Tr("Gold this set"), n, pi => Signed(d.Players[pi].Gold));
            Column(prog, I18n.Tr("XP this set"), n, pi => Signed(d.Players[pi].Xp));
            FillTable(m, m.Progress, prog);
            m.GoldBars = MakeBars(I18n.Tr("Gold per game"), I18n.Tr("gold"), d, pl => pl.GoldByGame, games);
            m.XpBars = MakeBars(I18n.Tr("XP per game"), I18n.Tr("XP"), d, pl => pl.XpByGame, games);
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
            for (int pi = 0; pi < m.Players.Count; pi++)
            {
                var row = new List<string> { Coloured(m, pi, Safe(m.Players[pi].Name)) };
                foreach (var c in cols) row.Add(c.Value[pi] ?? "-");
                t.Rows.Add(row);
            }
        }

        private static Bars MakeBars(string title, string unit, Derived d, Func<PlayerLine, List<float?>> pick, int games)
        {
            var b = new Bars { Title = title, Unit = unit };
            bool any = false;
            for (int gi = 0; gi < games; gi++)
            {
                var row = new float?[d.Players.Count];
                var text = new string[d.Players.Count];
                for (int pi = 0; pi < row.Length; pi++)
                {
                    var xs = pick(d.Players[pi]);
                    row[pi] = gi < xs.Count ? xs[gi] : null;
                    if (!row[pi].HasValue) continue;
                    any = true;
                    float v = row[pi].Value;
                    if (v > b.MaxY) b.MaxY = v;
                    text[pi] = v.ToString(Mathf.Abs(v - Mathf.Round(v)) < 0.05f ? "F0" : "F1", INV);
                }
                b.Values.Add(row);
                b.Texts.Add(text);
                b.Labels.Add("<color=#8FA3B8>" + (gi + 1).ToString(INV) + "</color>");
            }
            if (!any) b.Missing = I18n.Tr("not recorded for this mode");
            else b.MaxY = NiceCeil(b.MaxY);
            return b;
        }

        /// <summary>The set's final score in games won: the two names with the
        /// winner in colour (two players), the two sides (2v2 / 1v2), or the
        /// best four (FFA).</summary>
        private static string FinalScore(Model m, int[] wins)
        {
            int n = m.Players.Count;
            if (n == 2) return ScoreLine(m, 0, wins[0], 1, wins[1]);
            if (m.Kind == "team" || m.Kind == "ovt")
            {
                int p1 = -1, p2 = -1;
                for (int i = 0; i < n; i++)
                {
                    if (m.Players[i].Team == 1 && p1 < 0) p1 = i;
                    else if (m.Players[i].Team == 2 && p2 < 0) p2 = i;
                }
                if (p1 < 0 || p2 < 0) return "-";
                string a = wins[p1].ToString(INV), b = wins[p2].ToString(INV);
                if (wins[p1] > wins[p2]) a = Coloured(m, p1, a);
                else if (wins[p2] > wins[p1]) b = Coloured(m, p2, b);
                return m.Kind == "ovt"
                    ? I18n.TrF("solo {0}-{1} duo", a, b)
                    : I18n.TrF("team 1 {0}-{1} team 2", a, b);
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

        /// <summary>The race's end scores where a game has no point events
        /// (2v2, 1v2, or a player with no stream), and its y-axis: the rounds
        /// the mode is played to (WinTarget), raised only if a recorded score
        /// is higher, so nothing is ever clipped. The other panels keep NiceCeil.</summary>
        private static void FinishRace(Model m, Envelope env, string missing)
        {
            var p = m.Score;
            var raced = new HashSet<string>();
            int target = 0;
            for (int gi = 0; gi < env.Games.Count; gi++)
            {
                var g = env.Games[gi];
                target = Math.Max(target, WinTarget(m.Kind, g));
                var sp = m.Spans[gi];
                raced.Clear();
                foreach (var l in p.Lines)
                    if (l.Pts.Count > 0 && l.Pts[0].x >= sp.X0 - 0.01f && l.Pts[0].x < sp.X1) raced.Add(l.PlayerId);
                bool sides = m.Kind == "team" || m.Kind == "ovt";
                var seenSide = new HashSet<int>();
                for (int pi = 0; pi < m.Players.Count; pi++)
                {
                    string pid = m.Players[pi].Id;
                    int v;
                    if (raced.Contains(pid) || !g.Scores.TryGetValue(pid, out v)) continue;
                    // a side's players carry the side's rounds: one dot per side
                    if (sides && !seenSide.Add(m.Players[pi].Team)) continue;
                    p.Dots.Add(new Dot { X = sp.X1, Y = v, Tint = m.Tints[pi], Label = Coloured(m, pi, v.ToString(INV)) });
                }
            }
            if (p.Lines.Count == 0 && p.Dots.Count == 0) { p.Missing = missing; return; }
            float top = Math.Max(1, target);
            foreach (var l in p.Lines) foreach (var pt in l.Pts) top = Mathf.Max(top, pt.y);
            foreach (var d in p.Dots) top = Mathf.Max(top, d.Y);
            p.MaxY = Mathf.Ceil(top);
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
            return new Chip { Text = text, Label = Tinted(rolled ? ROLLED_TEXT : tint, text), Tint = tint, Rolled = rolled };
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
            int sa, sb;
            if (PairScores(g, m.Players, out sa, out sb))
                return I18n.TrF("Game {0}: {1}", number, ScoreLine(m, 0, sa, 1, sb));
            if (m.Kind == "team" || m.Kind == "ovt") return TeamScoreLabel(m, g, number, true);
            return FfaScoreLabel(m, g, number, true);
        }

        // ── small helpers ────────────────────────────────────────────────────

        // Round 2 M1: there is no "missing score reads 0" getter here. Every
        // rendered score comes from SessionReportRules.PairScores, SideScore or
        // Standings (executed by the client harness), which omit a player with
        // no key in the game.

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

        /// <summary>Divider label for a two-SIDED game (2v2, 1v2): the recorded
        /// side scores — every player of a side carries the side's rounds — with
        /// the winning side's score in that side's first player's colour. Short
        /// form for a narrow segment, long form names the sides. A side with no
        /// player who has a key in this game gives no score line (round 2 M1).</summary>
        private static string TeamScoreLabel(Model m, Game g, int gi, bool longForm)
        {
            int p1, p2;
            int s1 = SideScore(g, m.Players, 1, out p1), s2 = SideScore(g, m.Players, 2, out p2);
            if (p1 < 0 || p2 < 0)
                return longForm ? I18n.TrF("Game {0}", gi) : I18n.TrF("G{0}", gi);
            string a = s1.ToString(INV), b = s2.ToString(INV);
            if (s1 > s2) a = Coloured(m, p1, a);
            else if (s2 > s1) b = Coloured(m, p2, b);
            if (!longForm) return I18n.TrF("G{0} {1}-{2}", gi, a, b);
            return m.Kind == "ovt"
                ? I18n.TrF("Game {0}: solo {1}-{2} duo", gi, a, b)
                : I18n.TrF("Game {0}: team 1 {1}-{2} team 2", gi, a, b);
        }

        /// <summary>Divider label for an N-player game (FFA): the recorded points,
        /// best first, names in colour; at most four names, the rest counted.
        /// Only the players who PLAYED this game (SessionReportRules.Standings):
        /// a fluid lobby's union roster names players who sat it out, and they
        /// are omitted here, never shown with a 0 (round 2 M1).</summary>
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
