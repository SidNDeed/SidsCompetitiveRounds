using BepInEx;
using BepInEx.Bootstrap;
using BepInEx.Configuration;
using BepInEx.Logging;
using HarmonyLib;
using Photon.Pun;
using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Reflection;
using System.Runtime.InteropServices;
using InControl;
using UnityEngine;
using UnityEngine.Rendering.PostProcessing;

namespace CompetitiveRounds
{
    [BepInPlugin(ModId, ModName, ModVersion)]
    [BepInProcess("Rounds.exe")]
    public class Plugin : BaseUnityPlugin
    {
        public const string ModId = "com.competitiverounds.mod";
        public const string ModName = "Competitive ROUNDS";
        public const string ModVersion = "1.34.2";   // July 24: cosmetic placement workflow, flag evidence, perf pass; STATS_CLEAN/STEAM_AUTH gates stay at 1.34.0 (1.34.2 passes them)
        public const string RequiredGameVersion = "1.1.2";

        internal static ManualLogSource Log;
        internal static CompetitiveRoundsBehaviour Instance;
        internal static Harmony HarmonyInstance;

        // Config entries
        internal static ConfigEntry<string> ApiBaseUrl;
        internal static ConfigEntry<bool> RankedEnabled;
        internal static ConfigEntry<bool> RankedDisabledByConsent;
        internal static ConfigEntry<bool> ShowNotifications;
        internal static ConfigEntry<bool> ShowFps;
        internal static ConfigEntry<bool> ShowRegionPing;
        internal static ConfigEntry<bool> ShowIngameChat;
        internal static ConfigEntry<bool> ShowTrails;
        internal static ConfigEntry<bool> ShowBlockDebug;
        internal static ConfigEntry<bool> ShowPlayerColors;
        internal static ConfigEntry<bool> ShowInputOverlay;
        // v1.32 items 7+8 — standalone accessibility/FPS toggles. Deliberately
        // NOT under the Performance master switch: these are user preferences
        // that should survive a perf-master flip (map note, settings tab).
        internal static ConfigEntry<bool> ScreenShakeEnabled;
        internal static ConfigEntry<bool> MapLightingEnabled;
        internal static ConfigEntry<bool> MapShadowsEnabled;
        internal static ConfigEntry<bool> AnimatedCosmetics;
        internal static ConfigEntry<bool> ChromaticAberrationEnabled;
        internal static ConfigEntry<bool> AutoRequeueOnMatchmakingBug;
        // Performance pass — master + 7 per-patch flags so users can disable
        // any individual port without giving up the rest. Mirrors the
        // granularity the original "Performance Improvements" mod offered.
        internal static ConfigEntry<bool> PerfOptimizations;
        internal static ConfigEntry<bool> PerfStunPlayerNullGuard;
        internal static ConfigEntry<bool> PerfDespawnOffscreenBullets;
        internal static ConfigEntry<bool> PerfSwallowHitSoundNREs;
        internal static ConfigEntry<bool> PerfSwallowEdgeBounceNREs;
        internal static ConfigEntry<bool> PerfSkipMenuUpdateInMatch;
        // v1.26.9 — user-noticeable batch (cap-style perf wins).
        internal static ConfigEntry<bool> PerfBulletHitParticleCap;
        internal static ConfigEntry<bool> PerfClampObjectPoolInit;
        // PerfPauseCardPickParticles REMOVED v1.28.3 — the "skin preview particle
        // system" it paused IS the picker's body; pausing it the frame it spawns
        // rendered the pick-phase character invisible (bug #29).
        // Preferred timezone for tournament time display. Values: "Local" (use OS),
        // "UTC", or an IANA / Windows tz ID that TimeZoneInfo.FindSystemTimeZoneById
        // resolves. Persisted so it survives restarts; applies only to tournament UI.
        internal static ConfigEntry<string> TournamentTimezone;
        // Preferred date/time format. Values:
        //   "ISO" = 2026-04-24 14:30       (unambiguous, ASCII, 24h)
        //   "US"  = Sat 04/24 2:30 PM      (Anglophone default)
        //   "EU"  = Sat 24/04 14:30        (most of Europe + others)
        // All formats emit ASCII-only using CultureInfo.InvariantCulture so the
        // Gravity SDF font renders them cleanly regardless of OS locale.
        internal static ConfigEntry<string> TournamentDateFormat;
        // Pipe-delimited list of muted display names — local mute, doesn't leave the client.
        // Mutated via /mute and /unmute commands typed in the F5 chat input.
        internal static ConfigEntry<string> MutedChatNames;
        // Tri-state "" (unset — ask at launch) / "granted" / "denied".
        // Gates ALL outbound API traffic except the mod-version probe and consent-revocation calls.
        internal static ConfigEntry<string> DataConsent;

        public static bool DataConsentGranted => DataConsent != null && DataConsent.Value == "granted";
        public static bool DataConsentAsked   => DataConsent != null && !string.IsNullOrEmpty(DataConsent.Value);

        private static bool spawned = false;
        internal static bool modDisabled = false;

        // Ranked queue auto-join state (on Plugin so it survives scene changes)
        private static string pendingRankedRoom = null;
        private static string pendingRankedRegion = null;
        private static bool pendingRoomLeaving = false;
        private static float pendingRoomLogTimer = 0f;
        public static string PendingRankedRoom => pendingRankedRoom;
        public static string PendingRankedRegion => pendingRankedRegion;

        public static void SetPendingRoom(string roomName, string region = null)
        {
            pendingRankedRoom = roomName;
            pendingRankedRegion = region;
            Log.LogInfo($"[QUEUE] Pending ranked room set: {roomName} (region: {region ?? "auto"})");
        }

        public static void ClearPendingRoom()
        {
            pendingRankedRoom = null;
            pendingRankedRegion = null;
            pendingRoomLeaving = false;
        }

        // 2v2 slot 0-3 the server-side balancer assigned to us. Set when the
        // poll returns ready_join (computed from team_assigned + steam-id sort
        // within team). Read by PlayerAssigner_CreatePlayer_2v2_Patch to give
        // each of the 4 players a unique m_playerId — vanilla ROUNDS hardcodes
        // 0 for master, 1 for everyone else, which makes all 3 non-masters
        // collide on slot 1 and overwrite each other in PlayerManager.players.
        // Reset on room leave or series end.
        private static int pending2v2Slot = -1;
        public static int Pending2v2Slot => pending2v2Slot;
        public static void SetPending2v2Slot(int slot)
        {
            pending2v2Slot = slot;
            Log.LogInfo($"[2v2] Pending slot set: {slot} (team={(slot < 2 ? 1 : 2)})");
        }
        public static void ClearPending2v2Slot()
        {
            if (pending2v2Slot >= 0) Log.LogInfo("[2v2] Pending slot cleared");
            pending2v2Slot = -1;
        }

        // 1v2 slot 0-2 assigned at ovt queue lock: 0 = solo (team 0), 1/2 = duo
        // (team 1, in the server's duo_a/duo_b order so all three clients agree).
        // Same lifecycle as Pending2v2Slot: set on ready_join, cleared on queue
        // leave / poll expiry / series end. Read by the CreatePlayer override.
        private static int pendingOvtSlot = -1;
        public static int PendingOvtSlot => pendingOvtSlot;
        public static void SetPendingOvtSlot(int slot)
        {
            pendingOvtSlot = slot;
            Log.LogInfo($"[1v2] Pending slot set: {slot} ({(slot == 0 ? "solo/team0" : "duo/team1")})");
        }
        public static void ClearPendingOvtSlot()
        {
            if (pendingOvtSlot >= 0) Log.LogInfo("[1v2] Pending slot cleared");
            pendingOvtSlot = -1;
        }

        private void Awake()
        {
            Log = Logger;

            // BepInEx 5 defaults AppendLog=false, which truncates LogOutput.log
            // on every launch — meaning if a player crashes and reopens to file
            // a bug report, the crash log is gone. Hook Application.quitting
            // to snapshot the current session's log to LogOutput-prev.log
            // BEFORE BepInEx truncates the next run. Best-effort; failures are
            // swallowed (file lock / disk-full) so plugin load can't be blocked.
            try
            {
                UnityEngine.Application.quitting += () =>
                {
                    try
                    {
                        string src = CompetitiveUI.BepInExLogPathPublic();
                        string dst = CompetitiveUI.BepInExLogPreviousPath();
                        if (!string.IsNullOrEmpty(src) && !string.IsNullOrEmpty(dst) && System.IO.File.Exists(src))
                        {
                            System.IO.File.Copy(src, dst, overwrite: true);
                            Log.LogInfo($"[BUG-REPORT] log snapshot saved: {dst}");
                        }
                    }
                    catch (Exception ex) { Log.LogWarning($"[BUG-REPORT] quit-time log copy failed: {ex.Message}"); }
                };
            }
            catch (Exception ex) { Log.LogWarning($"[BUG-REPORT] quit hook bind failed: {ex.Message}"); }

            ApiBaseUrl = Config.Bind(
                "API", "BaseUrl",
                "http://competitive-rounds.duckdns.org:8443",
                "Base URL of the Competitive ROUNDS API server"
            );

            RankedEnabled = Config.Bind(
                "Ranked", "Enabled",
                true,
                "Whether ranked tracking is active"
            );

            // Set when a consent REVOKE auto-disabled ranked (vs. the user clicking
            // Disable). On the next consent grant, ranked is restored automatically —
            // without this, a decline/revoke silently left ranked off forever and the
            // startup sync kept pushing ranked_enabled=false, so every game vs that
            // player recorded casual (bug #47's "opponents have ranked disabled and
            // I'm not sure they intended it").
            RankedDisabledByConsent = Config.Bind(
                "Ranked", "DisabledByConsentRevoke",
                false,
                "Internal: ranked was auto-disabled by a data-consent revoke, not by the user"
            );

            ShowNotifications = Config.Bind(
                "UI", "ShowNotifications",
                true,
                "Show in-game notifications for match results"
            );

            ShowFps = Config.Bind(
                "UI", "ShowFps",
                true,
                "Show FPS counter in the top-left corner"
            );

            ShowRegionPing = Config.Bind(
                "UI", "ShowRegionPing",
                true,
                "Show Photon ping and region alongside FPS when in a room"
            );

            ShowIngameChat = Config.Bind(
                "UI", "ShowIngameChat",
                true,
                "Show the in-game chat overlay while outside the F5 menu"
            );

            ShowTrails = Config.Bind(
                "UI", "ShowTrails",
                true,
                "Show cosmetic trails behind players during matches (including your own and opponents')"
            );

            ShowBlockDebug = Config.Bind(
                "UI", "ShowBlockDebug",
                false,
                "Show the Block Debug overlay (top-right corner) during matches. Displays live counts of block activations vs successful absorbs, dedup drops, and per-hit timing ('too early' / 'too slow') so you can see why a block didn't land."
            );

            ShowPlayerColors = Config.Bind(
                "UI", "ShowPlayerColors",
                true,
                "Render custom player body colors (purchased from the Body Color shop tab) — your own and other modded players'. Off = everyone falls back to the default orange/blue team colors."
            );

            ShowInputOverlay = Config.Bind(
                "UI", "ShowInputOverlay",
                false,
                "Show a bottom-left WASD + Space + L/R-click input visualizer during matches. Keys glow red when pressed."
            );

            ScreenShakeEnabled = Config.Bind(
                "UI", "ScreenShakeEnabled",
                true,
                "Camera screen shake on hits/deaths/shots. Turn OFF to disable all shake (local only — opponents still see theirs)."
            );
            MapLightingEnabled = Config.Bind(
                "UI", "MapLightingEnabled",
                true,
                "The map lighting pass (SFSS). Turn OFF for a flat, full-bright scene — skips the whole per-frame lightmap render for extra FPS."
            );
            MapShadowsEnabled = Config.Bind(
                "UI", "MapShadowsEnabled",
                true,
                "Soft shadow beams cast by map lighting. Turn OFF to skip the shadow render pass (lighting stays) for extra FPS."
            );
            AnimatedCosmetics = Config.Bind(
                "UI", "AnimatedCosmetics",
                true,
                "Animated cosmetics (prismatic/chrome body colors, prism trail hue cycle, player effects, map-skin sparkle shimmer, animated face items). Turn OFF to freeze them all to a static frame instantly."
            );
            ChromaticAberrationEnabled = Config.Bind(
                "UI", "ChromaticAberrationEnabled",
                true,
                "The RGB color-fringing distortion that pulses on shots/hits/deaths. Turn OFF for crisp edges and a tiny FPS gain (local only)."
            );
            AutoRequeueOnMatchmakingBug = Config.Bind(
                "UI", "AutoRequeueOnMatchmakingBug",
                true,
                "When the vanilla 'Press Jump to Join over a dead connection' matchmaking bug is detected, automatically restart and put you back in the quickplay queue (OFF = fast return to menu instead)."
            );

            PerfOptimizations = Config.Bind(
                "Performance", "Enabled",
                true,
                "Master switch for the v1.26.8 performance pass. Turn OFF to disable ALL patches below in one click. Individual patches below also have their own toggle for granular control."
            );
            PerfStunPlayerNullGuard = Config.Bind(
                "Performance", "StunPlayerNullGuard",
                true,
                "Null-guard StunPlayer.Go so a destroyed parent Player reference doesn't NRE every frame. Pure error suppression, no visual change."
            );
            PerfDespawnOffscreenBullets = Config.Bind(
                "Performance", "DespawnOffscreenBullets",
                true,
                "Host of each projectile despawns it once it flies outside the camera viewport (0.5s throttle). Without this, missed bullets keep ticking physics + RPC handlers indefinitely. Slight bandwidth savings, no gameplay difference."
            );
            PerfSwallowHitSoundNREs = Config.Bind(
                "Performance", "SwallowHitSoundNREs",
                true,
                "Catch the NullReferenceException that fires from RayHitBulletSound.DoHitEffect when its parent is destroyed mid-frame, and destroy the now-dead instance. Reduces BepInEx log spam, no visual change."
            );
            // (v1.28.2) AutoCleanupColorGhosts bind removed — current ROUNDS'
            // ChangeColor is an empty MonoBehaviour (no Start to patch, no
            // Update tick to save); hit effects are pooled via PrefabPool now.
            PerfSwallowEdgeBounceNREs = Config.Bind(
                "Performance", "SwallowEdgeBounceNREs",
                true,
                "Catch NullReferenceExceptions from ScreenEdgeBounce.DoHit and ScreenEdgeBounce.Update when a parent bullet was destroyed mid-frame. Reduces log spam, no visual change."
            );
            // (v1.28.2) TagSpawnedObjectsForCleanup bind removed — the 3-arg
            // SpawnObject overload is void (the patch could never compile its
            // __result Postfix), and the 8-arg overload returns POOLED
            // PoolableWrappers that a RemoveAfterSeconds Destroy would corrupt.
            PerfSkipMenuUpdateInMatch = Config.Bind(
                "Performance", "SkipMenuUpdateInMatch",
                true,
                "Skip MenuControllerHandler.Update during an active match (menu controller input routing isn't needed during gameplay). Modest CPU win, no visible change."
            );
            // v1.26.9 — actual frame-time wins.
            PerfBulletHitParticleCap = Config.Bind(
                "Performance", "BulletHitParticleCap",
                true,
                "Cap bullet-hit particle explosions at 2 per frame. In a heavy firefight (BombsAway / Echo / Mayhem) a single frame can spawn 20+ explosion bursts — the cap drops GC and render cost noticeably. Missed bursts are silent: the damage already registered, you just don't see every visual."
            );
            PerfClampObjectPoolInit = Config.Bind(
                "Performance", "ClampObjectPoolInit",
                true,
                "Clamp ObjectPool initial-spawn to 4 instances while in a match (lazy growth instead of pre-allocating 30+ up-front). Reduces frame stutter when new pools are constructed mid-game."
            );
            TournamentTimezone = Config.Bind(
                "Tournaments", "Timezone",
                "Local",
                "Timezone used to display tournament times. One of: Local, UTC, PT, MT, CT, ET, UK, CET, EET, MSK, JST, AEST, or a system timezone ID."
            );

            TournamentDateFormat = Config.Bind(
                "Tournaments", "DateFormat",
                "ISO",
                "Date/time display format: ISO (2026-04-24 14:30), US (Sat 04/24 2:30 PM), or EU (Sat 24/04 14:30). All formats emit ASCII-only so any locale renders cleanly."
            );

            MutedChatNames = Config.Bind(
                "UI", "MutedChatNames",
                "",
                "Pipe-delimited list of display names whose chat messages are hidden from your in-game chat log. Use /mute name and /unmute name in chat."
            );

            DataConsent = Config.Bind(
                "Privacy", "DataConsent",
                "",
                "Consent to report match data to the leaderboard. Values: \"\" (unset — you'll be asked at launch), \"granted\", or \"denied\"."
            );

            Log.LogInfo($"{ModName} v{ModVersion} initializing (consent={(string.IsNullOrEmpty(DataConsent.Value) ? "unset" : DataConsent.Value)})...");

            // ── Game version check ──
            string gameVer = Application.version ?? "";
            if (!gameVer.StartsWith(RequiredGameVersion))
            {
                Log.LogError($"[COMPAT] ROUNDS version {gameVer} is NOT supported! This mod requires vanilla ROUNDS v{RequiredGameVersion}.");
                Log.LogError($"[COMPAT] Please switch to the 'Default Public Version' in Steam → ROUNDS → Properties → Betas.");
                Log.LogError($"[COMPAT] Mod DISABLED.");
                return;
            }
            Log.LogInfo($"[COMPAT] Game version OK: {gameVer}");

            // Patch each [HarmonyPatch] class individually so one bad patch
            // (e.g. parameter-name mismatch with vanilla, missing target method)
            // doesn't abort the rest. v1.25.10-13 silently shipped with a single
            // mis-named Prefix parameter on PlayerSkinBank.GetPlayerSkinColors —
            // PatchAll aborted there, every patch declared after it (including
            // ArtHandler.NextArt for map colors, MapManager spawn-point sort,
            // and several diag patches) never applied for 4 releases. With
            // per-class isolation, we lose just the broken class and keep
            // everything else.
            try
            {
                HarmonyInstance = new Harmony(ModId);
                int applied = 0, failed = 0;
                foreach (var type in Assembly.GetExecutingAssembly().GetTypes())
                {
                    var attrs = type.GetCustomAttributes(typeof(HarmonyPatch), true);
                    if (attrs == null || attrs.Length == 0) continue;
                    try
                    {
                        HarmonyInstance.CreateClassProcessor(type).Patch();
                        applied++;
                    }
                    catch (Exception ex)
                    {
                        failed++;
                        Log.LogError($"[HARMONY] Failed to patch {type.Name}: {ex.Message}");
                    }
                }
                Log.LogInfo($"[HARMONY] Patches applied: {applied} ok, {failed} failed");
            }
            catch (Exception ex)
            {
                Log.LogWarning($"Harmony patching bootstrap failed (mod will work without it): {ex.Message}");
            }

            // Create persistent object with maximum protection
            if (!spawned)
            {
                var go = new GameObject("CompetitiveRounds_Persistent");
                go.hideFlags = HideFlags.HideAndDontSave;
                UnityEngine.Object.DontDestroyOnLoad(go);
                Instance = go.AddComponent<CompetitiveRoundsBehaviour>();
                // Sibling component that receives Photon IInRoomCallbacks — used by the cosmetic
                // trail system to re-attach opponents' trails when their cr_trail_* props arrive
                // after OnMatchStart has already iterated.
                go.AddComponent<TrailPhotonCallbacks>();
                // Local-only nametag renderers. Both poll scene TMP labels every 0.5s. Font
                // renderer is attached FIRST so its coroutine runs before the glow renderer
                // each cycle — glow clones its material from the label's current sharedMaterial,
                // which changes after a font swap, so the glow rebuild needs to see the swapped
                // material to reapply correctly. Order here is load-bearing.
                go.AddComponent<NametagFontRenderer>();
                go.AddComponent<NametagGlowRenderer>();
                // 2v2 diagnostics — Photon callback target. Logs every
                // PlayerEntered / PlayerLeft / Disconnect / LeftRoom / etc.
                // when in (or recently in) a cr_ff room.
                go.AddComponent<Cr2v2DiagCallbacks>();
                spawned = true;
                Log.LogInfo("Created persistent GameObject with DontDestroyOnLoad");
            }

            Log.LogInfo($"{ModName} v{ModVersion} loaded!");

            // Create a separate tiny object for queue auto-join
            var queueObj = new GameObject("CR_QueueJoiner");
            queueObj.hideFlags = HideFlags.HideAndDontSave;
            UnityEngine.Object.DontDestroyOnLoad(queueObj);
            queueObj.AddComponent<QueueRoomJoiner>();

            // Taskbar flash for alt-tabbed match found notifications
            var flashObj = new GameObject("CR_TaskbarFlash");
            flashObj.hideFlags = HideFlags.HideAndDontSave;
            UnityEngine.Object.DontDestroyOnLoad(flashObj);
            flashObj.AddComponent<TaskbarFlash>();
        }
    }

    /// <summary>
    /// Tiny MonoBehaviour solely for ranked queue auto-join.
    /// Uses ROUNDS' own NetworkConnectionHandler for region connection and room joining.
    /// Requires Krafs.Publicizer for direct access to NCH private members.
    /// </summary>
    public class QueueRoomJoiner : MonoBehaviour
    {
        private enum JoinState { Idle, LeavingRoom, Connecting, WaitingForRoom }
        private JoinState state = JoinState.Idle;
        private float stateTimer = 0f;
        private bool joinInitiated = false;
        private string targetRoom;
        private string targetRegion;
        // One automatic full-sequence retry before giving up (#26 — "matched but
        // failed to auto join"). A slow Photon region connect or a transient
        // disconnect race eats the first 30s window; a second attempt from a
        // clean state recovers it without the player touching anything.
        private int joinAttempts = 0;

        private void Awake()
        {
            Plugin.Log.LogInfo("[QUEUE-JOINER] Awake, DontDestroyOnLoad set");
        }

        private void Update()
        {
            string pendingRoom = Plugin.PendingRankedRoom;
            if (string.IsNullOrEmpty(pendingRoom))
            {
                joinInitiated = false;
                state = JoinState.Idle;
                stateTimer = 0f;
                joinAttempts = 0;
                return;
            }

            stateTimer += Time.deltaTime;

            // Safety timeout — 30s to account for disconnect + NCH connection sequence.
            // Lexia hit this on a slow Photon connect (v1.26.1 logs): pending room set
            // mid-queue from a prior session, timeout fired, but the reset only cleared
            // the room — leaving GameStateWatcher.LeavingForRanked=true (set when we
            // initiated the leave on line where state became LeavingRoom) and stale
            // targetRoom / targetRegion behind. Subsequent matches in the same session
            // could then suppress legitimate DC-win counting. Clear everything.
            if (state != JoinState.Idle && stateTimer > 30f)
            {
                joinAttempts++;
                if (joinAttempts <= 1)
                {
                    // First timeout: retry the whole sequence from a clean slate.
                    // The pending room is still set, so the Idle branch below
                    // re-initiates leave/connect/join on the next frame.
                    Plugin.Log.LogWarning($"[QUEUE-JOINER] Join attempt {joinAttempts} timed out (state={state}, target='{targetRoom}') — retrying once");
                    joinInitiated = false;
                    state = JoinState.Idle;
                    stateTimer = 0f;
                    try { GameStateWatcher.LeavingForRanked = false; } catch { }
                    CompetitiveUI.ShowNotification("Slow connection — retrying ranked room join...", new Color(1f, 0.8f, 0.3f), 6f);
                    return;
                }
                Plugin.Log.LogWarning($"[QUEUE-JOINER] Timed out waiting for room join after {joinAttempts} attempts (state={state}, target='{targetRoom}'), resetting all queue state");
                // 1v2: a failed join must dissolve the lock server-side, or the
                // three 'ready_join' rows + the 'active' series persist as a
                // husk that re-feeds this dead room on every future Join click.
                // OvtLeaveQueue also resets the local lock state (status,
                // lineup, pending slot) that would otherwise leave the tab
                // showing "Match found! Joining…" over a live Join button.
                bool wasOvt = (targetRoom ?? "").StartsWith("ovt_") || (pendingRoom ?? "").StartsWith("ovt_");
                Plugin.ClearPendingRoom();
                joinInitiated = false;
                state = JoinState.Idle;
                stateTimer = 0f;
                joinAttempts = 0;
                targetRoom = null;
                targetRegion = null;
                // We may have set this when state went to LeavingRoom — clear so a
                // future legitimate leave doesn't mistakenly cancel match-result counting.
                try { GameStateWatcher.LeavingForRanked = false; } catch { }
                if (wasOvt)
                {
                    try { ApiClient.OvtLeaveQueue(); } catch { }
                    CompetitiveUI.ShowNotification("Failed to join the 1v2 room — lobby dissolved, please requeue", new Color(1f, 0.4f, 0.4f), 8f);
                }
                else
                {
                    CompetitiveUI.ShowNotification("Failed to join ranked room — please requeue", new Color(1f, 0.4f, 0.4f), 8f);
                }
                return;
            }

            switch (state)
            {
                case JoinState.Idle:
                    if (joinInitiated) return;

                    // If already in the correct room, done
                    if (PhotonNetwork.InRoom)
                    {
                        string currentRoom = PhotonNetwork.CurrentRoom?.Name ?? "";
                        if (currentRoom == pendingRoom)
                        {
                            OnJoinedRankedRoom(currentRoom);
                            return;
                        }
                        // In a different room — need to leave first
                        targetRoom = pendingRoom;
                        targetRegion = Plugin.PendingRankedRegion;
                        joinInitiated = true;
                        GameStateWatcher.LeavingForRanked = true;
                        // July 22 item 2: flag the deliberate leave so observers'
                        // leaver banner says "left for a ranked match" instead of
                        // implying a rage-quit. Best-effort — prop may not
                        // replicate before the leave lands on slow links.
                        try
                        {
                            var lvProps = new ExitGames.Client.Photon.Hashtable();
                            lvProps["cr_lv_rk"] = "1";
                            PhotonNetwork.LocalPlayer?.SetCustomProperties(lvProps);
                        }
                        catch { }
                        PhotonNetwork.LeaveRoom();
                        Plugin.Log.LogInfo("[QUEUE-JOINER] Leaving current room before ranked join...");
                        state = JoinState.LeavingRoom;
                        stateTimer = 0f;
                        return;
                    }

                    // Not in a room — go straight to connecting
                    targetRoom = pendingRoom;
                    targetRegion = Plugin.PendingRankedRegion;
                    StartNCHConnect();
                    break;

                case JoinState.LeavingRoom:
                    // Wait for Photon to fully leave the room
                    if (!PhotonNetwork.InRoom)
                    {
                        Plugin.Log.LogInfo("[QUEUE-JOINER] Left room, starting NCH connect...");
                        // Small delay to let Photon settle
                        StartNCHConnect();
                    }
                    break;

                case JoinState.Connecting:
                    // NCH coroutine is running, wait for room join
                    if (PhotonNetwork.InRoom)
                    {
                        string cur = PhotonNetwork.CurrentRoom?.Name ?? "";
                        if (cur == targetRoom)
                        {
                            OnJoinedRankedRoom(cur);
                            return;
                        }
                    }
                    break;

                case JoinState.WaitingForRoom:
                    if (PhotonNetwork.InRoom)
                    {
                        string cur = PhotonNetwork.CurrentRoom?.Name ?? "";
                        if (cur == targetRoom)
                        {
                            OnJoinedRankedRoom(cur);
                            return;
                        }
                    }
                    break;
            }
        }

        private void StartNCHConnect()
        {
            joinInitiated = true;
            var nch = NetworkConnectionHandler.instance;

            if (nch == null)
            {
                Plugin.Log.LogError("[QUEUE-JOINER] NetworkConnectionHandler.instance is null!");
                return;
            }

            try
            {
                // Disconnect fully if still connected (e.g. on master server but not in room)
                if (PhotonNetwork.IsConnected)
                {
                    PhotonNetwork.Disconnect();
                    Plugin.Log.LogInfo("[QUEUE-JOINER] Disconnecting from Photon...");
                }

                // Close menus
                try { CharacterCreatorHandler.instance?.CloseMenus(); } catch { }
                try { MainMenuHandler.instance?.Close(); } catch { }

                // Set target region
                if (!string.IsNullOrEmpty(targetRegion))
                {
                    RegionSelector.region = targetRegion;
                    Plugin.Log.LogInfo($"[QUEUE-JOINER] Set RegionSelector.region = {targetRegion}");
                }

                // Force region (via Publicizer)
                nch.m_ForceRegion = true;
                Plugin.Log.LogInfo("[QUEUE-JOINER] Set m_ForceRegion = true");
                // July 21 review fix: clear any stale vanilla search context — the
                // mod owns the connection now. Without this, a quickplay search
                // abandoned for a ranked match leaves m_searchingType=Quickmatch,
                // and a later dead-state recovery would auto-requeue the player
                // into the VANILLA queue instead of returning to menu. Vanilla-
                // safe: readers treat None like "no special search".
                try { nch.m_searchingType = (NetworkConnectionHandler.SearchingType)0; } catch { }

                // Loading screen
                try { TimeHandler.instance.gameStartTime = 1f; } catch { }
                try { LoadingScreen.instance?.StartLoading(); } catch { }

                // NCH handles: disconnect wait → ConnectToRegion → wait for master → execute callback
                string capturedRoom = targetRoom;
                nch.StartCoroutine(nch.DoActionWhenConnected(() =>
                {
                    try
                    {
                        Plugin.Log.LogInfo($"[QUEUE-JOINER] Connected! JoinOrCreate: {capturedRoom}");
                        // 2v2 rooms have a `team_` prefix (set by /team/queue/ready
                        // server-side). Bump MaxPlayers to 4 + flag the room as
                        // friendly-fire-on so a Harmony patch can read it during
                        // ProjectileCollision and let teammate shots through.
                        bool is2v2 = capturedRoom != null && capturedRoom.StartsWith("team_");
                        // 1v2: ovt_ rooms hold 3. Review CRITICAL — without this the
                        // room was created MaxPlayers=2 (the 1v1 default) and the
                        // third player could never join, so 1v2 could never start.
                        bool is1v2 = capturedRoom != null && capturedRoom.StartsWith("ovt_");
                        var roomProps = new ExitGames.Client.Photon.Hashtable
                        {
                            { "C2", capturedRoom }
                        };
                        if (is2v2) roomProps["cr_ff"] = true;
                        // July 22 item 3: solo-extra-pick flag rides the ROOM
                        // props (design doc: room-prop carrier) — all 3 clients
                        // got it in the lock payload, so whichever creates the
                        // room stamps it and late joiners read one truth.
                        if (is1v2 && ApiClient.OvtSoloExtraPick) roomProps["cr_ovt_xp"] = true;
                        var roomOptions = new Photon.Realtime.RoomOptions
                        {
                            MaxPlayers = (byte)(is2v2 ? 4 : (is1v2 ? 3 : 2)),
                            IsOpen = true,
                            IsVisible = true,
                            CustomRoomProperties = roomProps,
                            CustomRoomPropertiesForLobby = new string[] { "C2" }
                        };
                        var lobby = new Photon.Realtime.TypedLobby("RoomCodeLobby", Photon.Realtime.LobbyType.SqlLobby);
                        PhotonNetwork.JoinOrCreateRoom(capturedRoom, roomOptions, lobby);
                    }
                    catch (Exception ex)
                    {
                        Plugin.Log.LogError($"[QUEUE-JOINER] JoinOrCreate failed: {ex.Message}");
                    }
                }));

                Plugin.Log.LogInfo($"[QUEUE-JOINER] Started NCH connection sequence for room: {targetRoom}");
                state = JoinState.Connecting;
                stateTimer = 0f;
            }
            catch (Exception ex)
            {
                Plugin.Log.LogError($"[QUEUE-JOINER] StartNCHConnect failed: {ex.Message}");
                joinInitiated = false;
            }
        }

        private void OnJoinedRankedRoom(string roomName)
        {
            Plugin.Log.LogInfo($"[QUEUE] In ranked room: {roomName}!");
            Plugin.ClearPendingRoom();
            joinInitiated = false;
            state = JoinState.Idle;
            stateTimer = 0f;
            joinAttempts = 0;

            // Clear force region flag so NCH works normally for vanilla play afterward
            try
            {
                var nch = NetworkConnectionHandler.instance;
                if (nch != null)
                    nch.m_ForceRegion = false;
            }
            catch { }

            CompetitiveUI.ShowNotification("In ranked match room!", Color.green, 5f);
            CompetitiveRoundsBehaviour.HideMainMenu();

            string steamId = GameStateWatcher.LocalSteamId;
            if (!string.IsNullOrEmpty(steamId) && steamId != "unknown")
                ApiClient.LeaveQueue(steamId);

            // The 1v2 queue phase ends the moment the room join lands — reset
            // the status so the tab doesn't keep saying "Match found! Joining…"
            // after the series (the lock lineup stays cached for the HUD).
            if (roomName != null && roomName.StartsWith("ovt_"))
                ApiClient.OvtQueueStatus = "";

            // 2v2 / 1v2: bypass ROUNDS' character-select press-any-key gate.
            // Vanilla PlayerAssigner.Update polls input devices and only fires
            // CreatePlayer when the user mashes a key — but the character-select
            // widget container only has 2 child slots, so players assigned to
            // slots 2/3 don't see a prompt and never trigger their local
            // CreatePlayer. Result: 2 of N spawn correctly, the rest sit on the
            // menu while the room sits empty from their perspective. Auto-fire
            // CreatePlayer ourselves (which routes through the CreatePlayer
            // override and uses the server-issued slot).
            if (Plugin.Pending2v2Slot >= 0 || Plugin.PendingOvtSlot >= 0)
                StartCoroutine(Auto2v2SpawnCoroutine());
        }

        private System.Collections.IEnumerator Auto2v2SpawnCoroutine()
        {
            // Wait briefly for scene + PlayerAssigner to spin up. The scene
            // reload to "Main" happens around the same time as the Photon room
            // join, so PlayerAssigner.instance is usually null for ~1 second.
            float deadline = Time.realtimeSinceStartup + 12f;
            int tickLogCount = 0;
            while (Time.realtimeSinceStartup < deadline)
            {
                if (Plugin.Pending2v2Slot < 0 && Plugin.PendingOvtSlot < 0)
                {
                    Plugin.Log.LogInfo("[2v2] Auto-spawn aborted — pending slot cleared mid-wait");
                    yield break;
                }
                if (!PhotonNetwork.InRoom)
                {
                    Plugin.Log.LogInfo("[2v2] Auto-spawn aborted — not in Photon room mid-wait");
                    yield break;
                }
                var pa = PlayerAssigner.instance;
                if (pa != null && !pa.hasCreatedLocalPlayer)
                {
                    InputDevice device = null;
                    try
                    {
                        if (InputManager.ActiveDevices != null && InputManager.ActiveDevices.Count > 0)
                            device = InputManager.ActiveDevices[0];
                    }
                    catch { }
                    Plugin.Log.LogInfo($"[2v2] Auto-spawning local player (slot={Diag2v2.PendingSlot()}, device={(device != null ? "keyboard" : "null")})");
                    bool ok = false;
                    try { pa.CreatePlayer(device, false); ok = true; }
                    catch (Exception ex) { Plugin.Log.LogError($"[2v2] Auto-spawn CreatePlayer failed: {ex.Message}"); }
                    if (ok)
                    {
                        // Tell server we spawned, so it can detect when fewer than
                        // 4 of 4 confirm within the assembly deadline and cancel.
                        try
                        {
                            string sid = MatchTracker.LocalSteamId;
                            string seriesId = ApiClient.ActiveTeamSeriesId;
                            if (!string.IsNullOrEmpty(sid) && !string.IsNullOrEmpty(seriesId))
                                ApiClient.SendTeamSpawnConfirm(seriesId, sid);
                        }
                        catch (Exception ex) { Plugin.Log.LogWarning($"[2v2] spawn-confirm send error: {ex.Message}"); }
                        yield break;
                    }
                }
                else if (tickLogCount < 6)
                {
                    string reason = pa == null ? "PlayerAssigner.instance == null"
                                  : pa.hasCreatedLocalPlayer ? "local player already exists"
                                  : "?";
                    Plugin.Log.LogInfo($"[2v2] Auto-spawn waiting: {reason} (tick {tickLogCount})");
                    tickLogCount++;
                }
                yield return new WaitForSeconds(0.5f);
            }
            if (PlayerAssigner.instance == null || !PlayerAssigner.instance.hasCreatedLocalPlayer)
                Plugin.Log.LogWarning("[2v2] Auto-spawn timed out — PlayerAssigner never initialized or local player never spawned");
        }
    }

