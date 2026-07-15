using System;
using System.Collections;
using System.Collections.Generic;
using ExitGames.Client.Photon;
using Photon.Pun;
using Photon.Realtime;
using UnityEngine;

// IPunOwnershipCallbacks and IInRoomCallbacks live in Photon.Realtime; we only need the latter here.

namespace CompetitiveRounds
{
    /// <summary>
    /// Cosmetic trail system. Attaches a Unity TrailRenderer to each mod-equipped
    /// player's GameObject during a match. Cross-visibility is handled via Photon
    /// custom player properties — each mod publishes its own trail info, and all
    /// other mod clients read them to render opponents' trails.
    ///
    /// Photon property keys (per-Player):
    ///   cr_trail_sku   string (empty = no trail)
    ///   cr_trail_color string hex "#RRGGBB"
    ///   cr_trail_price int    (used to scale length: 3k=short, 5k=medium, 10k=long)
    ///
    /// Lifecycle:
    ///   Plugin init → TrailCosmetic.PublishLocalProps (called on stats refresh + consent flip)
    ///   GameStateWatcher.OnMatchStarted → TrailCosmetic.OnMatchStart → attach to every player
    ///   GameStateWatcher.ResetMatchState → TrailCosmetic.OnMatchEnd → destroy all
    ///
    /// The prismatic trail (sku == "trail_prism") runs a per-frame hue cycle so
    /// the color actually shifts, which the screenshot user saw as static before.
    /// </summary>
    internal static class TrailCosmetic
    {
        private const string PROP_SKU   = "cr_trail_sku";
        private const string PROP_COLOR = "cr_trail_color";
        private const string PROP_PRICE = "cr_trail_price";

        // actorNumber → trail GameObject (one per player currently carrying a trail).
        private static readonly Dictionary<int, GameObject> attached = new Dictionary<int, GameObject>();

