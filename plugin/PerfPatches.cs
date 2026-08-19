// PerfPatches.cs — selected ports from the community "Performance Improvements"
// mod for old-ROUNDS. v1.28.2 audit: every patch target re-verified against the
// CURRENT game decompile (logs-snapshot/decompiled/). Two old-game ports were
// DELETED (ChangeColorStartAutoCleanup — target method gone, class is empty now;
// ObjectsToSpawnSpawnObjectTagger — target is void, and tagging pooled wrappers
// would corrupt FriendlyFoe.PrefabPool), and the NRE swallowers no longer call
// Destroy (bullets are Photon-owned with pooled sub-effects).
//
// Original-perf-mod intro:
// mod for old-ROUNDS, adapted to ROUNDS 1.1.2 (v1.26.8). Each patch is gated on
// Plugin.PerfOptimizations.Value so users can opt out from the F5 → Settings
// panel if a conflict surfaces. We deliberately skip the heavier rendering
// patches (DynamicParticles, GeneralParticleSystem, PlayerSkinParticle) on
// first ship to limit blast radius — those will land later after focused
// in-game soak tests.

using HarmonyLib;
using Photon.Pun;
using System.Collections.Generic;
using System;
using UnityEngine;

namespace CompetitiveRounds
{
    internal static class PerfGate
    {
        // Each patch in this file gates through here. Both the master switch
        // and the per-patch toggle must be ON for the patch to take effect.
        // null-safe so a missing-binding deploy doesn't accidentally enable
        // a patch that the config file says should be off.
        public static bool Check(BepInEx.Configuration.ConfigEntry<bool> perPatch)
        {
            var master = Plugin.PerfOptimizations;
            if (master != null && !master.Value) return false;
            if (perPatch != null && !perPatch.Value) return false;
            return true;
        }

        // ── Telemetry ──────────────────────────────────────────────────────
        // Per-patch invocation counters so we can VERIFY a ported patch is
        // actually firing in-game (the #1 question when porting blind: "is this
        // even running?"). Each patch calls Hit("<name>") at the point it does
        // REAL work (skips the original, caps a spawn, tags an object, swallows
        // an NRE) — NOT merely when the gate passes, so the count reflects effect,
        // not opportunity. First hit of each patch logs a one-time [PERF] line so
        // the BepInEx log shows the patch came alive. DumpAndReset() prints the
        // per-match totals (called from the room-leave hook) and clears for the
        // next match. Lifetime totals persist via _lifetime so a late check can
        // still confirm a patch ever fired this session.
        private static readonly Dictionary<string, long> _counts = new Dictionary<string, long>();
        private static readonly Dictionary<string, long> _lifetime = new Dictionary<string, long>();
        private static readonly HashSet<string> _firstFireLogged = new HashSet<string>();

        public static void Hit(string patch)
        {
            try
            {
                _counts.TryGetValue(patch, out long c); _counts[patch] = c + 1;
                _lifetime.TryGetValue(patch, out long l); _lifetime[patch] = l + 1;
                if (_firstFireLogged.Add(patch))
                    Plugin.Log.LogInfo($"[PERF] {patch} FIRST FIRE (frame {Time.frameCount})");
            }
            catch { }
        }

        /// <summary>Log per-match counts for every patch that fired, then reset the
        /// per-match tally (lifetime totals persist). Called from the room-leave hook.</summary>
        public static void DumpAndReset()
        {
            try
            {
                if (_counts.Count == 0)
                {
                    Plugin.Log.LogInfo("[PERF] No perf patches fired this match (toggles off, or none triggered).");
                    return;
                }
                var sb = new System.Text.StringBuilder("[PERF] Per-match patch hits: ");
                foreach (var kv in _counts) sb.Append(kv.Key).Append('=').Append(kv.Value).Append("  ");
                Plugin.Log.LogInfo(sb.ToString());
                _counts.Clear();
            }
            catch { }
        }

        /// <summary>Snapshot of lifetime hit counts (for an in-game diagnostics surface).</summary>
        public static Dictionary<string, long> LifetimeSnapshot()
        {
            try { return new Dictionary<string, long>(_lifetime); }
            catch { return new Dictionary<string, long>(); }
        }
    }

