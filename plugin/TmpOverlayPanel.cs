using System;
using System.Reflection;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>A mod-owned TextMeshPro overlay panel: the object layer that
    /// ChatOverlayTmp (bug 333 step 1) built for the minimised chat, extracted
    /// beside it so a second surface (Sept 6 Group 4 item a, ProfileCard)
    /// renders through the SAME text system as the F5 pane — TMP with the OS
    /// fallback chain (#110), so names with emoji or non-Latin glyphs draw
    /// instead of boxing (IMGUI has no fallback font: bug 333's mechanism).
    /// ChatOverlayTmp itself is unchanged; its layout rules (bottom-up lines,
    /// the "[see F5]" cut) are the chat's, not the panel's.
    ///
    /// Own canvas per panel: ScreenSpaceOverlay at sortingOrder 30001 (above
    /// the F5 page's 30000; IMGUI modals still paint above this),
    /// ConstantPixelSize so every rect is in screen pixels — the units
    /// Input.mousePosition and CompetitiveUI.LiveRegionRect speak. Persistent
    /// (HideAndDontSave + DontDestroyOnLoad) with the #369 respawn check:
    /// Ensure() rebuilds the root when ROUNDS' scene teardown destroyed it and
    /// tells the owner so it re-adds its children.
    ///
    /// Input: a GraphicRaycaster is added only when the owner asks for one,
    /// and every Image this class creates has raycastTarget OFF; the owner
    /// turns the backdrop's on (SetBackdropRaycast) for exactly the span it
    /// means to own clicks over its own body. So a panel is click-through by
    /// default (#141/#200 stay moot), as the chat always was.
    ///
    /// Fitting is by MEASURED pixels, never a character budget (#528); a cut
    /// never splits a surrogate pair (SafeCut) and the marker is "..." and
    /// never U+2026 (#47).</summary>
    internal sealed class TmpOverlayPanel
    {
        internal const int DefaultSortingOrder = 30001;

        private readonly string name;
        private readonly int sortingOrder;
        private readonly bool raycasts;
        private GameObject canvasGO, rootGO, backdropGO;
        private RectTransform rootRT;
        private bool visible;
        private static PropertyInfo pRaycastTarget;

        internal TmpOverlayPanel(string name, int sortingOrder = DefaultSortingOrder, bool raycasts = false)
        {
            this.name = name;
            this.sortingOrder = sortingOrder;
            this.raycasts = raycasts;
        }

        internal GameObject CanvasGO => canvasGO;
        internal GameObject RootGO => rootGO;
        internal RectTransform Root => rootRT;
        internal bool Visible => visible && rootGO != null && rootGO.activeSelf;

        /// <summary>Canvas and root exist after this (built on demand). `rebuilt`
        /// is true when the root had to be (re)created — every child the owner
        /// added before is gone and must be added again. Returns false when
        /// Unity refused (no Canvas type resolved); the owner then renders
        /// nothing.</summary>
        internal bool Ensure(out bool rebuilt)
        {
            rebuilt = false;
            if (canvasGO == null) BuildCanvas();               // Unity's == : destroyed reads as null
            if (canvasGO == null) return false;
            if (rootGO == null || rootGO.transform.parent != canvasGO.transform)
            {
                BuildRoot();
                rebuilt = rootGO != null;
            }
            return rootGO != null;
        }

        internal void Show()
        {
            if (rootGO != null && !rootGO.activeSelf) rootGO.SetActive(true);
            visible = rootGO != null;
        }

        internal void Hide()
        {
            if (rootGO != null && rootGO.activeSelf) { try { rootGO.SetActive(false); } catch { } }
            visible = false;
        }

        /// <summary>Screen-pixel rect, bottom-left origin (Input.mousePosition's frame).</summary>
        internal void SetRect(float x, float y, float w, float h)
        {
            if (rootRT == null) return;
            rootRT.anchoredPosition = new Vector2(x, y);
            rootRT.sizeDelta = new Vector2(w, h);
        }

        internal Rect ScreenRect => rootRT != null
            ? new Rect(rootRT.anchoredPosition.x, rootRT.anchoredPosition.y, rootRT.sizeDelta.x, rootRT.sizeDelta.y)
            : new Rect(-99999f, -99999f, 1f, 1f);

        internal void SetBackdrop(Color c) { if (backdropGO != null) UIFactory.SetImageColor(backdropGO, c); }

        /// <summary>The ONLY raycast target this panel ever owns: on = clicks
        /// over the body stop here (a pinned card), off = click-through.</summary>
        internal void SetBackdropRaycast(bool on) { SetRaycast(backdropGO, on); }

        /// <summary>One TMP text child, placed top-left inside the root (x to the
        /// right, yTop down from the root's top edge). Created EMPTY: the owner
        /// writes it with UIFactory.SetTextRaw (user-authored or already
        /// composed text) or SetText (a catalogue string) — CreateText passes
        /// its initial text through the translation catalogue, which a display
        /// name must never touch.</summary>
        internal object AddText(string childName, float x, float yTop, float w, float h, float fontSize, Color color,
                                int align = UIFactory.AlignTopLeft, bool wrap = false)
        {
            if (rootGO == null) return null;
            var tmp = UIFactory.CreateText(childName, rootGO.transform, "", fontSize, color, align, new Vector2(w, h), true, false);
            UIFactory.SetWordWrap(tmp, wrap);
            var rt = ((Component)tmp).GetComponent<RectTransform>();
            PlaceTopLeft(rt, x, yTop, w, h);
            return tmp;
        }

        /// <summary>One solid Image child (bars, dots, dividers), raycast OFF.</summary>
        internal GameObject AddPanel(string childName, float x, float yTop, float w, float h, Color color)
        {
            if (rootGO == null) return null;
            var go = UIFactory.CreatePanel(childName, rootGO.transform, color, Vector2.zero);
            SetRaycast(go, false);
            var rt = go.GetComponent<RectTransform>();
            if (rt != null) PlaceTopLeft(rt, x, yTop, w, h);
            return go;
        }

        /// <summary>Anchor a child to its parent's top-left corner with a fixed
        /// rect: x to the right, yTop down from the top edge.</summary>
        internal static void PlaceTopLeft(RectTransform rt, float x, float yTop, float w, float h)
        {
            if (rt == null) return;
            rt.anchorMin = rt.anchorMax = new Vector2(0f, 1f);
            rt.pivot = new Vector2(0f, 1f);
            rt.anchoredPosition = new Vector2(x, -yTop);
            rt.sizeDelta = new Vector2(w, h);
        }

        internal static void SetRaycast(GameObject go, bool on)
        {
            if (go == null || UIFactory.tImage == null) return;
            try
            {
                var img = go.GetComponent(UIFactory.tImage);
                if (img == null) return;
                if (pRaycastTarget == null)
                    pRaycastTarget = UIFactory.tImage.GetProperty("raycastTarget", BindingFlags.Public | BindingFlags.Instance);
                pRaycastTarget?.SetValue(img, on);
            }
            catch { }
        }

        internal static float MeasureWidth(object probe, string text) => UIFactory.MeasureTextWidth(probe, text);
        internal static float MeasureHeight(object probe, string text, float width) => UIFactory.MeasureTextHeight(probe, text, width);

        /// <summary>The longest prefix of `text` that renders within maxW pixels
        /// on `probe`'s font, with the marker appended when anything was cut.
        /// Plain text only — a cut inside rich-text markup would leave an open
        /// tag, so callers fit the user-authored PART and compose the markup
        /// around the result. An unmeasurable probe (API missing) returns the
        /// text unchanged; the element's Truncate overflow is the backstop.</summary>
        internal static string FitOneLine(object probe, string text, float maxW, string marker = "...")
        {
            if (string.IsNullOrEmpty(text) || probe == null || maxW <= 0f) return text ?? "";
            float w = MeasureWidth(probe, text);
            if (w <= 0f || w <= maxW) return text;
            int lo = 1, hi = text.Length - 1, best = 0;
            while (lo <= hi)
            {
                int mid = (lo + hi) / 2;
                int cut = SafeCut(text, mid);
                if (MeasureWidth(probe, text.Substring(0, cut).TrimEnd() + marker) <= maxW) { best = cut; lo = mid + 1; }
                else hi = mid - 1;
            }
            return best <= 0 ? marker : text.Substring(0, best).TrimEnd() + marker;
        }

        /// <summary>ChatOverlayTmp.Measure's rule for a wrapped body: the whole
        /// text when it fits in `maxLines` lines at `width`, else the longest
        /// prefix that does with the marker appended. Returns the display string
        /// and its measured height (0 when the probe cannot measure).</summary>
        internal static string FitLines(object probe, string text, float width, int maxLines, string marker, out float height)
        {
            height = 0f;
            if (probe == null || string.IsNullOrEmpty(text)) return text ?? "";
            float lineH = MeasureHeight(probe, "Ag", width);
            if (lineH <= 0f) return text;
            float maxH = lineH * Math.Max(1, maxLines) + 2f;
            float h = MeasureHeight(probe, text, width);
            if (h <= maxH) { height = h > 0f ? h : lineH; return text; }
            int lo = 1, hi = text.Length - 1, best = SafeCut(text, 1);
            while (lo <= hi)
            {
                int mid = (lo + hi) / 2;
                int cut = SafeCut(text, mid);
                if (MeasureHeight(probe, text.Substring(0, cut).TrimEnd() + marker, width) <= maxH) { best = cut; lo = mid + 1; }
                else hi = mid - 1;
            }
            string disp = text.Substring(0, best).TrimEnd() + marker;
            height = Math.Max(lineH, MeasureHeight(probe, disp, width));
            return disp;
        }

        /// <summary>Back off one UTF-16 unit when idx would land between the
        /// halves of a surrogate pair (an emoji at the cut).</summary>
        internal static int SafeCut(string s, int idx)
        {
            if (idx > 0 && idx < s.Length && char.IsHighSurrogate(s[idx - 1])) idx--;
            return idx;
        }

        internal void Destroy()
        {
            try { if (canvasGO != null) UnityEngine.Object.Destroy(canvasGO); } catch { }
            canvasGO = null; rootGO = null; backdropGO = null; rootRT = null; visible = false;
        }

        private void BuildCanvas()
        {
            try
            {
                if (UIFactory.tCanvas == null) { canvasGO = null; return; }
                canvasGO = new GameObject(name + "Canvas");
                canvasGO.hideFlags = HideFlags.HideAndDontSave;
                UnityEngine.Object.DontDestroyOnLoad(canvasGO);
                var bf = BindingFlags.Public | BindingFlags.Instance;
                var cv = canvasGO.AddComponent(UIFactory.tCanvas);
                var rm = UIFactory.tCanvas.GetProperty("renderMode", bf);
                rm?.SetValue(cv, Enum.ToObject(rm.PropertyType, 0));                              // ScreenSpaceOverlay
                UIFactory.tCanvas.GetProperty("sortingOrder", bf)?.SetValue(cv, sortingOrder);
                if (UIFactory.tCanvasScaler != null)
                {
                    var sc = canvasGO.AddComponent(UIFactory.tCanvasScaler);
                    var smp = UIFactory.tCanvasScaler.GetProperty("uiScaleMode", bf);
                    if (smp != null) smp.SetValue(sc, Enum.ToObject(smp.PropertyType, 0));       // ConstantPixelSize: 1 unit = 1 px
                }
                if (raycasts && UIFactory.tGR != null) canvasGO.AddComponent(UIFactory.tGR);
                Plugin.Log.LogInfo($"[TMP-OVERLAY] created canvas {name} (order {sortingOrder}, raycasts {(raycasts ? "on" : "off")})");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[TMP-OVERLAY] canvas create failed for {name}: {ex.Message}");
                canvasGO = null;
            }
        }

        private void BuildRoot()
        {
            rootGO = null; backdropGO = null; rootRT = null; visible = false;
            try
            {
                var go = new GameObject(name);
                go.transform.SetParent(canvasGO.transform, false);
                rootRT = go.AddComponent<RectTransform>();
                rootRT.anchorMin = rootRT.anchorMax = Vector2.zero;    // screen bottom-left
                rootRT.pivot = Vector2.zero;
                rootRT.anchoredPosition = Vector2.zero;
                rootRT.sizeDelta = new Vector2(100f, 40f);
                backdropGO = UIFactory.CreatePanel("BG", go.transform, new Color(0f, 0f, 0f, 0.6f), Vector2.zero);
                SetRaycast(backdropGO, false);
                var bgRT = backdropGO.GetComponent<RectTransform>();
                if (bgRT != null)
                {
                    bgRT.anchorMin = Vector2.zero; bgRT.anchorMax = Vector2.one;
                    bgRT.offsetMin = Vector2.zero; bgRT.offsetMax = Vector2.zero;
                }
                go.SetActive(false);
                rootGO = go;
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[TMP-OVERLAY] root build failed for {name}: {ex.Message}");
                rootGO = null;
            }
        }
    }
}
