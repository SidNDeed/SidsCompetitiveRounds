using BepInEx;
using BepInEx.Configuration;
using BepInEx.Logging;
using System;
using System.Collections;
using UnityEngine;

namespace CompetitiveRounds
{
    [BepInPlugin(ModId, ModName, ModVersion)]
    [BepInProcess("Rounds.exe")]
    public class Plugin : BaseUnityPlugin
    {
        public const string ModId = "com.competitiverounds.mod";
        public const string ModName = "Competitive ROUNDS";
        public const string ModVersion = "1.4.0";

        internal static ManualLogSource Log;
        internal static CompetitiveRoundsBehaviour Instance;

        // Config entries
        internal static ConfigEntry<string> ApiBaseUrl;
        internal static ConfigEntry<bool> RankedEnabled;
        internal static ConfigEntry<bool> ShowNotifications;

        private static bool spawned = false;

        private void Awake()
        {
            Log = Logger;

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

            ShowNotifications = Config.Bind(
                "UI", "ShowNotifications",
                true,
                "Show in-game notifications for match results"
            );

            Log.LogInfo($"{ModName} v{ModVersion} initializing...");

            // Create persistent object with maximum protection
            if (!spawned)
            {
                var go = new GameObject("CompetitiveRounds_Persistent");
                go.hideFlags = HideFlags.HideAndDontSave;
                Instance = go.AddComponent<CompetitiveRoundsBehaviour>();
                spawned = true;
                Log.LogInfo("Created persistent GameObject with HideAndDontSave");
            }

            Log.LogInfo($"{ModName} v{ModVersion} loaded!");
        }
    }

    public class CompetitiveRoundsBehaviour : MonoBehaviour
    {
        private bool initialized = false;
        private float startupTimer = 0f;
        private bool startupComplete = false;

        private void Awake()
        {
            // Double protection
            hideFlags = HideFlags.HideAndDontSave;
            gameObject.hideFlags = HideFlags.HideAndDontSave;
            Plugin.Log.LogInfo("[PERSIST] Behaviour Awake, hideFlags set");
        }

        private void Update()
        {
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

            // F5 input
            if (Input.GetKeyDown(KeyCode.F5))
            {
                Plugin.Log.LogInfo("[INPUT] F5 pressed!");
                CompetitiveUI.ToggleOverlay();
            }

            // Poll game state
            try
            {
                GameStateWatcher.Poll();
            }
            catch (Exception ex)
            {
                Plugin.Log.LogError($"Poll error: {ex.Message}");
            }
        }

        private void DoInitialize()
        {
            Plugin.Log.LogInfo("[PERSIST] Delayed initialization starting...");

            ApiClient.Initialize(Plugin.ApiBaseUrl.Value);
            GameStateWatcher.Initialize();
            initialized = true;

            // Fetch initial data so overlay has content before first F5
            string steamId = GameStateWatcher.LocalSteamId;
            if (!string.IsNullOrEmpty(steamId) && steamId != "unknown")
            {
                ApiClient.FetchPlayerStats(steamId);
                ApiClient.FetchMatchHistory(steamId);
            }

            Plugin.Log.LogInfo("[PERSIST] All systems active! Press F5 for overlay.");
        }

        private void OnGUI()
        {
            if (!initialized) return;
            CompetitiveUI.DrawUI();
        }

        private void OnDestroy()
        {
            Plugin.Log.LogWarning("[PERSIST] Destroyed! Attempting respawn...");

            // Last resort: try to respawn ourselves
            try
            {
                var go = new GameObject("CompetitiveRounds_Respawn");
                go.hideFlags = HideFlags.HideAndDontSave;
                var newInstance = go.AddComponent<CompetitiveRoundsBehaviour>();
                Plugin.Instance = newInstance;
                Plugin.Log.LogInfo("[PERSIST] Respawned successfully!");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogError($"[PERSIST] Respawn failed: {ex.Message}");
            }
        }
    }
}
