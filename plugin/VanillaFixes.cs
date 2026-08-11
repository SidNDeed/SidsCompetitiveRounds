using System;
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
                bool shouldLog;
                lock (Sync)
                {
                    int count;
                    DiagnosticCounts.TryGetValue(key, out count);
                    shouldLog = count < maximum;
                    if (shouldLog) DiagnosticCounts[key] = count + 1;
                }

                if (shouldLog)
                    Plugin.Log.LogInfo("[VANILLA-DIAG] " + message);
            }
            catch
            {
                // Diagnostics are best effort only.
            }
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
        private static void ChargeIntensity(DeathEffect fx, float value)
        {
            try
            {
                object sp = AccessTools.Field(typeof(DeathEffect), "soundParameterChargeLoopIntensity")?.GetValue(fx);
                if (sp == null) return;
                var f = AccessTools.Field(sp.GetType(), "intensity");
                if (f != null) { f.SetValue(sp, value); return; }
                var pr = AccessTools.Property(sp.GetType(), "intensity");
                if (pr != null && pr.CanWrite) pr.SetValue(sp, value, null);
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

        [HarmonyFinalizer]
        private static Exception Finalizer(Exception __exception)
        {
            if (__exception != null)
                VanillaFixSupport.DiagLimited(
                    "SonigonVoiceUpdateGuard-swallowed",
                    "InstanceSoundEvent.ManagedUpdate threw " + __exception.GetType().Name +
                    " — swallowed so the sound manager's other voices keep updating",
                    20);
            return null;
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

                string key = n + "|" + normalize + "|" + modIssued + "|" + allRankedIntent + "|" + allCap;
                if (key != _lastLogKey)
                {
                    _lastLogKey = key;
                    Plugin.Log.LogInfo("[GROW-NORM] " + (normalize ? "NORMALIZING" : "vanilla growth")
                        + " room=" + n + " modIssued=" + modIssued
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
                    VanillaFixSupport.DiagLimited(
                        "StaleProjectileSweep-despawn",
                        "StaleProjectileSweep despawned " +
                        swept.ToString(CultureInfo.InvariantCulture) +
                        " leftover projectile(s) at " + reason,
                        10);
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
            return VanillaFixSupport.Cleanup("StaleProjectileSweep", exception);
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
}
