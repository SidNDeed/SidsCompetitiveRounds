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

    [HarmonyPatch(typeof(Gun), "ResetStats")]
    internal static class DemonicPactSprayPatch
    {
        [HarmonyPostfix]
        private static void AfterResetStats(Gun __instance)
        {
            try
            {
                if (!VanillaFixSupport.GameplayScope()) return;
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
                if (!VanillaFixSupport.GameplayScope()) return;

                // Adversarial-review find (Claude): healthRemoval ticks come
                // from TWO gameplay surfaces — poison DoT (the desync being
                // fixed) AND the Decay card, which spreads EVERY direct hit
                // into healthRemoval ticks over stats.secondsToTakeDamageOver.
                // Forcing ignoreBlock on a Decay holder would delete their
                // block-the-spread mitigation (a real ranked balance change,
                // not a desync fix). Exempt victims whose stats route direct
                // damage through the DoT path; they keep vanilla behavior
                // (including, rarely, the ghost-tick desync) until a designed
                // decision says otherwise.
                CharacterStatModifiers stats = __instance.GetComponent<CharacterStatModifiers>();
                if (stats != null && stats.secondsToTakeDamageOver != 0f) return;

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
                if (!VanillaFixSupport.GameplayScope()) return;

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
                if (!VanillaFixSupport.GameplayScope()) return;

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
                if (!VanillaFixSupport.GameplayScope()) return;

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
                if (!VanillaFixSupport.GameplayScope()) return true;
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
                if (!VanillaFixSupport.GameplayScope()) return true;
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
}
