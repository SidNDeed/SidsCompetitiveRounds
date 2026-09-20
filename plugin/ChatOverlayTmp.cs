using System;
using System.Collections.Generic;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Bug 333: the minimised in-game chat, rendered with TextMeshPro
    /// instead of IMGUI. The IMGUI panel drew with Unity's built-in font and no
    /// fallback, so every glyph outside it (emoji, most non-Latin scripts) was
    /// a box while the F5 pane — TMP with the OS fallback chain (#110) — showed
    /// them. This panel is the same text system as the pane: SetTextRaw
    /// registers each line's glyphs in the runtime fallback before layout.
    ///
    /// Division of labour: CompetitiveUI.DrawInGameChat keeps EVERY gate and the
    /// fade math (they are the one place those rules live) and hands the lines
    /// over once per rendered frame (Begin / Add / End); this class owns only
    /// the objects. Own canvas: ScreenSpaceOverlay at sortingOrder 30001 (IMGUI
    /// painted above the F5 page too, so the stacking is unchanged; IMGUI
    /// modals still paint above this), ConstantPixelSize so the geometry stays
    /// in the screen pixels the IMGUI input box still uses, and NO
    /// GraphicRaycaster — display-only and click-through, exactly as before
    /// (#141/#200 stay moot). Persistent (HideAndDontSave + DontDestroyOnLoad)
    /// with the #369 respawn check: a child that ROUNDS' scene teardown
    /// destroyed is rebuilt on the next frame that has lines to show.</summary>
    internal static class ChatOverlayTmp
    {
        internal const int MaxLines = 9;            // 8 messages + the bug-213 mute header
        internal const float PanelW = 440f;         // text width, as the IMGUI panel had
        internal const float PanelX = 12f;
        internal const float Padding = 6f, LineGap = 2f, BackdropBleed = 4f;
        internal const float FontSize = 15f;
        // == DrawChatInput's `bdTop = Screen.height - 90f` ("message panel
        // bottom"). The input box is still IMGUI and hard-codes that value;
        // move one and the other, or the 60 px band under the panel breaks.
        internal const float BottomMargin = 90f;
        private const int MaxWrapLines = 3;

        private static GameObject canvasGO, panelGO, backdropGO;
        private static RectTransform panelRT;
        private static readonly object[] lineTmp = new object[MaxLines];
        private static readonly RectTransform[] lineRT = new RectTransform[MaxLines];
        private static readonly string[] lineShown = new string[MaxLines];
        private static readonly Color[] lineColor = new Color[MaxLines];
        private static readonly float[] lineY = new float[MaxLines], lineH = new float[MaxLines];
        private static float shownPanelH = -1f, shownBackdropA = -1f;
        private static bool panelVisible;
        private static int lastFedFrame = -1;
        private static float singleLineH = -1f;

        private struct Fit { public string Disp; public float H; }
        private static readonly Dictionary<string, Fit> fitCache = new Dictionary<string, Fit>();

        // The frame being assembled between Begin and End.
        private static int count;
        private static readonly string[] fText = new string[MaxLines];
        private static readonly float[] fAlpha = new float[MaxLines];
        private static readonly Color[] fTint = new Color[MaxLines];

        internal static void Begin() { count = 0; }

        /// <summary>Queue one line for this frame, bottom-up: the first Add is
        /// the bottom (newest) row, the last the top. Beyond MaxLines is dropped.</summary>
        internal static void Add(string text, float alpha, Color tint)
        {
            if (count >= MaxLines || string.IsNullOrEmpty(text)) return;
            fText[count] = text; fAlpha[count] = alpha; fTint[count] = tint; count++;
        }

        /// <summary>Lay the queued lines out and show the panel (or hide it when
        /// nothing was queued). Everything is written only on change: text
        /// (SetTextRaw re-registers glyphs and re-lays out), colour, rects.</summary>
        internal static void End(float backdropAlpha)
        {
            lastFedFrame = Time.frameCount;
            if (count == 0) { Hide(); return; }
            try
            {
                if (!Ensure()) return;
                float y = Padding;
                for (int i = 0; i < count; i++)
                {
                    var fit = Measure(fText[i]);
                    if (!ReferenceEquals(lineShown[i], fit.Disp) && lineShown[i] != fit.Disp)
                    {
                        UIFactory.SetTextRaw(lineTmp[i], fit.Disp);
                        lineShown[i] = fit.Disp;
                    }
                    var c = new Color(fTint[i].r, fTint[i].g, fTint[i].b, fAlpha[i]);
                    if (ColorDiffers(lineColor[i], c)) { UIFactory.SetColor(lineTmp[i], c); lineColor[i] = c; }
                    if (lineY[i] != y || lineH[i] != fit.H)
                    {
                        lineRT[i].anchoredPosition = new Vector2(BackdropBleed, y);
                        lineRT[i].sizeDelta = new Vector2(PanelW, fit.H);
                        lineY[i] = y; lineH[i] = fit.H;
                    }
                    if (!lineRT[i].gameObject.activeSelf) lineRT[i].gameObject.SetActive(true);
                    y += fit.H + LineGap;
                }
                for (int i = count; i < MaxLines; i++)
                    if (lineRT[i] != null && lineRT[i].gameObject.activeSelf) lineRT[i].gameObject.SetActive(false);
                float panelH = y - LineGap + Padding;
                if (shownPanelH != panelH)
                {
                    panelRT.sizeDelta = new Vector2(PanelW + BackdropBleed * 2f, panelH);
                    shownPanelH = panelH;
                }
                if (Mathf.Abs(shownBackdropA - backdropAlpha) > 1f / 255f)
                {
                    UIFactory.SetImageColor(backdropGO, new Color(0f, 0f, 0f, backdropAlpha));
                    shownBackdropA = backdropAlpha;
                }
                if (!panelVisible) { panelGO.SetActive(true); panelVisible = true; }
            }
            catch (Exception ex)
            {
                VanillaFixSupport.DiagLimited("ChatOverlayTmp", "layout failed: " + ex.Message, 5);
            }
        }

        internal static void Hide()
        {
            if (panelVisible && panelGO != null) { try { panelGO.SetActive(false); } catch { } }
            panelVisible = false;
        }

        /// <summary>LateUpdate on the canvas (ChatOverlayWatchdog): when
        /// DrawInGameChat stopped feeding — OnGUI not running, a caller path
        /// that returned without Hide — the panel must not linger with stale
        /// lines over the game.</summary>
        internal static void OnLateUpdate()
        {
            if (panelVisible && Time.frameCount - lastFedFrame > 2) Hide();
        }

        private static bool ColorDiffers(Color a, Color b)
        {
            const float q = 1f / 255f;
            return Mathf.Abs(a.r - b.r) > q || Mathf.Abs(a.g - b.g) > q
                || Mathf.Abs(a.b - b.b) > q || Mathf.Abs(a.a - b.a) > q;
        }

        private static bool Ensure()
        {
            if (canvasGO == null) BuildCanvas();               // Unity's == : destroyed reads as null
            if (canvasGO == null) return false;
            if (panelGO == null || panelGO.transform.parent != canvasGO.transform) BuildPanel();
            return panelGO != null;
        }

        private static void BuildCanvas()
        {
            try
            {
                canvasGO = new GameObject("CR_ChatOverlayCanvas");
                canvasGO.hideFlags = HideFlags.HideAndDontSave;
                UnityEngine.Object.DontDestroyOnLoad(canvasGO);
                var bf = System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance;
                if (UIFactory.tCanvas != null)
                {
                    var cv = canvasGO.AddComponent(UIFactory.tCanvas);
                    var rm = UIFactory.tCanvas.GetProperty("renderMode", bf);
                    rm?.SetValue(cv, Enum.ToObject(rm.PropertyType, 0));                       // ScreenSpaceOverlay
                    // 30002: above F5's 30000 as IMGUI was, and above the TmpOverlayPanel
                    // surfaces at 30001 (the hover profile card) -- the chat is never
                    // covered by a card (design A-1; review a-M5).
                    UIFactory.tCanvas.GetProperty("sortingOrder", bf)?.SetValue(cv, 30002);
                }
                if (UIFactory.tCanvasScaler != null)
                {
                    var sc = canvasGO.AddComponent(UIFactory.tCanvasScaler);
                    var smp = UIFactory.tCanvasScaler.GetProperty("uiScaleMode", bf);
                    if (smp != null) smp.SetValue(sc, Enum.ToObject(smp.PropertyType, 0));    // ConstantPixelSize: 1 unit = 1 px
                }
                // No GraphicRaycaster: display-only, click-through.
                canvasGO.AddComponent<ChatOverlayWatchdog>();
                Plugin.Log.LogInfo("[CHAT-TMP] created the minimised-chat canvas");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning("[CHAT-TMP] canvas create failed: " + ex.Message);
                canvasGO = null;
            }
        }

        private static void BuildPanel()
        {
            panelGO = null; panelVisible = false; shownPanelH = -1f; shownBackdropA = -1f; singleLineH = -1f;
            fitCache.Clear();
            for (int i = 0; i < MaxLines; i++)
            {
                lineTmp[i] = null; lineRT[i] = null; lineShown[i] = null;
                lineColor[i] = default(Color); lineY[i] = -1f; lineH[i] = -1f;
            }
            var go = new GameObject("CR_ChatOverlayPanel");
            go.transform.SetParent(canvasGO.transform, false);
            panelRT = go.AddComponent<RectTransform>();
            panelRT.anchorMin = panelRT.anchorMax = Vector2.zero;   // screen bottom-left
            panelRT.pivot = Vector2.zero;
            panelRT.anchoredPosition = new Vector2(PanelX - BackdropBleed, BottomMargin);
            panelRT.sizeDelta = new Vector2(PanelW + BackdropBleed * 2f, 20f);
            backdropGO = UIFactory.CreatePanel("BG", go.transform, new Color(0f, 0f, 0f, 0.55f), Vector2.zero);
            var bgRT = backdropGO.GetComponent<RectTransform>();
            if (bgRT != null)
            {
                bgRT.anchorMin = Vector2.zero; bgRT.anchorMax = Vector2.one;
                bgRT.offsetMin = Vector2.zero; bgRT.offsetMax = Vector2.zero;
            }
            for (int i = 0; i < MaxLines; i++)
            {
                // Truncate (CreateText's default) and never Ellipsis (#47); the
                // cut itself is done in Measure, with the "[see F5]" indicator.
                var tmp = UIFactory.CreateText("L" + i, go.transform, "", FontSize, Color.white,
                                               UIFactory.AlignTopLeft, new Vector2(PanelW, 20f), true, false);
                UIFactory.SetWordWrap(tmp, true);
                try { EmojiSprites.Attach(tmp); } catch { }   // 333 step 2: colour emoji sprites on this label (no-op until the atlas is live)
                var rt = ((Component)tmp).GetComponent<RectTransform>();
                rt.anchorMin = rt.anchorMax = Vector2.zero;
                rt.pivot = Vector2.zero;
                lineTmp[i] = tmp; lineRT[i] = rt;
                rt.gameObject.SetActive(false);
            }
            panelGO = go;
            go.SetActive(false);
        }

        /// <summary>Display string and height for one line: wrapped at PanelW,
        /// capped at MaxWrapLines with the same rule the IMGUI panel had —
        /// never cut before the last rich-text tag (the name/title markup is at
        /// the head; user text is paren-escaped upstream, so '>' is only our
        /// markup), binary-search the longest prefix that fits with the
        /// indicator. Cached per line; the cache is bounded.</summary>
        private static Fit Measure(string line)
        {
            // Review LOW: the fitted string embeds the translated indicator,
            // so the cache key carries it too -- a locale switch or a
            // translation-pack update re-measures instead of reusing the
            // previous language's cut.
            string suffix = " ... " + I18n.Tr("[see F5]");
            // 333 step 2: the fitted string also embeds the emoji substitution, so the
            // atlas generation is part of the key -- an atlas arriving mid-session
            // re-measures instead of reusing a monochrome cut.
            string cacheKey = suffix + "\u0001" + EmojiSprites.Generation + "\u0001" + line;
            Fit cached;
            if (fitCache.TryGetValue(cacheKey, out cached)) return cached;
            if (fitCache.Count > 256) fitCache.Clear();
            object probe = lineTmp[0];
            if (singleLineH <= 0f)
            {
                singleLineH = UIFactory.MeasureTextHeight(probe, "Ag", PanelW);
                if (singleLineH <= 0f) singleLineH = FontSize * 1.3f;   // API missing: estimate, never 0
            }
            float maxH = singleLineH * MaxWrapLines + 2f;
            // MEASUREMENT FAILURE IS NOT "IT FITS" (#357, r2 MEDIUM). Height() used
            // to floor a failed measurement to one line, so a wholesale failure gave
            // every line a one-line height that could never exceed maxH: the cut
            // never ran, the "[see F5]" marker never appeared, and a long message was
            // drawn into a one-line rect against a Truncate label — which is exactly
            // the reported symptom, with the code reporting success. The unmeasurable
            // case now engages truncation conservatively and says so.
            float measured = HeightOrFail(probe, line);
            bool unmeasurable = measured < 0f;
            var fit = new Fit { Disp = line, H = unmeasurable ? maxH : measured };
            if (unmeasurable || fit.H > maxH)
            {
                int minCut = line.LastIndexOf('>') + 1;
                if (minCut < 1) minCut = 1;
                if (minCut < line.Length - 1)
                {
                    int lo = Math.Min(minCut + 1, line.Length), hi = line.Length, best = SafeCut(line, lo);
                    if (unmeasurable)
                    {
                        // No oracle to binary-search against, so a CHARACTER budget
                        // takes its place: the width divided by a deliberately narrow
                        // per-character estimate, times the wrap allowance. It is an
                        // estimate and is not pretending otherwise — it exists to make
                        // the marker appear and the rect claim its full allowance,
                        // which is the conservative direction. Never cuts before
                        // minCut, so the markup head always survives.
                        int perLine = Math.Max(8, (int)(PanelW / (FontSize * 0.5f)));
                        int budget = perLine * MaxWrapLines;
                        best = SafeCut(line, Math.Max(Math.Min(minCut + 1, line.Length),
                                                      Math.Min(budget, line.Length)));
                        WarnMeasurementUnavailable();
                    }
                    else
                    {
                        while (lo <= hi)
                        {
                            int mid = (lo + hi) / 2;
                            int cut = SafeCut(line, mid);   // review LOW: never split a surrogate pair
                            float h = HeightOrFail(probe, line.Substring(0, cut).TrimEnd() + suffix);
                            // A probe that could not be measured is NOT a fit.
                            if (h >= 0f && h <= maxH) { best = cut; lo = mid + 1; }
                            else hi = mid - 1;
                        }
                    }
                    fit.Disp = line.Substring(0, best).TrimEnd() + suffix;
                    float fh = HeightOrFail(probe, fit.Disp);
                    fit.H = fh >= 0f ? fh : maxH;
                }
                else
                {
                    // Markup-final line (nothing trimmable): keep the full
                    // allowance rather than append a false indicator to an uncut
                    // line. When the height came from no measurement at all, say
                    // so — the line is drawn against an estimate either way.
                    if (unmeasurable) WarnMeasurementUnavailable();
                }
            }
            if (fit.H <= 0f) fit.H = singleLineH;
            // 333 step 2: substitute AFTER the cut, so minCut (LastIndexOf('>')) never
            // lands inside a sprite tag and the cut never splits one; sprites keep the
            // font's line metrics, so the measured height stands.
            try { fit.Disp = EmojiSprites.Substitute(fit.Disp); } catch { }
            fitCache[cacheKey] = fit;
            return fit;
        }

        /// <summary>Back off one UTF-16 unit when idx would land between the
        /// halves of a surrogate pair (an emoji at the cut).</summary>
        /// <summary>Never split a surrogate pair, and (review f r2) never split an
        /// emoji SEQUENCE: a cut is moved back past a ZWJ, a variation selector,
        /// a keycap combiner, a skin-tone modifier pair and the second half of a
        /// regional-indicator (flag) pair, so the fitted prefix ends on a whole
        /// glyph cluster whether it renders as fallback glyphs or as one sprite.</summary>
        private static int SafeCut(string s, int idx)
        {
            while (idx > 0 && idx < s.Length)          // every continuing branch decrements idx: terminates at 0
            {
                if (char.IsLowSurrogate(s[idx])) { idx--; continue; }             // inside a pair
                char c = s[idx], prev = s[idx - 1];
                bool joinerAhead = c == (char)0x200D || c == (char)0xFE0F || c == (char)0xFE0E || c == (char)0x20E3;
                bool joinerBehind = prev == (char)0x200D;
                bool modifierAhead = c == (char)0xD83C && idx + 1 < s.Length && s[idx + 1] >= (char)0xDFFB && s[idx + 1] <= (char)0xDFFF;
                bool flagSplit = IsRegionalIndicator(s, idx) && RegionalRunBefore(s, idx) % 2 == 1;
                if (joinerAhead || joinerBehind || modifierAhead || flagSplit) { idx--; continue; }
                break;
            }
            return idx;
        }

        private static bool IsRegionalIndicator(string s, int i)
        {
            return i >= 0 && i + 1 < s.Length && s[i] == (char)0xD83C && s[i + 1] >= (char)0xDDE6 && s[i + 1] <= (char)0xDDFF;
        }

        /// <summary>How many regional-indicator pairs immediately precede `idx`.</summary>
        private static int RegionalRunBefore(string s, int idx)
        {
            int run = 0;
            for (int i = idx - 2; i >= 0 && IsRegionalIndicator(s, i); i -= 2) run++;
            return run;
        }

        /// <summary>The measured height, or a NEGATIVE value when the measurement
        /// API gave no answer. Separated from <see cref="Height"/> so a caller that
        /// is DECIDING something cannot silently receive an estimate: the render
        /// path wants a usable number and the fit path wants the truth.</summary>
        private static float HeightOrFail(object tmp, string text)
        {
            try
            {
                float h = UIFactory.MeasureTextHeight(tmp, text, PanelW);
                return h > 0f ? h : -1f;
            }
            catch { return -1f; }
        }

        /// <summary>A height that is always usable for a rect. Failure floors to one
        /// line, which is right for DRAWING and wrong for deciding — see
        /// <see cref="HeightOrFail"/>.</summary>
        private static float Height(object tmp, string text)
        {
            float h = HeightOrFail(tmp, text);
            return h > 0f ? h : singleLineH;
        }

        private static bool _warnedNoMeasure;

        /// <summary>Once per session. The condition is process-wide (the measure API
        /// is there or it is not), so one line names it and the rest of the bundle
        /// stays readable.</summary>
        private static void WarnMeasurementUnavailable()
        {
            if (_warnedNoMeasure) return;
            _warnedNoMeasure = true;
            try
            {
                Plugin.Log.LogWarning("[CHAT-OVERLAY] text measurement is unavailable — "
                    + "chat lines are being truncated on a character estimate with the "
                    + "indicator forced, rather than drawn uncut into a one-line rect (#357)");
            }
            catch { }
        }
    }

    /// <summary>Rides on the chat canvas so a stalled feeder hides the panel.</summary>
    internal sealed class ChatOverlayWatchdog : MonoBehaviour
    {
        private void LateUpdate() { ChatOverlayTmp.OnLateUpdate(); }
    }
}
