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
                if (!VanillaFixSupport.GameplayScope()) return;
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

    /// <summary>Bug #91 items 4/5 (July 27 log forensics): vanilla starts
    /// coroutines on INACTIVE GameObjects and Unity refuses with a console
    /// error each time (~14/session). Proven sites, all missing the
    /// activeInHierarchy guard vanilla's own HealthHandler.Revive has:
    /// RPCA_SendForceOverTime / RPCA_SendForceTowardsPointOverTime land from
    /// the same hit-volley that just killed the player (RPCA_Die SetActive
    /// false first), DamageOverTime.TakeDamageOverTime is the DOT-tick twin,
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
                if (!VanillaFixSupport.GameplayScope()) return true;
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
                if (!VanillaFixSupport.GameplayScope()) return true;
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

    [HarmonyPatch(typeof(DamageOverTime), "TakeDamageOverTime")]
    internal static class DeadPlayerDotPatch
    {
        [HarmonyPrefix]
        private static bool BeforeDotTick(DamageOverTime __instance)
        {
            try
            {
                if (!VanillaFixSupport.GameplayScope()) return true;
                if (__instance != null && !__instance.gameObject.activeInHierarchy)
                    return false;
            }
            catch (Exception ex) { VanillaFixSupport.LogError("DeadPlayerDot", ex); }
            return true;
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("DeadPlayerDot", exception);
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
                if (!VanillaFixSupport.GameplayScope()) return true;
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
}
