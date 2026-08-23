using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Reflection;
using HarmonyLib;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    internal static class VanillaFixSupport
    {
        private static readonly object Sync = new object();
        private static readonly HashSet<string> AttachedPatches = new HashSet<string>();
        private static readonly Dictionary<string, float> LastErrors = new Dictionary<string, float>();
        private static readonly Dictionary<string, int> DiagnosticCounts = new Dictionary<string, int>();

        /// <summary>STRICT scope: only rooms where EVERY client is guaranteed to be
        /// running this mod — mod-issued rooms (queue/tournament/FFA) plus offline.
        ///
        /// Use this ONLY where correctness requires every client in the room to apply
        /// the same patch, i.e. where a half-applied patch is WORSE than no patch.
        /// Today that is exactly one site: PoisonGhostPatch's ignoreBlock override.
        ///
        /// DO NOT widen CompetitiveRoomDetect.IsCompetitiveRoom() to reach privately
        /// hosted room-code games. It is load-bearing elsewhere for queue lifecycle,
        /// the in_match destruction veto, PopUpHandler auto-continue and the 2v2 spawn
        /// sort — widening it there has side effects that have nothing to do with
        /// gameplay patches. Use AnyGameScope() instead.
        ///
        /// Bug #151: nine patch classes used to sit behind this gate, which silently
        /// excluded privately hosted room-code games — 580 of 920 ranked matches in a
        /// 30-day window (63%). Everything that does NOT require room-wide unanimity
        /// has since moved to AnyGameScope() or been ungated outright.</summary>
        internal static bool GameplayScope()
        {
            try
            {
                return PhotonNetwork.OfflineMode || CompetitiveRoomDetect.IsCompetitiveRoom();
            }
            catch (Exception ex)
            {
                LogError("GameplayScope", ex);
                return false;
            }
        }

        /// <summary>BROAD scope: any actual game, however the room was created —
        /// mod-issued, private room code, public quickplay, or offline sandbox.
        ///
        /// Correct for any fix whose effect is LOCAL and IDEMPOTENT, i.e. one that
        /// cannot make two clients disagree about anything outliving a round
        /// transition. A patch under this gate is safe with an unpatched peer in the
        /// room because it never asks that peer to do anything.</summary>
        internal static bool AnyGameScope()
        {
            try
            {
                return PhotonNetwork.OfflineMode || PhotonNetwork.InRoom;
            }
            catch (Exception ex)
            {
                LogError("AnyGameScope", ex);
                return false;
            }
        }

        internal static Exception Cleanup(string name, Exception exception)
        {
            try
            {
                if (exception != null) return exception;

                bool shouldLog;
                lock (Sync)
                {
                    shouldLog = AttachedPatches.Add(name);
                }

                if (shouldLog)
                    Plugin.Log.LogInfo("[VANILLA-FIX] " + name + " attached");
            }
            catch
            {
                // Cleanup must never hide a Harmony patching exception.
            }

            return exception;
        }

        internal static void LogError(string name, Exception exception)
        {
            try
            {
                float now = Time.realtimeSinceStartup;
                lock (Sync)
                {
                    float last;
                    if (LastErrors.TryGetValue(name, out last) && now - last < 5f) return;
                    LastErrors[name] = now;
                }

                Plugin.Log.LogWarning(
                    "[VANILLA-FIX] " + name + " error: " +
                    exception.GetType().Name + ": " + exception.Message);
            }
            catch
            {
                // Logging is never allowed to affect vanilla control flow.
            }
        }

        internal static void DiagLimited(string key, string message, int maximum)
        {
            try
            {
                if (TryReserveDiag(key, maximum)) WriteReservedDiag(message);
            }
            catch
            {
                // Diagnostics are best effort only.
            }
        }

        /// <summary>Reserve a bounded diagnostic slot before constructing an
        /// expensive hot-path message. Callers that cache an exhausted result
        /// must clear that cache at the same edge that calls ResetDiag.</summary>
        internal static bool TryReserveDiag(string key, int maximum)
        {
            if (string.IsNullOrEmpty(key) || maximum <= 0) return false;
            try
            {
                lock (Sync)
                {
                    int count;
                    DiagnosticCounts.TryGetValue(key, out count);
                    if (count >= maximum) return false;
                    DiagnosticCounts[key] = count + 1;
                    return true;
                }
            }
            catch { return false; }
        }

        internal static void WriteReservedDiag(string message)
        {
            try { Plugin.Log.LogInfo("[VANILLA-DIAG] " + message); }
            catch { }
        }

        /// <summary>Drop one diagnostic budget entry so a per-sitting diag
        /// gets a fresh budget. Called from room-TRANSITION edges (today:
        /// GameStateWatcher's room-exit edge resets the stale-projectile
        /// sweep's key). Dynamic per-room keys were tried and rejected in
        /// review (r2/r3): they grow the dict per room and an in-sweep reset
        /// can only see key CHANGES, so a directly-rejoined room inherited
        /// its spent budget. Fixed key + edge reset has neither hole.</summary>
        internal static void ResetDiag(string key)
        {
            if (string.IsNullOrEmpty(key)) return;
            try { lock (Sync) { DiagnosticCounts.Remove(key); } } catch { }
        }

        internal static string Float(float value)
        {
            return value.ToString("0.000", CultureInfo.InvariantCulture);
        }

        internal static string PlayerId(Component component)
        {
            try
            {
                Player player = component.GetComponent<Player>();
                return player == null
                    ? "unknown"
                    : player.PlayerID.ToString(CultureInfo.InvariantCulture);
            }
            catch
            {
                return "unknown";
            }
        }
    }

    /// <summary>Codex FFA-audit find 3: RadarShot's block visual (VE_Radar)
    /// is spawned unparented by SpawnObjects.Spawn with NO lifetime — its
    /// 0.15s particle completes and the dead root stays forever (vanilla's
    /// MapTransition.ClearObjects only removes RemoveAfterSeconds carriers).
    /// Ten blocks = ten dead roots, unbounded over a long sitting. The
    /// visual is a plain local Instantiate (not Photon/pooled — #94 safe);
    /// give it the RemoveAfterSeconds vanilla forgot.</summary>
    [HarmonyPatch(typeof(SpawnObjects), "Spawn")]
    internal static class RadarVisualLifetimePatch
    {
        [HarmonyPostfix]
        private static void AfterSpawn(SpawnObjects __instance)
        {
            try
            {
                // Ungated (#151): a leaked local GameObject is not mode-specific, and
                // nothing here is networked or cross-client.
                var go = __instance.mostRecentlySpawnedObject;
                if (go == null || !go.name.StartsWith("VE_Radar")) return;
                if (go.GetComponent<RemoveAfterSeconds>() != null) return;
                var ras = go.AddComponent<RemoveAfterSeconds>();
                ras.seconds = 2f;
            }
            catch { }
        }
    }

    [HarmonyPatch(typeof(Gun), "ResetStats")]
    internal static class DemonicPactSprayPatch
    {
        [HarmonyPostfix]
        private static void AfterResetStats(Gun __instance)
        {
            try
            {
                // AnyGameScope since #151: auto-fire is purely LOCAL input behaviour —
                // nothing about it crosses the wire, so an unpatched peer keeping the
                // vanilla latch cannot desync anything. Learning #198 originally scoped
                // this to competitive rooms out of an asymmetry concern about public
                // quickplay; that reasoning does not reach privately hosted rated games,
                // where both players have the mod and today a vanilla bug silently
                // poisons their guns for the rest of the room with no repair at all.
                if (!VanillaFixSupport.AnyGameScope()) return;
                if (!__instance.dontAllowAutoFire) return;

                __instance.dontAllowAutoFire = false;
                VanillaFixSupport.DiagLimited(
                    "DemonicPactSpray-cleared",
                    "DemonicPactSpray cleared stale dontAllowAutoFire in Gun.ResetStats",
                    8);
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("DemonicPactSpray", ex);
            }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("DemonicPactSpray", exception);
        }
    }

    [HarmonyPatch(
        typeof(HealthHandler),
        "DoDamage",
        new Type[]
        {
            typeof(Vector2),
            typeof(Vector2),
            typeof(Color),
            typeof(GameObject),
            typeof(Player),
            typeof(bool),
            typeof(bool),
            typeof(bool),
            typeof(HealthHandler.DamageSource)
        })]
    internal static class PoisonGhostPatch
    {
        [HarmonyPrefix]
        private static void BeforeDoDamage(
            HealthHandler __instance,
            Vector2 damage,
            bool healthRemoval,
            ref bool ignoreBlock)
        {
            try
            {
                if (!healthRemoval) return;

                // ── THIS GATE MUST STAY STRICT. Do not "fix" it to AnyGameScope. ──
                //
                // Bug #151 widened eight sibling patches out of GameplayScope because
                // it excluded privately hosted room-code games. This one is the
                // deliberate exception, and widening it makes things WORSE.
                //
                // The bypass is only correct when EVERY client in the room forces it.
                // In a room where only some clients do, the modded victim ignores its
                // block while a block-aware peer honours it — so the two disagree on
                // the ENTIRE blocked set, instead of the ~1 boundary tick they
                // disagree on today. Only mod-issued rooms guarantee unanimity.
                //
                // Private room-code games are served by the authoritative protocol
                // (PoisonSync) instead, which needs no unanimity because the decision
                // is made once by the victim rather than agreed room-wide.
                if (!VanillaFixSupport.GameplayScope()) return;

                // FALLBACK ARM ONLY. Three cases route past this patch:
                //
                //  * Capable victim: its own client already made the block decision
                //    once, and its committed ticks arrive with ignoreBlock: true set
                //    explicitly. Forcing it here too would be redundant and would mask
                //    a stray local DOT if one ever escaped the scheduler — leave those
                //    visible.
                //  * Offline / sandbox: one simulation, so vanilla's own block check is
                //    already consistent. Forcing the bypass there removed a real
                //    mechanic for no benefit.
                //  * Online, incapable victim: unchanged v1.35.4 behaviour — ticks
                //    bypass block so every replica agrees, because we cannot make an
                //    unpatched peer honour a verdict.
                if (PoisonSync.CapableVictim(__instance.GetComponent<PhotonView>())) return;
                try
                {
                    if (!Photon.Pun.PhotonNetwork.InRoom || Photon.Pun.PhotonNetwork.OfflineMode) return;
                }
                catch { }

                // Bug #135 (galaxy ice, July 30): "poison desync still
                // happens". Root cause was this patch's own former exemption:
                // victims whose stats route direct damage through the DoT path
                // (Decay holders — stats.secondsToTakeDamageOver != 0) kept
                // FULL vanilla per-replica block behavior for every
                // healthRemoval tick, poison included. Proven from the
                // reported lobby: all four clients ran the fix, and two of
                // the four held Decay — the desync galaxy watched was a
                // Decay-holding victim's ghost HP. FFA makes the exemption
                // class common (more players x rolling card churn), which is
                // why "it failed for FFA".
                //
                // The exemption existed to preserve block-the-spread
                // mitigation, but that mitigation IS the desync: each replica
                // applies its own local block window to its own local tick
                // stream, and no client is authoritative. Blocking the DIRECT
                // hit still prevents the entire Decay spread — only the
                // unsyncable "block mid-spread to truncate remaining ticks"
                // niche is removed. Balance call flagged to Sid on the bug
                // report; revert by restoring the secondsToTakeDamageOver
                // early-return above this line.
                Block block = __instance.GetComponent<Block>();
                if (!ignoreBlock && block != null && block.IsBlocking())
                {
                    PhotonView view = __instance.GetComponent<PhotonView>();
                    VanillaFixSupport.DiagLimited(
                        "PoisonGhost-block-window",
                        "PoisonGhost bypassed a later block window player=" +
                        VanillaFixSupport.PlayerId(__instance) +
                        " mine=" + (view != null && view.IsMine) +
                        " sinceBlock=" + VanillaFixSupport.Float(block.sinceBlock) +
                        " damage=" + VanillaFixSupport.Float(damage.magnitude) +
                        " frame=" + Time.frameCount.ToString(CultureInfo.InvariantCulture),
                        20);
                }

                // DamageOverTime marks its ticks as healthRemoval. The flag is
                // otherwise ignored by vanilla, allowing a later local block
                // window to reject a tick on only one replica.
                ignoreBlock = true;
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("PoisonGhost", ex);
            }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("PoisonGhost", exception);
        }
    }

    [HarmonyPatch]
    internal static class DrillVisibilityPatch
    {
        // viewID -> deferred-replay attempts for the pre-Start race (Codex
        // design find 3). Bullet view ids are transient (and recycled), so
        // the map is best-effort: cleared on success and capacity-capped.
        private static readonly Dictionary<int, int> _drillReplays = new Dictionary<int, int>();

        [HarmonyPrefix]
        [HarmonyPatch(
            typeof(RayHitDrill),
            "RPCA_Deactivate",
            new Type[] { typeof(Vector2) })]
        private static void BeforeDrillDeactivate(RayHitDrill __instance, Vector2 tpPos)
        {
            try
            {
                // AnyGameScope since #151: this CONVERGES a non-owner's stale root to
                // the authoritative value the RPC itself carries. It removes divergence
                // rather than creating it, so a mixed roster is harmless.
                if (!VanillaFixSupport.AnyGameScope()) return;

                Transform root = __instance.transform.root;
                if (root == null) return;

                PhotonView view = root.GetComponent<PhotonView>();
                if (view == null || view.IsMine) return;

                Vector3 oldPosition = root.position;
                float error = Vector2.Distance(
                    new Vector2(oldPosition.x, oldPosition.y),
                    tpPos);

                root.position = new Vector3(tpPos.x, tpPos.y, oldPosition.z);

                RayCastTrail ray = root.GetComponent<RayCastTrail>();
                if (ray != null) ray.MoveRay();

                // Adversarial-review add (Claude): the pooled bullet trail is a
                // Unity TrailRenderer parented under this root — it records
                // world positions, so a multi-unit snap would otherwise paint a
                // straight streak spanning the jump for the trail's lifetime.
                // Clear() drops the recorded points; runs only on DrillStop.
                TrailRenderer[] trails = root.GetComponentsInChildren<TrailRenderer>(true);
                for (int i = 0; i < trails.Length; i++)
                {
                    if (trails[i] != null) trails[i].Clear();
                }

                bool divergent = error > 0.001f;
                VanillaFixSupport.DiagLimited(
                    divergent
                        ? "DrillVisibility-root-correction"
                        : "DrillVisibility-root-zero",
                    "DrillVisibility corrected remote root error=" +
                    VanillaFixSupport.Float(error) +
                    " view=" + view.ViewID.ToString(CultureInfo.InvariantCulture) +
                    " frame=" + Time.frameCount.ToString(CultureInfo.InvariantCulture),
                    divergent ? 20 : 1);
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("DrillVisibility.Deactivate", ex);
            }
        }

        [HarmonyPrefix]
        [HarmonyPatch(
            typeof(ProjectileHit),
            "RPCA_DoHit",
            new Type[]
            {
                typeof(Vector2),
                typeof(Vector2),
                typeof(Vector2),
                typeof(int),
                typeof(int),
                typeof(bool)
            })]
        private static bool DiagnoseMissingDrillEffect(
            ProjectileHit __instance,
            Vector2 hitPoint,
            Vector2 hitNormal,
            Vector2 vel,
            int viewID,
            int colliderID,
            bool wasBlocked)
        {
            try
            {
                if (viewID != -1 || colliderID < 0) return true;

                PhotonView view = __instance.GetComponent<PhotonView>();
                if (view == null || view.IsMine) return true;

                RayHitDrill[] drills = __instance.GetComponentsInChildren<RayHitDrill>(true);
                if (drills == null || drills.Length == 0) return true;

                /* Aug 9 upgrade (bug #186): diagnostic -> REPAIR. Seven
                 * missing-effect detections in one FFA game proved the race is
                 * real: on a remote client the Drill child can be instantiated
                 * by the (possibly one-frame-late) RPCA_Init AFTER
                 * ProjectileHit.Start snapshotted `effects`
                 * (ProjectileHit.cs:93) — so the remote's surface-hit
                 * processing never runs RayHitDrill.DoHitEffect: the remote
                 * copy dies at the wall while the owner's bullet drills
                 * through and keeps dealing damage. That IS the "drill bullet
                 * goes invisible when fired point-blank into a wall/box"
                 * report — a point-blank shot maximises exposure to the
                 * registration race.
                 *
                 * Repair: register the missing drill(s) into effects and
                 * re-sort via vanilla's own ResortHitEffects(), BEFORE vanilla
                 * processes this hit. Only drills whose Start has run are
                 * added (proj is assigned in RayHitDrill.Start; DoHitEffect
                 * dereferences it — #211's not-Started-yet trap); a pre-Start
                 * drill registers on the next hit instead. AnyGameScope like
                 * the root-snap fix above: this converges the remote toward
                 * the owner-authoritative behaviour, so a mixed roster is
                 * harmless. */
                if (!VanillaFixSupport.AnyGameScope()) return true;

                if (__instance.effects == null)
                    __instance.effects = new System.Collections.Generic.List<RayHitEffect>();

                int repaired = 0, notReady = 0;
                for (int i = 0; i < drills.Length; i++)
                {
                    if (drills[i] == null) continue;
                    if (__instance.effects.Contains(drills[i])) continue;
                    if (drills[i].proj == null) { notReady++; continue; }
                    __instance.effects.Add(drills[i]);
                    repaired++;
                }

                if (repaired > 0)
                {
                    __instance.ResortHitEffects();
                    VanillaFixSupport.DiagLimited(
                        "DrillVisibility-effect-repair",
                        "DrillVisibility re-registered " +
                        repaired.ToString(CultureInfo.InvariantCulture) +
                        " Drill child(ren) missing from ProjectileHit.effects" +
                        " view=" + view.ViewID.ToString(CultureInfo.InvariantCulture) +
                        " frame=" + Time.frameCount.ToString(CultureInfo.InvariantCulture),
                        20);
                }

                if (notReady > 0)
                {
                    /* Codex design find 3 — the point-blank same-frame race:
                     * the Drill child exists but RayHitDrill.Start has not run
                     * (proj/move/rpc/mainDrill unset), which happens exactly
                     * when the instantiate + RPCA_Init + RPCA_DoHit RPCs land
                     * in ONE dispatch batch — i.e. a shot fired with the gun
                     * pressed against a wall (bug #186's report). Registering
                     * it now would NRE inside DoHitEffect (#211); skipping it
                     * lets vanilla kill the remote bullet with no next hit to
                     * repair. So DEFER the whole hit one frame and replay it —
                     * Start will have run by then and the repair path above
                     * registers it. Capped at 2 replays per view id; giving up
                     * falls back to vanilla (the pre-fix behaviour). */
                    int attempts;
                    _drillReplays.TryGetValue(view.ViewID, out attempts);
                    if (attempts < 2 && Plugin.Instance != null)
                    {
                        if (_drillReplays.Count > 64) _drillReplays.Clear();
                        _drillReplays[view.ViewID] = attempts + 1;
                        Plugin.Instance.StartCoroutine(ReplayDeferredHit(
                            __instance, hitPoint, hitNormal, vel, viewID, colliderID, wasBlocked));
                        VanillaFixSupport.DiagLimited(
                            "DrillVisibility-hit-deferred",
                            "DrillVisibility deferred a pre-Start Drill hit one frame" +
                            " view=" + view.ViewID.ToString(CultureInfo.InvariantCulture) +
                            " attempt=" + (attempts + 1).ToString(CultureInfo.InvariantCulture) +
                            " frame=" + Time.frameCount.ToString(CultureInfo.InvariantCulture),
                            20);
                        return false;   // skip vanilla NOW; the replay re-enters this prefix
                    }
                    VanillaFixSupport.DiagLimited(
                        "DrillVisibility-missing-effect",
                        "DrillVisibility gave up on a pre-Start Drill child (replay cap)" +
                        " view=" + view.ViewID.ToString(CultureInfo.InvariantCulture) +
                        " frame=" + Time.frameCount.ToString(CultureInfo.InvariantCulture),
                        20);
                }
                else
                {
                    // Processed normally (repaired or nothing missing) —
                    // release the replay budget for this (possibly recycled)
                    // view id.
                    _drillReplays.Remove(view.ViewID);
                }
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("DrillVisibility.Diagnostic", ex);
            }
            return true;
        }

        private static System.Collections.IEnumerator ReplayDeferredHit(
            ProjectileHit hit, Vector2 hitPoint, Vector2 hitNormal, Vector2 vel,
            int viewID, int colliderID, bool wasBlocked)
        {
            yield return null;
            try
            {
                // The bullet may have died in the gap (round end, despawn) —
                // a lost hit there matches vanilla, which also loses it.
                if (hit != null && hit.gameObject != null)
                    hit.RPCA_DoHit(hitPoint, hitNormal, vel, viewID, colliderID, wasBlocked);
            }
            catch (Exception ex) { VanillaFixSupport.LogError("DrillVisibility.Replay", ex); }
        }

        [HarmonyPrefix]
        [HarmonyPatch(
            typeof(ChildRPC),
            "RPCA_RecieveFunction",
            new Type[] { typeof(string), typeof(Vector2) })]
        private static void DiagnoseDroppedDrillStop(
            ChildRPC __instance,
            string key)
        {
            try
            {
                if (!string.Equals(key, "DrillStop", StringComparison.Ordinal)) return;
                // Ungated (#151): log-only.

                PhotonView view = __instance.GetComponent<PhotonView>();
                if (view == null || view.IsMine) return;

                if (__instance.childRPCsVector2 == null ||
                    !__instance.childRPCsVector2.ContainsKey(key))
                {
                    VanillaFixSupport.DiagLimited(
                        "DrillVisibility-dropped-stop",
                        "DrillVisibility observed DrillStop before remote handler registration" +
                        " view=" + view.ViewID.ToString(CultureInfo.InvariantCulture) +
                        " frame=" + Time.frameCount.ToString(CultureInfo.InvariantCulture),
                        20);
                }
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("DrillVisibility.ChildRPCDiagnostic", ex);
            }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("DrillVisibility", exception);
        }
    }

    [HarmonyPatch]
    internal static class ChaseCardTextPatch
    {
        [HarmonyPostfix]
        [HarmonyPatch(typeof(CardChoice), "Awake")]
        private static void AfterCardChoiceAwake(CardChoice __instance)
        {
            try
            {
                if (__instance.cards == null) return;

                for (int i = 0; i < __instance.cards.Length; i++)
                    RemoveHealthRow(__instance.cards[i]);
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("ChaseCardText.CardChoice", ex);
            }
        }

        [HarmonyPrefix]
        [HarmonyPatch(typeof(CardInfo), "Awake")]
        private static void BeforeCardInfoAwake(CardInfo __instance)
        {
            try
            {
                RemoveHealthRow(__instance);
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("ChaseCardText.CardInfo", ex);
            }
        }

        private static void RemoveHealthRow(CardInfo card)
        {
            if (card == null || card.gameObject == null) return;

            string cardName = card.gameObject.name.Replace("(Clone)", "").Trim();
            if (!string.Equals(cardName, "Chase", StringComparison.OrdinalIgnoreCase)) return;
            if (card.cardStats == null || card.cardStats.Length == 0) return;

            List<CardInfoStat> kept = new List<CardInfoStat>(card.cardStats.Length);
            int removed = 0;
            for (int i = 0; i < card.cardStats.Length; i++)
            {
                CardInfoStat stat = card.cardStats[i];
                string label = stat == null || stat.stat == null ? "" : stat.stat.Trim();
                bool isHealth =
                    string.Equals(label, "Health", StringComparison.OrdinalIgnoreCase) ||
                    string.Equals(label, "HP", StringComparison.OrdinalIgnoreCase);

                if (isHealth)
                    removed++;
                else
                    kept.Add(stat);
            }

            if (removed == 0) return;

            card.cardStats = kept.ToArray();
            VanillaFixSupport.DiagLimited(
                "ChaseCardText-removed",
                "ChaseCardText removed_health=" +
                removed.ToString(CultureInfo.InvariantCulture) +
                " remaining=" + kept.Count.ToString(CultureInfo.InvariantCulture),
                1);
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("ChaseCardText", exception);
        }
    }

    [HarmonyPatch]
    internal static class EndScreenKillPatch
    {
        [HarmonyPrefix]
        [HarmonyPatch(
            typeof(HealthHandler),
            "DoDamage",
            new Type[]
            {
                typeof(Vector2),
                typeof(Vector2),
                typeof(Color),
                typeof(GameObject),
                typeof(Player),
                typeof(bool),
                typeof(bool),
                typeof(bool),
                typeof(HealthHandler.DamageSource)
            })]
        private static bool BeforeTransitionDamage(
            HealthHandler __instance,
            Vector2 damage,
            bool healthRemoval)
        {
            try
            {
                if (!healthRemoval) return true;
                // AnyGameScope since #151. battleOngoing is driven false by
                // RPCA_NextRound (an All-RPC) on every client, and the transition ends
                // in RevivePlayers() -> health reset everywhere, so any mixed-roster
                // disagreement inside the window is erased before combat resumes.
                // Widening strictly REDUCES the number of clients that apply
                // transition-window ticks.
                if (!VanillaFixSupport.AnyGameScope()) return true;
                if (GameManager.instance == null || GameManager.instance.battleOngoing) return true;

                VanillaFixSupport.DiagLimited(
                    "EndScreenKill-damage",
                    "EndScreenKill blocked transition DoT player=" +
                    VanillaFixSupport.PlayerId(__instance) +
                    " damage=" + VanillaFixSupport.Float(damage.magnitude) +
                    " frame=" + Time.frameCount.ToString(CultureInfo.InvariantCulture),
                    20);
                return false;
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("EndScreenKill.DoDamage", ex);
                return true;
            }
        }

        [HarmonyPrefix]
        [HarmonyPatch(
            typeof(GM_ArmsRace),
            "PlayerDied",
            new Type[] { typeof(Player), typeof(int) })]
        private static bool BeforeTransitionPlayerDied(Player killedPlayer)
        {
            try
            {
                // AnyGameScope since #151. The round advance is master-gated
                // (GM_ArmsRace only RPCs RPCA_NextRound when IsMasterClient) and rides
                // one All-RPC, so a split roster cannot diverge here — it only decides,
                // per-master, whether the fix applies at all.
                if (!VanillaFixSupport.AnyGameScope()) return true;
                if (GameManager.instance == null || GameManager.instance.battleOngoing) return true;

                VanillaFixSupport.DiagLimited(
                    "EndScreenKill-player-died",
                    "EndScreenKill ignored PlayerDied while battleOngoing=false player=" +
                    VanillaFixSupport.PlayerId(killedPlayer) +
                    " frame=" + Time.frameCount.ToString(CultureInfo.InvariantCulture),
                    20);
                return false;
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("EndScreenKill.PlayerDied", ex);
                return true;
            }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("EndScreenKill", exception);
        }
    }

    /// <summary>Bug #91 items 4/5 (July 27 log forensics): vanilla starts
    /// coroutines on INACTIVE GameObjects and Unity refuses with a console
    /// error each time (~14/session). Proven sites, all missing the
    /// activeInHierarchy guard vanilla's own HealthHandler.Revive has:
    /// RPCA_SendForceOverTime / RPCA_SendForceTowardsPointOverTime land from
    /// the same hit-volley that just killed the player (RPCA_Die SetActive
    /// false first), the DamageOverTime tick twin (now folded into
    /// PoisonDotSchedulerPatch — see the note where DeadPlayerDotPatch used to be),
    /// and CardChoiceVisuals.Hide fires while its GO is already hidden at
    /// round->pick transitions. Skipping while inactive changes nothing —
    /// Unity already refuses the StartCoroutine — it just stops the error
    /// noise that muddies every log read.</summary>
    [HarmonyPatch(typeof(HealthHandler), "RPCA_SendForceOverTime")]
    internal static class DeadPlayerForcePatch
    {
        [HarmonyPrefix]
        private static bool BeforeForceOverTime(HealthHandler __instance)
        {
            try
            {
                // Ungated (#151): Unity already refuses a StartCoroutine on an inactive
                // GameObject, so this is provably zero behavioural change — pure log
                // noise removal. Nothing to keep mode-scoped.
                if (__instance != null && !__instance.gameObject.activeInHierarchy)
                {
                    VanillaFixSupport.DiagLimited(
                        "DeadPlayerForce-skip",
                        "Skipped RPCA_SendForceOverTime on inactive player (post-death knockback)",
                        4);
                    return false;
                }
            }
            catch (Exception ex) { VanillaFixSupport.LogError("DeadPlayerForce", ex); }
            return true;
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("DeadPlayerForce", exception);
        }
    }

    [HarmonyPatch(typeof(HealthHandler), "RPCA_SendForceTowardsPointOverTime")]
    internal static class DeadPlayerForcePointPatch
    {
        [HarmonyPrefix]
        private static bool BeforeForceTowardsPoint(HealthHandler __instance)
        {
            try
            {
                // Ungated (#151) — see DeadPlayerForcePatch.
                if (__instance != null && !__instance.gameObject.activeInHierarchy)
                    return false;
            }
            catch (Exception ex) { VanillaFixSupport.LogError("DeadPlayerForcePoint", ex); }
            return true;
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("DeadPlayerForcePoint", exception);
        }
    }

    /// <summary>
    /// Bug #185 (NotNic) — the FFA "phoenix respawned me into thin air" bug.
    ///
    /// Vanilla <c>DeathEffect.RespawnPlayer</c> (DeathEffect.cs:82-95) resolves the
    /// player to revive by POSITIONAL INDEX: <c>PlayerManager.instance.players
    /// [playerIDToRevive]</c> — sound only while the list is PlayerID-indexed, which
    /// vanilla guarantees by never removing entries. FFA breaks that invariant by
    /// design: PurgeDepartedPlayers (#222) compacts the list when someone leaves, so
    /// any later Phoenix death of a player whose PlayerID >= the compacted length
    /// throws ArgumentOutOfRangeException inside the coroutine (log-proven, bug-185
    /// bundle: 3x AOORE in DeathEffect+&lt;RespawnPlayer&gt;d__21 right after
    /// "[ACH] Phoenix life consumed", immediately after "purged 1 departed player").
    ///
    /// The crash is catastrophic because <c>RPCA_Die_Phoenix</c> (HealthHandler.cs:
    /// 390-414) never sets <c>data.dead</c> — it deactivates the GameObject, sets
    /// <c>isRespawning=true</c> (which also gates out ALL damage, HealthHandler.cs:
    /// 269) and trusts the coroutine to call <c>Revive</c>. Crash the coroutine and
    /// the player is permanently alive-flagged, invisible and unhittable on EVERY
    /// client (each one purged, each one crashed): FFA counts them as the survivor,
    /// so everyone else must suicide to advance the round, and the state recurs on
    /// every later Phoenix proc. NotNic's sitting died exactly this way.
    ///
    /// Fix: replace the coroutine with a faithful copy whose lookup is BY PlayerID
    /// (the value vanilla put in the list at RegisterPlayer time), not by position.
    /// Identical behaviour whenever vanilla would not have crashed, so it is ungated
    /// (#151) like the DeadPlayerForce family. A player who genuinely left before
    /// the 2.53s charge completes simply gets no revive (vanilla crashed there too).
    /// Sound calls are individually guarded: the Sonigon voice pool NREs under load
    /// (bug-186: 673 in one session, one of which aborted a damage RPC) and a lost
    /// sound must never cost the revive.
    /// </summary>
    [HarmonyPatch(typeof(DeathEffect), "RespawnPlayer")]
    internal static class PhoenixRespawnPatch
    {
        [HarmonyPrefix]
        private static bool BeforeRespawn(DeathEffect __instance, int playerIDToRevive, ref System.Collections.IEnumerator __result)
        {
            try
            {
                __result = SafeRespawn(__instance, playerIDToRevive);
                return false;
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("PhoenixRespawn", ex);
                return true;   // fall back to vanilla wholesale — nothing applied yet
            }
        }

        // The Sonigon types (SoundManager/SoundEvent/SoundParameterIntensity)
        // live in SonigonAudioEngine.Runtime, which the csproj deliberately
        // does not reference — all sound plumbing below goes through tolerant
        // reflection, and a failed sound must never cost the revive (the
        // whole class exists because a crash in this coroutine strands a
        // player; see also bug-186's Sonigon-NRE-aborts-a-damage-RPC event).
        // Bug 223 incidental (learning #366 cause 5): this runs every 0.1s of
        // every Phoenix charge, and the old body probed a FIELD named
        // "intensity" through AccessTools first — which LOGS a HarmonyX
        // warning on every miss. The member is actually a PROPERTY, so that
        // was 1,924 warning lines (plus their disk writes) in one bug-223
        // game, on every seat, during combat — a #91-family reflection miss
        // functionally masked by the property fallback two lines later.
        // Resolution is now cached per concrete type and probes with PLAIN
        // reflection (silent on a miss, unlike AccessTools), property first.
        private static FieldInfo _fxChargeIntensityField;
        private static bool _fxChargeIntensityResolved;
        private static readonly Dictionary<Type, MemberInfo> _intensityMembers = new Dictionary<Type, MemberInfo>();

        private static void ChargeIntensity(DeathEffect fx, float value)
        {
            try
            {
                if (!_fxChargeIntensityResolved)
                {
                    _fxChargeIntensityResolved = true;
                    _fxChargeIntensityField = AccessTools.Field(typeof(DeathEffect), "soundParameterChargeLoopIntensity");
                }
                if (_fxChargeIntensityField == null) return;
                object sp = _fxChargeIntensityField.GetValue(fx);
                if (sp == null) return;
                Type t = sp.GetType();
                MemberInfo mi;
                if (!_intensityMembers.TryGetValue(t, out mi))
                {
                    mi = (MemberInfo)t.GetProperty("intensity",
                             BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance)
                         ?? t.GetField("intensity",
                             BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                    // Null is cached too: a genuinely missing member logs ONCE
                    // here instead of ten times a second (#91 — loud once,
                    // never a silent forever-no-op, never a storm).
                    _intensityMembers[t] = mi;
                    if (mi == null)
                        Plugin.Log?.LogWarning("[VANILLA-FIX] PhoenixRespawn: no 'intensity' member on "
                            + t.FullName + " — charge-loop volume will not ramp");
                }
                var pr = mi as PropertyInfo;
                if (pr != null) { if (pr.CanWrite) pr.SetValue(sp, value, null); return; }
                var f = mi as FieldInfo;
                if (f != null) f.SetValue(sp, value);
            }
            catch { }
        }

        private static void PhoenixSound(DeathEffect fx, string eventField, bool stop)
        {
            try
            {
                var f = AccessTools.Field(typeof(DeathEffect), eventField);
                object evt = f != null ? f.GetValue(fx) : null;
                if (evt == null) return;
                var smType = evt.GetType().Assembly.GetType("Sonigon.SoundManager");
                if (smType == null) return;
                object sm = AccessTools.Property(smType, "Instance")?.GetValue(null, null)
                            ?? AccessTools.Field(smType, "Instance")?.GetValue(null);
                if (sm == null) return;
                string name = stop ? "Stop" : "Play";
                // Codex code-review note: the runtime overloads carry trailing
                // OPTIONAL parameters (Stop has an optional bool), so an exact
                // 2-arg lookup misses them. Match by prefix (SoundEvent-
                // compatible, Transform) with every remaining parameter
                // optional, and invoke with their declared defaults.
                MethodInfo m = AccessTools.Method(smType, name,
                    new Type[] { evt.GetType(), typeof(Transform) });
                if (m == null)
                {
                    foreach (var cand in smType.GetMethods(BindingFlags.Public | BindingFlags.Instance))
                    {
                        if (cand.Name != name) continue;
                        var ps = cand.GetParameters();
                        if (ps.Length < 2) continue;
                        if (!ps[0].ParameterType.IsAssignableFrom(evt.GetType())) continue;
                        if (ps[1].ParameterType != typeof(Transform)) continue;
                        bool restOptional = true;
                        for (int i = 2; i < ps.Length; i++)
                            if (!ps[i].HasDefaultValue) { restOptional = false; break; }
                        if (!restOptional) continue;
                        m = cand;
                        break;
                    }
                }
                if (m == null) return;
                var pars = m.GetParameters();
                var args = new object[pars.Length];
                args[0] = evt;
                args[1] = fx.transform;
                for (int i = 2; i < pars.Length; i++) args[i] = pars[i].DefaultValue;
                m.Invoke(sm, args);
            }
            catch { }
        }

        private static System.Collections.IEnumerator SafeRespawn(DeathEffect fx, int playerIDToRevive)
        {
            // Codex design find 4: in FFA, a Phoenix that charges across a
            // point resolution must NOT fire its delayed Revive+DoBlock into
            // the NEXT round (the transition's own RevivePlayers has already
            // restored everyone; a stale revive would reset combat state and
            // fire block-card effects outside spawn grace). Fence by FFA
            // transition GENERATION captured at death: same-round recovery is
            // untouched, cross-transition revives are dropped. Non-FFA rooms
            // keep exact vanilla timing (vanilla fires the late revive too).
            bool ffaAtStart = false;
            int genAtStart = 0;
            try { ffaAtStart = FfaMode.EngineActive(); genAtStart = FfaMode.TransitionGeneration; } catch { }

            while (fx.respawnTimeCurrent < fx.respawnTime)
            {
                ChargeIntensity(fx, fx.respawnTimeCurrent / fx.respawnTime);
                fx.respawnTimeCurrent += 0.1f;
                yield return new WaitForSeconds(0.1f);
            }
            PhoenixSound(fx, "soundPhoenixRespawn", stop: false);
            PhoenixSound(fx, "soundPhoenixChargeLoop", stop: true);

            if (ffaAtStart)
            {
                bool stale = false;
                try { stale = !FfaMode.EngineActive() || FfaMode.TransitionGeneration != genAtStart; }
                catch { }
                if (stale)
                {
                    VanillaFixSupport.DiagLimited(
                        "PhoenixRespawn-transition-fence",
                        "PhoenixRespawn: FFA transition crossed during the charge — stale revive for PlayerID=" +
                        playerIDToRevive.ToString(CultureInfo.InvariantCulture) +
                        " dropped (round revive already restored everyone)",
                        10);
                    yield break;
                }
            }

            Player target = null;
            try
            {
                var players = PlayerManager.instance != null ? PlayerManager.instance.players : null;
                if (players != null)
                {
                    for (int i = 0; i < players.Count; i++)
                    {
                        var p = players[i];
                        if (p != null && p.gameObject != null && p.PlayerID == playerIDToRevive)
                        {
                            target = p;
                            // One-shot proof when the by-ID lookup actually
                            // diverged from vanilla's positional read (#83/#286).
                            if (i != playerIDToRevive)
                                VanillaFixSupport.DiagLimited(
                                    "PhoenixRespawn-index-divergence",
                                    "PhoenixRespawn revived PlayerID=" +
                                    playerIDToRevive.ToString(CultureInfo.InvariantCulture) +
                                    " found at list index " + i.ToString(CultureInfo.InvariantCulture) +
                                    " (vanilla would have crashed or revived the wrong player)",
                                    10);
                            break;
                        }
                    }
                }
            }
            catch (Exception ex) { VanillaFixSupport.LogError("PhoenixRespawn.Lookup", ex); }

            if (target == null || target.data == null || target.data.healthHandler == null)
            {
                VanillaFixSupport.DiagLimited(
                    "PhoenixRespawn-target-gone",
                    "PhoenixRespawn: PlayerID=" +
                    playerIDToRevive.ToString(CultureInfo.InvariantCulture) +
                    " no longer resolvable at respawn time — revive skipped",
                    10);
                yield break;
            }

            try
            {
                target.data.healthHandler.Revive(isFullRevive: false);
                if (target.data.block != null) target.data.block.RPCA_DoBlock(firstBlock: true);
            }
            catch (Exception ex) { VanillaFixSupport.LogError("PhoenixRespawn.Revive", ex); }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("PhoenixRespawn", exception);
        }
    }

    /// <summary>Bug 225 ("hitting enemies on my screen isn't doing damage")
    /// — the POISON half of the #186 Drill registration race, repaired the
    /// same way (see DiagnoseMissingDrillEffect above; learning #366 cause 1/2).
    ///
    /// On a REMOTE bullet copy, RPCA_Init can attach card children AFTER
    /// ProjectileHit.Start snapshotted `effects`, and an empty/stale list is
    /// SILENTLY skipped — no exception, no counter (decompile
    /// ProjectileHit.cs:321). For RayHitPoison that silent skip is the whole
    /// bug-225 mechanism: poison zeroes the bullet's direct damage (its
    /// Start sets bulletCanDealDeamage=false, so the direct hit deals ~1)
    /// and carries ALL of its damage in the DOT — and under the PoisonSync
    /// protocol the DOT authority arms on the VICTIM'S seat only when the
    /// victim's own replica runs RayHitPoison.DoHitEffect. A victim replica
    /// that missed registration = 16 silent streams in one game: full
    /// knockback, no damage, on every seat.
    ///
    /// Unlike Drill, NO deferred replay is needed: RayHitPoison.Start's only
    /// statement mutates the PARENT (bulletCanDealDeamage=false), and
    /// DoHitEffect reads nothing that Start initializes — it resolves
    /// everything via GetComponentInParent at call time (decompile
    /// RayHitPoison.cs), so a pre-Start child is safe to register
    /// immediately (#211's trap does not apply); we mirror its Start's
    /// parent mutation ourselves. PLAYER hits only (viewID != -1): a
    /// surface has no DamageOverTime component, so poison no-ops there
    /// anyway. Remote copies only (IsMine false): the owner's BulletInit
    /// runs synchronously before its own Start, so the owner's snapshot is
    /// always complete. AnyGameScope like the Drill repair (#286):
    /// converging a remote toward owner-authoritative behaviour is safe in
    /// mixed rosters.</summary>
    [HarmonyPatch]
    internal static class PoisonEffectRegistrationPatch
    {
        [HarmonyPrefix]
        [HarmonyPatch(
            typeof(ProjectileHit),
            "RPCA_DoHit",
            new Type[]
            {
                typeof(Vector2), typeof(Vector2), typeof(Vector2),
                typeof(int), typeof(int), typeof(bool)
            })]
        private static void RepairPoisonRegistration(ProjectileHit __instance, int viewID)
        {
            try
            {
                if (viewID == -1) return;
                if (!VanillaFixSupport.AnyGameScope()) return;
                if (__instance == null) return;
                PhotonView view = __instance.GetComponent<PhotonView>();
                if (view == null || view.IsMine) return;
                RayHitPoison[] poisons = __instance.GetComponentsInChildren<RayHitPoison>(true);
                if (poisons == null || poisons.Length == 0) return;

                if (__instance.effects == null)
                    __instance.effects = new System.Collections.Generic.List<RayHitEffect>();

                int repaired = 0;
                for (int i = 0; i < poisons.Length; i++)
                {
                    if (poisons[i] == null) continue;
                    if (__instance.effects.Contains(poisons[i])) continue;
                    __instance.effects.Add(poisons[i]);
                    repaired++;
                }

                if (repaired > 0)
                {
                    // Mirror RayHitPoison.Start's parent mutation — the
                    // child may not have Started yet, and the field is what
                    // keeps poison's direct damage at ~1 on every seat.
                    __instance.bulletCanDealDeamage = false;
                    __instance.ResortHitEffects();
                    VanillaFixSupport.DiagLimited(
                        "PoisonRegistration-repair",
                        "PoisonRegistration re-registered " +
                        repaired.ToString(CultureInfo.InvariantCulture) +
                        " RayHitPoison child(ren) missing from ProjectileHit.effects" +
                        " view=" + view.ViewID.ToString(CultureInfo.InvariantCulture) +
                        " frame=" + Time.frameCount.ToString(CultureInfo.InvariantCulture),
                        20);
                }
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("PoisonRegistration", ex);
            }
        }

        /// <summary>Review r1 HIGH: the prefix above can insert a RayHitPoison
        /// BEFORE the bullet's own Start has run (a blocked hit reflects and
        /// the bullet lives on); vanilla Start then appends its children
        /// unconditionally, leaving the SAME component in `effects` twice —
        /// and a later hit would run DoHitEffect twice, publishing two full
        /// DOT streams room-wide (double poison damage). Reference-dedupe in
        /// a Start POSTFIX: order-preserving, first occurrence wins, and it
        /// also retroactively repairs any other duplicate-registration
        /// source on any bullet.</summary>
        [HarmonyPostfix]
        [HarmonyPatch(typeof(ProjectileHit), "Start")]
        private static void DedupeEffectsAfterStart(ProjectileHit __instance)
        {
            try
            {
                var list = __instance != null ? __instance.effects : null;
                if (list == null || list.Count < 2) return;
                int removed = 0;
                for (int i = list.Count - 1; i >= 1; i--)
                {
                    for (int j = 0; j < i; j++)
                    {
                        if (ReferenceEquals(list[i], list[j]))
                        {
                            list.RemoveAt(i);
                            removed++;
                            break;
                        }
                    }
                }
                if (removed > 0)
                    VanillaFixSupport.DiagLimited(
                        "PoisonRegistration-dedupe",
                        "PoisonRegistration removed " +
                        removed.ToString(CultureInfo.InvariantCulture) +
                        " duplicate effect reference(s) after ProjectileHit.Start",
                        20);
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("PoisonRegistration.Dedupe", ex);
            }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("PoisonRegistration", exception);
        }
    }

    /// <summary>Bug #217 (Aug 13 FFA "latency lag with bullets and player
    /// positions") — mechanism CORRECTED post-ship (Codex ultra, Aug 15;
    /// learning #366 supersedes #362's queue story): an exception thrown
    /// inside a PunRPC body propagates out through ExecuteRpc into
    /// PhotonHandler.Dispatch's per-command loop, whose catch RECORDS the
    /// exception and KEEPS DRAINING — the batch is NOT aborted and no
    /// position/serialization update is deferred (decompile: Dispatch()'s
    /// while-loop catch stores ex and continues; production logs carry
    /// "Caught 2 exception(s)" aggregates, impossible under an abort).
    /// What each fault actually cost on 1.38.5: exception + stack-capture
    /// construction and a multi-line log burst (I/O) per fault, the
    /// AggregateException rethrow unwinding out of FixedUpdate, and the
    /// faulting command's own post-callback cleanup being skipped. This
    /// guard removes those costs and feeds the [NET] counter; it does NOT
    /// rescue deliveries — the faults are SYMPTOMS of dead/diverged
    /// projectile replicas (#366's causal model), which is where the real
    /// fixes live. 23 faults in the bug-217 session, 87 in bug-214's
    /// (v1.38.4), so the class long predates the Radiance change. RPCA_DoHit
    /// is the only RPC observed faulting: its body dereferences
    /// GetPhotonView(viewID) results, the map collider array and component
    /// lookups with no null checks, so a hit replicated after this client
    /// already retired the target NREs (decompile ProjectileHit.cs:199+).
    /// SCOPE note (#366): RpcTarget.All executes locally SYNCHRONOUSLY, so
    /// this finalizer also lets the SHOOTER's caller (e.g. RayCastTrail.
    /// Update) continue past a failed local hit where 1.38.5 unwound one
    /// component's frame — no damage-suppression path exists either way,
    /// but the containment is broader than "incoming dispatch".
    ///
    /// SWALLOW-ONLY, strictly better than the status quo: today the NRE
    /// aborts RPCA_DoHit at some statement AND kills the rest of the Photon
    /// batch; with the finalizer the body aborts at the same statement and
    /// the batch survives. No new divergence is introduced — whatever this
    /// client missed was already missed the moment the throw happened.
    /// #322's DoDamage rule, stated precisely (review r1 find 2 corrected
    /// this comment's first draft): an exception thrown INSIDE DoDamage —
    /// after its health commit, before its death RPC — DOES propagate up
    /// through RPCA_DoHit into this finalizer, so partial-DoDamage state
    /// (e.g. a negative-health live replica) remains reachable. It is
    /// reachable IDENTICALLY without this guard: vanilla never caught the
    /// throw either, so the replica state is byte-for-byte the same in both
    /// worlds. The swallow changes exactly one thing — that already-thrown
    /// exception no longer takes the rest of Photon's dispatch batch with
    /// it. No new state exists.
    ///
    /// UNGATED (#151/#286): a local crash guard has no cross-client
    /// semantics, and gating would exclude the room-code games where most
    /// rated play happens.</summary>
    [HarmonyPatch]
    internal static class RpcDoHitDispatchGuardPatch
    {
        static IEnumerable<MethodBase> TargetMethods()
        {
            // By name, all overloads (#324c); a signature drift in a game
            // patch must break loudly at attach, never silently no-op (#83).
            var list = new List<MethodBase>();
            foreach (var m in typeof(ProjectileHit).GetMethods(AccessTools.all))
                if (m.Name == "RPCA_DoHit") list.Add(m);
            if (list.Count == 0)
                throw new Exception("ProjectileHit.RPCA_DoHit not found — dispatch guard has no target");
            return list;
        }

        [HarmonyFinalizer]
        private static Exception Finalizer(Exception __exception)
        {
            if (__exception != null)
            {
                NetDiag.CountRpcSwallow();
                VanillaFixSupport.DiagLimited(
                    "RpcDoHitDispatchGuard-swallowed",
                    "RPCA_DoHit threw " + __exception.GetType().Name +
                    " — swallowed so Photon's incoming dispatch batch survives (" +
                    __exception.Message + ")",
                    20);
            }
            return null;
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("RpcDoHitDispatchGuard", exception);
        }
    }

    /// <summary>Companion to the dispatch guard: FriendlyFoe's pooled-bullet
    /// teardown NREs when a bullet dies before BulletPoolInstancer.Start ran
    /// (#94/#156 — the pool wrapper is wired in Start), and the throw rides
    /// whatever stack destroyed the bullet — including Photon's dispatch loop
    /// (Ev Destroy) and scene teardown. 85 in the bug-217 session, 179 in
    /// bug-214's. Swallowing does not repair the pool accounting (the
    /// instance was never returned — exactly as before), it stops the throw
    /// from escaping into the destroyer's stack. Type resolved by name: the
    /// FriendlyFoe types live in Assembly-CSharp but OnDestroy is private
    /// and the by-name TargetMethods throws if the game update renames it
    /// (#83/#91 — never a silent no-op).</summary>
    [HarmonyPatch]
    internal static class BulletPoolReleaseGuardPatch
    {
        static IEnumerable<MethodBase> TargetMethods()
        {
            var t = AccessTools.TypeByName("FriendlyFoe.BulletPoolInstancer");
            var m = t == null ? null : AccessTools.Method(t, "OnDestroy");
            if (m == null)
                throw new Exception("FriendlyFoe.BulletPoolInstancer.OnDestroy not found — pool guard has no target");
            return new List<MethodBase> { m };
        }

        [HarmonyFinalizer]
        private static Exception Finalizer(Exception __exception)
        {
            if (__exception != null)
            {
                NetDiag.CountPoolSwallow();
                VanillaFixSupport.DiagLimited(
                    "BulletPoolReleaseGuard-swallowed",
                    "BulletPoolInstancer.OnDestroy threw " + __exception.GetType().Name +
                    " — swallowed (pre-Start bullet death; pool entry was never registered)",
                    20);
            }
            return null;
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("BulletPoolReleaseGuard", exception);
        }
    }

    /// <summary>Bug 260 field diagnostic (LOG-ONLY, changes no behaviour):
    /// "invisible Toxic Cloud" — the victim seat shows no cloud while the
    /// owner-authoritative slow/damage (Explosion.cs:102-143, owner-seat
    /// RPCs) still land. Two prior fix designs were refuted in review, so
    /// this patch only MEASURES the surviving mechanism candidates at the
    /// ENTRY of ProjectileHit.RPCA_DoHit (before any vanilla processing; no
    /// explicit Harmony ordering vs the other prefixes on this method is
    /// declared or needed — none of them mutates what is measured here):
    ///
    ///  1. TARGET-VIEW-GONE: viewID != -1 but PhotonNetwork.GetPhotonView
    ///     returns null. If THIS invocation reaches vanilla, it NREs at the
    ///     target dereference (decompile ProjectileHit.cs:211-212) and the
    ///     dispatch guard swallows it — the hit body, spawn loop at :303
    ///     included, is lost on this seat only. The line does NOT prove
    ///     vanilla ran: the Drill prefix can defer the same invocation
    ///     (returns false, replays next frame — the replay re-enters this
    ///     prefix, so a deferred hit can print twice with different frame
    ///     stamps). The bug-260 bundle carries 3 swallowed RPCA_DoHit NREs
    ///     inside the reported 85-second window; this counter ties (or
    ///     fails to tie) that class to hits, with the spawn-list length.
    ///  2. REPLICA-EMPTY-SPAWNLIST: a remote copy whose Owner is ASSIGNED
    ///     processing a hit with an empty objectsToSpawn while that owner's
    ///     gun ON THIS SEAT currently has entries. NOT proof of divergence
    ///     on its own — a bullet fired before the owner's last card change
    ///     legitimately matches (round-tail bullets, rebuild boundaries);
    ///     the [FFA-GUNAUDIT] apply stamps are what dates the gun state
    ///     during analysis. Owner-null hits are counted under a SEPARATE
    ///     key/budget (review find 1: most Owner-null empty-list hits are
    ///     ordinary pre-init bullets that may carry no spawn cards at all,
    ///     and must not drain this key).
    ///
    /// This prefix is void — it never asks Harmony to skip the original
    /// (another prefix on the same method still can, see above). Budgets are
    /// PER SITTING: all keys reset on the room-leave edges alongside the
    /// sweep key (review find 1's exhaustion arm — a process-lifetime budget
    /// spent on game 1 noise would blind every later game). UNGATED like the
    /// other log-only diagnostics (#151).</summary>
    [HarmonyPatch]
    internal static class SpawnOnImpactFieldDiagPatch
    {
        internal const string FfaAuditFailKey = "FfaGunAudit-failed";

        // Reset together at the room-leave edges (both the reliable callback
        // and the lossy poll backup), exactly like the sweep key.
        internal static readonly string[] DiagKeys = new[]
        {
            "SpawnDiag-target-view-gone",
            "SpawnDiag-preinit-empty",
            "SpawnDiag-replica-empty-spawnlist",
            "SpawnDiag-dead-effect",
            "SpawnDiag-not-allowed",
            FfaAuditFailKey,
        };

        internal static void ResetBudgets()
        {
            for (int i = 0; i < DiagKeys.Length; i++)
            {
                try { VanillaFixSupport.ResetDiag(DiagKeys[i]); } catch { }
            }
        }

        [HarmonyPrefix]
        [HarmonyPatch(
            typeof(ProjectileHit),
            "RPCA_DoHit",
            new Type[]
            {
                typeof(Vector2), typeof(Vector2), typeof(Vector2),
                typeof(int), typeof(int), typeof(bool)
            })]
        private static void ObserveHit(
            ProjectileHit __instance, int viewID, int colliderID, bool wasBlocked)
        {
            try
            {
                if (__instance == null) return;
                PhotonView view = __instance.GetComponent<PhotonView>();
                var ots = __instance.objectsToSpawn;
                int otsLen = ots == null ? 0 : ots.Length;

                // Candidate 1: the hit target's view is unresolved on this
                // seat at hit entry (vanilla NREs at :212 if it runs — see
                // the class comment for the deferred-invocation caveat).
                if (viewID != -1 && PhotonNetwork.GetPhotonView(viewID) == null)
                {
                    VanillaFixSupport.DiagLimited(
                        "SpawnDiag-target-view-gone",
                        "SpawnDiag hit target view " +
                        viewID.ToString(CultureInfo.InvariantCulture) +
                        " unresolved at hit entry" +
                        " bulletView=" + (view == null ? "null" : view.ViewID.ToString(CultureInfo.InvariantCulture)) +
                        " mine=" + (view != null && view.IsMine) +
                        " spawnEntries=" + otsLen.ToString(CultureInfo.InvariantCulture) +
                        " blocked=" + wasBlocked +
                        " frame=" + Time.frameCount.ToString(CultureInfo.InvariantCulture),
                        30);
                }

                if (view == null || view.IsMine) return;

                if (otsLen == 0)
                {
                    var init = __instance.GetComponent<ProjectileInit>();
                    Player owner = init == null ? null : init.Owner;
                    if (owner == null)
                    {
                        // Init-race family tally only: with no owner there is
                        // no way to know whether spawn entries were due, so
                        // this key must never be read as bug-260 evidence by
                        // itself (review find 1).
                        VanillaFixSupport.DiagLimited(
                            "SpawnDiag-preinit-empty",
                            "SpawnDiag remote copy hit pre-init (Owner null, empty spawn list)" +
                            " view=" + view.ViewID.ToString(CultureInfo.InvariantCulture) +
                            " target=" + viewID.ToString(CultureInfo.InvariantCulture) +
                            "/" + colliderID.ToString(CultureInfo.InvariantCulture) +
                            " frame=" + Time.frameCount.ToString(CultureInfo.InvariantCulture),
                            20);
                        return;
                    }
                    int ownerGunLen = -1;
                    try
                    {
                        var gun = owner.data != null && owner.data.weaponHandler != null
                            ? owner.data.weaponHandler.gun : null;
                        if (gun != null && gun.objectsToSpawn != null)
                            ownerGunLen = gun.objectsToSpawn.Length;
                    }
                    catch { }
                    if (ownerGunLen > 0)
                    {
                        VanillaFixSupport.DiagLimited(
                            "SpawnDiag-replica-empty-spawnlist",
                            "SpawnDiag remote copy hit with EMPTY objectsToSpawn while owner's CURRENT gun has " +
                            ownerGunLen.ToString(CultureInfo.InvariantCulture) +
                            " entr(ies) on this seat (bullet may predate the last card change — date via FFA-GUNAUDIT)" +
                            " ownerPid=" + owner.PlayerID.ToString(CultureInfo.InvariantCulture) +
                            " view=" + view.ViewID.ToString(CultureInfo.InvariantCulture) +
                            " target=" + viewID.ToString(CultureInfo.InvariantCulture) +
                            "/" + colliderID.ToString(CultureInfo.InvariantCulture) +
                            " blocked=" + wasBlocked +
                            " frame=" + Time.frameCount.ToString(CultureInfo.InvariantCulture),
                            30);
                    }
                    return;
                }

                // Dead-reference sweep: an entry whose effect AND
                // AddToProjectile are both null spawns nothing, silently
                // (decompile ObjectsToSpawn.cs:72 gates on the effect).
                int dead = 0;
                for (int i = 0; i < ots.Length; i++)
                    if (ots[i] != null && ots[i].effect == null && ots[i].AddToProjectile == null)
                        dead++;
                if (dead > 0)
                {
                    VanillaFixSupport.DiagLimited(
                        "SpawnDiag-dead-effect",
                        "SpawnDiag remote copy carries " +
                        dead.ToString(CultureInfo.InvariantCulture) +
                        " spawn entr(ies) with null effect" +
                        " view=" + view.ViewID.ToString(CultureInfo.InvariantCulture) +
                        " frame=" + Time.frameCount.ToString(CultureInfo.InvariantCulture),
                        20);
                }

                if (!__instance.isAllowedToSpawnObjects)
                {
                    VanillaFixSupport.DiagLimited(
                        "SpawnDiag-not-allowed",
                        "SpawnDiag remote copy has isAllowedToSpawnObjects=false with " +
                        otsLen.ToString(CultureInfo.InvariantCulture) + " spawn entr(ies)" +
                        " view=" + view.ViewID.ToString(CultureInfo.InvariantCulture) +
                        " frame=" + Time.frameCount.ToString(CultureInfo.InvariantCulture),
                        10);
                }
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("SpawnOnImpactFieldDiag", ex);
            }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("SpawnOnImpactFieldDiag", exception);
        }
    }

    /// <summary>Bug #217's biggest diagnostic gap (both sweep agents, verdict
    /// A6): the log carries no rtt/fps/dispatch-health timeline at all, so
    /// "mild-moderate latency" could not be quantified from a bundle — the
    /// local-framerate answer had to be reverse-engineered from frame counters
    /// embedded in unrelated [VANILLA-DIAG] lines. One Info line every 10s
    /// while in an online room. Counters are process-cumulative; the line
    /// prints per-interval deltas so any single line reads in isolation.
    /// Called from GameStateWatcher.TickFrame BEFORE its spectator
    /// early-return — the spectator seat needs this line most.</summary>
    internal static class NetDiag
    {
        private static float _lastLog = -999f;
        private static int _lastFrame;
        private static int _rpcSwallows, _lastRpcSwallows;
        private static int _poolSwallows, _lastPoolSwallows;
        private static int _orphanSkips, _lastOrphanSkips;

        internal static void CountRpcSwallow() { _rpcSwallows++; }
        internal static void CountPoolSwallow() { _poolSwallows++; }
        internal static void CountOrphanSerialization() { _orphanSkips++; }
        // SpectatorPatches' existing mute counts the same PUN missing-view
        // branch before suppressing its warning. Keep the old name as an alias
        // so fighter and spectator seats feed one interval counter exactly once.
        internal static void CountOrphanSkip() { CountOrphanSerialization(); }
        // Room callbacks rebase the interval counter so a fast leave/rejoin
        // cannot attribute room A's unsampled orphan tail to room B's first
        // [NET] line. The monotonic process total remains untouched.
        internal static void RebaseOrphanCounter() { _lastOrphanSkips = _orphanSkips; }

        internal static void Tick()
        {
            float now = Time.unscaledTime;
            if (now - _lastLog < 10f) return;
            bool inRoom = false;
            int actors = 0;
            try
            {
                inRoom = PhotonNetwork.InRoom && !PhotonNetwork.OfflineMode;
                if (inRoom && PhotonNetwork.CurrentRoom != null)
                    actors = PhotonNetwork.CurrentRoom.PlayerCount;
            }
            catch { }
            if (inRoom)
            {
                int fps = (int)((Time.frameCount - _lastFrame) / Mathf.Max(0.01f, now - _lastLog));
                int ping = 0;
                try { ping = PhotonNetwork.GetPing(); } catch { }
                Plugin.Log?.LogInfo(
                    $"[NET] ping={ping}ms fps~{fps} actors={actors}" +
                    $" rpcSwallow=+{_rpcSwallows - _lastRpcSwallows}" +
                    $" poolSwallow=+{_poolSwallows - _lastPoolSwallows}" +
                    $" orphanSer=+{_orphanSkips - _lastOrphanSkips}");
            }
            // Baselines re-sync every interval, in-room or not, so the first
            // in-room line after a menu stretch spans at most one interval.
            _lastLog = now;
            _lastFrame = Time.frameCount;
            _lastRpcSwallows = _rpcSwallows;
            _lastPoolSwallows = _poolSwallows;
            _lastOrphanSkips = _orphanSkips;
        }
    }

    /// <summary>
    /// Sonigon damage-path guards (bug-186 follow-up; Codex Grow-review find 4
    /// made them load-bearing for the Phoenix fix too).
    ///
    /// Observed in the bug-186 bundle (~line 8520): an incoming
    /// RPCA_SendTakeDamage aborted mid-application — DoDamage → DealtDamage →
    /// Heal (lifesteal) → Sonigon Voice NRE — and because DoDamage calls
    /// DealtDamage BEFORE <c>data.health -=</c>, the victim's ENTIRE health
    /// delta was lost on that client only. ROUNDS never re-syncs health
    /// outside death RPCs, so one sound failure produced a persistent
    /// cross-client health desync (673 Sonigon voice NREs in that single
    /// session). The same class can strand a Phoenix player:
    /// RPCA_Die_Phoenix and DeathEffect.PlayDeath both play sounds between
    /// <c>isRespawning=true</c> and StartCoroutine(RespawnPlayer) — a throw
    /// there leaves an inactive, unrevivable player before PhoenixRespawnPatch
    /// can ever run.
    ///
    /// Three swallow-and-count Finalizers, all ungated (#151): every guarded
    /// path is one where vanilla aborts GAMEPLAY for a cosmetic failure —
    /// swallowing is strictly better in every reachable case.
    /// HealthHandler.DoDamage deliberately gets NO finalizer: a swallow
    /// between its health commit and the death RPC could suppress a death —
    /// the one place this pattern would be dangerous.
    /// </summary>
    [HarmonyPatch(typeof(CharacterStatModifiers), "DealtDamage")]
    internal static class DealtDamageGuardPatch
    {
        [HarmonyFinalizer]
        private static Exception Finalizer(Exception __exception)
        {
            if (__exception != null)
                VanillaFixSupport.DiagLimited(
                    "DealtDamageGuard-swallowed",
                    "DealtDamage threw " + __exception.GetType().Name +
                    " — swallowed so the victim's damage application commits (" +
                    __exception.Message + ")",
                    20);
            return null;
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("DealtDamageGuard", exception);
        }
    }

    [HarmonyPatch(typeof(HealthHandler), "Heal")]
    internal static class HealSoundGuardPatch
    {
        [HarmonyFinalizer]
        private static Exception Finalizer(Exception __exception)
        {
            if (__exception != null)
                VanillaFixSupport.DiagLimited(
                    "HealSoundGuard-swallowed",
                    "Heal threw " + __exception.GetType().Name +
                    " — swallowed so the caller continues (" + __exception.Message + ")",
                    20);
            return null;
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("HealSoundGuard", exception);
        }
    }

    /// <summary>Every public Play/PlayAtPosition/Stop overload on
    /// Sonigon.SoundManager (the assembly is not referenced — resolved by
    /// name). A sound-engine throw can only ever abort its CALLER, which is
    /// never desirable; this also covers the two Phoenix death-path calls and
    /// DoDamage's tail lifesteal sound, and silences the rope-hum Update
    /// aborts. Throws in TargetMethods = loud patch failure (#83), never a
    /// silent no-op.</summary>
    [HarmonyPatch]
    internal static class SonigonPlayGuardPatch
    {
        private static IEnumerable<MethodBase> TargetMethods()
        {
            var t = AccessTools.TypeByName("Sonigon.SoundManager");
            if (t == null)
                throw new InvalidOperationException("SonigonPlayGuard: Sonigon.SoundManager not found");
            var list = new List<MethodBase>();
            foreach (var m in t.GetMethods(BindingFlags.Public | BindingFlags.Instance))
            {
                if (m.Name != "Play" && m.Name != "PlayAtPosition" && m.Name != "Stop") continue;
                if (m.IsGenericMethodDefinition) continue;
                list.Add(m);
            }
            if (list.Count == 0)
                throw new InvalidOperationException("SonigonPlayGuard: no Play/Stop overloads found");
            return list;
        }

        [HarmonyFinalizer]
        private static Exception Finalizer(Exception __exception)
        {
            if (__exception != null)
                VanillaFixSupport.DiagLimited(
                    "SonigonPlayGuard-swallowed",
                    "Sonigon Play/Stop threw " + __exception.GetType().Name +
                    " — swallowed (a sound failure must never abort gameplay)",
                    20);
            return null;
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("SonigonPlayGuard", exception);
        }
    }

    /// <summary>Aug 11 (bug-198 log): 555 NREs in one spectator session from
    /// Sonigon.Internal.Voice.SetVolumeRatioUpdate — a voice holding a
    /// destroyed AudioSource (PUN's duplicate-ID RemoveInstantiatedGO killed
    /// its host mid-life). The throw propagates to SoundManager.Update and
    /// aborts the WHOLE manager loop every frame, starving every healthy
    /// voice's update too. InstanceSoundEvent.ManagedUpdate is the per-
    /// instance containment boundary: swallowing there skips only the broken
    /// instance's frame and is robust to WHICH internal leaf throws. Pure
    /// audio state — no gameplay can abort here. Play/Stop calls are the
    /// sibling patch above (#322).</summary>
    [HarmonyPatch]
    internal static class SonigonVoiceUpdateGuardPatch
    {
        private static MethodBase TargetMethod()
        {
            var t = AccessTools.TypeByName("Sonigon.Internal.InstanceSoundEvent");
            if (t == null)
                throw new InvalidOperationException("SonigonVoiceUpdateGuard: Sonigon.Internal.InstanceSoundEvent not found");
            var m = AccessTools.Method(t, "ManagedUpdate");
            if (m == null)
                throw new InvalidOperationException("SonigonVoiceUpdateGuard: ManagedUpdate not found");
            return m;
        }

        /// <summary>Bug 210: swallowing was necessary but NOT sufficient — it
        /// contained the exception and leaked the instance.
        ///
        /// InstanceSoundEvent.ManagedUpdate ends with the instance's ONLY
        /// self-retirement path (`waitingForPooling = true; PoolAllVoices(...)`),
        /// and SoundManagerData.ManagedUpdate reads that flag immediately after
        /// the call returns to remove the instance, pool its voices and
        /// deactivate it. So a throw BEFORE that tail — which this finalizer
        /// then turns into a clean return — means the instance is never
        /// retired, its AudioSources are never pooled, and it stays in the
        /// managed-update list throwing again every frame. A monotonic leak.
        ///
        /// Once SoundManagerVoicePool saturates (every voice isAssigned, and a
        /// leaked voice is assigned forever) every new Play enters the
        /// voice-STEALING branch and rips the voice with the lowest
        /// volume*priority away from a healthy sound. ROUNDS' events are
        /// layered SoundContainers, so the quiet layers are stolen first —
        /// which is exactly "intermittently muffled or suppressed", getting
        /// worse across a session and never recovering before relaunch.
        /// A spectator seat is the highest-rate producer of destroyed sound
        /// hosts (join-time burial + PUN destroys), which is why it surfaced
        /// there first.
        ///
        /// Retire the instance ourselves, VOICE BY VOICE. Flag FIRST: even if
        /// the pooling throws, ManagedUpdate returns at its first statement on
        /// every later frame, so the per-frame storm stops either way.
        ///
        /// Per-voice matters (Codex cold review, finding 3): retiring through
        /// the single PoolAllVoices call left the leak reachable one layer
        /// down. That call is one nested loop over every voice, so a throw
        /// while pooling voice (i,j) — and the broken voice is precisely the
        /// one that just threw out of ManagedUpdate — abandons every voice
        /// AFTER it. SoundManagerData then removes and deactivates the
        /// instance on the waitingForPooling flag regardless, so those later,
        /// HEALTHY voices stay isAssigned forever. Same saturation, same
        /// muffling, just slower. PoolSingleVoice is public and drives one
        /// voice at a time, so each gets its own catch.</summary>
        [HarmonyFinalizer]
        private static Exception Finalizer(object __instance, Exception __exception)
        {
            if (__exception == null) return null;
            VanillaFixSupport.DiagLimited(
                "SonigonVoiceUpdateGuard-swallowed",
                "InstanceSoundEvent.ManagedUpdate threw " + __exception.GetType().Name +
                " — swallowed and the instance retired so its voices return to the pool",
                20);
            // __instance is typed object deliberately: the Sonigon assembly is
            // resolved by name (AccessTools.TypeByName) and is not referenced by
            // the csproj, so we cannot name the type in a signature.
            try
            {
                if (__instance != null)
                {
                    var t = __instance.GetType();
                    AccessTools.Field(t, "waitingForPooling")?.SetValue(__instance, true);
                    if (!PoolVoicesIndividually(__instance, t))
                    {
                        // Structure not walkable — the instance still has to be
                        // retired, so fall back to vanilla's own tail call:
                        // PoolAllVoices(allowFadeOut: false,
                        //               isCalledByStopFunction: false).
                        // Logged rather than silent: a reflected name that no
                        // longer exists must never become a forever no-op (#91).
                        VanillaFixSupport.DiagLimited(
                            "SonigonVoiceUpdateGuard-poolwalk",
                            "InstanceSoundEvent voice structure not walkable — falling back to whole-instance PoolAllVoices",
                            5);
                        try
                        {
                            AccessTools.Method(t, "PoolAllVoices")?
                                .Invoke(__instance, new object[] { false, false, false });
                        }
                        catch { }
                    }
                }
            }
            catch { }
            return null;
        }

        /// <summary>Return every voice of one InstanceSoundEvent to the pool,
        /// one voice at a time, each in its own catch.
        ///
        /// Behaviourally identical to vanilla's
        /// PoolAllVoices(allowFadeOut: false, isCalledByStopFunction: false):
        /// that method's whole body (decompile —
        /// logs-snapshot/decompiled/sonigon/InstanceSoundEvent.cs:470) is this
        /// nested loop plus two blocks that are BOTH gated on
        /// isCalledByStopFunction / triggerOnStopEnable and so are dead for
        /// those arguments. The argument triple below is vanilla's own:
        /// shouldRestartIfLoop false, allowFadeOut false, isCalledByOnDestroy
        /// false.
        ///
        /// Returns false when the structure could not be walked AT ALL, so the
        /// caller falls back to the single call instead of quietly pooling
        /// nothing.</summary>
        private static bool PoolVoicesIndividually(object inst, Type t)
        {
            var holders = AccessTools.Field(t, "instanceSoundContainerHolder")?.GetValue(inst) as Array;
            var poolOne = AccessTools.Method(t, "PoolSingleVoice");
            if (holders == null || poolOne == null) return false;
            bool walked = false;
            for (int i = 0; i < holders.Length; i++)
            {
                object holder = null;
                try { holder = holders.GetValue(i); } catch { }
                if (holder == null) continue;
                Array voices = null;
                try { voices = AccessTools.Field(holder.GetType(), "voiceHolder")?.GetValue(holder) as Array; }
                catch { }
                if (voices == null) continue;
                for (int j = 0; j < voices.Length; j++)
                {
                    walked = true;
                    // One dead voice must not strand its siblings — that is the
                    // entire difference from the whole-instance call.
                    try { poolOne.Invoke(inst, new object[] { i, j, false, false, false }); }
                    catch { }
                }
            }
            return walked;
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("SonigonVoiceUpdateGuard", exception);
        }
    }

    // DeadPlayerDotPatch used to live here — a second Harmony Prefix on
    // DamageOverTime.TakeDamageOverTime whose only job was to skip the call while the
    // host GameObject was inactive. It has been FOLDED into
    // PoisonDotSchedulerPatch.Prefix (PoisonSync.cs) as step 1 and the class deleted.
    //
    // This is not tidying. Two prefixes on one method have UNDEFINED relative order,
    // and Harmony skips every subsequent prefix once one returns false — so with the
    // poison scheduler also prefixing this method, whichever ran first would silently
    // decide whether the other ran at all. One merged prefix removes the hazard
    // outright and makes the ordering explicit and reviewable.

    /// <summary>
    /// Bug #186 (Sid) — GROW's damage growth is exponential in FRAME TIME.
    ///
    /// The GROW card is vanilla's <c>TrickShot</c> component. Per Update frame it
    /// does (TrickShot.cs:66-83):
    ///
    ///   num  = Δdistance this frame                        (≈ v·dt)
    ///   num2 = 1 + num · TimeHandler.deltaTime · localScale.x · muiltiplier
    ///   projectileHit.damage *= num2;  shake *= num2;
    ///
    /// Over the 30-unit growth window bullet speed cancels and the total
    /// multiplier is  M = exp(30 · dt · s · m)  — exponential in the SHOOTER's
    /// frame time (damage is shooter-authoritative: the value crosses the wire
    /// once via RPCA_SendTakeDamage). At s·m=1 that is ×1.07 at 400 FPS but
    /// ×1.53 at 60 FPS and ×2.31 at 30 FPS; stacked builds SQUARE the gap
    /// (s·m=4: ×1.29 vs ×5.47 vs ×28.5). A single 200 ms hitch frame multiplies
    /// ×2.16 on its own (Δd and dt both spike). Hence "60-FPS players one-shot
    /// with Grow + any explosive" while 400-FPS players see +20-40%.
    ///
    /// Fix: a one-load TRANSPILER on TrickShot.Update swaps its single
    /// TimeHandler.deltaTime read for <see cref="GrowFpsNormalizePatch.EffectiveDt"/>,
    /// which returns the compiled constant <see cref="RefScaledDt"/> for
    /// normalized bullets and the live vanilla value otherwise — growth
    /// becomes (to first order — see the patch-class residual note) a function
    /// of distance flown (M ≈ exp(30·REF·s·m) for every shooter at every frame
    /// rate), the dt² hitch amplifier disappears, and remote simulations of
    /// the same bullet converge instead of drifting. Vanilla's body otherwise
    /// runs untouched (distance window, stacking, slow-mo pause via Δd→0,
    /// wail intensity, trail rescale, one-shot destroy).
    ///
    /// SCOPE: queue-issued ranked 1v1 (ranked_*), all 2v2/1v2/FFA/
    /// sync-tournament rooms, AND private/quickplay rooms where every fighter
    /// staged both the capability and RANKED INTENT pre-join (the
    /// cr_grow_rnk doc below carries the exact scope semantics, residuals and
    /// trust boundary — that arm is "both consented to ranked at connect",
    /// not "this game was reported rated"). Never active with an unmodded or
    /// mixed-version player in the room, never in the offline sandbox; the
    /// ranked-off guarantee applies to the PRIVATE/QUICKPLAY arm only —
    /// mod-issued rooms (including an FFA lobby whose host set casual rules)
    /// normalize regardless of the 1v1 Ranked toggle, because entering the
    /// mode's own room is that mode's consent (#106; intent-arm code r1
    /// find 3). Gate = whole-room quorum from replicated inputs, empty fails
    /// closed. The decision latches PER BULLET at its first Update: no
    /// mid-flight flips.
    /// </summary>
    internal static class GrowNormalize
    {
        /// <summary>Capability prop. cr_grow1 must never be reused for changed
        /// semantics — a semantic change gets cr_grow2 (the PoisonSync rule).</summary>
        internal const string CapabilityProp = "cr_grow1";
        internal const int CapabilityValue = 1;

        /// <summary>Ranked-INTENT prop (private-arm design r4, Codex-shaped):
        /// the local Ranked toggle's value AT CONNECT TIME, staged pre-join
        /// like the capability and re-synced only in idle states plus a
        /// synchronous pre-join fence (GrowPreJoinSyncPatch). 1 = Ranked was
        /// on, 0 = modded but Ranked off, absent = old/unmodded client.
        /// Non-mod-issued rooms normalize only when EVERY fighter advertises
        /// BOTH props — all replicated, all delivered with the player object
        /// (#287), constant while the room is assembled, so every seat
        /// computes the same answer and nothing can activate mid-game.
        ///
        /// SCOPE SEMANTICS (deliberate, Codex private-arm F1): this makes the
        /// private/quickplay arm "both players CONSENTED TO RANKED AT
        /// CONNECT", not "this specific game is rated". The two diverge only
        /// when consent is toggled mid-room or the server downgrades a game
        /// at report time; in those slivers a casual game between two
        /// connect-time-consenting modded players plays with normalized Grow
        /// (rule-symmetric — both seats read the same props). The
        /// strictly-rated-only alternative requires freezing room ratedness
        /// client+server (a report-pipeline change) and was rejected as its
        /// own project. Grow-scoped: other systems must not consume this prop
        /// without their own review.
        ///
        /// Trust boundary, stated plainly (Codex private-arm F3, widened per
        /// intent-arm code r1 find 3): a MODIFIED client can withhold/forge
        /// either prop — forcing any room it is in to vanilla Grow (keeping
        /// the low-FPS advantage) or normalizing a consenting victim's
        /// bullets in a casual room — and a modified HOST can additionally
        /// spoof a mod-issued identity (a recognized prefix or the cr_ff
        /// prop) to bypass a victim's ranked-off intent entirely. All of it
        /// is the same class as forging cr_grow1/cr_pois2 or patching one's
        /// own damage code: no client-attested protocol prevents it,
        /// server-side anti-cheat is the only real answer (#166 family), and
        /// the honest claim here is only that HONEST clients always agree.</summary>
        internal const string RankedIntentProp = "cr_grow_rnk";

        private static int _lastIntentMerged = -1;   // -1 = never merged

        private static int CurrentIntent()
        {
            try { return (Plugin.RankedEnabled != null && Plugin.RankedEnabled.Value) ? 1 : 0; }
            catch { return 0; }
        }

        /// <summary>True in the Photon states where a local property merge is
        /// provably not mid-join (#287's actual invariant — see the comment in
        /// StageCapability).</summary>
        private static bool InIdleClientState()
        {
            var st = PhotonNetwork.NetworkClientState;
            return st == Photon.Realtime.ClientState.Disconnected
                || st == Photon.Realtime.ClientState.PeerCreated
                || st == Photon.Realtime.ClientState.ConnectedToMasterServer
                || st == Photon.Realtime.ClientState.JoinedLobby;
        }

        /// <summary>Re-merge the intent prop when the Ranked toggle changed
        /// since the last merge. Separate state from the ONE-SHOT capability
        /// staging (Codex private-arm F4: capability success must not suppress
        /// intent refreshes; intent failures retry, they are not permanent).
        /// Called from the persistent tick (idle-state polling) AND
        /// synchronously from GrowPreJoinSyncPatch immediately before every
        /// ordinary join/create op — the polling alone is not an ordering
        /// fence. Never writes in-room or mid-join. RejoinOnly
        /// (ReconnectAndRejoin) is NOT fenced — nothing in game or mod code
        /// calls it, and a successful rejoin RESTORES the server-retained
        /// actor properties (the last values this room already saw), so the
        /// room's decision inputs stay consistent; it cannot inject an
        /// unfenced NEW value (intent-arm r1 guardrail correction).</summary>
        internal static void SyncRankedIntent(string source)
        {
            try
            {
                if (!_staged) return;                       // initial merge carries intent
                if (Plugin.modDisabled || !PatchesLive) return;
                if (PhotonNetwork.InRoom) return;
                if (!InIdleClientState()) return;
                int intent = CurrentIntent();
                if (intent == _lastIntentMerged) return;
                var local = PhotonNetwork.LocalPlayer;
                if (local == null) return;
                local.SetCustomProperties(new ExitGames.Client.Photon.Hashtable
                {
                    { RankedIntentProp, intent }
                });
                _lastIntentMerged = intent;
                Plugin.Log.LogInfo("[GROW-CAP] re-synced " + RankedIntentProp + "="
                    + intent.ToString(CultureInfo.InvariantCulture) + " (" + source + ")");
            }
            catch (Exception ex) { VanillaFixSupport.LogError("GrowNormalize.IntentSync", ex); }
        }

        /// <summary>THE BALANCE KNOB — the growth rate every shooter gets,
        /// expressed as the scaled frame time of a reference-FPS player
        /// (TimeHandler.deltaTime = Time.deltaTime × 0.85). At 240-FPS-equivalent
        /// a full 30-unit flight gives +11% base, +23% at s·m=2, +53% at s·m=4 —
        /// the high-FPS experience Sid described as sane, and the card stays
        /// meaningful. MUST remain a compiled constant: a config value would let
        /// any client legally buff its own damage (shooter authority). Changing
        /// it later changes rated-game balance → release-notes-worthy.</summary>
        internal const float RefScaledDt = 0.85f / 240f;

        /// <summary>Set by the patch class's [HarmonyCleanup] only when the
        /// TrickShot patch really attached — never advertise an authority we
        /// cannot deliver (PoisonSync rule).</summary>
        internal static bool PatchesLive;
        private static bool _staged;
        private static bool _stageFailedPermanently;

        /// <summary>Identical state rules to PoisonSync.StageCapability (#287):
        /// refuse in-room, merge only while Disconnected/PeerCreated, one-shot,
        /// retried from the persistent tick.</summary>
        internal static void StageCapability(string source)
        {
            try
            {
                if (_staged || _stageFailedPermanently) return;
                if (!PatchesLive)
                {
                    _stageFailedPermanently = true;
                    Plugin.Log.LogError("[GROW-CAP] TrickShot patch did NOT attach — "
                        + "Grow normalization disabled for this session (vanilla growth everywhere)");
                    return;
                }

                // Codex code-review find 6 (design F7): advertise only AFTER
                // the compat check has run — a capability staged at Awake and
                // revoked in-room when another plugin is detected reaches
                // peers late and leaves them counting us capable. The check
                // completes seconds after startup, long before any human can
                // join a room, so staging still always precedes the first
                // connect. (This is why there is no "Awake" stage call for
                // cr_grow1, unlike cr_pois2.)
                if (!Plugin.compatCheckComplete) return;

                if (PhotonNetwork.InRoom)
                {
                    Plugin.Log.LogError("[GROW-CAP] refusing to stage while in a room ("
                        + source + ") — an in-room write is the racy path this protocol forbids");
                    return;
                }

                // #287's actual invariant is "never merge MID-JOIN" (a merge
                // landing after LoadBalancingClient snapshots enterRoomParams
                // but before room entry is silently undelivered). PoisonSync
                // stages at Awake where Disconnected/PeerCreated suffices;
                // cr_grow1 stages AFTER the compat verdict (see above), by
                // which time ROUNDS may already sit idle on the master server
                // — an equally safe state (no join in flight; the local merge
                // rides the next join op's snapshot). Idle states only:
                var st = PhotonNetwork.NetworkClientState;
                if (!InIdleClientState())
                    return;   // connecting/joining: wait for a clean moment, do not merge now

                var local = PhotonNetwork.LocalPlayer;
                if (local == null) return;

                // Initial merge carries BOTH props together (Codex private-arm
                // design Q6): capability plus the current ranked intent, so a
                // client is never visible as capable-with-unknown-intent.
                int intent = CurrentIntent();
                local.SetCustomProperties(new ExitGames.Client.Photon.Hashtable
                {
                    { CapabilityProp, CapabilityValue },
                    { RankedIntentProp, intent }
                });
                _staged = true;
                _lastIntentMerged = intent;
                Plugin.Log.LogInfo("[GROW-CAP] staged " + CapabilityProp + "=" + CapabilityValue
                    + " " + RankedIntentProp + "=" + intent.ToString(CultureInfo.InvariantCulture)
                    + " pre-join (" + source + ", state=" + st + ")");
            }
            catch (Exception ex)
            {
                _stageFailedPermanently = true;
                Plugin.Log.LogError("[GROW-CAP] staging failed, Grow normalization disabled "
                    + "for this session: " + ex.Message);
            }
        }

        /// <summary>Withdraw on compat-disable, same as PoisonSync: peers must
        /// not count us capable when the patch will not run.</summary>
        internal static void RevokeCapability()
        {
            try
            {
                if (!_staged) return;
                _staged = false;
                _stageFailedPermanently = true;   // never re-stage this session
                var local = PhotonNetwork.LocalPlayer;
                if (local == null) return;
                local.SetCustomProperties(new ExitGames.Client.Photon.Hashtable
                {
                    { CapabilityProp, 0 }
                });
                Plugin.Log.LogWarning("[GROW-CAP] revoked " + CapabilityProp
                    + " — mod disabled, vanilla growth everywhere");
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[GROW-CAP] revoke failed: " + ex.Message); }
        }

        private sealed class Decision { internal bool Normalize; }
        private static readonly System.Runtime.CompilerServices.ConditionalWeakTable<TrickShot, Decision> _decisions =
            new System.Runtime.CompilerServices.ConditionalWeakTable<TrickShot, Decision>();

        /// <summary>Per-bullet latch: computed at the bullet's first patched
        /// Update, immutable for its flight, dies with the component (no room
        /// bookkeeping). Roster changes affect only later bullets, and #273's
        /// all-fighters rule makes a master handoff a non-event.</summary>
        internal static bool DecideForBullet(TrickShot ts)
        {
            Decision d;
            if (_decisions.TryGetValue(ts, out d)) return d.Normalize;
            d = new Decision { Normalize = ComputeDecision() };
            _decisions.Add(ts, d);
            return d.Normalize;
        }

        // NOTE for the follow-up pass: "cr_grow_on" (a master-published
        // private-room activation prop) was designed, implemented and CUT
        // after three review rounds — see ai-collab/grow-code-review-r2.md
        // and the ComputeDecision comment. Do not resurrect the prop name
        // with different semantics.

        private static string _lastLogKey = "";

        /// <summary>Quorum from REPLICATED inputs ONLY, collecting both props
        /// in one pass. Empty fails closed (every(∅) must not normalize).
        ///
        /// Basis: raw PhotonNetwork.PlayerList filtered by the replicated
        /// spectator role prop. This question went back and forth across
        /// review rounds, so the resolution is recorded here in full:
        /// RoomActors.ActiveFighters was tried and REJECTED (intent-arm code
        /// r1, HIGH) because its frozen-roster filter is LOCAL state — two
        /// seats freezing at different moments classify a prop-less intruder
        /// DIFFERENTLY, splitting rules in steady state for as long as the
        /// intruder stays. With the raw list, every seat counts the same
        /// actors from the same replicated data: an uninvited prop-less actor
        /// (no cr_spec, no cr_grow1 — indistinguishable by props from an
        /// unmodded quickplay opponent, which MUST read as incapable) makes
        /// allCap false on EVERY seat symmetrically — the whole room drops to
        /// vanilla, today's baseline, until the spectator system kicks it.
        /// That is a denial-of-NORMALIZATION primitive for someone holding
        /// the room code, not a split: fail-closed and rule-symmetric. The
        /// only asymmetry left is the ms-scale window while a join/leave
        /// event propagates to seats on different frames — bounded per bullet
        /// by the latch, and it converges the moment the event lands
        /// everywhere. Legitimate spectators carry cr_spec (replicated) and
        /// are excluded identically on every seat.</summary>
        private static bool Quorum(out bool allCap, out bool allRankedIntent,
                                   out int missingActor, out int fighterCount)
        {
            allCap = true;
            allRankedIntent = true;
            missingActor = -1;
            fighterCount = 0;
            var list = PhotonNetwork.PlayerList;
            if (list == null || list.Length == 0)
            {
                allCap = false;
                allRankedIntent = false;
                return false;
            }
            for (int i = 0; i < list.Length; i++)
            {
                var actor = list[i];
                if (actor == null) continue;
                if (RoomActors.IsSpectator(actor)) continue;
                fighterCount++;
                var props = actor.CustomProperties;
                object v = null;
                if (props != null) props.TryGetValue(CapabilityProp, out v);
                if (!(v is int) || (int)v != CapabilityValue)
                {
                    allCap = false;
                    if (missingActor < 0) missingActor = actor.ActorNumber;
                }
                object r = null;
                if (props != null) props.TryGetValue(RankedIntentProp, out r);
                if (!(r is int) || (int)r != 1)
                    allRankedIntent = false;
            }
            if (fighterCount == 0)
            {
                allCap = false;
                allRankedIntent = false;
                return false;
            }
            return true;
        }

        /// <summary>PURE replicated room identity — deliberately NOT
        /// IsCompetitiveRoom(): its ffa_ arm requires local FfaMode state and
        /// two clients could answer differently (PoisonSync.PeerWouldForce-
        /// Bypass precedent). The ffa_ arm additionally requires the
        /// creator-stamped cr_ffa_n room prop (Codex find 2 — FfaMode itself
        /// treats a bare ffa_ name as spoofable; a hand-made "ffa_test" room
        /// must not activate). ranked_/team_/sct-/ovt_ names are server-issued
        /// with random suffixes; deliberately hand-crafting one is the #294
        /// spoofing class, out of scope for a fix whose worst abuse is
        /// "normalized Grow in a joke room between consenting modded users".</summary>
        private static bool RoomIsModIssued(Photon.Realtime.Room room)
        {
            var rp = room.CustomProperties;
            if (rp != null && rp.ContainsKey("cr_ff")) return true;
            string n = room.Name ?? "";
            if (n.StartsWith("ffa_", StringComparison.Ordinal))
                return rp != null && rp.ContainsKey("cr_ffa_n");
            return n.StartsWith("ranked_", StringComparison.Ordinal)
                || n.StartsWith("team_", StringComparison.Ordinal)
                || n.StartsWith("sct-", StringComparison.Ordinal)
                || n.StartsWith("ovt_", StringComparison.Ordinal);
        }

        private static bool ComputeDecision()
        {
            try
            {
                // Codex find 7 fail-closed: a disabled mod (or a patch that
                // never attached) must never normalize, even if peers still
                // hold our stale capability advertisement.
                if (Plugin.modDisabled || !PatchesLive) return false;
                if (PhotonNetwork.OfflineMode || !PhotonNetwork.InRoom) return false;
                var room = PhotonNetwork.CurrentRoom;
                if (room == null) return false;

                bool allCap, allRankedIntent;
                int missingActor, fighterCount;
                Quorum(out allCap, out allRankedIntent, out missingActor, out fighterCount);

                // Two arms, both computed purely from replicated, constant-
                // while-assembled inputs (the property that killed attempts
                // 1-3 of the private arm — nothing here can activate late, so
                // there is no activation-barrier problem):
                //  * mod-issued rooms (queue/tournament/lobby identity) —
                //    intent not required; queueing is consent (#106);
                //  * private/quickplay rooms — every fighter staged BOTH
                //    capability and ranked intent pre-join (cr_grow_rnk doc
                //    above has the scope semantics and the trust boundary).
                bool modIssued = RoomIsModIssued(room);
                bool normalize = allCap && (modIssued || allRankedIntent);
                string n = room.Name ?? "";

                // Raw name stays in the DEDUP KEY only (internal comparison);
                // the LOG line masks it on the broadcast seat (§7.1, Codex
                // mod-r1 F3: this fires on a SPECTATOR seat too — every seat
                // simulates every bullet, so a watched fighter firing Grow
                // logs from here, and the room name is a join credential).
                string key = n + "|" + normalize + "|" + modIssued + "|" + allRankedIntent + "|" + allCap;
                if (key != _lastLogKey)
                {
                    _lastLogKey = key;
                    string roomForLog = BroadcastMode.IsBroadcastIdentity ? BroadcastMode.SafeRoomDesc() : n;
                    Plugin.Log.LogInfo("[GROW-NORM] " + (normalize ? "NORMALIZING" : "vanilla growth")
                        + " room=" + roomForLog + " modIssued=" + modIssued
                        + " rankedIntent=" + allRankedIntent
                        + " allCapable=" + allCap + " fighters=" + fighterCount.ToString(CultureInfo.InvariantCulture)
                        + (missingActor >= 0 ? " (no cap: actor " + missingActor.ToString(CultureInfo.InvariantCulture) + ")" : ""));
                }
                return normalize;
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("GrowNormalize.Decide", ex);
                return false;
            }
        }

    }

    /// <summary>One-load transpiler (Codex design review, twice-recommended
    /// structural form): TrickShot.Update reads <c>TimeHandler.deltaTime</c>
    /// exactly once (a static-field load); replace that single load with
    /// <c>EffectiveDt(this)</c>. Vanilla's ENTIRE body — destroy timing, the
    /// Sonigon wail-intensity update, damage/shake ordering, trail rescale —
    /// runs untouched, so there is no copied-body drift, no Sonigon
    /// reflection, and no partial-mutation hazard: a decision failure just
    /// returns the live vanilla deltaTime. The transpiler throws (= loud
    /// patch failure, PatchesLive stays false, capability never advertised)
    /// unless it finds exactly one load.
    ///
    /// Residual, documented not fixed (Codex find 9): the growth product
    /// Π(1+k·Δd) is partition-dependent to second order — very coarse frames
    /// UNDER-grow slightly (~4% at s·m=4, 60 FPS vs fine partitions), and a
    /// hitch that crosses the 30-unit cap loses the final segment (~13%
    /// worst observed direction). Both err SMALLER, never toward the nuke.</summary>
    [HarmonyPatch(typeof(TrickShot), "Update")]
    internal static class GrowFpsNormalizePatch
    {
        [HarmonyTranspiler]
        private static IEnumerable<CodeInstruction> Transpiler(IEnumerable<CodeInstruction> instructions)
        {
            var dtField = AccessTools.Field(typeof(TimeHandler), "deltaTime");
            var hook = AccessTools.Method(typeof(GrowFpsNormalizePatch), nameof(EffectiveDt));
            if (dtField == null || hook == null)
                throw new InvalidOperationException(
                    "GrowFpsNormalize: reflection targets missing (TimeHandler.deltaTime / EffectiveDt)");

            int replaced = 0;
            foreach (var ins in instructions)
            {
                if (ins.opcode == System.Reflection.Emit.OpCodes.Ldsfld && Equals(ins.operand, dtField))
                {
                    // Mutate the matched instruction in place so any labels /
                    // exception blocks attached to it ride along untouched
                    // (netstandard2.1 cannot name SRE.Label to copy them).
                    ins.opcode = System.Reflection.Emit.OpCodes.Ldarg_0;
                    ins.operand = null;
                    yield return ins;
                    yield return new CodeInstruction(System.Reflection.Emit.OpCodes.Call, hook);
                    replaced++;
                    continue;
                }
                yield return ins;
            }
            if (replaced != 1)
                throw new InvalidOperationException(
                    "GrowFpsNormalize: expected exactly 1 TimeHandler.deltaTime load in TrickShot.Update, found "
                    + replaced.ToString(CultureInfo.InvariantCulture));
        }

        /// <summary>Called from the patched IL in place of the deltaTime load.
        /// Public static: it is a call target inside game IL.</summary>
        public static float EffectiveDt(TrickShot ts)
        {
            try
            {
                return GrowNormalize.DecideForBullet(ts)
                    ? GrowNormalize.RefScaledDt
                    : TimeHandler.deltaTime;
            }
            catch { return TimeHandler.deltaTime; }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            if (exception == null) GrowNormalize.PatchesLive = true;
            return VanillaFixSupport.Cleanup("GrowFpsNormalize", exception);
        }
    }

    /// <summary>The synchronous PRE-JOIN FENCE for the ranked-intent prop
    /// (Codex private-arm design Q6: "a generic Update retry alone is not an
    /// ordering fence"). Prefixes every ordinary join/create entry point —
    /// vanilla uses CreateRoom/JoinRandomRoom/JoinRoom
    /// (NetworkConnectionHandler.cs:232-503), the mod adds JoinOrCreateRoom —
    /// and re-merges the intent BEFORE the op flips the client state to
    /// Joining. SetCustomProperties outside a room is a synchronous local
    /// merge, so the value the op's snapshot carries is exactly the current
    /// toggle. ReconnectAndRejoin (RejoinOnly) is deliberately not fenced:
    /// nothing in the game or mod calls it, and a successful rejoin RESTORES
    /// the server-retained actor properties — the values the room already
    /// saw — so the room's decision inputs stay consistent (see the
    /// SyncRankedIntent doc; intent-arm r1 guardrail correction).</summary>
    [HarmonyPatch]
    internal static class GrowPreJoinSyncPatch
    {
        private static IEnumerable<MethodBase> TargetMethods()
        {
            var list = new List<MethodBase>();
            foreach (var m in typeof(PhotonNetwork).GetMethods(BindingFlags.Public | BindingFlags.Static))
            {
                if (m.Name != "JoinRoom" && m.Name != "JoinOrCreateRoom"
                    && m.Name != "CreateRoom" && m.Name != "JoinRandomRoom") continue;
                if (m.IsGenericMethodDefinition) continue;
                list.Add(m);
            }
            if (list.Count == 0)
                throw new InvalidOperationException("GrowPreJoinSync: no PhotonNetwork join/create overloads found");
            return list;
        }

        [HarmonyPrefix]
        private static void BeforeJoin()
        {
            try
            {
                // Intent-arm code r1 find 2: the fence must also cover the
                // INITIAL staging — a join racing the first post-compat tick
                // would otherwise snapshot no Grow props at all and the seat
                // stays incapable for that whole room. StageCapability is
                // one-shot and self-guarded, so this is free when already
                // staged. If the compat verdict is not in yet, both calls
                // refuse and the room simply plays vanilla for this seat —
                // fail-closed, and only reachable by a join within the first
                // seconds of process startup.
                GrowNormalize.StageCapability("pre-join");
                GrowNormalize.SyncRankedIntent("pre-join");
            }
            catch (Exception ex) { VanillaFixSupport.LogError("GrowPreJoinSync", ex); }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("GrowPreJoinSync", exception);
        }
    }

    [HarmonyPatch(typeof(CardChoiceVisuals), "Hide")]
    internal static class InactiveVisualsHidePatch
    {
        [HarmonyPrefix]
        private static bool BeforeHide(CardChoiceVisuals __instance)
        {
            try
            {
                // Ungated (#151) — see DeadPlayerForcePatch.
                if (__instance != null && !__instance.gameObject.activeInHierarchy)
                    return false;
            }
            catch (Exception ex) { VanillaFixSupport.LogError("InactiveVisualsHide", ex); }
            return true;
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("InactiveVisualsHide", exception);
        }
    }

    /// <summary>Bug #153 — "Started with leftover parasite stacks from previous round."
    ///
    /// <para>MECHANISM (established from the reporter's bundle — an ffa_ lobby —
    /// plus the decompile): Parasite/Poison bullets carry RayHitPoison, whose
    /// DoHitEffect starts a DamageOverTime coroutine on the victim
    /// (RayHitPoison.cs:32). Every stream hosted there is killed at the
    /// transition — HealthHandler.Revive's LAST statement is
    /// dot.StopAllCoroutines() (HealthHandler.cs:362), and both
    /// PlayerManager.RevivePlayers and the tail of PlayerManager.Move call
    /// Revive for every player — so the only way a DoT can exist at round start
    /// is a stream STARTED AFTER the victim's final spawn revive. The starter
    /// is a leftover PROJECTILE: nothing destroys mid-air bullets at the
    /// point/round boundary (MapTransition.ClearObjects only sweeps
    /// RemoveAfterSeconds carriers), hits are decided on the bullet OWNER's
    /// client and replicated via ProjectileHit.RPCA_DoHit, and per-client
    /// transition pacing skews — so an end-of-round parasite bullet can register
    /// a hit that lands after the victim has already spawned, draining them for
    /// the full DoT duration with nobody shooting. The reporter's log carries
    /// the signature: RPCA_DoHit RPC bursts arriving immediately after MOVE
    /// PLAYERS END (copies whose local bullet was already gone NRE'd; ones whose
    /// bullet survived apply real damage + DoT). FFA amplifies it — 5-10
    /// players, staggered transitions — but the window exists in every mode.</para>
    ///
    /// <para>FIX: each client despawns the projectiles IT OWNS the moment the
    /// point is decided. RPCA_NextRound is a server-ordered All-RPC, so the
    /// sweep is near-simultaneous room-wide regardless of transition pacing
    /// skew; a second sweep at MovePlayers mops up anything fired during the
    /// win sequence (and covers the rematch/game-start boundary). Destruction
    /// is exactly vanilla's own despawn path — owner-side PhotonNetwork.Destroy,
    /// the same call ProjectileHit.DestroyMe makes and the one sanctioned
    /// exception in learning #94 — so every client agrees the bullet is gone
    /// and no health/stream divergence is possible.</para>
    ///
    /// <para>SCOPE: AnyGameScope, not GameplayScope (#151/#286). Bug #153's
    /// room was a mod-issued ffa_ lobby, which GameplayScope would cover — but
    /// the identical window exists in privately hosted room-code ranked games
    /// (the majority of rated play), which GameplayScope silently excludes.
    /// Owner-authoritative destruction cannot make two clients disagree: an
    /// unpatched peer simply keeps ITS OWN bullets alive, which is today's
    /// behaviour for those bullets, so a mixed room degrades to the status quo
    /// per unpatched owner and is never worse than vanilla (#198 asymmetry
    /// concern does not apply — we never ask the peer to do anything).</para>
    ///
    /// <para>POOL SAFETY (#94/#156): destroying a bullet before FriendlyFoe's
    /// BulletPoolInstancer.Start has run NREs its OnDestroy inside
    /// PrefabPool.Release and corrupts the pool for the session. Two guards:
    /// the sweep runs on Plugin.Instance two frames after the trigger (so
    /// everything it can see was instantiated in an earlier frame and its Start
    /// batch has run), and bullets whose ProjectileHit.view is still null
    /// (view is assigned in ProjectileHit.Start) are skipped outright — never
    /// Object.Destroyed.</para></summary>
    [HarmonyPatch]
    internal static class StaleProjectileSweepPatch
    {
        // Pending flag carries a TTL (#270c): the coroutine host can die
        // (persistent-GO respawn), and a suppression keyed on "a coroutine
        // will clear this" with no expiry is a permanent wedge. A dead host
        // costs at most one 2-second suppression window, self-healing.
        private static bool _sweepPending;
        private static float _pendingSince = -10f;
        // Fixed diag key; its budget is reset at the room-LEAVE edge in
        // GameStateWatcher, not here (see the DiagLimited call for why).
        internal const string DiagKey = "StaleProjectileSweep-despawn";

        [HarmonyPostfix]
        [HarmonyPatch(
            typeof(GM_ArmsRace),
            "RPCA_NextRound",
            new Type[]
            {
                typeof(int), typeof(int), typeof(int),
                typeof(int), typeof(int), typeof(int)
            })]
        private static void AfterNextRound()
        {
            // Runs in FFA too: FfaMode's prefix replaces the body (returns
            // false) but Harmony still runs postfixes, and the RPC itself is
            // the round-decided broadcast in every mode.
            Schedule("point-over");
        }

        // BOTH a prefix and a postfix on MovePlayers, deliberately:
        //  * the prefix covers vanilla THROWING mid-loop on a departed
        //    player's entry (#272) — a postfix never runs then;
        //  * the postfix covers the prefix being SKIPPED — the FFA map-scale
        //    patch takes MovePlayers over entirely (returns false) on scaled
        //    maps, and per this file's DeadPlayerDot note HarmonyX skips
        //    subsequent prefixes once one returns false, with UNDEFINED
        //    relative order between ours and the takeover's.
        // Schedule() coalesces, so when both fire the second is a no-op.
        [HarmonyPrefix]
        [HarmonyPatch(typeof(PlayerManager), "MovePlayers")]
        private static void BeforeMovePlayers()
        {
            Schedule("move-players");
        }

        [HarmonyPostfix]
        [HarmonyPatch(typeof(PlayerManager), "MovePlayers")]
        private static void AfterMovePlayers()
        {
            Schedule("move-players");
        }

        private static void Schedule(string reason)
        {
            try
            {
                // Boundary stamp for PoisonSync's shadow observer (bug 221):
                // both Schedule triggers — the point-over RPC and MovePlayers —
                // ARE the round-boundary signals, so one line here covers every
                // mode. Deliberately before the scope gate: the stamp is inert
                // data and the poison protocol has its own room gating.
                try { PoisonSync.NoteRoundBoundary(); } catch { }
                // Round-scoped SOUND hygiene rides the same trigger set (its
                // own coalescing + gating; deliberately before the scope gate
                // — the sound sweep is per-seat audio hygiene, ungated).
                try { RoundSoundSweep.Schedule(reason); } catch { }
                if (!VanillaFixSupport.AnyGameScope()) return;
                if (_sweepPending && Time.realtimeSinceStartup - _pendingSince < 2f) return;
                if (Plugin.Instance == null) return;
                _sweepPending = true;
                _pendingSince = Time.realtimeSinceStartup;
                Plugin.Instance.StartCoroutine(SweepAfterFrames(reason));
            }
            catch (Exception ex)
            {
                _sweepPending = false;
                VanillaFixSupport.LogError("StaleProjectileSweep", ex);
            }
        }

        private static System.Collections.IEnumerator SweepAfterFrames(string reason)
        {
            // Two frames: see POOL SAFETY note. Hosted on Plugin.Instance
            // (persistent GO, #85) so a mid-transition map teardown cannot
            // kill the coroutine before it runs.
            yield return null;
            yield return null;
            _sweepPending = false;
            SweepNow(reason);
        }

        private static void SweepNow(string reason)
        {
            try
            {
                // Re-check at sweep time — the player can leave the room in
                // the two-frame gap.
                if (!VanillaFixSupport.AnyGameScope()) return;

                int swept = 0;
                ProjectileHit[] projectiles = UnityEngine.Object.FindObjectsOfType<ProjectileHit>();
                if (projectiles == null) return;
                foreach (ProjectileHit projectile in projectiles)
                {
                    try
                    {
                        if (projectile == null || projectile.gameObject == null) continue;
                        // view is assigned in ProjectileHit.Start — null means
                        // this bullet is younger than one Start batch (or a
                        // rare non-networked spawn). Skip it: #94, swallow
                        // only, never Object.Destroy a pooled carrier.
                        PhotonView view = projectile.view;
                        if (view == null || !view.IsMine) continue;
                        PhotonNetwork.Destroy(projectile.gameObject);
                        swept++;
                    }
                    catch
                    {
                        // A bullet destroyed mid-sweep is the goal state.
                    }
                }

                if (swept > 0)
                {
                    // FIXED key, budget reset at the room-LEAVE edge in
                    // GameStateWatcher (r1 find 3 → r2 find 1 → r3 find 1
                    // ended the per-room-key experiment: a name-derived key
                    // both grew the dict per room AND let a directly-rejoined
                    // room inherit its spent budget, because any in-sweep
                    // reset can only see KEY CHANGES. The leave edge fires on
                    // EVERY transition, sweep or not, so each sitting starts
                    // with a fresh 50 and the dict never grows.)
                    VanillaFixSupport.DiagLimited(
                        DiagKey,
                        "StaleProjectileSweep despawned " +
                        swept.ToString(CultureInfo.InvariantCulture) +
                        " leftover projectile(s) at " + reason,
                        // 50, was 10: the 10-line budget ran out mid-game-1 of
                        // the bug-217 session, hiding the projectile-leak rate
                        // for every later game (#304's cap trap — a capped
                        // diag reads as a behaviour change).
                        50);
                }
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("StaleProjectileSweep", ex);
            }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            // Eager-resolve the sound sweep's reflection surface at patch time
            // so a Sonigon member rename fails LOUD in the startup log
            // (#83/#91), not silently at the first round boundary. Safe here:
            // SonigonVoiceUpdateGuard's own TargetMethod already proves the
            // Sonigon assembly is loaded at patch time.
            try { RoundSoundSweep.EagerResolve(); } catch { }
            return VanillaFixSupport.Cleanup("StaleProjectileSweep", exception);
        }
    }

    /// <summary>Round-boundary sweep for LOOPING sounds that outlive their round
    /// ("the map saws / Abyssal Countdown sometimes stick around", Aug 22).
    ///
    /// <para>Two-layer root cause, both verified against the Sonigon decompile
    /// (logs-snapshot/decompiled/sonigon/) and the serialized prefab data:
    /// (1) every map-saw prefab plays its LOOPING SFX_Environment_Saw_Loop_SE
    /// through SoundUnityEventPlayer's soundStart slot (soundStartLoop=null),
    /// and PlayEnd() only ever stops soundStartLoop — so no component EVER
    /// stops a map-saw loop; only the engine's dead-transform sweep does,
    /// ~2s after the next map loads. (2) the engine itself has a zombie
    /// state: InstanceSoundEvent.PoolSingleVoice's allowFadeOut=true branch
    /// never clears shouldRestartIfLoop (InstanceSoundEvent.cs:458-468), so a
    /// voice-STOLEN holder (armed, voice==null) that then receives any
    /// Stop-with-fade — every vanilla Stop, and the dead-transform sweep
    /// itself — freezes in FadeOut (fade progression only runs on a LIVE
    /// voice, VoiceFade/GetVolume), a state the dead-transform sweep skips
    /// forever (line 599) and the restart branch (663-677) happily
    /// resurrects. AbyssalCountdown is the worst case: its charge-loop
    /// container has volumeIntensityEnable=1 + a Continuous intensity param,
    /// so ShouldBePlaying is unconditionally true, the zombie restarts the
    /// next frame — and the component's own soundChargeIsPlaying latch is
    /// false by then, so its SoundStop early-returns forever (OnDisable,
    /// OnDestroy and the reviveAction reset all no-op through that latch).</para>
    ///
    /// <para>The sweep walks Sonigon's live sound table and hard-pools
    /// (fade=false — the branch that actually clears the restart flag) every
    /// LOOPING holder that is (a) owned by a destroyed/inactive transform,
    /// (b) positioned at a destroyed/inactive PlayAtTransform target, or
    /// (c) a frozen armed zombie (voice==null, shouldRestartIfLoop,
    /// state==FadeOut — legitimately reachable, see ClassifyLoopVoice: a
    /// fading stop whose voice is then STOLEN leaves the fade with nothing
    /// to progress on, so it never reaches FadePool). One-shot
    /// containers are deliberately untouched — they legitimately outlive
    /// their hosts (death/explosion sounds). Music is untouchable by
    /// construction (owner alive+active, DontDestroyOnLoad). Everything is
    /// reflection: the Sonigon assembly is resolved by name, never
    /// referenced (house rule, see PhoenixSound above); every member is
    /// resolved ONCE and a missing one fails LOUD once (#83/#91).</para>
    ///
    /// <para>Triggered from StaleProjectileSweepPatch.Schedule (the
    /// production-proven round-boundary trigger set: point-over RPC +
    /// MovePlayers, all modes including rematches) and from the reliable
    /// room-exit edge in Plugin.OnLeftRoom (a ghost saw at the MENU is the
    /// most audible variant). Each run does a first pass 2 frames in, a
    /// second pass ~3s later, and a TRAILING pass 8s after the LATEST
    /// boundary that arrived while the run was pending — the old map's scene
    /// is unloaded 2s after the next map finishes loading
    /// (MapManager.UnloadAfterSeconds), so only the delayed passes see those
    /// transforms dead, and a fast second boundary (review r2 M5) must push
    /// the tail rather than be swallowed by coalescing. Ungated by room
    /// type: pure per-seat audio hygiene (#286).</para></summary>
    internal static class RoundSoundSweep
    {
        internal const string DiagKey = "RoundSoundSweep";

        private static bool _pending;
        private static float _pendingSince = -10f;
        // Review r2 M5: EVERY Schedule call — coalesced or not — pushes the
        // trailing deadline; the running coroutine reads it live.
        private static float _lastBoundaryRt = -10f;
        // Liveness stamp of the in-flight coroutine (#270c/#367b: the host
        // can die under it — NetworkRestart — and a pending flag nothing
        // clears would mute the sweep for the session) + a run token so a
        // superseded run that merely stalled (suspended game) cannot resume
        // and double-run beside its successor.
        private static float _aliveRt = -10f;
        private static int _gen;

        // Reflection surface, resolved once (#91: a silent miss is a
        // forever-no-op; log loud, once).
        private static bool _resolved;
        private static bool _resolveFailed;
        private static Type _tSoundManager, _tInstanceSoundEvent;
        private static PropertyInfo _pInstance, _pData;
        private static FieldInfo _fEventDict, _fTransformDict, _fHolders;
        private static FieldInfo _fHolderContainer, _fHolderVoices;
        private static FieldInfo _fContainerSetting, _fSettingLoop;
        private static FieldInfo _fVoice, _fVoiceFade, _fRestart, _fPlayTypeInst, _fFadeState;
        private static FieldInfo _fPlayType, _fOwnerTransform, _fPosTransform;
        private static MethodInfo _mPoolSingleVoice, _mStop, _mStopAllAtOwner;
        private static FieldInfo _fAbyssalLoopEvent;

        private static bool Resolve()
        {
            if (_resolved) return !_resolveFailed;
            _resolved = true;
            try
            {
                _tSoundManager = AccessTools.TypeByName("Sonigon.SoundManager");
                _tInstanceSoundEvent = AccessTools.TypeByName("Sonigon.Internal.InstanceSoundEvent");
                var tData = AccessTools.TypeByName("Sonigon.Internal.SoundManagerData");
                var tDictValue = AccessTools.TypeByName("Sonigon.Internal.InstanceDictionaryValue");
                var tHolder = AccessTools.TypeByName("Sonigon.Internal.InstanceSoundContainerHolder");
                var tVoiceHolder = AccessTools.TypeByName("Sonigon.Internal.InstanceVoiceHolder");
                var tPlayTypeInst = AccessTools.TypeByName("Sonigon.Internal.PlayTypeInstance");
                var tVoiceFade = AccessTools.TypeByName("Sonigon.Internal.VoiceFade");
                var tContainer = AccessTools.TypeByName("Sonigon.SoundContainer");
                var tContainerVars = AccessTools.TypeByName("Sonigon.Internal.SoundContainerVariables");
                if (_tSoundManager == null || _tInstanceSoundEvent == null || tData == null
                    || tDictValue == null || tHolder == null || tVoiceHolder == null
                    || tPlayTypeInst == null || tVoiceFade == null || tContainer == null
                    || tContainerVars == null)
                    throw new InvalidOperationException("a Sonigon type failed to resolve");

                _pInstance = AccessTools.Property(_tSoundManager, "Instance");
                _pData = AccessTools.Property(_tSoundManager, "Data");
                _fEventDict = AccessTools.Field(tData, "soundEventDictionary");
                _fTransformDict = AccessTools.Field(tDictValue, "transformDictionary");
                _fHolders = AccessTools.Field(_tInstanceSoundEvent, "instanceSoundContainerHolder");
                _fHolderContainer = AccessTools.Field(tHolder, "soundContainer");
                _fHolderVoices = AccessTools.Field(tHolder, "voiceHolder");
                _fContainerSetting = AccessTools.Field(tContainer, "setting");
                _fSettingLoop = AccessTools.Field(tContainerVars, "loopEnabled");
                _fVoice = AccessTools.Field(tVoiceHolder, "voice");
                _fVoiceFade = AccessTools.Field(tVoiceHolder, "voiceFade");
                _fRestart = AccessTools.Field(tVoiceHolder, "shouldRestartIfLoop");
                _fPlayTypeInst = AccessTools.Field(tVoiceHolder, "playTypeInstance");
                _fFadeState = AccessTools.Field(tVoiceFade, "state");
                _fPlayType = AccessTools.Field(tPlayTypeInst, "playType");
                _fOwnerTransform = AccessTools.Field(tPlayTypeInst, "instanceIDTransform");
                _fPosTransform = AccessTools.Field(tPlayTypeInst, "positionTransform");
                // PoolSingleVoice(int s, int v, bool shouldRestartIfLoop,
                //                 bool allowFadeOut, bool isCalledByOnDestroy = false)
                _mPoolSingleVoice = AccessTools.Method(_tInstanceSoundEvent, "PoolSingleVoice",
                    new Type[] { typeof(int), typeof(int), typeof(bool), typeof(bool), typeof(bool) });
                _fAbyssalLoopEvent = AccessTools.Field(typeof(AbyssalCountdown), "soundAbyssalChargeLoop");
                _mStop = FindManagerMethod("Stop");
                _mStopAllAtOwner = FindManagerMethod("StopAllAtOwner");
                if (_fEventDict == null || _fTransformDict == null || _fHolders == null
                    || _fHolderContainer == null || _fHolderVoices == null
                    || _fContainerSetting == null || _fSettingLoop == null
                    || _fVoice == null || _fVoiceFade == null || _fRestart == null
                    || _fPlayTypeInst == null || _fFadeState == null || _fPlayType == null
                    || _fOwnerTransform == null || _fPosTransform == null
                    || _mPoolSingleVoice == null || _pInstance == null || _pData == null)
                    throw new InvalidOperationException("a Sonigon member failed to resolve");
            }
            catch (Exception ex)
            {
                _resolveFailed = true;
                Plugin.Log?.LogWarning("[VANILLA-FIX] RoundSoundSweep: Sonigon reflection surface failed to resolve — sweep disabled: " + ex.Message);
            }
            return !_resolveFailed;
        }

        /// <summary>Resolve a SoundManager method whose trailing parameters are
        /// all optional (#322: Stop/StopAllAtOwner carry an optional trailing
        /// allowFadeOut, so exact-arity lookups return null).</summary>
        private static MethodInfo FindManagerMethod(string name)
        {
            foreach (var cand in _tSoundManager.GetMethods(BindingFlags.Public | BindingFlags.Instance))
            {
                if (cand.Name != name) continue;
                var ps = cand.GetParameters();
                if (ps.Length < 1) continue;
                if (ps[ps.Length - 1].ParameterType != typeof(bool)) continue;
                bool ok = true;
                for (int i = 0; i < ps.Length; i++)
                    if (i >= 2 && !ps[i].HasDefaultValue) { ok = false; break; }
                if (ok) return cand;
            }
            return null;
        }

        /// <summary>Called once at patch time (StaleProjectileSweep's Cleanup)
        /// so resolution success/failure is visible in every startup log.</summary>
        internal static void EagerResolve()
        {
            if (Resolve())
                Plugin.Log?.LogInfo("[VANILLA-FIX] RoundSoundSweep: Sonigon reflection surface resolved");
        }

        internal static void Schedule(string reason)
        {
            try
            {
                float now = Time.realtimeSinceStartup;
                // Every boundary pushes the trailing deadline (r2 M5) — a
                // coalesced request is NOT dropped, its tail rides the
                // running coroutine.
                _lastBoundaryRt = now;
                // Coalesce only onto a LIVE run: the coroutine stamps _aliveRt
                // at every resume, so a host death shows up as a stale stamp
                // and the next boundary simply starts a fresh run.
                if (_pending && now - _aliveRt < 6f) return;
                if (Plugin.Instance == null) return;
                if (!Resolve()) return;
                _pending = true;
                _pendingSince = now;
                _aliveRt = now;
                int gen = ++_gen;
                Plugin.Instance.StartCoroutine(SweepTwice(reason, gen));
            }
            catch (Exception ex)
            {
                _pending = false;
                VanillaFixSupport.LogError("RoundSoundSweep", ex);
            }
        }

        private static System.Collections.IEnumerator SweepTwice(string reason, int gen)
        {
            yield return null;
            yield return null;
            if (gen != _gen) yield break;
            _aliveRt = Time.realtimeSinceStartup;
            SweepNow(reason);
            // Later passes after the old map's scene unload. Review r1 find 6
            // measured the real timeline: vanilla waits ~1s after the round
            // RPC before LOADING the next level, and MapManager unloads the
            // OLD scene only 2s after the new level finishes — so old-map
            // transforms can still be alive at +3s (and the 2s dead-transform
            // grace can then arm the frozen zombie with no sweep left).
            yield return new WaitForSecondsRealtime(3f);
            if (gen != _gen) yield break;
            _aliveRt = Time.realtimeSinceStartup;
            SweepNow(reason + "+3s");
            // Trailing pass: 8s after the LATEST boundary seen while this run
            // was pending (r2 M5 — a fast boundary B coalesced onto A's run
            // used to get no B-relative pass at all, so a ghost created by
            // B's transition survived into live play). Bounded at 30s from
            // the first boundary so a boundary storm cannot pin the run; a
            // boundary after the tail starts a fresh run.
            while (Time.realtimeSinceStartup < _lastBoundaryRt + 8f
                   && Time.realtimeSinceStartup - _pendingSince < 30f)
            {
                _aliveRt = Time.realtimeSinceStartup;
                yield return new WaitForSecondsRealtime(0.5f);
                if (gen != _gen) yield break;
            }
            _pending = false;
            SweepNow(reason + "+tail");
        }

        private static void SweepNow(string reason)
        {
            try
            {
                if (!Resolve()) return;
                object manager = _pInstance.GetValue(null, null);
                if (manager == null) return;
                object data = _pData.GetValue(manager, null);
                var eventDict = data != null ? _fEventDict.GetValue(data) as IDictionary : null;
                if (eventDict == null) return;

                int ownerDead = 0, posDead = 0, armedFrozen = 0;
                var names = new List<string>();
                foreach (DictionaryEntry eventEntry in eventDict)
                {
                    var transformDict = eventEntry.Value != null
                        ? _fTransformDict.GetValue(eventEntry.Value) as IDictionary : null;
                    if (transformDict == null) continue;
                    string evtName = null;
                    foreach (DictionaryEntry instEntry in transformDict)
                    {
                        object inst = instEntry.Value;
                        if (inst == null) continue;
                        var holders = _fHolders.GetValue(inst) as Array;
                        if (holders == null) continue;
                        for (int s = 0; s < holders.Length; s++)
                        {
                            object holder = holders.GetValue(s);
                            if (holder == null) continue;
                            object container = _fHolderContainer.GetValue(holder);
                            object setting = container != null ? _fContainerSetting.GetValue(container) : null;
                            if (setting == null || !(bool)_fSettingLoop.GetValue(setting)) continue;
                            var voices = _fHolderVoices.GetValue(holder) as Array;
                            if (voices == null) continue;
                            for (int v = 0; v < voices.Length; v++)
                            {
                                object vh = voices.GetValue(v);
                                if (vh == null) continue;
                                int rule = ClassifyLoopVoice(vh);
                                if (rule == 0) continue;
                                // Hard pool: shouldRestartIfLoop=false,
                                // allowFadeOut=false — the only argument shape
                                // that both pools the voice AND clears the
                                // restart flag (the fade branch clears neither).
                                try { _mPoolSingleVoice.Invoke(inst, new object[] { s, v, false, false, false }); }
                                catch { continue; }
                                if (rule == 1) ownerDead++;
                                else if (rule == 2) posDead++;
                                else armedFrozen++;
                                if (evtName == null)
                                {
                                    try { evtName = (eventEntry.Key as UnityEngine.Object)?.name ?? "?"; }
                                    catch { evtName = "?"; }
                                }
                                if (names.Count < 8 && !names.Contains(evtName)) names.Add(evtName);
                            }
                        }
                    }
                }

                ReconcileAbyssal(ref armedFrozen, names);

                if (ownerDead > 0 || posDead > 0 || armedFrozen > 0)
                {
                    VanillaFixSupport.DiagLimited(
                        DiagKey,
                        "RoundSoundSweep at " + reason + ": ownerDead=" +
                        ownerDead.ToString(CultureInfo.InvariantCulture) + " posDead=" +
                        posDead.ToString(CultureInfo.InvariantCulture) + " armedFrozen=" +
                        armedFrozen.ToString(CultureInfo.InvariantCulture) +
                        " events=[" + string.Join(",", names.ToArray()) + "]",
                        50);
                }
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("RoundSoundSweep", ex);
            }
        }

        /// <summary>0 = leave alone; 1 = ownerDead; 2 = posDead; 3 = armedFrozen.</summary>
        private static int ClassifyLoopVoice(object vh)
        {
            try
            {
                object pti = _fPlayTypeInst.GetValue(vh);
                if (pti != null)
                {
                    var owner = _fOwnerTransform.GetValue(pti) as Transform;
                    // Unity fake-null via the overloaded == on the typed ref.
                    if (owner == null || !owner.gameObject.activeInHierarchy)
                        return 1;
                    object playType = _fPlayType.GetValue(pti);
                    if (playType != null && playType.ToString() == "PlayAtTransform")
                    {
                        var pos = _fPosTransform.GetValue(pti) as Transform;
                        if (pos == null || !pos.gameObject.activeInHierarchy)
                            return 2;
                    }
                }
                object voice = _fVoice.GetValue(vh);
                if (voice == null && (bool)_fRestart.GetValue(vh))
                {
                    object fade = _fVoiceFade.GetValue(vh);
                    object state = fade != null ? _fFadeState.GetValue(fade) : null;
                    // Compare by NAME — the FadeState ordinals are
                    // FadeHold=0, FadeIn=1, FadeOut=2, FadePool=3 (decompile;
                    // NOT the declaration order a reader might guess).
                    // NOTE (review r1, R2 refinement): this state IS
                    // reachable legitimately — a normal fading Stop followed
                    // by a voice steal lands here. That holder was already
                    // STOPPING, so hard-disarming it is safe either way; the
                    // rule's job is killing the restart branch's zombie.
                    if (state != null && state.ToString() == "FadeOut")
                        return 3;
                }
            }
            catch { }
            return 0;
        }

        /// <summary>The one zombie class the table walk cannot see: a
        /// RESTARTED, LIVE abyssal charge loop whose owner (the card object on
        /// the player) is alive and active, while the component's
        /// soundChargeIsPlaying latch is false — so the component's own
        /// SoundStop no-ops forever. Reconcile: latch says silent but the
        /// engine may be playing → issue a hard Stop (fade=false, which pools
        /// AND disarms). When the latch is TRUE the component owns the sound —
        /// never stop behind its back (that would strand the latch the other
        /// way).</summary>
        private static void ReconcileAbyssal(ref int armedFrozen, List<string> names)
        {
            if (_mStop == null || _fAbyssalLoopEvent == null) return;
            try
            {
                object manager = _pInstance.GetValue(null, null);
                if (manager == null) return;
                object data = _pData.GetValue(manager, null);
                var eventDict = data != null ? _fEventDict.GetValue(data) as IDictionary : null;
                var comps = UnityEngine.Object.FindObjectsOfType<AbyssalCountdown>();
                if (comps == null) return;
                foreach (var comp in comps)
                {
                    try
                    {
                        if (comp == null || comp.soundChargeIsPlaying) continue;
                        object evt = _fAbyssalLoopEvent.GetValue(comp);
                        if (evt == null) continue;
                        // Review r2 L6: SoundManagerData.Stop simply returns
                        // when no instance exists for (event, owner), so a
                        // returning call proves nothing stopped. Only a
                        // holder that the engine actually tracks for this
                        // component is a reconcile worth counting — an
                        // always-on no-op count would burn the bounded diag
                        // budget three lines per boundary.
                        bool tracked = false;
                        if (eventDict != null && eventDict.Contains(evt))
                        {
                            var transformDict = _fTransformDict.GetValue(eventDict[evt]) as IDictionary;
                            // Keyed by owner.GetInstanceID() (SoundManagerData.Stop, decompile).
                            tracked = transformDict != null && transformDict.Contains(comp.transform.GetInstanceID());
                        }
                        if (!tracked) continue;
                        InvokeManagerStop(_mStop, manager, evt, comp.transform);
                        // Counts toward the diag line (review r1 find 12: a
                        // reconcile-only sweep otherwise acted silently —
                        // the structural-zero observability trap).
                        armedFrozen++;
                        if (names.Count < 8 && !names.Contains("AbyssalReconcile")) names.Add("AbyssalReconcile");
                    }
                    catch { }
                }
            }
            catch { }
        }

        /// <summary>Invoke Stop/StopAllAtOwner with allowFadeOut forced FALSE
        /// (a fade-stop on an armed holder is exactly the freeze this class
        /// exists to kill); every other optional gets its declared default.</summary>
        private static void InvokeManagerStop(MethodInfo m, object manager, object evtOrNull, Transform t)
        {
            var ps = m.GetParameters();
            var args = new object[ps.Length];
            int i = 0;
            if (evtOrNull != null) args[i++] = evtOrNull;
            args[i++] = t;
            for (; i < ps.Length; i++)
                args[i] = ps[i].ParameterType == typeof(bool) ? (object)false : ps[i].DefaultValue;
            m.Invoke(manager, args);
        }

        /// <summary>For SpectatorSync.SafeBuryAndClean: stop every sound owned
        /// by a husk BEFORE it is deactivated — cache-replayed saw husks start
        /// their loop at OnEnable, burial's OnDisable stops nothing (the loop
        /// is in the un-stopped soundStart slot), and a live-but-INACTIVE
        /// transform is invisible to the engine's fake-null sweep. The public
        /// API works here precisely because the transform is still valid at
        /// burial time.</summary>
        internal static void StopAllAtOwnerHard(Transform t)
        {
            try
            {
                if (t == null || !Resolve() || _mStopAllAtOwner == null) return;
                object manager = _pInstance.GetValue(null, null);
                if (manager == null) return;
                InvokeManagerStop(_mStopAllAtOwner, manager, null, t);
            }
            catch { }
        }
    }

    /// <summary>Bug #128 — keep our T chat's own keystrokes out of ROUNDS' Enter chat.
    ///
    /// <para>Vanilla <c>DevConsole.Update()</c> is <c>if (Input.GetKeyDown(KeyCode.Return))
    /// ToggleConsole();</c> — a RAW <c>Input</c> read, which no IMGUI <c>Event.Use()</c> can
    /// intercept. So pressing Enter to SEND one of our messages also toggled vanilla's chat
    /// open behind it: <c>isTyping</c> and <c>GameManager.lockInput</c> both latched true and
    /// the player was left input-locked with a vanilla text box up (at the main menu that box
    /// is the room-code field, so the next Enter tried to join a room named after the
    /// message). That is the mess the old "don't open T chat during combat" bandaid was
    /// papering over.</para>
    ///
    /// <para>Blocking <c>ToggleConsole</c> — not <c>Update</c> — is deliberate: Update also
    /// drives <c>PlatformManager.Update()</c>, which must keep running. Ordering works out
    /// because Unity runs Update before OnGUI: on the frame we submit, DevConsole reads Enter
    /// while our box is still open, so the guard is armed.</para>
    ///
    /// <para>Resolved via <c>TargetMethods()</c> instead of <c>[HarmonyPatch(typeof(DevConsole)…)]</c>
    /// so this file never names a type carrying a <c>TMP_InputField</c> field (this csproj
    /// references no TMPro assembly — learning #15), and logged either way because a patch
    /// that silently fails to attach is a forever-no-op (learning #83).</para></summary>
    [HarmonyPatch]
    internal static class DevConsoleToggleGuardPatch
    {
        private static IEnumerable<MethodBase> TargetMethods()
        {
            var found = new List<MethodBase>();
            try
            {
                Type dc = null;
                foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                {
                    try { dc = asm.GetType("DevConsole"); } catch { }
                    if (dc != null) break;
                }
                var m = dc?.GetMethod("ToggleConsole",
                    BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                if (m != null) found.Add(m);
                else Plugin.Log.LogWarning("[VANILLA-FIX] DevConsole.ToggleConsole NOT found — "
                                          + "our chat's Enter will also toggle the vanilla chat");
            }
            catch (Exception ex) { VanillaFixSupport.LogError("DevConsoleToggleGuard", ex); }
            return found;
        }

        [HarmonyPrefix]
        private static bool BeforeToggle()
        {
            try
            {
                // Only while OUR box owns the keyboard. Every other caller
                // (a genuine Enter with our chat closed, the platform dialog
                // callback) passes through untouched.
                //
                // Deadlock-proof by construction: if vanilla's box is ACTUALLY on
                // screen we always let the toggle through, so Enter can close it
                // even in the (patch-failed, flag-desynced) state where both boxes
                // somehow ended up open. A guard that can trap the player behind a
                // live text field is worse than the bug it fixes.
                if (CompetitiveUI.IsChatInputOpen && !CompetitiveUI.VanillaChatBoxOnScreen)
                    return false;
            }
            catch (Exception ex) { VanillaFixSupport.LogError("DevConsoleToggleGuard", ex); }
            return true;
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("DevConsoleToggleGuard", exception);
        }
    }

    /// <summary>Damage-dealt telemetry for FFA (bugs #127 / #130).
    ///
    /// <para>Nothing in the mod or the database ever recorded damage DEALT — only damage
    /// taken (the left half of <c>block_timeline</c>). Vanilla's
    /// <c>HealthHandler.DoDamage(damage, position, blinkColor, damagingWeapon, damagingPlayer, …)</c>
    /// carries the dealing <c>Player</c>, and since <c>CallTakeDamage</c> RPCs to
    /// <c>RpcTarget.All</c> every client runs it for every hit — the same property FFA kill
    /// credit already relies on. So a single Postfix gives the reporter a complete
    /// per-player damage table with no new Photon heartbeat fields.</para>
    ///
    /// <para>The hook is <c>CharacterStatModifiers.DealtDamage</c>, NOT <c>DoDamage</c> itself,
    /// and that choice is load-bearing: <c>DoDamage</c> opens with
    /// <c>if (damage == zero || !isPlaying || dead || (block.IsBlocking() &amp;&amp; !ignoreBlock) || isRespawning) return;</c>
    /// — a Postfix on it runs even on those early returns, so every BLOCKED shot would have
    /// been credited as damage dealt. <c>DealtDamage</c> is called on the dealer's own stats
    /// component immediately AFTER that guard, and receives the victim, so it fires exactly
    /// once per unit of damage that really landed. <c>__instance</c> is the DEALER's
    /// component (vanilla calls <c>damagingPlayer.GetComponent&lt;CharacterStatModifiers&gt;()</c>).</para>
    ///
    /// <para>FFA-gated (the only mode asking for it) and Postfix, so a throw here can never
    /// interfere with damage actually being applied. Note learning #137: <c>damagingWeapon</c>
    /// is the gun for DOT ticks too, so attribution deliberately uses the dealer identity —
    /// which means DOT and explosion damage IS credited to whoever applied it, unlike the
    /// bullets_hit counter which counts only direct impacts.</para></summary>
    [HarmonyPatch(typeof(CharacterStatModifiers), "DealtDamage")]
    internal static class FfaDamageDealtTrackerPatch
    {
        [HarmonyPostfix]
        private static void AfterDealtDamage(CharacterStatModifiers __instance, Vector2 damage,
                                            bool selfDamage, Player damagedPlayer)
        {
            try
            {
                if (selfDamage || damagedPlayer == null) return;
                if (!FfaMode.EngineActive()) return;
                var dealer = __instance != null ? __instance.GetComponent<Player>() : null;
                if (dealer == null) return;
                FfaMode.RecordDamageDealt(dealer, damagedPlayer, damage.magnitude);
            }
            catch (Exception ex) { VanillaFixSupport.LogError("FfaDamageDealtTracker", ex); }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("FfaDamageDealtTracker", exception);
        }
    }

    /// <summary>Aug 6 item 10 — FFA sudden death.
    ///
    /// <para>When the lobby option is on and someone is at match point, every player
    /// EXCEPT the match-point player(s) has friendly fire disabled: damage between two
    /// non-match-point players is suppressed until all match-point players are dead.
    /// The whole rule lives in <see cref="FfaMode.SuddenDeathSuppresses"/>, whose doc
    /// carries the cross-client determinism argument.</para>
    ///
    /// <para>Hooked on the 9-arg <c>HealthHandler.DoDamage</c> — the single funnel every
    /// health change passes through, direct hits and DOT ticks alike
    /// (HealthHandler.cs:267). Returning false skips vanilla entirely, so no health
    /// moves, no <c>DealtDamage</c> credit is recorded, <c>lastSourceOfDamage</c> is not
    /// rewritten (so kill credit cannot be stolen by a suppressed hit) and no death RPC
    /// can fire. Knockback is untouched: force travels through
    /// <c>CallTakeForce</c>/<c>TakeForce</c>, a different path — so bullets still shove,
    /// they just do not wound.</para>
    ///
    /// <para>Prefix rather than Postfix on purpose (#256 is about the opposite trap):
    /// a Postfix here could not prevent anything, and vanilla's own early-return block
    /// at the top of DoDamage is irrelevant to us because we run BEFORE it.</para>
    ///
    /// <para>INERT unless every condition holds: FFA engine active, the lobby's frozen
    /// config says sudden death, and someone is actually at match point. Outside FFA
    /// the very first check in <c>SuddenDeathSuppresses</c> returns false.</para></summary>
    [HarmonyPatch(
        typeof(HealthHandler),
        "DoDamage",
        new Type[]
        {
            typeof(Vector2),
            typeof(Vector2),
            typeof(Color),
            typeof(GameObject),
            typeof(Player),
            typeof(bool),
            typeof(bool),
            typeof(bool),
            typeof(HealthHandler.DamageSource)
        })]
    internal static class FfaSuddenDeathPatch
    {
        [HarmonyPrefix]
        private static bool BeforeDoDamage(HealthHandler __instance, Player damagingPlayer)
        {
            try
            {
                if (damagingPlayer == null) return true;      // out-of-bounds etc.
                if (!FfaMode.SuddenDeath) return true;        // cheapest gate first
                var victim = __instance != null ? __instance.GetComponent<Player>() : null;
                if (victim == null) return true;
                if (!FfaMode.SuddenDeathSuppresses(damagingPlayer, victim)) return true;

                VanillaFixSupport.DiagLimited(
                    "FfaSuddenDeath-suppressed",
                    "FfaSuddenDeath suppressed damage between two non-match-point players",
                    12);
                return false;
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("FfaSuddenDeath", ex);
                return true;   // never let this patch eat a legitimate hit
            }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("FfaSuddenDeath", exception);
        }
    }

    /// <summary>Bug #128 — the pick phase reads player input BEHIND GameManager.lockInput.
    ///
    /// <para><c>CardChoice.DoPlayerSelect</c> pulls the action set straight off the player
    /// (<c>PlayerManager.GetActionsFromPlayer(pickrID)</c>) and reads <c>Right/Left.Value</c>
    /// and <c>Jump.WasPressed</c> from it. It never consults <c>GameManager.lockInput</c>,
    /// which only gates <c>GeneralInput.Update</c>. So while the T chat has focus, typing
    /// "a"/"d" still slid the card highlight and a SPACE inside a message still CONFIRMED
    /// the pick. That hole predates this bug (the chat has always been openable during the
    /// pick phase) but it is squarely the thing #128 asks us to make safe.</para>
    ///
    /// <para>Suppressed by skipping the vanilla method rather than by toggling
    /// <c>playerActions.Enabled</c>: a mutated Enabled flag is one more piece of state that
    /// can be stranded if we stop running (learning #75's failure mode), whereas a Prefix
    /// that reads our own bool cannot leave anything behind. The picker keeps its current
    /// highlight; nothing else in the pick flow is touched.</para></summary>
    [HarmonyPatch(typeof(CardChoice), "DoPlayerSelect")]
    internal static class CardPickChatInputGuardPatch
    {
        [HarmonyPrefix]
        private static bool BeforeDoPlayerSelect()
        {
            try
            {
                if (CompetitiveUI.AnyChatTyping) return false;
            }
            catch (Exception ex) { VanillaFixSupport.LogError("CardPickChatInputGuard", ex); }
            return true;
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("CardPickChatInputGuard", exception);
        }
    }

    /// <summary><para>Quality-of-life (Sid, 2026-08-01, alongside the room-code
    /// FAQ correction): when the player hosts a private room (Online → Host
    /// Room), copy the 6-character room code to the clipboard the moment
    /// vanilla displays it, and say so. <c>LoadingScreen.SetRoomCode</c> is
    /// the exact display moment (HostPrivateRoom's connected callback calls
    /// it right after CreateRoom), so the hook can never fire for a join or
    /// a mod-issued queue room — those paths never call SetRoomCode.</para></summary>
    [HarmonyPatch(typeof(LoadingScreen), "SetRoomCode")]
    internal static class HostRoomCodeClipboardPatch
    {
        [HarmonyPostfix]
        private static void AfterSetRoomCode(string roomCode)
        {
            try
            {
                if (string.IsNullOrEmpty(roomCode)) return;
                GUIUtility.systemCopyBuffer = roomCode;
                CompetitiveUI.ShowNotification(
                    $"Room code {roomCode} copied to clipboard - paste it to your friends!",
                    new Color(0.6f, 1f, 0.6f), 6f);
                Plugin.Log.LogInfo($"[HOSTROOM] room code {roomCode} copied to clipboard");
            }
            catch (Exception ex) { VanillaFixSupport.LogError("HostRoomCodeClipboard", ex); }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("HostRoomCodeClipboard", exception);
        }
    }

    /// <summary>Forensics for the DC #1 class (Aug 12, bug 208 session): the
    /// log could prove the esc menu was OPEN during a pick phase (its button
    /// hover coroutines failed on the then-dead ListMenu host) but not WHEN
    /// it opened. Logs each ToggleEsc INVOCATION and the resulting state,
    /// online rooms only. Honest limits (review r1): a submenu-close call
    /// returns without toggling (so consecutive OPEN lines are possible),
    /// Esc key vs controller Command remain indistinguishable, and a throw
    /// inside the original skips this Postfix. It narrows the timeline; it
    /// does not identify the input source. Display/diag only.</summary>
    [HarmonyPatch(typeof(EscapeMenuHandler), "ToggleEsc")]
    internal static class EscToggleDiagPatch
    {
        private static void Postfix()
        {
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode) return;
                bool battle = false;
                try { battle = GameManager.instance != null && GameManager.instance.battleOngoing; } catch { }
                Plugin.Log.LogInfo($"[ESC-DIAG] esc menu -> {(EscapeMenuHandler.isEscMenu ? "OPEN" : "closed")} " +
                                   $"(room={PhotonNetwork.CurrentRoom?.Name}, battle={battle})");
            }
            catch { }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("EscToggleDiag", exception);
        }
    }

    /// <summary>Bug #234: vanilla publishes the literal pre-connect placeholder
    /// <c>PlayerName</c> before joining, then replaces it with the Steam persona as the
    /// final statement of <c>NetworkConnectionHandler.OnJoinedRoom</c>. A transient
    /// persona lookup failure can therefore leave the local actor property at the
    /// placeholder for the whole room. Always wake the persistent retry driver after
    /// the callback, including when the original throws; returning the same exception
    /// preserves vanilla's failure semantics.</summary>
    [HarmonyPatch(typeof(NetworkConnectionHandler), "OnJoinedRoom")]
    internal static class PlayerNicknameRepairPatch
    {
        [HarmonyFinalizer]
        private static Exception AfterJoin(Exception __exception)
        {
            try { PlayerNicknameRepairDriver.RequestImmediateCheck(); }
            catch (Exception ex) { VanillaFixSupport.LogError("PlayerNicknameRepair", ex); }
            return __exception;
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("PlayerNicknameRepair", exception);
        }
    }

    /// <summary>Companion attach point for bug #234's render repair. Vanilla
    /// <c>PlayerName.Start</c> copies <c>PhotonView.Owner.NickName</c> into TMP once
    /// and never revisits it. Reassert the current value after Start; later actor-name
    /// changes use the same helper from <see cref="PlayerNicknameRepairDriver"/>'s
    /// Photon property callback.</summary>
    [HarmonyPatch(typeof(PlayerName), "Start")]
    internal static class PlayerNicknameLabelRefreshPatch
    {
        [HarmonyPostfix]
        private static void AfterStart(PlayerName __instance)
        {
            try
            {
                if (__instance == null) return;
                if (__instance.GetComponent<PlayerNicknameLabelRefresher>() == null)
                    __instance.gameObject.AddComponent<PlayerNicknameLabelRefresher>();
                PlayerNicknameRepairDriver.RefreshLabel(__instance);
            }
            catch (Exception ex) { VanillaFixSupport.LogError("PlayerNicknameLabelRefresh", ex); }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("PlayerNicknameLabelRefresh", exception);
        }
    }

    /// <summary>Persistent, display-only half of bug #234. A slow tick retries the
    /// local Steam persona lookup only while an online room actually has a missing or
    /// placeholder nickname. Photon actor-property callbacks repaint the handful of
    /// live PlayerName labels only when key 255 (NickName) changes, avoiding a label
    /// poll and covering both modded and unmodded remote actors that later heal.</summary>
    internal sealed class PlayerNicknameRepairDriver : MonoBehaviourPunCallbacks
    {
        private const string VanillaPlaceholder = "PlayerName";
        private const int MaxRepairAttemptsPerRoom = 15;
        private const float CheckIntervalSeconds = 2f;

        private static PlayerNicknameRepairDriver _instance;
        private static bool _immediateCheckPending;

        private Photon.Realtime.Room _observedRoom;
        private int _repairAttempts;
        private bool _exhaustionLogged;
        private float _nextCheck;

        private void Awake()
        {
            _instance = this;
            _nextCheck = 0f;
            Plugin.Log?.LogInfo("[VANILLA-FIX] PlayerNicknameRepairDriver attached");
        }

        private void OnDestroy()
        {
            if (ReferenceEquals(_instance, this)) _instance = null;
        }

        internal static void RequestImmediateCheck()
        {
            _immediateCheckPending = true;
            if (_instance != null) _instance._nextCheck = 0f;
        }

        private void Update()
        {
            if (_immediateCheckPending)
            {
                _immediateCheckPending = false;
                _nextCheck = 0f;
            }

            float now = Time.unscaledTime;
            if (now < _nextCheck) return;
            _nextCheck = now + CheckIntervalSeconds;

            try { CheckLocalNickname(); }
            catch (Exception ex) { VanillaFixSupport.LogError("PlayerNicknameRepair", ex); }
        }

        public override void OnJoinedRoom()
        {
            BeginRoom(PhotonNetwork.CurrentRoom);
            RequestImmediateCheck();
        }

        public override void OnLeftRoom()
        {
            BeginRoom(null);
        }

        public override void OnPlayerPropertiesUpdate(
            Photon.Realtime.Player targetPlayer,
            ExitGames.Client.Photon.Hashtable changedProps)
        {
            try
            {
                // Photon Realtime reserves actor-property key 255 for NickName.
                // LoadBalancingClient caches the new value before invoking this callback.
                if (targetPlayer == null || changedProps == null ||
                    !changedProps.ContainsKey(byte.MaxValue)) return;
                RefreshActorLabels(targetPlayer);
            }
            catch (Exception ex) { VanillaFixSupport.LogError("PlayerNicknameLabelRefresh", ex); }
        }

        private void BeginRoom(Photon.Realtime.Room room)
        {
            _observedRoom = room;
            _repairAttempts = 0;
            _exhaustionLogged = false;
            _nextCheck = 0f;
        }

        private void CheckLocalNickname()
        {
            if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode ||
                PhotonNetwork.CurrentRoom == null)
            {
                if (_observedRoom != null) BeginRoom(null);
                return;
            }

            Photon.Realtime.Room room = PhotonNetwork.CurrentRoom;
            if (!ReferenceEquals(_observedRoom, room)) BeginRoom(room);

            Photon.Realtime.Player localPlayer = PhotonNetwork.LocalPlayer;
            if (localPlayer == null) return;

            string currentNickname = PhotonNetwork.NickName;
            if (!NeedsRepair(currentNickname)) return;

            if (_repairAttempts >= MaxRepairAttemptsPerRoom)
            {
                LogExhaustion();
                return;
            }

            // A missing Steam process is an unmet prerequisite, not a failed repair:
            // do not burn the bounded retry budget until a persona lookup can run (#98).
            bool steamRunning;
            try { steamRunning = Steamworks.SteamAPI.IsSteamRunning(); }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("PlayerNicknameRepairPrerequisite", ex);
                return;
            }
            if (!steamRunning) return;

            _repairAttempts++;
            string persona;
            try
            {
                persona = Steamworks.SteamFriends.GetPersonaName();
            }
            catch (InvalidOperationException ex)
            {
                // SteamFriends.GetPersonaName's installed wrapper throws this only
                // when InteropHelp.TestIfAvailableClient cannot initialize its client
                // context. That is still a missing prerequisite, so refund the attempt.
                _repairAttempts--;
                VanillaFixSupport.LogError("PlayerNicknameRepairPrerequisite", ex);
                return;
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("PlayerNicknameRepair", ex);
                if (_repairAttempts >= MaxRepairAttemptsPerRoom) LogExhaustion();
                return;
            }

            try
            {
                if (string.IsNullOrWhiteSpace(persona))
                {
                    VanillaFixSupport.DiagLimited(
                        "PlayerNicknameRepair-empty-persona",
                        "PlayerNicknameRepair got an empty Steam persona on attempt " +
                        _repairAttempts + "/" + MaxRepairAttemptsPerRoom, 3);
                    if (_repairAttempts >= MaxRepairAttemptsPerRoom) LogExhaustion();
                    return;
                }

                // Verified against installed PhotonRealtime.Player.NickName:
                // for the local actor in an online room this sends property key 255.
                PhotonNetwork.NickName = persona;

                // If this account has nametag cosmetics, refresh NametagStyler's base
                // from the healed raw persona and publish the wrapped value next.
                NametagStyler.PublishToPhoton();
                RefreshActorLabels(localPlayer);

                if (!NeedsRepair(PhotonNetwork.NickName))
                {
                    Plugin.Log?.LogInfo(
                        "[VANILLA-FIX] PlayerNicknameRepair healed the local actor nickname " +
                        "on attempt " + _repairAttempts + "/" + MaxRepairAttemptsPerRoom);
                    return;
                }

                // Steam can legitimately return the reserved literal as a person's real
                // display name. It is indistinguishable from vanilla's placeholder, but
                // the platform lookup succeeded, so preserve it and avoid 14 useless calls.
                if (string.Equals(NametagStyler.Clean(persona), VanillaPlaceholder,
                    StringComparison.Ordinal))
                {
                    _repairAttempts = MaxRepairAttemptsPerRoom;
                    _exhaustionLogged = true;
                    Plugin.Log?.LogWarning(
                        "[VANILLA-FIX] PlayerNicknameRepair platform persona equals the " +
                        "reserved vanilla placeholder; preserving the platform value");
                }
                else if (_repairAttempts >= MaxRepairAttemptsPerRoom)
                {
                    LogExhaustion();
                }
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("PlayerNicknameRepair", ex);
                if (_repairAttempts >= MaxRepairAttemptsPerRoom) LogExhaustion();
            }
        }

        private void LogExhaustion()
        {
            if (_exhaustionLogged) return;
            _exhaustionLogged = true;
            Plugin.Log?.LogWarning(
                "[VANILLA-FIX] PlayerNicknameRepair exhausted " +
                MaxRepairAttemptsPerRoom + " in-room attempt(s); nickname is still unavailable");
        }

        private static bool NeedsRepair(string nickname)
        {
            if (string.IsNullOrWhiteSpace(nickname)) return true;
            string clean = NametagStyler.Clean(nickname);
            return string.IsNullOrWhiteSpace(clean) ||
                   string.Equals(clean, VanillaPlaceholder, StringComparison.Ordinal);
        }

        private static void RefreshActorLabels(Photon.Realtime.Player player)
        {
            if (player == null) return;
            foreach (PlayerName playerName in UnityEngine.Object.FindObjectsOfType<PlayerName>())
            {
                try
                {
                    PhotonView view = playerName.GetComponentInParent<PhotonView>();
                    if (view == null || view.Owner == null ||
                        view.Owner.ActorNumber != player.ActorNumber) continue;
                    RefreshLabel(playerName);
                }
                catch (Exception ex)
                {
                    VanillaFixSupport.LogError("PlayerNicknameLabelRefresh", ex);
                }
            }
        }

        internal static void RefreshLabel(PlayerName playerName)
        {
            if (playerName == null) return;

            PhotonView view = playerName.GetComponentInParent<PhotonView>();
            Component label = TeamColorIdentity.FindTmpInParents(playerName.transform);
            if (view == null || view.Owner == null || label == null) return;

            string value = PhotonNetwork.OfflineMode ? string.Empty : view.Owner.NickName;
            PropertyInfo textProperty = label.GetType().GetProperty(
                "text", BindingFlags.Public | BindingFlags.Instance);
            if (textProperty == null || !textProperty.CanWrite ||
                textProperty.PropertyType != typeof(string)) return;

            string existing = null;
            try { existing = textProperty.GetValue(label, null) as string; } catch { }
            if (!string.Equals(existing, value, StringComparison.Ordinal))
                textProperty.SetValue(label, value ?? string.Empty, null);
        }
    }

    /// <summary>No-poll complement to the actor-property callback. Unity excludes
    /// inactive player roots from FindObjectsOfType, so a nickname can heal while a
    /// dead player's label is inactive. The same label object is reused on revive and
    /// PlayerName.Start does not rerun; this OnEnable refresh closes that lifecycle gap.</summary>
    internal sealed class PlayerNicknameLabelRefresher : MonoBehaviour
    {
        private void OnEnable()
        {
            try
            {
                PlayerNicknameRepairDriver.RefreshLabel(GetComponent<PlayerName>());
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("PlayerNicknameLabelRefresh", ex);
            }
        }
    }

    /// <summary>Bug 261 (the FFA second-rematch freeze). Vanilla
    /// GM_ArmsRace.GameOverRematch colors the "REMATCH?" text by HARDCODED
    /// team online — master reads GetColorFromTeam(0), every other seat
    /// GetColorFromTeam(1) — and GetColorFromTeam does
    /// GetPlayersInTeam(teamID)[0], which throws IndexOutOfRange on an
    /// EMPTY team. FFA's leave-tolerant design purges departed fighters
    /// (#222), so once the player occupying slot 0 or 1 left, every seat
    /// on the other side of the master check threw WHILE EVALUATING the
    /// DisplayScreenTextLoop argument — killing GameOverTransition before
    /// the rematch popup existed, so the auto-confirm never engaged and
    /// the room froze on the VICTORY screen (proven in bug 261's log:
    /// slot 1 = Sid left during game 2; every non-master seat froze at
    /// game 2's end). PURE COLOR LOOKUP, zero gameplay semantics —
    /// deliberately UNGATED (#286's ungated bucket): empty team falls back
    /// to the first live player's skin, else a clamped modulo, so the
    /// rematch text merely renders in a fallback color.</summary>
    [HarmonyPatch(typeof(PlayerManager), "GetColorFromTeam")]
    class GetColorFromTeamEmptyTeamPatch
    {
        static bool Prefix(PlayerManager __instance, int teamID, ref PlayerSkin __result)
        {
            try
            {
                var team = __instance.GetPlayersInTeam(teamID);
                if (team != null)
                {
                    if (team.Length > 0 && team[0] != null)
                        return true;   // vanilla path is safe (and the FFA skin
                                       // clamp already guards the id lookup)
                    // Review r1 find 5: a destroyed-but-not-yet-purged member
                    // can occupy slot 0 while a LIVE teammate sits later in
                    // the array — prefer the requested team's live member
                    // over any cross-team fallback.
                    for (int i = 1; i < team.Length; i++)
                        if (team[i] != null)
                        {
                            __result = PlayerSkinBank.GetPlayerSkinColors(team[i].PlayerID);
                            return false;
                        }
                }
                var ps = __instance.players;
                if (ps != null)
                    for (int i = 0; i < ps.Count; i++)
                        if (ps[i] != null)
                        {
                            __result = PlayerSkinBank.GetPlayerSkinColors(ps[i].PlayerID);
                            return false;
                        }
                __result = PlayerSkinBank.GetPlayerSkinColors(((teamID % 4) + 4) % 4);
                return false;
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("GetColorFromTeamEmptyTeam", ex);
                try { __result = PlayerSkinBank.GetPlayerSkinColors(((teamID % 4) + 4) % 4); }
                catch { }
                return false;
            }
        }
    }

    /// <summary>Sibling of the above (same vanilla `[0]`, same window):
    /// GetFirstPlayerInTeam is called by GameOverRematch with the winner's
    /// team, and the 2-second VICTORY wait inside GameOverTransition means
    /// even the WINNER's team can empty out before it runs — a window the
    /// once-only winner re-anchor in FfaMode.HandleNextRound cannot cover.
    /// Empty team: return any live player (callers use it for positioning/
    /// identity, never for scoring), null only when nobody is left.</summary>
    [HarmonyPatch(typeof(PlayerManager), "GetFirstPlayerInTeam")]
    class GetFirstPlayerInTeamEmptyTeamPatch
    {
        static bool Prefix(PlayerManager __instance, int teamID, ref Player __result)
        {
            try
            {
                var team = __instance.GetPlayersInTeam(teamID);
                if (team != null)
                {
                    if (team.Length > 0 && team[0] != null)
                        return true;
                    // Review r1 find 5: prefer a live member of the
                    // REQUESTED team before any cross-team fallback.
                    for (int i = 1; i < team.Length; i++)
                        if (team[i] != null) { __result = team[i]; return false; }
                }
                var ps = __instance.players;
                if (ps != null)
                    for (int i = 0; i < ps.Count; i++)
                        if (ps[i] != null) { __result = ps[i]; return false; }
                __result = null;
                return false;
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("GetFirstPlayerInTeamEmptyTeam", ex);
                __result = null;
                return false;
            }
        }
    }
}
