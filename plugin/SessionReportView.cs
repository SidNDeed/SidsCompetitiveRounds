using System;
using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Sept 6 batch (Group 4 item c) — the F5-owned INTERACTIVE session
    /// report: an IMGUI pager (prev / next / Esc, no auto-advance, no
    /// stream-mode requirement) drawn full-screen over the open F5 overlay.
    /// Three fixed pages (timeline, rates, totals) and then the builds: one
    /// compact block per game, as many blocks per page as fit and as many
    /// pages as needed (board row 30c) - the blocks are PAGED, never
    /// discarded, so the page count is dynamic (<see cref="PageCount"/>) and
    /// every key and footer path reads it (review r1).
    /// It draws a <see cref="SessionReportModel.Model"/> and nothing else — all
    /// parsing, sanitizing and maths live in the model.
    ///
    /// Contracts (verified against the live tree):
    ///  - Opened by NativeUI.OpenSessionReport from the history boxes' "Session"
    ///    buttons. Lives only while the F5 page is open: Draw() self-closes the
    ///    moment NativeUI.IsOpen is false (visibility-backed, the #75/#255
    ///    class — a wedged flag can never strand a full-screen backdrop).
    ///  - Esc: NativeUI.Tick consumes it for THIS view before its own close
    ///    while Active, so one Esc closes the report and the next closes the
    ///    page. OnGUI handles the key too, defensively.
    ///  - Torn down by NativeUI.TeardownOverlaySurfaces — the ONE shared close
    ///    path (#369) — so page close, match-start auto-close and the pageGO
    ///    recovery branch all reach Close().
    ///  - Input: CompetitiveUI's BackdroplessModalOpen includes Active, which
    ///    raises the uGUI click blocker AND ClickHandler.ModalBlockInput
    ///    (#141/#200); mouse/scroll events are Used here after the buttons so
    ///    nothing painted underneath reacts. Gameplay input is already gated by
    ///    the open overlay (OverlayInputGate).
    ///  - Read-only HTTP (ApiClient.FetchSessionReport, strict Steam session,
    ///    participant-only server side). Responses are generation-fenced: a
    ///    slow reply for a closed or superseded view is dropped.
    ///  - The broadcast renderer (PostSessionReport) is untouched: its data
    ///    source is the broadcast seat's own history fetches, not this
    ///    participant-authenticated envelope.
    /// Rendering is Repaint-cheap: every string is pre-composed by the model;
    /// styles are built lazily inside OnGUI (GUI.skin is only valid there).</summary>
    internal static class SessionReportView
    {
        public static bool Active { get; private set; }

        private static int gen;
        private static bool loading;
        /// <summary>A short diagnostic CODE, never prose: one of the ERR_*
        /// constants, ApiClient's own codes (no-identity, session_required,
        /// no-consent, ...) or the HTTP failure text. ErrorMessage translates
        /// the code; the raw tail goes to the log, not the label.</summary>
        private static string errorText;
        private const string ERR_LOCAL = "local";     // the request could not be started
        private const string ERR_PARSE = "parse";     // the body was not an envelope
        private const string ERR_MODEL = "model";     // the model builder threw
        private static SessionReportModel.Model model;
        private static int page;
        /// <summary>Build pages measured by the last DrawBuilds pass (the body
        /// height decides how many rows fit); 1 until a pass has run.</summary>
        private static int buildPages = 1;

        private static int PageCount() => SessionReportModel.FIXED_PAGES + Mathf.Max(1, buildPages);

        private static bool stylesReady;
        private static GUIStyle stTitle, stHeader, stBody, stSmall, stSmallR, stBtn, stCell, stCellHead, stCenter, stTiny, stChip;
        private static readonly Color BACKDROP = new Color(0.04f, 0.05f, 0.08f, 0.95f);
        private static readonly Color PANEL = new Color(1f, 1f, 1f, 0.05f);
        private static readonly Color GRID = new Color(1f, 1f, 1f, 0.08f);
        private static readonly Color DIVIDER = new Color(1f, 1f, 1f, 0.40f);
        private static readonly Color ROW = new Color(1f, 1f, 1f, 0.04f);
        private static readonly CultureInfo INV = CultureInfo.InvariantCulture;

        /// <summary>Open (or re-target) the view on one set. `selector` is
        /// series / match / session and `key` the UUID the history row carries;
        /// the server decides what the caller may see.</summary>
        public static void Open(string selector, string key)
        {
            if (string.IsNullOrEmpty(selector) || string.IsNullOrEmpty(key)) return;
            gen++;
            int g = gen;
            Active = true;
            loading = true;
            errorText = null;
            model = null;
            page = 0;
            buildPages = 1;
            try
            {
                ApiClient.FetchSessionReport(selector, key, (ok, body) => OnFetched(g, ok, body));
            }
            catch (Exception ex)
            {
                loading = false;
                errorText = ERR_LOCAL;
                Plugin.Log.LogWarning($"[SESSION-REPORT] fetch: {ex.Message}");
            }
        }

        private static void OnFetched(int g, bool ok, string body)
        {
            if (g != gen || !Active) return;    // closed or re-targeted meanwhile
            loading = false;
            if (!ok)
            {
                // The label shows a translated line for the CODE; the server's
                // actual text (status line + body head) is for the log only.
                errorText = body ?? "";
                string tail = errorText.Length > 160 ? errorText.Substring(0, 160) : errorText;
                Plugin.Log.LogWarning($"[SESSION-REPORT] fetch failed: {tail}");
                return;
            }
            try
            {
                var env = SessionReportRules.Parse(body);
                if (env == null)
                {
                    errorText = ERR_PARSE;
                    Plugin.Log.LogWarning($"[SESSION-REPORT] parse: body was not an envelope ({(body ?? "").Length} chars)");
                    return;
                }
                model = SessionReportModel.Build(env);
            }
            catch (Exception ex)
            {
                errorText = ERR_MODEL;
                Plugin.Log.LogWarning($"[SESSION-REPORT] build: {ex.Message}");
            }
        }

        /// <summary>Idempotent. Bumps the generation so an in-flight reply is
        /// dropped rather than reviving a closed view.</summary>
        public static void Close()
        {
            if (!Active && model == null && !loading) return;
            gen++;
            Active = false;
            loading = false;
            errorText = null;
            model = null;
            page = 0;
            buildPages = 1;
        }

        // ── drawing ──────────────────────────────────────────────────────────

        public static void Draw()
        {
            if (!Active) return;
            if (!NativeUI.IsOpen) { Close(); return; }
            var ev = Event.current;
            if (ev == null) return;
            try
            {
                EnsureStyles();
                if (ev.type == EventType.KeyDown)
                {
                    HandleKey(ev);
                    return;
                }
                float W = Screen.width, H = Screen.height;
                Fill(new Rect(0f, 0f, W, H), BACKDROP);
                var content = new Rect(Mathf.Min(40f, W * 0.03f), 22f, W - 2f * Mathf.Min(40f, W * 0.03f), H - 44f);

                // Header block: title, player-neutral score line, legend, sub-line.
                GUI.Label(new Rect(content.x, content.y, content.width * 0.6f, 30f), I18n.Tr("Session report"), stTitle);
                GUI.Label(new Rect(content.x, content.y + 30f, content.width, 30f), model != null ? model.Header : "", stHeader);
                GUI.Label(new Rect(content.x, content.y + 60f, content.width * 0.6f, 22f), model != null ? model.Legend : "", stBody);
                GUI.Label(new Rect(content.x + content.width * 0.6f, content.y, content.width * 0.4f, 22f), model != null ? model.Sub : "", stSmallR);
                GUI.Label(new Rect(content.x + content.width * 0.6f, content.y + 22f, content.width * 0.4f, 22f), model != null ? model.Note : "", stSmallR);

                var body = new Rect(content.x, content.y + 90f, content.width, content.height - 90f - 50f);
                // The build page count follows the body height: measure it every
                // frame (a few dozen blocks) so the footer and the keys are exact
                // before the builds are ever visited, and a resize can never leave
                // the current page past the end.
                if (model != null) MeasureBuildPages(body, model);
                page = Mathf.Clamp(page, 0, PageCount() - 1);
                if (loading) GUI.Label(body, I18n.Tr("Loading..."), stCenter);
                else if (model == null) GUI.Label(body, ErrorMessage(errorText), stCenter);
                else DrawPage(body, model, page);

                DrawFooter(new Rect(content.x, content.yMax - 42f, content.width, 42f));

                // Swallow everything the buttons above did not take (#141/#200 —
                // the uGUI and raw-poll paths are gated by the modal flag).
                if (ev.type == EventType.MouseDown || ev.type == EventType.MouseUp
                    || ev.type == EventType.MouseDrag || ev.type == EventType.ScrollWheel)
                    ev.Use();
            }
            catch (Exception ex)
            {
                // Never let a draw fault strand the backdrop (#255 class).
                Plugin.Log.LogWarning($"[SESSION-REPORT] draw: {ex.Message}");
                Close();
            }
        }

        private static void HandleKey(Event ev)
        {
            switch (ev.keyCode)
            {
                case KeyCode.LeftArrow:
                case KeyCode.PageUp:
                    page = Mathf.Max(0, page - 1); ev.Use(); break;
                case KeyCode.RightArrow:
                case KeyCode.PageDown:
                    page = Mathf.Min(PageCount() - 1, page + 1); ev.Use(); break;
                case KeyCode.Home: page = 0; ev.Use(); break;
                case KeyCode.End: page = PageCount() - 1; ev.Use(); break;
                case KeyCode.Escape: Close(); ev.Use(); break;
            }
        }

        /// <summary>The visible line for a diagnostic code. Every branch is a
        /// catalogue string; the only server-authored characters that can reach
        /// the label are the three digits of an HTTP status.</summary>
        private static string ErrorMessage(string raw)
        {
            string e = raw ?? "";
            if (e == ERR_LOCAL)
                return I18n.Tr("The report request could not be started");
            if (e == ERR_PARSE || e == ERR_MODEL)
                return I18n.Tr("The report could not be read");
            if (e == "no-identity")
                return I18n.Tr("Steam identity is not available yet");
            if (e == "no-consent")
                return I18n.Tr("Data sharing is disabled in your settings");
            if (e.Contains("401") || e.Contains("session_required"))
                return I18n.Tr("Steam sign-in is required to view session reports");
            if (e.Contains("404") || e.Contains("not_found"))
                return I18n.Tr("This report is not available");
            string status = HttpStatusOf(e);
            return status.Length > 0
                ? I18n.TrF("Could not load this report (error {0})", status)
                : I18n.Tr("Could not load this report");
        }

        /// <summary>The first three-digit run in an ApiClient failure text
        /// ("HTTP 503 ...", "Error: 500"), or "" — digits only, locale-neutral.</summary>
        private static string HttpStatusOf(string e)
        {
            for (int i = 0; i + 3 <= e.Length; i++)
            {
                if (!char.IsDigit(e[i]) || !char.IsDigit(e[i + 1]) || !char.IsDigit(e[i + 2])) continue;
                if (i > 0 && char.IsDigit(e[i - 1])) continue;
                if (i + 3 < e.Length && char.IsDigit(e[i + 3])) continue;
                if (e[i] < '1' || e[i] > '5') continue;
                return e.Substring(i, 3);
            }
            return "";
        }

        private static void DrawFooter(Rect r)
        {
            Fill(r, PANEL);
            float bw = 110f, bh = 30f, y = r.y + (r.height - bh) / 2f;
            bool wasEnabled = GUI.enabled;
            GUI.enabled = model != null && page > 0;
            if (GUI.Button(new Rect(r.x + 8f, y, bw, bh), I18n.Tr("< Prev"), stBtn)) page = Mathf.Max(0, page - 1);
            int pages = PageCount();
            GUI.enabled = model != null && page < pages - 1;
            if (GUI.Button(new Rect(r.x + 16f + bw, y, bw, bh), I18n.Tr("Next >"), stBtn))
                page = Mathf.Min(pages - 1, page + 1);
            GUI.enabled = wasEnabled;
            string pageLabel = "";
            if (model != null)
            {
                // A builds page names the games it holds, from the same page
                // breaks the draw path uses.
                int first = 0, last = 0;
                if (page >= SessionReportModel.FIXED_PAGES && buildStarts.Count > 0)
                {
                    int sub = Mathf.Clamp(page - SessionReportModel.FIXED_PAGES, 0, buildStarts.Count - 1);
                    first = buildStarts[sub];
                    last = (sub + 1 < buildStarts.Count ? buildStarts[sub + 1] : model.Builds.Count) - 1;
                }
                pageLabel = I18n.TrF("Page {0}/{1}", page + 1, pages) + "  -  " + model.PageTitle(page, first, last);
            }
            GUI.Label(new Rect(r.x + 24f + 2f * bw, y, r.width - 48f - 3f * bw, bh), pageLabel, stBody);
            if (GUI.Button(new Rect(r.xMax - bw - 8f, y, bw, bh), I18n.Tr("Close"), stBtn)) Close();
        }

        private static void DrawPage(Rect body, SessionReportModel.Model m, int pg)
        {
            const float gap = 10f;
            switch (pg)
            {
                case 0:
                {
                    float h1 = (body.height - gap) * 0.56f, h2 = body.height - gap - h1;
                    DrawPanel(new Rect(body.x, body.y, body.width, h1), m.Damage, m, true);
                    DrawPanel(new Rect(body.x, body.y + h1 + gap, body.width, h2), m.Score, m, false);
                    break;
                }
                case 1:
                {
                    float hp = (body.height - 3f * gap) * 0.26f, hs = body.height - 3f * gap - 3f * hp;
                    DrawPanel(new Rect(body.x, body.y, body.width, hp), m.Dps, m, false);
                    DrawPanel(new Rect(body.x, body.y + hp + gap, body.width, hp), m.HitPct, m, false);
                    DrawPanel(new Rect(body.x, body.y + 2f * (hp + gap), body.width, hp), m.BlockPct, m, false);
                    float sy = body.y + 3f * (hp + gap), half = (body.width - gap) / 2f;
                    DrawPanel(new Rect(body.x, sy, half, hs), m.Ping, m, false);
                    DrawPanel(new Rect(body.x + half + gap, sy, half, hs), m.Fps, m, false);
                    break;
                }
                case 2: DrawTotals(body, m); break;
                default: DrawBuilds(body, m, pg - SessionReportModel.FIXED_PAGES); break;
            }
        }

        // ── graph panel ──────────────────────────────────────────────────────

        private static void DrawPanel(Rect r, SessionReportModel.Panel p, SessionReportModel.Model m, bool marks)
        {
            Fill(r, PANEL);
            GUI.Label(new Rect(r.x + 8f, r.y + 2f, r.width * 0.7f, 22f), p.Title, stBody);
            GUI.Label(new Rect(r.xMax - r.width * 0.3f - 8f, r.y + 2f, r.width * 0.3f, 22f), p.Unit, stSmallR);
            if (p.Missing != null)
            {
                GUI.Label(r, "<color=#8FA3B8>" + p.Missing + "</color>", stCenter);
                return;
            }
            var plot = new Rect(r.x + 60f, r.y + 28f, r.width - 76f, r.height - 28f - 22f);
            if (plot.width < 20f || plot.height < 10f) return;

            // Horizontal grid with axis values.
            for (int k = 0; k <= 4; k++)
            {
                float y = plot.yMax - plot.height * k / 4f;
                CompetitiveUI.GuiLine(new Vector2(plot.xMin, y), new Vector2(plot.xMax, y), GRID, 1f);
                float v = p.MaxY * k / 4f;
                string lab = p.Percent ? v.ToString("F0", INV) + "%" : v.ToString(v >= 100f ? "F0" : "0.#", INV);
                GUI.Label(new Rect(r.x + 4f, y - 10f, 52f, 20f), "<color=#8FA3B8>" + lab + "</color>", stSmallR);
            }
            // Game dividers, labels and end-time ticks (time space, per-game offsets — C-6).
            float scale = plot.width / Mathf.Max(1f, m.TotalS);
            for (int gi = 0; gi < m.Spans.Count; gi++)
            {
                var sp = m.Spans[gi];
                float x0 = plot.x + sp.X0 * scale, x1 = plot.x + sp.X1 * scale;
                if (gi > 0) CompetitiveUI.GuiLine(new Vector2(x0, plot.yMin), new Vector2(x0, plot.yMax), DIVIDER, 1f);
                float segW = x1 - x0;
                string lab = segW >= 150f ? sp.LabelLong : (segW >= 34f ? sp.LabelShort : "");
                if (lab.Length > 0) GUI.Label(new Rect(x0 + 3f, plot.yMin - 2f, segW - 4f, 18f), lab, stTiny);
                GUI.Label(new Rect(x1 - 44f, plot.yMax + 2f, 44f, 18f),
                    "<color=#8FA3B8>" + SessionReportModel.Clock(sp.X1) + "</color>", stSmallR);
                if (marks)
                {
                    // Card picks: ticks on the divider, stacked by pick order.
                    for (int i = 0; i < sp.Picks.Count && i < 24; i++)
                    {
                        float ty = plot.yMin + 18f + i * 5f;
                        if (ty > plot.yMax - 12f) break;
                        Fill(new Rect(x0 + 1f, ty, 7f, 3f), sp.Picks[i].Tint);
                    }
                }
            }
            // Polylines: one per player per game, in the player's colour.
            for (int li = 0; li < p.Lines.Count; li++)
            {
                var line = p.Lines[li];
                var pts = line.Pts;
                for (int i = 1; i < pts.Count; i++)
                {
                    var a = Map(pts[i - 1], plot, scale, p.MaxY);
                    var b = Map(pts[i], plot, scale, p.MaxY);
                    CompetitiveUI.GuiLine(a, b, line.Tint, 2f);
                }
            }
            if (marks)
            {
                // Deaths: dots along the bottom, one lane per player.
                for (int i = 0; i < m.Deaths.Count; i++)
                {
                    var d = m.Deaths[i];
                    float x = plot.x + Mathf.Clamp(d.X, 0f, m.TotalS) * scale;
                    float y = plot.yMax - 5f - d.Lane * 7f;
                    Fill(new Rect(x - 3f, y - 3f, 6f, 6f), d.Tint);
                }
            }
        }

        private static Vector2 Map(Vector2 pt, Rect plot, float scale, float maxY)
        {
            float x = plot.x + Mathf.Clamp(pt.x * scale, 0f, plot.width);
            float y = plot.yMax - Mathf.Clamp(pt.y / Mathf.Max(1e-3f, maxY), 0f, 1f) * plot.height;
            return new Vector2(x, y);
        }

        // ── totals page ──────────────────────────────────────────────────────

        private static void DrawTotals(Rect body, SessionReportModel.Model m)
        {
            Fill(body, PANEL);
            int cols = m.TotalsHeader.Count;
            if (cols == 0) return;
            float nameW = Mathf.Min(260f, body.width * 0.28f);
            float otherW = (body.width - nameW - 16f) / Mathf.Max(1, cols - 1);
            float rowH = 30f, y = body.y + 8f;
            for (int c = 0; c < cols; c++)
            {
                float x = body.x + 8f + (c == 0 ? 0f : nameW + (c - 1) * otherW);
                GUI.Label(new Rect(x, y, c == 0 ? nameW : otherW, rowH), "<color=#8FA3B8>" + m.TotalsHeader[c] + "</color>", stCellHead);
            }
            y += rowH;
            for (int ri = 0; ri < m.TotalsRows.Count; ri++)
            {
                if (y + rowH > body.yMax - 8f) break;
                if ((ri & 1) == 0) Fill(new Rect(body.x + 4f, y, body.width - 8f, rowH), ROW);
                var row = m.TotalsRows[ri];
                for (int c = 0; c < cols && c < row.Count; c++)
                {
                    float x = body.x + 8f + (c == 0 ? 0f : nameW + (c - 1) * otherW);
                    GUI.Label(new Rect(x, y, c == 0 ? nameW : otherW, rowH), row[c], stCell);
                }
                y += rowH;
            }
            y += 14f;
            GUI.Label(new Rect(body.x + 8f, y, body.width - 16f, 24f), I18n.Tr("Set summary"), stBody);
            y += 26f;
            for (int i = 0; i < m.SummaryLines.Count; i++)
            {
                if (y + 22f > body.yMax - 4f) break;
                GUI.Label(new Rect(body.x + 8f, y, body.width - 16f, 22f), m.SummaryLines[i], stSmall);
                y += 22f;
            }
        }

        // -- builds pages (board row 30c) ------------------------------------------

        /// <summary>A measured builds block: its height and, per player
        /// column, where the column sits in the block, where each chip sits
        /// (SessionReportRules.FlowChips) and the stat lines laid out for the
        /// column's width. Measured with the styles that draw it.</summary>
        private sealed class ColLayout
        {
            public float X, Y, W, H;                 // relative to the block's inner top-left
            public readonly List<float> ChipW = new List<float>();
            public List<SessionReportRules.Pt> ChipAt = new List<SessionReportRules.Pt>();
            public float ChipsH;
            public string Stats = "";
            public float StatsH;
        }

        private sealed class BlockLayout
        {
            public readonly List<ColLayout> Cols = new List<ColLayout>();
        }

        // First block of every builds page, each block's measured height (its
        // gap included) and layout, index-aligned with m.Builds. Re-measured
        // only when the model or the body size changes; the pager, the footer
        // and the draw path all read these same numbers.
        private static readonly List<int> buildStarts = new List<int>();
        private static readonly List<float> blockH = new List<float>();
        private static readonly List<BlockLayout> blockLayouts = new List<BlockLayout>();
        private static SessionReportModel.Model measuredModel;
        private static float measuredW = -1f, measuredH = -1f;

        private const float PAGE_HEAD_H = 30f, BLOCK_GAP = 8f, BLOCK_PAD = 6f, BLOCK_HEAD_H = 26f;
        private const float COL_GAP = 12f, MIN_COL_W = 190f, NAME_H = 20f;
        private const float CHIP_H = 20f, CHIP_GAP = 4f, CHIP_ROW_GAP = 3f;

        /// <summary>Measures every game's block against the current body and
        /// packs them onto pages: as many blocks per page as fit, a block
        /// taller than a page gets one of its own, none is dropped and there
        /// is no cap (SessionReportRules.PackPages, executed by the client
        /// harness). Sets buildPages, which the pager reads.</summary>
        private static void MeasureBuildPages(Rect body, SessionReportModel.Model m)
        {
            if (ReferenceEquals(m, measuredModel) && body.width == measuredW && body.height == measuredH
                && buildStarts.Count > 0 && blockH.Count == m.Builds.Count)
                return;
            buildStarts.Clear();
            blockH.Clear();
            blockLayouts.Clear();
            measuredModel = m; measuredW = body.width; measuredH = body.height;
            if (m.BuildsMissing != null || m.Builds.Count == 0) { buildStarts.Add(0); buildPages = 1; return; }
            EnsureStyles();
            float innerW = body.width - 16f - 2f * BLOCK_PAD;
            for (int i = 0; i < m.Builds.Count; i++)
            {
                float h;
                blockLayouts.Add(MeasureBlock(m.Builds[i], innerW, out h));
                blockH.Add(h);
            }
            buildStarts.AddRange(SessionReportRules.PackPages(blockH, body.height - PAGE_HEAD_H - 4f));
            buildPages = buildStarts.Count;
        }

        /// <summary>One block: the header row, then the players' columns side
        /// by side - as many per row as the width holds at MIN_COL_W (two in
        /// 1v1, one per player in FFA until the width runs out, then a second
        /// row). `h` is the block's full height including the gap below it.</summary>
        private static BlockLayout MeasureBlock(SessionReportModel.GameBuild b, float innerW, out float h)
        {
            var lay = new BlockLayout();
            int n = b.Cols.Count;
            int perRow = Mathf.Clamp(Mathf.FloorToInt((innerW + COL_GAP) / (MIN_COL_W + COL_GAP)), 1, Mathf.Max(1, n));
            float colW = (innerW - (perRow - 1) * COL_GAP) / perRow;
            float y = BLOCK_HEAD_H, rowH = 0f;
            for (int c = 0; c < n; c++)
            {
                if (c > 0 && c % perRow == 0) { y += rowH + 6f; rowH = 0f; }
                var col = b.Cols[c];
                var cl = new ColLayout { X = (c % perRow) * (colW + COL_GAP), Y = y, W = colW };
                foreach (var chip in col.Chips) cl.ChipW.Add(ChipWidth(chip, colW));
                int rows;
                cl.ChipAt = SessionReportRules.FlowChips(cl.ChipW, colW, CHIP_GAP, out rows);
                cl.ChipsH = rows > 0 ? rows * CHIP_H + (rows - 1) * CHIP_ROW_GAP : 18f;
                if (col.StatsWire.Length > 0)
                {
                    // ~7 px per character of the 12 pt stat text: the packer puts
                    // as many stats on a line as the column holds.
                    int budget = Mathf.Max(12, Mathf.FloorToInt(colW / 7f));
                    try { cl.Stats = NativeUI.BuildStatsTipBlock(col.StatsWire, budget) ?? ""; } catch { cl.Stats = ""; }
                    if (cl.Stats.Length > 0)
                        cl.StatsH = Mathf.Ceil(stTiny.CalcHeight(new GUIContent(cl.Stats), colW)) + 2f;
                }
                cl.H = NAME_H + cl.ChipsH + (cl.StatsH > 0f ? 4f + cl.StatsH : 0f);
                rowH = Mathf.Max(rowH, cl.H);
                lay.Cols.Add(cl);
            }
            h = y + rowH + 2f * BLOCK_PAD + BLOCK_GAP;
            return lay;
        }

        /// <summary>A chip's width: its text measured with the style that
        /// draws it, plus the colour bar and padding; never wider than the
        /// column (a chip that wide takes a row of its own).</summary>
        private static float ChipWidth(SessionReportModel.Chip chip, float colW)
        {
            return Mathf.Min(colW, Mathf.Ceil(stChip.CalcSize(new GUIContent(chip.Text)).x) + 14f);
        }

        /// <summary>Builds page `sub` (0 = the first): the blocks between two
        /// measured page breaks, under a header naming the games it holds.</summary>
        private static void DrawBuilds(Rect body, SessionReportModel.Model m, int sub)
        {
            Fill(body, PANEL);
            if (m.BuildsMissing != null || m.Builds.Count == 0)
            {
                GUI.Label(body, "<color=#8FA3B8>" + (m.BuildsMissing ?? "") + "</color>", stCenter);
                return;
            }
            MeasureBuildPages(body, m);                 // cached unless the model or the body changed
            sub = Mathf.Clamp(sub, 0, buildPages - 1);
            int first = buildStarts[sub], end = sub + 1 < buildStarts.Count ? buildStarts[sub + 1] : m.Builds.Count;
            bool rolled = false;
            for (int i = first; i < end; i++) rolled |= m.Builds[i].HasRolled;
            GUI.Label(new Rect(body.x + 10f, body.y + 4f, body.width * 0.5f, 22f), m.BuildsRange(first, end - 1), stBody);
            GUI.Label(new Rect(body.x + body.width * 0.35f, body.y + 4f, body.width * 0.65f - 10f, 22f),
                rolled ? m.RolledKey + "     " + m.ChipKey : m.ChipKey, stSmallR);

            float y = body.y + PAGE_HEAD_H;
            for (int i = first; i < end; i++)
            {
                var b = m.Builds[i];
                var lay = blockLayouts[i];
                var r = new Rect(body.x + 8f, y, body.width - 16f, blockH[i] - BLOCK_GAP);
                Fill(r, ROW);
                float ix = r.x + BLOCK_PAD, iy = r.y + BLOCK_PAD, iw = r.width - 2f * BLOCK_PAD;
                GUI.Label(new Rect(ix, iy, iw - 140f, 22f), b.Header, stBody);
                if (b.Length.Length > 0)
                    GUI.Label(new Rect(ix + iw - 140f, iy, 140f, 22f), "<color=#8FA3B8>" + b.Length + "</color>", stSmallR);
                for (int c = 0; c < b.Cols.Count && c < lay.Cols.Count; c++)
                {
                    var col = b.Cols[c];
                    var cl = lay.Cols[c];
                    float cx = ix + cl.X, cy = iy + cl.Y, chipsY = cy + NAME_H;
                    GUI.Label(new Rect(cx, cy, cl.W, NAME_H), col.Name, stSmall);
                    if (col.Chips.Count == 0)
                        GUI.Label(new Rect(cx, chipsY, cl.W, 18f), "<color=#8FA3B8>" + col.Note + "</color>", stSmall);
                    for (int k = 0; k < col.Chips.Count && k < cl.ChipAt.Count; k++)
                    {
                        var at = cl.ChipAt[k];
                        DrawChip(new Rect(cx + at.X, chipsY + at.Y * (CHIP_H + CHIP_ROW_GAP), cl.ChipW[k], CHIP_H), col.Chips[k]);
                    }
                    if (cl.Stats.Length > 0)
                        GUI.Label(new Rect(cx, chipsY + cl.ChipsH + 4f, cl.W, cl.StatsH), cl.Stats, stTiny);
                }
                y += blockH[i];
            }
        }

        /// <summary>A chip: a faint fill and a bar in the card's rarity colour,
        /// the name (pre-coloured by the model) beside the bar; a rolled-out
        /// card is drawn dimmed.</summary>
        private static void DrawChip(Rect r, SessionReportModel.Chip chip)
        {
            Color t = chip.Tint;
            Fill(r, new Color(t.r, t.g, t.b, chip.Rolled ? 0.05f : 0.14f));
            Fill(new Rect(r.x, r.y, 3f, r.height), new Color(t.r, t.g, t.b, chip.Rolled ? 0.35f : 1f));
            GUI.Label(new Rect(r.x + 7f, r.y, r.width - 8f, r.height), chip.Label, stChip);
        }

        // ── primitives / styles ──────────────────────────────────────────────

        private static void Fill(Rect r, Color c)
            => GUI.DrawTexture(r, Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0f, c, 0f, 0f);

        private static void EnsureStyles()
        {
            if (stylesReady) return;
            stTitle = Mk(24, TextAnchor.MiddleLeft, FontStyle.Bold);
            stHeader = Mk(22, TextAnchor.MiddleLeft, FontStyle.Bold);
            stBody = Mk(16, TextAnchor.MiddleLeft, FontStyle.Bold);
            stSmall = Mk(14, TextAnchor.MiddleLeft, FontStyle.Bold);
            stSmallR = Mk(13, TextAnchor.MiddleRight, FontStyle.Bold);
            stTiny = Mk(12, TextAnchor.UpperLeft, FontStyle.Bold);
            // A card chip: one line, never wrapped (MiddleLeft does not wrap in Mk).
            stChip = Mk(13, TextAnchor.MiddleLeft, FontStyle.Bold);
            stCell = Mk(15, TextAnchor.MiddleLeft, FontStyle.Bold);
            stCellHead = Mk(13, TextAnchor.MiddleLeft, FontStyle.Bold);
            stCenter = Mk(18, TextAnchor.MiddleCenter, FontStyle.Bold);
            stBtn = new GUIStyle(GUI.skin.button) { fontSize = 15, fontStyle = FontStyle.Bold, richText = false };
            stylesReady = true;
        }

        private static GUIStyle Mk(int size, TextAnchor anchor, FontStyle fs)
        {
            var st = new GUIStyle(GUI.skin.label)
            {
                fontSize = size,
                alignment = anchor,
                fontStyle = fs,
                richText = true,
                wordWrap = anchor == TextAnchor.UpperLeft || anchor == TextAnchor.MiddleCenter,
                // ROUNDS' IMGUI skin has taller metrics than the point size suggests
                // (#72): let glyphs bleed past a tight rect instead of clipping.
                clipping = TextClipping.Overflow,
            };
            st.normal.textColor = Color.white;
            return st;
        }
    }
}
