using BepInEx;
using BepInEx.Configuration;
using BepInEx.Logging;
using HarmonyLib;
using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

namespace CompetitiveRounds
{
    [BepInPlugin(ModId, ModName, ModVersion)]
    [BepInProcess("Rounds.exe")]
    public class Plugin : BaseUnityPlugin
    {
        public const string ModId = "com.competitiverounds.mod";
        public const string ModName = "Competitive ROUNDS";
        public const string ModVersion = "1.10.0";

        internal static ManualLogSource Log;
        internal static CompetitiveRoundsBehaviour Instance;
        internal static Harmony HarmonyInstance;

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

            // Try Harmony patching
            try
            {
                HarmonyInstance = new Harmony(ModId);
                HarmonyInstance.PatchAll();
                Log.LogInfo("Harmony patches applied successfully!");
            }
            catch (Exception ex)
            {
                Log.LogWarning($"Harmony patching failed (mod will work without it): {ex.Message}");
            }

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

            // Try to inject main menu button (idempotent, checks once/sec)
            try
            {
                MainMenuInjector.TryInject();
            }
            catch { }
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

    // ── Harmony Patches ────────────────────────────────────────

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
    /// Injects a "COMPETITIVE" button into the main menu's ListMenu.
    /// Runs from Update() — checks once per scene if injection is needed.
    /// </summary>
    public static class MainMenuInjector
    {
        private static bool injected = false;
        private static float checkTimer = 0f;
        private static GameObject injectedButton = null;

        public static void TryInject()
        {
            // Don't spam checks — once per second
            checkTimer += Time.deltaTime;
            if (checkTimer < 1f) return;
            checkTimer = 0f;

            // Already injected and button still exists
            if (injected && injectedButton != null) return;
            injected = false; // Reset if button was destroyed (scene change)

            // Only inject when not in a Photon room (i.e., on main menu)
            if (Photon.Pun.PhotonNetwork.InRoom) return;

            try
            {
                DoInject();
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[MENU] Injection failed: {ex.Message}");
            }
        }

        private static void DoInject()
        {
            // Find the ListMenu in the scene
            var listMenu = UnityEngine.Object.FindObjectOfType<ListMenu>();
            if (listMenu == null) return;

            // Find the button container — the ListMenu's transform holds button children
            Transform container = listMenu.transform;
            if (container.childCount == 0) return;

            // Find an existing button to clone (use the last one — usually QUIT)
            Transform templateTransform = null;
            for (int i = container.childCount - 1; i >= 0; i--)
            {
                var child = container.GetChild(i);
                if (child.GetComponent<ListMenuButton>() != null)
                {
                    templateTransform = child;
                    break;
                }
            }

            if (templateTransform == null)
            {
                Plugin.Log.LogWarning("[MENU] No ListMenuButton found to clone");
                return;
            }

            // Clone the button
            var clone = UnityEngine.Object.Instantiate(templateTransform.gameObject, container);
            clone.name = "CompetitiveRoundsButton";

            // Move it above the template (insert before QUIT)
            clone.transform.SetSiblingIndex(templateTransform.GetSiblingIndex());

            // Change the text via reflection (TextMeshProUGUI)
            bool textSet = false;
            try
            {
                // Find TMP_Text type in loaded assemblies
                System.Type tmpType = null;
                foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                {
                    tmpType = asm.GetType("TMPro.TMP_Text");
                    if (tmpType != null) break;
                }

                if (tmpType != null)
                {
                    var tmpComponent = clone.GetComponentInChildren(tmpType);
                    if (tmpComponent != null)
                    {
                        var textProp = tmpType.GetProperty("text",
                            System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
                        if (textProp != null)
                        {
                            textProp.SetValue(tmpComponent, "COMPETITIVE");
                            textSet = true;
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[MENU] TMP text change failed: {ex.Message}");
            }

            if (!textSet)
            {
                Plugin.Log.LogWarning("[MENU] Could not set button text");
            }

            // Remove the existing ListMenuButton so it doesn't trigger the original action
            var oldButton = clone.GetComponent<ListMenuButton>();
            if (oldButton != null)
                UnityEngine.Object.Destroy(oldButton);

            // Add our click handler component
            clone.AddComponent<CompetitiveMenuButton>();

            injectedButton = clone;
            injected = true;
            Plugin.Log.LogInfo("[MENU] Competitive button injected into main menu!");
        }
    }

    /// <summary>
    /// Simple MonoBehaviour attached to the injected menu button.
    /// Detects pointer clicks and opens the overlay.
    /// </summary>
    public class CompetitiveMenuButton : MonoBehaviour
    {
        private void Start()
        {
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

        public static void Register(string cardName, string rarity)
        {
            if (!string.IsNullOrEmpty(cardName))
                lookup[cardName] = rarity;
        }

        public static string GetRarity(string cardName)
        {
            if (string.IsNullOrEmpty(cardName)) return "Unknown";
            // Try exact match first, then title case
            if (lookup.TryGetValue(cardName, out string rarity))
                return rarity;
            return "Unknown";
        }

        public static int Count => lookup.Count;

        /// <summary>
        /// Scan all CardInfo objects in the scene and build the rarity lookup.
        /// Can be called multiple times safely — only scans if lookup is empty.
        /// </summary>
        public static void ScanAll()
        {
            if (lookup.Count > 0) return; // Already populated

            try
            {
                var cardInfoType = typeof(CardInfo);
                var flags = System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance;

                // Find name field (we know from logs it's "cardName")
                var nameField = cardInfoType.GetField("cardName", flags);
                var rarityField = cardInfoType.GetField("rarity", flags);

                // Also try the property "CardName" 
                var nameProp = cardInfoType.GetProperty("CardName", flags);

                // Scan all CardInfo objects in scene (including inactive)
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

                        Register(cardName, rarity);
                    }
                    catch { }
                }

                if (lookup.Count > 0)
                    Plugin.Log.LogInfo($"[RARITY] Card rarity lookup built: {lookup.Count} cards. Sample: {GetSampleEntries(5)}");
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
}