    // ── CORRECTNESS FIX (v1.28): the "Escape key dies / inputs lock at match-found" bug ──
    //
    // Root cause is in VANILLA ROUNDS, not our mod. PlayerManager.SetInputActive:
    //
    //     public void SetInputActive(bool inputActive) {
    //         foreach (Player player in players)
    //             if (player.IsLocal)                                  // IsLocal => data.view.IsMine
    //                 player.data.playerActions.Enabled = inputActive;
    //     }
    //
    // During the match-found → spawn transition a Player can be present in `players`
    // while its `data` / `data.view` / `data.playerActions` is still null (not yet
    // wired). Vanilla dereferences with ZERO null checks, so the foreach throws a
    // NullReferenceException. Observed in Sid's 2026-06-01 logs:
    //
    //     NullReferenceException
    //       PlayerManager.SetInputActive (System.Boolean inputActive)
    //       EscapeMenuHandler.ToggleEsc ()
    //       EscapeMenuHandler.Update ()
    //
    // That single throw causes BOTH reported symptoms:
    //   1. ESCAPE DIES. EscapeMenuHandler.ToggleEsc() sets `isEscMenu = true` and THEN
    //      calls SetInputActive — which throws, aborting ToggleEsc with isEscMenu stuck
    //      true. Every later Esc press hits `if (isEscMenu && ...) return;` and early-
    //      exits, so Escape is permanently dead until the room is left.
    //   2. INPUTS LOCK / CAN'T READY UP. The foreach throws on the FIRST player whose
    //      data is null. If that player precedes the local one in the list, the loop
    //      never reaches the local player, so local input is never (re)enabled → keys
    //      frozen before space can be pressed. Because the un-wired player can be the
    //      OPPONENT, the freeze can manifest on either client ("sometimes it's my
    //      opponent, not me").
    //
    // Fix: replace the method body with a null-safe iteration that SKIPS un-wired
    // players and KEEPS GOING (so the local player is always reached once its data
    // exists) instead of letting the first null abort the whole loop. Not gated behind
    // the perf master toggle — this is a correctness fix that must always be on. Returns
    // false to fully replace the vanilla body. Mirrors vanilla semantics exactly for
    // fully-wired players.
    [HarmonyPatch(typeof(PlayerManager), "SetInputActive")]
    internal class PlayerManagerSetInputActiveNullGuard
    {
        static bool Prefix(PlayerManager __instance, bool inputActive)
        {
            try
            {
                var players = __instance != null ? __instance.players : null;
                if (players == null) return false;
                for (int i = 0; i < players.Count; i++)
                {
                    var player = players[i];
                    try
                    {
                        // IsLocal => data.view.IsMine; guard the whole chain. A player
                        // mid-spawn can have null data / null view; skip it this call —
                        // a later SetInputActive (the game issues several across the
                        // ready-up → spawn flow) re-runs once it's wired.
                        if (player == null) continue;
                        var data = player.data;
                        if (data == null || data.view == null || data.playerActions == null) continue;
                        if (data.view.IsMine)
                            data.playerActions.Enabled = inputActive;
                    }
                    catch { /* one bad player must never abort the rest of the loop */ }
                }
            }
            catch (System.Exception ex)
            {
                Plugin.Log.LogWarning($"[INPUTFIX] SetInputActive guard error: {ex.Message}");
            }
            return false;  // fully replace vanilla — we've done the work safely
        }
    }

    // Belt-and-suspenders for symptom #1: if EscapeMenuHandler.ToggleEsc still manages to
    // throw for any OTHER reason (vanilla touches ListMenu.instance, m_pageToOpen, etc.,
    // any of which can be null during a transition), a Finalizer swallows the exception so
    // the Esc handler never gets wedged. Without this, a throw anywhere AFTER the
    // `isEscMenu = !isEscMenu` line leaves isEscMenu inverted and Escape dead. We can't
    // un-invert isEscMenu from here (it's already flipped), but swallowing the throw lets
    // the NEXT Esc press run ToggleEsc cleanly and toggle back. The SetInputActive guard
    // above removes the KNOWN cause; this covers the unknown ones.
    [HarmonyPatch(typeof(EscapeMenuHandler), "ToggleEsc")]
    internal class EscapeMenuToggleEscFinalizer
    {
        static System.Exception Finalizer(System.Exception __exception)
        {
            if (__exception != null)
                Plugin.Log.LogWarning($"[INPUTFIX] EscapeMenuHandler.ToggleEsc threw (swallowed): {__exception.Message}");
            return null;  // swallow — keep the Esc handler alive for the next press
        }
    }

