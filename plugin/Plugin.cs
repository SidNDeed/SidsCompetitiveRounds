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
using System.Runtime.InteropServices;
using UnityEngine;

namespace CompetitiveRounds
{
    [BepInPlugin(ModId, ModName, ModVersion)]
    [BepInProcess("Rounds.exe")]
    public class Plugin : BaseUnityPlugin
    {
        public const string ModId = "com.competitiverounds.mod";
        public const string ModName = "Competitive ROUNDS";
        public const string ModVersion = "1.22.0";
        public const string RequiredGameVersion = "1.1.2";

        internal static ManualLogSource Log;
        internal static CompetitiveRoundsBehaviour Instance;
        internal static Harmony HarmonyInstance;

        // Config entries
        internal static ConfigEntry<string> ApiBaseUrl;
        internal static ConfigEntry<bool> RankedEnabled;
        internal static ConfigEntry<bool> ShowNotifications;
        internal static ConfigEntry<bool> ShowFps;
        internal static ConfigEntry<bool> ShowRegionPing;
        internal static ConfigEntry<bool> ShowIngameChat;
        internal static ConfigEntry<bool> ShowTrails;
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
                UnityEngine.Object.DontDestroyOnLoad(go);
                Instance = go.AddComponent<CompetitiveRoundsBehaviour>();
                // Sibling component that receives Photon IInRoomCallbacks — used by the cosmetic
                // trail system to re-attach opponents' trails when their cr_trail_* props arrive
                // after OnMatchStart has already iterated.
                go.AddComponent<TrailPhotonCallbacks>();
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
                return;
            }

            stateTimer += Time.deltaTime;

