using System;
using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Sept 6 batch (Group 4 item c) — the F5-owned INTERACTIVE session
    /// report: a four-page IMGUI pager (prev / next / Esc, no auto-advance, no
    /// stream-mode requirement) drawn full-screen over the open F5 overlay.
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
        private static string errorText;
        private static SessionReportModel.Model model;
        private static int page;

        private static bool stylesReady;
        private static GUIStyle stTitle, stHeader, stBody, stSmall, stSmallR, stBtn, stCell, stCellHead, stCenter, stTiny;
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
            try
            {
                ApiClient.FetchSessionReport(selector, key, (ok, body) => OnFetched(g, ok, body));
            }
            catch (Exception ex)
            {
                loading = false;
                errorText = "local: " + ex.Message;
                Plugin.Log.LogWarning($"[SESSION-REPORT] fetch: {ex.Message}");
            }
        }

        private static void OnFetched(int g, bool ok, string body)
        {
            if (g != gen || !Active) return;    // closed or re-targeted meanwhile
            loading = false;
            if (!ok)
            {
                errorText = body ?? "";
                return;
            }
            try
            {
                var env = SessionReportModel.Parse(body);
                if (env == null) { errorText = "parse"; return; }
                model = SessionReportModel.Build(env);
            }
            catch (Exception ex)
            {
                errorText = "model: " + ex.Message;
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
                    page = Mathf.Min(SessionReportModel.PAGE_COUNT - 1, page + 1); ev.Use(); break;
                case KeyCode.Home: page = 0; ev.Use(); break;
                case KeyCode.End: page = SessionReportModel.PAGE_COUNT - 1; ev.Use(); break;
                case KeyCode.Escape: Close(); ev.Use(); break;
            }
        }

        private static string ErrorMessage(string raw)
        {
            string e = raw ?? "";
            if (e.Contains("401") || e.Contains("session_required"))
                return I18n.Tr("Steam sign-in is required to view session reports");
            if (e.Contains("404") || e.Contains("not_found"))
                return I18n.Tr("This report is not available");
            if (e == "no-consent")
                return I18n.Tr("Data sharing is disabled in your settings");
            string tail = SessionReportModel.Safe(e.Length > 90 ? e.Substring(0, 90) : e);
            return I18n.Tr("Could not load this report") + (tail == "?" ? "" : "\n<size=13><color=#888>" + tail + "</color></size>");
        }

        private static void DrawFooter(Rect r)
        {
            Fill(r, PANEL);
            float bw = 110f, bh = 30f, y = r.y + (r.height - bh) / 2f;
            bool wasEnabled = GUI.enabled;
            GUI.enabled = model != null && page > 0;
            if (GUI.Button(new Rect(r.x + 8f, y, bw, bh), I18n.Tr("< Prev"), stBtn)) page = Mathf.Max(0, page - 1);
            GUI.enabled = model != null && page < SessionReportModel.PAGE_COUNT - 1;
            if (GUI.Button(new Rect(r.x + 16f + bw, y, bw, bh), I18n.Tr("Next >"), stBtn))
                page = Mathf.Min(SessionReportModel.PAGE_COUNT - 1, page + 1);
            GUI.enabled = wasEnabled;
            string pageLabel = model != null
                ? I18n.TrF("Page {0}/{1}", page + 1, SessionReportModel.PAGE_COUNT) + "  -  " + model.PageTitles[page]
                : "";
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
                default: DrawBuilds(body, m); break;
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

        // ── builds page ──────────────────────────────────────────────────────

        private static void DrawBuilds(Rect body, SessionReportModel.Model m)
        {
            Fill(body, PANEL);
            if (m.BuildsMissing != null)
            {
                GUI.Label(body, "<color=#8FA3B8>" + m.BuildsMissing + "</color>", stCenter);
                return;
            }
            int cols = Mathf.Clamp(m.Players.Count, 1, 4);
            float colW = (body.width - 16f) / cols;
            float y = body.y + 8f;
            int shown = 0;
            for (int i = 0; i < m.Builds.Count; i += cols)
            {
                float rowH = 0f;
                for (int c = 0; c < cols && i + c < m.Builds.Count; c++)
                    rowH = Mathf.Max(rowH, BlockHeight(m.Builds[i + c]));
                if (y + rowH > body.yMax - 8f) break;
                for (int c = 0; c < cols && i + c < m.Builds.Count; c++)
                {
                    var b = m.Builds[i + c];
                    var r = new Rect(body.x + 8f + c * colW, y, colW - 8f, rowH - 6f);
                    Fill(r, ROW);
                    GUI.Label(new Rect(r.x + 6f, r.y + 2f, r.width - 12f, 22f), b.Title, stBody);
                    GUI.Label(new Rect(r.x + 6f, r.y + 24f, r.width - 12f, 40f), b.Cards, stSmall);
                    if (b.Stats.Length > 0)
                        GUI.Label(new Rect(r.x + 6f, r.y + 66f, r.width - 12f, r.height - 70f), b.Stats, stTiny);
                    shown++;
                }
                y += rowH;
            }
            if (shown < m.Builds.Count)
                GUI.Label(new Rect(body.x + 8f, body.yMax - 24f, body.width - 16f, 22f),
                    "<color=#8FA3B8>" + I18n.TrF("showing {0} of {1}", shown, m.Builds.Count) + "</color>", stSmall);
        }

        private static float BlockHeight(SessionReportModel.BuildBlock b)
        {
            int lines = 0;
            if (b.Stats.Length > 0)
            {
                lines = 1;
                for (int i = 0; i < b.Stats.Length; i++) if (b.Stats[i] == '\n') lines++;
            }
            return 74f + lines * 15f;
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