    // Vanilla's StunPlayer.Go() walks GetComponentInParent<Player>() then deref's
    // it without a null-check. When a player is destroyed between the stun being
    // queued and Go() running, the field is null and Unity emits an NRE every
    // frame the stun coroutine ticks. Skipping the original call when the
    // ancestor Player is missing turns the cascade into a silent no-op — the
    // stun visuals are cosmetic so missing them on a dead player is fine.
    [HarmonyPatch(typeof(StunPlayer), "Go")]
    internal class StunPlayerGoNullGuard
    {
        static bool Prefix(StunPlayer __instance)
        {
            if (!PerfGate.Check(Plugin.PerfStunPlayerNullGuard)) return true;
            bool ok = __instance != null
                && __instance.GetComponentInParent<global::Player>() != null;
            if (!ok) PerfGate.Hit("StunPlayerGoNullGuard");
            return ok;
        }
    }

    // Despawn projectiles that have flown off-screen instead of letting them
    // live to the engine's maximum lifetime. Bullets that miss everything on
    // the map and exit camera bounds keep ticking their physics + RPC handlers
    // indefinitely — by ~3 minutes into a long round there's measurable Photon
    // bandwidth waste. Throttled to 0.5s per-projectile so we're not paying
    // the bounds check every frame for every active bullet.
    //
    // Only the bullet's OWNER (host of that projectile) issues the destroy
    // RPC — keeps the network authority model consistent with how vanilla
    // already handles projectile cleanup.
    [HarmonyPatch(typeof(ProjectileHit), "Update")]
    internal class ProjectileHitOutOfBoundsCleanup
    {
        private static readonly Dictionary<int, float> _lastChecked = new Dictionary<int, float>(64);
        // Consecutive out-of-bounds observations per projectile — see the streak
        // comment in Prefix. Pruned alongside _lastChecked.
        private static readonly Dictionary<int, int> _oobStreak = new Dictionary<int, int>(64);
        private const float CHECK_INTERVAL = 0.5f;
        // Match the original mod's bounds — slight cushion outside the camera
        // viewport so a bullet at the very edge isn't yanked prematurely.
        private const float X_MIN = -0.25f;
        private const float X_MAX =  1.25f;
        private const float Y_MIN = -1f;

