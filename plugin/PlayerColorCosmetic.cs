using System;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using ExitGames.Client.Photon;
using Photon.Pun;
using Photon.Realtime;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Player body-color cosmetic. Overrides ROUNDS' default team-based orange/blue
    /// player color with a player-chosen tint. Cross-visible via Photon custom props.
    ///
    /// Photon property keys (per-Player):
    ///   cr_pcolor_sku     string (empty = use default team color)
    ///   cr_pcolor_color   string hex "#RRGGBB"
    ///
    /// Lifecycle mirrors TrailCosmetic: Plugin init publishes our props on stats refresh,
    /// match-start applies tint to every player with a sku set, and a per-frame coroutine
    /// drives the animated "prismatic" / "chrome" specials.
    ///
    /// Implementation note on the actual tint: ROUNDS uses a `PlayerSkin` MonoBehaviour
    /// (under the player GO) with a public `color` field plus particle-system color modules.
    /// Setting that field updates the body during the next frame. We reflect by name so
    /// we don't pull a hard ROUNDS-version dependency in. Fallback: walk SpriteRenderer +
    /// ParticleSystem children and tint all of them. Either path gets a visible result.
    /// </summary>
    internal static class PlayerColorCosmetic
    {
        private const string PROP_SKU   = "cr_pcolor_sku";
        private const string PROP_COLOR = "cr_pcolor_color";

        // actorNumber → state used by per-frame animated specials (prismatic etc).
        private class AnimState
        {
            public string sku;
            public Color baseColor;
            // The team-baseline color captured the FIRST time we applied to this
            // player. Cached so re-equipping mid-match (where PlayerSkin.color is
            // already our previous tint) still filters against the correct vanilla
            // value instead of, e.g., reading silver from a Chrome equip and rejecting
            // every body sprite.
            public Color teamBaseline;
            public bool baselineCaptured;
            // PlayerSkin / PlayerSkinHandler fields holding Color values that the
            // game later reads to drive renderers. Tinting them propagates without
            // having to chase every visual ourselves.
            public List<Component> tintedSkins = new List<Component>();
            public List<FieldInfo> skinColorFields = new List<FieldInfo>();
            public List<Color> originalSkinColors = new List<Color>();
            // Direct sprite tints (face, gun base, limbs) — fallback path when
            // the skin field isn't honored.
            public List<SpriteRenderer> tintedSprites = new List<SpriteRenderer>();
            public List<Color> originalSpriteColors = new List<Color>();
            // Body-blob particle systems. ROUNDS' player body is a glowing particle
            // mass; tinting the start color (+ color-over-lifetime where present)
            // re-paints the blob to our chosen color.
            public List<ParticleSystem> tintedParticles = new List<ParticleSystem>();
            public List<Color> originalParticleColors = new List<Color>();
            // Static-cosmetics mode applies one representative frame, then leaves
            // the renderers alone until animation resumes.
            public bool staticFrameApplied;
        }
        private static readonly Dictionary<int, AnimState> animByActor = new Dictionary<int, AnimState>();
        private static Coroutine animLoop;

        /// <summary>Publish our own player-color selection so other mod clients can render it.</summary>
        public static void PublishLocalProps()
        {
            try
            {
                if (!PhotonNetwork.IsConnected || PhotonNetwork.LocalPlayer == null) return;
                var s = ApiClient.CachedPlayerStats;
                var props = new ExitGames.Client.Photon.Hashtable();
                props[PROP_SKU]   = s?.active_player_color_sku ?? "";
                props[PROP_COLOR] = s?.active_player_color_hex ?? "";
                PhotonNetwork.LocalPlayer.SetCustomProperties(props);
                Plugin.Log.LogInfo($"[PCOLOR] Published sku={props[PROP_SKU]} color={props[PROP_COLOR]}");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[PCOLOR] PublishLocalProps failed: {ex.Message}"); }
        }

        public static void OnMatchStart()
        {
            if (Plugin.ShowPlayerColors != null && !Plugin.ShowPlayerColors.Value) return;
            try { Plugin.Instance.StartCoroutine(DelayedApplyAll()); }
            catch (Exception ex) { Plugin.Log.LogWarning($"[PCOLOR] OnMatchStart error: {ex.Message}"); }
        }

        /// <summary>Called from GameStateWatcher when p1Rounds + p2Rounds advances —
        /// catches sprites that spawn AFTER our initial DelayedApplyAll walk
        /// (Phoenix respawn, card effects creating new SpriteRenderers, etc.)
        /// and re-tints them. Without this, players reported seeing the native
        /// team color "leak through" their cosmetic mid-match — that's exactly
        /// these post-match-start spawned sprites we never reached on the
        /// first walk.</summary>
        public static void OnRoundStart()
        {
            if (Plugin.ShowPlayerColors != null && !Plugin.ShowPlayerColors.Value) return;
            try { Plugin.Instance.StartCoroutine(DelayedApplyAll()); }
            catch (Exception ex) { Plugin.Log.LogWarning($"[PCOLOR] OnRoundStart error: {ex.Message}"); }
        }

        public static void OnMatchEnd()
        {
            // Restore each tinted player's originals before clearing state. Match-end
            // typically destroys the player GameObjects too, but if the cosmetic is
            // toggled off mid-match this is what guarantees the visuals revert.
            foreach (var kv in animByActor)
                try { RevertOnState(kv.Value); } catch { }
            animByActor.Clear();
            if (animLoop != null && Plugin.Instance != null)
            {
                try { Plugin.Instance.StopCoroutine(animLoop); } catch { }
                animLoop = null;
            }
        }

        /// <summary>Restore one player to their pre-tint colors. Called when re-equipping
        /// (so the new baseline detection runs against vanilla state) and when the
        /// global cosmetic toggle flips off mid-match.</summary>
        public static void RevertPlayer(int actor)
        {
            if (animByActor.TryGetValue(actor, out var st))
            {
                try { RevertOnState(st); } catch { }
                animByActor.Remove(actor);
            }
        }

        /// <summary>Toggle off → revert every player. Toggle on → re-apply for everyone
        /// in the current match. Called from the Settings tab when the user flips
        /// ShowPlayerColors live.</summary>
        public static void OnShowPlayerColorsToggled()
        {
            if (Plugin.ShowPlayerColors == null) return;
            if (!Plugin.ShowPlayerColors.Value)
            {
                foreach (var kv in animByActor)
                    try { RevertOnState(kv.Value); } catch { }
                animByActor.Clear();
                if (animLoop != null && Plugin.Instance != null)
                {
                    try { Plugin.Instance.StopCoroutine(animLoop); } catch { }
                    animLoop = null;
                }
                // Also force a re-bake of every player's PlayerSkin via vanilla
                // so any tints we applied that didn't get caught by RevertOnState
                // (e.g., live SpriteRenderer.color we don't have an originals
                // backref for) get redrawn from the prefab. Mirrors the path
                // used at match start by PlayerSkinHandler.Init.
                try
                {
                    var pm = PlayerManager.instance;
                    if (pm != null && pm.players != null)
                    {
                        foreach (var p in pm.players)
                        {
                            if (p == null) continue;
                            var psh = p.GetComponentInChildren(typeof(PlayerSkinHandler), true);
                            if (psh == null) continue;
                            var initMethod = typeof(PlayerSkinHandler).GetMethod("Init",
                                BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                            initMethod?.Invoke(psh, null);
                        }
                    }
                }
                catch (Exception ex) { Plugin.Log.LogWarning($"[PCOLOR] re-bake on toggle-off failed: {ex.Message}"); }
            }
            else if (GameStateWatcher.IsInMatch)
            {
                OnMatchStart();
            }
        }

        private static void RevertOnState(AnimState st)
        {
            if (st == null) return;
            for (int i = 0; i < st.tintedSkins.Count && i < st.originalSkinColors.Count; i++)
            {
                try { st.skinColorFields[i].SetValue(st.tintedSkins[i], st.originalSkinColors[i]); }
                catch { }
            }
            for (int i = 0; i < st.tintedSprites.Count && i < st.originalSpriteColors.Count; i++)
            {
                try { if (st.tintedSprites[i] != null) st.tintedSprites[i].color = st.originalSpriteColors[i]; }
                catch { }
            }
            for (int i = 0; i < st.tintedParticles.Count && i < st.originalParticleColors.Count; i++)
            {
                try
                {
                    var ps = st.tintedParticles[i];
                    if (ps == null) continue;
                    var main = ps.main;
                    main.startColor = new ParticleSystem.MinMaxGradient(st.originalParticleColors[i]);
                }
                catch { }
            }
        }

        public static void OnPlayerPropertiesChanged(Photon.Realtime.Player target, ExitGames.Client.Photon.Hashtable changed)
        {
            if (target == null || changed == null) return;
            if (!changed.ContainsKey(PROP_SKU) && !changed.ContainsKey(PROP_COLOR)) return;
            // No reaction needed for our own writes — local apply already ran via OnMatchStart.
            if (PhotonNetwork.LocalPlayer != null && target.ActorNumber == PhotonNetwork.LocalPlayer.ActorNumber) return;
            ReapplyForActor(target.ActorNumber);
        }

        public static void ReapplyForActor(int actor)
        {
            try
            {
                var pm = PlayerManager.instance;
                if (pm == null || pm.players == null) return;

                Photon.Realtime.Player photonPlayer = null;
                foreach (var pp in PhotonNetwork.PlayerList)
                    if (pp != null && pp.ActorNumber == actor) { photonPlayer = pp; break; }
                if (photonPlayer == null || photonPlayer.CustomProperties == null) return;

                var cp = photonPlayer.CustomProperties;
                string sku = cp.ContainsKey(PROP_SKU) ? (cp[PROP_SKU]?.ToString() ?? "") : "";
                string colorHex = cp.ContainsKey(PROP_COLOR) ? (cp[PROP_COLOR]?.ToString() ?? "") : "";
                if (string.IsNullOrEmpty(sku)) return;

                foreach (var p in pm.players)
                {
                    if (p == null) continue;
                    var pv = p.GetComponent<PhotonView>();
                    if (pv == null || pv.OwnerActorNr != actor) continue;
                    ApplyToPlayer(p.transform, actor, sku, colorHex);
                    Plugin.Log.LogInfo($"[PCOLOR] Re-applied for actor={actor} (late props) sku={sku}");
                    return;
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[PCOLOR] ReapplyForActor failed: {ex.Message}"); }
        }

        private static IEnumerator DelayedApplyAll()
        {
            // Wait for player GameObjects to spawn — the player visuals (PlayerSkin)
            // attach a few frames after PlayerManager populates `players`.
            for (int i = 0; i < 30; i++) yield return null;

            var pm = PlayerManager.instance;
            if (pm == null || pm.players == null) yield break;

            animByActor.Clear();

            foreach (var p in pm.players)
            {
                if (p == null) continue;
                var pv = p.GetComponent<PhotonView>();
                if (pv == null) continue;
                int actor = pv.OwnerActorNr;

                Photon.Realtime.Player photonPlayer = null;
                foreach (var pp in PhotonNetwork.PlayerList)
                    if (pp != null && pp.ActorNumber == actor) { photonPlayer = pp; break; }

                string sku = "";
                string colorHex = "";
                if (pv.IsMine)
                {
                    var s = ApiClient.CachedPlayerStats;
                    sku = s?.active_player_color_sku ?? "";
                    colorHex = s?.active_player_color_hex ?? "";
                }
                else if (photonPlayer != null && photonPlayer.CustomProperties != null)
                {
                    var cp = photonPlayer.CustomProperties;
                    if (cp.ContainsKey(PROP_SKU))   sku      = cp[PROP_SKU]?.ToString() ?? "";
                    if (cp.ContainsKey(PROP_COLOR)) colorHex = cp[PROP_COLOR]?.ToString() ?? "";
                }
                if (string.IsNullOrEmpty(sku)) continue;
                ApplyToPlayer(p.transform, actor, sku, colorHex);
            }

            // Spin up the animation tick if any equipped sku is animated.
            bool needTick = false;
            foreach (var st in animByActor.Values)
                if (IsAnimatedSku(st.sku)) { needTick = true; break; }
            if (needTick && animLoop == null)
                animLoop = Plugin.Instance.StartCoroutine(AnimTickLoop());
        }

        private static bool IsAnimatedSku(string sku) =>
            sku == "pcolor_prismatic" || sku == "pcolor_chrome";

        /// <summary>Resolve the color, find the player's PlayerSkin component (or fallback
        /// SpriteRenderers / ParticleSystems), and apply the tint. Only tints visuals
        /// that were ORIGINALLY close to the team color — leaves the face, gun, block
        /// orb, and cosmetic trails alone (those have their own non-team colors).
        /// Caches originals on first call so re-equipping mid-match restores cleanly
        /// before applying the new tint.</summary>
        private static void ApplyToPlayer(Transform playerRoot, int actor, string sku, string colorHex)
        {
            if (playerRoot == null) return;
            // Setting off → revert any existing tint on this player and bail.
            if (Plugin.ShowPlayerColors != null && !Plugin.ShowPlayerColors.Value)
            {
                RevertPlayer(actor);
                return;
            }
            Color tint = ParseHex(colorHex, Color.white);

            // If we've already tinted this actor, restore originals first so the new
            // baseline detection runs against the vanilla colors (not our last tint).
            // Preserves the cached teamBaseline so we don't have to re-derive it.
            Color cachedBaseline = default;
            bool hadBaseline = false;
            if (animByActor.TryGetValue(actor, out var existing))
            {
                cachedBaseline = existing.teamBaseline;
                hadBaseline = existing.baselineCaptured;
                RevertOnState(existing);
            }
            var st = new AnimState { sku = sku, baseColor = tint };

            // First pass: identify the player's BASELINE team color. On a re-equip
            // we use the cached value from the previous apply (now back to vanilla
            // after RevertOnState). On a fresh apply, sniff PlayerSkin's most-saturated
            // Color field — that's the body's team color (orange-ish team 0, blue-ish
            // team 1). Used to filter what to tint vs leave alone.
            Color teamBaseline = hadBaseline ? cachedBaseline : new Color(1f, 0.5f, 0.2f);
            if (!hadBaseline)
            {
                try
                {
                    var comps = playerRoot.GetComponentsInChildren<MonoBehaviour>(true);
                    foreach (var c in comps)
                    {
                        if (c == null) continue;
                        var t = c.GetType();
                        if (t.Name != "PlayerSkin" && t.Name != "PlayerSkinHandler") continue;
                        var fields = t.GetFields(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                        Color best = teamBaseline; float bestSat = -1f;
                        foreach (var f in fields)
                        {
                            if (f.FieldType != typeof(Color)) continue;
                            try
                            {
                                var v = (Color)f.GetValue(c);
                                float sat = ColorSaturation(v);
                                if (sat > bestSat) { bestSat = sat; best = v; }
                            }
                            catch { }
                        }
                        if (bestSat > 0.2f) { teamBaseline = best; break; }
                    }
                }
                catch { }
            }
            st.teamBaseline = teamBaseline;
            st.baselineCaptured = true;

            // 1) Reflect PlayerSkin / PlayerSkinHandler. Set every Color-typed field
            //    whose existing value matches the team baseline (within 0.35 dist).
            //    That covers body/limb/secondary-tint fields and skips outline / accent
            //    colors that might be black or contrasting.
            try
            {
                var comps = playerRoot.GetComponentsInChildren<MonoBehaviour>(true);
                foreach (var c in comps)
                {
                    if (c == null) continue;
                    var t = c.GetType();
                    if (t.Name != "PlayerSkin" && t.Name != "PlayerSkinHandler") continue;
                    var fields = t.GetFields(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                    foreach (var f in fields)
                    {
                        if (f.FieldType != typeof(Color)) continue;
                        Color original;
                        try
                        {
                            original = (Color)f.GetValue(c);
                            if (!IsTeamLike(original, teamBaseline)) continue;
                        }
                        catch { continue; }
                        f.SetValue(c, tint);
                        st.tintedSkins.Add(c);
                        st.skinColorFields.Add(f);
                        st.originalSkinColors.Add(original);
                    }
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[PCOLOR] PlayerSkin tint failed: {ex.Message}"); }

            // 2) Particle systems = the body blob. Only tint particles whose START color
            //    is already close to the team baseline (skips block-orb cyan, hit-spark
            //    yellow, etc).
            try
            {
                var pss = playerRoot.GetComponentsInChildren<ParticleSystem>(true);
                foreach (var ps in pss)
                {
                    if (ps == null) continue;
                    var main = ps.main;
                    Color startC = main.startColor.color;
                    if (!IsTeamLike(startC, teamBaseline)) continue;
                    main.startColor = new ParticleSystem.MinMaxGradient(tint);
                    var col = ps.colorOverLifetime;
                    if (col.enabled)
                    {
                        var grad = new Gradient();
                        grad.SetKeys(
                            new[] { new GradientColorKey(tint, 0f), new GradientColorKey(tint, 1f) },
                            new[] { new GradientAlphaKey(1f, 0f), new GradientAlphaKey(0f, 1f) }
                        );
                        col.color = new ParticleSystem.MinMaxGradient(grad);
                    }
                    st.tintedParticles.Add(ps);
                    st.originalParticleColors.Add(startC);
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[PCOLOR] ParticleSystem tint failed: {ex.Message}"); }

            // 3) SpriteRenderer pass — only tint sprites whose existing color is close
            //    to the team baseline. Face (cream/white), gun (grey/black), block orb
            //    (cyan), cosmetic trails — all skipped.
            try
            {
                var sprs = playerRoot.GetComponentsInChildren<SpriteRenderer>(true);
                foreach (var sr in sprs)
                {
                    if (sr == null) continue;
                    var c0 = sr.color;
                    if (c0.a < 0.3f) continue;
                    if (!IsTeamLike(c0, teamBaseline)) continue;
                    sr.color = tint;
                    st.tintedSprites.Add(sr);
                    st.originalSpriteColors.Add(c0);
                }
            }
            catch { }

            animByActor[actor] = st;
            Plugin.Log.LogInfo($"[PCOLOR] Applied actor={actor} sku={sku} hex={colorHex}  baseline=({teamBaseline.r:F2},{teamBaseline.g:F2},{teamBaseline.b:F2})  skins={st.tintedSkins.Count} particles={st.tintedParticles.Count} sprites={st.tintedSprites.Count}");

            // Kick the anim loop if this is an animated sku and the loop isn't
            // already running. Previously only DelayedApplyAll started the loop,
            // so any apply via ReapplyForActor (late prop arrivals, our 2v2
            // forced reapply pass) added animByActor entries but never animated —
            // prismatic stayed stuck on the static color (white when colorHex
            // was the empty-string fallback) and chrome stayed at one shade.
            try
            {
                if (IsAnimatedSku(sku) && animLoop == null && Plugin.Instance != null)
                {
                    animLoop = Plugin.Instance.StartCoroutine(AnimTickLoop());
                    Plugin.Log.LogInfo($"[PCOLOR] Started anim tick loop (triggered by actor={actor} sku={sku})");
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[PCOLOR] anim loop start failed: {ex.Message}"); }
        }

        /// <summary>True if `c` is recognizable as a tint of `teamBaseline`. Filter
        /// criteria: must be reasonably opaque, must have meaningful saturation (so
        /// greys / whites / cream face reject), and must point in the same hue
        /// quadrant as the baseline. RGB-distance fallback catches body-shadow tints
        /// that share hue but are darker.</summary>
        private static bool IsTeamLike(Color c, Color baseline)
        {
            if (c.a < 0.2f) return false;
            float satC = ColorSaturation(c);
            float satB = ColorSaturation(baseline);
            // Reject low-sat (greys, cream, near-white).
            if (satC < 0.18f) return false;
            // Reject very dark (gun base, outlines).
            float vC = Mathf.Max(c.r, c.g, c.b);
            if (vC < 0.18f) return false;
            // Hue match: project to "warm vs cool" axis. Baseline orange = R > B,
            // baseline blue = B > R. If they diverge (e.g. baseline orange, c is
            // cyan block-orb), reject.
            bool baselineWarm = baseline.r > baseline.b;
            bool cWarm = c.r > c.b;
            if (baselineWarm != cWarm && satB > 0.2f) return false;
            // Final RGB-distance gate. Allows shadow/highlight variants of the team
            // color through but rejects unrelated hues.
            float dr = c.r - baseline.r, dg = c.g - baseline.g, db = c.b - baseline.b;
            float dist = Mathf.Sqrt(dr*dr + dg*dg + db*db);
            return dist < 0.55f;
        }

        private static float ColorSaturation(Color c)
        {
            float mx = Mathf.Max(c.r, Mathf.Max(c.g, c.b));
            float mn = Mathf.Min(c.r, Mathf.Min(c.g, c.b));
            return mx <= 0.001f ? 0f : (mx - mn) / mx;
        }

        /// <summary>Drives the animated specials (prismatic = HSV cycle, chrome = subtle
        /// shifting tint). Runs once for the whole match while at least one animated sku
        /// is equipped. ~30Hz update — cheap enough that we can avoid per-frame.</summary>
        private static IEnumerator AnimTickLoop()
        {
            var wait = new WaitForSeconds(1f / 30f);
            while (animByActor.Count > 0)
            {
                // v1.32 item 8: static-cosmetics mode freezes the animation clock —
                // prismatic/chrome render a stable representative hue instantly (and
                // resume from live time the moment the setting flips back on).
                bool animationsEnabled = Plugin.AnimatedCosmetics == null || Plugin.AnimatedCosmetics.Value;
                float now = animationsEnabled ? Time.time : 0f;
                foreach (var kv in animByActor)
                {
                    var st = kv.Value;
                    if (!IsAnimatedSku(st.sku)) continue;
                    if (!animationsEnabled && st.staticFrameApplied) continue;
                    Color c = st.baseColor;
                    if (st.sku == "pcolor_prismatic")
                    {
                        // Full hue cycle in 4 seconds.
                        float h = (now * 0.25f) % 1f;
                        c = Color.HSVToRGB(h, 0.85f, 1f);
                    }
                    else if (st.sku == "pcolor_chrome")
                    {
                        // Soft shift between two cool greys + faint blue tint.
                        float t = (Mathf.Sin(now * 0.7f) + 1f) * 0.5f;
                        c = Color.Lerp(new Color(0.78f, 0.78f, 0.86f), new Color(0.92f, 0.92f, 0.96f), t);
                    }
                    // Apply to all 3 visual layers.
                    for (int i = 0; i < st.tintedSkins.Count; i++)
                        st.skinColorFields[i].SetValue(st.tintedSkins[i], c);
                    foreach (var sr in st.tintedSprites)
                        if (sr != null) sr.color = c;
                    foreach (var ps in st.tintedParticles)
                    {
                        if (ps == null) continue;
                        var main = ps.main;
                        main.startColor = new ParticleSystem.MinMaxGradient(c);
                    }
                    st.staticFrameApplied = !animationsEnabled;
                }
                yield return wait;
            }
            animLoop = null;
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
