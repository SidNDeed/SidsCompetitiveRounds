// PerfPatches.cs — selected ports from the community "Performance Improvements"
// mod for old-ROUNDS. Updated 2026-05-30 to add 2 more patches:
//   RayHitBulletSoundDoHitEffectFinalizer — swallow NRE from destroyed parents
//   ChangeColorStartAutoCleanup           — force 2s destruction so the bullet
//                                            hit color-change ghosts don't pile up
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
                foreach (var k in stale) _lastChecked.Remove(k);
            }
            try
            {
                if (!IsOutOfBounds(__instance.transform)) return;
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
    // coroutine). The original throws NREs which propagate up through Unity's
    // event loop and log-spam BepInEx. Mirroring the BlockTrigger Finalizer
    // pattern we already use elsewhere: swallow the NRE and destroy the now-dead
    // instance so it doesn't try again next frame.
    [HarmonyPatch(typeof(RayHitBulletSound), "DoHitEffect")]
    internal class RayHitBulletSoundDoHitEffectFinalizer
    {
        static System.Exception Finalizer(RayHitBulletSound __instance, System.Exception __exception)
        {
            if (!PerfGate.Check(Plugin.PerfSwallowHitSoundNREs)) return __exception;
            if (__exception is System.NullReferenceException)
            {
                try
                {
                    if (__instance != null && __instance.gameObject != null)
                        UnityEngine.Object.Destroy(__instance.gameObject);
                }
                catch { }
                PerfGate.Hit("SwallowHitSoundNRE");
                return null;
            }
            return __exception;
        }
    }

    // Vanilla's ChangeColor (the bullet-hit color-change ghost) doesn't always
    // self-clean. After heavy firefights you get N hundred of these GameObjects
    // hanging around the scene root, each running an Update tick. Force a 2s
    // RemoveAfterSeconds component on each newly-Started ChangeColor so they
    // self-destruct shortly after their visual purpose is served.
    [HarmonyPatch(typeof(ChangeColor), "Start")]
    internal class ChangeColorStartAutoCleanup
    {
        static void Postfix(ChangeColor __instance)
        {
            if (!PerfGate.Check(Plugin.PerfAutoCleanupColorGhosts)) return;
            if (__instance == null || __instance.gameObject == null) return;
            try
            {
                if (__instance.gameObject.GetComponent<RemoveAfterSeconds>() != null) return;
                var ras = __instance.gameObject.AddComponent<RemoveAfterSeconds>();
                ras.seconds = 2f;
                PerfGate.Hit("AutoCleanupColorGhosts");
            }
            catch { }
        }
    }

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
        internal static System.Exception SwallowAndDestroy(MonoBehaviour mb, System.Exception ex)
        {
            if (ex is System.NullReferenceException)
            {
                try { if (mb != null && mb.gameObject != null) UnityEngine.Object.Destroy(mb.gameObject); }
                catch { }
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

    // CardChoiceVisuals.Show puts up the giant card-pick UI between rounds.
    // The skin preview underneath the card array runs a particle system
    // (bullet trail, gun particles) that costs CPU for the entire 8-12s the
    // pick UI is up. Pause that ParticleSystem when the picker shows — it
    // looks identical (the particles freeze in place rather than animating)
    // and the card render itself uses no particles. ROUNDS' CardChoiceVisuals
    // private field is ___currentSkin.
    [HarmonyPatch(typeof(CardChoiceVisuals), "Show")]
    internal class CardChoiceVisualsShowParticlePause
    {
        static void Postfix(CardChoiceVisuals __instance)
        {
            if (!PerfGate.Check(Plugin.PerfPauseCardPickParticles)) return;
            if (__instance == null) return;
            try
            {
                var f = typeof(CardChoiceVisuals).GetField("currentSkin",
                    System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
                var skin = f?.GetValue(__instance) as GameObject;
                if (skin == null) return;
                var ps = skin.GetComponentInChildren<ParticleSystem>();
                if (ps != null) { ps.Pause(); PerfGate.Hit("PauseCardPickParticles"); }
            }
            catch { }
        }
    }

    // MenuControllerHandler.Update runs every frame even when the player is in
    // an active match — the menu controller routes pad/keyboard input to the
    // menu's button focus state, which is meaningless during gameplay. Skip
    // it while we're tracking a match AND no escape menu is open. Modest
    // CPU win, no visible behavior change.
    [HarmonyPatch(typeof(MenuControllerHandler), "Update")]
    [HarmonyPriority(800)]
    internal class MenuControllerHandlerUpdateBail
    {
        static bool Prefix()
        {
            if (!PerfGate.Check(Plugin.PerfSkipMenuUpdateInMatch)) return true;
            try
            {
                bool inMatch = GameStateWatcher.IsInMatch;
                bool escOpen = false;
                try { escOpen = EscapeMenuHandler.isEscMenu; } catch { }
                bool runOriginal = !inMatch || escOpen;
                if (!runOriginal) PerfGate.Hit("SkipMenuUpdateInMatch");
                return runOriginal;
            }
            catch { return true; }
        }
    }

    // Postfix on ObjectsToSpawn.SpawnObject (the 3-arg overload taking position +
    // rotation) — tags each spawned GameObject with a small marker so that the
    // existing round-cleanup paths can find and destroy them at point-over.
    // Without this, transient bullet-hit decorations accumulate across rounds
    // and the scene root grows by ~50-300 objects per firefight on Stan's setup.
    //
    // ROUNDS may not have `RemoveAfterPoint` in vanilla 1.1.2 — if not, the
    // try/catch silently no-ops and we lose the cleanup-on-point side but
    // nothing breaks.
    [HarmonyPatch]
    internal class ObjectsToSpawnSpawnObjectTagger
    {
        static System.Reflection.MethodBase TargetMethod()
        {
            try
            {
                var t = typeof(ObjectsToSpawn);
                // Try the 3-arg static overload first (Position + Rotation).
                foreach (var m in t.GetMethods(System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.Public))
                {
                    if (m.Name != "SpawnObject") continue;
                    var pars = m.GetParameters();
                    if (pars.Length == 3
                        && pars[1].ParameterType == typeof(Vector3)
                        && pars[2].ParameterType == typeof(Quaternion))
                        return m;
                }
            }
            catch { }
            return null;
        }

        static void Postfix(GameObject[] __result)
        {
            if (!PerfGate.Check(Plugin.PerfTagSpawnedObjectsForCleanup)) return;
            if (__result == null) return;
            foreach (var go in __result)
            {
                if (go == null) continue;
                try
                {
                    // Best-effort: 4s timeout component caps the lifespan
                    // regardless of whether the round ever ends.
                    if (go.GetComponent<RemoveAfterSeconds>() == null)
                    {
                        var ras = go.AddComponent<RemoveAfterSeconds>();
                        ras.seconds = 4f;
                        PerfGate.Hit("TagSpawnedObjectsForCleanup");
                    }
                }
                catch { }
            }
        }
    }
}