        static void Prefix(ProjectileHit __instance)
        {
            if (!PerfGate.Check(Plugin.PerfDespawnOffscreenBullets)) return;
            if (__instance == null) return;
            int key;
            try { key = __instance.GetInstanceID(); } catch { return; }
            float now = Time.time;
            if (_lastChecked.TryGetValue(key, out float prev) && now < prev + CHECK_INTERVAL) return;
            _lastChecked[key] = now;
            // Periodic prune so the dict doesn't grow without bound across
            // long sessions (instance IDs are reused but only after destroy).
            if (_lastChecked.Count > 512)
            {
                var stale = new List<int>();
                foreach (var kv in _lastChecked) if (now - kv.Value > 30f) stale.Add(kv.Key);
                foreach (var k in stale) { _lastChecked.Remove(k); _oobStreak.Remove(k); }
            }
            try
            {
                if (!IsOutOfBounds(__instance.transform)) { _oobStreak.Remove(key); return; }
                /* Require TWO consecutive out-of-bounds observations, a
                 * CHECK_INTERVAL apart, before destroying (bug #156; Codex
                 * Aug-4 r2 find 2).
                 *
                 * Learning #94: killing a bullet before FriendlyFoe's
                 * BulletPoolInstancer.Start has run makes its OnDestroy NRE
                 * inside PrefabPool.Release, leaving the pooled sub-effect
                 * unreleased and corrupting the pool for the session — Sid's
                 * log carries 12 of exactly that NRE.
                 *
                 * A first-sighting guard keyed on the instance ID does NOT
                 * close it: these projectiles are POOLED, so the same managed
                 * object comes back with the same instance ID and a stale
                 * dictionary entry, and its first Update after reuse sails past
                 * the guard. A streak counter is immune to that — a freshly
                 * reused bullet has to be observed off-screen twice, half a
                 * second apart, by which time its pool init has certainly run.
                 * A bullet that genuinely flew out of frame satisfies it on the
                 * very next check, so nothing real is kept alive longer. */
                /* Round-3 blocker 1: a pooled projectile comes back with the
                 * SAME instance ID, so a streak recorded in a previous lifetime
                 * would carry over and let the very first check of the new one
                 * reach the threshold. An airborne bullet is re-checked every
                 * CHECK_INTERVAL; a gap materially longer than that means this
                 * object was not being tracked in between — i.e. it was in the
                 * pool — so the streak belongs to a dead lifetime. Three
                 * intervals of slack keeps a frame-rate dip from resetting a
                 * real streak; the cost of a false reset is only one more 0.5s
                 * of life for a bullet that already left the screen. */
                int streak; _oobStreak.TryGetValue(key, out streak);
                if (now - prev > CHECK_INTERVAL * 3f) streak = 0;
                streak++;
                _oobStreak[key] = streak;
                if (streak < 2) return;
                _oobStreak.Remove(key);
                if (__instance.ownPlayer == null || __instance.ownPlayer.data == null
                    || __instance.ownPlayer.data.view == null
                    || !__instance.ownPlayer.data.view.IsMine) return;
                if (__instance.gameObject != null)
                {
                    PhotonNetwork.Destroy(__instance.gameObject);
                    PerfGate.Hit("DespawnOffscreenBullets");
                }
            }
            catch { /* destroyed-mid-tick is fine; let it ride */ }
        }

        private static bool IsOutOfBounds(Transform t)
        {
            try
            {
                var cam = MainCam.instance?.transform?.GetComponent<Camera>();
                if (cam == null) return false;
                Vector3 sp = cam.WorldToScreenPoint(new Vector3(t.position.x, t.position.y, 0f));
                float nx = sp.x / Mathf.Max(1f, (float)Screen.width);
                float ny = sp.y / Mathf.Max(1f, (float)Screen.height);
                return nx <= X_MIN || nx >= X_MAX || ny <= Y_MIN;
            }
            catch { return false; }
        }
    }

    // Vanilla's RayHitBulletSound.DoHitEffect iterates components on a GameObject
    // that may already be in mid-destruction (Photon-side destroy raced the local
    // coroutine). Swallow the NRE so it doesn't log-spam.
    //
    // v1.28.2: swallow WITHOUT destroying. The old-game port destroyed the
    // GameObject — but on current ROUNDS the host object is a Photon-owned
    // bullet carrying POOLED sub-effects (BulletPoolInstancer). A plain
    // Object.Destroy here killed bullets before BulletPoolInstancer.Start ran
    // (PrefabPool.Release NREs in its OnDestroy) and orphaned PhotonViews on
    // the remote, producing the later ProjectileHit.RPCA_DoHit NRE storms
    // seen in lopi's log. Log-silencing only; vanilla owns the lifecycle.
    [HarmonyPatch(typeof(RayHitBulletSound), "DoHitEffect")]
    internal class RayHitBulletSoundDoHitEffectFinalizer
    {
        static System.Exception Finalizer(System.Exception __exception)
        {
            if (!PerfGate.Check(Plugin.PerfSwallowHitSoundNREs)) return __exception;
            if (__exception is System.NullReferenceException || __exception is UnityEngine.MissingReferenceException)
            {
                PerfGate.Hit("SwallowHitSoundNRE");
                return null;
            }
            return __exception;
        }
    }

    // (v1.28.2) ChangeColorStartAutoCleanup REMOVED. It was ported blind from
    // the old-game PI mod and never attached on current ROUNDS 1.1.2 —
    // startup log: "AccessTools.DeclaredMethod: Could not find method for
    // type ChangeColor and name Start" / "Failed to patch
    // ChangeColorStartAutoCleanup". The current decompile
    // (logs-snapshot/decompiled/ChangeColor.cs) shows ChangeColor is an EMPTY
    // MonoBehaviour: no Start, no Update tick, nothing to clean. Hit effects
    // are pooled via FriendlyFoe.PrefabPool now, so the old "ghost pile-up"
    // problem this solved no longer exists.