            // Safety timeout — 30s to account for disconnect + NCH connection sequence
            if (state != JoinState.Idle && stateTimer > 30f)
            {
                Plugin.Log.LogWarning("[QUEUE-JOINER] Timed out waiting for room join, resetting");
                Plugin.ClearPendingRoom();
                joinInitiated = false;
                state = JoinState.Idle;
                stateTimer = 0f;
                CompetitiveUI.ShowNotification("Failed to join ranked room", new Color(1f, 0.4f, 0.4f));
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
                        var roomOptions = new Photon.Realtime.RoomOptions
                        {
                            MaxPlayers = 2,
                            IsOpen = true,
                            IsVisible = true,
                            CustomRoomProperties = new ExitGames.Client.Photon.Hashtable
                            {
                                { "C2", capturedRoom }
                            },
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

            // Poll queue count when competitive page is open (every 10s)
            if (NativeUI.IsOpen)
            {
                try { ApiClient.UpdateQueueCount(); }
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
            CompetitiveUI.CacheRaycasters(); // No-op but kept for compat
            initialized = true;

            // Initialize UI type cache for native menu integration
            try { UIFactory.InitTypes(); UIFactory.InitFont(); }
            catch (Exception ex) { Plugin.Log.LogWarning($"[UI] Type init deferred: {ex.Message}"); }

            // Fetch initial data so overlay has content before first F5
            string steamId = GameStateWatcher.LocalSteamId;
            if (!string.IsNullOrEmpty(steamId) && steamId != "unknown")
            {
                // Sync ranked status to server on every startup
                // This ensures DB stays in sync even after resets/wipes
                ApiClient.ToggleRanked(steamId, Plugin.RankedEnabled.Value);

                ApiClient.FetchPlayerStats(steamId);
                ApiClient.FetchMatchHistory(steamId);
                ApiClient.FetchBlockedPlayers(steamId);
                // Determine admin status once at startup. The admin tab is hidden when this is false.
                ApiClient.CheckAdminStatus(steamId);
            }

            // Wire the chat pipe so incoming messages reach the UI log.
            ChatClient.OnMessage = NativeUI.OnChatMessage;

            // If the user already granted consent in a previous session, open the chat WS now.
            // Fresh installs stay offline until the consent modal gets a Yes.
            if (Plugin.DataConsentGranted)
                ChatClient.Connect();

            Plugin.Log.LogInfo("[PERSIST] All systems active! Press F5 for overlay.");
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
                            GameStateWatcher.OnLocalCardOffered(cn, cid == targetCardID, round);
                        }
                        catch { }
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

            // Already injected and button still exists
            if (injected && injectedButton != null) return;

            // Button was destroyed (scene change) — allow re-injection
            if (injected && injectedButton == null)
            {
                injected = false;
                retryCount = 0;
                // Don't re-log on re-injection — already logged once
            }

            // Stop trying after max retries (resets on scene change)
            if (retryCount >= maxRetries) return;
            retryCount++;

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

        // Known mismatches between GameObject name (log capture) and cardName field
        private static readonly Dictionary<string, string> hardAliases = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            { "Leach", "Leech" },
            { "BombsAway", "Bombs Away" },
            { "Glasscannon", "Glass Cannon" },
            { "ShieldCharge", "Shield Charge" },
            { "AbyssalCountdown", "Abyssal Countdown" },
            { "Poison", "Poison Bullets" },
            { "Prisitne Perseverence", "Pristine Perseverence" },
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
            // ArtInstance.profile is a PostProcessProfile from Unity.Postprocessing.Runtime,
            // which we don't reference at compile time. Reflect into it so we don't have to.
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
    [HarmonyPatch(typeof(Map), "Start")]
    class MapPhysicalColorPatch
    {
        // Cached tinted materials, keyed by "{sku}|{originalMaterialName}".
        private static readonly Dictionary<string, Material> _matCache = new Dictionary<string, Material>();
        private static bool _loggedTypes;

        static void Postfix(Map __instance)
        {
            try
            {
                var stats = ApiClient.CachedPlayerStats;
                string sku = stats?.active_color_sku;
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

                // Step 1: SpriteRenderer.color on every sprite child of Map.
                int sprites = 0;
                var typeCounts = new Dictionary<string, int>();
                foreach (var r in __instance.GetComponentsInChildren<Renderer>(true))
                {
                    if (r == null) continue;
                    string tn = r.GetType().Name;
                    typeCounts.TryGetValue(tn, out int n); typeCounts[tn] = n + 1;
                    if (tintN.HasValue && r is SpriteRenderer sr) { sr.color = c; sprites++; }
                }
                if (!_loggedTypes && typeCounts.Count > 0)
                {
                    _loggedTypes = true;
                    foreach (var kv in typeCounts)
                        Plugin.Log.LogInfo($"[MAPCOLOR] Map child renderer type {kv.Key}: {kv.Value}");
                }

                if (!tintN.HasValue) return;

                // Confirmed from prior diagnostic: Map.MapMaterial is null, walls/floors aren't
                // child renderers of Map (Map's children are 49 SpriteRenderers = the moving
                // boxes). Walls live elsewhere in the scene. Strategy: scan EVERY SpriteRenderer
                // in the scene and tint any that look map-like (skip player avatars, bullets,
                // UI sprites) by inspecting parent path. Tint via SpriteRenderer.color so we
                // don't need to clone any material.
                int sceneSprites = 0, sceneSkipped = 0;
                var pathSamples = new Dictionary<string, int>(StringComparer.Ordinal);
                foreach (var r in UnityEngine.Object.FindObjectsOfType<SpriteRenderer>())
                {
                    if (r == null) continue;
                    string path = GetTransformPath(r.transform);
                    // Sample the first ~30 unique parent prefixes for diagnostic — tells us what
                    // top-level objects exist so we can tighten the filter next round if needed.
                    string topLevel = path.Split('/')[0];
                    if (pathSamples.Count < 60)
                    {
                        pathSamples.TryGetValue(topLevel, out int n);
                        pathSamples[topLevel] = n + 1;
                    }
                    // Skip obvious non-map renderers: players, bullets, UI, HUD, projectiles.
                    string pl = path.ToLowerInvariant();
                    if (pl.Contains("player") || pl.Contains("bullet") || pl.Contains("ui_") ||
                        pl.Contains("hud") || pl.Contains("/cards") || pl.Contains("cardchoice") ||
                        pl.Contains("particle") || pl.Contains("character"))
                    { sceneSkipped++; continue; }
                    r.color = c;
                    sceneSprites++;
                }
                if (!_loggedScenePaths)
                {
                    _loggedScenePaths = true;
                    foreach (var kv in pathSamples)
                        Plugin.Log.LogInfo($"[MAPCOLOR] scene top-level: {kv.Key} ({kv.Value} sprites)");
                    // Walls/floors aren't sprites — log every NON-SpriteRenderer in the scene with
                    // its full path so we can identify what to target. One-shot.
                    var nonSpriteByType = new Dictionary<string, int>();
                    var nonSpritePaths = new List<string>();
                    foreach (var rr in UnityEngine.Object.FindObjectsOfType<Renderer>())
                    {
                        if (rr == null || rr is SpriteRenderer) continue;
                        string tname = rr.GetType().Name;
                        // Skip SpriteMask — they're player limb masks (246 of them) and were
                        // monopolizing the 80-entry dump cap, hiding the single MeshRenderer
                        // we actually need to identify (the map wall mesh).
                        if (tname == "SpriteMask") { nonSpriteByType.TryGetValue(tname, out int sc); nonSpriteByType[tname] = sc + 1; continue; }
                        nonSpriteByType.TryGetValue(tname, out int cnt);
                        nonSpriteByType[tname] = cnt + 1;
                        if (nonSpritePaths.Count < 200)
                        {
                            string mn = rr.sharedMaterial != null ? rr.sharedMaterial.name : "<null>";
                            nonSpritePaths.Add(tname + "  " + GetTransformPath(rr.transform) + "  mat=" + mn);
                        }
                    }
                    foreach (var kv in nonSpriteByType)
                        Plugin.Log.LogInfo($"[MAPCOLOR] non-sprite renderer type {kv.Key}: {kv.Value}");
                    foreach (var p in nonSpritePaths)
                        Plugin.Log.LogInfo($"[MAPCOLOR] non-sprite path: {p}");
                }
                // Step 3 — tint the wall-like particle systems. Alternate between MapBlockColor
                // and SecondaryColor by index so the wall reads as multi-tone instead of a flat
                // single color block. Vanilla arts achieve their "atmosphere" via per-particle
                // color variation; this restores that feel for our custom presets.
                Color secondary = CustomMapColors.GetSecondaryColor(sku);
                int boundaryParts = 0, idx = 0;
                foreach (var ps in UnityEngine.Object.FindObjectsOfType<ParticleSystem>())
                {
                    if (ps == null) continue;
                    string ppath = GetTransformPath(ps.transform);
                    if (!ppath.StartsWith("OutOfBounds/", StringComparison.OrdinalIgnoreCase)) continue;
                    var main = ps.main;
                    Color pc = (idx++ % 2 == 0) ? c : secondary;
                    main.startColor = new ParticleSystem.MinMaxGradient(pc);
                    boundaryParts++;
                }

                // Step 4 — vanilla ArtInstance particle backdrops, also alternating.
                // We use a single counter shared across arts so the secondary color is sprinkled
                // evenly across the active art's particles.
                int artParts = 0;
                try
                {
                    var ah = ArtHandler.instance;
                    if (ah != null && ah.arts != null)
                    {
                        var partsField = typeof(ArtInstance).GetField("parts",
                            System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
                        int aidx = 0;
                        foreach (var art in ah.arts)
                        {
                            if (art == null) continue;
                            var partsArr = partsField?.GetValue(art) as ParticleSystem[];
                            if (partsArr == null) continue;
                            foreach (var ps in partsArr)
                            {
                                if (ps == null) continue;
                                var main = ps.main;
                                Color apc = (aidx++ % 2 == 0) ? c : secondary;
                                main.startColor = new ParticleSystem.MinMaxGradient(apc);
                                artParts++;
                            }
                        }
                    }
                }
                catch (Exception ex) { Plugin.Log.LogWarning($"[MAPCOLOR] art-particle tint failed: {ex.Message}"); }

                Plugin.Log.LogInfo($"[MAPCOLOR] Map.Start sku={sku}: map-children-sprites={sprites}, scene-sprites-tinted={sceneSprites}, boundary-parts={boundaryParts}, art-parts={artParts}, skipped={sceneSkipped}");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[MAPCOLOR] Map tint failed: {ex.Message}"); }
        }

        private static bool _loggedScenePaths;

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

        static bool Prefix(ArtHandler __instance)
        {
            try
            {
                var s = ApiClient.CachedPlayerStats;
                string sku = s?.active_color_sku;
                if (string.IsNullOrEmpty(sku)) return true;

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
                    Plugin.Log.LogInfo($"[MAPCOLOR] applied custom sku={sku} on base='{baseArt}' (cloned profile)");
                    return false;
                }

                if (!SKU_TO_ART.TryGetValue(sku, out string artName)) return true;
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
