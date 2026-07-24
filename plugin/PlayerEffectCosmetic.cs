using System;
using System.Collections;
using System.Collections.Generic;
using ExitGames.Client.Photon;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Player EFFECT cosmetic (kind=player_effect). Spawns a procedural particle aura
    /// attached to the player body that follows it around during a match. Cross-visible
    /// via the Photon custom property cr_effect_sku so other mod users see it too.
    ///
    /// Lifecycle mirrors PlayerColorCosmetic exactly:
    ///   - PublishLocalProps()        on stats refresh / room join (broadcast our sku)
    ///   - OnMatchStart / OnRoundStart spawn/re-spawn auras for every player with a sku
    ///   - OnMatchEnd                  tear everything down
    ///   - OnPlayerPropertiesChanged   late-peer prop arrival → (re)spawn that actor's aura
    ///
    /// Each sku maps to a distinct ParticleSystem configuration (color, motion, lifetime,
    /// emission) + a procedurally generated sprite texture (soft dot for most, heart/clover
    /// shapes for those two). We avoid a hard ParticleSystem material dependency by cloning
    /// the material off an existing in-scene particle system (the player body blob), falling
    /// back to a Shader.Find chain. All visuals are guarded — a missing material or shader
    /// degrades to "no aura" rather than throwing.
    /// </summary>
    internal static class PlayerEffectCosmetic
    {
        private const string PROP_SKU = "cr_effect_sku";

        // actorNumber → the spawned aura GameObject (destroyed on cleanup).
        private static readonly Dictionary<int, GameObject> auraByActor = new Dictionary<int, GameObject>();
        // actorNumber → sku currently applied, so we can skip redundant re-spawns.
        private static readonly Dictionary<int, string> skuByActor = new Dictionary<int, string>();

        // Cached generated textures keyed by shape name so we build each once per session.
        private static readonly Dictionary<string, Texture2D> _texCache = new Dictionary<string, Texture2D>();
        // Cached base particle material (cloned per-aura so per-sku tint/texture don't collide).
        private static Material _baseParticleMat;
        private static bool _baseMatSearched;

        // ── Publish ─────────────────────────────────────────────────
        public static void PublishLocalProps()
        {
            try
            {
                if (!PhotonNetwork.IsConnected || PhotonNetwork.LocalPlayer == null) return;
                var s = ApiClient.CachedPlayerStats;
                var props = new ExitGames.Client.Photon.Hashtable();
                props[PROP_SKU] = s?.active_player_effect_sku ?? "";
                PhotonNetwork.LocalPlayer.SetCustomProperties(props);
                Plugin.Log.LogInfo($"[EFFECT] Published sku={props[PROP_SKU]}");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[EFFECT] PublishLocalProps failed: {ex.Message}"); }
        }

        // ── Lifecycle ───────────────────────────────────────────────
        public static void OnMatchStart()
        {
            if (Plugin.ShowPlayerColors != null && !Plugin.ShowPlayerColors.Value) return;
            try { Plugin.Instance.StartCoroutine(DelayedApplyAll()); }
            catch (Exception ex) { Plugin.Log.LogWarning($"[EFFECT] OnMatchStart error: {ex.Message}"); }
        }

        public static void OnRoundStart()
        {
            if (Plugin.ShowPlayerColors != null && !Plugin.ShowPlayerColors.Value) return;
            // Player GameObjects respawn each round — re-attach auras to the fresh bodies.
            try { Plugin.Instance.StartCoroutine(DelayedApplyAll()); }
            catch (Exception ex) { Plugin.Log.LogWarning($"[EFFECT] OnRoundStart error: {ex.Message}"); }
        }

        public static void OnMatchEnd()
        {
            foreach (var kv in auraByActor)
                try { if (kv.Value != null) UnityEngine.Object.Destroy(kv.Value); } catch { }
            auraByActor.Clear();
            skuByActor.Clear();
        }

        public static void OnShowPlayerColorsToggled()
        {
            if (Plugin.ShowPlayerColors == null) return;
            if (!Plugin.ShowPlayerColors.Value) OnMatchEnd();
            else if (GameStateWatcher.IsInMatch) OnMatchStart();
        }

        public static void OnAnimatedCosmeticsToggled()
        {
            bool animate = Plugin.AnimatedCosmetics == null || Plugin.AnimatedCosmetics.Value;
            foreach (var kv in auraByActor)
            {
                try
                {
                    var ps = kv.Value != null ? kv.Value.GetComponent<ParticleSystem>() : null;
                    if (ps == null) continue;
                    ApplyAnimationState(ps, animate);
                }
                catch { }
            }
        }

        private static void ApplyAnimationState(ParticleSystem ps, bool animate)
        {
            if (ps == null) return;
            ps.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);
            var main = ps.main;
            main.simulationSpace = animate
                ? ParticleSystemSimulationSpace.World
                : ParticleSystemSimulationSpace.Local;
            if (animate)
            {
                ps.Play(true);
            }
            else
            {
                // Local-space particles remain attached to a moving player
                // after the simulation is paused; world-space particles would
                // be left behind as a detached ghost.
                ps.Simulate(0.75f, true, true);
                ps.Pause(true);
            }
        }

        public static void OnPlayerPropertiesChanged(Photon.Realtime.Player target, ExitGames.Client.Photon.Hashtable changed)
        {
            if (target == null || changed == null) return;
            if (!changed.ContainsKey(PROP_SKU)) return;
            // Our own writes already apply via OnMatchStart — ignore the echo.
            if (PhotonNetwork.LocalPlayer != null && target.ActorNumber == PhotonNetwork.LocalPlayer.ActorNumber) return;
            try { ReapplyForActor(target.ActorNumber); } catch (Exception ex) { Plugin.Log.LogWarning($"[EFFECT] propchange failed: {ex.Message}"); }
        }

        public static void ReapplyForActor(int actor)
        {
            if (Plugin.ShowPlayerColors != null && !Plugin.ShowPlayerColors.Value) return;
            var pm = PlayerManager.instance;
            if (pm == null || pm.players == null) return;

            Photon.Realtime.Player photonPlayer = null;
            foreach (var pp in PhotonNetwork.PlayerList)
                if (pp != null && pp.ActorNumber == actor) { photonPlayer = pp; break; }
            if (photonPlayer == null || photonPlayer.CustomProperties == null) return;
            string sku = photonPlayer.CustomProperties.ContainsKey(PROP_SKU)
                ? (photonPlayer.CustomProperties[PROP_SKU]?.ToString() ?? "") : "";

            foreach (var p in pm.players)
            {
                if (p == null) continue;
                var pv = p.GetComponent<PhotonView>();
                if (pv == null || pv.OwnerActorNr != actor) continue;
                ApplyToPlayer(p.transform, actor, sku);
                return;
            }
        }

        private static IEnumerator DelayedApplyAll()
        {
            // Wait for player bodies to spawn (mirrors PlayerColorCosmetic's 30-frame wait).
            for (int i = 0; i < 30; i++) yield return null;

            var pm = PlayerManager.instance;
            if (pm == null || pm.players == null) yield break;

            foreach (var p in pm.players)
            {
                if (p == null) continue;
                var pv = p.GetComponent<PhotonView>();
                if (pv == null) continue;
                int actor = pv.OwnerActorNr;

                string sku = "";
                if (pv.IsMine)
                {
                    sku = ApiClient.CachedPlayerStats?.active_player_effect_sku ?? "";
                }
                else
                {
                    Photon.Realtime.Player photonPlayer = null;
                    foreach (var pp in PhotonNetwork.PlayerList)
                        if (pp != null && pp.ActorNumber == actor) { photonPlayer = pp; break; }
                    if (photonPlayer != null && photonPlayer.CustomProperties != null
                        && photonPlayer.CustomProperties.ContainsKey(PROP_SKU))
                        sku = photonPlayer.CustomProperties[PROP_SKU]?.ToString() ?? "";
                }
                ApplyToPlayer(p.transform, actor, sku);
            }
        }

        // ── Apply ───────────────────────────────────────────────────
        private static void ApplyToPlayer(Transform playerRoot, int actor, string sku)
        {
            if (playerRoot == null) return;

            // Tear down any prior aura for this actor first (round respawn, sku change, clear).
            if (auraByActor.TryGetValue(actor, out var old))
            {
                try { if (old != null) UnityEngine.Object.Destroy(old); } catch { }
                auraByActor.Remove(actor);
            }
            skuByActor.Remove(actor);

            if (string.IsNullOrEmpty(sku)) return;
            if (Plugin.ShowPlayerColors != null && !Plugin.ShowPlayerColors.Value) return;

            try
            {
                var go = new GameObject("cr_effect");
                go.transform.SetParent(playerRoot, false);
                go.transform.localPosition = Vector3.zero;

                var ps = go.AddComponent<ParticleSystem>();
                // Stop before configuring — Unity requires the system stopped to edit some modules.
                ps.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);

                ConfigureForSku(ps, sku);

                var psr = go.GetComponent<ParticleSystemRenderer>();
                if (psr != null)
                {
                    var mat = BuildMaterialForSku(playerRoot, sku);
                    if (mat != null) psr.material = mat;
                    psr.sortingFudge = -2f;  // draw just behind the body so the aura haloes it
                    psr.renderMode = ParticleSystemRenderMode.Billboard;
                }

                // Seed/freeze in local space when animations are disabled so
                // the static aura follows the player without simulating.
                ApplyAnimationState(ps,
                    Plugin.AnimatedCosmetics == null || Plugin.AnimatedCosmetics.Value);
                auraByActor[actor] = go;
                skuByActor[actor] = sku;
                Plugin.Log.LogInfo($"[EFFECT] Applied actor={actor} sku={sku}");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[EFFECT] ApplyToPlayer failed: {ex.Message}"); }
        }

        // ── In-shop preview (v1.31 rework — IMGUI simulation) ─────────────
        // History: the preview started as a world particle (invisible behind the
        // ScreenSpaceOverlay menu), then an isolated-layer RenderTexture pass
        // composited over the menu (v1.30) — which rendered EMPTY on real
        // machines (probe never lit), so its menu-fade fallback fired every
        // time and read as "the SCR menu goes transparent" (Sid, #67 follow-up).
        // Final form: no cameras, no layers, no canvases — a small CPU particle
        // sim drawn with GUI.DrawTexture from CompetitiveUI.DrawUI. IMGUI paints
        // after every canvas by construction, so it is always above the menu,
        // needs no fade, and behaves identically on every machine. Parameters
        // mirror ConfigureForSku 1:1 so the preview still shows what you buy.
        private static string _previewSku = "";

        public static string PreviewSku => _previewSku;

        private struct PreviewCfg
        {
            public float life, speed, size, rate, rise, gravity, orbital, radius;
            public Color start, start2;      // start2: second color of a random-between pair (void)
            public Color fadeFrom, fadeTo;   // color-over-lifetime endpoints when fade=true
            public bool twoStart, fade, rainbow, spin;
            public string shape;             // dot | heart | clover
        }

        private static PreviewCfg CfgFor(string sku)
        {
            // Defaults mirror ConfigureForSku's defaults.
            var c = new PreviewCfg
            {
                life = 1.2f, speed = 1.0f, size = 0.5f, rate = 14f,
                rise = 0f, gravity = 0f, orbital = 0f, radius = 1f,
                start = new Color(1f, 1f, 1f, 0.6f), shape = "dot",
            };
            switch (sku)
            {
                case "effect_smoke":
                    c.start = new Color(0.55f, 0.55f, 0.6f, 0.5f);
                    c.life = 2.2f; c.speed = 0.6f; c.size = 0.9f; c.rate = 10f; c.rise = 0.8f;
                    c.fade = true; c.fadeFrom = new Color(0.55f, 0.55f, 0.6f); c.fadeTo = new Color(0.7f, 0.7f, 0.75f);
                    break;
                case "effect_clover":
                    c.start = new Color(0.25f, 0.72f, 0.32f, 1f);
                    c.life = 1.8f; c.speed = 0.9f; c.size = 0.4f; c.rate = 12f;
                    c.gravity = 0.35f; c.spin = true; c.shape = "clover";
                    break;
                case "effect_hearts":
                    c.start = new Color(0.95f, 0.36f, 0.58f, 1f);
                    c.life = 1.8f; c.speed = 0.7f; c.size = 0.5f; c.rate = 9f; c.rise = 1.1f;
                    c.fade = true; c.fadeFrom = new Color(0.95f, 0.36f, 0.58f); c.fadeTo = new Color(1f, 0.55f, 0.72f);
                    c.shape = "heart";
                    break;
                case "effect_bubbles":
                    c.start = new Color(0.5f, 0.78f, 0.94f, 0.7f);
                    c.life = 2.0f; c.speed = 0.6f; c.size = 0.45f; c.rate = 11f; c.rise = 1.0f;
                    break;
                case "effect_embers":
                    c.start = new Color(0.94f, 0.47f, 0.16f, 1f);
                    c.life = 1.4f; c.speed = 1.1f; c.size = 0.25f; c.rate = 22f; c.rise = 1.5f;
                    c.fade = true; c.fadeFrom = new Color(1f, 0.6f, 0.2f); c.fadeTo = new Color(0.7f, 0.15f, 0.05f);
                    break;
                case "effect_sparks":
                    c.start = new Color(0.96f, 0.88f, 0.29f, 1f);
                    c.life = 0.7f; c.speed = 2.4f; c.size = 0.18f; c.rate = 30f; c.radius = 0.4f;
                    c.fade = true; c.fadeFrom = new Color(1f, 0.95f, 0.5f); c.fadeTo = new Color(1f, 0.6f, 0.1f);
                    break;
                case "effect_rainbow":
                    c.start = Color.white;
                    c.life = 1.6f; c.speed = 0.9f; c.size = 0.4f; c.rate = 24f; c.rise = 0.7f;
                    c.rainbow = true;
                    break;
                case "effect_void":
                    c.start = new Color(0.6f, 0.36f, 0.88f, 1f); c.start2 = new Color(0.2f, 0.78f, 0.9f, 1f);
                    c.twoStart = true;
                    c.life = 2.0f; c.speed = 0.5f; c.size = 0.45f; c.rate = 20f; c.radius = 0.9f; c.orbital = 1.4f;
                    c.fade = true; c.fadeFrom = new Color(0.6f, 0.36f, 0.88f); c.fadeTo = new Color(0.12f, 0.05f, 0.2f);
                    break;
                default:
                    c.rise = 0.8f;
                    break;
            }
            return c;
        }

        private struct SimParticle
        {
            public Vector2 pos;       // GUI pixels, y-down
            public Vector2 vel;       // px/s, y-down
            public float born, life, size, spinSpeed, startLerp;
        }

        private const int PREVIEW_MAX_PARTICLES = 220;
        private static readonly List<SimParticle> _simParticles = new List<SimParticle>();
        private static PreviewCfg _cfg;
        private static float _emitAcc;
        private static System.Random _rng = new System.Random();

        public static void TogglePreview(string sku)
        {
            if (!string.IsNullOrEmpty(_previewSku) && _previewSku == sku) { StopPreview(); return; }
            StopPreview();
            if (string.IsNullOrEmpty(sku)) return;
            _cfg = CfgFor(sku);
            _previewSku = sku;
            _emitAcc = 0f;
            Plugin.Log.LogInfo($"[EFFECT] preview started: {sku} (IMGUI sim)");
        }

        public static void StopPreview()
        {
            _previewSku = "";
            _simParticles.Clear();
            _emitAcc = 0f;
        }

        /// <summary>Called from CompetitiveUI.DrawUI (OnGUI) every frame. Simulates
        /// and draws the preview aura around the cursor while the shop preview is
        /// active. Repaint-only, draw-only (never consumes events), hard-capped.</summary>
        public static void DrawPreview()
        {
            if (string.IsNullOrEmpty(_previewSku)) return;
            if (!NativeUI.IsOpen) { StopPreview(); return; }  // menu closed with preview armed
            if (Event.current == null || Event.current.type != EventType.Repaint) return;

            try
            {
                float dt = Mathf.Clamp(Time.unscaledDeltaTime, 0f, 0.05f);
                // World→pixel scale chosen so sizes/speeds read like the in-match
                // aura at ROUNDS' standard ortho size 20 (40 world units of height).
                float px = Screen.height / 40f;
                var mouse = Input.mousePosition;
                var cursor = new Vector2(mouse.x, Screen.height - mouse.y);  // GUI y-down

                // Emit.
                _emitAcc += _cfg.rate * dt;
                int spawn = (int)_emitAcc;
                _emitAcc -= spawn;
                for (int i = 0; i < spawn && _simParticles.Count < PREVIEW_MAX_PARTICLES; i++)
                {
                    double ang = _rng.NextDouble() * Math.PI * 2.0;
                    float rr = (float)Math.Sqrt(_rng.NextDouble()) * _cfg.radius;
                    var dir = new Vector2((float)Math.Cos(ang), (float)Math.Sin(ang));
                    _simParticles.Add(new SimParticle
                    {
                        pos = cursor + dir * rr * px,
                        vel = dir * _cfg.speed * px,
                        born = Time.unscaledTime,
                        life = _cfg.life,
                        size = _cfg.size,
                        spinSpeed = _cfg.spin ? (float)(_rng.NextDouble() * 6.0 - 3.0) : 0f,
                        startLerp = _cfg.twoStart ? (float)_rng.NextDouble() : 0f,
                    });
                }

                // Simulate + draw.
                var tex = GetTextureForSku(_previewSku);
                var prevColor = GUI.color;
                var prevMatrix = GUI.matrix;
                int prevDepth = GUI.depth;
                GUI.depth = -1000;  // IMGUI: lower depth paints later = on top
                for (int i = _simParticles.Count - 1; i >= 0; i--)
                {
                    var p = _simParticles[i];
                    float age = Time.unscaledTime - p.born;
                    if (age >= p.life) { _simParticles.RemoveAt(i); continue; }
                    float t = age / p.life;

                    // Motion: rise (world +y = screen -y), gravity, orbital swirl.
                    p.vel.y += _cfg.gravity * 9.81f * px * dt;
                    var v = p.vel + new Vector2(0f, -_cfg.rise * px);
                    if (_cfg.orbital != 0f)
                    {
                        var off = p.pos - cursor;
                        // Perpendicular (screen y-down: this swirls counter-clockwise on screen).
                        v += new Vector2(off.y, -off.x) * _cfg.orbital;
                    }
                    p.pos += v * dt;
                    _simParticles[i] = p;

                    // Color over lifetime — same curves as the real system.
                    Color col;
                    float alpha;
                    if (_cfg.rainbow)
                    {
                        col = RainbowAt(t);
                        alpha = 1f - t;
                    }
                    else if (_cfg.fade)
                    {
                        col = Color.Lerp(_cfg.fadeFrom, _cfg.fadeTo, t);
                        alpha = t < 0.3f ? Mathf.Lerp(1f, 0.9f, t / 0.3f) : Mathf.Lerp(0.9f, 0f, (t - 0.3f) / 0.7f);
                        alpha *= _cfg.start.a;
                    }
                    else
                    {
                        col = _cfg.twoStart ? Color.Lerp(_cfg.start, _cfg.start2, p.startLerp) : _cfg.start;
                        alpha = _cfg.start.a;
                    }

                    float d = p.size * 2f * px;  // startSize is a radius-ish scale; billboard quad = 2x
                    var rect = new Rect(p.pos.x - d / 2f, p.pos.y - d / 2f, d, d);
                    GUI.color = new Color(col.r, col.g, col.b, alpha);
                    if (p.spinSpeed != 0f)
                    {
                        var m = GUI.matrix;
                        GUIUtility.RotateAroundPivot(p.spinSpeed * age * Mathf.Rad2Deg, p.pos);
                        GUI.DrawTexture(rect, tex);
                        GUI.matrix = m;
                    }
                    else GUI.DrawTexture(rect, tex);
                }
                GUI.color = prevColor;
                GUI.matrix = prevMatrix;
                GUI.depth = prevDepth;
            }
            catch { /* preview must never break the menu's OnGUI */ }
        }

        private static Color RainbowAt(float t)
        {
            // Same 6 stops as RainbowOverLifetime.
            Color[] stops =
            {
                new Color(1f, 0.2f, 0.2f), new Color(1f, 0.8f, 0.2f), new Color(0.3f, 1f, 0.3f),
                new Color(0.2f, 0.8f, 1f), new Color(0.5f, 0.3f, 1f), new Color(1f, 0.3f, 0.9f),
            };
            float f = Mathf.Clamp01(t) * (stops.Length - 1);
            int i = Mathf.Min((int)f, stops.Length - 2);
            return Color.Lerp(stops[i], stops[i + 1], f - i);
        }


        // ── Per-sku particle configuration ──────────────────────────
        private static void ConfigureForSku(ParticleSystem ps, string sku)
        {
            var main = ps.main;
            main.loop = true;
            main.playOnAwake = false;
            main.simulationSpace = ParticleSystemSimulationSpace.World;  // trail behind moving body
            main.scalingMode = ParticleSystemScalingMode.Local;
            main.maxParticles = 200;

            var emission = ps.emission;
            emission.enabled = true;

            var shape = ps.shape;
            shape.enabled = true;
            shape.shapeType = ParticleSystemShapeType.Sphere;
            shape.radius = 0.7f;

            // Defaults; overridden per-sku below.
            main.startLifetime = 1.2f;
            main.startSpeed = 1.0f;
            main.startSize = 0.5f;
            main.gravityModifier = 0f;
            emission.rateOverTime = 14f;
            var vel = ps.velocityOverLifetime;
            vel.enabled = false;
            var col = ps.colorOverLifetime;
            col.enabled = false;

            switch (sku)
            {
                case "effect_smoke":
                    main.startColor = new ParticleSystem.MinMaxGradient(new Color(0.55f, 0.55f, 0.6f, 0.5f));
                    main.startLifetime = 2.2f; main.startSpeed = 0.6f; main.startSize = 0.9f;
                    emission.rateOverTime = 10f;
                    EnableRise(ps, 0.8f);
                    FadeOut(ps, new Color(0.55f, 0.55f, 0.6f), new Color(0.7f, 0.7f, 0.75f));
                    break;

                case "effect_clover":
                    main.startColor = new ParticleSystem.MinMaxGradient(new Color(0.25f, 0.72f, 0.32f, 1f));
                    main.startLifetime = 1.8f; main.startSpeed = 0.9f; main.startSize = 0.4f;
                    main.gravityModifier = 0.35f;  // tumble down like falling clovers
                    emission.rateOverTime = 12f;
                    var rot = ps.rotationOverLifetime; rot.enabled = true;
                    rot.z = new ParticleSystem.MinMaxCurve(-3.0f, 3.0f);
                    break;

                case "effect_hearts":
                    main.startColor = new ParticleSystem.MinMaxGradient(new Color(0.95f, 0.36f, 0.58f, 1f));
                    main.startLifetime = 1.8f; main.startSpeed = 0.7f; main.startSize = 0.5f;
                    emission.rateOverTime = 9f;
                    EnableRise(ps, 1.1f);
                    FadeOut(ps, new Color(0.95f, 0.36f, 0.58f), new Color(1f, 0.55f, 0.72f));
                    break;

                case "effect_bubbles":
                    main.startColor = new ParticleSystem.MinMaxGradient(new Color(0.5f, 0.78f, 0.94f, 0.7f));
                    main.startLifetime = 2.0f; main.startSpeed = 0.6f; main.startSize = 0.45f;
                    emission.rateOverTime = 11f;
                    EnableRise(ps, 1.0f);
                    break;

                case "effect_embers":
                    main.startColor = new ParticleSystem.MinMaxGradient(new Color(0.94f, 0.47f, 0.16f, 1f));
                    main.startLifetime = 1.4f; main.startSpeed = 1.1f; main.startSize = 0.25f;
                    emission.rateOverTime = 22f;
                    EnableRise(ps, 1.5f);
                    FadeOut(ps, new Color(1f, 0.6f, 0.2f), new Color(0.7f, 0.15f, 0.05f));
                    break;

                case "effect_sparks":
                    main.startColor = new ParticleSystem.MinMaxGradient(new Color(0.96f, 0.88f, 0.29f, 1f));
                    main.startLifetime = 0.7f; main.startSpeed = 2.4f; main.startSize = 0.18f;
                    emission.rateOverTime = 30f;
                    shape.radius = 0.4f;
                    FadeOut(ps, new Color(1f, 0.95f, 0.5f), new Color(1f, 0.6f, 0.1f));
                    break;

                case "effect_rainbow":
                    main.startColor = new ParticleSystem.MinMaxGradient(Color.white);
                    main.startLifetime = 1.6f; main.startSpeed = 0.9f; main.startSize = 0.4f;
                    emission.rateOverTime = 24f;
                    EnableRise(ps, 0.7f);
                    RainbowOverLifetime(ps);
                    break;

                case "effect_void":
                    main.startColor = new ParticleSystem.MinMaxGradient(new Color(0.6f, 0.36f, 0.88f, 1f), new Color(0.2f, 0.78f, 0.9f, 1f));
                    main.startLifetime = 2.0f; main.startSpeed = 0.5f; main.startSize = 0.45f;
                    emission.rateOverTime = 20f;
                    shape.radius = 0.9f;
                    OrbitSwirl(ps);
                    FadeOut(ps, new Color(0.6f, 0.36f, 0.88f), new Color(0.12f, 0.05f, 0.2f));
                    break;

                default:
                    // Unknown sku → gentle white motes (still better than a hard fail).
                    main.startColor = new ParticleSystem.MinMaxGradient(new Color(1f, 1f, 1f, 0.6f));
                    EnableRise(ps, 0.8f);
                    break;
            }
        }

        private static void EnableRise(ParticleSystem ps, float speed)
        {
            var vel = ps.velocityOverLifetime;
            vel.enabled = true;
            vel.space = ParticleSystemSimulationSpace.World;
            vel.y = new ParticleSystem.MinMaxCurve(speed);
        }

        private static void OrbitSwirl(ParticleSystem ps)
        {
            var vel = ps.velocityOverLifetime;
            vel.enabled = true;
            vel.space = ParticleSystemSimulationSpace.Local;
            vel.orbitalZ = new ParticleSystem.MinMaxCurve(1.4f);
        }

        private static void FadeOut(ParticleSystem ps, Color from, Color to)
        {
            var col = ps.colorOverLifetime;
            col.enabled = true;
            var grad = new Gradient();
            grad.SetKeys(
                new[] { new GradientColorKey(from, 0f), new GradientColorKey(to, 1f) },
                new[] { new GradientAlphaKey(1f, 0f), new GradientAlphaKey(0.9f, 0.3f), new GradientAlphaKey(0f, 1f) }
            );
            col.color = new ParticleSystem.MinMaxGradient(grad);
        }

        private static void RainbowOverLifetime(ParticleSystem ps)
        {
            var col = ps.colorOverLifetime;
            col.enabled = true;
            var grad = new Gradient();
            grad.SetKeys(
                new[]
                {
                    new GradientColorKey(new Color(1f, 0.2f, 0.2f), 0.0f),
                    new GradientColorKey(new Color(1f, 0.8f, 0.2f), 0.2f),
                    new GradientColorKey(new Color(0.3f, 1f, 0.3f), 0.4f),
                    new GradientColorKey(new Color(0.2f, 0.8f, 1f), 0.6f),
                    new GradientColorKey(new Color(0.5f, 0.3f, 1f), 0.8f),
                    new GradientColorKey(new Color(1f, 0.3f, 0.9f), 1.0f),
                },
                new[] { new GradientAlphaKey(1f, 0f), new GradientAlphaKey(0f, 1f) }
            );
            col.color = new ParticleSystem.MinMaxGradient(grad);
        }

        // ── Material + texture ──────────────────────────────────────
        private static Material BuildMaterialForSku(Transform playerRoot, string sku)
        {
            try
            {
                Material baseMat = FindBaseParticleMaterial(playerRoot);
                Material mat = baseMat != null ? new Material(baseMat) : null;
                if (mat == null) return BuildUnlitPreviewMaterial(sku);
                mat.mainTexture = GetTextureForSku(sku);
                return mat;
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[EFFECT] material build failed: {ex.Message}"); return null; }
        }

        /// <summary>Self-contained unlit particle material — renders identically on
        /// any camera, including the isolated RT preview pass (no scene-lighting
        /// dependency). Sprites/Default is the always-included last resort (UI uses it).</summary>
        private static Material BuildUnlitPreviewMaterial(string sku)
        {
            try
            {
                Shader sh = Shader.Find("Particles/Standard Unlit")
                            ?? Shader.Find("Legacy Shaders/Particles/Alpha Blended")
                            ?? Shader.Find("Sprites/Default");
                if (sh == null) return null;
                var mat = new Material(sh);
                mat.mainTexture = GetTextureForSku(sku);
                return mat;
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[EFFECT] unlit material build failed: {ex.Message}"); return null; }
        }

        private static Material FindBaseParticleMaterial(Transform playerRoot)
        {
            if (_baseMatSearched && _baseParticleMat != null) return _baseParticleMat;
            _baseMatSearched = true;
            try
            {
                // Prefer a particle material off the player body itself (correct blend mode).
                if (playerRoot != null)
                {
                    var local = playerRoot.GetComponentInChildren<ParticleSystemRenderer>(true);
                    if (local != null && local.sharedMaterial != null) { _baseParticleMat = local.sharedMaterial; return _baseParticleMat; }
                }
                foreach (var r in UnityEngine.Object.FindObjectsOfType<ParticleSystemRenderer>())
                {
                    if (r != null && r.sharedMaterial != null) { _baseParticleMat = r.sharedMaterial; return _baseParticleMat; }
                }
            }
            catch { }
            return _baseParticleMat;
        }

        private static Texture2D GetTextureForSku(string sku)
        {
            string shape = (sku == "effect_hearts") ? "heart"
                         : (sku == "effect_clover") ? "clover"
                         : "dot";
            if (_texCache.TryGetValue(shape, out var cached) && cached != null) return cached;
            Texture2D tex = shape == "heart" ? BuildHeartTex()
                          : shape == "clover" ? BuildCloverTex()
                          : BuildDotTex();
            _texCache[shape] = tex;
            return tex;
        }

        private const int TEX = 32;

        private static Texture2D NewTex()
        {
            var t = new Texture2D(TEX, TEX, TextureFormat.RGBA32, false);
            t.wrapMode = TextureWrapMode.Clamp;
            t.filterMode = FilterMode.Bilinear;
            t.hideFlags = HideFlags.HideAndDontSave;
            return t;
        }

        /// <summary>Soft radial dot — white core fading to transparent edge.</summary>
        private static Texture2D BuildDotTex()
        {
            var t = NewTex();
            var px = new Color[TEX * TEX];
            float c = (TEX - 1) * 0.5f, r = c;
            for (int y = 0; y < TEX; y++)
                for (int x = 0; x < TEX; x++)
                {
                    float d = Mathf.Sqrt((x - c) * (x - c) + (y - c) * (y - c)) / r;
                    float a = Mathf.Clamp01(1f - d);
                    a = a * a;  // soften falloff
                    px[y * TEX + x] = new Color(1f, 1f, 1f, a);
                }
            t.SetPixels(px); t.Apply();
            return t;
        }

        /// <summary>White heart silhouette (implicit heart curve), transparent elsewhere.</summary>
        private static Texture2D BuildHeartTex()
        {
            var t = NewTex();
            var px = new Color[TEX * TEX];
            for (int y = 0; y < TEX; y++)
                for (int x = 0; x < TEX; x++)
                {
                    // Map to [-1,1], flip Y so the point is at the bottom.
                    float fx = (x / (float)(TEX - 1)) * 2f - 1f;
                    float fy = 1f - (y / (float)(TEX - 1)) * 2f;
                    fx *= 1.25f; fy = fy * 1.25f + 0.15f;
                    // Heart implicit: (x^2 + y^2 - 1)^3 - x^2 y^3 <= 0
                    float v = Mathf.Pow(fx * fx + fy * fy - 1f, 3f) - fx * fx * fy * fy * fy;
                    float a = v <= 0f ? 1f : 0f;
                    px[y * TEX + x] = new Color(1f, 1f, 1f, a);
                }
            t.SetPixels(px); t.Apply();
            return t;
        }

        /// <summary>Four-leaf clover: four overlapping circles around the centre.</summary>
        private static Texture2D BuildCloverTex()
        {
            var t = NewTex();
            var px = new Color[TEX * TEX];
            float c = (TEX - 1) * 0.5f;
            float lobeR = TEX * 0.26f, off = TEX * 0.20f;
            Vector2[] centers =
            {
                new Vector2(c - off, c), new Vector2(c + off, c),
                new Vector2(c, c - off), new Vector2(c, c + off),
            };
            for (int y = 0; y < TEX; y++)
                for (int x = 0; x < TEX; x++)
                {
                    float best = 1f;
                    foreach (var ce in centers)
                    {
                        float d = Mathf.Sqrt((x - ce.x) * (x - ce.x) + (y - ce.y) * (y - ce.y)) / lobeR;
                        if (d < best) best = d;
                    }
                    float a = best <= 1f ? Mathf.Clamp01(1.2f - best) : 0f;
                    px[y * TEX + x] = new Color(1f, 1f, 1f, a);
                }
            t.SetPixels(px); t.Apply();
            return t;
        }
    }
}