        /// <summary>Publish our own trail selection to Photon so opponents can render it.
        /// Called whenever the local stats refresh, on consent flip, and on room join.</summary>
        public static void PublishLocalProps()
        {
            try
            {
                if (!PhotonNetwork.IsConnected || PhotonNetwork.LocalPlayer == null) return;
                var s = ApiClient.CachedPlayerStats;
                var props = new ExitGames.Client.Photon.Hashtable();
                props[PROP_SKU]   = s?.active_trail_sku ?? "";
                props[PROP_COLOR] = s?.active_trail_color ?? "";
                props[PROP_PRICE] = s?.active_trail_price ?? 0;
                PhotonNetwork.LocalPlayer.SetCustomProperties(props);
                Plugin.Log.LogInfo($"[TRAIL] Published local props sku={props[PROP_SKU]} color={props[PROP_COLOR]} price={props[PROP_PRICE]}");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[TRAIL] PublishLocalProps failed: {ex.Message}"); }
        }

        /// <summary>Called on match start. Attaches a trail to every player with one equipped.</summary>
        public static void OnMatchStart()
        {
            try
            {
                if (Plugin.ShowTrails != null && !Plugin.ShowTrails.Value)
                {
                    Plugin.Log.LogInfo("[TRAIL] Skipped — ShowTrails is off");
                    return;
                }
                // Give PlayerManager a moment to spawn all Player GameObjects.
                Plugin.Instance.StartCoroutine(DelayedAttachAll());
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[TRAIL] OnMatchStart error: {ex.Message}"); }
        }

        /// <summary>
        /// Called by TrailPhotonCallbacks when a player's custom properties change.
        /// Our own mod writes cr_trail_* on stats refresh, but those props may arrive at
        /// opponents' clients AFTER the opponent's OnMatchStart has already iterated players
        /// (Photon property broadcast is async). Without this hook the opponent would see the
        /// trail only starting game 2, once the props were cached. Reattach on late arrivals.
        /// </summary>
        public static void OnPlayerPropertiesChanged(Photon.Realtime.Player target, ExitGames.Client.Photon.Hashtable changed)
        {
            if (target == null || changed == null) return;
            if (!changed.ContainsKey(PROP_SKU) && !changed.ContainsKey(PROP_COLOR) && !changed.ContainsKey(PROP_PRICE))
                return;
            // We don't need to react to our own prop writes — local trail is already attached via OnMatchStart.
            if (PhotonNetwork.LocalPlayer != null && target.ActorNumber == PhotonNetwork.LocalPlayer.ActorNumber)
                return;
            ReattachForActor(target.ActorNumber);
        }

        /// <summary>Re-attach the trail for a single player by actor number. No-op outside a match
        /// (PlayerManager has no players) or if the player has no trail sku.</summary>
        public static void ReattachForActor(int actor)
        {
            try
            {
                if (Plugin.ShowTrails != null && !Plugin.ShowTrails.Value) return;
                var pm = PlayerManager.instance;
                if (pm == null || pm.players == null || pm.players.Count == 0) return;

                Photon.Realtime.Player photonPlayer = null;
                foreach (var pp in PhotonNetwork.PlayerList)
                    if (pp != null && pp.ActorNumber == actor) { photonPlayer = pp; break; }
                if (photonPlayer == null || photonPlayer.CustomProperties == null) return;

                var cp = photonPlayer.CustomProperties;
                string sku = cp.ContainsKey(PROP_SKU) ? (cp[PROP_SKU]?.ToString() ?? "") : "";
                string color = cp.ContainsKey(PROP_COLOR) ? (cp[PROP_COLOR]?.ToString() ?? "") : "";
                int price = 0;
                if (cp.ContainsKey(PROP_PRICE)) { try { price = Convert.ToInt32(cp[PROP_PRICE]); } catch { } }
                if (string.IsNullOrEmpty(sku)) return;

                foreach (var p in pm.players)
                {
                    if (p == null) continue;
                    var pv = p.GetComponent<PhotonView>();
                    if (pv == null || pv.OwnerActorNr != actor) continue;
                    AttachTrail(p.transform, actor, sku, color, price);
                    Plugin.Log.LogInfo($"[TRAIL] Re-attached for actor={actor} (late props) sku={sku}");
                    return;
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[TRAIL] ReattachForActor failed: {ex.Message}"); }
        }

        /// <summary>Called on match/room end. Destroys every trail we spawned.</summary>
        public static void OnMatchEnd()
        {
            try
            {
                foreach (var kv in attached)
                    if (kv.Value != null) UnityEngine.Object.Destroy(kv.Value);
                attached.Clear();
                Plugin.Log.LogInfo("[TRAIL] All detached");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[TRAIL] OnMatchEnd error: {ex.Message}"); }
        }

        private static IEnumerator DelayedAttachAll()
        {
            for (int i = 0; i < 30; i++) yield return null;

            var pm = PlayerManager.instance;
            if (pm == null || pm.players == null) yield break;

            foreach (var p in pm.players)
            {
                if (p == null) continue;
                var pv = p.GetComponent<PhotonView>();
                if (pv == null) continue;
                int actor = pv.OwnerActorNr;

                // Find Photon player to read properties off. Fully-qualified
                // because ROUNDS also has its own `Player` type in scope.
                Photon.Realtime.Player photonPlayer = null;
                foreach (var pp in PhotonNetwork.PlayerList)
                    if (pp != null && pp.ActorNumber == actor) { photonPlayer = pp; break; }

                string sku = "";
                string color = "";
                int price = 0;
                if (pv.IsMine)
                {
                    // Use our own cached stats (faster, and the Photon roundtrip may not have landed yet).
                    var s = ApiClient.CachedPlayerStats;
                    sku = s?.active_trail_sku ?? "";
                    color = s?.active_trail_color ?? "";
                    price = s?.active_trail_price ?? 0;
                }
                else if (photonPlayer != null && photonPlayer.CustomProperties != null)
                {
                    var cp = photonPlayer.CustomProperties;
                    if (cp.ContainsKey(PROP_SKU))   sku   = cp[PROP_SKU]?.ToString() ?? "";
                    if (cp.ContainsKey(PROP_COLOR)) color = cp[PROP_COLOR]?.ToString() ?? "";
                    if (cp.ContainsKey(PROP_PRICE))
                    {
                        try { price = Convert.ToInt32(cp[PROP_PRICE]); } catch { price = 0; }
                    }
                }

                if (string.IsNullOrEmpty(sku)) continue;
                AttachTrail(p.transform, actor, sku, color, price);
            }
        }

        private static void AttachTrail(Transform playerT, int actor, string sku, string hexColor, int price)
        {
            if (playerT == null) return;
            if (attached.TryGetValue(actor, out var existing) && existing != null)
                UnityEngine.Object.Destroy(existing);

            var go = new GameObject($"CR_Trail_{actor}_{sku}");
            go.transform.SetParent(playerT, false);
            go.transform.localPosition = Vector3.zero;

            var tr = go.AddComponent<TrailRenderer>();
            // Length scales with price: 3k tier = short, 5k = medium, 10k = long.
            float len = 0.35f;
            if (price >= 10000)     len = 0.90f;
            else if (price >= 5000) len = 0.60f;
            else if (price >= 3000) len = 0.35f;
            tr.time = len;
            tr.startWidth = 0.50f;
            tr.endWidth = 0.0f;
            tr.minVertexDistance = 0.05f;
            tr.autodestruct = false;
            tr.emitting = true;

            var mat = new Material(Shader.Find("Sprites/Default"));
            Color baseColor = Color.white;
            if (!string.IsNullOrEmpty(hexColor))
                ColorUtility.TryParseHtmlString(hexColor, out baseColor);
            // Top-tier trails use a multi-stop colorGradient and need the material to be white
            // so the gradient's own colors aren't tinted. 3k trails use the per-color material.
            Gradient grad = BuildGradientForSku(sku, baseColor);
            mat.color = grad != null ? Color.white : baseColor;
            tr.material = mat;

            if (grad != null)
                tr.colorGradient = grad;
            else
            {
                tr.startColor = baseColor;
                tr.endColor = new Color(baseColor.r, baseColor.g, baseColor.b, 0f);
            }

            attached[actor] = go;

            // Prismatic cycles hue over time — overrides whatever gradient was set above.
            if (sku == "trail_prism")
                go.AddComponent<PrismaticHueCycle>().Target = tr;

            // >3k trails with effects: Phoenix, Void, Prism (legacy) + Tride (v1.22).
            // 4k two-color gradient trails (Colossus/Ascendant/Sovereign/Titan) stay particle-free
            // per the shop description — the gradient is the effect.
            if (sku == "trail_phoenix" || sku == "trail_void" || sku == "trail_prism" || sku == "trail_tride")
                AttachParticles(go.transform, sku);

            Plugin.Log.LogInfo($"[TRAIL] Attached actor={actor} sku={sku} color={hexColor} len={len:F2}s gradient={(grad!=null?"yes":"no")}");
        }

        // Sparkle/glow particles that ride along with the trail. Configured per-SKU:
        // Phoenix = warm yellow sparks rising, Void = cold purple wisps, Prism = white sparkles.
        // Parented to the trail GO so OnMatchEnd's Destroy(go) cleans them up automatically.
        private static void AttachParticles(Transform parent, string sku)
        {
            try
            {
                var psGO = new GameObject($"CR_TrailFX_{sku}");
                psGO.transform.SetParent(parent, false);
                psGO.transform.localPosition = Vector3.zero;

                var ps = psGO.AddComponent<ParticleSystem>();
                // Configure BEFORE first Play tick: ParticleSystem auto-plays when added; if we
                // mutate modules after, the first burst uses default values for one frame.
                ps.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);

                var main = ps.main;
                main.duration = 1.0f;
                main.loop = true;
                main.startLifetime = sku == "trail_void" ? 0.7f : 0.5f;
                main.startSpeed = sku == "trail_void" ? 0.6f : 1.4f;
                main.startSize = sku == "trail_void" ? 0.18f : 0.12f;
                main.maxParticles = 80;
                main.simulationSpace = ParticleSystemSimulationSpace.World;  // particles trail behind player
                main.scalingMode = ParticleSystemScalingMode.Local;

                Color tint;
                switch (sku)
                {
                    case "trail_phoenix": tint = new Color(1f, 0.65f, 0.15f, 1f); break;
                    case "trail_void":    tint = new Color(0.6f, 0.25f, 0.95f, 1f); break;
                    case "trail_tride":   tint = new Color(0.95f, 0.78f, 0.87f, 1f); break;  // soft pink — trans palette base
                    default:              tint = new Color(1f, 1f, 1f, 1f); break;  // prism — colorOverLifetime supplies the rainbow
                }
                main.startColor = new ParticleSystem.MinMaxGradient(tint);

                var emission = ps.emission;
                emission.enabled = true;
                emission.rateOverTime = sku == "trail_void" ? 14f : 22f;

                var shape = ps.shape;
                shape.enabled = true;
                shape.shapeType = ParticleSystemShapeType.Sphere;
                shape.radius = 0.25f;

                // Fade alpha to zero over lifetime so particles don't pop out abruptly.
                var col = ps.colorOverLifetime;
                col.enabled = true;
                Gradient cg = new Gradient();
                if (sku == "trail_prism")
                {
                    cg.SetKeys(
                        new[] {
                            new GradientColorKey(Color.red, 0f),
                            new GradientColorKey(Color.yellow, 0.2f),
                            new GradientColorKey(Color.green, 0.4f),
                            new GradientColorKey(Color.cyan, 0.6f),
                            new GradientColorKey(new Color(0.55f, 0.4f, 1f), 0.8f),
                            new GradientColorKey(new Color(1f, 0.4f, 0.85f), 1f),
                        },
                        new[] { new GradientAlphaKey(0.95f, 0f), new GradientAlphaKey(0f, 1f) });
                }
                else if (sku == "trail_tride")
                {
                    // Trans flag sparkles: cyan → pink → white across particle lifetime.
                    cg.SetKeys(
                        new[] {
                            new GradientColorKey(ParseHex("#55CDFC"), 0f),
                            new GradientColorKey(ParseHex("#F7A8B8"), 0.5f),
                            new GradientColorKey(Color.white,        1f),
                        },
                        new[] { new GradientAlphaKey(0.95f, 0f), new GradientAlphaKey(0f, 1f) });
                }
                else
                {
                    cg.SetKeys(
                        new[] { new GradientColorKey(tint, 0f), new GradientColorKey(tint, 1f) },
                        new[] { new GradientAlphaKey(0.95f, 0f), new GradientAlphaKey(0f, 1f) });
                }
                col.color = new ParticleSystem.MinMaxGradient(cg);

                // Shrink particles as they age for a sparkle feel.
                var siz = ps.sizeOverLifetime;
                siz.enabled = true;
                AnimationCurve fade = new AnimationCurve(new Keyframe(0f, 1f), new Keyframe(1f, 0f));
                siz.size = new ParticleSystem.MinMaxCurve(1f, fade);

                // Use a default particle material from Sprites/Default with additive blend feel
                // — keeps it visually in-line with the trail material.
                var pr = psGO.GetComponent<ParticleSystemRenderer>();
                if (pr != null)
                {
                    var mat = new Material(Shader.Find("Sprites/Default"));
                    mat.color = Color.white;
                    pr.material = mat;
                    pr.sortingOrder = 1;
                }

                ps.Play();
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[TRAIL] AttachParticles failed for {sku}: {ex.Message}");
            }
        }

        // Per-SKU multi-stop gradients for 5k+ trails. Returns null for trails that should
        // keep the cheap single-color alpha fade (3k tier) — caller falls back to start/endColor.
        // Stops are along the trail's tail (0 = newest, 1 = oldest), with alpha fading to 0 at the tip.
        private static Gradient BuildGradientForSku(string sku, Color baseColor)
        {
            switch (sku)
            {
                case "trail_phoenix":  // Red → orange → yellow flame
                    return MakeGradient(
                        new[] { new Color(1f, 0.95f, 0.2f), new Color(1f, 0.55f, 0.1f), new Color(0.9f, 0.15f, 0.05f) },
                        new[] { 0f, 0.5f, 1f });
                case "trail_void":     // Bright purple → deep violet → pure black
                    return MakeGradient(
                        new[] { new Color(0.75f, 0.35f, 1f), new Color(0.35f, 0.05f, 0.6f), new Color(0f, 0f, 0f) },
                        new[] { 0f, 0.55f, 1f });
                case "trail_colossus":  // Icy blue → white
                    return MakeGradient(
                        new[] { ParseHex("#4CADD0"), ParseHex("#E3ECEC") },
                        new[] { 0f, 1f });
                case "trail_ascendant": // Deep green → bright jade
                    return MakeGradient(
                        new[] { ParseHex("#71FF9E"), ParseHex("#376655") },
                        new[] { 0f, 1f });
                case "trail_sovereign": // Royal purple → pale cyan
                    return MakeGradient(
                        new[] { ParseHex("#8E4CD0"), ParseHex("#B2F9FF") },
                        new[] { 0f, 1f });
                case "trail_titan":     // Dusky pink → bright red
                    return MakeGradient(
                        new[] { ParseHex("#FF4848"), ParseHex("#CC9AAB") },
                        new[] { 0f, 1f });
                case "trail_tride":     // Trans pride — alternating cyan + pink stripes.
                    // Earlier: 5 stops with white in middle → Unity TrailRenderer's gradient
                    // averaged everything into white. Now: only cyan and pink at 5 stops, so
                    // the gradient pingpongs between two distinct colors with no white melt.
                    return MakeGradient(
                        new[] { ParseHex("#5BCEFA"), ParseHex("#F5A9B8"), ParseHex("#5BCEFA"), ParseHex("#F5A9B8"), ParseHex("#5BCEFA") },
                        new[] { 0f, 0.25f, 0.5f, 0.75f, 1f });
                case "trail_prism":    // PrismaticHueCycle drives this per-frame via start/endColor — return null so it gets the 2-key path.
                    return null;
                default:
                    return null;
            }
        }

        private static Color ParseHex(string hex)
        {
            Color c = Color.white;
            ColorUtility.TryParseHtmlString(hex, out c);
            return c;
        }

        private static Gradient MakeGradient(Color[] colors, float[] times)
        {
            var g = new Gradient();
            var ck = new GradientColorKey[colors.Length];
            var ak = new GradientAlphaKey[colors.Length];
            for (int i = 0; i < colors.Length; i++)
            {
                ck[i] = new GradientColorKey(colors[i], times[i]);
                // Solid head, fading to transparent at the oldest end of the trail.
                float a = Mathf.Lerp(1f, 0f, times[i]);
                ak[i] = new GradientAlphaKey(a, times[i]);
            }
            g.SetKeys(ck, ak);
            return g;
        }
    }

    /// <summary>
    /// Registers with PhotonNetwork to receive OnPlayerPropertiesUpdate callbacks. Exists so
    /// TrailCosmetic can re-attach an opponent's trail when their cr_trail_* props arrive after
    /// the initial OnMatchStart iteration has already finished.
    /// </summary>
    internal class TrailPhotonCallbacks : MonoBehaviour, IInRoomCallbacks
    {
        void OnEnable() { try { PhotonNetwork.AddCallbackTarget(this); } catch { } }
        void OnDisable() { try { PhotonNetwork.RemoveCallbackTarget(this); } catch { } }

        public void OnPlayerPropertiesUpdate(Photon.Realtime.Player target, ExitGames.Client.Photon.Hashtable changedProps)
        {
            try { TrailCosmetic.OnPlayerPropertiesChanged(target, changedProps); } catch { }
            try { PlayerColorCosmetic.OnPlayerPropertiesChanged(target, changedProps); } catch { }
            try { PlayerEffectCosmetic.OnPlayerPropertiesChanged(target, changedProps); } catch { }
        }

        // Unused interface methods — IInRoomCallbacks requires all of them.
        public void OnPlayerEnteredRoom(Photon.Realtime.Player newPlayer) { }
        public void OnPlayerLeftRoom(Photon.Realtime.Player otherPlayer) { }
        public void OnRoomPropertiesUpdate(ExitGames.Client.Photon.Hashtable propertiesThatChanged) { }
        public void OnMasterClientSwitched(Photon.Realtime.Player newMasterClient) { }
    }

    /// <summary>Rotates a TrailRenderer's color through HSV hues every frame. Only
    /// used for trail_prism — costs nothing when not attached.</summary>
    internal class PrismaticHueCycle : MonoBehaviour
    {
        public TrailRenderer Target;
        private float t;

        void Update()
        {
            if (Target == null) return;
            // v1.32 item 8: static-cosmetics mode freezes the hue where it is.
            if (Plugin.AnimatedCosmetics == null || Plugin.AnimatedCosmetics.Value)
            {
                t += Time.deltaTime * 0.6f;  // one full hue cycle every ~1.7s
                if (t > 1f) t -= 1f;
            }
            var col = Color.HSVToRGB(t, 0.85f, 1.0f);
            Target.startColor = col;
            Target.endColor = new Color(col.r, col.g, col.b, 0f);
        }
    }

    /// <summary>
    /// Local-only trail preview that follows the mouse cursor in world space.
    /// Spawned by the Shop tab's "Preview" button; never published via Photon so
    /// other mod players don't see it. Toggled off by re-clicking the same button,
    /// switching to a different trail, or closing the F5 menu.
    /// </summary>
    /// <summary>
    /// Cursor-following trail preview rendered via uGUI dots so it draws OVER the F5 menu
    /// (the previous world-space TrailRenderer rendered behind the menu's opaque BG panel).
    ///
    /// Lives on a screen-space-overlay Canvas at sortingOrder 30001 (one above the main F5
    /// overlay's 30000) so it always appears on top. The trail is approximated as a circular
    /// buffer of small Image dots, each fading from start→end color over a short lifetime.
    /// Per-SKU colors picked to match the in-game trail's gradient feel — single-color trails
    /// get one tint, two-color get start/end pairs, multi-stop get a 3-stop sample.
    /// </summary>
    internal static class TrailPreview
    {
        private static GameObject canvasGO;
        private static GameObject previewGO;
        private static string activeSku = "";

        public static string ActiveSku => activeSku;
        public static bool IsActive => previewGO != null;

        public static void Toggle(string sku, string hexColor, int price)
        {
            if (string.IsNullOrEmpty(sku)) { Stop(); return; }
            if (activeSku == sku && previewGO != null) { Stop(); return; }
            Stop();
            Start(sku, hexColor, price);
        }

        public static void Start(string sku, string hexColor, int price)
        {
            try
            {
                Stop();
                EnsureCanvas();
                if (canvasGO == null) return;

                previewGO = new GameObject($"CR_TrailPreviewUI_{sku}");
                previewGO.transform.SetParent(canvasGO.transform, false);
                previewGO.AddComponent<RectTransform>();

                Color baseColor = Color.white;
                if (!string.IsNullOrEmpty(hexColor))
                    ColorUtility.TryParseHtmlString(hexColor, out baseColor);

                // Lifetime scales with price tier same as world trails: 3k=short, 5k=medium, 10k=long.
                float lifetime = 0.45f;
                if (price >= 10000) lifetime = 0.90f;
                else if (price >= 5000) lifetime = 0.60f;

                var fx = previewGO.AddComponent<CursorTrailUI>();
                fx.lifetime = lifetime;
                fx.dotSizeStart = 26f;
                fx.dotSizeEnd = 4f;
                fx.maxDots = 36;
                ConfigureColorsForSku(fx, sku, baseColor);

                activeSku = sku;
                Plugin.Log.LogInfo($"[TRAIL-PREVIEW] Started sku={sku} lifetime={lifetime:F2}s (uGUI)");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[TRAIL-PREVIEW] Start failed: {ex.Message}");
                Stop();
            }
        }

        public static void Stop()
        {
            if (previewGO != null)
            {
                try { UnityEngine.Object.Destroy(previewGO); } catch { }
                previewGO = null;
            }
            activeSku = "";
        }

        // Ensure a screen-space-overlay canvas exists at sortingOrder 30001 (above the F5 overlay's
        // 30000). Created once per session, kept alive across menu open/close so we don't churn.
        private static void EnsureCanvas()
        {
            if (canvasGO != null) return;
            try
            {
                canvasGO = new GameObject("CR_TrailPreviewCanvas");
                canvasGO.hideFlags = HideFlags.HideAndDontSave;
                UnityEngine.Object.DontDestroyOnLoad(canvasGO);

                if (UIFactory.tCanvas != null)
                {
                    var cv = canvasGO.AddComponent(UIFactory.tCanvas);
                    var bf = System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance;
                    var rmProp = UIFactory.tCanvas.GetProperty("renderMode", bf);
                    rmProp?.SetValue(cv, Enum.ToObject(rmProp.PropertyType, 0));     // ScreenSpaceOverlay
                    UIFactory.tCanvas.GetProperty("sortingOrder", bf)?.SetValue(cv, 30001);  // above F5's 30000
                }
                if (UIFactory.tCanvasScaler != null)
                {
                    var sc = canvasGO.AddComponent(UIFactory.tCanvasScaler);
                    var bf = System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance;
                    var smp = UIFactory.tCanvasScaler.GetProperty("uiScaleMode", bf);
                    if (smp != null) smp.SetValue(sc, Enum.ToObject(smp.PropertyType, 0));  // ConstantPixelSize
                }
                // No GraphicRaycaster — trail dots must NEVER block clicks.
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[TRAIL-PREVIEW] Canvas create failed: {ex.Message}"); }
        }

        // Pick a 3-color sample from each SKU's gradient so the dot trail roughly matches the
        // in-game look. Single-color trails (3k tier) get baseColor for all three.
        private static void ConfigureColorsForSku(CursorTrailUI fx, string sku, Color baseColor)
        {
            switch (sku)
            {
                case "trail_phoenix":
                    fx.startColor = new Color(1f, 0.95f, 0.2f);
                    fx.midColor   = new Color(1f, 0.55f, 0.1f);
                    fx.endColor   = new Color(0.9f, 0.15f, 0.05f, 0f);
                    break;
                case "trail_void":
                    fx.startColor = new Color(0.75f, 0.35f, 1f);
                    fx.midColor   = new Color(0.35f, 0.05f, 0.6f);
                    fx.endColor   = new Color(0f, 0f, 0f, 0f);
                    break;
                case "trail_colossus":
                    fx.startColor = Hex("#4CADD0"); fx.midColor = Color.Lerp(Hex("#4CADD0"), Hex("#E3ECEC"), 0.5f);
                    fx.endColor   = new Color(Hex("#E3ECEC").r, Hex("#E3ECEC").g, Hex("#E3ECEC").b, 0f);
                    break;
                case "trail_ascendant":
                    fx.startColor = Hex("#71FF9E"); fx.midColor = Color.Lerp(Hex("#71FF9E"), Hex("#376655"), 0.5f);
                    fx.endColor   = new Color(Hex("#376655").r, Hex("#376655").g, Hex("#376655").b, 0f);
                    break;
                case "trail_sovereign":
                    fx.startColor = Hex("#8E4CD0"); fx.midColor = Color.Lerp(Hex("#8E4CD0"), Hex("#B2F9FF"), 0.5f);
                    fx.endColor   = new Color(Hex("#B2F9FF").r, Hex("#B2F9FF").g, Hex("#B2F9FF").b, 0f);
                    break;
                case "trail_titan":
                    fx.startColor = Hex("#FF4848"); fx.midColor = Color.Lerp(Hex("#FF4848"), Hex("#CC9AAB"), 0.5f);
                    fx.endColor   = new Color(Hex("#CC9AAB").r, Hex("#CC9AAB").g, Hex("#CC9AAB").b, 0f);
                    break;
                case "trail_tride":
                    // Standard trans-pride cyan + pink, no white (white melted everything together
                    // last time). 8 dots per color = visible bands at typical cursor speeds.
                    fx.cycleColors = new[] {
                        Hex("#5BCEFA"), Hex("#5BCEFA"), Hex("#5BCEFA"), Hex("#5BCEFA"),
                        Hex("#5BCEFA"), Hex("#5BCEFA"), Hex("#5BCEFA"), Hex("#5BCEFA"),
                        Hex("#F5A9B8"), Hex("#F5A9B8"), Hex("#F5A9B8"), Hex("#F5A9B8"),
                        Hex("#F5A9B8"), Hex("#F5A9B8"), Hex("#F5A9B8"), Hex("#F5A9B8"),
                    };
                    fx.preserveSpawnColor = true;
                    fx.startColor = Hex("#5BCEFA"); fx.midColor = Hex("#F5A9B8");
                    fx.endColor   = new Color(0f, 0f, 0f, 0f);
                    break;
                case "trail_prism":
                    fx.cyclePrismatic = true;
                    fx.startColor = Color.red; fx.midColor = Color.white;
                    fx.endColor   = new Color(1f, 0f, 1f, 0f);
                    break;
                default:
                    fx.startColor = baseColor;
                    fx.midColor   = baseColor;
                    fx.endColor   = new Color(baseColor.r, baseColor.g, baseColor.b, 0f);
                    break;
            }
        }

        private static Color Hex(string h) { Color c = Color.white; ColorUtility.TryParseHtmlString(h, out c); return c; }
    }

    /// <summary>
    /// uGUI cursor trail. Maintains a circular buffer of dot Images that follow the cursor.
    /// Each dot uses a soft circular alpha sprite (built once at runtime) so overlapping dots
    /// blend into a smooth trail rather than a hard-edged square box. Dots are only spawned
    /// when the cursor has moved at least MIN_SPAWN_DIST pixels since the last spawn — that
    /// way a stationary cursor doesn't pile dots into a solid blob, and a fast-moving cursor
    /// gets evenly-spaced dots that read as a continuous streak.
    /// </summary>
    internal class CursorTrailUI : MonoBehaviour
    {
        public Color startColor = Color.white;
        public Color midColor   = Color.white;
        public Color endColor   = new Color(1f, 1f, 1f, 0f);
        public float lifetime = 0.5f;
        public float dotSizeStart = 28f;
        public float dotSizeEnd = 4f;
        public int maxDots = 120;
        public bool cyclePrismatic = false;
        // Optional per-spawn color cycle (for trails like Tride where multi-stop gradients blur
        // into white). When set, each spawn picks the next color in this array. Ignored when null.
        public Color[] cycleColors;
        // When true, each dot KEEPS its spawn color (only alpha fades). Without this, all dots
        // lerp toward midColor and the trail averages to whatever midColor is — Tride's per-spawn
        // colors all became white because midColor was white.
        public bool preserveSpawnColor = false;

        // Pixel distance between dot SAMPLES along the cursor path. Smaller = denser trail.
        // Cursor frame-jumps further than SAMPLE_STEP get filled in with extra dots so a fast
        // cursor doesn't leave gaps that read as "spray". 3px reads as a smooth streak.
        private const float SAMPLE_STEP = 3f;
        private const float MAX_FILL_DOTS = 30f;  // safety cap per frame

        private struct DotEntry
        {
            public GameObject go;
            public RectTransform rt;
            public Component img;
            public float spawnedAt;
            public Color spawnColor;   // captured per-dot for prism / to lerp from cleanly
            public bool active;
        }

        private DotEntry[] dots;
        private int nextSlot = 0;
        private int spawnIndex = 0;  // monotonically increases — used for cycleColors picking
        private Vector2 lastSpawnPos = new Vector2(float.NegativeInfinity, float.NegativeInfinity);
        private float prismT;

        // Cached reflection refs + the soft circular sprite — shared across all instances.
        private static System.Reflection.PropertyInfo s_imgColorProp;
        private static System.Reflection.PropertyInfo s_imgSpriteProp;
        private static System.Reflection.PropertyInfo s_imgRayProp;
        private static Sprite s_dotSprite;

        void Awake()
        {
            EnsureSprite();
            dots = new DotEntry[maxDots];
            for (int i = 0; i < maxDots; i++) dots[i] = MakeDot(i);
        }

        // 64x64 RGBA sprite with a soft radial alpha falloff. Generated once per session.
        private static void EnsureSprite()
        {
            if (s_dotSprite != null) return;
            const int sz = 64;
            var tex = new Texture2D(sz, sz, TextureFormat.RGBA32, false);
            tex.hideFlags = HideFlags.HideAndDontSave;
            tex.wrapMode = TextureWrapMode.Clamp;
            tex.filterMode = FilterMode.Bilinear;
            var px = new Color32[sz * sz];
            float cx = sz / 2f - 0.5f, cy = sz / 2f - 0.5f, r = sz / 2f;
            for (int y = 0; y < sz; y++)
            {
                for (int x = 0; x < sz; x++)
                {
                    float dx = x - cx, dy = y - cy;
                    float d = Mathf.Sqrt(dx * dx + dy * dy) / r;
                    float a = Mathf.Clamp01(1f - d);
                    a = a * a;  // squared falloff for softer edge
                    px[y * sz + x] = new Color32(255, 255, 255, (byte)(a * 255));
                }
            }
            tex.SetPixels32(px);
            tex.Apply(false, true);
            s_dotSprite = Sprite.Create(tex, new Rect(0, 0, sz, sz), new Vector2(0.5f, 0.5f), sz);
            s_dotSprite.hideFlags = HideFlags.HideAndDontSave;
        }

        private DotEntry MakeDot(int i)
        {
            var go = new GameObject($"d{i}");
            go.transform.SetParent(transform, false);
            var rt = go.AddComponent<RectTransform>();
            rt.sizeDelta = new Vector2(dotSizeStart, dotSizeStart);
            DotEntry e = new DotEntry { go = go, rt = rt, active = false };

            if (UIFactory.tImage != null)
            {
                var img = go.AddComponent(UIFactory.tImage);
                e.img = img;
                if (s_imgColorProp == null) s_imgColorProp = UIFactory.tImage.GetProperty("color",
                    System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
                if (s_imgSpriteProp == null) s_imgSpriteProp = UIFactory.tImage.GetProperty("sprite",
                    System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
                if (s_imgRayProp == null) s_imgRayProp = UIFactory.tImage.GetProperty("raycastTarget",
                    System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
                s_imgRayProp?.SetValue(img, false);  // never block clicks
                s_imgSpriteProp?.SetValue(img, s_dotSprite);
                s_imgColorProp?.SetValue(img, new Color(1, 1, 1, 0));
            }
            go.SetActive(false);
            return e;
        }

        void Update()
        {
            Vector2 cursor = Input.mousePosition;

            // Cycle prismatic hue every frame so the next-spawned dot uses elapsed-time hue
            // (not just spawn-rate hue). v1.32 item 8: frozen in static-cosmetics mode.
            if (cyclePrismatic && (Plugin.AnimatedCosmetics == null || Plugin.AnimatedCosmetics.Value))
            {
                prismT += Time.unscaledDeltaTime * 0.6f;
                if (prismT > 1f) prismT -= 1f;
            }

            // First-frame anchor — don't spawn a long line from (-inf, -inf) to the cursor.
            if (float.IsNegativeInfinity(lastSpawnPos.x))
                lastSpawnPos = cursor;

            // Interpolate the gap from last spawn to current cursor, dropping a dot every
            // SAMPLE_STEP pixels. Fast cursor movement that previously left visible blotches
            // ("spray") now reads as a smooth streak. Capped at MAX_FILL_DOTS per frame so
            // a teleport doesn't burn the whole pool in one tick.
            float dist = Vector2.Distance(lastSpawnPos, cursor);
            int samples = Mathf.Min(Mathf.FloorToInt(dist / SAMPLE_STEP), (int)MAX_FILL_DOTS);
            for (int s = 1; s <= samples; s++)
            {
                float t = (float)s / samples;
                Vector2 pos = Vector2.Lerp(lastSpawnPos, cursor, t);
                SpawnDot(pos);
            }
            if (samples > 0) lastSpawnPos = cursor;

            // Age all active dots — color lerps spawn→mid→end, size shrinks toward zero.
            for (int i = 0; i < dots.Length; i++)
            {
                if (!dots[i].active) continue;
                float age = Time.unscaledTime - dots[i].spawnedAt;
                float ageT = age / lifetime;
                if (ageT >= 1f)
                {
                    dots[i].active = false;
                    dots[i].go.SetActive(false);
                    continue;
                }
                Color c;
                if (preserveSpawnColor)
                {
                    // Keep the dot's hue, only fade alpha — important for cycle-color trails
                    // (Tride) so adjacent cyan/pink dots don't both melt into the shared midColor.
                    c = dots[i].spawnColor;
                    c.a = Mathf.Lerp(dots[i].spawnColor.a, 0f, ageT);
                }
                else
                {
                    c = (ageT < 0.5f)
                        ? Color.Lerp(dots[i].spawnColor, midColor, ageT * 2f)
                        : Color.Lerp(midColor, endColor, (ageT - 0.5f) * 2f);
                }
                s_imgColorProp?.SetValue(dots[i].img, c);
                float size = Mathf.Lerp(dotSizeStart, dotSizeEnd, ageT);
                dots[i].rt.sizeDelta = new Vector2(size, size);
            }
        }

        private void SpawnDot(Vector2 pos)
        {
            // Pick the spawn color: cycleColors[spawnIndex] if a per-spawn cycle is configured
            // (Tride uses this — pink/cyan alternating so colors stay visible), or HSV if
            // prismatic, or the configured startColor otherwise.
            Color spawnColor;
            if (cycleColors != null && cycleColors.Length > 0)
                spawnColor = cycleColors[spawnIndex % cycleColors.Length];
            else if (cyclePrismatic)
                spawnColor = Color.HSVToRGB(prismT, 0.85f, 1.0f);
            else
                spawnColor = startColor;

            var slot = dots[nextSlot];
            slot.rt.position = new Vector3(pos.x, pos.y, 0f);
            slot.rt.sizeDelta = new Vector2(dotSizeStart, dotSizeStart);
            slot.spawnedAt = Time.unscaledTime;
            slot.spawnColor = spawnColor;
            slot.active = true;
            slot.go.SetActive(true);
            s_imgColorProp?.SetValue(slot.img, spawnColor);
            dots[nextSlot] = slot;
            nextSlot = (nextSlot + 1) % dots.Length;
            spawnIndex++;
        }
    }
}
