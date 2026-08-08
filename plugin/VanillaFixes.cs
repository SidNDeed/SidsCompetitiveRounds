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
        private static void DiagnoseMissingDrillEffect(
            ProjectileHit __instance,
            int viewID,
            int colliderID)
        {
            try
            {
                if (viewID != -1 || colliderID < 0) return;
                // Ungated (#151): log-only.

                PhotonView view = __instance.GetComponent<PhotonView>();
                if (view == null || view.IsMine) return;

                RayHitDrill[] drills = __instance.GetComponentsInChildren<RayHitDrill>(true);
                if (drills == null || drills.Length == 0) return;

                bool missing = __instance.effects == null;
                if (!missing)
                {
                    for (int i = 0; i < drills.Length; i++)
                    {
                        if (!__instance.effects.Contains(drills[i]))
                        {
                            missing = true;
                            break;
                        }
                    }
                }

                if (missing)
                {
                    VanillaFixSupport.DiagLimited(
                        "DrillVisibility-missing-effect",
                        "DrillVisibility found a Drill child missing from ProjectileHit.effects" +
                        " view=" + view.ViewID.ToString(CultureInfo.InvariantCulture) +
                        " frame=" + Time.frameCount.ToString(CultureInfo.InvariantCulture),
                        20);
                }
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("DrillVisibility.Diagnostic", ex);
            }
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