    public class CompetitiveRoundsBehaviour : MonoBehaviour
    {
        private bool initialized = false;
        private float startupTimer = 0f;
        private bool startupComplete = false;

        // Ranked queue room joining — now handled by Plugin.Update()
        // (Plugin's MonoBehaviour survives scene changes via BepInEx)

        private void Awake()
        {
            hideFlags = HideFlags.HideAndDontSave;
            gameObject.hideFlags = HideFlags.HideAndDontSave;
            DontDestroyOnLoad(gameObject);
            Plugin.Log.LogInfo("[PERSIST] Behaviour Awake, DontDestroyOnLoad set");
        }

        private void Update()
        {
            if (Plugin.modDisabled) return;

            // Menu injection runs independently
            try { MainMenuInjector.TryInject(); } catch { }

            // Delayed initialization (wait for game to be fully loaded)
            if (!startupComplete)
            {
                startupTimer += Time.deltaTime;
                if (startupTimer >= 3f)
                {
                    startupComplete = true;
                    DoInitialize();
                }
                return;
            }

            if (!initialized) return;

            // Canvas UI tick (notifications, match status, session refresh)
            try { CompetitiveUI.Tick(); } catch { }

            // F5 input (no log spam — just toggle)
            if (Input.GetKeyDown(KeyCode.F5))
            {
                CompetitiveUI.ToggleOverlay();
            }

            // Per-frame FPS sampling (active only while a match is being tracked).
            try { GameStateWatcher.TickFrame(); } catch { }

            // Poll game state
            try
            {
                GameStateWatcher.Poll();
            }
            catch (Exception ex)
            {
                Plugin.Log.LogError($"Poll error: {ex.Message}");
            }

            // Poll ranked queue if searching
            if (ApiClient.IsQueuePolling)
            {
                try
                {
                    ApiClient.UpdateQueuePoll(GameStateWatcher.LocalSteamId);
                }
                catch { }
            }

            // Poll 2v2 queue if searching
            if (ApiClient.IsTeamQueuePolling)
            {
                try { ApiClient.UpdateTeamQueuePoll(GameStateWatcher.LocalSteamId); }
                catch { }
            }

            // Poll 1v2 queue if searching. Must run here (not just from the
            // F5 tab ticker) — a player who queues and closes the menu would
            // otherwise never receive ready_join, and their stale row would
            // strand the other two at 2/3 until the server prunes it.
            if (ApiClient.IsOvtQueuePolling)
            {
                try { ApiClient.UpdateOvtQueuePoll(false); }
                catch { }
            }

            // Poll queue count when competitive page is open (every 10s)
            if (NativeUI.IsOpen)
            {
                try { ApiClient.UpdateQueueCount(); }
                catch { }
                try { ApiClient.UpdateTeamQueueCount(); }
                catch { }
                // Auto-refresh Live Ranked Games while the Leaderboard tab is open. Cheaply
                // gated by the 10s timer in NativeUI.MaybeRefreshLiveSeries so we're not
                // hammering /series/active every frame.
                try { NativeUI.MaybeRefreshLiveSeries(); }
                catch { }
            }
        }

        private void DoInitialize()
        {
            Plugin.Log.LogInfo("[PERSIST] Delayed initialization starting...");

            // ── Other mods check (Chainloader is complete by now) ──
            try
            {
                var plugins = Chainloader.PluginInfos;
                if (plugins != null && plugins.Count > 1)
                {
                    var otherMods = new List<string>();
                    foreach (var kvp in plugins)
                    {
                        if (kvp.Key != Plugin.ModId)
                            otherMods.Add($"{kvp.Value.Metadata.Name} ({kvp.Key})");
                    }
                    if (otherMods.Count > 0)
                    {
                        Plugin.Log.LogError($"[COMPAT] {otherMods.Count} other mod(s) detected! This mod requires vanilla ROUNDS with no other plugins.");
                        foreach (var m in otherMods)
                            Plugin.Log.LogError($"[COMPAT]   - {m}");
                        Plugin.Log.LogError("[COMPAT] Mod DISABLED to ensure competitive integrity.");
                        Plugin.modDisabled = true;
                        return;
                    }
                }
                Plugin.Log.LogInfo("[COMPAT] No other mods detected — OK");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[COMPAT] Could not check other mods: {ex.Message}");
            }

            ApiClient.Initialize(Plugin.ApiBaseUrl.Value);
            GameStateWatcher.Initialize();
            CardImageLoader.Initialize();
            try { CustomCosmetics.Initialize(); } catch (Exception ex) { Plugin.Log.LogWarning($"[COSMETIC] init failed: {ex.Message}"); }
            CompetitiveUI.CacheRaycasters(); // No-op but kept for compat
            initialized = true;

            // Initialize UI type cache for native menu integration
            try { UIFactory.InitTypes(); UIFactory.InitFont(); }
            catch (Exception ex) { Plugin.Log.LogWarning($"[UI] Type init deferred: {ex.Message}"); }

            // Fetch initial data so overlay has content before first F5.
            // Steamworks resolution is racy — on first launch, GetSteamID()
            // routinely returns 0 ("unknown") for the first second or so.
            // Without a retry path, ToggleRanked + FetchPlayerStats etc.
            // never fire and the player's server-side ranked_enabled stays
            // at its default false. Fix the new-install "casual instead of
            // ranked" bug by spawning a coroutine that polls until Steam
            // resolves, then runs the same one-shot init.
            Plugin.Instance.StartCoroutine(InitWhenSteamReady());

            // Wire the chat pipe so incoming messages reach the UI log.
            ChatClient.OnMessage = NativeUI.OnChatMessage;

            // If the user already granted consent in a previous session, open the chat WS now.
            // Fresh installs stay offline until the consent modal gets a Yes.
            if (Plugin.DataConsentGranted)
                ChatClient.Connect();

            // One-shot: log every TMP_FontAsset currently loaded so we can see which fonts
            // are actually available for in-game use (OS-font path is broken, see comments
            // in NametagFontRenderer). Useful for choosing target fonts to map typeface SKUs
            // onto in a follow-up pass.
            try { NametagFontRenderer.LogAvailableTmpFonts(); } catch { }

            Plugin.Log.LogInfo("[PERSIST] All systems active! Press F5 for overlay.");
        }

        // Polls until LocalSteamId resolves (Steamworks isn't always ready by
        // the time DoInitialize runs on first launch), then fires the same
        // one-shot init the inline guard used to do — ToggleRanked,
        // FetchPlayerStats, FetchMatchHistory, FetchBlockedPlayers,
        // CheckAdminStatus. Without this, a brand-new install whose
        // Steamworks resolve loses the race never calls ToggleRanked, leaves
        // their server-side ranked_enabled at false, and is matched as
        // casual by every opponent until they restart the game.
        private static bool _initSteamRanFired = false;
        private System.Collections.IEnumerator InitWhenSteamReady()
        {
            float deadline = Time.unscaledTime + 30f;  // give up after 30s; logs warn
            int tries = 0;
            while (!_initSteamRanFired && Time.unscaledTime < deadline)
            {
                tries++;
                string sid = GameStateWatcher.LocalSteamId;
                if (!string.IsNullOrEmpty(sid) && sid != "unknown")
                {
                    _initSteamRanFired = true;
                    Plugin.Log.LogInfo($"[INIT] Steam resolved on try {tries} (sid={sid}); firing one-shot init");
                    try { ApiClient.ToggleRanked(sid, Plugin.RankedEnabled.Value); } catch (Exception ex) { Plugin.Log.LogWarning($"[INIT] ToggleRanked failed: {ex.Message}"); }
                    try { ApiClient.FetchPlayerStats(sid); } catch { }
                    try { ApiClient.FetchMatchHistory(sid); } catch { }
                    try { ApiClient.FetchBlockedPlayers(sid); } catch { }
                    try { ApiClient.CheckAdminStatus(sid); } catch { }
                    // Warm the shop cache so the character editor knows owned
                    // cosmetics even if the F5 page was never opened this session.
                    try { ApiClient.FetchShopItems(sid); } catch { }
                    yield break;
                }
                yield return new WaitForSeconds(0.5f);
            }
            if (!_initSteamRanFired)
                Plugin.Log.LogWarning($"[INIT] Steam ID never resolved after {tries} tries / 30s. Server-side ranked_enabled may be stale until next launch.");
        }

        private void OnGUI()
        {
            if (!initialized || Plugin.modDisabled) return;
            CompetitiveUI.DrawUI();
        }

        /// <summary>
        /// Hides the main menu UI after auto-joining a ranked room.
        /// Our Photon connect bypasses ROUNDS' normal scene transition,
        /// so the main menu stays rendered over the game.
        /// </summary>
        internal static void HideMainMenu()
        {
            try
            {
                // Log loaded scenes for debugging
                for (int i = 0; i < UnityEngine.SceneManagement.SceneManager.sceneCount; i++)
                {
                    var scene = UnityEngine.SceneManagement.SceneManager.GetSceneAt(i);
                    Plugin.Log.LogInfo($"[QUEUE] Loaded scene: {scene.name} (index {scene.buildIndex})");
                }

                // Disable MainMenuHandler
                var mainMenuHandler = UnityEngine.Object.FindObjectOfType<MainMenuHandler>();
                if (mainMenuHandler != null)
                {
                    mainMenuHandler.gameObject.SetActive(false);
                    Plugin.Log.LogInfo("[QUEUE] Disabled MainMenuHandler");
                }

                // Disable all ListMenu objects (menu buttons)
                var listMenus = UnityEngine.Object.FindObjectsOfType<ListMenu>();
                foreach (var menu in listMenus)
                {
                    menu.gameObject.SetActive(false);
                }
                if (listMenus.Length > 0)
                    Plugin.Log.LogInfo($"[QUEUE] Disabled {listMenus.Length} ListMenu objects");

                // Disable CharacterSelectionInstance if present
                var charSelect = UnityEngine.Object.FindObjectOfType<CharacterSelectionInstance>();
                if (charSelect != null)
                {
                    charSelect.transform.root.gameObject.SetActive(false);
                    Plugin.Log.LogInfo("[QUEUE] Disabled character selection");
                }
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[QUEUE] HideMainMenu error: {ex.Message}");
            }
        }

        private void OnDestroy()
        {
            Plugin.Log.LogWarning("[PERSIST] Destroyed! Attempting respawn...");
            MainMenuInjector.Reset();

            try
            {
                var go = new GameObject("CompetitiveRounds_Respawn");
                go.hideFlags = HideFlags.HideAndDontSave;
                UnityEngine.Object.DontDestroyOnLoad(go);
                var newInstance = go.AddComponent<CompetitiveRoundsBehaviour>();
                Plugin.Instance = newInstance;
                Plugin.Log.LogInfo("[PERSIST] Respawned with DontDestroyOnLoad!");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogError($"[PERSIST] Respawn failed: {ex.Message}");
            }
        }

    }

    // ── Harmony Patches ────────────────────────────────────────

    // NOTE: LobbyRedirectPatch was added in v1.18.3 for Thunderstore compliance.
    // It redirects vanilla quickmatch to a mod-only Photon lobby ("QuickmatchCompLobby")
    // so mod users never match with vanilla players.
    // Currently DISABLED for direct distribution — Landfall permission pending.
    // To re-enable: uncomment this patch. No other changes needed.
    // See HANDOFF.md "Landfall / Thunderstore Situation" for full context.
    //
    // [HarmonyPatch(typeof(NetworkConnectionHandler), "Awake")]
    // class LobbyRedirectPatch
    // {
    //     private static readonly Photon.Realtime.TypedLobby LOBBY_QUICKMATCH_COMP =
    //         new Photon.Realtime.TypedLobby("QuickmatchCompLobby", Photon.Realtime.LobbyType.SqlLobby);
    //
    //     static void Postfix()
    //     {
    //         NetworkConnectionHandler.LOBBY_QUICKMATCH = LOBBY_QUICKMATCH_COMP;
    //         Plugin.Log.LogInfo("[HARMONY] Quickmatch lobby redirected to CompLobby (mod-only matchmaking)");
    //     }
    // }

    [HarmonyPatch(typeof(GM_ArmsRace), "Awake")]
    class GMArmsRaceAwakePatch
    {
        static void Postfix(GM_ArmsRace __instance)
        {
            Plugin.Log.LogInfo("[HARMONY] GM_ArmsRace.Awake fired! Harmony is WORKING!");
            CardRarityLookup.ScanAll();
            if (CardRarityLookup.Count == 0)
                Plugin.Log.LogInfo("[HARMONY] No cards found yet — will retry on match start");
        }
    }

