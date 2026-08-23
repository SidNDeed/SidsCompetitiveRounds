using System;
using System.Collections.Generic;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Ambient particle layer for map skins (Aug 23 "night pack": Forest
    /// Fire embers, Rainy Day rain, Moonlit stars). ONE persistent emitter on the background
    /// camera's layer, configured per skin and switched off for skins without an
    /// effect or when the vanilla backdrop is restored.
    ///
    /// <para>Why its own object and not a child of ArtHandler.m_background: every
    /// tint pass in Plugin.MapPhysicalColorPatch walks m_background's particle
    /// systems (TintArtBackground) and ArtInstance.parts[] (the wall/backdrop
    /// pass) and REWRITES their startColor — an emitter parented under either
    /// would be repainted to the sky colour on every map load. A standalone
    /// HideAndDontSave object is outside both walks, so the effect keeps its
    /// designed colours and adds nothing to the flicker surface those passes
    /// carry (docs/map-skin-color-pipeline.md §5). It is also never a
    /// ParticleSystem that the twinkle loop registered, so the 1.6s re-roll
    /// cannot touch it.</para>
    ///
    /// <para>Layer: the background camera's layer (LightCamera, cullingMask 512 =
    /// layer 9 in the shipped scene — read from the mask the tint pass recorded,
    /// never hardcoded). Drawn UNDER every wall and player by construction, so the
    /// effect can never occlude gameplay. Material: cloned from one of the sky's
    /// own particle renderers so it blends and grades exactly like the backdrop
    /// particles on that camera; unlit fallback if none is found.</para>
    ///
    /// <para>Timing: Apply is only ever called from the END of the deferred tint
    /// pass (already past MapTransitionGuardSec, learnings #45/#85) and Clear only
    /// touches this object — neither reaches into a Map-owned particle system.
    /// Player preference: the Animated Cosmetics toggle (#162) also freezes this
    /// layer — a player who turned animation off for performance gets no new
    /// emitter.</para></summary>
    internal static class MapSkinEffects
    {
        private const string GO_NAME = "SCR_MapSkinEffect";
        private static GameObject _go;
        private static ParticleSystem _ps;
        private static string _appliedSku;
        private static CustomMapColors.SkinEffect _appliedKind;
        private static Material _mat;
        private static Texture2D _dotTex, _streakTex;
        private static bool _loggedMaterial;

        /// <summary>Configure (or switch off) the effect for the skin being applied.
        /// Idempotent per (sku, kind): a repeat apply for the same skin on the next
        /// map just re-centres and keeps emitting.</summary>
        internal static void Apply(string sku)
        {
            try
            {
                var kind = CustomMapColors.GetEffect(sku);
                bool animOff = Plugin.AnimatedCosmetics != null && !Plugin.AnimatedCosmetics.Value;
                if (kind == CustomMapColors.SkinEffect.None || animOff)
                {
                    Clear(animOff ? "animated cosmetics off" : "skin has no effect");
                    return;
                }
                if (_go == null) CreateHost();
                if (_go == null || _ps == null) return;
                _go.layer = BackdropLayer();
                _go.transform.position = Vector3.zero;   // the map is centred at the origin after MapTransition.Enter

                bool same = _appliedKind == kind && string.Equals(_appliedSku, sku, StringComparison.OrdinalIgnoreCase);
                if (!same)
                {
                    Configure(kind, sku);
                    _appliedKind = kind;
                    _appliedSku = sku;
                    Plugin.Log.LogInfo($"[MAPFX] {kind} engaged for {sku} (layer {_go.layer})");
                }
                if (!_go.activeSelf) _go.SetActive(true);
                if (!_ps.isPlaying) _ps.Play(true);
                // One-shot proof line per engage: a configured emitter that
                // renders nothing (live count 0, or bounds off-view) is
                // otherwise indistinguishable from "working" in the log.
                if (!same && Plugin.Instance != null) Plugin.Instance.StartCoroutine(ReportLive(sku));
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[MAPFX] apply failed: {ex.Message}"); }
        }

        /// <summary>Stop emitting (live particles age out) — vanilla backdrop restore,
        /// a skin without an effect, or the test lever clearing.</summary>
        internal static void Clear(string why)
        {
            try
            {
                if (_go == null) { _appliedSku = null; _appliedKind = CustomMapColors.SkinEffect.None; return; }
                if (_appliedKind != CustomMapColors.SkinEffect.None)
                    Plugin.Log.LogInfo($"[MAPFX] cleared ({why})");
                if (_ps != null) _ps.Stop(true, ParticleSystemStopBehavior.StopEmitting);
                _appliedSku = null;
                _appliedKind = CustomMapColors.SkinEffect.None;
            }
            catch { }
        }

        private static System.Collections.IEnumerator ReportLive(string sku)
        {
            yield return new WaitForSecondsRealtime(2f);
            try
            {
                if (_ps == null || _go == null) yield break;
                var psr = _go.GetComponent<ParticleSystemRenderer>();
                var b = psr != null ? psr.bounds : new Bounds();
                Plugin.Log.LogInfo($"[MAPFX] live check {sku}: particles={_ps.particleCount} playing={_ps.isPlaying} emitting={_ps.isEmitting} bounds=({b.center.x:F1},{b.center.y:F1}) size=({b.size.x:F1},{b.size.y:F1}) mode={(psr != null ? psr.renderMode.ToString() : "?")} layer={_go.layer}");
            }
            catch { }
        }

        private static int BackdropLayer()
        {
            int mask = MapPhysicalColorPatch.BackdropLayerMask;
            if (mask != 0)
                for (int i = 0; i < 32; i++)
                    if ((mask & (1 << i)) != 0) return i;
            return 9;   // shipped scene: LightCamera cullingMask 512
        }

        private static void CreateHost()
        {
            _go = new GameObject(GO_NAME);
            _go.hideFlags = HideFlags.HideAndDontSave;   // survives ROUNDS' scene teardown (#16)
            _ps = _go.AddComponent<ParticleSystem>();
            _ps.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);
            var psr = _go.GetComponent<ParticleSystemRenderer>();
            if (psr != null)
            {
                psr.sortingFudge = 50f;     // furthest back within the layer
                psr.renderMode = ParticleSystemRenderMode.Billboard;
            }
        }

        /// <summary>Half extents of the visible area in world units: ROUNDS' camera is
        /// orthographic, zoomed toward Map.size (15 by default) — read the live
        /// camera when there is one, with a generous margin so edges never show.</summary>
        private static void ViewHalfExtents(out float halfW, out float halfH)
        {
            float size = 15f;
            float aspect = 16f / 9f;
            try
            {
                var cam = Camera.main;
                if (cam != null && cam.orthographic)
                {
                    size = Mathf.Max(8f, cam.orthographicSize);
                    aspect = Mathf.Max(1f, cam.aspect);
                }
            }
            catch { }
            halfH = size * 1.25f;
            halfW = size * aspect * 1.25f;
        }

        private static void Configure(CustomMapColors.SkinEffect kind, string sku)
        {
            _ps.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);
            CustomMapColors.GetEffectColors(sku, out Color c1, out Color c2);
            ViewHalfExtents(out float hw, out float hh);
            var psr = _go.GetComponent<ParticleSystemRenderer>();
            if (_mat == null) _mat = BuildMaterial();

            var main = _ps.main;
            main.simulationSpace = ParticleSystemSimulationSpace.World;
            main.playOnAwake = false;
            main.loop = true;
            main.prewarm = true;
            main.scalingMode = ParticleSystemScalingMode.Local;
            main.maxParticles = 400;

            var shape = _ps.shape;
            shape.enabled = true;
            shape.shapeType = ParticleSystemShapeType.Box;

            var emission = _ps.emission;
            emission.enabled = true;
            var vel = _ps.velocityOverLifetime;
            var noise = _ps.noise;
            var col = _ps.colorOverLifetime;
            var sol = _ps.sizeOverLifetime;

            if (kind == CustomMapColors.SkinEffect.Embers)
            {
                // Glowing motes rising from the bottom of the scene, drifting,
                // fading out before they reach the top. Sparse: ~14/s, 5-8s life.
                main.startLifetime = new ParticleSystem.MinMaxCurve(5f, 8f);
                main.startSpeed = new ParticleSystem.MinMaxCurve(1.2f, 2.6f);
                main.startSize = new ParticleSystem.MinMaxCurve(0.22f, 0.55f);
                main.startColor = new ParticleSystem.MinMaxGradient(c1, c2);
                main.gravityModifier = -0.02f;
                shape.position = new Vector3(0f, -hh, 0f);
                shape.scale = new Vector3(hw * 2f, 1f, 1f);
                shape.rotation = new Vector3(-90f, 0f, 0f);   // box emits along +Y
                emission.rateOverTime = 14f;
                vel.enabled = true;
                vel.space = ParticleSystemSimulationSpace.World;
                vel.x = new ParticleSystem.MinMaxCurve(-0.6f, 0.6f);
                vel.y = new ParticleSystem.MinMaxCurve(1.0f, 2.2f);
                // All three axes MUST share one curve mode — a lone constant z beside
                // two-constant x/y silently disables the whole module (tour-proven:
                // 350 live rain drops parked on the emission line).
                vel.z = new ParticleSystem.MinMaxCurve(0f, 0f);
                noise.enabled = true;
                noise.strength = 0.9f;
                noise.frequency = 0.25f;
                noise.scrollSpeed = 0.4f;
                noise.damping = true;
                col.enabled = true;
                var g = new Gradient();
                g.SetKeys(
                    new[] { new GradientColorKey(Color.white, 0f), new GradientColorKey(Color.white, 1f) },
                    new[] { new GradientAlphaKey(0f, 0f), new GradientAlphaKey(0.95f, 0.12f),
                            new GradientAlphaKey(0.85f, 0.6f), new GradientAlphaKey(0f, 1f) });
                col.color = new ParticleSystem.MinMaxGradient(g);
                sol.enabled = true;
                sol.size = new ParticleSystem.MinMaxCurve(1f, AnimationCurve.EaseInOut(0f, 1f, 1f, 0.35f));
                if (psr != null)
                {
                    psr.renderMode = ParticleSystemRenderMode.Billboard;
                    if (_mat != null) { _mat.mainTexture = DotTexture(); psr.material = _mat; }
                }
            }
            else if (kind == CustomMapColors.SkinEffect.Stars)
            {
                // A sparse star field over the whole view: motionless points
                // that fade in, hold, and fade out — a slow twinkle, never a
                // strobe (3-7s per star, ~10 alive per second of emission).
                main.startLifetime = new ParticleSystem.MinMaxCurve(3f, 7f);
                main.startSpeed = new ParticleSystem.MinMaxCurve(0f);
                main.startSize = new ParticleSystem.MinMaxCurve(0.16f, 0.36f);
                main.startColor = new ParticleSystem.MinMaxGradient(c1, c2);
                main.gravityModifier = 0f;
                shape.position = Vector3.zero;
                shape.scale = new Vector3(hw * 2f, hh * 2f, 1f);
                shape.rotation = Vector3.zero;
                emission.rateOverTime = 14f;
                vel.enabled = false;
                noise.enabled = false;
                col.enabled = true;
                var g = new Gradient();
                g.SetKeys(
                    new[] { new GradientColorKey(Color.white, 0f), new GradientColorKey(Color.white, 1f) },
                    new[] { new GradientAlphaKey(0f, 0f), new GradientAlphaKey(0.9f, 0.35f),
                            new GradientAlphaKey(0.9f, 0.65f), new GradientAlphaKey(0f, 1f) });
                col.color = new ParticleSystem.MinMaxGradient(g);
                sol.enabled = false;
                if (psr != null)
                {
                    psr.renderMode = ParticleSystemRenderMode.Billboard;
                    if (_mat != null) { _mat.mainTexture = DotTexture(); psr.material = _mat; }
                }
            }
            else if (kind == CustomMapColors.SkinEffect.Rain)
            {
                // Thin streaks falling fast with a slight slant across the whole
                // view; lifetime sized so every drop crosses the full height.
                float fall = 34f;
                main.startLifetime = new ParticleSystem.MinMaxCurve((hh * 2f + 4f) / fall);
                main.startSpeed = new ParticleSystem.MinMaxCurve(0f);
                main.startSize = new ParticleSystem.MinMaxCurve(0.14f, 0.22f);
                Color rain = c1; rain.a = 0.95f;
                Color rain2 = c2; rain2.a = 0.70f;
                main.startColor = new ParticleSystem.MinMaxGradient(rain, rain2);
                main.gravityModifier = 0f;
                shape.position = new Vector3(0f, hh + 2f, 0f);
                shape.scale = new Vector3(hw * 2.4f, 1f, 1f);
                shape.rotation = new Vector3(90f, 0f, 0f);
                emission.rateOverTime = 170f;
                vel.enabled = true;
                vel.space = ParticleSystemSimulationSpace.World;
                vel.x = new ParticleSystem.MinMaxCurve(-4.5f, -3.5f);
                vel.y = new ParticleSystem.MinMaxCurve(-fall, -fall * 0.85f);
                // All three axes MUST share one curve mode — a lone constant z beside
                // two-constant x/y silently disables the whole module (tour-proven:
                // 350 live rain drops parked on the emission line).
                vel.z = new ParticleSystem.MinMaxCurve(0f, 0f);
                noise.enabled = false;
                col.enabled = true;
                var g = new Gradient();
                g.SetKeys(
                    new[] { new GradientColorKey(Color.white, 0f), new GradientColorKey(Color.white, 1f) },
                    new[] { new GradientAlphaKey(0f, 0f), new GradientAlphaKey(1f, 0.08f),
                            new GradientAlphaKey(1f, 0.9f), new GradientAlphaKey(0f, 1f) });
                col.color = new ParticleSystem.MinMaxGradient(g);
                sol.enabled = false;
                if (psr != null)
                {
                    // Stretched along velocity → a streak, not a dot.
                    psr.renderMode = ParticleSystemRenderMode.Stretch;
                    psr.velocityScale = 0f;
                    psr.lengthScale = 12f;
                    if (_mat != null) { _mat.mainTexture = StreakTexture(); psr.material = _mat; }
                }
            }
            _ps.Clear(true);
        }

        /// <summary>Clone a material off the sky's own particle renderers (same
        /// shader/blend as the backdrop particles on the background camera); fall
        /// back to an unlit particle shader. Logged once so a wrong pick is visible.</summary>
        private static Material BuildMaterial()
        {
            Material baseMat = null;
            string source = "none";
            try
            {
                var ah = ArtHandler.instance;
                var bg = ah != null ? ah.m_background : null;
                if (bg != null)
                    foreach (var r in bg.GetComponentsInChildren<ParticleSystemRenderer>(true))
                        if (r != null && r.sharedMaterial != null) { baseMat = r.sharedMaterial; source = "m_background/" + r.name; break; }
                if (baseMat == null)
                    foreach (var r in UnityEngine.Object.FindObjectsOfType<ParticleSystemRenderer>())
                        if (r != null && r.sharedMaterial != null && r.gameObject.layer == BackdropLayer())
                        { baseMat = r.sharedMaterial; source = "layer/" + r.name; break; }
            }
            catch { }
            Material mat = null;
            try
            {
                if (baseMat != null) mat = new Material(baseMat);
                else
                {
                    Shader sh = Shader.Find("Particles/Standard Unlit")
                                ?? Shader.Find("Legacy Shaders/Particles/Alpha Blended")
                                ?? Shader.Find("Sprites/Default");
                    if (sh != null) { mat = new Material(sh); source = "shader/" + sh.name; }
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[MAPFX] material build failed: {ex.Message}"); }
            if (mat != null) mat.hideFlags = HideFlags.HideAndDontSave;
            if (!_loggedMaterial)
            {
                _loggedMaterial = true;
                Plugin.Log.LogInfo($"[MAPFX] material source={source} shader={(mat != null && mat.shader != null ? mat.shader.name : "null")}");
            }
            return mat;
        }

        private const int TEX = 32;

        private static Texture2D NewTex(int w, int h)
        {
            var t = new Texture2D(w, h, TextureFormat.RGBA32, false);
            t.wrapMode = TextureWrapMode.Clamp;
            t.filterMode = FilterMode.Bilinear;
            t.hideFlags = HideFlags.HideAndDontSave;
            return t;
        }

        /// <summary>Soft radial dot (white core → transparent edge).</summary>
        private static Texture2D DotTexture()
        {
            if (_dotTex != null) return _dotTex;
            var t = NewTex(TEX, TEX);
            var px = new Color[TEX * TEX];
            float c = (TEX - 1) * 0.5f, r = c;
            for (int y = 0; y < TEX; y++)
                for (int x = 0; x < TEX; x++)
                {
                    float d = Mathf.Sqrt((x - c) * (x - c) + (y - c) * (y - c)) / r;
                    float a = Mathf.Clamp01(1f - d);
                    a = a * a;
                    px[y * TEX + x] = new Color(1f, 1f, 1f, a);
                }
            t.SetPixels(px); t.Apply();
            _dotTex = t;
            return t;
        }

        /// <summary>Vertical streak: soft across X, fading at both ends of Y.</summary>
        private static Texture2D StreakTexture()
        {
            if (_streakTex != null) return _streakTex;
            const int W = 8, H = 32;
            var t = NewTex(W, H);
            var px = new Color[W * H];
            for (int y = 0; y < H; y++)
                for (int x = 0; x < W; x++)
                {
                    float fx = Mathf.Abs((x + 0.5f) / W - 0.5f) * 2f;   // 0 centre → 1 edge
                    float fy = (y + 0.5f) / H;
                    float ax = Mathf.Clamp01(1f - fx);
                    float ay = Mathf.Clamp01(Mathf.Min(fy, 1f - fy) * 4f);
                    px[y * W + x] = new Color(1f, 1f, 1f, ax * ax * ay);
                }
            t.SetPixels(px); t.Apply();
            _streakTex = t;
            return t;
        }
    }
}