    // ScreenEdgeBounce.DoHit / Update both can NRE when the parent bullet has
    // been destroyed mid-frame but the bounce coroutine ticks one more time
    // before it learns about the destroy. Same Finalizer pattern as
    // RayHitBulletSound + BlockTrigger: swallow the NRE and destroy the now-
    // dead instance so it doesn't try again.
    [HarmonyPatch(typeof(ScreenEdgeBounce), "DoHit")]
    internal class ScreenEdgeBounceDoHitFinalizer
    {
        static System.Exception Finalizer(ScreenEdgeBounce __instance, System.Exception __exception)
        {
            if (!PerfGate.Check(Plugin.PerfSwallowEdgeBounceNREs)) return __exception;
            return _PerfHelpers.SwallowAndDestroy(__instance, __exception);
        }
    }
    [HarmonyPatch(typeof(ScreenEdgeBounce), "Update")]
    internal class ScreenEdgeBounceUpdateFinalizer
    {
        static System.Exception Finalizer(ScreenEdgeBounce __instance, System.Exception __exception)
        {
            if (!PerfGate.Check(Plugin.PerfSwallowEdgeBounceNREs)) return __exception;
            return _PerfHelpers.SwallowAndDestroy(__instance, __exception);
        }
    }
    internal static class _PerfHelpers
    {
        // v1.28.2: renamed semantics — swallow ONLY, never Destroy. Current
        // ROUNDS bullets are Photon-owned with pooled sub-effects; destroying
        // them locally corrupted FriendlyFoe.PrefabPool and desynced
        // PhotonViews (see RayHitBulletSoundDoHitEffectFinalizer note). A
        // repeated swallowed NRE costs a log counter tick; a destroyed pooled
        // object costs pool integrity for the rest of the session.
        internal static System.Exception SwallowAndDestroy(MonoBehaviour mb, System.Exception ex)
        {
            if (ex is System.NullReferenceException || ex is UnityEngine.MissingReferenceException)
            {
                PerfGate.Hit("SwallowEdgeBounceNRE");
                return null;
            }
            return ex;
        }
    }
    // Bridge the per-patch Finalizers above to the shared helper. Local alias so the
    // null-check chain reads the same in both ScreenEdgeBounce variants.
    internal static class _PerfHelpersAlias
    {
        public static System.Exception _SwallowAndDestroy(ScreenEdgeBounce mb, System.Exception ex)
            => _PerfHelpers.SwallowAndDestroy(mb, ex);
    }
}

namespace CompetitiveRounds
{
    // ── v1.26.9 perf additions (user-noticeable batch) ─────────────────────
    // The earlier patches (StunPlayer null-guard, OOB bullet cleanup, NRE
    // swallowers) chiefly trimmed log spam and edge-case memory leaks. These
    // three are the perf-mod's actual frame-time wins ported to current
    // ROUNDS 1.1.2. RemoveAfterPoint and ColorFlash were removed by Landfall,
    // so the bulletHit / skin-particle patches are simplified — cap the spawn
    // rate instead of also re-tagging the spawned objects.

    // DynamicParticles.PlayBulletHit fires per bullet impact. In a heavy
    // firefight (BombsAway + Echo + Mayhem) a single frame can have 20+
    // bullets land simultaneously — each one spawning a multi-particle
    // explosion. Cap at MAX_PER_FRAME hits per frame: the first N spawn as
    // normal, the rest silently no-op. Visually you don't notice the missed
    // explosion (the actual damage already registered), but the GC pressure
    // and the render cost drop a lot.
    [HarmonyPatch(typeof(DynamicParticles), "PlayBulletHit")]
    internal class DynamicParticlesPlayBulletHitCap
    {
        private const int MAX_PER_FRAME = 2;
        private static int _lastFrame = -1;
        private static int _countThisFrame;

        static bool Prefix()
        {
            if (!PerfGate.Check(Plugin.PerfBulletHitParticleCap)) return true;
            int frame = Time.frameCount;
            if (frame != _lastFrame)
            {
                _lastFrame = frame;
                _countThisFrame = 0;
            }
            if (_countThisFrame >= MAX_PER_FRAME) { PerfGate.Hit("BulletHitParticleCap"); return false; }
            _countThisFrame++;
            return true;
        }
    }

