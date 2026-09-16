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
            // A portrait rig: the animation clock is held at 0 whatever the
            // animated-cosmetics setting says, so a capture never depends on
            // when it was taken.
            public bool clockPinned;
            // The ApplyForPortrait call that created this state (0 for a live
            // player's): a capture checks it is reading its own application.
            public int portraitToken;
            // Tint passes of ApplyToPlayer that threw part-way (their targets
            // are then a partial list).
            public int passFailures;
            // Targets the last static (clock 0) frame wrote; -1 before one ran.
            public int frameWrites = -1;
        }
        private static readonly Dictionary<int, AnimState> animByActor = new Dictionary<int, AnimState>();
        // AnimTickLoop's handle and the behaviour it runs on. Unity stops a
        // coroutine when its behaviour is destroyed, without running the rest of
        // the loop, so the handle alone stays set after its loop is gone:
        // OnHostDestroyed clears it for the destroyed behaviour, and a loop is
        // only taken as running while its behaviour is not destroyed. Each start
        // has its own generation, so a loop that ends clears the handle only
        // while no later loop has been started.
        private static Coroutine animLoop;
        private static MonoBehaviour animLoopHost;
        private static int animLoopGen;

        /// <summary>Starts AnimTickLoop on Plugin.Instance when an animated
        /// state exists and no loop runs on a behaviour that is not destroyed.</summary>
        private static void EnsureAnimLoop(string why)
        {
            if (animLoop != null && animLoopHost != null) return;
            if (Plugin.Instance == null) return;
            bool need = false;
            foreach (var st in animByActor.Values)
                if (st != null && IsAnimatedSku(st.sku)) { need = true; break; }
            if (!need) return;
            int gen = ++animLoopGen;
            animLoopHost = Plugin.Instance;
            animLoop = Plugin.Instance.StartCoroutine(AnimTickLoop(gen));
            Plugin.Log.LogInfo($"[PCOLOR] Started anim tick loop ({why})");
        }

        /// <summary>Stops AnimTickLoop, on the behaviour that runs it, and
        /// forgets its handle.</summary>
        private static void StopAnimLoop()
        {
            if (animLoop != null && animLoopHost != null)
            {
                try { animLoopHost.StopCoroutine(animLoop); } catch { }
            }
            animLoop = null;
            animLoopHost = null;
        }

        /// <summary>The plugin's coroutine host is being destroyed (Plugin.cs
        /// OnDestroy): the coroutines it runs stop with it, so the deferred
        /// applies recorded on it are forgotten (they no longer hold back a
        /// later request for those actors) and a loop it runs has its handle
        /// cleared. Compared by reference, so it answers from inside the host's
        /// own OnDestroy.</summary>
        internal static void OnHostDestroyed(MonoBehaviour host)
        {
            if (ReferenceEquals(host, null)) return;
            var stopped = new List<int>();
            foreach (var kv in _pendingInactiveApplies)
                if (ReferenceEquals(kv.Value.host, host)) stopped.Add(kv.Key);
            foreach (var actor in stopped) _pendingInactiveApplies.Remove(actor);
            if (!ReferenceEquals(animLoopHost, host)) return;
            animLoop = null;
            animLoopHost = null;
        }

        /// <summary>The plugin's coroutine host was respawned (Plugin.cs
        /// OnDestroy, after Plugin.Instance names the new host): the animated
        /// states are animated again from it.</summary>
        internal static void OnHostRespawned()
        {
            try { EnsureAnimLoop("host respawned"); }
            catch (Exception ex) { Plugin.Log.LogWarning($"[PCOLOR] anim loop restart failed: {ex.Message}"); }
        }

        /// <summary>Publish our own player-color selection so other mod clients can render it.</summary>
        public static void PublishLocalProps()
        {
            try
            {
                // Spectator: no cosmetic publishes (design 3.5, Codex r1 find 13).
                if (RoomActors.LocalIsSpectator) return;
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
            StopAnimLoop();
        }

        /// <summary>Restore one player to their pre-tint colors. Called when re-equipping
        /// (so the new baseline detection runs against vanilla state) and when the
        /// global cosmetic toggle flips off mid-match.</summary>
        /// <summary>Portrait spike / renderer entry: tint an offscreen rig exactly like a
        /// live body (same sniff + apply path). Pair with RevertPlayer(actor) at teardown.</summary>
        private static bool _portraitApply;   // v22 section 3.4: a portrait shows the EQUIPPED cosmetics whatever the local visibility toggle says
        private static int _portraitToken;    // the token of the ApplyForPortrait call in progress; 0 outside one
        private static int _portraitSerial;

        /// <summary>Returns this application's token: never 0 when the call
        /// created the actor's state, 0 when it did not (ApplyToPlayer returned
        /// before creating one). A throw from ApplyToPlayer propagates, and the
        /// caller then has no token.</summary>
        internal static int ApplyForPortrait(Transform rigRoot, int actor, string sku, string colorHex)
        {
            int token = ++_portraitSerial;
            if (token <= 0) { _portraitSerial = 1; token = 1; }
            _portraitApply = true;
            _portraitToken = token;
            try { ApplyToPlayer(rigRoot, actor, sku, colorHex); }
            finally { _portraitApply = false; _portraitToken = 0; }
            // The pinned (time 0) frame is written here, synchronously, instead of
            // waiting for AnimTickLoop: that loop is a coroutine on the plugin's
            // host, which can be destroyed and respawned while a render runs, and
            // a capture must not depend on when, or whether, that loop next runs.
            AnimState st;
            if (!animByActor.TryGetValue(actor, out st) || st == null || st.portraitToken != token) return 0;
            st.clockPinned = true;
            if (!IsAnimatedSku(st.sku)) return token;
            st.staticFrameApplied = false;
            try { st.frameWrites = WriteFrame(st, 0f); st.staticFrameApplied = true; }
            catch (Exception ex) { Plugin.Log.LogWarning($"[PCOLOR] portrait frame write failed: {ex.Message}"); }
            return token;
        }

        /// <summary>True only when the portrait actor's colour is the one a
        /// capture may take: the actor's state is the one the ApplyForPortrait
        /// call that returned `token` created, its clock is pinned, no tint pass
        /// threw, it tinted at least one target, and -- for an animated sku --
        /// its pinned (time 0) frame completed and wrote at least one target
        /// (written by ApplyForPortrait itself, or by AnimTickLoop, which skips a
        /// pinned state once it holds that frame). False for anything else,
        /// a missing state included.</summary>
        internal static bool PortraitFrameReady(int actor, int token)
        {
            AnimState st;
            if (token == 0 || !animByActor.TryGetValue(actor, out st) || st == null) return false;
            if (st.portraitToken != token || !st.clockPinned || st.passFailures != 0) return false;
            if (st.tintedSkins.Count + st.tintedParticles.Count + st.tintedSprites.Count == 0) return false;
            return !IsAnimatedSku(st.sku) || (st.staticFrameApplied && st.frameWrites > 0);
        }

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
                StopAnimLoop();
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
                foreach (var pp in RoomActors.ActiveFighters())   // census: cosmetic bodies belong to fighters
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
                    if (ApplyOrDefer(p.transform, actor, sku, colorHex))
                        Plugin.Log.LogInfo($"[PCOLOR] Re-applied for actor={actor} (late props) sku={sku}");
                    return;
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[PCOLOR] ReapplyForActor failed: {ex.Message}"); }
        }

        // ── Inactive-player defer ───────────────────────────────────
        // Between rounds ROUNDS deactivates dead Player GOs (RPCA_Die →
        // SetActive(false); Revive at next-round load reactivates them). A
        // tint applied in that window runs against the mid-death state and
        // gets partially clobbered by Revive() (which re-reads team colors,
        // e.g. hpSprite). Defer the apply on Plugin.Instance (learning #85:
        // never host coroutines on scene/player objects) until the body is
        // active again, with a bail so a player who never revives doesn't
        // leak a spinning coroutine. Returns true when applied immediately.
        //
        // One deferred apply per actor is recorded, with the behaviour its
        // coroutine runs on, the request generation it applies and the time
        // after which it no longer holds back a new defer. Unity stops a
        // coroutine without running the rest of its body when its behaviour is
        // destroyed (learning #508), and that is not the only way a coroutine
        // stops without reaching its end, so the coroutine's own removal is not
        // the only way a record ends: OnHostDestroyed removes the records of
        // the behaviour being destroyed, and a record whose behaviour is
        // destroyed, or whose time has passed, is replaced by the next defer
        // for its actor.
        private struct PendingApply
        {
            internal MonoBehaviour host;
            internal int gen;
            internal float until;
        }
        private static readonly Dictionary<int, PendingApply> _pendingInactiveApplies = new Dictionary<int, PendingApply>();
        // How long a deferred apply waits for the body to be active, and how much
        // longer its record holds back a new defer: a frame that stalls past the
        // deadline ends the wait late. A defer started while an older one still
        // runs is safe: the request that started it bumped the generation, so the
        // older one finds itself superseded and applies nothing.
        private const float DEFER_WAIT_SECS = 10f;
        private const float DEFER_SLACK_SECS = 2f;

        // Per-actor generation: every request supersedes an in-flight defer so
        // a stale deferred apply can't overwrite a newer color/unequip on
        // revive (review find 12, same shape as PlayerEffectCosmetic).
        private static readonly Dictionary<int, int> _applyGen = new Dictionary<int, int>();

        private static bool ApplyOrDefer(Transform playerRoot, int actor, string sku, string colorHex)
        {
            if (playerRoot == null) return false;
            int g;
            _applyGen.TryGetValue(actor, out g);
            g++;
            _applyGen[actor] = g;
            if (playerRoot.gameObject.activeInHierarchy)
            {
                ApplyToPlayer(playerRoot, actor, sku, colorHex);
                return true;
            }
            PendingApply pending;
            if (_pendingInactiveApplies.TryGetValue(actor, out pending) && pending.host != null
                && Time.realtimeSinceStartup <= pending.until)
                return false;   // the actor's record still holds back a new defer
            var host = Plugin.Instance;
            _pendingInactiveApplies[actor] = new PendingApply { host = host, gen = g, until = Time.realtimeSinceStartup + DEFER_WAIT_SECS + DEFER_SLACK_SECS };
            Plugin.Log.LogInfo($"[PCOLOR] deferred (player inactive) actor={actor}");
            try { host.StartCoroutine(ApplyWhenActive(playerRoot, actor, sku, colorHex, g)); }
            catch (Exception ex)
            {
                DropPending(actor, g);
                Plugin.Log.LogWarning($"[PCOLOR] defer failed: {ex.Message}");
            }
            return false;
        }

        /// <summary>Removes the actor's defer record when it is the one for
        /// `gen`: a defer that ends after a later one replaced its record leaves
        /// that record alone.</summary>
        private static void DropPending(int actor, int gen)
        {
            PendingApply pending;
            if (_pendingInactiveApplies.TryGetValue(actor, out pending) && pending.gen == gen)
                _pendingInactiveApplies.Remove(actor);
        }

        private static IEnumerator ApplyWhenActive(Transform playerRoot, int actor, string sku, string colorHex, int gen)
        {
            float deadline = Time.realtimeSinceStartup + DEFER_WAIT_SECS;
            while (playerRoot != null && !playerRoot.gameObject.activeInHierarchy
                   && Time.realtimeSinceStartup < deadline)
                yield return null;
            DropPending(actor, gen);
            int cur;
            if (_applyGen.TryGetValue(actor, out cur) && cur != gen)
            {
                Plugin.Log.LogInfo($"[PCOLOR] deferred apply superseded actor={actor}");
                yield break;
            }
            // Destroyed (room/match ended) or still inactive at the bail → drop;
            // the next OnRoundStart pass re-applies from live props anyway.
            if (playerRoot == null || !playerRoot.gameObject.activeInHierarchy) yield break;
            ApplyToPlayer(playerRoot, actor, sku, colorHex);
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
                foreach (var pp in RoomActors.ActiveFighters())   // census: cosmetic bodies belong to fighters
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
                ApplyOrDefer(p.transform, actor, sku, colorHex);
            }

            // Spin up the animation tick if any equipped sku is animated.
            EnsureAnimLoop("apply all");
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
            if (!_portraitApply && Plugin.ShowPlayerColors != null && !Plugin.ShowPlayerColors.Value)
            {
                RevertPlayer(actor);
                return;
            }
            // Player/Effects contains gameplay-readability indicators (silence,
            // stun, overheat and boundary warnings), never body visuals.
            Transform fx = playerRoot.Find("Effects");
            if (fx == null)
            {
                VanillaFixSupport.DiagLimited(
                    "PlayerColorCosmetic-effects-missing",
                    "[PCOLOR] Player/Effects subtree not found; gameplay indicators remain eligible for body tint",
                    1);
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
            // A portrait state is pinned from creation: StartCoroutine below runs the
            // loop's first tick synchronously, and that tick must not write a
            // live-time hue onto the rig.
            var st = new AnimState { sku = sku, baseColor = tint, clockPinned = _portraitApply, portraitToken = _portraitApply ? _portraitToken : 0 };

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
                catch { st.passFailures++; }
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
            catch (Exception ex) { st.passFailures++; Plugin.Log.LogWarning($"[PCOLOR] PlayerSkin tint failed: {ex.Message}"); }

            // 2) Particle systems = the body blob. Only tint particles whose START color
            //    is already close to the team baseline (skips block-orb cyan, hit-spark
            //    yellow, etc).
            try
            {
                var pss = playerRoot.GetComponentsInChildren<ParticleSystem>(true);
                foreach (var ps in pss)
                {
                    if (ps == null) continue;
                    if (fx != null && ps.transform.IsChildOf(fx)) continue;
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
            catch (Exception ex) { st.passFailures++; Plugin.Log.LogWarning($"[PCOLOR] ParticleSystem tint failed: {ex.Message}"); }

            // 3) SpriteRenderer pass — only tint sprites whose existing color is close
            //    to the team baseline. Face (cream/white), gun (grey/black), block orb
            //    (cyan), cosmetic trails — all skipped.
            try
            {
                var sprs = playerRoot.GetComponentsInChildren<SpriteRenderer>(true);
                foreach (var sr in sprs)
                {
                    if (sr == null) continue;
                    if (fx != null && sr.transform.IsChildOf(fx)) continue;
                    var c0 = sr.color;
                    if (c0.a < 0.3f) continue;
                    if (!IsTeamLike(c0, teamBaseline)) continue;
                    sr.color = tint;
                    st.tintedSprites.Add(sr);
                    st.originalSpriteColors.Add(c0);
                }
            }
            catch { st.passFailures++; }

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
                if (IsAnimatedSku(sku)) EnsureAnimLoop($"triggered by actor={actor} sku={sku}");
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
        private static IEnumerator AnimTickLoop(int gen)
        {
            var wait = new WaitForSeconds(1f / 30f);
            while (animByActor.Count > 0)
            {
                // v1.32 item 8: static-cosmetics mode freezes the animation clock —
                // prismatic/chrome render a stable representative hue instantly (and
                // resume from live time the moment the setting flips back on).
                bool animationsEnabled = Plugin.AnimatedCosmetics == null || Plugin.AnimatedCosmetics.Value;
                float live = Time.time;
                foreach (var kv in animByActor)
                {
                    var st = kv.Value;
                    if (!IsAnimatedSku(st.sku)) continue;
                    // A portrait rig's clock is pinned: it takes the static frame
                    // once, exactly like static-cosmetics mode.
                    bool animThis = animationsEnabled && !st.clockPinned;
                    if (!animThis && st.staticFrameApplied) continue;
                    int writes = WriteFrame(st, animThis ? live : 0f);
                    if (!animThis) st.frameWrites = writes;
                    st.staticFrameApplied = !animThis;
                }
                yield return wait;
            }
            if (gen == animLoopGen) { animLoop = null; animLoopHost = null; }
        }

        /// <summary>One frame of an animated sku, at animation clock `now`,
        /// onto all three visual layers of its state. Returns the targets
        /// written (a destroyed sprite or particle system is skipped).</summary>
        private static int WriteFrame(AnimState st, float now)
        {
            int writes = 0;
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
            {
                st.skinColorFields[i].SetValue(st.tintedSkins[i], c);
                writes++;
            }
            foreach (var sr in st.tintedSprites)
                if (sr != null) { sr.color = c; writes++; }
            foreach (var ps in st.tintedParticles)
            {
                if (ps == null) continue;
                var main = ps.main;
                main.startColor = new ParticleSystem.MinMaxGradient(c);
                writes++;
            }
            return writes;
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
