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

                ps.Play(true);
                auraByActor[actor] = go;
                skuByActor[actor] = sku;
                Plugin.Log.LogInfo($"[EFFECT] Applied actor={actor} sku={sku}");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[EFFECT] ApplyToPlayer failed: {ex.Message}"); }
        }

        // ── In-shop preview (item 1, v1.30) ─────────────────────────
        // Mirrors the trail preview UX: the effect's particle aura follows the
        // mouse cursor while the shop is open. Same ConfigureForSku pipeline as
        // the real in-match aura, so what you see is what you buy.
        private static GameObject _previewGO;
        private static string _previewSku = "";

        public static string PreviewSku => _previewGO != null ? _previewSku : "";

        // July 12 round 2 item 10: TRUE foreground rendering. A world particle
        // can never out-sort a ScreenSpaceOverlay canvas (the 30500 sortingOrder
        // attempt was structurally dead), and the menu-fade stopgap read as the
        // menu "bugging out". So: the preview lives on an isolated free layer, a
        // dedicated camera (synced to Camera.main every frame) renders ONLY that
        // layer into a RenderTexture, and a RawImage on a 30050-sortingOrder
        // overlay canvas composites the texture ABOVE the F5 page. No raycaster
        // and raycastTarget=false, so every click passes straight through.
        private static Camera _previewCam;
        private static RenderTexture _previewRT;
        private static GameObject _previewCanvasGO;
        private static int _previewLayer = -1;
        private static bool _mainMaskAdjusted;

        public static void TogglePreview(string sku)
        {
            if (_previewGO != null && _previewSku == sku) { StopPreview(); return; }
            StopPreview();
            if (string.IsNullOrEmpty(sku)) return;
            try
            {
                var go = new GameObject("cr_effect_preview");
                go.hideFlags = HideFlags.HideAndDontSave;
                var ps = go.AddComponent<ParticleSystem>();
                ps.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);
                ConfigureForSku(ps, sku);
                var psr = go.GetComponent<ParticleSystemRenderer>();
                if (psr != null)
                {
                    var mat = BuildMaterialForSku(null, sku);
                    if (mat != null) psr.material = mat;
                    psr.renderMode = ParticleSystemRenderMode.Billboard;
                }
                go.AddComponent<EffectPreviewFollower>();
                ps.Play(true);
                _previewGO = go;
                _previewSku = sku;
                SetupForegroundPass(go);
                Plugin.Log.LogInfo($"[EFFECT] preview started: {sku}");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[EFFECT] preview failed: {ex.Message}"); }
        }

        public static void StopPreview()
        {
            if (_previewGO != null)
            {
                try { UnityEngine.Object.Destroy(_previewGO); } catch { }
                _previewGO = null;
            }
            _previewSku = "";
            TeardownForegroundPass();
            // The RT-probe fallback may have faded the menu — always restore.
            try { NativeUI.SetMenuFade(false); } catch { }
        }

        /// <summary>Round 4 item 3 ("preview shows nothing"): one second after the
        /// foreground pass starts, read a patch of the RenderTexture back and check
        /// that ANY pixel actually landed. Logs the verdict either way, and when the
        /// RT is empty falls back to fading the menu so the world-rendered aura is
        /// visible regardless of why the RT path failed on this machine.</summary>
        private static IEnumerator ProbeForegroundPass()
        {
            yield return new WaitForSecondsRealtime(1.0f);
            if (_previewGO == null || _previewRT == null || _previewCam == null) yield break;
            int lit = 0;
            bool ok = false;
            try
            {
                var prev = RenderTexture.active;
                RenderTexture.active = _previewRT;
                int px = Mathf.Min(64, _previewRT.width);
                var probe = new Texture2D(px, px, TextureFormat.RGBA32, false);
                // Read around the CURSOR's position — that's where the aura is.
                var mp = Input.mousePosition;
                int rx = Mathf.Clamp((int)mp.x - px / 2, 0, _previewRT.width - px);
                int ry = Mathf.Clamp((int)mp.y - px / 2, 0, _previewRT.height - px);
                probe.ReadPixels(new Rect(rx, ry, px, px), 0, 0);
                RenderTexture.active = prev;
                var cols = probe.GetPixels32();
                for (int i = 0; i < cols.Length; i++) if (cols[i].a > 8) lit++;
                UnityEngine.Object.Destroy(probe);
                ok = true;
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[EFFECT-FG] probe failed: {ex.Message}"); }
            if (!ok || _previewGO == null) yield break;
            if (lit > 0)
            {
                Plugin.Log.LogInfo($"[EFFECT-FG] probe OK - {lit} lit pixels near cursor, foreground pass rendering");
            }
            else
            {
                Plugin.Log.LogWarning("[EFFECT-FG] probe EMPTY - RT pass rendered nothing; falling back to menu fade "
                    + $"(cam={( _previewCam != null ? "ok" : "null")} main={(Camera.main != null ? Camera.main.name : "NULL")})");
                try { NativeUI.SetMenuFade(true); } catch { }
            }
        }

        private static int PickFreeLayer()
        {
            // Unnamed layers are unused by ROUNDS' curated layer list; take the
            // highest one so we're far from gameplay layers.
            for (int i = 31; i >= 8; i--)
                if (string.IsNullOrEmpty(LayerMask.LayerToName(i))) return i;
            return -1;
        }

        private static void SetupForegroundPass(GameObject previewGO)
        {
            try
            {
                if (_previewLayer < 0) _previewLayer = PickFreeLayer();
                if (_previewLayer < 0)
                {
                    Plugin.Log.LogWarning("[EFFECT] no free layer — preview stays world-rendered (behind menu)");
                    return;
                }
                previewGO.layer = _previewLayer;
                foreach (var t in previewGO.GetComponentsInChildren<Transform>(true))
                    t.gameObject.layer = _previewLayer;

                // Keep the preview OUT of the main camera's own pass so it doesn't
                // ALSO render behind the menu. Restored on teardown.
                var main = Camera.main;
                if (main != null && (main.cullingMask & (1 << _previewLayer)) != 0)
                {
                    main.cullingMask &= ~(1 << _previewLayer);
                    _mainMaskAdjusted = true;
                }

                _previewRT = new RenderTexture(Screen.width, Screen.height, 0, RenderTextureFormat.ARGB32);
                _previewRT.name = "cr_effect_preview_rt";

                var camGO = new GameObject("cr_effect_preview_cam");
                camGO.hideFlags = HideFlags.HideAndDontSave;
                _previewCam = camGO.AddComponent<Camera>();
                _previewCam.clearFlags = CameraClearFlags.SolidColor;
                _previewCam.backgroundColor = new Color(0f, 0f, 0f, 0f);
                _previewCam.cullingMask = 1 << _previewLayer;
                _previewCam.orthographic = true;
                _previewCam.targetTexture = _previewRT;
                _previewCam.allowHDR = false;
                _previewCam.useOcclusionCulling = false;
                SyncPreviewCam();

                // Overlay canvas + RawImage, TrailPreview's reflection idiom
                // (no UI-assembly references, learning #15).
                _previewCanvasGO = new GameObject("CR_EffectPreviewCanvas");
                _previewCanvasGO.hideFlags = HideFlags.HideAndDontSave;
                UnityEngine.Object.DontDestroyOnLoad(_previewCanvasGO);
                var bf = System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance;
                if (UIFactory.tCanvas == null) return;
                var cv = _previewCanvasGO.AddComponent(UIFactory.tCanvas);
                var rmProp = UIFactory.tCanvas.GetProperty("renderMode", bf);
                rmProp?.SetValue(cv, Enum.ToObject(rmProp.PropertyType, 0));   // ScreenSpaceOverlay
                UIFactory.tCanvas.GetProperty("sortingOrder", bf)?.SetValue(cv, 30050);
                var imgGO = new GameObject("RT");
                imgGO.transform.SetParent(_previewCanvasGO.transform, false);
                var imgRT = imgGO.AddComponent<RectTransform>();
                imgRT.anchorMin = Vector2.zero; imgRT.anchorMax = Vector2.one;
                imgRT.offsetMin = Vector2.zero; imgRT.offsetMax = Vector2.zero;
                var tRaw = FindRawImageType();
                if (tRaw == null) { Plugin.Log.LogWarning("[EFFECT] RawImage type missing — preview stays world-rendered"); return; }
                var raw = imgGO.AddComponent(tRaw);
                tRaw.GetProperty("texture", bf)?.SetValue(raw, _previewRT);
                tRaw.GetProperty("raycastTarget", bf)?.SetValue(raw, false);
                Plugin.Log.LogInfo($"[EFFECT-FG] pass up: layer={_previewLayer} rt={_previewRT.width}x{_previewRT.height} "
                    + $"main={(main != null ? main.name : "NULL")} mainOrtho={(main != null && main.orthographic ? main.orthographicSize.ToString("F1") : "-")}");
                if (Plugin.Instance != null) Plugin.Instance.StartCoroutine(ProbeForegroundPass());
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[EFFECT-FG] setup failed: {ex.Message} - falling back to menu fade");
                TeardownForegroundPass();
                // Put the preview back where the main camera can see it and fade
                // the menu — degraded but always visible.
                try
                {
                    if (previewGO != null)
                        foreach (var t in previewGO.GetComponentsInChildren<Transform>(true))
                            t.gameObject.layer = 0;
                }
                catch { }
                try { NativeUI.SetMenuFade(true); } catch { }
            }
        }

        /// <summary>Mirror the main camera every frame so cursor-following world
        /// positions land on the same screen pixels in the RT pass.</summary>
        internal static void SyncPreviewCam()
        {
            try
            {
                var main = Camera.main;
                if (_previewCam == null || main == null) return;
                _previewCam.transform.position = main.transform.position;
                _previewCam.transform.rotation = main.transform.rotation;
                _previewCam.orthographic = main.orthographic;
                _previewCam.orthographicSize = main.orthographicSize;
                _previewCam.fieldOfView = main.fieldOfView;
                _previewCam.nearClipPlane = main.nearClipPlane;
                _previewCam.farClipPlane = main.farClipPlane;
            }
            catch { }
        }

        private static void TeardownForegroundPass()
        {
            try
            {
                if (_mainMaskAdjusted && Camera.main != null && _previewLayer >= 0)
                    Camera.main.cullingMask |= (1 << _previewLayer);
                _mainMaskAdjusted = false;
                if (_previewCam != null) { _previewCam.targetTexture = null; UnityEngine.Object.Destroy(_previewCam.gameObject); _previewCam = null; }
                if (_previewRT != null) { _previewRT.Release(); UnityEngine.Object.Destroy(_previewRT); _previewRT = null; }
                if (_previewCanvasGO != null) { UnityEngine.Object.Destroy(_previewCanvasGO); _previewCanvasGO = null; }
            }
            catch { }
        }

        private static Type _tRawImage;
        private static bool _rawSearched;
        private static Type FindRawImageType()
        {
            if (_rawSearched) return _tRawImage;
            _rawSearched = true;
            foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
            {
                var t = asm.GetType("UnityEngine.UI.RawImage");
                if (t != null) { _tRawImage = t; break; }
            }
            return _tRawImage;
        }

        /// <summary>Follows the mouse in world space; self-destructs when the F5
        /// menu closes so a forgotten preview can't leak into gameplay. Also keeps
        /// the foreground-pass camera mirrored to the main camera (item 10).</summary>
        private class EffectPreviewFollower : MonoBehaviour
        {
            private void Update()
            {
                try
                {
                    if (!NativeUI.IsOpen) { PlayerEffectCosmetic.StopPreview(); return; }
                    var cam = Camera.main;
                    if (cam == null) return;
                    var mp = Input.mousePosition;
                    mp.z = Mathf.Abs(cam.transform.position.z) > 0.5f
                        ? Mathf.Abs(cam.transform.position.z) : 10f;
                    transform.position = cam.ScreenToWorldPoint(mp);
                    PlayerEffectCosmetic.SyncPreviewCam();
                }
                catch { }
            }
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
                if (mat == null)
                {
                    Shader sh = Shader.Find("Particles/Standard Unlit")
                                ?? Shader.Find("Legacy Shaders/Particles/Alpha Blended")
                                ?? Shader.Find("Sprites/Default");
                    if (sh == null) return null;
                    mat = new Material(sh);
                }
                mat.mainTexture = GetTextureForSku(sku);
                return mat;
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[EFFECT] material build failed: {ex.Message}"); return null; }
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