    // ObjectPool's constructor pre-spawns an initial pool of GameObjects.
    // During a match, that's a frame-stutter source whenever a new
    // particle/effect pool is built — clamping initSpawn to 4 means the pool
    // grows lazily instead of allocating 30+ instances up-front. Outside a
    // match (lobby, menu) the clamp doesn't fire — original behavior preserved.
    [HarmonyPatch]
    internal class ObjectPoolInitClamp
    {
        static System.Reflection.MethodBase TargetMethod()
        {
            try
            {
                var t = typeof(ObjectPool);
                foreach (var c in t.GetConstructors(
                    System.Reflection.BindingFlags.Public
                    | System.Reflection.BindingFlags.NonPublic
                    | System.Reflection.BindingFlags.Instance))
                {
                    var pars = c.GetParameters();
                    // Constructor signature ROUNDS uses:
                    //   ObjectPool(GameObject prefab, int initSpawn, Transform parent)
                    if (pars.Length >= 2
                        && pars[0].ParameterType == typeof(GameObject)
                        && pars[1].ParameterType == typeof(int))
                        return c;
                }
            }
            catch { }
            return null;
        }

        static void Prefix(ref int initSpawn)
        {
            if (!PerfGate.Check(Plugin.PerfClampObjectPoolInit)) return;
            // Only clamp during gameplay — preserves snappy menu/lobby load.
            try { if (!GameStateWatcher.IsInMatch) return; }
            catch { return; }
            if (initSpawn > 4) { initSpawn = 4; PerfGate.Hit("ClampObjectPoolInit"); }
        }
    }

    // REMOVED v1.28.3 (bug #29): CardChoiceVisualsShowParticlePause. It paused
    // the card-pick visualizer's first ParticleSystem to save CPU while the
    // pick UI was up — but that ParticleSystem IS the picker's character body:
    // vanilla CardChoiceVisuals.Show clones the PlayerSkinBank skin template
    // and Play()s exactly that system. Our Postfix ran in the same frame,
    // before a single particle had been emitted, so "freeze in place" really
    // meant "freeze at zero particles" — the pick-phase body rendered
    // invisible (face + cosmetics unaffected; they aren't particle-driven).
    // Verified live: 29 patch hits in the session where Sid reproduced it
    // 100% in a room-code ranked lobby. The CPU win was one paused particle
    // system for ~10s — not worth a patch at all.

    // MenuControllerHandler.Update runs every frame even when the player is in
    // an active match — the menu controller routes pad/keyboard input to the
    // menu's button focus state, which is meaningless during gameplay. Skip
    // it while we're tracking a match AND no escape menu is open. Modest
    // CPU win, no visible behavior change.
    [HarmonyPatch(typeof(MenuControllerHandler), "Update")]
    [HarmonyPriority(800)]
    internal class MenuControllerHandlerUpdateBail
    {
        private static bool _wasSkipping;

        static bool Prefix()
        {
            if (!PerfGate.Check(Plugin.PerfSkipMenuUpdateInMatch))
            {
                _wasSkipping = false;
                return true;
            }
            try
            {
                bool inMatch = GameStateWatcher.IsInMatch;
                bool escOpen = false;
                try { escOpen = EscapeMenuHandler.isEscMenu; } catch { }
                bool runOriginal = !inMatch || escOpen;
                // Record the transition, not every skipped frame. Updating two
                // telemetry dictionaries each frame partially erased this
                // deliberately small hot-path optimization.
                if (!runOriginal && !_wasSkipping) PerfGate.Hit("SkipMenuUpdateInMatch");
                _wasSkipping = !runOriginal;
                return runOriginal;
            }
            catch { _wasSkipping = false; return true; }
        }
    }

