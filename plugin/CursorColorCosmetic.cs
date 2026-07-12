using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Cursor-color cosmetic (kind=cursor_color). Recolors the hardware mouse cursor
    /// via Cursor.SetCursor with a procedurally drawn, tinted arrow pointer. Local-only
    /// (never published over Photon — the cursor is a viewer-side thing).
    ///
    /// Cursor.SetCursor swaps the OS hardware cursor, so the tint shows everywhere the
    /// pointer is visible: the F5 menu AND in-match aiming (ROUNDS aims with the visible
    /// hardware cursor). Crucially this touches NOTHING in ROUNDS' UI / EventSystem /
    /// canvases — per the project's hard-won UI lessons, that's the only safe way to do
    /// this. If ROUNDS ever resets the cursor, a low-frequency maintenance loop re-applies.
    /// </summary>
    internal static class CursorColorCosmetic
    {
        private static string _activeSku = "";
        private static Color _activeColor = Color.white;
        private static Texture2D _activeTex;
        private static Vector2 _activeHotspot = new Vector2(1f, 1f);

        private static Coroutine _maintainLoop;
        private static bool _started;

        // Cached tinted cursor textures keyed by shape+hex so repeated equips don't rebuild.
        private static readonly Dictionary<string, Texture2D> _texCache = new Dictionary<string, Texture2D>();

        // ── Cursor SHAPE (local-only setting; the cursor is never networked) ──────────
        // Shape is a client preference (PlayerPrefs), independent of the equipped color
        // cosmetic. "default" = don't override → ROUNDS' own in-game cursor shows (Sid:
        // "I'm ok with a normal cursor as an option" + wanting the in-game one back). Any
        // other shape is drawn in the equipped cursor color (white if none equipped).
        public static readonly string[] Shapes = { "default", "arrow", "dot", "crosshair", "circle" };
        public static readonly string[] ShapeLabels = { "ROUNDS default", "Arrow", "Dot", "Crosshair", "Circle" };
        private const string SHAPE_PREF = "cr_cursor_shape";
        private static string _shape;
        public static string CurrentShape
        {
            get { if (_shape == null) _shape = LoadShape(); return _shape; }
        }
        private static string LoadShape()
        {
            try { var v = PlayerPrefs.GetString(SHAPE_PREF, "default"); return Array.IndexOf(Shapes, v) >= 0 ? v : "default"; }
            catch { return "default"; }
        }
        public static string CurrentShapeLabel()
        {
            int i = Array.IndexOf(Shapes, CurrentShape);
            return i >= 0 ? ShapeLabels[i] : "ROUNDS default";
        }
        /// <summary>Advance to the next cursor shape (Settings cycler) and re-apply.</summary>
        public static void CycleShape()
        {
            int i = Array.IndexOf(Shapes, CurrentShape);
            _shape = Shapes[(Mathf.Max(0, i) + 1) % Shapes.Length];
            try { PlayerPrefs.SetString(SHAPE_PREF, _shape); PlayerPrefs.Save(); } catch { }
            ApplyFromStats();
        }

        /// <summary>Spin up the maintenance loop once. Safe to call repeatedly; also invoked
        /// lazily from Apply() so no explicit startup wiring is required.</summary>
        public static void Initialize()
        {
            if (_started) return;
            try
            {
                if (Plugin.Instance == null) return;  // not ready yet — Apply() will retry
                _maintainLoop = Plugin.Instance.StartCoroutine(MaintainLoop());
                _started = true;
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[CURSOR] init failed: {ex.Message}"); }
        }

        /// <summary>Read the local player's equipped cursor color from cached stats and apply it.
        /// Called on every stats refresh (mirrors how trail / body-color republish).</summary>
        public static void ApplyFromStats()
        {
            var s = ApiClient.CachedPlayerStats;
            string sku = s?.active_cursor_color_sku ?? "";
            string hex = s?.active_cursor_color_hex ?? "";
            Apply(sku, hex);
        }

        /// <summary>Apply the cursor: the chosen SHAPE drawn in the equipped color. Shape
        /// "default" restores ROUNDS' own cursor (no override). Color is optional — a shape
        /// shows in white when no cursor color is equipped.</summary>
        public static void Apply(string sku, string hex)
        {
            try
            {
                if (!_started) Initialize();  // lazy-start the maintenance loop
                string shape = CurrentShape;

                if (shape == "default")
                {
                    if (string.IsNullOrEmpty(sku))
                    {
                        // No color equipped: hand the cursor back to ROUNDS/OS.
                        _activeSku = ""; _activeTex = null;
                        Cursor.SetCursor(null, Vector2.zero, CursorMode.Auto);
                        return;
                    }
                    // July 12 round 4 item 1: ROUNDS' original cursor is the Unity
                    // PLAYER-SETTINGS default cursor — no SetCursor call exists in
                    // the decompile, which is why the earlier pass wrongly concluded
                    // "no texture to recolor" and substituted our arrow. The asset
                    // is loaded at runtime though: find it, make a readable tinted
                    // copy, and the ORIGINAL shape renders in the equipped color.
                    var vanillaTinted = GetTintedVanillaCursor(hex);
                    if (vanillaTinted != null)
                    {
                        _activeSku = "default|" + (sku ?? "");
                        _activeColor = ParseHex(hex, Color.white);
                        _activeTex = vanillaTinted;
                        _activeHotspot = new Vector2(1f, 1f);
                        Cursor.SetCursor(_activeTex, _activeHotspot, CursorMode.Auto);
                        return;
                    }
                    // Couldn't locate the vanilla texture this session — fall back
                    // to the drawn arrow so the color still shows SOMEWHERE.
                    shape = "arrow";
                }

                Color c = string.IsNullOrEmpty(sku) ? Color.white : ParseHex(hex, Color.white);
                _activeSku = shape + "|" + (sku ?? "");
                _activeColor = c;
                _activeTex = GetTintedCursor(shape, hex, c);
                // Arrow points from its top-left tip; the symmetric shapes hot-spot at center.
                _activeHotspot = shape == "arrow" ? new Vector2(1f, 1f) : new Vector2(SZ / 2f, SZ / 2f);
                if (_activeTex != null)
                    Cursor.SetCursor(_activeTex, _activeHotspot, CursorMode.Auto);
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[CURSOR] Apply failed: {ex.Message}"); }
        }

        // Re-assert our cursor periodically. ROUNDS (and some menu transitions) can reset
        // the hardware cursor; a 2.5s re-apply keeps ours sticky without per-frame churn.
        private static IEnumerator MaintainLoop()
        {
            var wait = new WaitForSeconds(2.5f);
            while (true)
            {
                yield return wait;
                try
                {
                    if (!string.IsNullOrEmpty(_activeSku) && _activeTex != null)
                        Cursor.SetCursor(_activeTex, _activeHotspot, CursorMode.Auto);
                }
                catch { }
            }
        }

        private static Texture2D GetTintedCursor(string shape, string hex, Color c)
        {
            string key = shape + ":" + (string.IsNullOrEmpty(hex) ? "#FFFFFF" : hex);
            if (_texCache.TryGetValue(key, out var cached) && cached != null) return cached;
            bool[] solid = BuildShapeMask(shape);
            var tex = BuildFromMask(solid, c);
            _texCache[key] = tex;
            return tex;
        }

        // ── Vanilla cursor recolor (round 4 item 1) ────────────────────────
        // The engine-level default cursor is a texture asset in memory. Find it
        // once (small texture named like "cursor"), then tint readable copies
        // per color. The asset usually isn't CPU-readable — blit through a
        // temporary RenderTexture to copy the pixels out.
        private static Texture2D _vanillaCursor;
        private static bool _vanillaSearched;

        private static Texture2D FindVanillaCursor()
        {
            if (_vanillaSearched) return _vanillaCursor;
            _vanillaSearched = true;
            try
            {
                Texture2D best = null;
                foreach (var t in Resources.FindObjectsOfTypeAll<Texture2D>())
                {
                    if (t == null) continue;
                    string n = (t.name ?? "").ToLowerInvariant();
                    if (!n.Contains("cursor")) continue;
                    if (t.width > 128 || t.height > 128) continue;   // cursors are small
                    // Prefer the shortest matching name ("Cursor" over "CursorGlow" etc.)
                    if (best == null || t.name.Length < best.name.Length) best = t;
                }
                _vanillaCursor = best;
                Plugin.Log.LogInfo(best != null
                    ? $"[CURSOR] vanilla cursor texture: '{best.name}' {best.width}x{best.height}"
                    : "[CURSOR] no vanilla cursor texture found - default shape can't be tinted this session");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[CURSOR] vanilla search: {ex.Message}"); }
            return _vanillaCursor;
        }

        private static Texture2D GetTintedVanillaCursor(string hex)
        {
            string key = "vanilla:" + (string.IsNullOrEmpty(hex) ? "#FFFFFF" : hex);
            if (_texCache.TryGetValue(key, out var cached) && cached != null) return cached;
            var src = FindVanillaCursor();
            if (src == null) return null;
            try
            {
                // Readable copy via RT blit (the asset itself is not CPU-readable).
                var rt = RenderTexture.GetTemporary(src.width, src.height, 0, RenderTextureFormat.ARGB32);
                var prev = RenderTexture.active;
                Graphics.Blit(src, rt);
                RenderTexture.active = rt;
                var copy = new Texture2D(src.width, src.height, TextureFormat.RGBA32, false);
                copy.ReadPixels(new Rect(0, 0, src.width, src.height), 0, 0);
                RenderTexture.active = prev;
                RenderTexture.ReleaseTemporary(rt);
                copy.wrapMode = TextureWrapMode.Clamp;
                copy.filterMode = FilterMode.Bilinear;
                copy.hideFlags = HideFlags.HideAndDontSave;
                // Multiply-tint: the vanilla art is white/grey, so fill pixels take
                // the color fully while the dark outline and alpha stay intact.
                Color c = ParseHex(hex, Color.white);
                var px = copy.GetPixels32();
                for (int i = 0; i < px.Length; i++)
                {
                    px[i].r = (byte)(px[i].r * c.r);
                    px[i].g = (byte)(px[i].g * c.g);
                    px[i].b = (byte)(px[i].b * c.b);
                }
                copy.SetPixels32(px);
                copy.Apply();
                _texCache[key] = copy;
                return copy;
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[CURSOR] vanilla tint failed: {ex.Message}");
                return null;
            }
        }

        private const int SZ = 32;

        // Build the filled-pixel mask for a shape (texture space, y bottom-up).
        private static bool[] BuildShapeMask(string shape)
        {
            var solid = new bool[SZ * SZ];
            float cx = SZ / 2f, cy = SZ / 2f;
            switch (shape)
            {
                case "dot":
                {
                    float r = 4.5f;
                    for (int y = 0; y < SZ; y++) for (int x = 0; x < SZ; x++)
                    { float dx = x + 0.5f - cx, dy = y + 0.5f - cy; if (dx * dx + dy * dy <= r * r) solid[y * SZ + x] = true; }
                    break;
                }
                case "circle":
                {
                    float rO = 9f, rI = 6f;
                    for (int y = 0; y < SZ; y++) for (int x = 0; x < SZ; x++)
                    { float dx = x + 0.5f - cx, dy = y + 0.5f - cy; float d2 = dx * dx + dy * dy; if (d2 <= rO * rO && d2 >= rI * rI) solid[y * SZ + x] = true; }
                    break;
                }
                case "crosshair":
                {
                    // Classic reticle: 4 ticks + center dot, with a gap around the middle.
                    int t = 1;            // half-thickness
                    int inner = 3, outer = 11; // gap radius .. arm length
                    for (int y = 0; y < SZ; y++) for (int x = 0; x < SZ; x++)
                    {
                        float dx = x + 0.5f - cx, dy = y + 0.5f - cy;
                        bool horiz = Mathf.Abs(dy) <= t && Mathf.Abs(dx) >= inner && Mathf.Abs(dx) <= outer;
                        bool vert  = Mathf.Abs(dx) <= t && Mathf.Abs(dy) >= inner && Mathf.Abs(dy) <= outer;
                        bool dot   = dx * dx + dy * dy <= 1.6f * 1.6f;
                        if (horiz || vert || dot) solid[y * SZ + x] = true;
                    }
                    break;
                }
                default: // "arrow"
                {
                    for (int y = 0; y < SZ; y++) for (int x = 0; x < SZ; x++)
                    {
                        float fx = x / (float)(SZ - 1);
                        float fy = 1f - (y / (float)(SZ - 1)); // poly is y-down, tip at (0,0)
                        if (PointInPoly(new Vector2(fx, fy), ARROW)) solid[y * SZ + x] = true;
                    }
                    break;
                }
            }
            return solid;
        }

        // Rasterize a mask: fill = chosen color + a contrasting 1px outline so it reads on
        // any background.
        private static Texture2D BuildFromMask(bool[] solid, Color fill)
        {
            var t = new Texture2D(SZ, SZ, TextureFormat.RGBA32, false);
            t.wrapMode = TextureWrapMode.Clamp; t.filterMode = FilterMode.Bilinear; t.hideFlags = HideFlags.HideAndDontSave;
            var px = new Color[SZ * SZ];
            for (int i = 0; i < px.Length; i++) px[i] = solid[i] ? fill : new Color(0, 0, 0, 0);
            float lum = fill.r * 0.299f + fill.g * 0.587f + fill.b * 0.114f;
            Color outline = lum > 0.5f ? new Color(0.05f, 0.05f, 0.05f, 1f) : new Color(0.95f, 0.95f, 0.95f, 1f);
            var outPx = (Color[])px.Clone();
            for (int y = 0; y < SZ; y++) for (int x = 0; x < SZ; x++)
            {
                if (solid[y * SZ + x]) continue;
                bool border = false;
                for (int dy = -1; dy <= 1 && !border; dy++) for (int dx = -1; dx <= 1; dx++)
                {
                    int nx = x + dx, ny = y + dy;
                    if (nx < 0 || ny < 0 || nx >= SZ || ny >= SZ) continue;
                    if (solid[ny * SZ + nx]) { border = true; break; }
                }
                if (border) outPx[y * SZ + x] = outline;
            }
            t.SetPixels(outPx); t.Apply();
            return t;
        }

        // Classic pointer polygon in 0..1 space (y grows downward), tip at (0,0).
        private static readonly Vector2[] ARROW =
        {
            new Vector2(0.00f, 0.00f),
            new Vector2(0.00f, 0.78f),
            new Vector2(0.22f, 0.60f),
            new Vector2(0.36f, 0.92f),
            new Vector2(0.50f, 0.86f),
            new Vector2(0.34f, 0.55f),
            new Vector2(0.60f, 0.55f),
        };

        /// <summary>Rasterize the arrow: fill = chosen color, plus a 1px dark/light outline so
        /// the pointer stays visible over both light and dark backgrounds.</summary>
        private static Texture2D BuildArrowTex(Color fill)
        {
            var t = new Texture2D(SZ, SZ, TextureFormat.RGBA32, false);
            t.wrapMode = TextureWrapMode.Clamp;
            t.filterMode = FilterMode.Bilinear;
            t.hideFlags = HideFlags.HideAndDontSave;
            var px = new Color[SZ * SZ];

            // First pass: interior fill.
            bool[] solid = new bool[SZ * SZ];
            for (int y = 0; y < SZ; y++)
                for (int x = 0; x < SZ; x++)
                {
                    // Texture y is bottom-up; flip so the polygon's y-down maps correctly.
                    float fx = x / (float)(SZ - 1);
                    float fy = 1f - (y / (float)(SZ - 1));
                    bool inside = PointInPoly(new Vector2(fx, fy), ARROW);
                    solid[y * SZ + x] = inside;
                    px[y * SZ + x] = inside ? fill : new Color(0, 0, 0, 0);
                }

            // Second pass: outline any transparent pixel adjacent to a solid one.
            // Outline color contrasts the fill (dark fill → light outline, vice-versa).
            float lum = fill.r * 0.299f + fill.g * 0.587f + fill.b * 0.114f;
            Color outline = lum > 0.5f ? new Color(0.05f, 0.05f, 0.05f, 1f) : new Color(0.95f, 0.95f, 0.95f, 1f);
            var outPx = (Color[])px.Clone();
            for (int y = 0; y < SZ; y++)
                for (int x = 0; x < SZ; x++)
                {
                    if (solid[y * SZ + x]) continue;
                    bool border = false;
                    for (int dy = -1; dy <= 1 && !border; dy++)
                        for (int dx = -1; dx <= 1; dx++)
                        {
                            int nx = x + dx, ny = y + dy;
                            if (nx < 0 || ny < 0 || nx >= SZ || ny >= SZ) continue;
                            if (solid[ny * SZ + nx]) { border = true; break; }
                        }
                    if (border) outPx[y * SZ + x] = outline;
                }

            t.SetPixels(outPx);
            t.Apply();
            return t;
        }

        private static bool PointInPoly(Vector2 p, Vector2[] poly)
        {
            bool inside = false;
            int n = poly.Length;
            for (int i = 0, j = n - 1; i < n; j = i++)
            {
                if (((poly[i].y > p.y) != (poly[j].y > p.y)) &&
                    (p.x < (poly[j].x - poly[i].x) * (p.y - poly[i].y) / (poly[j].y - poly[i].y) + poly[i].x))
                    inside = !inside;
            }
            return inside;
        }

        private static Color ParseHex(string hex, Color fallback)
        {
            if (string.IsNullOrEmpty(hex)) return fallback;
            if (hex.StartsWith("#")) hex = hex.Substring(1);
            if (hex.Length != 6) return fallback;
            try
            {
                int r = Convert.ToInt32(hex.Substring(0, 2), 16);
                int g = Convert.ToInt32(hex.Substring(2, 2), 16);
                int b = Convert.ToInt32(hex.Substring(4, 2), 16);
                return new Color(r / 255f, g / 255f, b / 255f, 1f);
            }
            catch { return fallback; }
        }
    }
}