    /// <summary>
    /// Force GM_ArmsRace.playersNeededToStart = 4 in 2v2 rooms. Vanilla OnEnable
    /// hardcodes it to 2 — the rest of the engine handles 4 players fine (there's
    /// even a debug keybind on '4' that toggles this exact field), but our normal
    /// game-start would fire as soon as 2 players joined, leaving the 3rd + 4th
    /// dangling without GameObjects → RPCO_RequestSyncUp targets a viewID that
    /// doesn't exist locally → MapManager.UnloadAfterSeconds throws on the bad
    /// scene state → Photon network restart → all 4 drop. Setting it to 4 makes
    /// the engine wait for all 4 before StartGame fires, which is what 4-player
    /// mode in vanilla local play does.
    ///
    /// Detection: the Photon room's `cr_ff` custom property (set by QueueJoiner
    /// when the room name starts with `team_`) doubles as a 2v2-mode signal.
    /// </summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "OnEnable")]
    class GMArmsRaceOnEnable_4Player_Patch
    {
        static void Postfix(GM_ArmsRace __instance)
        {
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.CurrentRoom == null) return;
                var props = PhotonNetwork.CurrentRoom.CustomProperties;
                string rn = PhotonNetwork.CurrentRoom.Name ?? "";
                // 1v2 (ovt_) rooms need 3; 2v2 (cr_ff) rooms need 4. Same engine
                // path — the CharacterSelectionMenu slot-overflow guard below
                // already tolerates the extra players generically.
                bool isOvt = rn.StartsWith("ovt_");
                bool isFf = props != null && props.ContainsKey("cr_ff");
                if (!isOvt && !isFf) return;
                int need = isOvt ? 3 : 4;
                __instance.playersNeededToStart = need;
                if (PlayerAssigner.instance != null)
                    PlayerAssigner.instance.maxPlayers = need;
                Plugin.Log.LogInfo($"[MODE] Forced playersNeededToStart={need} ({(isOvt ? "ovt_ 1v2" : "cr_ff 2v2")} room)");
            }
            catch (Exception ex) { Plugin.Log.LogError($"[2v2] OnEnable patch error: {ex.Message}"); }
        }
    }

    /// <summary>
    /// Don't crash on the 3rd / 4th player joining a 2v2 room. Vanilla
    /// CharacterSelectionMenu.PlayerJoined does:
    ///   transform.GetChild(0).GetChild(players.Count - 1).GetComponent&lt;…&gt;().StartPicking(p)
    /// The container at GetChild(0) only has 2 children (one per 1v1 slot), so
    /// when players.Count hits 3, GetChild(2) throws "Transform child out of
    /// bounds". The exception aborts PlayerJoined's multicast invocation,
    /// meaning GM_ArmsRace.PlayerJoined never fires for players 3 and 4 →
    /// playersNeededToStart=4 never gets reached → StartGame never fires.
    /// Players 3 and 4 don't get the face-customization step (they spawn
    /// with their last-saved face) but the game continues normally.
    /// </summary>
    [HarmonyPatch(typeof(CharacterSelectionMenu), "PlayerJoined")]
    class CharacterSelectionMenu_PlayerJoined_2v2_Patch
    {
        static bool Prefix(CharacterSelectionMenu __instance)
        {
            try
            {
                if (__instance == null || __instance.transform.childCount == 0) return true;
                int slot = (PlayerManager.instance != null && PlayerManager.instance.players != null)
                    ? PlayerManager.instance.players.Count - 1 : -1;
                var container = __instance.transform.GetChild(0);
                if (slot < 0 || slot >= container.childCount)
                {
                    Plugin.Log.LogInfo($"[2v2] CharacterSelectionMenu skipped (slot={slot} >= children={container.childCount})");
                    return false;
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[2v2] CharacterSelectionMenu prefix error: {ex.Message}"); }
            return true;
        }
    }

    // NetworkConnectionHandler_OnPlayerLeftRoom_2v2_Patch removed in v1.25.9.
    // Originally added in v1.25.5 to suppress vanilla's cascade-DC during the
    // 2v2 spawn race (where 2 of 4 bailed mid-spawn and dragged the others).
    // Spawn race is fixed by v1.25.4–v1.25.8 (PlayerAssigner slot collision,
    // late-joiner GM_ArmsRace activation, character-select OOB, auto-spawn).
    // Now when a player leaves mid-game we want vanilla's DoDisconnect →
    // NetworkRestart → GoToMenu cascade to fire so the remaining 3 don't sit
    // forever — matches user-reported expectation that a quit ends the match
    // for everyone.

    /// <summary>
    /// Skip-and-replace PlayerAssigner.CreatePlayer in 2v2 rooms. Vanilla logic
    /// hardcodes m_playerId = 0 for master / 1 for everyone else, so all 3 non-
    /// master clients collide on slot 1 in PlayerManager.players (RegisterPlayer
    /// does `players[forceIndex] = player`, overwriting). This patch uses the
    /// server-issued slot 0-3 (Plugin.Pending2v2Slot, set when /queue/poll
    /// returns ready_join) so each of the 4 players lands at a unique slot and
    /// the team mapping (slot/2 = team 0 or 1) matches the balancer's output.
    ///
    /// Critical ordering: we set VAR_PLAYERID + VAR_TEAMID custom properties on
    /// LocalPlayer BEFORE PhotonNetwork.Instantiate, so the message order on
    /// remote clients is "props update → instantiate" — when their Player.Start
    /// runs ReadPlayerID/ReadTeamID, the right values are already on Owner.
    /// </summary>
    [HarmonyPatch(typeof(PlayerAssigner), "CreatePlayer")]
    class PlayerAssigner_CreatePlayer_2v2_Patch
    {
        // Throttle for the spawn-guard warning (LateUpdate can call CreatePlayer
        // every frame while an input device is waiting, so the bad-state window
        // would otherwise spam the log).
        static float _lastSpawnGuardLog = -999f;
        // First moment of the CURRENT continuous suppression episode (-1 = not
        // suppressing). Drives the #37 watchdog below.
        static float _suppressEpisodeStart = -1f;

        static bool Prefix(PlayerAssigner __instance, InputDevice inputDevice, bool isAI)
        {
            // ── Spawn guard (v1.28): "no space to ready up" freeze ──────────────
            // Vanilla CreatePlayer does PhotonNetwork.Instantiate(...).GetComponent
            // <CharacterData>(). When the client is NOT in a room (e.g. mid region-
            // reconnect / quickplay churn — Photon state ConnectingToMasterServer),
            // Instantiate returns NULL and the GetComponent NREs, so the local
            // player never spawns → no ready ring → the player is stuck unable to
            // ready up (Sid's report, 2026-06-02 casual quickplay logs). Skip the
            // call entirely until we're actually in a room (or OfflineMode, where
            // Instantiate works fine). PlayerAssigner.LateUpdate keeps polling the
            // waiting input device, so vanilla CreatePlayer runs cleanly and spawns
            // the player as soon as the connection settles. Applies to ALL modes
            // (1v1 casual/ranked + 2v2) since the race is in vanilla networking.
            if (!PhotonNetwork.OfflineMode &&
                (!PhotonNetwork.InRoom || PhotonNetwork.CurrentRoom == null))
            {
                try
                {
                    if (Time.unscaledTime - _lastSpawnGuardLog > 2f)
                    {
                        _lastSpawnGuardLog = Time.unscaledTime;
                        Plugin.Log.LogWarning(
                            "[SPAWN-GUARD] CreatePlayer suppressed — client not in a room " +
                            $"(state={PhotonNetwork.NetworkClientState}). Will retry when connected.");
                    }
                    // ── #37 watchdog: the guard can be CORRECT forever ──────────
                    // Bug #37's log: casual quickplay left the room, a region-ping
                    // sweep + Network restart followed, and a stale game scene kept
                    // polling CreatePlayer with no room for the rest of the session
                    // — guard suppressing each time, "Press jump to join" dead. The
                    // suppressed state can't self-heal without a room, so after 30s
                    // of CONTINUOUS suppression, pull the vanilla ripcord
                    // (NetworkRestart → clean return to menu) instead of letting
                    // the player sit on an unjoinable screen.
                    if (_suppressEpisodeStart < 0f) _suppressEpisodeStart = Time.unscaledTime;
                    else if (Time.unscaledTime - _suppressEpisodeStart > 30f)
                    {
                        _suppressEpisodeStart = -1f;  // one shot per episode
                        Plugin.Log.LogWarning("[SPAWN-GUARD] stuck >30s with no room — NetworkRestart back to menu");
                        try { CompetitiveUI.ShowNotification("Connection was lost — returning to menu.", new Color(1f, 0.8f, 0.3f), 6f); } catch { }
                        try { NetworkConnectionHandler.instance.NetworkRestart(); } catch { }
                    }
                }
                catch { }
                return false;  // skip vanilla; LateUpdate retries next frame
            }
            _suppressEpisodeStart = -1f;  // in a room (or offline) — episode over

            if (PhotonNetwork.OfflineMode) return true;
            if (!PhotonNetwork.InRoom || PhotonNetwork.CurrentRoom == null) return true;
            // Strict mode-matching: an ovt_ room only honors the ovt slot and a
            // cr_ff room only honors the 2v2 slot, so a stale pending slot from
            // the OTHER mode can never mis-map teams.
            var roomProps = PhotonNetwork.CurrentRoom.CustomProperties;
            bool isOvtRoom = (PhotonNetwork.CurrentRoom.Name ?? "").StartsWith("ovt_");
            bool isFfRoom = roomProps != null && roomProps.ContainsKey("cr_ff");
            int slot = isOvtRoom ? Plugin.PendingOvtSlot
                     : isFfRoom ? Plugin.Pending2v2Slot
                     : -1;
            if (slot < 0) return true;                              // not a team-mode spawn
            if (__instance.hasCreatedLocalPlayer) return false;     // already done

            int teamID = Diag2v2.SlotToTeam(slot);   // 2v2: slot/2 · 1v2: solo=0, duo=1
            int playerID = slot;

            try
            {
                var fM_playerId = typeof(PlayerAssigner).GetField("m_playerId",
                    BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Public);
                fM_playerId?.SetValue(__instance, slot);
                __instance.hasCreatedLocalPlayer = true;

                // Pre-set Photon LocalPlayer custom props so remote clients reading
                // VAR_PLAYERID / VAR_TEAMID inside Player.Start (after they receive
                // our Instantiate message) see the right values. Photon serializes
                // operations: SetCustomProperties → Instantiate guarantees props
                // arrive first.
                var pre = new ExitGames.Client.Photon.Hashtable();
                pre[Player.VAR_PLAYERID] = playerID;
                pre[Player.VAR_TEAMID] = teamID;
                // Also publish u_id (our Steam ID). Vanilla CreatePlayer relies on
                // AssignUserID() to do this; our 2v2 override skips that to avoid
                // pulling in ROUNDS identity machinery. Without u_id, peers can't
                // resolve actor→Steam ID at match-end and TryReportTeamMatch
                // aborts → match falls through to the 1v1 casual report path.
                // (The /queue/poll ready_join handler also publishes u_id before
                // room join — this is belt-and-suspenders for the CreatePlayer
                // path.)
                try
                {
                    string mySid = MatchTracker.LocalSteamId;
                    if (!string.IsNullOrEmpty(mySid) && mySid != "unknown")
                        pre["u_id"] = mySid;
                }
                catch { }
                PhotonNetwork.LocalPlayer.SetCustomProperties(pre);

                Vector3 position = Vector3.up * 100f;
                var component = PhotonNetwork.Instantiate(
                    __instance.playerPrefab.name, position, Quaternion.identity, 0
                ).GetComponent<CharacterData>();

                // Online 4-player ranked is keyboard-only (no split-screen). Vanilla
                // CreatePlayer chooses keyboard/controller based on inputDevice; for
                // our ranked path everyone is keyboard.
                component.input.inputType = GeneralInput.InputType.Keyboard;
                component.playerActions = PlayerActions.CreateWithKeyboardBindings();
                component.playerActions.Device = inputDevice;
                __instance.players.Add(component);

                int forceIndex = playerID;
                PlayerManager.RegisterPlayer(component.player, forceIndex);
                component.player.AssignPlayerID(playerID);
                component.player.AssignTeamID(teamID);
                // Skip Platform/UserID/UnityID assignments — they're identity metadata
                // for cross-platform matchmaking + the in-game block-list. Not required
                // for a ranked 4-player match to function. Optional best-effort attempt
                // via reflection so we don't pull in extra ROUNDS namespaces here.
                try
                {
                    var t = typeof(Player);
                    foreach (var (name, val) in new (string, object)[] {
                        ("AssignPlatform", null),
                        ("AssignUserID", null),
                        ("AssignUnityID", null),
                    })
                    {
                        var m = t.GetMethod(name);
                        if (m != null && val != null) m.Invoke(component.player, new[] { val });
                    }
                }
                catch { }

                // Force PlayerSkinHandler to re-bake using the correct PlayerID.
                // PlayerSkinHandler.Init() reads `data.player.PlayerID` and instantiates
                // a skin GameObject keyed off it. If Init runs DURING PhotonNetwork.Instantiate
                // (before our AssignPlayerID call lands), m_playerID is the field-default 0
                // and every local 2v2 player ends up rendered with skin index 0 (orange).
                // That's why the user reported themselves as orange but their teammate as
                // blue — local was wrong, remote was right (Player.Start.ReadPlayerID sets
                // it correctly for non-mine players before PlayerSkinHandler.Start runs).
                try
                {
                    var psh = component.GetComponentInChildren<PlayerSkinHandler>(true);
                    if (psh != null)
                    {
                        // Destroy whatever skin GameObject was already baked
                        for (int i = psh.transform.childCount - 1; i >= 0; i--)
                        {
                            var ch = psh.transform.GetChild(i);
                            if (ch != null) UnityEngine.Object.Destroy(ch.gameObject);
                        }
                        psh.inited = false;
                        var initMethod = typeof(PlayerSkinHandler).GetMethod("Init",
                            BindingFlags.NonPublic | BindingFlags.Instance);
                        initMethod?.Invoke(psh, null);
                        Plugin.Log.LogInfo($"[2v2] Re-baked local PlayerSkin for slot={slot} (post-AssignPlayerID)");
                    }
                }
                catch (Exception ex) { Plugin.Log.LogWarning($"[2v2] PlayerSkin re-bake failed: {ex.Message}"); }

                Plugin.Log.LogInfo($"[{(isOvtRoom ? "1v2" : "2v2")}] CreatePlayer override: slot={slot} team={teamID} pid={playerID}");
                return false;  // skip vanilla
            }
            catch (Exception ex)
            {
                Plugin.Log.LogError($"[2v2] CreatePlayer override failed: {ex.Message} — falling back to vanilla");
                return true;  // fall back to vanilla CreatePlayer (still wrong but at least game runs)
            }
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Bug #79 — the "Press Jump to Join does nothing" quickplay race. Vanilla's
    // 15s region-churn timer (NetworkConnectionHandler.Update) is gated only on
    // `InRoom && !GM_ArmsRace.instance`, and GM_ArmsRace activates ~2.5s AFTER
    // an opponent joins (the MATCH FOUND jingle runs first). OnPlayerEnteredRoom
    // never resets the timer, so if the opponent arrives in the last ~2.5s of
    // the window, PlayOnBestActiveRegion() leaves the just-matched room mid-
    // animation → a 16-region ping sweep (~25s) → "PRESS JUMP TO JOIN" shown
    // with no room and no opponent. Always-on (vanilla race, all modes).
    // ─────────────────────────────────────────────────────────────────────────
    [HarmonyPatch(typeof(NetworkConnectionHandler), "OnPlayerEnteredRoom")]
    class QuickplayChurnFreezePatch
    {
        static void Postfix()
        {
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.CurrentRoom == null) return;
                if (PhotonNetwork.CurrentRoom.PlayerCount < 2) return;
                var nch = NetworkConnectionHandler.instance;
                if (nch == null) return;
                // Publicized private field — freeze the churn timer the moment a
                // match is found. Vanilla re-arms it to 15f in OnJoinedRoom on the
                // next search, so no un-freeze bookkeeping is needed.
                nch.untilTryOtherRegionCounter = float.MaxValue;
                Plugin.Log.LogInfo("[QUICKPLAY-GUARD] opponent joined — region-churn timer frozen");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[QUICKPLAY-GUARD] freeze failed: {ex.Message}"); }
        }
    }

    [HarmonyPatch(typeof(NetworkConnectionHandler), "PlayOnBestActiveRegion")]
    class QuickplayChurnAbandonGuardPatch
    {
        // Second freeze point: covers the JOINER seat (which never receives
        // OnPlayerEnteredRoom — Photon routes the local join to OnJoinedRoom,
        // so its churn timer is never frozen by the Postfix above) and any
        // failure of that Postfix. Never abandon a room that already has a
        // full match in it; only skip at 2+ players — lone searchers
        // legitimately rotate regions. CRITICAL: re-arm the counter when
        // suppressing — vanilla's Update never resets it after firing, so a
        // bare suppression would re-trigger (and log) every frame while the
        // counter sits expired. Re-arming to 15s also preserves vanilla's
        // stalled-full-room escape at a delay instead of removing it.
        //
        // July 21 item 3: the running sweep coroutine is WRAPPED so the
        // requeue watchdog can (a) know a sweep is in flight (a sweep never
        // coexists with an active GM_ArmsRace except via the bug-79 race) and
        // (b) ABORT it before NetworkRestart — restarting mid-sweep is the
        // bug-#37 livelock (WaitForRestart's IsConnected wait is perpetually
        // re-satisfied by the sweep's next ConnectToRegion and m_restarting
        // is consumed forever).
        internal static volatile bool SweepActive = false;
        internal static volatile bool AbortSweep = false;

        static bool Prefix(ref System.Collections.IEnumerator __result)
        {
            try
            {
                if (PhotonNetwork.InRoom && PhotonNetwork.CurrentRoom != null &&
                    PhotonNetwork.CurrentRoom.PlayerCount >= 2)
                {
                    Plugin.Log.LogWarning("[QUICKPLAY-GUARD] PlayOnBestActiveRegion suppressed — match already found in this room");
                    try { NetworkConnectionHandler.instance.untilTryOtherRegionCounter = 15f; } catch { }
                    __result = EmptyRoutine();
                    return false;
                }
            }
            catch { }
            return true;
        }

        static void Postfix(ref System.Collections.IEnumerator __result)
        {
            __result = Track(__result);
        }

        static System.Collections.IEnumerator Track(System.Collections.IEnumerator orig)
        {
            SweepActive = true; AbortSweep = false;
            try
            {
                while (!AbortSweep && orig.MoveNext())
                    yield return orig.Current;
            }
            finally
            {
                SweepActive = false;
                if (AbortSweep) Plugin.Log.LogWarning("[QUICKPLAY-GUARD] region sweep aborted by requeue watchdog");
            }
        }

        static System.Collections.IEnumerator EmptyRoutine() { yield break; }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // 2v2 diagnostics — heavy logging gated on Pending2v2Slot >= 0 OR cr_ff
    // room presence. Goal: when a 4-player attempt fails, the BepInEx log
    // names exactly who triggered the disconnect / room-leave / restart.
    // Remove when 2v2 is stable.
    // ─────────────────────────────────────────────────────────────────────────

    internal static class Diag2v2
    {
        // "Active" = any multi-player team-mode context: 2v2 (cr_ff room prop /
        // pending 2v2 slot) OR 1v2 (ovt_ room / pending ovt slot). Every patch
        // gated here is join/spawn/skin/crown machinery that a 3-player ovt
        // room needs exactly like a 4-player cr_ff room — vanilla is 2-player-
        // shaped in all of those places. Mode differences (player count, slot→
        // team mapping) go through PlayersNeeded()/SlotToTeam() below.
        public static bool IsActive()
        {
            if (Plugin.Pending2v2Slot >= 0 || Plugin.PendingOvtSlot >= 0) return true;
            try
            {
                if (PhotonNetwork.InRoom && PhotonNetwork.CurrentRoom != null)
                {
                    var p = PhotonNetwork.CurrentRoom.CustomProperties;
                    if (p != null && p.ContainsKey("cr_ff")) return true;
                    if ((PhotonNetwork.CurrentRoom.Name ?? "").StartsWith("ovt_")) return true;
                }
            }
            catch { }
            return false;
        }

        /// <summary>True in the 1v2 context. When in a room, the room's name is
        /// authoritative (a stale pending slot from the OTHER mode must never
        /// flip the mapping); outside a room, the pending ovt slot covers the
        /// pre-join window.</summary>
        public static bool IsOvt()
        {
            try
            {
                if (PhotonNetwork.InRoom && PhotonNetwork.CurrentRoom != null)
                    return (PhotonNetwork.CurrentRoom.Name ?? "").StartsWith("ovt_");
            }
            catch { }
            return Plugin.PendingOvtSlot >= 0;
        }

        /// <summary>Server-issued slot → ROUNDS TeamID. 2v2: slots 0,1 = team 0,
        /// slots 2,3 = team 1. 1v2: slot 0 = solo = team 0, slots 1,2 = duo =
        /// team 1 (vanilla two-team scoring carries straight through).</summary>
        public static int SlotToTeam(int slot)
        {
            return IsOvt() ? (slot == 0 ? 0 : 1) : slot / 2;
        }

        /// <summary>Players required for the mode's game to start: 3 in an ovt_
        /// room, 4 in a cr_ff room.</summary>
        public static int PlayersNeeded()
        {
            return IsOvt() ? 3 : 4;
        }

        /// <summary>The local pending slot regardless of mode (-1 when neither
        /// queue has issued one). 1v2 wins when both are somehow set — the ovt
        /// slot is always the more recent lock (2v2 slots persist through
        /// series end only until cleared).</summary>
        public static int PendingSlot()
        {
            if (Plugin.PendingOvtSlot >= 0) return Plugin.PendingOvtSlot;
            return Plugin.Pending2v2Slot;
        }

        public static string ShortStack()
        {
            try
            {
                var st = new System.Diagnostics.StackTrace(2, false);
                var sb = new System.Text.StringBuilder();
                int n = Math.Min(st.FrameCount, 8);
                for (int i = 0; i < n; i++)
                {
                    var m = st.GetFrame(i)?.GetMethod();
                    if (m == null) continue;
                    sb.Append(m.DeclaringType?.Name ?? "?").Append('.').Append(m.Name);
                    if (i < n - 1) sb.Append(" <- ");
                }
                return sb.ToString();
            }
            catch { return "<stack-unavailable>"; }
        }

        public static string DescribeRoom()
        {
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.CurrentRoom == null) return "(not in room)";
                var r = PhotonNetwork.CurrentRoom;
                int pcount = r.PlayerCount;
                int max = r.MaxPlayers;
                return $"room={r.Name} players={pcount}/{max}";
            }
            catch { return "(room-describe failed)"; }
        }
    }

    /// <summary>Photon callback target for 2v2 diagnostics. Logs every player
    /// enter/leave/disconnect with the relevant Photon state so we can trace
    /// which client dropped first and why.</summary>
    public class Cr2v2DiagCallbacks : MonoBehaviour,
        Photon.Realtime.IInRoomCallbacks,
        Photon.Realtime.IConnectionCallbacks,
        Photon.Realtime.IMatchmakingCallbacks
    {
        void OnEnable()  { try { PhotonNetwork.AddCallbackTarget(this); } catch { } }
        void OnDisable() { try { PhotonNetwork.RemoveCallbackTarget(this); } catch { } }

        public void OnPlayerEnteredRoom(Photon.Realtime.Player p)
        {
            // Republish our cr_face every time a new player joins the room.
            // This fixes the "two characters missing in card-pick" bug where
            // a peer joined after our OnJoinedRoom-time publish so they never
            // received the cr_face property update.
            try
            {
                if (CompetitiveRoomDetect.IsCompetitiveRoom())
                    FacePublisher.PublishLocal();
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[POPUP] PlayerEntered face republish: {ex.Message}"); }

            if (!Diag2v2.IsActive()) return;
            try
            {
                int slot = -1, team = -1;
                if (p.CustomProperties != null)
                {
                    if (p.CustomProperties.ContainsKey("p_id")) int.TryParse(p.CustomProperties["p_id"].ToString(), out slot);
                    if (p.CustomProperties.ContainsKey("t_id")) int.TryParse(p.CustomProperties["t_id"].ToString(), out team);
                }
                Plugin.Log.LogInfo($"[2v2-DIAG] PlayerEntered: nick='{p.NickName}' actor={p.ActorNumber} p_id={slot} t_id={team} {Diag2v2.DescribeRoom()}");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[2v2-DIAG] PlayerEntered log error: {ex.Message}"); }
        }

        public void OnPlayerLeftRoom(Photon.Realtime.Player p)
        {
            // July 22 item 2 (bug #81): universal leaver banner — BEFORE the
            // Diag2v2 gate so casual/ranked 1v1 rooms get it too. Photon fires
            // this on every remaining seat, so the ally AND both opponents all
            // see who left. Display-only; every report path below is untouched.
            try { GameStateWatcher.NotifyPlayerLeftRoom(p); } catch { }
            if (!Diag2v2.IsActive()) return;
            try { Plugin.Log.LogInfo($"[2v2-DIAG] PlayerLeft: nick='{p?.NickName}' actor={p?.ActorNumber} {Diag2v2.DescribeRoom()}"); }
            catch { }

            // 2v2 DC reporting: when a player drops mid-series, the lowest-Steam-ID
            // remaining client reports the DC to the server. Server awards the
            // current match to the non-DC team (if total points >= 2) and starts
            // the 5-min sticky-team requeue grace window.
            //
            // STRICTLY 2v2: the widened IsActive() also fires this callback in
            // ovt_ rooms, where ActiveTeamSeriesId can be a STALE id from an
            // earlier 2v2 sitting (it's only cleared on the reporter's client
            // at series completion). A rage-quit in a 1v2 game would otherwise
            // post report-dc against that old 2v2 series — whose membership
            // checks PASS when the trio overlaps the old roster — applying
            // real 2v2 Glicko/gold from a 1v2 game's points. 1v2 has no DC
            // path yet by design (unscored beta; the match report handles the
            // recorded outcome).
            if (Diag2v2.IsOvt()) return;
            try
            {
                if (p == null) return;
                string seriesId = ApiClient.ActiveTeamSeriesId;
                if (string.IsNullOrEmpty(seriesId)) return;

                // Suppress DC reports during the assembly phase (between Photon
                // room join and "Round 1 active"). Two real testers (4-player
                // 2v2 sessions, v1.26.3 logs) hit this: when the slowest client
                // takes 25+ seconds to spawn-confirm, ANY transient leave by
                // another peer fires our OnPlayerLeftRoom which posts report-dc,
                // which races against the server's assembly_timeout cancel and
                // turns into a cascading DC storm — every remaining player's
                // OnPlayerLeftRoom fires when the others leave the now-cancelled
                // room, and the cascade kicks all 4 back to the menu. The
                // server's own assembly_timeout handler resolves stuck assemblies
                // without our help; we only want to report DCs once gameplay
                // has actually started.
                if (!GameStateWatcher.IsInMatch)
                {
                    Plugin.Log.LogInfo($"[2v2-DC] suppressed during assembly phase " +
                        $"(IsInMatch=false), leaver='{p?.NickName}' actor={p?.ActorNumber}");
                    return;
                }

                // Resolve the DC'd player's Steam ID from their custom props.
                string dcSteamId = null;
                if (p.CustomProperties != null)
                {
                    if (p.CustomProperties.ContainsKey("u_id")) dcSteamId = p.CustomProperties["u_id"]?.ToString();
                    if (string.IsNullOrEmpty(dcSteamId) && p.CustomProperties.ContainsKey("unity_id"))
                        dcSteamId = p.CustomProperties["unity_id"]?.ToString();
                }
                if (string.IsNullOrEmpty(dcSteamId) && !string.IsNullOrEmpty(p.UserId)) dcSteamId = p.UserId;
                if (string.IsNullOrEmpty(dcSteamId) || dcSteamId.StartsWith("photon_")) return;

                // Reporter election: lowest steam_id of those still in the room.
                string myId = MatchTracker.LocalSteamId;
                if (string.IsNullOrEmpty(myId)) return;
                long myVal; if (!long.TryParse(myId, out myVal)) return;
                bool iAmLowest = true;
                foreach (var pp in PhotonNetwork.PlayerList)
                {
                    if (pp == null || pp.ActorNumber == p.ActorNumber) continue;  // skip the leaver
                    if (pp.IsLocal) continue;
                    string ppSid = null;
                    if (pp.CustomProperties != null && pp.CustomProperties.ContainsKey("u_id"))
                        ppSid = pp.CustomProperties["u_id"]?.ToString();
                    if (string.IsNullOrEmpty(ppSid) || ppSid.StartsWith("photon_")) continue;
                    if (long.TryParse(ppSid, out long ppVal) && ppVal < myVal) { iAmLowest = false; break; }
                }
                if (!iAmLowest) return;

                // Pull current point totals from the in-game state. Per the DC rule,
                // a match with combined points >= 2 awards the match to the non-DC team.
                int t1Points = GameStateWatcher.LastP1Points;
                int t2Points = GameStateWatcher.LastP2Points;
                ApiClient.ReportTeamSeriesDc(seriesId, myId, dcSteamId, t1Points, t2Points);
                Plugin.Log.LogInfo($"[2v2-DC] reporter={myId} dc={dcSteamId} series={seriesId} pts={t1Points}/{t2Points}");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[2v2-DC] report error: {ex.Message}"); }
        }

        public void OnPlayerPropertiesUpdate(Photon.Realtime.Player target, ExitGames.Client.Photon.Hashtable changedProps) { }
        public void OnRoomPropertiesUpdate(ExitGames.Client.Photon.Hashtable propertiesThatChanged) { }
        public void OnMasterClientSwitched(Photon.Realtime.Player newMasterClient)
        {
            if (!Diag2v2.IsActive()) return;
            try { Plugin.Log.LogInfo($"[2v2-DIAG] MasterClientSwitched: new='{newMasterClient?.NickName}' actor={newMasterClient?.ActorNumber}"); }
            catch { }
        }

        public void OnConnected() { }
        public void OnConnectedToMaster() { }
        public void OnDisconnected(Photon.Realtime.DisconnectCause cause)
        {
            if (Diag2v2.PendingSlot() < 0) return;
            try { Plugin.Log.LogWarning($"[2v2-DIAG] Disconnected: cause={cause} stack={Diag2v2.ShortStack()}"); }
            catch { }
        }
        public void OnRegionListReceived(Photon.Realtime.RegionHandler regionHandler) { }
        public void OnCustomAuthenticationResponse(System.Collections.Generic.Dictionary<string, object> data) { }
        public void OnCustomAuthenticationFailed(string debugMessage) { }

        public void OnFriendListUpdate(System.Collections.Generic.List<Photon.Realtime.FriendInfo> friendList) { }
        public void OnCreatedRoom() { }
        public void OnCreateRoomFailed(short returnCode, string message)
        {
            if (Diag2v2.PendingSlot() < 0) return;
            Plugin.Log.LogWarning($"[2v2-DIAG] CreateRoomFailed: code={returnCode} msg={message}");
        }
        public void OnJoinedRoom()
        {
            // Stale-slot hygiene: a pending team-mode slot only makes sense for
            // the room it was issued for. Joining any OTHER kind of room means
            // that pending join was abandoned — without this clear, the stale
            // slot keeps Diag2v2.IsActive() true in casual/1v1 rooms, which
            // activates the slot→team skin mapping there (both players would
            // bake skin 0). The slot is published pre-join, so the MATCHING
            // room always arrives with it intact and never hits this branch.
            try
            {
                string rn = PhotonNetwork.CurrentRoom?.Name ?? "";
                var rpj = PhotonNetwork.CurrentRoom?.CustomProperties;
                bool ffRoom = rpj != null && rpj.ContainsKey("cr_ff");
                if (Plugin.Pending2v2Slot >= 0 && !ffRoom && !rn.StartsWith("team_"))
                    Plugin.ClearPending2v2Slot();
                if (Plugin.PendingOvtSlot >= 0 && !rn.StartsWith("ovt_"))
                    Plugin.ClearPendingOvtSlot();
            }
            catch { }
            // July 22 item 2: fresh room, stale leaver banner (and our own
            // left-for-ranked flag) must not carry over.
            try { CompetitiveUI.ClearLeaverBanner(); } catch { }
            try
            {
                var myProps = PhotonNetwork.LocalPlayer?.CustomProperties;
                if (myProps != null && myProps.ContainsKey("cr_lv_rk"))
                {
                    var clr = new ExitGames.Client.Photon.Hashtable();
                    clr["cr_lv_rk"] = "0";
                    PhotonNetwork.LocalPlayer.SetCustomProperties(clr);
                }
            }
            catch { }

            // Competitive-wide setup runs for any mod-issued ranked room
            // (1v1 ranked / 2v2 / sync tournament). Cosmetic late-prop reapply
            // helps every flow — opponents' custom colors / trails sometimes
            // miss the OnPlayerPropertiesUpdate event when their props were
            // already cached at room-join time. Face publish is also useful
            // as a fallback for the CardChoiceVisuals RPC timing race.
            bool isCompetitive = CompetitiveRoomDetect.IsCompetitiveRoom();
            if (isCompetitive)
            {
                try { FacePublisher.PublishLocal(); }
                catch (Exception ex) { Plugin.Log.LogWarning($"[POPUP] Face publish hook error: {ex.Message}"); }

                if (Plugin.Instance != null)
                {
                    Plugin.Instance.StartCoroutine(RepeatedCompetitiveCosmeticReapply());
                }
            }

            // Everything below is 2v2-specific: GM_ArmsRace late-joiner
            // activation, LoadingScreen clear, force-StartGame fallback,
            // 4-player card bars, assembly state poll. None of these
            // matter for 1v1 (vanilla path handles it) or for tournaments
            // (sync tournaments are 1v1-shaped).
            if (!Diag2v2.IsActive()) return;
            try { Plugin.Log.LogInfo($"[2v2-DIAG] JoinedRoom: {Diag2v2.DescribeRoom()} masterClient={(PhotonNetwork.LocalPlayer?.IsMasterClient ?? false)}"); }
            catch { }

            // Activate GM_ArmsRace.gameObject ASAP (in the same Photon callback,
            // BEFORE remote-player Photon Instantiations fire Player.Start). In
            // vanilla, NetworkConnectionHandler.OnPlayerEnteredRoom fires
            // RPCA_FoundGame (RpcTarget.All, NOT AllBuffered) when
            // PlayerList.Length == MAX_PLAYERS (vanilla const = 2). That RPC is
            // the *only* path that calls LoadingScreen.StopLoading() →
            // gameMode.SetActive(true) → GM_ArmsRace activated. In a 4-player
            // room, the master fires the RPC the moment player #2 joins; players
            // 3 and 4 (joining later) miss it forever. So their GM_ArmsRace stays
            // inactive → instance is null → NCH.Update's untilTryOtherRegionCounter
            // timer (gated on !GM_ArmsRace.instance) ticks → PlayOnBestActiveRegion
            // → LeaveRoom. Plus PlayerJoined never subscribes to PlayerManager's
            // events, so StartGame never fires either. Idempotent for early joiners
            // (vanilla activates first, our SetActive is a no-op).
            try
            {
                var gm = UnityEngine.Object.FindObjectOfType<GM_ArmsRace>(true);
                if (gm != null && !gm.gameObject.activeInHierarchy)
                {
                    gm.gameObject.SetActive(true);
                    Plugin.Log.LogInfo("[2v2] Force-activated GM_ArmsRace.gameObject (vanilla path missed late joiner)");
                }
            }
            catch (Exception ex) { Plugin.Log.LogError($"[2v2] GM_ArmsRace activate failed: {ex.Message}"); }

            // Clear LoadingScreen state so the giant "Searching" overlay disappears
            // for late joiners. RPCA_FoundGame normally calls LoadingScreen.StopLoading
            // (which sets m_isLoading=false + stops the searching particle systems +
            // hides the cancel text) but late joiners miss that RPC. Do it manually.
            try
            {
                var ls = LoadingScreen.instance;
                if (ls != null)
                {
                    try { ls.searchingSystem?.Stop(); } catch { }
                    try { ls.matchFoundSystem?.Stop(); } catch { }
                    if (ls.playerNamesSystem != null)
                        foreach (var pns in ls.playerNamesSystem)
                            try { pns?.Stop(); } catch { }
                    try { if (ls.m_cancelText != null) ls.m_cancelText.SetActive(false); } catch { }
                    var fIsLoading = typeof(LoadingScreen).GetField("m_isLoading",
                        BindingFlags.NonPublic | BindingFlags.Instance);
                    fIsLoading?.SetValue(ls, false);
                    Plugin.Log.LogInfo("[2v2] Cleared LoadingScreen searching overlay (late joiner)");
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[2v2] LoadingScreen clear failed: {ex.Message}"); }

            // Kick off a fallback that manually invokes GM_ArmsRace.StartGame
            // once all 4 players are spawned. Belt-and-suspenders: if any
            // Player.Start fires BEFORE our SetActive lands (race), GM_ArmsRace
            // wouldn't have subscribed PlayerJoined yet for that player and the
            // count won't reach 4 organically.
            if (Plugin.Instance != null)
            {
                Plugin.Instance.StartCoroutine(Force2v2StartGameWhenReady());
                Plugin.Instance.StartCoroutine(Setup4PlayerCardBarsWhenReady());
                Plugin.Instance.StartCoroutine(PollAssemblyStateLoop());
            }
        }

        /// <summary>Poll /team/series/{id}/state every 2s for the first ~20s
        /// after joining a cr_ff room. Server cancels the series after 15s if
        /// fewer than 4 of 4 spawn-confirms have arrived. When we see status=
        /// 'canceled' with reason 'assembly_timeout', show a notification and
        /// leave the room — saves the remaining clients from sitting on the
        /// ready screen until our 30s force-StartGame timeout.</summary>
        private static System.Collections.IEnumerator PollAssemblyStateLoop()
        {
            yield return new WaitForSeconds(3f);
            float deadline = Time.realtimeSinceStartup + 22f;
            while (Time.realtimeSinceStartup < deadline)
            {
                if (Plugin.Pending2v2Slot < 0) yield break;
                if (!PhotonNetwork.InRoom) yield break;
                string sid = ApiClient.ActiveTeamSeriesId;
                if (string.IsNullOrEmpty(sid)) yield break;

                bool gotResponse = false;
                ApiClient.PollTeamSeriesState(sid, (status, reason, conf) =>
                {
                    gotResponse = true;
                    if (status == "canceled" && reason == "assembly_timeout")
                    {
                        Plugin.Log.LogWarning($"[2v2] Server canceled series (assembly_timeout, {conf}/4 confirmed) — leaving room");
                        try
                        {
                            CompetitiveUI.ShowNotification(
                                $"Match couldn't assemble — only {conf} of 4 connected. Returning to menu.",
                                new Color(1f, 0.55f, 0.2f), 6f);
                        }
                        catch { }
                        try
                        {
                            Plugin.ClearPending2v2Slot();
                            if (PhotonNetwork.InRoom) PhotonNetwork.LeaveRoom();
                        }
                        catch (Exception ex) { Plugin.Log.LogWarning($"[2v2] LeaveRoom on assembly cancel failed: {ex.Message}"); }
                    }
                    else if (status == "active" && conf >= 4)
                    {
                        // All 4 confirmed — assembly succeeded, no need to keep polling.
                    }
                });
                // Wait for response or timeout, then sleep before next poll.
                float waitUntil = Time.realtimeSinceStartup + 1.5f;
                while (!gotResponse && Time.realtimeSinceStartup < waitUntil) yield return null;
                // If status is 'canceled' or assembly succeeded we can stop early.
                if (ApiClient.LastSeriesStateStatus == "canceled") yield break;
                if (ApiClient.LastSeriesStateStatus == "active" && ApiClient.LastSeriesStateConfirmations >= 4)
                    yield break;
                yield return new WaitForSeconds(2f);
            }
        }

        /// <summary>Aggressively re-apply PlayerColorCosmetic AND TrailCosmetic for
        /// every non-local actor in the room over the first ~12 seconds after
        /// joining ANY mod-issued competitive room (1v1 ranked, 2v2, sync
        /// tournament). Photon's `OnPlayerPropertiesUpdate` callback fires on PROP
        /// UPDATES only — but late joiners receive the room's existing player prop
        /// state without an update event, so cosmetic apply paths are never
        /// triggered for them. Result: some clients see opponents' custom body
        /// colors as "white" (no tint applied because cr_pcolor_color was empty
        /// when the initial DelayedApplyAll ran), and trails simply don't appear.
        /// Polling re-apply catches the late arrivals AND nudges the PCOLOR
        /// animation tick into existence for animated SKUs. Originally added for
        /// 2v2 but generalized to all competitive paths in v1.25.14.</summary>
        private static System.Collections.IEnumerator RepeatedCompetitiveCosmeticReapply()
        {
            // Wait for the spawned player GameObjects to settle.
            yield return new WaitForSeconds(2f);
            float deadline = Time.realtimeSinceStartup + 12f;
            while (Time.realtimeSinceStartup < deadline)
            {
                if (!CompetitiveRoomDetect.IsCompetitiveRoom()) yield break;
                if (!PhotonNetwork.InRoom) yield break;
                try
                {
                    var list = PhotonNetwork.PlayerList;
                    if (list != null)
                    {
                        foreach (var pp in list)
                        {
                            if (pp == null) continue;
                            if (PhotonNetwork.LocalPlayer != null && pp.ActorNumber == PhotonNetwork.LocalPlayer.ActorNumber) continue;
                            PlayerColorCosmetic.ReapplyForActor(pp.ActorNumber);
                            TrailCosmetic.ReattachForActor(pp.ActorNumber);
                            try { PlayerEffectCosmetic.ReapplyForActor(pp.ActorNumber); } catch { }
                        }
                    }
                }
                catch (Exception ex) { Plugin.Log.LogWarning($"[POPUP] cosmetic reapply tick error: {ex.Message}"); }
                yield return new WaitForSeconds(2f);
            }
        }

        /// <summary>Extend CardBarHandler.cardBars to length 4 in cr_ff rooms so
        /// each of the 4 players gets their own card-pick bar. Vanilla prefab is
        /// 1v1-shaped (2 CardBars: cardBars[0]=team 0/left, cardBars[1]=team 1/right).
        /// CardBarHandler.AddCard(int teamId, ...) at vanilla call site receives
        /// PlayerID, so PlayerID 2 and 3 hit IndexOutOfRange and their picks
        /// vanish. Strategy: try includeInactive children first (in case the
        /// prefab actually has 4 slots that 1v1 mode hides); else clone bars
        /// 0 and 1 with a vertical offset so all 4 are visible.</summary>
        private static System.Collections.IEnumerator Setup4PlayerCardBarsWhenReady()
        {
            float deadline = Time.realtimeSinceStartup + 15f;
            while (Time.realtimeSinceStartup < deadline)
            {
                // 1v2 needs this too: pid 2 (duo_b) overflows the vanilla
                // 2-slot cardBars array exactly like 2v2's pids 2/3. Extending
                // to 4 covers both modes (the 4th bar just stays unused in ovt).
                if (Diag2v2.PendingSlot() < 0) yield break;
                if (!PhotonNetwork.InRoom) yield break;
                var cbh = CardBarHandler.instance;
                if (cbh == null || cbh.cardBars == null || cbh.cardBars.Length < 2)
                {
                    yield return new WaitForSeconds(0.5f);
                    continue;
                }

                // Already extended for this mode? bail (3 bars cover 1v2's
                // pids 0-2; 4 cover 2v2's 0-3).
                if (cbh.cardBars.Length >= (Diag2v2.IsOvt() ? 3 : 4))
                {
                    Plugin.Log.LogInfo($"[2v2] CardBars already {cbh.cardBars.Length} — no extension needed");
                    yield break;
                }

                try
                {
                    // Probe the prefab tree for any inactive CardBars first — vanilla
                    // 4-player local mode might have 4 in the hierarchy with 2 hidden.
                    var allInTree = cbh.GetComponentsInChildren<CardBar>(true);
                    if (allInTree != null && allInTree.Length >= 4)
                    {
                        foreach (var b in allInTree)
                            if (b != null && !b.gameObject.activeSelf) b.gameObject.SetActive(true);
                        cbh.cardBars = allInTree;
                        Plugin.Log.LogInfo($"[2v2] CardBars: found {allInTree.Length} in tree (incl. inactive), activated all");
                        yield break;
                    }

                    // Prefab only has 2 — clone with a vertical offset.
                    var bar0 = cbh.cardBars[0];
                    var bar1 = cbh.cardBars[1];
                    if (bar0 == null || bar1 == null)
                    {
                        Plugin.Log.LogWarning("[2v2] CardBars: original bar0/bar1 is null, skipping extension");
                        yield break;
                    }

                    // The array is indexed by PlayerID at vanilla's AddCard call
                    // site, so its ORDER must mirror the mode's slot→team map.
                    // 1v2 (pid 0 = solo/left, pids 1,2 = duo/right): one clone of
                    // the RIGHT bar — [bar0, bar1, clone1]. The 2v2-shaped order
                    // would put duo_a's (pid 1) cards in a left-side clone under
                    // the solo's bar, misreading as "solo + A vs B".
                    if (Diag2v2.IsOvt())
                    {
                        var cloneObj = UnityEngine.Object.Instantiate(bar1.gameObject, bar1.transform.parent);
                        cloneObj.name = bar1.gameObject.name + "_1v2_duoB";
                        OffsetBar(cloneObj.transform, new Vector2(0f, -180f));
                        var cloneCB = cloneObj.GetComponent<CardBar>();
                        if (cloneCB == null)
                        {
                            Plugin.Log.LogWarning("[1v2] CardBars: clone missing CardBar component");
                            yield break;
                        }
                        cbh.cardBars = new CardBar[] { bar0, bar1, cloneCB };
                        Plugin.Log.LogInfo("[1v2] CardBars: extended to 3 entries [solo_left, duoA_right, duoB_right_low]");
                        yield break;
                    }

                    var clone0Obj = UnityEngine.Object.Instantiate(bar0.gameObject, bar0.transform.parent);
                    var clone1Obj = UnityEngine.Object.Instantiate(bar1.gameObject, bar1.transform.parent);
                    clone0Obj.name = bar0.gameObject.name + "_2v2_p1";
                    clone1Obj.name = bar1.gameObject.name + "_2v2_p3";

                    // Offset clones vertically so they don't overlap originals.
                    // ROUNDS' bars use RectTransform anchored to top corners.
                    OffsetBar(clone0Obj.transform, new Vector2(0f, -180f));
                    OffsetBar(clone1Obj.transform, new Vector2(0f, -180f));

                    var clone0CB = clone0Obj.GetComponent<CardBar>();
                    var clone1CB = clone1Obj.GetComponent<CardBar>();
                    if (clone0CB == null || clone1CB == null)
                    {
                        Plugin.Log.LogWarning("[2v2] CardBars: clone missing CardBar component");
                        yield break;
                    }

                    cbh.cardBars = new CardBar[] { bar0, clone0CB, bar1, clone1CB };
                    Plugin.Log.LogInfo("[2v2] CardBars: cloned to 4 entries [team0_p0, team0_p1, team1_p2, team1_p3]");
                }
                catch (Exception ex)
                {
                    Plugin.Log.LogError($"[2v2] CardBar extension failed: {ex.Message}");
                }
                yield break;
            }
            Plugin.Log.LogWarning("[2v2] CardBar setup timed out — CardBarHandler.instance never appeared");
        }

        private static void OffsetBar(Transform t, Vector2 offset)
        {
            var rt = t as RectTransform;
            if (rt != null) rt.anchoredPosition += offset;
            else t.localPosition += new Vector3(offset.x, offset.y, 0f);
        }

        private static System.Collections.IEnumerator Force2v2StartGameWhenReady()
        {
            float deadline = Time.realtimeSinceStartup + 30f;
            while (Time.realtimeSinceStartup < deadline)
            {
                if (Diag2v2.PendingSlot() < 0) yield break;
                if (!PhotonNetwork.InRoom) yield break;
                // Vanilla path took over and the game is rolling — exit success.
                // Without this, the coroutine loops until deadline and emits a
                // misleading "never reached N spawned players" warning even
                // when the match is mid-play.
                try { if (GameManager.instance != null && GameManager.instance.isPlaying) yield break; } catch { }
                int need = Diag2v2.PlayersNeeded();   // 3 in ovt_, 4 in cr_ff
                var gm = GM_ArmsRace.instance;
                if (gm != null && gm.gameObject.activeInHierarchy && PlayerManager.instance != null)
                {
                    int counted = 0;
                    foreach (var p in PlayerManager.instance.players) if (p != null) counted++;
                    if (counted >= need)
                    {
                        Plugin.Log.LogInfo($"[2v2] Force-invoking GM_ArmsRace.StartGame (counted={counted}/{need})");
                        try { gm.StartGame(); }
                        catch (Exception ex) { Plugin.Log.LogError($"[2v2] StartGame invoke failed: {ex.Message}"); }
                        yield break;
                    }
                }
                yield return new WaitForSeconds(0.5f);
            }
            Plugin.Log.LogWarning($"[2v2] Force-StartGame timed out — never reached {Diag2v2.PlayersNeeded()} spawned players");
        }
        public void OnJoinRoomFailed(short returnCode, string message)
        {
            if (Diag2v2.PendingSlot() < 0) return;
            Plugin.Log.LogWarning($"[2v2-DIAG] JoinRoomFailed: code={returnCode} msg={message}");
        }
        public void OnJoinRandomFailed(short returnCode, string message) { }
        public void OnLeftRoom()
        {
            if (Diag2v2.PendingSlot() < 0) return;
            try { Plugin.Log.LogWarning($"[2v2-DIAG] LeftRoom (Photon callback) stack={Diag2v2.ShortStack()}"); }
            catch { }
        }
    }

    /// <summary>Vanilla `NetworkConnectionHandler.OnJoinedRoom` resets
    /// `PhotonNetwork.LocalPlayer.NickName` to the Steam persona name. That
    /// happens AFTER our pre-join `NametagStyler.PublishToPhoton()` (which
    /// set the styled rich-text version), so by the time remote clients see
    /// our actor's join broadcast they get the unstyled persona name. This
    /// Postfix re-publishes the styled NickName immediately after vanilla's
    /// reset, racing as little as possible against the remote actor-join
    /// broadcasts on other clients.</summary>
    [HarmonyPatch(typeof(NetworkConnectionHandler), "OnJoinedRoom")]
    class NetworkConnectionHandler_OnJoinedRoom_RestyleNick_Patch
    {
        static void Postfix()
        {
            try
            {
                if (!CompetitiveRoomDetect.IsCompetitiveRoom()) return;
                NametagStyler.PublishToPhoton();
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[POPUP] OnJoinedRoom restyle failed: {ex.Message}"); }
        }
    }

    /// <summary>Patches NetworkRestart to log entry with caller context. Vanilla
    /// flips m_restarting=true and bails on subsequent calls, so we only see the
    /// first trigger — but that's the one we want.</summary>
    [HarmonyPatch(typeof(NetworkConnectionHandler), "NetworkRestart")]
    class NetworkConnectionHandler_NetworkRestart_Diag_Patch
    {
        static void Prefix()
        {
            // Fire in ANY competitive room (1v1 ranked OR 2v2), not just 2v2 — this
            // was `Pending2v2Slot < 0` so 1v1 ranked DCs (e.g. the "instant DC vs Toast"
            // room-abandonment) captured ZERO stack data. The stack here names whatever
            // vanilla/mod path triggered the Photon restart that ejected us mid-setup.
            try { if (!CompetitiveRoomDetect.IsCompetitiveRoom()) return; } catch { return; }
            try
            {
                var nch = NetworkConnectionHandler.instance;
                bool already = nch != null && nch.m_restarting;
                Plugin.Log.LogWarning($"[NCH-DIAG] NetworkRestart() entered (already_restarting={already}) {Diag2v2.DescribeRoom()} stack={Diag2v2.ShortStack()}");
            }
            catch { }
        }
    }

    /// <summary>Patches PhotonNetwork.LeaveRoom to log the caller. Catches any
    /// non-vanilla code path that yanks us out of the room.</summary>
    [HarmonyPatch(typeof(PhotonNetwork), "LeaveRoom", new Type[] { typeof(bool) })]
    class PhotonNetwork_LeaveRoom_Diag_Patch
    {
        static void Prefix(bool becomeInactive)
        {
            // Any competitive room (1v1 ranked OR 2v2) — was 2v2-only, blind to 1v1 DCs.
            try { if (!CompetitiveRoomDetect.IsCompetitiveRoom()) return; } catch { return; }
            try { Plugin.Log.LogWarning($"[NCH-DIAG] PhotonNetwork.LeaveRoom(becomeInactive={becomeInactive}) {Diag2v2.DescribeRoom()} stack={Diag2v2.ShortStack()}"); }
            catch { }
        }
    }

    /// <summary>Patch GM_ArmsRace.PlayerJoined to log every fire so we can see
    /// where the count gets stuck. Vanilla does:
    ///   if (num &lt; playersNeededToStart) return;
    ///   StartGame();
    /// — if `num` never reaches 4, StartGame never fires.</summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "PlayerJoined")]
    class GMArmsRace_PlayerJoined_Diag_Patch
    {
        static void Prefix(GM_ArmsRace __instance, global::Player player)
        {
            if (!Diag2v2.IsActive()) return;
            try
            {
                int num = 0;
                int total = 0;
                if (PlayerManager.instance != null && PlayerManager.instance.players != null)
                {
                    total = PlayerManager.instance.players.Count;
                    foreach (var p in PlayerManager.instance.players) if (p != null) num++;
                }
                int needed = __instance.playersNeededToStart;
                Plugin.Log.LogInfo($"[2v2-DIAG] GM_ArmsRace.PlayerJoined fired: counted={num} listSize={total} playersNeededToStart={needed}");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[2v2-DIAG] GM_ArmsRace.PlayerJoined log error: {ex.Message}"); }
        }
    }

    /// <summary>Log when GM_ArmsRace.StartGame fires — if all 4 join but this
    /// never triggers, the gating in PlayerJoined is the problem.</summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "StartGame")]
    class GMArmsRace_StartGame_Diag_Patch
    {
        static void Prefix()
        {
            if (!Diag2v2.IsActive()) return;
            try { Plugin.Log.LogInfo($"[2v2-DIAG] GM_ArmsRace.StartGame() fired {Diag2v2.DescribeRoom()}"); }
            catch { }
        }
    }

    /// <summary>Player.Start sets PlayerID/TeamID from custom properties. Log
    /// the values we see so we can confirm slots/teams arrive correctly on
    /// remote clients.</summary>
    [HarmonyPatch(typeof(global::Player), "Start")]
    class Player_Start_Diag_Patch
    {
        static void Postfix(global::Player __instance)
        {
            if (!Diag2v2.IsActive()) return;
            try
            {
                bool isLocal = false;
                int actor = -1;
                try { isLocal = __instance.data?.view?.IsMine ?? false; } catch { }
                try { actor = __instance.data?.view?.OwnerActorNr ?? -1; } catch { }
                Plugin.Log.LogInfo($"[2v2-DIAG] Player.Start: pid={__instance.PlayerID} team={__instance.TeamID} isLocal={isLocal} actor={actor}");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[2v2-DIAG] Player.Start log error: {ex.Message}"); }
        }
    }

    /// <summary>Publishes the local player's selected face to a Photon LocalPlayer
    /// custom property `cr_face` so that in cr_ff rooms, every client can read any
    /// other player's face without depending on RPC timing. Vanilla's
    /// CardChoiceVisuals.Show fires `RPCA_SetFace` with `RpcTarget.All` only from
    /// the picker's client — in 2v2 with 4 sequential pickers, the RPC for picker N
    /// can arrive AFTER picker N+1's Show() has already torn down and re-rendered
    /// the visualizer locally, so remote clients see "yesterday's picker" or no
    /// face at all. Reading from custom props on each Show() call eliminates the
    /// timing race entirely.</summary>
    internal static class FacePublisher
    {
        public const string PROP_FACE = "cr_face";

        public static void PublishLocal()
        {
            try
            {
                var cch = CharacterCreatorHandler.instance;
                if (cch == null)
                {
                    Plugin.Log.LogInfo("[POPUP-DIAG] PublishLocal skipped: CharacterCreatorHandler.instance is null (game state not ready)");
                    return;
                }
                if (cch.selectedPlayerFaces == null || cch.selectedPlayerFaces.Length == 0)
                {
                    Plugin.Log.LogInfo("[POPUP-DIAG] PublishLocal skipped: selectedPlayerFaces empty");
                    return;
                }
                var face = cch.selectedPlayerFaces[0];
                if (face == null)
                {
                    Plugin.Log.LogInfo("[POPUP-DIAG] PublishLocal skipped: face[0] is null");
                    return;
                }
                if (PhotonNetwork.LocalPlayer == null)
                {
                    Plugin.Log.LogInfo("[POPUP-DIAG] PublishLocal skipped: LocalPlayer is null");
                    return;
                }
                // If the local face is fully default (all four item IDs zero), skip
                // publishing. Accounts that never opened the character creator
                // have an uninitialized face — publishing all-zeros causes
                // CharacterCreatorItemEquipper.EquipFace to call Equip(null) on
                // each slot, which destroys the visualizer's stock face entirely
                // and renders a featureless body. User reported: "2 of 4 missing
                // in card-pick phase" pointed at Sid3/Sid4 (alts that never
                // customized their face). Without our publish, vanilla's
                // RPCA_SetFace on the picker's client falls back to the local
                // visualizer's saved face.
                if (face.eyeID == 0 && face.mouthID == 0 && face.detailID == 0 && face.detail2ID == 0)
                {
                    Plugin.Log.LogInfo("[2v2] FacePublisher: skipping publish (face is all-zero defaults — let vanilla RPC handle it)");
                    return;
                }

                string serialized = string.Join("|", new[] {
                    face.eyeID.ToString(System.Globalization.CultureInfo.InvariantCulture),
                    face.eyeOffset.x.ToString("F3", System.Globalization.CultureInfo.InvariantCulture),
                    face.eyeOffset.y.ToString("F3", System.Globalization.CultureInfo.InvariantCulture),
                    face.mouthID.ToString(System.Globalization.CultureInfo.InvariantCulture),
                    face.mouthOffset.x.ToString("F3", System.Globalization.CultureInfo.InvariantCulture),
                    face.mouthOffset.y.ToString("F3", System.Globalization.CultureInfo.InvariantCulture),
                    face.detailID.ToString(System.Globalization.CultureInfo.InvariantCulture),
                    face.detailOffset.x.ToString("F3", System.Globalization.CultureInfo.InvariantCulture),
                    face.detailOffset.y.ToString("F3", System.Globalization.CultureInfo.InvariantCulture),
                    face.detail2ID.ToString(System.Globalization.CultureInfo.InvariantCulture),
                    face.detail2Offset.x.ToString("F3", System.Globalization.CultureInfo.InvariantCulture),
                    face.detail2Offset.y.ToString("F3", System.Globalization.CultureInfo.InvariantCulture),
                });
                var props = new ExitGames.Client.Photon.Hashtable();
                props[PROP_FACE] = serialized;
                PhotonNetwork.LocalPlayer.SetCustomProperties(props);
                Plugin.Log.LogInfo($"[2v2] Published local face to Photon: {serialized}");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[2v2] Face publish failed: {ex.Message}"); }
        }

        public static bool TryReadAndApply(int pickerActorNumber, GameObject visualizerRoot)
        {
            try
            {
                Photon.Realtime.Player photonPlayer = null;
                foreach (var pp in PhotonNetwork.PlayerList)
                    if (pp != null && pp.ActorNumber == pickerActorNumber) { photonPlayer = pp; break; }
                if (photonPlayer == null || photonPlayer.CustomProperties == null)
                {
                    Plugin.Log.LogInfo($"[POPUP-DIAG] Face apply skipped actor={pickerActorNumber}: photonPlayer={(photonPlayer == null ? "null" : "found")} props={(photonPlayer?.CustomProperties == null ? "null" : "ok")}");
                    return false;
                }
                if (!photonPlayer.CustomProperties.ContainsKey(PROP_FACE))
                {
                    Plugin.Log.LogInfo($"[POPUP-DIAG] Face apply skipped actor={pickerActorNumber}: cr_face property not set on remote player (their client never published, or property not yet replicated)");
                    return false;
                }
                string s = photonPlayer.CustomProperties[PROP_FACE]?.ToString() ?? "";
                if (string.IsNullOrEmpty(s))
                {
                    Plugin.Log.LogInfo($"[POPUP-DIAG] Face apply skipped actor={pickerActorNumber}: cr_face value is empty string");
                    return false;
                }
                var parts = s.Split('|');
                if (parts.Length < 12)
                {
                    Plugin.Log.LogInfo($"[POPUP-DIAG] Face apply skipped actor={pickerActorNumber}: cr_face has {parts.Length} parts (expected 12) — likely truncated");
                    return false;
                }
                var ic = System.Globalization.CultureInfo.InvariantCulture;
                int eyeID = int.Parse(parts[0], ic);
                float eOx = float.Parse(parts[1], ic), eOy = float.Parse(parts[2], ic);
                int mouthID = int.Parse(parts[3], ic);
                float mOx = float.Parse(parts[4], ic), mOy = float.Parse(parts[5], ic);
                int detailID = int.Parse(parts[6], ic);
                float dOx = float.Parse(parts[7], ic), dOy = float.Parse(parts[8], ic);
                int detail2ID = int.Parse(parts[9], ic);
                float d2Ox = float.Parse(parts[10], ic), d2Oy = float.Parse(parts[11], ic);
                // Skip all-zero faces (uninitialized accounts). Applying a
                // default face wipes the visualizer's stock face. Caller will
                // see TryReadAndApply return false and won't log "applied".
                if (eyeID == 0 && mouthID == 0 && detailID == 0 && detail2ID == 0) return false;
                var face = PlayerFace.CreateFace(
                    eyeID, new Vector2(eOx, eOy),
                    mouthID, new Vector2(mOx, mOy),
                    detailID, new Vector2(dOx, dOy),
                    detail2ID, new Vector2(d2Ox, d2Oy)
                );
                var equipper = visualizerRoot?.GetComponentInChildren<CharacterCreatorItemEquipper>(true);
                if (equipper == null) return false;
                equipper.EquipFace(face);
                return true;
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[2v2] Face read+apply failed: {ex.Message}");
                return false;
            }
        }
    }

    /// <summary>Patch CardChoiceVisuals.Show Postfix to apply the picker's face from
    /// Photon custom props after vanilla's RPC-broadcast attempt. In 2v2 the vanilla
    /// RPC has timing races (only the picker's client fires it; remote clients can
    /// see stale faces from the previous picker, or nothing if the RPC arrived
    /// AFTER the next picker's Show tore down and re-instantiated the skin). Reading
    /// from custom props each Show() guarantees the right face on every client.</summary>
    /// <summary>Re-tint the card-pick visualizer body to match the picker's
    /// actual team. Vanilla CardChoiceVisuals spawns a skin clone that displays
    /// fine in 1v1, but in 2v2 our PlayerSkinBank patch can't reach the visualizer
    /// because the body's color is baked at clone time from a path that runs
    /// before children spawn. User report: "Sid4 was on blue, his character
    /// color showed as orange at the card pick screen" while in-game body
    /// renders blue correctly. Fix: wait a couple frames for the visualizer
    /// hierarchy to populate, then walk SpriteRenderer + ParticleSystem and
    /// recolor anything that looks team-baseline (the wrong team's hue).</summary>
    internal static class CardPickBodyTinter
    {
        // Vanilla ROUNDS team colors. These match the in-game player body for
        // each team — used as both the "wrong-team baseline to detect" and
        // the "right-team color to apply" depending on which side we're on.
        // Read from PlayerSkinBank.instance.skins[] at first call so the values
        // track whatever ROUNDS ships rather than hardcoded hex.
        private static Color teamColor0 = new Color(0.95f, 0.45f, 0.32f); // orange-ish fallback
        private static Color teamColor1 = new Color(0.45f, 0.62f, 0.95f); // blue-ish fallback
        private static bool teamColorsResolved = false;

        // Public accessors so the skin-rebake guard (PlayerSkinHandlerInitRebakeGuard)
        // can compare a baked body against the real team colors.
        public static Color TeamColor0 { get { return teamColor0; } }
        public static Color TeamColor1 { get { return teamColor1; } }
        public static void EnsureTeamColors() { TryResolveTeamColors(); }

        private static void TryResolveTeamColors()
        {
            if (teamColorsResolved) return;
            try
            {
                // v1.28 fix: the OLD code reflected over PlayerSkinBank.skins[] entries
                // looking for the "most-saturated Color FIELD". But skins[] is a
                // PlayerSkinInstance[] whose team color lives at
                // .currentPlayerSkin.color (a NESTED object) — the top-level struct has
                // NO Color field, so the sniff found nothing and returned Color.white for
                // BOTH teams (logs: "t0=#FFFFFF t1=#FFFFFF"). The card-pick retint then
                // matched nothing (IsCloseHue vs white) and was a total no-op, so a body
                // that rendered the wrong team color never got corrected. Read the REAL
                // color via PlayerSkinBank.GetPlayerSkinColors(team).color through
                // reflection (no direct PlayerSkin type ref — all-reflection rule), with
                // the skins[].currentPlayerSkin.color path as the fallback.
                Color? c0 = ResolveTeamColor(0);
                Color? c1 = ResolveTeamColor(1);
                // Saturation floor: only accept a resolved color if it's actually
                // colored (not white/grey). Otherwise keep the sane hardcoded fallback
                // so the retint still has two distinct hues to work with.
                if (c0.HasValue && ColorSat(c0.Value) > 0.12f) teamColor0 = c0.Value;
                if (c1.HasValue && ColorSat(c1.Value) > 0.12f) teamColor1 = c1.Value;
                teamColorsResolved = true;
                Plugin.Log.LogInfo($"[CARDPICK-TINT] resolved team colors: t0={ColorHex(teamColor0)} t1={ColorHex(teamColor1)} (raw c0={(c0.HasValue?ColorHex(c0.Value):"null")} c1={(c1.HasValue?ColorHex(c1.Value):"null")})");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[CARDPICK-TINT] resolve failed: {ex.Message}"); }
        }

        private static float ColorSat(Color c)
        {
            float mx = Math.Max(c.r, Math.Max(c.g, c.b));
            float mn = Math.Min(c.r, Math.Min(c.g, c.b));
            return mx <= 0.001f ? 0f : (mx - mn) / mx;
        }

        /// <summary>Resolve a team's real body color. Primary path:
        /// PlayerSkinBank.GetPlayerSkinColors(team) → PlayerSkin whose `.color` field
        /// is the team body color. Fallback: instance.skins[team].currentPlayerSkin.color.
        /// All reflection so we keep zero direct PlayerSkin/PlayerSkinBank type refs.</summary>
        private static Color? ResolveTeamColor(int team)
        {
            try
            {
                var bankType = typeof(PlayerSkinBank);
                // Static PlayerSkinBank.GetPlayerSkinColors(int) → PlayerSkin
                var mGet = bankType.GetMethod("GetPlayerSkinColors",
                    BindingFlags.Public | BindingFlags.Static);
                object skin = null;
                if (mGet != null)
                {
                    try { skin = mGet.Invoke(null, new object[] { team }); } catch { }
                }
                // Fallback: instance.skins[team].currentPlayerSkin
                if (skin == null)
                {
                    var bank = PlayerSkinBank.instance;
                    if (bank == null) return null;
                    var fSkins = bankType.GetField("skins",
                        BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                    var arr = fSkins?.GetValue(bank) as System.Array;
                    if (arr == null || arr.Length <= team) return null;
                    var inst = arr.GetValue(team);
                    var fCur = inst?.GetType().GetField("currentPlayerSkin",
                        BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                    skin = fCur?.GetValue(inst);
                }
                if (skin == null) return null;
                var fColor = skin.GetType().GetField("color",
                    BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                if (fColor == null || fColor.FieldType != typeof(Color)) return null;
                return (Color)fColor.GetValue(skin);
            }
            catch { return null; }
        }

        private static string ColorHex(Color c) =>
            $"#{(int)(c.r * 255):X2}{(int)(c.g * 255):X2}{(int)(c.b * 255):X2}";

        public static IEnumerator RetintAfterChildrenSpawn(GameObject visualizer, int pickerTeamID, int pickerID, int pickerActor = -1)
        {
            // NO position mutation here — ever. The clone lives under
            // CardChoiceVisuals' root, which vanilla scales to 33x when shown
            // (CurveAnimation animates it through arbitrary values), so ANY
            // localPosition offset gets multiplied by the parent's current scale:
            // the old (pickerID-1.5)*4 anti-stack spread put picker 0 at world
            // X=-198 and picker 1 at X=-66 on every solo pick — the "body
            // missing, cosmetics still show" bug (#58, proven in the 7/12 log:
            // 34/34 solo picks off-screen). The spread guarded against a
            // stacking scenario that cannot happen — vanilla destroys
            // currentSkin on every Show, so only ONE picker body exists at a
            // time and vanilla's own stage-center placement is correct for it.
            // Wait for vanilla's child-spawn pass, then only recolor in place.
            for (int i = 0; i < 10; i++)
            {
                if (visualizer == null) yield break;
                yield return null;
            }
            if (visualizer == null) yield break;

            TryResolveTeamColors();
            Color desired = (pickerTeamID == 1) ? teamColor1 : teamColor0;
            Color wrongTeam = (pickerTeamID == 1) ? teamColor0 : teamColor1;

            // v1.30 (#58 "wrong avatar"): if the picker has a CUSTOM body color
            // equipped (cr_pcolor_color Photon prop), that — not the vanilla team
            // hue — is what their body should read as. In that case both vanilla
            // team baselines count as "wrong" and get repainted to the custom color.
            bool hasCustom = false;
            try
            {
                if (pickerActor > 0 && PhotonNetwork.PlayerList != null)
                {
                    foreach (var pl in PhotonNetwork.PlayerList)
                    {
                        if (pl == null || pl.ActorNumber != pickerActor) continue;
                        if (pl.CustomProperties != null && pl.CustomProperties.ContainsKey("cr_pcolor_color"))
                        {
                            string hex = pl.CustomProperties["cr_pcolor_color"] as string;
                            Color cc;
                            if (!string.IsNullOrEmpty(hex) && ColorUtility.TryParseHtmlString(hex, out cc))
                            {
                                desired = cc;
                                hasCustom = true;
                            }
                        }
                        break;
                    }
                }
            }
            catch { }

            int sprites = 0, particles = 0, skinFields = 0;
            try
            {
                Func<Color, bool> looksWrong = c =>
                    hasCustom ? (IsCloseHue(c, teamColor0) || IsCloseHue(c, teamColor1))
                              : IsCloseHue(c, wrongTeam);

                // 1) Replace SpriteRenderer colors that look like the WRONG team's hue.
                var sprs = visualizer.GetComponentsInChildren<SpriteRenderer>(true);
                foreach (var sr in sprs)
                {
                    if (sr == null) continue;
                    if (looksWrong(sr.color))
                    {
                        sr.color = new Color(desired.r, desired.g, desired.b, sr.color.a);
                        sprites++;
                    }
                }

                // 2) ParticleSystems — main module + colorOverLifetime.
                var pss = visualizer.GetComponentsInChildren<ParticleSystem>(true);
                foreach (var ps in pss)
                {
                    if (ps == null) continue;
                    var main = ps.main;
                    var sc = main.startColor;
                    Color current = sc.color;
                    if (looksWrong(current))
                    {
                        sc.color = new Color(desired.r, desired.g, desired.b, current.a);
                        main.startColor = sc;
                        particles++;
                    }
                }

                // 3) PlayerSkin / PlayerSkinHandler MonoBehaviours within the visualizer.
                //    Some hue propagation goes via these field-color reads at render time,
                //    not via the spawned sprites — set the fields too.
                var comps = visualizer.GetComponentsInChildren<MonoBehaviour>(true);
                foreach (var c in comps)
                {
                    if (c == null) continue;
                    var t = c.GetType();
                    if (t.Name != "PlayerSkin" && t.Name != "PlayerSkinHandler") continue;
                    foreach (var f in t.GetFields(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance))
                    {
                        if (f.FieldType != typeof(Color)) continue;
                        try
                        {
                            var v = (Color)f.GetValue(c);
                            if (looksWrong(v))
                            {
                                f.SetValue(c, new Color(desired.r, desired.g, desired.b, v.a));
                                skinFields++;
                            }
                        }
                        catch { }
                    }
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[CARDPICK-TINT] retint failed: {ex.Message}"); }

            if (sprites > 0 || particles > 0 || skinFields > 0)
                Plugin.Log.LogInfo($"[CARDPICK-TINT] pickerID={pickerID} team={pickerTeamID} custom={hasCustom} retinted: sprites={sprites} particles={particles} skinFields={skinFields}");

            // v1.30 (#58 "no body, cosmetics still show"): the picker's body IS the
            // clone's root particle system (learning #96 — vanilla Play()s exactly
            // one PS at Show-time, before children spawn). If it isn't emitting by
            // now, kick it — and ALWAYS log its state so the next report tells us
            // which layer failed instead of guessing. Never Pause/Stop/Clear (#96/#108).
            try
            {
                var bodyPs = visualizer.GetComponent<ParticleSystem>() ?? visualizer.GetComponentInChildren<ParticleSystem>(true);
                if (bodyPs != null)
                {
                    bool wasPlaying = bodyPs.isPlaying;
                    if (!wasPlaying) bodyPs.Play(true);
                    Plugin.Log.LogInfo($"[CARDPICK-BODY] pickerID={pickerID} ps={bodyPs.gameObject.name} wasPlaying={wasPlaying} count={bodyPs.particleCount} activeInHierarchy={bodyPs.gameObject.activeInHierarchy} worldPos={bodyPs.transform.position}");
                }
                else
                {
                    Plugin.Log.LogWarning($"[CARDPICK-BODY] pickerID={pickerID} NO ParticleSystem found on visualizer — body cannot render");
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[CARDPICK-BODY] check failed: {ex.Message}"); }

        }

        // RGB distance — works for any hue without needing to convert to HSV.
        // Threshold 0.35 matches PlayerColorCosmetic.IsTeamLike so we get the
        // same "look like the team's color, not face/gun/accent" filter.
        private static bool IsCloseHue(Color a, Color b)
        {
            float dr = a.r - b.r, dg = a.g - b.g, db = a.b - b.b;
            return Mathf.Sqrt(dr * dr + dg * dg + db * db) < 0.35f;
        }
    }

    [HarmonyPatch(typeof(CardChoiceVisuals), "Show")]
    class CardChoiceVisuals_Show_Competitive_Patch
    {
        static void Postfix(CardChoiceVisuals __instance, int pickerID)
        {
            try
            {
                if (!CompetitiveRoomDetect.IsCompetitiveRoom()) return;
                var pm = PlayerManager.instance;
                if (pm == null || pm.players == null || pickerID < 0 || pickerID >= pm.players.Count) return;
                var picker = pm.players[pickerID];
                if (picker == null) return;
                var pv = picker.GetComponent<PhotonView>();
                if (pv == null || pv.Owner == null) return;

                // If THIS client is the picker, republish our cr_face right
                // before the visualizer renders. Tester report (Sid2's logs)
                // showed multiple players' face publish never reached remote
                // clients despite OnJoinedRoom firing — likely a replication
                // race between OnJoinedRoom and the first card-pick on a peer.
                // A republish here gives the remote a fresh property right
                // before they need it.
                if (picker.IsLocal) FacePublisher.PublishLocal();
                // Instinct achievement (v1.30): remember whose pick popup this is
                // so the RPCA_SetCurrentSelected postfix only counts LOCAL scrolls.
                CardPickSelectionTracker.CurrentPickerIsLocal = picker.IsLocal;

                bool ok = FacePublisher.TryReadAndApply(pv.Owner.ActorNumber, __instance.gameObject);
                if (ok)
                    Plugin.Log.LogInfo($"[POPUP] CardChoiceVisuals: applied picker face from Photon (pickerID={pickerID}, actor={pv.Owner.ActorNumber})");

                // Diagnostic for "2 of 4 pickers don't show a character" bug.
                // Log currentSkin state + transform so we can tell if the GO
                // exists, is active, has children, and where it's positioned.
                try
                {
                    var fSkin = typeof(CardChoiceVisuals).GetField("currentSkin",
                        BindingFlags.NonPublic | BindingFlags.Instance);
                    var skin = fSkin?.GetValue(__instance) as GameObject;
                    string skinDesc;
                    if (skin == null) skinDesc = "(null)";
                    else
                    {
                        var lp = skin.transform.localPosition;
                        var ls = skin.transform.localScale;
                        int childCount = skin.transform.childCount;
                        skinDesc = $"name={skin.name} active={skin.activeInHierarchy} layer={skin.layer} children={childCount} localPos=({lp.x:F1},{lp.y:F1},{lp.z:F1}) localScale=({ls.x:F2},{ls.y:F2},{ls.z:F2})";

                        // Deferred re-tint + body health-check only. The clone must be
                        // left at vanilla's stage-center placement: it sits under the
                        // 33x-scaled CardChoiceVisuals root, so any local offset lands
                        // at offset*33 world units — the retired 2v2 anti-stack spread
                        // (v1.27-v1.30.1) was exactly that, parking solo-pick bodies at
                        // world X=-198/-66, i.e. bug #58's "no body, cosmetics show".
                        // Only one picker body exists at a time (vanilla destroys
                        // currentSkin on every Show), so no spread is ever needed.
                        if (Plugin.Instance != null && skin != null)
                        {
                            Plugin.Instance.StartCoroutine(
                                CardPickBodyTinter.RetintAfterChildrenSpawn(skin, picker.TeamID, pickerID, pv.Owner.ActorNumber));
                        }
                    }
                    Plugin.Log.LogInfo($"[CARDPICK-DIAG] pickerID={pickerID} actor={pv.Owner.ActorNumber} pid={picker.PlayerID} team={picker.TeamID} isLocal={picker.IsLocal} currentSkin: {skinDesc}");
                }
                catch (Exception dex) { Plugin.Log.LogWarning($"[CARDPICK-DIAG] log error: {dex.Message}"); }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[POPUP] CardChoiceVisuals.Show postfix error: {ex.Message}"); }
        }
    }

    /// <summary>Instinct achievement tracker (v1.30). ROUNDS broadcasts every
    /// card-selection change through CardChoiceVisuals.RPCA_SetCurrentSelected;
    /// selection starts at index 0 (the left-most card). If the LOCAL player's
    /// own pick popup ever moves off index 0, they "viewed the other cards" and
    /// the match's Instinct run is broken. GameStateWatcher resets the flag per
    /// match and evaluates it at game over.</summary>
    internal static class CardPickSelectionTracker
    {
        public static bool CurrentPickerIsLocal;
    }

    /// <summary>Deep End achievement tracker (v1.30, July 12 spec). ROUNDS routes
    /// every Abyssal Countdown activation through AbyssalCountdown.RPCA_Activate
    /// (a ChildRPC that fires on ALL clients). Count only the LOCAL player's
    /// activations; GameStateWatcher banks them per round and requires one in
    /// every round of a won game.</summary>
    [HarmonyPatch(typeof(AbyssalCountdown), "RPCA_Activate")]
    class AbyssalCountdown_Activate_DeepEnd_Patch
    {
        static void Postfix(AbyssalCountdown __instance)
        {
            try
            {
                var cd = __instance.GetComponentInParent<CharacterData>();
                if (cd != null && cd.view != null && cd.view.IsMine)
                    GameStateWatcher.OnAbyssalActivatedLocal();
            }
            catch { }
        }
    }

    [HarmonyPatch(typeof(CardChoiceVisuals), "RPCA_SetCurrentSelected")]
    class CardChoiceVisuals_SetSelected_Instinct_Patch
    {
        static void Postfix(int toSet)
        {
            try
            {
                if (!CompetitiveRoomDetect.IsCompetitiveRoom()) return;
                if (!CardPickSelectionTracker.CurrentPickerIsLocal) return;
                if (toSet != 0 && !GameStateWatcher.achLeftmostViolated)
                {
                    GameStateWatcher.achLeftmostViolated = true;
                    Plugin.Log.LogInfo("[ACH] Instinct run broken — selection moved off the left-most card");
                }
            }
            catch { }
        }
    }

    /// <summary>2v2 crown fix (bug #59). Vanilla GameCrownHandler is hard-coded
    /// 1v1: one crown GameObject whose LateUpdate lerps strictly between
    /// players[0] and players[1] head positions — in a 4-player cr_ff room the
    /// crown can only ever sit on ONE player, and never on players[2]/[3] at
    /// all. This prefix fully replaces LateUpdate in cr_ff rooms: it computes
    /// the leading TEAM from GM_ArmsRace rounds→points (same precedence as
    /// vanilla PointOver), then parks the vanilla crown on one member and a
    /// clone ("cr_mate_crown") on the other. The clone lives as a SIBLING of
    /// the handler (not a child) so positioning the handler on player A can't
    /// drag it, and it dies with the scene — re-created lazily per map.
    /// 1v1 rooms return true and run vanilla untouched.</summary>
    [HarmonyPatch(typeof(GameCrownHandler), "LateUpdate")]
    class GameCrownHandler2v2Patch
    {
        private static GameObject mateCrown;   // Unity fake-null after scene unload → lazily re-cloned

        static bool Prefix(GameCrownHandler __instance)
        {
            if (!Diag2v2.IsActive()) return true;
            try
            {
                var gm = __instance.gm != null ? __instance.gm : __instance.GetComponentInParent<GM_ArmsRace>();
                if (gm == null || PlayerManager.instance == null || PlayerManager.instance.players == null)
                    return false;

                // Leading team: rounds first, points as tiebreak (vanilla PointOver order).
                int lead = -1;
                if (gm.p1Rounds != gm.p2Rounds) lead = gm.p1Rounds > gm.p2Rounds ? 0 : 1;
                else if (gm.p1Points != gm.p2Points) lead = gm.p1Points > gm.p2Points ? 0 : 1;

                GameObject crown = __instance.transform.childCount > 0
                    ? __instance.transform.GetChild(0).gameObject : null;
                if (crown == null) return false;

                if (lead == -1)
                {
                    // Tied — no crown for anyone (vanilla shows none until a first leader too).
                    if (crown.activeSelf) crown.SetActive(false);
                    if (mateCrown != null && mateCrown.activeSelf) mateCrown.SetActive(false);
                    return false;
                }

                Player a = null, b = null;
                foreach (var p in PlayerManager.instance.players)
                {
                    if (p == null || p.data == null || p.TeamID != lead) continue;
                    if (a == null) a = p; else if (b == null) { b = p; break; }
                }
                if (a == null)
                {
                    if (crown.activeSelf) crown.SetActive(false);
                    if (mateCrown != null && mateCrown.activeSelf) mateCrown.SetActive(false);
                    return false;
                }

                bool aVisible = a.gameObject.activeInHierarchy;
                if (crown.activeSelf != aVisible) crown.SetActive(aVisible);
                if (aVisible) __instance.transform.position = a.data.GetCrownPos();

                if (b != null)
                {
                    if (mateCrown == null)
                    {
                        mateCrown = UnityEngine.Object.Instantiate(crown, __instance.transform.parent);
                        mateCrown.name = "cr_mate_crown";
                        // Match the handler chain's world scale — the clone's new parent
                        // is one level up, so inherit the handler's local scale too.
                        mateCrown.transform.localScale = Vector3.Scale(
                            __instance.transform.localScale, crown.transform.localScale);
                        Plugin.Log.LogInfo("[2v2-CROWN] mate crown cloned");
                    }
                    bool bVisible = b.gameObject.activeInHierarchy;
                    if (mateCrown.activeSelf != bVisible) mateCrown.SetActive(bVisible);
                    if (bVisible)
                    {
                        // The vanilla crown renders at handlerPos + its child-local
                        // offset; mirror that exact world offset on the clone so both
                        // crowns float at the same height above their player.
                        Vector3 childOfs = crown.transform.position - __instance.transform.position;
                        mateCrown.transform.position = b.data.GetCrownPos() + childOfs;
                    }
                }
                else if (mateCrown != null && mateCrown.activeSelf)
                {
                    mateCrown.SetActive(false);
                }
                return false;
            }
            catch (Exception ex)
            {
                // Never break the round over a cosmetic — fall through to vanilla.
                Plugin.Log.LogWarning($"[2v2-CROWN] prefix error: {ex.Message}");
                return true;
            }
        }
    }

    /// <summary>True when we're in a mod-issued competitive room — 2v2 (cr_ff /
    /// team_*), 1v1 ranked (ranked_*), or sync tournament (sct-*). Used to scope
    /// behaviors that should apply uniformly across competitive paths but NOT to
    /// vanilla casual/private rooms (which may have mixed mod / non-mod players).
    /// </summary>
    internal static class CompetitiveRoomDetect
    {
        public static bool IsCompetitiveRoom()
        {
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.CurrentRoom == null) return false;
                var props = PhotonNetwork.CurrentRoom.CustomProperties;
                if (props != null && props.ContainsKey("cr_ff")) return true;
                string n = PhotonNetwork.CurrentRoom.Name ?? "";
                return n.StartsWith("ranked_") || n.StartsWith("team_") || n.StartsWith("sct-") || n.StartsWith("ovt_");
            }
            catch { return false; }
        }
    }

    /// <summary>Bug #64 — per-game card baseline for the hold-Tab board. Vanilla's
    /// rematch flow (GM_ArmsRace.IDoRematch → PlayerManager.ResetCharacters →
    /// Player.FullReset) resets gun/stats/block but never clears data.currentCards,
    /// so the list accumulates across all games in a room. FullReset firing IS the
    /// "new game in same room" signal — snapshot the count so TabStatsOverlay can
    /// render only cards picked since.</summary>
    [HarmonyPatch(typeof(global::Player), "FullReset")]
    class Player_FullReset_CardBaseline_Patch
    {
        static void Postfix(global::Player __instance)
        {
            try { TabStatsOverlay.RecordCardBaseline(__instance); } catch { }
        }
    }

    /// <summary>Auto-confirm the post-game "Continue?" popup so all clients advance
    /// together. Vanilla `PopUpHandler.StartPicking` waits for the local-mine player
    /// to press Jump on a directional Yes/No selector — there's no network sync of
    /// the choice, each client decides independently. In 2v2 with 4 sequential
    /// pickers this caused desync (player 1 hits Yes → DoContinue locally → next
    /// round on their client; others stuck). Even in 1v1, players found the prompt
    /// annoying and "really don't like hitting Yes". Bypass: Prefix fires the
    /// supplied callback with `Yes` immediately and skips the picker setup. Gated
    /// to mod-issued rooms only (ranked_*, team_*, sct-*) — vanilla casual /
    /// private rooms still get the vanilla popup so non-mod opponents don't desync.</summary>
    [HarmonyPatch(typeof(PopUpHandler), "StartPicking")]
    class PopUpHandler_StartPicking_Competitive_Patch
    {
        static bool Prefix(global::Player player, Action<PopUpHandler.YesNo> functionToCall)
        {
            try
            {
                if (!CompetitiveRoomDetect.IsCompetitiveRoom()) return true;
                Plugin.Log.LogInfo("[POPUP] Auto-confirming Continue prompt (competitive room bypass)");
                try { functionToCall?.Invoke(PopUpHandler.YesNo.Yes); }
                catch (Exception ex) { Plugin.Log.LogError($"[POPUP] Continue auto-invoke failed: {ex.Message}"); }
                return false;  // skip vanilla picker setup entirely
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[POPUP] StartPicking prefix error: {ex.Message}");
                return true;
            }
        }
    }

    /// <summary>Sort the SpawnPoint[] array left-to-right by X position in cr_ff
    /// rooms. PlayerManager.MovePlayers indexes spawnPoints[i] for players[i],
    /// but the prefab child order isn't guaranteed to be left-then-right. With
    /// our slot mapping (slots 0/1 = team 0, slots 2/3 = team 1), sorting X
    /// ascending puts team 0 on the left half, team 1 on the right half — same
    /// layout as 1v1.</summary>
    [HarmonyPatch(typeof(MapManager), "GetSpawnPoints")]
    class MapManager_GetSpawnPoints_2v2_Patch
    {
        static void Postfix(ref SpawnPoint[] __result)
        {
            try
            {
                if (__result == null || __result.Length < 2) return;
                if (!Diag2v2.IsActive()) return;
                Array.Sort(__result, (a, b) =>
                    (a == null ? 0f : a.localStartPos.x).CompareTo(b == null ? 0f : b.localStartPos.x));
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[2v2] SpawnPoint sort failed: {ex.Message}"); }
        }
    }

    /// <summary>In cr_ff rooms, force teammates to share a team color. Vanilla
    /// PlayerSkinBank.GetPlayerSkinColors(playerID) returns a different skin
    /// per slot (orange/pink/blue/something), so 2v2 ends up with 4 visually
    /// distinct players. Map slot → team-base (slots 0,1 → 0; slots 2,3 → 2)
    /// so both team-0 players look orange and both team-1 players look blue.
    /// PlayerColorCosmetic's custom body-color override still applies on top.</summary>
    [HarmonyPatch(typeof(PlayerSkinBank), "GetPlayerSkinColors")]
    class PlayerSkinBank_GetPlayerSkinColors_2v2_Patch
    {
        // CRITICAL: the parameter MUST be named `team` to match vanilla's
        // signature — HarmonyX binds Prefix parameters by NAME. v1.25.10
        // shipped this with `playerID` which broke `PatchAll()` entirely.

        // Class names whose calls to GetPlayerSkinColors should map slot→team_skin
        // in 2v2. UI code (PointVisualizer, UIHandler) passes literal team-index
        // values (0 or 1) and shouldn't be mapped — that's what made the round
        // counter fill BOTH dots orange in v1.25.14 (team 1's `1` got mapped to
        // `0` and returned orange instead of blue).
        private static readonly System.Collections.Generic.HashSet<string> _bodyCallers =
            new System.Collections.Generic.HashSet<string>
        {
            "PlayerSkinHandler",   // body skin instantiate
            "Player",              // SetColors / GetTeamColors / SetCardLevelTeam
            "PlayerAssigner",      // initial body color setup
            "HealthHandler",       // hp sprite + death effect colors
            "CharacterData",       // any direct player-data path
            "Holdable",            // gun/block trail colors
            "DeathEffect",         // death particle colors
            "PlayerSkinParticle",  // body particle colors
            "DamageHandler",       // hit-blink / damage flash
            "CardChoiceVisuals",   // card-pick body skin
        };

        private static readonly System.Collections.Generic.HashSet<string> _loggedKeys =
            new System.Collections.Generic.HashSet<string>();
        private static float _lastClear;

        static void Prefix(ref int team)
        {
            try
            {
                if (!Diag2v2.IsActive()) return;
                if (team < 0 || team > 3) return;

                // Walk a few stack frames up to determine if this call is for a
                // player BODY (where we want slot→team_skin mapping) vs a UI
                // ELEMENT (where the input is already a team index). UI bypass
                // is what restores the round-counter blue fill.
                bool isBodyCaller = false;
                try
                {
                    var st = new System.Diagnostics.StackTrace(1, false);
                    int n = Math.Min(st.FrameCount, 6);
                    for (int i = 0; i < n; i++)
                    {
                        var m = st.GetFrame(i)?.GetMethod();
                        if (m == null) continue;
                        string typeName = m.DeclaringType?.Name ?? "";
                        if (_bodyCallers.Contains(typeName)) { isBodyCaller = true; break; }
                    }
                }
                catch { }
                if (!isBodyCaller) return;

                int original = team;
                team = Diag2v2.SlotToTeam(team);   // 2v2: slot/2 · 1v2: solo=0, duo=1

                if (Time.realtimeSinceStartup - _lastClear > 5f)
                {
                    _loggedKeys.Clear();
                    _lastClear = Time.realtimeSinceStartup;
                }
                string key = $"{original}→{team}";
                if (_loggedKeys.Add(key))
                    Plugin.Log.LogInfo($"[2v2-COLOR] body-call mapped {key}");
            }
            catch { }
        }
    }

    /// <summary>v1.28 — remote-player skin re-bake guard (the OTHER half of the
    /// both-orange bug). PlayerSkinHandler.Init reads data.player.PlayerID and
    /// bakes PlayerSkinBank.GetPlayerSkinColors(PlayerID). In a cr_ff room, if
    /// Init runs before the player's PlayerID is assigned (it defaults to 0),
    /// the body bakes with team-0's skin (orange) regardless of the real team.
    /// The existing CreatePlayer override re-bakes the LOCAL player, but REMOTE
    /// players have no equivalent — they rely on the ReadPlayerID→Start ordering,
    /// which races. This Postfix runs a deferred check on EVERY PlayerSkinHandler
    /// in a cr_ff room: a few frames after Init, if the player's PlayerID is now
    /// known and the baked skin doesn't match PlayerID/2's team, force a re-bake.
    /// Self-correcting for both local and remote, idempotent (only re-bakes on
    /// mismatch). Gated strictly to cr_ff so 1v1 / casual are untouched.</summary>
    [HarmonyPatch(typeof(PlayerSkinHandler), "Init")]
    class PlayerSkinHandlerInitRebakeGuard
    {
        static void Postfix(PlayerSkinHandler __instance)
        {
            try
            {
                if (!Diag2v2.IsActive()) return;
                if (__instance == null || Plugin.Instance == null) return;
                Plugin.Instance.StartCoroutine(VerifyAndRebake(__instance));
            }
            catch { }
        }

        private static System.Collections.IEnumerator VerifyAndRebake(PlayerSkinHandler psh)
        {
            // Let PlayerID assignment + the initial bake settle.
            for (int i = 0; i < 8; i++) yield return null;
            if (psh == null) yield break;
            int rebakes = 0;
            try
            {
                // Resolve this skin handler's owning player + PlayerID via reflection.
                var fData = typeof(PlayerSkinHandler).GetField("data",
                    BindingFlags.NonPublic | BindingFlags.Instance);
                var data = fData?.GetValue(psh);
                if (data == null) yield break;
                var pPlayer = data.GetType().GetField("player",
                    BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance)?.GetValue(data);
                if (pPlayer == null) yield break;
                var pidProp = pPlayer.GetType().GetProperty("PlayerID",
                    BindingFlags.Public | BindingFlags.Instance);
                if (pidProp == null) yield break;
                int playerID = (int)pidProp.GetValue(pPlayer);
                if (playerID < 0 || playerID > 3) yield break;

                // Expected team skin index after our GetPlayerSkinColors SlotToTeam
                // Prefix: the baked child should correspond to the slot's team.
                int expectedTeam = Diag2v2.SlotToTeam(playerID);
                // Heuristic for "baked wrong": the child skin GO carries no reliable
                // team marker, so instead we detect the known failure — a non-team-0
                // player (playerID >= 2, i.e. team 1) whose body still reads team-0
                // (orange) baseline. We re-bake whenever the player is team 1 but the
                // first body sprite's color is closer to team 0's color than team 1's.
                var sr = psh.GetComponentInChildren<SpriteRenderer>(true);
                if (sr == null) yield break;
                CardPickBodyTinter.EnsureTeamColors();
                Color c0 = CardPickBodyTinter.TeamColor0;
                Color c1 = CardPickBodyTinter.TeamColor1;
                Color want = (expectedTeam == 1) ? c1 : c0;
                Color other = (expectedTeam == 1) ? c0 : c1;
                float dWant = ColorDist(sr.color, want);
                float dOther = ColorDist(sr.color, other);
                // Only re-bake when the body clearly matches the WRONG team.
                if (dOther + 0.08f < dWant)
                {
                    var fInited = typeof(PlayerSkinHandler).GetField("inited",
                        BindingFlags.NonPublic | BindingFlags.Instance);
                    for (int i = psh.transform.childCount - 1; i >= 0; i--)
                    {
                        var ch = psh.transform.GetChild(i);
                        if (ch != null) UnityEngine.Object.Destroy(ch.gameObject);
                    }
                    fInited?.SetValue(psh, false);
                    var initMethod = typeof(PlayerSkinHandler).GetMethod("Init",
                        BindingFlags.NonPublic | BindingFlags.Instance);
                    initMethod?.Invoke(psh, null);
                    rebakes++;
                    Plugin.Log.LogInfo($"[2v2-COLOR] Re-baked skin for PlayerID={playerID} (expectedTeam={expectedTeam}, body matched wrong team)");
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[2v2-COLOR] rebake guard error: {ex.Message}"); }
        }

        private static float ColorDist(Color a, Color b)
        {
            float dr = a.r - b.r, dg = a.g - b.g, db = a.b - b.b;
            return (float)Math.Sqrt(dr * dr + dg * dg + db * db);
        }
    }

    /// <summary>MapManager.UnloadAfterSeconds was the original v1.25.4-era crash
    /// site (NRE on a missing PhotonView). Wrap to catch and log instead of
    /// letting the throw propagate into Photon's network restart path.</summary>
    [HarmonyPatch(typeof(MapManager), "UnloadAfterSeconds")]
    class MapManager_UnloadAfterSeconds_Diag_Patch
    {
        static Exception Finalizer(Exception __exception)
        {
            if (__exception != null && Diag2v2.IsActive())
            {
                try { Plugin.Log.LogError($"[2v2-DIAG] MapManager.UnloadAfterSeconds threw: {__exception.GetType().Name}: {__exception.Message}"); }
                catch { }
            }
            return __exception;  // rethrow normally — don't swallow
        }
    }

    /// <summary>
    /// July 22 item 3 — 1v2 Solo Extra Initial Pick. Vanilla's pick loop is
    /// natively multi-pick (StartPick sets `picks`; ReplaceCards re-deals while
    /// picks > 0, all driven on the PICKER's client only, so a flag mismatch
    /// can never stall the WaitForSyncUp barrier — remote clients just watch
    /// replicated card spawns until RPCA_DonePicking). We bump the SOLO
    /// player's INITIAL draw from 1 to 2 picks when the series has the toggle.
    /// Initial-draw discriminator: all four GM_ArmsRace score fields are 0
    /// (round picks always run after RPCA_NextRound incremented rounds; holds
    /// for same-room rematches too since ResetMatch zeroes scores first).
    /// Flag carrier: cr_ovt_xp ROOM prop (stamped by the room creator from the
    /// lock payload) with the local lock cache as fallback.
    /// FIRST-PLAYTEST-PENDING: vanilla online never passes picks>1, so the
    /// second ReplaceCards round-trip is unproven in the wild (learning #145).
    /// </summary>
    [HarmonyPatch(typeof(CardChoice), "StartPick")]
    class OvtExtraPickPatch
    {
        static void Prefix(ref int picksToSet, int pickerIDToSet)
        {
            try
            {
                if (picksToSet != 1) return;
                if (PhotonNetwork.OfflineMode || !PhotonNetwork.InRoom) return;
                string rn = PhotonNetwork.CurrentRoom?.Name ?? "";
                if (!rn.StartsWith("ovt_")) return;
                // Flag: room prop first, local lock cache as fallback.
                bool extra = false;
                var rp = PhotonNetwork.CurrentRoom.CustomProperties;
                if (rp != null && rp.ContainsKey("cr_ovt_xp"))
                    extra = rp["cr_ovt_xp"] is bool b ? b : rp["cr_ovt_xp"]?.ToString() == "True";
                else
                    extra = ApiClient.OvtSoloExtraPick;
                if (!extra) return;
                // Initial draw only: every score field still zero.
                var gm = GM_ArmsRace.instance;
                if (gm == null) return;
                if (gm.p1Points != 0 || gm.p2Points != 0 || gm.p1Rounds != 0 || gm.p2Rounds != 0) return;
                // Picker must be the SOLO side = the ROUNDS team with exactly
                // one player (same detection TryReportOvtMatch trusts).
                var picker = PlayerManager.instance?.GetPlayerWithID(pickerIDToSet);
                if (picker == null) return;
                int teamSize = 0;
                foreach (var po in PlayerManager.instance.players)
                    if (po != null && po.TeamID == picker.TeamID) teamSize++;
                if (teamSize != 1) return;
                picksToSet = 2;
                Plugin.Log.LogInfo($"[1v2-EXTRAPICK] solo picker {pickerIDToSet} (team {picker.TeamID}) gets 2 initial picks");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[1v2-EXTRAPICK] prefix failed: {ex.Message}");
            }
        }
    }

    /// <summary>
    /// Hooks CardChoice.Pick to capture LOCAL card picks with full CardInfo.
    /// Pick only fires for the local player's selection.
    /// Used to confirm local picks and extract rarity data.
    /// </summary>
    [HarmonyPatch(typeof(CardChoice), "Pick")]
    class CardChoicePickPatch
    {
        static void Prefix(GameObject pickedCard, bool clear)
        {
            try
            {
                if (pickedCard == null) return;

                CardInfo cardInfo = pickedCard.GetComponent<CardInfo>();
                if (cardInfo == null)
                    cardInfo = pickedCard.GetComponentInChildren<CardInfo>();
                if (cardInfo == null) return;

                string cardName = null;
                try
                {
                    var flags = System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance;
                    var nameField = typeof(CardInfo).GetField("cardName", flags);
                    if (nameField != null)
                        cardName = nameField.GetValue(cardInfo) as string;
                }
                catch { }

                if (string.IsNullOrEmpty(cardName))
                    cardName = pickedCard.name.Replace("(Clone)", "").Trim();

                if (string.IsNullOrEmpty(cardName)) return;

                int pickerID = -1;
                try { pickerID = CardChoice.instance.pickrID; } catch { }

                Plugin.Log.LogInfo($"[HARMONY-CARD] Local Pick: card={cardName}, pickerID={pickerID}");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[HARMONY-CARD] Pick hook error: {ex.Message}");
            }
        }
    }

    /// <summary>
    /// Hooks CardChoice.RPCA_DoEndPick — the Photon RPC that fires on ALL clients
    /// for ALL player card picks (local AND opponent).
    /// 
    /// Verified from diagnostics:
    ///   pickId = player index (0 or 1), matches localTeam
    ///   targetCardID = Photon ViewID of the picked card GameObject
    ///   theInt = card position in the pick UI (not player-related)
    /// </summary>
    [HarmonyPatch(typeof(CardChoice), "RPCA_DoEndPick")]
    class CardChoiceEndPickPatch
    {
        // Buffer for picks that arrive before localTeam is resolved
        private static List<PendingPick> pendingPicks = new List<PendingPick>();

        private struct PendingPick
        {
            public string CardName;
            public string Rarity;
            public int PickId;
        }

        /// <summary>
        /// Called by GameStateWatcher once localTeam is known.
        /// Flushes any buffered picks that were opponent cards.
        /// </summary>
        public static void FlushPendingPicks(int localTeam)
        {
            if (pendingPicks.Count == 0) return;

            foreach (var pick in pendingPicks)
            {
                if (pick.PickId != localTeam && !string.IsNullOrEmpty(pick.CardName))
                {
                    Plugin.Log.LogInfo($"[HARMONY-CARD] Flushing pre-match opp card: {pick.CardName} ({pick.Rarity})");
                    GameStateWatcher.OnOpponentCardPicked(pick.CardName, pick.Rarity);
                }
            }
            pendingPicks.Clear();
        }

        public static void ClearPending()
        {
            pendingPicks.Clear();
        }

        static void Prefix(int[] cardIDs, int targetCardID, int theInt, int pickId)
        {
            try
            {
                // Instinct (bug #60): the scroll tracker alone can miss a pick
                // (stale CurrentPickerIsLocal, RPC ordering), so also verify the
                // card actually TAKEN. theInt is the pick-UI slot index, 0 =
                // left-most. Resolve "is this my pick" via the player's own
                // PhotonView instead of localTeam so pre-match picks (localTeam
                // not yet resolved) are covered too.
                try
                {
                    if (theInt != 0 && CompetitiveRoomDetect.IsCompetitiveRoom())
                    {
                        var pkr = PlayerManager.instance != null ? PlayerManager.instance.GetPlayerWithID(pickId) : null;
                        if (pkr != null && pkr.data != null && pkr.data.view != null && pkr.data.view.IsMine
                            && !GameStateWatcher.achLeftmostViolated)
                        {
                            GameStateWatcher.achLeftmostViolated = true;
                            Plugin.Log.LogInfo($"[ACH] Instinct run broken — took card slot {theInt} (not the left-most)");
                        }
                    }
                }
                catch { }

                int localTeam = GameStateWatcher.LocalTeamId;

                // Resolve card name via Photon ViewID
                string cardName = null;
                string rarity = "Unknown";

                try
                {
                    var photonView = PhotonView.Find(targetCardID);
                    if (photonView != null)
                    {
                        var cardInfo = photonView.GetComponent<CardInfo>();
                        if (cardInfo == null)
                            cardInfo = photonView.GetComponentInChildren<CardInfo>();

                        if (cardInfo != null)
                        {
                            var flags = System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance;
                            var nameField = typeof(CardInfo).GetField("cardName", flags);
                            if (nameField != null)
                                cardName = nameField.GetValue(cardInfo) as string;

                            var rarityField = typeof(CardInfo).GetField("rarity", flags);
                            if (rarityField != null)
                            {
                                var rarVal = rarityField.GetValue(cardInfo);
                                rarity = rarVal?.ToString() ?? "Unknown";
                            }
                        }

                        if (string.IsNullOrEmpty(cardName))
                            cardName = photonView.gameObject.name.Replace("(Clone)", "").Trim();
                    }
                }
                catch { }

                // Canonicalize before anything downstream consumes it. The cardInfo.cardName
                // field and GameObject name can diverge (e.g. "Poison" vs "Poison Bullets",
                // "Prisitne Perseverence" vs "Pristine Perseverence") — without this, match
                // reports leak the non-canonical form and split the card in stats.
                if (!string.IsNullOrEmpty(cardName))
                    cardName = CardRarityLookup.GetCanonicalName(cardName);

                if (!string.IsNullOrEmpty(cardName) && rarity == "Unknown")
                    rarity = CardRarityLookup.GetRarity(cardName);

                // If localTeam not yet resolved, buffer the pick for later
                if (localTeam < 0)
                {
                    if (!string.IsNullOrEmpty(cardName))
                    {
                        pendingPicks.Add(new PendingPick { CardName = cardName, Rarity = rarity, PickId = pickId });
                        Plugin.Log.LogInfo($"[HARMONY-CARD] Buffered pick: card={cardName}, pickId={pickId} (localTeam unknown)");
                    }
                    return;
                }

                bool isOpponent = (pickId != localTeam);
                Plugin.Log.LogInfo($"[HARMONY-CARD] EndPick: card={cardName ?? "(unresolved)"}, pickId(player)={pickId}, localTeam={localTeam}, isOpp={isOpponent}");

                if (isOpponent && !string.IsNullOrEmpty(cardName))
                {
                    Plugin.Log.LogInfo($"[HARMONY-CARD] Opponent picked: {cardName} ({rarity})");
                    GameStateWatcher.OnOpponentCardPicked(cardName, rarity);
                }

                // Pass-tracking: if LOCAL was the picker, capture every card on offer.
                // cardIDs[] is the full set shown in the pick UI; targetCardID is the chosen one.
                if (!isOpponent && cardIDs != null && cardIDs.Length > 0)
                {
                    int round = GameStateWatcher.CurrentRound;
                    int localOffersSnapshot = GameStateWatcher.LocalOffersCount;
                    var bflags = System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance;
                    var cnField = typeof(CardInfo).GetField("cardName", bflags);
                    foreach (int cid in cardIDs)
                    {
                        try
                        {
                            var pv = PhotonView.Find(cid);
                            if (pv == null) continue;
                            string cn = null;
                            var ci = pv.GetComponent<CardInfo>();
                            if (ci == null) ci = pv.GetComponentInChildren<CardInfo>();
                            if (ci != null && cnField != null)
                                cn = cnField.GetValue(ci) as string;
                            if (string.IsNullOrEmpty(cn))
                                cn = pv.gameObject.name.Replace("(Clone)", "").Trim();
                            cn = CardRarityLookup.GetCanonicalName(cn);
                            if (string.IsNullOrEmpty(cn)) continue;
                            bool wasPicked = cid == targetCardID;
                            GameStateWatcher.OnLocalCardOffered(cn, wasPicked, round);
                            if (wasPicked)
                                Plugin.Log.LogInfo($"[HARMONY-CARD] offer marked picked: card={cn} cid={cid} target={targetCardID} round={round}");
                        }
                        catch (Exception ex)
                        {
                            Plugin.Log.LogWarning($"[HARMONY-CARD] offer loop error on cid={cid}: {ex.Message}");
                        }
                    }
                    // Safety net: if none of the cardIDs[] entries resolved to a "picked"
                    // offer (PhotonView.Find returned null for all, or targetCardID wasn't
                    // present in the array — e.g. reroll / special card paths), manually add
                    // one was_picked=true offer so pass_rate doesn't stay at 100%. The
                    // fallback uses whatever card name GameStateWatcher already captured from
                    // the Unity log "Picking Card:" line for this round, which is the
                    // canonical source of truth for "what did the local player actually take."
                    int newOffers = GameStateWatcher.LocalOffersCount - localOffersSnapshot;
                    bool anyPickedRecorded = GameStateWatcher.LocalOffersPickedIn(localOffersSnapshot);
                    if (!anyPickedRecorded)
                    {
                        string fallbackName = GameStateWatcher.LastLocalPickedCardName;
                        if (!string.IsNullOrEmpty(fallbackName))
                        {
                            GameStateWatcher.OnLocalCardOffered(fallbackName, true, round);
                            Plugin.Log.LogInfo($"[HARMONY-CARD] offer fallback picked: card={fallbackName} round={round} (newOffers={newOffers}, no picked row in cardIDs[])");
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[HARMONY-CARD] EndPick error: {ex.Message}");
            }
        }
    }

    /// <summary>
    /// Injects a "COMPETITIVE" button into the main menu's ListMenu.
    /// Runs from Update() — checks once per scene if injection is needed.
    /// </summary>
    public static class MainMenuInjector
    {
        private static bool injected = false;
        private static float checkTimer = 0f;
        private static GameObject injectedButton = null;
        private static int retryCount = 0;
        private static int maxRetries = 30; // 30 seconds of trying — enough for slow scene loads
        private static bool loggedFirstInjection = false; // Suppress verbose re-injection logs, not warnings
        private static bool wasInRoomLastCheck = false;   // detect room-exit → fresh retry budget
        private static bool loggedBudgetExhausted = false;

        /// <summary>
        /// Resets injector state — called when persistent object respawns
        /// so the button gets re-injected on the new scene.
        /// </summary>
        public static void Reset()
        {
            injected = false;
            injectedButton = null;
            retryCount = 0;
            // Keep loggedFirstInjection to avoid re-logging verbose info
        }

        public static void TryInject()
        {
            // Don't spam checks — once per second
            checkTimer += Time.deltaTime;
            if (checkTimer < 1f) return;
            checkTimer = 0f;

            // Only inject when not in a Photon room (i.e., on main menu). This
            // check MUST come before the retry accounting: the old order burned
            // the whole 30-try budget at 1/sec while the player was mid-match
            // (button destroyed on room join → injected=false → tick, tick,
            // tick...), so after any game longer than 30s the button never came
            // back for the rest of the session (bug #27, "menu item always
            // disappears after a few games"). In-room ticks are free now, and
            // leaving a room refreshes the budget.
            bool inRoomNow = false;
            try { inRoomNow = Photon.Pun.PhotonNetwork.InRoom; } catch { }
            if (inRoomNow)
            {
                wasInRoomLastCheck = true;
                return;
            }
            if (wasInRoomLastCheck)
            {
                wasInRoomLastCheck = false;
                retryCount = 0;          // fresh budget back at the menu
                loggedBudgetExhausted = false;
            }

            // Already injected and button still exists
            if (injected && injectedButton != null) return;

            // Button was destroyed (scene change) — allow re-injection
            if (injected && injectedButton == null)
            {
                injected = false;
                retryCount = 0;
                // Don't re-log on re-injection — already logged once
            }

            // After the budget, don't stop forever — degrade to a slow retry
            // (every ~10s) as a self-healing failsafe. A menu that exists but
            // briefly lacked its QUIT button (mid-rebuild) used to strand us.
            if (retryCount >= maxRetries)
            {
                if (!loggedBudgetExhausted)
                {
                    loggedBudgetExhausted = true;
                    Plugin.Log.LogWarning($"[MENU] Injection still failing after {maxRetries} attempts — dropping to slow retry (10s)");
                }
                if (retryCount % 10 != 0) { retryCount++; return; }
            }
            retryCount++;

            try
            {
                DoInject();
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[MENU] Injection failed: {ex.Message}");
            }
        }

        private static System.Type cachedTmpType = null;

        private static void DoInject()
        {
            // Cache TMP_Text type for text reading
            if (cachedTmpType == null)
            {
                foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                {
                    cachedTmpType = asm.GetType("TMPro.TMP_Text");
                    if (cachedTmpType != null) break;
                }
                if (cachedTmpType == null)
                {
                    Plugin.Log.LogWarning("[MENU] TMPro.TMP_Text not found");
                    return;
                }
            }

            var textProp = cachedTmpType.GetProperty("text",
                System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
            if (textProp == null) return;

            // Find ALL ListMenuButtons in the scene
            var allButtons = UnityEngine.Object.FindObjectsOfType<ListMenuButton>();
            if (allButtons == null || allButtons.Length == 0) return;

            // Find a main menu button by checking TMP text for known labels
            ListMenuButton quitButton = null;
            foreach (var btn in allButtons)
            {
                try
                {
                    var tmpComp = btn.GetComponentInChildren(cachedTmpType, true);
                    if (tmpComp == null) continue;
                    string text = (textProp.GetValue(tmpComp) as string ?? "").Trim().ToUpper();
                    if (text == "QUIT")
                    {
                        quitButton = btn;
                        break;
                    }
                }
                catch { }
            }

            if (quitButton == null)
            {
                // Only warn once per injection cycle
                if (!loggedFirstInjection)
                    Plugin.Log.LogWarning("[MENU] Could not find QUIT button in main menu");
                return;
            }

            Transform templateTransform = quitButton.transform;
            Transform container = templateTransform.parent;

            // Only log first injection
            if (!loggedFirstInjection)
                Plugin.Log.LogInfo($"[MENU] Found QUIT button at {templateTransform.name}, parent: {container.name}");

            // Clone the QUIT button
            var clone = UnityEngine.Object.Instantiate(templateTransform.gameObject, container);
            clone.name = "CompetitiveRoundsButton";

            // Insert above QUIT — layout group will handle spacing automatically
            clone.transform.SetSiblingIndex(templateTransform.GetSiblingIndex());

            // Change the text (short label for the menu)
            bool textSet = false;
            try
            {
                var tmpComponent = clone.GetComponentInChildren(cachedTmpType);
                if (tmpComponent != null)
                {
                    textProp.SetValue(tmpComponent, "SID'S COMPETITIVE ROUNDS");
                    textSet = true;
                }
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[MENU] TMP text change failed: {ex.Message}");
            }

            if (!textSet)
                Plugin.Log.LogWarning("[MENU] Could not set button text");

            // ── FIX: Keep ListMenuButton for hover highlight ──
            // ListMenuButton is purely visual — it handles text color, hover bar animation,
            // font sizing. It has NO page/action fields (verified from Assembly-CSharp.dll).
            // The actual click behavior comes from QuitButton, GoBack, and Button.onClick,
            // which we remove/override below. Keeping ListMenuButton = orange hover bar works!

            // CRITICAL: Remove QuitButton component — without this, clicking quits the game
            try
            {
                var quitComp = clone.GetComponent<QuitButton>();
                if (quitComp != null)
                    UnityEngine.Object.Destroy(quitComp);
            }
            catch { }

            // Also remove GoBack if present
            try
            {
                var goBack = clone.GetComponent<GoBack>();
                if (goBack != null)
                    UnityEngine.Object.Destroy(goBack);
            }
            catch { }

            // Add our click handler component
            clone.AddComponent<CompetitiveMenuButton>();

            injectedButton = clone;
            injected = true;
            if (!loggedFirstInjection)
            {
                Plugin.Log.LogInfo("[MENU] Competitive button injected into main menu!");
                loggedFirstInjection = true;
            }
        }
    }

    /// <summary>
    /// Simple MonoBehaviour attached to the injected menu button.
    /// Detects pointer clicks and opens the overlay.
    /// </summary>
    public class CompetitiveMenuButton : MonoBehaviour
    {
        private const string BUTTON_TEXT = "SID'S COMPETITIVE ROUNDS";
        private object cachedTmpComponent = null;
        private System.Reflection.PropertyInfo cachedTextProp = null;
        private bool textEnforcementReady = false;

        private void Start()
        {
            // Cache the TMP component and text property for text enforcement
            CacheTmpReferences();

            // Try to wire into the Unity Button onClick via reflection
            try
            {
                System.Type buttonType = null;
                foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                {
                    buttonType = asm.GetType("UnityEngine.UI.Button");
                    if (buttonType != null) break;
                }

                if (buttonType != null)
                {
                    var btn = GetComponent(buttonType);
                    if (btn != null)
                    {
                        // Clear existing listeners
                        var onClickProp = buttonType.GetProperty("onClick",
                            System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
                        if (onClickProp != null)
                        {
                            var onClick = onClickProp.GetValue(btn);
                            // RemoveAllListeners
                            var removeAll = onClick.GetType().GetMethod("RemoveAllListeners");
                            if (removeAll != null) removeAll.Invoke(onClick, null);

                            // AddListener with our action
                            var addListener = onClick.GetType().GetMethod("AddListener");
                            if (addListener != null)
                            {
                                var action = (UnityEngine.Events.UnityAction)OnButtonClick;
                                addListener.Invoke(onClick, new object[] { action });
                                Plugin.Log.LogInfo("[MENU] Button onClick wired successfully");
                            }
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[MENU] Button wiring failed: {ex.Message}");
            }
        }

        private void CacheTmpReferences()
        {
            try
            {
                System.Type tmpType = null;
                foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                {
                    tmpType = asm.GetType("TMPro.TMP_Text");
                    if (tmpType != null) break;
                }
                if (tmpType == null) return;

                cachedTmpComponent = GetComponentInChildren(tmpType);
                if (cachedTmpComponent == null) return;

                cachedTextProp = tmpType.GetProperty("text",
                    System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);

                textEnforcementReady = (cachedTextProp != null);
            }
            catch { }
        }

        /// <summary>
        /// ROUNDS' ListMenuButton re-initializes after submenu navigation and resets
        /// the TMP text back to "QUIT". LateUpdate catches this and re-applies our text.
        /// </summary>
        private void LateUpdate()
        {
            if (!textEnforcementReady) return;

            try
            {
                string current = cachedTextProp.GetValue(cachedTmpComponent) as string;
                if (current != BUTTON_TEXT)
                {
                    cachedTextProp.SetValue(cachedTmpComponent, BUTTON_TEXT);
                }
            }
            catch { }
        }

        private void OnButtonClick()
        {
            Plugin.Log.LogInfo("[MENU] Competitive button clicked!");
            CompetitiveUI.ToggleOverlay();
        }
    }

    /// <summary>
    /// Static lookup table for card name → rarity.
    /// Built by Harmony hook on GM_ArmsRace.Awake.
    /// </summary>
    public static class CardRarityLookup
    {
        private static readonly Dictionary<string, string> lookup = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        private static readonly Dictionary<string, string> canonical = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);

        // Known mismatches between GameObject name (log capture) and cardName field.
        // Maps input (either form) → canonical card name used in the DB. Dictionary is
        // OrdinalIgnoreCase so "abyssalcountdown" finds the same entry as "AbyssalCountdown",
        // but both forms must still route through GetCanonicalName() to be normalized —
        // several paths historically skipped the call (fixed one more in this pass:
        // OnOpponentCardPicked). Entries cover every ROUNDS rename / typo / CamelCase
        // compression we've observed producing near-duplicates in the DB.
        private static readonly Dictionary<string, string> hardAliases = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            // Letter typos
            { "Leach", "Leech" },
            { "Riccochet", "Ricochet" },
            // CamelCase / no-space GameObject-name variants → spaced display-name canonical
            { "BombsAway", "Bombs Away" },
            { "Glasscannon", "Glass Cannon" },
            { "ShieldCharge", "Shield Charge" },
            { "AbyssalCountdown", "Abyssal Countdown" },
            { "ChillingPresence", "Chilling Presence" },
            { "DrillAmmo", "Drill Ammo" },
            { "RadarShot", "Radar Shot" },
            { "TargetBounce", "Target Bounce" },
            { "TasteOfBlood", "Taste Of Blood" },
            { "Fastball", "Fast Ball" },
            // "Poison Bullets" was the old pre-rename name for what ROUNDS now displays as
            // just "Poison" — reverse the previous alias so every variant canonicalizes to
            // the in-game display (migration 043 merged historical rows).
            { "Poison Bullets", "Poison" },
            { "PoisonBullets",  "Poison" },
            // Pristine Perseverance had two independent typos accumulating: the previous
            // canonical was itself misspelled ("Perseverence"), and at least one code path
            // missed the alias and wrote both typos raw ("Prisitne Perseverence"). Canonical
            // is now the correct in-game spelling; aliases below cover every observed typo.
            { "Prisitne Perseverence", "Pristine Perseverance" },
            { "Pristine Perseverence", "Pristine Perseverance" },
            { "PristinePerseverance", "Pristine Perseverance" },
            { "PristinePerseverence", "Pristine Perseverance" },
        };

        public static void Register(string cardName, string rarity)
        {
            if (!string.IsNullOrEmpty(cardName))
            {
                lookup[cardName] = rarity;
                if (!canonical.ContainsKey(cardName))
                    canonical[cardName] = cardName;
            }
        }

        public static string GetRarity(string cardName)
        {
            if (string.IsNullOrEmpty(cardName)) return "Unknown";
            if (lookup.TryGetValue(cardName, out string rarity))
                return rarity;
            // Try alias
            string norm = GetCanonicalName(cardName);
            if (norm != cardName && lookup.TryGetValue(norm, out rarity))
                return rarity;
            return "Unknown";
        }

        /// <summary>
        /// Maps a log-captured card name to the canonical CardInfo name.
        /// Returns title-cased canonical name for display.
        /// </summary>
        public static string GetCanonicalName(string name)
        {
            if (string.IsNullOrEmpty(name)) return name;
            // Hard alias first
            if (hardAliases.TryGetValue(name, out string alias))
                name = alias;
            // Canonical map (populated during ScanAll)
            if (canonical.TryGetValue(name, out string canon))
                return ToTitleCase(canon);
            return name;
        }

        private static string ToTitleCase(string input)
        {
            if (string.IsNullOrEmpty(input)) return input;
            var words = input.ToLower().Split(' ');
            for (int i = 0; i < words.Length; i++)
                if (words[i].Length > 0)
                    words[i] = char.ToUpper(words[i][0]) + words[i].Substring(1);
            return string.Join(" ", words);
        }

        public static int Count => lookup.Count;

        /// <summary>
        /// Scan all CardInfo objects in the scene and build the rarity lookup.
        /// Registers BOTH the cardName field and the GameObject name as lookup keys,
        /// mapping both to the canonical cardName.
        /// </summary>
        public static void ScanAll()
        {
            if (lookup.Count > 0) return; // Already populated

            try
            {
                var cardInfoType = typeof(CardInfo);
                var flags = System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance;

                var nameField = cardInfoType.GetField("cardName", flags);
                var rarityField = cardInfoType.GetField("rarity", flags);
                var nameProp = cardInfoType.GetProperty("CardName", flags);

                var allCards = Resources.FindObjectsOfTypeAll<CardInfo>();

                foreach (var ci in allCards)
                {
                    try
                    {
                        string cardName = null;
                        if (nameField != null)
                            cardName = nameField.GetValue(ci) as string;
                        else if (nameProp != null)
                            cardName = nameProp.GetValue(ci) as string;

                        if (string.IsNullOrEmpty(cardName))
                            cardName = ci.gameObject.name.Replace("(Clone)", "").Trim();

                        if (string.IsNullOrEmpty(cardName)) continue;

                        string rarity = "Unknown";
                        if (rarityField != null)
                        {
                            var rarVal = rarityField.GetValue(ci);
                            rarity = rarVal?.ToString() ?? "Unknown";
                        }

                        // Register canonical cardName
                        Register(cardName, rarity);

                        // Also register by GameObject name (log capture uses this)
                        string goName = ci.gameObject.name.Replace("(Clone)", "").Trim();
                        if (!string.IsNullOrEmpty(goName))
                        {
                            lookup[goName] = rarity;
                            canonical[goName] = cardName; // maps GO name → canonical
                        }
                    }
                    catch { }
                }

                // Register hard aliases
                foreach (var kvp in hardAliases)
                {
                    if (lookup.TryGetValue(kvp.Value, out string r))
                    {
                        lookup[kvp.Key] = r;
                        canonical[kvp.Key] = kvp.Value;
                    }
                }

                if (lookup.Count > 0)
                    Plugin.Log.LogInfo($"[RARITY] Card rarity lookup built: {lookup.Count} entries ({allCards.Length} CardInfo objects scanned)");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[RARITY] Card scan failed: {ex.Message}");
            }
        }

        public static string GetSampleEntries(int max)
        {
            var samples = new List<string>();
            int i = 0;
            foreach (var kvp in lookup)
            {
                samples.Add($"{kvp.Key}={kvp.Value}");
                if (++i >= max) break;
            }
            return string.Join(", ", samples.ToArray());
        }
    }

    /// <summary>
    /// Flashes the ROUNDS taskbar icon when the window is not focused.
    /// Used for ranked match found notifications when alt-tabbed.
    /// Based on code contributed by lopidav.
    /// </summary>
    public class TaskbarFlash : MonoBehaviour
    {
        private const uint FLASHW_STOP = 0;
        private const uint FLASHW_ALL = 3;
        private const uint FLASHW_TIMERNOFG = 12;

        [StructLayout(LayoutKind.Sequential)]
        private struct FLASHWINFO
        {
            public uint cbSize;
            public IntPtr hwnd;
            public uint dwFlags;
            public uint uCount;
            public uint dwTimeout;
        }

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool FlashWindowEx(ref FLASHWINFO pwfi);

        [DllImport("user32.dll")]
        private static extern IntPtr FindWindow(string lpClassName, string lpWindowName);

        private bool shouldFlash = false;
        private bool isFlashing = false;
        private IntPtr gameWindowHandle = IntPtr.Zero;

        private static TaskbarFlash instance;

        private void Awake()
        {
            if (instance != null && instance != this)
            {
                Destroy(gameObject);
                return;
            }
            instance = this;
        }

        private void Update()
        {
            // Resolve window handle (try multiple methods)
            if (gameWindowHandle == IntPtr.Zero)
            {
                try
                {
                    gameWindowHandle = Process.GetCurrentProcess().MainWindowHandle;
                }
                catch { }

                // Fallback: find Unity window by class name
                if (gameWindowHandle == IntPtr.Zero)
                {
                    try { gameWindowHandle = FindWindow("UnityWndClass", null); } catch { }
                }

                if (gameWindowHandle == IntPtr.Zero) return;
                Plugin.Log.LogInfo($"[FLASH] Window handle resolved: {gameWindowHandle}");
            }

            // Use Unity's own focus detection — more reliable than Win32 GetForegroundWindow
            bool isWindowInFocus = Application.isFocused;

            if (shouldFlash && !isFlashing && !isWindowInFocus)
                StartFlashing();

            if (shouldFlash && isWindowInFocus)
                shouldFlash = false;

            if (isFlashing && (!shouldFlash || isWindowInFocus))
                StopFlashing();
        }

        /// <summary>Call this to trigger a taskbar flash (only flashes if window is not focused).</summary>
        public static void Flash()
        {
            if (instance != null)
            {
                instance.shouldFlash = true;
                Plugin.Log.LogInfo($"[FLASH] Flash requested (focused={Application.isFocused}, handle={instance.gameWindowHandle})");
            }
            else
            {
                Plugin.Log.LogWarning("[FLASH] Flash requested but no instance");
            }
        }

        private void StartFlashing()
        {
            if (isFlashing) return;
            FLASHWINFO fInfo = new FLASHWINFO();
            fInfo.cbSize = (uint)Marshal.SizeOf(fInfo);
            fInfo.hwnd = gameWindowHandle;
            fInfo.dwFlags = FLASHW_ALL | FLASHW_TIMERNOFG;
            fInfo.uCount = uint.MaxValue;
            fInfo.dwTimeout = 0;
            bool result = FlashWindowEx(ref fInfo);
            isFlashing = true;
            shouldFlash = true;
            Plugin.Log.LogInfo($"[FLASH] Started flashing (result={result})");
        }

        private void StopFlashing()
        {
            if (!isFlashing) return;
            FLASHWINFO fInfo = new FLASHWINFO();
            fInfo.cbSize = (uint)Marshal.SizeOf(fInfo);
            fInfo.hwnd = gameWindowHandle;
            fInfo.dwFlags = FLASHW_STOP;
            fInfo.uCount = 0;
            fInfo.dwTimeout = 0;
            FlashWindowEx(ref fInfo);
            isFlashing = false;
            shouldFlash = false;
        }
    }

    // ── F5 click-block: stop the LOCAL player from shooting/blocking while the
    //    competitive menu is open. Without this, clicks on Settings buttons fire
    //    the gun in the game world too. uGUI raycast blockers don't help because
    //    Gun.Attack/Block.TryBlock are called from gameplay code reading Input directly.
    //    Only the LOCAL player is gated (PhotonView.IsMine) so opponent shots still render.

    [HarmonyPatch(typeof(Gun), "Attack")]
    class GunAttackBlockOnF5Patch
    {
        static bool Prefix(Gun __instance)
        {
            if (!NativeUI.IsOpen) return true;
            try
            {
                var pv = __instance != null ? __instance.GetComponentInParent<PhotonView>() : null;
                if (pv == null || !pv.IsMine) return true;  // never block opponents — only the local player
            }
            catch { return true; }
            return false;  // skip the original Attack — local shot suppressed while F5 is open
        }

        // Counter Postfix lives in the same class so Harmony resolves it to exactly the
        // Attack overload the Prefix already works on (the one that fires on every user
        // click). Earlier standalone patch classes using TargetMethod picked the wrong
        // overload and fired once per session.
        private static bool _postfixFirstFireLogged;
        private static bool _postfixFirstPvRejectLogged;
        private static bool _postfixFirstIsMineRejectLogged;
        private static bool _postfixFirstFalseRejectLogged;
        private static bool _postfixFirstForcedRejectLogged;
        static void Postfix(Gun __instance, bool __result, float charge, bool forceAttack)
        {
            if (!_postfixFirstFireLogged)
            {
                _postfixFirstFireLogged = true;
                Plugin.Log.LogInfo($"[GUN-POST] Attack Postfix first invocation (gun={__instance?.name}, uiOpen={NativeUI.IsOpen})");
            }
            if (NativeUI.IsOpen) return;  // Prefix blocked this shot, don't credit it
            // Attack returns false when no volley launched (cooldown/reload) — the
            // auto-fire branch retries every frame through a reload, so counting
            // false returns inflated bullets_fired by hundreds per match (bug #77 era).
            if (!__result)
            {
                if (!_postfixFirstFalseRejectLogged) { _postfixFirstFalseRejectLogged = true; Plugin.Log.LogInfo("[GUN-POST] first __result=false reject (reload/cooldown phantom)"); }
                return;
            }
            // forceAttack=true is never a player trigger pull: EMP block-rings,
            // RadarShot auto-shots and spawned shooters all force. Only deliberate
            // shots count toward accuracy (Sid: EMP projectiles aren't "shots").
            if (forceAttack)
            {
                if (!_postfixFirstForcedRejectLogged) { _postfixFirstForcedRejectLogged = true; Plugin.Log.LogInfo("[GUN-POST] first forceAttack reject (card-driven attack)"); }
                return;
            }
            try
            {
                // ROUNDS' Gun GameObject hierarchy ("WeaponBase(Clone)") doesn't walk up to a
                // PhotonView — logs confirmed GetComponentInParent<PhotonView>() returns null
                // for every user shot. The reliable path is Gun.player → the Player component
                // whose PhotonView represents the match ownership. Fall back to the hierarchy
                // lookup if the Gun.player ref is somehow null.
                PhotonView pv = null;
                try
                {
                    var gunPlayer = __instance?.player;
                    if (gunPlayer != null)
                        pv = gunPlayer.data?.view ?? gunPlayer.GetComponent<PhotonView>();
                }
                catch { }
                if (pv == null) pv = __instance?.GetComponentInParent<PhotonView>();

                if (pv == null)
                {
                    if (!_postfixFirstPvRejectLogged) { _postfixFirstPvRejectLogged = true; Plugin.Log.LogInfo($"[GUN-POST] first pv-null reject on gun={__instance?.name}"); }
                    return;
                }
                if (!pv.IsMine)
                {
                    if (!_postfixFirstIsMineRejectLogged) { _postfixFirstIsMineRejectLogged = true; Plugin.Log.LogInfo($"[GUN-POST] first !IsMine reject (pv.owner={pv.Owner?.NickName})"); }
                    return;
                }
                int projectiles = 1;
                try { projectiles = Math.Max(1, __instance.numberOfProjectiles); } catch { }
                // Real bullets per successful Attack = attacks (charge volleys) x bursts x
                // projectiles — vanilla FireBurst spawns all of them and each can register
                // a hit, so the denominator must match or Burst/charge builds inflate hit%.
                try
                {
                    int bursts = Math.Max(1, __instance.bursts);
                    int attacks = 1;
                    if (!__instance.lockGunToDefault && charge > 0f && __instance.attackSpeed > 0f)
                        attacks = Mathf.Clamp(Mathf.RoundToInt(0.5f * charge / __instance.attackSpeed), 1, 10);
                    projectiles *= bursts * attacks;
                }
                catch { }
                GameStateWatcher.OnLocalBulletFired(projectiles);
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[GUN-POST] exception: {ex.Message}"); }
        }
    }

    [HarmonyPatch(typeof(Block), "TryBlock")]
    class BlockTryBlockOnF5Patch
    {
        static bool Prefix(Block __instance)
        {
            if (!NativeUI.IsOpen) return true;
            try
            {
                var pv = __instance != null ? __instance.GetComponentInParent<PhotonView>() : null;
                if (pv == null || !pv.IsMine) return true;
            }
            catch { return true; }
            return false;
        }
    }

    // ── Hit % / Block % tracking (v1.23) ───────────────────────────────────
    //
    // Separate patches from the F5 input-gate above because the gate short-circuits the
    // original with `return false` when F5 is open, and we must NOT count suppressed
    // actions. Harmony Postfixes run even after a false Prefix, so each counting patch
    // checks NativeUI.IsOpen and bails.
    //
    // Only the LOCAL player is tracked (PhotonView.IsMine on the Gun / Block / target).
    // See learnings.md #4: only the lower Steam ID reports matches, so these counters
    // accumulate on whichever side reports. The backend stores them on the reporter.

    // Gun.Attack patch removed — TargetMethod(most-params) attached to an overload that's
    // only called from internal code paths (once per session per the logs), not from user
    // clicks. The F5-block patch uses `[HarmonyPatch(typeof(Gun), "Attack")]` without args
    // and works, but layering a Postfix under that attribute on a different patch class
    // disambiguates to potentially-different overloads and was unreliable in testing.
    // Instead, bullets_fired reuses the existing mouse-click counter (LocalShotsThisMatch)
    // which is driven by Input.GetMouseButtonDown(0) in GameStateWatcher — reliable, exactly
    // "one trigger pull per click", good enough semantically for Hit % on the leaderboard.
    // Each trigger pull is one "shot" even if the weapon is a shotgun — aligns with how
    // most players intuitively think about "my accuracy."

    [HarmonyPatch]
    class HealthHandlerTakeDamageCounterPatch
    {
        // HealthHandler.TakeDamage has multiple overloads in ROUNDS (a public canonical one
        // with 8 params and at least one shorter shim), which makes `[HarmonyPatch(typeof(X),
        // "TakeDamage")]` without explicit args throw "Ambiguous match" — that aborts the
        // entire PatchAll() call and nothing else in this assembly gets patched either.
        // Resolve the target ourselves by picking the overload with the most parameters,
        // which is the canonical damage path (damage, position, color, weapon, player, ...).
        static MethodBase TargetMethod()
        {
            var t = typeof(HealthHandler);
            MethodInfo best = null;
            int bestPc = -1;
            foreach (var m in t.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.NonPublic))
            {
                if (m.Name != "TakeDamage") continue;
                int pc = m.GetParameters().Length;
                if (pc > bestPc) { bestPc = pc; best = m; }
            }
            return best;
        }

        // FF-DIAG: in 2v2 rooms (cr_ff Photon room property = true), log when a teammate's
        // damage REACHES TakeDamage. If we see it: the team-filter is downstream of TakeDamage
        // (we'd patch HealthHandler.CallTakeDamage's bail-out). If we DON'T: filter is upstream
        // (in ProjectileCollision / MoveTransform). Opt-in with Block Debug and capped.
        private static int _ffDiagRemaining = 8;
        static void Postfix(HealthHandler __instance, Vector2 damage, GameObject damagingWeapon, Player damagingPlayer)
        {
            try
            {
                if (damagingPlayer == null) return;
                if (damage.magnitude <= 0.01f) return;  // non-damage events (e.g. block-only pings)

                // FF telemetry — fires on any damage event so we can see ALL hits in a 2v2,
                // not just enemy ones. Enabled when cr_ff Photon room property is true.
                try
                {
                    if (Plugin.ShowBlockDebug != null && Plugin.ShowBlockDebug.Value
                        && PhotonNetwork.InRoom && PhotonNetwork.CurrentRoom != null
                        && PhotonNetwork.CurrentRoom.CustomProperties != null
                        && PhotonNetwork.CurrentRoom.CustomProperties.ContainsKey("cr_ff")
                        && _ffDiagRemaining > 0)
                    {
                        var srcCD = damagingPlayer != null ? damagingPlayer.GetComponent<CharacterData>() : null;
                        var tgtCD = __instance != null ? __instance.GetComponentInParent<CharacterData>() : null;
                        var teamField = typeof(CharacterData).GetField("teamID", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                        int srcTeam = (srcCD != null && teamField != null) ? (int)teamField.GetValue(srcCD) : -1;
                        int tgtTeam = (tgtCD != null && teamField != null) ? (int)teamField.GetValue(tgtCD) : -1;
                        bool sameTeam = (srcTeam >= 0 && srcTeam == tgtTeam);
                        _ffDiagRemaining--;
                        Plugin.Log.LogInfo($"[FF-DIAG] dmg={damage.magnitude:F1} src_team={srcTeam} tgt_team={tgtTeam} same_team={sameTeam} weapon='{(damagingWeapon != null ? damagingWeapon.name : "(null)")}'");
                    }
                }
                catch { }

                var damagerPV = damagingPlayer.data?.view ?? damagingPlayer.GetComponent<PhotonView>();
                var targetPV = __instance != null ? __instance.GetComponentInParent<PhotonView>() : null;

                // Block-debug: if WE are the target and the damager is someone else, record
                // the hit so the overlay can classify it against the last activation time.
                // Owned by the target client — damagerPV.IsMine check is from the wrong side.
                try
                {
                    if (targetPV != null && targetPV.IsMine && damagerPV != null && !damagerPV.IsMine)
                    {
                        GameStateWatcher.OnLocalPlayerHit(damage.magnitude);
                    }
                }
                catch { }

                if (damagerPV == null || !damagerPV.IsMine) return;
                // Self-damage (rebounds, own explosions) shouldn't count toward Hit %.
                if (targetPV != null && targetPV.IsMine) return;

                // Hit counting moved to ProjectileHit_DirectHitCounter_Patch (bug #69).
                // The HIT-DIAG data settled the question this postfix was waiting on:
                // TakeDamage's damagingWeapon is always the GUN (WeaponBase), for DOT
                // ticks too (damage=1.2 events carried the same weapon), so no filter
                // here can separate direct hits from poison/burn ticks. The relaxed
                // count let DOT pump bullets_hit up to the _hitsRemaining cap — i.e.
                // hits == fired == "100% accuracy" for any DOT build (Stan's report).
                // Direct impacts are counted at ProjectileHit.RPCA_DoHit instead, the
                // single funnel every real bullet impact passes through and DOT never
                // does. This postfix still owns the damage timeline and the opt-in
                // block-debug hit signal.
            }
            catch { }
        }
    }

    /// <summary>Bug #69 — precise Hit % numerator. ProjectileHit.RPCA_DoHit is the
    /// one path every direct bullet impact takes (local, remote, and RPC'd), and
    /// DOT/explosion/thorns damage never routes through it. Count an unblocked
    /// impact on an enemy player, owner-side only. The _hitsRemaining budget in
    /// GameStateWatcher still bounds hits ≤ fired.</summary>
    [HarmonyPatch(typeof(ProjectileHit), "RPCA_DoHit")]
    class ProjectileHit_DirectHitCounter_Patch
    {
        // PREFIX, not Postfix (bugs #77/#80): a killing blow's vanilla body runs
        // damage → death → SetActive(false) on the target's ROOT GameObject
        // synchronously, after which GetComponentInParent<Player>() returns null
        // (inactive GO) and the kill shot read as "hit a box". A Postfix also
        // never runs at all if the body throws mid-teardown. Counting up front
        // sees the target while it is still alive; wasBlocked arrives as an
        // argument so the block gate is unaffected.
        static void Prefix(ProjectileHit __instance, int viewID, bool wasBlocked)
        {
            try
            {
                if (wasBlocked) return;               // absorbed — not a hit
                if (viewID == -1) return;             // terrain/map collider
                var own = __instance != null ? __instance.ownPlayer : null;
                if (own == null || own.data == null || own.data.view == null || !own.data.view.IsMine) return;
                var targetView = PhotonNetwork.GetPhotonView(viewID);
                if (targetView == null) return;
                // GetComponent (unlike GetComponentInParent) also works on inactive
                // GameObjects — the Player component lives on the PhotonView's root.
                var targetPlayer = targetView.GetComponent<global::Player>();
                if (targetPlayer == null) targetPlayer = targetView.GetComponentInParent<global::Player>();
                if (targetPlayer == null) return;     // hit a box or other damagable, not a player
                if (targetPlayer.TeamID == own.TeamID) return;  // self or teammate (2v2)
                GameStateWatcher.OnLocalBulletHit();
            }
            catch { /* never break vanilla's hit path */ }
        }
    }

    // Block.TryBlock counter — drives LocalBlocksActivatedThisMatch (the blocks_activated
    // denominator). Full-decompile fact: TryBlock has exactly ONE caller — Block.Update on
    // user block input — so this hook IS the right-click counter (the old comment claiming
    // Shields Up/Empower invoke TryBlock was wrong; every card block goes straight to
    // RPCA_DoBlock). Denominator = right-clicks that fired while off cooldown.
    // ── Block-chain classification (July 21 item 1, Stan's community spec) ──
    // Count ONLY right-click-activated blocks: one right-click = one activation,
    // and its Echo / Shield Charge follow-on auto-blocks inherit the same
    // activation (max 1 success credit). Blocks with NO right-click origin
    // (Abyssal Countdown's BlinkStep, ExtraBlock/Shields Up wiring, revive
    // blocks) count NOWHERE. Verified against the full decompile:
    //  - Block.TryBlock has exactly ONE caller — Block.Update on user input.
    //    (The old comment claiming Shields Up/Empower call TryBlock was wrong.)
    //  - Every block funnels through RPCA_DoBlock(firstBlock, dontSetCD,
    //    triggerType, ...); Echo follow-ons are triggerType=Echo scheduled only
    //    from Default+firstBlock events; ShieldCharge dashes start from any
    //    non-ShieldCharge block event and fire triggerType=ShieldCharge.
    //  - So origin inheritance by TRIGGER TYPE is exact — no time windows:
    //    Default -> user iff called inside TryBlock (re-entrancy flag);
    //    Echo -> status of the last Default+firstBlock; ShieldCharge -> status
    //    of the last non-ShieldCharge event.
    internal static class BlockChain
    {
        internal static bool InTryBlock;
        // TIMESTAMPS, not last-writer-wins booleans (review finding): interleaved
        // auto-blocks (Abyssal BlinkStep fires Default+firstBlock every 0.29s;
        // ExtraBlock-style wiring fires inside the user's own IDoBlock) would
        // otherwise CLOSE a still-open user absorb window and drop the user's
        // legitimate success. Auto events can never close a user window now;
        // the worst case flips to slightly user-FAVORABLE attribution, which
        // _activationSuccessCredited caps at 1 credit per right-click anyway.
        internal static float LastUserWindowTime = -999f;   // any user-chain block event (opens a 0.3s absorb window)
        internal static float LastUserDefaultTime = -999f;  // user right-click (Default+firstBlock) — echo scheduler origin
        internal static void Reset() { InTryBlock = false; LastUserWindowTime = LastUserDefaultTime = -999f; }
        // The absorb event arrives ONE NETWORK ROUND-TRIP after our local
        // block stamp (wasBlocked is decided on the bullet owner's client and
        // RPC'd back), on top of the 0.3s vanilla window — July 21 playtest
        // showed real user absorbs dropped at 0.35s. 0.8s covers window + RTT;
        // over-crediting is bounded by the 1-credit-per-right-click cap.
        internal static bool AbsorbIsUserChain() => Time.time - LastUserWindowTime <= 0.8f;
    }

    [HarmonyPatch(typeof(Block), "RPCA_DoBlock")]
    class BlockRpcaDoBlockChainClassifierPatch
    {
        static void Prefix(Block __instance, bool firstBlock,
                           BlockTrigger.BlockTriggerType triggerType, bool onlyBlockEffects)
        {
            try
            {
                var pv = __instance != null ? __instance.GetComponentInParent<PhotonView>() : null;
                if (pv == null || !pv.IsMine) return;   // local player's block only
                if (onlyBlockEffects) return;           // Empower bullet-site: opens no absorb window
                bool user;
                switch (triggerType)
                {
                    case BlockTrigger.BlockTriggerType.Default:
                        user = firstBlock && BlockChain.InTryBlock;   // BlinkStep/ExtraBlock/ShieldsUp/revive → false
                        if (user) BlockChain.LastUserDefaultTime = Time.time;
                        break;
                    case BlockTrigger.BlockTriggerType.Echo:
                        // Echoes schedule at 0.2s steps from their Default+firstBlock
                        // origin; stacked Echo cards reach ~1s. 1.5s horizon covers it.
                        user = Time.time - BlockChain.LastUserDefaultTime <= 1.5f;
                        break;
                    case BlockTrigger.BlockTriggerType.ShieldCharge:
                        // Dash blocks belong to whatever user-chain event started the
                        // dash; dashes run a couple seconds at high levels.
                        user = Time.time - BlockChain.LastUserWindowTime <= 3.0f;
                        break;
                    default:
                        user = false;
                        break;
                }
                if (user) BlockChain.LastUserWindowTime = Time.time;
                if (GameStateWatcher.IsTracking
                    && Plugin.ShowBlockDebug != null && Plugin.ShowBlockDebug.Value)
                    Plugin.Log.LogInfo($"[BLOCK-DBG] WINDOW type={triggerType} first={firstBlock} user={user}");
            }
            catch { }
        }
    }

    [HarmonyPatch(typeof(Block), "TryBlock")]
    class BlockTryBlockCounterPatch
    {
        // Readiness gate: vanilla activates on `counter >= Cooldown()` which is
        // (cooldown + cdAdd) * cdMultiplier — the old reflection read of the raw
        // `cooldown` field mis-gated whenever a block-CD-modifying card was held.
        // Both members are publicized; read them directly.
        static void Prefix(Block __instance, out bool __state)
        {
            __state = false;
            try { __state = !(__instance.counter < __instance.Cooldown()); }
            catch { __state = true; }
            BlockChain.InTryBlock = true;   // re-entrancy marker: RPCA_DoBlock fired inside this frame = right-click
        }

        static System.Exception Finalizer(System.Exception __exception)
        {
            BlockChain.InTryBlock = false;  // never leave the flag stuck
            return __exception;
        }

        static void Postfix(Block __instance, bool __state)
        {
            if (NativeUI.IsOpen) return;  // F5 Prefix blocked the call; don't credit it
            try
            {
                var pv = __instance != null ? __instance.GetComponentInParent<PhotonView>() : null;
                if (pv == null || !pv.IsMine) return;

                // [BLOCK-TEAM] diagnostic for the "right-click block fails on non-host" report.
                // Logs EVERY TryBlock attempt by the local player — ready or on cooldown — so
                // we can confirm whether the bug correlates with team / playerId / IsMasterClient.
                // Captures only competitive (mod-issued) rooms so the noise is bounded.
                try
                {
                    if (Plugin.ShowBlockDebug != null && Plugin.ShowBlockDebug.Value
                        && CompetitiveRoomDetect.IsCompetitiveRoom() && !_diagThrottled())
                    {
                        var p = __instance.GetComponentInParent<global::Player>();
                        int team = -1, playerId = -1;
                        try { team = p != null ? p.TeamID : -1; } catch { }
                        try { playerId = p != null ? p.PlayerID : -1; } catch { }
                        int actor = -1;
                        bool isMaster = false;
                        try { actor = PhotonNetwork.LocalPlayer != null ? PhotonNetwork.LocalPlayer.ActorNumber : -1; } catch { }
                        try { isMaster = PhotonNetwork.IsMasterClient; } catch { }
                        Plugin.Log.LogInfo($"[BLOCK-TEAM] tryBlock ready={__state} team={team} playerID={playerId} actor={actor} isMaster={isMaster}");
                    }
                }
                catch { }

                if (!__state) return;          // block was on cooldown — TryBlock didn't actually activate
                GameStateWatcher.OnLocalBlockActivated();
            }
            catch { }
        }

        // Per-second throttle so a 6-second-cooldown spam doesn't write 200 log lines.
        private static float _lastDiagLogTime;
        private static bool _diagThrottled()
        {
            float now = Time.unscaledTime;
            if (now - _lastDiagLogTime < 0.5f) return true;
            _lastDiagLogTime = now;
            return false;
        }
    }

    [HarmonyPatch]
    class BlockDoBlockCounterPatch
    {
        // Block.DoBlock has multiple overloads across ROUNDS revisions. Target the one with
        // the most parameters (the canonical path). Previously we filtered on
        // triggerType=Default to exclude ShieldCharge/Echo, but empirically this suppresses
        // real bullet-absorb events too (the engine fires DoBlock with various trigger types
        // depending on the source of the hit, not reliably Default for projectiles). Count
        // ANY DoBlock on the local player's block — it represents "your block timed right and
        // stopped something," which matches the user-facing meaning of "successful block."
        static MethodBase TargetMethod()
        {
            var t = typeof(Block);
            MethodInfo best = null;
            int bestPc = -1;
            foreach (var m in t.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.NonPublic))
            {
                if (m.Name != "DoBlock") continue;
                int pc = m.GetParameters().Length;
                if (pc > bestPc) { bestPc = pc; best = m; }
            }
            return best;
        }

        private static bool _firstEntry;
        static void Postfix(Block __instance)
        {
            if (!_firstEntry) { _firstEntry = true; Plugin.Log.LogInfo("[BLOCK] DoBlock Postfix first invocation (patch attached)"); }
            try
            {
                var pv = __instance != null ? __instance.GetComponentInParent<PhotonView>() : null;
                if (pv == null || !pv.IsMine) return;
                // July 21 item 1: the absorb credits the chain that opened a
                // window RECENTLY — user right-click chains (incl. Echo/
                // ShieldCharge follow-ons) count; pure auto-blocks (Abyssal
                // etc.) count nowhere. Time-based so an interleaved auto event
                // can't close a still-open user window.
                GameStateWatcher.OnLocalBlockSuccessful(BlockChain.AbsorbIsUserChain());
            }
            catch { }
        }
    }

    // ── Diagnostic: ConnectToRegion call-site tracer (v1.26.3) ─────────────
    // Lopi reported (v1.26.1 logs): joined ranked room successfully, sat
    // there ~15 seconds with the F5 menu open, then suddenly the vanilla
    // Photon flow fired `connectToRegion us` → Left room → joined a vanilla
    // EU casual room. Match was abandoned; Lexia stuck in the empty ranked
    // room. We don't yet know what triggered NCH.ConnectToRegion mid-room
    // — our QueueJoiner shouldn't fire it once already in the target room,
    // and MainMenuHandler was disabled so vanilla quickmatch shouldn't be
    // reachable. This Prefix logs every call to ConnectToRegion along with
    // a partial managed stack-trace (top 12 frames) when we're in a
    // competitive room, so the next reproduction tells us exactly which
    // code path is calling it.
    //
    // v1.28: the original `[HarmonyPatch(typeof(NetworkConnectionHandler),
    // "ConnectToRegion")]` NEVER ATTACHED — HarmonyX logged "Could not find
    // method for type NetworkConnectionHandler and name ConnectToRegion", so we
    // got zero trace data for ~2 release cycles. ROUNDS routes region switching
    // through Photon's `PhotonNetwork.ConnectToRegion(string)` (a PUN static),
    // not an NCH method of that name. Resolve the target dynamically across both
    // types and read the region via __args so we're agnostic to the exact
    // signature/overload. The expensive stack capture is gated to competitive
    // rooms only — the region-select ping screen calls ConnectToRegion ~17× in a
    // burst and we don't want to trace those.
    class NCHConnectToRegionDiagPatch
    {
        static IEnumerable<MethodBase> TargetMethods()
        {
            var seen = new HashSet<MethodBase>();
            foreach (var t in new[] { typeof(NetworkConnectionHandler), typeof(PhotonNetwork) })
            {
                if (t == null) continue;
                List<MethodInfo> methods = null;
                try { methods = AccessTools.GetDeclaredMethods(t); }
                catch { methods = null; }
                if (methods == null) continue;
                foreach (var m in methods)
                    if (m != null && m.Name == "ConnectToRegion" && seen.Add(m))
                        yield return m;
            }
        }

        static void Prefix(object[] __args)
        {
            try
            {
                // Only trace calls that happen while we're sitting in a competitive
                // room — that's the abandoned-ranked-room bug (Lopi/Lexia). Normal
                // region pinging from the menu is expected and not worth logging.
                if (!CompetitiveRoomDetect.IsCompetitiveRoom()) return;

                string region = "?";
                if (__args != null)
                    foreach (var a in __args) if (a is string s) { region = s; break; }
                string roomName = "(none)";
                try { roomName = PhotonNetwork.CurrentRoom?.Name ?? "(none)"; } catch { }
                // Trim the stack-trace to a manageable size — the top frames
                // are what matter.
                var st = new System.Diagnostics.StackTrace(1, false);
                var sb = new System.Text.StringBuilder();
                int n = Math.Min(st.FrameCount, 12);
                for (int i = 0; i < n; i++)
                {
                    var m = st.GetFrame(i)?.GetMethod();
                    if (m == null) continue;
                    sb.Append("  at ").Append(m.DeclaringType?.FullName ?? "?")
                      .Append('.').Append(m.Name).Append('\n');
                }
                Plugin.Log.LogWarning($"[NCH-DIAG] ConnectToRegion('{region}') called " +
                    $"while in comp room='{roomName}'. Stack:\n{sb}");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[NCH-DIAG] log error: {ex.Message}"); }
        }
    }

    // ── Block trigger null-safety (v1.26.3) ────────────────────────────────
    // Vanilla Block.IDoBlock iterates Block.triggers and calls DoBlock on each.
    // The iteration does NOT null-check before invoking, but card teardowns
    // between rounds can leave references to destroyed BlockTrigger instances
    // in the list. Vanilla's BlockTrigger.DoBlock reads `this.gameObject`
    // early, which throws NRE on a destroyed Component. The exception
    // propagates out of the IDoBlock coroutine, abandoning the remaining
    // triggers — so a single dangling reference silently breaks ALL of the
    // player's blocks for the rest of the round.
    //
    // Reproduced in Lexia's v1.26.1 logs: 9 BLOCK-DBG ACTIVATED events in a
    // single round, each followed by the same NRE (BlockTrigger.DoBlock
    // [0x0002a]). Block effect never registered for any of them. Adding a
    // Prefix that bails on a destroyed __instance restores the rest of
    // the iteration. Vanilla bug; we're patching the missing null-check.
    [HarmonyPatch(typeof(BlockTrigger), "DoBlock")]
    class BlockTriggerDoBlockNullSafetyPatch
    {
        // Original v1.26.3 patch silently swallowed destroyed-trigger NREs so
        // Block.IDoBlock's iterator could continue with remaining triggers.
        // That fixed Lexia's "9 NREs in one round" cascade but masked an
        // upstream bug where SOME players (Sir Blender, NotHoly reported
        // post-v1.26.3) end up with their MAIN block-effect trigger destroyed
        // — meaning the cascade-skip works as intended, but the visual /
        // damage-absorb that lived on the destroyed trigger never fires and
        // the player's block "doesn't proc". v1.26.5 expands the patch to
        // capture per-call diagnostic context (player ActorNumber + trigger
        // info) so the next reproduction tells us which trigger is being
        // destroyed and from where, AND adds a Finalizer backstop in case
        // vanilla NREs even when __instance looks alive (some sub-component
        // destroyed under it).
        static bool Prefix(BlockTrigger __instance, BlockTrigger.BlockTriggerType triggerType)
        {
            if (__instance == null)
            {
                // Try to figure out which player owned this trigger so the log
                // tells us "Sid's block missed its main trigger" not just
                // "some block trigger somewhere died."
                string ownerInfo = "?";
                try
                {
                    // __instance is fake-null but the wrapper still has a
                    // type — try to introspect. transform/gameObject access
                    // will themselves throw on a destroyed object, so wrap.
                    ownerInfo = "(GameObject destroyed)";
                }
                catch { }
                Plugin.Log.LogWarning($"[BLOCK-SAFETY] DoBlock skipped: triggerType={triggerType} owner={ownerInfo}. " +
                    "If a player's block isn't proccing this round, this is the cause — main BlockTrigger was destroyed.");
                return false;
            }
            return true;
        }

        // Backstop: if vanilla still NREs after the Prefix lets it through
        // (e.g., a child Component on a live BlockTrigger is destroyed),
        // swallow the exception so Block.IDoBlock's iterator continues with
        // the remaining triggers instead of aborting the whole block.
        static Exception Finalizer(Exception __exception, BlockTrigger __instance, BlockTrigger.BlockTriggerType triggerType)
        {
            // MissingReferenceException is what Unity actually throws when a
            // destroyed component's members are touched (zombie DoBlock reads
            // base.gameObject.name) — it does NOT derive from NRE.
            if (__exception is NullReferenceException || __exception is UnityEngine.MissingReferenceException)
            {
                string state = "alive";
                try { if (__instance == null) state = "destroyed"; } catch { state = "introspection-failed"; }
                Plugin.Log.LogWarning($"[BLOCK-SAFETY] NRE inside vanilla DoBlock " +
                    $"(triggerType={triggerType} instance={state}) — swallowed so iterator continues. " +
                    "Stack: " + (__exception.StackTrace ?? "(none)").Replace("\n", " | "));
                return null;
            }
            return __exception;
        }
    }

    // ── Block zombie-delegate scrub (v1.28.2) ──────────────────────────────
    // THE ranked no-block / infinite-empower root cause, established from the
    // CURRENT game decompile (logs-snapshot/decompiled/), not the old-game PI
    // source. There is NO `Block.triggers` list in ROUNDS 1.1.2 — the previous
    // ScrubNullTriggers reflected a field that does not exist and was a silent
    // no-op forever ("scrubbed 0" was structural, not evidence).
    //
    // Real mechanism: card components (Empower, ShieldCharge, BlockTrigger,
    // …) Delegate.Combine their handlers onto Block/Gun/HealthHandler action
    // fields in Start() and Delegate.Remove them in OnDestroy(). But their
    // OnDestroy bodies dereference the parent chain FIRST (e.g. ShieldCharge:
    // `data.GetComponent<PlayerCollision>()` line 1; Empower:
    // `GetComponentInParent<Player>().data.healthHandler`). During the
    // between-games teardown (our auto-Continue rematch) destruction order is
    // arbitrary; those lookups NRE (proven: lopi's log shows
    // ShieldCharge.OnDestroy + EmpowerStopBlockObjectFollow.OnDestroy NREs at
    // LOADING SCENE), OnDestroy aborts, and the dead component's handlers stay
    // subscribed as ZOMBIES:
    //   • zombie BlockTrigger/ShieldCharge handler → MissingReferenceException
    //     inside Block.IDoBlock (which runs synchronously) → coroutine dies
    //     BEFORE `sinceBlock = 0f` → cooldown engages, no effects, no
    //     absorption = "block broken after game 1" (#15/#19/#23/#24). Each
    //     client simulates BOTH players' blocks from replicated input, so a
    //     zombie on the opponent's replica breaks your block on THEIR screen
    //     only ("effects show but nothing blocks").
    //   • zombie Empower.Block/Empower.Attack → invisible infinite empower,
    //     ×2 damage after each block, no particles, no card shown (#25).
    //
    // Fix: surgically remove ONLY invocation-list entries whose Target is a
    // destroyed UnityEngine.Object. Live subscribers are never touched; no
    // wholesale nulling, no re-running Start() (the old rebuild re-Started
    // INACTIVE template triggers vanilla never starts — the #15 regression).
    internal static class BlockReflect
    {
        private static System.Reflection.FieldInfo _fCounter;
        private static System.Reflection.FieldInfo _fCooldown;
        private static bool _resolved;
        private static void Resolve()
        {
            if (_resolved) return;
            try
            {
                var t = typeof(Block);
                var bf = System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance;
                _fCounter  = t.GetField("counter", bf);
                _fCooldown = t.GetField("cooldown", bf);
            }
            catch { }
            _resolved = true;
        }

        // Per-type cache of delegate-typed instance fields (Block has 6,
        // Gun/HealthHandler/PlayerCollision a few each). Walks the inheritance
        // chain so subclass fields are covered too.
        private static readonly System.Collections.Generic.Dictionary<System.Type, System.Reflection.FieldInfo[]> _delFieldCache
            = new System.Collections.Generic.Dictionary<System.Type, System.Reflection.FieldInfo[]>();

        public static int ScrubDeadDelegateFields(UnityEngine.Component c)
        {
            if (c == null) return 0;
            int removed = 0;
            try
            {
                var t = c.GetType();
                System.Reflection.FieldInfo[] fields;
                if (!_delFieldCache.TryGetValue(t, out fields))
                {
                    var acc = new System.Collections.Generic.List<System.Reflection.FieldInfo>();
                    var bf = System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic
                           | System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.DeclaredOnly;
                    for (var cur = t; cur != null && cur != typeof(UnityEngine.MonoBehaviour) && cur != typeof(UnityEngine.Behaviour) && cur != typeof(object); cur = cur.BaseType)
                        foreach (var f in cur.GetFields(bf))
                            if (typeof(System.Delegate).IsAssignableFrom(f.FieldType)) acc.Add(f);
                    fields = acc.ToArray();
                    _delFieldCache[t] = fields;
                }
                foreach (var f in fields)
                {
                    var del = f.GetValue(c) as System.Delegate;
                    if (del == null) continue;
                    var inv = del.GetInvocationList();
                    System.Delegate rebuilt = null;
                    int dead = 0;
                    foreach (var d in inv)
                    {
                        // Unity fake-null: the managed wrapper survives while the
                        // native object is destroyed — exactly the zombie state an
                        // aborted OnDestroy leaves behind. Static handlers
                        // (Target == null) and plain managed targets are kept.
                        var uo = d.Target as UnityEngine.Object;
                        bool zombie = !object.ReferenceEquals(uo, null) && uo == null;
                        if (zombie) { dead++; continue; }
                        rebuilt = System.Delegate.Combine(rebuilt, d);
                    }
                    if (dead > 0)
                    {
                        f.SetValue(c, rebuilt);
                        removed += dead;
                    }
                }
            }
            catch { }
            return removed;
        }

        /// <summary>Scrub ChildRPC's string→delegate DICTIONARIES (bug #39/#40).
        /// Card components register RPC handlers by Dictionary.Add with a fixed
        /// key ("ShieldChargeCollide" etc.) in Start() and Remove them in
        /// OnDestroy(). When OnDestroy aborts mid-teardown (the same #92 NRE —
        /// proven in lopi's log: ShieldCharge.OnDestroy threw, then next game
        /// ShieldCharge.Start threw ArgumentException 'same key already added'
        /// and ABORTED BEFORE its SuperFirstBlockAction subscription — so
        /// blocking worked but the charge never fired), the stale key blocks
        /// the next game's re-registration. Remove entries whose delegate
        /// targets are ALL destroyed objects; live or mixed entries are kept.</summary>
        public static int ScrubChildRpcDictionaries(UnityEngine.Component rpc)
        {
            if (rpc == null) return 0;
            int removed = 0;
            try
            {
                var bf = System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic
                       | System.Reflection.BindingFlags.Instance;
                foreach (var f in rpc.GetType().GetFields(bf))
                {
                    var dict = f.GetValue(rpc) as System.Collections.IDictionary;
                    if (dict == null || dict.Count == 0) continue;
                    System.Collections.Generic.List<object> deadKeys = null;
                    foreach (System.Collections.DictionaryEntry e in dict)
                    {
                        var del = e.Value as System.Delegate;
                        if (del == null) continue;
                        bool anyLive = false, anyDead = false;
                        foreach (var d in del.GetInvocationList())
                        {
                            var uo = d.Target as UnityEngine.Object;
                            bool zombie = !object.ReferenceEquals(uo, null) && uo == null;
                            if (zombie) anyDead = true; else anyLive = true;
                        }
                        if (anyDead && !anyLive)
                        {
                            if (deadKeys == null) deadKeys = new System.Collections.Generic.List<object>();
                            deadKeys.Add(e.Key);
                        }
                    }
                    if (deadKeys != null)
                        foreach (var k in deadKeys)
                        {
                            dict.Remove(k);
                            removed++;
                            Plugin.Log.LogWarning($"[BLOCK-RESET] removed stale ChildRPC key '{k}' (dead card handler — aborted OnDestroy)");
                        }
                }
            }
            catch { }
            return removed;
        }

        // Scrub every delegate holder a card can hook on a player. Covers the
        // confirmed zombie hosts (Block actions, Gun.ShootPojectileAction,
        // HealthHandler.reviveAction, PlayerCollision.collideWithPlayerAction)
        // plus CharacterData/stats for the same pattern on other cards, and
        // the ChildRPC dictionaries (stale keys abort card Start()s, #39/#40).
        public static int ScrubPlayerDelegates(Player p)
        {
            int n = 0;
            try
            {
                if (p == null || p.data == null) return 0;
                n += ScrubDeadDelegateFields(p.data);
                n += ScrubDeadDelegateFields(p.data.block);
                n += ScrubDeadDelegateFields(p.data.healthHandler);
                n += ScrubDeadDelegateFields(p.data.stats);
                if (p.data.weaponHandler != null)
                    n += ScrubDeadDelegateFields(p.data.weaponHandler.gun);
                n += ScrubDeadDelegateFields(p.GetComponent<PlayerCollision>());
                n += ScrubDeadDelegateFields(p.GetComponent<PlayerVelocity>());
                var childRpc = (UnityEngine.Component)p.GetComponentInChildren<ChildRPC>(true)
                            ?? p.GetComponentInParent<ChildRPC>();
                n += ScrubChildRpcDictionaries(childRpc);
            }
            catch { }
            return n;
        }
        public static void ForceReady(Block b)
        {
            if (b == null) return;
            Resolve();
            try
            {
                if (_fCounter != null && _fCooldown != null)
                {
                    float cd = (float)_fCooldown.GetValue(b);
                    _fCounter.SetValue(b, cd);
                }
            }
            catch { }
        }

    }

    [HarmonyPatch(typeof(Block), "RPCA_DoBlock")]
    class BlockRpcaDoBlockZombieScrubPatch
    {
        // RPCA_DoBlock is the single gateway into IDoBlock for EVERY block
        // path: local TryBlock, remote replicas driven by replicated input,
        // and card-forced CallDoBlock RPCs. Scrubbing zombie delegate entries
        // here guarantees the action chain holds only live subscribers at the
        // moment vanilla invokes it — IDoBlock runs synchronously, so one
        // throwing zombie would otherwise kill `sinceBlock = 0f` (absorption)
        // for that block press. UNGATED: casual in-room rematches hit the
        // same vanilla teardown bug, and removing provably-dead entries is
        // side-effect-free.
        static void Prefix(Block __instance)
        {
            int removed = BlockReflect.ScrubDeadDelegateFields(__instance);
            // Same sweep for this player's Gun + HealthHandler: a zombie
            // Empower deals its ×2 damage via gun.ShootPojectileAction on the
            // first SHOT after a block — scrubbing the gun at block time kills
            // it before it can ever buff a bullet, even if it formed mid-game.
            try
            {
                var data = __instance.GetComponent<CharacterData>();
                if (data != null)
                {
                    if (data.weaponHandler != null)
                        removed += BlockReflect.ScrubDeadDelegateFields(data.weaponHandler.gun);
                    removed += BlockReflect.ScrubDeadDelegateFields(data.healthHandler);
                }
            }
            catch { }
            if (removed > 0)
                Plugin.Log.LogWarning($"[BLOCK-DBG] ZOMBIE-SCRUB removed {removed} dead delegate entry(ies) at block time (an earlier card OnDestroy aborted mid-teardown)");
        }
    }

    [HarmonyPatch(typeof(GM_ArmsRace), "StartGame")]
    class GMArmsRaceStartGameBlockResetPatch
    {
        // Sweep every player's delegate holders — Block actions,
        // Gun.ShootPojectileAction (zombie Empower.Attack = the invisible ×2
        // damage of #25), HealthHandler.reviveAction,
        // PlayerCollision.collideWithPlayerAction (zombie ShieldCharge) — and
        // drop only destroyed-target entries. UNGATED: the scrub is pure
        // repair and the same vanilla bug exists in casual in-room rematches.
        // ForceReady stays competitive-gated: it changes gameplay (block
        // ready at game start) and that behavior was only ever promised for
        // mod-issued rooms.
        //
        // TWO hooks share this body. GM_ArmsRace.StartGame only fires on FRESH
        // room assembly — vanilla's rematch flow (GetRematchYesNo→IDoRematch)
        // calls DoStartGame directly and BYPASSES StartGame, proven in the
        // 7/12 logs: a 7-game ranked 2v2 sitting logged exactly ONE
        // [BLOCK-RESET] line. So games 2+ of every sitting were getting no
        // sweep and no ChildRPC stale-key scrub (the #39/#40 Shield Charge
        // fix), which is why "block/card effects broken" reports kept coming
        // from mid-session games. PlayerManager.ResetCharacters is the
        // rematch-path hook: it fires in IDoRematch right before DoStartGame,
        // i.e. after the teardown that created the zombies and before the new
        // game's card Start() calls re-register ChildRPC keys.
        internal static void RunSweep(string source)
        {
            try
            {
                int dead = 0, players = 0;
                var pm = PlayerManager.instance;
                if (pm != null && pm.players != null)
                {
                    foreach (var p in pm.players)
                    {
                        if (p == null) continue;
                        dead += BlockReflect.ScrubPlayerDelegates(p);
                        players++;
                    }
                }
                bool comp = CompetitiveRoomDetect.IsCompetitiveRoom();
                if (comp)
                {
                    var blocks = UnityEngine.Object.FindObjectsOfType<Block>();
                    if (blocks != null)
                        foreach (var b in blocks) BlockReflect.ForceReady(b);
                }
                Plugin.Log.LogInfo($"[BLOCK-RESET] {source}: scrubbed {dead} zombie delegate entry(ies) across {players} player(s) (competitive={comp})");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[BLOCK-RESET] error: {ex.Message}"); }
        }

        static void Postfix() => RunSweep("StartGame v2");
    }

    /// <summary>Rematch-path half of the block sweep (see RunSweep comment).
    /// Same-room rematches never fire StartGame; ResetCharacters is the hook
    /// vanilla's IDoRematch DOES call, in the correct window. The sweep is
    /// idempotent, so double-firing alongside StartGame on fresh rooms is fine.</summary>
    [HarmonyPatch(typeof(PlayerManager), "ResetCharacters")]
    class PlayerManagerResetCharactersBlockResetPatch
    {
        static void Postfix() => GMArmsRaceStartGameBlockResetPatch.RunSweep("ResetCharacters (rematch)");
    }

    // ── Map color override (v1.22) ─────────────────────────────────────────
    // ROUNDS' ArtHandler.Update polls for LeftShift in Update and calls NextArt() which
    // picks a random art from arts[]. For users who own a "color" cosmetic AND have one
    // active, we patch NextArt to instead apply their saved selection. SetSpecificArt
    // already exists and matches by ArtInstance.profile.name.
    //
    // The Awake postfix logs every art profile name on first load — Sid uses this to
    // identify which art-name maps to which shop SKU. Map mappings live in the static
    // dict below; SKUs not in the dict fall through to vanilla cycling.

    [HarmonyPatch(typeof(ArtHandler), "Awake")]
    class ArtHandlerAwakePatch
    {
        static void Postfix(ArtHandler __instance)
        {
            // NOTE: the csproj references Unity.Postprocessing.Runtime directly these
            // days (added for CustomMapColors), so typed PostProcessProfile access is
            // fine — this diagnostic predates that and keeps its reflection harmlessly.
            try
            {
                if (__instance.arts == null) return;
                var profileField = typeof(ArtInstance).GetField("profile",
                    System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
                for (int i = 0; i < __instance.arts.Length; i++)
                {
                    var art = __instance.arts[i];
                    if (art == null) continue;
                    object profileObj = profileField?.GetValue(art);
                    string profileName = "<no profile>";
                    if (profileObj is UnityEngine.Object uo) profileName = uo.name;
                    Plugin.Log.LogInfo($"[MAPCOLOR] arts[{i}] profile.name = '{profileName}'");
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[MAPCOLOR] Awake log failed: {ex.Message}"); }
            // Item 8: assert the chromatic-aberration toggle on every art profile
            // as soon as the scene's ArtHandler exists (per-scene coverage).
            try { MapPhysicalColorPatch.ChromaticAberrationSetting.Apply(); } catch { }
        }
    }

    // Tints the physical map block renderers per the active custom-color SKU. Each Map
    // instance is spawned per round, so this Postfix runs once per round. We use
    // renderer.material (capital M, auto-clones) so we never poison the shared MapMaterial
    // across maps or rounds. A null MapBlockColor (vanilla SKUs / mapcolor_default) is a no-op.
    // Map block tint per active custom-color SKU. Last attempt set material.color but the map's
    // visible blocks are SpriteRenderers — for those, .color on the renderer is the actual tint
    // (material.color does nothing because the sprite shader samples sprite.color * vertex color).
    // Now sets BOTH SpriteRenderer.color AND multiple known shader properties on the cloned
    // material so we cover sprite, mesh, and any custom-shader renderer ROUNDS uses.
    // Tints map blocks per active custom-color SKU. The walls/floors in ROUNDS are NOT child
    // Renderers of the Map GameObject — they're siblings in the scene OR they use an asset-
    // referenced shared Material (Map.MapMaterial) that we need to tint via a CLONE to not
    // leak across rounds. Strategy here:
    //   1. Clone Map.MapMaterial per-SKU (cached) and reassign it to __instance.MapMaterial
    //      AND to every child Renderer whose sharedMaterial matches the original MapMaterial.
    //   2. Also set SpriteRenderer.color on every sprite child (for moving boxes — these don't
    //      use the shared material).
    // Tints map blocks per active custom-color SKU. Logs verbosely so we can diagnose
    // why walls/floors weren't getting tinted. Strategy:
    //   1. Always tint every SpriteRenderer.color (catches moving boxes + many wall sprites).
    //   2. Walk every renderer in the entire scene (NOT just Map's children) and re-assign
    //      shared materials whose name matches the map material — walls/floors are sometimes
    //      siblings of Map, not children.
    //   3. Cache cloned materials per (sku, original-material-name) so we don't churn.
    // We re-run on every round (Map.Start is per-round). The "glitch" between two patterns
    // probably means another system is reassigning the original material each round — by
    // hooking Start (which fires AFTER ROUNDS' own setup) we should win.
    /// <summary>Shared current-sku holder so the post-process cycle (ArtHandler.NextArt)
    /// and the physical-tint pass (Map.Start + cycle re-apply) agree on which equipped
    /// color is live. Before this existed, Map.Start read the legacy single-value
    /// active_color_sku and the cycle would update post-process alone — walls stuck on
    /// the first sku while color grading rotated through the rest.</summary>
    internal static class MapColorState
    {
        public static string CurrentSku;

        // Bottom-screen toast shown for a few seconds when the player Shift-cycles to a
        // new map skin (so they can find a specific one by name). Read by CompetitiveUI.
        public static string ToastText = "";
        public static float ToastUntil = -999f;
        public static void ShowToast(string name)
        {
            try { ToastText = name ?? ""; ToastUntil = Time.unscaledTime + 2.5f; } catch { }
        }
    }

    [HarmonyPatch(typeof(Map), "Start")]
    class MapPhysicalColorPatch
    {
        // Cached tinted materials, keyed by "{sku}|{originalMaterialName}".
        private static readonly Dictionary<string, Material> _matCache = new Dictionary<string, Material>();
        private static bool _loggedTypes;

        // Per-PS vanilla startColor cache. Read once on the first time we touch each
        // ParticleSystem (when its color is still vanilla, before our patch has mutated
        // it); subsequent applies pull from cache so we don't compound the tint by
        // re-reading our own already-multiplied value. Keyed by GetInstanceID — each
        // round's new PS instances populate fresh entries on their first apply.
        private static readonly Dictionary<int, Color> _vanillaPSColorCache = new Dictionary<int, Color>(512);

        /// <summary>Returns the vanilla startColor for a particle system, caching on
        /// first encounter. Subsequent calls for the same instance return the cached
        /// vanilla value even after we've mutated its current startColor. Falls back
        /// to white if reading the .color property throws (which can happen for
        /// gradient-mode startColors on some ROUNDS art presets).</summary>
        private static Color GetCachedVanillaColor(ParticleSystem ps)
        {
            int id;
            try { id = ps.GetInstanceID(); }
            catch { return Color.white; }
            if (_vanillaPSColorCache.TryGetValue(id, out var cached)) return cached;
            Color current;
            try { current = ps.main.startColor.color; }
            catch { current = Color.white; }
            _vanillaPSColorCache[id] = current;
            return current;
        }

        // Timestamp of the most recent Map.Start. ROUNDS runs Map.Start INSIDE
        // MapTransition.Move (the coroutine that repositions players each round), and it
        // also fires ArtHandler.NextArt during that same window. So for ~the transition
        // duration after Map.Start, any particle mutation risks the MapTransition NRE
        // (learning #45). NextArt uses this to decide defer-vs-apply-now.
        public static float LastMapStartTime = -999f;
        // How long after Map.Start we treat the scene as "still transitioning" and must
        // NOT mutate particles. The move itself is ~0.9s; 2.0s is the proven-safe buffer
        // from learning #45 (v1.26.9 cut it to 0.4s and reintroduced the player-freeze /
        // off-screen bug — opponents on the shipped build hit it every round).
        public const float MapTransitionGuardSec = 2.0f;

        // Recolor a particle system's LIVE particles in place (#28, final form).
        // History: a bare Clear(true) killed burst-emission walls until next
        // round (invisible Velvet walls); the v1.28.3 attempt (Clear +
        // Simulate(0, restart) + Play) was supposed to re-fire the burst, but
        // Sid's retest showed burst systems can still come back EMPTY — Unity
        // doesn't reliably re-fire a t=0 burst from a zero-length Simulate. So
        // stop depending on re-emission entirely: rewrite the CURRENT
        // particles' startColor via GetParticles/SetParticles (positions,
        // lifetimes, per-particle alpha untouched) and let main.startColor
        // (set by the caller) cover everything emitted afterwards. Nothing is
        // cleared, so nothing can go invisible — on any emitter type.
        private static ParticleSystem.Particle[] _retintBuf;
        private static void RetintLiveParticles(ParticleSystem ps, Color tinted, Color? sparkle = null, uint tick = 0)
        {
            try
            {
                int live = ps.particleCount;
                if (live <= 0) return;
                if (_retintBuf == null || _retintBuf.Length < live)
                    _retintBuf = new ParticleSystem.Particle[Mathf.Max(live, 256)];
                int n = ps.GetParticles(_retintBuf);
                var rgb = new Color32(
                    (byte)Mathf.Clamp(Mathf.RoundToInt(tinted.r * 255f), 0, 255),
                    (byte)Mathf.Clamp(Mathf.RoundToInt(tinted.g * 255f), 0, 255),
                    (byte)Mathf.Clamp(Mathf.RoundToInt(tinted.b * 255f), 0, 255),
                    0);
                // Premium sparkle: live particles alternate between the base and the
                // glint color by a stable per-particle key (randomSeed), matching the
                // random-between-two-colors look of new emissions.
                Color32 rgb2 = rgb;
                bool twoTone = sparkle.HasValue;
                if (twoTone)
                {
                    var sp = sparkle.Value;
                    rgb2 = new Color32(
                        (byte)Mathf.Clamp(Mathf.RoundToInt(sp.r * 255f), 0, 255),
                        (byte)Mathf.Clamp(Mathf.RoundToInt(sp.g * 255f), 0, 255),
                        (byte)Mathf.Clamp(Mathf.RoundToInt(sp.b * 255f), 0, 255),
                        0);
                }
                for (int i = 0; i < n; i++)
                {
                    Color32 cur = _retintBuf[i].startColor;
                    // tick rotates which particles carry the glint (the twinkle loop);
                    // tick=0 gives the stable emission-matching split. Only 1-in-3
                    // particles glint at a time — a sparse drift, not a strobe.
                    var pick = twoTone && (((_retintBuf[i].randomSeed + tick) % 3u) == 0u) ? rgb2 : rgb;
                    _retintBuf[i].startColor = new Color32(pick.r, pick.g, pick.b, cur.a);
                }
                if (n > 0) ps.SetParticles(_retintBuf, n);
            }
            catch { }
        }

        // Cap a lifted color's brightest channel so bright hues can't blow out
        // into HDR bloom (Sid: platinum/gilded were "blindingly shiny" — silver
        // × 1.6 lift = 1.4+ per channel = nuclear bloom). 1.15 keeps a gentle
        // glow for dark hues (Magma's molten look) without the white-out.
        private static Color CapBrightness(Color c, float maxChannel = 1.15f)
        {
            float mx = Mathf.Max(c.r, Mathf.Max(c.g, c.b));
            if (mx <= maxChannel || mx <= 0f) return c;
            float s = maxChannel / mx;
            return new Color(c.r * s, c.g * s, c.b * s, c.a);
        }

        // Push a color away from grey toward full saturation by `mult` (1 = unchanged).
        // Keeps luminance roughly stable so brightness is set by the lift, not this.
        private static Color SaturateColor(Color c, float mult)
        {
            float g = c.r * 0.299f + c.g * 0.587f + c.b * 0.114f; // perceived grey level
            return new Color(
                Mathf.Clamp01(g + (c.r - g) * mult),
                Mathf.Clamp01(g + (c.g - g) * mult),
                Mathf.Clamp01(g + (c.b - g) * mult),
                c.a);
        }

        static void Postfix(Map __instance)
        {
            LastMapStartTime = Time.time;
            // v1.32 item 7: lighting/shadow disable settings survive scene reloads —
            // fresh SFRenderer instances spawn with vanilla state every map load.
            // Field flips are transition-safe (not particle mutations), so this
            // does NOT need the MapTransitionGuardSec defer.
            RenderPerfSettings.Apply();
            ChromaticAberrationSetting.Apply();
            // Use whatever sku is currently live after the cycle (ArtHandlerNextArtPatch sets
            // MapColorState.CurrentSku on every cycle advance). Fall back to the legacy single
            // field when the cycle hasn't run yet (fresh map load before any Shift press).
            string sku = MapColorState.CurrentSku;
            if (string.IsNullOrEmpty(sku))
                sku = ApiClient.CachedPlayerStats?.active_color_sku;
            if (string.IsNullOrEmpty(sku) || !CustomMapColors.IsCustomSku(sku))
            {
                // Vanilla/default skin active — un-tint the persistent sky object +
                // camera clears + backdrop quads so a previous custom skin's
                // backdrop doesn't linger.
                RestoreVanillaSky();
                RestoreCameraBackground();
                RestoreBackdropQuads();
                RestoreLighting();
                _twinkleSystems.Clear();
                // v1.32 round 2: runs LAST so a lighting-off flat backdrop wins over
                // the RestoreVanillaSky above (which would otherwise restore the raw
                // dark sky). No-op when lighting is on and never toggled off.
                RenderPerfSettings.ApplyBackdrop();
                return;
            }
            // Defer past the transition before touching particles (see MapTransitionGuardSec).
            // Hosted on the persistent Plugin object, NOT the Map — the Map can be destroyed
            // mid-transition, which would kill a Map-hosted coroutine before it applies.
            ScheduleDeferredTints(sku);
            RenderPerfSettings.ApplyBackdrop();
        }

        // Schedule the wall/atmosphere particle tint to run AFTER the MapTransition window.
        // Always hosted on Plugin.Instance so it survives Map destruction during the move.
        public static void ScheduleDeferredTints(string sku)
        {
            if (string.IsNullOrEmpty(sku) || !CustomMapColors.IsCustomSku(sku)) return;
            var host = Plugin.Instance;
            if (host != null) host.StartCoroutine(DelayedApplyTints(sku));
        }

        private static System.Collections.IEnumerator DelayedApplyTints(string sku)
        {
            yield return new WaitForSeconds(MapTransitionGuardSec);
            // Stale-apply guard: if the player Shift-cycled again during the wait,
            // this scheduled apply is for an OLD sku — proven in Sid's log
            // ("burgundy" tints landing right after "pine" was selected). Skip;
            // the newer selection has its own apply in flight.
            if (!string.Equals(MapColorState.CurrentSku, sku, StringComparison.OrdinalIgnoreCase))
            {
                Plugin.Log.LogInfo($"[MAPCOLOR] skipped stale deferred tint for {sku} (current={MapColorState.CurrentSku})");
                yield break;
            }
            ApplyPhysicalTintsForSku(null, sku); // null → finds the active Map itself
        }

        /// <summary>Apply the SKU's wall / sprite / particle tints to the current scene. Shared
        /// between Map.Start (one-shot on map load) and the Shift cycle (invoked after each
        /// NextArt call, so walls and post-process stay in sync when the player cycles).
        /// Falls through gracefully for vanilla skus and null.</summary>
        public static void ApplyPhysicalTintsForSku(Map mapInstance, string sku)
        {
            if (mapInstance == null)
            {
                // Shift cycle path — find the active Map to operate on.
                mapInstance = UnityEngine.Object.FindObjectOfType<Map>();
                if (mapInstance == null) return;
            }
            try
            {
                if (string.IsNullOrEmpty(sku) || !CustomMapColors.IsCustomSku(sku))
                {
                    return;
                }
                Color? tintN = CustomMapColors.GetMapBlockColor(sku);
                if (!tintN.HasValue)
                {
                    Plugin.Log.LogInfo($"[MAPCOLOR] Map.Start sku={sku} but no MapBlockColor → SpriteRenderer-only path");
                }
                Color c = tintN ?? Color.white;

                // Tint ONLY the walls (OutOfBounds particle systems, Step 3 below) and the
                // art-instance atmosphere particles (Step 4). Previously also tinted every
                // SpriteRenderer under Map/* (the 49 moving physics boxes) and every scene
                // SpriteRenderer that wasn't a player/bullet/UI — both passes also caught
                // the brown boxes and their background variants, making the whole map read
                // as a monotone color block. User feedback: "It should only be the map
                // background and the two wall colors" — i.e. just walls + atmosphere.
                if (!tintN.HasValue) return;
                // v1.26.9 final approach — MULTIPLY vanilla startColor by our preset
                // tint instead of replacing it. Vanilla has many particle systems with
                // subtly-different per-PS colors layered to produce texture; multiplying
                // preserves that variation while shifting the overall hue into our preset.
                //
                // Cache vanilla colors per PS instance ID — the FIRST read captures the
                // vanilla value (before our patch has mutated it); subsequent reads on
                // re-apply pull from the cache so we don't compound our tint by re-reading
                // our own already-tinted value and re-multiplying.
                //
                // History of failed approaches (kept here so I don't repeat them):
                //   1. Per-PS alternation by enumeration index — flashed between rounds.
                //   2. Stable-sort by position — still flashed (random map per round).
                //   3. MinMaxGradient TwoColors — gameplay-wide shimmer (per-particle).
                //   4. Single primary on walls — flat (lost vanilla variation).
                //   5. No mutation, post-process only — vanilla colors leaked through.
                // Walls: kill the texture-flicker via STABLE draw order (v1.26.10).
                // The OutOfBounds boundary is built from several OVERLAPPING semi-transparent
                // particle systems. Unity sorts transparent particles by camera distance; when
                // overlapping systems sit at ~equal depth their relative draw order flips frame to
                // frame, so the visible sprite alternates between systems — the "flickering between
                // textures" the user reported (DISTINCT from per-particle brightness shimmer, which
                // is vanilla and fine). It's invisible in vanilla because the systems carry distinct
                // colors that read as depth, and it vanishes with "1 solid object" because a single
                // draw can't fight itself. Fix without collapsing to one object: give each system a
                // distinct, STABLE sortingFudge so the inter-system draw order is fixed every frame.
                // Assignment is ordered by transform path (deterministic across frames AND rounds)
                // so the order never changes mid-session. We also two-tone the colors (primary /
                // secondary by path parity) so both colors land in the walls as requested.
                // ── v1.29 round 6: the "OutOfBounds/" pass is RETIRED (learning #118).
                // Sid's WALLDIAG log proved those 14 systems are the two PLAYERS'
                // out-of-bounds WARNING effects (OutOfBounds/Particles/Wall, Burst,
                // ShieldWall, Warning... — 7 per player, playing=False by design,
                // played by OutOfBoundsHandler only near the boundary). They were
                // never map walls: the old Clear/Restart code force-played them into
                // permanent visibility (our "colored border beams"), and clearing
                // them mid-shift was the ACTUAL invisible-walls bug. They now stay
                // vanilla (red warnings, gameplay-readable). The visible "walls" of
                // a skin are the base art's glow slabs — the atmosphere pass below
                // carries the PRIMARY/SECONDARY two-tone there instead.
                // ArtInstance atmosphere particles — THE VISIBLE WALLS of a skin
                // (learning #118): the base art's glow slabs hugging the map
                // geometry. They now carry the skin's PRIMARY/SECONDARY two-tone
                // (alternating per system) while the BACKGROUND is carried by the
                // SFSS light + ambient. That's the wall/background separation Sid
                // asked for: walls get their designed colors, backdrop its own.
                int artParts = 0;
                _twinkleSystems.Clear();
                try
                {
                    Color secondary = CustomMapColors.GetSecondaryColor(sku);
                    string baseArt = CustomMapColors.GetBaseArt(sku);
                    var ah = ArtHandler.instance;
                    if (ah != null && ah.arts != null)
                    {
                        var partsField = typeof(ArtInstance).GetField("parts",
                            System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
                        var profileField = typeof(ArtInstance).GetField("profile",
                            System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
                        foreach (var art in ah.arts)
                        {
                            if (art == null) continue;
                            var partsArr = partsField?.GetValue(art) as ParticleSystem[];
                            if (partsArr == null) continue;
                            // Only the SKU's base art should paint the sky. Any other art left
                            // playing (e.g. the Rainbow arts) bleeds purple/pink into the
                            // background — Magma's "sky is purple and pink". Turn the others off.
                            bool isBase = false;
                            try
                            {
                                var prof = profileField?.GetValue(art) as UnityEngine.Object;
                                isBase = prof != null && !string.IsNullOrEmpty(baseArt)
                                         && string.Equals(prof.name, baseArt, StringComparison.OrdinalIgnoreCase);
                            }
                            catch { }
                            if (!isBase)
                            {
                                try { art.TogglePart(false); } catch { }
                                continue;
                            }
                            // Premium sparkle skins: the atmosphere particles ARE the visible
                            // glitter (the wall border systems are thin edge strips), so they
                            // get the full-brightness two-color glint instead of the dim haze.
                            Color? atmoSparkle = CustomMapColors.GetSparkleColor(sku);
                            for (int i = 0; i < partsArr.Length; i++)
                            {
                                var ps = partsArr[i];
                                if (ps == null) continue;
                                try
                                {
                                    Color vanilla = GetCachedVanillaColor(ps);
                                    float lum = vanilla.r * 0.299f + vanilla.g * 0.587f + vanilla.b * 0.114f;
                                    var main = ps.main;
                                    if (atmoSparkle.HasValue)
                                    {
                                        // Premium: primary-colored slabs at SUB-BLOOM brightness
                                        // (Sid: "way too flashy") + a subtle glint. The visible
                                        // twinkle comes from the shimmer loop re-rolling which
                                        // particles are glinted a few times a second.
                                        Color baseHue = SaturateColor(c, 1.15f);
                                        float gLift = 0.62f + 0.28f * Mathf.Clamp01(lum);
                                        Color gA = CapBrightness(new Color(baseHue.r * gLift, baseHue.g * gLift, baseHue.b * gLift, vanilla.a), 0.85f);
                                        Color glintHue = Color.Lerp(gA, SaturateColor(atmoSparkle.Value, 1.0f), 0.5f);
                                        Color gB = CapBrightness(new Color(glintHue.r * 1.15f, glintHue.g * 1.15f, glintHue.b * 1.15f, vanilla.a), 0.95f);
                                        main.startColor = new ParticleSystem.MinMaxGradient(gA, gB);
                                        RetintLiveParticles(ps, gA, gB);
                                        _twinkleSystems.Add(new TwinkleEntry { ps = ps, baseColor = gA, glintColor = gB });
                                    }
                                    else
                                    {
                                        // Two-tone: even systems PRIMARY, odd SECONDARY — the
                                        // designed wall pair, independent of the backdrop.
                                        // Brightness kept BELOW the bloom threshold (Sid: glow
                                        // "right above 0") — the faint remaining glow comes
                                        // from the neutered bloom pass, not HDR colors.
                                        Color layer = (i % 2 == 0) ? c : secondary;
                                        Color hue = SaturateColor(layer, 1.30f);
                                        float lift = 0.70f + 0.30f * Mathf.Clamp01(lum);
                                        Color tinted = CapBrightness(new Color(hue.r * lift, hue.g * lift, hue.b * lift, vanilla.a), 1.0f);
                                        main.startColor = new ParticleSystem.MinMaxGradient(tinted);
                                        RetintLiveParticles(ps, tinted);
                                    }
                                    // Green-hunt diagnostic: name every art part with its vanilla
                                    // + applied color so any hue that still looks wrong on screen
                                    // is attributable to a specific object from one log line.
                                    try
                                    {
                                        var psr0 = ps.GetComponent<ParticleSystemRenderer>();
                                        var b = psr0 != null ? psr0.bounds.size : Vector3.zero;
                                        Color applied = ps.main.startColor.color;
                                        Plugin.Log.LogInfo($"[MAPCOLOR-ART] part='{ps.gameObject.name}' vanilla=#{(int)(vanilla.r*255):X2}{(int)(vanilla.g*255):X2}{(int)(vanilla.b*255):X2} applied=#{(int)(Mathf.Clamp01(applied.r)*255):X2}{(int)(Mathf.Clamp01(applied.g)*255):X2}{(int)(Mathf.Clamp01(applied.b)*255):X2} size={b.x:F0}x{b.y:F0}");
                                    }
                                    catch { }
                                }
                                catch { }
                                artParts++;
                            }
                        }
                    }
                }
                catch (Exception ex) { Plugin.Log.LogWarning($"[MAPCOLOR] art-particle tint failed: {ex.Message}"); }

                // v1.29: tint the ACTUAL sky. ArtHandler carries a dedicated
                // m_background GameObject that the particle passes never touched —
                // its vanilla (blue-leaning) art is what kept showing through and
                // made even green skins read blue once the colorFilter stopped
                // masking it (Sid: "Pine/Forest turned blue").
                int skyParts = TintArtBackground(sku);
                // And the flat backdrop itself: color-clearing cameras + per-map
                // backdrop quads (learning #116 v2 — MainCam clears Depth only, so
                // whatever is under it paints the sky).
                ApplyCameraBackground(sku);
                int quadParts = TintBackdropQuads(sku);
                if (quadParts > 0) Plugin.Log.LogInfo($"[MAPCOLOR] tinted {quadParts} backdrop quad(s) for {sku}");
                // The strongest lever: SFSS light + ambient carry the sky and the
                // shadow beams (learning #116 v3).
                ApplyLighting(sku);

                EnsureTwinkleLoop();
                Plugin.Log.LogInfo($"[MAPCOLOR] sku={sku}: {artParts} two-tone wall slab system(s) + {skyParts} sky renderer(s) + lighting; OOB player-warning effects untouched (vanilla)");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[MAPCOLOR] Map tint failed: {ex.Message}"); }
        }

        private static bool _loggedScenePaths;

        // ── Camera clear color = THE background (v1.29 final, learning #116) ──
        // The big flat backdrop is MainCam's clear color — an editor constant
        // (blue-ish) that vanilla never changes per-art (arts repaint it with
        // strong colorFilters instead). Setting it directly gives each skin an
        // exact background with ZERO effect on walls/geometry, and it swaps
        // instantly on Shift. Vignette + postExposure still shape it into the
        // soft gradient look.
        // v2 (learning #116 correction): MainCam clears DEPTH ONLY (proven in
        // Sid's log: "flags=Depth"), so its backgroundColor is ignored — the
        // backdrop is rendered by something UNDER it: a lower-depth camera
        // and/or a per-map full-screen quad. Tint every color-clearing camera
        // AND every huge backdrop renderer, and dump a one-time [MAPCOLOR-CAMS]
        // inventory so the real painter is identified from a single test log.
        private static readonly Dictionary<int, Color> _vanillaCamClears = new Dictionary<int, Color>();
        private static bool _loggedCams;

        public static void ApplyCameraBackground(string sku)
        {
            try
            {
                Color? bgN = CustomMapColors.GetBackgroundColor(sku) ?? CustomMapColors.GetMapBlockColor(sku);
                if (!bgN.HasValue) return;
                Color bg = bgN.Value;
                var cams = UnityEngine.Object.FindObjectsOfType<Camera>();
                foreach (var cam in cams)
                {
                    if (cam == null) continue;
                    if (!_loggedCams)
                        Plugin.Log.LogInfo($"[MAPCOLOR-CAMS] '{cam.gameObject.name}' depth={cam.depth} flags={cam.clearFlags} bg={cam.backgroundColor} rt={(cam.targetTexture != null)} mask={cam.cullingMask}");
                    // ROUND 8 FIX (the universal green cast, learning #119): only
                    // SCREEN cameras may be tinted. 'LightCamera' renders the SFSS
                    // light/shadow TEXTURE and its SolidColor clear RGBA(1,0,0,0) is
                    // the buffer's required init value — round 4..7 overwrote it with
                    // skin colors at alpha 1, corrupting the lighting buffer on every
                    // skin (the "so much green"). Off-screen cameras are restored if
                    // we ever touched them, then left strictly alone.
                    bool offscreen = cam.targetTexture != null
                                  || cam.gameObject.name.IndexOf("Light", StringComparison.OrdinalIgnoreCase) >= 0;
                    int id = cam.GetInstanceID();
                    if (offscreen)
                    {
                        if (_vanillaCamClears.TryGetValue(id, out var v))
                        {
                            cam.backgroundColor = v;
                            _vanillaCamClears.Remove(id);
                            Plugin.Log.LogInfo($"[MAPCOLOR-CAMS] restored off-screen camera '{cam.gameObject.name}' clear to {v}");
                        }
                        continue;
                    }
                    // Only cameras that actually CLEAR to a color paint backdrop.
                    if (cam.clearFlags != CameraClearFlags.SolidColor && cam.clearFlags != CameraClearFlags.Skybox)
                        continue;
                    if (!_vanillaCamClears.ContainsKey(id)) _vanillaCamClears[id] = cam.backgroundColor;
                    cam.backgroundColor = new Color(
                        Mathf.Clamp01(bg.r * 1.15f), Mathf.Clamp01(bg.g * 1.15f),
                        Mathf.Clamp01(bg.b * 1.15f), 1f);
                    if (cam.clearFlags == CameraClearFlags.Skybox)
                        cam.clearFlags = CameraClearFlags.SolidColor;
                }
                _loggedCams = true;
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[MAPCOLOR] camera bg failed: {ex.Message}"); }
        }

        public static void RestoreCameraBackground()
        {
            try
            {
                foreach (var cam in UnityEngine.Object.FindObjectsOfType<Camera>())
                {
                    if (cam == null) continue;
                    if (_vanillaCamClears.TryGetValue(cam.GetInstanceID(), out var v))
                        cam.backgroundColor = v;
                }
            }
            catch { }
        }

        // ── Premium twinkle loop (v1.29 round 6) ──────────────────────────────
        // Static two-color gradients only vary at EMISSION — big slow slabs never
        // visibly "sparkle". This loop re-rolls WHICH particles carry the glint a
        // few times a second (stable per-particle randomSeed + a rolling tick),
        // producing an actual twinkle at sub-bloom brightness.
        internal struct TwinkleEntry { public ParticleSystem ps; public Color baseColor; public Color glintColor; }
        internal static readonly List<TwinkleEntry> _twinkleSystems = new List<TwinkleEntry>();
        private static bool _twinkleLoopRunning;
        private static uint _twinkleTick;

        internal static void EnsureTwinkleLoop()
        {
            if (_twinkleLoopRunning || Plugin.Instance == null) return;
            _twinkleLoopRunning = true;
            Plugin.Instance.StartCoroutine(TwinkleLoop());
        }

        private static System.Collections.IEnumerator TwinkleLoop()
        {
            // 1.6s between re-rolls (was 0.45s — Sid: "premium colors are
            // shifting too fast"). A slow drift of which particles glint reads
            // as shimmer; the old rate read as strobing.
            var wait = new WaitForSeconds(1.6f);
            while (true)
            {
                yield return wait;
                if (_twinkleSystems.Count == 0) continue;
                // v1.32 item 8: static-cosmetics mode — stop re-rolling the glint.
                // The tick=0 emission gradient already gives a stable two-tone
                // pattern, so skipping here freezes the shimmer in place. Gate the
                // BODY, not the loop start: the loop is while(true) and started at
                // most once per session, so a start-site gate would never re-arm.
                if (Plugin.AnimatedCosmetics != null && !Plugin.AnimatedCosmetics.Value) continue;
                _twinkleTick++;
                for (int i = 0; i < _twinkleSystems.Count; i++)
                {
                    var e = _twinkleSystems[i];
                    try
                    {
                        if (e.ps == null) continue;
                        RetintLiveParticles(e.ps, e.baseColor, e.glintColor, _twinkleTick);
                    }
                    catch { }
                }
            }
        }

        // ── SFSS lighting = the REAL background system (learning #116 v3) ─────
        // The scene composite is: sprites × lightmap, where lightmap = SFLight
        // glow + SFRenderer._ambientLight everywhere else. The "sky" is a
        // backdrop lit by the big light; the shadow beams are ambient-only
        // regions ("a darker grey, BLUE..." per the asset's own tooltip — the
        // ever-blue tone). Tint the big light toward a bright version of the
        // skin background and the ambient toward a dark version: sky and
        // shadows become the designed hue, walls/geometry sprites keep their
        // own colors. Small lights (muzzle flashes etc.) are left alone.
        private static readonly Dictionary<int, Color> _vanillaLightColors = new Dictionary<int, Color>();
        private static readonly Dictionary<int, Color> _vanillaAmbient = new Dictionary<int, Color>();
        private static bool _loggedLights;

        public static void ApplyLighting(string sku)
        {
            try
            {
                Color? bgN = CustomMapColors.GetBackgroundColor(sku) ?? CustomMapColors.GetMapBlockColor(sku);
                if (!bgN.HasValue) return;
                Color bg = SaturateColor(bgN.Value, 1.10f);
                // Lit areas = bright designed hue; shadowed areas = deep shade of it.
                // v1.29.1: the +0.22 brightness floor is now LUMINANCE-SCALED. The
                // fixed floor meant even a pitch-black background rendered as a
                // grey sky (0.22 minimum) — the dark skins (charcoal/obsidian/
                // blackwood/abyss) could never go actually dark (Sid: "Charcoal
                // should be pretty dark"). Backgrounds at luminance >= 0.25 keep
                // the exact old math (floor 0.22, zero visual change for the
                // mid/light skins); below that the floor sinks toward 0.04 so a
                // near-black value reads as pitch-black smoke instead of fog.
                float bgLum = 0.299f * bg.r + 0.587f * bg.g + 0.114f * bg.b;
                float skyFloor = Mathf.Lerp(0.04f, 0.22f, Mathf.InverseLerp(0.04f, 0.25f, bgLum));
                Color lit = CapBrightness(new Color(
                    skyFloor + bg.r * 0.95f, skyFloor + bg.g * 0.95f, skyFloor + bg.b * 0.95f, 1f), 1.0f);
                // Alpha 0.85 matches the vanilla ambient's alpha (its meaning is
                // internal to the SFSS shader — keep the semantics identical).
                Color amb = new Color(bg.r * 0.45f, bg.g * 0.45f, bg.b * 0.45f, 0.85f);

                foreach (var rend in UnityEngine.Object.FindObjectsOfType<SFRenderer>())
                {
                    if (rend == null) continue;
                    int id = rend.GetInstanceID();
                    if (!_vanillaAmbient.ContainsKey(id))
                    {
                        _vanillaAmbient[id] = rend.ambientLight;
                        Plugin.Log.LogInfo($"[MAPCOLOR-LIGHT] SFRenderer '{rend.gameObject.name}' vanilla ambient={rend.ambientLight}");
                    }
                    rend.ambientLight = amb;
                }
                if (SFLight._lights != null)
                    foreach (var l in SFLight._lights)
                    {
                        if (l == null) continue;
                        if (!_loggedLights)
                            Plugin.Log.LogInfo($"[MAPCOLOR-LIGHT] SFLight '{l.gameObject.name}' color={l._color} intensity={l._intensity} radius={l._radius} parallax={l._parallaxLight}");
                        // Scene light detection: Sid's log shows THE sun-light is
                        // radius=0.5, intensity=10, vanilla color PURE BLUE — the
                        // radius>=20 filter skipped exactly the light that paints the
                        // sky. Key on intensity/parallax instead; gameplay flashes are
                        // low-intensity.
                        if (!l._parallaxLight && l._intensity < 5f) continue;
                        int id = l.GetInstanceID();
                        if (!_vanillaLightColors.ContainsKey(id)) _vanillaLightColors[id] = l._color;
                        l._color = lit;
                    }
                _loggedLights = true;
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[MAPCOLOR] lighting tint failed: {ex.Message}"); }
        }

        public static void RestoreLighting()
        {
            try
            {
                foreach (var rend in UnityEngine.Object.FindObjectsOfType<SFRenderer>())
                {
                    if (rend == null) continue;
                    if (_vanillaAmbient.TryGetValue(rend.GetInstanceID(), out var a))
                        rend.ambientLight = a;
                }
                if (SFLight._lights != null)
                    foreach (var l in SFLight._lights)
                    {
                        if (l == null) continue;
                        if (_vanillaLightColors.TryGetValue(l.GetInstanceID(), out var c))
                            l._color = c;
                    }
            }
            catch { }
        }

        // ── v1.32 item 7: FPS settings — map lighting / shadows kill-switches ──
        // Mechanics (full-game decompile SFRenderer.cs, on the 'LightCamera'):
        //  • Shadows off (_shadows=false) skips the WHOLE shadow pass — CullPolys +
        //    a second lightmap RT + per-light shadow meshes. Big win, scene stays
        //    fully lit and correctly colored. This is the safe perf toggle.
        //  • Lighting off (enabled=false) stops OnPreRender, so no lightmap is built.
        //    We set the SFSS shader globals to white so scene SPRITES (players,
        //    walls) render full-bright and clearly. BUT the map's SKY COLOR *is* the
        //    lighting: the scene composites as sprites × lightmap, and the backdrop
        //    sprite art (ArtHandler.m_background) is a fixed DARK texture that the
        //    lightmap normally brightens/tints into the per-map sky (learning #117).
        //    White light on a dark backdrop = dark → the constant "dark purple"
        //    Sid saw regardless of map (v1.32 round 2). There is NO way to recover
        //    the coloured sky without the lighting, so lighting-off deliberately
        //    paints m_background a flat neutral slate (ApplyBackdrop) — a clean
        //    minimal backdrop that reads as an intentional perf/accessibility mode.
        // Vanilla state cached per instance id; re-applied every Map.Start / NextArt
        // because scene reloads spawn fresh renderers.
        internal static class RenderPerfSettings
        {
            private static readonly Dictionary<int, bool> _vanillaShadows = new Dictionary<int, bool>();
            private static readonly Dictionary<int, bool> _vanillaEnabled = new Dictionary<int, bool>();
            // Flat backdrop shown while lighting is disabled (matches the mod's UI
            // panel slate so it looks deliberate). Kept opaque; per-sprite vanilla
            // alpha is preserved at paint time.
            private static readonly Color FLAT_BACKDROP = new Color(0.09f, 0.10f, 0.13f, 1f);
            private static bool _flatBackdropActive = false;

            // Renderer enable + shadow flags + shader globals. Safe to run early in
            // the Map.Start postfix (field flips, not particle mutation — no
            // MapTransitionGuardSec needed). Does NOT touch the backdrop; that must
            // run LAST (ApplyBackdrop) so the postfix's own RestoreVanillaSky for
            // default maps can't undo it.
            internal static void Apply()
            {
                try
                {
                    bool light = Plugin.MapLightingEnabled == null || Plugin.MapLightingEnabled.Value;
                    bool shadow = Plugin.MapShadowsEnabled == null || Plugin.MapShadowsEnabled.Value;
                    foreach (var rend in UnityEngine.Object.FindObjectsOfType<SFRenderer>())
                    {
                        if (rend == null) continue;
                        int id = rend.GetInstanceID();
                        if (!_vanillaShadows.ContainsKey(id)) _vanillaShadows[id] = rend._shadows;
                        if (!_vanillaEnabled.ContainsKey(id)) _vanillaEnabled[id] = rend.enabled;
                        rend._shadows = shadow ? _vanillaShadows[id] : false;
                        rend.enabled = light ? _vanillaEnabled[id] : false;
                    }
                    if (!light)
                    {
                        // A disabled SFRenderer never runs OnPostRender, so the SFSS
                        // shader globals keep pointing at the previous scene's released
                        // lightmap RTs. Pin them to vanilla's OnPostRender identity
                        // (white ambient/exposure/lightmaps) so scene sprites stay
                        // full-bright and stable.
                        Shader.SetGlobalColor("_SFAmbientLight", Color.white);
                        Shader.SetGlobalFloat("_SFExposure", 1f);
                        Shader.SetGlobalTexture("_SFLightMap", Texture2D.whiteTexture);
                        Shader.SetGlobalTexture("_SFLightMapWithShadows", Texture2D.whiteTexture);
                    }
                }
                catch (Exception ex) { Plugin.Log.LogWarning($"[RENDERPERF] apply failed: {ex.Message}"); }
            }

            // Backdrop paint/restore. Runs LAST in the Map.Start postfix (after the
            // default-map RestoreVanillaSky) and on a mid-match settings toggle.
            internal static void ApplyBackdrop()
            {
                try
                {
                    bool light = Plugin.MapLightingEnabled == null || Plugin.MapLightingEnabled.Value;
                    if (!light)
                    {
                        PaintFlatBackdrop();
                        _flatBackdropActive = true;
                    }
                    else if (_flatBackdropActive)
                    {
                        // Lighting came back on — bring the real sky back. Restore the
                        // vanilla backdrop, then re-tint if a custom map skin is active
                        // (its sky is a direct sprite tint, independent of lighting).
                        RestoreVanillaSky();
                        var sku = MapColorState.CurrentSku;
                        if (!string.IsNullOrEmpty(sku) && CustomMapColors.IsCustomSku(sku))
                            TintArtBackground(sku);
                        _flatBackdropActive = false;
                    }
                }
                catch (Exception ex) { Plugin.Log.LogWarning($"[RENDERPERF] backdrop failed: {ex.Message}"); }
            }

            // Paint ArtHandler.m_background a flat neutral slate. Captures true vanilla
            // into the SAME caches the skin-tint pass uses (_vanillaSkyColors for
            // sprites, GetCachedVanillaColor for particles), so RestoreVanillaSky
            // brings the real sky back and the skin-tint pass reads correct vanilla.
            private static void PaintFlatBackdrop()
            {
                var ah = ArtHandler.instance;
                var bgGO = ah != null ? ah.m_background : null;
                if (bgGO == null) return;
                foreach (var sr in bgGO.GetComponentsInChildren<SpriteRenderer>(true))
                {
                    if (sr == null) continue;
                    int id = sr.GetInstanceID();
                    if (!_vanillaSkyColors.TryGetValue(id, out var vanilla))
                    {
                        vanilla = sr.color;
                        _vanillaSkyColors[id] = vanilla;
                    }
                    sr.color = new Color(FLAT_BACKDROP.r, FLAT_BACKDROP.g, FLAT_BACKDROP.b, vanilla.a);
                }
                foreach (var ps in bgGO.GetComponentsInChildren<ParticleSystem>(true))
                {
                    if (ps == null) continue;
                    Color vanilla = GetCachedVanillaColor(ps);
                    Color flat = new Color(FLAT_BACKDROP.r, FLAT_BACKDROP.g, FLAT_BACKDROP.b, vanilla.a);
                    var main = ps.main;
                    main.startColor = new ParticleSystem.MinMaxGradient(flat);
                    RetintLiveParticles(ps, flat);
                }
            }
        }

        // Item 8 (July 20): chromatic aberration toggle. CA lives as a
        // ChromaticAberration settings object on every art's shared
        // PostProcessProfile (baseline) plus vanilla's ChomaticAberrationFeeler
        // (sic) writing intensity pulses each frame. Zeroing intensity loses to
        // the feeler's per-frame writes; flipping `active` wins outright —
        // PostProcessLayer.OverrideSettings skips inactive effects and re-blends
        // from profiles every frame, so the flip is instant both directions and
        // needs no vanilla-value caching (default true, vanilla never writes it).
        // Profiles are session-long shared assets, so every apply site must
        // assert the CURRENT toggle value, and the CustomMapColors clone cache
        // must be swept too (clones deep-copy the CA settings object).
        internal static class ChromaticAberrationSetting
        {
            internal static void Apply()
            {
                try
                {
                    bool on = Plugin.ChromaticAberrationEnabled == null || Plugin.ChromaticAberrationEnabled.Value;
                    var ah = ArtHandler.instance;
                    if (ah != null)
                    {
                        try { Set(ah.volume != null ? ah.volume.profile : null, on); } catch { }
                        try { Set(ah.menuArt != null ? ah.menuArt.profile : null, on); } catch { }
                        try { if (ah.arts != null) foreach (var a in ah.arts) Set(a != null ? a.profile : null, on); } catch { }
                    }
                    foreach (var clone in CustomMapColors.CachedClones) Set(clone, on);
                }
                catch (Exception ex) { Plugin.Log.LogWarning($"[CA-TOGGLE] apply failed: {ex.Message}"); }
            }

            private static void Set(PostProcessProfile p, bool on)
            {
                if (p == null) return;
                try
                {
                    if (p.TryGetSettings<ChromaticAberration>(out var ca) && ca != null)
                        ca.active = on;
                }
                catch { }
            }
        }

        // Per-map backdrop quads: any renderer wide enough to cover the play
        // area (x span [-35.56, 35.56] per OutOfBoundsHandler) that isn't a
        // particle. Cached vanilla colors per instance; logged once per object
        // so a wrong-looking map's log names its backdrop immediately.
        private static readonly Dictionary<int, Color> _vanillaQuadColors = new Dictionary<int, Color>();
        private static readonly HashSet<int> _loggedQuads = new HashSet<int>();

        private static int TintBackdropQuads(string sku)
        {
            int touched = 0;
            try
            {
                Color? bgN = CustomMapColors.GetBackgroundColor(sku) ?? CustomMapColors.GetMapBlockColor(sku);
                if (!bgN.HasValue) return 0;
                Color bg = SaturateColor(bgN.Value, 1.10f);
                foreach (var r in UnityEngine.Object.FindObjectsOfType<Renderer>())
                {
                    if (r == null || r is ParticleSystemRenderer) continue;
                    // SpriteRenderers only (round 8): the sole MeshRenderer ever
                    // matched was 'CLEAR_STENCIL_BUFFER' — a sprite-masking utility
                    // quad, not scenery. Tinting utility materials corrupts render
                    // plumbing (same lesson as the LightCamera, learning #119).
                    var sr = r as SpriteRenderer;
                    if (sr == null) continue;
                    if (r.gameObject.name.IndexOf("STENCIL", StringComparison.OrdinalIgnoreCase) >= 0) continue;
                    var size = r.bounds.size;
                    if (size.x < 60f || size.y < 25f) continue;   // not backdrop-sized
                    int id = r.GetInstanceID();
                    if (_loggedQuads.Add(id))
                        Plugin.Log.LogInfo($"[MAPCOLOR-BG] backdrop candidate: '{GetTransformPath(r.transform)}' type={r.GetType().Name} size={size.x:F0}x{size.y:F0}");
                    if (!_vanillaQuadColors.TryGetValue(id, out var vanilla))
                    { vanilla = sr.color; _vanillaQuadColors[id] = vanilla; }
                    float lum = vanilla.r * 0.299f + vanilla.g * 0.587f + vanilla.b * 0.114f;
                    float lift = 0.50f + 0.60f * Mathf.Clamp01(lum);
                    sr.color = new Color(Mathf.Clamp01(bg.r * lift), Mathf.Clamp01(bg.g * lift),
                                         Mathf.Clamp01(bg.b * lift), vanilla.a);
                    touched++;
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[MAPCOLOR] backdrop quad tint failed: {ex.Message}"); }
            return touched;
        }

        private static void RestoreBackdropQuads()
        {
            try
            {
                foreach (var r in UnityEngine.Object.FindObjectsOfType<Renderer>())
                {
                    if (r == null) continue;
                    if (!_vanillaQuadColors.TryGetValue(r.GetInstanceID(), out var v)) continue;
                    var sr = r as SpriteRenderer;
                    if (sr != null) sr.color = v;
                    else if (r.material != null && r.material.HasProperty("_Color")) r.material.color = v;
                }
            }
            catch { }
        }

        // ── Sky (ArtHandler.m_background) tint, v1.29 ─────────────────────────
        // The real backdrop is a dedicated GameObject on ArtHandler, separate
        // from the art particles. Colorize its SpriteRenderers + ParticleSystems
        // toward the skin's BackgroundColor (luminance-preserving, like walls but
        // dimmer), caching vanilla colors per instance so vanilla skins restore.
        private static readonly Dictionary<int, Color> _vanillaSkyColors = new Dictionary<int, Color>();

        private static int TintArtBackground(string sku)
        {
            int touched = 0;
            try
            {
                var ah = ArtHandler.instance;
                var bgGO = ah != null ? ah.m_background : null;
                if (bgGO == null) return 0;
                Color? bgN = CustomMapColors.GetBackgroundColor(sku) ?? CustomMapColors.GetMapBlockColor(sku);
                if (!bgN.HasValue) return 0;
                Color bg = SaturateColor(bgN.Value, 1.15f);

                foreach (var sr in bgGO.GetComponentsInChildren<SpriteRenderer>(true))
                {
                    if (sr == null) continue;
                    int id = sr.GetInstanceID();
                    if (!_vanillaSkyColors.TryGetValue(id, out var vanilla))
                    {
                        vanilla = sr.color;
                        _vanillaSkyColors[id] = vanilla;
                    }
                    float lum = vanilla.r * 0.299f + vanilla.g * 0.587f + vanilla.b * 0.114f;
                    float lift = 0.45f + 0.60f * Mathf.Clamp01(lum);
                    sr.color = new Color(bg.r * lift, bg.g * lift, bg.b * lift, vanilla.a);
                    touched++;
                }
                Color? skySparkle = CustomMapColors.GetSparkleColor(sku);
                foreach (var ps in bgGO.GetComponentsInChildren<ParticleSystem>(true))
                {
                    if (ps == null) continue;
                    Color vanilla = GetCachedVanillaColor(ps);
                    float lum = vanilla.r * 0.299f + vanilla.g * 0.587f + vanilla.b * 0.114f;
                    float lift = 0.45f + 0.60f * Mathf.Clamp01(lum);
                    Color tinted = new Color(bg.r * lift, bg.g * lift, bg.b * lift, vanilla.a);
                    var main = ps.main;
                    if (skySparkle.HasValue)
                    {
                        // Premium skins: sky particles glint gently between the backdrop
                        // tint and a slightly brighter sparkle — star-field, not floodlight.
                        Color glint = CapBrightness(
                            Color.Lerp(tinted, skySparkle.Value, 0.5f) * 1.10f, 1.0f);
                        glint.a = vanilla.a;
                        main.startColor = new ParticleSystem.MinMaxGradient(tinted, glint);
                        RetintLiveParticles(ps, tinted, glint);
                    }
                    else
                    {
                        main.startColor = new ParticleSystem.MinMaxGradient(tinted);
                        RetintLiveParticles(ps, tinted);
                    }
                    touched++;
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[MAPCOLOR] sky tint failed: {ex.Message}"); }
            return touched;
        }

        /// <summary>Restore the sky renderers to their cached vanilla colors —
        /// called when a vanilla/default skin becomes active so a previous custom
        /// skin's sky tint doesn't linger (the background object persists).</summary>
        public static void RestoreVanillaSky()
        {
            try
            {
                if (_vanillaSkyColors.Count == 0) return;
                var ah = ArtHandler.instance;
                var bgGO = ah != null ? ah.m_background : null;
                if (bgGO == null) return;
                int restored = 0;
                foreach (var sr in bgGO.GetComponentsInChildren<SpriteRenderer>(true))
                {
                    if (sr == null) continue;
                    if (_vanillaSkyColors.TryGetValue(sr.GetInstanceID(), out var vanilla))
                    {
                        sr.color = vanilla;
                        restored++;
                    }
                }
                foreach (var ps in bgGO.GetComponentsInChildren<ParticleSystem>(true))
                {
                    if (ps == null) continue;
                    Color vanilla = GetCachedVanillaColor(ps);
                    var main = ps.main;
                    main.startColor = new ParticleSystem.MinMaxGradient(vanilla);
                    RetintLiveParticles(ps, vanilla);
                    restored++;
                }
                if (restored > 0) Plugin.Log.LogInfo($"[MAPCOLOR] restored vanilla sky ({restored} renderer(s))");
            }
            catch { }
        }

        // Deterministic 0/1 bucket for a transform path, used to two-tone the wall
        // particle systems. FNV-1a (not string.GetHashCode, which is salted per process
        // run in modern .NET) so the SAME wall path maps to the SAME color on every map
        // load — no between-round color flipping.
        private static int StablePathParity(string s)
        {
            uint h = 2166136261u;
            for (int i = 0; i < s.Length; i++) { h ^= s[i]; h *= 16777619u; }
            return (int)(h & 1u);
        }

        private static string GetTransformPath(Transform t)
        {
            if (t == null) return "";
            var sb = new System.Text.StringBuilder(t.name);
            var p = t.parent;
            while (p != null)
            {
                sb.Insert(0, p.name + "/");
                p = p.parent;
            }
            return sb.ToString();
        }
    }

    [HarmonyPatch(typeof(ArtHandler), "NextArt")]
    class ArtHandlerNextArtPatch
    {
        // SKU → ROUNDS art profile name. Names confirmed via the [MAPCOLOR] Awake postfix log:
        //   arts[0..8] = RainbowSequence, Rainbow, Sweden, Gold, Soviet, Poison, Gold, Sky, Poison
        // SKUs not in this dict fall through to vanilla random behavior.
        private static readonly Dictionary<string, string> SKU_TO_ART = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            { "mapcolor_default", "" },          // empty → fall through to original NextArt
            { "mapcolor_sweden",  "Sweden" },
            { "mapcolor_sky",     "Sky" },
            { "mapcolor_poison",  "Poison" },
            { "mapcolor_gold",    "Gold" },
            { "mapcolor_soviet",  "Soviet" },
            { "mapcolor_rainbow", "Rainbow" },
        };

        // Index into the player's active_color_skus list. Advances by one per NextArt
        // invocation (which ROUNDS fires on Left Shift). Resets to 0 when the equipped
        // list changes so a newly-added color appears immediately instead of being
        // skipped while the index points past the end.
        private static int _cycleIndex = 0;
        private static int _cycleLastListHash = 0;

        // Last-known non-empty filtered equipped list. CachedPlayerStats can briefly
        // become null during a stats refresh or a consent flip; we don't want a Shift
        // press in that window to leak a vanilla random art into the rotation. Once
        // the user has equipped at least one custom color this session we stay on
        // that list until a NEW non-empty list replaces it.
        private static List<string> _lastEquippedFiltered;

        static bool Prefix(ArtHandler __instance)
        {
            try
            {
                var s = ApiClient.CachedPlayerStats;
                // Multi-equip: pick the next sku in the equipped-colors list on each press.
                // Filter null/empty entries so a corrupted server response doesn't
                // promote vanilla into the cycle.
                var rawEquipped = s?.active_color_skus;
                List<string> equipped = null;
                if (rawEquipped != null && rawEquipped.Count > 0)
                {
                    equipped = new List<string>(rawEquipped.Count);
                    for (int i = 0; i < rawEquipped.Count; i++)
                    {
                        var e = rawEquipped[i];
                        if (!string.IsNullOrEmpty(e)) equipped.Add(e);
                    }
                }
                // If the live list is empty but we cached a last-known-good one this
                // session, use that. Prevents the "after a bit of time vanilla colors
                // appear" bug — once the user has equipped customs, the rotation stays
                // on customs regardless of mid-session stats churn.
                if ((equipped == null || equipped.Count == 0) && _lastEquippedFiltered != null)
                {
                    equipped = _lastEquippedFiltered;
                    Plugin.Log.LogInfo($"[MAPCOLOR] Live equipped empty/null, reusing last-known list ({equipped.Count} skus)");
                }
                else if (equipped != null && equipped.Count > 0)
                {
                    _lastEquippedFiltered = equipped;
                }
                string sku = null;
                if (equipped != null && equipped.Count > 0)
                {
                    int listHash = 0;
                    for (int i = 0; i < equipped.Count; i++) listHash = (listHash * 31) + (equipped[i]?.GetHashCode() ?? 0);
                    if (listHash != _cycleLastListHash)
                    {
                        _cycleIndex = 0;
                        _cycleLastListHash = listHash;
                    }
                    // Advance the cycle ONLY on a real Left-Shift press. ROUNDS also calls
                    // NextArt automatically every round (often 2-3× at round start), and
                    // advancing on those made the skin auto-shuffle unpredictably — Sid kept
                    // landing on the dull brown/grey ones over and over and saw a multi-color
                    // FLICKER as several skus applied in a burst. Gating on Shift keeps the
                    // chosen skin STABLE per round; the player deliberately cycles with Shift.
                    bool manualShift = false;
                    try { manualShift = Input.GetKey(KeyCode.LeftShift) || Input.GetKey(KeyCode.RightShift); } catch { }
                    if (manualShift)
                        _cycleIndex = (_cycleIndex + 1) % equipped.Count;
                    sku = equipped[_cycleIndex % equipped.Count];
                    Plugin.Log.LogInfo($"[MAPCOLOR] {(manualShift ? "Shift cycle" : "auto-keep")} → {sku} (index {_cycleIndex}/{equipped.Count})");
                    // Toast the friendly skin name on a manual cycle so the player can find a
                    // specific skin (e.g. Magma) by sight.
                    if (manualShift) MapColorState.ShowToast(CustomMapColors.FriendlyName(sku));
                }
                // Backward compat: if the new list field is empty, fall back to the
                // legacy single-value active_color_sku (older clients / transitional state).
                if (string.IsNullOrEmpty(sku)) sku = s?.active_color_sku;
                if (string.IsNullOrEmpty(sku))
                {
                    Plugin.Log.LogInfo("[MAPCOLOR] No custom sku resolved — falling through to vanilla NextArt");
                    return true;
                }
                // Record the cycle-selected sku so Map.Start / physical-tint re-apply reads the
                // same sku the post-process path is using.
                MapColorState.CurrentSku = sku;

                // Custom-profile path: SetSpecificArt(baseArt) so the vanilla particle bg AND
                // base profile (bloom, vignette, etc.) load. Then ApplyPost(clonedProfile) where
                // the clone is baseArt.profile + our ColorGrading override. Cloning is critical:
                // mutating volume.profile in place corrupts the SHARED art profile for the rest
                // of the session — Sky's vanilla look would gain our tint permanently. The clone
                // is cached per SKU in CustomMapColors.
                if (CustomMapColors.IsCustomSku(sku))
                {
                    string baseArt = CustomMapColors.GetBaseArt(sku);
                    if (string.IsNullOrEmpty(baseArt)) return true;
                    // ROUNDS' ApplyArt (reached via SetSpecificArt) does NOT deactivate the
                    // previously-active art — only NextArt/SetMenuArt call the private TurnArtsOff
                    // first. Calling SetSpecificArt directly therefore leaves the OLD art's
                    // particles Play()-ing alongside the new one → two overlapping art layers (a
                    // second source of texture-flicker, confirmed by decompiling ArtHandler).
                    // Replicate TurnArtsOff via the public ArtInstance.TogglePart so only our
                    // chosen art stays active.
                    try
                    {
                        if (__instance.arts != null)
                            foreach (var a in __instance.arts) a?.TogglePart(false);
                    }
                    catch { }
                    __instance.SetSpecificArt(baseArt);
                    var basePr = __instance.volume != null ? __instance.volume.profile : null;
                    if (basePr == null)
                    {
                        Plugin.Log.LogWarning($"[MAPCOLOR] sku={sku} — volume.profile null after SetSpecificArt({baseArt})");
                        return false;
                    }
                    var clone = CustomMapColors.BuildOrGetClone(sku, basePr);
                    if (clone == null)
                    {
                        Plugin.Log.LogWarning($"[MAPCOLOR] sku={sku} — clone build failed, leaving base art active");
                        return false;
                    }
                    __instance.ApplyPost(clone);
                    // Backdrop levers that are safe mid-transition (no particle
                    // mutation): camera clears + SFSS light/ambient. Applying here
                    // makes Shift visibly swap the background on the same frame.
                    MapPhysicalColorPatch.ApplyCameraBackground(sku);
                    MapPhysicalColorPatch.ApplyLighting(sku);
                    // v1.32 item 7: lighting/shadow disable settings re-assert after
                    // the skin's own lighting pass touched the renderers.
                    MapPhysicalColorPatch.RenderPerfSettings.Apply();
                    // Freshly-built skin clones carry a copied CA object — assert
                    // the toggle on it same-frame.
                    MapPhysicalColorPatch.ChromaticAberrationSetting.Apply();
                    // Instant/sharp swap (v1.26.10): ROUNDS fades the post-process volume in
                    // gradually, which reads as the map "sliding" into the next skin on Shift.
                    // Force the volume to full weight on the same frame so the new ColorGrading
                    // snaps in immediately instead of lerping. Harmless if ROUNDS already had it
                    // at 1. Wrapped in try/catch since volume is reflected ROUNDS internals.
                    try { if (__instance.volume != null) __instance.volume.weight = 1f; } catch { }
                    // Re-apply wall / atmosphere particle tints for the new sku. CRITICAL: ROUNDS
                    // calls NextArt every round FROM INSIDE MapTransition.Move; mutating particles
                    // then NREs MapTransition+<Move>d__15 and the move STALLS — players don't get
                    // repositioned (stuck mid-screen, then off-screen next round — the freeze).
                    // So defer the particle work past the transition window. A genuine mid-round
                    // MANUAL Shift (well after Map.Start) is safe to apply immediately for snappy
                    // cycling. ColorGrading (ApplyPost, above) is volume-only and stays immediate.
                    bool inTransition = Time.time - MapPhysicalColorPatch.LastMapStartTime
                                        < MapPhysicalColorPatch.MapTransitionGuardSec;
                    if (inTransition)
                        MapPhysicalColorPatch.ScheduleDeferredTints(sku);
                    else
                        MapPhysicalColorPatch.ApplyPhysicalTintsForSku(null, sku);
                    Plugin.Log.LogInfo($"[MAPCOLOR] applied custom sku={sku} on base='{baseArt}' (deferParticles={inTransition})");
                    return false;
                }

                if (!SKU_TO_ART.TryGetValue(sku, out string artName))
                {
                    Plugin.Log.LogWarning($"[MAPCOLOR] Unknown sku '{sku}' — not in CustomMapColors presets, not in vanilla SKU_TO_ART. Equipped but not renderable; falling through to vanilla.");
                    return true;
                }
                if (string.IsNullOrEmpty(artName)) return true;        // explicit "default" sku

                // Safety: only override if the named art actually exists on this ArtHandler
                // instance. Earlier shipped a dict with guessed names that didn't match — the
                // SetSpecificArt no-op left the map invisible because we'd already short-
                // circuited the original NextArt. Now we fall through to vanilla random when
                // the name isn't found, so a stale config can never blank the map again.
                bool found = false;
                if (__instance.arts != null)
                {
                    var profileField = typeof(ArtInstance).GetField("profile",
                        System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
                    foreach (var art in __instance.arts)
                    {
                        if (art == null) continue;
                        var profileObj = profileField?.GetValue(art) as UnityEngine.Object;
                        if (profileObj != null && profileObj.name == artName) { found = true; break; }
                    }
                }
                if (!found)
                {
                    Plugin.Log.LogWarning($"[MAPCOLOR] sku={sku} mapped to art='{artName}' but no matching art on this ArtHandler — falling through to vanilla random");
                    return true;
                }
                __instance.SetSpecificArt(artName);
                return false;
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[MAPCOLOR] NextArt prefix failed: {ex.Message}");
                return true;
            }
        }
    }
}