    // (v1.28.2) ObjectsToSpawnSpawnObjectTagger REMOVED — two independent
    // fatal mismatches against current ROUNDS 1.1.2
    // (logs-snapshot/decompiled/ObjectsToSpawn.cs):
    //   1. The 3-arg SpawnObject(ObjectsToSpawn, Vector3, Quaternion) it
    //      targeted is VOID — the GameObject[] __result Postfix can never
    //      bind ("Cannot get result from void method" / "IL Compile Error"
    //      at startup; the patch never attached).
    //   2. The 8-arg overload returns PoolableWrapper[] from
    //      FriendlyFoe.PrefabPool — POOLED instances. Adding a
    //      RemoveAfterSeconds (a Destroy timer) to pooled objects destroys
    //      pool members and corrupts the pool (PrefabPool.Release NREs).
    // Vanilla's pooling already solves the accumulation problem this patch
    // existed for on the old game. Nothing to port — delete.

    // ── v1.32 item 7: disable screen shake ─────────────────────────────────
    // Vanilla routes every shake impulse (gun fire, hits, deaths, landings, UI
    // pops — including cross-client RPCA_AllGameFeel replication) through the
    // GameFeeler fan-out; Screenshaker is THE camera-shake receiver (decompile
    // -Module-.cs:29411, spring/damper integrator). Prefix-return-false on both
    // receive methods = no impulse ever enters the spring, and the Update
    // integrator is inert at rest — zero visual residue, purely local.
    // Standalone gate (Plugin.ScreenShakeEnabled), deliberately NOT under the
    // perf master: this is an accessibility preference, not a perf patch.
    // NOTE (learning #83): verify "Failed to patch" is absent from the startup
    // log on first launch — a renamed method would fail silently otherwise.
    [HarmonyPatch(typeof(Screenshaker))]
    internal static class ScreenshakerDisablePatch
    {
        /// <summary>Full / Reduced / Off (Sid's call on report #141).
        ///
        /// <para>Scaling the incoming impulse rather than touching
        /// <c>Screenshaker.shakeforce</c> is deliberate: vanilla's
        /// <c>LowerScreenshakePerPlayer</c> permanently halves that field once,
        /// mid-game, when a lobby exceeds two players and then destroys itself.
        /// Anything that caches and restores the field would either undo that
        /// reduction or compound with it. The impulse is stateless, so both
        /// systems compose.</para>
        ///
        /// <para>0.35 for Reduced: the shake is a spring-damper integrator
        /// (<c>velocity += direction * shakeforce</c>), so the visible amplitude
        /// scales linearly with the impulse — a third keeps the hit feedback
        /// legible while removing the part people find nauseating.</para></summary>
        internal static string Level
        {
            get
            {
                string v = Plugin.ScreenShakeStrength != null ? (Plugin.ScreenShakeStrength.Value ?? "") : "";
                if (string.Equals(v, "Off", StringComparison.OrdinalIgnoreCase)) return "Off";
                if (string.Equals(v, "Reduced", StringComparison.OrdinalIgnoreCase)) return "Reduced";
                return "Full";
            }
        }

        /// <summary>Cycles Full -> Reduced -> Off -> Full. No apply step needed —
        /// the patch reads the level per impulse.</summary>
        internal static void Cycle()
        {
            if (Plugin.ScreenShakeStrength == null) return;
            Plugin.ScreenShakeStrength.Value =
                Level == "Full" ? "Reduced" : Level == "Reduced" ? "Off" : "Full";
        }

        private static bool Scale(ref Vector2 feelDirection)
        {
            // Spectator seats: always Off, whatever the setting says. The
            // dynamic spectator camera was deleted for a static broadcast
            // frame (SpectatorCamera.cs tombstone, Aug 19); shake impulses
            // were the remaining camera motion on that seat (D1 finding 2).
            try { if (RoomActors.LocalIsSpectator) { PerfGate.Hit("ScreenShakeBlocked"); return false; } } catch { }
            string lvl = Level;
            if (lvl == "Full") return true;
            if (lvl == "Off")
            {
                PerfGate.Hit("ScreenShakeBlocked");
                return false;
            }
            feelDirection *= 0.35f;
            PerfGate.Hit("ScreenShakeReduced");
            return true;
        }

        [HarmonyPrefix]
        [HarmonyPatch("OnGameFeel")]
        static bool PreOnGameFeel(ref Vector2 feelDirection) => Scale(ref feelDirection);

        [HarmonyPrefix]
        [HarmonyPatch("OnUIGameFeel")]
        static bool PreOnUIGameFeel(ref Vector2 feelDirection) => Scale(ref feelDirection);
    }
}
