using System;
using System.Reflection;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Visual companions for the Info tab (Sid, Aug 30: "split up all
    /// the walls of text with visualizations wherever possible").
    ///
    /// Every visual is a PURE uGUI panel — solid-color Images positioned
    /// absolutely inside a fixed-height panel (the DrawBar/MakeGraphLabel
    /// technique from the Compare tab) — so panels scroll with the article,
    /// cost no textures and no mod-size, and obey learning #63 (fixed prefH
    /// inside the scroll content; flex would collapse). Text labels route
    /// through I18n.Tr in THIS file so the extractor harvests them (#295a —
    /// this file must stay listed in tools/i18n_extract.py FILES). Chart
    /// number labels stay raw (numbers do not translate).
    ///
    /// FACT DISCIPLINE (#351): every gameplay number drawn here restates a
    /// claim already made (and fact-checked) by the article it sits in, or a
    /// named server constant — sources are cited per builder, and rules with
    /// server-side adjustments (truncation, bonuses, taxes) are stated
    /// QUALITATIVELY rather than as formulas that would misstate them (two
    /// review rounds each caught a numeric claim here; do not add numbers
    /// without running the server code they restate).
    ///
    /// Builders return null on any failure, and Build destroys a partially
    /// constructed panel before returning (the Panel helper registers the
    /// in-flight root) — the caller renders the article without the visual,
    /// never with an orphaned half-drawn one.</summary>
    internal static class InfoViz
    {
        private static readonly Color PANEL_BG = new Color(0.085f, 0.10f, 0.14f, 0.92f);
        private static readonly Color HDR_GOLD = new Color(1f, 0.85f, 0.30f);
        private static readonly Color TXT_MAIN = new Color(0.84f, 0.85f, 0.90f);
        private static readonly Color TXT_DIM = new Color(0.55f, 0.58f, 0.66f);
        private static readonly Color AXIS_COL = new Color(0.45f, 0.48f, 0.56f, 0.55f);
        // Keycap fills: gold = mod function, blue = base game, purple = both.
        private static readonly Color KEY_MOD = new Color(0.52f, 0.42f, 0.14f, 0.95f);
        private static readonly Color KEY_GAME = new Color(0.16f, 0.30f, 0.50f, 0.95f);
        private static readonly Color KEY_BOTH = new Color(0.40f, 0.24f, 0.52f, 0.95f);
        private static readonly Color KEY_NONE = new Color(0.15f, 0.17f, 0.23f, 0.9f);

        // The panel a builder is currently constructing. Build() destroys it
        // on a mid-builder throw — without this, a reflection failure after
        // Panel() left an ACTIVE, untracked half-drawn panel that article
        // switches could never clean up (r2 finding).
        private static GameObject _inFlight;

        internal static GameObject Build(string key, Transform parent)
        {
            _inFlight = null;
            try
            {
                GameObject made = null;
                switch (key)
                {
                    case "keyboard": made = BuildKeyboard(parent); break;
                    case "dot-timeline": made = BuildDotTimeline(parent); break;
                    case "block-window": made = BuildBlockWindow(parent); break;
                    case "rank-ladder": made = BuildRankLadder(parent); break;
                    case "glicko-rd": made = BuildGlickoRd(parent); break;
                    case "xp-curve": made = BuildXpCurve(parent); break;
                    case "gold-sources": made = BuildGoldSources(parent); break;
                    case "series-format": made = BuildSeriesFormat(parent); break;
                    case "ffa-scoring": made = BuildFfaScoring(parent); break;
                    case "grow-curve": made = BuildGrowCurve(parent); break;
                    case "netcode-map": made = BuildNetcodeMap(parent); break;
                    case "bet-window": made = BuildBetWindow(parent); break;
                    case "bracket-flow": made = BuildBracketFlow(parent); break;
                    case "forfeit-clock": made = BuildForfeitClock(parent); break;
                    case "when-counts": made = BuildWhenCounts(parent); break;
                    case "refresh-flow": made = BuildRefreshFlow(parent); break;
                    case "movement-window": made = BuildMovementWindow(parent); break;
                    case "team-format": made = BuildTeamFormat(parent); break;
                    default:
                        Plugin.Log.LogWarning("[INFO-VIZ] unknown viz key '" + key + "'");
                        break;
                }
                // A builder that deliberately returned null (e.g. xp-curve's
                // zero-total bail) still owns a created panel — destroy it.
                if (made == null && _inFlight != null)
                { try { UnityEngine.Object.Destroy(_inFlight); } catch { } }
                _inFlight = null;
                return made;
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning("[INFO-VIZ] build '" + key + "' failed: " + ex.Message);
                if (_inFlight != null)
                { try { UnityEngine.Object.Destroy(_inFlight); } catch { } _inFlight = null; }
                return null;
            }
        }

        // ── positioning primitives (bottom-left origin inside the panel) ──

        private static GameObject Panel(Transform parent, string name, float h)
        {
            var p = UIFactory.CreatePanel(name, parent, PANEL_BG);
            UIFactory.AddLE(p, prefH: h, minH: h, flexH: 0);
            _inFlight = p;   // Build() destroys this on a mid-builder failure
            return p;
        }

        private static GameObject Box(GameObject panel, float x, float y, float w, float h, Color c)
        {
            var go = new GameObject("bx");
            go.transform.SetParent(panel.transform, false);
            var rt = go.AddComponent<RectTransform>();
            rt.anchorMin = Vector2.zero; rt.anchorMax = Vector2.zero;
            rt.pivot = Vector2.zero;
            rt.anchoredPosition = new Vector2(x, y);
            rt.sizeDelta = new Vector2(w, h);
            go.AddComponent(UIFactory.tImage);
            UIFactory.SetImageColor(go, c);
            return go;
        }

        private static void Line(GameObject panel, Vector2 a, Vector2 b, Color c, float thick)
        {
            var go = Box(panel, 0f, 0f, 0f, 0f, c);
            var rt = go.GetComponent<RectTransform>();
            rt.pivot = new Vector2(0f, 0.5f);
            rt.anchoredPosition = a;
            float len = Vector2.Distance(a, b);
            rt.sizeDelta = new Vector2(len, thick);
            rt.localRotation = Quaternion.Euler(0f, 0f, Mathf.Atan2(b.y - a.y, b.x - a.x) * Mathf.Rad2Deg);
        }

        /// <summary>Free-positioned label. Text arrives ALREADY Tr'd (or raw
        /// numeric) — SetTextRaw skips the second lookup while keeping glyph
        /// registration + the bold wrap (#48/#110 pattern).</summary>
        private static object Lbl(GameObject panel, string text, float size, Color c,
            float x, float y, float w, float h, int align = -1)
        {
            var t = UIFactory.CreateText("lb", panel.transform, "", size, c,
                align < 0 ? UIFactory.AlignMidLeft : align, sizeDelta: new Vector2(w, h));
            var go = (t as Component)?.gameObject;
            if (go == null) return t;
            if (UIFactory.tLE != null)
            {
                var le = go.GetComponent(UIFactory.tLE);
                if (le != null) UnityEngine.Object.Destroy(le as UnityEngine.Object);
            }
            var rt = go.GetComponent<RectTransform>();
            rt.anchorMin = Vector2.zero; rt.anchorMax = Vector2.zero;
            rt.pivot = Vector2.zero;
            rt.anchoredPosition = new Vector2(x, y);
            rt.sizeDelta = new Vector2(w, h);
            UIFactory.SetTextRaw(t, text);
            UIFactory.FitOneLine(t);
            return t;
        }

        private static void Header(GameObject panel, float panelH, string text)
        {
            var t = Lbl(panel, text, 15f, HDR_GOLD, 14f, panelH - 32f, 1100f, 22f);
            UIFactory.SetBold(t, true);
        }

        private static void Arrow(GameObject panel, Vector2 a, Vector2 b, Color c, float thick = 2f)
        {
            Line(panel, a, b, c, thick);
            Vector2 d = (b - a).normalized;
            Vector2 n = new Vector2(-d.y, d.x);
            Line(panel, b, b - d * 10f + n * 5f, c, thick);
            Line(panel, b, b - d * 10f - n * 5f, c, thick);
        }

        private static void Diamond(GameObject panel, float x, float y, float w, float h, Color c)
        {
            var left = new Vector2(x, y + h * 0.5f);
            var top = new Vector2(x + w * 0.5f, y + h);
            var right = new Vector2(x + w, y + h * 0.5f);
            var bottom = new Vector2(x + w * 0.5f, y);
            Line(panel, left, top, c, 2f);
            Line(panel, top, right, c, 2f);
            Line(panel, right, bottom, c, 2f);
            Line(panel, bottom, left, c, 2f);
        }

        // ── keyboard guide ────────────────────────────────────────────────
        // Key inventory verified against the code this release: F5
        // Plugin.TickF5, T/M CompetitiveUI chat block, Q DrawQuickChat wheel,
        // E DrawDanceWheel (Aug 31 — Y and the digit picks are RETIRED with
        // the old list panel), Tab TabStatsOverlay,
        // Shift Plugin map-skin cycle; vanilla
        // bindings from decompiled PlayerActions.CreateWithKeyboardBindings
        // (Fire=LMB, Block=RMB, Jump=Space, WASD, Start=Enter) and
        // PlayerAssigner.LateUpdate (Space ready-up, B practice bot).

        private sealed class KeyDef
        {
            public string Cap; public float W; public Color Fill;
            public KeyDef(string cap, float w, Color fill) { Cap = cap; W = w; Fill = fill; }
        }

        private static void KeyRow(GameObject p, float x, float y, KeyDef[] keys)
        {
            foreach (var k in keys)
            {
                Box(p, x, y, k.W, 32f, k.Fill);
                var t = Lbl(p, k.Cap, 12f, Color.white, x, y + 3f, k.W, 26f, UIFactory.AlignMidCenter);
                UIFactory.SetBold(t, true);
                x += k.W + 4f;
            }
        }

        private static GameObject BuildKeyboard(Transform parent)
        {
            const float H = 500f;
            var p = Panel(parent, "VizKeys", H);
            Header(p, H, I18n.Tr("KEYS THAT DO SOMETHING"));
            float kw = 40f;
            float top = H - 76f;      // y of the top key row
            float pitch = 36f;
            // Row 0: ESC + function keys (F5 is the mod menu).
            KeyRow(p, 14f, top, new[]
            {
                new KeyDef("ESC", 52f, KEY_BOTH), new KeyDef("F1", kw, KEY_NONE), new KeyDef("F2", kw, KEY_NONE),
                new KeyDef("F3", kw, KEY_NONE), new KeyDef("F4", kw, KEY_NONE), new KeyDef("F5", kw, KEY_MOD),
                new KeyDef("F6", kw, KEY_NONE), new KeyDef("F7", kw, KEY_NONE), new KeyDef("F8", kw, KEY_NONE),
            });
            // Row 1: backquote + digits (plain since the Aug 31 wheel rework —
            // the old 1-9/0 quick-chat picks are retired).
            KeyRow(p, 14f, top - pitch, new[]
            {
                new KeyDef(I18n.Tr("`"), kw, KEY_NONE),
                new KeyDef("1", kw, KEY_NONE), new KeyDef("2", kw, KEY_NONE), new KeyDef("3", kw, KEY_NONE),
                new KeyDef("4", kw, KEY_NONE), new KeyDef("5", kw, KEY_NONE), new KeyDef("6", kw, KEY_NONE),
                new KeyDef("7", kw, KEY_NONE), new KeyDef("8", kw, KEY_NONE), new KeyDef("9", kw, KEY_NONE),
                new KeyDef("0", kw, KEY_NONE),
            });
            // Row 2: TAB + top letters.
            KeyRow(p, 14f, top - 2f * pitch, new[]
            {
                new KeyDef(I18n.Tr("TAB"), 62f, KEY_MOD),
                new KeyDef("Q", kw, KEY_MOD), new KeyDef("W", kw, KEY_GAME),
                new KeyDef("E", kw, KEY_MOD), new KeyDef("R", kw, KEY_NONE), new KeyDef("T", kw, KEY_MOD),
                new KeyDef("Y", kw, KEY_NONE), new KeyDef("U", kw, KEY_NONE), new KeyDef("I", kw, KEY_NONE),
                new KeyDef("O", kw, KEY_NONE), new KeyDef("P", kw, KEY_NONE),
            });
            // Row 3: CAPS + home row + ENTER.
            KeyRow(p, 14f, top - 3f * pitch, new[]
            {
                new KeyDef(I18n.Tr("CAPS"), 73f, KEY_NONE),
                new KeyDef("A", kw, KEY_GAME), new KeyDef("S", kw, KEY_GAME), new KeyDef("D", kw, KEY_GAME),
                new KeyDef("F", kw, KEY_NONE), new KeyDef("G", kw, KEY_NONE), new KeyDef("H", kw, KEY_NONE),
                new KeyDef("J", kw, KEY_NONE), new KeyDef("K", kw, KEY_NONE), new KeyDef("L", kw, KEY_NONE),
                new KeyDef("ENTER", 76f, KEY_GAME),
            });
            // Row 4: SHIFT + bottom letters.
            KeyRow(p, 14f, top - 4f * pitch, new[]
            {
                new KeyDef(I18n.Tr("SHIFT"), 95f, KEY_MOD),
                new KeyDef("Z", kw, KEY_NONE), new KeyDef("X", kw, KEY_NONE),
                new KeyDef("C", kw, KEY_NONE), new KeyDef("V", kw, KEY_NONE), new KeyDef("B", kw, KEY_GAME),
                new KeyDef("N", kw, KEY_NONE), new KeyDef("M", kw, KEY_MOD),
            });
            // ANSI stagger, measured from "1": Q +22, A +33, Z +55 pixels.
            // The home row is widest and ends at x=563, leaving 77px before
            // the mouse block at x=640. Space x=137 centers it under A-L.
            KeyRow(p, 137f, top - 5f * pitch, new[] { new KeyDef(I18n.Tr("SPACE"), 300f, KEY_GAME) });
            // Mouse, to the right of the board.
            float mx = 640f, my = top - 3f * pitch;
            Box(p, mx, my, 46f, 66f, KEY_GAME);
            Box(p, mx + 50f, my, 46f, 66f, KEY_GAME);
            Lbl(p, I18n.Tr("LMB"), 12f, Color.white, mx, my + 20f, 46f, 22f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("RMB"), 12f, Color.white, mx + 50f, my + 20f, 46f, 22f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("Mouse"), 12f, TXT_DIM, mx, my - 24f, 96f, 20f, UIFactory.AlignMidCenter);
            // Color legend chips.
            float cy = top + 8f;
            Box(p, 640f, cy, 16f, 16f, KEY_MOD); Lbl(p, I18n.Tr("mod"), 12f, TXT_MAIN, 662f, cy - 2f, 90f, 20f);
            Box(p, 760f, cy, 16f, 16f, KEY_GAME); Lbl(p, I18n.Tr("base game"), 12f, TXT_MAIN, 782f, cy - 2f, 130f, 20f);
            Box(p, 920f, cy, 16f, 16f, KEY_BOTH); Lbl(p, I18n.Tr("both"), 12f, TXT_MAIN, 942f, cy - 2f, 90f, 20f);
            // Function legend, two columns.
            string[] left =
            {
                I18n.Tr("F5 - open / close the competitive menu"),
                I18n.Tr("T - open in-game chat"),
                I18n.Tr("Q (hold) - quick-chat wheel, release to send"),
                I18n.Tr("E (hold, between rounds) - dance emote wheel"),
                I18n.Tr("M - cycle the chat overlay mode"),
                I18n.Tr("TAB (hold, in a match) - live scoreboard"),
                I18n.Tr("SHIFT - cycle your equipped map skins"),
            };
            string[] right =
            {
                I18n.Tr("WASD - move.  SPACE - jump"),
                I18n.Tr("LMB - shoot.  RMB - block"),
                I18n.Tr("SPACE (hold, in a lobby) - ready up / join"),
                I18n.Tr("ENTER - room code box / vanilla chat"),
                I18n.Tr("B (in a lobby) - add a practice bot"),
                I18n.Tr("ESC - closes this menu first, then the game menu"),
            };
            float ly = top - 5f * pitch - 40f;
            for (int i = 0; i < left.Length; i++)
                Lbl(p, left[i], 13f, TXT_MAIN, 14f, ly - i * 24f, 560f, 20f);
            for (int i = 0; i < right.Length; i++)
                Lbl(p, right[i], 13f, TXT_MAIN, 590f, ly - i * 24f, 570f, 20f);
            return p;
        }

        // ── DoT tick timeline ─────────────────────────────────────────────
        // Numbers restate the Poison article's asset-verified facts (#424):
        // Poison = 10 ticks over 3.0s (one per 0.3s, first on impact), Toxic
        // Cloud = ~17 ticks over 5.0s, block window = 0.3s.

        private static GameObject BuildDotTimeline(Transform parent)
        {
            const float H = 200f;
            var p = Panel(parent, "VizDot", H);
            Header(p, H, I18n.Tr("DOT TICKS VS THE BLOCK WINDOW"));
            float x0 = 150f, pxPerSec = 196f;
            float yP = H - 92f, yT = H - 132f;
            // Axis + second marks.
            Line(p, new Vector2(x0, 44f), new Vector2(x0 + 5f * pxPerSec, 44f), AXIS_COL, 1.5f);
            for (int s = 0; s <= 5; s++)
            {
                float x = x0 + s * pxPerSec;
                Line(p, new Vector2(x, 40f), new Vector2(x, 50f), AXIS_COL, 1.5f);
                Lbl(p, s + "s", 12f, TXT_DIM, x - 12f, 24f, 40f, 16f);
            }
            // Block window band: 0.3s wide, drawn over both rows at t=0.9s.
            float bw = 0.3f * pxPerSec;
            Box(p, x0 + 0.9f * pxPerSec, yT - 8f, bw, (yP + 22f) - (yT - 8f), new Color(1f, 0.85f, 0.30f, 0.22f));
            Lbl(p, I18n.Tr("one 0.3s block window"), 12f, HDR_GOLD, x0 + 0.9f * pxPerSec - 40f, yP + 26f, 260f, 18f);
            // Poison: 10 ticks, 0.3s apart, first on impact.
            Lbl(p, I18n.Tr("Poison"), 13f, new Color(0.55f, 0.9f, 0.45f), 14f, yP, 120f, 20f);
            for (int i = 0; i < 10; i++)
                Box(p, x0 + i * 0.3f * pxPerSec - 2f, yP, 4f, 16f, new Color(0.45f, 0.85f, 0.35f, 0.95f));
            // Toxic Cloud: 17 ticks across 5s.
            Lbl(p, I18n.Tr("Toxic Cloud"), 13f, new Color(0.72f, 0.55f, 0.95f), 14f, yT, 130f, 20f);
            for (int i = 0; i < 17; i++)
                Box(p, x0 + i * 0.3f * pxPerSec - 2f, yT, 4f, 16f, new Color(0.65f, 0.45f, 0.9f, 0.95f));
            Lbl(p, I18n.Tr("Every mark is one tick of damage. A well-timed block erases the 1-2 ticks inside its window."),
                13f, TXT_DIM, 150f, 0f, 1000f, 20f);
            return p;
        }

        // ── block window ─────────────────────────────────────────────────
        private static GameObject BuildBlockWindow(Transform parent)
        {
            const float H = 130f;
            var p = Panel(parent, "VizBlock", H);
            Header(p, H, I18n.Tr("THE 0.3 SECOND WINDOW"));
            float x0 = 150f, w1s = 700f, y = H - 84f;
            Box(p, x0, y, 0.3f * w1s, 26f, new Color(0.30f, 0.75f, 0.95f, 0.85f));
            Box(p, x0 + 0.3f * w1s, y, 0.7f * w1s, 26f, new Color(0.2f, 0.23f, 0.3f, 0.85f));
            Lbl(p, I18n.Tr("absorbs everything"), 12f, Color.white, x0 + 6f, y + 4f, 200f, 18f);
            Lbl(p, I18n.Tr("window over - cooldown keeps counting from the press"), 12f, TXT_DIM,
                x0 + 0.3f * w1s + 8f, y + 4f, 470f, 18f);
            Lbl(p, I18n.Tr("press"), 12f, TXT_DIM, x0 - 4f, y - 24f, 80f, 20f);
            Lbl(p, "0.3s", 12f, HDR_GOLD, x0 + 0.3f * w1s - 16f, y - 24f, 60f, 20f);
            Line(p, new Vector2(x0, y - 4f), new Vector2(x0, y + 34f), AXIS_COL, 1.5f);
            Line(p, new Vector2(x0 + 0.3f * w1s, y - 4f), new Vector2(x0 + 0.3f * w1s, y + 34f), HDR_GOLD, 1.5f);
            return p;
        }

        // ── rank ladder ──────────────────────────────────────────────────
        // Floors + reward multipliers mirror the server TIER_MULTIPLIERS
        // table (main.py) and the client fallback palette; the Rewards and
        // Rating articles state the same numbers.

        private static GameObject BuildRankLadder(Transform parent)
        {
            const float H = 160f;
            var p = Panel(parent, "VizRanks", H);
            Header(p, H, I18n.Tr("RANK TIERS AND REWARD MULTIPLIERS"));
            float[] floors = { 1000f, 1500f, 1675f, 1980f, 2330f, 2700f };  // 1000/2700 are draw bounds
            string[] names =
            {
                I18n.Tr("Beginner"), I18n.Tr("Intermediate"), I18n.Tr("Advanced"),
                I18n.Tr("Master"), I18n.Tr("Grand Master"),
            };
            string[] mults = { "x1.0", "x1.5", "x2.0", "x2.5", "x3.0" };
            Color[] cols =
            {
                new Color(0.733f, 0.475f, 0.933f), new Color(0.992f, 0.780f, 0.467f),
                new Color(0.467f, 0.639f, 0.988f), new Color(0.333f, 0.847f, 0.275f),
                new Color(0.957f, 0.529f, 0.663f),
            };
            float x0 = 20f, wAll = 1120f, span = floors[5] - floors[0];
            float y = H - 96f;
            for (int i = 0; i < 5; i++)
            {
                float x = x0 + (floors[i] - floors[0]) / span * wAll;
                float w = (floors[i + 1] - floors[i]) / span * wAll;
                var c = cols[i]; c.a = 0.85f;
                Box(p, x, y, w - 2f, 34f, c);
                var nm = Lbl(p, names[i], 12f, Color.black, x + 4f, y + 8f, w - 8f, 18f);
                UIFactory.SetBold(nm, true);
                Lbl(p, mults[i], 13f, HDR_GOLD, x + 2f, y + 38f, 60f, 20f);
                if (i > 0) Lbl(p, ((int)floors[i]).ToString(), 12f, TXT_DIM, x - 18f, y - 24f, 60f, 20f);
            }
            Lbl(p, I18n.Tr("Everyone starts at 1500. Higher tiers multiply series gold; each band splits into sub-tiers V to I."),
                13f, TXT_DIM, 20f, 6f, 1100f, 20f);
            return p;
        }

        // ── rating confidence (RD) ───────────────────────────────────────
        private static GameObject BuildGlickoRd(Transform parent)
        {
            const float H = 150f;
            var p = Panel(parent, "VizRd", H);
            Header(p, H, I18n.Tr("HOW SURE THE SYSTEM IS"));
            float cx = 620f, wPerPt = 0.9f;   // center = your rating
            string[] rows =
            {
                I18n.Tr("brand new (+/- 350)"),
                I18n.Tr("after a handful of series"),
                I18n.Tr("regular (converged)"),
            };
            float[] rd = { 350f, 160f, 90f };
            for (int i = 0; i < 3; i++)
            {
                float y = H - 66f - i * 28f;
                Lbl(p, rows[i], 13f, TXT_MAIN, 20f, y, 280f, 20f);
                var c = new Color(0.50f, 0.91f, 0.50f, 0.28f + 0.22f * i);
                Box(p, cx - rd[i] * wPerPt, y, rd[i] * 2f * wPerPt, 18f, c);
            }
            Line(p, new Vector2(cx, 30f), new Vector2(cx, H - 44f), new Color(1f, 1f, 1f, 0.7f), 2f);   // stops above the caption (r2 nit)
            Lbl(p, I18n.Tr("The white line is your rating; the band is the rating deviation - it shrinks as you play, and your rating moves less once it is narrow."),
                13f, TXT_DIM, 20f, 4f, 1120f, 20f);
            return p;
        }

        // ── XP curve ─────────────────────────────────────────────────────
        // Mirrors NativeUI.TotalXpForLevel (100 * n^1.5 per level, cumulative,
        // cap 100) and the level_reward_for gold rule (100g every 5 levels
        // through 50, 500g every 5 from 55).

        private static GameObject BuildXpCurve(Transform parent)
        {
            const float H = 200f;
            var p = Panel(parent, "VizXp", H);
            Header(p, H, I18n.Tr("THE ROAD TO LEVEL 100"));
            float x0 = 60f, w = 1040f, y0 = 42f, hMax = 108f;
            // NativeUI.TotalXpForLevel is the client's server-mirror of the
            // curve (100 * n^1.5 cumulative) — one source, no third copy.
            double max = NativeUI.TotalXpForLevel(100);
            if (max <= 0) return null;
            Line(p, new Vector2(x0, y0), new Vector2(x0 + w, y0), AXIS_COL, 1.5f);
            Vector2 prev = new Vector2(x0, y0);
            for (int lv = 5; lv <= 100; lv += 5)
            {
                double total = NativeUI.TotalXpForLevel(lv);
                var pt = new Vector2(x0 + w * lv / 100f, y0 + (float)(total / max) * hMax);
                Line(p, prev, pt, new Color(0.3f, 0.7f, 1f, 0.9f), 2f);
                // Level-ding markers: gold every 5 levels, brighter past 50
                // where the ding pays 500g instead of 100g.
                Box(p, pt.x - 3f, pt.y - 3f, 6f, 6f, lv > 50 ? new Color(1f, 0.85f, 0.2f) : new Color(0.8f, 0.65f, 0.25f));
                prev = pt;
            }
            foreach (int lv in new[] { 25, 50, 75, 100 })
                Lbl(p, lv.ToString(), 12f, TXT_DIM, x0 + w * lv / 100f - 12f, y0 - 20f, 40f, 16f);
            Lbl(p, I18n.Tr("level"), 12f, TXT_DIM, 4f, y0 - 20f, 52f, 16f);   // left of the axis — the right edge collided with the "100" mark (r2 nit)
            Lbl(p, I18n.Tr("Each level costs more XP than the last (level^1.5). Every gold dot is a level-up: 100g each through 50, 500g after."),
                13f, TXT_DIM, 20f, 0f, 1120f, 20f);
            return p;
        }

        // ── gold sources ─────────────────────────────────────────────────
        // A LEGEND, deliberately not a chart (r1 finding 4: the first cut
        // drew bars from invented magnitudes — quantities across these
        // sources are not comparable). Every note restates a verified server
        // rule: SERIES_GOLD_BASE 5 x2 winner x tier; ACHIEVEMENT_GOLD 100
        // with 300/500/1000 overrides; the FFA battles-x-players pool
        // (v1.36.0 meter, ~45% XP / 55% gold); level_reward_for; bet payout.

        private static GameObject BuildGoldSources(Transform parent)
        {
            const float H = 220f;
            var p = Panel(parent, "VizGold", H);
            Header(p, H, I18n.Tr("WHERE GOLD COMES FROM"));
            string[] names =
            {
                I18n.Tr("Ranked series"),
                I18n.Tr("Achievements"),
                I18n.Tr("FFA games"),
                I18n.Tr("Level-ups"),
                I18n.Tr("Betting"),
            };
            string[] notes =
            {
                // Nonnumeric where the server rule has adjustments a formula
                // line would misstate (r2 finding: int(5*mult)*2 truncates,
                // podium/sweep bonuses stack, short-odds bets are taxed).
                I18n.Tr("the base award scales with your opponent's tier; podium and sweep bonuses can add more"),
                I18n.Tr("100g each - the hardest pay 300g, 500g or 1000g"),
                I18n.Tr("a pot scaled by lobby size, battles and opponent tier, split by placement"),
                I18n.Tr("every 5 levels: 100g, then 500g past level 50"),
                I18n.Tr("your stake plus profit by the odds - short-odds wins are lightly taxed"),
            };
            var chip = new Color(1f, 0.78f, 0.25f, 0.85f);
            for (int i = 0; i < names.Length; i++)
            {
                float y = H - 62f - i * 30f;
                Box(p, 20f, y + 5f, 10f, 10f, chip);
                var nm = Lbl(p, names[i], 13f, TXT_MAIN, 38f, y, 180f, 20f);
                UIFactory.SetBold(nm, true);
                Lbl(p, notes[i], 13f, TXT_DIM, 230f, y, 930f, 20f);
            }
            return p;
        }

        // ── series format ────────────────────────────────────────────────
        private static GameObject BuildSeriesFormat(Transform parent)
        {
            const float H = 150f;
            var p = Panel(parent, "VizBo3", H);
            Header(p, H, I18n.Tr("A SERIES IS FIRST TO 2"));
            float y = H - 92f;
            var on = new Color(0.20f, 0.42f, 0.65f, 0.95f);
            var dim = new Color(0.18f, 0.20f, 0.27f, 0.95f);
            string g = I18n.Tr("Game");
            for (int i = 0; i < 3; i++)
            {
                float x = 40f + i * 200f;
                Box(p, x, y, 160f, 40f, i < 2 ? on : dim);
                var t = Lbl(p, g + " " + (i + 1), 13f, Color.white, x, y + 10f, 160f, 20f, UIFactory.AlignMidCenter);
                UIFactory.SetBold(t, true);
                if (i < 2) Lbl(p, ">", 16f, TXT_DIM, x + 168f, y + 8f, 24f, 24f);
            }
            Lbl(p, I18n.Tr("only if it is 1-1"), 12f, TXT_DIM, 440f, y - 24f, 220f, 20f);
            // Full-width caption line (r1 finding 13 + screenshot: the old
            // right-column box clipped mid-word at the pane edge).
            Lbl(p, I18n.Tr("Ratings, gold and the series result all settle when someone takes their 2nd game."),
                13f, TXT_DIM, 40f, 6f, 1120f, 20f);
            return p;
        }

        // ── FFA placement payout ─────────────────────────────────────────
        // QUALITATIVE share illustration only — deliberately no gold numbers
        // (r1 finding 4: the old fixed 50g->10g scale is retired; the live
        // pool is the v1.36.0 battles-x-players meter with a placement
        // shape, an opponent-tier factor and a ~45% XP / 55% gold split, so
        // any absolute figure here would be wrong by construction).

        private static GameObject BuildFfaScoring(Transform parent)
        {
            const float H = 210f;
            var p = Panel(parent, "VizFfa", H);
            Header(p, H, I18n.Tr("PLACEMENT PAYS"));
            int n = 8;
            float x0 = 60f, bw = 70f, gap = 34f, y0 = 68f;
            for (int i = 0; i < n; i++)
            {
                float share = Mathf.Lerp(1f, 0.2f, i / (float)(n - 1));
                float h = 90f * share;
                float x = x0 + i * (bw + gap);
                Box(p, x, y0, bw, h, new Color(1f, 0.78f, 0.25f, 0.55f + 0.35f * (1f - i / (float)(n - 1))));
                Lbl(p, Ordinal(i + 1), 12f, TXT_MAIN, x, y0 - 24f, bw, 20f, UIFactory.AlignMidCenter);
            }
            Lbl(p, I18n.Tr("Higher placement takes a bigger share of the pot; the pot itself scales with lobby size, battles played and opponent tier."),
                13f, TXT_DIM, 20f, 26f, 1120f, 20f);
            Lbl(p, I18n.Tr("Just under half of a payout arrives as XP, the rest as gold. Rating moves from pairwise comparisons against the finishers nearest you."),
                13f, TXT_DIM, 20f, 4f, 1120f, 20f);
            return p;
        }

        // -- Grow frame-rate curve ------------------------------------------
        // The three bars restate the article's unstacked full-flight table.
        // The competitive reference is 240 FPS; the article does not state
        // the internal 0.85 constant, so it is deliberately not drawn.

        private static GameObject BuildGrowCurve(Transform parent)
        {
            const float H = 220f;
            var p = Panel(parent, "VizGrow", H);
            Header(p, H, I18n.Tr("VANILLA GROW: FRAME RATE CHANGES DAMAGE"));
            string[] fps = { I18n.Tr("400 FPS"), I18n.Tr("60 FPS"), I18n.Tr("30 FPS") };
            string[] mult = { I18n.Tr("x1.07"), I18n.Tr("x1.53"), I18n.Tr("x2.31") };
            float[] values = { 1.07f, 1.53f, 2.31f };
            Color[] colors =
            {
                new Color(0.30f, 0.68f, 0.95f, 0.85f),
                new Color(0.82f, 0.58f, 0.22f, 0.90f),
                new Color(0.92f, 0.30f, 0.25f, 0.90f),
            };
            for (int i = 0; i < fps.Length; i++)
            {
                float y = H - 82f - i * 40f;
                Lbl(p, fps[i], 13f, TXT_MAIN, 24f, y, 120f, 22f);
                float w = values[i] * 360f;
                Box(p, 150f, y + 1f, w, 22f, colors[i]);
                Lbl(p, mult[i], 13f, Color.white, 160f + w, y, 80f, 22f);
            }
            Box(p, 880f, H - 64f, 250f, 28f, new Color(0.25f, 0.62f, 0.38f, 0.82f));
            Lbl(p, I18n.Tr("competitive clock: 240 FPS"), 12f, Color.white,
                880f, H - 61f, 250f, 22f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("Un-stacked, full flight. The mod pins every eligible Grow bullet to the same 240 FPS growth clock."),
                13f, TXT_DIM, 24f, 6f, 1110f, 20f);
            return p;
        }

        // -- Photon topology -------------------------------------------------

        private static GameObject BuildNetcodeMap(Transform parent)
        {
            const float H = 230f;
            var p = Panel(parent, "VizNetcode", H);
            Header(p, H, I18n.Tr("EVERYTHING TRAVELS THROUGH PHOTON"));
            var seat = new Color(0.16f, 0.30f, 0.50f, 0.95f);
            var relay = new Color(0.40f, 0.24f, 0.52f, 0.95f);
            Box(p, 30f, 72f, 240f, 102f, seat);
            Box(p, 470f, 82f, 240f, 82f, relay);
            Box(p, 900f, 72f, 240f, 102f, seat);
            var p1 = Lbl(p, I18n.Tr("PLAYER 1"), 14f, Color.white, 30f, 145f, 240f, 22f, UIFactory.AlignMidCenter);
            var ph = Lbl(p, I18n.Tr("PHOTON CLOUD"), 14f, Color.white, 470f, 137f, 240f, 22f, UIFactory.AlignMidCenter);
            var p2 = Lbl(p, I18n.Tr("PLAYER 2"), 14f, Color.white, 900f, 145f, 240f, 22f, UIFactory.AlignMidCenter);
            UIFactory.SetBold(p1, true); UIFactory.SetBold(ph, true); UIFactory.SetBold(p2, true);
            Lbl(p, I18n.Tr("local fight simulation"), 12f, TXT_MAIN, 30f, 112f, 240f, 20f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("own bullets judge hits"), 12f, HDR_GOLD, 30f, 88f, 240f, 20f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("game server relay"), 12f, TXT_MAIN, 470f, 108f, 240f, 20f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("no direct PC link"), 12f, TXT_DIM, 470f, 88f, 240f, 20f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("local fight simulation"), 12f, TXT_MAIN, 900f, 112f, 240f, 20f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("own bullets judge hits"), 12f, HDR_GOLD, 900f, 88f, 240f, 20f, UIFactory.AlignMidCenter);
            Arrow(p, new Vector2(274f, 145f), new Vector2(466f, 145f), TXT_MAIN);
            Arrow(p, new Vector2(714f, 145f), new Vector2(896f, 145f), TXT_MAIN);
            Arrow(p, new Vector2(896f, 100f), new Vector2(714f, 100f), TXT_DIM);
            Arrow(p, new Vector2(466f, 100f), new Vector2(274f, 100f), TXT_DIM);
            Lbl(p, I18n.Tr("events and streamed state"), 12f, TXT_DIM, 285f, 166f, 175f, 18f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("events and streamed state"), 12f, TXT_DIM, 720f, 166f, 170f, 18f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("Each seat simulates its own replicas. Damage is computed on the shooter's seat and relayed as a final number."),
                13f, TXT_DIM, 30f, 10f, 1110f, 20f);
            return p;
        }

        // -- betting lock window --------------------------------------------

        private static GameObject BuildBetWindow(Transform parent)
        {
            const float H = 190f;
            var p = Panel(parent, "VizBetWindow", H);
            Header(p, H, I18n.Tr("1V1 BETTING WINDOW"));
            float y = 78f;
            Box(p, 70f, y, 500f, 28f, new Color(0.20f, 0.62f, 0.34f, 0.88f));
            Box(p, 570f, y, 520f, 28f, new Color(0.68f, 0.22f, 0.24f, 0.88f));
            Lbl(p, I18n.Tr("OPEN"), 13f, Color.white, 260f, y + 4f, 100f, 20f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("LOCKED"), 13f, Color.white, 780f, y + 4f, 100f, 20f, UIFactory.AlignMidCenter);
            float[] marks = { 70f, 310f, 570f, 835f, 1090f };
            foreach (float x in marks)
                Line(p, new Vector2(x, y - 8f), new Vector2(x, y + 38f), AXIS_COL, 1.5f);
            Lbl(p, I18n.Tr("series created"), 12f, TXT_MAIN, 34f, 120f, 150f, 20f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("game 1 starts"), 12f, TXT_MAIN, 240f, 48f, 140f, 20f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("LOCK: 2 total points"), 12f, HDR_GOLD, 480f, 120f, 180f, 20f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("also locks when any game is decided"), 12f, TXT_MAIN, 690f, 48f, 290f, 20f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("series ends"), 12f, TXT_MAIN, 1020f, 120f, 130f, 20f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("The cutoff is scored points, never a clock. Either lock condition closes the window."),
                13f, TXT_DIM, 70f, 8f, 1020f, 20f);
            return p;
        }

        // -- tournament bracket flow ----------------------------------------

        private static GameObject BuildBracketFlow(Transform parent)
        {
            const float H = 260f;
            var p = Panel(parent, "VizBracket", H);
            Header(p, H, I18n.Tr("8-PLAYER DOUBLE-ELIMINATION FLOW"));
            Lbl(p, I18n.Tr("A winners-bracket loss drops to the lower lane; lose there and you are out."),
                13f, TXT_DIM, 24f, 205f, 1116f, 20f);
            var round = new Color(0.22f, 0.29f, 0.44f, 0.95f);
            var loss = new Color(0.40f, 0.24f, 0.52f, 0.95f);
            string[] qf = { I18n.Tr("QF A"), I18n.Tr("QF B"), I18n.Tr("QF C"), I18n.Tr("QF D") };
            float[] qy = { 174f, 134f, 94f, 54f };
            for (int i = 0; i < qf.Length; i++)
            {
                Box(p, 24f, qy[i], 140f, 24f, round);
                Lbl(p, qf[i], 12f, Color.white, 24f, qy[i] + 2f, 140f, 20f, UIFactory.AlignMidCenter);
            }
            Box(p, 290f, 154f, 140f, 26f, round);
            Box(p, 290f, 74f, 140f, 26f, round);
            Lbl(p, I18n.Tr("SF A"), 12f, Color.white, 290f, 157f, 140f, 20f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("SF B"), 12f, Color.white, 290f, 77f, 140f, 20f, UIFactory.AlignMidCenter);
            Box(p, 555f, 114f, 150f, 28f, round);
            Lbl(p, I18n.Tr("WINNERS FINAL"), 12f, Color.white, 555f, 118f, 150f, 20f, UIFactory.AlignMidCenter);
            Box(p, 785f, 114f, 160f, 28f, new Color(0.25f, 0.55f, 0.34f, 0.90f));
            Lbl(p, I18n.Tr("WINNERS CHAMP"), 12f, Color.white, 785f, 118f, 160f, 20f, UIFactory.AlignMidCenter);
            Box(p, 982f, 104f, 158f, 48f, new Color(0.62f, 0.44f, 0.16f, 0.95f));
            Lbl(p, I18n.Tr("GRAND FINAL"), 12f, Color.white, 982f, 126f, 158f, 20f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("reset if LB wins"), 11f, TXT_MAIN, 982f, 106f, 158f, 18f, UIFactory.AlignMidCenter);
            Arrow(p, new Vector2(164f, 186f), new Vector2(286f, 167f), AXIS_COL);
            Arrow(p, new Vector2(164f, 146f), new Vector2(286f, 167f), AXIS_COL);
            Arrow(p, new Vector2(164f, 106f), new Vector2(286f, 87f), AXIS_COL);
            Arrow(p, new Vector2(164f, 66f), new Vector2(286f, 87f), AXIS_COL);
            Arrow(p, new Vector2(430f, 167f), new Vector2(551f, 128f), AXIS_COL);
            Arrow(p, new Vector2(430f, 87f), new Vector2(551f, 128f), AXIS_COL);
            Arrow(p, new Vector2(705f, 128f), new Vector2(781f, 128f), AXIS_COL);
            Arrow(p, new Vector2(945f, 128f), new Vector2(978f, 128f), AXIS_COL);
            Box(p, 290f, 18f, 655f, 28f, loss);
            Lbl(p, I18n.Tr("LOSERS BRACKET: one winners-bracket loss drops you here; a loss here eliminates you"),
                12f, Color.white, 300f, 22f, 635f, 20f, UIFactory.AlignMidCenter);
            Arrow(p, new Vector2(164f, 54f), new Vector2(286f, 32f), loss);
            Arrow(p, new Vector2(945f, 32f), new Vector2(978f, 108f), loss);
            return p;
        }

        // -- async tournament deadline --------------------------------------

        private static GameObject BuildForfeitClock(Transform parent)
        {
            const float H = 260f;
            var p = Panel(parent, "VizForfeit", H);
            Header(p, H, I18n.Tr("ASYNC MATCH DEADLINE"));
            float y = 158f;
            Box(p, 60f, y, 820f, 24f, new Color(0.40f, 0.24f, 0.52f, 0.82f));
            Line(p, new Vector2(60f, y - 8f), new Vector2(60f, y + 34f), AXIS_COL, 1.5f);
            Line(p, new Vector2(650f, y - 8f), new Vector2(650f, y + 34f), AXIS_COL, 1.5f);
            Line(p, new Vector2(880f, y - 8f), new Vector2(880f, y + 34f), HDR_GOLD, 2f);
            Lbl(p, I18n.Tr("match goes live"), 12f, TXT_MAIN, 24f, 194f, 150f, 20f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("final 24h check-in"), 12f, TXT_MAIN, 565f, 194f, 170f, 20f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("7-day deadline"), 12f, HDR_GOLD, 815f, 194f, 140f, 20f, UIFactory.AlignMidCenter);
            Box(p, 930f, y - 2f, 200f, 30f, new Color(0.24f, 0.48f, 0.32f, 0.90f));
            Lbl(p, I18n.Tr("one +24h extension"), 12f, Color.white, 930f, y + 3f, 200f, 20f, UIFactory.AlignMidCenter);
            Arrow(p, new Vector2(884f, y + 12f), new Vector2(926f, y + 12f), HDR_GOLD);
            string[] outcomes =
            {
                I18n.Tr("finished series: result stands"),
                I18n.Tr("game in last 45 min: wait"),
                I18n.Tr("one present: absent player forfeits"),
                I18n.Tr("otherwise: score / check-in / no-show tiebreak"),
            };
            float[] ox = { 20f, 300f, 580f, 860f };
            for (int i = 0; i < outcomes.Length; i++)
            {
                Box(p, ox[i], 62f, 260f, 42f, i == 2 ? new Color(0.66f, 0.24f, 0.25f, 0.90f) : KEY_NONE);
                Lbl(p, outcomes[i], 10f, TXT_MAIN, ox[i] + 6f, 73f, 248f, 20f, UIFactory.AlignMidCenter);
            }
            Lbl(p, I18n.Tr("If no earlier rule settles it, score, check-in, no-show rate and a fixed tiebreak decide."),
                13f, TXT_DIM, 20f, 12f, 1110f, 20f);
            return p;
        }

        // -- recorded / ranked decision tree --------------------------------

        private static GameObject BuildWhenCounts(Transform parent)
        {
            const float H = 260f;
            var p = Panel(parent, "VizWhenCounts", H);
            Header(p, H, I18n.Tr("WHEN A GAME IS RECORDED AND RATED"));
            var yes = new Color(0.35f, 0.78f, 0.45f, 0.90f);
            var no = new Color(0.90f, 0.34f, 0.30f, 0.90f);
            Box(p, 20f, 167f, 110f, 38f, KEY_GAME);
            Lbl(p, I18n.Tr("GAME ENDS"), 12f, Color.white, 20f, 176f, 110f, 20f, UIFactory.AlignMidCenter);
            Diamond(p, 160f, 156f, 170f, 60f, TXT_DIM);
            Lbl(p, I18n.Tr("recordable setting?"), 12f, TXT_MAIN, 174f, 177f, 142f, 20f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("online, data on, fighter"), 10f, TXT_DIM, 174f, 160f, 142f, 18f, UIFactory.AlignMidCenter);
            Diamond(p, 380f, 156f, 160f, 60f, TXT_DIM);
            Lbl(p, I18n.Tr("room type?"), 12f, TXT_MAIN, 394f, 177f, 132f, 20f, UIFactory.AlignMidCenter);
            Arrow(p, new Vector2(130f, 186f), new Vector2(156f, 186f), AXIS_COL);
            Arrow(p, new Vector2(334f, 186f), new Vector2(376f, 186f), yes);
            Lbl(p, I18n.Tr("yes"), 10f, yes, 334f, 194f, 40f, 16f, UIFactory.AlignMidCenter);
            Box(p, 585f, 164f, 555f, 48f, new Color(0.22f, 0.42f, 0.38f, 0.90f));
            Lbl(p, I18n.Tr("mod-issued: queue / 2v2 / tournament / ranked FFA = ranked"),
                11f, Color.white, 595f, 186f, 535f, 18f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("casual FFA and 1v2 = recorded, not rated"),
                11f, TXT_MAIN, 595f, 166f, 535f, 18f, UIFactory.AlignMidCenter);
            Arrow(p, new Vector2(544f, 186f), new Vector2(581f, 186f), yes);
            Lbl(p, I18n.Tr("mod-issued"), 10f, yes, 532f, 199f, 90f, 16f, UIFactory.AlignMidCenter);
            Box(p, 158f, 66f, 174f, 38f, new Color(0.58f, 0.20f, 0.22f, 0.90f));
            Lbl(p, I18n.Tr("NOT RECORDED"), 12f, Color.white, 158f, 75f, 174f, 20f, UIFactory.AlignMidCenter);
            Arrow(p, new Vector2(245f, 152f), new Vector2(245f, 108f), no);
            Lbl(p, I18n.Tr("no - stop"), 10f, no, 250f, 123f, 70f, 16f);
            Diamond(p, 430f, 48f, 180f, 68f, TXT_DIM);
            Lbl(p, I18n.Tr("opponent has run"), 11f, TXT_MAIN, 446f, 78f, 148f, 18f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("the mod?"), 11f, TXT_MAIN, 446f, 60f, 148f, 18f, UIFactory.AlignMidCenter);
            Arrow(p, new Vector2(460f, 152f), new Vector2(520f, 120f), AXIS_COL);
            Lbl(p, I18n.Tr("room code"), 10f, TXT_DIM, 456f, 127f, 80f, 16f);
            Diamond(p, 690f, 48f, 180f, 68f, TXT_DIM);
            Lbl(p, I18n.Tr("both Ranked"), 11f, TXT_MAIN, 706f, 78f, 148f, 18f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("enabled?"), 11f, TXT_MAIN, 706f, 60f, 148f, 18f, UIFactory.AlignMidCenter);
            Arrow(p, new Vector2(614f, 82f), new Vector2(686f, 82f), yes);
            Lbl(p, I18n.Tr("yes"), 10f, yes, 628f, 89f, 40f, 16f, UIFactory.AlignMidCenter);
            Box(p, 960f, 94f, 180f, 38f, new Color(0.20f, 0.58f, 0.32f, 0.90f));
            Box(p, 960f, 38f, 180f, 38f, new Color(0.22f, 0.34f, 0.52f, 0.90f));
            Lbl(p, I18n.Tr("RANKED"), 12f, Color.white, 960f, 103f, 180f, 20f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("CASUAL, RECORDED"), 12f, Color.white, 960f, 47f, 180f, 20f, UIFactory.AlignMidCenter);
            Arrow(p, new Vector2(874f, 82f), new Vector2(956f, 113f), yes);
            Arrow(p, new Vector2(780f, 44f), new Vector2(956f, 57f), no);
            Arrow(p, new Vector2(520f, 44f), new Vector2(956f, 57f), no);
            Lbl(p, I18n.Tr("no - casual"), 10f, no, 600f, 40f, 90f, 16f);
            Lbl(p, I18n.Tr("no - casual"), 10f, no, 840f, 50f, 90f, 16f);
            Lbl(p, I18n.Tr("Casual games keep their stats and XP but never move rating."),
                13f, TXT_DIM, 390f, 8f, 560f, 20f, UIFactory.AlignMidCenter);
            return p;
        }

        // -- RefreshValid state machine (Spirit) ----------------------------

        private static GameObject BuildRefreshFlow(Transform parent)
        {
            const float H = 250f;
            var p = Panel(parent, "VizRefresh", H);
            Header(p, H, I18n.Tr("REFRESHVALID STATE MACHINE"));
            var trueCol = new Color(0.20f, 0.58f, 0.32f, 0.92f);
            var falseCol = new Color(0.62f, 0.25f, 0.28f, 0.92f);
            Box(p, 210f, 138f, 190f, 44f, trueCol);
            Box(p, 760f, 138f, 190f, 44f, falseCol);
            Lbl(p, I18n.Tr("RefreshValid = true"), 13f, Color.white, 210f, 150f, 190f, 20f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("RefreshValid = false"), 13f, Color.white, 760f, 150f, 190f, 20f, UIFactory.AlignMidCenter);
            Arrow(p, new Vector2(404f, 170f), new Vector2(756f, 170f), HDR_GOLD);
            Lbl(p, I18n.Tr("5-10 damage: Refresh triggers"), 12f, HDR_GOLD, 430f, 184f, 300f, 18f, UIFactory.AlignMidCenter);
            Arrow(p, new Vector2(756f, 146f), new Vector2(404f, 146f), TXT_DIM);
            Lbl(p, I18n.Tr("5-10 damage: no Refresh"), 12f, TXT_MAIN, 430f, 119f, 300f, 18f, UIFactory.AlignMidCenter);
            Box(p, 40f, 57f, 300f, 42f, KEY_NONE);
            Lbl(p, I18n.Tr("under 5 damage: nothing; state unchanged"),
                11f, TXT_MAIN, 46f, 68f, 288f, 20f, UIFactory.AlignMidCenter);
            Box(p, 415f, 57f, 330f, 42f, new Color(0.22f, 0.38f, 0.56f, 0.90f));
            Lbl(p, I18n.Tr("over 10, outside 0.35s: Refresh; set false"),
                11f, Color.white, 421f, 68f, 318f, 20f, UIFactory.AlignMidCenter);
            Arrow(p, new Vector2(745f, 78f), new Vector2(855f, 134f), new Color(0.30f, 0.68f, 0.95f, 0.90f));
            Box(p, 820f, 57f, 320f, 42f, KEY_NONE);
            Lbl(p, I18n.Tr("over 10 inside 0.35s: treat as Conditional"),
                11f, TXT_MAIN, 826f, 68f, 308f, 20f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("Diagram of Spirit's research, 'On Damage Types and Buff Activation'."),
                13f, TXT_DIM, 40f, 10f, 1100f, 20f);
            return p;
        }

        // -- movement timing windows ----------------------------------------

        private static GameObject BuildMovementWindow(Transform parent)
        {
            const float H = 230f;
            var p = Panel(parent, "VizMovement", H);
            Header(p, H, I18n.Tr("EDGE BOUNCE AND WALL-JUMP WINDOWS"));
            Lbl(p, I18n.Tr("SHIELD EDGE BOUNCE"), 13f, HDR_GOLD, 24f, 174f, 260f, 20f);
            Line(p, new Vector2(345f, 68f), new Vector2(345f, 172f), new Color(0.90f, 0.34f, 0.30f, 0.90f), 3f);
            Box(p, 225f, 112f, 34f, 34f, KEY_GAME);
            Arrow(p, new Vector2(263f, 129f), new Vector2(395f, 129f), new Color(0.90f, 0.34f, 0.30f, 0.90f));
            Arrow(p, new Vector2(395f, 98f), new Vector2(263f, 98f), new Color(0.35f, 0.78f, 0.45f, 0.90f), 3f);
            Lbl(p, I18n.Tr("kill boundary"), 11f, TXT_DIM, 306f, 48f, 100f, 18f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("not blocking: 51 damage + return impulse"), 11f, TXT_MAIN, 24f, 82f, 300f, 18f);
            Lbl(p, I18n.Tr("blocking: 0 damage + 2x return impulse"), 11f, TXT_MAIN, 24f, 60f, 300f, 18f);
            Lbl(p, I18n.Tr("edge check: 0.1s; block window: 0.3s"), 13f, TXT_DIM, 24f, 12f, 500f, 20f);
            Lbl(p, I18n.Tr("WALL JUMP"), 13f, HDR_GOLD, 610f, 174f, 180f, 20f);
            Line(p, new Vector2(900f, 62f), new Vector2(900f, 172f), AXIS_COL, 4f);
            Box(p, 828f, 104f, 34f, 34f, KEY_GAME);
            Arrow(p, new Vector2(864f, 121f), new Vector2(896f, 121f), TXT_MAIN);
            Arrow(p, new Vector2(846f, 102f), new Vector2(790f, 162f), new Color(0.30f, 0.68f, 0.95f, 0.90f), 3f);
            Lbl(p, I18n.Tr("touch wall while holding into it"), 11f, TXT_MAIN, 615f, 126f, 250f, 18f);
            Lbl(p, I18n.Tr("jump within 0.1s: up and away"), 11f, TXT_MAIN, 615f, 102f, 250f, 18f);
            Lbl(p, I18n.Tr("wall touch refreshes all jumps unless you jumped within the last 0.15s"),
                13f, TXT_DIM, 610f, 12f, 530f, 20f);
            return p;
        }

        // -- 2v2 format ------------------------------------------------------

        private static GameObject BuildTeamFormat(Transform parent)
        {
            const float H = 220f;
            var p = Panel(parent, "VizTeam", H);
            Header(p, H, I18n.Tr("2V2: ONE SERIES, TWO TEAMS"));
            var stage = new Color(0.18f, 0.31f, 0.50f, 0.95f);
            float y = 126f;
            Box(p, 24f, y, 180f, 48f, stage);
            Box(p, 265f, y, 220f, 48f, stage);
            Box(p, 550f, y, 260f, 48f, stage);
            Box(p, 875f, y, 265f, 48f, new Color(0.24f, 0.52f, 0.34f, 0.92f));
            Lbl(p, I18n.Tr("2v2 QUEUE"), 13f, Color.white, 24f, y + 24f, 180f, 20f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("4 players"), 11f, TXT_MAIN, 24f, y + 5f, 180f, 18f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("AUTO-BALANCE"), 13f, Color.white, 265f, y + 24f, 220f, 20f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("two teams of two"), 11f, TXT_MAIN, 265f, y + 5f, 220f, 18f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("BEST-OF-3"), 13f, Color.white, 550f, y + 24f, 260f, 20f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("first team to 2 games"), 11f, TXT_MAIN, 550f, y + 5f, 260f, 18f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("COMPLETED SERIES"), 13f, Color.white, 875f, y + 24f, 265f, 20f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("one 2v2 rating outcome"), 11f, TXT_MAIN, 875f, y + 5f, 265f, 18f, UIFactory.AlignMidCenter);
            Arrow(p, new Vector2(208f, y + 24f), new Vector2(261f, y + 24f), AXIS_COL);
            Arrow(p, new Vector2(489f, y + 24f), new Vector2(546f, y + 24f), AXIS_COL);
            Arrow(p, new Vector2(814f, y + 24f), new Vector2(871f, y + 24f), AXIS_COL);
            Box(p, 265f, 62f, 220f, 34f, new Color(0.72f, 0.38f, 0.16f, 0.90f));
            Box(p, 550f, 62f, 220f, 34f, new Color(0.20f, 0.42f, 0.72f, 0.90f));
            Lbl(p, I18n.Tr("Team 1: orange"), 12f, Color.white, 265f, 69f, 220f, 20f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("Team 2: blue"), 12f, Color.white, 550f, 69f, 220f, 20f, UIFactory.AlignMidCenter);
            Lbl(p, I18n.Tr("W-L and WR count completed series. XP and Gold accrue per player slot; 1v1 rating never moves."),
                13f, TXT_DIM, 24f, 14f, 1116f, 20f);
            return p;
        }

        // Locale-neutral placement tag: English ordinal suffixes ("th") are
        // sub-3-letter fragments the extractor rightly refuses (#295c), so we
        // use #N, which reads the same in every shipped locale.
        private static string Ordinal(int n) => "#" + n;
    }
}
